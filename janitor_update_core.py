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
  6. Reload seam: invalidate import caches, clear helper cache and the
     three fresh-wrapper sentinels, rebind the fresh wrappers from the
     freshly-pulled modules. Runs on both the post-pull and the
     already-current paths so a no-pull update also reloads.
  7. Python dependency install via uv/pip + lazy-feature/bootstrap refresh.
  8. Node repair (``_update_node_dependencies`` + TUI build). Failures
     write ``update-incomplete.json`` with ``failed_step="node_deps"`` and
     exit 1 — no success banner, no stash restore.
  9. Fresh-wrapper config migration phase (``_run_config_check_fresh`` +
     conditional ``_run_migrate_config_fresh(interactive=False, quiet=True)``).
     Any failure (missing helpers, exception from check / migrate / post-check,
     or still-behind without an explicit support-floor warning) writes the
     marker with ``failed_step="config_migration"`` and exits 1.
 10. Desktop receipt via ``_print_update_completion("✓ Update complete!")``.
 11. Marker cleanup, stash restore LAST (using persisted marker stash_ref
     as fallback when the current run did not produce a new stash), success
     banner. Cleanup / restore failures return 1 and skip the banner.

Helpers from ``hermes_cli.update_cmd`` (``_run_config_check_fresh``,
``_run_migrate_config_fresh``, ``_print_update_completion``) and from
``hermes_cli.main`` (the legacy helpers) are imported lazily so a
partially-broken venv can still recover. The marker file lives at
``hermes_constants.get_hermes_home() / "update-incomplete.json"`` —
profile-safe, never at a hardcoded path.

