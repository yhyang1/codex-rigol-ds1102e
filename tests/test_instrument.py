from collections import defaultdict

import pytest

from rigol_tool.config import AppConfig
from rigol_tool.cli import _channels
from rigol_tool.errors import TriggerTimeoutError
from rigol_tool.instrument import (
    CaptureSession,
    SettingChange,
    _command_value,
    _equivalent,
    _read_block,
    capture_once,
    identify,
    is_ds1102e_resource,
    parse_optional_measurement,
    preflight,
)


def make_block(size: int, value: int = 125) -> bytes:
    return f"#9{size:09d}".encode() + bytes([value]) * size + b"\n"


class FakeInstrument:
    timeout = 30000
    write_termination = "\n"
    read_termination = "\n"

    def __init__(self, statuses=None, blocks=None):
        self.statuses = iter(statuses or ["STOP"])
        self.last_status = "STOP"
        self.blocks = iter(blocks or [make_block(600)])
        self.pending = None
        self.requested_read_sizes = []
        self.clear_count = 0
        self.writes = []
        self.values = defaultdict(lambda: "0")
        self.values.update({
            "*IDN?": "Rigol Technologies,DS1102E,DS1ET183009083,00.04.04.00.00",
            ":TRIG:MODE?": "EDGE", ":WAV:POIN:MODE?": "NORMAL", ":TRIG:EDGE:SWE?": "AUTO",
            ":TRIG:EDGE:SOUR?": "CH1", ":ACQ:MEMD?": "NORMAL", ":ACQ:TYPE?": "NORMAL",
            ":TRIG:EDGE:SLOP?": "POSITIVE", ":TRIG:EDGE:LEV?": "0.06",
            ":TRIG:EDGE:COUP?": "DC",
            ":ACQ:SAMP?": "1000", ":TIM:SCAL?": "0.001", ":TIM:OFFS?": "0",
            ":CHAN1:MEMD?": "600", ":CHAN1:SCAL?": "1", ":CHAN1:OFFS?": "0", ":CHAN1:PROB?": "10",
            ":CHAN1:DISP?": "ON",
            ":CHAN2:MEMD?": "600", ":CHAN2:SCAL?": "1", ":CHAN2:OFFS?": "0", ":CHAN2:PROB?": "10",
            ":CHAN2:DISP?": "OFF",
            ":MEAS:FREQ? CHAN1": "60", ":MEAS:VPP? CHAN1": "8",
            ":MEAS:FREQ? CHAN2": "60", ":MEAS:VPP? CHAN2": "8",
        })

    def query(self, command):
        if command == ":TRIG:STAT?":
            try:
                self.last_status = next(self.statuses)
            except StopIteration:
                pass
            return self.last_status
        return self.values[command]

    def write(self, command):
        self.writes.append(command)
        if command.startswith(":WAV:DATA?"):
            self.pending = command
            return
        if " " in command:
            prefix, value = command.split(" ", 1)
            self.values[prefix + "?"] = value

    def read_raw(self, size=None):
        assert self.pending
        self.pending = None
        self.requested_read_sizes.append(size)
        return next(self.blocks)

    def close(self):
        pass

    def clear(self):
        self.clear_count += 1


def test_identity() -> None:
    inst = FakeInstrument()
    assert "DS1102E" in identify(inst, "DS1ET183009083")


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("2.80", 2.8),
        (">2.50e+04", None),
        ("99e36", None),
        ("9.9e37", None),
        ("nan", None),
        ("inf", None),
        ("not-a-number", None),
    ],
)
def test_optional_measurement_normalization(response, expected) -> None:
    assert parse_optional_measurement(response) == expected


