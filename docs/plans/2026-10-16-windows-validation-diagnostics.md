# Trustworthy Windows Validation Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Wine-helper contamination and obtain a trustworthy, stage-resolved reproduction of the Windows/Wine failure.

**Architecture:** Repair artifact ownership and API admission first, then add private streaming diagnostics behind the existing guarded operation. A builtin-first ProcessPrng probe may select an overlay-only bridge backed by Wine's OS crypto; fabricated success is removed. Instrumentation is evidence, not a timeout fix.

**Tech Stack:** Bash, Python standard library, MinGW C, Wine, pytest; existing dependencies.

## Global Constraints

- Authority: `docs/specs/2026-10-16-windows-validation-diagnostics-design.md` (`7f3f58e`).
- “Keep the existing four guarded wrapper commands.”
- “No `.opencode/**` changes or new execution profiles are needed for this first diagnostic cycle.”
- “Do not introduce a general execution framework, arbitrary command/environment passthrough, or permission workaround.”
- “Do not change test assertions, case deadlines, skips or selection.”
- Preserve `tests.fast:main` and its existing180-second Wine-hosted invocation for the first instrumented reproduction.
- Each stream log capped16MiB; retain three positively owned diagnostic runs.
- “The native package is immutable input to Wine preparation.”
- “These probes are API-contract admission checks, not entropy certification.”
- Preserve initial Wine prefix/display conditions; no guessed prefix reset or Xvfb addition.
- Fresh internal script APIs may be refactored, all repo callers migrated, no old mock alias retained.
- Independent review gates each task; only supervisor commits after PASS. Workers do not stage/commit/push.
- Native Windows remains authoritative, and historical Linux native SIG investigation remains separately open.

### Task 1: Isolate Artifacts and Admit a Valid ProcessPrng Runtime

**Files:**
- Modify: `scripts/package-windows-runtime.sh`, `scripts/prepare-windows-wine-runtime.sh`, `scripts/test-windows-under-wine.sh`, `scripts/opencode_windows_ci_repro.py`
- Rename/delete: `scripts/build-wine-bcryptprimitives-mock.sh` → `scripts/build-wine-bcryptprimitives-compat.sh`
- Create: `scripts/wine/process_prng_compat.c`, `scripts/wine/probe.c`, `scripts/wine/runtime.sh`
- Create/Test: `scripts/tests/test_windows_wine_runtime.py`
- Modify/Test: `scripts/tests/test_windows_build_host_setup.py`, `scripts/tests/test_opencode_windows_ci_repro.py`
- Modify: `.github/workflows/build.yml`, `.github/workflows/windows.yml`, `docs/dev/notes/windows-wine-build-and-test.md`

**Interfaces:**
- Build `build/windows`, native package `build/dist/windows`, Wine overlay `build/wine/windows` have separate ownership.
- `prepare-windows-wine-runtime.sh`: no arguments, creates/admit fresh overlay, exits0 only on real API admission.
- `build-wine-bcryptprimitives-compat.sh`: no arguments, writes only fixed owned overlay DLL.
- `test-windows-under-wine.sh`: runs the admitted overlay, full fast suite and existing deadline; wrapper uses fixed full settings.
- Private `scripts/wine/runtime.sh`: `resolve_wine_cmd()` and `configure_admitted_wine_runtime()`, validating a receipt and applying fixed backend settings, never evaluating generated shell.
- Probe no arguments: exit0 admitted, exit10 confirmed missing library/export, exit20 contract/identity failure; crash/timeout/other errors never authorize fallback.

- [ ] **1. Write failing artifact/admission tests.** Exercise repeat package→Wine→package with lower/mixed-case stale helper copies; native artifacts never include helper. An old unmarked output/unrelated sentinel is preserved, not blindly deleted. Overlay preparation preserves build/package hashes and copies packaged assets. Symlinked/unsafe outputs fail before mutation. Only initial probe10 permits fallback; failed/no-op/crashed/timed-out probes stop. Probe/application/workflow smoke share selected Wine/prefix/backend conditions.

  ```python
  def test_only_absence_allows_bridge(preparation):
      for code in (1, 20, 124, 139):
          result = preparation.run(probe_codes=[code])
          assert result.returncode != 0
          assert not preparation.compat_was_built()
      result = preparation.run(probe_codes=[10, 0])
      assert result.returncode == 0
      assert preparation.compat_was_built()
  ```

