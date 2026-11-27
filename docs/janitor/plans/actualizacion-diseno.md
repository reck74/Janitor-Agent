# F1-21 — Diseño: contrato único de actualización

Complementa `janitor-desktop-app.md` (sección 4.5, filas F1-09, F1-12, F1-17, F1-19,
F1-20, F1-21, F5-03). Diseño producido el 2026-11-22 por un subagente **solo leyendo
código**: no se ejecutó ninguna prueba, compilación ni actualización. Etiquetas:
**[leído]** = comprobado leyendo el código citado, **[inferido]** = deducción sin
verificar. Rutas relativas a la raíz; `main.ts` = `apps/desktop/electron/main.ts`.

## 1. Mapa actual

| Entrada | Proceso que lanza | Código que corre | Termina bien | Falla | Se interrumpe |
|---|---|---|---|---|---|
| **App** (botón «Actualizar ahora») | `applyUpdates` → `applyUpdatesPosixHandoff` (`main.ts:4194-4214`, `:4791`) lanza `bash <motor>/scripts/desktop-update/posix.sh --install-root … --branch <HEAD> --desktop-pid … --relaunch-target <execPath>` desacoplado y **sale** (`main.ts:4834-4911`). Pasa `--gateway` salvo conexión remota (`main.ts:4842-4844`, `posix.sh:767-771`) **[leído]** | `posix.sh` se re-ejecuta con `setsid` (`:651-669`), escribe el marcador (`:694`), espera a que la app muera (`:702-708`) y, si existe `venv/bin/janitor`, ejecuta `janitor update --yes --gateway --keep-stash --branch <rama>` (`:736-739`, `:774`) → intercepto `janitor/cli.py:66-73` → `janitor/update_bootstrap.py:31-40` → `janitor/update_core.py:1449` **[leído]** | Con AppImage `linux_gate` da siempre `skew` (`posix.sh:316-319`): no relanza, escribe `manual:true` con el texto español de `:318` (`:438-439`, `:452-464`). El usuario ve la ventana `ui.html` («Update complete» + mensaje) solo si su navegador por defecto es Chromium (`:207-230`); sin ventana, `notify-send` con título «Hermes update» (`:126-157`, solo `manual|error`). Al reabrir a mano, diálogo «La actualización terminó, pero falta un paso más» con `detail` = mensaje (`main.ts:2589-2601`, traducido en `brand/literals.mjs:44-45`) **[leído]** | Resultado `ok:false` (`posix.sh:445-449`); diálogo de error con «Volver a intentar / Abrir registro» al siguiente arranque (`main.ts:2604-2630`, traducido); el `detail` lleva `FINAL_MSG` en **inglés** (`posix.sh:705,718,748,791,809,816,822`) **[leído]** | Señal atrapada → `FINAL_MSG` inglés «Update hand-off was interrupted by…» (`:102`). `kill -9` → sin archivo de resultado: la app reabre sin decir nada. Marcador caduca por PID muerto o 20 min (`hermes_cli/update_lock.py:125`) **[leído]** |
| **Terminal** (`janitor update`) | El propio proceso | Intercepto `janitor/cli.py:66-73` → `update_core.run_janitor_update` **[leído]** | Salida en **inglés** terminada en «✓ Janitor Agent updated successfully! / Restart Janitor to use the new version.» (`update_core.py:1734-1736`) **[leído]** | `✗ …` en inglés y código 1; 2 si hay otro dueño del bloqueo, con el texto inglés de upstream «Another Hermes update is already running… run `hermes update`» (`update_core.py:1509-1512` → `hermes_cli/update_lock.py:132-143`) **[leído]** | Ctrl+C → «✗ Update cancelled.», reaplica el autostash, 130 (`update_core.py:1739-1743`) **[leído]** |
| **TUI** (`/update`) | TUI clásico: `_pending_relaunch=["update"]` (`hermes_cli/cli_commands_mixin.py:2694-2715`, `cli.py:1500-1502`); TUI Ink: sale con código 42 (`ui-tui/src/app/slash/commands/core.ts:150-163`) y `main_tui_launch.py:821-824` relanza **[leído]** | `hermes_cli/relaunch.py:62-101`: usa `sys.argv[0]` si es ejecutable (→ `~/.local/bin/janitor update`, intercepto Janitor); si no, `which hermes`; si no, `python -m hermes_cli.main update` (**flujo de upstream**) **[leído; qué rama se toma en una instalación real: inferido]** | Igual que terminal. El modal previo dice «Update Hermes Agent… run `hermes update`» en inglés (`cli_commands_mixin.py:2702-2708`) **[leído]** | Igual que terminal |
| **Mensajería** (`/update`) | `_handle_update_command` escribe `.update_pending.json`, borra `.update_exit_code` y llama a `_spawn_detached_update` (`gateway/slash_commands.py:1263-1306`); el plugin lo envuelve y pasa `[python, -m, janitor.cli]` (`janitor/plugin/gateway_update.py:21-44`) → `setsid bash -c "… update --gateway > .update_output.txt; printf rc > .update_exit_code"` (`slash_commands.py:131-160`) **[leído]** | Mismo intercepto → `update_core`; con `--gateway` escribe `.update_exit_code` antes de reiniciar la flota (`update_core.py:1724-1732`) **[leído]** | El vigilante retransmite `.update_output.txt` al chat cada 4 s (en **inglés**) y al ver el código envía «✅ Actualización de Janitor terminada.» (`gateway/run_notifications.py:658-700`, `janitor/locales/es.yaml:136`). Si el reinicio mató al gateway, el siguiente lo notifica al arrancar (`:730-800`) **[leído]** | «❌ La actualización de Janitor falló…» + últimas líneas (`run_notifications.py:793-795`, `es.yaml:138`) **[leído]** | Sin código en 30 min → escribe 124 y «no terminó en 30 minutos» (`run_notifications.py:722-728`) **[leído]** |

