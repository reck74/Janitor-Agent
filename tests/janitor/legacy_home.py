"""Builder for a realistic pre-1.0 Janitor home (``~/.janitor``).

The layout mirrors what ``scripts/bootstrap.sh`` + ``scripts/janitor-install.sh``
+ the first ``janitor`` launch leave on disk for a v0.20.1 user:

* seed files copied from ``assets/janitor/`` (config, SOUL, honcho, skin);
* Janitor skills synced into ``skills/`` by the bundled-skills sync, at their
  legacy paths (flat ``skills/janitor-*`` and nested ``skills/devops/janitor-*``)
  with a v2 ``.bundled_manifest`` (``name:hash``);
* one user-modified Janitor skill and one skill the user wrote themselves;
* a real ``state.db`` written through ``SessionDB``;
* memories, cron jobs and an opt-in Docker compose file.

Tests snapshot the "user data" part of this tree before and after running
the real launcher / migration and assert nothing was lost.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSETS = REPO_ROOT / "assets" / "janitor"

# Legacy (pre-1.0) on-disk location of each Janitor skill inside
# ``$HERMES_HOME/skills`` — this is where skills_sync placed them while they
# lived in the upstream ``skills/`` tree.
LEGACY_SKILL_PATHS: Dict[str, str] = {
    "janitor-core": "janitor-core",
    "janitor-firecrawl": "janitor-firecrawl",
    "janitor-honcho": "janitor-honcho",
    "janitor-onboarding": "janitor-onboarding",
    "janitor-n8n": "devops/janitor-n8n",
}

USER_MODIFIED_SKILL = "janitor-core"
USER_OWN_SKILL = "my-own-skill"

SESSION_ID = "legacy-session-0001"


@dataclass
class LegacyHome:
    root: Path
    home: Path
    user_data: Dict[str, str] = field(default_factory=dict)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_skill_source(name: str) -> Path:
    """Locate the current in-repo source directory of a Janitor skill."""
    for root in (REPO_ROOT / "janitor" / "skills", REPO_ROOT / "skills", REPO_ROOT / "optional-skills"):
        if not root.is_dir():
            continue
        for skill_md in root.rglob("SKILL.md"):
            if skill_md.parent.name == name:
                return skill_md.parent
    raise FileNotFoundError(f"Janitor skill source not found: {name}")


def _seed_skills(home: Path) -> None:
    from tools.skills_sync import _dir_hash

    skills_dir = home / "skills"
    manifest_lines = []
    for name, rel in LEGACY_SKILL_PATHS.items():
        dest = skills_dir / rel
        shutil.copytree(find_skill_source(name), dest)
        manifest_lines.append(f"{name}:{_dir_hash(dest)}")

    modified = skills_dir / LEGACY_SKILL_PATHS[USER_MODIFIED_SKILL] / "SKILL.md"
    modified.write_text(
        modified.read_text(encoding="utf-8") + "\n<!-- local tweak by the user -->\n",
        encoding="utf-8",
    )

    own = skills_dir / USER_OWN_SKILL
    own.mkdir(parents=True)
    (own / "SKILL.md").write_text(
        "---\nname: my-own-skill\ndescription: A skill the user wrote.\n---\n\n# Mine\n",
        encoding="utf-8",
    )
    (skills_dir / ".bundled_manifest").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")


def _seed_state_db(home: Path) -> None:
    from hermes_state import SessionDB

    db = SessionDB(db_path=home / "state.db")
    try:
        db.create_session(SESSION_ID, source="telegram")
        db.append_message(SESSION_ID, role="user", content="limpia mi repo")
        db.append_message(SESSION_ID, role="assistant", content="DENEGADO. Muestra el diff.")
    finally:
        close = getattr(db, "close", None)
        if callable(close):
            close()


def build_legacy_home(root: Path) -> LegacyHome:
    """Create ``<root>/.janitor`` the way a v0.20.1 install leaves it."""
    home = root / ".janitor"
    for sub in ("sessions", "skills", "skins", "logs", "tmp", "memories", "cron", "docker"):
        (home / sub).mkdir(parents=True, exist_ok=True)

    (home / ".env").write_text(
        "MINIMAX_API_KEY=sk-legacy-test\n"
        "HONCHO_BASE_URL=http://127.0.0.1:1973\n"
        f"HERMES_HOME={home}\n"
        "HERMES_SKIN=sentry-janitor\n",
        encoding="utf-8",
    )
    shutil.copy2(ASSETS / "config.yaml", home / "config.yaml")
    shutil.copy2(ASSETS / "SOUL.md", home / "SOUL.md")
    shutil.copy2(ASSETS / "honcho.json", home / "honcho.json")
    shutil.copy2(ASSETS / "sentry-janitor.yaml", home / "skins" / "sentry-janitor.yaml")
    (home / "memories" / "MEMORY.md").write_text("- El usuario usa MiniMax.\n", encoding="utf-8")
    (home / "cron" / "jobs.json").write_text('{"jobs": []}\n', encoding="utf-8")
    (home / "docker" / "honcho-compose.yml").write_text("services: {}\n", encoding="utf-8")

    previous = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(home)
    try:
        _seed_skills(home)
        _seed_state_db(home)
    finally:
        if previous is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = previous

    legacy = LegacyHome(root=root, home=home)
    legacy.user_data = snapshot_user_data(home)
    return legacy


# Files the user owns outright. Their bytes must survive any upgrade.
_USER_DATA_FILES: Iterable[str] = (
    ".env",
    "SOUL.md",
    "honcho.json",
    "skins/sentry-janitor.yaml",
    "memories/MEMORY.md",
    "cron/jobs.json",
    "docker/honcho-compose.yml",
)


def snapshot_user_data(home: Path) -> Dict[str, str]:
    """Hash every user-owned file plus every user-authored skill file."""
    snap: Dict[str, str] = {}
    for rel in _USER_DATA_FILES:
        path = home / rel
        if path.exists():
            snap[rel] = _sha256(path)
    for skill in (USER_OWN_SKILL, LEGACY_SKILL_PATHS[USER_MODIFIED_SKILL]):
        skill_dir = home / "skills" / skill
        if not skill_dir.is_dir():
            continue
        for f in sorted(skill_dir.rglob("*")):
            if f.is_file():
                snap[f.relative_to(home).as_posix()] = _sha256(f)
    return snap


def session_messages(home: Path) -> list[tuple[str, str]]:
    """Read the legacy session's messages straight from SQLite."""
    with sqlite3.connect(home / "state.db") as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
            (SESSION_ID,),
        ).fetchall()
    return [(r[0], r[1]) for r in rows]


def launcher_env(root: Path) -> Dict[str, str]:
    """Environment for running the real ``janitor`` launcher against ``root``."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERMES_")}
    env.update(
        {
            "HOME": str(root),
            "USERPROFILE": str(root),
            "HERMES_QUIET": "1",
            "PYTHONPATH": str(REPO_ROOT),
        }
    )
    return env