- [ ] **2. Implement ownership-safe artifacts.** Exclude `bcryptprimitives.dll` case-insensitively from native copying and verify no forbidden final entry. Never remove stale source build helpers as a hidden side effect. Create versioned ownership/inventory manifests for generated output. Never recursively delete an argument, linked tree, or output with unrecognized entries. For validated fixed old unmarked `build/dist/windows`, atomically preserve it as `windows.pre-diagnostics`; if that slot exists or ownership is ambiguous, fail explicitly instead of overwriting evidence. Replace only verified owned output. Overlay copies the clean immutable package, never top-level build DLL leftovers; serialize concurrent preparation/reproduction.

- [ ] **3. Replace false RNG success.** Real C source exports `BOOL WINAPI ProcessPrng(PBYTE,SIZE_T)` and statically imports exact `BOOLEAN WINAPI SystemFunction036(PVOID,ULONG)` from advapi32. Backend overrides use Wine builtins for advapi32/cryptbase, avoiding ProcessPrng recursion/loader-lock LoadLibrary. Fill all requested bytes through checked nonzero chunks ≤ULONG_MAX. Zero length including null/zero succeeds without backend call; null/nonzero or observable backend failure emits fixed diagnostics and terminates nonzero. No rand/timestamp/zero-fill fallback.

  Compile real fill-loop source against test-only adapters: chunkcap7/request16 must call `[7,7,2]`; failure on call2 stops and cannot return success. Test zero/null/guard behavior without huge buffers. This checks our bridge, not every Wine backend failure. Wine's underlying host-RNG implementation may hide short reads; document that limitation, not cryptographic certification.

- [ ] **4. Implement real PE admission.** Probe loads actual bcryptprimitives/export, verifies correct ABI/module identity, tests two64KiB requests and odd65539-byte request with distinct patterns/canaries, rejects unchanged/stuck/guard-damaged output, and checks zero-length canaries. Prefer builtin-only ProcessPrng. Only absence10 compiles overlay bridge and re-probes; a second failure stops, no retry loop. Builtin settings: `bcryptprimitives=b;advapi32,cryptbase=b`; compatibility: `bcryptprimitives=n;advapi32,cryptbase=b`. Bound each probe60s (the existing workflow startup-smoke bound); distinguish admission timeout from crypto failure. Emit flushed phases/results; create admission receipt only after success. The full application180s bound is unchanged.

- [ ] **5. Migrate every caller, remove mock.** Existing wrapper prepares/admit overlay before full tests. Workflow smoke prepares/admit overlay and runs its existing60s `--help` against overlay CLI, never build/runtime-injected CLI. Use absolute overlay assets/macros/SPACE_BIN and retain working-directory/test-data behavior. Update all old script callers/docs/tests without aliases. No `.opencode` rule change or agent environment prefix.

- [ ] **6. Validate and independently review.** Establish RED then GREEN using the focused Python modules and `bash -n` on changed/new scripts. Fixture compilation uses actual MinGW headers with `-Wall -Wextra -Werror`, bridge `-ladvapi32`, plus deterministic host adapters. Do not execute PE/Wine directly from implementer: real admission runs through Task3's exact guarded operation. Report actual fixtures versus unexecuted runtime evidence and full manifest/diff.

### Task 2: Stream Evidence Behind the Same Reproduce Command

**Files:**
- Modify: `scripts/opencode_windows_ci_repro.py`, `scripts/test-windows-under-wine.sh`, `scripts/tests/test_opencode_windows_ci_repro.py`, `docs/dev/notes/windows-wine-build-and-test.md`
- Leave unchanged: `scripts/opencode_capabilities.py`

**Interfaces:**
- Existing `reproduce(repo_root: Path) -> dict` and response/status/CLI exit conventions remain.
- Private `_run_repro_step(repo,run_dir,step,args) -> dict`, called only by fixed internal stage table; no user command passthrough.
- Fixed owned `build/windows-ci-repro/<generated-id>/ledger.json`, `<stage>.stdout.log`, `<stage>.stderr.log`.
- Stage order: preflight, build-windows-from-linux, package-windows-runtime, verify-windows-outputs, wine-admission, wine-fast. Admission records builtin/compat phases separately from tests.

- [ ] **1. Add failing fake-process tests.** Success followed by failure retains earlier outputs. Large simultaneous streams drain and cap logs. Markers after disk caps still update. Exit124, launch error and interruption have distinct finalized outcomes. EOF before process exit waits correctly; descendant-held pipes terminate capture within a bound. Fourth owned run prunes only eligible owned runs; unrelated/quarantined/symlinked entries are untouched/rejected. Admission failure must prevent full test launch.

- [ ] **2. Implement bounded private capture.** Binary incremental/concurrent drainage with bounded decoder/line buffers; no full-output communicate/PIPE subprocess.run for reproduction steps. Returned tail bound4000 characters per stream, with separate excerpt/log truncation flags, observed/stored counts and capture errors. Continue drain after16MiB. Private0700 run directories and exclusive regular logs, no symlink traversal; serialize reproduction ownership. Retain three positively identified runs including current, never arbitrary/unowned/quarantined evidence.

