---
type: dev-note
tags:
  - note
---

# Test Harness Cleanup Notes

This note documents the recent cleanup of the Lua/Fennel test harness around shared fixtures,
temporary app-state replacement, and terrain-heavy integration tests.

The main goal was not adding new product behavior. It was making the tests:

- less duplicated
- less machine-specific
- less dependent on implicit global app state
- more trustworthy under full-suite execution instead of only isolated runs

## Problems We Hit

Several test failures and maintenance smells turned out to be harness problems rather than product
bugs.

### 1. Fixture Paths Were Reimplemented Incorrectly

Some tests were resolving fixture paths ad hoc, including direct user-home paths and incorrect use
of `app.engine.get-asset-path(...)`.

Problems:

- machine-specific paths made tests non-hermetic
- repeated path code invited drift
- a few helpers were simply wrong

This affected:

- [test-demo-browser.fnl](https://github.com/semanticdreams/spacecore/blob/main/assets/lua/tests/test-demo-browser.fnl)
- [test-heightfield-terrain.fnl](https://github.com/semanticdreams/spacecore/blob/main/assets/lua/tests/test-heightfield-terrain.fnl)
- [find-heightfield-support-mismatch.fnl](https://github.com/semanticdreams/spacecore/blob/main/assets/lua/tests/find-heightfield-support-mismatch.fnl)
- [test-heightfield-physics-support-grid.fnl](https://github.com/semanticdreams/spacecore/blob/main/assets/lua/tests/e2e/test-heightfield-physics-support-grid.fnl)

### 2. Tests Mutated `app.states` Without Suspending The Current State

Many tests replaced `app.states` directly with a fresh `States` instance.

That was often good enough in isolated runs, but it was not clean:

- the previously active state could remain connected to engine signals
- full-suite ordering could expose leaks that narrowed runs did not
- restoring `app.states` alone did not restore the previous state lifecycle correctly

This was especially visible in terrain pick / terrain paint tests spread across:

- [test-demo-browser.fnl](https://github.com/semanticdreams/spacecore/blob/main/assets/lua/tests/test-demo-browser.fnl)
- [test-states.fnl](https://github.com/semanticdreams/spacecore/blob/main/assets/lua/tests/test-states.fnl)
- [test-graph-view.fnl](https://github.com/semanticdreams/spacecore/blob/main/assets/lua/tests/test-graph-view.fnl)
- [test-world-nodes.fnl](https://github.com/semanticdreams/spacecore/blob/main/assets/lua/tests/test-world-nodes.fnl)

### 3. One Test Was Over-Specifying Global Input Plumbing

One terrain-rect-pick test asserted that clickables counters stayed at zero.

That was brittle because it tested too much of the surrounding global routing instead of the actual
behavior the test owned:

- engine events reach the active terrain-rect-pick session
- the session completes
- state is restored

The counter assertion was removed because it made refactors harder without increasing confidence in
the picker logic itself.

### 4. Full-Suite Execution Exposed Stale State Teardown

After extracting shared suspend/resume helpers, the full suite exposed a real harness issue:

- some previously active states were already effectively detached
- calling `on-leave` again caused `Signal handler not connected`

That did not show up in the smaller targeted runs, which is exactly why the full-suite rerun
mattered.

## Final Improvements

### Shared Test Helper Module

The shared helper now lives in:

- [test-support.fnl](https://github.com/semanticdreams/spacecore/blob/main/assets/lua/tests/test-support.fnl)

It currently owns:

- `fixture-path`
- `suspend-active-state`
- `resume-active-state`

This gives the touched tests one place for:

- repo-local fixture resolution
- temporary active-state suspension before swapping `app.states`
- resuming the previous state after restoration

### Repo-Local Fixtures

The terrain-heavy tests now use committed fixtures under `assets/lua/tests/data/` instead of user
home paths.

This makes the tests:

- portable
- reproducible
- safe to run outside the original development machine

### Safer App-State Swaps

The touched suites now suspend the currently active state before replacing `app.states`, then
restore `app.states`, then resume the suspended state.

This is better than the old pattern because it makes state lifecycle explicit instead of relying on
the old state silently staying valid in the background.

### Better Aggregate Verification

The cleanup was not accepted based only on targeted suites. It was verified against:

- `tests.test-states:main`
- `tests.test-graph-view:main`
- `tests.test-world-nodes:main`
- `tests.fast:main`
- `make test`

The important lesson here is that harness cleanup must be verified in the full aggregate shape,
because state leaks are often invisible in isolated test runs.

## Trade-Offs

The current result is good, but not perfect.

### 1. `test-support` Still Knows About A Specific Error String

`suspend-active-state` currently treats `"Signal handler not connected"` as a stale-state case and
returns `nil` instead of failing.

That is acceptable for test glue because:

- the failure was real under aggregate runs
- the helper is intentionally defensive around global mutable app state

But it is still a compromise. String matching is not a clean systems boundary.

### 2. The Deeper Problem Is Still Global App State

The helper improves the situation, but it does not remove the architectural reason these tests are
fragile:

- many tests still mutate global `app` fields
- the harness still depends on lifecycle discipline rather than hard isolation

So the helper is a practical containment layer, not a fundamental redesign.

## Per-Test Timeout Budgets

A runner test descriptor may declare `:timeout-seconds` alongside `:name` and
`:fn`. When present it must be a positive finite number; false, strings, zero,
negative values, NaN and infinities are errors, not requests to inherit or disable
the deadline. A nonempty explicit `SPACE_TEST_CASE_TIMEOUT_SECONDS` takes precedence
over valid descriptor metadata, including 0 to disable deadlines. With an absent
or empty environment value, valid descriptor metadata applies; an absent descriptor
defaults to 120 seconds. Invalid metadata still fails even with an explicit
environment override. Test filtering is unchanged.

The three app-root reload integration descriptors use main's 300-second budget
and explicit per-case root-fixture teardown. An explicit environment value still
wins. Expiry remains one-shot, restores the exact prior debug hook before teardown,
permits protected cleanup/rollback, and still fails a case that catches the timeout
exception. Suite finalization captures the owned Engine before executing tests;
replacing or clearing `app.engine` does not redirect its single shutdown attempt.

## What To Watch Out For

### Readable bounded failures

`tests.error-format.format-error(err)` is the shared base diagnostic formatter.
It reads only raw `code`, `message`, `outcome`, and `current-revision` fields, in
that priority order. Encoded field caps are respectively128,1536,96,192 bytes;
the complete base description is at most2048 bytes. Plain strings use the same
2048-byte encoded limit. Truncation is visible as `[truncated]`; controls,
non-ASCII bytes, quotes and backslashes are escaped into printable ASCII. Work
is bounded by the output budget, not by the size of an oversized input string.

Nested values and unsupported objects have type-only descriptions. The formatter
never walks `result`, invokes table getters/iteration/metamethods or stringifies
arbitrary objects. This is a **metadata allowlist, not a PII redactor**:
producer-supplied `message` text can still appear, bounded and escaped. Producers
remain responsible for excluding credentials/private payloads from that field.
Formatter failure falls back to the original error's type, not a new exception.

The runner normalizes raw body/load/teardown errors **before** adding a traceback,
and uses the same base description when traceback support is absent. Generated
stacks are not escaped again when logged or combined with shutdown diagnostics.
Shutdown failures are logged safely while original single-failure propagation,
counts, timeout latches/hooks and the captured Engine finalizer remain intact.
Runner regression cases that own an Engine continue to run in child processes;
negative logs are captured rather than leaked into the successful parent suite.

Windows private-publication refusals now identify the literal `anchor`, `attempt`
or `record` role, owner-match/protection/DACL-match booleans, expected/actual DACL
byte lengths and safe ACE counts. SID/ACL/descriptor bytes and payloads are never
printed. This instrumentation does not change the owner/protection/raw-DACL
equality predicate or subsequent owner-ACE checks. Linux checks do not execute
that Windows branch; use the next actual guarded Windows/Wine evidence to decide
what mismatched, rather than guessing a policy change from an opaque error.

When writing or refactoring tests in this codebase:

- do not hardcode user-home fixture paths
- prefer [test-support.fnl](https://github.com/semanticdreams/spacecore/blob/main/assets/lua/tests/test-support.fnl) for fixture lookup
- if a test replaces `app.states`, suspend the current active state first and resume it after restore
- verify state-heavy cleanup with `tests.fast` or `make test`, not only a narrow module run
- avoid asserting incidental global plumbing when the test can assert the owned behavior directly

### Exception-Safe Second-Precision Clock Tests

Session persistence uses zero-argument `os.time()` integer seconds. Its timestamp
regression must not depend on a shell `sleep` command or polling: a missing command
under Wine used to leave the ignored delay unsuccessful and the newer-time
assertion racing the same second.

The agent-layer test now scopes a test-only clock at1700000000, verifies a
same-second save remains equal, then advances to1700000001 before update/save.
It asserts exact creation/update/status values in memory and persisted JSON,
without directly assigning session timestamps. The protected clock scope restores
the original `os.time` before directory cleanup or rethrow; a throwing-body case
also verifies restoration and original error identity. Production session APIs,
second-precision semantics and test deadlines remain unchanged.

## Future Improvements

The next worthwhile improvements are structural, not urgent.

### 1. Make State Teardown Idempotent At The Source

The best long-term fix is not better string matching in test glue.
It is making state/signal teardown safe to call repeatedly.

If `on-leave` and signal disconnect paths become idempotent, `test-support` can be simplified
substantially.

### 2. Broaden Shared App-Fixture Helpers

`test-support` currently focuses on:

- fixture paths
- active-state suspension/resume

It could grow carefully into a shared helper for other common global test setup patterns, for
example:

- temporary HUD replacement
- temporary clickables / hoverables setup
- temporary world-manager setup

That should be done incrementally, not by building a giant generic harness abstraction up front.

### 3. Reduce Direct Global Mutation In Tests

Longer term, the cleanest direction is to reduce how many tests need to patch global `app` fields at
all.

That would likely require more explicit app-fixture construction helpers or narrower module
boundaries.

## Summary

The practical improvements were:

- centralize fixture lookup
- centralize active-state suspend/resume
- remove brittle over-specified assertions
- verify under the full suite

The remaining known compromise is:

- `test-support` still contains a stale-state string match because state teardown is not yet
  idempotent at the source

That is acceptable for now, but it is the first place to revisit if this harness area gets touched
again.


## List Operand Observations and Canonical Fixture Roots

With the existing `SPACE_TEST_TIMINGS=1`, the List presentation fixture emits
`[LIST-OPERANDS]` observations at its existing `JsonUtils.write-json!` seam for
move, remove, selection, name-only edit, and resolver-error recovery scenarios.
Each line contains only the generated fixture root, the intercepted write path,
their `fs.absolute` equivalents, the exact intended canonical
`entities/list/list.json` destination, the existing raw-prefix predicate result,
and canonical destination equality. No record values, app-data paths, or session
data are inspected or printed. The sink immediately flushes each line.

Qualification uses equality with that fixture-owned canonical destination, not
the raw-prefix predicate. Other leaf names and unrelated writes are excluded from
diagnostic output; diagnostic observations never supply write-counter values.

The guarded Task 7 Wine run established the original fixture defect: all nine
observations across the five affected scenarios had `raw-prefix=false` and
`intended-equal=true`. The fixture retained a raw mixed-separator temporary root
while the real store/writer used its canonical Windows absolute spelling. Only
the write counter was zero; expected signal counts and existing disk assertions
were consistent with the real writes. Native passes alone had not proven this.

The fixture now returns `fs.absolute` from `make-temp-dir` before directory
creation, store construction, observation, snapshots, or cleanup. All share that
one canonical root. Counting canonicalizes each intercepted write path using the
same lexical `fs.absolute` contract and requires the root plus its native path
separator, so a sibling sharing only the textual root prefix is not counted.
This adds no symlink, case-folding, or trailing-separator policy and changes no
production List persistence or filesystem API.

Real-writer regressions exercise absolute, relative, and dot-component spellings
of the same canonical List leaf, check exact JSON disk bytes, and reject a real
sibling-prefix write. The five existing counter arrays and all passive/error,
signal, view, and cleanup oracles remain intact. Recovery additionally compares
the final held record with a fresh disk readback after its successful name edit.

Output is capped at two observations per scenario and twelve lines per module,
with at most 1024 encoded bytes per line. Each path is byte-escaped to printable
ASCII and independently bounded to 128 encoded bytes plus quotes; truncation is
marked `[truncated]`. Disabled observations resolve no extra paths and emit no
output. In-module controls exercise escaping, caps, unrelated writes, and a
canonical destination whose raw prefix differs. Native timings on/off runs
check outcomes, caps, and parity. When this repair was documented, the actual
Wine cause was established by the earlier guarded operands, but repair success
still required the next guarded combined run. The bounded observations retained
their original raw operands and predicates for that verification, rather than
assuming success. That pending status is historical: the
[2026-10-26 measured result](windows-wine-build-and-test.md#current-publication-contract-measured-wine-acceptance-below)
at `fa4fc4b2` subsequently recorded full Wine acceptance **4867/4867 PASS**, capture
`20261026T192428846633Z-2fbf968e2a3543808e0f8f3889cdb0d0`.

## See also

- [Development Tooling](/dev/features/development-tooling)
