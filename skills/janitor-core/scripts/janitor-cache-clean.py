#!/usr/bin/env python3
"""
janitor-cache-clean — removes stale caches and temp files from the Janitor/Hermes environment.

Usage:
    python scripts/janitor-cache-clean.py [--dry-run] [--days N] [--force]

Security notes:
    - Only operates within ~/.hermes/ cache directories
    - Never deletes outside the hermes home tree
    - All actions logged to stderr for auditability
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from hermes_constants import get_hermes_home
except ImportError:
    def get_hermes_home() -> Path:
        return Path.home() / ".hermes"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean stale caches from the Janitor/Hermes environment",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Delete cache entries older than N days (default: 7)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow deletion of tool artifact caches (checkpoints, compressed states)",
    )
    return parser.parse_args()


def get_cache_dirs(hermes_home: Path) -> list[Path]:
    cache_dirs = []
    for sub in ("sessions", "memory", "tools", "checkpoints"):
        d = hermes_home / sub
        if d.exists():
            cache_dirs.append(d)
    temp = hermes_home / "tmp"
    if temp.exists():
        cache_dirs.append(temp)
    return cache_dirs


def find_stale_caches(cache_dirs: list[Path], days: int, force: bool) -> list[tuple[Path, str]]:
    cutoff = time.time() - (days * 86400)
    to_delete = []

    for cache_dir in cache_dirs:
        for entry in cache_dir.rglob("*"):
            if not entry.is_file():
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue

            is_tool_artifact = (
                entry.name.endswith((".ckpt", ".gz", ".bz2", ".pickle", ".state"))
                or entry.name.startswith(("model_", "checkpoint_"))
            )

            if is_tool_artifact and not force:
                continue

            if mtime < cutoff:
                age_days = (time.time() - mtime) / 86400
                reason = f"{age_days:.1f} days old"
                to_delete.append((entry, reason))

    return to_delete


def main() -> int:
    args = parse_args()

    hermes_home = get_hermes_home()
    print(f"[janitor-cache-clean] Scanning {hermes_home}", file=sys.stderr)

    cache_dirs = get_cache_dirs(hermes_home)
    if not cache_dirs:
        print("[janitor-cache-clean] No cache directories found.", file=sys.stderr)
        return 0

    stale = find_stale_caches(cache_dirs, args.days, args.force)

    if not stale:
        print("[janitor-cache-clean] No stale caches found.", file=sys.stderr)
        return 0

    print(f"[janitor-cache-clean] Found {len(stale)} stale entries:", file=sys.stderr)
    for path, reason in stale:
        print(f"  [{reason}] {path}", file=sys.stderr)

    if args.dry_run:
        print(f"[janitor-cache-clean] DRY RUN — no files deleted.", file=sys.stderr)
        return 0

    deleted = 0
    for path, _ in stale:
        try:
            path.unlink()
            print(f"[janitor-cache-clean] DELETED: {path}", file=sys.stderr)
            deleted += 1
        except OSError as e:
            print(f"[janitor-cache-clean] FAILED to delete {path}: {e}", file=sys.stderr)

    print(f"[janitor-cache-clean] Deleted {deleted} entries.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())