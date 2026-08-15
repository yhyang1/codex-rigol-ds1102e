from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import signal
import sys
import time

from .artifacts import export_csv, write_capture, write_event
from .analysis import analyze_capture, analyze_series
from .config import load_config
from .errors import ConfigurationError, DeviceIdentityError, RigolError, TriggerTimeoutError, WaveformDataError
from .instrument import CaptureSession, VisaConnection, capture_once, identify
from .paired_analysis import analyze_paired_series
from .session import ContactGate, MultiChannelQualificationResult, QualificationResult, assess_channels
from .verify import verify_artifacts


def _channels(value: str) -> tuple[int, ...]:
    try:
        channels = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("channels must be 1, 2, or 1,2") from exc
    if (
        not channels
        or any(channel not in (1, 2) for channel in channels)
        or len(set(channels)) != len(channels)
    ):
        raise argparse.ArgumentTypeError("channels must be unique and contain only 1 and/or 2")
    return channels


def _positive(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _nonnegative(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return number


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return number


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="rigol", description="RIGOL DS1102E USB acquisition")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--resource", help="exact VISA resource; auto-detected by default")
    common.add_argument("--serial", help="required serial when multiple matching instruments exist")
    common.add_argument("--io-timeout", type=_positive, default=30.0, help="USB I/O timeout in seconds (default: 30)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", parents=[common], help="identify the connected instrument")
    capture = commands.add_parser("capture", parents=[common], help="capture one fresh triggered waveform")
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--config", type=Path)
    capture.add_argument("--channels", type=_channels, default=(1,))
    capture.add_argument("--trigger-timeout", type=_positive, required=True)
    watch = commands.add_parser("watch", parents=[common], help="capture fresh triggered waveforms periodically")
    watch.add_argument("--output", type=Path, required=True)
    watch.add_argument("--config", type=Path)
    watch.add_argument("--channels", type=_channels, default=(1,))
    watch.add_argument("--trigger-timeout", type=_positive, required=True)
    watch.add_argument("--interval", type=_positive, required=True)
    watch.add_argument("--count", type=int)
    session = commands.add_parser(
        "session", parents=[common], help="wait for stable probe contact, then capture qualified frames"
    )
    session.add_argument("--output", type=Path, required=True)
    session.add_argument("--config", type=Path)
    session.add_argument("--channels", type=_channels, default=(1,))
    session.add_argument("--trigger-attempt-timeout", type=_positive, default=5.0)
    session.add_argument("--qualify-consecutive", type=_positive_int, default=3)
    session.add_argument("--accepted-count", type=_positive_int, default=10)
    session.add_argument("--wait-timeout", type=_nonnegative, default=0.0)
    session.add_argument("--keep-rejected", action="store_true")
    export = commands.add_parser("export-csv", help="export one channel from an existing capture")
    export.add_argument("capture_dir", type=Path)
    export.add_argument("--channel", type=int, choices=(1, 2), default=1)
    analyze = commands.add_parser("analyze", help="analyze one pulse waveform against a nominal frequency")
    analyze.add_argument("capture_dir", type=Path)
    analyze.add_argument("--channel", type=int, choices=(1, 2), default=1)
    analyze.add_argument("--nominal-frequency", type=_positive, required=True)
    series = commands.add_parser("analyze-series", help="aggregate frequency, phase, and glitch results")
    series.add_argument("root", type=Path)
    series.add_argument("--channel", type=int, choices=(1, 2), default=1)
    series.add_argument("--nominal-frequency", type=_positive, required=True)
    paired = commands.add_parser(
        "analyze-paired-series",
        help="analyze one trigger channel and one dependent pulse channel",
    )
    paired.add_argument("root", type=Path)
    paired.add_argument("--trigger-channel", type=int, choices=(1, 2), required=True)
    paired.add_argument("--strobe-channel", type=int, choices=(1, 2), required=True)
    paired.add_argument("--expectations", type=Path)
    verify = commands.add_parser("verify", help="verify hashes and structure for a capture or run")
    verify.add_argument("path", type=Path)
    verify.add_argument("--output", type=Path, help="also persist the JSON verification report")
    return root


def _connect(args: argparse.Namespace, serial: str | None):
    return VisaConnection(args.resource, args.serial or serial, args.io_timeout)


def _acquire_with_retry(
    args: argparse.Namespace,
    config,
    serial: str | None,
    sequence: int,
):
    for attempt in (1, 2):
        try:
            with _connect(args, serial) as (inst, resource):
                idn = identify(inst, serial)
                return capture_once(inst, resource, idn, config, args.channels, args.trigger_timeout)
        except WaveformDataError as exc:
            if attempt == 2:
                raise
            write_event(
                args.output,
                "capture_retry",
                sequence=sequence,
                attempt=attempt,
                error=str(exc),
                error_type=type(exc).__name__,
            )


def _doctor(args: argparse.Namespace) -> int:
    with _connect(args, None) as (inst, resource):
        idn = identify(inst, args.serial)
        print(json.dumps({"resource": resource, "idn": idn}, indent=2))
    return 0


def _capture(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    serial = args.serial or config.instrument.serial
    capture = _acquire_with_retry(args, config, serial, 1)
    path = write_capture(capture, args.output, 1)
    write_event(args.output, "capture_success", sequence=1, path=str(path))
    print(path)
    return 0


def _watch(args: argparse.Namespace) -> int:
    if args.count is not None and args.count <= 0:
        raise RigolError("--count must be positive")
    config = load_config(args.config)
    serial = args.serial or config.instrument.serial
    stop = False

    def request_stop(signum, frame):
        nonlocal stop
        stop = True

    previous_int = signal.signal(signal.SIGINT, request_stop)
    previous_term = signal.signal(signal.SIGTERM, request_stop)
    failures = 0
    sequence = 0
    try:
        with _connect(args, serial) as (inst, resource):
            idn = identify(inst, serial)
            write_event(args.output, "watch_started", resource=resource, idn=idn)
        while not stop and (args.count is None or sequence < args.count):
            sequence += 1
            cycle_started = time.monotonic()
            try:
                capture = _acquire_with_retry(args, config, serial, sequence)
                path = write_capture(capture, args.output, sequence)
                write_event(args.output, "capture_success", sequence=sequence, path=str(path))
                print(path, flush=True)
            except RigolError as exc:
                failures += 1
                write_event(args.output, "capture_failed", sequence=sequence, error=str(exc), error_type=type(exc).__name__)
                print(f"capture {sequence} failed: {exc}", file=sys.stderr, flush=True)
            elapsed = time.monotonic() - cycle_started
            if elapsed > args.interval:
                write_event(args.output, "overrun", sequence=sequence, elapsed_s=elapsed, interval_s=args.interval)
                continue
            deadline = time.monotonic() + (args.interval - elapsed)
            while not stop and time.monotonic() < deadline:
                time.sleep(min(0.1, deadline - time.monotonic()))
        write_event(args.output, "watch_stopped", captures=sequence, failures=failures, interrupted=stop)
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)
    return 3 if failures else 0


def _emit_status(output: Path, event: str, **fields) -> None:
    write_event(output, event, **fields)
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def _qualification_payload(result: QualificationResult) -> dict:
    payload = asdict(result)
    payload["reasons"] = list(result.reasons)
    return payload


def _multi_qualification_payload(result: MultiChannelQualificationResult) -> dict:
    return {
        "accepted": result.accepted,
        "channels": {
            str(channel): _qualification_payload(channel_result)
            for channel, channel_result in result.channels.items()
        },
    }


def _session(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if len(args.channels) > 1:
        missing_qualifications = [
            channel for channel in args.channels if channel not in config.qualifications
        ]
        if missing_qualifications:
            raise ConfigurationError(
                "two-channel session requires [qualification.channel1] and "
                "[qualification.channel2] definitions"
            )
    serial = args.serial or config.instrument.serial
    stop = False

    def request_stop(signum, frame):
        nonlocal stop
        stop = True

    previous_int = signal.signal(signal.SIGINT, request_stop)
    previous_term = signal.signal(signal.SIGTERM, request_stop)
    gate = ContactGate(args.qualify_consecutive)
    accepted_count = 0
    rejected_count = 0
    waiting_attempts = 0
    channel_qualifications = {
        channel: config.qualification_for(channel) for channel in args.channels
    }
    provisional_frequencies = {
        channel: qualification.nominal_frequency_hz
        for channel, qualification in channel_qualifications.items()
    }
    outcome = "cancelled"
    started = time.monotonic()
    baseline_saved = None
    baseline_was_running = False
    restored = True
    reconnects = 0
    try:
        _emit_status(
            args.output,
            "session_started",
            requested_serial=serial,
            qualify_consecutive=args.qualify_consecutive,
            accepted_target=args.accepted_count,
            wait_timeout_s=args.wait_timeout,
            channels=list(args.channels),
        )
        while not stop and accepted_count < args.accepted_count:
            if args.wait_timeout and time.monotonic() - started >= args.wait_timeout:
                outcome = "deadline"
                break
            try:
                with _connect(args, serial) as (inst, resource):
                    idn = identify(inst, serial)
                    _emit_status(
                        args.output,
                        "instrument_connected" if reconnects == 0 else "instrument_reconnected",
                        resource=resource,
                        idn=idn,
                        reconnects=reconnects,
                    )
                    with CaptureSession(inst, resource, idn, config, args.channels) as acquisition:
                        if baseline_saved is None:
                            baseline_saved = list(acquisition.saved)
                            baseline_was_running = acquisition.was_running
                        else:
                            acquisition.saved = list(baseline_saved)
                            acquisition.was_running = baseline_was_running
                        _emit_status(args.output, "armed", message="waiting for probe contact")
                        while not stop and accepted_count < args.accepted_count:
                            if args.wait_timeout and time.monotonic() - started >= args.wait_timeout:
                                outcome = "deadline"
                                break
                            try:
                                capture = acquisition.capture(args.trigger_attempt_timeout)
                            except TriggerTimeoutError:
                                waiting_attempts += 1
                                _emit_status(
                                    args.output,
                                    "waiting_contact",
                                    attempts=waiting_attempts,
                                    accepted=accepted_count,
                                )
                                continue
                            except WaveformDataError as exc:
                                rejected_count += 1
                                gate.observe(None, False)
                                _emit_status(
                                    args.output,
                                    "candidate_rejected",
                                    reasons=["waveform_transfer_error"],
                                    error=str(exc),
                                )
                                raise

                            result = assess_channels(
                                capture,
                                channel_qualifications,
                                provisional_frequencies,
                            )
                            transition = gate.observe((capture, result), result.accepted)
                            if result.accepted:
                                for channel, channel_result in result.channels.items():
                                    if channel_qualifications[channel].nominal_frequency_hz is None:
                                        provisional_frequencies[channel] = channel_result.reference_frequency_hz
                            if transition.state in {"rejected", "contact_lost"}:
                                rejected_count += 1
                                for channel, qualification in channel_qualifications.items():
                                    if qualification.nominal_frequency_hz is None:
                                        provisional_frequencies[channel] = None
                                if args.keep_rejected:
                                    write_capture(
                                        capture,
                                        args.output / "rejected",
                                        rejected_count,
                                        {"qualification": _multi_qualification_payload(result)},
                                    )
                                _emit_status(
                                    args.output,
                                    transition.state,
                                    qualification=_multi_qualification_payload(result),
                                    accepted=accepted_count,
                                )
                                continue
                            if transition.state == "candidate":
                                _emit_status(
                                    args.output,
                                    "contact_candidate",
                                    candidate=transition.candidate_count,
                                    required=args.qualify_consecutive,
                                    qualification=_multi_qualification_payload(result),
                                )
                                continue
                            if transition.state == "contact_qualified":
                                _emit_status(
                                    args.output,
                                    "contact_qualified",
                                    epoch=transition.epoch,
                                    promoted=len(transition.promoted),
                                )
                            for promoted_capture, promoted_result in transition.promoted:
                                if accepted_count >= args.accepted_count:
                                    break
                                accepted_count += 1
                                path = write_capture(
                                    promoted_capture,
                                    args.output,
                                    accepted_count,
                                    {
                                        "session": {
                                            "epoch": transition.epoch,
                                            "accepted_sequence": accepted_count,
                                            "qualification": _multi_qualification_payload(promoted_result),
                                        }
                                    },
                                )
                                _emit_status(
                                    args.output,
                                    "capture_accepted",
                                    sequence=accepted_count,
                                    target=args.accepted_count,
                                    epoch=transition.epoch,
                                    path=str(path),
                                )
                    restored = True
            except Exception as exc:
                if isinstance(exc, DeviceIdentityError) and not str(exc).startswith(
                    "expected exactly one DS1102E USB resource"
                ):
                    raise
                restored = baseline_saved is None
                reconnects += 1
                gate.observe(None, False)
                for channel, qualification in channel_qualifications.items():
                    if qualification.nominal_frequency_hz is None:
                        provisional_frequencies[channel] = None
                _emit_status(
                    args.output,
                    "transport_waiting",
                    reconnects=reconnects,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                retry_deadline = time.monotonic() + 1.0
                while not stop and time.monotonic() < retry_deadline:
                    time.sleep(min(0.1, retry_deadline - time.monotonic()))
        if accepted_count >= args.accepted_count:
            outcome = "complete"
        _emit_status(
            args.output,
            f"session_{outcome}",
            accepted=accepted_count,
            target=args.accepted_count,
            rejected=rejected_count,
            waiting_attempts=waiting_attempts,
            reconnects=reconnects,
            restored=restored,
        )
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)
    if outcome == "complete":
        return 0
    if outcome == "cancelled":
        return 130
    return 3


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            return _doctor(args)
        if args.command == "capture":
            return _capture(args)
        if args.command == "watch":
            return _watch(args)
        if args.command == "session":
            return _session(args)
        if args.command == "export-csv":
            print(export_csv(args.capture_dir, args.channel))
            return 0
        if args.command == "analyze":
            print(json.dumps(analyze_capture(args.capture_dir, args.channel, args.nominal_frequency), indent=2))
            return 0
        if args.command == "analyze-series":
            print(analyze_series(args.root, args.channel, args.nominal_frequency))
            return 0
        if args.command == "analyze-paired-series":
            print(analyze_paired_series(
                args.root,
                args.trigger_channel,
                args.strobe_channel,
                args.expectations,
            ))
            return 0
        if args.command == "verify":
            report = verify_artifacts(args.path)
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            if args.output is not None:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                temporary = args.output.with_name(f".{args.output.name}.tmp")
                temporary.write_text(rendered, encoding="utf-8")
                temporary.replace(args.output)
            print(rendered, end="")
            return 0 if report["valid"] else 4
        raise AssertionError(args.command)
    except RigolError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
