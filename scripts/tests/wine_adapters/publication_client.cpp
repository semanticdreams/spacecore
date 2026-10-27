// Host Win32 model, NOT Wine/SDK proof. Compile the actual client and native core.
#include "record_publication_wine.h"
#include "record_publication_unix.h"
#include <windows.h>

#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <new>
#include <string>

namespace {
std::string selected, host;
std::wstring expected_input, expected_resolved;
std::string expected_host;
std::map<std::wstring, std::string> mapped_paths;
std::map<std::wstring, std::wstring> environment;
DWORD last_error;
unsigned loads, pins, frees, begins, identities, mappings, temp_sets;
bool mapped_live, denied, fail_copy;
uint64_t challenge_counter;
HMODULE ntdll = reinterpret_cast<HMODULE>(1), kernel = reinterpret_cast<HMODULE>(2), bridge = reinterpret_cast<HMODULE>(3);
bool is(const char* value) { return selected == value; }
template<class F> FARPROC exported(F function)
{
    FARPROC result;
    static_assert(sizeof(result) == sizeof(function));
    std::memcpy(&result, &function, sizeof(result));
    return result;
}
const char* __cdecl version() { return is("unsupported") ? "10.0" : "9.0 (host model)"; }
char* __cdecl map_path(const wchar_t* path)
{
    assert(std::wstring(path) == expected_resolved);
    const auto route = mapped_paths.find(path);
    assert(route != mapped_paths.end());
    host = route->second;
    assert(host == expected_host);
    ++mappings;
    if (is("map-null")) { last_error = 701; return nullptr; }
    char* result = static_cast<char*>(std::malloc(host.size() + 1));
    assert(result);
    std::memcpy(result, host.c_str(), host.size() + 1);
    mapped_live = true;
    if (is("copy-oom")) fail_copy = true;
    return result;
}
int32_t WINAPI entry(uint32_t code, void* frame)
{
    if (code == SRP_ENTRY_IDENTITY) {
        ++identities;
        auto& id = *static_cast<SrpIdentity*>(frame);
        const auto challenge = id.challenge;
        assert(challenge && challenge == challenge_counter);
        id = {};
        id.size = 112; id.abi = 1; id.challenge = id.echo = challenge;
        std::fill_n(id.pe_build_id, 32, 0xaa); std::fill_n(id.unix_build_id, 32, 0xaa);
        id.module_device = 7; id.module_inode = 9; id.architecture = SRP_ARCH_X86_64; id.features = 3;
        if (is("identity-status")) return SRP_UNSUCCESSFUL;
        if (is("identity-size")) ++id.size;
        if (is("identity-abi")) ++id.abi;
        if (is("identity-challenge")) ++id.challenge;
        if (is("identity-echo")) ++id.echo;
        if (is("identity-pe")) ++id.pe_build_id[31];
        if (is("identity-unix")) ++id.unix_build_id[0];
        if (is("identity-device")) ++id.module_device;
        if (is("identity-inode") || (is("fresh-identity") && begins)) ++id.module_inode;
        if (is("identity-arch")) ++id.architecture;
        if (is("identity-features")) id.features = 1;
        if (is("identity-extra-feature")) id.features = 7;
        return SRP_SUCCESS;
    }
    assert(code == SRP_ENTRY_OPERATION);
    auto& call = *static_cast<SrpCall*>(frame);
    if (call.opcode == SRP_BEGIN) {
        assert(!mapped_live && frees == mappings && identities > begins && pins == 1);
        assert(std::string_view(reinterpret_cast<const char*>(call.path.address), call.path.size) == expected_host);
        ++begins;
    }
    return srp_unix_call(&call);
}
}

