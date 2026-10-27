#ifndef SPACE_RECORD_PUBLICATION_WINE_AUTHORITY_H
#define SPACE_RECORD_PUBLICATION_WINE_AUTHORITY_H

#include <windows.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Cooperative represented-state guard for stock Wine9 admin lineage, from:
 * https://github.com/wine-mirror/wine/blob/wine-9.0/server/token.c
 * token_create_admin/admin_privs. Not an ever-filtered/restriction-SID test,
 * sandbox boundary, native-Windows policy, or proof of a foreign host UID.
 * Do not replace a failed/unsupported restriction query with acceptance.
 */
#ifdef __cplusplus
static_assert(sizeof(DWORD) == 4 && sizeof(LUID) == 8 && sizeof(TOKEN_ELEVATION_TYPE) == 4,
              "Windows token scalar widths");
#else
_Static_assert(sizeof(DWORD) == 4 && sizeof(LUID) == 8 && sizeof(TOKEN_ELEVATION_TYPE) == 4,
               "Windows token scalar widths");
#endif

typedef union {
    ULONGLONG alignment;
    BYTE bytes[65536];
} SpaceRecordPublicationTokenBuffer;

static inline DWORD space_record_publication_authority_error(DWORD error)
{
    return error ? error : ERROR_GEN_FAILURE;
}

static inline DWORD space_record_publication_authority_query(HANDLE token, TOKEN_INFORMATION_CLASS kind,
    SpaceRecordPublicationTokenBuffer *buffer, DWORD minimum, DWORD *returned)
{
    DWORD needed = 0;
    if (GetTokenInformation(token, kind, NULL, 0, &needed)) return ERROR_INVALID_DATA;
    const DWORD error = GetLastError();
    if (error != ERROR_INSUFFICIENT_BUFFER) return space_record_publication_authority_error(error);
    if (needed < minimum || needed > sizeof(buffer->bytes)
        || (kind == TokenElevationType && needed != sizeof(TOKEN_ELEVATION_TYPE))) return ERROR_INVALID_DATA;
    *returned = 0;
    if (!GetTokenInformation(token, kind, buffer->bytes, needed, returned)) {
        const DWORD read_error = GetLastError();
        return space_record_publication_authority_error(read_error);
    }
    if (*returned < minimum || *returned > needed) return ERROR_INVALID_DATA;
    return ERROR_SUCCESS;
}

static inline DWORD space_record_publication_authority_groups(SpaceRecordPublicationTokenBuffer *buffer, DWORD bytes)
{
    DWORD count = 0;
    memcpy(&count, buffer->bytes + offsetof(TOKEN_GROUPS, GroupCount), sizeof(count));
    const size_t offset = offsetof(TOKEN_GROUPS, Groups);
    if (count > (bytes - offset) / sizeof(SID_AND_ATTRIBUTES)) return ERROR_INVALID_DATA;
    const uintptr_t start = (uintptr_t)buffer->bytes;
    const uintptr_t end = start + bytes;
    const uintptr_t sid_start = start + offset + count * sizeof(SID_AND_ATTRIBUTES);
    for (DWORD index = 0; index < count; ++index) {
        SID_AND_ATTRIBUTES group;
        /* The validated array extent bounds each copy. Alignment alone does not
         * create token-record objects in byte storage, especially in C++17. */
        const size_t entry_offset = offset + (size_t)index * sizeof(group);
        memcpy(&group, buffer->bytes + entry_offset, sizeof(group));
        const uintptr_t address = (uintptr_t)group.Sid;
        const size_t header = offsetof(SID, SubAuthority);
        /* Check pointer extent/alignment before reading even revision/count. */
        if (address < sid_start || address > end || (address & (sizeof(DWORD) - 1))
            || end - address < header) return ERROR_INVALID_DATA;
        const BYTE *sid = (const BYTE *)address;
        if (sid[0] != SID_REVISION || sid[1] > SID_MAX_SUB_AUTHORITIES
            || sid[1] > (end - address - header) / sizeof(DWORD)) return ERROR_INVALID_DATA;
        if (group.Attributes & SE_GROUP_USE_FOR_DENY_ONLY) return ERROR_ACCESS_DENIED;
    }
    return ERROR_SUCCESS;
}

