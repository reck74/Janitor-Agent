# Janitor Agent

Janitor es un fork de [Hermes Agent](https://github.com/NousResearch/hermes-agent) con configuración, identidad y herramientas orientadas al mantenimiento de proyectos. Conserva el motor y las interfaces de Hermes, y aísla sus extensiones en `janitor_ext/`, wrappers, skins y `skills/janitor-*/`.

Esta rama prepara **Janitor 1.0.0**, basado en **Hermes 0.22.2** (`d923a5eb487a17c0a68801bba9ef0f56c81040a8`). La versión de producto es independiente del motor. La publicación estable depende de completar la [aceptación de recuperación](JANITOR_RECOVERY_AUDIT.md); un build local o un candidato no acredita esa aceptación.

La primera entrega Desktop es **Linux x86_64**, en AppImage. CLI, TUI, Web y Desktop comparten el runtime y los perfiles Janitor.

## Requisitos

- **Docker** instalado, activo y accesible para tu usuario, también cuando elijas memoria cloud.
- **MiniMax** como proveedor principal: `MINIMAX_API_KEY` válida.
- **Honcho** obligatorio, con una de estas modalidades:
  - Local: servidor Docker y `OPENAI_API_KEY` válida para embeddings; MiniMax realiza la inferencia.
  - Cloud: `HONCHO_API_KEY` válida; no requiere la credencial OpenAI local.
- Red para descargar el runtime y las dependencias. El gestor PM prepara Python 3.14, Node 26 y los paquetes fijados; no hace falta mantener un venv manual.

El instalador pide las credenciales sin mostrarlas y las conserva en `.env` del perfil con permisos privados. Las opciones de comportamiento viven en `config.yaml`. Ayuda y diagnóstico siguen accesibles si una credencial falta o deja de funcionar.

## Instalación

Cuando exista la release estable `v1.0.0`, el instalador público fijado será:

```bash
(
  set -e
  installer=$(mktemp)
  trap 'rm -f "$installer"' EXIT
  curl -fsSL https://raw.githubusercontent.com/reck74/Janitor-Agent/v1.0.0/scripts/bootstrap.sh -o "$installer"
  bash "$installer"
) && janitor
```

El bootstrap verifica Docker, descarga Janitor, prepara PM, construye las interfaces y comprueba Honcho. Un fallo detiene la instalación con salida no cero. Browser y computer-use quedan excluidos de la instalación base.

Para probar un candidato, usa únicamente el **SHA publicado y verificado del candidato** desde su checkout:

```bash
bash scripts/bootstrap.sh --commit <SHA_COMPLETO_DEL_CANDIDATO>
```

No sustituyas ese SHA por el commit de Hermes: el instalador y los metadatos deben pertenecer a Janitor. El comando sin ref necesita la release estable; no convierte automáticamente una rama de desarrollo en estable.

La raíz predeterminada es `~/.janitor`, con el código bajo `~/.janitor/janitor-core` y el comando privado publicado por el instalador. No se impone un `HERMES_HOME` global en el shell ni se reemplaza una instalación Hermes. Para otra raíz, usa `--hermes-home /ruta/janitor`.

## Desktop Linux

Descarga el AppImage y su archivo SHA256 de [Releases de Janitor](https://github.com/reck74/Janitor-Agent/releases), verifica el checksum y concede permiso de ejecución:

```bash
sha256sum --check janitor-desktop-1.0.0-linux-x86_64.AppImage.sha256
chmod +x janitor-desktop-1.0.0-linux-x86_64.AppImage
./janitor-desktop-1.0.0-linux-x86_64.AppImage
```

Usa el nombre exacto del artefacto publicado si pruebas un candidato. El primer arranque prepara el runtime local con el mismo instalador Janitor y solicita MiniMax/Honcho. Un AppImage no incluye credenciales. La interfaz conserva los componentes upstream y añade identidad, bootstrap y actualización de Janitor.

Consulta el [contrato de Desktop](apps/desktop/janitor/README.md) y la [guía de uso y recuperación](website/docs/user-guide/janitor.md).

## Uso, perfiles y recuperación

```bash
janitor --version
janitor --help
janitor doctor
janitor update --check
janitor update
janitor --profile trabajo
```

`update --check` sólo consulta disponibilidad. La actualización utiliza un único flujo, bloqueo compartido y recuperación de cambios locales. El resultado identifica si el runtime se actualizó y si el AppImage depende de otro propietario o necesita una acción adicional.

Antes de migrar una instalación anterior:

```bash
bash ~/.janitor/janitor-core/scripts/migrate-janitor-1.0.sh --help
bash ~/.janitor/janitor-core/scripts/migrate-janitor-1.0.sh
```

La migración crea un backup verificable antes de escribir y conserva sesiones, perfiles, credenciales y datos duraderos. No borra volúmenes Docker. Para reparar la configuración del perfil activo, ejecuta `janitor setup`; si necesitas cambiar la modalidad Honcho, consulta sus opciones con `janitor --run-module janitor_ext.install --help`. No restaures snapshots antiguos sobre todo `config.yaml`.

## Capacidades opcionales

Se instalan explícitamente después del primer arranque. El comando general resuelve la skill desde el checkout o el perfil instalado y conserva el perfil elegido:

```bash
janitor --run-module janitor_ext.optional_deploy skills/janitor-firecrawl/scripts/deploy.sh
```

| Capacidad | Guía y comando específico |
| --- | --- |
| Browser | [janitor-browser](skills/janitor-browser/SKILL.md) |
| Firecrawl | [janitor-firecrawl](skills/janitor-firecrawl/SKILL.md) |
| OpenDesign | [janitor-opendesign](skills/janitor-opendesign/SKILL.md) |
| LightRAG | [janitor-lightrag](skills/janitor-lightrag/SKILL.md) |
| n8n | [janitor-n8n](skills/janitor-n8n/SKILL.md) |
| NocoDB | [janitor-nocodb](skills/janitor-nocodb/SKILL.md) |
| WAHA | [janitor-waha](skills/janitor-waha/SKILL.md) |
| Revisión de código | [janitor-code-review-agent](skills/janitor-code-review-agent/SKILL.md) |
| Investigación de repositorios | [janitor-repo-research-agent](skills/janitor-repo-research-agent/SKILL.md) |
| Auditoría de configuración | [janitor-config-audit](skills/janitor-config-audit/SKILL.md) |
| OpenCode experimental | [janitor-opencode](skills/janitor-opencode/SKILL.md), health check explícito |

[Onboarding](skills/janitor-onboarding/SKILL.md) reúne el inventario completo. Honcho es parte de la base, aunque su implementación esté aislada en una skill. Infisical y AgentMemory no forman parte de este stack.

## Desarrollo y mantenimiento

Lee [AGENTS.md](AGENTS.md), [MERGE_GUIDE.md](MERGE_GUIDE.md) y la [arquitectura Janitor](website/docs/developer-guide/janitor-project.md). El gate Python del fork usa `.github/janitor-tests.txt`; la suite upstream completa se conserva y se ejecuta en la verificación de sincronización. TUI requiere build, typecheck y tests. Desktop exige build y smoke del overlay Janitor, además de aceptación real de instalación y actualización.

El [inventario del fork](legacy/fork-inventory.json) identifica las diferencias, consumidores y sustitutos. [Legacy](legacy/README.md) conserva material histórico fuera del runtime. La documentación general de Hermes permanece como referencia del motor; los requisitos y comandos de instalación de Janitor son los de esta página y su guía propia.

[Licencia MIT](LICENSE). Se conservan la autoría y los avisos de Nous Research y de todos los colaboradores upstream.
