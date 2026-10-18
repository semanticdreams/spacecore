# Wine POSIX Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Real private persistent publication under local Wine without relaxing native policies or changing public outcomes.

**Architecture:** Prove the installed builtin-PE/Unix pair before production integration. Share one private phased operation across native publish and a synchronous Wine ABI; hooks stay in the caller. Add real host-policy tests and a separately bounded publication stage.

**Tech Stack:** C++17, MinGW, Linux shared libraries, matched Wine9 tools/headers, Python/pytest, CMake/CTest, existing Fennel stores.

**Authority:** `docs/specs/2026-10-17-wine-posix-publication-design.md` at `f2901da`. Debug-advisor `ses_eb4785684ffesgu7D1Ay0rKJJT` requires the plan and early actual compatibility proof.

## Global Constraints

- “Initial supported bridge scope is Linux x86_64 host, win64 PE and the matched, locally tested Wine9 mechanism.”
- “No parent chmod, ownership takeover or process-global umask changes.”
- “Keep the public `publish(destination, payload, hooks) -> Result` and binding/store outcomes unchanged.”
- “No hook, PE return, bridge round trip or adapter work separates final validation, rename and immediate committed assignment.”
- “No C++ objects/exceptions, native long/size_t/bool/wchar_t, CRT allocation ownership or callbacks cross it.”
- “Opaque contexts are destroyed by their creating module.”
- “Commit fields must be recoverable without allocating after commit.”
- “Keep existing public capability commands; do not introduce an arbitrary executable/filter/path converter.”
- “No installed Wine module is modified.”
- “Application death, memory corruption and power loss have no stronger guarantee than native publication.”
- Retain0700/0600 private creation, supported destination policy, retained handles, atomic rename and explicit unsupported-policy refusal. No production subprocess, daemon, journal, new outcome, reverse callback or compatibility alias.
- Load the unique builtin basename through fixed owned WINEDLLPATH. Neither absolute PE loading nor logical System32 naming proves Unix association.
- Actual Wine, provisioning and application cross-builds use `windows-ci-reproducer` only. Host unit/ABI tests may run locally.
- `make build` and guarded reproduction tool timeout14400000 ms (four hours); `make cmake`600000; complete six-module harness1800000.
- Preserve admission480, application1800, fast outer1920, cleanup backstop45 and existing per-case bounds. New fixed stages have separate bounds.
- No production Fennel/store/editor contract changes. Required failures block integration and require systematic diagnosis. No native-Windows-CI substitution, skipped checks or false PASS. PR CI remains the full integration gate, supplemented by actual local Wine.

### Worker/review checkpoints

Every task has two phases. Phase1 implements/tests WIP without staging or committing, returns `NEEDS_CONTEXT — review required before Phase2`, and writes its assigned ignored report plus complete BASE diff/manifest/hashes (include untracked contents). Reviewer inspects the full task. Fixes remain WIP until PASS. Only then authorize Phase2 exact reviewed-file commit, no extra edits or `git add -A`. Never report deferred Wine checks as passed. Capacity/conflicting instructions return before unauthorized edits/commits.

---

### Task 1: Matched Toolchain Without Unowned Runtime Queries

**Files:** Create `scripts/wine/publication_toolchain.py`, `scripts/tests/test_wine_publication_build.py`; modify `scripts/setup-windows-build-host.sh`, `scripts/opencode_windows_ci_repro.py`, `scripts/tests/test_windows_build_host_setup.py`, `scripts/tests/test_opencode_windows_ci_repro.py`.

**Interfaces:** `resolve_toolchain(repo: Path, runtime: dict | None = None) -> dict`; `verify_toolchain(identity: dict) -> None`. Runtime identity comes from immutable `Session.owner['tools']['wine']`. Absent runtime permits pure-host package discovery only. Canonical tool path/version/hash and header package/version/hash are recorded. These functions never launch Wine.

