# Guía de Merge Upstream para Janitor

Janitor es un **fork delgado** de [`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent):
el core de Hermes se mantiene casi idéntico a upstream y todo lo propio de
Janitor vive en zonas exclusivas del fork que un merge nunca toca. Esta guía
describe cómo traer una release nueva de upstream. Lo que antes eran
checklists con `grep` ahora es un solo script:

```bash
scripts/janitor-sync-verify.sh            # gate completo post-merge
scripts/janitor-sync-verify.sh --help     # opciones (--base, --skip-tui, --skip-desktop)
```

---

## 1. Dónde vive Janitor

| Zona | Contenido | Merge |
|------|-----------|-------|
| `janitor/` | Lanzador (`janitor/cli.py`), update (`update_core.py`), versión, tips, migraciones de `~/.janitor`, plugin, servicios, inventario `overlay.yaml` | fork-only |
| `janitor/skills/{core,services,agents,integrations}/` | Skills Janitor, cargadas vía `skills.external_dirs` | fork-only |
| `assets/janitor/` | Config, SOUL, skin `sentry-janitor`, assets de Telegram | fork-only |
| `apps/desktop-janitor/` | Overlay de build del desktop (appId, nombre, iconos) | fork-only |
| `tests/janitor/` | Toda la suite Janitor | fork-only |
| Touchpoints | Ediciones mínimas en archivos upstream (versión, banner, …) | ver `janitor/overlay.yaml` |

`janitor/overlay.yaml` es la fuente de verdad: cada divergencia respecto a
upstream es un `fork_path` o un touchpoint declarado (con `why`, cómo se
verifica y cómo resolver un conflicto: `merge: ours` o `merge: reapply`).
`python -m janitor.overlay check` falla ante cualquier divergencia no
declarada, así que un merge ya no puede dejar código zombie en silencio.

**Regla de oro (directiva #1): zero-renaming.** Nunca buscar-y-reemplazar
`hermes` en el core.

---

## 2. Flujo automático

`.github/workflows/upstream-sync.yml` (semanal o manual):

1. Toma el tag de release upstream más reciente (`v20*`), nunca `upstream/main`.
2. `git merge <tag>` en una rama `upstream-sync-<tag>`. Si hay conflictos, abre
   un issue con la lista y se detiene.
3. Poda los workflows de upstream (conserva `tests.yml`, `janitor-ci.yml`,
   `upstream-sync.yml`, `janitor-desktop-release.yml`).
4. Actualiza `upstream.base` en `janitor/overlay.yaml` al commit del tag.
5. Corre `scripts/janitor-sync-verify.sh --skip-tui` y abre el PR con el
   resultado. El TUI gate corre en el CI del propio PR.

Al mergear el PR (mensaje `chore(sync):` o rama `upstream-sync-*`), el job
`upstream-sync-verify` de `tests.yml` corre la suite completa de upstream.

---

## 3. Flujo manual (con conflictos)

```bash
git remote add upstream https://github.com/NousResearch/hermes-agent.git 2>/dev/null || true
git fetch upstream --tags
TAG=v2026.X.Y
git checkout -b upstream-sync-$TAG origin/main
git merge $TAG --no-edit          # 3-way; prohibido -X theirs / -X ours global
```

Resolución por archivo:

- **Touchpoints** (`janitor/overlay.yaml`): `merge: ours` conserva la versión
  del fork; `merge: reapply` toma upstream y vuelve a aplicar lo descrito en
  `why`.
- **Workflows**: los de upstream se borran; los cuatro de Janitor se conservan.
- **Archivos upstream que el fork no declara**: siempre la versión de upstream.
- **Tests upstream que asertan el banner** (directiva #12): cambiar
  `Hermes Agent` por `THE JANITOR` con un comentario que apunte a la directiva.

Después del merge:

```bash
sed -i "s|^  base: .*|  base: $(git rev-parse $TAG^{commit})|" janitor/overlay.yaml
scripts/janitor-sync-verify.sh
```

---

## 4. Qué verifica `janitor-sync-verify.sh`

| Paso | Falla cuando… | Arreglo |
|------|---------------|---------|
| Marcadores de conflicto | quedan `<<<<<<<` / `>>>>>>>` en archivos que difieren de upstream | resolver |
| `python -m janitor.overlay check` | un archivo difiere de upstream sin estar declarado | volver a upstream, o declararlo como touchpoint con su `why` |
| `tests/janitor/` | contrato de touchpoints (versión `+janitor.N`, banner, packaging, cache refresh, endpoints MCP), firmas de monkey-patch (#14), definiciones duplicadas (#15), preservación de `~/.janitor`, plugin, servicios, skills, skin | actualizar el código Janitor, **nunca** debilitar el test |
| Overlay desktop | un asset destino ya no existe upstream, o el `productName` empaquetado deja de coincidir (rompería el `userData` de los usuarios) | ajustar `apps/desktop-janitor/` |
| TUI (`npm run build` + `npm test`, directiva #7) | el hook de branding del skin o el TUI no compila | re-aplicar el touchpoint `tui-branding-hook` |

**Directiva #14.** Si upstream añade parámetros a una función que
`janitor/cli.py` monkey-patchea, actualizar la firma del wrapper.

**Directiva #15.** Si fork y upstream añadieron el mismo método o función,
conservar la definición correcta (normalmente la del fork) y borrar la otra.

---

## 5. Usuarios existentes

`janitor update` trae el código nuevo. En el siguiente arranque, `janitor`
migra `~/.janitor` al layout vigente (`~/.janitor/.layout_version`), con
backup previo en `~/.janitor/.backup/`. Manual: `bash scripts/migrate-janitor-v1.sh [--dry-run]`.
Cada reestructuración nueva añade una migración en `janitor/migrations/`
(directiva #10).

---

## 6. Troubleshooting

- **El TUI no compila tras el merge**: recompilar `@hermes/ink` primero
  (`npm run build --prefix ui-tui/packages/hermes-ink`), luego `npm run build`.
- **Vitest: `Cannot find module ./dist/entry-exports.js`**: falta el build de
  `hermes-ink` (`npm run build:ink` en `ui-tui`).
- **`overlay check` lista cientos de archivos**: `upstream.base` sigue
  apuntando a la release anterior; actualizarlo al tag mergeado.
