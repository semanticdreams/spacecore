#ifndef SPACE_RECORD_PUBLICATION_WINE_SUPPORT_H
#define SPACE_RECORD_PUBLICATION_WINE_SUPPORT_H

/* Test-only Wine9 x64 contract. No dependency on, or commands in, production ABI.
 * All storage is inline and caller-owned for the synchronous call. No pointers,
 * callbacks, CRT ownership, native-width scalars or exceptions cross this ABI.
 */
#include <stddef.h>
#include <stdint.h>

#define SRPT_ABI UINT32_C(2)
#define SRPT_ARCH_X86_64 UINT32_C(0x8664)
#define SRPT_FEATURES UINT32_C(7) /* identity, bounded fixtures, closed launch */
#define SRPT_ENTRY_IDENTITY UINT32_C(0)
#define SRPT_ENTRY_FIXTURE UINT32_C(1)
#define SRPT_ENTRY_LAUNCH UINT32_C(2)
#define SRPT_BOUND 4096
#define SRPT_SUCCESS INT32_C(0)
#define SRPT_INVALID_ARGUMENT ((int32_t)UINT32_C(0xc000000d))
#define SRPT_UNSUCCESSFUL ((int32_t)UINT32_C(0xc0000001))
#define SRPT_MODULE_UNAVAILABLE ((int32_t)UINT32_C(0xc0000135))
#define SRPT_IDENTITY_MISMATCH ((int32_t)UINT32_C(0xc000007b))

typedef struct {
    uint32_t size, abi;
    uint64_t challenge, echo;
    uint8_t pe_build_id[32], unix_build_id[32];
    uint64_t module_device, module_inode;
    uint32_t architecture, features;
} SrptIdentity;

#define SRPT_RETAIN UINT32_C(1)
#define SRPT_RELEASE UINT32_C(2)
#define SRPT_OBSERVE UINT32_C(3)
#define SRPT_MKDIR UINT32_C(4)
#define SRPT_CREATE UINT32_C(5)
#define SRPT_WRITE UINT32_C(6)
#define SRPT_CHMOD UINT32_C(7)
#define SRPT_LINK UINT32_C(8)
#define SRPT_SYMLINK UINT32_C(9)
#define SRPT_RENAME UINT32_C(10)
#define SRPT_UNLINK UINT32_C(11)
#define SRPT_XATTR UINT32_C(12)
#define SRPT_SET_GID UINT32_C(13)
#define SRPT_RMDIR UINT32_C(14)

/* RETAIN alone accepts an absolute host path, opening each component nofollow.
 * The final root must be current-UID, mode0700. At most64 live nonrecycled IDs.
 * RELEASE closes only; it never deletes/adopts the root or its contents.
 * Everything else uses a retained root and relative names (no empty components,
 * dot/dotdot, trailing slash or absolute forms). Only OBSERVE permits empty path
 * to inspect the root itself. Root metadata is never mutated.
 *
 * OBSERVE returns actual stat fields. Regular file data is the exact bounded
 * chunk at offset (at most4096bytes; file_size reports the full size). Directory
 * data is NUL-separated child names (excluding dot/dotdot); order is unspecified,
 * offset must be zero, and oversized listings fail explicitly. Symlinks are
 * lstat-only, never followed. Only regular-file OBSERVE accepts a nonzero offset.
 * CREATE is exclusive; WRITE truncates a verified owned single-link regular file.
 * CHMOD/SET_GID/XATTR also require owned single-link regular file or directory.
 * XATTR sets only user.space-publication-test to the supplied bytes, for unsafe
 * metadata refusals. SYMLINK creates path -> other; LINK/RENAME use path -> other.
 * SET_GID is limited to the effective/supplementary host groups (no UID takeover).
 * Modes are explicit0777-bounded inputs; creation still obeys the caller's umask.
 * os_error is errno on host failures, zero on protocol refusals. No diagnostics
 * disclose fixture paths, and no partial read/list is reported as success.
 */
typedef struct {
    uint32_t size, abi, opcode, reserved;
    uint64_t root;
    uint32_t mode, gid, data_size, os_error;
    uint64_t device, inode, links, file_size;
    uint32_t uid, reserved2;
    uint64_t offset;
    char path[SRPT_BOUND], other[SRPT_BOUND];
    uint8_t data[SRPT_BOUND];
} SrptCall;

#define SRPT_CONFIGURE UINT32_C(1)
#define SRPT_RUN UINT32_C(2)
#define SRPT_PHASE_INPUT UINT32_C(0)
#define SRPT_PHASE_CONTEXT UINT32_C(1)
#define SRPT_PHASE_LAYOUT UINT32_C(2)
#define SRPT_PHASE_RUNTIME UINT32_C(3)
#define SRPT_PHASE_ENVIRONMENT UINT32_C(4)
#define SRPT_PHASE_SPAWN UINT32_C(5)
#define SRPT_PHASE_WAIT UINT32_C(6)
#define SRPT_PHASE_TERMINATE UINT32_C(7)
#define SRPT_PHASE_REAP UINT32_C(8)
#define SRPT_PHASE_COMPLETE UINT32_C(9)
#define SRPT_OUTCOME_UNSET UINT32_C(0)
#define SRPT_OUTCOME_COMPLETED UINT32_C(1)
#define SRPT_OUTCOME_EXITED_OR_SIGNALLED UINT32_C(2)
#define SRPT_OUTCOME_TIMED_OUT_AND_REAPED UINT32_C(3)
#define SRPT_OUTCOME_HOST_FAILURE UINT32_C(4)
#define SRPT_OUTCOME_OWNERSHIP_UNCERTAIN UINT32_C(5)

