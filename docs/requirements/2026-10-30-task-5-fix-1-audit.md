# Task 5 fix round 1: dependency audit

Assignment `REQ-IMPL-5`, supervisor/strict SDD, branch `juicyrebel/scoter`.
FIX_BASE `15957052ffc9d5ff465b8841d6a73bdfd9aed587`; original BASE
`e4efadf63202b859e65496da243c5fcacce18820`. Accepted Important findings R1-1/R1-2
from independent reviewer `ses_e7601615fffeNHdP1mh12CHBTl` (valid candidates_found,
delivery correction_used=0). Same author/fix round; interrupted dispatch did no work.

## Observed defects and RED

The retained initial ten analytical observations all declared the same eighteen
registered paths. That omitted imported library initialization, graph validation
and `locking.py`, the CLI test helper, actual inspected agents/skills, `AGENTS.md`,
`Makefile`, and docs build/configuration/navigation inputs. The prior safe execution
summary remains historical evidence of observed commands, **not proof of complete
dependency declarations**. The tool cannot infer omissions from a nonempty manifest.
Its `current` value means only the declared bytes, anchored evidence and normative
revision agree. No production currency algorithm change is required for this fix.

Actual focused RED command:
`python3 -m pytest scripts/tests/test_requirements_demos.py -k 'independently_sourced or material_tested or observation_stales' -q --tb=short`
(through transparent `rtk proxy`): **13 failed / 7 deselected in 1.82s**.
Ten cases identify omitted inputs. Two real copied-seed fixture observations remain
`current` after the copied tested supervisor file changes, instead of becoming
`stale`. The separate proposed-future-requirement fixture fails the old blanket
historical provenance assertion. No real supervisor source was mutated.

## Audited input groups and claim boundaries

Every analytical criterion is re-audited, not just the two workflow records:

| Seed criterion | Material declared group | Why |
| --- | --- | --- |
| Native entity/history | Core | CLI/library/schema/history tests and helpers |
| Typed recursive graph | Core | Relation validation and real graph report tests |
| Artifact trace | Core | CLI/graph/render/demo definitions |
| Strict transactions | Core | Includes actual advisory locking and graph/schema validation |
| Evidence/currency | Core | Evidence/store/schema/query tests and helpers |
| Coverage/impact/readiness | Core | Graph applicability/report/evidence machinery |
| All-intent reconciliation | Core + policy | Actual workflow touchpoints and preserved policy checks |
| Autonomous review/safeguards | Core + policy | Actual agents/skills/configuration and guarded policy tests |
| Historical compatibility | Core + docs | Actual seed tests and record inventory/build/navigation inputs |
| Documentation/demos/validation | Core + policy + docs | Explicit full relevant gate criterion |

**Core** conservatively includes the complete requirements library (including
`__init__.py`, `locking.py`, relation validators), CLI, all requirements test
definitions and helper, `.gitignore`, `Makefile`, `AGENTS.md`, reviewed normative
design/plan, API/templates and every agent/skill directly read by
`test_requirements_workflow_contracts.py`: eight named agents, five owning skills,
plus the shared reconciliation skill. Grouping is conservative per-file, not an
assertion that every line was executed or every semantic obligation is proven.

**Policy** additionally includes tracked `.opencode/` sources, `.opencode/opencode.json`,
tracked `scripts/` test/wrapper/fixture sources and `.github/workflows/test.yml`,
covering the actual policy gate and docs automation tests' repository inputs.
This is a deliberately broad content boundary, not universal live-agent compliance.

**Docs** additionally includes tracked build-included docs sources (including
navigation config/theme, package/lockfile, scripts/tests, record pages and mutable
progress), `.github/workflows/test.yml`, docs automation tests' external policy
inputs, and `assets/pics/space.png` read by the icon-sync command. Excluded
`dev/openai`, `dev/zai`, `dev/fennel` sources follow actual VitePress `srcExclude`.
Generator outputs (record/journal/devlog indexes, synced icon, dist/cache), canonical
ledger/requirements index, and this run's new evidence outputs are not independent
source prerequisites: generators and canonical append/render produce them. The
evidence reference anchors the observation summary separately. Existing older safe
evidence pages are ordinary docs source inputs, not edited/resealed history.

Declared digest maps enumerate the actual captured paths. They cannot detect new
undeclared files, inventory changes or missing assumptions automatically. Rerun and
re-audit after relevant changes. In particular, progress is now a docs dependency:
subsequent progress edits must make docs observations stale until revalidated;
updating the progress artifact's registry digest alone cannot freshen observations.

## Correction protocol (no premature pass)

Append ten **pending** inspection observations with audited manifests, explicitly
recording that full validation is not yet complete. Preserve all original ten
observations/assessments byte-for-byte as structured records. Then execute the
focused/full relevant gates on the amended source and record a separate safe
completed-run summary before appending ten **passed** observations with actual
procedure/environment/time and freshly captured audited manifests. The intermediate
pending records are not passing test evidence. No partial assessment is promoted.

Canonical mutations use real CLI `apply --stdin` with actor and loaded exact
`expected_revision`, capturing returned revisions/IDs before dependent operations.
No direct JSON edits, init replay, rewritten prior digests or automatic satisfaction.
The historical seed test applies historical provenance/activation/initial-assessment
checks only to the twelve retained IDs; strict schema/graph validation still applies
to the entire live ledger, including independently sourced proposed requirements.

This page records completed audit/RED findings and the protocol, not an advance claim
that pending checks passed. Actual GREEN/gate output belongs to the subsequent
completed-run evidence and author fix handoff. Independent re-review and safeguarded
actual final integration remain controller-owned and pending.
