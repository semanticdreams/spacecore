# GLM-Default Expert Consultation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use GLM for ordinary project agents in supervisor, fast-dev and live-dev, with mandatory GLM/GPT input on architecture/design/system contracts and bounded GPT help for difficult or critical questions.

**Architecture:** Change all sixteen project-agent pins and add one read-only expert. Preserve authority and workflow ownership, with explicit pending-consultation outputs and controller handling. A small opt-in pressure helper freezes five baseline contexts before skill edits and runs five updated contexts after independent review; no new benchmark platform or candidate code execution.

**Tech Stack:** OpenCode Markdown/YAML agents and skills; Python stdlib/pytest; existing Node workflow-contract tests.

## Global Constraints

- Authoritative spec: `docs/specs/2026-10-25-glm-default-expert-consultation-design.md`.
- All sixteen existing project roles use exactly `opencode-go/glm-5.3-flash`, without GPT-specific variants.
- Only new `expert-advisor` uses `openai/gpt-6.1-sol`, variant `high`, read-only subagent.
- Project/root OpenCode JSON and home configuration remain untouched; inherited built-in/hidden/global agents are outside coverage. Use project-defined explorer/workers rather than implicit model fallback.
- Preserve existing permissions, delegation denials, capability commands, publication/checkpoint authority and independent review.
- One consultation per decision scope; reconsultation requires genuinely new material evidence. No expert implementer or automatic full GPT review.
- User refinement: every architecture, software-design or system-contract decision requires a GLM proposal and GPT critique before dependent implementation, regardless of confidence or prior failure. Reuse a reconciled decision until materially changed; this applies to all three workflows, including meaningful local design.
- Ten fresh GLM validation calls maximum: five baseline before any skill edits and five guidance afterward. No retries or extra GPT trials.
- This original experiment limit is immutable. Separately authorized later tranches use only their explicit addendum budgets/roots; they do not reset, rescore or retry the original experiment.
- 180 seconds per run plus own-session export, 35 minutes aggregate live CLI time across both phases. Persist consumed time; do not reset it. Offline development/review and human pauses are not live CLI time.
- Runtime artifacts only under `/tmp/space/opencode-expert-routing`. Controller owns live calls/reads; implementers use repository/mock tests and supplied facts, not denied external reads.
- Normal internal CLI authentication is allowed; never inspect/copy auth, home config, private logs, databases, other sessions or environment secrets.
- No production Fennel changes/native build or edits to frozen pilot data/runner. Restart only after the complete reviewed rollout; loaded sessions retain old models/rules.

---

### Task 1: Reviewed routing-pressure helper and frozen baseline

**Files:**
- Create: `scripts/eval_opencode_expert_routing.py`
- Create: `scripts/tests/test_eval_opencode_expert_routing.py`
- Reuse read-only: safe capture/parser primitives in `scripts/eval_opencode_pilot.py`
- Read context: `AGENTS.md`, primary/worker prompts, and full SDD/systematic-debugging/fast-dev-wrap-up skills.
- Do not change agents, skills, routing policy or pilot evidence in this task.

**Interfaces:**
- `prepare(repo_root: Path) -> dict`: exclusive runtime workspace and baseline context/scenario/schema snapshots.
- `run_phase(repo_root: Path, phase: str) -> dict`: only `baseline` or `guidance`, exactly five reservations per phase.
- `checked_runtime_path(path: Path) -> Path`: reject outside-root/symlink escapes before reads.
- `parse_answer(text: str) -> dict`: exact scenario coverage and routing-only JSON.
- CLI: `prepare --repo-root .`, `run --repo-root . --phase baseline|guidance`, `report`.

- [ ] **Step 1: Write failing offline tests** for reject-before-read, exclusive preparation, symlink escape, duplicate phase/slot refusal, guidance-before-baseline, fixed ten-call budget, and aggregate time persistence. Mock real-runtime access so tests never inspect controller artifacts.

```python
def test_outside_root_rejected_before_read(monkeypatch):
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("unexpected read"))
    with pytest.raises(ValueError):
        routing.checked_runtime_path(Path("/tmp/not-allowed/result.json"))
```

