"""Approved Hermes-sync reference for Janitor's two incremental CI gates.

Only an ancestral merge of the exact approved engine can use its health baseline.
The PR base still owns ENFORCEMENT; all rule implementations and limits stay upstream.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.ci import check_blob_size as blobs
from scripts.code_health import cli as health
from scripts.code_health import gitio

APPROVED_ENGINE = "d923a5eb487a17c0a68801bba9ef0f56c81040a8"


@dataclass(frozen=True)
class Baseline:
    pr_base: str
    engine: str
    health_base: str


def _is_ancestor(repo: Path, ancestor: str, head: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, head], cwd=repo,
        capture_output=True, text=True, encoding="utf-8", timeout=120,
        stdin=subprocess.DEVNULL, check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"cannot verify Git ancestry: {result.stderr.strip()}")
    return result.returncode == 0


def select_baseline(repo: Path, base: str, head: str = "HEAD") -> Baseline:
    """Reject missing history or unrelated revisions before selecting any exemption."""
    if gitio.git(repo, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise RuntimeError("shallow history cannot establish the approved sync baseline")
    tip = gitio.resolve_rev(repo, head)
    pr_base = gitio.resolve_rev(repo, base)
    engine = gitio.resolve_rev(repo, APPROVED_ENGINE)
    for label, revision in (("PR base", pr_base), ("approved engine", engine)):
        if not _is_ancestor(repo, revision, tip):
            raise RuntimeError(f"{label} {revision} is not an ancestor of {tip}")
    health_base = pr_base if _is_ancestor(repo, engine, pr_base) else engine
    return Baseline(pr_base, engine, health_base)


def blob_offenders(repo: Path, selected: Baseline, head: str | None) -> list[blobs.Offender]:
    """Apply upstream blob rules, then recognize only identical approved-engine objects."""
    allowlist = blobs.allowlist_at(repo, head) if head else blobs.read_allowlist(repo / blobs.ALLOWLIST)
    offenders = blobs.find_offenders(repo, selected.pr_base, head, blobs.MAX_BYTES, allowlist)
    inherited = blobs._tree_blobs(repo, selected.engine)
    remaining = []
    for offender in offenders:
        oid = (gitio.git(repo, "rev-parse", "--verify", f"{head}:{offender.path}").strip()
               if head else blobs._hash_file(repo, offender.path))
        if oid not in inherited:
            remaining.append(offender)
    return remaining


def _run_blobs(repo: Path, selected: Baseline, head: str | None) -> int:
    offenders = blob_offenders(repo, selected, head)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(blobs.summary_table(offenders, blobs.MAX_BYTES))
    if offenders:
        print("\n".join(blobs.render(offenders, blobs.MAX_BYTES)))
        return 1
    print(f"check_blob_size: no new content over the existing {blobs.MAX_BYTES // 1024} KiB limit")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=("health", "blob-size"))
    parser.add_argument("--base", required=True, help="PR base revision; also owns ENFORCEMENT")
    parser.add_argument("--head", help="head commit (default: current working tree)")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        repo = gitio.repo_root(args.repo)
        selected = select_baseline(repo, args.base, args.head or "HEAD")
        head = gitio.resolve_rev(repo, args.head) if args.head else None
        print(f"Janitor CI: PR base={selected.pr_base}; approved engine={selected.engine}; "
              f"health base={selected.health_base}", flush=True)
        if args.gate == "health":
            return health.run(repo, selected.health_base, head, switch_rev=selected.pr_base)
        return _run_blobs(repo, selected, head)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"janitor CI baseline: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