Notas del mapa:
- `posix.sh` y `ui.html` viven en el **checkout del motor** (`apps/desktop/electron/updater-process.ts:115`), no en el AppImage: se actualizan con el motor, pero cada actualización corre la copia **anterior** al pull. Un cambio de texto en `posix.sh` se ve a partir de la actualización siguiente a la que lo trae **[leído / inferido]**.
- Con `skew`, la app **no** se relanza (`posix.sh:452-464`): el usuario se queda sin ventana hasta reabrir el AppImage, que sigue siendo el viejo **[leído]**.
- La pregunta con botones de Telegram («Update needs your input» / «✓ Yes» / «✗ No», `plugins/platforms/telegram/adapter.py:4221-4229`) solo aparece si el actualizador escribe `.update_prompt.json`; `update_core.py` nunca llama a `_gateway_prompt` (`hermes_cli/update_cmd.py:243-250`), así que en el flujo Janitor es inalcanzable **[leído: grep sin coincidencias en `update_core.py`]**.

## 2. Componentes y sus versiones

| Componente | Cómo sabe su versión hoy | De dónde se actualiza | Combinación incompatible y detección |
|---|---|---|---|
| **App** (AppImage) | `install-stamp.json` con el commit de la compilación (`apps/desktop/scripts/write-build-stamp.mjs`; en una etiqueta se fija el SHA y la rama pasa a `main`, `.github/workflows/janitor-desktop-release.yml:56`). `app.getVersion()` = `apps/desktop/package.json` `0.17.6` (versión de upstream); el artefacto sale como `Janitor-0.17.6-linux-x86_64.AppImage` (`electron-builder.janitor.json:5`) **[leído; nombre exacto: inferido]** | Solo a mano: release `v*` del fork (`janitor-desktop-release.yml:18,94-96`). Ningún enlace de la app apunta ahí: «Obtener el instalador» y «Abrir la página de descarga» llevan a `hermes-agent.nousresearch.com` (`src/app/settings/about-settings.tsx:27`, `src/app/updates-overlay.tsx:46`; ningún parche de `apps/desktop-janitor/brand/` los cambia) **[leído]** | Upstream detecta «renderer atrasado» comparando el commit del sello con el `HEAD` del motor en rutas de `apps/desktop` (`electron/bundle-skew.ts:69-77`, `main.ts:18286-18319`); solo se muestra en Ajustes → Acerca de y es un aviso, no un bloqueo. **No hay comprobación de incompatibilidad dura**: un motor que cambie el contrato de arranque (`python -m janitor.cli serve`, parche P3) deja una app que no arranca sin explicar por qué **[leído / inferido]** |
| **Motor** (checkout git en `~/.janitor/hermes-agent`) | `pyproject.toml:5` / `hermes_cli/__init__.py:6` = `0.21.5+janitor.1`, mostrado como `0.21.5-janitor.1` (`janitor/version.py`). Las etiquetas del repo no siguen ese esquema de forma sistemática (`v0.16.0-janitor.1`, `v0.1.x`) **[leído]** | `origin/<rama>` (por defecto `main`), sea cual sea `origin` (`update_core.py:526-547,572-612`). La app compara con la punta de la rama vía API de GitHub (`main.ts:3348-3401`, `:3418-3440`), no con releases **[leído]** | Sin contrato con la app. El motor avanza commit a commit; el AppImage, etiqueta a etiqueta **[leído]** |
| **Plugin de escritorio** | Digest sha256 por archivo en `plugins/janitor/.janitor-shipped.json` (`janitor/desktop_plugin/__init__.py:36-45,83-114`) **[leído]** | Copiado del motor al home en cada arranque del lanzador (`janitor/seed.py:202-204` ← `janitor/cli.py:93-96`), incluido el `serve` de la app. Un gateway como servicio arranca por `hermes_cli.main` (`hermes_cli/gateway_service_unit.py:223`) y no lo sincroniza **[leído]** | `plugin.js` corre en el renderer del AppImage: su compatibilidad es la de app↔motor. No se detecta **[inferido]** |
| **Layout del home** | `LAYOUT_VERSION = 2` (`janitor/home.py:17`), marcador `.layout_version` **[leído]** | `auto_migrate()` en `janitor/cli.py:361-363` (lanzador). `update_core` no migra (directiva 13) **[leído]** | Tras `janitor update`, un gateway reiniciado por systemd corre código nuevo por `hermes_cli.main` sin migrar hasta que alguien arranque el lanzador **[inferido]** |
| **Catálogo de skills** | `schema: 1` (`janitor/catalog.yaml:20`); sin versión propia, va con el motor **[leído]** | `apply_quietly` en cada arranque del lanzador (`janitor/cli.py:127-129`) y tras un pull (`update_core.py:1305-1319,1640`) **[leído]** | Coherente con el motor salvo el caso de interrupción de la sección 3.4 **[leído]** |

