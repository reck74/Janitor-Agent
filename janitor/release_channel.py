"""The Janitor release channel (plan decision 2.10, directive #13).

Users receive tagged versions only. ``stable`` is the branch the release
workflow fast-forwards to every published ``v…`` tag, so "the latest release"
is a branch tip the installer, the updater, the banner probe and the desktop
app can all track; a merge to ``main`` moves nothing a user follows.
"""
from __future__ import annotations

import sys
from pathlib import Path

RELEASE_BRANCH = "stable"


def expected_tag(pyproject: Path) -> str:
    """The only tag that may release the tree holding ``pyproject``: ``v`` plus
    the version the user sees (``0.21.5+janitor.1`` → ``v0.21.5-janitor.1``).
    A release is found by its tag, so the two must never disagree."""
    import tomllib

    from janitor.version import display_version

    with open(pyproject, "rb") as fh:
        return "v" + display_version(tomllib.load(fh)["project"]["version"])


def check_tag(tag: str, pyproject: Path) -> str | None:
    """None when ``tag`` releases this tree, else the reason, for the release job."""
    expected = expected_tag(pyproject)
    if tag == expected:
        return None
    return (
        f"The tag {tag!r} does not match the version in {pyproject.name} (expected {expected!r}). "
        "Bump the version in pyproject.toml and hermes_cli/__init__.py, merge it to main and tag that commit."
    )


def apply_to_engine() -> None:
    """Point upstream's passive update probe (banner, TUI badge, dashboard) at
    the release channel. Idempotent; a missing module leaves the probe as is."""
    try:
        from hermes_cli import banner
    except Exception:
        return
    banner._UPDATE_BRANCH = RELEASE_BRANCH


def main(argv: list[str]) -> int:
    """``python -m janitor.release_channel --check-tag <tag>`` (release workflow)
    or ``--expected-tag`` (the tag this tree would be released as, e.g. to name
    the Arch package locally)."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if argv == ["--expected-tag"]:
        print(expected_tag(pyproject))
        return 0
    if len(argv) != 2 or argv[0] != "--check-tag":
        print(
            "usage: python -m janitor.release_channel --check-tag <tag> | --expected-tag",
            file=sys.stderr,
        )
        return 2
    problem = check_tag(argv[1], pyproject)
    if problem:
        print(f"::error::{problem}")
        return 1
    print(f"tag {argv[1]} matches the version")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
