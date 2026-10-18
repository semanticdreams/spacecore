/* Wine9-only PE bridge. Initialization is explicit, outside DllMain.
 * Matched installed public headers supply NT types and MemoryWineUnixFuncs.
 */
#define __WINESRC__
#include <windef.h>
#include <winbase.h>
#include <winternl.h>
#include <string.h>

#include "record_publication_wine_abi.h"
#include "record_publication_wine_authority.h"

#ifndef SRP_BUILD_ID_BYTES
#error "The fixed publication builder must supply SRP_BUILD_ID_BYTES"
#endif
#if !defined(_WIN64) || !defined(__x86_64__)
#error "The publication PE module supports only win64 x86_64"
#endif

/* Minimal private contract from Wine 9.0, not a vendored internal header:
 * https://github.com/wine-mirror/wine/blob/wine-9.0/include/wine/unixlib.h
 * The source defines a UINT64 opaque handle and NTSTATUS WINAPI dispatch.
 * Ubuntu intentionally does not install that private source header.
 */
typedef uint64_t SrpUnixHandle;
typedef NTSTATUS (WINAPI *SrpUnixCall)(SrpUnixHandle, unsigned int, void*);
_Static_assert(sizeof(SrpUnixHandle) == 8, "Wine9 opaque Unix handle size");
_Static_assert(_Alignof(SrpUnixHandle) == 8, "Wine9 opaque Unix handle alignment");
_Static_assert(sizeof(NTSTATUS) == 4, "Wine9 status width");
_Static_assert(sizeof(SrpUnixCall) == 8 && _Alignof(SrpUnixCall) == 8, "Wine9 x64 dispatch pointer layout");
_Static_assert(MemoryWineUnixFuncs == 1000, "Wine9 Unix function query class");
static const uint8_t build_id[32] = SRP_BUILD_ID_BYTES;
__declspec(dllexport) const uint8_t SpaceRecordPublicationPeBuildId[32] = SRP_BUILD_ID_BYTES;

__declspec(dllexport) int32_t WINAPI SpaceRecordPublicationCall(uint32_t entry, void* args)
{
    HMODULE self = NULL, ntdll;
    SrpUnixHandle handle = 0;
    NTSTATUS status;
    SrpIdentity result = {0};
    SrpIdentity* input = args;
    __typeof__(&NtQueryVirtualMemory) query;
    SrpUnixCall dispatch;
    if (entry == SRP_ENTRY_IDENTITY) {
        if (!input || input->size != sizeof(*input) || input->abi != SRP_ABI) return SRP_INVALID_ARGUMENT;
    } else if (entry == SRP_ENTRY_OPERATION) {
        SrpCall *call = args;
        if (!call || call->size != sizeof(*call) || call->abi != SRP_ABI) return SRP_INVALID_ARGUMENT;
        if (call->opcode < SRP_BEGIN || call->opcode > SRP_RELEASE
            || (call->opcode == SRP_ADVANCE && call->event > SRP_BEFORE_CLEANUP)) return SRP_INVALID_ARGUMENT;
        if (call->opcode == SRP_BEGIN || (call->opcode == SRP_ADVANCE && call->event <= SRP_BEFORE_COMMIT)) {
            /* Authority precedes native payload/range validation. Recovery routes
             * remain callable after loss; native exact phase/sequence rejects lies. */
            const DWORD error = space_record_publication_check_authority();
            if (error) {
                call->context = call->sequence = 0;
                call->event = SRP_START;
                call->flags = 0;
                call->primary_state = SRP_PRIMARY_ABSENT;
                call->primary_error.required = call->cleanup_error.required = call->transport_error.required = 0;
                call->path = call->payload = call->hook_error = (SrpSlice){0};
                call->reply = SRP_CONTINUE;
                call->reserved = 0;
                /* Only the checked control frame is writable here. Never follow
                 * caller text pointers before native range validation. */
                SetLastError(error);
                return SRP_ACCESS_DENIED;
            }
        }
    } else return SRP_UNSUPPORTED;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            (LPCWSTR)(uintptr_t)&SpaceRecordPublicationCall, &self)) return SRP_MODULE_UNAVAILABLE;
    ntdll = GetModuleHandleW(L"ntdll.dll");
    if (!ntdll) return SRP_MODULE_UNAVAILABLE;
    query = (__typeof__(query))GetProcAddress(ntdll, "NtQueryVirtualMemory");
    dispatch = (SrpUnixCall)GetProcAddress(ntdll, "__wine_unix_call");
    if (!query || !dispatch) return SRP_MODULE_UNAVAILABLE;
    /* Wine9 checks the exact input length but does not set ReturnLength for
     * this class. Match winecrt0/unix_lib.c: NULL, not a fabricated length check.
     * The opaque handle belongs to our own module; it is NOT a PE-callable ptr.
     */
    status = query(GetCurrentProcess(), self, MemoryWineUnixFuncs, &handle, sizeof(handle), NULL);
    if (status != 0) return status;
    if (!handle) return SRP_MODULE_UNAVAILABLE;
    if (entry == SRP_ENTRY_OPERATION) return dispatch(handle, SRP_ENTRY_OPERATION, args);
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
