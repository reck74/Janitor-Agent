# Candidatos upstream y evaluación de distro separada

Janitor 1.0 es un fork delgado: todo lo propio vive en zonas fork-only
(`janitor/`, `tests/janitor/`, `apps/desktop-janitor/`, …) y lo que queda
editado sobre el core de Hermes está declarado como *touchpoint* en
[`janitor/overlay.yaml`](../../janitor/overlay.yaml). Cada touchpoint es un
costo recurrente: en cada `chore(sync)` hay que re-aplicarlo o verificarlo.

Este documento lista los touchpoints marcados `upstream_candidate: true` y los
monkey-patches que siguen en `janitor/cli.py`, con la propuesta concreta para
upstream y qué borra Janitor cuando se acepte. El objetivo es llevar los
touchpoints a casi cero; la última sección evalúa qué hacer entonces.

Reglas para proponer:

- Un PR upstream por candidato, redactado para Hermes (sin mencionar Janitor
  como motivación de producto; el caso de uso es "white-label / redistribución").
- Debe pasar el rubric de `AGENTS.md` (sección *Contribution Rubric*): bug real
  reproducido en `main`, o hook con consumidor concreto. Los hooks de branding
  tienen consumidor concreto (esta distro), así que no son *speculative
  infrastructure*.
- Nada de variables `HERMES_*` nuevas para configuración no secreta: los hooks
  van por skin o `config.yaml`.
- Cuando upstream lo acepte: en el siguiente `chore(sync)` se borra la edición,
  se quita el touchpoint de `overlay.yaml` (el test de contrato falla si queda
  un patrón sin archivo) y se actualiza la tabla de estado de abajo.

## 1. Bugs y correcciones (proponer primero)

Son fixes independientes de Janitor; upstream los quiere por el rubric
("fix real bugs, well").

### 1.1 `gateway-cache-refresh` — `await` sobre una función síncrona

- **Síntoma upstream:** `GatewayRunner._refresh_agent_cache_message_count`
  hace `await self._session_db.get_session(session_id)`, pero
  `SessionDB.get_session` es síncrona. El `TypeError` lo traga el
  `except Exception: return`, así que el conteo de mensajes del agente
  cacheado nunca se re-sincroniza.
- **Edición Janitor:** `await asyncio.to_thread(self._session_db.get_session, session_id)`.
- **PR propuesto:** `fix(gateway): run SessionDB.get_session off-loop in cache refresh`,
  con un test que use un `SessionDB` real en un `HERMES_HOME` temporal y
  verifique que el conteo se actualiza (el test actual de Janitor,
  `test:gateway-cache-refresh` en `tests/janitor/test_janitor_overlay_contract.py`,
  sirve de base).
- **Al aceptarse:** se elimina el touchpoint; la invariante `async` de la
  directiva #15 se mantiene en `test_janitor_no_duplicate_methods.py`.

### 1.2 `web-typecheck` — `tsc -p .` no chequea nada

- **Síntoma upstream:** `web/tsconfig.json` tiene `files: []` y referencias de
  proyecto, así que `tsc -p . --noEmit` termina en verde sin compilar ningún
  archivo.
- **Edición Janitor:** `"typecheck": "tsc -b --noEmit"` en `web/package.json`.
- **PR propuesto:** `fix(web): typecheck the referenced projects`. Ojo: al
  activarlo upstream puede aflorar errores de tipos acumulados; el PR debe
  incluir esos arreglos o no lo van a mergear.

### 1.3 `tui-test-timeout` — flake de `cursorDriftRegression.test.ts`

- **Síntoma upstream:** el test recorre ~4k iteraciones de `wrap-ansi` y en
  runners cargados pasa de 4.3 s; el default de vitest es 5 s.
- **Edición Janitor:** `testTimeout: 15000` global en `ui-tui/vitest.config.ts`.
- **PR propuesto:** subir el timeout **solo de ese test** (tercer argumento de
  `it(...)`) en lugar del global; es lo que upstream aceptaría y le basta a
  Janitor.

