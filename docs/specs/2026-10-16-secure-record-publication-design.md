# Secure record publication correction

## Authority and scope

The user explicitly approved a narrow native publication boundary after final
whole-branch review of uniform graph capabilities found two defects: CRT rename
does not reliably overwrite existing files on Windows, and ordinary staging can
expose private content or replace a restricted destination with broader access.
This supplements `2026-10-15-uniform-graph-access-design.md`; it does not change
the graph contract or authorize an ACL framework or unrelated filesystem repair.

The diagnosis and unavailable existing primitives are recorded in
`.superpowers/sdd/graph-capabilities/publication-fix-report.md`. Existing native
atomic replacement applies permissions after writing; it cannot supply the
required before-content privacy. The existing JSON helper remains canonical.

## Alternatives and selected boundary

1. Adapt `fs.rename` locally: fixes the CRT/void-return issue but not security.
2. Add a native file writer and change JSON helper write hooks: workable, but
   introduces shared-helper surface and two coordinated staging paths.
3. **Selected:** one scoped native publication operation owns an exclusive private
   sibling directory, calls the current checked text/JSON writer inside it,
   verifies bytes and security, and performs atomic publication.

This reuses `json-utils.write-json!` unchanged while protecting both its destination
and `.tmp` name. Directory ownership is local to a synchronous operation, not a
new Lua lifetime/service or a general persistence abstraction.

## Contract

Add `fs.publish-record(destination, expected-bytes, stage!, opts?)` returning
`{committed: true, cleanup-error?: string}`. `stage!` receives the single owned
staging file path. Callback failure, mismatch, security-preparation failure, or
publication failure before commit raises an explicit error. Successful atomic
replacement is the commit point; subsequent cleanup failure must not be reported
as a rolled-back mutation.

The operation owns short, exclusive same-directory staging independent of the
destination basename. Create restrictions before invoking any writer or storing
private bytes. The callback's record path starts absent; only the JSON temporary
is privately precreated. Thus the unchanged JSON helper renames to a new record,
without depending on inner overwrite behavior. The only expected entries are
the fixed record and JSON temporary. Keep cleanup attempt-local, identity checked,
and nonrecursive; never
remove the destination to make publication work. Do not expose an independently
owned stage to Lua GC or retain callbacks after the synchronous call.

Use a focused native module behind the existing filesystem binding. RecordFiles
retains checked write/flush/close behavior, byte verification, failure injection,
and successful boolean return. Replace its old rename seam with phase hooks
at the new owning boundary, migrating tests instead of keeping a bypass alias.

## Access restrictions and platform behavior

- POSIX staging directory is private (0700). It protects effective access to
  intermediate files even if the unchanged writer's creation mode inside it is
  broader; no private content is publicly reachable. Newly created records must
  have verified private mode0600 before publication outside that directory.
- Existing destinations retain their owner/group/mode restrictions. Inspect
  additional ACL/security policy rather than assuming mode bits describe it all;
  preserve supported restrictions or fail closed before publication. Do not
  silently drop restrictive ACLs or broaden access.
- Windows staging uses an explicit owner-restricted, inheritable protected DACL,
  not an assumption about default temporary-file permissions. Preserve the
  existing destination's supported owner/group/DACL and restrictive policy before
  atomic overwrite, with checked native security APIs. Unsupported/uninspectable
  policies fail explicitly; no generic ACL editing interface is introduced.
- Final replacement must work on existing Windows destinations, without a
  delete-first or cross-volume-copy fallback. Do not rely on CRT `os.rename`.
- Verify regular-file identities, short staging ownership and destination policy
  before commit. Reject symlink/reparse/hard-link cases where identity/security
  preservation cannot be guaranteed. Do not follow a substituted staging entry.
- The path-based callback must operate under trusted, stable ancestry. Defend
  against other local users accessing or substituting private staging. Hostile
  same-identity writers and general external-writer transactions remain excluded.
- Never change process-wide umask, invoke a production shell, apply restrictions
  only after publicly writing content, or ignore a security-check failure.

Supported platform-policy details and exact native validation must be explicit in
the plan and code; complex unsupported policies may be rejected rather than
approximately copied. This is not metadata migration or a power-loss guarantee.

## Failure and cache ordering

All precommit failures leave destination bytes/access and owning cache/revision
unchanged. Native RAII cleans only this attempt even after a Lua callback throws.
Fault hooks are local test seams before security, commit, and cleanup; the final
security check has no intervening arbitrary Lua callback before commit.

After commit, return committed status before handling cleanup diagnostics. Stores
must still publish their cache/revision and follow existing notification behavior.
Cleanup diagnostics must be surfaced without claiming rollback or encouraging a
blind retry. Existing store APIs, formats, exact text and graph DTOs are unchanged.

## Acceptance and validation

1. Existing text/link create, unconditional update and revision replacement work
   through the new default boundary, including long destination basenames.
2. POSIX child-process umask022 tests start from0600 files and verify final access
   is0600 for text replacement/update and link update. Inspect privacy while both
   staging and JSON `.tmp` contain bytes, not just after commit.
3. Security/verification/publication faults preserve old bytes, access, cached
   object identity/content/revision and unrelated temporary artifacts.
4. Test destination security/identity changes before commit, unsafe links, Lua
   errors, owned cleanup and honest postcommit cleanup outcomes.
5. Guarded Windows/Wine tests cover existing overwrite and supported ACL
   preservation including deny restrictions; native Windows validation remains
   authoritative. No ad-hoc dependency installation or broad permission prompts.
6. Build native changes, then project-native Fennel compile, constraints and
   focused native/store/graph/editor tests. Independent review precedes commit;
   rerun the full local suite after reviewed fixes.

The previously observed native timeout/shutdown SIGSEGV remains a separate open
incident. This correction and its passing tests do not close that investigation.