## 3. Contrato propuesto

### 3.1 Origen único y esquema de versión
- **Origen único:** `reck74/Janitor-Agent`. El motor sigue `origin/main` (sin cambios: el
  actualizador de la app, `update_core` y el sello de las compilaciones de etiqueta ya lo
  suponen). Las **releases** son etiquetas `v<versión mostrada>` (`v0.21.5-janitor.1`) sobre
  `main`; cada release adjunta un AppImage. Una comprobación de CI exige que la etiqueta sea
  igual a `display_version(pyproject)`.
- **Nombre estable del AppImage:** `Janitor-linux-x86_64.AppImage` (sin la versión de upstream,
  que engaña). Así `https://github.com/reck74/Janitor-Agent/releases/latest` lleva siempre al
  correcto, y el glob del workflow (`Janitor-*.AppImage`) sigue valiendo.

### 3.2 Compatibilidad app↔motor (mecanismo de menor huella)
- **Un entero de contrato** en un archivo del fork, legible sin Python:
  `janitor/desktop-compat.json` → `{"contract": N, "release_url": "https://github.com/reck74/Janitor-Agent/releases/latest"}`.
  Se sube `N` solo cuando el motor exige una app nueva (cambia el arranque del backend, el
  RPC que usa la app, o la API que usa `plugin.js`).
