from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "rigol-ds1102e"


def _copytree(source: Path, target: Path) -> None:
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def _materialize_venv_interpreter(runtime: Path) -> None:
    """Keep the packaged runtime executable when an installer drops symlinks."""
    interpreter = runtime / ".venv" / "bin" / "python"
    if not interpreter.exists():
        raise FileNotFoundError(f"packaged Python interpreter missing: {interpreter}")
    if not interpreter.is_symlink():
        return

    resolved = interpreter.resolve(strict=True)
    temporary = interpreter.with_name(".python.materializing")
    if temporary.exists():
        temporary.unlink()
    shutil.copy2(resolved, temporary)
    temporary.replace(interpreter)


def package(output_root: Path, sync: bool = True) -> Path:
    output_root = output_root.resolve()
    target = output_root / PLUGIN_NAME
    expected_parent = (REPOSITORY_ROOT / "build" / "codex-plugin").resolve()
    if output_root != expected_parent:
        raise ValueError(f"output must be exactly {expected_parent}")
    if target.exists():
        if target.parent != expected_parent or target.name != PLUGIN_NAME:
            raise ValueError(f"refusing to replace unexpected path: {target}")
        shutil.rmtree(target)

    _copytree(REPOSITORY_ROOT / "plugin" / PLUGIN_NAME, target)
    runtime = target / "runtime"
    runtime.mkdir()
    for filename in ("pyproject.toml", "uv.lock", "README.md"):
        shutil.copy2(REPOSITORY_ROOT / filename, runtime / filename)
    _copytree(REPOSITORY_ROOT / "src", runtime / "src")
    if sync:
        subprocess.run(
            ["uv", "sync", "--frozen", "--no-dev", "--no-editable", "--project", str(runtime)],
            check=True,
        )
        _materialize_venv_interpreter(runtime)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the installable Codex plugin directory")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "build" / "codex-plugin",
    )
    parser.add_argument("--no-sync", action="store_true", help="skip creation of the bundled virtual environment")
    args = parser.parse_args()
    print(package(args.output, sync=not args.no_sync))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
