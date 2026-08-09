from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .errors import AcquisitionError, WaveformDataError


@dataclass(frozen=True)
class ParsedWaveform:
    header: bytes
    raw: np.ndarray


def waveform_block_extent(block: bytes) -> tuple[int, int]:
    if len(block) < 3 or block[:1] != b"#" or not block[1:2].isdigit():
        raise WaveformDataError(f"invalid DS1000E waveform block prefix: {block[:16]!r}")
    length_digits = int(block[1:2])
    if length_digits < 1 or length_digits > 9:
        raise WaveformDataError(f"invalid waveform length field width: {length_digits}")
    header_size = 2 + length_digits
    if len(block) < header_size or not block[2:header_size].isdigit():
        raise WaveformDataError(f"invalid DS1000E waveform header: {block[:header_size]!r}")
    declared = int(block[2:header_size])
    return header_size, declared


def parse_legacy_block(block: bytes) -> ParsedWaveform:
    header_size, declared = waveform_block_extent(block)
    header = block[:header_size]
    payload_and_tail = block[header_size:]
    if len(payload_and_tail) < declared:
        raise WaveformDataError(f"short waveform payload: declared {declared}, received {len(payload_and_tail)}")
    tail = payload_and_tail[declared:]
    if tail not in (b"", b"\n", b"\r\n"):
        raise WaveformDataError(f"unexpected bytes after waveform payload: {tail[:16]!r}")
    raw = np.frombuffer(payload_and_tail[:declared], dtype=np.uint8).copy()
    return ParsedWaveform(header=header, raw=raw)


def voltage_axis(raw: np.ndarray, scale_v_div: float, offset_v: float) -> np.ndarray:
    values = raw.astype(np.float64)
    return (240.0 - values) * (scale_v_div / 25.0) - (offset_v + scale_v_div * 4.6)


def time_axis(point_count: int, sample_rate_hz: float, time_offset_s: float) -> np.ndarray:
    if point_count <= 0 or sample_rate_hz <= 0:
        raise AcquisitionError("point count and sample rate must be positive")
    indices = np.arange(point_count, dtype=np.float64)
    return time_offset_s + (indices - point_count / 2.0) / sample_rate_hz