static inline DWORD space_record_publication_authority_privileges(SpaceRecordPublicationTokenBuffer *buffer, DWORD bytes)
{
    static const DWORD expected[21] = {5,7,8,9,10,11,12,13,14,15,17,18,19,20,22,23,24,25,28,29,30};
    DWORD count = 0;
    memcpy(&count, buffer->bytes + offsetof(TOKEN_PRIVILEGES, PrivilegeCount), sizeof(count));
    const size_t offset = offsetof(TOKEN_PRIVILEGES, Privileges);
    if (count > (bytes - offset) / sizeof(LUID_AND_ATTRIBUTES)) return ERROR_INVALID_DATA;
    if (count != 21) return ERROR_ACCESS_DENIED;
    DWORD seen = 0;
    for (DWORD index = 0; index < count; ++index) {
        LUID_AND_ATTRIBUTES privilege;
        const size_t entry_offset = offset + (size_t)index * sizeof(privilege);
        memcpy(&privilege, buffer->bytes + entry_offset, sizeof(privilege));
        if (privilege.Luid.HighPart != 0
            || (privilege.Attributes & ~(SE_PRIVILEGE_ENABLED | SE_PRIVILEGE_ENABLED_BY_DEFAULT))) return ERROR_ACCESS_DENIED;
        unsigned position = 0;
        while (position < 21 && expected[position] != privilege.Luid.LowPart) ++position;
        if (position == 21 || (seen & ((DWORD)1 << position))) return ERROR_ACCESS_DENIED;
        seen |= (DWORD)1 << position;
    }
    return ERROR_SUCCESS;
}

static inline DWORD space_record_publication_check_authority(void)
{
    HANDLE thread = NULL, process = NULL;
    DWORD result;
    if (OpenThreadToken(GetCurrentThread(), TOKEN_QUERY, TRUE, &thread)) {
        result = ERROR_ACCESS_DENIED;
        /* A thread token is already a primary denial. Close once; do not replace it. */
        if (!CloseHandle(thread)) { const DWORD close_error = GetLastError(); (void)close_error; }
        SetLastError(result);
        return result;
    }
    result = GetLastError();
    if (result != ERROR_NO_TOKEN) {
        result = space_record_publication_authority_error(result);
        SetLastError(result);
        return result;
    }
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &process)) {
        result = space_record_publication_authority_error(GetLastError());
        SetLastError(result);
        return result;
    }
    SpaceRecordPublicationTokenBuffer buffer;
    DWORD bytes = 0;
    result = space_record_publication_authority_query(process, TokenGroups, &buffer,
        (DWORD)offsetof(TOKEN_GROUPS, Groups), &bytes);
    if (!result) result = space_record_publication_authority_groups(&buffer, bytes);
    if (!result) result = space_record_publication_authority_query(process, TokenPrivileges, &buffer,
        (DWORD)offsetof(TOKEN_PRIVILEGES, Privileges), &bytes);
    if (!result) result = space_record_publication_authority_privileges(&buffer, bytes);
    if (!result) result = space_record_publication_authority_query(process, TokenElevationType, &buffer,
        sizeof(TOKEN_ELEVATION_TYPE), &bytes);
    if (!result) {
        DWORD elevation = 0;
        if (bytes != sizeof(elevation)) result = ERROR_INVALID_DATA;
        else {
            /* An unknown API scalar must not first be loaded as an invalid C++
             * enum value. Interpret its checked bytes before classifying it. */
            memcpy(&elevation, buffer.bytes, sizeof(elevation));
            if (elevation != TokenElevationTypeDefault && elevation != TokenElevationTypeFull) result = ERROR_ACCESS_DENIED;
        }
    }
    if (!CloseHandle(process)) {
        const DWORD close_error = GetLastError();
        if (!result) result = space_record_publication_authority_error(close_error);
    }
    if (result) SetLastError(result);
    return result; /* A successful API may leave stale LastError; ignore it. */
}

#endif
