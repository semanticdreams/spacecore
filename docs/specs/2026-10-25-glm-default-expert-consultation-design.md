# GLM-default project agents with bounded GPT consultation

## Direction

The user explicitly chooses aggressive cost optimization: GLM is the default;
agents delegate really difficult or critical questions to GPT experts. This
applies equally to supervisor, fast-dev, and live-dev workflows. Lack of model
evaluation is not a reason to retain GPT for a whole role.

The user further requires **input from both models on every architecture or
software-design decision and every contract between systems**. This is mandatory
even if GLM is confident and no defect has occurred. GLM remains the ordinary
owner; GPT supplies a bounded critique before dependent implementation.

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

- Any architecture/software-design decision or new/changed contract between
  systems: responsibilities, abstraction boundaries, state/resource ownership,
  interfaces, data flow, failure/lifetime guarantees or persistence semantics.
  This includes meaningful local design decisions, not just cross-module work;
  the pilot's retained-state/aliasing/fallible-transition cases are examples, not
  the limit of the mandatory dual-model requirement.
- A specifically critical unresolved permissions/security boundary or
  irreversible-data question must be decided before acting.
- The same material failure remains after one focused repair, evidenced by the
  same reproduction, failed validation, violated invariant or fix verification.
- A material technical design conflict remains unresolved, with conflicting
  source evidence or contracts rather than stylistic disagreement.

Routine execution, review, diagnosis and implementation of an already reviewed
design stay GLM. Expected TDD RED, an initial typo/syntax repair, cosmetic wording
or naming, mechanical follow-through without a new design choice, and missing
evidence that can be collected do not require GPT. Calling work "internal", "UI"
or "small" does not exempt an actual design or contract decision. Unknown
product/API/data policy remains a human decision, not expert authority.

## Consultation contract

Task-capable controllers (supervisor and selected fast/live primaries) dispatch
`expert-advisor`. Workers retain `task: deny` and return a structured request:

`decision_scope`, `trigger`, `question`, `sources`, `invariant`, `evidence`,
`attempted_fix` (nullable), `glm_proposal` (nonempty for architecture/design/contract
decisions, otherwise nullable), and `decision_needed`.

Supply one concrete question and inspectable original source/diff excerpts or
paths, not only a cheap-model conclusion. Keep the packet bounded to the relevant
decision; do not delegate the entire task or ask the expert to repeat exploration.
For design consultation GLM first states the proposal, responsibilities/contracts,
invariants and rationale; GPT critiques them against original evidence. GLM records
the reconciliation before implementing anything that relies on the decision.

The expert returns `decision_scope`, `status` (`answered`,
`insufficient_evidence`, `requires_human`), `finding`, `evidence`, and `action`.
It may read/search/list/LSP within the repository, with existing sensitive-read
exclusions. It cannot edit, execute shell, delegate, browse external directories,
web-fetch, ask the user directly, publish, or grant approval/integration authority.

Allow one consultation per decision scope. Reuse the reconciled design for routine
follow-through: do not call GPT again merely because another task uses an unchanged
contract. A material change to design, contract or assumptions reopens the decision
and again requires both models. Further consultation otherwise requires genuinely
new material evidence. Record scope, proposal, evidence, critique and disposition in existing
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
direct fast/live ownership, denied worker delegation, human-owned decisions, and
mandatory dual input for a confident fresh design/contract decision. Use a compact
matrix of approximately 12–18 labelled decisions covering all three workflows,
not every case crossed with every workflow; keep rationales concise.
Ask for routing decisions only; no actual dispatch, edits or privileged operations.
Record baseline failures and updated outcomes honestly. Ten GLM validation calls
maximum, no candidate implementation benchmark or retry-until-pass, 180-second
per-call and 35-minute aggregate live-CLI cap. Persist and never reset consumed
run/export time across phases; offline implementation/review and human pauses are
not live-CLI time. No extra GPT evaluation trials are needed.
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

## Dual-model input on this workflow design

GLM consultation session `ses_e8b8a74dbffeK736igCe4FQulf` was verified from its own
public export as `opencode-go/glm-5.3-flash`. Its proposal supported GLM ownership,
bounded GPT critique before dependent implementation, a decision record with
reuse/material invalidation, and preservation of direct-primary authority. This
was one real design consultation, separate from the ten pressure-validation slots;
it did not run tools or change files. The current GPT supervisor independently
critiqued that proposal and reconciled it here:

- Accept the proposal/critique/reconciliation/reuse protocol and separation of
  advice from approval. Retain expert repository inspection permission, not the
  proposal's unnecessary ban on all read tools.
- Reject exempting all internal algorithms, local structures or UI details:
  meaningful design decisions in those areas still require both models.
- Reject informal optional GPT calls for routine tactical work; use explicit
  triggers and the recorded decision scope to avoid uncontrolled expense.
- Reject refresh around consultation alone. Live-dev establishes manual mode
  before editing and refreshes after validated code changes, not merely advice.
- Reject letting the cheaper owner dismiss an unresolved material finding by
  preference. Reconciliation needs evidence; unresolved material disagreement
  remains a human decision. Reconsultation requires new material evidence.

## User-authorized clarification validation tranche

After the original ten calls, strict guidance validation did not pass: three
answers used Markdown fences, one contained malformed JSON, and the sole valid
answer had route/owner mismatches. The diagnostic advisor supported a bounded
clarification but required human authorization for further calls. The user then
said "do it", authorizing the proposed separate five-call GLM tranche.

Preserve the original ten runs, manifests, questions, instructions, expected
answers, budgets and scores byte-for-byte. Do not normalize or rescore old replies.
The new protocol only explains existing route/owner meanings and gives a positive
raw-JSON output recipe. It does not change scenario text, oracle, schemas, production
agent policy, or mandatory GLM/GPT design consultation.

Use a separate fixed runtime root
`/tmp/space/opencode-expert-routing-clarified`, fresh sessions, and its own frozen
manifest and five-slot ledger. Reuse the existing safe capture/parser and matrix
primitives; no generic experiment framework. Limit the new tranche to exactly
five attempts, each run plus own-session export at most 180 seconds, at most 900
seconds aggregate live execution. Failed/incomplete attempts consume slots. No
retries, continuation tricks, extra smoke calls, or additional model providers.

Clarify existing meanings before freezing the packet:

- `expert_advisor`: a task-capable primary dispatches the bounded expert itself.
- `request_consultation`: a task-denied worker returns a non-approving structured
  request to its controller; it does not dispatch the expert.
- `human`: genuinely unknown product/policy needs a human decision; this does not
  make the human the eventual code implementation owner in these workflow cases.
- `blocked`: the specifically proposed unsafe/bypass/publication action cannot
  proceed. Do not label that action `glm` merely because other valid work remains.
- `glm`: the specifically requested ordinary, authorized next work stays GLM.
- `implementation_owner`: eventual code/fix owner, including while a decision is
  blocked: supervisor uses implementer; direct fast/live primaries remain owners.

The first non-whitespace output character is `{` and the last is `}`; emit exactly
one JSON object with the prescribed decisions array, no Markdown wrapper or
surrounding prose. Keep strings correctly escaped and rationales concise. Strict
parsing remains unchanged: fenced or malformed JSON still fails.

Predeclared acceptance: all five actual identities are verified GLM, all five
outputs pass the original strict schema and complete 18-case coverage, all 90
route/owner pairs match the unchanged oracle, and manual review finds preserved
dual-model design-before-implementation, proposal/critique/reconciliation/reuse,
worker/controller authority, human policy, direct-primary ownership, and live
manual-before-edit/refresh-after-validation behavior. This is new-protocol
conformance evidence, not a causal improvement claim over the old protocol or
proof of general architectural ability. If it fails, preserve the failures and
do not claim completion or publish under an invented pass.

## User-approved fail-closed delivery contract

The five-call clarification tranche remained 4/5 strict accepted outputs. The
user subsequently approved the proposed alternative: reject malformed or
inconsistent handoffs, allow one bounded original-GLM-author format correction,
and never advance without a valid handoff. This prospectively replaces perfect
first-response delivery as the rollout criterion; none of the original ten or
five outcomes is changed, repaired in place, rescored or relabeled successful.

### Dual-model proposal and reconciliation

Actual GLM proposal session `ses_e891f3f7affeoubxIC9Y778d2c` was verified from its
own public export as `opencode-go/glm-5.3-flash`, completed with no tools. It
proposed controller-owned delivery states, one original-author content-frozen
correction separate from code-fix/consultation budgets, immutable failed reports,
and corrected delivery being eligible for ordinary semantic review, not approved.
The current GPT supervisor inspected the existing role and skill contracts and
critiqued/reconciled that proposal before implementation:

- Apply it to all task-capable controllers, including fast-dev/live-dev receiving
  observational reviews, not only supervisor. Direct primary replies to the human
  do not acquire a new universal JSON format or supervisor worker pipeline.
- Use each role's declared format: JSON where required, Markdown plans/reviews
  where intended. The experimental `route` field is not a production-wide field.
- Keep one stable identity per original handoff, not a budget key containing a
  mutable attempt number. Include task, author role, selected controller/workflow,
  branch, recorded base/head or equivalent source snapshot, and review mode.
  A changed label, redispatch, duplicate or stale reply cannot reset allowance.
- Reject scope/authorship/staleness mismatches rather than permitting SHA or
  identity edits to disguise unreviewed work. Only unambiguous delivery metadata
  copied from the original assignment, such as the demonstrated workflow label,
  may be corrected without new work.
- Keep capability wrapper JSON/refusals and GPT expert answers outside this GLM
  repair path. GLM must not synthesize wrapper facts, rerun privileged operations,
  rewrite expert evidence or turn unavailable advice into approval.
- A corrected valid delivery enters the original ordinary handler/reviewer. It
  needs no extra full-review layer and grants no pass, permission or publication.
  Do not invent unspecified daily rate caps or a new tracking subsystem.

### Delivery states and authority

The receiving controller checks format, required fields, assignment identity,
source/review range, and consistency before using a report as any verdict.
Preserve original payloads and record delivery state/correction usage in existing
handoff/progress artifacts.

1. Valid initial delivery enters normal semantic handling. Quality, findings,
   consultation needs and approval remain governed by the original contract.
2. An eligible malformed delivery stops dependent actions. The controller may
   resume the same GLM author once with the original contract/evidence and precise
   delivery errors. Mark the one correction as consumed before dispatch.
3. This assignment is **format-only, no code edits, tests, builds, commits,
   operations, changed findings/verdicts/evidence or source/review range**. It may
   reissue existing facts and correct permitted assignment metadata; it cannot
   invent missing facts. If reconstruction is unsupported, use the role's existing
   context/evidence-needed or non-approving branch (NEEDS_CONTEXT where supported),
   not a new universal status or response field.
   Caller-side fence stripping, aliases, default pass or salvaged partial verdicts
   are forbidden.
4. Validate the correction against the unchanged role contract and retained facts.
   A valid corrected delivery is only eligible for ordinary semantic handling;
   otherwise block dependent work. No second delivery repair or budget reset.
5. Stale/untrusted evidence, changed substantive content or an unavailable original
   author stays blocked/context-needed, not papered over with a new worker. Existing
   technical consultation/human escalation may apply but cannot create a verdict.

Delivery correction neither consumes nor resets substantive code-fix rounds or
expert consultation counts. It cannot defer mandatory dual-model design input
past dependent implementation. Fast/live keep direct fixes and one observational
review; live manual mode and refresh are for code edits, not report-only repair.

### Bounded validation and prospective acceptance

Implement workflow guidance and narrow validation helpers, not an OpenCode runtime
plugin or universal report-schema engine. State explicitly that source guidance
and replay tests do not prove hard runtime enforcement for all future sessions.

Use five short fresh GLM pressure controls before guidance changes and the same
five fresh contexts afterward, covering initial invalid delivery, one used repair,
changed/stale evidence, valid-but-substantive findings, and excluded expert/wrapper
authority across all three workflows. Responses are routing explanations assessed
manually, not another serialized-production-handoff perfection benchmark. Preserve
baseline compliance and limitations; do not claim causality from a small sample.
Each call is at most 120 seconds, ten pressure calls maximum, no resampling.

Add deterministic fixtures that prove reject-before-use, exactly one author repair,
valid correction returning only to normal handling, and a failed/changed/stale
correction blocking with no additional action or model call. Replay the retained
real bad report through one explicitly authorized GLM correction, with at most one
generation and a 180-second combined run/export budget. A new correction record
must preserve the rejected original. Any original own-session continuation must
retain old snapshots and select only the new verified assistant message, never
concatenate the old invalid answer or claim a fresh comparison sample.

Required acceptance is correct fail-closed state handling, unchanged schema and
authority boundaries, complete deterministic/source checks, manually acceptable
post-guidance decisions, and an honest bounded correction trace. A valid repair
may enter normal review; an invalid repair must block. The model is not required
to succeed on every first response or every correction, and no blocked trace may
be presented as an approved task. Preserve and report actual repair success or
failure separately. No extra model calls or retries beyond these limits.
