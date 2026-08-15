from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any, Protocol
import warnings

import numpy as np

from .config import AppConfig, ChannelConfig
from .errors import AcquisitionError, DeviceIdentityError, RestorationError, TriggerTimeoutError, WaveformDataError
from .waveform import ParsedWaveform, parse_legacy_block, time_axis, voltage_axis


VID = 0x1AB1
PID = 0x0588
SUPPORTED_SINGLE_MODES = {"EDGE", "PULSE", "SLOPE", "PATTERN", "DURATION"}


class MessageInstrument(Protocol):
    timeout: int
    write_termination: str | None
    read_termination: str | None

    def query(self, command: str) -> str: ...
    def write(self, command: str) -> Any: ...
    def read_raw(self, size: int | None = None) -> bytes: ...
    def clear(self) -> Any: ...
    def close(self) -> Any: ...


@dataclass
class ChannelWaveform:
    channel: int
    header: bytes
    raw: np.ndarray
    voltage_v: np.ndarray
    scale_v_div: float
    offset_v: float
    probe: float
    memory_depth: int


@dataclass
class Capture:
    captured_at_utc: str
    idn: str
    resource: str
    sample_rate_hz: float
    timebase_scale_s_div: float
    timebase_offset_s: float
    time_s: np.ndarray
    channels: dict[int, ChannelWaveform]
    trigger_wait_s: float
    transfer_s: float
    settings: dict[str, str]
    measurements: dict[int, dict[str, float | None]]


@dataclass(frozen=True)
class SettingChange:
    query: str
    set_prefix: str
    value: str


class VisaConnection:
    def __init__(self, resource: str | None, serial: str | None, timeout_s: float):
        self.requested_resource = resource
        self.serial = serial
        self.timeout_s = timeout_s
        self.manager: Any = None
        self.instrument: MessageInstrument | None = None
        self.resource = ""

    def __enter__(self) -> tuple[MessageInstrument, str]:
        import pyvisa

        self.manager = pyvisa.ResourceManager("@py")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", module=r"pyvisa_py\.tcpip")
            resources = tuple(self.manager.list_resources("USB?*::INSTR"))
        if self.requested_resource:
            candidates = [self.requested_resource]
        else:
            candidates = [r for r in resources if is_ds1102e_resource(r)]
            if self.serial:
                candidates = [r for r in candidates if self.serial.upper() in r.upper()]
        if len(candidates) != 1:
            raise DeviceIdentityError(
                f"expected exactly one DS1102E USB resource, found {len(candidates)}; resources={resources}"
            )
        self.resource = candidates[0]
        self.instrument = self.manager.open_resource(self.resource)
        self.instrument.timeout = int(self.timeout_s * 1000)
        self.instrument.write_termination = "\n"
        self.instrument.read_termination = None
        return self.instrument, self.resource

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            if self.instrument is not None:
                self.instrument.close()
        finally:
            if self.manager is not None:
                self.manager.close()


def is_ds1102e_resource(resource: str) -> bool:
    fields = resource.split("::")
    if len(fields) < 3 or not fields[0].upper().startswith("USB"):
        return False
    try:
        return int(fields[1], 0) == VID and int(fields[2], 0) == PID
    except ValueError:
        return False


def query(inst: MessageInstrument, command: str) -> str:
    return inst.query(command).strip()


def identify(inst: MessageInstrument, expected_serial: str | None = None) -> str:
    idn = query(inst, "*IDN?")
    fields = [field.strip() for field in idn.split(",")]
    if len(fields) < 4 or fields[0].upper() != "RIGOL TECHNOLOGIES" or fields[1] != "DS1102E":
        raise DeviceIdentityError(f"unexpected instrument identity: {idn!r}")
    if expected_serial and fields[2] != expected_serial:
        raise DeviceIdentityError(f"expected serial {expected_serial}, received {fields[2]}")
    return idn


def _bool(value: bool) -> str:
    return "ON" if value else "OFF"


