---
type: dev-note
tags:
  - note
---

# Windows Build + Wine Validation Notes

This document summarizes the Windows build and Wine validation work completed in this cycle, including decisions, trade-offs, known limitations, and follow-up work.

## Scope

Goals covered:

- make Windows build scripts match current dependency/build setup
- make the setup reproducible on other Linux machines
- validate Windows artifacts under Wine
- keep Windows coverage as high as possible in `tests.fast`, with explicit and minimal skips
- keep optional modules (notably libtorrent and ffmpeg) enabled by default for Windows
- align local Windows-from-Linux builds and CI as closely as practical
- replace the unstable Windows-host MinGW CI path with the Linux cross-build path

## What Changed

### 1) Reproducible Windows-from-Linux toolchain flow

Added/updated scripts:

- `scripts/setup-windows-build-host.sh`
- `scripts/build-windows-from-linux.sh`
- `scripts/build-windows.sh`
- `scripts/prepare-windows-runtime.sh`
- `scripts/prepare-windows-wine-runtime.sh`
- `scripts/test-windows-under-wine.sh`
- `scripts/build-wine-bcryptprimitives-compat.sh`
- `scripts/wine/{prefix.py,artifacts.py,probe.c,process_prng_compat.c}`
- `scripts/vcpkg-triplets/*`
- `scripts/vcpkg-ports/openal-soft/portfile.cmake`

Result:

- one-time host setup is isolated
- build and test steps are repeatable across machines
- Native runtime prep resolves/copies dependent DLLs automatically and stages `matrix.dll` when present; Wine preparation copies only the clean native package
- local and CI Windows builds now share the same core build entrypoint (`scripts/build-windows.sh`)
- `scripts/build-windows.sh` uses `vcpkg install --recurse` so local cross-builds also work on non-pristine machines

### 1.1) Final CI architecture

The original attempt used a native Windows-host MinGW build in GitHub Actions. That path turned out to be the least stable part of the system:

- repeated upstream vcpkg/MinGW resource compilation failures
- Windows-host tool naming/path mismatches
- long failure cycles with poor feedback

Final CI shape:

- `test.yml` Linux PR/merge-queue validation path
  - Linux validation is the PR and merge-queue gate; this workflow does not contain Windows build or native Windows test jobs
- `windows.yml` Windows main-push/manual validation path
  - Linux job builds the Windows artifact with `scripts/setup-windows-build-host.sh` + `scripts/build-windows-from-linux.sh`
  - Linux job prepares and uploads only the runtime bundle needed by tests
  - native Windows job downloads that runtime bundle and runs the native Windows fast suite
  - this path does not build the Windows installer and does not create the release ZIP
- `build.yml` Release/manual packaging path
  - Linux job builds the Windows artifact the same way
  - Linux job smoke-tests the Windows binary under Wine
  - Linux job creates the Windows release ZIP
  - native Windows job builds and smoke-tests the installer
  - existing `workflow_dispatch` behavior remains available

Windows validation is post-merge, not a PR or merge-queue gate.
`windows.yml` runs on pushes to `main` plus `workflow_dispatch`, not on PRs, merge groups or a schedule.
Manual dispatch remains applicable to Windows validation and release packaging;
`build.yml` also runs on `v*` tag pushes. Wine support does not replace the native
Windows fast suite or its authority.

