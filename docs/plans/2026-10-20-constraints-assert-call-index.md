# Constraints Assert-Call Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace repeated named assertion-call filtering with one lazy invocation-local index without changing rule results or supported dynamic-fact behavior.

**Architecture:** Keep the coverage algorithm and cleaners in `layout.fnl`. A focused private selector supplies ordered original call references for canonical immutable facts; unsupported shapes retain the actual existing scanner. Classification occurs only at the first named-coverage demand, never for anonymous/nil-name-only workloads.

**Tech Stack:** Existing Fennel/Lua, project-native compiler, Source/Facts pipeline and test runner; no dependency or native binding change.

## Global Constraints

- Starting source checkpoint5b5c5e74dea545266673c16c245ecddaf80a71b0; verify current HEAD/index/status. Preserve all historical sealed probes and logs; new evidence uses `.superpowers/sdd/wine-posix-publication/assert-index-*` only.
- Single optimization: assertion-call selection. Do not change masking, cleaning, relevance/scope/keyword policy, diagnostics, fact extraction, baseline/rule limits, target selection, skips, timeout/hook/teardown, public tooling or production telemetry.
- Keep the existing120s case/1800s application bounds. Native results do not prove Wine compliance; unchanged guarded reproduction remains required.
- Preserve original call references/order, matched presence even when formnil/false, name collisions, anonymous/nil branches, conservative keyword coverage, fallback text scanning and untouched calls supplied to build-bare-covered.
- Phase1 unfinished unstaged WIP and complete evidence →independent review/fixes →separately authorized Phase2 exact commit. No publishing, force/rebase, artificial evidence commit or implementation-time capability bypass.
- No production fault/counter hooks. Test-only compiled-source traversal counters require review of the exact ignored driver before execution. Production never reads those counters or emits output.

## Evidence and Limits

Advisor `ses_ea68fc920ffeUdAJEbTCn7hN5e` supports this direction and requires this settled plan. Actual Wine fullrepo120s timed out inside guarded rule10; its43.5s interval is censored. Facts cost~59s remains a separate unresolved contribution. Read-only native corpus1361 and private helper attribution prove repeated full-file filtering in a materially expensive boundary, not that filtering dominates unwrapped Wine time. Coverage-helper invocations91756 are not measured named scans. Instrumented masking/assertion proxies75.44%, bracket drift/perturbation10–18%; exact ranking remains inconclusive. This plan promises a deterministic work reduction and semantic equivalence, not a Wine speedup in advance.

## Exact Implementation Files

1. Create `assets/lua/constraints/rules/layout-assert-calls.fnl` — private lazy candidate selection only.
2. Modify `assets/lua/constraints/rules/layout.fnl` — integrate selector in the existing named branch, coverage logic unchanged.
3. Create `assets/lua/tests/test-constraints-layout-assert-calls.fnl` — semantic, dynamic and laziness cases.
4. Modify `assets/lua/tests/test-constraints-rules-layout.fnl` — merge new tests exactly once through existing aggregator; fast registration unchanged.
5. Modify `docs/dev/constraints.md` — invocation lifetime, selection/fallback contract, work proof and evidence limits.

The saved plan is a separate coordination checkpoint. No baseline path is authorized. Existing layout module1166lines is near1200; the selector is a focused private module rather than unrelated restructuring.

### Task 1: Prepare Reference, Regression and Work Evidence

**Files:** new selector tests and existing layout-test aggregator; ignored baseline/source-corpus/differential/work driver artifacts. No production selector/layout change before valid RED.

**Interfaces:** existing Layout.rules selected `.run(ctx)`, tests.constraints-layout-helpers make-file-fact/make-ctx/find-rule-by-id; new test module exports name/tests/main and is merged once by aggregator. No new production export for measuring work.

