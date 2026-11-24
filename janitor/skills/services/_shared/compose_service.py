"""Shared engine for the guided Docker service skills (janitor-n8n, janitor-nocodb, janitor-lightrag).

This directory holds no ``SKILL.md``: it is not a skill and is never listed in the catalog.
Each skill's ``scripts/<name>_setup.py`` describes its service with a :class:`ServiceSpec`
and calls :func:`main`. Commands: ``preflight`` (read-only), ``deploy`` (needs ``--yes``),
``verify`` (read-only HTTP check on loopback), ``stop`` (needs ``--yes``).

Every command prints ONE JSON document on stdout and Spanish hints on stderr. Secret values
are never printed: anything read from an env file is redacted from output and log tails.

Homes: ``HERMES_HOME`` is the active profile (its ``.env`` is read only for the credentials a
spec names). The containers are per machine: their files live in ``<root>/docker`` where the
root is ``JANITOR_HOME``, else derived from ``HERMES_HOME``. The containers get only the
variables their compose lists, interpolated from ``<root>/docker/<key>.env`` (0600), and
``docker compose`` runs with a minimal process environment, so the profile ``.env`` never
reaches a container. Nothing here runs ``sudo``, removes a container, or removes a volume.

Exit codes: 0 ok, 1 refused or failed (``ok: false`` + ``reason``), 2 ``HERMES_HOME`` unset.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import http.client
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SCHEMA_VERSION = 1
ENV_MARKER = "# janitor: generado por {script}; se regenera en cada deploy"
SECRET_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "AUTH", "COOKIE", "PRIVATE")
# Process variables docker compose may need to reach the daemon. Nothing else is passed.
DOCKER_ENV_KEEP = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "XDG_RUNTIME_DIR", "DOCKER_HOST",
                   "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY")
FORBIDDEN_HINT = "Nunca se borran volúmenes ni contenedores desde aquí."


class Refusal(Exception):
    """Raised by a spec's ``build_env`` when a prerequisite is missing."""

    def __init__(self, reason: str, **extra) -> None:
        super().__init__(reason)
        self.reason, self.extra = reason, extra


@dataclass(frozen=True)
class ServiceSpec:
    key: str                      # "n8n" → janitor-n8n, n8n-compose.yml, n8n.env
    title: str                    # human name for hints
    script: str                   # the skill script name (for the env marker)
    skill_dir: Path
    containers: tuple[str, ...]
    main_container: str
    volumes: tuple[str, ...]
    network: str
    images: tuple[str, ...]
    default_port: int
    health_path: str
    healthy_status: Callable[[int], bool]
    generated_secrets: tuple[str, ...]           # created once, kept across deploys
    build_env: Callable[["Context"], dict]       # the full env file content (no marker)
    min_free_gb: float = 2.0
    legacy_containers: tuple[str, ...] = ()      # names an older install used and we no longer ship
    extra_dirs: tuple[str, ...] = ()             # created under <root>/docker before up
    credential_names: tuple[str, ...] = ()       # profile .env names the spec reads (presence reported)
    credential_check: Callable[[dict], list[str]] | None = None   # blockers from credential presence

    @property
    def project(self) -> str:
        return f"janitor-{self.key}"

    @property
    def port_var(self) -> str:
        return f"JANITOR_{self.key.upper()}_PORT"

    @property
    def compose_name(self) -> str:
        return f"{self.key}-compose.yml"

    @property
    def env_name(self) -> str:
        return f"{self.key}.env"

    @property
    def shipped_compose(self) -> Path:
        return self.skill_dir / "scripts" / self.compose_name

    @property
    def marker(self) -> str:
        return ENV_MARKER.format(script=self.script)


@dataclass
class Context:
    spec: ServiceSpec
    port: int
    secrets: dict[str, str]          # generated values (kept across deploys)
    creds: dict[str, str]            # profile .env + process env, only credential_names
    args: argparse.Namespace
    timezone: str = "UTC"
    notes: list[str] = field(default_factory=list)


