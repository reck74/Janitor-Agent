#!/usr/bin/env python3
"""
janitor-config-audit
Compara config.yaml y SOUL.md activos contra los assets de janitor-core.
Sin --apply: solo reporta diferencias.
Con --apply: aplica las actualizaciones automaticamente.
"""

import argparse
import os
import difflib
import sys
import yaml
from pathlib import Path

JANITOR_HOME = Path(os.environ.get("JANITOR_HOME", str(Path.home() / ".janitor")))
ASSETS_JANITOR = JANITOR_HOME / "janitor-core" / "assets" / "janitor"

FILES = {
    "config.yaml": ("config.yaml", "config.yaml"),
    "SOUL.md": ("SOUL.md", "SOUL.md"),
}


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def flatten_dict(d, parent_key="", sep="."):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def diff_configs(active_path, asset_path):
    """Devuelve lista de diferencias entre dos archivos YAML."""
    try:
        active_data = load_yaml(active_path)
        asset_data = load_yaml(asset_path)
    except yaml.YAMLError as e:
        return [f"  ERROR parseando YAML: {e}"]

    active_flat = flatten_dict(active_data) if active_data else {}
    asset_flat = flatten_dict(asset_data) if asset_data else {}

    all_keys = set(active_flat.keys()) | set(asset_flat.keys())
    diffs = []

    # Keys solo en asset (en asset pero no en activo)
    for k in sorted(all_keys - set(active_flat.keys())):
        diffs.append(f"  + {k}: {asset_flat[k]}")

    # Keys solo en activo
    for k in sorted(all_keys - set(asset_flat.keys())):
        diffs.append(f"  - {k}: {active_flat[k]}")

    # Keys con valores distintos
    for k in sorted(all_keys):
        if k in active_flat and k in asset_flat and active_flat[k] != asset_flat[k]:
            diffs.append(f"  ~ {k}:")
            diffs.append(f"      ACTIVO: {active_flat[k]}")
            diffs.append(f"      ASSET:  {asset_flat[k]}")

    return diffs


def diff_text_files(active_path, asset_path):
    """Devuelve diff estilo unificado para archivos de texto plano."""
    with open(active_path, encoding="utf-8") as f:
        active_lines = f.readlines()
    with open(asset_path, encoding="utf-8") as f:
        asset_lines = f.readlines()

    diff = list(difflib.unified_diff(
        asset_lines, active_lines,
        fromfile=str(asset_path),
        tofile=str(active_path),
        lineterm=""
    ))
    return diff


def audit_file(name, apply_mode=False):
    filename, asset_name = FILES[name]
    active_path = JANITOR_HOME / filename
    asset_path = ASSETS_JANITOR / asset_name

    if not active_path.exists():
        print(f"[{name}] ACTIVO: no existe ({active_path})")
        return False

    if not asset_path.exists():
        print(f"[{name}] ASSET: no existe ({asset_path})")
        return False

    print(f"\n{'='*60}")
    print(f"  AUDIT: {name}")
    print(f"  Activo: {active_path}")
    print(f"  Asset:  {asset_path}")
    print(f"{'='*60}")

    if filename == "config.yaml":
        diffs = diff_configs(active_path, asset_path)
    else:
        diffs = diff_text_files(active_path, asset_path)

    if not diffs:
        print(f"  [OK] Sin diferencias — archivos identicos.")
        return True

    print(f"  [{len(diffs)} diferencia(s)]")
    for d in diffs:
        print(d)

    if apply_mode:
        print(f"\n  >> Aplicando actualizacion...")
        import shutil
        backup = active_path.with_suffix(active_path.suffix + ".bak")
        shutil.copy2(active_path, backup)
        shutil.copy2(asset_path, active_path)
        print(f"  [OK] Asset aplicado. Backup en: {backup}")

        # Validar YAML si es config.yaml
        if filename == "config.yaml":
            try:
                load_yaml(active_path)
                print(f"  [OK] YAML valido tras aplicacion.")
            except yaml.YAMLError as e:
                print(f"  [FALLO] YAML invalido tras aplicacion: {e}")
                # Restaurar backup
                shutil.copy2(backup, active_path)
                print(f"  [RESTORED] Backup restaurado.")
                return False
    else:
        print(f"\n  Para aplicar: /audit-config --apply")

    return True


def main():
    parser = argparse.ArgumentParser(description="Janitor Config Audit")
    parser.add_argument("--apply", action="store_true", help="Aplicar actualizaciones automaticamente")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar diff sin aplicar (default)")
    parser.add_argument("target", nargs="?", choices=["config", "soul", "all"], default="all",
                        help="Archivo a auditar: config (config.yaml), soul (SOUL.md), all (ambos, default)")
    args = parser.parse_args()

    targets = {"config": ["config.yaml"], "soul": ["SOUL.md"], "all": ["config.yaml", "SOUL.md"]}
    selected = targets[args.target]

    results = []
    for name in selected:
        ok = audit_file(name, apply_mode=args.apply)
        results.append((name, ok))

    print(f"\n{'='*60}")
    print(f"  RESUMEN")
    print(f"{'='*60}")
    for name, ok in results:
        status = "OK" if ok else "FALLO"
        print(f"  [{status}] {name}")

    if all(ok for _, ok in results):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()