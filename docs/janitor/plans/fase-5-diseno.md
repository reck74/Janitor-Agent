# Fase 5 — Diseño: adopción de instalaciones antiguas y limpieza

> **Sin efecto en lo que toca a F5-01 (2026-11-22).** El dueño decidió que la app es un
> punto cero: las instalaciones antiguas no se adoptan, se desinstalan (decisión 2.9 del
> plan). Este documento se conserva por los hechos del layout antiguo (sección 1) y por el
> análisis de F5-02 y F5-03; las secciones 2 a 4 ya no se implementan.


Complementa `janitor-desktop-app.md` (secciones 3.2, 4.3–4.5; filas F1-22, F5-01,
F5-02, F5-03). Diseño producido el 2026-11-22 por un subagente, **solo lectura**: no
se ejecutó ninguna prueba, compilación ni instalador. Etiquetas: **[leído]** = se
comprobó leyendo código o con `ls`/`grep` de solo lectura (incluido el `~/.janitor`
real del dueño, sin abrir `.env` ni credenciales); **[inferido]** = sin verificar.
Rutas relativas a la raíz del repo salvo `~/…`.

## 1. Hechos

### 1.1 Qué deja en disco la instalación antigua

| Pieza | Quién la escribe | Evidencia |
|---|---|---|
| Código en `~/.janitor/janitor-core` (clon del fork, `git pull origin main` si ya existe) | `scripts/bootstrap.sh:10,99-106` | [leído] |
| Entorno `janitor-core/.venv` (`uv venv .venv`, `pip install -e .[all]`) | `bootstrap.sh:11,143-146` | [leído] |
| Enlace `~/.local/bin/janitor` → `janitor-core/.venv/bin/janitor` (`ln -sf`) | `bootstrap.sh:176-177` | [leído]; en el equipo real apunta ahí [leído] |
| Docker instalado y usuario añadido al grupo `docker` (con `sudo`) | `bootstrap.sh:27-73` | [leído] |
| `.env` reescrito (respaldo previo en `.backup/install-*`), con `HERMES_HOME=` dentro | `scripts/janitor-install.sh:170-208` | [leído] |
| `SOUL.md`, `honcho.json`, `config.yaml` copiados solo si faltan; skin si falta | `janitor-install.sh:219-253` | [leído] |
| **RC de shell:** añade `export HERMES_HOME="$HOME/.janitor"` y `PATH` a `~/.bashrc`/`~/.zshrc` si existen | `janitor-install.sh:262-278` | [leído] |
| **Unidad systemd `janitor-honcho.service`** (habilitada) que hace `docker compose … up` en `~/.janitor/docker`; independiente del motor | `scripts/setup-honcho.sh:143-174` | [leído]; existe y está `enabled` en el equipo real [leído] |
| Unidad `hermes-gateway.service` con `ExecStart=…/janitor-core/.venv/bin/python -m hermes_cli.main gateway run`, `VIRTUAL_ENV=…/janitor-core/.venv`, `HERMES_HOME=~/.janitor` | `hermes gateway install` de una versión anterior; no la crea ningún instalador Janitor | [leído] en el equipo real: `enabled` y `active`. Cómo obtuvo el nombre sin sufijo: sin verificar |

Más hechos del equipo real [leído, `ls`/`git status`]: `.layout_version` = 1 (v2
pendiente); `janitor-core` en `25ae039cc0` con dos archivos modificados localmente;
tres perfiles bajo `profiles/`, cada uno con su `state.db`; `state.db` raíz de ~1,37 GB
más otras bases SQLite en la raíz (`kanban.db`, `projects.db`, `response_store.db`,
`shared-state.db`, `verification_evidence.db`); `skills/` con el paquete de upstream
copiado (`.bundled_manifest` de 54 líneas, sin `.no-bundled-skills`), lo que responde a
la duda de F5-01; `config.yaml` raíz con una referencia a `janitor-core`; datos de
Electron en `~/.config/Hermes` y `~/.config/Janitor Agent`, no en `~/.config/Janitor`.

### 1.2 Cómo decide la app que hay motor
- Home: `~/.janitor` por el parche P1 (`apps/desktop-janitor/brand/patches.mjs:6-13`)
  salvo que `HERMES_HOME` venga en el entorno (`apps/desktop/electron/main.ts:866-869`). [leído]
