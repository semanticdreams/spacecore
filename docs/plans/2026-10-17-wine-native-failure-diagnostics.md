# Wine Native Failure Diagnostics and Input Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the reproduced InputDialType boundary defect and obtain an isolated, actionable Windows failure result instead of opaque errors and a debugger wait.

**Architecture:** Required native input validation, followed by three focused diagnostic components with independent review: readable errors/security metrics, owned roots/crash policy, and bounded fatal capture. Extend existing lifecycle/capture ownership rather than add another runner. One subsequent guarded run defines the next source fix from its first decoded failure and security metrics.

**Tech Stack:** C++17, existing sol2/Lua/Fennel, Python/pytest, Wine9, GNU timeout; existing dependencies.

## Global Constraints

- Authority: `docs/specs/2026-10-17-wine-native-failure-diagnostics-design.md` at `db576e4` and named retained evidence.
- Preserve app modules, assertions, Windows skips, case120/240, child bounds and full1800; do not raise suite budget again.
- Existing init90/probe60/smoke60/stop10/wait15/kill-after5/admission480/fast1920/backstop45 remain; add registry30+5 and one fatal-report grace30 only.
- Keep backend DACL predicate EXACTLY unchanged: owner equality, protected requirement, raw byte equality and subsequent ACE checks. Instrument role/booleans/sizes/counts, never SID/ACL bytes/payload.
- Generated verified owned prefix only. No HOME/default/shared-state cleanup, arbitrary registry access, new skips, feature disabling, idle watchdog, global sol2 flags or stale-userdata lifetime redesign.
- Four existing capability commands unchanged; actual app Wine/cross-build through windows-ci-reproducer only. No raw Wine, permission/profile/environment bypass.
- User's fresh internal API guidance applies: refactor and migrate repo consumers without compatibility aliases. Do not ask human approval for ordinary evidence-backed fixes.
- Workers never stage/commit/push. Independent review PASS precedes supervisor checkpoint.
- Native Windows/macOS proof and historical Linux SIG remain separate; no new crash is assumed identical without causal evidence.

## Evidence

Run `build/windows-ci-repro/20261017T021559707002Z-290576cffcc94012a145d36380114595/`: build/package/coldinit/admission passed;2167RUN/1779PASS/387FAIL then factory crash0x140269c6d at337s, WineDbg waited to1800. Cleanup0/0 and capture complete. Read-only matching-binary disassembly maps the fault to unchecked `as<InputState&>()`, not adapter update.

`input-binding-evidence.md` records six invalid-input Linux child SIGSEGVs and foreign-userdata acceptance, with existing valid tests4/4. No Linux PC captured, original Wine argument unknown. Grouped failures include63 private-policy mismatches,130 opaque tables and likely fixture cascades. Do not preemptively repair guessed producers or relax security.

### Task 1: Guard the Required InputState Factory

**Files:**
- Modify: `src/lua_dial_type.cpp`, `assets/lua/tests/test-dial-type.fnl`
- Create/Test: `assets/lua/tests/dial-type-invalid-argument.fnl`
- Modify: `docs/sdk/modules/dial-type.md`, `docs/dev/subsystems/input.md`

**Interfaces:**
- Existing `dial-type.InputDialType(input-state)` remains the canonical factory.
- Invalid argument errors contain `InputDialType requires a non-null InputState userdata`.
- Child module `tests.dial-type-invalid-argument:main()` accepts only child-local `SPACE_DIAL_TYPE_INVALID_CASE` selecting seven fixed cases; marker appears only after all rejection assertions pass.

