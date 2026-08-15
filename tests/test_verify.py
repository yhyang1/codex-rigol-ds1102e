from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from rigol_tool.verify import verify_artifacts
from rigol_tool.cli import main


def make_capture(root: Path, name: str = "capture", channels: tuple[int, ...] = (1,)) -> Path:
    capture = root / name
    capture.mkdir(parents=True)
    waveform = capture / "waveform.npz"
    arrays = {"time_s": np.arange(4, dtype=float)}
    for channel in channels:
        arrays[f"ch{channel}_voltage_v"] = np.ones(4)
        arrays[f"ch{channel}_raw_u8"] = np.ones(4, dtype=np.uint8)
    np.savez_compressed(waveform, **arrays)
    digest = hashlib.sha256(waveform.read_bytes()).hexdigest()
    (capture / "metadata.json").write_text(
        json.dumps({
            "point_count": 4,
            "channels": {str(channel): {} for channel in channels},
            "waveform_npz_sha256": digest,
        }),
        encoding="utf-8",
    )
    return capture


def test_verify_capture_and_detect_hash_mismatch(tmp_path: Path) -> None:
    capture = make_capture(tmp_path)
    assert verify_artifacts(capture)["valid"]
    with (capture / "waveform.npz").open("ab") as handle:
        handle.write(b"damage")
    report = verify_artifacts(capture)
    assert not report["valid"]
    assert "waveform SHA-256 mismatch" in report["captures"][0]["errors"]


def test_verify_complete_session_counts(tmp_path: Path) -> None:
    make_capture(tmp_path, "20260809T000000.000000Z_000001")
    events = [
        {"event": "session_started"},
        {"event": "capture_accepted"},
        {"event": "session_complete", "accepted": 1, "target": 1, "restored": True},
    ]
    (tmp_path / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )
    report = verify_artifacts(tmp_path)
    assert report["valid"]
    assert report["event_counts"]["capture_accepted"] == 1


def test_verify_cancelled_waiting_session_without_captures(tmp_path: Path) -> None:
    events = [
        {"event": "session_started"},
        {"event": "waiting_contact"},
        {"event": "session_cancelled", "accepted": 0, "target": 10, "restored": True},
    ]
    (tmp_path / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )
    report = verify_artifacts(tmp_path)
    assert report["valid"]
    assert report["capture_count"] == 0


def test_verify_cli_persists_report(tmp_path: Path) -> None:
    capture = make_capture(tmp_path)
    output = tmp_path / "verification.json"
    assert main(["verify", str(capture), "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["valid"] is True


def test_verify_dual_session_requires_both_channels_in_every_capture(tmp_path: Path) -> None:
    make_capture(tmp_path, "20260809T000000.000000Z_000001", channels=(1,))
    events = [
        {"event": "session_started", "channels": [1, 2]},
        {"event": "session_complete", "accepted": 1, "target": 1, "restored": True},
    ]
    (tmp_path / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    report = verify_artifacts(tmp_path)

    assert not report["valid"]
    assert any("capture channels differ" in error for error in report["event_errors"])


def test_verify_rejects_dual_channel_length_mismatch(tmp_path: Path) -> None:
    capture = make_capture(tmp_path, channels=(1, 2))
    waveform = capture / "waveform.npz"
    np.savez_compressed(
        waveform,
        time_s=np.arange(4, dtype=float),
        ch1_voltage_v=np.ones(4),
        ch1_raw_u8=np.ones(4, dtype=np.uint8),
        ch2_voltage_v=np.ones(3),
        ch2_raw_u8=np.ones(3, dtype=np.uint8),
    )
    metadata_path = capture / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["waveform_npz_sha256"] = hashlib.sha256(waveform.read_bytes()).hexdigest()
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    report = verify_artifacts(capture)

    assert not report["valid"]
    assert any("CH2 voltage length" in error for error in report["captures"][0]["errors"])


def test_verify_rejects_non_monotonic_time_axis(tmp_path: Path) -> None:
    capture = make_capture(tmp_path)
    waveform = capture / "waveform.npz"
    np.savez_compressed(
        waveform,
        time_s=np.array([0.0, 1.0, 0.5, 2.0]),
        ch1_voltage_v=np.ones(4),
        ch1_raw_u8=np.ones(4, dtype=np.uint8),
    )
    metadata_path = capture / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["waveform_npz_sha256"] = hashlib.sha256(waveform.read_bytes()).hexdigest()
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    report = verify_artifacts(capture)

    assert not report["valid"]
    assert any("strictly increasing" in error for error in report["captures"][0]["errors"])
