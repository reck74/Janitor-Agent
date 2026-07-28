# Janitor-Agent Project Documentation

## Overview

**Janitor-Agent** es un agente DevSecOps orquestador construido como un fork/wrapper alrededor de **Hermes-Agent** (de Nous Research). Proporciona capacidades de auditoría de ciberseguridad, análisis de código y automatización de infraestructura con una personalidad "cínica". El proyecto se encuentra en `/home/reck/Janitor-Agent`.

El nombre del proyecto en `package.json` es `hermes-agent` (v1.0.0), pero la marca ha sido cambiada a "Janitor" a través de un patrón de wrapper.

---

## Estructura del Proyecto

```
/home/reck/Janitor-Agent/
├── agent/                    # Core modules del agente (~80 archivos)
├── hermes_cli/              # Implementación CLI (~60 archivos)
├── gateway/                 # Gateway de mensajería
├── tools/                   # Definiciones de herramientas
├── plugins/                 # Sistema de plugins (~50 archivos)
├── skills/                  # Skills integrados (29 directorios)
├── optional-skills/         # Skills opcionales (19 directorios)
├── tests/                   # Suite de pruebas (~24 subdirectorios)
├── environments/            # Entornos de ejecución del agente
├── ui-tui/                  # Terminal UI (React/Ink)
├── cron/                    # Sistema de cron
├── acp_adapter/             # Agent Client Protocol adapter
├── tui_gateway/             # TUI Gateway alternativo
├── providers/               # Proveedores de modelos
├── web/                     # Dashboard web (React)
├── website/                 # Sitio de documentación (Docusaurus)
├── docs/                    # Documentación adicional
├── scripts/                 # Scripts de instalación y utilería
├── locales/                 # Archivos de internacionalización (16 idiomas)
├── .github/                 # GitHub workflows y actions
├── pyproject.toml           # Configuración Python
├── package.json             # Dependencias Node.js
├── Dockerfile               # Definición de contenedor
├── docker-compose.yml       # Configuración Docker Compose
├── flake.nix                # Configuración Nix
└── README.md                # README (bilingüe EN/CN)
```

---

## Puntos de Entrada Principales

### Comandos CLI

| Comando | Módulo | Propósito |
|---------|--------|-----------|
| `hermes` | `hermes_cli.main:main` | Launcher CLI principal |
| `hermes-agent` | `run_agent:main` | Ejecutor de agente AI con tool calling |
| `hermes-acp` | `acp_adapter.entry:main` | Adapter Agent Client Protocol |
| `janitor` | `janitor_cli:main` | Wrapper CLI de Janitor |

### Archivos Python Principales

| Archivo | Propósito | Tamaño |
|---------|-----------|--------|
| `run_agent.py` | Implementación principal del agente | ~818KB |
| `cli.py` | CLI de Hermes | ~622KB |
| `janitor_cli.py` | Wrapper CLI de Janitor | ~7KB |
| `mcp_serve.py` | Implementación del servidor MCP | - |
| `batch_runner.py` | Procesamiento paralelo por lotes | - |
| `rl_cli.py` | CLI de entrenamiento RL | - |
| `hermes_bootstrap.py` | Bootstrap UTF-8 para Windows | - |

---

## Módulos Principales

### 1. `/agent/` - Módulos Core del Agente (~80 archivos)

Proporciona las capacidades centrales del agente:

| Módulo | Propósito |
|--------|-----------|
| `browser_tool.py`, `browser_cdp_tool.py`, `browser_supervisor.py` | Automatización de navegador |
| `code_execution_tool.py` | Ejecución de código |
| `delegate_tool.py` | Delegación de tareas |
| `file_operations.py`, `file_tools.py` | Manipulación de archivos |
| `terminal_tool.py` | Emulación de terminal |
| `skills_hub.py`, `skills_tool.py`, `skill_manager_tool.py` | Gestión de skills |
| `mcp_tool.py` | Integración MCP (Model Context Protocol) |
| `memory_tool.py`, `transcription_tools.py`, `tts_tool.py`, `vision_tools.py` | Herramientas multimedia |
| `web_tools.py` | Web scraping/búsqueda |
| `discord_tool.py`, `send_message_tool.py` | Mensajería |
| `kanban_tools.py` | Integración de tableros Kanban |
| `cronjob_tools.py` | Gestión de trabajos cron |
| `credential_files.py`, `mcp_oauth.py` | Autenticación/OAuth |
| `checkpoint_manager.py` | Checkpoint de estado |

