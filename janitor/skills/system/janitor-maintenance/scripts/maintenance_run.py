#!/usr/bin/env python3
"""Run the janitor-system-health audit and compare it with the previous run.

Report-only: it runs the read-only audit, stores the new report in the state
directory (``last.json``, the prior one rotated to ``previous.json``) and prints
the diff as JSON on stdout. The state directory defaults to
``$HERMES_HOME/janitor/system-health`` — the active profile's home, which the
agent's terminal and cron runs export — and is the ONLY place this script
writes. ``--no-save`` writes nothing; ``--compare OLD NEW`` diffs two existing
reports without running the audit.

Exit codes: 0 ok, 2 usage/environment error (no HERMES_HOME and no
``--state-dir``, audit script missing or failed, unwritable state dir).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
STATE_SUBDIR = Path("janitor") / "system-health"
LAST, PREVIOUS = "last.json", "previous.json"
DEFAULT_AUDIT = (Path(__file__).resolve().parents[2]
                 / "janitor-system-health" / "scripts" / "system_health.py")


def _brief(f: dict) -> dict:
    return {k: f.get(k) for k in ("id", "severity", "area", "title", "evidence", "suggested_fix",
                                  "requires_privileges")}


def diff_reports(previous: dict | None, current: dict) -> dict:
    """Compare two audit reports by finding id.

    - ``new``: present now, absent before.
    - ``worse`` / ``improved``: present in both with a higher / lower severity now.
    - ``still_open``: present in both with the same severity.
    - ``fixed``: present before, absent now AND its probe ran now.
    - ``not_verified``: present before, absent now, but its probe was skipped or failed now
      (absence is not evidence of a fix).
    ``info`` findings are context, not problems: they never count as new/fixed/still open.
    """
    def problems(report: dict | None) -> dict[str, dict]:
        return {f["id"]: f for f in (report or {}).get("findings", [])
                if f.get("severity") != "info"}

    prev, cur = problems(previous), problems(current)
    ran_now = {name for name, state in current.get("probes", {}).items() if state == "ok"}
    out = {"new": [], "worse": [], "improved": [], "still_open": [], "fixed": [], "not_verified": []}
    for fid, f in cur.items():
        old = prev.get(fid)
        if old is None:
            out["new"].append(_brief(f))
            continue
        delta = SEVERITY_RANK[f["severity"]] - SEVERITY_RANK[old["severity"]]
        entry = dict(_brief(f), previous_severity=old["severity"])
        out["worse" if delta < 0 else "improved" if delta > 0 else "still_open"].append(entry)
    for fid, old in prev.items():
        if fid in cur:
            continue
        probe = old.get("probe") or fid.split(":", 1)[0]
        (out["fixed"] if probe in ran_now else out["not_verified"]).append(_brief(old))
    for bucket in out.values():
        bucket.sort(key=lambda f: (SEVERITY_RANK.get(f["severity"], 9), f["id"]))
    return {
        "first_run": previous is None,
        "previous_generated_at": (previous or {}).get("generated_at"),
        "current_generated_at": current.get("generated_at"),
        "summary": current.get("summary", {}),
        "skipped": current.get("skipped", []),
        "counts": {k: len(v) for k, v in out.items()},
        **out,
    }


def resolve_state_dir(explicit: str | None, env: dict | None = None) -> Path | None:
    if explicit:
        return Path(explicit).expanduser()
    home = (env if env is not None else os.environ).get("HERMES_HOME", "").strip()
    return Path(home).expanduser() / STATE_SUBDIR if home else None


def load_report(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and "findings" in data else None


def _atomic_write(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def save_rotation(state_dir: Path, current: dict) -> None:
    """``last.json`` → ``previous.json``, new report → ``last.json``."""
    state_dir.mkdir(parents=True, exist_ok=True)
    last = state_dir / LAST
    if load_report(last) is not None:
        os.replace(last, state_dir / PREVIOUS)
    _atomic_write(last, current)


def run_audit(audit_script: Path, extra: list[str]) -> dict:
    proc = subprocess.run([sys.executable, str(audit_script), "--quiet", *extra],
                          capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise RuntimeError(f"la auditoría terminó con código {proc.returncode}: {proc.stderr.strip()[:500]}")
    return json.loads(proc.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auditoría periódica con comparación (solo informe).")
    parser.add_argument("--state-dir", help="Dónde guardar last.json/previous.json "
                                            "(por defecto $HERMES_HOME/janitor/system-health).")
    parser.add_argument("--audit-script", type=Path, default=DEFAULT_AUDIT,
                        help="Ruta de system_health.py (por defecto, la skill hermana).")
    parser.add_argument("--no-save", action="store_true", help="Compara sin guardar el informe nuevo.")
    parser.add_argument("--compare", nargs=2, metavar=("ANTERIOR", "ACTUAL"),
                        help="Compara dos informes existentes sin ejecutar la auditoría.")
    parser.add_argument("--skip", help="Sondas a omitir (se pasa a la auditoría).")
    args = parser.parse_args(argv)

    if args.compare:
        old, new = (load_report(Path(p)) for p in args.compare)
        if new is None:
            print(f"Informe no válido: {args.compare[1]}", file=sys.stderr)
            return 2
        json.dump(diff_reports(old, new), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    state_dir = resolve_state_dir(args.state_dir)
    if state_dir is None:
        print("HERMES_HOME no está definido: pasa --state-dir con el home del perfil.", file=sys.stderr)
        return 2
    if not args.audit_script.is_file():
        print(f"No se encuentra la auditoría: {args.audit_script}", file=sys.stderr)
        return 2
    try:
        current = run_audit(args.audit_script, ["--skip", args.skip] if args.skip else [])
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"Fallo al ejecutar la auditoría: {exc}", file=sys.stderr)
        return 2
    previous = load_report(state_dir / LAST)
    result = diff_reports(previous, current)
    result["state_dir"] = str(state_dir)
    result["saved"] = False
    if not args.no_save:
        try:
            save_rotation(state_dir, current)
            result["saved"] = True
        except OSError as exc:
            print(f"No se pudo guardar en {state_dir}: {exc}", file=sys.stderr)
            return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    c = result["counts"]
    print(f"Nuevos {c['new']}, peores {c['worse']}, mejorados {c['improved']}, corregidos {c['fixed']}, "
          f"siguen {c['still_open']}, sin verificar {c['not_verified']}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
