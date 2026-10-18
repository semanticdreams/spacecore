/* Inert WinAPI model; production bridge and authority logic are NOT substituted. */
#include <windef.h>
#include <winbase.h>
#include <winternl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "record_publication_wine_abi.h"

int32_t WINAPI SpaceRecordPublicationCall(uint32_t, void *);
#ifdef SRP_MODEL_NATIVE
/* Test-only Wine dispatch destination; never used by the production bridge. */
extern int32_t srp_unix_call(SrpCall *);
#endif

static const char *selected;
static unsigned variation;
static DWORD last_error;
static unsigned threads, processes, closed_thread, closed_process, queries, modules, dispatches;
static void *query_buffer;
static const DWORD privileges[21] = {5,7,8,9,10,11,12,13,14,15,17,18,19,20,22,23,24,25,28,29,30};

static void require(int value, const char *message)
{
    if (!value) { fprintf(stderr, "%s\n", message); exit(1); }
}
static int is(const char *value) { return !strcmp(selected, value); }
void publication_model_configure(const char *value) { selected = value; variation = 0; }
void SetLastError(DWORD value) { last_error = value; }
DWORD GetLastError(void) { return last_error; }
HANDLE WINAPI GetCurrentProcess(void) { return (HANDLE)(uintptr_t)1; }
HANDLE WINAPI GetCurrentThread(void) { return (HANDLE)(uintptr_t)2; }

BOOL OpenThreadToken(HANDLE thread, DWORD access, BOOL self, HANDLE *token)
{
    require(thread == (HANDLE)(uintptr_t)2 && access == TOKEN_QUERY && self, "thread query arguments");
    ++threads;
    if (is("thread") || is("close-thread")) { *token = (HANDLE)(uintptr_t)3; return TRUE; }
    last_error = is("thread-error") ? 2001 : is("thread-zero-error") ? 0 : ERROR_NO_TOKEN;
    return FALSE;
}
BOOL OpenProcessToken(HANDLE process, DWORD access, HANDLE *token)
{
    require(process == (HANDLE)(uintptr_t)1 && access == TOKEN_QUERY && threads > processes, "process query ordering/arguments");
    ++processes;
    query_buffer = NULL;
    if (is("process-error") || is("process-zero-error")) { last_error = is("process-zero-error") ? 0 : 2002; return FALSE; }
    *token = (HANDLE)(uintptr_t)4;
    return TRUE;
}
BOOL CloseHandle(HANDLE token)
{
    if (token == (HANDLE)(uintptr_t)3) {
        ++closed_thread;
        require(closed_thread == 1, "thread token closed once");
        if (is("close-thread")) { last_error = 2003; return FALSE; }
    } else {
        require(token == (HANDLE)(uintptr_t)4, "only acquired token handles closed");
        ++closed_process;
        require(closed_process <= processes, "process token closed once per acquisition");
        if (is("close-process") || is("close-preserve")) { last_error = 2004; return FALSE; }
        if (is("close-zero-error")) { last_error = 0; return FALSE; }
    }
    last_error = 5999; /* Stale LastError on API success must not deny normal authority. */
    return TRUE;
}

static DWORD length_for(TOKEN_INFORMATION_CLASS kind)
{
    if (kind == TokenGroups) {
        if (is("groups-oversized")) return 65537;
        if (is("groups-max")) return 65536;
        if (is("groups-tiny")) return (DWORD)offsetof(TOKEN_GROUPS, Groups) - 1;
        return (DWORD)(offsetof(TOKEN_GROUPS, Groups) + sizeof(SID_AND_ATTRIBUTES) + 12);
    }
    if (kind == TokenPrivileges) {
        unsigned count = is("missing") ? 20 : is("extra") ? 22 : 21;
        return (DWORD)(offsetof(TOKEN_PRIVILEGES, Privileges) + count * sizeof(LUID_AND_ATTRIBUTES));
    }
    require(kind == TokenElevationType, "only Wine9-supported query classes");
    return is("elevation-size") ? 5 : sizeof(TOKEN_ELEVATION_TYPE);
}

