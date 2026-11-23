"""Backend of the desktop plugin's "Skills" and "Agentes" screens (F4-04, F4-05).

Mounted with the "Servicios" routes by :func:`janitor.desktop_plugin.api.build_router`.

A Janitor agent is a Hermes profile (directive #19). Nothing the client sends
becomes a path:

* a profile is addressed by name; the name must be one of the profiles that
  exist under the Janitor root (``hermes_cli.profiles.list_profile_names``) and
  only then is it mapped to its directory (``get_profile_dir``);
* skills are addressed by catalog id; anything that is not an id of
  ``janitor/catalog.yaml`` is refused before anything is written;
* a template is addressed by the name of one of the shipped templates.

Changing an agent's skills writes ``janitor.skills`` (and the generated
``skills.external_dirs``) of that profile's ``config.yaml`` only. A
conversation already open keeps its system prompt (prompt caching): the change
applies from the next conversation, and nothing is invalidated in place.

Creating a specialist reuses :func:`janitor.profile_templates.create_from_template`
in a child process: that function points ``HERMES_HOME`` at the Janitor root
while it runs, which inside a gateway serving another profile would be seen
by every other thread. The child's result carries no secret: whether provider
credentials were copied is a boolean.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import yaml

from janitor import catalog as cat

MAIN_PROFILE = "default"
MAX_SKILLS = 200          # a request listing more ids than this is not from the screen
CREATE_TIMEOUT = 120.0    # seconds for the child that creates a specialist

# Error codes of the agent creation (the screen translates them).
ERR_NAME = "nombre_invalido"
ERR_EXISTS = "existe"
ERR_TEMPLATE = "plantilla_desconocida"
ERR_FAILED = "fallo"
ERR_TIMEOUT = "tiempo_agotado"

_write_locks: dict = {}
_write_locks_guard = threading.Lock()
_create_lock = threading.Lock()


class UnknownProfile(LookupError):
    """The name is not an existing profile (or not a valid profile name at all)."""


class InvalidSkills(ValueError):
    """The requested selection is not a list of catalog ids."""


def _profile_id_re():
    from hermes_constants import PROFILE_ID_RE

    return PROFILE_ID_RE


def janitor_root() -> Path:
    """The Janitor root whose ``profiles/`` this backend administers."""
    from hermes_constants import get_default_hermes_root

    return Path(get_default_hermes_root())


def profile_names() -> List[str]:
    """``default`` (the main agent) and every live named profile."""
    from hermes_cli.profiles import list_profile_names

    return list_profile_names()


def resolve_profile(name) -> Tuple[str, Path]:
    """``(name, directory)`` of the existing profile called exactly ``name``.

    No normalisation: the screen only sends back names it received.
    """
    if not isinstance(name, str) or not _profile_id_re().fullmatch(name):
        raise UnknownProfile(name)
    if name not in profile_names():
        raise UnknownProfile(name)
    from hermes_cli.profiles import get_profile_dir

    directory = Path(get_profile_dir(name))
    if not (directory / "config.yaml").is_file():
        raise UnknownProfile(name)
    return name, directory


def _read_config(home: Path) -> dict:
    try:
        data = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _profile_row(name: str, home: Path) -> dict:
    janitor_cfg = _read_config(home).get("janitor")
    janitor_cfg = janitor_cfg if isinstance(janitor_cfg, dict) else {}
    skills = janitor_cfg.get(cat.SKILLS_KEY)
    template = janitor_cfg.get(cat.TEMPLATE_KEY)
    return {
        "nombre": name,
        "principal": name == MAIN_PROFILE,
        "plantilla": str(template) if template else None,
        "skills": len(skills) if isinstance(skills, list) else None,
    }


def profiles_view() -> List[dict]:
    from hermes_cli.profiles import get_profile_dir

    rows = []
    for name in profile_names():
        home = Path(get_profile_dir(name))
        if (home / "config.yaml").is_file():
            rows.append(_profile_row(name, home))
    return rows


# --- F4-04: skills of one agent -------------------------------------------


def _skill_row(entry: cat.Entry, platform: str, active: set) -> dict:
    path = cat.resolve(entry)
    return {
        "id": entry.id,
        "proposito": entry.purpose,
        "plataformas": list(entry.platforms),
        "plantillas": list(entry.templates),
        "disponible": cat.matches_platform(entry, platform) and (path is None or path.is_dir()),
        "otra_plataforma": not cat.matches_platform(entry, platform),
        "activa": entry.id in active,
        # The SKILL.md description (upstream's is in English): the screen shows
        # its own Spanish text and keeps this only as data.
        "descripcion": _skill_description(path),
    }


def _skill_description(path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        text = (path / "SKILL.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    if not text.startswith("---"):
        return ""
    try:
        front = yaml.safe_load(text.split("---", 2)[1])
    except (yaml.YAMLError, IndexError):
        return ""
    value = front.get("description") if isinstance(front, dict) else None
    return str(value).strip() if value else ""


def skills_view(name: str) -> dict:
    """The catalog grouped by purpose, with what profile ``name`` has active."""
    name, home = resolve_profile(name)
    catalog = cat.load_catalog()
    platform = cat.current_platform()
    selection = cat.read_selection(home)
    active = set(selection or [])
    groups = []
    for purpose, label in catalog.purposes.items():
        rows = [_skill_row(e, platform, active) for e in catalog.entries if e.purpose == purpose]
        if rows:
            groups.append({"id": purpose, "nombre": label, "skills": rows})
    known = set(catalog.by_id())
    return {
        "perfil": name,
        "perfiles": profiles_view(),
        "plataforma": platform,
        # False: the profile predates the catalog; saving makes it catalog-managed.
        "gestionado": selection is not None,
        "plantilla": _profile_row(name, home)["plantilla"],
        "activas": [sid for sid in (selection or []) if sid in known],
        "fuera_del_catalogo": [sid for sid in (selection or []) if sid not in known],
        "propositos": groups,
        "aplica": "proxima_conversacion",
    }


def _validated_ids(ids) -> List[str]:
    if not isinstance(ids, list) or len(ids) > MAX_SKILLS:
        raise InvalidSkills("skills must be a list of catalog ids")
    if not all(isinstance(sid, str) for sid in ids):
        raise InvalidSkills("skills must be a list of catalog ids")
    known = cat.load_catalog().by_id()
    unknown = [sid for sid in ids if sid not in known]
    if unknown:
        raise InvalidSkills(f"not in the catalog: {', '.join(unknown[:5])}")
    out: List[str] = []
    for sid in ids:
        if sid not in out:
            out.append(sid)
    return out


def _write_lock(home: Path) -> threading.Lock:
    with _write_locks_guard:
        return _write_locks.setdefault(str(home), threading.Lock())


def set_skills(name: str, ids) -> dict:
    """Make ``ids`` the skills of profile ``name``. Refuses (writing nothing) any non-catalog id."""
    name, home = resolve_profile(name)
    selected = _validated_ids(ids)
    with _write_lock(home):
        cat.set_selection(home, selected)
    return {"ok": True, **skills_view(name)}


def activate_skill(name: str, skill_id) -> dict:
    """Add one catalog skill to profile ``name`` (idempotent): «Instalar con Janitor» of Servicios."""
    name, home = resolve_profile(name)
    [sid] = _validated_ids([skill_id])
    with _write_lock(home):
        current = cat.read_selection(home) or []
        if sid not in current:
            cat.set_selection(home, [*current, sid])
    return {"ok": True, "perfil": name, "skill": sid, "aplica": "proxima_conversacion"}


# --- F4-05: specialists from templates ------------------------------------


def templates_view() -> dict:
    from janitor import profile_templates as pt

    catalog = cat.load_catalog()
    templates = [
        {
            "id": t.name,
            "nombre": t.display_name,
            "descripcion": t.description,
            "skills": cat.skills_for_template(t.name, catalog=catalog),
        }
        for t in pt.list_templates()
        if t.name in catalog.templates
    ]
    return {"plantillas": templates, "perfiles": profiles_view()}


def _template_names() -> List[str]:
    from janitor import profile_templates as pt

    return [t.name for t in pt.list_templates()]


def validate_new_name(name) -> Optional[str]:
    """The error code for ``name`` as a new profile name, or None when it is acceptable.

    Same rules as Hermes profiles (``validate_profile_name``), on the exact
    string: no case folding or trimming, so what is created is what was typed.
    """
    if not isinstance(name, str) or not _profile_id_re().fullmatch(name) or name == MAIN_PROFILE:
        return ERR_NAME
    from hermes_cli.profiles import validate_profile_name

    try:
        validate_profile_name(name)
    except ValueError:
        return ERR_NAME
    if name in profile_names():
        return ERR_EXISTS
    return None


def _child_env(root: Path) -> dict:
    from tools.environments.local import served_profile_child_env

    env = served_profile_child_env(target_home=root)
    package_parent = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = os.pathsep.join(p for p in (package_parent, env.get("PYTHONPATH", "")) if p)
    return env


def create_agent(template, name) -> dict:
    """Create specialist ``name`` from ``template``. Expected failures: ``{"ok": False, "error": code}``."""
    if not isinstance(template, str) or template not in _template_names():
        return {"ok": False, "error": ERR_TEMPLATE}
    problem = validate_new_name(name)
    if problem:
        return {"ok": False, "error": problem}
    root = janitor_root()
    with _create_lock:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "janitor.desktop_plugin.crear_agente", template, name],
                capture_output=True, text=True, timeout=CREATE_TIMEOUT, env=_child_env(root),
                cwd=str(root), stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": ERR_TIMEOUT}
    result = _last_json_line(proc.stdout)
    if not isinstance(result, dict) or "ok" not in result:
        return {"ok": False, "error": ERR_FAILED}
    if not result["ok"]:
        return {"ok": False, "error": result.get("error") if result.get("error") in (ERR_NAME, ERR_EXISTS, ERR_TEMPLATE) else ERR_FAILED}
    return {
        "ok": True,
        "agente": {
            "nombre": str(result.get("nombre")),
            "plantilla": str(result.get("plantilla")),
            "skills": [str(s) for s in result.get("skills") or []],
            "credenciales": bool(result.get("credenciales")),
        },
        "perfiles": profiles_view(),
    }


def _last_json_line(text: str):
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                return None
    return None


def run_create(template: str, name: str, out=print) -> int:
    """Child side of :func:`create_agent` (``python -m janitor.desktop_plugin.crear_agente``)."""
    from janitor import profile_templates as pt

    def emit(payload: dict) -> None:
        out(json.dumps(payload, ensure_ascii=False))

    try:
        created = pt.create_from_template(template, name=name, home_root=janitor_root())
    except pt.TemplateError as exc:
        error = ERR_EXISTS if isinstance(exc.__cause__, FileExistsError) else ERR_FAILED
        emit({"ok": False, "error": error})
        return 1
    emit({
        "ok": True,
        "nombre": created.name,
        "plantilla": created.template,
        "skills": list(created.skills),
        "credenciales": bool(created.env_keys),
    })
    return 0


def _main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print(json.dumps({"ok": False, "error": ERR_FAILED}))
        return 2
    return run_create(argv[0], argv[1])
