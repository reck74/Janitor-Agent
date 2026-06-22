# Guía de Merge Upstream para Janitor

> Este documento describe el flujo de trabajo para sincronizar Janitor con los cambios del repositorio upstream `NousResearch/hermes-agent`, preservando la identidad y las extensiones propias de Janitor.

---

## 1. Principios del Fork (Janitor vs. Upstream)

### 1.1 Regla de oro: Zero-Renaming

**NUNCA** hagas buscar-y-reemplazo global de la palabra `hermes` en el core. El motor subyacente se mantiene intacto para garantizar que `git pull upstream main` funcione sin conflictos destructivos.

- ✅ **Sí**: Extender, envolver, inyectar comportamiento vía patrones wrapper.
- ❌ **No**: Renombrar clases, funciones o archivos core de Hermes.

### 1.2 Líneas divisorias

| Capa | Upstream (Hermes) | Janitor (Fork) |
|------|-------------------|----------------|
| **Core** | `cli.py`, `run_agent.py`, `gateway/run.py`, `model_tools.py` | **Inmutable** — solo se mergea, no se edita |
| **CLI wrapper** | `cli.py` (base) | `janitor_cli.py` (extensiones heredadas de `HermesCLI`) |
| **Skills** | `skills/*` (oficiales) | `skills/janitor-*/` (skills propios) |
| **TUI branding** | Componentes base Ink | `branding.tsx`, skins (`sentry-janitor.yaml`) |
| **Instalador** | `scripts/bootstrap.sh` | `scripts/janitor-install.sh`, `setup-honcho.sh` |
| **Configuración** | `config.yaml` (estructura) | Valores por defecto (`assets/janitor/config.yaml`) |

---

## 2. Flujo de Merge

### 2.1 Preparación

```bash
# Asegúrate de tener el remoto upstream configurado
git remote add upstream ssh://git@github.com/NousResearch/hermes-agent.git 2>/dev/null || true

# Fetch de ambos remotos
git fetch origin main
git fetch upstream main

# Verifica cuántos commits faltan
git log --oneline HEAD..upstream/main
```

### 2.2 Checklist previo al merge

- [ ] `git status` limpio (sin cambios sin commitear)
- [ ] Stash de cambios locales temporales si es necesario
- [ ] Eliminar archivos de continuación de Sisyphus: `rm -f .sisyphus/run-continuation/*.json`

### 2.3 Ejecución del merge

```bash
# Merge directo (crea un commit de merge)
git merge upstream/main --no-edit

# Si hay conflictos, resuelve manualmente antes de continuar
```

---

## 3. Resolución de Conflictos por Categoría

### 3.1 Workflows de GitHub (`.github/workflows/`)

**Situación**: Upstream modifica workflows que Janitor eliminó o reemplazó.

**Solución**:
```bash
# Elimina todos los workflows en conflicto (modificados por upstream, eliminados por Janitor)
git rm -f .github/workflows/*.yml 2>/dev/null || true

# Restaura los workflows nativos de Janitor si existían en HEAD
git checkout HEAD -- .github/workflows/
```

**Regla**: Janitor mantiene sus propios workflows (`janitor-ci.yml`, `upstream-sync.yml`). Nunca adoptar workflows de upstream sin revisar.

### 3.2 Branding / Identidad Visual

**Archivos típicamente en conflicto**:
- `ui-tui/src/components/branding.tsx`
- `hermes_cli/main.py` (funciones de versión)
- `README.md`

**Reglas de resolución**:

1. **TUI (`branding.tsx`)**:
   - Adopta la lógica responsiva de upstream (`wide ? ... : ...`)
   - Reemplaza texto hardcoded de upstream (`Nous Research`, `Messenger of the Digital Gods`) con variables del tema Janitor (`t.brand.name`, `t.brand.icon`, `t.brand.version`)
   - No uses constantes string hardcoded; usa helpers dinámicos:
     ```typescript
     const brandTagFull = (t: Theme) => `${t.brand.name} · DevSecOps Orchestrator`
     ```

2. **CLI (`main.py`)**:
   - Adopta funciones helper de upstream (ej. `_print_version_info()`)
   - Cambia strings de versión a `THE JANITOR`:
     ```python
     print(f"THE JANITOR v{__version__} ({__release_date__})")
     ```

3. **README**:
   - Preserva la estructura de upstream si mejora la documentación
   - Mantén el contrato del instalador mínimo + skills opcionales
   - Docker, Honcho, Firecrawl son **skills opcionales**, no requisitos base

### 3.3 Scripts de Instalación (`scripts/setup-stack.sh`)

