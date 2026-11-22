"""Janitor's backend copy: Spanish, branded "Janitor", without editing upstream catalogs.

The launcher merges ``janitor/locales/<lang>.yaml`` over upstream's ``locales/``
and exports ``HERMES_BUNDLED_LOCALES`` (``janitor.locales``);
``tui_gateway/user_messages.py`` consults the catalog before its English text
(touchpoint ``backend-user-copy``). These tests pin both halves and catch an
upstream sync that adds a Spanish string saying "Hermes".
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from janitor import locales as janitor_locales
from tests.janitor.legacy_home import launcher_env

REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = REPO_ROOT / "locales"

# Mentions a Spanish user may legitimately read: environment variable names,
# URLs and third-party product names. Anything else saying "hermes" is a leak.
_ALLOWED_HERMES = (
    re.compile(r"\bHERMES_[A-Z0-9_]+\b"),  # env var names (HERMES_LANGUAGE, ...)
    re.compile(r"https?://\S+"),  # URLs (docs, repos)
    re.compile(r"\bHermes Cloud\b"),  # hosted service name
)
# Keys whose "hermes" mention is reasoned and accepted: {flat key: reason}.
_ALLOWED_KEYS: dict[str, str] = {}


def _flat(node, prefix="", out=None):
    out = {} if out is None else out
    if isinstance(node, dict):
        for key, value in node.items():
            _flat(value, f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(node, str):
        out[prefix] = node
    return out


def _load(path: Path) -> dict:
    return _flat(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def _hermes_leaks(text: str) -> list[str]:
    for pattern in _ALLOWED_HERMES:
        text = pattern.sub("", text)
    return re.findall(r"(?i)\S*hermes\S*", text)


@pytest.fixture()
def janitor_spanish(tmp_path, monkeypatch):
    """A Spanish Janitor home with the launcher's catalogs exported, as the launcher leaves it."""
    from agent.i18n import reset_language_cache

    home = Path(os.environ["HERMES_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text("display:\n  language: es\n", encoding="utf-8")
    monkeypatch.delenv("HERMES_LANGUAGE", raising=False)
    monkeypatch.delenv(janitor_locales.ENV_VAR, raising=False)
    path = janitor_locales.build(tmp_path / "locales")
    monkeypatch.setenv(janitor_locales.ENV_VAR, str(path))
    reset_language_cache()
    yield path
    reset_language_cache()


@pytest.fixture()
def upstream_spanish(monkeypatch):
    """Same Spanish config, upstream catalogs only (no Janitor launcher)."""
    from agent.i18n import reset_language_cache

    home = Path(os.environ["HERMES_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text("display:\n  language: es\n", encoding="utf-8")
    monkeypatch.delenv("HERMES_LANGUAGE", raising=False)
    monkeypatch.delenv(janitor_locales.ENV_VAR, raising=False)
    reset_language_cache()
    yield
    reset_language_cache()


def _missing_credentials_error():
    """The AuthError the runtime resolver really raises for MiniMax without a key."""
    from hermes_cli.auth_constants import AuthError
    from hermes_cli.runtime_provider import resolve_runtime_provider

    with pytest.raises(AuthError) as info:
        resolve_runtime_provider(requested="minimax")
    return info.value


def _surfaces():
    """Every error_surface shape user_messages distinguishes (codes, layers, the default)."""
    from tui_gateway import user_messages as um

    yield from ({"code": code} for code in um._TURN_ERROR_CODE_COPY)
    yield from ({"layer": layer} for layer in um._TURN_ERROR_LAYER_COPY)
    yield {"layer": "runtime", "code": "agent_init_failed"}


# ── overlay hygiene ──────────────────────────────────────────────────────────


def test_overlay_brand_fixes_name_live_upstream_keys():
    """A brand fix for a key upstream renamed or removed would silently stop applying."""
    upstream_en = _load(UPSTREAM / "en.yaml")
    for lang, path in janitor_locales.overlay_files().items():
        assert (UPSTREAM / f"{lang}.yaml").is_file(), f"overlay for a language upstream lacks: {lang}"
        stale = [k for k in _load(path) if not k.startswith("tui_gateway.") and k not in upstream_en]
        assert not stale, f"{path.name}: keys not in upstream en.yaml: {stale}"


def test_merged_spanish_catalog_lacks_no_key_upstream_spanish_has(janitor_spanish):
    """The merge only adds/replaces: missing keys vs en.yaml are exactly upstream es.yaml's gaps."""
    en, upstream_es = _load(UPSTREAM / "en.yaml"), _load(UPSTREAM / "es.yaml")
    merged = _load(janitor_spanish / "es.yaml")
    assert set(en) - set(merged) == set(en) - set(upstream_es)
    assert set(upstream_es) <= set(merged)


def test_spanish_catalog_never_says_hermes(janitor_spanish):
    """Fails at sync time when upstream adds a Spanish string with "Hermes" or a `hermes` command."""
    merged = _load(janitor_spanish / "es.yaml")
    leaks = {k: _hermes_leaks(v) for k, v in merged.items() if k not in _ALLOWED_KEYS}
    assert not {k: v for k, v in leaks.items() if v}, (
        "Spanish backend strings mention Hermes; add the fix to janitor/locales/es.yaml "
        "(or a reasoned entry to _ALLOWED_KEYS)"
    )


def test_non_overlaid_catalogs_are_upstream_bytes(janitor_spanish):
    overlaid = set(janitor_locales.overlay_files())
    for src in UPSTREAM.glob("*.yaml"):
        if src.stem not in overlaid:
            assert (janitor_spanish / src.name).read_bytes() == src.read_bytes(), src.name


def test_rebuild_from_our_own_output_uses_upstream(tmp_path, monkeypatch):
    """A child launched with the variable already exported must not merge over a stale copy."""
    out = tmp_path / "locales"
    janitor_locales.build(out)
    (out / "es.yaml").write_text("gateway: {help: {header: stale}}\n", encoding="utf-8")
    monkeypatch.setenv(janitor_locales.ENV_VAR, str(out))
    janitor_locales.build(out)
    assert _load(out / "es.yaml")["gateway.help.header"].startswith("📖 **Comandos de Janitor**")


# ── user-visible messages ────────────────────────────────────────────────────


def test_agent_init_failure_is_spanish_janitor(janitor_spanish):
    from tui_gateway.user_messages import agent_init_failed_message

    text = agent_init_failed_message(_missing_credentials_error())
    assert text.startswith("Janitor no pudo iniciar el asistente de esta sesión.")
    assert "No hay credenciales utilizables para el proveedor 'minimax'. Configura MINIMAX_API_KEY." in text
    assert "`janitor setup`" in text and ".." not in text
    assert not _hermes_leaks(text)


def test_failed_turn_after_missing_credentials_is_spanish(janitor_spanish):
    """The turn refusal a user gets after sending a message with no key configured."""
    from tui_gateway.user_messages import turn_error_text

    text = turn_error_text(str(_missing_credentials_error()), {"layer": "runtime", "code": "agent_init_failed"})
    assert text.splitlines() == [
        "La petición falló. Tu mensaje quedó sin respuesta.",
        "Detalles: No hay credenciales utilizables para el proveedor 'minimax'. Configura MINIMAX_API_KEY.",
        "Envía /retry, o cambia de modelo con /model.",
    ]


@pytest.mark.parametrize("recoverable", [True, False])
def test_every_turn_error_shape_is_translated(janitor_spanish, recoverable):
    from tui_gateway.user_messages import turn_error_hint, turn_error_text, turn_error_title

    from agent.i18n import reset_language_cache

    spanish = {json.dumps(s): turn_error_text("x", s, recoverable=recoverable) for s in _surfaces()}
    os.environ.pop(janitor_locales.ENV_VAR)
    reset_language_cache()
    for key, text in spanish.items():
        surface = json.loads(key)
        english_lines = (turn_error_title(surface), turn_error_hint(surface, recoverable))
        assert not any(line in text for line in english_lines), (surface, text)
        assert "Tu mensaje quedó sin respuesta." in text and not _hermes_leaks(text), text


def test_upstream_catalogs_keep_upstream_english_copy(upstream_spanish):
    """Without the launcher, user_messages is byte-for-byte upstream's English."""
    from tui_gateway.user_messages import agent_init_failed_message, turn_error_text

    exc = _missing_credentials_error()
    assert agent_init_failed_message(exc) == (
        f"Hermes could not start the assistant for this session. Details: {exc}. "
        "Check the model and provider with /model, or run `hermes setup` in a terminal to reconfigure.")
    assert turn_error_text("boom", {"layer": "provider", "provider": "minimax"}, recoverable=False) == (
        "The model provider returned an error (minimax). Your message was not answered.\n"
        "Details: boom\n"
        "Pick another model with /model, or switch with /model.")


def test_gateway_replies_use_janitor_catalog(janitor_spanish):
    from agent.i18n import t

    assert t("gateway.help.header").startswith("📖 **Comandos de Janitor**")
    assert t("gateway.status.header") == "📊 **Estado del gateway de Janitor**"
    assert t("gateway.update.starting") == "☤ Iniciando la actualización de Janitor… Transmitiré el progreso aquí."
    assert "janitor config set approvals.timeout 600" in t("approval.timeout", waited="5m", suggested=600)


# ── reach: launcher process and the children it spawns ───────────────────────

_CHILD = "from agent.i18n import t; print(t('gateway.status.header', lang='es'))"

_LAUNCHER = f"""
import json, os, subprocess, sys
sys.argv = ['janitor', 'serve']
import janitor.cli
from hermes_cli.web_server_gateway import _profile_action_environment
from tools.environments.local import build_subprocess_env
envs = {{
    'gateway_action': _profile_action_environment(['gateway', 'run']),
    'profile_gateway_action': _profile_action_environment(['-p', 'coder', 'gateway', 'run']),
    'scrubbed_child': build_subprocess_env(scrub_secrets=True),
}}
out = {{}}
for name, env in envs.items():
    r = subprocess.run([sys.executable, '-c', {_CHILD!r}], env=env, capture_output=True, text=True, timeout=120)
    out[name] = r.stdout.strip() or r.stderr[-400:]
print(json.dumps(out))
"""


@pytest.mark.linux_only
def test_launcher_catalogs_reach_spawned_backends(tmp_path):
    """`python -m janitor.cli serve` exports the catalogs; detached gateways and scrubbed children inherit them."""
    from janitor.seed import ensure_home

    root = tmp_path / ".janitor"
    ensure_home(root)
    profile = root / "profiles" / "coder"
    profile.mkdir(parents=True)
    (profile / "config.yaml").write_text("display:\n  language: es\n", encoding="utf-8")
    env = launcher_env(tmp_path)
    result = subprocess.run(
        [sys.executable, "-c", _LAUNCHER], env=env, cwd=str(tmp_path), capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    seen = json.loads(result.stdout.strip().splitlines()[-1])
    assert seen == {name: "📊 **Estado del gateway de Janitor**" for name in seen}, seen


def test_plain_engine_process_keeps_upstream_catalog(tmp_path):
    """A process started without the launcher (no variable) reads upstream's Spanish."""
    env = {k: v for k, v in os.environ.items() if k != janitor_locales.ENV_VAR}
    result = subprocess.run(
        [sys.executable, "-c", _CHILD], env=env, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
    )
    assert result.stdout.strip() == _load(UPSTREAM / "es.yaml")["gateway.status.header"], result.stderr


# ── reach: processes the launcher did not start (gateway service) ───────────

_PLUGIN_ONLY = """
import json, os
from agent.i18n import t
before = t('gateway.status.header')
from gateway.config import load_gateway_config
load_gateway_config()  # a gateway's startup step: discovers plugins, so the Janitor plugin registers
after = t('gateway.status.header')
from janitor.locales import ensure_exported
first = os.environ.get('HERMES_BUNDLED_LOCALES')
again = str(ensure_exported())
print(json.dumps({'before': before, 'after': after, 'exported': first, 'again': again}))
"""


def _service_home(tmp_path: Path) -> tuple[Path, dict]:
    """A Janitor home as a gateway service sees it: HERMES_HOME set, no launcher environment."""
    home = tmp_path / ".janitor"
    home.mkdir()
    (home / "config.yaml").write_text(
        "plugins:\n  enabled: [janitor]\ndisplay:\n  language: es\n", encoding="utf-8",
    )
    env = launcher_env(tmp_path)
    env.pop(janitor_locales.ENV_VAR, None)
    env["HERMES_HOME"] = str(home)
    return home, env


def test_plugin_gives_a_launcherless_gateway_the_janitor_catalog(tmp_path):
    """A gateway started as a service (no launcher) reads Janitor's catalog once its plugin loads,
    even for a key ``t()`` had already cached from upstream; a second export is a no-op."""
    home, env = _service_home(tmp_path)
    result = subprocess.run(
        [sys.executable, "-c", _PLUGIN_ONLY], env=env, cwd=str(tmp_path), capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    seen = json.loads(result.stdout.strip().splitlines()[-1])
    assert seen["before"] == _load(UPSTREAM / "es.yaml")["gateway.status.header"]
    assert seen["after"] == "📊 **Estado del gateway de Janitor**"
    assert seen["exported"] == seen["again"] == str(home / "cache" / "janitor-locales")


def test_catalog_export_is_once_per_process(tmp_path, monkeypatch):
    monkeypatch.setattr(janitor_locales, "_ensured", None)
    monkeypatch.delenv(janitor_locales.ENV_VAR, raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "root" / "profiles" / "coder"))
    first = janitor_locales.ensure_exported()
    assert first == tmp_path / "root" / "cache" / "janitor-locales", "profiles share the root home's copy"
    builds = []
    monkeypatch.setattr(janitor_locales, "build", lambda *a, **kw: builds.append(a))
    assert janitor_locales.ensure_exported() == first
    assert builds == []


def test_broken_overlay_never_blocks_plugin_registration(tmp_path, monkeypatch):
    from hermes_cli import plugins
    from hermes_constants import get_hermes_home

    broken = tmp_path / "overlays"
    broken.mkdir()
    (broken / "es.yaml").write_text("gateway: {help: [unclosed\n", encoding="utf-8")
    monkeypatch.setattr(janitor_locales, "OVERLAY_DIR", broken)
    monkeypatch.setattr(janitor_locales, "_ensured", None)
    monkeypatch.delenv(janitor_locales.ENV_VAR, raising=False)
    home = get_hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text("plugins:\n  enabled: [janitor]\n", encoding="utf-8")
    plugins._reset_plugin_managers_for_tests()
    try:
        plugins.discover_plugins(force=True)
        loaded = plugins.get_plugin_manager()._plugins["janitor"]
        assert loaded.enabled and not loaded.error
        assert plugins.has_hook("pre_gateway_dispatch")
        assert janitor_locales.ENV_VAR not in os.environ
    finally:
        plugins._reset_plugin_managers_for_tests()