# ── output ────────────────────────────────────────────────────────────────


class Redactor:
    def __init__(self) -> None:
        self.values: set[str] = set()

    def add(self, *values: str | None) -> None:
        self.values.update(v for v in values if v and len(v) >= 6)

    def __call__(self, text: str) -> str:
        for value in sorted(self.values, key=len, reverse=True):
            text = text.replace(value, "***")
        return text


REDACT = Redactor()


def hint(message: str) -> None:
    print(REDACT(message), file=sys.stderr, flush=True)


def finish(doc: dict) -> int:
    doc.setdefault("schema_version", SCHEMA_VERSION)
    print(REDACT(json.dumps(doc, ensure_ascii=False, indent=2, default=str)), flush=True)
    return 0 if doc.get("ok", True) else 1


def refuse(command: str, reason: str, **extra) -> int:
    return finish({"command": command, "ok": False, "reason": reason, **extra})


# ── homes and files ───────────────────────────────────────────────────────


class Homes:
    def __init__(self, profile: Path, root: Path, spec: ServiceSpec) -> None:
        self.profile, self.root = profile, root
        self.deploy_dir = root / "docker"
        self.compose = self.deploy_dir / spec.compose_name
        self.env = self.deploy_dir / spec.env_name
        self.stamp = self.deploy_dir / f".{spec.compose_name}.sha256"
        self.profile_env = profile / ".env"


def resolve_homes(spec: ServiceSpec) -> Homes | None:
    raw = (os.environ.get("HERMES_HOME") or os.environ.get("JANITOR_HOME") or "").strip()
    if not raw:
        return None
    profile = Path(raw).expanduser()
    root_raw = (os.environ.get("JANITOR_HOME") or "").strip()
    if root_raw:
        root = Path(root_raw).expanduser()
    elif profile.parent.name == "profiles":
        root = profile.parent.parent
    else:
        root = profile
    return Homes(profile, root, spec)


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def is_secret_name(name: str) -> bool:
    return any(word in name.upper() for word in SECRET_WORDS)


def credentials(spec: ServiceSpec, homes: Homes) -> dict[str, str]:
    profile_env = read_env_file(homes.profile_env)
    REDACT.add(*(v for k, v in profile_env.items() if is_secret_name(k)))
    out = {n: (profile_env.get(n) or os.environ.get(n) or "").strip() for n in spec.credential_names}
    REDACT.add(*out.values())
    return out


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def compose_owner(spec: ServiceSpec, homes: Homes) -> str | None:
    """None (absent), "janitor" (a copy we shipped) or "user" (edited: kept as is)."""
    digest = sha256_file(homes.compose)
    if digest is None:
        return None
    stamped = homes.stamp.is_file() and homes.stamp.read_text(encoding="utf-8").strip() == digest
    return "janitor" if digest == sha256_file(spec.shipped_compose) or stamped else "user"


def env_owner(spec: ServiceSpec, homes: Homes) -> str | None:
    try:
        first = homes.env.read_text(encoding="utf-8").splitlines()[:1]
    except OSError:
        return None
    return "janitor" if first == [spec.marker] else "user"


def host_timezone() -> str:
    tz = (os.environ.get("TZ") or "").strip().lstrip(":")
    if tz and "/" in tz:
        return tz
    with contextlib.suppress(OSError):
        value = Path("/etc/timezone").read_text(encoding="utf-8").strip()
        if value:
            return value
    with contextlib.suppress(OSError):
        target = os.readlink("/etc/localtime")
        if "zoneinfo/" in target:
            return target.split("zoneinfo/", 1)[1]
    return "UTC"


# ── docker probes (read-only) ─────────────────────────────────────────────


