#!/usr/bin/env python3
"""Audit an explicit Git base before a Janitor merge is accepted."""

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from janitor_ext.fork_audit import fork_diff_violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    diff = subprocess.check_output(
        ["git", "diff", "--no-ext-diff", "--no-color", "--src-prefix=a/",
         "--dst-prefix=b/", "--unified=0", f"{args.base}...HEAD", "--"],
        cwd=ROOT, text=True, encoding="utf-8", errors="replace", timeout=120)
    errors = fork_diff_violations(diff)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("Janitor fork diff audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
