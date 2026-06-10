"""Tests for ``janitor_update_core.run_janitor_update``.

Mirrors the structure of ``tests/hermes_cli/test_update_autostash.py`` so
the Janitor update path is held to the same standard as the official one.
"""

from __future__ import annotations

import os
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
