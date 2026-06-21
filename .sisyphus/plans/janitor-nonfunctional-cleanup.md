# Janitor Non-Functional Cleanup Pass 1

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task.

## TL;DR

> **Quick Summary**: Perform a conservative, deletion-only first cleanup pass for Janitor-Agent by removing six non-functional upstream/readme/planning markdown files while preserving upstream Hermes merge compatibility.
>
> **Deliverables**:
> - Remove exactly six approved non-functional markdown files.
> - Keep all runtime, build, test, install, skills, provider, plugin, and upstream-sync-critical files untouched.
> - Add one future-cleanup candidate document for deeper cleanup review.
> - Capture lightweight verification evidence.
>
> **Estimated Effort**: Quick
> **Parallel Execution**: YES - 3 waves + final review
> **Critical Path**: T1 → T4/T5/T6 → T7 → Final Verification

---

## Context

### Original Request
The user wants to clean the Janitor-Agent repository relative to Hermes upstream by identifying files that are unnecessary for Janitor and creating a plan that makes the repository cleaner without complicating future upstream updates.

### Interview Summary
**Key Discussions**:
- Janitor must preserve upstream Hermes compatibility and avoid unnecessary merge friction.
- User chose **Plan C**: keep broad Hermes upstream content mostly in place, but avoid loading/adopting non-Janitor capabilities by default.
- Non-Janitor/Hermes skills remain available, but a Janitor profile adopts them only after explicit user confirmation.
- First cleanup pass must delete only non-functional files.
- Deeper cleanup candidates should be documented for a future plan, not removed now.
- Verification level selected: lightweight only.

**Research Findings**:
- Janitor-specific runtime additions are small and should not be touched.
- Large upstream surfaces such as `skills/`, `providers/`, `plugins/`, `web/`, `website/`, and `apps/` are deferred because removing them would complicate upstream merges.
- Safe first-pass deletion set is limited to six non-functional markdown files:
  - `README.ur-pk.md`
  - `README.zh-CN.md`
  - `hermes-already-has-routines.md`
  - `.plans/openai-api-server.md`
  - `.plans/streaming-support.md`
  - `plans/gemini-oauth-provider.md`
- `.plans/` and `plans/` must remain because they are not guaranteed empty after this deletion set.

### Metis Review
**Identified Gaps** (addressed):
- Branch isolation must be explicit.
- Deletion list must be exact, not category-based.
- Parent directories must not be removed.
- Borderline docs such as `master_plan.md`, `janitor-project.md`, `MERGE_GUIDE.md`, and `docs/RESTRUCTURE_v5.md` should be kept in pass 1.
- Future cleanup candidates must be documented in the same pass.

### Oracle Phase 1 Review
Oracle initially rejected the generic scope because parent directory removal was invalid and deletion/keep lists were not explicit enough. The draft was corrected, and Oracle returned `CHECK [5/5] PASS | VERDICT: GO`.

### Momus High-Accuracy Review
High-accuracy mode was selected by the user after plan generation. Momus reviewed `.sisyphus/plans/janitor-nonfunctional-cleanup.md` and returned `[OKAY]`.

**Momus verdict summary**:
- All referenced files exist.
- Deletion and keep lists are exact and accurate.
- Every task has executable QA scenarios with concrete commands and expected outputs.
- The wave-based dependency matrix is internally consistent.
- The plan is executable by a capable developer without additional context.

---

## Work Objectives

### Core Objective
Execute a low-risk repository cleanup that removes only pre-approved non-functional files while preserving Janitor runtime behavior, upstream Hermes merge compatibility, and future cleanup traceability.

### Concrete Deliverables
- Delete exactly these files:
  - `README.ur-pk.md`
  - `README.zh-CN.md`
  - `hermes-already-has-routines.md`
  - `.plans/openai-api-server.md`
  - `.plans/streaming-support.md`
  - `plans/gemini-oauth-provider.md`
- Create `docs/maintenance/janitor-future-cleanup-candidates.md` documenting deferred cleanup targets.
- Save verification evidence under `.sisyphus/evidence/`.
- Produce one atomic cleanup commit.

