"""Seed a Janitor home: minimal ``config.yaml``, ``SOUL.md``, skin, no upstream skills.

Called by the ``janitor`` launcher before Hermes is imported and by the config
stage of ``scripts/install.sh`` (the path the desktop app takes), so a fresh
machine ends up with a working Janitor home whichever entry point ran first.

Idempotent, and it never overwrites what the user wrote:

* ``config.yaml`` is written only when missing or byte-equal to upstream's
  ``cli-config.yaml.example`` (what ``install.sh`` copies in before this runs)
  or to the raw ``assets/janitor/config.yaml`` (what ``janitor-install.sh``
  copies). Any other file — including a pre-1.0 Janitor config — is the user's.
* ``SOUL.md`` is written when missing or still an upstream auto-seeded default
  (``DEFAULT_SOUL_MD`` or one of the legacy templates upstream itself treats
  as carrying zero user intent).
* ``skins/sentry-janitor.yaml`` is copied only when missing.
* ``.no-bundled-skills`` and the layout stamp are written only for a home this
  module just seeded, never for an existing one.
* ``.env`` is never touched.

This module imports no ``hermes_cli.config``: that import seeds upstream's
default ``SOUL.md`` into whatever ``HERMES_HOME`` points at.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import yaml

from janitor.home import (
    ASSETS_ROOT,
    LAYOUT_VERSION,
    REPO_ROOT,
    SKILLS_EXTERNAL_DIRS,
    janitor_home,
    read_layout_version,
    write_layout_version,
)

# Same name as tools.skills_sync.NO_BUNDLED_SKILLS_MARKER (not imported: this
# module runs before Hermes is imported and must not touch its import chain).
NO_BUNDLED_SKILLS_MARKER = ".no-bundled-skills"
CONFIG_FILE = "config.yaml"
SOUL_FILE = "SOUL.md"
SKIN_FILE = "sentry-janitor.yaml"
UPSTREAM_CONFIG_EXAMPLE = REPO_ROOT / "cli-config.yaml.example"
COMMAND_NAME = "janitor"

_CONFIG_HEADER = (
    "# Janitor config. Only Janitor's changes on top of the Hermes defaults are\n"
    "# listed; every other setting uses the upstream default.\n"
)


def _atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".seed", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def seed_config() -> dict:
    """The config a new Janitor home starts with."""
    from hermes_cli.config_defaults import DEFAULT_CONFIG  # the object hermes_cli.config re-exports

    config = yaml.safe_load((ASSETS_ROOT / CONFIG_FILE).read_text(encoding="utf-8"))
    skills = config.setdefault("skills", {})
    dirs = list(skills.get("external_dirs") or [])
    skills["external_dirs"] = dirs + [d for d in SKILLS_EXTERNAL_DIRS if d not in dirs]
    # Stamped at seed time so the first load does not replay every config
    # migration from version 0 over a config that is already current.
    config["_config_version"] = DEFAULT_CONFIG["_config_version"]
    return config


def _config_is_replaceable(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return True
    try:
        data = path.read_bytes()
        # Upstream's template (install.sh's config stage) or Janitor's own raw
        # asset (copied verbatim by scripts/janitor-install.sh): neither carries
        # user intent, and both lack the seed-time additions.
        templates = (UPSTREAM_CONFIG_EXAMPLE, ASSETS_ROOT / CONFIG_FILE)
        return any(t.is_file() and data == t.read_bytes() for t in templates)
    except OSError:
        return False


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip()


def _soul_is_replaceable(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return True
    from hermes_cli.default_soul import DEFAULT_SOUL_MD, is_legacy_template_soul

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return _normalize(text) == _normalize(DEFAULT_SOUL_MD) or is_legacy_template_soul(text)


def _needs_layout_migration(home: Path) -> bool:
    """True when ``home`` still holds old Janitor skill copies or skin."""
    from janitor.migrations import v1, v2

    plan = v1.Plan(home=home)
    v1._plan_skills(plan, v1.shipped_skills())
    v1._plan_skin(plan)
    legacy = v2.Plan(home=home)
    v2._plan_skills(legacy)
    return not (plan.empty and legacy.empty)


def ensure_home(home: Optional[Path] = None) -> List[str]:
    """Seed ``home`` (default ``~/.janitor``). Returns what changed (empty = no-op)."""
    home = Path(home or janitor_home()).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    changes: List[str] = []

    config_path = home / CONFIG_FILE
    fresh = _config_is_replaceable(config_path)
    if fresh:
        body = _CONFIG_HEADER + yaml.safe_dump(
            seed_config(), sort_keys=False, allow_unicode=True, default_flow_style=False
        )
        _atomic_write(config_path, body.encode("utf-8"))
        changes.append(CONFIG_FILE)

    soul_path = home / SOUL_FILE
    if _soul_is_replaceable(soul_path):
        if soul_path.is_symlink():
            soul_path.unlink()
        _atomic_write(soul_path, (ASSETS_ROOT / SOUL_FILE).read_bytes())
        changes.append(SOUL_FILE)

    skin_path = home / "skins" / SKIN_FILE
    if not skin_path.exists():
        skin_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(skin_path, (ASSETS_ROOT / SKIN_FILE).read_bytes(), mode=0o644)
        changes.append(f"skins/{SKIN_FILE}")

    if fresh:
        marker = home / NO_BUNDLED_SKILLS_MARKER
        if not marker.exists():
            marker.write_text(
                "Janitor homes start without Hermes' bundled skills (essential skills only).\n"
                "Delete this file to re-enable bundled-skill sync on the next update.\n",
                encoding="utf-8",
            )
            changes.append(marker.name)
        if read_layout_version(home) < LAYOUT_VERSION and not _needs_layout_migration(home):
            write_layout_version(LAYOUT_VERSION, home)
            changes.append(f".layout_version={LAYOUT_VERSION}")

    return changes


def ensure_command_link(link_dir: Path, target: Optional[Path] = None) -> str:
    """Put ``janitor`` in ``link_dir`` as a symlink to this venv's console script.

    Returns ``created``, ``updated``, ``unchanged`` or ``kept: <reason>``.
    A ``janitor`` this installer did not create is left alone, except a link
    into a pre-1.0 ``janitor-core`` venv or a dangling link, which are replaced
    (the new target exists, so the command keeps working).
    """
    target = Path(target or Path(sys.prefix) / "bin" / COMMAND_NAME)
    if not target.is_file():
        return f"kept: {target} does not exist"
    link_dir.mkdir(parents=True, exist_ok=True)
    link = link_dir / COMMAND_NAME

    if link.is_symlink():
        current = Path(os.readlink(link))
        if not current.is_absolute():
            current = link_dir / current
        if current == target or (current.exists() and current.resolve() == target.resolve()):
            return "unchanged"
        if current.exists() and "janitor-core" not in current.parts:
            return f"kept: {link} points to {current}"
        link.unlink()
        link.symlink_to(target)
        return "updated"
    if link.exists():
        return f"kept: {link} is not a link created by the Janitor installer"
    link.symlink_to(target)
    return "created"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m janitor.seed", description=__doc__.split("\n", 1)[0])
    parser.add_argument("--home", type=Path, default=None, help="Janitor home (default: ~/.janitor)")
    parser.add_argument(
        "--link-command",
        type=Path,
        default=None,
        metavar="DIR",
        help="only create DIR/janitor pointing at this venv's janitor script",
    )
    args = parser.parse_args(argv)

    if args.link_command is not None:
        result = ensure_command_link(args.link_command.expanduser())
        print(f"janitor command ({args.link_command}/{COMMAND_NAME}): {result}")
        return 0

    home = (args.home or janitor_home()).expanduser()
    changes = ensure_home(home)
    if changes:
        print(f"Janitor home {home} seeded: {', '.join(changes)}")
    else:
        print(f"Janitor home {home} already seeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
