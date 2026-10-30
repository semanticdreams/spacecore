# Requirement and reconciliation templates

Use these as proportional authoring aids, not mandatory new documents or CLI
symbolic-ID support. See the [actual API](/dev/features/requirements-driven-engineering)
and [current records](/requirements/). Canonical changes use assigned implementer
CLI transactions, not pasted direct ledger edits. Inspect and retain existing IDs.

## Grounded requirement creation

Use the current ledger revision and a genuine source, excerpt and verifiable
criterion; this example uses placeholders deliberately. `create-requirement`
returns an opaque ID; use that returned ID in subsequent link/activation requests.

```json
{
  "actor": "implementer/session",
  "expected_revision": 0,
  "ops": [{
    "op": "create-requirement",
    "args": {
      "classification": "behavior",
      "statement": "Desired behavior, independent of a technical solution",
      "rationale": "Why this follows from the inspected intent",
      "acceptance_criteria": [{
        "id": "c1",
        "text": "Observable, bounded acceptance condition",
        "applicability": "analytical"
      }],
      "provenance": {
        "source_reference": "Original user contract or recorded clarification",
        "excerpt": "Exact relevant source wording",
        "actor": "implementer/session",
        "date": "2026-10-29",
        "origin": "user_intent"
      }
    }
  }]
}
```

Choose `empirical` when acceptance needs real outcome observation. Do not replace
it with an analytical test just to obtain a pass. Separate justified interpretation
from explicit intent; source documents are not requirements by mere registration.
Activation requires `transition-requirement` with ID, `to: active`, grounded
`reason` and `authority`. Revision retains ID/history; supersession creates/uses a
distinct replacement. No transfer of satisfaction.

## Reconciliation conclusion (existing handoff/progress record)

- **Conclusion:** already covered / clarification / refinement / extension /
  conflict / supersession / missing requirement / design defect / implementation
  defect / maintenance (combine only when justified).
- **Scope and sources:** intent, actual IDs/revisions, artifact locators, inspected
  original sources, query bounds, explicit unknowns.
- **Authority and uncertainty:** source/excerpt; interpretation versus assumption;
  confidence; genuine unresolved policy choices and their owner.
- **Changes and impacts:** what changes and why; retained identities; affected
  designs/plans/code/tests/evidence; potential downstream effects, not complete proof.
- **Constraints and verification:** applicable constraints, material criterion
  pairs, observation currency, negative results, checks and empirical follow-up.
- **Next transition:** report-only / reuse / independently reviewed ledger or
  artifact change / debugging / bounded consultation / focused clarification,
  then autonomous resume under the existing workflow.

Read-only audits stay report-only. Maintenance does not create a synthetic REQ.
Defects reuse intent unless inspected authority demonstrates a real gap. A contrary
technical solution is not by itself a product-policy question.

## Design / implementation-spec trace note

- Intent and requirement IDs/revisions addressed; applicable constraint IDs.
- Original source authority and derivation/refinement/contribution rationale.
- Actual artifact IDs and typed links (not a fixed required document ladder).
- Alternatives and reconciled technical decisions reused; unresolved questions.
- Validation criteria, material scope, safe evidence and declared dependencies.
- Independent review range/revision and autonomous next transition.

Do not copy the complete ledger into every document. Register only linked artifacts;
unregistered historical records remain useful outside semantic coverage.

## Verification and handoff note

Record the actual command/procedure, environment, observation/time, result, safe
durable evidence and SHA-256 dependency identities. Separate a test definition from
a test run, result from currency, and verification from explicit satisfaction claim.
State scoped readiness, truncation/unknowns and limits. State which independent
reviews remain and whether actual CI/`mergedAt` is available. Never claim fixture
runs prove live-agent compliance, production outcomes or final merge.