### 2. `/hermes_cli/` - Implementación CLI (~60 archivos)

Módulo CLI grande (~461KB solo main.py):

| Archivo | Propósito |
|---------|-----------|
| `main.py` | Entry point CLI principal (~461KB) |
| `gateway.py` | Cliente gateway (~223KB) |
| `config.py` | Gestión de configuración (~229KB) |
| `models.py` | Gestión de modelos (~143KB) |
| `commands.py` | Comandos CLI (~73KB) |
| `setup.py` | Setup/instalación (~141KB) |
| `tools_config.py` | Configuración de herramientas (~129KB) |
| `skin_engine.py` | Motor de temas TUI (~49KB) |
| `banner.py` | Branding ASCII art |
| `auth.py` | Autenticación (~214KB) |
| `profiles.py` | Gestión de perfiles (~48KB) |
| `providers.py` | Gestión de proveedores |
| `kanban.py`, `kanban_db.py` | Integración Kanban |
| `web_server.py` | Servidor web dashboard (~171KB) |
| `doctor.py` | Diagnósticos (~83KB) |

### 3. `/gateway/` - Gateway de Mensajería

Maneja mensajería multiplataforma:

- `server.py` - Servidor gateway (~70KB)
- `session.py` - Gestión de sesiones
- `tools.py` - Herramientas del gateway
- `permissions.py` - Gestión de permisos
- `run.py` - Runner principal del gateway (~794KB, archivo más grande)

### 4. `/tools/` - Definiciones de Herramientas

| Directorio | Propósito |
|------------|-----------|
| `browser_providers/` | Backends de proveedor de navegador (browserbase, firecrawl, browser_use) |
| `computer_use/` | Automatización de uso de computadora (cua_backend.py, tool.py, schema.py) |
| `environments/` | Entornos sandbox (docker, local, modal, daytona, vercel) |
| `neutts_samples/` | Muestras de síntesis de voz |
| `context_engine/` | Motor de contexto |
| `disk-cleanup/` | Herramientas de limpieza de disco |

### 5. `/plugins/` - Sistema de Plugins (~50 archivos)

Arquitectura de plugins extensible:

| Plugin | Propósito |
|--------|-----------|
| `context_compressor.py` | Compresión de contexto |
| `model_metadata.py` | Metadatos de modelo |
| `curator.py` | Curación de contenido |
| `credential_pool.py` | Gestión de credenciales |
| `prompt_builder.py` | Construcción de prompts |
| `auxiliary_client.py` | Servicios auxiliares (~207KB) |
| `anthropic_adapter.py`, `bedrock_adapter.py`, `gemini_*.py`, `codex_responses_adapter.py` | Adaptadores de proveedor LLM |
| `models_dev.py`, `models.py` | Definiciones de modelos |
| `memory_manager.py`, `memory_provider.py` | Sistemas de memoria |
| `tool_guardrails.py` | Guardrails de seguridad |
| `rate_limit_tracker.py` | Seguimiento de rate limiting |
| `lsp/` | Soporte Language Server Protocol |
| `transports/` | Capas de transporte |

---

## Skills del Sistema

### `/skills/` - Skills Integrados (29 directorios)

Skills categorizados por dominio:

| Categoría | Skills |
|-----------|--------|
| apple | Integración ecosistema Apple |
| autonomous-ai-agents | Frameworks de agentes AI |
| creative | Arte, música, generación de video |
| data-science | Análisis de datos, pandas, visualización |
| devops | Infraestructura, Docker, Kubernetes |
| diagramming | Generación de diagramas |
| dogfood | Pruebas internas |
| email | Integración email |
| gaming | Herramientas relacionadas con juegos |
| github | Integración GitHub |
| janitor-core | **Skills core específicos de Janitor** |
| janitor-onboarding | **Skills de onboarding de Janitor** |
| media | Procesamiento video/audio |
| mlops | Operaciones de machine learning |
| productivity | Herramientas de productividad |
| research | Utilidades de investigación |
| smart-home | Automatización del hogar |
| social-media | Integración redes sociales |
| software-development | Herramientas de codificación |
| yuanbao | Integración Yuanbao |

