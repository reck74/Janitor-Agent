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
import sys
import types
from pathlib import Path

import pytest


# The entire module drives scripts/migrate-janitor-v0.20.1.sh — a POSIX
# install-path script whose documented Windows runtime is WSL2 (README),
# not native Git Bash. Python-level migration behavior is covered on all
# platforms by tests/test_janitor_update_core.py.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="drives the POSIX migration script; Windows runtime is WSL2",
)


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
    assert re.match(r"^\d{8}T\d{6}(Z|\d{3}Z|\d{6}Z|\d{9}Z)$", ts), ts


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
    """A free-form agent.system_prompt block survives the migration.

    Extended for Finding 6 (idempotency): the test runs the script TWICE
    on a config that has a preserved ``agent.system_prompt`` block. A raw
    ``_config_version: 34`` stamp is authoritative: the second run is a
    no-op and does NOT create a new timestamped backup. We also assert the
    backup filename shape explicitly so a timestamp collision cannot hide
    a regression.
    """
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
    env = {**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""}

    r = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    text = (home / "config.yaml").read_text()
    assert "Custom prompt the user wrote." in text
    assert "Keep this verbatim across migrations." in text

    backups_after_first = sorted(home.glob("config.yaml.bak.*"))
    assert len(backups_after_first) == 1, (
        f"first run must create exactly one backup, found {len(backups_after_first)}"
    )
    first_ts = backups_after_first[0].name.split(".", 3)[3]
    assert re.match(r"^\d{8}T\d{6}(Z|\d{3}Z|\d{6}Z|\d{9}Z)$", first_ts), first_ts

    # Second run: raw _config_version is now 34 (stamped by migration), so
    # even with a preserved agent.system_prompt block, the script must be a
    # no-op and not create a new backup.
    r2 = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True,
    )
    assert r2.returncode == 0, r2.stderr
    backups_after_second = sorted(home.glob("config.yaml.bak.*"))
    assert len(backups_after_second) == len(backups_after_first), (
        f"second run must not create a new backup; "
        f"before={backups_after_first!r} after={backups_after_second!r}"
    )
    # The preserved block must still survive the second run.
    text2 = (home / "config.yaml").read_text()
    assert "Custom prompt the user wrote." in text2
    assert "Keep this verbatim across migrations." in text2


def test_unknown_arg_exits_2_no_backup_no_mutation(tmp_path):
    """Unknown args print usage to stderr and exit 2 — NO backup, NO mutation."""
    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    before = (home / "config.yaml").read_bytes()
    r = subprocess.run(
        ["bash", str(SCRIPT), "--bogus"],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert list(home.glob("config.yaml.bak.*")) == []
    assert (home / "config.yaml").read_bytes() == before
    assert "Usage" in r.stderr or "usage" in r.stderr or "unknown" in r.stderr.lower()


def test_extra_args_after_dry_run_exits_2_no_backup_no_mutation(tmp_path):
    """Extra positional args after --dry-run also exit 2 — NO backup, NO mutation."""
    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    before = (home / "config.yaml").read_bytes()
    r = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--also-bogus"],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert list(home.glob("config.yaml.bak.*")) == []
    assert (home / "config.yaml").read_bytes() == before


def test_no_args_runs_normally(tmp_path):
    """Exactly zero positional args runs the script normally (no usage error)."""
    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


def test_prints_raw_and_display_version(tmp_path):
    """Stdout includes both raw and display versions on success.

    Round 2/5 strengthening: expected values are derived DIRECTLY from
    the canonical APIs (``hermes_cli.__version__`` import, NOT
    source-reading of ``hermes_cli/__init__.py``).
    """
    import hermes_cli
    import janitor_version

    raw = hermes_cli.__version__
    display = janitor_version.display_version(raw)

    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert f"Raw version: {raw}" in r.stdout
    assert f"Display version: {display}" in r.stdout


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


# ---------------------------------------------------------------------------
# Fix Round 2/5 — Oracle re-review regression tests for the script.
# ---------------------------------------------------------------------------


def test_backup_filename_strict_portable_shape_no_nanoseconds(tmp_path):
    """Round 2/5 Oracle finding: restore the exact portable backup
    name ``config.yaml.bak.<YYYYMMDDTHHMMSSZ>``. Nanoseconds violate the
    required shape and are removed. Uniqueness is achieved WITHOUT
    nanoseconds (the migrate-once-then-idempotent contract means only
    one backup per migration run, and the test uses a fresh tmp_path).
    """
    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    backups = list(home.glob("config.yaml.bak.*"))
    assert len(backups) == 1
    name = backups[0].name
    # Exact portable shape: ``config.yaml.bak.<YYYYMMDDTHHMMSSZ>``
    # has exactly four dot-separated tokens; the last is the timestamp.
    parts = name.split(".")
    assert len(parts) == 4, f"expected 4 dot-separated tokens, got {parts!r}"
    assert parts[:3] == ["config", "yaml", "bak"], (parts, name)
    ts = parts[3]
    assert re.match(r"^\d{8}T\d{6}Z$", ts), (
        f"timestamp portion must be exactly YYYYMMDDTHHMMSSZ; got {ts!r}"
    )
    # No nanoseconds / microseconds / millisecond suffixes anywhere.
    assert not re.search(r"\.\d+Z$", name), name


def test_script_uses_canonical_hermes_cli_version_import(tmp_path):
    """Round 2/5 Oracle finding C8: the script MUST source its raw
    version from a direct ``import hermes_cli`` + ``print(hermes_cli.__version__)``
    call AND derive display via ``janitor_version.display_version``.
    The script is observable here: we read its stdout and assert the
    emitted values MATCH the canonical ``hermes_cli.__version__`` /
    ``display_version(__version__)`` pair from the SAME Python
    interpreter the script uses. If the script ever falls back to
    source-reading (the prior ``Path(spec.origin).read_text() + re.search``
    pattern), it would only happen to match the canonical value if the
    source string is byte-identical to ``hermes_cli.__version__`` at that
    moment — any drift between the two paths would surface as a
    contract violation.
    """
    import hermes_cli
    import janitor_version

    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text(
        "_config_version: 99\nmemory:\n  provider: honcho\n"
    )

    r = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"],
        env={
            **os.environ,
            "HERMES_HOME": str(home),
            "JANITOR_HOME": "",
        },
        capture_output=True,
        text=True,
    )

    # Canonical values, derived exactly the way the script must derive them.
    expected_raw = hermes_cli.__version__
    expected_display = janitor_version.display_version(expected_raw)

    assert f"Raw version: {expected_raw}" in r.stdout, (
        f"script's raw version must come from hermes_cli.__version__; "
        f"expected {expected_raw!r}, stdout={r.stdout!r}"
    )
    assert f"Display version: {expected_display}" in r.stdout, (
        f"script's display version must come from "
        f"janitor_version.display_version; expected {expected_display!r}, "
        f"stdout={r.stdout!r}"
    )


