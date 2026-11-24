"""Runtime copy the engine sends as English literals reaches a Spanish Janitor user in Spanish.

Touchpoint ``runtime-copy`` (``janitor/overlay.yaml``): upstream call sites with
no key in upstream's ``en.yaml`` ask the catalog first through
``agent.i18n.t_default`` and keep their English otherwise; Janitor's overlay
(``janitor/locales/es.yaml``, ``runtime_copy.*``) supplies the Spanish. These
tests drive the real call sites with the merged catalog and relate the catalog
to the command registry, so a command upstream adds without a Spanish
description, or a Spanish string that says "Hermes", fails here at sync time.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from janitor import locales as janitor_locales

# Words a Spanish user may read: env var names, URLs and third-party product names.
_ALLOWED = (re.compile(r"\bHERMES_[A-Z0-9_]+\b"), re.compile(r"https?://\S+"))


def _hermes(text: str) -> list[str]:
    for pattern in _ALLOWED:
        text = pattern.sub("", text)
    return re.findall(r"(?i)\S*hermes\S*", text)


def _flat(node, prefix="", out=None):
    out = {} if out is None else out
    if isinstance(node, dict):
        for key, value in node.items():
            _flat(value, f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(node, str):
        out[prefix] = node
    return out


def _gateway_commands():
    """Every command a gateway can list: not CLI-only, or behind a config gate a user may open."""
    from hermes_cli.commands import COMMAND_REGISTRY, _is_gateway_available

    gated = {c.name for c in COMMAND_REGISTRY if c.gateway_config_gate}
    return [c for c in COMMAND_REGISTRY if _is_gateway_available(c, gated)]


def _spanish_home():
    home = Path(os.environ["HERMES_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text("display:\n  language: es\n", encoding="utf-8")


@pytest.fixture()
def janitor_spanish(tmp_path, monkeypatch):
    from agent.i18n import reset_language_cache

    _spanish_home()
    monkeypatch.delenv("HERMES_LANGUAGE", raising=False)
    path = janitor_locales.build(tmp_path / "locales")
    monkeypatch.setenv(janitor_locales.ENV_VAR, str(path))
    reset_language_cache()
    yield _flat(yaml.safe_load((path / "es.yaml").read_text(encoding="utf-8")))
    reset_language_cache()


@pytest.fixture()
def upstream_spanish(monkeypatch):
    from agent.i18n import reset_language_cache

    _spanish_home()
    monkeypatch.delenv("HERMES_LANGUAGE", raising=False)
    monkeypatch.delenv(janitor_locales.ENV_VAR, raising=False)
    reset_language_cache()
    yield
    reset_language_cache()


# ── catalog ↔ registry ───────────────────────────────────────────────────────


def test_every_gateway_command_has_a_spanish_description(janitor_spanish):
    """A command upstream adds to /help or the Telegram menu needs a Spanish line here."""
    missing = {c.name: c.description for c in _gateway_commands()
               if f"runtime_copy.commands.{c.name}" not in janitor_spanish}
    assert not missing, f"add runtime_copy.commands.<name> to janitor/locales/es.yaml: {missing}"
    untranslated = {c.name for c in _gateway_commands()
                    if janitor_spanish[f"runtime_copy.commands.{c.name}"] == c.description}
    assert not untranslated


def test_command_descriptions_name_live_commands(janitor_spanish):
    from hermes_cli.commands import COMMAND_REGISTRY

    names = {c.name for c in COMMAND_REGISTRY}
    stale = [k for k in janitor_spanish if k.startswith("runtime_copy.commands.")
             and k.removeprefix("runtime_copy.commands.") not in names]
    assert not stale, f"descriptions for commands upstream removed or renamed: {stale}"


def test_runtime_copy_never_says_hermes(janitor_spanish):
    leaks = {k: _hermes(v) for k, v in janitor_spanish.items() if k.startswith("runtime_copy.")}
    assert not {k: v for k, v in leaks.items() if v}


# ── the real call sites ──────────────────────────────────────────────────────


def test_gateway_help_and_telegram_menu_are_spanish(janitor_spanish):
    from hermes_cli.commands import gateway_help_lines
    from hermes_cli.commands_platforms import telegram_bot_commands

    english = {c.description for c in _gateway_commands()}
    lines = gateway_help_lines()
    assert lines and not [line for line in lines if any(line.endswith(f"-- {e}") for e in english)]
    assert any(line.startswith("`/help") and "Muestra los comandos disponibles" in line for line in lines)
    menu = dict(telegram_bot_commands(include_plugins=False))
    assert menu["update"] == "Actualiza Janitor a la última versión"
    assert not [d for d in menu.values() if d in english or _hermes(d)]


def test_upstream_catalogs_keep_the_registry_english(upstream_spanish):
    """Without the Janitor catalogs the call sites are upstream's, byte for byte."""
    from hermes_cli.commands import COMMAND_REGISTRY, gateway_help_lines
    from hermes_cli.commands_platforms import telegram_bot_commands

    help_cmd = next(c for c in COMMAND_REGISTRY if c.name == "help")
    assert any(line.endswith(f"-- {help_cmd.description}") for line in gateway_help_lines())
    assert dict(telegram_bot_commands(include_plugins=False))["help"] == help_cmd.description


def _runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    runner._voice_mode = {}
    runner._update_prompt_pending = {}
    return runner


def _update_markers(home: Path, exit_code: str, output: str) -> None:
    (home / ".update_pending.json").write_text(json.dumps({"platform": "telegram", "chat_id": "1", "user_id": "2"}))
    (home / ".update_output.txt").write_text(output, encoding="utf-8")
    (home / ".update_exit_code").write_text(exit_code)


