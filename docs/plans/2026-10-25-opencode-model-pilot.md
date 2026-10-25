# Space Fennel Model Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare GLM and GPT on real Space Fennel architectural judgment and clean implementation, including a GPT-design/GLM-execution split.

**Architecture:** Freeze four repository-backed reasoning packets and one Sized implementation brief. A small standard-library Python script invokes eleven fresh tool-denied CLI sessions, verifies their own public exports, and retains inert responses; fresh independent GPT reviewers assess anonymized outputs. Candidate code is never run or applied.

**Tech Stack:** Python standard library and unittest for orchestration only; OpenCode CLI 1.18.35; actual Space Fennel source and focused tests as evaluation context; JSON/Markdown evidence.

## Global Constraints

- Follow `docs/specs/2026-10-25-opencode-model-pilot-design.md`, including the user's static-analysis clarification.
- Exact candidates: `opencode-go/glm-5.3-flash` and `openai/gpt-6.1-sol`.
- Do not change production agent definitions or model routing during this pilot.
- Preserve normal internal CLI subscription authentication; never inspect/copy auth files, home configuration, private logs, credentials, or databases.
- Python may orchestrate calls and evidence; it is not the evaluated language.
- Load space-fennel, space-fennel-ui, and space-testing-runtime guidance.
- Freeze prompts, source hashes, seeded answers, rubric, and contract before candidate calls.
- Use fresh all-deny trial agents under `/tmp/opencode`, outside repository ancestry; no model tools, delegation, or continuation.
- Export only sessions created by the pilot. Verify actual provider/model and completion; never fall back to another model.
- Keep raw exports and captures outside version control. Commit sanitized final answers, not private reasoning parts.
- Never apply, compile, import, or execute model-generated Fennel. Do not build Space.
- Candidate validation is explicitly static-only; assess proposed tests and native validation knowledge without inventing execution evidence.
- Eleven primary candidate calls; at most two architecture repeats and one repeat judgment under the spec's conditional rule.
- Per-call deadlines: reasoning 180 seconds; implementation 360 seconds. Persist a 90-minute overall model execution deadline.
- No repair conversations, silent retries, or best-of-N selection.
- Missing usage stays unknown. Reported zero cost does not prove zero subscription cost; no financial-savings claims.
- PR CI is the integration gate for any landed orchestration tooling.

## Files and responsibility boundaries

- `scripts/eval_opencode_pilot.py`: thin fixed-purpose preparation/invocation/export/evidence utility, not a framework.
- `scripts/evals/opencode_pilot_cases.json`: frozen public briefs, source references/hashes, review mutations, evaluator-only answers, static vectors, rubric, and Sized contract.
- `scripts/tests/test_eval_opencode_pilot.py`: offline mocked unittest coverage.
- `docs/dev/notes/opencode-model-pilot.md`: procedure, findings, responsibility recommendation, and limitations.
- `docs/dev/notes/opencode-model-pilot/2026-10-25/records.json`: sanitized trial and scoring evidence.
- `docs/dev/notes/opencode-model-pilot/2026-10-25/responses.md`: complete sanitized final responses, including inert returned Fennel.
- `docs/dev/notes/opencode-model-pilot/2026-10-25/judgments.md`: independent anonymized judgments and unblinding map after scoring.

No production `.fnl` file is edited. No new native acceptance harness is needed because candidate code execution is out of scope.

---

### Task 1: Freeze and review the packets and minimal runner

**Files:** Create runner, cases JSON, mocked tests, and procedure page listed above.

**Interfaces:**

- `prepare(repo_root: Path, run_root: Path) -> dict`: capture pinned public source and packet hashes beneath a new run root, without model calls.
- `run_trial(trial: dict, run_root: Path, overall_deadline: float) -> dict`: one subprocess/session and its own export, no retries.
- `parse_capture(ndjson: str, exported: dict, expected_model: str, owned_session_id: str) -> dict`: verified completion, identity, final text, and usage.
- `parse_files(answer: str) -> dict[str, str]`: inert JSON containing exactly `assets/lua/sized.fnl` and `assets/lua/tests/test-sized.fnl`; never writes them.
- CLI: `prepare --repo-root . --run-root <new-root>` and `run --run-root <root>`; individual-trial execution may be supported only with a persistent reservation/deadline ledger.

