"""Subprocess tests for ``scripts/migrate-janitor-v0.20.1.sh``.

Subprocess-only: no source reads. Each test drives the script via
``subprocess.run(["bash", str(SCRIPT), *args], env=env, ...)`` against a
temp ``HERMES_HOME``; every subprocess env block sets ``JANITOR_HOME`` to
the empty string so an ambient ``JANITOR_HOME`` from the test harness cannot
skew home-resolution precedence.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate-janitor-v0.20.1.sh"


def test_script_is_present_and_bash_n_clean():
    """The migration script exists and passes bash -n syntax check."""
    assert SCRIPT.exists()
    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_dry_run_does_not_modify_config(tmp_path):
    """--dry-run is idempotent and does NOT modify the source config."""
    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    before = (home / "config.yaml").read_bytes()
    r = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert (home / "config.yaml").read_bytes() == before


def test_creates_timestamped_backup(tmp_path):
    """For-real run creates exactly one timestamped config backup."""
    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    backups = [
        p for p in home.glob("config.yaml.bak.*")
        if len(p.name.split(".", 3)) == 4
        and p.name.split(".", 3)[3].startswith("20")
    ]
    assert len(backups) == 1
    ts = backups[0].name.split(".", 3)[3]
    assert re.match(r"^\d{8}T\d{6}Z$", ts), ts


def test_is_idempotent(tmp_path):
    """Second for-real run on already-migrated config is a no-op (no new backup)."""
    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    env = {**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""}
    subprocess.run(["bash", str(SCRIPT)], env=env, check=True, capture_output=True, text=True)
    first_count = len(list(home.glob("config.yaml.bak.*")))
    r = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    second_count = len(list(home.glob("config.yaml.bak.*")))
    assert second_count == first_count


def test_missing_config_exits_1(tmp_path):
    """No config → exit 1, no backup file."""
    home = tmp_path / "janitor"
    home.mkdir()
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert list(home.glob("config.yaml.bak.*")) == []


def test_v33_content_triggers_migration(tmp_path):
    """A real v33 display.personality value triggers the v34 migration step."""
    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text(
        "_config_version: 33\n"
        "display:\n"
        "  personality: kawaii\n"
        "memory:\n"
        "  provider: honcho\n"
    )
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    import yaml
    after = yaml.safe_load((home / "config.yaml").read_text())
    assert after["_config_version"] == 34
    assert after["display"]["personality"] == ""


def test_manual_prompts_preserved(tmp_path):
    """A free-form agent.system_prompt block survives the migration."""
    home = tmp_path / "janitor"
    home.mkdir()
    custom = (
        "_config_version: 33\n"
        "display:\n"
        "  personality: kawaii\n"
        "agent:\n"
        "  system_prompt: |\n"
        "    Custom prompt the user wrote.\n"
        "    Keep this verbatim across migrations.\n"
        "memory:\n"
        "  provider: honcho\n"
    )
    (home / "config.yaml").write_text(custom)
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    text = (home / "config.yaml").read_text()
    assert "Custom prompt the user wrote." in text
    assert "Keep this verbatim across migrations." in text


def test_janitor_home_precedence_over_hermes_home(tmp_path):
    """$JANITOR_HOME wins over $HERMES_HOME and over $HOME/.janitor."""
    janitor_home = tmp_path / "j"
    hermes_home = tmp_path / "h"
    janitor_home.mkdir()
    hermes_home.mkdir()
    (janitor_home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={
            **os.environ,
            "JANITOR_HOME": str(janitor_home),
            "HERMES_HOME": str(hermes_home),
            "HOME": str(tmp_path),
        },
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert list(janitor_home.glob("config.yaml.bak.*")) != []
    assert list(hermes_home.glob("config.yaml.bak.*")) == []


def test_hermes_home_precedence_over_default_home(tmp_path):
    """$HERMES_HOME wins over $HOME/.janitor when JANITOR_HOME is unset."""
    default_home = tmp_path / "default"
    explicit_home = tmp_path / "explicit"
    (default_home / ".janitor").mkdir(parents=True)
    (default_home / ".janitor" / "config.yaml").write_text("memory:\n  provider: honcho\n")
    explicit_home.mkdir()
    (explicit_home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={
            **os.environ,
            "HERMES_HOME": str(explicit_home),
            "HOME": str(default_home),
            "JANITOR_HOME": "",
        },
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert list(explicit_home.glob("config.yaml.bak.*")) != []
    assert list((default_home / ".janitor").glob("config.yaml.bak.*")) == []


def test_prints_raw_and_display_version(tmp_path):
    """Stdout includes both raw and display versions on success."""
    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "Raw version: 0.20.1+janitor.1" in r.stdout
    assert "Display version: 0.20.1-janitor.1" in r.stdout


def test_prints_rollback_instructions(tmp_path):
    """Stdout prints rollback instructions referencing the actual backup filename."""
    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "To rollback:" in r.stdout
    backups = list(home.glob("config.yaml.bak.*"))
    assert str(backups[0].name) in r.stdout


def test_migration_failure_after_backup_exits_3_and_preserves_original(tmp_path):
    """Malformed v33 YAML is backed up before migration fails with exit 3."""
    home = tmp_path / "janitor"
    home.mkdir()
    original = "_config_version: 33\ndisplay:\n  personality: kawaii\nmemory: {{ invalid yaml\n"
    (home / "config.yaml").write_text(original)
    before_bytes = (home / "config.yaml").read_bytes()
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    backups = list(home.glob("config.yaml.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before_bytes
    assert (home / "config.yaml").read_bytes() == before_bytes