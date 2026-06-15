#!/bin/bash
# migrate-janitor-v0.16.0.sh
# Migración de v0.15.x → v0.16.0 (Hermes upstream #43354)
#
# Cambios:
# - `memory.write_mode` y `skills.write_mode` (tri-state) se renombran a
#   `write_approval` (boolean, default false).
#   Mapeo: 'approve' → true; 'on' / 'off' / unset → false
# - `_config_version` se incrementa 28 → 29.
# - Slash commands: '/memory mode <on|off|approve>' → '/memory approval <on|off>'
#   (mode se mantiene como alias de back-compat).
#
# Ejecutar como usuario, NO como root. Idempotente: corre varias veces sin daño.

set -euo pipefail

CONFIG="${JANITOR_CONFIG:-$HOME/.janitor/config.yaml}"

if [ ! -f "$CONFIG" ]; then
  echo "No config at $CONFIG — nothing to migrate"
  exit 0
fi

# Backup before editing
BACKUP="${CONFIG}.v0.15.bak"
if [ ! -f "$BACKUP" ]; then
  cp "$CONFIG" "$BACKUP"
  echo "Backed up: $BACKUP"
fi

python3 - "$CONFIG" <<'PY'
import sys
import yaml
from pathlib import Path

p = Path(sys.argv[1])
data = yaml.safe_load(p.read_text()) or {}

migrated = []

for section in ('memory', 'skills'):
    sub = data.get(section) or {}
    if not isinstance(sub, dict):
        continue
    mode = sub.pop('write_mode', None)
    if mode is not None:
        sub['write_approval'] = (mode == 'approve')
        migrated.append(f"{section}.write_mode ({mode!r}) → {section}.write_approval ({sub['write_approval']})")

# Bump config version (only if lower than 29)
old_version = int(data.get('_config_version', 0) or 0)
if old_version < 29:
    data['_config_version'] = 29
    migrated.append(f"_config_version: {old_version} → 29")

if migrated:
    p.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    print("Migrated:")
    for line in migrated:
        print(f"  {line}")
else:
    print("No changes needed (already on v0.16.0 schema or no write_mode keys)")
PY

echo
echo "Post-migration: review $CONFIG and run 'janitor --version' to confirm."