- [ ] **Step 1: Write failing offline tests.** Use `unittest` and synthetic NDJSON/export objects; no model calls. Cover actual model mismatch/missingness, wrong own-session ID, incomplete/error output, malformed JSON, tool calls, duplicate usage, timeouts, no retry, private-answer exclusion, and path allowlisting. Initial examples:

```python
def test_unsafe_implementation_path(self):
    with self.assertRaises(ValueError):
        pilot.parse_files('{"files":{"../../outside.fnl":"x"}}')

def test_contract_arms_share_packet(self):
    packets = pilot.prepare(self.repo_root, self.fresh_run_root)
    self.assertEqual(packets['contract_gpt_sha256'],
                     packets['contract_glm_sha256'])
```

- [ ] **Step 2: Run the new unittest module and observe the initial failure**, then implement only the fixed-purpose runner needed for these cases.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/tests -p 'test_eval_opencode_pilot.py' -v
```

- [ ] **Step 3: Freeze public source at `d6e3742`** (all evaluated Fennel unchanged since that commit). Include `tab-view.fnl`, `search-view.fnl`, `sized.fnl` and their actual focused tests. Include short relevant helper excerpts from Layout, Flex, Input/InputModel, and Signal so ownership judgments are verifiable. Hash blob/excerpt and rendered packet bytes. Do not send historical worked solutions or evaluator-only answers to candidates.

- [ ] **Step 4: Freeze four public reasoning briefs and private expectations.**
  - TabView: opt-in retained logical state with static items; preserve widget rebuilding, existing index/button/events, per-built-instance state, and explicit state versus widget ownership. Accept multiple clean bounded APIs, not one preferred spelling.
  - SearchView: neutral labels for layout-only teardown, recursive double-drop, a fixture-only long-lived external signal disconnected from the wrong source, and a matched sound cleanup. Supply the external source lifetime. Do not falsely seed a lasting input-signal leak merely by omitting redundant disconnect: InputModel.drop clears its signals.
  - Escalation: dynamic tab updates, duplicate/absent IDs, external state changes with undefined identity/ownership/precedence. Reward specific missing decisions and safe bounded work, not invented policy or refusal of everything.
  - Handoff: an inert Sized setter patch updates ordinary/constrained wrapper measurement but leaves `resolve-child-max` using constructor `opts.size`. Supply original tests and a clearly synthetic author claim of completion; no fake runtime transcript. Expected finding is stale child constraints and absent relevant coverage.

- [ ] **Step 5: Freeze the implementation public brief and static vectors.** Add canonical `set-size`, changing both wrapper measurement paths and child-max resolution, marking the wrapper measure dirty, keeping child identity, shared-option independence, and direct layouter transforms. Preserve original tests; ask for focused proposed tests. Vectors include current size `[7,0,-2]` with parent max `[20,30,40]` giving child max `[7,30,40]`, no-parent fallback using current size, repeated updates, wrapper dirtiness, and two builds sharing options. These are requirements for static assessment, not executed assertions.

- [ ] **Step 6: Freeze an independently reviewed GPT-authored contract.** The contract gives owning abstraction, affected measurement paths, ownership/compatibility constraints, scope, and test requirements, but no code/reference implementation. Compare GLM plain brief against GPT and GLM receiving this identical contract. All arms receive identical public requirements/source. Require final JSON with two complete source strings and notes that clearly distinguish proposed validation from executed evidence.

- [ ] **Step 7: Freeze schedule and rubric.** Four reasoning cases times two models, plus `sized-glm-plain`, `sized-gpt-contract`, `sized-glm-contract`: eleven calls total. Alternate candidate order across cases. GPT requests `xhigh` reasoning and `high` implementation; do not assume GLM supports these variants. Record requested/sent/reported values and variant uncertainty. Rubric dimensions, scored 0–4: architecture/design 35%, correctness/invariants 30%, validation 15%, scope/escalation 10%, evidence accuracy 10%. Material defects/fabricated evidence remain explicit regardless of aggregate score.

- [ ] **Step 8: Implement fresh tool-denied CLI sessions.** Generated explicit agents and global permission use the supported all-deny form; invocation is `opencode run --format json --agent <pilot-agent> --model <exact-id> [--variant <supported>] --file <packet> <fixed-instruction>`. Run from the generated control directory, not repo ancestry. Suppress external plugin/skill discovery where supported without copying/browsing auth. Record ambient-config limitations. Do not inspect merged home config, auth storage, session lists, private logs, or databases.

- [ ] **Step 9: Implement capture/export accounting.** Reserve each trial exclusively before invocation. Persist the overall deadline. Timeout cleans up the process group and produces a timeout outcome with no retry. Observe own session ID in that subprocess's NDJSON, then `opencode export <that-id>`. Verify assistant provider/model, completion and errors; tool calls are protocol violations. Use one authoritative per-message usage representation, preserving null/zero and cache/reasoning fields without double counting. Extract final text only, no reasoning parts. Parse returned implementation files as inert data; reject duplicate/missing/extra/unsafe keys.

- [ ] **Step 10: Run all offline tests and prepare packets without generative calls.** Confirm exact schedule, source/contract equality, private-key exclusion, no model call on preparation, hashes, and no `.fnl` writes. Document the procedure and empty-results status. Run JSON parse and diff checks. Self-review and checkpoint only assigned files. Independent reviewer must pass the complete Task 1 range before any candidate call.

---

### Task 2: Run comparisons and independently review evidence

**Files:** Modify procedure/results page; add the three evidence files listed above. Runner/cases remain frozen; collection fixes require reviewed changes, not silent prompt tuning.

**Interfaces:** Consume Task 1's approved hashes and reservation ledger. Produce trial records, anonymized response packets, judgments, and qualified recommendations. Each trial records requested/actual model, variants, session ID, source/prompt/contract hashes, outcome/error, wall time, available usage/cost, capture hashes, and `static-only` for implementations.

- [ ] **Step 1: Verify approved hashes and run the first architecture pair.** These are the live authentication/identity checks, not extra smoke calls. CLI-internal auth is allowed. Stop on actual authentication/identity failure rather than browsing auth or falling back. A provider failure is infrastructure evidence, not an architectural score.
- [ ] **Step 2: Run the remaining six reasoning calls and three implementation calls**, with fresh sessions and deadlines, exact frozen packets, no clarifying answers/repair loops. Preserve every attempt/outcome, including truncation, timeout, invalid implementation JSON, or provider errors.
- [ ] **Step 3: Collect sanitized complete final answers and compact records.** Keep large raw captures/exports outside version control. Check for secrets/private paths and preserve substantive mistakes. Create anonymized labels/order with no model/arm/timing/usage hints in reviewer packets; keep the map sealed until judging completes.
- [ ] **Step 4: Dispatch five fresh independent GPT evaluation reviewers**, one per reasoning pair and one for all three implementation arms. Give each frozen source/requirements, rubric, private expectations, static vectors, and the explicit no-runtime-evidence status. Require dimension scores, concrete findings, false positives against sound controls, material-defect/fabrication flags, confidence and limits. Separate evaluation judging from implementation-code review gates. Record the reviewer agent/config provenance and same-family bias; do not claim public-export identity verification for a subagent when unavailable.
- [ ] **Step 5: Apply the repeat rule only if warranted.** If the initial architecture gap is at most five points or judgment confidence is low, and enough budget remains, run one fresh pair with original packets and at most one new judgment. Preserve originals; no other repetitions or preferred-result selection. Otherwise explicitly record no repeat.
- [ ] **Step 6: Write the evidence-backed responsibility recommendation.** Distinguish architectural origination, patch review, escalation, evidence checking, and bounded implementation. Compare plain/hybrid GLM; report where a GPT contract helped or did not. Preserve strong architecture/review gates unless evidence supports otherwise; no automatic production routing changes. Explain small sample, static-only Fennel, fixed context, no tools/repair loops, judge bias and imperfect blinding. No subscription savings estimates from unknown billing.
- [ ] **Step 7: Validate records and rerun offline tests**, JSON parsing and diff checks. Reconcile eleven planned calls, any conditional repeats, every own-session export and all outcomes. Do not invent quality scores for infrastructure failures or missing judgments. Native compile/constraints/tests are not run by design; constraint impact is not applicable because production Fennel is unchanged.
- [ ] **Step 8: Checkpoint sanitized results and obtain independent full Task 2 review** for count/hash integrity, evidence accuracy, reporting limitations and recommendation support. Fix documentation/collection defects through implementer and independent review; no extra candidate experiments without new authorization.

## Finishing

After all changes pass independent review, use finishing-a-development-branch.
Verify committed reviewed content and a clean tree, fetch/evaluate current
`origin/main` through the capability agent, rerun focused orchestration tests,
and follow project integration policy. No Space build or candidate execution is
part of this static analysis task. PR CI remains the integration gate; do not
equate evaluation findings with permission to change production agents.
