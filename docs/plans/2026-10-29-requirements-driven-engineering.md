# Goal-aware requirements-driven engineering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the reviewed [requirements-driven design](../specs/2026-10-29-requirements-driven-engineering-design.md), including native requirements, typed traceability, evidence, reconciliation, autonomous workflows, scenarios, documentation and safeguarded actual merge.

**Architecture:** One Git-native JSON ledger and a small standard-library Python library/CLI; Markdown indexes are derived projections. Existing agents perform semantic reconciliation and reviews, while deterministic tooling validates and queries recorded data. Canonical mutations remain implementer-owned in strict flow.

**Tech Stack:** Python standard library, pytest, Node/VitePress, existing OpenCode Markdown roles/skills and guarded Git/GitHub wrappers.

## Global Constraints

- The reviewed design is authoritative; this plan does not introduce a parallel requirements system.
- Canonical `docs/requirements/ledger.json`; deterministic `docs/requirements/index.md` projection; no historical bulk migration or fabricated requirements.
- Opaque immutable `REQ-<uuid>` requirement IDs and `ART-<uuid>` artifact IDs independent of classification/location; five initial classifications without a fixed hierarchy.
- Lifecycle `proposed`, `active`, `superseded`, `rejected` separate from explicit satisfaction assessments and criterion verification. No edge, descendant satisfaction, completed plan or merged implementation derives even partial satisfaction automatically.
- Statement/classification/criterion changes conservatively advance normative revision and preserve previous snapshots, change rationale and authority. Terminal records cannot resurrect; supersession creates/uses a distinct replacement.
- Activation and terminal transitions require grounded authority/rationale, including justified derivation from explicit intent, not a new human approval.
- Combined directed `refines`/`derived_from` decomposition and `supersedes` lineage are acyclic. Other semantic cycles are allowed, diagnosed, and terminate without false truncation.
- Confidence `explicit`, `inferred`, `uncertain` remains visible through every path; candidate inference never establishes authority or satisfaction.
- Empirical criteria need empirical observations, not capability test/scenario passes. Latest applicable observation governs; current failed result is not stale merely because it failed.
- Strict JSON rejects duplicate keys, nonfinite numbers, unknown fields/versions and invalid endpoints. Broken references fail loudly; valid incomplete coverage is not corruption.
- Portable advisory writer lock covers load/expected-revision comparison/full validation/atomic replacement. Failed replacement and stale writes preserve canonical bytes; projection failure reports committed revision and stale output separately.
- Read queries never initialize, repair or write. Repository artifact locators reject traversal, absolute paths and outside-root symlinks. Descriptive external sources are never fetched/executed by this tool.
- No new permissions, runtime hooks, orchestrator, database, app graph, Fennel or C++ work. Preserve fast/live exceptions, strict independent review, dual-model consultation, handoff integrity, caps, debugging and capability refusals.
- Never require user review/approval of intermediate artifacts. Ask only focused questions for genuinely unresolved product/policy choices; resume automatically after answers.
- Fixtures do not prove live-agent compliance or remote merge. Static prompt tests establish declared contracts only. Actual CI and `mergedAt` remain final integration evidence.

## Shared interfaces and file responsibilities

`scripts/requirements.py` is a thin CLI adapter; focused private modules under `scripts/requirements_lib/` own schema, graph validation, transactions, evidence, graph reports and rendering. Python tests may use library calls and real CLI subprocesses.

