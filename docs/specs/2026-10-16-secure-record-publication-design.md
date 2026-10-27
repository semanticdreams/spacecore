# Compatible secure record publication

## Authority and correction

The user authorized a native correction for Windows overwrite failures and
private-record permission weakening found during whole-branch graph review.
Ordinary default editing must continue to work: refusing normal umask002 paths
is an implementation defect, not an accepted product policy. The user clarified
that these interfaces are fresh and internal; migrate all repository callers,
refactor when useful, and do not retain draft APIs through compatibility shims.

This document supersedes its earlier pathname-callback design. Root causes and
chronology remain in `.superpowers/sdd/secure-record-publication/` reports. The
callback required overly strict ancestry because another user could redirect its
path before private writes. Preparing special test fixtures did not fix ordinary
userdata. The replacement removes the path-writing mechanism, not privacy checks.

## Selected mechanism

Three options were considered:

1. Linux `/proc/self/fd` callback paths anchor a writer but are not a portable
   macOS/Windows interface and depend on procfs availability.
2. **Selected:** native code already receives the complete serialized payload;
   write it directly through exclusively owned handles, verify and publish through
   pinned directory/file handles. JSONUtils gains a small publisher hook and
   remains the canonical JSON-writing abstraction.
3. A separate private-directory allocator still leaves subsequent pathname
   resolution redirectable and adds lifetime machinery without solving the defect.

Retain one focused native publication module. No general filesystem/ACL framework,
new runtime, production subprocess, global umask mutation, or parent chmod.

## Native contract

`fs.publish-record(destination, payload, opts?)` returns
`{committed: true, cleanup-error?: string}`. Remove the staging callback and its
native type entirely. No overloaded legacy signature or writable-path callback
escapes. Explicit test hooks may observe before-write, before-security,
before-commit and before-cleanup phases; they are not payload writers.

Pin the target directory, exclusively allocate a private workspace and record,
establish confidentiality before bytes, and write the payload through retained
handles. Check partial writes, interruptions, completion, readback and identity.
There is no JSON `.tmp` inside this native operation: it writes serialized bytes
directly. New records publish privately; existing records retain supported access
restrictions. Unsupported or unreadable security policy fails explicitly.

Reserve an internal `.space-publication` directory within each destination
parent, created exclusively or opened without following links and verified as
owned/private before use. Retain this anchor intentionally; never remove its
entry from a foreign-writable parent. Each operation owns a private attempt
directory beneath the retained anchor handle. Attempt cleanup is therefore in
a private namespace, not identity-check-then-unlink in a shared writable parent.
An empty retained anchor is metadata, not a leak or cleanup error. Do not sweep
other attempts or unrelated anchor entries, or compare volatile directory times
and link counts as identity. The anchor has no independent service/global cache.

POSIX anchors require directory type, effective-user ownership, exact0700,
supported inspectable metadata and named-entry/handle identity. Windows anchors
require a non-reparse local directory with the expected owner and protected
owner-only inheritable DACL. Reject unsafe or uninspectable preexisting entries,
including file/symlink/name collisions, without chmod or ownership takeover.
Do not widen the owner-only anchor to serve multiple UIDs in one directory;
this boundary supports the per-user owning stores in scope.

On Linux/macOS, use directory-relative `openat`/`mkdirat`/`fstatat`/`renameat`.
On Windows, use directory-handle-relative `NtCreateFile` and retained-source-handle
`NtSetInformationFile(FileRenameInformation)` with the pinned target directory.
Do not pretend Win32 FILE_RENAME_INFO.RootDirectory accepts a non-null value, or
fall back to path-based MoveFileExW when anchoring cannot be established.
Resolve the needed Native API entry points explicitly and fail if unavailable.

Group/other write bits on an ancestor are not, by themselves, grounds to refuse
ordinary editing when writes and commit are handle anchored. Preserve normal
default/custom roots under umask002 and existing home0750/inner0775 layouts.
Verify relevant namespace identity/security changes before commit; do not claim
an external-writer transaction. Other local users must not redirect private bytes
into their files. Denial of service and hostile same-identity writers are not
prevented by this boundary.

Renaming the public anchor entry cannot redirect already retained handles.
Revalidate relevant namespace changes before publication and clean only through
verified private handles, leaving foreign/substituted public entries untouched.
Record filenames/formats are unchanged, but record-empty directories may contain
the retained private anchor; store scans must continue filtering records rather
than assuming filesystem emptiness.

Preserve the existing bounded policy for destination restrictions: POSIX supported
UID/GID/mode without silently dropping unsupported ACL/xattr policy; Windows
supported owner/group/ordered allow-deny DACL, with explicit unsupported-policy
refusal. Keep new files private, never broaden access while preparing publication,
and do not delete the destination to make overwrite succeed.

Run final byte, link, identity and security checks after any phase fault hook,
with no arbitrary Lua callback between final validation and atomic commit. Latch
commit immediately after success. Fixed-entry, identity-checked, nonrecursive
cleanup owns only the attempt. Retained handle-close or cleanup failures after
commit are diagnostics, not rollback claims. No power-loss guarantee is made.

## JSON and owning integration

JSONUtils remains canonical, but its implementation is not frozen. Add the
canonical `publish!` option receiving `(path, serialized-payload)` and returning
`true, cleanup-error?`. Serialize once and forward both returns. Without that
option, unrelated repository callers retain their existing atomic write path;
this is a bounded integration choice, not a public compatibility commitment.
The unused `atomic? false` option is removed after a full caller audit; update its
documentation and reject old/unknown options rather than add aliases.

RecordFiles supplies the native-backed publisher for JSON and uses it directly
for text. Its `open` injection remains read-only. Remove `stage-json!` and all
production pathname-write/open/flush/close seams; migrate fault coverage to native
writer tests and the existing owning `files` injection boundary.

Preserve the already implemented store ordering: native commit, cache/revision
publication, one normal notification attempt, then explicit committed cleanup or
notification error. Preserve detached results, exact text, graph DTOs and the
editor's committed-baseline advancement. Migrate all repo callers/tests/docs of
the draft native and adapter APIs together, without compatibility overloads.

## Acceptance

- Unmodified production constructors create, update and replace text/link records
  under both umask022 and002, using default/custom roots and a preexisting private
  home with group-writable descendants. Do not treat refusal as a passing case.
- Verify confidentiality during native writes and final0600/restricted access,
  real overwrite on Windows, supported policy preservation, unsafe stage/namespace
  substitutions, unsupported-policy failure, exact bytes and long basenames.
- Verify anchor reuse, independent attempts, unsafe preexisting anchors, public
  anchor substitution without unrelated deletion, and exact expected entries
  including retained metadata with no owned attempt residue after normal cleanup.
- Precommit faults preserve destination and cache/revision. Postcommit faults
  publish cache/revision, attempt notification, and return truthful committed data.
- Native and Fennel tests cover the new signature, strict hook validation,
  serialization-once and second-return propagation, obsolete-option rejection,
  ordinary JSON callers, graph operations and full/preview editor recovery.
- Build native changes, run native Fennel compile then constraints then focused
  native/store/graph/editor tests; independently review; rerun the full local suite
  and platform gates. Linux/Wine/source results are not native Windows/macOS proof.

The historical native timeout/shutdown SIGSEGV remains separately open. This
refactor, its changed safety budget, and passing normal runs do not close it.
