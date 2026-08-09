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
    try:
        with np.load(waveform_path, allow_pickle=False) as data:
            if "time_s" not in data:
                errors.append("waveform.npz missing time_s")
            else:
                point_count = int(metadata.get("point_count", -1))
                if data["time_s"].size != point_count:
                    errors.append("time_s length differs from metadata point_count")
            channels = metadata.get("channels", {})
            if not isinstance(channels, dict) or not channels:
                errors.append("metadata has no channels")
            else:
                for channel in channels:
                    if f"ch{channel}_voltage_v" not in data or f"ch{channel}_raw_u8" not in data:
                        errors.append(f"waveform.npz missing CH{channel} arrays")
    except Exception as exc:
        errors.append(f"cannot load waveform.npz: {exc}")
    return {"path": str(path), "valid": not errors, "errors": errors, "sha256": actual}


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
    events_path = path / "events.jsonl"
    if events_path.is_file():
        for line_number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                record = json.loads(line)
                event_counts[str(record["event"])] += 1
                if record["event"] in {"session_complete", "session_cancelled", "session_deadline"}:
                    terminal_events.append(record)
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                event_errors.append(f"events.jsonl line {line_number}: {exc}")
    if event_counts["session_started"]:
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
