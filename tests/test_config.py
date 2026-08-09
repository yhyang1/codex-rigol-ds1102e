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
