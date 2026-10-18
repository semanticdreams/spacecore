# Real private publication under local Wine

## Direction and scope

The user requires real persistent record publication under local Wine, not mocked
storage and not a native-Windows-CI-only debugging loop. Local Wine is a required
development/validation target for this feature. Preserve private staging, supported
destination policy, handle-relative namespace safety, atomic replacement and
truthful committed errors. Do not weaken native Windows policy to accommodate
Wine's descriptor representation.

This supersedes the native-runner/gate-substitution proposal recorded in the Wine
note and extends the backend scope of the 2026-10-16 secure-publication design.
Its no-production-subprocess requirement remains intact. No transport/server,
daemon, Wine fork, post-create privacy repair or new unknown-outcome API is needed.

## Evidence and rejected shortcuts

At reviewed source `583d213f`, the retained run
`build/windows-ci-repro/20261017T094643826398Z-3c1534e65b1d4821afb46c6a137ce75d/`
cross-built successfully. Its first refusal (`wine-fast.stdout.log:798`) correlates
valid protected owner-only input, successful exclusive `FILE_CREATED` completion,
and an immediate same-handle query returning an unprotected, different DACL.
Owner matches; expected/actual DACL sizes are44/64 and ACE counts1/2. No application
mutation intervenes. This proves the exercised creation/query fidelity mismatch,
not the extra ACE's identity or an exact upstream function responsible.

Upstream `wine-9.0` research establishes why recognizing a two-ACE shape is unsafe:
`server/file.c::mode_to_sd` loses group-mode information;0700/0750/0770 can have
identical synthesized descriptors. `sd_to_mode` can itself grant group permissions
for a current-user ACE. Neither relaxed ACL matching nor a restricted Windows token
under Wine establishes host privacy.

An ordinary ELF child launched through Wine9 `CreateProcessW` is also unsuitable:
the native fallback double-forks, does not map the requested stderr, and does not
establish the assumed Win32 waitable process object. A separate broker would add
authentication/lifecycle and acknowledgement-loss semantics without being needed.

Selected alternative: Wine's in-process PE/Unix-library mechanism. Upstream Wine9
and the out-of-tree LatencyFleX example establish a feasible mechanism, not proof
that our eventual artifact works. Actual installed loader, ABI and persistence
behavior remain mandatory local evidence gates.

## Three backend boundaries

1. Native POSIX retains its existing policy and filesystem implementation.
2. Native Windows retains its existing strict descriptor policy and native handle
   operations. It never requires or loads the Wine module pair.
3. Wine delegates the complete operation in-process to the same source compiled
   for the host POSIX environment. Host UID/GID, modes and supported metadata are
   the Wine security contract; emulated Windows ACL fidelity is not promised.

The Wine host contract retains0700 owned anchor/workspace,0600 private record
before bytes, supported destination UID/GID/mode preservation, unsupported
ACL/xattr/special-policy refusal, reparse/symlink/link/identity defenses appropriate
to the existing POSIX backend, and descriptor-relative atomic replacement.
No parent chmod, ownership takeover or process-global umask changes.

Detect Wine internally through an export in already loaded NTDLL, not an
environment/user option. Initial supported bridge scope is Linux x86_64 host,
win64 PE and the matched, locally tested Wine9 mechanism. Other Wine runtimes or
missing/incompatible support fail explicitly, never fall back to relaxed native
Windows checks. Runtime detection is compatibility selection, not authentication
against an attacker able to replace the application/runtime.

Reject caller thread impersonation and restricted primary-token contexts before
delegation; token-query errors also reject. Recheck authority after hooks before
resuming publication. Authority refusal cancels/cleans instead of continuing; it
cannot clear a committed latch. Host metadata is authoritative, not Wine tokens.

## Shared phased operation

Keep the public `publish(destination, payload, hooks) -> Result` and binding/store
outcomes unchanged. Introduce one private per-publication operation owning the
existing platform Attempt, copied payload, primary/cleanup errors and sticky
committed state. Native publish drives it inline; Wine drives it synchronously
through the bridge. Do not clone either filesystem/security algorithm.

Only the existing hook boundaries yield:

| Continuation | Native work before the next event |
|---|---|
| Start | Prepare private objects; request before-write |
| before-write succeeded | Write/flush/read back; request before-security |
| before-security succeeded | Apply/verify final policy; request before-commit |
| before-commit succeeded | Validate, rename and latch committed; enter cleanup |
| Publication or precommit hook failed | Preserve primary failure; enter cleanup |
| Owned workspace needs cleanup | Request before-cleanup; then clean even if hook failed |
| Cleanup complete | Return existing result or primary plus cleanup error |

