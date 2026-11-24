"""Desktop plugin "Skills" (F4-04) and "Agentes" (F4-05) screens: their backend.

Real routes (FastAPI ``TestClient`` over ``api.build_router``), real catalog,
real ``create_profile`` in a temp Janitor root (``Path.home`` and ``HERMES_HOME``
both point inside ``tmp_path``). What an agent sees is read back through the
system-prompt skill index, not only from config values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from janitor import catalog as cat
from janitor import profile_templates as pt
from janitor.desktop_plugin import api
from janitor.home import ASSETS_ROOT
from janitor.seed import ensure_home
from tests.janitor.skill_index import ESSENTIAL, skill_index

BASE = "/api/plugins/janitor"
ROOT_ENV = (
    "MINIMAX_API_KEY=sk-minimax-secreto\n"
    "MINIMAX_BASE_URL=https://api.minimax.io/anthropic\n"
    "TELEGRAM_BOT_TOKEN=123456:telegram-secreto\n"
)
SECRETS = ("sk-minimax-secreto", "telegram-secreto")


@pytest.fixture
def root(tmp_path, monkeypatch):
    home = tmp_path / ".janitor"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(home))
    ensure_home(home)
    (home / ".env").write_text(ROOT_ENV, encoding="utf-8")
    return home


@pytest.fixture
def client(root):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(api.build_router(), prefix=BASE)
    return TestClient(app)


@pytest.fixture
def two_agents(root):
    """Specialists ``a`` and ``b`` beside the main agent."""
    a = pt.create_from_template("investigador", name="a", home_root=root).path
    b = pt.create_from_template("creador-proyectos", name="b", home_root=root).path
    return a, b


def _config(home: Path) -> dict:
    return yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))


def _external_dirs(home: Path) -> set:
    return {str(Path(d).resolve()) for d in _config(home)["skills"]["external_dirs"]}


def _available(ids) -> list:
    by_id = cat.load_catalog().by_id()
    platform = cat.current_platform()
    return [i for i in ids if cat.matches_platform(by_id[i], platform)]


def _pick(exclude) -> list:
    """Two catalog skills offered on this OS that are not in ``exclude``."""
    platform = cat.current_platform()
    picks = [e.id for e in cat.load_catalog().entries
             if e.id not in exclude and cat.matches_platform(e, platform) and cat.check_entry(e) is None]
    assert len(picks) >= 2
    return picks[:2]


# ── F4-04: skills of one agent ─────────────────────────────────────────────


def test_get_reflects_the_profiles_selection(client, root, two_agents):
    a, _ = two_agents
    for name, home in (("default", root), ("a", a)):
        view = client.get(f"{BASE}/perfiles/{name}/skills").json()
        assert view["perfil"] == name and view["gestionado"] is True
        assert view["activas"] == _config(home)["janitor"]["skills"]
        listed = [s for g in view["propositos"] for s in g["skills"]]
        # Only the Janitor catalog reaches the screen: an upstream skill outside it is never offered.
        assert {s["id"] for s in listed} == set(cat.load_catalog().by_id())
        assert {s["id"] for s in listed if s["activa"]} == set(view["activas"])
        assert view["aplica"] == "proxima_conversacion"
        assert {p["nombre"] for p in view["perfiles"]} == {"default", "a", "b"}


def test_saving_changes_only_that_agent_a_b_a(client, root, two_agents, monkeypatch):
    a, b = two_agents
    original_a = _config(a)["janitor"]["skills"]
    root_bytes, b_bytes = (root / "config.yaml").read_bytes(), (b / "config.yaml").read_bytes()
    index_b = skill_index(b, monkeypatch)
    wanted = _pick(original_a)

    saved = client.put(f"{BASE}/perfiles/a/skills", json={"skills": wanted})
    assert saved.status_code == 200 and saved.json()["activas"] == wanted

    assert _config(a)["janitor"]["skills"] == wanted
    by_id = cat.load_catalog().by_id()
    assert {str(cat.resolve(by_id[i])) for i in wanted} <= _external_dirs(a)
    assert skill_index(a, monkeypatch) == set(_available(wanted)) | {ESSENTIAL}
    assert (root / "config.yaml").read_bytes() == root_bytes
    assert (b / "config.yaml").read_bytes() == b_bytes
    assert skill_index(b, monkeypatch) == index_b

    # B changes; A keeps what it was given; then A goes back.
    monkeypatch.setenv("HERMES_HOME", str(root))
    assert client.put(f"{BASE}/perfiles/b/skills", json={"skills": []}).status_code == 200
    assert _config(a)["janitor"]["skills"] == wanted
    assert client.put(f"{BASE}/perfiles/a/skills", json={"skills": original_a}).status_code == 200
    assert _config(a)["janitor"]["skills"] == original_a
    assert skill_index(a, monkeypatch) == set(_available(original_a)) | {ESSENTIAL}
    assert skill_index(b, monkeypatch) == {ESSENTIAL}
    assert (root / "config.yaml").read_bytes() == root_bytes


@pytest.mark.parametrize("skills", [
    ["skill-que-no-existe"],
    ["../../../etc"],
    ["/home/usuario/.janitor/skills/x"],
    "pdf",
    [{"id": "pdf"}],
    None,
])
def test_anything_but_catalog_ids_is_refused_without_writing(client, root, two_agents, skills):
    a, _ = two_agents
    before = (a / "config.yaml").read_bytes()
    response = client.put(f"{BASE}/perfiles/a/skills", json={"skills": skills})
    assert response.status_code == 400
    assert (a / "config.yaml").read_bytes() == before


@pytest.mark.parametrize("name", ["no-existe", "A", "..", "default ", "profiles", ".deleted"])
def test_unknown_profiles_are_404(client, root, two_agents, name):
    before = (root / "config.yaml").read_bytes()
    assert client.get(f"{BASE}/perfiles/{name}/skills").status_code == 404
    assert client.put(f"{BASE}/perfiles/{name}/skills", json={"skills": []}).status_code == 404
    assert (root / "config.yaml").read_bytes() == before


def test_install_button_activates_the_guided_skill_once(client, root, two_agents):
    a, _ = two_agents
    assert "janitor-n8n" not in _config(a)["janitor"]["skills"]
    first = client.post(f"{BASE}/perfiles/a/skills/janitor-n8n")
    assert first.status_code == 200 and first.json()["skill"] == "janitor-n8n"
    after = (a / "config.yaml").read_bytes()
    assert _config(a)["janitor"]["skills"].count("janitor-n8n") == 1
    assert client.post(f"{BASE}/perfiles/a/skills/janitor-n8n").status_code == 200
    assert (a / "config.yaml").read_bytes() == after
    assert client.post(f"{BASE}/perfiles/a/skills/..%2Fpdf").status_code in (400, 404)
    assert client.post(f"{BASE}/perfiles/a/skills/no-existe").status_code == 400


# ── F4-05: specialists from templates ──────────────────────────────────────


def test_templates_are_listed_with_their_skills(client, root):
    view = client.get(f"{BASE}/agentes").json()
    by_id = {t["id"]: t for t in view["plantillas"]}
    assert {t.name for t in pt.list_templates()} <= set(by_id)
    for name, t in by_id.items():
        assert t["nombre"] and t["descripcion"]
        assert t["skills"] == cat.skills_for_template(name)
    assert [p["nombre"] for p in view["perfiles"]] == ["default"]


def test_creating_a_specialist(client, root, monkeypatch):
    root_files = {p: p.read_bytes() for p in (root / "config.yaml", root / "SOUL.md", root / ".env")}
    root_memories = sorted(p.name for p in (root / "memories").iterdir()) if (root / "memories").is_dir() else []

    response = client.post(f"{BASE}/agentes", json={"plantilla": "investigador", "nombre": "lupa"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["agente"] == {"nombre": "lupa", "plantilla": "investigador",
                              "skills": cat.skills_for_template("investigador"), "credenciales": True}
    assert "lupa" in {p["nombre"] for p in body["perfiles"]}
    for secret in SECRETS:
        assert secret not in response.text

    profile = root / "profiles" / "lupa"
    assert list((profile / "memories").iterdir()) == []
    persona = (ASSETS_ROOT / "SOUL.md").read_text(encoding="utf-8").rstrip()
    assert (profile / "SOUL.md").read_text(encoding="utf-8").startswith(persona)
    assert _config(profile)["janitor"]["skills"] == cat.skills_for_template("investigador")
    assert skill_index(profile, monkeypatch) == set(cat.skills_for_template("investigador")) | {ESSENTIAL}
    assert "telegram-secreto" not in (profile / ".env").read_text(encoding="utf-8")

    assert {p: p.read_bytes() for p in root_files} == root_files
    assert (sorted(p.name for p in (root / "memories").iterdir()) if (root / "memories").is_dir() else []) \
        == root_memories


@pytest.mark.parametrize("name", ["", "Lupa", "../lupa", "lupa/x", "default", "hermes", "-x", "a b", None, 7,
                                  "x" * 65])
def test_invalid_names_are_refused(client, root, name):
    response = client.post(f"{BASE}/agentes", json={"plantilla": "investigador", "nombre": name})
    assert response.json() == {"ok": False, "error": "nombre_invalido"}
    assert not (root / "profiles").exists() or [p.name for p in (root / "profiles").iterdir()
                                                 if not p.name.startswith(".")] == []


def test_existing_name_and_unknown_template_are_refused(client, root, two_agents):
    a, _ = two_agents
    soul = (a / "SOUL.md").read_bytes()
    assert client.post(f"{BASE}/agentes", json={"plantilla": "investigador", "nombre": "a"}).json() == \
        {"ok": False, "error": "existe"}
    assert (a / "SOUL.md").read_bytes() == soul
    for template in ("astronauta", "../investigador", "main", None):
        assert client.post(f"{BASE}/agentes", json={"plantilla": template, "nombre": "nuevo"}).json() == \
            {"ok": False, "error": "plantilla_desconocida"}
    assert not (root / "profiles" / "nuevo").exists()


def test_the_child_reports_no_secret(root, capsys):
    """The creation child's only output is one JSON line without credential values."""
    from janitor.desktop_plugin import perfiles

    assert perfiles.run_create("investigador", "sabueso") == 0
    out = capsys.readouterr().out.strip().splitlines()
    payload = json.loads(out[-1])
    assert payload["ok"] is True and payload["credenciales"] is True
    for secret in SECRETS:
        assert secret not in "\n".join(out)
