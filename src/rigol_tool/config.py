from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib
from typing import Any

from .errors import ConfigurationError


@dataclass(frozen=True)
class InstrumentConfig:
    serial: str | None = None


@dataclass(frozen=True)
class AcquisitionConfig:
    memory_depth: str | None = None
    type: str | None = None


@dataclass(frozen=True)
class ChannelConfig:
    display: bool | None = None
    coupling: str | None = None
    probe: float | None = None
    scale_v_div: float | None = None
    offset_v: float | None = None
    bandwidth_limit: bool | None = None


@dataclass(frozen=True)
class TimebaseConfig:
    scale_s_div: float | None = None
    offset_s: float | None = None


@dataclass(frozen=True)
class TriggerConfig:
    mode: str | None = None
    source: str | None = None
    slope: str | None = None
    level_v: float | None = None
    coupling: str | None = None


@dataclass(frozen=True)
class QualificationConfig:
    nominal_frequency_hz: float | None = None
    frequency_tolerance_percent: float = 5.0
    min_vpp_v: float | None = None
    max_vpp_v: float | None = None
    min_complete_pulses: int = 3
    max_period_cv_percent: float = 5.0


@dataclass(frozen=True)
class AppConfig:
    instrument: InstrumentConfig = field(default_factory=InstrumentConfig)
    acquisition: AcquisitionConfig = field(default_factory=AcquisitionConfig)
    channels: dict[int, ChannelConfig] = field(default_factory=dict)
    timebase: TimebaseConfig = field(default_factory=TimebaseConfig)
    trigger: TriggerConfig = field(default_factory=TriggerConfig)
    qualification: QualificationConfig = field(default_factory=QualificationConfig)


def _only_keys(section: str, value: dict[str, Any], allowed: set[str]) -> None:
    extra = set(value) - allowed
    if extra:
        raise ConfigurationError(f"unknown keys in [{section}]: {sorted(extra)}")


def _choice(name: str, value: str | None, choices: set[str]) -> str | None:
    if value is None:
        return None
    normalized = value.upper()
    if normalized not in choices:
        raise ConfigurationError(f"{name} must be one of {sorted(choices)}")
    return normalized


def _positive(name: str, value: float | None) -> float | None:
    if value is not None and value <= 0:
        raise ConfigurationError(f"{name} must be positive")
    return value


def _channel(section: str, raw: dict[str, Any]) -> ChannelConfig:
    _only_keys(section, raw, {"display", "coupling", "probe", "scale_v_div", "offset_v", "bandwidth_limit"})
    coupling = _choice(f"{section}.coupling", raw.get("coupling"), {"AC", "DC", "GND"})
    probe = raw.get("probe")
    if probe is not None and float(probe) not in {1, 5, 10, 50, 100, 500, 1000}:
        raise ConfigurationError(f"{section}.probe is not supported by DS1102E")
    return ChannelConfig(
        display=raw.get("display"),
        coupling=coupling,
        probe=float(probe) if probe is not None else None,
        scale_v_div=_positive(f"{section}.scale_v_div", raw.get("scale_v_div")),
        offset_v=raw.get("offset_v"),
        bandwidth_limit=raw.get("bandwidth_limit"),
    )


def load_config(path: Path | None) -> AppConfig:
    if path is None:
        return AppConfig()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"cannot read config {path}: {exc}") from exc
    _only_keys(
        "root",
        raw,
        {"instrument", "acquisition", "channel1", "channel2", "timebase", "trigger", "qualification"},
    )
    instrument = raw.get("instrument", {})
    acquisition = raw.get("acquisition", {})
    timebase = raw.get("timebase", {})
    trigger = raw.get("trigger", {})
    qualification = raw.get("qualification", {})
    _only_keys("instrument", instrument, {"serial"})
    _only_keys("acquisition", acquisition, {"memory_depth", "type"})
    _only_keys("timebase", timebase, {"scale_s_div", "offset_s"})
    _only_keys("trigger", trigger, {"mode", "source", "slope", "level_v", "coupling"})
    _only_keys(
        "qualification",
        qualification,
        {
            "nominal_frequency_hz",
            "frequency_tolerance_percent",
            "min_vpp_v",
            "max_vpp_v",
            "min_complete_pulses",
            "max_period_cv_percent",
        },
    )
    channels = {
        index: _channel(f"channel{index}", raw[f"channel{index}"])
        for index in (1, 2)
        if f"channel{index}" in raw
    }
    source = _choice("trigger.source", trigger.get("source"), {"CHAN1", "CHAN2", "EXT", "ACLINE"})
    mode = _choice("trigger.mode", trigger.get("mode"), {"EDGE"})
    min_vpp = qualification.get("min_vpp_v")
    max_vpp = qualification.get("max_vpp_v")
    if min_vpp is not None and float(min_vpp) < 0:
        raise ConfigurationError("qualification.min_vpp_v must be non-negative")
    if max_vpp is not None and float(max_vpp) <= 0:
        raise ConfigurationError("qualification.max_vpp_v must be positive")
    if min_vpp is not None and max_vpp is not None and float(min_vpp) >= float(max_vpp):
        raise ConfigurationError("qualification.min_vpp_v must be less than max_vpp_v")
    min_pulses = int(qualification.get("min_complete_pulses", 3))
    if min_pulses < 2:
        raise ConfigurationError("qualification.min_complete_pulses must be at least 2")
    return AppConfig(
        instrument=InstrumentConfig(serial=instrument.get("serial")),
        acquisition=AcquisitionConfig(
            memory_depth=_choice("acquisition.memory_depth", acquisition.get("memory_depth"), {"LONG", "NORMAL"}),
            type=_choice("acquisition.type", acquisition.get("type"), {"NORMAL", "AVERAGE", "PEAKDETECT"}),
        ),
        channels=channels,
        timebase=TimebaseConfig(
            scale_s_div=_positive("timebase.scale_s_div", timebase.get("scale_s_div")),
            offset_s=timebase.get("offset_s"),
        ),
        trigger=TriggerConfig(
            mode=mode,
            source=source,
            slope=_choice("trigger.slope", trigger.get("slope"), {"POSITIVE", "NEGATIVE"}),
            level_v=trigger.get("level_v"),
            coupling=_choice("trigger.coupling", trigger.get("coupling"), {"DC", "AC", "HF", "LF"}),
        ),
        qualification=QualificationConfig(
            nominal_frequency_hz=_positive(
                "qualification.nominal_frequency_hz", qualification.get("nominal_frequency_hz")
            ),
            frequency_tolerance_percent=_positive(
                "qualification.frequency_tolerance_percent",
                qualification.get("frequency_tolerance_percent", 5.0),
            ),
            min_vpp_v=float(min_vpp) if min_vpp is not None else None,
            max_vpp_v=float(max_vpp) if max_vpp is not None else None,
            min_complete_pulses=min_pulses,
            max_period_cv_percent=_positive(
                "qualification.max_period_cv_percent",
                qualification.get("max_period_cv_percent", 5.0),
            ),
        ),
    )
