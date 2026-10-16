---
title: Janitor Agent
sidebar_label: Janitor
---

# Instalar, actualizar y recuperar Janitor

Janitor 1.0.0 usa Hermes 0.22.2 como motor. Su instalación, credenciales y versión de producto son propias. El código Hermes mantiene sus nombres para permitir sincronizaciones; los comandos de esta guía arrancan el wrapper Janitor.

## Instalación base

Docker, MiniMax y Honcho son obligatorios. El modo Honcho local requiere `OPENAI_API_KEY` válida para embeddings además de `MINIMAX_API_KEY`; el modo cloud requiere `HONCHO_API_KEY` y `MINIMAX_API_KEY`. Docker sigue siendo requisito con Honcho cloud.

El bootstrap público estable está en `https://raw.githubusercontent.com/reck74/Janitor-Agent/v1.0.0/scripts/bootstrap.sh`. Descárgalo y ejecútalo con Bash cuando esa release esté publicada. Durante aceptación, usa el checkout del candidato y `bash scripts/bootstrap.sh --commit <SHA_COMPLETO_DEL_CANDIDATO>`. No mezcles un bootstrap de una versión con el SHA de otra.

El instalador prepara herramientas y Python mediante PM, construye TUI/Web y verifica la conexión a memoria. Browser y computer-use quedan excluidos hasta instalación explícita. Los servicios opcionales no se inician durante el arranque base.

La raíz predeterminada es `~/.janitor`; el runtime fuente vive en `~/.janitor/janitor-core`. Cada perfil mantiene su configuración, `.env`, persona, sesiones y memoria. `janitor --profile trabajo` selecciona un perfil nombrado. Una ruta explícita en `HERMES_HOME` se respeta para procesos hijos y reparaciones; no es necesario exportarla globalmente.

## Reparar y reinstalar

`janitor doctor` y `janitor --help` no requieren que todas las credenciales estén disponibles. `janitor setup` repara la instalación base del perfil seleccionado. El instalador valida YAML antes de escribir, preserva valores existentes y genera un backup al modificar una instalación.

Para elegir la modalidad de memoria desde el perfil correspondiente:

```bash
janitor --profile trabajo --run-module janitor_ext.install --help
janitor --profile trabajo --run-module janitor_ext.install --honcho-mode cloud
```

Introduce las credenciales cuando se soliciten. No las pongas en comandos, capturas o reportes. Cambiar entre local y cloud normaliza la configuración del proveedor; los perfiles ajenos permanecen intactos.

## Migración y backup

Ejecuta `scripts/migrate-janitor-1.0.sh --help` desde el checkout instalado antes de migrar. La migración de raíz recorre los perfiles; una reparación explícita de perfil sólo actúa en ese perfil. Los backups incluyen manifiesto, hashes, configuración, secretos, bases SQLite consistentes y configuración duradera de servicios. Los dumps de Honcho se registran como artefactos verificables. No borres el backup hasta comprobar sesiones, memoria y servicios.

La migración conserva los volúmenes originales. Para restaurar, detén los escritores del perfil o servicio afectado, verifica los hashes del manifiesto y restaura los archivos de ese perfil. Un volumen no equivale a un backup de sus credenciales: recupera también su configuración y archivos de entorno. Si un paso falla, conserva el backup y revisa el error antes de reintentar.

## Actualización y Desktop

`janitor update --check` consulta sin instalar. `janitor update` prepara la nueva versión, comprueba dependencias y coordina la conservación de cambios locales mediante el flujo compartido. No ejecutes `git reset --hard` para resolver un fallo: revisa el recibo y el stash que indica el actualizador.

Desktop Linux usa AppImage source/bootstrap. El build publica identidad Janitor, versión, arquitectura y SHA fuente. La aplicación y CLI comparten perfiles y sesiones. Si el AppImage pertenece a un gestor externo, el resultado explica la acción pendiente; no anuncia actualización completa de todos los componentes.

Una sustitución de AppImage debe confirmar el arranque de la nueva versión. Si falla, conserva o restaura el artefacto anterior e informa por separado del estado del runtime. La release estable requiere validar instalación desde cero y actualización N→N+1 sobre los artefactos publicados, además de los tests.

## Opcionales y documentación histórica

La skill `janitor-onboarding` enumera Browser, Firecrawl, OpenDesign, LightRAG, n8n, NocoDB, WAHA, auditorías y agentes. Ejecútalos mediante `janitor --run-module janitor_ext.optional_deploy <ruta-del-script>` para mantener el runtime y perfil correctos. Cada capacidad dispone de su `SKILL.md` con requisitos y verificación funcional.

Las guías v5, routers experimentales y snapshots de configuración están en `legacy/`; no son instrucciones de instalación actuales. La guía de mantenimiento del fork detalla los gates de CI y la sincronización con Hermes estable.
