# Compatible Secure Record Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve normal default editing and private publication by refactoring the fresh internal draft APIs and migrating every repository consumer.

**Architecture:** Native code writes the supplied serialized payload through retained private handles, then commits to the pinned target directory. An intentionally retained per-parent private anchor owns attempt cleanup safely. JSONUtils stays canonical through one serialized-payload publisher hook; RecordFiles/stores retain truthful committed outcomes.

**Tech Stack:** C++17, sol2, POSIX handle-relative APIs, Windows Native file APIs, Fennel, existing JSONUtils, CMake/CTest; existing dependencies only.

## Global Constraints

- Authority: current `docs/specs/2026-10-16-secure-record-publication-design.md`, corrected in `5b79ef2` and `c27e655`; old callback/ancestry-refusal plan is superseded.
- The user clarified fresh internal APIs have no outside consumers: refactor/migrate repository callers, remove draft APIs and unused options, and add no compatibility aliases.
- Ordinary default/custom editing under umask002 and home0750/inner0775 must work. Refusal is not accepted compatibility.
- No process-wide production umask changes, parent chmod, shell writers, delete-before-overwrite, or public-write-then-restrict interval.
- Other local users must not redirect private bytes. No hostile same-identity writer, external-writer transaction, remote-filesystem or power-loss guarantee.
- Preserve supported destination restrictions or fail explicitly for unsupported/uninspectable policy; no ACL framework.
- Preserve inherited uncommitted Task2 cache/revision/notification/editor outcome work and its reviewed platform-test corrections; do not discard it.
- Historical native SIGSEGV remains separately open. Passing publication/platform tests do not close it.
- One coherent refactor task spans native API and every affected caller; do not ship mixed signatures. Implementer does not stage/commit/push. Independent reviewer PASS precedes supervisor commit.

## Scope and Caller Inventory

Modify `src/record_publication.h`, `.cpp`, `src/lua_fs.cpp`, `tests/test_record_publication.cpp`; `assets/lua/json-utils.fnl`, `entities/record-files.fnl`, `entities/string.fnl`, `entities/link.fnl`, `graph/view/string-entity-editor.fnl`; tests `test-fs.fnl`, `test-entity-record-persistence.fnl`, `test-string-entities.fnl`, `test-link-entities.fnl`, `test-graph-entity-capabilities.fnl`, `test-string-entity-editor.fnl`; docs `dev/features/graph-capabilities.md`, `sdk/modules/json-utils.md`.

CMake already registers the native module/test. Change it only if actually needed. Existing JSON callers (other entity stores, workflows, temporal/repo/notebook stores, kernels, LLM stores, world persistence, wallet, live-dev) use ordinary two-argument writes and retain their default path; audit them for assumptions rather than rewrite unrelated systems. No actual `atomic? false` caller was found; implementation/SDK documentation are its only uses. Remove that unused option and update docs. Unknown/old options fail explicitly, not via aliases.

The caller audit found native calls only in lua_fs, RecordFiles, test-fs, one persistence canonical-path probe, and the native test. RecordFiles `open` serves reads and old staging writes; retain only read injection. Remove `Stage`, stage callbacks, `stage-json!`, and path-writer open/write/flush/close fault assumptions. Preserve store `files` injection and meaningful completion/failure invariants.

### Task 1: Refactor Native Publication and All Internal Consumers

**Interfaces:**

```cpp
namespace record_publication {
struct Hooks {
    std::function<void()> before_write, before_security,
                          before_commit, before_cleanup;
};
struct Result {
    bool committed = false;
    std::optional<std::string> cleanup_error;
};
Result publish(const std::filesystem::path& destination,
               std::string_view payload, const Hooks& hooks = {});
}
```

- Lua: `fs.publish-record(destination, payload, opts?) -> {committed: true, cleanup-error?: string}`. Options only `test-before-write`, `test-before-security`, `test-before-commit`, `test-before-cleanup`; functions must return true. No callback overload or path writer.
- `JsonUtils.write-json!(path,data,opts?) -> true, cleanup-error?: string`; only optional `publish!` function `(path,serialized-payload) -> true, cleanup-error?`. Serialize once. No hook means the existing default atomic path; reject obsolete `atomic?` and unknown options.
- `RecordFiles({open?, publication-hooks?})`; `open` is read-only. Text uses the native-backed publisher directly; JSON supplies it through canonical JSONUtils. Writer return `true, cleanup-error?` and store APIs remain as already implemented.
- Preserve committed error precedence: notification-only → notification-failed; cleanup-only or both → storage-failed/outcome committed with detached result and relevant diagnostic strings, after cache publication and one signal attempt.

