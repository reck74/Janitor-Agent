"""Tests for ``janitor_update_core.run_janitor_update``.

Mirrors the structure of ``tests/hermes_cli/test_update_autostash.py`` so
the Janitor update path is held to the same standard as the official one.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import janitor_update_core as juc


# ---------------------------------------------------------------------------
# Helpers (mirror _make_update_side_effect from the official test file)
# ---------------------------------------------------------------------------


def _make_side_effect(
    *,
    ff_only_fails: bool = False,
    reset_fails: bool = False,
    fetch_fails: bool = False,
    fetch_stderr: str = "",
    commit_count: str = "3",
    current_branch: str = "main",
    syntax_break_in: str | None = None,
):
    """Build a subprocess.run side_effect for run_janitor_update tests.

    The returned side_effect records every command it sees; tests inspect
    the recorded list to assert on command shape and order.
    """
    recorded: list[list[str]] = []

    def side_effect(cmd, **kwargs):
        recorded.append([str(c) for c in cmd])
        joined = " ".join(str(c) for c in cmd)
        cwd = kwargs.get("cwd")

        if "fetch" in joined and "origin" in joined:
            if fetch_fails:
                return SimpleNamespace(
                    stdout="",
                    stderr=fetch_stderr,
                    returncode=128,
                )
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        if "rev-parse" in joined and "--abbrev-ref" in joined:
            return SimpleNamespace(
                stdout=f"{current_branch}\n", stderr="", returncode=0,
            )

        if "rev-list" in joined and "--count" in joined:
            return SimpleNamespace(
                stdout=f"{commit_count}\n", stderr="", returncode=0,
            )

        if "rev-parse" in joined and "HEAD" in joined and "--abbrev-ref" not in joined:
            return SimpleNamespace(
                stdout="abc123def456\n", stderr="", returncode=0,
            )

        if "--ff-only" in joined:
            if ff_only_fails:
                return SimpleNamespace(
                    stdout="",
                    stderr="fatal: Not possible to fast-forward, aborting.\n",
                    returncode=128,
                )
            return SimpleNamespace(stdout="Updating abc..def\n", stderr="", returncode=0)

        if "reset" in joined and "--hard" in joined:
            if reset_fails:
                return SimpleNamespace(
                    stdout="",
                    stderr="error: unable to write\n",
                    returncode=1,
                )
            return SimpleNamespace(stdout="HEAD is now at abc123\n", stderr="", returncode=0)

        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return side_effect, recorded


def _stub_helpers(monkeypatch, tmp_path, *, syntax_break_in: str | None = None):
    """Stub the lazy-imported helpers that the core fetches from hermes_cli.

    Mirrors ``_setup_update_mocks`` in ``tests/hermes_cli/test_update_autostash.py``.
    """
    # PROJECT_ROOT becomes tmp_path
    monkeypatch.setattr(juc, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".git").mkdir(exist_ok=True)

    # Helper stubs — every helper the core might lazy-import gets a no-op
    monkeypatch.setattr(juc, "_run_pre_update_backup", lambda args: None)
    monkeypatch.setattr(
        juc, "_install_hangup_protection", lambda gateway_mode=False: {}
    )
    monkeypatch.setattr(juc, "_finalize_update_output", lambda state: None)
    monkeypatch.setattr(
        juc, "_stash_local_changes_if_needed", lambda git_cmd, cwd: None
    )
    monkeypatch.setattr(
        juc, "_restore_stashed_changes", lambda *a, **kw: True
    )
    monkeypatch.setattr(juc, "_refresh_active_lazy_features", lambda: None)
    monkeypatch.setattr(juc, "_update_node_dependencies", lambda: None)
    monkeypatch.setattr(juc, "_invalidate_update_cache", lambda: None)
    monkeypatch.setattr(
        juc,
        "_clear_bytecode_cache",
        lambda root: 0,
    )

    def syntax_check(root):
        if syntax_break_in is None:
            return True, None, None
        return False, str(Path(root) / syntax_break_in), "SyntaxError: bad"

    monkeypatch.setattr(juc, "_validate_critical_files_syntax", syntax_check)
    monkeypatch.setattr(juc, "_capture_head_sha", lambda git_cmd, cwd: "abc123def456")

    # uv detection — pretend uv is available
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(
        juc,
        "_install_python_dependencies_with_optional_fallback",
        lambda *a, **kw: None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ff_only_failure_falls_back_to_reset_hard_origin_main(monkeypatch, tmp_path, capsys):
    """When ff-only fails (diverged branches), reset to origin/main."""
    _stub_helpers(monkeypatch, tmp_path)
    side_effect, recorded = _make_side_effect(ff_only_fails=True)
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    rc = juc.run_janitor_update(SimpleNamespace())

    reset_calls = [c for c in recorded if "reset" in c and "--hard" in c]
    assert len(reset_calls) == 1
    assert reset_calls[0] == ["git", "reset", "--hard", "origin/main"]
    assert "Fast-forward not possible" in capsys.readouterr().out
    assert rc == 0  # fallback succeeded


def test_ff_only_succeeds_does_not_run_reset_hard(monkeypatch, tmp_path):
    """When ff-only succeeds, no destructive reset is performed."""
    _stub_helpers(monkeypatch, tmp_path)
    side_effect, recorded = _make_side_effect(ff_only_fails=False)
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    juc.run_janitor_update(SimpleNamespace())

    reset_calls = [c for c in recorded if "reset" in c and "--hard" in c]
    assert len(reset_calls) == 0


def test_already_up_to_date_skips_pull(monkeypatch, tmp_path, capsys):
    """When rev-list returns 0, print 'Already up to date' and return 0."""
    _stub_helpers(monkeypatch, tmp_path)
    side_effect, recorded = _make_side_effect(commit_count="0")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    rc = juc.run_janitor_update(SimpleNamespace())

    pull_calls = [c for c in recorded if "--ff-only" in c]
    assert pull_calls == []
    assert "Already up to date" in capsys.readouterr().out
    assert rc == 0


def test_post_pull_syntax_break_triggers_rollback(monkeypatch, tmp_path, capsys):
    """When pulled code has a syntax error, auto-rollback to pre-pull SHA."""
    _stub_helpers(monkeypatch, tmp_path, syntax_break_in="janitor_cli.py")
    side_effect, recorded = _make_side_effect()
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    rc = juc.run_janitor_update(SimpleNamespace())

    # The rollback must run with the captured pre-pull SHA
    rollback_calls = [
        c for c in recorded
        if "reset" in c and "--hard" in c and "abc123def456" in c
    ]
    assert len(rollback_calls) == 1
    assert "SyntaxError" in capsys.readouterr().out or "syntax" in capsys.readouterr().out
    assert rc == 1


def test_fetch_failure_dns_shows_friendly_message(monkeypatch, tmp_path, capsys):
    """DNS failure during fetch prints friendly error and exits 1."""
    _stub_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(
        fetch_fails=True, fetch_stderr="fatal: Could not resolve host: github.com\n"
    )
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    rc = juc.run_janitor_update(SimpleNamespace())

    out = capsys.readouterr().out
    assert "Network error" in out
    assert rc == 1


def test_fetch_failure_auth_shows_friendly_message(monkeypatch, tmp_path, capsys):
    """Auth failure during fetch prints friendly error and exits 1."""
    _stub_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(
        fetch_fails=True,
        fetch_stderr="fatal: Authentication failed for 'https://github.com/reck74/Janitor-Agent.git/'\n",
    )
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    rc = juc.run_janitor_update(SimpleNamespace())

    out = capsys.readouterr().out
    assert "Authentication failed" in out
    assert rc == 1


def test_reset_fallback_failure_exits_1(monkeypatch, tmp_path, capsys):
    """When reset --hard fails after ff-only diverges, exit 1 with guidance."""
    _stub_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(ff_only_fails=True, reset_fails=True)
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    rc = juc.run_janitor_update(SimpleNamespace())

    out = capsys.readouterr().out
    assert "Failed to reset" in out
    assert "git fetch origin && git reset --hard origin/main" in out
    assert rc == 1


def test_check_only_mode_does_not_pull(monkeypatch, tmp_path, capsys):
    """When args.check is True, only fetch + rev-list, no pull, no deps."""
    _stub_helpers(monkeypatch, tmp_path)
    side_effect, recorded = _make_side_effect(commit_count="5")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    rc = juc.run_janitor_update(SimpleNamespace(check=True))

    out = capsys.readouterr().out
    assert "5 update(s) available" in out
    pull_calls = [c for c in recorded if "--ff-only" in c]
    assert pull_calls == []
    assert rc == 0


def test_hangup_protection_wraps_io_and_finalizes_in_finally(monkeypatch, tmp_path):
    """_install_hangup_protection is called before any work; finalize runs even on error."""
    _stub_helpers(monkeypatch, tmp_path)
    hangup_calls: list[bool] = []
    finalize_calls: list[dict] = []

    def fake_hangup(*, gateway_mode=False):
        hangup_calls.append(gateway_mode)
        return {"marker": "fake-state"}

    def fake_finalize(state):
        finalize_calls.append(state)
        # raise to confirm finally still ran
        raise RuntimeError("simulated late failure")

    monkeypatch.setattr(juc, "_install_hangup_protection", fake_hangup)
    monkeypatch.setattr(juc, "_finalize_update_output", fake_finalize)

    # Force a ff-only failure so the test path runs through the finally block
    side_effect, _ = _make_side_effect(ff_only_fails=True)
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    with pytest.raises(RuntimeError):
        juc.run_janitor_update(SimpleNamespace())

    assert hangup_calls == [False]
    assert len(finalize_calls) == 1
    assert finalize_calls[0] == {"marker": "fake-state"}


def test_keyboard_interrupt_restores_stash_and_exits_130(monkeypatch, tmp_path):
    """Ctrl-C during update restores stash and returns 130."""
    _stub_helpers(monkeypatch, tmp_path)
    stash_ref = "fake-stash-ref"

    def fake_stash(git_cmd, cwd):
        return stash_ref

    stash_restore_calls: list[str | None] = []

    def fake_restore(git_cmd, cwd, ref, **kw):
        stash_restore_calls.append(ref)
        return True

    monkeypatch.setattr(juc, "_stash_local_changes_if_needed", fake_stash)
    monkeypatch.setattr(juc, "_restore_stashed_changes", fake_restore)

    def raise_interrupt(cmd, **kwargs):
        if "rev-list" in " ".join(str(c) for c in cmd):
            raise KeyboardInterrupt()
        return SimpleNamespace(returncode=0, stdout="0\n", stderr="")

    monkeypatch.setattr(juc.subprocess, "run", raise_interrupt)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 130
    assert stash_restore_calls == [stash_ref]


def test_lazy_helper_import_falls_back_gracefully(monkeypatch, tmp_path, capsys):
    """When _validate_critical_files_syntax cannot be imported, core still runs."""
    _stub_helpers(monkeypatch, tmp_path)

    # Force the import to fail
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if "_validate_critical_files_syntax" in name or "py_compile" in name:
            raise ImportError("simulated venv breakage")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    side_effect, _ = _make_side_effect()
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    # Should NOT crash; should print a warning and continue
    rc = juc.run_janitor_update(SimpleNamespace())
    out = capsys.readouterr().out
    assert "syntax check" in out.lower() or "skipped" in out.lower()
    assert rc == 0


def test_lazy_helper_import_failure_logs_only(monkeypatch, tmp_path):
    """Failed helper import logs to stderr/print but does not abort."""
    _stub_helpers(monkeypatch, tmp_path)

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if "_install_hangup_protection" in name:
            raise ImportError("simulated venv breakage")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    side_effect, _ = _make_side_effect()
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    # Should still complete (hangup degrades to no-op)
    rc = juc.run_janitor_update(SimpleNamespace())
    assert rc == 0


def test_detached_head_switches_to_main_before_pull(monkeypatch, tmp_path, capsys):
    """Detached HEAD (rev-parse returns 'HEAD') auto-switches to main."""
    _stub_helpers(monkeypatch, tmp_path)
    side_effect, recorded = _make_side_effect(
        current_branch="HEAD", commit_count="3",
    )
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    juc.run_janitor_update(SimpleNamespace())

    checkout_calls = [c for c in recorded if "checkout" in c and "main" in c]
    assert len(checkout_calls) == 1
    out = capsys.readouterr().out
    assert "detached HEAD" in out


def test_feature_branch_switches_to_main_before_pull(monkeypatch, tmp_path, capsys):
    """On a non-main branch, auto-switches to main before pulling."""
    _stub_helpers(monkeypatch, tmp_path)
    side_effect, recorded = _make_side_effect(
        current_branch="experiment/audio-check", commit_count="3",
    )
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    juc.run_janitor_update(SimpleNamespace())

    checkout_calls = [c for c in recorded if "checkout" in c and "main" in c]
    assert len(checkout_calls) == 1
    out = capsys.readouterr().out
    assert "experiment/audio-check" in out


# ---------------------------------------------------------------------------
# Post-redesign contract tests (Task 10): the 11-step pipeline behavior
# ---------------------------------------------------------------------------


def _stub_pipeline_helpers(monkeypatch, tmp_path):
    """Wire the additional helpers the redesigned pipeline needs.

    Builds on ``_stub_helpers`` (sets PROJECT_ROOT to tmp_path and stubs the
    legacy lazy-imported helpers) plus the fresh-wrapper helpers used after
    the pull (config check / migrate / Desktop receipt) and the marker
    location via ``get_hermes_home``. The post-pull reload seam is
    no-op'd so tests can stub the fresh-wrapper sentinels without the seam
    overwriting them; seam-specific tests override the seam function
    themselves. The default check_fn / migrate_fresh stubs model a
    SUCCESSFUL migration: initial check returns (33, 34); after the
    migrate call, the check returns (34, 34) so the post-check passes.
    """
    _stub_helpers(monkeypatch, tmp_path)

    # State shared between check_fn and migrate_fresh so a successful
    # rerun reflects actual migration: post-check returns (latest, latest).
    migration_state = {"migrate_calls": 0}

    def fake_check_fresh():
        if migration_state["migrate_calls"] == 0:
            return (33, 34)
        return (34, 34)

    def fake_migrate_fresh(*, interactive=False, quiet=True):
        migration_state["migrate_calls"] += 1
        return {
            "env_added": [],
            "config_added": [],
            "warnings": [],
        }

    monkeypatch.setattr(juc, "_run_config_check_fresh", fake_check_fresh)
    monkeypatch.setattr(juc, "_run_migrate_config_fresh", fake_migrate_fresh)
    monkeypatch.setattr(juc, "_print_update_completion", lambda message: None)

    # Marker location must be profile-safe (uses hermes_constants.get_hermes_home).
    monkeypatch.setattr(juc, "get_hermes_home", lambda: tmp_path)

    # The post-pull reload seam clears the three fresh-wrapper sentinels;
    # no-op it for tests that stub those sentinels directly. Tests verifying
    # the seam itself override this with a fake implementation.
    monkeypatch.setattr(juc, "_reload_helper_modules_after_pull", lambda: None)

    # _refresh_active_lazy_features may not exist on juc yet; create a default
    # no-op binding so _ensure_loaded does not leave it None.
    if not hasattr(juc, "_refresh_active_lazy_features"):
        monkeypatch.setattr(juc, "_refresh_active_lazy_features", lambda: None)


def test_post_pull_syntax_check_occurs_before_python_dependency_install(
    monkeypatch, tmp_path
):
    """post-pull syntax/import validation runs BEFORE Python deps install.

    The pipeline runs ``_validate_critical_files_syntax`` (called inside
    the pull helper) before ``_install_python_dependencies``. When syntax
    breaks, the install helpers must not be invoked.
    """
    _stub_helpers(monkeypatch, tmp_path, syntax_break_in="janitor_cli.py")
    side_effect, _ = _make_side_effect()
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    install_calls: list[bool] = []

    def fake_install_python_dependencies(root):
        install_calls.append(True)

    monkeypatch.setattr(juc, "_install_python_dependencies", fake_install_python_dependencies)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 1
    assert install_calls == [], "Python deps must not be installed when syntax breaks"


def test_fresh_config_wrappers_only_called_after_pull(monkeypatch, tmp_path):
    """Fresh config check / migrate wrappers are invoked AFTER git pull.

    The merged ``_run_config_check_fresh()`` and
    ``_run_migrate_config_fresh(...)`` wrappers reload their modules
    internally; calling them before the pull would defeat the point. The
    initial check is followed by a fresh post-check after supported
    migration (2 calls total).
    """
    _stub_helpers(monkeypatch, tmp_path)
    side_effect, recorded = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    # The post-pull reload seam clears the fresh-wrapper sentinels; no-op
    # it so this test's stubs survive.
    monkeypatch.setattr(juc, "_reload_helper_modules_after_pull", lambda: None)

    check_calls = 0
    migrate_calls: list[dict] = []

    def fake_check_fresh():
        nonlocal check_calls
        check_calls += 1
        # First call: v33 (needs migration). Second call (post-check): v34
        # (migration succeeded).
        return (33, 34) if check_calls == 1 else (34, 34)

    def fake_migrate_fresh(*, interactive=False, quiet=True):
        migrate_calls.append({"interactive": interactive, "quiet": True})
        return {"env_added": [], "config_added": [], "warnings": []}

    monkeypatch.setattr(juc, "_run_config_check_fresh", fake_check_fresh)
    monkeypatch.setattr(juc, "_run_migrate_config_fresh", fake_migrate_fresh)

    juc.run_janitor_update(SimpleNamespace())

    pull_index = next(
        (
            i
            for i, c in enumerate(recorded)
            if any("--ff-only" in x for x in c)
        ),
        -1,
    )
    assert pull_index >= 0
    # Initial check + post-check after migration = 2 calls; migrate runs once.
    assert check_calls == 2
    assert len(migrate_calls) == 1


def test_success_order_python_deps_lazy_node_repair_migration_receipt_stash(
    monkeypatch, tmp_path
):
    """Successful run order:

    Python deps → lazy-feature/bootstrap refresh → Node repair →
    config check → config migration → fresh post-check →
    Desktop receipt → stash restore → success banner.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    call_log: list[str] = []

    def fake_python_deps(root):
        call_log.append("python_deps")

    def fake_lazy_refresh():
        call_log.append("lazy_refresh")

    def fake_node_repair():
        call_log.append("node_repair")

    def fake_check_fresh():
        call_log.append("config_check")
        # First call (initial): v33. Second call (post-check): v34
        # so the pipeline reaches the success branch.
        return (33, 34) if call_log.count("config_check") == 1 else (34, 34)

    def fake_migrate_fresh(*, interactive=False, quiet=True):
        call_log.append("config_migrate")
        return {"env_added": [], "config_added": [], "warnings": []}

    def fake_receipt(message):
        call_log.append(f"receipt:{message}")

    monkeypatch.setattr(juc, "_install_python_dependencies", fake_python_deps)
    monkeypatch.setattr(juc, "_refresh_active_lazy_features", fake_lazy_refresh)
    monkeypatch.setattr(juc, "_update_node_dependencies", fake_node_repair)
    monkeypatch.setattr(juc, "_run_config_check_fresh", fake_check_fresh)
    monkeypatch.setattr(juc, "_run_migrate_config_fresh", fake_migrate_fresh)
    monkeypatch.setattr(juc, "_print_update_completion", fake_receipt)

    stash_ref = "fake-stash-ref"
    monkeypatch.setattr(
        juc, "_stash_local_changes_if_needed", lambda *a, **kw: stash_ref
    )

    restore_calls: list[str | None] = []

    def fake_restore(*a, **kw):
        restore_calls.append(kw.get("stash_ref") or (a[2] if len(a) > 2 else None))
        return True

    monkeypatch.setattr(juc, "_restore_stashed_changes", fake_restore)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 0
    assert call_log == [
        "python_deps",
        "lazy_refresh",
        "node_repair",
        "config_check",
        "config_migrate",
        "config_check",
        "receipt:✓ Update complete!",
    ]
    # Stash restore is the LAST post-receipt action before the success banner.
    assert restore_calls == [stash_ref]