def _sent(adapter) -> str:
    return "\n".join(call.args[1] for call in adapter.send.call_args_list)


def test_update_watcher_closes_in_spanish(janitor_spanish, tmp_path):
    """The message that closes a /update from Telegram (directive #13 route)."""
    from gateway.config import Platform

    home = tmp_path / "home"
    home.mkdir()
    _update_markers(home, "0", "listo\n")
    runner, adapter = _runner(), AsyncMock()
    runner.adapters = {Platform.TELEGRAM: adapter}
    with patch("gateway.run._hermes_home", home):
        asyncio.run(runner._watch_update_progress(poll_interval=0.01, stream_interval=0.01, timeout=1.0))
    sent = _sent(adapter)
    assert "✅ Actualización de Janitor terminada." in sent and not _hermes(sent), sent


def test_post_restart_update_failure_is_spanish(janitor_spanish, tmp_path):
    from gateway.config import Platform

    home = tmp_path / "home"
    home.mkdir()
    _update_markers(home, "1", "ERROR: pip failed\n")
    runner, adapter = _runner(), AsyncMock()
    runner.adapters = {Platform.TELEGRAM: adapter}
    with patch("gateway.run._hermes_home", home):
        asyncio.run(runner._send_update_notification())
    sent = _sent(adapter)
    assert sent.startswith("❌ La actualización de Janitor falló") and "Últimas líneas:" in sent, sent
    assert "ERROR: pip failed" in sent and "`janitor update`" in sent and not _hermes(sent)


def test_no_home_channel_notice_is_spanish(janitor_spanish, monkeypatch):
    from gateway.config import Platform
    from gateway.session import SessionSource

    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)
    runner = _runner()
    runner.session_store = MagicMock()
    runner._async_session_store = MagicMock(_store=runner.session_store,
                                            has_any_sessions=AsyncMock(return_value=True))
    runner.config = MagicMock(get_home_channel=MagicMock(return_value=None))
    runner._deliver_platform_notice = AsyncMock()
    source = SessionSource(platform=Platform.TELEGRAM, chat_id="1")
    asyncio.run(runner._hmwa_first_contact_notes(source, [], []))
    (_, text), _ = runner._deliver_platform_notice.call_args
    assert text.startswith("📬 No hay canal principal para Telegram.") and "/sethome" in text, text
    assert not _hermes(text)


def test_telegram_pairing_errors_are_spanish_but_keep_the_apps_410_words(janitor_spanish):
    """The app stops polling when a 410 body says expired/claimed (telegram-qr-setup.tsx)."""
    from hermes_cli.web_server_messaging import _telegram_onboarding_error_message as message

    for code in ("not_found", "unauthorized", "telegram_manager_bot_token_not_configured",
                 "telegram_token_fetch_failed"):
        text = message(code, "fallback")
        assert text == janitor_spanish[f"runtime_copy.telegram_onboarding.{code}"], code
    assert re.search(r"(?i)\bexpired\b", message("expired", ""))
    assert re.search(r"(?i)\bclaimed\b", message("claimed", ""))
    assert message("something_new", "fallback") == "fallback"


def test_update_prompt_without_buttons_is_spanish(janitor_spanish):
    """A platform with no native buttons gets the typed-reply prompt (with a default hint)."""
    class _PlainAdapter:  # no send_update_prompt -> text fallback
        typed_command_prefix = "/"

    runner = _runner()
    runner._session_state = MagicMock()
    target = MagicMock(adapter=_PlainAdapter(), send=AsyncMock(), session_key="k")
    asyncio.run(runner._forward_update_prompt(target, "¿Migrar config?", "y"))
    (text,), _ = target.send.call_args
    assert text.startswith("☤ **La actualización necesita una respuesta:**"), text
    assert "¿Migrar config? (por defecto: y)" in text and "`/approve` (sí)" in text, text


# ── `janitor --version` ──────────────────────────────────────────────────────

# The English labels upstream prints after the banner line.
_VERSION_ENGLISH = ("Install directory", "Install method", "OpenAI SDK", "Not installed",
                    "Update available", "Up to date", "behind")


def _version_output(capsys, monkeypatch, behind):
    import hermes_cli.banner as banner
    from hermes_cli._startup_fast import print_fast_version_info

    monkeypatch.setattr(banner, "check_for_updates", lambda passive=True: behind)
    print_fast_version_info(check_updates=True)
    return capsys.readouterr().out.splitlines()


@pytest.mark.parametrize("behind", [0, 3, "no-count"])
def test_version_output_is_spanish(janitor_spanish, capsys, monkeypatch, behind):
    """Every line after the banner comes from the catalog: no English label, no `hermes` command."""
    import hermes_cli.banner as banner

    behind = banner.UPDATE_AVAILABLE_NO_COUNT if behind == "no-count" else behind
    lines = _version_output(capsys, monkeypatch, behind)
    assert lines[0].startswith("THE JANITOR v"), lines
    rest = "\n".join(lines[1:])
    assert not [w for w in _VERSION_ENGLISH if w in rest], rest
    assert not _hermes(rest.replace(str(Path(__file__).resolve().parents[2]), "")), rest
    assert len(lines) >= 4, lines  # directory, (method,) Python, SDK, update status


def test_version_output_keeps_upstream_english_without_the_janitor_catalog(upstream_spanish, capsys, monkeypatch):
    """Upstream's catalogs carry no `runtime_copy.version.*`: the inline English prints as before."""
    rest = "\n".join(_version_output(capsys, monkeypatch, 0)[1:])
    assert "Install directory: " in rest and rest.endswith("Up to date")
