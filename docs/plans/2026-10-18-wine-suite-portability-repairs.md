# Wine Suite Portability Repairs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair established portability defects, measure unproven failures, and require a zero-failure actual Wine run.

**Architecture:** Independently review subsystem repairs and behavior-preserving diagnostics before one combined guarded full-fast run. Gate List fixture changes on actual operands and constraints optimization on a measured causal mechanism. Existing Wine publication Tasks7–9 remain separate.

**Tech Stack:** C++17, CMake, embedded Lua/Fennel, sol2, existing TrezorCrypto sources, Python/pytest, CTest.

## Global Constraints

- Preserve privacy, atomic publication, committed-outcome truth, strict filesystem APIs, and domain-owned graph data. No publication ABI/client/core changes or permission relaxation.
- Preserve the existing 120-second case deadline, outer1800 application deadline, 10000-instruction latched timeout hook, teardown, and all other guarded budgets.
- No skipped gates, native-Windows-CI substitution, arbitrary actual selectors, new public commands, production subprocess, compatibility aliases, algorithm copying, new downloads, or speculative optimization.
- Actual Wine/application cross-build/provisioning uses only `windows-ci-reproducer`. Do not browse prefix internals or execute raw Wine.
- No production clock semantics change. Unavailable native Terminal registration may omit only that optional widget; registered failures remain explicit.
- Do not claim the List normalization hypothesis proven before measuring actual operands. Last-started constraints phase is not itself root cause.
- Every source task: Phase1 **unfinished unstaged WIP**, full report/diff/manifest/hashes, independent reviewer/fix loop, then Phase2 exact reviewed commit without extra edits. No worker reads this whole plan: globals, shared validation, and assigned task only.
- Preserve historical evidence; supervisor alone updates `.superpowers/sdd/wine-posix-publication/progress.md`. Unexpected failures require systematic debugging/advisor before repair.
- All remaining failures block final integration. Missing measurements are an investigation gate, not automatically a human decision.

## Evidence and File Ownership

Starting clean source: `71753a34d342ffb1102d09b589a3bd4c452d14d2`. Actual run: `build/windows-ci-repro/20261018T230423286902Z-9af10940063442b4b3095c435abd0418/`, 4565run/4535pass/30fail. Independent reviewer passed only the ordinary String/Link publication milestone. Advisor `ses_eaea715c2ffeZOnuZ6j11w6Hsc` requires this bounded follow-up; evidence brief is the newest remaining30 section of the progress ledger.

Accounting: Terminal1; List observer5; packaged documentation1; timestamp1; Workflow2; SHA4 plus External Unit MCP15; constraints timeout1. Do not infer repaired names from aggregate subtraction. Terminal/docs/sleep/missing executable diagnoses are established. Workflow cache canonicalization is source-proven but not the demonstrated cause of both Wine assertions. List operands and constraints hot operation remain unknown.

Each task below owns its explicit file list. Native hashing is a focused binding plus provider-selection module; test-only progress formatting is separate from production constraints workload. Do not restructure unrelated large files. Read-only references confer no edit authority.

## Shared Validation and Handoff

Use runtime environment:

```bash
export SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data
export SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH="$(pwd)/assets"
export FENNEL_PATH="$(pwd)/assets/lua/?.fnl;$(pwd)/assets/lua/?/init.fnl"
export FENNEL_MACRO_PATH="$FENNEL_PATH"
```

After CMake edits: `make cmake` tool timeout600000, then `make build` timeout14400000. Build is also the runtime freshness prerequisite whenever needed. Fennel order: `make fennel-check` → `make constraints` → focused real runner. A module vector below uses:

```bash
xvfb-run -a ./build/space -c '((. (require :tests.runner) :run-modules) {:name :wine-portability :modules [:tests.test-workflow-store]})'
```

