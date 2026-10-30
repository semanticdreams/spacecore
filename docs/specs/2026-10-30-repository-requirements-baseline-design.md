# One-time repository requirements baseline audit

## Authority and reconciliation

The maintainer explicitly requests a one-time repository-wide top-down and bottom-up
requirements discovery, direct reconciliation of the existing ledger, meaningful
traceability, autonomous independent review, idempotent resumption, and a concise
coverage/gaps/contradictions report. This is exploration plus evidence-backed
requirements backfill/refinement, using the full strict workflow because its scope
is repository-wide. It is not new product development or a discovery system.

Initial source snapshot: `fec176453c88fa1c47f22b7fe1d447dfe0ba281b`, branch
`juicyrebel/ridley`; clean tree verified by the controller. Canonical ledger revision
29 validates and its rendered index is current. Its 12 requirements and 26 artifacts
cover the recently merged methodology, not the wider Space product.

Conclusion: missing product representation, with existing methodology obligations
reused. Retain especially `REQ-8e50a634-76ae-4100-9f60-90e4552ec954`
(intent reconciliation), `REQ-26f18ef2-15f6-4278-b9a1-9c7b4b246e5c`
(historical preservation), `REQ-1970c4a9-a5dc-4d1b-93ce-dc88ed42df84`
(traceability), and `REQ-2824ad77-fbc5-4db6-ac9a-732af10eeabc`
(assessment/evidence separation). The original seed-only boundary describes the
original task; this explicit follow-up authorizes grounded discovery, not wholesale
activation of historical plans. Do not weaken its historical-preservation contract.

## Approach and boundaries

Choose evidence-backed capability-family reconciliation using the existing CLI and
tracked audit documentation. Reject a document-per-requirement import (duplicates,
historical activation, solution-derived authority) and inventory-only delivery
(does not update the ledger as requested). Families organize this audit, not the
schema or a new normative hierarchy. No new infrastructure, recurring job, schema,
tooling, application/test changes, or rewritten historical records.

Inventory all tracked documentation families; explicitly account for every existing
design and plan/progress filename. Initial discovery enumerated 168 designs and 194
plan/progress records, excluding indexes; workers must verify these at the frozen
snapshot. Inventory feature, goal/milestone, ADR, SDK, user, journal, reference and
notes families, plus canonical C++/Fennel code, tests and scripts. Inspect original
source and relevant Git history before deciding authority/currentness. External
API mirrors, vendor content, historical Python prototypes and incidental examples
are not normative Space intent. Record sampling/depth honestly: filename inventory
is not complete semantic review of every line.

Each design/plan source receives a disposition and rationale: grounded obligation,
supporting solution/evidence, duplicate/reused, historical/replaced, reference-only,
or unresolved gap. Other source families receive explicit coverage boundaries and
the same authority distinctions. Never label an unread historical source superseded
merely from its date/name. Preserve source excerpts/locators and resulting IDs where
applicable; register only artifacts with justified semantic links.

## Reconciliation and status rules

1. Search and inspect the current ledger before creation, comparing semantics and
   provenance as well as literal terms. Reuse existing requirement/artifact IDs.
2. Backfill independently meaningful obligations supported by explicit intent or
   justified interpretation. Keep proposed roadmaps proposed. A current documented
   contract can justify an active capability/constraint; source placement or a plan
   completion checkbox cannot. Implementation-only candidates remain descriptive
   gaps until grounded. Do not manufacture maintenance requirements.
3. Acceptance criteria must be scoped and verifiable. Qualitative strategic outcomes
   remain unverified with measurement/threshold gaps; do not invent numeric targets.
4. Use `refines` for precision, `derived_from` only for evidenced derivation, and
   `contributes_to` for assistance without sufficiency. Use existing typed artifact
   relations for design, plan, code, test and evidence. A complete chain is preferred
   only where original sources support it. Record missing links instead of filling
   them speculatively. Constraints need evidenced applicability.
5. Separately report documented intent, implementation presence/partiality, test
   definition presence, historical reported verification, current observations and
   strategic satisfaction. No automatic satisfaction/partial assessment from links,
   code, tests, plan completion or merge. Do not claim runtime verification from this
   docs/ledger audit. Preserve existing observations and normative history.
6. Inspect contradictory provenance. Explicit intent outranks contrary technical
   narrowing absent policy-change evidence: record the solution/coverage defect,
   not invented policy ambiguity. For example, broad temporal-platform intent versus
   bounded closeout needs original-source/Git investigation; no broad-completeness
   claim follows from passing bounded tests. Recording this gap does not require
   deciding new product scope or repairing application code in this audit.

## Existing data flow and idempotence

Implementers alone mutate `docs/requirements/ledger.json` through existing
`apply` operations with exact `expected_revision`, then render the existing index.
No direct JSON/index editing or initialization. Split dependent transactions using
actual returned IDs. Search both obligation semantics and artifact locators; inspect
canonical provenance because literal search is not semantic/provenance search.

Use `docs/requirements/2026-10-30-repository-reconciliation.md` for the one-time
source/disposition, IDs, decisions and coverage report, and an ordinary progress
ledger under `docs/plans/`. These are project history, not a new database. Record
batch revisions/IDs as soon as returned. Resume by comparing the report with current
canonical records, not replaying requests. A post-commit projection failure requires
inspection of `committed_revision` and rendering, never blind retry. Demonstrate a
second reconciliation sweep produces zero justified new records/links and no ledger
byte/revision change; a no-op write is not required.

## Verification and acceptance

Independent reviewers inspect exact artifact and complete batch/fix ranges, including
additions and ledger revisions, original authority, semantic duplication, criteria,
typed relationship directions/confidence, justified contribution, coverage, conflicts
and unjustified expansion. Use ordinary consultation/fix-cap gates and automatic
transitions; no intermediate human artifact approval.

Required local validation: ledger `validate`, `render --check`, `make requirements-check`,
source-manifest set comparison, duplicate/locator/relation inspection, targeted
coverage/reconciliation/trace queries with bounds reported, and second-sweep no-change
evidence. Run existing documentation/index/build checks appropriate to added pages.
No runtime build or Fennel tests are warranted solely by documentation/ledger changes;
test presence is not fresh execution evidence. No prompt/policy changes are planned.

Acceptance: all source families and historical spec/plan filenames accounted for;
grounded missing requirements backfilled and existing ones reused/refined; supported
goal-to-solution/test links established; uncertainty, missing links, partial
implementation and outcome gaps visible; idempotence demonstrated; focused checks
green; independent pass over all changes. Finish with clean committed state, guarded
current `origin/main` evaluation and default PR/merge-queue integration per repository
policy. Final summary states discovered/created/reused/linked counts, implementation
coverage denominator, significant contradictions, verification limits and open gaps.