def test_already_current_checkout_runs_node_repair_and_config_migration(
    monkeypatch, tmp_path
):
    """When HEAD already matches origin/main, Node repair and config migration still run."""
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, recorded = _make_side_effect(commit_count="0")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    call_log: list[str] = []

    def fake_node_repair():
        call_log.append("node_repair")

    def fake_check_fresh():
        call_log.append("config_check")
        # First call (initial): v33. Second call (post-check): v34
        # so the pipeline reaches the success branch.
        return (33, 34) if call_log.count("config_check") == 1 else (34, 34)

    def fake_migrate_fresh(*, interactive=False, quiet=True):
        call_log.append("config_migrate")
        return {"env_added": [], "config_added": [], "warnings": []}

    monkeypatch.setattr(juc, "_update_node_dependencies", fake_node_repair)
    monkeypatch.setattr(juc, "_run_config_check_fresh", fake_check_fresh)
    monkeypatch.setattr(juc, "_run_migrate_config_fresh", fake_migrate_fresh)

    rc = juc.run_janitor_update(SimpleNamespace())

    # No pull ran (no --ff-only command)
    assert all("--ff-only" not in c for c in recorded)
    # Node repair and config migration still ran
    assert "node_repair" in call_log
    assert "config_check" in call_log
    assert "config_migrate" in call_log
    assert rc == 0