- [ ] **Step 2: Run the focused test module and observe RED**, then implement the minimal stdlib helper; no platform abstractions or new package dependencies.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q scripts/tests/test_eval_opencode_expert_routing.py
```

- [ ] **Step 3: Freeze baseline packets before Task 2.** Use a fixed source allowlist: AGENTS, three primary prompts, relevant worker output contracts, full SDD/systematic-debugging/fast-dev-wrap-up. Guidance uses the updated same sources; scenarios/instructions/schema are identical. Keep expected answers out of candidate context.
- [ ] **Step 4: Encode all workflow/skill pressure cases.** Every fresh context answers the same compact matrix (approximately 12–18 labelled decisions, not a full case/workflow cross-product), combining time, sunk-cost and authority pressure: first syntax repair/TDD RED stays GLM; every fresh architecture/design/system-contract decision consults even when confident; retained alias/fallible-save and same material failure after a repair consult; unchanged reviewed design reuse and mechanical follow-through stay GLM; materially changed contracts consult again; critical security/irreversible-data questions consult; task-denied workers return requests; fast/live retain direct ownership/one wrap-up review; human policy, unavailable experts and repeat-without-evidence block or escalate appropriately. Cover all three workflows and use concise rationales.
- [ ] **Step 5: Validate response shape.** Require JSON `decisions` with each case/workflow/actor exactly once and fields `case_id`, `workflow`, `actor`, `route`, `implementation_owner`, `rationale`. Routes: `glm`, `request_consultation`, `expert_advisor`, `human`, `blocked`. Reject missing/duplicate cases, narrative envelopes and claims of actual dispatch/execution.
- [ ] **Step 6: Implement opt-in live execution safely.** Generated config starts with schema, exact GLM model/no variant and global/eval-agent scalar deny permissions. Use `--pure`, fresh sessions, regular-file stdout/stderr, and public export of only the observed own session. Reuse `capture_process`, `own_session`, `parse_capture`, `load_json`, not pilot preparation/trial/recovery. Verify actual model/completion and no tools/delegation/retries. Normal CLI auth stays internal. Exclusive reservations precede calls; failures consume slots. Aggregate run/export elapsed time persists across phases and does not include offline pauses. Keep final-answer rationales, not reasoning parts; preserve failures, no retries.
- [ ] **Step 7: Complete offline tests** for identity/session mismatch, malformed/incomplete output, tools/retries, timeout cleanup, large regular-file output and honest no-effect comparison. Run both helper and existing parser tests, diff checks, self-review and checkpoint assigned files. Independent Task 1 review must pass before live calls.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q scripts/tests/test_eval_opencode_expert_routing.py scripts/tests/test_eval_opencode_pilot.py
git diff --check
```

- [ ] **Step 8: Controller runs five baseline calls before any skill edits.** Verify permitted parent directory, approved helper and unchanged context. Record exact final-answer rationalizations and all outcomes. Baseline noncompliance is evidence, not permission to retry; preserve passing controls as no-effect cases. Infrastructure failure is diagnosed, not a model-quality score or bypass of call limits.

```bash
python3 scripts/eval_opencode_expert_routing.py prepare --repo-root .
python3 scripts/eval_opencode_expert_routing.py run --repo-root . --phase baseline
```

### Task 2: GLM routing, bounded expert and all three workflow integrations

**Files:**
- Modify all existing `.opencode/agents/` files: `adjudicator.md`, `config-auditor.md`, `debug-advisor.md`, `explorer.md`, `fast-dev-reviewer.md`, `fast-dev.md`, `git-integrator.md`, `github-operator.md`, `implementer.md`, `live-dev.md`, `planner.md`, `pr-recovery-operator.md`, `reviewer.md`, `supervisor.md`, `web-researcher.md`, `windows-ci-reproducer.md`.
- Create: `.opencode/agents/expert-advisor.md`.
- Modify: `AGENTS.md`.
- Modify skills: `.opencode/skills/subagent-driven-development/SKILL.md`, `.opencode/skills/systematic-debugging/SKILL.md`, `.opencode/skills/fast-dev-wrap-up/SKILL.md`.
- Modify/test: `scripts/check_opencode_permissions.py`, `scripts/tests/test_check_opencode_permissions.py`.
- Modify docs: `docs/dev/features/opencode-agent-workflow.md`, `docs/dev/notes/opencode-model-pilot.md` (supersession note only for old recommendations; preserve observations).
- Test unchanged Node contracts: `docs/scripts/test-opencode-automation-config.mjs`.
- Consume reviewed helper and controller-supplied baseline facts; do not let workers read external captures.

