from pathlib import Path

from rigol_tool.cli import main


def test_dual_session_requires_explicit_qualification_before_usb(
    tmp_path: Path,
    capsys,
) -> None:
    result = main([
        "session",
        "--output",
        str(tmp_path / "run"),
        "--channels",
        "1,2",
    ])

    assert result == 2
    assert "requires [qualification.channel1]" in capsys.readouterr().err
