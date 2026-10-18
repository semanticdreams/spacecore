#ifndef NOMINMAX
#define NOMINMAX
#endif

#include "record_publication_wine.h"
#include "record_publication_wine_binding.h"
#include "record_publication_wine_driver.h"
#include "record_publication_wine_authority.h"
#include "wine_owned_environment.h"

#include <windows.h>

#include <cstring>
#include <memory>
#include <string>

// RtlGenRandom is exported under this name by advapi32, including Wine9.
extern "C" BOOLEAN WINAPI SystemFunction036(PVOID, ULONG);

namespace record_publication::wine {
namespace {

using Entry = int32_t (WINAPI *)(uint32_t, void*);
using Version = const char* (__cdecl *)();
using Mapper = char* (__cdecl *)(const wchar_t*);

template<class Function>
Function function_pointer(FARPROC address)
{
    static_assert(sizeof(Function) == sizeof(address), "Win32 export pointer width");
    Function result;
    std::memcpy(&result, &address, sizeof(result));
    return result;
}

[[noreturn]] void fail(const char* phase, DWORD error = ERROR_INVALID_DATA)
{
    throw std::runtime_error(std::string("record publication: Wine ") + phase + " error=" + std::to_string(error));
}

HMODULE loaded(const wchar_t* name)
{
    const auto module = GetModuleHandleW(name);
    if (!module) { const auto error = GetLastError(); fail("loaded module", error); }
    return module;
}

void check_owner(HMODULE module, FARPROC address, DWORD flags = GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT)
{
    HMODULE owner = nullptr;
    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | flags,
                           reinterpret_cast<LPCSTR>(address), &owner)) {
        const auto error = GetLastError(); fail("export owner/pin", error);
    }
    if (owner != module) fail("foreign export");
}

void require_runtime()
{
#ifndef _WIN64
    fail("requires win64", ERROR_BAD_EXE_FORMAT);
#endif
    const auto ntdll = loaded(L"ntdll.dll");
    const auto address = GetProcAddress(ntdll, "wine_get_version");
    if (!address) fail("missing Wine runtime");
    check_owner(ntdll, address);
    const auto version = function_pointer<Version>(address)();
    if (!version || version[0] != '9' || version[1] != '.') fail("unsupported runtime");
}

detail::Binding current_binding()
{
    // Max106 ASCII bytes plus terminator. No allocation or unbounded env retry.
    wchar_t value[107] {};
    SetLastError(ERROR_SUCCESS);
    const auto count = GetEnvironmentVariableW(L"SPACE_WINE_PUBLICATION_BINDING", value, 107);
    if (!count || count > 106 || value[count] != 0) {
        const auto error = GetLastError(); fail("publication binding", error ? error : ERROR_INVALID_DATA);
    }
    char ascii[106];
    for (DWORD i = 0; i < count; ++i) {
        if (static_cast<uint32_t>(value[i]) > 127) fail("non-ASCII binding");
        ascii[i] = static_cast<char>(value[i]);
    }
    return detail::parse_binding(std::string_view(ascii, count));
}

void verify_identity(Entry entry, const detail::Binding& binding)
{
    uint64_t challenge = 0;
    if (!SystemFunction036(&challenge, sizeof(challenge)) || !challenge) fail("identity challenge");
    SrpIdentity identity {};
    identity.size = sizeof(identity);
    identity.abi = SRP_ABI;
    identity.challenge = challenge;
    const auto status = entry(SRP_ENTRY_IDENTITY, &identity);
    if (status != SRP_SUCCESS) throw std::runtime_error("record publication: Wine identity NTSTATUS=" + std::to_string(status));
    detail::validate_identity(identity, binding, challenge);
}

struct LibraryDeleter {
    void operator()(void* module) const noexcept
    {
        if (!FreeLibrary(static_cast<HMODULE>(module))) std::terminate();
    }
};

struct Client {
    Entry entry;
    Mapper mapper;
};

const Client& client()
{
    // Thread-safe one-time initialization; no global current operation or unload.
    static const Client pinned = [] {
        require_runtime();
        const auto binding = current_binding();
        const auto module = LoadLibraryA("space_record_publication.dll");
        if (!module) { const auto error = GetLastError(); fail("builtin load", error); }
        std::unique_ptr<void, LibraryDeleter> pending(module);
        const auto address = GetProcAddress(module, "SpaceRecordPublicationCall");
        if (!address) { const auto error = GetLastError(); fail("operation export", error); }
        check_owner(module, address);
        const auto kernel = loaded(L"kernel32.dll");
        const auto mapping = GetProcAddress(kernel, "wine_get_unix_file_name");
        if (!mapping) { const auto error = GetLastError(); fail("mapping export", error); }
        check_owner(kernel, mapping);
        const auto entry = function_pointer<Entry>(address);
        verify_identity(entry, binding);
        check_owner(module, address, GET_MODULE_HANDLE_EX_FLAG_PIN);
        pending.release(); // Pinned for process lifetime, including every context retirement.
        return Client {entry, function_pointer<Mapper>(mapping)};
    }();
    return pinned;
}

