/* API-contract admission, NOT an entropy test or native Windows certification. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <wchar.h>
#include "record_publication_wine_abi.h"

#ifndef SRP_BUILD_ID_BYTES
#error "The capability probe must be bound to the inventoried publication build"
#endif

typedef int32_t (WINAPI *PublicationCall)(uint32_t, void *);
static const uint8_t expected_build_id[32] = SRP_BUILD_ID_BYTES;

typedef BOOL (WINAPI *ProcessPrngFn)(PBYTE, SIZE_T);

static int failure(const char *message)
{
    fprintf(stderr, "ProcessPrng probe: %s (contract/identity failure)\n", message);
    fflush(stderr);
    return 20;
}

static void hex_id(char *output, const uint8_t *input)
{
    static const char digits[] = "0123456789abcdef";
    size_t i;
    for (i = 0; i < 32; ++i) {
        output[2 * i] = digits[input[i] >> 4];
        output[2 * i + 1] = digits[input[i] & 15];
    }
    output[64] = '\0';
}

static int publication_identity(void)
{
    HMODULE module, owner = NULL;
    union { FARPROC generic; PublicationCall call; } function;
    SrpIdentity identity = {0};
    static const char digits[] = "0123456789abcdef";
    const char *challenge = getenv("SPACE_WINE_IDENTITY_CHALLENGE");
    uint64_t value = 0;
    size_t i;
    char pe[65], unix_id[65], report[4096];
    WCHAR path[32768];
    DWORD length, written;
    DWORD error;
    int32_t status;
    HANDLE file;
    int count, ok;
    if (!challenge || strlen(challenge) != 16) return failure("missing publication challenge");
    for (i = 0; i < 16; ++i) {
        const char *digit = strchr(digits, challenge[i]);
        if (!digit) return failure("invalid publication challenge");
        value = (value << 4) | (uint64_t)(digit - digits);
    }
    /* Only basename loading uses Wine's builtin PE/Unix association. Neither an
     * absolute DLL load nor a logical System32 filename proves Unix dispatch. */
    SetLastError(ERROR_SUCCESS);
    module = LoadLibraryA("space_record_publication.dll");
    if (!module) {
        error = GetLastError();
        fprintf(stderr, "Publication probe: phase=load-library error=%" PRIu32 "\n", (uint32_t)error);
        fflush(stderr);
        return failure("publication builtin unavailable");
    }
    function.generic = GetProcAddress(module, "SpaceRecordPublicationCall");
    if (!function.generic || !GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCSTR)function.call, &owner) || owner != module)
        return failure("publication entry ownership");
    identity.size = sizeof(identity);
    identity.abi = SRP_ABI;
    identity.challenge = value;
    status = function.call(SRP_ENTRY_IDENTITY, &identity);
    fprintf(stderr, "Publication probe: phase=entry0 status=%" PRId32 "\n", status);
    fflush(stderr);
    if (status != SRP_SUCCESS) return failure("publication entry0 failed");
    if (identity.size != sizeof(identity)
            || identity.abi != SRP_ABI || identity.challenge != value || identity.echo != value
            || identity.architecture != SRP_ARCH_X86_64 || identity.features != SRP_REQUIRED_FEATURES
            || !identity.module_inode
            || memcmp(identity.pe_build_id, expected_build_id, sizeof(expected_build_id))
            || memcmp(identity.unix_build_id, expected_build_id, sizeof(expected_build_id)))
        return failure("publication identity roundtrip");
    hex_id(pe, identity.pe_build_id);
    hex_id(unix_id, identity.unix_build_id);
    count = snprintf(report, sizeof(report),
        "{\"version\":1,\"size\":112,\"abi\":%" PRIu32 ",\"challenge\":\"%s\",\"echo\":\"%016" PRIx64
        "\",\"pe_build_id\":\"%s\",\"unix_build_id\":\"%s\",\"module_device\":%" PRIu64
        ",\"module_inode\":%" PRIu64 ",\"architecture\":%" PRIu32 ",\"features\":%" PRIu32 "}\n",
        identity.abi, challenge, identity.echo, pe, unix_id, identity.module_device, identity.module_inode,
        identity.architecture, identity.features);
    if (count <= 0 || (size_t)count >= sizeof(report)) return failure("publication report size");
    length = GetEnvironmentVariableW(L"TEMP", path, (DWORD)(sizeof(path) / sizeof(path[0])));
    if (!length || length + wcslen(L"\\space-record-publication-identity.json") >= sizeof(path) / sizeof(path[0]))
        return failure("publication report TEMP");
    wcscat(path, L"\\space-record-publication-identity.json");
    file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return failure("exclusive publication report create");
    written = 0;
    ok = WriteFile(file, report, (DWORD)count, &written, NULL) && written == (DWORD)count;
    if (!CloseHandle(file)) ok = 0;
    if (!ok) return failure("publication report write/close");
    puts("Publication identity: entry0 report written; host identity comparison required");
    fflush(stdout);
    return 0;
}

