"""Janitor self-hosted services (``janitor services ...``).

Each service skill under ``janitor/skills/services/<skill>/`` ships a
``service.yaml`` manifest::

    name: honcho
    description: ...
    deploy: scripts/deploy.sh        # idempotent install/repair script
    compose: scripts/honcho-compose.yml
    url: http://127.0.0.1:1973
    containers: [janitor-honcho-api, ...]

Lifecycle commands act on the declared container names rather than on a
compose project: the deploy scripts historically ran compose from different
directories (``-p janitor``, ``~/.janitor/docker``), so the project name —
and therefore the volume prefix — differs between installs. Container names
are fixed by ``container_name:`` in every compose file and are stable.

Nothing here ever removes Docker volumes: user data survives ``uninstall``.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import yaml

from janitor.home import REPO_ROOT, SKILLS_ROOT, janitor_home

SERVICES_ROOT = SKILLS_ROOT / "services"
MANIFEST = "service.yaml"
CONTAINER_PREFIX = "janitor-"

Runner = Callable[..., subprocess.CompletedProcess]


class ServiceError(Exception):
    pass


@dataclass(frozen=True)
class Service:
    name: str
    description: str
    skill_dir: Path
    deploy: str
    compose: str
    url: str
    containers: tuple[str, ...]

    @property
    def deploy_script(self) -> Path:
        return self.skill_dir / self.deploy

    @property
    def compose_file(self) -> Path:
        return self.skill_dir / self.compose


def _parse_manifest(path: Path) -> Service:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ServiceError(f"{path}: manifest must be a mapping")
    missing = [k for k in ("name", "deploy", "containers") if not data.get(k)]
    if missing:
        raise ServiceError(f"{path}: missing {', '.join(missing)}")
    containers = data["containers"]
    if not isinstance(containers, list) or not all(isinstance(c, str) for c in containers):
        raise ServiceError(f"{path}: containers must be a list of names")
    bad = [c for c in containers if not c.startswith(CONTAINER_PREFIX)]
    if bad:
        raise ServiceError(f"{path}: containers must use the {CONTAINER_PREFIX!r} prefix: {bad}")
    return Service(
        name=str(data["name"]),
        description=str(data.get("description", "")),
        skill_dir=path.parent,
        deploy=str(data["deploy"]),
        compose=str(data.get("compose", "")),
        url=str(data.get("url", "")),
        containers=tuple(containers),
    )


def discover_services(root: Path = SERVICES_ROOT) -> list[Service]:
    if not root.is_dir():
        return []
    return sorted(
        (_parse_manifest(p) for p in root.glob(f"*/{MANIFEST}")),
        key=lambda s: s.name,
    )


def get_service(name: str, root: Path = SERVICES_ROOT) -> Service:
    wanted = name.strip().lower()
    if wanted.startswith(CONTAINER_PREFIX):
        wanted = wanted[len(CONTAINER_PREFIX):]
    for service in discover_services(root):
        if service.name == wanted:
            return service
    known = ", ".join(s.name for s in discover_services(root)) or "none"
    raise ServiceError(f"Unknown service {name!r} (available: {known})")


def _run(runner: Runner, argv: Sequence[str], **kwargs) -> subprocess.CompletedProcess:
    try:
        return runner(list(argv), **kwargs)
    except FileNotFoundError as exc:
        raise ServiceError(f"{argv[0]} not found — is Docker installed?") from exc


def container_states(service: Service, runner: Runner = subprocess.run) -> dict[str, str]:
    """Map each declared container to its Docker state (``absent`` if missing)."""
    states: dict[str, str] = {}
    for container in service.containers:
        proc = _run(
            runner,
            ["docker", "inspect", "-f", "{{.State.Status}}", container],
            capture_output=True,
            text=True,
            check=False,
        )
        states[container] = (proc.stdout or "").strip() if proc.returncode == 0 else "absent"
    return states


def summarize(states: dict[str, str]) -> str:
    values = set(states.values())
    if values == {"running"}:
        return "running"
    if values == {"absent"}:
        return "not deployed"
    if "running" in values:
        return "degraded"
    return "stopped"


def deploy(service: Service, runner: Runner = subprocess.run) -> int:
    script = service.deploy_script
    if not script.is_file():
        raise ServiceError(f"Deploy script missing: {script}")
    env = dict(os.environ)
    env.setdefault("JANITOR_SOURCE_DIR", str(REPO_ROOT))
    env.setdefault("JANITOR_HOME", str(janitor_home()))
    proc = _run(runner, ["bash", str(script)], cwd=str(service.skill_dir), env=env, check=False)
    return proc.returncode


def _present(service: Service, runner: Runner) -> list[str]:
    return [c for c, s in container_states(service, runner).items() if s != "absent"]


def start(service: Service, runner: Runner = subprocess.run) -> int:
    present = _present(service, runner)
    if not present:
        raise ServiceError(
            f"{service.name} is not deployed. Run: janitor services deploy {service.name}"
        )
    return _run(runner, ["docker", "start", *present], check=False).returncode


def stop(service: Service, runner: Runner = subprocess.run) -> int:
    present = _present(service, runner)
    if not present:
        return 0
    return _run(runner, ["docker", "stop", *present], check=False).returncode


def uninstall(service: Service, runner: Runner = subprocess.run) -> int:
    """Remove the containers. Volumes and ``~/.janitor/docker`` files stay."""
    present = _present(service, runner)
    if not present:
        return 0
    return _run(runner, ["docker", "rm", "-f", *present], check=False).returncode


# ── CLI ────────────────────────────────────────────────────────────────────


def setup_parser(parser) -> None:
    sub = parser.add_subparsers(dest="services_action")
    sub.add_parser("list", help="List available services and their state")
    status = sub.add_parser("status", help="Show container state for one or all services")
    status.add_argument("name", nargs="?")
    for action, text in (
        ("deploy", "Install or repair a service (idempotent)"),
        ("start", "Start the containers of a deployed service"),
        ("stop", "Stop the containers of a service"),
        ("uninstall", "Remove the containers of a service (keeps volumes/data)"),
    ):
        p = sub.add_parser(action, help=text)
        p.add_argument("name")


def handle(args, runner: Runner = subprocess.run, out=print) -> int:
    action = getattr(args, "services_action", None) or "list"
    try:
        if action == "list":
            for service in discover_services():
                state = summarize(container_states(service, runner))
                out(f"{service.name:<10} {state:<13} {service.url:<24} {service.description}")
            return 0
        if action == "status":
            services = [get_service(args.name)] if args.name else discover_services()
            for service in services:
                states = container_states(service, runner)
                out(f"{service.name}: {summarize(states)}")
                for container, state in states.items():
                    out(f"  {container:<32} {state}")
            return 0
        service = get_service(args.name)
        if action == "deploy":
            return deploy(service, runner)
        if action == "start":
            return start(service, runner)
        if action == "stop":
            return stop(service, runner)
        if action == "uninstall":
            code = uninstall(service, runner)
            if code == 0:
                out(f"{service.name}: containers removed; Docker volumes and ~/.janitor/docker kept.")
            return code
    except ServiceError as exc:
        out(f"error: {exc}")
        return 1
    out(f"error: unknown action {action!r}")
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="janitor services")
    setup_parser(parser)
    return handle(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
