# Current Layout Boundary Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Obtain one current-source observation separating interactive-rule masking from residual elapsed work without optimizing or weakening the required Wine120s gate.

**Architecture:** Forward the existing optional observer into internal rule context, preserve guarded rule error ownership, and instrument only boundaries around unchanged operations. The existing test progress consumer owns clocks/state/output; its existing private `:rule` detail mode is selected only by the full-pipeline test owner.

**Tech Stack:** Space Fennel compiler/runtime, constraints runner, injected sysinfo monotonic clock, existing test runner/hook regressions, native CLI and capability-owned Wine.

## Global Constraints

- Authority: `docs/specs/2026-10-25-current-layout-boundary-diagnostic-design.md`, commitd62cb9c.
- Diagnostic only: no optimization, Facts memoization, parser/FFI changes, deadline increase, skips, baseline allowance growth or automatic scope expansion.
- Frozen `.superpowers/sdd/facts-span-diagnostic/**` stays untouched/UNEXECUTED; no open, reuse, execution, reseal or authority refresh.
- No new public runner signature, selector, observer option, environment flag, hook, profiler process, Source/Facts instrumentation or parent runtime-policy change.
- Without observer: no observation factories, events, clocks, diagnostic state/counters, output or retained history; one-time path selection is allowed.
- Preserve definition order/count, form/merge reads, dynamic semantics, input identity/raw contents, complete ordered diagnostics and exact one-value/nil returns when observation succeeds.
- Preserve original rule guard,120s case limit, timeout catches/latch, previous hook restoration and teardown. Callback failure is explicitly relayed, not silently converted into an accepted framework diagnostic.
- No pair/match counters or extra traversal. Only fixed aggregate scalars and one current-file/definition slot, not retained event/file/definition histories.
- Entire rule-detail mode: at most2N+1records,512bytes/serializedline,2MiB total includingCRLF reservation; N from actual Facts END. Numeric/enums/indices only, no path/form/source/name/env dump or arbitrary stringification.
- Every heavyweight validation/observation runs SEQUENTIALLY. Native/Wine must never overlap; check memory/processes before each.
- No original test moves, skips, removals or reductions. Dedicated test module plus one fast registration; two existing owner-output expectations migrate while preserving opt-in/disabled/flush/restoration checks.
- Layout's actual module metric must remain<=1200 and all applicable function/depth limits must pass. No formatting golf, baseline/limit change or unrelated refactor; stop for bounded decomposition if clean fit is impossible.
- Commit spec/plan and obtain independent SCHEMA / CONTROL / INACTIVE review BEFORE implementation; implementation checkpoint review BEFORE observation.
- Runtime artifacts only under new ignored `.superpowers/sdd/current-layout-boundary-diagnostic/`, never force-add them. Ordinary validated/self-reviewed implementer checkpoints precede independent full-range review; no publication/history rewrite authority.

## Exact Manifest and Interfaces

Implementation changes exactly8files:

1. assets/lua/constraints/runner.fnl — internal observer forwarding/error relay.
2. assets/lua/constraints/rules/layout.fnl — guarded boundaries only.
3. assets/lua/tests/constraint-progress.fnl — existing private rule mode.
4. assets/lua/tests/test-constraints-runner.fnl — relay/identity/hook tests.
5. NEW assets/lua/tests/test-constraints-layout-progress.fnl — substantial new parity/consumer/cap/deadline tests.
6. assets/lua/tests/test-constraints-default-run.fnl — private literal and two existing owner-test expectations only.
7. assets/lua/tests/fast.fnl — one registration line, no case reduction.
8. docs/dev/constraints.md — canonical schema/limits/error/privacy documentation.

Public signatures stay unchanged. Private interfaces:

```text
make-rule-observer(observer) -> (notify, raise-observer-error)
ctx = {:facts exact-original-fact-db, :observer notify?}
make-interactive-observation(observer)
  -> notify(edge, subphase, file-index, definition-index?, definitions?) -> nil
ConstraintProgress.create({now-ms, write, detail-phase}) -> observer
```

New events contain ONLY phase=rule, fixed rule-id=layout.interactive-context-assertion,
edge=begin|end, subphase=interactive-file|interactive-mask|interactive-analysis,
existing positive file index, positive definition-index for mask/analysis, and
definitions=#all-defs at mask BEGIN/file END. Fresh event tables allocate only
through the observed-path factory. Layout owns no timing, diagnostic counters,
formatting or history; original outer-only-form/analysis are unchanged.