def _profile_changes(config: AppConfig) -> list[SettingChange]:
    changes: list[SettingChange] = []
    if config.acquisition.type is not None:
        changes.append(SettingChange(":ACQ:TYPE?", ":ACQ:TYPE", config.acquisition.type))
    if config.acquisition.memory_depth is not None:
        changes.append(SettingChange(":ACQ:MEMD?", ":ACQ:MEMD", config.acquisition.memory_depth))
    for number, channel in config.channels.items():
        changes.extend(_channel_changes(number, channel))
    if config.timebase.scale_s_div is not None:
        changes.append(SettingChange(":TIM:SCAL?", ":TIM:SCAL", str(config.timebase.scale_s_div)))
    if config.timebase.offset_s is not None:
        changes.append(SettingChange(":TIM:OFFS?", ":TIM:OFFS", str(config.timebase.offset_s)))
    trigger = config.trigger
    has_trigger_profile = any(
        value is not None
        for value in (trigger.mode, trigger.source, trigger.slope, trigger.level_v, trigger.coupling)
    )
    mode = trigger.mode or "EDGE"
    if has_trigger_profile:
        changes.append(SettingChange(":TRIG:MODE?", ":TRIG:MODE", mode))
    if trigger.source is not None:
        changes.append(SettingChange(f":TRIG:{mode}:SOUR?", f":TRIG:{mode}:SOUR", trigger.source))
    if trigger.slope is not None:
        changes.append(SettingChange(":TRIG:EDGE:SLOP?", ":TRIG:EDGE:SLOP", trigger.slope))
    if trigger.level_v is not None:
        changes.append(SettingChange(f":TRIG:{mode}:LEV?", f":TRIG:{mode}:LEV", str(trigger.level_v)))
    if trigger.coupling is not None:
        changes.append(SettingChange(f":TRIG:{mode}:COUP?", f":TRIG:{mode}:COUP", trigger.coupling))
    return changes


def _channel_changes(number: int, channel: ChannelConfig) -> list[SettingChange]:
    prefix = f":CHAN{number}"
    values = (
        ("DISP", channel.display, _bool),
        ("COUP", channel.coupling, str),
        ("PROB", channel.probe, str),
        ("SCAL", channel.scale_v_div, str),
        ("OFFS", channel.offset_v, str),
        ("BWL", channel.bandwidth_limit, _bool),
    )
    return [SettingChange(f"{prefix}:{key}?", f"{prefix}:{key}", convert(value)) for key, value, convert in values if value is not None]


def _equivalent(expected: str, actual: str) -> bool:
    aliases = {
        "NORMAL": "NORMAL",
        "NORM": "NORMAL",
        "PEAKDETECT": "PEAK_DETECT",
        "PEAK": "PEAK_DETECT",
        "SING": "SINGLE",
        "SINGLE": "SINGLE",
        "CHAN1": "CH1",
        "CH1": "CH1",
        "CHAN2": "CH2",
        "CH2": "CH2",
        "ON": "BOOLEAN_ON",
        "1": "BOOLEAN_ON",
        "OFF": "BOOLEAN_OFF",
        "0": "BOOLEAN_OFF",
    }
    left = aliases.get(expected.upper(), expected.upper())
    right = aliases.get(actual.upper().replace(" ", "_"), actual.upper().replace(" ", "_"))
    if left == right:
        return True
    try:
        return abs(float(expected) - float(actual)) <= max(1e-12, abs(float(expected)) * 1e-6)
    except ValueError:
        return False


def _command_value(change: SettingChange, value: str) -> str:
    """Translate abbreviated query responses into accepted DS1000E setters."""
    normalized = value.upper()
    if change.set_prefix.upper().startswith(":TRIG:") and change.set_prefix.upper().endswith(":SWE"):
        return {
            "NORMAL": "NORM",
            "SINGLE": "SING",
        }.get(normalized, value)
    if change.set_prefix.upper().endswith(":SLOP"):
        return {
            "POSITIVE": "POS",
            "NEGATIVE": "NEG",
        }.get(normalized, value)
    alias = {
        "CH1": "CHAN1",
        "CH2": "CHAN2",
    }.get(normalized)
    if alias is not None:
        return alias
    try:
        # Firmware 00.04.02 emits scientific notation in queries but silently
        # ignores the same notation in several setters (notably trigger level).
        decimal = format(float(value), ".12f").rstrip("0").rstrip(".")
        return "0" if decimal in {"", "-0"} else decimal
    except ValueError:
        return value