- [ ] Record BASE/branch/status/index/runtime/source hashes. Freeze original layout module directly from Git BASE and complete ordered1361-source corpus into new ignored evidence, with path/hash inventory. Do not use edited worktree as historical reference or modify old experiments.
- [ ] Add public-rule cases asserting complete diagnostics/nil and facts unchanged: named/local name collisions, duplicate names/scopes, ordered multiple asserts, empty names, both keywords, nil/false call forms, nonmatching poisonous forms, no-match text fallback, cleaned-form variants, nil/false names, anonymous and recovered definitions, existing cleaning quirks. Semantic controls pass on BASE.
- [ ] Prepare private differential/work driver using project-native Fennel compiler inside build/space, not system Lua/Fennel. Original/candidate receive identical facts/target/by-file objects and complete ordered inventory; compare packed returns, nil arity, full nested diagnostic evidence/order/types and error outcomes. Compile-location prefixes may differ; sentinel identity, failing operation and semantic message must not. Include positive existing fixtures, not only all-nil corpus parity.
- [ ] Review the exact test-only source instrumentation before running it: freeze the original module, apply explicit unique traversal-counter insertions to compiled test variants only, preserve algorithms, verify source-delta hashes and independently restore module-cache scopes. No production source/hook mutation or actual-target scope reduction.
- [ ] Work RED fixture:100 calls/four named queries, two matched assertions per query. Distinguish coverage-helper invocations from actual named scans/visits. Original must demonstrate four scans/400 visits and fail the new bound of one classification/100 entries plus eight matched visits. Do not count syntax/missing-module/fixture errors as performance RED. All-anonymous/nil-name work oracle must require zero classification/eligibility demand.
- [ ] Run project-native compile→whole constraints→focused tests and the independently reviewed work driver. Capture exact argv/exits/counts; only a meaningful repeated-traversal RED permits production implementation.

### Task 2: Implement Lazy Candidate Selection

**Files:** new private selector, existing layout integration, selector tests and documentation within the five-path manifest.

**Private interface:** `create({:file-fact ff :definitions all-defs :calls calls}) -> lookup`; factory captures references only. `lookup(def)` returns an ordered candidate-call array for an eligible file or the exact original calls value for the scan path, including malformed values. Internal coverage helper replaces its unused interactive-access-texts parameter with named-calls; public rule/runner APIs unchanged.

- [ ] Creation performs no eligibility traversal, call-entry/key/form reads or classification. Invoke lookup only inside the old named branch after old nil/false-name and anonymous branches. Do not add relevance/kind/scope filtering.
- [ ] First demand uses raw, side-effect-free eligibility (`type`, getmetatable, rawget, next; no __index/__pairs/__len/__eq). Check file/definition/recovered containers and all definitions before serving any indexed query, so later dynamic definitions cannot invalidate an earlier group. Protected metatable values includingfalse mean dynamic, not absence.
- [ ] Supported indexed facts are plain dense canonical arrays and metatable-free records with string field keys/raw scalar values. Name/enclosure/callee/form are nil, false or strings; nonstring/NaN/object keys or relevant dynamic values select the existing scanner for the entire file invocation. File module/path are nil/false/strings. Avoid inspecting unrelated object payloads. Canonical facts are read-only for the invocation; no cache survives a file/run.
- [ ] Combine raw call eligibility and tentative grouping in one classification traversal. Unsupported shape discards tentative groups and permanently selects scan; it neither raises a new error nor invokes unsupported objects. Do not clean forms eagerly. Unsupported calls/containers/definitions retain original scanner equality, access ordering, error objects and ignored-input behavior, not new rejection semantics.
- [ ] Group only calleeexactlyassert by exact `(or call.enclosing-fn "")` semantics; append original references in original ipairs order, preserving formnil/false. No deduplication or coverage-result caching. Keep named helper's original match predicate/matched-presence flag/cleaning/keyword loop/all-keyword conservative result and text fallback, changing only its iterable. build-bare-covered receives original calls unchanged.
- [ ] Dynamic regressions compare original/candidate numeric/true/table/function/NaN names/enclosures, sparse arrays, non-table entries, nil/false containers, metatable-bearing calls/containers/current/later/recovered definitions, __index sentinel errors and __eq side effects, plus a later definition mutating earlier calls. Require identical observable access traces/error ordering. Unmatched poisonous forms remain ignored; matched invalid forms retain failure. If raw eligibility cannot prove safety, use scanner, not guessed normalization.
- [ ] Work GREEN: zero work for nil/false/anonymous-only fixtures, exactly one100-entry classification and eight matched visits for four named queries, same-name queries revisit their ordered group without rebuilding. Use reviewed test-only counters, never wall-time assertions or production test hooks.
- [ ] Document invocation lifetime, immutable canonical fast-path/raw dynamic fallback, no eager cleaning and priorQ×C versus oneC+sum matched-group visits (plus linear definition eligibility). Preserve all ownership/progress/privacy documentation.

