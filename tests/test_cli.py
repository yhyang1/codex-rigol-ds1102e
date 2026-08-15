from pathlib import Path

from rigol_tool.cli import main
from rigol_tool.cli import parser


def test_preflight_parser_selects_both_channels() -> None:
    args = parser().parse_args(["preflight", "--channels", "1,2"])

    assert args.command == "preflight"
    assert args.channels == (1, 2)


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
