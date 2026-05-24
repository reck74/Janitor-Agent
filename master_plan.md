# Janitor Master Plan v5 — Minimal Installer + Optional Skills Architecture

## System Context

Estas actuando como OpenCode, ejecutando un Master Plan de Arquitectura disenado por el CTO.
El objetivo es mantener un fork parasitario (Janitor) sobre el repositorio de Hermes Agent.

**REGLA DE ORO DE ARQUITECTURA**: PROHIBIDO realizar buscar-y-reemplazo masivo de la palabra hermes. 
El paquete interno mantiene su nombre original para garantizar que  
funcione sin conflictos destructivos.

**ENTORNO**: WSL2 / Linux.
**TESTING**:  para Python,  para TypeScript (TUI). TDD es obligatorio.

---

## Nueva Arquitectura: Minimalista + Skills Expansibles

### Filosofia del Cambio

Janitor evoluciona de un instalador monolitico que desplegaba toda la infraestructura 
(Infisical + Honcho + Firecrawl + Playwright + AgentMemory) a un modelo minimalista donde:

1. **El primer arranque instala solo lo fundamental**: identidad, configuracion, skin, y memoria Honcho
2. **Todas las capacidades adicionales son skills opcionales**: se instalan post-primer-arranque via comandos de skill
3. **Cada update puede entregar nuevas skills**: el agente crece organicamente

### Contrato de Instalacion Minima