- [ ] **1. RED fixtures:** missing winegcc is reported without Wine/build calls; mismatched headers/tools or changed pinned files refuse. A simulated transaction replacing/upgrading/removing selected Wine must produce human-decision evidence before any elevated install.
  ```python
  fixture.remove_tool('winegcc')
  assert 'winegcc' in fixture.preflight()['evidence']['missing']
  assert fixture.wine_invocations == []
  fixture.simulate_selected_runtime_replacement()
  assert fixture.setup_host()['status'] == 'human_decision_required'
  assert fixture.sudo_install_calls == []
  ```
- [ ] **2. Run RED:** `python3 -m pytest -q scripts/tests/test_wine_publication_build.py scripts/tests/test_windows_build_host_setup.py scripts/tests/test_opencode_windows_ci_repro.py`. Use inert host tools, never real Wine.
- [ ] **3. Implement fixed resolution:** host C++17, MinGW, matching winebuild/winegcc and development headers; resolve distro logical tool names against selected installation/package ownership. Host compiler-tool version queries are not runtime release proof.
- [ ] **4. Guard setup before existing install can upgrade Wine:** simulate/pin the exact matching `wine64-tools`/`libwine-dev` transaction through setup-host. Reject unapproved sources and runtime replacement. No ad-hoc package commands or local installation in the fixture loop.
  This restriction concerns new Wine provisioning sources: preserve the existing separately established Microsoft/PowerShell bootstrap path without expanding it. Initial supported Wine development-package origin is the already configured official Ubuntu archive origin matching the selected distro Wine source/version; mirrors retaining signed Ubuntu origin metadata are equivalent. Do not add WineHQ/other sources or infer their approval from mere configuration. Unsupported origin or unavailable exact matching packages yields human-decision evidence, not a source edit or runtime upgrade.
- [ ] **5. GREEN focused fixtures; review and exact checkpoint:** `build(wine): guard matched publication toolchain provisioning`. Real provisioning is deferred to Task3.

### Task 2: Minimal Builtin Pair and Final Identity Entry

**Files:** Create `src/record_publication_wine_abi.h`, `scripts/wine/record_publication_bridge.c`, `scripts/wine/record_publication_unix_entry.cpp`, `scripts/wine/build_publication.py`; modify `scripts/tests/test_wine_publication_build.py`.

**Interfaces:** Fixed pair `modules/x86_64-windows/space_record_publication.dll` and `modules/x86_64-unix/space_record_publication.so`; PE export `int32_t WINAPI SpaceRecordPublicationCall(uint32_t entry, void *args)`. Entry0 is real final identity, not a publication stub. Feature1 identifies identity support; feature2 later identifies operation support.
```c
typedef struct {
    uint32_t size, abi;
    uint64_t challenge, echo;
    uint8_t pe_build_id[32], unix_build_id[32];
    uint64_t module_device, module_inode;
    uint32_t architecture, features;
} SrpIdentity;
```
ABI1 size112, offsets challenge8/echo16/PE-ID24/Unix-ID56/device88/inode96/architecture104/features108. `build_publication(repo: Path, session: prefix.Session) -> dict` writes fixed owned `build/wine-publication/`.

Shared constants: `SRP_ABI=1`, `SRP_FEATURE_IDENTITY=1`, `SRP_FEATURE_OPERATION=2`, initially `SRP_REQUIRED_FEATURES=SRP_FEATURE_IDENTITY`. Probe and clients use that single required-feature constant.

- [ ] **1. RED:** compile shared C/C++ layout assertions; fixtures check exact outputs, matching embedded IDs, refused extra/symlink/unowned output and no runtime version invocation.
  ```c
  _Static_assert(sizeof(SrpIdentity) == 112, "identity size");
  _Static_assert(offsetof(SrpIdentity, module_inode) == 96, "inode offset");
  ```