void* operator new(std::size_t count)
{
    if (fail_copy) { fail_copy = false; throw std::bad_alloc(); }
    if (void* p = std::malloc(count)) return p;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

extern "C" {
void SetLastError(DWORD e) { last_error = e; }
DWORD GetLastError() { return last_error; }
HMODULE GetModuleHandleW(LPCWSTR name)
{
    if (std::wstring(name) == L"ntdll.dll") return ntdll;
    assert(std::wstring(name) == L"kernel32.dll"); return kernel;
}
HMODULE LoadLibraryA(const char* name)
{
    assert(!std::strcmp(name, "space_record_publication.dll")); ++loads;
    if (is("load-fail")) { last_error = 702; return nullptr; }
    return bridge;
}
BOOL FreeLibrary(HMODULE module) { assert(module == bridge && !pins); return TRUE; }
FARPROC GetProcAddress(HMODULE module, const char* name)
{
    if (!std::strcmp(name, "wine_get_version")) { assert(module == ntdll); return is("native") ? nullptr : exported(version); }
    if (!std::strcmp(name, "wine_get_unix_file_name")) { assert(module == kernel); return is("mapper-missing") ? nullptr : exported(map_path); }
    assert(module == bridge && !std::strcmp(name, "SpaceRecordPublicationCall"));
    return is("export-missing") ? nullptr : exported(entry);
}
BOOL GetModuleHandleExA(DWORD flags, LPCSTR address, HMODULE* result)
{
    assert(flags & GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS);
    HMODULE expected = address == reinterpret_cast<LPCSTR>(entry) ? bridge
        : address == reinterpret_cast<LPCSTR>(map_path) ? kernel : ntdll;
    if (flags & GET_MODULE_HANDLE_EX_FLAG_PIN) {
        if (is("pin-fail")) { last_error = 703; return FALSE; }
        ++pins; assert(expected == bridge);
    } else assert(flags & GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT);
    if (is("owner-fail")) { last_error = 704; return FALSE; }
    *result = is("export-foreign") && expected == bridge ? kernel : expected;
    return TRUE;
}
DWORD GetEnvironmentVariableW(LPCWSTR name, WCHAR* out, DWORD capacity)
{
    const auto found = environment.find(name);
    if (found == environment.end()) { last_error = ERROR_ENVVAR_NOT_FOUND; return 0; }
    const auto& value = found->second;
    last_error = 0;
    if (value.size() >= capacity) return static_cast<DWORD>(value.size() + 1);
    std::copy(value.begin(), value.end(), out); out[value.size()] = 0;
    return static_cast<DWORD>(value.size());
}
BOOL SetEnvironmentVariableW(LPCWSTR name, LPCWSTR value)
{
    ++temp_sets; assert(!loads && !mappings);
    if (is("temp-set-fail")) { last_error = 705; return FALSE; }
    environment[name] = is("temp-readback") ? L"Q:\\wrong" : value; return TRUE;
}
DWORD GetFullPathNameW(LPCWSTR path, DWORD capacity, WCHAR* out, WCHAR**)
{
    const auto value = std::wstring(path);
    assert(value == expected_input);
    if (is("fullpath-fail")) { last_error = 706; return 0; }
    if (is("fullpath-long")) return capacity;
    // Finite model: current directory and Q:'s drive directory are Q:\base.
    // In particular Q:record is NOT Q:\base\Q:record. No general Win32
    // resolver is implemented here; unsupported fixture inputs are test errors.
    static const std::map<std::wstring, std::wstring> resolutions {
        {L"Q:\\missing-leaf", L"Q:\\missing-leaf"}, {L"Q:\\other-leaf", L"Q:\\other-leaf"},
        {L"record", L"Q:\\base\\record"}, {L"other-record", L"Q:\\base\\other-record"},
        {L"Q:record", L"Q:\\base\\record"}, {L"Q:other-record", L"Q:\\base\\other-record"},
        {L"Q:\\.record", L"Q:\\.record"}, {L"Q:\\.other-record", L"Q:\\.other-record"}
    };
    const auto resolution = resolutions.find(value);
    assert(resolution != resolutions.end());
    const auto& full = resolution->second;
    if (full.size() >= capacity) return static_cast<DWORD>(full.size() + 1);
    std::copy(full.begin(), full.end(), out); out[full.size()] = 0;
    return static_cast<DWORD>(full.size());
}
UINT GetDriveTypeW(LPCWSTR root) { assert(std::wstring(root).substr(1) == L":\\"); return is("remote") ? DRIVE_REMOTE : DRIVE_FIXED; }
HANDLE GetProcessHeap() { return reinterpret_cast<HANDLE>(5); }
BOOL HeapFree(HANDLE heap, DWORD flags, void* address)
{
    assert(heap == reinterpret_cast<HANDLE>(5) && !flags && mapped_live); ++frees;
    std::free(address); mapped_live = false;
    if (is("free-fail")) { last_error = 707; return FALSE; }
    return TRUE;
}
BOOLEAN WINAPI SystemFunction036(PVOID out, ULONG count)
{
    assert(count == 8);
    if (is("random-fail")) return FALSE;
    const auto value = ++challenge_counter; std::memcpy(out, &value, 8); return TRUE;
}
HANDLE GetCurrentProcess() { return reinterpret_cast<HANDLE>(6); }
HANDLE GetCurrentThread() { return reinterpret_cast<HANDLE>(7); }
BOOL OpenThreadToken(HANDLE, DWORD access, BOOL self, HANDLE* token)
{
    assert(access == TOKEN_QUERY && self);
    if (denied) { *token = reinterpret_cast<HANDLE>(8); return TRUE; }
    last_error = ERROR_NO_TOKEN; return FALSE;
}
BOOL OpenProcessToken(HANDLE, DWORD access, HANDLE* token) { assert(access == TOKEN_QUERY); *token = reinterpret_cast<HANDLE>(9); return TRUE; }
BOOL CloseHandle(HANDLE) { return TRUE; }
BOOL GetTokenInformation(HANDLE, TOKEN_INFORMATION_CLASS kind, void* out, DWORD capacity, DWORD* returned)
{
    const DWORD bytes = kind == TokenGroups ? offsetof(TOKEN_GROUPS, Groups)
        : kind == TokenPrivileges ? offsetof(TOKEN_PRIVILEGES, Privileges) + 21 * sizeof(LUID_AND_ATTRIBUTES) : 4;
    *returned = bytes;
    if (!out) { last_error = ERROR_INSUFFICIENT_BUFFER; return FALSE; }
    assert(capacity == bytes); std::memset(out, 0, bytes);
    if (kind == TokenPrivileges) {
        const DWORD count = 21, ids[21] = {5,7,8,9,10,11,12,13,14,15,17,18,19,20,22,23,24,25,28,29,30};
        std::memcpy(out, &count, 4);
        for (unsigned i = 0; i < 21; ++i) {
            LUID_AND_ATTRIBUTES p {{ids[i], 0}, 0};
            std::memcpy(static_cast<char*>(out) + offsetof(TOKEN_PRIVILEGES, Privileges) + i * sizeof(p), &p, sizeof(p));
        }
    } else if (kind == TokenElevationType) { const DWORD e = TokenElevationTypeDefault; std::memcpy(out, &e, 4); }
    else assert(kind == TokenGroups);
    return TRUE;
}
}

int main(int argc, char** argv)
{
    assert(argc == 3); selected = argv[1];
    const std::string root = argv[2]; // Virtual Q:\ maps to this raw-byte host directory.
    mapped_paths = {{L"Q:\\missing-leaf", root + "/missing-leaf"},
                    {L"Q:\\other-leaf", root + "/other-leaf"},
                    {L"Q:\\base\\record", root + "/base/record"},
                    {L"Q:\\base\\other-record", root + "/base/other-record"},
                    {L"Q:\\.record", root + "/.record"},
                    {L"Q:\\.other-record", root + "/.other-record"}};
    environment[L"SPACE_WINE_PUBLICATION_BINDING"] = std::wstring(64, L'a') + L":7:9";
    if (is("binding-missing")) environment.erase(L"SPACE_WINE_PUBLICATION_BINDING");
    if (is("binding-empty")) environment[L"SPACE_WINE_PUBLICATION_BINDING"] = L"";
    if (is("binding-long")) environment[L"SPACE_WINE_PUBLICATION_BINDING"] = std::wstring(107, L'a');
    if (is("binding-wide")) environment[L"SPACE_WINE_PUBLICATION_BINDING"][0] = 0x100;
    if (is("temp-valid") || is("temp-set-fail") || is("temp-readback")) environment[L"SPACE_WINE_WINDOWS_TMP"] = L"Q:\\owned";
    if (is("temp-empty")) environment[L"SPACE_WINE_WINDOWS_TMP"] = L"";
    if (is("temp-malformed")) environment[L"SPACE_WINE_WINDOWS_TMP"] = L"relative";
    if (is("native")) environment[L"SPACE_WINE_WINDOWS_TMP"] = L"bad native ignored";
    bool threw = false;
    try {
        assert(record_publication::wine::detected() == !is("native"));
        record_publication::wine::initialize_process_environment();
        if (is("native")) { assert(!loads && !temp_sets); return 0; }
        assert(temp_sets == (is("temp-valid") ? 2u : 0u));
        std::filesystem::path input("Q:\\missing-leaf");
        if (is("relative")) input = "record";
        if (is("dotfile")) input = "Q:\\.record";
        if (is("drive-relative")) input = "Q:record";
        if (is("nul")) input = std::string("Q:\\bad\0leaf", 11);
        if (is("reserved")) input = "Q:\\NUL.txt";
        if (is("reserved-parent")) input = "Q:\\COM1\\record";
        if (is("reserved-spaced")) input = "Q:\\CON .txt";
        if (is("ads")) input = "Q:\\record:stream";
        if (is("unc")) input = "\\\\server\\share\\record";
        if (is("device")) input = "\\\\?\\Q:\\record";
        if (is("slash-unc")) input = "//server/share/record";
        if (is("trailing-dot")) input = "Q:\\record.";
        if (is("wildcard")) input = "Q:\\bad*";
        expected_input = input.wstring();
        expected_resolved = is("relative") || is("drive-relative") ? L"Q:\\base\\record"
            : is("dotfile") ? L"Q:\\.record" : L"Q:\\missing-leaf";
        expected_host = root + (is("relative") || is("drive-relative") ? "/base/record"
            : is("dotfile") ? "/.record" : "/missing-leaf");
        denied = is("authority");
        unsigned hooks = 0;
        record_publication::Hooks callbacks;
        callbacks.before_write = [&] { assert(hooks++ == 0); };
        callbacks.before_security = [&] { assert(hooks++ == 1); if (is("hook-denial")) denied = true; };
        callbacks.before_commit = [&] { assert(hooks++ == 2); };
        callbacks.before_cleanup = [&] { ++hooks; };
        const auto result = record_publication::wine::publish(input, "raw host publication", callbacks);
        assert(result.committed && !result.cleanup_error && hooks == 4);
        if (is("normal") || is("relative") || is("drive-relative") || is("dotfile") || is("raw-bytes")) {
            // Two distinguishable requests must reach two distinguishable host
            // destinations, not an argv-selected file independent of the leaf.
            input = is("relative") ? "other-record" : is("drive-relative") ? "Q:other-record"
                : is("dotfile") ? "Q:\\.other-record" : "Q:\\other-leaf";
            expected_input = input.wstring();
            expected_resolved = is("relative") || is("drive-relative") ? L"Q:\\base\\other-record"
                : is("dotfile") ? L"Q:\\.other-record" : L"Q:\\other-leaf";
            expected_host = root + (is("relative") || is("drive-relative") ? "/base/other-record"
                : is("dotfile") ? "/.other-record" : "/other-leaf");
            const auto second = record_publication::wine::publish(input, "second destination", {});
            assert(second.committed && !second.cleanup_error && begins == 2 && loads == 1 && pins == 1);
        }
        if (is("pin-once") || is("fresh-identity") || is("fresh-binding")) {
            if (is("fresh-binding")) environment[L"SPACE_WINE_PUBLICATION_BINDING"] = std::wstring(64, L'a') + L":7:10";
            const auto again = record_publication::wine::publish(input, "second publication", {});
            assert(again.committed && begins == 2 && loads == 1 && pins == 1);
        }
    } catch (const std::exception&) { threw = true; }
    const bool success = is("normal") || is("raw-bytes") || is("relative") || is("dotfile") || is("drive-relative") || is("pin-once") || is("temp-valid");
    assert(threw != success && !mapped_live);
    if (!success && !is("hook-denial") && !is("fresh-identity") && !is("fresh-binding")) assert(!begins);
    if (is("copy-oom") || is("free-fail")) assert(frees == 1);
    return 0;
}