- Motor: `~/.janitor/hermes-agent` y `venv` dentro (`main.ts:944,946`). La app lo usa si
  `isActiveRuntimeUsable()` — raíz de código válida, `venv/bin/python` existe e importa
  `hermes_cli` (`main.ts:4954-4969`); el marcador `.hermes-bootstrap-complete` es
  opcional (`main.ts:5310-5325`). [leído]
- Si no es usable: el `hermes` del PATH y el Python del sistema están anulados por P3
  (`patches.mjs:31-46`), así que corre el instalador por etapas
  (`bootstrap-runner.ts:1002-1024`). `janitor-core/.venv` **no** se detecta. [leído]
- Un fallo de etapa muestra su `reason` (`apps/desktop/src/components/desktop-install-overlay.tsx:135`)
  y la app ofrece reintentar (`main.ts:15882-15894`). [leído]
- Mientras exista un marcador de actualización vivo (`HERMES_HOME/.hermes-update-in-progress`)
  la app **aparca** el arranque del motor (`update-gate.ts:44-56`, `main.ts:2497-2502`),
  pero solo hasta 20 min y luego arranca igual (`main.ts:2476`, `update-gate.ts` comentario
  de `waitForUpdateClearance`). Python considera muerto un marcador de más de 20 min aunque
  su proceso viva (`hermes_cli/update_lock.py:23,124-128`). [leído]

### 1.3 La guarda F1-22 hoy
`janitor_refuse_legacy_home` se niega si existe `$HERMES_HOME/janitor-core`
(`scripts/install.sh:246-256`) en el modo monolítico (`:3947`), en cada `--stage` antes de
escribir (`:3906-3911`) y en `--ensure` (`:3993`). No hay forma de saltarla. [leído]

### 1.4 Qué hace hoy el lanzador nuevo si arranca sobre un home antiguo
Nada lo detiene [leído]. Fuerza `HERMES_HOME=~/.janitor` **derivado de `HOME`**
(`janitor/cli.py:33`, `janitor/home.py:34-57`: para aislar una prueba hay que cambiar
`HOME`, no `HERMES_HOME`); al importarse corre `ensure_home` (`cli.py:93-98`: respeta el
`config.yaml` del usuario, `seed.py:119-130`; `SOUL.md` solo si es el de upstream; skin si
falta; siempre sincroniza el plugin de escritorio, `seed.py:202-204`) y
`catalog.apply_quietly` (`cli.py:127-129`); en `main()`, `auto_migrate` (`cli.py:361-363`).
`ensure_command_link` reapunta `janitor` con la única condición de que el destino
contenga `janitor-core` (`seed.py:222-232`). [leído]

### 1.5 Qué cubren las migraciones v1/v2
- Orden v1→v2, un solo respaldo, sello `.layout_version` (`janitor/migrations/__init__.py:34-61`). [leído]
- **Solo el home raíz**: perfiles fuera. El respaldo copia `config.yaml`, `SOUL.md`,
  `honcho.json`, skin, `skills/` y **solo el `state.db` raíz**, por la API de backup sin
  comprobación de integridad (`v1.py:278-305`). [leído]
- v1 añade `str(SKILLS_ROOT)` **del árbol que se ejecuta** a `external_dirs` en homes sin
  `janitor.skills` (`v1.py:164-201`; `home.py:31`). v2 retira nombres de skills (`v2.py:13-29`). [leído]
- **Hueco para la adopción:** `catalog._owned` solo reemplaza entradas de una instalación
  movida si ya no existen en disco (`janitor/catalog.py:274-284`). Con `janitor-core`
  conservado, sus entradas absolutas sobreviven junto a las del árbol nuevo: dos copias
  de cada skill Janitor visibles. Cómo resuelve Hermes el duplicado: [inferido], no verificado.

### 1.6 Bloqueo y gateway
- El marcador compartido vive en el home (`update_lock.py:39-47`), así que lo ven los dos
  motores y la app. `janitor/update_core.py:1281-1299` ya lo toma. [leído]
- Con `HERMES_HOME=~/.janitor` y sin root, `get_service_name()` daría
  `hermes-gateway-<hash>`, no `hermes-gateway`: el nombre sin sufijo solo corresponde a
  `~/.hermes` o a una unidad de sistema fijada siendo root (`hermes_cli/gateway.py:2148-2178,2196-2200`).
  `janitor gateway install` desde el motor nuevo crearía **una segunda unidad** y dejaría
  la antigua; `_find_legacy_hermes_units` solo busca `hermes.service` (`gateway.py:2443-2452`).
  Lectura, no ejecución → [inferido]. Afecta también a F1-24.
