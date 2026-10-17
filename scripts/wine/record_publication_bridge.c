/* Wine9-only PE bridge. Initialization is explicit, outside DllMain.
 * The matched Wine headers supply MemoryWineUnixFuncs and unixlib_handle_t.
 */
#define __WINESRC__
#include <windef.h>
#include <winbase.h>
#include <winternl.h>
#include <wine/unixlib.h>
#include <string.h>

#include "record_publication_wine_abi.h"

#ifndef SRP_BUILD_ID_BYTES
#error "The fixed publication builder must supply SRP_BUILD_ID_BYTES"
#endif
#if !defined(_WIN64) || !defined(__x86_64__)
#error "The publication PE module supports only win64 x86_64"
#endif

_Static_assert(sizeof(unixlib_handle_t) == 8, "Wine9 opaque Unix handle size");
_Static_assert(sizeof(NTSTATUS) == 4, "Wine9 status width");
static const uint8_t build_id[32] = SRP_BUILD_ID_BYTES;
__declspec(dllexport) const uint8_t SpaceRecordPublicationPeBuildId[32] = SRP_BUILD_ID_BYTES;

__declspec(dllexport) int32_t WINAPI SpaceRecordPublicationCall(uint32_t entry, void* args)
{
    HMODULE self = NULL, ntdll;
    unixlib_handle_t handle = 0;
    NTSTATUS status;
    SrpIdentity result = {0};
    SrpIdentity* input = args;
    __typeof__(&NtQueryVirtualMemory) query;
    __typeof__(&__wine_unix_call) dispatch;
    if (entry != SRP_ENTRY_IDENTITY) return SRP_UNSUPPORTED;
    if (!input || input->size != sizeof(*input) || input->abi != SRP_ABI) return SRP_INVALID_ARGUMENT;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            (LPCWSTR)(uintptr_t)&SpaceRecordPublicationCall, &self)) return SRP_MODULE_UNAVAILABLE;
    ntdll = GetModuleHandleW(L"ntdll.dll");
    if (!ntdll) return SRP_MODULE_UNAVAILABLE;
    query = (__typeof__(query))GetProcAddress(ntdll, "NtQueryVirtualMemory");
    dispatch = (__typeof__(dispatch))GetProcAddress(ntdll, "__wine_unix_call");
    if (!query || !dispatch) return SRP_MODULE_UNAVAILABLE;
    /* Wine9 checks the exact input length but does not set ReturnLength for
     * this class. Match winecrt0/unix_lib.c: NULL, not a fabricated length check.
     * The opaque handle belongs to our own module; it is NOT a PE-callable ptr.
     */
    status = query(GetCurrentProcess(), self, MemoryWineUnixFuncs, &handle, sizeof(handle), NULL);
    if (status != 0) return status;
    if (!handle) return SRP_MODULE_UNAVAILABLE;
    result.size = sizeof(result);
    result.abi = SRP_ABI;
    result.challenge = input->challenge;
    memcpy(result.pe_build_id, build_id, sizeof(build_id));
    status = dispatch(handle, SRP_ENTRY_IDENTITY, &result);
    if (status != 0) return status;
    if (result.size != sizeof(result) || result.abi != SRP_ABI || result.echo != result.challenge
        || result.architecture != SRP_ARCH_X86_64 || result.features != SRP_REQUIRED_FEATURES
        || !result.module_inode || memcmp(result.unix_build_id, build_id, sizeof(build_id)) != 0
        || memcmp(result.pe_build_id, build_id, sizeof(build_id)) != 0) return SRP_IDENTITY_MISMATCH;
    *input = result;
    return SRP_SUCCESS;
}
