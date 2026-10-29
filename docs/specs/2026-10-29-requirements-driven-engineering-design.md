# Goal-aware requirements-driven engineering

## Authority and intent

This design implements the current user contract, **Evolve the Existing Agentic
Development System into a Goal-Aware, Requirements-Driven Engineering System**.
Requirements express desired states and obligations; designs choose technical
solutions; implementation specifications describe executable work. Code, tests,
reviews and operational observations provide evidence, not product authority.

The supervisor remains the primary orchestrator. Specification reviews and
technical decisions are autonomous. Never require the user to review or approve
requirements, decompositions, designs, plans or files. Ask a focused question only
for a material unresolved product/policy decision, record the answer and resume.
Existing independent review, consultation, debugging, permissions and actual-merge
gates remain effective. This rollout does not change already-loaded agent roles.

## Investigation and architectural choice

At source `4f607d36cfcb5031b669e847d8c7cf1be8d0d311`, development records are
date-named Markdown under `docs/specs/` and `docs/plans/`. There is no structured
specification ledger, stable specification ID scheme or semantic graph to extend.
`docs/scripts/generate-record-indexes.mjs` inventories Markdown; the development
records guide explicitly declines to infer authority or semantic links from
placement. Preserve this useful browsing infrastructure and all historical records.

Orchestration lives in `.opencode/agents/` and `.opencode/skills/`; configuration
contains no repository runtime orchestration hooks. Python scripts, pytest,
`make opencode-check`, and guarded Git/GitHub wrappers are the executable tooling.
Orca setup is documented in `docs/dev/features/opencode-agent-workflow.md` and
automation guides; Orca's implementation is not in this repository.

Three approaches were considered:

1. **One Git-native structured ledger and a small Python library/CLI (chosen).**
   Provides independently addressable entities, transactions and graph validation
   without dependencies or a service. Centralized writes require serialization.
2. Metadata scattered through Markdown/frontmatter. Close to authoring, but adds
   parser and cross-file transaction complexity and pressures legacy migration.
3. Prompt-only requirements. Low initial cost, but no reliable identity,
   validation, reverse traversal or executable coverage analysis.

Canonical data lives in `docs/requirements/ledger.json`; a deterministic generated
`docs/requirements/index.md` is a projection, never a second authority. Use
standard-library Python in `scripts/requirements.py` and focused private modules.
Do not couple this methodology graph to Space's application graph/Fennel runtime.

## Requirements entity and revisions

Use one Requirement entity with opaque immutable `REQ-<uuid>` identity. IDs do not
encode classification, wording or location. Initially support classifications
`goal`, `outcome`, `capability`, `behavior`, `constraint`; do not impose an
abstraction ladder. Schema evolution can extend classifications explicitly.

Each requirement records statement, rationale, acceptance criteria, provenance
(source reference/excerpt or current contract reference, actor, date, origin),
lifecycle and normative revision. Provenance must distinguish explicit user
authority from technical interpretation, assumptions and descriptive evidence.
Sources justify obligations without becoming obligations themselves.

Lifecycle is `proposed`, `active`, `superseded`, `rejected`. Activation needs
grounded authority/rationale; rejection and supersession preserve rationale and
history. Terminal records are not deleted or silently reactivated. Supersession
atomically records new-to-old relation and old terminal state. No satisfaction,
evidence or links transfer to the replacement automatically.

Statement, classification or acceptance-criterion changes conservatively advance
the requirement revision; keep prior normative snapshots and change rationale.
Locator/title changes preserve artifact identity. Revision-specific assessments
and observations remain historical, not current after their requirement changes.

## Typed recursive graph

Store each relation once with source, target, type, rationale, provenance and
confidence `explicit`, `inferred` or `uncertain`. Inference is candidate evidence,
never normative authority. Promotion requires a grounded explicit decision.

| Source → target | Meaning | Validation |
| --- | --- | --- |
| A `refines` B | A makes B more precise | Requirement endpoints; combined refinement/derivation decomposition acyclic |
| A `derived_from` B | A was established based on B with rationale | Requirement endpoints; not synonymous with refinement or contribution |
| A `contributes_to` B | A helps achieve B, without sufficiency | Requirement endpoints; cycles allowed and diagnosed |
| A `depends_on` B | A relies on B | Requirement endpoints; cyclic components reported, not generic corruption |
| C `constrains` X | Constraint C restricts acceptable satisfaction/solution X | Source constraint, target requirement/design/implementation; constraint-to-constraint permitted |
| A `conflicts_with` B | Incompatible obligations under recorded conditions | Requirement endpoints, one lexicographically canonical symmetric pair |
| A `supersedes` B | A replaces B | Explicit requirement endpoints; acyclic lineage, B superseded |

No self edges. Duplicate logical relations and broken references fail validation.
Same-class refinement, shared refinements and multiple parents are valid.
Mixed dependency/contribution/constraint cycles must terminate in queries; a
visited set prevents loops. Cycle diagnostics do not mean traversal was truncated:
`truncated` means an actual node/depth/result bound was reached.