- [ ] **2. Implement exact Wine9 association:** inspect matching headers/loader sources; builtin basename discovery, own-HMODULE MemoryWineUnixFuncs query, checked eight-byte opaque handle, NTDLL __wine_unix_call. No host function-pointer cast, guessed SO fallback or DllMain initialization.
- [ ] **3. Implement entry0:** Unix echoes challenge and returns native SO device/inode (`dladdr` plus metadata) and build ID; PE supplies independently embedded ID. Catch Unix exceptions; unsupported entries error explicitly.
- [ ] **4. Fixed builder:** no arguments, required SPACE_WINE_SESSION_ID handoff, `prefix.load_session`, reuse pinned identity. Compile host SO/MinGW PE, matched `winebuild --builtin`, check architectures; inventory dependencies. Build ID hashes fixed inputs/tool/header identities. Seal schema1 `{version, abi, build_id, runtime, toolchain, files}`. Replace recognized owned output only.
- [ ] **5. GREEN host layout/builder fixtures; review and checkpoint:** `build(wine): add minimal builtin publication module pair`. Installed dispatch remains unproved.

### Task 3: Same-Process Admission and Early Actual Compatibility Proof

**Files:** Modify `scripts/wine/probe.c`, `scripts/wine/artifacts.py`, `scripts/opencode_windows_ci_repro.py`, `scripts/_windows_repro_evidence.py`, `scripts/tests/test_windows_wine_runtime.py`, `scripts/tests/test_opencode_windows_ci_repro.py`.

**Interfaces:** Existing60-second crypto process becomes fixed runtime-capability probe, no extra selector/process/generation. Seventh stage before admission: `timeout --kill-after=5s 900s python3 scripts/wine/build_publication.py`. Admission: `timeout --kill-after=5s 480s python3 scripts/wine/artifacts.py prepare-bootstrap`; private handoff-only action. Receipt schema3 adds `bridge:{abi,build_id,toolchain,files,identity}` and preserves all old bindings; schema2 execution refuses.

- [ ] **1. RED:** missing/mismatched module/echo/dev-inode/report gives contract exit20, never crypto-absence10. Test exact unchanged60/480 bounds, setup/generation count, old receipt refusal and complete seven-stage summaries/caps.
- [ ] **2. Probe entry0 first, then ProcessPrng in the same pinned Wine process.** Basename load through fixed owned WINEDLLPATH; both embedded IDs and Unix roundtrip required. Checked exclusive report `<owned tmp>/space-record-publication-identity.json`, max4096 bytes, compared by host code to inventoried SO device/inode/build identity. Stdout is progress, not authority.
- [ ] **3. Preserve crypto fallback:**10 only after successful pair proof and confirmed crypto absence;20 for bridge contract. Retry removes only verified fixed report and reruns both checks within its existing60-second launch.
- [ ] **4. Parent owns Session before builder/admission:** never default/unowned prefix; no inherited lock FDs. Composite public `artifacts.py prepare` runs separately bounded builder900/bootstrap480. Do not hold a build lock across child helpers that reacquire it. Reproducer invokes individual stages for separate evidence; one initialization/setup cycle.
- [ ] **5. Migrate all receipt/evidence/inventory producers and consumers together; native packages remain pair-free.** Ordinary publisher is unchanged in this task.
- [ ] **6. GREEN full six-module harness and Linux gate (commands Task10); full source review and exact checkpoint:** `feat(wine): admit the builtin publication bridge identity`.
- [ ] **7. Capability-only actual preflight/diagnosed setup-host/reproduce**, tool14400000. Record revision/hashes/entry0/SO identity. Matching packages that require runtime replacement or an unapproved source are a human infrastructure decision.
- [ ] **8. Reviewer consumes actual compatibility evidence before Task4.** Require actual Unix dispatch, not compilation/fixtures. Full Wine still exposes known old publisher failure; retain/diagnose it, never call the full run green. A different failure or absent pair proof must be investigated before production integration. No push/readiness claim.

