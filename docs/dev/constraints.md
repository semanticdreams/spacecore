# Fennel Constraints

The constraints gate checks repository Fennel code before normal Fennel tests run. It combines source facts from the Fennel parser with executable scenario checks so structural, lifecycle, layout, rendering, Scene, and Sandbox mistakes are caught early.

The gate is blocking. If a constraint is noisy or wrong, fix or remove that constraint through normal reviewed code. Do not bypass the gate.

## Daily Workflow

Run the compile gate before the constraints gate, then run focused Fennel test
runs:

```bash
make fennel-check
```

Then run constraints:

```bash
make constraints
```

`make constraints` runs the default repository target over `assets/lua/` with the runtime environment configured for the Space asset tree and Fennel module paths. A clean repository run exits successfully with status `pass` and 0 diagnostics.

`make test` already depends on `make constraints`, so full test runs execute the constraints gate first. You do not need to run `make constraints` separately immediately before `make test`, but running it before narrowed Fennel tests gives faster feedback and keeps focused runs honest.

## Relationship to Fennel Compile Check

`make fennel-check` is the first-stage syntax oracle for Space Fennel. It runs
the vendored compiler through `./build/space -m tools.fennel-check:main -- --target repo`,
so agents should use it instead of system `fennel`, system `lua`, `fennel-ls`,
or `fnlfmt` validation.

`make constraints` runs after the compile check. The compile gate catches invalid
Fennel syntax and delimiter/enclosing form errors before structural constraints
attempt to analyze source facts; constraints then enforce higher-level lifecycle,
layout, rendering, Scene, Sandbox, and structure rules.

## CI Workflow

GitHub Actions `test.yml` runs `make constraints` explicitly after the Linux build. This gives constraint failures a fast, named `Run constraints` step in CI logs.

The broader CTest suite still keeps its `space_constraints` fixture dependency, so normal test execution remains structurally gated as defense in depth. The explicit GitHub Actions step improves failure visibility; the CTest fixture remains the blocking integration gate.

## Agent Workflow

Treat constraints as early feedback that reduces review and fix cycles, not as a ritual to satisfy after the fact. For Fennel-facing implementation work, run `make constraints` before narrowed Fennel test commands when feasible, then run the focused test with the usual runtime environment. If the final validation is the full `make test`, that command already gates constraints; do not duplicate the same gate unless earlier feedback would save time.

Handoffs for Fennel-facing feature or bugfix work should include a lightweight constraint-impact note: `helped catch`, `obstructed/noisy`, `changed constraint`, or `not applicable`. Reviewers should verify that constraint validation was reported, or that the report explains why it does not apply. Unresolved `violations`, `fail`, or `interrupted` statuses are validation failures.

When an intentional architecture transition conflicts with a constraint that encodes the old contract, update the production code and the constraint contract together through reviewed changes. Do not contort production code around a stale rule, skip the gate, or add broad baselines/allowlists just to make the gate green. If the new contract is ambiguous, pause for clarification before changing constraints.

`make constraints` prints concise summaries by default to keep local and agent logs readable. Use `make constraints VERBOSE=1` for the full JSON payload from both `fennel-check` and the constraints runner, or call `./build/space -m constraints.runner:main -- --output json --target repo` directly when debugging parser/constraint details.

## Runner Statuses

The runner reports one of four result statuses:

- `pass` — all required constraints ran and no unaccepted diagnostics remain.
- `violations` — one or more constraints found new, stale, or worsened diagnostics.
- `fail` — a constraint or runner operation failed before producing a valid pass result.
- `interrupted` — a cooperative/CPU-bound Lua constraint run was interrupted.

Every status other than `pass` exits nonzero and blocks the workflow.

## Targets

The Make target is the normal repository workflow. The runner can also be invoked directly for repository, unit-root, app-root, or explicit-file checks:

```bash
./build/space -m constraints.runner:main -- --target repo
./build/space -m constraints.runner:main -- --target unit --root /path/to/unit-root
./build/space -m constraints.runner:main -- --target app --root /path/to/app-scripts
./build/space -m constraints.runner:main -- --target files --file /path/to/one.fnl --file /path/to/two.fnl
```

