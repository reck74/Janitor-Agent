# Material anterior a Janitor 1.0

Este directorio conserva referencias y prototipos retirados del runtime. Los fuentes Python históricos usan `.py.txt` para conservar sus bytes sin registrarse como módulos ejecutables ni pruebas. No se instala ni se importa desde el agente.

| Material | Motivo | Sustituto | Soporte |
| --- | --- | --- | --- |
| `docs/pre-1.0/` | Planes v5, transcripciones y decisiones superadas | `MERGE_GUIDE.md` y guías Janitor de `website/docs/` | Histórico |
| `config/config-pre-1.0.yaml` | Snapshot completo de defaults antiguos | Defaults del motor + `assets/janitor/config-overlay.yaml` | Referencia; no copiar a un perfil |
| `prototypes/agent/opencode_session_manager.py.txt` | Gestor experimental sin consumidores activos | Sesiones y delegación upstream; cliente opcional `skills/janitor-opencode/` | Sin integración runtime |
| `prototypes/agent/janitor_language_guard.py.txt` | Helper desconectado del bucle | Persona `SOUL.md` y configuración del perfil | Histórico |
| `prototypes/tools/{agent_router,specialized_agents}.py.txt` | Router especializado sin punto de entrada activo | Skills de agentes y delegación explícita | Prototipo |
| `prototypes/gateway/whatsapp.py.txt` | Adapter anterior a la arquitectura de plugins | `plugins/platforms/whatsapp/` | Retirado |
| `prototypes/gateway/feishu_meeting_invite.py.txt` | Copia anterior sin consumidores | Helper bajo `plugins/platforms/feishu/` | Retirado |
| `prototypes/scripts/test_opencode_orchestrator.py.txt` | Prueba manual con imports históricos | Health explícito de la skill OpenCode | Referencia |

Los dos clientes OpenCode tenían SHA-256 idéntico `26646cd8ee17db73e910bbaf0d5892341528aa1ee803dc8a9eb15d9ace307b5a`. Se conserva una implementación bajo `skills/janitor-opencode/scripts/client.py`. El script manual histórico describe operaciones que crean sesiones; no debe ejecutarse como test del repositorio.

Google Code Assist/OAuth y el compose Honcho duplicado fueron retirados: estable ya eliminó esos módulos y el despliegue vigente tiene un único dueño bajo `skills/janitor-honcho/`. Las protecciones de archivos de credenciales OAuth se conservan, porque siguen protegiendo datos de instalaciones antiguas.

Ninguna de estas operaciones elimina configuración, perfiles, sesiones o volúmenes del usuario. La migración de datos existente es `scripts/migrate-janitor-1.0.sh`, que toma un backup verificable antes de aplicar cambios.