**Interfaces:**
- Preserve checker `check_repo(repo_root: Path) -> list[PolicyViolation]`, CLI envelope and exit codes.
- Request fields: `decision_scope`, `trigger`, `question`, `sources`, `invariant`, `evidence`, nullable `attempted_fix`, `glm_proposal` (required nonempty for architecture/design/contract decisions, otherwise nullable), `decision_needed`.
- Expert response: `decision_scope`, `status` (`answered`, `insufficient_evidence`, `requires_human`), `finding`, `evidence`, `action`.
- Pending branches: reviewer/adjudicator `status: needs_consultation`, debug-advisor `verdict: needs_consultation`, each with `consultation_request`; implementer existing `NEEDS_CONTEXT`; planner explicit `NEEDS_CONTEXT` exception to final-plan Markdown; observational reviewer pending report retains base/head evidence. Never approve pending requests.

- [ ] **Step 1: Write failing regressions before routing edits.** Cover all sixteen exact GLM pins/no variants, missing/wrong expert model/variant/mode, missing safe repository access or granted operational power, unchanged existing permission sections/capability commands, worker request schemas and controller handlers. Update live-dev GPT/variant fixture expectations without weakening lifecycle assertions.

```python
@pytest.mark.parametrize("name", ORDINARY_ROLES)
def test_ordinary_model(name):
    keys, _ = load_checker()._frontmatter((REPO_ROOT / f".opencode/agents/{name}.md").read_text())
    assert keys["model"] == "opencode-go/glm-5.3-flash"
    assert "variant" not in keys
```

