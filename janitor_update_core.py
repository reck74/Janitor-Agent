#!/usr/bin/env python3
"""
Janitor update core — the canonical update flow shared by both entry points.

Aligned with the official Hermes ``_cmd_update_impl`` in
``hermes_cli/update_cmd.py``. Both ``janitor update`` (early intercept in
``janitor_cli.py``) and the monkey-patched ``cmd_update`` (also in
``janitor_cli.py``) delegate here.

The 11-step pipeline:

  1. Hangup protection (captures IO state for restore on exit)
  2. Pre-update backup (optional via ``_run_pre_update_backup``)
  3. Fetch + branch detection + auto-stash + branch switch
  4. Behind-count: if HEAD == origin/branch, skip pull/deps/lazy refresh
     and continue to step 8 (Node repair) for the "already up to date" path.
  5. Pull with ``--ff-only`` fallback to ``reset --hard origin/<branch>``;
     post-pull syntax/import validation; auto-rollback to captured pre-pull SHA
     on syntax failure.
  6. Invalidate update cache + clear stale ``__pycache__``.
  7. Python dependency install via uv/pip + lazy-feature/bootstrap refresh.
  8. Node repair (``_update_node_dependencies`` + TUI build). Failures
     write ``update-incomplete.json`` with ``failed_step="node_deps"`` and
     exit 1 — no success banner, no stash restore.
  9. Fresh-wrapper config migration phase (``_run_config_check_fresh`` +
     conditional ``_run_migrate_config_fresh(interactive=False, quiet=True)``).
     Migrate only when both versions are integers and ``current < latest``;
     warn and leave config untouched otherwise. Failures write the marker
     with ``failed_step="config_migration"`` and exit 1.
 10. Desktop receipt via ``_print_update_completion("✓ Update complete!")``.
 11. Marker cleanup, stash restore LAST, success banner.

Helpers from ``hermes_cli.update_cmd`` (``_run_config_check_fresh``,
``_run_migrate_config_fresh``, ``_print_update_completion``) and from
``hermes_cli.main`` (the legacy helpers) are imported lazily so a
partially-broken venv can still recover. The marker file lives at
``get_hermes_home() / "update-incomplete.json"`` — profile-safe, never at a
hardcoded ``$HERMES_HOME``.

Per JANITOR FORK DIRECTIVE #13: any change to the update flow lives here,
not inline in ``janitor_cli.py`` or ``janitor_update_bootstrap.py``.
"""

from __future__ import annotations

import json
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
# Fresh-wrapper helpers from hermes_cli.update_cmd.
_run_config_check_fresh: Optional[Callable] = None
_run_migrate_config_fresh: Optional[Callable] = None
_print_update_completion: Optional[Callable] = None


# Lazy-import cache: only try each helper once per process.
_HELPER_CACHE: dict[str, Any] = {}


def _try_import(name: str) -> Any:
    """Lazy-import a single helper from ``hermes_cli.main`` or
    ``hermes_cli.update_cmd``.

    Returns the helper or ``None`` if the import fails. Cached.
    """
    if name in _HELPER_CACHE:
        return _HELPER_CACHE[name]
    helper: Any = None
    for module_name in ("hermes_cli.update_cmd", "hermes_cli.main"):
        try:
            import importlib
            mod = importlib.import_module(module_name)
            candidate = getattr(mod, name, None)
            if candidate is not None:
                helper = candidate
                break
        except Exception:
            continue
    _HELPER_CACHE[name] = helper
    return helper


