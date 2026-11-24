"""Specialist agents from templates: ``janitor plantillas list|crear``.

A Janitor agent is a Hermes profile (directive #19). A template
(``janitor/templates/<name>/template.yaml`` + a role-only ``SOUL.md``) creates
one with :func:`create_from_template`:

1. ``create_profile(name, no_skills=True)`` — a fresh profile, never a clone
   (``--clone`` copies ``memories/``: specialists share no memory).
2. Config = Janitor's base config (``assets/janitor/config.yaml``) < the model
   block ``create_profile`` copied from the main agent < ``template.config``;
   ``janitor.template`` / ``janitor.skills`` come from the catalog and
   ``janitor.catalog.apply`` generates ``skills.external_dirs``.
3. ``SOUL.md`` = the main persona verbatim + the template's role section
   (the persona is a product invariant, directive #18).
4. The ``sentry-janitor`` skin.
5. The credentials of the profile's model provider, copied from the main
   agent's ``.env`` (each profile resolves its own ``.env``). Only that
   provider's API-key and base-URL variables, never messaging tokens.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import yaml

from janitor.home import ASSETS_ROOT, PACKAGE_ROOT

TEMPLATES_ROOT = PACKAGE_ROOT / "templates"
SKIN_FILE = "sentry-janitor.yaml"
_SOUL_SEPARATOR = "\n\n---\n\n"
# Providers whose key variable is not in ``hermes_cli.auth.PROVIDER_REGISTRY``
# (upstream hardcodes the same names in ``hermes_cli.main``'s provider check).
_UNREGISTERED_PROVIDER_KEYS = {"openrouter": ("OPENROUTER_API_KEY",)}


class TemplateError(ValueError):
    """A template is missing or malformed, or the profile cannot be created."""


@dataclass(frozen=True)
class Template:
    name: str
    display_name: str
    description: str
    config: dict
    role_soul: str
    inherit_soul: bool = True


@dataclass
class Created:
    name: str
    path: Path
    template: str
    skills: List[str] = field(default_factory=list)
    env_keys: List[str] = field(default_factory=list)


def _load(directory: Path) -> Template:
    meta_path = directory / "template.yaml"
    try:
        data = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise TemplateError(f"{meta_path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("name") != directory.name:
        raise TemplateError(f"{meta_path}: `name` must be {directory.name!r}")
    config = data.get("config") or {}
    if not isinstance(config, dict):
        raise TemplateError(f"{meta_path}: `config` must be a mapping")
    soul_path = directory / "SOUL.md"
    role = soul_path.read_text(encoding="utf-8").strip() if soul_path.is_file() else ""
    if not role:
        raise TemplateError(f"{soul_path}: the role section is missing")
    return Template(
        name=directory.name,
        display_name=str(data.get("display_name") or directory.name),
        description=str(data.get("description") or ""),
        config=config,
        role_soul=role,
        inherit_soul=bool(data.get("inherit_soul", True)),
    )


def list_templates(root: Path = TEMPLATES_ROOT) -> List[Template]:
    return [_load(d) for d in sorted(root.iterdir()) if (d / "template.yaml").is_file()] if root.is_dir() else []


def get_template(name: str, root: Path = TEMPLATES_ROOT) -> Template:
    directory = root / name
    if not (directory / "template.yaml").is_file():
        known = ", ".join(t.name for t in list_templates(root)) or "ninguna"
        raise TemplateError(f"no existe la plantilla {name!r} (disponibles: {known})")
    return _load(directory)


def compose_soul(template: Template) -> str:
    """Main persona (verbatim) + the template's role section."""
    if not template.inherit_soul:
        return template.role_soul + "\n"
    persona = (ASSETS_ROOT / "SOUL.md").read_text(encoding="utf-8").rstrip()
    return persona + _SOUL_SEPARATOR + template.role_soul + "\n"


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


@contextlib.contextmanager
def _serving(home_root: Path) -> Iterator[None]:
    """Run upstream profile code against ``home_root`` (its profiles root and model source)."""
    previous = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(home_root)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = previous


def provider_env_keys(config: dict) -> List[str]:
    """The ``.env`` variables the model provider of ``config`` reads: its API keys and base URL."""
    model = config.get("model")
    provider = model.get("provider") if isinstance(model, dict) else None
    if not provider:
        return []
    from hermes_cli.auth import PROVIDER_REGISTRY
    from hermes_cli.providers import get_provider, normalize_provider

    canonical = normalize_provider(str(provider))
    keys: List[str] = list(_UNREGISTERED_PROVIDER_KEYS.get(canonical, ()))
    # A custom endpoint (``providers.<name>``) names its own key variable.
    custom = (config.get("providers") or {}).get(str(provider))
    if isinstance(custom, dict):
        keys += [str(custom[k]) for k in ("key_env", "api_key_env") if custom.get(k)]
    # The auth registry lists the key variables offline; the provider catalog adds
    # overlay extras (and a base-URL variable) without touching the network.
    for pdef in (PROVIDER_REGISTRY.get(canonical), get_provider(canonical, allow_network=False)):
        if pdef is None:
            continue
        for key in (*pdef.api_key_env_vars, pdef.base_url_env_var):
            if key and key not in keys:
                keys.append(key)
    return keys


