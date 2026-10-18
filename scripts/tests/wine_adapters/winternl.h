#ifndef SPACE_TEST_WINTERNL_H
#define SPACE_TEST_WINTERNL_H
#include "windows.h"
typedef int32_t NTSTATUS;
typedef enum { MemoryWineUnixFuncs = 1000 } MEMORY_INFORMATION_CLASS;
NTSTATUS WINAPI NtQueryVirtualMemory(HANDLE, const void *, MEMORY_INFORMATION_CLASS, void *, SIZE_T, SIZE_T *);
#endif
