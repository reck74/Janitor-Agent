"""Backend of the Janitor desktop plugin's "Servicios" screen.

Mounted by Hermes at ``/api/plugins/janitor/`` through the shim
``assets/plugins/janitor/dashboard/plugin_api.py`` (seeded into the home by
:mod:`janitor.desktop_plugin`), so it rides the dashboard plugin mount: the
session-token / OAuth middlewares and the ``plugins.enabled`` runtime gate
apply exactly as for any user plugin.

Read/act surface over :mod:`janitor.services`, safe by construction:

* a service is addressed only by a name that matches ``NAME_RE`` AND is one
  of the names discovered from ``service.yaml``; nothing else is accepted —
  no paths, commands, flags or container names;
* the only lifecycle verbs are ``start`` and ``stop`` (``janitor.services``
  runs ``docker inspect|start|stop`` on the declared ``janitor-*``
  containers). Deploy goes through the agent's guided skill; uninstall stays
  CLI-only;
* Docker missing / down / slow is a state in the payload, never a 500;
* every Docker call runs under a deadline; one action per service at a time.
"""

from __future__ import annotations

import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from janitor import services

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
APPS_PURPOSE = "aplicativos"

PROBE_TIMEOUT = 10.0    # docker version
LIST_TIMEOUT = 30.0     # every inspect of one listing
ACTION_TIMEOUT = 120.0  # inspect + start/stop of one service

STATE_RUNNING = "running"
STATE_PARTIAL = "partial"
STATE_STOPPED = "stopped"
STATE_NOT_INSTALLED = "not_installed"
STATE_DOCKER_UNAVAILABLE = "docker_unavailable"

_SUMMARY_STATE = {
    "running": STATE_RUNNING,
    "degraded": STATE_PARTIAL,
    "stopped": STATE_STOPPED,
    "not deployed": STATE_NOT_INSTALLED,
}

Runner = Callable[..., subprocess.CompletedProcess]

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class UnknownService(LookupError):
    """The name is not a discovered service (or not a valid name at all)."""


def _deadline_runner(runner: Runner, deadline: float) -> Runner:
    """``runner`` with every call's timeout capped by the time left until ``deadline``."""

    def run(argv, **kwargs):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(argv, 0)
        kwargs["timeout"] = min(kwargs.get("timeout") or remaining, remaining)
        return runner(argv, **kwargs)

    return run


def resolve_service(name: str, root: Path = services.SERVICES_ROOT) -> services.Service:
    """The discovered service called exactly ``name``; :class:`UnknownService` otherwise.

    Stricter than :func:`janitor.services.get_service`: no prefix stripping,
    no case folding — the screen only ever sends back names it received.
    """
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise UnknownService(name)
    for service in services.discover_services(root):
        if service.name == name:
            return service
    raise UnknownService(name)


def _service_view(service: services.Service, docker: str, states: Optional[dict]) -> dict:
    if states is not None:
        state = _SUMMARY_STATE[services.summarize(states)]
    elif docker == services.DOCKER_MISSING:
        # No Docker CLI: nothing of this service can exist on the machine.
        state = STATE_NOT_INSTALLED
    else:
        state = STATE_DOCKER_UNAVAILABLE
    container_state = states or {}
    return {
        "name": service.name,
        "skill": service.skill_dir.name,
        "skill_md": str(service.skill_dir / "SKILL.md"),
        "description": service.description,
        "url": service.url,
        "state": state,
        "containers": [
            {"name": c, "state": container_state.get(c, "unknown")} for c in service.containers
        ],
    }


def _states(service: services.Service, runner: Runner) -> Optional[dict]:
    try:
        return services.container_states(service, runner)
    except (subprocess.TimeoutExpired, services.ServiceError):
        return None


