# Task 5 — bounded delivery-state validator and opt-in replay driver

## Status and scope

**DONE for the assigned implementation, ready for independent review, not approval.**
No baseline, guidance or live replay was executed. Controller preparation and model
calls remain review-gated. Task 6 guidance changes have not begun.

BASE: `42d6b443b8ca6c068d0bae84dd5c960cf4adac67`.
Approved delivery-contract source: `989261a5` (spec); bounded Task 5 plan: `42d6b443`.
The existing actual GLM proposal / GPT critique / reconciliation in the approved
spec is reused unchanged. No new architecture or delivery contract was introduced;
no repeat consultation or GPT quality evaluation was performed.

Complete assigned file list (all additions):

- `scripts/eval_opencode_handoff_delivery.py`
- `scripts/tests/test_eval_opencode_handoff_delivery.py`
- `.superpowers/sdd/2026-10-25-glm-default-expert-consultation-44988498/task-5-report.md`

No agents, skills, AGENTS, policy guidance, old helper, old report, frozen evidence,
spec, plan or ledger was edited. Initial worktree/index were clean; only these
three assigned additions are included in the local checkpoint.

## Implementation

- `evaluate_delivery(case: dict) -> dict` uses explicit fixture evidence, retaining
  stable identity and correction usage. Initial valid delivery and valid preserved
  correction are only `ELIGIBLE_FOR_NORMAL_HANDLING`, never approval. An eligible
  initial malformed delivery returns `FORMAT_REPAIR_REQUIRED` with its sole repair
  consumed. Exhaustion, excluded expert/wrapper output, stale scope, changed facts
  or unavailable author blocks. Counter state belongs to the original identity,
  not mutable labels; this is not a production identity registry/schema engine.
- Explicit JSON and intentionally Markdown fixtures exercise declared validity
  without imposing universal serialized handoffs on ordinary roles.
- Fixed CLI: `prepare --repo-root .`, `micro --phase baseline|guidance`, `replay`,
  `report`. Import, preparation and tests do not implicitly invoke OpenCode.
  Only controller execution of micro/replay can invoke it.
- Fixed new root: `/tmp/space/opencode-handoff-delivery`. Scope checking rejects
  lexical escapes and symlink components before content reads. Historical reads
  are confined to the two explicit owned routing roots; inventory rejects
  non-regular evidence. No home/auth/config/log/database/session discovery.
- Preparation freezes full `original.SOURCES` workflow context, one short
  five-scenario pressure bundle, separate evaluator-only manual rubric, hashes,
  schema-first all-tools-denied GLM/no-variant config, and a new zero budget.
  Old answers and the rubric are not included in micro candidate packets.
- Baseline verifies current source equality before calls. Guidance requires all
  five baseline outcomes; only source context changes between phases. Both phases
  use the identical question and five fresh contexts, deadline/sunk-cost/authority
  pressure, plain routing explanations rather than matrix/JSON perfection scoring.
  Independent review, all three controllers, both-model design input, direct
  fast/live ownership and live code-edit versus report-only lifecycle are covered.
- Exclusive guards/reservations cap the ledger at ten micro slots plus one repair
  slot. Five slots are reserved before each phase's first call; crashes, malformed
  replies and timeouts cannot be resampled. Micro run plus own export shares one
  120-second deadline; replay preexport/run/postexport shares 180 seconds. The new
  persistent micro/repair accounts are separate from historical spent budgets;
  worst-case charges precede calls and survive interruption. Normal completed
  accounting measures CLI capture time, not offline packet/validation work.
- Existing read-only context, file-backed capture, strict JSON loader and actual
  own-session/model/completion/tool checks are reused. Additional checks require
  exactly one assistant, absent reported variant, run/export message-ID and text
  agreement, and no reused recorded historical/new session. Failed micro calls
  retain observed own IDs for later freshness checks. No model/API fallback.
- Replay only exports/resumes `ses_e8a4fd4a1ffeg08U1O1gJVbwTD`, anchored to the
  retained clarified-2 result/run/export. It checks actual GLM identity and retained
  content, preexports all original message IDs/content, requires unchanged original
  history, and rechecks frozen evidence before authorizing a generation. Canonical
  assignment metadata allows only `wrap-up-review.workflow` from
  `fast-dev-reviewer` to `fast-dev`; no semantic oracle route/owner answers enter
  the correction request. All other JSON values, including rationales, must match
  the retained original exactly.
