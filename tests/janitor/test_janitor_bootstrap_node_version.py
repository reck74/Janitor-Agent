"""Regression tests for how Janitor's bootstrap.sh provisions Node.js.

Context (the bugs these tests lock out):
  The root ``package.json`` declares an ``engines.node`` floor.  An older
  ``scripts/bootstrap.sh`` hardcoded ``nvm install 20``, which can never
  satisfy it — every fresh ``curl | bash`` install died at ``npm install``
  with ``EBADENGINE``.  Its replacement sourced upstream's
  ``scripts/lib/node-bootstrap.sh``, which upstream deleted in v0.22.5 when
  Node moved to its package manager (pm); the bootstrap then aborted with
  "node-bootstrap.sh no encontrado tras el clone".

The bootstrap now builds the frontends with ``python -m
hermes_cli.source_build``, the same product step ``janitor update`` runs: it
provisions pm's pinned Node/npm under ``$HERMES_HOME/tools``.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

BOOTSTRAP = REPO_ROOT / "scripts" / "bootstrap.sh"


def _active_lines() -> list[str]:
    return [
        line for line in BOOTSTRAP.read_text(encoding="utf-8").splitlines()
        if line.lstrip() and not line.lstrip().startswith("#")
    ]


def test_bootstrap_does_not_hardcode_node_20():
    """An active ``nvm install 20`` statement must NOT appear in bootstrap.sh.

    This is the exact line that caused the EBADENGINE regression. Comment
    lines may reference the historical bug; only an active statement fails.
    """
    for line in _active_lines():
        assert "nvm install 20" not in line, (
            f"scripts/bootstrap.sh executes 'nvm install 20' (line: {line!r}) "
            "— this causes EBADENGINE. Node comes from hermes_cli.source_build."
        )


def test_bootstrap_depends_only_on_files_and_modules_the_checkout_ships():
    """Every in-checkout file and ``python -m`` module the bootstrap uses
    exists, so an upstream removal fails here instead of on a user's
    ``curl | bash``."""
    text = "\n".join(_active_lines())
    files = set(re.findall(r"\$\{JANITOR_SOURCE_DIR\}/([\w./-]+)", text)) - {".venv"}
    modules = set(re.findall(r"\s-m\s+([\w.]+)", text))

    assert "hermes_cli.source_build" in modules
    assert [f for f in sorted(files) if not (REPO_ROOT / f).exists()] == []
    assert [m for m in sorted(modules) if importlib.util.find_spec(m) is None] == []


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="bash -n probe for the POSIX bootstrap; Windows runtime is WSL2",
)
def test_bootstrap_passes_bash_syntax_check():
    """bootstrap.sh must be syntactically valid bash (``bash -n``)."""
    result = subprocess.run(
        ["bash", "-n", str(BOOTSTRAP)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"bash -n found syntax errors in bootstrap.sh:\n{result.stderr}"
    )