Substitute the exact task vector; prove cases executed and process failures propagate. No system Lua/Fennel or unsupported compile oracle. Parse errors: inspect enclosing form, simplify nesting, recompile first. Targeted checks by default; broad source gate in Task7 is justified by registration/startup/linkage/pipeline risk.

Seven host modules, tool timeout1800000:

```bash
python3 -m pytest -q scripts/tests/test_windows_wine_prefix.py scripts/tests/test_windows_wine_runtime.py scripts/tests/test_windows_build_host_setup.py scripts/tests/test_opencode_windows_ci_repro.py scripts/tests/test_windows_ci_speedups.py scripts/tests/test_opencode_windows_ci_policy_docs.py scripts/tests/test_wine_publication_build.py
```

Full Linux: standard environment plus `make test`, timeout14400000. Actual capability action: `python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .`, timeout14400000 (four hours), internal bounds unchanged; preflight through the same capability when needed. No silent retries.

Task artifacts under `.superpowers/sdd/wine-posix-publication/`: `suite-portability-task-N-report.md`, `suite-portability-task-N-review.diff`, `suite-portability-task-N-manifest.md`, `suite-portability-task-N-hashes.sha256`, referenced command/exit logs. Record BASE/branch/status/index, meaningful RED/GREEN, coverage rationale, constraint impact and deferred proof. Include complete new-file contents, not just tracked diff. Preserve prior rounds. Reviewer covers every path; controller checks hashes/exclusive scope/full diff/empty index before Phase2. Evidence-only tasks need review but no artificial commit. PR CI/current-origin checks remain later integration requirements.

### Task 1: Absence-Only Terminal Registration

**Files:** modify `assets/lua/main.fnl`, `assets/lua/tests/test-reference-lifecycle-composition.fnl`, `docs/dev/notes/windows-wine-build-and-test.md`.

**Interfaces:** consume native `package.preload["terminal"]` and existing startup/sidebar fixtures; preserve public Main/sidebar APIs and widget ownership.

- [ ] Add startup RED cases that save/restore preload and loaded Terminal/widget entries even after errors: genuinely absent preloader permits startup and retains unrelated sidebar/Space Agent behavior; registered throwing loader preserves sentinel error; unusable registered module fails; real registration retains Terminal.
- [ ] Run compile→constraints→`[:tests.test-reference-lifecycle-composition]` and capture absence failure before production edit.
- [ ] Guard only Terminal require/register with `(not (= (rawget package.preload "terminal") nil))`. Keep sidebar creation, agent registration and pending-state restoration outside. No OS switch, dummy module or broad pcall fallback.
- [ ] Validate compile→constraints→`[:tests.test-reference-lifecycle-composition :tests.test-main-events :tests.test-hud-extended-sidebar]`; retain startup-provider and teardown assertions. Document availability boundary; independent review/checkpoint.

#### Task1 Constraint Refinement

Advisor `ses_eae88b5c3ffe1N7QMdCExPbxYy` confirmed that the required guard adds a real depth8 finding (limit7), increases the existing module measure2242→2243 and relocates15 existing line-keyed findings. Preproduction constraints passed; this is not environmental noise. Add only `assets/lua/constraints/baseline-data.fnl` to Task1's allowlist; no rule/module extraction is authorized.

- [ ] Separate the lazy Terminal builder callback from the registration table using a named local builder. Preserve require/error timing during registration and defer widget construction until the callback runs. Keep the exact raw-preloader absence guard and unrelated sidebar behavior. Measure nesting; new depth8 must disappear in code, never be baselined.
- [ ] Reconcile existing baseline entries one-to-one using actual diagnostics and unchanged/reduced measures; record old/new locations/fingerprints. No bulk regeneration, new exception, dropped unrelated debt or rule/limit change.
- [ ] **Explicit bounded debt approval:** the supervisor permits updating only the existing main module-length measure to the exact observed minimum increase attributable to the necessary availability guard/named-builder separation, at most8 lines over2242. This is intentional measured debt, not mere relocation: a focused availability repair does not justify unrelated restructuring of the2242-line main module. Report the exact delta and justification separately for independent review. Stop if the increase exceeds8 or any other finding worsens. Do not minify/remove unrelated whitespace to game measures.
- [ ] Preserve initial failing artifacts; run compile→whole constraints→the exact unfiltered three-module vector above. Reviewer covers all four paths and verifies both nesting repair and narrow baseline continuity/debt approval before checkpoint. Later broad/actual gates unchanged.

