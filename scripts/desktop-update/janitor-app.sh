# janitor-app.sh -- Janitor's half of the desktop update hand-off (fork-only).
# Sourced by posix.sh; never executed on its own.
#
# Plan docs/janitor/plans/actualizacion-automatica.md, Fase 9 (F9-06). The app
# downloads and verifies the new installer BEFORE it closes and passes it here;
# this file installs it BEFORE the engine is touched (plan 4.1):
#
#   app installed, engine updated   → the new app reopens, "all updated"
#   app NOT installed               → the engine is left alone, the previous app
#                                     reopens and says exactly why
#   app installed, engine failed    → the new app reopens and offers the engine
#                                     update again (same delivery, same commit)
#
# The app always reopens. The step reached is written to
# $HERMES_HOME/desktop-update/paso.json for whoever diagnoses a cut delivery;
# nothing reads it back: the same delivery is finished because the app compares
# its own version and the engine's commit with the signed manifest again.
#
# Arguments (parsed in posix.sh, all optional; none = today's engine-only run):
#   --target-commit <sha>      engine commit of the signed manifest (janitor update --commit)
#   --app-kind <kind>          appimage | pacman: how the app says it was installed
#   --app-version <v>          version being installed, for messages
#   --app-installer <path>     the verified installer; absent = engine only
#   --app-sha256 <hex> --app-size <bytes>
#   --app-manifest <path> --app-manifest-sig <path>   the signed manifest (pacman)
#
# Linux only. Never sudo, never a password: on Arch the system asks for it
# through polkit (pkexec) and the package's own root helper verifies everything
# again on its own copy (plan section 8, finding 1). Every message is Spanish.

JANITOR_TARGET_COMMIT="" JANITOR_APP_KIND="" JANITOR_APP_VERSION=""
JANITOR_APP_INSTALLER="" JANITOR_APP_SHA256="" JANITOR_APP_SIZE=""
JANITOR_APP_MANIFEST="" JANITOR_APP_MANIFEST_SIG=""
JANITOR_APP_STATE="none"   # none | installed | failed
JANITOR_APP_FAIL_CODE=0 JANITOR_APP_FAIL_MSG=""
JANITOR_ARCH_HELPER=/usr/lib/janitor-desktop/janitor-update-helper
JANITOR_RELEASES_URL="https://github.com/reck74/Janitor-Agent/releases/latest"