- CLI verbs: `init`, `apply`, `query`, `validate`, `render`; `--repo-root` defaults to `.`; `--ledger` defaults to root-relative canonical path; complex requests use `--request FILE` or `--stdin`. `render --check` never writes; ordinary rendering is an implementer operation.
- Apply envelope: `{"actor":"implementer/session","expected_revision":0,"ops":[{"op":"create-requirement","args":{}}]}`. One or more operations validate and commit atomically.
- Query envelope: `{"op":"get","args":{"id":"REQ-..."}}`.
- Success: `{"status":"ok","revision":1,"result":{}}`; error: `{"status":"error","revision":null,"error":{"code":"...","message":"...","details":{}}}`, nonzero exit. Invalid requests, storage failures and stale projections never return empty successful reports.
- Library entry points: `load_ledger(repo_root, ledger_path=None) -> dict`; `apply(repo_root, request, ledger_path=None) -> dict`; `query(repo_root, request, ledger_path=None) -> dict`; `RequirementsError.code` for explicit failures. Tests share `helpers_requirements.run_cli(repo_root, verb, *flags, request=None)`.
- Ledger: `schema_version`, `revision`, `requirements` and `artifacts` ID maps, relation list, append-only assessments, verifications and conflict dispositions. Each record has strict allowed/required fields.
- Requirement: ID, classification, statement, rationale, `acceptance_criteria` (`id`, `text`, `applicability: empirical|analytical`), provenance (`source_reference`, `excerpt`, `actor`, `date`, `origin` distinguishing user intent/justified interpretation/descriptive evidence), lifecycle, normative revision, retained history.
- Artifact: ID, kind (`design`, `implementation_spec`, `code`, `test`, `evidence`), title, locator, optional selector, content digest. Register only linked artifacts; unregistered historical records stay outside semantic coverage.
- Relation: stable ID, type, source, target, rationale, provenance, confidence. Canonical symmetric conflict once, no self/duplicate logical edges. Revise/retract with rationale and retained history; never silently erase lineage.
- Assessment: requirement ID/revision, state (`unaddressed|partial|satisfied`), rationale, actor, time and source/evidence refs. Verification: requirement revision/criterion, method/result, procedure, environment, observation/time, safe durable evidence ref, declared dependency digests. Currency `current|stale|unknown` is distinct from result `absent|pending|passed|failed|inconclusive`.

| Relation | Endpoints |
| --- | --- |
| `refines`, `derived_from`, `contributes_to`, `depends_on`, `conflicts_with`, `supersedes` | requirement → requirement |
| `constrains` | constraint requirement → requirement/design/implementation spec |
| `addresses` | design/implementation spec → requirement |
| `realizes` | implementation spec → design |
| `implements` | code → implementation spec |
| `verifies` | test → requirement |
| `exercises` | test → code |
| `supports` | evidence → requirement/test |

---

### Task 1: Strict ledger, mutations and serialized storage

**Files:**
- Create: `scripts/requirements.py`, `scripts/requirements_lib/__init__.py`, `schema.py`, `store.py`, `locking.py`, `graphvalidate.py` inside that package.
- Create: `scripts/tests/helpers_requirements.py`, `scripts/tests/test_requirements_store.py`.
- Modify: `.gitignore` for ledger lock/temp siblings only.

**Interfaces:**
- Consumes: shared interfaces and endpoint matrix above.
- Produces: load/apply, CLI init/apply/validate/get; operations `create-requirement`, `revise-requirement`, `transition-requirement`, `supersede-requirement`, `register-artifact`, `update-artifact`, `add-relation`, `revise-relation`, `retract-relation`.

- [ ] **Step 1: RED.** Test strict top-level/nested schema, lifecycle/authority/revisions/history, identity across rename/reclassification, endpoint matrix, canonical conflict, forbidden directed composite/supersession cycles, allowed cycles, transaction rollback, safe locators and all CLI errors. Include two real competing writers using the same expected revision: exactly one commits, loser is stale; failed `os.replace` preserves old bytes and releases lock. Example:

```python
def test_stale_writer_preserves_bytes(repo):
    before = (repo / "docs/requirements/ledger.json").read_bytes()
    result = run_cli(repo, "apply", request={
        "actor": "test", "expected_revision": 999,
        "ops": [{"op": "transition-requirement", "args": {"id": "missing"}}]})
    assert result.returncode != 0
    assert json.loads(result.stdout)["error"]["code"] == "expected-revision-stale"
    assert (repo / "docs/requirements/ledger.json").read_bytes() == before
```

