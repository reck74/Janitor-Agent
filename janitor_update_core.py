#!/usr/bin/env python3
"""
Janitor update core — the canonical update flow shared by both entry points.

Aligned with the official Hermes ``_cmd_update_impl`` in ``hermes_cli/main.py``.
Both ``janitor update`` (early intercept in ``janitor_cli.py``) and the
monkey-patched ``cmd_update`` (also in ``janitor_cli.py``) delegate here.

Helpers are imported lazily inside each phase so a partially-broken venv
(after a failed pull, mid-update crash, etc.) can still recover without
importing every Hermes module at startup. When a helper import fails the
core falls back to a local minimal implementation that preserves the
original ``janitor_update_bootstrap`` behavior for that one helper.

Per JANITOR FORK DIRECTIVE #12 (proposed in this same plan): any change to
the update flow lives here, not inline in ``janitor_cli.py`` or
``janitor_update_bootstrap.py``.
"""

from __future__ import annotations

import sys


def _git_cmd() -> list[str]:
    """Return the git command list, with Windows atomic-append workaround."""
    base = ["git"]
    if sys.platform == "win32":
        base = ["git", "-c", "windows.appendAtomically=false"]
    return base


def run_janitor_update(args) -> int:
    """Canonical Janitor update flow. Mirrors ``_cmd_update_impl``.

    Args:
        args: argparse Namespace from the CLI. Recognised attributes:
            check (bool): if True, only report behind-count and return.
            gateway (bool): suppresses interactive prompts.
            backup (bool): forces a pre-update backup for this run.
            no_backup (bool): skips pre-update backup even if config has it on.
            branch (str|None): target branch (default ``"main"``).

    Returns:
        Process exit code: 0 = updated, 1 = failed, 130 = cancelled.
    """
    raise NotImplementedError("Task3 will implement this.")
