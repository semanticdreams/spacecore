---
name: subagent-driven-development
description: Use when executing implementation plans with independent tasks using specialized subagents
---

# Subagent-Driven Development

Execute plan by dispatching the **implementer** subagent per task, a task review (spec compliance + code quality) by the **reviewer** subagent after each, a fix loop if needed, and a broad whole-branch review at the end. The **adjudicator** resolves findings at the fix-loop cap.

**Why subagents:** Each role has a specialized prompt and the right model for its job. The controller constructs exactly what each subagent needs — no inherited session context.

## Model Selection

All ordinary project roles use `opencode-go/glm-5.3-flash`, variant `high`.
Only read-only `expert-advisor` uses `openai/gpt-6.1-sol` high. Project roles, not
inherited built-in/hidden/global agents, are covered; use project `explorer` for
exploration. Fix-loop retries keep the GLM implementer, including rounds 4-5.

## Handoff delivery preflight

Apply `AGENTS.md#fail-closed-handoff-delivery` before consultation, verdict, fix,
cap or completion transitions for every received report, including targeted/CI
and adjudication. One same-author format-only redelivery, marked spent before
dispatch, is not a code-fix round. Valid delivery resumes the ordinary handler,
not approval; exhausted/stale/untrusted delivery blocks without a budget reset.
Quarantined delivery is not the task's end: apply the canonical `Autonomous
operational recovery` rule before replaying work — authorize replacement work
for the missing/unusable assessment on the same verified branch and base/head
range, record immutable failure ancestry and every preserved obligation, and
keep task-wide failure counts and budgets; recovery is not a budget reset,
review shopping or approval. Missing records block only the replacement
dispatch while they are gathered autonomously.

## Pending consultation handler

Apply the canonical `AGENTS.md` contract before normal report/review/fix/cap
transitions. Every architecture/software-design/system-contract decision needs a
GLM proposal, bounded GPT critique of original sources and evidenced reconciliation
before dependent implementation, including confident local/UI/internal design.
Reuse unchanged reconciled decisions; reopen material design/contract/assumption
changes. The same material failure after one focused repair also requires advice
before another repair; initial syntax/typo repair, expected TDD RED and routine
follow-through alone do not. Critical unresolved boundaries/evidenced material
technical conflicts trigger advice; unknown product/API/data policy is human-owned.

The task-capable controller handles implementer/planner `NEEDS_CONTEXT` containing
`consultation_request`, reviewer (full/targeted/CI) or adjudicator
`status: needs_consultation`, and diagnostic `verdict: needs_consultation` first:

1. Validate the canonical request fields, including nonempty `glm_proposal` for
   design/contract decisions. Workers keep delegation denied; this is a pending
   request, not a finding, blanket role blocker, approval or full GPT task.
2. Dispatch `expert-advisor` for that one question with inspectable original
   sources/diffs and evidence, not only the GLM summary.
3. Record scope/proposal/evidence/critique and evidenced reconciliation in existing
   handoff/progress artifacts. Resolve/validate material findings or escalate to
   the human. Unavailable advice or unanswered necessary decisions block dependent
   work. Reconsult only for genuinely new material evidence; do not loop for approval.
4. Return the decision/evidence to the original GLM worker to finish its own
   report/review/adjudication. Resume the interrupted transition only after its
   normal verdict; expert advice is not pass/verified/confirmed. Requests alone do
   not consume repair rounds, reset fix caps or replace independent GLM review.

Capability wrappers retain verbatim JSON/refusals; advice cannot grant authority.

## Setup

1. **Durable ledger:** use `.opencode/skills/subagent-driven-development/scripts/sdd-workspace --progress PLAN_FILE` to resolve `<plan-stem>-progress.md` beside a canonical plan under `docs/plans/`. This mode is read-only: it returns a non-ignored candidate path, not a created or tracked file. The controller verifies plan/task identity, branch, source/review ranges and existing ownership before creating or appending; a filename is not identity. Stop on an unrelated existing document or ambiguous ownership instead of overwriting it.

2. **Private workspace and resume:** the existing `sdd-workspace PLAN_FILE` invocation still resolves/creates ignored scratch for briefs, reports, raw handoffs and diffs, not durable ledgers. Before resuming, reconcile the public ledger with any retained legacy scratch `progress.md`: verify unchanged assignment/range facts and retain later progress and spent `correction_used` allowances. Never blindly prefer a stale public ledger, merge contradictory verdicts, or reset an allowance. If only a legacy ledger exists, retain its original unchanged and prepare an explicitly privacy-reviewed summary in the public ledger with source provenance. Do not automatically copy private content or mutate originals. Missing/untrusted facts or divergent ownership block dependent work; ask for context rather than manufacturing a verdict. All new durable updates go to the reconciled public ledger.

3. **Read the plan once** and create a todo per task.

4. **Pre-flight scan:** check for tasks that contradict each other or the plan's Global Constraints. Present findings as a batched question before execution.

## The Task Loop

### 1. Dispatch the Implementer

Record BASE (`git rev-parse HEAD`) before dispatching.

**Ordinary checkpoint handoff:** The assigned implementer implements, validates,
self-reviews, and creates task-scoped local checkpoint commits before reporting.
Review covers the complete BASE..HEAD range, including every checkpoint, not
only the latest commit. A checkpoint, clean tree, self-review, or DONE is not
approval; independent review and applicable finishing gates still block task
completion, publication, and integration. Implementers gain no push, PR,
integration, or history-rewrite authority. Preserve unrelated worktree and index
entries; never absorb, discard, or unstage them. If safe task isolation is
unclear, return NEEDS_CONTEXT.

**Explicit stage-only/no-commit handoff:** When the assignment requires it,
dispatch the implementer with that restriction instead of checkpointing. Repeat
the restriction on every fix dispatch. Review the complete assigned pending
diff, including additions; for staged handoffs, require all assigned content
staged and use `git diff --staged -- <assigned paths>` plus a complete file
manifest. Confirm no assigned unstaged or untracked content is omitted. For an
uncommitted worktree handoff, include both staged and unstaged assigned changes
and explicitly include new-file contents. Do not use an unchanged BASE..HEAD
package as evidence of pending edits. Keep unrelated index entries untouched.
These handoffs remain uncommitted until independent pass, then the supervisor
may commit only the exact approved content. Newly edited policy never grants
retroactive checkpoint authority to a running no-commit session; restart
OpenCode before relying on updated instructions.

**Task brief:** run `.opencode/skills/subagent-driven-development/scripts/task-brief PLAN_FILE N` — it extracts the task's full text to a file. The controller's dispatch should include:
1. One line on where this task fits in the project
2. The brief path ("read this first — it is your requirements")
3. Interfaces and decisions from earlier tasks the brief cannot know
4. The report-file path (`task-N-report.md` in the workspace)
5. Context: whether this is a fresh dispatch or a fix-round resume
6. The targeted local validation default from `AGENTS.md` — the implementer should run the narrowest meaningful checks for the changed behavioral surface, not the full suite by default before every checkpoint commit.
7. The changed behavioral surface to validate (Fennel/UI/layout, C++ behind Fennel bindings, pure C++ utility, docs/prompt-only, or high-risk broad change).
8. `make build` as the runtime/freshness prerequisite when `./build/space` may be missing or stale (C++, CMake, runtime initialization, bindings, or host scaffolding changes).
9. For Fennel-facing work: compile check first (`make fennel-check` or touched-file `tools.fennel-check`), then constraints, then focused Fennel tests — with evidence reported in that order in the handoff.
10. A requirement that the implementer report explain validation coverage (why the selected checks cover the behavioral surface), not merely list commands.
11. A reminder that checkpoint commits are not final integration sign-offs — the reviewer must still approve before the task is complete. Do not claim ready-to-merge until the applicable PR CI gate is green.
12. The handoff mode: ordinary validated/self-reviewed checkpoints with all SHAs,
    or explicit stage-only/no-commit with a complete assigned file list and
    pending-diff review evidence. Repeat a no-commit restriction on fix resumes.

**Report file:** `task-N-report.md` in the plan's workspace. The implementer writes its full report there and returns only status summary.

For Fennel-facing feature or bugfix tasks, expect the report to include compile-check evidence before constraint validation evidence, plus a constraint-impact note when relevant. Missing compile evidence is a ledger triage item unless the reported command clearly included the `fennel-check` gate. Include the same lightweight constraint-impact signal in ledger entries when it is useful for follow-up triage, and note recurring delimiter/enclosing form repair issues for follow-up if they obstruct tasks.

**Never make a subagent read the whole plan file.** The brief is the single source of requirements. Exact values (numbers, magic strings, signatures, test cases) appear only in the brief.

Never dispatch multiple implementation subagents in parallel (conflicts).

### 2. Handle the Report

Implementer subagents report one of four statuses:

- **DONE:** For ordinary checkpoints, verify the reported SHAs and generate the
  complete task review package (`.opencode/skills/subagent-driven-development/scripts/review-package PLAN_FILE BASE HEAD`).
  For explicit stage-only/no-commit work, prepare the complete assigned pending
  diff and file manifest as described above instead. Then dispatch the **reviewer**
  subagent in FULL REVIEW MODE with: the brief path, the report file path, the
  review evidence path, and the plan's Global Constraints. See below for review dispatch format.

- **DONE_WITH_CONCERNS:** Read the concerns. If about correctness or scope, address them before review. If observations (e.g., "this file is getting large"), note them and proceed to review.

**Atomic handoff (review dispatch):** When DONE or DONE_WITH_CONCERNS proceeds to review, the review-package generation and reviewer dispatch form a single atomic handoff. Do not emit any user-facing status update (including "review queued," "in progress," "waiting," or ledger/todo changes) before the reviewer `task` tool call has actually been issued. If the reviewer dispatch cannot proceed, report BLOCKED explicitly rather than implying a handoff that hasn't happened.

- **NEEDS_CONTEXT:** If it contains `consultation_request`, run the pending
  consultation handler first. Otherwise provide missing context and re-dispatch.

- **BLOCKED:** Assess the blocker — provide more context, or if the task is too large, break it into smaller pieces. If the plan is wrong, escalate to the human.

### 3. Review the Task

Dispatch the **reviewer** subagent in FULL REVIEW MODE. The reviewer's prompt body should specify:

```
You are reviewing Task N using FULL REVIEW MODE.

