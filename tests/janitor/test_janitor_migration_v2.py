"""Layout v2 migration of ~/.janitor: retired / renamed Janitor skills (``janitor/migrations/v2.py``)."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from janitor import migrations
from janitor.home import SKILLS_ROOT  # noqa: E402
from janitor.home import LAYOUT_VERSION, SKILLS_EXTERNAL_DIRS, read_layout_version, write_layout_version
from janitor.migrations import v1, v2
from tests.janitor.legacy_home import (
    LEGACY_SKILL_PATHS,
    LEGACY_SKILL_SOURCES,
    REPO_ROOT,
    USER_MODIFIED_SKILL,
    build_legacy_home,
)

ROOT_VAR = SKILLS_EXTERNAL_DIRS[0]


def _tree(home: Path) -> dict:
    return {
        p.relative_to(home).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(home.rglob("*"))
        if p.is_file()
    }


def _config(home: Path) -> dict:
    return yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def home_v1(tmp_path):
    """A Janitor 1.x home (seeded, stamped v1) still carrying retired skills and names."""
    from janitor.seed import ensure_home

    home = tmp_path / ".janitor"
    ensure_home(home)
    write_layout_version(1, home)
    (home / ".env").write_text("MINIMAX_API_KEY=sk-test\n", encoding="utf-8")

    skills = home / "skills"
    # Pristine copy recognised by a frozen shipped digest (no manifest entry).
    shutil.copytree(LEGACY_SKILL_SOURCES / "janitor-core", skills / "janitor-core")
    # Pristine copy recognised by its manifest entry.
    shutil.copytree(LEGACY_SKILL_SOURCES / "janitor-repo-research-agent", skills / "research" / "janitor-repo-research-agent")
    # A retired skill the user edited after it was synced.
    edited = skills / "devops" / "janitor-config-audit"
    edited.mkdir(parents=True)
    (edited / "SKILL.md").write_text("---\nname: janitor-config-audit\n---\n# shipped\n", encoding="utf-8")
    manifest = {
        "janitor-repo-research-agent": v1.dir_hash(skills / "research" / "janitor-repo-research-agent"),
        "janitor-config-audit": v1.dir_hash(edited),
        "janitor-vault": "0" * 32,  # synced once, deleted by the user since
    }
    (edited / "SKILL.md").write_text("---\nname: janitor-config-audit\n---\n# mine now\n", encoding="utf-8")
    (skills / ".bundled_manifest").write_text(
        "".join(f"{k}:{v}\n" for k, v in manifest.items()), encoding="utf-8"
    )

    config = _config(home)
    config["skills"]["disabled"] = ["janitor-core", "my-skill", "janitor-repo-research-agent"]
    config["skills"]["platform_disabled"] = {"telegram": ["janitor-browser", "pdf"], "cli": ["pdf"]}
    config["skills"]["external_dirs"] += [f"{ROOT_VAR}/agents/janitor-code-review-agent", f"{ROOT_VAR}/agents"]
    config.setdefault("janitor", {})["skills"] = ["pdf", "janitor-repo-research-agent"]
    (home / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return home


def _quiet(_line: str) -> None:
    pass


def test_legacy_names_are_not_shipped_anymore():
    """The frozen list and the live tree never overlap, or v2 would delete live skills' copies."""
    assert v2.LEGACY_NAMES and not (v2.LEGACY_NAMES & set(v1.shipped_skills()))
    assert set(v2.RENAMED.values()) <= set(v1.shipped_skills())
    assert set(v2.SHIPPED_DIGESTS) <= v2.LEGACY_NAMES


def test_migration_retires_pristine_copies_and_keeps_edited_ones(home_v1):
    env_before = (home_v1 / ".env").read_bytes()
    lines: list[str] = []
    backup = migrations.run(home_v1, out=lines.append)

    skills = home_v1 / "skills"
    assert not (skills / "janitor-core").exists()
    assert not (skills / "research").exists(), "emptied category dir left behind"
    assert (skills / "devops" / "janitor-config-audit" / "SKILL.md").read_text(encoding="utf-8").endswith("# mine now\n")
    assert any("KEEP skills/devops/janitor-config-audit" in line for line in lines)
    manifest = (skills / ".bundled_manifest").read_text(encoding="utf-8").split()
    assert [entry.split(":")[0] for entry in manifest] == ["janitor-config-audit"]

    assert backup is not None and backup.name.startswith(f"v{LAYOUT_VERSION}-")
    assert (backup / "skills" / "janitor-core" / "SKILL.md").is_file()
    assert (backup / "skills" / "research" / "janitor-repo-research-agent" / "SKILL.md").is_file()
    assert "janitor-core" in _config(backup)["skills"]["disabled"]
    assert (home_v1 / ".env").read_bytes() == env_before
    assert read_layout_version(home_v1) == LAYOUT_VERSION


