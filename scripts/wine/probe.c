/* API-contract admission, NOT an entropy test or native Windows certification. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef BOOL (WINAPI *ProcessPrngFn)(PBYTE, SIZE_T);

static int failure(const char *message)
{
    fprintf(stderr, "ProcessPrng probe: %s (contract/identity failure)\n", message);
    fflush(stderr);
    return 20;
}

static int expected_module_path(char *path)
{
    const char *backend = getenv("WINEDLLOVERRIDES");
    DWORD length;
    char *base;
    if (backend && strcmp(backend, "bcryptprimitives=b;advapi32,cryptbase=b") == 0) {
        length = GetSystemDirectoryA(path, MAX_PATH);
        if (length == 0 || length >= MAX_PATH) return failure("system directory identity");
        if (length + strlen("\\bcryptprimitives.dll") >= MAX_PATH) return failure("long system path");
        strcat(path, "\\bcryptprimitives.dll");
    } else if (backend && strcmp(backend, "bcryptprimitives=n;advapi32,cryptbase=b") == 0) {
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