Use neutral absolute paths for external unit, app, or file targets. Production modules should not import or call constraint modules.

## Scenario Helper Runtime Ownership

`constraints.scenarios.with-test-app(f)` returns only the first result of `f`,
including nil or false. Escaping body errors retain a traceback and the
`scenario failed: ` prefix. Setup and cleanup errors are explicit; cleanup errors
are appended without replacing a primary failure, and cleanup-only failure still
fails the scenario.

The helper has two bounded ownership modes:

- **Verified test caller:** borrow the exact app and already-started,
  non-shutdown Engine. The caller must be a table marked `testing`, have cached
  `main`, Engine physics/jobs, initialized interaction/theme/light services, and
  a jobs preload that resolves to its Engine's jobs. A cached jobs module, when
  present, must be that same object. Borrowing performs no setup, app drop,
  Engine construction/start/shutdown, main reload, or native jobs rebinding.
  It restores the captured global app reference on body unwind. Invalid nonnil
  callers fail before the body rather than creating a nested Engine.
- **Owned standalone:** setup is allowed only for an absent app or the pristine
  native CLI bootstrap: an ordinary empty table with no metatable/raw Engine and
  genuinely nil cached main, jobs preload and cached jobs. False is not absence.
  Setup itself is protected; its allocated app/Engine are captured at the setup
  success/error boundary before body or teardown can replace global app. The
  captured app teardown and Engine finalization are independently attempted,
  using the test runner's one-attempt started-owner policy (skip unstarted or
  already-shutdown Engines). Caller app identity/content, reset-engine-events,
  package namespace and loaded/preload table identities and complete slot
  membership are restored independently, including false values and absent keys.

This is not arbitrary live-UI rollback or a native ownership-restoration API.
Module membership restoration is shallow: it does not reverse mutations inside
shared module objects or promises about unrelated globals. Borrowed scenario
bodies must own and clean up their Lua resources; the helper does not snapshot
the caller's canvas, activity registry, sessions, selection or mutable services.

The Scene/Sandbox routing scenario installs a private, fresh Lua app fixture
inside this helper. Only the verified caller's Engine and read-only themes are
shared. Canonical interaction services and LightSystem, projection factory,
canvas/runtime, activity registry, sessions and signals belong to the fixture;
caller renderers, hooks, callbacks and selection are never installed there.
The scenario still loads and activates the real Sandbox activity and checks its
actual Scene slot for render context and layout-root routing.

Each returned Camera, Scene and interaction service is recorded before the next
failure point. Cleanup independently attempts activity deactivation, session
cleanup, unregistration, Scene drop, Camera drop and interaction-service drops
under the fixture app, then always restores the exact caller app. Activity
selection/session references are detached after their cleanup attempt, including
on failure, so unregister's internal teardown cannot retry an attempted owner.
LightSystem has no drop API. Primary tracebacks are preserved and cleanup-stage
errors are appended; cleanup-only failures still fail the scenario through the
helper's existing `scenario failed: ` prefix.

These are bounded test-runtime ownership guarantees, not arbitrary UI rollback
or recovery of resources that a constructor never returned. Other scenario
bodies must provide their own isolation. Task6C timing validation, actual Wine
evidence and final integration remain separate requirements.

## Injected Pipeline Observer

`Runner.run-target(target, opts?)` accepts an optional `opts.observer(event) -> nil`.
It forwards that callback to `Source.discover(target, observer?)` and
`Facts.extract(records, observer?)`; all existing return values and one-argument
calls are unchanged. This is inactive diagnostic instrumentation, not a timeout
fix or a measured explanation of the Wine full-repository timeout.

The constraints pipeline owns this event schema. Every event is a fresh table
containing only these scalar fields (optional fields are omitted when unavailable):

