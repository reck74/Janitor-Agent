"""Regression tests for the Node.js version pinned by Janitor's bootstrap.sh.

Context (the bug these tests lock out):
  The root ``package.json`` declares ``engines.node >= 22.22.0``.  An older
  ``scripts/bootstrap.sh`` hardcoded ``nvm install 20``, which can never
  satisfy that constraint — every fresh ``curl | bash`` install died at
  ``npm install`` with ``EBADENGINE``.  Worse, the PATH it exported lived
  only inside the ``curl | bash`` subshell, so the user's login shell saw
  ``npm: command not found`` immediately afterwards.

The fix delegates to ``scripts/lib/node-bootstrap.sh`` (the shared,
upstream-maintained helper).  These tests assert the three properties that
must hold for the bug to stay fixed:

1. The shared helper targets Node major 22 by default (so even a ``curl |
   bash`` install lands on a version the engines field accepts).
2. ``bootstrap.sh`` no longer hardcodes the old, sub-floor ``nvm install
   20`` (string-level regression guard — the same pattern used by
   ``tests/test_janitor_no_duplicate_methods.py`` for structural guards).
3. ``bootstrap.sh`` delegates Node provisioning to the shared helper
   rather than rolling its own ``nvm install`` call.

Tests run hermetically: they only ``source`` the helper in a subprocess
and inspect exported variables.  No network, no tarball download.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

BOOTSTRAP = REPO_ROOT / "scripts" / "bootstrap.sh"
NODE_HELPER = REPO_ROOT / "scripts" / "lib" / "node-bootstrap.sh"


def _source_helper_get_var(varname: str) -> str:
    """Source node-bootstrap.sh in a fresh bash and return an exported var.

    Runs in ``--noprofile --norc`` so the user's shell doesn't leak anything
    into the probe.  The helper only sets variables on source (no side
    effects until ``ensure_node`` is actually invoked), so this is safe.
    """
    result = subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-c",
            f'source "{NODE_HELPER}" && printf "%s" "${{{varname}:-}}"',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="helper targets POSIX installs; the documented Windows runtime is WSL2",
)
def test_node_helper_targets_major_22_by_default():
    """The shared helper must default to Node 22 (satisfies engines >=22.22.0).

    A Janitor bootstrap that delegates to this helper inherits the target —
    if the default drops below 22, ``npm install`` will fail EBADENGINE on
    a fresh install exactly like the original bug.
    """
    target = _source_helper_get_var("HERMES_NODE_TARGET_MAJOR")
    assert target == "22", (
        f"node-bootstrap.sh targets Node major '{target}', expected '22'. "
        "A fresh Janitor install would fail EBADENGINE — bump "
        "HERMES_NODE_TARGET_MAJOR back to 22."
    )


def test_bootstrap_does_not_hardcode_node_20():
    """An active ``nvm install 20`` statement must NOT appear in bootstrap.sh.

    This is the exact line that caused the EBADENGINE regression. Once the
    bootstrap delegates to the shared helper, no Node version literal
    should be hardcoded — the helper owns the version.  Same structural-
    guard style as ``test_janitor_no_duplicate_methods.py`` (directive #15)
    and ``test_janitor_monkeypatch_signatures.py`` (directive #14).

    Comment lines are skipped: a comment may legitimately reference the
    historical bug (e.g. "previously hardcoded nvm install 20") without
    re-introducing it. Only an active, uncommented statement fails.
    """
    text = BOOTSTRAP.read_text(encoding="utf-8")
    active_lines = [
        line for line in text.splitlines()
        if line.lstrip() and not line.lstrip().startswith("#")
    ]
    for line in active_lines:
        assert "nvm install 20" not in line, (
            f"scripts/bootstrap.sh executes 'nvm install 20' (line: {line!r}) "
            "— this causes EBADENGINE because package.json requires Node "
            ">=22.22.0. Delegate to scripts/lib/node-bootstrap.sh via "
            "ensure_node instead."
        )


def test_bootstrap_delegates_to_shared_node_helper():
    """bootstrap.sh must source scripts/lib/node-bootstrap.sh and call ensure_node.

    This is the structural contract introduced by the fix.  If either side
    disappears, the bootstrap has no Node provisioning (or, worse, has gone
    back to rolling its own nvm block).
    """
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "node-bootstrap.sh" in text, (
        "scripts/bootstrap.sh must source scripts/lib/node-bootstrap.sh "
        "(the shared Node provisioning helper)."
    )
    assert "ensure_node" in text, (
        "scripts/bootstrap.sh must call ensure_node() after sourcing the "
        "shared helper — that's the function that actually provisions Node."
    )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="bash -n probe for the POSIX bootstrap; Windows runtime is WSL2",
)
def test_bootstrap_passes_bash_syntax_check():
    """bootstrap.sh must be syntactically valid bash (``bash -n``).

    Guards against regressions where the refactor breaks shell parsing.
    Cheap and catches a wide class of typos before the next ``curl | bash``
    user hits them at runtime.
    """
    result = subprocess.run(
        ["bash", "-n", str(BOOTSTRAP)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"bash -n found syntax errors in bootstrap.sh:\n{result.stderr}"
    )


if __name__ == "__main__":
    sys.exit(subprocess.run(["pytest", "-v", __file__]).returncode)