**Observed SDK repair subtask:** After guarded installation of matching Noble9.0
development packages, preflight exposed the false requirement for noninstalled
`wine/unixlib.h`. Coordinated allowlist: `scripts/wine/publication_toolchain.py`,
`scripts/wine/build_publication.py`, `scripts/wine/record_publication_bridge.c`,
`scripts/tests/test_wine_publication_build.py`. First RED a realistic installed
public-header inventory without unixlib.h, plus missing/mixed-root refusal cases.
Resolver/builder require one inventoried matching Windows SDK root containing
winternl/windef/winbase, never weaken package/source/hash verification. PE removes
the private include and declares only the exact Wine9 uint64 handle and WINAPI
dispatch-pointer types; static-assert widths/alignment and guarded enum value1000,
query ReturnLength NULL as already required. Unix entry/identity payload unchanged.
Use a provenance comment, not wholesale LGPL header vendoring or source download.
Run Python compile and the build/setup/reproducer three-module gate with1800000ms,
native shared-layout checks and diff review; actual matching PE compile remains
capability-only. Independent review and exact checkpoint precede one guarded
preflight, then first guarded reproduction if PASS. No provisioning retry, ABI
fallback, new tool/API selector, native policy change or production integration.

### Task 4: Shared Phased Operation Without Backend Changes

**Files:** Create `src/record_publication_operation.h`, `tests/test_record_publication_operation.cpp`; modify `src/record_publication.cpp`, `CMakeLists.txt`.

**Interfaces:** Private `detail::Phase` start0/before_write1/before_security2/before_commit3/before_cleanup4/done5; `Reply{Phase phase; bool failed; string error;}`; `State{Phase phase=Phase::start; bool committed=false; optional<string> failure,cleanup_error;}`. Noncopyable PIMPL `Operation(path,string_view)`, `advance(const Reply&)->Phase`, `cancel(string_view)->Phase`, `state() const noexcept->const State&`. Own Attempt/copied payload. Public publish/header/binding stay unchanged.

- [ ] **1. RED transition/cancellation tests:** constructor/partial-prepare failures, every failed hook, primary+cleanup failure, stale/duplicate replies, copied payload, cancellation at each phase and nested independent calls.
  ```cpp
  Operation op(path, "new");
  check(op.advance({Phase::start, false, {}}) == Phase::before_write);
  check(op.advance({Phase::before_write, false, {}}) == Phase::before_security);
  check(op.advance({Phase::before_security, false, {}}) == Phase::before_commit);
  op.advance({Phase::before_commit, false, {}});
  check(op.state().committed && read(path) == "new");
  op.advance({Phase::before_cleanup, true, "cleanup fault"});
  check(op.state().phase == Phase::done && op.state().committed);
  ```
- [ ] **2. Implement only shared orchestration:** prepare→hook→write→hook→secure→hook→validate/commit/immediate latch→cleanup. Without owned workspace, no cleanup hook; with ownership request it once. Cleanup-hook failure never prevents cleanup. Keep both Attempt algorithms unchanged.
- [ ] **3. Native publish drives operation inline:** local Hooks, no locks across hooks, cancellation cannot resume publication, explicit cleanup reports errors; destructor is safeguard only.
- [ ] **4. GREEN:** `make build`; `ctest --test-dir build -R '^test_record_publication(_operation)?$' --output-on-failure`. Register focused target. Review/checkpoint `refactor(engine): make record publication explicitly phased`.

### Task 5: Production Operation ABI and Native Adapter

**Files:** Modify `src/record_publication_wine_abi.h`, `scripts/wine/record_publication_unix_entry.cpp`, `scripts/wine/build_publication.py`, `CMakeLists.txt`; create `src/record_publication_unix.cpp`, `tests/test_record_publication_abi.cpp`.

**Interfaces:** Preserve entry0. Entry1 consumes ABI1:
```c
typedef struct { uint64_t address, size; } SrpSlice;
typedef struct { uint64_t address, capacity, required; } SrpBuffer;
typedef struct {
    uint32_t size, abi, opcode, event;
    uint64_t context, sequence;
    SrpSlice path, payload, hook_error;
    SrpBuffer primary_error, cleanup_error;
    uint32_t reply, flags, status, reserved;
} SrpCall;
```
Size144; offsets context16/sequence24/path32/primary_error80/reply128. Constants `SRP_BEGIN=1`, `SRP_ADVANCE=2`, `SRP_SNAPSHOT=3`, `SRP_CANCEL=4`, `SRP_RELEASE=5`; `SRP_CONTINUE=0`, `SRP_FAILED=1`; flags `SRP_VALID=1`, `SRP_COMMITTED=2`, `SRP_DONE=4`, `SRP_PRIMARY_TRUNCATED=8`, `SRP_CLEANUP_TRUNCATED=16`. `int32_t srp_unix_call(SrpCall*) noexcept`. No Wine headers in portable core.