def test_preflight_queries_selected_channels_without_writes() -> None:
    class QueryOnlyInstrument(FakeInstrument):
        def write(self, command):
            raise AssertionError(f"preflight attempted write: {command}")

    inst = QueryOnlyInstrument()
    inst.values[":MEAS:FREQ? CHAN1"] = "10"
    inst.values[":MEAS:VPP? CHAN1"] = "0.9"
    inst.values[":MEAS:FREQ? CHAN2"] = "99e36"
    inst.values[":MEAS:VPP? CHAN2"] = "0.04"

    result = preflight(inst, "USB::INSTR", identify(inst), (1, 2))

    assert result["trigger_status"] == "STOP"
    assert result["trigger"]["source"] == "CH1"
    assert result["channels"]["1"]["probe"] == 10.0
    assert result["channels"]["1"]["measurements"] == {
        "frequency_hz": 10.0,
        "vpp_v": 0.9,
    }
    assert result["channels"]["2"]["measurements"] == {
        "frequency_hz": None,
        "vpp_v": 0.04,
    }


def test_scpi_channel_aliases_are_equivalent() -> None:
    assert _equivalent("CHAN1", "CH1")
    assert _equivalent("ON", "1")
    assert _equivalent("OFF", "0")
    source = SettingChange(":TRIG:EDGE:SOUR?", ":TRIG:EDGE:SOUR", "EXT")
    sweep = SettingChange(":TRIG:EDGE:SWE?", ":TRIG:EDGE:SWE", "SING")
    slope = SettingChange(":TRIG:EDGE:SLOP?", ":TRIG:EDGE:SLOP", "POS")
    assert _command_value(source, "CH1") == "CHAN1"
    assert _command_value(source, "CH2") == "CHAN2"
    assert _command_value(sweep, "NORMAL") == "NORM"
    assert _command_value(slope, "POSITIVE") == "POS"
    assert _command_value(source, "2.00e+00") == "2"
    assert _command_value(source, "-8.186e-05") == "-0.00008186"


def test_read_block_requests_full_payload_in_first_usbtmc_read() -> None:
    inst = FakeInstrument(blocks=[make_block(8192)])
    inst.pending = "waveform"
    parsed = _read_block(inst, 1, 8192)
    assert parsed.raw.size == 8192
    assert inst.requested_read_sizes == [8224]


@pytest.mark.parametrize(
    "resource",
    [
        "USB0::6833::1416::DS1ET183009083\\x00::0::INSTR",
        "USB0::0x1AB1::0x0588::DS1ET183009083::INSTR",
    ],
)
def test_resource_matching_accepts_decimal_and_hex(resource: str) -> None:
    assert is_ds1102e_resource(resource)


def test_cli_rejects_duplicate_channel_selection() -> None:
    with pytest.raises(Exception, match="unique"):
        _channels("1,1")


def test_capture_and_restore() -> None:
    inst = FakeInstrument(statuses=["RUN", "STOP", "STOP", "WAIT", "STOP", "STOP", "RUN"])
    result = capture_once(inst, "USB::INSTR", identify(inst), AppConfig(), (1,), 1, poll_interval_s=0)
    assert result.time_s.size == 600
    assert ":WAV:POIN:MODE RAW" in inst.writes
    assert ":ACQ:MEMD LONG" in inst.writes
    assert ":ACQ:MEMD NORMAL" in inst.writes
    assert ":TRIG:EDGE:SWE SING" in inst.writes
    assert ":WAV:POIN:MODE NORMAL" in inst.writes
    assert inst.writes[-1] == ":RUN"
    assert inst.writes.index(":TRIG:EDGE:SWE SING") < inst.writes.index(":STOP")


def test_capture_tolerates_overrange_measurement() -> None:
    inst = FakeInstrument(statuses=["RUN", "STOP", "STOP", "WAIT", "STOP", "STOP", "RUN"])
    inst.values[":MEAS:FREQ? CHAN1"] = ">2.50e+04"

    result = capture_once(inst, "USB::INSTR", identify(inst), AppConfig(), (1,), 1, poll_interval_s=0)

    assert result.measurements[1]["frequency_hz"] is None


