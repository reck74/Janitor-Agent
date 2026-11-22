"""Janitor skill catalog: which skills exist for Janitor agents and where they live.

``janitor/catalog.yaml`` lists every skill a Janitor agent (a Hermes profile)
may use, by purpose and template (directive #19). A profile chooses skills by
id in ``janitor.skills`` of its ``config.yaml``; :func:`apply` turns that list
into ``skills.external_dirs`` — one absolute entry per skill, pointing at the
skill's directory in this install tree (upstream indexes a single-skill
directory under the ``general`` category).

A profile created from a template (``janitor.template``) also follows that
template as the catalog evolves: see :func:`evolve_selection`. The seed, the
launcher (every start, for the home it serves) and ``janitor update`` (every
Janitor home) run the same reconciliation.

Import-light on purpose (stdlib + PyYAML): the launcher and the seed call it
before Hermes is configured, and ``hermes_cli.config`` is imported only inside
:func:`apply`, the same way ``janitor.migrations.v1`` does.

    python -m janitor.catalog list
    python -m janitor.catalog check
    python -m janitor.catalog apply --home ~/.janitor
"""

from __future__ import annotations

import argparse
import copy
import logging
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from janitor.home import PACKAGE_ROOT, REPO_ROOT, SKILLS_ROOT

logger = logging.getLogger(__name__)

CATALOG_PATH = PACKAGE_ROOT / "catalog.yaml"
SCHEMA_VERSION = 1
SOURCES = ("janitor", "upstream-bundled", "upstream-optional", "hub")
# Same vocabulary as the skills' ``platforms:`` frontmatter (agent.skill_utils.PLATFORM_MAP).
PLATFORMS = ("linux", "macos", "windows")
_SYS_PLATFORM_PREFIX = {"darwin": "macos", "win32": "windows", "linux": "linux"}
# Legacy whole-root entries (janitor.home.SKILLS_EXTERNAL_DIRS) spell the root
# through the launcher's variable, which may be unset when apply() runs.
_ROOT_VARS = ("${JANITOR_SKILLS_ROOT}", "$JANITOR_SKILLS_ROOT")


class CatalogError(ValueError):
    """The catalog file is malformed."""


@dataclass(frozen=True)
class Entry:
    id: str
    source: str
    path: str
    purpose: str
    templates: Tuple[str, ...] = ()
    platforms: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Catalog:
    purposes: Dict[str, str]
    templates: Dict[str, str]
    entries: Tuple[Entry, ...]

    def by_id(self) -> Dict[str, Entry]:
        return {e.id: e for e in self.entries}


@dataclass
class ApplyResult:
    changed: bool = False
    managed: bool = False                                  # False: no ``janitor.skills``, config untouched
    external_dirs: List[str] = field(default_factory=list)  # the written list (when managed)
    unknown: List[str] = field(default_factory=list)        # ids not in the catalog
    unresolved: List[str] = field(default_factory=list)     # ids whose directory is missing here
    other_platform: List[str] = field(default_factory=list)  # ids gated to another OS
    added: List[str] = field(default_factory=list)          # template skills offered for the first time
    dropped: List[str] = field(default_factory=list)        # ids gone from the catalog, removed from janitor.skills


@dataclass
class SelectionChange:
    """What :func:`evolve_selection` changed in ``janitor.skills``."""

    added: List[str] = field(default_factory=list)
    dropped: List[str] = field(default_factory=list)


# --- loading -----------------------------------------------------------------