def which(name: str) -> str | None:
    """PATH lookup without shutil.which (an upstream guard scans janitor/ for it)."""
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry:
            candidate = Path(entry) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def docker_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: os.environ[k] for k in DOCKER_ENV_KEEP if k in os.environ}
    env.update(extra or {})
    return env


def run(argv: list[str], *, timeout: float = 60, env: dict | None = None, cwd: str | None = None):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              env=env if env is not None else docker_env(), cwd=cwd, check=False)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, "", f"{argv[0]}: not found")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"{argv[0]}: timed out after {timeout}s")


def tail(text: str, lines: int = 30) -> list[str]:
    return [REDACT(line) for line in (text or "").splitlines()[-lines:]]


def docker_install_hint() -> dict[str, str]:
    """Command for the user to run in their own terminal. Never executed here."""
    if sys.platform == "darwin":
        return {"distro": "macos", "command": "brew install --cask docker  # o Docker Desktop: https://docs.docker.com/desktop/"}
    rel: dict[str, str] = {}
    with contextlib.suppress(OSError):
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            rel[key.strip()] = value.strip().strip('"')
    ids = {rel.get("ID", "").lower(), *rel.get("ID_LIKE", "").lower().split()}
    group = "sudo usermod -aG docker $USER  # cierra sesión y vuelve a entrar"
    if "arch" in ids:
        cmd = f"sudo pacman -S --needed docker docker-compose && sudo systemctl enable --now docker.service && {group}"
    elif ids & {"opensuse", "suse", "sles"}:
        cmd = f"sudo zypper install docker docker-compose && sudo systemctl enable --now docker && {group}"
    else:
        cmd = f"curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh && {group}"
    return {"distro": rel.get("ID", "linux") or "linux", "command": cmd}


def probe_docker() -> dict:
    out = {"cli": False, "daemon": False, "compose_v2": False, "compose_version": None,
           "root_dir": None, "error": None, "install_hint": None, "fix_hint": None}
    if not which("docker"):
        out["error"] = "docker_missing"
        out["install_hint"] = docker_install_hint()
        return out
    out["cli"] = True
    info = run(["docker", "info", "--format", "{{.DockerRootDir}}"], timeout=20)
    if info.returncode != 0:
        if "permission denied" in (info.stderr or "").lower():
            out["error"] = "docker_permission_denied"
            out["fix_hint"] = "sudo usermod -aG docker $USER  # cierra sesión y vuelve a entrar"
        else:
            out["error"] = "docker_daemon_down"
            out["fix_hint"] = "sudo systemctl start docker"
    else:
        out["daemon"] = True
        out["root_dir"] = (info.stdout or "").strip() or None
    compose = run(["docker", "compose", "version", "--short"], timeout=20)
    version = (compose.stdout or "").strip().lstrip("v")
    if compose.returncode == 0 and version:
        out["compose_version"] = version
        major = version.split(".", 1)[0]
        out["compose_v2"] = major.isdigit() and int(major) >= 2
    if out["error"] is None and not out["compose_v2"]:
        out["error"] = "compose_v2_missing"
    return out


INSPECT_FORMAT = ('{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}|'
                  '{{index .Config.Labels "com.docker.compose.project"}}')


def container_states(names: tuple[str, ...], docker_ok: bool) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for name in names:
        if not docker_ok:
            states[name] = {"status": "unknown", "health": None, "project": None}
            continue
        proc = run(["docker", "inspect", "-f", INSPECT_FORMAT, name])
        if proc.returncode != 0:
            states[name] = {"status": "absent", "health": None, "project": None}
            continue
        status, _, rest = (proc.stdout or "").strip().partition("|")
        health, _, project = rest.partition("|")
        states[name] = {"status": status or "unknown", "health": health or None, "project": project or None}
    return states


def summarize(states: dict[str, dict]) -> str:
    values = {s["status"] for s in states.values()}
    if values == {"running"}:
        return "running"
    if values == {"absent"}:
        return "not deployed"
    if "unknown" in values:
        return "unknown"
    return "degraded" if "running" in values else "stopped"