- **La app compilada hornea su N** al compilar: `apps/desktop-janitor/scripts/build.mjs` lee el
  archivo y un parche de construcción inyecta la constante en `main.ts`.
- **Comprobación al arrancar, antes de lanzar el backend** (parche de `main.ts`): lee
  `<resolveUpdateRoot()>/janitor/desktop-compat.json` (`main.ts:3245-3253`).
  - motor N > app N → diálogo bloqueante en español con botón «Abrir la descarga»
    (`release_url`) y «Salir». La app **no** arranca el backend. Nunca queda una app que no
    arranca sin explicación.
  - motor N < app N (app nueva, motor viejo) → abre la vista de actualizaciones con
    «Actualizar motor» (flujo normal).
  - archivo ausente (motor anterior a este contrato) → compatible.
- **Aviso previo en la app:** `checkUpdates` ya pide la punta de `main` a la API de GitHub;
  con un tercer pedido del archivo en `targetSha` la tarjeta «Actualizar ahora» puede avisar
  «esta versión del motor necesita la app nueva; descárgala después». No bloquea.
- **Aviso en terminal y Telegram:** `update_core` compara `contract` antes y después del pull
  y, si subió, termina con «Esta versión necesita la app nueva: <release_url>».
- `bundle-skew` de upstream se conserva como aviso blando (Acerca de), con su enlace
  reapuntado a `release_url`.

### 3.3 Caso AppImage tras actualizar el motor
1. `posix.sh` actualiza el motor y `linux_gate` da `skew` (sin cambio de decisión).
2. **Relanzar el AppImage viejo** cuando exista `$APPIMAGE` (variable del runtime de AppImage,
   heredada porque la app pasa `...process.env` al lanzar `posix.sh`, `main.ts:4866-4872`
   **[leído; que el runtime la defina: inferido]**). Es seguro porque la comprobación de 3.2
   decide al arrancar. Sin `$APPIMAGE` (deb/rpm) se mantiene el `manual` actual.
3. El mensaje de `skew` pasa a ser neutro, porque `posix.sh` no conoce el contrato:
   «Motor actualizado. Janitor se vuelve a abrir solo; si necesita la app nueva, te lo dirá
   ahí mismo con el enlace de descarga.» Quien juzga la compatibilidad es la app al arrancar.
4. Al arrancar: si es compatible, sigue normal (y el aviso blando de `bundle-skew` si
   aplica); si no, el diálogo de 3.2 con el enlace al release. Texto propuesto del diálogo:
   «Esta app es más vieja que el motor que acabas de instalar. Descarga la nueva desde el
   enlace, reemplaza el AppImage y ábrela. Tus chats y ajustes no se tocan.»

### 3.4 Bloqueo compartido, interrupción y reanudación
- **Un solo bloqueo:** el marcador `.hermes-update-in-progress` de `hermes_cli/update_lock.py`
  (sin cambios). App: la app rechaza si hay dueño vivo (`main.ts:4800-4809`) y `posix.sh`
  lo toma con su PID; `janitor update` lo hereda por ascendencia (`update_lock.py:173-175`).
  Terminal/TUI/Telegram: `update_core.py:1509-1512`.
- **Mensaje de rechazo propio en español** en `update_core` (con `holder.pid` y la edad), en
  vez de `describe_holder` de upstream, que nombra `hermes update`.
- **Rechazo bajo `--gateway`:** no escribir `.update_exit_code` (hoy el `finally` escribe `1`,
  `update_core.py:1749-1751`), para no pisar el resultado de quien sí tiene el bloqueo.
- **Interrupción tras el pull — defecto encontrado:** las dependencias de Python y el catálogo
  solo se instalan si hubo pull (`update_core.py:1595-1640`). Si se mata el proceso entre el
  pull y `uv sync`, la siguiente corrida ve «Already up to date» y **se salta las
  dependencias** **[leído]**. Propuesta: tras un pull correcto, escribir
  `update-incomplete.json` con un `failed_step` nuevo `"pull"` (amplía el conjunto permitido de
  `_read_persisted_marker`, `update_core.py:1128`); borrarlo al final; una corrida que lo
  encuentre trata el árbol como recién bajado (dependencias, lazy features, catálogo).
