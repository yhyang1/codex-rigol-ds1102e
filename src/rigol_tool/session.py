from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .analysis import analyze_pulse_waveform
from .config import QualificationConfig
from .instrument import Capture


@dataclass(frozen=True)
class QualificationResult:
    accepted: bool
    reasons: tuple[str, ...]
    metrics: dict[str, float | int | None]
    reference_frequency_hz: float | None


@dataclass(frozen=True)
class GateTransition:
    state: str
    promoted: tuple[Any, ...]
    epoch: int
    candidate_count: int


class ContactGate:
    def __init__(self, consecutive_frames: int):
        if consecutive_frames <= 0:
            raise ValueError("consecutive_frames must be positive")
        self.consecutive_frames = consecutive_frames
        self.candidates: list[Any] = []
        self.qualified = False
        self.epoch = 0

    def observe(self, frame: Any, accepted: bool) -> GateTransition:
        if not accepted:
            had_contact = self.qualified or bool(self.candidates)
            self.qualified = False
            self.candidates.clear()
            return GateTransition(
                state="contact_lost" if had_contact else "rejected",
                promoted=(),
                epoch=self.epoch,
                candidate_count=0,
            )
        if self.qualified:
            return GateTransition("accepted", (frame,), self.epoch, 0)
        self.candidates.append(frame)
        if len(self.candidates) < self.consecutive_frames:
            return GateTransition("candidate", (), self.epoch, len(self.candidates))
        self.epoch += 1
        self.qualified = True
        promoted = tuple(self.candidates)
        self.candidates.clear()
        return GateTransition("contact_qualified", promoted, self.epoch, 0)


def _estimate_frequency(time_s: np.ndarray, voltage_v: np.ndarray) -> float | None:
    low = float(np.percentile(voltage_v, 20))
    high = float(np.percentile(voltage_v, 95))
    amplitude = high - low
    if amplitude <= 0:
        return None
    rising = low + 0.65 * amplitude
    falling = low + 0.35 * amplitude
    in_pulse = float(voltage_v[0]) >= rising
    edges: list[float] = []
    for index in range(1, voltage_v.size):
        previous = float(voltage_v[index - 1])
        current = float(voltage_v[index])
        if not in_pulse and previous < rising <= current:
            fraction = 0.0 if current == previous else (rising - previous) / (current - previous)
            edges.append(float(time_s[index - 1] + fraction * (time_s[index] - time_s[index - 1])))
            in_pulse = True
        elif in_pulse and previous > falling >= current:
            in_pulse = False
    if len(edges) < 3:
        return None
    periods = np.diff(np.asarray(edges, dtype=np.float64))
    periods = periods[periods > 0]
    if not periods.size:
        return None
    median = float(np.median(periods))
    return 1.0 / median if median > 0 else None


def assess_capture(
    capture: Capture,
    channel: int,
    qualification: QualificationConfig,
    provisional_frequency_hz: float | None = None,
) -> QualificationResult:
    waveform = capture.channels[channel]
    voltage = waveform.voltage_v
    vpp = float(np.max(voltage) - np.min(voltage))
    minimum_vpp = qualification.min_vpp_v
    if minimum_vpp is None:
        minimum_vpp = 0.5 * waveform.scale_v_div
    reference = qualification.nominal_frequency_hz or provisional_frequency_hz
    scope_frequency = capture.measurements[channel].get("frequency_hz")
    if reference is None and scope_frequency is not None and np.isfinite(scope_frequency):
        if 0 < scope_frequency < 1e30:
            reference = float(scope_frequency)
    if reference is None:
        reference = _estimate_frequency(capture.time_s, voltage)

    reasons: list[str] = []
    if vpp < minimum_vpp:
        reasons.append("vpp_below_minimum")
    if qualification.max_vpp_v is not None and vpp > qualification.max_vpp_v:
        reasons.append("vpp_above_maximum")
    if reference is None:
        reasons.append("frequency_not_estimable")
        return QualificationResult(
            False,
            tuple(reasons),
            {"vpp_v": vpp, "frequency_hz": None, "complete_pulses": 0, "period_cv_percent": None},
            None,
        )

    analysis = analyze_pulse_waveform(capture.time_s, voltage, reference).values
    complete_pulses = len(analysis["pulse_widths_s"])
    mean_period = analysis["period_mean_s"]
    std_period = analysis["period_std_s"]
    period_cv = None
    if mean_period is not None and std_period is not None and mean_period > 0:
        period_cv = float(std_period / mean_period * 100.0)
    measured_frequency = analysis["frequency_hz"]
    if complete_pulses < qualification.min_complete_pulses:
        reasons.append("too_few_complete_pulses")
    if period_cv is None or period_cv > qualification.max_period_cv_percent:
        reasons.append("period_variation_too_high")
    if measured_frequency is None:
        reasons.append("frequency_not_measurable")
    else:
        tolerance = qualification.frequency_tolerance_percent if qualification.nominal_frequency_hz else 2.0
        error_percent = abs(measured_frequency - reference) / reference * 100.0
        if error_percent > tolerance:
            reasons.append("frequency_out_of_range")
    return QualificationResult(
        accepted=not reasons,
        reasons=tuple(reasons),
        metrics={
            "vpp_v": vpp,
            "frequency_hz": measured_frequency,
            "complete_pulses": complete_pulses,
            "period_cv_percent": period_cv,
        },
        reference_frequency_hz=reference,
    )
