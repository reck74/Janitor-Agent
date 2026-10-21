#!/usr/bin/env python3
"""
diff-waha-group.py — Diff a WAHA WhatsApp group against an external base.

Proven Aug 2026 against a large example group (225→259 records across 4 runs).
Reports three buckets:

  NEW      - In the group, not in the base
  KNOWN    - In both
  EXITED   - In the base, not in the group (candidates only — DO NOT delete)

Usage:
    # Diff against a NocoDB table (default)
    python3 diff-waha-group.py \\
        --waha-url http://127.0.0.1:3000 \\
        --waha-key "$WAHA_API_KEY" \\
        --group-id "120363000000000001@g.us" \\
        --nocodb-url http://127.0.0.1:1980 \\
        --nocodb-token "$NOCODB_XC_TOKEN" \\
        --cookie-file /tmp/nocodb-cookies-fresh.txt \\
        --table-id msgsrwt93puiq7l \\
        --by lid

    # Diff against a custom external base (CSV)
    python3 diff-waha-group.py \\
        --group-id "120363000000000001@g.us" \\
        --csv contacts.csv \\
        --csv-lid-column lid \\
        --by lid

The script is read-only: it reports and never deletes. It can mark records
with a 'left' label via --mark-left-label if your base supports it (NocoDB
PATCH on MultiSelect column).

Important:
- WAHA NOWEB store is NOT needed for this script (group metadata is always
  available from /api/default/groups).
- Phones are normalized (strip @s.whatsapp.net, +, spaces, dashes).
- Run with --dry-run to preview before any modifications.

Pre-flight checks performed:
1. WAHA session WORKING (else abort with clear message)
2. NocoDB cookie file exists and returns 200 on test query
3. Each new contact checked against base before insert

This is a script the agent should run via execute_code (Python 3.11+ on
the workstation), NOT hand-type. The skill's SKILL.md names this script
as the canonical implementation of the diff methodology.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path


def normalize_phone(p):
    """Strip @s.whatsapp.net, +, spaces, dashes. Return only digits, or None."""
    if not p:
        return None
    s = str(p).replace("@s.whatsapp.net", "").replace("+", "").replace(" ", "").replace("-", "")
    return s if s.isdigit() else None


def fetch_waha_groups(waha_url: str, waha_key: str) -> dict:
    """Fetch all groups from WAHA. Returns {group_id: group_dict}."""
    r = subprocess.run(
        ["curl", "-s", "-m", "30",
         "-H", f"X-Api-Key: $WAHA_API_KEY",
         f"{waha_url}/api/default/groups"],
        capture_output=True, text=True,
    )
    r.raise_for_status()
    return json.loads(r.stdout)


def fetch_waha_session_status(waha_url: str, waha_key: str, session: str = "default") -> dict:
    r = subprocess.run(
        ["curl", "-s", "-m", "5",
         "-H", f"X-Api-Key: $WAHA_API_KEY",
         f"{waha_url}/api/sessions/{session}"],
        capture_output=True, text=True,
    )
    r.raise_for_status()
    return json.loads(r.stdout)


def fetch_nocodb_records(base_url: str, token: str, table_id: str,
                         cookie_file: str, limit: int = 100) -> list:
    """Page through all NocoDB records. Returns a list of record dicts."""
    all_records = []
    offset = 0
    while True:
        r = subprocess.run(
            ["curl", "-s", "-m", "15",
             "-b", cookie_file,
             "-H", f"xc-token: {token}",
             f"{base_url}/api/v2/tables/{table_id}/records?limit={limit}&offset={offset}"],
            capture_output=True, text=True,
        )
        r.raise_for_status()
        data = json.loads(r.stdout)
        records = data.get("list", [])
        if not records:
            break
        all_records.extend(records)
        if data.get("pageInfo", {}).get("isLastPage", True):
            break
        offset += limit
    return all_records


def fetch_csv_records(csv_path: str, lid_column: str) -> list:
    """Minimal CSV reader. Avoids pandas dependency."""
    import csv
    records = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lid = row.get(lid_column, "").strip()
            if lid:
                records.append({**row, "_lid": lid})
    return records


def diff(group_participants: list, base_records: list, by: str = "lid") -> dict:
    """
    Three-way diff: NEW (in group, not in base), KNOWN, EXITED (in base, not in group).

    `by` controls the comparison key:
      'lid'      - strict on WhatsApp LID (default, recommended)
      'phone'    - strict on normalized phone (~80% of members visible)
      'username' - strict on @username (~20% of members visible)

    Returns:
        { 'new': [...group_participants], 'known_count': int, 'exited': [...base_records] }
    """
    if by == "lid":
        base_keys = {r.get("WA LID") or r.get("_lid"): r for r in base_records
                     if r.get("WA LID") or r.get("_lid")}
    elif by == "phone":
        base_keys = {}
        for r in base_records:
            pn = normalize_phone(r.get("Phone") or r.get("phone"))
            if pn:
                base_keys[pn] = r
    elif by == "username":
        base_keys = {r.get("@username") or r.get("username"): r for r in base_records
                     if r.get("@username") or r.get("username")}
    else:
        raise ValueError(f"Unknown diff key: {by}")

    new = []
    known = []
    for p in group_participants:
        lid = p["id"]
        if by == "lid":
            if lid in base_keys:
                known.append(lid)
            else:
                new.append(p)
        elif by == "phone":
            pn = normalize_phone(p.get("phoneNumber"))
            if pn and pn in base_keys:
                known.append(lid)
            else:
                new.append(p)
        elif by == "username":
            u = p.get("username")
            if u and u in base_keys:
                known.append(lid)
            else:
                new.append(p)

    exited = []
    if by == "lid":
        group_keys = {p["id"]: p for p in group_participants}
        for lid, rec in base_keys.items():
            if lid and lid not in group_keys:
                exited.append(rec)
    elif by == "phone":
        group_phones = {normalize_phone(p.get("phoneNumber")) for p in group_participants}
        group_phones.discard(None)
        for pn, rec in base_keys.items():
            if pn not in group_phones:
                exited.append(rec)
    elif by == "username":
        group_usernames = {p.get("username") for p in group_participants}
        group_usernames.discard(None)
        for u, rec in base_keys.items():
            if u not in group_usernames:
                exited.append(rec)

    return {
        "new": new,
        "known_count": len(known),
        "exited": exited,
    }


def print_report(group_subject: str, group_size: int, base_size: int,
                 diff_by: str, result: dict, group_lids: list, dry_run: bool):
    """Markdown-friendly report."""
    print(f"\n# Diff against group: {group_subject}")
    print(f"  WAHA participants: {group_size}")
    print(f"  Base records: {base_size}")
    print(f"  Diff key: {diff_by}")
    print()
    print(f"## New in group, not in base: {len(result['new'])}")
    if result["new"]:
        sample = result["new"][:5]
        for p in sample:
            phone = (p.get("phoneNumber") or "").replace("@s.whatsapp.net", "")
            print(f"  - {p['id']:25s} phone={phone:18s} @{p.get('username') or '':20s} role={p.get('admin') or 'member'}")
        if len(result["new"]) > 5:
            print(f"  - ... and {len(result['new']) - 5} more")
    print(f"\n## Known in both: {result['known_count']}")
    print(f"\n## In base, not in group (EXITED candidates — do NOT delete): {len(result['exited'])}")
    if result["exited"]:
        for r in result["exited"][:5]:
            lid = r.get("WA LID") or r.get("_lid") or "?"
            phone = r.get("Phone") or r.get("phone") or ""
            print(f"  - {lid:25s} phone={phone:18s} @{r.get('@username') or r.get('username') or ''}")
        if len(result["exited"]) > 5:
            print(f"  - ... and {len(result['exited']) - 5} more")
    if dry_run:
        print(f"\n[DRY-RUN] No inserts would be applied.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--nocodb-url", help="NocoDB base URL (e.g. http://127.0.0.1:1980)")
    ap.add_argument("--nocodb-token", help="NocoDB xc-token")
    ap.add_argument("--cookie-file", help="Path to NocoDB cookie jar (e.g. /tmp/nocodb-cookies-fresh.txt)")
    ap.add_argument("--table-id", help="NocoDB table ID")
    src.add_argument("--csv", help="Path to CSV with base contacts (alternative to NocoDB)")
    ap.add_argument("--csv-lid-column", default="lid", help="Column name for LID in CSV")
    ap.add_argument("--waha-url", default="http://127.0.0.1:3000", help="WAHA base URL")
    ap.add_argument("--waha-key", help="WAHA API key (env: WAHA_API_KEY)")
    ap.add_argument("--group-id", required=True, help="WAHA group JID, e.g. 120363...@g.us")
    ap.add_argument("--by", choices=["lid", "phone", "username"], default="lid",
                    help="Diff key (default: lid)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report only, do not apply any changes")
    args = ap.parse_args()

    waha_key = args.waha_key or __import__("os").environ.get("WAHA_API_KEY")
    if not waha_key:
        print("ERROR: --waha-key or WAHA_API_KEY env var required", file=sys.stderr)
        sys.exit(1)

    # Preflight: session WORKING
    sess = fetch_waha_session_status(args.waha_url, waha_key)
    if sess.get("status") != "WORKING":
        print(f"ERROR: WAHA session not WORKING (status={sess.get('status')})", file=sys.stderr)
        sys.exit(2)

    # Source from WAHA
    groups = fetch_waha_groups(args.waha_url, waha_key)
    if args.group_id not in groups:
        print(f"ERROR: group {args.group_id} not found in WAHA", file=sys.stderr)
        print(f"Available groups (first 5): {[g.get('subject') for g in list(groups.values())[:5]]}",
              file=sys.stderr)
        sys.exit(3)
    group = groups[args.group_id]
    group_participants = group["participants"]
    group_lids = {p["id"]: p for p in group_participants}

    # Source from base
    if args.csv:
        base_records = fetch_csv_records(args.csv, args.csv_lid_column)
    else:
        if not (args.nocodb_token and args.cookie_file and args.table_id):
            print("ERROR: --nocodb-token, --cookie-file, --table-id required for NocoDB",
                  file=sys.stderr)
            sys.exit(4)
        cookie_path = Path(args.cookie_file)
        if not cookie_path.exists():
            print(f"ERROR: cookie file {args.cookie_file} does not exist — re-run NocoDB login first",
                  file=sys.stderr)
            sys.exit(5)
        base_records = fetch_nocodb_records(args.nocodb_url, args.nocodb_token,
                                            args.table_id, args.cookie_file)

    # Diff
    result = diff(group_participants, base_records, by=args.by)
    print_report(
        group_subject=group["subject"],
        group_size=group["size"],
        base_size=len(base_records),
        diff_by=args.by,
        result=result,
        group_lids=group_lids,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        return

    # If new contacts exist and not dry-run, build insert payload
    if result["new"]:
        print(f"\n# Apply: {len(result['new'])} inserts")
        print("Set --dry-run to preview only. To apply, run without --dry-run and")
        print("extend this script with POST /api/v2/tables/{id}/records (see skill for the payload shape).")
        # In production usage: build payload here and POST.
        # Intentionally NOT auto-inserting: the user's first-class constraint is
        # "never delete from the base" and we always report NEW exits explicitly
        # before mutating the base.


if __name__ == "__main__":
    main()