### Definition of Done
- [ ] Only the six approved files are deleted.
- [ ] `docs/maintenance/janitor-future-cleanup-candidates.md` exists and lists deferred candidates with rationale.
- [ ] `.plans/` and `plans/` directories remain present if they still contain any files.
- [ ] No runtime/source/build/test/install files are deleted or modified.
- [ ] Lightweight verification evidence is captured.
- [ ] Final verification wave approves.

### Must Have
- Exact deletion set only; no opportunistic additions.
- Feature-branch isolation before any deletion.
- Pre- and post-cleanup `git status` evidence.
- Reference checks for every deleted filename.
- Future-candidate document with at least low/medium/high-risk sections.

### Must NOT Have (Guardrails)
- Must NOT rename or search-and-replace `hermes` in core files.
- Must NOT delete or modify `cli.py`, `run_agent.py`, `hermes_cli/`, `agent/`, `tools/`, `gateway/`, `providers/`, `plugins/`, `skills/`, `tests/`, `ui-tui/`, `tui_gateway/`, `cron/`, `acp_adapter/`, `apps/`, `web/`, `website/`, `optional-skills/`, `optional-mcps/`, `locales/`, `nix/`, `packaging/`, or installer/build infrastructure.
- Must NOT delete `master_plan.md`, `janitor-project.md`, `MERGE_GUIDE.md`, or `docs/RESTRUCTURE_v5.md` in this pass.
- Must NOT remove `.plans/` or `plans/` directories.
- Must NOT run broad cleanup of generated artifacts, providers, plugins, skills, or upstream docs in this pass.
- Must NOT require broad test suite execution for this docs-only cleanup.

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES, but not used for this docs-only cleanup.
- **Automated tests**: None for this pass.
- **Framework**: N/A
- **Reason**: User explicitly selected lightweight verification because this pass deletes only non-functional files.

### QA Policy
Every task includes agent-executed QA scenarios. Evidence must be saved to `.sisyphus/evidence/`.

- **Filesystem/Git QA**: Use Bash/git commands.
- **Reference QA**: Search for deleted filenames in tracked files.
- **Evidence**: terminal output captured to `.sisyphus/evidence/task-{N}-{scenario}.txt`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Preflight and classification, can run in parallel after branch creation):
├── T1: Create feature branch and baseline git evidence [quick]
├── T2: Confirm deletion and keep lists [quick]
├── T3: Baseline reference audit for deletion targets [quick]
└── T4: Draft future-cleanup candidate document [writing]

Wave 2 (Deletion and documentation finalization):
├── T5: Delete localized README files [quick]
├── T6: Delete non-functional planning/analysis markdown files [quick]
└── T7: Finalize future-cleanup candidate document [writing]

Wave 3 (Lightweight verification and commit):
├── T8: Post-delete status and reference verification [quick]
├── T9: Guardrail audit for untouched protected areas [quick]
└── T10: Atomic commit preparation [quick]