Rule detail prints ONLY these records after `[CONSTRAINT-PROGRESS]`:

```text
phase=rule subphase=interactive edge=begin file_index at_ms stage=setup
phase=rule subphase=interactive edge=end file_index definitions masks analyses elapsed_ms mask_ms remaining_ms
aggregate phase=rule subphase=interactive outcome files_begun files_ended definitions masks analyses elapsed_ms mask_ms remaining_ms pending_file pending_def pending_stage pending_definitions definitions_known pending_ms
```

Outcome complete|unfinished|cap is boundary completeness, never rule/pipeline PASS.
Pending stage none|setup|mask|analysis|between; zero pending indices mean none,
definitions_known=0 means unknown pending D. Counts increment only on observed END;
known D adds once/file. Summary mask_ms includes completed intervals and pending
mask interval ONLY when pending_stage=mask explicitly marks censoring. Residual
remaining_ms=elapsed_ms-mask_ms includes setup/instrumentation/possible unwind,
not pure analysis CPU. No natural runtime or Wine/native speed ratio claim.

---

### Task 1: Forward Observer and Preserve Error Ownership

**Files:** constraints/runner.fnl and tests/test-constraints-runner.fnl only.

**Interfaces:** Private relay/ctx above; run-rule and all public results unchanged.

- [ ] **1. Add forwarding RED tests** with existing module substitution/restoration: exact Facts/target references, omitted/empty/nil observer complete result parity, active callback identity, unchanged input membership.
- [ ] **2. Add private-factory non-entry tests** using restored upvalue substitution and an active control proving the throwing spy is connected. No production test export.
- [ ] **3. Implement observed-only relay:** pcall callback ONLY, latch first error with separate presence boolean, preserve table/false/nil, rethrow into unchanged rule guard. After run-rule hook restoration, rethrow exact latched callback error outside guard BEFORE consuming result or emitting rule END.
- [ ] **4. Error/hook RED/GREEN:** test table/false/nil callback failure with/without synthetic per-rule timeout; previous hook restored before outside propagation. Ordinary workload failures keep old treatment.
- [ ] **5. Distinguish timeout locations:** work timeout may be caught and yield rule END; notification timeout may relay before END (no summary). Nested run-case must latch original timeout FAIL/restorehook/runteardown even if a later sink throws. Do not fabricate completion or claim identical callback-failure flow.
- [ ] **6. Compile touched files, repository constraints, focused runner tests SEQUENTIALLY** using Task3 environment/commands; RED must be behavioral, not parser/setup failure. Self-review/checkpoint and independent full Task1 range review.

### Task 2: Boundary Events, Bounded Consumer, Owner and Regressions

**Files:** layout.fnl, constraint-progress.fnl, NEW test-constraints-layout-progress.fnl, default-run owner, fast registration, docs/dev/constraints.md.

**Interfaces:** Consume Task1 ctx.observer; emit exact event/output schemas above; new module exports canonical tests/main and registers once.

