#!/usr/bin/env python3
"""
Janitor CLI - A cínico, ciberseguridad-focused wrapper around HermesCLI.

Per JANITOR FORK DIRECTIVES:
- ZERO-RENAMING: Never rename 'hermes' in the core.
- CLI WRAPPER: Janitor extensions inherit from HermesCLI in separate files.
- TUI ISOLATION: Visual changes go through skin_engine.py, not hardcoded.

This module provides the `janitor` command entry point and the JanitorCLI class
that forces the Janitor skin and identity on top of the Hermes core.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import cli


def _apply_janitor_identity():
    os.environ.setdefault("HERMES_SKIN", "janitor")


class JanitorCLI(cli.HermesCLI):
    """
    Janitor CLI — inherits from HermesCLI to inject cínico/ciberseguridad identity.

    Per CLI WRAPPER directive, we inherit instead of modifying the core HermesCLI.
    This class forces the 'janitor' skin on initialization and ensures all branding
    reflects the Janitor fork identity rather than the base Hermes one.
    """

    def __init__(self, *args, **kwargs):
        _apply_janitor_identity()

        try:
            from hermes_cli.skin_engine import set_active_skin
            set_active_skin("janitor")
        except Exception:
            pass

        super().__init__(*args, **kwargs)

    @property
    def force_skin(self) -> bool:
        return True

    def get_skin_name(self) -> str:
        return "janitor"


def _owasp_honcho_fail_safe():
    """
    OWASP fail-safe: verify Honcho memory integration has required credentials.

    Exit with security error (code 1) if:
    - memory.provider is 'honcho' AND
    - neither HONCHO_API_KEY nor HONCHO_BASE_URL is set

    This prevents the Janitor from running with an incomplete Honcho integration
    that could leak session data to an unconfigured external service.
    """
    import json
    from pathlib import Path

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

    print("FATAL: Honcho memory provider configured but HONCHO_API_KEY / HONCHO_BASE_URL not set.", file=sys.stderr)
    print("Janitor will not start with partial Honcho credentials (OWASP fail-safe).", file=sys.stderr)
    print("Set HONCHO_API_KEY in ~/.hermes/.env or run 'hermes honcho setup'.", file=sys.stderr)
    sys.exit(1)


def main():
    """
    Entry point for the `janitor` command.

    Forces the Janitor skin and then delegates to HermesCLI.main().
    We do NOT run HermesCLI here directly — we configure the environment
    first so that when HermesCLI initializes, it picks up the Janitor skin.
    """
    _apply_janitor_identity()

    try:
        from hermes_cli.skin_engine import set_active_skin
        set_active_skin("janitor")
    except Exception:
        pass

    _owasp_honcho_fail_safe()

    from hermes_cli.main import main as hermes_main
    sys.exit(hermes_main())


if __name__ == "__main__":
    main()