- [ ] **Step 2: Change model pins and add expert.** Existing modes, limits and permissions are unchanged. Expert is a high-variant GPT subagent allowing repository read/glob/grep/list/LSP with sensitive-read exclusions and denying edit/task/bash/external/webfetch/websearch/question. It answers one technical question; no implementation, approval or publication. Extend the existing checker with this named role and model policy using supported frontmatter forms, not a parser redesign; expert is not a wrapper capability.
- [ ] **Step 3: Put canonical triggers/non-triggers in AGENTS.** Every meaningful architecture/design/system-contract decision requires both models, including local designs, not just pilot failure classes. GLM proposes, GPT critiques original evidence, GLM reconciles before dependent implementation. Record the decision and reuse it without repeat consultation until materially changed. Routine execution, first ordinary repair and unchanged-contract follow-through stay GLM; persistent failure and critical questions also trigger advice. Unknown product/policy stays human. Reconcile fast/live's routine-advisor exemption with mandatory dual-model design input while preserving direct edits, local checkpoints, branch prefixes, explicit-only wrap-up and live manual/refresh behavior.
- [ ] **Step 4: Update worker outputs and all controller handlers together.** Include valid pending JSON examples and preserve ordinary schemas. Only task-capable controllers dispatch; workers never gain delegation. Provide original inspectable evidence, one question and decision scope. Resolve/validate material expert findings or escalate; never silently ignore them. Unavailable expert or unanswered necessary decision blocks dependent work. Reconsult only for new material evidence; use existing handoffs/progress, no new tracking subsystem. Capability workers keep verbatim wrapper JSON and expert cannot override refusals.
- [ ] **Step 5: Align process skills and parent transitions.** SDD handles pending report/full/targeted/adjudication requests before normal dispatch; required advice precedes another repair, retaining GLM implementation, independent review and fix caps. Debugging retains its ordinary diagnostic-advisor gate now GLM, not GPT for every fix; handle consultation before confirmed progression. Fast/live wrap-up retains one observational GLM review and direct fixes, no mandatory second full review. Remove stale model tables, stronger-implementer fallback and blanket smarter-model wording. Do not alter commit/publication/queue safety contracts.
- [ ] **Step 6: Document current policy and preserve history.** Update the canonical workflow page with exact coverage, triggers, contracts, limits, authority and restart semantics. Mark pilot conservative routing advice superseded without claiming hybrid/model competence now proven. Record baseline/guidance outcomes and exact behavior limits here, no new developer policy page.
- [ ] **Step 7: Validate and checkpoint before live guidance calls.** Run focused/new regressions and full relevant policy/Node suites; source-search stale ordinary GPT routing/variants and review permissions/output consistency. Self-review and checkpoint, then obtain independent Task 2 review. Existing running-session pins remain old until restart; fresh pressure contexts are explicitly GLM.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q scripts/tests/test_check_opencode_permissions.py scripts/tests/test_eval_opencode_expert_routing.py scripts/tests/test_eval_opencode_pilot.py
make opencode-check
node --test docs/scripts/test-opencode-automation-config.mjs
git diff --check
```

- [ ] **Step 8: Controller runs five guidance calls.** Use same frozen scenarios/schema and updated full context. Read every final rationale and flagged result manually, including baseline-pass/no-effect cases. Verify actual identities and ten-call/aggregate-time ledger. No model competence claims from prompt compliance.

```bash
python3 scripts/eval_opencode_expert_routing.py run --repo-root . --phase guidance
python3 scripts/eval_opencode_expert_routing.py report
```

- [ ] **Step 9: Route any defects through implementer and independent review.** Do not exceed ten calls or pretend old responses validate later changed guidance. If bounded behavioral evidence fails or is exhausted, diagnose and report human input needed for additional validation, not an invented pass. Commit reviewed result documentation with controller-provided facts; rerun focused offline checks.
- [ ] **Step 10: Final whole-branch review and finishing.** Verify committed reviewed content/clean state, fetch/evaluate current `origin/main` through guarded capability agents, safe-merge only if needed, rerun relevant checks and follow normal integration policy. PR CI is the integration gate. Tell user to quit/restart OpenCode after complete changes; no claim that current workers already migrated.

**Acceptance:** Sixteen ordinary project pins GLM/no variants, one exact read-only GPT expert; no permission expansion. All request branches have non-approving controller handling. Every architecture/design/system-contract decision has both model inputs before dependent implementation; unchanged decisions are reused. Supervisor strict ownership and fast/live direct ownership remain distinct. Bounded updated pressure checks show dual-design coverage, escalation and restraint, with missing/failed evidence honestly reported.

**Out of scope:** Global/root/project JSON edits, built-in/hidden role guarantees, automatic model switching, expert implementers, extra full GPT reviews, generic benchmark infrastructure, prior pilot resets, private-data browsing, native/Fennel changes, and extra model trials.

## Subsequent user authorization

The original ten pressure calls were consumed without a passing guidance gate.
The user explicitly approved a separate five-call clarification tranche after
diagnostic review. Only this new tranche is excepted from the original call cap;
the original evidence, oracle, instruction and budget are not reset or rescored.
Use the spec's clarification meanings and predeclared strict acceptance criteria.

### Task 3: Bounded clarification helper, not a policy or oracle rewrite

**Files:**
- Create: `scripts/eval_opencode_expert_routing_clarified.py`.
- Create: `scripts/tests/test_eval_opencode_expert_routing_clarified.py`.
- Reuse read-only: `scripts/eval_opencode_expert_routing.py` and pilot capture/parser primitives.
- No changes to production agents, skills, old helper, old tests or old runtime evidence.

**Interfaces:** fixed CLI `prepare --repo-root .`, `run`, `report`; fixed new root
`/tmp/space/opencode-expert-routing-clarified`; five fresh own sessions only.
The helper reuses the unchanged matrix/schema/oracle and original strict parser;
its frozen instruction appends definitions and a raw-JSON recipe, not case answers.

- [ ] **Step 1: Add failing tests** for unchanged original matrix/schema/oracle, original-evidence byte preservation, strict fenced/malformed JSON rejection, new root rejection before reads, exclusive preparation, five consumed slots/no repeats, and independent 900-second active budget.

```python
def test_fences_still_fail():
    with pytest.raises(ValueError):
        original.parse_answer('```json\n{"decisions": []}\n```')
```

- [ ] **Step 2: Implement the narrow helper.** Reuse file-backed capture, own-session model/completion/tool checks and existing parsing. Generate schema-first all-deny config, preserve normal internal auth, and never browse private data. Freeze the current allowlisted workflow context and the new instruction before calls. Record user authorization, source/packet fingerprints and original experiment metadata hashes; never write to the original root. Use exclusive slots and budget reservation before calls so crashes cannot authorize retries. Keep a separate report, not a new baseline/guidance comparison or hidden retry path.
- [ ] **Step 3: Validate offline and checkpoint for independent review.** Implementer has no external-read authority: all live root preparation/calls remain controller-owned; use mocked/disposable fixtures only.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q scripts/tests/test_eval_opencode_expert_routing_clarified.py scripts/tests/test_eval_opencode_expert_routing.py scripts/tests/test_eval_opencode_pilot.py
git diff --check
```