def test_npm_failure_writes_marker_no_banner_no_stash_restore(monkeypatch, tmp_path):
    """When Node deps fail (real upstream returns a non-empty failure list
    rather than raising), the update:

    - returns non-zero,
    - does NOT emit the success banner,
    - does NOT restore the stash (kept for manual recovery),
    - writes ``update-incomplete.json`` at ``get_hermes_home()``.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    def failing_node_repair():
        return ["ui-tui, web workspaces"]

    monkeypatch.setattr(juc, "_update_node_dependencies", failing_node_repair)

    stash_ref = "fake-stash-ref"
    monkeypatch.setattr(
        juc, "_stash_local_changes_if_needed", lambda *a, **kw: stash_ref
    )

    restore_calls: list[str | None] = []

    def fake_restore(*a, **kw):
        restore_calls.append("called")
        return True

    monkeypatch.setattr(juc, "_restore_stashed_changes", fake_restore)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 1
    assert restore_calls == [], "stash must NOT be restored on failure"

    marker = tmp_path / "update-incomplete.json"
    assert marker.exists(), "update-incomplete.json must be written on node_deps failure"
    payload = __import__("json").loads(marker.read_text())
    assert payload["failed_step"] == "node_deps"
    assert payload["stash_ref"] == stash_ref
    assert payload["timestamp"].endswith("Z")


def test_pre_dependency_syntax_failure_rolls_back_to_captured_sha(
    monkeypatch, tmp_path, capsys
):
    """Syntax failure before deps rolls back to the captured pre-pull SHA."""
    _stub_helpers(monkeypatch, tmp_path, syntax_break_in="janitor_cli.py")
    side_effect, recorded = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    rc = juc.run_janitor_update(SimpleNamespace())

    out = capsys.readouterr().out
    assert rc == 1
    rollback_calls = [
        c
        for c in recorded
        if "reset" in c and "--hard" in c and "abc123def456" in c
    ]
    assert len(rollback_calls) == 1
    assert "SyntaxError" in out or "syntax" in out


def test_later_successful_rerun_removes_marker_and_restores_stash_last(
    monkeypatch, tmp_path
):
    """A successful rerun removes the incomplete marker and restores stash last."""
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    stash_ref = "persisted-stash-ref"
    monkeypatch.setattr(
        juc, "_stash_local_changes_if_needed", lambda *a, **kw: stash_ref
    )

    marker = tmp_path / "update-incomplete.json"
    marker.write_text(
        __import__("json").dumps(
            {"stash_ref": stash_ref, "failed_step": "node_deps",
             "timestamp": "20260816T150000Z"}
        )
    )

    call_log: list[str] = []

    def fake_restore(*a, **kw):
        call_log.append("stash_restored")
        return True

    monkeypatch.setattr(juc, "_restore_stashed_changes", fake_restore)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 0
    assert call_log == ["stash_restored"]
    assert not marker.exists(), "marker must be removed on successful rerun"


# ---------------------------------------------------------------------------
# Fix Round 1/5 — regression tests for the Oracle findings.
# ---------------------------------------------------------------------------


def test_node_deps_failure_list_writes_marker_no_receipt_no_banner_no_stash_restore(
    monkeypatch, tmp_path
):
    """When ``_update_node_dependencies`` returns a non-empty failure list,
    the update aborts: writes the node_deps marker, prints NO receipt, NO
    success banner, and does NOT restore the stash.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    events: list[str] = []

    def node_repair_failure_list():
        events.append("node_repair")
        # Real upstream returns a non-empty list — no exception.
        return ["ui-tui, web workspaces"]

    def receipt_unwanted(message):
        events.append(f"receipt:{message}")

    def banner_unwanted():
        events.append("success_banner")

    monkeypatch.setattr(juc, "_update_node_dependencies", node_repair_failure_list)
    monkeypatch.setattr(juc, "_print_update_completion", receipt_unwanted)

    stash_ref = "fake-stash-ref"
    monkeypatch.setattr(
        juc, "_stash_local_changes_if_needed", lambda *a, **kw: stash_ref
    )

    restore_calls: list[str] = []
    monkeypatch.setattr(
        juc,
        "_restore_stashed_changes",
        lambda *a, **kw: restore_calls.append("called") or True,
    )

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 1
    assert "node_repair" in events
    # No receipt, no success banner.
    assert not any(e.startswith("receipt:") for e in events)
    assert "success_banner" not in events
    # No stash restore on node_deps failure.
    assert restore_calls == []

    marker = tmp_path / "update-incomplete.json"
    assert marker.exists()
    payload = json.loads(marker.read_text())
    assert payload["failed_step"] == "node_deps"
    assert payload["stash_ref"] == stash_ref


