# Próximo sync upstream: Hermes v2026.8.13 → v2026.9.24

Traspaso para una sesión nueva. Janitor 1.0 (`0.20.1+janitor.2`) está en
`main` sobre Hermes **v2026.8.13**; upstream publicó 11 releases desde
entonces. Este documento junta lo que ya se sabe del salto para que el sync se
haga sin redescubrirlo. El procedimiento general está en
[`MERGE_GUIDE.md`](../../MERGE_GUIDE.md); aquí solo va lo específico de este
salto. Al terminar el sync, borrar este archivo o reescribirlo para el
siguiente.

## Datos

| | Valor |
|--|-------|
| Base actual (`upstream.base` en `janitor/overlay.yaml`) | `f80f453ae0679347e38abc917c7f94f717bf96c5` (v2026.8.13) |
| Objetivo | `v2026.9.24` → commit `f97608f178d1ffeca59860195ab7da295f7c8e5f` |
| Releases intermedias | v2026.8.16, .8.16.2, .8.18, .8.19, .8.27, .8.31, .9.7, .9.11, .9.14, .9.21 |
| Versión upstream en el objetivo | `0.21.5` (`__release_date__ = "2026.9.24"`) |
| Versión Janitor resultante | `0.21.5+janitor.1`; entrada de CHANGELOG `1.0.1 — 0.21.5+janitor.1 (Hermes v2026.9.24)` |
| Tamaño del salto | ~12.400 archivos distintos entre base y objetivo |

Si para cuando se haga el sync hay un tag más nuevo, usar ese: el análisis de
abajo sigue siendo el punto de partida, pero hay que repetir la sección
"Touchpoints" contra el tag nuevo.

## Cómo arrancar

Dos caminos; el manual es el recomendado para este salto.

1. **Automático:** Actions → "🔄 Upstream Sync" → *Run workflow*
   (`workflow_dispatch`). Con este tamaño de salto lo esperable es que
   encuentre conflictos en los touchpoints de abajo y abra un issue en vez de
   un PR. Sirve para confirmar la lista de conflictos, no para resolverlos.
2. **Manual (MERGE_GUIDE §3):** rama `upstream-sync-v2026.9.24` desde
   `origin/main`, `git merge v2026.9.24 --no-edit` (3-way, nunca `-X theirs`
   / `-X ours` global), resolver por archivo con la tabla de abajo, podar los
   workflows de upstream, actualizar `upstream.base` y correr
   `scripts/janitor-sync-verify.sh` (completo, con TUI y desktop).

El merge debe quedar como merge commit con mensaje `chore(sync): merge
upstream v2026.9.24` y los arreglos posteriores en commits `fix(sync): …`,
para que `tests.yml :: upstream-sync-verify` corra la suite completa de
upstream al llegar a `main`.

## Touchpoints: qué cambió upstream y qué hacer

Comparación de cada archivo declarado en `janitor/overlay.yaml` entre la base y
el objetivo.