- [ ] **1. Add complete semantic parity fixtures** using public rule entry and independent active/inactive instances: uncovered definitions, locals, duplicates, identical/non-nested masking, recovered parents; complete ordered diagnostics/exact one value includingnil; input references/raw membership unchanged; throwing dynamic form accessor identity.
- [ ] **2. Preserve/read-test sequences** explicitly: calls,definitions,recovered-parents,recovered-parents; assertion reads first,first,second,second; original dynamic definition-form reads through masking. No optimization/filter/reordering.
- [ ] **3. Implement observed-only factory/raw context read:** rawget only on table ctx avoids new __index effects; factory and new event literals exist only in observer-present branch. Use existing loop indices; observed-only #all-defs on merged plain vector.
- [ ] **4. Insert guarded boundaries** file BEGIN before original file work; maskBEGIN/originalouter-only-form/maskEND; analysisBEGIN/originalremainingbody/analysisEND including skipped definitions; fileEND only normal return. No per-pair counter, changed eligibility/selector, extra traversal or finallyEND.
- [ ] **5. Implement existing detail-phase=:rule path** inside create, not newmodule/API: actual N from FactsEND, namedinteractive events only, otherpipelineevents silent, fixed aggregate state/current slot, immediate per-boundary aggregation/nohistory. Other existing modes unchanged.
- [ ] **6. Implement honest pending/summary:** BEGIN persists before work, completedEND counters only, knownD once, setup/mask/analysis/between pending states, complete versus unfinished at actual top-level rule END. Relay/process/sink failure without END may leave no summary; preserve missing completion.
- [ ] **7. Enforce limits before writes:** reserve one terminal record+CRLF; wholemode2N+1/512line/2MiB; explicit single outcome=cap then no more clocks/formatting/writes. Reject NaN/infinity/negative indices/counts/overflow explicitly; no silent truncation.
- [ ] **8. Deterministic consumer RED/GREEN** exact times/counts with empty/multiple files; pending allstages; completed versus censored masktime; residual includes setup/unwind; D unknown flag; caughtworkload failure no falseEND; summaryonlyonce.
- [ ] **9. Privacy/cap/inactive tests:** hostile extras never traversed/stringified; private sentinels absent; maxfinite formatting/line lengths/LF+CRLF budgets; throwingclock/writer/factory nil-owner spies with active controls; structural allocation review, no production exports. A clockspy alone is not allocation proof.
- [ ] **10. Observer/deadline regressions** file/mask/summary callback errors; nested run-case success/sinkfailure/caughttimeout restores original hook before teardown, originaltimeoutlatchwins secondary error. Relayescape no fabricated summary.
- [ ] **11. Activate existing full-repo owner** private detail literal nil->rule, exact SPACE_TEST_TIMINGS="1" gate, originalclock/flushingnewline sink/roots/suites/baseline=false/resultassertions/case120 unchanged. Migrate only two existing ownertests to validinteractiveevents preserving disabled/opt-in/flush/restoration; add one fastregistration.
- [ ] **12. Document exact canonical internal schemas, inactive/error/censoring/overhead/privacy contracts.** Check actual structural metrics and source-anchored baseline compatibility; no allowance changes.
- [ ] **13. Compile -> repository constraints -> focused suites sequentially**, self-review/checkpoint, independent SCHEMA / CONTROL / INACTIVE source review before observation.

### Task 3: Source-Bound Sequential Gates and One Native Observation

**Files:** Generated evidence only in new ignored current-layout-boundary-diagnostic directory: manifest.json, validation.md, native.stdout.log, native.stderr.log, native.resources.txt, native.capture.json, analysis.md. No source edits in this task.

**Interfaces:** Consume approved spec/plan and reviewed implementation, output one bounded observation/diagnosis, not optimization authority.

- [ ] **1. Bind provenance before execution:** evidence3af37439 separate from actualHEAD; spec/plan commits/hashes/reviews, implementation base/head/reviews, seven Fennel hashes/sizes, unchanged Source/Facts/asserthelper/testrunner hashes, canonicaldocs/runtimebinaryhash, exact commands/env/allowances. Reject source drift rather than silently refreshauthority. Record unrun stages as unrun.
- [ ] **2. Ensure runtime freshness:** make build BUILD_JOBS=1 timeout14400000 if runtime missing/stale; make cmake timeout600000 if needed. No C++ change planned but no stalebinary assumption.
- [ ] **3. Direct environment:** absoluteassets, both canonicalFennelpaths, disabledaudio/skippedkeyring, isolatedXDG/state/cache/config/log/TMPDIR under configured /tmp/space/tests scope; CTEST_PARALLEL_LEVEL=1/BUILD_JOBS=1. Unset TEST_FILTER, SPACE_TEST_CASE_TIMEOUT_SECONDS, TEST_SUITE, SPACE_TEST_TIMINGS, TEST_VERBOSE until the exact observation command. No heavy concurrent process.

```sh
export SPACE_DISABLE_AUDIO=1 SKIP_KEYRING_TESTS=1
export SPACE_ASSETS_PATH="$PWD/assets"
export FENNEL_PATH="$PWD/assets/lua/?.fnl;$PWD/assets/lua/?/init.fnl"
export FENNEL_MACRO_PATH="$FENNEL_PATH"
export XDG_DATA_HOME=/tmp/space/tests/xdg-data
export CTEST_PARALLEL_LEVEL=1 BUILD_JOBS=1
unset TEST_FILTER SPACE_TEST_CASE_TIMEOUT_SECONDS TEST_SUITE SPACE_TEST_TIMINGS TEST_VERBOSE
```