bool component_valid(std::wstring_view part)
{
    if (!space_wine_owned_component_valid(part.data(), static_cast<DWORD>(part.size()))) return false;
    // DOS device recognition also trims spaces before the extension and treats
    // superscript1/2/3 as COM/LPT digits. Do not let the mapper reinterpret these.
    auto stem = std::wstring(part.substr(0, part.find(L'.')));
    while (!stem.empty() && stem.back() == L' ') stem.pop_back();
    if (stem.empty()) return true; // A leading-dot filename is not a DOS device.
    if (stem.size() == 4) {
        if (stem[3] == 0x00b9) stem[3] = L'1';
        else if (stem[3] == 0x00b2) stem[3] = L'2';
        else if (stem[3] == 0x00b3) stem[3] = L'3';
    }
    return space_wine_owned_component_valid(stem.data(), static_cast<DWORD>(stem.size()));
}

std::wstring windows_path(const std::filesystem::path& destination)
{
    const auto input = destination.wstring();
    if (input.empty() || input.size() >= 32768 || input.find(L'\0') != std::wstring::npos) fail("path syntax");
    const auto separator = [](wchar_t c) { return c == L'\\' || c == L'/'; };
    if (input.size() >= 2 && separator(input[0]) && separator(input[1])) fail("UNC/device path");
    const bool drive = input.size() >= 2 && input[1] == L':'
        && ((input[0] >= L'A' && input[0] <= L'Z') || (input[0] >= L'a' && input[0] <= L'z'));
    size_t component = drive ? 2 : 0;
    for (size_t i = component; i <= input.size(); ++i) {
        if (i == input.size() || separator(input[i])) {
            const auto part = std::wstring_view(input).substr(component, i - component);
            if (!part.empty() && part != L"." && part != L".."
                && !component_valid(part)) fail("reserved path component");
            component = i + 1;
        } else if (input[i] < 32 || input[i] == L':' || input[i] == L'<' || input[i] == L'>'
                   || input[i] == L'"' || input[i] == L'|' || input[i] == L'?' || input[i] == L'*') fail("path syntax");
    }
    wchar_t full[32768] {};
    const auto count = GetFullPathNameW(input.c_str(), 32768, full, nullptr);
    if (!count || count >= 32768) { const auto error = GetLastError(); fail("full path", error); }
    if (count < 3 || full[1] != L':' || !separator(full[2])
        || !((full[0] >= L'A' && full[0] <= L'Z') || (full[0] >= L'a' && full[0] <= L'z'))) fail("nonlocal path");
    const wchar_t root[] {full[0], L':', L'\\', 0};
    const auto type = GetDriveTypeW(root);
    if (type != DRIVE_FIXED && type != DRIVE_REMOVABLE && type != DRIVE_RAMDISK && type != DRIVE_CDROM) fail("nonlocal drive");
    return std::wstring(full, count);
}

struct MappingDeleter {
    void operator()(char* bytes) const noexcept
    {
        if (!HeapFree(GetProcessHeap(), 0, bytes)) std::terminate();
    }
};

std::string host_path(Mapper mapper, const std::wstring& path)
{
    const auto allocation = mapper(path.c_str());
    if (!allocation) { const auto error = GetLastError(); fail("path mapping", error); }
    std::unique_ptr<char, MappingDeleter> owned(allocation);
    std::string bytes(allocation); // Raw host bytes, never a PE fs::path/UTF conversion.
    owned.release();
    if (!HeapFree(GetProcessHeap(), 0, allocation)) { const auto error = GetLastError(); fail("mapping free", error); }
    if (bytes.empty() || bytes.front() != '/') fail("nonabsolute host mapping");
    return bytes;
}

} // namespace

bool detected()
{
    return GetProcAddress(loaded(L"ntdll.dll"), "wine_get_version") != nullptr;
}

void initialize_process_environment()
{
    if (!detected()) return; // Native Windows neither reads handoff nor loads helpers.
    require_runtime();
    const auto error = space_wine_apply_owned_environment(FALSE);
    if (error) fail("owned environment apply", error);
}

Result publish(const std::filesystem::path& destination, std::string_view payload, const Hooks& hooks)
{
    require_runtime(); // Presence with an unsupported runtime is never native fallback.
    const auto path = windows_path(destination);
    const auto& pinned = client();
    const auto bytes = host_path(pinned.mapper, path);
    verify_identity(pinned.entry, current_binding()); // Fresh binding/challenge before EVERY BEGIN.
    auto authority = [] { return space_record_publication_check_authority(); };
    return detail::drive(pinned.entry, bytes, payload, hooks, authority);
}

} // namespace record_publication::wine
