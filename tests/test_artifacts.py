import json

import numpy as np

from rigol_tool.artifacts import waveform_statistics, write_capture
from rigol_tool.instrument import Capture, ChannelWaveform
from rigol_tool.verify import verify_artifacts


def test_frequency_rejects_repeated_crossings_around_each_pulse() -> None:
    sample_rate = 10_000.0
    time_s = np.arange(5000) / sample_rate
    voltage_v = np.zeros(5000)
    for start in (500, 1500, 2500, 3500, 4500):
        voltage_v[start] = 10
        voltage_v[start + 2] = 10
    result = waveform_statistics(time_s, voltage_v, reference_frequency_hz=10.0)
    assert result["frequency_hz"] == 10.0


def test_write_and_verify_schema_v2_dual_capture(tmp_path) -> None:
    time_s = np.arange(8, dtype=np.float64) / 1_000_000
    channels = {}
    measurements = {}
    for number, raw_value in ((1, 125), (2, 150)):
        raw = np.full(time_s.size, raw_value, dtype=np.uint8)
        channels[number] = ChannelWaveform(
            number,
            b"#18",
            raw,
            np.full(time_s.size, float(number)),
            1.0,
            0.0,
            10.0,
            time_s.size,
        )
        measurements[number] = {"frequency_hz": 1000.0, "vpp_v": 3.0}
    capture = Capture(
        captured_at_utc="2026-08-15T00:00:00+00:00",
        idn="Rigol Technologies,DS1102E,SERIAL,FW",
        resource="USB::INSTR",
        sample_rate_hz=1_000_000,
        timebase_scale_s_div=0.001,
        timebase_offset_s=0.0,
        time_s=time_s,
        channels=channels,
        trigger_wait_s=0.1,
        transfer_s=0.2,
        settings={":ACQ:MEMD?": "NORMAL"},
        measurements=measurements,
    )

    path = write_capture(capture, tmp_path, 1)
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    report = verify_artifacts(path)

    assert metadata["schema_version"] == 2
    assert metadata["acquisition"]["selected_channels"] == [1, 2]
    assert metadata["acquisition"]["sample_alignment"] == "simultaneously_sampled_sequentially_downloaded"
    assert report["valid"]
