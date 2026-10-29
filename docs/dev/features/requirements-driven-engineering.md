# Requirements-driven engineering

Requirements describe desired states and obligations, not the implementation that
happens to exist. Start with the user's intent and reconcile it with existing
requirements, designs, plans, code and observations before choosing a solution.
This is a shared agent capability, not a new orchestrator or Space application
graph. See the [current requirements index](/requirements/),
[templates](/dev/notes/requirement-templates),
[reviewed design](/specs/2026-10-29-requirements-driven-engineering-design) and
[implementation progress](/plans/2026-10-29-requirements-driven-engineering-progress).

## Ownership and authority

Classify goal/outcome, feature, change, bug, maintenance, exploration or clarification
independently of task size. Inspect original provenance; literal retrieval is only
candidate context. Record a proportional conclusion in the existing handoff/progress
record: scope/sources, authority/uncertainty, changes/impacts, constraints/verification
and next transition. A read-only conclusion stays report-only.

- New intended behavior needs grounded obligations. Reuse existing identities when
  covered; do not duplicate requirements to accompany every change.
- An implementation defect reuses the governing requirement; a design defect revises
  the solution. A genuine requirements gap needs intent authority, not just a bug.
  Behavior-preserving maintenance gets no synthetic requirement.
- Explicit user intent outranks a contrary technical design. Ask a focused human
  question only for genuinely unresolved product/policy choices, then resume.
- In strict flow, implementers own canonical mutations; controllers may inspect and
  query. Requirements, designs and implementation specs receive independent review
  over the exact pending diff/revision or complete checkpoint range. Advance
  autonomously after pass, never ask the user to approve intermediate artifacts.
- Existing consultation, debugging, review caps, handoff integrity and capability
  refusals remain in force. Fast/live retain direct edits and their explicit wrap-up
  exceptions; live retains manual-before-edit and validated-refresh.

The shared source is `.opencode/skills/requirements-reconciliation/SKILL.md`.
Quit and restart OpenCode after reviewed rollout: running sessions retain loaded
roles. Orca configuration is described in the [workflow guide](/dev/features/opencode-agent-workflow);
this repository does not contain Orca's implementation or add runtime hooks.

## Records and relations

`docs/requirements/ledger.json` is canonical schema version 1. The generated
`docs/requirements/index.md` is a deterministic ledger-only projection, not a
freshness report. Never edit either JSON records or the index by hand.

Requirement IDs are opaque immutable `REQ-<uuid>` values; artifact IDs are
`ART-<uuid>`. Classification (`goal`, `outcome`, `capability`, `behavior`, `constraint`)
is not a fixed ladder. Requirements contain statement, rationale, criteria
(`id`, `text`, `applicability`), provenance and independent lifecycle/revision/history.
Provenance includes `source_reference`, optional `excerpt`, `actor`, `date`, and
`origin`: `user_intent`, `justified_interpretation` or `descriptive_evidence`.
Descriptive sources are not automatically authority.

Lifecycle is `proposed`, `active`, `superseded` or `rejected`. Activation and terminal
transitions require grounded reason/authority. Revisions retain prior normative
snapshots; terminal records cannot resurrect. Supersession uses a distinct replacement
and transfers no evidence or satisfaction. Artifact title/locator updates retain ID.

| Relation | Stored source → target | Interpretation |
| --- | --- | --- |
| `refines` | requirement → requirement | More precise obligation |
| `derived_from` | requirement → requirement | Established based on source, justified derivation |
| `contributes_to` | requirement → requirement | Helps, not sufficient or logically derived |
| `depends_on` | requirement → requirement | Prerequisite |
| `conflicts_with` | requirement ↔ requirement | One canonical symmetric pair |
| `supersedes` | replacement → old requirement | Acyclic retained lineage |
| `constrains` | constraint → requirement/design/implementation spec | Restricts acceptable solution; constraint-to-constraint valid |
| `addresses` | design/implementation spec → requirement | Justifies solution |
| `realizes` | implementation spec → design | Executable design work |
| `implements` | code → implementation spec | Implementation trace |
| `verifies` | test → requirement | Test definition, not test run |
| `exercises` | test → code | Test surface |
| `supports` | evidence → requirement/test | Supporting observation |

Relations retain rationale, provenance, confidence (`explicit`, `inferred`, `uncertain`)
and revision/retraction history. No self/duplicate logical edges. Combined
`refines`/`derived_from` decomposition and supersession lineage are acyclic; other
semantic cycles are diagnosed and terminate without falsely implying truncation.
Confidence stays visible through paths; inferred links establish no authority.
Only register linked artifacts, not a historical source inventory. Existing
[record indexes](/dev/development-records) remain useful without bulk registration.