- [ ] **Step 2: GREEN.** Implement the above operations and strict complete-candidate validation, portable `fcntl`/`msvcrt` serialization and atomic storage. Run `python3 -m pytest scripts/tests/test_requirements_store.py -q`; capture expected RED and passing GREEN in the task report.
- [ ] **Step 3: Checkpoint.** Self-review exact assigned diff, preserve unrelated state, commit `feat(scripts): add transactional requirements ledger`; independent reviewer covers full task range.

### Task 2: Satisfaction assessments and verification evidence

**Files:**
- Create: `scripts/requirements_lib/evidence.py`, `scripts/tests/test_requirements_evidence.py`.
- Modify: `schema.py`, `store.py`, `scripts/requirements.py` for evidence ops and get reports.

**Interfaces:**
- Consumes: Task 1 record/revision/transaction APIs.
- Produces: `record-assessment`, `record-verification`, `record-conflict-disposition`; per-criterion latest observations and currency in query get.

- [ ] **Step 1: RED.** Test append-only history, source/evidence references, requirement revision and criterion identity, latest failure/inconclusive/pending masking old passes, missing dependency declarations unknown, content/digest changes stale, unrelated commit unaffected, empirical method applicability, and independent claim/result/lifecycle state. Use empirical_measurement for actual empirical evidence, analytical methods automated_test/scenario/audit/analysis/inspection. Inapplicable capability evidence must never establish empirical verification.

```python
def test_latest_failed_observation_is_not_hidden(evidence_case):
    evidence_case.observe(result="passed", at="2026-10-28T10:00:00Z")
    evidence_case.observe(result="failed", at="2026-10-29T10:00:00Z")
    latest = evidence_case.report()["criteria_latest"]["c1"]
    assert latest["result"] == "failed"
    assert latest["currency"] == "current"
```

- [ ] **Step 2: GREEN.** Implement evidence recording and currency without executing stored procedures or inferring satisfaction. Run `python3 -m pytest scripts/tests/test_requirements_store.py scripts/tests/test_requirements_evidence.py -q`.
- [ ] **Step 3: Checkpoint.** Validate/self-review and commit `feat(scripts): track requirement assessments and verification`; full-range independent review.

### Task 3: Bidirectional graph, coverage, impact and reconciliation reports

**Files:**
- Create: `scripts/requirements_lib/graph.py`, `render.py`, `scripts/tests/test_requirements_graph.py`, `scripts/tests/test_requirements_render.py`.
- Modify: CLI/store/schema dispatch as needed within defined contracts.

**Interfaces:**
- Consumes: Task 1 typed graph and Task 2 evidence reports.
- Produces: query `search`, `trace`, `impact`, `coverage`, `reconciliation-context`, `readiness`; `render` and check-only projection freshness.

- [ ] **Step 1: RED.** Test every relation forward/backward; many-to-many/shared paths; original orientation and path confidence; allowed cycles terminate with diagnostics not truncation; actual bounds truncate. Test upward/downward semantic impact, code-to-purpose trace, shared-locator potential impacts, all design coverage findings, indirect goal design trace without outcome proof, stale artifact/evidence, superseded dependencies, and change-scoped readiness. Explicit material applicable conflicts/negative observations/constraints block; candidate links remain uncertainty for agent investigation, not automatic normative blockers or automatic clearance. Unrelated pending empirical parents do not block capability work. Do not invent readiness bypasses.

```python
def test_allowed_cycle_is_not_truncation(graph_case):
    start = graph_case.dependency_cycle()
    report = graph_case.query("trace", id=start, direction="forward")
    assert report["cycle_diagnostics"]
    assert report["truncated"] is False
```

