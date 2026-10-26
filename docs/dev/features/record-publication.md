# Record publication

The public `publish(destination, payload, hooks) -> Result` contract and the
Fennel store/editor outcomes are unchanged. Native POSIX uses the host filesystem
backend; native Windows uses its strict NT descriptor/handle backend. Wine selects
an in-process bridge to the same POSIX publication core, **not** relaxed emulated
Windows ACL checks. No production subprocess, daemon, journal or new outcome is
introduced. This page is the canonical source contract; runtime evidence is
separately qualified below.

## One private phased operation

`src/record_publication_operation.h` owns a per-attempt operation: platform
Attempt, copied payload, primary/cleanup errors and sticky committed state.
Native publication drives it inline; the synchronous Wine driver drives the same
operation through fixed events. Only existing hook boundaries yield:

| Continuation | Work before the next event |
| --- | --- |
| START | Prepare private objects; request before-write |
| before-write success | Write, flush and read back; request before-security |
| before-security success | Apply and verify final policy; request before-commit |
| before-commit success | Final validation, rename, latch committed; enter cleanup |
| Publication/hook failure or cancellation | Preserve primary failure; enter cleanup only |
| Owned workspace cleanup | Request before-cleanup; clean even if that hook fails |
| Cleanup complete | Return the existing result/error contract |

No hook, PE return, bridge round trip or adapter work separates
final validation, rename and immediate committed assignment. Construction failure
has no hook; partial preparation still cleans owned state. Hooks execute in the
caller, outside driver/context locks, not as Unix-to-PE callbacks. Exact pending
event/sequence checks reject stale, duplicate and out-of-order mutation. Independent
contexts permit nested/overlapping attempts; there is no global current attempt,
reset session or public incremental API.

Cancellation never resumes publication. Explicit finalization reports cleanup
errors; RAII cleanup is a last resort. Once known, committed truth survives cleanup,
authority and recoverable transport errors. An irrecoverably inconsistent response
after a potentially committing call, or unretirable ownership, is fatal rather
than a fabricated not-committed result. Application death, memory corruption and power loss have no stronger guarantee
than native publication.

## Private ABI, loader and lifetime

`src/record_publication_wine_abi.h` defines fixed-width, checked layouts:
identity **ABI1/112 bytes**, operation **ABI1/168 bytes**. No 144-byte alias exists.
No C++ objects/exceptions, native long/size_t/bool/wchar_t, callbacks or CRT-owned
allocations cross the ABI. Caller-owned counted input/output storage lives through
the synchronous call; the host copies owned inputs. Opaque contexts are destroyed
by their creating module. Unix entries contain exceptions.

Entry0 validates identity; entry1 implements BEGIN/ADVANCE/SNAPSHOT/CANCEL/RELEASE.
BEGIN captures only START/sequence0, without preparing files. Mutation consumes
the exact event/sequence. SNAPSHOT is nonadvancing/nonallocating; diagnostics never
replay a committing call. RELEASE finalizes cleanup before retiring a nonrecycled
ID. Unexpected live exceptions poison publication, preserving snapshot/cleanup.
Protocol NTSTATUS is distinct from operation error presence, including a present
empty error. Primary, cleanup and transport buffers are separate, counted and
explicitly truncated. The driver starts each at4096 bytes and permits one growth
per channel to65536, refilled by SNAPSHOT only; committed scalars latch before
diagnostic allocation. Bounded recovery cannot erase primary or cleanup failures.

The initial supported scope is Linux x86_64, win64 PE, matched distro Wine9.
Presence of `ntdll!wine_get_version` selects Wine internally, not an environment
backend switch. Unsupported Wine or missing support explicitly refuses; it does
not fall back to relaxed native Windows policy. Native Windows never loads the
pair or applies the private Wine temp handoff.

The owned overlay contains:

```text
wine-publication/modules/x86_64-windows/space_record_publication.dll
wine-publication/modules/x86_64-unix/space_record_publication.so
```

The builtin-marked PE is loaded by its unique basename with fixed owned
`WINEDLLPATH`. Wine9 also needs a byte-identical **discovery copy** beside the
probe/application. Its digest is verified during staging, admission, execution
and readonly inspection, but does not alone prove selected dispatch. Absolute PE
loading or logical System32 naming is not proof of Unix association. No installed
Wine module or prefix System32 module is replaced.