BOOL GetTokenInformation(HANDLE token, TOKEN_INFORMATION_CLASS kind, void *out, DWORD capacity, DWORD *returned)
{
    require(token == (HANDLE)(uintptr_t)4, "queries use the acquired process token");
    require(kind == TokenGroups || kind == TokenPrivileges || kind == TokenElevationType, "no unsupported token restriction query");
    ++queries;
    const DWORD needed = length_for(kind);
    *returned = needed;
    const unsigned stage = kind == TokenGroups ? 0 : kind == TokenPrivileges ? 1 : 2;
    if (!out) {
        require(capacity == 0, "sizing query has no buffer");
        if ((is("size-error") && variation == stage) || is("close-preserve")) { last_error = 2100 + stage; return FALSE; }
        if (is("size-zero-error") && variation == stage) { last_error = 0; return FALSE; }
        if (is("size-success") && variation == stage) return TRUE;
        if (is("size-zero") && variation == stage) *returned = 0;
        last_error = ERROR_INSUFFICIENT_BUFFER;
        return FALSE;
    }
    require(capacity == needed && capacity <= 65536 && !((uintptr_t)out % 8), "bounded aligned query readback");
    if (!query_buffer) query_buffer = out;
    require(query_buffer == out, "one buffer reused for all query classes");
    if (is("read-error") && variation == stage) { last_error = 2200 + stage; return FALSE; }
    if (is("read-zero-error") && variation == stage) { last_error = 0; return FALSE; }
    memset(out, 0, capacity);
    BYTE *raw = out;
    if (kind == TokenGroups) {
        const DWORD count = is("groups-count") ? UINT32_MAX : 1;
        memcpy(raw + offsetof(TOKEN_GROUPS, GroupCount), &count, sizeof(count));
        BYTE *storage = raw + offsetof(TOKEN_GROUPS, Groups) + sizeof(SID_AND_ATTRIBUTES);
        SID sid = {0};
        sid.Revision = is("sid-revision") ? 2 : SID_REVISION;
        sid.SubAuthorityCount = is("sid-count") ? 16 : is("sid-extent") ? 15 : 1;
        memcpy(storage, &sid, sizeof(sid));
        SID_AND_ATTRIBUTES group = {0};
        group.Sid = storage;
        group.Attributes = is("deny-disabled") ? SE_GROUP_USE_FOR_DENY_ONLY :
            is("deny-enabled") ? SE_GROUP_USE_FOR_DENY_ONLY | 4 : 4;
        if (is("sid-null")) group.Sid = NULL;
        if (is("sid-before")) group.Sid = (void *)((uintptr_t)out - 4);
        if (is("sid-header")) group.Sid = out;
        if (is("sid-short")) group.Sid = raw + capacity - 1;
        if (is("sid-unaligned")) group.Sid = storage + 1;
        memcpy(raw + offsetof(TOKEN_GROUPS, Groups), &group, sizeof(group));
        if (is("groups-short")) *returned = (DWORD)offsetof(TOKEN_GROUPS, Groups);
    } else if (kind == TokenPrivileges) {
        unsigned count = is("missing") ? 20 : is("extra") ? 22 : 21;
        const DWORD reported_count = is("priv-count") ? UINT32_MAX : count;
        memcpy(raw + offsetof(TOKEN_PRIVILEGES, PrivilegeCount), &reported_count, sizeof(reported_count));
        for (unsigned i = 0, source = 0; i < count; ++i, ++source) {
            if (is("missing") && source == variation) ++source;
            LUID_AND_ATTRIBUTES privilege = {0};
            privilege.Luid.LowPart = source < 21 ? privileges[source] : 31;
            privilege.Attributes = is("attributes") ? variation : SE_PRIVILEGE_ENABLED | SE_PRIVILEGE_ENABLED_BY_DEFAULT;
            if (is("duplicate") && i == 20) privilege.Luid.LowPart = privileges[0];
            if (i == variation % 21) {
                if (is("high")) privilege.Luid.HighPart = 1;
                if (is("unknown-low")) privilege.Luid.LowPart = 6;
                if (is("removed")) privilege.Attributes |= SE_PRIVILEGE_REMOVED;
                if (is("unknown-attributes")) privilege.Attributes |= 0x80000000u;
            }
            memcpy(raw + offsetof(TOKEN_PRIVILEGES, Privileges) + (size_t)i * sizeof(privilege),
                &privilege, sizeof(privilege));
        }
        if (is("priv-short")) *returned = (DWORD)offsetof(TOKEN_PRIVILEGES, Privileges);
    } else {
        const DWORD elevation = is("limited") ? TokenElevationTypeLimited : is("elevation-unknown") ? 99 :
            is("default") ? TokenElevationTypeDefault : TokenElevationTypeFull;
        memcpy(raw, &elevation, sizeof(elevation));
    }
    if (is("read-zero") && variation == stage) *returned = 0;
    if (is("read-overflow") && variation == stage) *returned = capacity + 1;
    last_error = 5998;
    return TRUE;
}

