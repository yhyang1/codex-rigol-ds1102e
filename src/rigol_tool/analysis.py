from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import numpy as np

from .errors import ArtifactError, ConfigurationError


@dataclass(frozen=True)
class PulseAnalysis:
    values: dict[str, Any]


def _interpolated_crossing(t0: float, t1: float, y0: float, y1: float, level: float) -> float:
    if y1 == y0:
        return t1
    return t0 + (level - y0) * (t1 - t0) / (y1 - y0)


def analyze_pulse_waveform(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    nominal_frequency_hz: float,
) -> PulseAnalysis:
    if time_s.ndim != 1 or voltage_v.ndim != 1 or time_s.size != voltage_v.size or time_s.size < 3:
        raise ArtifactError("time and voltage arrays must be equal-length one-dimensional arrays")
    if nominal_frequency_hz <= 0:
        raise ConfigurationError("nominal frequency must be positive")
    if not np.all(np.isfinite(time_s)) or not np.all(np.isfinite(voltage_v)):
        raise ArtifactError("waveform contains non-finite values")

    low_level = float(np.percentile(voltage_v, 20))
    high_level = float(np.max(voltage_v))
    amplitude = high_level - low_level
    if amplitude <= 0:
        raise ArtifactError("waveform has no measurable amplitude")
    rising_level = low_level + 0.65 * amplitude
    falling_level = low_level + 0.35 * amplitude
    nominal_period_s = 1.0 / nominal_frequency_hz
    rising_edges: list[float] = []
    pulse_widths: list[float] = []
    pulse_peaks: list[float] = []
    in_pulse = float(voltage_v[0]) >= rising_level
    leading_partial = in_pulse
    current_rise: float | None = None
    active_peak = float(voltage_v[0]) if in_pulse else low_level
    for index in range(1, voltage_v.size):
        previous = float(voltage_v[index - 1])
        current = float(voltage_v[index])
        if not in_pulse and previous < rising_level <= current:
            current_rise = _interpolated_crossing(
                float(time_s[index - 1]), float(time_s[index]), previous, current, rising_level
            )
            active_peak = current
            in_pulse = True
        elif in_pulse:
            active_peak = max(active_peak, current)
            if previous > falling_level >= current:
                falling_edge = _interpolated_crossing(
                    float(time_s[index - 1]), float(time_s[index]), previous, current, falling_level
                )
                if current_rise is not None and falling_edge > current_rise:
                    rising_edges.append(current_rise)
                    pulse_widths.append(falling_edge - current_rise)
                    pulse_peaks.append(active_peak)
                current_rise = None
                in_pulse = False

    trailing_partial = current_rise is not None

    edges = np.asarray(rising_edges, dtype=np.float64)
    periods = np.diff(edges)
    valid_periods = periods[(periods >= 0.75 * nominal_period_s) & (periods <= 1.25 * nominal_period_s)]
    frequency_hz: float | None = None
    period_mean_s: float | None = None
    period_std_s: float | None = None
    period_peak_to_peak_s: float | None = None
    if valid_periods.size:
        period_mean_s = float(np.mean(valid_periods))
        period_std_s = float(np.std(valid_periods))
        period_peak_to_peak_s = float(np.ptp(valid_periods))
        frequency_hz = float(1.0 / np.mean(valid_periods))

    missing_cycles = int(sum(max(0, round(period / nominal_period_s) - 1) for period in periods))
    extra_pulses = int(np.count_nonzero(periods < 0.75 * nominal_period_s))
    widths = np.asarray(pulse_widths, dtype=np.float64)
    peaks = np.asarray(pulse_peaks, dtype=np.float64)

    phase_deg: float | None = None
    if edges.size:
        nearest = float(edges[np.argmin(np.abs(edges))])
        phase_deg = ((nearest * nominal_frequency_hz * 360.0 + 180.0) % 360.0) - 180.0

    peak_outliers = 0
    if peaks.size >= 3:
        median_peak = float(np.median(peaks))
        mad = float(np.median(np.abs(peaks - median_peak)))
        tolerance = max(5.0 * 1.4826 * mad, amplitude / 25.0)
        peak_outliers = int(np.count_nonzero(np.abs(peaks - median_peak) > tolerance))

    values: dict[str, Any] = {
        "algorithm": "hysteretic-pulse-v2",
        "nominal_frequency_hz": nominal_frequency_hz,
        "nominal_period_s": nominal_period_s,
        "sample_count": int(time_s.size),
        "sample_interval_s": float(np.median(np.diff(time_s))),
        "levels": {
            "baseline_v": low_level,
            "peak_v": high_level,
            "rising_threshold_v": rising_level,
            "falling_threshold_v": falling_level,
        },
        "rising_edge_count": int(edges.size),
        "rising_edges_s": edges.tolist(),
        "frequency_hz": frequency_hz,
        "frequency_error_hz": frequency_hz - nominal_frequency_hz if frequency_hz is not None else None,
        "frequency_error_ppm": (
            (frequency_hz - nominal_frequency_hz) / nominal_frequency_hz * 1e6
            if frequency_hz is not None
            else None
        ),
        "period_mean_s": period_mean_s,
        "period_std_s": period_std_s,
        "period_peak_to_peak_s": period_peak_to_peak_s,
        "pulse_width_mean_s": float(np.mean(widths)) if widths.size else None,
        "pulse_width_std_s": float(np.std(widths)) if widths.size else None,
        "pulse_widths_s": widths.tolist(),
        "pulse_peaks_v": peaks.tolist(),
        "boundary_truncation": {
            "leading_partial_pulse": leading_partial,
            "trailing_partial_pulse": trailing_partial,
        },
        "trigger_relative_phase_deg": phase_deg,
        "glitches": {
            "missing_cycles": missing_cycles,
            "extra_pulses": extra_pulses,
            "peak_outliers": peak_outliers,
        },
    }
    return PulseAnalysis(values)


