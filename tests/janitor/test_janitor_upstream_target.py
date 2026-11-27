"""Behavior of ``scripts/janitor-upstream-target.sh``.

Upstream moved from date tags (``v2026.9.24``) to semver (``v0.23.2``) and
also publishes ``rc.*``, ``abandoned-rc.*`` and ``+canary.*`` tags. The old
``git tag -l 'v20*'`` selection kept returning an already-merged date tag, so
the weekly sync reported "nothing to do" forever. These tests run the real
script against a throwaway git repo.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from janitor.home import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "janitor-upstream-target.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("bash") is None,
    reason="needs git and bash",
)

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, **_GIT_ENV, "HOME": str(repo.parent)}
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, **_GIT_ENV, "HOME": str(repo.parent)}
    return subprocess.run(
        ["bash", str(SCRIPT), *args], cwd=repo, env=env, capture_output=True, text=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """``main`` holds the merged date-era release; ``upstream`` carries the rest.

    Each tag points at its own commit on the upstream line, so any tag the
    script picks is distinguishable and none of the newer ones is in ``main``.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "root")
    _git(repo, "tag", "-a", "v2026.9.24", "-m", "date-era release")
    _git(repo, "tag", "v2026.5.29.2")
    _git(repo, "checkout", "-q", "-b", "upstream")
    for tag in (
        "v0.21.6",
        "v0.23.2",
        "v0.23.10",
        "v0.23.2+canary.20261118T064620Z",
        "v0.24.0-rc.1",
        "rc.13-v0.24.0",
        "abandoned-rc.1-v0.25.0",
        "v0.0.1+channel.20261118T064620Z.43839687721",
        "v1.0",
    ):
        _commit(repo, tag)
        _git(repo, "tag", "-a", tag, "-m", tag)
    _git(repo, "checkout", "-q", "main")
    return repo


def test_picks_highest_stable_semver_numerically(repo: Path):
    result = _run(repo, "--tags-ref", "refs/tags", "--branch", "main")
    assert result.returncode == 0, result.stderr
    # Numeric per component (10 > 2); canary/rc/abandoned, date tags and
    # non-three-component tags are never candidates.
    assert result.stdout.strip() == "v0.23.10"


def test_prints_nothing_when_highest_stable_already_merged(repo: Path):
    # The canary/rc/abandoned tags sit on commits after v0.23.10 and stay
    # unmerged: they still must not be offered as a target.
    _git(repo, "merge", "-q", "--no-edit", "v0.23.10")
    result = _run(repo, "--tags-ref", "refs/tags", "--branch", "main")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_reads_only_the_given_tag_namespace(repo: Path):
    """The fork's own v* tags under refs/tags must not compete with upstream's."""
    v0216 = _git(repo, "rev-parse", "v0.21.6^{commit}")
    _git(repo, "update-ref", "refs/upstream-tags/v0.21.6", v0216)
    result = _run(repo, "--tags-ref", "refs/upstream-tags", "--branch", "main")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "v0.21.6"


def test_default_namespace_ignores_the_fork_release_tags(repo: Path):
    """Without --tags-ref only refs/upstream-tags counts: a fork tag such as
    v1.0.0 under refs/tags is never offered as the upstream release."""
    _git(repo, "tag", "v1.0.0")
    v0216 = _git(repo, "rev-parse", "v0.21.6^{commit}")
    _git(repo, "update-ref", "refs/upstream-tags/v0.21.6", v0216)
    result = _run(repo, "--branch", "main")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "v0.21.6"


def test_fails_loudly_without_any_stable_tag(repo: Path):
    """Only date / pre-release tags -> error, not a silent "nothing to do"."""
    for tag in ("v2026.9.24", "v0.24.0-rc.1", "v0.23.2+canary.20261118T064620Z"):
        sha = _git(repo, "rev-parse", f"{tag}^{{commit}}")
        _git(repo, "update-ref", f"refs/only-unstable/{tag}", sha)
    result = _run(repo, "--tags-ref", "refs/only-unstable", "--branch", "main")
    assert result.returncode != 0
    assert result.stdout == ""