El instalador base (
[1m[38;2;194;239;78m
       ██╗ █████╗ ███╗   ██╗██╗████████╗██████╗ ██████╗  
       ██║██╔══██╗████╗  ██║██║╚══██╔══╝██╔══██╗██╔══██╗ 
       ██║███████║██╔██╗ ██║██║   ██║   ██║  ██║██████╔╝ 
 ██   ██║██╔══██║██║╚██╗██║██║   ██║   ██║  ██║██╔══██╗
 ╚█████╔╝██║  ██║██║ ╚████║██║   ██║   ██████╔╝██║  ██║
  ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝   ╚═╝   ╚═════╝ ╚═╝  ╚═╝
[0m
  [38;2;250;127;170m╔══════════════════════════════════════════════════════╗[0m
  [38;2;250;127;170m║[0m  [1m[38;2;229;231;235mTu agente cinico de auditoria y ciberseguridad[0m  [38;2;250;127;170m║[0m
  [38;2;250;127;170m╚══════════════════════════════════════════════════════╝[0m

  [38;2;121;98;140mScanning ports... analyzing artifact... hunting vulns.[0m

[38;2;106;95;193m--- Credenciales del Agente ---[0m

[38;2;255;178;135mOPENAI_API_KEY[0m — Sin esto no puedo razonar. Ni limpiar codigo basura.
[38;2;121;98;140m   Obtenla en: https://platform.openai.com/api-keys[0m) ahora termina con:
-  — variables de entorno
-  — configuracion del agente
-  — persona del agente
-  — tema visual
- Opcional: Honcho local (si el usuario elige modo local)

**NO incluye**: Infisical, Firecrawl, Playwright, AgentMemory, ni systemd full-stack.

### Jerarquia de Skills



---

## Directivas del Fork (Supreme Rules)

1. **ZERO-RENAMING POLICY**: Nunca hagas buscar-y-reemplazar de la palabra hermes en el core. El motor subyacente se mantiene intacto para garantizar que  funcione sin conflictos destructivos.
2. **CLI WRAPPER**: Las extensiones de Janitor heredan de HermesCLI en archivos separados (janitor_cli.py). No se modifica cli.py original.
3. **SKILLS AISLADOS**: Toda habilidad nueva debe ir exclusivamente bajo . Los skills del core Hermes nunca se tocan.
4. **TUI ISOLATION**: Los cambios visuales del TUI deben ser condicionados o inyectados via el sistema de skins (skin_engine.py) sin destruir la compatibilidad del protocolo JSON-RPC. No se hace hardcode en los componentes base del TUI.
5. **NAMING CONVENTION (BRANDING)**: Todo contenedor Docker, red, volumen, servicio de sistema o aplicacion de terceros que Janitor instale o configure DEBE llevar obligatoriamente el prefijo janitor- (ej. janitor-redis, janitor-network). Sin excepciones.
6. **merge-auditor**: Cada merge debe ser auditado contra estas directivas. Si un PR introduce hermes renombrado en archivos core, se rechaza automaticamente.
7. **tui-compilation**: Los cambios en el TUI requieren pasar  Y  (vitest) ANTES de hacer commit. El pipeline CI de Janitor ejecuta esta habilidad como gate obligatorio.
8. **MINIMALIST INSTALLER**: El instalador base NUNCA debe depender de Docker, Infisical, o servicios externos para funcionar. Honcho es la unica dependencia fundamental.
9. **SKILLS ARE OPTIONAL**: Todas las capacidades mas alla de Honcho son skills opt-in. El usuario las instala explicitamente post-primer-arranque.
10. **MIGRATION SUPPORT**: Cada reestructuracion importante debe incluir un script de migracion (scripts/migrate-*.sh) para usuarios existentes.

---

## Arquitectura de Componentes

### 1. Instalador Base (scripts/janitor-install.sh)

**Responsabilidad**: Crear un Janitor funcional con memoria Honcho configurada.

**Flujo**:
1. Pide OPENAI_API_KEY y MINIMAX_API_KEY
2. Ofrece 3 modos para Honcho:
   - Modo 1: Cloud (usuario provee HONCHO_API_KEY)
   - Modo 2: Local (despliega Honcho via Docker usando setup-honcho.sh)
   - Modo 3: Saltar (configurar memoria luego)
3. Genera ~/.janitor/.env, copia config.yaml, SOUL.md, skin
4. Inyecta HERMES_HOME en shell RC
5. Si modo 2, ejecuta setup-honcho.sh
6. Muestra lista de skills opcionales disponibles

### 2. Honcho Setup (scripts/setup-honcho.sh)

**Responsabilidad**: Desplegar SOLO Honcho + Postgres + Redis.

**NO incluye**: Infisical, Firecrawl, Playwright, AgentMemory, systemd full-stack.

### 3. Stack Legacy (scripts/setup-stack.sh)

**Estado**: Marcado como LEGACY con aviso de deprecacion.
**Uso**: Solo para compatibilidad con instalaciones existentes. No llamado por el instalador base.

### 4. Runtime Wrapper (janitor_cli.py)

**Responsabilidad**: 
- Fijar HERMES_HOME=~/.janitor
- Cargar ~/.janitor/.env
- Leer ~/.janitor/SOUL.md como fuente canonica de persona
- Usar DEFAULT_CONFIG.setdefault (no override forzado)
- Fail-safe OWASP para Honcho

**NO hace**: Carga automatica de Infisical, hardcode de soul, override de config.

### 5. Skills Opcionales

Cada skill es un paquete autonomo bajo skills/janitor-<name>/:

- SKILL.md — metadata, descripcion, instrucciones
- scripts/ — scripts de despliegue/instalacion
- Compose files (si aplica) — solo para ese servicio

**Skills disponibles**:
- janitor-vault: Infisical + scripts de bootstrap
- janitor-firecrawl: Firecrawl local + pg_cron patch
- janitor-browser: Playwright + Chromium
- janitor-agentmemory: AgentMemory via npm
- janitor-honcho: Honcho local (si se salto en instalacion)

### 6. Orientacion (skills/janitor-onboarding/)

**Nuevo rol**: Guia/selector de capacidades. NO despliega infraestructura.
- Lista skills disponibles
- Proporciona comandos de instalacion
- Troubleshooting basico

---

## Flujo de Trabajo del Usuario

### Instalacion Fresca

Descargando e instalando el motor de Janitor...
→ Checking Docker Daemon...
[1;33mSe requieren permisos de administrador para validar Docker...[0m
[0;31mAutenticación fallida.[0m
























╭──────────── THE JANITOR v0.14.0 (2026.5.16) · upstream a50db46d ─────────────╮
│                                     Available Tools                          │
│                  ⢀⣤⣶⣶⣤⡀             browser: browser_back, browser_click,    │
│                  ⣿⣿⣿⣿⣿⣿             ...                                      │
│                  ⠙▀⠿⠿▀⠋             browser-cdp: browser_cdp,                │
│                  🛠 ── 🔥            browser_dialog                           │
│           incinerating bugs         clarify: clarify                         │
│                                     code_execution: execute_code             │
│  MiniMax-M2.7-highspeed · by Reck!  computer_use: computer_use               │
│      /home/reck/Janitor-Agent       cronjob: cronjob                         │
│   Session: 20260524_150048_83b7f3   delegation: delegate_task                │
│                                     discord: discord                         │
│                                     (and 27 more toolsets...)                │
│                                                                              │
│                                     MCP Servers                              │
│                                     minimax_docs (http) — 4 tool(s)          │
│                                     minimax (stdio) — 6 tool(s)              │
│                                     deepwiki (http) — 7 tool(s)              │
│                                     context7 (http) — 2 tool(s)              │
│                                     playwright (stdio) — 23 tool(s)          │
│                                     codebase-memory (stdio) — 14 tool(s)     │
│                                                                              │
│                                     Available Skills                         │
│                                     autonomous-ai-agents: claude-code,       │
│                                     codex, hermes-agent, opencode            │
│                                     creative: architecture-diagram,          │
│                                     ascii-art, ascii-video, b...             │
│                                     data-science:                            │
│                                     government-data-dashboards,              │
│                                     jupyter-live-kernel                      │
│                                     devops: kanban-orchestrator,             │
│                                     kanban-worker, webhook-sub...            │
│                                     email: himalaya                          │
│                                     gaming: minecraft-modpack-server,        │
│                                     pokemon-player                           │
│                                     general: dogfood, janitor-core,          │
│                                     janitor-onboarding, yuanbao              │
│                                     github: codebase-inspection,             │
│                                     github-auth, github-code-r...            │
│                                     janitor-core: janitor-config-review      │
│                                     mcp: codebase-memory, context7,          │
│                                     native-mcp, playwright                   │
│                                     media: gif-search, heartmula,            │
│                                     minimax-music-generation...              │
│                                     mlops: audiocraft-audio-generation,      │
│                                     dspy, evaluating-l...                    │
│                                     note-taking: obsidian                    │
│                                     productivity: airtable,                  │
│                                     google-workspace, linear, maps,          │
│                                     nano-...                                 │
│                                     red-teaming: godmode                     │
│                                     research: arxiv, blogwatcher, llm-wiki,  │
│                                     polymarket, resea...                     │
│                                     smart-home: openhue                      │
│                                     social-media: xurl                       │
│                                     software-development:                    │
│                                     debugging-hermes-tui-commands,           │
│                                     hermes-agent-ski...                      │
│                                                                              │
│                                     88 tools · 93 skills · 6 MCP servers ·   │
│                                     /help for commands                       │
│                                     ⚠ 6 commits behind — run hermes update   │
│                                     to update                                │
╰──────────────────────────────────────────────────────────────────────────────╯

System online. Code breaks. I incinerate it. Terminal active.
✦ Tip: SSRF protection blocks private networks, loopback, link-local, and cloud 
metadata addresses.


Garbage collected. Shutting down.

### Expansion Post-Instalacion

[0;36m→[0m Installing Playwright browser automation...
[0;33m⚠[0m Playwright install had issues — continuing anyway.
[0;36m→[0m You can retry later with: uv run playwright install --with-deps chromium
[0;36m→[0m Installing AgentMemory via npm...
npm warn ERESOLVE overriding peer dependency
npm warn While resolving: @anthropic-ai/claude-agent-sdk@0.3.150
npm warn Found: @anthropic-ai/sdk@0.39.0
npm warn node_modules/@agentmemory/agentmemory/node_modules/@anthropic-ai/sdk
npm warn   @anthropic-ai/sdk@"^0.39.0" from @agentmemory/agentmemory@0.9.21
npm warn   node_modules/@agentmemory/agentmemory
npm warn     @agentmemory/agentmemory@"*" from the root project
npm warn
npm warn Could not resolve dependency:
npm warn peer @anthropic-ai/sdk@">=0.93.0" from @anthropic-ai/claude-agent-sdk@0.3.150
npm warn node_modules/@agentmemory/agentmemory/node_modules/@anthropic-ai/claude-agent-sdk
npm warn   @anthropic-ai/claude-agent-sdk@"^0.3.142" from @agentmemory/agentmemory@0.9.21
npm warn   node_modules/@agentmemory/agentmemory
npm warn
npm warn Conflicting peer dependency: @anthropic-ai/sdk@0.98.0
npm warn node_modules/@anthropic-ai/sdk
npm warn   peer @anthropic-ai/sdk@">=0.93.0" from @anthropic-ai/claude-agent-sdk@0.3.150
npm warn   node_modules/@agentmemory/agentmemory/node_modules/@anthropic-ai/claude-agent-sdk
npm warn     @anthropic-ai/claude-agent-sdk@"^0.3.142" from @agentmemory/agentmemory@0.9.21
npm warn     node_modules/@agentmemory/agentmemory
npm warn deprecated prebuild-install@7.1.3: No longer maintained. Please contact the author of the relevant native addon; alternatives are available.
npm warn deprecated node-domexception@1.0.0: Use your platform's native DOMException instead

changed 254 packages in 57s

55 packages are looking for funding
  run `npm fund` for details
[0;32m✓[0m AgentMemory npm package installed
[0;32m✓[0m Service file written to /home/reck/.config/systemd/user/janitor-agentmemory.service
[0;32m✓[0m janitor-agentmemory.service enabled

### Migracion desde Modelo Antiguo

[1m═══ Janitor Migration: Full Stack → Minimal ═══[0m

[0;36m→[0m This script migrates your Janitor installation from the old
[0;36m→[0m full-stack model to the new minimal model.

[0;33m⚠[0m It will NOT delete Docker volumes or secrets.

---

## Fases de Implementacion (Actualizadas)

### Fase 1: Configuracion del Wrapper CLI Janitor
- [x] Crear janitor_cli.py con herencia de HermesCLI
- [x] Fijar HERMES_HOME=~/.janitor
- [x] Integrar carga de ~/.janitor/SOUL.md
- [x] Remover carga automatica de Infisical
- [x] Usar DEFAULT_CONFIG.setdefault en lugar de override forzado
- [x] Agregar fail-safe OWASP para Honcho

### Fase 2: Instalador Minimalista
- [x] Crear scripts/janitor-install.sh v5
- [x] Separar Honcho (remoto/local/skip)
- [x] Remover Infisical/Firecrawl del flujo base
- [x] Inyectar config.yaml, SOUL.md, skin
- [x] Crear scripts/setup-honcho.sh (solo Honcho)
- [x] Marcar scripts/setup-stack.sh como legacy

### Fase 3: Aislamiento del TUI
- [x] Personalizacion via skin engine (sentry-janitor)
- [x] No hardcode en componentes base
- [x] Gate npm run build + npm test en CI

### Fase 4: Configuracion Nativa de Honcho
- [x] Fail-safe si memory.provider=honcho pero no hay credenciales
- [x] Tres modos: cloud key, local docker, skip

### Fase 5: Extraccion de Skills
- [x] Crear skills/janitor-honcho/ con compose y SKILL.md
- [x] Crear skills/janitor-vault/ (migrar Infisical scripts)
- [x] Crear skills/janitor-firecrawl/ (migrar Firecrawl compose)
- [x] Crear skills/janitor-browser/ (migrar Playwright install)
- [x] Crear skills/janitor-agentmemory/ (migrar AgentMemory deploy)
- [x] Convertir skills/janitor-onboarding/ en guia/orientacion

### Fase 6: Documentacion y Migracion
- [x] Crear docs/RESTRUCTURE_v5.md
- [x] Crear scripts/migrate-janitor-minimal.sh
- [x] Actualizar master_plan.md (este archivo)
- [ ] Actualizar AGENTS.md con nuevas directivas

---

## Protocolo de Fallback y Anti-Bucle

Si en cualquier punto de implementacion se experimentan 3 fallos consecutivos:
1. DETENER LA EJECUCION INMEDIATAMENTE.
2. Revertir archivos en conflicto con git checkout -- <archivo>.
3. Documentar TODO detallado en el codigo.
4. Invocar al auditor: @merge-auditor por favor revisa por que la extension esta fallando.

---

## CI y Seguridad Local

Antes de marcar cualquier fase como completada:
- Ejecutar bash -n en todos los scripts bash nuevos/modificados
- Ejecutar python3 -m py_compile en archivos Python modificados
- Verificar que janitor arranca sin errores de importacion
- Confirmar que no hay referencias a hermes renombrado en archivos core
- Validar que skills nuevos siguen el formato SKILL.md correcto

---

## Estado Actual

**Commit**: 794685ef5 — restructure: minimal installer + optional skills model
**Fecha**: 2026-05-24

La reestructuracion v5 esta completa y operativa en main.
