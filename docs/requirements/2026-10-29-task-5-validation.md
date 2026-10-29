# Task 5 local validation evidence

Assignment: `REQ-IMPL-5`, implementer/current delegated author (session ID not
exposed), supervisor/strict SDD, branch `juicyrebel/scoter`, source BASE
`e4efadf63202b859e65496da243c5fcacce18820`. Date: 2026-10-29.
This is a privacy-safe author execution summary, not independent approval.

## Observed local checks

- `python3 -m pytest scripts/tests/test_requirements_scenarios.py scripts/tests/test_requirements_demos.py -q`:
  **22 passed in 20.97s** (fifteen scenarios, four demos, three docs/seed/ignore checks).
- `python3 -m pytest scripts/tests/test_requirements_*.py -q`:
  **307 passed in 57.30s**, no warnings.
- `make requirements-check`: **307 passed**, canonical revision 5 validated and
  read-only projection check passed. The complete final policy gate below repeats it.
- `make opencode-check`, with a 1800000ms command allowance: **307 requirements
  tests passed in 59.37s**, permission checker **pass**, **1181 policy/capability/
  lifecycle/workspace tests passed in 683.41s**, no warnings. This final run used
  unfiltered `rtk proxy` output; earlier filtered repetitions are not needed to
  establish the result.
- From `docs/`: `npm run test:scripts` **56 passed**; `npm run records:indices`
  passed. Record inventories stayed unchanged because existing records were already
  inventoried; no speculative generator change was needed.
- `NODE_OPTIONS=--max-old-space-size=4096 npm run docs:build` passed in 139.17s,
  including built navigation; then `npm run records:check` passed with **186 plan
  and 165 spec pages**. These are historical inventory counts, not semantic coverage.

Python 3.12.3 / pytest 9.1.1 on Linux; docs Node 18.19.1 / VitePress 1.6.4.
Commands were actually run, sometimes through the transparent `rtk proxy` or
output-filtering `rtk` launcher. No Space compile/build/runtime/constraint gate is
applicable to this Python/docs-only Task 5 surface. Constraint impact: **not applicable**.

## TDD and limitations

The first focused fixture run was **19 passed / 1 failed**: the new documentation
contract failed because the API page was absent. Existing CLI behavior already
worked; those nineteen working scenarios/demos are not fabricated RED evidence.
After documentation was added, new seed/ignore contract tests gave **20 passed /
2 failed** for the missing canonical seed and the unignored `.index.md.*.tmp`
projection sibling. CLI seed capture and the narrow ignore fix made them GREEN.
Self-review strengthened demo C with an actual failing fixture Python assertion
before correction and a passing assertion afterwards, and demos A/D execute their
fixture code too. This remains synthetic demonstration behavior, not Space product
or production outcome measurement.

Every fixture initializes/mutates through the real CLI with expected-revision
envelopes; queries use actual CLI/library report logic. Semantic reconciliation
findings remain agent-owned. Static declarations and supplied-source observations
do not establish universal live-agent compliance. No empirical goal is credited,
and no remote base check, CI, push, PR, merge or `mergedAt` observation was performed
by this implementer. Independent Task 5/whole-branch review and controller-owned
safeguarded actual integration remain pending.

## Diagnosed environmental failures (not hidden passes)

The initial `npm run docs:build` stopped with `vitepress: not found`. Inspection
showed `docs/node_modules` absent and `npm ls --depth=0` reported the declared
VitePress dependency unmet. `npm ci` installed the existing lockfile without
source/dependency changes. The next build reached VitePress but failed at Node's
heap limit, with GC near 2022 MiB and `Reached heap limit`. A read-only Node probe
reported a 2096 MiB heap ceiling and the host had about 5936 MiB available. The
single capacity correction to 4096 MiB passed. These were distinct setup/capacity
failures, not repeated source failures. Systematic-debugging was loaded; no
repository code/config fix, bypass, weakened check or mandatory architecture
decision resulted. Final focused docs gates are rerun after the seed/evidence
snapshot refresh and reported in the handoff.

Known non-fatal output: VitePress's existing `fnl` highlighting fallbacks and
large-chunk warning. `npm ci` reported **9 existing audit vulnerabilities (2 moderate,
7 high)**. No audit fix or dependency change was made outside this assignment.

## Evidence currency

This summary is anchored by content digest when verification is recorded. Declared
dependencies name the inspected production/test/docs files, not the mutable progress
ledger or generated index. Changed dependencies must become stale; an unrelated
commit alone does not invalidate them. The progress artifact is a separate mutable
snapshot: refresh its registered digest through `update-artifact` after appending
review/integration history. Never edit old observations to make them current.