Task brief: [BRIEF_FILE]
Implementer report: [REPORT_FILE]
Review package (diff): [DIFF_FILE]

Global constraints:
[Copy verbatim from the plan's Global Constraints section]
```

The reviewer returns JSON with verification results. Handle `needs_consultation`
using the pending handler before findings or completion; it is not approval.
Ordinary fields remain `status` (pass/candidates_found/requires_human),
`candidate_findings`, `cannot_verify_from_diff`, and `non_blocking_notes`.

**Large review packages:** If the review package contains a `## Manifest` section with a file checklist, the reviewer MUST enumerate every file in the manifest and report in `non_blocking_notes` that all manifest entries were inspected. Any file the reviewer could not inspect must be reported as a `cannot_verify_from_diff` item with the file name and reason.

- Minor findings: record in the ledger (`Task <N>: minor (deferred): <one-liner>`) — they don't enter the fix loop.
- Plan-mandated contradictions: present to the human.
- Critical and Important findings enter the fix loop.

### 4. The Fix Loop

Triggered when review status is `candidates_found` with Critical or Important findings.

**Atomic handoff:** When Critical or Important findings are returned and no `requires_human` or BLOCKED condition applies, immediately dispatch/resume the implementer with the open findings in the same turn. Do not pause for user acknowledgement or say "I'll send these next." User-facing status may be emitted only after the implementer has been dispatched/resumed, or when human input is actually required.

**Rounds 1-3:** Dispatch the implementer with the open findings. It is being *resumed* — it knows the code and the task. The dispatch should include: brief path, report-file path, and the findings verbatim.

**Rounds 4-5:** The implementer should try fresh — this is a hard stall. Same model but frame it as a fresh dispatch: "A prior implementer attempted this task and could not converge. You own it now. Read the report file for what was tried."

Before any further repair of the same material failure after one focused repair,
use the pending consultation handler. This is scoped advice, not a model swap.

**Every round:** Record `FIX_BASE=$(git rev-parse HEAD)` before dispatching the
fix. The implementer fixes, re-runs covering tests, self-reviews, checkpoints only
assigned accepted fixes, and appends a fix report with SHAs to the report file.
After the implementer returns, generate the complete fix-range package:
`.opencode/skills/subagent-driven-development/scripts/review-package PLAN_FILE FIX_BASE HEAD`.
Prior approval does not cover subsequent edits; each FIX_BASE..HEAD range needs
independent verification. For explicit stage-only/no-commit assignments, repeat
that restriction on the fix dispatch, leave fixes uncommitted, and refresh the
complete assigned pending diff and manifest (including additions and updated
staged fixes) instead of generating a commit-only package. Pass the applicable
evidence to the reviewer in TARGETED VERIFICATION MODE for a scoped re-review:

```
You are verifying fixes for Task N using TARGETED VERIFICATION MODE.

Task brief: [BRIEF_FILE]
Implementer report (fix reports appended): [REPORT_FILE]
Findings under verification: [list findings verbatim]
Review package (fix diff): [FIX_DIFF_FILE]
```

For TARGETED VERIFICATION MODE, handle `needs_consultation` before verified/fix_failed
routing and before the cap. Resume that reviewer with reconciled evidence.

**The breaker (round 5 cap):** When round 5's re-review still leaves findings open, dispatch the **adjudicator** subagent with the open findings and the plan. Handle adjudicator `needs_consultation` through the pending handler before accept/park/escalate routing. Resume adjudication after reconciliation; no request bypasses the cap. Parked findings go to the ledger for the final review.

### 5. Complete the Task

**Before marking a task complete**, verify that the reviewer was dispatched
and returned a verdict for this task. This means: you must have actually
dispatched the reviewer subagent for this task and consumed its JSON response.
If the reviewer was never dispatched for this task, STOP — dispatch the
reviewer now. Never write "review clean" to the ledger without first
dispatching and consuming the reviewer's verdict.

Ensure all reviewed changes are committed before marking the task complete.
Ordinary reviewed checkpoints need no extra or empty post-review commit. For
review-first handoffs, the supervisor checks for subsequent edits and unrelated
staged content, then commits only the exact approved assigned content. Any new
edits require refreshed review evidence; never absorb unrelated work to satisfy
completion or finishing clean-tree gates.

When review passes or findings are parked at the cap, append to the ledger
with the reviewer's status recorded:

- `Task <N>: complete (commits <base>..<head>, reviewer: pass)`
- `Task <N>: complete (commits <base>..<head>, K parked, adjudicator: accept)`

Mark the todo complete only after the durable ledger entry is written and included
in the relevant checkpoint. Confirm the safe `docs/plans/` ledger is actually
tracked; a clean status alone does not prove that an ignored record was preserved.
Keep private original/corrected payloads unchanged in private storage. Do not
delete specs, plans or progress ledgers at task completion or cleanup.

## Single-Task Low-Risk Path

This low-ceremony path is eligible only when one focused task covers the
complete diff and the plan or controller explicitly marked the run as
single-task low-risk. It is not available for high-risk surfaces, multi-task
plans, parked findings, or unclear task boundaries.

The task loop does not change: each task still dispatches `implementer`, each
task still dispatches `reviewer`, and the fix loop and adjudicator rules remain
unchanged. The single-task path only affects whether an additional final
whole-branch review is required after that reviewed task completes.

The final whole-branch review may be skipped only when all of these are true:

- the single task covers the complete branch diff;
- the task reviewer passed;
- there are no parked findings;
- the reviewer did not request broader review;
- there is no high-risk surface;
- the plan or controller explicitly marked the run single-task low-risk.

If any condition fails, run the normal final whole-branch review.

## Final Whole-Branch Review

After all tasks, dispatch the **reviewer** in FULL REVIEW MODE with the complete branch diff (`.opencode/skills/subagent-driven-development/scripts/review-package PLAN_FILE MERGE_BASE HEAD`) and the ledger's deferred-minor and parked findings for triage.

Handle final-review `needs_consultation` before claiming a clean verdict or finishing.

During final review preparation, triage repeated `constraint obstructed/noisy` notes as possible constraint-system follow-ups rather than one-off task failures.

## Finish

When final review is clean, use the finishing-a-development-branch skill. Do
not report implementation complete merely because final review passed. Final
review passing does not mean ready-to-merge — the finishing skill chooses the
required final validation from `AGENTS.md` for the changed surface, and **PR CI**
remains the authoritative full integration gate before any ready-to-merge claim.
If the single-task low-risk path skipped final whole-branch review, that skip is
only a review de-duplication decision: it is not a ready-to-merge claim and does
not skip finishing validation, current-base checks, or **PR CI**.

OpenCode users must restart after `.opencode/**` changes for the updated
agent and skill instructions to take effect.

If finishing validation fails, or if the branch is behind current `origin/main`,
stay in coordination mode. Follow the finishing skill's current-base and
validation-failure loops: fetch `origin`, safe-merge `origin/main` when
permitted, invoke `systematic-debugging` for required validation failures,
continue investigating even when failures appear unrelated, flaky,
timing-dependent, or environmental, route conflicts and repository fixes
through `implementer` → `reviewer` → pass, commit reviewed fixes, rerun
validation, and only finish or create a PR when the required suite is green.

Report BLOCKED or HUMAN_DECISION_REQUIRED only when systematic debugging
establishes that progress requires credentials, inaccessible infrastructure,
unsafe git history decisions, unreproducible behavior after reasonable evidence
gathering, or a product/API/data/architecture choice. Do not rebase or
force-push unless the human explicitly requests it.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Close enough on spec compliance" | Reviewer found spec gaps = not done. Fix or hit the cap and adjudicate. |
| "I'll fix it myself, dispatching is overhead" | Controller fixes pollute your context and skip review. Resume the implementer. |
| "One more round will converge" | Past the cap, rounds don't converge — the failure is structural. Adjudicate and route. |
| "The fix was small, skip the re-review" | Unreviewed fixes are how regressions land. Every round ends with a scoped re-review. |
| "The checkpoint or DONE means we can publish now" | Checkpoints are review inputs, not approval. Independent review and finishing gates still apply, including for tiny tasks. |
| "The new policy permits this session to commit staged-only work" | Explicit no-commit assignments still govern, including fixes. Review the pending content before the supervisor commits it; restart to load new policy. |
| "Ledger bookkeeping is overhead" | The ledger is what survives compaction. Controllers without one have re-dispatched entire completed task sequences. |