- [ ] **Step 2: GREEN.** Implement deterministic reports with scope/unknowns/paths/reasons/confidence, terminating traversal and documented relation/direction rules. Literal search and context retrieval are not semantic equivalence. Render deterministically; projection failure after canonical commit reports revision and stale output nonzero without claiming rollback. Run `python3 -m pytest scripts/tests/test_requirements_graph.py scripts/tests/test_requirements_render.py -q`.
- [ ] **Step 3: Checkpoint.** Self-review and commit `feat(scripts): query requirements traceability and impact`; independent review.

### Task 4: Reconciliation skill and autonomous workflow integration

**Files:**
- Create: `.opencode/skills/requirements-reconciliation/SKILL.md`, `scripts/tests/test_requirements_workflow_contracts.py`.
- Modify: `.opencode/agents/{supervisor,planner,implementer,reviewer,debug-advisor,fast-dev-reviewer,fast-dev,live-dev}.md`.
- Modify: `.opencode/skills/{brainstorming,writing-plans,subagent-driven-development,systematic-debugging,finishing-a-development-branch}/SKILL.md`, `AGENTS.md`, `Makefile`.

**Interfaces:**
- Consumes: exact CLI query/mutation names; existing reviewer schema and role boundaries.
- Produces: shared skill used for goal/feature/change/bug/maintenance/exploration/clarification independently of read-only/tiny/full ceremony; requirements/design/plan independent artifact reviews; autonomous transitions and focused clarification/resumption. Existing caps, handoff gate, dual-model/capability/merge boundaries unchanged.

- [ ] **Step 0: Behavioral baseline.** Before edits the controller dispatches read-only pressure probes for goal contribution versus derivation, no-synthetic-requirement bug/maintenance, conflicting intent versus design, deferred empirical outcome, and artifact-approval pressure. Retain actual original responses privately; record safe exact outcomes in progress. No edits needed for probes.
- [ ] **Step 1: RED.** Write static tests for skill discovery/frontmatter, canonical CLI names, proportional reconciliation conclusion contract, no stale ordinary user artifact approvals, fast/live exception preservation, unchanged permissions, and nonrecursive Makefile gate wiring. Label static tests honestly; they do not prove live compliance. `python3 -m pytest scripts/tests/test_requirements_workflow_contracts.py -q` must expose missing guidance before edits.
- [ ] **Step 2: GREEN.** Add skill and targeted touchpoints at intake, brainstorming, planning, execution/review, debugging and finishing. Read-only conclusions stay report-only; mutation findings use reviewed ledger changes/provenance and existing progress records. Register `requirements-check` and make `opencode-check` depend on it without recursion; include focused tests and canonical validation/index freshness when the seed exists. Run focused tests and `make opencode-check`.
- [ ] **Step 3: Behavioral GREEN.** Controller reruns same probes with new sources explicitly supplied; running roles are not reloaded by edits. Compare observations and fix real gaps via reviewed changes. Document restart requirement, do not claim guaranteed runtime enforcement.
- [ ] **Step 4: Checkpoint.** Self-review, preserve fast/live manual lifecycle/exceptions, commit `feat(opencode): integrate requirements-driven reconciliation`; full independent review.

### Task 5: Current-task ledger, demonstrations, templates and documentation

**Files:**
- Create: `docs/requirements/ledger.json`, `docs/requirements/index.md`, `scripts/tests/test_requirements_scenarios.py`, `scripts/tests/test_requirements_demos.py`.
- Create: `docs/dev/features/requirements-driven-engineering.md`, `docs/dev/notes/requirement-templates.md`.
- Modify: `docs/dev/development-records.md`, `docs/dev/features/opencode-agent-workflow.md`, `docs/.vitepress/config.mts`, `docs/index.md`, record index generator/navigation scripts/tests if required, `Makefile`, design/plan/progress links.

**Interfaces:**
- Consumes: complete CLI/library, reconciliation skill and existing docs browsing.
- Produces: actual current user obligations with provenance and stable identities; this design/plan/code/test/evidence linked where justified; no fabricated historical requirements. Documentation/templates mirror actual implemented APIs, evidence and workflow limitations.

