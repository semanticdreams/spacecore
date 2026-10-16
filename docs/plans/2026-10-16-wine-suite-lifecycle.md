# Bounded Wine Suite and Owned Prefix Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the complete Wine suite run within a justified finite budget and clean its server domain without touching unrelated prefixes.

**Architecture:** A private prefix-lifecycle module owns generated sessions beside the existing artifact helper. Preparation initializes and admits one prefix, then quiesces it while retaining one execution authorization. Cleanup-owning smoke/full consumers end that authorization and stop the server; the existing guarded parent has early ownership and a final backstop.

**Tech Stack:** Python standard library, Bash, GNU timeout, Wine/wineserver, pytest; existing dependencies.

## Global Constraints

- Authority: `docs/specs/2026-10-16-wine-suite-lifecycle-design.md` at `458fc69`; evidence in `.superpowers/sdd/windows-validation/observed-timeout-diagnosis.md` and its real run ledger.
- The run established active progress cut off at180s:93RUN/92PASS/0FAIL, lastPASS9.13s before cutoff; descendants retained pipes. It did not prove later cases pass or identify surviving processes.
- Keep the same four guarded wrapper commands; no `.opencode`, external profile, permission, arbitrary command/env/budget passthrough.
- Full suite1800s, init90s, probe60s, smoke60s, server stop10s, wait15s, each kill-after5s. Outer admission480s, fast1920s, cleanup backstop45s+5s. These fixed overhead budgets are not extra test time.
- Preserve case120/240, regression-child timeouts, modules, assertions, selection and Windows skips. No idle watchdog or guessed Xvfb/application-DLL disabling.
- Native package immutable. Mutable prefix is outside overlay/evidence inventories; never read/log registry, private home prefix, credentials or full environment.
- Prefix isolation enables owned cleanup, not a slowness explanation. Never reset/stop caller/default/unrelated prefixes or run a global wineserver kill.
- Preserve primary failure; success plus cleanup failure is FAIL. Forced capture closure never becomes retrospective complete evidence.
- No prefix pruning/deletion in this correction. Native Windows/macOS and historical Linux SIG gates remain separate.
- Each task requires independent review before supervisor commit. Workers never stage/commit/push; no raw application Wine/cross-build/host setup outside the dedicated capability.

### Task 1: Own, Admit, Execute and Stop One Prefix

**Files:**
- Create: `scripts/wine/prefix.py`
- Modify: `scripts/wine/artifacts.py`, `scripts/prepare-windows-wine-runtime.sh`, `scripts/test-windows-under-wine.sh`
- Delete: `scripts/wine/runtime.sh`
- Modify: `.github/workflows/build.yml`, `.github/workflows/windows.yml`
- Create/Test: `scripts/tests/test_windows_wine_prefix.py`
- Modify/Test: `scripts/tests/test_windows_wine_runtime.py`, `scripts/tests/test_windows_build_host_setup.py`
- Verify consumer: `Makefile` test-windows-wine

**Interfaces:**
- `Session`: generated `id`, `directory`, `prefix`, `nonce`, pinned tools/ownership and lifecycle data; no global session service/cache.
- Prefix API: `create_session(repo)->Session`, `load_session(repo,id)->Session`, `initialize(session)->int`, `stop_session(session, end: bool)->CleanupResult`.
- `CleanupResult`: `ok`, `stop_returncode`, `wait_returncode`, `errors`; actual statuses retained, signal normalization only for process exit.
- Artifacts API: `prepare(session)->int`, `configuration(session)->dict`, `execute_admitted(session, mode: Literal['smoke60','fast1800'])->int`.
- Private artifact CLI: existing preparation/build operations plus fixed smoke60/fast1800/terminal-stop operations, no arbitrary arguments. Wrapper handoff is internally generated `SPACE_WINE_SESSION_ID`; reject inherited handoff values at guarded boundary. Standalone preparation creates a session; consumers use only new-schema verified receipt IDs.