- La unidad generada fija `ExecStart` al Python del motor que la instala y `HERMES_HOME`
  (`hermes_cli/gateway_service_unit.py:155-230`). [leído]

## 2. Diseño de F5-01

### 2.1 Opción elegida
**Coexistencia con relevo:** el motor nuevo se instala en `~/.janitor/hermes-agent/venv`
**sin mover `janitor-core`**, y el home (configuración, credenciales, memoria, sesiones,
perfiles) **no se mueve ni se copia**: solo cambian el motor y el enlace. Coincido con
Codex en esto (mover rompe shebangs y el `ExecStart` de la unidad; `.venv` ≠ `venv`).

Me aparto de Codex en cinco puntos, por el código:

1. **Mismo commit en los dos motores.** La adopción exige que el motor nuevo quede en el
   mismo commit que `janitor-core` (este se pone al día antes con `janitor update`). Así la
   adopción es una **mudanza, no una actualización**: los dos motores entienden el mismo
   esquema de `state.db` y la vuelta atrás no choca con un esquema nuevo [inferido: no hay
   migración de esquema sin cambio de código].
2. **Entrada por terminal, no por la app.** Preguntar antes de lanzar el motor exige un
   parche estructural de interfaz: las etapas no son interactivas (`install.sh:379-384`),
   los parches de `apps/desktop-janitor/` reemplazan texto anclado (`patches.mjs`) y el
   plugin de escritorio solo existe con un motor en marcha. La app ya muestra el motivo de
   la guarda y ofrece reintentar (§1.2). Para ≤ 10 usuarios técnicos que ya usan `janitor`:
   `janitor update` + `janitor adopt`, y «Reintentar» en la app. Un botón «Adoptar» es
   decisión del dueño (§9).
3. **El marcador de actualización no basta como cerrojo** (§1.2: caduca a los 20 min y la
   app arranca igual). Se añade una **guarda en el lanzador nuevo** que se niega a arrancar
   sobre un home con adopción a medias.
4. **Hace falta una migración v3** que reapunte `external_dirs` de `janitor-core` al árbol
   nuevo en la raíz **y en los perfiles** (§1.5). Codex no lo cubre.
5. **Restaurar nunca destruye:** antes de cualquier restauración se guarda el estado
   actual, de modo que «perder la actividad nueva» se convierte en «la actividad nueva queda
   aparte, recuperable a mano».

### 2.2 Dónde vive
| Pieza | Archivo |
|---|---|
| Orquestador y CLI | `janitor/adoption/__init__.py` (`main`, `run`), interceptado temprano en `janitor/cli.py` como `update` (antes de `ensure_home`, para no escribir nada al entrar) |
| Diario | `janitor/adoption/journal.py` |
| Inventario sin escritura | `janitor/adoption/preflight.py` |
| Respaldo y restauración | `janitor/adoption/backup.py` (reutiliza `hermes_cli/backup.py`: `_safe_copy_db` `:332`, `verify_sqlite_integrity` `:419`, `_safe_restore_db` `:511`, `_foreign_db_holder_pids` `:469`) |
| Relevo del enlace y vuelta atrás | `janitor/adoption/activate.py` |
| Paso de servicio (aparte) | `janitor/adoption/gateway.py` |
| Guarda del lanzador | `janitor/cli.py` (función en `janitor/adoption/journal.py`) |
| Guarda del instalador | `scripts/install.sh` (touchpoint `install-sh` ya declarado) |
| Reapuntado de skills | `janitor/migrations/v3.py`, `LAYOUT_VERSION = 3` en `janitor/home.py`, `scripts/migrate-janitor-v3.sh --dry-run` |

### 2.3 Secuencia (`janitor adopt`, ejecutado por el motor antiguo ya actualizado)
Cada fase se escribe en el diario **antes** de empezar y se marca hecha al terminar.

0. **Inventario** (`preflight.py`, sin escribir): `janitor-core/.venv`; destino **literal**
   de `~/.local/bin/janitor` (`os.readlink`); HEAD, rama, `origin` y cambios locales de
   `janitor-core`; unidades de `user_systemd_unit_dir()` que nombren `janitor-core` en
   `ExecStart`/`Environment=` (activas o no); líneas del RC con `HERMES_HOME`; procesos del
   home (gateways: `find_gateway_pids(all_profiles=True)` + `_hermes_home_for_pid`; resto por
   ruta del ejecutable, nunca por subcadenas del argv); tamaño de cada SQLite y espacio
   libre (2× bases + 3 GB, [inferido]). Muestra el plan y pide «sí».