- [ ] **Step 1: RED.** Write real CLI/library fixture scenarios and four composite demos; run `python3 -m pytest scripts/tests/test_requirements_scenarios.py scripts/tests/test_requirements_demos.py -q`. Exercise actual retrieval/mutations/report logic, not mocked hard-coded semantic routing. Scenario reasoning stays explicitly agent-owned.
- [ ] **Step 2: GREEN.** Close demonstrated designed gaps, execute demos A goal feature, B existing behavior change, C bug correction, D verified capability/unproven outcome. All use temporary fixture repositories and do not claim genuine remote merge or agent compliance.
- [ ] **Step 3: Seed and trace.** Implementer initializes and captures only obligations grounded in current user intent using real CLI operations; link design and implementation spec, code/tests and safe validation evidence. Do not claim high-level empirical achievement. Render the index, check lock/temp artifacts ignored, validate forward/backward trace and scoped coverage/readiness.
- [ ] **Step 4: Docs.** Update developer pages, templates, sidebar/overview and generated record indexes; add requirements browsing without breaking legacy inventories. Run actual package commands from `docs/package.json`: script tests, records generation/navigation check and docs build in their required dependency order. Record exact commands/results.
- [ ] **Step 5: Checkpoint and final integration.** Run `python3 -m pytest scripts/tests/test_requirements_*.py -q`, `make requirements-check`, `make opencode-check`, relevant docs gates, self-review and commit. Independent task review and whole-branch review precede finishing. Fetch/evaluate current `origin/main`, resolve any failures through debugging/review, use guarded automatic PR/auto-merge/queue flow and poll to actual `mergedAt`.

## Scenario acceptance mapping

Each named scenario test lives in `scripts/tests/test_requirements_scenarios.py`:

| # | Scenario | Test suffix after `test_scenario_` |
| --- | --- | --- |
| 1 | Missing requirement for new behavior | `01_missing_requirement_intake` |
| 2 | Already-covered new behavior | `02_reuses_existing_requirements` |
| 3 | High-level goal decomposition | `03_goal_decomposition_refines` |
| 4 | Outcome with multiple capabilities | `04_multi_capability_outcomes` |
| 5 | Capability contributing to multiple goals | `05_capability_contributes_multiple_goals` |
| 6 | Constraint across branches | `06_cross_branch_constraint_readiness` |
| 7 | Requirement conflict | `07_conflict_disposition_readiness` |
| 8 | Intent versus current design | `08_intent_design_conflict_finding` |
| 9 | Implementation defect, no new requirement | `09_implementation_defect_reuses_requirement` |
| 10 | Design defect requiring revision | `10_design_defect_routes_to_design_revision` |
| 11 | Bug revealing requirements gap | `11_bug_reveals_missing_requirement` |
| 12 | Maintenance without synthetic requirement | `12_maintenance_reporting_explicit` |
| 13 | Requirement change across designs | `13_revision_invalidates_design_traces` |
| 14 | Design discovery returns to reconciliation | `14_design_discovery_returns_to_reconciliation` |
| 15 | Strategic outcome still awaiting evidence | `15_verified_capability_outcome_not_satisfied` |

Demonstration tests in `test_requirements_demos.py`: `test_demo_a_goal_driven_feature`, `test_demo_b_existing_behavior_change`, `test_demo_c_bug_correction`, `test_demo_d_verified_capability_outcome_not_proven`.

## Validation and scope

No runtime build is required for Python/prompt/docs changes. PR CI remains the complete integration gate. Required failures trigger systematic diagnosis, not bypass or immediate abandonment. Unknown product/data policy remains human-owned, but operational recovery and artifact reviews do not require user approval. The unchanged reconciled architecture is recorded in the [progress ledger](2026-10-29-requirements-driven-engineering-progress.md); no new consultation scope is introduced by this plan.
