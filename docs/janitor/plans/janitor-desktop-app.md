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
- Opcional: proveedor `holographic` (SQLite local, sin tope de tamaño).
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
| Firecrawl | Búsqueda web totalmente local (Hermes ya busca sin clave) |
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
- **Consecuencia:** la compilación Janitor actual, en una máquina limpia, instala
  Hermes puro en `~/.hermes` y crea el comando `hermes`.
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

## 5. Tablero de tareas

Estados: `pendiente` · `en curso (quién)` · `hecho` (lo dice quien lo ejecutó) ·
`auditado` (lo confirmó un revisor distinto corriendo las pruebas).

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
| F1-01 | Siembra `janitor/seed.py` + semilla mínima + lanzador apto para la app | `janitor/seed.py`, `janitor/cli.py`, `janitor/home.py`, `assets/janitor/config.yaml`, `tests/janitor/` | `scripts/run_tests.sh tests/janitor/` | auditado |
| F1-02 | `scripts/install.sh` como touchpoint: repo del fork, comando `janitor`, sin skills heredadas | `scripts/install.sh`, `janitor/overlay.yaml`, `tests/janitor/` | `python -m janitor.overlay check` + pruebas | auditado |
| F1-03 | Motor de parches de la capa de construcción (anclas, aplicar, revertir a prueba de fallos) + P1-P5 | `apps/desktop-janitor/` | pruebas node de `apps/desktop-janitor/` | auditado |
| F1-04 | Reglas de marca del catálogo (P6) + prueba de vigilancia | `apps/desktop-janitor/` | prueba de vigilancia en verde | auditado |
| F1-05 | Literales de Electron y de la interfaz (P7, P8) | `apps/desktop-janitor/` | prueba de anclas + vigilancia | auditado |
| F1-06 | `SOUL.md` y bienvenida de Telegram: de código a tecnología | `assets/janitor/SOUL.md`, `janitor/plugin/telegram.py`, su prueba | `scripts/run_tests.sh tests/janitor/` | auditado |
| F1-07 | Compilación real de la app Janitor y prueba en home limpio | — | AppImage arranca, instala y abre chat | compilación y arranque auditados; **instalación real en home limpio sin probar** (requiere push) |
| F1-08 | Onboarding: MiniMax primero, Nous y «Hermes Cloud» ocultos | `apps/desktop-janitor/` | revisión visual | auditado (primera pantalla comprobada en compilación real; resto de pantallas sin revisar) |
| F1-09 | Actualización desde la app por el flujo Janitor (directiva 13) | por definir | por definir | auditado |
| F1-10 | Español para plugins `kanban`, `hermes-bots`, `radio` y las 6 claves sin traducir | `apps/desktop-janitor/` | vigilancia de idioma | auditado por pruebas; sin revisar en pantalla |
| F1-11 | CI: compilar la app Janitor y publicar el AppImage | `.github/workflows/` | job en verde | auditado (los workflows no se han ejecutado) |
| F1-12 | `janitor update` lanzado desde la app: reiniciar gateways en ejecución y reconstruir `web/`, como hace el flujo de upstream | `janitor/update_core.py`, pruebas | prueba de comportamiento | pendiente |
| F1-13 | La primera pantalla sale con tema claro: aplicar los colores del skin desde el arranque | `apps/desktop-janitor/` | captura de la primera pantalla | pendiente |
| F1-14 | Mensajes del motor que llegan a la app en inglés o con «Hermes» (errores de credenciales, «run `hermes setup`») | por definir | captura | pendiente |
| F1-15 | Instalación real de punta a punta en un home limpio con el AppImage publicado | — | checklist del criterio de terminado | pendiente (bloqueado: requiere push y release) |

### Fase 2 — Agente principal y catálogo de skills

Diseño, alcances y verificaciones: [`fase-2-diseno.md`](fase-2-diseno.md).

| ID | Tarea | Estado |
|---|---|---|
| F2-01 | Perfil principal con su lista de skills | auditado |
| F2-02 | Catálogo por propósito | auditado |
| F2-03 | Plantillas Investigador y Creador de proyectos | auditado |
| F2-04 | Retiro de `agents.py`, `opencode/` y skills obsoletas | auditado |
| F2-05 | `janitor-onboarding` reescrita | auditado |

### Fase 3 — Skills nuevas del equipo (Linux)

| ID | Tarea | Estado |
|---|---|---|
| F3-01 | Limpieza del equipo | en curso (subagente Opus) |
| F3-02 | Organización de archivos | en curso (subagente Opus) |
| F3-03 | Salud del sistema | auditado |
| F3-04 | Mantenimiento programado | auditado |
| F3-05 | Creación de proyectos | pendiente |

### Fase 4 — Aplicativos opcionales

| ID | Tarea | Estado |
|---|---|---|
| F4-01 | Skill guiada de Honcho | pendiente |
| F4-02 | Plugin de escritorio: pantalla de servicios | pendiente |
| F4-03 | Mismo patrón para n8n, LightRAG, NocoDB, WAHA, Firecrawl, Open Design | pendiente |

### Fase 5 — Migración y limpieza

| ID | Tarea | Estado |
|---|---|---|
| F5-01 | Adopción de un `~/.janitor` existente (`janitor-core`) con respaldo | pendiente |
| F5-02 | Retiro de `bootstrap.sh`, `janitor-install.sh`, `setup-honcho.sh` | pendiente |
| F5-03 | Revisar si `janitor/update_core.py` se puede reducir | pendiente |

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
- La capa de construcción modifica `apps/desktop/` mientras compila. Si el proceso
  muere antes de revertir, el árbol queda sucio; `python -m janitor.overlay check` lo detecta.
- El lanzador fuerza `HERMES_HOME=~/.janitor`. Falta confirmar que no rompe el
  manejo de perfiles de la app (`--profile`).
- La marca en textos que envía el motor (errores, descripciones de comandos) no la
  cubre la capa de construcción.
- No está verificado que MiniMax llame de forma fiable a la herramienta `memory`.
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
