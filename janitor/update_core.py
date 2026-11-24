#!/usr/bin/env python3
"""
Janitor update core — the canonical update flow shared by both entry points.

Aligned with the official Hermes ``_cmd_update_impl`` in
``hermes_cli/update_cmd.py``. Both ``janitor update`` (early intercept in
``janitor/cli.py``) and the monkey-patched ``cmd_update`` (also in
``janitor/cli.py``) delegate here.

The 12-step pipeline:

  1. Hangup protection (captures IO state for restore on exit)
  2. Pre-update backup (optional via ``_run_pre_update_backup``)
  3. Discard npm lockfile / CRLF churn, then fetch + branch detection +
     auto-stash + branch switch
  4. Behind-count: if HEAD == origin/branch, skip pull/deps/lazy refresh
     and continue to step 8 (Node repair) for the "already up to date" path.
  5. Pull with ``--ff-only`` fallback to ``reset --hard origin/<branch>``;
     post-pull syntax/import validation; auto-rollback to captured pre-pull SHA
     on syntax failure.
  6. Reload seam: invalidate import caches, clear helper cache and the
     three fresh-wrapper sentinels, rebind the fresh wrappers from the
     freshly-pulled modules. Runs on both the post-pull and the
     already-current paths so a no-pull update also reloads.
  7. Python dependency install via uv/pip, then a check that every BASE
     dependency of the pulled ``pyproject.toml`` is installed in the target
     interpreter (upstream's installer only warns); a miss writes the
     marker with ``failed_step="python_deps"``, keeps the deps-pending flag
     and exits 1. Then lazy-feature/bootstrap refresh and skill catalog.
  8. Node repair (``_update_node_dependencies`` + TUI build). Failures
     write ``update-incomplete.json`` with ``failed_step="node_deps"`` and
     exit 1 — no success banner, no stash restore. Then the ``web/`` build
     (upstream ``_build_web_ui``, non-fatal).
  9. Fresh-wrapper config migration phase (``_run_config_check_fresh`` +
     conditional ``_run_migrate_config_fresh(interactive=False, quiet=True)``).
     Any failure (missing helpers, exception from check / migrate / post-check,
     or still-behind without an explicit support-floor warning) writes the
     marker with ``failed_step="config_migration"`` and exits 1.
 10. Desktop receipt via ``_print_update_completion("✓ Actualización completa")``.
 11. Marker cleanup, stash restore LAST (using persisted marker stash_ref
     as fallback when the current run did not produce a new stash), success
     banner. Cleanup / restore failures return 1 and skip the banner.
     ``--keep-stash`` (the desktop updater, ``scripts/desktop-update/posix.sh``)
     leaves every autostash parked instead of restoring it.
 12. Only on success: ``--gateway`` writes ``.update_exit_code``, then the
     running gateways of THIS checkout are restarted with upstream's
     ``_restart_gateway_fleet_after_update`` (skipped by
     ``--no-gateway-restart``; skipped with a notice when a gateway of the
     same home runs from another checkout). A gateway still on pre-update
     code once the restart settled fails the run (exit 1). The last line of a
     pulled update says when the engine raised the app/engine contract
     (``janitor/desktop-compat.json``). Any other ``--gateway`` exit writes a
     failing ``.update_exit_code``.

All user-facing output is Spanish: it is read in the terminal and streamed
into the chat during a messaging ``/update``.

Helpers from ``hermes_cli.update_cmd`` (``_run_config_check_fresh``,
``_run_migrate_config_fresh``, ``_print_update_completion``) and from
``hermes_cli.main`` (the legacy helpers) are imported lazily so a
partially-broken venv can still recover. The marker file lives at
``hermes_constants.get_hermes_home() / "update-incomplete.json"`` —
profile-safe, never at a hardcoded path.

Per JANITOR FORK DIRECTIVE #13: any change to the update flow lives here,
not inline in ``janitor/cli.py`` or ``janitor/update_bootstrap.py``.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


# Janitor-fork critical files validated by the post-pull syntax guard.
# Upstream's ``_UPDATE_CRITICAL_FILES`` (hermes_cli/update_cmd.py) only lists
# Hermes core files; the fork's entry chain is equally boot-critical for the
# ``janitor`` command — a syntax error here bricks the CLI exactly like a
# broken ``hermes_cli/main.py`` (Task 16 gate A.7 CRITICAL finding). Kept as
# an explicit tuple mirroring upstream's convention. Missing files are
# skipped, so the list stays safe if a fork file is ever retired.
_JANITOR_CRITICAL_FILES = (
    "janitor/__init__.py",
    "janitor/home.py",
    "janitor/cli.py",
    "janitor/update_core.py",
    "janitor/update_bootstrap.py",
    "janitor/version.py",
    "janitor/tips_es.py",
    # Root module the banner touchpoints import the version helper by.
    "janitor_version.py",
)


# Module-level sentinels so tests can monkeypatch.setattr() before any import
# error fires. Real values are loaded lazily via _try_import().
PROJECT_ROOT: Optional[Path] = None
_run_pre_update_backup: Optional[Callable] = None
_install_hangup_protection: Optional[Callable] = None
_finalize_update_output: Optional[Callable] = None
_discard_lockfile_churn: Optional[Callable] = None
_normalize_managed_eol: Optional[Callable] = None
_stash_local_changes_if_needed: Optional[Callable] = None
_restore_stashed_changes: Optional[Callable] = None
_park_stashed_changes: Optional[Callable] = None
_refresh_active_lazy_features: Optional[Callable] = None
_update_node_dependencies: Optional[Callable] = None
_resolve_node_runtime_npm: Optional[Callable] = None
_run_npm_install_deterministic: Optional[Callable] = None
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
# Post-update phases shared with ``hermes update`` (``_finish_pulled_update``):
# the web UI build, the gateway's ``.update_exit_code`` and the fleet restart.
_build_web_ui: Optional[Callable] = None
_write_gateway_update_exit_code: Optional[Callable] = None
_restart_gateway_fleet_after_update: Optional[Callable] = None


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



def _validate_janitor_files_syntax(
    root,
) -> tuple[bool, Optional[str], Optional[str]]:
    """py_compile each Janitor-fork critical file under ``root``.

    Fork-side twin of upstream's ``_validate_critical_files_syntax``
    (hermes_cli/update_cmd.py), restricted to the ``janitor_*`` entry
    chain. Same semantics: compile to a throwaway cfile in a temp dir,
    missing file -> skip, returns ``(ok, failing_path, error_message)``.
    """
    import py_compile
    import tempfile

    root = Path(root)
    with tempfile.TemporaryDirectory(prefix="janitor-syntax-check-") as tmpdir:
        for relpath in _JANITOR_CRITICAL_FILES:
            path = root / relpath
            if not path.exists():
                continue
            cfile = Path(tmpdir) / (relpath.replace("/", "__") + "c")
            try:
                py_compile.compile(str(path), cfile=str(cfile), doraise=True)
            except py_compile.PyCompileError as exc:
                return False, str(path), str(exc)
            except OSError as exc:
                return False, str(path), f"no se pudo leer: {exc}"
    return True, None, None


def _make_fork_syntax_validator(upstream: Optional[Callable]) -> Callable:
    """Wrap the upstream syntax validator to also cover fork files.

    The returned callable first delegates to ``upstream`` (the Hermes core
    guard) and propagates its failure unchanged; on upstream success it
    additionally validates ``_JANITOR_CRITICAL_FILES``. When ``upstream``
    is ``None`` (partially-broken venv / import-order variance observed in
    gate A.7) the fork files are STILL validated — the fork entry chain is
    the part whose breakage bricks ``janitor`` outright.

    A ``_janitor_fork_wrapper`` marker attribute makes the wiring in
    ``_ensure_loaded`` idempotent and lets tests detect the wrapper.
    """

    def _validate_critical_files_syntax_with_fork_files(root):
        if upstream is not None:
            ok, failing_path, error = upstream(root)
            if not ok:
                return ok, failing_path, error
        return _validate_janitor_files_syntax(root)

    _validate_critical_files_syntax_with_fork_files._janitor_fork_wrapper = True  # type: ignore[attr-defined]
    return _validate_critical_files_syntax_with_fork_files


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
        PROJECT_ROOT = helper if helper is not None else Path(__file__).resolve().parent.parent

    lazy_helpers = (
        "_run_pre_update_backup",
        "_install_hangup_protection",
        "_finalize_update_output",
        "_discard_lockfile_churn",
        "_normalize_managed_eol",
        "_stash_local_changes_if_needed",
        "_restore_stashed_changes",
        "_park_stashed_changes",
        "_refresh_active_lazy_features",
        "_update_node_dependencies",
        "_resolve_node_runtime_npm",
        "_run_npm_install_deterministic",
        "_invalidate_update_cache",
        "_clear_bytecode_cache",
        "_validate_critical_files_syntax",
        "_capture_head_sha",
        "_install_python_dependencies_with_optional_fallback",
        "_is_termux_env",
        "_is_android_python",
        "_install_psutil_android_compat",
        "_ensure_uv_for_termux",
        "_build_web_ui",
        "_write_gateway_update_exit_code",
        "_restart_gateway_fleet_after_update",
    )
    for name in lazy_helpers:
        if globals().get(name) is None:
            globals()[name] = _try_import(name)

    # Janitor fork extension (Task 16 A.7 fix): upstream's guard only
    # validates Hermes core files. ALWAYS make the module-level validator
    # the fork-aware wrapper — including when the upstream helper resolved
    # to None — so ``janitor/cli.py`` & friends are checked post-pull.
    # The marker keeps this idempotent across repeated _ensure_loaded()
    # calls; a pre-set value (test stub) is wrapped, not replaced, so its
    # failure signal is preserved and the fork files are still checked.
    syntax_helper = globals().get("_validate_critical_files_syntax")
    if not getattr(syntax_helper, "_janitor_fork_wrapper", False):
        globals()["_validate_critical_files_syntax"] = _make_fork_syntax_validator(
            syntax_helper
        )

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
        print(f" ⚠ Falta el ayudante {name} en esta instalación: se omite ese paso.")
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
        print(" → Limpiando restos de un conflicto anterior...")
        subprocess.run(git_cmd + ["reset"], cwd=cwd, capture_output=True)

    stash_name = datetime.now(timezone.utc).strftime(
        "janitor-update-autostash-%Y%m%d-%H%M%S"
    )
    print(" → El motor tiene cambios locales: se apartan antes de actualizar...")
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
            f" ⚠ No aparece la copia apartada de tus cambios locales ({stash_ref}). "
            f"Búscala con `git stash list`."
        )
        return False

    print(" → Reaplicando tus cambios locales...")
    apply_result = subprocess.run(
        git_cmd + ["stash", "apply", selector],
        cwd=cwd,
    )
    if apply_result.returncode != 0:
        print(
            f" ⚠ Tus cambios locales chocan con la versión nueva y siguen guardados. "
            f"Recupéralos con `git stash apply {selector}`."
        )
        return False

    subprocess.run(git_cmd + ["stash", "drop", selector], cwd=cwd, check=True)
    return True


def _local_park_stash(stash_ref: str) -> None:
    """Local fallback for ``_park_stashed_changes``."""
    print()
    print(" ℹ Tus cambios locales quedaron apartados y no se reaplicaron (--keep-stash).")
    print(f"  Referencia: {stash_ref}")
    print(f"  Para recuperarlos: git stash apply {stash_ref}")


def _settle_stash(
    git_cmd: list[str], cwd: Path, stash_ref: str, keep_stash: bool
) -> Any:
    """Restore an autostash, or leave it parked under ``--keep-stash``.

    ``--keep-stash`` is the desktop updater's mode: local source edits stay in
    ``git stash`` instead of riding along onto the updated code.
    """
    if keep_stash:
        _call("_park_stashed_changes", stash_ref, fallback=_local_park_stash)
        return True
    return _call(
        "_restore_stashed_changes",
        git_cmd,
        cwd,
        stash_ref,
        fallback=lambda *a, **kw: _local_restore_stash(a[0], a[1], a[2]),
    )


def _project_venv(project_root: Path) -> Path:
    """The virtualenv this update installs into.

    The checkout's ``venv`` (desktop app / ``install.sh`` layout,
    ``~/.janitor/hermes-agent/venv``), otherwise the running interpreter's.
    """
    candidate = Path(project_root) / "venv"
    if candidate.is_dir():
        return candidate
    return Path(sys.prefix)


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
        print(_BROKEN_INSTALL_MESSAGE)
        return 1

    print("→ Buscando la versión nueva...")
    fetch_result = subprocess.run(
        git_cmd + ["fetch", "origin"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if fetch_result.returncode != 0:
        _report_fetch_failure(fetch_result.stderr.strip())
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
        print(_UP_TO_DATE_MESSAGE)
    else:
        print(f"⚕ Hay una versión nueva ({behind} cambios).")
        print("  Instálala con `janitor update`.")
    return 0


# The checkout's ``.git`` is gone: the engine cannot be updated in place.
_BROKEN_INSTALL_MESSAGE = (
    "✗ La instalación del motor está dañada (le falta su historial de versiones).\n"
    "  Reinstala Janitor desde la app."
)
_UP_TO_DATE_MESSAGE = "✓ Ya tienes la última versión."
# Marks a line quoted verbatim from git (English, for diagnosis only).
_DETAIL_PREFIX = "Detalle técnico: "


def _report_fetch_failure(stderr: str) -> None:
    """Explain a failed download in the user's terms; git's own stderr
    (English, technical) is shown only for the unclassified case."""
    if "Could not resolve host" in stderr or "unable to access" in stderr:
        print("✗ Sin conexión: no se llega al servidor de actualizaciones.")
        print("  Revisa la red y vuelve a ejecutar `janitor update`.")
    elif "Authentication failed" in stderr or "could not read Username" in stderr:
        print("✗ El servidor de actualizaciones rechazó la descarga (pide credenciales).")
        print("  El motor apunta a un repositorio privado o equivocado: reinstala Janitor desde la app.")
    else:
        print("✗ No se pudo descargar la versión nueva.")
        if stderr:
            print(f"  {_DETAIL_PREFIX}{stderr.splitlines()[0]}")
        print("  Vuelve a ejecutar `janitor update`; si se repite, revisa la conexión.")


def _fetch(git_cmd: list[str], cwd: Path) -> bool:
    """git fetch + error classification. Returns False on failure."""
    print("→ Descargando la versión nueva...")
    fetch_result = subprocess.run(
        git_cmd + ["fetch", "origin"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if fetch_result.returncode == 0:
        return True

    _report_fetch_failure(fetch_result.stderr.strip())
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

    print("→ Instalando la versión nueva...")
    pull_result = subprocess.run(
        git_cmd + ["pull", "--ff-only", "origin", branch],
        cwd=cwd,
        capture_output=True,
        text=True,
    )

    if pull_result.returncode != 0:
        print(
            "  ⚠ La copia local del motor se desvió de la oficial: "
            "se reemplaza por la versión oficial..."
        )
        reset_result = subprocess.run(
            git_cmd + ["reset", "--hard", f"origin/{branch}"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if reset_result.returncode != 0:
            print("✗ No se pudo reemplazar el código del motor por la versión nueva.")
            if reset_result.stderr.strip():
                print(f"  {_DETAIL_PREFIX}{reset_result.stderr.strip().splitlines()[0]}")
            print(
                f"  Revisa el espacio en disco y los permisos de {cwd} "
                f"y vuelve a ejecutar `janitor update`."
            )
            return False

    # Post-pull syntax guard — auto-rollback if pulled code is broken.
    print("→ Comprobando que el código nuevo está sano...")
    syntax_helper = globals().get("_validate_critical_files_syntax")
    if syntax_helper is not None:
        try:
            syntax_ok, failing_path, syntax_error = syntax_helper(cwd)
        except Exception as exc:
            print(f"  ⚠ No se pudo comprobar el código nuevo ({exc}); se sigue.")
            syntax_ok = True
    else:
        print("  ⚠ No se pudo comprobar el código nuevo (falta el ayudante); se sigue.")
        syntax_ok = True

    if not syntax_ok:
        print()
        print("✗ La versión nueva trae un error de sintaxis en un archivo crítico:")
        if failing_path:
            print(f"  {failing_path}")
        if syntax_error:
            for line in str(syntax_error).splitlines()[:6]:
                print(f"    {line}")
        if pre_pull_sha:
            print()
            print("→ Volviendo a la versión anterior...")
            rollback_result = subprocess.run(
                git_cmd + ["reset", "--hard", pre_pull_sha],
                cwd=cwd,
                capture_output=True,
                text=True,
            )
            if rollback_result.returncode == 0:
                print("  ✓ Vuelta atrás hecha: tu instalación queda como estaba.")
                print("  Vuelve a ejecutar `janitor update` más tarde, cuando publiquen el arreglo.")
            else:
                print("  ✗ No se pudo volver atrás. Recupera la versión anterior con:")
                print(f"    cd {cwd} && git reset --hard {pre_pull_sha}")
                if rollback_result.stderr.strip():
                    print(f"    {_DETAIL_PREFIX}{rollback_result.stderr.strip().splitlines()[0]}")
        else:
            print()
            print("  No se guardó la versión anterior; recupérala con:")
            print(f"    cd {cwd} && git reflog && git reset --hard <versión-anterior>")
        return False

    return True


def _resolve_uv_bin(pip_cmd: list[str]) -> Optional[str]:
    """Same uv rungs as ``hermes update``: Hermes' managed uv in
    ``$HERMES_HOME/bin`` (self-updated, installed if missing), then the
    Termux fallback. ``None`` means the pip path."""
    try:
        from hermes_cli.managed_uv import ensure_uv, update_managed_uv
    except Exception:
        uv_bin = None
    else:
        update_managed_uv()
        uv_bin = str(ensure_uv()) or None
    return uv_bin or _call(
        "_ensure_uv_for_termux",
        pip_cmd,
        fallback=lambda *a, **kw: None,
    )


def _install_python_dependencies(project_root: Path) -> None:
    """Install Python deps via uv (preferred) or pip fallback."""
    print("→ Instalando dependencias de Python...")
    pip_cmd = [sys.executable, "-m", "pip"]
    uv_bin = _resolve_uv_bin(pip_cmd)
    install_group = "all"

    if uv_bin:
        uv_env = {**os.environ, "VIRTUAL_ENV": str(_project_venv(project_root))}
        is_termux = _call("_is_termux_env", uv_env, fallback=lambda env: False)
        is_android = _call("_is_android_python", fallback=lambda: False)
        if is_termux:
            uv_env.pop("PYTHONPATH", None)
            uv_env.pop("PYTHONHOME", None)
            install_group = "termux-all"
            print("  → Termux detectado: se usa uv con el perfil termux-all...")
        if is_termux and is_android:
            print("  → Termux/Android detectado: se precompila psutil...")
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
            print("  → Termux detectado: se usa el perfil termux-all...")
        if _call("_is_termux_env", fallback=lambda: False) and _call(
            "_is_android_python", fallback=lambda: False
        ):
            print("  → Termux/Android detectado: se precompila psutil...")
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


# Run in the target interpreter: prints every name whose distribution metadata
# is absent (same probe as upstream's ``_verify_core_dependencies_installed``).
_MISSING_DISTRIBUTIONS_SCRIPT = (
    "import importlib.metadata as md, sys\n"
    "for name in sys.argv[1:]:\n"
    "    try: md.version(name)\n"
    "    except md.PackageNotFoundError: print(name)\n"
)


def _required_dependency_names(project_root: Path) -> Optional[list[str]]:
    """Names of the base ``[project].dependencies`` of the checkout's
    ``pyproject.toml`` whose markers apply to this host.

    Only the base list: optional extras (``.[all]``) may legitimately fail
    to install and upstream tolerates that, so they never count here.
    ``None`` when the file cannot be read (nothing to verify against).
    """
    import re
    import tomllib

    try:
        with (Path(project_root) / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle).get("project", {})
    except (OSError, ValueError):
        return None
    specs = project.get("dependencies") if isinstance(project, dict) else None
    if not isinstance(specs, list):
        return None
    try:
        from packaging.requirements import Requirement
    except ImportError:
        Requirement = None  # type: ignore[assignment]
    names: list[str] = []
    for spec in specs:
        if Requirement is None:
            name = re.split(r"[\s<>=!~;\[(@]", str(spec).strip(), maxsplit=1)[0]
            if name:
                names.append(name)
            continue
        try:
            req = Requirement(str(spec))
            if req.marker is not None and not req.marker.evaluate():
                continue
        except Exception:  # noqa: BLE001 — unparseable spec: nothing reliable to check
            continue
        names.append(req.name)
    return names


def _dependency_target_python(project_root: Path) -> Path:
    """Interpreter the dependency install targeted: the checkout's ``venv``
    (``_project_venv``) when it has one, else the running interpreter."""
    venv = _project_venv(project_root)
    candidate = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return candidate if candidate.exists() else Path(sys.executable)


def _missing_required_dependencies(project_root: Path) -> Optional[list[str]]:
    """Base dependencies absent from the target interpreter after the install.

    ``None`` when ``pyproject.toml`` cannot be read. A probe that cannot run
    (the interpreter is broken) is itself a failed install and is returned as
    one missing entry naming the interpreter.
    """
    names = _required_dependency_names(project_root)
    if names is None:
        return None
    if not names:
        return []
    python = _dependency_target_python(project_root)
    try:
        result = subprocess.run(
            [str(python), "-c", _MISSING_DISTRIBUTIONS_SCRIPT, *names],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"(el intérprete {python} no responde: {exc})"]
    if result.returncode != 0:
        return [f"(el intérprete {python} falla al comprobarlas)"]
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _verify_required_dependencies(project_root: Path) -> bool:
    """True when every base dependency is installed in the target interpreter.

    Upstream's installer only warns when a base dependency is still missing
    after its repairs, so an install can return cleanly with the engine unable
    to start. This is the gate before the update is called done.
    """
    missing = _missing_required_dependencies(project_root)
    if missing is None:
        print("  ⚠ No se pudo leer pyproject.toml: las dependencias de Python quedan sin comprobar.")
        return True
    if missing:
        shown = ", ".join(missing[:8]) + ("..." if len(missing) > 8 else "")
        print(f"✗ Faltan dependencias obligatorias de Python tras instalarlas: {shown}")
        print("  El motor no arrancaría así. Revisa la conexión y vuelve a ejecutar `janitor update`.")
        return False
    print("✓ Dependencias de Python instaladas")
    return True


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
        print("→ Compilando la interfaz de terminal...")
        failures.extend(_build_tui(ui_tui_dir))

    return failures


def _tui_install_context(ui_tui_dir: Path) -> Optional[tuple[Path, tuple[str, ...]]]:
    """``(cwd, extra npm args)`` when the TUI's ``node_modules`` is missing or
    behind the lockfile, else ``None``."""
    try:
        from hermes_cli.main_tui_launch import _tui_need_npm_install, _workspace_root
    except Exception:
        return None
    if not _tui_need_npm_install(ui_tui_dir):
        return None
    ws_root = _workspace_root(ui_tui_dir)
    return ws_root, (() if ws_root == ui_tui_dir else ("--workspace", "ui-tui"))


def _find_npm() -> Optional[str]:
    """Fallback for ``_resolve_node_runtime_npm`` when ``hermes_cli`` cannot be
    imported: the same lookup it delegates to (``find_node_executable``: Hermes'
    managed Node first, then PATH), else ``hermes_platform``'s PATH resolver."""
    try:
        from hermes_constants import find_node_executable
    except Exception:
        find_node_executable = None
    if find_node_executable is not None:
        return find_node_executable("npm")
    try:
        from hermes_platform.resolver import locate_command
    except Exception:
        return None
    command = locate_command("npm").command
    return command[0] if command else None


