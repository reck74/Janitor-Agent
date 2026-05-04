---
name: tui-compilation
description: Valida que los cambios en el TUI de Janitor compilan correctamente y pasan todos los tests antes de commit. Ejecuta npm run build + npm test (vitest) como gate obligatorio del pipeline CI.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [tui, compilation, ci-gate, typescript]
    category: devops
---

# tui-compilation Skill

Valida que los cambios en el TUI de Janitor (ui-tui/) compilan y pasan los tests antes de cualquier commit.

## Ejecutar como Gate CI

```bash
cd ui-tui
npm install
npm run build
npm test
```

## Criterios de aprobación

- `npm run build` debe completar con exit code 0
- `npm test` (vitest) debe pasar con 0 tests fallidos
- El build genera archivos en `ui-tui/dist/` sin errores de TypeScript

## Integración en pipeline

Este skill se ejecuta automáticamente como gate obligatorio antes de commit cuando se modifica cualquier archivo bajo `ui-tui/src/`. Puede también invocarse manualmente:

```bash
opencode run-agent .opencode/skills/tui-compilation/SKILL.md
```

## Notas

- No ejecutar en paralelo con otros procesos de build
- Requiere Node.js 22+ y npm install previo
- Si `npm run build` falla, no hacer commit hasta resolver errores de TypeScript