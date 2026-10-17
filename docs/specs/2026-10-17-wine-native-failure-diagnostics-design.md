# Actionable native failures in Windows validation

## Evidence and scope

The full safe Wine run at `e4185c0` built, packaged, initialized and admitted its
owned prefix successfully. It reached2167 RUN/1779 PASS/387 FAIL, then faulted
at InputDialType's unchecked Lua-to-InputState conversion. Wine's debugger UI
consumed the remaining1800-second limit. Scoped cleanup and full capture worked.
Retained evidence and binary symbolization are recorded under
`.superpowers/sdd/wine-suite-lifecycle/` in `windows-crash-evidence.md` and the
named run logs. This is no longer a compiler or startup diagnosis.

Separately, child-isolated native Linux probes reproduced six SIGSEGVs for
invalid factory arguments and incorrect acceptance of unrelated userdata. The
existing valid binding tests passed4/4. `input-binding-evidence.md` records the
exact commands. This independently justifies an explicit required-argument guard;
the original Wine value and historical Linux reload signal remain unproven.

The387 failures are not387 established independent bugs:63 explicitly report
the native private-security predicate,130 errors are opaque table addresses,
and many later failures fit leaked fixture stubs. Do not repair guessed cascades
or weaken security before the first structured error/mismatch fields are known.

## Bounded direction

Implement required binding validation, then independently reviewed failure-path
diagnostic components (readable errors/metrics, owned roots/crash policy, and
fatal capture). Keep all tests/case budgets and the1800 full budget.
No global sol2 flag, input lifetime redesign, source DACL-policy change, new skip,
application-feature disabling, arbitrary registry access or capability expansion.
Fresh internal helper interfaces may be refactored with all repo callers migrated.

## Required InputState boundary

The exported factory must validate full userdata of InputState type before any
unsafe extraction, extract its pointer only after that check, and reject null
before forming a reference. Invalid values produce a descriptive Lua error,
not a signal or silently accepted adapter. Valid engine.input and adapter behavior
remain unchanged. This does not detect correctly typed stale native objects.

Tests run invalid cases in separate native child processes so old crashes do not
kill the test parent. Each child must complete rejection assertions, print its
case marker and exit0; parent success alone is insufficient. Retain the four
actual valid-engine control tests and native update behavior.

## Noninteractive crash reporting and data isolation

Configure only three fixed values in the generated owned win64 prefix after
wineboot and before admission:64-bit AeDebug Debugger REG_SZ
`winedbg --auto %ld %ld`, Auto REG_SZ1, and HKCU Wine/WineDbg ShowCrashDialog
REG_DWORD0. Verify only these named values through bounded commands. Do not read
registry files/export hives, touch HOME/default prefixes, use Auto0/delete the
debugger value, or confuse WINEDEBUG logging with JIT policy.

This preserves automatic registers/backtrace/detach output while removing UI.
Application status, not debugger exit0, decides success. On an actual root Wine
fatal banner, collect output for one30-second reporting grace, never reset or
extend it beyond the existing application deadline. If the reporter hangs, retain
partial trace and real statuses, then use existing owned cleanup. Ordinary text,
wrong streams/stages, quoted banners and captured expected-child failures must
not trigger teardown. Any observed genuine root fatal prevents PASS, even if
the helper returns0. Do not fabricate application status when unknown.

Give the owned session independent data/cache/tmp roots, also0700 and identity
checked. Apply XDG_DATA_HOME/XDG_CACHE_HOME and host/Windows-compatible temporary
paths consistently. This avoids known shared Linux/Wine test-state roots; it is
not yet proven to explain the security mismatch. Do not clean shared prior data.

## Readable and private first-failure diagnostics

Normalize errors before debug.traceback so structured tables retain scalar code,
message, outcome and current-revision in a fixed bounded representation. Use raw
allowlisted fields, escape controls, visibly truncate at2048 encoded bytes, and
never traverse result payloads, invoke hostile metamethods or replace a failure
with a formatting exception. Apply the same renderer to body/load/teardown/
shutdown diagnostics, preserving public runner behavior and actual failures.

Keep native security checks EXACTLY unchanged. Add literal object role and
non-sensitive owner-match/protection/DACL-match booleans, byte sizes and ACE counts
to the current private-policy rejection. Never dump SID/descriptor/ACL bytes or
record payload. The new metrics are an experiment to identify the failed check,
not a change to which policy is accepted.

## Validation and next observation

Build native changes, then project Fennel compile, constraints and focused
binding/runner tests; run the native publication CTest and complete six-module
Python harness gate. After independent review and commits, run the full standard
Linux suite because native bindings and shared test-runner paths changed.

Then one exact guarded Windows reproduction must establish actual crash policy,
owned roots, first decoded failure, native role/mismatch fields, fatal-report
behavior if encountered, full result and bounded cleanup. Continue only from
that evidence. Wine results do not replace native Windows/macOS acceptance, and
no signal here is assumed identical to the historical Linux reload crash.