| Touchpoint | Archivo | Upstream | Acción |
|------------|---------|----------|--------|
| version | `pyproject.toml`, `hermes_cli/__init__.py` | cambiados (0.21.5) | tomar upstream, poner `0.21.5+janitor.1` |
| version / packaging | `uv.lock` | cambiado | tomar el de upstream y editar **solo** la línea de versión de `hermes-agent`; `uv lock --check` debe pasar. No regenerar con otra versión de `uv` (sube `revision` y reformatea todo) |
| packaging | `pyproject.toml` | +287/−53 | re-aplicar: script `janitor = "janitor.cli:main"`, entry point `[project.entry-points."hermes_agent.plugins"] janitor = "janitor.plugin"`, `janitor`/`janitor.*` en `packages.find.include`, package data `janitor = ["overlay.yaml", "skills/**/*"]`, py-modules alias pre-1.0 (`janitor_cli`, `janitor_update_bootstrap`, `janitor_update_core`, `janitor_version`). Ver `test:packaging` |
| banner | `hermes_cli/banner.py` | reescrito en parte | `format_banner_version_label()` sigue existiendo; re-aplicar `THE JANITOR v{display_version(VERSION)}` |
| banner | `hermes_cli/_startup_fast.py` | cambiado | `print_fast_version_info` ahora recibe `*, check_updates`; re-aplicar el literal |
| banner | `cli.py` | **−18k líneas** | `_build_compact_banner` se movió a **`hermes_cli/cli_render.py`**. Tomar `cli.py` de upstream completo y re-aplicar el literal en `cli_render.py`. En `overlay.yaml`, reemplazar `cli.py` por `hermes_cli/cli_render.py` en `files` |
| banner | `tests/hermes_cli/test_startup_fast_guards.py` | cambiado | las aserciones `"Hermes Agent v"` (hoy en las líneas ~69 y ~119) pasan a `THE JANITOR v` (directiva #12) |
| banner | `tests/hermes_cli/test_banner.py`, `test_kanban_db.py` | cambiados | tomar upstream y re-aplicar solo las aserciones de banner |
| gateway-cache-refresh | `gateway/run.py` | **−27k líneas** | el método se movió a **`gateway/run_agent_cache.py`** (`_refresh_agent_cache_message_count`, ~línea 567) y **upstream todavía tiene el bug** (`await self._session_db.get_session(...)` sobre una función síncrona). Tomar `run.py` de upstream y re-aplicar `asyncio.to_thread` en `run_agent_cache.py`; actualizar `files` en `overlay.yaml` |
| mcp-dashboard-endpoints | `hermes_cli/mcp_config.py`, `hermes_cli/web_routers/mcp.py` | ~600 líneas cambiadas en cada uno | upstream **no** agregó `discover`/`logs`. Tomar upstream y re-aplicar los dos endpoints y sus helpers; los tests son `tests/janitor/test_mcp_router_{discover,logs}.py` |
| web-typecheck | `web/package.json` | +4 líneas, sigue con `tsc -p . --noEmit` | re-aplicar `tsc -b --noEmit`; si aparecen errores de tipos nuevos de upstream, arreglarlos o documentarlos antes de cerrar |
| tui-branding-hook | `ui-tui/src/theme.ts`, `ui-tui/src/components/branding.tsx` | cambiados; siguen los literales `TAG_FULL` / `Nous Research` | re-aplicar `branding.tagline` / `branding.vendor` |
| tui-test-timeout | `ui-tui/vitest.config.ts` | sin cambios | nada |
| installers | `scripts/install.ps1` | +925/−230 | `merge: ours`, pero revisar qué arregló upstream y portar lo que aplique a Janitor |
| installers | `scripts/bootstrap.sh` | solo existe en el fork | nada |
| fork-docs | `AGENTS.md`, `.env.example`, `.gitignore` | cambiados | `merge: ours` para el bloque Janitor; incorporar las secciones nuevas de upstream debajo del bloque Janitor de `AGENTS.md` |
| fork-docs | `README.md`, `CHANGELOG.md` | sin cambios / solo fork | nada (más la entrada nueva de CHANGELOG) |
| fork-ci | `.github/workflows/*.yml` | — | podar todo lo de upstream salvo `tests.yml`, `upstream-sync.yml`, `janitor-ci.yml`, `janitor-desktop-release.yml` (mismo `find` que `upstream-sync.yml`). Esto borra también los workflows upstream que hoy siguen en `main` (lint, tests-os, …): es lo previsto |

## Dependencias de la capa Janitor (comprobadas en v2026.9.24)

Todas siguen existiendo; aun así, el verify las cubre:

- `hermes_cli/_parser.py` sigue con `prog="hermes"` (patch de argparse).
  Hay un segundo parser nuevo en `hermes_cli/console_engine.py` con
  `prog="hermes"`; revisar si el patch de `janitor/cli.py` lo cubre o si hay
  que ampliarlo.
- `hermes_cli.main.cmd_update` y `hermes_cli.tips.TIPS` / `get_random_tip`
  existen; la firma de `get_random_tip(exclude_recent: int = 0)` no cambió.
  `test_janitor_monkeypatch_signatures.py` (directiva #14) lo confirma tras
  el merge.
- `tools/skills_sync._dir_hash` ahora acepta
  `*, include_runtime_cache: bool = False`. `janitor/migrations/v1.dir_hash`
  debe seguir dando el mismo hash que el default; lo verifica
  `test_manifest_hash_matches_bundled_sync`.
- `skills.external_dirs`, el grupo de entry points `hermes_agent.plugins` y
  el hook `pre_gateway_dispatch` existen.
- Desktop: `apps/desktop/package.json` mantiene `productName: "Hermes"`
  (el `userData` de los usuarios no cambia). Los destinos del overlay
  (`public/apple-touch-icon.png`, `public/nous-girl.jpg`,
  `public/ds-assets/filler-bg0.jpg`) existen; `assets/janitor-icon.png` lo
  crea el overlay. `build.icon` upstream es `assets/icon` y
  `artifactName` `Hermes-…`; los overrides de
  `electron-builder.janitor.json` los siguen reemplazando.

## Antes de dar el sync por terminado

1. `scripts/janitor-sync-verify.sh` (sin `--skip-*`) en verde.
2. `uv lock --check` en verde.
3. Prueba real del launcher contra una copia de un `~/.janitor` existente:
   `JANITOR_HOME=/tmp/janitor-copy janitor skills list` y `janitor sessions list`.
   Si upstream cambió el esquema de config, su migración corre sola; si el
   layout de `~/.janitor` que define Janitor cambia, hace falta
   `janitor/migrations/v2.py` + `scripts/migrate-janitor-v2.sh` (directiva #10).
4. Actualizar `docs/janitor/upstream-candidates.md` (el fix del gateway ahora
   apunta a `gateway/run_agent_cache.py`) y borrar este archivo.
5. PR → merge en `main` → tag `v1.0.1` sobre `main` (dispara el release del
   AppImage).

## Prompt para la sesión nueva

> Sincroniza Janitor con Hermes upstream v2026.9.24 (o el último tag `v20*`
> si hay uno más nuevo). Sigue `docs/janitor/next-upstream-sync.md` y
> `MERGE_GUIDE.md`: merge 3-way en una rama `upstream-sync-<tag>`, resolver
> cada touchpoint según la tabla, actualizar `janitor/overlay.yaml`, versión
> `0.21.5+janitor.1` con su entrada de CHANGELOG, y dejar
> `scripts/janitor-sync-verify.sh` completo en verde. Abre un PR con el
> resultado; no mergees ni etiquetes sin preguntarme.
