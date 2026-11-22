"""``janitor plantillas``: specialist agents created from templates (F2-03).

Real ``create_profile`` + real catalog against a temp Janitor root; the skill
index is read back through the system-prompt builder.
"""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

import pytest
import yaml

from janitor import catalog as cat
from janitor import profile_templates as pt
from janitor.home import ASSETS_ROOT
from janitor.seed import ensure_home
from tests.janitor.skill_index import ESSENTIAL, skill_index

ROOT_ENV = (
    "MINIMAX_API_KEY=sk-minimax-test\n"
    "MINIMAX_BASE_URL=https://api.minimax.io/anthropic\n"
    "TELEGRAM_BOT_TOKEN=123456:telegram-test\n"
    "DISCORD_BOT_TOKEN=discord-test\n"
    "TELEGRAM_ALLOWED_USERS=42\n"
    "FIRECRAWL_API_KEY=fc-test\n"
    "HONCHO_API_KEY=honcho-test\n"
)


@pytest.fixture
def root(tmp_path, monkeypatch):
    home = tmp_path / ".janitor"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(home))
    ensure_home(home)
    (home / ".env").write_text(ROOT_ENV, encoding="utf-8")
    return home


def _env_keys(path: Path) -> set:
    return {line.split("=", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line}


def test_templates_are_listed_and_each_offers_skills():
    names = {t.name for t in pt.list_templates()}
    assert {"investigador", "creador-proyectos"} <= names
    catalog = cat.load_catalog()
    for t in pt.list_templates():
        assert t.name in catalog.templates
        assert cat.skills_for_template(t.name, catalog=catalog)
        assert t.role_soul and t.description


def test_specialist_is_a_janitor_agent_with_its_own_skills(root, monkeypatch):
    root_env_before = (root / ".env").read_bytes()
    main = set(cat.skills_for_template("main"))
    research = set(cat.skills_for_template("investigador"))
    assert main != research

    root_index = skill_index(root, monkeypatch)
    created = pt.create_from_template("investigador", home_root=root)
    profile = created.path
    specialist_index = skill_index(profile, monkeypatch)
    root_again = skill_index(root, monkeypatch)            # A -> B -> A

    assert profile == root / "profiles" / "investigador"
    assert root_index == root_again == main | {ESSENTIAL}
    assert specialist_index == research | {ESSENTIAL}

    soul = (profile / "SOUL.md").read_text(encoding="utf-8")
    persona = (ASSETS_ROOT / "SOUL.md").read_text(encoding="utf-8").rstrip()
    assert soul.startswith(persona)
    assert pt.get_template("investigador").role_soul in soul

    assert list((profile / "memories").iterdir()) == []
    assert (profile / ".no-bundled-skills").is_file()
    assert (profile / "skins" / "sentry-janitor.yaml").read_bytes() == \
        (root / "skins" / "sentry-janitor.yaml").read_bytes()

    from hermes_cli.config import load_config
    monkeypatch.setenv("HERMES_HOME", str(profile))
    config = load_config()
    assert "janitor" in config["plugins"]["enabled"]
    assert config["display"]["language"] == "es"
    assert config["display"]["skin"] == "sentry-janitor"
    assert config["janitor"]["template"] == "investigador"

    # Exactly the main model provider's variables; no messaging or tool secret.
    assert created.env_keys == ["MINIMAX_API_KEY", "MINIMAX_BASE_URL"]
    assert _env_keys(profile / ".env") == {"MINIMAX_API_KEY", "MINIMAX_BASE_URL"}
    assert "telegram-test" not in (profile / ".env").read_text(encoding="utf-8")
    assert (root / ".env").read_bytes() == root_env_before


def test_copied_keys_follow_the_main_agents_provider(root):
    path = root / "config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["model"] = {"default": "some/model", "provider": "openrouter"}
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    (root / ".env").write_text(ROOT_ENV + "OPENROUTER_API_KEY=sk-or-test\n", encoding="utf-8")

    created = pt.create_from_template("creador-proyectos", name="constructor", home_root=root)

    assert yaml.safe_load((created.path / "config.yaml").read_text(encoding="utf-8"))["model"]["provider"] == "openrouter"
    assert created.env_keys == ["OPENROUTER_API_KEY"]
    assert _env_keys(created.path / ".env") == {"OPENROUTER_API_KEY"}


def test_existing_profile_is_never_overwritten(root):
    created = pt.create_from_template("investigador", home_root=root)
    marker = created.path / "memories" / "MEMORY.md"
    marker.write_text("recuerdo\n", encoding="utf-8")
    soul_before = (created.path / "SOUL.md").read_bytes()

    with pytest.raises(pt.TemplateError, match="ya existe"):
        pt.create_from_template("creador-proyectos", name="investigador", home_root=root)

    assert marker.read_text(encoding="utf-8") == "recuerdo\n"
    assert (created.path / "SOUL.md").read_bytes() == soul_before


def test_unknown_template_is_refused(root):
    with pytest.raises(pt.TemplateError, match="no existe"):
        pt.create_from_template("astronauta", home_root=root)
    assert not (root / "profiles" / "astronauta").exists()


def test_cli_list_and_crear_through_the_plugin_handler(root, monkeypatch):
    """The registered command parses and runs ``list`` and ``crear`` end to end."""
    from hermes_cli import plugins

    plugins._reset_plugin_managers_for_tests()
    try:
        plugins.discover_plugins(force=True)
        command = plugins.get_plugin_manager()._cli_commands["plantillas"]
    finally:
        plugins._reset_plugin_managers_for_tests()

    parser = ArgumentParser(prog="janitor plantillas")
    command["setup_fn"](parser)
    handler = command["handler_fn"]

    lines: list = []
    assert handler(parser.parse_args(["list"]), out=lines.append) == 0
    assert any(line.startswith("investigador") for line in lines)

    lines.clear()
    assert handler(parser.parse_args(["crear", "investigador", "--nombre", "lupa"]), out=lines.append) == 0
    assert (root / "profiles" / "lupa" / "SOUL.md").is_file()
    assert "lupa" in lines[0]

    lines.clear()
    assert handler(parser.parse_args(["crear", "investigador", "--nombre", "lupa"]), out=lines.append) == 1
    assert lines[0].startswith("error:")
