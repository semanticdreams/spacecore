# Secure Record Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct Windows overwrite and private-staging regressions without broadening record access or misreporting committed writes.

**Architecture:** Add one native publication operation owning a private sibling directory; existing text and JSON writers operate inside it. Native code verifies bytes/security, atomically publishes, and cleans only its own entries. RecordFiles and owning stores preserve the completion/cleanup distinction through cache and notification publication.

**Tech Stack:** C++17, sol2, POSIX/Win32 APIs, Fennel, existing JSONUtils, CMake/CTest; existing dependencies only.

## Global Constraints

- Authority: `docs/specs/2026-10-16-secure-record-publication-design.md` at `27144fd`; user approved the additional native boundary.
- “The existing JSON helper remains canonical.” Do not edit `assets/lua/json-utils.fnl`.
- “POSIX staging directory is private (0700)”; “Newly created records publish privately (0600).”
- “Existing destinations retain their owner/group/mode restrictions.”
- “Unsupported/uninspectable policies fail explicitly; no generic ACL editing interface is introduced.”
- “Never change process-wide umask, invoke a production shell, apply restrictions only after publicly writing content, or ignore a security-check failure.”
- “Keep cleanup attempt-local, identity checked, and nonrecursive”; never delete the destination before replacing it.
- “Do not expose an independently owned stage to Lua GC or retain callbacks after the synchronous call.”
- Preserve formats, exact text, cached identity, revision ordering, graph DTOs, read/scan behavior, and successful writer boolean first return.
- No external-writer transaction, hostile same-identity writer, remote-filesystem, metadata-migration, or power-loss guarantee.
- Native SIGSEGV incident remains separately open. No publication/test pass closes it.
- Each task requires independent reviewer PASS before supervisor commit. Workers do not stage, commit, push, or change permissions/configuration policy.

### Task 1: Native Publication Boundary and Independent Contract Tests

**Files:**
- Create: `src/record_publication.h`, `src/record_publication.cpp`
- Modify: `src/lua_fs.cpp`, `CMakeLists.txt`
- Create/Test: `tests/test_record_publication.cpp`
- Modify/Test: `assets/lua/tests/test-fs.fnl`

**Interfaces:**

```cpp
namespace record_publication {
using Stage = std::function<void(const std::filesystem::path&)>;
struct Hooks {
    std::function<void()> before_security, before_commit, before_cleanup;
};
struct Result {
    bool committed = false;
    std::optional<std::string> cleanup_error;
};
Result publish(const std::filesystem::path& destination,
               std::string_view expected_bytes, const Stage& stage,
               const Hooks& hooks = {});
}
```

- Lua: `fs.publish-record(destination, expected-bytes, stage!, opts?) -> {committed: true, cleanup-error?: string}`.
- Callback receives the one owned stage path. `opts` accepts only `test-before-security`, `test-before-commit`, `test-before-cleanup`, each a function returning true; false/nil/throw injects failure.
- Precommit errors raise explicitly; committed cleanup errors return diagnostics, never rollback claims.

- [ ] **1. Add RED native and Fennel cases.** Register `test_record_publication` in CTest. Native checks must throw on failure in Release, not rely on disabled `assert`. Cover missing/new/existing destination, bytes, private workspace with initially absent callback target, callbacks/GC, phase failures, changed identity/security, links, unsupported policy, cleanup outcomes, and long basenames. In `test-fs`, use real JSONUtils:

  ```fennel
  (local JsonUtils (require :json-utils))
  (local json (require :json))
  (each [_ value (ipairs ["before" "after 雪"])]
    (local data {:value value})
    (local result
      (fs.publish-record path (json.dumps data)
        (fn [stage] (JsonUtils.write-json! stage data))))
    (assert result.committed)
    (assert (= (fs.read-file path) (json.dumps data))))
  ```

- [ ] **2. Implement private synchronous ownership.** Pin trusted parent/workspace identities. POSIX ancestry excludes foreign-writable substitution, allowing safe sticky ancestry; owner/root aliases may resolve to a verified stable parent. Reject untrusted aliases and unpinnable Windows reparse ancestry. Windows directory handles prevent workspace/ancestor renaming while the path-based callback runs. No broad path-management abstraction.

  Exclusively create a short `.record-<unique-id>` sibling directory. Precreate only `record.tmp`; callback target `record` starts absent, so real JSONUtils renames to a new target without an inner overwrite dependency. POSIX directory0700 and exclusive no-follow temporary0600 protect effective confidentiality; intermediate writer-created numeric modes can be broader INSIDE the private directory, but final modes are verified before publication. Verify owner/type/link counts. Windows `CreateDirectoryW`/`CreateFileW(CREATE_NEW)` use protected owner-only DACL; directory ACE inherits to writer-created files, owner SID from effective token. File confidentiality on Windows must not rely on directory traversal restrictions alone. Establish protection before private bytes. Never change parent permissions or global umask.

