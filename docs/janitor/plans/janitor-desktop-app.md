# Plan: Janitor como aplicativo de escritorio

> **Fuente de verdad del replanteo.** Todo agente (Claude, Codex u otro) lee este
> archivo antes de tocar el repo y actualiza el [tablero](#5-tablero-de-tareas) al
> terminar una tarea. Las reglas vigentes están en `AGENTS.md` (directivas 1-20).
> Decisiones acordadas con el dueño del proyecto el 2026-11-22; no se reabren sin él.

Índice: [1 Objetivo](#1-objetivo) · [2 Decisiones de producto](#2-decisiones-de-producto) ·
[3 Hechos verificados](#3-hechos-verificados-en-el-código) · [4 Diseño técnico](#4-diseño-técnico) ·
[5 Tablero](#5-tablero-de-tareas) · [6 Protocolo entre agentes](#6-protocolo-de-trabajo-entre-agentes) ·
[7 Riesgos](#7-riesgos-y-puntos-sin-verificar) · [8 Bitácora](#8-bitácora)

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
- No se reutiliza `~/.janitor/janitor-core` en la fase 1. La app instala su propia
  copia en `hermes-agent/`; la adopción de instalaciones viejas es la fase 5.
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
  nuevo. Es una adopción parcial sin diseñar. Decidido: una guarda lo impide (F1-22)
  y la adopción completa (F5-01) se hace después de la primera instalación real.
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
| F1-11 | CI: compilar la app Janitor y publicar el AppImage | `.github/workflows/` | job en verde | auditado: solo código (los workflows no se han ejecutado; el job en verde que pide la verificación no existe aún) → F1-15 |
| F1-12 | `janitor update` lanzado desde la app: reiniciar gateways en ejecución y reconstruir `web/`, como hace el flujo de upstream | `janitor/update_core.py`, pruebas | prueba de comportamiento | auditado: código y pruebas; aceptación pendiente (sin actualización ni reinicio reales) → F1-21 |
| F1-13 | La primera pantalla sale con tema claro: aplicar los colores del skin desde el arranque | `apps/desktop-janitor/` | captura de la primera pantalla | auditado: código, pruebas y aceptación (captura de la compilación real) |
| F1-14 | Mensajes del motor que llegan a la app en inglés o con «Hermes» (errores de credenciales, «run `hermes setup`») | por definir | captura | auditado: código y pruebas; aceptación parcial (un mensaje real generado; el resto en F1-19) |
| F1-15 | Instalación real de punta a punta en un home limpio con el AppImage publicado | — | checklist de abajo | pendiente (bloqueado: requiere push y release, decisión del dueño) |
| F1-16 | Un gateway arrancado como servicio (sin pasar por el lanzador) no ve el catálogo español de Janitor: que el plugin exporte `HERMES_BUNDLED_LOCALES` al registrarse | `janitor/plugin/__init__.py`, `janitor/locales/`, pruebas | prueba de comportamiento | auditado: código y pruebas; aceptación pendiente (bot real) → F1-23 |
| F1-17 | Los gateways lanzados como `janitor gateway run` / `-m janitor.cli gateway run` no los reconoce el descubrimiento de upstream (`looks_like_gateway_command_line`), así que ninguna actualización los reinicia | `gateway/status.py` (touchpoint) o lanzar siempre por `hermes_cli.main` | prueba de comportamiento | auditado: código y pruebas (sin tocar `gateway/status.py`: el lanzador hace exec al comando canónico); aceptación pendiente (reinicio real) → F1-21 |
| F1-18 | El verde lima del skin no llega a la app: el conversor de upstream nunca lee `ui_primary`; el color de marca en la app queda en morado | `apps/desktop-janitor/` | captura | pendiente — **decisión del dueño** |
| F1-19 | Textos del motor aún en inglés o con «Hermes»: aviso de canal principal de Telegram, descripciones de comandos en `/help`, errores RPC crudos, routers web, `setup`/`doctor`, avisos finales de `scripts/desktop-update/posix.sh` («Backend updated, but…», «Reopen Hermes…») y errores del emparejamiento de Telegram (`hermes_cli/web_server_messaging.py`) | por definir (ver informe de F1-14 en la bitácora) | vigilancia + recorrido visual de F1-15 | pendiente |
| F1-20 | `/update` enviado desde Telegram ejecuta `python -m hermes_cli.main update --gateway`: el flujo de upstream, no `janitor update` (directiva 13) | `gateway/run.py::_resolve_hermes_bin` (touchpoint) o parche del lanzador | prueba de comportamiento | pendiente |
| F1-21 | Contrato único de actualización (sección 4.5): origen de releases, compatibilidad app–motor–plugin, cómo llega el AppImage nuevo, bloqueo compartido, interrupción y recuperación, resultado visible en español; cubre app, TUI y Telegram. Reúne la aceptación de F1-09, F1-12, F1-17 y F1-20 | por definir. **Decidido:** el AppImage nuevo llega por descarga guiada desde los releases del fork, con aviso en español; sin actualización automática | actualización real de una versión publicada a la siguiente, con un gateway en marcha | pendiente |
| F1-22 | Guarda de instalación existente: si el home tiene `janitor-core`, la app y `install.sh` se detienen con un aviso en español y no instalan un segundo motor ni reapuntan `janitor`, hasta que exista F5-01 | `janitor/seed.py`, `scripts/install.sh` (touchpoint), `apps/desktop-janitor/`, pruebas | prueba de comportamiento con un home temporal que imita la instalación antigua; el home queda intacto | pendiente. **Decidido:** guarda ahora; la adopción completa (F5-01) después de la primera instalación real |
| F1-23 | Telegram desde la app: probar el QR con un bot real (autorización, caducidad, reintento, servicio caído), nombre con que nace el bot, `/start` y avatar; la ruta de pegar un token siempre visible | por definir | recorrido con un bot real | pendiente. **Decidido:** se mantiene el QR con la ruta por token siempre visible; se revisa si el bot nace con marca Hermes o el servicio no es fiable |
| F1-24 | Operación cotidiana (sección 4.5): al configurar Telegram la app ofrece instalar el gateway como servicio (el usuario confirma; nunca se instala solo); cerrar ventana, Salir, inicio de sesión, reinicio, app y TUI a la vez, sin gateways duplicados; entrada en el menú de aplicaciones, diagnóstico, reparación y desinstalación conservando datos | por definir | recorrido en la instalación de F1-15 | pendiente. **Decidido:** ofrecer el gateway como servicio al configurar Telegram |
| F1-25 | Memoria integrada con MiniMax, en casos observables: guardar una preferencia, recuperarla tras reiniciar, corregirla, y que otro perfil no la vea; qué pasa con lo guardado al cambiar de proveedor de memoria | — | los cuatro casos, con evidencia | pendiente (necesita una clave real: la introduce el dueño) |

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
| F4-03 | Mismo patrón para n8n, LightRAG, NocoDB, Firecrawl, Open Design (WAHA pasa a F4-07). Ningún `deploy.sh` depende de los scripts que retira F5-02 | pendiente |
| F4-04 | Activar desde la app una skill del catálogo en un perfil (hoy los aplicativos no están en ninguna plantilla y «Instalar con Janitor» pasa la ruta del SKILL.md en la petición). Aceptación: elegir, quitar y actualizar skills desde la app; el perfil solo ve las elegidas; una skill nueva de upstream no se activa sola; el cambio aplica desde la sesión siguiente (no rompe la caché de una conversación abierta); alternancia A→B→A | pendiente |
| F4-05 | Plantillas de agente desde la app (el diálogo de crear perfil de upstream clona la memoria). Aceptación: el especialista nace con memoria vacía, su `SOUL.md` y sus skills; sin contaminación de memoria, skills ni credenciales entre perfiles | pendiente |
| F4-06 | La pantalla Servicios distingue «contenedor en marcha» de «el servicio responde»: comprobación contra la `url` del `service.yaml` antes de anunciarlo listo; progreso, cancelación y fallo visibles | pendiente |
| F4-07 | WAHA con su contrato (decisión 2.4): la skill actual es la antigua, en inglés y con operaciones de envío. Solo lectura por defecto; enviar únicamente por orden directa del usuario en la conversación, nunca por el contenido de un mensaje recibido; selección de conversaciones, ventana de historial y conservación de resultados; aviso de que las conversaciones viajan al proveedor de IA | pendiente |

### Fase 5 — Migración y limpieza

| ID | Tarea | Estado |
|---|---|---|
| F5-01 | Adopción de un `~/.janitor` existente (`janitor-core`) con respaldo. **Requisito previo a entregar la app a un usuario existente** (hasta entonces, F1-22). Define: convivencia o sustitución de los dos motores, comando y entorno resultantes, conservación de configuración, credenciales, memoria, sesiones y perfiles, respaldo consistente de SQLite con recorrido de restauración probado, qué preferencias de ventana se reinician al pasar a `~/.config/Janitor`, y qué se hace con el paquete de skills de Hermes si el home antiguo lo tiene copiado (sin verificar). Límites de la directiva 10 | pendiente |
| F5-02 | Retiro de `bootstrap.sh`, `janitor-install.sh`, `setup-honcho.sh`. Antes: comprobar que nada los ejecuta (hoy solo los mencionan comentarios de `deploy.sh` de Firecrawl y WAHA, y `janitor/seed.py` / `update_core.py` por compatibilidad) | pendiente |
| F5-03 | Revisar si `janitor/update_core.py` se puede reducir. No antes de F1-21: primero se fija qué responsabilidades se conservan y dónde | pendiente |

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

## 9. Decisiones pendientes del dueño

No bloquean el trabajo en curso; cada una tiene un valor provisional ya aplicado.

| Tema | Valor provisional | Qué decidir |
|---|---|---|
| `approvals.mode` en la semilla | `manual` (como antes) | Upstream pasó su valor por defecto a `smart`. Mantener `manual` o seguir a upstream |
| Verde lima en la app (F1-18) | La app usa el morado del skin | Si el lima `#c2ef4e` debe ser el color de acento de la app |
| Frases nuevas de «pensando» | No aplicadas | Diez frases propuestas sobre equipos, redes y seguridad (bitácora de F1-06); el dueño dijo que las frases del terminal se conservan |
| `.claude/agents/janitor-dev-boss-autonomous.md` | Sin tocar | Importa `OpenCodeOrchestrator`, que ya no existe. Borrarlo o reescribirlo |
| Push y release | Nada publicado | La instalación real de punta a punta (F1-15) necesita la rama en GitHub y un AppImage publicado |
| Prueba de memoria con MiniMax (F1-25) | Sin probar | Necesita una clave real; ningún agente introduce claves: la corre el dueño o indica cómo |
| Valor rescatable de skills retiradas | Nada rescatado | `janitor-config-audit` (diff de config frente a la semilla) puede servir para adoptar instalaciones viejas (F5-01) |