- **Qué queda en cada interrupción:** marcador (caduca solo: PID muerto o 20 min); autostash
  aparcado (con `--keep-stash` siempre queda aparcado, `update_core.py:396-401`); `.update_*`
  del gateway (el vigilante los cierra a los 30 min con 124); sin archivo de resultado de
  `posix.sh` si fue `kill -9`.
- **Reanudar = volver a ejecutar la misma entrada.** No hay reanudación parcial.

### 3.5 Reinicio de gateways
Se conserva F1-12/F1-17: tras éxito se reinicia la flota del home con los ayudantes de upstream,
salvo que algún gateway del home corra desde otro checkout (`update_core.py:1407-1446`). Cambio
único: tras reiniciar, **contar los gateways que siguen con código viejo**
(`_fleet_runs_stale_code`, `update_core.py:1362-1372`) y, si queda alguno, terminar con salida 1
y «gateway con código viejo: `janitor gateway restart`». Upstream ya lo trata como fallo
(`hermes_cli/AGENTS.md`, «Verify»).

### 3.6 Resultado visible en cada entrada

| Entrada | Éxito | Fallo |
|---|---|---|
| App | La app se vuelve a abrir sola; si es incompatible, diálogo de 3.2. La ventana `ui.html` en español | Diálogo de error del arranque (ya traducido) con un `detail` en español |
| Terminal / TUI | Última línea en español con la versión nueva; aviso de app nueva si subió `contract` | `✗` en español, qué hacer y código distinto de 0 |
| Telegram | Retransmisión en español y «✅ Actualización de Janitor terminada.»; aviso de app nueva | «❌ … sigue corriendo la versión anterior» + últimas líneas en español |

## 4. Carrera de `/update` simultáneos

**Mecanismo confirmado leyendo** **[leído]**: el segundo `/update` reescribe
`.update_pending.json` y borra `.update_exit_code` antes de lanzar nada
(`slash_commands.py:1287-1301`); su proceso trunca `.update_output.txt` (`> …`, `:150`);
`update_core` lo rechaza por el bloqueo, pero el `finally` escribe `1` en `.update_exit_code`
(`update_core.py:1749-1751`) y el envoltorio bash escribe `2` después (`:153`). El vigilante
del primero lee ese código, anuncia «falló» con la actualización real aún en curso y borra los
marcadores. Lo mismo ocurre si el bloqueo lo tiene la app o el terminal.

| Opción | Qué hace | Problema |
|---|---|---|
| A. Touchpoint mínimo en `_handle_update_command` | Antes de escribir marcadores: si `read_live_update()` devuelve dueño, o ya existe `.update_pending.json` / `.update_pending.claimed.json`, responde «Ya hay una actualización en curso; te aviso cuando termine» y no toca nada | Edita un archivo de upstream (touchpoint `reapply`, `upstream_candidate: true`: el defecto es de upstream) |
| B. Rechazo desde el envoltorio del plugin (`gateway_update.py`) | Consulta el bloqueo antes de llamar al original | **Llega tarde**: cuando se llama a `_spawn_detached_update` los marcadores ya están reescritos. Solo evita truncar la salida |
| C. Hook `pre_gateway_dispatch` del plugin | Descarta el mensaje `/update` si hay bloqueo | Corre **antes de la autorización** (`hermes_cli/plugins.py:135-137`, `gateway/run_inbound.py:67-73`): o descarta en silencio, o responde a remitentes no autorizados |

**Recomendada: A**, más el cambio de `update_core` de 3.4 (no escribir el código de salida al
rechazar). A cierra la carrera dentro de un proceso de gateway porque entre la comprobación y
`_spawn_detached_update` no hay ningún `await` (`slash_commands.py:1263-1306`) **[leído]**. El
texto nuevo usa `agent.i18n.t_default` con clave `runtime_copy.gateway.update_already_running`,
como el touchpoint `runtime-copy`, para no tocar `locales/en.yaml`. Queda sin cubrir una carrera
entre **dos procesos de gateway** del mismo home a la vez **[inferido: raro, con multiplex hay un
solo proceso]**.

