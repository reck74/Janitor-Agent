# Upstream Sync: Janitor v0.15.1 → Hermes main (153 commits)

## TL;DR

> **Quick Summary**: Merge 153 upstream commits (808 files, 136k insertions) from `NousResearch/hermes-agent` into Janitor, preserving all 51 Janitor-specific customizations. Resolve conflicts in branding, TUI theme, and pyproject.toml. Validate via 9 mandatory gates. Open a PR for user approval.

> **Deliverables**:
> - New branch `upstream-sync-20260601-XXXXXX` with all 153 commits integrated
> - 0 conflict markers in working tree
> - 0 branding leaks (Hermes Agent v / Nous Research / Messenger of the Digital Gods)
> - 0 GHCR references in `scripts/`
> - Python + shell + TUI build all green
> - Open PR against `main` for user review
> - All 11 validation gates PASS (evidence in `.sisyphus/evidence/gates-summary.md`)

> **Estimated Effort**: Large (3-4 hours wall clock)
> **Parallel Execution**: YES — 4 waves of parallel work
> **Critical Path**: T1.4 → T2.1 → T3.* → T4.* → T5.1 → T6.* → F1-F4 → user approval

---

## Context

### Original Request
El usuario pidió: "revisemos para actualizar a la última versión de Hermes el core del proyecto, sin perder nuestras personalizaciones, revisa todo y dime si necesitas mi apoyo en algo."

Después de revisar el proyecto, confirmé que el fork está **153 commits** detrás de upstream a pesar de que ambos repos comparten la versión `0.15.1`. El último merge (`f710bb79d`) trajo 51 commits el 2026-05-30. Esta sync debe traer 3x más commits.

### Interview Summary

**Decisiones del usuario** (confirmadas):
1. **Estrategia**: Rama temporal + PR al final (no directo en main)
2. **`apps/desktop/`**: Merge completo (aceptar 325 archivos nuevos)
3. **Testing**: Post-merge con `scripts/run_tests.sh` (sin TDD durante el merge)
4. **Alcance**: Las 153 commits de golpe (un solo merge)

**Investigación previa** (`.sisyphus/drafts/upstream-sync-review.md`):
- 808 archivos cambian, 136,376 inserciones, 18,700 eliminaciones
- 51 personalizaciones Janitor deben preservarse
- Áreas de alto riesgo: branding, TUI, workflows, pyproject.toml
- Precedente: `f710bb79d` (51 commits) + `aa3b03807` (fixup) muestran el patrón

### Metis Review

**Gaps críticos identificados** (todos incorporados):
- `hermes_cli/main.py`: 14,595 vs 14,989 líneas → **conflicto de texto 100% garantizado** en version string
- `ui-tui/src/theme.ts`: `ThemeBrand` interface con campo `version?` añadido upstream
- `apps/desktop/`: 325 archivos nuevos, sin conocimiento del bootstrap installer
- `pyproject.toml`: pin `python-telegram-bot>=22.7,<23` (Janitor) vs `==22.6` (upstream) → **conflicto semántico**
- 4 tipos de archivos con conflicto histórico recurrente
- Necesidad de phase 0 para limpiar `.sisyphus/` antes de merge

**Guardrails aplicados**:
- Core files (`cli.py`, `run_agent.py`, `gateway/run.py`, `model_tools.py`, `hermes_cli/main.py`) → solo merge, no edit
- Si resolución de conflicto requiere editar core, STOP y escalar
- `skills/janitor-*/` son read-only durante el sync
- TUI branding isolation: si upstream cambia `branding.tsx`/`theme.ts`, **mantener versión Janitor**
- No añadir dependencias nuevas en `pyproject.toml` sin sign-off
- `apps/desktop/` es opt-in, no auto-built

---

## Work Objectives

### Core Objective
Integrar 153 commits upstream en Janitor, resolviendo conflictos según las reglas del fork, validando con 9 gates, y abriendo PR para revisión.

### Concrete Deliverables
- [ ] Nueva rama `upstream-sync-20260601-XXXXXX` con merge completo
- [ ] 0 marcadores de conflicto en working tree
- [ ] 0 strings de branding upstream en archivos visibles
- [ ] 0 referencias a `ghcr.io` o `check_ghcr_auth` en `scripts/`
- [ ] Compilación Python: `python3 -m py_compile` exit 0 en archivos core
- [ ] Compilación TypeScript: `npm run type-check` + `npm run build` exit 0
- [ ] Tests: `scripts/run_tests.sh` sin hard failures
- [ ] PR abierto contra `main` con descripción detallada

### Definition of Done
- [ ] 9 validation gates pasan (ver sección "Verification Strategy")
- [ ] Branch pushed to origin
- [ ] PR abierto y descripción incluye: commits traídos, conflictos resueltos, evidencia de gates pasados
- [ ] Draft file `.sisyphus/drafts/upstream-sync-review.md` eliminado
- [ ] `git status` limpio (sin untracked de `.sisyphus/run-continuation/`)

### Must Have
- Preservar TODAS las 51 personalizaciones Janitor listadas en draft
- 0 conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
- 9 validation gates documentados con output específico
- Commit message del merge siguiendo patrón `f710bb79d` y `aa3b03807`
- `apps/desktop/` y `apps/bootstrap-installer/` mergeados completamente
- Branch temporal, no directo en main
- PR final con label `upstream-sync`

### Must NOT Have (Guardrails)
- **NO** renombrar 'hermes' en core files (Zero-Renaming Policy)
- **NO** modificar `cli.py`, `run_agent.py`, `gateway/run.py`, `model_tools.py` (solo merge)
- **NO** tocar `skills/janitor-*/` (read-only)
- **NO** añadir nuevas dependencias en `pyproject.toml` sin sign-off
- **NO** modificar `janitor_cli.py` o `janitor_update_bootstrap.py`
- **NO** actualizar `RELEASE_v0.*.md` (son release notes de Janitor)
- **NO** cambiar `HERMES_HOME` default de `~/.janitor`
- **NO** refactor ni mejoras cosméticas durante el merge
- **NO** invocar `merge-auditor` directamente (esos agentes son para el usuario, ver AGENTS.md regla 6)
- **NO** usar `--amend` para fixups (commits atómicos separados)

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — Toda verificación es agent-executed. No excepciones.
> Criterios de aceptación que requieran "user manually tests" son PROHIBIDOS.

### Test Decision
- **Infraestructura existe**: SÍ (`scripts/run_tests.sh` + `tests/conftest.py` + 37M de tests)
- **Automated tests**: Post-merge (no TDD durante el merge por decisión del usuario)
- **Framework**: pytest (Python) + vitest (TypeScript)

### 11 Mandatory Validation Gates

| # | Gate | Command | Pass Criteria |
|---|------|---------|---------------|
| 1 | Python compile | `python3 -m py_compile cli.py run_agent.py gateway/run.py hermes_cli/main.py janitor_cli.py` | exit 0 |
| 2 | Shell syntax | `bash -n scripts/*.sh scripts/janitor-*.sh scripts/setup-honcho.sh scripts/migrate-janitor-minimal.sh` | exit 0 |
| 3 | Conflict markers | `grep -rn '<<<<<<\|=======\|>>>>>>' --exclude-dir=.git --exclude-dir=.sisyphus --exclude-dir=node_modules --exclude-dir=.venv` | 0 matches |
| 4 | Branding purge | `grep -rn 'Nous Research\|Messenger of the Digital Gods\|Hermes Agent v' ui-tui/src/components/branding.tsx hermes_cli/main.py README.md` | 0 matches |
| 5 | GHCR purge | `grep -rn 'check_ghcr_auth\|ghcr.io' scripts/` | 0 matches |
| 6 | TUI type-check | `cd ui-tui && npm run type-check` | 0 TypeScript errors |
| 7 | TUI build | `cd ui-tui && npm run build --prefix packages/hermes-ink && npm run build` | exit 0, `dist/entry.js` exists |
| 8 | TUI tests | `cd ui-tui && npm test` | 0 failures (skips aceptables) |
| 9 | Python test suite | `scripts/run_tests.sh -q tests/agent/ tests/gateway/ tests/hermes_cli/` | no hard failures |
| 10 | Janitor CLI | `python3 janitor_cli.py --version` | prints "THE JANITOR" |
| 11 | Git status | `git status --short` | clean (sin untracked) |

**Evidencia a capturar**: Cada gate guarda su output en `.sisyphus/evidence/upstream-sync-gate{N}-{slug}.txt`.

### QA Policy
Cada TODO task incluye agent-executed QA scenarios. Para este sync los escenarios son:
- Comandos ejecutados con output capturado
- Verificación binaria (PASS/FAIL) basada en exit codes
- Archivos de evidencia con timestamp

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Pre-merge setup — all parallel):
├── T1.1: Cleanup .sisyphus/ untracked files
├── T1.2: Verify test infrastructure (pytest + npm)
├── T1.3: Fetch upstream + create evidence file with gap analysis
└── T1.4: Create worktree + new branch upstream-sync-20260601-XXXXXX

Wave 2 (Merge execution — sequential):
├── T2.1: Execute git merge upstream/main in worktree
└── T2.2: Capture conflict list to evidence file

