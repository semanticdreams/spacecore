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

### 3.1) Optional native Terminal startup boundary (portability source checkpoint)

The Windows build intentionally has no VTERM backend. The runtime registers the
native `terminal` preloader only when that backend is available. Main therefore
requires/registers the Terminal sidebar widget only when
`(rawget package.preload "terminal")` is not nil. This is an availability check,
not an OS branch or a broad protected-require fallback: a registered throwing
loader still propagates its error, and an unusable registered module still fails
when its panel is built. A cached widget/native module does not substitute for
native registration when the preloader is genuinely absent.

Only Terminal is optional at this boundary. Sidebar creation, Space Agent
registration, pending sidebar-state restoration, startup providers and ownership
remain unchanged. Host startup regressions isolate/restore native preload and
loaded native/widget caches on success and failure, including a cached widget.
This unfinished source checkpoint does not establish a repaired actual Wine
full-suite run; independent review/exact commit and the supervisor's combined
guarded runtime validation remain pending. No test deadline or skip policy changes.

### 3.2) Fixed canonical runtime documentation resource

The Windows native package carries the single required
`docs/dev/features/entity-type-catalog.md` page at the same relative path as the
checkout, beside `assets/`. The existing graph-extension test resolves it through
`SPACE_ASSETS_PATH/../docs/dev/features/entity-type-catalog.md` and still extracts
the executable example from that one canonical document; no example copy, cwd
fallback or Fennel skip is introduced.

The private `REQUIRED_RESOURCES` tuple owns this fixed list, not the whole docs
tree. Packaging validates the canonical safe regular source, protects `ROOT/docs`
from output overlap, and copies the page **before** sealing the native inventory.
The overlay inherits that verified package; existing recursive inventories and
the unchanged admission receipt bind its exact bytes. Native verification and
admitted overlay configuration independently compare required resources with the
canonical source, so missing or tampered resources refuse launch even after
resealing inventories/receipts. Owned-session cleanup remains independent of
documentation and receipt availability. Host fixture/source checks are not proof
of a repaired actual Wine run; combined guarded runtime validation remains pending.

### 3.3) Workflow default-store lexical cache ownership

`WorkflowStore.get-default` resolves the explicit/appdirs request, requires that
data, and applies the existing `fs.absolute` before comparing it with the cached
owner and passing it to the constructor. Direct construction retains its existing
normalization boundary. Equivalent request spellings share the store, cached
definitions and subscriptions only when their `fs.absolute` results are exactly
equal; truly different roots retain separate owners and output files.

This is existing lexical normalization, not a new trailing-separator, symlink,
case-folding or filesystem-identity policy. A terminal `/.` may keep a separator
under C++ `lexically_normal` and is not promised equivalent. Tests use raw,
absolute and `fs.relative(root)` witnesses with an explicit equal-result premise.
The two original default-root cases now compare against canonical expectations
while retaining disk and different-root checks. The source cache mismatch and
uncanonical test expectations are distinct observations, not proof that the cache
bug explains both actual Wine failures; combined guarded runtime proof is pending.

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
identity of surviving processes. The two actual post-diagnostic guarded runs
recorded below subsequently ended before the unchanged1800-second bound; neither
was a passing full suite. Fixture success alone is not actual-run evidence.

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
suite completed. The actual post-diagnostic runs below acknowledge generation11
with stop/wait0/0; that is CLI cleanup evidence, not native-process proof or a
passing full suite.

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
host `data/`/`cache/` paths and POSIX TMPDIR with the owned host `tmp/`. TEMP/TMP
launch inputs use `C:\windows\temp` **inside the fresh owned prefix** until
conversion is ready; regular host capture files already use the private host
`tmp/`. Wine9 may skip Unix TEMP/TMP imports and reapply registry environment, so
those inputs alone do not establish effective Windows process temp. After wineboot,
the selected Wine launches
builtin `C:\windows\system32\winepath.exe -w <owned-tmp>` then `-u <result>`.
Only that one owned root can be converted. The result must be drive-absolute and
roundtrip exactly to the owned host root. No `Z:` mapping is presumed or inspected.
After verification, protected private `SPACE_WINE_WINDOWS_TMP` carries that exact
Windows path; before mapping it carries the bootstrap path. Inherited and extra
launch overrides cannot replace it. At entry the admission probe requires the
generic `wine_owned_environment.h` initializer: validate bounded drive-absolute,
traversal-free UTF-16, set TEMP then TMP, and read back both exactly after both
sets, before publication/crypto DLL loading or report use. Missing required,
empty/malformed/truncated, API or readback failures are fatal contract20 with only
fixed-phase numeric diagnostics. Optional absence is a no-op only for a genuinely
absent handoff; it establishes no owned-root claim. Server cleanup uses immutable
bootstrap data without reading derived setup, including when setup is damaged.

