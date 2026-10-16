# Janitor: arquitectura y mantenimiento

Janitor conserva el motor Hermes y extiende sus interfaces desde módulos propios. La base de esta actualización es Hermes **v0.22.2**, commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8`.

## Superficies activas

| Superficie | Ubicación | Contrato |
| --- | --- | --- |
| CLI e identidad | `janitor_cli.py`, `janitor_ext/` | Extender HermesCLI; conservar nombres y protocolo upstream |
| Actualización | `janitor_update_core.py` | Un único flujo compartido por los dos entry points |
| Instalación | `scripts/bootstrap.sh`, `scripts/janitor-install.sh` | Linux primero; Docker, MiniMax y Honcho son requisitos base |
| Configuración | `assets/janitor/config-overlay.yaml` | Overlay de defaults Hermes; preservar configuración del usuario |
| TUI | `ui-tui/`, `skins/` | Skin e inyección compatibles; build y tests obligatorios |
| Desktop | `apps/desktop/janitor/` | Overlay de producto y staging; conservar la implementación Hermes |
| MCP web | `janitor_ext/mcp_dashboard.py`, `janitor_ext/mcp_logs.py` | Autenticación upstream, ámbito de perfil y stderr aislado por servidor |
| Capacidades opcionales | `skills/janitor-*/` | Instalación explícita después del primer arranque |

Honcho puede ser local o cloud; Docker sigue siendo un requisito de Janitor. Browser y Firecrawl se instalan de forma explícita. Infisical y AgentMemory no forman parte del stack base. El snapshot `legacy/config/config-pre-1.0.yaml` se conserva como referencia histórica; el instalador usa defaults actuales más el overlay.

## Verificación

`.github/janitor-tests.txt` es el manifiesto único del gate Python del fork. Ejecutar `python3 scripts/run_janitor_tests.py -j 2 --file-retries 0` con el entorno de pruebas preparado por `hermes pm`. Los tests upstream permanecen en el árbol y se ejecutan en `upstream-sync-verify` en sincronizaciones, releases o ejecución manual.

El TUI requiere `npm run build --workspace ui-tui` y `npm run test --workspace ui-tui`. El dashboard web tiene su propio check/build. Desktop requiere tests de adapter, typecheck, bundle y un smoke de lanzamiento antes de publicar.

## Qué se conserva como legado

`legacy/docs/pre-1.0/` contiene planes anteriores y especificaciones experimentales; no son instrucciones vigentes. Los skills de agentes especializados describen delegación explícita. El prototipo de routing automático no se considera una capacidad activa ni justifica modificar el core.

El código, las pruebas y la documentación upstream se conservan para facilitar futuras sincronizaciones. Una ruta poco usada no se elimina sólo por no formar parte del gate del fork.

La guía raíz `MERGE_GUIDE.md` define los gates de sincronización y `AGENTS.md` las directivas del fork.
