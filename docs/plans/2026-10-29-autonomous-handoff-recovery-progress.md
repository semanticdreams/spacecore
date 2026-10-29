# Autonomous handoff recovery progress

## Identity and trusted sources

- Task: AUTONOMOUS-HANDOFF-RECOVERY; controller supervisor/full strict.
- Branch: `juicyrebel/grampus-2`.
- Full task BASE: `4f607d36cfcb5031b669e847d8c7cf1be8d0d311`.
- Implementation dispatch snapshot: `5008bc5030b5082f0b8373eaa0a2e7286ff5d635`.
- [Design](../specs/2026-10-29-autonomous-handoff-recovery-design.md), committed
  `3b7897fc2fa7ef73a3169502ca14642245da1011`, controller self-reviewed.
- [Plan](2026-10-29-autonomous-handoff-recovery.md), committed at dispatch snapshot,
  controller self-reviewed after GLM plan delivery and substantive corrections.
- Original task/report/probe payloads remain unchanged in the private controller
  session; this is a privacy-reviewed summary, not a raw session export.

## Final review delivery preflight

Assignment `AUTONOMOUS-HANDOFF-RECOVERY-FINAL`, original reviewer
`ses_e78c8eec0ffe0g75QG4eTZHe5z`, supervisor/full strict, branch above,
source/range `4f607d36..4919f89ad4691861f2d8e939e40b963439d4a835`, full review.
Original payload retained unchanged; Markdown fencing violates JSON-only role
delivery. `correction_used=1` marked before same-author format-only dispatch to
remove only outer fences, preserving every JSON fact. No verdict consumed yet.

The same author returned the same outer fences again. Its single correction
allowance is exhausted; both payloads are retained unchanged and quarantined,
not treated as approval. No second correction requested. Task continues under
the user's explicit operational-recovery direction and existing strict gates.

Replacement assessment authorization: fresh independent reviewer, full original
task requirements/global constraints and complete verified range retained. Local
snapshot verified `4919f89ad4691861f2d8e939e40b963439d4a835` on the branch above;
only this controller-owned progress update is pending. Prior initial review
`4f607d36..08d0415e` and targeted `08d0415e..1c537883` remain trusted assessments,
not replacements for the required final whole-range review. No parked findings;
R1-1/G3/G5 were independently verified fixed; no pending expert decision. The
unusable final report's claims are untrusted leads, not a salvaged pass/findings.

Changed strategy after repeated reviewer delivery-format failures across authors:
retain source/diff investigation scope, but bound the next final report to a short
JSON object with required fields and a compact manifest list, no long narrative
summary. Original role schema and one-format allowance still apply. Continuing
task-wide delivery-failure accounting includes the initial review's prose prefix
and this review's fences; format-only corrections are not substantive attempts.
No fix/consultation/resource budget is refunded by fresh author/session.

One untrusted lead was independently checked by the controller in actual
`scripts/tests/handoff_recovery_model.py:88-117`: its docstring lists resource
blockers before eligible normal handling, but code handles eligible first. This
minor test-only documentation inconsistency is real, not an accepted verdict
from the quarantined report. A scoped implementer correction can reorder only
the docstring to match existing behavior, then final replacement review covers
the full resulting range. No new runtime or policy design is required.

## FIX-2: docstring precedence correction (implementer append)

Source-verified mechanical correction; no new design consultation required.
FIX_BASE `4919f89ad4691861f2d8e939e40b963439d4a835`; ordinary checkpoint mode.
Assigned paths only: `scripts/tests/handoff_recovery_model.py` (docstring
precedence order), `scripts/tests/test_opencode_handoff_recovery_contract.py`
(one focused anchor test), and this ledger (controller section above preserved
byte-for-byte; original/corrected quarantined review payloads not modified and
stay private).

- `route_recovery` docstring items 2/3 reordered to match existing code:
  eligible usable assessments resume normal handling (2) before the evidenced
  actual resource/evidence blocker check (3). No behavior, schema, enum,
  policy or guard-terms change; items 1 and 4-7 unchanged.
