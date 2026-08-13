from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import numpy as np

from .errors import ArtifactError, ConfigurationError
from .verify import verify_artifacts


@dataclass(frozen=True)
class PulseEdges:
    rising_s: np.ndarray
    falling_s: np.ndarray
    low_v: float
    high_v: float
    rising_threshold_v: float
    falling_threshold_v: float


def _crossing(t0: float, t1: float, y0: float, y1: float, level: float) -> float:
    if y1 == y0:
        return t1
    return t0 + (level - y0) * (t1 - t0) / (y1 - y0)


def detect_pulse_edges(time_s: np.ndarray, voltage_v: np.ndarray) -> PulseEdges:
    if time_s.ndim != 1 or voltage_v.ndim != 1 or time_s.size != voltage_v.size:
        raise ArtifactError("time and voltage arrays must be equal-length one-dimensional arrays")
    if time_s.size < 3:
        raise ArtifactError("waveform must contain at least three samples")
    if not np.all(np.isfinite(time_s)) or not np.all(np.isfinite(voltage_v)):
        raise ArtifactError("waveform contains non-finite values")
    if not np.all(np.diff(time_s) > 0):
        raise ArtifactError("time axis must be strictly increasing")

    low_v = float(np.percentile(voltage_v, 5))
    high_tail_count = max(8, int(np.ceil(voltage_v.size * 0.001)))
    high_v = float(np.median(np.partition(voltage_v, -high_tail_count)[-high_tail_count:]))
    amplitude_v = high_v - low_v
    if amplitude_v <= 0.0:
        raise ArtifactError("waveform has no measurable amplitude")
    rising_level = low_v + 0.65 * amplitude_v
    falling_level = low_v + 0.35 * amplitude_v

    rising: list[float] = []
    falling: list[float] = []
    in_pulse = float(voltage_v[0]) >= rising_level
    active_rise: float | None = None
    for index in range(1, time_s.size):
        t0 = float(time_s[index - 1])
        t1 = float(time_s[index])
        y0 = float(voltage_v[index - 1])
        y1 = float(voltage_v[index])
        if not in_pulse and y0 < rising_level <= y1:
            active_rise = _crossing(t0, t1, y0, y1, rising_level)
            in_pulse = True
        elif in_pulse and y0 > falling_level >= y1:
            edge = _crossing(t0, t1, y0, y1, falling_level)
            if active_rise is not None and edge > active_rise:
                rising.append(active_rise)
                falling.append(edge)
            active_rise = None
            in_pulse = False

    return PulseEdges(
        rising_s=np.asarray(rising, dtype=np.float64),
        falling_s=np.asarray(falling, dtype=np.float64),
        low_v=low_v,
        high_v=high_v,
        rising_threshold_v=rising_level,
        falling_threshold_v=falling_level,
    )


def _statistics(values: list[float], scale: float = 1.0) -> dict[str, float | int | None]:
    data = np.asarray(values, dtype=np.float64) * scale
    return {
        "count": int(data.size),
        "mean": float(np.mean(data)) if data.size else None,
        "std": float(np.std(data)) if data.size else None,
        "min": float(np.min(data)) if data.size else None,
        "p50": float(np.percentile(data, 50)) if data.size else None,
        "p95": float(np.percentile(data, 95)) if data.size else None,
        "max": float(np.max(data)) if data.size else None,
    }


