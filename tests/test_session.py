from __future__ import annotations

import numpy as np
import pytest

from rigol_tool.config import QualificationConfig
from rigol_tool.instrument import Capture, ChannelWaveform
from rigol_tool.session import ContactGate, assess_capture, assess_channels


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


def dual_pulse_capture(ch2_amplitude_v: float) -> Capture:
    capture = pulse_capture()
    ch1 = capture.channels[1]
    ch2_voltage = np.where(ch1.voltage_v > 0, ch2_amplitude_v, 0.0)
    ch2_raw = np.clip(125 - ch2_voltage / 0.04, 0, 255).astype(np.uint8)
    ch2 = ChannelWaveform(2, b"#40000", ch2_raw, ch2_voltage, 1.0, 0.0, 1.0, ch2_raw.size)
    capture.channels[2] = ch2
    capture.measurements[2] = {"frequency_hz": 1000.0, "vpp_v": ch2_amplitude_v}
    return capture


def mixed_capture(static_level_v: float, static_vpp_v: float = 0.0) -> Capture:
    capture = pulse_capture()
    ch1 = capture.channels[1]
    alternating = np.where(np.arange(ch1.raw.size) % 2, 0.5, -0.5)
    ch2_voltage = np.full(ch1.raw.size, static_level_v) + alternating * static_vpp_v
    ch2_raw = np.clip(125 - ch2_voltage / 0.04, 0, 255).astype(np.uint8)
    capture.channels[2] = ChannelWaveform(
        2,
        b"#40000",
        ch2_raw,
        ch2_voltage,
        1.0,
        0.0,
        1.0,
        ch2_raw.size,
    )
    capture.measurements[2] = {"frequency_hz": None, "vpp_v": static_vpp_v}
    return capture


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


def test_dual_qualification_requires_both_probe_signals() -> None:
    result = assess_channels(
        dual_pulse_capture(ch2_amplitude_v=0.1),
        {
            1: QualificationConfig(nominal_frequency_hz=1000, min_vpp_v=2),
            2: QualificationConfig(nominal_frequency_hz=1000, min_vpp_v=2),
        },
    )

    assert result.channels[1].accepted
    assert not result.channels[2].accepted
    assert not result.accepted


@pytest.mark.parametrize(
    ("level_v", "window_index"),
    [(0.01, 0), (2.8, 1)],
)
def test_static_qualification_accepts_either_declared_window(
    level_v: float,
    window_index: int,
) -> None:
    result = assess_capture(
        mixed_capture(level_v),
        2,
        QualificationConfig(
            mode="STATIC",
            allowed_level_windows_v=((-0.05, 0.08), (2.6, 3.1)),
            max_vpp_v=0.1,
        ),
    )

    assert result.accepted
    assert result.mode == "static"
    assert result.metrics["matched_window_index"] == window_index
    assert result.metrics["transitions_verified"] is False


def test_static_qualification_rejects_intermediate_level_and_excess_noise() -> None:
    qualification = QualificationConfig(
        mode="STATIC",
        allowed_level_windows_v=((-0.05, 0.08), (2.6, 3.1)),
        max_vpp_v=0.1,
    )

    intermediate = assess_capture(mixed_capture(1.5), 2, qualification)
    noisy = assess_capture(mixed_capture(2.8, static_vpp_v=0.4), 2, qualification)

    assert "static_level_outside_allowed_windows" in intermediate.reasons
    assert "vpp_above_maximum" in noisy.reasons


def test_mixed_qualification_requires_pulse_and_static_channels() -> None:
    result = assess_channels(
        mixed_capture(2.8),
        {
            1: QualificationConfig(
                nominal_frequency_hz=1000,
                min_vpp_v=2,
                max_vpp_v=4,
            ),
            2: QualificationConfig(
                mode="STATIC",
                allowed_level_windows_v=((-0.05, 0.08), (2.6, 3.1)),
                max_vpp_v=0.1,
            ),
        },
    )

    assert result.accepted
    assert result.channels[1].mode == "pulse"
    assert result.channels[2].mode == "static"
