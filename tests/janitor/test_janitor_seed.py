"""``janitor.seed``: a fresh home gets Janitor's identity; a user's home keeps theirs.

Runs the real seed against temp homes and reads the result back through
Hermes' own config loader and skills resolver, the way the backend will.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from janitor import catalog, migrations, seed
from janitor.home import ASSETS_ROOT, LAYOUT_VERSION, REPO_ROOT, SKILLS_ROOT, read_layout_version
from tests.janitor.legacy_home import launcher_env
from tests.janitor.skill_index import ESSENTIAL, skill_index


def _tree(home: Path) -> dict:
    return {
        p.relative_to(home).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(home.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def home(tmp_path):
    return tmp_path / ".janitor"


def _load(home: Path, monkeypatch) -> dict:
    from agent import skill_utils
    from hermes_cli.config import load_config

    monkeypatch.setenv("HERMES_HOME", str(home))
    skill_utils._external_dirs_cache_clear()
    return load_config()


def test_fresh_home_is_a_working_janitor_home(home, monkeypatch):
    from hermes_cli.config import DEFAULT_CONFIG

    changes = seed.ensure_home(home)
    assert changes

    raw = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert raw["_config_version"] == DEFAULT_CONFIG["_config_version"]

    monkeypatch.delenv("JANITOR_SKILLS_ROOT", raising=False)
    config = _load(home, monkeypatch)
    assert "janitor" in config["plugins"]["enabled"]
    assert config["display"]["language"] == "es"
    assert config["display"]["skin"] == "sentry-janitor"
    assert config["memory"].get("provider", "") != "honcho"

    assert (home / "skins" / "sentry-janitor.yaml").read_bytes() == (ASSETS_ROOT / "sentry-janitor.yaml").read_bytes()
    assert (home / "SOUL.md").read_bytes() == (ASSETS_ROOT / "SOUL.md").read_bytes()
    assert (home / seed.NO_BUNDLED_SKILLS_MARKER).is_file()
    assert not (home / "honcho.json").exists()
    assert not (home / ".env").exists()


def test_marker_name_matches_the_skills_sync_contract():
    from tools.skills_sync import NO_BUNDLED_SKILLS_MARKER

    assert seed.NO_BUNDLED_SKILLS_MARKER == NO_BUNDLED_SKILLS_MARKER


def test_seeded_home_is_stamped_with_the_current_layout(home):
    seed.ensure_home(home)
    assert read_layout_version(home) == LAYOUT_VERSION
    assert not migrations.pending(home)


def test_second_run_is_a_noop(home):
    seed.ensure_home(home)
    before = _tree(home)
    assert seed.ensure_home(home) == []
    assert _tree(home) == before


@pytest.mark.parametrize("variant", ["exact", "install_sh_heredoc"])
def test_upstream_default_soul_is_replaced(home, variant):
    from hermes_cli.default_soul import DEFAULT_SOUL_MD

    home.mkdir()
    text = DEFAULT_SOUL_MD if variant == "exact" else DEFAULT_SOUL_MD + "\n"
    (home / "SOUL.md").write_text(text, encoding="utf-8")
    # What install.sh's config stage leaves before janitor.seed runs.
    (home / "config.yaml").write_bytes((REPO_ROOT / "cli-config.yaml.example").read_bytes())

    seed.ensure_home(home)

    assert (home / "SOUL.md").read_bytes() == (ASSETS_ROOT / "SOUL.md").read_bytes()
    config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert "janitor" in config["plugins"]["enabled"]


# ── F2-01: the main agent's skills come from the catalog ─────────────────


def test_fresh_home_index_is_exactly_the_main_template(home, monkeypatch):
    """Not the whole janitor/skills root: only ``main`` + the essential skill."""
    monkeypatch.delenv("JANITOR_SKILLS_ROOT", raising=False)
    seed.ensure_home(home)
    main = catalog.skills_for_template("main")

    index = skill_index(home, monkeypatch)

    assert index == set(main) | {ESSENTIAL}
    shipped = {catalog.read_skill_name(d) for d in SKILLS_ROOT.glob("*/*") if (d / "SKILL.md").is_file()}
    assert shipped - set(main), "the tree ships Janitor skills outside main"
    assert not (shipped - set(main)) & index  # none of them leaks in
    raw = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert raw["janitor"]["skills"] == main
    assert raw["janitor"]["catalog_seen"] == main
    assert all(Path(d).is_absolute() for d in raw["skills"]["external_dirs"])


def test_catalog_apply_on_a_seeded_home_is_a_noop(home):
    seed.ensure_home(home)
    before = (home / "config.yaml").read_bytes()
    result = catalog.apply(home)
    assert result.managed and not result.changed
    assert (home / "config.yaml").read_bytes() == before


def test_upstream_default_soul_is_replaced_in_an_existing_home(home):
    """Upstream's auto-seeded SOUL carries no user intent, even next to a user config."""
    from hermes_cli.default_soul import DEFAULT_SOUL_MD

    home.mkdir()
    (home / "config.yaml").write_text("model:\n  default: my-model\n", encoding="utf-8")
    (home / "SOUL.md").write_text(DEFAULT_SOUL_MD, encoding="utf-8")
    config_before = (home / "config.yaml").read_bytes()

    seed.ensure_home(home)

    assert (home / "SOUL.md").read_bytes() == (ASSETS_ROOT / "SOUL.md").read_bytes()
    assert (home / "config.yaml").read_bytes() == config_before