| Field | Values / meaning |
| --- | --- |
| `edge` | `begin` or `end` |
| `phase` | `discover`, `facts`, `select`, `rule`, `baseline`, `summarize` |
| `subphase` | Optional `scan`, `read`, `parse` (discover) or `extract`, `recover`, `span` (facts) |
| `file` | Optional safe forward-slash relative file; never an absolute-path fallback |
| `index` | Optional 1-based file index in discovery/record order, or selected-rule index |
| `rule-id` | Registered rule identifier on rule events |
| `count` | Nonnegative count: discovered files, extracted files, selected rules, rule diagnostics, post-baseline diagnostics or summarized diagnostics, according to phase |
| `definitions`, `calls` | Nonnegative file-fact counts on facts subphase end events |

Runner emits discover → facts → select, one begin/end pair per selected rule in
registry order, then baseline → summarize. Source emits scan around collection,
sorting, deduplication and module-root normalization, then read/parse per sorted
file. Parse ends when `ts.parse` returns; existing root/metadata projection follows.
Facts emits extract → recover → span for each record, including the existing
recovery call on non-ERROR trees and span correction on every file. Baseline
events also bracket the disabled-policy path; no policy is applied in that path.

File metadata rejects empty, absolute, drive/UNC, backslash, control-character,
empty-segment, dot-segment and trailing-slash spellings. Unsafe or unavailable
relative metadata uses the index alone, without changing any record/fact path
projection. Events never contain source text, ASTs, diagnostics, result/status
payloads, timestamps or absolute paths.

Begin is delivered before its work; end only after that work returns normally.
Escaping workload errors leave unmatched begins. A rule's existing guarded
execution can return crash/interruption diagnostics; that is a returned rule
operation and has an end event, not a claim that the rule passed. Observer calls
are synchronous and unprotected: callback errors propagate directly, outside the
existing guarded rule body, without being converted into framework diagnostics.
Observers must not mutate pipeline state and should return nil.

With no observer, no event tables are allocated and no observation clocks run.
These production modules add no environment switch, clock, formatting, output,
writer import, protected workload wrapper, coroutine, deadline or hook. Consumers
own any opt-in policy, clock, bounded formatting/output and overhead assessment;
the bounded test-only consumer is described below. Existing budgets and exception
boundaries remain unchanged.

### Bounded Full-Repository Test Progress

`tests.constraint-progress` is a test-only consumer, not a production dependency
or a generic profiler. Its sole export is:

```text
ConstraintProgress.create({now-ms = () -> number,
                           write = (string) -> nil,
                           detail-phase = string | nil}) -> observer
```

The caller injects the monotonic wall-clock millisecond function and a synchronous
sink. The writer samples that clock at creation and on valid events, reports
relative `at_ms` and completed `elapsed_ms`, and clamps backward samples to the
last observed time. Nonfinite samples fail explicitly. Each sink call receives a
complete, encoded line **without** a newline and returns before observation
continues; sink errors propagate unchanged. Every line, including the cap marker,
conservatively reserves **two terminator bytes**: the live sink supplies LF, which
text-mode stdout may expand to CRLF on Windows/Wine. On an LF-only sink this
leaves one unused byte per line; no stdout mode or callback API is changed.
This introduces no workload exception
wrapper, coroutine, replacement debug hook or per-rule timeout.

Only the existing full-repository pipeline case in
`tests.test-constraints-default-run` attaches a live observer, and only when the
existing `SPACE_TEST_TIMINGS` value is exactly `1`. For that case, disabled values
allocate no writer and call neither its clock nor sink. The live clock is `sysinfo.now-ms`;
the sink adds one newline, flushes immediately, and raises returned write/flush
errors. The full roots, all five suites, `baseline-data=false`, existing result
assertions, 120-second case deadline and 1800-second outer application deadline
are unchanged. Synthetic nested `Runner.run-case` tests verify the existing
10000-instruction hook stays installed during writes, is restored before teardown,
and retains its failure latch when an inner timeout exception is caught.

The private live `detail-phase` literal remains **nil** for the first experiment.
There is no new environment selector, command or test-runner marker/schema change.
Every diagnostic line uses the distinct `[CONSTRAINT-PROGRESS] ` prefix:

- **Phase-first (`detail-phase=nil`):** emit high-level begin/end events and, at
  phase end, fixed-subphase aggregate begin/end counts, completed elapsed totals,
  definitions and calls. Top-level `count` carries the phase's actual file, rule
  or diagnostic count. Individual file events are not printed. State consists
  of fixed phase/subphase slots, never event history or a file-keyed map.
  Output is capped at **256 lines**, **256 encoded bytes per line** and
  **65536 bytes total**, including the two-byte terminator reservation per line.
  The final available line is
  reserved for `[CONSTRAINT-PROGRESS] cap reached mode=phase`.
- **Later measured detail:** the injected option may select one known pipeline
  phase. Only that phase's subphase/file edges are added to the high-level output.
  The entire observer output is capped at **2 MiB** and **512 encoded bytes per
  line**, including the two-byte terminator reservation. Space for
  `[CONSTRAINT-PROGRESS] cap reached mode=detail` and its two-byte terminator is reserved
  inside the total budget. This mode exists for a later evidence-selected
  experiment; it is not enabled by the live integration. LF output need not fill
  the physical 2-MiB bound: conservative reserved bytes, not LF bytes alone,
  determine the cap. CRLF output is bounded without that unused byte per line.

After either cap marker, further observation does no clock or formatting work.
There is no fabricated completion at a cap or after a raised workload/sink error.
An emitted end means that an end event was received, **not** that a rule passed.
Elapsed values are attached only to matched starts; aggregate `begins` and `ends`
preserve unmatched work without assigning it a completed duration. Phase elapsed
already includes its subphase work. Definitions/calls describe each subphase's
observed file-fact state, not distinct records to sum across subphases.

Formatting reads only allowlisted raw scalar fields: known phase/subphase/edge,
finite nonnegative integral counts, positive file/rule indices, registered rule
identifiers and safe relative file labels. Unsafe or absent labels use the index
without an absolute-path fallback. Labels are quoted and byte-escaped to printable
ASCII, with explicit `[truncated]` on bounded label truncation. No source, AST,
diagnostic/result payload, arbitrary object stringification, runtime-private path
or data dump is included. Number formatting is bounded and approximate (six
significant digits); these observations are diagnostics, not exact counters for
accounting or a timing API.

The phase-first allowance plus the existing approximately 642-KiB capture remains
below the 16-MiB capture limit; even the optional 2-MiB detail allowance fits within
that bound. Compare native default-module OFF/ON executed counts, ordered outcomes,
output size, phase inventory and elapsed time before actual Wine observation.
Alternating repeated local samples assess obvious instrumentation overhead but
are not a general speed guarantee. Last-started phases are not a root-cause
diagnosis; this instrumentation does not itself fix the Wine timeout. The
separately reviewed scenario-ownership repair above does not waive Task6C or
Task7's remaining measurement and integration gates.

## Constraint Families

The current constraints are grouped into four families:

- **Scene/Sandbox** — protects scene ownership and sandbox boundaries.
- **Lifecycle** — catches stale callback, teardown, drop, and ownership mistakes.
- **Layout/rendering** — checks layout/rendering contracts that are expensive to debug at runtime.
- **Structure/formatting** — keeps Fennel modules within reviewed structural and formatting limits.

These constraints complement human review and normal unit/integration tests; they do not replace either one.

### Invocation-local candidates and assertion-call selection

`layout.interactive-context-assertion` selects analysis candidates only after the
unchanged access collection, calls read, original/recovered definition merge and
reference-only assertion-selector creation. The private `select-definitions`
helper reuses the existing complete canonical classifier. Unsupported graphs
return the **identical full merged definitions array**, preserving the original
dynamic reads and errors. On canonical graphs it returns an ordered reference
subset retaining every function and every record whose form is not strictly a
string. Only nonfunction/string records are omitted: the interactive-access,
bare-keyword and dotted-access gates require function kind, so these records
cannot produce a diagnostic. Nil/false forms remain candidates, preserving their
original errors. There is no keyword-absence filter; stripping quoted text can
synthesize a keyword absent from the original form.