- [ ] **3. Implement bounded POSIX policy and commit.** Support mode-only, single-link regular destinations without extended security metadata. On Linux inspect `flistxattr`; on macOS inspect extended ACL via `acl_get_fd_np(..., ACL_TYPE_EXTENDED)` plus xattrs. Reject nonempty unsupported metadata; distinguish unsupported facility from denied inspection. Check inherited stage/ancestry restrictions too. Snapshot destination identity/security before staging. Preserve existing UID/GID and0777 permission bits, rejecting special bits or failed reproduction. New records remain0600. Keep handles usable for validation after restrictions are applied. Revalidate immediately before handle-relative `renameat`.

- [ ] **4. Implement bounded Windows policy and overwrite.** Require local persistent-ACL filesystem semantics. Open metadata without following reparse points; reject nonregular/multiple-link/reparse destinations. Capture owner/group and ordered DACL using checked `GetSecurityInfo`. Support present ordinary allow/deny DACLs and implicit-medium labeling only. Explicit mandatory labels and resource/scoped/trust/access-filter policies are unsupported: inspect selective security-information flags and reject nonempty/unknown/unreadable policy, EFS, or unknown ACEs. No elevated backup/restore/security privileges or weaker fallback.

  Apply captured owner/group/exact ordered DACL to the private replacement with `SetSecurityInfo`; protect against workspace inheritance and read back to verify. Protection is the only allowed narrowing. Confirm stage lacks unsupported policy. Existing overwrite uses `MoveFileExW(..., MOVEFILE_REPLACE_EXISTING)`, new publication flags0, same volume only. No `COPY_ALLOWED`, CRT rename, deletion, delayed move or `ReplaceFileW` partial-failure assumptions. FALSE is explicit failure; TRUE irrevocably latches committed status.

- [ ] **5. Protect callbacks and outcome ordering.** Use `sol::protected_function` so Lua failure becomes C++ unwinding while RAII owns cleanup. Run stage then before-security hook, verify bytes through no-follow regular-file handles, prepare restrictions, run before-commit hook, then revalidate directory/stage identities, bytes, links, final policy and destination snapshot. No Lua callback after final validation before commit. Prepare Lua success envelope before publication.

  Cleanup is fixed-entry, identity-checked and nonrecursive. Never follow substituted entries or remove unrelated objects; unexpected entries produce diagnostics. Destructors are noexcept and invoke no Lua. Explicit cleanup contains hook errors and still attempts safe cleanup. Before commit preserve original error plus cleanup diagnostics; after commit return committed plus cleanup-error. No logger is needed to communicate outcome.

- [ ] **6. Validate independent usability.** Native tests inspect the private directory, initially absent callback target, protected precreated temporary and intermediate confidentiality while content exists. Real JSONUtils Fennel tests inspect `.tmp`, callback errors/GC and cleanup results without stores. Windows tests must cover existing overwrite and allow/deny restrictions; test-only platform security interop is allowed, not production shell use. CMake already links `advapi32` on space_lib; link the standalone test target only as required, no new dependencies/public ACL APIs. Compile/constraints and focused commands below; independent review before commit.

### Task 2: Owning Store Integration and Acceptance

**Files:**
- Modify: `assets/lua/entities/record-files.fnl`, `assets/lua/entities/string.fnl`, `assets/lua/entities/link.fnl`
- Modify: `assets/lua/graph/view/string-entity-editor.fnl`
- Modify/Test: `assets/lua/tests/test-entity-record-persistence.fnl`, `assets/lua/tests/test-graph-entity-capabilities.fnl`, `assets/lua/tests/test-string-entity-editor.fnl`
- Modify: `docs/dev/features/graph-capabilities.md`

**Interfaces:**
- Consume exact Task1 native API and hook contract.
- `RecordFiles({open?, stage-json!?, publication-hooks?})`; remove old rename seam and migrate tests, no alias.
- `write-text!(path,text)` / `write-json!(path,data) -> true, cleanup-error?: string`.
- Existing successful store APIs unchanged. Cleanup failure becomes owning `{code: "storage-failed", outcome: "committed", message, result, cleanup-error, notification-error?}` only AFTER cache publication and normal notification attempt.
- Replacement error result is existing `{id,value,revision}` snapshot; other write result is detached owning record. Local diagnostic fields do not extend graph DTOs.