- [ ] **Step 4: Controller prepares and freezes the separate tranche after review.** Inspect the packet, source/oracle equality, empty results/reservations, strict acceptance and original metadata fingerprints. The definitions clarify the existing contract; do not modify expected answers to match past outputs.
- [ ] **Step 5: Controller invokes exactly five calls.** Each is GLM/no variant/no tools, fresh session, 180-second run-plus-export cap. Preserve every attempt and manually inspect every final rationale. All five strict outputs and all 90 route/owner pairs must pass before calling the behavioral gate green. A failed attempt is not regenerated.

```bash
python3 scripts/eval_opencode_expert_routing_clarified.py prepare --repo-root .
python3 scripts/eval_opencode_expert_routing_clarified.py run
python3 scripts/eval_opencode_expert_routing_clarified.py report
```

### Task 4: Record truthful validation and finish the complete branch

**Files:** update only `docs/dev/features/opencode-agent-workflow.md` and task reports as needed; preserve old pilot observations.

- [ ] **Step 1:** Controller supplies sanitized new outcomes, model identities, strict/manual acceptance, source fingerprints and exact failures to the repository-only implementer. State old baseline/guidance failures and the new protocol separately. Do not claim causal improvement or effective routing in an already-loaded session.
- [ ] **Step 2:** Implementer updates documentation, runs relevant checks, self-reviews and checkpoints. Independently review the complete pending results/documentation range. No further policy edits may be silently attributed to already-recorded responses.
- [ ] **Step 3:** Perform final whole-branch review, fetch/evaluate current `origin/main`, and run `make opencode-check`, relevant helper/parser pytest suites, Node workflow contracts and diff checks. No native build or candidate code execution. Follow guarded integration/merge-queue policy only when required checks and behavioral acceptance are green. Tell the user to quit/restart OpenCode after the reviewed rollout.

## User-approved delivery-contract addendum

The user approved a fail-closed, one-original-author correction path after the
clarification tranche remained4/5. The spec's “User-approved fail-closed delivery
contract” at989261a records actual GLM proposal and GPT critique/reconciliation.
Tasks5–7 prospectively validate this new contract instead of perfect first replies;
oldten/five failures stay failed. Model pins, permissions and mandatory both-model
design input remain unchanged. No plugin or hard runtime-enforcement claim.

New validation allowance: five short fresh baseline microcontexts before handoff
guidance edits, five with-guidance contexts afterward, each at most120s, plus one
original-author format-correction generation at most180s including exports.
Maximum11 validation generations, no retries/resampling. The recorded design GLM
consultation is separate. Controller owns all actual calls/runtime reads; workers
use mocks and supplied facts only. New runtime is `/tmp/space/opencode-handoff-delivery`.

### Task 5: Small delivery-state validator/replay helper and baseline

**Files:**
- Create: `scripts/eval_opencode_handoff_delivery.py`.
- Create: `scripts/tests/test_eval_opencode_handoff_delivery.py`.
- Reuse read-only: existing capture, strict matrix parser and context helpers.
- No role/skill/AGENTS guidance changes yet; old helpers and evidence untouched.

**Interfaces:**
- `evaluate_delivery(case: dict) -> dict`: explicit fixture state evaluation, not a universal production schema engine. Inputs include stable handoff identity, previous correction count/state, declared-format validity, scope/fact preservation, author availability and excluded-role facts. Outputs retain identity/count and yield `FORMAT_REPAIR_REQUIRED`, `ELIGIBLE_FOR_NORMAL_HANDLING` or `BLOCKED`, with reasons.
- Fixed controller-invoked CLI `prepare --repo-root .`, `micro --phase baseline|guidance`, `replay`, `report`. Preparation/model calls never run implicitly during tests.
- Runtime artifacts contain frozen source/scenario/rubric snapshots, reservations, captured final text and evidence hashes; exclude private reasoning from summaries.

