# Autonomous Handoff Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make internal delivery recovery autonomous while retaining fail-closed report acceptance and all substantive review safeguards.

**Architecture:** Extend the canonical AGENTS contract and existing receiving-controller and skill hooks. Add source guards and a separately labelled test-only executable fixture model, not a production recovery engine. The [design](../specs/2026-10-29-autonomous-handoff-recovery-design.md) records GLM proposal, expert critique and corrected GLM reconciliation.

**Tech Stack:** Markdown prompts/docs, Python pytest, existing Makefile policy gate and Node docs tooling.

## Global Constraints

- Branch `juicyrebel/grampus-2`; task BASE `4f607d36cfcb5031b669e847d8c7cf1be8d0d311`; review the complete accumulated `BASE..HEAD`, including coordination documents.
- No production parser/service/orchestrator, worker response-key changes, permission expansion, model changes, Fennel/C++ changes or runtime build.
- Keep the frozen `scripts/eval_opencode_handoff_delivery.py`, its QUESTION/RUBRIC/results and existing evaluator tests unchanged. Per-payload BLOCKED is still correct.
- Reject the unusable delivery, not the overall task. One same-author format correction per original identity remains; no salvage/reset/impersonation.
- Explicit same-range independent replacement completes a missing/unusable assessment; usable adverse assessments retain the ordinary fix/consultation/adjudication route.
- Preserve established findings and pending consultations; independently verify invalid-report concerns as untrusted leads, never salvaged verdicts.
- Two same-signature substantive failures across the task require diagnosis/changed strategy, not task termination or a human authorization question. Counts persist across authors and decomposition; format correction is not a new substantive attempt.
- Preserve fix/consultation/resource budgets, complete review coverage and global constraints. No fetch/merge at every handoff; existing final freshness gates remain.
- Actual resource/evidence/service blockers must be evidenced; genuine product/safety/permission boundaries and substantive human-escalation rules remain unchanged.
- Five baseline probes ran before skill edits; five guided fresh-context probes must follow. Virtual probes, source guards and offline fixtures are not runtime enforcement or completion proof.
- Reviewed configuration takes effect after restart. Do not modify the running scoter session or claim it already loaded the new policy.

---

### Task 1: Canonical recovery contract, receiving hooks and regression evidence

**Files:**
- Modify: `AGENTS.md`, subsection `### Fail-closed handoff delivery`.
- Modify: `.opencode/agents/supervisor.md`, `.opencode/agents/fast-dev.md`, `.opencode/agents/live-dev.md`, handoff gates only.
- Modify: `.opencode/skills/subagent-driven-development/SKILL.md`, `.opencode/skills/systematic-debugging/SKILL.md`, `.opencode/skills/fast-dev-wrap-up/SKILL.md`, delivery preflights only.
- Create: `scripts/tests/handoff_recovery_model.py`, `scripts/tests/test_opencode_handoff_recovery_contract.py`.
- Modify: `Makefile`, `docs/dev/features/opencode-agent-workflow.md`.
- Create: `docs/plans/2026-10-29-autonomous-handoff-recovery-progress.md` (controller-owned ledger; implementer appends its validation/checkpoint evidence).
- Regenerate: `docs/plans/index.md`, `docs/specs/index.md`.

**Interfaces:**
- Consumes the reconciled design and existing role-specific formats. Old source guards remain meaningful; replace contradictory prose rather than appending an exception that leaves the original human gate intact.
- Produces canonical `Autonomous operational recovery` guidance in the same AGENTS section, concise references in all three controller gates and three preflights, and docs section `#### Autonomous handoff recovery: controller-owned replacement`.
- Test-only function `route_recovery(case: dict) -> str` illustrates explicit fixture facts, does no I/O, imports no production modules, and makes no enforcement claim. `CASES` contains named `{facts, expected}` examples. Do not reuse or edit the frozen evaluator.
- Closed fixture schema: enums `delivery_state` (`eligible`, `format_repair`, `quarantined`, `excluded`) and `assessment` (`missing`, `unusable`, `usable_adverse`, `usable_ok`); strict booleans `snapshot_verified`, `ancestry_recorded`, `independent_work_required`, `findings_preserved`, `pending_consultations_preserved`, `global_constraints_preserved`, `whole_range_review_required`, `changed_strategy_recorded`, `actual_resource_exhaustion`, `unavailable_evidence_after_diagnosis`, `permitted_productive_step`, `human_boundary`; nonnegative strict integer `failures_same_signature`. Reject unknown/missing keys and bool-as-integer counter values.
- Fixture precedence: actual human boundary/excluded output follows its existing route; eligible usable assessment resumes normal handling (adverse findings cannot be replaced); eligible first-format repair spends its single allowance; quarantined delivery may only enter replacement after verified snapshot, immutable ancestry, independent work and all inherited obligations are recorded. Missing facts block replacement dispatch for autonomous evidence gathering, not human permission. Evidenced actual resource/unavailable-evidence blockers or no permitted productive next step produce truthful incomplete status, not approval. Otherwise threshold ≥2 requires changed strategy before dispatch; ordinary same-range replacement remains possible below threshold. Test both successful changed-strategy continuation and refusal of unchanged blind retries.