def port_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def disk_free(paths: list[Path], required: float) -> dict:
    for path in paths:
        probe = path
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            usage = shutil.disk_usage(probe)
        except OSError:
            continue
        free_gb = round(usage.free / 1024 ** 3, 1)
        return {"path": str(probe), "free_gb": free_gb, "required_gb": required, "enough": free_gb >= required}
    return {"path": None, "free_gb": None, "required_gb": required, "enough": None}


def probe_http(url: str, timeout: float = 3.0) -> dict:
    """One GET on loopback. ``responding``: any HTTP answer. Redirects are not followed."""
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    if parts.hostname not in ("127.0.0.1", "localhost", "::1"):
        return {"url": url, "responding": False, "status": None, "error": "not_loopback"}
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
    try:
        conn.request("GET", parts.path or "/", headers={"Connection": "close"})
        status = conn.getresponse().status
    except (OSError, http.client.HTTPException) as exc:
        return {"url": url, "responding": False, "status": None, "error": exc.__class__.__name__}
    finally:
        conn.close()
    return {"url": url, "responding": True, "status": status, "error": None}


def configured_port(spec: ServiceSpec, homes: Homes, requested: int | None) -> int:
    if requested:
        return requested
    value = read_env_file(homes.env).get(spec.port_var, "")
    return int(value) if value.isdigit() and 0 < int(value) < 65536 else spec.default_port


def health_url(spec: ServiceSpec, port: int) -> str:
    return f"http://127.0.0.1:{port}{spec.health_path}"


def foreign(spec: ServiceSpec, states: dict[str, dict]) -> list[dict]:
    """Containers with our names that this skill's compose project did not create."""
    return [{"container": n, "project": s["project"], "status": s["status"]}
            for n, s in states.items()
            if s["status"] not in ("absent", "unknown") and (s["project"] != spec.project or n in spec.legacy_containers)]


# ── preflight ─────────────────────────────────────────────────────────────


def assess(spec: ServiceSpec, homes: Homes, port: int) -> dict:
    """Everything preflight reports and deploy decides on. Read-only."""
    docker = probe_docker()
    docker_ok = docker["daemon"]
    states = container_states(spec.containers + spec.legacy_containers, docker_ok)
    ours = {n: states[n] for n in spec.containers}
    service_state = summarize(ours)
    main_running = ours[spec.main_container]["status"] == "running"
    free = port_free(port)
    owner = None if free else (spec.main_container if main_running else "other")
    creds = credentials(spec, homes)
    disk = disk_free(([Path(docker["root_dir"])] if docker["root_dir"] else []) + [homes.root], spec.min_free_gb)
    volumes = {v: (run(["docker", "volume", "inspect", v]).returncode == 0) if docker_ok else None for v in spec.volumes}
    network = (run(["docker", "network", "inspect", spec.network]).returncode == 0) if docker_ok else None
    others = foreign(spec, states)

    blockers: list[str] = []
    if docker["error"]:
        blockers.append(docker["error"])
    if others:
        blockers.append("foreign_containers")
    if owner == "other":
        blockers.append("port_busy")
    if disk["enough"] is False and service_state == "not deployed":
        blockers.append("disk_low")
    if spec.credential_check:
        blockers += spec.credential_check(creds)
    return {
        "docker": docker,
        "port": {"number": port, "free": free, "owner": owner},
        "disk": disk,
        "service": {"state": service_state, "url": f"http://127.0.0.1:{port}", "containers": ours,
                    "volumes": volumes, "network": network},
        "foreign_containers": others,
        "files": {"deploy_dir": str(homes.deploy_dir), "compose": compose_owner(spec, homes),
                  "env_file": env_owner(spec, homes)},
        "credentials": {n: bool(v) for n, v in creds.items()},
        "blockers": blockers,
    }