def _env_values(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    from dotenv import dotenv_values

    return {k: v for k, v in (dotenv_values(path, encoding="utf-8-sig") or {}).items() if v and v.strip()}


def _copy_provider_env(root_env: Path, profile_env: Path, keys: List[str]) -> List[str]:
    values = _env_values(root_env)
    copied = [k for k in keys if k in values]
    if not copied:
        return []
    existing = profile_env.read_text(encoding="utf-8") if profile_env.is_file() else ""
    block = "".join(f"{k}={values[k]}\n" for k in copied)
    sep = "" if not existing or existing.endswith("\n") else "\n"
    profile_env.write_text(existing + sep + "# Copiado del agente principal por `janitor plantillas crear`.\n"
                           + block, encoding="utf-8")
    os.chmod(profile_env, 0o600)
    return copied


def create_from_template(template: str, name: Optional[str] = None, home_root: Optional[Path] = None) -> Created:
    """Create profile ``name`` (default: the template name) under ``home_root`` from ``template``.

    ``home_root`` defaults to the root of the running home. Refuses an existing
    profile (upstream raises ``FileExistsError``); a failure after the profile
    directory was published leaves it in place for inspection.
    """
    from hermes_constants import get_default_hermes_root

    from janitor import catalog as cat
    from janitor.seed import CONFIG_FILE, _CONFIG_HEADER, base_config, with_template

    tmpl = get_template(template)
    root = Path(home_root or get_default_hermes_root()).expanduser()
    profile_name = name or tmpl.name

    with _serving(root):
        from hermes_cli.profiles import create_profile, seed_profile_skills

        try:
            profile = create_profile(profile_name, no_skills=True, description=tmpl.description)
        except FileExistsError as exc:
            raise TemplateError(f"el perfil {profile_name!r} ya existe; no se sobrescribe") from exc
        except ValueError as exc:
            raise TemplateError(str(exc)) from exc
        seed_profile_skills(profile, quiet=True)

    config_path = profile / CONFIG_FILE
    seeded = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
    config = _merge(_merge(base_config(), seeded or {}), tmpl.config)
    config = with_template(config, tmpl.name, profile)
    config_path.write_text(_CONFIG_HEADER + cat.dump_config(config), encoding="utf-8")
    cat.apply(profile)

    (profile / "SOUL.md").write_text(compose_soul(tmpl), encoding="utf-8")

    skin_src = root / "skins" / SKIN_FILE
    skin_dst = profile / "skins" / SKIN_FILE
    skin_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(skin_src if skin_src.is_file() else ASSETS_ROOT / SKIN_FILE, skin_dst)

    env_keys = _copy_provider_env(root / ".env", profile / ".env", provider_env_keys(config))
    return Created(profile_name, profile, tmpl.name, list(config["janitor"][cat.SKILLS_KEY]), env_keys)


# --- CLI (registered by the Janitor plugin as `janitor plantillas`) ----------


def setup_parser(parser) -> None:
    sub = parser.add_subparsers(dest="plantillas_action")
    sub.add_parser("list", help="Lista las plantillas de agente especialista")
    crear = sub.add_parser("crear", help="Crea un agente especialista (perfil) desde una plantilla")
    crear.add_argument("plantilla", help="Nombre de la plantilla (ver `janitor plantillas list`)")
    crear.add_argument("--nombre", default=None, help="Nombre del perfil (por defecto, el de la plantilla)")


def handle(args, out=print) -> int:
    action = getattr(args, "plantillas_action", None) or "list"
    try:
        if action == "list":
            from janitor import catalog as cat

            catalog = cat.load_catalog()
            for t in list_templates():
                skills = cat.skills_for_template(t.name, catalog=catalog)
                out(f"{t.name:<20} {t.display_name:<22} {t.description}")
                out(f"{'':<20} skills: {', '.join(skills) or '-'}")
            return 0
        if action == "crear":
            created = create_from_template(args.plantilla, name=args.nombre)
            out(f"Agente '{created.name}' creado desde la plantilla '{created.template}': {created.path}")
            out(f"  skills: {', '.join(created.skills) or '-'}")
            if created.env_keys:
                out(f"  credenciales copiadas del agente principal: {', '.join(created.env_keys)}")
            else:
                out("  sin credenciales que copiar: configura el proveedor con "
                    f"`janitor -p {created.name} model`.")
            out(f"  memoria vacía. Úsalo con: janitor -p {created.name}")
            return 0
    except (TemplateError, KeyError) as exc:
        out(f"error: {exc}")
        return 1
    out(f"error: acción desconocida {action!r}")
    return 2
