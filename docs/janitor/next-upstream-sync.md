# Próximo sync upstream (después de Hermes v2026.9.24)

Traspaso para la sesión que haga el siguiente sync. El procedimiento general
está en [`MERGE_GUIDE.md`](../../MERGE_GUIDE.md); aquí va solo el estado y lo
aprendido en el salto v2026.8.13 → v2026.9.24 que todavía aplica.

## Estado (1 nov 2026)

| | Valor |
|--|-------|
| Base (`upstream.base` en `janitor/overlay.yaml`) | `f97608f178d1ffeca59860195ab7da295f7c8e5f` (v2026.9.24) |
| Versión Janitor en `main` | `0.21.5+janitor.1`, entrada de CHANGELOG `1.0.1` |
| Tag más nuevo de upstream | v2026.9.24 (no hay release más nuevo todavía) |
| Sync anterior | PR #84 (sync) y PR #87 (arreglo de `janitor update`) |

Pendiente del sync anterior: etiquetar `v1.0.1` sobre `main` cuando el
mantenedor lo apruebe (dispara el release del AppImage).

## Fallos de upstream que quedaron visibles

`upstream-sync-verify` dejó dos fallos que también ocurren en upstream puro
(regla de `MERGE_GUIDE.md`: no se deseleccionan). Si siguen fallando en el
próximo sync, no son de Janitor:

- `tests/plugins/model_providers/test_commandcode_profile.py::TestCommandCodeFetchModelsPickerContract::test_resolve_provider_full`
  (el archivo define dos clases con ese nombre; la segunda pisa a la primera)
- `tests/hermes_cli/test_session_recovery_lost_and_found.py::test_unreadable_schema_without_cli_names_the_sqlite3_requirement`

La lista `deselect` de `tests.yml` solo tiene los cuatro tests de descubrimiento
de plugins que cuentan el plugin `janitor` por entry point. Si upstream los
renombra, el job falla con "not found": actualizar los ids, no ampliar la lista.

## Helpers de upstream de los que depende la capa Janitor

`janitor/update_core.py` carga sus helpers en forma perezosa y, si un nombre
desaparece, cae a un fallback **sin fallar**. Un rename de upstream no rompe
ningún test: degrada `janitor update` en silencio. En cada sync, confirmar que
siguen existiendo con la misma firma:

| Helper | Dónde | Para qué |
|--------|-------|----------|
| `_discard_lockfile_churn`, `_normalize_managed_eol` | `hermes_cli.update_cmd` | descartar la reescritura de `package-lock.json` / CRLF antes del stash. Sin ellos vuelve el error de restore del PR #87 |
| `_stash_local_changes_if_needed`, `_restore_stashed_changes` | `hermes_cli.update_cmd` | autostash |
| `_update_node_dependencies`, `_resolve_node_runtime_npm`, `_run_npm_install_deterministic` | `hermes_cli.update_cmd` / `hermes_cli.main` | Node del update sin tocar el lockfile |
| `_tui_need_npm_install`, `_workspace_root` | `hermes_cli.main_tui_launch` | reparar `ui-tui/node_modules` solo si hace falta |
| `ensure_uv`, `update_managed_uv` | `hermes_cli.managed_uv` | uv gestionado en `~/.janitor/bin` |
| `require_readable_config_before_write` | `hermes_cli.config` | lectura fail-closed de `config.yaml` en la migración v1 |

Comprobación rápida tras el merge:

```bash
python -c "
import janitor.update_core as j; j._ensure_loaded()
missing = [n for n in ('_discard_lockfile_churn', '_normalize_managed_eol',
    '_stash_local_changes_if_needed', '_restore_stashed_changes',
    '_update_node_dependencies', '_resolve_node_runtime_npm',
    '_run_npm_install_deterministic') if getattr(j, n) is None]
from hermes_cli.main_tui_launch import _tui_need_npm_install, _workspace_root
from hermes_cli.managed_uv import ensure_uv, update_managed_uv
from hermes_cli.config import require_readable_config_before_write
print('faltan:', missing or 'ninguno')"
```

## Recordatorios del salto anterior

- Los tests de upstream que vigilan código nuevo (`test_config_read_guard`,
  `test_managed_runtime_resolution`, …) también escanean `janitor/`. Si
  fallan por código Janitor, se arregla el código Janitor para que use el
  helper de upstream; no se deselecciona el test.
- El update que descarga una versión lo ejecuta el código de la versión
  anterior. Un arreglo en `janitor/update_core.py` solo actúa a partir del
  segundo `janitor update`; si el primero puede fallar, documentarlo en la
  sección "Upgrading" del CHANGELOG (ver 1.0.1).
- `e2e` y `upstream-sync-verify` no corren en PRs: lanzar **Tests** a mano
  sobre la rama del sync antes de mergear.

## Prompt para la sesión nueva

> Sincroniza Janitor con el último tag `v20*` de Hermes upstream posterior a
> v2026.9.24. Sigue `MERGE_GUIDE.md` y `docs/janitor/next-upstream-sync.md`:
> merge 3-way en una rama `upstream-sync-<tag>`, re-aplicar los touchpoints de
> `janitor/overlay.yaml`, comprobar los helpers de la tabla, nueva versión con
> su entrada de CHANGELOG y `scripts/janitor-sync-verify.sh` completo en verde.
> Abre un PR con el resultado; no mergees ni etiquetes sin preguntarme.