**Reglas**:
- Elimina cualquier referencia a GHCR (`ghcr.io`, `check_ghcr_auth`) — Janitor compila Honcho desde fuente
- Corrige problemas de `set -e` que bypass error handling:
  ```bash
  # ❌ Mal (set -e sale antes del if)
  DOCKER_OUTPUT=$(docker info 2>&1)
  if [ $? -ne 0 ]; then ...

  # ✅ Bien
  if ! DOCKER_OUTPUT=$(docker info 2>&1); then ...
  ```

---

## 4. Validación Post-Merge (Gates Obligatorios)

### 4.1 Checklist de validación

- [ ] **Shell syntax**: `bash -n scripts/setup-stack.sh`
- [ ] **Python syntax**: `python3 -m py_compile hermes_cli/main.py gateway/run.py`
- [ ] **Conflict markers**: escanear archivos resueltos por `<<<<<<<`, `=======`, `>>>>>>>`
- [ ] **Branding sanitization**: verificar que no queden strings de upstream (`Nous Research`, `Messenger of the Digital Gods`, `Hermes Agent v`)
- [ ] **GHCR purge**: verificar que no queden `check_ghcr_auth` ni `ghcr.io` en scripts
- [ ] **Git status**: `git status --short` debe estar limpio (sin untracked de `.sisyphus/run-continuation/`)

### 4.2 Gates del TUI (obligatorios si se toca `ui-tui/`)

```bash
cd ui-tui
npm run type-check
npm run build --prefix packages/hermes-ink
npm run build
npm test
```

**Criterios de aprobación**:
- `npm run type-check`: 0 errores de TypeScript
- `npm run build`: exit code 0, genera `dist/entry.js`
- `npm test`: 0 tests fallidos (skips aceptables)

### 4.3 Compilación rápida de Python

```bash
python3 -m py_compile cli.py run_agent.py gateway/run.py
```

---

## 5. Commit del Merge

### 5.1 Mensaje del commit de merge

```
chore(merge): resolve upstream conflicts and purge obsolete GHCR check
```

### 5.2 Si hay fixes post-review

Si los agentes de review encuentran bloqueos, crear commits atómicos separados:

```
fix(branding): remove upstream identity leaks
fix(installer): align legacy stack guidance
fix(tui): resolve merge compilation blockers
```

**Nunca** mezclar fixes de branding con fixes de installer en el mismo commit.

---

## 6. Verificación Final con Agentes

Tras completar el merge y sus fixes, lanzar los 5 agentes de review en paralelo:

1. **Goal & Constraint Verification** (oracle): ¿Se cumplió el objetivo del merge?
2. **QA Execution** (unspecified-high): ¿Pasan las validaciones manuales?
3. **Code Quality Review** (oracle): ¿Es mantenible y consistente?
4. **Security Audit** (oracle): ¿Hay riesgos de seguridad?
5. **Context Mining** (unspecified-high): ¿Faltó contexto relevante?

**Todos deben dar PASS** antes de considerar el merge finalizado.

---

## 7. Troubleshooting

### 7.1 El TUI no compila después del merge

**Síntoma**: `npm run type-check` falla con errores de tipo en archivos que no tocaste.

**Causa probable**: Upstream cambió la firma de funciones en `@hermes/ink` y el paquete no está recompilado.

**Solución**:
```bash
npm run build --prefix packages/hermes-ink  # Recompila las exportaciones
npm run type-check                           # Ahora debería pasar
```

### 7.2 Tests del TUI fallan con `wrapAnsi is not a function`

**Causa**: El build de `packages/hermes-ink` generó un export inválido o el test usa un mock incompleto.

**Solución**: Revisar `ui-tui/packages/hermes-ink/src/ink/wrapAnsi.ts` y asegurar que exporta correctamente; recompilar.

### 7.3 Conflictos recurrentes en `branding.tsx`

**Prevención**: Si upstream actualiza frecuentemente el banner, considera crear un patch file o un script de post-merge que verifique automáticamente que `TAG_FULL` no re-aparezca.

---

## 8. Anexo: Referencia Rápida de Comandos

