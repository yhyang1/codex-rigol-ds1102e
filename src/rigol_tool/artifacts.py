from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np

from .errors import ArtifactError
from .instrument import Capture


SCHEMA_VERSION = 1


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def waveform_statistics(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    reference_frequency_hz: float | None = None,
) -> dict[str, float | None]:
    minimum = float(np.min(voltage_v))
    maximum = float(np.max(voltage_v))
    midpoint = (minimum + maximum) / 2.0
    crossings = np.flatnonzero((voltage_v[:-1] < midpoint) & (voltage_v[1:] >= midpoint)) + 1
    frequency: float | None = None
    if (
        crossings.size
        and reference_frequency_hz is not None
        and np.isfinite(reference_frequency_hz)
        and 0 < reference_frequency_hz < 1e30
    ):
        minimum_separation_s = 0.5 / reference_frequency_hz
        accepted = [int(crossings[0])]
        for crossing in crossings[1:]:
            if time_s[crossing] - time_s[accepted[-1]] >= minimum_separation_s:
                accepted.append(int(crossing))
        crossings = np.asarray(accepted, dtype=np.int64)
    if crossings.size >= 2:
        periods = np.diff(time_s[crossings])
        positive = periods[periods > 0]
        if positive.size:
            frequency = float(1.0 / np.median(positive))
    return {
        "minimum_v": minimum,
        "maximum_v": maximum,
        "vpp_v": maximum - minimum,
        "mean_v": float(np.mean(voltage_v)),
        "frequency_hz": frequency,
    }


def write_event(output: Path, event: str, **fields: Any) -> None:
    output.mkdir(parents=True, exist_ok=True)
    record = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    with (output / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=_json_default, sort_keys=True) + "\n")


def write_capture(
    capture: Capture,
    output: Path,
    sequence: int,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    cache_dir = Path(tempfile.gettempdir()) / "rigol-tool-matplotlib-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(capture.captured_at_utc).strftime("%Y%m%dT%H%M%S.%fZ")
    name = f"{stamp}_{sequence:06d}"
    target = output / name
    if target.exists():
        raise ArtifactError(f"capture target already exists: {target}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{name}.", dir=output))
    try:
        arrays: dict[str, np.ndarray] = {"time_s": capture.time_s}
        for number, waveform in capture.channels.items():
            arrays[f"ch{number}_voltage_v"] = waveform.voltage_v
            arrays[f"ch{number}_raw_u8"] = waveform.raw
            arrays[f"ch{number}_header_u8"] = np.frombuffer(waveform.header, dtype=np.uint8).copy()
        npz_path = temporary / "waveform.npz"
        np.savez_compressed(npz_path, **arrays)
        digest = hashlib.sha256(npz_path.read_bytes()).hexdigest()
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "captured_at_utc": capture.captured_at_utc,
            "instrument": {"idn": capture.idn, "resource": capture.resource},
            "sample_rate_hz": capture.sample_rate_hz,
            "timebase": {"scale_s_div": capture.timebase_scale_s_div, "offset_s": capture.timebase_offset_s},
            "trigger_wait_s": capture.trigger_wait_s,
            "transfer_s": capture.transfer_s,
            "point_count": int(capture.time_s.size),
            "settings": capture.settings,
            "channels": {
                str(number): {
                    "memory_depth": waveform.memory_depth,
                    "scale_v_div": waveform.scale_v_div,
                    "offset_v": waveform.offset_v,
                    "probe": waveform.probe,
                    "header_ascii": waveform.header.decode("ascii"),
                    "scope_measurements": capture.measurements[number],
                    "host_measurements": waveform_statistics(
                        capture.time_s,
                        waveform.voltage_v,
                        capture.measurements[number]["frequency_hz"],
                    ),
                }
                for number, waveform in capture.channels.items()
            },
            "waveform_npz_sha256": digest,
        }
        if extra_metadata:
            metadata.update(extra_metadata)
        (temporary / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8"
        )
        figure, axis = plt.subplots(figsize=(12, 5), constrained_layout=True)
        for number, waveform in capture.channels.items():
            axis.plot(capture.time_s, waveform.voltage_v, linewidth=0.8, label=f"CH{number}")
        axis.set_xlabel("Time (s)")
        axis.set_ylabel("Voltage (V)")
        axis.grid(True, alpha=0.25)
        axis.legend()
        figure.savefig(temporary / "preview.png", dpi=140)
        plt.close(figure)
        os.replace(temporary, target)
    except Exception as exc:
        if temporary.exists() and temporary.parent == output:
            shutil.rmtree(temporary)
        if isinstance(exc, ArtifactError):
            raise
        raise ArtifactError(f"failed to publish capture: {exc}") from exc
    return target


def export_csv(capture_dir: Path, channel: int) -> Path:
    source = capture_dir / "waveform.npz"
    if not source.is_file():
        raise ArtifactError(f"missing {source}")
    with np.load(source, allow_pickle=False) as data:
        key = f"ch{channel}_voltage_v"
        if key not in data:
            raise ArtifactError(f"capture does not contain CH{channel}")
        values = np.column_stack((data["time_s"], data[key]))
    target = capture_dir / f"ch{channel}.csv"
    temporary = capture_dir / f".{target.name}.tmp"
    np.savetxt(temporary, values, delimiter=",", header="time_s,voltage_v", comments="")
    os.replace(temporary, target)
    return target