The parent exclusively allocates the fixed identity report in its owned host tmp
with mode0600, nofollow and CLOEXEC, checking a current-UID, regular, single-linked,
zero-length object. It retains the noninherited native descriptor through probe
execution and all host validation. After process-local temp initialization the
Windows child uses OPEN_EXISTING, checked WriteFile/CloseHandle, and no creation or
truncation. Acceptance requires the path/read result and retained descriptor to
match the original device/inode/mode/UID/link identity plus the unchanged bounded
JSON/challenge/pair/SO proof. Legitimate writes may change size and timestamps,
not that origin. Substitution or failed close proof cannot authorize0 or10; close
errors are explicit and do not mask an already failed child or primary exception.
Preexisting paths are never adopted/repaired/removed. Only a fully verified10
permits existing verified removal and a fresh exclusive sink for the next probe;
failed empty/partial reports can remain as evidence without admission.

Application/test entry-point initialization remains future Tasks6/7 work: neither
launch inputs nor probe initialization proves universal application startup.
Actual Wine runtime correction remains unproved until the guarded experiment
after source review/commit; host adapters and tiny PE compilation are not that
proof. The prior missing report's effective Windows location was not observed and
is not recovered by browsing prefix contents. Windows profile data remains within
the private prefix; old shared/home data is neither inspected nor cleaned. Data
isolation is not claimed to fix a DACL mismatch.

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
features. Application status is not debugger status. The actual post-diagnostic
runs below verified the fixed crash policy, but neither observed a root native
fatal. Actual reporter/grace behavior therefore remains unexercised, not verified
fixed by either those runs or the host fixtures.

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
will be observable. Native Windows remains authoritative. The actual runs below
passed admission but failed the full guarded reproduction; this tooling alone does
not establish later full-suite success, nor close the
historical Linux native SIG investigation. Agents must use the existing guarded
capability, not the manual shell examples above, for real reproduction.

### Private publication operation ABI (source/host-model admission stage)

The shared private header now defines the first operation frame: ABI1, **168 bytes**,
with separate caller-owned primary, cleanup and transport byte buffers. Identity
remains ABI1/112 bytes. There is no 144-byte compatibility frame. Protocol NTSTATUS
is separate from operation failure: `SRP_SUCCESS` can carry a primary or cleanup
error, including a **present empty** error. `primary_state` and `CLEANUP_PRESENT`
encode presence independently of byte counts. Buffers report complete required
byte lengths and separate truncation flags; they never imply a NUL terminator.

The native-only `record_publication_unix.h` entry owns opaque, nonrecycled context
IDs and delegates all filesystem/security work to the unchanged phased Operation.
BEGIN copies/constructs only (START/sequence0), without preparing a workspace.
ADVANCE/CANCEL/RELEASE consume only an exact event/sequence; SNAPSHOT ignores stale
event/sequence inputs and retrieves sticky state without allocation or native work.
Release finalizes cleanup only, returns the final snapshot before retiring the ID,
and does not invent cancellation errors for BEFORE_CLEANUP/DONE. Native DONE with
cleanup errors is completed finalization: return its error-bearing snapshot and
retire normally, not a false clean result. Unexpected contained live exceptions
instead poison publication, retain a bounded diagnostic and recoverable ownership
until finalization completes, and never clear committed truth. Shared registry
ownership and per-context serialization prevent stale release from erasing newer
work. Pointer spans must be caller-owned valid synchronous storage; integer ranges
and incompatible overlap are checked, not arbitrary hostile addresses probed.

This adapter is **excluded from the engine source glob on every platform**. The
fixed Unix SO builder now links the Unix entry, native adapter and existing phased
publisher core with threading and dl linkage; native ABI tests and host recovery
models use that same real adapter/core. Slot1 forwards `srp_unix_call`; it is not
a PE-callable imported host symbol. Required and reported pair features now change
together to identity|operation3, refusing old identity-only and extra flags.