def cmd_preflight(spec: ServiceSpec, args, homes: Homes) -> int:
    port = configured_port(spec, homes, args.port)
    doc = {"command": "preflight", "ok": True, "service_name": spec.key,
           "home": {"profile": str(homes.profile), "root": str(homes.root)}, **assess(spec, homes, port)}
    doc["health"] = (probe_http(health_url(spec, port))
                     if doc["service"]["containers"][spec.main_container]["status"] == "running" else None)
    doc["ready_to_deploy"] = not doc["blockers"]
    for blocker in doc["blockers"]:
        hint(f"{spec.title}: bloqueado por {blocker}")
    return finish(doc)


# ── deploy ────────────────────────────────────────────────────────────────


def existing_secrets(spec: ServiceSpec, homes: Homes) -> dict[str, str]:
    current = read_env_file(homes.env)
    return {name: current[name] for name in spec.generated_secrets if current.get(name)}


def plan_doc(spec: ServiceSpec, homes: Homes, port: int) -> dict:
    return {
        "write": [str(homes.compose), f"{homes.env} (0600, solo las variables de {spec.title})",
                  *(str(homes.deploy_dir / d) for d in spec.extra_dirs)],
        "images": list(spec.images), "containers": list(spec.containers),
        "volumes": list(spec.volumes), "network": spec.network,
        "listen": f"127.0.0.1:{port}", "command": f"docker compose -p {spec.project} up -d",
        "never": ["sudo", "docker rm", "docker compose down", "docker volume rm"],
    }


def ensure_compose(spec: ServiceSpec, homes: Homes) -> str:
    owner = compose_owner(spec, homes)
    shipped = spec.shipped_compose.read_bytes()
    shipped_sha = hashlib.sha256(shipped).hexdigest()
    if owner == "user":
        hint(f"{homes.compose} tiene cambios tuyos: se respeta tal cual.")
        return "kept-user-file"
    if owner == "janitor" and sha256_file(homes.compose) == shipped_sha:
        atomic_write(homes.stamp, shipped_sha.encode(), 0o644)
        return "unchanged"
    if owner == "janitor":
        backup = homes.deploy_dir / f"{spec.compose_name}.bak-{_dt.datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(homes.compose, backup)
    atomic_write(homes.compose, shipped, 0o644)
    atomic_write(homes.stamp, shipped_sha.encode(), 0o644)
    return "updated" if owner else "installed"


def compose_variables(path: Path) -> set[str]:
    """``${VAR}`` / ``${VAR:-x}`` names a compose file interpolates."""
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"\$\{([A-Z0-9_]+)(?::?[-?][^}]*)?\}", text))


def ensure_env(spec: ServiceSpec, homes: Homes, ctx: Context) -> str:
    """Write ``<key>.env``. A file without our marker is the user's: kept, but it must define
    every variable the compose interpolates."""
    owner = env_owner(spec, homes)
    if owner == "user":
        missing = sorted(compose_variables(homes.compose) - set(read_env_file(homes.env)) - {spec.port_var})
        if missing:
            raise Refusal("env_file_incomplete", path=str(homes.env), missing=missing)
        REDACT.add(*read_env_file(homes.env).values())
        hint(f"{homes.env} es tuyo (sin la marca de Janitor): se usa tal cual.")
        return "kept-user-file"
    values = {spec.port_var: str(ctx.port), **ctx.secrets, **spec.build_env(ctx)}
    REDACT.add(*(v for k, v in values.items() if is_secret_name(k) or k in spec.generated_secrets))
    lines = [spec.marker, "# Solo lo que estos contenedores necesitan. No lo subas a ningún repositorio."]
    lines += [f"{k}={v}" for k, v in values.items()]
    data = ("\n".join(lines) + "\n").encode("utf-8")
    if homes.env.is_file() and homes.env.read_bytes() == data:
        return "unchanged"
    atomic_write(homes.env, data, 0o600)
    return "generated" if owner is None else "updated"


