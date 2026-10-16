# Bounded full-suite Wine validation and owned teardown

## Confirmed diagnosis

The first reviewed, artifact-safe, instrumented reproduction at `9b261b0` is
recorded in `.superpowers/sdd/windows-validation/observed-timeout-diagnosis.md`
and its named `build/windows-ci-repro/` ledger/logs. Build, package and Wine9
builtin ProcessPrng admission passed. The fast suite reached93 RUN/92 PASS/0 FAIL
and was still progressing through subprocess-backed runner regressions when its
180-second whole-invocation deadline expired. The last PASS was9.13 seconds
before cutoff. Linux's full fast suite takes roughly518 seconds.

This establishes an insufficient whole-suite budget during continued progress,
not a compiler failure, Wine startup failure, crypto admission failure, or proof
of a hang. Later tests were not executed; their success is unknown. Separately,
descendant-held pipes survived leader exit and original process-group cleanup.
That is a lifecycle defect, not an explanation for suite slowness.

## Direction

A timeout-only change would leave orphan cleanup unsafe. An application Job
Object/process redesign is outside this harness task. Select explicit finite
full-suite budgets plus a generated owned64-bit Wine prefix, allowing bounded
server-domain cleanup without affecting a user's/default/unrelated prefix.

This is a scoped lifecycle refactor of the existing fixed reproduction and
existing smoke/full consumers. Preserve all four agent wrapper commands; no
permission/profile expansion, `.opencode` changes or arbitrary command/env input.
Fresh internal helper APIs may be refactored and all repo callers migrated.

## Budgets and execution scope

Full application suite:1800 seconds, kill escalation5 seconds. This is an
evidence-based next bound, not yet a measured guarantee that the suite fits.
Preserve individual120/240-second cases, regression-child bounds, modules,
assertions, filters and Windows skips. Do not add an idle watchdog without need.

Prefix initialization90s, API probe60s, existing help smoke60s, selected-server
stop10s and wait15s, each with5s kill escalation. Fixed outer admission480s and
fast-stage1920s bounds cover setup/shutdown overhead, not additional test time.
Cleanup backstop45s+5s is bounded independently. Do not disable application DLLs
or guess an Xvfb/display change; recorded display conditions already allowed tests.

## Ownership and authorization

Create a fresh private session under `build/wine/sessions/<generated-id>/` before
Wine initialization, with controls outside the mutable prefix directory. Bind
canonical repo/build identities, effective UID, random ID/nonce and session/prefix
device/inode identities. Wine-created registry/drive data is never read or logged.
No prefix pruning/deletion is introduced in this correction.

Pin matching Wine and wineserver executable/version/hash identities; fail if
pairing cannot be established. Internally set only the generated WINEPREFIX,
selected WINESERVER and WINEARCHwin64 for controlled children. Never reset,
shutdown or inspect a caller's HOME/.wine or inherited prefix. Admission and
application use demonstrably the same owned prefix, tools, display and backend.

Before every stop/wait, validate containment, ownership, private modes, nonlinked
roots, nonce/identity and coherent state. Receipt content cannot confer destructive
authority by itself. Refuse substituted, unowned and malformed roots before any
server action. Wine dosdevices links must not be traversed by ownership logic.

Initialization uses the selected Wine's builtin `wineboot.exe --init`. Preparation
admits the API then quiesces that prefix's server while leaving authorization for
one application execution. Application completion/failure terminates authorization
and stops/waits its server. Record launch generations so cleanup is idempotent
only after verified shutdown for the current generation; failed cleanup is retryable.

Use a new receipt schema binding owned session and both tool identities; reject
old default-prefix receipts rather than upgrade them. Prefix contents remain mutable
outside native payload/overlay inventories. Preserve package immutability and
builtin-first/absence-only compatibility admission.

## Cleanup-owning consumers and evidence

Replace configure-only shell consumers with fixed cleanup-owning helper execution
for the existing smoke60 and fast1800 paths. All Make/workflow/test call sites
migrate; remove obsolete `runtime.sh`/configuration APIs without aliases.

Parents retain ownership locks; every Wine/wineserver child excludes lock FDs.
Inherit the outer logger streams and wait for leaders, avoiding an internal
communicate wait on orphan Windows pipe writers. Cleanup occurs before helper
exit; the guarded parent also owns the session early and provides a final backstop
if initialization/admission/helper execution/capture/storage fails or is interrupted.

Handle SIGINT/catchable SIGTERM and exceptions with finite cleanup. Preserve the
primary nonzero/timeout result and separately record cleanup errors. Success plus
cleanup failure is FAIL. Scoped stop/wait must still work after the original
POSIX process group disappears. No global wineserver kill or arbitrary PID action.
Uncatchable SIGKILL cannot guarantee cleanup and is an explicit limitation.

Keep the existing six-stage ledger. Add prefix initialization, launch generations,
budget/tool/session metadata and cleanup subrecords to the appropriate Wine stage.
Use the existing capped evidence mechanism, with no retrospective fabricated EOF
or completeness after forced capture closure. Preserve earlier failure/progress,
including during storage failure. Return truthful bounded failure results.

## Acceptance

Focused host fixtures cover success, init/admission/application failures, timeout,
interruption, cleanup-only failure and retry, plus an escaped-process-group writer
closed by prefix-scoped cleanup and an unrelated-prefix negative control. Prove
lock FDs absent in children while parent locks remain held; substituted roots
stop before server invocation; dosdevices targets are not followed.

After independent review and tooling checks, run one exact guarded reproduction
with the new bound, no source/case/filter weakening. Require actual init/admission/
application prefix parity, recorded1800 launch, bounded stop/wait and full capture.
Either establish complete suite success or diagnose the newly observed boundary.
Native Windows/macOS security acceptance and the historical Linux native SIG
remain independent; a longer successful Wine run cannot close them.