def analyze_paired_waveforms(
    time_s: np.ndarray,
    trigger_v: np.ndarray,
    strobe_v: np.ndarray,
) -> dict[str, Any]:
    trigger = detect_pulse_edges(time_s, trigger_v)
    strobe = detect_pulse_edges(time_s, strobe_v)
    trigger_periods = np.diff(trigger.rising_s).tolist()
    trigger_widths = (trigger.falling_s - trigger.rising_s).tolist()
    delays: list[float] = []
    strobe_widths: list[float] = []
    pair_rows: list[dict[str, Any]] = []
    missing_strobes = 0
    extra_strobes = 0
    used_strobes: set[int] = set()

    # Only intervals closed by the next trigger are eligible. Pulses outside
    # that interval may be truncated by the downloaded waveform boundary.
    for trigger_index in range(max(0, trigger.rising_s.size - 1)):
        start = float(trigger.rising_s[trigger_index])
        end = float(trigger.rising_s[trigger_index + 1])
        candidates = [
            index
            for index, rise in enumerate(strobe.rising_s)
            if start <= float(rise) < end and float(strobe.falling_s[index]) < end
        ]
        row: dict[str, Any] = {
            "trigger_index": trigger_index,
            "trigger_rise_s": start,
            "next_trigger_rise_s": end,
            "strobe_candidate_count": len(candidates),
        }
        if not candidates:
            missing_strobes += 1
            row["status"] = "missing_strobe"
        elif len(candidates) > 1:
            extra_strobes += len(candidates) - 1
            row["status"] = "extra_strobe"
            used_strobes.update(candidates)
        else:
            strobe_index = candidates[0]
            used_strobes.add(strobe_index)
            delay = float(strobe.rising_s[strobe_index]) - start
            width = float(strobe.falling_s[strobe_index] - strobe.rising_s[strobe_index])
            delays.append(delay)
            strobe_widths.append(width)
            row.update({
                "status": "paired",
                "strobe_index": strobe_index,
                "strobe_rise_s": float(strobe.rising_s[strobe_index]),
                "strobe_fall_s": float(strobe.falling_s[strobe_index]),
                "delay_s": delay,
                "strobe_width_s": width,
            })
        pair_rows.append(row)

    interval_start = float(trigger.rising_s[0]) if trigger.rising_s.size > 1 else None
    interval_end = float(trigger.rising_s[-1]) if trigger.rising_s.size > 1 else None
    unpaired_in_complete_intervals = 0
    if interval_start is not None and interval_end is not None:
        unpaired_in_complete_intervals = sum(
            interval_start <= float(rise) < interval_end and index not in used_strobes
            for index, rise in enumerate(strobe.rising_s)
        )

    sample_interval_s = float(np.median(np.diff(time_s)))
    return {
        "algorithm": "hysteretic-paired-pulses-v1",
        "sample_count": int(time_s.size),
        "sample_interval_s": sample_interval_s,
        "trigger": {
            "levels": {
                "low_v": trigger.low_v,
                "high_v": trigger.high_v,
                "rising_threshold_v": trigger.rising_threshold_v,
                "falling_threshold_v": trigger.falling_threshold_v,
            },
            "rising_edges_s": trigger.rising_s.tolist(),
            "falling_edges_s": trigger.falling_s.tolist(),
            "period_us": _statistics(trigger_periods, 1e6),
            "high_width_us": _statistics(trigger_widths, 1e6),
        },
        "strobe": {
            "levels": {
                "low_v": strobe.low_v,
                "high_v": strobe.high_v,
                "rising_threshold_v": strobe.rising_threshold_v,
                "falling_threshold_v": strobe.falling_threshold_v,
            },
            "rising_edges_s": strobe.rising_s.tolist(),
            "falling_edges_s": strobe.falling_s.tolist(),
        },
        "pairing": {
            "complete_trigger_intervals": max(0, int(trigger.rising_s.size) - 1),
            "paired_count": len(delays),
            "missing_strobes": missing_strobes,
            "extra_strobes": extra_strobes + unpaired_in_complete_intervals,
            "trigger_to_strobe_delay_us": _statistics(delays, 1e6),
            "strobe_high_width_us": _statistics(strobe_widths, 1e6),
            "rows": pair_rows,
        },
    }


def _load_expectations(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"cannot read expectations {path}: {exc}") from exc
    required = {
        "trigger_period_us", "trigger_high_us", "strobe_delay_min_us",
        "strobe_delay_max_us", "strobe_width_min_us", "strobe_width_max_us",
    }
    missing = required - set(value)
    if missing:
        raise ConfigurationError(f"expectations missing keys: {sorted(missing)}")
    return value


