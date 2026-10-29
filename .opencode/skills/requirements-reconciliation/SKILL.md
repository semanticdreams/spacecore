---
name: requirements-reconciliation
description: Use when receiving a goal, outcome, feature, behavior change, bug, maintenance, exploration or clarification request, or discovering intent, design, implementation or evidence discrepancies during development or review.
---

# Requirements reconciliation

Reconcile desired behavior before choosing solutions. This is a shared semantic
capability, not a new orchestrator, entity or mandatory document pipeline.
New intended-behavior development is requirements-driven; ceremony is separate.

## Source-to-conclusion recipe

1. Classify intent (goal/outcome, feature, change, bug, maintenance, exploration,
   clarification) separately from read-only, tiny strict or full strict execution.
2. Inspect original intent/provenance, relevant ledger records at useful levels,
   designs/plans, code/tests, decisions and observations. Query results are candidate
   context, not natural-language judgments or complete impact proof. Follow unknowns,
   confidence and bounds back to sources; missing links mean unknown, not absent behavior.
3. Compare obligations with solutions. Explicit source records establish authority;
   a technical design cannot silently replace them. With explicit never-auto-send
   intent and contrary auto-send design, inspect provenance: with no evidence of policy change,
   classify a design defect and revise the solution autonomously. Do not manufacture
   product ambiguity. Genuine unresolved product/API/data policy gets one focused
   human question; record the answer and resume automatically. Technical uncertainty
   follows the existing consultation contract, reusing unchanged reconciled decisions.
4. Record the following conclusion in the existing handoff/progress record. Use one
   compact paragraph for simple work; expand only material findings. Read-only work
   uses a report-only conclusion: no forced tracked record or mutation.

### Required conclusion slots

- **Conclusion:** already covered, clarification, refinement, extension, conflict,
  supersession, missing requirement, design defect, implementation defect or
  maintenance; multiple findings may apply.
- **Scope and sources:** intended behavior, applicable requirement IDs/revisions,
  artifact IDs/locators and original intent/evidence inspected; explicit unknowns.
- **Authority and uncertainty:** source/excerpt and justified interpretation versus
  assumption/descriptive evidence; confidence, unresolved choices and owner.
- **Changes and impacts:** what changes, why, retained identities/links, affected
  requirements/designs/plans/code/tests/evidence and potential downstream effects.
- **Constraints and verification:** applicable constraints, material criteria,
  observation/currency gaps, focused checks and empirical follow-up where required.
- **Next transition:** report-only, reuse, reviewed ledger/artifact change, debugging,
  consultation or focused clarification, followed by the existing autonomous workflow.

## Identity, relations and evidence

| Situation | Contract |
| --- | --- |
| Existing obligation/solution | Reuse opaque immutable `REQ-<uuid>` / `ART-<uuid>` identities; IDs do not encode classification or location. Classifications `goal`, `outcome`, `capability`, `behavior`, `constraint` are not a fixed hierarchy. |
| More precise obligation | `refines`: child makes parent more precise. |
| Established based on another obligation | `derived_from`: record authority and derivation rationale, not merely usefulness. |
| Capability helps a goal | `contributes_to`: contribution without sufficiency; a deadline is not derivation evidence. Decompose only as justified by intent. |
| Bug/maintenance | Reproduce a bug and discover governing intent first. An implementation defect reuses requirements; a design defect revises designs; a genuine gap establishes grounded obligations. Behavior-preserving maintenance: no synthetic requirement. |
| Changed obligation | Preserve normative history, rationale and provenance; supersession uses a distinct replacement, never resurrection or silent evidence transfer. |
| Evidence | Lifecycle, explicit assessment and criterion verification are separate: no automatic satisfaction, even partial, from edges, descendants, tests, plan completion or merge. Empirical criteria require empirical observations. Latest applicable result governs; failure is not stale merely because it failed. |

Capabilities can pass while strategic outcomes remain pending indefinitely: that is
not a global merge freeze. Scope readiness to material affected criteria/constraints;
retain unknowns, conflicts and negative observations. Keep inferred links as candidates,
not authority. Impact reachability is not normative inheritance or sufficiency.
Use the reconciled applicability rules in the query reports, not arbitrary graph paths.

## Existing tool and ownership

Canonical data: `docs/requirements/ledger.json`; derived index:
`docs/requirements/index.md`. Historical documents remain discoverable and usable
without registration or bulk backfill; do not fabricate historical obligations.
Register only linked artifacts using existing typed relations (`addresses`,
`realizes`, `implements`, `verifies`, `exercises`, `supports`, `constrains`).
Keep source provenance distinct from technical interpretations.

The controller may run read-only queries. A bash-denied planner/reviewer/advisor
requests the same query from the controller, then inspects supplied records and
original sources within its permissions. Reads never initialize/repair/write.
Substitute actual IDs from inspected records in these request examples:

```sh
python3 scripts/requirements.py query --repo-root . --stdin
```
```json
{"op":"reconciliation-context","args":{"scope":["REQ-<uuid>"],"max_depth":32,"max_paths":1000}}
```
```json
{"op":"readiness","args":{"scope":["ART-<uuid>"],"material_criteria":[],"material_constraints":[]}}
```

Select actual material criteria/constraint IDs after inspection; empty lists are
not a blanket clearance. Other query operations: `get`, `search`, `trace`, `impact`,
`coverage`; `get` includes `criteria_latest` for a requirement. CLI verbs are `init`, `apply`, `query`, `validate`,
`render`; use `--request FILE` instead of `--stdin` for saved JSON requests.

Canonical writes are implementer-owned in strict flow, assigned and independently
reviewed with normal progress records. A revision envelope for `apply --stdin`:

```json
{"actor":"implementer/session","expected_revision":7,"ops":[{"op":"revise-requirement","args":{"id":"REQ-<uuid>","reason":"Recorded source clarifies existing intent","rationale":"Justified by the inspected source; preserve its provenance"}}]}
```

Use actual current revision/ID/source rationale, not these placeholders. Obligation
changes must carry grounded provenance; activation/terminal transitions require
authority. Use existing operations, not direct JSON edits. Run `validate` and
`render --check`; ordinary rendering is a writer operation. Stale writes and
projection errors fail loudly; a projection error may report an already committed
ledger revision. Never assume rollback or blindly repeat the mutation.

## Autonomous reviews and transitions

Strict requirements, design and implementation-spec artifacts each receive an
independent existing-reviewer review over the exact pending diff (including additions
and ledger revision) or complete recorded `BASE..HEAD` range. Supply intent,
authority, IDs/revisions, constraints, derivation/contribution, verifiability,
coverage, conflicts and expansion risks. Retain the reviewer's declared output
schema. Self-review is not independent review; changed artifacts need review of
their changed range. After pass, advance automatically, never user artifact approval.

Discoveries during design, planning, execution, review or debugging return to this
recipe, not silent scope expansion. Existing handoff integrity, consultation,
diagnostic gates, fix caps/adjudication, capability refusals, validation and actual
merge evidence still govern. Fast/live keep direct edits, no mandatory extra
artifacts or per-change worker/review gates, explicit-only wrap-up and one
observational review; live manual-before-edit/validated-refresh remains intact.

Static contracts and fixture runs do not prove live-agent compliance. After reviewed
`.opencode/**` changes, quit and restart OpenCode; running roles retain loaded rules.