- [ ] **1. RED host ABI tests:** layout/version/length/reserved errors, invalid IDs, stale sequences, double release, multiple contexts, cancellation, tiny buffers, sticky postcommit snapshot.
  ```cpp
  // The test's successful begin/phase replies reach before-cleanup after commit.
  call.opcode = SRP_ADVANCE;
  call.event = 3; // before-commit, with the current valid sequence
  check(srp_unix_call(&call) == 0);
  check(call.flags & SRP_COMMITTED);
  call.opcode = SRP_SNAPSHOT;
  check(srp_unix_call(&call) == 0 && (call.flags & SRP_COMMITTED));
  ```
- [ ] **2. Implement module-owned validated context handles:** copy begin inputs, exact phase/sequence continuations, allocation-free/nonadvancing snapshot. Release cancels/finalizes without resuming, returns sticky state, destroys within originating module.
- [ ] **3. Catch every exception:** publish committed flags before diagnostics; bounded copies set required lengths/truncation, fixed fallback text on allocation failure. Never replay work for an error. No hook registration or fixture/fault commands in ABI.
- [ ] **4. SO compiles existing POSIX publisher and adapter; entry1 forwards and feature2 activates.** Change the single header constant SRP_REQUIRED_FEATURES to identity|operation so all newly built probes/clients require both. Exclude adapter from engine source glob; link only into Unix module/native ABI test.
- [ ] **5. GREEN build/publication-operation-ABI CTest; review/checkpoint:** `feat(engine): implement publication operation Unix ABI`. Actual new operation dispatch remains deferred.

### Task 6: PE Publication Client and Authority Checks

**Files:** Create `src/record_publication_wine.h`, `src/record_publication_wine.cpp`, `src/record_publication_wine_driver.h`, `tests/test_record_publication_bridge_driver.cpp`; modify `src/record_publication.cpp`, `scripts/wine/record_publication_bridge.c`, `CMakeLists.txt`.

**Interfaces:** `wine::detected()->bool`, `wine::publish(path,string_view,Hooks)->Result`. Private host-testable `drive(entry,host_path,payload,hooks,authority_check)->Result`; entry has `int32_t(uint32_t,void*)` semantics. No public contract change.

- [ ] **1. RED driver sequencing/nesting/cancel/postcommit recovery tests:** failed advance followed by committed snapshot must not become precommit error. Fake entry proves driver logic only.
- [ ] **2. Detect supported Wine9/win64 from loaded NTDLL wine_get_version; require proven entry0 and feature2.** Native Windows never loads pair and keeps strict backend. Use proven basename lookup/identity, retain module through release; no unproved absolute-path association.
- [ ] **3. Map with CDECL wine_get_unix_file_name, copy host bytes, HeapFree result.** Reject NUL/reserved/ADS/device/remote inputs. Mapping is acquisition, not retained authority.
- [ ] **4. Reject thread impersonation/restricted primary token/query failure before begin and after hooks.** Cancellation/cleanup on refusal, sticky commit retained. Hooks execute locally, never through Unix callback. Unrecoverable ABI corruption cannot fabricate recoverable noncommit.
- [ ] **5. GREEN native driver/ABI/operation tests.** CMake includes client in Windows engine and standalone target, excludes it on POSIX; direct publisher linking must resolve correctly. Review/checkpoint `feat(engine): delegate Wine publication to the POSIX bridge`. Installed client/path/token behavior is deferred.

### Task 7: Real Host-Policy Cases and Fresh-Process Store Probe