- Only the newly observed assistant ID absent from preexport may be parsed;
  unchanged old messages are checked before filtering the export. Hidden/duplicate
  assistants, tool/retry parts, old history edits, invalid schema or protected fact
  changes block. The old strict matrix parser is used only for this retained matrix
  replay, never for Markdown reviews or micro explanations. There is no scoring of
  old answers and no old answer mutation or normalization.
- Replay exposes `repair_succeeded` separately from delivery state. An invalid
  response is correctly blocked without a second generation, not treated as a
  harness acceptance failure merely because the model could not repair. Verified
  final text survives strict-parser rejection; private reasoning stays out of
  result/report summaries. The possible original-server-history append is disclosed
  even for a failed attempt; it is not a fresh sample or metadata alias.
- All 73 original experiment files and the full clarified owned tree are hashed
  before preparation and verified afterward, before execution/reporting, after
  each attempt and before the one repair generation. Historical budget bytes and
  saved raw snapshots remain immutable. New root files never replace old evidence.

## Validation evidence (offline only)

Compile-check evidence: **not applicable** — no Fennel, bindings, native/runtime
or build edits; no native/Fennel execution.

Constraint status: **not applicable** — no Fennel constraints, agents, skills or
guidance edited. **Constraint Impact: not applicable.** The assigned Python-only
surface is covered by new deterministic tests plus all 125 existing helper tests,
not the unrelated full engine suite or a live model trial.

Final command:

```text
PYTHONDONTWRITEBYTECODE=1 rtk pytest -q scripts/tests/test_eval_opencode_handoff_delivery.py scripts/tests/test_eval_opencode_expert_routing.py scripts/tests/test_eval_opencode_expert_routing_clarified.py scripts/tests/test_eval_opencode_pilot.py
Pytest: 187 passed
```

That is **62 new + 125 existing passing tests**, no warnings or stray test output.
`rtk pytest` runs the requested pytest checks and formats the captured summary.
Focused new tests were run first and throughout implementation. The existing
capture suite supplies the regular-file stdio regression, including the prior
pipe-truncation boundary; no new pipe-based capture implementation was introduced.

Coverage includes delivery transitions, JSON/Markdown fixtures, explicit invalid
fixture state, renamed duplicate exhaustion, no eligibility-as-approval, excluded
authors, lexical/symlink scope rejection, source and packet freezing, 73-file and
clarified snapshot preservation, 120/180-second shared deadlines, persistent invalid
budget rejection, interruption/timeout consumption, exactly eleven possible
generations, actual model/variant/tool/completion checks, failed-session freshness,
own author unavailable, new-ID-only selection, hidden assistants, immutable old
message content, protected route/owner/rationale changes, invalid correction text,
and source changes during preexport preventing any generation. All external CLI
calls are mocked; an autouse guard also prohibits actual `subprocess.Popen`.

This covers the driver/state machine and reused capture/parser boundary. It does
not prove future prompt conformance, hard runtime enforcement, model competence,
repair success or manual acceptance of actual model explanations.

### TDD evidence

Before implementation, wrote the state/scope/counter/freeze/budget/parser/history/
protected-fact/no-actual-call fixtures. Initial focused RED:

```text
PYTHONDONTWRITEBYTECODE=1 rtk pytest -q scripts/tests/test_eval_opencode_handoff_delivery.py
Pytest: 0 passed, 1 failed, 48 skipped
AssertionError: delivery helper not implemented
```

The explicit existence assertion failed because the production module did not
exist; dependent fixtures were intentionally skipped rather than failing import
collection. Initial GREEN after implementation: **49 passed**.

Additional self-review regressions were also added before their implementation:

- **RED 57 passed / 2 failed:** request record incorrectly said `BLOCKED` after
  preconsumption; accounting included ten synthetic seconds of offline work.
  Root causes were evaluating the already-consumed state as a new request and
  measuring the whole action rather than capture intervals. Record the initial
  transition, then consume it; measure captures separately. GREEN combined:
  **184 passed**.
- **RED 52 passed / 8 failed:** new assertions exposed missing generation/history
  disclosure and lost failed-call session IDs. Persist observed identities and
  verified final text independently of role-schema success, and disclose possible
  history append on failures too. GREEN combined: **185 passed**.