### `/optional-skills/` - Skills Opcionales (19 directorios)

Skills adicionales para casos de uso especializados:

- `blockchain/` - Integración blockchain
- `communication/` - Mensajería avanzada
- `devops/` - DevOps extendido
- `dogfood/` - Pruebas internas
- `finance/` - Herramientas financieras
- `health/` - Salud/bienestar
- `mcp/` - Skills relacionados con MCP
- `migration/` - Herramientas de migración
- `mlops/` - Herramientas ML extendidas
- `security/` - Auditoría de seguridad
- `web-development/` - Herramientas de desarrollo web

---

## Entornos de Ejecución

### `/environments/` - Entornos del Agente

Entornos sandbox para ejecución de agentes:

| Archivo/Directorio | Propósito |
|-------------------|-----------|
| `agent_loop.py` | Implementación del loop del agente |
| `agentic_opd_env.py` | Entorno de operaciones agentic |
| `hermes_base_env.py` | Entorno base |
| `hermes_swe_env/` | Entorno de ingeniería de software |
| `tool_context.py` | Gestión de contexto de herramientas |
| `web_research_env.py` | Entorno de investigación web |
| `benchmarks/` | Benchmarks de rendimiento |
| `tool_call_parsers/` | Parsers de tool calls |

---

## Interfaces de Usuario

### `/ui-tui/` - Terminal UI (React/Ink)

TUI basada en React con:

- `src/` - Componentes React
- `packages/hermes-ink/` - Librería de componentes Ink
- `dist/` - Output construido
- `package.json` - Dependencias NPM

### `/web/` - Dashboard Web (React)

Aplicación React para dashboard:

- `src/` - Código fuente React
- `public/` - Assets estáticos
- `package.json` - Dependencias
- `vite.config.ts` - Configuración de build Vite

### `/website/` - Sitio de Documentación (Docusaurus)

- `docs/` - Documentación
- `docusaurus.config.ts` - Configuración Docusaurus
- `sidebars.ts` - Configuración de sidebar

---

## Sistema de Cron

### `/cron/` - Programación de Tareas

| Archivo | Propósito |
|---------|-----------|
| `scheduler.py` | Programador de cron (~77KB) |
| `jobs.py` | Definiciones de trabajos (~41KB) |

---

## Scripts de Instalación y Utilería

### `/scripts/` - Directorio de Scripts

| Script | Propósito |
|--------|-----------|
| `bootstrap.sh` | Script de bootstrap principal |
| `install.sh` | Script de instalación (~78KB) |
| `install.ps1` | Instalador PowerShell (~68KB) |
| `janitor-install.sh` | Instalador específico de Janitor (~17KB) |
| `setup_open_webui.sh` | Setup de Open WebUI |
| `release.py` | Automatización de releases (~71KB) |
| `build_skills_index.py` | Constructor de índice de skills |
| `profile-tui.py` | TUI de perfiles |
| `contributor_audit.py` | Auditoría de contribuidores |
| `lint_diff.py` | Utilidades de linting |
| `whatsapp-bridge/`, `hermes-gateway/` | Scripts específicos de plataforma |

---

## Integración GitHub

### `/.github/`

**Workflows CI/CD:**

| Workflow | Propósito |
|----------|-----------|
| `janitor-ci.yml` | CI de Janitor |
| `lint.yml` | Workflow de linting |
| `upstream-sync.yml` | Sincronización upstream (NousResearch/hermes-agent) |
| `uv-lockfile-check.yml` | Validación de lockfile |

**Otros:**
- `actions/` - GitHub Actions personalizadas
- `dependabot.yml` - Actualizaciones de dependencias automáticas

---

## Internacionalización

### `/locales/` - Archivos de Idiomas (16 idiomas)

- `en.yaml`, `es.yaml`, `fr.yaml`, `de.yaml`, `ja.yaml`, `ko.yaml`
- `zh.yaml`, `zh-hant.yaml`, `ru.yaml`, `pt.yaml`, `it.yaml`, `tr.yaml`
- `hu.yaml`, `ga.yaml`, `uk.yaml`, `af.yaml`

---

## Documentación