1. **Preparar**: crea el diario, toma `UpdateLock` y lo **renueva** entre etapas (reescribe
   pid y hora: `python-deps` puede pasar de 20 min). Ejecuta `janitor-core/scripts/install.sh --stage
   <s> --json --non-interactive --hermes-home ~/.janitor --dir ~/.janitor/hermes-agent
   --branch <rama de janitor-core> --adopt-journal <ruta>` para `repository`, `venv`,
   `python-deps`, `node-deps`. **Omite** `prerequisites` (puede usar `sudo`), `path` (escribe
   en el RC si `~/.local/bin` no está en el PATH, `install.sh:2289-2352`), `config` (escribe
   `.no-bundled-skills` sobre el home existente, `:2414-2421`, y toca `.env`, `:2367-2383`),
   `setup` y `gateway`. Comprueba que HEAD nuevo = HEAD de `janitor-core`; si difiere,
   se detiene y pide `janitor update`.
2. **Probar aislado**: `hermes-agent/venv/bin/python -m janitor.cli serve --host 127.0.0.1
   --port 0` con `HOME`, `XDG_CONFIG_HOME` y directorio de comandos temporales, sin `.env`,
   hasta que responda como lo comprueba la app (señal exacta de disponibilidad: [inferido]); luego se detiene.
3. **Escritores parados**: pide al usuario detener el gateway (muestra el comando exacto de
   `systemctl --user stop …`; la adopción no lo ejecuta), cerrar TUI y app, y vuelve a
   comprobar procesos y `_foreign_db_holder_pids` de cada base. Si una unidad sigue
   **habilitada**, avisa de que revivirá al iniciar sesión y exige confirmarlo.
4. **Respaldar** (`backup.py`) en `.backup/adoption-<id>/home/`, permisos 0700. Se respalda
   lo que el primer arranque del motor nuevo puede cambiar, en la raíz y en cada perfil:
   `config.yaml`, `SOUL.md`, `profile.yaml`, `honcho.json`, `auth.json`, `skins/`, `skills/`
   (con `.bundled_manifest`), `memories/`, `cron/`, `plugins/`, `desktop-plugins/`,
   `.layout_version`, y **cada `*.db`** por la API de backup con
   `verify_sqlite_integrity` (que hace `PRAGMA integrity_check` hasta 2 GiB,
   `hermes_cli/backup.py:416`). **No** se respalda: `.env` (nadie lo toca), `sessions/`,
   `logs/`, cachés, `browser-profiles/`, `docker/`, `janitor-core/`. Cada archivo queda en
   el diario con tamaño y sha256; un fallo de integridad detiene la adopción.
5. **Migrar** con el motor nuevo: `hermes-agent/venv/bin/python -m janitor.migrations
   --home ~/.janitor` (v1, v2, v3) y `janitor.catalog.apply_quietly` sobre
   `janitor_homes(~/.janitor)` (`catalog.py:487-494`).
6. **Verificar en real**: el mismo `serve` sobre el home real. La guarda del lanzador lo
   admite porque su padre es el proceso adoptante registrado en el diario. Se detiene al responder.
7. **Activar** (`activate.py`): si `readlink(~/.local/bin/janitor)` sigue siendo el literal
   registrado, symlink temporal en el mismo directorio + `os.replace` (atómico); si no,
   se detiene («enlace inesperado»). Escribe `.hermes-bootstrap-complete` con la etapa
   `complete` (`install.sh:3877-3888`, `:3160-3200`) para que la app lo trate como suyo.
   Diario → `completed`; suelta el bloqueo.
8. **Informe**: rutas de los dos motores, unidades y líneas del RC que siguen apuntando al
   motor antiguo (sin tocarlas), cómo volver atrás, cómo retirar el motor viejo.

**Paso aparte, con confirmación propia: `janitor adopt --gateway`.** Detiene y deshabilita
la unidad antigua y ejecuta `janitor gateway install` desde el motor nuevo. No forma
parte de la migración (directiva 10). Antes de construirlo hay que resolver el nombre de
la unidad (§1.6): sin eso quedarían dos gateways peleando por el token de Telegram.

**Nada de la adopción toca** `.env`, líneas del RC, unidades systemd (salvo el paso
aparte confirmado), contenedores, volúmenes ni `janitor-core`.

