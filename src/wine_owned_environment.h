#ifndef SPACE_WINE_OWNED_ENVIRONMENT_H
#define SPACE_WINE_OWNED_ENVIRONMENT_H

#include <windows.h>

/* Private post-bootstrap process initialization, not a Wine detection API. */
#define SPACE_WINE_WINDOWS_TMP_CAPACITY 32768

static inline DWORD space_wine_read_environment(const WCHAR *name, WCHAR *value, DWORD *length)
{
    DWORD count, error;
    SetLastError(ERROR_SUCCESS);
    count = GetEnvironmentVariableW(name, value, SPACE_WINE_WINDOWS_TMP_CAPACITY);
    if (!count) {
        error = GetLastError();
        return error ? error : ERROR_INVALID_PARAMETER; /* Present but empty. */
    }
    if (count >= SPACE_WINE_WINDOWS_TMP_CAPACITY) return ERROR_INSUFFICIENT_BUFFER;
    if (value[count] != 0) return ERROR_INVALID_DATA;
    *length = count;
    return ERROR_SUCCESS;
}

static inline BOOL space_wine_owned_component_valid(const WCHAR *value, DWORD length)
{
    static const WCHAR *const devices[] = {L"CON", L"PRN", L"AUX", L"NUL", L"CONIN$", L"CONOUT$"};
    DWORD stem = 0, i, device;
    WCHAR name[8];
    if (!length || value[length - 1] == L'.' || value[length - 1] == L' ') return FALSE;
    while (stem < length && value[stem] != L'.') ++stem;
    if (stem >= sizeof(name) / sizeof(name[0])) return TRUE;
    for (i = 0; i < stem; ++i)
        name[i] = value[i] >= L'a' && value[i] <= L'z' ? value[i] - L'a' + L'A' : value[i];
    name[stem] = 0;
    for (device = 0; device < sizeof(devices) / sizeof(devices[0]); ++device) {
        for (i = 0; i < stem && devices[device][i] && name[i] == devices[device][i]; ++i) {}
        if (i == stem && devices[device][i] == 0) return FALSE;
    }
    if (stem == 4 && name[3] >= L'1' && name[3] <= L'9'
            && ((name[0] == L'C' && name[1] == L'O' && name[2] == L'M')
                || (name[0] == L'L' && name[1] == L'P' && name[2] == L'T'))) return FALSE;
    return TRUE;
}

static inline BOOL space_wine_owned_root_valid(const WCHAR *value, DWORD length)
{
    DWORD i, component = 3;
    if (length < 3 || !((value[0] >= L'A' && value[0] <= L'Z')
                       || (value[0] >= L'a' && value[0] <= L'z'))
            || value[1] != L':' || value[2] != L'\\') return FALSE;
    for (i = 3; i < length; ++i) {
        unsigned long unit = (unsigned long)value[i];
        if (unit > 0xffff || unit < 0x20 || (unit >= 0x7f && unit <= 0x9f)
                || value[i] == L'/' || value[i] == L':' || value[i] == L'<' || value[i] == L'>'
                || value[i] == L'"' || value[i] == L'|' || value[i] == L'?' || value[i] == L'*') return FALSE;
        if (unit >= 0xd800 && unit <= 0xdbff) {
            if (i + 1 >= length || (unsigned long)value[i + 1] < 0xdc00
                    || (unsigned long)value[i + 1] > 0xdfff) return FALSE;
            ++i;
        } else if (unit >= 0xdc00 && unit <= 0xdfff) {
            return FALSE;
        } else if (value[i] == L'\\') {
            if (!space_wine_owned_component_valid(value + component, i - component)) return FALSE;
            component = i + 1;
        }
    }
    return component == length || space_wine_owned_component_valid(value + component, length - component);
}

static inline DWORD space_wine_apply_owned_environment(BOOL required)
{
    WCHAR root[SPACE_WINE_WINDOWS_TMP_CAPACITY], observed[SPACE_WINE_WINDOWS_TMP_CAPACITY];
    DWORD length = 0, count = 0, error, i, variable;
    static const WCHAR *const names[] = {L"TEMP", L"TMP"};
    error = space_wine_read_environment(L"SPACE_WINE_WINDOWS_TMP", root, &length);
    if (error == ERROR_ENVVAR_NOT_FOUND && !required) return ERROR_SUCCESS;
    if (error) return error;
    if (!space_wine_owned_root_valid(root, length)) return ERROR_INVALID_PARAMETER;
    for (variable = 0; variable < 2; ++variable) {
        SetLastError(ERROR_SUCCESS);
        if (!SetEnvironmentVariableW(names[variable], root)) {
            error = GetLastError();
            return error ? error : ERROR_GEN_FAILURE;
        }
    }
    /* Both reads follow both sets: setting TMP must not invalidate TEMP. */
    for (variable = 0; variable < 2; ++variable) {
        error = space_wine_read_environment(names[variable], observed, &count);
        if (error) return error;
        if (count != length) return ERROR_INVALID_DATA;
        for (i = 0; i < length; ++i)
            if (observed[i] != root[i]) return ERROR_INVALID_DATA;
    }
    return ERROR_SUCCESS;
}

#endif