def test_user_files_are_never_touched(home):
    home.mkdir()
    (home / "skins").mkdir()
    files = {
        "config.yaml": b"model:\n  default: my-model\nmemory:\n  provider: holographic\n",
        "SOUL.md": "Eres mi asistente, y punto.\n".encode("utf-8"),
        ".env": b"MINIMAX_API_KEY=sk-user\n",
        "skins/sentry-janitor.yaml": b"name: sentry-janitor\n# my tweak\n",
    }
    for rel, data in files.items():
        (home / rel).write_bytes(data)

    assert seed.ensure_home(home) == []

    for rel, data in files.items():
        assert (home / rel).read_bytes() == data, rel
    assert not (home / seed.NO_BUNDLED_SKILLS_MARKER).exists()
    assert read_layout_version(home) == 0


def test_env_is_never_modified_on_a_fresh_home(home):
    home.mkdir()
    (home / ".env").write_bytes(b"MINIMAX_API_KEY=sk-test\n# keep me\n")
    seed.ensure_home(home)
    assert (home / ".env").read_bytes() == b"MINIMAX_API_KEY=sk-test\n# keep me\n"


# ── janitor command on PATH ────────────────────────────────────────────────


@pytest.fixture
def venv_script(tmp_path):
    target = tmp_path / "new-venv" / "bin" / "janitor"
    target.parent.mkdir(parents=True)
    target.write_text("#!/bin/sh\n", encoding="utf-8")
    target.chmod(0o755)
    return target


@pytest.mark.linux_only
def test_command_link_is_created_and_idempotent(tmp_path, venv_script):
    link_dir = tmp_path / "bin"
    assert seed.ensure_command_link(link_dir, venv_script) == "created"
    assert os.readlink(link_dir / "janitor") == str(venv_script)
    assert seed.ensure_command_link(link_dir, venv_script) == "unchanged"


@pytest.mark.linux_only
def test_command_link_keeps_the_old_link_without_a_new_target(tmp_path):
    old = tmp_path / "old-venv" / "bin" / "janitor"
    old.parent.mkdir(parents=True)
    old.write_text("#!/bin/sh\n", encoding="utf-8")
    link_dir = tmp_path / "bin"
    link_dir.mkdir()
    (link_dir / "janitor").symlink_to(old)

    result = seed.ensure_command_link(link_dir, tmp_path / "missing" / "janitor")
    assert result.startswith("kept")
    assert os.readlink(link_dir / "janitor") == str(old)


@pytest.mark.linux_only
def test_command_link_leaves_a_foreign_janitor_alone(tmp_path, venv_script):
    link_dir = tmp_path / "bin"
    link_dir.mkdir()
    other = tmp_path / "elsewhere" / "janitor"
    other.parent.mkdir()
    other.write_text("#!/bin/sh\n", encoding="utf-8")
    (link_dir / "janitor").symlink_to(other)
    (tmp_path / "bin2").mkdir()
    (tmp_path / "bin2" / "janitor").write_bytes(b"#!/bin/sh\necho mine\n")

    assert seed.ensure_command_link(link_dir, venv_script).startswith("kept")
    assert os.readlink(link_dir / "janitor") == str(other)
    assert seed.ensure_command_link(tmp_path / "bin2", venv_script).startswith("kept")
    assert (tmp_path / "bin2" / "janitor").read_bytes() == b"#!/bin/sh\necho mine\n"


@pytest.mark.linux_only
def test_command_link_replaces_a_dangling_link(tmp_path, venv_script):
    link_dir = tmp_path / "bin"
    link_dir.mkdir()
    (link_dir / "janitor").symlink_to(tmp_path / "gone" / "janitor")
    assert seed.ensure_command_link(link_dir, venv_script) == "updated"
    assert os.readlink(link_dir / "janitor") == str(venv_script)


def test_command_link_on_windows_touches_nothing(tmp_path, venv_script):
    """Windows gets its command from install.ps1: no symlink, not even the directory."""
    link_dir = tmp_path / "bin"
    result = seed.ensure_command_link(link_dir, venv_script, platform="win32")
    assert result.startswith("kept")
    assert not link_dir.exists()


@pytest.mark.windows_only
def test_command_link_on_a_real_windows_host_touches_nothing(tmp_path, venv_script):
    link_dir = tmp_path / "bin"
    assert seed.ensure_command_link(link_dir, venv_script).startswith("kept")
    assert not link_dir.exists()


# ── the launcher, end to end ───────────────────────────────────────────────


def test_launcher_version_seeds_a_fresh_home(tmp_path):
    """No Honcho credentials anywhere: a fresh seeded home must not trip the
    launcher's Honcho fail-safe (it runs before ``--version`` is handled)."""
    env = launcher_env(tmp_path)
    for key in ("HONCHO_API_KEY", "HONCHO_BASE_URL"):
        env.pop(key, None)
    result = subprocess.run(
        [sys.executable, "-m", "janitor.cli", "--version"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    assert "THE JANITOR v" in result.stdout
    home = tmp_path / ".janitor"
    assert (home / "SOUL.md").read_bytes() == (ASSETS_ROOT / "SOUL.md").read_bytes()
    assert "janitor" in yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))["plugins"]["enabled"]
    assert read_layout_version(home) == LAYOUT_VERSION
    assert not (home / ".backup").exists()