### 2.4 Diario (`.backup/adoption-<id>/journal.json`, escritura atómica)
Campos: `schema`, `id`, `phase`, `phases_done`, `adopter_pid`, `home` (absoluta);
`old` y `new` (`root`, `venv`, `head`; `old` también `branch` y `dirty`); `link`
(`path`, `literal_before` = `readlink` literal, `target_after`); `units` (nombre,
habilitada, activa, apunta al viejo); `backup` (`dir`, archivos con `rel`, `bytes`,
`sha256`, `integrity`); `layout_before`, `layout_after`, `rolled_back`. Fases: `checked`,
`preparing`, `prepared`, `probed`, `writers-stopped`, `backed-up`, `migrated`, `verified`,
`completed`, `rolled-back`.

### 2.5 Guardas
- **Instalador** (`janitor_refuse_legacy_home`): deja pasar si algún
  `.backup/adoption-*/journal.json` tiene `"phase": "completed"`, o si se pasó
  `--adopt-journal F` y `F` está entre `preparing` y `verified` (la etapa `complete` del
  paso 7 entra así). Es una opción de línea de
  órdenes, no una variable de entorno. En cualquier otro caso se niega, como hoy.
- **Lanzador** (`janitor/cli.py`, antes de `ensure_home`): si hay un diario cuya fase no es
  `completed` ni `rolled-back`, y el proceso no es hijo del `adopter_pid`, sale con código 1
  y un aviso. Cubre la app tras los 20 min del marcador y cualquier `janitor` del motor nuevo.
  `janitor adopt` queda exento.

### 2.6 Textos (tono de la directiva 18; borrador)
- Instalador: «Alto ahí: en `~/.janitor` vive una instalación de Janitor por terminal y no
  pienso plantarte un segundo motor encima a ciegas. En un terminal: `janitor update` y
  luego `janitor adopt`. Cuando acabe, vuelve aquí y dale a Reintentar.»
- Lanzador: «Hay una adopción a medias en `~/.janitor`. No arranco sobre un home en obras:
  `janitor adopt --resume` o `janitor adopt --rollback`.»
- Fin: «Hecho. `janitor` ya usa el motor nuevo. El viejo sigue en `janitor-core` y tu
  `hermes-gateway.service` todavía le apunta: `janitor adopt --gateway`, o ya verás al reiniciar.»

### 2.7 Lo que se pierde o cambia
Preferencias de ventana de la app: `userData` pasa a `~/.config/Janitor` (plan 4.3/4.4);
lo de `~/.config/Hermes` y `~/.config/Janitor Agent` no se migra (decisión técnica:
≤ 10 usuarios, ya decidido no compartir estado). Los cambios locales de `janitor-core`
no pasan al motor nuevo: se listan y siguen en `janitor-core`.

## 3. Estados intermedios y recuperación (al volver a ejecutar `janitor adopt`)

| Evidencia | Acción |
|---|---|
| `janitor-core`, sin diario, sin `hermes-agent/` | Instalación antigua normal: empezar en la fase 0 |
| `janitor-core` + `hermes-agent/` **sin diario**, o dos diarios sin terminar | Origen desconocido (a mano, una app anterior a F1-22): detenerse, listar, no tocar nada |
| Diario en `preparing`/`prepared`, adoptante muerto | Reanudar la etapa pendiente (`clone_repo` ya maneja checkout existente y clon interrumpido, `install.sh:1546-1560`) |
| Diario en `probed`/`writers-stopped` | Repetir comprobación de escritores y seguir |
| Respaldo incompleto o con integridad fallida | Respaldo nuevo en `home-2/`; nunca activar sin uno completo |
| `backed-up`/`migrated` sin `verified` | Repetir verificación; si falla, ofrecer vuelta atrás (aún sin sesiones nuevas) |
| Activación interrumpida: enlace = destino nuevo | Marcar `completed` |
| Activación interrumpida: enlace = literal viejo | Repetir el relevo |
| Enlace distinto de ambos | Detenerse: el usuario lo cambió; no se toca |
| `completed` con motor viejo presente | Normal; las guardas dejan pasar; el informe recuerda unidades y RC |
| `completed` pero el enlace volvió a `janitor-core` (p. ej. `bootstrap.sh` reejecutado) | Avisar: la app usa el motor nuevo y el terminal el viejo; no corregir solo |

