"""Layout v1 migration of ~/.janitor (``janitor/migrations``), on a real pre-1.0 home."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from janitor import migrations
from janitor.home import LAYOUT_VERSION, read_layout_version
from janitor.migrations import v1
from tests.janitor.legacy_home import (
    ASSETS,
    LEGACY_SKILL_PATHS,
    REPO_ROOT,
    USER_MODIFIED_SKILL,
    USER_OWN_SKILL,
    build_legacy_home,
    session_messages,
    snapshot_user_data,
)

PRISTINE = [name for name in LEGACY_SKILL_PATHS if name != USER_MODIFIED_SKILL]


def _tree(home: Path) -> dict:
    return {
        p.relative_to(home).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(home.rglob("*"))
        if p.is_file()
    }


def _quiet(_line: str) -> None:
    pass


@pytest.fixture
def legacy(tmp_path):
    return build_legacy_home(tmp_path)


def test_dry_run_writes_nothing(legacy):
    before = _tree(legacy.home)
    lines: list[str] = []
    assert migrations.run(legacy.home, dry_run=True, out=lines.append) is None
    assert _tree(legacy.home) == before
    assert any("plugins.enabled" in line for line in lines)
    assert read_layout_version(legacy.home) == 0


def test_migration_moves_home_to_layout_v1(legacy):
    messages = session_messages(legacy.home)
    backup = migrations.run(legacy.home, out=_quiet)

    config = yaml.safe_load((legacy.home / "config.yaml").read_text(encoding="utf-8"))
    for entry in v1.EXTERNAL_DIRS:
        assert entry in config["skills"]["external_dirs"]
    assert "janitor" in config["plugins"]["enabled"]

    skills = legacy.home / "skills"
    for name in PRISTINE:
        assert not (skills / LEGACY_SKILL_PATHS[name]).exists(), name
    assert not (skills / "devops").exists(), "emptied category dir left behind"
    assert (skills / LEGACY_SKILL_PATHS[USER_MODIFIED_SKILL]).is_dir()
    assert (skills / USER_OWN_SKILL).is_dir()
    manifest = (skills / ".bundled_manifest").read_text(encoding="utf-8")
    assert [line.split(":")[0] for line in manifest.split()] == [USER_MODIFIED_SKILL]

    after = snapshot_user_data(legacy.home)
    assert {k: v for k, v in legacy.user_data.items() if after.get(k) != v} == {}
    assert session_messages(legacy.home) == messages
    assert read_layout_version(legacy.home) == LAYOUT_VERSION

    assert backup is not None and backup.parent == legacy.home / ".backup"
    for name in LEGACY_SKILL_PATHS:
        assert (backup / "skills" / LEGACY_SKILL_PATHS[name] / "SKILL.md").is_file()
    assert "plugins" not in yaml.safe_load((backup / "config.yaml").read_text(encoding="utf-8"))
    with sqlite3.connect(backup / "state.db") as conn:
        assert conn.execute("SELECT count(*) FROM messages").fetchone()[0] == len(messages)


def test_second_run_is_a_noop(legacy):
    migrations.run(legacy.home, out=_quiet)
    before = _tree(legacy.home)
    backups = sorted((legacy.home / ".backup").iterdir())

    assert migrations.run(legacy.home, out=_quiet) is None
    assert _tree(legacy.home) == before
    assert sorted((legacy.home / ".backup").iterdir()) == backups


def test_seeded_1_0_home_needs_no_backup(tmp_path):
    home = tmp_path / ".janitor"
    (home / "skins").mkdir(parents=True)
    shutil.copy2(ASSETS / "config.yaml", home / "config.yaml")
    shutil.copy2(ASSETS / "sentry-janitor.yaml", home / "skins" / "sentry-janitor.yaml")

    assert migrations.run(home, out=_quiet) is None
    assert not (home / ".backup").exists()
    assert read_layout_version(home) == LAYOUT_VERSION


def test_user_disabled_plugin_stays_disabled(legacy):
    path = legacy.home / "config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["plugins"] = {"disabled": ["janitor"]}
    path.write_text(yaml.safe_dump(config), encoding="utf-8")

    migrations.run(legacy.home, out=_quiet)
    plugins = yaml.safe_load(path.read_text(encoding="utf-8"))["plugins"]
    assert "janitor" not in (plugins.get("enabled") or [])


def test_bytecode_cache_does_not_mark_a_copy_as_edited(legacy):
    name = PRISTINE[0]
    copy = legacy.home / "skills" / LEGACY_SKILL_PATHS[name]
    cache = copy / "scripts" / "__pycache__"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "helper.cpython-311.pyc").write_bytes(b"\x00bytecode")

    migrations.run(legacy.home, out=_quiet)

    assert not copy.exists()


def test_hub_installed_copy_is_left_alone(legacy):
    hub = legacy.home / "skills" / ".hub"
    hub.mkdir()
    name = PRISTINE[0]
    (hub / "lock.json").write_text(json.dumps({"version": 1, "installed": {name: {}}}), encoding="utf-8")

    migrations.run(legacy.home, out=_quiet)
    assert (legacy.home / "skills" / LEGACY_SKILL_PATHS[name]).is_dir()


@pytest.mark.parametrize(
    "edited, newline", [(False, "\n"), (False, "\r\n"), (True, "\n")], ids=["shipped", "shipped-crlf", "edited"]
)
def test_skin_refreshed_only_when_unmodified(legacy, monkeypatch, edited, newline):
    skin = legacy.home / "skins" / v1.SKIN_FILE
    old = "name: sentry-janitor\ncolors: {}\n"
    monkeypatch.setattr(v1, "SHIPPED_SKIN_SHA256", frozenset({hashlib.sha256(old.encode()).hexdigest()}))
    skin.write_bytes((old + ("# mine\n" if edited else "")).replace("\n", newline).encode())
    before = skin.read_bytes()

    migrations.run(legacy.home, out=_quiet)
    expected = before if edited else (ASSETS / v1.SKIN_FILE).read_bytes()
    assert skin.read_bytes() == expected


def test_manifest_hash_matches_bundled_sync(tmp_path):
    from tools.skills_sync import _dir_hash

    cached = tmp_path / "cached-skill"
    (cached / "scripts" / "__pycache__").mkdir(parents=True)
    (cached / "SKILL.md").write_text("---\nname: cached-skill\n---\n")
    (cached / "scripts" / "run.py").write_text("print('hi')\n")
    (cached / "scripts" / "__pycache__" / "run.cpython-311.pyc").write_bytes(b"\x00bytecode")

    for skill_dir in [*v1.shipped_skills().values(), cached]:
        for legacy in (False, True):
            assert v1.dir_hash(skill_dir, include_runtime_cache=legacy) == _dir_hash(
                skill_dir, include_runtime_cache=legacy
            ), (skill_dir, legacy)
    assert v1.dir_hash(cached) != v1.dir_hash(cached, include_runtime_cache=True)


def test_auto_migrate_never_blocks_startup(legacy, monkeypatch, capsys):
    def _boom(_home):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(v1, "build_plan", _boom)
    migrations.auto_migrate(legacy.home)

    assert "disk on fire" in capsys.readouterr().err
    assert read_layout_version(legacy.home) == 0


def test_module_cli_dry_run(legacy):
    before = _tree(legacy.home)
    result = subprocess.run(
        [sys.executable, "-m", "janitor.migrations", "--dry-run", "--home", str(legacy.home)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "dry run" in result.stdout
    assert _tree(legacy.home) == before


@pytest.mark.linux_only
def test_shell_entry_point_migrates(legacy):
    script = REPO_ROOT / "scripts" / "migrate-janitor-v1.sh"
    env = {**os.environ, "JANITOR_HOME": str(legacy.home)}

    dry = subprocess.run(["bash", str(script), "--dry-run"], capture_output=True, text=True, env=env, timeout=60)
    assert dry.returncode == 0, dry.stderr
    assert read_layout_version(legacy.home) == 0

    real = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env, timeout=60)
    assert real.returncode == 0, real.stderr
    assert read_layout_version(legacy.home) == LAYOUT_VERSION

    bad = subprocess.run(["bash", str(script), "--force"], capture_output=True, text=True, env=env, timeout=60)
    assert bad.returncode == 2


@pytest.mark.linux_only
def test_rerunning_installer_keeps_existing_home(legacy):
    keep = ("config.yaml", "SOUL.md", "honcho.json", "skins/sentry-janitor.yaml")
    for rel in keep:
        path = legacy.home / rel
        path.write_text(path.read_text(encoding="utf-8") + "\n# user edit\n", encoding="utf-8")
    before = {rel: (legacy.home / rel).read_bytes() for rel in keep}
    old_env = (legacy.home / ".env").read_bytes()

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "janitor-install.sh")],
        input="sk-openai-new\nsk-minimax-new\n3\n\n",
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(legacy.root), "JANITOR_HOME": str(legacy.home)},
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    assert {rel: (legacy.home / rel).read_bytes() for rel in keep} == before
    assert "MINIMAX_API_KEY=sk-minimax-new" in (legacy.home / ".env").read_text(encoding="utf-8")
    backups = list((legacy.home / ".backup").glob("install-*/.env"))
    assert [b.read_bytes() for b in backups] == [old_env]