def _ensure_loaded() -> None:
    """Populate module-level sentinels from hermes_cli on first use.

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
        "_run_config_check_fresh",
        "_run_migrate_config_fresh",
        "_print_update_completion",
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
# Profile-safe path helper
# ---------------------------------------------------------------------------


def get_hermes_home() -> Path:
    """Profile-safe Janitor/Hermes home directory.

    Imports lazily so a partially-broken venv can still call this helper
    without loading the full ``hermes_constants`` module eagerly.
    """
    try:
        from hermes_constants import get_hermes_home as _h
        return Path(_h())
    except Exception:
        return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".janitor")))


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
    """Build the TUI (Janitor-specific) + run upstream node update helper.

    Raises on failure so the caller can write the incomplete marker and
    abort the update.
    """
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


def _run_fresh_config_migration_phase() -> dict:
    """Run the fresh-wrapper config migration phase after a successful pull.

    Uses ``hermes_cli.update_cmd._run_config_check_fresh`` and
    ``_run_migrate_config_fresh`` so the freshly-pulled config modules are
    read — not the stale cached ones from before the pull.

    Behavior contract:

    - Migrate only when both versions are integers and ``current < latest``.
    - Warn and leave config untouched for invalid version values.
    - Warn and leave config untouched on downgrade (``current > latest``).
    - On ``current == latest``, no-op (no warning).
    - Consume ``results.get("warnings", [])`` defensively (a support-floor
      refusal is not an exception).
    - Run a fresh post-check after a supported migration.

    Returns the migration results dict (or ``{}`` on no-op).
    """
    check_fn = globals().get("_run_config_check_fresh")
    if check_fn is None:
        return {}

    try:
        version_tuple = check_fn()
    except Exception as exc:
        print(f"  ⚠ Config version check failed: {exc}")
        return {}

    if not (isinstance(version_tuple, tuple) and len(version_tuple) == 2):
        return {}

    current_ver, latest_ver = version_tuple
    if not (isinstance(current_ver, int) and isinstance(latest_ver, int)):
        print(
            f"  ⚠ Config version check returned non-integer values: "
            f"{current_ver!r}, {latest_ver!r}"
        )
        return {}

    if current_ver > latest_ver:
        print(
            f"  ⚠ Config version {current_ver} > latest {latest_ver} — "
            f"leaving config untouched (downgrade detected)."
        )
        return {}

    if current_ver == latest_ver:
        return {}

    migrate_fn = globals().get("_run_migrate_config_fresh")
    if migrate_fn is None:
        return {}

    print()
    print(f"  → Migrating config v{current_ver} → v{latest_ver}...")
    results = migrate_fn(interactive=False, quiet=True)

    if not isinstance(results, dict):
        results = {}

    for warning in results.get("warnings", []) or []:
        if warning:
            print(f"  ⚠ {warning}")

    # Fresh post-check after a supported migration.
    try:
        post = check_fn()
        if isinstance(post, tuple) and len(post) == 2:
            cur, lat = post
            if (
                isinstance(cur, int)
                and isinstance(lat, int)
                and cur < lat
            ):
                print(
                    f"  ⚠ Config still at v{cur} (target v{lat}) after migration; "
                    f"a manual step may be required."
                )
    except Exception as exc:
        print(f"  ⚠ Post-migration config check failed: {exc}")

    return results


def _write_incomplete_marker(failed_step: str, stash_ref: Optional[str]) -> None:
    """Write ``update-incomplete.json`` at ``get_hermes_home()``.

    Profile-safe location; not at a hardcoded ``$HERMES_HOME``. The marker
    records the stash ref, the failed step, and a UTC ISO 8601 timestamp with
    ``Z`` suffix. A later successful rerun removes this file (see
    ``_clear_incomplete_marker``).
    """
    marker = get_hermes_home() / "update-incomplete.json"
    payload = {
        "stash_ref": stash_ref,
        "failed_step": failed_step,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        marker.write_text(json.dumps(payload))
    except OSError as exc:
        print(f"  ⚠ Could not write incomplete-update marker: {exc}")


def _clear_incomplete_marker() -> None:
    """Remove ``update-incomplete.json`` if present."""
    marker = get_hermes_home() / "update-incomplete.json"
    try:
        marker.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        print(f"  ⚠ Could not remove incomplete-update marker: {exc}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_janitor_update(args) -> int:
    """Canonical Janitor update flow.

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

    auto_stash_ref: Optional[str] = None
    project_root: Optional[Path] = None
    git_cmd: Optional[list[str]] = None
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
                fallback=lambda *a, **kw: _local_stash(git_cmd, a[1]),
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
                fallback=lambda *a, **kw: _local_stash(git_cmd, a[1]),
            )

        commit_count = _behind_count(git_cmd, project_root, branch)
        already_current = (commit_count == 0)

        if already_current:
            _call("_invalidate_update_cache", fallback=lambda: None)
            print("✓ Already up to date.")
            # Still run Node repair, fresh-wrapper config migration, Desktop
            # receipt, marker cleanup, and stash restore per the spec.
        else:
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

        # Node repair — fail-loud. Failure writes the incomplete marker,
        # prints no success banner, and does NOT restore the stash.
        print("→ Repairing Node.js dependencies...")
        try:
            _install_node_dependencies(project_root)
        except Exception as node_exc:
            print(f"  ⚠ Node.js dependency refresh failed: {node_exc}")
            print(
                "  Stash is preserved for manual recovery — re-run\n"
                "  `janitor update` after repairing the install."
            )
            _write_incomplete_marker("node_deps", auto_stash_ref)
            return 1

        # Fresh-wrapper config migration phase. Migrate only when both
        # versions are integers and current < latest. Failures here write
        # the incomplete marker with failed_step="config_migration" and
        # exit 1 (no success banner, no stash restore).
        print("→ Running fresh config migration check...")
        try:
            _run_fresh_config_migration_phase()
        except Exception as mig_exc:
            print(f"  ⚠ Config migration failed: {mig_exc}")
            print(
                "  Manual recovery: re-run `janitor update` or run the\n"
                "  bundled migration script directly:\n"
                "    bash scripts/migrate-janitor-v0.20.1.sh"
            )
            _write_incomplete_marker("config_migration", auto_stash_ref)
            return 1

        # Desktop receipt (only after Node repair + config migration succeeded).
        _call(
            "_print_update_completion",
            "✓ Update complete!",
            fallback=lambda _msg: None,
        )

        # Marker cleanup (safe — only deletes the marker if no failure
        # occurred above).
        _clear_incomplete_marker()

        # Stash restore LAST — after Node repair, config migration,
        # fresh-wrapper config phase, receipt, and marker cleanup.
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
        if auto_stash_ref and git_cmd is not None and project_root is not None:
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
        if auto_stash_ref and git_cmd is not None and project_root is not None:
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