def unmanaged_apps(managed_skills: set) -> list[dict]:
    """Catalog ``aplicativos`` this OS offers that have no ``service.yaml``.

    They are installed by their guided skill too, but this backend cannot see
    their state (Open Design runs from a source tree, not containers).
    """
    from janitor import catalog as cat

    try:
        catalog = cat.load_catalog()
        platform = cat.current_platform()
    except (cat.CatalogError, ImportError, OSError):
        return []
    apps = []
    for entry in catalog.entries:
        if entry.purpose != APPS_PURPOSE or entry.id in managed_skills:
            continue
        if not cat.matches_platform(entry, platform):
            continue
        path = cat.resolve(entry)
        if path is None or not (path / "SKILL.md").is_file():
            continue
        apps.append({"skill": entry.id, "skill_md": str(path / "SKILL.md")})
    return apps


def list_view(runner: Runner = subprocess.run, root: Path = services.SERVICES_ROOT) -> dict:
    """Docker availability, every service with its state, and the stateless apps."""
    docker = services.docker_status(runner, PROBE_TIMEOUT)
    bounded = _deadline_runner(runner, time.monotonic() + LIST_TIMEOUT)
    items = []
    for service in services.discover_services(root):
        states = _states(service, bounded) if docker == services.DOCKER_OK else None
        items.append(_service_view(service, docker, states))
    return {
        "docker": {"available": docker == services.DOCKER_OK, "status": docker},
        "services": items,
        "unmanaged": unmanaged_apps({item["skill"] for item in items}),
    }


def _lock_for(name: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(name, threading.Lock())


def act(name: str, action: str, runner: Runner = subprocess.run,
        root: Path = services.SERVICES_ROOT) -> dict:
    """Start or stop one service. Expected failures come back as ``{"ok": False, "error": code}``.

    Codes: ``busy``, ``docker_unavailable``, ``not_installed``, ``timeout``,
    ``docker_failed``. Raises :class:`UnknownService` for an unknown name and
    ``ValueError`` for any other action.
    """
    if action not in ("start", "stop"):
        raise ValueError(action)
    service = resolve_service(name, root)
    lock = _lock_for(service.name)
    if not lock.acquire(blocking=False):
        return {"ok": False, "error": "busy"}
    try:
        docker = services.docker_status(runner, PROBE_TIMEOUT)
        if docker != services.DOCKER_OK:
            return {"ok": False, "error": "docker_unavailable",
                    "service": _service_view(service, docker, None)}
        bounded = _deadline_runner(runner, time.monotonic() + ACTION_TIMEOUT)
        try:
            before = services.container_states(service, bounded)
            if action == "start" and services.summarize(before) == "not deployed":
                return {"ok": False, "error": "not_installed",
                        "service": _service_view(service, docker, before)}
            verb = services.start if action == "start" else services.stop
            code = verb(service, bounded)
        except subprocess.TimeoutExpired:
            error = "timeout"
        except services.ServiceError:
            error = "docker_failed"
        else:
            error = None if code == 0 else "docker_failed"
        after = _states(service, _deadline_runner(runner, time.monotonic() + PROBE_TIMEOUT))
        return {"ok": error is None, "error": error, "service": _service_view(service, docker, after)}
    finally:
        lock.release()


def build_router(runner: Runner = subprocess.run, root: Path = services.SERVICES_ROOT):
    from fastapi import APIRouter, HTTPException

    router = APIRouter()

    # Sync handlers: FastAPI runs them in its threadpool, so a slow Docker
    # never blocks the gateway's event loop.
    @router.get("/servicios")
    def get_services() -> dict:
        return list_view(runner, root)

    def _action(name: str, action: str) -> dict:
        try:
            return act(name, action, runner, root)
        except UnknownService:
            raise HTTPException(status_code=404, detail="unknown service") from None

    @router.post("/servicios/{name}/start")
    def start_service(name: str) -> dict:
        return _action(name, "start")

    @router.post("/servicios/{name}/stop")
    def stop_service(name: str) -> dict:
        return _action(name, "stop")

    return router
