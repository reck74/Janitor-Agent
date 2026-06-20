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