**Files:** Modify `tests/test_record_publication.cpp`, `scripts/wine/build_publication.py`, `scripts/build-windows.sh`, `scripts/tests/test_wine_publication_build.py`, `CMakeLists.txt`; create `tests/record_publication_wine_support.h`, `tests/record_publication_wine_support_pe.c`, `tests/record_publication_wine_support_unix.cpp`, `assets/lua/tests/wine-record-publication.fnl`.

**Interfaces:** Separate test-only `space_record_publication_tests.dll/.so` pair, fixture-relative host inspection/mutation only. Fixed Fennel `write()/read()` no path arguments. C++ fixed `<TEMP>/space-record-publication-report.json` schema1: backend/build ID/Unix dev-inode, category statuses common/host-policy/mapping-authority and native-windows:not-exercised; foreign UID probe not-configured or passed.

- [ ] **1. RED backend-aware selection:** run common cases through production public API; Wine uses actual host-policy assertions, not `_WIN32` DACL assumptions. Preserve native NT tests, explicitly unexercised under Wine.
- [ ] **2. Separate test module observes actual modes at hooks:** before-write anchor/workspace0700, record0600/size0; after-write0600/exact bytes. Reject unchanged0750/0770 anchors; test descriptor ambiguity, UID/GID/mode preservation, unsupported metadata, links, final mutation and retained parents. No fixture commands enter production ABI.
- [ ] **3. Exercise binary/empty/NUL/multichunk/Unicode/long paths, mapping/missing-parent/reserved forms, hook/cancel/nested/release/committed cleanup, missing/bad modules and token changes.** Bad-module fixtures are owned copies, never mutate admitted overlay. Foreign UID proof requires configured actual identities/positive controls; otherwise not-configured, never fake PASS or sudo.
- [ ] **4. Actual store writer:** use normal StringEntityStore/LinkEntityStore constructors, fixed IDs, ordinary persistent defaults. Capture old revision before in-place mutation; listeners assert updated cache/revision before one notification. Exact method contracts must match current canonical modules.
  ```fennel
  (local first (strings:create-entity {:id "wine-persistent-text" :value "before"}))
  (local old-revision first.revision)
  (local updated (strings:replace-text first.id "  after 雪\r\n\n" old-revision))
  (assert (not= updated.revision old-revision))
  (links:create-entity {:id "wine-persistent-link" :source-key "source" :target-key "target"
                       :metadata {:old-revision old-revision :value "before"}})
  (links:update-entity "wine-persistent-link"
                       {:metadata {:old-revision old-revision :value "after"}})
  ```
- [ ] **5. New reader process reopens exact text/link, rejects stale old revision with conflict/not-committed, proves persisted bytes unchanged.** No filesystem injection. Emit bounded markers; propagate failure nonzero.
- [ ] **6. Fixed cross-build targets:** `space space-cli test_record_publication`. Builder stages test pair; native release/ZIP/installer excludes both pairs/test executable. Checked report is written only after mandatory cases pass.
- [ ] **7. GREEN native build, Fennel compile→constraints→focused persistence, native focused CTest and builder fixtures; review/checkpoint:** `test(wine): cover real host-private publication and persistence`. Actual Wine categories remain deferred.

### Task 8: Bounded Publication Evidence Support

**Files:** Modify `scripts/_windows_repro_evidence.py`, `scripts/tests/test_opencode_windows_ci_repro.py`.

**Interfaces:** Dormant fixed eighth-stage support (`wine-publication`), activated Task9. Four ordered components cpp-022/cpp-002/store-write/store-read with deadline/umask/actual launch/hard-deadline/nullable raw status. Private observer accepts four launch/result pairs plus final `{version:1,passed:bool,bridge_build_id:hex64,foreign_uid_probe:not-configured|passed}`; fast retains two messages.

