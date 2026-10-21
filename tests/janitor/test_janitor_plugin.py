"""The Janitor plugin, loaded through the real entry-point discovery path."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import yaml

from hermes_cli import plugins
from hermes_constants import get_hermes_home

INSTRUCTION = "Responde solo en español o inglés."


def _write_config(cfg: dict) -> None:
    home = get_hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")


@pytest.fixture
def discover():
    def _discover():
        plugins._reset_plugin_managers_for_tests()
        plugins.discover_plugins(force=True)
        return plugins.get_plugin_manager()

    yield _discover
    plugins._reset_plugin_managers_for_tests()


def test_language_instruction_lands_in_new_session_prompt(discover):
    _write_config({"plugins": {"enabled": ["janitor"]}, "janitor": {"language_instruction": INSTRUCTION}})
    discover()

    from agent.system_prompt import _frozen_plugin_prompt_sections

    agent = SimpleNamespace(session_id="s1", model="m", provider="p", platform="cli")
    sections = _frozen_plugin_prompt_sections(agent)

    assert [(s.id, s.content) for s in sections] == [("janitor.language", INSTRUCTION)]


def test_empty_instruction_adds_no_section(discover):
    _write_config({"plugins": {"enabled": ["janitor"]}})
    discover()

    assert plugins.render_system_prompt_sections({}) == []


def test_plugin_is_opt_in(discover):
    _write_config({"plugins": {"enabled": []}, "janitor": {"language_instruction": INSTRUCTION}})
    manager = discover()

    assert plugins.render_system_prompt_sections({}) == []
    loaded = manager._plugins.get("janitor")
    assert loaded is not None and loaded.enabled is False


def test_enabled_plugin_registers_its_hooks(discover):
    _write_config({"plugins": {"enabled": ["janitor"]}})
    manager = discover()

    loaded = manager._plugins["janitor"]
    assert loaded.enabled and not loaded.error
    assert plugins.has_hook("pre_gateway_dispatch")