def _gate_frames(
    frames: list[dict[str, Any]], expectations: dict[str, Any] | None,
) -> dict[str, Any]:
    findings: list[str] = []
    total_pairs = sum(frame["analysis"]["pairing"]["paired_count"] for frame in frames)
    missing = sum(frame["analysis"]["pairing"]["missing_strobes"] for frame in frames)
    extra = sum(frame["analysis"]["pairing"]["extra_strobes"] for frame in frames)
    if missing:
        findings.append(f"missing_strobes={missing}")
    if extra:
        findings.append(f"extra_strobes={extra}")
    if expectations is None:
        return {
            "status": "not_evaluated_no_expectations",
            "pass": None,
            "paired_count": total_pairs,
            "missing_strobes": missing,
            "extra_strobes": extra,
            "findings": findings,
        }

    required_captures = int(expectations.get("required_capture_count", 1))
    minimum_pairs = int(expectations.get("minimum_paired_pulses", required_captures))
    if len(frames) < required_captures:
        findings.append(f"capture_count={len(frames)}<{required_captures}")
    if total_pairs < minimum_pairs:
        findings.append(f"paired_count={total_pairs}<{minimum_pairs}")

    maximum_sample_interval_us = max(
        float(frame["analysis"]["sample_interval_s"]) * 1e6 for frame in frames
    )
    tolerance_us = max(
        float(expectations.get("timing_tolerance_us", 10.0)),
        5.0 * maximum_sample_interval_us,
    )

    trigger_periods = [
        (b - a) * 1e6
        for frame in frames
        for a, b in zip(
            frame["analysis"]["trigger"]["rising_edges_s"],
            frame["analysis"]["trigger"]["rising_edges_s"][1:],
        )
    ]
    trigger_widths = [
        (fall - rise) * 1e6
        for frame in frames
        for rise, fall in zip(
            frame["analysis"]["trigger"]["rising_edges_s"],
            frame["analysis"]["trigger"]["falling_edges_s"],
        )
    ]
    delays = [
        float(row["delay_s"]) * 1e6
        for frame in frames
        for row in frame["analysis"]["pairing"]["rows"]
        if row["status"] == "paired"
    ]
    strobe_widths = [
        float(row["strobe_width_s"]) * 1e6
        for frame in frames
        for row in frame["analysis"]["pairing"]["rows"]
        if row["status"] == "paired"
    ]

    def require_close(name: str, values: list[float], expected: float) -> None:
        bad = [value for value in values if abs(value - expected) > tolerance_us]
        if not values:
            findings.append(f"{name}=missing")
        elif bad:
            findings.append(f"{name}_outside_tolerance={len(bad)}/{len(values)}")

    def require_range(name: str, values: list[float], low: float, high: float) -> None:
        bad = [value for value in values if value < low - tolerance_us or value > high + tolerance_us]
        if not values:
            findings.append(f"{name}=missing")
        elif bad:
            findings.append(f"{name}_outside_range={len(bad)}/{len(values)}")

    require_close("trigger_period_us", trigger_periods, float(expectations["trigger_period_us"]))
    require_close("trigger_high_us", trigger_widths, float(expectations["trigger_high_us"]))
    require_range(
        "strobe_delay_us", delays,
        float(expectations["strobe_delay_min_us"]),
        float(expectations["strobe_delay_max_us"]),
    )
    require_range(
        "strobe_width_us", strobe_widths,
        float(expectations["strobe_width_min_us"]),
        float(expectations["strobe_width_max_us"]),
    )

    low_max_v = float(expectations.get("logic_low_max_v", 0.8))
    high_min_v = float(expectations.get("logic_high_min_v", 2.0))
    for channel in ("trigger", "strobe"):
        bad_levels = sum(
            frame["analysis"][channel]["levels"]["low_v"] > low_max_v
            or frame["analysis"][channel]["levels"]["high_v"] < high_min_v
            for frame in frames
        )
        if bad_levels:
            findings.append(f"{channel}_logic_level_failures={bad_levels}/{len(frames)}")

    return {
        "status": "pass" if not findings else "fail",
        "pass": not findings,
        "capture_count": len(frames),
        "paired_count": total_pairs,
        "missing_strobes": missing,
        "extra_strobes": extra,
        "effective_timing_tolerance_us": tolerance_us,
        "maximum_sample_interval_us": maximum_sample_interval_us,
        "findings": findings,
    }


def analyze_paired_series(
    root: Path,
    trigger_channel: int,
    strobe_channel: int,
    expectations_path: Path | None = None,
) -> Path:
    if trigger_channel == strobe_channel:
        raise ConfigurationError("trigger and strobe channels must differ")
    verification = verify_artifacts(root)
    if not verification["valid"]:
        raise ArtifactError("artifact verification failed before paired analysis")
    captures = sorted(
        path for path in root.iterdir()
        if path.is_dir() and (path / "waveform.npz").is_file()
    )
    if not captures:
        raise ArtifactError(f"no capture directories under {root}")

    frames: list[dict[str, Any]] = []
    for capture in captures:
        metadata = json.loads((capture / "metadata.json").read_text(encoding="utf-8"))
        with np.load(capture / "waveform.npz", allow_pickle=False) as data:
            trigger_key = f"ch{trigger_channel}_voltage_v"
            strobe_key = f"ch{strobe_channel}_voltage_v"
            if trigger_key not in data or strobe_key not in data:
                raise ArtifactError(
                    f"capture {capture.name} must contain CH{trigger_channel} and CH{strobe_channel}"
                )
            analysis = analyze_paired_waveforms(data["time_s"], data[trigger_key], data[strobe_key])
        frames.append({
            "capture": capture.name,
            "captured_at_utc": metadata["captured_at_utc"],
            "analysis": analysis,
        })

    expectations = _load_expectations(expectations_path)
    started = datetime.fromisoformat(frames[0]["captured_at_utc"])
    ended = datetime.fromisoformat(frames[-1]["captured_at_utc"])
    report = {
        "schema_version": 1,
        "trigger_channel": trigger_channel,
        "strobe_channel": strobe_channel,
        "capture_count": len(frames),
        "elapsed_wall_time_s": (ended - started).total_seconds(),
        "artifact_verification": verification,
        "expectations": expectations,
        "gate": _gate_frames(frames, expectations),
        "frames": frames,
        "limitations": [
            "Timing accuracy is relative to the oscilloscope sampling timebase unless externally calibrated.",
            "The analysis proves only the two connected probe points and does not infer an unmeasured channel.",
            "Waveform boundaries are excluded from one-to-one pairing unless a complete next-trigger interval exists.",
        ],
    }
    target = root / "paired-series-analysis.json"
    temporary = root / ".paired-series-analysis.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target
