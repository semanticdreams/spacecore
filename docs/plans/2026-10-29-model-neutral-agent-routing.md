# Model-Neutral Agent Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all project roles to the requested model/effort inputs while making future routing changes configuration-only.

**Architecture:** One atomic task updates the checker, all role configs, active instructions, current contract tests and canonical documentation. Routing syntax validation is independent of role safety; consultation is evidence-triggered, not based on model family. Historical protocols remain unchanged.

**Tech Stack:** Markdown frontmatter/prompts, Python checker and pytest. No engine/Fennel/build work.

**Spec:** `docs/specs/2026-10-29-model-neutral-agent-routing-design.md`.

## Global Constraints

- Keep agent modes, step budgets and complete permission blocks unchanged.
- Both `model:` and `variant:` frontmatter lines are authoritative and may later be edited independently without checker/policy/test pin changes.
- Do not maintain a provider/model allowlist, role-tier table or equality relationship between roles.
- Maintain an explicit required inventory of all 17 existing project roles separately from configurable pins.
- Rename the canonical request field `glm_proposal` to `proposal` atomically across active examples, workers, controllers and tests; no compatibility alias.
- Keep strict implementer -> independent reviewer -> pass, diagnostic-advisor confirmation, fix caps/adjudication, checkpoint ownership, clean-tree and integration/merge-queue gates.
- Fast-dev/live-dev retain direct ownership and their one observational whole-branch wrap-up review.
- Preserve historical specs/plans/progress, captured handoffs, experiment results, and the existing model-pilot/expert-routing/handoff-delivery evaluation protocols and tests byte-for-byte.
- Restart OpenCode to activate the new instruction snapshot and schema; do not retrofit retained old handoffs into the new schema or claim this running session has switched models.
- Controller owns the durable ledger. Implementer owns ordinary validated/self-reviewed local checkpoints, not publication.
- No home/global config, dependency, runtime, capability permission or workflow CI changes.

---

### Task 1: Atomic model-neutral configuration and consultation migration

**Files:**
- Modify: all 17 `.opencode/agents/*.md` definitions.
- Modify: `AGENTS.md`.
- Modify: `.opencode/skills/subagent-driven-development/SKILL.md`.
- Modify: `.opencode/skills/systematic-debugging/SKILL.md`.
- Modify: `.opencode/skills/fast-dev-wrap-up/SKILL.md`.
- Modify: `scripts/check_opencode_permissions.py`.
- Modify: `scripts/tests/test_check_opencode_permissions.py`.
- Modify: `scripts/tests/test_opencode_handoff_delivery_contract.py` where model-branded text assertions need neutral wording.
- Modify: other already-wired current-policy tests only if exact active-contract wording must change; preserve their invariant strength.
- Modify: `docs/dev/features/opencode-agent-workflow.md` active policy and supersession notes only.
- Do not modify: `scripts/eval_opencode_*.py`, `scripts/tests/test_eval_*.py`, old specs/plans/captures/pilot notes.

**Interfaces:**
- Consumes: reconciled spec and original checker `_frontmatter`, `_check_agents`, `_check_expert_profile`, `check_repo`, fixture helpers and preservation tests.
- Produces: explicit model/variant scalar validation for every agent; required-role inventory validation; separate unchanged expert safety check; canonical request `proposal` field and targeted role-based consultation.
- Preserve existing violation/report contracts where appropriate; new malformed-routing and missing-role diagnostics must be explicit and regression-tested.

- [ ] **Step 1: Capture baseline before prompt edits.** Controller records BASE and original source-policy probes for all three skills, with cases: routine design/no trigger; same failure after one repair; strict ownership versus fast/live wrap-up under deadline pressure. Current source demands advice for routine confident design, the behavior intentionally changing. Preserve original tool deliveries privately; track safe summaries in the ledger.

- [ ] **Step 2: Add failing routing tests.** Update existing fixtures to synthetic model/variant inputs and a complete required-role inventory without altering role safety profiles. Replace exact model pin assertions with syntax/independence tests. Example inputs for parametrization:

```python
VALID_ROUTING = [
    ("example-provider/model-a", "medium"),
    ("other-provider/model-b", "high"),
    ("third-provider/model-c", "custom-effort"),
]
INVALID_MODELS = ["", "model-only", "/model", "provider/", "a/b/c", "a /b", "[]", "{}"]
INVALID_VARIANTS = ["", "high medium", "[]", "{}", "true", "null", "123"]
```

Use real checker calls on fixture repositories. Cover quoted valid scalar strings,
missing fields, whitespace, YAML lists/maps/non-string scalar shapes, every missing
required role, and independent changes to expert/ordinary/future-role model and
variant inputs. Keep exact permission/mode/steps preservation tests unchanged.
No permanent test may pin the requested production model or initial effort table.

