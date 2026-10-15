"""Reproducible local Honcho deployment; no existing volumes are removed."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import hermes_yaml as yaml

from janitor_ext.install import HONCHO_REF, ROOT, private_write, read_secrets
from janitor_ext.migrate import snapshot, record_backup_artifact


def legacy_database_credentials(home: Path) -> dict[str, str]:
    """Read the installed compose before replacing it; a volume keeps its original login."""
    installed = home / "docker/honcho-compose.yml"
    if not installed.exists():
        return {}
    document = yaml.safe_load(installed.read_text()) or {}
    for service in document.get("services", {}).values():
        environment = service.get("environment", {})
        if isinstance(environment, list):
            environment = dict(line.split("=", 1) for line in environment if "=" in line)
        user, password = environment.get("POSTGRES_USER"), environment.get("POSTGRES_PASSWORD")
        if user and password and not str(user).startswith("${") and not str(password).startswith("${"):
            return {"HONCHO_POSTGRES_USER": str(user), "HONCHO_POSTGRES_PASSWORD": str(password)}
    return {}


def prepare_service(home: Path) -> Path:
    values = read_secrets(home / ".env")
    if not values.get("MINIMAX_API_KEY") or not values.get("OPENAI_API_KEY"):
        raise ValueError("Local Honcho needs MINIMAX_API_KEY for reasoning and OPENAI_API_KEY for embeddings")
    previous = read_secrets(home / "honcho.env")
    login = legacy_database_credentials(home) | {key: value for key, value in previous.items()
        if key in ("HONCHO_POSTGRES_USER", "HONCHO_POSTGRES_PASSWORD")}
    login.setdefault("HONCHO_POSTGRES_USER", "janitor_honcho")
    login.setdefault("HONCHO_POSTGRES_PASSWORD", secrets.token_urlsafe(36))
    source = home / "src/honcho"
    runtime = {
        **login,
        "JANITOR_HONCHO_SOURCE": str(source),
        "JANITOR_HONCHO_ENV": str(home / "honcho.env"),
        "JANITOR_HONCHO_CONFIG": str(home / "honcho.toml"),
        "DB_CONNECTION_URI": "postgresql+psycopg://" + quote(login["HONCHO_POSTGRES_USER"], safe="") + ":"
            + quote(login["HONCHO_POSTGRES_PASSWORD"], safe="") + "@janitor-honcho-database:5432/honcho",
        "LLM_ANTHROPIC_API_KEY": values["MINIMAX_API_KEY"],
        "LLM_OPENAI_API_KEY": values["OPENAI_API_KEY"],
    }
    snapshot(home, include_profiles=False)
    private_write(home / "honcho.env", "".join(f"{key}={json.dumps(value)}\n" for key, value in sorted(runtime.items())))
    sections = ["deriver.model_config", "summary.model_config", "dream.deduction_model_config", "dream.induction_model_config",
                *[f"dialectic.levels.{level}.model_config" for level in ("minimal", "low", "medium", "high", "max")]]
    config = '[app]\nEMBED_MESSAGES = true\n[embedding]\nVECTOR_DIMENSIONS = 1536\n[embedding.model_config]\ntransport = "openai"\nmodel = "text-embedding-3-small"\n'
    for section in sections:
        config += f'\n[{section}]\ntransport = "anthropic"\nmodel = "MiniMax-M2.7"\n[{section}.overrides]\nbase_url = "https://api.minimax.io/anthropic"\n'
    if (home / "honcho.toml").exists():
        import tomllib
        tomllib.loads((home / "honcho.toml").read_text())
    else:
        private_write(home / "honcho.toml", config)
    target = home / "docker/honcho-compose.yml"
    private_write(target, (ROOT / "skills/janitor-honcho/scripts/honcho-compose.yml").read_text())
    return source


def checkout_server(source: Path) -> None:
    fresh = not source.exists()
    if fresh:
        source.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", "https://github.com/plastic-labs/honcho.git", str(source)], check=True, timeout=600)
    # A --no-checkout clone intentionally has all worktree files absent.
    if not fresh and subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True, timeout=30).strip():
        raise RuntimeError(f"Honcho source has local changes: {source}; preserve them before upgrading")
    subprocess.run(["git", "-C", str(source), "fetch", "origin", HONCHO_REF], check=True, timeout=600)
    subprocess.run(["git", "-C", str(source), "checkout", "--detach", HONCHO_REF], check=True, timeout=120)


def compose_command(home: Path, *args: str) -> list[str]:
    return ["docker", "compose", "--project-name", "janitor-honcho", "--env-file", str(home / "honcho.env"),
            "-f", str(home / "docker/honcho-compose.yml"), *args]


def verify_memory(base_url: str = "http://127.0.0.1:1973", timeout: float = 5,
                  *, api_key: str | None = None, workspace: str | None = None) -> None:
    """Health plus a real API read: a listening socket alone does not prove usable memory."""
    requests = []
    if workspace is None:
        requests.append(Request(base_url.rstrip("/") + "/health"))
        requests.append(Request(base_url.rstrip("/") + "/v3/workspaces/list", data=b"{}", headers={"Content-Type": "application/json"}))
    else:
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + (api_key or "")}
        requests.append(Request(base_url.rstrip("/") + "/v3/workspaces", data=json.dumps({"name": workspace}).encode(), headers=headers))
    for request in requests:
        with urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError("Honcho memory API is unavailable")


def probe_local_transports() -> None:
    code = (ROOT / "janitor_ext/honcho_probe.py").read_text()
    # Read the server's effective credentials/configuration and test its outbound network.
    # The command contains no secret values; the child reports only curated provider/status errors.
    try:
        subprocess.run(["docker", "exec", "janitor-honcho-api", "python", "-c", code], check=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise RuntimeError("Honcho transport readiness failed; resolve the provider error above before using local memory") from None


def _compose_owner(home: Path, state: dict) -> Path:
    """Resolve a single compose owner inside this installation, before any mutation."""
    root = Path(os.environ.get("JANITOR_HOME") or home).expanduser().resolve()
    if root.parent.name == "profiles":
        root = root.parent.parent
    if home != root and home.parent != root / "profiles":
        raise RuntimeError("Selected Honcho profile does not belong to this Janitor owner")
    labels = state.get("Config", {}).get("Labels") or {}
    paths = str(labels.get("com.docker.compose.project.config_files", "")).split(",")
    project = labels.get("com.docker.compose.project")
    if project not in ("janitor-honcho", "docker") or len(paths) != 1 or not paths[0]:
        raise RuntimeError("Existing Honcho ownership is ambiguous; repair its owner before continuing")
    compose = Path(paths[0])
    if not compose.is_absolute() or not compose.is_file():
        raise RuntimeError("Existing Honcho owner compose is unavailable; preserve its credentials before continuing")
    compose = compose.resolve()
    owner = compose.parent.parent
    if (compose != owner / "docker/honcho-compose.yml"
            or (owner != root and owner.parent != root / "profiles")):
        raise RuntimeError("Existing Honcho belongs to an external owner; it was preserved")
    # The old installer used docker/honcho-compose.yml without an explicit project.
    # Its default project may migrate only through the verified owning profile;
    # another profile must wait for that upgrade before reusing the shared daemon.
    if project == "docker" and owner != home:
        raise RuntimeError("Upgrade legacy Honcho from its owner profile before reusing this server")
    return owner


def _database_login(owner: Path, state: dict) -> dict[str, str]:
    previous = read_secrets(owner / "honcho.env")
    login = legacy_database_credentials(owner) | {key: value for key, value in previous.items()
        if key in ("HONCHO_POSTGRES_USER", "HONCHO_POSTGRES_PASSWORD")}
    actual = dict(value.split("=", 1) for value in state.get("Config", {}).get("Env", []) if "=" in value)
    for name in ("POSTGRES_USER", "POSTGRES_PASSWORD"):
        value = login.get("HONCHO_" + name)
        if not value or actual.get(name) != value:
            raise RuntimeError("Existing Honcho owner credentials cannot be verified; they were preserved")
    return login


def deploy(home: Path) -> None:
    home = home.expanduser().resolve()
    subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, check=True, timeout=30)
    # The server runs schema migrations on startup. Capture an existing database first.
    previous = subprocess.run(["docker", "inspect", "janitor-honcho-database"], capture_output=True, text=True, check=False, timeout=30)
    if previous.returncode == 0:
        state = json.loads(previous.stdout)[0]
        owner = _compose_owner(home, state)
        login = _database_login(owner, state)
        if not state["State"]["Running"]:
            raise RuntimeError("Start the existing Honcho database before upgrading so pg_dump can back it up")
        if owner != home:
            # A named profile uses its own client/workspace, while this local daemon
            # retains the owning profile's server credentials and configuration.
            api = subprocess.run(["docker", "inspect", "janitor-honcho-api"], capture_output=True, text=True, check=False, timeout=30)
            if api.returncode != 0:
                raise RuntimeError("Repair the existing Honcho owner before using its shared server")
            api_state = json.loads(api.stdout)[0]
            if _compose_owner(home, api_state) != owner or not api_state.get("State", {}).get("Running"):
                raise RuntimeError("Existing Honcho API ownership is inconsistent; repair its owner first")
            verify_memory()
            probe_local_transports()
            print("Reusing this installation's healthy Honcho server; profile and owner credentials were preserved.")
            return
        backup = snapshot(home, include_profiles=False)
        user = login["HONCHO_POSTGRES_USER"]
        dump = backup / "honcho-postgres.dump"
        with dump.open("wb") as output:
            subprocess.run(["docker", "exec", "janitor-honcho-database", "pg_dump", "-U", user, "-d", "honcho", "-Fc"], stdout=output, check=True, timeout=1800)
        record_backup_artifact(backup, dump, kind="postgres-dump")
    source = prepare_service(home)
    checkout_server(source)
    subprocess.run(compose_command(home, "build"), check=True, timeout=3600)
    from janitor_ext.volumes import migrate_compose
    migrate_compose(home / "docker/honcho-compose.yml", home / "honcho.env")
    subprocess.run(compose_command(home, "up", "-d", "--wait", "--wait-timeout", "180"), check=True, timeout=300)
    verify_memory()
    probe_local_transports()
    print("Janitor Honcho memory, embeddings and reasoning are ready; existing volumes were preserved.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    from janitor_ext.startup import janitor_home
    parser.add_argument("--home", type=Path, default=janitor_home())
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare_only:
        prepare_service(args.home.expanduser().resolve())
    else:
        deploy(args.home.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
