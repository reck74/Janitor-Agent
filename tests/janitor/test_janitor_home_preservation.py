"""E2E: upgrading the code must never lose what a Janitor user has in ~/.janitor.

Builds a realistic pre-1.0 home (see ``legacy_home.py``) under a temp ``HOME``
and drives the REAL ``janitor`` launcher in a subprocess — no mocks — so the
whole chain runs: HERMES_HOME isolation, first-run layout migration, config
loading, SessionDB, and skill discovery across local + external skill dirs.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.janitor.legacy_home import (
    LEGACY_SKILL_PATHS,
    SESSION_ID,
    USER_OWN_SKILL,
    build_legacy_home,
    launcher_env,
    session_messages,
    snapshot_user_data,
)


def _janitor(root, *args: str) -> subprocess.CompletedProcess:
    code = (
        "import sys; sys.argv = ['janitor', *sys.argv[1:]]; "
        "from janitor_cli import main; main()"
    )
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        capture_output=True,
        text=True,
        env=launcher_env(root),
        cwd=str(root),
        timeout=180,
    )


@pytest.fixture
def legacy(tmp_path):
    return build_legacy_home(tmp_path)


def test_launcher_reads_legacy_sessions(legacy):
    result = _janitor(legacy.root, "sessions", "list")
    assert result.returncode == 0, result.stderr
    assert SESSION_ID in result.stdout


def test_user_data_survives_launch(legacy):
    before_messages = session_messages(legacy.home)

    result = _janitor(legacy.root, "skills", "list")
    assert result.returncode == 0, result.stderr

    after = snapshot_user_data(legacy.home)
    changed = {k for k in legacy.user_data if legacy.user_data[k] != after.get(k)}
    assert not changed, f"user-owned files changed or vanished: {sorted(changed)}"
    assert session_messages(legacy.home) == before_messages


def test_every_skill_is_listed_exactly_once(legacy):
    result = _janitor(legacy.root, "skills", "list")
    assert result.returncode == 0, result.stderr

    rows = [line for line in result.stdout.splitlines() if line.startswith("│")]
    names = [row.split("│")[1].strip() for row in rows]
    for name in [*LEGACY_SKILL_PATHS, USER_OWN_SKILL]:
        assert names.count(name) == 1, (
            f"skill {name!r} listed {names.count(name)} times — a stale local copy "
            f"is shadowing (or duplicating) the shipped one.\n{result.stdout}"
        )