- [ ] **1. Add RED child-isolated tests.** Separate parent cases for omitted/nil/table/boolean/number/string/foreign DialType userdata. Canonical runtime resolver and process.run launch native children with90s bounds. Require exit0, no signal/timeout, `pcall=false`, descriptive error and exactly one case marker. Do not use an incorrectly accepted adapter or let a child crash terminate parent.

  ```fennel
  (local (ok err) (pcall DialTypeModule.InputDialType nil))
  (assert (not ok))
  (assert (= (type err) :string))
  (assert (string.find err "InputDialType requires a non-null InputState userdata" 1 true))
  (print (.. "DIAL_INVALID_OK " case-name))
  (io.flush)
  ```

- [ ] **2. Guard before unsafe extraction.** Require valid full userdata and `is<InputState>()` before reading native data; then extract InputState pointer, reject null, and only then form reference/construct adapter. No unchecked as-reference before check. No global sol2 configuration or ownership/lifetime behavior change; stale typed objects are not claimed detected.
- [ ] **3. Retain the valid contract.** All four existing real-engine input/update cases remain unchanged and pass. Child assertions, not diagnostic-parent exit0 alone, establish rejection. Update SDK/subsystem error and caller-lifetime documentation.
- [ ] **4. Validate and review.** Native rebuild, touched Fennel compile, constraints and complete test-dial-type. Retain actual old child signal/acceptance RED and post-fix completion markers. Independent review before checkpoint; no real Wine until Task3.

### Task 2: Readable First Failures and Unchanged Security Metrics

**Scope:** Implement only the formatter/runner/native-metric portions listed below (original steps5–7). Files: new `assets/lua/tests/error-format.fnl`; existing runner.fnl, test-runner.fnl, runner-regression-cases.fnl; src/record_publication.cpp, tests/test_record_publication.cpp; harness cleanup note. Interfaces: `format-error(err)->string` bounded2048 and `require_private(policy,role)` diagnostics. Build/compile/constraints/focused runner/native CTest before independent review. No prefix or fatal-capture source edits in this task.

The remaining shared diagnostic contract is retained below; Task3 and Task4 own its other components. This decomposition follows a worker's pre-edit capacity report and changes no behavior/security requirement.

**Files:**
- Modify: `scripts/wine/prefix.py`, `scripts/wine/artifacts.py`, `scripts/_windows_repro_evidence.py`, `scripts/opencode_windows_ci_repro.py`
- Create: `assets/lua/tests/error-format.fnl`
- Modify/Test: `assets/lua/tests/runner.fnl`, `assets/lua/tests/test-runner.fnl`, `assets/lua/tests/runner-regression-cases.fnl`
- Modify/Test: `src/record_publication.cpp`, `tests/test_record_publication.cpp`
- Modify/Test: `scripts/tests/test_windows_wine_prefix.py`, `scripts/tests/test_windows_wine_runtime.py`, `scripts/tests/test_opencode_windows_ci_repro.py`, `scripts/tests/test_opencode_windows_ci_policy_docs.py`
- Modify: `docs/dev/notes/windows-wine-build-and-test.md`, `docs/dev/notes/test-harness-cleanup.md`

**Interfaces:**
- `Session.binding()->dict` is the single internal owned identity/root representation; migrate both producers/callers.
- `Session.environment()` includes owned XDG_DATA_HOME/XDG_CACHE_HOME and TMP/TEMP/TMPDIR.
- `Session.launch(argv,kind,extra_env=None,stdout=None,stderr=None)->int` preserves durable generation accounting and default outer-stream inheritance.
- `configure_crash_reporting(session)->None` applies/verifies only fixed debug-policy values; failure prevents admission/app.
- `tests.error-format.format-error(err)->string`: allowlisted, encoded-bound2048, no arbitrary stringification.
- Windows `require_private(policy,role)` uses literal role anchor/attempt/record; acceptance predicate unchanged.
- Ledger adds bounded first-fatal/report deadline, termination and known app-command status distinct from debugger/helper/stage/cleanup statuses.

