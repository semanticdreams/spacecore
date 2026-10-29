# Autonomous operational handoff recovery

## Intent and acceptance

Internal agent delivery failures are controller-owned operational problems. A
malformed response, exhausted format correction, unavailable author, truncated
plan or missing repository context must not by itself produce a question asking
the human to authorize replanning, investigation, delegation or review.

Reject the unusable delivery, not the overall task. Recover autonomously within
existing permissions and substantive safeguards. Do not promise that all tasks
can complete: report actual resource/infrastructure blockers honestly and ask
only for genuinely human-owned decisions.

Acceptance requires explicit same-range recovery, independent new source work,
immutable failure ancestry, preserved findings and budgets, strategy changes on
repeated failure, source-contract regression tests and read-only routing probes.

## Evidence and existing owners

Initial branch: `juicyrebel/grampus-2`; BASE:
`4f607d36cfcb5031b669e847d8c7cf1be8d0d311`, clean at investigation.

The controller inspected sanitized OpenCode database excerpts for the `scoter`
requirements-engineering task and its committed progress record at
`be3619120289eb6036e3384f0112db89545bcb21`. A planner returned trailing tool-call
delimiters, then changed substantive content during its single format-only
correction. The supervisor correctly rejected the correction but asked the user
to authorize fresh planning. The user clarified that operational recovery is
entirely the agent's responsibility. Raw session payloads remain private.

`AGENTS.md#fail-closed-handoff-delivery` currently blocks invalid delivery without
an explicit autonomous task-continuation contract. The supervisor, fast-dev and
live-dev gates and three process skill preflights repeat that stopping point.
The existing delivery evaluator is a frozen experiment, not a runtime gate.

## Alternatives and reconciled decision

1. A single reassurance sentence is too ambiguous: it leaves same-range recovery,
   reviewer shopping and exhaustion unaddressed.
2. **Extend the canonical controller contract and wire existing owners.** This is
   selected: no new orchestrator, worker status or production state machine.
3. A new recovery agent/runtime adds unnecessary authority and tracking surfaces.

GLM planner session `ses_e792e27dbffeF2EIA7L1I50eQ7` proposed option 2, initially
with a two-replacement task ceiling. Expert session
`ses_e792b4637ffebsCN4vCZ6TZRei` inspected original AGENTS, controller, reviewer,
adjudicator, skill, evaluator and test sources. Its critique required explicit
unchanged-range replacement, anti-review-shopping, strategy rather than task
termination at retry limits, evidence-based blockers and adversarial tests.

Those five corrections are accepted. The GLM planner supplied a corrected
reconciliation after unsupported terminology, an incorrect incident hash and
counter-reset language in its first reconciliation were rejected. The final
reconciliation preserves task-wide counts, verified local snapshots and technical
decisions under dual-model consultation, without claiming activation before
reviewed rollout and restart. This is design reconciliation, not task approval.

## Recovery contract

### Preserve delivery integrity

Run the existing delivery preflight before semantic handling. An eligible
malformed report still receives at most one same-original-author format-only
correction, marked consumed before dispatch. No normalization, partial verdict
salvage, invented facts, second correction or renamed allowance is authorized.
Eligible delivery is ordinary handling, never approval.

An exhausted, changed-fact, stale or unavailable-author delivery remains unusable.
Preserve original/corrected payloads separately and its immutable identity and
spent correction counter. Quarantine this delivery, then recover the task.

### Explicit controller-owned replacement

The receiving controller autonomously authorizes actual replacement work to
complete a missing/unusable assessment, including on the **same verified branch
and base/head range**. No artificial commit or range change is required. A new
label or repeated prompt alone is not replacement work.

Before dispatch, record in existing handoff/progress artifacts:

- predecessor identity and immutable failure ancestry;
- original task, requirements and global constraints;
- actual current local branch/snapshot and complete assigned range;
- observed failure, diagnosis/hypothesis and concrete changed strategy;
- trusted source/diff references and required independent investigation;
- established unresolved findings, pending consultations/adjudications;
- untrusted concerns from invalid reports, separately labelled for verification;
- continuing task-level failure counts and fix/consultation/resource accounting.

Gather missing repository evidence directly or through the existing explorer.
Resume with a narrower brief or commission fresh substantive work, possibly with
a new author. Never impersonate the unavailable author or reconstruct their
unretained facts. The new worker inspects actual original sources and produces
its own assessment, which must pass delivery and normal semantic gates. Recheck
source/range before consumption. Local staleness requires real reassignment, not
paper SHAs; no origin fetch/merge is required on every handoff. Existing final
integration freshness gates remain unchanged.

### Preserve substantive obligations

