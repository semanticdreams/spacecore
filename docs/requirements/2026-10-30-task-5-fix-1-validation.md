# Task 5 fix round 1: observed validation

Assignment `REQ-IMPL-5`, same implementer/current delegated author (session ID not
exposed), supervisor/strict SDD, branch `juicyrebel/scoter`. FIX_BASE
`15957052ffc9d5ff465b8841d6a73bdfd9aed587`; original BASE
`e4efadf63202b859e65496da243c5fcacce18820`. Accepted R1-1/R1-2, not a new fix round
or delivery reset. This safe summary is author evidence, not independent approval.
See the [input audit](./2026-10-30-task-5-fix-1-audit).

## Actual commands and output

All commands below were actually run through the transparent `rtk proxy` launcher,
with complete terminal output observed, not inferred from truncated summaries.

| Command | Observed result |
| --- | --- |
| `python3 -m pytest scripts/tests/test_requirements_demos.py -k 'independently_sourced or material_tested or observation_stales' -q --tb=short` before fixes | **13 failed / 7 deselected in 1.82s**: blanket provenance rejection, ten missing-input assertions, two `current` rather than `stale` mutations |
| Same focused command after fixes/audited pending capture | **13 passed / 7 deselected in 15.05s** |
| `python3 -m pytest scripts/tests/test_requirements_*.py -q` | **320 passed in 87.03s** |
| `make requirements-check` | **320 passed in 93.46s**, revision 13 valid and projection current |
| `make opencode-check`, 1800000ms command allowance | **320 passed in 74.17s**, permissions **pass/no violations**, **1181 passed in 730.47s** |
| From `docs/`: `npm run test:scripts` | **56 passed**, no failures/skips/cancellations |
| `npm run records:indices` | passed, inventories unchanged |
| `NODE_OPTIONS=--max-old-space-size=4096 npm run docs:build` | passed in **164.66s**, including generated indexes/icon, VitePress and built navigation |
| `npm run records:check` after build | passed, **186 plans / 165 specs** |

Python 3.12.3 / pytest 9.1.1, Linux; Node 18.19.1 / VitePress 1.6.4. Python output
had no warnings. Docs retain known `fnl` highlighting fallbacks and large-chunk
warning; no dependency or warning-suppression change. No unexpected validation
failure occurred in this fix round. Space compile/build/constraints/runtime are
not applicable; constraint impact **not applicable**.

## What these runs validate

The complete requirement suite includes all fifteen scenarios/four demos and the
new thirteen accepted-finding regressions. General schema/graph validation loads
the entire live ledger. Historical provenance/activation/initial-partial checks
now select the twelve retained seed IDs only. The isolated future-requirement
fixture uses real CLI apply with independent user provenance, proposed lifecycle
and no assessment; the historical seed contract accepts it.

The two workflow regressions copy actual seed records/source bytes without symlinks
to the checkout, append a fixture-only observation preserving declared dependency
membership, establish `current`, then modify the copied tested supervisor source
and require `stale`. Fixture re-observation isolates omission behavior from the
test file's own ongoing changes. It does not rewrite canonical observations or
claim a real workflow execution/production metric. Ten separate manifest checks
exercise every seed analytical criterion's audited input declarations.

R1-1 changes only author declarations/data and documentation, not the existing
currency algorithm. New analytical observations use criterion-appropriate audited
groups (core, policy and/or docs), including imported helpers/locking, actual
workflow source touchpoints, package/config/theme/build/nav scripts, tested policy
sources and built record input pages. The tool checks **only declared dependencies**;
nonempty declarations do not prove completeness or detect new undeclared files.

## Observation/source correspondence and preservation

Initial Task 5 retained complete command evidence really showed 307 requirements
tests, permission pass, 1181 policy tests (683.41s), 56 docs tests and a successful
capacity-adjusted docs build/navigation. Those command outputs are retained as
historical observations. Their shared eighteen-path manifest was incomplete; this
fix explicitly retracts any inference that the old computed `current` established
comprehensive source applicability. The original safe summary and ten stored
verification records are unchanged. This new evidence supports the corrected
records and the new 320-test source, not a relabeling of old execution.

Retained original private capture scripts were inspected again: seeding invokes
actual CLI `init` once, applies actor/exact-expected-revision envelopes, and consumes
returned opaque IDs/revisions before dependent batches. Refresh uses CLI
`update-artifact`; initial observation capture used the registry-derived manifest
whose omissions are now accepted. No script directly wrote canonical JSON. The
fix script separately appends audit-stage `pending` observations, then corrected
`passed` observations only after these actual completed checks. It asserts the
original verification prefix, requirements and partial assessments equal FIX_BASE
after every canonical transaction. Pending audit results are not test passes.
Raw requests/private tool payloads remain private; safe summaries are tracked.

Mutable progress is a material docs source now. After the fix progress append and
registered snapshot refresh, docs build/navigation are rerun before final corrected
observations are captured; final requirements/data checks then cover the appended
records. Those final post-capture results and checkpoint SHAs are reported in the
author handoff, without editing this anchored observation summary afterwards.
Generated projections and this validation output are not independent source inputs:
they are produced by the procedure and evidence is separately content-anchored.
Subsequent progress/source edits must invalidate applicable corrected observations
until justified revalidation/new observations, not merely registry digest refresh.

No assessment is auto-promoted. All twelve retained assessments remain partial;
empirical goal/actual integration criteria remain unproven. Independent targeted
re-review, whole-branch review and safeguarded actual final remote CI/merge remain
controller-owned. No remote operations or live-session reload are claimed.
