# Upstream Sync CI/CD Error Handling Refactor

## TL;DR

> **Quick Summary**: Replace the `git merge upstream/main --no-edit || true` block in `.github/workflows/upstream-sync.yml` with explicit conflict detection, graceful abort, GitHub Issue creation, and visible `exit 1` failure.
> 
> **Deliverables**:
> - Refactored merge + prune step in `upstream-sync.yml` (lines 46-50)
> 
> **Estimated Effort**: Quick (single file, ~15 lines changed)
> **Parallel Execution**: NO — single task
> **Critical Path**: Task 1 → Final Verification

---

## Context

### Original Request
El CTO ha ordenado una refactorización crítica del pipeline de CI/CD. El script de sincronización actual (`.github/workflows/upstream-sync.yml`) enmascara los conflictos de merge porque usa `|| true` al final del proceso. El pipeline dio "verde" pero falló fatalmente en segundo plano.

### Interview Summary
**Key Decisions**:
- Commit strategy: **Separate commit** (NOT `--amend`) — preserve "chore: prune upstream workflows" pattern
- Exit code on conflict: **`exit 1`** — workflow must fail visibly (❌ in GitHub Actions)
- Assignee: **`reck74`** — correct hardcoded GitHub username
- Issue actionability: Include conflict file list in issue body before `git merge --abort`

**Research Findings**:
- File is 82 lines total, changes affect lines 46-50 only
- Downstream triple verification (lines 52-67) must remain untouched and functional
- The `|| true` on line 30 (`git remote add upstream`) is LEGITIMATE and must NOT be changed
- The `|| true` on the `find ... -exec git rm` line is LEGITIMATE (no files to prune is OK)
- The `git merge --abort` can itself fail — must handle with `2>/dev/null || true`

### Metis Review
**Identified Gaps** (all addressed):
- Branch cleanup on conflict: local `upstream-sync-*` branch left behind → add `git checkout main && git branch -D $BRANCH_NAME` before exit
- `git merge --abort` failure handling → use `git merge --abort 2>/dev/null || true`
- Conflict issue should capture file list before aborting → capture `git diff --name-only --diff-filter=U` before abort
- `|| true` on line 30 is legitimate → explicitly guard against changes
- Issue label: reuse `upstream-sync` from existing fallback issue (line 82)

---

## Work Objectives

### Core Objective
Replace the silent-failure merge block with Enterprise-grade error handling that detects conflicts, aborts cleanly, creates a properly-labeled and actionable GitHub issue, and fails the pipeline visibly with `exit 1`.

### Concrete Deliverables
- Modified `.github/workflows/upstream-sync.yml` with lines 46-50 replaced by explicit conflict-handling block

### Definition of Done
- [ ] `git merge upstream/main --no-edit || true` is GONE from the file
- [ ] New block uses `if ! git merge upstream/main --no-edit; then` for explicit conflict detection
- [ ] On conflict: creates a GitHub issue with conflict file list, reuses `upstream-sync` label
- [ ] On conflict: runs `git merge --abort 2>/dev/null || true` (safe abort)
- [ ] On conflict: cleans up local sync branch
- [ ] On conflict: exits with code 1 (visible red failure in GitHub Actions)
- [ ] On success: prune unchanged (`find ... -exec git rm ... || true` + separate commit)
- [ ] All other lines (1-44, 52-82) are UNCHANGED

### Must Have
- Explicit conflict detection (no `|| true` on merge)
- `exit 1` on conflict (visible pipeline failure)
- GitHub Issue creation with actionable conflict file list
- `upstream-sync` label on conflict issue
- Safe `git merge --abort` (even if abort itself fails)
- Separate commit for prune (NOT `--amend`)

