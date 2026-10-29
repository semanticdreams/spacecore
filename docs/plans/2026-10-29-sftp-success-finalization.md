# SFTP Success Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish successful SFTP transfer notifications only after checked local I/O, checked remote-file close, and transfer SFTP-session teardown.

**Architecture:** Keep finalization in the existing libssh transfer workers with explicitly idempotent RAII resources and the per-file mutex. A native regression executable uses the real backend and existing disposable OpenSSH fixture, with executable-local linker wrappers for deterministic teardown gates and close-error injection. This fits existing ownership without redesigning arbitration or general same-session concurrency.

**Tech Stack:** C++17, libssh, CMake/CTest, Python OpenSSH fixture, unchanged Fennel integration tests.

## Global Constraints

- Task `ssh-sftp-success-finalization`, branch `juicyrebel/devilray`; verified clean source `59d92dc11e289bd79f9b103d620573443df91424`.
- Reuse the confirmed diagnostic/expert reconciliation recorded in `2026-10-29-model-neutral-agent-routing-progress.md`, final sections. Two reproductions in four close-delay trials demonstrate the hazard, not the original CI's precise failing stage or necessity/exclusivity of this schedule.
- Success-only cleanup guarantee. Cancellation/timeouts remain asynchronous terminal winners, NOT cleanup barriers. SftpComplete and OperationSuccess remain separately arbitrated, not atomic.
- Finish checked local I/O; explicitly close remote file; free transfer SFTP session; recheck activity; only then publish successful-transfer notifications.
- Remote close failure => RemoteFileError; local finalization/upload read failure => LocalFileError. Preserve primary errors and terminal winners.
- File close is mutex-protected/idempotent despite cancellation retaining shared_ptr references. libssh 0.10.6 sftp_close consumes the handle even on error: never retry or double-close. Capture diagnostics while parents live. sftp_free returns void; keep parent SSH alive through teardown.
- No coarse session-wide blocking mutex, production sleeps/retries, test skips, broad concurrency redesign, durability/fsync promise, or migration/config/dependency/CI-policy edits.
- Preserve original diagnostic sources, traces and manifests privately. The ignored diagnostic shim is not production or committed test code and must not be committed.
- Controller owns the existing durable progress ledger; implementer owns assigned validated/self-reviewed checkpoints, not publication.
- PR CI remains the authoritative integration gate; completion requires observed mergedAt for PR290.

---

### Task 1: Checked transfer finalization and real-backend regressions

**Files:**
- Modify `src/ssh_backend_libssh.cpp`: resource close/reset and upload/download finalization.
- Modify `CMakeLists.txt`: Linux/libssh-only regression target and CTest registration.
- Create `tests/test_ssh_sftp_finalization.cpp`: real-backend deterministic regression coverage.
- Modify `docs/dev/subsystems/ssh.md`: success/failure/ownership semantics and test command.
- Consume unchanged `tests/ssh_fixture.py`, `tests/test_ssh_service.cpp`, `tests/test_lua_ssh_binding.cpp`, `assets/lua/tests/test-ssh-integration.fnl`.

**Interfaces:**
- Existing `make_libssh_backend()`, Service SFTP/cancel/poll/close_session/shutdown APIs stay unchanged.
- Internal `SftpFileResource::close() -> int` caches close status under its mutex; `request_close()` delegates. Internal `SftpHandle::reset() -> void` consumes/nulls and frees once; prohibit accidental copying.
- Native target `test_ssh_sftp_finalization`, CTest `space_ssh_sftp_finalization`, links actual backend/service sources with installed libssh and executable-local GNU `--wrap` symbols for sftp_open/close/free and ssh_free as needed. Wrappers match installed headers and forward real calls. No public injection API or runtime test switch.