The existing60-second probe validates entry0 first, then makes a fresh zeroed
168-byte BEGIN with context0/sequence0/START/CONTINUE, empty inputs, zero primary/
cleanup capacities and a4096-byte transport buffer, before report writing/Crypto.
The PE authority guard must allow the ordinary process before native validation.
The probe requires INVALID_ARGUMENT, flags0/no context or sequence/event progress,
primary ABSENT, zero primary/cleanup required counts and complete nonempty bounded
transport text. Native empty-path refusal precedes any filesystem work or context
creation. Unsupported, access denied, success or unexpected outputs are contract20
without Crypto or fallback. Only fixed phase/raw status is logged, not diagnostics
or payload data. Identity remains112 bytes and report/receipt schemas, temp/report
origin proof, discovery/IDs/SO checks, generations and all deadlines are unchanged.

This is benign routing/default-authority API evidence, not a real publication,
filtering-history or token-security proof. Actual matched SDK pair execution and
entry0/entry1 dispatch under Wine remain guarded supervisor work after source
review/checkpoint. The Task6 C++ production client is not activated here; the old
strict Windows publisher failure is not resolved or represented as a full-run PASS.

#### Inactive synchronous publication driver (Task6A host validation)

`src/record_publication_wine_driver.h` provides the private platform-neutral
`record_publication::wine::detail::drive(Entry&&, host_path_bytes, payload, hooks,
AuthorityCheck&&) -> Result` template. Entry is the synchronous
`int32_t(uint32_t, void*)` callable; authority returns a `uint32_t` error (zero
allows). The eventual caller owns the validated binding/module lifetime. Paths
are counted **raw host bytes**, not PE filesystem paths; binary and empty payloads
are copied by the existing native adapter/core. No Windows loader, binding
producer, public dispatch, native policy or ABI is changed or activated here.

Each call uses a fresh zeroed frame and separate primary, cleanup and transport
channels, initially4096 bytes each. Each channel may grow once, bounded at65536
bytes, with **SNAPSHOT only** refilling it. Diagnostics use byte counts, not NUL
termination. Empty error presence is retained, and capacity/producer truncation is
explicit. A no-context BEGIN error and an already-retiring RELEASE cannot be
replayed to obtain more text. NTSTATUS is never mistaken for native success.
Precommit native primary errors throw `runtime_error` with the native publication
context; known commit returns `Result{true, ...}` with any cleanup/transport
lifecycle diagnostics instead of a false not-committed result.

BEGIN captures START/sequence0 without workspace preparation or a hook. The four
hooks execute once, in caller context and native order, with no driver lock held.
Authority is checked before BEGIN, before publication continuations and after
publication hooks. Publication hook failure or authority loss at START through
BEFORE_COMMIT uses CANCEL, never a failed publication ADVANCE that the PE guard
would deny. BEFORE_CLEANUP may send a failed ADVANCE, including a present empty
error. Cancellation/poison never resumes publication, even if authority returns.

The driver saves context identity independently of responses, latches scalar
committed truth before allocating diagnostic text, and recovers protocol errors
with SNAPSHOT followed only by cancellation/cleanup, not publication replay.
Every ordinary context explicitly retires and consumes RELEASE's final errors.
Retirement has at most two RELEASE attempts total, with one snapshot-assisted
cleanup-only recovery; the first transport failure survives later poison.
Ordinary native DONE with cleanup errors is still a valid retiring result.
Unrecoverable state/ownership, or diagnostic failure after commit that prevents
representing the truthful Result, calls `std::terminate` rather than inventing an
outcome or throwing an apparent publication failure.

Entry is a C++ callable and need not be `noexcept`: if forwarding completes before
Entry bookkeeping throws, the driver harvests only coherent response ownership/
commit scalars before unwinding, then snapshots and explicitly retires. A cleared
denial cannot overwrite an already saved ID. After known commit and successful
bounded retirement, a transient diagnostic allocation failure gets one attempt to
construct a truthful committed Result with a lifecycle diagnostic, consuming the
saved final RELEASE errors without another native call. Persistent allocation
denial or unrecoverable state/ownership remains fatal; not every OOM is recoverable.
Reconstruction routes its lifecycle marker through the bridge error channel so
retained final native poison/transport details and truncation remain visible,
including after a failed emergency RELEASE followed by successful retirement.

The Linux x86_64 `test_record_publication_bridge_driver` target links the **real
native adapter, phased publisher core and Threads**, not the engine. Filesystem
effects, nested calls, authority loss, native poison, response/sequence faults,
bounded diagnostics, release recovery and child-isolated fatal invariants are
host tests, with no production fatal-test hook. Focused validation:

```bash
make cmake                         # timeout600000 ms
make build                         # timeout14400000 ms
cmake --build build --target test_record_publication test_record_publication_operation test_record_publication_abi test_record_publication_bridge_driver -j2
ctest --test-dir build -R '^test_record_publication(_operation|_abi|_bridge_driver)?$' --output-on-failure
```

These are not actual Wine/PE/SDK execution, validated-binding or public delegation
proof. Task5B2's approved routing/default-authority admission checkpoint does not
activate publication. Production binding/dispatch and actual Wine publication
remain deferred to later tasks and their independent review/runtime gates; strict
Windows publication is unchanged. Task6A Phase1 itself remains uncommitted WIP
until independent reviewer PASS and explicit Phase2 exact-file commit authority.

#### Production publication client activation (Task6B WIP source checkpoint)

Task6B adds the production Windows client and public Wine dispatch on top of the
unchanged Task6A driver/ABI/native core. Presence of `wine_get_version` in already
loaded NTDLL selects Wine even if unsupported: only Wine9/win64 is admitted, with
explicit errors instead of native-Windows fallback. Native Windows retains the
strict native policy and neither loads the bridge nor applies the private temp
handoff. POSIX engine targets exclude the Windows client; every engine excludes
the Unix adapter. Both Windows standalone public-core test targets link the client
and advapi32 as well.

The existing validated configuration now emits `SPACE_WINE_PUBLICATION_BINDING`
only after receipt/session/package/payload/pair/discovery-copy/runtime checks:
`<64lowercase-buildid>:<canonical-uint64-device>:<canonical-uint64-inode>`, at most
106 ASCII bytes, inode nonzero. Both smoke and full application launches supply
this producer-owned value last, replacing hostile inherited input. It is an
integrity hint, not a credential, selector, sandbox or cleanup prerequisite.
Server cleanup remains based on immutable owned-session metadata, not a receipt.

The client loads only the fixed `space_record_publication.dll` builtin basename
through the admitted overlay/discovery copy and fixed owned WINEDLLPATH. It checks
export ownership and independent PE/Unix build IDs, actual Unix module device and
inode, ABI1/112-byte identity, x86_64, exact feature bits3 and fresh challenge echo.
Verified module/function metadata is immutable and pinned for process lifetime;
there is no global current operation. A fresh entry0 call checks the **current**
binding before every BEGIN. Missing, malformed or stale handoffs fail precommit.

Windows syntax validation rejects NUL, reserved components, alternate streams,
UNC/device and remote-drive forms. Local relative and drive paths (not just Z:),
including missing leaves, use `kernel32!wine_get_unix_file_name` with its CDECL
signature. Its ProcessHeap allocation is copied as raw host bytes and HeapFree'd
before BEGIN, also on copy exceptions. Returned bytes never traverse a PE
filesystem-path or UTF-8 conversion. Mapping is acquisition, not authorization:
the real shared authority helper and unchanged driver enforce represented-token
checks around hooks, and the host native publisher owns all retained-handle and
filesystem policy. Unrecoverable post-dispatch state/retirement remains fatal;
committed results and explicit diagnostics retain Task6A's truth boundary.

At the beginning of Windows `main`, before path capture, dotenv, logging, CEF or
runtime work, Wine-only initialization calls `space_wine_apply_owned_environment`
with FALSE: genuinely absent optional handoff leaves the environment unchanged
and makes no owned-root claim; malformed **provided** handoff fails startup.
Native Windows does not inspect it. Supported Wine execution remains the admitted
launcher/overlay, not an arbitrary unprepared interactive prefix.

Host tests compile the actual client, shared authority, driver and real native
adapter/core with inert Win32 models, including non-UTF8 host bytes and actual
filesystem publication. These are **not** Windows-width/SDK/Wine execution proof.
This activation source gate is an unfinished review checkpoint, not ready-to-merge
or all-feature completion. Actual application cross-build and guarded Wine
reproduction must be dispatched to `windows-ci-reproducer` by the supervisor
after independent review and the exact checkpoint commit. Proving ordinary Store
writes reach host publication does not replace later controlled umask/fresh-read/
grant checks. The previously observed495 failures are not asserted to share one
cause; independent whole-repository constraint timeout and remaining failures
still block final validation. Current-origin/main and PR CI gates remain later.

#### Supported Wine9 represented-authority guard (source/host-model stage)