- [ ] **Step 3: Add failing active-contract tests.** Rename current schema assertions to `proposal`; test active worker pending/resumption and neutral role wording. Assert ordinary design does not automatically require consultation, repeated material failure still does, and strict/fast/live review distinctions remain. Scope neutral-text checks to agent bodies, current AGENTS policy and the three skills; canonical docs checks must exclude historical evidence and compatibility anchors. Do not turn historical provenance into a new pin assertion. Run focused tests against unchanged implementation/prompts and record expected RED failures.

- [ ] **Step 4: Implement syntax-only routing validation.** Remove exact ordinary/expert model and high-effort comparisons. Add explicit required inventory of the 17 named project agents. Validate explicit scalar provider/model and variant token configuration for every agent, including future roles; reject missing/blank/malformed/non-scalar shapes with useful diagnostics. Keep implementation small and dependency-free using existing parser conventions; do not treat `[]`, `{}` or non-string scalar shapes as valid merely because they lack whitespace. A syntax pass does not verify provider/variant availability. Separate expert model/variant validation from its exact mode/permission safety predicate, preserving all existing sensitive-read exclusions and ordering.

- [ ] **Step 5: Apply the supplied config inputs.** Set each role's model line to the exact user-requested value supplied in the handoff. Initial high: supervisor, fast-dev, live-dev, planner, reviewer, fast-dev-reviewer, debug-advisor, adjudicator, expert-advisor. Initial medium: implementer, explorer, web-researcher, config-auditor, git-integrator, github-operator, pr-recovery-operator, windows-ci-reproducer. Change no other frontmatter keys except expert's model-neutral description. Controller verifies all 17 actual inputs as one-time evidence; tests must permit later config-only changes.

- [ ] **Step 6: Migrate the active instruction contract.** Remove model IDs/family assumptions from AGENTS, role bodies, role tables and three skills. Replace mandatory every-design consultation with the spec's three evidenced triggers, optional bounded consequential-uncertainty advice, ordinary evidence-backed design rationale, and human-owned product/API/data policy. Reuse prior advice only when applicable; do not recreate universal consultation on material changes without a current reason. Rename `glm_proposal` to `proposal` across active schema/examples/tests without aliases. Preserve role-based delivery exclusions, immutable originals, correction/recovery budgets, pending statuses, original-worker resumption, diagnostic confirmation and independent approval. Expert prompt/description changes, but permission/mode/steps do not. Update active links to a neutral AGENTS consultation heading. Compatibility anchors may preserve historical links without constituting normative model instructions.

- [ ] **Step 7: Update canonical docs without rewriting evidence.** Explain frontmatter authority, targeted triggers/schema, unchanged safety and restart requirements in `docs/dev/features/opencode-agent-workflow.md`. Sweep other current normative paragraphs on that page for stale mandatory dual-model language. Preserve historical trial/evidence sections and results byte-for-byte, explicitly label superseded protocol scope and avoid review-quality equivalence claims. Do not scrub old request fields or model identities from history.

- [ ] **Step 8: Run GREEN and diff checks.** Execute:

```bash
python3 -m pytest scripts/tests/test_check_opencode_permissions.py scripts/tests/test_opencode_handoff_delivery_contract.py scripts/tests/test_opencode_handoff_recovery_contract.py -q
make opencode-check
git diff --check
git diff --stat
git status --porcelain
```

The explicit delivery-contract module is not part of the current Makefile target,
so run it separately. Compare permission/mode/steps against BASE, verify all 17
inputs, and inspect the complete diff to prove frozen scripts/tests/historical
records did not change. No `make build`, engine suite or Fennel checks apply.

- [ ] **Step 9: Self-review and checkpoint.** Inspect status, full diff, staged diff and recent commit style. Commit only assigned changes with a conventional subject such as `refactor(workflow): Make agent routing configuration-only`. Report checkpoint SHA, complete files, RED/GREEN evidence, coverage rationale, preserved safety proof and any concerns. Do not edit controller ledger, push, create PR or integrate.

- [ ] **Step 10: Controller probes and independent review.** Controller repeats the same source-policy scenarios against the new source and records observations/limits. This evaluates instruction clarity, not loaded-role or runtime model activation. Dispatch independent reviewer over complete BASE..HEAD plus spec/plan and validation. Route accepted fixes through implementer/reviewer and complete finishing only after pass.

## Acceptance and validation scope

All requested inputs are present in the 17 configs, but instructions and checker
remain model-neutral. Alternate valid model/variant strings work without policy
edits. Complete inventory, exact safety, targeted mandatory consultation, pending
worker verdict ownership and existing strict/direct workflows are covered.
Legacy schema remains only in preserved history/frozen protocols, not active
requests. Focused Python/contract checks and `make opencode-check` are the relevant
local gate; PR CI is the integration gate. Fetch/evaluate current origin/main,
clean-tree checks, guarded publication and merge-queue polling follow independent
approval. No runtime behavior or equivalent defect-detection claim is authorized.