def importlib_origin():
    """Return the hermes_cli package __init__.py path for the sentinel."""
    import importlib.util
    spec = importlib.util.find_spec("hermes_cli")
    assert spec is not None and spec.origin is not None
    return Path(spec.origin)


def test_post_check_failure_message_is_truthful_about_config_state(tmp_path):
    """Round 2/5 Oracle finding: a successful happy-path run MUST NOT
    emit the ``"byte-identical to backup"`` recovery message — that
    message is reserved for the strict-parse failure path where the
    config genuinely was not mutated. On exit 0 the live config WAS
    migrated and so cannot be byte-identical to its pre-migration
    backup.
    """
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
    assert r.returncode == 0
    combined = r.stdout + r.stderr
    assert "byte-identical" not in combined, (
        "the byte-identical recovery message must not appear on the "
        "exit-0 happy path; the migrate step has mutated the config"
    )


# ---------------------------------------------------------------------------
# Fix Round 3/5 — Oracle re-review regression tests (shell parity)
# ---------------------------------------------------------------------------


def test_real_pre_floor_config_is_allowed_to_remain_behind(tmp_path):
    """The real shell path permits the canonical support-floor refusal."""
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    from hermes_cli.config_migrations import SUPPORT_FLOOR_VERSION

    # Given an explicit on-disk schema immediately below the real floor.
    pre_floor_version = SUPPORT_FLOOR_VERSION - 1
    latest_version = DEFAULT_CONFIG["_config_version"]
    home = tmp_path / "janitor"
    home.mkdir()
    config = home / "config.yaml"
    config.write_text(
        f"_config_version: {pre_floor_version}\n"
        "memory:\n"
        "  provider: honcho\n"
    )
    before = config.read_bytes()

    # When the actual script invokes the repository's real fresh wrappers.
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HERMES_HOME": str(home), "JANITOR_HOME": ""},
        capture_output=True,
        text=True,
    )

    # Then the supported refusal exits zero while remaining visibly behind.
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert f"v{pre_floor_version}" in result.stdout
    assert f"v{latest_version}" in result.stdout
    assert config.read_bytes() == before
    backups = list(home.glob("config.yaml.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before


def test_script_imports_repository_modules_from_hostile_outside_cwd(tmp_path):
    """Caller cwd and ambient PYTHONPATH cannot shadow repository imports."""
    import hermes_cli
    import janitor_version

    repo_raw = hermes_cli.__version__
    repo_display = janitor_version.display_version(repo_raw)

    # Given conflicting modules in both the outside cwd and ambient path.
    outside_cwd = tmp_path / "outside-cwd"
    cwd_hermes_cli = outside_cwd / "hermes_cli"
    cwd_hermes_cli.mkdir(parents=True)
    cwd_raw = "9.99.99+cwd-conflict"
    cwd_display = "9.99.99-cwd-display-conflict"
    (cwd_hermes_cli / "__init__.py").write_text(
        f"__version__ = {cwd_raw!r}\n"
    )
    (outside_cwd / "janitor_version.py").write_text(
        "def display_version(raw_version):\n"
        f"    return {cwd_display!r}\n"
    )

    ambient = tmp_path / "ambient-pythonpath"
    ambient_hermes_cli = ambient / "hermes_cli"
    ambient_hermes_cli.mkdir(parents=True)
    ambient_raw = "8.88.88+ambient-conflict"
    ambient_display = "8.88.88-ambient-display-conflict"
    (ambient_hermes_cli / "__init__.py").write_text(
        f"__version__ = {ambient_raw!r}\n"
    )
    (ambient / "janitor_version.py").write_text(
        "def display_version(raw_version):\n"
        f"    return {ambient_display!r}\n"
    )

    home = tmp_path / "janitor"
    home.mkdir()
    (home / "config.yaml").write_text(
        "_config_version: 99\nmemory:\n  provider: honcho\n"
    )

    # When the script is launched from the hostile directory.
    result = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"],
        cwd=outside_cwd,
        env={
            **os.environ,
            "HERMES_HOME": str(home),
            "JANITOR_HOME": "",
            "PYTHONPATH": str(ambient),
        },
        capture_output=True,
        text=True,
    )

    # Then only repository canonical values are observable.
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert f"Raw version: {repo_raw}" in result.stdout
    assert f"Display version: {repo_display}" in result.stdout
    for conflicting_value in (
        cwd_raw,
        cwd_display,
        ambient_raw,
        ambient_display,
    ):
        assert conflicting_value not in result.stdout
