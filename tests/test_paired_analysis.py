import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from rigol_tool.paired_analysis import analyze_paired_series, analyze_paired_waveforms


def paired_train(*, missing_index: int | None = None, extra_index: int | None = None):
    sample_interval_s = 1e-6
    time_s = np.arange(120_000, dtype=np.float64) * sample_interval_s - 0.06
    trigger_v = np.zeros_like(time_s)
    strobe_v = np.zeros_like(time_s)
    trigger_starts = (5_000, 38_333, 71_666, 104_999)
    for index, start in enumerate(trigger_starts):
        trigger_v[start : start + 100] = 3.3
        if index != missing_index:
            strobe_v[start + 1_264 : start + 1_264 + 9_971] = 3.3
        if index == extra_index:
            strobe_v[start + 15_000 : start + 15_200] = 3.3
    return time_s, trigger_v, strobe_v


def test_paired_trigger_and_strobe_timing() -> None:
    time_s, trigger_v, strobe_v = paired_train()
    result = analyze_paired_waveforms(time_s, trigger_v, strobe_v)

    assert result["pairing"]["paired_count"] == 3
    assert result["pairing"]["missing_strobes"] == 0
    assert result["pairing"]["extra_strobes"] == 0
    assert result["trigger"]["period_us"]["p50"] == pytest.approx(33_333, abs=1)
    assert result["trigger"]["high_width_us"]["p50"] == pytest.approx(100, abs=1)
    assert result["pairing"]["trigger_to_strobe_delay_us"]["p50"] == pytest.approx(1_264, abs=1)
    assert result["pairing"]["strobe_high_width_us"]["p50"] == pytest.approx(9_971, abs=1)


def test_missing_strobe_is_fail_closed() -> None:
    time_s, trigger_v, strobe_v = paired_train(missing_index=1)
    result = analyze_paired_waveforms(time_s, trigger_v, strobe_v)

    assert result["pairing"]["missing_strobes"] == 1
    assert result["pairing"]["paired_count"] == 2


def test_extra_strobe_is_fail_closed() -> None:
    time_s, trigger_v, strobe_v = paired_train(extra_index=1)
    result = analyze_paired_waveforms(time_s, trigger_v, strobe_v)

    assert result["pairing"]["extra_strobes"] == 1


def test_non_monotonic_time_axis_is_rejected() -> None:
    time_s, trigger_v, strobe_v = paired_train()
    time_s[100] = time_s[99]
    with pytest.raises(Exception, match="strictly increasing"):
        analyze_paired_waveforms(time_s, trigger_v, strobe_v)


def test_verified_series_applies_expectation_gate(tmp_path: Path) -> None:
    time_s, trigger_v, strobe_v = paired_train()
    capture = tmp_path / "20260814T000000.000000Z_000001"
    capture.mkdir()
    waveform = capture / "waveform.npz"
    np.savez_compressed(
        waveform,
        time_s=time_s,
        ch1_voltage_v=trigger_v,
        ch1_raw_u8=np.zeros(time_s.size, dtype=np.uint8),
        ch2_voltage_v=strobe_v,
        ch2_raw_u8=np.zeros(time_s.size, dtype=np.uint8),
    )
    digest = hashlib.sha256(waveform.read_bytes()).hexdigest()
    (capture / "metadata.json").write_text(json.dumps({
        "captured_at_utc": "2026-08-14T00:00:00+00:00",
        "point_count": int(time_s.size),
        "channels": {"1": {}, "2": {}},
        "waveform_npz_sha256": digest,
    }), encoding="utf-8")
    (tmp_path / "events.jsonl").write_text("\n".join([
        json.dumps({"event": "session_started"}),
        json.dumps({
            "event": "session_complete", "accepted": 1, "target": 1, "restored": True,
        }),
    ]) + "\n", encoding="utf-8")
    expectations = tmp_path / "expectations.json"
    expectations.write_text(json.dumps({
        "trigger_period_us": 33_333,
        "trigger_high_us": 100,
        "strobe_delay_min_us": 1_264,
        "strobe_delay_max_us": 1_264,
        "strobe_width_min_us": 9_971,
        "strobe_width_max_us": 9_971,
        "required_capture_count": 1,
        "minimum_paired_pulses": 3,
        "timing_tolerance_us": 10,
    }), encoding="utf-8")

    report_path = analyze_paired_series(tmp_path, 1, 2, expectations)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["artifact_verification"]["valid"] is True
    assert report["gate"]["pass"] is True
    assert report["gate"]["paired_count"] == 3

    np.savez_compressed(
        waveform,
        time_s=time_s,
        ch1_voltage_v=strobe_v,
        ch1_raw_u8=np.zeros(time_s.size, dtype=np.uint8),
        ch2_voltage_v=trigger_v,
        ch2_raw_u8=np.zeros(time_s.size, dtype=np.uint8),
    )
    metadata = json.loads((capture / "metadata.json").read_text(encoding="utf-8"))
    metadata["waveform_npz_sha256"] = hashlib.sha256(waveform.read_bytes()).hexdigest()
    (capture / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    reverse_report_path = analyze_paired_series(tmp_path, 2, 1, expectations)
    reverse_report = json.loads(reverse_report_path.read_text(encoding="utf-8"))

    assert reverse_report["trigger_channel"] == 2
    assert reverse_report["strobe_channel"] == 1
    assert reverse_report["gate"]["pass"] is True