- [ ] **3. Persist stage/progress truthfully.** Atomic start/end ledger updates include wall timestamps, monotonic elapsed, outcome/returncode, logs, tails/completeness. Bound marker lines4KiB; count recognized launch/load/run/pass/fail/timing markers and retain latest text/timestamp. On leader exit allow2s for EOF, then terminate only owned processgroup, allow2s, kill remaining owned group and close pipes, flagging forced closure/incomplete evidence. Preserve partial ledger on launch/capture/interruption errors. Missing evidence is not a complete successful diagnosis.

- [ ] **4. Enable fixed diagnostics, not broader authority.** Internally enable TEST_VERBOSE1 and SPACE_TEST_TIMINGS1. Reject conflicting inherited suite/deadline/filter overrides for the guarded operation; preserve full fast,180s and current per-case/skips. Record allowlisted Wine/version/payload identity/module/deadline/settings, prefix selection and display presence only—not environment/registry/credentials/prefix files. Return bounded structured ledger sufficient for restricted operator; log paths let supervisor inspect complete named artifacts. CLI still accepts exactly four existing commands, no profiles/extra flags.

- [ ] **5. Validate and independently review.** RED/GREEN full wrapper tests, including real oversized-output and lifecycle cases rather than only short fixture strings. Shell syntax and policy tests confirm no scope widening. No real Wine run before Task1 safety and Task2 review gates pass.

### Task 3: One Guarded Diagnosis and Evidence-Driven Follow-up

**Files:**
- Modify: `docs/dev/notes/windows-wine-build-and-test.md`
- Read/evidence: `.superpowers/sdd/windows-validation/evidence.md`, generated owned `build/windows-ci-repro/` artifacts
- Test: `scripts/tests/test_windows_ci_speedups.py`, `scripts/tests/test_opencode_windows_ci_policy_docs.py`

**Interfaces:**
- Consume reviewed/committed Tasks1–2 and passing fixtures.
- Produce a retained real ledger/PE probe result and exact last reached failure boundary; not an unsupported timeout-fix claim.

- [ ] **1. Complete relevant local checks.** During work run individual pytest RED/GREEN and changed-shell syntax; then run the five-module suite below. No Fennel/native app changes are planned, so broad Linux make-test does not exercise this tooling boundary and is not required at each checkpoint. The guarded cross-build supplies app freshness.
- [ ] **2. Dispatch once through existing capability.** Preflight may run first. Then exactly `python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .`, via windows-ci-reproducer. No agent environment prefix, raw Wine/manual probe, profile override or automatic retry.
- [ ] **3. Inspect actual evidence.** Native package contains no banned helper, build/package unchanged by overlay preparation, real selected PE probe succeeds before app tests. Inspect phase/marker/timing ledger and complete logs to identify admission, startup/module-load, active progress, specific case/native call or shutdown. Prefix/display and180s remain recorded. No marker means before first observed boundary, not proof of one startup cause. Repeated124 is failure/incomplete, never success.
- [ ] **4. Continue diagnosis only from evidence.** Specify root-cause-specific follow-up with exact failure, files, regression and confirming check. If uncertain, instrument the missing boundary, not a guessed runtime fix. Route any further mutation through implementation/review; no arbitrary timeout increase, profiles, prefix reset or Xvfb until evidence justifies it.
- [ ] **5. Document and review.** Update ownership/migration, probe/log limits, real result and follow-up; independent review before commit. Record native CTest coverage separately: test_record_publication configured but not built by space/cli-only Windows targets. Missing coverage is not an observed failing Windows test. Keep native Windows authoritative and historical SIG separate. PR CI remains integration gate.

## Exact Focused Validation

```bash
python3 -m pytest -q \
  scripts/tests/test_windows_wine_runtime.py \
  scripts/tests/test_windows_build_host_setup.py \
  scripts/tests/test_opencode_windows_ci_repro.py \
  scripts/tests/test_windows_ci_speedups.py \
  scripts/tests/test_opencode_windows_ci_policy_docs.py
bash -n scripts/package-windows-runtime.sh
bash -n scripts/prepare-windows-wine-runtime.sh
bash -n scripts/test-windows-under-wine.sh
bash -n scripts/build-wine-bcryptprimitives-compat.sh
bash -n scripts/wine/runtime.sh
```

Full application cross-build/Wine execution uses only windows-ci-reproducer. No ad-hoc setup/package installation or home-prefix browsing. Source/test fixes use apply_patch and targeted checks; reviewer gates and clean/current-base finishing remain required. Do not report the Wine failure fixed merely because tooling now exposes it.
