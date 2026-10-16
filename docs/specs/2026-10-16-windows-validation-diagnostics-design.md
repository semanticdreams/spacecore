# Trustworthy Windows cross-build diagnosis

## Goal and evidence

The user requested diagnosis and a clean solution for failing cross-build
validation. Current evidence distinguishes stages: compilation and packaging
return success; the full Wine invocation exits124 at its existing180-second
deadline. Startup, active slow tests, native-call blockage and shutdown cannot
yet be distinguished. Linux fast-suite duration is not proof of Wine's cause.

Source inspection and actual local PE inspection independently confirm two
defects: the reproduction wrapper discards successful output/full failing logs,
and a Wine-only no-op ProcessPrng DLL can contaminate native packages on repeat
runs. Both local build and packaged DLLs export a function that returns1 without
writing output. No such artifact was published. The detailed evidence is in
`.superpowers/sdd/windows-validation/evidence.md`.

This is a local build/validation correction, not a new graph feature, native
Windows security certification, or closure of the historical Linux native SIG.
Fresh internal script interfaces may be refactored; migrate all repo callers
and tests, with no obsolete aliases.

## Alternatives and direction

Merely raising180 could conceal a hang. Logging alone would diagnose an
untrustworthy runtime because the RNG shim violates its API. Select bounded
artifact isolation and valid API admission first, then complete stage evidence,
then one guarded full reproduction to establish the failing phase.

Do not introduce a general execution framework, arbitrary command/environment
passthrough, or permission workaround. Keep the existing four guarded wrapper
commands. No `.opencode/**` changes or new execution profiles are needed for
this first diagnostic cycle. Focused/native-C++ profile support is a later
evidence-driven change if necessary, not implied permission to bypass the agent.

## Artifact ownership and Wine admission

- Native build output and native distribution must never receive Wine-only
  compatibility files. Exclude the known system-name helper case-insensitively
  from packaging even if stale build output contains it. Verify final artifacts.
- Create a fresh, script-owned Wine overlay from the clean packaged payload at
  a distinct repo-local location. Do not inject DLLs into build/windows or dist.
  Wine tests use overlay executables and overlay-packaged assets consistently.
- Reject unsafe output paths/symlink traversal; replace or prune only positively
  identified script-owned outputs. Preserve unrelated files and old evidence;
  never recursively remove an arbitrary argument or unowned directory.
- Remove the no-op mock rather than preserve it as a fallback. If a compatibility
  bridge is required, export the correct ProcessPrng ABI and fill every requested
  byte using Wine's existing OS-crypto path. Use the documented advapi32
  SystemFunction036/RtlGenRandom ABI with checked ULONG-sized chunks and no
  timestamp, rand(), deterministic or zero-fill substitute. Do not recurse through
  ProcessPrng. Constrain the Wine backend selection to the intended built-ins.
- If the bridge cannot resolve the backend or the backend reports failure,
  terminate the validation process with a diagnostic/nonzero status; never return
  fabricated success. Bound zero/null/length behavior explicitly in bridge tests.
- Run a small PE API probe using the same runtime/prefix/overrides before app
  tests: verify export/module identity, output writes across full/odd-sized
  buffers, canaries and zero-length behavior. Deterministic backend fixtures
  exercise chunking and failure paths without multi-gigabyte allocations.
  Reject missing/no-op/stuck output, crashes, failure or timeout.
- These probes are API-contract admission checks, not entropy certification.
  Wine backend implementation limitations remain documented; native Windows is
  authoritative. Never infer native ACL correctness from a Wine probe.

Migrate all callers of the old mock/preparation script, including workflow smoke
steps, so none can reintroduce build/package contamination. Do not keep a legacy
script alias. The native package is immutable input to Wine preparation.

## Evidence within the existing operation

Retain the fixed preflight → cross-build → package → verify → Wine operation.
Keep tests.fast:main and its180-second whole invocation deadline for the first
instrumented run. Enable existing flushed TEST_VERBOSE and SPACE_TEST_TIMINGS
internally. Do not change test assertions, case deadlines, skips or selection.

The Windows wrapper owns streaming capture for reproduction, leaving the shared
capability command runner unchanged. Store stdout/stderr for success and failure
under generated private repo-local run directories; use fixed stage filenames.
Cap each stream at16MiB while continuing to drain, bound returned excerpts and
report every truncation/incompleteness explicitly. Retain at most three owned
runs; never prune an unowned/symlinked artifact directory.

Persist the ordered ledger before and after each stage, including outcome,
numeric status, elapsed time, paths, excerpt/truncation status, and last flushed
launch/load/test/timing markers. Distinguish launch error, nonzero exit, timeout
and interrupted/incomplete run. Successful stages remain visible after failure.
The restricted operator receives sufficient bounded JSON evidence without raw
log-reading permission; supervisor/explorer can inspect the named repo artifacts.

Record only allowlisted non-secret launch facts: selected Wine executable/version,
payload identity, selected module/deadline, inherited/default prefix selection,
display presence and explicit diagnostic settings. Do not dump environment,
credentials, registry contents or private Wine-prefix files. Preserve initial
prefix/display conditions for the diagnostic run; do not reset Wine or add Xvfb
without evidence that these are the fault boundary.

## Validation and completion of this diagnostic cycle

Use regression fixtures for repeat-run contamination, mixed-case helpers, real
compatibility source/probe behavior, immutable package/owned overlay, symlink and
unrelated-file safety, bounded capture, retained successful stages, actual
truncation, timeout propagation, and last-marker reporting. Shell syntax and
focused Python tests cover the changed tooling; no unrelated full Linux suite
is required at every checkpoint.

After implementation and independent review, run one exact guarded reproduction.
The compatibility probe must pass before app tests count as usable evidence.
Inspect the resulting stage ledger and full retained logs to identify startup,
test progress, a specific failing test/native call, or shutdown. A repeated124 is
still failure/incomplete evidence—not success. Any runtime fix or new profile
then follows systematic diagnosis, bounded planning, implementation and review.
Do not declare the underlying Wine timeout fixed merely because diagnostics work.