- **RED 6 passed / 1 failed** on focused invalid/changed-facts cases: a responding
  author's invalid JSON was mislabeled unavailable. Only pre-generation inability
  marks unavailable; exhausted invalid correction blocks as exhausted. Later
  focused and combined GREEN confirmed the result.
- **RED 1 passed / 1 failed** on the source-during-preexport / full-ledger selection:
  snapshot changes detected only after replay could allow generation first. Verify
  the frozen evidence again after preexport and before spending the generation.
  Final combined GREEN: **187 passed**.

These were focused additions under the unchanged approved contract, not new live
diagnostics or model calls. No tests were weakened or valid failures suppressed.

## Self-review and decisions

Self-reviewed complete source and tests. Kept one focused 418-line fixed driver,
not plugins, universal schemas, generalized orchestration or a new policy tracker.
The state assessor consumes explicit evidence; only the retained real matrix
replay uses the old strict matrix parser. Kept manual interpretation separate
from capture validity and repair success separate from safe blocked handling.
The small self-review defects above are fixed and covered by regression tests.
No unresolved correctness concern identified; independent review remains required.

`git diff --check` and `git diff --staged --check` passed (exit 0, no whitespace
errors). Staged local-path/credential-marker search found no matches. Review the
entire `BASE..HEAD` range, including both new scripts and
this report; no preexisting helper diff or pending guidance edits are part of it.
Resolve the report-bearing checkpoint with:

```text
git log -1 --format='%h %s' -- .superpowers/sdd/2026-10-25-glm-default-expert-consultation-44988498/task-5-report.md
```

The final handoff supplies its exact checkpoint SHA (a report cannot embed its
own commit hash). No earlier task checkpoint is being reused as this task's review.

## Exact live-operation statement and handoff limits

**Actual model calls: 0. Actual live runtime preparations: 0. Reads of actual
external routing roots: 0.** No original own-session exports/resumes, native/Fennel
execution, credential browsing, home/private log/database access, environment
dumps, push, PR, integration, history rewrite or runtime restart. Tests prepared
only synthetic pytest-owned fixtures, never any actual fixed live root.

Historical `593.4621967620624` and `339.499002335011` spent seconds are supplied
context and immutable synthetic-fixture values, not fresh measurements by this
implementer. Real before/after hashes and model outcomes remain controller-owned.

After independent review, the controller must verify the permitted parent, prepare
the fixed root, run exactly five baseline contexts, and read every final explanation
before guidance edits. All later calls remain within the authorized ten micro plus
one original-author repair allocation, no repeats or extra GPT quality evaluations.
Baseline compliance cannot support an improvement claim. The prior first-perfect
five-call gate remains historically **FAILED**; prospective safe delivery handling
does not rescore or approve it. Loaded project roles remain unchanged in this
running session until the separately authorized complete-rollout restart.

## Accepted final whole-branch finding R2-1 — fix round 1

### Scope and checkpoint

Verified starting HEAD exactly matches assigned
`FIX_BASE=778b794ce778931e3eba6453c5ce18e7d1999def`; initial worktree/index clean.
This section covers only the accepted cancellation-cleanup finding, not a new
review of the other branch changes or a new model/policy validation tranche.
The original Task 5 implementation checkpoint remains `87aca044`.
The fix checkpoint is the commit containing this appended section; its exact SHA
is supplied in the final handoff and can be resolved using the report-path log
command above. Independent targeted verification must inspect `FIX_BASE..HEAD`.

Complete fix file list:

- `scripts/eval_opencode_pilot.py` — shared `capture_process` cleanup only.
- `scripts/tests/test_eval_opencode_pilot.py` — five focused cleanup regressions.
- `scripts/tests/test_eval_opencode_handoff_delivery.py` — one integration regression
  coupling real shared capture logic to the existing synthetic delivery fixtures.
- `.superpowers/sdd/2026-10-25-glm-default-expert-consultation-44988498/task-5-report.md`
  — this appended fix evidence.

The accepted finding explicitly authorizes this narrow exception to the earlier
no-pilot-runner-edit restriction. Frozen cases/data, source policy, questions,
oracles, parsers, actual captured files, historical results and success records
were not changed or rescored. No driver production code or budget rules changed.

### Root cause and implementation

