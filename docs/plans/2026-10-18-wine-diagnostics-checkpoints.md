# Wine Diagnostics Checkpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the full portability Task6 diagnostic contract in three reviewable source checkpoints.

**Architecture:** Separate fixture observations, injected production observation, and bounded test-only formatting/integration. All original workload, outcome, privacy and deadline contracts remain unchanged.

**Tech Stack:** Fennel/Lua, existing constraints pipeline and test runner.

## Global Constraints

- Refines only Task6 of `docs/plans/2026-10-18-wine-suite-portability-repairs.md`; inherit its globals/shared validation and all original Task6 acceptance requirements. Worker reads only those shared sections and its own subtask, never the entire coordination plan.
- Source at split: clean8ee118ff8b974ec42b77f49474956494d5038591; prior fresh worker declined capacity before edits. No diagnostic WIP to recover.
- Sequence6A review/checkpoint →6B review/checkpoint →6C review/checkpoint →Task7 cumulative source gate →guarded actual Wine. No actual Wine before all three and that gate.
- Every checkpoint is unfinished unstaged Phase1 →independent review/fixes →authorized exact Phase2 commit. No skipped checks, arbitrary selector/command, budget/rule/baseline change, guessed normalization/optimization or root-cause claim.
- Preserve120s/outer1800/10000-instruction latched hook/teardown. No flamegraph, per-rule timeout, coroutine, replacement hook or new protected workload wrapper.
- Only new source file is test-only `assets/lua/tests/constraint-progress.fnl`. Production observers own no environment/clock/formatting/output.
- Validation canonical environment and makebuild14400000 freshness as needed; project compile first, whole constraints second, assigned focused tests third. Unexpected failures require systematic diagnosis/advisor before further fixes. Supervisor alone edits ledger.

### Task 6A: List Fixture Observations

**Files:** modify only `assets/lua/tests/test-list-entities.fnl`, `docs/dev/notes/test-harness-cleanup.md`.

**Interfaces:** existing SPACE_TEST_TIMINGS=1 and intercepted JsonUtils write seam; no exported API/counting-predicate change.

- [ ] Fixless observation at all five affected scenarios: actual fixture prefix/write path, fs.absolute equivalents, existing raw-prefix predicate and canonical intended-destination equality. Keep roots/counters/expectedarrays/disk/signal/cleanup unchanged.
- [ ] At most2observations/scenario,12escapedlines/module,1024encodedbytes/line. Only generated test-owned fixture paths; unrelated writes excluded. No runtime-private/session data or record contents. Explain unproven hypothesis.
- [ ] Tests cover scalar/escaped/bounded output and no output when disabled without weakening existing oracles. Compile→constraints→`[:tests.test-list-entities]`; compare timings off/on outcomes, elapsed/output and bounds, assess overhead. Independent full two-path review/checkpoint.

### Task 6B: Injected Constraints Observer

**Files:** modify only `assets/lua/constraints/runner.fnl`, `assets/lua/constraints/source.fnl`, `assets/lua/constraints/facts.fnl`, `assets/lua/tests/test-constraints-source.fnl`, `assets/lua/tests/test-constraints-facts.fnl`, `assets/lua/tests/test-constraints-runner.fnl`, `docs/dev/constraints.md`.

**Interfaces:** optional `opts.observer(event)->nil` in Runner.run-target forwarded to `Source.discover(target, observer?)` and `Facts.extract(records, observer?)`; unchanged returns. Event allowlist: edge begin/end; phase discover/facts/select/rule/baseline/summarize; optional subphase scan/read/parse/extract/recover/span, safe relative file, 1-based index, registered rule-id, nonnegative count/definitions/calls. Unsafe relative metadata uses index, never absolute fallback. No timestamps/AST/source/diagnostic/result payload.

- [ ] Add compatibility/parity/order/privacy/error regressions before production observer edits: same discovery/facts/results/diagnostics/counts/order/status, no fabricated end after raised workload error.
- [ ] Notify existing Runner phase/rule, Source scan/read/parse and Facts extract/recover/span boundaries. Nil observer allocates no event tables/clocks. Production reads no timing env, writes nothing, imports no writer, installs no hook. No altered workload exception boundary.
- [ ] Document schema/ownership. Compile→constraints→`[:tests.test-constraints-source :tests.test-constraints-facts :tests.test-constraints-runner]`; independent seven-path review/checkpoint. This remains inactive instrumentation, not measured cause or timeout fix.

### Task 6C: Bounded Test Writer and Full-Repo Integration

**Files:** create `assets/lua/tests/constraint-progress.fnl`; modify only `assets/lua/tests/test-constraints-default-run.fnl`, `docs/dev/constraints.md`.

**Interfaces:** consume6B schema; `ConstraintProgress.create({:now-ms (() -> number) :write ((string) -> nil) :detail-phase string|nil})->observer`. Inject clock/sink; write receives complete bounded encoded line immediately, live sink adds newline/flushes.

- [ ] All writer unit/cap/privacy/escaping/fakeclock/sink/flush and associated hook tests reside in existing default-run module. Use existing runner test APIs and synthetic events/sinks to prove installed/restored latched deadline including caught inner exceptions. If required runner API is not exported, stop for a bounded refinement rather than editing runner or weakening hook proof.
- [ ] Phase-first detail-phase=nil: monotonic begin/end, aggregate file work without history, max256lines×256bytes. Later measured single-phase detail max2MiB,512bytes/line, explicit cap marker included in limits. Safe relative metadata/scalars only; preserve unmatched starts/no false ends. Distinct custom prefix, no marker parser/schema changes. Existing~642KiB plus caps below16MiB capture.
- [ ] Inject only existing full-repo default-run test when existing SPACE_TEST_TIMINGS exactly1; private detail-phase literal remainsnil first run. Samefullroots/five suites/baselinefalse/assertions/120s/outer1800. Production modules unchanged in6C.
- [ ] Compile→whole constraints→`[:tests.test-constraints-source :tests.test-constraints-facts :tests.test-constraints-runner :tests.test-constraints-default-run :tests.test-runner :tests.test-list-entities]`. Compare native on/off elapsed/output/outcomes and assess material overhead before Wine; independent three-path review/checkpoint.

## Reports and Downstream Acceptance

Task6C domain interruption: execute `docs/plans/2026-10-18-constraint-scenario-ownership.md` as a separately reviewed ownership repair before resuming6C validation. Preserve the existing writer/default-run WIP byte-for-byte and exclude it from the repair commit. This refinement does not waive any6C/Task7 gate.

Under `.superpowers/sdd/wine-posix-publication/` use task prefixes `suite-portability-task-6a`, `suite-portability-task-6b`, `suite-portability-task-6c`: report.md, full review.diff including new contents, manifest.md, source hashes.sha256, evidence-hashes.sha256 and command logs. Record BASE/scope/index/constraint impact/RED-GREEN/parity/privacy/caps/hooks/overhead as applicable. Preserve preceding evidence; reviewer PASS precedes exact commit.

Original Task7 consumes all three checkpoint reports and its focused/native/provider/seven-host/fullLinux/diff/cumulative-review gates before actual guarded full reproduction. Actual measurements still gate any List fix or constraints optimization. Original publication Tasks7–9 remain separate. No feature/PR readiness claim or publishing action here.
