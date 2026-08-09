import numpy as np
import pytest

from rigol_tool.errors import AcquisitionError
from rigol_tool.waveform import parse_legacy_block, time_axis, voltage_axis, waveform_block_extent


def block(payload: bytes, tail: bytes = b"\n") -> bytes:
    return f"#9{len(payload):09d}".encode() + payload + tail


def test_parse_legacy_block() -> None:
    parsed = parse_legacy_block(block(bytes([25, 125, 225])))
    assert parsed.header == b"#9000000003"
    assert parsed.raw.tolist() == [25, 125, 225]
    assert waveform_block_extent(parsed.header) == (11, 3)


@pytest.mark.parametrize("value", [b"", b"#x00000001x", b"#9000000003xy"])
def test_rejects_bad_blocks(value: bytes) -> None:
    with pytest.raises(AcquisitionError):
        parse_legacy_block(value)


def test_voltage_formula_from_rigol_guide() -> None:
    raw = np.array([25, 225], dtype=np.uint8)
    actual = voltage_axis(raw, scale_v_div=1.0, offset_v=0.0)
    np.testing.assert_allclose(actual, [4.0, -4.0])


def test_deep_time_axis_centers_on_offset() -> None:
    actual = time_axis(4, sample_rate_hz=2.0, time_offset_s=0.25)
    np.testing.assert_allclose(actual, [-0.75, -0.25, 0.25, 0.75])