Outside DllMain, the PE queries its own HMODULE using `NtQueryVirtualMemory` /
`MemoryWineUnixFuncs` (Wine9 value1000), validates the eight-byte opaque table
handle, and uses `ntdll!__wine_unix_call`. It is not a callable PE function pointer.
Minimal private Wine9 declarations have provenance and ABI assertions; installed
matching windef/winbase/winternl headers supply platform types. Missing
`wine/unixlib.h` is expected on this SDK, not permission to copy internal headers.

Matched `wine64-tools`/`libwine-dev`, `winebuild --builtin`, MinGW and host C++17
produce the pair. The host toolchain verifier binds coherent package/source
versions, selected loader implementation, SDK root, tools and hashes. It cannot
certify runtime compatibility by package metadata alone. Provisioning and actual
cross-build/Wine runs remain `windows-ci-reproducer` work, never ad-hoc commands.
Native packages, ZIPs and installers exclude production and test-support helpers.

Validated configuration overrides inherited `SPACE_WINE_PUBLICATION_BINDING` with
`buildid:device:inode`:64 lowercase hex, canonical uint64 decimals, nonzero inode,
at most106 ASCII bytes. It carries no path/selector and is an integrity hint, not
a credential. Before every BEGIN, fresh entry0 proof compares independent PE/Unix
build IDs, actual SO identity, ABI/architecture/exact feature bits3 and challenge
echo. Verified module/function metadata is immutable and pinned for process lifetime;
no context outlives its code. Missing, malformed or stale bindings refuse.

The client validates supported Windows path syntax, then calls
`kernel32!wine_get_unix_file_name` with its CDECL signature and releases the Wine
allocation with `HeapFree` before BEGIN. Mapped paths are raw host bytes, never a
PE filesystem-path/assumed UTF-8 conversion. Mapping is acquisition, not
authorization; the POSIX backend owns retained handles and namespace checks.
Source tests cover missing leaves, local relative/drive paths and case semantics;
their actual PE/Wine execution measured PASS at `fa4fc4b2` as recorded below. No Z: mapping
is assumed. NUL/reserved/alternate-stream/device/UNC/remote forms refuse.

## Host policy and represented authority

The Wine privacy boundary is actual host UID/GID/modes and supported metadata:
owned0700 anchor/workspace,0600 staged file **before bytes**, preserved supported
destination UID/GID/mode, ACL/xattr/special-policy refusal, symlink/link/identity
defenses and descriptor-relative atomic replacement. Unsafe0750/0770 anchors
refuse unchanged even when Wine synthesizes the same descriptor as0700.
No parent chmod, ownership takeover, post-create privacy repair or process-global
umask change is allowed.

The shared PE/client authority guard rejects thread impersonation and unsupported
reported process-token states, including query/close failures. Bounded
`TokenGroups`, `TokenPrivileges` and `TokenElevationType` queries require no
deny-only groups, Default/Full elevation and the21 unique stock Wine9 admin LUIDs
with supported attributes. It does not interpret unsupported
TokenHasRestrictions/IsTokenRestricted failures as unrestricted. This cooperative
guard checks represented reductions, not arbitrary filtering history, ignored
restriction SID requests, a sandbox or foreign-host-UID denial.

Authority is rechecked after publication hooks. Failure cancels rather than
resuming; SNAPSHOT/CANCEL/RELEASE and actual cleanup remain available. Authoritative
native phase checks reject forged cleanup transitions. Native Windows strict NT
assertions remain a distinct backend contract, not weakened for Wine.

## Closed validation harness

The four public guarded commands remain preflight/bootstrap-vcpkg/setup-host/
reproduce. There is no executable/filter/path-converter passthrough. The current
reproduce stage order is:

<!-- publication-stages -->
| Stage | Bound/role |
| --- | --- |
| `preflight` | Fixed prerequisite checks |
| `build-windows-from-linux` | Existing application cross-build |
| `package-windows-runtime` | Clean native payload |
| `verify-windows-outputs` | Native output verification |
| `wine-publication-build` | 900 seconds, production and test-support pairs |
| `wine-admission` | 480 seconds outer helper |
| `wine-publication` | 420 seconds independent outer helper |
| `wine-fast` | 1920 seconds outer; application1800 seconds |
<!-- /publication-stages -->

GNU timeout steps retain a further5-second kill escalation. Admission probes
remain60 seconds, initialization90, fixed path/registry commands30, smoke60,
wineserver stop/wait10/15, parent terminal cleanup backstop45 seconds.
The runner default remains 120 seconds; the full-repository pipeline case has an
explicit 300-second deadline, human-authorized on 2026-10-26 after measured Wine
evidence. The three app-root reload integration cases and reference-lifecycle
composition startup cases also retain explicit 300-second deadlines. The
240-second overrides remain in the runner's synthetic budget regressions, not as
a general case deadline. Wine publication components retain their 120/120/30/30-second
budgets and independent 420-second outer helper. Existing environment-override
precedence and skips are unchanged. These are limits, **not measured PASS
timings**; publication does not consume or enlarge application time.

