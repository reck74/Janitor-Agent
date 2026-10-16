"""Idempotent profile setup shared by bootstrap and Janitor Desktop."""
from __future__ import annotations

import argparse
import copy
import getpass
import json
import os
import subprocess
import tempfile
from pathlib import Path

import hermes_yaml as yaml

from janitor_ext.migrate import snapshot

ROOT = Path(__file__).resolve().parents[1]
HONCHO_REF = "e2d2aba182862deeb846e5cd4a30a41bce0ed82a"


def read_secrets(path: Path) -> dict[str, str]:
    from dotenv import dotenv_values
    return {key: value for key, value in dotenv_values(path, interpolate=False).items() if value is not None} if path.exists() else {}


def private_write(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() and path.read_text() == content:
        path.chmod(0o600)
        return False
    fd, name = tempfile.mkstemp(prefix=".janitor-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    return True


def merge_defaults(defaults: dict, current: dict) -> dict:
    result = copy.deepcopy(defaults)
    for key, value in current.items():
        result[key] = merge_defaults(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


def _is_janitor_local_endpoint(value: str | None) -> bool:
    from urllib.parse import urlparse
    import ipaddress
    if not value:
        return False
    parsed = urlparse(value)
    if parsed.port != 1973:
        return False
    host = parsed.hostname or ""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalize_honcho_connection(config: dict, mode: str, secrets: dict[str, str]) -> None:
    """Select one transport across the pinned provider's flat/native/host spellings.

    The profile owns this file. Preserve workspaces, tuning and unrelated hosts;
    credentials stay in its .env rather than stale config fields winning over it.
    """
    endpoint = "http://127.0.0.1:1973" if mode == "local" else secrets.get("HONCHO_BASE_URL") or secrets.get("HONCHO_URL")
    active_host = secrets.get("HERMES_HONCHO_HOST") or config.get("defaultHost")
    blocks = [config, *[block for name, block in config.get("hosts", {}).items()
                       if name in ("hermes", active_host) or name.startswith(("hermes_", "hermes."))]]
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("Honcho host configuration must contain an object")
        for key in ("baseUrl", "base_url", "apiKey"):
            block.pop(key, None)
        native = block.get("endpoint")
        if isinstance(native, dict):
            native.pop("baseUrl", None)
            native.pop("base_url", None)
        block["environment"] = "production"
        if endpoint:
            block["baseUrl"] = endpoint.rstrip("/")


def prepare_profile(home: Path, secrets: dict[str, str], mode: str) -> dict:
    """Missing values inherit current defaults; existing choices and persona win."""
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    from hermes_cli.config import require_readable_config_before_write
    home = home.expanduser().resolve()
    before = snapshot(home, include_profiles=False) if any((home / f).exists() for f in (".env", "config.yaml", "SOUL.md")) else None
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    overlay = require_readable_config_before_write(ROOT / "assets/janitor/config-overlay.yaml")
    current_path = home / "config.yaml"
    current = require_readable_config_before_write(current_path)
    if not isinstance(current, dict):
        raise ValueError("config.yaml must contain a mapping")
    # Existing version stays until upstream's actual migrations have run.
    baseline = merge_defaults(DEFAULT_CONFIG, overlay)
    config = merge_defaults(baseline, current)
    config.setdefault("memory", {})["provider"] = "honcho"
    config.setdefault("janitor", {})["honcho_mode"] = mode
    config["_config_version"] = current.get("_config_version", DEFAULT_CONFIG["_config_version"])
    values = read_secrets(home / ".env") | secrets
    if mode == "local":
        values["HONCHO_BASE_URL"] = "http://127.0.0.1:1973"
        values.setdefault("HONCHO_API_KEY", "janitor-local")
    else:
        for key in ("HONCHO_BASE_URL", "HONCHO_URL"):
            if _is_janitor_local_endpoint(values.get(key)):
                values.pop(key, None)
    # The pinned provider's SDK builder falls back to config.yaml after honcho.json.
    # Keep that fallback on the same transport, while preserving tuning fields.
    honcho_options = config.get("honcho")
    if isinstance(honcho_options, dict):
        endpoint = values.get("HONCHO_BASE_URL") or values.get("HONCHO_URL")
        honcho_options.pop("base_url", None)
        if endpoint:
            honcho_options["base_url"] = endpoint.rstrip("/")
    private_write(current_path, yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    private_write(home / ".env", "".join(f"{key}={json.dumps(value, ensure_ascii=False)}\n" for key, value in sorted(values.items())))
    for filename in ("SOUL.md", "honcho.json"):
        target = home / filename
        if not target.exists():
            legacy = Path.home() / ".honcho/config.json"
            source = legacy if filename == "honcho.json" and legacy.is_file() else ROOT / "assets/janitor" / filename
            if filename == "honcho.json":
                if not isinstance(json.loads(source.read_text()), dict):
                    raise ValueError("Honcho configuration must contain an object")
            private_write(target, source.read_text())
    honcho_path = home / "honcho.json"
    honcho_config = json.loads(honcho_path.read_text())
    normalize_honcho_connection(honcho_config, mode, values)
    private_write(honcho_path, json.dumps(honcho_config, indent=2) + "\n")
    skin = home / "skins/sentry-janitor.yaml"
    if not skin.exists():
        private_write(skin, (ROOT / "assets/janitor/sentry-janitor.yaml").read_text())
    for folder in ("sessions", "skills", "logs", "tmp"):
        (home / folder).mkdir(exist_ok=True, mode=0o700)
    return {"home": str(home), "backup": str(before) if before else None}


def configure_credentials(home: Path, *, non_interactive: bool, mode: str | None) -> tuple[dict, str]:
    values = read_secrets(home / ".env")
    for name in ("MINIMAX_API_KEY", "HONCHO_API_KEY", "OPENAI_API_KEY", "HONCHO_BASE_URL", "HONCHO_URL"):
        if os.environ.get(name):
            values[name] = os.environ[name]
    from hermes_cli.config import require_readable_config_before_write, load_config_readonly
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    require_readable_config_before_write(home / "config.yaml")
    token = set_hermes_home_override(home)
    try:
        config = load_config_readonly()
    finally:
        reset_hermes_home_override(token)
    mode = mode or (config or {}).get("janitor", {}).get("honcho_mode")
    if not values.get("MINIMAX_API_KEY") and not non_interactive:
        values["MINIMAX_API_KEY"] = getpass.getpass("MINIMAX_API_KEY (proveedor principal): ").strip()
    if not mode and not non_interactive:
        mode = "cloud" if input("Honcho [local/cloud] (local): ").strip().lower() == "cloud" else "local"
    mode = mode or ("cloud" if values.get("HONCHO_API_KEY") and not values.get("HONCHO_BASE_URL") else "local")
    if mode not in ("local", "cloud"):
        raise ValueError("janitor.honcho_mode must be local or cloud")
    required = ["MINIMAX_API_KEY", "HONCHO_API_KEY" if mode == "cloud" else "OPENAI_API_KEY"]
    for key in required:
        if not values.get(key) and not non_interactive:
            purpose = " (sólo embeddings de Honcho local)" if key == "OPENAI_API_KEY" else ""
            values[key] = getpass.getpass(key + purpose + ": ").strip()
        if not values.get(key):
            raise ValueError(f"Missing {key}; run janitor setup to configure {mode} Honcho")
    return values, mode


def _honcho_install_record(home: Path) -> dict | None:
    path = home / "plugins/.install-metadata.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid plugin install metadata: {path}")
    record = data.get("honcho")
    return record if isinstance(record, dict) else None


def _require_honcho_pin(home: Path) -> None:
    record = _honcho_install_record(home)
    source = str((record or {}).get("source", ""))
    repo, _, subdir = source.partition("#")
    expected = repo.removesuffix(".git").rstrip("/").lower() == "https://github.com/plastic-labs/honcho"
    if (not record or record.get("revision") != HONCHO_REF or record.get("pinned") is not True
            or not expected or subdir != "hermes-plugin-honcho"):
        raise RuntimeError(
            "Existing Honcho plugin is custom or uses a different pin; it was preserved. "
            f"Review/back it up before explicitly installing honcho --ref {HONCHO_REF}."
        )


def honcho_connection(home: Path):
    """Use the pinned provider's resolver, including its named-profile host selection."""
    from importlib import import_module
    from plugins.memory import load_memory_provider
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from agent.secret_scope import (build_profile_secret_scope, set_secret_scope, reset_secret_scope,
                                    set_multiplex_context, reset_multiplex_context)
    # Setup has just persisted credentials; the launching process may still have
    # the old endpoint/key. Bind the selected profile exactly as routed runtime does.
    values = build_profile_secret_scope(home)
    token = set_hermes_home_override(home)
    secret_token = set_secret_scope(values, profile_home=str(home))
    context_token = set_multiplex_context(True)
    try:
        provider = load_memory_provider("honcho", register_skills=False)
        if provider is None:
            raise RuntimeError("Honcho provider cannot load in the selected profile")
        client_module = import_module(type(provider).__module__ + ".client")
        return client_module.HonchoClientConfig.from_global_config(config_path=home / "honcho.json")
    finally:
        reset_multiplex_context(context_token)
        reset_secret_scope(secret_token)
        reset_hermes_home_override(token)


def verify_honcho_provider(home: Path) -> None:
    """Run only in a newly selected PM child; imported provider code alone is insufficient."""
    from pm.client import venv_is_current
    if not venv_is_current(project_root=ROOT):
        raise RuntimeError("Honcho dependencies were not admitted into the current PM environment")
    _require_honcho_pin(home)
    # The SDK is lazily imported by the provider, so probe it explicitly too.
    try:
        from honcho import Honcho
    except ImportError:
        raise RuntimeError("Honcho SDK is missing from the selected PM environment; repair its provider dependencies") from None
    if not callable(Honcho):
        raise RuntimeError("Honcho SDK does not expose its client")
    connection = honcho_connection(home)
    from hermes_cli.config import require_readable_config_before_write
    config = require_readable_config_before_write(home / "config.yaml")
    mode = config.get("janitor", {}).get("honcho_mode")
    # Match the SDK constructor's secondary YAML lookup, not just its JSON resolver.
    fallback = config.get("honcho", {})
    effective_url = connection.base_url or (fallback.get("base_url") if isinstance(fallback, dict) else None)
    if mode == "cloud" and (_is_janitor_local_endpoint(effective_url) or connection.environment != "production"):
        raise RuntimeError("Cloud Honcho still resolves to a local endpoint; repair the selected profile")
    if mode == "local" and effective_url != "http://127.0.0.1:1973":
        raise RuntimeError("Local Honcho does not resolve to the installed server; repair the selected profile")


def _verify_fresh_honcho(home: Path) -> None:
    env = dict(os.environ, HERMES_HOME=str(home), JANITOR_HOME=str(home))
    subprocess.run([str(ROOT / "scripts/janitor"), "--run-module", "janitor_ext.install",
                    "--home", str(home), "--verify-honcho"], cwd=ROOT, env=env, check=True, timeout=300)


def install_honcho_plugin() -> None:
    from hermes_constants import get_hermes_home
    home = get_hermes_home()
    target = home / "plugins/honcho"
    if target.is_symlink():
        raise RuntimeError("Existing linked Honcho plugin was preserved; review it before installing the Janitor pin")
    if target.exists():
        # Re-running installation must not replace personalized plugin code.
        _require_honcho_pin(home)
    else:
        from hermes_cli.plugins_cmd_install import dashboard_install_plugin
        result = dashboard_install_plugin("", force=False, enable=True, catalog_name="honcho",
                                          ref=HONCHO_REF, assume_deps_consent=True)
        if not isinstance(result, dict) or not result.get("ok"):
            detail = result.get("error", "unknown plugin admission error") if isinstance(result, dict) else "invalid installer result"
            raise RuntimeError(f"Honcho plugin installation failed: {detail}")
        _require_honcho_pin(home)
    from hermes_cli.memory_setup import prepare_memory_provider_dependencies
    prepare_memory_provider_dependencies("honcho")
    _verify_fresh_honcho(home)


def publish_commands(root: Path, home: Path) -> None:
    from hermes_cli._launchers import ensure_install_launchers
    written = ensure_install_launchers(root, root / ".hermes/bin")
    if not written:
        raise RuntimeError("PM did not publish an installation-bound launcher")
    target = Path.home() / ".local/bin/janitor"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not target.is_symlink():
        raise RuntimeError(f"Refusing to replace unmanaged command: {target}")
    target.unlink(missing_ok=True)
    target.symlink_to(root / "scripts/janitor")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    from janitor_ext.startup import janitor_home
    parser.add_argument("--home", type=Path, default=janitor_home())
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--honcho-mode", choices=("local", "cloud"))
    parser.add_argument("--profile-only", action="store_true", help="Prepare files; deployment is completed by bootstrap")
    parser.add_argument("--publish-only", action="store_true")
    parser.add_argument("--verify-honcho", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.home = args.home.expanduser().resolve()
    os.environ["HERMES_HOME"] = str(args.home.expanduser().resolve())
    if args.verify_honcho:
        verify_honcho_provider(args.home)
        return 0
    if args.publish_only:
        publish_commands(ROOT, args.home)
        return 0
    if not args.profile_only:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, check=True, timeout=30)
    values, mode = configure_credentials(args.home, non_interactive=args.non_interactive, mode=args.honcho_mode)
    result = prepare_profile(args.home, values, mode)
    # prepare_profile normalizes mode-dependent endpoints; never use stale
    # credentials/URLs captured before switching from local to cloud memory.
    values = read_secrets(args.home / ".env")
    if not args.profile_only:
        install_honcho_plugin()
        if mode == "local":
            subprocess.run(["bash", str(ROOT / "skills/janitor-honcho/scripts/deploy.sh")], check=True, timeout=18000)
        else:
            from janitor_ext.honcho import verify_memory
            connection = honcho_connection(args.home)
            verify_memory(connection.base_url or "https://api.honcho.dev",
                          api_key=connection.api_key, workspace=connection.workspace_id)
        from janitor_ext.migrate import migrate
        result["migration"] = migrate(args.home, apply=True)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