def _str_tuple(value, what: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise CatalogError(f"{what} must be a list of names")
    return tuple(v.strip() for v in value)


def _name_map(value, what: str) -> Dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise CatalogError(f"`{what}` must be a non-empty mapping")
    return {str(k): str(v) for k, v in value.items()}


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    """Parse and validate the catalog; raises :class:`CatalogError` on any defect."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CatalogError(f"{path}: top level must be a mapping")
    if data.get("schema") != SCHEMA_VERSION:
        raise CatalogError(f"{path}: unsupported schema {data.get('schema')!r} (expected {SCHEMA_VERSION})")
    purposes = _name_map(data.get("purposes"), "purposes")
    templates = _name_map(data.get("templates"), "templates")
    raw = data.get("skills")
    if not isinstance(raw, list):
        raise CatalogError(f"{path}: `skills` must be a list")

    entries: List[Entry] = []
    seen: set = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CatalogError(f"skills[{i}] must be a mapping")
        sid = str(item.get("id") or "").strip()
        where = f"skills[{i}] ({sid or 'no id'})"
        if not sid:
            raise CatalogError(f"{where}: missing `id`")
        if sid in seen:
            raise CatalogError(f"{where}: duplicate id")
        seen.add(sid)
        source = item.get("source")
        if source not in SOURCES:
            raise CatalogError(f"{where}: unknown source {source!r} (expected one of {', '.join(SOURCES)})")
        rel = str(item.get("path") or "").strip()
        if source != "hub":
            if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
                raise CatalogError(f"{where}: `path` must be relative to its source tree")
        purpose = item.get("purpose")
        if purpose not in purposes:
            raise CatalogError(f"{where}: unknown purpose {purpose!r}")
        if "templates" not in item:
            raise CatalogError(f"{where}: missing `templates` (use [] for an optional skill)")
        tmpl = _str_tuple(item.get("templates"), f"{where}: templates")
        for t in tmpl:
            if t not in templates:
                raise CatalogError(f"{where}: unknown template {t!r}")
        plats = _str_tuple(item.get("platforms"), f"{where}: platforms")
        for p in plats:
            if p not in PLATFORMS:
                raise CatalogError(f"{where}: unknown platform {p!r} (expected one of {', '.join(PLATFORMS)})")
        entries.append(Entry(sid, source, rel, purpose, tmpl, plats))
    return Catalog(purposes, templates, tuple(entries))


# --- resolution --------------------------------------------------------------


def bundled_skills_dir() -> Path:
    """The install tree's ``skills/`` — upstream's own lookup (``tools/skills_sync._get_bundled_dir``)."""
    from hermes_constants import get_bundled_skills_dir  # stdlib-only, no side effects

    return get_bundled_skills_dir(REPO_ROOT / "skills")


def optional_skills_dir() -> Path:
    """The install tree's ``optional-skills/`` (``tools/skills_sync._get_optional_dir``)."""
    from hermes_constants import get_optional_skills_dir

    return get_optional_skills_dir(REPO_ROOT / "optional-skills")


def source_roots() -> Dict[str, Path]:
    return {"janitor": SKILLS_ROOT, "upstream-bundled": bundled_skills_dir(),
            "upstream-optional": optional_skills_dir()}


def resolve(entry: Entry) -> Optional[Path]:
    """Absolute directory of ``entry`` in this install; None for ``hub`` (installed per home).

    The directory may not exist (e.g. a packaging that drops ``optional-skills/``).
    """
    root = source_roots().get(entry.source)
    return None if root is None else (root / entry.path).resolve()


def current_platform() -> str:
    from hermes_platform.host.facts import os_family

    family = os_family()
    for prefix, name in _SYS_PLATFORM_PREFIX.items():
        if family.startswith(prefix):
            return name
    return family


def matches_platform(entry: Entry, platform: str) -> bool:
    return not entry.platforms or platform in entry.platforms


def skills_for_template(name: str, *, catalog: Optional[Catalog] = None,
                        platform: Optional[str] = None) -> List[str]:
    """Catalog ids of template ``name``, in catalog order, offered on ``platform`` (default: this OS)."""
    catalog = catalog or load_catalog()
    if name not in catalog.templates:
        raise KeyError(f"unknown template {name!r}")
    platform = platform or current_platform()
    return [e.id for e in catalog.entries if name in e.templates and matches_platform(e, platform)]


def read_skill_name(skill_dir: Path) -> Optional[str]:
    """Frontmatter ``name`` of ``skill_dir/SKILL.md``; None when missing or unparseable."""
    try:
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = re.match(r"\A﻿?---\s*\n(.*?)\n---\s*(?:\n|\Z)", text, re.S)
    if not match:
        return None
    try:
        front = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    name = front.get("name") if isinstance(front, dict) else None
    return str(name).strip() if name else None


def check_entry(entry: Entry) -> Optional[str]:
    """Why ``entry`` does not resolve to its own skill here, or None when it does."""
    if entry.source == "hub":
        return None
    path = resolve(entry)
    if path is None or not (path / "SKILL.md").is_file():
        return f"no SKILL.md at {path}"
    name = read_skill_name(path)
    if name != entry.id:
        return f"SKILL.md name is {name!r}, expected {entry.id!r}"
    return None


# --- apply -------------------------------------------------------------------


def _expand_entry(raw: str, home: Path) -> Path:
    text = raw
    for var in _ROOT_VARS:
        text = text.replace(var, str(SKILLS_ROOT))
    p = Path(os.path.expanduser(os.path.expandvars(text)))
    if not p.is_absolute():
        p = home / p
    try:
        return p.resolve()
    except OSError:
        return p


def _is_within(path: Path, root: Path) -> bool:
    try:
        root = root.resolve()
    except OSError:
        pass
    return path == root or root in path.parents


def _owned(raw: str, home: Path, roots: Sequence[Path], catalog: Catalog) -> bool:
    """An ``external_dirs`` entry apply() manages (replaces) rather than preserves."""
    path = _expand_entry(raw, home)
    if any(_is_within(path, r) for r in roots):
        return True
    # A catalog entry left behind by an install that moved: same tail, gone from disk.
    if path.exists():
        return False
    posix = path.as_posix()
    tails = {"janitor": "janitor/skills", "upstream-bundled": "skills", "upstream-optional": "optional-skills"}
    return any(e.source in tails and posix.endswith(f"/{tails[e.source]}/{e.path}") for e in catalog.entries)


def _leading_comments(text: str) -> str:
    lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith("#") or (lines and not line.strip()):
            lines.append(line)
        else:
            break
    while lines and not lines[-1].strip():
        lines.pop()
    return "".join(lines)


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def plan_external_dirs(selected: Sequence, current: Sequence[str], home: Path,
                       catalog: Catalog, platform: Optional[str] = None) -> Tuple[List[str], ApplyResult]:
    """The ``external_dirs`` list for ``selected`` ids, keeping entries apply() does not own."""
    result = ApplyResult(managed=True)
    platform = platform or current_platform()
    by_id = catalog.by_id()
    roots = list(source_roots().values())
    kept = [d for d in current if not _owned(d, home, roots, catalog)]
    managed: List[str] = []
    for raw_id in selected:
        sid = str(raw_id).strip()
        entry = by_id.get(sid)
        if entry is None:
            result.unknown.append(sid)
            continue
        if not matches_platform(entry, platform):
            result.other_platform.append(sid)
            continue
        path = resolve(entry)
        if path is None:  # hub skills live in the home's own skills/ tree
            continue
        if not path.is_dir():
            result.unresolved.append(sid)
            continue
        if str(path) not in managed:
            managed.append(str(path))
    dirs = kept + [d for d in managed if d not in kept]
    result.external_dirs = dirs
    return dirs, result


# Profile config keys (under ``janitor:``). ``skills`` is the agent's selection,
# ``template`` the catalog template it was created from, ``catalog_seen`` every
# template id already offered to this profile (so a removed skill stays removed).
SKILLS_KEY = "skills"
TEMPLATE_KEY = "template"
SEEN_KEY = "catalog_seen"


def _id_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise CatalogError("janitor.skills / janitor.catalog_seen must be lists of catalog ids")
    out: List[str] = []
    for raw in value:
        sid = str(raw).strip()
        if sid and sid not in out:
            out.append(sid)
    return out


def evolve_selection(config: dict, template_skills: Sequence[str],
                     catalog_ids: Iterable[str]) -> Tuple[dict, SelectionChange]:
    """Bring a template-managed profile's ``janitor.skills`` up to the current catalog.

    Pure: returns a new config dict and what changed; ``config`` is not mutated.
    Only a config carrying both ``janitor.skills`` and ``janitor.template`` is
    managed (anything else comes back unchanged):

    * an id of the template (``template_skills``) never offered before — absent
      from ``janitor.catalog_seen`` — is appended to ``janitor.skills`` once;
    * every template id is then recorded in ``catalog_seen``, so a skill the user
      removed from ``janitor.skills`` is never re-added;
    * ids no longer in the catalog leave ``janitor.skills`` (reported as dropped)
      and ``catalog_seen``.

    A profile without ``catalog_seen`` (written before this rule existed) counts
    the current template as already offered: it is recorded, nothing is added.
    """
    new = copy.deepcopy(config)
    change = SelectionChange()
    janitor_cfg = new.get("janitor")
    if not isinstance(janitor_cfg, dict) or SKILLS_KEY not in janitor_cfg or not janitor_cfg.get(TEMPLATE_KEY):
        return new, change
    known = set(catalog_ids)
    offered = [str(s).strip() for s in template_skills if str(s).strip() in known]
    skills = _id_list(janitor_cfg.get(SKILLS_KEY))
    seen_raw = janitor_cfg.get(SEEN_KEY)
    seen = list(offered) if seen_raw is None else _id_list(seen_raw)

    change.dropped = [s for s in skills if s not in known]
    skills = [s for s in skills if s in known]
    seen = [s for s in seen if s in known]
    change.added = [s for s in offered if s not in seen and s not in skills]
    skills += change.added
    seen += [s for s in offered if s not in seen]

    janitor_cfg[SKILLS_KEY] = skills
    janitor_cfg[SEEN_KEY] = seen
    return new, change


def reconcile_config(config: dict, home: Path, *, catalog: Optional[Catalog] = None,
                     platform: Optional[str] = None) -> Tuple[dict, ApplyResult]:
    """The config ``apply()`` would write for ``home``: evolved selection + generated ``external_dirs``.

    No I/O besides checking that skill directories exist. A config with no
    ``janitor.skills`` comes back unchanged with ``result.managed == False``.
    """
    janitor_cfg = config.get("janitor")
    if not isinstance(janitor_cfg, dict) or SKILLS_KEY not in janitor_cfg:
        return config, ApplyResult()
    catalog = catalog or load_catalog()
    platform = platform or current_platform()
    new = copy.deepcopy(config)
    change = SelectionChange()
    template = janitor_cfg.get(TEMPLATE_KEY)
    if template:
        if template in catalog.templates:
            offered = skills_for_template(str(template), catalog=catalog, platform=platform)
            new, change = evolve_selection(new, offered, (e.id for e in catalog.entries))
        else:
            logger.warning("janitor.template: %r is not a catalog template; selection not evolved", template)
    selected = _id_list(new["janitor"].get(SKILLS_KEY))

    skills = new.get("skills")
    if not isinstance(skills, dict):
        skills = {}
    current = skills.get("external_dirs") or []
    if isinstance(current, str):
        current = [current]
    current = [str(d) for d in current]
    dirs, result = plan_external_dirs(selected, current, home, catalog, platform)
    result.added, result.dropped = change.added, change.dropped
    if dirs != current:
        skills["external_dirs"] = dirs
        new["skills"] = skills
    return new, result


def _log_result(result: ApplyResult, where: Path) -> None:
    for sid in result.unknown:
        logger.warning("%s: janitor.skills %r is not in the Janitor catalog; skipped", where, sid)
    for sid in result.unresolved:
        logger.warning("%s: janitor.skills %r is not present in this install; skipped", where, sid)
    for sid in result.dropped:
        logger.warning("%s: skill %r left the Janitor catalog; removed from janitor.skills", where, sid)
    for sid in result.added:
        logger.info("%s: new template skill %r added to janitor.skills", where, sid)


def dump_config(config: dict, header: str = "") -> str:
    body = yaml.safe_dump(config, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return (header + "\n" if header else "") + body


def apply(home: Path, *, catalog: Optional[Catalog] = None, platform: Optional[str] = None) -> ApplyResult:
    """Bring ``home/config.yaml`` up to the catalog: evolve ``janitor.skills``, regenerate ``external_dirs``.

    Idempotent; the file is rewritten only when something changed (a second run
    is a byte-for-byte no-op). A config with no ``janitor.skills`` key is left
    untouched. Unknown ids are reported in the result (and logged), never fatal.
    """
    home = Path(home).expanduser()
    path = home / "config.yaml"
    if not path.exists():
        return ApplyResult()
    from hermes_cli.config import require_readable_config_before_write

    # Raises on an unreadable / unparseable file instead of rewriting it.
    config = require_readable_config_before_write(path)
    new, result = reconcile_config(config, home, catalog=catalog, platform=platform)
    if not result.managed:
        return result
    _log_result(result, path)
    if new == config:
        return result
    header = _leading_comments(path.read_text(encoding="utf-8"))
    _atomic_write(path, dump_config(new, header))
    result.changed = True
    return result


def janitor_homes(home: Path) -> List[Path]:
    """The Janitor root owning ``home`` (itself or ``<root>/profiles/<name>``) and every profile under it."""
    home = Path(home).expanduser()
    root = home.parent.parent if home.parent.name == "profiles" else home
    profiles = root / "profiles"
    named = sorted(p for p in profiles.iterdir() if p.is_dir() and not p.name.startswith(".")) \
        if profiles.is_dir() else []
    return [root, *named]


def apply_quietly(home: Path) -> Optional[ApplyResult]:
    """:func:`apply` for callers that must never fail (launcher, update): a problem is logged."""
    try:
        return apply(home)
    except Exception as exc:  # noqa: BLE001 — a broken catalog/config must not stop the caller
        logger.warning("Janitor skill catalog not applied to %s: %s", home, exc)
        return None


# --- CLI ---------------------------------------------------------------------


def _cmd_list(catalog: Catalog) -> int:
    rows = [("id", "source", "purpose", "templates", "resolved")]
    for e in catalog.entries:
        problem = check_entry(e)
        rows.append((e.id, e.source, e.purpose, ",".join(e.templates) or "-",
                     "hub" if e.source == "hub" else ("yes" if problem is None else "NO")))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
    return 0


def _cmd_check(catalog: Catalog) -> int:
    failures = [(e.id, p) for e in catalog.entries if (p := check_entry(e))]
    for sid, problem in failures:
        print(f"FAIL {sid}: {problem}")
    print(f"{len(catalog.entries) - len(failures)}/{len(catalog.entries)} catalog entries resolve")
    return 1 if failures else 0


def _cmd_apply(home: Path) -> int:
    result = apply(home)
    if not result.managed:
        print(f"{home / 'config.yaml'}: no janitor.skills — left unchanged")
        return 0
    for label, ids in (("unknown", result.unknown), ("not in this install", result.unresolved),
                       ("other platform", result.other_platform), ("left the catalog", result.dropped)):
        if ids:
            print(f"skipped ({label}): {', '.join(ids)}")
    if result.added:
        print(f"added (new in template): {', '.join(result.added)}")
    print(f"skills.external_dirs: {len(result.external_dirs)} entries "
          f"({'updated' if result.changed else 'already current'})")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m janitor.catalog", description="Janitor skill catalog")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show every catalog entry")
    sub.add_parser("check", help="fail when an entry does not resolve to its SKILL.md")
    p_apply = sub.add_parser("apply", help="regenerate skills.external_dirs from janitor.skills")
    p_apply.add_argument("--home", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog()
    except CatalogError as exc:
        print(f"catalog error: {exc}", file=sys.stderr)
        return 2
    if args.command == "list":
        return _cmd_list(catalog)
    if args.command == "check":
        return _cmd_check(catalog)
    return _cmd_apply(args.home.expanduser())


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    sys.exit(main())