- [ ] **1. Record the actual base and preserve inherited work.** Capture HEAD, status, and the 10-file inherited Task2 diff/manifest. Adopt those changes as part of this coherent task; no unrelated user edits. Read the corrected spec and only this task/global/validation brief. Write report and complete scoped diff/manifest under `.superpowers/sdd/secure-record-publication/`. Do not retry denied orchestration helpers or create task-brief files; the committed task section is the brief.

- [ ] **2. Add behavioral RED cases before refactoring.** Change ordinary umask002 production-constructor expectations from refusal to success for default/custom roots and preexisting home0750/inner0775. Add new native/Lua payload-signature and JSON publisher tests. Demonstrate old callback API/new hook failures and the actual ordinary-path refusal; do not count drafting errors as behavioral RED.

  ```fennel
  (local calls {:count 0})
  (local (ok cleanup)
    (JsonUtils.write-json! path {:value "雪"}
      {:publish! (fn [target payload]
                   (set calls.count (+ calls.count 1))
                   (assert (= target path))
                   (assert (= (. (json.loads payload) :value) "雪"))
                   (values true "cleanup diagnostic"))}))
  (assert ok)
  (assert (= cleanup "cleanup diagnostic"))
  (assert (= calls.count 1))
  ```

- [ ] **3. Own a persistent private cleanup anchor.** Reserve `.space-publication` in each target parent. Create exclusively or open no-follow relative to its pinned parent; verify directory type, effective owner, exact POSIX0700/no unsupported security metadata, or Windows protected owner-only inheritable DACL/local non-reparse policy. Group ownership need not equal the caller's primary group when mode0700. Reject unsafe/foreign/symlink/file collisions; never chmod/take over existing entries or fall back insecurely. Refuse the reserved destination basename itself.

  Keep the anchor intentionally, even if a newly created operation fails. It is one internal metadata directory, not cleanup residue. Each attempt creates an exclusive private child directory and record beneath the retained anchor handle. Clean only its owned entries and attempt directory inside that private namespace; never delete/sweep the public anchor or another attempt. Do not compare volatile anchor times/link counts as identity. Anchor reuse and independent attempts must work.

- [ ] **4. Write payloads through POSIX handles.** Use `openat`/`mkdirat`/`fstatat` with exclusive/no-follow flags. The mkdir/open sequence must verify the opened anchor/attempt belongs to the caller with restrictive effective access and the expected identity BEFORE record bytes. Do not reject all group/other-writable ancestors. Retain relevant directory/record FDs; loop over partial writes/EINTR, check completion/flush/readback and errors. All payload bytes go through the retained private record FD, not a reconstructed pathname. Preserve supported UID/GID/mode and ACL/xattr refusal, links/type checks and final snapshot validation. Commit by handle-relative `renameat` into the original pinned target parent. Relevant namespace changes may fail before commit; no external-writer transaction is promised.

- [ ] **5. Implement exact Windows handle-relative creation/rename.** Resolve `NtCreateFile`, `NtSetInformationFile` and required status conversion/completion functions from existing ntdll; fail explicitly if absent. Use checked `OBJECT_ATTRIBUTES`/`UNICODE_STRING`, `RootDirectory` and relative leaf names; request required data/security/DELETE/SYNCHRONIZE rights and synchronous completion options. Exclusive create uses `FILE_CREATE`, directory/non-directory and reparse-open options, with protected security effective at creation. Pin handles rather than retaining the old ancestry-wide foreign-write refusal.

  Define/use the documented Native `FILE_RENAME_INFORMATION` layout (ReplaceIfExists, RootDirectory, FileNameLength, relative FileName), destination parent handle, and `FileRenameInformation`. Do not claim Win32 FILE_RENAME_INFO.RootDirectory supports non-null values. Retain the source handle; destination inspection handles must allow FILE_SHARE_DELETE or close safely before rename. Treat STATUS_PENDING as incomplete: await checked final status before latching commit. No pathname MoveFileExW/CRT/copy/delete fallback. Preserve ordinary allow/deny DACL/owner/group policy with exact checked readback or explicit unsupported refusal. Verify child-file privacy before bytes, not merely directory traversal.

