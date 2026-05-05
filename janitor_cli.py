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
import sys

# AISLAMIENTO CRÍTICO: Must be set BEFORE any hermes_ modules are imported.
# hermes_constants.get_hermes_home() reads this env var at import time.
os.environ["HERMES_HOME"] = os.path.expanduser("~/.janitor")

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
        f"Set HONCHO_API_KEY in {home_display}/.env or run 'hermes honcho setup'.",
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
        f"Set HONCHO_API_KEY in {home_display}/.env or run 'hermes honcho setup'."
    )
    return False, msg


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

    from hermes_cli.main import main as hermes_main

    sys.exit(hermes_main())


if __name__ == "__main__":
    main()