## 4. Vuelta atrás (`janitor adopt --rollback`)
**Garantiza:** (a) antes de restaurar se guarda el estado actual con el mismo método en
`.backup/adoption-<id>/post-adoption/`; (b) los archivos y bases del respaldo vuelven
a su sitio (bases con `_safe_restore_db`, que se niega si otro proceso las tiene abiertas);
(c) `.layout_version` vuelve al valor registrado; (d) el enlace vuelve al literal anterior
**solo si** hoy apunta al destino nuevo; (e) `hermes-agent/` no se borra; queda inactivo
porque el diario pasa a `rolled-back` y la guarda del instalador vuelve a negarse.

**No garantiza:** fusionar la actividad nueva (sesiones, memorias, tareas de cron,
cambios de configuración: quedan en `post-adoption/`, recuperables a mano, y hay que
decirlo); lo hecho fuera del home (mensajes enviados, cron ya ejecutados, contenedores,
APIs externas); tokens OAuth renovados después del respaldo (el `auth.json` restaurado
puede obligar a volver a iniciar sesión, [inferido]); unidades o RC que el usuario cambió;
la compatibilidad si alguien actualizó un motor tras la adopción (rompe la premisa del mismo commit).

## 5. F5-02 — Retiro de `bootstrap.sh`, `janitor-install.sh`, `setup-honcho.sh`

Referencias reales (`git grep`, excluido `docs/janitor/plans/`) [leído]:

| Tipo | Dónde |
|---|---|
| **Ejecuta** `janitor-install.sh` | `.github/workflows/janitor-ci.yml:346` (job `installer-e2e`); `tests/janitor/test_janitor_migration_v1.py:253` |
| **Prueba** `bootstrap.sh` | `tests/janitor/test_janitor_bootstrap_node_version.py:35-142` |
| Instrucción de instalación pública | `README.md:28-33` (`curl … bootstrap.sh \| bash`) |
| Inventario del overlay | `janitor/overlay.yaml:36` (`setup-honcho.sh` en `fork_paths`), `:157-161` (touchpoint `installers` con `bootstrap.sh` + `install.ps1`; `bootstrap.sh` no existe en `upstream.base`) |
| Compatibilidad en código | `janitor/seed.py:11,125` (config copiado tal cual es reemplazable), `janitor/update_core.py:428` (`.venv`) |
| Mensajes y comentarios | `scripts/migrate-janitor-update-flow.sh:24`, `janitor/skills/services/janitor-firecrawl/scripts/deploy.sh:9,29`, `janitor-ci.yml:110,322-327`, `tests/janitor/legacy_home.py:3`, `test_janitor_cli.py:75`, `test_janitor_firecrawl_skill.py:7`, `test_janitor_overlay_contract.py:234` |
| Documentación histórica | `AGENTS.md:17,75`, `docs/janitor/RESTRUCTURE_v5.md`, `master_plan.md`, `project.md`, `next-upstream-sync.md:66` |

La skill `janitor-honcho` no llama a `setup-honcho.sh`; la unidad `janitor-honcho.service`
ya instalada no depende del script (§1.1).

**Condiciones previas:** F5-01 aceptada en el equipo real; el dueño confirma que ningún
usuario conserva solo la instalación antigua; F1-15 hecha (el README puede apuntar a la app).

**Orden:** (1) README y textos que mandan a los scripts; (2) `installer-e2e` reescrito
sobre `scripts/install.sh` y sus etapas; (3) pruebas: borrar
`test_janitor_bootstrap_node_version.py`, cambiar la ejecución de `test_janitor_migration_v1.py:253`
por la construcción de `legacy_home.py` (que **se conserva**: la usan las pruebas de adopción);
(4) borrar los tres scripts, quitar `setup-honcho.sh` de `fork_paths` y `bootstrap.sh` del
touchpoint `installers`; (5) comentarios de `seed.py`/`deploy.sh`. La lógica de `.venv` y de
config reemplazable **se queda** mientras quede un home sin adoptar.

## 6. F5-03 — `janitor/update_core.py` (1758 líneas)

