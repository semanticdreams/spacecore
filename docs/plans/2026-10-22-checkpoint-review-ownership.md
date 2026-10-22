# Checkpoint and Review Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align local checkpoint ownership without weakening independent review.

**Architecture:** Implementers own ordinary local task checkpoints; reviewers
approve changes; supervisors own completion and guarded integration. Explicit
stage-only handoffs preserve specialized review-first workflows. No review-helper
or permission changes are needed.

**Tech Stack:** Markdown agent prompts, workflow skills, existing Git review
tooling, Python policy checker and pytest.

**Design:** `docs/specs/2026-10-22-checkpoint-review-ownership-design.md`

## Global Constraints

- This is a repository-local instruction correction, not a Git permission change.
- Do not change runtime tooling, home configuration, capability wrappers, or the selected fast-dev/live-dev lifecycle.
- Checkpoints, a clean tree, self-review, and DONE are not approval.
- Preserve unrelated work and index state. If task ownership cannot be isolated safely, return NEEDS_CONTEXT rather than absorbing or discarding changes.
- Explicit stage-only/no-commit assignments override the ordinary checkpoint handoff.
- The running session retains its existing stricter commit discipline: policy edits remain uncommitted until independent approval.
- Restart OpenCode before relying on updated agent or skill instructions; do not claim this session hot-reloaded them.

---

### Task 1: Align Strict-Flow Checkpoint and Review Ownership

**Files:**
- Modify: `AGENTS.md`
- Modify: `.opencode/agents/supervisor.md`
- Modify: `.opencode/agents/implementer.md`
- Modify: `.opencode/skills/subagent-driven-development/SKILL.md`
- Modify: `.opencode/skills/daily-devlog-automation/SKILL.md`
- Modify: `.opencode/skills/weekly-agent-workflow-automation/SKILL.md`
- Modify: `.opencode/skills/github-workflow-debug/SKILL.md`
- Modify: `docs/dev/features/opencode-agent-workflow.md`
- Inspect: `.opencode/skills/finishing-a-development-branch/SKILL.md`
- Inspect: `.opencode/skills/systematic-debugging/SKILL.md`
- Test, unchanged: `scripts/tests/test_check_opencode_permissions.py`
- Test, unchanged: `scripts/tests/test_opencode_windows_ci_policy_docs.py`

**Interfaces:**
- Preserve `review-package PLAN_FILE BASE HEAD [OUTFILE]` for ordinary committed
  task and fix ranges.
- Explicit staged-review assignments use complete assigned staged diffs,
  including new files and updates after fixes, not commit-only packages.
- Preserve statuses, reviewer contracts, permission mappings, capability routing,
  fix-loop/adjudication mechanics, and finishing requirements.

- [ ] **Step 1: Record baseline and bootstrap boundary.**

  The supervisor already recorded a clean starting tree and captured an audit
  plus five independent control simulations before edits. All five identified
  ordinary/tiny/fix commit-timing contradictions and missing staged-review
  exceptions. They withheld publication but disagreed about safe unrelated-index
  handling. Treat these as instruction simulations, not runtime Git execution.
  Retain their exact task responses in session evidence; summarize honestly in
  the implementation report.

  Record current HEAD and status before dispatch. Every implementation/fix
  handoff in this execution must say: **return policy edits uncommitted; do not
  commit, amend, push, or integrate. Future checkpoint permissions do not apply
  retroactively to this loaded session.**

- [ ] **Step 2: Align four core instruction files.**

  Add the actor-scoped rule under AGENTS.md Commit Conventions, leaving the
  fast/live-dev exception intact. Scope the supervisor's direct-commit rule to
  supervisor-owned commits; remove tiny-task pre-checkpoint review wording.
  A checkpoint does not count as approval. Completion must ensure all reviewed
  changes are committed without requiring another or empty commit.

  Change the implementer sequence to implement, validate, self-review,
  checkpoint assigned changes, report. Explicit stage-only/no-commit assignments
  override the default, including fixes; report no checkpoint in that case.
  Preserve unrelated index/worktree entries and surface unsafe isolation.
  Grant no publication or history-rewrite authority.

  SDD ordinary ordering: record BASE, implementer validates/self-reviews and
  checkpoints, package the complete BASE..HEAD, independent review. Repeat with
  FIX_BASE for accepted fixes. Prior approval does not cover subsequent edits.
  Explicit no-commit handoffs require pending-diff review instead.

- [ ] **Step 3: Preserve specialized handoffs and update canonical docs.**

  Daily and weekly automation must explicitly dispatch stage-only/no-commit
  implementation and fixes, review complete assigned staged content including
  new files, and commit only after pass. Workflow-debug's final staged landing
  and staged-fix dispatches must say the same; preserve its throwaway-branch
  CI lifecycle. Update the canonical agent workflow guide's blanket
  before-commit rule to describe actor ownership and approval/publication gates.

  Inspect finishing/debugging callers; retain compatible supervisor dirty-tree
  restrictions and committed-range debugging handoffs. Report any need to expand
  the eight-file scope before doing so. Do not rewrite historical plans.

- [ ] **Step 4: Run candidate wording and pressure simulations.**

  Supervisor dispatches five independent fresh-context read-only simulations
  against the revised full relevant prompts/skills. Use the same scenarios as
  the controls: urgent multi-checkpoint task plus premature publication request;
  tiny deadline task; FIX_BASE fix; explicit staged new file and fix resume;
  unrelated staged content. Add the current-session bootstrap counterexample.

  Each response reports next actor/action, commit owner/timing, review evidence,
  and completion/publication permission. Required outcomes: complete BASE..HEAD
  review, independent tiny-task approval, FIX_BASE..HEAD re-review, no premature
  publish, complete staged review and no early specialized commit, preserved
  unrelated index, and uncommitted policy edits in this execution.

  Manually inspect all five responses and retained exceptions. Fresh samples
  must have no prior answers. Deadline, senior-authority and sunk-cost pressure
  are combined in the scenario. If ambiguity remains, revise only that guidance
  and repeat affected simulations. Never claim simulation proves runtime loading.

- [ ] **Step 5: Run focused checks and relevant local suite.**

  ```bash
  git diff --check
  git diff --cached --check
  python3 scripts/check_opencode_permissions.py --repo-root .
  python3 -m pytest scripts/tests/test_check_opencode_permissions.py scripts/tests/test_opencode_windows_ci_policy_docs.py
  make opencode-check
  ```

  Search assigned files for before-commit and checkpoint wording, classifying
  specialized and supervisor-owned restrictions separately from ordinary tasks.
  Existing tests plus instruction simulations cover this prose-only change; no
  runtime build or new checker is required. Diagnose any required failure rather
  than bypassing it. Report executable results separately from simulations.

- [ ] **Step 6: Independently review complete pending changes.**

  Return an implementation report with validation and no commits. The supervisor
  dispatches reviewer with the design, this task's brief, report and complete
  assigned worktree/staged diff. Include assigned additions explicitly; do not
  use unchanged BASE..HEAD as proof of pending edits. Every fix stays uncommitted
  and is re-reviewed using refreshed evidence. Reviewer must check all eight
  files, unchanged permissions/fast-live behavior, and exact approval boundaries.

- [ ] **Step 7: Commit approved content and finish through existing gates.**

  Only after independent pass may the supervisor commit the exact reviewed file
  set, after checking for subsequent edits and unrelated staged content. Preserve
  the full-branch review, current-origin/main validation, guarded publication and
  merge-queue requirements. No empty approval commit is needed. Tell the user to
  restart OpenCode before relying on the new policy.