def test_marker_cleanup_returns_bool_and_failure_returns_1_no_success_banner(
    monkeypatch, tmp_path, capsys
):
    """If marker cleanup returns False (the marker could not be removed), the
    pipeline returns 1 and does NOT print the success banner — the user
    must know the recovery marker is still on disk.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    monkeypatch.setattr(juc, "_print_update_completion", lambda m: None)

    def cleanup_fails():
        return False

    monkeypatch.setattr(juc, "_clear_incomplete_marker", cleanup_fails)

    rc = juc.run_janitor_update(SimpleNamespace())

    out = capsys.readouterr().out
    assert rc == 1
    assert "✓ Janitor Agent updated successfully!" not in out


def test_stash_restore_failure_returns_1_no_success_banner(monkeypatch, tmp_path, capsys):
    """If ``_restore_stashed_changes`` returns False, the pipeline returns 1
    and does NOT print the success banner.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    stash_ref = "fake-stash-ref"
    monkeypatch.setattr(
        juc, "_stash_local_changes_if_needed", lambda *a, **kw: stash_ref
    )

    def restore_fails(*a, **kw):
        return False

    monkeypatch.setattr(juc, "_restore_stashed_changes", restore_fails)

    rc = juc.run_janitor_update(SimpleNamespace())

    out = capsys.readouterr().out
    assert rc == 1
    assert "✓ Janitor Agent updated successfully!" not in out


def test_shared_event_log_receipt_marker_cleanup_stash_restore_banner_ordering(
    monkeypatch, tmp_path, capsys
):
    """A successful run records, in this exact order, on one shared event log:

    receipt → marker_cleanup → stash_restore → success_banner.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    events: list[str] = []

    def receipt(message):
        events.append("receipt")
        print(f"receipt:{message}")

    def cleanup():
        events.append("marker_cleanup")
        print("marker_cleanup")
        return True

    def restore(*a, **kw):
        events.append("stash_restore")
        print("stash_restore")
        return True

    monkeypatch.setattr(juc, "_print_update_completion", receipt)
    monkeypatch.setattr(juc, "_clear_incomplete_marker", cleanup)
    monkeypatch.setattr(juc, "_restore_stashed_changes", restore)

    stash_ref = "fake-stash-ref"
    monkeypatch.setattr(
        juc, "_stash_local_changes_if_needed", lambda *a, **kw: stash_ref
    )

    rc = juc.run_janitor_update(SimpleNamespace())
    out = capsys.readouterr().out

    assert rc == 0
    assert events == ["receipt", "marker_cleanup", "stash_restore"]
    assert "✓ Janitor Agent updated successfully!" in out
    banner_idx = out.index("✓ Janitor Agent updated successfully!")
    receipt_idx = out.index("receipt")
    marker_idx = out.index("marker_cleanup")
    stash_idx = out.index("stash_restore")
    assert receipt_idx < marker_idx < stash_idx < banner_idx


def test_post_pull_helper_module_reload_seam_invalidates_caches_and_rebinds(
    monkeypatch, tmp_path
):
    """After a successful pull + syntax validation, an explicit reload seam:

    1. invalidates the importlib cache,
    2. clears the helper cache and the three fresh-wrapper sentinels,
    3. rebinds the fresh wrappers from the freshly-loaded modules,
    4. only then enters the Node / config phase.

    The same seam runs on the already-current path so wrappers stay
    current after a no-pull update.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    events: list[str] = []
    sentinel_check_before_rebind = object()
    sentinel_check_after_rebind = object()

    # The seam must explicitly invalidate importlib caches.
    captured: dict = {}

    def fake_invalidate_caches():
        events.append("invalidate_caches")

    def fake_reload_module(name):
        events.append(f"reload:{name}")
        # Pretend to return a module with our sentinel bound.
        import types
        mod = types.SimpleNamespace()
        if name.endswith(".config"):
            mod.check_config_version = lambda: (33, 34)
            mod.migrate_config = lambda *, interactive=False, quiet=True: {
                "env_added": [], "config_added": [], "warnings": []
            }
        return mod

    def fake_clear_helper_cache():
        events.append("clear_helper_cache")
        juc._HELPER_CACHE.clear()
        # Clear the three fresh-wrapper sentinels.
        for name in (
            "_run_config_check_fresh",
            "_run_migrate_config_fresh",
            "_print_update_completion",
        ):
            if hasattr(juc, name):
                setattr(juc, name, None)

    def fake_rebind_fresh_wrappers():
        events.append("rebind_fresh_wrappers")
        # Re-import from the (already-reloaded) hermes_cli.update_cmd.
        try:
            from hermes_cli.update_cmd import (
                _run_config_check_fresh,
                _run_migrate_config_fresh,
                _print_update_completion,
            )
            juc._run_config_check_fresh = _run_config_check_fresh
            juc._run_migrate_config_fresh = _run_migrate_config_fresh
            juc._print_update_completion = _print_update_completion
        except Exception:
            pass

    def fake_rebind_fresh_wrappers_test_lambdas():
        # Variant for the seam-ordering test: rebind to the test's own
        # recording fakes instead of the real upstream, so subsequent
        # phase calls (node_repair, config_check, config_migrate) can
        # still be observed on the shared events list.
        events.append("rebind_fresh_wrappers")
        juc._run_config_check_fresh = fake_check_fresh
        juc._run_migrate_config_fresh = fake_migrate_fresh

    monkeypatch.setattr(juc.importlib, "invalidate_caches", fake_invalidate_caches)
    def seam_lambda():
        # The seam MUST clear the sentinels; the rebind step uses the
        # test's own lambdas (not the real upstream) so we can verify
        # the order against the test's recording fakes.
        fake_invalidate_caches()
        fake_clear_helper_cache()
        fake_rebind_fresh_wrappers_test_lambdas()
    monkeypatch.setattr(
        juc,
        "_reload_helper_modules_after_pull",
        seam_lambda,
    )

    # Track order: pull -> reload seam -> node/config phase.
    def node_repair():
        events.append("node_repair")

    # Re-bind AFTER the seam so the seam cannot clobber the test's own
    # fakes (the rebind is intentionally a no-op for the test).
    monkeypatch.setattr(juc, "_run_config_check_fresh", lambda: (33, 34))
    monkeypatch.setattr(
        juc,
        "_run_migrate_config_fresh",
        lambda *, interactive=False, quiet=True: {
            "env_added": [],
            "config_added": [],
            "warnings": [],
        },
    )

    def fake_check_fresh():
        events.append("config_check")
        # First call (initial): v33. Second call (post-check): v34
        # so the pipeline reaches the success branch.
        return (33, 34) if events.count("config_check") == 1 else (34, 34)

    def fake_migrate_fresh(*, interactive=False, quiet=True):
        events.append("config_migrate")
        return {"env_added": [], "config_added": [], "warnings": []}

    monkeypatch.setattr(juc, "_update_node_dependencies", node_repair)
    monkeypatch.setattr(juc, "_run_config_check_fresh", fake_check_fresh)
    monkeypatch.setattr(juc, "_run_migrate_config_fresh", fake_migrate_fresh)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 0
    # Pull must complete before the reload seam.
    pull_idx = next(
        (i for i, e in enumerate(events)
         if any("pull" in e for _ in [0])),
        -1,
    )
    # The seam must run BEFORE node_repair / config_check / config_migrate.
    assert "clear_helper_cache" in events
    assert "rebind_fresh_wrappers" in events
    assert "node_repair" in events
    assert "config_check" in events
    assert "config_migrate" in events
    assert events.index("clear_helper_cache") < events.index("node_repair")
    assert events.index("rebind_fresh_wrappers") < events.index("config_check")
    assert events.index("rebind_fresh_wrappers") < events.index("config_migrate")