| Líneas | Responsabilidad | ¿Duplica upstream? |
|---|---|---|
| 71-93 | Archivos críticos Janitor (incl. alias raíz) para la validación de sintaxis tras el pull | No: upstream solo valida los suyos |
| 96-306, 452-476 | Carga perezosa de ayudantes, `_call` con alternativas, `get_hermes_home` | Consecuencia de reimplementar |
| 424-436 | `venv`/`.venv` | Solo para `janitor-core` |
| 308-421, 482-1053 | Stash, `--check`, fetch/pull con `reset --hard`, dependencias Python/Node/TUI, migración de config | Sí (`update_cmd_stash.py`, `_git.py`, `_deps.py`, `_config.py`) |
| 1054-1102 | Recarga de módulos tras el pull (usado en 1630) | **Patrón que upstream retiró**: ahora reejecuta un hijo `--post-swap` (`hermes_cli/update_handoff.py:104-105`; `hermes_cli/AGENTS.md`) |
| 1103-1217 | Marcador `update-incomplete.json` | Parcial |
| 1218-1300 | Argumentos y bloqueo compartido | Sí (`hermes_cli/main.py:2426-2443`) |
| 1305-1324 | Reaplicar catálogo | No (Janitor); el lanzador ya lo hace al arrancar (`cli.py:127-129`) |
| 1327-1360 | Web y código de salida del gateway | Envoltorios finos |
| 1362-1446 | Reinicio de gateways salvo los de otro checkout | No: protege la coexistencia de dos motores |
| 1449-1758 | Orquestador | — |

Dato clave [leído]: el flujo de upstream ya es seguro para un fork por delante de upstream:
nunca hace pull de NousResearch si `origin` lleva commits propios
(`hermes_cli/update_cmd_git.py:284-306`); solo pregunta si añadir el remoto `upstream`, lo
que evita el marcador `.skip_upstream_prompt` del home (`:186,223-233`).

**Recomendación (no implementar aún):** después de F1-21 y de F5-01, reducir
`run_janitor_update` a: banner + sembrar `.skip_upstream_prompt` + delegar en el flujo de
upstream (bloqueo, recibos, hijo `--post-swap`, reinicio de la flota) + comprobar los
archivos críticos Janitor. **Se quedan** por la directiva 13: el punto único
`run_janitor_update`, la interceptación temprana, `/update` vía `gateway_update.py`, y el
aviso de gateway de otro checkout mientras exista coexistencia. **Se van:** 308-421,
482-1102, 1218-1300. Riesgo a verificar antes: el hijo `--post-swap` arranca
`hermes_cli.main` y no el lanzador, así que lo que hoy hace la Janitor tras el pull debe
poder ocurrir al siguiente arranque del lanzador o dentro del hijo [inferido].

## 7. Tareas (alcances disjuntos)

| ID | Alcance | Verificación | Depende | ¿Antes de F1-15? |
|---|---|---|---|---|
| F5-01a Diario e inventario | `janitor/adoption/journal.py`, `janitor/adoption/preflight.py`, `tests/janitor/test_janitor_adoption_preflight.py` | Pruebas 1 y 9 (§8) | — | Sí, homes temporales |
| F5-01b Respaldo y restauración | `janitor/adoption/backup.py`, `tests/janitor/test_janitor_adoption_backup.py` | Pruebas 2 y 7 | a (formato) | Sí |
| F5-01c Migración v3 | `janitor/migrations/v3.py`, `janitor/migrations/__init__.py`, `janitor/home.py`, `scripts/migrate-janitor-v3.sh`, `tests/janitor/test_janitor_migration_v3.py` | Prueba 3 | — | Sí |
| F5-01d Guarda e intercepción del lanzador | `janitor/cli.py`, `tests/janitor/test_janitor_adoption_gate.py` | Prueba 4 + `test_janitor_monkeypatch_signatures.py` sin cambios | a | Sí |
| F5-01e Guarda del instalador | `scripts/install.sh`, `janitor/overlay.yaml` (texto del touchpoint), `tests/janitor/test_janitor_install_sh.py`, `tests/janitor/install_sh_harness.py` | Prueba 5 + `python -m janitor.overlay check` | a | Sí |
| F5-01f Orquestador, relevo y vuelta atrás | `janitor/adoption/__init__.py`, `janitor/adoption/activate.py`, `tests/janitor/test_janitor_adoption_e2e.py` | Pruebas 6, 7, 8 con `install.sh` falso (`install_sh_harness.fake_install_dir`) | a-e | Sí, salvo la etapa real `python-deps` |
| F5-01g Paso del servicio | `janitor/adoption/gateway.py`, `tests/janitor/test_janitor_adoption_gateway.py` | Prueba 10 con `XDG_CONFIG_HOME` temporal | §1.6 resuelto, F1-24 | Parcial |
| F5-01h Documentación de usuario | `README.md`, `janitor/skills/core/janitor-onboarding/SKILL.md` | Lectura del revisor | f | Sí |
| F5-01-acept | — | Adopción real del home del dueño con el AppImage de F1-15, y vuelta atrás probada en una copia | todas + F1-15 | **No** |
| F5-02a CI | `.github/workflows/janitor-ci.yml` | Job verde | F5-01-acept | No |
| F5-02b Pruebas y scripts | §5 pasos 3-5 | `scripts/run_tests.sh tests/janitor/` + `overlay check` | F5-02a, dueño | No |
| F5-03 | `janitor/update_core.py`, sus pruebas | Suite Janitor + una actualización real | F1-21, F5-01-acept | No |

