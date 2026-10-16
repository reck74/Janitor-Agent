#!/usr/bin/env python3
"""Fail closed on new high advisories; make the temporary website exception explicit."""
from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def audit_errors(report: dict, policy: dict, lock: dict, today: date) -> list[str]:
    if report.get("error") or not isinstance(report.get("vulnerabilities"), dict):
        return ["npm audit did not return a complete report"]
    if not isinstance(report.get("metadata", {}).get("vulnerabilities"), dict):
        return ["npm audit omitted vulnerability totals"]
    exceptions = {item["advisory"]: item for item in policy.get("exceptions", [])}
    nodes = report["vulnerabilities"]
    errors = []

    def leaves(name: str, seen: frozenset[str]) -> list[dict]:
        if name in seen:
            return []
        node = nodes.get(name)
        if not isinstance(node, dict):
            raise ValueError(f"audit dependency {name} is missing")
        out = []
        for via in node.get("via", []):
            if isinstance(via, dict):
                out.append(via)
            elif isinstance(via, str):
                out.extend(leaves(via, seen | {name}))
            else:
                raise ValueError(f"invalid audit dependency for {name}")
        return out

    for name, node in nodes.items():
        if node.get("severity") not in {"high", "critical"}:
            continue
        try:
            advisories = leaves(name, frozenset())
            if not advisories:
                raise ValueError(f"{name}: high severity without an attributable advisory")
            for advisory in advisories:
                if advisory.get("severity", "high") not in {"high", "critical"}:
                    continue
                url = advisory.get("url", "")
                exception = exceptions.get(url)
                if not exception:
                    raise ValueError(f"{name}: unreviewed advisory {url}")
                if advisory.get("severity", "high") != exception.get("severity", "high"):
                    raise ValueError(f"{name}: advisory severity changed since review")
                if today > date.fromisoformat(exception["expires"]):
                    raise ValueError(f"{name}: exception expired on {exception['expires']}")
                if advisory.get("name") != exception["package"]:
                    raise ValueError(f"{name}: exception package does not match the advisory")
                affected = nodes[exception["package"]]
                if not affected.get("nodes") or any(
                    lock.get("packages", {}).get(path, {}).get("version") != exception["version"]
                    for path in affected["nodes"]
                ):
                    raise ValueError(f"{name}: installed version differs from reviewed {exception['version']}")
        except (KeyError, TypeError, ValueError) as error:
            errors.append(str(error))
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8-sig"))
    policy = json.loads((ROOT / "website/security-exceptions.json").read_text(encoding="utf-8-sig"))
    lock = json.loads((ROOT / "website/package-lock.json").read_text(encoding="utf-8-sig"))
    errors = audit_errors(report, policy, lock, datetime.now(UTC).date())
    for error in errors:
        print(error)
    if errors:
        return 1
    print("Website audit reviewed: " + json.dumps(report["metadata"]["vulnerabilities"], sort_keys=True))
    print("Known advisories remain; see website/SECURITY-DEPENDENCIES.md and expiring exceptions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