def _set_and_verify(inst: MessageInstrument, change: SettingChange, expected: str) -> str:
    deadline = time.monotonic() + 4.0
    next_write = 0.0
    while True:
        now = time.monotonic()
        if now >= next_write:
            inst.write(f"{change.set_prefix} {_command_value(change, expected)}")
            next_write = now + 0.5
        actual = query(inst, change.query)
        if _equivalent(expected, actual):
            return actual
        if now >= deadline:
            raise AcquisitionError(
                f"setting verification failed for {change.set_prefix}: requested {expected}, got {actual}"
            )
        time.sleep(0.05)


def _apply(
    inst: MessageInstrument,
    changes: list[SettingChange],
    saved: list[tuple[SettingChange, str]],
) -> None:
    snapshots = [(change, query(inst, change.query)) for change in changes]
    saved.extend(snapshots)
    for change in changes:
        _set_and_verify(inst, change, change.value)


def _restore_priority(change: SettingChange) -> int:
    prefix = change.set_prefix.upper()
    if prefix.startswith(":TRIG:") and prefix.endswith(":SWE"):
        return 0
    if prefix == ":TRIG:MODE":
        return 1
    if prefix.startswith(":TRIG:") and prefix.endswith(":SOUR"):
        return 2
    if prefix.startswith(":TRIG:") and prefix.endswith(":LEV"):
        return 3
    if prefix.startswith(":TRIG:") and any(prefix.endswith(suffix) for suffix in (":SLOP", ":COUP")):
        return 4
    if prefix.startswith(":WAV:"):
        return 5
    if prefix.startswith(":ACQ:"):
        return 6
    return 7


def _restore(inst: MessageInstrument, saved: list[tuple[SettingChange, str]], was_running: bool) -> None:
    failures: list[str] = []
    try:
        mode = query(inst, ":TRIG:MODE?").upper()
        _stop_for_rearm(inst, timeout_s=4.0, single_mode=mode)
        time.sleep(0.5)
    except Exception as exc:
        failures.append(f"pre-restore STOP: {exc}")
    original: dict[str, tuple[SettingChange, str]] = {}
    for change, old in saved:
        original.setdefault(change.query, (change, old))
    ordered = sorted(original.values(), key=lambda item: _restore_priority(item[0]))
    for change, old in ordered:
        try:
            _set_and_verify(inst, change, old)
            # DS1000E firmware can report the new trigger hierarchy value before
            # dependent trigger registers are writable.  A settle window after
            # sweep/mode/source restoration prevents subsequent writes from
            # being silently ignored.
            priority = _restore_priority(change)
            if priority == 2:
                time.sleep(2.5)
            elif priority <= 1:
                time.sleep(1.5)
        except Exception as exc:  # restoration must aggregate every failure
            failures.append(f"{change.set_prefix}: {exc}")
    try:
        inst.write(":RUN" if was_running else ":STOP")
        deadline = time.monotonic() + 1.0
        while True:
            status = query(inst, ":TRIG:STAT?").upper()
            state_matches = status != "STOP" if was_running else status == "STOP"
            if state_matches:
                break
            if time.monotonic() >= deadline:
                expected = "running acquisition" if was_running else "STOP"
                failures.append(f"run state: expected {expected}, got {status}")
                break
            time.sleep(0.05)
    except Exception as exc:
        failures.append(f"run state: {exc}")
    if failures:
        raise RestorationError("; ".join(failures))


def _read_block(inst: MessageInstrument, channel: int, expected_points: int) -> ParsedWaveform:
    old_termination = inst.read_termination
    try:
        inst.read_termination = None
        inst.write(f":WAV:DATA? CHAN{channel}")
        block = inst.read_raw(expected_points + 32)
        return parse_legacy_block(block)
    except AcquisitionError:
        raise
    except Exception as exc:
        raise WaveformDataError(f"USB waveform read failed for CHAN{channel}: {exc}") from exc
    finally:
        inst.read_termination = old_termination


def _read_block_with_recovery(
    inst: MessageInstrument,
    channel: int,
    expected_points: int,
) -> ParsedWaveform:
    try:
        return _read_block(inst, channel, expected_points)
    except WaveformDataError as first_error:
        try:
            inst.clear()
            time.sleep(0.5)
            return _read_block(inst, channel, expected_points)
        except Exception as retry_error:
            raise WaveformDataError(
                f"CHAN{channel} transfer failed, and USBTMC clear/retry failed: "
                f"first={first_error}; retry={retry_error}"
            ) from retry_error


