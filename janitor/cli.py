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
import shlex
import shutil
import sys

from pathlib import Path

from janitor.home import ASSETS_ROOT, REPO_ROOT, SKILLS_ROOT, janitor_home, resolve_hermes_home

# AISLAMIENTO CRÍTICO: Must be set BEFORE any hermes_ modules are imported.
# hermes_constants.get_hermes_home() reads this env var at import time.
# A HERMES_HOME that already names a ~/.janitor profile is kept; anything else
# (unset, ~/.hermes, ...) becomes ~/.janitor. ``--profile`` / ``active_profile``
# are resolved by upstream when hermes_cli.main is imported below.
os.environ["HERMES_HOME"] = str(resolve_hermes_home(os.environ.get("HERMES_HOME")))
# Referenced as ${JANITOR_SKILLS_ROOT} in skills.external_dirs so Janitor's
# skills resolve from whichever install tree is running.
os.environ["JANITOR_SKILLS_ROOT"] = str(SKILLS_ROOT)


def _load_janitor_env() -> None:
    env_path = Path(os.environ["HERMES_HOME"]) / ".env"
    try:
        with open(env_path, "r", encoding="utf-8") as f:
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


# COMMAND HIJACKING: Intercept `janitor update` before Hermes CLI parses arguments.
# We delegate to a minimal bootstrap helper so this path stays importable
# even when the venv is partially broken (e.g. new Hermes imports after a pull).
# Only this path loads .env by hand: everywhere else Hermes loads the .env of
# the home it resolved, and an early load of the root .env would leak its
# secrets into a ``--profile`` process (the desktop's per-profile backends).
if len(sys.argv) > 1 and sys.argv[1] == "update":
    _load_janitor_env()
    try:
        from janitor.update_bootstrap import run_update
        sys.exit(run_update())
    except Exception as e:
        print(f"⚠ Bootstrap update failed: {e}", file=sys.stderr)
        sys.exit(1)

import argparse

_original_argparser_init = argparse.ArgumentParser.__init__


def _janitor_argparser_init(self, *args, **kwargs):
    if kwargs.get("prog") == "hermes":
        kwargs["prog"] = "janitor"
    _original_argparser_init(self, *args, **kwargs)


argparse.ArgumentParser.__init__ = _janitor_argparser_init

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Seed a fresh ~/.janitor before Hermes loads its config: that first load
# writes upstream's default SOUL.md. Never blocks startup.
try:
    from janitor.seed import ensure_home

    ensure_home(janitor_home())
except Exception as _seed_exc:  # noqa: BLE001
    print(f"⚠ Janitor home seeding failed: {_seed_exc}", file=sys.stderr)

# Backend messages (TUI gateway, desktop backend, messaging gateways) read
# Janitor's catalogs: upstream's with janitor/locales/ merged in, exported as
# HERMES_BUNDLED_LOCALES so every child process inherits them. On failure the
# engine keeps upstream's catalogs. The Janitor plugin repeats this (a no-op
# here) for processes started without the launcher.
try:
    from janitor.locales import ensure_exported as _export_locales

    _export_locales()
except Exception as _locale_exc:  # noqa: BLE001
    print(f"⚠ Janitor message catalogs unavailable: {_locale_exc}", file=sys.stderr)

# What a gateway hand-off replays (``_hand_off_gateway``): the argv and
# environment as they are before hermes_cli.main strips ``-p`` and loads .env,
# so the canonical process resolves the same home the launcher did.
_LAUNCH_ARGV = list(sys.argv)
_LAUNCH_ENV = dict(os.environ)

# Upstream resolves ``--profile`` / ``active_profile`` (and loads that home's
# .env) when hermes_cli.main is imported; ``cli`` reads the home at import, so
# it must come second or a profile process starts on the root profile's state.
import hermes_cli.main  # noqa: E402,F401

# The home is final now (root or the ``--profile`` home): bring its skill
# selection up to the catalog before ``cli`` loads the config. A no-op rewrite
# is skipped, a config without ``janitor.skills`` is untouched, and a broken
# catalog/config only warns.
from janitor.catalog import apply_quietly  # noqa: E402

apply_quietly(Path(os.environ["HERMES_HOME"]))

import cli  # noqa: E402


