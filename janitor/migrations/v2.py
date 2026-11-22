"""Layout v2: retire the parallel agent system and the obsolete Janitor skills.

Janitor 1.x shipped skills that no longer exist (``janitor-core``,
``janitor-config-audit``, the ``agents/`` group, ...) and renamed
``janitor-repo-research-agent`` to ``janitor-repo-research``. A pre-1.0 home
still holds synced copies of them in ``skills/`` (a local copy always wins over
an external dir), and any config may still name them.

v1 recognises Janitor skills by walking the LIVE ``janitor/skills`` tree, so it
stops seeing these names the moment their directories are deleted. v2 works
from the FROZEN tables below instead, which never change with the tree.

What this migration changes, and nothing else:

* ``skills/`` — removes copies of a legacy skill whose content matches the hash
  recorded in ``.bundled_manifest`` or a version Janitor shipped
  (``SHIPPED_DIGESTS``), and drops their manifest entries; removes symlinks
  named after a legacy skill that dangle or point into this install's
  ``janitor/skills``. Copies the user edited, hub-installed skills and any
  other link are kept and reported;
* ``config.yaml`` — in ``skills.disabled``, ``skills.platform_disabled.*`` and
  ``janitor.skills`` retired names are dropped and renamed ones rewritten; in
  ``skills.external_dirs`` entries naming a retired directory of the Janitor
  tree are dropped or repointed. No other key is touched, and nothing is
  added (a config without ``janitor.skills`` keeps whole-root
  ``external_dirs``).

Docker containers and volumes, ``.env``, shell RC lines and systemd units are
never touched. Everything changed is backed up first (see ``v1.make_backup``).
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

from janitor.home import SKILLS_EXTERNAL_DIRS, SKILLS_ROOT
from janitor.migrations import v1
from janitor.migrations.v1 import LocalSkill, Out

VERSION = 2

# Skills Janitor shipped and no longer ships. Frozen: never derive from the tree.
RETIRED: FrozenSet[str] = frozenset(
    {
        # Retired in layout v2 (F2-04): a Janitor agent is a Hermes profile.
        "janitor-code-review-agent",
        "janitor-config-audit",
        "janitor-core",
        "janitor-browser",
        "janitor-desktop-launcher",
        "janitor-skill-integration",
        # Retired before 1.0; v1 never knew them because they had already left the tree.
        "janitor-agentmemory",
        "janitor-playwright",
        "janitor-vault",
    }
)
RENAMED: Dict[str, str] = {"janitor-repo-research-agent": "janitor-repo-research"}
LEGACY_NAMES: FrozenSet[str] = RETIRED | frozenset(RENAMED)

# ``tools.skills_sync._dir_hash`` (= ``v1.dir_hash``) of every version of each
# legacy skill that ever existed in this repository's history, under any of its
# paths (``skills/<name>``, ``janitor/skills/<group>/<name>``). A copy matching
# one of these is something Janitor wrote, not the user.
SHIPPED_DIGESTS: Dict[str, FrozenSet[str]] = {
    "janitor-agentmemory": frozenset(
        {
            "1db59ea4d4562614bdea08402d251072",
        }
    ),
    "janitor-browser": frozenset(
        {
            "40db385ce90e7bf18a364eb45a737c22",
            "4ad673dfbc78d3b435a30b19cdf7b76f",
            "a5635cd8965f70a3bdad8a84460da1c6",
            "c95d38e3d898b0b46740a8065ab7a36a",
        }
    ),
    "janitor-code-review-agent": frozenset(
        {
            "3516847ffc63e492b6a8e9349d98520a",
            "fbef98e4d4612b57d665174d64b98798",
        }
    ),
    "janitor-config-audit": frozenset(
        {
            "563e129949669917be157e9e5a1f5028",
            "68bb2b5cd7859f753f94e675b0980825",
            "908098f41ba8a994c587467b0a0ae780",
            "982328f0c6739aa3fdb55efab03dacfa",
            "a70b589ec0f4db1223a64ebe338398f5",
            "ebcb5c3480b7441216167088d56c236f",
            "f83e423255116b86b7ffdc642c9b0d59",
        }
    ),
    "janitor-core": frozenset(
        {
            "07e7cf83391d31fa0ea13ff23da2cf01",
            "1dc592c18ae3dfbfbf22cd290571a05c",
            "45e4eabc02ba7a65be5c0ca40668827d",
            "9da9f31b1519ca1a4266af6fefe992b7",
        }
    ),
    "janitor-desktop-launcher": frozenset(
        {
            "1d496877bbfeb7ddcfc9f547bf41446d",
            "3636d68c1091181279b471dc80331a66",
            "56f7fccb6d52bba8a41174840fef1cd1",
            "962ca1220bbd365aef3fd71d0a28f2c3",
            "ca5ef32611b57a97cd8598fd9b1497fa",
            "d18b17237a3734aaca0635aafed7a32c",
            "dd4757c1db0b26593dbec187e1c2ec3d",
            "e241fc1636d74dc7069d487f892f72f7",
        }
    ),
    "janitor-playwright": frozenset(
        {
            "25dffdbfd75dda718dfc310cef83a9f1",
        }
    ),
    "janitor-repo-research-agent": frozenset(
        {
            "c30f3f19171a185464628c84e1d97e57",
            "e06a1ee676b9f60f16df905f9929e958",
        }
    ),
    "janitor-skill-integration": frozenset(
        {
            "4517600131264854a49fe4d8a16a080a",
            "455bef137678e304375ffd4845fa85de",
        }
    ),
    "janitor-vault": frozenset(
        {
            "3f808e309021ed1ccb608a8eae1437c2",
        }
    ),
}

# ``skills.external_dirs`` paths inside the Janitor tree that no longer exist,
# relative to ``${JANITOR_SKILLS_ROOT}`` / this install's ``janitor/skills``.
# ``None`` = drop the entry.
LEGACY_TREE_DIRS: Dict[str, Optional[str]] = {
    "agents": "research",
    "agents/janitor-repo-research-agent": "research/janitor-repo-research",
    "agents/janitor-code-review-agent": None,
    "core/janitor-config-audit": None,
    "core/janitor-core": None,
    "integrations/janitor-browser": None,
    "integrations/janitor-desktop-launcher": None,
    "integrations/janitor-skill-integration": None,
}


@dataclass
class Plan:
    home: Path
    config: Optional[dict] = None
    config_changes: List[str] = field(default_factory=list)
    remove: List[LocalSkill] = field(default_factory=list)
    keep: List[LocalSkill] = field(default_factory=list)
    drop_manifest: List[str] = field(default_factory=list)
    unlink: List[Path] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.config_changes or self.remove or self.drop_manifest or self.unlink)


# ── skills/ ────────────────────────────────────────────────────────────────


def _legacy_links(skills_dir: Path) -> List[Path]:
    """Symlinks named after a legacy skill anywhere under ``skills/`` (not followed)."""
    found: List[Path] = []
    if not skills_dir.is_dir():
        return found
    for root, dirs, files in os.walk(skills_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in [*dirs, *files]:
            path = Path(root) / name
            if name in LEGACY_NAMES and path.is_symlink():
                found.append(path)
    return sorted(found)


def _link_is_ours(link: Path) -> bool:
    if not link.exists():
        return True  # dangling: points at a directory that is gone
    try:
        target = link.resolve()
        return target == SKILLS_ROOT.resolve() or SKILLS_ROOT.resolve() in target.parents
    except OSError:
        return False


def _plan_skills(plan: Plan) -> None:
    skills_dir = plan.home / "skills"
    manifest = v1._read_manifest(skills_dir / ".bundled_manifest")
    hub = v1._hub_installed(skills_dir)
    local = v1._local_copies(skills_dir, set(LEGACY_NAMES))

    for link in _legacy_links(skills_dir):
        if link.name in hub:
            continue
        if _link_is_ours(link):
            plan.unlink.append(link)
        else:
            plan.keep.append(LocalSkill(link.name, link, "symlink to a directory outside Janitor"))

    links = _legacy_links(skills_dir)
    for name in sorted(LEGACY_NAMES):
        if name in hub:
            continue
        # A copy reached through a link is the link's target: handled above, never deleted.
        copies = [c for c in local.get(name, []) if not any(c == l or l in c.parents for l in links)]
        recorded = manifest.get(name)
        shipped = SHIPPED_DIGESTS.get(name, frozenset())
        for found in copies:
            digests = {v1.dir_hash(found), v1.dir_hash(found, include_runtime_cache=True)}
            if recorded in digests or digests & shipped:
                plan.remove.append(LocalSkill(name, found))
            else:
                reason = "edited locally" if recorded else "not tracked by the bundled manifest"
                plan.keep.append(LocalSkill(name, found, reason))
        if name in manifest and not any(k.name == name and not k.path.is_symlink() for k in plan.keep):
            plan.drop_manifest.append(name)


# ── config.yaml ────────────────────────────────────────────────────────────


def _clean_names(value) -> Tuple[object, bool]:
    """Drop retired / rename renamed names in a skill-name list. Returns (value, changed)."""
    if isinstance(value, str):
        from agent.skill_utils import parse_config_string_list

        names = parse_config_string_list(value)
    elif isinstance(value, list):
        names = value
    else:
        return value, False
    if not any(isinstance(n, str) and n.strip() in LEGACY_NAMES for n in names):
        return value, False
    cleaned: List = []
    for name in names:
        key = name.strip() if isinstance(name, str) else name
        if key in RETIRED:
            continue
        new = RENAMED.get(key, name) if isinstance(key, str) else name
        if new not in cleaned:
            cleaned.append(new)
    return cleaned, True


def _legacy_tree_entry(entry: str) -> Tuple[bool, Optional[str]]:
    """(is a retired Janitor-tree path, replacement entry or None)."""
    if not isinstance(entry, str):
        return False, None
    text = entry.rstrip("/")
    for prefix in SKILLS_EXTERNAL_DIRS:
        for old, new in LEGACY_TREE_DIRS.items():
            if text == f"{prefix}/{old}":
                return True, (f"{prefix}/{new}" if new else None)
    return False, None


def _plan_config(plan: Plan, base_config: Optional[dict]) -> None:
    path = plan.home / "config.yaml"
    if base_config is not None:
        config = copy.deepcopy(base_config)
    elif path.exists():
        from hermes_cli.config import require_readable_config_before_write

        config = require_readable_config_before_write(path)
    else:
        return

    skills = config.get("skills")
    if isinstance(skills, dict):
        value, changed = _clean_names(skills.get("disabled"))
        if changed:
            skills["disabled"] = value
            plan.config_changes.append("skills.disabled: retired/renamed Janitor skills updated")

        per_platform = skills.get("platform_disabled")
        if isinstance(per_platform, dict):
            for platform in list(per_platform):
                value, changed = _clean_names(per_platform[platform])
                if changed:
                    per_platform[platform] = value
                    plan.config_changes.append(
                        f"skills.platform_disabled.{platform}: retired/renamed Janitor skills updated"
                    )

        dirs = skills.get("external_dirs")
        if isinstance(dirs, list):
            new_dirs: List = []
            changed = False
            for entry in dirs:
                legacy, replacement = _legacy_tree_entry(entry)
                if legacy:
                    changed = True
                    entry = replacement
                if entry is not None and entry not in new_dirs:
                    new_dirs.append(entry)
            if changed:
                skills["external_dirs"] = new_dirs
                plan.config_changes.append("skills.external_dirs: retired Janitor skill directories updated")

    janitor = config.get("janitor")
    if isinstance(janitor, dict):
        value, changed = _clean_names(janitor.get("skills"))
        if changed:
            janitor["skills"] = value
            plan.config_changes.append("janitor.skills: retired/renamed Janitor skills updated")

    plan.config = config


def build_plan(home: Path, base_config: Optional[dict] = None) -> Plan:
    """``base_config``: the config as the previous migration leaves it, if it read one."""
    plan = Plan(home=home)
    _plan_config(plan, base_config)
    _plan_skills(plan)
    return plan


def apply(plan: Plan) -> None:
    home = plan.home
    if plan.config_changes and plan.config is not None:
        v1.write_config(home, plan.config)

    skills_dir = home / "skills"
    for link in plan.unlink:
        link.unlink()
    for skill in plan.remove:
        v1._remove_skill(skill.path, skills_dir)
    if plan.drop_manifest:
        manifest_path = skills_dir / ".bundled_manifest"
        entries = v1._read_manifest(manifest_path)
        for name in plan.drop_manifest:
            entries.pop(name, None)
        v1._write_manifest(manifest_path, entries)


def describe(plan: Plan, out: Out) -> None:
    for change in plan.config_changes:
        out(f"  config.yaml: {change}")
    for link in plan.unlink:
        out(f"  skills: remove link {link.relative_to(plan.home)} (retired Janitor skill)")
    for skill in plan.remove:
        new = RENAMED.get(skill.name)
        why = f"renamed to {new}, read from janitor/skills" if new else "retired Janitor skill"
        out(f"  skills: remove pristine copy {skill.path.relative_to(plan.home)} ({why})")
    for skill in plan.keep:
        out(
            f"  skills: KEEP {skill.path.relative_to(plan.home)} ({skill.reason}) — {skill.name} is no "
            f"longer shipped by Janitor; delete it yourself if you do not need it"
        )
