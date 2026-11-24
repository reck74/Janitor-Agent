"""Layout marker of a Janitor home (directive #10): what ``auto_migrate`` does today.

There are no layout steps (old terminal installs are uninstalled, not migrated:
plan decision 2.9), so the launcher hook only stamps a home that lacks the
marker and leaves everything else alone.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from janitor import migrations
from janitor.home import LAYOUT_MARKER, LAYOUT_VERSION, read_layout_version


def _tree(home: Path) -> dict:
    return {
        p.relative_to(home).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(home.rglob("*"))
        if p.is_file()
    }


def test_unstamped_home_is_stamped_and_nothing_else_changes(tmp_path):
    home = tmp_path / ".janitor"
    (home / "skins").mkdir(parents=True)
    (home / "config.yaml").write_text("model:\n  default: my-model\n", encoding="utf-8")
    (home / ".env").write_text("MINIMAX_API_KEY=sk-user\n", encoding="utf-8")
    (home / "skins" / "mine.yaml").write_text("name: mine\n", encoding="utf-8")
    before = _tree(home)
    assert migrations.pending(home)

    migrations.auto_migrate(home)

    assert read_layout_version(home) == LAYOUT_VERSION
    assert not migrations.pending(home)
    after = _tree(home)
    assert after.pop(LAYOUT_MARKER)
    assert after == before


def test_stamped_home_is_left_untouched_and_a_missing_home_is_not_created(tmp_path):
    home = tmp_path / ".janitor"
    home.mkdir()
    (home / LAYOUT_MARKER).write_text(f"{LAYOUT_VERSION}\n", encoding="utf-8")
    (home / "config.yaml").write_text("model:\n  default: my-model\n", encoding="utf-8")
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in home.iterdir()}

    migrations.auto_migrate(home)

    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in home.iterdir()} == before
    missing = tmp_path / "nowhere" / ".janitor"
    migrations.auto_migrate(missing)
    assert not missing.exists()
