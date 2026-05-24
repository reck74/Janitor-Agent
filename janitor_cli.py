#!/usr/bin/env python3
"""
Janitor CLI - A cínico, ciberseguridad-focused wrapper around HermesCLI.

Per JANITOR FORK DIRECTIVES:
- ZERO-RENAMING: Never rename 'hermes' in the core.
- CLI WRAPPER: Janitor extensions inherit from HermesCLI in separate files.
- TUI ISOLATION: Visual changes go through skin_engine.py, not hardcoded.

This module provides the `janitor` command entry point and the JanitorCLI class
that forces the Janitor skin and identity on top of the Hermes core.

Aislamiento: Janitor uses ~/.janitor as HERMES_HOME to stay fully isolated
from any pre-existing Hermes installation at ~/.hermes/.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

# AISLAMIENTO CRÍTICO: Must be set BEFORE any hermes_ modules are imported.
# hermes_constants.get_hermes_home() reads this env var at import time.
os.environ["HERMES_HOME"] = os.path.expanduser("~/.janitor")


def _load_janitor_env() -> None:
    env_path = os.path.expanduser("~/.janitor/.env")
    try:
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key and key != "HERMES_HOME":
                    os.environ.setdefault(key, value)
    except FileNotFoundError:
        pass
    except Exception:
        pass


_load_janitor_env()

from hermes_cli.config import DEFAULT_CONFIG

DEFAULT_CONFIG.setdefault("memory", {}).setdefault("provider", "honcho")
DEFAULT_CONFIG.setdefault("display", {}).setdefault("skin", "sentry-janitor")


def _load_janitor_soul() -> str:
    soul_path = os.path.expanduser("~/.janitor/SOUL.md")
    try:
        with open(soul_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return ""


from agent import prompt_builder

_original_load_soul_md = prompt_builder.load_soul_md


def _janitor_load_soul_md() -> str:
    soul = _load_janitor_soul()
    if soul:
        return soul
    return _original_load_soul_md()


prompt_builder.load_soul_md = _janitor_load_soul_md

# COMMAND HIJACKING: Intercept `janitor update` before Hermes CLI parses arguments.
if len(sys.argv) > 1 and sys.argv[1] == "update":
    import subprocess
    print("\n🔥 THE JANITOR: Initiating tactical update...\n")
    try:
        janitor_root = os.path.dirname(os.path.abspath(__file__))
        os.chdir(janitor_root)

        print("-> Syncing incinerator protocols (git pull)...")
        subprocess.run(["git", "pull", "origin", "main"], check=True)

        print("-> Updating dependencies (uv)...")
        venv_path = sys.prefix
        subprocess.run(["uv", "pip", "install", "--python", venv_path, "-e", ".[all]"], check=True)

        print("-> Compiling TUI components...")
        subprocess.run("cd ui-tui && npm install && npm run build", shell=True, check=True)

        print("\n✅ Janitor updated successfully. Garbage collected.\n")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Update failed at step: {e.cmd}\n")
        sys.exit(1)
    sys.exit(0)

import argparse

_original_argparser_init = argparse.ArgumentParser.__init__


def _janitor_argparser_init(self, *args, **kwargs):
    if kwargs.get("prog") == "hermes":
        kwargs["prog"] = "janitor"
    _original_argparser_init(self, *args, **kwargs)


argparse.ArgumentParser.__init__ = _janitor_argparser_init

sys.path.insert(0, os.path.dirname(__file__))
import cli


def _apply_janitor_identity():
    os.environ.setdefault("HERMES_SKIN", "janitor")


def _ensure_janitor_skin_file():
    """Ensure the sentry-janitor skin file exists in ~/.janitor/skins/.

    If the user skin file is missing, copy from the bundled fallback so
    load_skin('sentry-janitor') always works.
    """
    try:
        from hermes_cli.skin_engine import _skins_dir
        from pathlib import Path
        import shutil

        skins_dir = Path(_skins_dir())
        if not skins_dir.exists():
            skins_dir.mkdir(parents=True, exist_ok=True)

        skin_file = skins_dir / "sentry-janitor.yaml"
        if not skin_file.exists():
            bundled = Path(__file__).parent / "example_skin_sentry-janitor.yaml.txt"
            if bundled.exists():
                shutil.copy2(bundled, skin_file)
    except Exception:
        pass


class JanitorCLI(cli.HermesCLI):
    """
    Janitor CLI — inherits from HermesCLI to inject cínico/ciberseguridad identity.

    Per CLI WRAPPER directive, we inherit instead of modifying the core HermesCLI.
    This class forces the 'janitor' skin on initialization and ensures all branding
    reflects the Janitor fork identity rather than the base Hermes one.
    """

    def __init__(self, *args, **kwargs):
        _apply_janitor_identity()
        _ensure_janitor_skin_file()

        try:
            from hermes_cli.skin_engine import set_active_skin

            set_active_skin("sentry-janitor")
        except Exception:
            pass

        super().__init__(*args, **kwargs)

    @property
    def force_skin(self) -> bool:
        return True

    def get_skin_name(self) -> str:
        return "sentry-janitor"


def _owasp_honcho_fail_safe():
    """
    OWASP fail-safe: verify Honcho memory integration has required credentials.

    Exit with security error (code 1) if:
    - memory.provider is 'honcho' AND
    - neither HONCHO_API_KEY nor HONCHO_BASE_URL is set

    This prevents the Janitor from running with an incomplete Honcho integration
    that could leak session data to an unconfigured external service.
    """

    honcho_key = os.environ.get("HONCHO_API_KEY", "").strip()
    honcho_base = os.environ.get("HONCHO_BASE_URL", "").strip()

    if honcho_key or honcho_base:
        return

    from cli import load_cli_config

    try:
        cfg = load_cli_config()
    except Exception:
        return

    memory_provider = cfg.get("memory", {}).get("provider", "")
    if memory_provider != "honcho":
        return

    from hermes_constants import display_hermes_home

    home_display = display_hermes_home()

    print(
        "FATAL: Honcho memory provider configured but HONCHO_API_KEY / HONCHO_BASE_URL not set.",
        file=sys.stderr,
    )
    print(
        "Janitor will not start with partial Honcho credentials (OWASP fail-safe).",
        file=sys.stderr,
    )
    print(
        f"Set HONCHO_API_KEY in {home_display}/.env or run 'janitor honcho setup'.",
        file=sys.stderr,
    )
    sys.exit(1)


def _owasp_honcho_fail_safe_for_test(hermes_home: str):
    """
    OWASP fail-safe variant that accepts an explicit hermes_home path.
    Used only by tests to validate the check works with any HERMES_HOME.
    """
    honcho_key = os.environ.get("HONCHO_API_KEY", "").strip()
    honcho_base = os.environ.get("HONCHO_BASE_URL", "").strip()

    if honcho_key or honcho_base:
        return True, ""

    from pathlib import Path

    config_path = Path(hermes_home) / "config.yaml"
    if not config_path.exists():
        return True, ""

    import yaml

    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}

    memory_provider = cfg.get("memory", {}).get("provider", "")
    if memory_provider != "honcho":
        return True, ""

    from hermes_constants import display_hermes_home

    os.environ["HERMES_HOME"] = hermes_home
    home_display = display_hermes_home()

    msg = (
        f"FATAL: Honcho memory provider configured but HONCHO_API_KEY / HONCHO_BASE_URL not set.\n"
        f"Janitor will not start with partial Honcho credentials (OWASP fail-safe).\n"
        f"Set HONCHO_API_KEY in {home_display}/.env or run 'janitor honcho setup'."
    )
    return False, msg


def _janitor_cmd_update(args):
    """Update Janitor Agent from the Janitor fork (reck74/Janitor-Agent).

    Replaces the built-in ``hermes update`` so it only pulls from the
    Janitor fork and never syncs with the upstream NousResearch/hermes-agent
    repository.
    """
    from pathlib import Path
    import hermes_cli.main as _main_mod

    # Re-use Hermes internal helpers — they are stable enough for this wrapper.
    _run_pre_update_backup = _main_mod._run_pre_update_backup
    _install_hangup_protection = _main_mod._install_hangup_protection
    _finalize_update_output = _main_mod._finalize_update_output
    _stash_local_changes_if_needed = _main_mod._stash_local_changes_if_needed
    _install_python_dependencies_with_optional_fallback = (
        _main_mod._install_python_dependencies_with_optional_fallback
    )
    _is_termux_env = _main_mod._is_termux_env
    _is_android_python = _main_mod._is_android_python
    _install_psutil_android_compat = _main_mod._install_psutil_android_compat
    _ensure_uv_for_termux = _main_mod._ensure_uv_for_termux
    _update_node_dependencies = _main_mod._update_node_dependencies
    _invalidate_update_cache = _main_mod._invalidate_update_cache
    _clear_bytecode_cache = _main_mod._clear_bytecode_cache
    PROJECT_ROOT = _main_mod.PROJECT_ROOT

    if getattr(args, "check", False):
        git_dir = PROJECT_ROOT / ".git"
        if not git_dir.exists():
            print("✗ Not a git repository — cannot check for updates.")
            sys.exit(1)

        git_cmd = ["git"]
        if sys.platform == "win32":
            git_cmd = ["git", "-c", "windows.appendAtomically=false"]

        print("→ Fetching from origin...")
        fetch_result = subprocess.run(
            git_cmd + ["fetch", "origin"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if fetch_result.returncode != 0:
            stderr = fetch_result.stderr.strip()
            if "Could not resolve host" in stderr or "unable to access" in stderr:
                print("✗ Network error — cannot reach the remote repository.")
            elif (
                "Authentication failed" in stderr
                or "could not read Username" in stderr
            ):
                print(
                    "✗ Authentication failed — check your git credentials or SSH key."
                )
            else:
                print("✗ Failed to fetch.")
                if stderr:
                    print(f"  {stderr.splitlines()[0]}")
            sys.exit(1)

        result = subprocess.run(
            git_cmd + ["rev-list", "HEAD..origin/main", "--count"],
            cwd=PROJECT_ROOT,
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
        return

    gateway_mode = getattr(args, "gateway", False)

    # Protect against mid-update terminal disconnects (SIGHUP) and tolerate
    # writes to a closed stdout.  No-op in gateway mode.
    _update_io_state = _install_hangup_protection(gateway_mode=gateway_mode)
    try:
        print("⚕ Updating Janitor Agent from fork...")
        print()

        # Pre-update backup — runs before any git/file mutation.
        _run_pre_update_backup(args)

        git_dir = PROJECT_ROOT / ".git"
        if not git_dir.exists():
            print("✗ Not a git repository. Please reinstall:")
            print("  git clone https://github.com/reck74/Janitor-Agent.git")
            sys.exit(1)

        git_cmd = ["git"]
        if sys.platform == "win32":
            git_cmd = ["git", "-c", "windows.appendAtomically=false"]

        # Fetch updates from origin (the Janitor fork).
        print("→ Fetching updates from origin...")
        fetch_result = subprocess.run(
            git_cmd + ["fetch", "origin"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if fetch_result.returncode != 0:
            stderr = fetch_result.stderr.strip()
            if "Could not resolve host" in stderr or "unable to access" in stderr:
                print("✗ Network error — cannot reach the remote repository.")
            elif (
                "Authentication failed" in stderr
                or "could not read Username" in stderr
            ):
                print(
                    "✗ Authentication failed — check your git credentials or SSH key."
                )
            else:
                print("✗ Failed to fetch updates from origin.")
                if stderr:
                    print(f"  {stderr.splitlines()[0]}")
            sys.exit(1)

        # Determine current branch.
        result = subprocess.run(
            git_cmd + ["rev-parse", "--abbrev-ref", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        current_branch = result.stdout.strip()
        branch = "main"

        if current_branch != "main":
            label = (
                "detached HEAD"
                if current_branch == "HEAD"
                else f"branch '{current_branch}'"
            )
            print(f"  ⚠ Currently on {label} — switching to main for update...")
            auto_stash_ref = _stash_local_changes_if_needed(git_cmd, PROJECT_ROOT)
            subprocess.run(
                git_cmd + ["checkout", "main"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            auto_stash_ref = _stash_local_changes_if_needed(git_cmd, PROJECT_ROOT)

        # Check if there are updates.
        result = subprocess.run(
            git_cmd + ["rev-list", f"HEAD..origin/{branch}", "--count"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        commit_count = int(result.stdout.strip())

        if commit_count == 0:
            _invalidate_update_cache()
            print("✓ Already up to date.")
            return

        print(f"→ Pulling {commit_count} update(s) from origin/{branch}...")
        subprocess.run(
            git_cmd + ["pull", "--ff-only", "origin", branch],
            cwd=PROJECT_ROOT,
            check=True,
        )
        print(f"  ✓ Pulled {commit_count} update(s)")

        _invalidate_update_cache()

        # Clear stale .pyc bytecode cache.
        removed = _clear_bytecode_cache(PROJECT_ROOT)
        if removed:
            print(
                f"  ✓ Cleared {removed} stale __pycache__ director{'y' if removed == 1 else 'ies'}"
            )

        # Reinstall Python dependencies.
        print("→ Updating Python dependencies...")
        pip_cmd = [sys.executable, "-m", "pip"]
        uv_bin = shutil.which("uv") or _ensure_uv_for_termux(pip_cmd)
        install_group = "all"

        if uv_bin:
            uv_env = {**os.environ, "VIRTUAL_ENV": str(PROJECT_ROOT / "venv")}
            if _is_termux_env(uv_env):
                uv_env.pop("PYTHONPATH", None)
                uv_env.pop("PYTHONHOME", None)
                install_group = "termux-all"
                print(
                    "  → Termux detected: using uv + curated termux-all optional profile..."
                )
            if _is_termux_env(uv_env) and _is_android_python():
                print(
                    "  → Termux/Android detected: prebuilding psutil with Linux source path compatibility..."
                )
                _install_psutil_android_compat([uv_bin, "pip"], env=uv_env)
            _install_python_dependencies_with_optional_fallback(
                [uv_bin, "pip"], env=uv_env, group=install_group
            )
        else:
            pip_cmd = [sys.executable, "-m", "pip"]
            try:
                subprocess.run(
                    pip_cmd + ["--version"],
                    cwd=PROJECT_ROOT,
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError:
                subprocess.run(
                    [sys.executable, "-m", "ensurepip", "--upgrade", "--default-pip"],
                    cwd=PROJECT_ROOT,
                    check=True,
                )
            if _is_termux_env():
                install_group = "termux-all"
                print(
                    "  → Termux detected: using curated termux-all optional profile..."
                )
            if _is_termux_env() and _is_android_python():
                print(
                    "  → Termux/Android detected: prebuilding psutil with Linux source path compatibility..."
                )
                _install_psutil_android_compat(pip_cmd)
            _install_python_dependencies_with_optional_fallback(
                pip_cmd, env=None, group=install_group
            )

        print("✓ Python dependencies updated")

        _update_node_dependencies()

        print()
        print("✓ Janitor Agent updated successfully!")
        print("  Restart Janitor to use the new version.")

    except subprocess.CalledProcessError as e:
        print(f"✗ Update failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n✗ Update cancelled.")
        sys.exit(130)
    finally:
        _finalize_update_output(_update_io_state)


def main():
    """
    Entry point for the `janitor` command.

    Forces the Janitor skin and then delegates to HermesCLI.main().
    We do NOT run HermesCLI here directly — we configure the environment
    first so that when HermesCLI initializes, it picks up the Janitor identity.
    """
    _apply_janitor_identity()
    _ensure_janitor_skin_file()

    try:
        from hermes_cli.skin_engine import set_active_skin

        set_active_skin("sentry-janitor")
    except Exception:
        pass

    _owasp_honcho_fail_safe()

    # Monkey-patch ``hermes update`` so it pulls from the Janitor fork only.
    import hermes_cli.main as _hermes_main_mod

    _hermes_main_mod.cmd_update = _janitor_cmd_update

    from hermes_cli.main import main as hermes_main

    sys.exit(hermes_main())


if __name__ == "__main__":
    main()