def _ensure_janitor_skin_file():
    """Ensure the sentry-janitor skin file exists in ~/.janitor/skins/.

    If the user skin file is missing, copy from the bundled fallback so
    load_skin('sentry-janitor') always works.
    """
    try:
        from pathlib import Path

        from hermes_cli.skin_engine import _skins_dir

        skins_dir = Path(_skins_dir())
        if not skins_dir.exists():
            skins_dir.mkdir(parents=True, exist_ok=True)

        skin_file = skins_dir / "sentry-janitor.yaml"
        if not skin_file.exists():
            bundled = ASSETS_ROOT / "sentry-janitor.yaml"
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


# Commands that run while the Honcho fail-safe is tripped: the way out of it
# (``memory off``, ``config set``, ``setup``) and diagnostics. They never open
# a session, so no conversation can reach a half-configured Honcho.
_FAILSAFE_EXEMPT_COMMANDS = frozenset({
    "memory", "config", "setup", "doctor", "update", "honcho", "status", "logs",
    "dump", "version", "profile", "uninstall", "help",
})
_FAILSAFE_EXEMPT_FLAGS = frozenset({"-h", "--help", "-V", "--version"})


def _honcho_json_has_credential(path: Path) -> bool:
    """Fallback when the Honcho plugin cannot be imported: ``apiKey`` / ``baseUrl`` / an OAuth
    grant at the root or in any host block of ``path``."""
    import json

    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    if not isinstance(raw, dict):
        return False
    endpoint = raw.get("endpoint") if isinstance(raw.get("endpoint"), dict) else {}
    hosts = raw.get("hosts") if isinstance(raw.get("hosts"), dict) else {}
    blocks = [raw, endpoint, *(b for b in hosts.values() if isinstance(b, dict))]
    return any(b.get(k) for b in blocks for k in ("apiKey", "baseUrl", "base_url", "oauth"))


def _honcho_credential_configured() -> bool:
    """Does Honcho have something to connect with: a key or URL in the environment, or an API
    key / OAuth grant / base URL in the Honcho config upstream's client resolves
    (``$HERMES_HOME/honcho.json`` > default profile > ``~/.honcho/config.json``)?"""
    if any(os.environ.get(n, "").strip() for n in ("HONCHO_API_KEY", "HONCHO_BASE_URL", "HONCHO_URL")):
        return True
    try:
        from plugins.memory.honcho.client import HonchoClientConfig

        cfg = HonchoClientConfig.from_global_config()
    except Exception:  # noqa: BLE001 — plugin missing or broken: read the profile's file
        return _honcho_json_has_credential(Path(os.environ["HERMES_HOME"]) / "honcho.json")
    host_block = ((cfg.raw or {}).get("hosts") or {}).get(cfg.host) or {}
    return bool(cfg.api_key or cfg.base_url or (isinstance(host_block, dict) and host_block.get("oauth")))


def _honcho_failsafe_refusal(cfg: dict) -> str | None:
    """The Spanish refusal when ``cfg`` selects Honcho with nothing to connect with, else None."""
    memory = cfg.get("memory") if isinstance(cfg.get("memory"), dict) else {}
    if memory.get("provider") != "honcho" or _honcho_credential_configured():
        return None
    from hermes_constants import display_hermes_home

    home = Path(os.environ["HERMES_HOME"])
    janitor = f"janitor -p {home.name}" if home.parent.name == "profiles" else "janitor"
    return (
        "FATAL: memory.provider es 'honcho' pero Honcho no tiene credencial: ni HONCHO_API_KEY ni "
        "HONCHO_BASE_URL, ni apiKey, baseUrl o acceso OAuth en honcho.json.\n"
        "Janitor no arranca con una integración de Honcho incompleta (fail-safe OWASP).\n"
        f"Para volver a la memoria integrada:  {janitor} memory off\n"
        f"Para usar Honcho cloud:  {janitor} config set HONCHO_API_KEY <tu-clave>  "
        f"(se guarda en {display_hermes_home()}/.env)\n"
        "Para Honcho local, vuelve a la memoria integrada y pide a Janitor que instale Honcho "
        "(skill janitor-honcho)."
    )


def _failsafe_applies(argv: list[str]) -> bool:
    """False for the recovery and diagnostic commands, which must run while it is tripped."""
    words = _command_words(argv)
    if words:
        return words[0] not in _FAILSAFE_EXEMPT_COMMANDS
    return not any(token in _FAILSAFE_EXEMPT_FLAGS for token in argv[1:])