```bash
# Fetch y ver diferencias
git fetch upstream main
git log --oneline HEAD..upstream/main

# Merge
git merge upstream/main --no-edit

# Validación rápida
bash -n scripts/setup-stack.sh
python3 -m py_compile hermes_cli/main.py
grep -rn 'Nous Research\|Messenger of the Digital Gods\|Hermes Agent v' ui-tui/src/components/branding.tsx hermes_cli/main.py
grep -rn 'check_ghcr_auth\|ghcr.io' scripts/setup-stack.sh

# TUI gates
cd ui-tui && npm run type-check && npm run build --prefix packages/hermes-ink && npm run build && npm test

# Estado final
git status --short

---

### 3.X Re-apply test-assertion branding after any upstream sync

Per AGENTS.md fork directive #12 (TEST ASSERTION BRANDING), any test file that newly contains the upstream-original string `Hermes Agent` (or `Hermes Agent v`) in a banner / `--version` assertion must be updated to `THE JANITOR` (or `THE JANITOR v`) in the same commit that re-applies the branding. Run this grep after the merge to find any drift; the result must be `0 matches`:

```bash
git grep -nE '"Hermes Agent"|"Hermes Agent v"' -- tests/ -- ':!*.pyc' ':!docs/superpowers/'
```

If any matches are found, update the assertion in the same commit and add the inline comment block pointing back to AGENTS.md rule #12 (the comment template lives in `docs/superpowers/specs/2026-06-10-migrate-specialized-agents-to-kanban-profiles-design.md`, "Baseline assertion drift" section).

---

*Última actualización: Mayo 2026*

---

## v2026.6.5 Sync (Hermes v0.16.0)

**Rango:** `1a710e8df` → `2a14e8957` (1,607 commits, 996 files, +80,859 / -26,205 líneas)
**Fecha:** 2026-06-15
**Estrategia:** Full merge con `git merge -X theirs upstream/main --no-commit` + restauración manual de archivos Janitor-only desde `HEAD` + re-aplicación de branding

### Cambios adoptados

**7 parches de seguridad críticos:**
- `da28d5d11` — SSH/credential gate en `cp`/`mv`/`install`
- `972a9885e` — Bloqueo de exfil en MCP stdio configs
- `fc4635458` — Gateway fail-closed en own-policy adapters
- `3380563d9` — `/api/status` host-leak fix
- `a218a0f15` + `af5b52647` — SSL CA bundle fail-fast guard
- `bd66e7e3f` — Codex OAuth refresh_token self-heal
- `7a1eed826` — Anthropic replay redaction

**Módulos nuevos adoptados:**
- `agent/coding_context.py` (738 líneas)
- `agent/ssl_guard.py` + `agent/anthropic_adapter.py`
- `agent/transports/{anthropic,chat_completions,codex,types}.py`
- `cron/blueprint_catalog.py` (713 líneas)
- `gateway/platforms/whatsapp_cloud.py` (1956 líneas)
- `hermes_cli/mcp_security.py` (nuevo módulo seguridad)
- `hermes_cli/blueprint_cmd.py`, `model_cost_guard.py`, `setup_whatsapp_cloud.py`, `suggestions_cmd.py`, `write_approval_commands.py`
- `tools/blueprints.py`, `read_extract.py`, `read_terminal_tool.py`, `write_approval.py`

**Plataformas nuevas:** `photon`, `simplex`, `teams`, `whatsapp_cloud`

**Providers nuevos:** `zai` (GLM-5.2), `langfuse` observability

**Skills nuevos adoptados (11):** 5 github + 4 productivity + 2 media + 1 research + 1 note-taking (ver `skills/` post-merge)

**Config v11→v12 + breaking change:**
- `memory.write_mode` / `skills.write_mode` (tri-state) → `write_approval` (boolean, default false)
- `_config_version`: 28 → 29
- Slash commands: `/memory mode <on|off|approve>` → `/memory approval <on|off>` (mode queda como alias)

**God-file refactor:** cli.py y gateway/run.py (Phase 2/3) — módulos extraídos a `hermes_cli/subcommands/`, `gateway/*_mixin.py`

### Cambios descartados

- **1,495 archivos de tests upstream** en `tests/` (per directiva #11)
  - El job `upstream-sync-verify` corre la suite completa contra el código post-merge en `workflow_dispatch` y en pushes a `main` con commits `chore(sync):` / `fix(sync):`
  - **Preservados**: 5 tests Janitor-specific + 3 archivos comunes (`__init__.py`, `conftest.py`) + 114 tests Electron del subtree `apps/desktop/electron/*.test.cjs`

- **32 commits de `chore(release): map <author>`** (bookkeeping upstream irrelevante)
- **`apps/desktop/` subtree Electron** traído pero NO publicado (per directivas #4 + #8). El instalador base sigue sin incluirlo.

### Fixes aplicados durante el merge

1. `scripts/run_tests_parallel.py`: removida definición duplicada de `--slice` (regresión upstream en su propio merge de god-file phase)
2. `pyproject.toml`: restaurados `janitor_cli`, `janitor_update_bootstrap`, `janitor_update_core` en `py-modules` (necesario para directiva #13)
3. Branding re-aplicado: `hermes_cli/main.py:231` y `hermes_cli/banner.py:478` ahora dicen `THE JANITOR v{VERSION} ({RELEASE_DATE})`

### Post-merge para usuarios existentes

```bash
# Si tenías una config v0.15.x con write_mode, migrar:
bash scripts/migrate-janitor-v0.16.0.sh

# Verificar que la versión es correcta:
janitor --version
# Expected: THE JANITOR v0.16.0 (...)
```

### Branding
- `THE JANITOR` preservado en `hermes_cli/main.py:231` y `hermes_cli/banner.py:478`
- Re-aplicado automáticamente durante el merge

### CI
- `tests.yml` sigue podado a 5 tests Janitor-specific
- `upstream-sync.yml` presente (job `upstream-sync-verify`)
- `janitor-ci.yml` presente
- `supply-chain-audit.yml` y `typecheck.yml` aceptados
- 19 workflows en total (vs 18 upstream-only)

---

## 9. Customizaciones Desktop — Asset Replacement (`apps/desktop/public/`)

> Las personalizaciones visuales de la app desktop siguen un enfoque **puramente
> binario**: reemplazar assets upstream con sus contrapartes Janitor. Cero
> código React/CSS/TS tocado. Trade-off: cualquier cambio upstream a esos
> archivos requiere re-aplicar el reemplazo (conflicto trivial esperado).

### 9.1 Archivos reemplazados (3 upstream binary swaps)

| Path upstream | Tamaño antes → después | Asset Janitor | Uso upstream |
|---|---|---|---|
| `apps/desktop/public/ds-assets/filler-bg0.jpg` | 3.8 MB → 766 KB | `j4nitor-agent-logo-transparent.png` (wireframe) | `<img>` en `src/components/Backdrop.tsx:103` — fondo del empty view |
| `apps/desktop/public/nous-girl.jpg` | 20 KB → 1.3 MB | `j4nitor-monogram.png` (wireframe) | `<img>` en `src/components/brand-mark.tsx:16` — Settings/About + Updates overlay |
| `apps/desktop/public/apple-touch-icon.png` | 541 KB → 1.3 MB | `j4nitor-monogram.png` (wireframe) | favicon (`index.html:7-9`) + Dock/Taskbar icon (`electron/main.cjs:339-343` via `APP_ICON_PATHS`) |

### 9.2 Archivos NO modificados (intencional)

| Path | Razón |
|---|---|
| `apps/desktop/public/hermes.png` | Sin referencia en `src/` (graph confirma 0 usos). Mantenido como reliquia upstream. |
| `apps/desktop/public/hermes-sprite.png` | Sin referencia en `src/`. Mantenido. |
| `apps/desktop/public/hermes-frames/hermes-frame-{0..7}.png` | Sin referencia en `src/`. Mantenidos. |
| `apps/desktop/src/components/chat/intro.tsx` (wordmark + tagline) | Renderiza texto React con `<p>{WORDMARK}</p>`. **No es un asset binario**. Reemplazar este archivo requiere upstream modification o componente React override (próxima iteración). |
| `apps/desktop/index.html:11` (`<title>Hermes</title>`) | Texto en HTML, no binario. Próxima iteración. |
| `apps/desktop/assets/icon.{icns,ico,png}` | Build-time Electron icons. Reemplazo va via electron-builder config externo (`apps/desktop/electron-builder.janitor.json`) — próxima iteración. |

### 9.3 Riesgo conocido — MIME mismatch

Los assets wireframe source son **PNG**, pero el path upstream exige extensión
`.jpg` para 2 de los 3 archivos. El reemplazo conserva el filename upstream:

| Archivo | Contenido real | Extensión | MIME servido |
|---|---|---|---|
| `filler-bg0.jpg` | PNG (1942×809 RGBA) | `.jpg` | `image/jpeg` por Vite |
| `nous-girl.jpg` | PNG (1254×1254 RGB) | `.jpg` | `image/jpeg` por Vite |
| `apple-touch-icon.png` | PNG (1254×1254 RGB) | `.png` | `image/png` (sin riesgo) |

**Mitigación Chromium (Electron renderer)**: content-sniffing debería detectar
el contenido real y renderizar OK. Si el render local muestra cuadros rotos,
el fix es renombrar upstream a `.png` + actualizar el path en `Backdrop.tsx:103`
(de upstream modification menor).

### 9.4 Conflictos esperados al `git pull upstream main`

| Archivo | Riesgo | Mitigación |
|---|---|---|
| `apps/desktop/public/ds-assets/filler-bg0.jpg` | **Alto** — upstream puede actualizar el fondo (animaciones, nuevos productos) | Aceptar upstream, re-aplicar el reemplazo Janitor |
| `apps/desktop/public/nous-girl.jpg` | **Medio** — asset visualmente estable, upstream raramente lo cambia | Mismo |
| `apps/desktop/public/apple-touch-icon.png` | **Medio** — idem | Mismo |
| `apps/desktop/src/components/Backdrop.tsx` | CERO | No tocado |
| `apps/desktop/src/components/brand-mark.tsx` | CERO | No tocado |
| `apps/desktop/index.html` | CERO | No tocado |
| Código React/TS/CSS upstream | CERO | Este commit no toca código fuente |

### 9.5 Verificación post-merge

```bash
cd apps/desktop
npm run typecheck      # sin errores esperados (no tocamos código)
npm run test:desktop:platforms  # 18 tests electron, no afectados
# Visual: npm run dev → verificar BrandMark, fondo, favicon
```

### 9.6 Próximas iteraciones (no incluidas)

- **Wordmark + tagline**: requieren componente React o upstream modification en `intro.tsx:145,21-42,117-138`.
- **Window title** (`index.html:11`): cambio trivial upstream, 1 línea.
- **Sidebar top-left brand**: no existe upstream, requiere nuevo componente React.
- **Build-time icons** (`apps/desktop/assets/icon.{icns,ico,png}`): requieren electron-builder config externo + regenerar `.icns`/`.ico` desde PNG fuente.

### 9.7 Pre-flight checklist antes de PR de branding

Antes de cualquier PR que toque `apps/desktop/public/`:

- [ ] `npm run dev` local muestra el render esperado (BrandMark, fondo, favicon)
- [ ] `vite build` OK sin warnings de MIME/asset resolution
- [ ] `git diff --stat` solo toca `apps/desktop/public/*` + (opcional) `.gitignore`
- [ ] Screenshot de Settings → About + Updates overlay + ventana maximizada con fondo visible

---

## 10. Stale CI Config — Actualización post-sync de `janitor-ci.yml`

> **Lección aprendida:** El sync upstream (`607078d2c`, v0.16.0) eliminó/renombró
> archivos referenciados por `janitor-ci.yml`, pero el workflow no se actualizó
> en el mismo commit. Resultado: ambos jobs (`python-tests` y `react-tests`)
> fallaban en CI sin que el código tuviera bugs reales.

### 10.1 Síntomas

- `python-tests` job falla con `ERROR: file or directory not found: tests/hermes_cli/test_skin_engine.py`
- `react-tests` job falla con `npm error Missing script: "type-check"`
- Los tests pasan localmente cuando se ejecutan manualmente con los nombres correctos

### 10.2 Causa raíz

El commit de sync upstream puede **eliminar, mover o renombrar** archivos que
`janitor-ci.yml` referencia directamente. El sync es un merge masivo (~1600
commits, ~1000 archivos) y `janitor-ci.yml` es un archivo Janitor-only que el
sync no toca — pero sus **referencias** apuntan a archivos que sí cambiaron.

| Referencia en `janitor-ci.yml` | Qué pasó en el sync | Fix aplicado |
|---|---|---|
| `tests/hermes_cli/test_skin_engine.py` | Eliminado por upstream (reestructuración de tests) | Reemplazado con `tests/test_janitor_update_core.py` |
| `npm run type-check` | Script renombrado a `typecheck` (sin guion) en `ui-tui/package.json` | Actualizado a `npm run typecheck` |

### 10.3 Checklist post-sync obligatorio para `janitor-ci.yml`

Después de **cualquier** `git merge upstream/main` (o `chore(sync):` commit),
verificar estas 3 referencias antes de pushear:

```bash
# 1. Los archivos de test referenciados existen
grep -E 'python -m pytest' .github/workflows/janitor-ci.yml | \
  grep -oE 'tests/\S+\.py' | \
  while read f; do test -f "$f" && echo "OK: $f" || echo "MISSING: $f"; done

# 2. Los scripts de npm referenciados existen en package.json
grep -E 'npm run ' .github/workflows/janitor-ci.yml | \
  grep -oE 'npm run \S+' | \
  while read script; do
    name=$(echo "$script" | sed 's/npm run //')
    node -e "const p=require('./ui-tui/package.json'); \
      p.scripts['$name'] ? console.log('OK: $name') : console.log('MISSING: $name')"
  done

# 3. La versión de actions/checkout es consistente con el resto de workflows
grep 'actions/checkout@' .github/workflows/janitor-ci.yml
```

Si cualquier línea dice `MISSING:`, corregir `janitor-ci.yml` en el mismo
commit del sync (o en un commit `fix(ci):` inmediatamente después) antes
de abrir el PR.

### 10.4 Prevención — añadir al checklist de validación post-merge (§4.1)

Añadir estos ítems al checklist de la sección 4.1 después de cada sync:

- [ ] **CI refs válidos**: `janitor-ci.yml` no referencia archivos eliminados ni scripts renombrados (ver §10.3)
- [ ] **CI jobs verificados**: ejecutar localmente los 2 jobs de `janitor-ci.yml` antes de pushear

### 10.5 Archivos Janitor-only que el sync NO protege

`janitor-ci.yml` es un archivo Janitor-only — el sync upstream no lo toca ni
lo valida. Cualquier referencia que apunte a código upstream (tests, scripts
de npm, paths de build) es **frágil** y debe verificarse después de cada sync.

Archivos Janitor-only que dependen de estructura upstream:

| Archivo Janitor | Dependencia upstream | Riesgo |
|---|---|---|
| `.github/workflows/janitor-ci.yml` | Tests files, npm scripts | **Alto** — se rompe en cada sync que reestructura tests o renombra scripts |
| `.github/workflows/tests.yml` | Tests files (5 Janitor-specific) | **Medio** — los tests Janitor-specific son estables, pero nombres de archivos pueden cambiar |
| `janitor_cli.py` | `HermesCLI` class en `cli.py` | **Bajo** — la interfaz pública es estable |

### 10.6 Fix aplicado en este commit

```
fix(ci): update janitor-ci.yml references after upstream sync

- Replace deleted tests/hermes_cli/test_skin_engine.py with
  tests/test_janitor_update_core.py (skin_engine test was removed
  by upstream sync commit 607078d2c)
- Fix npm run type-check → npm run typecheck (script renamed in
  upstream sync)
- Document stale CI config issue in MERGE_GUIDE.md §10

Both CI jobs now pass locally:
- python-tests: 29 passed
- react-tests: 1026 passed, 2 skipped
```

---

## 11. Telegram Core Customization (`gateway/platforms/telegram.py`)

> **Lección aprendida:** El sync upstream vía wholesale adoption (T2.1,
> commit `607078d2c`) eliminó **todas** las personalizaciones Janitor de
> Telegram al sobreescribir `gateway/platforms/telegram.py` con la versión
> upstream. El fix de re-aplicación (`91a891618`) tuvo que restaurar 6
> piezas de código + 5 constantes + 1 import + 1 handler + 1 call site.
> Las personalizaciones **no sobreviven** a un merge masivo si no se
> documentan como zona de conflicto explícita.

### 11.1 Inventario de personalizaciones Janitor en `telegram.py`

Todas las adiciones son **puramente aditivas** (cumple directiva #1
ZERO-RENAMING y directiva #4 TUI ISOLATION — no se renombra nada de
upstream, solo se inyecta comportamiento):

| Símbolo | Tipo | Ubicación | Qué hace |
|---|---|---|---|
| `_JANITOR_ASSETS_DIR` | Constante módulo | línea 116 | `Path(__file__).resolve().parents[2] / "assets" / "janitor"` |
| `_JANITOR_AVATAR_PATH` | Constante módulo | línea 117 | Apunta a `assets/janitor/janitor_avatar.png` (uso general) |
| `_JANITOR_TELEGRAM_AVATAR_PATH` | Constante módulo | línea 118 | Apunta a `assets/janitor/janitor_avatar_telegram.jpg` (uso Telegram) |
| `_JANITOR_WELCOME_PATH` | Constante módulo | línea 119 | Apunta a `assets/janitor/telegram_welcome.jpg` |
| `_JANITOR_WELCOME_TEXT` | Constante módulo | línea 120 | Texto de bienvenida en español (menciona `/topic`) |
| `InputProfilePhotoStatic` (try/except) | Import | líneas 31, 33, 53 | Necesario para PTB ≥ 22.7; los mocks de test lo parchean en ambas ramas |
| `_set_janitor_avatar()` | Método async | líneas 1872-1926 | Quita el profile photo actual del bot y sube el JPG Janitor vía `set_my_profile_photo` (PTB ≥ 22.7) con fallback `do_api_request("removeMyProfilePhoto")` |
| `await self._set_janitor_avatar()` | Call site | línea 2077 dentro de `connect()` | **Punto de inyección único** — se ejecuta después de `_app.initialize()` |
| `self._app.add_handler(CommandHandler("start", self._handle_start))` | Handler registration | línea 2052 | Registra el comando `/start` que envía la imagen de bienvenida |
| `_handle_start()` | Método async | líneas 5874-5906 | Envía `telegram_welcome.jpg` con caption `_JANITOR_WELCOME_TEXT`; fallback a texto si falta el asset |

### 11.2 Assets aislados (NO se modifican en merges)

Estos archivos viven en `assets/janitor/` y **no son parte de upstream**.
Un merge no debe tocarlos (no aparecen en el árbol de upstream):

| Archivo | Tamaño | Uso | Test |
|---|---|---|---|
| `assets/janitor/janitor_avatar_telegram.jpg` | ~36 KB | Profile photo del bot (set on every connect) | `test_telegram_avatar_asset_is_jpeg` verifica magic bytes JPEG |
| `assets/janitor/telegram_welcome.jpg` | ~948 KB | Imagen enviada en `/start` | Implícitamente cubierto por `test_handle_start_*` |
| `assets/janitor/janitor_avatar.png` | ~169 KB | Avatar general (no Telegram-específico) | Sin test directo |

**Verificación rápida post-merge**:
```bash
test -f assets/janitor/janitor_avatar_telegram.jpg && \
  test -f assets/janitor/telegram_welcome.jpg && \
  echo "OK: telegram assets present" || \
  echo "MISSING: telegram assets"
```

### 11.3 Test de regresión — `tests/gateway/test_telegram_janitor_branding.py`

Este es el archivo de **regression guard** para toda la zona de conflicto
Telegram. Cualquier sync upstream que toque `gateway/platforms/telegram.py`
debe ir acompañado de una corrida verde de este test.

**12 funciones de test** que cubren:
1. Avatar upload en cada `connect()` (sin flag file de "ya subido")
2. Idempotencia del avatar setter (sube en cada llamada)
3. Skip graceful cuando PTB < 22.7 (warning + no-op)
4. Fallback a `do_api_request("removeMyProfilePhoto")` cuando falla la API moderna
5. Uso correcto de `photo=` kwarg (no `profile_photo=` ni `media=`) — testea el contrato de la API de PTB
6. Skip silencioso cuando falta el asset (no bloquea startup)
7. `/start` envía `telegram_welcome.jpg` con caption Janitor (no `send_message`)
8. `/start` fallback a texto cuando falta el asset
9. Integridad JPEG del avatar (`file(1)` confirma `JPEG image data`)

**Wiring CI** (ver §4.1):
```yaml
# .github/workflows/tests.yml, líneas 87-100
- name: Run Janitor-specific tests
  run: |
    source .venv/bin/activate
    python -m pytest \
      tests/test_janitor_cli.py \
      tests/test_janitor_update_bootstrap.py \
      tests/test_janitor_update_core.py \
      tests/gateway/test_telegram_janitor_branding.py \
      tests/skills/test_janitor_config_audit_skill.py \
      --tb=short -v
```

### 11.4 Síntomas de regresión Telegram

Si un merge upstream rompe las personalizaciones Janitor de Telegram,
los síntomas son:

- `tests/gateway/test_telegram_janitor_branding.py` reporta **11 de 12 tests rojos** (solo pasa `test_telegram_avatar_asset_is_jpeg`, que no depende del código)
- En runtime: el bot de Telegram arranca con el avatar de upstream (o sin avatar) en lugar de `janitor_avatar_telegram.jpg`
- En runtime: el comando `/start` responde con texto genérico de Hermes en lugar de `telegram_welcome.jpg` + caption Janitor
- Mensaje en logs: `TelegramAdapter` no llama a `_set_janitor_avatar()` durante el connect

### 11.5 Causa raíz

`gateway/platforms/telegram.py` es un **hot path** de upstream — recibe
commits en casi cada sync (v0.16.0 incorporó ~25 commits Telegram: rich
messages, Bot API 10.1, streaming fixes, etc.). Los métodos de Janitor
(`_set_janitor_avatar`, `_handle_start`) son **inyectados en el cuerpo
de la clase `TelegramAdapter`**, lo que los hace invisibles al `git
diff` de superficie: un merge con `-X theirs` los borra sin levantar
conflictos de tres vías.

### 11.6 Resolución de conflictos

**Si git marca conflicto en `gateway/platforms/telegram.py`**:

1. **NO adoptes upstream completo** — las personalizaciones Janitor están en medio de métodos de upstream (`connect()`, `_handle_start` se inyecta cerca de otros handlers).
2. **Resuelve preservando ambos lados**:
   - Adopta la lógica nueva de upstream (rich messages, streaming fixes, etc.)
   - Conserva los símbolos `_JANITOR_*`, los métodos `_set_janitor_avatar` y `_handle_start`, y los call sites en `connect()` y `add_handler`
   - Verifica que el import de `InputProfilePhotoStatic` siga en **ambas** ramas del try/except (líneas 31 y 33)
3. **Después de resolver, corre el test de regresión**:
   ```bash
   python -m pytest tests/gateway/test_telegram_janitor_branding.py -v
   ```
   Debe pasar 12/12 en menos de 2s.

**Si git NO marca conflicto pero el test falla** (caso del wholesale
adoption `607078d2c`): upstream sobreescribió el archivo sin conservar
nada. Restaurar desde el commit de re-aplicación de referencia
`91a891618`:
```bash
# Ver qué se perdió
git diff 91a891618^ -- gateway/platforms/telegram.py | head -200

# Re-aplicar el delta Janitor desde el commit de referencia
git show 91a891618 -- gateway/platforms/telegram.py | git apply
```

### 11.7 Checklist post-merge obligatorio para Telegram

Añadir al checklist de validación (§4.1) después de cualquier merge
que toque `gateway/platforms/telegram.py`:

- [ ] **Constantes presentes**: `grep -q "_JANITOR_ASSETS_DIR" gateway/platforms/telegram.py`
- [ ] **Método avatar presente**: `grep -q "_set_janitor_avatar" gateway/platforms/telegram.py`
- [ ] **Call site en connect**: `grep -q "await self._set_janitor_avatar" gateway/platforms/telegram.py`
- [ ] **Handler /start**: `grep -q "_handle_start" gateway/platforms/telegram.py`
- [ ] **Import PTB**: `grep -q "InputProfilePhotoStatic" gateway/platforms/telegram.py` (debe aparecer en línea 31 — try block — Y en línea 33 — except block; en total ≥ 2 referencias)
- [ ] **Test verde**: `python -m pytest tests/gateway/test_telegram_janitor_branding.py -v` → 12/12 pass
- [ ] **Assets presentes**: `test -f assets/janitor/janitor_avatar_telegram.jpg && test -f assets/janitor/telegram_welcome.jpg`

```bash
# One-liner para validar todo de una vez
(
  grep -q "_JANITOR_ASSETS_DIR" gateway/platforms/telegram.py && \
  grep -q "_set_janitor_avatar" gateway/platforms/telegram.py && \
  grep -q "await self._set_janitor_avatar" gateway/platforms/telegram.py && \
  grep -q "_handle_start" gateway/platforms/telegram.py && \
  grep -q "InputProfilePhotoStatic" gateway/platforms/telegram.py && \
  test -f assets/janitor/janitor_avatar_telegram.jpg && \
  test -f assets/janitor/telegram_welcome.jpg
) && echo "Telegram Janitor branding: SYMBOLS OK" || echo "Telegram Janitor branding: SYMBOLS MISSING"

# Test verde (separado porque pytest puede tardar):
python -m pytest tests/gateway/test_telegram_janitor_branding.py -q
```

### 11.8 Archivos Janitor-only relacionados con Telegram

| Archivo | Tipo | Riesgo en sync |
|---|---|---|
| `tests/gateway/test_telegram_janitor_branding.py` | Test Janitor-only | **Medio** — corre en PR gate pero el sync puede romper `gateway/platforms/telegram.py` y el test detecta regresiones |
| `assets/janitor/janitor_avatar_telegram.jpg` | Asset binario | **Bajo** — no está en árbol upstream, no se toca |
| `assets/janitor/telegram_welcome.jpg` | Asset binario | **Bajo** — idem |
| `.sisyphus/evidence/post-merge-gate-9-telegram.txt` | Evidencia | **Bajo** — archivo `.sisyphus/` ignorado por git |
| `docs/plans/2026-06-09-003-fix-telegram-stream-overflow-continuations-plan.md` | Plan activo | **Bajo** — fork-only, fuera del árbol upstream |

### 11.9 Fix de referencia — commit `91a891618`

El commit de referencia para restaurar las personalizaciones Janitor de
Telegram tras un wholesale adoption es:

```
91a891618 fix(sync): re-apply Janitor fork identity lost by upstream adoption (T5b.3)

- _JANITOR_ASSETS_DIR, _JANITOR_AVATAR_PATH,
  _JANITOR_TELEGRAM_AVATAR_PATH, _JANITOR_WELCOME_PATH,
  _JANITOR_WELCOME_TEXT constants
- _set_janitor_avatar() method (with PTB >= 22.7 fallback)
- _handle_start() method
- await self._set_janitor_avatar() call in connect()
- CommandHandler('start', self._handle_start) registration
- Added 'InputProfilePhotoStatic' to both try/except import blocks
```

Si un sync futuro vuelve a borrar la zona (por ejemplo, otro wholesale
adoption o una resolución `-X theirs` mal calibrada), este commit es
la **fuente canónica** del delta Janitor en `telegram.py`. Aplicar con:
```bash
git show 91a891618 -- gateway/platforms/telegram.py | git apply
```

