#!/usr/bin/env python3
"""Run the canonical Janitor manifest through upstream's isolated test runner."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from janitor_ext.ci_contracts import janitor_test_files


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        files = janitor_test_files(ROOT)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args == ["--list"]:
        print("\n".join(files))
        return 0
    if args[:1] == ["--"]:
        args.pop(0)
    # health: allow HX006 -- the isolated upstream runner owns per-file deadlines, retries and cancellation
    return subprocess.call(["bash", str(ROOT / "scripts/run_tests.sh"), *files, *args], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