- [ ] **Step 1:** Write failing tests for initial-valid normal handling; initial malformed ordinary report with unused correction; valid fact-preserving correction after one request; invalid correction exhaustion; duplicates/renaming/staleness not resetting counters; changed facts/verdicts/base/head blocking; original author unavailable; JSON and intentionally Markdown contracts; excluded GPT/wrapper rewriting; and no approval from delivery eligibility.

```python
def test_invalid_correction_blocks_without_second_request():
    result = delivery.evaluate_delivery({"identity": "stable-scope", "repair_used": 1,
        "payload_valid": False, "scope_current": True, "facts_preserved": True,
        "author_available": True, "excluded": False})
    assert result["state"] == "BLOCKED"
    assert result["repair_used"] == 1
```

- [ ] **Step 2:** Implement the smallest explicit fixture assessor and opt-in driver. Reuse safe file-backed capture/own-session checks and original matrix parser for matrix-shaped replay only; do not generalize it to every role. Reject out-of-scope/symlink paths before reads, use schema-first tool-denied config, preserve normal CLI-internal auth, and never inspect home/auth/private logs/databases.
- [ ] **Step 3:** Freeze one concise five-scenario question bundle and full relevant old workflow context before any handoff-guidance changes. Each of five fresh contexts sees initial malformed delivery, exhausted correction, changed/stale facts, valid correction still awaiting semantic review, and expert/wrapper exclusions plus direct-primary/lifecycle constraints under deadline/sunk-cost/authority pressure. Ask plain routing explanations; expected actions remain evaluator-only. Same bundle/context assignments are used after guidance, with updated sources only. These are policy-understanding checks, not first-response JSON scoring.
- [ ] **Step 4:** Add mocked call/accounting tests: five slots per microphase, one replay generation, no duplicate calls/reset/resume loophole,120s/180s limits, actual GLM/no variant/tools checks, source/packet freezing and historical snapshots untouched. A failed attempt consumes its slot. Preserve final explanations without reasoning text; no automatic efficacy/causality claim.
- [ ] **Step 5:** Implement the bounded replay preparation. It may publicly export only retained own GLM session `ses_e8a4fd4a1ffeg08U1O1gJVbwTD`, retain original assistant IDs/content and canonical request metadata, and authorize only the demonstrated workflow scalar correction. No other field, route, owner, rationale, verdict, evidence or range may change. Preserve all saved historical files and scores. If author/source/facts cannot be verified, record blocked without a generation.
- [ ] **Step 6:** Tests and independent review precede controller calls.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q scripts/tests/test_eval_opencode_handoff_delivery.py scripts/tests/test_eval_opencode_expert_routing.py scripts/tests/test_eval_opencode_expert_routing_clarified.py scripts/tests/test_eval_opencode_pilot.py
git diff --check
```

- [ ] **Step 7:** After review, controller verifies the permitted parent, prepares fixed runtime, runs the five baseline contexts and reads every final explanation before Task6 guidance edits. Record failures and already-compliant controls verbatim. No claim of improvement where baseline already complies; preserve any missing/failed evidence.

### Task 6: Canonical fail-closed handoff rule and all-controller hooks

**Files:**
- Modify: `AGENTS.md` canonical delivery subsection.
- Modify: `.opencode/agents/supervisor.md`, `fast-dev.md`, `live-dev.md` controller hooks.
- Modify ordinary author prompts only where needed: `implementer.md`, `planner.md`, `reviewer.md`, `debug-advisor.md`, `adjudicator.md`, `fast-dev-reviewer.md` under `.opencode/agents/`.
- Modify short parent references in `.opencode/skills/subagent-driven-development/SKILL.md`, `.opencode/skills/systematic-debugging/SKILL.md`, `.opencode/skills/fast-dev-wrap-up/SKILL.md`.
- Modify/test: `scripts/tests/test_check_opencode_permissions.py` and new delivery tests; existing checker code only if a concrete policy-regression need requires it, not to add report parsing.
- Modify: existing `docs/dev/features/opencode-agent-workflow.md`; no duplicate policy page.

**Contract:** stable task/author/controller/branch/source/base-head/mode identity,
immutable original, one separate correction counter, original-author format-only
no-operation assignment, unchanged facts and role format, eligible-not-approved
normal handling, blocked second/stale/changed/unsupported delivery. GPT advice
and capability wrapper outputs stay outside this repair path.

- [ ] **Step 1:** Add failing source-contract regressions before guidance edits: all3 parent hooks, ordinary author format-only exception to code/test/commit obligations, one correction per stable scope, no counter reset, excluded outputs, valid correction returning to ordinary handlers, and preserved model/permission/consultation/direct-primary contracts.
- [ ] **Step 2:** Add the canonical rule in AGENTS and short pointers from parents/authors. Validate declared JSON/Markdown formats, not a universal routing field. Mark correction allowance spent before dispatch; resume the original worker with existing facts and precise delivery errors. Do not strip fences, alias fields, default pass, salvage partial verdicts or change scope/SHAs. Missing reconstructable facts uses the role's existing context/evidence-needed or non-approving branch (NEEDS_CONTEXT only where supported), not invented content. Format-only is an assignment mode; do not add it or delivery-state bookkeeping as an extra field to existing worker response schemas.
- [ ] **Step 3:** Wire delivery validation before consultation/verdict/fix/cap/completion transitions. It is not a substantive code-fix round, new expert consultation, second whole-branch review or authority grant. Fast/live remain direct; report-only repair triggers no live app setup or refresh. Preserve normal semantic review and all finishing gates after eligible delivery.
- [ ] **Step 4:** Document the prospective user-approved contract, observed historical failures, stable bookkeeping and runtime-enforcement limitations. Old failed gates remain historical facts, not silently waived successes. Run source/permission/Node guards, self-review, checkpoint and obtain independent review before with-guidance calls.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q scripts/tests/test_check_opencode_permissions.py scripts/tests/test_eval_opencode_handoff_delivery.py
make opencode-check
node --test docs/scripts/test-opencode-automation-config.mjs
git diff --check
```