No hook, PE return, bridge round trip or adapter work separates final validation,
rename and immediate committed assignment. Construction failure has no hook;
partially failed preparation still cleans owned state. Cleanup-hook failure never
suppresses actual cleanup. A known commit remains committed through later errors.

Callbacks execute in the caller's native/PE context. The Unix library returns a
fixed phase event, not a reverse callback. Continue/fail applies only to the exact
pending event; stale/duplicate/out-of-order transitions fail explicitly. Separate
contexts support nested and overlapping attempts without a global current attempt
or locks spanning hooks. There is no reset/reuse session or public incremental API.

Cancellation never resumes publication. Explicit cancellation/finalization reports
cleanup problems; RAII cleanup is a last-resort safeguard, not a reason to swallow
failures. The loaded module outlives every context. Unexpected recoverable adapter
errors after a potentially committing advance must preserve/query sticky commit
truth rather than manufacture a not-committed error. Application death, memory
corruption and power loss have no stronger guarantee than native publication.

## Wine bridge and ABI

Package a uniquely named builtin-marked PE bridge and native Unix library under
one overlay-owned module root:

```
x86_64-windows/space_record_publication.dll
x86_64-unix/space_record_publication.so
```

Use matched `winebuild --builtin` with MinGW for the PE and the host C++17 compiler
for the SO. Initialization occurs outside DllMain. The bridge queries its own
HMODULE using Wine's `NtQueryVirtualMemory` / `MemoryWineUnixFuncs`, validates the
eight-byte result, then dispatches through NTDLL's `__wine_unix_call`. The returned
opaque table handle is not a directly callable PE function pointer. This is a
versioned Wine-internal dependency with explicit compatibility checks.

Ubuntu's matching SDK deliberately does not install `wine/unixlib.h`. Do not
require or install that private source header. The PE bridge owns only the minimal
Wine9 opaque-handle and dynamically resolved dispatch-pointer declarations, with
source provenance and size/alignment/calling-convention assertions. Installed,
package-verified `windows/winternl.h`, `windef.h` and `winbase.h` supply NT/Windows
types and the guarded MemoryWineUnixFuncs enum; assert its Wine9 value1000. The Unix
entry remains self-contained signed32-bit status/native calling convention. Select
one coherent installed SDK root and retain all header/package/source identity
checks; absence or mixed roots fail explicitly. No wholesale internal-header copy,
source-tree dependency or system Wine modification.

The shared private C layout uses fixed-width types, explicit sizes/offsets, version
and request validation, with assertions in both builds. No C++ objects/exceptions,
native long/size_t/bool/wchar_t, CRT allocation ownership or callbacks cross it.
Caller-owned input/output storage remains live synchronously; the host copies
operation-owned data. Opaque contexts are destroyed by their creating module.
Every Unix entry contains C++ exceptions. Bounded diagnostics include explicit
truncation/buffer failure; retrieving an error must never replay publication.
Commit fields must be recoverable without allocating after commit.

Resolve `kernel32!wine_get_unix_file_name` with the actual CDECL signature; free
its result with `HeapFree`. Treat the returned host pathname as bytes rather than
assuming UTF-8. Wine mapping is initial pathname acquisition, not authorization
or a canonicalization/retained-handle proof. Thereafter the existing POSIX backend
owns handles and policy. Validate NULs, reserved names and unsupported device,
remote and alternate-stream forms. Preserve intended missing-leaf, case, symlink
and retained-parent semantics with explicit tests; do not assume a Z: mapping.

## Build, packaging and execution

Add the matching Wine development tools/headers to reviewed fixed host setup and
preflight. On the current Ubuntu family these are `wine64-tools` and `libwine-dev`.
Do not silently upgrade/replace the selected Wine or add an unapproved package
source. If matching packages cannot preserve it, report that infrastructure choice.
All provisioning remains through guarded setup-host, not ad-hoc elevated commands.

Only the Wine overlay contains the pair and its native dependencies. Native build
packages, ZIPs and installers remain pair-free. Fixed owned WINEDLLPATH replaces
ambient module roots for the appropriate Wine launches; it is not an arbitrary
environment passthrough. Bind both artifacts, ABI/build identity and tool/runtime
identity into overlay inventories/admission. Verify actual selected dispatch, not
merely a filename. No installed Wine module is modified.

