"""Run the fork's ``scripts/install.sh`` stages offline against a temp HOME.

``fake_install_dir`` stands in for the checkout the ``repository`` stage would
clone: its ``venv/bin/python`` execs this test interpreter (which imports the
real ``janitor`` package from the repo), and it carries the upstream templates
the ``config`` stage copies. Nothing is downloaded and nothing outside
``root`` is written.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"


def fake_install_dir(root: Path) -> Path:
    install = root / "install"
    bin_dir = install / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    python.chmod(0o755)
    for name in ("cli-config.yaml.example", ".env.example"):
        shutil.copy2(REPO_ROOT / name, install / name)
    # setup_path only checks that the checked-in entrypoint exists.
    (install / "hermes").write_text("# entrypoint stub\n", encoding="utf-8")
    return install


def run_install_sh(
    root: Path, *args: str, path_prefix: Optional[Path] = None, path: Optional[str] = None
) -> subprocess.CompletedProcess:
    """``path`` replaces PATH outright: a stage that probes for a tool (``cua-driver``)
    must not find, and run, the developer's own copy."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERMES_")}
    env.update({"HOME": str(root), "PYTHONPATH": str(REPO_ROOT), "SHELL": "/bin/bash"})
    if path is not None:
        env["PATH"] = path
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args],
        env=env,
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=180,
    )


def stage_frame(stdout: str) -> Optional[dict]:
    """The desktop's parser: the last stdout line that is a stage result frame."""
    for line in reversed([l for l in stdout.splitlines() if l.strip()]):
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("ok"), bool) and isinstance(parsed.get("stage"), str):
            return parsed
    return None


def tree_snapshot(root: Path) -> dict:
    """Every entry under ``root``: file bytes, symlink target, or ``dir``."""
    snap = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            snap[rel] = ("link", os.readlink(path))
        elif path.is_dir():
            snap[rel] = ("dir", path.stat().st_mode)
        else:
            snap[rel] = ("file", path.stat().st_mode, path.read_bytes())
    return snap


def run_stage(root: Path, stage: str, install: Path, home: Path, *extra: str, **kw) -> subprocess.CompletedProcess:
    return run_install_sh(
        root,
        "--stage",
        stage,
        "--non-interactive",
        "--json",
        "--dir",
        str(install),
        "--hermes-home",
        str(home),
        *extra,
        **kw,
    )


def write_fakes(bin_dir: Path, fakes: dict) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, body in fakes.items():
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
