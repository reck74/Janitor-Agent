"""Minimal Janitor update bootstrap — branding shell only.

Per JANITOR FORK DIRECTIVE #13, this module:

- Prints the Janitor update branding banner.
- Builds the default argparse Namespace.
- Delegates to ``janitor.update_core.run_janitor_update``.

All update-flow logic (fetch / pull / fallback / post-pull validation /
dependency install / stash handling / error recovery) lives in
``janitor.update_core``. The bootstrap is intentionally lightweight so the
early ``janitor update`` intercept can import it on a partially-broken venv.

The git/stash/bytecode helpers previously defined here were moved to
``janitor.update_core``; tests for them live in
``tests/janitor/test_janitor_update_core.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

from janitor import update_core as janitor_update_core


def run_update() -> int:
    """Print Janitor branding and delegate to ``janitor.update_core``."""
    print("\n🔥 THE JANITOR: Initiating tactical update...\n")

    args = SimpleNamespace(
        check=False,
        gateway=False,
        backup=False,
        no_backup=False,
        branch=None,
    )
    return janitor_update_core.run_janitor_update(args)


if __name__ == "__main__":
    import sys

    sys.exit(run_update())