## Actual CLI and library

Run from the repository root with Python 3 (standard library only):

```sh
python3 scripts/requirements.py validate --repo-root .
python3 scripts/requirements.py render --repo-root . --check
python3 scripts/requirements.py query --repo-root . --request query.json
python3 scripts/requirements.py apply --repo-root . --request change.json
```

For `query`/`apply`, supply exactly one of `--request FILE` or `--stdin`.
All verbs accept `--repo-root` (default `.`) and `--ledger` (root-relative or
absolute canonical path). The projection destination is always
`docs/requirements/index.md`, even with a custom ledger; colliding destinations
are rejected. `init` explicitly creates an empty revision-0 ledger and refuses an
existing ledger; it does **not** render. Do not initialize the already-seeded repo.
`render` is a writer operation; `render --check` is read-only.

Apply envelope (replace revision and actual IDs after inspection):

```json
{"actor":"implementer/session","expected_revision":7,"ops":[{"op":"revise-requirement","args":{"id":"REQ-<uuid>","reason":"Explicit source clarifies intent","statement":"Grounded desired behavior","provenance":{"source_reference":"recorded user contract","excerpt":"Exact relevant intent","actor":"implementer/session","date":"2026-10-29","origin":"user_intent"}}}]}
```

These placeholders are documentation, not runnable IDs. `apply` returns generated
IDs in `result.ops`; later requests must use them. No symbolic forward references.
Batch operations are atomic; split dependent batches after inspecting returned IDs.
Every mutation requires an actor and exact `expected_revision`. Operation arguments:

| Operation | Required arguments | Optional arguments |
| --- | --- | --- |
| `create-requirement` | classification, statement, rationale, provenance | acceptance_criteria |
| `revise-requirement` | id, reason; at least one change | statement, classification, acceptance_criteria, rationale, provenance, date |
| `transition-requirement` | id, to, reason, authority | date |
| `supersede-requirement` | old_id, reason, authority, provenance; exactly one replacement form | create (create-requirement args) **or** replacement_id; date |
| `register-artifact` | kind, title, locator | selector, content_digest |
| `update-artifact` | id; at least one change | title, locator, selector, content_digest |
| `add-relation` | type, source, target, rationale, provenance, confidence | none |
| `revise-relation` | id, reason | confidence, rationale, date |
| `retract-relation` | id, reason | date |
| `record-assessment` | requirement_id, requirement_revision, state, rationale, source_refs | date |
| `record-verification` | requirement_id, requirement_revision, criterion_id, method, result, procedure, environment, observation, timestamp, evidence_ref, dependency_digests | none |
| `record-conflict-disposition` | relation_id, explanation, authority | date |

Artifact kinds are `design`, `implementation_spec`, `code`, `test`, `evidence`.
Digests are SHA-256 hex. References use exactly one of `locator` or `artifact_id`.
Repository artifact/evidence locators reject traversal, absolute paths and outside-root
symlinks. External descriptive provenance is never fetched or executed.

Query envelope: `{"op":"coverage","args":{}}`. Unknown fields are errors.

| Query | Required arguments | Optional/default arguments |
| --- | --- | --- |
| `get` | id | none; requirements include criteria_latest |
| `search` | text | classification **or** kind |
| `trace` | id | direction=forward (backward/both available), max_depth=32, max_paths=1000 |
| `impact` | id | max_depth=32, max_paths=1000 |
| `coverage` | none | scope (nonempty ID list); default all registered records |
| `reconciliation-context` | scope | max_depth=32, max_paths=1000 |
| `readiness` | scope, material_criteria, material_constraints | max_depth=32, max_paths=1000 |

Bounds allow depth 1–1000 and paths 1–10000. `search` is case-insensitive literal
substring retrieval (`semantic_equivalence: false`), not natural-language reasoning.
Trace follows original orientation or its inverse without editable inverse edges.
Impact is bounded potential reachability, never complete behavioral blast-radius
proof. Read original records and path confidence, unknowns and `truncated`.

Library entry points in `scripts/requirements_lib`: `load_ledger(repo_root,
ledger_path=None)`, `apply(repo_root, request, ledger_path=None)`,
`query(repo_root, request, ledger_path=None)`; explicit failures expose
`RequirementsError.code`. CLI success is `status: ok`, `revision`, `result`.
Errors are nonzero with `status: error`, `revision: null`, and
`error: {code, message, details}`. A `projection-stale` error after commit includes
`details.committed_revision` and `projection_stale: true`: canonical data committed.
Inspect it, then run ordinary `render`; do not blindly repeat the mutation.
`expected-revision-stale` preserves canonical bytes. Reads never initialize/repair.
Advisory writer locking covers load/compare/full validation/atomic replacement.
Duplicate JSON keys, nonfinite numbers, unknown versions/fields and broken references
fail loudly; valid incomplete coverage is not corruption. Local lock/temp siblings
are ignored, not authoritative data.

