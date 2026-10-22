# Strict-flow checkpoint and review ownership

## Decision and scope

Allow assigned standard implementers to create task-scoped local checkpoint
commits before independent review. Keep independent approval mandatory before
completion, publication, or integration. The user authorized resolving the
audited contradiction using the recommended checkpoint-first approach.

This is a repository-local instruction correction, not a Git permission change.
Do not change runtime tooling, home configuration, capability wrappers, or the
selected fast-dev/live-dev lifecycle.

## Problem and alternatives

The implementer prompt requires committing before reporting, and SDD packages
committed BASE..HEAD ranges. The supervisor instead prohibits commits before
review, explicitly including tiny tasks. A baseline instruction exercise found
the same conflict in initial tasks and fix rounds, and found specialized
automation that intentionally requires review before committing.

Universal review-before-commit would require pending-change and fix-snapshot
packaging. Universal checkpoint-first would override intentional staged-review
workflows. Actor-scoped checkpoint ownership with explicit review-first handoffs
fits existing tools and preserves both meaningful safety boundaries.

## Contract

1. Ordinary tasks: record BASE; implementer implements, validates, self-reviews,
   checkpoints only assigned changes, and reports SHAs; supervisor packages the
   complete BASE..HEAD range and dispatches independent review.
2. Fixes: record FIX_BASE before dispatch; implementer validates and checkpoints
   accepted fixes; reviewer verifies the fix range. Prior approval does not
   cover new changes. Tiny tasks retain the same independent approval gate.
3. Checkpoints, a clean tree, self-review, and DONE are not approval. No completion
   or publication follows until independent review and applicable finishing
   gates pass. The supervisor ensures reviewed work is committed; no extra or
   empty post-review commit is necessary.
4. Checkpoint authority belongs to assigned implementers. Supervisors may commit
   only their existing coordination allowlist or exact independently approved
   changes. Implementers gain no push, PR, integration, or history-rewrite power.
5. Preserve unrelated work and index state. If task ownership cannot be isolated
   safely, return NEEDS_CONTEXT rather than absorbing or discarding changes.
6. Explicit stage-only/no-commit assignments override the ordinary checkpoint
   handoff. Preserve daily/weekly automation review-first behavior and the final
   staged landing review in workflow debugging. Repeat the no-commit instruction
   on fix dispatches. Review task-scoped staged content, including new files,
   and updated staged fixes; do not use commit-only packaging for that handoff.

## Owning files

Align AGENTS.md, supervisor and implementer prompts, SDD, daily/weekly automation,
workflow-debug's final staged handoff, and the canonical agent workflow guide.
Inspect finishing/debugging callers for compatible actor-scoped wording; change
them only if a live contradiction remains. Do not rewrite historical plans or
add a new policy framework.

## Validation and rollout

Before edits, record fresh-context interpretations of ordinary, tiny, fix-round,
premature publication, specialized staged-review, and unrelated-index scenarios.
After edits, repeat scenario exercises and independently inspect decisions.
Distinguish simulated instruction compliance from actual Git execution.

Run focused timing-rule searches, diff whitespace checks, the existing OpenCode
permission checker, relevant policy-doc tests, and make opencode-check. No Space
runtime build is warranted for instruction-only changes. Independent review must
check complete file coverage, unchanged permission mappings, preserved fast/live
exceptions, and complete-range review after checkpoints.

The running session retains its existing stricter commit discipline: policy edits
remain uncommitted until independent approval. After reviewed changes are
committed, evaluate current origin/main, rerun required validation, and use the
guarded publication and merge-queue flow. Restart OpenCode before relying on
updated agent or skill instructions; do not claim this session hot-reloaded them.
