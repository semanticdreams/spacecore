# Repository Requirements Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile the existing ledger against repository-wide intent and sampled implementation evidence, with complete source accounting, supported traceability, explicit gaps and idempotent resumption.

**Architecture:** Four serial implementer/reviewer tasks use only the existing requirements CLI. Ordinary tracked audit/disposition records distinguish source inventory from normative coverage; no new infrastructure or application changes.

**Tech Stack:** Existing Python requirements CLI, JSON ledger, Markdown records, read-only Git, existing requirements checks and VitePress package scripts.

## Global Constraints

Verbatim governing design constraints:

- “It is not new product development or a discovery system.”
- “Families organize this audit, not the schema or a new normative hierarchy.”
- “No new infrastructure, recurring job, schema, tooling, application/test changes, or rewritten historical records.”
- “Inventory all tracked documentation families; explicitly account for every existing design and plan/progress filename.”
- “External API mirrors, vendor content, historical Python prototypes and incidental examples are not normative Space intent.”
- “Record sampling/depth honestly: filename inventory is not complete semantic review of every line.”
- “Never label an unread historical source superseded merely from its date/name.”
- “Search and inspect the current ledger before creation, comparing semantics and provenance as well as literal terms.”
- “Reuse existing requirement/artifact IDs.”
- “Keep proposed roadmaps proposed.”
- “Acceptance criteria must be scoped and verifiable.”
- “Qualitative strategic outcomes remain unverified with measurement/threshold gaps; do not invent numeric targets.”
- “Constraints need evidenced applicability.”
- “Do not claim runtime verification from this docs/ledger audit.”
- “Preserve existing observations and normative history.”
- “No direct JSON/index editing or initialization.”
- “Split dependent transactions using actual returned IDs.”
- “Demonstrate a second reconciliation sweep produces zero justified new records/links and no ledger byte/revision change; a no-op write is not required.”
- “Use ordinary consultation/fix-cap gates and automatic transitions; no intermediate human artifact approval.”

## Authority, ownership and shared protocol

Governing design: `docs/specs/2026-10-30-repository-requirements-baseline-design.md`, checkpoint `6fd7c0b`, independently passed by reviewer session `ses_e72c340f1ffet4XVnib8r2Ew4I`. Frozen discovery source: `fec176453c88fa1c47f22b7fe1d447dfe0ba281b`, branch `juicyrebel/ridley`, clean at intake, ledger revision 29 with 12 requirements/26 artifacts. Resolve actual full checkpoint IDs when executing.

Conclusion: missing product representation, not missing functionality. This request authorizes grounded discovery beyond the original methodology seed, not automatic activation of historical plans. Reuse existing revision-1 obligations for reconciliation (`REQ-8e50a634-76ae-4100-9f60-90e4552ec954`), history (`REQ-26f18ef2-15f6-4278-b9a1-9c7b4b246e5c`), traceability (`REQ-1970c4a9-a5dc-4d1b-93ce-dc88ed42df84`), evidence separation (`REQ-2824ad77-fbc5-4db6-ac9a-732af10eeabc`), transaction safety (`REQ-0bf07879-9bbb-421a-85ab-37f495b6e552`) and reviewed progression (`REQ-49e62b92-aada-447d-9d15-531625fa0dcc`).

Exactly one canonical writer; execute tasks serially after independent pass. Record BASE and FIX_BASE; validate, self-review and checkpoint every assigned task/fix locally, then independently review its complete range. No worker publication/integration/history rewrite. Preserve unrelated state. Controller owns the plan and `docs/plans/2026-10-30-repository-requirements-baseline-progress.md`.

Allowed worker writes:

- `docs/requirements/ledger.json` via existing apply operations only.
- `docs/requirements/index.md` via existing render only.
- `docs/requirements/2026-10-30-repository-reconciliation.md`: consolidated decisions, IDs, counts, status, gaps and validation.
- `docs/requirements/2026-10-30-repository-source-dispositions.md`: source-family inventory and filename-level dispositions.
- `docs/requirements/2026-10-30-baseline-task-{1,2,3,4}-report.md`: assigned worker report.
- Task 4 only: `docs/dev/features/requirements-driven-engineering.md`, `docs/dev/development-records.md`, `docs/index.md`.
- `docs/specs/index.md`, `docs/plans/index.md` through existing generator when records are added.

All other files read-only. Transient inspection/request snippets may use approved temporary space; do not check in an importer. Worker reports are not automatically registered evidence. Do not anchor mutable reporting as immutable measurement evidence.

CLI commands:

```sh
python3 scripts/requirements.py query --repo-root . --stdin
python3 scripts/requirements.py apply --repo-root . --request /tmp/opencode/space-baseline-change.json
python3 scripts/requirements.py validate --repo-root .
python3 scripts/requirements.py render --repo-root . --check
make requirements-check
git diff --check
```

Requests use `{"actor":"implementer/task-session","expected_revision":CURRENT_INTEGER,"ops":[{"op":"OPERATION","args":{}}]}` populated with inspected actual values. See `docs/dev/features/requirements-driven-engineering.md:102-143` for exact operation fields. Create requirements with scoped acceptance criteria and provenance (`source_reference`, excerpt, actor/date/origin); sources are not user intent merely because they are technical designs. New records start proposed; activation requires separate grounded authority. Split dependent requests using actual returned IDs/revision. On stale revision reload; on projection error inspect committed revision and render, never replay creation.

Queries use `{"op":"coverage","args":{}}`, scoped `coverage` with `scope:[actual IDs]`, `reconciliation-context` with `scope`, `max_depth:32`, `max_paths:1000`, and `trace` with `id`, `direction:"both"` and the same bounds. Record scope, truncation and unknowns; narrow material truncated queries. Literal search is not semantic/provenance search. Inspect canonical records.

Use `refines` for precision; `derived_from` only for evidenced authority/derivation; `contributes_to` for help without sufficiency. Design/implementation-spec `addresses` requirement; implementation-spec `realizes` design; code `implements` implementation-spec; test `verifies` requirement and `exercises` code; evidence `supports` requirement/test; constraint `constrains` requirement/design/implementation-spec. No invented code-to-requirement edge or artificial plan to fill a chain.

Separate intent, implementation, test definitions, historical reported tests, fresh audit observations and satisfaction. No automatic partial/satisfied assessments. Unknown material policy remains human-owned; contrary technical narrowing without policy-change evidence is a solution/coverage defect. Record gaps without expanding into application repair.

## Task 1: Complete source accounting and top-down goals/roadmaps

**Files:** Create consolidated audit, source-disposition page and Task 1 report; mutate ledger/index through CLI; regenerate spec/plan indexes. Inspect all tracked docs families, README, goals/milestones and source history. Tests remain unchanged.

**Interfaces:** Consumes reviewed design/current ledger/frozen source. Produces manifest, top-down IDs/revisions and family assignments/gaps for Tasks 2–4.

