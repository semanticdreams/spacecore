/* Test-only host adapter: Windows ABI scalar WIDTHS, not host unsigned long. */
#ifndef SPACE_TEST_WINDOWS_H
#define SPACE_TEST_WINDOWS_H
#include <stddef.h>
#include <stdint.h>
#include <wchar.h>
#define WINAPI
#define __declspec(attribute)
#define TRUE 1
#define FALSE 0
#define MAX_PATH 260
#define ERROR_SUCCESS 0
#define ERROR_MOD_NOT_FOUND 126
#define ERROR_PROC_NOT_FOUND 127
#define ERROR_ACCESS_DENIED 5
#define ERROR_BAD_EXE_FORMAT 193
#define ERROR_DLL_INIT_FAILED 1114
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
typedef wchar_t WCHAR;
#define INVALID_HANDLE_VALUE ((HANDLE)(intptr_t)-1)
#define GENERIC_WRITE 0x40000000
#define CREATE_NEW 1
#define FILE_ATTRIBUTE_NORMAL 0x80
DWORD GetEnvironmentVariableW(const WCHAR *, WCHAR *, DWORD);
HANDLE CreateFileW(const WCHAR *, DWORD, DWORD, void *, DWORD, DWORD, HANDLE);
BOOL WriteFile(HANDLE, const void *, DWORD, DWORD *, void *);
BOOL CloseHandle(HANDLE);
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