/* CONFIGURE: case0/retained TEMP; RUN: ordered case1..5/one retained fixture.
 * Bindings are independently checked in Unix; no path, argv, env or timeout is
 * selected by this frame. All outputs/reserved must be zero on input. An output
 * exit_code of UINT32_MAX means no normal child exit was observed.
 */
typedef struct {
    uint32_t size, abi, action, case_id;
    uint64_t root;
    uint8_t production_build_id[32], support_build_id[32];
    uint64_t production_device, production_inode, support_device, support_inode;
    uint32_t phase, os_error, exit_code, term_signal, outcome, reserved;
    uint32_t remaining_ms, reserved2;
} SrptLaunch;

#ifdef __cplusplus
#define SRPT_ASSERT static_assert
#define SRPT_ALIGNOF alignof
#else
#define SRPT_ASSERT _Static_assert
#define SRPT_ALIGNOF _Alignof
#endif
SRPT_ASSERT(sizeof(SrptIdentity) == 112, "test identity size");
SRPT_ASSERT(offsetof(SrptIdentity, challenge) == 8, "challenge offset");
SRPT_ASSERT(offsetof(SrptIdentity, echo) == 16, "echo offset");
SRPT_ASSERT(offsetof(SrptIdentity, pe_build_id) == 24, "PE ID offset");
SRPT_ASSERT(offsetof(SrptIdentity, unix_build_id) == 56, "Unix ID offset");
SRPT_ASSERT(offsetof(SrptIdentity, module_device) == 88, "device offset");
SRPT_ASSERT(offsetof(SrptIdentity, module_inode) == 96, "inode offset");
SRPT_ASSERT(offsetof(SrptIdentity, architecture) == 104, "architecture offset");
SRPT_ASSERT(offsetof(SrptIdentity, features) == 108, "features offset");
SRPT_ASSERT(sizeof(SrptCall) == 12376, "fixture frame size");
SRPT_ASSERT(offsetof(SrptCall, root) == 16, "root offset");
SRPT_ASSERT(offsetof(SrptCall, mode) == 24, "mode offset");
SRPT_ASSERT(offsetof(SrptCall, gid) == 28, "gid offset");
SRPT_ASSERT(offsetof(SrptCall, data_size) == 32, "data size offset");
SRPT_ASSERT(offsetof(SrptCall, os_error) == 36, "errno offset");
SRPT_ASSERT(offsetof(SrptCall, device) == 40, "device offset");
SRPT_ASSERT(offsetof(SrptCall, inode) == 48, "inode offset");
SRPT_ASSERT(offsetof(SrptCall, links) == 56, "links offset");
SRPT_ASSERT(offsetof(SrptCall, file_size) == 64, "file size offset");
SRPT_ASSERT(offsetof(SrptCall, uid) == 72, "uid offset");
SRPT_ASSERT(offsetof(SrptCall, reserved2) == 76, "reserved offset");
SRPT_ASSERT(offsetof(SrptCall, offset) == 80, "read offset");
SRPT_ASSERT(offsetof(SrptCall, path) == 88, "path offset");
SRPT_ASSERT(offsetof(SrptCall, other) == 4184, "other offset");
SRPT_ASSERT(offsetof(SrptCall, data) == 8280, "data offset");
SRPT_ASSERT(sizeof(SrptLaunch) == 152, "launch frame size");
SRPT_ASSERT(SRPT_ALIGNOF(SrptLaunch) == 8, "launch alignment");
SRPT_ASSERT(offsetof(SrptLaunch, size) == 0, "launch size offset");
SRPT_ASSERT(offsetof(SrptLaunch, abi) == 4, "launch ABI offset");
SRPT_ASSERT(offsetof(SrptLaunch, action) == 8, "launch action offset");
SRPT_ASSERT(offsetof(SrptLaunch, case_id) == 12, "launch case offset");
SRPT_ASSERT(offsetof(SrptLaunch, root) == 16, "launch root offset");
SRPT_ASSERT(offsetof(SrptLaunch, production_build_id) == 24, "launch production ID offset");
SRPT_ASSERT(offsetof(SrptLaunch, support_build_id) == 56, "launch support ID offset");
SRPT_ASSERT(offsetof(SrptLaunch, production_device) == 88, "launch production device offset");
SRPT_ASSERT(offsetof(SrptLaunch, production_inode) == 96, "launch production inode offset");
SRPT_ASSERT(offsetof(SrptLaunch, support_device) == 104, "launch support device offset");
SRPT_ASSERT(offsetof(SrptLaunch, support_inode) == 112, "launch support inode offset");
SRPT_ASSERT(offsetof(SrptLaunch, phase) == 120, "launch phase offset");
SRPT_ASSERT(offsetof(SrptLaunch, os_error) == 124, "launch errno offset");
SRPT_ASSERT(offsetof(SrptLaunch, exit_code) == 128, "launch exit offset");
SRPT_ASSERT(offsetof(SrptLaunch, term_signal) == 132, "launch signal offset");
SRPT_ASSERT(offsetof(SrptLaunch, outcome) == 136, "launch outcome offset");
SRPT_ASSERT(offsetof(SrptLaunch, reserved) == 140, "launch reserved offset");
SRPT_ASSERT(offsetof(SrptLaunch, remaining_ms) == 144, "launch remaining offset");
SRPT_ASSERT(offsetof(SrptLaunch, reserved2) == 148, "launch reserved2 offset");
#undef SRPT_ALIGNOF
#undef SRPT_ASSERT
#endif