## 2. Hooks de white-label

Upstream ya tiene la superficie correcta para esto: el skin engine
(`hermes_cli/skin_engine.py` + `ui-tui/src/theme.ts`). La propuesta es que
todo texto de marca salga del skin, con los valores actuales de Hermes como
default. Así ningún usuario de Hermes ve un cambio y la distro solo entrega un
skin.

### 2.1 `tui-branding-hook` — tagline y vendor por skin (TUI)

- **Hoy:** `ui-tui/src/components/branding.tsx` tiene hardcodeados
  `'Nous Research · Messenger of the Digital Gods'` y `' · Nous Research'`.
- **Edición Janitor:** claves opcionales `branding.tagline` y
  `branding.vendor` en `ThemeBrand`/`fromSkin`; sin valor, se usan los
  literales de siempre.
- **PR propuesto:** `feat(tui): skin-driven banner tagline and vendor label`,
  con el test `ui-tui/src/__tests__/brandingSkinTagline.test.ts` y la entrada
  correspondiente en la tabla de skins de la documentación. Es el candidato
  más fácil de aceptar: es puro dato, mismo patrón que `branding.welcome`.

### 2.2 `banner` — nombre de producto en la etiqueta de versión (CLI)

- **Hoy:** `"Hermes Agent v{version} ({date})"` aparece literal en tres
  sitios: `format_banner_version_label()` (`hermes_cli/banner.py`),
  `_build_compact_banner()` (`cli.py`) y `print_fast_version_info()`
  (`hermes_cli/_startup_fast.py`).