def _owasp_honcho_fail_safe(argv: list[str] | None = None):
    """OWASP fail-safe: never open a session on a Honcho integration without credentials.

    Exits 1 when ``memory.provider`` is ``honcho`` and neither the environment nor the
    resolved Honcho config has an API key, an OAuth grant or a base URL, unless the command
    is one of ``_FAILSAFE_EXEMPT_COMMANDS`` (``janitor memory off`` is the way back).
    """
    if not _failsafe_applies(sys.argv if argv is None else argv):
        return
    from cli import load_cli_config

    try:
        cfg = load_cli_config()
    except Exception:
        return
    refusal = _honcho_failsafe_refusal(cfg if isinstance(cfg, dict) else {})
    if refusal:
        print(refusal, file=sys.stderr)
        sys.exit(1)


_PROFILE_FLAGS = ("-p", "--profile")


def _command_words(argv: list[str]) -> list[str]:
    """Positional words of a launcher argv (``argv[1:]``): flags and the ``-p`` value dropped."""
    words: list[str] = []
    skip = False
    for token in argv[1:]:
        if skip:
            skip = False
        elif token in _PROFILE_FLAGS:
            skip = True
        elif not token.startswith("-"):
            words.append(token)
    return words


def _gateway_handoff_argv(argv: list[str], python: str) -> list[str] | None:
    """``python -m hermes_cli.main <args>`` when ``argv`` makes this process a gateway runtime.

    A gateway started as ``janitor gateway run`` (console script) or ``python
    -m janitor.cli gateway run`` keeps that command line for life, and
    upstream's discovery (``gateway.status.looks_like_gateway_command_line``,
    behind ``find_gateway_pids``, PID-file validation and the update fleet
    restart) only recognises Hermes entrypoints, so that gateway is invisible
    to status, stop and every update. The decision is upstream's own runtime
    matcher applied to the canonical command line.
    """
    from gateway.status import looks_like_gateway_runtime_command_line

    words = _command_words(argv)
    if not words or words[0] != "gateway":
        return None
    canonical = [python, "-m", "hermes_cli.main", *argv[1:]]
    return canonical if looks_like_gateway_runtime_command_line(shlex.join(canonical)) else None


def _hand_off_gateway() -> None:
    """Replace this launcher with the canonical gateway process; return when it is not one.

    Everything the launcher gives a gateway is done by now (seed, migration,
    catalogs, skill selection, fail-safe) or travels with it: the environment
    (``HERMES_HOME``, ``JANITOR_SKILLS_ROOT``, ``HERMES_BUNDLED_LOCALES``) and
    the Janitor plugin (catalogs, tips). The in-process patches below do not
    matter to a gateway: ``/update`` runs a separate updater process.
    """
    argv = _gateway_handoff_argv(_LAUNCH_ARGV, sys.executable)
    if argv is None:
        return
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":  # no exec on Windows: the child is the gateway, the launcher waits
        import subprocess

        sys.exit(subprocess.call(argv, env=_LAUNCH_ENV))
    os.execve(sys.executable, argv, _LAUNCH_ENV)


def _janitor_cmd_update(args):
    """Janitor update — delegates to the shared core in ``janitor.update_core``.

    Replaces the built-in ``hermes update`` so it only pulls from the
    Janitor fork and never syncs with the upstream NousResearch/hermes-agent
    repository.
    """
    from janitor import update_core

    return update_core.run_janitor_update(args)


def main():
    """
    Entry point for the `janitor` command.

    Forces the Janitor skin and then delegates to HermesCLI.main().
    We do NOT run HermesCLI here directly — we configure the environment
    first so that when HermesCLI initializes, it picks up the Janitor identity.
    """
    # Must run before Hermes starts: its bundled-skills sync drops manifest
    # entries for skills that left the bundled tree, which is the evidence the
    # layout migration uses to tell pristine copies from user edits.
    from janitor.migrations import auto_migrate

    auto_migrate()

    _ensure_janitor_skin_file()

    try:
        from hermes_cli.skin_engine import set_active_skin

        set_active_skin("sentry-janitor")
    except Exception:
        pass

    _owasp_honcho_fail_safe()

    _hand_off_gateway()

    # Monkey-patch tips to the Janitor Spanish corpus without touching core Hermes.
    import hermes_cli.tips as _hermes_tips_mod

    from janitor.tips_es import JANITOR_TIPS, get_janitor_tip

    _hermes_tips_mod.TIPS = JANITOR_TIPS
    _hermes_tips_mod.get_random_tip = get_janitor_tip

    # Monkey-patch ``hermes update`` so it pulls from the Janitor fork only.
    import hermes_cli.main as _hermes_main_mod

    _hermes_main_mod.cmd_update = _janitor_cmd_update

    from hermes_cli.main import main as hermes_main

    sys.exit(hermes_main())


if __name__ == "__main__":
    main()
