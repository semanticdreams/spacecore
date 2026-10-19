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

**Task1B Scene/Sandbox isolation remains pending:** the real routing rule still
needs its fresh rule-owned Lua fixture and exception-safe resource cleanup before
it is safe to certify against a borrowed caller. Task1A helper validation does
not exercise that consumer against a borrowed test runtime or certify the
unchanged205-case combined regression gate. That gate, Task6C timing validation,
actual Wine evidence and final integration remain separate later requirements.

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
test-only writer integration is a separate checkpoint. Existing budgets and
exception boundaries remain unchanged.

## Constraint Families

The current constraints are grouped into four families:

- **Scene/Sandbox** — protects scene ownership and sandbox boundaries.
- **Lifecycle** — catches stale callback, teardown, drop, and ownership mistakes.
- **Layout/rendering** — checks layout/rendering contracts that are expensive to debug at runtime.
- **Structure/formatting** — keeps Fennel modules within reviewed structural and formatting limits.

These constraints complement human review and normal unit/integration tests; they do not replace either one.

## Baselines

Baselines are reviewed, versioned project data for accepted existing violations. They are not a bypass flag.

A baseline entry records the known exception with its file, rule, current measure, and reason. The gate still blocks when:

- a new violation appears;
- an existing baseline violation worsens;
- a baseline entry becomes stale and no longer matches the current code;
- a required constraint disappears;
- a constraint fails or is interrupted.

When a baseline becomes stale because the code improved, update the reviewed baseline data instead of leaving dead exceptions behind.