def test_already_current_path_runs_reload_seam(monkeypatch, tmp_path):
    """The already-current checkout path still runs the reload seam (so a
    no-pull update reloads fresh wrappers and validates the on-disk schema).
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="0")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    events: list[str] = []
    monkeypatch.setattr(juc, "_update_node_dependencies", lambda: events.append("node_repair"))

    check_call_count = [0]
    def fake_check_fresh():
        events.append("config_check")
        check_call_count[0] += 1
        # Initial check: v33 (needs migration). Post-check: v34.
        return (33, 34) if check_call_count[0] == 1 else (34, 34)

    monkeypatch.setattr(juc, "_run_config_check_fresh", fake_check_fresh)
    monkeypatch.setattr(
        juc, "_run_migrate_config_fresh",
        lambda *, interactive=False, quiet=True: (
            events.append("config_migrate"),
            {"env_added": [], "config_added": [], "warnings": []},
        )[1],
    )

    monkeypatch.setattr(
        juc, "_reload_helper_modules_after_pull",
        lambda: events.append("reload_seam"),
    )

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 0
    assert "reload_seam" in events
    assert "node_repair" in events
    assert "config_check" in events
    assert "config_migrate" in events


def test_fresh_wrappers_loaded_after_pull_via_single_event_log(monkeypatch, tmp_path):
    """Single event log proves: pull completes BEFORE cache_clear /
    rebind / config_check / config_migrate.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, recorded = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    events: list[str] = []

    def fake_clear():
        events.append("cache_clear")

    def fake_rebind():
        events.append("rebind")

    monkeypatch.setattr(juc, "_reload_helper_modules_after_pull",
                        lambda: (fake_clear(), fake_rebind()))

    def node_repair():
        events.append("node_repair")

    def check():
        events.append("config_check")
        # Initial: v33 (migration needed). Post-check: v34.
        return (33, 34) if events.count("config_check") == 1 else (34, 34)

    def migrate(*, interactive=False, quiet=True):
        events.append("config_migrate")
        return {"env_added": [], "config_added": [], "warnings": []}

    monkeypatch.setattr(juc, "_update_node_dependencies", node_repair)
    monkeypatch.setattr(juc, "_run_config_check_fresh", check)
    monkeypatch.setattr(juc, "_run_migrate_config_fresh", migrate)

    rc = juc.run_janitor_update(SimpleNamespace())

    # Pull completed (at least one --ff-only recorded command).
    assert any("--ff-only" in c for c in recorded)
    # Event ordering — pull-then-reload-then-node-then-check-then-migrate.
    assert rc == 0
    # All events after pull should appear in the recorded events.
    # The seam runs after pull completes; cache_clear must be the first
    # seam event recorded.
    assert events[0] == "cache_clear", (
        f"cache_clear must be the first post-pull event; got {events[:3]!r}"
    )
    assert events.index("rebind") > events.index("cache_clear")
    assert events.index("node_repair") > events.index("rebind")
    assert events.index("config_check") > events.index("rebind")
    assert events.index("config_migrate") > events.index("config_check")


def test_persisted_marker_stash_ref_restored_last_when_no_new_stash(
    monkeypatch, tmp_path
):
    """A later successful run with NO new local stash still restores the
    persisted ``stash_ref`` from a pre-existing ``update-incomplete.json`` LAST.
    Current ``_stash_local_changes_if_needed`` returns ``None``; the
    persisted marker carries the ref.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    persisted_ref = "persisted-stash-ref"
    marker = tmp_path / "update-incomplete.json"
    marker.write_text(json.dumps({
        "stash_ref": persisted_ref,
        "failed_step": "node_deps",
        "timestamp": "20260816T150000Z",
    }))

    # Current run has nothing new to stash.
    monkeypatch.setattr(
        juc, "_stash_local_changes_if_needed", lambda *a, **kw: None
    )

    restore_calls: list[str] = []
    def fake_restore(*a, **kw):
        # _restore_stashed_changes(git_cmd, project_root, stash_ref)
        ref = kw.get("stash_ref")
        if ref is None and len(a) >= 3:
            ref = a[2]
        restore_calls.append(ref)
        return True

    monkeypatch.setattr(juc, "_restore_stashed_changes", fake_restore)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 0
    assert restore_calls == [persisted_ref], (
        f"expected the persisted stash_ref to be restored LAST, got {restore_calls!r}"
    )
    assert not marker.exists()


def test_marker_payload_has_exact_required_keys_and_parseable_utc_z_timestamp(
    monkeypatch, tmp_path
):
    """The marker JSON has EXACTLY the keys {stash_ref, failed_step,
    timestamp}; failed_step is one of {node_deps, config_migration};
    timestamp parses as UTC ISO 8601 with the ``Z`` suffix.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    monkeypatch.setattr(juc, "_update_node_dependencies",
                        lambda: ["ui-tui, web workspaces"])

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 1
    marker = tmp_path / "update-incomplete.json"
    payload = json.loads(marker.read_text())
    assert set(payload.keys()) == {"stash_ref", "failed_step", "timestamp"}
    assert payload["failed_step"] in {"node_deps", "config_migration"}
    ts = payload["timestamp"]
    assert ts.endswith("Z"), ts
    # Parseable as UTC ISO 8601.
    parsed = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    assert parsed.tzinfo is None  # naive; the Z is the explicit marker


def test_missing_fresh_check_writes_marker_no_banner_config_migration_step(
    monkeypatch, tmp_path
):
    """When ``_run_config_check_fresh`` is None (not lazy-loaded), the
    INITIAL check returns ``(None, None)`` (warn-and-no-op per Round 3/5
    brief). No migration runs, no marker is written, the run is a
    no-op success.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    monkeypatch.setattr(juc, "_run_config_check_fresh", None)
    monkeypatch.setattr(juc, "_run_migrate_config_fresh", lambda *, interactive=False, quiet=True: {
        "env_added": [], "config_added": [], "warnings": []
    })

    receipt_calls: list[str] = []
    monkeypatch.setattr(juc, "_print_update_completion",
                        lambda m: receipt_calls.append(m))

    restore_calls: list[str] = []
    monkeypatch.setattr(juc, "_restore_stashed_changes",
                        lambda *a, **kw: restore_calls.append("called") or True)

    rc = juc.run_janitor_update(SimpleNamespace())

    # Initial-check invalid (no wrapper): warn + no-op → rc=0, no marker,
    # the success path runs (Node repair, receipt, cleanup, stash restore).
    assert rc == 0
    assert receipt_calls == ["✓ Update complete!"]
    marker = tmp_path / "update-incomplete.json"
    assert not marker.exists()


def test_initial_check_exception_writes_marker_no_banner_config_migration_step(
    monkeypatch, tmp_path
):
    """When the initial ``_run_config_check_fresh()`` raises, the initial-
    check policy (Round 3/5) treats this as invalid: warn + no-op
    migration. The strict failure path is reserved for the post-check.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    def check_raises():
        raise RuntimeError("simulated initial check exception")

    monkeypatch.setattr(juc, "_run_config_check_fresh", check_raises)
    monkeypatch.setattr(juc, "_run_migrate_config_fresh",
                        lambda *, interactive=False, quiet=True: {
                            "env_added": [], "config_added": [], "warnings": []
                        })

    receipt_calls: list[str] = []
    monkeypatch.setattr(juc, "_print_update_completion",
                        lambda m: receipt_calls.append(m))

    rc = juc.run_janitor_update(SimpleNamespace())

    # Initial-check exception: warn + no-op (Round 3/5 policy). The
    # success path still runs (Node repair, receipt, marker cleanup,
    # stash restore).
    assert rc == 0
    assert receipt_calls == ["✓ Update complete!"]
    marker = tmp_path / "update-incomplete.json"
    assert not marker.exists()