The FULL merged definitions array remains the masking, assertion-call and
ancestor/closure context, including omitted records and original order and
references. Only the analysis loop's iterable changes. Candidate eligibility
adds linear definition/container, call and raw-field checks, including temporary
assertion groups built by the existing classifier and then discarded. These
groups are not shared with the separate lazy assertion-call selector or cached
across files/runs.

`layout.interactive-context-assertion` keeps one private lazy selector per file
and rule invocation. Creating it only captures the file fact, merged definitions
and original calls references. Anonymous and nil/false-name coverage branches
never demand this selector's eligibility or classification; the separate candidate
pass above still runs. The first named coverage lookup
checks the entire original/recovered definition graph before serving any group;
no name, kind, scope or relevance policy is added.

The indexed path supports immutable canonical Facts: metatable-free dense arrays,
plain definition/call records with string keys and finite scalar fields, and
nil/false/string name, enclosure, callee and form fields. File module/path must
also be nil/false/strings. Raw eligibility does not invoke access, equality, length
or iteration metamethods, including protected metatables. Unrelated FileFact AST,
target, metrics and access payloads are not recursively inspected. Unsupported or
dynamic shapes discard tentative groups and retain the **actual original
scanner**, with the original calls value, accesses, ignored poison fields and
errors—not a normalized substitute or a new rejection.

Eligible groups contain original assertion call references in original `ipairs`
order, keyed by the existing enclosure-or-empty-string semantics. Duplicate
names/scopes and calls are not deduplicated. Nil/false forms still count as
matched assertions; forms are never cleaned eagerly. The coverage algorithm,
conservative all-keyword coverage, text fallback, nested-definition masking and
the original calls passed to bare/closure coverage remain unchanged. No cache
survives a file/run, and neither results nor cleaned forms are cached.

For Q named queries and C calls, repeated named filtering was Q×C entry visits.
The lazy named-call selector uses one C-entry eligibility/grouping pass plus the
sum of queried group sizes. There is also a separate C-key array-density metadata
pass (not another call-record classification), linear definition/container
eligibility and linear raw record-field checks. Thus the 100-call/four-query fixture targets
100 classified records plus eight group visits, **and 100 call-array key
visits**; it is not a claim of only 108 total operations. Repeated names revisit
their groups without rebuilding. These named-index counts exclude the additional
candidate pass described above. Zero named demands mean zero lazy named-index
work, **not zero total selection work**. Deterministic work proof uses separately
reviewed test-only compiled-source counters and bounded restored private-upvalue
wrapping, never production instrumentation hooks, counters, observation exports
or wall-time assertions. Canonical N16/N32 nonfunction fixtures omit the original
16/32 completed masking calls with full D=N; the corresponding 256/1024 loop
visits are structurally derived work, not CPU time or a measured Wine fraction.

The candidate unsupported-field matrix excludes numeric NaN: its raw-equality
snapshot cannot verify unchanged NaN, which is not equal to itself. Positive and
negative infinity and the other unsupported-input controls remain covered; this
matrix does not establish candidate-selector NaN coverage. A NaN-aware mutation
oracle is needed before adding that coverage; existing assertion-selector NaN
fallback tests are unchanged.

Native semantic equivalence and work counts do not establish a Wine speedup or
120-second full-repository compliance. Uninstrumented alternating comparisons,
the unchanged hook-bearing regression vector, full local suite and guarded
actual reproduction remain separate gates. Selection adds no telemetry or
progress/privacy contract changes, and changes no baseline, rule or timeout limit.

## Baselines

Baselines are reviewed, versioned project data for accepted existing violations. They are not a bypass flag.

A baseline entry records the known exception with its file, rule, current measure, and reason. The gate still blocks when:

- a new violation appears;
- an existing baseline violation worsens;
- a baseline entry becomes stale and no longer matches the current code;
- a required constraint disappears;
- a constraint fails or is interrupted.

When a baseline becomes stale because the code improved, update the reviewed baseline data instead of leaving dead exceptions behind.
