# 🛠 THE JANITOR v0.1.0 — DevSecOps Orchestrator

<p align="center">
  <img src="assets/banner.png" alt="The Janitor" width="100%">
</p>

<<<<<<< HEAD
**El agente cínico que аудирует tu código, limpia tu deuda técnica y orquesta tu infraestructura DevOps — automáticamente.**
=======
**The self-improving AI agent built by [Nous Research](https://nousresearch.com).** It's the only agent with a built-in learning loop — it creates skills from experience, improves them during use, nudges itself to persist knowledge, searches its own past conversations, and builds a deepening model of who you are across sessions. Run it on a $5 VPS, a GPU cluster, or serverless infrastructure that costs nearly nothing when idle. It's not tied to your laptop — talk to it from Telegram while it works on a cloud VM.

Use any model you want — [Nous Portal](https://portal.nousresearch.com), [OpenRouter](https://openrouter.ai) (200+ models), [NovitaAI](https://novita.ai) (AI-native cloud for Model API, Agent Sandbox, and GPU Cloud), [NVIDIA NIM](https://build.nvidia.com) (Nemotron), [Xiaomi MiMo](https://platform.xiaomimimo.com), [z.ai/GLM](https://z.ai), [Kimi/Moonshot](https://platform.moonshot.ai), [MiniMax](https://www.minimax.io), [Hugging Face](https://huggingface.co), OpenAI, or your own endpoint. Switch with `hermes model` — no code changes, no lock-in.

<table>
<tr><td><b>A real terminal interface</b></td><td>Full TUI with multiline editing, slash-command autocomplete, conversation history, interrupt-and-redirect, and streaming tool output.</td></tr>
<tr><td><b>Lives where you do</b></td><td>Telegram, Discord, Slack, WhatsApp, Signal, and CLI — all from a single gateway process. Voice memo transcription, cross-platform conversation continuity.</td></tr>
<tr><td><b>A closed learning loop</b></td><td>Agent-curated memory with periodic nudges. Autonomous skill creation after complex tasks. Skills self-improve during use. FTS5 session search with LLM summarization for cross-session recall. <a href="https://github.com/plastic-labs/honcho">Honcho</a> dialectic user modeling. Compatible with the <a href="https://agentskills.io">agentskills.io</a> open standard.</td></tr>
<tr><td><b>Scheduled automations</b></td><td>Built-in cron scheduler with delivery to any platform. Daily reports, nightly backups, weekly audits — all in natural language, running unattended.</td></tr>
<tr><td><b>Delegates and parallelizes</b></td><td>Spawn isolated subagents for parallel workstreams. Write Python scripts that call tools via RPC, collapsing multi-step pipelines into zero-context-cost turns.</td></tr>
<tr><td><b>Runs anywhere, not just your laptop</b></td><td>Seven terminal backends — local, Docker, SSH, Singularity, Modal, Daytona, and Vercel Sandbox. Daytona and Modal offer serverless persistence — your agent's environment hibernates when idle and wakes on demand, costing nearly nothing between sessions. Run it on a $5 VPS or a GPU cluster.</td></tr>
<tr><td><b>Research-ready</b></td><td>Batch trajectory generation, trajectory compression for training the next generation of tool-calling models.</td></tr>
</table>
>>>>>>> upstream/main

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

<<<<<<< HEAD
=======
What gets imported:
- **SOUL.md** — persona file
- **Memories** — MEMORY.md and USER.md entries
- **Skills** — user-created skills → `~/.hermes/skills/openclaw-imports/`
- **Command allowlist** — approval patterns
- **Messaging settings** — platform configs, allowed users, working directory
- **API keys** — allowlisted secrets (Telegram, OpenRouter, OpenAI, Anthropic, ElevenLabs)
- **TTS assets** — workspace audio files
- **Workspace instructions** — AGENTS.md (with `--workspace-target`)

See `hermes claw migrate --help` for all options, or use the `openclaw-migration` skill for an interactive agent-guided migration with dry-run previews.

---

## Contributing

We welcome contributions! See the [Contributing Guide](https://hermes-agent.nousresearch.com/docs/developer-guide/contributing) for development setup, code style, and PR process.

Quick start for contributors — clone and go with `setup-hermes.sh`:

```bash
git clone https://github.com/NousResearch/hermes-agent.git
cd hermes-agent
./setup-hermes.sh     # installs uv, creates venv, installs .[all], symlinks ~/.local/bin/hermes
./hermes              # auto-detects the venv, no need to `source` first
```

Manual path (equivalent to the above):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[all,dev]"
scripts/run_tests.sh
```

---

## Community

- 💬 [Discord](https://discord.gg/NousResearch)
- 📚 [Skills Hub](https://agentskills.io)
- 🐛 [Issues](https://github.com/NousResearch/hermes-agent/issues)
- 🔌 [computer-use-linux](https://github.com/avifenesh/computer-use-linux) — Linux desktop-control MCP server for Hermes and other MCP hosts, with AT-SPI accessibility trees, Wayland/X11 input, screenshots, and compositor window targeting.
- 🔌 [HermesClaw](https://github.com/AaronWong1999/hermesclaw) — Community WeChat bridge: Run Hermes Agent and OpenClaw on the same WeChat account.

>>>>>>> upstream/main
---

## License

MIT — ver [LICENSE](LICENSE).

**Construido por Reck!** — [@reck74](https://github.com/reck74)

Inspirado en [Hermes Agent](https://github.com/NousResearch/hermes-agent) de Nous Research.