- [ ] **1. Add RED lifecycle fixtures.** Fake Wine/wineboot/server record each argv and selected prefix/arch. Old probe-count assertions must count probes, not boot/server calls. Cover init failure, admission failure, successful quiescent admission, application failure/timeout, interruption, cleanup failure and retry.

  ```python
  def test_one_owned_prefix_for_probe_app_cleanup(runtime):
      runtime.package()
      assert runtime.prepare([0]).returncode == 0
      assert runtime.run('test-windows-under-wine.sh').returncode == 0
      calls = runtime.calls()
      prefixes = {c['env']['WINEPREFIX'] for c in calls if 'wine' in c or 'server' in c}
      assert len(prefixes) == 1
      assert next(iter(prefixes)).startswith(str(runtime.root / 'build/wine/sessions') + '/')
      assert all(c['env']['WINEARCH'] == 'win64' for c in calls if 'wine' in c or 'server' in c)
      assert [c['server'] for c in calls if 'server' in c][-2:] == [['-k'], ['-w']]
  ```

- [ ] **2. Create independently verifiable ownership before initialization.** Allocate private0700 `build/wine/sessions/<id>/` and real prefix directory plus0600 versioned control metadata outside prefix contents. Bind canonical repo/build identities, effective UID, ID/nonce, session/prefix dev+inode and fixed bounds. No raw registry/drive inventory. Before every stop/wait validate containment, private ownership/modes, nonlinked roots, immutable nonce/identities, pinned tools and coherent state. Mutable state/persistence errors cannot confer authority on unowned paths or prevent a safely owned cleanup attempt; keep immutable ownership separate from mutable generation/authorization.

- [ ] **3. Pin matching Wine tools and controlled environment.** Preserve WINE_CMD selection; otherwise wine64/wine fallback. Resolve corresponding installation/suffixed wineserver, verify matching release and both canonical executable hashes. Fail before init if pairing unavailable. Internally pin WINESERVER, generated WINEPREFIX and WINEARCHwin64; preserve actual display. Never use inherited/default prefix for initialization or cleanup.

- [ ] **4. Bound init/admission/quiescence.** Run selected Wine `wineboot.exe --init` with90+5 bound, real probe60+5, selected scoped server `-k`10+5 then `-w`15+5 even after stop failure. Inherit outer logger streams and wait leaders, not internal communicate on orphan writers. Mark launch generation before each Wine launch. Preparation stops/waits with endFalse, retaining authorization only after successful admission/quiescence. Failure ends authorization. Preserve builtin-first/absence-only bridge behavior and native package immutability.

- [ ] **5. Issue new session-bound receipt.** Schema2 binds session ID/nonce/prefix identity/win64, both tools, display/backend and package/payload inventories. Reject old default-prefix receipts, changed identities, wrong sessions and ended/consumed authorization; never upgrade stale receipts. Revoke execution authorization durably before launching its one application so later state-write failure cannot permit replay. Verified stopped generation makes cleanup idempotent; failed cleanup remains retryable.

- [ ] **6. Replace configure-only consumers.** Private fixed smoke60 retains --help; fast1800 runs unchanged `-m tests.fast:main`. Both use finite kill-after5 and finally stop/wait their session, including configuration errors, exceptions, SIGINT/catchable SIGTERM. Preserve primary rc; success+cleanup failure returns nonzero. Every Wine/server child excludes lock FDs with close_fds/CLOEXEC while parent holds locks. Move both workflow callers to owning helper, keep subsystem/native-Windows checks unchanged. Shell entrypoints are no-argument thin delegates; remove runtime.sh and all live references, no aliases.

- [ ] **7. Prove ownership and liveness.** Real host different-PGID pipe writer is stopped by fake prefix-scoped server; an unrelated prefix stays alive. Verify parent locks held/child FDs absent, root/symlink substitution refuses before kill, DOS-device symlink targets remain untouched, and cleanup-error detail does not erase primary error. No prefix pruning/removal. Signal handling must not allow a repeated catchable signal to skip already-running finite cleanup.

- [ ] **8. Validate and hand off.** Task-specific RED/GREEN then complete prefix/runtime/host-setup modules and shell syntax. Existing deterministic C and actual tiny MinGW compilation tests remain, but no PE/Wine application execution here. Full manifest/diff/report includes all retired consumers, status/hashes and remaining real evidence gaps. Independent review before commit.

### Task 2: Guarded Backstop, Evidence and One Real Confirmation