## 8. Pruebas mínimas de comportamiento
Todas con `legacy_home.build_legacy_home` + `janitor-core/.venv/bin/janitor` falso + enlace
en un `bin` temporal; `HOME` y `XDG_CONFIG_HOME` temporales; nada lee código fuente.
1. Inventario: el árbol (home, `bin`, RC, unidades) queda byte a byte igual.
2. Respaldo→restauración: `state.db` con escrituras en WAL hechas por `SessionDB` con la
   conexión abierta; tras restaurar, mismos mensajes e integridad correcta; perfil B incluido.
3. v3: raíz sin catálogo y perfil con catálogo, ambos con entradas en `<home>/janitor-core/janitor/skills`
   → apuntan al árbol en ejecución; entradas ajenas intactas; idempotente; `--dry-run` no
   escribe; ejecutada desde `janitor-core` no hace nada.
4. Lanzador: diario en `preparing` → sale con 1 y el home no cambia; `completed` → arranca.
5. `install.sh`: sin diario se niega; `completed` deja pasar; `--adopt-journal` en
   `preparing` deja pasar; en `rolled-back` se niega.
6. Relevo: solo con el literal registrado; destino inesperado → nada cambia y sale con
   error; symlink temporal abandonado → la reanudación termina.
7. A→B→A: adoptar (A→B), escribir una sesión con el motor nuevo, volver atrás (B→A): el
   enlace vuelve, la sesión nueva aparece en `post-adoption/`, el home queda como el respaldo.
8. Directiva 10: tras adoptar y volver atrás, `.env`, RC, unidades y `docker/` byte a byte iguales.
9. Reanudación: cortar tras cada fase (escribiendo el diario y saliendo) y comprobar la
   acción de la tabla del §3.
10. Servicio: con una unidad antigua en `XDG_CONFIG_HOME` temporal, `--gateway` no deja dos
    unidades habilitadas para el mismo home.

## 9. Riesgos, sin verificar y decisiones del dueño

**Riesgos y sin verificar.**
- Nombre de la unidad del gateway (§1.6): leído, no ejecutado. Si se confirma, F1-24 tiene
  el mismo problema en una instalación limpia con `~/.janitor`.
- Cómo deduplica Hermes una skill visible desde dos árboles (§1.5).
- Señal exacta de disponibilidad de `serve` para las pruebas aislada y real.
- `python-deps` puede pasar de 20 min: la renovación del marcador lo cubre, pero la app
  aparcada arranca igual a los 20 min (de ahí la guarda del lanzador).
- `PRAGMA integrity_check` sobre 1,4 GB: minutos de CPU; en este equipo `systemd-oomd` ya
  mató procesos, así que se prueba en serie.
- Mismo commit exige que `janitor update` del motor viejo funcione con cambios locales (autostash, [inferido]).
- Reparar desde la app un home adoptado corre `config`, que escribe `.no-bundled-skills`
  aunque el home tenga el paquete de upstream (`install.sh:2414-2421`).
- El `HERMES_HOME=` del `.env` antiguo lo ignora el lanzador (`cli.py:52`); upstream: sin verificar.
  Qué es `~/.janitor/installs/`: sin verificar.

**Decisiones que necesitan al dueño (producto).**
1. ¿Basta `janitor adopt` en terminal más el aviso y el botón Reintentar de la app, o la
   entrega exige un botón «Adoptar» dentro de la app (parche de interfaz nuevo)?
2. Paquete de skills de upstream ya copiado en homes adoptados: ¿se conserva y se sigue
   sincronizando, se congela con `.no-bundled-skills` o se ofrece retirarlo?
3. ¿La adopción se da por completa con el gateway aún en el motor viejo, o exige pasar
   antes por `janitor adopt --gateway`?
4. Retiro del motor viejo y del respaldo: ¿solo a petición del usuario o Janitor lo ofrece
   pasado un tiempo? (Nunca mientras una unidad lo referencie.)
5. F5-02: confirmar cuándo ningún usuario conserva solo la instalación antigua.
