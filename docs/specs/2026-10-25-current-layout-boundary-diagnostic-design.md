# Current-source interactive layout boundary diagnostic

## Purpose and authority

This is a bounded diagnostic transition for the existing graph/publication
contract's required Wine acceptance gate. It authorizes no optimization, new
graph feature, production publication change, deadline increase, skip, or baseline
allowance. It does not reactivate historical Facts profiler work.

Evidence source is `3af3743901496058dadb03c601ef9ccefa94bed5`, actual sequential run
`build/windows-ci-repro/20261025T063805379446Z-ada8ac9e92ac4571a8ff93a0b6fe7c40/`.
Publication passed with all four privately observed components, reports and
application promotion. Full Wine completed with4782PASS/1FAIL, application exit1;
only `runner run-target with repo target runs full pipeline` hit its existing120s
case limit. It was not OOM, external interruption or the1800s application deadline.

The current trace measures discovery6.223s, Facts52.281s, and prior rules9.095s.
The interactive rule begins at67.599s; the outer test timeout is caught inside its
rule guard at120s and the pipeline subsequently continues. Its52.401s is censored,
not natural rule runtime. Complete analysis within120s has not been established.
The source's all-definition masking loop is a credible quadratic-work candidate,
but its share versus other work is unmeasured. Existing assertion-call indexing
must not be duplicated; Facts span work alone is not the measured dominant cause.

The untouched `.superpowers/sdd/facts-span-diagnostic/**` artifacts remain frozen
and UNEXECUTED at their old authority. No opening, execution, reuse, resealing or
silent source-authority refresh of them is part of this transition. New runtime
evidence belongs only in `.superpowers/sdd/current-layout-boundary-diagnostic/`.

## Chosen scope

Use the existing optional pipeline observer and test-only progress consumer.
Forward it internally into rule context; place boundaries around unchanged file,
mask and remaining-definition work. The existing full-pipeline test owner selects
its already supported private `detail-phase=:rule`, still gated by exactly
`SPACE_TEST_TIMINGS="1"`. No new option, environment selector, CLI, hook, profiler
process, Source/Facts instrumentation or public runner signature is introduced.

File-only timing cannot distinguish masking from residual work. Per-pair counters
would perturb the suspected hot loop. Boundary-only observation is sufficient for
the first falsifiable experiment and is the selected minimal approach.

Exactly eight implementation files are in scope:

- `assets/lua/constraints/runner.fnl`
- `assets/lua/constraints/rules/layout.fnl`
- `assets/lua/tests/constraint-progress.fnl`
- `assets/lua/tests/test-constraints-runner.fnl`
- new `assets/lua/tests/test-constraints-layout-progress.fnl`
- `assets/lua/tests/test-constraints-default-run.fnl`
- `assets/lua/tests/fast.fnl`
- `docs/dev/constraints.md`

The dedicated new test module carries substantial new parity/consumer tests and
is registered once; no original case moves or disappears. Default-run changes
are the live private mode literal and two existing owner-test expectation migrations
to interactive events, preserving opt-in, disabled-output, immediate-flush and
restoration checks. This is controller-approved maintenance of the selected mode,
not permission to weaken their coverage. New inventory is expected1365files, but
the actual observed Facts count determines all output limits.

No module-length/function/depth threshold or allowance may grow. Layout currently
has1171displayed lines, close to the1200module metric. Keep localized instrumentation
clean and compact, not formatting golf; if this cannot fit, stop for reviewed
bounded decomposition before expanding the manifest. No unrelated refactor.

## Observer forwarding and exception ownership

Public `Runner.run-target(target, opts?)` and
`Runner.run-rule(rule, target, timeout-seconds, rule-id)` remain unchanged.
Internal rule context becomes `{:facts fact-db, :observer notify?}`; the Facts
reference is the exact original object, and absent observer creates no new field.

Private `make-rule-observer(observer)` returns `(notify, raise-observer-error)`
only when an observer exists. `notify` pcalls only callback delivery, not rule
work, latches the first failure using a separate presence boolean (table/false/nil
values all preserved), then rethrows the same value into the existing rule guard.
Immediately after run-rule restores any owned hook, raise the latched original
callback failure outside that guard before result processing or top-level rule END.
It must not become a framework diagnostic accepted as successful observation.
Existing top-level pipeline notifications retain their synchronous behavior.

