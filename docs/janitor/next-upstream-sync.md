# Próximo sync upstream: Hermes v2026.9.24 → v0.22.5

Verificación del 2 de noviembre de 2026 (America/Bogota). Janitor
(`0.21.5+janitor.1`) está en `main` sobre Hermes **v2026.9.24**. Esa sigue
siendo la última release con tag calver, y el workflow de sync solo miraba
`v20*`, así que reportaba "ya estamos al día". Upstream cambió el esquema:
las releases estables publicadas ahora son `v0.x.y`. La última publicada es
**v0.22.5**. Este archivo es el punto de partida para ese sync. El
procedimiento general está en [`MERGE_GUIDE.md`](../../MERGE_GUIDE.md).

No se mergeó nada en esta verificación. Un `git merge v0.22.5 --no-commit`
se abortó después de listar los conflictos.

## Datos

| | Valor |
|--|-------|
| Base actual (`upstream.base`) | `f97608f178d1ffeca59860195ab7da295f7c8e5f` (v2026.9.24, 24 sep 2026, 5:08 America/Bogota) |
| Objetivo | **v0.22.5** → `bf0203a794a07aac3ff764972ab9087baa4e4f4e` (commit 22 oct 2026, 9:24 p.m. America/Bogota; release de GitHub 23 oct 2026, 12:28 a.m.) |
| Releases intermedias publicadas | v0.21.6, v0.21.7, v0.22.0 ("The Threshold Release"), v0.22.1, v0.22.2, v0.22.3, v0.22.4 |
| Commits base → objetivo | 16.231 |
| Diff | 13.049 archivos, +1.278.488 / −338.380 |
| `upstream/main` por delante de v0.22.5 | 3.397 commits (punta del 2 nov 2026, 8:35 a.m. America/Bogota). No es release: no se mergea |
| Canary más nuevo | `v0.22.5+canary.20261102T065013Z`, 3.359 commits después de v0.22.5. Tampoco se mergea |
| Versión en el objetivo | `pyproject.toml` y el desktop dicen `0.0.0`. La identidad real sale de `install-stamp.json` / `hermes_cli.version_info.get_version_info()` (`baseVersion` del stamp, o git). `__release_date__` sigue en `"2026.9.24"` |
| Conflicto de un merge 3-way | **45 archivos**. 33 son workflows que el fork ya borró (modify/delete). 12 son contenido |

No hay un escalón más chico. v0.21.6, la primera release después de la base,
ya trae `version = "0.0.0"`, `__version__` perezoso y la desaparición de
`hermes_cli.tips.TIPS` (8.342 archivos). El corte es v0.22.5 o nada.

## Por qué el bot no lo veía

`upstream-sync.yml` hacía `git tag -l 'v20*' --sort=-v:refname`. El tag más
nuevo con ese glob sigue siendo v2026.9.24, que ya es ancestro de
`origin/main`, y el job salía en verde sin abrir PR. El selector ahora usa
el mismo patrón que `STABLE_TAG_RE` de upstream (major ≤ 999), ordenado por
fecha del tag, y solo tags que existen en `NousResearch/hermes-agent`. El
tag `v1.0.0` de este fork entra en el patrón pero no está en upstream.

## Merge de prueba

```text
45 conflicts
  33  modify/delete  .github/workflows/*   (el fork los podó; upstream los siguió editando)
  12  content        ver tabla
```

Auto-merge limpio, revisar igual: `AGENTS.md` (el bloque Janitor quedó
primero), `hermes_cli/mcp_config.py`, `hermes_cli/web_routers/mcp.py` (los
endpoints `discover` y `logs` sobrevivieron), `.env.example`,
`tests/hermes_cli/test_startup_fast_guards.py`. Ese test de banner conservó
`THE JANITOR v` en las aserciones viejas y **añadió** un `"Hermes Agent v"`
nuevo (~línea 230 del merge). Directiva #12: hay que cambiarlo en el mismo
commit y dejar el comentario.

## Conflictos de contenido