`space_record_publication_check_authority` is shared C/C++ private code. Only
OpenThreadToken failure with ERROR_NO_TOKEN permits process-token inspection; any
thread token or other thread-query error denies. Process TOKEN_QUERY acquisition
and supported TokenGroups, TokenPrivileges and TokenElevationType sizing/readback
must succeed with bounded, structurally valid data. One aligned64KiB buffer is
reused. SID pointer extent, revision and subauthority count are checked before
reading, and deny-only groups reject **even when disabled**. Elevation must be
Default1 or Full2. Privileges must be exactly21 unique LUIDs with HighPart0 and
LowPart `[5,7,8,9,10,11,12,13,14,15,17,18,19,20,22,23,24,25,28,29,30]`.
Enabled/default-enable changes are allowed; removed or other attributes, duplicate,
missing and extra LUIDs reject. All API/close failures deny, handles close once,
and a primary captured Win32 error survives cleanup. Denial returns a meaningful
nonzero DWORD and retains it in LastError; stale LastError on success is ignored.
No token, SID or group data is logged.

This matches the represented stock-admin lineage in public Wine9
[`server/token.c` token_create_admin/admin_privs](https://github.com/wine-mirror/wine/blob/wine-9.0/server/token.c).
It deliberately does not call unsupported TokenHasRestrictions/IsTokenRestricted
or accept a failed query as unrestricted. It detects the represented reductions
above, **not** arbitrary filtering history, ignored restriction-SID requests, a
foreign host UID, or a sandbox boundary. Native Windows strict publication and
host filesystem privacy policies are unchanged.

Direct PE entry1 BEGIN and ADVANCE START through BEFORE_COMMIT run this guard
before native payload validation/dispatch. Denial returns SRP_ACCESS_DENIED and
clears only safe inline state claims, never following unchecked diagnostic pointers;
callers retain their saved context ID for recovery. SNAPSHOT/CANCEL/RELEASE and
actual BEFORE_CLEANUP advance remain callable after authority loss. Native exact
phase/sequence validation rejects a forged cleanup event rather than resuming a
commit. Entry0 retains its112-byte identity roundtrip and own-HMODULE opaque Wine9
dispatcher. Source/host WinAPI models and tiny header-only MinGW C/C++ compilation
do not prove actual Wine token-query behavior; that remains guarded Task5B2 runtime
validation. The builder inventories all ten fixed pair source/header inputs: shared
ABI/authority/native-entry/Operation/publication headers, adapter and publisher
sources, PE/Unix bridge units and builder itself, excluding uncompiled probe/temp
helpers. Named translation units select SO entry+adapter+publisher independently
of input order; the PE remains its bridge alone linked to advapi32, with no native
adapter/core symbol import.

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
result beyond the historical cutoff. Actual post-review observations are recorded
separately below; their diagnostic clarity does not make the Windows gate green.

### Actual post-diagnostic observations (2026-10-17)

Two actual guarded `reproduce --repo-root .` runs followed review/commit of the
diagnostics. The second was a single advisor-requested discriminating experiment,
not an unchanged retry. Retained evidence roots (all paths repo-relative):

- **Run A:** `build/windows-ci-repro/20261017T084732204168Z-596071b82b514e789559dc7802dd6eac/`
- **Run B:** `build/windows-ci-repro/20261017T094643826398Z-3c1534e65b1d4821afb46c6a137ce75d/`

Each root retains `ledger.json`, `build-windows-from-linux.stdout.log` and
`wine-fast.stdout.log` / `wine-fast.stderr.log`, alongside the other stage logs.

| Observation | Run A | Run B |
| --- | --- | --- |
| Clean source HEAD at execution | `027a63e498f8f3d18bec0ff976eebe5a734f650c` | `583d213fedf10069b928effc9bdd34f8c9bd634a` |
| Build version | `6+git.2293.g027a63e4` | `6+git.2294.g583d213f` |
| Cross-build / package / output verification / API admission | PASS | PASS |
| Wine fast outcome | FAIL | FAIL |
| Observed RUN / PASS / FAIL markers | 2261 / 1816 / 446 | 2261 / 1816 / 446 |
| Application-command / stage-helper return codes | 1 / 1 | 1 / 1 |
| Approximate Wine-fast stage duration | 471 seconds | 501.66 seconds |
| Root native fatal banner | None observed | None observed |
| Primary capture | Complete | Complete |
| Terminal cleanup helper / wineserver stop / wait | 0 / 0 / 0 | 0 / 0 / 0 |
| Final owned lifecycle | Ended, unauthorized; generation11 / stopped11 | Ended, unauthorized; generation11 / stopped11 |

Marker counts include the terminal module-load failure; they are not 446 proven
independent product bugs, nor is RUN minus PASS a reliable substitute for FAIL
counting. Both runs stopped later while loading `tests.test-openai-offline`, with
`get-asset-path` nil, not a native crash. Complete capture and successful cleanup
do not mean a complete successful test suite or a successful top-level ledger.
The fixed owned data/cache/tmp roots and crash-policy verification were recorded
in both runs. With no observed root native fatal, actual automatic reporter
detach and the 30-second fatal-report grace remain **unexercised**.

Before each actual run, the standard full Linux gate passed: Fennel compile
**1331 files**, constraints **0 violations**, CTest **31/31**. The six-module host
tooling gate passed **478/478** before the actual runs. These are retained prior
validation results, not new checks performed for this documentation update.
Run B's build log records version at line 224, recompilation of
`src/record_publication.cpp.obj` at 447 and Windows build completion at 492. The new
Windows production diagnostic branch therefore cross-compiled; its native Windows
C++ test assertions remain **unrun**. Run B's captured CLI payload SHA-256 is
`f940618f4107289fff3c7004cc201226ce2e5362cc94a2eb829f149cfdc63bb7`.
Version, clean HEAD and payload identity correlate the observation; they are not
independent full-binary-to-source attestation.

#### First refusal and the measured creation/query boundary

Both runs first fail `Menu root show link entities adds related nodes`
(`wine-fast.stdout.log`:796–798), reporting `storage-failed` / `not-committed`.
Run A reports anchor owner-match=true, expected-protected=true versus
actual-protected=false, dacl-match=false, expected 44 versus actual 64 DACL bytes,
and expected 1 versus actual 2 ACEs. Its 127 matching diagnostic occurrences are
message occurrences, not failed-test counts. Those metrics alone did not correlate
input/create-versus-reopen/initial-versus-later validation, so did not settle the
creation boundary.

Run B's complete first refusal at `wine-fast.stdout.log`:798 adds the reviewed
same-attempt correlation:

- `attempt-id=1 phase=initial-prepare initial-private=refused`;
  `acquisition-id=2 acquisition-phase=initial-prepare acquisition=exclusive-create`.
- Actual descriptor input: present and valid; owner-match=true; protected=true;
  DACL present, valid and matching the expected owner-only policy; 44 bytes, 1 ACE.
- Checked native completion: `native-complete=true file-created=true`
  (`FILE_CREATED`), establishing successful exclusive creation of a fresh anchor,
  not collision/reopen.
- Immediate query of that **same acquired handle**, with no intervening application
  mutation in the reviewed source: owner-match=true, actual-protected=false,
  dacl-match=false, 64 bytes and 2 ACEs versus expected protected 44 bytes/1 ACE.

The unchanged security predicate correctly **fails closed**. This establishes a
creation/query security-descriptor fidelity incompatibility in the exercised Wine
environment. It does **not** establish an exact upstream function responsible,
the additional ACE's trustee (including any claim that it is SYSTEM), or a native
Windows failure. Upstream Wine9 source is compatible with the observation, not
direct proof of the installed implementation or observed ACE identity.

Later missing-directory failures are consistent with a failed test leaving a
default store override referring to a removed temporary directory; later engine
stub/get-asset-path failures may also be fixture cascades. Those remain hypotheses,
not demonstrated identities or fixed defects. No guessed cascade fix is included.

#### Human/infrastructure block: validation policy is unchanged

Advisor `ses_eb6e4928cffe1uGagsdt54R5O4` assessed the final correlated evidence as
**requires_human**. The next requirements are native Windows persistent-ACL
validation and an explicit decision whether that native validation may substitute
for the mandatory Wine-green gate for this work. **The user has not approved that
substitution.** If substitution is not approved, the work remains blocked on the
Wine gate; native validation alone does not silently waive it.

Repeated unchanged Wine probes are not useful next evidence. No additional skip,
production security-policy relaxation, post-create ACL repair, budget increase or
gate bypass is authorized. No publish, readiness or completion claim follows from
these runs. Native Windows/macOS proof and the historical Linux signal
investigation remain separate; this measured Wine boundary does not close them.


## See also

- [Cross Platform](/dev/subsystems/cross-platform)
