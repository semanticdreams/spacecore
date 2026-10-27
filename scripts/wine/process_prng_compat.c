/* Wine-only bridge. Static import: never LoadLibrary under loader lock.
 * ProcessPrng's public contract is TRUE + bytes; fail fast on any observable
 * failure since callers may ignore FALSE. This is not entropy certification.
 */
#include <windows.h>
#include <stdio.h>

__declspec(dllimport) BOOLEAN WINAPI SystemFunction036(PVOID buffer, ULONG length);

#ifndef PROCESS_PRNG_CHUNK_MAX
#define PROCESS_PRNG_CHUNK_MAX ((ULONG)~(ULONG)0)
#endif

static _Noreturn void backend_failure(void)
{
    fputs("ProcessPrng compatibility: OS RNG backend unresolved/failed; terminating\n", stderr);
    fflush(stderr);
    /* ExitProcess runs DLL detach callbacks and can deadlock on locks held by
     * terminated threads. Hard termination must not enter that teardown path. */
    TerminateProcess(GetCurrentProcess(), 20);
    __builtin_trap(); /* Never return even if hard termination unexpectedly does. */
}

__declspec(dllexport) BOOL WINAPI ProcessPrng(PBYTE buffer, SIZE_T length)
{
    if (length == 0) {
        return TRUE; /* NULL/zero is explicitly allowed; no backend call. */
    }
    if (buffer == NULL) {
        backend_failure();
    }
    while (length != 0) {
        ULONG chunk = length > (SIZE_T)PROCESS_PRNG_CHUNK_MAX
            ? PROCESS_PRNG_CHUNK_MAX : (ULONG)length;
        if (chunk == 0 || !SystemFunction036(buffer, chunk)) {
            backend_failure();
        }
        buffer += chunk;
        length -= chunk;
    }
    return TRUE;
}
