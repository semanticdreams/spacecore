# Model-neutral project agent routing

## Intent and scope

Configure all 17 project-specific agents with the user's requested model and
appropriate reasoning effort, then remove instructions and checks that make
future model changes require a policy rewrite. This covers project agent
frontmatter, AGENTS.md, active workflow skills, checker/tests and the canonical
`docs/dev/features/opencode-agent-workflow.md` page. It does not modify global
OpenCode configuration, runtime application code or permissions.

The model selection is an implementation input, not an instruction contract:
every role's `model:` line is set to the exact model requested in the user task.
Do not duplicate that ID in instruction bodies, role tables, active prose or
checker policy. Both `model:` and `variant:` frontmatter lines are authoritative
and may later be edited independently without checker/policy/test pin changes.

## Initial effort allocation

These are controller-selected defaults implementing the user's preference, not
a permanent tier map enforced by code:

| Effort | Roles |
| --- | --- |
| high | supervisor, fast-dev, live-dev, planner, reviewer, fast-dev-reviewer, debug-advisor, adjudicator, expert-advisor |
| medium | implementer, explorer, web-researcher, config-auditor, git-integrator, github-operator, pr-recovery-operator, windows-ci-reproducer |

Keep agent modes, step budgets and complete permission blocks unchanged.
Inherited built-in/internal roles are outside this project's pin contract.

## Configuration authority and validation

Each project agent must have explicit, well-formed scalar `model` and `variant`
values. Validate a provider/model identifier and a nonempty single variant token,
rejecting missing, blank, whitespace-only and malformed/non-scalar values. Do not
maintain a provider/model allowlist, role-tier table or equality relationship
between roles. A syntax check does not prove runtime provider availability or
variant support. Maintain an explicit required inventory of all 17 existing
project roles separately from configurable pins.

Separate expert safety validation from routing validation. Retain its exact
read-only/default-deny permission surface and subagent mode, along with every
other role's existing capability boundaries, modes and budgets. Regression tests
must accept alternate per-role model identifiers and variant tokens without
changing policy code and reject malformed/missing config and missing roles.

## Role-based consultation

Replace mandatory dual-model input on every architecture/design/contract decision
with role-based targeted consultation. Ordinary design decisions still need an
evidence-backed rationale, but do not require expert dispatch or fictitious
reconciliation. Independent review is a separate assessment of untrusted changes,
not a guarantee supplied by using different model families.

Mandatory expert triggers are:

1. The same material failure after one focused repair, evidenced by reproduction,
   validation or a violated invariant, before another dependent repair.
2. An evidenced unresolved material technical conflict; an ordinary reviewer
   finding or normal design choice is not automatically such a conflict.
3. A critical unresolved security, permissions or irreversible-data technical
   boundary before acting across it.

Controllers may request one bounded consultation for consequential technical
uncertainty. Do not turn optional consultation into a universal prerequisite.
Unknown product/API/data policy remains human-owned. Necessary unresolved advice
blocks dependent work. Reuse unchanged advice; materially changed assumptions
require reassessing its applicability, with a new consultation only when a
current trigger or consequential uncertainty warrants it. Do not claim equal
defect-detection performance relative to historical cross-model experiments.

Rename the canonical request field `glm_proposal` to `proposal` atomically across
active examples, workers, controllers and tests; no compatibility alias. Keep
all other request fields and pending status/output formats. A proposal is
required for design/contract questions, nullable for other triggers.

Delivery validation precedes report handling. Pending worker requests route to
the controller, then expert critique and evidenced reconciliation, then return
to the original worker for its own assessment. Expert advice never approves,
edits, delegates, publishes or overrides a capability refusal. Report-repair
eligibility and exclusions are based on role/output contract, not model family.
Preserve immutable delivery payloads, correction ancestry and recovery budgets.

## Preserved safeguards and historical boundary

Keep strict implementer -> independent reviewer -> pass, diagnostic-advisor
confirmation, fix caps/adjudication, checkpoint ownership, clean-tree and
integration/merge-queue gates. Fast-dev/live-dev retain direct ownership and
their one observational whole-branch wrap-up review. Do not broaden their
permissions or alter live manual/refresh behavior.

Preserve historical specs/plans/progress, captured handoffs, experiment results,
and the existing model-pilot/expert-routing/handoff-delivery evaluation protocols
and tests byte-for-byte. Their pins and old request schema describe their frozen
protocol, not the active configuration. Add a current supersession note and
update active anchors in the canonical docs; do not rescore or rewrite history.
New tests must explicitly validate the new contract rather than claim old eval
oracles prove it. Restart OpenCode to activate the new instruction snapshot and
schema; do not retrofit retained old handoffs into the new schema or claim this
running session has switched models.

## Consultation and evidenced reconciliation

Original source snapshot: branch `juicyrebel/devilray`, commit
`e34e4c0542d1f41fae4e5676ff574e6ddd5f3af0`, initially clean. Explorer sessions
`ses_e78809430ffenqIcl1k5JN4uAk` and `ses_e78798fa4ffevVIUAILTeYtPTI` delivered
eligible read-only Markdown audits; git identity was supplied/verified by the
controller, not inferred from those reports. No delivery correction was needed.

Planner session `ses_e787e8056ffezbZnzWprOC4KcA` proposed per-role config authority,
targeted consultation and neutral schema, initially with a checker tier map.
Expert session `ses_e787c0de7ffezbZnzWprOC4KcA` returned answered JSON inspecting
AGENTS.md, checker/tests, role definitions,
the three affected skills, frozen evaluation scripts and canonical docs.

Accepted critique: remove the duplicate tier map; split safety from routing
validation; require the complete role inventory; make triggers explicitly
evidence-based; preserve pending-worker resumption and role-based delivery
exclusions; migrate only active schema and label historical protocols. The
planner returned a reconciled proposal in the same session, accepting these
points. All report formats/assignment identity/source references were eligible;
`correction_used=0` for each ordinary author. Mechanical active-link changes
and supersession notes need no human product/data-policy decision.

The expert role's permission/mode/steps profile is preserved, but its prompt and
description must change to the neutral contract; the reconciliation's shorthand
"profile unchanged" does not freeze obsolete prompt text. No new design or
permission authority is introduced by that clarification.

## Validation and acceptance

Use test-first checker and contract regressions, focused text/diff checks, and
`make opencode-check`. Include routing pressure cases for routine design without
automatic advice, repeated failure requiring advice, and retained strict versus
fast/live review obligations. Observe baseline behavior before skill edits,
then evaluate changed source instructions explicitly: currently loaded roles
remain on their old snapshot until restart. Historical harnesses are not the new
behavior oracle. No Space engine build or Fennel validation is relevant.

Implementation must receive an independent full-range review. Before integration,
verify current origin/main, a clean committed worktree and required validation;
use guarded capability workers for publication and poll until merged. Stop for
real credentials/permissions/product-policy boundaries, not routine docs choices.