- [ ] **4. Compile FIRST** project-native touched7files:

```sh
./build/space -m tools.fennel-check:main -- --target files \
 --file assets/lua/constraints/runner.fnl --file assets/lua/constraints/rules/layout.fnl \
 --file assets/lua/tests/constraint-progress.fnl --file assets/lua/tests/test-constraints-runner.fnl \
 --file assets/lua/tests/test-constraints-layout-progress.fnl \
 --file assets/lua/tests/test-constraints-default-run.fnl --file assets/lua/tests/fast.fnl
```

Parse failure: inspect nearest malformed enclosing form, repair/simplify only that form, compile again before constraints. No unsupported Fennel oracle.

- [ ] **5. Repository constraints SECOND:** `make constraints BUILD_JOBS=1`, timingsunset/normalunobservedsourcegate. Explicit-file targets have differentbaseline scope and are not a substitute here. Any nonpass blocks further execution; no baseline/skip repair shortcut.
- [ ] **6. Focused tests THIRD**, sequential:

```sh
xvfb-run -a ./build/space -m tests.test-constraints-runner:main
xvfb-run -a ./build/space -m tests.test-constraints-layout-progress:main
TEST_FILTER='constraint progress' xvfb-run -a ./build/space -m tests.test-constraints-default-run:main
xvfb-run -a ./build/space -m tests.test-constraints-layout-assert-calls:main
xvfb-run -a ./build/space -m tests.test-constraints-rules-layout-interactive:main
xvfb-run -a ./build/space -m tests.test-constraints-rules-layout-interactive-precision:main
xvfb-run -a ./build/space -m tests.test-constraints-rules-layout-interactive-ancestors:main
```

- [ ] **7. Verify independent source review and prerequisites** before spending the single repository observation; record exact identity. A prerequisite failure stops the ladder; it is not the approved observation.
- [ ] **8. One native observation ALONE**, ART is the new ignored directory:

```sh
/usr/bin/time -v -o "$ART/native.resources.txt" \
 timeout --kill-after=5s 600s \
 env TEST_FILTER='runner run-target with repo target runs full pipeline' \
     SPACE_TEST_TIMINGS=1 TEST_VERBOSE=1 \
 xvfb-run -a ./build/space -m tests.test-constraints-default-run:main \
 >"$ART/native.stdout.log" 2>"$ART/native.stderr.log"
```

Invoking tool660000ms, case still120s. Save raw exit immediately, UTC/monotonic endpoints, streamhashes/sizes/EOF/truncation/timeoutsignals/subprocessretirement. Verify actual diagnostic2N+1/512/2MiB limits. Never infer natural completion from outertimeout or missingEND.

- [ ] **9. Interpret measured completed/pending states only:** masking versus residual, knownD, censoredintervals and overhead. No exactpair/byte/assertindexeligibility measurement; any completedmasks*D derived value is only loop-visit lower bound excluding unfinished calls. If residual dominates, reject maskingdominance for this observation. No automatic diagnostic expansion/optimization.
- [ ] **10. Return evidence for diagnostic judgment.** If nativecost cannotresolveWine distribution, request separately reviewed fresh full windows-ci-reproducer run14400000, unchangedcomponents/app/casebounds, no directWinefilters/endedownerreuse. Fullnativegate once before publication justifiedsharedrunnerchanges, executedALONE with standard make test; do not repeatwholegate aftereverytinycheckpoint unnecessarily.
- [ ] **11. Keep original finishing obligations:** actual unchangedfullWinePASS inclpublicationproof/cleanup, currentorigin/main, finalreview, PRCI and actualmergequeuecompletion. Diagnosticmeasurement/nativePASS do not satisfy them. No pushwhileactualrequiredfailureunresolved.

## Plan Self-Review

Spec mappings: forwarding/observer-failure ownership(Task1); unchanged operations/
inactive path/dynamicparity/exactnumericcaps/privateowner(Task2); provenance/
sequentialsourcegates/singlecurrentobservation/censoringinterpretation(Task3).
No unresolved product/API choice. All8implementation paths are explicit. No frozen
authority, parser/Facts optimization, newhook/selector/framework or budget/skip
change is included. Implementation/measurement still require their independent
reviews; neither committed documents nor useful measurements prove feature success.
