"""The Janitor look ships as the ``sentry-janitor`` skin, not as TUI code.

Drives the real skin engine and the TUI gateway's ``resolve_skin()`` (the
payload sent in ``gateway.ready``) against a temp ``HERMES_HOME`` holding the
shipped skin, the way ``janitor --tui`` sees it.
"""

from __future__ import annotations

import shutil

import pytest
import yaml

from tests.janitor.legacy_home import ASSETS

SKIN = ASSETS / "sentry-janitor.yaml"


@pytest.fixture
def skin_home(tmp_path, monkeypatch):
    home = tmp_path / ".janitor"
    (home / "skins").mkdir(parents=True)
    shutil.copy2(SKIN, home / "skins" / "sentry-janitor.yaml")
    (home / "config.yaml").write_text("display:\n  skin: sentry-janitor\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))

    import hermes_cli.skin_engine as skin_engine

    monkeypatch.setattr(skin_engine, "_active_skin", None, raising=False)
    return home


def test_tui_receives_the_janitor_skin(skin_home):
    from tui_gateway.server import resolve_skin

    payload = resolve_skin()
    shipped = yaml.safe_load(SKIN.read_text(encoding="utf-8"))

    assert payload["name"] == "sentry-janitor"
    for key, value in shipped["colors"].items():
        assert payload["colors"][key] == value
    for key in ("agent_name", "welcome", "goodbye", "prompt_symbol", "tagline", "vendor"):
        assert payload["branding"][key] == shipped["branding"][key]
    assert payload["help_header"] == shipped["branding"]["help_header"]


def test_seed_config_selects_the_janitor_skin():
    config = yaml.safe_load((ASSETS / "config.yaml").read_text(encoding="utf-8"))
    assert config["display"]["skin"] == "sentry-janitor"
