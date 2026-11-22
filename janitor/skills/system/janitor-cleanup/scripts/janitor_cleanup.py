#!/usr/bin/env python3
"""janitor-cleanup — reclaim disk space on a Linux workstation, plan first.

Subcommands:
  plan     read-only scan; writes a JSON plan and prints a summary
  summary  prints the human summary and the plan digest
  select   marks plan entries for apply (by id, category or risk)
  apply    executes ONLY the selected entries of a plan (requires --confirm DIGEST)
  restore  moves back from the Trash what an apply moved there

Nothing is ever unlinked: files and directories go to the freedesktop.org Trash;
regenerable tool caches are cleared by the tool's own command; privileged actions
are only suggested. This script never calls sudo.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import time
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import janitor_fs_safety as fs  # noqa: E402

SCHEMA = "janitor-cleanup-plan/1"
RESULT_SCHEMA = "janitor-cleanup-journal/1"
MiB = 1024 * 1024
DAY = 86400

CATEGORIES = {
    "pkg-cache": "Cachés del gestor de paquetes (requiere privilegios: solo sugerencia)",
    "tool-cache": "Cachés de lenguajes y herramientas",
    "user-cache": "Entradas antiguas de ~/.cache",
    "thumbnails": "Miniaturas",
    "trash-old": "Papelera: elementos antiguos",
    "logs": "Logs antiguos del usuario y journal",
    "docker": "Docker: imágenes colgantes, contenedores parados, caché de build",
    "build-artifacts": "Artefactos de build en proyectos inactivos",
    "large-files": "Archivos grandes (solo informe)",
    "old-downloads": "Descargas antiguas (solo informe)",
    "duplicates": "Duplicados (solo informe)",
}
REPORT_ONLY = {"large-files", "old-downloads", "duplicates"}


@dataclass(frozen=True)
class Tool:
    bins: tuple
    argv: tuple
    risk: str
    label: str
    probe: tuple | None = None


# The ONLY commands apply may run. A plan entry names a key; apply rebuilds the
# argv from this table and refuses any entry whose argv differs.
TOOLS = {
    "pip": Tool(("pip", "pip3"), ("cache", "purge"), "safe", "caché de pip", ("cache", "dir")),
    "uv": Tool(("uv",), ("cache", "clean"), "safe", "caché de uv", ("cache", "dir")),
    "npm": Tool(("npm",), ("cache", "clean", "--force"), "safe", "caché de npm",
                ("config", "get", "cache")),
    "yarn": Tool(("yarn",), ("cache", "clean"), "safe", "caché de yarn", ("cache", "dir")),
    "pnpm": Tool(("pnpm",), ("store", "prune"), "safe", "store de pnpm (paquetes sin uso)",
                 ("store", "path")),
    "go-build": Tool(("go",), ("clean", "-cache"), "safe", "caché de build de Go",
                     ("env", "GOCACHE")),
    "go-mod": Tool(("go",), ("clean", "-modcache"), "review",
                   "caché de módulos de Go (se vuelve a descargar)", ("env", "GOMODCACHE")),
    "cargo": Tool(("cargo-cache",), ("--autoclean",), "safe", "caché de registro de cargo"),
    "docker-images": Tool(("docker",), ("image", "prune", "-f"), "safe",
                          "Docker: imágenes colgantes (dangling)"),
    "docker-containers": Tool(("docker",), ("container", "prune", "-f"), "review",
                              "Docker: contenedores parados (se pierde su estado)"),
    "docker-build": Tool(("docker",), ("builder", "prune", "-f"), "safe",
                         "Docker: caché de build"),
    "trash-empty": Tool(("trash-empty",), (), "review",
                        "vaciar de la papelera lo más antiguo (borrado definitivo)"),
}

# Costly to rebuild or holding state: never proposed from ~/.cache.
CACHE_DENY = {
    "huggingface", "torch", "JetBrains", "bazel", "ollama", "lm-studio", "whisper",
    "keepassxc", "gnome-software", "flatpak", "nix", "hermes", "janitor", "pip", "uv",
    "yarn", "pnpm", "go-build", "ms-playwright", "thumbnails", "pypoetry", "conda",
    "mozilla", "chromium", "google-chrome", "BraveSoftware", "vivaldi", "evolution",
    "tracker3", "kioexec", "kwalletd", "gnupg",
}

PROJECT_MARKERS = {
    "package.json": ("node_modules", "dist", "build", ".next", ".nuxt", ".parcel-cache"),
    "Cargo.toml": ("target",),
    "pom.xml": ("target",),
    "build.gradle": ("build", ".gradle"),
    "build.gradle.kts": ("build", ".gradle"),
    "pyproject.toml": (".venv", "venv", "dist", "build", ".tox", ".mypy_cache",
                       ".pytest_cache", ".ruff_cache"),
    "setup.py": (".venv", "venv", "dist", "build", ".tox"),
    "requirements.txt": (".venv", "venv"),
    "go.mod": (),
}
REVIEW_ARTIFACTS = {".venv", "venv", "dist", "build"}
LOG_RE = re.compile(r"(\.log|\.log\.\d+|\.log\.(gz|xz|zst|bz2)|\.log\.old)$")
SIZE_RE = re.compile(r"^\s*([\d.]+)\s*([kKMGT]?i?B)\s*$")


on_path = fs.find_executable


def tool_binary(tool: Tool) -> str | None:
    for name in tool.bins:
        found = on_path(name)
        if found:
            return found
    return None


def run_probe(argv: list, timeout: int = 20) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None


def parse_size(text: str) -> int:
    m = SIZE_RE.match(text.split("(")[0])
    if not m:
        return 0
    value, unit = float(m.group(1)), m.group(2).upper().replace("I", "")
    mult = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}.get(unit, 1)
    return int(value * mult)


# --------------------------------------------------------------------------- planning


class Planner:
    def __init__(self, args: argparse.Namespace, bounds: fs.Bounds, budget: fs.Budget):
        self.a = args
        self.b = bounds
        self.budget = budget
        self.home = bounds.home
        self.entries: list[dict] = []
        self.excluded: list[dict] = []
        self.notes: list[str] = []
        self.now = time.time()
        self._paths: set[tuple[str, str]] = set()

    # ---- entry builders ------------------------------------------------------

    def _add(self, entry: dict) -> None:
        entry["id"] = len(self.entries) + 1
        self.entries.append(entry)

    def add_trash(self, category: str, path: str, reason: str, risk: str,
                  *, report_only: bool = False, extra: dict | None = None) -> bool:
        real = self.b.resolve(path)
        if (category, real) in self._paths:
            return False
        refusal = self.b.refusal(real)
        if refusal:
            self.excluded.append({"category": category, "path": real, "reason": refusal})
            return False
        stats = self.b.stats_cache.get(real) or fs.tree_stats(real)
        fp = fs.fingerprint(real, stats=stats if os.path.isdir(real) else None)
        if fp is None:
            return False
        self._paths.add((category, real))
        entry = {
            "category": category, "path": real, "bytes": stats.disk, "reason": reason,
            "risk": risk, "method": "trash", "report_only": report_only,
            "selected": risk == "safe" and not report_only, "fingerprint": fp,
        }
        entry.update(extra or {})
        self._add(entry)
        return True

    def add_tool(self, category: str, key: str, path: str, nbytes: int, reason: str) -> None:
        tool = TOOLS[key]
        binary = tool_binary(tool)
        if not binary:
            return
        argv = list(tool.argv) if key != "trash-empty" else [str(self.a.trash_days)]
        self._add({
            "category": category, "path": path, "bytes": nbytes, "reason": reason,
            "risk": tool.risk, "method": "tool", "report_only": False,
            "selected": tool.risk == "safe", "tool": key, "binary": binary, "argv": argv,
            "command": shlex.join([os.path.basename(binary), *argv]),
        })

    def add_suggestion(self, category: str, path: str, nbytes: int, reason: str,
                       command: str, privileged: bool) -> None:
        self._add({
            "category": category, "path": path, "bytes": nbytes, "reason": reason,
            "risk": "review", "method": "suggest", "report_only": True, "selected": False,
            "command": command, "privileged": privileged,
        })

    # ---- categories ----------------------------------------------------------

    def pkg_cache(self) -> None:
        managers = [
            ("pacman", ["/var/cache/pacman/pkg"],
             "sudo paccache -rk2" if on_path("paccache") else "sudo pacman -Sc"),
            ("apt-get", ["/var/cache/apt/archives"], "sudo apt-get clean"),
            ("dnf", ["/var/cache/libdnf5", "/var/cache/dnf"], "sudo dnf clean packages"),
        ]
        for binary, dirs, command in managers:
            if not on_path(binary):
                continue
            for d in dirs:
                if os.path.isdir(d):
                    ts = fs.tree_stats(d, self.budget)
                    if ts.disk >= MiB:
                        self.add_suggestion("pkg-cache", d, ts.disk,
                                            f"caché de paquetes de {binary}", command, True)
                    break

    def tool_cache(self) -> None:
        for key in ("pip", "uv", "npm", "yarn", "pnpm", "go-build", "go-mod"):
            self.budget.phase(f"tool-cache/{key}")
            tool = TOOLS[key]
            binary = tool_binary(tool)
            if not binary:
                continue
            proc = run_probe([binary, *tool.probe])
            if proc is None or proc.returncode != 0:
                continue
            lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
            path = lines[-1] if lines else ""
            if not os.path.isabs(path) or not os.path.isdir(path):
                continue
            ts = fs.tree_stats(path, self.budget)
            if ts.disk >= MiB:
                label = tool.label + (" (tamaño mínimo: escaneo truncado)" if ts.truncated else "")
                self.add_tool("tool-cache", key, path, ts.disk, label)
        self.budget.phase("tool-cache/otros")
        self._cargo()
        for rel, label in ((".gradle/caches", "caché de Gradle (se vuelve a descargar)"),
                           (".m2/repository", "repositorio local de Maven (se vuelve a descargar)")):
            path = os.path.join(self.home, rel)
            if os.path.isdir(path):
                self.add_trash("tool-cache", path, label, "review")
        self._huggingface()
        self._playwright()

    def _cargo(self) -> None:
        cargo_home = os.environ.get("CARGO_HOME") or os.path.join(self.home, ".cargo")
        dirs = [os.path.join(cargo_home, rel) for rel in
                ("registry/cache", "registry/src", "git/checkouts")]
        dirs = [d for d in dirs if os.path.isdir(d)]
        if not dirs:
            return
        if tool_binary(TOOLS["cargo"]):
            total = sum(fs.tree_stats(d, self.budget).disk for d in dirs)
            if total >= MiB:
                self.add_tool("tool-cache", "cargo", cargo_home, total, TOOLS["cargo"].label)
            return
        for d in dirs:
            self.add_trash("tool-cache", d, "caché de cargo (se regenera al compilar)", "safe")

    def _huggingface(self) -> None:
        hub = os.environ.get("HF_HUB_CACHE") or os.path.join(
            os.environ.get("HF_HOME") or os.path.join(fs.xdg_cache_home(self.home), "huggingface"),
            "hub")
        if not os.path.isdir(hub):
            return
        ts = fs.tree_stats(hub, self.budget)
        if ts.disk >= MiB:
            command = "hf cache delete" if on_path("hf") else "huggingface-cli delete-cache"
            self.add_suggestion("tool-cache", hub, ts.disk,
                                "modelos de HuggingFace (costosos de volver a descargar)",
                                command, False)

    def _playwright(self) -> None:
        base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.join(
            fs.xdg_cache_home(self.home), "ms-playwright")
        try:
            names = os.listdir(base)
        except OSError:
            return
        families: dict[str, list[tuple[int, str]]] = {}
        for name in names:
            fam, _, rev = name.rpartition("-")
            if fam and rev.isdigit():
                families.setdefault(fam, []).append((int(rev), name))
        for fam, revs in families.items():
            revs.sort()
            for _rev, name in revs[:-1]:
                self.add_trash("tool-cache", os.path.join(base, name),
                               f"revisión antigua de navegador Playwright ({fam})", "safe")

    def user_cache(self) -> None:
        cache = fs.xdg_cache_home(self.home)
        try:
            names = sorted(os.listdir(cache))
        except OSError:
            return
        cutoff_ns = (self.now - self.a.cache_days * DAY) * 1e9
        for name in names:
            if self.budget.exhausted:
                return
            if name in CACHE_DENY:
                continue
            path = os.path.join(cache, name)
            if os.path.islink(path):
                continue
            ts = fs.tree_stats(path, self.budget)
            if ts.truncated or ts.disk < MiB or ts.max_mtime_ns > cutoff_ns:
                continue
            days = int((self.now - ts.max_mtime_ns / 1e9) / DAY)
            self.add_trash("user-cache", path, f"sin uso desde hace {days} días", "safe")

    def thumbnails(self) -> None:
        path = os.path.join(fs.xdg_cache_home(self.home), "thumbnails")
        if os.path.isdir(path) and fs.tree_stats(path, self.budget).disk >= MiB:
            self.add_trash("thumbnails", path, "miniaturas (se regeneran al navegar)", "safe")

    def trash_old(self) -> None:
        items = fs.trash_items(fs.home_trash_dir(self.home))
        cutoff = self.now - self.a.trash_days * DAY
        old = [it for it in items if it["deleted"] < cutoff]
        if not old:
            return
        total = sum(fs.tree_stats(it["files"], self.budget).disk for it in old)
        reason = f"{len(old)} elementos en la papelera hace más de {self.a.trash_days} días"
        if tool_binary(TOOLS["trash-empty"]):
            self.add_tool("trash-old", "trash-empty", fs.home_trash_dir(self.home), total, reason)
        else:
            self.add_suggestion("trash-old", fs.home_trash_dir(self.home), total, reason,
                                f"trash-empty {self.a.trash_days}  # paquete trash-cli", False)

    def logs(self) -> None:
        cutoff = self.now - self.a.log_days * DAY
        for base in {fs.xdg_state_home(self.home), fs.xdg_cache_home(self.home),
                     fs.xdg_config_home(self.home), fs.xdg_data_home(self.home)}:
            for path, st in self._walk_files(base, max_depth=6):
                if LOG_RE.search(os.path.basename(path)) and st.st_mtime < cutoff \
                        and st.st_blocks * 512 >= 64 * 1024:
                    days = int((self.now - st.st_mtime) / DAY)
                    self.add_trash("logs", path, f"log sin escribir desde hace {days} días",
                                   "review")
        journalctl = on_path("journalctl")
        if journalctl:
            proc = run_probe([journalctl, "--user", "--disk-usage"])
            m = re.search(r"take up ([\d.]+\s*[KMGT]?)", proc.stdout + proc.stderr) if proc else None
            if m:
                num = m.group(1).replace(" ", "")
                unit = num[-1] if num[-1] in "KMGT" else ""
                value = float(num.rstrip("KMGT"))
                nbytes = int(value * {"": 1, "K": 1024, "M": MiB, "G": 1024 * MiB,
                                      "T": 1024 * 1024 * MiB}[unit])
                if nbytes >= 64 * MiB:
                    self.add_suggestion(
                        "logs", "journal --user", nbytes, "journal de systemd del usuario",
                        f"journalctl --user --vacuum-time={self.a.log_days}d", False)

    def _walk_files(self, base: str, max_depth: int):
        if not os.path.isdir(base):
            return
        base_dev = os.lstat(base).st_dev
        stack = [(base, 0)]
        while stack:
            current, depth = stack.pop()
            if any(fs.within(current, d) for d in self.b.deny):
                continue
            try:
                names = os.listdir(current)
            except OSError:
                continue
            for name in names:
                if not self.budget.tick():
                    return
                child = os.path.join(current, name)
                try:
                    st = os.lstat(child)
                except OSError:
                    continue
                if st.st_dev != base_dev or stat.S_ISLNK(st.st_mode):
                    continue
                if stat.S_ISDIR(st.st_mode):
                    if name != ".git" and depth < max_depth:
                        stack.append((child, depth + 1))
                elif stat.S_ISREG(st.st_mode):
                    yield child, st

    def docker(self) -> None:
        tool = TOOLS["docker-images"]
        binary = tool_binary(tool)
        if not binary:
            return
        df = run_probe([binary, "system", "df", "--format", "{{json .}}"])
        if df is None or df.returncode != 0:
            err = (df.stderr.strip().splitlines() or ["sin respuesta"])[-1] if df else "sin respuesta"
            self.notes.append(f"Docker no responde sin privilegios ({err}); no se propone nada. "
                              "Si el usuario lo pide, sugerir: sudo docker system df")
            return
        rows = {}
        for line in df.stdout.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            rows[row.get("Type", "")] = row
        dangling = run_probe([binary, "images", "--filter", "dangling=true", "--format",
                              "{{.Size}}"])
        img_bytes = sum(parse_size(x) for x in dangling.stdout.split()) if dangling and \
            dangling.returncode == 0 else 0
        if img_bytes:
            self.add_tool("docker", "docker-images", "docker:images", img_bytes,
                          tool.label)
        for key, row_type in (("docker-containers", "Containers"),
                              ("docker-build", "Build Cache")):
            nbytes = parse_size(rows.get(row_type, {}).get("Reclaimable", "0B"))
            if nbytes:
                self.add_tool("docker", key, f"docker:{row_type.lower()}", nbytes,
                              TOOLS[key].label)
        vol = parse_size(rows.get("Local Volumes", {}).get("Reclaimable", "0B"))
        if vol:
            self.notes.append(f"Docker: {fs.human(vol)} en volúmenes sin usar. Los volúmenes "
                              "NUNCA se tocan salvo que el usuario nombre cuáles.")

    # ---- one walk of the roots for the report-only and build categories -----

    def home_walk(self, cats: set[str]) -> None:
        large = self.a.large_mb * MiB
        dup_min = self.a.dup_min_mb * MiB
        downloads = download_dir(self.home)
        dl_cutoff = self.now - self.a.downloads_days * DAY
        large_files: list[tuple[str, int]] = []
        old_dl: list[tuple[str, float]] = []
        dup_files: list[tuple[str, int]] = []
        projects: list[dict] = []

        def scan(current: str, dev: int, depth: int, stack: list[dict]) -> None:
            try:
                names = os.listdir(current)
            except OSError:
                return
            markers = [m for m in PROJECT_MARKERS if m in names]
            if markers:
                proj = {"path": current, "mtime": 0,
                        "artifacts": [],
                        "allowed": {a for m in markers for a in PROJECT_MARKERS[m]}}
                projects.append(proj)
                stack = stack + [proj]
            for name in names:
                if not self.budget.tick():
                    return
                child = os.path.join(current, name)
                try:
                    st = os.lstat(child)
                except OSError:
                    continue
                if stat.S_ISLNK(st.st_mode) or st.st_dev != dev:
                    continue
                if stat.S_ISDIR(st.st_mode):
                    if markers and name in stack[-1]["allowed"]:
                        stack[-1]["artifacts"].append(child)
                        continue
                    if name == "__pycache__" and stack:
                        stack[-1]["artifacts"].append(child)
                        continue
                    if name.startswith(".") or name in ("node_modules", "__pycache__"):
                        continue
                    if any(fs.within(child, d) for d in self.b.deny):
                        continue
                    if depth < self.a.max_depth:
                        scan(child, dev, depth + 1, stack)
                elif stat.S_ISREG(st.st_mode):
                    for proj in stack:
                        if st.st_mtime_ns > proj["mtime"]:
                            proj["mtime"] = st.st_mtime_ns
                    if downloads and fs.within(child, downloads) and st.st_mtime < dl_cutoff:
                        old_dl.append((child, st.st_mtime))
                    elif st.st_size >= large:
                        large_files.append((child, st.st_size))
                    if st.st_size >= dup_min:
                        dup_files.append((child, st.st_size))

        for root in self.b.roots:
            scan(root, os.lstat(root).st_dev, 0, [])

        if "large-files" in cats:
            for path, size in sorted(large_files, key=lambda x: -x[1])[: self.a.max_report]:
                self.add_trash("large-files", path, f"archivo de {fs.human(size)}", "review",
                               report_only=True)
        if "old-downloads" in cats:
            for path, mtime in sorted(old_dl, key=lambda x: x[1])[: self.a.max_report]:
                days = int((self.now - mtime) / DAY)
                self.add_trash("old-downloads", path, f"descargado hace {days} días", "review",
                               report_only=True)
        if "build-artifacts" in cats:
            self._artifacts(projects)
        if "duplicates" in cats:
            self._duplicates(dup_files)

    def _artifacts(self, projects: list[dict]) -> None:
        cutoff_ns = (self.now - self.a.project_days * DAY) * 1e9
        for proj in projects:
            if not proj["artifacts"] or proj["mtime"] > cutoff_ns:
                continue
            top = self.b.git_top(os.path.join(proj["path"], "x"))
            days = int((self.now - proj["mtime"] / 1e9) / DAY)
            for art in proj["artifacts"]:
                if top and not fs.git_ignored(top, art):
                    continue  # tracked by git: not an artefact
                name = os.path.basename(art)
                risk = "review" if name in REVIEW_ARTIFACTS else "safe"
                self.add_trash("build-artifacts", art,
                               f"{name} de un proyecto sin tocar hace {days} días", risk)

    def _duplicates(self, files: list[tuple[str, int]]) -> None:
        groups, complete = fs.find_duplicates(files, self.budget,
                                              self.a.dup_max_gb * 1024 * MiB)
        if not complete:
            self.notes.append("Búsqueda de duplicados incompleta (presupuesto agotado).")
        for gid, group in enumerate(groups[: self.a.max_report], start=1):
            n = len(group["paths"])
            for path in group["paths"]:
                self.add_trash("duplicates", path,
                               f"grupo {gid}: {n} copias idénticas (sha256 {group['sha256'][:12]})",
                               "review", report_only=True,
                               extra={"group": gid, "sha256": group["sha256"]})


def download_dir(home: str) -> str | None:
    cfg = os.path.join(fs.xdg_config_home(home), "user-dirs.dirs")
    try:
        with open(cfg, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r'\s*XDG_DOWNLOAD_DIR="(.*)"', line)
                if m:
                    path = m.group(1).replace("$HOME", home)
                    if os.path.isdir(path):
                        return os.path.realpath(path)
    except OSError:
        pass
    for name in ("Downloads", "Descargas"):
        path = os.path.join(home, name)
        if os.path.isdir(path):
            return os.path.realpath(path)
    return None


# --------------------------------------------------------------------------- plan file helpers


def plan_digest(plan: dict) -> str:
    keys = ("id", "category", "path", "method", "tool", "binary", "argv", "fingerprint")
    selected = [{k: e.get(k) for k in keys} for e in plan["entries"] if e.get("selected")]
    return fs.digest({"roots": plan.get("roots"), "selected": selected})


def totals(entries: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for e in entries:
        t = out.setdefault(e["category"], {"count": 0, "bytes": 0, "selected": 0,
                                            "selected_bytes": 0})
        t["count"] += 1
        t["bytes"] += int(e.get("bytes") or 0)
        if e.get("selected"):
            t["selected"] += 1
            t["selected_bytes"] += int(e.get("bytes") or 0)
    return out


def method_label(e: dict) -> str:
    if e["method"] == "trash":
        return "papelera"
    if e["method"] == "tool":
        return f"comando: {e['command']}"
    return ("SUGERENCIA CON PRIVILEGIOS: " if e.get("privileged") else "sugerencia: ") + e["command"]


def print_summary(plan: dict, path: str, top: int) -> None:
    entries = plan["entries"]
    print(f"Plan: {path}")
    print(f"Raíces: {', '.join(plan['roots'])}")
    print("\nPor categoría (total | marcado para aplicar):")
    for cat, t in sorted(totals(entries).items(), key=lambda kv: -kv[1]["bytes"]):
        flag = " [solo informe]" if cat in REPORT_ONLY else ""
        print(f"  {cat:16} {t['count']:5} elem. {fs.human(t['bytes']):>11} | "
              f"{t['selected']:4} marcados {fs.human(t['selected_bytes']):>11}{flag}")
    sel = [e for e in entries if e.get("selected")]
    print(f"\nMarcado para aplicar: {len(sel)} elementos, "
          f"{fs.human(sum(int(e['bytes']) for e in sel))}")
    for e in sorted(sel, key=lambda e: -int(e["bytes"]))[:top]:
        print(f"  #{e['id']:<5} {fs.human(e['bytes']):>11}  {e['risk']:6} {e['path']}  "
              f"({e['reason']}; {method_label(e)})")
    unusual = [e for e in entries if e["method"] == "suggest"]
    if unusual:
        print("\nSolo sugerencias (este script no las ejecuta):")
        for e in unusual:
            print(f"  #{e['id']:<5} {fs.human(e['bytes']):>11}  {e['reason']}: {method_label(e)}")
    review = [e for e in entries if not e.get("selected") and e["method"] != "suggest"]
    if review:
        print(f"\nSin marcar (decide el usuario): {len(review)} elementos, "
              f"{fs.human(sum(int(e['bytes']) for e in review))}. Mayores:")
        for e in sorted(review, key=lambda e: -int(e["bytes"]))[:top]:
            print(f"  #{e['id']:<5} {fs.human(e['bytes']):>11}  {e['category']:15} {e['path']}  "
                  f"({e['reason']})")
    for note in plan.get("notes", []):
        print(f"\nNota: {note}")
    if plan.get("limits_hit"):
        print(f"\nAVISO: escaneo incompleto — {plan['limits_hit']}")
    if plan.get("excluded"):
        print(f"\nExcluidos por las reglas de seguridad: {len(plan['excluded'])} "
              "(lista en el plan, clave 'excluded').")
    print("\nLo que va a la papelera libera espacio solo cuando se vacía la papelera.")
    print(f"DIGEST: {plan_digest(plan)}")


# --------------------------------------------------------------------------- subcommands


def cmd_plan(a: argparse.Namespace) -> int:
    cats = set(CATEGORIES) if a.categories == "all" else set(a.categories.split(","))
    unknown = cats - set(CATEGORIES)
    if unknown:
        print(f"error: categorías desconocidas: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    try:
        bounds = fs.Bounds.build(a.root or None, a.agent_home, explicit_roots=a.root)
    except fs.BoundsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    budget = fs.Budget(a.max_seconds, a.max_files)
    p = Planner(a, bounds, budget)
    order = ["pkg-cache", "tool-cache", "thumbnails", "trash-old", "docker", "user-cache",
             "logs"]
    for cat in order:
        budget.phase(cat)
        if cat in cats and not budget.exhausted:
            getattr(p, cat.replace("-", "_"))()
    walk_cats = cats & {"large-files", "old-downloads", "duplicates", "build-artifacts"}
    budget.phase("recorrido del home")
    if walk_cats and not budget.exhausted:
        p.home_walk(walk_cats)
    out = a.out or os.path.join(fs.plans_dir(), f"cleanup-{time.strftime('%Y%m%d-%H%M%S')}.json")
    plan = {
        "schema": SCHEMA, "created": fs.now_iso(), "home": bounds.home, "roots": bounds.roots,
        "agent_homes": bounds.agent, "categories": sorted(cats),
        "params": {k: getattr(a, k) for k in ("cache_days", "trash_days", "log_days",
                                              "downloads_days", "large_mb", "dup_min_mb",
                                              "project_days", "max_seconds", "max_files")},
        "limits_hit": budget.hit, "notes": p.notes, "entries": p.entries,
        "excluded": p.excluded[:500], "totals": totals(p.entries),
    }
    fs.write_json(out, plan)
    print_summary(plan, out, a.top)
    return 0


def cmd_summary(a: argparse.Namespace) -> int:
    print_summary(fs.load_json(a.plan, SCHEMA), a.plan, a.top)
    return 0


def cmd_select(a: argparse.Namespace) -> int:
    plan = fs.load_json(a.plan, SCHEMA)
    ids = {int(x) for x in a.ids.split(",") if x.strip()} if a.ids else set()
    changed = 0
    for e in plan["entries"]:
        hit = (e["id"] in ids) or (a.category and e["category"] == a.category) or \
              (a.risk and e["risk"] == a.risk) or a.none
        if not hit:
            continue
        want = False if (a.off or a.none) else True
        if want and e["method"] == "suggest":
            print(f"aviso: #{e['id']} es solo una sugerencia; no se puede aplicar", file=sys.stderr)
            continue
        if want and e["category"] in REPORT_ONLY and e["id"] not in ids:
            print(f"aviso: #{e['id']} ({e['category']}) solo se marca por id explícito",
                  file=sys.stderr)
            continue
        if e.get("selected") != want:
            e["selected"] = want
            changed += 1
    plan["totals"] = totals(plan["entries"])
    fs.write_json(a.plan, plan)
    print(f"{changed} entradas cambiadas.\n")
    print_summary(plan, a.plan, a.top)
    return 0


def _tool_refusal(e: dict) -> str | None:
    key = e.get("tool")
    if key not in TOOLS:
        return "herramienta desconocida"
    tool = TOOLS[key]
    expected = list(tool.argv)
    if key == "trash-empty":
        argv = e.get("argv") or []
        if len(argv) != 1 or not str(argv[0]).isdigit() or int(argv[0]) < 1:
            return "argumentos inválidos para trash-empty"
        expected = [str(int(argv[0]))]
    if e.get("argv") != expected:
        return "el comando del plan no coincide con la tabla interna"
    binary = tool_binary(tool)
    if not binary or binary != e.get("binary"):
        return "el binario de la herramienta cambió o desapareció"
    return None


def _run_tool(e: dict) -> tuple[bool, str, dict]:
    """Run an entry that already passed _tool_refusal (argv rebuilt from TOOLS)."""
    binary = e["binary"]
    argv = list(e["argv"])
    try:
        proc = subprocess.run([binary, *argv], capture_output=True, text=True,
                              timeout=1800, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"no se pudo ejecutar: {exc}", {"command": shlex.join([binary, *argv])}
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
    rec = {"command": shlex.join([binary, *argv]), "returncode": proc.returncode,
           "output_tail": tail}
    if proc.returncode != 0:
        return False, f"terminó con código {proc.returncode}", rec
    return True, "", rec


DIGEST_MISMATCH = ("error: el plan cambió o el digest no es el suyo. Ejecuta `summary PLAN`, "
                   "muéstraselo al usuario y usa el DIGEST que imprime solo tras su confirmación.")


class _Stop(Exception):
    """The journal could not be written: stop before touching anything else."""


def cmd_apply(a: argparse.Namespace) -> int:
    plan = fs.load_json(a.plan, SCHEMA)
    if a.confirm != plan_digest(plan):
        print(DIGEST_MISMATCH, file=sys.stderr)
        return 2
    try:
        bounds = fs.Bounds.build(plan.get("roots"), a.agent_home, explicit_roots=a.root)
        trash = fs.Trash(a.trash_backend)
    except (fs.BoundsError, fs.TrashError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out = f"{os.path.splitext(a.plan)[0]}.journal-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    try:
        journal = fs.Journal(out, {"schema": RESULT_SCHEMA, "created": fs.now_iso(),
                                   "plan": os.path.abspath(a.plan)})
    except fs.JournalError as exc:
        print(f"error: sin diario no se toca nada: {exc}", file=sys.stderr)
        return 1

    def jot(record: dict) -> None:
        try:
            journal.append(record)
        except fs.JournalError as exc:
            raise _Stop(str(exc)) from exc

    done: list[dict] = []
    skipped: list[dict] = []
    seen: set[str] = set()
    stopped = None
    try:
        for e in plan["entries"]:
            if not e.get("selected"):
                continue
            base = {"id": e.get("id"), "category": e.get("category"), "path": e.get("path"),
                    "bytes": e.get("bytes")}
            reason, method = None, e.get("method")
            if method == "suggest":
                reason = "solo sugerencia; no se ejecuta"
            elif method == "tool":
                reason = _tool_refusal(e)
            elif method != "trash" or not isinstance(e.get("path"), str):
                reason = "entrada inválida"
            else:
                real = bounds.resolve(e["path"])
                if real in seen:
                    reason = "duplicada en el plan"
                seen.add(real)
                reason = reason or bounds.refusal(real)
                if not reason:
                    ok, why = fs.fingerprint_matches(real, e.get("fingerprint"),
                                                     bounds.stats_cache.get(real))
                    reason = None if ok else why
                if not reason:
                    try:
                        tdir, top = fs.trash_location(real, bounds.home)
                    except (OSError, fs.TrashError) as exc:
                        reason = f"sin papelera posible: {exc}"
            if reason:
                skipped.append({**base, "reason": reason})
                jot({"op": "skip", **base, "reason": reason})
                continue
            seq = journal.next_seq()
            if method == "tool":
                jot({"op": "tool", "seq": seq, "state": "pending", **base,
                     "tool": e["tool"], "argv": e["argv"]})
                ok, why, rec = _run_tool(e)
                jot({"seq": seq, "state": "done" if ok else "failed", **rec,
                     **({} if ok else {"reason": why})})
                (done if ok else skipped).append({**base, "method": "tool", **rec,
                                                  **({} if ok else {"reason": why})})
                continue
            jot({"op": "trash", "seq": seq, "state": "pending", **base, "path": real,
                 "trash_dir": tdir, "top": top, "since": time.time() - 1})
            try:
                rec = trash.put(real)
            except fs.TrashError as exc:
                jot({"seq": seq, "state": "failed", "reason": str(exc)})
                skipped.append({**base, "reason": f"sin papelera posible: {exc}"})
                continue
            jot({"seq": seq, "state": "done", "trash": rec})
            done.append({**base, "method": "trash", "trash": rec})
    except _Stop as exc:
        stopped = str(exc)
    finally:
        journal.close()
    trashed = [d for d in done if d["method"] == "trash"]
    print(f"A la papelera: {len(trashed)} elementos, "
          f"{fs.human(sum(int(d['bytes'] or 0) for d in trashed))}")
    for d in trashed:
        print(f"  #{d['id']} {d['path']} -> {d['trash'].get('files') or 'papelera (gio)'}")
    for d in (d for d in done if d["method"] == "tool"):
        print(f"Comando ejecutado: {d['command']} (código {d['returncode']})")
    print(f"Omitidos: {len(skipped)}")
    for s_ in skipped:
        print(f"  #{s_['id']} {s_['path']}: {s_['reason']}")
    print(f"\nDiario: {out}")
    print(f"Restaurar: python3 {os.path.abspath(__file__)} restore {out}  "
          "(o desde la papelera del gestor de archivos)")
    if stopped:
        print(f"\nDETENIDO: no se pudo escribir el diario ({stopped}); no se tocó nada más.",
              file=sys.stderr)
        return 1
    return 0


def cmd_restore(a: argparse.Namespace) -> int:
    _header, records = fs.read_journal(a.journal, RESULT_SCHEMA)
    ids = {int(x) for x in a.ids.split(",")} if a.ids else None
    failed = 0
    for op in fs.journal_ops(records):
        if op.get("op") != "trash" or op["outcome"] == "failed" or \
                (ids is not None and op.get("id") not in ids):
            continue
        original = op.get("path")
        if op["outcome"] == "done":
            record = op["result"].get("trash") or {}
        elif isinstance(original, str) and os.path.lexists(original):
            # Died after writing the .trashinfo but before the move: drop the
            # orphan metadata (it points at nothing in files/).
            info = fs.find_trashinfo(original, op.get("trash_dir") or "", op.get("top"),
                                     float(op.get("since") or 0))
            name = os.path.basename(info)[: -len(".trashinfo")] if info else None
            if name and not os.path.lexists(os.path.join(op["trash_dir"], "files", name)):
                os.unlink(info)
            print(f"sin cambios: {original} (no llegó a moverse)")
            continue
        else:  # died between the two records: find the item by its .trashinfo
            info = fs.find_trashinfo(original, op.get("trash_dir") or "", op.get("top"),
                                     float(op.get("since") or 0))
            name = os.path.basename(info)[: -len(".trashinfo")] if info else None
            record = {"original": original, "info": info,
                      "files": os.path.join(op["trash_dir"], "files", name) if name else None}
        ok, why = fs.restore_from_trash(record)
        print(f"{'restaurado' if ok else 'NO restaurado'}: {original}{'' if ok else ' — ' + why}")
        failed += 0 if ok else 1
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="janitor_cleanup.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="escaneo de solo lectura; escribe el plan")
    p.add_argument("--categories", default="all",
                   help="lista separada por comas o 'all': " + ",".join(CATEGORIES))
    p.add_argument("--root", action="append", help="raíz permitida (por defecto el home)")
    p.add_argument("--agent-home", action="append", help="home de agente adicional a proteger")
    p.add_argument("--cache-days", type=int, default=30)
    p.add_argument("--trash-days", type=int, default=30)
    p.add_argument("--log-days", type=int, default=30)
    p.add_argument("--downloads-days", type=int, default=90)
    p.add_argument("--project-days", type=int, default=60)
    p.add_argument("--large-mb", type=int, default=500)
    p.add_argument("--dup-min-mb", type=int, default=1)
    p.add_argument("--dup-max-gb", type=int, default=20, help="tope de bytes a hashear")
    p.add_argument("--max-depth", type=int, default=12)
    p.add_argument("--max-report", type=int, default=200, help="tope por categoría de informe")
    p.add_argument("--max-seconds", type=float, default=180)
    p.add_argument("--max-files", type=int, default=1_000_000)
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--out", help="ruta del plan (por defecto en el home del agente)")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("summary", help="resumen y digest de un plan")
    p.add_argument("plan")
    p.add_argument("--top", type=int, default=15)
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("select", help="marcar/desmarcar entradas del plan")
    p.add_argument("plan")
    p.add_argument("--ids", help="ids separados por comas")
    p.add_argument("--category")
    p.add_argument("--risk", choices=["safe", "review"])
    p.add_argument("--off", action="store_true", help="desmarcar en vez de marcar")
    p.add_argument("--none", action="store_true", help="desmarcar todo")
    p.add_argument("--top", type=int, default=15)
    p.set_defaults(func=cmd_select)

    p = sub.add_parser("apply", help="ejecuta las entradas marcadas del plan")
    p.add_argument("plan")
    p.add_argument("--confirm", required=True, help="DIGEST mostrado al usuario")
    p.add_argument("--root", action="append", help="raíz fuera del home, repetida a propósito")
    p.add_argument("--agent-home", action="append")
    p.add_argument("--trash-backend", choices=["auto", "gio", "python"], default="auto")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("restore", help="devuelve a su sitio lo que movió un apply")
    p.add_argument("journal", help="diario .jsonl que imprimió apply")
    p.add_argument("--ids")
    p.set_defaults(func=cmd_restore)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