## 5. Textos en español pendientes de este recorrido

| Grupo | Dónde | Mecanismo |
|---|---|---|
| Salida de `update_core.py` (~90 `print`, p. ej. `:491`, `:528`, `:585`, `:615`, `:681`, `:760`, `:1514`, `:1600`, `:1645`, `:1667`, `:1735-1736`, `:1740`, `:1745`; avisos de reinicio `:1419-1446`) | Terminal, TUI y chat de Telegram | Código del fork: reescribir los literales en español directamente (no es upstream; la directiva 17 no aplica). Revisar pruebas que comparen literales en inglés |
| Rechazo por bloqueo (`hermes_cli/update_lock.py:136-143`) | Terminal y chat | Mensaje propio en `update_core` (3.4); `update_lock.py` no se toca |
| `⚠ Bootstrap update failed` (`janitor/cli.py:72`) | Terminal y chat | Literal del fork |
| `FINAL_MSG` de `posix.sh` (`:79`, `:102`, `:353-365` solo macOS, `:460`, `:470`, `:705`, `:718`, `:748`, `:791`, `:809`, `:814`, `:816`, `:822`), etapas `publish_stage` (`:349`, `:773`, `:795`, `:807`) y título `Hermes update` de `notify-send`/`zenity`/`kdialog` (`:136-150`) | `detail` del diálogo, `ui.html`, notificación | Ampliar el touchpoint `desktop-update-posix` (líneas `# JANITOR:`). El código de salida 2 (otro dueño del bloqueo) merece su propio mensaje: hoy cae en «Update failed (exit 2). Run hermes debug share» (`:816`) |
| `ui.html` (`:26`, `:108-111`, `:211`, `:230-231`, `:238-239`, `:243-244`, `:282-283`) | Ventana de progreso | Archivo de upstream → touchpoint nuevo `desktop-update-ui`. Además, la rama `error` ignora `state.message` (`:242-244`): mostrarlo |
| Mensaje de progreso «Updating Hermes — this window will close…» (`main.ts:4277`, `:4891`) y `INSTALLER_URL` (`updates-overlay.tsx:46`, `about-settings.tsx:27`) | Vista de actualizaciones y Acerca de | Capa de construcción (`brand/literals.mjs`, directiva 17) **[que el mensaje llegue a pantalla: inferido]** |
| Modal de `/update` del TUI clásico (`cli_commands_mixin.py:2702-2711`) y ayuda del TUI Ink (`core.ts:150`, `:159`) | TUI | Fuera de este recorrido: inventario general de F1-19 (`/help` del CLI/TUI) |
| Botones de Telegram (`telegram/adapter.py:4226-4229`) | — | Inalcanzables con `update_core` (sección 1). No se toca; si algún día el flujo Janitor pregunta, touchpoint en el adaptador |

## 6. `update_core.py`: qué se conserva y qué se podría reducir (insumo para F5-03)

Se conserva (razón de existir): no sincronizar con `NousResearch` (upstream ofrece añadir el
remoto `upstream` y empuja `main` del fork, `hermes_cli/update_cmd_git.py:238-300`); validación
de sintaxis de archivos del fork (`:78-93`); catálogo tras el pull; ramas `venv`/`.venv`
(`:424-436`, hasta F5-01/F5-02); bloqueo; reinicio de flota con la exclusión por checkout
ajeno; `--keep-stash`; aviso de contrato de 3.2.

Candidatos a reducir:
- La «costura de recarga» (`_reload_helper_modules_after_pull`, `:1054`; paso 6 del
  docstring) es justo el patrón que upstream retiró: «nothing runs pulled code in the pre-pull
  interpreter», ahora con un proceso hijo `--post-swap` (`hermes_cli/AGENTS.md`, sección del
  pipeline; `hermes_cli/update_cmd.py:1379-1460`). Rehacer la cola de `update_core` como un hijo
  que importa solo el árbol nuevo eliminaría la costura y los ~25 centinelas de `_try_import`
  (`:99-128`, `:213-285`).