- [ ] **1. Add owned data isolation.** Create/validate0700 data/cache/tmp roots and inode identities under Session. Both admission/helpers and app use the same roots; remove fixed shared XDG override. Supply Windows-compatible absolute TEMP/TMP and host POSIX TMPDIR resolving to the owned tmp. Do not clean/read earlier shared data; do not claim isolation explains DACL errors. Update internal binding builders/fixtures together and reject stale incomplete ownership.
- [ ] **2. Configure only fixed Wine9 crash policy.** After successful wineboot, before API probe, launch three `/reg:64` writes through selected Wine `reg.exe`: HKLM `Software\Microsoft\Windows NT\CurrentVersion\AeDebug` Debugger REG_SZ `winedbg --auto %ld %ld`, Auto REG_SZ1; HKCU `Software\Wine\WineDbg` ShowCrashDialog REG_DWORD0. Bound each30+5 and count each generation.
- [ ] **3. Verify only these values.** Three fixed `/v` queries with bounded regular-file capture compare exact types/data (DWORD0/0x0 equivalent). No enumeration/raw hive read. Any write/query/verification error ends authorization and cleans owned prefix. Document this narrow owned-policy exception, not a general registry interface. Preserve all case/selection/feature policy.
- [ ] **4. Test registry/isolation ownership.** Fake tools verify exact argv/order/bounds/pinned prefix, private root identities, inherited-data override/two-session separation, substituted-root refusal and configuration-failure cleanup. Generation assertions count real added launches. Receipt/context binding represents actual owned roots and policy; no obsolete configuration alias.
- [ ] **5. Format errors safely.** Pure helper reads raw scalar code/message/outcome/current-revision in fixed order; cap complete encoded output2048 with visible truncation/control escaping. No result traversal, payload/sensitive data, metatable getters/tostring or formatting exception replacing original failure. Unsupported/cyclic/non-scalar values get bounded type-only descriptions.
- [ ] **6. Wire before traceback.** protected-call normalizes before debug.traceback, including no-traceback path; use same representation for body/load/teardown/combined-shutdown logs. Preserve actual original failure propagation where relevant, counts, timeout latch/hooks, Engine shutdown and module selection. Isolated runner cases prove actual log wiring and non-leakage, not only pure helper calls; deliberate child failures remain captured.
- [ ] **7. Instrument unchanged native policy.** Append literal object role, owner equality, expected/actual protection and DACL equality, byte lengths and ACE counts to rejection. Do not modify predicate/order or print descriptors/SIDs. Update all callsites; native tests assert safe metrics and unchanged unsafe-policy rejection.
- [ ] **8. Detect genuine fatal banners.** Only wine-fast root stderr, newline-terminated bounded Wine grammar with fault address/thread/starting-debugger shape. Wrong stream/stage, quoted/embedded/ordinary text and hidden expected-child failures must not trigger. Latch first fatal and report clock once, never reset/extend it beyond existing1800 application deadline.
- [ ] **9. Bound report handling.** Continue draining both streams for automatic trace/detach; completion may occur earlier. Apply one30s grace even through early EOF/live leader or exited leader/held pipes. Carry explicit private application launch/hard-deadline observation from owning helper, not shutdown overhead inference. Expiry uses existing scoped teardown/backstop, preserves partial trace and real statuses; unknown app status remains unknown. Root fatal prevents PASS even if helper/debugger returns0.
- [ ] **10. Exercise fatal/error edge cases.** Host fixtures cover split/repeated banner, false-positive negatives, both trace streams, fatal+exit0, report hang, near-hard-deadline crash, early EOF, held writers, interruption and persistence failure. Retain caps/48KiB, owner cleanup and unrelated-session survival. Structured error tests cover hostile metatables, invalid/large/cyclic values and private-result sentinels through real isolated runner wiring.
- [ ] **11. Validate and review.** Build native first; compile/constraints/Fennel runner + native publication CTest and full six-module harness suite below. Update canonical notes and retain historical observations. No actual Windows rerun until review/commit.

### Task 3: Owned Roots and Automatic Noninteractive Crash Policy

