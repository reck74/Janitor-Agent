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

A running container is not a working service: when every container runs and
the manifest declares a loopback ``url``, :func:`check_health` asks it once
(read-only GET, short timeout, no redirects followed) whether it answers.
"""

from __future__ import annotations

import http.client
import os
import ssl
import subprocess
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence
from urllib.parse import urlsplit

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


DOCKER_OK = "ok"
DOCKER_MISSING = "missing"          # no ``docker`` CLI on PATH
DOCKER_UNAVAILABLE = "unavailable"  # CLI present, daemon down or no permission
DOCKER_TIMEOUT = "timeout"


def docker_status(runner: Runner = subprocess.run, timeout: float = 10.0) -> str:
    """Whether the Docker daemon answers (read-only): one of the ``DOCKER_*`` values.

    ``container_states`` reports every container ``absent`` when the daemon is
    down, which would read as "not deployed"; callers that show state to a
    user check this first.
    """
    try:
        proc = runner(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError:
        return DOCKER_MISSING
    except subprocess.TimeoutExpired:
        return DOCKER_TIMEOUT
    except OSError:
        return DOCKER_UNAVAILABLE
    return DOCKER_OK if proc.returncode == 0 and (proc.stdout or "").strip() else DOCKER_UNAVAILABLE


def summarize(states: dict[str, str]) -> str:
    values = set(states.values())
    if values == {"running"}:
        return "running"
    if values == {"absent"}:
        return "not deployed"
    if "running" in values:
        return "degraded"
    return "stopped"


# ── health: does the running service answer? ──────────────────────────────

HEALTH_RESPONDING = "responding"          # an HTTP response came back (any status)
HEALTH_NOT_RESPONDING = "not_responding"  # connection refused / reset / timed out
HEALTH_UNCHECKED = "unchecked"            # no url, or a url this module will not call
HEALTH_TIMEOUT = 2.0
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _loopback_target(url: str) -> Optional[tuple[str, str, Optional[int], str]]:
    """``(scheme, host, port, path)`` for an http(s) url on loopback; ``None`` for anything else."""
    try:
        parts = urlsplit(url or "")
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or (parts.hostname or "") not in LOOPBACK_HOSTS:
        return None
    return parts.scheme, parts.hostname, port, parts.path or "/"


def probe_url(url: str, timeout: float = HEALTH_TIMEOUT) -> str:
    """One GET against a loopback ``url``: any HTTP status (401, 404, 3xx…) means it answers.

    Redirects are never followed and the body is never read. A url whose host
    is not 127.0.0.1 / localhost / ::1 is not requested at all.
    """
    target = _loopback_target(url)
    if target is None or timeout <= 0:
        return HEALTH_UNCHECKED
    scheme, host, port, path = target
    if scheme == "https":
        # Liveness only, on loopback, sending nothing: a self-signed local
        # certificate must not read as "down".
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=context)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", path, headers={"Connection": "close"})
        conn.getresponse()
    except (OSError, http.client.HTTPException):
        return HEALTH_NOT_RESPONDING
    finally:
        conn.close()
    return HEALTH_RESPONDING


def check_health(
    entries: Iterable[tuple[Service, Optional[dict]]], budget: float = HEALTH_TIMEOUT
) -> dict[str, Optional[str]]:
    """Service name -> health (``HEALTH_*``) for every service whose containers all run.

    Other services map to ``None`` (their container state already says it all).
    Probes run in parallel and the whole call returns within about ``budget``
    seconds; a probe still pending then counts as not responding.
    """
    result: dict[str, Optional[str]] = {}
    to_probe: list[Service] = []
    for service, states in entries:
        if not states or summarize(states) != "running":
            result[service.name] = None
        elif _loopback_target(service.url) is None:
            result[service.name] = HEALTH_UNCHECKED
        else:
            to_probe.append(service)
    if not to_probe:
        return result
    timeout = min(HEALTH_TIMEOUT, budget)
    if timeout <= 0:
        result.update({s.name: HEALTH_UNCHECKED for s in to_probe})
        return result
    pool = ThreadPoolExecutor(max_workers=len(to_probe), thread_name_prefix="janitor-health")
    futures = {pool.submit(probe_url, s.url, timeout): s for s in to_probe}
    wait(futures, timeout=budget)
    pool.shutdown(wait=False)
    for future, service in futures.items():
        result[service.name] = future.result() if future.done() else HEALTH_NOT_RESPONDING
    return result


_HEALTH_TEXT = {
    HEALTH_RESPONDING: "responde",
    HEALTH_NOT_RESPONDING: "contenedor en marcha, el servicio no responde (todavía)",
    HEALTH_UNCHECKED: "contenedor en marcha",
}


def state_text(summary: str, health: Optional[str]) -> str:
    """CLI state cell: the container summary, qualified by health when it is known."""
    return f"{summary}: {_HEALTH_TEXT[health]}" if health else summary


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
        if action in ("list", "status"):
            if action == "list" or not args.name:
                services = discover_services()
            else:
                services = [get_service(args.name)]
            rows = [(service, container_states(service, runner)) for service in services]
            health = check_health(rows)
            for service, states in rows:
                state = state_text(summarize(states), health[service.name])
                if action == "list":
                    out(f"{service.name:<10} {state:<13} {service.url:<24} {service.description}")
                    continue
                out(f"{service.name}: {state}")
                for container, container_state in states.items():
                    out(f"  {container:<32} {container_state}")
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
