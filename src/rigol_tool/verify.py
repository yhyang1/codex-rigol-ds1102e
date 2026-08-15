from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .errors import ArtifactError


def _verify_capture(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    metadata_path = path / "metadata.json"
    waveform_path = path / "waveform.npz"
    if not metadata_path.is_file():
        errors.append("missing metadata.json")
    if not waveform_path.is_file():
        errors.append("missing waveform.npz")
    if errors:
        return {"path": str(path), "valid": False, "errors": errors}
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"path": str(path), "valid": False, "errors": [f"invalid metadata.json: {exc}"]}
    expected = metadata.get("waveform_npz_sha256")
    actual = hashlib.sha256(waveform_path.read_bytes()).hexdigest()
    if expected != actual:
        errors.append("waveform SHA-256 mismatch")
    verified_channels: list[int] = []
    try:
        with np.load(waveform_path, allow_pickle=False) as data:
            point_count = int(metadata.get("point_count", -1))
            if "time_s" not in data:
                errors.append("waveform.npz missing time_s")
            else:
                time_s = data["time_s"]
                if time_s.ndim != 1 or time_s.size != point_count:
                    errors.append("time_s length differs from metadata point_count")
                elif not np.all(np.isfinite(time_s)) or not np.all(np.diff(time_s) > 0):
                    errors.append("time_s must be finite and strictly increasing")
            channels = metadata.get("channels", {})
            if not isinstance(channels, dict) or not channels:
                errors.append("metadata has no channels")
            else:
                for channel in channels:
                    try:
                        channel_number = int(channel)
                    except (TypeError, ValueError):
                        errors.append(f"invalid metadata channel key: {channel!r}")
                        continue
                    if channel_number not in (1, 2):
                        errors.append(f"unsupported metadata channel: {channel_number}")
                        continue
                    verified_channels.append(channel_number)
                    voltage_key = f"ch{channel}_voltage_v"
                    raw_key = f"ch{channel}_raw_u8"
                    if voltage_key not in data or raw_key not in data:
                        errors.append(f"waveform.npz missing CH{channel} arrays")
                        continue
                    voltage = data[voltage_key]
                    raw = data[raw_key]
                    if voltage.ndim != 1 or voltage.size != point_count:
                        errors.append(f"CH{channel} voltage length differs from metadata point_count")
                    if raw.ndim != 1 or raw.size != point_count:
                        errors.append(f"CH{channel} raw length differs from metadata point_count")
                    if raw.dtype != np.uint8:
                        errors.append(f"CH{channel} raw array is not uint8")
                    channel_metadata = channels[channel]
                    if isinstance(channel_metadata, dict) and "memory_depth" in channel_metadata:
                        if int(channel_metadata["memory_depth"]) != point_count:
                            errors.append(f"CH{channel} memory depth differs from metadata point_count")
                    if int(metadata.get("schema_version", 1)) >= 2:
                        header_key = f"ch{channel}_header_u8"
                        if header_key not in data or data[header_key].dtype != np.uint8:
                            errors.append(f"waveform.npz missing valid CH{channel} header")
            schema_version = int(metadata.get("schema_version", 1))
            if schema_version >= 2:
                acquisition = metadata.get("acquisition")
                if not isinstance(acquisition, dict):
                    errors.append("schema v2 metadata missing acquisition")
                else:
                    selected = acquisition.get("selected_channels")
                    transfer_order = acquisition.get("transfer_order")
                    expected_mode = "dual" if len(verified_channels) == 2 else "single"
                    if selected != verified_channels:
                        errors.append("selected_channels differ from metadata channels")
                    if transfer_order != verified_channels:
                        errors.append("transfer_order differs from metadata channels")
                    if acquisition.get("channel_mode") != expected_mode:
                        errors.append("channel_mode differs from metadata channels")
                    if acquisition.get("sample_alignment") != "simultaneously_sampled_sequentially_downloaded":
                        errors.append("invalid or missing sample_alignment")
                if not (path / "preview.png").is_file():
                    errors.append("schema v2 capture missing preview.png")
    except Exception as exc:
        errors.append(f"cannot load waveform.npz: {exc}")
    return {
        "path": str(path),
        "valid": not errors,
        "errors": errors,
        "sha256": actual,
        "channels": verified_channels,
    }


def verify_artifacts(path: Path) -> dict[str, Any]:
    if (path / "metadata.json").is_file() or (path / "waveform.npz").is_file():
        capture = _verify_capture(path)
        return {"kind": "capture", "valid": capture["valid"], "captures": [capture]}
    if not path.is_dir():
        raise ArtifactError(f"not an artifact path: {path}")
    capture_paths = sorted(item for item in path.iterdir() if item.is_dir() and not item.name.startswith("."))
    captures = [_verify_capture(item) for item in capture_paths if (item / "metadata.json").exists() or (item / "waveform.npz").exists()]
    event_counts: Counter[str] = Counter()
    event_errors: list[str] = []
    terminal_events: list[dict[str, Any]] = []
    session_starts: list[dict[str, Any]] = []
    events_path = path / "events.jsonl"
    if events_path.is_file():
        for line_number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                record = json.loads(line)
                event_counts[str(record["event"])] += 1
                if record["event"] == "session_started":
                    session_starts.append(record)
                if record["event"] in {"session_complete", "session_cancelled", "session_deadline"}:
                    terminal_events.append(record)
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                event_errors.append(f"events.jsonl line {line_number}: {exc}")
    if event_counts["session_started"]:
        if len(session_starts) != 1:
            event_errors.append("session run must contain exactly one session_started event")
        if len(terminal_events) != 1:
            event_errors.append("session run must contain exactly one terminal event")
        else:
            terminal = terminal_events[0]
            if terminal.get("restored") is not True:
                event_errors.append("session terminal event does not confirm restoration")
            if int(terminal.get("accepted", -1)) != len(captures):
                event_errors.append("session accepted count differs from capture artifacts")
            if terminal["event"] == "session_complete" and int(terminal.get("target", -1)) != len(captures):
                event_errors.append("complete session target differs from capture artifacts")
        if len(session_starts) == 1 and "channels" in session_starts[0]:
            selected_channels = session_starts[0]["channels"]
            if not isinstance(selected_channels, list) or not selected_channels:
                event_errors.append("session_started channels must be a non-empty list")
            else:
                for capture in captures:
                    if capture.get("channels") != selected_channels:
                        event_errors.append(
                            f"capture channels differ from session selection: {capture['path']}"
                        )
    elif not captures:
        event_errors.append("no capture artifacts found")
    invalid_captures = sum(not item["valid"] for item in captures)
    valid = invalid_captures == 0 and not event_errors
    return {
        "kind": "run",
        "valid": valid,
        "capture_count": len(captures),
        "invalid_capture_count": invalid_captures,
        "event_counts": dict(sorted(event_counts.items())),
        "event_errors": event_errors,
        "captures": captures,
    }