def _stop_for_rearm(
    inst: MessageInstrument,
    timeout_s: float = 1.0,
    single_mode: str | None = None,
    saved: list[tuple[SettingChange, str]] | None = None,
) -> None:
    if single_mode is not None:
        if single_mode not in SUPPORTED_SINGLE_MODES:
            raise AcquisitionError(
                f"trigger mode {single_mode} has no supported SINGLE sweep; use an EDGE profile"
            )
        sweep = SettingChange(
            f":TRIG:{single_mode}:SWE?",
            f":TRIG:{single_mode}:SWE",
            "SING",
        )
        original_sweep = query(inst, sweep.query)
        if not _equivalent("SING", original_sweep):
            if saved is not None:
                saved.append((sweep, original_sweep))
            _set_and_verify(inst, sweep, "SING")
    inst.write(":STOP")
    deadline = time.monotonic() + timeout_s
    while query(inst, ":TRIG:STAT?").upper() != "STOP":
        if time.monotonic() >= deadline:
            raise AcquisitionError("oscilloscope did not enter STOP before arming")
        time.sleep(0.05)


class CaptureSession:
    """Configure once, acquire repeated fresh triggers, and restore once."""

    def __init__(
        self,
        inst: MessageInstrument,
        resource: str,
        idn: str,
        config: AppConfig,
        channels: tuple[int, ...],
        poll_interval_s: float = 0.002,
    ):
        if not channels or any(channel not in (1, 2) for channel in channels):
            raise AcquisitionError("channels must contain 1 and/or 2")
        self.inst = inst
        self.resource = resource
        self.idn = idn
        self.config = config
        self.channels = channels
        self.poll_interval_s = poll_interval_s
        self.saved: list[tuple[SettingChange, str]] = []
        self.was_running = False
        self.mode = ""
        self.configured = False

    def __enter__(self) -> "CaptureSession":
        initial_status = query(self.inst, ":TRIG:STAT?").upper()
        self.was_running = initial_status != "STOP"
        try:
            initial_mode = query(self.inst, ":TRIG:MODE?").upper()
            _stop_for_rearm(self.inst, single_mode=initial_mode, saved=self.saved)
            _apply(self.inst, _profile_changes(self.config), self.saved)
            self.mode = query(self.inst, ":TRIG:MODE?").upper()
            if self.mode not in SUPPORTED_SINGLE_MODES:
                raise AcquisitionError(
                    f"trigger mode {self.mode} has no supported SINGLE sweep; use an EDGE profile"
                )
            runtime = [
                SettingChange(
                    ":ACQ:MEMD?",
                    ":ACQ:MEMD",
                    self.config.acquisition.memory_depth or "LONG",
                ),
                SettingChange(":WAV:POIN:MODE?", ":WAV:POIN:MODE", "RAW"),
                SettingChange(f":TRIG:{self.mode}:SWE?", f":TRIG:{self.mode}:SWE", "SING"),
            ]
            _apply(self.inst, runtime, self.saved)
            time.sleep(0.5)
            self.configured = True
            return self
        except Exception as primary_error:
            try:
                _restore(self.inst, self.saved, self.was_running)
            except RestorationError as restore_error:
                raise RestorationError(
                    f"session setup failed: {primary_error}; restoration failed: {restore_error}"
                ) from restore_error
            raise

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        try:
            _restore(self.inst, self.saved, self.was_running)
        except RestorationError as restore_error:
            if exc is not None:
                raise RestorationError(
                    f"capture failed: {exc}; restoration failed: {restore_error}"
                ) from restore_error
            raise
        self.configured = False
        return False

    def capture(self, trigger_timeout_s: float) -> Capture:
        if not self.configured:
            raise AcquisitionError("capture session is not configured")
        _stop_for_rearm(self.inst, single_mode=self.mode)
        _set_and_verify(
            self.inst,
            SettingChange(f":TRIG:{self.mode}:SWE?", f":TRIG:{self.mode}:SWE", "SING"),
            "SING",
        )
        time.sleep(0.05)
        started = time.monotonic()
        self.inst.write(":RUN")
        armed = False
        while True:
            status = query(self.inst, ":TRIG:STAT?").upper()
            elapsed = time.monotonic() - started
            if not armed:
                if status != "STOP":
                    armed = True
                elif elapsed >= min(2.0, trigger_timeout_s):
                    raise AcquisitionError("oscilloscope never entered an armed state after :RUN")
            elif status == "STOP":
                break
            if elapsed >= trigger_timeout_s:
                raise TriggerTimeoutError(
                    f"no trigger within {trigger_timeout_s:g} seconds; last status={status}"
                )
            time.sleep(self.poll_interval_s)
        trigger_wait = time.monotonic() - started
        # DS1000E firmware reports STOP before the deep-memory buffer is ready.
        time.sleep(0.2)
        sample_rate = float(query(self.inst, ":ACQ:SAMP?"))
        time_scale = float(query(self.inst, ":TIM:SCAL?"))
        time_offset = float(query(self.inst, ":TIM:OFFS?"))
        settings = {
            ":TRIG:MODE?": self.mode,
            f":TRIG:{self.mode}:SOUR?": query(self.inst, f":TRIG:{self.mode}:SOUR?"),
            f":TRIG:{self.mode}:SWE?": query(self.inst, f":TRIG:{self.mode}:SWE?"),
            ":ACQ:MEMD?": query(self.inst, ":ACQ:MEMD?"),
            ":ACQ:TYPE?": query(self.inst, ":ACQ:TYPE?"),
        }
        def optional_measurement(command: str) -> float | None:
            response = query(self.inst, command).strip()
            if response.startswith((">", "<")):
                return None
            return float(response)

        measurements = {
            channel: {
                "frequency_hz": optional_measurement(f":MEAS:FREQ? CHAN{channel}"),
                "vpp_v": optional_measurement(f":MEAS:VPP? CHAN{channel}"),
            }
            for channel in self.channels
        }
        transferred_at = time.monotonic()
        waveforms: dict[int, ChannelWaveform] = {}
        point_count: int | None = None
        for channel in self.channels:
            memory_depth = int(float(query(self.inst, f":CHAN{channel}:MEMD?")))
            scale = float(query(self.inst, f":CHAN{channel}:SCAL?"))
            offset = float(query(self.inst, f":CHAN{channel}:OFFS?"))
            probe = float(query(self.inst, f":CHAN{channel}:PROB?"))
            parsed = _read_block_with_recovery(self.inst, channel, memory_depth)
            if parsed.raw.size == 600 and memory_depth > 600:
                time.sleep(0.5)
                parsed = _read_block_with_recovery(self.inst, channel, memory_depth)
            if parsed.raw.size != memory_depth:
                raise WaveformDataError(
                    f"CHAN{channel} payload has {parsed.raw.size} points, instrument reports {memory_depth}"
                )
            if point_count is None:
                point_count = parsed.raw.size
            elif point_count != parsed.raw.size:
                raise WaveformDataError("selected channels returned different point counts")
            waveforms[channel] = ChannelWaveform(
                channel=channel,
                header=parsed.header,
                raw=parsed.raw,
                voltage_v=voltage_axis(parsed.raw, scale, offset),
                scale_v_div=scale,
                offset_v=offset,
                probe=probe,
                memory_depth=memory_depth,
            )
        assert point_count is not None
        return Capture(
            captured_at_utc=datetime.now(timezone.utc).isoformat(),
            idn=self.idn,
            resource=self.resource,
            sample_rate_hz=sample_rate,
            timebase_scale_s_div=time_scale,
            timebase_offset_s=time_offset,
            time_s=time_axis(point_count, sample_rate, time_offset),
            channels=waveforms,
            trigger_wait_s=trigger_wait,
            transfer_s=time.monotonic() - transferred_at,
            settings=settings,
            measurements=measurements,
        )


def capture_once(
    inst: MessageInstrument,
    resource: str,
    idn: str,
    config: AppConfig,
    channels: tuple[int, ...],
    trigger_timeout_s: float,
    poll_interval_s: float = 0.002,
) -> Capture:
    with CaptureSession(inst, resource, idn, config, channels, poll_interval_s) as session:
        return session.capture(trigger_timeout_s)