`capture_process` starts a separate process session but previously killed/reaped
it only when `communicate` raised `TimeoutExpired`. A `KeyboardInterrupt`,
`SystemExit` or ordinary exception could propagate while that child group remained
running. Existing ledger-only interruption tests did not exercise this boundary.

The same boundary now handles `BaseException` after a child has been started:
send `SIGKILL` only to the group identified by that child PID, drain via
`communicate`, and explicitly `wait` even if draining itself raises. A group that
already exited (`ProcessLookupError`) is an expected race, not a reason to skip
reaping. The original exception instance is propagated; unexpected cleanup errors
are chained as its explicit cause rather than suppressed or substituted. Normal
successful/nonzero behavior and the existing timeout classification remain intact.
Raw capture files are retained and their handles close on unwind.

This restores the already-approved lifetime contract at the shared boundary for
all reusers. It adds no new design/authority contract and needs no repeat design
consultation or model call. Parent/unrelated process groups are not targeted;
`start_new_session=True` and the exact child PID target are regression-checked.

### TDD and validation

Compile-check evidence: **not applicable** (Python-only change; no native/Fennel
execution). Constraint status: **not applicable** (no Fennel constraints, role or
policy changes). **Constraint Impact: not applicable.**

RED, before the production edit:

```text
PYTHONDONTWRITEBYTECODE=1 rtk pytest -q scripts/tests/test_eval_opencode_pilot.py::CaptureProcessCleanupTests::test_capture_process_interrupt_kills_and_reaps_process_group
Pytest: 0 passed, 1 failed
```

The failure is the `kill.assert_called_once_with(proc.pid, SIGKILL)` assertion:
after the fake started child's first `communicate` raised `KeyboardInterrupt`,
the old boundary propagated it without calling `killpg`. The focused command was
repeated before implementation with the same expected failure. All additional
cleanup and delivery-integration fixtures were also written before implementation;
their pre-edit run failed on missing cleanup/error-preservation assertions.

GREEN after the shared-boundary change:

```text
PYTHONDONTWRITEBYTECODE=1 rtk pytest -q scripts/tests/test_eval_opencode_pilot.py::CaptureProcessCleanupTests::test_capture_process_interrupt_kills_and_reaps_process_group
Pytest: 1 passed

PYTHONDONTWRITEBYTECODE=1 rtk pytest -q scripts/tests/test_eval_opencode_pilot.py::CaptureProcessCleanupTests scripts/tests/test_eval_opencode_handoff_delivery.py::test_capture_interrupt_cleanup_keeps_delivery_slots_and_budget_consumed
Pytest: 6 passed

PYTHONDONTWRITEBYTECODE=1 rtk pytest -q scripts/tests/test_eval_opencode_pilot.py scripts/tests/test_eval_opencode_expert_routing.py scripts/tests/test_eval_opencode_expert_routing_clarified.py scripts/tests/test_eval_opencode_handoff_delivery.py
Pytest: 193 passed
```

Output pristine. Coverage includes interrupt, SystemExit, ordinary communicate
failure, timeout/interrupt raced with group exit, unexpected kill failure, a second
interrupt during cleanup, same-instance exception propagation, visible cleanup
causes, exact child-group targeting, reaping, closed handles and byte-preserved
partial stdout/stderr. Existing nonzero/timeout and regular-file stdio tests remain
green. The integration case uses shared capture with mocked Popen/killpg and proves
all five phase slots and the full reserved 120-second charge remain consumed, no
second Popen/retry occurs, and synthetic historical hashes stay unchanged.

### Self-review, limitations and handoff

Self-reviewed the complete narrow diff and failure paths. No test weakened and no
unrelated index/worktree entry changed. Focused six new tests plus all four helper
suites cover the shared capture behavior and downstream accounting; a full Space
build/suite is unrelated and was not run. Diff whitespace checks passed; complete
staged checks are repeated before the task-scoped local checkpoint.

An unexpected OS cleanup failure is surfaced explicitly; it is not silently
reported as successful termination. No real model cancellation trial was performed
or needed for this offline regression. **This fix round made zero model calls,
zero live runtime preparations and zero reads of actual external evidence roots.**
No native/Fennel execution, permission edits, credentials/private data access,
push/PR/integration or history rewrite. Ready for independent targeted verification,
not an approval or integration claim.