### `/docs/` - Documentación Adicional

- `plans/` - Planes y especificaciones del proyecto
- `SOUL.md` - Definición del alma/personalidad del agente

---

## Archivos de Configuración

| Archivo | Propósito |
|---------|-----------|
| `pyproject.toml` | Configuración del paquete Python, dependencias, entry points |
| `package.json` | Dependencias Node.js (herramientas de navegador) |
| `pnpm-workspace.yaml` | Configuración monorepo pnpm |
| `flake.nix` | Configuración Nix flake |
| `.env.example` | Template de variables de entorno |
| `.envrc` | Configuración direnv |
| `cli-config.yaml.example` | Ejemplo de configuración CLI |
| `docker-compose.yml` | Configuración Docker Compose |
| `Dockerfile` | Definición de contenedor |

---

## Dependencias Principales

### Dependencias Python Core (de `pyproject.toml`)

```python
openai              # Cliente API OpenAI
python-dotenv       # Carga de variables de entorno
httpx               # Cliente HTTP con soporte SOCKS
rich                # Output de terminal enriquecido
pydantic            # Validación de datos
prompt_toolkit      # Input CLI
croniter            # Programación cron
PyJWT               # Autenticación JWT
psutil              # Gestión de procesos
```

### Dependencias Opcionales (extras)

```python
anthropic           # API Anthropic
firecrawl-py, exa-py, parallel-web  # Web scraping
discord.py, python-telegram-bot     # Mensajería
google-api-python-client           # Google Workspace
boto3                # AWS Bedrock
honcho-ai            # Memoria Honcho
fastapi, uvicorn     # Servidor web
```

### Dependencias Node.js

```javascript
// Automatización de navegador
@askjo/camofox-browser
agent-browser

// TUI
ink
react
nanostores
```

---

## Patrones de Arquitectura

1. **Patrón Wrapper**: Janitor envuelve a Hermes-Agent sin modificar los archivos core de Hermes
2. **Sistema de Plugins**: Extensible vía directorio `plugins/`
3. **Sistema de Skills**: Módulos organizados en `skills/` y `optional-skills/`
4. **Adaptadores de Proveedores**: Soporte múltiple de proveedores LLM vía patrón adapter
5. **Tool Backends**: Entornos sandbox para ejecución segura de código
6. **Arquitectura Gateway**: Mensajería multiplataforma
7. **TUI + Web UI**: Interfaces tanto de terminal como basadas en web

---

## Características Especiales

| Directorio | Propósito |
|-----------|-----------|
| `.opencode/` | Configuración del agente OpenCode |
| `.sisyphus/` | Herramienta de planificación Sisyphus |
| `tinker-atropos/` | Submódulo de entrenamiento RL |
| `packaging/` | Utilidades de empaquetado |
| `datagen-config-examples/` | Ejemplos de generación de datos |
| `assets/` | Assets estáticos (banners, imágenes) |
| `docker/` | Archivos relacionados con Docker |
| `nix/` | Archivos específicos de Nix |

---

## Testing

### `/tests/` - Suite de Pruebas (~24 subdirectorios)

| Directorio | Propósito |
|-----------|-----------|
| `agent/` | Tests unitarios del agente |
| `cli/` | Tests de CLI |
| `gateway/` | Tests del gateway |
| `plugins/` | Tests de plugins |
| `providers/` | Tests de proveedores |
| `e2e/` | Tests end-to-end |
| `integration/` | Tests de integración |
| `stress/` | Tests de estrés |
| `honcho_plugin/`, `openviking_plugin/` | Tests de plugins |
| `hermes_cli/` | Tests de CLI (~12KB+ archivos) |
| `conftest.py` | Configuración Pytest |

---

## Notas de Implementación

- **Wrapper Pattern**: Janitor envuelve Hermes-Agent, usando `janitor_cli.py` como punto de entrada que importa y reutiliza la funcionalidad de Hermes
- **Extensibilidad**: El sistema de plugins permite agregar nuevos proveedores, herramientas y capacidades sin modificar el core
- **Seguridad**: Los guardrails (`tool_guardrails.py`) y los entornos sandbox proporcionan seguridad para la ejecución de código
- **Modularidad**: Cada skill es un paquete independiente que puede ser habilitado/deshabilitado según necesidad
