#!/usr/bin/env python3
"""janitor-file-organizer — put one messy directory in order, plan first.

Subcommands:
  plan     read-only scan of ONE directory; writes a JSON plan of moves
  summary  prints the human summary and the plan digest
  apply    executes the plan's moves (requires --confirm DIGEST); writes an undo manifest
  undo     moves every file back to where it was, removes the folders apply created if empty

Moves are renames inside the same filesystem that never overwrite. Nothing is
deleted; duplicates are only reported. This script never calls sudo.
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import re
import stat
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import janitor_fs_safety as fs  # noqa: E402

SCHEMA = "janitor-organizer-plan/1"
UNDO_SCHEMA = "janitor-organizer-undo/1"

CATEGORY_DIRS = {
    "documents": "Documentos", "images": "Imagenes", "video": "Videos", "audio": "Audio",
    "archives": "Comprimidos", "installers": "Instaladores", "code": "Codigo",
    "data": "Datos", "other": "Otros",
}
COMPOUND = {
    ".pkg.tar.zst": "installers", ".pkg.tar.xz": "installers", ".tar.gz": "archives",
    ".tar.xz": "archives", ".tar.bz2": "archives", ".tar.zst": "archives",
}
EXT = {
    "documents": "pdf doc docx odt rtf txt md epub mobi ppt pptx odp pages key xls xlsx ods tex djvu",
    "images": "jpg jpeg png gif webp bmp tif tiff svg heic heif avif raw cr2 nef arw ico psd xcf kra",
    "video": "mp4 mkv webm avi mov wmv flv m4v mpg mpeg 3gp",
    "audio": "mp3 flac ogg opus wav m4a aac wma aiff mid midi",
    "archives": "zip tar gz tgz xz txz bz2 tbz2 zst 7z rar lz lzma cab",
    "installers": "appimage deb rpm flatpakref flatpak snap run iso exe msi dmg apk jar",
    "code": "py js mjs cjs ts tsx jsx c h cc cpp hpp rs go java kt rb php sh bash zsh fish "
            "lua pl swift cs html css scss ipynb sql",
    "data": "csv tsv json jsonl ndjson xml yaml yml toml ini db sqlite sqlite3 parquet "
            "feather arrow avro gpx kml geojson log",
}
EXT_MAP = {e: cat for cat, exts in EXT.items() for e in exts.split()}
MIME_MAP = {"image": "images", "video": "video", "audio": "audio", "text": "documents"}
PARTIAL_SUFFIXES = (".part", ".crdownload", ".download", ".partial", ".tmp", ".!qb", ".aria2")
PROJECT_MARKERS = (".git", "package.json", "Cargo.toml", "pyproject.toml", "setup.py",
                   "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "Makefile",
                   "CMakeLists.txt", "requirements.txt", ".hg", ".svn")
PLAN_FILE_RE = re.compile(r"^organize-.*\.json$|\.undo\.jsonl?$")


def classify(name: str) -> str:
    lower = name.lower()
    for suffix, cat in COMPOUND.items():
        if lower.endswith(suffix):
            return cat
    ext = os.path.splitext(lower)[1].lstrip(".")
    if ext in EXT_MAP:
        return EXT_MAP[ext]
    mime, _ = mimetypes.guess_type(name, strict=False)
    if mime:
        major, _, minor = mime.partition("/")
        if major in MIME_MAP:
            return MIME_MAP[major]
        if "zip" in minor or "compressed" in minor or "archive" in minor:
            return "archives"
    return "other"


def split_name(name: str) -> tuple[str, str]:
    lower = name.lower()
    for suffix in COMPOUND:
        if lower.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)], name[-len(suffix):]
    stem, ext = os.path.splitext(name)
    return (stem, ext) if stem else (name, "")


def with_suffix(name: str, n: int) -> str:
    stem, ext = split_name(name)
    return f"{stem} ({n}){ext}"


def target_dir(root: str, by: str, category: str, mtime: float) -> str:
    year, month = time.strftime("%Y", time.localtime(mtime)), time.strftime("%Y-%m", time.localtime(mtime))
    if by == "date":
        return os.path.join(root, year, month)
    if by == "type-date":
        return os.path.join(root, CATEGORY_DIRS[category], year)
    return os.path.join(root, CATEGORY_DIRS[category])


# --------------------------------------------------------------------------- plan


def scan(root: str, recursive: bool, include_hidden: bool, bounds: fs.Bounds,
         budget: fs.Budget, notes: list[str]) -> list[tuple[str, os.stat_result]]:
    root_dev = os.lstat(root).st_dev
    reserved = set(CATEGORY_DIRS.values())
    files: list[tuple[str, os.stat_result]] = []
    skipped_dirs = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            names = sorted(os.listdir(current))
        except OSError:
            continue
        for name in names:
            if not budget.tick():
                return files
            child = os.path.join(current, name)
            try:
                st = os.lstat(child)
            except OSError:
                continue
            if stat.S_ISLNK(st.st_mode) or st.st_dev != root_dev:
                continue
            if stat.S_ISDIR(st.st_mode):
                if not recursive:
                    skipped_dirs += 1
                    continue
                if name.startswith(".") or (current == root and (name in reserved or name.isdigit())):
                    continue
                if any(fs.within(child, d) for d in bounds.deny):
                    continue
                try:
                    inner = set(os.listdir(child))
                except OSError:
                    continue
                if inner & set(PROJECT_MARKERS):
                    notes.append(f"Proyecto o repositorio no tocado: {child}")
                    continue
                stack.append(child)
            elif stat.S_ISREG(st.st_mode):
                if name.startswith(".") and not include_hidden:
                    continue
                if name.lower().endswith(PARTIAL_SUFFIXES):
                    notes.append(f"Descarga en curso o temporal, no se mueve: {child}")
                    continue
                if PLAN_FILE_RE.search(name):
                    continue
                files.append((child, st))
    if skipped_dirs:
        notes.append(f"{skipped_dirs} carpetas en la raíz se dejan como están "
                     "(modo no recursivo).")
    return files


def cmd_plan(a: argparse.Namespace) -> int:
    root_arg = os.path.realpath(os.path.expanduser(a.directory))
    try:
        bounds = fs.Bounds.build([root_arg], a.agent_home, explicit_roots=[root_arg])
    except fs.BoundsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    root = bounds.roots[0]
    if root == bounds.home:
        print("error: el home entero no se organiza; nombra una carpeta concreta", file=sys.stderr)
        return 2
    budget = fs.Budget(a.max_seconds, a.max_files)
    notes: list[str] = []
    excluded: list[dict] = []
    files = scan(root, a.recursive, a.include_hidden, bounds, budget, notes)
    entries: list[dict] = []
    taken: set[str] = set()
    for path, st in files:
        refusal = bounds.refusal(path)
        if refusal:
            excluded.append({"path": path, "reason": refusal})
            continue
        name = os.path.basename(path)
        category = classify(name)
        dest_dir = target_dir(root, a.by, category, st.st_mtime)
        if os.path.dirname(path) == dest_dir:
            continue  # already in place
        dst = os.path.join(dest_dir, name)
        n, collision = 2, False
        while dst in taken or os.path.lexists(dst):
            dst = os.path.join(dest_dir, with_suffix(name, n))
            n, collision = n + 1, True
        taken.add(dst)
        entries.append({
            "id": len(entries) + 1, "src": path, "dst": dst, "bytes": st.st_size,
            "category": category, "reason": f"tipo {category}" if a.by == "type" else a.by,
            "collision": collision, "selected": True, "fingerprint": fs.fingerprint(path),
        })
    groups, complete = fs.find_duplicates([(p, st.st_size) for p, st in files if st.st_size > 0],
                                          budget)
    if not complete:
        notes.append("Búsqueda de duplicados incompleta (presupuesto agotado).")
    out = a.out or os.path.join(fs.plans_dir(), f"organize-{time.strftime('%Y%m%d-%H%M%S')}.json")
    plan = {
        "schema": SCHEMA, "created": fs.now_iso(), "home": bounds.home, "roots": [root],
        "root": root, "by": a.by, "recursive": a.recursive, "agent_homes": bounds.agent,
        "limits_hit": budget.hit, "notes": notes, "entries": entries,
        "duplicates": groups, "excluded": excluded,
    }
    fs.write_json(out, plan)
    print_summary(plan, out, a.top)
    return 0


def plan_digest(plan: dict) -> str:
    keys = ("id", "src", "dst", "fingerprint")
    selected = [{k: e.get(k) for k in keys} for e in plan["entries"] if e.get("selected", True)]
    return fs.digest({"roots": plan.get("roots"), "selected": selected})


def print_summary(plan: dict, path: str, top: int) -> None:
    root = plan["root"]
    entries = [e for e in plan["entries"] if e.get("selected", True)]
    print(f"Plan: {path}")
    print(f"Carpeta: {root}  (criterio: {plan['by']}, recursivo: {plan['recursive']})")
    per_dir: dict[str, list[dict]] = {}
    for e in entries:
        per_dir.setdefault(os.path.relpath(os.path.dirname(e["dst"]), root), []).append(e)
    print(f"\nMovimientos: {len(entries)} archivos, "
          f"{fs.human(sum(int(e['bytes']) for e in entries))}")
    for d, items in sorted(per_dir.items(), key=lambda kv: -len(kv[1])):
        print(f"  {d + '/':28} {len(items):5} arch. {fs.human(sum(int(e['bytes']) for e in items)):>11}")
        for e in items[:top]:
            flag = "  [renombrado por colisión]" if e.get("collision") else ""
            print(f"      {os.path.relpath(e['src'], root)} -> "
                  f"{os.path.relpath(e['dst'], root)}{flag}")
        if len(items) > top:
            print(f"      … y {len(items) - top} más")
    if plan.get("duplicates"):
        print(f"\nDuplicados (solo informe, nada se borra): {len(plan['duplicates'])} grupos")
        for g in plan["duplicates"][:top]:
            print(f"  {fs.human(g['size'])} × {len(g['paths'])}: "
                  + ", ".join(os.path.relpath(p, root) for p in g["paths"]))
    for note in plan.get("notes", [])[:top]:
        print(f"Nota: {note}")
    if plan.get("excluded"):
        print(f"Excluidos por las reglas de seguridad: {len(plan['excluded'])}")
    if plan.get("limits_hit"):
        print(f"AVISO: escaneo incompleto — {plan['limits_hit']}")
    print(f"DIGEST: {plan_digest(plan)}")


def cmd_summary(a: argparse.Namespace) -> int:
    print_summary(fs.load_json(a.plan, SCHEMA), a.plan, a.top)
    return 0


# --------------------------------------------------------------------------- apply / undo


def _dst_refusal(bounds: fs.Bounds, dst: str, src_dev: int) -> str | None:
    if not isinstance(dst, str) or not os.path.isabs(dst) or os.path.normpath(dst) != dst:
        return "destino inválido"
    if bounds.root_of(dst) is None:
        return "destino fuera de la carpeta"
    for d in bounds.deny:
        if fs.within(dst, d):
            return "destino protegido"
    existing = os.path.dirname(dst)
    while not os.path.lexists(existing):
        existing = os.path.dirname(existing)
    real_existing = os.path.realpath(existing)
    if real_existing != existing or (bounds.root_of(real_existing) is None
                                     and real_existing not in bounds.roots):
        return "el destino atraviesa un enlace simbólico"
    if not os.path.isdir(existing):
        return "el destino choca con un archivo"
    if os.stat(existing).st_dev != src_dev:
        return "destino en otro sistema de archivos (no se copia)"
    rel = os.path.relpath(dst, bounds.root_of(dst))
    if any(part.startswith(".") or part == ".git" for part in rel.split(os.sep)[:-1]):
        return "destino dentro de una carpeta oculta"
    return None


class _Stop(Exception):
    """The journal could not be written: stop before touching anything else."""


DIGEST_MISMATCH = ("error: el plan cambió o el digest no es el suyo. Ejecuta `summary PLAN`, "
                   "muéstraselo al usuario y usa el DIGEST que imprime solo tras su confirmación.")


def undo_path_for(plan_path: str) -> str:
    return f"{os.path.splitext(plan_path)[0]}.undo.jsonl"


def cmd_apply(a: argparse.Namespace) -> int:
    plan = fs.load_json(a.plan, SCHEMA)
    if a.confirm != plan_digest(plan):
        print(DIGEST_MISMATCH, file=sys.stderr)
        return 2
    try:
        bounds = fs.Bounds.build(plan.get("roots"), a.agent_home, explicit_roots=a.root)
    except fs.BoundsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if len(bounds.roots) != 1 or bounds.roots[0] == bounds.home:
        print("error: el plan debe tener exactamente una carpeta que no sea el home", file=sys.stderr)
        return 2
    root = bounds.roots[0]
    undo_path = undo_path_for(a.plan)
    if os.path.lexists(undo_path):
        print(f"error: ya existe {undo_path}; este plan ya se aplicó", file=sys.stderr)
        return 2
    try:
        journal = fs.Journal(undo_path, {"schema": UNDO_SCHEMA, "created": fs.now_iso(),
                                         "plan": os.path.abspath(a.plan), "roots": [root]})
    except fs.JournalError as exc:
        print(f"error: sin diario de deshacer no se mueve nada: {exc}", file=sys.stderr)
        return 1

    def jot(record: dict) -> None:
        try:
            journal.append(record)
        except fs.JournalError as exc:
            raise _Stop(str(exc)) from exc

    moved: list[dict] = []
    skipped: list[dict] = []
    seen: set[str] = set()
    stopped = None
    try:
        for e in plan["entries"]:
            if not e.get("selected", True):
                continue
            src = bounds.resolve(e["src"]) if isinstance(e.get("src"), str) else ""
            reason = None if src and src not in seen else "entrada inválida"
            seen.add(src)
            if not reason:
                reason = bounds.refusal(src)
            if not reason and (os.path.islink(src) or not os.path.isfile(src)):
                reason = "no es un archivo regular"
            if not reason:
                ok, why = fs.fingerprint_matches(src, e.get("fingerprint"))
                reason = None if ok else why
            dst = e.get("dst")
            if not reason:
                reason = _dst_refusal(bounds, dst, os.lstat(src).st_dev)
            if not reason:
                reason = _make_dirs(os.path.dirname(dst), root, journal, jot)
            if reason:
                skipped.append({"id": e.get("id"), "src": src or e.get("src"), "reason": reason})
                jot({"op": "skip", "id": e.get("id"), "src": src or str(e.get("src")),
                     "reason": reason})
                continue
            st = os.lstat(src)
            ident = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "ino": st.st_ino}
            target, n = dst, 2
            while True:
                seq = journal.next_seq()
                jot({"op": "move", "seq": seq, "state": "pending", "id": e.get("id"),
                     "src": src, "dst": target, **ident})
                try:
                    fs.rename_noreplace(src, target)
                except FileExistsError:
                    jot({"seq": seq, "state": "failed", "reason": "destino ocupado"})
                    target = os.path.join(os.path.dirname(dst),
                                          with_suffix(os.path.basename(dst), n))
                    n += 1
                    continue
                except OSError as exc:
                    jot({"seq": seq, "state": "failed", "reason": exc.strerror})
                    skipped.append({"id": e.get("id"), "src": src, "reason": exc.strerror})
                    break
                moved.append({"src": src, "dst": target, "renamed": target != dst})
                jot({"seq": seq, "state": "done"})
                break
    except _Stop as exc:
        stopped = str(exc)
    finally:
        journal.close()
    print(f"Movidos: {len(moved)} archivos")
    for m in moved:
        flag = " (renombrado por colisión)" if m["renamed"] else ""
        print(f"  {os.path.relpath(m['src'], root)} -> {os.path.relpath(m['dst'], root)}{flag}")
    print(f"Omitidos: {len(skipped)}")
    for s_ in skipped:
        print(f"  #{s_['id']} {s_['src']}: {s_['reason']}")
    print(f"\nDeshacer: python3 {os.path.abspath(__file__)} undo {undo_path}")
    if stopped:
        print(f"\nDETENIDO: no se pudo escribir el diario ({stopped}); no se movió nada más.",
              file=sys.stderr)
        return 1
    return 0


def _make_dirs(path: str, root: str, journal: "fs.Journal", jot) -> str | None:
    """Create the missing folders of *path*, journaling each one before mkdir."""
    missing = []
    cur = path
    while not os.path.lexists(cur) and fs.within(cur, root) and cur != root:
        missing.append(cur)
        cur = os.path.dirname(cur)
    for d in reversed(missing):
        seq = journal.next_seq()
        jot({"op": "mkdir", "seq": seq, "state": "pending", "path": d})
        try:
            os.mkdir(d, 0o755)
        except OSError as exc:
            jot({"seq": seq, "state": "failed", "reason": exc.strerror})
            return f"no se pudo crear {d}: {exc.strerror}"
        jot({"seq": seq, "state": "done"})
    return None


def _ident(path: str) -> tuple | None:
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns, st.st_ino)


def cmd_undo(a: argparse.Namespace) -> int:
    header, records = fs.read_journal(a.undo, UNDO_SCHEMA)
    try:
        bounds = fs.Bounds.build(header.get("roots"), a.agent_home, explicit_roots=a.root)
    except fs.BoundsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    ops = fs.journal_ops(records)
    restored, already, failed = 0, 0, []
    for op in reversed([o for o in ops if o.get("op") == "move" and o["outcome"] != "failed"]):
        src, dst = op.get("src"), op.get("dst")
        if not all(isinstance(x, str) and os.path.isabs(x) for x in (src, dst)) \
                or bounds.root_of(src) is None or bounds.root_of(dst) is None:
            failed.append((dst, "registro inválido o fuera de la carpeta"))
            continue
        ident = (op.get("size"), op.get("mtime_ns"), op.get("ino"))
        at_dst, at_src = _ident(dst) == ident, _ident(src) == ident
        if at_src and not at_dst:
            already += 1  # never moved (crash before rename) or already restored
            continue
        if not at_dst:
            failed.append((dst, "el archivo ya no está en el destino o cambió"))
            continue
        if os.path.lexists(src):
            failed.append((dst, "la ruta original está ocupada; no se sobrescribe"))
            continue
        # Reverting our own moves: the git state may have changed because of them,
        # so only bounds/denylist/symlink rules apply.
        reason = bounds.refusal(dst, check_git=False) or (
            None if os.path.isdir(os.path.dirname(src)) else
            _dst_refusal(bounds, src, os.lstat(dst).st_dev))
        if reason:
            failed.append((dst, reason))
            continue
        os.makedirs(os.path.dirname(src), exist_ok=True)
        try:
            fs.rename_noreplace(dst, src)
            restored += 1
        except FileExistsError:
            failed.append((dst, "la ruta original está ocupada; no se sobrescribe"))
        except OSError as exc:
            failed.append((dst, exc.strerror or "error al mover"))
    dirs = [o.get("path") for o in ops if o.get("op") == "mkdir" and o["outcome"] != "failed"]
    for d in sorted((d for d in dirs if isinstance(d, str)), key=len, reverse=True):
        if bounds.root_of(d) is not None:
            try:
                os.rmdir(d)  # only succeeds when empty; never removes content
            except OSError:
                pass
    print(f"Restaurados: {restored} archivos")
    if already:
        print(f"Ya en su sitio (no movidos o ya restaurados): {already}")
    for dst, reason in failed:
        print(f"  NO restaurado {dst}: {reason}")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="janitor_organize.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="escaneo de solo lectura de una carpeta")
    p.add_argument("directory")
    p.add_argument("--by", choices=["type", "date", "type-date"], default="type")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--include-hidden", action="store_true", help="mover también archivos ocultos")
    p.add_argument("--agent-home", action="append")
    p.add_argument("--max-seconds", type=float, default=120)
    p.add_argument("--max-files", type=int, default=200_000)
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--out")
    p.set_defaults(func=cmd_plan)
    p = sub.add_parser("summary")
    p.add_argument("plan")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(func=cmd_summary)
    p = sub.add_parser("apply")
    p.add_argument("plan")
    p.add_argument("--confirm", required=True)
    p.add_argument("--root", action="append", help="carpeta fuera del home, repetida a propósito")
    p.add_argument("--agent-home", action="append")
    p.set_defaults(func=cmd_apply)
    p = sub.add_parser("undo")
    p.add_argument("undo")
    p.add_argument("--root", action="append")
    p.add_argument("--agent-home", action="append")
    p.set_defaults(func=cmd_undo)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
