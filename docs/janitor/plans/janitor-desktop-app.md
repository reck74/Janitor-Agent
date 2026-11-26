# Plan: Janitor como aplicativo de escritorio

> **Fuente de verdad del replanteo.** Todo agente (Claude, Codex u otro) lee este
> archivo antes de tocar el repo y actualiza el [tablero](#5-tablero-de-tareas) al
> terminar una tarea. Las reglas vigentes están en `AGENTS.md` (directivas 1-20).
> Decisiones acordadas con el dueño del proyecto el 2026-11-22; no se reabren sin él.

Índice: [0 Estado y cómo retomar](#0-estado-al-cierre-del-2026-11-23-y-cómo-retomar) · [1 Objetivo](#1-objetivo) · [2 Decisiones de producto](#2-decisiones-de-producto) ·
[3 Hechos verificados](#3-hechos-verificados-en-el-código) · [4 Diseño técnico](#4-diseño-técnico) ·
[5 Tablero](#5-tablero-de-tareas) · [6 Protocolo entre agentes](#6-protocolo-de-trabajo-entre-agentes) ·
[7 Riesgos](#7-riesgos-y-puntos-sin-verificar) · [8 Bitácora](#8-bitácora)

## 0. Estado al cierre del 2026-11-23 y cómo retomar

**Dónde está todo.** `janitor-app/fase-1` está **fusionada en `main`** desde el 2026-11-24
([#91](https://github.com/reck74/Janitor-Agent/pull/91), merge `50212e2832`). El trabajo
posterior (canal `stable`, base sin navegador, páginas de Hermes ocultas, línea gráfica,
nombre estable del AppImage) también está **fusionado en `main`** desde el 2026-11-24
([#92](https://github.com/reck74/Janitor-Agent/pull/92), merge `03533f09ff`). No hay trabajo
pendiente fuera de `main`.

**Primera versión publicada (2026-11-25): `v0.21.5-janitor.1`.** La etiqueta, `main` y la rama
`stable` apuntan al mismo commit (`7b3db40455`). El AppImage está en
<https://github.com/reck74/Janitor-Agent/releases/tag/v0.21.5-janitor.1>
(`Janitor-linux-x86_64.AppImage`). Instalado desde esa descarga en un home vacío el mismo día (parte sin pantalla de A4; ver bitácora).

**Segunda versión publicada (2026-11-25): `v0.21.5-janitor.2`.** Fusionado el PR #98 (merge `6a0846d413`); la etiqueta, `main` y
`stable` apuntan a ese commit. En <https://github.com/reck74/Janitor-Agent/releases/tag/v0.21.5-janitor.2> están el AppImage,
el instalador de Windows x64, los `.dmg` de macOS (arm64 y x64) y el paquete de Arch. Sigue **sin probar en un Windows ni un Mac real**.

**Qué está hecho.** Fases 1 a 4 y el retiro de lo antiguo (F5-02), en código y pruebas. La
instalación real de punta a punta funciona desde un home vacío con la app compilada en
local. El detalle por tarea está en el [tablero](#5-tablero-de-tareas); la evidencia, en la
[bitácora](#8-bitácora).

**Qué sigue, por prioridad** (reordenado el 2026-11-24 con el dueño). Lo pendiente es casi
todo aceptación en uso real. Los bloques C y D corren en paralelo al camino crítico.

*A. Camino crítico hacia la primera versión publicada (secuencial).*

| # | Paso | Cierra | Depende de |
|---|---|---|---|
| A1 | ~~Revisar y fusionar el PR #91~~ **Hecho el 2026-11-24** (`50212e2832`). `main` ya contiene la app; el aviso falso de actualización de F1-27 queda por ver en la instalación de A4 | F1-27 (falta aceptación) | — |
| A2 | ~~Decisiones que cambian lo que se publica~~ **Tomadas el 2026-11-24** ([2.10](#210-qué-lleva-la-primera-versión-publicada-decidido-el-2026-11-24)): canal por versiones etiquetadas, base sin navegador, páginas de Hermes ocultas. El color quedó resuelto con la línea gráfica (F1-18) | sección 9 | — |
| A2b | ~~Implementar esas tres decisiones~~ **Hechas el 2026-11-24** (F1-28, F1-29, F1-30), en código y pruebas | — | — |
| A3 | ~~Primera etiqueta `v…`~~ **Hecho (2026-11-25):** `v0.21.5-janitor.1` publicada; el workflow compiló el AppImage, creó `stable` y lo adjuntó a la versión (corrida 45631111616, al segundo intento; ver bitácora). Instalar desde el AppImage descargado ya está verificado (bitácora, 2026-11-25); no verificado: recibir una versión nueva por `stable`, que exige una segunda etiqueta | F1-11, F1-28 | — |
| A4 | Una sola sesión **con escritorio** y una clave, sobre el AppImage publicado: elegir proveedor y chatear, abrir el TUI con `janitor`, ver el aviso de app vieja (el diálogo nativo no se pudo ver sin pantalla), los fallos (sin red, corte a medias, reparación), la memoria con MiniMax en sus cuatro casos, y chatear con un especialista y con una skill recién activada | F1-15, F1-25, restos de F4-04 y F4-05 | A3 y una clave del dueño |
| A5 | Segunda etiqueta y actualización real de una versión publicada a la siguiente con un gateway en marcha, desde la app, el terminal y Telegram | F1-21g (y la aceptación de F1-09, F1-12, F1-17, F1-20) | A3 |

*B. Operación cotidiana (después de A4).*

- F1-23: Telegram con un bot real (QR, nombre, `/start`, avatar).
- F1-24: gateway como servicio (posible segunda unidad systemd), cerrar, Salir, reinicio, app y TUI a la vez sin gateways duplicados. Su alcance sigue «por definir»: se diseña en el bloque D.
- F3-04: un disparo real del mantenimiento programado.

*C. Aplicativos opcionales (en paralelo; necesita un equipo de prueba con Docker).*

- Despliegue real de cada aplicativo (F4-01, F4-03, F4-07): imágenes, puertos y variables salen de las skills antiguas y no se han probado; LightRAG y la API de WAHA son los más dudosos.
- Iniciar, detener y el estado «no responde» en la pantalla Servicios (F4-02, F4-06), con un servicio de prueba, nunca con los contenedores del dueño.

*D. Sin dependencias (se puede empezar ya).*

- Diseño de F1-24, para que no frene el bloque B.
- Restos de F1-19 (textos del motor en inglés fuera de la app) y de F5-02 (`scripts/install.ps1`, `.env.example`).
- Riesgos sin verificar de la [sección 7](#7-riesgos-y-puntos-sin-verificar): perfiles con `HERMES_HOME` forzado, modo SSH con Janitor, marca en `@nous-research/ui`.
- Ensayar `docs/janitor/desinstalar-instalacion-antigua.md` en una máquina real.
- F5-03 (reducir `update_core.py`): después de A5.

**Cómo verificar (lo que funcionó en esta rama).**
- Pruebas: `scripts/run_tests.sh tests/janitor/` (668), `node --test apps/desktop-janitor/scripts/*.test.mjs` (243),
  `node apps/desktop-janitor/scripts/build.mjs --check` (222 anclas), `python -m janitor.overlay check`,
  `python -m janitor.catalog check`.
- App sin pantalla: `node apps/desktop-janitor/scripts/build.mjs --linux --dir` y abrir
  `apps/desktop/release/linux-unpacked/Janitor` con Playwright (`_electron.launch`,
  `--ozone-platform=headless --no-sandbox --disable-gpu`) y un `HOME` temporal. Con
  `HERMES_DESKTOP_HERMES_ROOT=<repo>` usa el motor del checkout y **salta la instalación**;
  sin esa variable hace la instalación real (la app descarga `install.sh` por el commit de su
  compilación, que debe existir en `origin`).
- Un diálogo nativo no sale en una captura: se comprobó sustituyendo `dialog.showMessageBox`
  bajo `--inspect-brk`.

**Avisos del equipo de desarrollo.**
- `/tmp` es memoria (tmpfs): una instalación de prueba ocupa gigas y debe ir en disco
  (`/var/tmp`). Lo que se guarde en `/tmp` se pierde al reiniciar.
- Al correr `scripts/run_tests.sh`, de vez en cuando un proceso muere por SIGKILL externo
  (un archivo de pruebas sale «CRASHED» y a solas pasa). No es memoria. Causa sin
  identificar; pista sin comprobar: `scripts/run_tests_parallel.py::_kill_tree` hace
  `os.killpg(…, SIGKILL)` al terminar cada archivo.
- `gh` está autenticado también en el shell de los agentes desde el 2026-11-24 (cuenta
  `reck74`, permisos `repo` y `workflow`). Fusionar a `main`, etiquetar y tocar `stable`
  siguen siendo órdenes del dueño.
- En el equipo hay un `~/.janitor` real de la instalación antigua, con un gateway y
  contenedores `janitor-*` en marcha. Ninguna prueba lo toca.

## 1. Objetivo

Janitor deja de instalarse por terminal y pasa a ser una **app de escritorio
instalable**, configurable por interfaz gráfica, que **convive con el TUI**. Es el
consejero, administrador y auditor de todo lo tecnológico del usuario: organiza,
limpia, investiga y crea proyectos.

- **Público:** personas técnicas hispanohablantes que trabajan en tecnología. No es
  un producto para usuarios de hogar.
- **Base actual:** máximo 10 usuarios. Hay libertad para cambios de fondo; la
  migración no necesita cubrir cada versión antigua.
- **Principio:** heredar de Hermes todo lo posible. Buena parte de la capa Janitor
  cubría carencias que Hermes ya resolvió.

## 2. Decisiones de producto

### 2.1 Memoria
- Base: memoria integrada de Hermes (`MEMORY.md` + `USER.md`) más `session_search`. Sin Docker.
- Opcional: proveedor `holographic` (SQLite local en el home del perfil). Crece con
  el uso; su extracción automática viene **apagada** por defecto (`auto_extract`), así
  que no «recuerda todo» sin configurarlo. Copia y recuperación: va dentro del home.
- Avanzado: Honcho, en la nube o local.
- Se crea una skill que instala Honcho de forma **conversacional y automática**
  (evolución de `janitor/skills/services/janitor-honcho`): revisa Docker, pide la
  clave, despliega, activa el proveedor y comprueba que responde.

### 2.2 Proveedor de IA y configuración inicial
- MiniMax es el proveedor **recomendado y preconfigurado**, no obligatorio. Se elige
  en el primer arranque gráfico.
- La semilla de `config.yaml` es mínima: solo lo que Janitor cambia. Sin valores
  personales (zona horaria, MCP de un proveedor concreto).
- El nivel gratuito de Nous y los flujos de cuenta de Nous quedan ocultos.

### 2.3 Agentes y skills
- Un agente es un perfil de Hermes. Se retiran `janitor/agents.py` y `janitor/opencode/`.
- Un agente principal, **Janitor**, es la cara del producto y delega en subagentes.
  Especialistas opcionales por plantilla: **Investigador** y **Creador de proyectos**.
- Los perfiles nacen sin el paquete de skills de Hermes (marcador `.no-bundled-skills`)
  y reciben skills de un catálogo Janitor organizado por propósito.
- No se comparte memoria entre agentes: el principal es quien conoce al usuario.
- **Especialista y subagente son cosas distintas.** Un especialista es un perfil: una
  conversación independiente que el usuario abre, con su `SOUL.md`, sus skills y su
  memoria. Un subagente es temporal: lo crea `delegate_task` dentro de una
  conversación, comparte el home y las skills de quien lo lanza y no lee ni escribe
  memoria (`tools/delegate_tool.py`, `skip_memory=True`). El principal **no** delega en
  perfiles especialistas; no hay mecanismo de upstream para ello y no se crea uno
  paralelo (directiva 19).

| Skill actual de Janitor | Destino |
|---|---|
| `janitor-config-audit`, `janitor-core`, `janitor-desktop-launcher`, `janitor-code-review-agent`, `janitor-browser` | Se retiran |
| `janitor-skill-integration` | Sale del producto (herramienta de desarrollo) |
| `janitor-onboarding` | Se reescribe corta |
| `janitor-repo-research-agent` | Pasa a la plantilla Investigador |
| `janitor-opendesign` y las 6 de servicios | Aplicativos opcionales (2.4) |

Skills nuevas a crear (no existen hoy): limpieza del equipo, organización de
archivos, salud del sistema, mantenimiento programado, creación de proyectos.
Siempre muestran lo que van a hacer antes de hacerlo y envían a la papelera en lugar
de borrar. El plugin `disk-cleanup` de Hermes solo limpia temporales del agente.

| Destino | Skills de Hermes en el catálogo |
|---|---|
| Agente principal | `pdf`, `docx`, `xlsx`, `powerpoint`, `document-to-action-items`, `weekly-review-planning`, `grounded-citations`, `blocked-page-recovery` |
| Investigador | `arxiv`, `grounded-citations`, `llm-wiki`, `competitor-news-monitor`, `youtube-content` |
| Creador de proyectos | `github`, `spike`, `systematic-debugging`, `test-driven-development`, delegación a `claude-code` / `codex` / `opencode` |
| Opcionales | `google-workspace`, `email-inbox-triage`, `notion`, `obsidian`, `computer-use`, Apple (solo macOS) |

### 2.4 Aplicativos opcionales
La app base no requiere Docker. Todos los opcionales siguen un único patrón: skill
guiada conversacional + pantalla de servicios; se conserva `service.yaml` y
`janitor services`.

| Aplicativo | Para qué |
|---|---|
| Honcho | Memoria avanzada. Único con guía en la primera versión |
| n8n | Automatizaciones |
| LightRAG | Base de conocimiento |
| NocoDB | Desarrollo con base de datos |
| WAHA | Auditar el WhatsApp personal del usuario: lee conversaciones y avisa de lo importante u olvidado. Solo lectura; no envía mensajes salvo orden directa. La skill avisa que las conversaciones viajan al proveedor de IA |
| Firecrawl | Extracción y búsqueda web con Firecrawl alojado en el propio equipo (Hermes ya busca sin clave). El servicio es local; las páginas se siguen pidiendo a Internet |
| Open Design | Generación de diseños |

### 2.5 Identidad, tono e idioma
- La personalidad **se mantiene**: sarcástica, ruda, directa, sin filtro. Insulta y
  corrige al usuario cuando hace falta. Es la característica principal del producto
  (directiva 18).
- Único cambio de identidad: el alcance pasa de **código a tecnología** en general.
  Ediciones pequeñas en `SOUL.md` y en la bienvenida de Telegram.
- **Español obligatorio** en toda superficie visible.
- El TUI se conserva completo (skin `sentry-janitor`, banner, caras, frases de
  «pensando», saludo, despedida, `tips_es.py`). El comando `janitor` sigue abriéndolo.
- La app toma del skin solo los colores. Las frases del personaje viven solo en el terminal.
- **Línea gráfica de la app (decidido el 2026-11-24, F1-18):** fondo morado profundo
  `#150f23`, verde lima `#c2ef4e` como color principal (botones, interruptores, pestaña
  activa), morado `#6a5fc1` como acento y el banner J4NITOR-AGENT en la bienvenida. Los
  colores salen del skin `sentry-janitor.yaml`, la misma fuente que el terminal. Es el
  trabajo gráfico previo del dueño, que se había perdido en la app el 2026-10-21
  (`afdaa0d7a1`) al pasar el escritorio a capa de construcción. La carpeta original
  `.plans/janitor_theme_wireframe/` nunca se commiteó y no se encontró; referencia viva
  de la misma línea: `~/Projects/openwebui-fork/branding/client-janitor/` (fuera del repo).

### 2.6 Mensajería
- Telegram es la única plataforma de la primera versión, configurada desde la app (QR).
- `janitor/plugin/telegram.py` (`/start` + avatar) se conserva.
- El QR depende de un servicio de Nous (`setup.hermes-agent.nousresearch.com`,
  `hermes_cli/web_server_messaging.py:376`; se puede cambiar con
  `TELEGRAM_ONBOARDING_URL`). No se ha probado desde el fork. La app también permite
  pegar un token de BotFather: esa ruta queda siempre visible (decidido; F1-23).
- WhatsApp como canal para hablar con el agente queda para después.

### 2.7 Plataforma y estructura
- **Linux primero** (AppImage). Windows y macOS después; exigen firma de código.
- Fork delgado en cuatro capas:

| Capa | Contenido | Mantenimiento |
|---|---|---|
| Motor | Hermes, sin renombrar | Sincronización con upstream |
| Capa Janitor | Lanzador, siembra, plugin, skills, plantillas, skin, `SOUL.md` | Carpetas propias del fork |
| Plugin de escritorio | Pantalla de servicios, catálogo de skills por agente | Nuevo, sobre el Desktop Plugin SDK |
| Capa de construcción | Marca, idioma, origen de instalación, home | Se aplica al compilar y se revierte |

### 2.8 Marca «Hermes» → «Janitor»
- Se reemplaza **al compilar**, nunca en el código fuente (directivas 1 y 17).
- Una prueba automática falla si queda «Hermes» en el texto visible en español fuera
  de una lista de excepciones declarada.
- Se acepta que queden rutas, variables `HERMES_*`, registros y nombres de servicios
  de terceros («Hermes Cloud», «Nous Portal»).

### 2.9 Punto cero: sin adopción de instalaciones antiguas
Decisión del dueño (2026-11-22). La app es el **nuevo punto de partida**:
- No se adopta, migra ni actualiza ninguna instalación anterior por terminal. Quien
  tenga un Janitor antiguo lo desinstala entero y empieza de cero con la app; el dueño
  avisa directamente a los usuarios (≤10). Guía:
  [`../desinstalar-instalacion-antigua.md`](../desinstalar-instalacion-antigua.md).
- La guarda de F1-22 se conserva solo como protección: si encuentra `janitor-core`, se
  niega y manda a desinstalar.
- **F5-01 queda cancelada.** El código que solo existía para instalaciones antiguas se
  retira (F5-02).
- A partir de aquí lo que importa es que **esta** app se actualice de forma práctica y
  sencilla, sin que el usuario tenga que lidiar con Git (F1-21).
- **Git oculto (decisión del dueño, 2026-11-22):** el motor sigue siendo un checkout que
  se actualiza con Git por debajo; el usuario solo pulsa un botón o escribe `/update` y
  nunca ve Git ni resuelve nada a mano. No se rediseña la entrega como paquete.

### 2.10 Qué lleva la primera versión publicada (decidido el 2026-11-24)

Tres decisiones del dueño, tomadas antes de la primera etiqueta. Son reglas vigentes
(directivas 8, 13 y 19); el código todavía no las cumple y cada una tiene su tarea.

- **Canal del motor: solo versiones etiquetadas.** Un usuario recibe una versión nueva
  del motor únicamente cuando existe una etiqueta `v…` publicada en el fork; un merge a
  `main` **no** llega a nadie por sí solo. La comprobación de actualizaciones y
  `janitor update` (app, terminal y `/update` de Telegram: un solo flujo, directiva 13)
  comparan contra la última etiqueta, no contra `origin/main`. La etiqueta es la misma
  que publica el AppImage, de modo que app y motor salen juntos y con la misma versión.
  Consecuencias para quien trabaja en el repo: `main` puede recibir merges y
  sincronizaciones con upstream sin que eso sea una entrega; **etiquetar es entregar**
  y lo decide el dueño; ningún agente crea ni mueve una etiqueta `v…` sin su orden.
  Motivo: con `main` como canal, un merge a medio probar llegaba a todos los usuarios.
  **Cómo se implementa (elegido con el dueño el 2026-11-24):** una rama `stable` que el
  workflow de release avanza, sin forzar, al commit de cada etiqueta `v…` que ya esté en
  `main`. Todo lo que instala o actualiza sigue `stable`; su nombre vive en
  `janitor/release_channel.py`. Se descartó hacer que cada pieza buscara la última
  etiqueta: el actualizador de upstream está construido alrededor de ramas y habría que
  reescribirlo en cuatro sitios. Nadie empuja a `stable` a mano. Tarea: F1-28.
- **El navegador no va en la instalación base.** La instalación omite Chromium de
  Playwright (~700 MB) y `browser-use` (122 MB), que eran 144 s de unos 195. Se
  descargan la primera vez que el agente necesita navegar, con un aviso en español de
  que está descargando. Coherente con la directiva 8: la base lleva lo mínimo.
  Tarea: F1-29.
- **Las páginas incrustadas de Hermes se ocultan.** El catálogo de plugins y el Skills
  Hub (`plugin-catalog.ts`, `embedded-hub-picker.tsx`) son páginas externas que no se
  pueden renombrar al compilar: muestran «Hermes» (directiva 17) y el Skills Hub deja
  instalar skills fuera del catálogo Janitor (directiva 19). La app Janitor no las
  ofrece; las skills se eligen solo en la pantalla Skills. Tarea: F1-30.

## 3. Hechos verificados en el código

Verificado el 2026-11-22 por lectura de código (tres subagentes de investigación).
Nada de esta sección se probó en una máquina limpia. Rutas relativas a la raíz.

### 3.1 Instalación desde la app
- `apps/desktop/`, `apps/bootstrap-installer/` y `scripts/install.sh` son hoy
  idénticos a upstream. `install.sh` no es touchpoint (solo `bootstrap.sh` e `install.ps1`).
- Home por defecto de la app en Linux: `~/.hermes`, escrito a mano en
  `apps/desktop/electron/main.ts:902`. No se deriva del nombre del producto ni se
  puede fijar con configuración de electron-builder.
- La app instala el motor en `HERMES_HOME/hermes-agent` con su entorno en
  `HERMES_HOME/hermes-agent/venv`.
- Orden para conseguir el instalador (`bootstrap-runner.ts:330-410`): copia local
  junto a la app → caché → descarga de
  `raw.githubusercontent.com/NousResearch/hermes-agent/<ref>/scripts/install.sh`
  (`:245`) → copia del motor ya instalado.
- `scripts/install.sh:46-47` clona siempre `NousResearch/hermes-agent`; no hay
  variable ni opción para cambiar el repositorio. Crea los comandos `hermes` y
  `hermes-agent` en `~/.local/bin` (`:2155-2198`), **no** `janitor`. Su etapa
  `config` siembra `.env`, un `config.yaml` de ejemplo y un `SOUL.md` de Hermes, y
  copia las skills incluidas salvo que exista `.no-bundled-skills`.
- **Consecuencia (inferida de la lectura, nunca reproducida):** la compilación
  Janitor anterior a la fase 1, en una máquina limpia, instalaría Hermes puro en
  `~/.hermes` con el comando `hermes`; también podría fallar antes, al pedir a
  upstream una referencia que solo existe en el fork.
- El repositorio `reck74/Janitor-Agent` es público: se puede clonar sin credenciales.

### 3.2 Arranque del motor
- La app ejecuta `<venv>/bin/python -m hermes_cli.main serve --host 127.0.0.1 --port 0`
  (`main.ts:5265-5281`, `backend-command.ts:18-22`). **No pasa por `janitor/cli.py`.**
- Por eso hoy no ocurre nada de lo que hace el lanzador: forzar `HERMES_HOME`,
  exportar `JANITOR_SKILLS_ROOT`, migrar el home, copiar y activar el skin,
  reemplazar tips y `cmd_update`.
- `serve` nunca sincroniza las skills incluidas; lo hace la etapa de instalación.
- Una instalación Janitor previa (`~/.janitor/janitor-core` con `.venv`) **no** la
  encuentra la app: busca `~/.janitor/hermes-agent/venv`. Instalaría una segunda copia.
- Riesgo: si hay un `hermes` de upstream en el PATH, la app puede usarlo como motor.

### 3.3 Siembra y configuración
- En un home vacío, upstream escribe un `SOUL.md` por defecto («Hermes Agent») en la
  primera carga de configuración. No escribe `config.yaml`: fusiona en memoria.
- Un `config.yaml` con pocas claves es seguro: se fusiona sobre `DEFAULT_CONFIG`.
- La semilla actual fija `_config_version: 23`; en la siguiente actualización
  correrían todas las migraciones 24→46 sobre ella. La versión debe escribirse al
  sembrar, tomada de `DEFAULT_CONFIG`.
- Un plugin de entry point no se activa solo: requiere `plugins.enabled: [janitor]`
  escrito en `config.yaml`. No hay forma upstream de distribuir un plugin activo por defecto.
- `.no-bundled-skills` funciona también en el home por defecto; queda solo la skill
  esencial `hermes-agent`.
- El respaldo relativo `janitor-core/janitor/skills` de `skills.external_dirs` solo
  sirve al instalador viejo. Con la app, las skills Janitor desaparecerían en silencio.
- El lanzador sale con error si `memory.provider: honcho` no tiene clave ni URL. La
  semilla nueva no debe fijar Honcho como proveedor.
- Un `SOUL.md` no vacío reemplaza por completo la identidad por defecto de Hermes.

### 3.4 Idioma y marca
- Idioma por defecto de la app: `'en'` en `apps/desktop/src/i18n/languages.ts:7`.
  Orden real: `display.language` del motor → idioma del sistema → por defecto.
- `apps/desktop/src/i18n/es.ts` tiene 283 apariciones de «Hermes»: 256 son nombre
  de producto, 13 son claves internas (no se tocan), 3 son comandos, el resto
  necesita excepción («Hermes Cloud» ×15, URL de instalación, marcadores de ejemplo,
  `.hermes/plans/`).
- La prueba de completitud del catálogo no detecta claves sin traducir. Hay al menos
  6 textos reales sin traducir en `es.ts`.
- Sin catálogo en español (caen a inglés): plugins `kanban`, `hermes-bots`, `radio`.
- Fuera de los catálogos: todo el proceso principal de Electron está en inglés y sin
  i18n (menús, bandeja, diálogos, mensajes de arranque, `APP_NAME = 'Hermes'` en
  `main.ts:1040`); en la interfaz hay ~93 literales con «Hermes» en 47 archivos, la
  mayoría mensajes de error.
- La notificación «Hermes terminó» sale solo del catálogo (`es.ts:572`).
- El nivel gratuito ya viene apagado salvo bandera explícita. Siguen visibles: Nous
  como primer proveedor del onboarding, la tarjeta «Hermes Cloud» y el tipo de conexión Cloud.
  La compilación Janitor va más lejos a propósito (decisión 2.2): ignora esa bandera,
  de modo que el nivel gratuito no se puede encender (`brand/first-run.mjs`).
- Lo que una transformación de archivos **no** alcanza: textos que envía el motor,
  mensajes de error en tiempo de ejecución, `@nous-research/ui`, menús nativos del sistema.

### 3.5 Actualización
- El actualizador de la app toma el repositorio del `origin` del motor instalado: si
  se instaló desde el fork, sigue al fork sin parches.
- Aplica la actualización con `venv/bin/hermes update` de upstream, **no** con
  `janitor/update_core.py`. Choca con la directiva 13 y queda como tarea F1-09.

## 4. Diseño técnico

### 4.1 Piezas

| Pieza | Dónde | Qué hace |
|---|---|---|
| Instalador del fork | `scripts/install.sh` (touchpoint nuevo, mínimo) | Clona `reck74/Janitor-Agent`; crea el comando `janitor` y no `hermes`; no copia el paquete de skills; deja el home listo para la siembra |
| Siembra | `janitor/seed.py` (nuevo) | `ensure_home(home)`: idempotente. Escribe la semilla mínima, `SOUL.md`, skin y `.no-bundled-skills` en un home nuevo; no pisa nada editado por el usuario; nunca toca `.env` |
| Lanzador | `janitor/cli.py` | Llama a la siembra antes de cargar el motor; ejecutable como `python -m janitor.cli`; sigue abriendo el TUI |
| Capa de construcción | `apps/desktop-janitor/` | Aplica parches y reglas de marca sobre `apps/desktop/`, compila y revierte |
| Reglas de marca | `apps/desktop-janitor/brand/` | Reglas para catálogos, mapa de literales exactos por archivo, lista de excepciones |

### 4.2 Parches de construcción (se aplican y se revierten)

| # | Archivo de `apps/desktop/` | Cambio |
|---|---|---|
| P1 | `electron/main.ts` | Home por defecto `~/.hermes` → `~/.janitor` |
| P2 | `electron/bootstrap-runner.ts` | URL del instalador → `reck74/Janitor-Agent` |
| P3 | `electron/main.ts` / `backend-command.ts` | Módulo del motor `hermes_cli.main` → `janitor.cli` |
| P4 | `src/i18n/languages.ts` | Idioma por defecto `'en'` → `'es'` |
| P5 | `electron/main.ts`, `index.html` | Nombre de la app y título de ventana → Janitor |
| P6 | `src/i18n/es.ts` | Reglas de marca del catálogo |
| P7 | Archivos de Electron con texto visible | Mapa de literales: marca y traducción al español |
| P8 | Componentes con marca visible fuera del catálogo | Mapa de literales exactos |

Cada parche se ancla a un texto exacto. Si upstream cambia ese texto, la
compilación **falla** con un mensaje que nombra el parche; nunca se salta en silencio.

### 4.3 Contrato entre la capa Python y la capa de construcción
- Home: `~/.janitor`. Motor: `~/.janitor/hermes-agent`. Entorno: `~/.janitor/hermes-agent/venv`.
- Arranque: `<venv>/bin/python -m janitor.cli serve --host 127.0.0.1 --port 0 [--profile P]`.
- Comando de usuario: `~/.local/bin/janitor`.
- `userData` de Electron: `~/.config/Janitor` (deja de compartirse con Hermes Desktop).

### 4.4 Decisiones técnicas tomadas por el orquestador
Se pueden revisar; ninguna es decisión de producto.
- `install.sh` pasa a ser touchpoint en el árbol en vez de generarse al compilar: el
  instalador de un fork debe instalar el fork por cualquier vía de respaldo.
- No se reutiliza `~/.janitor/janitor-core`. La app instala su propia copia en
  `hermes-agent/`; las instalaciones viejas no se adoptan (decisión 2.9).
- `extraMetadata.productName` pasa a `Janitor`. Con ≤10 usuarios pesa más no
  compartir estado con un Hermes Desktop real que conservar ajustes de ventanas.
- «Hermes Cloud» no se renombra (servicio de terceros); se intenta ocultar en F1-08.

### 4.5 Operación cotidiana, actualización e instalaciones existentes

Lo que se sabe hoy por lectura de código; cada punto abierto tiene su tarea.

- **Cerrar la ventana.** En Linux, cerrar la última ventana cierra la app
  (`apps/desktop/electron/main.ts`, `window-all-closed`) y con ella su motor.
- **Segundo plano.** Las tareas programadas y Telegram solo funcionan mientras hay un
  proceso que los atienda: la app abierta, o un gateway instalado como servicio
  (`janitor gateway install`). Con la app cerrada y sin servicio, se detienen. Sin
  verificar: inicio de sesión, reinicio del equipo, app y TUI a la vez, y que no se
  dupliquen gateways (F1-24). Decidido: al configurar Telegram la app ofrece instalar
  el gateway como servicio.
- **Actualización.** El motor se actualiza por `janitor update` (directiva 13). El
  AppImage **no** se reemplaza: `scripts/desktop-update/posix.sh` termina con un aviso
  en inglés de que el paquete de escritorio no cambió. Falta el contrato único de
  actualización: origen de los releases, compatibilidad entre app, motor y plugin,
  y qué ve el usuario si algo falla (F1-21). Decidido: el AppImage nuevo llega por
  descarga guiada desde los releases del fork; no hay actualización automática.
- **Instalación existente.** La app y la instalación antigua comparten `~/.janitor`.
  Abierta sobre un home con `janitor-core`, la app instalaría un segundo motor en
  `hermes-agent/`, la migración de layout correría sobre ese home y
  `janitor/seed.py::ensure_command_link` reapuntaría el comando `janitor` al motor
  nuevo. Decidido (2.9): una guarda lo impide (F1-22) y no hay adopción: lo antiguo se
  desinstala antes.
- **Dónde actúan los servicios.** La pantalla Servicios opera sobre el equipo donde
  corre el motor, no sobre el equipo que muestra la app si la conexión es remota.

## 5. Tablero de tareas

Estados: `pendiente` · `en curso (quién)` · `hecho` (lo dice quien lo ejecutó) ·
`auditado` (lo confirmó un revisor distinto).

`auditado` se desglosa en tres niveles, y el estado dice hasta cuál llegó:
**código** (un revisor distinto leyó el diff) · **pruebas** (ese revisor volvió a
correr las pruebas automáticas y pasan) · **aceptación** (se comprobó funcionando en
el recorrido real que pide la tarea). Una tarea sin «aceptación» no está cerrada: su
estado nombra qué falta y en qué tarea se comprueba. Una prueba de código nunca
cuenta como demostración de una instalación, actualización o despliegue real.

### Fase 0 — Preparación

| ID | Tarea | Estado |
|---|---|---|
| F0-01 | Decisiones de producto cerradas | auditado |
| F0-02 | Verificación de supuestos en el código (sección 3) | auditado |
| F0-03 | `AGENTS.md`: directivas 8 y 9 reescritas, 17-20 nuevas | auditado |

### Fase 1 — La app instala Janitor de verdad

Criterio de terminado: en un Linux limpio, instalar el AppImage deja un Janitor
funcional en español, con su identidad, sin «Hermes» en el uso normal y con
`janitor` abriendo el TUI.

| ID | Tarea | Alcance de archivos | Verificación | Estado |
|---|---|---|---|---|
| F1-01 | Siembra `janitor/seed.py` + semilla mínima + lanzador apto para la app | `janitor/seed.py`, `janitor/cli.py`, `janitor/home.py`, `assets/janitor/config.yaml`, `tests/janitor/` | `scripts/run_tests.sh tests/janitor/` | auditado: código y pruebas; aceptación en F1-15 |
| F1-02 | `scripts/install.sh` como touchpoint: repo del fork, comando `janitor`, sin skills heredadas | `scripts/install.sh`, `janitor/overlay.yaml`, `tests/janitor/` | `python -m janitor.overlay check` + pruebas | auditado: código y pruebas; aceptación en F1-15 |
| F1-03 | Motor de parches de la capa de construcción (anclas, aplicar, revertir a prueba de fallos) + P1-P5 | `apps/desktop-janitor/` | pruebas node de `apps/desktop-janitor/` | auditado: código y pruebas; aceptación en F1-15 |
| F1-04 | Reglas de marca del catálogo (P6) + prueba de vigilancia | `apps/desktop-janitor/` | prueba de vigilancia en verde | auditado: código y pruebas; aceptación en F1-15 |
| F1-05 | Literales de Electron y de la interfaz (P7, P8) | `apps/desktop-janitor/` | prueba de anclas + vigilancia | auditado: código y pruebas; aceptación en F1-15 |
| F1-06 | `SOUL.md` y bienvenida de Telegram: de código a tecnología | `assets/janitor/SOUL.md`, `janitor/plugin/telegram.py`, su prueba | `scripts/run_tests.sh tests/janitor/` | auditado: código y pruebas; aceptación en F1-15 |
| F1-07 | Compilación real de la app Janitor y prueba en home limpio | — | AppImage arranca, instala y abre chat | auditado: código y pruebas; aceptación parcial (compila y arranca sin pantalla, con `HERMES_DESKTOP_HERMES_ROOT` apuntando al repo: no demuestra descarga ni instalación) → F1-15 |
| F1-08 | Onboarding: MiniMax primero, Nous y «Hermes Cloud» ocultos | `apps/desktop-janitor/` | revisión visual | auditado: código y pruebas; aceptación parcial (solo la primera pantalla y el formulario de clave) → F1-15 |
| F1-09 | Actualización desde la app por el flujo Janitor (directiva 13) | `scripts/desktop-update/posix.sh` (touchpoint), `janitor/update_core.py`, `janitor/overlay.yaml`, pruebas | `scripts/run_tests.sh tests/janitor/` + `tests/scripts/desktop_update/` | auditado: código y pruebas; aceptación pendiente (ninguna actualización real) → F1-21 |
| F1-10 | Español para plugins `kanban`, `hermes-bots`, `radio` y las 6 claves sin traducir | `apps/desktop-janitor/` | vigilancia de idioma | auditado: código y pruebas; aceptación pendiente (sin revisar en pantalla) → F1-15 |
| F1-11 | CI: compilar la app Janitor y publicar el AppImage | `.github/workflows/` | job en verde | auditado: código y **aceptación del CI** (`Janitor CI` en verde en la rama publicada, corrida 45285144598: Python, instalación mínima, TUI, web, capa de construcción, macOS y Windows). El workflow de release (`janitor-desktop-release.yml`) sigue sin ejecutarse: necesita una etiqueta |
| F1-12 | `janitor update` lanzado desde la app: reiniciar gateways en ejecución y reconstruir `web/`, como hace el flujo de upstream | `janitor/update_core.py`, pruebas | prueba de comportamiento | auditado: código y pruebas; aceptación pendiente (sin actualización ni reinicio reales) → F1-21 |
| F1-13 | La primera pantalla sale con tema claro: aplicar los colores del skin desde el arranque | `apps/desktop-janitor/` | captura de la primera pantalla | auditado: código, pruebas y aceptación (captura de la compilación real) |
| F1-14 | Mensajes del motor que llegan a la app en inglés o con «Hermes» (errores de credenciales, «run `hermes setup`») | por definir | captura | auditado: código y pruebas; aceptación parcial (un mensaje real generado; el resto en F1-19) |
| F1-15 | Instalación real de punta a punta en un home limpio con el AppImage publicado | — | checklist de abajo | **aceptada en instalación real** con la app compilada en local (`60434274ff`), dos veces desde un home vacío: instala, siembra y arranca sola, sin pantalla de fallo, sin `~/.hermes`, sin `cua-driver`, con las etapas y el instalador en español. Sin comprobar todavía: elegir proveedor y chatear (sin clave), abrir el TUI, fallos (sin red, interrupción, reparación), y un AppImage publicado |
| F1-16 | Un gateway arrancado como servicio (sin pasar por el lanzador) no ve el catálogo español de Janitor: que el plugin exporte `HERMES_BUNDLED_LOCALES` al registrarse | `janitor/plugin/__init__.py`, `janitor/locales/`, pruebas | prueba de comportamiento | auditado: código y pruebas; aceptación pendiente (bot real) → F1-23 |
| F1-17 | Los gateways lanzados como `janitor gateway run` / `-m janitor.cli gateway run` no los reconoce el descubrimiento de upstream (`looks_like_gateway_command_line`), así que ninguna actualización los reinicia | `gateway/status.py` (touchpoint) o lanzar siempre por `hermes_cli.main` | prueba de comportamiento | auditado: código y pruebas (sin tocar `gateway/status.py`: el lanzador hace exec al comando canónico); aceptación pendiente (reinicio real) → F1-21 |
| F1-18 | El verde lima del skin no llega a la app: el conversor de upstream nunca lee `ui_primary`; el color de marca en la app queda en morado | `apps/desktop-janitor/` | captura | auditado: pruebas (243/243 node, 224 anclas, overlay check) y **aceptación en la app compilada** sin pantalla (capturas de proveedor, principal, Skills, Servicios y Agentes; el dueño aprobó principal y Skills). Sin revisor distinto del código. Decidido el 2026-11-24: **línea gráfica** = fondo `#150f23`, lima `#c2ef4e` como principal, morado como acento y banner J4NITOR-AGENT en la bienvenida, todo en `brand/theme.mjs`. Sin ver: un chat con mensajes, diálogos y errores sobre el fondo nuevo → F1-15 |
| F1-19 | Textos del motor aún en inglés o con «Hermes»: aviso de canal principal de Telegram, descripciones de comandos en `/help`, errores RPC crudos, routers web, `setup`/`doctor`, avisos finales de `scripts/desktop-update/posix.sh` («Backend updated, but…», «Reopen Hermes…») y errores del emparejamiento de Telegram (`hermes_cli/web_server_messaging.py`) | por definir (ver informe de F1-14 en la bitácora) | vigilancia + recorrido visual de F1-15 | auditado: código y pruebas; aceptación parcial en la app compilada (paleta de comandos y Conexiones guardadas vistas en español). Sigue sin ver nada en un Telegram real. Queda sin resolver: salida de los ayudantes de upstream durante `janitor update` (stash, dependencias, Node), pregunta de `/update` con botones en Telegram, router de mensajería, errores RPC de `tui_gateway`, menús de Slack/Discord, `/help` del CLI/TUI, `setup`/`doctor`, `/login`·`/topup`·`/subscription` en la ayuda del motor, las 28 skills de upstream del catálogo siguen en inglés fuera de la app (TUI, Telegram y el índice del prompt), pantalla «Actualizaciones remotas» (habla de SSH), `pet-generate/generate-unavailable.tsx` y `settings/constants.ts:51` |
| F1-20 | `/update` enviado desde Telegram ejecutaba `python -m hermes_cli.main update --gateway`: el flujo de upstream, no `janitor update` (directiva 13). Ahora el plugin envuelve el lanzador de la actualización del gateway y este ejecuta `python -m janitor.cli update --gateway` | `janitor/plugin/gateway_update.py`, `janitor/plugin/__init__.py`, `tests/janitor/test_janitor_monkeypatch_signatures.py`, `AGENTS.md` (sin touchpoint: `gateway/` queda idéntico a upstream) | prueba de comportamiento | auditado: código y pruebas por el orquestador + revisión de solo lectura de Codex (no repitió las pruebas); aceptación pendiente (`/update` real desde Telegram) → F1-21. Windows sin cubrir. Defecto heredado de upstream sin corregir: dos `/update` simultáneos comparten marcadores y pueden cruzar resultados |
| F1-21 | Diseño: [`actualizacion-diseno.md`](actualizacion-diseno.md) (tareas F1-21a a F1-21g). Contrato único de actualización (sección 4.5): origen de releases, compatibilidad app–motor–plugin, cómo llega el AppImage nuevo, bloqueo compartido, interrupción y recuperación, resultado visible en español; cubre app, TUI y Telegram. Reúne la aceptación de F1-09, F1-12, F1-17 y F1-20 | por definir. **Decidido:** el AppImage nuevo llega por descarga guiada desde los releases del fork, con aviso en español; sin actualización automática | actualización real de una versión publicada a la siguiente, con un gateway en marcha | F1-21a, b, c, d y e: auditado, código y pruebas. **F1-21f hecha el 2026-11-24**, pruebas sin revisor distinto: el AppImage se llama siempre `Janitor-linux-x86_64.AppImage` (`electron-builder.janitor.json`) y el workflow rechaza, antes de compilar, una etiqueta que no sea `v` + la versión mostrada de `pyproject.toml` (`python -m janitor.release_channel --check-tag`; hoy `v0.21.5-janitor.1`); el job en sí solo se demuestra con una etiqueta real. Pendiente: F1-21g (aceptación: actualizar de una versión publicada a la siguiente con un gateway en marcha, desde app, terminal y Telegram). Nada de esto se ha visto en una actualización real. Sin corregir: carrera residual entre la guarda de `/update` y el bloqueo; el aviso de contrato se pierde si la corrida que lo subía se cortó; la sonda de dependencias mira `venv/bin/python` del checkout, que puede no ser donde instaló el respaldo de upstream |
| F1-22 | Guarda de instalación existente: si el home tiene `janitor-core`, la app y `install.sh` se detienen con un aviso en español y no instalan un segundo motor ni reapuntan `janitor`, hasta que exista F5-01 | `scripts/install.sh` (touchpoint), `janitor/overlay.yaml`, `tests/janitor/test_janitor_install_sh.py`, `tests/janitor/install_sh_harness.py` | prueba de comportamiento con un home temporal que imita la instalación antigua; el home queda intacto | auditado: código y pruebas; aceptación parcial (instalador real corrido sin red sobre un home temporal antiguo: se niega en modo monolítico, en las 10 etapas y en `--ensure`, home intacto). Sin ver en pantalla → F1-15. Caso marginal sin cubrir: `--hermes-home ""` |
| F1-23 | Telegram desde la app: probar el QR con un bot real (autorización, caducidad, reintento, servicio caído), nombre con que nace el bot, `/start` y avatar; la ruta de pegar un token siempre visible | por definir | recorrido con un bot real | parcial: la app envía `bot_name: 'Janitor'` (parche de construcción) y la ruta por token sigue visible; el valor por defecto «Hermes Agent» sigue en `hermes_cli/web_routers/messaging.py:685` para otros clientes. Pendiente: probar el QR con un bot real (¿respeta el servicio de Nous el nombre?), `/start` y avatar |
| F1-24 | Operación cotidiana (sección 4.5): al configurar Telegram la app ofrece instalar el gateway como servicio (el usuario confirma; nunca se instala solo); cerrar ventana, Salir, inicio de sesión, reinicio, app y TUI a la vez, sin gateways duplicados; entrada en el menú de aplicaciones, diagnóstico, reparación y desinstalación conservando datos | por definir | recorrido en la instalación de F1-15 | pendiente. **Decidido:** ofrecer el gateway como servicio al configurar Telegram |
| F1-25 | Memoria integrada con MiniMax, en casos observables: guardar una preferencia, recuperarla tras reiniciar, corregirla, y que otro perfil no la vea; qué pasa con lo guardado al cambiar de proveedor de memoria | — | los cuatro casos, con evidencia | pendiente (necesita una clave real: la introduce el dueño) |
| F1-26 | Defectos de la primera instalación real (bitácora 2026-11-23): (a) pantalla «Janitor no pudo iniciarse» durante la instalación, que no se recupera sola al terminar; (b) la app crea `~/.hermes` con un `SOUL.md` de Hermes (sonda `canImportHermesCli` sin `HERMES_HOME`); (c) el instalador instala `cua-driver` (Computer Use) sin preguntar, con identificador de telemetría y archivos en `~/.cursor` y `~/.agents`; (d) inglés y «Hermes» en las etapas y la salida del instalador, en `janitor --version` y en `janitor services list`; (e) la comprobación de contrato no se repite al terminar la instalación | `apps/desktop-janitor/`, `scripts/install.sh` (touchpoint), `janitor/services.py`, `janitor/skills/services/*/service.yaml` | repetir la instalación real en un home limpio: sin pantalla de fallo, sin `~/.hermes`, sin `cua-driver`, recorrido en español | auditado: código, pruebas y **aceptación en instalación real** (los cinco defectos no reaparecen). Restos en inglés en la salida desplegada del instalador: líneas `[bootstrap]` de la app, títulos del manifiesto (`Download Hermes Agent`), salida de uv, git y Playwright, y dos líneas de `janitor/seed.py` |
| F1-27 | La comprobación de actualizaciones y `janitor update` siguen la rama `main`, no la rama con la que se compiló la app: una instalación hecha desde `janitor-app/fase-1` muestra «Hay una actualización» (`.update_check`: `target` = `origin/main`, `behind: -1`) y `janitor update` la llevaría a `main`, que hoy es **más antiguo**. Se resuelve al integrar la rama en `main` antes de entregar la app, o haciendo que el motor siga la rama de su compilación (decisión «canal del motor») | `janitor/update_core.py`, la sonda de actualizaciones de upstream | instalación real desde la rama: sin aviso falso | resuelto por integración: PR #91 fusionado en `main` (`50212e2832`, 2026-11-24), que ya no es más antiguo que la rama. Aceptación pendiente (ninguna instalación real desde `main` ha mostrado la comprobación sin aviso falso) → F1-15. La decisión «canal del motor» sigue abierta |
| F1-28 | Canal del motor por versiones etiquetadas (decisión 2.10): la sonda de actualizaciones y `janitor update` siguen la última etiqueta `v…` del fork, no `origin/main`; cubre app, terminal y `/update` de Telegram; un `main` más nuevo que la última etiqueta no produce aviso ni actualización; sin etiquetas publicadas, no hay nada que actualizar. Va junto con F1-21f (etiqueta = versión) | `janitor/update_core.py`, la sonda de actualizaciones de upstream (touchpoint si hace falta, declarado en `janitor/overlay.yaml`), `tests/janitor/`, `actualizacion-diseno.md` | prueba de comportamiento con un repo temporal (main por delante de la etiqueta: sin aviso; etiqueta nueva: aviso y actualización a esa etiqueta); aceptación en F1-21g | auditado: código (el orquestador leyó los diffs de los dos subagentes) y pruebas (repetidas por el orquestador); **aceptación pendiente** → F1-21g: nada se ha visto con una etiqueta real. **Diseño elegido con el dueño:** rama `stable` que solo mueve el workflow de release (no «seguir etiquetas» pieza por pieza). Una sola fuente: `janitor/release_channel.py`. Motor: `update_core.py` (por defecto el canal; sin `origin/stable` avisa «todavía no hay ninguna versión publicada» y sale con 0), touchpoint `update-channel` en `hermes_cli/banner.py` (constante `_UPDATE_BRANCH`, `main` en upstream), aplicado desde el lanzador y el plugin. App: parches P19 (`brand/release-channel.mjs`). Instalador: rama por defecto. Workflow: en una etiqueta sella `stable`, exige que el commit esté en `main` y avanza `stable` sin forzar **antes** de adjuntar el AppImage. **Sin verificar / riesgos:** el workflow no se ha ejecutado; GitHub puede rechazar el push de `stable` hecho con `GITHUB_TOKEN` si entre dos etiquetas cambió algún archivo de `.github/workflows/` (haría falta un token con permiso `workflows` o una deploy key; el job se detiene antes de publicar); hasta la primera etiqueta `stable` no existe, así que `install.sh` sin `--branch` no puede clonar; la caché `.update_check` no incluye la rama en su clave; no se comprobó que en un gateway el plugin se registre antes de la precarga del banner; el comando manual que muestra la app sigue diciendo `hermes update` (→ F1-19) |
| F1-29 | Instalación base sin navegador (decisión 2.10): la app instala sin Chromium de Playwright ni `browser-use`; se descargan al primer uso de las herramientas de navegación, con aviso en español; si la descarga falla, el error dice cómo reintentar | por definir: los argumentos con que la app invoca `scripts/install.sh` (`--skip-browser` ya existe) en `apps/desktop-janitor/`, y el camino de descarga al primer uso | instalación real en home limpio: sin Chromium ni `browser-use`, tiempo anotado; primer uso de navegación descarga y funciona | auditado: pruebas (`scripts/run_tests.sh tests/janitor/test_janitor_install_sh.py` 18/18; dos nuevas), sin revisor distinto. Hecho en `scripts/install.sh` (touchpoint), no en la app: el navegador pasa a opcional (`--with-browser`), igual que Computer Use, así vale para cualquier vía de instalación; avisos del instalador en español. **Aceptación pendiente** → F1-15: instalación real sin navegador (tiempo y disco) y primera navegación. Leído en el código, sin probar: sin Chromium las herramientas `browser_*` no se anuncian (`check_browser_requirements`), pero `browser_exec` (Browser Use por `uvx`, que el instalador sí deja) sigue disponible y al usarlo el motor descarga Chromium una vez (`_maybe_autoinstall_chromium`, ~170 MB, hasta 600 s, permitido por `security.allow_lazy_installs`). **Falta:** el aviso en español durante esa primera descarga (hoy solo queda una línea en inglés en `agent.log`; el usuario ve una llamada lenta) |
| F1-30 | Ocultar en la app el catálogo de plugins y el Skills Hub de Hermes (decisión 2.10) | `apps/desktop-janitor/` (parches de construcción sobre `plugin-catalog.ts`, `embedded-hub-picker.tsx` y sus entradas de menú) | anclas + recorrido en la app compilada: ninguna entrada lleva a esas páginas | auditado: pruebas (228 anclas, 243/243 node) y **aceptación en la app compilada** sin pantalla; sin revisor distinto. `brand/hidden-surfaces.mjs` (P18): no se monta el Skills Hub, ni el iframe ni la sección del catálogo de plugins, y la lista «Disponibles para instalar» de Capacidades → Skills queda vacía (era una tercera vía, hallada al mirar la app: skills opcionales de upstream con un clic). Comprobado en Capacidades → Skills y → Plugins: ningún iframe y ninguna petición a `nousresearch`. Sigue abierto: el enlace `hermes://plugin/install?catalog=…` aún resuelve contra el catálogo de Hermes; «Instalar desde Git» se conserva. Visto de paso, para F1-19: cabecera «Agente en Hermes (default)», descripciones de plugins en inglés (la del plugin `janitor` es la de Hermes), skill `hermes-agent` y autor «Hermes Agent» en la lista |

**Checklist de F1-15.** Con el AppImage publicado, en un Linux limpio, **sin**
`HERMES_DESKTOP_HERMES_ROOT` y sin Docker ni herramientas de desarrollo preparadas:

1. Descarga del instalador, instalación, siembra y arranque; se anota qué se
   descarga en el primer arranque y qué tuvo que hacer el usuario.
2. Elección de proveedor y un chat que responde, en español y con la identidad de Janitor.
3. `janitor` abre el TUI en un terminal **nuevo**, con el mismo home y sesiones.
4. Fallos: sin red, instalación interrumpida y reintento, instalación parcial, reparación.
5. Recorrido visual completo, incluidos errores: sin «Hermes» ni inglés fuera de las
   excepciones declaradas (cierra la aceptación de F1-08, F1-10 y F1-14).
6. El job de CI que compila y publica, en verde (cierra F1-11).

### Fase 2 — Agente principal y catálogo de skills

Diseño, alcances y verificaciones: [`fase-2-diseno.md`](fase-2-diseno.md).

| ID | Tarea | Estado |
|---|---|---|
| F2-01 | Perfil principal con su lista de skills | auditado: código y pruebas |
| F2-02 | Catálogo por propósito | auditado: código y pruebas |
| F2-03 | Plantillas Investigador y Creador de proyectos | auditado: código y pruebas |
| F2-04 | Retiro de `agents.py`, `opencode/` y skills obsoletas | auditado: código y pruebas |
| F2-05 | `janitor-onboarding` reescrita | auditado: código y pruebas |

### Fase 3 — Skills nuevas del equipo (Linux)

| ID | Tarea | Estado |
|---|---|---|
| F3-01 | Limpieza del equipo | auditado: código, pruebas y aceptación en home temporal (prueba adversaria de la bitácora) |
| F3-02 | Organización de archivos | auditado: código, pruebas y aceptación en home temporal (plan → aplicar → deshacer) |
| F3-03 | Salud del sistema | auditado: código, pruebas y aceptación en el equipo de desarrollo; parsers de apt/dnf sin probar en máquina real |
| F3-04 | Mantenimiento programado | auditado: código y pruebas; aceptación pendiente (ningún disparo real de la tarea). La ejecución programada solo informa, nunca aplica arreglos → F1-24 |
| F3-05 | Creación de proyectos | auditado: código y pruebas |

### Fase 4 — Aplicativos opcionales

| ID | Tarea | Estado |
|---|---|---|
| F4-01 | Skill guiada de Honcho | auditado: código y pruebas; aceptación pendiente (sin despliegue real, sin Honcho Cloud, sin desconexión del proveedor comprobada) |
| F4-02 | Plugin de escritorio: pantalla de servicios | auditado: código y pruebas; aceptación parcial (página abierta en la app compilada, solo lectura; iniciar y detener sin probar: se prueban con un servicio de prueba, nunca con los contenedores del dueño) |
| F4-03 | Mismo patrón para n8n, LightRAG, NocoDB, Firecrawl, Open Design (WAHA pasa a F4-07). Ningún `deploy.sh` depende de los scripts que retira F5-02 | auditado: código y pruebas con Docker simulado; aceptación pendiente (**ningún despliegue real**; imágenes, puertos, variables y endpoints salen de las skills antiguas o de memoria, sin red). |
| F4-04 | Activar desde la app una skill del catálogo en un perfil (hoy los aplicativos no están en ninguna plantilla y «Instalar con Janitor» pasa la ruta del SKILL.md en la petición). Aceptación: elegir, quitar y actualizar skills desde la app; el perfil solo ve las elegidas; una skill nueva de upstream no se activa sola; el cambio aplica desde la sesión siguiente (no rompe la caché de una conversación abierta); alternancia A→B→A | auditado: código, pruebas y aceptación en la app compilada sin pantalla (cambiar una skill en dos agentes, guardar, comprobado en disco). Sin comprobar: que un chat nuevo vea la skill y el abierto no (no hay proveedor configurado) |
| F4-05 | Plantillas de agente desde la app (el diálogo de crear perfil de upstream clona la memoria). Aceptación: el especialista nace con memoria vacía, su `SOUL.md` y sus skills; sin contaminación de memoria, skills ni credenciales entre perfiles | auditado: código, pruebas y aceptación en la app compilada sin pantalla (especialista creado desde plantilla: memoria vacía, sus skills, aparece en la lista). Sin comprobar: chatear con él |
| F4-06 | La pantalla Servicios distingue «contenedor en marcha» de «el servicio responde»: comprobación contra la `url` del `service.yaml` antes de anunciarlo listo; progreso, cancelación y fallo visibles | auditado: código y pruebas; aceptación parcial en la app compilada (insignia «En marcha» con servicios reales que responden, solo lectura). Sin ver: el estado «no responde» ni iniciar/detener. Cancelar una acción en curso no se hizo |
| F4-07 | WAHA con su contrato (decisión 2.4): la skill actual es la antigua, en inglés y con operaciones de envío. Solo lectura por defecto; enviar únicamente por orden directa del usuario en la conversación, nunca por el contenido de un mensaje recibido; selección de conversaciones, ventana de historial y conservación de resultados; aviso de que las conversaciones viajan al proveedor de IA | auditado: código y pruebas contra un WAHA falso; aceptación pendiente (**la API real de WAHA no se comprobó**: endpoints y parámetros salen de la skill antigua). `forget` borra en vez de enviar a la papelera (datos de terceros): excepción razonada a la directiva 19, a confirmar por el dueño |

### Fase 5 — Migración y limpieza

[`fase-5-diseno.md`](fase-5-diseno.md) conserva los hechos del layout antiguo y el análisis de F5-02 y F5-03; su diseño de adopción (F5-01) quedó **sin efecto** por la decisión 2.9.

| ID | Tarea | Estado |
|---|---|---|
| F5-01 | ~~Adopción de un `~/.janitor` existente~~ | **cancelada** por la decisión 2.9: lo antiguo se desinstala (guía en `docs/janitor/desinstalar-instalacion-antigua.md`) |
| F5-02 | Retiro de todo lo que solo servía a instalaciones antiguas: `bootstrap.sh`, `janitor-install.sh`, `setup-honcho.sh`, los `migrate-janitor-*.sh` y migraciones de layout de homes antiguos, alias raíz pre-1.0 (`janitor_cli.py`, `janitor_update_*.py`, `janitor_version.py`, `janitor_ext/`), ramas `janitor-core` / `.venv` de `update_core.py` y `seed.py`, el job de CI que ejecuta `janitor-install.sh`, y las secciones de `AGENTS.md` que los describen. Ya no espera a nada (decisión 2.9) | auditado: código y pruebas; el job `installer-e2e` de CI reescrito no se ha ejecutado. Quedan: residuo en `scripts/install.ps1` (bloque del fork que nunca se ejecuta), `.env.example` y `scripts/verify-firecrawl-pgcron.sh` con restos de Firecrawl, y documentación histórica en `docs/janitor/` que cita lo retirado |
| F5-03 | Revisar si `janitor/update_core.py` se puede reducir. No antes de F1-21: primero se fija qué responsabilidades se conservan y dónde | pendiente |

### Fase 6 — Segundo release: Windows, macOS y paquete de Arch (orden del dueño, 2026-11-25)

El dueño pidió que el siguiente release lleve la app para **Windows** y **macOS**, y un **paquete para
Arch Linux** con icono y entrada en el lanzador. No está disponible para probar: todo se construye y
se prueba en GitHub Actions y la evidencia son los artefactos y capturas de CI. Diseños de dos
subagentes Opus de solo lectura (2026-11-25), contrastados por muestreo por el orquestador.

**Decisiones tomadas por el orquestador, a confirmar por el dueño** (se eligió la opción que menos
piezas mueve; ninguna es irreversible antes de etiquetar):
- Home `~/.janitor` también en Windows (`%USERPROFILE%\.janitor`): un solo contrato para la app, el motor y el TUI.
- Windows solo x64 (`get-windows` no publica binario para arm64). macOS arm64 seguro; x64 solo si hay runner Intel.
- Sin certificados: macOS con firma ad hoc (`identity: "-"`), Windows sin firmar. El usuario tendrá que
  aceptar el aviso de Gatekeeper / SmartScreen; se documenta en español.
- Se mantiene el esquema de enlaces `hermes://` (ya aceptado en Linux).
- Arch: paquete `janitor-desktop-bin` construido desde el mismo AppImage publicado, comando
  `janitor-desktop` (el `janitor` a secas es el TUI). Se descartó el target `pacman` de electron-builder
  (dependencias inexistentes en Arch, nombre `hermes`, versión de upstream).

| ID | Tarea | Alcance | Verificación | Estado |
|----|-------|---------|--------------|--------|
| F1-31 | Paquete de Arch: plantilla `PKGBUILD`, lanzador, `.desktop`, generador y job de CI en contenedor `archlinux` (namcap + instalación de prueba) | `apps/desktop-janitor/packaging/arch/`, `apps/desktop-janitor/scripts/arch-package.*`, `janitor/release_channel.py` (`--expected-tag`), workflow de release | `makepkg` local, `node --test`, job en verde | hecho; CI en verde (corrida 45666821137); **sin probar en un equipo real** |
| F6-02 | Iconos `.ico` / `.icns` de Janitor y su copia por el overlay | `apps/desktop-janitor/assets/`, `scripts/build.mjs`, `build.test.mjs` | `node --test …/build.test.mjs` | hecho; CI en verde (corrida 45666821137); **sin probar en un equipo real** |
| F6-03 | Configuración de electron-builder para win/mac (targets, firma ad hoc, NSIS y permisos de macOS en español) | `apps/desktop-janitor/electron-builder.janitor.json` | prueba de la configuración fusionada | hecho; CI en verde (corrida 45666821137); **sin probar en un equipo real** |
| F6-04 | Parches de marca de Windows: home `~/.janitor`, identificador de app, identidad del `.exe`, aviso de app vieja por plataforma | `apps/desktop-janitor/brand/` | `build.mjs --check` + `node --test` | hecho; CI en verde (corrida 45666821137); **sin probar en un equipo real** |
| F6-05 | `scripts/install.ps1` de Janitor: repo del fork, `~/.janitor`, rama `stable`, sin navegador ni Computer Use por defecto, sin skills de upstream, siembra, comando `janitor`, se niega sobre instalaciones antiguas, textos en español en ASCII (PowerShell 5.1) | `scripts/install.ps1`, `janitor/overlay.yaml` (touchpoint `install-ps1`), `tests/janitor/` | overlay check + `os-compat` en Windows | hecho; CI en verde (corrida 45666821137); **sin probar en un equipo real** |
| F6-06 | `scripts/desktop-update/windows.ps1` actualiza con `janitor update` (directiva #13), sin `--force`, en español | `scripts/desktop-update/windows.ps1`, `janitor/overlay.yaml` | overlay check + prueba | hecho; CI en verde (corrida 45666821137); **sin probar en un equipo real** |
| F6-07 | Python en Windows: `seed` sin symlink, `/update` del gateway, skill de bienvenida visible en Windows, mensaje claro de servicios | `janitor/seed.py`, `janitor/plugin/gateway_update.py`, `janitor/skills/core/janitor-onboarding/SKILL.md`, `janitor/services.py`, `tests/janitor/` | `scripts/run_tests.sh tests/janitor/` + `os-compat` | hecho; CI en verde (corrida 45666821137); **sin probar en un equipo real** |
| F6-08 | Workflow de release con matriz de sistemas, verificación dentro de cada artefacto (sello, firma, arquitectura, identidad) y release con todos los archivos | `.github/workflows/janitor-desktop-release.yml` | PR en verde en todos los sistemas | hecho; CI en verde (corrida 45666821137); **sin probar en un equipo real** |
| F6-09 | Arranque de la app empaquetada en cada runner con Playwright y captura de pantalla como artefacto | `apps/desktop-janitor/scripts/smoke-packaged.mjs`, workflow | capturas en los artefactos | hecho; CI en verde (corrida 45666821137); **sin probar en un equipo real** |
| F6-10 | Instalación real del motor en runners de Windows y macOS (`install.ps1` / `install.sh`, `janitor --version`) | `.github/workflows/janitor-ci.yml` | job en verde | hecho; CI en verde (corrida 45666821137); **sin probar en un equipo real** |
| F6-11 | Instrucciones de instalación en español (Gatekeeper, SmartScreen, Arch) | `docs/janitor/instalar-app.md`, notas del release | revisión | hecho; CI en verde (corrida 45666821137); **sin probar en un equipo real** |
| F6-12 | Token para mover `stable` cuando entre dos etiquetas cambian archivos de workflow (este release los cambia) | secreto del repo + paso `git push` | release real | resuelto: el `GITHUB_TOKEN` movió `stable` en el release real (corrida 45714931560), aunque el release cambiaba workflows; no hizo falta token del dueño |

Riesgos propios de esta fase: nadie probará en un Windows ni en un Mac reales (la aceptación quedará
como «no verificada en equipo real»); macOS x64 compilado en un runner arm64 empaqueta un Electron arm64;
la CI corre con `PYTHONUTF8=1` y puede tapar errores de codificación en Windows; GitHub a veces no
asigna runner de macOS.

### Después
Windows y macOS (firma de código). WhatsApp como canal.

## 6. Protocolo de trabajo entre agentes

1. **Orquestación.** Un orquestador reparte las tareas del tablero a subagentes
   (modelo Opus). Cada subagente recibe: el ID, el alcance de archivos, el contrato
   de la sección 4.3, las verificaciones exigidas y lo que ya se descartó.
2. **Alcances disjuntos.** Dos agentes nunca escriben los mismos archivos a la vez.
   Si una tarea necesita un archivo fuera de su alcance, se detiene y lo reporta.
3. **Auditoría obligatoria.** El informe de un subagente no es prueba. El
   orquestador lee el diff completo, vuelve a correr las verificaciones y solo
   entonces marca `auditado`. Lo que no se pudo verificar se anota como no verificado.
4. **Reglas que ningún agente rompe.** Directivas 1-20 de `AGENTS.md`. En especial:
   no renombrar el core, declarar todo touchpoint en `janitor/overlay.yaml`, no
   suavizar la identidad, español en lo visible, `scripts/run_tests.sh` y nunca
   `pytest` directo.
5. **Git.** Se trabaja en la rama `janitor-app/fase-1`. Commits locales por tarea
   auditada. No se hace push ni se abre PR sin orden del dueño del proyecto.
6. **Agentes externos (Codex u otros).** Antes de empezar: leer este archivo y tomar
   una tarea `pendiente` marcándola `en curso (quién)`. Al terminar: estado, evidencia
   (comando y resultado) y una línea en la bitácora. Para revisar trabajo ajeno:
   auditar una tarea en `hecho` y pasarla a `auditado` o devolverla con el hallazgo.

## 7. Riesgos y puntos sin verificar

- **Nada se ha probado en una máquina limpia.** La sección 3 sale de leer código.
- Cada sincronización con upstream puede mover las anclas de los parches. Está
  cubierto: la compilación falla con el nombre del parche.
- La capa de construcción modifica `apps/desktop/` mientras compila. Cada archivo se
  guarda antes en un diario (`apps/desktop/.janitor-build-journal`). Si el proceso
  muere, la siguiente compilación restaura primero; a mano:
  `node apps/desktop-janitor/scripts/build.mjs --restore` (`--force` solo tras revisar
  los archivos que el aviso nombra como cambiados después del fallo). Una segunda
  compilación sobre el mismo checkout se rechaza mientras la primera siga viva.
  `python -m janitor.overlay check` detecta residuos pero no los recupera. Cubierto por
  pruebas (`patch-engine.test.mjs`) y visto tras una compilación fallida real; no se ha
  matado una compilación real a mitad.
- El lanzador fuerza `HERMES_HOME=~/.janitor`. Falta confirmar que no rompe el
  manejo de perfiles de la app (`--profile`).
- La marca en textos que envía el motor (errores, descripciones de comandos) no la
  cubre la capa de construcción.
- No está verificado que MiniMax llame de forma fiable a la herramienta `memory` (F1-25).
- El QR de Telegram depende de un servicio de Nous sin probar desde el fork (F1-23).
- El AppImage no se actualiza solo y una instalación antigua sufriría una adopción
  parcial (sección 4.5; F1-21, F1-22).
- `@nous-research/ui` puede mostrar marca de Hermes; sin verificar.

## 8. Bitácora

| Fecha | Quién | Qué |
|---|---|---|
| 2026-11-22 | Claude (orquestador) | Decisiones de producto cerradas; verificación de supuestos con tres subagentes; `AGENTS.md` actualizado; plan reescrito |
| 2026-11-22 | Subagentes Opus, auditado por el orquestador | F1-01 a F1-06 hechas y auditadas. Evidencia: `scripts/run_tests.sh tests/janitor/` → 24 archivos, 341 pruebas, 0 fallos; `python -m janitor.overlay check` limpio; `node --test apps/desktop-janitor/scripts/build.test.mjs` → 31/31; `build.mjs --check` → 135/135 anclas |
| 2026-11-22 | Claude (orquestador) | F1-07 primera mitad: `build.mjs --linux --dir` compila (requirió `npm ci` en la raíz). En el binario: instalador desde `reck74/Janitor-Agent`, home `.janitor`, motor por `-m janitor.cli` (3 sitios), menús en español, «Janitor terminó». `apps/desktop` quedó idéntico a upstream tras compilar y también tras una compilación fallida. **Sin probar:** instalación real en home limpio — el instalador se descarga por el SHA de la compilación, que debe existir en GitHub (hace falta push) |
| 2026-11-22 | Claude (orquestador) | Ajustes propios sobre F1-01: personalidades ampliadas a tecnología; `approvals.mode` se mantiene en `manual` (upstream pasó a `smart`: decisión pendiente del dueño) |
| 2026-11-22 | Subagente Opus, revisado por el orquestador | F1-07 arranque: la app compilada abre sin pantalla (Playwright + `--ozone-platform=headless`) con un HOME temporal y `HERMES_DESKTOP_HERMES_ROOT` apuntando al repo. Título «Janitor», interfaz en español, motor por `python -m janitor.cli serve`, `HERMES_HOME=<tmp>/.janitor`, userData `<tmp>/.config/Janitor`, nada en `<tmp>/.hermes`, home sembrado correcto, 16 skills visibles. El `~/.janitor` real no cambió. **Fallos vistos:** Nous Portal como único proveedor «RECOMENDADO»; error crudo del motor en inglés por la clave de MiniMax ausente; MiniMax al final de la lista de claves; tema claro en la primera pantalla; textos en inglés sueltos. Sin probar: instalación por red, menús nativos, `--profile` |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F1-09 y F1-11. Evidencia: `run_tests.sh tests/janitor/` → 26 archivos, 368 pruebas, 0 fallos; `run_tests.sh tests/scripts/desktop_update/` (upstream) → 25 pasan, 9 omitidas; overlay check limpio. Pendiente detectado → F1-12 |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F2 diseño (`fase-2-diseno.md`) y F2-02 catálogo: `python -m janitor.catalog check` → 37/37; 17 pruebas |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F1-08 y F1-10: 169 anclas, 54 pruebas node. Recompilado y capturado sin pantalla: la primera pantalla destaca MiniMax «RECOMENDADO», aviso de clave en español, Nous sin promoción. Sigue con tema claro (F1-13) |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F2-04: retiro de `agents.py`, `opencode/` y seis skills; `research/janitor-repo-research`; migración v2. `AGENTS.md` actualizado por el orquestador (directiva 3, contrato de instalación, jerarquía de skills) |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F3-03 y F3-04: `janitor-system-health` y `janitor-maintenance`. La auditoría corrió de verdad en el equipo de desarrollo: 24 hallazgos, salida 0, sin sudo ni escrituras. Sin probar: parsers de apt/dnf en una máquina real, y un disparo real de la tarea programada |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F2-01, F2-03, F2-05: perfil principal desde el catálogo, `janitor plantillas`, onboarding. Evidencia: `run_tests.sh tests/janitor/` → 31 archivos, 430 pruebas, 0 fallos; prueba manual en home temporal: `plantillas crear investigador` → perfil con memoria vacía y sus 6 skills. El orquestador corrigió `migrations/v1.py` para no re-añadir la raíz de skills a un home gestionado por el catálogo |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F3-01 y F3-02: `janitor-cleanup` y `janitor-file-organizer`. 30 pruebas. Prueba adversaria propia del orquestador en un home temporal: entradas metidas a mano en el plan (archivo fuera del home, `~/.ssh/id_rsa`, enlace simbólico hacia fuera, `/etc/hostname`) rechazadas; archivo cambiado tras planificar omitido; el elemento legítimo fue a la papelera con su `.trashinfo`. Organizador: plan → apply → undo devuelve el árbol idéntico. Devuelto una vez al subagente para dos correcciones: diario escrito antes de cada movimiento y no revelar el digest válido en el error |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F3-05 `janitor-project-create`: 39 pruebas. El subagente generó y verificó con red proyectos reales de Python (uv) y Node (npm y pnpm): lint y pruebas pasan. El tipo ops queda sin lint verificado (no hay shellcheck en la máquina) |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F1-13 tema: 174 anclas, 62 pruebas node. Recompilado y capturado: primera pantalla oscura con la paleta del skin, sin azul ni naranja; formulario de clave con MiniMax preseleccionado |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F1-14 mensajes del motor: `janitor/locales/es.yaml` (solo diferencias) + touchpoint `backend-user-copy`. Mensaje real generado por el orquestador: «Janitor no pudo iniciar el asistente de esta sesión… ejecuta `janitor setup`…». Pruebas de upstream de los módulos tocados: pasan sin cambios |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F1-12: `janitor update` reconstruye `web/`, escribe el código de salida del gateway y reinicia la flota del home con los ayudantes de upstream; no reinicia nada si algún gateway del home corre desde otra instalación. 108 pruebas de actualización. Hallazgo → F1-17 |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F4-01 skill guiada de Honcho: 20 pruebas con Docker simulado; preflight de solo lectura corrido por el orquestador en un home temporal. Corrige que el compose pasaba todo el `.env` del home a los contenedores |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F4-02 pantalla Servicios: plugin de ejecución sembrado en `<home>/desktop-plugins/janitor` + backend en `<home>/plugins/janitor/dashboard`. Abierta por el orquestador en la app compilada sin pantalla: entrada en la barra lateral y estado real de los contenedores (solo lectura) |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F1-16, F1-17 y fail-safe de Honcho. Hallazgo → F1-20 |
| 2026-11-22 | Claude (orquestador) | **Verificación final de la rama `janitor-app/fase-1` (22 commits sobre `main`, sin push):** `scripts/run_tests.sh tests/janitor/` → 37 archivos, 619 pruebas, 0 fallos · `node --test apps/desktop-janitor/scripts/build.test.mjs` → 70/70 · `build.mjs --check` → 174/174 anclas · `python -m janitor.overlay check` limpio · `python -m janitor.catalog check` → 42/42 · `build.mjs --linux --dir` compila y la app arranca sin pantalla. **No verificado en ningún momento:** instalación real desde la app en una máquina limpia, AppImage, workflows de CI, actualización real, reinicio real de gateways, despliegue real de Honcho, un bot de Telegram real, Windows y macOS, y la suite completa de upstream (solo se corrieron los archivos de upstream de los módulos tocados) |
| 2026-11-22 | Claude (orquestador) | Revisión de `recomendaciones-codex-para-claude.md` (R01–R13) contra el plan y el código, solo lectura. Resuelta: R13. Parciales: R01, R02, R04, R06, R08, R09, R10. Pendientes: R03, R05, R07, R11, R12. Incorporado al plan con aprobación del dueño: precisiones en 2.1, 2.3, 2.4, 2.6, 3.1 y 3.4; sección 4.5; estado `auditado` desglosado en código, pruebas y aceptación; checklist de F1-15; tareas nuevas F1-21 a F1-25, F4-06 y F4-07; alcance ampliado de F1-19, F4-04, F4-05 y F5-01 a F5-03. No se cambió código. Descartado: tratar el nivel gratuito de Nous como activable (la compilación lo anula a propósito), más pruebas de interrupción del overlay y repetir las pruebas adversarias de F3. Sin verificar en esta revisión: que el aviso en inglés de `posix.sh` llegue tal cual a la pantalla, si los homes antiguos tienen el paquete de skills de Hermes copiado, y el comportamiento real del servicio de QR |
| 2026-11-22 | Dueño del proyecto | Decisiones tomadas sobre las propuestas del orquestador: AppImage por descarga guiada desde los releases del fork (F1-21); guarda ante instalación antigua ahora y adopción después de la primera instalación real (F1-22, F5-01); QR de Telegram con la ruta por token siempre visible (F1-23); ofrecer el gateway como servicio al configurar Telegram (F1-24). Sigue pendiente la prueba de memoria con MiniMax (F1-25) |
| 2026-11-22 | Subagente Opus (interrumpido por un corte de red con el trabajo ya escrito), auditado y cerrado por el orquestador | F1-22: `install.sh` se niega antes de escribir si el home tiene `janitor-core`, con aviso en español en stderr y en el marco JSON. Evidencia del orquestador: sin la guarda las 2 pruebas nuevas fallan, con ella pasan; `scripts/run_tests.sh tests/janitor/` → 37 archivos, 622 pruebas, 0 fallos; `python -m janitor.overlay check` limpio; `unshare -rn bash scripts/install.sh` y `--stage <cada una> --json` sobre un home temporal con `janitor-core` y un enlace `janitor` hacia él → salida 1 en todos, árbol idéntico antes y después. No se tocó `janitor/seed.py`: con la guarda, `ensure_command_link` no llega a ejecutarse sobre un home antiguo |
| 2026-11-22 | Claude (orquestador), sin revisor distinto todavía | F1-20: el plugin envuelve `gateway.slash_commands._spawn_detached_update` y le pasa el argv del lanzador Janitor. Se instala al registrar el plugin y, de nuevo, en el hook `pre_gateway_dispatch`: comprobado con el gestor de plugins real en un home temporal que el plugin se registra antes de que exista `gateway.run` (la instalación al registrar no actúa) y que el primer mensaje deja el envoltorio puesto; el comando resultante es `<venv>/bin/python -m janitor.cli update --gateway`. No se ejecutó ninguna actualización real ni un `/update` desde Telegram. El aviso «🔥 THE JANITOR: Initiating tactical update...» de `janitor/update_bootstrap.py` sigue en inglés y ahora llega a Telegram → F1-19 |
| 2026-11-22 | Claude (orquestador) | Prueba inestable detectada: `tests/janitor/test_janitor_system_organizer.py::test_collisions_never_overwrite_and_undo_restores_exact_tree` falló una vez en la suite completa (48 procesos) y pasó al reintentar; sola pasa 6 de 6. Sin diagnosticar; no la tocan los cambios de F1-20 ni F1-22. Queda como defecto por investigar (F3-02) |
| 2026-11-22 | Claude (orquestador) | Investigación de la prueba inestable del organizador: **sin causa diagnosticada**. No se reprodujo en 6 corridas del archivo solo, 48 corridas concurrentes de esa prueba con la CPU cargada y sin reintentos, ni 10 corridas de la suite completa. Revisados sin hallar dependencia del reloj ni del orden: huellas (`fingerprint`), colisiones, duplicados y presupuesto de tiempo (120 s). La salida del fallo original no se guardó. Único dato anómalo posterior: en una corrida bajo carga, `tests/janitor/test_mcp_router_discover.py` murió por SIGKILL externo; `systemd-oomd` está activo en el equipo de desarrollo y vigila `app.slice`, así que una muerte externa de un subproceso (la prueba lanza el script real) es una hipótesis para el fallo original, no un hecho. Las corridas de estrés del orquestador coincidieron con el cierre de aplicaciones del escritorio del dueño: no repetir bucles de la suite ni cargas concurrentes en este equipo. Si reaparece: guardar la salida completa de `scripts/run_tests.sh` (sección `⚠ FLAKY`) antes de nada |
| 2026-11-22 | Codex (modelo solicitado `gpt-6.2-astra`, solo lectura), verificado por el orquestador | Revisión de F1-20 y F1-22. Confirmado y corregido: `--ensure` de `install.sh` no pasaba por la guarda. Confirmado y trasladado a F1-19: «✅ Hermes update finished.» en `gateway/run_notifications.py`. Confirmado sin corregir: carrera heredada de upstream entre dos `/update` simultáneos; Windows; `--hermes-home ""`. Codex no ejecutó pruebas |
| 2026-11-22 | Subagentes Opus, auditado por el orquestador | F4-06 (salud de servicios), F4-07 (WAHA de solo lectura) y F1-19 (touchpoint `runtime-copy`: `agent/i18n.py`, `gateway/run_turn.py`, `gateway/run_notifications.py`, `hermes_cli/commands.py`, `hermes_cli/commands_platforms.py`, `hermes_cli/web_server_messaging.py`, más dos líneas de `scripts/desktop-update/posix.sh`). Evidencia del orquestador, una sola corrida: `scripts/run_tests.sh tests/janitor/` → 39 archivos, 656 pruebas, 0 fallos; `tests/gateway/test_update_command.py`, `test_update_streaming.py`, `tests/agent/test_i18n.py`, `tests/hermes_cli/test_commands.py` → 109 pasan; `python -m janitor.overlay check` limpio; `node --test …/servicios-plugin.test.mjs` → 9/9. Cabo suelto: `janitor-nocodb/SKILL.md` aún cita el script retirado `diff-waha-group.py` (F4-03) |
| 2026-11-22 | Codex (modelo solicitado `gpt-6.2-astra`, solo lectura) | Opinión de diseño para F5-01, sin aplicar: instalar el motor nuevo junto al antiguo sin mover `janitor-core`, probarlo aislado, respaldar con los escritores detenidos y solo entonces reapuntar `janitor`; adopción explícita desde la app con diario en `.backup/adoption-<id>/`; el gateway antiguo lo detiene el usuario (la migración no toca unidades systemd); motor viejo y respaldo se conservan hasta que el dueño pida retirarlos; restaurar tras usar la app nueva pierde las sesiones nuevas |
| 2026-11-22 | Claude (orquestador) | **Trabajo detenido por un problema del equipo de desarrollo**: al correr `scripts/run_tests.sh` algo envía SIGKILL a procesos ajenos (un proceso de pruebas o la propia app de Claude); no es falta de memoria (`oom_kill 0`). Otro agente lo investiga. Hasta que se resuelva no se corren pruebas en este equipo, así que ninguna tarea nueva puede pasar a «auditado» |
| 2026-11-22 | Subagentes Opus (solo lectura, sin pruebas), contrastado por muestreo por el orquestador | Dos diseños, sin implementar. **`actualizacion-diseno.md` (F1-21):** contrato de compatibilidad app↔motor por un entero (`janitor/desktop-compat.json`) que la app compara al arrancar; siete tareas. Defectos hallados y comprobados por el orquestador en el código: (1) si `janitor update --gateway` se rechaza por el bloqueo, el `finally` de `run_janitor_update` escribe «falló» en `.update_exit_code` y el chat anuncia un fallo con la actualización real en curso; (2) los botones «Obtener el instalador» / «Abrir la página de descarga» de la app Janitor apuntan a `hermes-agent.nousresearch.com` (`about-settings.tsx:27`, `updates-overlay.tsx:46`), declarados por error como excepción de marca; (3) una actualización cortada entre el pull y la instalación de dependencias se da por «al día» en la corrida siguiente. **`fase-5-diseno.md` (F5-01 a F5-03):** motor nuevo junto al antiguo en el mismo commit, entrada por terminal (`janitor adopt`) y reintento en la app, migración v3 para no ver cada skill desde dos árboles, respaldo de todos los SQLite, vuelta atrás que aparta el estado nuevo en vez de destruirlo. Se aparta de la opinión de Codex en la entrada (terminal, no app) y en exigir el mismo commit. Sin determinar: el nombre de la unidad del gateway que crearía `janitor gateway install` (posible segunda unidad junto a la antigua; afecta también a F1-24) |
| 2026-11-22 | Claude (orquestador) — **hecho, sin revisor distinto y sin correr la suite** (equipo de desarrollo bloqueado) | Tres defectos del diseño de F1-21 corregidos. (1) `/update` repetido: `janitor/update_core.py` ya no escribe el código de salida cuando se le rechaza por el bloqueo, y touchpoint nuevo `update-single-flight` en `gateway/slash_commands.py` (`_update_already_running`): si hay bloqueo vivo o un `/update` lanzado sin terminar, responde «ya hay una actualización en marcha» sin tocar los marcadores. (2) Actualización cortada: bandera por checkout `.git/janitor-update-deps-pending`, puesta tras un pull correcto y quitada tras dependencias y catálogo; la corrida siguiente la retoma aunque el árbol esté «al día». (3) `INSTALLER_URL` de `updates-overlay.tsx` y `about-settings.tsx` → releases del fork (dos literales nuevos). Evidencia, toda de un solo proceso: `python -m janitor.overlay check` limpio; `build.mjs --check` → 176/176 anclas; la comprobación de contrato `check_update_single_flight` y los ayudantes de la bandera ejecutados a mano en un directorio temporal, correctos. **Debe:** correr `scripts/run_tests.sh tests/janitor/` y las pruebas de upstream de `gateway/` (`test_update_command.py`, `test_update_streaming.py`); prueba de comportamiento para la reanudación (no escrita); revisión por un agente distinto. Estas correcciones adelantan parte de F1-21b, F1-21d y F1-21e |
| 2026-11-22 | Codex (modelo solicitado `gpt-6.2-astra`, solo lectura, sin ejecutar nada), verificado por el orquestador | Revisión del commit `0698ef4478`. **Confirmado y corregido** (sin correr la suite): la marca de dependencias pendientes se ponía después de que el pull moviera `HEAD` → ahora se pone antes y se quita si el pull falla y `HEAD` volvió a su sitio; en un worktree enlazado `.git` es un archivo → la marca usa `git rev-parse --absolute-git-dir` y un fallo al guardarla se avisa; un segundo `/update` podía pisar los marcadores mientras el observador aún entregaba el resultado → la guarda reserva también `.update_pending.claimed.json` y ya no mira el código de salida; «Notas de versión» abría los releases de Hermes → releases del fork (177/177 anclas). Evidencia de un solo proceso: contrato `check_update_single_flight` ejecutado a mano; marca probada en un repo y un worktree temporales (no ensucia `git status`); overlay check limpio. **Confirmado, sin corregir (→ F1-21d/e):** `_install_python_dependencies` puede volver sin error con dependencias base ausentes (tolerancia de upstream) y entonces se quita la marca y se da el recibo; entre la guarda y el bloqueo del hijo otro proceso puede tomar el bloqueo, y el código 2 que escribe el envoltorio bash se anuncia como fallo. **Hallazgo nuevo, sin corregir:** la instrucción de instalación por SSH (`settings.gateway.sshErrNotInstalled`, `electron/remote-lifecycle.ts:240`) manda a instalar Hermes desde la web de Nous; no se cambió el texto porque el modo SSH busca un ejecutable `hermes` en el host remoto y el instalador del fork solo crea `janitor`: **el modo de conexión remota por SSH no está verificado con Janitor**. Quedan unas veinte referencias a `nousresearch` en `apps/desktop/src` sin inventariar una a una |
| 2026-11-22 | Dueño del proyecto | **Punto cero** (decisión 2.9): no se adoptan instalaciones antiguas; se desinstalan y se empieza de cero con la app. F5-01 cancelada; F5-02 desbloqueada y ampliada. Las actualizaciones de la app nueva deben ser prácticas y sencillas, sin Git a la vista |
| 2026-11-22 | Claude (orquestador) | Equipo de desarrollo sano de nuevo. Suite debida, una corrida con registro guardado: `scripts/run_tests.sh tests/janitor/` → 39 archivos, 657 pruebas, 0 fallos (tras corregir un fallo propio: la comprobación `update-single-flight` no recibía su directorio temporal); `tests/gateway/test_update_command.py` + `test_update_streaming.py` → 24 pasan; `node --test apps/desktop-janitor/scripts/*.test.mjs` → 137/137; overlay check limpio. Las correcciones del flujo de actualización pasan a «código y pruebas»; siguen sin prueba propia la reanudación tras un corte y sin revisor distinto las del orquestador (Codex las revisó en solo lectura). Guarda de F1-22 reescrita para mandar a desinstalar; guía `docs/janitor/desinstalar-instalacion-antigua.md` escrita a partir de los instaladores antiguos, **sin ensayar en una máquina real** |
| 2026-11-22 | Subagentes Opus, auditado por el orquestador | F5-02 (retiro: 3 instaladores, 6 scripts de migración, migraciones v1/v2, alias raíz pre-1.0, 5 archivos de prueba; queda el mecanismo de `.layout_version` con base v2 y la guarda del instalador), F4-03 (n8n, NocoDB, LightRAG con motor común `janitor/skills/services/_shared/compose_service.py`; Firecrawl; Open Design), F4-04 y F4-05 (pantallas «Skills» y «Agentes» del plugin de escritorio; `catalog.set_selection`; creación de agentes en proceso hijo). Evidencia del orquestador, una corrida con registro: `scripts/run_tests.sh tests/janitor/` → 38 archivos, 640 pasan, **9 fallan, todas en `test_janitor_lightrag_skill.py`** (prueba de la skill antigua de LightRAG, pendiente de borrar); overlay check limpio; catálogo 42/42; `node --test apps/desktop-janitor/scripts/*.test.mjs` → 153/153; anclas 177/177. Error del orquestador corregido antes de terminar: un `git add -A` metió en el commit de F5-02 los enlaces de `.claude/worktrees/`; se enmendó el commit local y la carpeta quedó excluida en `.git/info/exclude` |
| 2026-11-22 | Subagente Opus (compilación y capturas), revisado por el orquestador | App recompilada (`build.mjs --linux --dir`, `apps/desktop` limpio después) y abierta sin pantalla con HOME temporal: «Servicios», «Skills» y «Agentes» se ven, en español, sin «Hermes», consola sin errores. Creado un especialista `prueba-inv` (Investigador): `memories/` vacío, `janitor.skills` de su plantilla; cambiada una skill en el principal y en el especialista, reflejado en cada `config.yaml`. Dos defectos vistos por el orquestador en las capturas y corregidos en `plugin.js` (comprobado repitiendo la captura): la barra de guardado de «Skills» era transparente y tapaba la última fila; la descripción de Firecrawl decía «totalmente local». Observación sin resolver: `janitor.catalog_seen` no incluye la skill recién activada |
| 2026-11-22 | Claude (orquestador), con autorización del dueño | Borrada `tests/janitor/test_janitor_lightrag_skill.py` (prueba de la skill antigua de LightRAG, leía el código como texto). `scripts/run_tests.sh tests/janitor/` → 37 archivos, 627 pruebas, 0 fallos |
| 2026-11-22 | Dueño del proyecto | Actualizaciones: **Git oculto**. Se mantiene el mecanismo actual (checkout + `janitor update`), sin Git a la vista del usuario. Se desbloquean F1-21a a F1-21e |
| 2026-11-22 | Subagentes Opus, auditado por el orquestador | Contrato de actualización: F1-21a (`janitor/desktop-compat.json`, parches `P13-compat-*`, función pura `decideDesktopCompat`), F1-21b (inventario `brand/inventory/nous-urls.tsv` de 38 referencias y vigilancia; **modo de conexión por SSH oculto**: busca `hermes` y `~/.hermes` en el host remoto, no puede funcionar con Janitor; bot de Telegram «Janitor»; `/topup` fuera de la paleta), F1-21c (`posix.sh` relanza `$APPIMAGE` validado como ruta absoluta a un ejecutable; textos de Linux y `ui.html` en español; touchpoint nuevo `desktop-update-ui`), F1-21d (salida de `janitor update` en español; comprobación de dependencias base con `importlib.metadata` en el intérprete destino; flota con código viejo → salida 1; aviso de contrato; pruebas de la reanudación). Evidencia del orquestador, una corrida con registro: `scripts/run_tests.sh tests/janitor/` → 39 archivos, 668 pruebas, 0 fallos; `tests/scripts/desktop_update/` + `tests/gateway/test_update_*.py` → 47 pasan, 9 omitidas, **2 fallan por diseño** (`test_desktop_update_shim_progress.py`: fijan los nombres de etapa en inglés; deseleccionadas en el job `upstream-sync-verify` de `tests.yml`); overlay check limpio; `node --test apps/desktop-janitor/scripts/*.test.mjs` → 195/195; anclas 186/186; `apps/desktop` intacto. Valores provisionales aplicados a dos decisiones abiertas: la app se reabre sola tras actualizar; el botón de descarga abre la página del release. Fuera de alcance, sin corregir: el motor sigue listando `/login` y `/topup` en la ayuda del terminal y de Telegram (`hermes_cli/commands.py`); textos en inglés en `pet-generate/generate-unavailable.tsx`, `settings/constants.ts:51` y `desktop-slash-commands.ts` |
| 2026-11-22 | Subagente Opus (compilación y comprobación sin pantalla), revisado por el orquestador | App recompilada con los 186 parches (`apps/desktop` limpio después). **A, arranque normal:** `[janitor-compat] app 1, engine 1: compatible`, el motor levanta. **B, app vieja:** con una raíz de motor de enlaces simbólicos y `contract: 2`, registro `app 1, engine 2: app_vieja`; el diálogo se llamó una vez con el texto y los botones esperados (capturado sustituyendo `dialog.showMessageBox` bajo `--inspect-brk`), la app se cierra sola y **el motor no se lanza** (sin proceso `janitor.cli serve`, sin `state.db`). Limitación: con el diálogo nativo real sin pantalla la app muere con SIGSEGV; hay que verlo en una sesión con escritorio. **C, SSH oculto:** solo «Gateway local» y «Gateway remoto» al elegir modo y al añadir conexión. **D:** `/topup` y `/login` fuera de la paleta; «Notas de la versión» → releases del fork. **Defectos vistos, sin corregir todavía (→ F1-19):** la paleta de comandos tiene encabezados en inglés («SESSION», «CONFIGURATION», «INFO», «TOOLS & SKILLS», «SKILLS», «COMMANDS»), sufijos «(usage: …)» y descripciones de skills en inglés; `/subscription` («plan de Nous») sigue visible; la fila «This device» y la cabecera de Conexiones guardadas, que aún nombra «SSH o Cloud» |
| 2026-11-22 | Subagente Opus, auditado por el orquestador | F1-19, defectos vistos en la app: parche `P14` (`brand/palette.mjs`) traduce encabezados de grupo y pistas de uso de la paleta; 28 descripciones de skills de upstream como filas del catálogo español; `/subscription`, `/upgrade` y `/debug` dejan de ofrecerse en el chat (`/debug` sube registros con texto de conversaciones a un servicio público sin pedir confirmación: decisión del subagente, reversible en una línea); «Este equipo» y cabecera de Conexiones sin SSH ni Cloud; las 14 skills de Janitor llevan su `description` en español (llega a TUI, Telegram y al índice del prompt; efecto en la elección de skill por el modelo **sin comprobar**). Vigilancia `palette.test.mjs` contra el registro real de comandos del motor (usa `python3`; en el job `desktop-overlay` de CI no está comprobado). Evidencia del orquestador: `scripts/run_tests.sh tests/janitor/` → 668 pruebas, 0 fallos; `node --test …/*.test.mjs` → 215/215; anclas 207/207; overlay limpio; app recompilada y capturada sin pantalla: encabezados «SESIÓN», «CONFIGURACIÓN», «INFORMACIÓN», «HERRAMIENTAS Y SKILLS», «(uso: …)», «Este equipo», consola sin errores |
| 2026-11-23 | Claude (orquestador), con autorización del dueño | Rama `janitor-app/fase-1` publicada en `origin` (`reck74/Janitor-Agent`), 54 commits sobre `main`, hasta `e4fd038431`. Antes de publicar: búsqueda de secretos y datos personales en lo añadido (solo valores de prueba). Sin PR y sin etiqueta: el workflow de release (`v*` o manual) no se ha lanzado. Arrancó `Janitor CI` por primera vez sobre esta rama |
| 2026-11-23 | Claude (orquestador) | **Primera ejecución de `Janitor CI`** (rama publicada, commit `b73b307`): pasan `python-tests`, `Janitor minimal-install smoke` (el job reescrito en F5-02), `react-tests` y `web-tests`. Fallan dos: (1) `desktop-overlay`, por un defecto del propio workflow: su comprobación `grep '^skip transpile'` también coincidía con los dos archivos que no son TypeScript y que `build.mjs --check` informa como omitidos por diseño; corregido para fallar solo si falta el transpilador. (2) `Janitor tests on windows-latest`: falla el paso de pruebas; **causa sin diagnosticar** (los registros del job exigen sesión en GitHub y `gh` no está autenticado en este equipo). macOS quedó cancelado al fallar Windows. La instalación real (F1-15) se lanzó y **no llegó a instalar**: la sesión se cortó con la app en «Esperando que elijas la configuración inicial»; el equipo se reinició y se perdieron los guiones de captura, que vivían en `/tmp` (memoria) |
| 2026-11-23 | Claude (orquestador) | Segunda ejecución de `Janitor CI` (`90f95d9`): pasan `python-tests`, la prueba de instalación mínima, `react-tests`, `web-tests`, **`desktop-overlay`** (ya corregido) y **macOS**. Falla solo Windows, 65 pruebas en 6 archivos; registro leído con `gh` desde el terminal del dueño. Causas y arreglo: `test_janitor_project_create.py` (34) y `test_janitor_services_plugin_api.py` (21) simulan git/npm y Docker con guiones POSIX en el `PATH` → marcados `linux_only` a nivel de archivo; `test_script_is_executable` de salud del sistema (bit de ejecución) → `linux_only`; `test_resolve_hermes_home` (7) solo fijaba `HOME` → fija también `USERPROFILE`; la vigilancia de idioma de `janitor update` tomaba por inglés una ruta con `\` → descarta rutas con cualquier separador; y **un defecto real**: `catalog._atomic_write` escribía `config.yaml` con CRLF en Windows, así que un segundo `apply` no era idéntico byte a byte → escribe siempre con `\n`. Evidencia local: `scripts/run_tests.sh tests/janitor/` → 668 pruebas, 0 fallos. Windows sigue sin soporte verificado: las dos suites marcadas no corren allí |
| 2026-11-23 | Claude (orquestador) | `Janitor CI` **en verde en todos los jobs** sobre la rama publicada (corrida 45285144598, commit `87e9a43`), incluido Windows tras las correcciones |
| 2026-11-23 | Subagente Opus (verificación), evidencias comprobadas por el orquestador en `/var/tmp/janitor-e2e/` | **F1-15, primera instalación real de punta a punta.** App compilada en local (`c8d95b0703`), HOME limpio en disco, sin variables `HERMES_*`. La app descargó `https://raw.githubusercontent.com/reck74/Janitor-Agent/c8d95b07…/scripts/install.sh` (HTTP 200), clonó `reck74/Janitor-Agent` y fijó `c8d95b0703`. Etapas: prerequisites 24,7 s (uv y CPython 3.11 gestionados), repository 356,7 s, venv, python-deps 16,4 s, node-deps 174,2 s (npm, Chromium de Playwright, browser-use, cua-driver), path, config; setup y gateway omitidas. **Del clic al backend listo: 9 min 39 s.** En disco (verificado por el orquestador): clon del fork en el commit fijado; `~/.local/bin/janitor` → `hermes-agent/venv/bin/janitor`; sin `hermes*` en `~/.local/bin`; semilla correcta (`config.yaml` con idioma, skin, plugin y 13 skills; `SOUL.md` de Janitor; skin; `.no-bundled-skills`; `.layout_version` 2); ningún RC de shell escrito; `janitor --version` → «THE JANITOR v0.21.5-janitor.1». Tamaño: `~/.janitor` 1,9 GB; cachés 1,8 GB. **Defectos (→ F1-26):** (a) a los ~3 min, aún clonando, la ventana pasó a «Janitor no pudo iniciarse — El servicio en segundo plano de Janitor no respondió a tiempo» (detalle «Timed out connecting to Hermes backend», `use-gateway-boot.ts:1315`), el instalador siguió por debajo y al terminar la pantalla no se recuperó: hubo que pulsar «Reintentar»; (b) se creó `<HOME>/.hermes` con un `SOUL.md` «You are Hermes Agent…»: lo provoca la sonda `canImportHermesCli` (`electron/main.ts:4963`), que importa `hermes_cli.config` sin `HERMES_HOME`; reproducido aparte; (c) se instaló `cua-driver` sin preguntar: `~/.cua-driver/.telemetry_id`, `~/.local/bin/cua-driver`, `~/.cursor/mcp.json`, `~/.agents/skills/cua-driver`, y un `cua-driver serve` huérfano al cerrar; (d) inglés: nombres de etapa («Prerequisites», «Repository»…), salida del instalador («☤ Hermes Agent Installer», «hermes command ready»), `janitor --version` («Up to date»), `services list` (descripción de Honcho y «running:»); (e) la comprobación de contrato corre antes de instalar y no se repite al terminar. Sin comprobar: elegir proveedor y chatear, abrir el TUI, fallos (sin red, interrupción, reparación), un AppImage publicado |
| 2026-11-23 | Subagentes Opus, auditado por el orquestador | F1-26. **App** (`brand/install-boot.mjs`, parches P15-P17 y `P13-compat-after-bootstrap`; 222 anclas): causa raíz de la pantalla de fallo falsa = defecto de upstream — `use-gateway-boot.ts` limita la conexión a 45 s contados desde que abre la ventana (saltó a los 46 s, no a los 3 min) y el cerrojo `bootFailed` ignora el progreso posterior; ahora no falla con una instalación en curso o esperando la elección, y un fallo mostrado se retira al evento `complete`. Las sondas del intérprete del motor llevan `HERMES_HOME` (4 de 12 invocaciones no lo pasaban). Etapas en español. **Instalador/CLI**: `SKIP_COMPUTER_USE=true` con `--with-computer-use`; banner, resumen y mensajes del recorrido de Linux mediante una tabla que redefine los ayudantes de upstream (2 líneas de upstream cambiadas); `janitor --version` (touchpoint `runtime-copy` ampliado a `hermes_cli/_startup_fast.py`) y `janitor services` en español. Candidatos a upstream: el plazo de arranque durante la instalación y la sonda sin home. Evidencia: `node --test …/*.test.mjs` → 243/243; overlay limpio; `scripts/run_tests.sh tests/janitor/` → 657 pasan, 0 fallan y **1 archivo muerto por SIGKILL externo** (`test_janitor_update_outcomes.py`, 33/33 en tres corridas a solas: es el problema del equipo de desarrollo; pista sin comprobar: `scripts/run_tests_parallel.py::_kill_tree` hace `os.killpg(…, SIGKILL)` al terminar cada archivo) |
| 2026-11-23 | Subagente Opus (verificación), evidencias comprobadas por el orquestador en `/var/tmp/janitor-e2e/` | **Instalación real repetida** con la app recompilada en `60434274ff`, dos corridas desde un home vacío (3a con cachés, 3b sin cachés: 3 min 15 s del clic al backend listo; ventana abierta 4 min 37 s, con 70 s de espera antes de pulsar). (a) sin «Janitor no pudo iniciarse» en ninguna captura ni en el texto, y la app pasa sola a la pantalla de proveedor; (b) sin `~/.hermes` tras instalar, tras el primer arranque y tras reabrir; (c) sin `cua-driver` ni `~/.cursor` ni `~/.agents`; fuera de `.janitor`, `.local`, `.config` y `.cache` solo existe `.pki` (Chromium de Electron); (d) etapas «Requisitos del sistema, Descarga de Janitor, Entorno de Python, Dependencias de Python, Herramientas del navegador, Comando janitor, Configuración y skills, Claves y ajustes, Servicio de mensajería, Finalizar»; banner «THE JANITOR · instalador»; `janitor --version` y `janitor services list` en español; (e) `[janitor-compat] app 1, engine 1: compatible` después de instalar y antes de `HERMES_BACKEND_READY`. `~/.janitor`: 1,5 GB. **Defecto nuevo → F1-27** (aviso de actualización falso contra `main`). Observaciones: el sello de la compilación dice `dirty: true` con el árbol limpio; la barra de progreso de Playwright llena la salida desplegada; la etapa de navegador sigue siendo la larga (144 s sin cachés) |
| 2026-11-23 | Claude (orquestador), a petición del dueño | PR abierto para integrar `janitor-app/fase-1` en `main`: `reck74/Janitor-Agent#91` (listo para revisión, sin fusionar). Su descripción lista lo verificado y lo que no. Integrarlo resuelve F1-27 |
| 2026-11-23 | Claude (orquestador) | **Cierre de sesión.** Sección 0 añadida con el estado, los siguientes pasos en orden, el método de verificación y los avisos del equipo. Eliminados los artefactos temporales de la sesión (homes y cachés de las instalaciones de prueba en `/var/tmp/janitor-e2e/`, registros de CI descargados, ejecuciones de `.bridge/`); se conservan en `/var/tmp/janitor-e2e/` los guiones (`scripts/`) y las capturas (`capturas/`, `capturas3/`), que no están en el repositorio y pueden desaparecer con una limpieza del sistema |
| 2026-11-24 | Claude (orquestador), a petición del dueño | Sección 0: «Qué sigue» reordenado por prioridad en cuatro bloques (A camino crítico, B operación cotidiana, C aplicativos, D sin dependencias). Cambios frente al orden anterior: las decisiones que afectan a lo publicado van antes de la primera etiqueta; F1-25 se junta con la sesión de F1-15 (misma clave); C y D corren en paralelo; F5-03 pasa a después de F1-21g. Solo documentación: ningún estado del tablero cambió. `recomendaciones-codex-para-claude.md` (ya contrastado el 2026-11-22) sigue sin commitear |
| 2026-11-24 | Claude (orquestador) | **PR #91 fusionado por el dueño**, revisado: commit de merge `50212e2832` (padres `8f7573c60e` y `d35689d7a4`); `git diff origin/main origin/janitor-app/fase-1` vacío, o sea que `main` es idéntico a la rama auditada y no se repitió la suite. Sobre ese árbol: `python -m janitor.overlay check` limpio (317 rutas, todas declaradas) y `python -m janitor.catalog check` 42/42. CI del commit de merge, leído de la API pública de GitHub: en verde `test`, `python-tests`, `Janitor minimal-install smoke`, `react-tests`, `web-tests`, `desktop-overlay` y Windows; **macOS seguía en cola** al consultar; `e2e` y `upstream-sync-verify` se saltaron (solo corren en sincronizaciones). F1-27 pasa a resuelto por integración, con la aceptación pendiente en F1-15 |
| 2026-11-24 | Claude (orquestador), decisiones del dueño | Tres decisiones registradas en la sección 2.10 y en `AGENTS.md` (directivas 8, 13 y 19): **canal del motor por versiones etiquetadas** (un merge a `main` no es una entrega; etiquetar lo ordena el dueño), **instalación base sin navegador** (Chromium y `browser-use` al primer uso) y **páginas incrustadas de Hermes ocultas** (catálogo de plugins y Skills Hub). Tareas nuevas F1-28, F1-29 y F1-30, las tres antes de la primera etiqueta; salen de la sección 9. Solo documentación: ningún código cambió, así que hoy el motor sigue `main`, la base instala el navegador y las páginas siguen visibles. Color de acento (F1-18) sin decidir: el dueño pidió ver la app; se le enviaron dos capturas de la instalación real del 2026-11-23 (`60434274ff`) |
| 2026-11-24 | Claude (orquestador), aprobado por el dueño | **F1-18: línea gráfica de la app.** Búsqueda en la historia: la app perdió su aspecto en `afdaa0d7a1` (2026-10-21), que devolvió `apps/desktop/` a upstream y solo llevó a la capa de construcción el icono y el fondo; el banner `janitor-logo-banner.png` se recuperó de `afdaa0d7a1^`. Cambio, solo en `apps/desktop-janitor/`: `brand/theme.mjs` (el preset usa `completion_menu_bg` como fondo y `ui_primary` como principal; parches `P12-look-banner-import` y `P12-look-banner` sobre `intro.tsx`), `scripts/build.mjs` (el banner como archivo copiado; `FORK_ONLY_TARGETS`) y el asset. Evidencia: `node apps/desktop-janitor/scripts/build.mjs --check` → 224/224; `node --test apps/desktop-janitor/scripts/*.test.mjs` → 243/243 tras reescribir dos pruebas que describían el aspecto anterior (tema = salida exacta del conversor; todo destino existe en upstream); `python -m janitor.overlay check` limpio; `build.mjs --linux --dir` compiló y dejó `apps/desktop/` sin cambios; app abierta sin pantalla con `HERMES_DESKTOP_HERMES_ROOT` y un home temporal, cinco capturas. Sin revisor distinto. Sin ver: chat con mensajes, diálogos, errores. Quedan dos decisiones nuevas en la sección 9 (nombre visible y frase bajo el banner) |
| 2026-11-24 | Claude (orquestador) | **F1-29 y F1-30.** F1-29: `SKIP_BROWSER=true` por defecto y `--with-browser` en `scripts/install.sh`, cuatro avisos traducidos, touchpoint actualizado, dos pruebas nuevas. F1-30: cuatro parches P18. Evidencia: `scripts/run_tests.sh tests/janitor/` → 39 archivos, 676 pasan, 0 fallan, y `test_janitor_backend_i18n.py` salió CRASHED (el SIGKILL externo ya conocido); a solas, 16/16. `node --test apps/desktop-janitor/scripts/*.test.mjs` → 243/243; `build.mjs --check` → 228/228; overlay check limpio; `build.mjs --linux --dir` compila y deja `apps/desktop/` sin cambios; app abierta sin pantalla, capturas de Capacidades. Sin revisor distinto. **F1-28 sin empezar**, con un hallazgo de lectura: el canal no es un solo punto. Siguen `main` por separado `janitor/update_core.py` (por defecto), la sonda del banner (`hermes_cli/banner.py::_check_via_local_git`, `"main"` fijo, por la API de GitHub), la app (`electron/main.ts`: `DEFAULT_UPDATE_BRANCH` y `resolveHealedBranch`, que vuelve a `main`) y el sello de compilación (el workflow pone `GITHUB_REF_NAME=main` en una etiqueta porque «a tag is not a branch the installer or the updater can track»). Además `_github_compare` consulta `nousresearch/hermes-agent` fijo para listar los cambios pendientes |
| 2026-11-24 | Dos subagentes Opus (alcances disjuntos), auditado por el orquestador | **F1-28: canal por versiones etiquetadas, con la rama `stable`** (commit `388eef255c`). El orquestador dejó la base en `janitor/release_channel.py` y `update_core.py`; un subagente hizo el motor (touchpoint `update-channel`, lanzador, plugin, pruebas) y otro la app (P19), el workflow y `install.sh`. Auditoría: diffs leídos y verificaciones repetidas por el orquestador con todo junto: `scripts/run_tests.sh tests/janitor/` → 39 archivos, 696 pasan, 0 fallan; `tests/hermes_cli/test_banner*.py` + `test_update_check.py` (upstream) → 13 pasan; `node --test apps/desktop-janitor/scripts/*.test.mjs` → 246/246; `build.mjs --check` → 235/235; overlay check y catalog check limpios; `build.mjs --linux --dir` compila, deja `apps/desktop/` sin cambios y la app arranca sin pantalla. El subagente del motor hizo una prueba de mutación (volver el valor por defecto a `main` hace fallar 6 pruebas). Pruebas nuevas con repos git reales: un merge a `main` no se anuncia; una versión publicada se anuncia y se instala; sin `stable` en origin el motor se queda como está. **No verificado:** el workflow (necesita una etiqueta) y todo lo que el estado de F1-28 lista como riesgo |
| 2026-11-24 | Claude (orquestador), a petición del dueño | PR abierto para integrar `janitor-app/plan-tras-merge` en `main`: `reck74/Janitor-Agent#92`, seis commits, fusionable según GitHub. Su descripción lista lo verificado y lo que no. El dueño inició sesión de `gh` para los agentes (`env -u GH_TOKEN gh auth login -s workflow`) |
| 2026-11-24 | Claude (orquestador) | **F1-21f.** `artifactName` sin versión; `janitor/release_channel.py` gana `expected_tag`, `check_tag` y el modo `--check-tag`; paso nuevo «Tag matches the version» en el job `appimage`, solo en etiquetas y antes de instalar dependencias. Evidencia: `python3 -m janitor.release_channel --check-tag v0.21.5-janitor.1` → 0, con `v0.21.5` → 1 y línea `::error::`; `scripts/run_tests.sh` sobre `test_janitor_release_channel.py` (nuevo, 2 pruebas), `test_janitor_update_core.py` y `test_janitor_overlay_contract.py` → 97 pasan; `node --test apps/desktop-janitor/scripts/build.test.mjs` → 0 fallos; YAML válido; overlay check limpio. **No verificado:** el workflow con una etiqueta real; que el runner tenga Python ≥ 3.11 (usa `tomllib`; `ubuntu-latest` lo trae hoy, el workflow no lo fija) |
| 2026-11-24 | Claude (orquestador), a petición del dueño | **PR #92 fusionado por el dueño** (merge `03533f09ff`). Revisado: el árbol de `main` es idéntico al de la rama (`8bcb24d8b1`). CI del PR: 15 checks en verde, 4 saltados, 1 cancelado («Janitor tests on macos-latest»: GitHub no asignó máquina macOS, el job no ejecutó ningún paso; igual en el commit anterior de `main`). **No verificado:** las pruebas en macOS sobre estos cambios; el CI de `main` tras la fusión seguía en curso al escribir esto. `stable` y la etiqueta `v0.21.5-janitor.1` no existen todavía |
| 2026-11-25 | Claude (orquestador), por orden del dueño | **Primera etiqueta `v0.21.5-janitor.1`**, creada sobre `main` (`28154d4d20`, tras fusionar #93). **El workflow de release falló** (run 45627112451) en «Build AppImage»: el paso «Tag matches the version» pasó y el AppImage llegó a empaquetarse, pero electron-builder intentó publicar por su cuenta («GitHub Personal Access Token is not set»). Causa: el workflow pasaba `--publish never` y `run-electron-builder.mjs` ya lo añade; repetido, llega como lista y `PublishManager` no lo lee como `never`. En los PR no se veía porque electron-builder nunca publica desde un pull request. Arreglo: quitar el flag del workflow. **Resultado:** no hay versión publicada, `stable` no existe y la etiqueta apunta a un commit cuyo workflow no puede publicar; qué hacer con ella lo decide el dueño. El job `release` (mover `stable`, adjuntar el AppImage) sigue **sin ejecutarse nunca**. Corrección de la entrada anterior: las pruebas en macOS sí corrieron en verde en `main` (`03533f09ff` y `28154d4d20`) |
| 2026-11-25 | Claude (orquestador), por orden del dueño | **Primera versión publicada.** Fusionado #94 (merge `7b3db40455`, por orden del dueño) y, por decisión suya, la etiqueta `v0.21.5-janitor.1` se borró y se recreó sobre ese commit (la anterior no había publicado nada). Corrida 45631111616 en verde en sus dos jobs: `appimage` (incluye «Verify AppImage and install stamp») y `release`. Comprobado después: `refs/heads/stable`, `refs/heads/main` y la etiqueta resuelven a `7b3db40455`; la versión «Janitor v0.21.5-janitor.1» no es borrador ni preliminar y lleva `Janitor-linux-x86_64.AppImage` (143 MB). El `GITHUB_TOKEN` pudo crear `stable` esta vez. **No verificado:** descargar e instalar ese AppImage en un equipo limpio; `janitor update` contra `stable` en una instalación real; que el token pueda mover `stable` cuando entre dos etiquetas cambien archivos de workflow (aquí `stable` se creó, no se movió) |
| 2026-11-25 | Claude (orquestador), evidencias en `/var/tmp/janitor-a4/` | **A4, parte sin pantalla ni clave: instalación real desde el AppImage publicado.** Descargado de la versión `v0.21.5-janitor.1`: SHA-256 `5abb8476…279aa`, igual al que publica GitHub; sello `install-stamp.json`: rama `stable`, commit `7b3db40455`, `source: ci`. App lanzada sin pantalla (Playwright) con HOME vacío `/var/tmp/janitor-a4/home` y sin motor local: «Instalar Janitor localmente» → pantalla de proveedor en 4 min 35 s (`capturas/install-timeline.log`). Resultado: motor en `~/.janitor/hermes-agent` en el commit `7b3db40455` (HEAD desacoplado, remoto el fork, rama `stable` presente), `.layout_version` 2, `.no-bundled-skills`, sin Chromium de Playwright (F1-29 confirmado en una instalación real), 1,1 GB. `janitor --version` → `THE JANITOR v0.21.5-janitor.1`; `janitor update --check` → «Ya tienes la última versión», salida 0; `janitor` abre el TUI con el banner J4NITOR-AGENT. **Hallazgo:** el número de versión del banner del TUI enlaza a `github.com/NousResearch/hermes-agent/releases/tag/v0.21.5-janitor.1`, que no existe (`hermes_cli/banner.py::_RELEASE_URL_BASE`); sin arreglar. **No verificado (necesita pantalla y una clave del dueño):** elegir proveedor y chatear, el aviso de app vieja, los fallos (sin red, corte a medias, reparación), la memoria con MiniMax, especialistas y skills recién activadas, y la primera navegación (descarga del navegador). Lanzadores para esa sesión: `/var/tmp/janitor-a4/abrir-janitor.sh` (app) y `tui-janitor.sh` (TUI), ambos sobre el home de prueba |
| 2026-11-25 | Claude (orquestador) con dos subagentes Opus de solo lectura; hechos clave contrastados en `state.db` | **A4, primer chat real (MiniMax): ante «hola», Janitor auditó el equipo sin que se lo pidieran y no respondió.** Sesión `20261125_111531_80fafd` del home de prueba: 1 `skill_view` (`janitor-system-health`) y 8 `terminal` en 3 min, todos los mensajes del asistente con `finish_reason=tool_calls`, hasta que el dueño lo detuvo. Nada mutó el sistema, pero servicios, procesos, puertos y montajes del equipo real salieron hacia el proveedor. Causa (razonamiento guardado del modelo): `SOUL.md` prohíbe saludar, exige cargar skills y declara libre la exploración, sin ninguna regla de «un saludo no es una tarea»; lo refuerzan el «Get to work» de la personalidad sembrada y la guía de ejecución de upstream para MiniMax (`agent/prompt_builder.py`). **Arreglo:** regla «SIN ORDEN NO HAY TRABAJO» en `assets/janitor/SOUL.md`, exploración libre solo «dentro de una tarea pedida», skills obligatorias solo «si pide una tarea», y «Wait for an order, then get to work» en la semilla. El tono no cambia (directiva #18). Pruebas: `scripts/run_tests.sh` sobre seed, install_sh, profile_templates y desktop_plugin_catalog, 70 pasan. **No verificado:** repetir el «hola» con el arreglo (aplicado a mano al home de prueba; lo hace el dueño). **Límites:** no llega a homes ya sembrados (la semilla no sobrescribe) y a los usuarios solo con otra etiqueta. **Hallazgos sin arreglar:** el aviso de aprobación devolvió «the attached client cannot answer approval requests (update the Hermes app)» (¿la app muestra las aprobaciones?; además dice «Hermes»); 22 s instalando `anthropic` y `boto3` antes de la primera respuesta con MiniMax; la sesión usó MiniMax-M3 aunque `config.yaml` dice M2.7; el lanzador de prueba heredó `GH_TOKEN` del terminal |
| 2026-11-25 | Claude (orquestador), por orden del dueño | Repetido el «hola» con el arreglo en el home de prueba (sesión `20261125_112654_b230a9`): respuesta en dos frases, 0 herramientas. **MiniMax-M3 pasa a ser el modelo por defecto** (semilla y skills de Honcho y LightRAG; orden del dueño). Abierta la **Fase 6** (Windows, macOS y Arch para el segundo release) con sus decisiones provisionales; rama de trabajo `janitor-app/release-2` |
| 2026-11-25 | Claude (orquestador) con subagentes Opus por tarea y una revisión de Codex (modelo solicitado `gpt-6.2-astra`) sobre los scripts de Windows; el dueño fuera, todo probado en GitHub Actions | **Fase 6 implementada en `janitor-app/release-2` (PR `reck74/Janitor-Agent#98`).** Corrida 45666821137 del workflow de release en verde en sus cinco builds: Linux (AppImage), Windows x64 (NSIS), macOS arm64 y macOS x64 (dmg, firma ad hoc) y paquete de Arch (makepkg en contenedor, namcap sin errores, `pacman -U`, comprobaciones y `pacman -R`). En cada sistema la app empaquetada arrancó y la prueba de arranque vio título «Janitor», `lang=es`, pantalla «Configurar Janitor» sin «Hermes» y versión `v0.21.5-janitor.1` (antes mostraba `0.17.6`, la de upstream; arreglado con P21 y `extraMetadata.version`). Capturas en los artefactos `janitor-smoke-*`. **Instalación real del motor** (`install-e2e`, corrida 45663622520): `install.ps1` bajo PowerShell 5.1 en windows-latest e `install.sh` en macos-latest, por etapas como la app, con `janitor --version`, `janitor update --check`, home sembrado, sin navegador e idempotencia: en verde en ambos. `tests/janitor/` en verde en los tres sistemas, incluidos los `windows_only` nuevos. La revisión de Codex encontró siete defectos en los scripts de Windows (podían tocar un Hermes ajeno, caer al actualizador de upstream, reiniciar gateways con `-NoGateway`, actualizar desde `main`, informar éxito con la siembra fallida); corregidos y cubiertos con pruebas. Versión subida a `0.21.5+janitor.2`: la etiqueta del release sería **`v0.21.5-janitor.2`**. **No verificado:** nada en un Windows ni un Mac reales (Gatekeeper, SmartScreen, notificaciones, el instalador NSIS visto por una persona); instalar el paquete de Arch en el equipo del dueño; chatear en Windows o macOS; una actualización real de `.1` a `.2`; el job `release` con cuatro sistemas; y que el token pueda mover `stable` (F6-12: este release cambia workflows). `macos-arm64` e `install-e2e (macos)` fueron cancelados una vez cada uno porque GitHub no asignó runner; pasaron en otra corrida. **Pendientes anotados:** `install.sh` no comprueba el `origin` de un checkout existente (en Windows sí); mensajes informativos de `install.ps1` en inglés en «Mostrar salida del instalador»; algunos errores poco frecuentes de Windows en inglés; iconos sin transparencia; copyright «Nous Research» en «Acerca de»; el enlace de versión del banner del TUI; ningún revisor distinto del ejecutor para la Fase 6 salvo Codex en los `.ps1` |
| 2026-11-25 | Claude (orquestador), por orden del dueño («Sí, publica») | **Segunda versión publicada, `v0.21.5-janitor.2`.** PR #98 fusionado con commit de merge (`6a0846d413`; árbol idéntico al de la rama, `59368529d9`); etiqueta anotada creada sobre ese commit tras `python -m janitor.release_channel --check-tag` (coincide). Workflow de release, corrida 45714931560: `prepare`, los cuatro `build` (linux, windows-x64, macos-arm64, macos-x64), `arch-package` y `release` en verde al primer intento; «Janitor CI» y «Tests» de `main` y de la etiqueta también en verde. Comprobado después: `main`, `stable` y la etiqueta apuntan a `6a0846d413`; el release no es borrador y lleva 7 archivos (`Janitor-linux-x86_64.AppImage`, `Janitor-win-x64.exe`, `Janitor-mac-arm64.dmg`, `Janitor-mac-x64.dmg`, `janitor-desktop-bin-0.21.5.janitor.2-1-x86_64.pkg.tar.zst`, su `.src.tar.gz` y `SHA256SUMS`). **F6-12 resuelto:** el `GITHUB_TOKEN` movió `stable`. **Actualización real `.1` → `.2`** en el home de prueba (`/var/tmp/janitor-a4/home`, motor en `7b3db404`): `janitor update --check` → «Hay una versión nueva (22 cambios)»; `janitor update --yes` → salida 0, «Actualización completa [stable @ 6a0846d4]», `janitor --version` → `THE JANITOR v0.21.5-janitor.2` (registro en `/var/tmp/janitor-a4/update-a-2.log`). Observado: antes de actualizar, `janitor --version` decía «Al día» mientras `update --check` ya veía la versión nueva (la sonda pasiva va con caché; sin investigar). **Sin verificar:** los artefactos descargados no se ejecutaron en un Windows ni un Mac real; el paquete de Arch no se instaló en el equipo del dueño; la actualización se hizo por terminal, no desde el botón de la app, y la app de prueba (AppImage de la `.1`) no se reinició. |
| 2026-11-25 | Claude (orquestador) con tres subagentes de solo lectura, a petición del dueño | **Propuesta: Janitor dirige a Claude Code y a Codex.** Investigado qué hay en el repo, el puente `claude_codex` y los dos programas (versiones 2.1.332 y 0.172.0 en este equipo; sin enviar ningún mensaje a un modelo). Opciones y recomendación en [`obreros-claude-codex.md`](obreros-claude-codex.md). **Nada implementado; pendiente de las decisiones del dueño.** Revisada después por Codex (`gpt-6.2-astra` solicitado): de acuerdo con la recomendación, cinco hallazgos contrastados e incorporados (sección 8 del documento). |

## 9. Decisiones pendientes del dueño

No bloquean el trabajo en curso; cada una tiene un valor provisional ya aplicado.

| Tema | Valor provisional | Qué decidir |
|---|---|---|
| `approvals.mode` en la semilla | `manual` (como antes) | Upstream pasó su valor por defecto a `smart`. Mantener `manual` o seguir a upstream |
| Nombre visible: «Janitor» o «J4NITOR-AGENT» | Conviven: la app y sus textos dicen «Janitor»; el banner de la bienvenida y el skin del terminal dicen «J4NITOR-AGENT» / «J4nitor Agent» | Cuál manda |
| Frase bajo el banner de la bienvenida | La de upstream traducida («Envía el problema…») | Si debe ser una frase del personaje (hoy las frases del personaje viven solo en el terminal, decisión 2.5) |
| Frases nuevas de «pensando» | No aplicadas | Diez frases propuestas sobre equipos, redes y seguridad (bitácora de F1-06); el dueño dijo que las frases del terminal se conservan |
| `.claude/agents/janitor-dev-boss-autonomous.md` | Sin tocar | Importa `OpenCodeOrchestrator`, que ya no existe. Borrarlo o reescribirlo |
| Release | `main` integrado; sin etiqueta ni AppImage publicado | Cuándo etiquetar la primera versión (`v…`) para que el workflow publique el AppImage |
| Prueba de memoria con MiniMax (F1-25) | Sin probar | Necesita una clave real; ningún agente introduce claves: la corre el dueño o indica cómo |
| `forget` de WAHA (F4-07) | Borra los resúmenes en vez de enviarlos a la papelera | Confirmar la excepción a la directiva 19 o pasar a papelera |
| Tras actualizar el motor desde la app (F1-21) | Aplicado provisionalmente: la app se reabre sola | Confirmar o volver a «la reabre el usuario» |
| Botón de descarga del AppImage nuevo (F1-21) | Aplicado provisionalmente: abre la página del release | Confirmar o descargar el archivo directamente |
| `/debug` en el chat de la app | Oculto (sube registros con texto de conversaciones a un servicio público sin confirmar); sigue en la terminal como `janitor debug share --local` | Confirmar o volver a ofrecerlo |
| Valor rescatable de skills retiradas | Nada rescatado | `janitor-config-audit` (diff de config frente a la semilla) puede servir para adoptar instalaciones viejas (F5-01) |
| Decisiones provisionales de la Fase 6 | Home `~/.janitor` también en Windows; Windows solo x64; macOS con firma ad hoc y Windows sin firmar (no hay certificados); se mantiene `hermes://`; paquete de Arch `janitor-desktop-bin` con comando `janitor-desktop` | Confirmarlas o cambiarlas antes de etiquetar `v0.21.5-janitor.2` |
| Copyright en «Acerca de» y en el `.exe` | Se conserva «Nous Research» como atribución a upstream | Mantenerlo, añadir Janitor o sustituirlo |
| Janitor dirige a Claude Code y a Codex (pedido el 2026-11-25) | Propuesta en [`obreros-claude-codex.md`](obreros-claude-codex.md): motor propio + comando + skill; nada implementado | Las siete decisiones de su sección 7 (nombre, suscripción o clave de API, agentes, directiva #19, escritura, topes, prioridad) |
