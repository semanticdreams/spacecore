#ifndef SPACE_RECORD_PUBLICATION_WINE_ABI_H
#define SPACE_RECORD_PUBLICATION_WINE_ABI_H

#include <stddef.h>
#include <stdint.h>

#define SRP_ABI UINT32_C(1)
#define SRP_FEATURE_IDENTITY UINT32_C(1)
#define SRP_FEATURE_OPERATION UINT32_C(2)
#define SRP_REQUIRED_FEATURES SRP_FEATURE_IDENTITY
#define SRP_ARCH_X86_64 UINT32_C(0x8664)
#define SRP_ENTRY_IDENTITY UINT32_C(0)
#define SRP_ENTRY_OPERATION UINT32_C(1)

/* NTSTATUS is a Windows 32-bit signed value, including on the LP64 host. */
#define SRP_SUCCESS INT32_C(0)
#define SRP_INVALID_ARGUMENT ((int32_t)UINT32_C(0xc000000d))
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
#undef SRP_ASSERT

#endif