- [ ] **1. Add RED completion-ordering cases.** Cover text/link create/update and conditional text replace, cleanup-only, notification-only and simultaneous failures. Listener assertions need external completion guards and must observe persisted bytes/cache/revision. Error results detach; graph conversion retains existing committed DTOs.

  ```fennel
  (local fault {:active false})
  (local boundary
    (Files.RecordFiles
      {:publication-hooks
        {:test-before-cleanup (fn [] (if fault.active (error "cleanup fault") true))}}))
  (local cached (store:create-entity {:value "before"}))
  (local revision cached.revision)
  (set fault.active true)
  (local (ok err) (pcall store.replace-text store cached.id "after" revision))
  (assert (not ok))
  (assert (= err.code :storage-failed))
  (assert (= err.outcome :committed))
  (assert (= cached.value "after"))
  (assert (= err.result.revision cached.revision))
  ```

- [ ] **2. Integrate RecordFiles without a bypass.** Replace its UUID sibling/final rename/cleanup with native publication. Callback retains checked text write/flush/close and local verification; JSON uses unchanged JSONUtils. Native verification remains independent. Precommit exceptions map to existing storage errors; committed returns forward both values. Preserve `open`/`stage-json!` seams. Rename faults migrate to before-commit; JSON partial-write tests write inside the private workspace rather than nest publication.

- [ ] **3. Carry committed diagnostics through stores.** Local `storage!` and write-record paths forward both successful return values. For each create/update/replacement: persist, publish cache/revision, form existing result, attempt existing signal once, then decide outcome. No new shared postcommit framework or deletion redesign.

  Exact precedence: neither error → success; notification only → existing committed notification-failed; cleanup only → committed storage-failed, `"Record committed; staging cleanup failed."`; both → committed storage-failed, `"Record committed; staging cleanup and notification failed."`, with both diagnostics. Do not skip notification, throw before cache publication, or return not-committed after native success.

- [ ] **4. Preserve GUI truthfulness.** Existing provider maps committed results; test without graph schema changes. Editor retains notification-specific copy for notification-only failure; committed storage failure uses `"Save committed; post-save error."`. Both surfaces advance to the committed baseline and permit a subsequent successful save. No layout/lifecycle redesign.

- [ ] **5. Exercise secure acceptance.** Preserve all prior fault/revision/cache/exact-text/long-name/scan tests. Update workspace assertions for private directories. POSIX child process sets umask022 and starts from0600 files: text replacement, unconditional text update, link update; inspect directory/files while record and `.tmp` contain bytes. No parent umask mutation. Cover security/permission/verification/identity/link failures and unchanged bytes/cache/revisions, unrelated temporary preservation, Lua errors/GC and committed cleanup errors. Windows real overwrite and ordinary allow/deny DACL preservation or narrowing must be validated; unsupported policy explicitly fails without publication.

- [ ] **6. Document and validate.** Canonical graph-capabilities page documents native API, supported/refused security policies, private precreation, writer second value, error precedence, seam migration, filesystem/threat assumptions and durability limit. Independent review before commit; full suite after reviewed fixes.

## Validation Commands and Gates

After CMake edits: `make cmake`, tool timeout600000; native freshness `make build`, timeout14400000. Native tests remain active in Release.

```bash
export SKIP_KEYRING_TESTS=1
export XDG_DATA_HOME=/tmp/space/tests/xdg-data
export SPACE_DISABLE_AUDIO=1
export SPACE_ASSETS_PATH="$PWD/assets"
export FENNEL_PATH="$PWD/assets/lua/?.fnl;$PWD/assets/lua/?/init.fnl"
export FENNEL_MACRO_PATH="$FENNEL_PATH"
```

Native build FIRST; touched-file `tools.fennel-check` next; `make constraints` next; focused tests next. Repair nearest enclosing forms on parser errors, then restart compile gate. Constraint failures are blocking, not waived.

```bash
ctest --test-dir build -R '^test_record_publication$' --output-on-failure
./build/space -m tests.test-fs:main
./build/space -m tests.test-entity-record-persistence:main
./build/space -m tests.test-string-entities:main
./build/space -m tests.test-link-entities:main
./build/space -m tests.test-graph-entity-capabilities:main
./build/space -m tests.test-string-entity-editor:main
SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH="$PWD/assets" make test
```

Use guarded `windows-ci-reproducer` for cross-build/Wine, no ad-hoc setup. Native Windows validation is authoritative for security; obtain existing `windows.yml` branch-dispatch evidence where available (it lacks PR triggers). Unavailable required platform evidence is a documented human-input blocker, not a claimed pass. PR CI remains the full integration gate. Record commands, coverage rationale and constraint impact. Native SIG incident is separate and open.