- [ ] **Step 5:** Controller runs five new with-guidance microcontexts using the same questions/rubric and manually reads every explanation. Require correct reject/one-author-repair/eligible-normal-handler/block behavior and retained authority; do not score free-form analysis as serialized report delivery or claim model competence.
- [ ] **Step 6:** Controller performs at most one original-author repair generation using CLI `--session` on the verified retained own session, all tools denied,180s including pre/post exports. Explicitly request only correction of the workflow scalar to original request metadata, preserving other values exactly. This is a new delivery-repair record, not an old trial rerun or fresh comparison sample.
- [ ] **Step 7:** Select only the new assistant message ID observed in run NDJSON and absent from the pre-export. Verify provider/model/completion/tool absence; never concatenate old and new answers. Verify old assistant contents and historical snapshot inventories unchanged, disclose the intentional server-session append. Parse and compare protected content strictly. Valid preserved correction yields only `ELIGIBLE_FOR_NORMAL_HANDLING`; otherwise `BLOCKED` with no second generation. Deterministic fixtures demonstrate exhaustion without extra live calls.

### Task 7: Record prospective acceptance and finish the complete rollout

**Files:** update `docs/dev/features/opencode-agent-workflow.md` and task reports; generated evidence stays in the fixed runtime root.

- [ ] **Step 1:** Controller supplies sanitized baseline/guidance assessments, repair success or failure, state trace, model identities, counts, timings and immutable-history checks to the repo-only implementer. Record actual blocked/repaired delivery separately from correctness of fail-closed handling. A safe blocked trace is not a repaired or approved task.
- [ ] **Step 2:** Implementer documents results and limitations, validates text/count consistency, self-reviews/checkpoints; independently review complete result changes. Old ten/five trials remain failed. No policy changes after testing may be attributed to earlier answers.
- [ ] **Step 3:** Final whole-branch review covers all rollout, helper, guidance and evidence changes. Resolve material defects through implementer/reviewer without unapproved new model calls. Required prospective gates are correct fail-closed traces, preserved inputs/authority/budgets, passing deterministic/source checks and acceptable manual with-guidance decisions—not perfect first-response formatting.
- [ ] **Step 4:** Fetch/evaluate current `origin/main` through guarded integration wrappers, safe-merge when needed, preserve unrelated work and rerun focused Python/policy/Node/diff checks on a clean tree. No native/Fennel build. Follow default push/PR/merge-queue policy through actual merge only when required gates pass; then tell the user to quit/restart OpenCode. Do not claim this session already migrated.
