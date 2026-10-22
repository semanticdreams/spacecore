/* Test-only Wine9 forwarding, initialized explicitly outside DllMain. */
#define __WINESRC__
#include <windef.h>
#include <winbase.h>
#include <winternl.h>
#include <string.h>
#include "record_publication_wine_support.h"

#ifndef SRPT_BUILD_ID_BYTES
#error "The test support builder must supply SRPT_BUILD_ID_BYTES"
#endif
#if !defined(_WIN64) || !defined(__x86_64__)
#error "Test support requires win64 x86_64"
#endif

/* Minimal declarations from Wine9, exactly as the production mechanism:
 * https://github.com/wine-mirror/wine/blob/wine-9.0/include/wine/unixlib.h
 * The returned table handle is opaque, never a PE-callable function pointer.
 */
typedef uint64_t SrptUnixHandle;
typedef NTSTATUS (WINAPI *SrptUnixCall)(SrptUnixHandle, unsigned int, void*);
_Static_assert(sizeof(SrptUnixHandle) == 8 && _Alignof(SrptUnixHandle) == 8, "Wine9 handle layout");
_Static_assert(sizeof(NTSTATUS) == 4, "Wine9 status width");
_Static_assert(sizeof(SrptUnixCall) == 8 && _Alignof(SrptUnixCall) == 8, "Wine9 dispatch layout");
_Static_assert(MemoryWineUnixFuncs == 1000, "Wine9 query class");
static const uint8_t build_id[32] = SRPT_BUILD_ID_BYTES;
__declspec(dllexport) const uint8_t SpaceRecordPublicationTestsPeBuildId[32] = SRPT_BUILD_ID_BYTES;

__declspec(dllexport) int32_t WINAPI SpaceRecordPublicationTestsCall(uint32_t entry, void* args)
{
    HMODULE self = NULL, ntdll;
    SrptUnixHandle handle = 0;
    SrptUnixCall dispatch;
    __typeof__(&NtQueryVirtualMemory) query;
    NTSTATUS status;
    SrptIdentity result = {0};
    SrptIdentity* input = args;
    if (entry == SRPT_ENTRY_IDENTITY) {
        if (!input || input->size != sizeof(*input) || input->abi != SRPT_ABI) return SRPT_INVALID_ARGUMENT;
    } else if (entry == SRPT_ENTRY_FIXTURE) {
        const SrptCall* call = args;
        if (!call || call->size != sizeof(*call) || call->abi != SRPT_ABI
            || call->opcode < SRPT_RETAIN || call->opcode > SRPT_RMDIR) return SRPT_INVALID_ARGUMENT;
    } else return SRPT_INVALID_ARGUMENT;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            (LPCWSTR)(uintptr_t)&SpaceRecordPublicationTestsCall, &self)) return SRPT_MODULE_UNAVAILABLE;
    ntdll = GetModuleHandleW(L"ntdll.dll");
    if (!ntdll) return SRPT_MODULE_UNAVAILABLE;
    query = (__typeof__(query))GetProcAddress(ntdll, "NtQueryVirtualMemory");
    dispatch = (SrptUnixCall)GetProcAddress(ntdll, "__wine_unix_call");
    if (!query || !dispatch) return SRPT_MODULE_UNAVAILABLE;
    /* Wine9 does not set ReturnLength for this class; match winecrt0/unix_lib.c. */
    status = query(GetCurrentProcess(), self, MemoryWineUnixFuncs, &handle, sizeof(handle), NULL);
    if (status != 0) return status;
    if (!handle) return SRPT_MODULE_UNAVAILABLE;
    if (entry == SRPT_ENTRY_FIXTURE) return dispatch(handle, SRPT_ENTRY_FIXTURE, args);
    result.size = sizeof(result);
    result.abi = SRPT_ABI;
    result.challenge = input->challenge;
    memcpy(result.pe_build_id, build_id, sizeof(build_id));
    status = dispatch(handle, SRPT_ENTRY_IDENTITY, &result);
    if (status != 0) return status;
    if (result.size != sizeof(result) || result.abi != SRPT_ABI || result.challenge != input->challenge
        || result.echo != result.challenge
        || result.architecture != SRPT_ARCH_X86_64 || result.features != SRPT_FEATURES || !result.module_inode
        || memcmp(result.pe_build_id, build_id, sizeof(build_id)) != 0
        || memcmp(result.unix_build_id, build_id, sizeof(build_id)) != 0) return SRPT_IDENTITY_MISMATCH;
    *input = result;
    return SRPT_SUCCESS;
}