def test_config_references_are_cleaned_and_renamed(home_v1):
    before = _config(home_v1)
    migrations.run(home_v1, out=_quiet)
    after = _config(home_v1)

    assert after["skills"]["disabled"] == ["my-skill", "janitor-repo-research"]
    assert after["skills"]["platform_disabled"] == {"telegram": ["pdf"], "cli": ["pdf"]}
    assert after["janitor"]["skills"] == ["pdf", "janitor-repo-research"]
    dirs = after["skills"]["external_dirs"]
    assert f"{ROOT_VAR}/research" in dirs and not any("/agents" in d for d in dirs)
    # This home lists `janitor.skills`, so its external_dirs belong to the catalog
    # (janitor.catalog.apply): the migration must not re-add the whole janitor/skills
    # root. Homes without `janitor.skills` keep it -- see the next test.
    assert str(SKILLS_ROOT) not in dirs

    touched = ("disabled", "platform_disabled", "external_dirs")
    assert {k: v for k, v in after["skills"].items() if k not in touched} == {
        k: v for k, v in before["skills"].items() if k not in touched
    }
    assert {k: v for k, v in after.items() if k not in ("skills", "janitor")} == {
        k: v for k, v in before.items() if k not in ("skills", "janitor")
    }


def test_catalog_is_not_switched_on_for_existing_users(home_v1):
    config = _config(home_v1)
    del config["janitor"]["skills"]
    (home_v1 / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    migrations.run(home_v1, out=_quiet)
    after = _config(home_v1)
    assert "skills" not in after.get("janitor", {})
    assert all(d in after["skills"]["external_dirs"] for d in SKILLS_EXTERNAL_DIRS)


def test_json_string_disabled_list_is_cleaned(home_v1):
    path = home_v1 / "config.yaml"
    config = _config(home_v1)
    config["skills"]["disabled"] = '["janitor-browser", "my-skill"]'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    migrations.run(home_v1, out=_quiet)
    assert _config(home_v1)["skills"]["disabled"] == ["my-skill"]


def test_second_run_is_a_noop(home_v1):
    migrations.run(home_v1, out=_quiet)
    before = _tree(home_v1)
    backups = sorted((home_v1 / ".backup").iterdir())

    assert migrations.run(home_v1, out=_quiet) is None
    assert _tree(home_v1) == before
    assert sorted((home_v1 / ".backup").iterdir()) == backups


def test_dry_run_changes_nothing(home_v1):
    before = _tree(home_v1)
    lines: list[str] = []
    assert migrations.run(home_v1, dry_run=True, out=lines.append) is None
    assert _tree(home_v1) == before
    assert not (home_v1 / ".backup").exists()
    assert read_layout_version(home_v1) == 1
    assert any("remove pristine copy skills/janitor-core" in line for line in lines)


def test_freshly_seeded_home_is_stamped_and_untouched(tmp_path):
    from janitor.seed import ensure_home

    home = tmp_path / ".janitor"
    ensure_home(home)
    assert read_layout_version(home) == LAYOUT_VERSION
    before = _tree(home)

    assert migrations.run(home, out=_quiet) is None
    assert _tree(home) == before
    assert not (home / ".backup").exists()


def test_launcher_hook_upgrades_a_v1_home(home_v1):
    assert migrations.pending(home_v1)
    migrations.auto_migrate(home_v1)
    assert read_layout_version(home_v1) == LAYOUT_VERSION
    assert not (home_v1 / "skills" / "janitor-core").exists()


def test_pre_1_0_home_reaches_v2_in_one_run(tmp_path):
    legacy = build_legacy_home(tmp_path)
    env_before = (legacy.home / ".env").read_bytes()
    backup = migrations.run(legacy.home, out=_quiet)

    skills = legacy.home / "skills"
    for name, rel in LEGACY_SKILL_PATHS.items():
        assert (skills / rel).is_dir() == (name == USER_MODIFIED_SKILL), name
    assert "janitor" in _config(legacy.home)["plugins"]["enabled"]  # the v1 step ran too
    assert [p.name for p in (legacy.home / ".backup").iterdir()] == [backup.name]
    assert (backup / "skills" / "janitor-repo-research-agent" / "SKILL.md").is_file()
    assert (legacy.home / ".env").read_bytes() == env_before
    assert read_layout_version(legacy.home) == LAYOUT_VERSION


def test_links_are_removed_only_when_they_point_at_nothing_or_janitor(home_v1, tmp_path):
    skills = home_v1 / "skills"
    dangling = skills / "janitor-desktop-launcher"
    dangling.symlink_to(tmp_path / "gone" / "janitor-desktop-launcher")
    mine = tmp_path / "my-checkout" / "janitor-browser"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("---\nname: janitor-browser\n---\n", encoding="utf-8")
    outside = skills / "janitor-browser"
    outside.symlink_to(mine)

    migrations.run(home_v1, out=_quiet)

    assert not dangling.is_symlink()
    assert outside.is_symlink() and (mine / "SKILL.md").is_file()


@pytest.mark.linux_only
def test_shell_entry_point(home_v1):
    script = REPO_ROOT / "scripts" / "migrate-janitor-v2.sh"
    env = {**os.environ, "JANITOR_HOME": str(home_v1)}
    before = _tree(home_v1)

    dry = subprocess.run(["bash", str(script), "--dry-run"], capture_output=True, text=True, env=env, timeout=60)
    assert dry.returncode == 0, dry.stderr
    assert "dry run" in dry.stdout and _tree(home_v1) == before

    real = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env, timeout=60)
    assert real.returncode == 0, real.stderr
    assert read_layout_version(home_v1) == LAYOUT_VERSION

    again = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env, timeout=60)
    assert f"already uses layout v{LAYOUT_VERSION}" in again.stdout