BOOL GetModuleHandleExW(DWORD flags, LPCWSTR pointer, HMODULE *module)
{
    ++modules;
    require(flags == (GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT)
        && (uintptr_t)pointer == (uintptr_t)&SpaceRecordPublicationCall, "own HMODULE, unchanged refcount");
    if (is("self-error")) return FALSE;
    *module = (HMODULE)(uintptr_t)11;
    return TRUE;
}
HMODULE GetModuleHandleW(LPCWSTR name)
{
    require(!wcscmp(name, L"ntdll.dll"), "only pinned NTDLL lookup");
    return is("ntdll-error") ? NULL : (HMODULE)(uintptr_t)12;
}
NTSTATUS WINAPI NtQueryVirtualMemory(HANDLE process, const void *module, MEMORY_INFORMATION_CLASS kind,
                                     void *out, SIZE_T size, SIZE_T *returned)
{
    require(process == (HANDLE)(uintptr_t)1 && module == (HMODULE)(uintptr_t)11 && kind == MemoryWineUnixFuncs
        && size == 8 && !returned, "Wine9 own-module opaque eight-byte query, NULL ReturnLength");
    if (is("module-query-error")) return SRP_UNSUCCESSFUL;
    *(uint64_t *)out = is("zero-handle") ? 0 : UINT64_C(0x1122334455667788);
    return SRP_SUCCESS;
}
static NTSTATUS WINAPI unix_dispatch(uint64_t handle, unsigned entry, void *args)
{
    require(handle == UINT64_C(0x1122334455667788), "opaque handle dispatched, never cast to host function");
    ++dispatches;
    if (entry == SRP_ENTRY_IDENTITY) {
        SrpIdentity *identity = args;
        identity->echo = identity->challenge;
        memcpy(identity->unix_build_id, identity->pe_build_id, 32);
        identity->module_device = 7;
        identity->module_inode = 9;
        identity->architecture = SRP_ARCH_X86_64;
        identity->features = is("identity-corrupt") ? SRP_FEATURE_OPERATION : SRP_REQUIRED_FEATURES;
        return SRP_SUCCESS;
    }
    require(entry == SRP_ENTRY_OPERATION, "only the operation slot is forwarded");
#ifdef SRP_MODEL_NATIVE
    return srp_unix_call(args);
#else
    return SRP_UNSUPPORTED; /* Pure authority/dispatch model; real native slot requires SRP_MODEL_NATIVE. */
#endif
}
FARPROC GetProcAddress(HMODULE module, const char *name)
{
    require(module == (HMODULE)(uintptr_t)12, "dispatch resolved from NTDLL only");
    if (is("export-error")) return NULL;
    union { FARPROC generic; __typeof__(&NtQueryVirtualMemory) query; __typeof__(&unix_dispatch) dispatch; } pointer;
    if (!strcmp(name, "NtQueryVirtualMemory")) pointer.query = &NtQueryVirtualMemory;
    else { require(!strcmp(name, "__wine_unix_call"), "fixed opaque dispatcher export"); pointer.dispatch = &unix_dispatch; }
    return pointer.generic;
}

static SrpCall request(uint32_t opcode)
{
    SrpCall call = {0};
    call.size = sizeof(call); call.abi = SRP_ABI; call.opcode = opcode;
    return call;
}
static int allowed(void)
{
    return is("ordinary") || is("default") || is("attributes") || is("groups-max");
}