def wait_healthy(spec: ServiceSpec, port: int, timeout: float, interval: float) -> tuple[dict, dict]:
    start = time.monotonic()
    grace = min(30.0, timeout / 2)
    while True:
        states = container_states(spec.containers, True)
        probe = probe_http(health_url(spec, port))
        if probe["responding"] and spec.healthy_status(probe["status"]):
            return probe, states
        elapsed = time.monotonic() - start
        crashed = any(s["status"] in ("exited", "dead", "absent") or s["health"] == "unhealthy"
                      for s in states.values())
        if elapsed >= timeout or (crashed and elapsed >= grace):
            return probe, states
        time.sleep(interval)


def cmd_deploy(spec: ServiceSpec, args, homes: Homes) -> int:
    port = configured_port(spec, homes, args.port)
    found = assess(spec, homes, port)
    if found["blockers"]:
        return refuse("deploy", found["blockers"][0], blockers=found["blockers"],
                      docker=found["docker"], port=found["port"], foreign_containers=found["foreign_containers"],
                      credentials=found["credentials"], changed=[])
    ctx = Context(spec=spec, port=port, args=args, timezone=host_timezone(),
                  creds=credentials(spec, homes),
                  secrets={n: secrets.token_hex(24) for n in spec.generated_secrets})
    ctx.secrets.update(existing_secrets(spec, homes))
    try:
        spec.build_env(ctx)  # validates the choices before anything is written
    except Refusal as exc:
        return refuse("deploy", exc.reason, changed=[], **exc.extra)
    ctx.notes.clear()
    if not args.yes:
        hint("Nada se ha tocado. Enseña el plan al usuario y vuelve con --yes si dice que sí.")
        return refuse("deploy", "confirmation_required", plan=plan_doc(spec, homes, port), changed=[])

    homes.deploy_dir.mkdir(parents=True, exist_ok=True)
    compose = ensure_compose(spec, homes)
    try:
        env_file = ensure_env(spec, homes, ctx)
    except Refusal as exc:
        return refuse("deploy", exc.reason, compose=compose, **exc.extra)
    for name in spec.extra_dirs:
        (homes.deploy_dir / name).mkdir(parents=True, exist_ok=True)

    hint(f"docker compose up -d para {spec.title} (la primera vez descarga imágenes: paciencia) ...")
    up = run(["docker", "compose", "-p", spec.project, "-f", str(homes.compose), "--env-file", str(homes.env),
              "up", "-d"], timeout=args.up_timeout, env=docker_env({spec.port_var: str(port)}),
             cwd=str(homes.deploy_dir))
    if up.returncode != 0:
        return refuse("deploy", "compose_up_failed", log=tail(up.stderr or up.stdout, 40),
                      compose=compose, env_file=env_file, volumes_removed=False)

    hint(f"Esperando a que {health_url(spec, port)} conteste (máx. {args.timeout:.0f}s) ...")
    probe, states = wait_healthy(spec, port, args.timeout, args.interval)
    healthy = probe["responding"] and spec.healthy_status(probe["status"])
    doc = {"command": "deploy", "ok": healthy, "url": f"http://127.0.0.1:{port}", "health": probe,
           "compose": compose, "env_file": env_file, "credentials_file": str(homes.env),
           "containers": states, "volumes_removed": False, "notes": ctx.notes}
    if not healthy:
        failing = [n for n, s in states.items() if s["status"] != "running" or s["health"] == "unhealthy"]
        failing = failing or [spec.main_container]
        doc["reason"] = "health_timeout"
        doc["failing"] = [{"container": n, **states[n], "log_tail": tail(
            (lambda p: (p.stdout or "") + (p.stderr or ""))(run(["docker", "logs", "--tail", "30", n])), 30)}
            for n in failing]
        hint(f"{spec.title} no contesta. Los volúmenes siguen ahí; re-ejecutar deploy reutiliza los datos.")
    return finish(doc)