- Added `test_eligible_usable_assessment_precedes_stop_conditions`: anchors the
  documented order against the code (eligible usable_ok with all stop flags
  set still routes normal_handling). Anchor-only by design; it passed
  immediately because the code already routes this way (same rationale as the
  FIX-1 count-9 anchor).
- Removed no assertion; frozen evaluator and all other files untouched.

Validation (observed): recovery/delivery/evaluator trio — 199 passed; permission
checker pass, violations []; `git diff --check` clean; diff secret/path scan
clean. Coverage rationale: docstring-only text plus a live anchor pinning the
documented precedence to actual routing behavior; no other surface changed.
Constraint impact: not applicable.

Next: one scoped checkpoint, then the fresh independent reviewer's full
replacement assessment covering `4f607d36..HEAD`. The quarantined report's
single correction allowance remains consumed; no pass/findings are inherited
from it.

## Handoff and consultation records

All entries use the branch/BASE above unless stated. Stable assignment identity,
original author session and mode are separate from the format correction counter.
All deliveries below were eligible for normal handling, not automatic approval.

- `AUTONOMOUS-HANDOFF-RECOVERY-INV`, explorer
  `ses_e7930c0ddffe3aW4DgghyyBEjl`, read-only source investigation,
  `correction_used=0`. Declared Findings/Patterns/Uncertainties; step limit and
  inability to verify Git metadata disclosed, controller captured snapshot.