Component deadlines120/120/30/30, umasks0022/0002/0002/0002; publication outer420. Launch frame is `{event:'launch',component:<fixed ID>,launched_monotonic:<finite float>,hard_deadline_monotonic:<finite float>}`; result is `{event:'result',component:<same ID>,command_returncode:<int>}`; terminal frame is `{event:'publication-result',version:1,passed:<bool>,bridge_build_id:<hex64>,foreign_uid_probe:<closed enum>}`. No extra IDs/messages or implicit status inference.

- [ ] **1. RED:** wrong/duplicate/out-of-order IDs/deadlines, truncated frames/missing result, stdout status spoofing. Only private observations establish command status.
- [ ] **2. Extend parser/summary without changing live execution/auth:** reuse counters plus `publication` progress from `Wine publication:`. FAIL/native fatal/nonzero/incomplete/missing report prevents PASS despite helper0.
- [ ] **3. Preserve16 MiB streams,4000-character tails,4 KiB lines,48 KiB encoded response,4 MiB ledger and existing fast fatal clock.** Worst-case eight stages, EOF/held writers/storage errors must retain truth and caps.
- [ ] **4. Fixed prepare parent can use persist=False capture into exclusive session-owned logs with identical observation checks, not a generic public command.** GREEN full reproducer fixtures; review/checkpoint `feat(wine): add bounded publication-stage evidence`.

### Task 9: Purpose Grants and Independently Bounded Publication Execution

**Files:** Modify `scripts/wine/prefix.py`, `scripts/wine/artifacts.py`, `scripts/opencode_windows_ci_repro.py`, `scripts/tests/test_windows_wine_prefix.py`, `scripts/tests/test_windows_wine_runtime.py`, `scripts/tests/test_opencode_windows_ci_repro.py`; create `scripts/wine/publication_validation.py`.

**Interfaces:** `validate_publication(session)->int`, `configuration(session,purpose)->dict`, `authorize_application(session,capture_record)->None`. Owner schema4; replace authorized boolean with authorized_for(None/publication/application) and grant(None/hex32), retain nonce/generation/stopped_generation/ended. Phase created/prepared/publication-consumed/publication-checked/publication-passed/application-consumed. Receipt schema4 adds authorization(purpose/grant/stopped_generation) and nullable publication proof, retaining schema3 bridge/bindings; older execution refuses, no aliases.

**New final fixed stage** before wine-fast: `timeout --kill-after=5s 420s python3 scripts/wine/publication_validation.py`.

| Component | Pinned Wine argv after executable | Seconds | Child umask |
|---|---|---:|---:|
| cpp-022 | overlay/test_record_publication.exe |120|0022|
| cpp-002 | overlay/test_record_publication.exe |120|0002|
| store-write | overlay/space-cli.exe -m tests.wine-record-publication:write |30|0002|
| store-read | overlay/space-cli.exe -m tests.wine-record-publication:read |30|0002|

- [ ] **1. RED atomic producer/consumer migration:** bootstrap grants publication, validation consumes grant before any launch, succeeds/stops into publication-checked with no grant. Only complete passing parent capture+reports+stopped generation permits fresh application grant. App consumes it/ends; replay/wrong purpose/stale generation/corruption/failed teardown/revival refuse.
  ```python
  bootstrap(session)
  assert state()['authorized_for'] == 'publication'
  publication(session)
  assert state()['phase'] == 'publication-checked' and state()['authorized_for'] is None
  authorize_application(session, complete_passing_capture)
  assert state()['authorized_for'] == 'application'
  fast(session)
  assert state()['ended'] and state()['authorized_for'] is None
  ```
