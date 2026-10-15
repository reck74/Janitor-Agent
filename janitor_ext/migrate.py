"""Back up Janitor state before applying upstream's supported migrations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PROFILE_FILES = (
    ".env", "config.yaml", "SOUL.md", "honcho.json", "honcho.env", "honcho.toml",
    "auth.json", "active_profile", "vault.key", "vault.json.enc",
    "gateway_state.json", "channel_directory.json", "channel_aliases.json",
    "feishu_comment_pairing.json", "cron/jobs.json", "cron/executions.db",
    "gateway/discord_message_recovery.db",
)
STATE_DIRECTORIES = ("skins", "sessions", "memory", "memories", "auth", "secrets", "pairing", "platforms/pairing", "kanban/boards", "docker")
EXCLUDED_DIRECTORIES = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".cache", "cache",
    "backups", "checkpoints", "janitor-core", "hermes-agent", "site-packages",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox", "logs", "tmp",
})
SKILL_NAMES = ("janitor-lightrag", "janitor-n8n", "janitor-nocodb", "janitor-waha", "janitor-skill-integration")


def profiles(home: Path) -> list[Path]:
    children = home / "profiles"
    return [home, *sorted(p for p in children.iterdir() if p.is_dir() and not p.is_symlink())] if children.is_dir() and not children.is_symlink() else [home]


def state_files(home: Path, *, include_profiles: bool = True) -> list[Path]:
    """Curated durable state only; never traverse a link into another tree."""
    def safe_path(path: Path) -> bool:
        return all(not part.is_symlink() for part in (path, *path.parents) if part != home.parent)

    found = set()
    for profile in profiles(home) if include_profiles else [home]:
        found.update(p for name in PROFILE_FILES if (p := profile / name).is_file() and safe_path(p))
        found.update(p for p in profile.glob("*.db") if p.is_file() and safe_path(p))
        for directory in STATE_DIRECTORIES:
            folder = profile / directory
            if not folder.is_dir() or not safe_path(folder):
                continue
            for current, directories, files in os.walk(folder, followlinks=False):
                directories[:] = [name for name in directories
                                  if name not in EXCLUDED_DIRECTORIES and not (Path(current) / name).is_symlink()]
                found.update(path for name in files if (path := Path(current) / name).is_file()
                             and not path.is_symlink())
    return sorted(p for p in found if p.suffix not in (".wal", ".shm")
                  and not p.name.endswith(("-wal", "-shm", "-journal")))


def snapshot(home: Path, *, include_profiles: bool = True) -> Path:
    """SQLite's backup API captures committed WAL data without copying live journals."""
    home = home.resolve()
    destination = home / "backups" / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    destination.mkdir(parents=True, mode=0o700)
    manifest = []
    for source in state_files(home, include_profiles=include_profiles):
        relative = source.relative_to(home)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if source.suffix in (".db", ".sqlite", ".sqlite3"):
            with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=10) as original:
                with sqlite3.connect(target) as saved:
                    original.backup(saved)
                    if saved.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise RuntimeError(f"Invalid SQLite backup: {relative}")
        else:
            shutil.copy2(source, target)
        target.chmod(0o600)
        manifest.append({"path": str(relative), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    (destination / "manifest.json").write_text(json.dumps({"schema": 1, "files": manifest}, indent=2) + "\n")
    (destination / "manifest.json").chmod(0o600)
    return destination


def record_backup_artifact(backup: Path, artifact: Path, *, kind: str) -> None:
    """Append a completed external backup (such as pg_dump) to the verified inventory."""
    artifact = artifact.resolve(strict=True)
    relative = artifact.relative_to(backup.resolve(strict=True))
    artifact.chmod(0o600)
    path = backup / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"] = [entry for entry in manifest["files"] if entry["path"] != str(relative)]
    manifest["files"].append({"path": str(relative), "kind": kind,
                              "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()})
    from janitor_ext.install import private_write
    private_write(path, json.dumps(manifest, indent=2) + "\n")


def restore_snapshot(backup: Path, destination: Path) -> dict:
    """Verify every checksum before restoring to an empty directory; never touch live volumes.

    External database dumps are verified but require their service-specific restore
    (pg_restore for Honcho). Return their paths so recovery cannot silently omit them.
    """
    backup = backup.expanduser().resolve(strict=True)
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Restore destination must not exist; review the restored files before replacing live state")
    if any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("Restore destination must not traverse symlinks")
    manifest = json.loads((backup / "manifest.json").read_text())
    entries = manifest["files"]
    seen = set()
    for entry in entries:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or str(relative) in seen:
            raise ValueError("Unsafe or duplicate backup manifest path")
        seen.add(str(relative))
        source = backup / relative
        if source.is_symlink() or not source.resolve(strict=True).is_relative_to(backup):
            raise ValueError("Unsafe backup artifact path")
        if hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Backup checksum mismatch: {relative}")
    destination.mkdir(parents=True, mode=0o700)
    external = []
    for entry in entries:
        if entry.get("kind", "profile") != "profile":
            external.append(entry["path"])
            continue
        target = destination / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(backup / entry["path"], target)
        target.chmod(0o600)
    return {"home": str(destination), "backup": str(backup), "externalArtifacts": external}


def relocate_skills(home: Path, backup: Path, *, include_profiles: bool = True) -> list[str]:
    moved = []
    for profile in profiles(home) if include_profiles else [home]:
        for name in SKILL_NAMES:
            source = profile / "skills" / "devops" / name
            target = profile / "skills" / name
            if not source.is_dir() or source.is_symlink():
                continue
            if target.exists():
                target = backup / "displaced-skills" / profile.relative_to(home) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moved.append(str(target.relative_to(home)))
    return moved


def migrate_profile() -> None:
    """One fresh process/profile: supported config migrations plus pinned memory admission."""
    from hermes_cli.config import migrate_config, load_config
    migrate_config(interactive=False, quiet=True)
    if (load_config().get("memory") or {}).get("provider") == "honcho":
        from janitor_ext.install import install_honcho_plugin
        install_honcho_plugin()


def prepare_source_update(root: Path) -> None:
    """Fresh PM completion hook, before upstream's best-effort catalog migration."""
    import subprocess
    import sys
    from pm.plugins_state import dependency_homes
    from hermes_cli.memory_provider_migration import configured_provider
    for home in dependency_homes():
        if configured_provider(home) != "honcho":
            continue
        env = dict(os.environ, HERMES_HOME=str(home), JANITOR_HOME=str(home))
        subprocess.run([sys.executable, "-c", "from janitor_ext.install import install_honcho_plugin; install_honcho_plugin()"],
                       cwd=root, env=env, check=True, timeout=1800)


def migrate(home: Path, *, apply: bool = False, all_profiles: bool = False) -> dict:
    home = home.expanduser().resolve()
    selected = profiles(home) if all_profiles else [home]
    report = {"home": str(home), "profiles": [str(p) for p in selected], "apply": apply}
    if not apply:
        report["files"] = [str(p.relative_to(home)) for p in state_files(home, include_profiles=all_profiles)]
        return report
    backup = snapshot(home, include_profiles=all_profiles)
    report["backup"] = str(backup)
    report["relocatedSkills"] = relocate_skills(home, backup, include_profiles=all_profiles)
    # A separate process per profile prevents cached paths and ContextVars from crossing profiles.
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    for profile in selected:
        if not (profile / "config.yaml").is_file():
            continue
        env = dict(os.environ, HERMES_HOME=str(profile), JANITOR_HOME=str(profile))
        code = "from janitor_ext.migrate import migrate_profile; migrate_profile()"
        subprocess.run([sys.executable, "-c", code], cwd=root, env=env, check=True, timeout=1800)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    from janitor_ext.startup import janitor_home
    parser.add_argument("--home", type=Path, default=janitor_home())
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--all-profiles", action="store_true", help="Migrate the selected root and all its profiles")
    parser.add_argument("--restore", type=Path, metavar="BACKUP", help="Verify and restore a snapshot into a new --home directory")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")
    if args.restore:
        if args.apply or args.dry_run or args.all_profiles:
            parser.error("--restore cannot be combined with migration options")
        report = restore_snapshot(args.restore, args.home)
    else:
        if args.all_profiles:
            from hermes_constants import get_default_hermes_root
            args.home = get_default_hermes_root(home=args.home)
        report = migrate(args.home, apply=args.apply, all_profiles=args.all_profiles)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
