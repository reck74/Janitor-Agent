#!/usr/bin/env python3
"""
Janitor update core — the canonical update flow shared by both entry points.

Aligned with the official Hermes ``_cmd_update_impl`` in ``hermes_cli/main.py``.
Both ``janitor update`` (early intercept in ``janitor_cli.py``) and the
monkey-patched ``cmd_update`` (also in ``janitor_cli.py``) delegate here.

Helpers are imported lazily inside each phase so a partially-broken venv
(after a failed pull, mid-update crash, etc.) can still recover without
importing every Hermes module at startup. When a helper import fails the
core falls back to a local minimal implementation that preserves the
original ``janitor_update_bootstrap`` behavior for that one helper.

Per JANITOR FORK DIRECTIVE #12: any change to the update flow lives here,
not inline in ``janitor_cli.py`` or ``janitor_update_bootstrap.py``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


# Module-level sentinels so tests can monkeypatch.setattr() before any import
# error fires. Real values are loaded lazily via _try_import().
PROJECT_ROOT: Optional[Path] = None
_run_pre_update_backup: Optional[Callable] = None
_install_hangup_protection: Optional[Callable] = None
_finalize_update_output: Optional[Callable] = None
_stash_local_changes_if_needed: Optional[Callable] = None
_restore_stashed_changes: Optional[Callable] = None
_refresh_active_lazy_features: Optional[Callable] = None
_update_node_dependencies: Optional[Callable] = None
_invalidate_update_cache: Optional[Callable] = None
_clear_bytecode_cache: Optional[Callable] = None
_validate_critical_files_syntax: Optional[Callable] = None
_capture_head_sha: Optional[Callable] = None
_install_python_dependencies_with_optional_fallback: Optional[Callable] = None
_is_termux_env: Optional[Callable] = None
_is_android_python: Optional[Callable] = None
_install_psutil_android_compat: Optional[Callable] = None
_ensure_uv_for_termux: Optional[Callable] = None


# Lazy-import cache: only try each helper once per process.
_HELPER_CACHE: dict[str, Any] = {}


def _try_import(name: str) -> Any:
    """Lazy-import a single helper from ``hermes_cli.main``.

    Returns the helper or ``None`` if the import fails. Cached.
    """
    if name in _HELPER_CACHE:
        return _HELPER_CACHE[name]
    try:
        import hermes_cli.main as _main_mod
        helper = getattr(_main_mod, name, None)
    except Exception:
        helper = None
    _HELPER_CACHE[name] = helper
    return helper


def _ensure_loaded() -> None:
    """Populate module-level sentinels from hermes_cli.main on first use.

    Tests can override any of these via monkeypatch.setattr() before the
    first call. If a helper is None (e.g. venv partially broken), the
    core falls back to a local minimal implementation.
    """
    global PROJECT_ROOT
    if PROJECT_ROOT is None:
        helper = _try_import("PROJECT_ROOT")
        PROJECT_ROOT = helper if helper is not None else Path(__file__).parent.resolve()

    for name in (
        "_run_pre_update_backup",
        "_install_hangup_protection",
        "_finalize_update_output",
        "_stash_local_changes_if_needed",
        "_restore_stashed_changes",
        "_refresh_active_lazy_features",
        "_update_node_dependencies",
        "_invalidate_update_cache",
        "_clear_bytecode_cache",
        "_validate_critical_files_syntax",
        "_capture_head_sha",
        "_install_python_dependencies_with_optional_fallback",
        "_is_termux_env",
        "_is_android_python",
        "_install_psutil_android_compat",
        "_ensure_uv_for_termux",
    ):
        if globals().get(name) is None:
            globals()[name] = _try_import(name)


def _call(
    name: str,
    *args,
    fallback: Optional[Callable] = None,
    **kwargs,
) -> Any:
    """Call a lazy-loaded helper with a graceful fallback.

    If the helper is None (lazy import failed), invoke ``fallback`` if
    provided, otherwise return ``None`` and print a one-line warning.
    """
    helper = globals().get(name)
    if helper is None:
        if fallback is not None:
            return fallback(*args, **kwargs)
        print(f" ⚠ Helper {name} unavailable — skipping.")
        return None
    return helper(*args, **kwargs)


# ---------------------------------------------------------------------------
# Local fallbacks (preserve original janitor_update_bootstrap behavior)
# ---------------------------------------------------------------------------


def _local_stash(git_cmd: list[str], cwd: Path) -> Optional[str]:
    """Local fallback for ``_stash_local_changes_if_needed``."""
    status = subprocess.run(
        git_cmd + ["status", "--porcelain"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    if not status.stdout.strip():
        return None

    unmerged = subprocess.run(
        git_cmd + ["ls-files", "--unmerged"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if unmerged.stdout.strip():
        print(" → Clearing unmerged index entries from a previous conflict...")
        subprocess.run(git_cmd + ["reset"], cwd=cwd, capture_output=True)

    stash_name = datetime.now(timezone.utc).strftime(
        "janitor-update-autostash-%Y%m%d-%H%M%S"
    )
    print(" → Local changes detected — stashing before update...")
    subprocess.run(
        git_cmd + ["stash", "push", "--include-untracked", "-m", stash_name],
        cwd=cwd,
        check=True,
    )
    return subprocess.run(
        git_cmd + ["rev-parse", "--verify", "refs/stash"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _local_restore_stash(
    git_cmd: list[str], cwd: Path, stash_ref: Optional[str]
) -> bool:
    """Local fallback for ``_restore_stashed_changes``."""
    if not stash_ref:
        return True

    list_result = subprocess.run(
        git_cmd + ["stash", "list", "--format=%gd %H"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    selector = None
    for line in list_result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == stash_ref:
            selector = parts[0]
            break

    if not selector:
        print(
            f" ⚠ Could not find autostash {stash_ref}; "
            f"run `git stash list` manually."
        )
        return False

    print(" → Restoring local changes from stash...")
    apply_result = subprocess.run(
        git_cmd + ["stash", "apply", selector],
        cwd=cwd,
    )
    if apply_result.returncode != 0:
        print(
            f" ⚠ Failed to apply autostash {selector}; "
            f"resolve manually with `git stash apply {selector}`."
        )
        return False

    subprocess.run(git_cmd + ["stash", "drop", selector], cwd=cwd, check=True)
    return True


def _git_cmd() -> list[str]:
    """Return the git command list, with Windows atomic-append workaround."""
    base = ["git"]
    if sys.platform == "win32":
        base = ["git", "-c", "windows.appendAtomically=false"]
    return base


# ---------------------------------------------------------------------------
# Phase helpers
# ---------------------------------------------------------------------------


def _check_only(branch: str) -> int:
    """Read-only mode: fetch + rev-list + report behind-count."""
    git_cmd = _git_cmd()
    project_root = PROJECT_ROOT
    git_dir = project_root / ".git"
    if not git_dir.exists():
        print("✗ Not a git repository — cannot check for updates.")
        return 1

    print("→ Fetching from origin...")
    fetch_result = subprocess.run(
        git_cmd + ["fetch", "origin"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if fetch_result.returncode != 0:
        stderr = fetch_result.stderr.strip()
        if "Could not resolve host" in stderr or "unable to access" in stderr:
            print("✗ Network error — cannot reach the remote repository.")
        elif "Authentication failed" in stderr or "could not read Username" in stderr:
            print("✗ Authentication failed — check your git credentials or SSH key.")
        else:
            print("✗ Failed to fetch.")
            if stderr:
                print(f"  {stderr.splitlines()[0]}")
        return 1

    result = subprocess.run(
        git_cmd + ["rev-list", f"HEAD..origin/{branch}", "--count"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    )
    behind = int(result.stdout.strip())
    if behind == 0:
        print("✓ Already up to date.")
    else:
        print(f"⚕ {behind} update(s) available.")
        print("  Run 'janitor update' to install.")
    return 0


def _fetch(git_cmd: list[str], cwd: Path) -> bool:
    """git fetch + error classification. Returns False on failure."""
    print("→ Fetching updates from origin...")
    fetch_result = subprocess.run(
        git_cmd + ["fetch", "origin"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if fetch_result.returncode == 0:
        return True

    stderr = fetch_result.stderr.strip()
    if "Could not resolve host" in stderr or "unable to access" in stderr:
        print("✗ Network error — cannot reach the remote repository.")
    elif "Authentication failed" in stderr or "could not read Username" in stderr:
        print("✗ Authentication failed — check your git credentials or SSH key.")
    else:
        print("✗ Failed to fetch updates from origin.")
        if stderr:
            print(f"  {stderr.splitlines()[0]}")
    return False


def _current_branch(git_cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(
        git_cmd + ["rev-parse", "--abbrev-ref", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _behind_count(git_cmd: list[str], cwd: Path, branch: str) -> int:
    result = subprocess.run(
        git_cmd + ["rev-list", f"HEAD..origin/{branch}", "--count"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return int(result.stdout.strip())


def _pull_with_fallback(git_cmd: list[str], cwd: Path, branch: str) -> bool:
    """Run git pull --ff-only; on divergence reset --hard origin/<branch>.

    Returns True on success, False on hard failure. Performs post-pull
    syntax validation with auto-rollback to the pre-pull SHA on error.
    """
    pre_pull_sha = _call(
        "_capture_head_sha",
        git_cmd,
        cwd,
        fallback=lambda *a, **kw: None,
    )

    print(f"→ Pulling updates from origin/{branch}...")
    pull_result = subprocess.run(
        git_cmd + ["pull", "--ff-only", "origin", branch],
        cwd=cwd,
        capture_output=True,
        text=True,
    )

    if pull_result.returncode != 0:
        print(
            "  ⚠ Fast-forward not possible (history diverged), "
            "resetting to match remote..."
        )
        reset_result = subprocess.run(
            git_cmd + ["reset", "--hard", f"origin/{branch}"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if reset_result.returncode != 0:
            print(f"✗ Failed to reset to origin/{branch}.")
            if reset_result.stderr.strip():
                print(f"  {reset_result.stderr.strip()}")
            print(
                f"  Try manually: git fetch origin && "
                f"git reset --hard origin/{branch}"
            )
            return False

    # Post-pull syntax guard — auto-rollback if pulled code is broken.
    print("→ Running post-pull syntax check...")
    syntax_helper = globals().get("_validate_critical_files_syntax")
    if syntax_helper is not None:
        try:
            syntax_ok, failing_path, syntax_error = syntax_helper(cwd)
        except Exception as exc:
            print(f"  ⚠ Post-pull syntax check skipped: {exc}")
            syntax_ok = True
    else:
        print("  ⚠ Post-pull syntax check skipped: helper unavailable")
        syntax_ok = True

    if not syntax_ok:
        print()
        print("✗ Pulled code has a syntax error in a critical file:")
        if failing_path:
            print(f"  {failing_path}")
        if syntax_error:
            for line in str(syntax_error).splitlines()[:6]:
                print(f"    {line}")
        if pre_pull_sha:
            print()
            print(f"→ Rolling back to {pre_pull_sha[:10]}...")
            rollback_result = subprocess.run(
                git_cmd + ["reset", "--hard", pre_pull_sha],
                cwd=cwd,
                capture_output=True,
                text=True,
            )
            if rollback_result.returncode == 0:
                print("  ✓ Rollback complete — your install is unchanged.")
                print("  Run `janitor update` again later once a fix lands.")
            else:
                print("  ✗ Rollback failed. Recover manually with:")
                print(f"    cd {cwd} && git reset --hard {pre_pull_sha}")
                if rollback_result.stderr.strip():
                    print(f"    ({rollback_result.stderr.strip().splitlines()[0]})")
        else:
            print()
            print("  Could not capture pre-pull SHA — recover manually with:")
            print(f"    cd {cwd} && git reflog && git reset --hard <prev-sha>")
        return False

    return True


def _install_python_dependencies(project_root: Path) -> None:
    """Install Python deps via uv (preferred) or pip fallback."""
    print("→ Updating Python dependencies...")
    pip_cmd = [sys.executable, "-m", "pip"]
    uv_bin = shutil.which("uv") or _call(
        "_ensure_uv_for_termux",
        pip_cmd,
        fallback=lambda *a, **kw: None,
    )
    install_group = "all"

    if uv_bin:
        uv_env = {**os.environ, "VIRTUAL_ENV": str(project_root / "venv")}
        is_termux = _call("_is_termux_env", uv_env, fallback=lambda env: False)
        is_android = _call("_is_android_python", fallback=lambda: False)
        if is_termux:
            uv_env.pop("PYTHONPATH", None)
            uv_env.pop("PYTHONHOME", None)
            install_group = "termux-all"
            print("  → Termux detected: using uv + curated termux-all optional profile...")
        if is_termux and is_android:
            print("  → Termux/Android detected: prebuilding psutil...")
            _call(
                "_install_psutil_android_compat",
                [uv_bin, "pip"],
                env=uv_env,
                fallback=lambda *a, **kw: None,
            )

        def _uv_install(*_a, **_kw):
            subprocess.run(
                [uv_bin, "pip", "install", "--python", sys.prefix, "-e", ".[all]"],
                cwd=project_root,
                check=True,
            )

        _call(
            "_install_python_dependencies_with_optional_fallback",
            [uv_bin, "pip"],
            env=uv_env,
            group=install_group,
            fallback=_uv_install,
        )
    else:
        try:
            subprocess.run(
                pip_cmd + ["--version"],
                cwd=project_root,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            subprocess.run(
                [sys.executable, "-m", "ensurepip", "--upgrade", "--default-pip"],
                cwd=project_root,
                check=True,
            )
        if _call("_is_termux_env", fallback=lambda: False):
            install_group = "termux-all"
            print("  → Termux detected: using curated termux-all optional profile...")
        if _call("_is_termux_env", fallback=lambda: False) and _call(
            "_is_android_python", fallback=lambda: False
        ):
            print("  → Termux/Android detected: prebuilding psutil...")
            _call(
                "_install_psutil_android_compat",
                pip_cmd,
                fallback=lambda *a, **kw: None,
            )

        def _pip_install(*_a, **_kw):
            subprocess.run(
                pip_cmd + ["install", "-e", ".[all]"],
                cwd=project_root,
                check=True,
            )

        _call(
            "_install_python_dependencies_with_optional_fallback",
            pip_cmd,
            env=None,
            group=install_group,
            fallback=_pip_install,
        )

    print("✓ Python dependencies updated")


def _install_node_dependencies(project_root: Path) -> None:
    """Build the TUI (Janitor-specific) + run upstream node update helper."""
    _call(
        "_update_node_dependencies",
        fallback=lambda: None,
    )

    ui_tui_dir = project_root / "ui-tui"
    if (ui_tui_dir / "package.json").exists():
        print("→ Compiling TUI components...")
        subprocess.run(
            ["npm", "install"], cwd=ui_tui_dir, check=True,
        )
        subprocess.run(
            ["npm", "run", "build"], cwd=ui_tui_dir, check=True,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_janitor_update(args) -> int:
    """Canonical Janitor update flow. Mirrors ``_cmd_update_impl``.

    Args:
        args: argparse Namespace from the CLI. Recognised attributes:
            check (bool): if True, only report behind-count and return.
            gateway (bool): suppresses interactive prompts.
            backup (bool): forces a pre-update backup for this run.
            no_backup (bool): skips pre-update backup even if config has it on.
            branch (str|None): target branch (default ``"main"``).

    Returns:
        Process exit code: 0 = updated, 1 = failed, 130 = cancelled.
    """
    _ensure_loaded()

    gateway_mode = bool(getattr(args, "gateway", False))
    branch = getattr(args, "branch", None) or "main"

    _update_io_state = _call(
        "_install_hangup_protection",
        gateway_mode=gateway_mode,
        fallback=lambda **kw: {},
    )

    try:
        if getattr(args, "check", False):
            return _check_only(branch)

        print("⚕ Updating Janitor Agent from fork...")
        print()

        _call("_run_pre_update_backup", args, fallback=lambda _a: None)

        project_root = PROJECT_ROOT
        git_dir = project_root / ".git"
        if not git_dir.exists():
            print("✗ Not a git repository. Please reinstall:")
            print("  git clone https://github.com/reck74/Janitor-Agent.git")
            return 1

        git_cmd = _git_cmd()

        if not _fetch(git_cmd, project_root):
            return 1

        current_branch = _current_branch(git_cmd, project_root)
        auto_stash_ref: Optional[str] = None

        if current_branch != branch:
            label = (
                "detached HEAD"
                if current_branch == "HEAD"
                else f"branch '{current_branch}'"
            )
            print(f"  ⚠ Currently on {label} — switching to {branch} for update...")
            auto_stash_ref = _call(
                "_stash_local_changes_if_needed",
                git_cmd,
                project_root,
                fallback=_local_stash,
            )
            subprocess.run(
                git_cmd + ["checkout", branch],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            auto_stash_ref = _call(
                "_stash_local_changes_if_needed",
                git_cmd,
                project_root,
                fallback=_local_stash,
            )

        commit_count = _behind_count(git_cmd, project_root, branch)
        if commit_count == 0:
            _call("_invalidate_update_cache", fallback=lambda: None)
            print("✓ Already up to date.")
            return 0

        update_succeeded = _pull_with_fallback(git_cmd, project_root, branch)
        if not update_succeeded:
            if auto_stash_ref:
                print(
                    f"  ℹ️  Local changes preserved in stash (ref: {auto_stash_ref})"
                )
                print("  Restore manually with: git stash apply")
            return 1

        _call("_invalidate_update_cache", fallback=lambda: None)

        removed = _call(
            "_clear_bytecode_cache",
            project_root,
            fallback=lambda _r: 0,
        )
        if removed:
            print(
                f"  ✓ Cleared {removed} stale __pycache__ director{'y' if removed == 1 else 'ies'}"
            )

        _install_python_dependencies(project_root)

        _call(
            "_refresh_active_lazy_features",
            fallback=lambda: None,
        )

        _install_node_dependencies(project_root)

        if auto_stash_ref:
            _call(
                "_restore_stashed_changes",
                git_cmd,
                project_root,
                auto_stash_ref,
                fallback=lambda *a, **kw: _local_restore_stash(
                    a[0], a[1], a[2],
                ),
            )

        print()
        print("✓ Janitor Agent updated successfully!")
        print("  Restart Janitor to use the new version.")
        return 0

    except KeyboardInterrupt:
        print("\n✗ Update cancelled.")
        if auto_stash_ref:
            _call(
                "_restore_stashed_changes",
                git_cmd,
                project_root,
                auto_stash_ref,
                fallback=lambda *a, **kw: _local_restore_stash(
                    a[0], a[1], a[2],
                ),
            )
        return 130
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Update failed at step: {e.cmd}")
        if auto_stash_ref:
            _call(
                "_restore_stashed_changes",
                git_cmd,
                project_root,
                auto_stash_ref,
                fallback=lambda *a, **kw: _local_restore_stash(
                    a[0], a[1], a[2],
                ),
            )
        return 1
    finally:
        _call(
            "_finalize_update_output",
            _update_io_state,
            fallback=lambda _s: None,
        )
