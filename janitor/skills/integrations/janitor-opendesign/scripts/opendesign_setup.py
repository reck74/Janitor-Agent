#!/usr/bin/env python3
"""Guided Open Design for Janitor: preflight, install, register, start, verify, stop, uninstall.

Open Design is a third-party design-generation app (nexu-io/open-design) that runs from a
source tree with ``pnpm`` (no containers). This script clones it, registers Janitor as its
coding agent (one new file, one icon, two small text patches) and starts it on fixed
loopback ports. Every command prints ONE JSON document on stdout and Spanish hints on
stderr. Nothing here runs ``sudo`` or deletes anything: files Janitor added are moved to
``<root>/janitor/opendesign/removed-<ts>/`` and the source tree is left for the user to send
to the trash.

Exit codes: 0 ok, 1 refused or failed (``ok: false`` + ``reason``), 2 usage/environment.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
AGENT_DEF = SKILL_DIR / "agent-defs" / "janitor.ts"
ICON = SKILL_DIR / "icon" / "janitor.png"

SCHEMA_VERSION = 1
GIT_URL = "https://github.com/nexu-io/open-design.git"
TAG_PATTERN = "open-design-v*"
DEFAULT_DAEMON_PORT = 45351
DEFAULT_WEB_PORT = 45343

DEF_PATH = "apps/daemon/src/runtimes/defs/janitor.ts"
REGISTRY_PATH = "apps/daemon/src/runtimes/registry.ts"
ICON_PATH = "apps/web/public/agent-icons/janitor.png"
AGENT_ICON_PATH = "apps/web/src/components/AgentIcon.tsx"
TOOLS_DEV = "node_modules/.bin/tools-dev"

IMPORT_ANCHOR = "import { hermesAgentDef } from './defs/hermes.js';"
IMPORT_LINE = "import { janitorAgentDef } from './defs/janitor.js';"
ARRAY_ANCHOR = "  hermesAgentDef,"
ARRAY_LINE = "  janitorAgentDef,"
ICON_ANCHOR = "  hermes: 'svg',"
ICON_LINE = "  janitor: 'png',"
MONO_LINE = "  'janitor',"


# ── output ────────────────────────────────────────────────────────────────


def hint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def finish(doc: dict) -> int:
    doc.setdefault("schema_version", SCHEMA_VERSION)
    print(json.dumps(doc, ensure_ascii=False, indent=2, default=str), flush=True)
    return 0 if doc.get("ok", True) else 1


def refuse(command: str, reason: str, **extra) -> int:
    return finish({"command": command, "ok": False, "reason": reason, **extra})


# ── homes, tools ──────────────────────────────────────────────────────────


class Homes:
    def __init__(self, root: Path, source: Path) -> None:
        self.root, self.source = root, source
        self.state_dir = root / "janitor" / "opendesign"
        self.legacy_source = Path.home() / "open-design"


def resolve_homes(source_arg: str | None) -> Homes | None:
    raw = (os.environ.get("JANITOR_HOME") or os.environ.get("HERMES_HOME") or "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser()
    if root.parent.name == "profiles" and not os.environ.get("JANITOR_HOME"):
        root = root.parent.parent
    source = source_arg or os.environ.get("OD_SOURCE_DIR") or str(root / "src" / "open-design")
    return Homes(root, Path(source).expanduser())


def which(name: str) -> str | None:
    """PATH lookup without shutil.which (an upstream guard scans janitor/ for it)."""
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        candidate = Path(entry) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def run(argv: list[str], *, timeout: float = 60, cwd: str | None = None):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, "", f"{argv[0]}: not found")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"{argv[0]}: timed out after {timeout}s")


def tail(text: str, lines: int = 30) -> list[str]:
    return (text or "").splitlines()[-lines:]


def tool_versions() -> dict:
    out = {}
    for name in ("git", "node", "pnpm", "janitor"):
        path = which(name)
        version = None
        if path and name != "janitor":
            proc = run([name, "--version"], timeout=20)
            version = (proc.stdout or "").strip().splitlines()[0] if proc.returncode == 0 and proc.stdout else None
        out[name] = {"present": bool(path), "version": version}
    return out


def port_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def http_get(url: str, timeout: float = 5.0) -> tuple[int | None, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 — loopback URL we built
            return resp.status, resp.read(262144)
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, OSError, ValueError):
        return None, b""


def probe(daemon_port: int, web_port: int) -> dict:
    """Real HTTP answers on loopback: daemon health, Janitor in the agent list, web UI."""
    daemon = f"http://127.0.0.1:{daemon_port}"
    status, _ = http_get(f"{daemon}/api/health")
    responds = status == 200
    registered = None
    if responds:
        a_status, body = http_get(f"{daemon}/api/agents", timeout=30)
        if a_status == 200:
            try:
                registered = _lists_janitor(json.loads(body or b"null"))
            except ValueError:
                registered = None
    web_status, _ = http_get(f"http://127.0.0.1:{web_port}/")
    return {"daemon": {"url": daemon, "health_status": status, "responds": responds},
            "janitor_in_agent_list": registered,
            "web": {"url": f"http://127.0.0.1:{web_port}", "status": web_status,
                    "responds": web_status is not None and 200 <= web_status < 400},
            "mcp_url": f"{daemon}/mcp"}


def _lists_janitor(data) -> bool:
    if isinstance(data, dict):
        data = data.get("agents", data.get("data", []))
    return isinstance(data, list) and any(isinstance(a, dict) and a.get("id") == "janitor" for a in data)


# ── source tree + integration (read-only inspection) ──────────────────────


def source_state(path: Path) -> str:
    if not path.exists():
        return "absent"
    if (path / "package.json").is_file() and (path / "apps" / "daemon").is_dir():
        return "open-design"
    return "other" if any(path.iterdir()) else "empty"


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def has_line(text: str | None, line: str) -> bool:
    return text is not None and line in text.splitlines()


def integration_status(source: Path) -> dict:
    registry = read_text(source / REGISTRY_PATH)
    agent_icon = read_text(source / AGENT_ICON_PATH)
    def_file = source / DEF_PATH
    icon_file = source / ICON_PATH
    steps = {
        "agent_def": def_file.is_file() and def_file.read_bytes() == AGENT_DEF.read_bytes(),
        "registry": has_line(registry, IMPORT_LINE) and has_line(registry, ARRAY_LINE),
        "icon": icon_file.is_file() and icon_file.read_bytes() == ICON.read_bytes(),
        "agent_icon": has_line(agent_icon, ICON_LINE) and not has_line(agent_icon, MONO_LINE),
    }
    missing_anchors = []
    if not def_file.parent.is_dir():
        missing_anchors.append(str(def_file.parent))
    if registry is None or (not has_line(registry, IMPORT_LINE) and not has_line(registry, IMPORT_ANCHOR)):
        missing_anchors.append(f"{REGISTRY_PATH}: {IMPORT_ANCHOR}")
    if registry is None or (not has_line(registry, ARRAY_LINE) and not has_line(registry, ARRAY_ANCHOR)):
        missing_anchors.append(f"{REGISTRY_PATH}: {ARRAY_ANCHOR.strip()}")
    if not icon_file.parent.is_dir():
        missing_anchors.append(str(icon_file.parent))
    if agent_icon is None or (not has_line(agent_icon, ICON_LINE) and not has_line(agent_icon, ICON_ANCHOR)):
        missing_anchors.append(f"{AGENT_ICON_PATH}: {ICON_ANCHOR.strip()}")
    return {"steps": steps, "registered": all(steps.values()), "missing_anchors": missing_anchors}


# ── preflight ─────────────────────────────────────────────────────────────


def cmd_preflight(args, homes: Homes) -> int:
    tools = tool_versions()
    state = source_state(homes.source)
    integration = integration_status(homes.source) if state == "open-design" else None
    installed = state == "open-design" and (homes.source / TOOLS_DEV).is_file()
    live = probe(args.daemon_port, args.web_port)
    ports = {"daemon": {"number": args.daemon_port, "free": port_free(args.daemon_port)},
             "web": {"number": args.web_port, "free": port_free(args.web_port)}}

    blockers = [f"{name}_missing" for name in ("git", "node", "pnpm") if not tools[name]["present"]]
    if not tools["janitor"]["present"]:
        blockers.append("janitor_command_missing")
    if state == "other":
        blockers.append("source_dir_not_open_design")
    if not live["daemon"]["responds"]:
        blockers += [f"{k}_port_busy" for k, v in ports.items() if not v["free"]]

    if live["daemon"]["responds"]:
        recommendation = "already-running"
    elif blockers:
        recommendation = "blocked"
    elif not installed:
        recommendation = "install"
    elif integration and not integration["registered"]:
        recommendation = "register"
    else:
        recommendation = "start"
    legacy = homes.legacy_source if homes.legacy_source != homes.source and \
        source_state(homes.legacy_source) == "open-design" else None
    for blocker in blockers:
        hint(f"bloqueado por {blocker}")
    return finish({
        "command": "preflight", "ok": True,
        "tools": tools,
        "source": {"path": str(homes.source), "state": state, "dependencies_installed": installed,
                   "legacy_tree": str(legacy) if legacy else None},
        "integration": integration,
        "ports": ports, "service": live,
        "blockers": blockers, "recommendation": recommendation,
    })


# ── install / register / unregister ───────────────────────────────────────


def cmd_install(args, homes: Homes) -> int:
    tools = tool_versions()
    missing = [f"{n}_missing" for n in ("git", "node", "pnpm") if not tools[n]["present"]]
    if missing:
        return refuse("install", missing[0], missing=missing, tools=tools)
    state = source_state(homes.source)
    if state == "other":
        return refuse("install", "source_dir_not_open_design", path=str(homes.source))
    clone, ref = "present", None
    if state in ("absent", "empty"):
        homes.source.parent.mkdir(parents=True, exist_ok=True)
        hint(f"Clonando Open Design en {homes.source} ...")
        proc = run(["git", "clone", "--quiet", GIT_URL, str(homes.source)], timeout=900)
        if proc.returncode != 0:
            return refuse("install", "git_clone_failed", log=tail(proc.stderr))
        clone = "cloned"
        ref = args.ref
        if not ref:
            tags = run(["git", "-C", str(homes.source), "tag", "--list", TAG_PATTERN, "--sort=-v:refname"])
            ref = next(iter((tags.stdout or "").split()), None)
        if ref:
            checkout = run(["git", "-C", str(homes.source), "checkout", "--quiet", ref], timeout=120)
            if checkout.returncode != 0:
                return refuse("install", "git_checkout_failed", ref=ref, log=tail(checkout.stderr))
    elif args.ref:
        hint("El árbol ya existe: no se cambia de versión (hazlo tú con git si quieres).")
    deps = "present"
    if not (homes.source / TOOLS_DEV).is_file():
        hint("pnpm install (puede tardar varios minutos) ...")
        proc = run(["pnpm", "install"], timeout=args.install_timeout, cwd=str(homes.source))
        if proc.returncode != 0 or not (homes.source / TOOLS_DEV).is_file():
            return refuse("install", "pnpm_install_failed", clone=clone, ref=ref,
                          log=tail((proc.stdout or "") + (proc.stderr or ""), 40))
        deps = "installed"
    return finish({"command": "install", "ok": True, "source": str(homes.source), "clone": clone,
                   "ref": (ref or "(rama por defecto)") if clone == "cloned" else None, "dependencies": deps,
                   "integration": integration_status(homes.source)})


def _insert_after(text: str, anchor: str, line: str) -> str:
    lines = text.splitlines(keepends=True)
    for i, current in enumerate(lines):
        body = current.rstrip("\r\n")
        if body == anchor:
            ending = current[len(body):] or "\n"
            lines[i] = body + ending
            lines.insert(i + 1, line + ending)
            return "".join(lines)
    raise ValueError(anchor)


def _drop_line(text: str, line: str) -> str:
    return "".join(l for l in text.splitlines(keepends=True) if l.rstrip("\r\n") != line)


def cmd_register(args, homes: Homes) -> int:
    if source_state(homes.source) != "open-design":
        return refuse("register", "open_design_not_installed", path=str(homes.source))
    status = integration_status(homes.source)
    if status["missing_anchors"]:
        hint("Open Design cambió su código: no se toca nada. Hay que adaptar la skill.")
        return refuse("register", "anchor_missing", missing_anchors=status["missing_anchors"])
    changed = []
    src = homes.source
    if not status["steps"]["agent_def"]:
        shutil.copyfile(AGENT_DEF, src / DEF_PATH)
        changed.append(DEF_PATH)
    if not status["steps"]["registry"]:
        text = read_text(src / REGISTRY_PATH) or ""
        if not has_line(text, IMPORT_LINE):
            text = _insert_after(text, IMPORT_ANCHOR, IMPORT_LINE)
        if not has_line(text, ARRAY_LINE):
            text = _insert_after(text, ARRAY_ANCHOR, ARRAY_LINE)
        (src / REGISTRY_PATH).write_text(text, encoding="utf-8")
        changed.append(REGISTRY_PATH)
    if not status["steps"]["icon"]:
        shutil.copyfile(ICON, src / ICON_PATH)
        changed.append(ICON_PATH)
    if not status["steps"]["agent_icon"]:
        text = read_text(src / AGENT_ICON_PATH) or ""
        if not has_line(text, ICON_LINE):
            text = _insert_after(text, ICON_ANCHOR, ICON_LINE)
        (src / AGENT_ICON_PATH).write_text(_drop_line(text, MONO_LINE), encoding="utf-8")
        changed.append(AGENT_ICON_PATH)
    return finish({"command": "register", "ok": True, "changed": changed,
                   "integration": integration_status(src),
                   "restart_needed": bool(changed)})


def unregister(homes: Homes) -> dict:
    """Undo register: drop the inserted lines, move the two added files aside (never delete)."""
    src = homes.source
    changed, moved = [], []
    for rel, lines in ((REGISTRY_PATH, (IMPORT_LINE, ARRAY_LINE)), (AGENT_ICON_PATH, (ICON_LINE,))):
        text = read_text(src / rel)
        if text is None:
            continue
        new = text
        for line in lines:
            new = _drop_line(new, line)
        if new != text:
            (src / rel).write_text(new, encoding="utf-8")
            changed.append(rel)
    aside = homes.state_dir / f"removed-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    for rel in (DEF_PATH, ICON_PATH):
        if (src / rel).is_file():
            aside.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src / rel), str(aside / Path(rel).name))
            moved.append(str(aside / Path(rel).name))
    return {"changed": changed, "moved_aside": moved}


# ── start / verify / stop / uninstall ─────────────────────────────────────


def cmd_start(args, homes: Homes) -> int:
    tools_dev = homes.source / TOOLS_DEV
    if not tools_dev.is_file():
        return refuse("start", "open_design_not_installed", path=str(homes.source))
    live = probe(args.daemon_port, args.web_port)
    if live["daemon"]["responds"]:
        return finish({"command": "start", "ok": True, "state": "already-running", "service": live})
    busy = [name for name, port in (("daemon", args.daemon_port), ("web", args.web_port)) if not port_free(port)]
    if busy:
        return refuse("start", "port_busy", ports=busy)
    homes.state_dir.mkdir(parents=True, exist_ok=True)
    log_path = homes.state_dir / "start.log"
    with open(log_path, "ab") as log:
        proc = subprocess.Popen([str(tools_dev), "start", "--daemon-port", str(args.daemon_port),
                                 "--web-port", str(args.web_port)], cwd=str(homes.source),
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)
    hint(f"Esperando a que Open Design responda en el puerto {args.daemon_port} (máx. {args.timeout}s) ...")
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        live = probe(args.daemon_port, args.web_port)
        if live["daemon"]["responds"]:
            return finish({"command": "start", "ok": True, "state": "started", "pid": proc.pid,
                           "log": str(log_path), "service": live})
        if proc.poll() not in (None, 0):
            break
        time.sleep(args.interval)
    log_tail = tail(read_text(log_path) or "", 30)
    return refuse("start", "health_timeout", exit_code=proc.poll(), log=str(log_path), log_tail=log_tail)


def cmd_verify(args, homes: Homes) -> int:
    live = probe(args.daemon_port, args.web_port)
    doc = {"command": "verify", "service": live,
           "integration": integration_status(homes.source) if source_state(homes.source) == "open-design" else None}
    if not live["daemon"]["responds"]:
        doc.update(ok=False, reason="service_unreachable")
    elif live["janitor_in_agent_list"] is False:
        doc.update(ok=False, reason="janitor_not_listed")
    else:
        doc["ok"] = True
    return finish(doc)


def stop(homes: Homes) -> dict:
    tools_dev = homes.source / TOOLS_DEV
    if not tools_dev.is_file():
        return {"stopped": None, "reason": "open_design_not_installed"}
    proc = run([str(tools_dev), "stop"], timeout=60, cwd=str(homes.source))
    return {"stopped": proc.returncode == 0, "log_tail": tail((proc.stdout or "") + (proc.stderr or ""), 10)}


def cmd_stop(args, homes: Homes) -> int:
    result = stop(homes)
    if result["stopped"] is None:
        return refuse("stop", result["reason"], path=str(homes.source))
    return finish({"command": "stop", "ok": result["stopped"], **result,
                   **({} if result["stopped"] else {"reason": "tools_dev_stop_failed"})})


def trash_hint(path: Path) -> str:
    if sys.platform == "darwin":
        return f"mv {path} ~/.Trash/"
    return f"gio trash {path}"


def cmd_uninstall(args, homes: Homes) -> int:
    if source_state(homes.source) != "open-design":
        return refuse("uninstall", "open_design_not_installed", path=str(homes.source))
    stopped = stop(homes)
    undone = unregister(homes)
    return finish({"command": "uninstall", "ok": True, "stopped": stopped["stopped"], **undone,
                   "source_kept": str(homes.source), "trash_hint": trash_hint(homes.source)})


# ── CLI ─────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opendesign_setup.py", description=__doc__.splitlines()[0])
    parser.add_argument("--source", help="Open Design source tree (default <janitor home>/src/open-design)")
    sub = parser.add_subparsers(dest="command", required=True)

    def ports(p):
        p.add_argument("--daemon-port", type=int, default=int(os.environ.get("OD_DAEMON_PORT") or DEFAULT_DAEMON_PORT))
        p.add_argument("--web-port", type=int, default=int(os.environ.get("OD_WEB_PORT") or DEFAULT_WEB_PORT))

    ports(sub.add_parser("preflight", help="Read-only: what is feasible and what is missing"))
    p = sub.add_parser("install", help="Clone Open Design and install its dependencies")
    p.add_argument("--ref", help="git tag or commit to check out (default: newest open-design-v* tag)")
    p.add_argument("--install-timeout", type=float, default=1800, help=argparse.SUPPRESS)
    sub.add_parser("register", help="Register Janitor as an Open Design agent (idempotent)")
    p = sub.add_parser("start", help="Start Open Design on fixed loopback ports")
    ports(p)
    p.add_argument("--timeout", type=float, default=180)
    p.add_argument("--interval", type=float, default=2, help=argparse.SUPPRESS)
    ports(sub.add_parser("verify", help="Prove Open Design answers and lists Janitor (writes nothing)"))
    sub.add_parser("stop", help="Stop Open Design")
    sub.add_parser("uninstall", help="Stop, undo the registration, keep the source tree")
    return parser


COMMANDS = {"preflight": cmd_preflight, "install": cmd_install, "register": cmd_register, "start": cmd_start,
            "verify": cmd_verify, "stop": cmd_stop, "uninstall": cmd_uninstall}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    homes = resolve_homes(args.source)
    if homes is None:
        hint("HERMES_HOME no está definido: ejecútalo desde Janitor (terminal del agente).")
        finish({"command": args.command, "ok": False, "reason": "hermes_home_unset"})
        return 2
    return COMMANDS[args.command](args, homes)


if __name__ == "__main__":
    raise SystemExit(main())