- [ ] Establish actual branch/BASE, author/session, full design commit, frozen snapshot, revision and strict review identity. Preserve unrelated state. Retrieve governing requirements and scoped reconciliation context plus coverage.
- [ ] Enumerate frozen tracked paths using `git ls-tree -r -z fec176453c88fa1c47f22b7fe1d447dfe0ba281b`. Verify initial 168 specs/194 plans excluding root indexes; investigate discrepancies rather than adjusting denominator. Account separately for new audit records.
- [ ] Give each frozen spec/plan path exactly one first-column backticked table row: family/owner, disposition, source-specific rationale, inspected section/excerpt/Git reference, depth and resulting IDs or concrete gap. Categories: grounded obligation, supporting solution/evidence, duplicate/reused, historical/replaced, reference-only or unresolved gap. Never use unsupported blanket supersession.
- [ ] Inventory ALL docs families with directory membership/counts/depth and uninspected bounds: features, project goals/milestones/backlog/history, ADRs, SDK/user, notes/subsystems/Fennel, journals, requirements, external API/reference and docs tooling. Verify 61 feature pages/12 milestone files with index-inclusion rules. Inventory canonical code/test/script/build/package families; exclude vendor/prototypes from normative authority.
- [ ] Inspect top-down source text and introduction/modification history with `git log FROZEN -- paths` and `git show COMMIT:path`. Reconcile public positioning, active goals and proposed work; preserve exact provenance and qualitative measurement gaps. No source status label proves achievement.
- [ ] Search each candidate semantically and by provenance before reuse/refinement/creation. Apply grounded goal/roadmap changes, with meaningful contribution/refinement links; no count targets or fixed hierarchy. Record returned IDs/revision and completed scope after every transaction.
- [ ] Run shared validation, manifest-set equality and scoped context/coverage/trace; regenerate indexes using `npm run records:indices` with workdir `docs`. Report counts, revisions, findings, handoffs and rationale in Task 1 report. Self-review, checkpoint all assigned changes, then controller obtains complete-range independent review.

**Acceptance:** All frozen spec/plan paths accounted exactly once; all docs families have explicit coverage bounds; grounded top-down intent recorded without activation/achievement inflation.

## Task 2: Graph, entities, workflows, agents and text

**Files:** Create Task 2 report; modify audit/dispositions and CLI-owned ledger/index. Inspect assigned specs/plans, graph doctrine, feature contracts and corresponding canonical code/tests. `.opencode/` is read-only workflow evidence, distinct from application agents.

**Interfaces:** Consumes accepted Task 1 IDs/manifest/assignments. Produces grounded family IDs/typed traces, evidence/status matrix, cross-family gaps.

- [ ] Reload current revision; search existing semantics/locators/provenance and retrieve scoped context. Read applicable domain guidance to interpret terminology/ownership without changing architecture.
- [ ] Inspect graph foundation/capabilities/projections/ordered membership/navigation, persistent entities/search/reference lifecycle, workflows/runs/notebooks/kernels, agent runner/providers/MCP/OpenCode exposure and text/lazy-buffer/input contracts. Follow original Git evidence, public exports, lifecycle/persistence/runner boundaries and actual test assertions enough to justify traces.
- [ ] Reuse top-down/shared obligations; create only independently justified capability/behavior/constraint records. Establish supported design→requirement, plan→design, code→plan, test→requirement/code and contribution links. Record missing links rather than inventing them; inspect applicability of constraints.
- [ ] For each obligation report implementation presence/partiality, test definitions, historical verification separately, fresh audit observations and outcome gaps. Update every assigned source disposition; no product-test execution claims or automatic satisfaction from links.
- [ ] Run shared validation, manifest comparison and scoped queries with bounds. Write actual revision/ID/count/inspection/validation report; self-review and checkpoint complete task for independent review before Task 3.

**Acceptance:** Assigned families meaningfully represented without duplicated shared contracts; exact sources/traces and implementation/verification limits inspectable.

## Task 3: Remaining platform and product capabilities

**Files:** Create Task 3 report; modify audit/dispositions and CLI ledger/index. Inspect remaining assigned docs/specs/plans/code/test/build families; no product changes.

**Interfaces:** Consumes accepted Tasks 1–2 identities/shared obligations. Produces remaining capability traces, original-source contradictions and completed family matrix for Task 4.