- **Edición Janitor:** los tres imprimen `THE JANITOR v{display_version(...)}`,
  y tres tests upstream ajustan la aserción (directiva #12).
- **PR propuesto, en dos pasos:**
  1. `refactor(cli): single version-label helper` — que los tres sitios usen
     una sola función (hoy son tres literales que ya pueden divergir). Sin
     cambio de comportamiento; fácil de mergear.
  2. `feat(skins): branding.product_name for the version label` — el helper
     lee `branding.product_name` del skin (default `Hermes Agent`).
     `_startup_fast.py` no carga el skin engine por diseño (arranque rápido),
     así que ahí el valor debe leerse de forma barata o quedarse en el
     default; hay que acordarlo con upstream antes de escribir código.
- **Al aceptarse:** Janitor pone `product_name: THE JANITOR` en
  `assets/janitor/sentry-janitor.yaml`, desaparecen el touchpoint y la
  directiva #12 deja de exigir editar tests upstream en cada sync.
- **Pendiente propio:** el sufijo `+janitor.N` → `-janitor.N`
  (`janitor/version.py:display_version`) puede quedarse en Janitor: con el
  nombre de producto parametrizado, el helper de Janitor solo formatea la
  versión.

### 2.3 Nombre del programa en `argparse` (monkey-patch)

- **Hoy:** `janitor/cli.py` envuelve `argparse.ArgumentParser.__init__` para
  cambiar `prog="hermes"` por `janitor`. Es el patch más frágil (afecta a
  todo `argparse` del proceso) y lo vigila la directiva #14.
- **PR propuesto:** que el parser raíz de `hermes_cli/_parser.py` (hoy
  `prog="hermes"`) derive `prog` de `os.path.basename(sys.argv[0])` cuando el
  ejecutable no es `hermes` (comportamiento estándar de `argparse` si no se
  fuerza `prog`). No requiere ninguna configuración nueva.
- **Al aceptarse:** se borra el wrapper y su caso en
  `test_janitor_monkeypatch_signatures.py`.

### 2.4 Tips por idioma (monkey-patch)

- **Hoy:** `janitor/cli.py` reemplaza `hermes_cli.tips.TIPS` y
  `get_random_tip` por el corpus en español de `janitor/tips_es.py`.
- **PR propuesto:** `feat(tips): locale-aware tip corpus` — `hermes_cli/tips.py`
  elige el corpus según el locale (o una clave nueva de `config.yaml`, p. ej.
  `display.language`, que hoy no existe en `DEFAULT_CONFIG`) y busca
  `tips_<lang>.py`/YAML; Janitor aporta la traducción al español como primer
  corpus no inglés. Beneficia a cualquier usuario hispanohablante de Hermes.
- **Al aceptarse:** se borran el patch y `janitor/tips_es.py`.

### 2.5 Flujo de `update` con remoto y hooks configurables

- **Hoy:** el patch más grande. `janitor/update_core.py` (~1.3k líneas)
  reimplementa `_cmd_update_impl` de `hermes_cli/update_cmd.py` para usar el
  remoto del fork, el fallback `reset --hard origin/<branch>`, la validación
  post-pull y la migración de `~/.janitor` (directiva #13). Cada sync obliga a
  comparar a mano contra upstream.
- **PR propuesto (orden):**
  1. `fix(update): recover from non-fast-forward pulls` — el fallback de
     `reset --hard` tras `pull --ff-only` fallido, con rollback al SHA previo
     si la validación de sintaxis falla. Es la parte que es un bug también
     para Hermes (la instalación queda atascada sin camino de recuperación).
  2. `feat(update): post-update hook` — punto de extensión por plugin
     (`ctx.register_hook("post_update", ...)` o similar) para que una distro
     ejecute sus migraciones tras el pull. Consumidor concreto:
     `janitor.migrations`.
  El remoto ya lo resuelve git (`origin` apunta al fork en una instalación
  Janitor); no hace falta configuración nueva.
- **Al aceptarse:** `janitor update` pasa a ser un wrapper de pocas líneas que
  imprime el banner y llama a `cmd_update` upstream; `update_core.py` y el
  patch de `cmd_update` se eliminan.

### 2.6 `mcp-dashboard-endpoints`

- **Hoy:** `POST /api/mcp/servers/{name}/discover` y
  `GET /api/mcp/servers/{name}/logs` en `hermes_cli/web_routers/mcp.py` +
  helpers en `hermes_cli/mcp_config.py`, consumidos por el dashboard de
  Janitor.
- **PR propuesto:** `feat(dashboard): MCP tool discovery and per-server logs`,
  junto con los tests `tests/janitor/test_mcp_router_{discover,logs}.py`
  movidos a `tests/hermes_cli/`. Encaja en "expand reach at the edges"
  (dashboard) y no agrega tools al modelo.
- **Plan B si upstream no lo quiere:** mover los endpoints al plugin `janitor`
  si el plugin surface permite registrar routers web; si no, proponer ese
  hook genérico (`ctx.register_web_router`), que es lo que el rubric pide en
  vez de tocar core.

## 3. Lo que no se propone

| Touchpoint | Motivo |
|------------|--------|
| `version`, `packaging` | Identidad de la distro (`+janitor.N`, script `janitor`, entry point del plugin). Siempre serán propios; en una distro separada viven en su propio `pyproject.toml`. |
| `installers` | Instalan desde el fork en `~/.janitor` y exigen Docker/Honcho (directiva #8). |
| `fork-docs`, `fork-ci` | Documentación y CI de la distro. |

## 4. Estado

| Candidato | Tipo | PR upstream | Estado |
|-----------|------|-------------|--------|
| 1.1 gateway-cache-refresh | fix | — | por proponer |
| 1.2 web-typecheck | fix | — | por proponer |
| 1.3 tui-test-timeout | fix | — | por proponer |
| 2.1 tui-branding-hook | hook | — | por proponer |
| 2.2 banner (refactor + product_name) | hook | — | por proponer |
| 2.3 argparse `prog` | hook | — | por proponer |
| 2.4 tips por idioma | feature | — | por proponer |
| 2.5 update (fallback + post_update) | fix + hook | — | por proponer |
| 2.6 MCP discover/logs | feature | — | por proponer |

Actualizar esta tabla con el link al PR y el resultado (aceptado / rechazado /
plan B). Un rechazo no es un fracaso: el touchpoint queda declarado y el gate
de sync lo sigue verificando.

## 5. Evaluación: separar Janitor como paquete o distro

### Opciones

1. **Fork delgado (estado actual, 1.0).** El repo es Hermes + overlay. Cada
   release upstream entra por `upstream-sync.yml` y se valida con
   `scripts/janitor-sync-verify.sh`.
2. **Distro como paquete.** Repo propio `janitor` que depende de
   `hermes-agent` fijado a un tag (`hermes-agent==2026.8.13`, o git URL con
   SHA según la política de pinning) y contiene solo lo que hoy es
   `fork_paths`: `janitor/` (CLI, plugin, migraciones, skills, skin),
   `apps/desktop-janitor/` (overlay que construye el desktop desde el
   `apps/desktop` de Hermes) y los instaladores.
3. **Solo plugin + skills.** Sin CLI ni desktop propios: un plugin pip y un
   skin que el usuario instala sobre Hermes. Pierde la identidad de producto
   (`janitor`, `~/.janitor`, app de escritorio), que es parte del valor para
   los usuarios actuales. Descartado salvo que el producto cambie de rumbo.

### Cuándo migrar a la opción 2

Se cumple cuando **todos** estos criterios son ciertos:

- Los touchpoints de la sección 3 son los únicos que quedan en
  `overlay.yaml` (todos los candidatos aceptados o resueltos por plan B).
- `janitor/cli.py` no monkey-patchea nada de upstream
  (`test_janitor_monkeypatch_signatures.py` sin casos).
- Hermes publica en PyPI (o en tags con SHA estable) un artefacto que incluye
  `ui-tui` compilado y `apps/desktop` consumible por el overlay; hoy la distro
  necesita el árbol fuente completo para construir TUI y desktop.
- `skills.external_dirs` y el plugin entry point (`hermes_agent.plugins`), en
  los que ya se apoya Janitor 1.0, siguen siendo superficie documentada de
  plugins (ver *Native plugin compatibility policy* en `AGENTS.md`).

### Qué se gana y qué cuesta

| | Fork delgado | Distro separada |
|--|--------------|-----------------|
| Actualizar Hermes | merge de tag + verify (automático, puede tener conflictos en touchpoints) | subir el pin + verify; sin conflictos de merge |
| Divergencias invisibles | detectadas por `janitor.overlay check` | imposibles: no hay copia del core |
| Parchear un bug del core urgente | editar en el árbol (nuevo touchpoint) | esperar a upstream o fijar un fork-SHA temporal |
| Tamaño del repo / CI | repo completo de Hermes; el gate corre solo `tests/janitor/` | solo código Janitor |
| Desktop / TUI | se construyen del árbol | dependen de que upstream publique artefactos (criterio 3) |

### Migración de usuarios (cuando toque)

El layout de `~/.janitor` no cambia: `skills.external_dirs` y
`plugins.enabled` ya apuntan al paquete `janitor`, no a rutas del fork. El
cambio para el usuario sería de método de instalación (`pip`/`uv tool` en vez
de checkout git), y debe venir con su `scripts/migrate-*.sh` con backup
(directiva #10) que convierta el checkout en `~/.janitor/janitor-core` en una
instalación de paquete sin tocar `config.yaml`, `SOUL.md`, `skills/`,
`state.db` ni los volúmenes `janitor-*`.

### Conclusión actual

Quedarse en el fork delgado. Con 11 touchpoints (6 candidatos a upstream) y
tres monkey-patches, separar hoy significaría vendorizar esas ediciones en
otro sitio sin reducir trabajo. Revisar esta evaluación cada vez que se
acepte un candidato; el disparador concreto es que la tabla de la sección 4
quede completa y `overlay.yaml` solo contenga los touchpoints de la sección 3.