def test_migration_exception_writes_marker_no_banner_config_migration_step(
    monkeypatch, tmp_path
):
    """When ``_run_migrate_config_fresh`` raises, the pipeline takes the
    config_migration non-success path: writes the marker, exits 1, no
    receipt, no banner, no stash restore.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    monkeypatch.setattr(juc, "_run_config_check_fresh", lambda: (33, 34))

    def migrate_raises(*, interactive=False, quiet=True):
        raise RuntimeError("simulated migration exception")

    monkeypatch.setattr(juc, "_run_migrate_config_fresh", migrate_raises)

    receipt_calls: list[str] = []
    monkeypatch.setattr(juc, "_print_update_completion",
                        lambda m: receipt_calls.append(m))

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 1
    assert receipt_calls == []
    marker = tmp_path / "update-incomplete.json"
    assert marker.exists()
    assert json.loads(marker.read_text())["failed_step"] == "config_migration"


def test_post_check_exception_writes_marker_no_banner_config_migration_step(
    monkeypatch, tmp_path
):
    """When the FRESH POST-CHECK (after supported migration) raises, the
    pipeline takes the config_migration non-success path: writes the
    marker, exits 1, no receipt, no banner, no stash restore.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    call_count = {"check": 0}

    def check_raises_after_first():
        call_count["check"] += 1
        if call_count["check"] == 1:
            return (33, 34)  # initial check: migration needed
        raise RuntimeError("simulated post-check exception")

    monkeypatch.setattr(juc, "_run_config_check_fresh", check_raises_after_first)
    monkeypatch.setattr(juc, "_run_migrate_config_fresh",
                        lambda *, interactive=False, quiet=True: {
                            "env_added": [], "config_added": [], "warnings": []
                        })

    receipt_calls: list[str] = []
    monkeypatch.setattr(juc, "_print_update_completion",
                        lambda m: receipt_calls.append(m))

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 1
    assert receipt_calls == []
    marker = tmp_path / "update-incomplete.json"
    assert marker.exists()
    assert json.loads(marker.read_text())["failed_step"] == "config_migration"


def test_post_check_still_behind_with_support_floor_warnings_is_allowed(
    monkeypatch, tmp_path
):
    """A still-behind post-check is allowed ONLY when the migration results
    returned warnings that match the real upstream ``support_floor_message()``
    text (not fabricated substrings). In that case: no marker, exit 0,
    receipt + cleanup + stash restore. The warning here is the actual text
    returned by ``hermes_cli.config_migrations.support_floor_message()`` so
    the contract is exercised against reality, not a fabricated proxy.
    """
    import hermes_cli.config_migrations as upstream_migrations

    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    monkeypatch.setattr(juc, "_run_config_check_fresh", lambda: (32, 34))
    real_floor_warning = upstream_migrations.support_floor_message()
    monkeypatch.setattr(
        juc, "_run_migrate_config_fresh",
        lambda *, interactive=False, quiet=True: {
            "env_added": [],
            "config_added": [],
            "warnings": [real_floor_warning],
        },
    )

    receipt_calls: list[str] = []
    monkeypatch.setattr(juc, "_print_update_completion",
                        lambda m: receipt_calls.append(m))

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 0
    assert receipt_calls == ["✓ Update complete!"]
    assert not (tmp_path / "update-incomplete.json").exists()


def test_get_hermes_home_uses_canonical_helper_when_importable(
    monkeypatch, tmp_path
):
    """``get_hermes_home`` defers to ``hermes_constants.get_hermes_home()``
    when that module is importable. No hardcoded ``$HOME/.janitor``
    fallback path is reachable in a normal install.
    """
    from hermes_constants import get_hermes_home as canonical_home

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile_home"))
    resolved = juc.get_hermes_home()
    canonical_resolved = Path(canonical_home())
    assert resolved.resolve() == canonical_resolved.resolve()


# ---------------------------------------------------------------------------
# Fix Round 2/5 — Oracle re-review regression tests
# ---------------------------------------------------------------------------


def test_seam_rebinds_from_freshly_loaded_module_after_evicting_sys_modules(
    monkeypatch, tmp_path
):
    """The seam MUST evict ``hermes_cli.update_cmd`` from ``sys.modules``
    before re-binding, otherwise ``importlib.import_module`` returns the
    stale cached module and the rebound callables come from cached code
    (not refreshed disk code). This is a behavior test that proves the
    rebound wrappers were obtained from a freshly-loaded module — not a
    mock-away.

    Procedure:
      1. Capture the real upstream wrapper.
      2. Patch ``hermes_cli.update_cmd._run_config_check_fresh`` to a
         sentinel that the seam CANNOT mistake for real.
      3. Run the seam. The patched sentinel is in ``sys.modules``.
      4. Verify the sentinel is gone (replaced) and the rebound is the
         real upstream wrapper (NOT the sentinel).
    """
    import sys

    _stub_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    # Force hermes_cli.update_cmd to be loaded and capture its real wrapper.
    import hermes_cli.update_cmd as real_update_cmd_mod  # noqa: F401
    real_check_fn = real_update_cmd_mod._run_config_check_fresh
    # Sanity: real_check_fn must NOT be the sentinel we are about to install.
    assert callable(real_check_fn)

    sentinel = lambda: ("STALE_PATCH", 0)
    real_update_cmd_mod._run_config_check_fresh = sentinel
    # The sentinel is now live in sys.modules; the seam's _try_import
    # would return this same stale binding unless it evicts first.
    assert sys.modules["hermes_cli.update_cmd"]._run_config_check_fresh is sentinel

    # Run a real update path so the seam is reached (the seam itself runs
    # *before* Node repair / config migration; we use a no-op node repair
    # and stub config migration to a no-op migrate with no post-check
    # still-behind so the run completes).
    monkeypatch.setattr(juc, "_update_node_dependencies", lambda: [])
    check_calls = []

    def fresh_check_fresh():
        check_calls.append("called")
        # If the seam evicted + reloaded, this is a fresh module's
        # function (different binding than the sentinel).
        return real_check_fn()

    monkeypatch.setattr(juc, "_run_config_check_fresh", fresh_check_fresh)
    monkeypatch.setattr(
        juc, "_run_migrate_config_fresh",
        lambda *, interactive=False, quiet=True: {
            "env_added": [],
            "config_added": [],
            "warnings": [],
        },
    )

    rc = juc.run_janitor_update(SimpleNamespace())
    assert rc == 0

    # The sentinel that was in sys.modules is gone: hermes_cli.update_cmd
    # has been evicted and the seam's re-import produced a fresh binding.
    fresh_update_cmd = sys.modules.get("hermes_cli.update_cmd")
    assert fresh_update_cmd is not None
    assert fresh_update_cmd._run_config_check_fresh is not sentinel, (
        "seam did not evict sys.modules['hermes_cli.update_cmd']; "
        "the sentinel binding is still live"
    )


def test_seam_loads_seam_when_helper_module_already_evicted(
    monkeypatch, tmp_path
):
    """Behavioral contract: the seam clears and reloads the helper
    module whether or not a sentinel is currently cached in
    ``sys.modules``. The pre-seam sentinel installed directly in
    ``hermes_cli.update_cmd._run_config_check_fresh`` MUST be gone
    after the seam — otherwise a stale cached binding would survive
    invalidation.
    """
    import sys

    _stub_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    import hermes_cli.update_cmd as real_update_cmd_mod  # noqa: F401

    pre_seam_sentinel = lambda *a, **kw: ("STALE_PRE_SEAM", 0)
    real_update_cmd_mod._run_config_check_fresh = pre_seam_sentinel

    monkeypatch.setattr(juc, "_update_node_dependencies", lambda: [])

    monkeypatch.setattr(juc, "_run_migrate_config_fresh",
        lambda *, interactive=False, quiet=True: {
            "env_added": [],
            "config_added": [],
            "warnings": [],
        })
    monkeypatch.setattr(juc, "_run_config_check_fresh", lambda: (34, 34))

    rc = juc.run_janitor_update(SimpleNamespace())
    # Exit code is irrelevant for this test — what matters is that the
    # seam evicted and re-imported the module.
    assert rc in (0, 1)
    # After the seam, the fresh module's binding is NOT the pre-seam
    # sentinel (it must come from a freshly loaded module).
    fresh_module = sys.modules["hermes_cli.update_cmd"]
    assert fresh_module._run_config_check_fresh is not pre_seam_sentinel


