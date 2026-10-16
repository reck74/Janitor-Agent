---
name: janitor-onboarding
description: "Janitor orientation and optional capability selector."
version: 3.0.0
author: Janitor Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [onboarding, orientation, skills, capabilities]
    category: devops
---

# Primer arranque de Janitor

La instalación base requiere **Docker, MiniMax y Honcho**. Honcho puede ser local o cloud. Local requiere además `OPENAI_API_KEY` para embeddings; cloud requiere `HONCHO_API_KEY`. MiniMax es el proveedor principal en ambos modos. El instalador comprueba dependencias, memoria y credenciales antes de anunciar éxito.

CLI y Desktop comparten `~/.janitor`, sus perfiles y sesiones. La instalación prepara `.env`, `config.yaml`, `SOUL.md` y la skin `sentry-janitor`. Una reinstalación conserva elecciones, secretos y persona y crea backups antes de migrar. Ayuda, diagnóstico y reparación permanecen accesibles cuando faltan credenciales:

```bash
janitor --help
janitor doctor
janitor setup
janitor update --check
```

Browser, Firecrawl y el resto de capacidades se instalan **explícitamente después del arranque base**. Infisical y AgentMemory no forman parte del stack. Este onboarding no despliega servicios.

| Capacidad | Activación desde la raíz del repositorio |
| --- | --- |
| Honcho base (reparar local) | `bash skills/janitor-honcho/scripts/deploy.sh` |
| Browser | `bash skills/janitor-browser/scripts/install.sh` |
| Firecrawl | `bash skills/janitor-firecrawl/scripts/deploy.sh` |
| LightRAG + Ollama propio | `bash skills/janitor-lightrag/scripts/deploy.sh` |
| n8n | `bash skills/janitor-n8n/scripts/deploy.sh` |
| NocoDB | `bash skills/janitor-nocodb/scripts/deploy.sh` |
| WAHA | `bash skills/janitor-waha/scripts/deploy.sh` |
| OpenDesign | Seguir `skills/janitor-opendesign/SKILL.md` e integrar explícitamente |
| OpenCode experimental | Health explícito en `skills/janitor-opencode/SKILL.md` |
| Integración de skills externas | `skills/janitor-skill-integration/SKILL.md` |
| Revisión de código | Cargar `janitor-code-review-agent` y delegar explícitamente |
| Investigación de repositorios | Cargar `janitor-repo-research-agent` y delegar explícitamente |
| Auditoría de configuración | `janitor-config-audit`: preview y merge con backup |
| Higiene y cachés | `janitor-core`: revisar alcance antes de limpiar |
| Desktop Linux | `skills/janitor-desktop-launcher/scripts/launch.sh --help` |

Ejecuta los scripts desde una instalación PM preparada. Usa `JANITOR_HOME` para un home personalizado; los comandos CLI admiten `--profile`. Cada skill describe credenciales, puertos, uso de recursos, verificación y recuperación. Los instaladores propagan errores y los volúmenes anteriores se conservan durante migraciones.

Para comprobar servicios instalados, sin activar otros:

```bash
bash skills/janitor-onboarding/scripts/local-services.sh status
```

Los errores de Docker o de credenciales se reparan desde la configuración correspondiente. No borres un archivo de secretos o un volumen para resolver un problema de arranque. Consulta `MERGE_GUIDE.md` y las guías Janitor vigentes; `legacy/` conserva material histórico sin soporte runtime.
