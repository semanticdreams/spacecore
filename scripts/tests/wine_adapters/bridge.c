#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(ULONG) == 4, "Windows ULONG must be 32-bit");
_Static_assert(sizeof(BOOLEAN) == 1, "Windows BOOLEAN must be 8-bit");
_Static_assert(sizeof(BOOL) == 4, "Windows BOOL must be 32-bit");
static unsigned int calls;
static int fail_second;
static int termination_returns;
static int current_process_token;
BOOLEAN WINAPI SystemFunction036(PVOID buffer, ULONG length)
{
    ++calls;
    printf("chunk=%u\n", length);
    fflush(stdout);
    if (fail_second && calls == 2) {
        return FALSE;
    }
    memset(buffer, (int)calls, length);
    return TRUE;
}
HANDLE WINAPI GetCurrentProcess(void) { return &current_process_token; }
BOOL WINAPI TerminateProcess(HANDLE process, UINT code)
{
    if (process != &current_process_token || code != 20) exit(98);
    printf("terminate=current-process code=%u\n", code);
    fflush(stdout);
    if (termination_returns) return FALSE;
    exit((int)code);
}

#include "process_prng_compat.c"

int main(int argc, char **argv)
{
    BYTE buffer[18];
    if (argc != 2) return 91;
    memset(buffer, 0xa5, sizeof(buffer));
    if (!strcmp(argv[1], "zero")) {
        if (!ProcessPrng(NULL, 0) || !ProcessPrng(buffer + 1, 0) || calls != 0) return 92;
        for (SIZE_T i = 0; i < sizeof(buffer); ++i) if (buffer[i] != 0xa5) return 93;
    } else if (!strcmp(argv[1], "null") || !strcmp(argv[1], "terminate-returns")) {
        termination_returns = !strcmp(argv[1], "terminate-returns");
        ProcessPrng(NULL, 1);
        return 94;
    } else {
        fail_second = !strcmp(argv[1], "fail-second");
        if (!ProcessPrng(buffer + 1, 16)) return 95;
        if (buffer[0] != 0xa5 || buffer[17] != 0xa5 || calls != 3) return 96;
        for (SIZE_T i = 1; i <= 16; ++i) {
            if (buffer[i] != (i <= 7 ? 1 : i <= 14 ? 2 : 3)) return 97;
        }
    }
    puts("success");
    return 0;
}