def _build_tui(ui_tui_dir: Path) -> list[str]:
    # A plain ``npm install`` here re-resolves the whole workspace and rewrites
    # the root package-lock.json on every update; that churn then blocks the
    # stash restore. Upstream's Node step already installs the ui-tui
    # workspace, so only repair a stale node_modules, and never via ``install``.
    npm = _call("_resolve_node_runtime_npm", fallback=_find_npm)
    if not npm:
        return ["ui-tui npm (npm not found)"]

    install = _tui_install_context(ui_tui_dir)
    if install is not None:
        cwd, extra_args = install
        result = _call(
            "_run_npm_install_deterministic",
            npm, cwd, extra_args=extra_args, capture_output=False,
        )
        if result is None or result.returncode != 0:
            return ["ui-tui npm (install)"]

    try:
        subprocess.run([npm, "run", "build"], cwd=ui_tui_dir, check=True)
    except subprocess.CalledProcessError as exc:
        return [f"ui-tui npm ({exc.cmd})"]
    return []


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
            "falta el ayudante que lee la versión de la configuración; no se puede verificar"
        )

    try:
        version_tuple = call_check()
    except Exception as exc:
        raise RuntimeError(f"la lectura de la versión de la configuración falló: {exc}") from exc

    if not (isinstance(version_tuple, tuple) and len(version_tuple) == 2):
        raise RuntimeError(
            f"la lectura de la versión de la configuración devolvió algo inválido: {version_tuple!r}"
        )

    current_ver, latest_ver = version_tuple
    if not (isinstance(current_ver, int) and isinstance(latest_ver, int)):
        raise RuntimeError(
            f"la versión de la configuración no es un número: "
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
        print("  ⚠ No se puede leer la versión de la configuración (falta el ayudante): se deja como está.")
        return (None, None)
    try:
        version_tuple = check_check()
    except Exception as exc:
        print(f"  ⚠ Falló la lectura de la versión de la configuración ({exc!r}): se deja como está.")
        return (None, None)
    if not (isinstance(version_tuple, tuple) and len(version_tuple) == 2):
        print(
            f"  ⚠ La lectura de la versión de la configuración devolvió algo inválido "
            f"({version_tuple!r}): se deja como está."
        )
        return (None, None)
    current_ver, latest_ver = version_tuple
    if not (isinstance(current_ver, int) and isinstance(latest_ver, int)):
        print(
            f"  ⚠ La versión de la configuración no es un número "
            f"({current_ver!r}, {latest_ver!r}): se deja como está."
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
            f"  ⚠ La configuración (v{current_ver}) es más nueva que esta versión "
            f"del motor (v{latest_ver}): se deja como está."
        )
        return {}

    if current_ver == latest_ver:
        return {}

    migrate_fn = globals().get("_run_migrate_config_fresh")
    if migrate_fn is None:
        raise RuntimeError(
            "falta el ayudante que migra la configuración"
        )

    print()
    print(f"  → Migrando la configuración de v{current_ver} a v{latest_ver}...")
    try:
        results = migrate_fn(interactive=False, quiet=True)
    except Exception as exc:
        raise RuntimeError(f"la migración de la configuración falló: {exc}") from exc

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
                f"tras migrar, la configuración quedó en v{post_cur}, por encima "
                f"de la última que conoce el motor (v{post_lat})"
            )
        if post_cur < post_lat:
            if not _support_floor_warning_explains_still_behind(warnings):
                raise RuntimeError(
                    f"la configuración sigue en v{post_cur} (objetivo v{post_lat}) "
                    f"tras migrar, sin un aviso que lo explique"
                )
            print(
                f"  ⚠ La configuración sigue en v{post_cur} (objetivo v{post_lat}): "
                f"es demasiado antigua para migrarla sola; hay que revisarla a mano."
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
    if payload.get("failed_step") not in {"python_deps", "node_deps", "config_migration"}:
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
        print(f"  ⚠ No se pudo guardar la marca de actualización incompleta: {exc}")


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


def _deps_pending_marker(project_root: Path, git_cmd: Optional[list[str]] = None) -> Path:
    """Per-checkout flag: the tree may hold new code whose dependencies are not installed yet.

    Lives in the checkout's own git directory (``git rev-parse
    --absolute-git-dir``: a linked worktree's ``.git`` is a file), so it is
    tied to the checkout and can never be tracked or show up in ``git status``.
    """
    git_dir = project_root / ".git"
    if git_cmd is not None:
        try:
            out = subprocess.run(
                git_cmd + ["rev-parse", "--absolute-git-dir"],
                cwd=project_root, capture_output=True, text=True, timeout=30,
            )
            if out.returncode == 0 and out.stdout.strip():
                git_dir = Path(out.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    return git_dir / "janitor-update-deps-pending"


def _set_deps_pending(project_root: Path, pending: bool, git_cmd: Optional[list[str]] = None) -> None:
    """A failure to persist only loses the resume-after-interruption guarantee,
    never the update — but it is said out loud."""
    marker = _deps_pending_marker(project_root, git_cmd)
    try:
        if pending:
            marker.write_text(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ\n"), encoding="utf-8")
        else:
            marker.unlink(missing_ok=True)
    except OSError as exc:
        print(f"  ⚠ No se pudo {'guardar' if pending else 'quitar'} la marca de actualización a medias: {exc}")


def _head_sha(git_cmd: list[str], project_root: Path) -> Optional[str]:
    try:
        out = subprocess.run(git_cmd + ["rev-parse", "HEAD"], cwd=project_root,
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


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
        print(f"  ⚠ No se pudo quitar la marca de actualización incompleta: {exc}")
        return False
    return True


# Mirrors hermes_cli.update_lock.UPDATE_EXIT_CONCURRENT so the refusal exit
# code survives a venv where that module cannot be imported.
_UPDATE_EXIT_CONCURRENT = 2

# Read-only `hermes update` modes the Janitor flow does not implement. The
# monkey-patched cmd_update receives upstream's parsed args, so these must be
# refused rather than silently turned into a mutating update.
_UNSUPPORTED_READ_ONLY_FLAGS = {
    "plan": "--plan",
    "list_venv_holders": "--list-venv-holders",
}


def parse_update_args(argv: list[str]):
    """Parse ``janitor update`` arguments for the early intercept.

    Only flags the core implements are accepted; anything else is an argparse
    error (exit 2) so a read-only request such as ``--plan`` can never fall
    through to a real update.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="janitor update",
        description="Actualiza el motor de Janitor a la última versión publicada.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Solo dice si hay una versión nueva; no instala nada",
    )
    parser.add_argument(
        "--gateway", action="store_true",
        help="Modo gateway: deja el resultado en archivos (lo usa /update internamente)",
    )
    parser.add_argument(
        "--backup", action="store_true",
        help="Fuerza una copia de seguridad completa antes de actualizar",
    )
    parser.add_argument(
        "--no-backup", action="store_true",
        help="No hace ninguna copia de seguridad antes de actualizar",
    )
    parser.add_argument(
        "--branch", default=None, metavar="NAME",
        help="Actualiza contra esta rama en vez de main",
    )
    # The desktop updater (scripts/desktop-update/posix.sh) always passes
    # these two; the core never prompts, so --yes changes nothing.
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Lo pasa el actualizador de la app; janitor update nunca pregunta",
    )
    parser.add_argument(
        "--keep-stash", action="store_true",
        help="No reaplica los cambios locales tras actualizar; quedan apartados en git stash",
    )
    parser.add_argument(
        "--no-gateway-restart", action="store_true",
        help="Actualiza código y dependencias, pero deja los gateways en marcha con el código anterior",
    )
    return parser.parse_args(argv)


def _acquire_update_lock():
    """Claim the update marker shared with ``hermes update``, the dashboard
    and the desktop/Tauri updaters.

    Returns ``(lock, refusal)``: ``refusal`` is the user-facing message when
    another live update holds the marker. The lock is best-effort — if the
    module cannot be imported (partially-broken venv, early intercept) the
    update proceeds unlocked rather than being blocked.
    """
    try:
        from hermes_cli.update_lock import UpdateLock
    except Exception:
        return None, None
    lock = UpdateLock()
    if not lock.acquire():
        return None, _describe_update_holder(lock.holder)
    return lock, None


def _describe_update_holder(holder) -> str:
    """Spanish refusal naming the running update by age and PID, in place of
    upstream's ``describe_holder`` (which sends the user to ``hermes update``).
    The holder can be the app, a terminal or a ``/update`` from the chat."""
    pid = getattr(holder, "pid", None)
    seconds = int(max(getattr(holder, "age_seconds", 0) or 0, 0))
    minutes = seconds // 60
    since = f"{minutes} min" if minutes else f"{seconds} s"
    who = f" (proceso {pid})" if pid else ""
    return (
        f"✗ Ya hay una actualización en marcha desde hace {since}{who}.\n"
        "  Dos a la vez rompen la instalación. Espera a que termine "
        "y vuelve a ejecutar `janitor update` si hace falta."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _reapply_skill_catalog() -> None:
    """Regenerate every Janitor home's ``skills.external_dirs`` from the pulled catalog.

    The entries are absolute paths into the install tree, and a release may add
    a skill to a template; homes without ``janitor.skills`` are left untouched.
    Imported after the pull so the freshly pulled catalog code and data run;
    never fails the update (``apply_quietly`` logs per home).
    """
    try:
        from janitor.catalog import apply_quietly, janitor_homes

        for home in janitor_homes(get_hermes_home()):
            apply_quietly(home)
    except Exception as exc:  # noqa: BLE001 — a broken catalog must not fail a good pull
        print(f"  ⚠ No se reaplicó el catálogo de skills: {exc}")


# ---------------------------------------------------------------------------
# Post-update phases shared with ``hermes update``
# ---------------------------------------------------------------------------


def _rebuild_web_ui(project_root: Path) -> None:
    """Rebuild ``web/`` with upstream's ``_build_web_ui`` (non-fatal and
    staleness-checked, as ``hermes update`` calls it on both the pulled and the
    already-current path). Never fails the update."""
    web_dir = Path(project_root) / "web"
    if not web_dir.is_dir():
        return
    if globals().get("_build_web_ui") is None:
        print("  ⚠ Falta el ayudante que compila el panel web: web/ no se recompiló.")
        return
    try:
        _call("_build_web_ui", web_dir)
    except Exception as exc:  # noqa: BLE001 — the dashboard build must not fail a good pull
        print(f"  ⚠ El panel web no se recompiló: {exc}")


def _local_write_gateway_exit_code(ok: bool) -> None:
    """Fallback for upstream's ``_write_gateway_update_exit_code``: the gateway's
    ``/update`` watcher waits for this file and reports a timeout without it."""
    try:
        (get_hermes_home() / ".update_exit_code").write_text(
            "0" if ok else "1", encoding="utf-8"
        )
    except (OSError, RuntimeError) as exc:
        print(f"  ⚠ No se pudo dejar el resultado de la actualización para el gateway: {exc}")


def _write_gateway_exit_code(ok: bool) -> None:
    """``--gateway`` mode: write ``$HERMES_HOME/.update_exit_code`` like ``hermes update``."""
    try:
        _call("_write_gateway_update_exit_code", ok, fallback=_local_write_gateway_exit_code)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠ No se pudo dejar el resultado de la actualización para el gateway: {exc}")


def _fleet_runs_stale_code() -> bool:
    """Does a gateway of this install still serve pre-update code? Upstream's
    fleet probe (``collect_fleet_versions``) compares each running gateway's
    stamped ``code_sha`` with this checkout's HEAD; a gateway of another
    checkout is ``external``, never ``stale``. False when the probe fails."""
    try:
        from hermes_cli.update_receipt import collect_fleet_versions

        return any(row.get("state") == "stale" for row in collect_fleet_versions())
    except Exception:
        return False


def _gateways_in_update_scope() -> list[tuple[int, Optional[Path]]]:
    """``(pid, checkout)`` of every running gateway upstream's restart phase
    would touch, discovered and home-scoped with upstream's own helpers.

    Upstream scopes the restart by home only (``hermes_cli/update_fleet_scope.py``):
    the homes this update owns, plus every gateway mapped to their profile PID
    files. The checkout is what ``hermes update``'s fleet probe reads
    (``_gateway_code_root``: the status record's argv, the process'
    ``VIRTUAL_ENV``, exe and argv); ``None`` when it cannot be read.
    """
    from hermes_cli.dashboard_procs import _hermes_home_for_pid
    from hermes_cli.gateway import find_gateway_pids, find_profile_gateway_processes
    from hermes_cli.update_fleet_scope import partition_gateway_pids_by_scope
    from hermes_cli.update_receipt import _gateway_code_root

    pids = list(find_gateway_pids(all_profiles=True))
    mapped = {proc.pid for proc in find_profile_gateway_processes() if proc.pid in pids}
    owned, _other_homes = partition_gateway_pids_by_scope(
        [pid for pid in pids if pid not in mapped]
    )
    rows: list[tuple[int, Optional[Path]]] = []
    for pid in pids:
        if pid not in mapped and pid not in owned:
            continue
        try:
            home = _hermes_home_for_pid(pid)
        except Exception:
            home = None
        rows.append((pid, _gateway_code_root(pid, Path(home) if home else get_hermes_home())))
    return rows


def _restart_gateways_after_update(gateway_mode: bool) -> Any:
    """Restart this install's running gateways onto the updated code.

    Delegates to upstream's ``_restart_gateway_fleet_after_update`` (systemd,
    launchd and manual gateways; drain first; never raises). Upstream scopes by
    home, but one Janitor home can be served by two checkouts (the pre-1.0
    ``janitor-core/.venv`` and the app's ``hermes-agent/venv``), and upstream
    relaunches a stopped manual gateway with THIS install's interpreter. So when
    any in-scope gateway runs from another checkout (or one that cannot be
    read), nothing is restarted. Every failure here is a warning; the caller
    judges the result with ``_stale_gateways_after_restart``.

    Returns upstream's restart outcome, or ``None`` when no restart ran.
    """
    if globals().get("_restart_gateway_fleet_after_update") is None:
        print("  ⚠ Falta el ayudante que reinicia los gateways: reinícialos con `janitor gateway restart`.")
        return None
    try:
        gateways = _gateways_in_update_scope()
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠ No se pudieron listar los gateways en marcha ({exc}): reinícialos con `janitor gateway restart`.")
        return None
    if not gateways:
        return None

    ours = Path(PROJECT_ROOT).resolve()
    foreign = [(pid, root) for pid, root in gateways if root is None or Path(root).resolve() != ours]
    if foreign:
        print("→ No se reinicia ningún gateway: uno de este home corre desde otra instalación.")
        for pid, root in foreign:
            where = root if root is not None else "una instalación que no se pudo identificar"
            print(f"  ↷ PID {pid}: gateway que corre desde {where}; no se toca.")
        print(f"  Los gateways de {ours} siguen con el código anterior hasta que los reinicies (`janitor gateway restart`).")
        return None

    print("→ Reiniciando los gateways con el código nuevo...")
    try:
        outcome = _call("_restart_gateway_fleet_after_update", None, gateway_mode)
    except Exception as exc:  # noqa: BLE001 — upstream never raises; a stale venv might
        print(f"  ⚠ Falló el reinicio de los gateways ({exc}): ejecuta `janitor gateway restart`.")
        return None
    if getattr(outcome, "incomplete", False):
        print("  ⚠ El reinicio de los gateways quedó a medias: revisa `janitor gateway status`.")
    return outcome


def _stale_gateways_after_restart(outcome) -> list[dict]:
    """Gateways still serving pre-update code once the restart settled.

    Upstream's own verification (``_collect_fleet_snapshot``: polls while a
    relaunched gateway has not stamped its ``code_sha`` yet, and marks the
    gateway this update runs inside as ``restart_pending``, not ``stale``).
    Only ``stale`` counts here (design 3.5); a probe that cannot run is a
    warning, never a failure.
    """
    try:
        from hermes_cli.update_cmd_fleet import _collect_fleet_snapshot

        expected = bool(
            getattr(outcome, "restarted_services", None)
            or getattr(outcome, "killed_pids", None)
            or getattr(outcome, "relaunched_profiles", None)
        )
        rows = _collect_fleet_snapshot(outcome, expected)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠ No se pudo comprobar qué código corren los gateways ({exc}).")
        return []
    return [row for row in rows or [] if isinstance(row, dict) and row.get("state") == "stale"]


def _gateway_restart_command(profile: Any) -> str:
    """The exact command that restarts one profile's gateway."""
    if not profile or profile == "default":
        return "janitor gateway restart"
    return f"janitor -p {profile} gateway restart"


def _report_stale_gateways(stale: list[dict]) -> None:
    print()
    print("✗ El motor se actualizó, pero hay gateways que siguen con el código viejo:")
    for row in stale:
        print(f"  PID {row.get('pid')} (perfil {row.get('profile') or 'default'}): {_gateway_restart_command(row.get('profile'))}")
    print("  Ejecuta esa orden; hasta entonces ese gateway puede fallar.")


# Where a Janitor app release is published; the only URL the contract notice prints.
_FORK_RELEASES_URL = "https://github.com/reck74/Janitor-Agent/releases/latest"
_FORK_URL_PREFIX = "https://github.com/reck74/Janitor-Agent/"


def _read_desktop_compat(project_root: Path) -> tuple[Optional[int], str]:
    """``(contract, release_url)`` from the checkout's ``janitor/desktop-compat.json``.

    ``contract`` is ``None`` when the file is absent (an engine older than the
    app/engine contract) or malformed. ``release_url`` falls back to the fork's
    releases page unless the file names a page of the fork itself.
    """
    try:
        payload = json.loads(
            (Path(project_root) / "janitor" / "desktop-compat.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None, _FORK_RELEASES_URL
    if not isinstance(payload, dict):
        return None, _FORK_RELEASES_URL
    contract = payload.get("contract")
    if isinstance(contract, bool) or not isinstance(contract, int):
        contract = None
    url = payload.get("release_url")
    if not (isinstance(url, str) and url.startswith(_FORK_URL_PREFIX) and url.isprintable() and " " not in url):
        url = _FORK_RELEASES_URL
    return contract, url


def _app_update_notice(before: Optional[int], project_root: Path) -> Optional[str]:
    """The closing line when the pulled engine raised the app/engine contract.

    Only a rise between two known contracts counts: with no contract before the
    pull the installed app predates the mechanism and nothing can be compared.
    """
    after, url = _read_desktop_compat(project_root)
    if before is None or after is None or after <= before:
        return None
    return f"Esta versión necesita la app nueva: {url}"


def _installed_version(project_root: Path) -> Optional[str]:
    """Display version of the checkout (``pyproject.toml``), ``None`` if unreadable."""
    import tomllib

    try:
        with (Path(project_root) / "pyproject.toml").open("rb") as handle:
            raw = tomllib.load(handle).get("project", {}).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(raw, str) or not raw:
        return None
    from janitor.version import display_version

    return display_version(raw)


# First line of a successful run; the rest of the line carries the version.
_SUCCESS_LINE = "✓ Janitor actualizado"
# Message handed to upstream's receipt printer (it appends branch @ sha).
_COMPLETION_MESSAGE = "✓ Actualización completa"


def run_janitor_update(args) -> int:
    """Canonical Janitor update flow.

    Args:
        args: argparse Namespace from the CLI. Recognised attributes:
            check (bool): if True, only report behind-count and return.
            gateway (bool): suppresses interactive prompts.
            backup (bool): forces a pre-update backup for this run.
            no_backup (bool): skips pre-update backup even if config has it on.
            branch (str|None): target branch (default ``"main"``).
            keep_stash (bool): leave the autostash parked instead of
                re-applying it (the desktop updater's mode).
            no_gateway_restart (bool): leave running gateways on the old code.
            yes (bool): accepted and ignored; the flow never prompts.

    After a successful update the running gateways of this install are
    restarted onto the new code (pulled path, or already-current when one still
    serves stale code), like ``hermes update``. Under ``--gateway`` the exit
    code is also written to ``$HERMES_HOME/.update_exit_code`` — before the
    restart, which can take this process down with the gateway it runs in.

    Returns:
        Process exit code: 0 = updated, 1 = failed, 2 = another update holds
        the shared update lock or an unsupported read-only mode was requested,
        130 = cancelled.
    """
    unsupported = [
        flag for attr, flag in _UNSUPPORTED_READ_ONLY_FLAGS.items()
        if getattr(args, attr, False)
    ]
    if unsupported:
        print(
            f"✗ `janitor update` no admite {', '.join(unsupported)}. "
            "Para ver si hay una versión nueva: `janitor update --check`."
        )
        return 2

    _ensure_loaded()

    gateway_mode = bool(getattr(args, "gateway", False))
    branch = getattr(args, "branch", None) or "main"
    keep_stash = bool(getattr(args, "keep_stash", False))
    check_only = bool(getattr(args, "check", False))
    gateway_exit_code_written = False

    _update_io_state = _call(
        "_install_hangup_protection",
        gateway_mode=gateway_mode,
        fallback=lambda **kw: {},
    )

    auto_stash_ref: Optional[str] = None
    persisted_stash_ref: Optional[str] = None
    project_root: Optional[Path] = None
    git_cmd: Optional[list[str]] = None
    update_lock = None
    try:
        if check_only:
            return _check_only(branch)

        update_lock, refusal = _acquire_update_lock()
        if refusal is not None:
            print(refusal)
            # The exit-code marker belongs to the update that holds the lock:
            # writing "failed" here would make its watcher announce a failure
            # while the real update is still running.
            gateway_exit_code_written = True
            return _UPDATE_EXIT_CONCURRENT

        print("⚕ Actualizando Janitor...")
        print()

        # If a previous run left a well-formed marker, surface its stash
        # ref so we can restore it LAST when this run produces nothing new.
        persisted_stash_ref = _read_persisted_marker()

        _call("_run_pre_update_backup", args, fallback=lambda _a: None)

        project_root = PROJECT_ROOT
        git_dir = project_root / ".git"
        if not git_dir.exists():
            print(_BROKEN_INSTALL_MESSAGE)
            return 1

        git_cmd = _git_cmd()

        # Before any stash: npm rewrites package-lock.json on every Node
        # repair and CRLF checkouts read as modified. Stashing that churn
        # makes the next run's restore collide with the lockfile npm just
        # rewrote again.
        _call("_discard_lockfile_churn", git_cmd, project_root, fallback=lambda *a: None)
        _call("_normalize_managed_eol", git_cmd, project_root, fallback=lambda *a: None)

        if not _fetch(git_cmd, project_root):
            return 1

        current_branch = _current_branch(git_cmd, project_root)

        if persisted_stash_ref:
            worktree_status = subprocess.run(
                git_cmd + ["status", "--porcelain"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=True,
            )
            if worktree_status.stdout.strip():
                print(
                    "✗ Quedan cambios locales sin recuperar de una actualización "
                    "anterior y el motor tiene cambios nuevos."
                )
                print(f"  Copia pendiente: {persisted_stash_ref}")
                print(
                    "  Recupérala antes de volver a actualizar:\n"
                    "    git stash list\n"
                    f"    git stash apply {persisted_stash_ref}\n"
                    "  Luego guarda o aparta los cambios actuales y vuelve a "
                    "ejecutar `janitor update`."
                )
                return 1

        if current_branch != branch:
            label = (
                "una versión suelta, sin rama"
                if current_branch == "HEAD"
                else f"la rama '{current_branch}'"
            )
            print(f"  ⚠ El motor estaba en {label}: se pasa a '{branch}' para actualizar...")
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
        contract_before: Optional[int] = None

        if already_current:
            _call("_invalidate_update_cache", fallback=lambda: None)
            print(_UP_TO_DATE_MESSAGE)
            # Still run the reload seam so wrappers stay current, plus
            # Node repair, fresh-wrapper config migration, Desktop receipt,
            # marker cleanup, and stash restore per the spec.
        else:
            # Set BEFORE the pull moves HEAD: a run killed anywhere between the
            # pull and the end of the dependency phase must not be mistaken for
            # "already up to date" next time.
            head_before_pull = _head_sha(git_cmd, project_root)
            contract_before, _url = _read_desktop_compat(project_root)
            _set_deps_pending(project_root, True, git_cmd)
            update_succeeded = _pull_with_fallback(git_cmd, project_root, branch)
            if not update_succeeded:
                # Rolled back to where it started: nothing new to install.
                if head_before_pull and _head_sha(git_cmd, project_root) == head_before_pull:
                    _set_deps_pending(project_root, False, git_cmd)
                if auto_stash_ref:
                    print(
                        f"  ℹ Tus cambios locales siguen apartados ({auto_stash_ref}). "
                        f"Para recuperarlos: git stash apply {auto_stash_ref}"
                    )
                return 1

            _call("_invalidate_update_cache", fallback=lambda: None)

            removed = _call(
                "_clear_bytecode_cache",
                project_root,
                fallback=lambda _r: 0,
            )
            if removed:
                print(
                    f"  ✓ Borrada la caché de Python antigua "
                    f"({removed} carpeta{'' if removed == 1 else 's'})"
                )

        # Post-pull / already-current reload seam: invalidate importlib
        # caches, clear the helper cache and the three fresh-wrapper
        # sentinels, rebind the fresh wrappers from the freshly-pulled
        # modules. Runs BEFORE the Node / config phase.
        _reload_helper_modules_after_pull()

        if not already_current or _deps_pending_marker(project_root, git_cmd).exists():
            if already_current:
                print("→ La actualización anterior se cortó antes de instalar dependencias: se retoma.")
            _install_python_dependencies(project_root)
            if not _verify_required_dependencies(project_root):
                # The pending flag stays: the next run reinstalls even if git
                # reports the tree as current.
                _write_incomplete_marker("python_deps", auto_stash_ref)
                return 1

            _call(
                "_refresh_active_lazy_features",
                fallback=lambda: None,
            )

            _reapply_skill_catalog()
            _set_deps_pending(project_root, False, git_cmd)

        # Node repair — fail-loud. Non-empty failure list writes the
        # incomplete marker, prints NO receipt, NO success banner, and does
        # NOT restore the stash.
        print("→ Revisando las dependencias de Node.js...")
        node_failures = _install_node_dependencies(project_root)
        if node_failures:
            print(
                f"✗ Fallaron las dependencias de Node.js: "
                f"{', '.join(node_failures)}"
            )
            print(
                "  Revisa la conexión (npm descarga paquetes) y vuelve a "
                "ejecutar `janitor update`."
            )
            _write_incomplete_marker("node_deps", auto_stash_ref)
            return 1

        _rebuild_web_ui(project_root)

        # Fresh-wrapper config migration phase. Any failure (missing
        # helpers, initial check exception, migration exception, post-check
        # exception, still-behind without an explicit support-floor
        # warning) writes the incomplete marker with
        # failed_step="config_migration" and exits 1 (no success banner,
        # no stash restore).
        print("→ Revisando la configuración...")
        try:
            _run_fresh_config_migration_phase()
        except Exception as mig_exc:
            print(f"✗ Falló la migración de la configuración: {mig_exc}")
            print("  Vuelve a ejecutar `janitor update`.")
            _write_incomplete_marker("config_migration", auto_stash_ref)
            return 1

        # Desktop receipt (only after Node repair + config migration succeeded).
        _call(
            "_print_update_completion",
            _COMPLETION_MESSAGE,
            fallback=lambda _msg: None,
        )

        # Marker cleanup. Failure → return 1 and skip the success banner.
        if not _clear_incomplete_marker():
            print(
                "  ⚠ No se pudo quitar la marca de recuperación. Bórrala a mano:\n"
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
            restored = _settle_stash(
                git_cmd, project_root, stash_to_restore, keep_stash
            )
            if restored is False:
                print(
                    f"  ⚠ No se pudieron reaplicar tus cambios locales ({stash_to_restore}); "
                    f"siguen guardados. Recupéralos con: git stash apply {stash_to_restore}"
                )
                return 1

        # Exit code before the restart: under --gateway this process can live
        # in the gateway's service cgroup and die with it.
        if gateway_mode:
            _write_gateway_exit_code(True)
            gateway_exit_code_written = True
        if getattr(args, "no_gateway_restart", False):
            print("→ Los gateways no se reinician (--no-gateway-restart).")
        elif not already_current or _fleet_runs_stale_code():
            outcome = _restart_gateways_after_update(gateway_mode)
            stale = _stale_gateways_after_restart(outcome) if outcome is not None else []
            if stale:
                # Upstream's rule (hermes_cli/AGENTS.md, "Verify"): a mixed-version
                # fleet is not a healthy update.
                _report_stale_gateways(stale)
                if gateway_mode:
                    _write_gateway_exit_code(False)
                return 1

        version = _installed_version(project_root)
        print()
        print(f"{_SUCCESS_LINE}{f' a la versión {version}' if version else ''}.")
        print("  Reinicia Janitor para usar la versión nueva.")
        if not already_current:
            notice = _app_update_notice(contract_before, project_root)
            if notice:
                print(notice)
        return 0

    except KeyboardInterrupt:
        print("\n✗ Actualización cancelada.")
        if auto_stash_ref and git_cmd is not None and project_root is not None:
            _settle_stash(git_cmd, project_root, auto_stash_ref, keep_stash)
        return 130
    except subprocess.CalledProcessError as e:
        cmd = " ".join(str(part) for part in e.cmd) if isinstance(e.cmd, (list, tuple)) else e.cmd
        print(f"\n✗ La actualización falló en un paso interno ({cmd}).")
        print("  Vuelve a ejecutar `janitor update`.")
        if auto_stash_ref and git_cmd is not None and project_root is not None:
            _settle_stash(git_cmd, project_root, auto_stash_ref, keep_stash)
        return 1
    finally:
        if gateway_mode and not check_only and not gateway_exit_code_written:
            _write_gateway_exit_code(False)
        if update_lock is not None:
            update_lock.release()
        _call(
            "_finalize_update_output",
            _update_io_state,
            fallback=lambda _s: None,
        )