- [ ] **2. Fixed child umask:** private Session.launch child_umask option accepts only these fixed launches; subprocess child support, never parent mutation. Five-second command escalation and stop/wait10/15 plus escalation give355 seconds, fitting420 with65 overhead. Preserve480/1800/1920/45, one wineboot/setup cycle.
- [ ] **3. No-argument helper requires owned handoff, consumes authorization durably, emits actual private launch/result data and removes observer FD from PE environment.** Validate fixed C++ reports as bounded owned regular files with current IDs/dev-inode; verified stale reports removed before next component. No stdout authority.
- [ ] **4. Both entry paths:** reproducer captures new stage then authorizes; public prepare owns separately bounded builder900/bootstrap480/publication420, uses same checks then authorizes. Failures end session/backstop45; no composite inside480 or1920 and no lock reacquisition deadlock.
- [ ] **5. Complete state/receipt/bounds/table/log/metadata/summary/fixture migrations together.** Generations follow actual launches, not historical11. New stages are only the two named fixed additions; no public selectors/capability changes.
- [ ] **6. GREEN full prefix/runtime/reproducer fixtures including storage failure/unrelated-session survival; review/checkpoint:** `feat(wine): require purpose-bound real publication validation`.

### Task 10: Final Actual Gates and Canonical Documentation

**Files:** Create `docs/dev/features/record-publication.md`; modify `docs/dev/notes/windows-wine-build-and-test.md`, `scripts/tests/test_opencode_windows_ci_policy_docs.py`. No graph/API/outcome migration.

- [ ] **1. Clean committed current base:** guarded origin fetch/evaluate origin/main; permitted merge/conflicts through implementer/reviewer. Record exact runtime-tested HEAD.
- [ ] **2. Native build; Fennel compile then constraints; focused native publication/operation/ABI/driver CTest and persistence tests.** Direct runs use absolute assets, both canonical Fennel paths, disabled audio, skipped keyring and external XDG. Parse repairs isolate enclosing form then compile again.
- [ ] **3. Full gates:**
  ```bash
  SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH="$(pwd)/assets" make test
  python3 -m pytest -q scripts/tests/test_windows_wine_prefix.py scripts/tests/test_windows_wine_runtime.py scripts/tests/test_windows_build_host_setup.py scripts/tests/test_opencode_windows_ci_repro.py scripts/tests/test_windows_ci_speedups.py scripts/tests/test_opencode_windows_ci_policy_docs.py
  python3 -m pytest -q scripts/tests/test_wine_publication_build.py
  ```
  Full native14400000, six modules1800000. Add affected package-exclusion tests. Report each gate separately.
- [ ] **4. Whole-branch review, then capability-only actual execution** with14400000 tool timeout. Require actual final entry0/1, both umasks, separate writer/reader, correct grants/generations/cleanup and full Wine success. Earlier compatibility proof is not final publication success.
- [ ] **5. Diagnose every required failure:** retain command/status/capture/ledger/revision/tree; reviewed fixes, no speculative cascade skips or push while required failures remain.
- [ ] **6. Document measured phases, ABI/loader/authority/lifetime, host policy, matched tools, eight stages, bounds/grants, early versus final evidence and platform gaps.** Explicitly supersede old native-substitution/six-stage wording. No stronger crash guarantee. Record exact measured source revision if docs-only commit follows.
- [ ] **7. Focused doc tests/text/diff review; independent review and exact checkpoint:** `docs(wine): document real POSIX publication and validation`. Finish only with clean tree, agreed local/Wine gates and PR CI green.

## Acceptance and Self-Review

Actual Wine production writes/reopens exact bytes; actual0700/0600 and unsafe0750/0770 checks; retained policy/namespace/atomicity/committed cleanup; nested/cancelled contexts; verified selected pair; one initialized session and independent bounded validation; unchanged native NT assertions explicitly unexercised. Foreign-UID proof only when configured. Out of scope: Wine fork/ACL relaxation, subprocesses, new outcomes, production Fennel changes, native certification,32-bit/WoW64, remote filesystems, hostile same-UID protection and power-loss guarantees.

Coverage: Tasks1–3 prove mechanism before Tasks4–6 integrate; Task7 real behavior, Task8 evidence, Task9 atomic live authorization, Task10 final actual gates. ABI sizes/offsets, entry0 persistence, basename loading and owned runtime queries are explicit. No unresolved product choice requires a native runner. Installed-tool/loader facts are measured gates, not claims. Tool timeout14400000 is four hours, not fourteen. Every mutation uses implementer/reviewer/exact-checkpoint ownership.