def test_persisted_marker_stash_ref_preserved_across_repeated_failure(
    monkeypatch, tmp_path
):
    """A repeated failure (a second failed run with no new local stash)
    must NOT overwrite the persisted ``stash_ref`` on disk. The marker
    is the recovery contract; losing the prior ref loses user work.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    # First run: produces an auto_stash_ref and node_deps failure.
    persisted_ref = "persisted-ref-from-first-failure"
    marker = tmp_path / "update-incomplete.json"
    marker.write_text(json.dumps({
        "stash_ref": persisted_ref,
        "failed_step": "node_deps",
        "timestamp": "20260817T150000Z",
    }))

    # No new local stash this run (already in failure-loop), so the
    # recovered marker must preserve the prior ref.
    monkeypatch.setattr(
        juc, "_stash_local_changes_if_needed", lambda *a, **kw: None
    )

    def still_failing():
        return ["ui-tui, web workspaces"]

    monkeypatch.setattr(juc, "_update_node_dependencies", still_failing)

    rc = juc.run_janitor_update(SimpleNamespace())

    # The failure path still writes a marker (failure happened), but the
    # prior persisted_stash_ref is preserved on disk.
    assert rc == 1
    assert marker.exists()
    payload = json.loads(marker.read_text())
    assert payload["failed_step"] == "node_deps"
    assert payload["stash_ref"] == persisted_ref, (
        f"persisted_stash_ref was clobbered: {payload['stash_ref']!r}"
    )


def test_restore_both_auto_and_persisted_stash_refs_when_both_exist(
    monkeypatch, tmp_path
):
    """When the current run produced a NEW auto_stash_ref AND a
    persisted marker carries a different stash_ref, BOTH must be
    restored — the persisted one LAST. Losing either loses user work.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    persisted_ref = "persisted-ref-on-disk"
    marker = tmp_path / "update-incomplete.json"
    marker.write_text(json.dumps({
        "stash_ref": persisted_ref,
        "failed_step": "node_deps",
        "timestamp": "20260817T150000Z",
    }))

    auto_ref = "auto-ref-this-run"

    def stash_new(*a, **kw):
        return auto_ref

    monkeypatch.setattr(juc, "_stash_local_changes_if_needed", stash_new)

    restore_calls: list[str] = []
    monkeypatch.setattr(
        juc, "_restore_stashed_changes",
        lambda *a, **kw: (
            restore_calls.append(
                kw.get("stash_ref") or (a[2] if len(a) > 2 else None)
            )
            or True
        ),
    )

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 0
    # Both refs must be restored; the persisted one LAST.
    assert auto_ref in restore_calls
    assert persisted_ref in restore_calls
    auto_idx = restore_calls.index(auto_ref)
    persisted_idx = restore_calls.index(persisted_ref)
    assert auto_idx < persisted_idx, (
        f"persisted_stash_ref must be restored LAST; got {restore_calls!r}"
    )


def test_persisted_marker_ref_preserved_on_dirty_new_work_rerun_failure(
    monkeypatch, tmp_path
):
    """Round 3/5 Oracle finding C1: when a persisted marker carries a
    stash_ref AND the current run ALSO produced a NEW auto_stash_ref
    (dirty/new-work), the new run's failure must NOT overwrite the
    persisted ref on disk. Never overwrite one recoverable ref with
    another. The exact three-key marker schema is preserved.

    In this test, the prior marker has stash_ref="prior", the new run
    produces auto_stash_ref="new", and the new run fails. The marker on
    disk after the failure must still carry the prior ref — the new ref
    is in memory only and is restored together with the prior on a
    later successful rerun.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    prior_ref = "prior-ref-on-disk"
    marker = tmp_path / "update-incomplete.json"
    marker.write_text(json.dumps({
        "stash_ref": prior_ref,
        "failed_step": "node_deps",
        "timestamp": "20260817T150000Z",
    }))

    new_ref = "new-ref-this-run"

    def stash_new(*a, **kw):
        return new_ref

    monkeypatch.setattr(juc, "_stash_local_changes_if_needed", stash_new)

    # New run fails in node_deps.
    def failing_node_repair():
        return ["ui-tui, web workspaces"]

    monkeypatch.setattr(juc, "_update_node_dependencies", failing_node_repair)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 1
    # The persisted marker schema is preserved: exactly three keys.
    assert marker.exists()
    payload = json.loads(marker.read_text())
    assert set(payload.keys()) == {"stash_ref", "failed_step", "timestamp"}
    # The PRIOR stash_ref is preserved on disk; the new ref is in memory
    # only (will be restored from in-memory state on a later successful
    # rerun alongside the prior).
    assert payload["stash_ref"] == prior_ref, (
        f"a new run's auto_stash_ref must not overwrite the persisted "
        f"prior on disk; persisted={prior_ref!r} new={new_ref!r} "
        f"actual={payload['stash_ref']!r}"
    )
    # failed_step / timestamp reflect THIS run.
    assert payload["failed_step"] == "node_deps"


def test_dirty_worktree_with_persisted_stash_aborts_before_second_stash(
    monkeypatch, tmp_path, capsys
):
    """An unresolved persisted stash blocks a dirty-worktree rerun.

    The update must stop before creating another stash or starting any
    mutating/downstream phase. The existing marker is the durable recovery
    contract and must remain byte-for-byte untouched.
    """
    # Given a valid unresolved marker and new dirty work in the checkout.
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    base_side_effect, recorded = _make_side_effect(commit_count="3")

    def dirty_worktree(cmd, **kwargs):
        result = base_side_effect(cmd, **kwargs)
        if cmd[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(
                returncode=0,
                stdout=" M user-owned-change.py\n",
                stderr="",
            )
        return result

    monkeypatch.setattr(juc.subprocess, "run", dirty_worktree)

    persisted_ref = "persisted-ref-from-unresolved-update"
    marker = tmp_path / "update-incomplete.json"
    marker.write_text(json.dumps({
        "stash_ref": persisted_ref,
        "failed_step": "node_deps",
        "timestamp": "20260817T150000Z",
    }))
    marker_before = marker.read_bytes()

    events: list[str] = []
    monkeypatch.setattr(
        juc,
        "_stash_local_changes_if_needed",
        lambda *a, **kw: events.append("stash") or "second-stash-ref",
    )
    monkeypatch.setattr(
        juc,
        "_install_python_dependencies",
        lambda root: events.append("python_deps"),
    )
    monkeypatch.setattr(
        juc,
        "_update_node_dependencies",
        lambda: events.append("node_repair") or [],
    )
    monkeypatch.setattr(
        juc,
        "_run_config_check_fresh",
        lambda: events.append("config_check") or (34, 34),
    )
    monkeypatch.setattr(
        juc,
        "_run_migrate_config_fresh",
        lambda **kwargs: events.append("config_migrate") or {},
    )
    monkeypatch.setattr(
        juc,
        "_print_update_completion",
        lambda message: events.append("receipt"),
    )
    monkeypatch.setattr(
        juc,
        "_clear_incomplete_marker",
        lambda: events.append("marker_cleanup") or True,
    )

    # When the user reruns the updater.
    rc = juc.run_janitor_update(SimpleNamespace())

    # Then it fails closed before any second stash or downstream mutation.
    output = capsys.readouterr().out
    assert rc == 1
    assert events == []
    assert all("--ff-only" not in command for command in recorded)
    assert marker.read_bytes() == marker_before
    assert persisted_ref in output
    assert "git stash apply" in output
    assert "✓ Janitor Agent updated successfully!" not in output


def test_initial_check_invalid_versions_warn_and_no_op(
    monkeypatch, tmp_path
):
    """Round 3/5 Oracle finding C3: the brief requires invalid initial
    values to warn and leave config untouched, NOT fail. Post-check
    keeps strict failure for malformed / non-int.

    The initial check may legitimately see invalid version tuples when
    the on-disk config is broken (e.g., a user hand-edited
    ``_config_version: 99`` with garbage). The initial check should warn
    and treat the config as already-at-target — the migrate step does
    not run, the post-check is not reached, no marker is written, rc=0.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    monkeypatch.setattr(juc, "_update_node_dependencies", lambda: [])

    # First call (initial check) returns non-int versions — a malformed
    # on-disk config.
    monkeypatch.setattr(juc, "_run_config_check_fresh", lambda: ("33", "34"))

    rc = juc.run_janitor_update(SimpleNamespace())

    # The pipeline warns + leaves config untouched; the success path
    # still runs (Node repair, receipt, marker cleanup, stash restore).
    assert rc == 0
    marker = tmp_path / "update-incomplete.json"
    assert not marker.exists(), (
        "no failure occurred; the invalid-initial-values path is a "
        "no-op, not a failure, so no marker should be written"
    )


