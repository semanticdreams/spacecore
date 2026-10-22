---
name: daily-devlog-automation
description: Use when a scheduled Orca/OpenCode run or user prompt asks to run daily devlog automation, create a daily devlog entry, inspect recent repo changes for a devlog, or publish a devlog automation branch
---

# Daily Devlog Automation

## Overview

This skill turns a scheduled Orca/OpenCode run into a reviewed, brief devlog PR. The durable workflow lives in the repo; the Orca UI prompt is only a trigger.

## Preconditions

1. Verify a clean dedicated checkout with `git status --porcelain`; stop if dirty.
2. Verify the checkout is on a branch that can safely create `automation/daily-devlog/YYYY-MM-DD` from `origin/main`.
3. Dispatch `github-operator` to verify GitHub authentication before relying on PR creation or auto-merge.
4. Dispatch `github-operator` to verify branch protection rules and required status checks are active on the target repository before attempting auto-merge; do not assume they are available just because authentication succeeds. Required status checks (for this repo: `test`), pull-request protection, and merge queue requirement must be present in wrapper evidence before auto-merge. If merge queue is not enabled or cannot be verified, report `HUMAN_DECISION_REQUIRED` — the automation relies on merge queue for post-PR freshness. If protection cannot be confirmed, fail closed.

## Capability Boundaries

Safe base update and push steps dispatch `git-integrator`. PR creation,
protection checks, auto-merge enablement, and merge-queue polling dispatch
`github-operator`. OpenCode config verification, when needed, dispatches
`config-auditor`. If a capability wrapper returns `human_decision_required`, the
supervisor reports `HUMAN_DECISION_REQUIRED` with wrapper evidence and does not
ask for a one-off broad command permission.

## Workflow

**Review-first handoff:** Every implementation and fix dispatch in this
automation must explicitly say: **stage only assigned changes; return them
uncommitted; do not commit, amend, push, or integrate**. This overrides ordinary
implementer checkpoints, including validation repairs, conflict resolutions, and
merge-queue fixes. Review the complete assigned staged diff, including new files,
with `git diff --staged -- <assigned paths>` and a complete assigned file list.
Confirm no assigned unstaged or untracked content was omitted; a commit-only
BASE..HEAD package cannot represent this handoff. After fixes, refresh the whole
assigned staged diff and dispatch reviewer again. Each handoff includes successful
local validation; any validation-generated edits must be staged and reviewed too.
Only after pass may the supervisor commit the exact approved, locally validated
content, checking for subsequent edits and
preserving unrelated worktree/index entries; if isolation is unsafe, return
NEEDS_CONTEXT rather than absorbing or unstaging unrelated work.

1. Fetch `origin/main` through `git-integrator`.
2. Create or switch to `automation/daily-devlog/YYYY-MM-DD` from `origin/main`.
3. Inspect the latest relevant journal entry or recent day boundary, docs notes, plans/specs, and `origin/main` mainline/first-parent history to identify work that landed since that boundary.
4. Apply the meaningful-change filter.
5. If no entry is warranted, stop without edits, commits, pushes, or PRs.
6. If an entry is warranted, dispatch `implementer` to write/update the journal entry, regenerate indexes, and run local validation, explicitly using the stage-only/no-commit handoff above.
7. Dispatch `reviewer` over the complete assigned staged content before commit and before push. Every fix dispatch repeats stage-only/no-commit and is followed by refreshed staged review.
8. The supervisor commits only the exact independently approved, locally validated staged devlog automation content and verifies a clean tree before any safe merge. Preserve unrelated state; do not bypass the wrapper's clean-tree guard.
9. Dispatch `git-integrator` to fetch `origin` and confirm the automation branch has accounted for current `origin/main`. If behind, use the safe-merge wrapper when permitted. Route conflicts or regenerated docs repairs through the stage-only/no-commit handoff above: implementer locally validates, reviewer inspects the refreshed complete assigned staged diff, then supervisor commits only approved content and verifies a clean tree. Do not rebase or force-push unless the human explicitly requests it.
10. Run final validation from the clean, current-base tree. If validation produces file changes, route them through the same locally validated staged-review/commit handoff, then restart at step 9; prior review does not cover generated edits. Handle failures through Validation Failure Recovery below.
11. Re-fetch `origin` and recheck current `origin/main` through `git-integrator` before push or PR creation. If behind, repeat step 9's safe-merge and repair handoff, then rerun final validation from a clean tree before rechecking. Do not rebase or force-push unless the human explicitly requests it.
12. Push only the dated automation branch through `git-integrator`.
13. Open a PR, enable auto-merge (or queue the PR), and poll merge queue through `github-operator` when branch protection
    allows it. After the PR enters merge queue, poll with
    wrapper evidence until `mergedAt` is present (PR merged). Do not run direct
    broad `gh pr`, `gh run list`, or `gh run watch` commands. Do not update
    the PR branch solely because origin/main advanced after PR creation —
    merge queue handles post-PR freshness. Resume only for actionable
    queue blockers: merge queue conflicts, merge-group `test` failures,
    missing merge queue protection, permission blockers, closed-unmerged
    PRs, and queue timeouts. For queue
    failures, invoke `systematic-debugging`, route any repository fix
    through `implementer` → `reviewer` → pass, commit reviewed fixes,
    validate from current `origin/main`, push, and requeue. Do not rebase
    or force-push unless the human
    explicitly requests it.