### Task 2: Canonical Documentation Resource Integrity

**Files:** modify `scripts/wine/artifacts.py`, `scripts/tests/test_windows_wine_runtime.py`, `scripts/tests/test_opencode_windows_ci_repro.py`, `docs/dev/notes/windows-wine-build-and-test.md`. Read-only canonical `docs/dev/features/entity-type-catalog.md` and `assets/lua/tests/test-builtin-graph-extensions.fnl`.

**Interfaces:** consume existing package/clean-native/overlay/configuration/inventory/receipt lifecycle. Produce private `REQUIRED_RESOURCES: tuple[str, ...]` initially containing `docs/dev/features/entity-type-catalog.md`, and `verify_required_resources(path: Path) -> None` checking safe regular canonical bytes. No schema change.

- [ ] Fake repository fixtures copy the actual canonical file; never duplicate the executable example. RED tests cover exact bytes/location/inventory/receipt, missing/symlink source, missing/tampered output even after resealing, overlay corruption refusal before launch, and independent cleanup.
- [ ] Add `ROOT / "docs"` to overlap protection. Copy fixed resources to matching relative paths before native sealing. Verify canonical-byte identity in native verification and admitted overlay configuration; existing recursive inventory/receipt owns them. No whole docs tree, cwd fallback or post-seal mutation.
- [ ] Run `python3 -m py_compile scripts/wine/artifacts.py scripts/tests/test_windows_wine_runtime.py scripts/tests/test_opencode_windows_ci_repro.py` and both Python test modules; compile→constraints→`[:tests.test-builtin-graph-extensions]`.
- [ ] Document fixed resource/sealing and review/checkpoint. Existing Fennel test must still extract and execute the single canonical document.

### Task 3: Deterministic Second-Precision Timestamp Test

**Files:** modify `assets/lua/tests/test-agent-layer.fnl`, `docs/dev/notes/test-harness-cleanup.md`; production session module read-only.

**Interfaces:** existing create/update/save session and second-precision `os.time`; no production API change.

- [ ] Replace only shell-delay scenario with scoped zero-argument test clock. Save `os.time`; use protected body; restore before cleanup/rethrow.
- [ ] Create/save at1700000000, same-second save stays equal; advance to1700000001, update/save; assert unchanged creation time, exact update time and persisted status/timestamps. Do not directly assign the session timestamp. Prove restoration after throwing body.
- [ ] Compile→constraints→`[:tests.test-agent-layer]`; no shell delay/polling. Document exception-safe clock testing; independent review/checkpoint.

#### Task3 Measured Baseline Continuity

Advisor `ses_eae49660cffeITY3eJ72dyD06e` confirmed all18 blocking diagnostics: eight unchanged findings paired with stale line entries, plus existing module growth paired with its exceeded baseline. Add only `assets/lua/constraints/baseline-data.fnl` as the third Task3 path. The supervisor explicitly approves the measured test module increase2848→2886 (+38) for the deterministic scoped clock, exact same/later-second persisted assertions and throwing-body restoration regression; this bounded test-only growth does not justify unrelated restructuring.

- [ ] Relocate exactly the eight report-listed existing findings by+37, preserving identity/measures/limits and source continuity; update only the existing module measure to2886. No new exceptions, changed limits, unrelated baseline entries, production-session edits or formatting tricks.
- [ ] Preserve pre-refinement evidence; compile→whole constraints→the exact unfiltered agent-layer runner. Independent review covers all three paths, measured growth and unchanged production session; actual combined runtime proof remains pending.