Conflicts may remain unresolved in a structurally valid ledger. Disposition
records explanation and authority, not proof that incompatible active statements
are now compatible. Readiness treats material applicable unresolved conflicts as
blocking. Design/implementation discrepancies are reconciliation findings, not
artificial requirement-conflict edges between arbitrary artifact types.

## Traceable artifacts

The same ledger contains a minimal linked-artifact registry, not a source inventory.
Designs, implementation specs, code references, test definitions and evidence have
stable IDs with kind, title, repository-relative locator, optional selector and
content identity. New designs and implementation specs record applicable IDs and
links without duplicating full requirements. Registry links provide machine
traceability; documents remain readable Markdown. Historical records remain
discoverable without registration or mandatory backfill.

| Relation | Permitted endpoints |
| --- | --- |
| `addresses` | design/implementation → requirement |
| `realizes` | implementation → design |
| `implements` | code → implementation |
| `verifies` | test → requirement |
| `exercises` | test → code |
| `supports` | evidence → requirement/test |

Explicitly justified shorter paths are supported by direct `addresses`, `verifies`
and `supports` edges; no pipeline of artificial intermediate artifacts is required.
Code/test locators and Git references aid backward investigation without requiring
every source file to link directly to a requirement. A test definition is not a
test run. An artifact locator's existence proves neither correctness nor coverage.

Resolve repository locators safely: reject absolute paths, traversal, outside-root
symlinks and non-file artifacts where files are required. External evidence is a
safe descriptive source reference; do not fetch or execute it. Preserve private
logs, credentials and raw session payloads outside published ledger data.

## Satisfaction and verification

Lifecycle, satisfaction claims and verification are independent:

- Append explicit requirement-revision assessments `unaddressed`, `partial`,
  `satisfied`, with rationale, actor, time and source/evidence references.
- Record verification per acceptance criterion and requirement revision. Results
  distinguish absent, pending, passed, failed and inconclusive. Include method,
  procedure/command description, environment, observation, timestamp, safe durable
  evidence reference and declared dependency content identities.
- Methods include empirical measurement, scenario, automated test, audit,
  analysis and inspection; criteria declare empirical or analytical applicability.
  Empirical criteria require empirical observations, not capability test passes.
- Currency is `current`, `stale` or `unknown`. Changed normative revision,
  criteria, evidence content or declared dependency digests invalidate currency.
  Missing dependency declarations mean unknown applicability, not proven fresh.
  Unrelated repository commits alone do not invalidate evidence.
- Latest applicable observation per criterion governs; an older pass cannot hide
  a later failed, inconclusive or pending result. Historical observations remain.

No edge, descendant satisfaction, completed plan or merged implementation derives
even partial satisfaction automatically. A supported/implemented capability can
be verified while its strategic parent awaits empirical evidence indefinitely.
Verification records describe authorized execution elsewhere; the ledger tool
never executes stored commands or claims to collect production metrics.

## Query, coverage and impact contracts

All reports expose confidence, original edge orientation, reasons/paths, unknowns,
scope and bounds. Queries traverse both directions without editable inverse edges.
Return truncation honestly; never claim a complete blast radius from incomplete
traceability. Shared artifact locators can justify potential impact, not normative
dependency. Inferred links remain inferred throughout a path.

Coverage separates trace coverage, recorded satisfaction claims and criterion
verification. Detect behavioral requirements lacking explicit design justification,
designs without requirement justification (legacy distinguished), missing linked
implementation/evidence, broken/stale references, unaddressed applicable
constraints, orphaned refinements, unsupported goals/outcomes and superseded
dependencies. Missing links mean unknown/unlinked, not proof of absent behavior.
High-level goals can have indirect design trace through contributors/refinements;
that never demonstrates outcome achievement.

Impact includes potential effects both upward toward purposes and downward toward
obligations/solutions. Use relation-and-direction rules: changes to a broader
requirement affect refinements/derivations; changes to a child/contributor can affect
its purpose; changes to prerequisites affect dependents; constraints affect their
targets and target changes require constraint rechecking; conflicts affect both
ends; supersession flags old dependents for reconciliation. Artifact chains are
traversed to designs, implementations, code, tests and evidence and back to governing
requirements. Label upward contribution impact as potential, not guaranteed.
Do not mistake traceability reachability for a proven behavioral dependency.

Structural validation is distinct from scope-specific readiness. Valid pending
empirical outcomes are not global merge failures. Readiness accepts the explicit
change scope and material affected criteria/constraints; unresolved material
violations in that scope block or require an existing explicit exception. It
cannot grant Git permissions, bypass reviews or substitute for actual tests.

## Library, CLI and transactional writes

One shared implementation owns parsing, schema/graph validation, queries,
reconciliation context, mutation and deterministic rendering. Provide CLI verbs
`init`, `apply`, `query`, `validate`, `render` with strict JSON request files/stdin
for complex requests. Query operations include get/search, forward/backward trace,
impact, coverage, reconciliation context and scoped readiness. Write operations
create/revise requirements, transition lifecycle, register/update artifacts,
add/revise relations, append assessments/verifications and record conflict
dispositions. Batch related operations transactionally when necessary.