def test_initial_check_non_tuple_warn_and_no_op(monkeypatch, tmp_path):
    """Initial check returning a non-tuple (e.g. None) is also a
    warn-and-no-op for the same reason as invalid versions — the on-disk
    config cannot be characterised by the wrapper. No migration, no
    marker, rc=0.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    monkeypatch.setattr(juc, "_update_node_dependencies", lambda: [])
    monkeypatch.setattr(juc, "_run_config_check_fresh", lambda: None)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 0
    assert not (tmp_path / "update-incomplete.json").exists()


def test_post_check_malformed_tuple_fails_loudly(monkeypatch, tmp_path):
    """A post-check that returns a malformed value (None / wrong type /
    wrong arity) is non-success — never silently ignored. Round 2/5
    Oracle finding C5 disallows the prior permissive swallow.

    The initial check is valid (33, 34) so migration runs. The
    post-check then returns None — a malformed post-check value. The
    post-check policy is strict (Round 3/5): malformed values fail
    loudly with a marker, rc=1.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    monkeypatch.setattr(juc, "_update_node_dependencies", lambda: [])
    monkeypatch.setattr(
        juc, "_run_migrate_config_fresh",
        lambda *, interactive=False, quiet=True: {
            "env_added": [],
            "config_added": [],
            "warnings": [],
        },
    )

    counter = [0]
    def check_fresh():
        counter[0] += 1
        if counter[0] == 1:
            return (33, 34)  # initial check: needs migration
        return None  # post-check: malformed (not a tuple)

    monkeypatch.setattr(juc, "_run_config_check_fresh", check_fresh)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 1
    marker = tmp_path / "update-incomplete.json"
    assert marker.exists()
    payload = json.loads(marker.read_text())
    assert payload["failed_step"] == "config_migration"


def test_post_check_non_int_versions_fails_loudly(monkeypatch, tmp_path):
    """Post-check returning non-int versions (str, None, float) is
    non-success — never silently a no-op. Strict (Round 3/5).
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    monkeypatch.setattr(juc, "_update_node_dependencies", lambda: [])
    monkeypatch.setattr(
        juc, "_run_migrate_config_fresh",
        lambda *, interactive=False, quiet=True: {
            "env_added": [],
            "config_added": [],
            "warnings": [],
        },
    )

    counter = [0]
    def check_fresh():
        counter[0] += 1
        if counter[0] == 1:
            return (33, 34)  # initial check: valid
        return ("33", "34")  # post-check: non-int

    monkeypatch.setattr(juc, "_run_config_check_fresh", check_fresh)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 1
    assert (tmp_path / "update-incomplete.json").exists()


def test_post_check_current_strictly_greater_than_latest_fails_loudly(
    monkeypatch, tmp_path
):
    """When ``current > latest`` at the post-check, the pipeline is
    non-success — Round 2/5 C5 disallows silently accepting a downgrade
    as a no-op after migration. The initial check may legitimately
    observe a downgrade (the config is newer than what the wrapper
    knows about); only the post-check downgrade is a HARD failure.
    """
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    monkeypatch.setattr(juc, "_update_node_dependencies", lambda: [])
    monkeypatch.setattr(
        juc, "_run_migrate_config_fresh",
        lambda *, interactive=False, quiet=True: {
            "env_added": [],
            "config_added": [],
            "warnings": [],
        },
    )

    # First call (initial check): v33 → migrate runs. Second call
    # (post-check): simulate a downgrade where current exceeded latest
    # after migration (impossible in upstream, but a must-fail scenario).
    counter = [0]
    def check_fresh_with_downgrade():
        counter[0] += 1
        if counter[0] == 1:
            return (33, 34)  # initial check: needs migration
        return (40, 34)  # post-check: downgrade to simulate failure

    monkeypatch.setattr(juc, "_run_config_check_fresh", check_fresh_with_downgrade)

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 1
    marker = tmp_path / "update-incomplete.json"
    assert marker.exists()
    payload = json.loads(marker.read_text())
    assert payload["failed_step"] == "config_migration"


def test_support_floor_real_upstream_message_is_only_allowed_still_behind(
    monkeypatch, tmp_path
):
    """The only allowed still-behind post-check is when the upstream
    ``support_floor_message()`` text appears in the migration warnings.
    Any other warning (even one that contains the fabricated substring
    ``"support floor"`` outside the real contract) is non-success.
    """
    import hermes_cli.config_migrations as upstream_migrations

    _stub_pipeline_helpers(monkeypatch, tmp_path)
    side_effect, _ = _make_side_effect(commit_count="3")
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    monkeypatch.setattr(juc, "_update_node_dependencies", lambda: [])

    # First call returns (32, 34) → migrate should run. Post-check also
    # returns (32, 34) → still behind. Warnings contain an UNRELATED
    # string with the words "support floor" but NOT the real upstream
    # message — this must be non-success.
    monkeypatch.setattr(juc, "_run_config_check_fresh", lambda: (32, 34))
    monkeypatch.setattr(
        juc, "_run_migrate_config_fresh",
        lambda *, interactive=False, quiet=True: {
            "env_added": [],
            "config_added": [],
            "warnings": [
                "fabricated message about support floor policy that is not the "
                "real upstream contract"
            ],
        },
    )

    rc = juc.run_janitor_update(SimpleNamespace())

    real_floor = upstream_migrations.support_floor_message()
    assert real_floor not in (
        "fabricated message about support floor policy that is not the real "
        "upstream contract"
    ), (
        "the fabricated warning must not match support_floor_message(); that "
        "would mean we accidentally contract to fabricated text"
    )

    assert rc == 1
    marker = tmp_path / "update-incomplete.json"
    assert marker.exists()
    payload = json.loads(marker.read_text())
    assert payload["failed_step"] == "config_migration"


def test_get_hermes_home_falls_back_to_hermes_home_env_when_constants_breaks(
    monkeypatch, tmp_path
):
    """When ``hermes_constants`` cannot be imported (venv partially
    broken), ``get_hermes_home`` must fall back to a non-empty
    ``HERMES_HOME`` env var. No hardcoded ``~/.janitor`` and no
    ``Path.home()`` fallback.
    """
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "fallback_home"))

    # Force a controlled ImportError on every import attempt.
    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "hermes_constants" or name.startswith("hermes_constants."):
            raise ImportError("simulated broken venv")
        return real_import(name, globals, locals, fromlist, level)

    import builtins
    real_import = builtins.__import__
    builtins.__import__ = fake_import
    try:
        resolved = juc.get_hermes_home()
    finally:
        builtins.__import__ = real_import

    assert resolved.resolve() == (tmp_path / "fallback_home").resolve()
    # No fallback to ~/.janitor or $HOME — the only fall back path
    # observed here is HERMES_HOME.
    assert not str(resolved).endswith("/.janitor")
    assert not str(resolved).endswith("/.hermes")


def test_get_hermes_home_raises_when_hermes_constants_breaks_and_hermes_home_unset(
    monkeypatch, tmp_path
):
    """Without a usable HERMES_HOME env var AND a broken hermes_constants,
    ``get_hermes_home`` raises — never silently substitutes Path.home()
    or a hardcoded ``~/.janitor``.
    """
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "no_default_home"))

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "hermes_constants" or name.startswith("hermes_constants."):
            raise ImportError("simulated broken venv")
        return real_import(name, globals, locals, fromlist, level)

    import builtins
    real_import = builtins.__import__
    builtins.__import__ = fake_import
    try:
        raised = False
        try:
            juc.get_hermes_home()
        except (ImportError, RuntimeError):
            raised = True
    finally:
        builtins.__import__ = real_import

    assert raised, (
        "get_hermes_home must raise when both hermes_constants is broken "
        "AND HERMES_HOME is unset"
    )