If the timeout occurs during rule work, the unchanged guard may catch it and emit
top-level rule END; the consumer can then emit an unfinished summary. If it occurs
during callback delivery, the relay may abort before that END. Missing summary is
honest incomplete capture; no finally/completion synthesis is allowed. Both paths
must preserve the original test timeout FAIL latch, previous hook restoration and
teardown. Successful-observation semantic parity is required, not a claim that new
callback failures leave execution control flow identical.

## Inactive path and semantic parity

Without an observer there are no new observation factory calls, event tables,
clock calls, diagnostic counters/state, output or retained history. A one-time
path selection is allowed. Read optional context observer with raw table access,
not a new dynamic __index invocation. All new layout event allocation is isolated
in private `make-interactive-observation(observer)` and guarded by observer presence.
Layout itself owns no timing, diagnostic counters, formatting or history.

Preserve original file/definition order, counts, calls/merge accesses, dynamic
form-read sequence, assertion selection, complete ordered diagnostics, exact
one-value/nil behavior and all input references/raw membership. Do not move masking
after eligibility or change masking, analysis, outer-only-form, lexical spans or
dynamic fallbacks. No extra traversal of definitions, calls or forms.

Tests must compare independent fixture instances for active/inactive parity,
including recovered parents, locals, duplicates, identical/non-nested forms and
throwing dynamic accessors. Preserve known calls read sequence
`calls, definitions, recovered-parents, recovered-parents`, dynamic assertion reads
`first, first, second, second`, and explicit dynamic definition-form read order.
Throwing private-factory spies with restored upvalues and active controls combine
with structural event-allocation review; no new production test export is allowed.

## Internal boundary events

Every new event is a fresh scalar-only table containing only:

| Field | Contract |
|---|---|
| phase | rule |
| rule-id | layout.interactive-context-assertion |
| edge | begin or end |
| subphase | interactive-file, interactive-mask, interactive-analysis |
| index | existing positive file iteration index |
| definition-index | existing positive selected-definition loop ordinal for mask/analysis (1-based, reset per file, shared by that iteration's mask and analysis boundaries; not a merged-definition position or stable source identity; coincides with the merged index on unfiltered paths) |
| definitions | #all-defs at mask BEGIN and file END only |

Private notify signature is
`notify(edge, subphase, index, definition-index?, definitions?) -> nil`.
File BEGIN is delivered before original per-file work. Mask BEGIN/END immediately
bracket the existing outer-only-form call; analysis BEGIN/END bracket the remaining
original definition body, including ordinary skipped definitions. File END occurs
only on normal file return. Use existing loop indices and observed-only merged
array length; add no per-pair or match counters. Never synthesize END during unwind.

### Reconciled index contract (2026-10-26)

`definition-index` is the 1-based ordinal in the existing selected-definition
iteration, not a merged-definition position or stable source identity. On the
unsafe/dynamic selector path (`select-definitions` returns `all-defs`), it coincides
with the merged index. `definitions` remains `#all-defs`, the complete merged
masking-context count—a different population from observed mask/analysis END
counts. Consumer pending state `pending_def` carries the same ordinal meaning.

The consumer must not require masks/analyses to equal D, interpret `pending_def` as
a merged position, or treat `pending_def/D` as completion or remaining-work
progress. Boundary completeness stays independent of rule acceptance.

Provenance: reconciled via dual-model consultation on 2026-10-26 (GLM proposal;
expert review ses_e86d6174affexO3i4m8ZAvLAcu, answered; recorded in the SDD ledger)
after current-source inspection found the compacting selector diverges selected
ordinals from merged positions.

## Test-owned timing and bounded output

`ConstraintProgress.create({now-ms, write, detail-phase}) -> observer` remains its
sole export. Private rule mode consumes other pipeline events silently, obtains
actual N from Facts END and recognizes only the named interactive rule's detail.
Clock is the owner's existing injected monotonic sysinfo clock; state is fixed
aggregate scalars plus one current-file/current-definition slot. No event lists,
per-definition history, per-file map, global cache or production timer.

Records begin `[CONSTRAINT-PROGRESS]` and use exactly these fields:

| Record | Fields |
|---|---|
| file BEGIN | phase=rule subphase=interactive edge=begin file_index at_ms stage=setup |
| file END | phase=rule subphase=interactive edge=end file_index definitions masks analyses elapsed_ms mask_ms remaining_ms |
| summary/cap | aggregate phase=rule subphase=interactive outcome files_begun files_ended definitions masks analyses elapsed_ms mask_ms remaining_ms pending_file pending_def pending_stage pending_definitions definitions_known pending_ms |

Outcome is complete/unfinished/cap; **complete means observed boundary completeness,
never rule/pipeline acceptance or deadline compliance**. Pending stage is
none/setup/mask/analysis/between; zero indices mean none. Unknown pending D uses
definitions_known=0, not a measured zero. Add known merged D once per file.
Masks/analyses count observed END notifications only. Work that returned before
its END was interrupted is not silently counted as observed completion.

File mask_ms sums completed intervals; summary additionally includes a censored
pending mask interval only when explicitly identified as pending mask. Residual
remaining_ms is elapsed_ms minus mask_ms, including setup, callback/output/GC cost,
inter-boundary work and possible unwind; it is not pure analysis CPU. Pending_ms
is since the last pending-stage boundary. Summary at top-level interactive rule
END does not manufacture missing file/definition END. Process death/relay/sink
failure before END can leave no summary; preserve that incompleteness.

The whole rule-detail mode prints at most2N+1records, each serialized line at most
512bytes, total at most2MiB, including CRLF reservation. Reserve one terminal
summary/cap record and terminator space before ordinary output. On exhaustion emit
exactly one outcome=cap record, then cease clocks, formatting and writes. No silent
truncation, extra completion record or unbounded numeric formatting. Reject
nonfinite/overflowing values explicitly. Payload is fixed enums and finite
nonnegative numbers/indices only: no source, forms, names, paths, environment values,
metatable traversal or arbitrary stringification.

No pair visits/matches or assertion-index eligibility are measured. Analysis may
derive completed_masks times D as a loop-visit lower bound excluding unfinished
invocations under the inspected loop invariant, not exact work, bytes or cost.
Instrumented elapsed time is not uninstrumented natural runtime or a Wine/native
speed ratio; disclose boundary callbacks, allocation, clock, formatting, flushing,
GC and unwind overhead.

## Gates and one observation

Before implementation, independently review SCHEMA / CONTROL / INACTIVE contracts
in the committed spec/plan. Before observation, require independently reviewed
implementation plus compile -> constraints -> focused synthetic/compatibility
tests, sequentially. No baseline/skip/deadline change to pass source gates.

New private manifest binds evidence source separately from actual implementation
HEAD/range/review IDs, spec/plan hashes, seven Fennel file hashes/sizes, unchanged
Source/Facts/assert-helper/test-runner hashes, canonical documentation and native
runtime binary hash, exact commands/environment/allowances, UTC/monotonic intervals,
raw exits and complete capture accounting. Mismatched source invalidates authority;
do not silently refresh it. Do not commit/force-add the ignored capture directory.

After reviewed source gates, run exactly one native observation ALONE, with
absolute assets/both canonical Fennel paths, disabled audio, skipped keyring,
isolated external XDG/state/cache/log/TMPDIR, CTEST_PARALLEL_LEVEL=1/BUILD_JOBS=1,
and no case/suite override:

```sh
/usr/bin/time -v -o "$ART/native.resources.txt" \
  timeout --kill-after=5s 600s \
  env TEST_FILTER='runner run-target with repo target runs full pipeline' \
      SPACE_TEST_TIMINGS=1 TEST_VERBOSE=1 \
  xvfb-run -a ./build/space -m tests.test-constraints-default-run:main \
  >"$ART/native.stdout.log" 2>"$ART/native.stderr.log"
```

ART is the new ignored diagnostic directory. Invoking tool allowance660000ms lets
the600s harness and cleanup finish; the case remains120s. Save raw exit immediately,
times/EOF/truncation/stream hashes/sizes/retirement, verify actual record/line/byte
bounds. A prerequisite failure prevents spending this single observation.

Return measurements and limitations for diagnostic judgment before optimizing.
If native evidence cannot resolve Wine distribution, a separately authorized
fresh full windows-ci-reproducer run uses14400000ms and every original bound/gate;
never direct Wine filters or an ended Session. Heavy native/Wine/host validations
are always sequential. Shared runner changes require full applicable native
validation before publication; the unchanged full Wine gate, current origin/main,
PR CI and actual merge-queue completion remain mandatory. No diagnostic result
alone completes the original feature contract.