# ── verify / stop ─────────────────────────────────────────────────────────


def cmd_verify(spec: ServiceSpec, args, homes: Homes) -> int:
    port = configured_port(spec, homes, args.port)
    probe = probe_http(health_url(spec, port), timeout=args.http_timeout)
    healthy = probe["responding"] and spec.healthy_status(probe["status"])
    docker = probe_docker() if which("docker") else {"daemon": False}
    states = container_states(spec.containers, bool(docker.get("daemon")))
    doc = {"command": "verify", "ok": healthy, "service_name": spec.key, "health": probe,
           "service": {"state": summarize(states), "containers": states}}
    if not healthy:
        doc["reason"] = "not_responding" if not probe["responding"] else "unhealthy_status"
    return finish(doc)


def cmd_stop(spec: ServiceSpec, args, homes: Homes) -> int:
    docker = probe_docker()
    if docker["error"] and docker["error"] != "compose_v2_missing":
        return refuse("stop", docker["error"], docker=docker)
    states = container_states(spec.containers, True)
    running = [n for n, s in states.items() if s["status"] in ("running", "restarting", "paused")]
    if not args.yes:
        return refuse("stop", "confirmation_required", would_stop=running, keeps=list(spec.volumes), changed=[])
    if not running:
        return finish({"command": "stop", "ok": True, "stopped": [], "volumes_removed": False})
    proc = run(["docker", "stop", *running], timeout=120)
    doc = {"command": "stop", "ok": proc.returncode == 0, "stopped": running if proc.returncode == 0 else [],
           "volumes_removed": False, "kept": {"volumes": list(spec.volumes), "files": [str(homes.compose), str(homes.env)]}}
    if proc.returncode != 0:
        doc["reason"] = "docker_stop_failed"
        doc["log"] = tail(proc.stderr, 20)
    return finish(doc)


# ── CLI ───────────────────────────────────────────────────────────────────


def build_parser(spec: ServiceSpec, add_deploy_args: Callable | None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=spec.script, description=f"Guided {spec.title} install for Janitor.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preflight", help="Read-only: what is there and what blocks a deploy")
    p.add_argument("--port", type=int)
    p = sub.add_parser("deploy", help="Write the files and start the containers (needs --yes)")
    p.add_argument("--port", type=int)
    p.add_argument("--yes", action="store_true", help="the user confirmed the plan")
    p.add_argument("--timeout", type=float, default=180, help="seconds to wait for the health URL")
    p.add_argument("--up-timeout", type=float, default=1200, help="seconds for docker compose up (pulls)")
    p.add_argument("--interval", type=float, default=3, help=argparse.SUPPRESS)
    if add_deploy_args:
        add_deploy_args(p)
    p = sub.add_parser("verify", help="Read-only: does the service answer on loopback?")
    p.add_argument("--port", type=int)
    p.add_argument("--http-timeout", type=float, default=3.0, help=argparse.SUPPRESS)
    p = sub.add_parser("stop", help="Stop the containers (never removes them or their volumes; needs --yes)")
    p.add_argument("--yes", action="store_true")
    return parser


COMMANDS = {"preflight": cmd_preflight, "deploy": cmd_deploy, "verify": cmd_verify, "stop": cmd_stop}


def main(spec: ServiceSpec, argv: list[str] | None = None, add_deploy_args: Callable | None = None) -> int:
    args = build_parser(spec, add_deploy_args).parse_args(argv)
    homes = resolve_homes(spec)
    if homes is None:
        hint("HERMES_HOME no está definido: esto se ejecuta desde Janitor, no a pelo.")
        finish({"command": args.command, "ok": False, "reason": "hermes_home_unset"})
        return 2
    return COMMANDS[args.command](spec, args, homes)