#ifdef SRP_MODEL_NATIVE
static void native_recovery(const char *path)
{
    SrpCall call = request(SRP_BEGIN);
    call.path.address = (uintptr_t)path; call.path.size = strlen(path);
    const char bytes[] = "native guarded bytes";
    call.payload.address = (uintptr_t)bytes; call.payload.size = sizeof(bytes) - 1;
    selected = "ordinary";
    require(SpaceRecordPublicationCall(1, &call) == SRP_SUCCESS, "real native BEGIN through guarded bridge");
    while (call.event != SRP_BEFORE_COMMIT) { call.opcode = SRP_ADVANCE; require(SpaceRecordPublicationCall(1, &call) == 0, "real native precommit phase"); }
    const uint64_t id = call.context, sequence = call.sequence;
    selected = "thread";
    require(SpaceRecordPublicationCall(1, &call) == (int32_t)UINT32_C(0xc0000022), "direct write denied after authority loss");
    const unsigned authority_calls = threads;
    call = request(SRP_SNAPSHOT); call.context = id;
    require(SpaceRecordPublicationCall(1, &call) == 0 && call.event == SRP_BEFORE_COMMIT
        && call.sequence == sequence && !(call.flags & SRP_COMMITTED), "saved-ID snapshot recovers actual uncommitted phase without authority");
    call.opcode = SRP_ADVANCE; call.event = SRP_BEFORE_CLEANUP;
    require(SpaceRecordPublicationCall(1, &call) == SRP_INVALID_ARGUMENT && call.event == SRP_BEFORE_COMMIT,
        "fake cleanup cannot resume publication: real native continuation rejects lie");
    call.opcode = SRP_CANCEL;
    require(SpaceRecordPublicationCall(1, &call) == 0 && call.event == SRP_BEFORE_CLEANUP, "cancel remains available after loss");
    call.opcode = SRP_ADVANCE;
    require(SpaceRecordPublicationCall(1, &call) == 0 && call.event == SRP_DONE && !(call.flags & SRP_COMMITTED), "actual cleanup after loss");
    call.opcode = SRP_RELEASE;
    require(SpaceRecordPublicationCall(1, &call) == 0 && threads == authority_calls, "release and cleanup never query authority");
    call = request(SRP_SNAPSHOT); call.context = id;
    require(SpaceRecordPublicationCall(1, &call) == SRP_INVALID_ARGUMENT, "retired native ID");

    selected = "ordinary";
    call = request(SRP_BEGIN); call.path.address = (uintptr_t)path; call.path.size = strlen(path);
    call.payload.address = (uintptr_t)bytes; call.payload.size = sizeof(bytes) - 1;
    require(SpaceRecordPublicationCall(1, &call) == 0, "second native context");
    while (call.event != SRP_BEFORE_CLEANUP) { call.opcode = SRP_ADVANCE; require(SpaceRecordPublicationCall(1, &call) == 0, "guarded actual commit"); }
    require(call.flags & SRP_COMMITTED, "native committed latch");
    selected = "thread";
    const unsigned after_commit = threads;
    call.opcode = SRP_CANCEL;
    require(SpaceRecordPublicationCall(1, &call) == 0 && (call.flags & SRP_COMMITTED)
        && call.primary_state == SRP_PRIMARY_ABSENT, "postcommit loss/cancel does not reclassify success");
    call.opcode = SRP_RELEASE;
    require(SpaceRecordPublicationCall(1, &call) == 0 && (call.flags & SRP_COMMITTED)
        && threads == after_commit, "postcommit release needs no authority");
}
#endif

