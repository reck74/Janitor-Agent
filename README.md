# 🛠 THE JANITOR v0.1.0 — DevSecOps Orchestrator

<p align="center">
  <img src="assets/banner.png" alt="The Janitor" width="100%">
</p>

**El agente cínico que аудирует tu código, limpia tu deuda técnica y orquesta tu infraestructura DevOps — automáticamente.**

---

## ¿Qué es Janitor?

Janitor es un **orquestador DevSecOps** con personalidad cínica que:

- **Pre-instala y configura infraestructura Docker local** (Honcho + Firecrawl) sin que te toques nada
- **Audit tu código** buscando OWASP Top 10, CWE Top 25 y deuda técnica
- **Ejecuta en WSL2/Linux** con `HERMES_HOME` aislado en `~/.janitor` — **Hostile Takeover** del entorno
- **Viene con baterías incluidas**: Zero-Friction Install en una sola línea

> ⚠️ **ATENCIÓN:** Janitor es una evolución agresiva de Hermes. Al instalar, Janitor inyecta `HERMES_HOME=~/.janitor` en tu `~/.bashrc`. Tu instalación Hermes existente puede dejar de funcionar por defecto.

---

## Features

| Feature | Descripción |
|---------|-------------|
| 🚀 **Zero-Friction Install** | `curl -sL https://raw.githubusercontent.com/reck74/Janitor-Agent/main/scripts/bootstrap.sh \| bash` — una línea, nada más |
| 🐳 **Docker Auto-Setup** | Honcho (memoria persistente) + Firecrawl (scraping web) levantados via `/onboard` |
| 🔒 **Hostile Takeover** | `HERMES_HOME=~/.janitor` inyectado en `~/.bashrc`/`~/.zshrc` — aislamiento total de Hermes |
| 🌑 **Sentry Dark Native TUI** | Interfaz oscura estilo Sentry, optimizada para DevOps |
| 🔍 **Auditoría DevSecOps** | Escanea tu código en busca de vulnerabilidades OWASP/CWE |
| ⬆️ **Upstream Sync** | Sincronización automática semanal con `NousResearch/hermes-agent` via PRs |
| 🛠️ **Wrapper Pattern** | Extensiones en archivos separados, core de Hermes inmutable |

---

## Quick Start

### Linux, macOS, WSL2, Termux

```bash
# Una línea — instala Python, Node, uv, Janitor y hace el enlace global:
curl -sL https://raw.githubusercontent.com/reck74/Janitor-Agent/main/scripts/bootstrap.sh | bash

# Recarga tu shell:
source ~/.bashrc

# Lanza Janitor:
janitor

# Dentro de Janitor, ejecuta el onboarding para levantar Honcho + Firecrawl:
/onboard
```

### Requisitos

- **Linux / WSL2** (no soporta macOS ni Android/Termux)
- **Docker** instalado y corriendo
- **Git**, **curl**

---

## Onboarding

```bash
# 1. Instalar (ver Quick Start arriba)
# 2. Configurar API keys interactivamente:
~/.janitor-source/scripts/janitor-install.sh

# 3. Levantar infraestructura Docker local:
janitor
# Dentro de Janitor:
/onboard

# 4. Listo — Janitor recordará tu contexto entre sesiones via Honcho
```

---

## Arquitectura

### Wrapper Pattern

Janitor es un **fork wrapper** de [Hermes Agent](https://github.com/NousResearch/hermes-agent):

| Capa | Regla |
|------|-------|
| **Core inmutable** | Nunca se modifica `cli.py`, `run_agent.py`, `gateway/run.py` |
| **Extensiones** | `janitor_cli.py` — `JanitorCLI` hereda de `HermesCLI` |
| **Skills aislados** | Solo en `skills/janitor-*/` — skills upstream nunca se tocan |
| **TUI branding** | `skin_engine.py` maneja el tema visual sin hardcode |

### Upstream Sync

Janitor sincroniza cambios upstream via GitHub Actions (cada Lunes 00:00 UTC):

1. Verifica si hay cambios nuevos en `NousResearch/hermes-agent`
2. Crea rama `upstream-sync-YYYYMMDDHHMMSS`
3. Merge + poda automática de workflows intrusos de upstream
4. Si hay diff real → abre PR; si no → `exit 0` limpio

---

## Configuración de API Keys

```bash
# El instalador interactivo solicita:
# - OPENAI_API_KEY  (obligatoria)
# - MINIMAX_API_KEY (obligatoria — usada como LLM_ANTHROPIC_API_KEY para Honcho)
# - HONCHO_API_KEY  (opcional — si no se provee, usar modo Docker local)
# - FIRECRAWL_API_KEY (opcional)
```

---

## License

MIT — ver [LICENSE](LICENSE).

**Construido por Reck!** — [@reck74](https://github.com/reck74)

Inspirado en [Hermes Agent](https://github.com/NousResearch/hermes-agent) de Nous Research.