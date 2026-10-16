#include <windows.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>

static DWORD last_error;
static unsigned int calls;
static const char *mode(void) { return getenv("PROBE_FIXTURE"); }
static int is(const char *value) { return !strcmp(mode(), value); }
void SetLastError(DWORD error) { last_error = error; }
DWORD GetLastError(void) { return last_error; }
HMODULE LoadLibraryA(const char *name)
{
    if (strcmp(name, "bcryptprimitives.dll")) abort();
    if (!strncmp(mode(), "load-", 5)) {
        last_error = (DWORD)atoi(mode() + 5);
        return NULL;
    }
    return (HMODULE)(uintptr_t)1;
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
    (void)address;
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
        !strcmp(getenv("WINEDLLOVERRIDES"), "bcryptprimitives=n;advapi32,cryptbase=b") ?
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
