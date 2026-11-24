#!/usr/bin/env python3
"""Deterministic project scaffolding for the janitor-project-create skill.

Four subcommands, each a separate step the agent runs and reports:

    plan     read-only: validates the intake, detects tools, prints the tree, every
             file's purpose and every command, and writes the plan JSON (never into
             the target directory).
    apply    creates the project from a plan, ONLY inside the new target directory,
             then runs the selected dependency install (network) and git init/commit.
    verify   runs the project's own lint and tests offline and reports per step.
    publish  creates the remote repository and pushes (network, outward-facing).

Safety rules enforced here, not left to the prompt: the target must not exist or be
an empty, non-symlink directory; files are created with O_EXCL|O_NOFOLLOW through
directory file descriptors (no overwrite, no escaping through symlinks); a plan whose
files or commands differ from what the inputs re-derive is refused (a hand-edited plan
cannot inject paths or commands); network commands run only when the plan selected
them; git identity is never invented; sudo is never called.

Stdlib only. Templates are plain files with ``{{UPPER_CASE}}`` placeholders.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = 1
SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL_DIR / "templates"
TYPE_DIRS = {"python": "python-uv", "node": "node-ts", "ops": "ops"}
PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
REMOTE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
CMD_TIMEOUT = 900
VERSION_TIMEOUT = 15
TAIL_LINES = 40
TAIL_CHARS = 4000

EXIT_OK, EXIT_FAILED, EXIT_REFUSED, EXIT_UNVERIFIED = 0, 1, 2, 3


class Refused(Exception):
    """The request breaks a rule; the message is shown to the user (Spanish)."""


# ---------------------------------------------------------------------------
# Host helpers
# ---------------------------------------------------------------------------

def find_tool(name: str, path: str | None = None) -> str | None:
    """Resolve *name* against PATH only."""
    for directory in (path if path is not None else os.environ.get("PATH", "")).split(os.pathsep):
        if not directory:
            continue
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def tail(text: str) -> str:
    lines = text.strip().splitlines()[-TAIL_LINES:]
    return "\n".join(lines)[-TAIL_CHARS:]


def run_cmd(argv: list[str], cwd: Path, timeout: int = CMD_TIMEOUT,
            extra_env: dict | None = None) -> dict:
    """Run *argv* without a shell. Returns rc + combined output tail."""
    exe = find_tool(argv[0])
    if exe is None:
        return {"argv": argv, "rc": None, "output_tail": f"{argv[0]} no está en PATH"}
    env = dict(os.environ, **(extra_env or {}))
    try:
        proc = subprocess.run([exe, *argv[1:]], cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, env=env, stdin=subprocess.DEVNULL,
                              errors="replace")
    except subprocess.TimeoutExpired:
        return {"argv": argv, "rc": None, "output_tail": f"tiempo agotado tras {timeout}s"}
    except OSError as exc:
        return {"argv": argv, "rc": None, "output_tail": str(exc)}
    return {"argv": argv, "rc": proc.returncode, "output_tail": tail(proc.stdout + "\n" + proc.stderr)}


def tool_version(name: str) -> dict | None:
    exe = find_tool(name)
    if exe is None:
        return None
    flag = "-V" if name == "shellcheck" else "--version"
    try:
        proc = subprocess.run([exe, flag], capture_output=True, text=True, timeout=VERSION_TIMEOUT,
                              stdin=subprocess.DEVNULL, errors="replace")
        first = (proc.stdout or proc.stderr).strip().splitlines()
        if name == "shellcheck":
            first = [ln for ln in first if ln.startswith("version:")] or first
        version = first[0] if first else "?"
    except (OSError, subprocess.TimeoutExpired):
        version = "?"
    return {"path": exe, "version": version}


def git_identity(cwd: Path) -> tuple[str, str] | None:
    """The configured git user.name/user.email, or None. Never invented."""
    values = []
    for key in ("user.name", "user.email"):
        res = run_cmd(["git", "config", "--get", key], cwd=cwd, timeout=VERSION_TIMEOUT)
        value = res["output_tail"].strip() if res["rc"] == 0 else ""
        if not value:
            return None
        values.append(value.splitlines()[0])
    return values[0], values[1]


NO_IDENTITY = ("Git no tiene identidad configurada (user.name y user.email). Janitor no "
               "inventa una: configúrala tú con `git config --global user.name \"Nombre\"` y "
               "`git config --global user.email correo@dominio` y vuelve a lanzar el plan.")


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render(text: str, variables: dict[str, str], where: str) -> str:
    def sub(match: re.Match) -> str:
        key = match.group(1)
        if key not in variables:
            raise ValueError(f"placeholder desconocido {{{{{key}}}}} en {where}")
        return variables[key]
    return PLACEHOLDER.sub(sub, text)


def output_path(rel_template: str) -> str:
    """``dot-github/workflows/ci.yml.tmpl`` -> ``.github/workflows/ci.yml``."""
    if not rel_template.endswith(".tmpl"):
        raise ValueError(f"plantilla sin sufijo .tmpl: {rel_template}")
    parts = rel_template[: -len(".tmpl")].split("/")
    return "/".join("." + p[4:] if p.startswith("dot-") else p for p in parts)


def template_sources(type_dir: Path, kind: str) -> dict[str, Path]:
    """Output-path template -> source file. Later roots override earlier ones."""
    roots = [TEMPLATES / "common" / "files", type_dir / "files", type_dir / "variants" / kind]
    sources: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for src in sorted(root.rglob("*")):
            if src.is_file() and not src.name.endswith((".pyc",)) and "__pycache__" not in src.parts:
                sources[output_path(src.relative_to(root).as_posix())] = src
    return sources


# ---------------------------------------------------------------------------
# Intake validation
# ---------------------------------------------------------------------------

def clean_text(label: str, value: str | None, limit: int = 300) -> str:
    value = (value or "").strip()
    if len(value) < 10:
        raise Refused(f"{label}: falta o es demasiado vago (mínimo 10 caracteres).")
    if len(value) > limit:
        raise Refused(f"{label}: más de {limit} caracteres; resúmelo en una frase.")
    if any(ord(c) < 32 for c in value):
        raise Refused(f"{label}: una sola línea, sin caracteres de control.")
    if "{{" in value or "}}" in value:
        raise Refused(f"{label}: no puede contener '{{{{' ni '}}}}'.")
    return value


def check_target(target: Path) -> str:
    """Return 'missing' or 'empty'; raise Refused otherwise. Never follows a symlink target."""
    if target.is_symlink():
        raise Refused(f"El destino {target} es un enlace simbólico; elige un directorio real.")
    if target.exists():
        if not target.is_dir():
            raise Refused(f"El destino {target} existe y no es un directorio.")
        if any(target.iterdir()):
            raise Refused(f"El destino {target} no está vacío. No se escribe sobre nada existente.")
        return "empty"
    parent = target.parent
    if not parent.is_dir():
        raise Refused(f"El directorio padre {parent} no existe; créalo tú o elige otro destino.")
    return "missing"


def validate_rel(path: str) -> None:
    """A plan path must be relative, normalised and stay inside the target."""
    if not path or path.startswith(("/", "\\")) or "\\" in path or ":" in path.split("/")[0]:
        raise Refused(f"Ruta fuera del destino en el plan: {path!r}")
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts) or parts[0] == ".git":
        raise Refused(f"Ruta fuera del destino en el plan: {path!r}")


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def resolve_inputs(args: argparse.Namespace, cwd: Path) -> dict:
    if args.type not in TYPE_DIRS:
        raise Refused(f"Tipo no soportado: {args.type}. Tipos: {', '.join(TYPE_DIRS)}.")
    type_info = load_json(TEMPLATES / TYPE_DIRS[args.type] / "type.json")
    kind = args.kind or type_info["kinds"][0]
    if kind not in type_info["kinds"]:
        raise Refused(f"Variante {kind!r} no existe para {args.type}: {', '.join(type_info['kinds'])}.")
    name = (args.name or "").strip()
    if not NAME_RE.match(name) or len(name) > 64:
        raise Refused("Nombre inválido: minúsculas, dígitos y guiones (ej. 'inventario-red').")
    common = load_json(TEMPLATES / "common" / "common.json")
    if args.license not in common["licenses"]:
        raise Refused(f"Licencia no soportada: {args.license}. Opciones: {', '.join(common['licenses'])}.")
    if not args.target:
        raise Refused("Falta el directorio destino (--target).")
    target = Path(os.path.abspath(os.path.expanduser(args.target)))
    check_target(target)
    pm = None
    if args.type == "node":
        pm = args.package_manager
        if pm == "auto":
            pm = "npm" if find_tool("npm") or not find_tool("pnpm") else "pnpm"
        if pm not in type_info["package_managers"]:
            raise Refused(f"Gestor de paquetes no soportado: {pm}.")
    elif args.package_manager not in (None, "auto"):
        raise Refused("--package-manager solo aplica a proyectos node.")
    remote = None
    if args.remote:
        if not REMOTE_RE.match(args.remote):
            raise Refused("--remote debe ser PROPIETARIO/NOMBRE de GitHub.")
        remote = args.remote
    if find_tool("git") is None:
        raise Refused("git no está en PATH; sin git no hay proyecto.")
    identity = git_identity(target.parent if target.parent.is_dir() else cwd)
    if identity is None:
        raise Refused(NO_IDENTITY)
    return {
        "type": args.type,
        "kind": kind,
        "name": name,
        "target": str(target),
        "problem": clean_text("Problema (--problem)", args.problem),
        "users": clean_text("Usuarios (--users)", args.users),
        "license": args.license,
        "package_manager": pm,
        "install": bool(args.install),
        "remote": remote,
        "visibility": args.visibility,
        "author": identity[0],
        "year": args.year or _dt.date.today().year,
    }


def build_variables(inputs: dict, pins: dict, common: dict) -> dict[str, str]:
    lic = common["licenses"][inputs["license"]]
    pm = inputs["package_manager"] or ""
    v = {
        "NAME": inputs["name"],
        "PY_PACKAGE": inputs["name"].replace("-", "_"),
        "PROBLEM": inputs["problem"],
        "USERS": inputs["users"],
        "AUTHOR": inputs["author"],
        "YEAR": str(inputs["year"]),
        "DESCRIPTION_TOML": json.dumps(inputs["problem"], ensure_ascii=False),
        "DESCRIPTION_PY": json.dumps(inputs["problem"], ensure_ascii=False),
        "DESCRIPTION_JSON": json.dumps(inputs["problem"], ensure_ascii=False),
        "GITIGNORE_SECRETS": (TEMPLATES / "common" / "gitignore-secrets.txt").read_text(encoding="utf-8"),
        "LICENSE_README": (f"{lic['spdx']}. Ver `LICENSE`." if lic["spdx"]
                           else "Sin licencia: todos los derechos reservados."),
        "PY_LICENSE_LINES": (f'license = "{lic["spdx"]}"\nlicense-files = ["LICENSE"]\n'
                             if lic["spdx"] else ""),
        "NPM_LICENSE": lic["spdx"] or "UNLICENSED",
        "PM": pm,
        "LOCKFILE": {"npm": "package-lock.json", "pnpm": "pnpm-lock.yaml"}.get(pm, ""),
        "PM_CI_INSTALL": {"npm": "npm ci", "pnpm": "pnpm install --frozen-lockfile"}.get(pm, ""),
        "PM_REQUIREMENT": {"npm": "npm (incluido con Node.js).",
                           "pnpm": f"pnpm {pins.get('PNPM', '')} (`npm install --global pnpm@{pins.get('PNPM', '')}`)."
                           }.get(pm, ""),
        "PM_FIELD": f'  "packageManager": "pnpm@{pins["PNPM"]}",\n' if pm == "pnpm" else "",
        "CI_PM_SETUP": (f"      - name: Instalar pnpm\n        run: npm install --global pnpm@{pins['PNPM']}\n"
                        if pm == "pnpm" else ""),
        "NODE_USAGE": "",
    }
    if inputs["type"] == "node":
        if inputs["kind"] == "cli":
            v["NODE_USAGE"] = (f"```bash\n{pm} run build\nnode dist/src/main.js --help\n```\n\n"
                               f"`{pm} link` (o `npm link`) instala el comando `{inputs['name']}` en local.")
        else:
            v["NODE_USAGE"] = (f"```bash\n{pm} run build\nPORT=3000 {pm} start\n"
                               "curl http://127.0.0.1:3000/health\n```\n\n"
                               "`HOST` (por defecto 127.0.0.1) y `PORT` (por defecto 3000) se leen del entorno.")
    for key, action in common["actions"].items():
        v[f"ACTION_{key.upper()}"] = action
    for key, value in pins.items():
        v[f"PIN_{key}"] = str(value)
    return v


def render_files(inputs: dict, variables: dict, type_dir: Path, type_info: dict,
                 common: dict) -> list[dict]:
    purposes = {**common["purposes"], **type_info["purposes"]}
    files = []
    for tpath, src in template_sources(type_dir, inputs["kind"]).items():
        out = render(tpath, variables, f"ruta {tpath}")
        purpose = purposes.get(tpath)
        if purpose is None:
            raise ValueError(f"la plantilla {tpath} no declara propósito en type.json")
        content = render(src.read_text(encoding="utf-8"), variables, tpath)
        mode = 0o755 if src.stat().st_mode & stat.S_IXUSR else 0o644
        files.append({"path": out, "template": src.relative_to(TEMPLATES).as_posix(),
                      "purpose": render(purpose, variables, tpath), "mode": mode, "content": content})
    lic = common["licenses"][inputs["license"]]
    if lic["template"]:
        src = TEMPLATES / "common" / lic["template"]
        files.append({"path": "LICENSE", "template": src.relative_to(TEMPLATES).as_posix(),
                      "purpose": common["purposes"]["LICENSE"], "mode": 0o644,
                      "content": render(src.read_text(encoding="utf-8"), variables, "LICENSE")})
    for f in files:
        f["sha256"] = hashlib.sha256(f["content"].encode("utf-8")).hexdigest()
        f["bytes"] = len(f["content"].encode("utf-8"))
    return sorted(files, key=lambda f: f["path"])


def build_commands(inputs: dict, variables: dict, type_info: dict) -> list[dict]:
    cmds = []
    install = type_info.get("install")
    if install:
        cmds.append({
            "id": "install", "phase": "install", "network": True, "selected": inputs["install"],
            "argv": [render(a, variables, "install") for a in install["argv"]],
            "purpose": render(install["purpose"], variables, "install"),
            "creates": [render(c, variables, "install") for c in install["creates"]],
        })
    cmds += [
        {"id": "git-init", "phase": "git", "network": False, "selected": True,
         "argv": ["git", "init", "--initial-branch=main"],
         "purpose": "Repositorio git en la rama main.", "creates": [".git/"]},
        {"id": "git-add", "phase": "git", "network": False, "selected": True,
         "argv": ["git", "add", "--all"],
         "purpose": "Prepara todo lo no ignorado por .gitignore.", "creates": []},
        {"id": "git-commit", "phase": "git", "network": False, "selected": True,
         "argv": ["git", "commit", "--message", f"chore: esqueleto inicial de {inputs['name']}"],
         "purpose": "Primer commit con la identidad git ya configurada.", "creates": []},
    ]
    if inputs["remote"]:
        cmds += [
            {"id": "remote-create", "phase": "publish", "network": True, "selected": True,
             "argv": ["gh", "repo", "create", inputs["remote"], f"--{inputs['visibility']}",
                      "--source", ".", "--remote", "origin"],
             "purpose": f"Crea el repositorio {inputs['visibility']} en GitHub y lo añade como origin.",
             "creates": []},
            {"id": "remote-push", "phase": "publish", "network": True, "selected": True,
             "argv": ["git", "push", "--set-upstream", "origin", "main"],
             "purpose": "Sube la rama main.", "creates": []},
        ]
    return cmds


def build_plan(inputs: dict, detect: bool = True) -> dict:
    type_dir = TEMPLATES / TYPE_DIRS[inputs["type"]]
    type_info = load_json(type_dir / "type.json")
    pins_doc = load_json(type_dir / "pins.json")
    common = load_json(TEMPLATES / "common" / "common.json")
    variables = build_variables(inputs, pins_doc["pins"], common)
    files = render_files(inputs, variables, type_dir, type_info, common)
    commands = build_commands(inputs, variables, type_info)
    verify_steps = [{"id": s["id"], "argv": [render(a, variables, "verify") for a in s["argv"]],
                     "needs": [render(n, variables, "verify") for n in s["needs"]]}
                    for s in type_info["verify"]]
    tool_names = [render(t, variables, "tools") for t in type_info["tools"]] + ["git"]
    if inputs["remote"]:
        tool_names.append("gh")
    plan = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "inputs": inputs,
        "type_title": type_info["title"],
        "pins": {"refreshed": pins_doc["refreshed"], "file": (type_dir / "pins.json").relative_to(SKILL_DIR).as_posix(),
                 **pins_doc["pins"]},
        "files": [{k: f[k] for k in ("path", "purpose", "template", "mode", "sha256", "bytes")} for f in files],
        "dirs": sorted({str(Path(f["path"]).parent) for f in files} - {"."}),
        "commands": commands,
        "verify": verify_steps,
        "deps_present": [render(p, variables, "deps") for p in type_info["deps_present"]],
        "tools": {},
        "warnings": [],
    }
    if detect:
        plan["tools"] = {name: tool_version(name) for name in dict.fromkeys(tool_names)}
        plan["warnings"] = plan_warnings(plan)
    plan["_contents"] = {f["path"]: f["content"] for f in files}
    return plan


def plan_warnings(plan: dict) -> list[str]:
    inputs, tools, warnings = plan["inputs"], plan["tools"], []
    for name, info in tools.items():
        if info is None:
            warnings.append(f"{name} no está en PATH: los pasos que lo usan quedarán sin verificar.")
    install = next((c for c in plan["commands"] if c["id"] == "install"), None)
    if install and not install["selected"]:
        warnings.append("Instalación de dependencias NO seleccionada: no habrá lockfile en el primer "
                        "commit, la CI fallará hasta commitearlo y `verify` no podrá pasar.")
    if inputs["type"] == "python" and tools.get("uv"):
        res = run_cmd(["uv", "python", "find", "--no-python-downloads", plan["pins"]["PYTHON"]],
                      cwd=Path(inputs["target"]).parent, timeout=VERSION_TIMEOUT)
        if res["rc"] != 0:
            warnings.append(f"uv no encuentra Python {plan['pins']['PYTHON']} instalado: `uv sync` lo "
                            "descargará (red).")
    if inputs["type"] == "node" and tools.get("node"):
        m = re.search(r"v?(\d+)", tools["node"]["version"])
        if m and int(m.group(1)) < int(plan["pins"]["NODE_MAJOR"]):
            warnings.append(f"Node local {tools['node']['version']} es menor que el exigido "
                            f"(>= {plan['pins']['NODE_MAJOR']}); engine-strict hará fallar la instalación.")
    if inputs["type"] == "node":
        other = "pnpm" if inputs["package_manager"] == "npm" else "npm"
        warnings.append(f"Gestor elegido: {inputs['package_manager']}"
                        f"{' (también hay ' + other + ')' if find_tool(other) else ''}.")
    return warnings


def format_plan(plan: dict, plan_path: Path | None) -> str:
    i = plan["inputs"]
    state = "existe y está vacío" if Path(i["target"]).exists() else "se crea"
    lines = [f"PLAN: {i['name']} — {plan['type_title']} (variante {i['kind']})",
             f"Destino: {i['target']} ({state})",
             f"Problema: {i['problem']}",
             f"Usuarios: {i['users']}",
             f"Licencia: {i['license']} (titular: {i['author']}, {i['year']})"]
    if i["package_manager"]:
        lines.append(f"Gestor de paquetes: {i['package_manager']}")
    lines.append(f"Versiones fijadas ({plan['pins']['file']}, revisadas {plan['pins']['refreshed']}):")
    lines += [f"  {k} = {v}" for k, v in plan["pins"].items() if k not in ("refreshed", "file")]
    lines.append("Herramientas detectadas:")
    for name, info in plan["tools"].items():
        lines.append(f"  {name}: {info['version'] + ' (' + info['path'] + ')' if info else 'NO ENCONTRADO'}")
    lines.append(f"Archivos ({len(plan['files'])}):")
    lines += [f"  {f['path']}{' (ejecutable)' if f['mode'] & 0o111 else ''} — {f['purpose']}"
              for f in plan["files"]]
    lines.append("Comandos (en el destino, en este orden):")
    for c in plan["commands"]:
        if c["phase"] == "publish":
            tag = "RED, PUBLICACIÓN: paso aparte con su propia confirmación"
        elif c["network"]:
            tag = "RED, seleccionado" if c["selected"] else "RED, NO seleccionado: no se ejecuta"
        else:
            tag = "local"
        lines.append(f"  [{tag}] {' '.join(c['argv'])} — {c['purpose']}")
    lines.append("Verificación (verify, sin red): " + "; ".join(" ".join(s["argv"]) for s in plan["verify"]))
    if plan["warnings"]:
        lines.append("Avisos:")
        lines += [f"  - {w}" for w in plan["warnings"]]
    if plan_path:
        lines.append(f"Plan JSON: {plan_path}")
    return "\n".join(lines)


def default_plan_path(name: str) -> Path:
    home = os.environ.get("HERMES_HOME", "").strip()
    if not home:
        raise Refused("HERMES_HOME no está definido: indica dónde guardar el plan con --output.")
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(home) / "janitor" / "project-create" / f"{name}-{stamp}.json"


def cmd_plan(args: argparse.Namespace) -> int:
    inputs = resolve_inputs(args, Path.cwd())
    plan = build_plan(inputs)
    plan.pop("_contents")
    out = Path(os.path.abspath(args.output)) if args.output else default_plan_path(inputs["name"])
    target = Path(inputs["target"])
    if out == target or target in out.parents:
        raise Refused("El plan no puede guardarse dentro del directorio destino.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(format_plan(plan, out))
    return EXIT_OK


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def load_plan(path: str) -> dict:
    try:
        plan = load_json(Path(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise Refused(f"No se puede leer el plan {path}: {exc}") from exc
    if plan.get("schema_version") != SCHEMA_VERSION or "inputs" not in plan:
        raise Refused("El archivo no es un plan de janitor-project-create.")
    return plan


def rederive(plan: dict) -> dict:
    """Validate paths, then rebuild from the inputs and require an identical result."""
    for f in plan.get("files", []):
        validate_rel(str(f.get("path", "")))
    inputs = plan["inputs"]
    if inputs.get("type") not in TYPE_DIRS:
        raise Refused("Tipo de proyecto desconocido en el plan.")
    if not NAME_RE.match(str(inputs.get("name", ""))):
        raise Refused("Nombre inválido en el plan.")
    if not os.path.isabs(str(inputs.get("target", ""))):
        raise Refused("El destino del plan no es una ruta absoluta.")
    try:
        fresh = build_plan(inputs, detect=False)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise Refused(f"El plan no se puede reconstruir: {exc}") from exc
    keys = ("path", "mode", "sha256")
    if ([{k: f.get(k) for k in keys} for f in plan["files"]]
            != [{k: f[k] for k in keys} for f in fresh["files"]]
            or plan.get("commands") != fresh["commands"]
            or plan.get("verify") != fresh["verify"]):
        raise Refused("El plan fue modificado o las plantillas cambiaron desde que se generó. "
                      "Vuelve a ejecutar `plan` y confirma el plan nuevo.")
    return fresh


def _open_dir(name: str, dir_fd: int) -> int:
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)


def write_tree(target: Path, files: list[dict], contents: dict[str, str]) -> list[str]:
    """Create *target* (or use it if empty) and every file, never following symlinks."""
    check_target(target)
    parent_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    created = []
    try:
        try:
            os.mkdir(target.name, 0o755, dir_fd=parent_fd)
        except FileExistsError:
            pass
        try:
            root_fd = _open_dir(target.name, parent_fd)
        except OSError as exc:
            raise Refused(f"El destino {target} no es un directorio real: {exc}") from exc
        try:
            if os.listdir(root_fd):
                raise Refused(f"El destino {target} dejó de estar vacío; no se escribe nada.")
            for f in files:
                parts = f["path"].split("/")
                fds = [root_fd]
                try:
                    for comp in parts[:-1]:
                        try:
                            os.mkdir(comp, 0o755, dir_fd=fds[-1])
                        except FileExistsError:
                            pass
                        fds.append(_open_dir(comp, fds[-1]))
                    fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 f["mode"], dir_fd=fds[-1])
                    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                        fh.write(contents[f["path"]])
                        os.fchmod(fh.fileno(), f["mode"])
                finally:
                    for d in fds[1:]:
                        os.close(d)
                created.append(f["path"])
        finally:
            os.close(root_fd)
    finally:
        os.close(parent_fd)
    return created


def cmd_apply(args: argparse.Namespace) -> int:
    if not args.confirmed:
        raise Refused("apply exige --confirmed: muestra el plan al usuario y espera su confirmación.")
    plan = load_plan(args.plan)
    fresh = rederive(plan)
    target = Path(plan["inputs"]["target"])
    check_target(target)
    if find_tool("git") is None:
        raise Refused("git no está en PATH.")
    if git_identity(target.parent) is None:
        raise Refused(NO_IDENTITY)
    print(f"Creando {len(fresh['files'])} archivos en {target}", file=sys.stderr)
    created = write_tree(target, fresh["files"], fresh["_contents"])
    result = {"target": str(target), "files_created": created, "commands": [], "status": "ok"}
    for cmd in fresh["commands"]:
        if cmd["phase"] == "publish":
            continue
        if not cmd["selected"]:
            result["commands"].append({"id": cmd["id"], "argv": cmd["argv"], "status": "not_selected"})
            continue
        print(f"Ejecutando: {' '.join(cmd['argv'])}", file=sys.stderr)
        res = run_cmd(cmd["argv"], cwd=target)
        res.update(id=cmd["id"], status="ok" if res["rc"] == 0 else "failed")
        result["commands"].append(res)
        if res["rc"] != 0:
            result["status"] = f"{cmd['id']}_failed"
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return EXIT_FAILED
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_OK


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

# Keep pnpm from fetching the packageManager version during an offline verify.
PNPM_OFFLINE_ENV = {"npm_config_manage_package_manager_versions": "false",
                    "pnpm_config_manage_package_manager_versions": "false"}


def cmd_verify(args: argparse.Namespace) -> int:
    plan = load_plan(args.plan)
    fresh = rederive(plan)
    target = Path(plan["inputs"]["target"])
    if target.is_symlink() or not target.is_dir():
        raise Refused(f"{target} no existe o no es un directorio: ejecuta apply primero.")
    steps = []
    env = PNPM_OFFLINE_ENV if plan["inputs"].get("package_manager") == "pnpm" else {}
    install = next((c for c in fresh["commands"] if c["id"] == "install"), None)
    if args.install:
        if install is None:
            raise Refused("Este tipo de proyecto no tiene paso de instalación.")
        res = run_cmd(install["argv"], cwd=target)
        steps.append({"id": "install", "command": " ".join(install["argv"]), "rc": res["rc"],
                      "status": "pass" if res["rc"] == 0 else "fail", "output_tail": res["output_tail"],
                      "network": True})
    missing_deps = [p for p in fresh["deps_present"] if not (target / p).exists()]
    for step in fresh["verify"]:
        entry = {"id": step["id"], "command": " ".join(step["argv"])}
        absent = [n for n in step["needs"] if find_tool(n) is None]
        if absent:
            entry.update(status="not_verified", reason=f"{', '.join(absent)} no está en PATH")
        elif missing_deps:
            entry.update(status="not_verified",
                         reason=(f"dependencias no instaladas (falta {', '.join(missing_deps)}); "
                                 f"requiere `{' '.join(install['argv'])}` con red"))
        else:
            res = run_cmd(step["argv"], cwd=target, extra_env=env)
            entry.update(rc=res["rc"], status="pass" if res["rc"] == 0 else "fail",
                         output_tail=res["output_tail"])
        steps.append(entry)
    statuses = {s["status"] for s in steps}
    overall = "failed" if "fail" in statuses else ("passed" if statuses == {"pass"} else "unverified")
    report = {"target": str(target), "overall": overall, "steps": steps}
    if find_tool("git") and (target / ".git").is_dir():
        res = run_cmd(["git", "status", "--porcelain"], cwd=target, timeout=VERSION_TIMEOUT)
        report["uncommitted"] = [ln for ln in res["output_tail"].splitlines() if ln.strip()]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return {"passed": EXIT_OK, "failed": EXIT_FAILED}.get(overall, EXIT_UNVERIFIED)


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

def cmd_publish(args: argparse.Namespace) -> int:
    if not args.confirmed:
        raise Refused("publish exige --confirmed: crear un repositorio remoto y subir código "
                      "requiere una confirmación explícita y aparte del usuario.")
    plan = load_plan(args.plan)
    fresh = rederive(plan)
    cmds = [c for c in fresh["commands"] if c["phase"] == "publish"]
    if not cmds:
        raise Refused("El plan no seleccionó repositorio remoto (--remote). Nada que publicar.")
    target = Path(plan["inputs"]["target"])
    if target.is_symlink() or not (target / ".git").is_dir():
        raise Refused(f"{target} no es un repositorio git creado por apply.")
    if run_cmd(["git", "rev-parse", "--verify", "HEAD"], cwd=target)["rc"] != 0:
        raise Refused("El repositorio no tiene commits: apply no terminó.")
    if run_cmd(["git", "remote", "get-url", "origin"], cwd=target)["rc"] == 0:
        raise Refused("Ya existe un remoto 'origin'; no se crea otro.")
    if find_tool("gh") is None:
        raise Refused("gh no está en PATH; instala GitHub CLI y autentícate (`gh auth login`).")
    result = {"target": str(target), "commands": [], "status": "ok"}
    for cmd in cmds:
        res = run_cmd(cmd["argv"], cwd=target)
        res.update(id=cmd["id"], status="ok" if res["rc"] == 0 else "failed")
        result["commands"].append(res)
        if res["rc"] != 0:
            result["status"] = f"{cmd['id']}_failed"
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return EXIT_FAILED
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="project_create.py", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    pl = sub.add_parser("plan", help="plan de solo lectura")
    pl.add_argument("--type", required=True, choices=sorted(TYPE_DIRS))
    pl.add_argument("--kind", help="python: cli; node: cli|service; ops: ops")
    pl.add_argument("--name", required=True)
    pl.add_argument("--target", required=True)
    pl.add_argument("--problem", required=True, help="qué resuelve, una frase")
    pl.add_argument("--users", required=True, help="quién lo usa, una frase")
    pl.add_argument("--license", required=True)
    pl.add_argument("--package-manager", choices=["auto", "npm", "pnpm"])
    pl.add_argument("--install", action="store_true", help="seleccionar la instalación (red)")
    pl.add_argument("--remote", help="PROPIETARIO/NOMBRE en GitHub (publicación aparte)")
    pl.add_argument("--visibility", choices=["private", "public"], default="private")
    pl.add_argument("--year", type=int, help=argparse.SUPPRESS)
    pl.add_argument("--output", help="ruta del plan JSON (por defecto bajo $HERMES_HOME)")
    for name, helptext in (("apply", "crea el proyecto"), ("publish", "crea el remoto y sube")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("plan")
        sp.add_argument("--confirmed", action="store_true")
    vp = sub.add_parser("verify", help="lint y pruebas del proyecto, sin red")
    vp.add_argument("plan")
    vp.add_argument("--install", action="store_true", help="instala dependencias antes (red)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "plan" and args.type == "node" and args.package_manager is None:
        args.package_manager = "auto"
    handler = {"plan": cmd_plan, "apply": cmd_apply, "verify": cmd_verify, "publish": cmd_publish}
    try:
        return handler[args.command](args)
    except Refused as exc:
        print(f"RECHAZADO: {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
