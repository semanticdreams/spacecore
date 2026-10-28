# Linux record-publication SELinux subset

This is a read-only extension of [record publication](record-publication.md),
not a relabeling service. Space never writes a SELinux xattr, sets a task creation
context, disables enforcement, repairs directory policy, or loads kernel policy.
Unknown xattrs (including ACL/capability metadata) still cause explicit refusal.

## Accepted metadata and ownership

The only additional accepted attribute is exactly `security.selinux`. Its counted
bytes must be nonempty, bounded, and end in exactly one NUL. Two attribute
enumerations/reads bracketed by inode/security checks must agree. Absence is
distinct from denied, malformed, truncated or unstable inspection. Parent, private
anchor and workspace retain independent label baselines; they need not share a
label. Successful validation during emergency cleanup allocates no heap memory.

An existing destination retains its complete initial label presence/bytes along
with its uid/gid/mode/stat snapshot. Its stage must already match before payload
bytes and after owner/mode reproduction; the destination and stage are rechecked
after the final hook. Space will not copy or repair a mismatching label.

New labeled records use this deliberately conservative initial subset:

- The retained parent and stage descriptors must associate unambiguously with the
  same current traditional mount ID, a `seclabel` tmpfs mount, and tmpfs filesystem
  magic. Exact mount/superblock tokens reject `context=`, `fscontext=`,
  `rootcontext=` and `defcontext=` options. Other filesystems are not predicted.
- A canonical final-parent pathname remains associated with the pinned inode.
  Public-parent substitution therefore refuses a **new labeled** record, without
  redirecting any bytes. Existing-target replacement remains handle-relative.
- Fresh successfully loaded file-context backends have first priority. A positive
  fixed default always wins; mismatch refuses, never falls through. Only an
  authenticated negative lookup (unmatched or `<<none>>`) allows kernel fallback.
  Failed loading/reading/compilation/matching is not a negative lookup.
- Fallback uses the kernel's name-aware creation query for the fresh calling-task
  context, actual pinned parent context, nonzero file class and **final basename**.
  Raw calling-task procattr reads avoid cached libselinux getter values. Any active
  fscreate override or unavailable/malformed task inspection refuses.
- Kernel policy generation/enforcement, task/fscreate state, mount association,
  parent label and freshly queried effective file-context result/provenance are
  rechecked. Revalidation compares with immutable acquisition baselines. A fresh
  second default lookup also brackets each computation; a digest is not sole
  authority. No cached backend can hide newly appearing optional files.

The stage must already equal the complete authorized context immediately before
bytes, after owner/mode preparation and after the final hook. Name-dependent
transitions or private-directory labels can make this impossible; the supported
behavior is refusal, not relabeling. Separate validation/rename syscalls cannot
detect every transient privileged change; no stronger atomic policy claim is made.
The existing immediate committed latch and cleanup/error truth remain unchanged.

## Private corrected lookup dependency

Linux CMake builds use a private, pinned public-domain libselinux 3.9 archive:

- Source: `https://github.com/SELinuxProject/selinux/releases/download/3.9/libselinux-3.9.tar.gz`
- SHA256: `e7ee2c01dba64a0c35c9d7c9c0e06209d8186b325b0638a0d83f915cc3c101e8`
- License: [`cmake/libselinux-LICENSE`](../../../cmake/libselinux-LICENSE).
- Exact idempotent failure-propagation patch:
  [`cmake/patch-private-selinux.py`](../../../cmake/patch-private-selinux.py).

The upstream file backend conflates regex execution failure and no-match as
`ENOENT`. Our pinned patch preserves regex compilation/execution, context
finalization, substitution-allocation and file-inspection/read failures as errors;
only genuine negatives remain eligible for fallback. Source hashes and expected
patch shapes are verified; unknown modifications fail configuration. Download,
patch or build failure never selects the system's unpatched backend.

Only the upstream `src` static archive is built, with explicit compiler/archive
tools, PCRE2 flags, PIC/hidden visibility and disabled setrans/X11/Android backends.
No upstream install, relabel, shared-library, bindings or utilities target runs.
Build dependencies include PCRE2 and libsepol development files. Build flags and
patched sources participate in rebuild dependencies.

Hidden references force private extraction; archive-specific final-link exclusion
localizes incorporated symbols. A system libselinux used by another component may
coexist and is not replaced. `test_selinux_lookup` tests both load orders with a
global system DSO and injects a real PCRE2 runtime failure, in executable and shared
consumers. `test_private_selinux_symbols` checks the actual engine and every final
native test consumer against the complete private archive symbol inventory;
none may appear as dynamic imports or exports. Publication never uses an unpatched
system fallback. Native publication, operation, ABI and bridge-driver consumers
link the same authority module.

Darwin and native Windows do not use this Linux dependency. Separately built Wine
host helpers without this capability retain the blanket unsupported-metadata
refusal; they do not silently acquire the system backend. Their fixed source
identity includes the authority header. No support is inferred merely from an
Enforcing host, readable label, filesystem name or successful subscription/build.