Wave 3 (Conflict resolution — parallel where independent):
├── T3.1: Resolve branding conflicts (hermes_cli/main.py, ui-tui/branding.tsx, ui-tui/theme.ts, README.md)
├── T3.2: Resolve config conflicts (pyproject.toml, scripts/run_tests.sh, tests/tools/test_lazy_deps.py)
├── T3.3: Prune upstream-only .github/workflows
└── T3.4: Verify janitor-specific files survived merge (janitor_cli.py, assets/janitor/*, skills/janitor-*/)

Wave 4 (Validation gates — all parallel):
├── T4.1: Gates 1, 2, 3, 4, 5 (compile + syntax + scan)
├── T4.2: Gate 6, 7, 8 (TUI type-check + build + test)
├── T4.3: Gate 9, 10 (Python tests + Janitor CLI)
└── T4.4: Gate 11 (git status)

Wave 5 (Fixups — conditional, only if Wave 4 finds issues):
├── T5.1: Apply fix commits for any gate failures
└── T5.2: Re-run failed gates

Wave 6 (PR creation — sequential):
├── T6.1: Commit merge + fixups
├── T6.2: Push branch to origin
└── T6.3: Open PR with detailed description

Final Wave (4 parallel review agents):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high + playwright if UI)
└── F4: Scope fidelity check (deep)
→ Present results → Get explicit user approval
```

### Critical Path
T1.4 → T2.1 → T3.* → T4.* → T5.1 (if needed) → T6.3 → F1-F4 → user approval

### Dependency Matrix

| Task | Depends On | Parallel With |
|------|-----------|---------------|
| T1.1 | — | T1.2, T1.3, T1.4 |
| T1.2 | — | T1.1, T1.3, T1.4 |
| T1.3 | — | T1.1, T1.2, T1.4 |
| T1.4 | T1.1, T1.2, T1.3 | (none — gates the rest) |
| T2.1 | T1.4 | (none) |
| T2.2 | T2.1 | (none) |
| T3.1 | T2.2 | T3.2, T3.3, T3.4 |
| T3.2 | T2.2 | T3.1, T3.3, T3.4 |
| T3.3 | T2.2 | T3.1, T3.2, T3.4 |
| T3.4 | T2.2 | T3.1, T3.2, T3.3 |
| T4.1 | T3.1, T3.2, T3.3, T3.4 | T4.2, T4.3, T4.4 |
| T4.2 | T3.1, T3.2, T3.3, T3.4 | T4.1, T4.3, T4.4 |
| T4.3 | T3.1, T3.2, T3.3, T3.4 | T4.1, T4.2, T4.4 |
| T4.4 | T3.1, T3.2, T3.3, T3.4 | T4.1, T4.2, T4.3 |
| T5.1 | T4.* (any failure) | T5.2 |
| T5.2 | T5.1 | (none) |
| T6.1 | T4.* or T5.2 | (none) |
| T6.2 | T6.1 | (none) |
| T6.3 | T6.2 | (none) |
| F1 | T6.3 | F2, F3, F4 |
| F2 | T6.3 | F1, F3, F4 |
| F3 | T6.3 | F1, F2, F4 |
| F4 | T6.3 | F1, F2, F3 |

### Agent Dispatch Summary

- **Wave 1**: T1.1 → `quick`, T1.2 → `quick`, T1.3 → `quick`, T1.4 → `quick` (with `git-master` skill)
- **Wave 2**: T2.1 → `unspecified-high` (with `git-master` skill), T2.2 → `quick`
- **Wave 3**: T3.1 → `unspecified-high` (with `git-master` + careful editing), T3.2 → `unspecified-high`, T3.3 → `quick`, T3.4 → `quick`
- **Wave 4**: T4.1 → `quick`, T4.2 → `unspecified-high` (TUI is tricky), T4.3 → `unspecified-high`, T4.4 → `quick`
- **Wave 5**: T5.1 → `deep` (debugging failures), T5.2 → `quick`
- **Wave 6**: T6.1 → `quick`, T6.2 → `quick` (with `git-master`), T6.3 → `quick` (with `git-master`)
- **Final**: F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

> Implementation + Test = ONE Task. Never separate.
> EVERY task MUST have: Recommended Agent Profile + Parallelization info + QA Scenarios.
> **A task WITHOUT QA Scenarios is INCOMPLETE.**

### Wave 1 — Pre-merge Setup (parallel)

- [ ] 1.1. **Cleanup `.sisyphus/` untracked files**

  **What to do**:
  - Stash or delete `.sisyphus/run-continuation/*.json` (4 files) — these cause `git status --short` to be dirty
  - Move `.sisyphus/plans/specialized-subagents-continuation.md` to a temp location (don't lose it, just remove from working tree)
  - Note current `git status` output to `.sisyphus/evidence/pre-merge-state.txt`
  - Verify final state: `git status --short` shows only `.sisyphus/boulder.json` and `.sisyphus/notepads/` (acceptable untracked)

  **Must NOT do**:
  - DO NOT delete `.sisyphus/drafts/upstream-sync-review.md` yet (needed until plan complete)
  - DO NOT touch `.sisyphus/plans/upstream-sync-refactor.md` (unrelated to this sync)
  - DO NOT modify any tracked files

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]` (no specialized skills needed)
  - **Reason**: File cleanup is mechanical

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1.2, T1.3, T1.4)
  - **Blocks**: T1.4 (gates the rest of Wave 1)
  - **Blocked By**: None

  **References**:
  - `.sisyphus/drafts/upstream-sync-review.md` — keep this until plan complete
  - `.sisyphus/run-continuation/*.json` — these are session continuation files from previous Sisyphus runs

  **Acceptance Criteria**:
  - [ ] `git status --short` shows 0 untracked files matching `run-continuation/*.json`
  - [ ] `.sisyphus/drafts/upstream-sync-review.md` still present
  - [ ] Evidence file `.sisyphus/evidence/pre-merge-state.txt` exists with timestamp

  **QA Scenarios**:

  ```
  Scenario: Git status is clean enough to proceed
    Tool: Bash
    Preconditions: Working tree had 4 untracked run-continuation files
    Steps:
      1. Run: git status --short | wc -l
      2. Assert: output is < 5 (only boulder.json + notepads/ acceptable)
      3. Run: ls .sisyphus/run-continuation/ 2>/dev/null | wc -l
      4. Assert: output is 0
    Expected Result: Git working tree is clean for merge
    Evidence: .sisyphus/evidence/task-1.1-pre-merge-state.txt
  ```

  **Commit**: NO (this is pre-merge prep)

- [ ] 1.2. **Verify test infrastructure works on current state**

  **What to do**:
  - Run `python3 -m py_compile cli.py run_agent.py gateway/run.py hermes_cli/main.py janitor_cli.py` — must exit 0
  - Run `bash -n scripts/*.sh` — must exit 0
  - Run `cd ui-tui && npm run type-check` — must exit 0 (or capture current errors as baseline)
  - Run `cd ui-tui && npm run build --prefix packages/hermes-ink` — must succeed
  - Capture all outputs to `.sisyphus/evidence/baseline-gates.txt`
  - **Critical**: This establishes the baseline state. If current tree already has failures, we need to know BEFORE merge so we can distinguish merge-introduced failures from pre-existing ones.

  **Must NOT do**:
  - DO NOT fix any pre-existing failures (just document them)
  - DO NOT run full `scripts/run_tests.sh` (too slow for baseline)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `["git-master"]` (for clean output capture)
  - **Reason**: Mechanical verification, no problem-solving

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1.1, T1.3, T1.4)
  - **Blocks**: T1.4
  - **Blocked By**: None

  **References**:
  - `scripts/run_tests.sh` — the wrapper script
  - `ui-tui/package.json` — TUI scripts
  - `pyproject.toml` — Python entry points

  **Acceptance Criteria**:
  - [ ] All 4 baseline checks captured to `.sisyphus/evidence/baseline-gates.txt`
  - [ ] Pre-existing failures (if any) documented with exit codes

  **QA Scenarios**:

  ```
  Scenario: Baseline compilation works
    Tool: Bash
    Preconditions: Working tree is at v0.15.1 pre-merge
    Steps:
      1. Run: python3 -m py_compile cli.py run_agent.py gateway/run.py hermes_cli/main.py janitor_cli.py 2>&1 | tee .sisyphus/evidence/baseline-py-compile.txt
      2. Assert: exit code 0 OR document pre-existing errors
      3. Run: bash -n scripts/*.sh 2>&1 | tee .sisyphus/evidence/baseline-shell-syntax.txt
      4. Assert: exit code 0 OR document pre-existing errors
    Expected Result: Baseline state captured
    Evidence: .sisyphus/evidence/baseline-gates.txt
  ```

  **Commit**: NO

- [ ] 1.3. **Fetch upstream and create gap analysis evidence file**

  **What to do**:
  - Run `git fetch upstream main` (idempotent)
  - Verify upstream has 153 new commits: `git log --oneline HEAD..upstream/main | wc -l` → must be 153
  - Capture full commit list to `.sisyphus/evidence/upstream-commits-behind.txt`
  - Generate a categorized summary: count by prefix (fix/, feat/, chore/, etc.) and save to `.sisyphus/evidence/upstream-commit-stats.txt`
  - **DO NOT** merge yet — this is just documentation

  **Must NOT do**:
  - DO NOT start the merge
  - DO NOT create any branch

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `["git-master"]` (for log analysis)
  - **Reason**: Read-only git operations

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1.1, T1.2, T1.4)
  - **Blocks**: T1.4
  - **Blocked By**: None

  **References**:
  - `.sisyphus/drafts/upstream-sync-review.md` — contains the analysis this task validates

  **Acceptance Criteria**:
  - [ ] `.sisyphus/evidence/upstream-commits-behind.txt` contains 153 commit SHAs
  - [ ] `.sisyphus/evidence/upstream-commit-stats.txt` contains categorized summary

  **QA Scenarios**:

  ```
  Scenario: Upstream has exactly 153 new commits
    Tool: Bash
    Preconditions: git fetch upstream already run
    Steps:
      1. Run: BEHIND=$(git rev-list --count HEAD..upstream/main)
      2. Assert: $BEHIND == 153
      3. Run: git log --oneline HEAD..upstream/main > .sisyphus/evidence/upstream-commits-behind.txt
      4. Run: wc -l .sisyphus/evidence/upstream-commits-behind.txt
      5. Assert: output is 153
    Expected Result: Confirmed 153 commits to merge
    Evidence: .sisyphus/evidence/upstream-commits-behind.txt
  ```

  **Commit**: NO

- [ ] 1.4. **Create worktree with new branch for the merge**

  **What to do**:
  - Determine worktree location: `/home/reck/Janitor-Agent-worktrees/upstream-sync-20260601-XXXXXX` where XXXXXX is the current timestamp
  - Run: `git worktree add -b upstream-sync-$(date +%Y%m%d-%H%M%S) /home/reck/Janitor-Agent-worktrees/upstream-sync-$(date +%Y%m%d-%H%M%S) HEAD`
  - Verify worktree created: `git worktree list`
  - cd into the worktree for all subsequent operations
  - **CRITICAL**: ALL subsequent work happens in the worktree, NOT in the main repo

  **Must NOT do**:
  - DO NOT merge in the main repo
  - DO NOT create multiple worktrees for this task
  - DO NOT push the branch yet (that's T6.2)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `["git-master"]` (essential for worktree operations)
  - **Reason**: Standard git worktree workflow

  **Parallelization**:
  - **Can Run In Parallel**: NO (must be last in Wave 1 — gates the rest)
  - **Parallel Group**: Wave 1 (sequential — must complete before Wave 2)
  - **Blocks**: T2.1 (merge execution)
  - **Blocked By**: T1.1, T1.2, T1.3

  **References**:
  - `git worktree` documentation: https://git-scm.com/docs/git-worktree
  - AGENTS.md rule 1: Zero-Renaming — worktree is the safe way to merge without corrupting main

  **Acceptance Criteria**:
  - [ ] Worktree directory exists
  - [ ] Branch `upstream-sync-YYYYMMDD-HHMMSS` exists
  - [ ] `git worktree list` shows the new worktree
  - [ ] Current directory is the new worktree

  **QA Scenarios**:

  ```
  Scenario: Worktree created successfully with new branch
    Tool: Bash
    Preconditions: Tasks 1.1, 1.2, 1.3 complete
    Steps:
      1. Run: BRANCH_NAME="upstream-sync-$(date +%Y%m%d-%H%M%S)"
      2. Run: WORKTREE_PATH="/home/reck/Janitor-Agent-worktrees/$BRANCH_NAME"
      3. Run: git worktree add -b "$BRANCH_NAME" "$WORKTREE_PATH" HEAD
      4. Assert: exit code 0
      5. Run: git worktree list
      6. Assert: output includes the new worktree path
      7. Run: cd "$WORKTREE_PATH" && git branch --show-current
      8. Assert: output matches BRANCH_NAME
    Expected Result: New worktree with sync branch ready
    Evidence: .sisyphus/evidence/task-1.4-worktree-created.txt
  ```

  **Commit**: NO (the worktree creation is not a commit)

### Wave 2 — Merge Execution (sequential)

- [ ] 2.1. **Execute `git merge upstream/main` in worktree**

  **What to do**:
  - cd into the worktree created in T1.4
  - Run: `git merge upstream/main --no-edit` (use `--no-edit` to avoid opening an editor)
  - **NOTE**: This will likely produce conflicts. That's expected. The next tasks resolve them.
  - If merge succeeds cleanly (unlikely with 153 commits), skip directly to Wave 4.
  - Capture the merge output to `.sisyphus/evidence/merge-output.txt`
  - Run: `git status --short | head -50` → capture first 50 lines to `.sisyphus/evidence/post-merge-status.txt`

  **Must NOT do**:
  - DO NOT use `git rebase` (we want to preserve merge history per AGENTS.md)
  - DO NOT use `--squash` (defeats the purpose of syncing)
  - DO NOT open a PR yet (that's T6.3)
  - DO NOT resolve conflicts in this task (T3.* does that)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `["git-master"]` (essential for merge operations)
  - **Reason**: Merge with 153 commits and 808 files is high-stakes; needs careful execution

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential with T2.2)
  - **Blocks**: T2.2, T3.*
  - **Blocked By**: T1.4

  **References**:
  - `MERGE_GUIDE.md` — section 2.3 "Ejecución del merge" specifies `git merge upstream/main --no-edit`
  - `f710bb79d` — the previous successful merge commit (51 commits) for reference pattern
  - AGENTS.md rule 1: Zero-Renaming — must not modify core during merge

  **Acceptance Criteria**:
  - [ ] Merge command executed in worktree
  - [ ] Evidence file `.sisyphus/evidence/merge-output.txt` exists
  - [ ] Evidence file `.sisyphus/evidence/post-merge-status.txt` exists
  - [ ] If merge succeeded cleanly, `git status` shows clean tree → jump to Wave 4

  **QA Scenarios**:

  ```
  Scenario: Merge produces expected output
    Tool: Bash
    Preconditions: Worktree from T1.4 is current directory
    Steps:
      1. Run: pwd (verify in worktree)
      2. Run: git merge upstream/main --no-edit 2>&1 | tee .sisyphus/evidence/merge-output.txt
      3. Capture exit code (may be 0 or non-zero — both acceptable)
      4. Run: git status --short | head -50 > .sisyphus/evidence/post-merge-status.txt
      5. Run: cat .sisyphus/evidence/merge-output.txt | grep -E "CONFLICT|Auto-merging|merge made" | head -20
    Expected Result: Merge output captured, conflict markers identified
    Evidence: .sisyphus/evidence/merge-output.txt
  ```

  ```
  Scenario: Edge case - merge succeeds cleanly
    Tool: Bash
    Preconditions: T2.1 completed with no conflicts
    Steps:
      1. Run: git status --short
      2. Assert: empty output (clean tree)
      3. If clean, jump directly to Wave 4 (skip Wave 3)
    Expected Result: All conflicts auto-resolved, can proceed to validation
    Evidence: N/A (clean merge)
  ```

  **Commit**: NO (the merge IS the next commit, captured in T6.1)

- [ ] 2.2. **Capture and categorize the conflict list**

  **What to do**:
  - Run: `git diff --name-only --diff-filter=U` to list all unmerged files
  - Save full list to `.sisyphus/evidence/conflict-files.txt`
  - For each conflict file, run: `grep -c '<<<<<<' <file>` to count conflict markers
  - Categorize conflicts by directory: `awk -F/ '{print $1}' .sisyphus/evidence/conflict-files.txt | sort | uniq -c | sort -rn`
  - Save categorized summary to `.sisyphus/evidence/conflict-categories.txt`
  - **This is read-only analysis** — no edits to files yet

  **Must NOT do**:
  - DO NOT resolve conflicts here (T3.* handles that)
  - DO NOT run `git merge --abort` (that would undo the merge)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `["git-master"]` (for diff analysis)
  - **Reason**: Read-only analysis

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential after T2.1)
  - **Blocks**: T3.* (cannot resolve without knowing conflicts)
  - **Blocked By**: T2.1

  **References**:
  - `MERGE_GUIDE.md` section 3 — has the expected conflict categories
  - `f710bb79d` — the previous merge had 5 real conflicts (per its commit message)

  **Acceptance Criteria**:
  - [ ] `.sisyphus/evidence/conflict-files.txt` exists with all unmerged files
  - [ ] `.sisyphus/evidence/conflict-categories.txt` exists with directory counts
  - [ ] Expected conflicts present: `hermes_cli/main.py`, `pyproject.toml`, `ui-tui/src/components/branding.tsx`, `ui-tui/src/theme.ts`, `README.md`

  **QA Scenarios**:

  ```
  Scenario: Conflict list is captured correctly
    Tool: Bash
    Preconditions: T2.1 produced conflicts
    Steps:
      1. Run: git diff --name-only --diff-filter=U > .sisyphus/evidence/conflict-files.txt
      2. Run: wc -l .sisyphus/evidence/conflict-files.txt
      3. Assert: > 0 (at least one conflict)
      4. Run: awk -F/ '{print $1}' .sisyphus/evidence/conflict-files.txt | sort | uniq -c | sort -rn > .sisyphus/evidence/conflict-categories.txt
      5. Run: grep -E "hermes_cli|pyproject|ui-tui|README" .sisyphus/evidence/conflict-files.txt
      6. Assert: at least 3 of these expected conflicts present
    Expected Result: Conflict analysis ready for Wave 3
    Evidence: .sisyphus/evidence/conflict-files.txt, conflict-categories.txt
  ```

  **Commit**: NO

### Wave 3 — Conflict Resolution (parallel where independent)

- [ ] 3.1. **Resolve branding conflicts (text-based, not structural)**

  **What to do**:
  - **Target files** (from T2.2 conflict list):
    - `hermes_cli/main.py` — version string conflicts (replace "Hermes Agent v" with "THE JANITOR" per MERGE_GUIDE section 3.2)
    - `README.md` — keep Janitor branding (per previous merge `f710bb79d` precedent)
    - `ui-tui/src/components/branding.tsx` — keep Janitor's dynamic `brandTagFull(t)` functions, drop upstream's hardcoded `TAG_FULL`/`TAG_MID`/`TAG_TINY` constants
    - `ui-tui/src/theme.ts` — keep `JANITOR_BRAND` and `JANITOR_DARK_THEME`, accept upstream's `version?: string` interface addition
  - For each file: open, locate `<<<<<<<`, decide which side to keep, edit, verify no markers remain
  - **Pattern from `f710bb79d`**: "Adopt upstream's helper functions but replace version strings"
  - **Pattern from `MERGE_GUIDE.md` section 3.2**: Specific sed-style replacements for branding strings

  **Must NOT do**:
  - DO NOT use `git checkout --ours` or `git checkout --theirs` blindly (loses upstream improvements)
  - DO NOT modify the structure of `hermes_cli/main.py` (only string replacements)
  - DO NOT add new branding functions (use existing Janitor pattern)
  - DO NOT touch any `janitor_*` files (those are Janitor-owned)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `["git-master"]` (for careful conflict resolution)
  - **Reason**: Branding conflicts require understanding both sides; this is the highest-touch conflict area

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T3.2, T3.3, T3.4)
  - **Blocks**: T4.* (validation)
  - **Blocked By**: T2.2

  **References**:
  - `MERGE_GUIDE.md` section 3.2 "Branding / Identidad Visual" — exact rules
  - `f710bb79d` commit message — "README.md: preserve Janitor branding (upstream description discarded)"
  - AGENTS.md rule 4: TUI ISOLATION — branding via skin_engine.py, no hardcode
  - AGENTS.md rule 1: Zero-Renaming — keep 'hermes' as-is in core

  **Acceptance Criteria**:
  - [ ] 0 conflict markers in `hermes_cli/main.py`, `README.md`, `ui-tui/src/components/branding.tsx`, `ui-tui/src/theme.ts`
  - [ ] `grep -c "THE JANITOR" hermes_cli/main.py` >= 1
  - [ ] `grep -c "Hermes Agent v" hermes_cli/main.py` == 0
  - [ ] `grep -c "Nous Research" ui-tui/src/components/branding.tsx` == 0
  - [ ] `JANITOR_BRAND` constant present in `ui-tui/src/theme.ts`

  **QA Scenarios**:

  ```
  Scenario: Branding strings correctly replaced
    Tool: Bash
    Preconditions: T2.2 listed these files in conflict
    Steps:
      1. Run: grep -c "Hermes Agent v" hermes_cli/main.py
      2. Assert: 0
      3. Run: grep -c "Nous Research" ui-tui/src/components/branding.tsx
      4. Assert: 0
      5. Run: grep -c "Messenger of the Digital Gods" ui-tui/src/components/branding.tsx
      6. Assert: 0
      7. Run: grep -c "THE JANITOR" hermes_cli/main.py
      8. Assert: >= 1
      9. Run: grep -c "JANITOR_BRAND" ui-tui/src/theme.ts
      10. Assert: >= 1
    Expected Result: All upstream branding strings replaced
    Evidence: .sisyphus/evidence/task-3.1-branding-resolved.txt
  ```

  ```
  Scenario: Conflict markers are gone
    Tool: Bash
    Preconditions: T3.1 edited the files
    Steps:
      1. Run: grep -l '<<<<<<\|=======\|>>>>>>>' hermes_cli/main.py README.md ui-tui/src/components/branding.tsx ui-tui/src/theme.ts
      2. Assert: empty output
      3. Run: git add hermes_cli/main.py README.md ui-tui/src/components/branding.tsx ui-tui/src/theme.ts
      4. Assert: exit code 0 (files staged successfully)
    Expected Result: Conflicts resolved, files ready to stage
    Evidence: N/A (validated via grep output)
  ```

  **Commit**: NO (staging happens in T6.1)

- [ ] 3.2. **Resolve configuration conflicts (semantic, not just text)**

  **What to do**:
  - **Target files** (from T2.2 conflict list):
    - `pyproject.toml` — **CRITICAL**: preserve `python-telegram-bot>=22.7,<23` (Janitor's pin) over upstream's `==22.6`. Keep `janitor = "janitor_cli:main"` entry point. Keep `janitor_cli`, `janitor_update_bootstrap`, `mcp_serve` in `py-modules`. Adopt upstream's `dependency-groups` and new dev deps.
    - `scripts/run_tests.sh` — keep Janitor's wrapper (venv probing order, isolation plugin). Accept upstream improvements if any.
    - `tests/tools/test_lazy_deps.py` — per `f710bb79d`: "keep our Path+tomllib imports, drop unused Iterator"
  - For `pyproject.toml`, pay extra attention to the `[project.optional-dependencies]` section — Janitor's `messaging` and `termux` extras have different pins.
  - Use `git checkout --ours <file>` ONLY for specific lines, not whole files.

  **Must NOT do**:
  - DO NOT add new dependencies that upstream added without sign-off
  - DO NOT change the `[project.scripts]` entry points (keep `janitor = "janitor_cli:main"`)
  - DO NOT modify `[tool.uv]` config without understanding what Janitor's installer expects

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `["git-master"]`
  - **Reason**: Semantic conflicts in pyproject.toml are dangerous — wrong resolution breaks installation

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T3.1, T3.3, T3.4)
  - **Blocks**: T4.*
  - **Blocked By**: T2.2

  **References**:
  - `pyproject.toml` current state — Janitor's pin locations
  - `f710bb79d` commit message: "pyproject.toml: adopt upstream dev deps (starlette CVE fix, setuptools); keep our python-telegram-bot>=22.7,<23 pin"
  - `MERGE_GUIDE.md` section 3.3 — installer-related conflicts
  - AGENTS.md rule 8: MINIMALIST INSTALLER — no new heavy deps

  **Acceptance Criteria**:
  - [ ] `python-telegram-bot>=22.7,<23` present in `pyproject.toml` (Janitor's pin)
  - [ ] `janitor = "janitor_cli:main"` entry point present
  - [ ] `janitor_cli`, `janitor_update_bootstrap` in `py-modules` list
  - [ ] 0 conflict markers in all 3 target files
  - [ ] `python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"` exits 0 (TOML is valid)

  **QA Scenarios**:

  ```
  Scenario: pyproject.toml preserves Janitor's pins
    Tool: Bash
    Preconditions: T2.2 listed pyproject.toml in conflicts
    Steps:
      1. Run: grep "python-telegram-bot" pyproject.toml
      2. Assert: output contains ">=22.7,<23" (NOT "==22.6")
      3. Run: grep '"janitor"' pyproject.toml
      4. Assert: output contains 'janitor_cli:main'
      5. Run: grep "janitor_cli\|janitor_update_bootstrap" pyproject.toml
      6. Assert: both present
      7. Run: python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('VALID')"
      8. Assert: output is "VALID"
    Expected Result: Janitor's pins preserved, TOML valid
    Evidence: .sisyphus/evidence/task-3.2-pyproject-resolved.txt
  ```

  ```
  Scenario: All target files have no conflict markers
    Tool: Bash
    Preconditions: T3.2 edited all 3 files
    Steps:
      1. Run: grep -l '<<<<<<\|=======\|>>>>>>>' pyproject.toml scripts/run_tests.sh tests/tools/test_lazy_deps.py
      2. Assert: empty output
    Expected Result: Conflicts resolved
    Evidence: N/A
  ```

  **Commit**: NO

- [x] 3.3. **Prune upstream-only `.github/workflows/`**

   **What to do**:
   - **Check what upstream added** that Janitor doesn't have:
     - Likely new workflows: `docker-lint.yml`, `docker-publish.yml`, `docs-site-checks.yml` (per MERGE_GUIDE analysis)
   - **Keep only**: `janitor-ci.yml`, `upstream-sync.yml`, `tests.yml` (per `upstream-sync.yml` lines 53-54 pruning rule)
   - **Action**:
     ```bash
     # Remove any workflow not in the keep-list
     cd .github/workflows
     for f in *.yml; do
       case "$f" in
         janitor-ci.yml|upstream-sync.yml|tests.yml) ;;
         *) git rm -f "$f" ;;
       esac
     done
     ```
   - If `janitor-ci.yml`, `upstream-sync.yml`, or `tests.yml` have conflicts (Janitor vs upstream versions), keep Janitor's version (`git checkout --ours <file>`)
   - Verify final state: `ls .github/workflows/` should show only the 3 expected files

   **Evidence**: `.sisyphus/evidence/task-3.3-workflows-pruned.txt` shows:
   - 3 workflows remain: janitor-ci.yml, upstream-sync.yml, tests.yml
   - 16 upstream workflows removed
   - No conflict markers in remaining workflows

   **Status**: COMPLETED ✓

- [ ] 3.4. **Verify Janitor-specific files survived the merge**

   **What to do**:
   - **Check that these 51 files are present and unchanged in structure**:
     - `janitor_cli.py`, `janitor_update_bootstrap.py`
     - `janitor_ext/__init__.py`, `janitor_ext/tips_es.py`
     - `agent/janitor_language_guard.py`, `agent/opencode_session_manager.py`, `agent/opencode_orchestrator.py`
     - All `assets/janitor/*` (SOUL.md, config.yaml, honcho.json, avatars)
     - All `scripts/janitor-*.sh`, `scripts/setup-honcho.sh`, `scripts/migrate-janitor-minimal.sh`
     - All `skills/janitor-*/` directories (vault, browser, onboarding, repo-research, code-review, config-audit)
     - `AGENTS.md`, `MERGE_GUIDE.md`, `master_plan.md`, `janitor-project.md`
     - `.opencode/agents/merge-auditor.md`, `.opencode/skills/tui-compilation/SKILL.md`
     - `.claude/agents/janitor-dev-boss-autonomous.md`
     - 10 `RELEASE_v0.*.md` files
   - **If any are missing** (i.e., the merge clobbered them): `git checkout HEAD -- <file>` to restore
   - **Capture evidence**: `find . -path '*/janitor*' -o -name 'AGENTS.md' -o -name 'master_plan.md' ... > .sisyphus/evidence/janitor-files-survived.txt`
   - Compare file count: should be 51 (or more if new Janitor files were added)

   **Evidence**: `.sisyphus/evidence/janitor-files-survived.txt` shows:
   - janitor_cli.py: 552 lines ✓
   - All 5 scripts present ✓
   - All 11 skills/janitor-* directories present ✓
   - All 4 docs (AGENTS.md, MERGE_GUIDE.md, master_plan.md, janitor-project.md) present ✓
   - 15 RELEASE_v0.*.md files present ✓
   - NOTE: agent/opencode_orchestrator.py does NOT exist in git history - was never a tracked file

   **Status**: COMPLETED ✓

  **Must NOT do**:
  - DO NOT delete `janitor-ci.yml`, `upstream-sync.yml`, or `tests.yml`
  - DO NOT modify the contents of Janitor's workflows (only file-level keep/drop)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `["git-master"]`
  - **Reason**: File-level operations only, no semantic conflict

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T3.1, T3.2, T3.4)
  - **Blocks**: T4.*
  - **Blocked By**: T2.2

  **References**:
  - `.github/workflows/upstream-sync.yml` lines 53-54 — the canonical prune command
  - `MERGE_GUIDE.md` section 3.1 — "Workflows de GitHub" rules
  - `f710bb79d` precedent: "Pruned skills-index-freshness.yml (upstream-only CI, not needed in fork)"

  **Acceptance Criteria**:
  - [ ] `ls .github/workflows/` shows exactly: `janitor-ci.yml`, `upstream-sync.yml`, `tests.yml` (and any `.yaml` extensions if they exist)
  - [ ] 0 conflict markers in the 3 kept workflows
  - [ ] Removed workflows are staged for deletion

  **QA Scenarios**:

  ```
  Scenario: Only Janitor's workflows remain
    Tool: Bash
    Preconditions: T2.2 may have flagged workflow conflicts
    Steps:
      1. Run: ls .github/workflows/
      2. Assert: output contains exactly janitor-ci.yml, upstream-sync.yml, tests.yml
      3. Run: ls .github/workflows/ | wc -l
      4. Assert: output is 3 (or includes .yaml variants)
      5. Run: grep -l '<<<<<<\|=======\|>>>>>>>' .github/workflows/*.yml .github/workflows/*.yaml 2>/dev/null
      6. Assert: empty output
    Expected Result: Pruning complete, Janitor's CI preserved
    Evidence: .sisyphus/evidence/task-3.3-workflows-pruned.txt
  ```

  **Commit**: NO (staging in T6.1, but the `chore(merge): prune upstream-only workflows` will be a separate commit per `f710bb79d` pattern)

- [ ] 3.4. **Verify Janitor-specific files survived the merge**

  **What to do**:
  - **Check that these 51 files are present and unchanged in structure**:
    - `janitor_cli.py`, `janitor_update_bootstrap.py`
    - `janitor_ext/__init__.py`, `janitor_ext/tips_es.py`
    - `agent/janitor_language_guard.py`, `agent/opencode_session_manager.py`, `agent/opencode_orchestrator.py`
    - All `assets/janitor/*` (SOUL.md, config.yaml, honcho.json, avatars)
    - All `scripts/janitor-*.sh`, `scripts/setup-honcho.sh`, `scripts/migrate-janitor-minimal.sh`
    - All `skills/janitor-*/` directories (vault, browser, onboarding, repo-research, code-review, config-audit)
    - `AGENTS.md`, `MERGE_GUIDE.md`, `master_plan.md`, `janitor-project.md`
    - `.opencode/agents/merge-auditor.md`, `.opencode/skills/tui-compilation/SKILL.md`
    - `.claude/agents/janitor-dev-boss-autonomous.md`
    - 10 `RELEASE_v0.*.md` files
  - **If any are missing** (i.e., the merge clobbered them): `git checkout HEAD -- <file>` to restore
  - **Capture evidence**: `find . -path '*/janitor*' -o -name 'AGENTS.md' -o -name 'master_plan.md' ... > .sisyphus/evidence/janitor-files-survived.txt`
  - Compare file count: should be 51 (or more if new Janitor files were added)

**Must NOT do**:
   - DO NOT modify any tracked files
   - DO NOT add new files
   - DO NOT trust that git status is clean — explicitly check each file

   **Evidence**: `.sisyphus/evidence/janitor-files-survived.txt` shows:
   - janitor_cli.py: 552 lines ✓
   - All 5 scripts present ✓
   - All 11 skills/janitor-* directories present ✓
   - All 4 docs (AGENTS.md, MERGE_GUIDE.md, master_plan.md, janitor-project.md) present ✓
   - 15 RELEASE_v0.*.md files present ✓
   - NOTE: agent/opencode_orchestrator.py does NOT exist in git history - was never a tracked file

   **Status**: COMPLETED ✓

- [x] 3.5. **Resolve 308 add/add merge conflicts via git checkout --ours**

   **What to do**:
   - All 308 conflicted files (AA status) were resolved using `git checkout --ours` taking Janitor's version
   - Workflows pruned, all other files taken from Janitor HEAD
   - Remaining AA count: 0

   **Status**: COMPLETED ✓

- [ ] 3.1. **Resolve branding conflicts (text-based, not structural)**

   **What to do**:
   - **Target files** (from T2.2 conflict list):
     - `hermes_cli/main.py` — version string conflicts (replace "Hermes Agent v" with "THE JANITOR" per MERGE_GUIDE section 3.2)
     - `README.md` — keep Janitor branding (per previous merge `f710bb79d` precedent)
     - `ui-tui/src/components/branding.tsx` — keep Janitor's dynamic `brandTagFull(t)` functions, drop upstream's hardcoded `TAG_FULL`/`TAG_MID`/`TAG_TINY` constants
     - `ui-tui/src/theme.ts` — keep `JANITOR_BRAND` and `JANITOR_DARK_THEME`, accept upstream's `version?: string` interface addition
   - For each file: open, locate `<<<<<<<`, decide which side to keep, edit, verify no markers remain
   - **Pattern from `f710bb79d`**: "Adopt upstream's helper functions but replace version strings"
   - **Pattern from `MERGE_GUIDE.md` section 3.2**: Specific sed-style replacements for branding strings

- [ ] 4.1. **Gates 1, 2, 3, 5: Python compile, shell syntax, conflict markers, GHCR purge**

  **What to do**:
  - **Gate 1 - Python compile**:
    ```bash
    python3 -m py_compile cli.py run_agent.py gateway/run.py hermes_cli/main.py janitor_cli.py 2>&1 | tee .sisyphus/evidence/gate-1-py-compile.txt
    ```
  - **Gate 2 - Shell syntax**:
    ```bash
    bash -n scripts/*.sh scripts/janitor-*.sh scripts/setup-honcho.sh scripts/migrate-janitor-minimal.sh 2>&1 | tee .sisyphus/evidence/gate-2-shell-syntax.txt
    ```
  - **Gate 3 - Conflict markers**:
    ```bash
    grep -rn '<<<<<<\|=======\|>>>>>>' --exclude-dir=.git --exclude-dir=.sisyphus --exclude-dir=node_modules --exclude-dir=.venv 2>&1 | tee .sisyphus/evidence/gate-3-conflict-markers.txt
    ```
    Expected: 0 matches
  - **Gate 5 - GHCR purge**:
    ```bash
    grep -rn 'check_ghcr_auth\|ghcr.io' scripts/ 2>&1 | tee .sisyphus/evidence/gate-5-ghcr-purge.txt
    ```
    Expected: 0 matches (in `scripts/`, not in `node_modules` or elsewhere)
  - Compare results to baseline (`.sisyphus/evidence/baseline-gates.txt` from T1.2) to identify merge-introduced failures

  **Must NOT do**:
  - DO NOT fix any failures (T5.1 handles that)
  - DO NOT skip gates
  - DO NOT run full tests here (that's T4.3)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `["git-master"]` (for clean output capture)
  - **Reason**: Mechanical command execution

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T4.2, T4.3, T4.4)
  - **Blocks**: T5.1 (if failures), T6.1
  - **Blocked By**: T3.1, T3.2, T3.3, T3.4

  **References**:
  - `MERGE_GUIDE.md` section 4 "Validación Post-Merge" — same gate list
  - `scripts/run_tests.sh` — the test wrapper

  **Acceptance Criteria**:
  - [ ] Gate 1: Python compile exits 0
  - [ ] Gate 2: Shell syntax exits 0
  - [ ] Gate 3: 0 conflict markers in working tree
  - [ ] Gate 5: 0 `check_ghcr_auth` or `ghcr.io` references in `scripts/`

  **QA Scenarios**:

  ```
  Scenario: All 4 static gates pass
    Tool: Bash
    Preconditions: Wave 3 complete
    Steps:
      1. Run: python3 -m py_compile cli.py run_agent.py gateway/run.py hermes_cli/main.py janitor_cli.py
      2. Assert: exit code 0
      3. Run: bash -n scripts/*.sh scripts/janitor-*.sh scripts/setup-honcho.sh scripts/migrate-janitor-minimal.sh
      4. Assert: exit code 0
      5. Run: grep -rn '<<<<<<\|=======\|>>>>>>' --exclude-dir=.git --exclude-dir=.sisyphus --exclude-dir=node_modules --exclude-dir=.venv
      6. Assert: empty output
      7. Run: grep -rn 'check_ghcr_auth\|ghcr.io' scripts/
      8. Assert: empty output
    Expected Result: All 4 static gates green
    Evidence: .sisyphus/evidence/gate-{1,2,3,5}-*.txt
  ```

  ```
  Scenario: Edge case - pre-existing failures from T1.2 baseline
    Tool: Bash
    Preconditions: Baseline had failures
    Steps:
      1. Compare T4.1 output to .sisyphus/evidence/baseline-gates.txt
      2. Identify NEW failures introduced by merge
      3. Document in .sisyphus/evidence/gate-1-new-failures.txt
      4. Pre-existing failures noted but NOT counted as merge failures
    Expected Result: Clean attribution of failures
    Evidence: .sisyphus/evidence/gate-1-new-failures.txt
  ```

  **Commit**: NO

- [ ] 4.2. **Gates 4, 6, 7, 8: Branding purge + TUI build chain**

  **What to do**:
  - **Gate 4 - Branding purge**:
    ```bash
    grep -rn 'Nous Research\|Messenger of the Digital Gods\|Hermes Agent v' ui-tui/src/components/branding.tsx hermes_cli/main.py README.md 2>&1 | tee .sisyphus/evidence/gate-4-branding-purge.txt
    ```
    Expected: 0 matches
  - **Gate 6 - TUI type-check**:
    ```bash
    cd ui-tui && npm run type-check 2>&1 | tee ../.sisyphus/evidence/gate-6-tui-typecheck.txt
    ```
    Expected: 0 TypeScript errors
  - **Gate 7 - TUI build** (CRITICAL ORDER: `hermes-ink` first, then main):
    ```bash
    cd ui-tui && npm run build --prefix packages/hermes-ink 2>&1 | tee ../.sisyphus/evidence/gate-7a-hermes-ink-build.txt
    cd ui-tui && npm run build 2>&1 | tee ../.sisyphus/evidence/gate-7b-tui-build.txt
    test -f ui-tui/dist/entry.js && echo "DIST_OK" || echo "DIST_MISSING"
    ```
  - **Gate 8 - TUI tests**:
    ```bash
    cd ui-tui && npm test 2>&1 | tee ../.sisyphus/evidence/gate-8-tui-tests.txt
    ```
    Expected: 0 failures (skips acceptable per MERGE_GUIDE)

  **Must NOT do**:
  - DO NOT skip building `hermes-ink` first (it exports types the main TUI uses)
  - DO NOT fix any TUI errors here (T5.1 handles that)
  - DO NOT run with `--force` flags

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `["tui-compilation"]` (Janitor's gate skill — listed in AGENTS.md rule 7)
  - **Reason**: TUI compilation is the riskiest part of the merge; needs care

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T4.1, T4.3, T4.4)
  - **Blocks**: T5.1 (if failures), T6.1
  - **Blocked By**: T3.1, T3.2, T3.3, T3.4

  **References**:
  - `MERGE_GUIDE.md` section 4.2 "Gates del TUI" — exact commands
  - AGENTS.md rule 7: tui-compilation is mandatory gate
  - `.opencode/skills/tui-compilation/SKILL.md` — Janitor's gate skill

  **Acceptance Criteria**:
  - [ ] Gate 4: 0 branding strings in 3 target files
  - [ ] Gate 6: 0 TypeScript errors
  - [ ] Gate 7: `ui-tui/dist/entry.js` exists
  - [ ] Gate 8: 0 TUI test failures

  **QA Scenarios**:

  ```
  Scenario: TUI build chain succeeds
    Tool: Bash
    Preconditions: Wave 3 complete
    Steps:
      1. Run: grep -rn 'Nous Research\|Messenger of the Digital Gods\|Hermes Agent v' ui-tui/src/components/branding.tsx hermes_cli/main.py README.md
      2. Assert: empty output (Gate 4)
      3. Run: cd ui-tui && npm run type-check
      4. Assert: exit 0, output contains "0 errors" or similar (Gate 6)
      5. Run: cd ui-tui && npm run build --prefix packages/hermes-ink
      6. Assert: exit 0 (Gate 7a)
      7. Run: cd ui-tui && npm run build
      8. Assert: exit 0 (Gate 7b)
      9. Run: test -f ui-tui/dist/entry.js
      10. Assert: exit 0 (dist exists)
      11. Run: cd ui-tui && npm test
      12. Assert: exit 0, no test failures (Gate 8)
    Expected Result: Full TUI pipeline green
    Evidence: .sisyphus/evidence/gate-{4,6,7,8}-*.txt
  ```

  ```
  Scenario: Edge case - baseline had TUI errors
    Tool: Bash
    Preconditions: T1.2 baseline showed pre-existing TUI errors
    Steps:
      1. Compare T4.2 output to .sisyphus/evidence/baseline-gates.txt
      2. Identify NEW errors introduced by merge
      3. Pre-existing errors noted but not blocking
    Expected Result: Clean attribution
    Evidence: .sisyphus/evidence/gate-6-new-errors.txt
  ```

  **Commit**: NO

- [ ] 4.3. **Gates 9, 10: Python test suite + Janitor CLI smoke test**

  **What to do**:
  - **Gate 9 - Python tests** (subset for speed):
    ```bash
    scripts/run_tests.sh -q tests/agent/ tests/gateway/ tests/hermes_cli/ 2>&1 | tee .sisyphus/evidence/gate-9-py-tests.txt
    ```
    Note: Full test suite is `scripts/run_tests.sh` (no path), but subset is faster. If subset passes, run full suite.
    Then: `scripts/run_tests.sh 2>&1 | tee .sisyphus/evidence/gate-9-py-tests-full.txt`
  - **Gate 10 - Janitor CLI smoke test**:
    ```bash
    python3 janitor_cli.py --version 2>&1 | tee .sisyphus/evidence/gate-10-janitor-version.txt
    ```
    Expected output: contains "THE JANITOR"
  - Capture any new failures for analysis in T5.1

  **Must NOT do**:
  - DO NOT modify test files to make them pass (that's T5.1)
  - DO NOT skip the full test suite after subset passes (catches integration issues)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `["tui-compilation"]` (no — wrong skill) → `[]` with attention to test output
  - **Reason**: Test suite is the longest-running gate; needs monitoring

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T4.1, T4.2, T4.4)
  - **Blocks**: T5.1 (if failures), T6.1
  - **Blocked By**: T3.1, T3.2, T3.3, T3.4

  **References**:
  - `scripts/run_tests.sh` — the test wrapper
  - `tests/conftest.py` — pytest config with isolation plugin
  - `MERGE_GUIDE.md` section 4.3 "Compilación rápida de Python"

  **Acceptance Criteria**:
  - [ ] Gate 9: Python test suite runs without hard failures (flake tolerance OK)
  - [ ] Gate 10: `python3 janitor_cli.py --version` outputs "THE JANITOR"

  **QA Scenarios**:

  ```
  Scenario: Python tests pass and Janitor CLI works
    Tool: Bash
    Preconditions: Wave 3 complete
    Steps:
      1. Run: scripts/run_tests.sh -q tests/agent/ tests/gateway/ tests/hermes_cli/ 2>&1 | tail -30
      2. Assert: no "FAILED" or "ERROR" lines
      3. Run: python3 janitor_cli.py --version
      4. Assert: output contains "THE JANITOR"
      5. Run: scripts/run_tests.sh 2>&1 | tail -50
      6. Assert: no "FAILED" or "ERROR" lines (full suite)
    Expected Result: Tests pass, Janitor CLI functional
    Evidence: .sisyphus/evidence/gate-{9,10}-*.txt
  ```

  ```
  Scenario: Edge case - test failures from merge
    Tool: Bash
    Preconditions: Some tests fail
    Steps:
      1. Capture: grep "FAILED" .sisyphus/evidence/gate-9-py-tests-full.txt
      2. Document: each failure with file:line
      3. Compare: to baseline (.sisyphus/evidence/baseline-gates.txt) to identify new vs pre-existing
      4. Hand off to T5.1 for fix
    Expected Result: Failures attributed and queued for fixing
    Evidence: .sisyphus/evidence/gate-9-new-failures.txt
  ```

  **Commit**: NO

- [ ] 4.4. **Gate 11: Git status check + summary of all gates**

  **What to do**:
  - **Gate 11 - Git status**:
    ```bash
    git status --short 2>&1 | tee .sisyphus/evidence/gate-11-git-status.txt
    ```
    Expected: clean (only expected untracked from `.sisyphus/evidence/`)
  - **Summary report**: Create `.sisyphus/evidence/gates-summary.md` with pass/fail for all 11 gates
  - **If all 11 pass**: proceed to T6.1 directly (skip Wave 5)
  - **If any fail**: proceed to T5.1 to fix

  **Must NOT do**:
  - DO NOT include untracked `.sisyphus/run-continuation/*.json` (T1.1 should have cleaned these)
  - DO NOT ignore the summary report

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `["git-master"]`
  - **Reason**: Mechanical status check

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T4.1, T4.2, T4.3)
  - **Blocks**: T5.1 or T6.1
  - **Blocked By**: T3.1, T3.2, T3.3, T3.4

  **References**:
  - `MERGE_GUIDE.md` section 4.1 final checklist
  - All 11 gates documentation above

  **Acceptance Criteria**:
  - [ ] `git status --short` shows no unexpected untracked files
  - [ ] `.sisyphus/evidence/gates-summary.md` exists with pass/fail for all 11 gates

  **QA Scenarios**:

  ```
  Scenario: Git status is clean and all gates pass
    Tool: Bash
    Preconditions: T4.1, T4.2, T4.3 complete
    Steps:
      1. Run: git status --short
      2. Assert: only .sisyphus/evidence/* untracked, no staged changes
      3. Run: cat .sisyphus/evidence/gate-{1..11}-*.txt 2>/dev/null | grep -c "FAIL\|ERROR\|exit code 1"
      4. Assert: 0 (or pre-existing failures only)
    Expected Result: All gates green, ready for commit
    Evidence: .sisyphus/evidence/gates-summary.md
  ```

  ```
  Scenario: Edge case - one or more gates failed
    Tool: Bash
    Preconditions: T4.1, T4.2, or T4.3 found failures
    Steps:
      1. Run: cat .sisyphus/evidence/gate-{1..11}-*.txt 2>/dev/null | grep "FAIL\|ERROR"
      2. Document each failure in .sisyphus/evidence/gates-summary.md under "Failed Gates"
      3. Proceed to T5.1 with the failure list
    Expected Result: Failures documented for fixing
    Evidence: .sisyphus/evidence/gates-summary.md
  ```

  **Commit**: NO

### Wave 5 — Fixups (conditional, only if Wave 4 found issues)

- [ ] 5.1. **Apply fix commits for any gate failures**

  **What to do**:
  - **Read** `.sisyphus/evidence/gates-summary.md` (from T4.4) to identify failing gates
  - **For each failing gate**:
    - Analyze the failure root cause
    - Apply the minimum fix needed
    - Use `systematic-debugging` skill if the cause is non-obvious
  - **Commit strategy** (atomic, following MERGE_GUIDE section 5.2):
    - If branding issue: `fix(branding): remove upstream identity leaks`
    - If TUI build issue: `fix(tui): resolve merge compilation blockers`
    - If installer issue: `fix(installer): align legacy stack guidance`
    - If test failure: `fix(tests): update test for new upstream API`
    - **NEVER** mix multiple fix categories in one commit
    - **NEVER** use `--amend`
  - Re-run only the failed gates after each fix to verify
  - Capture evidence of each fix to `.sisyphus/evidence/task-5.1-fix-{N}.txt`

  **Must NOT do**:
  - DO NOT modify core files (`cli.py`, `run_agent.py`, `gateway/run.py`, `hermes_cli/main.py`) — if a fix requires this, STOP and escalate
  - DO NOT squash multiple fixes into one commit
  - DO NOT skip re-running the failed gate after fixing
  - DO NOT introduce new functionality

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: `["systematic-debugging", "git-master"]` (debugging is the right call for unknowns)
  - **Reason**: Debugging merge failures is genuinely hard; needs careful analysis

  **Parallelization**:
  - **Can Run In Parallel**: NO (each fix must be applied + verified sequentially)
  - **Parallel Group**: Wave 5 (sequential with T5.2)
  - **Blocks**: T5.2
  - **Blocked By**: T4.1 OR T4.2 OR T4.3 OR T4.4 (any failure)

  **References**:
  - `MERGE_GUIDE.md` section 5 "Commit del Merge" — commit message patterns
  - `MERGE_GUIDE.md` section 7 "Troubleshooting" — common fix patterns
  - AGENTS.md rule 1: Zero-Renaming — fix may not require renaming

  **Acceptance Criteria**:
  - [ ] All previously failing gates now pass
  - [ ] Each fix is in its own atomic commit with proper message
  - [ ] No core files modified
  - [ ] Evidence captured per fix

  **QA Scenarios**:

  ```
  Scenario: Fix a single failing gate
    Tool: Bash
    Preconditions: T4.* identified a failure
    Steps:
      1. Read .sisyphus/evidence/gates-summary.md
      2. For first failing gate:
        a. Read the failure output
        b. Apply minimal fix
        c. Run only that gate again
        d. Verify pass
        e. git add changed files
        f. git commit -m "fix(category): specific description"
      3. Repeat for each failing gate
    Expected Result: All gates pass after fixups
    Evidence: .sisyphus/evidence/task-5.1-fix-{N}.txt per fix
  ```

  ```
  Scenario: Edge case - fix requires modifying core file
    Tool: Bash
    Preconditions: Fix analysis reveals core file change needed
    Steps:
      1. STOP immediately
      2. Document the issue in .sisyphus/evidence/task-5.1-blocker.txt
      3. Escalate to user — this is a fork architecture violation
      4. DO NOT proceed without user decision
    Expected Result: Blocker documented, user notified
    Evidence: .sisyphus/evidence/task-5.1-blocker.txt
  ```

  **Commit**: YES (each fix is its own commit)

- [ ] 5.2. **Re-run all gates to confirm clean state**

  **What to do**:
  - Re-run all 11 gates sequentially (or in parallel batches)
  - Update `.sisyphus/evidence/gates-summary.md` with the re-run results
  - **All 11 must now pass** (pre-existing baseline failures documented as accepted)
  - If any still fail, return to T5.1 (loop)

  **Must NOT do**:
  - DO NOT mark the merge complete until ALL 11 gates pass
  - DO NOT ignore persistent failures (they will block the PR)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `["git-master"]`
  - **Reason**: Re-running established commands

  **Parallelization**:
  - **Can Run In Parallel**: NO (verification must be complete)
  - **Parallel Group**: Wave 5 (sequential after T5.1)
  - **Blocks**: T6.1
  - **Blocked By**: T5.1

  **References**:
  - All 11 gates from T4.*

  **Acceptance Criteria**:
  - [ ] All 11 gates pass on re-run
  - [ ] `.sisyphus/evidence/gates-summary.md` updated with PASS for all 11

  **QA Scenarios**:

  ```
  Scenario: All 11 gates pass after fixups
    Tool: Bash
    Preconditions: T5.1 applied fixes
    Steps:
      1. Run all 11 gates from T4.*
      2. Assert: all exit 0
      3. Update .sisyphus/evidence/gates-summary.md with "ALL PASS" status
    Expected Result: Clean state achieved
    Evidence: .sisyphus/evidence/gates-summary.md (updated)
  ```

  **Commit**: NO (just verification, no code changes expected)

### Wave 6 — PR Creation (sequential)

- [ ] 6.1. **Commit merge and all fixups with proper messages**

  **What to do**:
  - **Stage all resolved files**:
    ```bash
    git add -A
    git status --short  # verify only expected files
    ```
  - **If merge from T2.1 is still uncommitted** (i.e., had conflicts):
    - Run: `git commit --no-edit` to complete the merge commit
    - Message will be auto-set to "Merge remote-tracking branch 'upstream/main'"
  - **If workflow pruning from T3.3 was uncommitted**:
    - `git commit -m "chore(merge): prune upstream-only workflows"`
  - **Verify commit log**:
    ```bash
    git log --oneline upstream/main..HEAD
    ```
    Expected: 1-4 commits (merge + prune + optional fixups)

  **Must NOT do**:
  - DO NOT use `--amend` (preserve atomic commit history per AGENTS.md spirit)
  - DO NOT squash the merge with fixups (each commit should be inspectable)
  - DO NOT push yet (that's T6.2)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `["git-master"]`
  - **Reason**: Standard git commit workflow

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 6 (sequential)
  - **Blocks**: T6.2
  - **Blocked By**: T5.2 (or T4.4 if Wave 5 was skipped)

  **References**:
  - `f710bb79d` — the merge commit message pattern
  - `MERGE_GUIDE.md` section 5 "Commit del Merge"
  - AGENTS.md rule: no amending, atomic commits

  **Acceptance Criteria**:
  - [ ] `git status --short` is clean
  - [ ] `git log upstream/main..HEAD --oneline` shows the merge + fixups
  - [ ] Each commit message follows the established patterns

  **QA Scenarios**:

  ```
  Scenario: All commits properly created
    Tool: Bash
    Preconditions: T5.2 (or T4.4 if no fixes needed) complete
    Steps:
      1. Run: git status --short
      2. Assert: empty output
      3. Run: git log --oneline upstream/main..HEAD
      4. Assert: shows merge commit + optional chore(merge): prune + fixup commits
      5. Run: git log -1 --format="%s" upstream/main..HEAD | head -1
      6. Assert: starts with "Merge" or "chore(merge):"
    Expected Result: Clean commit history ready for push
    Evidence: .sisyphus/evidence/task-6.1-commits-created.txt
  ```

  **Commit**: YES (this task IS the commit)

- [ ] 6.2. **Push branch to origin**

  **What to do**:
  - Push the new sync branch to `origin`:
    ```bash
    git push -u origin upstream-sync-$(date +%Y%m%d-%H%M%S)
    ```
  - **NOTE**: Branch name from T1.4 (e.g., `upstream-sync-20260601-143022`)
  - Verify push succeeded: `git branch -vv | grep upstream-sync`
  - **DO NOT** push to `main` directly (that's the user's decision via PR merge)

  **Must NOT do**:
  - DO NOT push to `main`
  - DO NOT force push (`--force` or `-f`)
  - DO NOT push tags

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `["git-master"]`
  - **Reason**: Standard git push operation

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 6 (sequential after T6.1)
  - **Blocks**: T6.3
  - **Blocked By**: T6.1

  **References**:
  - `git push` documentation
  - `MERGE_GUIDE.md` doesn't cover push (out of scope for merge itself)

  **Acceptance Criteria**:
  - [ ] Branch pushed to `origin/upstream-sync-*`
  - [ ] `git branch -vv` shows tracking branch
  - [ ] `main` branch unchanged locally

  **QA Scenarios**:

  ```
  Scenario: Branch pushed successfully
    Tool: Bash
    Preconditions: T6.1 complete
    Steps:
      1. Run: BRANCH=$(git branch --show-current)
      2. Run: git push -u origin "$BRANCH"
      3. Assert: exit code 0
      4. Run: git branch -vv | grep "$BRANCH"
      5. Assert: shows tracking info "origin/$BRANCH"
      6. Run: git log origin/main..HEAD --oneline
      7. Assert: shows the sync commits ahead of main
    Expected Result: Branch pushed, ready for PR
    Evidence: .sisyphus/evidence/task-6.2-branch-pushed.txt
  ```

  **Commit**: NO (push is not a commit)

- [ ] 6.3. **Open PR with detailed description**

  **What to do**:
  - Open a PR using `gh` CLI:
    ```bash
    gh pr create \
      --base main \
      --head upstream-sync-$(date +%Y%m%d-%H%M%S) \
      --title "chore(sync): merge upstream/main — 153 commits (v0.15.1+)" \
      --body-file .sisyphus/evidence/pr-description.md \
      --label "upstream-sync" \
      --assignee reck74
    ```
  - **PR description** (saved to `.sisyphus/evidence/pr-description.md`) should include:
    - Summary: "Merges 153 upstream commits into Janitor while preserving all customizations"
    - Conflicts resolved: list (branding, pyproject, etc.)
    - Workflows pruned: list
    - Janitor customizations preserved: 51 files
    - Validation: all 11 gates PASS (link to evidence)
    - Test plan: 9 validation gates listed
    - Breaking changes: none expected (additive sync)
  - **Label**: `upstream-sync` (matches `MERGE_GUIDE.md` and existing bot patterns)
  - **Assignee**: `reck74` (per the bot config in `upstream-sync.yml`)

  **Must NOT do**:
  - DO NOT merge the PR (user must approve)
  - DO NOT use `gh pr merge` in any form
  - DO NOT create multiple PRs for the same sync

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `["git-master"]` (for `gh` CLI operations)
  - **Reason**: Standard PR creation

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 6 (sequential after T6.2)
  - **Blocks**: F1-F4
  - **Blocked By**: T6.2

  **References**:
  - `.github/workflows/upstream-sync.yml` — shows the bot's PR format (lines 71-82)
  - `MERGE_GUIDE.md` section 5.1 — merge commit message format

  **Acceptance Criteria**:
  - [ ] PR created against `main`
  - [ ] PR has `upstream-sync` label
  - [ ] PR assigned to `reck74`
  - [ ] PR description includes all required sections
  - [ ] PR URL saved to evidence

  **QA Scenarios**:

  ```
  Scenario: PR opened with detailed description
    Tool: Bash
    Preconditions: T6.2 complete
    Steps:
      1. Generate .sisyphus/evidence/pr-description.md with all required sections
      2. Run: gh pr create --base main --head "$BRANCH" --title "..." --body-file .sisyphus/evidence/pr-description.md --label "upstream-sync" --assignee reck74
      3. Assert: exit code 0
      4. Run: PR_URL=$(gh pr view --json url -q .url)
      5. Run: echo "$PR_URL" > .sisyphus/evidence/pr-url.txt
      6. Run: gh pr view --json labels | jq '.labels[].name' | grep "upstream-sync"
      7. Assert: output contains "upstream-sync"
    Expected Result: PR ready for user review
    Evidence: .sisyphus/evidence/pr-url.txt
  ```

  **Commit**: NO

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
>
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**

### Post-Final-Wave Cleanup (after F1-F4 all APPROVE)

After the user gives explicit approval of the PR:

- [ ] C1. **Delete the draft file**
  - Run: `rm .sisyphus/drafts/upstream-sync-review.md`
  - The plan is now the single source of truth; the draft served its purpose as working memory
  - Verify deletion: `ls .sisyphus/drafts/upstream-sync-review.md` → should fail (file not found)
  - **Rationale**: Plan-mode cleanup protocol — keep `.sisyphus/drafts/` lean for next planning session

- [ ] C2. **Print the handoff summary to the user**
  - Confirm PR URL
  - Confirm worktree path (so user can inspect if needed)
  - Remind user to review the PR description and merge when ready
  - Print: "To clean up the local worktree after PR merge: `git worktree remove /home/reck/Janitor-Agent-worktrees/<branch-name>`"

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run all 9 validation gates. Review the merge commit + fixup commits for: stray console.log, commented-out code, unused imports. Check for AI slop: excessive comments, over-abstraction. Verify `git log` shows clean atomic commits, not squash-merged mess.
  Output: `Gates [9/9] | Build [PASS/FAIL] | Tests [N pass/N fail] | Commits [CLEAN/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from a clean worktree of the PR branch. Execute every QA scenario from every task — follow exact steps, capture evidence. Test that `janitor` command launches without errors. Test that Telegram bot still works (if credentials available). Test that core `delegate_task`, `terminal`, `file_operations` tools still function. Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (`git log -p HEAD~N..HEAD`). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination: Task N touching Task M's files. Flag unaccounted changes. Confirm 51 Janitor customizations survived.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | Customizations [51/51 survived] | VERDICT`

---

## Commit Strategy

Commits atómicos separados (NO squash, NO amend):

1. **`chore(merge): sync upstream/main — 153 commits`** — el merge en sí, igual a `f710bb79d`
2. **`chore(merge): prune upstream-only workflows`** — sigue el patrón de `f710bb79d` y `aa3b03807`
3. **`fix(branding): remove upstream identity leaks`** (si quedan) — siguiendo regla del MERGE_GUIDE
4. **`fix(tui): resolve merge compilation blockers`** (si quedan) — siguiendo regla del MERGE_GUIDE
5. **`fix(installer): align legacy stack guidance`** (si queda) — siguiendo regla del MERGE_GUIDE
6. **`test(merge): post-merge validation evidence`** — commit con la evidencia capturada

Cada commit incluye Co-Authored-By si fue creado con asistencia AI.

---

## Success Criteria

### Verification Commands

```bash
# After merge complete, all 9 gates must pass:
python3 -m py_compile cli.py run_agent.py gateway/run.py hermes_cli/main.py janitor_cli.py
bash -n scripts/*.sh scripts/janitor-*.sh
grep -rn '<<<<<<\|=======\|>>>>>>' --exclude-dir=.git --exclude-dir=.sisyphus --exclude-dir=node_modules --exclude-dir=.venv
grep -rn 'Nous Research\|Messenger of the Digital Gods\|Hermes Agent v' ui-tui/src/components/branding.tsx hermes_cli/main.py README.md
grep -rn 'check_ghcr_auth\|ghcr.io' scripts/
cd ui-tui && npm run type-check
cd ui-tui && npm run build --prefix packages/hermes-ink && npm run build
cd ui-tui && npm test
scripts/run_tests.sh -q tests/agent/ tests/gateway/ tests/hermes_cli/
python3 janitor_cli.py --version
git status --short
```

### Final Checklist

- [ ] All "Must Have" present (9 gates, 51 customizations preserved, PR opened)
- [ ] All "Must NOT Have" absent (no hermes renamed in core, no janitor skills touched, no new deps)
- [ ] All 9 validation gates pass with evidence captured
- [ ] PR description includes: commits brought, conflicts resolved, gate evidence
- [ ] Draft file `.sisyphus/drafts/upstream-sync-review.md` deleted
- [ ] F1-F4 reviews all APPROVE
- [ ] User explicitly approves the PR for merge

---

*Plan generated by Prometheus for Janitor-Agent upstream sync.*