**Scope:** Implement only original steps1–4 and their prefix/artifact/runtime-fixture/docs portions. Files: prefix.py, artifacts.py, test_windows_wine_prefix.py, test_windows_wine_runtime.py, affected mechanical binding-consumer fixtures and the Wine note. Interfaces: Session.binding/environment/launch and configure_crash_reporting. Reg/value/path-conversion setup is bounded/owned and fail-closed. Data/cache/tmp isolation is not claimed to cure the DACL mismatch. Source review and the complete six-module host gate precede checkpoint. Do not implement fatal deadlines or change native security policy.

### Task 4: One-Shot Bounded Fatal Report Capture

**Scope:** Implement only original steps8–11 and evidence/wrapper/application-launch-observation/fixture/docs portions after Task3. Files: _windows_repro_evidence.py, opencode_windows_ci_repro.py, artifacts.py launch observation, test_opencode_windows_ci_repro.py and relevant policy-doc guards/notes. Retain all existing caps/lifecycle/cleanup contracts. Validate fake native-fatal versus ordinary text, exact first grace deadline/hard bound, early EOF/held writers/storage failure and unrelated-prefix survival; review independently. No source binding or DACL policy edits.

### Task 5: One Guarded Observation and Next Source Contract

**Files:** generated owned logs/ledger; update `docs/dev/notes/windows-wine-build-and-test.md` after execution only.

**Interfaces:** consume reviewed/committed Tasks1–2 and green local gates; produce actual first structured failure/mismatch and measured crash behavior, not an invented timeout fix.

- [ ] **1. Run full Linux gate after reviews** because native binding and shared runner changed; command below, then clean/current-origin evaluation.
- [ ] **2. Dispatch one exact guarded reproduce**, tooltimeout14400000: `python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .`. No raw Wine, selectors, budget override or automatic retry.
- [ ] **3. Reconcile actual revision/payload, owned roots/policy, first decoded error, role/boolean/size metrics, RUN/PASS/FAIL, native fatal/report and independent app/helper/cleanup results.** Diagnostic clarity is not full-suite success.
- [ ] **4. Specify next fix only from measured facts.** Menu defaults, graph panels Engine restoration and board registry are investigation candidates, not approved cascade fixes. No preemptive DACL relaxation/emulation label. Review any documentation change before commit.

## Validation Ladder

`make build` before native/Fennel checks, timeout14400000; actual CMake configuration if needed timeout600000. Then touched-file tools.fennel-check or make fennel-check, constraints, focused tests. Nearest-enclosing-form/named-helper repair for authoring feedback; no gate bypass or new exemptions.

```bash
export SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data SPACE_DISABLE_AUDIO=1
export SPACE_ASSETS_PATH="$PWD/assets"
export FENNEL_PATH="$PWD/assets/lua/?.fnl;$PWD/assets/lua/?/init.fnl"
export FENNEL_MACRO_PATH="$FENNEL_PATH"
make fennel-check
make constraints
./build/space -m tests.test-dial-type:main
./build/space -m tests.test-runner:main
ctest --test-dir build -R '^test_record_publication$' --output-on-failure
python3 -m pytest -q scripts/tests/test_windows_wine_prefix.py scripts/tests/test_windows_wine_runtime.py scripts/tests/test_windows_build_host_setup.py scripts/tests/test_opencode_windows_ci_repro.py scripts/tests/test_windows_ci_speedups.py scripts/tests/test_opencode_windows_ci_policy_docs.py
SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH="$PWD/assets" make test
```

Use explicit600000 for focused chains and14400000 for Make build/full gates. Source/metadata/clean-current-origin and whole-branch review plus applicable green PR CI remain integration gates. Native Windows/macOS and historical Linux signal proof remain separate. No human decision blocks ordinary fixes/internal refactors; escalate only a genuine change to agreed behavior/security guarantees, unavailable infrastructure or unsafe history—not fresh API shape.
