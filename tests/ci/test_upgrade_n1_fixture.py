"""Historical engine fixture selection uses real Git ancestry and fails closed."""

import subprocess

import pytest

from tests.e2e.core.upgrade.git import _git_world as world


@pytest.fixture
def history(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()
    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("commit", "--allow-empty", "-qm", "historical engine")
    old = git("rev-parse", "HEAD")
    git("tag", "v2026.8.16")
    git("update-ref", "refs/janitor-ci/upgrade-n1", old)
    git("commit", "--allow-empty", "-qm", "current engine")
    monkeypatch.setattr(world.H, "WORKTREE", tmp_path)
    monkeypatch.delenv("HERMES_E2E_N1_TAG", raising=False)
    return git, old


def test_upstream_discovers_historical_tag(history):
    assert world.n1_tag() == "v2026.8.16"


def test_fork_uses_private_fixture_without_product_tags(history, monkeypatch):
    git, old = history
    git("tag", "-d", "v2026.8.16")
    monkeypatch.setenv("HERMES_E2E_N1_TAG", "refs/janitor-ci/upgrade-n1")
    assert world.n1_base() == old


@pytest.mark.parametrize("ref", ["HEAD", "refs/missing/fixture"])
def test_invalid_fixture_does_not_fall_back(history, monkeypatch, ref):
    monkeypatch.setenv("HERMES_E2E_N1_TAG", ref)
    with pytest.raises(AssertionError):
        world.n1_tag()


def test_unrelated_fixture_is_rejected(history, monkeypatch):
    git, _ = history
    tree = git("rev-parse", "HEAD^{tree}")
    orphan = git("commit-tree", tree, "-m", "unrelated root")
    git("update-ref", "refs/janitor-ci/upgrade-n1", orphan)
    monkeypatch.setenv("HERMES_E2E_N1_TAG", "refs/janitor-ci/upgrade-n1")
    with pytest.raises(AssertionError):
        world.n1_tag()
