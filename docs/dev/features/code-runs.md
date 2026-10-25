# Code runs

A code entity is a program. A **code run** is one invocation of its source through
a kernel. Code runs are independent of workflow definitions, workflow runs, and
LLM sessions. They persist under `<user-data-dir>/code-runs/` and are exposed as
`code-run:<id>` graph adapters.

## Ordinary execution

Pressing Run creates a durable record before evaluating the code, and reveals
that run in the requesting graph map, linked from the code entity. Successful
ordinary return completes the run, including `nil` or `false`. An exception
fails the run. Returning an object or function does not opt into async behavior.

The record contains its execution-time source/name/language/kernel snapshot,
resolved kernel configuration, start/finish times, monotonic elapsed duration,
captured output, final result display/type, errors/tracebacks, and artifact keys.
Results are inspection text, not executable serialized Lua objects. History
survives source edits and deletion.

## Deleting runs

A code-run node's context menu offers **Delete Run** for terminal runs only
(`succeeded`, `failed`, `timed-out`, `interrupted`). Deleting removes the stored
record and removes the run adapter from every open graph map; run history on the
owning code entity refreshes. Running runs refuse deletion explicitly — wait for
completion, failure, or timeout. Deleting a run never deletes its artifacts: a
report produced by a run is an independent record owned by its own store.

The full code-entity view includes searchable run history. Selecting a row
reveals only that run; Latest Run reveals the newest stored record. Historical
runs and artifacts are not expanded automatically. The run's full view exposes
source and payloads; its preview contains compact metadata and navigation only.

## Explicit deferred completion (internal Fennel kernel)

Every internal execution receives a private `execution` context:

```fennel
(local done (execution:defer))
(some-async-operation
  (execution:wrap
    (fn [response]
      (when response.error (error response.error))
      (execution:attach-artifact response.report-key "Analysis report")
      (done:succeed "Analysis complete"))))
"Analysis started"
```

- `execution:defer()` returns one run-owned completion handle. Calling it twice
  is an error. Initial return is then recorded separately, not treated as success.
- `done:succeed(value)` or `done:fail(error)` explicitly completes the run.
- `execution:wrap(callback)` catches callback exceptions and fails the same run.
  Normal callback return does not imply completion. Wrap all async entry points.
- Completion is staged until the initial evaluation or wrapped callback unwinds;
  signalling success and then throwing produces a failed run, not a false success.
- Conflicting completion signals are errors. Truly external wrapped callbacks
  arriving after completion, interruption, or timeout do not execute their bodies.
- `execution:write(text)` appends output. `print` in the evaluated source and its
  closures is run-bound and captured. Required modules, explicit `_G.print`, native
  logging, and arbitrary stdout writes are not redirected. Captured output is
  limited to 1 MiB per run; exceeding that limit explicitly fails the execution.
- `execution:attach-artifact(graph-key, label?)` stores an explicit graph reference.
  Reattaching a key is idempotent. Files may use an existing `fs:/absolute/path`
  key. Artifact contents remain owned by their existing stores/filesystems.
- `execution.id` and `execution.code-entity-id` identify the invocation and source.

Evaluation uses a fresh shallow global environment containing the run context
and bound print function. Global assignments in that environment are run-local;
shared objects such as `app` and imported modules remain shared. This is not a
sandbox. Use explicit shared services for deliberate cross-run state.

## Live progress

Internal Fennel runs stream progress through the run's `output` field: `print`
inside the evaluated source and its callbacks is run-bound, and
`execution:write(text)` appends explicitly. Every append persists immediately and
emits, so an open code-run node live-updates while the run is running. The
preview and full view show the same content — output, initial return, result,
and error — with one difference: the preview bounds the output to a recent
tail, while the full view shows all of it. The executed source is never inlined;
**Show Code** loads the source entity instead. The node label also shows the
current status, and the owning code entity's preview result label streams the
same live progress (status plus output tail while running; the result or error
head once terminal) after the initial return. Each line costs one persisted
update; the 1 MiB output cap bounds runaway loops, but very chatty loops still
pay per-line persistence. There is no separate stderr channel: failures carry
their message and traceback in the run's error record. External kernels receive
no host completion context and deliver combined stdout/stderr only with their
final reply; streaming for external kernels would need a protocol extension.

## Deadlines and lifetime

`app.code-runner:run(code-entity-id, {:timeout-ms 900000})` starts a run; fifteen
minutes is the default. A process-owned callback-queue pump checks elapsed time,
independent of UI next-frame delivery. Timeouts are logical terminal outcomes,
not preemption of arbitrary code or rollback of side effects. Synchronous code
must return/yield before its deadline can be observed. Completion after an elapsed
deadline is recorded as timed out even if the deadline pump has not yet run.

Graph/widget teardown detaches presentation, not execution. App-root teardown
marks owned active runs interrupted and invalidates their callbacks before
kernels disappear. No automatic retries or automatic code re-execution occur.

On Linux, cold recovery marks a persisted active run interrupted only after the
specific owner is proven dead using boot ID, PID, and process start ticks. Live
peer app instances are not interrupted. Hosts without that identity probe retain
unverified running records rather than falsely declaring another owner's death.

## External kernels

Existing external kernels get source/provenance/output/error/timing records via
their ordinary reply protocol. The `execution` context and deferred-completion
API are not injected into arbitrary subprocess languages. Duration includes any
kernel queue wait. A host timeout does not terminate a shared kernel or discard
its outstanding REQ/REP reply; late replies cannot revive the terminal run.

## Ownership

`app.code-run-store` owns the durable records. `app.code-runner` owns active
executions and deadline checks. Graph nodes and views borrow those services and
own only their subscriptions/widgets. Run artifact links are historical
references, not reference-lifecycle deletion cascades or duplicate domain data.
