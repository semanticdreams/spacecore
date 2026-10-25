# Minimal Interactive Canonical Candidates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove provably non-diagnostic canonical nonfunction analysis and resolve the existing required Wine pipeline timeout without a profiling framework.

**Architecture:** Reuse the existing private canonical classifier to select an ordered analysis subset while retaining the complete definition context. Characterize unmodified work first, then obtain diagnostic approval, implement the small guarded change and validate exact semantic/fallback behavior.

**Tech Stack:** Existing Space Fennel compiler/runtime, Source/Facts, layout/assert-call helper, native focused suites, guarded full Wine validation.

## Global Constraints

- Authority: docs/specs/2026-10-25-interactive-canonical-candidates-design.md.
- User stopped diagnostic expansion; archived WIP and previous diagnostic documents are follow-up only, not active instrumentation authority.
- Existing Wine full result4782PASS/1FAIL remains a merge blocker. No waived/skipped/inflated120s case or1800s application budget.
- No new module/observer/runner/profiler/public API/global or Facts cache/parserFFI/production or graph change.
- Unsafe graphs use IDENTICAL original all-defs and original dynamic access/error path; safe omission only nonfunction STRICTSTRING forms.
- FULL all-defs stays masking/assertion/ancestor context, original order/values/input identities remain unchanged.
- Existing create remains reference-only until named assertion lookup; canonical classifier and coverage semantics are unchanged.
- No baseline/depth/function/module allowance growth, formatting golf, test moves/removals/reductions or unrelated cleanup.
- Frozen old Facts artifacts untouched/UNEXECUTED; preserved deferred observer patch is not discarded or silently reapplied.
- Heavy validation SEQUENTIAL, never native/Wine overlap. Actual Wine/PE/application builds only windows-ci-reproducer with fresh owned Session and unchanged wrapper.
- Ordinary validated/self-reviewed checkpoints precede independent full-range review; preserve unrelated state, no task publication/history rewrite authority.

---

### Task 1: Characterize Actual Nonfunction Masking Work

**Files:** Modify only assets/lua/tests/test-constraints-layout-assert-calls.fnl. Read original layout/source/Facts/helper; production unchanged.

**Interfaces:** Source.discover(target)->records, Facts.extract(records)->fact-db, registered layout.interactive-context-assertion rule.run(ctx)->diagnostics|nil. Private outer-only-form is observed only by temporary restored upvalue wrapping.

- [ ] **1. Add one bounded test** generating canonical quote-free local definitions with N16 and N32 through real Source/Facts. Use existing fixture cleanup; named helpers avoid anonymous callback-depth growth.
- [ ] **2. Capture actual mask calls** by wrapping the existing rule upvalue, delegating ORIGINAL first and counting completed calls/full D afterward. Restore exact upvalue after success/error; stop if unsupported, add no production export.
- [ ] **3. Assert N definitions/no recovered parents/no accesses, N completed calls/full D=N, exact one nil result and unchanged Facts/raw references.** Derived256/1024 visits are structural work, not CPU/Wine cost.
- [ ] **4. Validate compile -> repo constraints -> complete assertion-call module sequentially** with canonical environment below; record baseline source/hash/case result before changing expectations.
- [ ] **5. Return characterization/proof for diagnostic advisor approval BEFORE production fix.** Self-review/checkpoint only if source gates pass; no framework or additional experiment if unsupported. Independent review covers this test-only checkpoint.

### Task 2: Select Safe Candidates, Preserve Complete Context

**Files:** layout.fnl, layout-assert-calls.fnl, existing test-constraints-layout-assert-calls.fnl, docs/dev/constraints.md only.

**Interfaces:** Add private helper export `select-definitions(ff, all-defs, calls)->definition[]`; unchanged classify(ff,definitions,calls)->groups|nil and create(opts)->lookup.

- [ ] **1. After advisor approval, write meaningful RED:** canonical N16/N32 now expect zero masking calls; mixed candidates expect functions analyzed with FULL original mask context; unsafe inputs preserve original array identity/dynamic access/errors. Record old N/old behavior, not parser failure.
- [ ] **2. Implement guarded ordered subset** using unchanged classify directly:

```fennel
;; Contract sketch: the implementation owns exact local style and tests.
(if (not (classify ff all-defs calls)) all-defs
    (do
      (local selected [])
      (each [_ def (ipairs all-defs)]
        (when (or (= (rawget def :kind) :fn)
                  (not= (type (rawget def :form)) :string))
          (table.insert selected def)))
      selected))
```

