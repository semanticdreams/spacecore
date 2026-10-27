# Closed Wine Publication Test-Child Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a pinned, closed Unix launch boundary for the five existing publication-test children without changing production APIs or validation budgets.

**Architecture:** Extend the existing separate test-support pair; retain PE fixture construction and publication assertions. Embed verified native-runtime metadata, construct explicit Unix child environments, and use checked GNU posix_spawn ownership. Installed-runtime feasibility is a blocking fresh full-capability measurement, never inferred from source or host models.

**Tech Stack:** C++17, C11, Python standard library, pytest, CTest, Linux x86_64, matched Wine9/win64, glibc2.34+.

## Global Constraints

- Authority: `docs/specs/2026-10-24-wine-test-child-launch-design.md`, commit7e2a932.
- “Production publication ABI1/features3, graph APIs, stores, revision checks, exact bytes, and truthful committed outcomes remain unchanged.”
- “The outer components remain `cpp-022`, `cpp-002`, `store-write`, `store-read`, with120/120/30/30 seconds, child umasks0022/0002/0002/0002, and outer420.”
- “The five private cases remain control, missing-pe, bad-pe, missing-unix, bad-unix, in that order, within the existing60-second setup/run/cleanup sequence.”
- “Each child has at most10 seconds plus2 seconds for termination/reap.”
- “No parent environment, cwd, or umask mutation; no arbitrary executable, argv, environment map, runtime path, root path, callback, or timeout selector.”
- “Same owned Session/prefix/server; unchanged outer generation/grant/report accounting.”
- “Owned copies only; never mutate the admitted overlay or installed Wine modules.”
- “No new public capability command, production subprocess, generic spawning service, daemon, retry, skip, ambient production-pair fallback, or deadline increase.”
- “Actual Wine/PE execution, application cross-build, and provisioning remain exclusively within `windows-ci-reproducer`. Frozen Facts artifacts stay unexecuted.”
- Existing no-argument store probes and approved parent-owned base-dir exception remain unchanged.
- No new hashing dependency/implementation, production source change, broad file split, probe-helper change, or `.opencode/**` edit.
- Ordinary implementers validate, self-review, and checkpoint before independent review. Review covers complete recorded BASE..HEAD and each FIX_BASE..HEAD; checkpoints are not approval. Preserve unrelated state; no publication/history rewrite authority.
- Native host fixtures are not Wine proof. Actual new PE binaries/application cross-builds run only through the capability; host PE-source adapter models and C/C++ layout compilation are ordinary native tests.

## Fixed Interfaces and Decisions

### Support runtime metadata

Builder helpers:

```python
def _capture_launch_metadata(repo: Path, session: prefix.Session, identity: dict) -> dict: ...
def _render_launch_header(metadata: dict) -> bytes: ...
def _recognized_test_output(output: Path, *, for_replacement: bool = False) -> tuple | None: ...
```

Metadata schema1 records checkout raw path as hex, implementation/server pins, and
ancestor records. File fields are path_hex, sha256, device, inode, size, uid, mode,
mtime_ns, ctime_ns; ancestor fields are path_hex, device, inode, uid, mode from root
through the file parent. Select native Wine64 from verified toolchain
`installation.implementation.file`, server from immutable Session owner.

Production capture requires nofollow absolute acquisition, root-owned ancestors and
files, no group/other write, regular non-set-ID executable files, executable access,
and existing verified SHA256. Wine64 must be Linux x86_64 ELF, not wrapper script.
Bound paths to4095 raw bytes and runtime reads to64MiB. Check stable tuples around
hashing and traversal, repeat before installing pair output. Host test fixtures use
separate baked inert pins without relaxing production capture policy.