Wave FINAL:
├── F1: Plan compliance audit (oracle)
├── F2: Code quality / diff hygiene review (unspecified-high)
├── F3: Real QA evidence replay (unspecified-high)
└── F4: Scope fidelity check (deep)
```

### Dependency Matrix

- **T1**: depends on none; blocks T5, T6, T8, T10.
- **T2**: depends on none; blocks T5, T6, T7.
- **T3**: depends on none; blocks T8.
- **T4**: depends on none; blocks T7.
- **T5**: depends on T1, T2; blocks T8, T9, T10.
- **T6**: depends on T1, T2; blocks T8, T9, T10.
- **T7**: depends on T2, T4; blocks T8, T9, T10.
- **T8**: depends on T1, T3, T5, T6, T7; blocks T10.
- **T9**: depends on T5, T6, T7; blocks T10.
- **T10**: depends on T8, T9; blocks Final Verification.

### Agent Dispatch Summary

- **Wave 1**: T1-T3 → `quick`; T4 → `writing`
- **Wave 2**: T5-T6 → `quick`; T7 → `writing`
- **Wave 3**: T8-T10 → `quick`
- **FINAL**: F1 → `oracle`; F2/F3 → `unspecified-high`; F4 → `deep`

---

## TODOs

> Implementation + verification = ONE task. Every task has exact references and QA scenarios.

- [ ] 1. Create feature branch and baseline git evidence

  **What to do**:
  - Start from `/home/reck/Janitor-Agent`.
  - Create a feature branch such as `chore/janitor-nonfunctional-cleanup-pass-1`.
  - Capture baseline `git status --porcelain`, `git rev-parse HEAD`, and `git branch --show-current`.

  **Must NOT do**:
  - Do not work directly on the active upstream-sync worktree.
  - Do not delete files in this task.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple git preflight and evidence capture.
  - **Skills**: [`git-master`]
    - `git-master`: Needed for branch/status/commit safety.
  - **Skills Evaluated but Omitted**:
    - `tui-compilation`: Not a TUI change.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T5, T6, T8, T10
  - **Blocked By**: None

  **References**:
  - `AGENTS.md` - Janitor fork directives and upstream-sync safety model.
  - `MERGE_GUIDE.md` - Upstream merge workflow that this cleanup must not complicate.

  **Acceptance Criteria**:
  - [ ] Current branch is not `main` after branch creation.
  - [ ] Baseline evidence file exists: `.sisyphus/evidence/task-1-git-baseline.txt`.
  - [ ] Baseline status is clean or any pre-existing changes are explicitly reported before proceeding.

  **QA Scenarios**:
  ```
  Scenario: Baseline branch isolation
    Tool: Bash (git)
    Preconditions: working directory is /home/reck/Janitor-Agent
    Steps:
      1. Run `git status --porcelain`.
      2. Run `git rev-parse HEAD`.
      3. Run `git branch --show-current`.
      4. Save combined output to `.sisyphus/evidence/task-1-git-baseline.txt`.
    Expected Result: Evidence shows a clean or explicitly acknowledged working tree and a cleanup feature branch.
    Failure Indicators: Work happens directly on upstream-sync worktree, branch is ambiguous, or untracked modifications are ignored.
    Evidence: .sisyphus/evidence/task-1-git-baseline.txt
  ```

  **Commit**: NO

- [ ] 2. Confirm exact deletion and keep lists

  **What to do**:
  - Confirm the six deletion targets exist or document if any are already absent.
  - Confirm keep-listed files and directories are not scheduled for deletion.
  - Record the deletion list and keep list in evidence.

  **Must NOT do**:
  - Do not expand deletion list.
  - Do not remove `.plans/` or `plans/` directories.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Direct filesystem classification.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `codebase-memory`: This is non-code file classification, not symbol discovery.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T5, T6, T7
  - **Blocked By**: None

  **References**:
  - `.sisyphus/drafts/janitor-repo-cleanup.md` - Interview decisions and exact deletion/keep lists.

  **Acceptance Criteria**:
  - [ ] Evidence lists the six approved deletion targets exactly.
  - [ ] Evidence lists `master_plan.md`, `janitor-project.md`, `MERGE_GUIDE.md`, `docs/RESTRUCTURE_v5.md`, `.plans/`, and `plans/` as keep items.
  - [ ] No extra delete candidates are added.

  **QA Scenarios**:
  ```
  Scenario: Deletion scope is exact
    Tool: Bash (filesystem/git)
    Preconditions: repository checkout exists
    Steps:
      1. Check existence of each approved deletion target.
      2. Check existence of each explicit keep item.
      3. Save results to `.sisyphus/evidence/task-2-scope-confirmation.txt`.
    Expected Result: Evidence contains exactly six deletion targets and the explicit keep list.
    Failure Indicators: A runtime/source/build/test file appears in deletion scope, or `.plans/`/`plans/` directories are scheduled for removal.
    Evidence: .sisyphus/evidence/task-2-scope-confirmation.txt
  ```

  **Commit**: NO

- [ ] 3. Run baseline reference audit for deletion targets

  **What to do**:
  - Search tracked files for these literal names before deletion:
    - `README.ur-pk.md`
    - `README.zh-CN.md`
    - `hermes-already-has-routines.md`
    - `openai-api-server.md`
    - `streaming-support.md`
    - `gemini-oauth-provider.md`
  - Record whether matches are only self-references/cross-references among deleted files.

  **Must NOT do**:
  - Do not modify references in this pass.
  - Do not convert this into a documentation rewrite.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: String reference audit.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: No code or tests are being authored.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T8
  - **Blocked By**: None

  **References**:
  - `README.md` - Main Janitor README that must not depend on deleted localized READMEs.
  - `AGENTS.md` - Janitor directives; must not depend on deleted docs.

  **Acceptance Criteria**:
  - [ ] Evidence file exists with search results for all six filenames.
  - [ ] Evidence explicitly notes localized README self/cross-reference status.
  - [ ] Any unexpected reference outside the deletion set stops execution for review.

  **QA Scenarios**:
  ```
  Scenario: No load-bearing references to deletion targets
    Tool: Bash (git grep or equivalent search)
    Preconditions: deletion targets still exist
    Steps:
      1. Search tracked files for each deletion target filename.
      2. Classify each match as self-reference, cross-reference among deleted files, or external reference.
      3. Save output to `.sisyphus/evidence/task-3-reference-baseline.txt`.
    Expected Result: No external runtime/build/config references are found.
    Failure Indicators: `README.md`, `AGENTS.md`, CI config, package metadata, installer scripts, or source files reference a deletion target.
    Evidence: .sisyphus/evidence/task-3-reference-baseline.txt
  ```

  **Commit**: NO

- [ ] 4. Draft future-cleanup candidate document

  **What to do**:
  - Create initial content for `docs/maintenance/janitor-future-cleanup-candidates.md`.
  - Include sections:
    - Purpose
    - Pass 1 excluded by design
    - Low-risk future candidates
    - Medium-risk future candidates
    - High-risk future candidates
    - Architectural/user-policy candidates
  - Include explicit adoption policy: upstream/Hermes skills become persistent in a Janitor profile only after explicit user confirmation.

  **Must NOT do**:
  - Do not recommend immediate deletion of runtime surfaces.
  - Do not change configuration in this task.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Documentation artifact creation.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `frontend-ui-ux`: No UI work.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T7
  - **Blocked By**: None

  **References**:
  - `AGENTS.md` - Janitor fork directives and optional skills philosophy.
  - `MERGE_GUIDE.md` - Upstream-sync constraints.
  - `.sisyphus/drafts/janitor-repo-cleanup.md` - User decisions from interview.

  **Acceptance Criteria**:
  - [ ] Draft document content includes all required sections.
  - [ ] Document does not instruct immediate deletion outside pass 1.
  - [ ] Explicit skill adoption policy is recorded.

  **QA Scenarios**:
  ```
  Scenario: Future cleanup document captures deferred scope
    Tool: Bash (filesystem/text check)
    Preconditions: repository checkout exists
    Steps:
      1. Create or stage draft content for `docs/maintenance/janitor-future-cleanup-candidates.md`.
      2. Verify the document contains `SECURITY.md`, `CONTRIBUTING.md`, `website/`, `web/`, `apps/`, `optional-skills/`, `optional-mcps/`, `locales/`, `nix/`, `packaging/`, `skills/*`, `providers/*`, and `plugins/*`.
      3. Save verification output to `.sisyphus/evidence/task-4-future-doc-draft.txt`.
    Expected Result: Document captures future candidates without authorizing their deletion in pass 1.
    Failure Indicators: Document suggests deleting runtime surfaces now or omits the explicit skill-adoption policy.
    Evidence: .sisyphus/evidence/task-4-future-doc-draft.txt
  ```

  **Commit**: NO

- [ ] 5. Delete localized upstream README files

  **What to do**:
  - Delete only:
    - `README.ur-pk.md`
    - `README.zh-CN.md`
  - Use git-aware deletion so the diff records removals cleanly.

  **Must NOT do**:
  - Do not delete `README.md`.
  - Do not delete `CONTRIBUTING.md` or `SECURITY.md` in this pass.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Exact two-file deletion.
  - **Skills**: [`git-master`]
    - `git-master`: Ensures safe tracked-file deletion.
  - **Skills Evaluated but Omitted**:
    - `writing`: No prose editing in this task.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: T8, T9, T10
  - **Blocked By**: T1, T2

  **References**:
  - `README.md` - Main README to keep.
  - `README.ur-pk.md` - Deletion target.
  - `README.zh-CN.md` - Deletion target.

  **Acceptance Criteria**:
  - [ ] `README.ur-pk.md` is removed from git diff.
  - [ ] `README.zh-CN.md` is removed from git diff.
  - [ ] `README.md` remains unchanged.

  **QA Scenarios**:
  ```
  Scenario: Localized README deletion only
    Tool: Bash (git)
    Preconditions: T1 and T2 complete
    Steps:
      1. Remove `README.ur-pk.md` and `README.zh-CN.md`.
      2. Run `git status --short`.
      3. Save output to `.sisyphus/evidence/task-5-readme-delete.txt`.
    Expected Result: Status shows deletions for exactly those two README localization files from this task.
    Failure Indicators: `README.md`, `CONTRIBUTING.md`, or `SECURITY.md` is modified/deleted.
    Evidence: .sisyphus/evidence/task-5-readme-delete.txt
  ```

  **Commit**: NO

- [ ] 6. Delete non-functional planning/analysis markdown files

  **What to do**:
  - Delete only:
    - `hermes-already-has-routines.md`
    - `.plans/openai-api-server.md`
    - `.plans/streaming-support.md`
    - `plans/gemini-oauth-provider.md`
  - Leave `.plans/` and `plans/` directories in place.

  **Must NOT do**:
  - Do not remove `.plans/` directory.
  - Do not remove `plans/` directory.
  - Do not delete `master_plan.md` or `janitor-project.md`.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Exact four-file deletion.
  - **Skills**: [`git-master`]
    - `git-master`: Safe tracked-file deletion and status review.
  - **Skills Evaluated but Omitted**:
    - `codebase-memory`: Non-code doc deletion.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: T8, T9, T10
  - **Blocked By**: T1, T2

  **References**:
  - `hermes-already-has-routines.md` - Deletion target.
  - `.plans/openai-api-server.md` - Deletion target.
  - `.plans/streaming-support.md` - Deletion target.
  - `plans/gemini-oauth-provider.md` - Deletion target.

  **Acceptance Criteria**:
  - [ ] The four listed files are removed.
  - [ ] `.plans/` and `plans/` directories are not removed.
  - [ ] `master_plan.md` and `janitor-project.md` remain unchanged.

  **QA Scenarios**:
  ```
  Scenario: Planning artifact deletion only
    Tool: Bash (git/filesystem)
    Preconditions: T1 and T2 complete
    Steps:
      1. Remove the four approved planning/analysis markdown files.
      2. Verify `.plans/` and `plans/` directories still exist if they contain files.
      3. Run `git status --short`.
      4. Save output to `.sisyphus/evidence/task-6-planning-delete.txt`.
    Expected Result: Status shows deletions for exactly the four approved files from this task; parent directories are not removed.
    Failure Indicators: Deletion of `master_plan.md`, `janitor-project.md`, `.plans/` directory, or `plans/` directory.
    Evidence: .sisyphus/evidence/task-6-planning-delete.txt
  ```

  **Commit**: NO

- [ ] 7. Finalize future-cleanup candidate document

  **What to do**:
  - Write `docs/maintenance/janitor-future-cleanup-candidates.md`.
  - Include deferred candidates:
    - `SECURITY.md`, `CONTRIBUTING.md`, `docs/hermes-kanban-v1-spec.pdf`
    - `master_plan.md`, `janitor-project.md`, `docs/superpowers/`
    - `website/`, `web/`, `apps/`, `optional-skills/`, `optional-mcps/`, `locales/`, `nix/`, `packaging/`
    - non-Janitor `skills/*`, non-default `providers/*`, non-default `plugins/*`, legacy scripts
  - Explain that all are deferred to future plans because pass 1 prioritizes upstream merge compatibility.

  **Must NOT do**:
  - Do not edit `AGENTS.md` or `MERGE_GUIDE.md` in this pass.
  - Do not include instructions to delete high-risk surfaces immediately.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Documentation finalization.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `git-master`: Commit happens in T10.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: T8, T9, T10
  - **Blocked By**: T2, T4

  **References**:
  - `AGENTS.md` - Rules that explain why runtime/upstream files are deferred.
  - `MERGE_GUIDE.md` - Upstream merge compatibility rationale.

  **Acceptance Criteria**:
  - [ ] `docs/maintenance/janitor-future-cleanup-candidates.md` exists.
  - [ ] Document includes low/medium/high-risk sections.
  - [ ] Document records explicit per-profile skill adoption policy.
  - [ ] Document makes clear that these are future candidates, not current deletions.

  **QA Scenarios**:
  ```
  Scenario: Future cleanup document complete
    Tool: Bash (text/file checks)
    Preconditions: T4 draft complete
    Steps:
      1. Verify `docs/maintenance/janitor-future-cleanup-candidates.md` exists.
      2. Verify it contains the strings `Plan C`, `explicit user confirmation`, `SECURITY.md`, `CONTRIBUTING.md`, `website/`, `optional-skills/`, `skills/*`, `providers/*`, and `plugins/*`.
      3. Save output to `.sisyphus/evidence/task-7-future-doc-final.txt`.
    Expected Result: Document captures deferred cleanup candidates and policy rationale.
    Failure Indicators: Missing deferred categories or language implying immediate deletion.
    Evidence: .sisyphus/evidence/task-7-future-doc-final.txt
  ```

  **Commit**: NO

- [ ] 8. Post-delete status and reference verification

  **What to do**:
  - Run post-delete `git status --short`.
  - Confirm diff contains exactly six deletions plus one new future-cleanup document.
  - Search for deleted filenames again and confirm no external references remain.

  **Must NOT do**:
  - Do not fix references by editing unrelated files unless a blocking reference is found; instead stop and report.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Lightweight verification.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `tui-compilation`: No TUI change.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: T10
  - **Blocked By**: T1, T3, T5, T6, T7

  **References**:
  - `.sisyphus/evidence/task-3-reference-baseline.txt` - Baseline reference audit.

  **Acceptance Criteria**:
  - [ ] `git status --short` shows exactly expected deletions and one expected new doc.
  - [ ] Reference search finds no external references to deleted filenames.
  - [ ] Evidence file exists.

  **QA Scenarios**:
  ```
  Scenario: Post-delete verification passes
    Tool: Bash (git/search)
    Preconditions: T5, T6, and T7 complete
    Steps:
      1. Run `git status --short`.
      2. Search tracked files for the six deleted filenames.
      3. Run `git diff --name-status`.
      4. Save output to `.sisyphus/evidence/task-8-post-delete-verification.txt`.
    Expected Result: Output shows six deletions, one new future-cleanup document, and no external references to deleted files.
    Failure Indicators: Unexpected file modifications, deleted protected files, or references from runtime/config/docs that remain.
    Evidence: .sisyphus/evidence/task-8-post-delete-verification.txt
  ```

  **Commit**: NO

- [ ] 9. Guardrail audit for untouched protected areas

  **What to do**:
  - Verify no files changed under protected directories:
    - `skills/`, `providers/`, `plugins/`, `tools/`, `agent/`, `gateway/`, `hermes_cli/`, `tests/`, `ui-tui/`, `tui_gateway/`, `cron/`, `acp_adapter/`, `apps/`, `web/`, `website/`, `optional-skills/`, `optional-mcps/`, `locales/`, `nix/`, `packaging/`.
  - Verify kept docs remain unchanged.

  **Must NOT do**:
  - Do not run broad cleanup commands.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Diff hygiene check.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `ai-slop-remover`: No code cleanup.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: T10
  - **Blocked By**: T5, T6, T7

  **References**:
  - `AGENTS.md` - Protected Janitor/Hermes fork boundaries.

  **Acceptance Criteria**:
  - [ ] No protected runtime/build/test directory appears in `git diff --name-only`.
  - [ ] `master_plan.md`, `janitor-project.md`, `MERGE_GUIDE.md`, and `docs/RESTRUCTURE_v5.md` are unchanged.
  - [ ] Evidence file exists.

  **QA Scenarios**:
  ```
  Scenario: Protected areas untouched
    Tool: Bash (git)
    Preconditions: T5, T6, T7 complete
    Steps:
      1. Run `git diff --name-only`.
      2. Confirm no protected path prefixes appear.
      3. Confirm keep-listed docs are absent from the diff.
      4. Save output to `.sisyphus/evidence/task-9-guardrail-audit.txt`.
    Expected Result: Only approved deletion paths and `docs/maintenance/janitor-future-cleanup-candidates.md` appear.
    Failure Indicators: Any source, test, build, installer, skill, provider, plugin, or keep-listed doc appears in the diff.
    Evidence: .sisyphus/evidence/task-9-guardrail-audit.txt
  ```

  **Commit**: NO

- [ ] 10. Atomic commit preparation

  **What to do**:
  - Review `git diff --name-status`.
  - Stage only the six deletions and the future-cleanup document.
  - Commit with a detailed message listing every deleted path.

  **Must NOT do**:
  - Do not amend, force-push, rebase, or include unrelated files.
  - Do not commit if T8 or T9 evidence shows unexpected changes.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single atomic git commit.
  - **Skills**: [`git-master`]
    - `git-master`: Required for safe staging/commit workflow.
  - **Skills Evaluated but Omitted**:
    - `verification-before-completion`: Final verification wave handles completion claims.

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 sequential endpoint
  - **Blocks**: Final Verification
  - **Blocked By**: T8, T9

  **References**:
  - `.sisyphus/evidence/task-8-post-delete-verification.txt` - Must pass before commit.
  - `.sisyphus/evidence/task-9-guardrail-audit.txt` - Must pass before commit.

  **Acceptance Criteria**:
  - [ ] One atomic commit exists for this cleanup.
  - [ ] Commit includes only approved deletions and future-cleanup doc.
  - [ ] Commit message body lists the six deleted paths.

  **QA Scenarios**:
  ```
  Scenario: Atomic cleanup commit is scoped
    Tool: Bash (git)
    Preconditions: T8 and T9 passed
    Steps:
      1. Run `git diff --name-status` before staging.
      2. Stage only approved files.
      3. Commit with message `chore(cleanup): remove non-functional Janitor docs pass 1` and a body listing deleted files.
      4. Save `git show --name-status --stat HEAD` to `.sisyphus/evidence/task-10-commit.txt`.
    Expected Result: Latest commit contains exactly six deletions and one new future-cleanup document.
    Failure Indicators: Commit includes source/runtime/build/test files, unrelated docs, or missing future-cleanup document.
    Evidence: .sisyphus/evidence/task-10-commit.txt
  ```

  **Commit**: YES
  - Message: `chore(cleanup): remove non-functional Janitor docs pass 1`
  - Files: six deletion targets + `docs/maintenance/janitor-future-cleanup-candidates.md`
  - Pre-commit: T8 and T9 evidence must pass

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read this plan end-to-end. Verify the commit contains exactly the six deletion targets and `docs/maintenance/janitor-future-cleanup-candidates.md`. Verify all Must Have items and Must NOT Have guardrails. Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`.

- [ ] F2. **Diff Hygiene Review** — `unspecified-high`
  Inspect `git show --name-status --stat HEAD` and evidence files. Confirm no source/runtime/build/test/install directories changed. Output: `Diff Scope [PASS/FAIL] | Evidence [N/N] | VERDICT`.

- [ ] F3. **Real QA Evidence Replay** — `unspecified-high`
  Re-run the lightweight verification commands from T8 and T9. Confirm results match evidence. Save to `.sisyphus/evidence/final-qa/`. Output: `Scenarios [N/N pass] | VERDICT`.

- [ ] F4. **Scope Fidelity Check** — `deep`
  Compare actual diff against this plan. Reject any deletion outside the exact six targets or any missing future-cleanup document. Output: `Tasks [N/N compliant] | Unaccounted [CLEAN/N files] | VERDICT`.

---

## Commit Strategy

- **One commit only**: `chore(cleanup): remove non-functional Janitor docs pass 1`
- Include detailed body:
  - Deleted `README.ur-pk.md`
  - Deleted `README.zh-CN.md`
  - Deleted `hermes-already-has-routines.md`
  - Deleted `.plans/openai-api-server.md`
  - Deleted `.plans/streaming-support.md`
  - Deleted `plans/gemini-oauth-provider.md`
  - Added `docs/maintenance/janitor-future-cleanup-candidates.md`
- Do not stage unrelated files.

---

## Success Criteria

### Verification Commands
```bash
git status --short
# Expected: clean after commit, or only expected untracked evidence files if evidence is not committed

git show --name-status --stat HEAD
# Expected: six deletions + one added future-cleanup document

git diff HEAD~1..HEAD --name-only
# Expected: exactly the approved changed paths
```

### Final Checklist
- [ ] All six deletion targets removed.
- [ ] No protected areas changed.
- [ ] Keep-listed docs remain.
- [ ] Future-cleanup document exists.
- [ ] Evidence exists for baseline, scope, reference audit, post-delete status, guardrail audit, and commit.
- [ ] Final verification wave approves.
