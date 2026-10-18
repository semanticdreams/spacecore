#ifndef SPACE_RECORD_PUBLICATION_WINE_ABI_H
#define SPACE_RECORD_PUBLICATION_WINE_ABI_H

#include <stddef.h>
#include <stdint.h>

#define SRP_ABI UINT32_C(1)
#define SRP_FEATURE_IDENTITY UINT32_C(1)
#define SRP_FEATURE_OPERATION UINT32_C(2)
#define SRP_REQUIRED_FEATURES (SRP_FEATURE_IDENTITY | SRP_FEATURE_OPERATION)
#define SRP_ARCH_X86_64 UINT32_C(0x8664)
#define SRP_ENTRY_IDENTITY UINT32_C(0)
#define SRP_ENTRY_OPERATION UINT32_C(1)

/* NTSTATUS is a Windows 32-bit signed value, including on the LP64 host. */
#define SRP_SUCCESS INT32_C(0)
#define SRP_INVALID_ARGUMENT ((int32_t)UINT32_C(0xc000000d))
#define SRP_ACCESS_DENIED ((int32_t)UINT32_C(0xc0000022))
#define SRP_UNSUPPORTED ((int32_t)UINT32_C(0xc00000bb))
#define SRP_UNSUCCESSFUL ((int32_t)UINT32_C(0xc0000001))
#define SRP_MODULE_UNAVAILABLE ((int32_t)UINT32_C(0xc0000135))
#define SRP_IDENTITY_MISMATCH ((int32_t)UINT32_C(0xc000007b))

typedef struct {
    uint32_t size, abi;
    uint64_t challenge, echo;
    uint8_t pe_build_id[32], unix_build_id[32];
    uint64_t module_device, module_inode;
    uint32_t architecture, features;
} SrpIdentity;

/* Private operation protocol; the complete pair requires both feature bits. */
#define SRP_BEGIN UINT32_C(1)
#define SRP_ADVANCE UINT32_C(2)
#define SRP_SNAPSHOT UINT32_C(3)
#define SRP_CANCEL UINT32_C(4)
#define SRP_RELEASE UINT32_C(5)
#define SRP_CONTINUE UINT32_C(0)
#define SRP_FAILED UINT32_C(1)
#define SRP_START UINT32_C(0)
#define SRP_BEFORE_WRITE UINT32_C(1)
#define SRP_BEFORE_SECURITY UINT32_C(2)
#define SRP_BEFORE_COMMIT UINT32_C(3)
#define SRP_BEFORE_CLEANUP UINT32_C(4)
#define SRP_DONE UINT32_C(5)
#define SRP_VALID UINT32_C(1)
#define SRP_COMMITTED UINT32_C(2)
#define SRP_DONE_FLAG UINT32_C(4)
#define SRP_PRIMARY_TRUNCATED UINT32_C(8)
#define SRP_CLEANUP_TRUNCATED UINT32_C(16)
#define SRP_CLEANUP_PRESENT UINT32_C(32)
#define SRP_POISONED UINT32_C(64)
#define SRP_TRANSPORT_TRUNCATED UINT32_C(128)
#define SRP_PRIMARY_ABSENT UINT32_C(0)
#define SRP_PRIMARY_PRESENT UINT32_C(1)

typedef struct { uint64_t address, size; } SrpSlice;
typedef struct { uint64_t address, capacity, required; } SrpBuffer;
typedef struct {
    uint32_t size, abi, opcode, event;
    uint64_t context, sequence;
    SrpSlice path, payload, hook_error;
    SrpBuffer primary_error, cleanup_error, transport_error;
    uint32_t reply, flags, primary_state, reserved;
} SrpCall;

#ifdef __cplusplus
#define SRP_ASSERT static_assert
#else
#define SRP_ASSERT _Static_assert
#endif
SRP_ASSERT(sizeof(SrpIdentity) == 112, "SrpIdentity size");
SRP_ASSERT(offsetof(SrpIdentity, challenge) == 8, "challenge offset");
SRP_ASSERT(offsetof(SrpIdentity, echo) == 16, "echo offset");
SRP_ASSERT(offsetof(SrpIdentity, pe_build_id) == 24, "PE ID offset");
SRP_ASSERT(offsetof(SrpIdentity, unix_build_id) == 56, "Unix ID offset");
SRP_ASSERT(offsetof(SrpIdentity, module_device) == 88, "device offset");
SRP_ASSERT(offsetof(SrpIdentity, module_inode) == 96, "inode offset");
SRP_ASSERT(offsetof(SrpIdentity, architecture) == 104, "architecture offset");
SRP_ASSERT(offsetof(SrpIdentity, features) == 108, "features offset");
SRP_ASSERT(sizeof(SrpSlice) == 16, "SrpSlice size");
SRP_ASSERT(sizeof(SrpBuffer) == 24, "SrpBuffer size");
SRP_ASSERT(sizeof(SrpCall) == 168, "SrpCall size");
SRP_ASSERT(offsetof(SrpCall, context) == 16, "context offset");
SRP_ASSERT(offsetof(SrpCall, sequence) == 24, "sequence offset");
SRP_ASSERT(offsetof(SrpCall, path) == 32, "path offset");
SRP_ASSERT(offsetof(SrpCall, payload) == 48, "payload offset");
SRP_ASSERT(offsetof(SrpCall, hook_error) == 64, "hook offset");
SRP_ASSERT(offsetof(SrpCall, primary_error) == 80, "primary error offset");
SRP_ASSERT(offsetof(SrpCall, cleanup_error) == 104, "cleanup error offset");
SRP_ASSERT(offsetof(SrpCall, transport_error) == 128, "transport error offset");
SRP_ASSERT(offsetof(SrpCall, reply) == 152, "reply offset");
SRP_ASSERT(offsetof(SrpCall, flags) == 156, "flags offset");
SRP_ASSERT(offsetof(SrpCall, primary_state) == 160, "primary state offset");
SRP_ASSERT(offsetof(SrpCall, reserved) == 164, "reserved offset");
#undef SRP_ASSERT

#endif