- [ ] **6. Preserve outcome/cleanup truthfulness.** After phase hooks, revalidate relevant pinned identities, links, bytes, final restrictions and destination snapshot; no Lua callback after final validation before commit. Latch committed only after successful atomic completion. Close/cleanup errors after commit are diagnostics, not rollback. RAII destructors noexcept/no Lua. Public-anchor renaming cannot redirect handle-relative writes; cleanup stays in the verified private anchor. On precommit failure preserve the original plus cleanup diagnostics and leave destination/cache/revision unchanged.

- [ ] **7. Migrate JSONUtils, adapters, tests and docs coherently.** Serialize once, validate publisher type/closed options, forward both return values with no trailing `true` that discards cleanup. Preserve default two-argument JSON calls. Remove unused atomic mode, old callback signature and stage-json seam; no aliases. RecordFiles no longer writes payload through Lua pathname handles. Keep read injection and existing store files boundaries. Preserve already implemented store cache/notification ordering and editor committed-error baseline recovery.

  Move meaningful write/flush/close failures to native writer tests (real bounded OS failure fixtures where available) rather than leave inert Lua fault tests. Hooks observe/perturb native stages for security tests, not provide payload writers. Update record.tmp assumptions: native now owns one record per attempt, JSON default helper remains separate. Replace old path-probe/canonical-string tests with native identity/alias behavior assertions. Keep all long-name, corruption, bounds, revision and committed-failure invariants. Update canonical graph and SDK docs; historical reports remain chronology.

- [ ] **8. Verify required compatibility and privacy.** Test real production default/custom constructors under child-only umask022 and002, preexisting private-home/group-writable descendants, unchanged parent permissions/parent umask, create/update/text replacement/link update, exact payload and final access. Default JSON callers still write correctly; new hook serializes once and forwards cleanup; old/unknown options fail. Verify anchor reuse, exact expected entries including retained metadata, concurrent independent attempts, unsafe existing anchors and substituted public anchor names without unrelated deletion. Native phase tests must cover adversarial namespace changes before writes, intermediate privacy, Windows overwrite/sharing failures/pending completion, unsupported policy, and truthful cleanup. No case skipping or refusal-as-success for ordinary layouts.

- [ ] **9. Run focused validation and hand off for review.** Report complete inherited/new manifest, raw diff including untracked files, exact build/compile/constraints/tests and RED/GREEN, coverage rationale and constraint impact. Independent full review is mandatory for the whole coherent refactor; local/platform gaps explicitly separate from source verdict. No completion/readiness claim.

## Validation and Finishing Gates

Native freshness: `make build`, timeout14400000; `make cmake` after actual CMake changes, timeout600000. Then native project Fennel compile, repository constraints, focused tests, in that order. Standard environment:

```bash
export SKIP_KEYRING_TESTS=1
export XDG_DATA_HOME=/tmp/space/tests/xdg-data
export SPACE_DISABLE_AUDIO=1
export SPACE_ASSETS_PATH="$PWD/assets"
export FENNEL_PATH="$PWD/assets/lua/?.fnl;$PWD/assets/lua/?/init.fnl"
export FENNEL_MACRO_PATH="$FENNEL_PATH"
make fennel-check
make constraints
ctest --test-dir build -R '^test_record_publication$' --output-on-failure
./build/space -m tests.test-fs:main
./build/space -m tests.test-entity-record-persistence:main
./build/space -m tests.test-string-entities:main
./build/space -m tests.test-link-entities:main
./build/space -m tests.test-graph-entity-capabilities:main
./build/space -m tests.test-string-entity-editor:main
```

Repair nearest enclosing forms/named helpers for authoring feedback, never bypass gates. Unexpected failures require systematic investigation and reviewed fixes. After review/commit, fetch/evaluate current origin/main through git-integrator, merge safely if needed with reviewed conflict fixes, and run the exact full gate:

```bash
SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH="$PWD/assets" make test
```

Use only guarded Windows reproduction capabilities. The current wrapper only offers a full180s Wine suite and cannot select a focused module; its timeout is not a platform pass. Native Windows/macOS security evidence remains required; preserve that infrastructure limit rather than widening permissions or inferring results. Whole-branch review and applicable green PR/merge-group checks remain required. The original native SIG incident separately needs causal evidence; no successful normal run closes it.