Generate only private staging `srpt_launch_config.h`. Encode byte arrays, not
unchecked C literals/assumed UTF8. Support toolchain metadata adds `launch` and
`launch_header_sha256`; both and all source inputs contribute to support build ID.
Render before computing ID; header does not include ID. Production build/manifest
remain independent. Runtime launch compares baked trusted ancestor/file snapshots
and descriptor/path identity before/after direct canonical-path posix_spawn; no
PATH lookup or runtime SHA dependency. Cooperative installation updates invalidate
the pin and require rebuild; malicious root/timestamp forgery is outside scope.

### Test ABI and configuration

Support only: ABI2/features7. Production remains ABI1/features3. Entry0 identity112
and entry1 fixture12376 retain layouts/semantics. Entry2 uses spec SrptLaunch152,
alignment8, offsets:

```text
size0 abi4 action8 case_id12 root16 production_build_id24 support_build_id56
production_device88 production_inode96 support_device104 support_inode112
phase120 os_error124 exit_code128 term_signal132 outcome136 reserved140
remaining_ms144 reserved2_148
```

CONFIGURE1 accepts case0/retainedTEMP; RUN2 accepts case1..5/retainedfixture.
Outputs/reserved zero on input; initialize outputs before work; UINT32_MAX exit
means no normal exit. Fixed phases0..9/outcomes0..5 and NTSTATUS meanings are exactly
the spec. No request executable/environment/path/timeout fields. Add binding header
`src/record_publication_wine_binding.h` and transitive production ABI header to
support TEST_INPUTS and fixture inventories; use pure existing codec unchanged.

Active support recognition rejects ABI1. Only builder replacement/cleanup recognizes
an exactly verified retired ABI1 using its original build-ID calculation. Support
manifest version1/top-level shape stays, support abi becomes2. No execution alias.

CONFIGURE compares request bindings to independent native environment bindings;
support binding must match actual loadedSO identity and embedded ID. Baked checkout
derives original production/support/overlay roots. It starts native monotonic60s
before setup and captures only closed inputs; PE uses call-start + floored returned
remaining_ms, never adds configuration time back.

Required native inputs: WINEPREFIX, WINEARCH, WINESERVER, XDG_DATA_HOME,
XDG_CACHE_HOME, TMPDIR, TEMP, TMP, SPACE_WINE_WINDOWS_TMP, both publication bindings,
SPACE_WINE_PUBLICATION_TEST_CRYPTO. Require owned0700 session siblings and32lowerhex
session name, win64, baked server selection, retainedTEMP matching nativeTMPDIR,
TEMP/TMP equal Windows temp handoff. No prefix-content/credential inspection.

Only optional inherited inputs: HOME, LANG, LC_ALL, LC_CTYPE, DISPLAY,
WAYLAND_DISPLAY, XDG_RUNTIME_DIR; each bounded4095, NUL-free. Path-valued HOME and
XDG_RUNTIME_DIR must be absolute; supplied XDG_RUNTIME_DIR nofollow/currentUID0700.
Child envp is this admitted set plus fixed empty PATH, exact overrides, two derived
raw application module roots, copied production binding and original support
binding. No LD_* / arbitraryWINE* / parent roots / observerFD.

Python sets test crypto exactly b or n from existing exact admitted backend values.
Producer and child require the single canonical format:

```text
space_record_publication=b;space_record_publication_tests=b;bcryptprimitives=<b-or-n>;advapi32,cryptbase=b
```

No grouped alias or acceptance of the other backend. Preserve CP_UNIXCP lossless
checks. Stock installed Wine loader paths are separate runtime dependencies, not
extra application module roots. Same fixture, exact ordered cases, one configuration
and one sequence per process; no reset/recovery. Busy roots reject mutation/release;
do not hold registry mutex across child execution.

---

### Task 1: Pin Native Runtime and Prove GNU Spawn Prerequisites

**Files:** Modify `scripts/wine/build_publication.py`; test `scripts/tests/test_wine_publication_build.py`; read toolchain resolver and prefix owner contracts. Generate only private staging header.

**Interfaces:** Produce capture/render helpers and support-only metadata/hash inputs above. Keep build_publication(), production-only fixtures, existing main call order and CLI unchanged.

