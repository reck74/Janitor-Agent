"""Skill ``janitor-obreros`` (F7-07) y su plantilla, Creador de proyectos (F7-08).

Todo pasa por el código real: el catálogo, ``create_from_template`` en un home
temporal, el índice de skills del prompt de sistema y ``skill_view``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from janitor import catalog as cat
from janitor import profile_templates as pt
from janitor.seed import ensure_home

SKILL = "janitor-obreros"
HERRAMIENTAS = {"obreros_enviar", "obreros_ver"}


@pytest.fixture
def root(tmp_path, monkeypatch):
    home = tmp_path / ".janitor"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("JANITOR_SKILLS_ROOT", raising=False)
    ensure_home(home)
    return home


def _indice(home: Path, monkeypatch, herramientas) -> set:
    """Skills del bloque ``<available_skills>`` que vería un agente con ``herramientas``."""
    from agent import skill_utils
    from agent.prompt_builder import build_skills_system_prompt, clear_skills_system_prompt_cache
    from tools.skills_sync import sync_skills

    monkeypatch.setenv("HERMES_HOME", str(home))
    skill_utils._external_dirs_cache_clear()
    clear_skills_system_prompt_cache()
    sync_skills(quiet=True)
    prompt = build_skills_system_prompt(available_tools=set(herramientas), available_toolsets={"terminal", "file"})
    block = prompt.split("<available_skills>", 1)[1].split("</available_skills>", 1)[0]
    return set(re.findall(r"^\s+- ([^:\s]+):", block, re.M))


def test_la_entrada_del_catalogo_resuelve_y_va_en_creador_de_proyectos():
    catalog = cat.load_catalog()
    entrada = catalog.by_id()[SKILL]
    assert cat.check_entry(entrada) is None
    for plataforma in cat.PLATFORMS:
        assert SKILL in cat.skills_for_template("creador-proyectos", catalog=catalog, platform=plataforma)
    assert SKILL not in cat.skills_for_template("main", catalog=catalog)


def test_el_creador_de_proyectos_la_ve_solo_con_las_herramientas_de_obreros(root, monkeypatch):
    creado = pt.create_from_template("creador-proyectos", home_root=root)
    assert SKILL in creado.skills

    con_obreros = _indice(creado.path, monkeypatch, HERRAMIENTAS | {"terminal"})
    sin_obreros = _indice(creado.path, monkeypatch, {"terminal"})
    principal = _indice(root, monkeypatch, HERRAMIENTAS | {"terminal"})

    assert SKILL in con_obreros
    assert SKILL not in sin_obreros
    # Sin obreros, el perfil conserva el resto de sus skills: trabaja como siempre.
    assert sin_obreros == con_obreros - {SKILL}
    assert SKILL not in principal


def test_el_cargador_real_de_skills_la_sirve_en_el_perfil(root, monkeypatch):
    from agent import skill_utils
    from tools.skills_tool import skill_view

    creado = pt.create_from_template("creador-proyectos", name="obra", home_root=root)
    monkeypatch.setenv("HERMES_HOME", str(creado.path))
    skill_utils._external_dirs_cache_clear()

    vista = json.loads(skill_view(SKILL))

    assert vista["success"] is True, vista
    assert vista["name"] == SKILL
    assert vista["content"].strip()
    assert Path(vista["skill_dir"]).resolve() == cat.resolve(cat.load_catalog().by_id()[SKILL]).resolve()