### Task 3: Equivalence, Performance and Checkpoint

**Files:** complete five-path implementation and ignored assert-index report/manifest/diff/source/evidence hashes. No extra production paths.

- [ ] Freshness makebuild tool14400000 when needed, makecmake600000 only if needed. Runtime environment SKIP_KEYRING_TESTS1/XDG_DATA_HOME=/tmp/space/tests/xdg-data/SPACE_DISABLE_AUDIO1/absoluteassets and both Fennel paths; unset filters/profiling/deadline overrides.
- [ ] Compile first, whole makeconstraints second, then unfiltered `xvfb-run -a ./build/space -m tests.test-constraints-layout-assert-calls:main` and complete `tests.test-constraints-rules-layout:main`. Nonzero cases and failure propagation required. No baseline/limit relaxation; parse repair at nearest enclosing form then recompile.
- [ ] Differential compare complete ordered frozenBASE corpus AND complete current repository corpus with new modules, no omitted files/recovered parents/outliers. Positive/negative existing fixtures and dynamic/sentinel matrix must be nonvacuous. Preserve full error semantics beyond source-location prefixes; no count-only parity.
- [ ] At least three alternating ORIGINAL/CANDIDATE full-corpus pairs with no wrappers/counters, same facts, disclosed warmup/order and every sample/variability. Performance is observational; no flaky timing threshold and no Wine guarantee. Bracket any instrumentation separately.
- [ ] Original hook-bearing regression vector remains source/facts/runner/default-run/test-runner/List in that order, fullrepo/five suites/baselinefalse/default120 intact. Require actual current cases/exits, not stale imported counts. Run standard-environment full make test with14400000 allowance because shared analyzer gates repository-wide tests. Host-only Python suites need not repeat solely for this private Fennel selector.
- [ ] Full independent five-path review including new files, all accepted fixes, RED/GREEN/work/differential/raw uninstrumented evidence; controller checks BASE/status/exclusive scope/index/hashes and entire patch. Only explicit Phase2 authorizes exact reviewed commit, then clean tree/index. This is a source checkpoint, not final feature completion.
- [ ] After source gates/review/checkpoint, guarded actual reproduction ONLY via windows-ci-reproducer, unchanged `python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .`, tool14400000/internal deadlines unchanged. Reconcile original five List cases/new List regressions and fullrepo timeout by name; remaining timeout requires diagnosis, not another unapproved optimization.

## Self-Review and Escalation

### First Implementation Gate Refinement

Advisor `ses_ea5a00cd3fferf7Fii4xJ4o3Ov` confirmed all43 initial diagnostics: raw generic-for iterator misuse,17 relocated old findings plus17 stale entries, new121-line rule function and seven helper alternative/doctrine findings. Add ONLY `assets/lua/constraints/baseline-data.fnl` as the sixth implementation path; no other scope expansion.

- [ ] Correct the three raw iterations using the project-verified iterator/state tuple `(values next object)`, not `next(object)` and not pairs/metamethod traversal. Verify spelling through the embedded runtime before accepting it.
- [ ] Replace the new selector's boolean/value alternatives with explicit branches preserving exact nil/false/value and short-circuit semantics, including nested create/lookup forms and expected absent-group behavior. No dummy assertion, unsupported-input rejection or rule bypass.
- [ ] Extract the existing definition/recovered-parent merge into a focused private helper to satisfy function length in code. Preserve fresh array, merge/call-read order, field-read behavior and nil/false optional-array defaults; no masking/coverage/cleaner change, line-count gaming or new length exception.
- [ ] After source structure settles, relocate ONLY the17 demonstrated existing baseline findings one-to-one using actual new positions/fingerprints and unchanged/reduced measures. Do not add debt, raise limits or regenerate unrelated rows. Compile→wholeconstraints→new semantic module and complete layout aggregator, then separately reviewed fresh work/differential instrumentation remains required before execution.

One authoritative coverage algorithm remains; selector changes candidate filtering only. Exact manifest/API/keys, lazy errors/accesses, raw fallback, nonvacuous equivalence, deterministic work and separate timing evidence are specified. No product decision is identified. If scope/API changes are needed, stop for coordinator/plan refinement; HUMAN_DECISION_REQUIRED only for a genuine unresolved product/API/data/architecture/access choice. Original publication controlled Tasks7–9, current-origin/whole-branch/PRCI integration gates remain separate and mandatory.
