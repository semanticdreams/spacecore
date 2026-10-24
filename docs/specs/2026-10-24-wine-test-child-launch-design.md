# Closed Unix launch boundary for Wine publication test children

## Authority, scope, and current evidence

This is a narrow extension of the approved Wine POSIX publication acceptance
harness, authorized by the user after the existing private-child launch mechanism
failed its first intact control. It does not redesign graph capabilities,
production publication, or the public validation capability.

The starting source revision is
`da22ba63099914bbe6d3c578ce07720947689583`. The latest actual reproduction,
`build/windows-ci-repro/20261023T141210326631Z-f33d822090dd443aa13dd973a2bd5459/`,
cross-built the PE test/support pair and passed admission. Its first publication
component failed with child lexical mask7 and `location-07/error0`; subsequent
components and full Wine were NOT RUN. The exact child override value was not
observed. Earlier reviewed fixture repairs resolved long-path inspection and
normal symlink-fixture teardown failures; they are not full acceptance evidence.

Stock Wine9 source separates the Windows startup environment from the Unix
environment inherited by the child loader. Its dynamic environment initialization
restores overrides from Unix `getenv`; DLL-root initialization likewise reads the
Unix environment. Thus Windows `GetEnvironmentVariableW` equality alone cannot
prove application-module root isolation. This source trace is not installed-runtime
proof. The intact copied-SO identity control remains mandatory.

## Chosen direction and alternatives

Extend the existing separately built test-support PE/Unix pair with one closed
synchronous Unix launch entry. Keep fixture construction and publication/refusal
assertions in the PE test. Use explicit Unix child environment and GNU
`posix_spawn` file actions, without modifying the multithreaded parent process.

Changing only the `CreateProcessW` override spelling cannot prove the intended
Unix loader environment. A new executable broker or Python per-child channel
would add an unnecessary process protocol and authority boundary. Neither is used.

The initial supported environment remains Linux x86_64, win64, matched distro
Wine9. GNU libc2.34 or later supplies the required cwd/closefrom spawn actions;
their actual availability is a host-native validation gate, not a fallback choice.

## Invariants

- Production publication ABI1/features3, graph APIs, stores, revision checks,
  exact bytes, and truthful committed outcomes remain unchanged.
- The outer components remain `cpp-022`, `cpp-002`, `store-write`, `store-read`,
  with120/120/30/30 seconds, child umasks0022/0002/0002/0002, and outer420.
- The five private cases remain control, missing-pe, bad-pe, missing-unix,
  bad-unix, in that order, within the existing60-second setup/run/cleanup sequence.
  Each child has at most10 seconds plus2 seconds for termination/reap.
- No parent environment, cwd, or umask mutation; no arbitrary executable, argv,
  environment map, runtime path, root path, callback, or timeout selector.
- Same owned Session/prefix/server; unchanged outer generation/grant/report
  accounting. Private descendants are not additional outer components.
- Owned copies only; never mutate the admitted overlay or installed Wine modules.
- No new public capability command, production subprocess, generic spawning
  service, daemon, retry, skip, ambient production-pair fallback, or deadline increase.
- Actual Wine/PE execution, application cross-build, and provisioning remain
  exclusively within `windows-ci-reproducer`. Frozen Facts artifacts stay unexecuted.

## Private test-support ABI

Test support advances to ABI2 and exact features7: identity1, fixture2, launch4.
Production ABI is unaffected. Identity entry0 retains its112-byte frame and actual
loaded-SO identity; fixture entry1 retains its12376-byte frame and fixture semantics.
Old support ABI1 cannot be admitted for execution. The builder may replace an
exactly recognized retired ABI1 output, but that is not execution compatibility.

Entry2 is `SRPT_ENTRY_LAUNCH`, forwarded through the existing test PE export and
Wine9 opaque Unix-table mechanism. `SrptLaunch` has size152, eight-byte alignment,
and these fixed-width fields/offsets, asserted in C and C++:

| Offset | Type | Field |
|---:|---|---|
|0|uint32_t|size|
|4|uint32_t|abi|
|8|uint32_t|action|
|12|uint32_t|case_id|
|16|uint64_t|root|
|24|uint8_t[32]|production_build_id|
|56|uint8_t[32]|support_build_id|
|88|uint64_t|production_device|
|96|uint64_t|production_inode|
|104|uint64_t|support_device|
|112|uint64_t|support_inode|
|120|uint32_t|phase (output)|
|124|uint32_t|os_error (output)|
|128|uint32_t|exit_code (output)|
|132|uint32_t|term_signal (output)|
|136|uint32_t|outcome (output)|
|140|uint32_t|reserved|
|144|uint32_t|remaining_ms (output)|
|148|uint32_t|reserved2|

