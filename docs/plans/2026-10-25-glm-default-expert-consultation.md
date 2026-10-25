# GLM-Default Expert Consultation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use GLM for ordinary project agents in supervisor, fast-dev and live-dev, reserving GPT for bounded difficult/critical questions.

**Architecture:** Change all sixteen project-agent pins and add one read-only expert. Preserve authority and workflow ownership, with explicit pending-consultation outputs and controller handling. A small opt-in pressure helper freezes five baseline contexts before skill edits and runs five updated contexts after independent review; no new benchmark platform or candidate code execution.

**Tech Stack:** OpenCode Markdown/YAML agents and skills; Python stdlib/pytest; existing Node workflow-contract tests.

## Global Constraints

- Authoritative spec: `docs/specs/2026-10-25-glm-default-expert-consultation-design.md`.
- All sixteen existing project roles use exactly `opencode-go/glm-5.3-flash`, without GPT-specific variants.
- Only new `expert-advisor` uses `openai/gpt-6.1-sol`, variant `high`, read-only subagent.
- Project/root OpenCode JSON and home configuration remain untouched; inherited built-in/hidden/global agents are outside coverage. Use project-defined explorer/workers rather than implicit model fallback.
- Preserve existing permissions, delegation denials, capability commands, publication/checkpoint authority and independent review.
- One consultation per decision scope; reconsultation requires genuinely new material evidence. No expert implementer or automatic full GPT review.
- Ten fresh GLM validation calls maximum: five baseline before any skill edits and five guidance afterward. No retries or extra GPT trials.
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
- [ ] **Step 4: Encode all workflow/skill pressure cases.** Every fresh context answers the same matrix with time, sunk-cost and authority pressure: first syntax repair/TDD RED stays GLM; retained-state alias or fallible-save-after-detach consults; same material failure after one repair consults; ordinary architecture work stays GLM; critical unresolved security/irreversible-data question consults; task-denied worker requests controller handling; fast/live keep direct ownership and one observational wrap-up review; unknown product policy/unavailable expert/repeated question without evidence has human/blocked disposition, not a consultation loop.
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
- Request fields: `decision_scope`, `trigger`, `question`, `sources`, `invariant`, `evidence`, nullable `attempted_fix`, `decision_needed`.
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
- [ ] **Step 3: Put canonical triggers/non-triggers in AGENTS.** Use the four spec predicates, not all architecture or all important work. First ordinary repair stays GLM; same material failure after a repair triggers advice. Unknown product/policy stays human. Explicitly reconcile fast/live's routine-advisor exemption with this narrow consultation policy while preserving direct edits, local checkpoints, branch prefixes, explicit-only wrap-up and live manual/refresh behavior.
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

**Acceptance:** Sixteen ordinary project pins GLM/no variants, one exact read-only GPT expert; no permission expansion. All request branches have non-approving controller handling. Supervisor strict ownership and fast/live direct ownership remain distinct. Bounded updated pressure checks show both escalation and restraint, with missing/failed evidence honestly reported.

**Out of scope:** Global/root/project JSON edits, built-in/hidden role guarantees, automatic model switching, expert implementers, extra full GPT reviews, generic benchmark infrastructure, prior pilot resets, private-data browsing, native/Fennel changes, and extra model trials.
