import numpy as np

from rigol_tool.artifacts import waveform_statistics


def test_frequency_rejects_repeated_crossings_around_each_pulse() -> None:
    sample_rate = 10_000.0
    time_s = np.arange(5000) / sample_rate
    voltage_v = np.zeros(5000)
    for start in (500, 1500, 2500, 3500, 4500):
        voltage_v[start] = 10
        voltage_v[start + 2] = 10
    result = waveform_statistics(time_s, voltage_v, reference_frequency_hz=10.0)
    assert result["frequency_hz"] == 10.0