**Files:**
- Modify: `scripts/opencode_windows_ci_repro.py`, `scripts/_windows_repro_evidence.py`
- Modify/Test: `scripts/tests/test_opencode_windows_ci_repro.py`
- Verify/Test: `scripts/tests/test_windows_ci_speedups.py`, `scripts/tests/test_opencode_windows_ci_policy_docs.py`
- Modify: `docs/dev/notes/windows-wine-build-and-test.md`

**Interfaces:**
- Existing public reproduce/CLI/status contracts and six ordered stages remain.
- Private `_run_repro_step(repo,run_dir,step,args,session: Session|None)` accepts fixed internal argv plus verified generated session only.
- Metadata/subrecords record all fixed budgets, generated prefix/tools/architecture, launch generation and cleanup attempts, primary status and complete/incomplete capture.

- [ ] **1. Add RED wrapper lifecycle cases.** Parent creates ownership after output verification and before init/probe. Internally assembled child environment carries only generated session ID. Tests cover no receipt on failed init/admission, final cleanup after fast, interruption/storage failures, cleanup-only failure, and retained earlier successes/primary failure.
- [ ] **2. Bound stages and catchable teardown.** Fixed admission outer480+5 and fast1920+5 include overhead only. Early EOF with live leader remains bounded. Finally attempt terminal owned cleanup after every catchable parent exit, even after interrupted helper or failed evidence writes. Record backstop in current Wine stage logs with separate bounded cleanup subrecord; its private helper45+5. Retry failed cleanup once via backstop; verified already-stopped generation needs no duplicate server action. Never require a valid admission receipt merely to clean a session owned before init.
- [ ] **3. Preserve capture honesty.** Keep original process-group cleanup as separate evidence, not proof of Wine-server shutdown. Helpers stop their prefix before exit; parent backstop covers interrupted helpers. Never fabricate EOF/completeness after forced closure. Preserve caps, progress,48KiB response, checked atomic publication/in-memory failure recovery, inventory and retention. Record no registry/home/credential contents.
- [ ] **4. Validate failure/lifecycle paths.** Real GNU timeout fixtures use shortened test-only bounds for TERM-resistant child,124/137, EOF/escaped writers and helper interruption. Check unrelated-prefix survival, primary status retention, explicit cleanup/incomplete outcomes and all Make/workflow callers owning teardown; native Windows commands unchanged.
- [ ] **5. Update developer note.** Replace current180/default-prefix/configure-only descriptions with confirmed diagnosis, explicit budgets, quiescence vs terminal authorization, immutable ownership, FD isolation, retained sessions and uncatchable-SIGKILL limits. Keep historical evidence labeled historical. Do not claim later suite outcomes before actual run.
- [ ] **6. Independently review, then run once.** After source/fixture gates pass and commits, dispatch exact guarded reproduce. Require actual init/admission/application prefix parity,1800 launch, bounded stop/wait and capture completeness. Full success requires complete suite, zero app/cleanup failures—not merely progress past the runner group. Further actual failures trigger source-backed diagnosis/review, not weaker assertions/skips.

## Focused Validation and Finishing

Use individual pytest node IDs for RED/GREEN, then:

```bash
python3 -m pytest -q scripts/tests/test_windows_wine_prefix.py scripts/tests/test_windows_wine_runtime.py scripts/tests/test_windows_build_host_setup.py scripts/tests/test_opencode_windows_ci_repro.py scripts/tests/test_windows_ci_speedups.py scripts/tests/test_opencode_windows_ci_policy_docs.py
bash -n scripts/prepare-windows-wine-runtime.sh
bash -n scripts/test-windows-under-wine.sh
git diff --check
```

No application/Fennel/C++ source changes are planned; no Linux runtime build/full suite is justified for this harness-only delta. Audit retired configure/runtime.sh callers using dedicated search. Real application cross-build/Wine only through `windows-ci-reproducer`, tool timeout14400000, exact `python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .`; no environment/profile override or automatic retry. The wrapper cross-build supplies executable freshness.

After the real result, whole-branch review/current-origin/clean-tree and applicable PR CI remain required. Record actual completion or the newly observed failure boundary. Native Windows/macOS security and historical native SIG remain separate; no implied closure or new public capability authority.