janitor_args_valid() { # the app builds these; anything else is refused before any work
  case "$JANITOR_TARGET_COMMIT" in
    "") ;;
    *[!0-9a-f]*) return 1 ;;
    *) [ "${#JANITOR_TARGET_COMMIT}" -eq 40 ] || return 1 ;;
  esac
  case "$JANITOR_APP_KIND" in ""|appimage|pacman) ;; *) return 1 ;; esac
  case "$JANITOR_APP_VERSION" in *[!0-9A-Za-z.-]*) return 1 ;; esac
  if [ -n "$JANITOR_APP_INSTALLER" ]; then
    case "$JANITOR_APP_KIND" in appimage|pacman) ;; *) return 1 ;; esac
    case "$JANITOR_APP_INSTALLER" in /*) ;; *) return 1 ;; esac
    case "$JANITOR_APP_SHA256" in *[!0-9a-f]*|"") return 1 ;; esac
    [ "${#JANITOR_APP_SHA256}" -eq 64 ] || return 1
    case "$JANITOR_APP_SIZE" in *[!0-9]*|"") return 1 ;; esac
    [ -n "$JANITOR_TARGET_COMMIT" ] || return 1
  fi
  return 0
}

janitor_note_step() { # step -- where this delivery got to, for people (nothing reads it back)
  local dir="$HERMES_HOME/desktop-update"
  mkdir -p "$dir" 2>/dev/null || return 0
  printf '{"version":"%s","commit":"%s","kind":"%s","step":"%s","at":%s}\n' \
    "$(json_escape "$JANITOR_APP_VERSION")" "$(json_escape "$JANITOR_TARGET_COMMIT")" \
    "$(json_escape "$JANITOR_APP_KIND")" "$(json_escape "$1")" "$(date +%s)" \
    > "$dir/paso.json.tmp" 2>/dev/null && mv -f "$dir/paso.json.tmp" "$dir/paso.json" 2>/dev/null || true
  log "JANITOR: step $1 (version ${JANITOR_APP_VERSION:-?}, commit ${JANITOR_TARGET_COMMIT:-?})"
}

janitor_app_fail() { # code message
  JANITOR_APP_STATE=failed JANITOR_APP_FAIL_CODE="$1"
  JANITOR_APP_FAIL_MSG="No se instaló la app nueva: $2 El motor no se tocó; sigues con la versión que tenías."
  janitor_note_step "app-fallida"
  log "JANITOR: app install failed ($1): $2"
  return 1
}

janitor_sha256_of() { # file → hex on stdout
  local out
  out="$(sha256sum -- "$1" 2>/dev/null)" || return 1
  printf '%s' "${out%% *}"
}

# AppImage: copy next to the running file, verify the COPY (what will actually
# run: the downloaded file could have been swapped after the app checked it),
# then rename over the old one -- atomic, the old file stays until that instant.
janitor_install_appimage() {
  local target="${APPIMAGE:-}" dir staged
  case "$target" in /*) ;; *) janitor_app_fail 21 "no se sabe qué archivo AppImage está en uso."; return 1 ;; esac
  [ -f "$target" ] || { janitor_app_fail 21 "el AppImage en uso ($target) ya no existe."; return 1; }
  dir="$(dirname -- "$target")"
  [ -w "$dir" ] || { janitor_app_fail 22 "no tienes permiso de escritura en $dir. Mueve el AppImage a una carpeta tuya o reemplázalo a mano por el de $JANITOR_RELEASES_URL."; return 1; }
  staged="$dir/.$(basename -- "$target").janitor-nuevo.$$"
  rm -f -- "$dir/.$(basename -- "$target").janitor-nuevo."* 2>/dev/null   # left by a run that was cut
  cp -f -- "$JANITOR_APP_INSTALLER" "$staged" 2>/dev/null \
    || { rm -f -- "$staged" 2>/dev/null; janitor_app_fail 23 "no se pudo copiar el AppImage nuevo a $dir (¿disco lleno?)."; return 1; }
  if [ "$(stat -c %s -- "$staged" 2>/dev/null)" != "$JANITOR_APP_SIZE" ] \
      || [ "$(janitor_sha256_of "$staged")" != "$JANITOR_APP_SHA256" ]; then
    rm -f -- "$staged" 2>/dev/null
    janitor_app_fail 24 "el archivo descargado ya no coincide con el que se verificó (cambió después de descargarlo)."
    return 1
  fi
  chmod --reference="$target" -- "$staged" 2>/dev/null || true
  chmod u+x -- "$staged" 2>/dev/null \
    || { rm -f -- "$staged" 2>/dev/null; janitor_app_fail 23 "no se pudo preparar el AppImage nuevo."; return 1; }
  mv -f -- "$staged" "$target" 2>/dev/null \
    || { rm -f -- "$staged" 2>/dev/null; janitor_app_fail 23 "no se pudo reemplazar $target."; return 1; }
  return 0
}

# Arch: the package's own root helper, through polkit. This process checks
# nothing on root's behalf: the helper copies the three files into a private
# root folder and verifies signature, size, sum, name, version and
# architecture there before it runs pacman.
janitor_install_pacman() {
  local manual="Para instalarla a mano: sudo pacman -U $JANITOR_APP_INSTALLER" rc=0 err
  [ -x "$JANITOR_ARCH_HELPER" ] \
    || { janitor_app_fail 25 "el paquete instalado no trae el actualizador. $manual"; return 1; }
  command -v pkexec >/dev/null 2>&1 \
    || { janitor_app_fail 25 "falta pkexec (paquete polkit), que es quien pide la contraseña del sistema. $manual"; return 1; }
  [ -n "$JANITOR_APP_MANIFEST" ] && [ -n "$JANITOR_APP_MANIFEST_SIG" ] \
    || { janitor_app_fail 25 "falta el manifiesto firmado de la versión."; return 1; }
  err="$(pkexec "$JANITOR_ARCH_HELPER" "$JANITOR_APP_INSTALLER" "$JANITOR_APP_MANIFEST" "$JANITOR_APP_MANIFEST_SIG" 2>&1 >/dev/null)" || rc=$?
  [ -n "$err" ] && printf '%s\n' "$err" >> "$LOG" 2>/dev/null
  case "$rc" in
    0) return 0 ;;
    126) janitor_app_fail 26 "cancelaste la contraseña del sistema." ;;
    127) janitor_app_fail 27 "el sistema no pudo pedir la contraseña (no hay agente de permisos en esta sesión, o no estás autorizado). $manual" ;;
    12) janitor_app_fail 28 "la firma de la versión no es válida para este paquete instalado." ;;
    13) janitor_app_fail 24 "el paquete descargado no es el que describe el manifiesto firmado (cambió después de verificarlo, o el manifiesto no lo incluye)." ;;
    15) janitor_app_fail 28 "el paquete publicado es más viejo que el instalado: no se baja de versión." ;;
    16) janitor_app_fail 29 "pacman no pudo instalar el paquete (detalle en el registro de la actualización). $manual" ;;
    17) janitor_app_fail 29 "ya hay otra actualización de la app en curso." ;;
    *) janitor_app_fail 29 "el actualizador del paquete lo rechazó (código $rc; detalle en el registro de la actualización)." ;;
  esac
  return 1
}

# The app stage. Returns nonzero when the app was due and did not get installed:
# the caller must then leave the engine alone.
janitor_install_app() {
  [ -n "$JANITOR_APP_INSTALLER" ] || return 0
  janitor_note_step "inicio"
  publish_stage "Instalando la app nueva"
  if [ ! -f "$JANITOR_APP_INSTALLER" ]; then
    janitor_app_fail 20 "el instalador descargado ya no está en $JANITOR_APP_INSTALLER."
    return 1
  fi
  case "$JANITOR_APP_KIND" in
    appimage) janitor_install_appimage || return 1 ;;
    pacman) janitor_install_pacman || return 1 ;;
  esac
  JANITOR_APP_STATE=installed
  janitor_note_step "app-instalada"
  return 0
}

# Relaunch gate for an install kind the app vouched for: the app is reopened
# whatever happened (plan 4.1), from the AppImage file or the installed binary.
# Returns nonzero for an unknown kind: posix.sh's own gate decides then.
janitor_gate() {
  case "$JANITOR_APP_KIND" in
    appimage)
      appimage_relaunch_target || return 1 ;;
    pacman)
      [ -n "$RELAUNCH_TARGET" ] && [ -f "$RELAUNCH_TARGET" ] && [ -x "$RELAUNCH_TARGET" ] || return 1 ;;
    *) return 1 ;;
  esac
  GATE=relaunch GATE_MSG=""
  return 0
}

# FINAL_MSG for a run that carried a delivery (engine exit code in $1).
janitor_final_message() {
  local code="$1" v="${JANITOR_APP_VERSION:+ $JANITOR_APP_VERSION}"
  if [ "$code" -eq 0 ]; then
    janitor_note_step "completa"
    if [ "$JANITOR_APP_STATE" = "installed" ]; then
      FINAL_MSG="Actualización completa: app y motor de Janitor${v} instalados."
    elif [ -n "$JANITOR_TARGET_COMMIT" ]; then
      FINAL_MSG="Actualización completa: motor de Janitor${v} instalado."
    fi
  elif [ "$JANITOR_APP_STATE" = "installed" ]; then
    janitor_note_step "motor-fallido"
    FINAL_MSG="La app nueva${v} quedó instalada, pero el motor no se pudo actualizar (salida $code). Vuelve a pulsar «Actualizar ahora»: se termina la misma actualización."
  fi
}