### Task 4: Workflow Canonical Cache Owner

**Files:** modify `assets/lua/workflows/store.fnl`, `assets/lua/tests/test-workflow-store.fnl`, `docs/dev/notes/windows-wine-build-and-test.md`.

**Interfaces:** preserve `WorkflowStore({:base-dir string})` and `get-default(opts?)`; use existing `fs.absolute` normalization.

- [ ] RED equivalent-spelling regression: raw root, absolute root and `fs.join-path(root, ".")` must return same store/cached definition, retain subscription and emit exactly one mutation signal; truly different root has separate owner/output.
- [ ] Resolve explicit/appdirs request, assert required data, canonicalize before cache comparison and constructor input. Keep direct constructor normalization. No extra cache, manual case folding or alias.
- [ ] Two original default-root tests compare exactly to `fs.absolute(root)`, retaining persisted-content/path and different-root assertions. Source cache bug alone is not proof both Wine failures repaired.
- [ ] Compile→constraints→`[:tests.test-workflow-store :tests.test-reference-lifecycle-composition]`; document, review/checkpoint.

### Task 5: Native Binary-Safe SHA-256

**Create:** `cmake/sha256.cmake`, `src/lua_sha256.h`, `src/lua_sha256.cpp`, `tests/test_lua_sha256_binding.cpp`, `tests/cmake/sha256-backend/CMakeLists.txt`, `docs/dev/notes/native-sha256.md`.
**Modify:** `CMakeLists.txt`, `src/lua_runtime.cpp`, `assets/lua/repo/sha256.fnl`, `assets/lua/tests/test-repo-sha256.fnl`, `external/wallet-core/trezor-crypto/crypto/memzero.c` (include spelling only), `scripts/wine/artifacts.py`, `scripts/tests/test_windows_wine_runtime.py`, `scripts/tests/test_opencode_windows_ci_repro.py`.

**Interfaces:** `void lua_bind_sha256(sol::state&)`; native `require("sha256").hash(string) -> 64 lowercase hex`; target `space_sha256_backend`. Existing Fennel `repo/sha256.hash`/`hash-file` signatures remain canonical.

**Backend decision:** reuse existing vendor `crypto/sha2.c`/`memzero.c`, headers `include/TrezorCrypto`; no algorithm source copy/download. SHA source/header BSD notice and bundled crypto MIT notice plus memzero attribution must be preserved/distributed. Explicit TestBigEndian definitions avoid header little-endian default. Existing real `TrezorCrypto` target when present is sole provider; otherwise compile exactly two C files. Keep existing Windows wallet-off policy. Validate both branches, not whole optional wallet product.

- [ ] Native strict-type/vector RED tests: reject absent/nil/number/boolean/table/userdata without coercion; explicit string byte lengths. Known vectors:

  | Input | Digest |
  |---|---|
  | empty | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
  | abc | `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad` |
  | one NUL | `6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d` |
  | abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq | `248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1` |
  | bytes0–255 | `40aff2e9d2d8922e47afd4648e6967497158785fbd1da870e7110266bf944880` |