A usable adverse assessment is not replaceable to seek a favorable verdict.
Route valid findings through ordinary fixes, verification, consultation and
adjudication. A later pass cannot silently cancel established findings or pending
consultations. Invalid reports supply only untrusted leads; independently verify
source-level concerns without partially salvaging a verdict. Do not claim that
missing or unreadable findings have all been recovered.

Strict work still requires implementer then independent reviewer then pass.
Fast/live retain direct edits and one observational wrap-up obligation; replacing
an unusable observational report completes that obligation, not discretionary
review shopping. Decomposed assessments retain global constraints and complete
coverage; passing fragments do not substitute for whole-range integration review.

### Change strategy, not identity counters

Count failed substantive deliveries by role/output phase and observed failure
category across the task, including initial, replacement and decomposed work.
Format-only correction is not a separate substantive attempt. At **two failures
with the same signature**, stop homogeneous retries and diagnose/change strategy:
gather missing evidence, reduce context/output, decompose, or change the relevant
inspection method. Record a concrete productive change before another dispatch.
Author/session/task renames do not reset these counts; later repetition still
requires diagnosis rather than blind generation.

Each genuinely new delivery has its own ordinary format-correction allowance;
that never refunds an ancestor's allowance or substantive fix/consultation/resource
budget. Retain existing substantive fix caps and triggered dual-model advice.
Operational recovery is not permission to restart code repair or consultation
budgets, evade adjudication, change model pins, or expand capabilities.

### Actual boundaries and truthful stopping

Neither a malformed report nor a numeric retry threshold is a human gate. Continue
with a permitted productive recovery step whenever one is identified.

Stop with truthful incomplete operational status only for evidenced actual
resource/time/tool exhaustion, required evidence/service unavailable after
permitted diagnosis, or no identified permitted productive next step. State the
concrete blocker, attempted strategies, retained state and unfinished obligations;
do not ask routine authorization to retry/replan and do not claim completion.

Genuine product/API/data policy, credentials, safety/permission/ownership or unsafe
history decisions, wrapper refusals and existing substantive human-escalation
rules remain human-owned. Technical design decisions remain autonomous under
the existing dual-model gate. Necessary unavailable expert advice still blocks.
Expert answers and capability wrapper JSON/refusals stay outside GLM delivery
repair and are never rewritten or rerun as a formatter.

## Implementation surface

Update canonical AGENTS, the supervisor/fast/live gates, and the preflights in
subagent-driven-development, systematic-debugging and fast-dev-wrap-up. Document
the prospective recovery policy beside the existing history in
`docs/dev/features/opencode-agent-workflow.md`. Preserve historical experiments
and progress records; do not rewrite their scores or past decisions.

Extend source-contract guards and add a separately labelled **test-only** offline
recovery fixture model. Do not add runtime orchestration, permissions, response
keys, model changes, or modifications to the frozen delivery evaluator/question/
rubric/results. No application Fennel/C++ changes or runtime build is warranted.

## Validation and evidence limits

Before skill edits, five independent read-only baseline samples exercised the
same four scenarios under deadline, sunk-cost and unavailable-user pressure.
Baseline sessions: `ses_e79264fd5ffeBI8y835Kw9PEbL`,
`ses_e79264f8effeq97mh5Ha5befQN`, `ses_e79264f60ffeUFMeswmnt5VLgD`,
`ses_e79264f39ffeOdyI04X1jpDYjG`, `ses_e79264f0dffeK5u4F31HxRG8N8`.
Their declared role was explorer, reporting Markdown Findings/Patterns/Uncertainties;
source snapshot was supplied by the controller. Original payloads remain in the
session. Baseline 2 said the block stands "until the human re-opens the scope";
baseline 5 called a same-scope redo ineligible and human-owned. Other samples
allowed continuation or exposed ambiguity. This establishes inconsistent routing,
not a model-wide success/failure rate. Baseline 1 disclosed incomplete supervisor
source access; git snapshot verification was controller-owned in all samples.

Run the same five fresh-context guided probes after edits, manually assess each,
and record safe summaries and limitations in the progress ledger. Cover intact
adverse reviews and capability refusal negatives, not only successful recovery.

Regression cases must include unchanged-range independent replacement, no
impersonation/reset/salvage, usable adverse-review shopping refusal, inherited
findings/consultations, stale replacement, missing global constraints or complete
review coverage, strategy transition after two failures across authors/subtasks,
and real resource/permission/product boundary termination. Run focused pytest,
`make opencode-check`, and relevant docs script/navigation checks. PR CI is the
full integration gate. Source guards, offline fixtures and virtual probes do not
prove runtime enforcement, serialization reliability or autonomous completion.

OpenCode must restart to load reviewed agent/skill changes. Do not modify the
running scoter session or claim its loaded policy has changed.