- Fallbacks locales que duplican ayudantes de upstream (`_local_stash`, `_local_restore_stash`,
  `_local_write_gateway_exit_code`) y rutas de Termux/Android (`:694-738`): Janitor es Linux de
  escritorio.
- La pista `scripts/migrate-janitor-v0.20.1.sh` en el fallo de migración de config (`:1675`) es
  de la instalación antigua.
- Lo que falta frente a upstream y conviene decidir en F5-03 si se adopta: recibos
  (`hermes_cli/update_receipt.py`), verificación de flota con fallo duro (3.5) e instantánea
  previa por perfil.

## 7. Tareas

Alcances disjuntos; `janitor/overlay.yaml` lo escriben dos tareas, por eso F1-21e va después
de F1-21c.

| ID | Alcance | Verificación | Depende de | Sin publicar |
|---|---|---|---|---|
| F1-21a Contrato app↔motor | `janitor/desktop-compat.json` (nuevo), `apps/desktop-janitor/brand/patches.mjs`, `apps/desktop-janitor/scripts/build.mjs`, prueba nueva `apps/desktop-janitor/scripts/compat.test.mjs` | `node --test` de la capa + `build.mjs --check`; arranque sin pantalla con un `desktop-compat.json` de N mayor en un home temporal → diálogo, sin backend | — | Sí |
| F1-21b Textos y enlaces de la app | `apps/desktop-janitor/brand/literals.mjs` (mensaje de progreso, `INSTALLER_URL` → `release_url`) | `node --test` de la capa + `build.mjs --check` + vigilancia de idioma | — | Sí |
| F1-21c `posix.sh` y `ui.html` | `scripts/desktop-update/posix.sh`, `scripts/desktop-update/ui.html`, `janitor/overlay.yaml` (entradas `desktop-update-posix` y `desktop-update-ui`), `tests/janitor/` (prueba de posix) | `posix.sh --self-test-gate` en un árbol temporal con y sin `APPIMAGE`; `--self-test-ui` (sin navegador: solo el archivo de estado); overlay check | — | Sí |
| F1-21d Núcleo | `janitor/update_core.py`, `janitor/update_bootstrap.py`, `janitor/cli.py` (solo la línea 72), `tests/janitor/test_janitor_update_core.py` y demás pruebas de actualización de `tests/janitor/` | Pruebas de comportamiento: rechazo sin código de salida, marcador `"pull"` y reanudación, aviso de contrato, flota con código viejo → 1, textos en español | F1-21a (formato del archivo) | Sí |
| F1-21e Carrera de `/update` | `gateway/slash_commands.py` (touchpoint), `janitor/locales/es.yaml`, `janitor/overlay.yaml`, `tests/janitor/test_janitor_overlay_contract.py` | Prueba: dos `/update` seguidos → el segundo responde «ya hay una en curso» y los marcadores del primero quedan intactos; con el bloqueo tomado por otro proceso, igual | F1-21c (overlay.yaml) | Sí |
| F1-21f Release | `.github/workflows/janitor-desktop-release.yml`, `apps/desktop-janitor/electron-builder.janitor.json` | Nombre estable del AppImage; el job falla si la etiqueta no es `v` + `display_version(pyproject)` | — | **No**: el job solo se demuestra con una etiqueta real |
| F1-21g Aceptación | — | Sección 8 | a–f, F1-15 | **No** |

## 8. Aceptación (cierra F1-21 y la aceptación de F1-09, F1-12, F1-17, F1-20)

Requisitos: dos releases publicados, **R1** y **R2** (R2 con al menos un cambio en `apps/desktop`
y otro que suba `contract`); instalación limpia de R1 por F1-15; un bot de Telegram real; un
gateway instalado como servicio (`janitor gateway install`). Anotar en cada paso salida, PID y
archivos `.update_*` / `.hermes-update-result.json`.