- [ ] **1. Write runtime-pin RED tests:** implementation versus wrapper, scripts/wrong ELF architecture, symlink ancestors/leaves, unsafe UID/mode, stale hash/tuple, raw-byte paths, source/pin change during build; no fixture Wine execution.
- [ ] **2. Run RED:** `python3 -m pytest -q scripts/tests/test_wine_publication_build.py -k 'support and runtime'`. Require missing-contract failures, not missing tools/Wine.
- [ ] **3. Implement deterministic capture/render/hash integration:** bounded records, header encoding, before-install toolchain/pin recheck, prior valid output preservation on every failure.
- [ ] **4. Test actual GNU spawn actions** using an inert native ELF and driver: /dev/null stdin, addfchdir_np(cwd fd), addclosefrom_np(3), empty signal mask/default dispositions, new group. Check closed sentinel/server-like fd, exact cwd, signal/group state, stdout/stderr preserved.
- [ ] **5. Assert unchanged parent environment/cwd/umask** using snapshots and /proc/self/status (do not call umask). Keep synthetic compiler-protocol metadata distinct from tests of production trusted capture refusals.
- [ ] **6. Run focused GREEN and existing support build-integrity controls; self-review/checkpoint/review.** Report actual host prerequisite results, not installed Wine feasibility.

### Task 2: Add ABI2 and Closed Unix Launch Ownership

**Files:** Modify `tests/record_publication_wine_support.h`, `_pe.c`, `_unix.cpp`; `scripts/wine/build_publication.py`; `tests/test_record_publication.cpp` support-model constants only; test existing publication-build, Wine-runtime and reproducer pytest files.

**Interfaces:** Consume generated pins/codec/root registry; produce SrptLaunch, SRPT_ENTRY_LAUNCH2 and `int32_t launch(void*) noexcept`. Keep64root slots/nonrecycled IDs, identity mapping proof, ordinary retained descriptor operations.

- [ ] **1. Add ABI/forwarder RED:** C/C++ size/alignment/every offset; zero input rules/action/case bounds; exact entry forwarding/refusal before dispatch. Run `python3 -m pytest -q scripts/tests/test_wine_publication_build.py -k 'support and (abi or forwarder or launch)'`.
- [ ] **2. Implement header/assertions/PE and Unix dispatch**, exception containment and initialized outputs. Update support-only abi/features/mutants atomically (extra7 becomes15); production features unchanged.
- [ ] **3. Implement retired-output replacement recognition** with exact original ID, ownership/inventory/file-set checks; active admission always ABI2 only, tampering refuses before compilation.
- [ ] **4. Add configuration/sequence RED:** wrong TEMP/siblings/server/architecture/bindings/actualSO; configure replay; skipped/reordered/changed fixture; insufficient reserve; release/mutation race.
- [ ] **5. Implement one closed configuration and conservative deadline.** Validate required/optional inputs and fixed original layouts independently; no arbitrary environment capture.
- [ ] **6. Bind first RUN to retained immediate TEMP fixture** `record-publication-<digits>`, owned0700/descriptor/name-walk identity. Derive case paths and validate exact owned single-link copies, discovery bytes, selected missing/bad mutation, unchanged build/support IDs, and intact-copy pre-damage binding.
- [ ] **7. Construct exact raw envp and fixed argv** with baked implementation, fixed PE basename/privatecase arg/cwd; canonical owner crypto, two private roots, no ambient loader/observer state.
- [ ] **8. Implement checked GNU spawn:** init/actions/attributes/destruction all checked; /dev/null, fchdir, closefrom3; reset signals/group; recheck runtime descriptor/path and13s remaining reserve immediately before launch.
- [ ] **9. Implement wait/retirement:** exact-leader waitpid/absolute monotonic deadline, EINTR no reset; after spawn every failure kills owned group and reaps within2s. Failure ends sequence. Uncertain retirement outcome5, never false success; do not release busy roots while child can exist.
- [ ] **10. Exercise ACTUAL Unix source as host ELF** with separately baked fixed inert runtimes: success/nonzero/signal/spawn refusal/timeout, malformed/replay/root replacement, no reserve, runtime pin change. Fake runtime never executes PE bytes; ABI has no runtime test selector.
- [ ] **11. Isolated native fault tests** use narrow syscall/linker wrappers, not ABI fault opcodes, for EINTR/clock/kill/reap/action failures. Check no fd leak or parent environment/cwd/umask change; recoverable return has no outstanding owned child; uncertain outcome retains evidence.
- [ ] **12. Run focused support suite and native publication target/CTest**, self-review/checkpoint and independent full task review. Actual PE/Wine compilation remains capability-only.

