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
2. Dispatch `git-integrator` to run `create-daily-devlog-branch`. Consume its `utc_date` and `target_branch` evidence for the UTC run branch `automation/daily-devlog/YYYY-MM-DD`, not the journal dates.
3. Perform Catch-up Discovery and Decision below against the fetched main snapshot.
4. Apply the meaningful-change filter to every candidate in that window, comparing actual narratives rather than source presence.
5. A no-op must satisfy the whole-window accounting in Catch-up Discovery and Decision; only then stop without edits, commits, pushes, or PRs.
6. For each warranted missing landing date, dispatch `implementer` to create the journal entry, regenerate indexes, and run local validation, explicitly using the stage-only/no-commit handoff above. Preserve pre-existing dated sources; unresolved work on an existing source follows the decision table below.
7. Dispatch `reviewer` over the complete assigned staged content before commit and before push. Every fix dispatch repeats stage-only/no-commit and is followed by refreshed staged review.
8. The supervisor commits only the exact independently approved, locally validated staged devlog automation content and verifies a clean tree before any safe merge. Preserve unrelated state; do not bypass the wrapper's clean-tree guard.
9. Dispatch `git-integrator` to fetch `origin` and confirm the automation branch has accounted for current `origin/main`. If behind, use the safe-merge wrapper when permitted. Route conflicts or regenerated docs repairs through the stage-only/no-commit handoff above: implementer locally validates, reviewer inspects the refreshed complete assigned staged diff, then supervisor commits only approved content and verifies a clean tree. Do not rebase or force-push unless the human explicitly requests it.
10. Run final validation from the clean, current-base tree. If validation produces file changes, route them through the same locally validated staged-review/commit handoff, then restart at step 9; prior review does not cover generated edits. Handle failures through Validation Failure Recovery below.
11. Re-fetch `origin` and recheck current `origin/main` through `git-integrator` before push or PR creation. If the fetched tip differs from the assessed snapshot, pin the new tip and repeat Catch-up Discovery and Decision, reconciling pending entries with newly published sources. Route newly warranted entries or repairs through stage-only implementation and refreshed review before commit. If behind, repeat step 9's safe-merge and repair handoff. Rerun final validation from a clean tree after changes, then recheck freshness. Do not rebase or force-push unless the human explicitly requests it.
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

## Catch-up Discovery and Decision

Pin the fetched `origin/main` tip from the wrapper's `origin_main_sha` evidence.
Read the latest dated journal source at that snapshot, including its actual narrative.
Inspect every first-parent landing day from the start of that source's UTC date
(00:00:00Z), inclusively, through the pinned tip. Inspect landed deltas and their
references (docs notes, plans/specs, PR merges), not only commit subjects. Starting
inclusively catches meaningful work that landed later on the latest journal's date.
Do not substitute today, yesterday, a fixed lookback, or the journal publication
commit for this boundary. If there is no reliable initial boundary or mainline
evidence, report BLOCKED or HUMAN_DECISION_REQUIRED with the missing evidence or
decision rather than guessing.

Classify each candidate as already covered, not meaningful, or meaningful uncovered
by comparing landed changes with actual journal narratives. Source presence and
generated indexes are not semantic coverage evidence; document filenames and author
dates are not landing evidence. Meaningfulness and coverage require agent judgment,
not automatic title classification. Ordinary daily scope includes recovery for
every warranted missing date in the window, without asking permission or a separate
request merely because the landing date predates the run.

| Evidence | Action |
| --- | --- |
| Missing dated source + meaningful uncovered work | Create one brief entry for that landing date. |
| Already covered or not meaningful | Skip with a concise reason; do not create filler. |
| Meaningful uncovered work on an existing published source | Preserve the source and request a human publication-treatment decision; do not rewrite it or misdate the work. |
| Uncertain evidence or boundary | Investigate; fail closed with the unresolved question if uncertainty remains, not guess or no-op. |

Preserve all pre-existing dated journal sources byte-for-byte. An existing source
with unresolved meaningful work is not a successful no-op. No-op requires a fully
examined interval and no unresolved meaningful work. Report the pinned tip,
inclusive boundary, and concise covered/skipped reasons for the whole window,
including any created dates or unresolved publication decisions. Keep this evidence
in normal review handoffs; introduce no persistent ledger or state schema.

## Landing-Date Attribution

Treat `origin/main` as the source of truth for recent work. Attribute work to the daily entry for the date it lands or merges into `origin/main`, regardless of the original author date or feature-branch commit date. Older feature-branch commits merged today are eligible for today's entry; author or original commit dates must not cause landed work to be skipped or backdated into an already-published journal entry.

Use mainline/first-parent history, merge commits, PR merges, or equivalent landed ranges on the pinned `origin/main` snapshot for Catch-up Discovery and Decision. Convert landing timestamps with offsets to UTC before choosing a date. Do not guess from local branch history when the `origin/main` landing evidence is unavailable.

The UTC run date and branch name are independent of journal source filenames,
frontmatter, and headings. Create one brief narrative entry per warranted missing
landing date, potentially several in one run. For example, an October 23 run with
meaningful uncovered October 22 landings creates an October 22 entry on the
October 23 automation branch, even if nothing landed on October 23. It does not
require a separate backfill request or an October 23 filler entry.

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
