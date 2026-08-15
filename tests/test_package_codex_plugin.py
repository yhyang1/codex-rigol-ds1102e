import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "package_codex_plugin.py"
SPEC = importlib.util.spec_from_file_location("package_codex_plugin", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_materialize_venv_interpreter_replaces_symlink(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    bin_dir = runtime / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    backing = tmp_path / "python3.13"
    backing.write_bytes(b"embedded-python")
    backing.chmod(0o755)
    interpreter = bin_dir / "python"
    interpreter.symlink_to(backing)

    MODULE._materialize_venv_interpreter(runtime)

    assert interpreter.is_file()
    assert not interpreter.is_symlink()
    assert interpreter.read_bytes() == b"embedded-python"
    assert interpreter.stat().st_mode & 0o100