- [ ] **Step 1: Add and run failing source guards (RED).** Mirror existing `section()` helper in the new test file. Representative test:

```python
def test_canonical_autonomous_recovery():
    rule = section("AGENTS.md", "### Fail-closed handoff delivery")
    for term in ("Autonomous operational recovery", "same verified branch and base/head range",
                 "immutable failure ancestry", "Reject the unusable delivery, not the overall task",
                 "untrusted lead", "truthful incomplete"):
        assert term in rule
```

Run `python3 -m pytest scripts/tests/test_opencode_handoff_recovery_contract.py -q` and record actual missing-policy failures before editing prompts/skills. Guards also cover each controller/skill reference, gate ordering, canonical docs heading, Makefile registration, and preservation of the original role formats and frozen evaluator.

- [ ] **Step 2: Add the test-only fixture model and adversarial examples.** Illustrate decisions with explicit facts, not inferred report parsing. Representative parametrization:

```python
@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_recovery_examples(case):
    assert route_recovery(case["facts"]) == case["expected"]
```

Cover valid ordinary handling, first format correction, changed-fact/exhausted/unavailable-author quarantine, unchanged-range replacement with actual new source inspection, no impersonation/rename/salvage, usable adverse-review shopping refusal, inherited findings/consultations, stale snapshot, lost constraints/whole-range coverage, task-wide count retention across authors/subtasks, threshold strategy switch without task stop, actual resource/evidence/no-productive-step stopping, human boundary and wrapper/expert exclusion. Isolate each negative fact and schema error; do not merely test a function that returns the fixture's expected field.

- [ ] **Step 3: Implement canonical prose and hooks.** Replace the ambiguous categorical block clause with per-delivery quarantine and explicit controller-owned replacement. Record predecessor identity, current verified local range, original requirements/global constraints, diagnosis, changed strategy, original source/diff work, established obligations vs untrusted concerns, continuing counts/budgets. Explicitly forbid review shopping; preserve strict and fast/live ownership. Skills reference the same contract with `replacement work` and `not a budget reset`; keep references before ordinary semantic/consultation transitions. No permissions, schemas or frontmatter changes.

- [ ] **Step 4: Document policy and wire tests.** Add the docs recovery section beside, not inside a rewrite of, frozen experiment history. State baseline inconsistent routing, current guided probes not yet run, and evidence/activation limits honestly. Register new pytest file in the existing `opencode-check` recipe. Record safe implementation evidence in the existing progress ledger. Regenerate record indexes after new tracked records exist.

- [ ] **Step 5: Validate focused surface (GREEN).** Run:

```bash
python3 -m pytest scripts/tests/test_opencode_handoff_recovery_contract.py scripts/tests/test_opencode_handoff_delivery_contract.py scripts/tests/test_eval_opencode_handoff_delivery.py -q
python3 scripts/check_opencode_permissions.py --repo-root .
make opencode-check
git diff --check
```

In `docs/` workdir, run `npm run records:indices`, `npm run test:scripts`, `npm run records:check`, `npm run docs:build`. Inspect actual package scripts first; install declared dependencies only if required and already permitted. Any failure enters systematic debugging rather than being waived as unrelated. PR CI is the full integration gate.

- [ ] **Step 6: Self-review and checkpoint.** Inspect full task diff, no secrets/private paths, frozen files unchanged, no contradictory block/human-gate wording, no schema/permission drift. Record commands/results and coverage rationale, then create one scoped local checkpoint. Preserve unrelated staged/worktree entries; no amend, push, PR or integration authority. Independent reviewer must inspect full `BASE..HEAD`; implementer DONE is not approval.

### Controller validation and finishing

- Run five guided fresh-context probes with the same four-scenario and deadline/sunk-cost/unavailable-user pressure structure as baseline; manually read every output. Preserve original payloads and record session identities and safe summaries.
- If a material probe failure appears, diagnose before routing a scoped implementer fix, preserve failure evidence and budgets, then rerun affected checks/probes. Do not turn the new policy into a claim that every failure is recoverable.
- After probe evidence, dispatch implementer to finalize the docs evidence status if needed and regenerate records; independent review must cover the complete task range and every subsequent evidence/fix range. Controller may maintain only its allowed progress ledger directly.
- Ensure reviewed changes committed, tree clean, fetch/evaluate current `origin/main` via capability worker, validate from current base, push/PR/queue per existing finishing policy. Do not stop at queue entry; mergedAt is success. Tell user restart is required.

### Acceptance and exclusions

All policy/test/docs gates green; unchanged historical evaluator; all receiving paths carry explicit autonomous same-range recovery; no usable adverse verdict displaced; five baseline and guided samples truthfully documented. Source-contract and fixture tests illustrate policy, not runtime execution. No app/runtime changes or broad validation claims. Existing permissions, model pins, substantive fix caps, expert advice and merge safeguards stay intact.

Plan provenance: GLM planner `ses_e7921cbbfffeLZKPyCfut4CY7Q`; controller self-review corrected the fixture call signature, inconsistent precedence, placeholder evidence phrasing and unsupported enforcement claim before capture. No new architectural decision was introduced.
