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
#define ERROR_ENVVAR_NOT_FOUND 203
#define ERROR_INVALID_PARAMETER 87
#define ERROR_INSUFFICIENT_BUFFER 122
#define ERROR_INVALID_DATA 13
#define ERROR_GEN_FAILURE 31
#define ERROR_FILE_NOT_FOUND 2
#define ERROR_NO_TOKEN 1008
#define TOKEN_QUERY 0x0008
#define SE_GROUP_USE_FOR_DENY_ONLY 0x10
#define SE_PRIVILEGE_ENABLED_BY_DEFAULT 1
#define SE_PRIVILEGE_ENABLED 2
#define SE_PRIVILEGE_REMOVED 4
#define SID_REVISION 1
#define SID_MAX_SUB_AUTHORITIES 15
#define GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS 4
#define GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT 2
typedef uint8_t BYTE, BOOLEAN;
typedef int32_t BOOL;
typedef uint32_t ULONG, DWORD;
typedef int32_t LONG;
typedef uint64_t ULONGLONG;
typedef uint32_t UINT;
typedef size_t SIZE_T;
typedef BYTE *PBYTE;
typedef void *PVOID;
typedef const char *LPCSTR;
typedef void *HMODULE;
typedef void *HANDLE;
typedef wchar_t WCHAR;
typedef const WCHAR *LPCWSTR;
typedef struct { DWORD LowPart; LONG HighPart; } LUID;
typedef struct { LUID Luid; DWORD Attributes; } LUID_AND_ATTRIBUTES;
typedef struct { BYTE Value[6]; } SID_IDENTIFIER_AUTHORITY;
typedef struct {
    BYTE Revision, SubAuthorityCount;
    SID_IDENTIFIER_AUTHORITY IdentifierAuthority;
    DWORD SubAuthority[1];
} SID;
typedef void *PSID;
typedef struct { PSID Sid; DWORD Attributes; } SID_AND_ATTRIBUTES;
typedef struct { DWORD GroupCount; SID_AND_ATTRIBUTES Groups[1]; } TOKEN_GROUPS;
typedef struct { DWORD PrivilegeCount; LUID_AND_ATTRIBUTES Privileges[1]; } TOKEN_PRIVILEGES;
typedef enum { TokenGroups = 2, TokenPrivileges = 3, TokenElevationType = 18 } TOKEN_INFORMATION_CLASS;
typedef enum { TokenElevationTypeDefault = 1, TokenElevationTypeFull = 2, TokenElevationTypeLimited = 3 } TOKEN_ELEVATION_TYPE;
#define INVALID_HANDLE_VALUE ((HANDLE)(intptr_t)-1)
#define GENERIC_WRITE 0x40000000
#define CREATE_NEW 1
#define OPEN_EXISTING 3
#define FILE_ATTRIBUTE_NORMAL 0x80
#ifdef __cplusplus
extern "C" {
#endif
DWORD GetEnvironmentVariableW(const WCHAR *, WCHAR *, DWORD);
BOOL SetEnvironmentVariableW(const WCHAR *, const WCHAR *);
HANDLE CreateFileW(const WCHAR *, DWORD, DWORD, void *, DWORD, DWORD, HANDLE);
BOOL WriteFile(HANDLE, const void *, DWORD, DWORD *, void *);
BOOL CloseHandle(HANDLE);
typedef intptr_t (*FARPROC)(void);
HANDLE WINAPI GetCurrentProcess(void);
HANDLE WINAPI GetCurrentThread(void);
BOOL OpenThreadToken(HANDLE, DWORD, BOOL, HANDLE *);
BOOL OpenProcessToken(HANDLE, DWORD, HANDLE *);
BOOL GetTokenInformation(HANDLE, TOKEN_INFORMATION_CLASS, void *, DWORD, DWORD *);
BOOL WINAPI TerminateProcess(HANDLE, UINT);
void SetLastError(DWORD);
DWORD GetLastError(void);
HMODULE LoadLibraryA(const char *);
FARPROC GetProcAddress(HMODULE, const char *);
BOOL GetModuleHandleExA(DWORD, LPCSTR, HMODULE *);
BOOL GetModuleHandleExW(DWORD, LPCWSTR, HMODULE *);
HMODULE GetModuleHandleW(LPCWSTR);
DWORD GetModuleFileNameA(HMODULE, char *, DWORD);
unsigned int GetSystemDirectoryA(char *, unsigned int);
int lstrcmpiA(const char *, const char *);
#ifdef __cplusplus
}
#endif
#endif
