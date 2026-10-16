/* Test-only host adapter: Windows ABI scalar WIDTHS, not host unsigned long. */
#ifndef SPACE_TEST_WINDOWS_H
#define SPACE_TEST_WINDOWS_H
#include <stddef.h>
#include <stdint.h>
#define WINAPI
#define __declspec(attribute)
#define TRUE 1
#define FALSE 0
#define MAX_PATH 260
#define ERROR_SUCCESS 0
#define ERROR_MOD_NOT_FOUND 126
#define ERROR_PROC_NOT_FOUND 127
#define GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS 4
#define GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT 2
typedef uint8_t BYTE, BOOLEAN;
typedef int32_t BOOL;
typedef uint32_t ULONG, DWORD;
typedef uint32_t UINT;
typedef size_t SIZE_T;
typedef BYTE *PBYTE;
typedef void *PVOID;
typedef const char *LPCSTR;
typedef void *HMODULE;
typedef void *HANDLE;
typedef intptr_t (*FARPROC)(void);
HANDLE WINAPI GetCurrentProcess(void);
BOOL WINAPI TerminateProcess(HANDLE, UINT);
void SetLastError(DWORD);
DWORD GetLastError(void);
HMODULE LoadLibraryA(const char *);
FARPROC GetProcAddress(HMODULE, const char *);
BOOL GetModuleHandleExA(DWORD, LPCSTR, HMODULE *);
DWORD GetModuleFileNameA(HMODULE, char *, DWORD);
unsigned int GetSystemDirectoryA(char *, unsigned int);
int lstrcmpiA(const char *, const char *);
#endif