### Task 3: Route Existing PE Cases and Crypto Handoff

**Files:** Modify `tests/test_record_publication.cpp`, `scripts/wine/publication_validation.py`, canonical record-publication page and Wine note; test existing publication-build/runtime/reproducer/policy-docs pytest files.

**Interfaces:** Preserve wine_loader_children()/wine_child() obligations. Add:

```cpp
SrptLaunch launch_request(uint32_t action, uint32_t case_id, uint64_t root,
                         const Binding& production, const Binding& support);
void invoke_launch(SrptLaunch& frame, Fixture* fixture);
```

- [ ] **1. Integration RED:** same four outer launches/bounds/umasks/generation delta4/report schema; failing publication blocks later components and promotion; ambient crypto replaced from exact verified backend.
- [ ] **2. Set Python crypto handoff:** builtin backend maps b, existing exact native variant maps n; any other backend refuses, no substring inference.
- [ ] **3. Configure FIRST in child sequence** using retainedTEMP/call-start time; set conservative local deadline before overlay inspection/fixture creation/copying.
- [ ] **4. Replace superseded child_environment/CreateProcessW/process-handle lifecycle only.** Keep independent sources, byte-copy validation, five-case order, original overlay inventory and per-case copiedSO identity captured before mutation.
- [ ] **5. Send zeroed closed requests** with retained fixture and exact case. Validate native status/outcome; outcome5 preserves fixture, flushes numeric failure and terminates current process without unwinding, with _Exit fallback. No debugger-dependent abort or unsafe deletion.
- [ ] **6. Preserve all child guards** and make overrides exact owner-selected canonical form; no aliases. Keep copied dependency locations, production-not-preloaded, two raw roots, CP_UNIXCP roundtrips and support-only actualSO identity.
- [ ] **7. Preserve publication assertions:** intact control proves actual copiedSO identity, exact nine-byte payload, four hooks/policy/clean anchor; negatives prove intended loader/association refusal, zero hooks, unchanged destination/object, no workspace/cache/fallback.
- [ ] **8. Emit bounded causal observations:** fixed numeric control-completion only after its assertions; parent case/phase/outcome/errno/exit/signal only after checked native result. No paths/bindings/env/payload dump or PASS authority from markers alone.
- [ ] **9. Keep explicit cleanup inside60s** and only after confirmed retirement. Check remaining reserve while copying and deadline after checked cleanup.
- [ ] **10. Update canonical docs** with supportABI2/productionABI1 distinction, implementation pin/Unix environment/GNU prerequisite, unchanged budgets, stock loader dependencies, installed-feasibility still UNPROVED.
- [ ] **11. Run narrow host/native checks GREEN; checkpoint/full independent review.** No actual capability run before source pass.

### Task 4: Establish Installed Feasibility Through Full Capability

**Files:** No source edits; inspect fresh ledger and complete streams only.

**Interfaces:** Consume reviewed committed Tasks1–3; produce exact measured runtime evidence or diagnosed blocker, no new command/mode/stage.

