"""``janitor update --commit <sha>`` (plan F9-12, directive #13).

The app's signed manifest names the engine commit of a release. The update
must land on exactly that commit, not on whatever the channel's tip is by the
time it runs, and the pin is checked against what the channel published before
any code is activated. Real git throughout; everything else is stubbed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import janitor.update_core as juc
from tests.janitor.test_janitor_desktop_update import (  # noqa: F401  (checkout is a fixture)
    _git,
    _stub_everything_but_git,
    checkout,
)


def _push_commit(tmp_path: Path, name: str, branch: str = "main") -> str:
    """One more commit on the origin's ``branch``; returns its sha."""
    seed = tmp_path / "seed"
    _git(seed, "checkout", "-B", branch)
    (seed / f"{name}.txt").write_text(name, encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", name)
    _git(seed, "push", str(tmp_path / "origin.git"), branch)
    return _git(seed, "rev-parse", "HEAD")


def _update(*argv: str) -> int:
    return juc.run_janitor_update(juc.parse_update_args(["--yes", "--keep-stash", "--branch", "main", *argv]))


@pytest.fixture
def stubbed(checkout, tmp_path, monkeypatch):
    (checkout / "tracked.txt").write_text("v1\n", encoding="utf-8")  # a clean tree
    _stub_everything_but_git(monkeypatch, checkout, tmp_path / "home", [])
    return checkout


def test_the_engine_lands_on_the_pinned_commit_when_the_channel_moved_on(stubbed, tmp_path):
    """The channel advanced while the app was downloading: the manifest's commit wins."""
    pinned = _git(tmp_path / "seed", "rev-parse", "HEAD")
    newer = _push_commit(tmp_path, "three")

    assert _update("--commit", pinned) == 0

    assert _git(stubbed, "rev-parse", "HEAD") == pinned != newer
    assert not (stubbed / "three.txt").exists()


def test_a_commit_the_channel_never_published_changes_nothing(stubbed, tmp_path, capsys):
    before = _git(stubbed, "rev-parse", "HEAD")
    foreign = _push_commit(tmp_path, "elsewhere", branch="other")

    assert _update("--commit", foreign) == 1

    assert _git(stubbed, "rev-parse", "HEAD") == before
    assert "no está publicada" in capsys.readouterr().out


def test_an_unknown_commit_changes_nothing(stubbed):
    before = _git(stubbed, "rev-parse", "HEAD")

    assert _update("--commit", "0" * 40) == 1

    assert _git(stubbed, "rev-parse", "HEAD") == before


def test_a_pin_older_than_the_installed_engine_never_goes_back(stubbed, capsys):
    older = _git(stubbed, "rev-parse", "HEAD")
    assert _update() == 0
    current = _git(stubbed, "rev-parse", "HEAD")
    assert current != older

    assert _update("--commit", older) == 0

    assert _git(stubbed, "rev-parse", "HEAD") == current
    assert "No se baja de versión" in capsys.readouterr().out


def test_repeating_the_same_pin_is_a_no_op_that_succeeds(stubbed, tmp_path):
    """The same delivery can be run again to finish one cut halfway."""
    pinned = _git(tmp_path / "seed", "rev-parse", "HEAD")

    assert _update("--commit", pinned) == 0
    assert _update("--commit", pinned) == 0

    assert _git(stubbed, "rev-parse", "HEAD") == pinned


@pytest.mark.parametrize("value", ["main", "HEAD", "abc123", "--upload-pack=x", "A" * 40, "0" * 41])
def test_only_a_full_lowercase_sha_is_accepted(value):
    with pytest.raises(SystemExit) as exit_info:
        juc.parse_update_args(["--commit", value])
    assert exit_info.value.code == 2


def test_a_malformed_pin_from_the_patched_entry_point_is_refused(stubbed):
    """cmd_update's namespace bypasses argparse: the core checks the value itself."""
    import argparse

    before = _git(stubbed, "rev-parse", "HEAD")

    assert juc.run_janitor_update(argparse.Namespace(commit="origin/main", branch="main")) == 2

    assert _git(stubbed, "rev-parse", "HEAD") == before
