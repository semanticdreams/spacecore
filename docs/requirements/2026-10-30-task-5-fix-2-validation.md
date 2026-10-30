# Task 5 fix round 2: historical fixture inputs

Assignment `REQ-IMPL-5`, same implementer/current delegated author (session ID not
exposed), supervisor/strict SDD, branch `juicyrebel/scoter`. FIX_BASE
`1aa86ea2a200f35982fac6a1285ce7358aba8cf6`; original BASE
`e4efadf63202b859e65496da243c5fcacce18820`. Delivery correction_used=0 unchanged.
This is the accepted new fix-induced fixture-copying defect, not a reset or a
confirmed repeat of R1-1. R1-2 was independently verified fixed; R1-1's remaining
immutable ledger-review coverage is being assessed separately by the controller.

## Diagnosis and bounded change

`copy_seed_fixture` collected paths from every retained observation and attempted
to copy all of them unconditionally. A missing historical dependency is valid data:
`schema.py:391-403` validates its safe locator, not its continued existence;
`evidence.py:96-101` reports missing bytes as unknown. A usable newer observation
does not erase the old locator. The fixture utility wrongly turned that supported
history into a mandatory filesystem prerequisite.

The utility now accepts an explicit source root for isolated reproductions, copies
available optional bytes, and preserves missing historical paths as missing. It
explicitly requires the canonical ledger, generated projection and supervisor source
used by these mutation tests. Missing required inputs fail loudly; no real checkout
source is deleted, no exception catch masks a failed copy of a present file, and no
stored observation/digest is rewritten. There is no production schema/currency or
architecture change and no synthetic new product requirement.

## Actual TDD and requirements evidence

Commands used transparent `rtk proxy`, with actual complete output observed:

| Command | Actual result |
| --- | --- |
| `python3 -m pytest scripts/tests/test_requirements_demos.py -k preserves_missing_historical_dependency -q --tb=short` before the fix | **1 failed / 20 deselected in 5.88s**, `FileNotFoundError` copying the retired fixture input |
| `python3 -m pytest scripts/tests/test_requirements_demos.py -k 'preserves_missing_historical_dependency or requires_mutation_input' -q --tb=short` before the fix | **2 failed / 20 deselected in 9.14s**, absent historical file and missing required supervisor both reached unconditional copy |
| Same two-case command after the fix | **2 passed / 20 deselected in 11.31s** |
| `python3 -m pytest scripts/tests/test_requirements_demos.py scripts/tests/test_requirements_evidence.py -q` | **102 passed in 70.81s** |
| `python3 -m pytest scripts/tests/test_requirements_*.py -q` | **322 passed in 100.31s** |

The main reproducer creates a copied seed, records an observation using a temporary
input and a later usable observation via real expected-revision CLI apply, deletes
only that isolated historical input, and copies the seed again. It asserts the old
locator/verification history remains, the missing file stays absent, required
supervisor bytes are present and latest verification is still passed/current. The
second regression ensures a missing required supervisor is explicitly rejected.

## Docs and final data checks

The following actual gates ran on the changed test source and appended progress
before this summary was anchored or new passing observations were captured:

| Command | Actual result |
| --- | --- |
| `make requirements-check` | **322 passed in 117.93s**, canonical revision 17 valid, read-only projection check current |
| From `docs/`: `npm run test:scripts` | **56 passed**, no failures, skips or cancellations |
| `npm run records:indices` | passed; historical inventories unchanged |
| `NODE_OPTIONS=--max-old-space-size=4096 npm run docs:build` | **passed in 161.55s**, including built navigation |
| `npm run records:check` after the build | **passed**, 186 plans / 165 specs |

Python 3.12.3/pytest 9.1.1 on Linux; Node 18.19.1/VitePress 1.6.4. Python output
was pristine. Known VitePress `fnl` highlighting fallbacks and large-chunk warning
remain, without suppression. No unexpected validation failure occurred in this
round. Space compile/build/runtime/constraints are not applicable; constraint impact
**not applicable**. Post-capture final requirements/projection and final docs checks
are recorded in the appended author report, without resealing this summary.

## Freshness, scope and retained evidence

Changing the test source makes prior observations stale. Newly appended observations
are scoped to actual focused/full requirements and docs revalidation; the earlier
complete policy run (1181 passed in 730.47s) remains historical evidence, not a new
policy execution. No permissions, agents/skills, policy wrappers, build scripts or
package/lock inputs change in this round, so a fresh twelve-minute policy suite is
not required for this fixture-only repair. The current requirements suite also
reruns static workflow declarations. No live-agent compliance, independent approval
or remote merge is inferred.

The previous thirty observations, requirements and twelve partial assessments are
preserved exactly as structured records. Existing safe evidence pages stay unchanged.
New records reuse the prior bounded declared input groups with actual current source
digests, adding the prior completed evidence page as an ordinary docs source. The
tool still checks only declared sources; this correction does not adjudicate R1-1's
independent review coverage or claim that a computed current result proves a complete
manifest. The new evidence output and generated projections are procedure outputs,
not independent source prerequisites; evidence bytes are separately anchored.

Progress is a material docs source. Its append is followed by real CLI
`update-artifact` with expected revision and render/check. New observations follow
actual checks, not blind resealing of old digests. Subsequent progress/source changes
must stale applicable observations until revalidated. Empirical criteria remain
unproven; all partial assessments and independent review/final integration gates remain.