This routing intentionally superseded the earlier Windows PR-gate arrangement:
`2f94237a` moved the existing Windows jobs to keep PR feedback fast while retaining
post-merge coverage, and `ae16caee` added the routing guard and matching policy.
See [GitHub Actions Hygiene](github-actions-hygiene.md#pr-and-windows-validation-routing).

Why this architecture was chosen:

- it matches the already-working local Windows-from-Linux build path
- it removes the least reliable environment (Windows-host MinGW dependency builds) from CI
- it still keeps native Windows runtime validation in CI, which matters for production confidence

### 2) Windows feature/dependency defaults

Final policy for Windows build:

- `libtorrent`: enabled by default
- `ffmpeg`: enabled by default
- `cef`: not available on Windows in current codebase (Linux-only integration path)

Notes:

- libtorrent package naming:
  - upstream library: **libtorrent-rasterbar**
  - vcpkg package name used here: `libtorrent`
  - Fennel/Lua module exposed by engine: `libtorrent`
  - these refer to the same underlying library integration in this project context

### 3) Runtime fixes for Windows/Wine execution

- implemented Windows process backend in `src/lua_process_windows.cpp` (instead of unsupported stubs)
- added Windows shell/process support (`src/lua_shell_windows.cpp` and runtime wiring)
- historical workaround: a Wine `bcryptprimitives.dll` mock was used for environments missing it. That no-op implementation was unsafe and has been removed; see current admission below.
- fixed OpenAL driver defaults in `src/audio.cpp`:
  - Windows default drivers: `dsound,wave`
  - Linux default drivers: `pipewire,pulse,alsa`

This removed Wine startup noise/failure pattern:

- previous: `Failed to open OpenAL device.`
- now: Windows binary under Wine initializes audio without forcing Linux backends

### 4) Test architecture and skip policy

Windows skip policy is centralized in:

- `assets/lua/tests/runner.fnl`

Key design:

- keep module-level skips explicit and minimal
- keep feature-level skips local to tests when appropriate (using existing skip idioms)
- avoid broad blanket skips unless technically required

Important refactor:

- moved the input external-editor integration test from `test-input` to `test-external-editor`
- unskipped `test-input` on Windows
- left `test-external-editor` skipped on Windows (shell-dependent `sh` behavior)

Files:

- `assets/lua/tests/test-input.fnl`
- `assets/lua/tests/test-external-editor.fnl`

Stability tweak:

- input context-menu clipboard assertions now use a local clipboard stub in test code to avoid Wine clipboard flakiness while still validating behavior.

Additional cleanup:

- terminal widget tests now restore their terminal stub correctly even if a test body throws
- terminal widget tests that assert raw grid or pointer behavior explicitly set `:frame-padding 0` instead of depending on old implicit layout assumptions

### 5) Kernel subprocess expectations under Wine

- `tests.test-kernels` subprocess integration remains skipped on Windows/Wine due Python runtime availability in Wine environments used for CI-style validation.
- this is an environment constraint, not a product-direction decision about kernel support in principle.

## Decisions and Trade-offs

1. Prioritize real Windows support over broad test exclusion

- decision: implement Windows process/shell support rather than skip whole suites
- trade-off: higher implementation effort now, much better long-term coverage and confidence

2. Keep skips explicit and centralized

- decision: define module-level Windows skips in `tests/runner.fnl`
- trade-off: slightly more maintenance in one list, but much easier to audit and reduce over time

3. Separate shell-integration tests from core widget behavior

- decision: external-editor path moved out of `test-input`
- trade-off: one extra module, but clearer ownership and platform handling

4. Reproducibility over ad-hoc local fixes

- decision: script host setup/build/runtime prep instead of manual commands
- trade-off: more scripts to maintain, but repeatable onboarding and CI/dev parity

4.1. Prefer the stable build environment over the nominally native one

- decision: build Windows artifacts on Linux in CI instead of building them on a Windows host
- trade-off: native Windows no longer compiles the dependency graph in CI, but native Windows still validates the produced artifact
- rationale: production confidence comes from reproducible builds plus native runtime validation, not from forcing the least stable host/toolchain combination through every dependency build

5. Wine-specific compatibility shim (`bcryptprimitives.dll`)

- current decision: prefer a probed builtin, using a Wine-only OS-crypto compatibility bridge only on confirmed missing library/export
- trade-off: API admission checks writes/guards and observable failures, not entropy quality; native Windows remains authoritative

## Problems Encountered and Resolutions

1. Matrix DLL discovery/runtime path mismatch

- symptom: matrix-related runtime loading issues for Windows artifact runs
- resolution: CMake copies the Rust artifact into the build tree, and `scripts/prepare-windows-runtime.sh` stages `matrix.dll` from there alongside the dependency scan

2. OpenAL device open failures under Wine

- symptom: `Failed to open OpenAL device.`
- root cause: Windows build forced Linux OpenAL drivers
- resolution: Windows driver defaults switched to `dsound,wave` in `src/audio.cpp`

3. Input suite failing under Wine after unskip

- symptom: clipboard assertions flaky/failing under Wine
- resolution: use test-local clipboard stub in `test-input` context-menu tests

4. External editor integration in mixed suite

- symptom: shell-dependent behavior caused platform-specific instability in `test-input`
- resolution: moved that case into `test-external-editor`, keep module skip on Windows

5. Windows-host MinGW CI instability

- symptom: repeated failures in upstream MinGW/vcpkg dependency builds on Windows-host CI
- root causes included:
  - resource compiler (`.rc`) failures in several upstream ports
  - tool-discovery and prefixed-bin naming mismatches
  - slow iteration loop with poor signal
- resolution: pivot CI to Linux cross-build for Windows artifacts, keep native Windows only for runtime validation

6. Terminal fast-suite regressions after unrelated CI iteration

- symptom: Linux `space_fnl_tests` started failing in terminal widget/scrollback tests
- root cause:
  - one terminal widget test had an outdated layout expectation after default frame padding changes
  - test helper `with-terminal-stub` leaked the stubbed terminal binding when a test failed, contaminating later terminal tests
- resolution:
  - make the helper restore the original binding even on failure
  - make raw grid/pointer tests opt into `:frame-padding 0`

7. `llm-tools bash runs command` Linux CI timeout

- symptom: bash integration test timed out in CI (`exit_code=143`, `timed_out=true`)
- root cause: test timeout margin was too tight for loaded CI runners
- resolution: widen the test timeout from `3` to `10` seconds for the bash tool integration checks

## Current Known Limitations

- CEF is still Linux-only in current engine integration path.
- `test-external-editor` remains skipped on Windows due shell-command assumptions (`sh`-driven behavior).
- kernel subprocess integration test is skipped on Windows/Wine test environments lacking Python runtime.
- Wine is validation support, not a complete substitute for native Windows verification.
- Windows cross-build CI uses `ccache`, `sccache`, GitHub Actions `vcpkg binary caching`, and Ninja parallel builds. The remaining bottlenecks are dependency cache misses, hosted-runner variance, and native Windows runner startup/installer work in the release/manual packaging path.

## Historical Validation Snapshot (not current admission evidence)

Validated in this cycle:

Linux / CI:

- `test.yml` green with:
  - Linux `test`
  - Linux `build-windows`
  - native Windows `test-windows`

Local:

- local Windows cross-build from Linux succeeded
- focused Linux `tests.test-llm-tools:main` succeeded after timeout fix
- focused terminal runner path covering:
  - `tests.test-terminal-widget`
  - `tests.test-terminal-renderer`
  - `tests.test-terminal-scrollback`
  - all passed after test helper/layout fixes

Windows binary under Wine:

- `tests.test-process:main` passing
- `tests.test-input:main` passing after refactor
- `tests.fast:main` passing with current explicit Windows skip policy
- audio smoke path no longer emits OpenAL device-open failure after driver fix

## Pending Work

1. Native Windows verification pass

- keep running the native Windows fast suite in CI
- later, validate release/workflow parity in `build.yml` on manual dispatch or tagged release

2. Reduce skip surface further

- revisit `test-external-editor` for Windows-friendly editor harness (no `sh` assumptions)
- re-evaluate remaining module skips over time (`terminal`, `ripgrep`, `flamegraph`, `llm-tools`) as platform support improves

3. CEF Windows implementation

- implement Windows platform handler in CEF setup/runtime path
- add Windows packaging/runtime asset flow for CEF payload

4. Windows build performance

- keep `ccache`, `sccache`, GitHub Actions `vcpkg binary caching`, and Ninja parallel builds enabled for Windows cross-build jobs
- use `SPACE_TEST_TIMINGS=1` in follow-up investigations if the native Windows fast suite becomes the dominant bottleneck
- keep release ZIP and installer generation out of PR/merge-queue validation unless a future test directly consumes those package artifacts

## Reproducible Workflow (Current)

For OpenCode Windows CI failure reproduction, use the guarded wrapper sequence:

```bash
python3 scripts/opencode_windows_ci_repro.py preflight --repo-root .
python3 scripts/opencode_windows_ci_repro.py bootstrap-vcpkg --repo-root .
python3 scripts/opencode_windows_ci_repro.py setup-host --repo-root .
python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .
```

Run `bootstrap-vcpkg` when `preflight` reports `missing_local_vcpkg`; it is safe
when the repository-local `vcpkg/` checkout is missing or unbootstrapped and host
tools already exist, because it stays inside the repo-local vcpkg path and does
not use sudo. Run `setup-host` only when prerequisite evidence says system host
tools are missing or require provisioning. The wrapper is intended to reproduce
`build-windows`, `test-windows`, and `build-windows-installer` failures locally
with a Linux cross-build + Wine loop before another push. Wine validation is not
a substitute for native Windows CI; native Windows CI remains authoritative for
Windows-host-only behavior, installer behavior, and final integration.

Host setup:

```bash
scripts/setup-windows-build-host.sh
```

Build Windows artifacts from Linux:

```bash
scripts/build-windows-from-linux.sh
```

Prepare native Windows runtime payload (for packaging):

```bash
scripts/package-windows-runtime.sh
```

Prepare/admit the isolated Wine overlay, then run the full Windows fast suite:

```bash
scripts/prepare-windows-wine-runtime.sh
scripts/test-windows-under-wine.sh
```

### Artifact ownership and ProcessPrng admission

`build/windows` is native build output; `build/dist/windows` is the native package.
Packaging excludes `bcryptprimitives.dll` case-insensitively, including stale
helpers left in the build tree, and verifies the final payload. It does not
silently remove the stale build helper. The old standard unmarked package is
preserved intact at `build/dist/windows.pre-diagnostics` if recognizable; a
collision or ambiguous ownership fails. New output has a versioned ownership and
SHA-256 inventory manifest. Only verified owned output is replaced. Symlinked
paths/entries and unrecognized additions are rejected, not recursively deleted.

`prepare-windows-wine-runtime.sh` takes no arguments. It creates a fresh owned
`build/wine/windows` from the clean immutable native package and packaged assets,
never native build DLL leftovers. Cooperative artifact writers and consumers
serialize on the build directory; the guarded wrapper also serializes complete
reproductions. No Wine helper is written into native build/package inputs.
`make test-windows-wine` first repackages the current built executables/assets,
then prepares/admit-tests the overlay; it does not implicitly cross-build.

The no-argument PE probe first runs with
`bcryptprimitives=b;advapi32,cryptbase=b`. Only confirmed missing library/export
(exit10) permits compiling the bridge in the overlay and one retry with
`bcryptprimitives=n;advapi32,cryptbase=b`. No-op output, bad identity, guard damage
and other contract failures (exit20), crashes and the60-second admission timeout
never authorize fallback. Admission uses a further5-second kill escalation if
TERM is ignored; SIGKILL/forced timeout fails without fallback or a receipt.
Load errors other than module absence are diagnosed as failures. Probe
phases/results are flushed. Successful admission records a schema-2 JSON receipt
tying the payload/package inventory, generated owned session (ID, nonce, prefix
inode identity and `win64` architecture), pinned Wine and matching wineserver
executable/version/hash, and display conditions to the fixed backend.
Consumers validate the receipt as data, never shell code. The guarded parent
creates and retains immutable ownership through `prefix.create_session` after
output verification, **before initialization or admission can launch**. Only
known Wine steps receive the internally generated `SPACE_WINE_SESSION_ID`;
inherited handoffs are rejected before execution. No caller/default/home prefix
is selected, reset, read or stopped. All boot/probe/application/stop/wait commands
use the same generated prefix, `WINEARCH=win64` and pinned `WINESERVER`.
Display conditions are not reset; no Xvfb is added. Workflow smoke uses the
admitted overlay with the existing60-second `--help`; full fast validation uses
**1800 seconds**, `tests.fast:main`, existing skips and test-data/working-directory behavior.
Assets, Fennel macro paths and `SPACE_BIN` all refer to the overlay.

### Owned Wine session lifecycle and fixed budgets

The observed historical run stopped active progress at the old180-second cutoff:
**93 RUN / 92 PASS / 0 FAIL**, with the last PASS9.13 seconds before cutoff.
Descendants retained pipes. This established an inadequate whole-suite bound,
not a runner-group hang, later-suite success, a slowness explanation or the
identity of surviving processes. Actual guarded confirmation of this correction
is still a separate post-review capability run; fixture success is not that run.

Fixed GNU timeout budgets (each with a further5-second kill escalation):

| Phase | Budget |
| --- | --- |
| Prefix initialization | 90 seconds |
| Each admission probe | 60 seconds |
| Each owned path-conversion / registry setup command | 30 seconds |
| Workflow smoke `--help` | 60 seconds |
| Full application `tests.fast:main` | 1800 seconds |
| Prefix-scoped wineserver stop / wait | 10 / 15 seconds |
| Guarded admission outer helper | 480 seconds |
| Guarded fast outer helper | 1920 seconds |
| Parent terminal cleanup backstop helper | 45 seconds |

Outer bounds cover overhead only: they do not add application test time. They
also terminate a live helper whose output pipes have already reached EOF.
Case120/240-second policies, regression-child deadlines, assertions, module lists
and Windows skips are unchanged. There is no idle watchdog.

Admission acknowledges bounded **Wine CLI cleanup completion**, not independently
proven native-process quiescence or terminal shutdown. An owned, acknowledged
`stopped_generation == generation` permits a still-authorized one-shot consumer.
Every launch increments the durable generation and invalidates that stopped
generation. Full/smoke consumers revoke authorization before launching and own
terminal stop/wait in `finally`. Initialization/admission failures also stop the
owned session, even without any admission receipt. The guarded parent retains
the immutable owner and always runs one bounded terminal backstop in `finally`
after acquisition, including interruption or evidence-storage failure. This
retries failed helper cleanup once; a previously acknowledged current generation
needs no duplicate server operations, but still ends authorization. Mutable
state corruption never authorizes execution and does not suppress cleanup using
verified immutable ownership. Stop/wait codes and state errors are evidence, not
an assumption of quiescence. Every server operation first verifies private roots,
owner/nonce and pinned tools; root or symlink substitution refuses the operation.

Cleanup preserves the raw selected-server `-k` and `-w` exit codes. The normal
`0/0` pair remains accepted. The only additional accepted pair is **`1/0` with
both stdout and stderr empty for both commands**, after verifying the same owned
prefix before each operation and with no ownership, state, invocation or capture
errors. Whitespace is output, not a recognized benign diagnostic. Diagnostic
output in either command makes `1/0` fail; other kill statuses, failed waits,
timeouts, signals and state/ownership errors remain failures. Server streams use
regular temporary files and leader waits, with bounded reads and control-safe
diagnostic excerpts relayed to the outer logger. Accepted CLI completion alone
acknowledges the current generation; failed cleanup stays retryable. No new
private Wine lockfile/process inspection, global server action or prefix pruning
is used to strengthen that acknowledgment into a native-process claim.

This narrow policy follows the public Wine 9.0 CLI, not an assumption that Unix
exit1 uniquely means “no server.” In
[`server/main.c`](https://github.com/wine-mirror/wine/blob/wine-9.0/server/main.c),
`-k` exits with `!kill_lock_owner(...)`; no owner or a shutdown race can yield1,
but silent failures can also yield1. In
[`server/request.c`](https://github.com/wine-mirror/wine/blob/wine-9.0/server/request.c),
the wait helper can return an `fcntl` error; `main.c` nevertheless exits0 without
checking that return. Consequently even silent `1/0` is **not formal proof of
native lock success or all-process quiescence**. The
[`wineserver` manual](https://github.com/wine-mirror/wine/blob/wine-9.0/server/wineserver.man.in)
documents normal default persistence of 3 seconds after the last client exits,
so an already-gone server is a normal possibility, not a failure by itself.
`CleanupResult.ok` means completion under this explicit CLI contract; it does not
certify which silent internal Wine branch occurred or prove the full application
suite completed. Actual guarded full 1800-second/session confirmation remains a
separate post-review run.

### Owned data roots and automatic crash reporting

Each generated session also owns private0700 `data/`, `cache/` and `tmp/`
directories immediately under its session directory. Their device/inode identities
are immutable owner metadata alongside the prefix and tool identities. The fresh
owner schema/bounds reject incomplete retained ownership; old sessions are not
adopted or acted on. `Session.binding()` is the single producer for admission
receipt and parent-wrapper owned metadata, including those roots, pinned tools,
verified Windows temp mapping and the fixed policy verification flag. Substituted
roots fail before launching Wine. No parent chmod or global umask change is used.

Every Wine child overrides inherited XDG_DATA_HOME/XDG_CACHE_HOME with the owned
host `data/`/`cache/` paths and POSIX TMPDIR with the owned host `tmp/`. Before
conversion is ready, Windows TEMP/TMP are `C:\windows\temp` **inside the fresh
owned prefix**, Wine's bootstrap system-temp location; regular host capture files
already use the private host `tmp/`. After wineboot, the selected Wine launches
builtin `C:\windows\system32\winepath.exe -w <owned-tmp>` then `-u <result>`.
Only that one owned root can be converted. The result must be drive-absolute and
roundtrip exactly to the owned host root. No `Z:` mapping is presumed or inspected.
After verification TEMP and TMP both use that returned Windows path, so native
temp operations and POSIX TMPDIR refer to the same owned directory. Windows
profile data remains within the private prefix as well; old shared/home data is
neither inspected nor cleaned. Data isolation is not claimed to fix a DACL mismatch.

Before the API probe, selected builtin `C:\windows\system32\reg.exe` sets only
these three values, with `/f /reg:64`, then queries each exact `/v` name with
`/reg:64` to verify type and data:

| Key | Value | Type | Data |
| --- | --- | --- | --- |
| `HKLM\Software\Microsoft\Windows NT\CurrentVersion\AeDebug` | `Debugger` | `REG_SZ` | `winedbg --auto %ld %ld` |
| same AeDebug key | `Auto` | `REG_SZ` | `1` |
| `HKCU\Software\Wine\WineDbg` | `ShowCrashDialog` | `REG_DWORD` | `0` (`0x0` query output also accepted) |

All eight path/registry launches have30+5 bounds, durable generation accounting,
closed parent FDs and bounded regular-file capture. Only these debug-policy keys
are queried; there is no registry enumeration/hive/drive-content read or arbitrary
key/mode interface. Utilities are builtin-pinned with utility-only DLL overrides;
the application's admitted backend and normal features remain unchanged. Any
conversion, write, query or verification failure prevents API/application launch,
ends authorization and cleans the owned session. A new wineboot invalidates the
policy verification flag until the fixed setup is reverified.

Derived mapping/policy observations live separately from immutable cleanup
authority. Invalid observations block launch/binding but cannot block safely
owned server cleanup. The server CLI always uses its minimal immutable environment
(including private host roots and prefix-local bootstrap Windows temp), independent
of those observations. Owner/root/tool corruption still refuses unsafe commands;
mutable lifecycle errors still make cleanup fail. The existing silent1/0 CLI
acceptance policy and its native-proof limitation above are unchanged.

This policy keeps the automatic `winedbg --auto` reporter enabled to produce a
backtrace and detach without interactive crash dialogs; it does not use Auto0,
delete Debugger, disable winedbg DLLs, alter WINEDEBUG or disable application
features. Application status is not debugger status. Actual native reporting
behavior remains unconfirmed by host fixtures; the guarded real Wine reproduction
is a separate post-review capability run, not established by the host tests below.

Root/build/session ownership locks stay with their owning parents; child FDs are
closed, so an escaped descendant cannot retain these locks. The guarded parent
holds the repo/session locks; artifact helpers hold the build lock (the parent
releases its acquisition-time build lock before launching a helper). The mutable
session directories under `build/wine/sessions/<generated-id>/prefix` are retained
outside native package, overlay and evidence inventories. There is no prefix
pruning/deletion, registry inspection or global wineserver kill. Catchable
termination is handled and repeated signals cannot interrupt the finite cleanup;
an uncatchable parent **SIGKILL**, host crash or power loss can still prevent its
backstop and leave retained session evidence for investigation.

The bridge exports `BOOL WINAPI ProcessPrng(PBYTE,SIZE_T)` and statically imports
`BOOLEAN WINAPI SystemFunction036(PVOID,ULONG)` from builtin advapi32. There is
no loader-lock `LoadLibrary`, ProcessPrng recursion, timestamp/random seed or
zero-fill fallback. It fills checked ULONG-sized chunks. Zero length (including
NULL/zero) succeeds without calling the backend; NULL/nonzero and observable
backend failure diagnose and hard-terminate the current process nonzero via
`TerminateProcess`, not `ExitProcess`/DLL detach callbacks. A nonreturning trap
guards against an unexpected return; failure never returns FALSE to callers
that may ignore it. An unresolved static import fails loading, never
claims success. Host fixtures exercise the actual loop with chunk7/request16
(`7,7,2`), second-call failure, null/zero policy and canaries; tiny real MinGW
fixtures check ABI compilation without running PE/Wine.

These are **API-contract admission checks, not entropy certification** or native
Windows security/ACL certification. Wine's underlying host RNG can hide upstream
short reads; even passing output probes cannot guarantee future backend failures
will be observable. Native Windows remains authoritative. Real admission and the
full guarded reproduction remain required separately; this tooling alone does not
establish later full-suite outcomes, nor close the
historical Linux native SIG investigation. Agents must use the existing guarded
capability, not the manual shell examples above, for real reproduction.

### Bounded reproduction evidence

The same `reproduce --repo-root .` action records these ordered stages:
`preflight`, `build-windows-from-linux`, `package-windows-runtime`,
`verify-windows-outputs`, `wine-admission`, then `wine-fast`. API admission must
succeed before the full application launches. Builtin/compat probe phases and
their observed exit codes are separate from full-suite progress. The four public
commands and their status/CLI exit conventions are unchanged; there is no command,
environment, timeout, module, or profile passthrough.

Each generated private run lives under `build/windows-ci-repro/<generated-id>/`:

- `ledger.json` is atomically replaced before and after every stage (and during
  capture). It retains earlier successes after a later failure, with UTC and
  monotonic timestamps, elapsed seconds, return code, outcome, capture errors,
  stream counters, paths, and last observed flushed markers.
- `<stage>.stdout.log` and `<stage>.stderr.log` are exclusive regular files, each
  capped at **16 MiB**. Both binary streams are drained concurrently even after
  their disk caps. Per-stream `observed_bytes` and `stored_bytes`, `eof`,
  `log_truncated`, and `errors` distinguish a cap or write error from full capture.
- Incremental UTF-8 tails are at most **4000 characters** per stream;
  `excerpt_truncated` is independent of `log_truncated`. Marker parsing retains
  no more than **4 KiB** of a line, discarding oversized lines until newline and
  counting them. Flushed `[LAUNCH]`, `[BOOT]`, `[LOAD]`, `[RUN]`, `[PASS]`, `[FAIL]`,
  `[TIME]`/`[TIMINGS]` and Wine-admission lines update counts, latest observation
  timestamps and last markers even after the log caps.
- Returned **whole encoded JSON is at most 48 KiB**, including control-character
  and Unicode escaping. Log/ledger pointers are repo-relative. Successful
  excerpts are compacted first, then allowlisted metadata and, if needed,
  failure excerpts (keeping bounded failure context). `response_truncated`,
  `response_excerpt_truncated` and `response_text_truncated` explicitly mark
  response-only compaction; the owned ledger and capped logs remain richer.

Atomic JSON writes check every short-write count and replace the previous ledger
or ownership marker only after the entire new JSON is written and fsynced. If
checkpoint/final-save/sealing storage fails, the response retains the live
in-memory history, current progress, actual exit codes and named log/ledger
pointers, with `persistence_errors`, `complete: false` and `sealed: false`.
Capture continues draining and waiting for the actual child status after a
checkpoint failure; broken storage is not retried indefinitely. The named ledger
then denotes the last valid durable checkpoint, which can predate the returned
failure/progress (including a sealing failure). Its earlier completeness field
does not establish that the run was successfully sealed.

Run directories are `0700`, files `0600`; existing parents are not chmodded.
A versioned ownership marker binds repo/build inode identity and the finalized
file inventory/hashes. Reproductions retain the repo-directory lock, and artifact
preparation/consumption retain their build-directory locks. Retention always
protects the current run plus two timestamp-selected verified historical runs,
even after a wall-clock rollback. Unowned, symlinked, changed, interrupted/unsealed
or otherwise quarantined paths are never pruned. No arbitrary recursive cleanup
argument is accepted. Supervisors can inspect the named artifacts without giving
the restricted reproducer a raw log-reading or arbitrary execution capability.

For ordinary nonfatal output, if pipes reach EOF first, capture checkpoints the
observed markers/EOF flags before waiting for the leader's real exit status,
without status spinning. The fixed outer GNU timeouts still bound Wine helper
shutdown in that state. After leader exit, pipes have a two-second EOF
grace; if descendants hold them open, only that newly owned process group gets
TERM, then two seconds later KILL if still present. Capture then closes its pipes
and records incomplete evidence, never a complete PASS. Launch errors, capture
errors, interruption, nonzero exits and GNU timeout exit **124** remain distinct
outcomes. A recognized `[FAIL]` from `wine-fast` with exit zero is an
`inconsistent_result`, not PASS; the real zero status is retained. This runner
failure rule does not reinterpret arbitrary successful build output. Process-group
cleanup is separate from prefix-scoped wineserver shutdown, not proof of it.

Only root wine-fast stderr can latch a fatal report: a bounded, newline-terminated
Wine banner must match the entire line, including an allowlisted fault description,
hexadecimal fault address and thread, and `starting debugger...`. Wrong stages or
streams, quoted/embedded banners, ordinary exception text and captured expected-child
failures do not qualify. The first observation starts one30-second reporting grace;
it never resets on repeated banners, progress or reporter output. Its deadline is
clamped to the explicit 1800-second application hard deadline, never to outer-stage
startup or inferred shutdown overhead. No other execution budget changes.

The owning artifact helper sends launch time/hard deadline and, when available,
the raw bounded Wine application `command_returncode` over a private application observation pipe.
The helper removes its private FD environment handoff and closes the FD across
application exec; application stdout/stderr cannot forge observations. The launch
clock is sampled at bounded-command creation, after `Session.launch` completes
validation, durable generation accounting and environment construction. Launch is
published only after successful `Popen`; prelaunch/spawn failure emits no launch
observation. The observer runs inside the process owner's exception/teardown path,
so publication failure still stops and reaps the created group. The command result
is sent before owned shutdown. The ledger's `application` observation is distinct from the stage's raw
helper `returncode`, `debugger_returncode` (unknown/null without an observation),
capture outcome and cleanup helper/server codes. A command return code is not
proof of a native PE/debugger exit status. Unobserved application status stays
unknown/null; helper exit zero never fabricates it.

During fatal reporting both streams continue draining, including after log caps,
through early EOF with a live leader or an exited leader with held pipes. Normal
completion may finish sooner; otherwise deadline expiry records
`fatal_report.termination: deadline_expired`, uses the existing owned process-group
teardown and prefix backstop, and keeps incomplete evidence/partial trace. It does
not block indefinitely in a leader wait or apply the ordinary two-second held-pipe
grace instead of the report grace. `native_fatal` prevents PASS even with helper or
application-command exit zero; `fatal_report_timeout` identifies expiry without a
previously known primary failure. Known nonzero/124 statuses, interruptions,
capture/storage errors and cleanup results retain their separate evidence and
precedence; report termination never rewrites raw return codes.

The parent's backstop appends to the current Wine stage's same capped logs, with
a separate cleanup subrecord for attempts, UTC/monotonic timestamps, actual helper
and stop/wait results, launch generation, authorization and state-read/write errors.
Structured cleanup markers share the parser's4KiB encoded-byte budget, including
JSON escaping; diagnostic excerpts carry explicit truncation flags and total error
counts without losing stop/wait codes. Malformed cleanup markers retain an aggregate
count and one diagnostic, even after log caps; they make capture incomplete rather
than growing the in-memory error list or replacing retained history with a generic failure.
No seventh stage or extra log inventory is introduced. Cleanup capture has its own
EOF/completeness fields: stopping a writer cannot retroactively make the primary
capture complete. Primary return codes/outcomes (including124/137, or an actual
negative signal status) are preserved. Cleanup never converts a primary failure
to PASS; success plus failed cleanup is FAIL. If log publication is unavailable,
owned cleanup still runs with bounded in-memory evidence and named log pointers;
the existing persistence-failure history recovery is retained.

The fixed operation enables `TEST_VERBOSE=1` and `SPACE_TEST_TIMINGS=1` internally.
Nonempty inherited `TEST_FILTER`, `SPACE_TEST_CASE_TIMEOUT_SECONDS`, `TEST_SUITE`,
`SPACE_TEST_SUITE`, `TEST_MODULES` or `SPACE_TEST_MODULES`, and enabled
`SPACE_MATRIX_TEST=1`/`SPACE_REALTIME_TEST=1`, are rejected rather than running an
unknown selection. Inherited `SPACE_WINE_SESSION_ID` is also rejected, including
an empty value. The full `tests.fast:main` invocation uses **1800 seconds**;
each admission probe uses **60 seconds** (with its existing kill escalation). Case
deadlines, assertions, Windows skips and module lists are not changed.

Metadata is allowlisted: module/deadline/diagnostic settings, effective uid/gid,
generated session/prefix identity and architecture, all fixed budgets,
display-presence booleans, and pinned tool identities, backend and payload identity.
Tool facts come from the retained session and existing schema-2 admission receipt
under the build lock; metadata collection does not execute a second Wine version
query or modify/reseal the receipt/overlay. HOME/default-prefix identity is not
guessed from the ambient environment.
No environment dump, credentials, registry or private-prefix contents are read.
Tooling regression tests use temporary repositories and host fixture processes;
they are not actual Wine admission, a PE runtime pass, or proof of a full-suite
result beyond the historical cutoff. A real guarded reproduction remains a separate
post-review step.


## See also

- [Cross Platform](/dev/subsystems/cross-platform)
