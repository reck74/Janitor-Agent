#!/usr/bin/env bash
# Janitor desktop app launcher (Arch package janitor-desktop-bin).
# Extra Electron options go in ${XDG_CONFIG_HOME:-$HOME/.config}/janitor-desktop-flags.conf,
# one per line; blank lines and lines starting with # are ignored.
set -euo pipefail

appdir=${JANITOR_DESKTOP_APPDIR:-/opt/janitor-desktop}
flags_file="${XDG_CONFIG_HOME:-$HOME/.config}/janitor-desktop-flags.conf"

flags=()
if [[ -r "$flags_file" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    # Trim surrounding whitespace.
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    flags+=("$line")
  done <"$flags_file"
fi

exec "$appdir/Janitor" "${flags[@]}" "$@"