- [ ] Reconcile core runtime/widget/layout/input, activities/world/terrain/drawing, hostable apps/commands/distribution, temporal/scheduling, media/browser/audio, networking/SSH/realtime, wallets/security/publication, reload/development/validation and workflow tooling. Reuse shared obligations. Do not access secrets or operate external services/migrations/security boundaries.
- [ ] Inspect current documented contracts into native/Fennel modules, adapters/data/build declarations and test definitions. Distinguish conditional backend availability from universal support; API/vendor references are not independent Space authority. Record exact pointers and depth.
- [ ] Investigate temporal breadth specifically: compare `docs/specs/2026-09-28-temporal-complete-library-design.md`, `docs/specs/2026-10-03-temporal-closeout-design.md`, current temporal feature/acceptance pages, tests and their `git log FROZEN -- paths`/`git show` history. Preserve original excerpts/commits. Later bounded closeout/merge does not authorize discarding broader intent; record evidenced solution/coverage defects or precise missing authority, not invented completion or new scope.
- [ ] Apply grounded remaining-family records and supported links through serial CLI transactions. Keep implementation-only candidates descriptive gaps. Finish assigned dispositions, status axes and cross-family contradictions without relabeling historical tests fresh.
- [ ] Run shared validation, manifest comparison and scoped queries. Report counts/IDs/revisions, original Git evidence, contradictions/limits and validation; self-review and checkpoint complete assigned changes for independent review before Task 4.

**Acceptance:** All remaining families reconciled within declared depth; material contradictions retained with source evidence and honest dispositions, no invented policy or empirical achievement.

## Task 4: Cross-family consistency, idempotence, reporting and docs

**Files:** Create Task 4 report; modify audit/dispositions, CLI ledger/index, methodology guide, development-records guide and docs homepage; regenerate record indexes only through existing generator.

**Interfaces:** Consumes accepted family batches, source manifest, shared IDs and gaps. Produces final ledger/index/report, complete source accounting, no-change second-sweep evidence and review package.

- [ ] Inspect cross-family semantic duplicates, provenance, artifact locator/selectors, active relation tuples/directions/confidence, lifecycle and criteria. Preserve history; use justified existing revisions/retractions/supersession only where warranted. Missing links are gaps, not absent-functionality proof.
- [ ] Compare frozen/current spec-plan path sets to first-column manifest rows: frozen exactly once, added audit records separately, no duplicate/unexplained extras, consistent index exclusions. Review each unresolved gap for concrete reason/owner. Check every docs family's denominator and depth.
- [ ] Update existing methodology guide to distinguish original seed from authorized baseline and describe limits/resumption; link audit/dispositions from development-records and homepage. Do not rewrite product intent/history or add new tooling pages.
- [ ] Run shared gates and final all-record coverage plus scoped context/trace. From `docs` run `npm run test:scripts`, `npm run records:indices`, `NODE_OPTIONS=--max-old-space-size=4096 npm run docs:build`, then `npm run records:check` (build before navigation check). Install locked deps with `npm ci` only if needed. Check capacity before heap increase. Diagnose unexpected generated side effects; never stage/discard outside scope blindly. No runtime/Fennel/full-app/prompt-policy suite required for ledger/docs-only changes.
- [ ] Capture ledger revision/byte digest and index digest after intended mutations. Perform a second source-to-ledger sweep across EVERY family, comparing actual IDs/provenance/locators/relations/dispositions: zero justified creates/revisions/transitions/links and unchanged bytes/revision. No no-op apply. If an omission is found, reconcile, validate and repeat honestly.
- [ ] Final audit report defines discovered/created/reused/revised/registered/linked counts; frozen/added inventory; family IDs/revisions/status; implementation-coverage numerator/denominator/unknowns; original-source contradictions, proposed work/missing links/measurement gaps; actual checks/no-change evidence; pending independent review/integration. No automatic satisfaction or global freeze for unrelated strategic gaps.
- [ ] Self-review, checkpoint all Task 4 changes and obtain independent task review. Controller then obtains final independent full range review `fec176453c88fa1c47f22b7fe1d447dfe0ba281b..HEAD` including design/plan/progress, every ledger batch/fix and docs additions. Passing fragments are not whole-range approval. Route fixes/consultation normally, then guarded current-main validation/PR/queue integration through actual merged-state evidence.

**Acceptance:** Source families and filenames accounted; grounded nonduplicate obligations and supported traces represented; honest gaps/status; unchanged second sweep; checks green; all content checkpointed and independently reviewed, followed by required finishing gates.