Wine9 also requires a Windows-side discoverable image before ordinary basename
loading reaches its builtin directories. Supply a byte-identical discovery copy of
the verified publication PE beside the probe/application in the owned Wine overlay;
keep the paired architecture directories and fixed WINEDLLPATH for Unix-library
association. Verify the copy against the pair's PE digest at staging, admission,
execution and readonly receipt inspection. This is not a System32/prefix install,
an installed-Wine modification or an arbitrary DLL search path. Any loader-native
fallback lacking paired Unix proof must still fail admission/client validation.
Native packages remain helper-free. Test-support pairs need equivalent Wine-only
discovery copies. A copy digest alone does not prove the module Wine loaded;
entry0, both build IDs and actual Unix SO identity remain mandatory.

Capture bounded immediate numeric loader errors and raw bridge-call status before
formatting, preserving the primary code20/refusal and crypto-absence distinction.
Do not enable broad Wine debug logging or inspect prefix drives/registries. The
first actual null-load result lacked numeric error evidence: deployment correction
and a successful later probe cannot retrospectively prove its exclusive cause.

Build and run a fixed publication-focused native PE test through the existing
guarded reproduction flow before the full suite. It must exercise the real bridge
and host metadata. Keep existing public capability commands; do not introduce an
arbitrary executable/filter/path converter. The plan must allocate this component
an explicit independent finite execution/cleanup bound and ownership lifecycle,
not consume the existing1800-second application's time or silently enlarge its
admission/outer budgets. Reconcile receipts, generations, stage summaries, caps and
failure preservation for the fixed component as one reviewed harness change.

## Locally meaningful tests and acceptance

Retain common actual publication tests through the public API: exact/binary/empty
bytes, overwrites, policy preservation, phase/error parity, cancelled contexts,
nested attempts, namespace substitution and committed cleanup truth.

Wine-specific tests require native host observations, using a separate test-only
support module if necessary. No arbitrary fixture mutation/inspection commands
enter the production bridge. Prove private modes before/after bytes; reject
group-readable/writable0750/0770 anchors unchanged even when Wine reports the same
descriptor as0700. Exercise unsafe metadata, final-policy mutation and ordinary
umask022/002 layouts without parent changes. Real differing-Unix-identity denial
tests require suitable configured identities and positive controls; Wine restricted
tokens must not be reported as that proof. Record any unavailable identity evidence
honestly rather than adding native-only CI as this feature's local gate.

Keep native Windows-specific tests for that backend, clearly separated and unrun
under Wine, not fake passing. Their implementation must not be weakened; they are
not a substitute or additional native-only execution prerequisite for the Wine
backend. Linux tests continue to exercise the unchanged real POSIX policy.

Require actual Wine create/update/reopen through owning stores with a new process
reading exact persisted bytes, correct cache/revision/notification ordering and
unchanged stale-edit rejection. Missing/tampered/incompatible support, mapping
failures, authority changes and bad ABI/phase transitions fail explicitly.

Validation order: native build; project Fennel compile then constraints as relevant;
focused native/ABI/tooling/persistence tests; complete applicable host harness and
standard Linux gate; guarded real focused publication and full Wine reproduction.
Any remaining suite failures require evidence-based diagnosis, not skips or a
return to native-CI-only debugging. Earlier fixture cascades and historical Linux
signals remain independent until proved related.

## Primary research references

- Wine9 server permission conversion: https://github.com/wine-mirror/wine/blob/wine-9.0/server/file.c
- Unix-library ABI: https://github.com/wine-mirror/wine/blob/wine-9.0/include/wine/unixlib.h
- Module initialization: https://github.com/wine-mirror/wine/blob/wine-9.0/dlls/winecrt0/unix_lib.c
- Loader/module association: https://github.com/wine-mirror/wine/blob/wine-9.0/dlls/ntdll/unix/loader.c
- Unix function-table lookup: https://github.com/wine-mirror/wine/blob/wine-9.0/dlls/ntdll/unix/virtual.c
- Path export/ownership: https://github.com/wine-mirror/wine/blob/wine-9.0/dlls/kernel32/path.c
- Native ELF process fallback: https://github.com/wine-mirror/wine/blob/wine-9.0/dlls/ntdll/unix/process.c
- Out-of-tree mechanism example: https://github.com/ishitatsuyuki/LatencyFleX/tree/b677c2e41f425a3d4c80ab099a2687479e1b35ef/layer/wine

Research establishes candidate mechanisms and counterexamples, not installed-binary
certification. No native Windows/macOS security certification, Wine-general ACL
emulation,32-bit/WoW64 support, hostile same-UID protection, remote filesystem
support or power-loss durability is claimed.