## Evidence and scoped readiness

Lifecycle, assessment (`unaddressed`, `partial`, `satisfied`) and criterion
verification are separate. No relation, descendant pass, completed plan or merge
automatically derives even partial satisfaction. Analytical methods are `scenario`,
`automated_test`, `audit`, `analysis`, `inspection`; empirical criteria require
`empirical_measurement`. Test definitions and scenario passes are not real outcome
measurements. Procedures are inert recorded descriptions, never executed by the tool.

Record result (`pending`, `passed`, `failed`, `inconclusive`), UTC timestamp,
procedure/environment/observation, durable safe evidence reference and declared
dependency digests. `absent` is a computed result when nothing applies. Evidence
bytes are independently hashed at record time. Currency (`current`, `stale`, `unknown`)
is separate from result: normative revision, changed evidence or declared dependencies
can invalidate it; undeclared dependencies leave currency unknown. Unrelated commits
alone do not. Latest applicable observation time governs, append order breaks ties.
A current failure is not stale merely because it failed.

Readiness needs explicit nonempty scope plus material criterion pairs
`{"requirement_id":"REQ-<uuid>","criterion_id":"c1"}` and constraint IDs.
Empty material lists mean none selected, not blanket clearance. Constraints are
established only at scope-self or via one explicit `constrains` then downward inverse
`refines`/`addresses`/`realizes`/`implements`, stopping at scope. `derived_from`,
contribution, repeated constraints, siblings and candidate links are not normative
inheritance. Direct explicit constraints are discovered; other material inherited
ones must be selected after inspection. Unlinked/excluded/truncated applicability
is unknown, not a violation or clearance.

Reports distinguish requested/established constraints and witnesses. Current negative
material observations, non-satisfied material constraint assessments and unresolved
material conflicts block. Missing/stale observations and unknown applicability need
investigation. Dispositions retain authority/explanation, not proof of compatibility.
`no-recorded-blockers` grants no permissions, test pass, independent approval or merge.
Pending unrelated strategic outcomes do not impose a global merge freeze.

## Demonstrations, validation and current seed

Run real temporary-repository fixtures, not mocks or keyword routing:

```sh
python3 -m pytest scripts/tests/test_requirements_scenarios.py scripts/tests/test_requirements_demos.py -q
python3 -m pytest scripts/tests/test_requirements_*.py -q
make requirements-check
make opencode-check
```

The fifteen named scenarios cover missing/reused intent, refinement, multi-capability
outcomes, shared goals, cross-branch constraints, conflicts, intent/design defects,
implementation defects, design revision, bug gaps, maintenance, requirement revisions,
design discoveries and unproven strategic outcomes. Four composite demos exercise
A goal-driven feature, B changed behavior, C bug correction, D verified capability
with unproven outcome. Agents still own reasoning, source authority and review routing.
Fixtures prove recorded-tool behavior, **not live-agent compliance or remote merge**.

From `docs/`, run the actual package commands in dependency order:

On a fresh checkout install locked dependencies first with `npm ci` if
`node_modules`/VitePress is absent. A large-site build may exceed Node's default
heap; the validated local invocation used
`NODE_OPTIONS=--max-old-space-size=4096 npm run docs:build` (check host capacity
before raising the limit). This changes process capacity, not the build gate.

```sh
npm run test:scripts
npm run records:indices
npm run docs:build
npm run records:check
```

The build generates journal/devlog and record indexes, syncs the icon, builds VitePress
and then checks built navigation. Running the navigation check before building may
inspect stale or missing output. Requirements rendering is separate: validate and
`render --check` before the docs build. `make requirements-check` runs Python checks
and, once the canonical seed exists, validates it and checks projection freshness;
it never seeds missing data. `make opencode-check` includes it nonrecursively.
No Space runtime/build change is needed for this Python/prompt/docs surface.

The seed captures only this current methodology task's explicit obligations. It is
not a migration of historical Space product goals. The reviewed design/plan and
justified code/test/safe evidence references are linked. Mutable progress pages are
not immutable measurement evidence: refresh artifact digests with `update-artifact`
after intentional content changes and record new observations if their declared
dependencies changed. Do not overwrite retained observations to manufacture currency.
Task assessments can remain partial pending independent review and final integration.
Empirical methodology improvement is not claimed achieved.

The controller owns final guarded integration after independent Task 5 and whole-branch
review: current remote-base evaluation, actual CI, guarded PR/queue and actual
`mergedAt` evidence. Local fixtures, checks and checkpoints cannot substitute for it.
