"""Layout v1: Janitor skills move out of ``~/.janitor/skills`` into the install tree.

Before 1.0 the bundled-skills sync copied every Janitor skill into
``$HERMES_HOME/skills``. From 1.0 they are read in place through
``skills.external_dirs`` and the Janitor plugin is enabled explicitly. A local
copy always wins over an external dir, so stale pristine copies would shadow
the shipped skills forever.

What this migration changes, and nothing else:

* ``config.yaml`` — adds the Janitor ``skills.external_dirs`` entries and
  ``plugins.enabled: [janitor]`` (unless the user disabled the plugin);
* ``skills/`` — removes Janitor skill copies whose content still matches the
  hash recorded in ``.bundled_manifest`` (or the shipped copy), and drops their
  manifest entries. Copies the user edited are kept and reported;
* ``skins/sentry-janitor.yaml`` — refreshed only when byte-identical to a
  version Janitor itself shipped.

Docker containers and volumes, ``.env``, shell RC lines and systemd units are
never touched. Everything changed is backed up first under
``.backup/v1-<timestamp>/`` together with a consistent copy of ``state.db``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import yaml

from janitor.home import ASSETS_ROOT, SKILLS_ROOT

VERSION = 1

EXTERNAL_DIRS: Tuple[str, ...] = ("${JANITOR_SKILLS_ROOT}", "janitor-core/janitor/skills")
PLUGIN_NAME = "janitor"
SKIN_FILE = "sentry-janitor.yaml"

# sha256 of every sentry-janitor.yaml the installer / launcher ever copied
# into ~/.janitor/skins before 1.0. Only these exact bytes are replaced.
SHIPPED_SKIN_SHA256 = frozenset(
    {
        "a856a19c14080fb0504296082582ab9ec5e0306edec947782cd4528a6a1c18f4",
        "6ca03795a5c5d642362e8e03288c3709ba46d2cd8c3f09e48f1d927a03861fc6",
    }
)

Out = Callable[[str], None]


@dataclass
class LocalSkill:
    name: str
    path: Path
    reason: str = ""


@dataclass
class Plan:
    home: Path
    config: Optional[dict] = None
    config_changes: List[str] = field(default_factory=list)
    remove: List[LocalSkill] = field(default_factory=list)
    keep: List[LocalSkill] = field(default_factory=list)
    drop_manifest: List[str] = field(default_factory=list)
    refresh_skin: bool = False

    @property
    def empty(self) -> bool:
        return not (self.config_changes or self.remove or self.drop_manifest or self.refresh_skin)


def dir_hash(directory: Path) -> str:
    """Same digest as ``tools.skills_sync._dir_hash`` (what the manifest stores)."""
    hasher = hashlib.md5()
    try:
        for fpath in sorted(directory.rglob("*")):
            if fpath.is_file():
                hasher.update(str(fpath.relative_to(directory)).encode("utf-8"))
                hasher.update(fpath.read_bytes())
    except OSError:
        pass
    return hasher.hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shipped_skills(root: Path = SKILLS_ROOT) -> Dict[str, Path]:
    return {skill_md.parent.name: skill_md.parent for skill_md in sorted(root.rglob("SKILL.md"))}


def _read_manifest(path: Path) -> Dict[str, str]:
    entries: Dict[str, str] = {}
    if not path.exists():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, digest = line.partition(":")
        entries[name.strip()] = digest.strip()
    return entries


def _write_manifest(path: Path, entries: Dict[str, str]) -> None:
    body = "".join(f"{name}:{digest}\n" for name, digest in sorted(entries.items()))
    _atomic_write(path, body)


def _hub_installed(skills_dir: Path) -> set:
    try:
        data = json.loads((skills_dir / ".hub" / "lock.json").read_text(encoding="utf-8"))
        return set((data.get("installed") or {}).keys())
    except (OSError, ValueError, AttributeError):
        return set()


def _local_copies(skills_dir: Path, names: set) -> Dict[str, List[Path]]:
    found: Dict[str, List[Path]] = {}
    if not skills_dir.is_dir():
        return found
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        rel_parts = skill_md.parent.relative_to(skills_dir).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        name = skill_md.parent.name
        if name in names:
            found.setdefault(name, []).append(skill_md.parent)
    return found


def _plan_config(plan: Plan) -> None:
    path = plan.home / "config.yaml"
    if not path.exists():
        return
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        return

    skills = config.get("skills")
    if not isinstance(skills, dict):
        skills = {}
    dirs = skills.get("external_dirs") or []
    if isinstance(dirs, str):
        dirs = [dirs]
    missing = [d for d in EXTERNAL_DIRS if d not in dirs]
    if missing:
        skills["external_dirs"] = list(dirs) + missing
        config["skills"] = skills
        plan.config_changes.append(f"skills.external_dirs += {missing}")

    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        plugins = {}
    enabled = plugins.get("enabled") or []
    disabled = plugins.get("disabled") or []
    if PLUGIN_NAME not in enabled and PLUGIN_NAME not in disabled:
        plugins["enabled"] = list(enabled) + [PLUGIN_NAME]
        config["plugins"] = plugins
        plan.config_changes.append(f"plugins.enabled += [{PLUGIN_NAME}]")

    plan.config = config


def _plan_skills(plan: Plan, shipped: Dict[str, Path]) -> None:
    skills_dir = plan.home / "skills"
    manifest = _read_manifest(skills_dir / ".bundled_manifest")
    hub = _hub_installed(skills_dir)
    local = _local_copies(skills_dir, set(shipped))

    for name in sorted(shipped):
        if name in hub:
            continue
        copies = local.get(name, [])
        if not copies:
            if name in manifest:
                plan.drop_manifest.append(name)
            continue
        shipped_hash = dir_hash(shipped[name])
        recorded = manifest.get(name)
        for copy in copies:
            digest = dir_hash(copy)
            if digest == recorded or digest == shipped_hash:
                plan.remove.append(LocalSkill(name, copy))
            else:
                reason = "edited locally" if recorded else "not tracked by the bundled manifest"
                plan.keep.append(LocalSkill(name, copy, reason))
        if name in manifest and not any(k.name == name for k in plan.keep):
            plan.drop_manifest.append(name)


def _plan_skin(plan: Plan) -> None:
    skin = plan.home / "skins" / SKIN_FILE
    current = ASSETS_ROOT / SKIN_FILE
    if not skin.is_file() or not current.is_file():
        return
    digest = _sha256(skin)
    plan.refresh_skin = digest in SHIPPED_SKIN_SHA256 and digest != _sha256(current)


def build_plan(home: Path, shipped_root: Path = SKILLS_ROOT) -> Plan:
    plan = Plan(home=home)
    _plan_config(plan)
    _plan_skills(plan, shipped_skills(shipped_root))
    _plan_skin(plan)
    return plan


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        if path.exists():
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _backup_dir(home: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    root = home / ".backup"
    candidate = root / f"v{VERSION}-{stamp}"
    n = 1
    while candidate.exists():
        candidate = root / f"v{VERSION}-{stamp}-{n}"
        n += 1
    candidate.mkdir(parents=True)
    try:
        os.chmod(root, 0o700)
        os.chmod(candidate, 0o700)
    except OSError:
        pass
    return candidate


def backup_sqlite(src: Path, dest: Path) -> None:
    """Consistent copy of a live SQLite DB (WAL included) via the backup API."""
    source = sqlite3.connect(str(src))
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def make_backup(plan: Plan) -> Path:
    home = plan.home
    dest = _backup_dir(home)
    for rel in ("config.yaml", "SOUL.md", "honcho.json", f"skins/{SKIN_FILE}"):
        src = home / rel
        if src.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)
    skills_dir = home / "skills"
    if skills_dir.is_dir():
        shutil.copytree(skills_dir, dest / "skills", symlinks=True)
    if (home / "state.db").is_file():
        backup_sqlite(home / "state.db", dest / "state.db")
    return dest


def _remove_skill(copy: Path, skills_dir: Path) -> None:
    shutil.rmtree(copy, ignore_errors=True)
    parent = copy.parent
    while parent != skills_dir and skills_dir in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def apply(plan: Plan) -> None:
    home = plan.home
    if plan.config_changes and plan.config is not None:
        _atomic_write(
            home / "config.yaml",
            yaml.safe_dump(plan.config, sort_keys=False, allow_unicode=True, default_flow_style=False),
        )

    skills_dir = home / "skills"
    for skill in plan.remove:
        _remove_skill(skill.path, skills_dir)
    if plan.drop_manifest:
        manifest_path = skills_dir / ".bundled_manifest"
        entries = _read_manifest(manifest_path)
        for name in plan.drop_manifest:
            entries.pop(name, None)
        _write_manifest(manifest_path, entries)

    if plan.refresh_skin:
        shutil.copy2(ASSETS_ROOT / SKIN_FILE, home / "skins" / SKIN_FILE)


def describe(plan: Plan, out: Out) -> None:
    for change in plan.config_changes:
        out(f"  config.yaml: {change}")
    for skill in plan.remove:
        out(f"  skills: remove pristine copy {skill.path.relative_to(plan.home)} (now read from janitor/skills)")
    for skill in plan.keep:
        out(
            f"  skills: KEEP {skill.path.relative_to(plan.home)} ({skill.reason}) — it shadows the "
            f"shipped {skill.name}; delete it to use the new version"
        )
    if plan.refresh_skin:
        out(f"  skins/{SKIN_FILE}: refresh unmodified shipped skin to the 1.0 version")
