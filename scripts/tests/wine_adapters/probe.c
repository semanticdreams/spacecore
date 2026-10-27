#define _POSIX_C_SOURCE 200809L
#include <windows.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <fcntl.h>
#include <unistd.h>
#include "record_publication_wine_abi.h"

/* Host wchar_t storage is not Win16 execution. Unicode inputs below are explicit
 * UTF-16 units; real Windows-width C/C++ header compilation is a separate test. */
static DWORD last_error = ERROR_ACCESS_DENIED;
static unsigned int calls;
static WCHAR owned_root[32768];
static WCHAR process_temp[32768] = L"C:\\registry\\temp";
static WCHAR process_tmp[32768] = L"D:\\registry\\tmp";
static unsigned int env_sets, env_reads, loads;
static const char *mode(void) { return getenv("PROBE_FIXTURE"); }
static int is(const char *value) { return !strcmp(mode(), value); }
static int env_case(const char *value)
{
    const char *selected = getenv("PROBE_ENV_CASE");
    return selected && !strcmp(selected, value);
}
int fixture_environment_unchanged(void)
{
    return !env_sets && !wcscmp(process_temp, L"C:\\registry\\temp")
        && !wcscmp(process_tmp, L"D:\\registry\\tmp");
}
void SetLastError(DWORD error) { last_error = error; }
DWORD GetLastError(void) { return last_error; }
HMODULE LoadLibraryA(const char *name)
{
    if (env_sets != 2 || env_reads != 3 || wcscmp(process_temp, owned_root) || wcscmp(process_tmp, owned_root)) {
        puts("fixture-load-before-owned-environment");
        last_error = ERROR_INVALID_DATA;
        return NULL;
    }
    if (!loads++) puts("fixture-owned-before-load");
    if (!strcmp(name, "space_record_publication.dll")) {
        DWORD error = is("pair-missing") ? ERROR_MOD_NOT_FOUND :
            is("pair-bad-image") ? ERROR_BAD_EXE_FORMAT :
            is("pair-init-failed") ? ERROR_DLL_INIT_FAILED :
            is("pair-access-denied") ? ERROR_ACCESS_DENIED : ERROR_SUCCESS;
        if (error != ERROR_SUCCESS) {
            last_error = error;
            return NULL;
        }
        return (HMODULE)(uintptr_t)3;
    }
    if (strcmp(name, "bcryptprimitives.dll")) abort();
    puts("fixture-crypto-load");
    if (!strncmp(mode(), "load-", 5)) {
        last_error = (DWORD)atoi(mode() + 5);
        return NULL;
    }
    return (HMODULE)(uintptr_t)1;
}
static int32_t fixture_operation(void *args)
{
    static const char diagnostic[] = "BEGIN requires a nonempty absolute NUL-free host path";
    SrpCall *value = args;
    SrpCall expected = {0};
    unsigned char *transport;
    size_t i, length = sizeof(diagnostic) - 1;
    if (!value || !value->transport_error.address || value->transport_error.capacity != 4096) abort();
    expected.size = 168;
    expected.abi = SRP_ABI;
    expected.opcode = SRP_BEGIN;
    expected.event = SRP_START;
    expected.reply = SRP_CONTINUE;
    expected.transport_error.address = value->transport_error.address;
    expected.transport_error.capacity = 4096;
    if (memcmp(value, &expected, sizeof(expected))) abort();
    transport = (unsigned char *)(uintptr_t)value->transport_error.address;
    for (i = 0; i < 4096; ++i) if (transport[i]) abort();
    puts("fixture-entry1");
    if (is("operation-unsupported")) return SRP_UNSUPPORTED;
    if (is("operation-denied")) return SRP_ACCESS_DENIED;
    if (is("operation-success")) return SRP_SUCCESS;
    memcpy(transport, diagnostic, length - is("operation-short"));
    value->transport_error.required = length;
    if (is("operation-flags")) value->flags = SRP_VALID;
    if (is("operation-context")) value->context = 1;
    if (is("operation-sequence")) value->sequence = 1;
    if (is("operation-event")) value->event = SRP_BEFORE_WRITE;
    if (is("operation-primary-state")) value->primary_state = SRP_PRIMARY_PRESENT;
    if (is("operation-primary-required")) value->primary_error.required = 1;
    if (is("operation-cleanup-required")) value->cleanup_error.required = 1;
    if (is("operation-empty")) value->transport_error.required = 0;
    if (is("operation-oversize")) value->transport_error.required = 4097;
    if (is("operation-truncated")) value->flags = SRP_TRANSPORT_TRUNCATED;
    if (is("operation-size")) value->size = 144;
    if (is("operation-abi")) value->abi = 2;
    if (is("operation-opcode")) value->opcode = SRP_ADVANCE;
    if (is("operation-reply")) value->reply = SRP_FAILED;
    if (is("operation-reserved")) value->reserved = 1;
    if (is("operation-input")) value->path.size = 1;
    if (is("operation-buffer")) ++value->transport_error.address;
    return SRP_INVALID_ARGUMENT;
}
static int32_t WINAPI fixture_publication(uint32_t entry, void *args)
{
    SrpIdentity *value = args;
    if (entry == SRP_ENTRY_OPERATION) return fixture_operation(args);
    if (entry != SRP_ENTRY_IDENTITY || value->size != 112 || value->abi != SRP_ABI) abort();
    puts("fixture-entry0");
    if (is("pair-status")) return SRP_MODULE_UNAVAILABLE;
    if (!strncmp(mode(), "pair-status-", 12)) return (int32_t)strtol(mode() + 12, NULL, 10);
    value->echo = value->challenge + is("pair-echo");
    value->pe_build_id[0] = is("pair-pe-id") ? 2 : 1;
    value->unix_build_id[0] = is("pair-unix-id") ? 2 : 1;
    value->size = is("pair-size") ? 0 : 112;
    value->abi = is("pair-abi") ? 0 : SRP_ABI;
    value->module_device = 7;
    value->module_inode = is("pair-inode") ? 0 : 19;
    value->architecture = is("pair-arch") ? 0 : SRP_ARCH_X86_64;
    value->features = is("pair-features") ? 0 : SRP_REQUIRED_FEATURES;
    if (is("pair-old-features")) value->features = SRP_FEATURE_IDENTITY;
    if (is("pair-extra-features")) value->features = SRP_REQUIRED_FEATURES | UINT32_C(4);
    return SRP_SUCCESS;
}
static BOOL WINAPI fixture_prng(PBYTE buffer, SIZE_T length)
{
    ++calls;
    printf("fixture-request=%zu\n", length);
    if (!length) {
        if (buffer && is("zero-damage")) *buffer = 0;
        return TRUE;
    }
    if (is("false")) return FALSE;
    if (is("no-op")) return TRUE;
    if (is("guard")) buffer[-1] = 0;
    SIZE_T written = is("partial") || (is("odd-partial") && length == 65539) ? 1 : length;
    for (SIZE_T i = 0; i < written; ++i) {
        buffer[i] = is("stuck") ? 0 : (BYTE)(i + (is("repeat") ? 0 : calls));
    }
    return TRUE;
}
FARPROC GetProcAddress(HMODULE module, const char *name)
{
    if (module == (HMODULE)(uintptr_t)3) {
        union { FARPROC generic; int32_t (WINAPI *call)(uint32_t, void *); } function;
        if (strcmp(name, "SpaceRecordPublicationCall")) abort();
        function.call = fixture_publication;
        return is("pair-export") ? NULL : function.generic;
    }
    union { FARPROC generic; BOOL (WINAPI *prng)(PBYTE, SIZE_T); } function;
    if (module != (HMODULE)(uintptr_t)1 || strcmp(name, "ProcessPrng")) abort();
    if (!strncmp(mode(), "export-", 7) || is("wrong-name-export")) {
        last_error = is("wrong-name-export") ? ERROR_PROC_NOT_FOUND : (DWORD)atoi(mode() + 7);
        return NULL;
    }
    function.prng = fixture_prng;
    return function.generic;
}
BOOL GetModuleHandleExA(DWORD flags, LPCSTR address, HMODULE *owner)
{
    if (address == (LPCSTR)fixture_publication) {
        *owner = (HMODULE)(uintptr_t)(is("pair-owner") ? 4 : 3);
        return TRUE;
    }
    if (flags != (GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT)) abort();
    *owner = (HMODULE)(uintptr_t)(is("wrong-owner") ? 2 : 1);
    return TRUE;
}
DWORD GetModuleFileNameA(HMODULE module, char *path, DWORD length)
{
    if (is("long-name")) { memset(path, 'x', length); return length; }
    if (is("missing-name")) return 0;
    const char *name = module == NULL ? "C:\\fixture\\process-prng-probe.exe" :
        is("wrong-name") || is("wrong-name-export") ? "C:\\other.dll" :
        is("wrong-directory") ? "C:\\elsewhere\\bcryptprimitives.dll" :
        !strcmp(getenv("WINEDLLOVERRIDES"), "space_record_publication=b;bcryptprimitives=n;advapi32,cryptbase=b") ?
            "C:\\fixture\\bcryptprimitives.dll" : "C:\\windows\\system32\\BCryptPrimitives.dll";
    if (length <= strlen(name)) abort();
    strcpy(path, name);
    return (DWORD)strlen(name);
}
unsigned int GetSystemDirectoryA(char *path, unsigned int length)
{
    const char *name = "C:\\windows\\system32";
    if (length <= strlen(name)) abort();
    strcpy(path, name);
    return (unsigned int)strlen(name);
}
int lstrcmpiA(const char *a, const char *b) { return strcasecmp(a, b); }