- [ ] Shared CMake module after optional wallet setup: target-private LITTLE_ENDIAN1234/BIG_ENDIAN4321/detected BYTE_ORDER. Target-present interface links real TrezorCrypto without second implementation; target-absent static library exactly two vendor files. No global definitions/includes or duplicate-symbol suppression. Change only memzero `<Windows.h>` to `<windows.h>` for case-sensitive MinGW.
- [ ] Binding checks `sol::object.get_type()` string, obtains counted bytes, calls existing `sha256_Data` into65bytes and returns first64; no strlen. Register preload unconditionally in existing base bindings. Link engine/native test and register CTest.
- [ ] Fennel wrapper asserts string content/path, delegates native hash and binary-safe `fs.read-file`; missing/read errors propagate. Test exact binary vectors/file equivalence, wrong types/missing file, and throwing Process.run seam proving subprocess not used; restore seam on errors.
- [ ] Isolated provider fixture uses real Lua/sol2/TrezorCrypto subdirectory (TW_TREZOR_TESTS=OFF), test-local `SPACE_SHA256_TEST_WALLET_TARGET` ON/OFF, same production CMake module/binding/test. Assert exclusive provider sources, resolve SHA and memzero. Configure `cmake -S tests/cmake/sha256-backend -B build/sha256-backend-off -DSPACE_SHA256_TEST_WALLET_TARGET=OFF`, build/CTest there; repeat in `build/sha256-backend-on` withON. Configure600000/build14400000. Inspect actual link evidence.
- [ ] Native SHA page includes full verbatim notices/provenance/API/provider/endian/include-case patch, install to `share/doc/space/native-sha256.md`; add canonical page to Task2 required resources and integrity fixtures.
- [ ] Fresh configure/build, `ctest --test-dir build -R '^test_lua_sha256_binding$' --output-on-failure`, compile→constraints→`[:tests.test-repo-sha256 :tests.test-external-unit-mcp :tests.test-external-unit-mcp-reload-evidence]`, Task2 Python modules. Account all4SHA/15MCP including stale-hash message and JSON response; diagnose new symptoms without unapproved MCP API changes. Review/checkpoint.

### Task 6: Fixless Operands and Bounded Constraints Progress

**Modify:** `assets/lua/constraints/runner.fnl`, `assets/lua/constraints/source.fnl`, `assets/lua/constraints/facts.fnl`, `assets/lua/tests/test-constraints-default-run.fnl`, `assets/lua/tests/test-constraints-source.fnl`, `assets/lua/tests/test-constraints-facts.fnl`, `assets/lua/tests/test-constraints-runner.fnl`, `assets/lua/tests/test-list-entities.fnl`, `docs/dev/constraints.md`, `docs/dev/notes/test-harness-cleanup.md`.
**Create:** `assets/lua/tests/constraint-progress.fnl` (test-only formatting).

**Interfaces:** optional `opts.observer(event)` in Runner.run-target, passed to `Source.discover(target, observer?)` and `Facts.extract(records, observer?)`, preserving returns. Test-only `ConstraintProgress.create({:now-ms fn :write fn :detail-phase string|nil}) -> observer`.

- [ ] Fixless List observations under existing SPACE_TEST_TIMINGS=1: actual fixture prefix/write path, fs.absolute equivalents, raw predicate and canonical intended-destination result for all five scenarios. At most2observations/scenario,12escaped lines/module,1024encoded bytes/line; only generated fixture paths, no runtime-private data. Keep roots/counters/assertions unchanged.
- [ ] Observer nil fast path allocates no event tables/clocks. Begin/end Runner discover/facts/select/rule/baseline/summarize; Source scan/read/parse and Facts extract/recover/span. Allowlisted scalar fields only: edge/phase/subphase/safe relative file or index/rule-id/counts/definitions/calls. No absolute fallback/AST/source/result payload, new protected workload/coroutine or timeout hook.
- [ ] Test-only writer injected only existing fullrepo test when timings1; production modules read no environment/write no logs. Phase-first detail-phase=nil flushes monotonic begin/end, aggregates file work without history, max256lines×256bytes. Later measured single-phase detail max2MiB,512bytes/line, explicit cap marker. Existing~642KiB + limits below16MiB capture; no marker-parser/schema changes.
- [ ] Tests prove disabled parity/order/results/facts, privacy/escaping/caps, begin without false end on failure, monotonic fake clock/sink and flushing, unchanged installed/restored latched deadline including caught inner exceptions. Never use flamegraph/per-rule timeout/newsethook.
- [ ] Compile→constraints→`[:tests.test-constraints-source :tests.test-constraints-facts :tests.test-constraints-runner :tests.test-constraints-default-run :tests.test-runner :tests.test-list-entities]`. Compare native timings on/off elapsed/output/outcomes, assess overhead before Wine. Same full roots/five suites/baselinefalse/120s budget. Document experiment, review/checkpoint, not timeout/List fix.

