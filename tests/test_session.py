from __future__ import annotations

import numpy as np

from rigol_tool.config import QualificationConfig
from rigol_tool.instrument import Capture, ChannelWaveform
from rigol_tool.session import ContactGate, assess_capture


def pulse_capture(frequency_hz: float = 1000.0, amplitude_v: float = 3.0) -> Capture:
    sample_rate = 1_000_000.0
    time_s = np.arange(10_000, dtype=np.float64) / sample_rate
    phase = np.mod(time_s * frequency_hz, 1.0)
    voltage = np.where(phase < 0.5, amplitude_v, 0.0)
    raw = np.clip(125 - voltage / 0.04, 0, 255).astype(np.uint8)
    waveform = ChannelWaveform(1, b"#40000", raw, voltage, 1.0, 0.0, 1.0, raw.size)
    return Capture(
        captured_at_utc="2026-08-09T00:00:00+00:00",
        idn="Rigol Technologies,DS1102E,SERIAL,FW",
        resource="USB::INSTR",
        sample_rate_hz=sample_rate,
        timebase_scale_s_div=0.001,
        timebase_offset_s=0.0,
        time_s=time_s,
        channels={1: waveform},
        trigger_wait_s=0.1,
        transfer_s=0.2,
        settings={},
        measurements={1: {"frequency_hz": frequency_hz, "vpp_v": amplitude_v}},
    )


def test_contact_gate_requires_consecutive_frames_and_requalifies() -> None:
    gate = ContactGate(3)
    assert gate.observe("a", True).state == "candidate"
    assert gate.observe("bad", False).state == "contact_lost"
    assert gate.observe("b", True).candidate_count == 1
    assert gate.observe("c", True).candidate_count == 2
    qualified = gate.observe("d", True)
    assert qualified.state == "contact_qualified"
    assert qualified.promoted == ("b", "c", "d")
    assert qualified.epoch == 1
    assert gate.observe("e", True).state == "accepted"
    assert gate.observe("lost", False).state == "contact_lost"
    assert gate.observe("f", True).state == "candidate"
    assert gate.observe("g", True).state == "candidate"
    assert gate.observe("h", True).epoch == 2


def test_capture_qualification_accepts_stable_probe_comp_waveform() -> None:
    result = assess_capture(
        pulse_capture(),
        1,
        QualificationConfig(
            nominal_frequency_hz=1000,
            min_vpp_v=2,
            max_vpp_v=4,
            min_complete_pulses=3,
        ),
    )
    assert result.accepted
    assert result.metrics["frequency_hz"] == 1000.0


def test_capture_qualification_rejects_weak_contact() -> None:
    result = assess_capture(
        pulse_capture(amplitude_v=0.1),
        1,
        QualificationConfig(nominal_frequency_hz=1000, min_vpp_v=2),
    )
    assert not result.accepted
    assert "vpp_below_minimum" in result.reasons
