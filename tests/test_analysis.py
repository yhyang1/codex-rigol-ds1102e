import numpy as np
import pytest

from rigol_tool.analysis import analyze_pulse_waveform


def pulse_train(missing_index: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    sample_rate = 100_000.0
    time_s = np.arange(10_000) / sample_rate - 0.05
    voltage_v = np.zeros_like(time_s)
    for index, start in enumerate(range(0, 10_000, 1000)):
        if index == missing_index:
            continue
        voltage_v[start : start + 10] = 10.0
    return time_s, voltage_v


def test_pulse_frequency_and_phase() -> None:
    time_s, voltage_v = pulse_train()
    result = analyze_pulse_waveform(time_s, voltage_v, 100.0).values
    assert result["frequency_hz"] == pytest.approx(100.0)
    assert result["period_std_s"] < 1e-12
    assert result["glitches"] == {"missing_cycles": 0, "extra_pulses": 0, "peak_outliers": 0}


def test_missing_pulse_is_reported() -> None:
    time_s, voltage_v = pulse_train(missing_index=4)
    result = analyze_pulse_waveform(time_s, voltage_v, 100.0).values
    assert result["glitches"]["missing_cycles"] == 1


def test_leading_partial_pulse_is_not_counted_as_a_glitch() -> None:
    time_s, voltage_v = pulse_train()
    result = analyze_pulse_waveform(time_s, voltage_v, 100.0).values
    assert result["boundary_truncation"]["leading_partial_pulse"] is True
    assert result["frequency_hz"] == pytest.approx(100.0)
    assert result["glitches"] == {"missing_cycles": 0, "extra_pulses": 0, "peak_outliers": 0}