## Landing-Date Attribution

Treat `origin/main` as the source of truth for recent work. Attribute work to the daily entry for the date it lands or merges into `origin/main`, regardless of the original author date or feature-branch commit date. Older feature-branch commits merged today are eligible for today's entry; author or original commit dates must not cause landed work to be skipped or backdated into an already-published journal entry.

Use mainline/first-parent history, merge commits, PR merges, or equivalent landed ranges on `origin/main` to decide what changed since the latest relevant journal entry or recent day boundary. Do not guess from local branch history when the `origin/main` landing evidence is unavailable.

## Meaningful Change Filter

Create an entry only for meaningful user-facing, architectural, workflow, tooling, or milestone-relevant progress. Skip routine churn, pure fix-loop commits, formatting-only changes, dependency noise, and changes already covered by a prior entry unless they complete or clarify a broader story.

## Journal Entry Contract

Use exactly this entry shape:

```md
---
type: journal
tags: [journal, devlog]
created: YYYY-MM-DD
---

# YYYY-MM-DD

One short narrative paragraph.
```

The paragraph connects concrete work to current project goals, milestones, or recent momentum. Inline Markdown links are allowed when they point to relevant docs, notes, plans, specs, or feature pages and improve reader context. Before writing or committing, perform a compression/style pass that makes the final paragraph denser than the full report while preserving the main landed changes, why they matter, and useful inline references. Forbid section headings, bullet lists, separate link lists, commit hashes, author lists, raw file lists, and commit-summary prose.

## Validation

Before running the docs build, ensure locked docs dependencies are installed:

```bash
cd docs
if [ ! -d node_modules ] || [ ! -x node_modules/.bin/vitepress ]; then npm ci; fi
```

Then run the full validation:

```bash
cd docs && npm run devlog:indices && npm run docs:build
```

Inspect the final diff and require only expected journal/devlog/docs automation files.

## Validation Failure Recovery

If required validation fails, do not commit, push, create a PR, enable
auto-merge, or report the automation branch as ready. Capture the failing
command, failing tests or docs build phase, relevant output, current branch
state, and `git status --porcelain`. Invoke `systematic-debugging` and continue
investigating even when the failure appears unrelated, flaky,
timing-dependent, or environmental.

Any repository fix, generated-doc repair, or conflict resolution must go
through `implementer` → `reviewer` → pass before commit. After reviewed fixes
are committed and the tree is clean, re-fetch `origin`, recheck current
`origin/main`, rerun validation, and continue only when validation is green.
Report BLOCKED or HUMAN_DECISION_REQUIRED only when systematic debugging
establishes that progress requires credentials, inaccessible infrastructure,
unsafe git history decisions, unreproducible behavior after reasonable evidence
gathering, or a product/API/data/architecture choice.

## Commit, Push, and PR

Commit after review. Push only through `git-integrator`. Create the PR, verify branch protection, enable auto-merge, and poll for merge only through `github-operator`. If repository rules require a rebase-only merge method, do not enable auto-merge automatically. Report HUMAN_DECISION_REQUIRED because the agent must not rebase unless the human explicitly requests it. Never push directly to `origin/main`. Later `origin/main` movement is handled by merge queue. Resume only for actionable queue blockers: merge queue conflicts, merge-group `test` failures, missing merge queue protection, permission blockers, closed-unmerged PRs, and queue timeouts. Invoke `systematic-debugging` for any queue failure and route repository fixes through `implementer` → `reviewer` → pass, commit reviewed fixes, validate from current `origin/main`, push through `git-integrator`, and requeue through `github-operator`.

## Fail-Closed Cases

Stop with a clear BLOCKED or HUMAN_DECISION_REQUIRED summary when the checkout
is dirty, credentials are missing, `gh` is unavailable,
`origin/main` cannot be fetched or inspected, mainline/merge evidence is
ambiguous, branch protection, required status checks, or merge queue
requirement are unavailable or cannot be verified (via classic protection
or rulesets/effective branch rules), auto-merge cannot proceed safely,
merge queue handoff fails with an unresolved blocker, the diff includes
unexpected files, or validation remains red after systematic debugging
establishes a true human-input blocker.

## Red Flags

- "I'll just push main because this is docs-only."
- "The entry can be a commit summary this time."
- "A quiet day still needs an entry."
- "The reviewer is unnecessary for one paragraph."
- "The UI prompt already says enough."
