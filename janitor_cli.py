#!/usr/bin/env python3
"""Janitor entrypoint and runtime adapters, isolated from the Hermes core."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from janitor_ext.startup import prepare_environment, profile_selection

_original_load_soul_md = None
_original_argparser_init = argparse.ArgumentParser.__init__
_RUNTIME_INSTALLED = False


def _janitor_load_soul_md(context_length=None, home_override=None):
    """Preserve upstream profile binding, scanning and context-length handling."""
    if _original_load_soul_md is None:
        _install_janitor_runtime()
    return _original_load_soul_md(context_length, home_override=home_override)


def _janitor_argparser_init(self, *args, **kwargs):
    if kwargs.get("prog") == "hermes":
        kwargs["prog"] = "janitor"
    _original_argparser_init(self, *args, **kwargs)


def _apply_janitor_identity():
    os.environ.setdefault("HERMES_SKIN", "sentry-janitor")  # health: allow HX002 -- internal bridge to the upstream skin loader for bundled Janitor identity; explicit user skin selection wins


def _ensure_janitor_skin_file():
    from hermes_constants import get_hermes_home
    skin = get_hermes_home() / "skins" / "sentry-janitor.yaml"
    bundled = Path(__file__).resolve().parent / "assets" / "janitor" / "sentry-janitor.yaml"
    if not skin.exists() and bundled.is_file():
        skin.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled, skin)


def _owasp_honcho_fail_safe():
    """Validate configured Honcho at conversation startup; repair commands stay reachable."""
    from hermes_cli.config import load_config
    from hermes_constants import get_hermes_home
    cfg = load_config()
    if (cfg.get("memory") or {}).get("provider") != "honcho":
        return
    from plugins.memory import find_provider_dir
    if find_provider_dir("honcho") is None:
        raise RuntimeError("Honcho memory plugin is missing. Run 'janitor plugins install honcho' or reinstall Janitor.")
    if os.environ.get("HONCHO_API_KEY", "").strip() or os.environ.get("HONCHO_BASE_URL", "").strip():
        return
    # Honcho supports a profile-local config in addition to environment credentials.
    for source in (get_hermes_home() / "honcho.json", Path.home() / ".honcho" / "config.json"):
        try:
            with source.open(encoding="utf-8") as stream:
                data = json.load(stream)
            host = (data.get("hosts") or {}).get("hermes") or {}
            if any(str(section.get(key) or "").strip() for section in (data, host)
                   for key in ("apiKey", "baseUrl", "baseURL")):
                return
        except (OSError, ValueError, AttributeError):
            continue
    raise RuntimeError("Honcho memory is configured without a key or local URL. Re-run scripts/janitor-install.sh for this profile.")


def _janitor_cmd_update(args):
    from janitor_update_core import run_janitor_update
    return run_janitor_update(args)


def _install_janitor_runtime():
    global _RUNTIME_INSTALLED, _original_load_soul_md
    if _RUNTIME_INSTALLED:
        return
    # Hermes bootstrap selects/activates the PM generation and applies --profile
    # before any Janitor adapter reads profile-owned configuration.
    import hermes_cli.main as main_module
    import cli
    from agent import prompt_builder
    from hermes_cli.skin_engine import set_active_skin
    from hermes_cli import banner
    from janitor_version import format_version
    from janitor_update_core import install_update_adapter

    _original_load_soul_md = prompt_builder.load_soul_md
    prompt_builder.load_soul_md = _janitor_load_soul_md
    argparse.ArgumentParser.__init__ = _janitor_argparser_init
    install_update_adapter(main_module)
    main_module.cmd_update = _janitor_cmd_update
    from janitor_ext.desktop import install_cli_adapter
    install_cli_adapter(main_module)
    main_module._print_version_info = lambda: print(format_version())
    main_module.cmd_version = lambda args: print(format_version())
    banner.format_banner_version_label = format_version
    # Register the fork section at runtime; upstream config source stays intact.
    import hermes_cli.config as config_module
    config_module._KNOWN_ROOT_KEYS = config_module._KNOWN_ROOT_KEYS | {"janitor"}
    _ensure_janitor_skin_file()
    set_active_skin("sentry-janitor")
    from janitor_ext.tips_es import JANITOR_TIPS, get_janitor_tip
    from hermes_cli import tips
    tips.TIPS, tips.get_random_tip = JANITOR_TIPS, get_janitor_tip

    original_cli = cli.HermesCLI

    class JanitorCLI(original_cli):
        """Fork CLI extends the current upstream class, without editing cli.py."""
        def __init__(self, *args, **kwargs):
            _owasp_honcho_fail_safe()
            super().__init__(*args, **kwargs)

        @property
        def force_skin(self):
            return True

        def get_skin_name(self):
            return "sentry-janitor"

    globals()["JanitorCLI"] = JanitorCLI
    cli.HermesCLI = JanitorCLI
    _RUNTIME_INSTALLED = True


def __getattr__(name):
    if name == "JanitorCLI":
        prepare_environment()
        _install_janitor_runtime()
        return globals()[name]
    raise AttributeError(name)


def main():
    argv = sys.argv[1:]
    try:
        prepare_environment(argv)
        _, command = profile_selection(argv)
        if command and command[0] == "update":
            from janitor_update_bootstrap import run_update
            return run_update(command[1:])
        if command in (["--version"], ["version"]):
            from janitor_version import format_version
            print(format_version())
            from pm.paths import install_root
            print(f"Install directory: {install_root()}")
            return 0
        _install_janitor_runtime()
        if command[:2] in (["gateway", "run"], ["gateway", "start"]):
            _owasp_honcho_fail_safe()
        from hermes_cli.main import main as upstream_main
        result = upstream_main()
        return result if isinstance(result, int) else 0
    except (ValueError, RuntimeError) as error:
        print(f"Janitor: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
