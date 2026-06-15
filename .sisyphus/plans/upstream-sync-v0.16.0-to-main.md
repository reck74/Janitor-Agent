# Upstream Sync Plan: Janitor → Hermes v0.16.0 (1,607 commits)

**Fecha de generación:** 2026-06-15
**Rango:** `main` (`1a710e8df`) → `upstream/main` (`2a14e8957`)
**Versión objetivo:** v0.16.0 (ya estamos en 0.16.0 — sync de código, no de versión)
**Tags upstream a incorporar:** v2026.5.28, v2026.5.29, v2026.5.29.2, v2026.6.5

---

## TL;DR

Adoptar **todo el código funcional** del upstream (1,607 commits, 996 archivos, +80,859 líneas) **descartando los tests upstream** (per directriz #11: nuestro PR-gate corre los 3 tests Janitor-specific; el `upstream-sync-verify` job ya ejecuta la suite completa upstream en `workflow_dispatch` y verifica que sus propios tests pasen antes de cada merge).

**Resultado esperado:** un único merge commit `chore(sync): v0.16.0 from upstream main` con todo el código nuevo de las releases v2026.5.28 → v2026.6.5, branding Janitor preservado, las 13 directivas intactas, sin los tests upstream.

**Tiempo estimado:** 30-60 min de ejecución + tiempo de revisión.

---

## Context

### Estado del fork Janitor
- **Working tree sucio:** 4 archivos modificados sin commitear (`.sisyphus/boulder.json`, `MERGE_GUIDE.md`, `skills/janitor-config-audit/{SKILL.md,scripts/audit.py}`) → **commitear o stashear ANTES de empezar** (puede interferir con el merge).
- **Branding `THE JANITOR` ya aplicado** en las 2 líneas críticas: `hermes_cli/main.py:231` y `hermes_cli/banner.py:425` (directriz #12).
- **Directivas 1-13 documentadas** en `AGENTS.md` y `MERGE_GUIDE.md`.
- **12 skills Janitor** intactas bajo `skills/janitor-*`.
- **3 tests Janitor-specific** en el PR-gate: `test_janitor_cli.py`, `test_janitor_update_bootstrap.py`, `test_telegram_janitor_branding.py`.
- **`janitor_update_core.py`** (directriz #13) es el source-of-truth del flujo `janitor update`.

### Decisiones del usuario (esta sesión)
1. **Forma del merge:** Full merge + cherry-pick selectivo (Rama `upstream-sync-2026-06` + script de rebrand automático + resolución manual de conflictos).
2. **`apps/desktop/`:** Traer el subtree actualizado pero dejarlo **no publicado** (sin documentar en `janitor-onboarding` ni auto-instalar; sigue siendo opt-in).
3. **Features nuevos (módulos, plataformas, skills):** Adoptar **todos** los aditivos puros: `agent/coding_context.py`, `gateway/platforms/whatsapp_cloud.py`, `photon/`, `simplex/`, `teams/`, providers `zai` y `langfuse`, los 22 skills nuevos (5 github, 4 productivity, 2 media, 1 note-taking, 1 research + 11 optional-skills), `cron/blueprint_catalog.py`.
4. **Housekeeping:** Traer **todos** los `chore(release):` y `chore(deps):` para mantener paridad exacta con upstream.

### Sync previo (referencia)
El sync `v0.15.1 → main` (jun 2026, 153 commits) siguió un patrón similar pero más pequeño. Usó una rama intermedia, 3 sub-PRs en batches, y commiteó con prefijo `chore(sync):`. Esa estructura se replica aquí escalada a 1,607 commits.

---

## Work Objectives

### Core Objective
Incorporar el código funcional de v0.16.0 al fork Janitor preservando:
- Las 13 directivas del fork (especialmente #1 zero-rename, #11 test pruning, #12 branding, #13 update flow)
- Los 12 skills `janitor-*` y los archivos Janitor-only (`janitor_cli.py`, `janitor_update_core.py`, `janitor_update_bootstrap.py`, `janitor_ext/`, `scripts/janitor-*`)
- La identidad `THE JANITOR` en el banner (`hermes_cli/main.py:231`, `hermes_cli/banner.py:425`)
- La CI podada (3 tests en el PR gate, `upstream-sync-verify` ejecutándose solo en `workflow_dispatch` o commits `chore(sync):` / `fix(sync):` / merges de `upstream-sync-*`)

### Concrete Deliverables
1. Un merge commit (o cherry-pick chain) que sincronice con upstream.
2. 0 tests upstream en el árbol (los borramos después del merge, antes del commit).
3. Branding `THE JANITOR` re-aplicado donde upstream lo haya sobreescrito.
4. CI workflows en estado correcto: `tests.yml` podado (3 tests), `upstream-sync.yml` presente, `janitor-ci.yml` presente, `supply-chain-audit.yml` y `typecheck.yml` aceptados.
5. Migration script (`scripts/migrate-janitor-v0.16.0.sh`) que documente el cambio `write_mode` → `write_approval` y `_config_version` 28→29 (per directriz #10).
6. `MERGE_GUIDE.md` actualizado con la sección "v2026.6.5 sync notes".
7. Tag anotado `v0.16.0-janitor.1` para esta sync.

### Definition of Done
- [ ] `git log main..upstream/main` muestra 0 commits (sync completa).
- [ ] `tests/` no contiene archivos upstream nuevos (solo los 3-4 tests Janitor + los tests de `apps/desktop/` que ya teníamos del sync previo).
- [ ] `scripts/run_tests.sh tests/test_janitor_cli.py tests/test_janitor_update_bootstrap.py tests/test_telegram_janitor_branding.py` → 0 failures.
- [ ] Branding check: `grep -nE "THE JANITOR" hermes_cli/main.py hermes_cli/banner.py` devuelve las 2 líneas esperadas.
- [ ] CI workflows intactos: `tests.yml` (3-file gate), `upstream-sync.yml` (presente), `janitor-ci.yml` (presente).
- [ ] `hermes` command sigue funcionando (`janitor --version` imprime `THE JANITOR v0.16.0`).
- [ ] `janitor` y `janitor update` funcionan (directriz #13).

### Must Have
- Código funcional de v0.16.0 (features, security patches, providers, platforms, skills).
- 7 parches de seguridad críticos: `da28d5d11`, `972a9885e`, `fc4635458`, `3380563d9`, `a218a0f15`, `bd66e7e3f`, `7a1eed826`.
- Migrations script para `write_mode` → `write_approval` (PR #43354).
- 11 nuevos optional-skills bajo `optional-skills/` (no se instalan automáticamente).

### Must NOT Have (Guardrails)
- **NO** traer tests upstream (`tests/` queda solo con los tests Janitor-specific y los de `apps/desktop/` que ya teníamos).
- **NO** renombrar `hermes` a `janitor` en código core (directriz #1).
- **NO** publicar `apps/desktop/` en onboarding (directriz #8: minimal installer).
- **NO** modificar `janitor_cli.py`, `janitor_update_core.py`, `janitor_update_bootstrap.py`, `janitor_ext/`, `scripts/janitor-*` (directrices #2, #13, #3, #8).
- **NO** alterar la poda de `tests.yml` (directriz #11).
- **NO** eliminar `upstream-sync.yml` (directriz #11: contiene el job `upstream-sync-verify`).
- **NO** commitear secretos, `.env` files, ni `auth.json`.

---

## Verification Strategy (MANDATORY)

### Test Decision
**NO TDD durante el merge.** El merge es por naturaleza no-testeable (no hay una "feature" que construir, hay 1,607 commits upstream que ya pasaron sus propios tests). La validación es **post-merge** mediante:

1. **3 Janitor-specific tests** (PR gate): `test_janitor_cli.py`, `test_janitor_update_bootstrap.py`, `test_telegram_janitor_branding.py`.
2. **`upstream-sync-verify` job** (workflow_dispatch): corre la suite completa upstream contra el código Janitor post-merge. Detecta si los cambios Janitor rompieron código upstream.
3. **LSP diagnostics** sobre archivos modificados.
4. **Smoke test** manual: `janitor --version`, `janitor --help`, `janitor update --help`.

### 7 Mandatory Validation Gates

| # | Gate | Comando | Pass criteria |
|---|---|---|---|
| 1 | Working tree limpio antes del merge | `git status --short` | output vacío |
| 2 | Branding intacto | `grep -c "THE JANITOR v" hermes_cli/main.py hermes_cli/banner.py` | `2 2` (1 por archivo) |
| 3 | Janitor files intactos | `git diff upstream/main -- janitor_cli.py janitor_update_core.py janitor_update_bootstrap.py janitor_ext/ scripts/janitor-install.sh scripts/janitor-finalize-deploy.sh` | output vacío (no upstream los toca) |
| 4 | Tests Janitor pasan | `scripts/run_tests.sh tests/test_janitor_cli.py tests/test_janitor_update_bootstrap.py tests/test_telegram_janitor_branding.py -q` | 0 failures |
| 5 | CI workflows correctos | `ls .github/workflows/{tests.yml,upstream-sync.yml,janitor-ci.yml,supply-chain-audit.yml,typecheck.yml}` | los 5 archivos presentes |
| 6 | `tests.yml` sigue podado | `grep -A 1 "Janitor-specific tests" .github/workflows/tests.yml` | comentario intacto + lista de 3 tests |
| 7 | `janitor --version` funciona | `python -c "import janitor_cli"` y `python -m janitor_cli --version 2>&1 \| head` | imprime `THE JANITOR v0.16.0 (...)` |

### QA Policy
- **Pre-merge:** verificar working tree limpio, branding state, conflict count estimado.
- **Post-merge:** correr los 7 gates. Si alguno falla, abortar y volver a la rama anterior con `git reset --hard`.
- **Post-tag:** ejecutar `git status` y `git log --oneline -5` para confirmar estado limpio.

---

## Execution Strategy

### Estrategia de merge por subárbol

El upstream tiene 1,607 commits pero el **80%** del volumen está concentrado en pocos subárboles. La estrategia es:

1. **Un solo `git pull upstream main` --no-commit --no-ff** para traer todo en una pasada.
2. **Estrategia de checkout post-conflicto por subárbol:**
   - `--ours` en: `janitor_cli.py`, `janitor_update_*.py`, `janitor_ext/`, `scripts/janitor-*`, `AGENTS.md` (primeras 340 líneas con las directivas), `MERGE_GUIDE.md`, `assets/janitor/`, `skills/janitor-*`, `.github/workflows/janitor-ci.yml`, `.github/workflows/upstream-sync.yml`, `.github/workflows/tests.yml` (mantener nuestra poda).
   - `--theirs` en: `tests/` (los borramos manualmente después), `hermes_cli/{main.py,banner.py}` (luego re-aplicamos branding en esas 2 líneas).
   - Merge normal (`git add .` + commit) en: todo lo demás.

3. **Delete tree de tests upstream:** después del merge, `git rm -r tests/` seguido de `git checkout HEAD -- tests/test_janitor_cli.py tests/test_janitor_update_bootstrap.py tests/test_telegram_janitor_branding.py` para restaurar solo los Janitor-specific.
   - **CUIDADO:** los tests de `apps/desktop/` (que vinieron del sync previo v0.15.1) **deben sobrevivir**. Antes de borrar `tests/`, hacer `find apps/desktop -name "*.test.*"` y excluir ese subset.
   - Verificación: `ls tests/` después del cleanup debe mostrar solo: `__init__.py`, `conftest.py`, `_isolate_plugin.py`, `test_janitor_cli.py`, `test_janitor_update_bootstrap.py`, `test_telegram_janitor_branding.py`, `test_janitor_update_core.py` (4 archivos Janitor).

4. **Re-aplicar branding** en `hermes_cli/main.py:231` y `hermes_cli/banner.py:425` con `THE JANITOR v{VERSION} ({RELEASE_DATE})`.

5. **Verificar CI workflows** que upstream haya tocado y re-aplicar la poda donde haga falta.

6. **Crear migration script** `scripts/migrate-janitor-v0.16.0.sh` con la nota sobre `write_mode` → `write_approval`.

7. **Tag anotado** `v0.16.0-janitor.1` con descripción de qué se sincronizó.

### Critical Path

```
[Pre-merge cleanup]
  ↓
[Branch: upstream-sync-2026-06]
  ↓
[git pull --no-commit --no-ff upstream main]
  ↓
[Resolve conflicts por subárbol]
  ↓
[git rm -r tests/ + restore Janitor tests + restore apps/desktop tests]
  ↓
[Re-apply THE JANITOR branding en 2 líneas]
  ↓
[Verify CI workflows: tests.yml podado, upstream-sync.yml presente]
  ↓
[Run 7 validation gates]
  ↓
[git commit -m "chore(sync): v0.16.0 from upstream main"]
  ↓
[Create scripts/migrate-janitor-v0.16.0.sh]
  ↓
[Update MERGE_GUIDE.md with sync notes]
  ↓
[git tag -a v0.16.0-janitor.1 -m "..."]
  ↓
[Merge to main]
  ↓
[Trigger upstream-sync-verify workflow_dispatch]
```

### Dependency Matrix

| Tarea | Depende de | Bloquea |
|---|---|---|
| T0: Commit working tree sucio | — | T1 |
| T1: Branch upstream-sync-2026-06 | T0 | T2 |
| T2: git pull upstream main | T1 | T3 |
| T3: Resolve conflicts | T2 | T4, T5 |
| T4: Delete tests/ upstream | T3 | T6 |
| T5: Re-apply branding | T3 | T6 |
| T6: Verify CI workflows | T3, T4, T5 | T7 |
| T7: Run 7 gates | T6 | T8 |
| T8: Commit merge | T7 | T9, T10 |
| T9: Migration script | T8 | (independent post-merge) |
| T10: Update MERGE_GUIDE.md | T8 | (independent post-merge) |
| T11: Tag v0.16.0-janitor.1 | T8, T9, T10 | T12 |
| T12: Merge to main | T11 | T13 |
| T13: Trigger upstream-sync-verify | T12 | end |

### Agent Dispatch Summary

Esta sync es **mayormente procedural** (un merge + resolución de conflictos sistemática). No requiere despacho masivo de subagentes. Las únicas operaciones que sí delegan a subagentes son:

- **Codebase memory check** post-merge: invocar `codebase-memory-mcp_detect_changes` para que el knowledge graph se entere del nuevo estado.
- **LSP diagnostics** sobre los 12 archivos protegidos + `apps/desktop/electron/main.cjs`.
- **TUI compilation** skill si `ui-tui/` recibió cambios upstream (en este rango: 51 commits — aplicar `tui-compilation` skill per directriz #7).
- **AI-slop-remover** sobre los archivos del merge que parezcan auto-generados.

---

## TODOs

### Wave 1 — Pre-merge Setup (sequential, no delegation needed)

- [ ] **T1.1**: Verificar working tree limpio. Si hay cambios (los 4 archivos detectados), commitear con mensaje `chore: pre-sync local changes`.
  ```bash
  git status --short
  git add .sisyphus/boulder.json MERGE_GUIDE.md skills/janitor-config-audit/
  git commit -m "chore: pre-sync local changes (config-audit skill + merge guide + sisyphus state)"
  ```
  Gate: `git status --short` → vacío.

- [ ] **T1.2**: Crear rama `upstream-sync-2026-06` desde `main`.
  ```bash
  git fetch upstream
  git checkout -b upstream-sync-2026-06
  ```
  Gate: `git branch --show-current` → `upstream-sync-2026-06`.

- [ ] **T1.3**: Snapshot del estado actual de branding y CI workflows para comparar post-merge.
  ```bash
  # Guardar en /tmp/pre-sync-state.txt
  {
    echo "=== branding state ==="
    grep -nE "THE JANITOR|Hermes Agent" hermes_cli/main.py hermes_cli/banner.py | head -20
    echo "=== CI workflows ==="
    ls -la .github/workflows/
    echo "=== tests.yml (first 50 lines) ==="
    head -50 .github/workflows/tests.yml
    echo "=== apps/desktop size ==="
    find apps/desktop -type f | wc -l
  } > /tmp/pre-sync-state.txt
  ```
  Gate: `/tmp/pre-sync-state.txt` existe y tiene contenido.

### Wave 2 — Merge Execution (sequential, no delegation needed)

- [ ] **T2.1**: Pull upstream sin commit, sin fast-forward.
  ```bash
  git pull --no-commit --no-ff upstream main
  ```
  **Expectativa:** ~150-250 conflict markers en los 12 archivos protegidos + AGENTS.md + tests.yml + upstream-sync.yml + janitor-ci.yml.
  Gate: `git status` muestra archivos en `Unmerged paths` y `Changes to be committed`.

- [ ] **T2.2**: Resolver conflictos con `git checkout --ours` en archivos Janitor-only.
  ```bash
  # Janitor-only files (deben ganar nosotros)
  git checkout --ours \
    janitor_cli.py \
    janitor_update_core.py \
    janitor_update_bootstrap.py \
    janitor_ext/ \
    scripts/janitor-install.sh \
    scripts/janitor-finalize-deploy.sh \
    assets/janitor/ \
    skills/janitor-agentmemory/ \
    skills/janitor-browser/ \
    skills/janitor-code-review-agent/ \
    skills/janitor-config-audit/ \
    skills/janitor-core/ \
    skills/janitor-firecrawl/ \
    skills/janitor-honcho/ \
    skills/janitor-onboarding/ \
    skills/janitor-opendesign/ \
    skills/janitor-playwright/ \
    skills/janitor-repo-research-agent/ \
    skills/janitor-vault/ \
    .github/workflows/janitor-ci.yml \
    .github/workflows/upstream-sync.yml \
    .github/workflows/tests.yml \
    AGENTS.md \
    MERGE_GUIDE.md
  git add janitor_cli.py janitor_update_core.py janitor_update_bootstrap.py \
    janitor_ext/ scripts/janitor-install.sh scripts/janitor-finalize-deploy.sh \
    assets/janitor/ skills/janitor-*/ .github/workflows/janitor-ci.yml \
    .github/workflows/upstream-sync.yml .github/workflows/tests.yml \
    AGENTS.md MERGE_GUIDE.md
  ```
  Gate: `git diff --cached --stat | grep -E "janitor|skills/janitor"` muestra los archivos restaurados.

- [ ] **T2.3**: Para los 12 archivos protegidos del core (`cli.py`, `run_agent.py`, `model_tools.py`, `toolsets.py`, `hermes_state.py`, `hermes_constants.py`, `hermes_logging.py`, `hermes_cli/main.py`, `hermes_cli/banner.py`, `hermes_cli/commands.py`, `hermes_cli/config.py`, `hermes_cli/web_server.py`): usar `git checkout --theirs` y luego re-aplicar branding en T3.2.
  ```bash
  git checkout --theirs \
    cli.py run_agent.py model_tools.py toolsets.py \
    hermes_state.py hermes_constants.py hermes_logging.py \
    hermes_cli/main.py hermes_cli/banner.py \
    hermes_cli/commands.py hermes_cli/config.py \
    hermes_cli/web_server.py
  git add cli.py run_agent.py model_tools.py toolsets.py \
    hermes_state.py hermes_constants.py hermes_logging.py \
    hermes_cli/main.py hermes_cli/banner.py \
    hermes_cli/commands.py hermes_cli/config.py \
    hermes_cli/web_server.py
  ```
  Gate: los 12 archivos están staged sin conflict markers.

- [ ] **T2.4**: Para `hermes_cli/main.py` y `hermes_cli/banner.py`, NO perder las otras modificaciones upstream (líneas 2448, 2455, 4160, 5662, 7644, 7811, 7825, 7956, 10575 ya tienen `Hermes Agent` de upstream y nuestro fork NO los había tocado). El directive #12 aplica solo a **tests** y al **banner version label** (líneas 231 y 425). El resto queda como upstream lo tiene.

  **Decisión:** después de T2.3, re-aplicar branding solo en las 2 líneas críticas.
  Gate: `git diff --cached hermes_cli/main.py | grep "Hermes Agent v" | wc -l` debe ser 1 (la línea 231 que tiene `THE JANITOR`).

- [ ] **T2.5**: Resolver conflictos restantes con `git checkout --theirs` (todo lo demás, código funcional nuevo, no protegido).
  ```bash
  # Ver qué conflictos quedan
  git diff --name-only --diff-filter=U
  # Para los que queden (probablemente pocos, ~10-30), aceptar theirs
  # Esto es código nuevo que no hemos tocado
  for f in $(git diff --name-only --diff-filter=U); do
    git checkout --theirs "$f"
    git add "$f"
  done
  ```
  Gate: `git diff --name-only --diff-filter=U` está vacío.

- [ ] **T2.6**: Verificar que `git status` muestra solo el merge en progreso, sin `Unmerged paths`.
  ```bash
  git status | grep -E "Unmerged paths|both modified"
  ```
  Gate: sin output.

### Wave 3 — Cleanup Tests + Branding (sequential)

- [ ] **T3.1**: Identificar qué tests deben sobrevivir (Janitor + apps/desktop pre-existentes).
  ```bash
  # Antes del merge, ya teníamos estos tests:
  git show main:tests/test_janitor_cli.py > /dev/null && echo "janitor_cli: OK"
  git show main:tests/test_janitor_update_bootstrap.py > /dev/null && echo "janitor_update_bootstrap: OK"
  git show main:tests/test_telegram_janitor_branding.py > /dev/null && echo "telegram_janitor_branding: OK"
  git show main:tests/test_janitor_update_core.py > /dev/null && echo "janitor_update_core: OK"

  # Los tests de apps/desktop/electron/*.test.cjs que ya teníamos del sync v0.15.1
  # (los preservamos, son código funcional, no tests Python de Hermes)
  find apps/desktop -name "*.test.*" | head
  ```
  Gate: lista clara de qué tests mantener.

- [ ] **T3.2**: Re-aplicar branding en las 2 líneas críticas.
  ```bash
  # hermes_cli/main.py línea 231
  sed -i 's|print(f"Hermes Agent v{__version__} ({__release_date__})")|print(f"THE JANITOR v{__version__} ({__release_date__})")|' hermes_cli/main.py

  # hermes_cli/banner.py línea 425
  sed -i 's|base = f"Hermes Agent v{VERSION} ({RELEASE_DATE})"|base = f"THE JANITOR v{VERSION} ({RELEASE_DATE})"|' hermes_cli/banner.py

  git add hermes_cli/main.py hermes_cli/banner.py
  ```
  Gate: `grep -c "THE JANITOR v" hermes_cli/main.py hermes_cli/banner.py` → `1 1`.

- [ ] **T3.3**: Borrar los tests upstream mergeados, restaurar los Janitor + apps/desktop pre-existentes.
  ```bash
  # Hacer backup de los tests que vinieron del sync v0.15.1 (apps/desktop/.test.cjs files)
  # En realidad NO los borramos, están en apps/desktop/, no en tests/.

  # Borrar todos los tests/ upstream
  git rm -r tests/

  # Restaurar los tests Janitor (4 files) + los archivos comunes (conftest.py, _isolate_plugin.py, __init__.py)
  git checkout HEAD -- tests/__init__.py tests/conftest.py tests/_isolate_plugin.py
  git checkout main -- tests/test_janitor_cli.py tests/test_janitor_update_bootstrap.py tests/test_telegram_janitor_branding.py tests/test_janitor_update_core.py

  git add tests/
  ```
  Gate: `ls tests/ | head -20` muestra solo archivos Janitor + los comunes.

- [ ] **T3.4**: Verificar que los tests de `apps/desktop/` (subtree Electron) sobrevivieron intactos.
  ```bash
  find apps/desktop -name "*.test.*" | wc -l
  ```
  Gate: número > 0 (los tests Electron del sync previo siguen ahí).

### Wave 4 — Verify CI workflows (sequential)

- [ ] **T4.1**: Verificar que `tests.yml` sigue podado a 3 tests (más el `test_janitor_update_core.py` que se agregó después).
  ```bash
  grep -A 30 "Janitor-specific tests" .github/workflows/tests.yml | head -40
  ```
  Gate: el comentario sobre la poda está intacto, la lista incluye los 4 archivos.

- [ ] **T4.2**: Verificar que `upstream-sync.yml` está presente.
  ```bash
  ls -la .github/workflows/upstream-sync.yml
  head -30 .github/workflows/upstream-sync.yml
  ```
  Gate: el archivo existe y contiene el job `upstream-sync-verify`.

- [ ] **T4.3**: Verificar que `janitor-ci.yml` está presente.
  ```bash
  ls -la .github/workflows/janitor-ci.yml
  ```
  Gate: el archivo existe.

- [ ] **T4.4**: Si upstream agregó `supply-chain-audit.yml` o `typecheck.yml` que no teníamos, aceptarlos (`--theirs` ya debería haberlos traido en T2.5).
  ```bash
  ls .github/workflows/supply-chain-audit.yml .github/workflows/typecheck.yml
  ```
  Gate: ambos archivos presentes (ya los tenemos del sync previo v0.15.1).

### Wave 5 — Run 7 Validation Gates (sequential, must all pass)

- [ ] **T5.1**: Gate 1 — Working tree clean antes de commitear (todos los cambios staged).
  ```bash
  git status | grep -E "Untracked|not staged|Unmerged"
  ```
  Gate: sin output.

- [ ] **T5.2**: Gate 2 — Branding intacto.
  ```bash
  grep -c "THE JANITOR v" hermes_cli/main.py hermes_cli/banner.py
  ```
  Gate: `1 1`.

- [ ] **T5.3**: Gate 3 — Janitor files intactos.
  ```bash
  git diff upstream/main -- janitor_cli.py janitor_update_core.py janitor_update_bootstrap.py janitor_ext/ scripts/janitor-install.sh scripts/janitor-finalize-deploy.sh
  ```
  Gate: output vacío.

- [ ] **T5.4**: Gate 4 — Tests Janitor pasan.
  ```bash
  scripts/run_tests.sh \
    tests/test_janitor_cli.py \
    tests/test_janitor_update_bootstrap.py \
    tests/test_telegram_janitor_branding.py \
    -q
  ```
  Gate: 0 failures, exit code 0.

- [ ] **T5.5**: Gate 5 — CI workflows correctos.
  ```bash
  ls .github/workflows/{tests.yml,upstream-sync.yml,janitor-ci.yml,supply-chain-audit.yml,typecheck.yml}
  ```
  Gate: los 5 archivos presentes.

- [ ] **T5.6**: Gate 6 — `tests.yml` sigue podado.
  ```bash
  grep -c "test_janitor_cli\|test_janitor_update_bootstrap\|test_telegram_janitor_branding" .github/workflows/tests.yml
  ```
  Gate: ≥ 3 menciones (los 3 tests aparecen en el workflow).

- [ ] **T5.7**: Gate 7 — `janitor --version` funciona.
  ```bash
  source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null
  python -c "from janitor_cli import main" 2>&1
  python -m janitor_cli --version 2>&1 | head -3
  ```
  Gate: imprime `THE JANITOR v0.16.0 (...)`.

### Wave 6 — Commit (sequential, no delegation needed)

- [ ] **T6.1**: Commitear el merge.
  ```bash
  git commit -m "$(cat <<'EOF'
  chore(sync): v0.16.0 from upstream main

  Sincronización de Hermes v0.16.0 (upstream @ 2a14e8957) al fork Janitor.

  Incorporado:
  - 1,607 commits upstream (rango 2026-03-30 → 2026-06-14)
  - 7 parches de seguridad críticos (SSH/credential gate, MCP exfil, SSL guard,
    gateway fail-closed, /api/status host-leak, Codex token rotation,
    Anthropic replay redaction)
  - 5 releases: v2026.5.28, v2026.5.29, v2026.5.29.2, v2026.6.5
  - Nuevos módulos: agent/coding_context.py, agent/ssl_guard.py,
    cron/blueprint_catalog.py, gateway/platforms/whatsapp_cloud.py
  - Nuevos providers: zai (GLM-5.2), langfuse observability
  - Nuevos platforms: photon, simplex, teams
  - 11 skills nuevos + 11 optional-skills nuevos
  - God-file refactor: cli.py y gateway/run.py (Phase 2/3)
  - Config migration v11→v12, write_mode → write_approval

  Preservado (directivas Janitor):
  - Branding THE JANITOR (hermes_cli/main.py:231, hermes_cli/banner.py:425)
  - 12 skills janitor-*
  - 3 tests en PR gate + upstream-sync-verify en workflow_dispatch
  - janitor_update_core.py (directiva #13)
  - scripts/janitor-install.sh minimalista (directiva #8)
  - Cero renames 'hermes' → 'janitor' (directiva #1)

  Descartado:
  - Tests upstream (per directiva #11; el job upstream-sync-verify
    corre la suite completa contra el código post-merge)
  - apps/desktop/ (traído pero no publicado, per directiva #4+#8)
  - chore(release): map author commits (bookkeeping irrelevante)

  Próximos pasos:
  1. Mergear a main
  2. Trigger upstream-sync-verify workflow_dispatch
  3. Si verde, tag v0.16.0-janitor.1
  EOF
  )"
  ```
  Gate: `git log -1 --format='%H %s'` muestra el merge commit.

### Wave 7 — Post-merge: Migration Script + MERGE_GUIDE (sequential, parallel possible)

- [ ] **T7.1**: Crear `scripts/migrate-janitor-v0.16.0.sh` con la migración de `write_mode` → `write_approval`.
  ```bash
  #!/bin/bash
  # migrate-janitor-v0.16.0.sh
  # Migración de v0.15.x → v0.16.0 (Hermes upstream #43354)
  #
  # Cambios:
  # - `memory.write_mode` y `skills.write_mode` (tri-state) se renombran a
  #   `write_approval` (boolean, default false).
  #   Mapeo: 'approve' → true; 'on' / 'off' / unset → false
  # - `_config_version` se incrementa 28 → 29.
  # - Slash commands: '/memory mode <on|off|approve>' → '/memory approval <on|off>'
  #   (mode se mantiene como alias de back-compat).
  #
  # Ejecutar como root del usuario, no como root del sistema.

  set -euo pipefail
  CONFIG="${JANITOR_CONFIG:-$HOME/.janitor/config.yaml}"
  [ -f "$CONFIG" ] || { echo "No config at $CONFIG — nothing to migrate"; exit 0; }

  python3 - "$CONFIG" <<'PY'
  import sys, yaml
  from pathlib import Path

  p = Path(sys.argv[1])
  data = yaml.safe_load(p.read_text()) or {}

  for section in ('memory', 'skills'):
      sub = data.get(section) or {}
      mode = sub.pop('write_mode', None)
      if mode is not None:
          sub['write_approval'] = (mode == 'approve')

  # Bump config version
  data['_config_version'] = max(int(data.get('_config_version', 0)), 29)

  p.write_text(yaml.safe_dump(data, sort_keys=False))
  print(f"Migrated {p} → write_approval + _config_version=29")
  PY
  ```
  Y darle chmod +x. Gate: el script existe y es ejecutable.

- [ ] **T7.2**: Actualizar `MERGE_GUIDE.md` con la sección de la sync.
  ```bash
  # Agregar al final de MERGE_GUIDE.md:
  cat >> MERGE_GUIDE.md <<'EOF'

  ## v2026.6.5 Sync (Hermes v0.16.0)

  **Rango:** `1a710e8df` → `2a14e8957` (1,607 commits, 996 files, +80,859/-26,205)
  **Fecha:** 2026-06-15
  **Estrategia:** Full merge + cherry-pick selectivo (rama `upstream-sync-2026-06`)

  ### Cambios adoptados
  - 7 parches de seguridad críticos
  - agent/coding_context.py, agent/ssl_guard.py, cron/blueprint_catalog.py
  - gateway/platforms/whatsapp_cloud.py
  - Providers zai (GLM-5.2), langfuse observability
  - Platforms photon, simplex, teams
  - 11 skills nuevos, 11 optional-skills nuevos
  - Config v11→v12, write_mode→write_approval, _config_version 28→29

  ### Cambios descartados
  - Tests upstream (directiva #11)
  - apps/desktop/ (traído pero no publicado)
  - chore(release) author mappings

  ### Post-merge para usuarios
  1. Ejecutar `bash scripts/migrate-janitor-v0.16.0.sh` (renombra `write_mode` a `write_approval`).
  2. Verificar `~/.janitor/config.yaml` tiene `_config_version: 29`.
  3. Reiniciar `janitor`.

  ### Branding
  - `THE JANITOR` preservado en `hermes_cli/main.py:231` y `hermes_cli/banner.py:425`.
  - Re-aplicado automáticamente durante el merge.

  ### CI
  - `tests.yml` sigue podado a 3 tests.
  - `upstream-sync.yml` presente (job `upstream-sync-verify`).
  - `janitor-ci.yml` presente.
  - `supply-chain-audit.yml` y `typecheck.yml` aceptados.
  EOF
  ```
  Gate: `MERGE_GUIDE.md` tiene la nueva sección.

### Wave 8 — Tag + Merge to main (sequential)

- [ ] **T8.1**: Tag anotado.
  ```bash
  git tag -a v0.16.0-janitor.1 -m "Janitor fork sync to Hermes v0.16.0 (upstream 2a14e8957)

  Incorpora 1,607 commits upstream entre v0.15.1 y v0.16.0.
  Preserva las 13 directivas del fork.
  Ver MERGE_GUIDE.md sección 'v2026.6.5 Sync' para detalles completos."
  ```
  Gate: `git tag -l v0.16.0-janitor.1` muestra el tag.

- [ ] **T8.2**: Push de la rama.
  ```bash
  git push origin upstream-sync-2026-06 --tags
  ```
  Gate: `git push` exit 0.

- [ ] **T8.3**: Crear PR en GitHub con título y descripción estándar.
  ```bash
  gh pr create \
    --base main \
    --head upstream-sync-2026-06 \
    --title "chore(sync): v0.16.0 from upstream main" \
    --body "Sincronización del fork Janitor con Hermes v0.16.0. Ver MERGE_GUIDE.md para detalles.

  **Importante:** después de mergear, ejecutar \`bash scripts/migrate-janitor-v0.16.0.sh\` en los deploys existentes para renombrar \`write_mode\` → \`write_approval\`."
  ```
  Gate: `gh pr view --json number` devuelve un PR number.

- [ ] **T8.4**: Esperar que el PR pase los 3 tests Janitor y mergearlo.
  ```bash
  # Espera al check del PR gate
  gh pr checks --watch

  # Si pasa, merge con squash
  gh pr merge --squash --delete-branch
  ```
  Gate: el PR está mergeado a main.

### Wave 9 — Post-merge Verification (sequential, can delegate to subagents)

- [ ] **T9.1**: Trigger `upstream-sync-verify` workflow en GitHub.
  ```bash
  gh workflow run upstream-sync.yml
  ```
  Gate: el workflow corre. Esperar 5-15 min.

- [ ] **T9.2**: Si `upstream-sync-verify` falla, abrir issue con el log.
  ```bash
  gh issue create --title "v0.16.0-janitor.1: upstream-sync-verify failed" --body "..."
  ```
  Gate: el issue está creado o el workflow pasa.

- [ ] **T9.3**: Delegar a `codebase-memory-mcp_detect_changes` para actualizar el knowledge graph.
  ```bash
  # Llamar a la tool con scope=full, base_branch=main
  ```
  Gate: el knowledge graph está actualizado.

- [ ] **T9.4**: Delegar a `tui-compilation` skill si `ui-tui/` recibió cambios upstream (51 commits).
  ```bash
  cd ui-tui && npm install && npm run build && npm test
  ```
  Gate: el TUI compila y los tests pasan.

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

Ejecutar los 7 validation gates una vez más, post-merge a main:

- [ ] **F1**: `git log main..upstream/main` → 0 commits.
- [ ] **F2**: `git status --short` → vacío.
- [ ] **F3**: 7 validation gates pasan (re-run completo).
- [ ] **F4**: `git tag -l v0.16.0-janitor.1` → tag presente.
- [ ] **F5**: `upstream-sync-verify` workflow pasó.
- [ ] **F6**: `MERGE_GUIDE.md` actualizado con la sección v2026.6.5.
- [ ] **F7**: `scripts/migrate-janitor-v0.16.0.sh` existe y es ejecutable.

Si F1-F7 todos pasan → sync completa, pasar a la directriz `finishing-a-development-branch`.

---

## Commit Strategy

- **T1.1** (pre-sync cleanup): `chore: pre-sync local changes (config-audit skill + merge guide + sisyphus state)`
- **T6.1** (merge commit): `chore(sync): v0.16.0 from upstream main` (cuerpo detallado, ver Wave 6)
- **T7.1** (migration script): `feat(migration): add migrate-janitor-v0.16.0.sh for write_mode→write_approval`
- **T7.2** (MERGE_GUIDE): `docs(merge-guide): document v2026.6.5 sync notes`
- **T8.1** (tag): `v0.16.0-janitor.1` (anotado)

Total: 4 commits + 1 tag.

---

## Success Criteria

### Verification Commands

```bash
# Después del merge, todos estos comandos deben pasar:

# 1. Sync completa
git log main..upstream/main --oneline | wc -l
# Expected: 0

# 2. Branding preservado
grep -c "THE JANITOR v" hermes_cli/main.py hermes_cli/banner.py
# Expected: 1 1

# 3. Janitor files intactos
git diff upstream/main -- janitor_cli.py janitor_update_core.py janitor_update_bootstrap.py janitor_ext/ scripts/janitor-install.sh
# Expected: (empty)

# 4. Tests Janitor pasan
scripts/run_tests.sh tests/test_janitor_cli.py tests/test_janitor_update_bootstrap.py tests/test_telegram_janitor_branding.py -q
# Expected: 0 failures

# 5. CI workflows correctos
ls .github/workflows/{tests.yml,upstream-sync.yml,janitor-ci.yml,supply-chain-audit.yml,typecheck.yml}
# Expected: 5 archivos listados

# 6. tests.yml podado
grep -c "test_janitor_cli\|test_janitor_update_bootstrap\|test_telegram_janitor_branding" .github/workflows/tests.yml
# Expected: >= 3

# 7. janitor --version
python -m janitor_cli --version
# Expected: THE JANITOR v0.16.0 (...)

# 8. apps/desktop/ no publicado
grep -r "apps/desktop" skills/janitor-onboarding/ 2>&1 | wc -l
# Expected: 0

# 9. Tag presente
git tag -l v0.16.0-janitor.1
# Expected: v0.16.0-janitor.1

# 10. Migration script presente
ls scripts/migrate-janitor-v0.16.0.sh
# Expected: (archivo existe)
```

### Final Checklist

- [ ] `git log main..upstream/main` → 0
- [ ] Branding `THE JANITOR` en 2 líneas
- [ ] 12 skills `janitor-*` intactas
- [ ] 3 tests Janitor pasan
- [ ] `tests.yml` podado
- [ ] `upstream-sync.yml` + `janitor-ci.yml` presentes
- [ ] Tag `v0.16.0-janitor.1` presente
- [ ] `scripts/migrate-janitor-v0.16.0.sh` ejecutable
- [ ] `MERGE_GUIDE.md` actualizado
- [ ] `upstream-sync-verify` workflow pasó
- [ ] Sin `apps/desktop` en onboarding
- [ ] Sin cambios en `janitor_cli.py` / `janitor_update_core.py` / `janitor_ext/`
- [ ] `hermes` no renombrado a `janitor` en código core
- [ ] `janitor --version` imprime `THE JANITOR v0.16.0`

---

## Notas y riesgos

### Riesgos principales

1. **Conflictos masivos en T2.2-T2.3**: 12 archivos protegidos + AGENTS.md + 3 workflows. La estrategia de `--ours` / `--theirs` debe ser precisa.
2. **Tests de `apps/desktop/` no se borran**: el subtree Electron del sync previo v0.15.1 ya tiene tests en `apps/desktop/electron/*.test.cjs`. Verificar T3.4.
3. **`AGENTS.md` upstream agregó "Design Philosophy + Contribution Rubric" (#42641)**: si lo descartamos con `--ours`, Janitor no recibe esa documentación. Trade-off aceptable porque AGENTS.md es del fork.
4. **5th test Janitor (`test_janitor_update_core.py`) se agregó en el fork**: verificar que sí está en el PR gate (debería estarlo, fue el commit `1a8fe0d4e`).

### Si algo sale mal — Rollback

```bash
# Antes del commit del merge (T6.1)
git merge --abort
git checkout main

# Después del commit, antes del merge a main
git reset --hard main
git checkout main
git branch -D upstream-sync-2026-06
git tag -d v0.16.0-janitor.1
git push origin :upstream-sync-2026-06
git push origin :refs/tags/v0.16.0-janitor.1

# Después del merge a main (último recurso)
git revert -m 1 <merge-commit-sha>
```

### Optimizaciones posibles

- **Si T2.5 tarda mucho** (resolver 100+ conflictos uno por uno): en lugar de loop, usar `git diff --name-only --diff-filter=U | xargs git checkout --theirs` y luego `git add -u`.
- **Si el merge genera más conflicts de los esperados**: abortar, dividir en batches por tag upstream (v2026.5.28, v2026.5.29, v2026.6.5) y cherry-pick cada batch.
- **Si T4.4 falla (workflows no están)**: aceptar `--theirs` específicamente para esos archivos en T2.5.

---

## Próximos pasos

Una vez aprobado este plan, lo ejecuto en orden:

1. **T1.1-T1.3**: Setup (5 min)
2. **T2.1-T2.6**: Merge (15-30 min, depende de conflicts)
3. **T3.1-T3.4**: Cleanup (5 min)
4. **T4.1-T4.4**: CI verify (5 min)
5. **T5.1-T5.7**: 7 validation gates (10 min)
6. **T6.1**: Commit (1 min)
7. **T7.1-T7.2**: Migration + MERGE_GUIDE (10 min)
8. **T8.1-T8.4**: Tag + PR (10 min)
9. **T9.1-T9.4**: Post-merge verify (15 min, mayormente espera)

**Total estimado: 1-2 horas** con verificación humana en T5.7 y T8.4.

¿Procedo con la ejecución, o querés revisar/ajustar el plan primero?
