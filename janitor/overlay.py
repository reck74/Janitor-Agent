"""Janitor overlay inventory (``janitor/overlay.yaml``) and divergence check.

``python -m janitor.overlay check [--base REF]`` lists every file that
differs from the upstream base and fails when one is neither fork-owned
(``fork_paths``) nor declared by a touchpoint.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List, Optional

import yaml

from janitor.home import PACKAGE_ROOT, REPO_ROOT

OVERLAY_PATH = PACKAGE_ROOT / "overlay.yaml"
MERGE_POLICIES = frozenset({"ours", "reapply"})


@dataclass(frozen=True)
class Touchpoint:
    id: str
    files: tuple
    why: str
    verify: str
    merge: str
    upstream_candidate: bool = False


@dataclass(frozen=True)
class Overlay:
    upstream_repo: str
    upstream_base: str
    fork_paths: tuple
    touchpoints: tuple = field(default_factory=tuple)

    def test_check_ids(self) -> set:
        return {
            t.verify.split(":", 1)[1]
            for t in self.touchpoints
            if t.verify.startswith("test:")
        }

    def owner_of(self, path: str) -> Optional[str]:
        """Return ``"fork"``, a touchpoint id, or ``None`` for ``path``."""
        if any(glob_match(path, p) for p in self.fork_paths):
            return "fork"
        for touchpoint in self.touchpoints:
            if any(glob_match(path, p) for p in touchpoint.files):
                return touchpoint.id
        return None

    def undeclared(self, changed_paths: Iterable[str]) -> List[str]:
        return sorted(p for p in set(changed_paths) if self.owner_of(p) is None)


@lru_cache(maxsize=256)
def _glob_regex(pattern: str) -> "re.Pattern[str]":
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def glob_match(path: str, pattern: str) -> bool:
    """Path glob where ``*`` stays inside one segment and ``**`` spans many."""
    return _glob_regex(pattern).match(path) is not None


def parse_overlay(data: dict) -> Overlay:
    if data.get("schema") != 1:
        raise ValueError(f"unsupported overlay schema: {data.get('schema')!r}")
    upstream = data.get("upstream") or {}
    touchpoints = []
    seen = set()
    for raw in data.get("touchpoints") or []:
        tp = Touchpoint(
            id=str(raw["id"]),
            files=tuple(raw["files"]),
            why=str(raw["why"]).strip(),
            verify=str(raw["verify"]),
            merge=str(raw["merge"]),
            upstream_candidate=bool(raw.get("upstream_candidate", False)),
        )
        if tp.id in seen:
            raise ValueError(f"duplicate touchpoint id: {tp.id}")
        if tp.merge not in MERGE_POLICIES:
            raise ValueError(f"{tp.id}: merge must be one of {sorted(MERGE_POLICIES)}")
        if not re.match(r"^(test|ci):[a-z0-9][a-z0-9-]*$", tp.verify):
            raise ValueError(f"{tp.id}: verify must be test:<id> or ci:<job>")
        if not tp.files or not tp.why:
            raise ValueError(f"{tp.id}: files and why are required")
        seen.add(tp.id)
        touchpoints.append(tp)
    return Overlay(
        upstream_repo=str(upstream["repo"]),
        upstream_base=str(upstream["base"]),
        fork_paths=tuple(data.get("fork_paths") or ()),
        touchpoints=tuple(touchpoints),
    )


def load_overlay(path: Path = OVERLAY_PATH) -> Overlay:
    with open(path, encoding="utf-8") as f:
        return parse_overlay(yaml.safe_load(f) or {})


def changed_paths(base: str, repo: Path = REPO_ROOT) -> List[str]:
    """Paths that differ between ``base`` and the working tree (incl. deletions)."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", base],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _cmd_check(args: argparse.Namespace) -> int:
    overlay = load_overlay()
    base = args.base or overlay.upstream_base
    try:
        paths = changed_paths(base)
    except subprocess.CalledProcessError as exc:
        print(f"✗ git diff against {base} failed: {exc.stderr.strip()}", file=sys.stderr)
        print("  Fetch upstream first: git fetch upstream --tags", file=sys.stderr)
        return 2
    undeclared = overlay.undeclared(paths)
    print(f"Overlay check against {base}: {len(paths)} changed paths")
    if not undeclared:
        print("✓ every divergence is fork-owned or a declared touchpoint")
        return 0
    print(f"✗ {len(undeclared)} undeclared divergence(s):")
    for path in undeclared:
        print(f"  {path}")
    print(
        "Restore them from upstream (likely merge residue) or declare them in "
        "janitor/overlay.yaml."
    )
    return 1


def _cmd_list(_args: argparse.Namespace) -> int:
    overlay = load_overlay()
    for tp in overlay.touchpoints:
        flag = " (upstream candidate)" if tp.upstream_candidate else ""
        print(f"{tp.id} [{tp.merge}] {tp.verify}{flag}")
        for f in tp.files:
            print(f"    {f}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m janitor.overlay")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="fail on undeclared divergences from upstream")
    check.add_argument("--base", help="upstream ref (default: overlay upstream.base)")
    check.set_defaults(func=_cmd_check)
    sub.add_parser("list", help="print declared touchpoints").set_defaults(func=_cmd_list)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
