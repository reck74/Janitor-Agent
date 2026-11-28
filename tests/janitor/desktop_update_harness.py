"""Run the desktop app's POSIX update hand-off offline against a fake install.

``scripts/desktop-update/posix.sh`` is what the desktop app spawns to apply an
update (``apps/desktop/electron/main.ts`` → ``applyUpdatesPosixHandoff``). The
fake install root has a ``venv/bin/hermes`` that only records its argv, and —
unless ``with_janitor=False`` — a ``venv/bin/janitor`` that runs the REAL
``janitor update`` intercept (``janitor/cli.py`` → ``janitor/update_bootstrap.py``
→ ``parse_update_args``) with ``run_janitor_update`` replaced by a recorder, so
the exact argv the hand-off passes is parsed by the real Janitor parser.
Nothing is pulled or installed and nothing outside ``root`` is written.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POSIX_SH = REPO_ROOT / "scripts" / "desktop-update" / "posix.sh"

_FAKE_HERMES = """#!/bin/bash
case "$*" in *--help*) echo "--keep-stash"; exit 0 ;; esac
printf '%s\\n' "$*" >> "$JANITOR_TEST_HERMES_ARGV"
exit 0
"""

_RECORDING_CORE = (
    "import json, os, sys\n"
    "sys.argv = ['janitor', *sys.argv[1:]]\n"
    "import janitor.update_core as core\n"
    "def _record(args):\n"
    "    with open(os.environ['JANITOR_TEST_CORE_ARGS'], 'a', encoding='utf-8') as fh:\n"
    "        fh.write(json.dumps(vars(args), sort_keys=True) + '\\n')\n"
    "    return int(os.environ.get('JANITOR_TEST_CORE_EXIT', '0'))\n"
    "core.run_janitor_update = _record\n"
    "import janitor.cli\n"
)


def _write_exe(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def handoff_env(root: Path, **overrides: str) -> dict:
    """The env the app passes the hand-off, without the test host's HERMES_* and APPIMAGE."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERMES_") and k != "APPIMAGE"}
    env.update({"HOME": str(root), "TMPDIR": str(root), "HERMES_HOME": str(root), **overrides})
    return env


def run_posix_handoff(
    root: Path, *extra_args: str, with_janitor: bool = True, env: dict | None = None,
    script: Path = POSIX_SH,
) -> dict:
    """Run the real hand-off end to end; return what each entry point received.

    ``script`` is the hand-off to run (a copy with a constant replaced, for a
    test that cannot use a system path). ``env`` adds variables to the environment the app would pass (e.g. ``APPIMAGE``);
    ``JANITOR_TEST_CORE_EXIT`` there makes the recorded ``janitor update`` fail
    with that exit code.
    """
    install_root = root / "hermes-agent"
    bin_dir = install_root / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    _write_exe(bin_dir / "hermes", _FAKE_HERMES)
    if with_janitor:
        _write_exe(
            bin_dir / "janitor",
            f"#!/bin/bash\nexec {sys.executable!s} -c \"$JANITOR_TEST_CORE\" \"$@\"\n",
        )

    hermes_argv = root / "hermes-argv.txt"
    core_args = root / "core-args.jsonl"
    run_env = handoff_env(root, **(env or {}))
    run_env.update({
        "PYTHONPATH": str(REPO_ROOT),
        "JANITOR_TEST_CORE": _RECORDING_CORE,
        "JANITOR_TEST_HERMES_ARGV": str(hermes_argv),
        "JANITOR_TEST_CORE_ARGS": str(core_args),
    })
    subprocess.run(
        ["/bin/bash", str(script), "--install-root", str(install_root), "--no-ui", *extra_args],
        env=run_env,
        timeout=60,
        check=True,
    )

    # posix.sh re-execs itself detached and writes its result file last.
    result = root / ".hermes-update-result.json"
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline and not result.exists():
        time.sleep(0.1)
    assert result.exists(), "hand-off never wrote its result file"
    # finish() removes its status file last, after any relaunch was accepted or
    # downgraded (which rewrites the result): that is the run's end.
    while time.monotonic() < deadline and any(root.glob("hermes-update-status.*")):
        time.sleep(0.1)
    assert not any(root.glob("hermes-update-status.*")), "hand-off never finished"

    return {
        "result": json.loads(result.read_text(encoding="utf-8")),
        "hermes": hermes_argv.read_text(encoding="utf-8").splitlines() if hermes_argv.exists() else [],
        "core": [
            json.loads(line)
            for line in (core_args.read_text(encoding="utf-8").splitlines() if core_args.exists() else [])
        ],
    }