Per JANITOR FORK DIRECTIVE #13: any change to the update flow lives here,
not inline in ``janitor_cli.py`` or ``janitor_update_bootstrap.py``.
"""

from __future__ import annotations

import importlib
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

    Tests can override any of these via ``monkeypatch.setattr()`` before
    the first call. If a helper is None (e.g. venv partially broken),
    the core falls back to a local minimal implementation. The
    three fresh-wrapper sentinels (``_run_config_check_fresh``,
    ``_run_migrate_config_fresh``, ``_print_update_completion``) honour
    an explicit ``None`` so a venv that genuinely lacks them surfaces
    as ``missing helpers`` to the config_migration non-success path.
    """
    global PROJECT_ROOT
    if PROJECT_ROOT is None:
        helper = _try_import("PROJECT_ROOT")
        PROJECT_ROOT = helper if helper is not None else Path(__file__).parent.resolve()

    lazy_helpers = (
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
    )
    for name in lazy_helpers:
        if globals().get(name) is None:
            globals()[name] = _try_import(name)

    fresh_wrappers = (
        "_run_config_check_fresh",
        "_run_migrate_config_fresh",
        "_print_update_completion",
    )
    # The three fresh wrappers are NOT auto-resolved here — they are
    # resolved by the explicit post-pull reload seam (see
    # ``_reload_helper_modules_after_pull``) which clears them and lets the
    # next call re-bind. An explicit ``None`` from a test or a broken
    # venv is preserved as the non-success signal.
    for name in fresh_wrappers:
        if name not in globals():
            globals()[name] = None


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
    without loading the full ``hermes_constants`` module eagerly. The
    canonical ``hermes_constants.get_hermes_home()`` is the primary path.
    Falls back to a non-empty ``$HERMES_HOME`` env var when
    ``hermes_constants`` cannot be imported (a partially-broken venv);
    this is the ONLY fallback — no hardcoded ``$HOME/.janitor`` or
    ``Path.home()`` substitution. Raises when both paths fail so a
    silent wrong-directory write cannot lose user work.
    """
    try:
        from hermes_constants import get_hermes_home as _h
        return Path(_h())
    except Exception:
        hermes_home = os.environ.get("HERMES_HOME", "").strip()
        if hermes_home:
            return Path(hermes_home)
        raise RuntimeError(
            "get_hermes_home failed: hermes_constants is not importable "
            "and HERMES_HOME env var is unset or empty"
        )


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


def _install_node_dependencies(project_root: Path) -> list[str]:
    """Build the TUI (Janitor-specific) + run upstream node update helper.

    Returns the list of labels whose refresh failed (empty on success).
    Matches the upstream ``_update_node_dependencies() -> list[str]``
    contract — non-empty means the Node repair partially failed and the
    caller must treat the update as incomplete (write the node_deps
    marker, return 1, no receipt, no banner, no stash restore).
    """
    failures: list[str] = []
    upstream_result = _call(
        "_update_node_dependencies",
        fallback=lambda: [],
    )
    if isinstance(upstream_result, list):
        failures.extend(x for x in upstream_result if x)

    ui_tui_dir = project_root / "ui-tui"
    if (ui_tui_dir / "package.json").exists():
        print("→ Compiling TUI components...")
        try:
            subprocess.run(
                ["npm", "install"], cwd=ui_tui_dir, check=True,
            )
            subprocess.run(
                ["npm", "run", "build"], cwd=ui_tui_dir, check=True,
            )
        except subprocess.CalledProcessError as exc:
            cmd = exc.cmd
            failures.append(f"ui-tui npm ({cmd})")

    return failures


# Substrings that the real upstream ``hermes_cli.config_migrations.support_floor_message()``
# is guaranteed to contain. We do NOT invent marker tokens here: the contract
# is grounded in the upstream function's actual text. A still-behind
# post-check may legitimately remain behind when ONE of these substrings is
# in the returned warnings — every other still-behind / failure case is
# non-success.
#
# See ``hermes_cli.config_migrations.support_floor_message()``.
_SUPPORT_FLOOR_WARNING_SUBSTRINGS = (
    "predates version",
    "no longer be auto-migrated",
)


def _support_floor_warning_explains_still_behind(warnings: list) -> bool:
    """True iff at least one upstream warning text includes a phrase that
    matches the real ``support_floor_message()`` contract.
    """
    if not warnings:
        return False
    for warning in warnings:
        if not warning:
            continue
        text = str(warning).lower()
        if any(marker in text for marker in _SUPPORT_FLOOR_WARNING_SUBSTRINGS):
            return True
    return False


def _read_config_version_strict(call_check: Callable[[], tuple]) -> tuple:
    """Call the check wrapper and validate the tuple shape strictly.

    Returns (current_ver, latest_ver) on success. Raises RuntimeError
    on any non-success: missing wrapper, exception, malformed tuple,
    non-integer versions, current > latest (the last is a failure ONLY
    during a post-check; callers control the exception policy). Use
    this for POST-CHECK validation where any non-success is a failure.
    """
    check_fn = globals().get("_run_config_check_fresh")
    if check_fn is None:
        raise RuntimeError(
            "fresh config check wrapper is unavailable; cannot verify schema"
        )

    try:
        version_tuple = call_check()
    except Exception as exc:
        raise RuntimeError(f"config version check raised: {exc}") from exc

    if not (isinstance(version_tuple, tuple) and len(version_tuple) == 2):
        raise RuntimeError(
            f"config version check returned non-tuple: {version_tuple!r}"
        )

    current_ver, latest_ver = version_tuple
    if not (isinstance(current_ver, int) and isinstance(latest_ver, int)):
        raise RuntimeError(
            f"config version check returned non-integer values: "
            f"{current_ver!r}, {latest_ver!r}"
        )
    return current_ver, latest_ver


def _read_config_version_initial(check_check: Callable[[], tuple]):
    """Initial-check variant: warn and return ``(None, None)`` for
    invalid / malformed values instead of raising. The brief requires
    invalid initial values to warn and leave config untouched, not
    fail. The post-check policy is strict (see
    ``_read_config_version_strict``).

    Returns a ``(current_ver, latest_ver)`` tuple of ints on success
    or ``(None, None)`` on any non-success. A None result triggers the
    warn-and-no-op branch in the caller.
    """
    check_fn = globals().get("_run_config_check_fresh")
    if check_fn is None:
        print("  ⚠ Initial config check wrapper unavailable; skipping migration.")
        return (None, None)
    try:
        version_tuple = check_check()
    except Exception as exc:
        print(f"  ⚠ Initial config check raised {exc!r}; skipping migration.")
        return (None, None)
    if not (isinstance(version_tuple, tuple) and len(version_tuple) == 2):
        print(
            f"  ⚠ Initial config check returned non-tuple: "
            f"{version_tuple!r}; skipping migration."
        )
        return (None, None)
    current_ver, latest_ver = version_tuple
    if not (isinstance(current_ver, int) and isinstance(latest_ver, int)):
        print(
            f"  ⚠ Initial config check returned non-integer values: "
            f"{current_ver!r}, {latest_ver!r}; skipping migration."
        )
        return (None, None)
    return (current_ver, latest_ver)


def _run_fresh_config_migration_phase() -> dict:
    """Run the fresh-wrapper config migration phase after a successful pull.

    Uses ``hermes_cli.update_cmd._run_config_check_fresh`` and
    ``_run_migrate_config_fresh`` so the freshly-pulled config modules are
    read — not the stale cached ones from before the pull.

    Behavior contract:

    - Initial check: ``current > latest`` is a benign no-op (warn only;
      no migration, no failure). Config already at a newer version than
      the wrapper knows about is left alone.
    - Initial check: invalid values (non-int / non-tuple / wrapper raises
      / wrapper unavailable) are a warn-and-no-op — the config is left
      untouched. (Round 3/5 brief: invalid initial values warn + no-op.)
    - Initial check: migrate only when ``current < latest`` and both are
      integers.
    - Post-check: ``current > latest`` is a HARD failure (migration
      should have put us AT latest, never over — a downgrade must not
      be silently accepted).
    - Post-check: invalid values / non-int / non-tuple are a HARD
      failure — strict.
    - Post-check: ``current == latest`` is a no-op (success branch).
    - Post-check: ``current < lat`` is a still-behind. Allowed ONLY when
      the warnings explicitly explain a support-floor refusal; every
      other still-behind / failure case is non-success.
    - Consume ``results.get("warnings", [])`` defensively.
    - Raise ``RuntimeError`` on every non-success path: missing helpers,
      post-check exception, malformed tuple, non-int versions, post-check
      downgrade, post-check still-behind without a recognised
      support-floor warning.

    Returns the migration results dict (or ``{}`` on a clean no-op).
    """
    initial = _read_config_version_initial(globals().get("_run_config_check_fresh"))
    current_ver, latest_ver = initial
    if current_ver is None or latest_ver is None:
        # Initial check was invalid: warn-and-no-op per Round 3/5 brief.
        return {}

    if current_ver > latest_ver:
        # Initial check — downgrade is a benign no-op.
        print(
            f"  ⚠ Config version {current_ver} > latest {latest_ver} — "
            f"leaving config untouched (downgrade detected)."
        )
        return {}

    if current_ver == latest_ver:
        return {}

    migrate_fn = globals().get("_run_migrate_config_fresh")
    if migrate_fn is None:
        raise RuntimeError(
            "fresh config migrate wrapper is unavailable; cannot run migration"
        )

    print()
    print(f"  → Migrating config v{current_ver} → v{latest_ver}...")
    try:
        results = migrate_fn(interactive=False, quiet=True)
    except Exception as exc:
        raise RuntimeError(f"config migration raised: {exc}") from exc

    if not isinstance(results, dict):
        results = {}

    warnings = list(results.get("warnings", []) or [])
    for warning in warnings:
        if warning:
            print(f"  ⚠ {warning}")

    # Fresh post-check after a supported migration. Post-check policy is
    # strict (Round 3/5 brief): malformed / non-int / wrapper raises /
    # current > latest are all non-success.
    try:
        post_cur, post_lat = _read_config_version_strict(
            globals().get("_run_config_check_fresh")
        )
    except RuntimeError:
        raise

    # POST-check ``current > latest`` is a HARD failure: migration should
    # have moved us AT or PAST the wrapper's latest version, never over
    # to a wrap-around / downgrade state. Silently accepting it would
    # leave the user with a config the wrapper thinks is at a future
    # version — refuse loudly.
    if isinstance(post_cur, int) and isinstance(post_lat, int):
        if post_cur > post_lat:
            raise RuntimeError(
                f"post-migration config version {post_cur} > latest "
                f"{post_lat}; the migration result exceeded the wrapper's "
                f"latest version — refusing silently"
            )
        if post_cur < post_lat:
            if not _support_floor_warning_explains_still_behind(warnings):
                raise RuntimeError(
                    f"config still at v{post_cur} (target v{post_lat}) "
                    f"after migration; warnings did not explain a "
                    f"support-floor refusal"
                )
            print(
                f"  ⚠ Config still at v{post_cur} (target v{post_lat}) "
                f"after migration; support-floor refusal — manual step "
                f"required."
            )

    return results


def _reload_helper_modules_after_pull() -> None:
    """Post-pull helper / module reload seam.

    After a successful ``git pull`` (or the equivalent already-current
    path), evict the helper modules from ``sys.modules`` (so a stale
    cached copy cannot be served), invalidate ``importlib``'s caches,
    clear the in-process helper cache and the three fresh-wrapper
    sentinels, and rebind the fresh wrappers from the freshly-loaded
    modules so the next phase reads the updated code.
    """
    importlib.invalidate_caches()
    _HELPER_CACHE.clear()
    for name in (
        "_run_config_check_fresh",
        "_run_migrate_config_fresh",
        "_print_update_completion",
    ):
        globals()[name] = None
    globals().pop("_run_config_check_fresh", None)
    globals().pop("_run_migrate_config_fresh", None)
    globals().pop("_print_update_completion", None)

    # EVICT the helper modules from ``sys.modules``. ``importlib.invalidate_caches``
    # alone is NOT enough: ``importlib.import_module`` returns the cached
    # entry from ``sys.modules`` if present, so a stale copy would survive
    # invalidation. The seam MUST also del the module entry to force a
    # genuine re-import from disk.
    for mod_name in (
        "hermes_cli.update_cmd",
        "hermes_cli.config_migrations",
        "hermes_cli.config",
        "hermes_cli.config_defaults",
        "hermes_cli.main",
        "hermes_cli",
    ):
        sys.modules.pop(mod_name, None)

    # Re-resolve via the existing lazy-import path so the new code is loaded.
    for name in (
        "_run_config_check_fresh",
        "_run_migrate_config_fresh",
        "_print_update_completion",
    ):
        try:
            globals()[name] = _try_import(name)
        except Exception:
            globals()[name] = None


def _read_persisted_marker() -> Optional[str]:
    """Read and validate an existing ``update-incomplete.json``.

    Returns the persisted ``stash_ref`` when the marker is well-formed
    (exact key set, allowed ``failed_step``, parseable UTC ISO 8601 ``Z``
    timestamp) and ``None`` otherwise. A well-formed marker is the only
    signal the current run can use to restore a stash from a prior
    failed run when this run produced nothing new to stash.

    Accepts BOTH the compact (``YYYYMMDDTHHMMSSZ``) and the dashed
    (``YYYY-MM-DDTHH:MM:SSZ``) UTC ``Z``-suffixed timestamp shapes so
    legacy markers written by older / partial installs are still
    recognised.
    """
    marker = get_hermes_home() / "update-incomplete.json"
    if not marker.exists():
        return None
    try:
        payload = json.loads(marker.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if set(payload.keys()) != {"stash_ref", "failed_step", "timestamp"}:
        return None
    if payload.get("failed_step") not in {"node_deps", "config_migration"}:
        return None
    ts = payload.get("timestamp")
    if not isinstance(ts, str) or not ts.endswith("Z"):
        return None
    parsed = False
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y%m%dT%H%M%SZ"):
        try:
            datetime.strptime(ts, fmt)
            parsed = True
            break
        except ValueError:
            continue
    if not parsed:
        return None
    stash_ref = payload.get("stash_ref")
    return stash_ref if isinstance(stash_ref, (str, type(None))) else None


def _write_incomplete_marker(failed_step: str, stash_ref: Optional[str]) -> None:
    """Write ``update-incomplete.json`` at ``get_hermes_home()``.

    Profile-safe location; not at a hardcoded ``$HERMES_HOME``. The marker
    records the stash ref, the failed step, and a UTC ISO 8601 timestamp
    with ``Z`` suffix. A later successful rerun removes this file (see
    ``_clear_incomplete_marker``).

    The persisted marker schema is fixed at three keys — no expansion.
    Never overwrite a recoverable stash_ref with another: when a prior
    stash_ref is already on disk (from a prior failed run), the prior is
    ALWAYS preserved as the persisted stash_ref on disk. This run's
    new stash_ref, if any, is held in memory only and is restored at the
    end of the run alongside the prior (the prior LAST). The
    ``failed_step`` / ``timestamp`` fields reflect THIS run.

    Net effect: the on-disk marker is the persistent recovery contract
    anchored to the EARLIEST FAILED run's ref. A new failed run adds its
    ref in memory; the persistent ref is not overwritten.
    """
    marker = get_hermes_home() / "update-incomplete.json"
    prior = _read_persisted_marker_raw(marker)
    if prior is not None:
        # The prior is ALWAYS preserved on disk — never overwrite one
        # recoverable ref with another. If this run also has a new ref,
        # the new ref is in memory only and is restored from
        # ``auto_stash_ref`` alongside the prior at end-of-run.
        stash_ref = prior
    payload = {
        "stash_ref": stash_ref,
        "failed_step": failed_step,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        marker.write_text(json.dumps(payload))
    except OSError as exc:
        print(f"  ⚠ Could not write incomplete-update marker: {exc}")


def _read_persisted_marker_raw(marker_path: Path) -> Optional[str]:
    """Read the prior marker's stash_ref without validation, for the
    preserve-on-write path. Returns ``None`` if absent or malformed.
    """
    try:
        payload = json.loads(marker_path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    stash_ref = payload.get("stash_ref")
    return stash_ref if isinstance(stash_ref, (str, type(None))) else None


def _clear_incomplete_marker() -> bool:
    """Remove ``update-incomplete.json`` if present.

    Returns True on success (including when no marker was present) and
    False when the marker existed but could not be removed. The caller
    must NOT print the success banner when this returns False.
    """
    marker = get_hermes_home() / "update-incomplete.json"
    try:
        marker.unlink()
    except FileNotFoundError:
        return True
    except OSError as exc:
        print(f"  ⚠ Could not remove incomplete-update marker: {exc}")
        return False
    return True


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
    persisted_stash_ref: Optional[str] = None
    project_root: Optional[Path] = None
    git_cmd: Optional[list[str]] = None
    try:
        if getattr(args, "check", False):
            return _check_only(branch)

        print("⚕ Updating Janitor Agent from fork...")
        print()

        # If a previous run left a well-formed marker, surface its stash
        # ref so we can restore it LAST when this run produces nothing new.
        persisted_stash_ref = _read_persisted_marker()

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
            # Still run the reload seam so wrappers stay current, plus
            # Node repair, fresh-wrapper config migration, Desktop receipt,
            # marker cleanup, and stash restore per the spec.
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

        # Post-pull / already-current reload seam: invalidate importlib
        # caches, clear the helper cache and the three fresh-wrapper
        # sentinels, rebind the fresh wrappers from the freshly-pulled
        # modules. Runs BEFORE the Node / config phase.
        _reload_helper_modules_after_pull()

        if not already_current:
            _install_python_dependencies(project_root)

            _call(
                "_refresh_active_lazy_features",
                fallback=lambda: None,
            )

        # Node repair — fail-loud. Non-empty failure list writes the
        # incomplete marker, prints NO receipt, NO success banner, and does
        # NOT restore the stash.
        print("→ Repairing Node.js dependencies...")
        node_failures = _install_node_dependencies(project_root)
        if node_failures:
            print(
                f"  ⚠ Node.js dependency refresh failed: "
                f"{', '.join(node_failures)}"
            )
            print(
                "  Stash is preserved for manual recovery — re-run\n"
                "  `janitor update` after repairing the install."
            )
            _write_incomplete_marker("node_deps", auto_stash_ref)
            return 1

        # Fresh-wrapper config migration phase. Any failure (missing
        # helpers, initial check exception, migration exception, post-check
        # exception, still-behind without an explicit support-floor
        # warning) writes the incomplete marker with
        # failed_step="config_migration" and exits 1 (no success banner,
        # no stash restore).
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

        # Marker cleanup. Failure → return 1 and skip the success banner.
        if not _clear_incomplete_marker():
            print(
                "  ⚠ Could not remove the recovery marker. Manually delete:\n"
                f"    {get_hermes_home() / 'update-incomplete.json'}"
            )
            return 1

        # Stash restore LAST. When this run AND a persisted marker
        # both carry a stash_ref, restore BOTH — the current run's
        # ``auto_stash_ref`` first (in run order), then the persisted
        # one LAST. The persisted marker is the recovery contract from
        # a prior failed run; the current run's stash is the live
        # workspace snapshot. Restoring both preserves user work across
        # repeated reruns. Restore failure → return 1 and skip the
        # success banner.
        restore_sequence = []
        if auto_stash_ref:
            restore_sequence.append(auto_stash_ref)
        if (
            persisted_stash_ref
            and persisted_stash_ref != auto_stash_ref
        ):
            # Persisted LAST — per marker contract.
            restore_sequence.append(persisted_stash_ref)

        for stash_to_restore in restore_sequence:
            restored = _call(
                "_restore_stashed_changes",
                git_cmd,
                project_root,
                stash_to_restore,
                fallback=lambda *a, **kw: _local_restore_stash(
                    a[0], a[1], a[2],
                ),
            )
            if restored is False:
                print(
                    f"  ⚠ Failed to restore stash (ref: {stash_to_restore}). "
                    f"Resolve manually with: git stash apply {stash_to_restore}"
                )
                return 1

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
