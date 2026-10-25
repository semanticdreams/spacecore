# GLM-default project agents with bounded GPT consultation

## Direction

The user explicitly chooses aggressive cost optimization: GLM is the default;
agents delegate really difficult or critical questions to GPT experts. This
applies equally to supervisor, fast-dev, and live-dev workflows. Lack of model
evaluation is not a reason to retain GPT for a whole role.

All sixteen existing project agent definitions use exactly
`opencode-go/glm-5.3-flash`, with GPT-specific variants removed. Add one read-only
`expert-advisor` using exactly `openai/gpt-6.1-sol`, variant `high`. No initial
expert implementation worker, automatic model switching, or full GPT review tax.

## Alternatives and selected approach

1. Retain GPT for planners, reviewers, diagnosis and direct-development primaries:
   rejected by the user's subsequent direction; it preserves too much expense.
2. **Selected:** explicit GLM project-agent pins plus controller-mediated,
   evidence-triggered GPT consultation. Existing authority boundaries remain.
3. Global/default-provider edits or automatic routing infrastructure: unnecessary
   for this bounded rollout, with configuration inheritance and edit-authority
   dependencies that are not needed to change the project agents.

Project/root OpenCode JSON configuration and home configuration remain untouched.
Explicit pins cover project-defined roles only; inherited built-in, hidden and
global roles are unverified and outside this guarantee. Canonical dispatch uses
project `explorer` and worker roles, not built-in general/explore as an implicit
model fallback. Do not widen tool permissions to change configuration.

## Evidence and consultation triggers

The preceding static Fennel pilot demonstrated local review ability but exposed
problems with writable aliases to committed retained state, false resource
exclusion guarantees, and detaching content before fallible save/validation. Its
direct implementation also had syntax/type/test-oracle defects. It did not prove
hybrid success or establish that GLM fails every architecture or implementation
task. Preserve the pilot's observations and mark its conservative routing advice
as superseded by this user-directed policy.

Require a bounded consultation when an observable predicate holds:

- A new or changed design depends on retained mutable-state ownership or live
  resource alias exclusion, or fallible save/cleanup ordering across detach,
  destruction or publication, matching those demonstrated design blind spots.
- A specifically critical unresolved permissions/security boundary or
  irreversible-data question must be decided before acting.
- The same material failure remains after one focused repair, evidenced by the
  same reproduction, failed validation, violated invariant or fix verification.
- A material technical design conflict remains unresolved, with conflicting
  source evidence or contracts rather than stylistic disagreement.

Routine planning, review, diagnosis and implementation stay GLM. Expected TDD RED,
an initial typo/syntax error, speculative concerns, missing evidence that can be
collected, and ordinary architecture changes without a predicate do not trigger
GPT. Unknown product/API/data policy remains a human decision, not expert authority.

## Consultation contract

Task-capable controllers (supervisor and selected fast/live primaries) dispatch
`expert-advisor`. Workers retain `task: deny` and return a structured request:

`decision_scope`, `trigger`, `question`, `sources`, `invariant`, `evidence`,
`attempted_fix` (nullable), and `decision_needed`.

Supply one concrete question and inspectable original source/diff excerpts or
paths, not only a cheap-model conclusion. Keep the packet bounded to the relevant
decision; do not delegate the entire task or ask the expert to repeat exploration.

The expert returns `decision_scope`, `status` (`answered`,
`insufficient_evidence`, `requires_human`), `finding`, `evidence`, and `action`.
It may read/search/list/LSP within the repository, with existing sensitive-read
exclusions. It cannot edit, execute shell, delegate, browse external directories,
web-fetch, ask the user directly, publish, or grant approval/integration authority.

Allow one consultation per decision scope. Further consultation requires genuinely
new material evidence. Record scope, evidence, outcome and disposition in existing
handoff/progress artifacts; do not build a new tracking subsystem. Material expert
findings must be resolved and validated or escalated to the human. Advice does not
replace independent review, tests, capability refusals or permissions. An unavailable
expert or an unanswered necessary decision blocks dependent work; do not loop,
silently ignore it, or move the whole task to GPT.

## Three workflow integrations

**Supervisor:** coordinate GLM planner, implementer, reviewers, diagnostic advisor,
adjudicator and operational workers. Handle a worker's consultation branch before
normal completion/approval dispatch. Strict implementer to independent reviewer
to pass gates, checkpoint ownership and fix caps remain unchanged.

**Fast-dev and live-dev:** the GLM primary still edits, diagnoses, validates and
fixes directly. Narrow triggered consultation is compatible with their exemption
from routine planner/advisor/worker gates. Do not import supervisor machinery or
add a second mandatory full review. Preserve identity-specific branch prefixes,
local-only checkpoints, explicit wrap-up authorization, and live-dev manual-mode
establishment plus explicit validated refresh with no watcher/lifecycle prompts.

**Review/wrap-up:** ordinary reviewers and the observational fast/live wrap-up
reviewer use GLM. Expert advice is a scoped question, not an extra full-branch
approval. Reviewers without delegation return pending consultation to their caller.

Worker output contracts need an explicit non-approving request branch without
breaking ordinary outputs: JSON reviewer/adjudicator `status: needs_consultation`,
debug-advisor `verdict: needs_consultation`, implementer `NEEDS_CONTEXT`, planner
an explicit `NEEDS_CONTEXT` exception to finished-plan Markdown, and observational
review a pending-consultation report retaining base/head evidence. No request may
be mislabeled `pass`, `confirmed` or complete. Genuine `requires_human` stays human.

## Process and validation

Align active role/model tables, agent prompts, AGENTS, systematic-debugging,
subagent-driven-development, and fast-dev-wrap-up with this routing. The ordinary
independent diagnostic gate is now GLM, not a GPT call for every fix. Same-model
implementation retry rules remain; expert advice precedes another repair when a
trigger holds. Direct primaries retain their routine-gate exceptions. Keep existing
publication, merge-queue, permission and independent-review contracts intact.

Extend the existing permission/config checker and tests to enforce ordinary GLM
pins/no variants, the exact GPT expert model/variant/mode/read-only profile, and
unchanged capability/worker permissions. Use current supported config shapes;
do not redesign the parser or edit frozen pilot cases/evidence.

Before editing process skill guidance, run a bounded baseline routing-pressure
control with five fresh GLM contexts; after changes run the same five-context
variant. Use identical realistic relevant workflow context plus scenarios for all
three skills/workflows: routine first repair, demonstrated ownership transition,
same material failure after a repair, ordinary non-triggering architecture work,
direct fast/live ownership, denied worker delegation, and human-owned decisions.
Ask for routing decisions only; no actual dispatch, edits or privileged operations.
Record baseline failures and updated outcomes honestly. Ten GLM validation calls
maximum, no candidate implementation benchmark or retry-until-pass, 180-second
per-call and 35-minute overall cap. No extra GPT evaluation trials are needed.
If the control already complies on a scenario, do not claim guidance improved it.
These are prompt-compliance checks, not proof of architecture/model competence.

Focused new regressions, complete `make opencode-check`, existing Node workflow
contract tests where affected, stale-routing text searches, YAML/JSON parsing and
diff review are the local gates. No Space/Fennel/native build is required for this
agent/prompt/Python-checker change. PR CI remains the integration gate.

The canonical developer page is `docs/dev/features/opencode-agent-workflow.md`;
update it rather than adding a second routing-policy page. Publish no secrets or
private paths. Restart OpenCode after the complete reviewed configuration change;
the running session retains its loaded agent definitions and must not pretend its
workers have already changed model or that a new expert is dispatchable here.