static unsigned int hex_digit(char value)
{
    if (value >= '0' && value <= '9') return (unsigned int)(value - '0');
    if (value >= 'a' && value <= 'f') return (unsigned int)(value - 'a' + 10);
    abort();
}
static DWORD copy_environment_value(const WCHAR *value, WCHAR *output, DWORD capacity)
{
    size_t length = wcslen(value);
    if (length >= capacity) return (DWORD)length + 1;
    wmemcpy(output, value, length + 1);
    return (DWORD)length;
}
DWORD GetEnvironmentVariableW(const WCHAR *name, WCHAR *output, DWORD capacity)
{
    if (!wcscmp(name, L"SPACE_WINE_WINDOWS_TMP")) {
        const char *value = getenv("SPACE_WINE_WINDOWS_TMP");
        const char *units = getenv("PROBE_HANDOFF_UTF16");
        size_t length, i;
        if (last_error != ERROR_SUCCESS) abort(); /* Caller must clear stale error. */
        if (env_case("api-read")) { last_error = ERROR_ACCESS_DENIED; return 0; }
        if (!value) { last_error = ERROR_ENVVAR_NOT_FOUND; return 0; }
        if (env_case("oversize")) return capacity + 1;
        if (env_case("truncated")) return capacity;
        if (units) {
            length = strlen(units);
            if (length % 4 || length / 4 >= 32768) abort();
            for (i = 0; i < length / 4; ++i)
                owned_root[i] = (WCHAR)(hex_digit(units[4*i]) * 16 + hex_digit(units[4*i+1])
                    + (hex_digit(units[4*i+2]) * 16 + hex_digit(units[4*i+3])) * 256);
            owned_root[length / 4] = 0;
        } else {
            length = strlen(value);
            if (length >= 32768) abort();
            for (i = 0; i <= length; ++i) owned_root[i] = (WCHAR)(unsigned char)value[i];
        }
        if (env_case("empty")) owned_root[0] = 0;
        if (env_case("relative")) wcscpy(owned_root, L"relative");
        if (env_case("drive-digit")) wcscpy(owned_root, L"1:\\owned");
        if (env_case("dos-device")) wcscpy(owned_root, L"Q:\\NUL.txt");
        if (env_case("ads")) wcscpy(owned_root, L"Q:\\owned:stream");
        if (env_case("trailing-dot")) wcscpy(owned_root, L"Q:\\owned.");
        if (env_case("trailing-space")) wcscpy(owned_root, L"Q:\\owned ");
        if (env_case("unc")) wcscpy(owned_root, L"\\\\host\\tmp");
        if (env_case("device")) wcscpy(owned_root, L"\\\\?\\Q:\\tmp");
        if (env_case("mixed")) wcscpy(owned_root, L"Q:\\owned/tmp");
        if (env_case("traversal")) wcscpy(owned_root, L"Q:\\owned\\..\\tmp");
        if (env_case("control")) wcscpy(owned_root, L"Q:\\own\ned");
        if (env_case("high-surrogate") || env_case("low-surrogate")) {
            wcscpy(owned_root, L"Q:\\private\\");
            length = wcslen(owned_root);
            owned_root[length] = (WCHAR)(env_case("high-surrogate") ? 0xd800 : 0xdc00);
            owned_root[length + 1] = 0;
        }
        return copy_environment_value(owned_root, output, capacity);
    }
    if (!wcscmp(name, L"TEMP") || !wcscmp(name, L"TMP")) {
        int temp = !wcscmp(name, L"TEMP");
        if (env_sets == 2) {
            if (env_case(temp ? "read-temp" : "read-tmp")) { last_error = ERROR_ACCESS_DENIED; return 0; }
            if (env_case(temp ? "read-temp-truncated" : "read-tmp-truncated")) return capacity;
            env_reads |= temp ? 1 : 2;
            puts(temp ? "fixture-read-temp" : "fixture-read-tmp");
        }
        return copy_environment_value(temp ? process_temp : process_tmp, output, capacity);
    }
    abort();
}
BOOL SetEnvironmentVariableW(const WCHAR *name, const WCHAR *value)
{
    int temp = !wcscmp(name, L"TEMP");
    if (!temp && wcscmp(name, L"TMP")) abort();
    if (env_case(temp ? "set-temp" : "set-tmp")) { last_error = ERROR_ACCESS_DENIED; return FALSE; }
    if (env_case(temp ? "set-temp-no-error" : "set-tmp-no-error")) return FALSE;
    if (wcslen(value) >= 32768) abort();
    wcscpy(temp ? process_temp : process_tmp, value);
    ++env_sets;
    puts(temp ? "fixture-set-temp" : "fixture-set-tmp");
    if (!temp && env_case("mismatch-temp")) process_temp[0] = L'X';
    if (!temp && env_case("mismatch-tmp")) process_tmp[0] = L'X';
    return TRUE;
}
HANDLE CreateFileW(const WCHAR *path, DWORD access, DWORD sharing, void *security,
                   DWORD disposition, DWORD attributes, HANDLE template)
{
    char name[4096];
    const char *host = getenv("PROBE_HOST_TMP");
    size_t root_length = wcslen(owned_root);
    int count;
    if (access != GENERIC_WRITE || sharing || security || disposition != OPEN_EXISTING
            || attributes != FILE_ATTRIBUTE_NORMAL || template) abort();
    if (is("report-open")) { last_error = ERROR_ACCESS_DENIED; return INVALID_HANDLE_VALUE; }
    /* Test-only fixed DOS-root/report mapping, never a production converter. */
    if (!host || wcsncmp(path, owned_root, root_length)
            || wcscmp(path + root_length, L"\\space-record-publication-identity.json")) abort();
    count = snprintf(name, sizeof(name), "%s/space-record-publication-identity.json", host);
    if (count < 0 || (size_t)count >= sizeof(name)) return INVALID_HANDLE_VALUE;
    int fd = open(name, O_WRONLY | O_NOFOLLOW);
    if (fd < 0) last_error = ERROR_FILE_NOT_FOUND;
    return fd < 0 ? INVALID_HANDLE_VALUE : (HANDLE)(intptr_t)fd;
}
BOOL WriteFile(HANDLE file, const void *data, DWORD length, DWORD *written, void *overlapped)
{
    if (overlapped) abort();
    if (is("report-write")) return FALSE;
    ssize_t count = write((int)(intptr_t)file, data, length - is("report-short"));
    *written = count < 0 ? 0 : (DWORD)count;
    return count >= 0;
}
BOOL CloseHandle(HANDLE file)
{
    return close((int)(intptr_t)file) == 0 && !is("report-close");
}