Reads never initialize, repair or modify data. Initialization refuses an existing
ledger. Reject duplicate JSON keys, non-finite values, unknown schema versions,
unknown fields, invalid IDs/endpoints and malformed records. Errors are nonzero,
machine-readable and actionable; valid incomplete coverage is not corrupt data.

Every canonical mutation carries expected ledger revision and actor. Serialize
writers with an advisory lock covering load, comparison, complete candidate
validation and atomic replacement. Stale writers and failed canonical replacement
preserve old canonical content. Locks/tempfiles are local ignored artifacts.
Index rendering is derived and separately checkable: failure after successful
canonical write reports the committed revision and stale projection explicitly,
never falsely claims rollback. Read-only `render --check` detects stale output.

The supervisor may inspect and query; canonical ledger mutations remain assigned
to implementers. Planners/reviewers consume repository data and supplied reports
without new execution/edit permissions. Preserve fast/live explicit exceptions.

## Shared reconciliation and autonomous orchestration

Add a focused reusable requirements-reconciliation skill, not another orchestrator.
The supervisor classifies intent (feature, existing behavior change, goal/outcome,
bug, maintenance, exploration, clarification) independently of execution ceremony
(read-only, tiny strict, full strict).

Before intended behavior changes, reconcile relevant requirements at all useful
levels, designs/plans, code/tests, decisions and evidence. Retrieval provides
candidate context; agents inspect real sources and make semantic judgments. The
CLI does not claim to understand natural language or automatically establish
equivalence, authority, conflicts or correctness.

Record a proportional reconciliation conclusion: already covered, clarification,
refinement, extension, conflict, supersession, missing requirement, design defect,
implementation defect or maintenance. Multiple findings can apply. Identify what
changes, why, applicable constraints, uncertainty, authority, downstream impacts
and verification. Do not generate artifacts unnecessarily.

High-level intent can require justified decomposition, not a full speculative tree.
Capabilities often contribute to goals rather than being logically derived from
them. Design limitations do not define product obligations. A reported bug is
evidence: reproduce, discover governing intent and classify before correcting.
Implementation defects reuse existing requirements; design defects revise designs;
real gaps establish obligations grounded in authority. Maintenance preserves
behavior and assesses constraints without synthetic requirements. Read-only audit
remains mutation-free. Discoveries during design/planning/execution/review route
back to the same reconciliation capability.

Integrate requirements into supervisor, brainstorming, planner, implementer,
reviewer, debugging, SDD and finishing guidance, and relevant fast/live guidance
without imposing strict-worker gates on those primary exceptions. Remove stale
ordinary human-approval transitions. Preserve focused clarification/resumption,
dual-model design consultation, fail-closed handoffs, fix caps/adjudication,
validation-failure diagnosis, capability refusals and final merge polling.

Requirements, design and implementation-spec reviews are scoped independent
reviews using the existing reviewer and exact pending-diff/revision or committed
range. Assess intent, authority, derivation/contribution, verifiability, conflicts,
constraints, coverage and unjustified expansion. No artifact approval by the user.
Reviews do not rewrite product policy or auto-approve later artifact revisions.

## Compatibility, documentation and verification

No bulk historical requirements generation. Seed only actual current-task
obligations grounded in this explicit user contract. New behavior-changing work
uses requirements-driven intake; historical docs remain readable/discoverable.
Document actual tool APIs and limitations, generated index integration, templates,
workflow ownership, evidence semantics, and Orca configuration/restart boundary.

Testing under `scripts/tests/` covers strict schema, creation and stable identities,
revisions/history, lifecycle/supersession, recursive many-to-many typed relations,
forbidden/allowed cycles, conflicts, locator safety, concurrent stale writers,
atomic-write/index failure, evidence freshness and latest results, forward/backward
traces, confidence, classification-aware coverage and bounded impact.

Executable workflow fixtures cover all fifteen user scenarios: missing and existing
requirements; goal decomposition; multi-capability outcomes; multi-goal capability;
cross-branch constraint; requirement conflict; intent/design conflict; implementation
defect without new requirement; design defect; bug revealing gap; maintenance
without requirement; requirement change across designs; design discovery returning
to reconciliation; strategic outcome awaiting empirical evidence.

Demonstrate (A) goal-driven feature, (B) existing behavior change, (C) bug correction,
(D) verified capability with unproven strategic outcome. Fixture executions test
real ledger operations and routing decisions, not genuine remote execution or
live-agent compliance. Run separate read-only agent pressure scenarios before and
after skill changes, retaining exact baseline and revised observations privately
and safe summaries here. Never describe text-search tests as proof of agent behavior
or simulated merge as actual merge. The current implementation itself must pass
independent review, relevant Python/policy/docs tests and actual remote CI/merge.

No Fennel/C++ runtime change is planned; runtime rebuilds/full Space tests are not
local prerequisites for this pure Python/prompt/docs surface unless scope expands.

## Related records

- [Implementation plan](../plans/2026-10-29-requirements-driven-engineering.md)
- [Progress and reconciliation](../plans/2026-10-29-requirements-driven-engineering-progress.md)
