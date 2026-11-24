"""The Janitor release channel (plan decision 2.10, directive #13).

Users receive tagged versions only. ``stable`` is the branch the release
workflow fast-forwards to every published ``v…`` tag, so "the latest release"
is a branch tip the installer, the updater, the banner probe and the desktop
app can all track; a merge to ``main`` moves nothing a user follows.
"""
from __future__ import annotations

RELEASE_BRANCH = "stable"


def apply_to_engine() -> None:
    """Point upstream's passive update probe (banner, TUI badge, dashboard) at
    the release channel. Idempotent; a missing module leaves the probe as is."""
    try:
        from hermes_cli import banner
    except Exception:
        return
    banner._UPDATE_BRANCH = RELEASE_BRANCH
