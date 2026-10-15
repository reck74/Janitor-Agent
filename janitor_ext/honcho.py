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
        subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", "https://github.com/plastic-labs/honcho.git", str(source)], check=True)
    # A --no-checkout clone intentionally has all worktree files absent.
    if not fresh and subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True).strip():
        raise RuntimeError(f"Honcho source has local changes: {source}; preserve them before upgrading")
    subprocess.run(["git", "-C", str(source), "fetch", "origin", HONCHO_REF], check=True)
    subprocess.run(["git", "-C", str(source), "checkout", "--detach", HONCHO_REF], check=True)


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
        subprocess.run(["docker", "exec", "janitor-honcho-api", "python", "-c", code], check=True)
    except subprocess.CalledProcessError:
        raise RuntimeError("Honcho transport readiness failed; resolve the provider error above before using local memory") from None


def deploy(home: Path) -> None:
    subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, check=True)
    # The server runs schema migrations on startup. Capture an existing database first.
    previous = subprocess.run(["docker", "inspect", "janitor-honcho-database"], capture_output=True, text=True, check=False)
    if previous.returncode == 0:
        state = json.loads(previous.stdout)[0]
        if not state["State"]["Running"]:
            raise RuntimeError("Start the existing Honcho database before upgrading so pg_dump can back it up")
        backup = snapshot(home, include_profiles=False)
        user = legacy_database_credentials(home).get("HONCHO_POSTGRES_USER") or read_secrets(home / "honcho.env").get("HONCHO_POSTGRES_USER")
        if not user:
            raise RuntimeError("Cannot determine existing Honcho database user; preserve its credentials before upgrading")
        dump = backup / "honcho-postgres.dump"
        with dump.open("wb") as output:
            subprocess.run(["docker", "exec", "janitor-honcho-database", "pg_dump", "-U", user, "-d", "honcho", "-Fc"], stdout=output, check=True)
        record_backup_artifact(backup, dump, kind="postgres-dump")
    source = prepare_service(home)
    checkout_server(source)
    subprocess.run(compose_command(home, "build"), check=True)
    from janitor_ext.volumes import migrate_compose
    migrate_compose(home / "docker/honcho-compose.yml", home / "honcho.env")
    subprocess.run(compose_command(home, "up", "-d", "--wait", "--wait-timeout", "180"), check=True)
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