Actions are CONFIGURE1 and RUN2. Configure requires case0 and a retained owned
TEMP context, with independently validated admitted production/support bindings.
RUN accepts case IDs1..5 and the retained fixture root; its production device/inode
is the intact case SO copy captured before intentional damage. There are no
caller-supplied executable, environment, root-path, or timeout fields.

Output and reserved fields must be zero on input. Both PE and Unix validate the
header/action/case; Unix additionally validates roots, bindings, state, and layout.
Outputs initialize before host work; `UINT32_MAX` exit code means no normal exit
was observed. Phases are input0/context1/layout2/runtime3/environment4/spawn5/
wait6/terminate7/reap8/complete9. Outcomes are unset0, completed1, exited-or-signalled2,
timed-out-and-reaped3, host-failure-no-outstanding-child4, ownership-uncertain5.

Malformed/replayed requests return INVALID_ARGUMENT; identity/pin mismatch returns
IDENTITY_MISMATCH; host/child failure returns UNSUCCESSFUL. SUCCESS means completed
configuration or a checked zero child exit. A negative case succeeds only when
its PE assertions verified the intended production refusal. All native exceptions
are contained; no ownership or native-width types cross the ABI.

## Pinned runtime and build provenance

The support builder consumes the already verified toolchain installation's native
Wine64 implementation, not merely the owning Session's logical Wine wrapper.
It nofollow-opens the canonical implementation, confirms Linux x86_64 ELF and
executable suitability, verifies the existing SHA256, and snapshots device/inode,
size, UID/mode, nanosecond mtime/ctime before and after reading. Ancestors must meet
the supported installed-path trust policy. Encode raw pathname bytes in generated
compile metadata without assuming UTF8 or interpolating unchecked C literals.

The implementation path, digest, snapshot, and fixed checkout/build-root derivation
are support-only build-ID inputs. Recheck runtime and toolchain identity before
installing the pair; preserve prior verified output on failure. Production builder
inputs, artifacts, manifest semantics, and independence from test inputs remain.

The Unix entry reopens the baked implementation with nofollow ancestor traversal,
compares the full snapshot, retains the descriptor, and rechecks descriptor/path
immediately before and after direct canonical-path `posix_spawn`. No PATH lookup,
runtime replacement, new hashing library, or home-grown crypto is needed. The
integrity argument is builder SHA validation plus trusted ancestors and stable
runtime tuple under the existing cooperative threat model, not filename equality.
Malicious root or timestamp forgery is not covered. An installation update requires
a rebuilt pair; source/build identity must not silently carry forward.

## Configuration, fixture ownership, and explicit environment

CONFIGURE is first, before sequence fixture creation/copying, and starts a native
monotonic60-second deadline. Its retained TEMP must match native TMPDIR. Verify the
owned fixed sibling relationship of prefix/tmp/data/cache, win64 architecture,
server selection, and the Windows TEMP handoff; do not inspect credentials or
invent a grant. Required runtime/server/session inputs are closed and validated,
never an arbitrary environment map.

Return floored remaining milliseconds. The PE records time before configure and
sets its conservative deadline to call-start plus returned remaining time; it
does not add configuration time back. Unix retains its own original deadline.

The first valid RUN binds one retained immediate TEMP child named
`record-publication-<decimal digits>`, owned0700 with descriptor/name-walk identity.
Subsequent calls require that same fixture and the exact next case. Concurrent,
replayed, skipped, reordered, or post-failure runs refuse. Do not hold the root
registry mutex while waiting for children; mark involved contexts busy and reject
mutation/release races until retirement. Ordinary fixture operations retain their
existing descriptor-relative behavior, including retained-parent tests.

Derive fixed case executable/cwd/module roots from the retained fixture, case ID,
and baked checkout layout. Require owned0700 directories, single-link owned regular
artifact copies, byte-exact comparison with independently validated original
artifacts, expected discovery copies and exactly the selected negative mutation.
Support comes from the independently bound support-only root, not a production
fallback. Revalidate launch acquisition paths without converting raw host bytes
through assumed UTF8.