- [ ] **Step 1: Establish regression RED.** Follow existing native assertion style and fixture environment. Invoke native executable through unchanged `tests/ssh_fixture.py --space <native-target> --assets <absolute-assets> --module ssh-sftp-finalization`; accept fixture CLI arguments. Register only on Linux with SPACE_HAS_LIBSSH. Use bounded condition-variable gates at close/free; failures must release gates and join workers. Track lifetimes without logging credentials, paths or payloads. Close-error injection calls real close once, then returns SSH_ERROR; label injected evidence separately. Demonstrate pre-fix premature success and ignored close/local-finalization errors, not infrastructure failures.
- [ ] **Step 2: Make teardown explicitly idempotent.** Under the existing file mutex consume/null the file and cache sftp_close status regardless of result. Destructors remain nonthrowing. Explicitly close before freeing parent SFTP even if cancellation holds another shared_ptr. Do not hold registry/service mutexes across blocking close/free. Retain fallback RAII and parent SSH shared ownership.
- [ ] **Step 3: Finalize both success paths.** Upload rejects failed size/seek and distinguishes bad/non-EOF read failure from valid EOF, including partial final buffers and empty inputs. Download checks flush and close, preserving a failed flush. Finish local I/O, checked remote close with diagnostics captured before parent free, unregister file, reset SFTP, then check_active before successful notifications. Early transfer failures keep primary errors; cleanup must not overwrite them or create a second terminal winner.
- [ ] **Step 4: Cover the matrix.** Both directions: binary/empty transfers and immediate exact bytes; independent close/free gates prove neither success notification while gated and close-before-free-before-success after release, with exactly-once ownership. Remote-close injection produces RemoteFileError/no success. Local cases: missing input, directory/non-EOF input/seek failure, invalid destination, small buffered /dev/full finalization failure; combine local failure and close injection to prove primary-error preservation. Cancellation and real service timeout while close/free gated retain one terminal/no late success after release and drain. Race cancellation/final close/session closure and check no duplicate close, file access after SFTP free, or parent SSH free before teardown. Use fresh sessions for disruptive scenarios. Source review supplements retained-reference execution coverage; FakeBackend tests alone are insufficient.
- [ ] **Step 5: Focused GREEN.** Run `make build` with tool timeout 14400000 (and standalone `make cmake` timeout 600000 if needed). Run the focused CTest command below and verify the new test actually ran. No Fennel edit is planned; if justified, use native compile check first, constraints second, focused tests third, inspecting nearest enclosing form on parse errors. Run ignored diagnostic modes 0/1/2 unchanged with distinct new evidence names and inspect real close/free-exit-before-success-chained-successor traces; passing timing runs alone are not the deterministic oracle.
- [ ] **Step 6: Document and checkpoint.** Update canonical SSH docs with success-only barrier, error mappings, consumed-close ownership, void-free limit, timeout/cancel non-barrier and regression invocation. Record RED/GREEN, coverage rationale, constraint impact, files and all checkpoint SHAs in the private implementation report. Self-review and checkpoint assigned four files only. Controller records privacy-safe progress and dispatches independent full task review. No push/PR/integration authority.

## Validation and finishing

Focused command (normal fixture-related constraints may run transitively):

```bash
SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data \
SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH="$(pwd)/assets" \
SPACE_TEST_REQUIRE_SSH_BACKEND=1 SPACE_TEST_REQUIRE_SSH_FIXTURE=1 \
ctest --test-dir build --output-on-failure \
  -R '^(test_ssh_service|test_lua_ssh_binding|ssh_fixture_strict_mode|space_ssh_sftp_finalization|space_ssh_integration)$'
sh build/opencode/ssh-interleave-probe/run-probe.sh 0 finalization-baseline
sh build/opencode/ssh-interleave-probe/run-probe.sh 1 finalization-close
sh build/opencode/ssh-interleave-probe/run-probe.sh 2 finalization-free
```

After task review, controller coordinates full accumulated branch review (prior migration reviews remain recorded, not discarded), guarded current-origin/main checks and broader validation justified by native lifecycle/concurrency risk:

```bash
SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data \
SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH="$(pwd)/assets" \
SPACE_TEST_REQUIRE_SSH_BACKEND=1 SPACE_TEST_REQUIRE_SSH_FIXTURE=1 make test
make opencode-check
python3 -m pytest scripts/tests/test_opencode_handoff_delivery_contract.py -q
git diff --check
```

Use adequate command budgets. Required failures enter systematic debugging, not blind retries/skips. Safe-merge current origin/main only when needed and permitted; route repository/conflict fixes through implementer/reviewer/pass. Push only reviewed committed green changes from a clean feature branch, then monitor PR290 until mergedAt is present.
