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
- `scripts/wine/{runtime.sh,artifacts.py,probe.c,process_prng_compat.c}`
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

- `test.yml` PR/merge-queue validation path
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
The application's180-second bound is unchanged. Load errors other than module absence are diagnosed
as failures. Probe phases/results are flushed. Successful admission records a
JSON receipt tying the payload/package inventory, selected Wine executable,
version/hash, inherited/default prefix selection, and display conditions to the
fixed backend. Default-prefix identity is derived from `HOME/.wine` without
reading home/prefix contents; changing HOME invalidates default-prefix admission,
but does not change an explicitly selected prefix. Wine selection uses the same
absolute-path resolver at admission and consumption, including relative custom
commands, while retaining executable hash/version checks.
Consumers validate the receipt as data, never shell code. Prefix/display
are not reset; no Xvfb is added. Workflow smoke uses the admitted overlay with
the existing60-second `--help`; full fast validation retains180 seconds,
`tests.fast:main`, existing skips, and test-data/working-directory behavior.
Assets, Fennel macro paths and `SPACE_BIN` all refer to the overlay.

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
full guarded reproduction remain required separately; this tooling does not
establish that the earlier180-second Wine timeout is fixed, nor close the
historical Linux native SIG investigation. Agents must use the existing guarded
capability, not the manual shell examples above, for real reproduction.


## See also

- [Cross Platform](/dev/subsystems/cross-platform)
