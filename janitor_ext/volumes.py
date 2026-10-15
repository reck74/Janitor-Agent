"""Preserve legacy Janitor data while adopting stable Compose project/volume names."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import uuid

COPY_IMAGE = "alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8"


def _run(*args, check=True):
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True)


def _inspect(kind: str, name: str):
    result = _run(kind, "inspect", name, check=False) if kind == "volume" else _run("inspect", name, check=False)
    if result.returncode:
        # Absence is expected; daemon/auth failures must never masquerade as a fresh installation.
        if "no such" in result.stderr.lower():
            return None
        raise RuntimeError(f"Cannot inspect Docker {kind} {name}: {result.stderr.strip()}")
    return json.loads(result.stdout)[0]


def migration_plan(model: dict, existing: dict) -> list[tuple[str, str]]:
    """Map mounts by destination, independent of historical Compose project names."""
    project = model.get("name", "")
    if not project.startswith("janitor-"):
        raise ValueError("A Janitor Compose project must have an explicit janitor- name")
    result = set()
    for service in model["services"].values():
        name = service.get("container_name", "")
        if not name.startswith("janitor-"):
            raise ValueError("Refusing a non-Janitor container")
        current = existing.get(name)
        if not current:
            continue
        mounts = {m["Destination"]: m for m in current.get("Mounts", [])}
        for mount in service.get("volumes", []):
            if mount.get("type") != "volume":
                continue
            key = mount["source"]
            target = model.get("volumes", {}).get(key, {}).get("name", key)
            if not target.startswith("janitor-"):
                raise ValueError("A Janitor volume must have an explicit janitor- name")
            old = mounts.get(mount["target"])
            if old and old.get("Type") != "volume":
                raise ValueError(f"Refusing to replace a bind mount at {name}:{mount['target']}")
            if old and old.get("Name") != target:
                result.add((old["Name"], target))
    return sorted(result)


def migrate_compose(compose: Path, env_file: Path) -> list:
    config = _run("compose", "-f", str(compose), "--env-file", str(env_file), "config", "--format", "json")
    model = json.loads(config.stdout)
    names = {s["container_name"] for s in model["services"].values()}
    existing = {name: data for name in names if (data := _inspect("container", name)) is not None}
    plan = migration_plan(model, existing)
    receipt_path = compose.parent / f"{model['name']}-volume-migration.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    pending = []
    for source, target in plan:
        if receipt.get(target, {}).get("completed") is True and receipt.get(target, {}).get("source") == source and _inspect("volume", target) is not None:
            continue
        if _inspect("volume", target) is not None:
            raise RuntimeError(f"{target} already exists without a completed migration receipt; inspect it before retrying. {source} is intact.")
        consumers = _run("ps", "-a", "--filter", f"volume={source}", "--format", "{{.Names}}").stdout.splitlines()
        if set(consumers) - names:
            raise RuntimeError(f"Legacy volume {source} is shared with another stack; stop and migrate it explicitly")
        pending.append((source, target))
    legacy = {name: data for name, data in existing.items()
              if (data.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project") != model["name"]}
    if not pending and not legacy:
        return []
    # Acquire the copy utility before stopping anything. No source data is ever mounted writable.
    if pending:
        _run("pull", COPY_IMAGE)
    running = [name for name, data in existing.items() if data.get("State", {}).get("Running")]
    renamed = []
    try:
        if running:
            _run("stop", *running)
        for source, target in pending:
            _run("volume", "create", "--label", f"janitor.migrated-from={source}", target)
            _run("run", "--rm", "--name", "janitor-volume-copy-" + uuid.uuid4().hex[:10],
                 "--network", "none", "--read-only", "--mount", f"type=volume,src={source},dst=/from,readonly",
                 "--mount", f"type=volume,src={target},dst=/to", COPY_IMAGE,
                 "sh", "-ec", "set -o pipefail; cd /from; tar cf - . | tar xpf - -C /to")
            receipt[target] = {"source": source, "completed": True}
            temporary = receipt_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(receipt, indent=2) + "\n")
            temporary.replace(receipt_path)
        # Keep legacy stopped containers too: naming is reversible, and volumes remain untouched.
        for name in sorted(legacy):
            saved = "janitor-legacy-" + name.removeprefix("janitor-") + "-" + uuid.uuid4().hex[:8]
            _run("rename", name, saved)
            renamed.append((name, saved))
    except Exception:
        for original, saved in reversed(renamed):
            _run("rename", saved, original, check=False)
        if running:
            _run("start", *running, check=False)
        raise
    return [{"source": source, "target": target} for source, target in pending]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    args = parser.parse_args(argv)
    result = migrate_compose(args.compose, args.env_file)
    if result:
        print(json.dumps({"preservedLegacyVolumes": result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