def analyze_capture(capture_dir: Path, channel: int, nominal_frequency_hz: float) -> dict[str, Any]:
    npz_path = capture_dir / "waveform.npz"
    metadata_path = capture_dir / "metadata.json"
    if not npz_path.is_file() or not metadata_path.is_file():
        raise ArtifactError(f"not a capture directory: {capture_dir}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with np.load(npz_path, allow_pickle=False) as data:
        voltage_key = f"ch{channel}_voltage_v"
        if voltage_key not in data:
            raise ArtifactError(f"capture does not contain CH{channel}")
        analysis = analyze_pulse_waveform(data["time_s"], data[voltage_key], nominal_frequency_hz).values
    return {
        "capture": capture_dir.name,
        "captured_at_utc": metadata["captured_at_utc"],
        "scope_measurements": metadata["channels"][str(channel)]["scope_measurements"],
        "analysis": analysis,
    }


def analyze_series(root: Path, channel: int, nominal_frequency_hz: float) -> Path:
    captures = sorted(path for path in root.iterdir() if path.is_dir() and (path / "waveform.npz").is_file())
    if not captures:
        raise ArtifactError(f"no capture directories under {root}")
    frames = [analyze_capture(path, channel, nominal_frequency_hz) for path in captures]
    frequencies = np.asarray(
        [frame["analysis"]["frequency_hz"] for frame in frames if frame["analysis"]["frequency_hz"] is not None],
        dtype=np.float64,
    )
    phases = np.asarray(
        [
            frame["analysis"]["trigger_relative_phase_deg"]
            for frame in frames
            if frame["analysis"]["trigger_relative_phase_deg"] is not None
        ],
        dtype=np.float64,
    )
    started = datetime.fromisoformat(frames[0]["captured_at_utc"])
    ended = datetime.fromisoformat(frames[-1]["captured_at_utc"])
    peaks_by_slot: dict[int, list[float]] = {}
    for frame in frames:
        frame_analysis = frame["analysis"]
        edges = frame_analysis["rising_edges_s"]
        peaks = frame_analysis["pulse_peaks_v"]
        if not edges or not peaks:
            continue
        trigger_index = int(np.argmin(np.abs(np.asarray(edges, dtype=np.float64))))
        for index, peak in enumerate(peaks):
            peaks_by_slot.setdefault(index - trigger_index, []).append(float(peak))
    peak_slots = {
        str(slot): {
            "count": len(values),
            "mean_v": float(np.mean(values)),
            "std_v": float(np.std(values)),
            "min_v": float(np.min(values)),
            "max_v": float(np.max(values)),
        }
        for slot, values in sorted(peaks_by_slot.items())
    }
    report = {
        "schema_version": 1,
        "channel": channel,
        "nominal_frequency_hz": nominal_frequency_hz,
        "capture_count": len(frames),
        "elapsed_wall_time_s": (ended - started).total_seconds(),
        "frequency": {
            "valid_capture_count": int(frequencies.size),
            "mean_hz": float(np.mean(frequencies)) if frequencies.size else None,
            "std_hz": float(np.std(frequencies)) if frequencies.size else None,
            "min_hz": float(np.min(frequencies)) if frequencies.size else None,
            "max_hz": float(np.max(frequencies)) if frequencies.size else None,
            "mean_error_ppm": (
                float((np.mean(frequencies) - nominal_frequency_hz) / nominal_frequency_hz * 1e6)
                if frequencies.size
                else None
            ),
        },
        "trigger_relative_phase": {
            "status": "diagnostic_only_not_a_long_term_phase_measurement",
            "reference": "downloaded RAW buffer origin, not an external time reference",
            "mean_deg": float(np.mean(phases)) if phases.size else None,
            "std_deg": float(np.std(phases)) if phases.size else None,
            "peak_to_peak_deg": float(np.ptp(phases)) if phases.size else None,
        },
        "glitch_totals": {
            key: int(sum(frame["analysis"]["glitches"][key] for frame in frames))
            for key in ("missing_cycles", "extra_pulses", "peak_outliers")
        },
        "boundary_truncation_totals": {
            key: int(sum(bool(frame["analysis"]["boundary_truncation"][key]) for frame in frames))
            for key in ("leading_partial_pulse", "trailing_partial_pulse")
        },
        "pulse_peak_by_trigger_slot": peak_slots,
        "frames": frames,
        "limitations": [
            "Trigger-relative phase is referenced to the downloaded RAW buffer origin and is not absolute source phase.",
            "Single-channel self-triggered captures cannot measure connector end-to-end phase delay.",
            "Frequency accuracy is relative to the oscilloscope sampling timebase unless that timebase is externally calibrated.",
        ],
    }
    target = root / "series-analysis.json"
    temporary = root / ".series-analysis.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target