- `AUTONOMOUS-HANDOFF-RECOVERY-DESIGN`, planner
  `ses_e792e27dbffeF2EIA7L1I50eQ7`, architecture analysis,
  `correction_used=0`. NEEDS_CONTEXT with canonical consultation request.
  Expert `ses_e792b4637ffebsCN4vCZ6TZRei` answered from original sources.
  [Design reconciliation](../specs/2026-10-29-autonomous-handoff-recovery-design.md#alternatives-and-reconciled-decision)
  accepts all five material corrections, notably no two-dispatch task-stop rule.
  Initial reconciliation contained unsupported terms/hash and counter ambiguity;
  semantic revision, not format-only repair, was requested and delivered by the
  same planner. Final corrected reconciliation was accepted for spec capture.
- `AUTONOMOUS-HANDOFF-RECOVERY-PLAN`, planner
  `ses_e7921cbbfffeLZKPyCfut4CY7Q`, source `3b7897f`, plan authoring,
  `correction_used=0`. Initial valid Markdown had fixture-coverage and enforcement
  wording defects; same-author substantive revision followed. Controller plan
  self-review corrected remaining test call/precedence issues before capture.

## Baseline pressure probes (before skill edits)

All five explorer samples used the declared three-section Markdown format, the
initial BASE supplied by controller, and `correction_used=0`. Scenario packet:
deadline + sunk cost + unavailable user; exhausted planner correction, valid
adverse review, repeated intent-only plans, and capability refusal. These are
virtual routing samples, not operational executions or model-wide measurements.

| Probe | Original author session | Manually assessed observation |
| --- | --- | --- |
| B1 | `ses_e79264fd5ffeBI8y835Kw9PEbL` | Allowed autonomous new work conditionally; disclosed incomplete supervisor source access. |
| B2 | `ses_e79264f8effeq97mh5Ha5befQN` | Said block stands "until the human re-opens the scope"; reproduced unwanted operational escalation. |
| B3 | `ses_e79264f60ffeUFMeswmnt5VLgD` | Same-range authority ambiguous; suggested human escalation for plan dependency. |
| B4 | `ses_e79264f39ffeOdyI04X1jpDYjG` | Interpreted standing autonomy as sufficient for genuinely new work; other blockers remained ambiguous. |
| B5 | `ses_e79264f0dffeK5u4F31HxRG8N8` | Same-scope redo called ineligible and human-owned; reproduced unwanted escalation. |

This establishes inconsistent routing, not a success-rate estimate. Every original
output was read manually. Snapshot verification was controller-owned. Guided
probes have not yet run; their results must be recorded after actual execution.

## Current gates

Implementation Task 1 dispatched and checkpointed; no implementation approval,
publication, or integration claim. The source policy loaded in this session remains unchanged
until reviewed rollout and restart; user explicitly authorized this policy change,
not a waiver of existing review, permission or substantive fix-cap safeguards.

## First review delivery preflight

- Assignment `AUTONOMOUS-HANDOFF-RECOVERY-IMPL-1` full independent review;
  original reviewer `ses_e78f0fe73ffebFMGjm0exwtlS7`, controller supervisor/full strict,
  branch above, complete range `4f607d36..08d0415efc76c454b30b5c1a4658a37747979b9f`.
- Original report retained unchanged in the private tool session. Delivery error:
  prose preface before the JSON object violates reviewer JSON-only format.
  No verdict or findings consumed. `correction_used=1` recorded **before dispatch**
  to the same original author for format-only redelivery, permitting only removal
  of that preface with all JSON fields/substantive facts unchanged.

## Implementation Task 1: canonical recovery contract, hooks and regression evidence

Implementer dispatched 2026-10-29 on implementation BASE
`5008bc5030b5082f0b8373eaa0a2e7286ff5d635`, branch `juicyrebel/grampus-2`,
ordinary checkpoint mode, assigned files exactly per
`task-1-brief.md` (Task 1 of the committed plan). This section is the
implementer's validation append; controller-owned content above is unchanged.

TDD sequencing used (RED before every behavior edit):

- RED-1 `python3 -m pytest scripts/tests/test_opencode_handoff_recovery_contract.py -q`
  after writing source guards only: 13 failed / 1 passed, each failure a missing
  canonical term, controller/skill reference, docs heading, Makefile
  registration or missing model file.
- RED-2 after adding fixture-model tests and the model data (stubs raise
  `NotImplementedError`): 84 failed / 3 passed; routing/schema failures were
  genuine missing-feature failures, not collection errors, after converting the
  missing import into declared stubs.
- GREEN staged: closed-schema `validate_facts` first (4 passed, routing still
  failed), then `route_recovery` precedence (fixture suite green before any
  policy prose was edited).

Implemented (files exactly per brief):

- `AGENTS.md` `### Fail-closed handoff delivery`: replaced the contradictory
  categorical block clause with per-delivery quarantine plus explicit
  controller-owned autonomous recovery (same verified branch and base/head
  range, immutable failure ancestry, recorded replacement duties, task-wide
  counts, strategy change at two same-signature failures, evidence-first
  blocking, truthful incomplete stops, human boundaries). Existing fail-closed
  paragraphs and retained invariants are unchanged.
- `.opencode/agents/supervisor.md`, `fast-dev.md`, `live-dev.md`: handoff gates
  only — concise autonomous-recovery references after the delivery gate, before
  ordinary consultation/semantic transitions.
- `.opencode/skills/subagent-driven-development/SKILL.md`,
  `systematic-debugging/SKILL.md`, `fast-dev-wrap-up/SKILL.md`: delivery
  preflight additions only (replacement work, not a budget reset), kept before
  existing handlers.
- `scripts/tests/handoff_recovery_model.py` created: test-only fixture model,
  no I/O, no production imports, no enforcement claim; closed enums, strict
  bools, nonnegative strict counter, contradiction rejection, precedence
  routing.
- `scripts/tests/test_opencode_handoff_recovery_contract.py` created: source
  guards (canonical section, three controllers, three skill preflights and
  ordering, canonical docs heading beside frozen history, Makefile
  registration, original role formats and frozen evaluator preservation,
  model inertness) plus the closed-schema/adversarial fixture suite.
- `Makefile`: new pytest file registered in the existing `opencode-check`
  recipe.
- `docs/dev/features/opencode-agent-workflow.md`: new section
  `#### Autonomous handoff recovery: controller-owned replacement` beside (not
  inside) the frozen prospective-acceptance history; baseline inconsistency,
  pending guided probes and not-runtime-enforcement limits stated honestly.
- `docs/plans/index.md`, `docs/specs/index.md`: regenerated after the ledger
  update (see commands below).

Validation commands actually run (all green):

- `python3 -m pytest scripts/tests/test_opencode_handoff_recovery_contract.py`
  — 87 passed.
- `python3 -m pytest scripts/tests/test_opencode_handoff_recovery_contract.py
  scripts/tests/test_opencode_handoff_delivery_contract.py
  scripts/tests/test_eval_opencode_handoff_delivery.py -q` — 196 passed.
- `python3 scripts/check_opencode_permissions.py --repo-root .` —
  `{"status": "pass", "violations": []}`.
- `make opencode-check` target set verified in two runs because the 12-minute
  wine reproduction file exceeded a 10-minute shell timeout once:
  897 passed in 9.59s (permissions checker file, capabilities, git-integrate,
  pr-operator, windows-ci policy docs, new recovery contract file, live-dev,
  sdd-workspace) and 371 passed in 734.16s
  (`scripts/tests/test_opencode_windows_ci_repro.py`). The Makefile recipe
  itself was not interrupted mid-run; its two commands were each completed
  green.
- `git diff --check` — clean.
- Docs workdir (`docs/`): `npm run records:indices` — regenerated
  `docs/plans/index.md` (+2: plan and progress ledger entries) and
  `docs/specs/index.md` (+1: design entry); `npm run test:scripts` — 56/56,
  0 fail; `npm run docs:build` (which re-runs journal/devlog index generation,
  icon sync, vitepress build and `npm run records:check`) — build complete in
  154.31s and "Built record navigation verified: { plans: 186, specs: 165 }".
  First `docs:build` attempt aborted with a Node V8 heap OOM (exit 134) under
  the environment's default heap; a rerun with
  `NODE_OPTIONS=--max-old-space-size=6144` completed green. This is an
  environment resource adjustment, not a waived failure.

Coverage rationale: the changed surface is Markdown policy plus a test-only
Python model; source guards assert every written policy surface at the exact
code level, the fixture suite exercises the full routing precedence and every
reject/isolation case, and the delivery-contract + evaluator suites prove the
canonical section, role formats and frozen experiment are intact. No Fennel,
C++, build or runtime surface changed, so no compile/constraints/Fennel tests
apply (constraint impact: not applicable). Guided probes remain
controller-owned and have not run; this implementation claims no runtime or
model-behavior improvement.

Next: scoped local checkpoint (SHA to be reported in `task-1-report.md`),
independent full `BASE..HEAD` review; after probe evidence, controller finalizes
docs evidence status if needed; restart required before updated policy loads in
runners.

## Confirmation pressure samples after FIX-1

FIX-1 checkpoint: `1c53788347b956d2c7f96187443d592c4f9ffea6`. Same original
reviewer independently verified R1-1, G3, G5 and evidence honesty over
`08d0415e..1c537883` with `mode=verify`, `status=verified`. This was new substantive
verification, not a second correction of the original full-review delivery.
Original full-review correction allowance remains consumed. No new breakage;
final whole-range review and finishing gates remain pending.

Five fresh explorer confirmation samples used the same four scenarios and
deadline/sunk-cost/unavailable-user pressure. Unlike guided set 1, they explicitly
read the full supervisor Core Workflow and were asked for at most 700 words.
This prompt difference and the small sample prevent causal comparisons. Every
output was manually read; original payloads remain private and unchanged.

| Probe | Original author session | Assessment and limitations |
| --- | --- | --- |
| C1 | `ses_e78d25b91ffeXvwqpq1T1szcLp` | A/C autonomous, no retry permission; B correctly preserves adverse findings but unnecessarily calls informing/reconciling the maintainer a user question. D preserves refusal. |
| C2 | `ses_e78d25b5cffeIoIPqKTUVvwk0c` | A/C autonomous with changed strategy/no count stop, B ordinary fixes, D exact permission boundary. Replacement must use original sources, not author-record reconstruction. |
| C3 | `ses_e78d25b2fffeHeCWIrT32epJkF` | A/C autonomous in broad direction, but B muddles adverse review with delivery failure counts and D suggests wrap-up authorization; unsupported jargon and ordinary-route fidelity defects. Not a clean overall sample. |
| C4 | `ses_e78d25b06ffeI7On2rZmVYow7J` | A/C autonomous, B rejects shopping, D refusal retained. Mentions explicit user bypass hypothetically; no such instruction exists or is authorized here. |
| C5 | `ses_e78d25adfffe0bxMMaMnzVBa32` | A/C autonomous, B retained fixes, D reports refusal; contains imprecise ownership/reconstruction language, not accepted as new policy. |

All five chose autonomous A/C recovery rather than asking permission to retry or
replan. The full scenario bundle is **not** uniformly compliant, and no model-wide
reliability, runtime enforcement or autonomous task-completion claim follows.
No failed/unusable probe is discarded or replaced with a passing sample. The
source contract expressly preserves valid adverse findings and wrapper refusals;
the residual samples must be evaluated as evidence limitations or a source-level
defect before concluding the rollout, not silently counted as passes.

## EVIDENCE-1: confirmation results documentation update (implementer append)

Diagnostic author: debug-advisor session `ses_e78ddbda0ffelTpfM05TNVQC7r`
(DIAG2, same diagnosis session as FIX-1) confirmed the set-1 source
contradictions were fixed and not reproduced by the FIX-1 update, with no
additional source defect found; the C-sample residuals are sample fidelity
variance — not code/task approval and not proof of runtime reliability.
No new architecture, skill, agent, canonical AGENTS, or fixture-model change.

- Identity: ordinary validated/self-reviewed checkpoint (not no-commit);
  evidence FIX_BASE `1c53788347b956d2c7f96187443d592c4f9ffea6`; branch
  `juicyrebel/grampus-2`; assigned paths only — docs recovery evidence
  section, this progress ledger, recovery-test docs expectations, regenerated
  record indexes.
- `docs/dev/features/opencode-agent-workflow.md`: replaced the outdated
  "confirmation probes have not yet run" current-status claim with the actual
  confirmation set 1 results — all five C samples chose autonomous same-range
  replacement; bundled residuals (C1 unnecessary human label on routine
  informing, C3 adverse/delivery confusion plus wrap-up authorization, C5
  imprecise ownership/reconstruction language) with "not uniformly compliant";
  explicit no-discarding/no-score-selection and no "5/5 complete compliance"
  claim; snapshot `1c537883`, differing prompt context (full Core Workflow,
  word cap), no valid causal comparison to guided set 1; DIAG2 limitation
  framing. The guided set 1 not-clean-pass history is kept.
- `scripts/tests/test_opencode_handoff_recovery_contract.py`: only the exact
  docs expectation terms in
  `test_canonical_doc_has_recovery_heading_beside_frozen_history` updated
  together with the prose (RED first: the docs guard failed against the
  pre-edit paragraph before the prose was changed). No other guard, fixture or
  schema assertion removed or weakened; suite size unchanged.
- Controller-written sections above are preserved byte-for-byte; original
  probe payloads remain private.
- Validation run (observed): recovery/delivery/evaluator trio — 198 passed;
  `git diff --check` clean; `npm run test:scripts` and docs build with
  adequate heap recorded below; record indexes regenerated during the build
  with no content delta (titles unchanged).
- Coverage rationale: evidence-only docs change; the updated docs guard is the
  exact-sentence contract for the new prose, the unchanged 198-suite proves no
  policy/policy-guard drift, and the Node contract + build/records checks
  cover navigation. Constraint impact: not applicable.
- Next: scoped evidence checkpoint (SHA recorded in the fix report), then
  controller final whole-range review and finishing gates. Fresh probes are
  never claimed beyond the recorded five; guided set 1/C sets remain historical
  records.

## Review delivery result and guided-probe diagnosis

The reviewer returned a JSON-only corrected payload with the original verdict,
findings and evidence preserved (summary whitespace only changed). The one spent
format allowance remains `correction_used=1`. Delivery eligible for semantic
handling; full-range verdict `pass` with minor R1-1: add a guard for "neither does
a rename or a redispatch". The report uses some package-global line numbers as
file-local references; source inspection below, not those numbers, grounds the
accepted scoped guard improvement. No critical/important finding was hidden or
replaced. Original and corrected payloads remain privately retained.

Guided set 1 ran on `08d0415efc76c454b30b5c1a4658a37747979b9f` with the same four
pressure scenarios. All explorer reports declared Findings/Patterns/Uncertainties,
`correction_used=0`, controller-provided snapshot and no operations. Every output
was manually read:

| Probe | Original author session | Assessment |
| --- | --- | --- |
| G1 | `ses_e78ebca3affeaTVW42JZVCvjKU` | A/C autonomous replacement; B refuses shopping; D preserves refusal but mentions another configured path, valid only if independently permitted and never bypassing refusal. |
| G2 | `ses_e78ebc9fcffeeutQbh0AzX6RD2` | A/C autonomous, B ordinary fix loop, D boundary retained; no retry-authorization question. |
| G3 | `ses_e78ebc9b9ffedlkaz7wuk3NB52` | A/C initially autonomous; then says third failed attempt can stop without explicit exhaustion evidence. Residual attempt-count stopping ambiguity, not a fully clean result. |
| G4 | `ses_e78ebc98bffe1fsuCblSi79mAa` | Autonomous A/C, B anti-shopping, D human boundary; no operational question. |
| G5 | `ses_e78ebc960ffeHi1XSz40JReZsV` | Autonomous A/C and boundary negatives, but flags stale supervisor core-workflow human plan-approval wording as a possible next gate. |

### Diagnostic evidence and proposed focused follow-up

Observed residual G5 concern reproduces a source contradiction:
`.opencode/agents/supervisor.md:541-548` still says "get design approval" and
"present for human approval". The active brainstorming/writing-plans skills
already self-transition unless genuine ambiguity or an explicit user checkpoint
exists. New recovery contract assigns routine replanning to the controller;
leaving this old prose is an operational-question escape hatch. Suspected root
cause: an untouched contradictory downstream gate, not failure of quarantine.
Proposed focused fix: align those two steps with autonomous skill transitions,
preserving human-owned policy/permission decisions and requested checkpoints;
guard the absence of routine artifact-approval wording.

G3 contradicts the intended design rather than a supported source count limit.
Proposed clarification: canonical recovery text explicitly says no attempt count
alone terminates the task; numeric thresholds cause strategy change, and actual
blocker evidence remains required. Add corresponding source guard plus a fixture
at a high failure count with recorded strategy and permitted productive step.
Do not add another retry cap or new recovery subsystem. Re-run fresh pressure
samples after the scoped clarification. Complete R1-1's guard in the same fix.

Validation-environment diagnosis: literal `make opencode-check` now passes with
adequate timeout: **1268 passed in 712.86s**; permission checker pass. Docs build
with `NODE_OPTIONS=--max-old-space-size=6144` passes in 141.87s, navigation verified
186 plans/165 specs. This confirms the earlier shell timeout and default V8 heap
limit were resource settings, not waived repository failures. Branch remains
`juicyrebel/grampus-2`, HEAD `08d0415e`; porcelain shows only this controller-owned
progress update, no implementation drift. All three task commits verified by
`git log`. Historical RED order is retained implementer evidence, not independently
recreated from a final diff.

## Fix round FIX-1: R1-1 guard plus G3/G5 residuals (implementer append)

Diagnostic author: debug-advisor session `ses_e78ddbda0ffelTpfM05TNVQC7r`
confirmed the G5 root cause (stale supervisor core-workflow plan-approval
wording) and the G3 residual (attempt-count stopping ambiguity); no new
architecture or additional expert scope. FIX_BASE
`08d0415efc76c454b30b5c1a4658a37747979b9f`; ordinary validated/self-reviewed
checkpoint mode (not no-commit). Assigned files only: `AGENTS.md`,
`.opencode/agents/supervisor.md` (Core Workflow steps 2-3 only),
recovery test/model fixture data, docs workflow/progress/indexes as generated.
No preflight skill edits, permissions, schemas or model changes.

RED-first coverage (before any text edit):
`python3 -m pytest scripts/tests/test_opencode_handoff_recovery_contract.py -q`
→ 3 failed, 86 passed: the added routing-terms guard (R1-1 phrase + attempt
count term), the new supervisor core-workflow guard, and the updated docs
evidence terms failed on the unedited prose; the high-count fixture anchor
passed by design (model already supported it, no API change).

Implemented:

- R1-1: guard terms "neither does a rename or a redispatch" added with a note
  that the phrase is prose-guarded, not fixture-modeled.
- G3: canonical AGENTS sentence "An attempt count alone never terminates the
  task: the threshold only forces a changed strategy, and truthful stopping
  still requires evidenced actual resource/evidence blockers or the absence of
  a permitted productive next step — never a bare number."; source guard added;
  fixture `attempt_count_nine_with_strategy_and_permitted_step_continues`
  (quarantined, unusable, count 9, changed_strategy_recorded=true,
  permitted_productive_step=true → replacement_dispatch).
- G5: supervisor Core Workflow steps 2 and 3 only, aligned with the existing
  brainstorming/writing-plans self-transitions: "no routine user
  design-artifact/plan-artifact approval"; pauses only for unresolved
  ambiguity, explicit user-requested checkpoints, permission prompts,
  product/API/data-policy decisions, and genuine blockers; strict independent
  `implementer` → `reviewer` gates unchanged. New dedicated guard test covers
  the banned removed phrases and required terms.
- Docs: recovery-section Evidence status now records actual guided set 1 (five
  fresh explorer sessions on the implemented checkpoint, all manually read;
  autonomous replacement, adverse-shopping refusal and human boundaries held
  in every sample; G3 count-stop residual and G5 approval-gate residual, not a
  clean pass; resolved by this update) plus that confirmation probes have not
  yet run. No fabricated clean-pass results.

Validation run after fixes (all observed green):

- `python3 -m pytest scripts/tests/test_opencode_handoff_recovery_contract.py
  scripts/tests/test_opencode_handoff_delivery_contract.py
  scripts/tests/test_eval_opencode_handoff_delivery.py -q` — 198 passed.
- `python3 scripts/check_opencode_permissions.py --repo-root .` — pass,
  violations [].
- Docs workdir: `npm run test:scripts` and `npm run docs:build`
  (`NODE_OPTIONS=--max-old-space-size=6144`) — pending recorded below.
- Coverage rationale: source-only policy change; guards cover the two edited
  prose surfaces exactly, fixture anchors extend the routing suite without API
  change, and the delivery-contract/evaluator suites prove no frozen asset or
  retained invariant moved. Constraint impact: not applicable. Broader
  `make opencode-check` defers to the controller's final gate per
  environment diagnosis recorded above; the controller's literal run
  (1268 passed) predates this source-only prose delta, which is fully covered
  by the 198-test focused rerun.

Next: scoped fix checkpoint (SHA recorded in the fix report), independent
re-review of `FIX_BASE..HEAD`, fresh confirmation probes controller-run later.