One initialized owned session uses **schema-4** owner/receipt validation. Admission
creates a one-shot **publication grant**, never direct application permission.
It is durably consumed before these four sequential components:

| Component | Bound | Child umask |
| --- | --- | --- |
| cpp-022 | 120 seconds | 0022 |
| cpp-002 | 120 seconds | 0002 |
| store-write | 30 seconds | 0002 |
| store-read | 30 seconds | 0002 |

Each C++ run uses an independent test-only support pair
`space_record_publication_tests.dll`/`.so`, its own verified discovery copy and
`SPACE_WINE_PUBLICATION_TEST_BINDING`; production entrypoints expose no fixture
mutation/inspection commands. It also runs five private PE children: intact
control, missing/bad PE, missing/bad Unix SO. Owned copied fixtures have rebound
identities and isolated loader environments. Each child has a10-second wait and,
if needed, a further2-second termination/reap wait. Both waits remain within the
shared60-second sequence inside each C++120-second limit; they add no host
component/grant or production subprocess.

### Closed Unix launch for private children (source contract)

The separate test pair uses support ABI2/features7; production ABI1/features3
is unchanged. Support entry0 identity112 and entry1 fixture12376 retain their
layouts; entry2 uses `SrptLaunch`, 152 bytes, with only fixed CONFIGURE/RUN actions,
case IDs, retained root tokens and independent production/support bindings. There
are no executable, environment-map, path or timeout selectors. CONFIGURE is first,
before overlay inspection or fixture creation/copying, with retained owned TEMP.
It starts the original native monotonic60-second budget. The PE uses call-start
plus floored returned remaining milliseconds, never adding configuration time back.
RUN requires the same retained fixture and exact control, missing-pe, bad-pe,
missing-unix, bad-unix order. Copy-time OBSERVE captures native full-byte/source
receipts for each intact SO, architecture PE and discovery copy before intentional
damage; the SO binding is never derived from a damaged or deleted artifact.

Support builds pin the verified native Wine64 implementation (Linux x86_64 ELF,
not a wrapper), server and trusted installed ancestors, with build-time SHA256 and
stable identity/metadata snapshots. Raw pathname bytes are embedded privately;
runtime nofollow descriptor/path rechecks detect cooperative installation changes,
which require a rebuild. GNU libc2.34 or later is required for `posix_spawn` cwd
and closefrom actions. Spawn uses the canonical pinned implementation, verified
case cwd, /dev/null stdin, closed descriptors3+, reset signals and an owned process
group; no parent environment/cwd/umask mutation or PATH lookup is allowed.

Python overrides ambient `SPACE_WINE_PUBLICATION_TEST_CRYPTO` for each C++ launch:
exact admitted `bcryptprimitives=b;advapi32,cryptbase=b` maps to `b`, exact native
variant `bcryptprimitives=n;advapi32,cryptbase=b` to `n`; unknown values refuse.
The native entry constructs the Unix loader environment, not merely a Windows
environment block. It uses empty PATH, the owned session/server/temp handoffs and
exactly two raw application roots: case production modules and independent
support-only modules. Wine's stock installed loader paths remain separate runtime
dependencies, not extra application roots. Producer and child require exactly
`space_record_publication=b;space_record_publication_tests=b;bcryptprimitives=<b-or-n>;advapi32,cryptbase=b`
with the owning crypto value, no grouped-name alias or acceptance of either backend.
Windows-visible guards still require CP_UNIXCP lossless roundtrips, exact roots,
cwd/private TEMP, copied dependencies and no production preload. The intact control
must prove actual copied-SO identity distinct from the original, exact nine-byte
embedded-NUL publication, four hooks, supported policy and a clean anchor. Negatives
must prove intended loader/association refusal, zero hooks, unchanged old bytes and
metadata, no anchor/cache/fallback—not malformed binding or setup failure.

At least13 seconds (10 wait +2 termination/reap +1 cleanup reserve) must remain
while copying and before RUN; no budget is enlarged. Checked native completion
retires the exact leader; failures permanently end the sequence. An
ownership-uncertain outcome preserves the fixture and terminates the current PE
process without unwinding or recursive deletion, with `_Exit` fallback, not a
debugger-dependent abort. Explicit checked final cleanup is inside the same60s.
Bounded numeric case/phase/outcome/errno/exit/signal/native-result diagnostics and
control-completion after all control assertions aid diagnosis; they are not report
or grant authority. No path, environment, binding or payload is dumped.

