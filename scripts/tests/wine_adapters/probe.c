#include <windows.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <fcntl.h>
#include <unistd.h>
#include "record_publication_wine_abi.h"

static DWORD last_error;
static unsigned int calls;
static const char *mode(void) { return getenv("PROBE_FIXTURE"); }
static int is(const char *value) { return !strcmp(mode(), value); }
void SetLastError(DWORD error) { last_error = error; }
DWORD GetLastError(void) { return last_error; }
HMODULE LoadLibraryA(const char *name)
{
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
static int32_t WINAPI fixture_identity(uint32_t entry, void *args)
{
    SrpIdentity *value = args;
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
        function.call = fixture_identity;
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
    if (address == (LPCSTR)fixture_identity) {
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

DWORD GetEnvironmentVariableW(const WCHAR *name, WCHAR *output, DWORD capacity)
{
    if (wcscmp(name, L"TEMP")) abort();
    const char *value = getenv("TEMP");
    if (!value) return 0;
    size_t count = mbstowcs(output, value, capacity);
    return count == (size_t)-1 ? 0 : (DWORD)count;
}
HANDLE CreateFileW(const WCHAR *path, DWORD access, DWORD sharing, void *security,
                   DWORD disposition, DWORD attributes, HANDLE template)
{
    char name[4096];
    if (access != GENERIC_WRITE || sharing || security || disposition != CREATE_NEW
            || attributes != FILE_ATTRIBUTE_NORMAL || template) abort();
    if (is("report-create") || wcstombs(name, path, sizeof(name)) >= sizeof(name)) return INVALID_HANDLE_VALUE;
    for (char *p = name; *p; ++p) if (*p == '\\') *p = '/';
    int fd = open(name, O_WRONLY | O_CREAT | O_EXCL, 0600);
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