### Must NOT Have (Guardrails)
- **MUST NOT** change lines 1-44 (checkout, remote setup, branch creation, commit-count check)
- **MUST NOT** change lines 52-67 (triple verification shield)
- **MUST NOT** change lines 69-82 (push + PR creation + fallback issue)
- **MUST NOT** remove `|| true` from line 30 (`git remote add upstream`) — legitimate idempotency
- **MUST NOT** use `--amend` — separate commit for prune step
- **MUST NOT** use `exit 0` on conflict — must use `exit 1`
- **MUST NOT** add any Python, Node.js, or new shell scripts — inline bash only
- **MUST NOT** change any other `.yml` file in `.github/workflows/`

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (this is a GitHub Actions workflow, not unit-testable locally)
- **Automated tests**: None (YAML bash validation only)
- **Framework**: Bash validation via `bash -n` (syntax check)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **CI/CD YAML**: Use Bash (yaml lint + bash syntax) — Validate structure, syntax, and logical correctness
- **Logic verification**: Manual trace of execution paths (happy path + conflict path)

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately):
└── Task 1: Replace merge block with Enterprise error handling [quick]

Wave FINAL (After Task 1):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: YAML structure + bash syntax validation (quick)
└── Task F3: Scope fidelity check (deep)

Critical Path: Task 1 → F1-F3 → user okay
```

### Dependency Matrix

- **1**: - → F1, F2, F3
- **F1**: 1 → -
- **F2**: 1 → -
- **F3**: 1 → -

### Agent Dispatch Summary

- **Wave 1**: 1 task — T1 → `quick`
- **FINAL**: 3 tasks — F1 → `oracle`, F2 → `quick`, F3 → `deep`

---

## TODOs

- [x] 1. Replace merge block with Enterprise error handling

  **What to do**:
  - In `.github/workflows/upstream-sync.yml`, replace lines 46-50 (the merge + prune block) with the following logic:
    1. **Merge with explicit conflict detection**: Replace `git merge upstream/main --no-edit || true` with an `if ! git merge upstream/main --no-edit; then` block
    2. **Conflict path** (inside the `then` block):
       - `echo "🚨 CONFLICTO DETECTADO. Abortando merge automático."`
       - Capture conflict file list: `CONFLICT_FILES=$(git diff --name-only --diff-filter=U 2>/dev/null || echo "Unable to list files")`
       - Create GitHub Issue with conflict info, label `upstream-sync`, assignee `reck74`, including the conflict file list and branch name in the body
       - `git merge --abort 2>/dev/null || true` (safe abort, don't mask original error if abort fails)
       - `git checkout main && git branch -D $BRANCH_NAME` (clean up local sync branch)
       - `exit 1` (visible red failure in GitHub Actions)
    3. **Success path** (after the `fi`):
       - Keep `find .github/workflows -type f ! -name 'tests.yml' ! -name 'upstream-sync.yml' -exec git rm -f {} + || true` unchanged
       - Keep `git commit -m "chore: prune upstream workflows" || true` (SEPARATE commit, NOT `--amend`)
  - The new block should look approximately like:
    ```bash
          # 3. Merge con detección explícita de conflictos
          if ! git merge upstream/main --no-edit; then
              echo "🚨 CONFLICTO DETECTADO. Abortando merge automático."
              CONFLICT_FILES=$(git diff --name-only --diff-filter=U 2>/dev/null || echo "No se pudieron listar los archivos")
              git merge --abort 2>/dev/null || true
              git checkout main
              git branch -D $BRANCH_NAME 2>/dev/null || true
              gh issue create \
                --repo "${{ github.repository }}" \
                --title "🚨 Sincronización Fallida: Conflictos Upstream" \
                --body "El bot intentó sincronizar con upstream pero encontró conflictos de merge.

    **Rama**: \`$BRANCH_NAME\`
    **Archivos en conflicto**:
    \`\`\`
    $CONFLICT_FILES
    \`\`\`

    Por favor, realiza un \`git fetch upstream && git merge upstream/main\` localmente para resolverlos." \
                --assignee reck74 \
                --label "upstream-sync"
              exit 1
          fi

          # 4. Poda de CI (Commit SEPARADO para no corromper el merge)
          find .github/workflows -type f ! -name 'tests.yml' ! -name 'upstream-sync.yml' -exec git rm -f {} + || true
          git commit -m "chore: prune upstream workflows" || true
    ```
  - **CRITICAL**: The indentation must match the existing file (12 spaces for run block content, then 10 spaces for nested bash inside the `run: |` block)

  **Must NOT do**:
  - Do NOT change lines 1-44 (checkout, remote, branch creation, commit count check)
  - Do NOT change lines 52-67 (triple verification shield) — the renumbered lines after this change
  - Do NOT change lines 69-82 (push + PR creation + fallback issue) — the renumbered lines
  - Do NOT remove `|| true` from line 30 (`git remote add upstream`)
  - Do NOT use `git commit --amend` — separate commit only
  - Do NOT use `exit 0` on conflict path — must be `exit 1`
  - Do NOT add any new files, scripts, or dependencies

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single file, targeted change, ~15 lines, clear spec
  - **Skills**: []
    - No specialized skills needed for a YAML bash block replacement
  - **Skills Evaluated but Omitted**:
    - `tui-compilation`: Not relevant — this is CI/CD YAML, not TUI code
    - `reveal-deck`: Not a presentation

  **Parallelization**:
  - **Can Run In Parallel**: NO (only one task)
  - **Parallel Group**: Wave 1 (solo task)
  - **Blocks**: F1, F2, F3
  - **Blocked By**: None

  **References** (CRITICAL — Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `.github/workflows/upstream-sync.yml:46-50` — THE EXACT BLOCK BEING REPLACED. Current code uses `git merge ... || true` which masks errors.
  - `.github/workflows/upstream-sync.yml:78-82` — Existing fallback `gh issue create` pattern. Copy the `--repo`, `--title`, `--label` structure from here. The new conflict issue must use the SAME `upstream-sync` label.
  - `.github/workflows/upstream-sync.yml:42` — `$BRANCH_NAME` variable is defined here. Used in cleanup and should be referenced in issue body.

  **API/Type References** (contracts to implement against):
  - `.github/workflows/upstream-sync.yml:24-25` — `GH_TOKEN: ${{ secrets.PAT_WORKFLOW }}` env provides auth for `gh issue create`. No additional auth needed.
  - `.github/workflows/upstream-sync.yml:8-11` — `permissions: issues: write` already granted at job level.

  **External References**:
  - `git merge --abort` — Git command to cancel an in-progress merge. Safe even if merge not in progress when combined with error suppression.
  - `git diff --name-only --diff-filter=U` — Lists unmerged files during a merge conflict. Falls back to generic message if git state is unexpected.
  - `gh issue create` — GitHub CLI to create issues. Requires `GH_TOKEN` (already in env).

  **WHY Each Reference Matters**:
  - Lines 46-50: This is the EXACT code to replace. Every byte matters.
  - Lines 78-82: The fallback issue pattern must be replicated for consistency — same label, same repo flag format.
  - Line 42: `$BRANCH_NAME` must be captured in the issue body before the branch is deleted for traceability.
  - Lines 24-25: Confirms `GH_TOKEN` is already available — no additional secret/setup needed for `gh issue create`.
  - Lines 8-11: Confirms `issues: write` permission is already granted — no permission changes needed.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Happy path — merge succeeds without conflict
    Tool: Bash
    Preconditions: upstream-sync.yml modified, bash syntax valid
    Steps:
      1. `grep -n "git merge.*|| true" .github/workflows/upstream-sync.yml` → returns nothing (no || true on merge)
      2. `grep -n "if ! git merge upstream/main --no-edit" .github/workflows/upstream-sync.yml` → returns the line
      3. `grep -n "exit 1" .github/workflows/upstream-sync.yml` → returns the line inside the conflict block
      4. `grep -n "git merge --abort" .github/workflows/upstream-sync.yml` → returns the line
      5. `grep -n 'chore: prune upstream workflows' .github/workflows/upstream-sync.yml` → returns the line (separate commit, NOT --amend)
    Expected Result: All greps return matching lines
    Failure Indicators: Any grep missing, `--amend` present, `exit 0` instead of `exit 1`
    Evidence: .sisyphus/evidence/task-1-happy-path.txt

  Scenario: Conflict path — all error handling elements present
    Tool: Bash
    Preconditions: upstream-sync.yml modified
    Steps:
      1. `grep -n "CONFLICTO DETECTADO" .github/workflows/upstream-sync.yml` → conflict message present
      2. `grep -n "git diff --name-only --diff-filter=U" .github/workflows/upstream-sync.yml` → conflict file capture present
      3. `grep -n "gh issue create" .github/workflows/upstream-sync.yml` → issue creation present
      4. `grep -n "assignee reck74" .github/workflows/upstream-sync.yml` → correct assignee
      5. `grep -n 'label "upstream-sync"' .github/workflows/upstream-sync.yml` → same label as fallback issue
      6. `grep -n "git checkout main" .github/workflows/upstream-sync.yml` → branch cleanup present
      7. `grep -n "git branch -D" .github/workflows/upstream-sync.yml` → branch deletion present
    Expected Result: All greps return matching lines with correct content
    Failure Indicators: Missing any of the 7 grep patterns
    Evidence: .sisyphus/evidence/task-1-conflict-path.txt

  Scenario: Guardrails — protected lines unchanged
    Tool: Bash
    Preconditions: upstream-sync.yml modified
    Steps:
      1. `sed -n '1,44p' .github/workflows/upstream-sync.yml` → compare against original (checkout, remote, branch, commit-count check)
      2. Verify `git remote add upstream https://github.com/NousResearch/hermes-agent.git || true` still exists (line ~30)
      3. Count total lines in file should be approximately 82 +- a few (small change)
    Expected Result: Lines 1-44 are byte-identical to original, `|| true` on remote add intact
    Failure Indicators: Any change to lines 1-44, removal of `|| true` from remote add
    Evidence: .sisyphus/evidence/task-1-guardrails.txt
  ```

  **Evidence to Capture**:
  - [ ] task-1-happy-path.txt — grep results confirming merge pattern, exit 1, --abort
  - [ ] task-1-conflict-path.txt — grep results confirming issue creation, assignee, label, branch cleanup
  - [ ] task-1-guardrails.txt — line comparison confirming untouched regions

  **Commit**: YES
  - Message: `fix(ci): replace silent merge failure with explicit conflict detection`
  - Files: `.github/workflows/upstream-sync.yml`
  - Pre-commit: (none — YAML file, no build step needed)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 3 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, grep for pattern). For each "Must NOT Have": search for forbidden patterns — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **YAML Structure + Bash Syntax Validation** — `quick`
  Run `bash -n` on the extracted bash block to validate syntax. Run `yamllint` or manual YAML structure check. Verify indentation is consistent. Verify the `run: |` block is properly formatted. Trace both execution paths (happy + conflict) line-by-line to ensure logical correctness.
  Output: `Bash Syntax [PASS/FAIL] | YAML Structure [PASS/FAIL] | Logic Trace [PASS/FAIL] | VERDICT`

- [x] F3. **Scope Fidelity Check** — `deep`
  For the single task: read "What to do", read actual diff (`git diff`). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Verify lines 1-44, 52-82, and 30 are UNCHANGED. Flag any unaccounted changes.
  Output: `Task [1/1 compliant] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **1**: `fix(ci): replace silent merge failure with explicit conflict detection` - `.github/workflows/upstream-sync.yml`
  Pre-commit: (none — YAML file)

---

## Success Criteria

### Verification Commands
```bash
# Syntax check the bash block
bash -n .github/workflows/upstream-sync.yml 2>&1 || echo "Note: bash -n on YAML is indirect"
# Verify "|| true" on git merge is GONE
grep -n "git merge.*|| true" .github/workflows/upstream-sync.yml && echo "FAIL: || true still on merge" || echo "PASS: no || true on merge"
# Verify "exit 1" is present (conflict path)
grep -n "exit 1" .github/workflows/upstream-sync.yml
# Verify "if ! git merge" pattern exists
grep -n "if ! git merge" .github/workflows/upstream-sync.yml
# Verify git merge --abort exists
grep -n "git merge --abort" .github/workflows/upstream-sync.yml
# Verify gh issue create exists
grep -n "gh issue create" .github/workflows/upstream-sync.yml
# Verify line 30 (git remote add) still has || true
grep -n "git remote add upstream.*|| true" .github/workflows/upstream-sync.yml
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] Exit 1 on conflict (not exit 0)
- [ ] Separate commit for prune (not --amend)
- [ ] Lines outside 46-50 unchanged