- [ ] **1. Dispatch windows-ci-reproducer only:** `python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .`, timeout14400000ms, fresh Session/unchanged internal bounds; no standalone child/ended-owner reuse/provisioning.
- [ ] **2. Intact control is FIRST blocking measurement:** all location guards, copiedSO identity distinct from original, bytes/policy/hooks, control completion preceding checked native zero exit. Windowsenv equality alone is insufficient.
- [ ] **3. Read full streams and correlate ordering:** assertions/completion, native result, then fixture cleanup; early leader exit/outstanding fixture users/wrong loader/encoding/reap uncertainty means feasibility NOT established.
- [ ] **4. Same wrapper must finish** four negatives under both umasks, both pinned reports, independent stores, delta4/proof/grant promotion, full Wine including unchanged constraints deadline, terminal cleanup.
- [ ] **5. Record revision/session/run/pins/statuses/deadlines/EOF/truncation/cleanup.** No marker-only PASS, no old Facts authority refresh.
- [ ] **6. Required failure invokes systematic debugging**, validated checkpoint/review before any fresh rerun. Escalate only concrete unsupported host/runtime/scope decisions; never relax checks or enlarge budgets.

### Task 5: Final Relevant Gates, Measured Docs, and Integration

**Files:** Canonical record-publication page/Wine note; tests in seven host-tooling modules and four existing publication CTest targets; no production/graph API edits.

**Interfaces:** Consume exact reviewed/measured revision; produce evidence-qualified docs and existing PR/merge-queue handoff.

- [ ] **1. Python syntax:** py_compile touched builder/validation and four touched pytest modules.
- [ ] **2. Native freshness:** make build timeout14400000; make cmake timeout600000 if needed. Build four publication targets explicitly with `cmake --build build --target test_record_publication test_record_publication_operation test_record_publication_abi test_record_publication_bridge_driver -- -j1`.
- [ ] **3. Four CTests:** `SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH="$(pwd)/assets" ctest --test-dir build -R '^test_record_publication(_operation|_abi|_bridge_driver)?$' --output-on-failure`.
- [ ] **4. Complete host modules:** `python3 -m pytest -q scripts/tests/test_wine_publication_build.py scripts/tests/test_windows_wine_prefix.py scripts/tests/test_windows_wine_runtime.py scripts/tests/test_windows_build_host_setup.py scripts/tests/test_opencode_windows_ci_repro.py scripts/tests/test_windows_ci_speedups.py scripts/tests/test_opencode_windows_ci_policy_docs.py`. Modules may run separately under unchanged1800000ms tool allowance; incomplete combined runs are not PASS. Route any actual PE execution/build nodes through capability, never silently skip and claim complete coverage.
- [ ] **5. Inherited full native contract gate:** make fennel-check first, then standard isolated/disabled-audio/skipped-keyring make test timeout14400000. Constraints precede tests transitively; preserve all existing case limits and counts.
- [ ] **6. Update docs from actual measured evidence** (revision/run/host-prerequisites/control feasibility/full publication/fullWine/cleanup/Windows limitations/foreignUIDnotconfigured). Any executable delta after measurement requires reviewed fresh actual execution.
- [ ] **7. Self-review/checkpoint/independent review docs**, git diff --check, clean tree; fetch origin/main and safe-merge/review/revalidate if needed. Do not rebase/force-push or absorb unrelated state.
- [ ] **8. Follow existing default integration policy only when local gates green:** PR CI is the full integration gate; push/PR/protection/queue via capability agents, poll through actual mergedAt. Queue handoff/control feasibility/localPASS are not final integration success.

## Self-Review and Non-Goals

Spec sections map to runtime pins(Task1), exact ABI/roots/process ownership(Task2),
PE integration/environment/diagnostics(Task3), actual installed feasibility(Task4),
and relevant/full validation/measured docs/integration(Task5). No unresolved product
choice is carried into code; a measured unsupported host property follows Task4's
bounded escalation rule. No generic spawn, new public verb, production/graph/store
change, provisioning, installed module/prefix mutation, aliases, hashing dependency,
budget increase, skip, WoW64/nativeWindows certification, malicious-root defense,
or universal process-quiescence claim is authorized.