- [ ] **3. Change ONLY loop iterable** after unchanged access/calls/merge/reference-only create prefix. Keep full all-defs in every masking, assertion and closure/ancestor call. No wrapper nesting increase or body rewrite.
- [ ] **4. Preserve unsafe/error behavior:** nonfunction nil/false forms stay; malformed form/kind/namespace/dense arrays, protected/dynamic metatables, nonscalar records/calls and dynamic access paths retain original reads/errors. Test table-sentinel error identity and known dynamic traces using independent fixtures.
- [ ] **5. Compare complete ordered diagnostics** on existing named/local collisions, duplicates, recovered parents, identical/nonnested forms, quote concatenation, bare/dotted coverage and adapters. All input raw memberships/references unchanged; lazy create/lookup tests remain.
- [ ] **6. Update canonical docs** to distinguish separate candidate-eligibility pass from unchanged lazy named-assert lookup. Acknowledge additional linear classification/discarded temporary groups; no false zero-total-work or measured speedup claim.
- [ ] **7. Compile -> repo constraints -> focused assertion/interactive/precision/ancestor tests sequentially**, self-review/checkpoint all four files, independent full Task2 range review. No allowance edits to pass structural gates.

### Task 3: Final Working-Point Validation and Integration

**Files:** Measured canonical docs/follow-up notes only after executable source approval; no new feature/diagnostic work.

**Interfaces:** Consume independently reviewed repair; produce actual required native/Wine gate results and existing PR/merge-queue completion.

- [ ] **1. Use runtime freshness** make build BUILD_JOBS=1 timeout14400000 if needed, make cmake timeout600000 if needed.
- [ ] **2. Native standard full gate ALONE:** unset filters/timing/suite/case overrides; `CTEST_PARALLEL_LEVEL=1 SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH="$(pwd)/assets" /usr/bin/time -v make test BUILD_JOBS=1`, tool14400000. Observe resource state/retirement before Wine.
- [ ] **3. Fresh current-base check** via git-integrator; safe-merge/review/revalidate if required, no rebase/reset/discard/force.
- [ ] **4. Full Wine ALONE** via windows-ci-reproducer: `python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .`, tool14400000, fresh Session, all original gates/bounds. Publication PASS is preserved independently but full pipeline case must actually pass; no direct filters/ended Session reuse.
- [ ] **5. Diagnose any actual failure** using captured command/test/raw status/source/tree; no optimistic retry/timeout inflation. Only actual gate success establishes resolution, not derived work counts.
- [ ] **6. Document measured working point and deferred observer/profiler follow-ups**, qualify native Windows/unconfigured foreign UID and known noise. Independent review any source/docs delta.
- [ ] **7. Final whole-branch/currentorigin/clean-tree checks**, default push/PR through capabilities only when required local gates green; PR CI is full integration gate, poll queue through actual mergedAt. No readiness claim from local proof or queue handoff alone.

## Canonical Focused Validation Environment

Absolute assets, both FENNEL_PATH and FENNEL_MACRO_PATH equal `$PWD/assets/lua/?.fnl;$PWD/assets/lua/?/init.fnl`, disabled audio/skipped keyring, isolated XDG state/cache/config/log/TMPDIR in configured /tmp/space/tests scope. CTEST_PARALLEL_LEVEL=1/BUILD_JOBS=1; unset TEST_FILTER, SPACE_TEST_CASE_TIMEOUT_SECONDS, TEST_SUITE, SPACE_TEST_TIMINGS, TEST_VERBOSE.

Compile touched files FIRST through `./build/space -m tools.fennel-check:main -- --target files --file <each touched fnl>`; constraints SECOND via `make constraints BUILD_JOBS=1`; focused THIRD sequentially:

```sh
xvfb-run -a ./build/space -m tests.test-constraints-layout-assert-calls:main
xvfb-run -a ./build/space -m tests.test-constraints-rules-layout-interactive:main
xvfb-run -a ./build/space -m tests.test-constraints-rules-layout-interactive-precision:main
xvfb-run -a ./build/space -m tests.test-constraints-rules-layout-interactive-ancestors:main
```

Structural/parse failure blocks behavioral evidence; repair nearest malformed form and restart compile. No system Fennel/Lua/alternate compiler oracle. No broad native/Wine rerun solely for characterization. Plan self-review maps proof/characterization toTask1, guarded omission/parity toTask2 and unchanged acceptance/follow-up/integration toTask3; no unresolved product choice.