def test_first_screen_block_is_discarded_for_deep_capture() -> None:
    inst = FakeInstrument(
        statuses=["STOP", "STOP", "STOP", "WAIT", "STOP", "STOP", "STOP"],
        blocks=[make_block(600), make_block(8192)],
    )
    inst.values[":CHAN1:MEMD?"] = "8192"
    result = capture_once(inst, "USB::INSTR", identify(inst), AppConfig(), (1,), 1, poll_interval_s=0)
    assert result.time_s.size == 8192


def test_transfer_error_uses_usbtmc_clear_and_retries() -> None:
    class OneFailedRead(FakeInstrument):
        def read_raw(self, size=None):
            if self.clear_count == 0:
                raise OSError("stalled endpoint")
            return super().read_raw(size)

    inst = OneFailedRead(
        statuses=["STOP", "STOP", "STOP", "WAIT", "STOP", "STOP", "STOP"],
        blocks=[make_block(600)],
    )
    result = capture_once(inst, "USB::INSTR", identify(inst), AppConfig(), (1,), 1, poll_interval_s=0)
    assert result.time_s.size == 600
    assert inst.clear_count == 1


def test_trigger_timeout_restores_state() -> None:
    inst = FakeInstrument(statuses=["STOP", "STOP", "STOP", "WAIT", "STOP", "STOP"])
    with pytest.raises(TriggerTimeoutError):
        capture_once(inst, "USB::INSTR", identify(inst), AppConfig(), (1,), 0.000001, poll_interval_s=0)
    assert inst.writes[-1] == ":STOP"


def test_session_can_wait_then_capture_without_reconfiguring() -> None:
    inst = FakeInstrument(
        statuses=["STOP", "STOP", "STOP", "WAIT", "STOP", "WAIT", "STOP", "STOP", "STOP"],
        blocks=[make_block(600)],
    )
    with CaptureSession(inst, "USB::INSTR", identify(inst), AppConfig(), (1,), poll_interval_s=0) as session:
        with pytest.raises(TriggerTimeoutError):
            session.capture(0.000001)
        result = session.capture(1)
    assert result.time_s.size == 600
    assert inst.writes.count(":ACQ:MEMD LONG") == 1
    assert inst.writes.count(":ACQ:MEMD NORMAL") == 1


def test_dual_capture_enables_both_channels_and_restores_display_state() -> None:
    inst = FakeInstrument(
        statuses=["RUN", "STOP", "STOP", "WAIT", "STOP", "STOP", "RUN"],
        blocks=[make_block(8192, 125), make_block(8192, 150)],
    )
    inst.values[":CHAN1:MEMD?"] = "8192"
    inst.values[":CHAN2:MEMD?"] = "8192"

    result = capture_once(inst, "USB::INSTR", identify(inst), AppConfig(), (1, 2), 1, poll_interval_s=0)

    assert result.time_s.size == 8192
    assert tuple(result.channels) == (1, 2)
    assert ":CHAN1:DISP ON" in inst.writes
    assert ":CHAN2:DISP ON" in inst.writes
    assert ":CHAN2:DISP OFF" in inst.writes
    assert ":ACQ:MEMD NORMAL" in inst.writes
    assert inst.writes.index(":WAV:DATA? CHAN1") < inst.writes.index(":WAV:DATA? CHAN2")


def test_dual_capture_rejects_unexpected_memory_depth() -> None:
    inst = FakeInstrument(
        statuses=["STOP", "STOP", "STOP", "WAIT", "STOP", "STOP", "STOP"],
        blocks=[make_block(16384)],
    )
    inst.values[":CHAN1:MEMD?"] = "16384"
    inst.values[":CHAN2:MEMD?"] = "16384"

    with pytest.raises(Exception, match="expected 8192"):
        capture_once(inst, "USB::INSTR", identify(inst), AppConfig(), (1, 2), 1, poll_interval_s=0)