### Task 7: Combined Actual Evidence Gate

**Files:** evidence-only task7 artifacts; no source changes. Consume reviewed Tasks1–6.

- [ ] Clean reviewed checkpoint; freshness→compile→constraints→combined focused/native/provider tests→seven host modules→full make test→diffcheck. Independent cumulative source-gate review.
- [ ] One capability preflight/reproduce using exact unchanged command/timeouts. Preserve HEAD/status, wrapper JSON, ledger/log hashes/sizes/truncation, admission IDs, totals/shutdown/stop/wait/endedunauthorized state; collect operand/timing evidence.
- [ ] Reconcile original30 by case name PASS/FAIL/unexecuted, not count subtraction. Explicit SHA/MCP downstream assertions/both Workflow cases/retained String-Link persistence successes. Independent actual review; remaining failures block closure.

### Task 8: Evidence-Gated List Correction and Constraints Decision

**Conditional modify:** `assets/lua/tests/test-list-entities.fnl`, `assets/lua/tests/constraint-progress.fnl`, `assets/lua/tests/test-constraints-default-run.fnl`, `docs/dev/notes/test-harness-cleanup.md`, `docs/dev/constraints.md`.

- [ ] List gate requires real seam reached, raw mismatch, canonical intended equality and disk/signals consistent for all5. Otherwise advisor/new measured proposal, no guessed mutation.
- [ ] If proven: fixture creation returns fs.absolute before create/store/observe/snapshot/cleanup; component-boundary descendant check and equivalent-spelling/sibling-prefix regression. Preserve move[2 2 2 0], remove/selection[1 1 1 0], name/recovery[1 1 0 0]. Compile→constraints→`[:tests.test-list-entities :tests.test-reference-lifecycle-projections :tests.test-reference-lifecycle-composition]`, diagnostics parity, review/checkpoint.
- [ ] Constraints gate: compare measured durations/counts/overhead; unmatched begin only localizes. Advisor before diagnostic refinement; set private detail-phase literal only for measured phase, same caps/deadlines, tests/review/checkpoint before guarded run. Batch proven List repair into that run.
- [ ] Before any algorithm optimization, coordinator adds exact measured function/input mechanism, regression/equivalence oracle, file allowlist/validation refinement. No algorithm/rule/baseline/timeout change authorized here. Unknown measurements remain investigation, human decision only genuine product/API/data/architecture/access choice.

### Task 9: Final Zero-Failure Follow-up Proof

**Files:** evidence-only task9 report plus reviewed status update in `docs/dev/notes/windows-wine-build-and-test.md`.

- [ ] Final source freshness/compile/constraints/focused/native/provider/sevenhost/fullLinux checks. Diagnose every failure.
- [ ] Guarded full reproduction at exact final reviewed source; zero failures, original30 plus new required cases executed/passed, constraints within unchanged bound, retained publication successes, complete logs/successful cleanup. Prior run reusable only exact final source.
- [ ] Independent actual review and truthful documentation. Main publication Tasks7–9 remain separate; current-origin/full-branch/PRCI finishing remains required. No publishing action inside this follow-up plan.

## Self-Review

All30 failures accounted, known repairs before combined runtime, evidence gates before List/constraints fixes. Provider source/license/include/endian selection resolved at plan level; actual ON/OFF compilation and native/Wine proof remain required. No publication/security/budget/graph ownership change or missing product approval identified. Supervisor saved this planner draft after self-review; implementation still requires task gates.