int main(int argc, char **argv)
{
    require(argc >= 2, "model case required");
    selected = argv[1]; variation = argc > 2 ? (unsigned)strtoul(argv[2], NULL, 10) : 0;
#ifdef SRP_MODEL_NATIVE
    if (is("native-recovery")) { require(argc == 3, "native fixture path"); native_recovery(argv[2]); puts("native bridge recovery passed"); return 0; }
#endif
    if (is("identity") || is("identity-corrupt")) {
        SrpIdentity identity = {0}, saved;
        identity.size = 112; identity.abi = 1; identity.challenge = 1234; saved = identity;
        const int32_t status = SpaceRecordPublicationCall(0, &identity);
        require(!threads && !processes && !queries, "entry0 remains independent of authority");
        if (is("identity-corrupt")) require(status == SRP_IDENTITY_MISMATCH && !memcmp(&identity, &saved, sizeof(saved)), "failed identity is readonly");
        else require(status == 0 && identity.echo == 1234 && identity.features == SRP_REQUIRED_FEATURES, "identity entry retains required pair features");
    } else if (is("unknown") || is("bad-header") || is("bad-opcode") || is("bad-event")) {
        SrpCall call = request(is("bad-opcode") ? 99 : SRP_ADVANCE);
        if (is("bad-header")) call.size = 144;
        if (is("bad-event")) call.event = 99;
        require(SpaceRecordPublicationCall(is("unknown") ? 99 : 1, &call) == (is("unknown") ? SRP_UNSUPPORTED : SRP_INVALID_ARGUMENT), "invalid control frame refused");
        require(!threads && !modules && !dispatches, "invalid control frame cannot dispatch native work");
    } else if (is("snapshot") || is("cancel") || is("release") || is("cleanup")) {
        SrpCall call = request(is("snapshot") ? SRP_SNAPSHOT : is("cancel") ? SRP_CANCEL : is("release") ? SRP_RELEASE : SRP_ADVANCE);
        call.event = SRP_BEFORE_CLEANUP;
        selected = "thread";
        require(SpaceRecordPublicationCall(1, &call) == SRP_UNSUPPORTED && !threads && dispatches == 1, "recovery routes bypass authority but use opaque native dispatcher");
    } else if (is("authority-event")) {
        SrpCall call = request(SRP_ADVANCE); call.event = variation;
        selected = "thread";
        require(SpaceRecordPublicationCall(1, &call) == (int32_t)UINT32_C(0xc0000022) && threads == 1 && !dispatches,
            "every publishing ADVANCE event guarded directly");
    } else {
        SrpCall call = request(SRP_BEGIN);
        /* Invalid payload and unsafe text pointers: denial must precede native
         * validation/dispatch and must never write through these pointers. */
        call.payload.size = 1; call.context = 88; call.sequence = 99; call.flags = SRP_VALID | SRP_COMMITTED;
        call.event = SRP_BEFORE_CLEANUP; /* BEGIN cannot disguise itself as cleanup. */
        call.primary_state = SRP_PRIMARY_PRESENT;
        call.primary_error.required = call.cleanup_error.required = call.transport_error.required = 99;
        call.primary_error.address = call.cleanup_error.address = call.transport_error.address = UINT64_MAX;
        call.primary_error.capacity = call.cleanup_error.capacity = call.transport_error.capacity = 12;
        const int32_t status = SpaceRecordPublicationCall(1, &call);
        if (allowed()) require(status == SRP_UNSUPPORTED && dispatches == 1 && threads == 1 && queries == 6 && closed_process == 1,
            "ordinary supported state must forward to still-unsupported Unix slot");
        else if (is("self-error") || is("ntdll-error") || is("export-error") || is("zero-handle") || is("module-query-error"))
            require(status == (is("module-query-error") ? SRP_UNSUCCESSFUL : SRP_MODULE_UNAVAILABLE) && !dispatches, "opaque module/query failure refused");
        else {
            require(status == (int32_t)UINT32_C(0xc0000022), "direct publication guard must deny");
            require(last_error && !modules && !dispatches && !call.context && !call.sequence && call.event == SRP_START
                && !call.flags && call.primary_state == SRP_PRIMARY_ABSENT && !call.primary_error.required
                && !call.cleanup_error.required && !call.transport_error.required, "denial clears only safe inline state, no native work");
            if (is("thread-error")) require(last_error == 2001, "capture thread API error before any other API");
            if (is("process-error")) require(last_error == 2002, "capture process API error");
            if (is("close-process")) require(last_error == 2004, "successful policy plus failed close denies with close error");
            if (is("close-preserve")) require(last_error == 2100, "failed close must not replace primary query error");
            if (is("size-error")) require(last_error == 2100 + variation, "capture sizing API error");
            if (is("read-error")) require(last_error == 2200 + variation, "capture readback API error");
            if (is("thread-zero-error") || is("process-zero-error") || is("size-zero-error") || is("read-zero-error") || is("close-zero-error"))
                require(last_error == ERROR_GEN_FAILURE, "false API result with zero error must still deny meaningfully");
            if (processes && !is("process-error") && !is("process-zero-error")) require(closed_process == 1, "all acquired process handles closed exactly once on denial");
            if (is("thread") || is("close-thread")) require(closed_thread == 1 && !processes && last_error == ERROR_ACCESS_DENIED,
                "thread authority rejected, handle closed once, close cannot mask primary denial");
        }
    }
    puts("publication bridge host model passed");
    return 0;
}