| Archivo | Resolución |
|---------|------------|
| `.github/workflows/tests.yml` | `merge: ours` para el job `test` (suite `tests/janitor/`, ubuntu-latest). Portar al job de sync/e2e lo que upstream cambió en la instalación: **Python 3.14**, `uv sync --locked --python 3.14 --extra all --group dev` (`dev` dejó de ser extra y pasó a `[dependency-groups]`), extras `anthropic mistral fal modal daytona parallel-web` (ya no está `bedrock` en el job e2e), Node 26, pin de `uv` 0.12.13. No copiar los runners `blacksmith-*` ni `useblacksmith/checkout`: este fork no los tiene. Lo mismo en `janitor-ci.yml`, que hoy sigue en Python 3.11 y `--extra dev` |
| `pyproject.toml` | Tomar upstream. Re-aplicar script `janitor`, entry point del plugin, `packages.find`, package data y py-modules pre-1.0. **No** volver a poner `0.21.5+janitor.N` en `project.version`: upstream lo fijó en `0.0.0` a propósito |
| `uv.lock` | Tomar el de upstream. El paquete `hermes-agent` ya dice `version = "0.0.0"`. No regenerar el lock con otro `uv` |
| `hermes_cli/__init__.py` | Tomar upstream (`__getattr__` lee el stamp). El segmento `+janitor.N` tiene que vivir en esa lectura, no en una asignación de módulo: los tests de `tests/janitor/` exigen `re.fullmatch(r"\d+\.\d+\.\d+\+janitor\.\d+", hermes_cli.__version__)` y que coincida con lo que el banner muestra. Diseñarlo antes de cerrar el sync; un literal al lado del `__getattr__` no gana |
| `hermes_cli/banner.py`, `_startup_fast.py`, `cli_render.py` | Tomar upstream y re-aplicar `THE JANITOR v…`. `format_banner_version_label()` sigue, pero ahora usa `get_version_info().derived_version` |
| `ui-tui/src/components/branding.tsx` | Tres hunks. Re-aplicar `branding.tagline` / `branding.vendor`. Siguen los literales `Nous Research` |
| `web/package.json` | Un hunk: upstream ya tiene `tsc -b . --noEmit`. El touchpoint `web-typecheck` (`tsc -b --noEmit`) quedó redundante; tomar upstream y retirar el touchpoint si el check sigue cubierto |
| `scripts/install.ps1` | `merge: ours` (+1390/−4908 en upstream). Revisar qué arregló upstream y portar lo que aplique; no reemplazar el instalador de Janitor |
| `.gitignore` | Unir los dos bloques: la higiene Janitor (`.sisyphus/`, `.omo/`, `apps/desktop/release/`) y lo nuevo de upstream (`.build/`, `.cache/`, `/pm/.lock.json.lock`, `apps/desktop/.dist-build*`) |
| `README.md` | Conservar el README del fork e incorporar solo lo que upstream cambió y siga siendo cierto |

Los 33 workflows en modify/delete se borran otra vez con el mismo `find`
del workflow de sync. `tests.yml` no entra en ese `find`.

## Lo que el merge no marca y el verify sí va a fallar

- **Tips.** `hermes_cli.tips.TIPS` ya no existe; el catálogo son claves i18n
  (`tip_keys()`, `get_random_tip(exclude_recent: int = 0)`). La firma de
  `get_janitor_tip` sigue siendo compatible. `janitor/cli.py` asigna
  `TIPS = JANITOR_TIPS`, y `tests/janitor/test_janitor_monkeypatch_signatures.py`
  hace `type(hermes_tips.TIPS)`. Hay que apuntar el parche al catálogo nuevo
  y actualizar el test al contrato nuevo, sin quitar la comprobación.
- **Hash de skills.** `tools.skills_sync._dir_hash` pasó a `dir_hash` público,
  misma firma (`directory, *, include_runtime_cache: bool = False`).
  `janitor/migrations/v1.py` tiene su propia copia; el test que compara
  contra el hash de upstream hay que apuntarlo a `dir_hash`.
- **Desktop overlay.** `apps/desktop/public/nous-girl.jpg` ya no existe.
  Upstream tiene `nous-girl.png` y `nous-girl-dark.png`. Siguen
  `public/apple-touch-icon.png` y `public/ds-assets/filler-bg0.jpg`.
  `productName` del `package.json` sigue siendo `"Hermes"` (el `userData` no
  cambia). `apps/desktop-janitor/scripts/build.mjs` copia el mark encima de
  `nous-girl.jpg`; el check del overlay falla si el destino no existe.
  Los iconos de build se movieron a `apps/desktop/assets/icon.png`.
- **Gateway cache.** El touchpoint ya está retirado. En v0.22.5
  `_refresh_agent_cache_message_count` sigue en `gateway/run_agent_cache.py`
  y hace `await self._session_db.get_session(...)`. No reintroducir
  `asyncio.to_thread`.
- **`cmd_update(args)`** sigue con un solo parámetro. El parche de Janitor
  no necesita firma nueva. El cuerpo de upstream creció (handoff, lock,
  stamp): `janitor/update_core.py` no se reemplaza por eso, pero hay que
  leer qué preflight nuevo debe respetar el core de Janitor.
- **Parser.** `hermes_cli/_parser.py` y `hermes_cli/console_engine.py` siguen
  con `prog="hermes"`.
- **`skills.external_dirs`** y **`pre_gateway_dispatch`** siguen.

## Cómo arrancar el sync

Manual, en una rama `upstream-sync-v0.22.5`:

```bash
git fetch upstream --tags
git checkout -b upstream-sync-v0.22.5 origin/main
git merge v0.22.5 --no-edit -m "chore(sync): merge upstream v0.22.5"
```

3-way, nunca `-X theirs` / `-X ours` global. Después: podar workflows,
resolver la tabla de arriba, decidir el segmento `+janitor.N` sobre el
stamp, actualizar `upstream.base` a `bf0203a794a07aac3ff764972ab9087baa4e4f4e`
y correr `scripts/janitor-sync-verify.sh` completo.

El merge commit lleva mensaje `chore(sync): merge upstream v0.22.5` y los
arreglos van en commits `fix(sync): …`, para que `upstream-sync-verify`
corra la suite de upstream al llegar a `main`.