Installed-runtime feasibility measured PASS at `fa4fc4b2` in the fresh full guarded
run recorded below; native host models alone do not establish
direct Wine64 synchronous PE completion, installed loader selection, actual roots,
encoding, retirement or timing. The prior first-control location-07 refusal is
not evidence that a different override spelling works. The fresh full
`windows-ci-reproducer` run measured the
intact control and then all five cases under both umasks, reports, stores, unchanged
four-generation grants, full Wine gate and terminal cleanup PASS. Native Windows and
POSIX branches, Wine category separation and the fixed store base-dir
exception remain unchanged.

Each C++ result is a **parent-pinned** report: exclusively allocated0600,
regular/current-UID/single-link/zero-length, nofollow/CLOEXEC, retained noninherited
FD. The child writes OPEN_EXISTING without create/truncate/adopt; the host verifies
original object and post-write path identity, bounded JSON, pair identity and
categories. The first report is verified before removal/fresh allocation. Both
historical fact vectors remain checked at promotion, not merely the final stat.

The writer/independent reader use one fresh parent-owned0700 external root,
`session/tmp/space-record-publication-store`, derived from the verified Windows
temp handoff. The user-approved test-only **fixed base-dir** exception uses existing
constructor options; it is **not default-root coverage**. Production
appdirs/stores/default selection is unchanged. Exact persisted bytes,
revision/conflict/notification/error and cleanup assertions remain required; the
root is not wiped between writer and reader.

Every component increments the durable generation. After four successful
components, stopped-generation acknowledgment, both reports and complete private
launch/result observations must agree. Only the owning parent, under the build
lock, independently validates capture plus proof and promotes a fresh distinct
one-shot **application grant**. Application/smoke consumes it before launch and
ends authorization during terminal cleanup; partial, replayed or interrupted work
cannot revive admission. Private observations distinguish raw command/helper
statuses from unknown native PE/debugger statuses. Existing16MiB stream caps,
4KiB marker limits,48KiB encoded response cap and richer retained ledger remain.
Cleanup acknowledges bounded Wine CLI completion, not native-process quiescence.

## Evidence and remaining gates

<!-- publication-evidence -->
This documentation describes reviewed source through
`a8012ef002c1bc21ae2c2685e788ddbcc7bb2c8e`, not an actual runtime-tested final Wine
revision. Earlier compatibility proof is not final Wine publication success.
Actual Wine/PE publication categories and the full Wine gate measured PASS at
`fa4fc4b2dc6465f89c85627017a442796695707e` on 2026-10-26:
production entry0/entry1, common/host-policy/mapping-authority categories, both
umasks, all five loader children, fresh writer/reader and grant/generation/cleanup
acceptance passed controlled execution. The full Wine suite executed 4867 tests:
4867 PASS / 0 FAIL, exit 0, total suite 900773.002ms. The complete, sealed capture
and detailed measured results are recorded in the
[Windows/Wine measured-result update](../notes/windows-wine-build-and-test.md#current-publication-contract-measured-wine-acceptance-below).
Native NT assertions remain intact and unexercised under Wine;
foreign_uid_probe=not-configured. Restricted Wine tokens do not substitute for a
real differing-UID probe with positive controls.
<!-- /publication-evidence -->

Native build, project-native Fennel compile **before** constraints, four focused
publication/operation/ABI/driver CTests, persistence tests, full Linux and host
tooling gates are separate evidence from actual Wine. Whole-branch independent
review precedes capability-only actual focused/full Wine execution. Required
failures must retain command/status/output/revision/tree evidence and be diagnosed,
not skipped or relabeled. This docs-only checkpoint identifies the exact
measured source revision and retained run for the final Wine results above.
PR CI remains the integration gate; native Windows-only behavior retains its own
authority without substituting for required local Wine publication validation.

No native Windows/macOS security certification,32-bit/WoW64, remote-filesystem,
hostile same-UID or power-loss durability claim follows from this source contract.
See [Windows/Wine build and test](../notes/windows-wine-build-and-test.md), the
[approved design](../../specs/2026-10-17-wine-posix-publication-design.md), and
`src/record_publication_wine_{abi,driver,authority}.h`,
`src/record_publication_wine.cpp` and `src/record_publication_wine.h` for private
boundaries.
