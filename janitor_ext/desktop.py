"""Janitor's distribution-owned Linux Desktop build and CLI launch policy."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def _artifact(root: Path) -> Path | None:
    """Select this distribution/version/architecture, never a Hermes package."""
    metadata = json.loads((root / "janitor_ext/release.json").read_text(encoding="utf-8"))
    architecture = {"x86_64": ("x86_64", "x64"), "aarch64": ("arm64", "aarch64")}.get(platform.machine(), ())
    for suffix in architecture:
        candidate = root / "apps/desktop/release" / f"janitor-desktop-{metadata['janitorVersion']}-linux-{suffix}.AppImage"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def build_desktop_product(project_root: Path, env: dict, publish_stage) -> None:
    """The fresh PM completion calls this distribution seam, never a core fork."""
    if env.get("_JANITOR_SKIP_DESKTOP_BUILD") == "1" or os.environ.get("_JANITOR_SKIP_DESKTOP_BUILD") == "1":
        print("  ✓ Janitor Desktop is managed by the verified AppImage transaction; updating runtime only")
        return
    if sys.platform != "linux":
        raise RuntimeError("Janitor Desktop currently builds Linux AppImages only")
    from hermes_cli.desktop_build_lock import DesktopBuildLock
    root = Path(project_root).resolve()
    lock = DesktopBuildLock(root)
    lock.acquire(wait=True)
    try:
        _run_overlay(root, env, publish_stage)
    finally:
        lock.release()


def _run_overlay(root: Path, env: dict, publish_stage) -> None:
    from hermes_cli.source_build import run_source_script
    publish_stage("Building Janitor Desktop")
    run_source_script(root, "apps/desktop/janitor/build.mjs", env=env, label="Building Janitor Desktop AppImage")
    if _artifact(root) is None:
        raise RuntimeError("Janitor Desktop build produced no executable AppImage for this architecture")


def install_cli_adapter(main_module) -> None:
    """Keep parser and engine untouched; Janitor owns the native product command."""
    def desktop(args) -> None:
        root = Path(main_module.PROJECT_ROOT).resolve()
        if sys.platform != "linux":
            raise SystemExit("Janitor Desktop currently supports Linux only")
        if getattr(args, "source", False):
            raise SystemExit("For a Janitor development stage run: node apps/desktop/janitor/build.mjs --build-only --keep-stage")
        if getattr(args, "setup_tcc_identity", False):
            raise SystemExit("This option is not available in the Linux Janitor AppImage launcher")
        target = _artifact(root)
        skip = getattr(args, "skip_build", False)
        force = getattr(args, "force_build", False) or getattr(args, "build_only", False)
        if skip and target is None:
            raise SystemExit("No Janitor AppImage exists. Run janitor desktop --build-only first.")
        if not skip and (target is None or force):
            from hermes_cli.source_build import prepare_source_dependencies, source_build_env
            from hermes_cli.desktop_build_lock import DesktopBuildLock
            lock = DesktopBuildLock(root)
            lock.acquire(wait=True)
            try:
                env = source_build_env(explicit=force)
                prepare_source_dependencies(root, ("ui-tui", "web", "apps/desktop"), env=env, explicit=force)
                _run_overlay(root, env, lambda message: print(f"  → {message}"))
                target = _artifact(root)
            finally:
                lock.release()
        if target is None:
            raise SystemExit("The Janitor Desktop AppImage is missing")
        if getattr(args, "build_only", False):
            print(f"Janitor Desktop ready: {target}")
            return
        from janitor_ext.startup import janitor_home
        from hermes_cli.main_desktop import _desktop_launch_env, _explicit_profile_args
        env, electron_flags = _desktop_launch_env(args)
        env.update(JANITOR_HOME=str(janitor_home()), HERMES_HOME=str(janitor_home()))
        command = [str(target), *electron_flags, *_explicit_profile_args()]
        if getattr(args, "local", False):
            command.append("--local")
        if getattr(args, "close_preview", False):
            command.append("--close-preview")
        subprocess.Popen(command, env=env, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Opened Janitor Desktop: {target}")
    main_module.cmd_desktop = desktop
    main_module.cmd_gui = desktop
