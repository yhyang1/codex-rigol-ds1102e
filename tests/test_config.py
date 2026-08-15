from pathlib import Path

import pytest

from rigol_tool.config import load_config
from rigol_tool.errors import ConfigurationError


def test_load_profile(tmp_path: Path) -> None:
    profile = tmp_path / "profile.toml"
    profile.write_text(
        """
[instrument]
serial = "DS1ET183009083"
[acquisition]
memory_depth = "long"
[channel1]
probe = 10
coupling = "dc"
[trigger]
mode = "edge"
source = "chan1"
[qualification]
nominal_frequency_hz = 1000
min_vpp_v = 2
max_vpp_v = 4
"""
    )
    config = load_config(profile)
    assert config.instrument.serial == "DS1ET183009083"
    assert config.acquisition.memory_depth == "LONG"
    assert config.channels[1].probe == 10
    assert config.trigger.source == "CHAN1"
    assert config.qualification.nominal_frequency_hz == 1000
    assert config.qualification.min_vpp_v == 2


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    profile = tmp_path / "bad.toml"
    profile.write_text("[instrument]\nmagic = true\n")
    with pytest.raises(ConfigurationError):
        load_config(profile)


def test_invalid_qualification_range_is_rejected(tmp_path: Path) -> None:
    profile = tmp_path / "bad-range.toml"
    profile.write_text("[qualification]\nmin_vpp_v = 4\nmax_vpp_v = 2\n")
    with pytest.raises(ConfigurationError):
        load_config(profile)


def test_per_channel_qualification_inherits_flat_defaults(tmp_path: Path) -> None:
    profile = tmp_path / "dual.toml"
    profile.write_text(
        """
[qualification]
frequency_tolerance_percent = 4
min_complete_pulses = 4
[qualification.channel1]
nominal_frequency_hz = 1000
min_vpp_v = 2
[qualification.channel2]
nominal_frequency_hz = 30
min_vpp_v = 1
"""
    )

    config = load_config(profile)

    assert config.qualification_for(1).nominal_frequency_hz == 1000
    assert config.qualification_for(2).nominal_frequency_hz == 30
    assert config.qualification_for(2).frequency_tolerance_percent == 4
    assert config.qualification_for(2).min_complete_pulses == 4


def test_invalid_nested_qualification_range_is_rejected(tmp_path: Path) -> None:
    profile = tmp_path / "bad-dual.toml"
    profile.write_text(
        "[qualification.channel2]\nmin_vpp_v = 4\nmax_vpp_v = 2\n"
    )
    with pytest.raises(ConfigurationError, match="qualification.channel2"):
        load_config(profile)


def test_static_qualification_windows(tmp_path: Path) -> None:
    profile = tmp_path / "static.toml"
    profile.write_text(
        """
[qualification]
min_vpp_v = 0.6
[qualification.channel1]
mode = "pulse"
nominal_frequency_hz = 10
[qualification.channel2]
mode = "static"
allowed_level_windows_v = [[-0.05, 0.08], [2.6, 3.1]]
max_vpp_v = 0.1
"""
    )

    config = load_config(profile)

    assert config.qualification_for(1).mode == "PULSE"
    assert config.qualification_for(2).mode == "STATIC"
    assert config.qualification_for(2).min_vpp_v == 0.6
    assert config.qualification_for(2).allowed_level_windows_v == (
        (-0.05, 0.08),
        (2.6, 3.1),
    )


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('mode = "static"\n', "required"),
        ('mode = "unknown"\n', "mode"),
        ('mode = "static"\nallowed_level_windows_v = [[1, 1]]\n', "less than"),
        ('mode = "static"\nallowed_level_windows_v = [[0, 1], [1, 2]]\n', "non-overlapping"),
        ('mode = "static"\nallowed_level_windows_v = [[0, inf]]\n', "finite"),
        ('mode = "pulse"\nallowed_level_windows_v = [[0, 1]]\n', "only valid"),
    ],
)
def test_invalid_static_qualification_windows(tmp_path: Path, body: str, message: str) -> None:
    profile = tmp_path / "bad-static.toml"
    profile.write_text("[qualification.channel2]\n" + body)

    with pytest.raises(ConfigurationError, match=message):
        load_config(profile)
