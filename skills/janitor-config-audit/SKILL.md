---
name: janitor-config-audit
description: Preview config drift and merge with a private backup.
version: 2.0.0
author: janitor
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [config, audit, drift, janitor, maintenance]
---

# Auditoría de configuración Janitor

Compara el perfil activo con el overlay Janitor vigente y la persona sugerida. Primero genera un preview. Las claves, tokens, contraseñas y credenciales en URLs se redactan; YAML inválido se rechaza sin reemplazar el archivo activo.

Desde la raíz del repositorio preparado por PM:

```bash
janitor --run-module janitor_ext.optional_deploy skills/janitor-config-audit/scripts/audit.sh config
janitor --run-module janitor_ext.optional_deploy skills/janitor-config-audit/scripts/audit.sh soul
```

Añade `--apply` para combinar defaults faltantes de configuración y conservar todas las elecciones existentes. Crea un backup privado antes de modificar. Un segundo backup recibe un nombre único y no reemplaza el anterior.

Para `SOUL.md`, `--apply` conserva la persona activa y escribe una propuesta `.proposed`; el usuario revisa e integra el texto. Los valores diferentes o extras del perfil se muestran como diferencias, pero no se borran ni se sobrescriben al aplicar defaults.

El script busca assets en `JANITOR_HOME/janitor-core/assets/janitor/`; usa `config-overlay.yaml`. Conserva compatibilidad con assets de instalaciones anteriores que sólo tengan `config.yaml`. Para una ruta de checkout distinta, define `JANITOR_CORE_ROOT` y ejecuta con el `JANITOR_HOME` del perfil correspondiente.

Los backups `.bak` permiten recuperar la versión previa. No copie el snapshot histórico `legacy/config/config-pre-1.0.yaml` como configuración nueva.