static int expected_module_path(char *path)
{
    const char *backend = getenv("WINEDLLOVERRIDES");
    DWORD length;
    char *base;
    if (backend && strcmp(backend, "space_record_publication=b;bcryptprimitives=b;advapi32,cryptbase=b") == 0) {
        length = GetSystemDirectoryA(path, MAX_PATH);
        if (length == 0 || length >= MAX_PATH) return failure("system directory identity");
        if (length + strlen("\\bcryptprimitives.dll") >= MAX_PATH) return failure("long system path");
        strcat(path, "\\bcryptprimitives.dll");
    } else if (backend && strcmp(backend, "space_record_publication=b;bcryptprimitives=n;advapi32,cryptbase=b") == 0) {
        length = GetModuleFileNameA(NULL, path, MAX_PATH);
        if (length == 0 || length >= MAX_PATH) return failure("probe executable identity");
        base = strrchr(path, '\\');
        if (base == NULL) return failure("probe executable directory");
        base[1] = '\0';
        if (strlen(path) + strlen("bcryptprimitives.dll") >= MAX_PATH) return failure("long overlay path");
        strcat(path, "bcryptprimitives.dll");
    } else {
        return failure("unrecognized backend configuration");
    }
    return 0;
}

static int fill(ProcessPrngFn prng, BYTE *buffer, SIZE_T length, BYTE pattern)
{
    SIZE_T i;
    int changed = 0;
    int varied = 0;
    SIZE_T unchanged_run = 0;
    memset(buffer, pattern, length + 2);
    if (prng(buffer + 1, length) != TRUE) {
        return failure("API did not return TRUE");
    }
    if (buffer[0] != pattern || buffer[length + 1] != pattern) {
        return failure("damaged guard");
    }
    for (i = 1; i <= length; ++i) {
        changed |= buffer[i] != pattern;
        varied |= buffer[i] != buffer[1];
        unchanged_run = buffer[i] == pattern ? unchanged_run + 1 : 0;
        /* Check coverage throughout the buffer, not just the first write.
         * This sentinel check is probabilistic, not proof of entropy or of
         * every individual write (random bytes can equal the sentinel). */
        if (unchanged_run >= 32) {
            return failure("unwritten sentinel span");
        }
    }
    if (!changed || !varied) {
        return failure("unchanged/stuck output");
    }
    return 0;
}

int main(void)
{
    HMODULE module;
    HMODULE owner = NULL;
    char path[MAX_PATH];
    char expected[MAX_PATH];
    char *base;
    union { FARPROC generic; ProcessPrngFn prng; } function;
    BYTE first[65536 + 2];
    BYTE second[65536 + 2];
    BYTE odd[65539 + 2];
    BYTE zero[3] = {0x31, 0x47, 0x59};
    DWORD error;
    DWORD path_length;
    if (publication_identity() != 0) return 20;
    puts("ProcessPrng probe: loading bcryptprimitives.dll");
    fflush(stdout);
    SetLastError(ERROR_SUCCESS);
    module = LoadLibraryA("bcryptprimitives.dll");
    if (module == NULL) {
        error = GetLastError();
        fprintf(stderr, "ProcessPrng probe: LoadLibrary error=%lu\n", (unsigned long)error);
        fflush(stderr);
        /* Only confirmed DLL absence. Bad image/access/initialization errors
         * are NOT absence and must never authorize compatibility fallback. */
        return error == ERROR_MOD_NOT_FOUND ? 10 : 20;
    }
    path_length = GetModuleFileNameA(module, path, MAX_PATH);
    if (path_length == 0 || path_length >= MAX_PATH) {
        return failure("cannot resolve module identity");
    }
    base = strrchr(path, '\\');
    base = base ? base + 1 : path;
    if (lstrcmpiA(base, "bcryptprimitives.dll") != 0) {
        return failure("unexpected module filename");
    }
    if (expected_module_path(expected) != 0) return 20;
    if (lstrcmpiA(path, expected) != 0) {
        return failure("module is not the selected system builtin/overlay bridge");
    }
    SetLastError(ERROR_SUCCESS);
    function.generic = GetProcAddress(module, "ProcessPrng");
    if (function.generic == NULL) {
        error = GetLastError();
        fprintf(stderr, "ProcessPrng probe: GetProcAddress error=%lu\n", (unsigned long)error);
        fflush(stderr);
        return error == ERROR_PROC_NOT_FOUND ? 10 : 20;
    }
    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            (LPCSTR)function.prng, &owner) || owner != module) {
        return failure("export belongs to another module");
    }
    printf("ProcessPrng probe: module=%s; checking buffers\n", path);
    fflush(stdout);
    if (fill(function.prng, first, 65536, 0xa5) ||
        fill(function.prng, second, 65536, 0x5a) ||
        fill(function.prng, odd, 65539, 0xc3)) {
        return 20;
    }
    if (memcmp(first + 1, second + 1, 65536) == 0) {
        return failure("repeated output across requests");
    }
    if (function.prng(zero + 1, 0) != TRUE || function.prng(NULL, 0) != TRUE ||
        zero[0] != 0x31 || zero[1] != 0x47 || zero[2] != 0x59) {
        return failure("zero-length policy/guards");
    }
    puts("ProcessPrng probe: API contract admitted; not entropy certification");
    fflush(stdout);
    return 0;
}
