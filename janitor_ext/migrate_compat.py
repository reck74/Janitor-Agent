"""Compatibility entry for the historical v0.20.1 migration command.

Keep its home/backup/exit-code contracts while delegating application migration
and memory admission to the current supported Janitor migrator.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import re
import shlex


def _backup(config: Path, raw: bytes) -> Path:
    stamp = datetime.now(UTC)
    while True:
        target = config.with_name(config.name + ".bak." + stamp.strftime("%Y%m%dT%H%M%SZ"))
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileExistsError:
            # Preserve the portable name without overwriting a failed prior run.
            stamp += timedelta(seconds=1)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    from janitor_ext.startup import janitor_home
    home = janitor_home().resolve()
    os.environ["JANITOR_HOME"] = os.environ["HERMES_HOME"] = str(home)
    config_path = home / "config.yaml"
    if not config_path.is_file():
        print(f"No config at {config_path} — nothing to migrate")
        return 1
    import hermes_cli
    import hermes_yaml as yaml
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    from hermes_cli.config_migrations import SUPPORT_FLOOR_VERSION, support_floor_message
    from janitor_version import display_version
    from janitor_ext.migrate import migrate

    raw = config_path.read_bytes()
    match = re.search(rb"^_config_version:\s*(\d+)\s*(?:#.*)?$", raw, re.MULTILINE)
    current = int(match[1]) if match else None
    latest = DEFAULT_CONFIG["_config_version"]
    print(f"Raw version: {hermes_cli.__version__}")
    print(f"Display version: {display_version(hermes_cli.__version__)}")
    if args.dry_run:
        print(f"Dry run: would migrate {config_path}; current v{current}, target v{latest}")
        return 0
    if current is not None and current >= latest:
        print(f"Config already at v{current}; latest v{latest} — nothing to migrate.")
        return 0
    backup = _backup(config_path, raw)
    print(f"Backed up: {backup}")
    rollback = f"To rollback: cp {shlex.quote(str(backup))} {shlex.quote(str(config_path))}"
    try:
        parsed = yaml.safe_load(raw)
        if not isinstance(parsed, dict):
            raise ValueError("config.yaml must contain a mapping")
    except (yaml.YAMLError, ValueError, TypeError) as exc:
        print(f"Migration aborted: config could not be parsed ({exc}).")
        print(f"Your live config is byte-identical to: {backup}")
        print(rollback)
        return 3
    try:
        try:
            report = migrate(home, apply=True)
        finally:
            # Upstream organizes legacy config.yaml.bak.* files on load.
            # Keep this compatibility command's promised recovery alias valid.
            if not backup.exists():
                try:
                    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(raw)
                except FileExistsError:
                    pass
        after = yaml.safe_load(config_path.read_text())
        final_version = after.get("_config_version")
        if current is not None and current < SUPPORT_FLOOR_VERSION and config_path.read_bytes() == raw:
            print(f"Config remains at v{current}; latest v{latest}. {support_floor_message()}")
        elif not isinstance(final_version, int) or final_version != latest:
            raise RuntimeError(f"Post-check current v{final_version}, latest v{latest}; migration did not reach the supported schema")
        else:
            print(f"Migration complete: v{latest}; state backup: {report['backup']}")
    except Exception as exc:
        print(f"Migration failed: {exc}. Live config may be partially modified; {backup} is the pre-migration snapshot.")
        print(rollback)
        return 3
    print(rollback)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