1. **App.** Con R1 abierto y el gateway en marcha: la app anuncia la actualización y, en la
   tarjeta, que hará falta la app nueva. «Actualizar ahora» → la ventana se cierra; la ventana de
   progreso (si hay Chromium por defecto) en español; `janitor update` en
   `~/.janitor/logs/desktop-update-handoff.log`; el gateway cambia de PID y
   `gateway_state.json` trae el `code_sha` nuevo; el AppImage R1 se reabre solo y muestra el
   diálogo de app incompatible con el enlace a R2; sin backend iniciado.
2. Descargar R2 desde el enlace, reemplazar, abrir: arranca normal; Acerca de sin aviso.
3. **Terminal.** Volver el motor a R1 (`git reset` en un home de pruebas, no en el real),
   `janitor update` en un terminal: todo en español, salida 0, aviso de app nueva, gateway
   reiniciado. Repetir con la app abierta y anotar qué pasa con su backend (sección 9).
4. **TUI.** `janitor`, `/update` en el TUI clásico y en el Ink: comprobar con `ps` que corre
   `janitor update` y no `hermes_cli.main update`.
5. **Telegram.** Motor en R1, `/update` desde el bot: «Iniciando…», retransmisión en español,
   reinicio del gateway, aviso final «✅ Actualización de Janitor terminada.» tras el reinicio.
6. **Carrera.** Dos `/update` en menos de un segundo: el segundo recibe «ya hay una en curso»;
   el primero termina con su propio resultado.
7. **Interrupción.** Matar `janitor update` justo después del pull (`kill -9`) y repetir: la
   segunda corrida instala dependencias y termina en 0. Matar `posix.sh` a mitad: la app reabre
   y el marcador caduca; volver a actualizar funciona.

## 9. Riesgos, sin verificar y decisiones del dueño

Riesgos y sin verificar:
- **Actualizar desde terminal o Telegram con la app abierta:** `update_core` no detiene ni
  avisa del backend `serve` de la app, que sigue con el código viejo en memoria; `posix.sh`
  insiste en no actualizar con backends vivos (`:701`). Qué pasa de verdad: sin verificar.
  Si falla en la aceptación, se añade un rechazo en `update_core` (alcance de F1-21d).
- Que un gateway bajo systemd reinicie bien cuando el propio actualizador cuelga de su
  cgroup (`update_core.py:1724-1725` lo anticipa): sin verificar.
- Si el gateway de mensajería que lanza la app sobrevive a cerrarla para actualizar en
  Linux (upstream solo lo detiene a propósito en Windows, `gateway-stop-before-update.ts`):
  sin verificar. Si no sobrevive y la app no se relanza, Telegram queda caído hasta reabrir.
- `relaunch.py` cae al flujo de upstream si `sys.argv[0]` no es ejecutable y no hay
  `hermes` en el PATH (`relaunch.py:95-101`): no visto en una instalación real.
- Tras actualizar, un gateway de systemd corre código nuevo sin migración de layout ni
  sincronización del plugin hasta el siguiente arranque del lanzador (sección 2).
- Que el runtime de AppImage defina `APPIMAGE` y que relanzar el archivo funcione desde el
  proceso desacoplado: sin verificar.
- Windows: fuera de alcance (el envoltorio de `/update` no actúa ahí,
  `janitor/plugin/gateway_update.py:13-14`).

Decisiones que necesitan al dueño (producto):

| Tema | Valor provisional | Qué decidir |
|---|---|---|
| Canal de actualización del motor | `main` (cada merge llega a todos los usuarios al pulsar «Actualizar») | Si los usuarios deben recibir solo releases etiquetados. Cambiarlo implica que motor, app y `update_core` sigan etiquetas en vez de una rama |
| Reapertura tras actualizar | El AppImage viejo se reabre solo y, si hace falta, pide la app nueva (3.3) | Si se prefiere que la app quede cerrada con el aviso, como hoy |
| Enlace de descarga | Página `releases/latest` del fork (descarga guiada). **Sustituido el 2026-11-27** por la actualización automática: [`actualizacion-automatica.md`](actualizacion-automatica.md) | Si el botón debe descargar el archivo directamente |