Python publication validation supplies one private test-only
`SPACE_WINE_PUBLICATION_TEST_CRYPTO` handoff: exactly `b` or `n`, derived from the
two existing exact admitted backend values and overriding ambient input. Use one
canonical override format in both producer and child predicate:

`space_record_publication=b;space_record_publication_tests=b;bcryptprimitives=<b-or-n>;advapi32,cryptbase=b`

The child requires the owning handoff's exact backend, not either backend. No
legacy grouped-name alias is accepted. Build fresh Unix envp with empty PATH,
canonical overrides, exactly case production modules plus support-only modules as
raw Unix WINEDLLPATH entries, copied production binding, independent support
binding, owned session/server/temp handoffs, and the closed crypto value. Do not
inherit LD_* or arbitrary WINE* knobs, parent module roots, or observer descriptors.
Wine's stock installed loader/system-library paths are runtime dependencies,
distinct from these exactly two application roots.

Retain the PE CP_UNIXCP lossless conversion checks, PATH/cwd/private location and
dependency checks, production-not-preloaded assertion, two-root comparisons, and
independent copied-SO identity. The existing fixed no-argument store probe and
approved parent-owned base-dir exception are unchanged.

## Spawn, completion, and failure ownership

Use GNU posix_spawn, not fork followed by C++ work in the multithreaded parent.
Actions set stdin to /dev/null, child cwd through addfchdir_np on the verified case
descriptor, then close descriptors3+ with addclosefrom_np. Only stdout/stderr remain
for capture. Reset child signal mask/dispositions and create an owned process group.
Check initialization, file actions, attributes, spawn, and destruction results.

Require at least10s wait +2s termination/reap +1s cleanup reserve before spawning,
and recheck immediately before process creation. Absolute monotonic deadlines and
EINTR handling never restart a budget. After successful spawn, any failure must
terminate the owned group and reap the exact leader within the2-second reserve.
No second launch or retry is permitted. A nonzero/spawn/timeout failure permanently
ends the private sequence; later fixed cases do not run as substitutes.

Outcome5 is fatal to the PE parent: preserve the fixture, expose bounded numeric
diagnostics, and terminate without recursive deletion of potentially live files.
No unsuccessful retirement may authorize publication proof. Existing terminal
owned-session cleanup remains a backstop, not universal native-process quiescence.
Installed feasibility must prove that direct Wine64 supplies synchronous PE
completion; stock source or leader exit alone is insufficient.

## Validation and installed-runtime feasibility

Host validation executes the actual support Unix source, compiled with a fixed
baked inert runtime only for host tests. No arbitrary-runtime ABI or copied launch
algorithm is allowed. Cover runtime pins, GNU spawn cwd/fd/signal/group semantics,
fixed environment, unchanged parent state, exact ABI, malformed/replayed requests,
identity/root replacement, nonzero/signal/spawn failure, timeout/termination/reap,
EINTR, insufficient reserve, and uncertain-ownership classification. Pair input,
identity, manifest, and forwarder tests migrate support-only ABI/features atomically.

After validated checkpoints and independent review, ONLY windows-ci-reproducer
executes `python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .`
with14400000ms tool timeout and a fresh owned Session. The intact control is the
first blocking installed-feasibility measurement. Require exact location guards,
actual copied production SO identity distinct from the admitted original, exact
publication bytes/policy/hooks, control-completion observation and checked zero
native launch result. No environment assertion alone is loader proof.

Then require all four negatives under both umasks, both pinned reports, independent
store writer/reader, unchanged four-generation proof/grant promotion, full Wine
suite including its unchanged constraints deadline, and terminal cleanup. Failure
of synchronous completion, loader selection, encoding, reaping, or budget means
feasibility is not established; diagnose rather than relax guards or inflate bounds.
Any implementation change after a measured revision requires fresh reviewed actual
execution. Native Windows assertions stay intact and unexercised under Wine;
foreign-UID proof remains not-configured absent real suitable controls.

Run targeted native support/ABI tests and publication CTests, relevant complete
host-tooling gates, and inherited final native/host checks for the full contract.
No Fennel source/constraint changes are part of this extension. If that scope
changes, compile precedes constraints and focused tests as usual. PR CI and actual
merge-queue completion remain required after local gates; this design is not
acceptance evidence or permission to publish a failing branch.
