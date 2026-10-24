#include "record_publication.h"
#include "record_publication_wine_binding.h"
#include "record_publication_wine_support.h"

#include <array>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#include <aclapi.h>
#include <sddl.h>
#include <winioctl.h>
#include "record_publication_wine.h"
#include "wine_owned_environment.h"

extern "C" BOOLEAN WINAPI SystemFunction036(PVOID, ULONG);
#else
#include <cerrno>
#include <csignal>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#ifdef __linux__
#include <sys/xattr.h>
#endif
#endif

namespace fs = std::filesystem;
namespace rp = record_publication;
namespace {

void check(bool condition, const std::string& message)
{
    if (!condition) throw std::runtime_error(message);
}

using Binding = rp::wine::detail::Binding;

std::string build_id(const Binding& value)
{
    std::string text;
    for (const auto byte : value.build_id) {
        text += "0123456789abcdef"[byte >> 4];
        text += "0123456789abcdef"[byte & 15];
    }
    return text;
}

void validate_support_identity(const SrptIdentity& identity, const Binding& expected, uint64_t original)
{
    check(identity.size == sizeof(identity) && identity.abi == SRPT_ABI
        && identity.architecture == SRPT_ARCH_X86_64 && identity.features == SRPT_FEATURES
        && identity.challenge == original && identity.echo == original
        && std::equal(expected.build_id.begin(), expected.build_id.end(), identity.pe_build_id)
        && std::equal(expected.build_id.begin(), expected.build_id.end(), identity.unix_build_id)
        && identity.module_device == expected.module_device && identity.module_inode == expected.module_inode,
        "independent support binding matches actual selected PE/Unix pair");
}

std::string report_json(const Binding& admitted)
{
    return "{\"version\":1,\"backend\":\"wine-posix\",\"build_id\":\"" + build_id(admitted)
        + "\",\"module_device\":" + std::to_string(admitted.module_device)
        + ",\"module_inode\":" + std::to_string(admitted.module_inode)
        + ",\"categories\":{\"common\":\"passed\",\"host-policy\":\"passed\",\"mapping-authority\":\"passed\","
          "\"native-windows\":\"not-exercised\"},\"foreign_uid_probe\":\"not-configured\"}\n";
}

#ifdef _WIN32
bool under_wine = false;
const char* child_phase = "entry";
DWORD child_error = ERROR_SUCCESS;
using WineEntry = int32_t (WINAPI *)(uint32_t, void*);

void win_check(BOOL ok, const char* phase)
{
    if (!ok) {
        child_error = ::GetLastError();
        throw std::runtime_error(std::string(phase) + " error=" + std::to_string(child_error));
    }
}

struct CheckedHandle {
    HANDLE value = nullptr;
    CheckedHandle() = default;
    CheckedHandle(const CheckedHandle&) = delete;
    CheckedHandle& operator=(const CheckedHandle&) = delete;
    ~CheckedHandle() { if (value && value != INVALID_HANDLE_VALUE && !::CloseHandle(value)) std::abort(); }
    void close()
    {
        const auto handle = value;
        value = nullptr;
        win_check(::CloseHandle(handle), "test handle close");
    }
};

template<class Function>
Function exported(HMODULE module, const char* name)
{
    const auto address = ::GetProcAddress(module, name);
    win_check(address != nullptr, "test export");
    HMODULE owner = nullptr;
    win_check(::GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCSTR>(address), &owner), "test export owner");
    check(owner == module, "test export belongs to selected module");
    Function function;
    static_assert(sizeof(function) == sizeof(address));
    std::memcpy(&function, &address, sizeof(function));
    return function;
}

std::wstring environment(const wchar_t* name)
{
    wchar_t value[32768] {};
    ::SetLastError(ERROR_SUCCESS);
    const auto size = ::GetEnvironmentVariableW(name, value, 32768);
    win_check(size != 0 && size < 32768, "test environment");
    check(value[size] == 0, "terminated test environment");
    return {value, size};
}

Binding binding(const wchar_t* name)
{
    const auto value = environment(name);
    check(value.size() <= 106, "bounded test binding");
    std::string ascii;
    for (const auto unit : value) {
        check(unit > 0 && unit < 128, "ASCII test binding");
        ascii.push_back(static_cast<char>(unit));
    }
    return rp::wine::detail::parse_binding(ascii);
}

uint64_t challenge()
{
    uint64_t value = 0;
    check(SystemFunction036(&value, sizeof(value)) && value, "test identity challenge");
    return value;
}

std::string host_path(const fs::path& path)
{
    using Mapper = char* (__cdecl *)(const wchar_t*);
    const auto map = exported<Mapper>(::GetModuleHandleW(L"kernel32.dll"), "wine_get_unix_file_name");
    char* allocation = map(fs::absolute(path).c_str());
    win_check(allocation != nullptr, "fixture host mapping");
    std::string bytes(allocation);
    win_check(::HeapFree(::GetProcessHeap(), 0, allocation), "fixture host mapping free");
    check(!bytes.empty() && bytes.front() == '/', "absolute raw host mapping");
    while (bytes.size() > 1 && bytes.back() == '/') bytes.pop_back();
    return bytes;
}

fs::path windows_path(const std::string& bytes)
{
    using Mapper = wchar_t* (__cdecl *)(const char*);
    const auto map = exported<Mapper>(::GetModuleHandleW(L"kernel32.dll"), "wine_get_dos_file_name");
    wchar_t* allocation = map(bytes.c_str());
    win_check(allocation != nullptr, "fixture Windows mapping");
    const fs::path path(allocation);
    win_check(::HeapFree(::GetProcessHeap(), 0, allocation), "fixture Windows mapping free");
    check(host_path(path) == bytes, "raw host mapping roundtrip (no UTF-8 assumption)");
    return path;
}

WineEntry support_entry = nullptr;
Binding support_binding {}, production_binding {};

void verify_support()
{
    SrptIdentity identity {};
    identity.size = sizeof(identity);
    identity.abi = SRPT_ABI;
    identity.challenge = challenge();
    const auto original = identity.challenge;
    check(support_entry(SRPT_ENTRY_IDENTITY, &identity) == SRPT_SUCCESS, "support identity status");
    validate_support_identity(identity, support_binding, original);
}

void load_support()
{
    support_binding = binding(L"SPACE_WINE_PUBLICATION_TEST_BINDING");
    production_binding = binding(L"SPACE_WINE_PUBLICATION_BINDING");
    const auto module = ::LoadLibraryW(L"space_record_publication_tests.dll");
    win_check(module != nullptr, "support builtin load");
    support_entry = exported<WineEntry>(module, "SpaceRecordPublicationTestsCall");
    verify_support();
    // Intentionally retained until process exit; root contexts must not outlive it.
}

struct HostRoot {
    uint64_t id = 0;
    std::string base;
    explicit HostRoot(const fs::path& path) : base(host_path(path))
    {
        auto frame = request(SRPT_RETAIN, base);
        frame.root = 0;
        invoke(frame);
        id = frame.root;
    }
    HostRoot(const HostRoot&) = delete;
    HostRoot& operator=(const HostRoot&) = delete;
    ~HostRoot()
    {
        if (id) {
            auto frame = request(SRPT_RELEASE, "");
            if (support_entry(SRPT_ENTRY_FIXTURE, &frame) != SRPT_SUCCESS) std::abort();
        }
    }
    SrptCall request(uint32_t opcode, const std::string& path) const
    {
        SrptCall frame {};
        frame.size = sizeof(frame);
        frame.abi = SRPT_ABI;
        frame.opcode = opcode;
        frame.root = id;
        check(path.size() < sizeof(frame.path), "bounded fixture path");
        std::memcpy(frame.path, path.c_str(), path.size() + 1);
        return frame;
    }
    static void invoke(SrptCall& frame)
    {
        const auto status = support_entry(SRPT_ENTRY_FIXTURE, &frame);
        check(status == SRPT_SUCCESS, "host fixture status=" + std::to_string(status) + " errno=" + std::to_string(frame.os_error));
    }
    std::string relative(const fs::path& path) const
    {
        const auto bytes = host_path(path);
        if (bytes == base) return "";
        check(bytes.size() > base.size() && bytes.compare(0, base.size() + 1, base + "/") == 0,
            "fixture stays under retained host root");
        return bytes.substr(base.size() + 1);
    }
    SrptCall observe(const fs::path& path, uint64_t offset = 0) const
    {
        auto frame = request(SRPT_OBSERVE, relative(path));
        frame.offset = offset;
        invoke(frame);
        return frame;
    }
    void mutate(uint32_t opcode, const fs::path& path, uint32_t mode = 0,
                const std::string& data = "", const fs::path& other = {}) const
    {
        auto frame = request(opcode, relative(path));
        frame.mode = mode;
        check(data.size() <= sizeof(frame.data), "bounded fixture data");
        frame.data_size = static_cast<uint32_t>(data.size());
        std::memcpy(frame.data, data.data(), data.size());
        if (!other.empty()) {
            const auto second = opcode == SRPT_SYMLINK ? other.generic_string() : relative(other);
            check(second.size() < sizeof(frame.other), "bounded second fixture path");
            std::memcpy(frame.other, second.c_str(), second.size() + 1);
        }
        invoke(frame);
    }
    std::string bytes(const fs::path& path) const
    {
        auto first = observe(path);
        check((first.mode & 0170000) == 0100000 && first.file_size <= 64 * 1024 * 1024,
            "bounded regular fixture read");
        std::string result(reinterpret_cast<const char*>(first.data), first.data_size);
        while (result.size() < first.file_size) {
            const auto next = observe(path, result.size());
            check(next.device == first.device && next.inode == first.inode && next.file_size == first.file_size
                && next.data_size, "stable chunked host read");
            result.append(reinterpret_cast<const char*>(next.data), next.data_size);
        }
        check(result.size() == first.file_size, "exact host read length");
        return result;
    }
};

std::unique_ptr<HostRoot> owned_tmp;

std::set<std::string> host_names(const HostRoot& root, const fs::path& path);

void host_private(const fs::path& path, bool directory)
{
    const auto info = owned_tmp->observe(path);
    const auto root = owned_tmp->observe(windows_path(owned_tmp->base));
    check((info.mode & 0177777) == (directory ? 0040700u : 0100600u)
        && info.uid == root.uid && (directory || info.links == 1), "actual owned host0700/0600 privacy");
}
#endif

void write(const fs::path& path, const std::string& text)
{
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    output << text;
    output.close();
    check(static_cast<bool>(output), "fixture write failed");
}

std::string read(const fs::path& path)
{
#ifdef _WIN32
    if (under_wine) return owned_tmp->bytes(path);
    auto absolute = fs::absolute(path);
    absolute.make_preferred();
    std::ifstream input(fs::path(L"\\\\?\\" + absolute.native()), std::ios::binary);
#else
    std::ifstream input(path, std::ios::binary);
#endif
    check(static_cast<bool>(input), "fixture read failed");
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

template<typename Function>
std::string rejects(Function action)
{
    try { action(); }
    catch (const std::exception& error) { return error.what(); }
    throw std::runtime_error("expected explicit precommit failure");
}

void private_contract_models()
{
    // Pure consumer checks run natively too. These are not loaded-Wine proof.
    const std::string id(64, 'a');
    const auto expected = rp::wine::detail::parse_binding(id + ":12:34");
    SrptIdentity identity {};
    identity.size = sizeof(identity);
    identity.abi = SRPT_ABI;
    identity.challenge = identity.echo = 42;
    std::fill(std::begin(identity.pe_build_id), std::end(identity.pe_build_id), 0xaa);
    std::fill(std::begin(identity.unix_build_id), std::end(identity.unix_build_id), 0xaa);
    identity.module_device = 12;
    identity.module_inode = 34;
    identity.architecture = SRPT_ARCH_X86_64;
    identity.features = SRPT_FEATURES;
    validate_support_identity(identity, expected, 42);
    for (int field = 0; field < 11; ++field) {
        auto bad = identity;
        switch (field) {
        case 0: ++bad.size; break;
        case 1: ++bad.abi; break;
        case 2: ++bad.challenge; break;
        case 3: ++bad.echo; break;
        case 4: ++bad.pe_build_id[31]; break;
        case 5: ++bad.unix_build_id[0]; break;
        case 6: ++bad.module_device; break;
        case 7: bad.module_inode = 0; break;
        case 8: ++bad.architecture; break;
        case 9: bad.features = 1; break;
        case 10: bad.features = 15; break;
        }
        rejects([&] { validate_support_identity(bad, expected, 42); });
    }
    check(report_json(expected) == "{\"version\":1,\"backend\":\"wine-posix\",\"build_id\":\"" + id
        + "\",\"module_device\":12,\"module_inode\":34,\"categories\":{\"common\":\"passed\",\"host-policy\":\"passed\","
          "\"mapping-authority\":\"passed\",\"native-windows\":\"not-exercised\"},\"foreign_uid_probe\":\"not-configured\"}\n",
        "schema1 report producer has exactly the fixed fields/statuses");
}

struct Fixture {
    fs::path root, cleanup_root;
#ifdef _WIN32
    bool wine_long_paths = false;
    bool preserve_wine_fixture = false;
#endif
    explicit Fixture(bool long_paths = false)
    {
#ifdef _WIN32
        wine_long_paths = long_paths && under_wine;
        root = fs::temp_directory_path() / ("record-publication-" + std::to_string(
            std::chrono::steady_clock::now().time_since_epoch().count()));
        if (under_wine) owned_tmp->mutate(SRPT_MKDIR, root, 0700);
        else check(fs::create_directory(root), "exclusive fixture creation");
#else
        auto pattern = (fs::temp_directory_path() / "record-publication-XXXXXX").string();
        std::vector<char> name(pattern.begin(), pattern.end());
        name.push_back('\0');
        check(::mkdtemp(name.data()) != nullptr, "exclusive private fixture creation");
        root = name.data();
#endif
        cleanup_root = root;
#ifdef _WIN32
        if (long_paths && !under_wine) {
            auto absolute = fs::absolute(root);
            absolute.make_preferred();
            cleanup_root = fs::path(L"\\\\?\\" + absolute.native());
        }
#else
        (void)long_paths;
#endif
    }
    ~Fixture()
    {
#ifdef _WIN32
        // Long Wine fixtures use checked fixed-name host cleanup, armed only
        // after publication/observation checks pass. Preserve failed evidence.
        if (wine_long_paths) return;
        if (under_wine && preserve_wine_fixture) return; // Explicit finalizer already reported retained evidence.
#endif
        std::error_code ignored;
#ifdef _WIN32
        if (under_wine) std::cerr << "record publication diagnostic: fixture-cleanup-begin\n" << std::flush;
#endif
        fs::remove_all(cleanup_root, ignored); // Test-owned fixture only; production never sweeps.
#ifdef _WIN32
        if (under_wine) std::cerr << "record publication diagnostic: fixture-cleanup-returned\n" << std::flush;
#endif
    }
};

fs::path anchor(const fs::path& parent) { return parent / ".space-publication"; }

fs::path only_attempt(const fs::path& parent)
{
    std::vector<fs::path> attempts;
    for (const auto& item : fs::directory_iterator(anchor(parent))) attempts.push_back(item.path());
    check(attempts.size() == 1 && fs::is_directory(attempts.front()), "exactly one owned attempt");
    return attempts.front();
}

void clean_anchor(const fs::path& parent)
{
#ifdef _WIN32
    if (under_wine) {
        // The support observer checks the actual directory type and reports
        // all host entries or an explicit error, without MinGW MAX_PATH limits.
        check(host_names(*owned_tmp, anchor(parent)).empty(), "no attempt residue inside persistent anchor");
        return;
    }
#endif
    check(fs::is_directory(anchor(parent)), "persistent anchor intentionally retained");
    check(fs::is_empty(anchor(parent)), "no attempt residue inside persistent anchor");
}

#ifndef _WIN32
mode_t mode(const fs::path& path)
{
    struct stat info {};
    check(::lstat(path.c_str(), &info) == 0, "fixture lstat");
    return info.st_mode & 07777;
}
void chmod_checked(const fs::path& path, mode_t value)
{
    check(::chmod(path.c_str(), value) == 0, "fixture chmod");
}
void private_object(const fs::path& path, bool directory)
{
    check(mode(path) == (directory ? 0700 : 0600), "exact private mode before bytes");
}
#else
struct Policy { std::vector<unsigned char> owner, group, dacl; };
Policy windows_policy(const fs::path& path)
{
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    PSID owner = nullptr, group = nullptr;
    PACL dacl = nullptr;
    check(::GetNamedSecurityInfoW(const_cast<wchar_t*>(path.c_str()), SE_FILE_OBJECT,
        OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
        &owner, &group, &dacl, nullptr, &descriptor) == ERROR_SUCCESS, "inspect policy fixture");
    Policy result;
    result.owner.assign(static_cast<unsigned char*>(owner), static_cast<unsigned char*>(owner) + ::GetLengthSid(owner));
    result.group.assign(static_cast<unsigned char*>(group), static_cast<unsigned char*>(group) + ::GetLengthSid(group));
    result.dacl.assign(reinterpret_cast<unsigned char*>(dacl), reinterpret_cast<unsigned char*>(dacl) + dacl->AclSize);
    ::LocalFree(descriptor);
    return result;
}
void private_object(const fs::path& path, bool directory)
{
    if (under_wine) { host_private(path, directory); return; }
    const auto policy = windows_policy(path);
    auto* dacl = reinterpret_cast<PACL>(const_cast<unsigned char*>(policy.dacl.data()));
    check(dacl->AceCount == 1, "one owner-only ACE");
    void* raw = nullptr;
    check(::GetAce(dacl, 0, &raw), "inspect private ACE");
    const auto* ace = static_cast<ACCESS_ALLOWED_ACE*>(raw);
    check(ace->Header.AceType == ACCESS_ALLOWED_ACE_TYPE && ace->Mask == FILE_ALL_ACCESS
        && ::EqualSid(const_cast<DWORD*>(&ace->SidStart), const_cast<unsigned char*>(policy.owner.data()))
        && !(ace->Header.AceFlags & INHERIT_ONLY_ACE), "effective owner-only file/directory policy");
}
#endif

void basic_publication()
{
    Fixture fixture;
    const auto destination = fixture.root / std::string(245, 'r');
    const std::string binary("after \xE9\x9B\xAA\0tail", 14);
    for (const auto& payload : {std::string(), std::string("before"), binary, std::string(262145, 'x')}) {
        rp::Hooks hooks;
        hooks.before_write = [&] {
            const auto attempt = only_attempt(fixture.root);
            private_object(anchor(fixture.root), true);
            private_object(attempt, true);
            private_object(attempt / "record", false);
            check(read(attempt / "record").empty(), "native file is empty before writer starts");
            check(std::distance(fs::directory_iterator(attempt), fs::directory_iterator()) == 1,
                "one native record, no inert record.tmp");
        };
        hooks.before_security = [&] {
            const auto attempt = only_attempt(fixture.root);
            private_object(anchor(fixture.root), true);
            private_object(attempt, true);
            private_object(attempt / "record", false);
            check(read(attempt / "record") == payload, "native writer completes and flushes exact bytes before security hook");
        };
        const auto result = rp::publish(destination, payload, hooks);
        check(result.committed && !result.cleanup_error, "new/overwrite result");
        check(read(destination) == payload, "exact final bytes including empty/binary/multiple write chunks");
        clean_anchor(fixture.root);
        check(std::distance(fs::directory_iterator(fixture.root), fs::directory_iterator()) == 2,
            "exact entries: destination and persistent anchor");
    }
}

#ifdef _WIN32
struct WineLongFixtureCleanup {
    const fs::path root;
    bool removed = false;
    explicit WineLongFixtureCleanup(const fs::path& path) : root(path) {}
    WineLongFixtureCleanup(const WineLongFixtureCleanup&) = delete;
    WineLongFixtureCleanup& operator=(const WineLongFixtureCleanup&) = delete;
    void remove()
    {
        auto parent = root;
        for (int i = 0; i < 4; ++i) parent /= std::string(70, static_cast<char>('a' + i));
        // Never remove evidence of a supposedly clean publication's residue.
        clean_anchor(parent);
        const auto destination = parent / fs::u8path("record-雪-🌱");
        const auto mapped = host_path(destination);
        check(host_names(*owned_tmp, parent) == std::set<std::string>{".space-publication", mapped.substr(mapped.rfind('/') + 1)},
            "only fixed long fixture descendants are eligible for cleanup");
        owned_tmp->mutate(SRPT_UNLINK, destination);
        owned_tmp->mutate(SRPT_RMDIR, anchor(parent));
        for (int i = 0; i < 4; ++i) {
            owned_tmp->mutate(SRPT_RMDIR, parent);
            parent = parent.parent_path();
        }
        check(parent == root, "fixed long fixture cleanup stays below its root");
        owned_tmp->mutate(SRPT_RMDIR, root);
        removed = true;
    }
    ~WineLongFixtureCleanup()
    {
        if (!removed) {
            try { remove(); }
            catch (const std::exception& error) {
                std::cerr << "Wine long fixture cleanup failed: " << error.what() << '\n';
                std::abort();
            }
        }
    }
};
#endif

void unicode_long_paths_and_payload_snapshot()
{
    struct FixtureUnwind {};
    for (bool unwind : {false, true}) {
        fs::path removed_root;
        try {
            Fixture fixture(true);
            removed_root = fixture.cleanup_root;
            auto parent = fixture.root;
            for (int i = 0; i < 4; ++i) {
                parent /= std::string(70, static_cast<char>('a' + i));
#ifdef _WIN32
                if (under_wine) owned_tmp->mutate(SRPT_MKDIR, parent, 0700);
                else {
                    auto absolute = fs::absolute(parent);
                    absolute.make_preferred();
                    win_check(::CreateDirectoryW((L"\\\\?\\" + absolute.native()).c_str(), nullptr), "long parent fixture");
                }
#else
                check(fs::create_directory(parent), "long parent fixture");
#endif
            }
            check(parent.native().size() > 260, "fixture exceeds legacy Windows MAX_PATH");
#ifdef _WIN32
            if (!under_wine) {
                check(fixture.cleanup_root.native().compare(0, 4, L"\\\\?\\") == 0
                    && fixture.root.native().compare(0, 4, L"\\\\?\\") != 0,
                    "native long fixture inspection/cleanup is extended, public root stays ordinary");
            }
#endif
            const auto destination = parent / fs::u8path("record-雪-🌱");
            std::string payload("owned\0binary", 12);
            const auto original = payload;
            rp::Hooks hooks;
            hooks.before_write = [&] { std::fill(payload.begin(), payload.end(), 'x'); };
            const auto result = rp::publish(destination, payload, hooks);
            check(result.committed && !result.cleanup_error && read(destination) == original,
                "Unicode long-path publication owns original binary snapshot");
            // Lexical suffix only: querying the ordinary long path here would
            // reintroduce a native Windows MAX_PATH dependency into the fixture.
            clean_anchor(fixture.cleanup_root / parent.lexically_relative(fixture.root));
#ifdef _WIN32
            if (under_wine) {
                const auto private_anchor = anchor(parent);
                check(host_names(*owned_tmp, private_anchor).empty(), "actual long host anchor is empty immediately after publication");
                const auto control = private_anchor / "observer-control";
                owned_tmp->mutate(SRPT_CREATE, control, 0600, "keep");
                const std::set<std::string> expected {"observer-control"};
                check(host_names(*owned_tmp, private_anchor) == expected, "actual long host anchor has exactly one control child");
                check(rejects([&] { clean_anchor(parent); }) == "no attempt residue inside persistent anchor",
                    "long host anchor observer must reject a real child");
                check(host_names(*owned_tmp, private_anchor) == expected && read(control) == "keep",
                    "failed emptiness predicate never removes the real control child");
                owned_tmp->mutate(SRPT_UNLINK, control);
                clean_anchor(parent);
                check(host_names(*owned_tmp, private_anchor).empty(), "long host anchor is empty only after explicit control removal");
                const auto control_parent = parent / "missing-observer-control";
                owned_tmp->mutate(SRPT_MKDIR, control_parent, 0700);
                check(rejects([&] { clean_anchor(control_parent); }).find("host fixture status=") == 0,
                    "long host anchor observation errors must propagate, never look empty");
                owned_tmp->mutate(SRPT_RMDIR, control_parent);
            }
            std::unique_ptr<WineLongFixtureCleanup> wine_cleanup;
            if (under_wine) wine_cleanup = std::make_unique<WineLongFixtureCleanup>(fixture.root);
#endif
            if (unwind) throw FixtureUnwind {};
#ifdef _WIN32
            if (under_wine) {
                wine_cleanup->remove();
                check(!host_names(*owned_tmp, windows_path(owned_tmp->base)).count(fixture.root.filename().string()),
                    "checked long host fixture removal completed before destructor");
            } else {
#endif
            check(fs::remove_all(fixture.cleanup_root) > 0, "checked recursive long fixture removal");
            check(!fs::exists(fixture.cleanup_root), "checked long fixture removal completed before destructor");
#ifdef _WIN32
            }
#endif
        } catch (const FixtureUnwind&) {
            // Only this deliberate fault is swallowed; real test failures escape.
        }
        bool remains;
#ifdef _WIN32
        if (under_wine) remains = host_names(*owned_tmp, windows_path(owned_tmp->base)).count(removed_root.filename().string()) != 0;
        else
#endif
        remains = fs::exists(removed_root);
        check(!remains, unwind ? "exceptional long fixture fallback removed all descendants"
                               : "normal long fixture removal left no descendants");
    }
}

void phase_failures_and_cleanup()
{
    Fixture fixture;
    const auto destination = fixture.root / "destination";
    write(destination, "old");
    const auto fault = [] { throw std::runtime_error("phase fault"); };
    for (int phase = 0; phase < 4; ++phase) {
        rp::Hooks hooks;
        if (phase == 0) hooks.before_write = fault;
        if (phase == 1) hooks.before_security = fault;
        if (phase == 2) hooks.before_commit = fault;
        if (phase == 3) hooks.before_cleanup = fault;
        if (phase < 3) {
            check(rejects([&] { rp::publish(destination, "new", hooks); }).find("phase fault") != std::string::npos,
                "original phase diagnostic");
            check(read(destination) == "old", "precommit failure preserves bytes");
        } else {
            const auto result = rp::publish(destination, "new", hooks);
            check(result.committed && result.cleanup_error && result.cleanup_error->find("phase fault") != std::string::npos,
                "postcommit fault is cleanup diagnostic, never rollback");
            check(read(destination) == "new", "committed bytes survive cleanup fault");
        }
        clean_anchor(fixture.root);
    }
    rp::Hooks both;
    both.before_write = fault;
    both.before_cleanup = [] { throw std::runtime_error("cleanup fault"); };
    const auto error = rejects([&] { rp::publish(destination, "bad", both); });
    check(error.find("phase fault") != std::string::npos && error.find("cleanup fault") != std::string::npos,
        "precommit and cleanup diagnostics retained together");
    clean_anchor(fixture.root);

    rp::Hooks unrelated;
    fs::path attempt;
    unrelated.before_cleanup = [&] {
        attempt = only_attempt(fixture.root);
        write(attempt / "record", "foreign"); // Original record has already committed.
        write(attempt / "unrelated", "keep");
    };
    const auto result = rp::publish(destination, "published", unrelated);
    check(result.committed && result.cleanup_error, "substituted cleanup names diagnosed");
    check(read(attempt / "record") == "foreign" && read(attempt / "unrelated") == "keep",
        "cleanup never removes foreign names or sweeps attempt");
    check(read(destination) == "published", "cleanup cannot modify published file");
    rejects([&] { rp::publish(fixture.root / "missing" / "record", "x"); });
    rejects([&] { rp::publish(anchor(fixture.root), "x"); });
}

void final_validation()
{
    for (const auto& phase : {0, 1, 2}) {
        Fixture fixture;
        const auto destination = fixture.root / "destination";
        write(destination, "old");
        rp::Hooks hooks;
        const auto corrupt = [&] { write(only_attempt(fixture.root) / "record", "bad"); };
        if (phase == 0) hooks.before_security = corrupt;
        if (phase == 1) hooks.before_commit = corrupt;
        if (phase == 2) hooks.before_commit = [&] { write(destination, "external"); };
        rejects([&] { rp::publish(destination, "new", hooks); });
        check(read(destination) == (phase == 2 ? "external" : "old"), "final bytes and destination snapshot revalidated after last hook");
        clean_anchor(fixture.root);
    }
    Fixture fixture;
    const auto appeared = fixture.root / "appeared";
    rp::Hooks hooks;
    hooks.before_commit = [&] { write(appeared, "external"); };
    rejects([&] { rp::publish(appeared, "new", hooks); });
    check(read(appeared) == "external", "new destination appearing before commit not overwritten");
    check(fs::create_directory(fixture.root / "directory"), "directory fixture");
    rejects([&] { rp::publish(fixture.root / "directory", "new"); });
}

void independent_attempts()
{
    Fixture fixture;
    rp::Hooks hooks;
    hooks.before_write = [&] {
        const auto first = only_attempt(fixture.root);
        const auto nested = rp::publish(fixture.root / "second", "second");
        check(nested.committed && !nested.cleanup_error, "overlapping independent attempt");
        check(only_attempt(fixture.root) == first, "second cleanup preserves first attempt");
        check(read(first / "record").empty(), "first attempt remains unwritten");
    };
    const auto first = rp::publish(fixture.root / "first", "first", hooks);
    check(first.committed && !first.cleanup_error, "anchor reuse ignores volatile directory metadata");
    clean_anchor(fixture.root);
    check(read(fixture.root / "first") == "first" && read(fixture.root / "second") == "second", "independent exact bytes");
}

void namespace_attacks()
{
    for (bool before_bytes : {true, false}) {
        Fixture fixture;
        const auto moved = fixture.root / "moved-anchor";
        rp::Hooks hooks;
        fs::path original_record;
        bool inspected = false;
        const auto substitute = [&] {
            const auto attempt_name = only_attempt(fixture.root).filename();
            fs::rename(anchor(fixture.root), moved);
            original_record = moved / attempt_name / "record";
            check(fs::create_directory(anchor(fixture.root)), "foreign substituted anchor");
            write(anchor(fixture.root) / "marker", "keep");
        };
        if (before_bytes) hooks.before_write = substitute;
        else hooks.before_commit = substitute;
        hooks.before_cleanup = [&] {
            check(read(original_record) == (before_bytes ? "" : "secret"),
                "namespace attack before writer cannot receive even partial private bytes");
            inspected = true;
        };
        rejects([&] { rp::publish(fixture.root / "destination", "secret", hooks); });
        check(inspected, "pre-cleanup privacy assertions must complete, not be mistaken for expected failure");
        check(read(anchor(fixture.root) / "marker") == "keep", "public anchor substitution never receives bytes or cleanup");
        check(fs::is_empty(moved), "owned attempts cleaned through original pinned anchor");
        check(!fs::exists(fixture.root / "destination"), "anchor substitution refuses before commit");
    }
    Fixture fixture;
    const auto parent = fixture.root / "parent";
    const auto moved = fixture.root / "moved-parent";
    check(fs::create_directory(parent), "parent fixture");
    rp::Hooks hooks;
    hooks.before_write = [&] {
        fs::rename(parent, moved);
        check(fs::create_directory(parent), "substituted public parent");
        write(parent / "marker", "keep");
    };
    const auto result = rp::publish(parent / "record", "secret", hooks);
    check(result.committed && !result.cleanup_error && read(moved / "record") == "secret", "write and commit use pinned parent after ancestor rename");
    check(read(parent / "marker") == "keep" && !fs::exists(parent / "record"), "no bytes or cleanup in substituted ancestry");
    clean_anchor(moved);
}

#ifndef _WIN32
template<typename Function>
void child_test(const char* description, Function action)
{
    const pid_t child = ::fork();
    check(child >= 0, "fork fixture");
    if (child == 0) {
        try { action(); ::_exit(0); }
        catch (const std::exception& error) { std::cerr << description << ": " << error.what() << '\n'; ::_exit(1); }
    }
    int status = 0;
    pid_t waited;
    do { waited = ::waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    check(waited == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, description);
}

void ordinary_layouts()
{
    for (const mode_t mask : {0022, 0002}) {
        child_test("ordinary umask/layout child", [=] {
            ::umask(mask); // Child only. Production never sets umask.
            Fixture fixture;
            const auto home = fixture.root / "home";
            const auto local = home / ".local";
            check(fs::create_directory(home) && fs::create_directory(local), "ordinary parents");
            chmod_checked(home, 0750);
            chmod_checked(local, 0775);
            check(rp::publish(local / "record", "first").committed, "ordinary writable parent supported");
            check(rp::publish(local / "record", "second").committed, "ordinary overwrite supported");
            check(mode(home) == 0750 && mode(local) == 0775, "caller parents untouched");
            check(mode(local / "record") == 0600 && mode(anchor(local)) == 0700, "private anchor and new file");
            write(fixture.root / "probe", "umask unchanged");
            check(mode(fixture.root / "probe") == (0666 & ~mask), "production preserves child process umask");
            basic_publication();
        });
    }
}

void owned_anchor_groups()
{
    const int count = ::getgroups(0, nullptr);
    check(count >= 0, "inspect supplementary groups for owned private anchor fixture");
    std::vector<gid_t> groups(static_cast<std::size_t>(count));
    check(::getgroups(count, groups.data()) == count, "read supplementary groups");
    groups.push_back(::getegid());
    for (const gid_t group : groups) {
        Fixture fixture;
        const auto destination = fixture.root / "record";
        check(rp::publish(destination, "first").committed, "initial private anchor");
        check(::chown(anchor(fixture.root).c_str(), static_cast<uid_t>(-1), group) == 0
            && ::chown(destination.c_str(), static_cast<uid_t>(-1), group) == 0, "owned supplementary-group fixtures");
        const auto result = rp::publish(destination, "second");
        struct stat actual_anchor {}, actual_file {};
        check(::stat(anchor(fixture.root).c_str(), &actual_anchor) == 0 && ::stat(destination.c_str(), &actual_file) == 0,
            "inspect supplementary-group publication");
        check(result.committed && !result.cleanup_error && actual_anchor.st_gid == group && actual_file.st_gid == group,
            "owner-only anchor reuse accepts nonprimary groups and replacement preserves destination group");
        check(mode(anchor(fixture.root)) == 0700, "anchor group does not grant effective access");
        clean_anchor(fixture.root);
    }
}

void posix_security()
{
    Fixture fixture;
    const auto destination = fixture.root / "destination";
    write(destination, "old");
    chmod_checked(destination, 0640);
    struct stat before {}, after {};
    check(::stat(destination.c_str(), &before) == 0, "stat original");
    check(rp::publish(destination, "new").committed, "restricted replacement");
    check(::stat(destination.c_str(), &after) == 0, "stat replacement");
    check(mode(destination) == 0640 && before.st_uid == after.st_uid && before.st_gid == after.st_gid, "exact uid/gid/mode preservation");
    chmod_checked(destination, 0400);
    check(rp::publish(destination, "readonly").committed && mode(destination) == 0400, "retained validation handle supports readonly policy");
    rp::Hooks changed;
    changed.before_commit = [&] { chmod_checked(destination, 0600); };
    rejects([&] { rp::publish(destination, "new", changed); });
    check(mode(destination) == 0600, "destination policy change preserved");
    chmod_checked(destination, 04600);
    rejects([&] { rp::publish(destination, "new"); });
    chmod_checked(destination, 0600);
    fs::create_hard_link(destination, fixture.root / "linked");
    rejects([&] { rp::publish(destination, "new"); });
    fs::remove(fixture.root / "linked");
    fs::create_symlink(destination, fixture.root / "symlink");
    rejects([&] { rp::publish(fixture.root / "symlink", "new"); });
    check(::mkfifo((fixture.root / "fifo").c_str(), 0600) == 0, "FIFO fixture");
    rejects([&] { rp::publish(fixture.root / "fifo", "new"); });
    fs::create_directory_symlink(fixture.root, fixture.root / "alias");
    check(rp::publish(fixture.root / "alias" / "alias-record", "alias").committed, "parent aliases resolve once to pinned identity");
    fs::remove(fixture.root / "alias");

    for (int kind = 0; kind < 4; ++kind) {
        Fixture malicious;
        const auto path = malicious.root / "record";
        fs::path staged;
        rp::Hooks hooks;
        hooks.before_commit = [&] {
            staged = only_attempt(malicious.root) / "record";
            if (kind == 0) chmod_checked(staged, 0666);
            if (kind == 1) fs::create_hard_link(staged, malicious.root / "link");
            if (kind == 2) { fs::rename(staged, staged.string() + ".saved"); write(staged, "foreign"); }
            if (kind == 3) { fs::rename(staged, staged.string() + ".saved"); fs::create_symlink(destination, staged); }
        };
        rejects([&] { rp::publish(path, "new", hooks); });
        check(!fs::exists(path), "unsafe final stage cannot commit");
        if (kind != 0) check(fs::exists(staged), "foreign/multilink entries left untouched");
    }
#ifdef __linux__
    check(::setxattr(destination.c_str(), "user.publication-test", "x", 1, 0) == 0, "real unsupported xattr fixture");
    rejects([&] { rp::publish(destination, "new"); });
    check(read(destination) == "readonly", "unsupported destination policy preserves bytes");
    rp::Hooks stage_policy;
    stage_policy.before_commit = [&] {
        const auto stage = only_attempt(fixture.root) / "record";
        check(::setxattr(stage.c_str(), "user.publication-test", "x", 1, 0) == 0, "stage xattr injection");
    };
    rejects([&] { rp::publish(fixture.root / "new-policy", "secret", stage_policy); });
    check(!fs::exists(fixture.root / "new-policy"), "unsupported staged policy never commits");
    clean_anchor(fixture.root);
    const auto parent = fixture.root / "metadata-parent";
    check(fs::create_directory(parent), "metadata parent fixture");
    check(::setxattr(parent.c_str(), "user.publication-test", "x", 1, 0) == 0, "parent xattr fixture");
    rejects([&] { rp::publish(parent / "record", "secret"); });
    check(!fs::exists(anchor(parent)), "unsupported target parent fails before creating namespace");
    check(::setxattr(anchor(fixture.root).c_str(), "user.publication-test", "x", 1, 0) == 0, "anchor xattr fixture");
    rejects([&] { rp::publish(fixture.root / "new-policy", "secret"); });
    check(!fs::exists(fixture.root / "new-policy") && fs::is_empty(anchor(fixture.root)), "unsupported existing anchor not taken over");
#endif
}

void unsafe_anchors()
{
    for (int kind = 0; kind < 4; ++kind) {
        Fixture fixture;
        const auto private_anchor = anchor(fixture.root);
        if (kind == 0) write(private_anchor, "foreign file");
        if (kind == 1) fs::create_directory_symlink(fixture.root, private_anchor);
        if (kind >= 2) { check(fs::create_directory(private_anchor), "unsafe directory fixture"); chmod_checked(private_anchor, kind == 2 ? 0770 : 0750); }
        rejects([&] { rp::publish(fixture.root / "destination", "secret"); });
        check(fs::exists(private_anchor), "unsafe anchor not taken over or deleted");
        if (kind >= 2) check(mode(private_anchor) == (kind == 2 ? 0770 : 0750), "unsafe anchor not chmodded");
        if (kind == 1) fs::remove(private_anchor);
    }
    Fixture fixture;
    fs::path attempt, moved;
    bool substituted = false;
    rp::Hooks hooks;
    hooks.before_write = [&] {
        attempt = only_attempt(fixture.root);
        moved = anchor(fixture.root) / "saved-attempt";
        fs::rename(attempt, moved);
        check(::mkdir(attempt.c_str(), 0700) == 0, "substituted attempt fixture");
        write(attempt / "foreign", "keep");
        substituted = true;
    };
    const auto error = rejects([&] { rp::publish(fixture.root / "record", "secret", hooks); });
    check(substituted && error.find("cleanup") != std::string::npos, "attempt identity change has original and cleanup diagnostics");
    check(read(attempt / "foreign") == "keep" && fs::is_empty(moved), "substituted attempt untouched, pinned original contents cleaned");
}

void real_writer_failure()
{
    child_test("bounded native writer OS failure", [] {
        Fixture fixture;
        const auto path = fixture.root / "record";
        write(path, "old");
        check(::signal(SIGXFSZ, SIG_IGN) != SIG_ERR, "ignore size-limit signal only in child");
        struct rlimit limit {};
        check(::getrlimit(RLIMIT_FSIZE, &limit) == 0, "get file size limit");
        limit.rlim_cur = 4096;
        check(::setrlimit(RLIMIT_FSIZE, &limit) == 0, "set bounded child-only file limit");
        const auto error = rejects([&] { rp::publish(path, std::string(131072, 'x')); });
        check(error.find("write private record") != std::string::npos, "real partial write then EFBIG must surface writer completion failure");
        check(read(path) == "old", "incomplete native write never replaces destination");
        clean_anchor(fixture.root);
    });
}
#else
struct WindowsHandle {
    HANDLE value = INVALID_HANDLE_VALUE;
    ~WindowsHandle() { if (value != INVALID_HANDLE_VALUE && value != nullptr) ::CloseHandle(value); }
    WindowsHandle() = default;
    WindowsHandle(const WindowsHandle&) = delete;
    WindowsHandle& operator=(const WindowsHandle&) = delete;
};

struct Impersonation {
    explicit Impersonation(HANDLE token) { check(::ImpersonateLoggedOnUser(token), "restricted impersonation fixture"); }
    ~Impersonation() { if (!::RevertToSelf()) std::abort(); }
};

unsigned long long diagnostic_id(const std::string& diagnostic, const char* name)
{
    const std::string field = std::string(" ") + name + "=";
    const auto offset = diagnostic.find(field);
    check(offset != std::string::npos, std::string("refusal includes ") + name);
    const auto start = offset + field.size();
    const auto end = diagnostic.find_first_not_of("0123456789", start);
    check(end != start && (end == std::string::npos || diagnostic[end] == ' '),
        std::string(name) + " is a complete numeric token");
    const auto value = std::stoull(diagnostic.substr(start, end - start));
    check(value > 0, std::string(name) + " is positive");
    return value;
}

void creation_diagnostic(const std::string& diagnostic, const fs::path& root,
                         const char* phase, bool collision, bool initial)
{
    check(diagnostic.find("; cleanup: ") == std::string::npos, "validate one refusal segment at a time");
    diagnostic_id(diagnostic, "attempt-id");
    diagnostic_id(diagnostic, "acquisition-id");
    for (const auto* field : {"acquisition-phase=initial-prepare",
            "native-complete=true", "initial-private=", " input{sd-present=", "dacl-valid=",
            "dacl-match=", "dacl-bytes=", "ace-count="}) {
        check(diagnostic.find(field) != std::string::npos, std::string("creation diagnostic includes ") + field);
    }
    check(diagnostic.find(std::string(" phase=") + phase + " ") != std::string::npos,
        "refusal phase is distinct from acquisition phase");
    check(diagnostic.find(initial ? "initial-private=refused" : "initial-private=accepted") != std::string::npos,
        "initial same-handle private check is distinguished from a later refusal");
    if (!initial) {
        check(diagnostic.find("actual-protected=false") != std::string::npos,
            "later refusal still rejects the injected unprotected policy");
    }
    const std::string protected_input = "{sd-present=true sd-valid=true owner-match=true protected=true "
        "dacl-present=true dacl-valid=true dacl-match=true dacl-bytes=";
    const auto expected_offset = diagnostic.find("expected-dacl-bytes=");
    check(expected_offset != std::string::npos, "returned policy retains expected DACL size");
    const auto expected_start = expected_offset + std::strlen("expected-dacl-bytes=");
    const auto expected_bytes = diagnostic.substr(expected_start, diagnostic.find(' ', expected_start) - expected_start);
    const auto matching_input = protected_input + expected_bytes + " ace-count=1}";
    if (collision) {
        check(diagnostic.find("acquisition=collision-reopen native-complete=true file-created=false") != std::string::npos,
            "collision/reopen is not described as newly created");
        check(diagnostic.find("collision-id=") != std::string::npos
            && diagnostic.find("collision-input" + matching_input) != std::string::npos,
            "collision retains the actual failed exclusive-create descriptor input");
        check(diagnostic.find("input{sd-present=false sd-valid=false") != std::string::npos,
            "successful reopen reports its own absent descriptor, not the create request");
    } else {
        check(diagnostic.find("acquisition=exclusive-create native-complete=true file-created=true") != std::string::npos,
            "exclusive-create classification uses checked FILE_CREATED completion");
        check(diagnostic.find("input" + matching_input) != std::string::npos,
            "actual successful native creation input is valid, matching and protected");
        check(diagnostic.find("collision-input") == std::string::npos, "fresh acquisition has no collision input");
    }
    check(diagnostic.size() < 1536, "individual refusal fits the structured message field budget");
    check(diagnostic.find(root.string()) == std::string::npos && diagnostic.find("S-1-") == std::string::npos
        && diagnostic.find("PRIVATE_PAYLOAD_SENTINEL") == std::string::npos,
        "creation diagnostics never expose paths, SIDs or payload");
}

void unprotect(const fs::path& path)
{
    const auto policy = windows_policy(path);
    check(::SetNamedSecurityInfoW(const_cast<wchar_t*>(path.c_str()), SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION | UNPROTECTED_DACL_SECURITY_INFORMATION, nullptr, nullptr,
        reinterpret_cast<PACL>(const_cast<unsigned char*>(policy.dacl.data())), nullptr) == ERROR_SUCCESS,
        "test-owned private policy mutation");
}

void windows_creation_boundary_diagnostics()
{
    unsigned long long previous = 0;
    for (bool reused : {false, true}) {
        for (int phase = 0; phase < 4; ++phase) {
            Fixture fixture;
            if (reused) check(rp::publish(fixture.root / "seed", "seed").committed, "seed reusable anchor");
            rp::Hooks hooks;
            const auto mutate = [&] { unprotect(anchor(fixture.root)); };
            if (phase == 0) hooks.before_write = mutate;
            if (phase == 1) hooks.before_security = mutate;
            if (phase == 2) hooks.before_commit = mutate;
            if (phase == 3) hooks.before_cleanup = mutate;
            std::string diagnostic;
            if (phase == 3) {
                const auto result = rp::publish(fixture.root / "record", "PRIVATE_PAYLOAD_SENTINEL", hooks);
                check(result.committed && result.cleanup_error, "cleanup refusal never rolls back committed publication");
                diagnostic = *result.cleanup_error;
                creation_diagnostic(diagnostic, fixture.root, "cleanup", reused, false);
            } else {
                diagnostic = rejects([&] { rp::publish(fixture.root / "record", "PRIVATE_PAYLOAD_SENTINEL", hooks); });
                check(!fs::exists(fixture.root / "record"), "later unsafe policy is still rejected before commit");
                const auto separator = diagnostic.find("; cleanup: ");
                check(separator != std::string::npos, "unsafe anchor must cause both primary and cleanup refusals");
                const auto primary = diagnostic.substr(0, separator);
                const auto cleanup = diagnostic.substr(separator + std::strlen("; cleanup: "));
                creation_diagnostic(primary, fixture.root,
                    phase == 0 ? "write-validation" : phase == 1 ? "security-validation" : "commit-validation", reused, false);
                creation_diagnostic(cleanup, fixture.root, "cleanup", reused, false);
                check(diagnostic_id(primary, "attempt-id") == diagnostic_id(cleanup, "attempt-id"),
                    "failure and cleanup refer to the same attempt");
                check(diagnostic_id(primary, "acquisition-id") == diagnostic_id(cleanup, "acquisition-id"),
                    "cleanup retains the same original handle acquisition, not its fresh name-check handle");
            }
            check(diagnostic.size() < 2048, "complete native failure including cleanup stays below 2048 bytes");
            const auto id = diagnostic_id(diagnostic, "attempt-id");
            check(id > previous, "attempt identifiers are monotonic, not reused across publications");
            previous = id;
        }
    }

    Fixture outer, inner;
    std::string nested_error;
    rp::Hooks hooks;
    hooks.before_write = [&] {
        rp::Hooks nested;
        nested.before_write = [&] { unprotect(only_attempt(inner.root)); };
        nested_error = rejects([&] { rp::publish(inner.root / "record", "PRIVATE_PAYLOAD_SENTINEL", nested); });
        unprotect(anchor(outer.root));
    };
    const auto error = rejects([&] { rp::publish(outer.root / "record", "PRIVATE_PAYLOAD_SENTINEL", hooks); });
    const auto outer_cleanup = error.find("; cleanup: ");
    const auto inner_cleanup = nested_error.find("; cleanup: ");
    check(outer_cleanup != std::string::npos && inner_cleanup != std::string::npos,
        "both overlapping unsafe-policy attempts must report cleanup refusal");
    creation_diagnostic(error.substr(0, outer_cleanup), outer.root, "write-validation", false, false);
    creation_diagnostic(error.substr(outer_cleanup + std::strlen("; cleanup: ")), outer.root, "cleanup", false, false);
    creation_diagnostic(nested_error.substr(0, inner_cleanup), inner.root, "write-validation", false, false);
    creation_diagnostic(nested_error.substr(inner_cleanup + std::strlen("; cleanup: ")), inner.root, "cleanup", false, false);
    check(error.size() < 2048 && nested_error.size() < 2048, "complete overlapping native failures stay below 2048 bytes");
    check(error.find("role=anchor") != std::string::npos && nested_error.find("role=attempt") != std::string::npos,
        "overlapping attempts retain their own failing handle role");
    check(diagnostic_id(error, "attempt-id") < diagnostic_id(nested_error, "attempt-id"),
        "nested attempt cannot overwrite outer correlation");

    Fixture record;
    rp::Hooks record_hooks;
    record_hooks.before_security = [&] { unprotect(only_attempt(record.root) / "record"); };
    const auto record_error = rejects([&] { rp::publish(record.root / "destination", "PRIVATE_PAYLOAD_SENTINEL", record_hooks); });
    creation_diagnostic(record_error, record.root, "security-validation", false, false);
    check(record_error.find("role=record") != std::string::npos && !fs::exists(record.root / "destination"),
        "private record rejection retains its own acquisition and prevents commit");
}

void windows_foreign_parent_and_private_children()
{
    Fixture fixture;
    const auto policy = windows_policy(fixture.root);
    alignas(DWORD) std::array<unsigned char, SECURITY_MAX_SID_SIZE> everyone {};
    DWORD size = everyone.size();
    check(::CreateWellKnownSid(WinWorldSid, nullptr, everyone.data(), &size), "foreign parent Everyone SID");
    std::vector<unsigned char> bytes(sizeof(ACL) + 2 * (sizeof(ACCESS_ALLOWED_ACE) - sizeof(DWORD)) + size + policy.owner.size());
    auto* dacl = reinterpret_cast<PACL>(bytes.data());
    check(::InitializeAcl(dacl, bytes.size(), ACL_REVISION)
        && ::AddAccessAllowedAce(dacl, ACL_REVISION, FILE_ALL_ACCESS, const_cast<unsigned char*>(policy.owner.data()))
        && ::AddAccessAllowedAce(dacl, ACL_REVISION, FILE_ALL_ACCESS, everyone.data()), "foreign mutable parent DACL fixture");
    check(::SetNamedSecurityInfoW(const_cast<wchar_t*>(fixture.root.c_str()), SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, nullptr, nullptr, dacl, nullptr) == ERROR_SUCCESS,
        "install foreign mutable test-owned parent policy");
    const auto original_parent = windows_policy(fixture.root);
    WindowsHandle process, restricted;
    check(::OpenProcessToken(::GetCurrentProcess(), TOKEN_QUERY | TOKEN_DUPLICATE, &process.value), "open token fixture");
    SID_AND_ATTRIBUTES limiting {everyone.data(), 0};
    check(::CreateRestrictedToken(process.value, DISABLE_MAX_PRIVILEGE, 0, nullptr, 0, nullptr, 1, &limiting, &restricted.value),
        "World-limited access-check fixture token");
    for (bool before_bytes : {true, false}) {
        rp::Hooks hooks;
        bool inspected = false;
        const auto inspect = [&] {
            const auto stage = only_attempt(fixture.root) / "record";
            private_object(stage, false);
            {
                Impersonation impersonation(restricted.value);
                WindowsHandle parent;
                parent.value = ::CreateFileW(fixture.root.c_str(), GENERIC_WRITE,
                    FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING,
                    FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
                check(parent.value != INVALID_HANDLE_VALUE, "foreign mutable parent positive control must actually open");
                WindowsHandle file;
                file.value = ::CreateFileW(stage.c_str(), GENERIC_READ,
                    FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING,
                    FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
                const DWORD error = ::GetLastError();
                check(file.value == INVALID_HANDLE_VALUE && error == ERROR_ACCESS_DENIED,
                    "foreign principal cannot read native file before or after payload bytes");
            }
            inspected = true;
        };
        if (before_bytes) hooks.before_write = inspect;
        else hooks.before_security = inspect;
        const auto result = rp::publish(fixture.root / "record", "secret", hooks);
        check(inspected && result.committed && !result.cleanup_error, "foreign writable parent is supported without byte disclosure");
        clean_anchor(fixture.root);
    }
    check(windows_policy(fixture.root).dacl == original_parent.dacl, "caller parent DACL is never repaired or replaced");
    // An unsafe preexisting anchor is never adopted, chmodded, or taken over.
    const auto unsafe = fixture.root / "unsafe";
    check(fs::create_directory(unsafe) && fs::create_directory(anchor(unsafe)), "unsafe anchor fixture");
    check(::SetNamedSecurityInfoW(const_cast<wchar_t*>(anchor(unsafe).c_str()), SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, nullptr, nullptr, dacl, nullptr) == ERROR_SUCCESS,
        "explicit foreign-readable/writable preexisting anchor fixture");
    const auto before = windows_policy(anchor(unsafe));
    const auto diagnostic = rejects([&] { rp::publish(unsafe / "record", "secret"); });
    creation_diagnostic(diagnostic, fixture.root, "initial-prepare", true, true);
    for (const auto* metric : {"role=anchor", "owner-match=", "expected-protected=true", "actual-protected=true",
            "dacl-match=false", "expected-dacl-bytes=", "actual-dacl-bytes=", "expected-ace-count=1", "actual-ace-count=2"}) {
        check(diagnostic.find(metric) != std::string::npos, std::string("private-policy refusal must include safe metric: ") + metric);
    }
    check(diagnostic.find("S-1-") == std::string::npos && diagnostic.find("secret") == std::string::npos,
        "diagnostic must not print SID or payload");
    check(windows_policy(anchor(unsafe)).dacl == before.dacl && !fs::exists(unsafe / "record"), "unsafe existing anchor policy untouched");
}

void windows_junction_anchor_attack()
{
    Fixture fixture;
    const auto foreign = fixture.root / "foreign";
    const auto moved = fixture.root / "original-anchor";
    check(fs::create_directory(foreign), "foreign junction target fixture");
    write(foreign / "marker", "keep");
    // Documented IO_REPARSE_TAG_MOUNT_POINT layout, two byte-counted UTF-16
    // names and terminating NULs. No SDK-private structure or shell utility.
    struct JunctionHeader { DWORD tag; WORD length, reserved, substitute_offset, substitute_length, print_offset, print_length; };
    static_assert(sizeof(JunctionHeader) == 16);
    auto target = fs::absolute(foreign);
    target.make_preferred();
    const auto print = target.native();
    const std::wstring substitute = L"\\??\\" + print;
    const auto substitute_bytes = substitute.size() * sizeof(wchar_t);
    const auto print_bytes = print.size() * sizeof(wchar_t);
    const auto names_bytes = substitute_bytes + print_bytes + 2 * sizeof(wchar_t);
    check(sizeof(JunctionHeader) + names_bytes <= 16384, "bounded junction fixture");
    const JunctionHeader header {IO_REPARSE_TAG_MOUNT_POINT, static_cast<WORD>(8 + names_bytes), 0,
        0, static_cast<WORD>(substitute_bytes), static_cast<WORD>(substitute_bytes + sizeof(wchar_t)), static_cast<WORD>(print_bytes)};
    std::vector<unsigned char> payload(sizeof(header) + names_bytes, 0);
    std::memcpy(payload.data(), &header, sizeof(header));
    std::memcpy(payload.data() + sizeof(header), substitute.c_str(), substitute_bytes);
    std::memcpy(payload.data() + sizeof(header) + substitute_bytes + sizeof(wchar_t), print.c_str(), print_bytes);
    bool installed = false, inspected = false;
    fs::path original_record;
    rp::Hooks hooks;
    hooks.before_write = [&] {
        const auto attempt = only_attempt(fixture.root).filename();
        fs::rename(anchor(fixture.root), moved);
        original_record = moved / attempt / "record";
        check(fs::create_directory(anchor(fixture.root)), "empty public junction replacement");
        WindowsHandle writer;
        writer.value = ::CreateFileW(anchor(fixture.root).c_str(), GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        check(writer.value != INVALID_HANDLE_VALUE, "open junction fixture writer");
        DWORD returned = 0;
        check(::DeviceIoControl(writer.value, FSCTL_SET_REPARSE_POINT, payload.data(), static_cast<DWORD>(payload.size()),
            nullptr, 0, &returned, nullptr), "actual public anchor junction installation must succeed");
        installed = true;
        check(read(anchor(fixture.root) / "marker") == "keep", "junction positive control really redirects path lookup");
    };
    hooks.before_cleanup = [&] {
        check(read(original_record).empty(), "junction attack before writer never receives bytes");
        inspected = true;
    };
    const auto error = rejects([&] { rp::publish(fixture.root / "record", "secret", hooks); });
    check(installed && inspected && error.find("unsupported reparse") != std::string::npos, "Native anchor reparse rejection executes before writer");
    check(read(foreign / "marker") == "keep" && fs::is_empty(moved), "foreign junction target untouched, original owned attempt cleaned");
    check(::RemoveDirectoryW(anchor(fixture.root).c_str()), "remove test-owned junction without following target");
}

void windows_security()
{
    Fixture fixture;
    const auto destination = fixture.root / "record";
    write(destination, "old");
    auto original = windows_policy(destination);
    alignas(DWORD) std::array<unsigned char, SECURITY_MAX_SID_SIZE> everyone {};
    DWORD size = everyone.size();
    check(::CreateWellKnownSid(WinWorldSid, nullptr, everyone.data(), &size), "Everyone fixture SID");
    std::vector<unsigned char> acl(sizeof(ACL) + 2 * (sizeof(ACCESS_ALLOWED_ACE) - sizeof(DWORD)) + size + original.owner.size());
    auto* dacl = reinterpret_cast<PACL>(acl.data());
    check(::InitializeAcl(dacl, acl.size(), ACL_REVISION)
        && ::AddAccessDeniedAce(dacl, ACL_REVISION, FILE_WRITE_DATA, everyone.data())
        && ::AddAccessAllowedAce(dacl, ACL_REVISION, FILE_ALL_ACCESS, original.owner.data()), "ordered allow/deny fixture");
    check(::SetNamedSecurityInfoW(const_cast<wchar_t*>(destination.c_str()), SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, nullptr, nullptr, dacl, nullptr) == ERROR_SUCCESS,
        "install ordinary destination restriction");
    original = windows_policy(destination);
    const auto result = rp::publish(destination, "new");
    check(result.committed && !result.cleanup_error && read(destination) == "new", "Native overwrite succeeds with inspection delete sharing");
    const auto replacement = windows_policy(destination);
    check(original.owner == replacement.owner && original.group == replacement.group && original.dacl == replacement.dacl,
        "exact owner/group/ordered DACL reproduction");
    const auto parent_policy = windows_policy(fixture.root);
    bool changed = false;
    rp::Hooks changed_policy;
    changed_policy.before_commit = [&] {
        check(::SetNamedSecurityInfoW(const_cast<wchar_t*>(destination.c_str()), SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, nullptr, nullptr,
            reinterpret_cast<PACL>(const_cast<unsigned char*>(parent_policy.dacl.data())), nullptr) == ERROR_SUCCESS,
            "inject destination policy change");
        changed = true;
    };
    rejects([&] { rp::publish(destination, "blocked", changed_policy); });
    check(changed && read(destination) == "new", "final destination DACL change preserves original bytes");
    check(::SetNamedSecurityInfoW(const_cast<wchar_t*>(destination.c_str()), SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, nullptr, nullptr, dacl, nullptr) == ERROR_SUCCESS,
        "restore test-owned destination policy");
    changed = false;
    changed_policy.before_commit = [&] {
        const auto stage = only_attempt(fixture.root) / "record";
        check(::SetNamedSecurityInfoW(const_cast<wchar_t*>(stage.c_str()), SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, nullptr, nullptr,
            reinterpret_cast<PACL>(const_cast<unsigned char*>(parent_policy.dacl.data())), nullptr) == ERROR_SUCCESS,
            "inject native stage DACL change");
        changed = true;
    };
    rejects([&] { rp::publish(destination, "blocked", changed_policy); });
    check(changed && read(destination) == "new", "final native file DACL change rejected after hook");
    clean_anchor(fixture.root);
    const HANDLE blocker = ::CreateFileW(destination.c_str(), FILE_READ_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    check(blocker != INVALID_HANDLE_VALUE, "open external missing-SHARE_DELETE fixture");
    const auto failure = rejects([&] { rp::publish(destination, "blocked"); });
    check(::CloseHandle(blocker), "close external sharing blocker");
    check(failure.find("atomic NtSetInformationFile rename") != std::string::npos && read(destination) == "new",
        "Native sharing failure is not latched as commit");
    clean_anchor(fixture.root);
    check(::SetFileAttributesW(destination.c_str(), FILE_ATTRIBUTE_READONLY), "readonly destination fixture");
    rejects([&] { rp::publish(destination, "blocked"); });
    check(read(destination) == "new", "readonly replacement failure preserves destination");
    check(::SetFileAttributesW(destination.c_str(), FILE_ATTRIBUTE_NORMAL), "restore readonly fixture");
    check(::CreateHardLinkW((fixture.root / "link").c_str(), destination.c_str(), nullptr), "hardlink fixture");
    rejects([&] { rp::publish(destination, "blocked"); });
    fs::remove(fixture.root / "link");
    PSECURITY_DESCRIPTOR label = nullptr;
    check(::ConvertStringSecurityDescriptorToSecurityDescriptorW(L"S:(ML;;NW;;;LW)", SDDL_REVISION_1, &label, nullptr), "label fixture");
    BOOL present = FALSE, defaulted = FALSE;
    PACL sacl = nullptr;
    check(::GetSecurityDescriptorSacl(label, &present, &sacl, &defaulted) && present, "inspect label fixture");
    const auto status = ::SetNamedSecurityInfoW(const_cast<wchar_t*>(destination.c_str()), SE_FILE_OBJECT,
        LABEL_SECURITY_INFORMATION, nullptr, nullptr, nullptr, sacl);
    ::LocalFree(label);
    check(status == ERROR_SUCCESS, "install explicit low label fixture");
    rejects([&] { rp::publish(destination, "blocked"); });
    check(read(destination) == "new", "unsupported label remains explicit refusal");
}
#endif

#ifdef _WIN32
struct WineSymlinkFixture {
    Fixture& owner;
    fs::path link, target;
    bool live = false;
    explicit WineSymlinkFixture(Fixture& fixture) : owner(fixture) {}
    WineSymlinkFixture(const WineSymlinkFixture&) = delete;
    WineSymlinkFixture& operator=(const WineSymlinkFixture&) = delete;

    void create(const fs::path& path, const char* other)
    {
        check(link.empty(), "one exclusive symlink per fixture finalizer");
        link = path;
        target = link.parent_path() / other;
        auto frame = owned_tmp->request(SRPT_SYMLINK, owned_tmp->relative(link));
        const auto length = std::strlen(other);
        check(length < sizeof(frame.other), "bounded fixed symlink target");
        std::memcpy(frame.other, other, length + 1);
        const auto status = support_entry(SRPT_ENTRY_FIXTURE, &frame);
        if (status == SRPT_SUCCESS) live = true; // Before diagnostic allocation or any other throwing work.
        check(status == SRPT_SUCCESS, "host fixture status=" + std::to_string(status) + " errno=" + std::to_string(frame.os_error));
    }

    static void diagnostic(const char* label, const std::exception_ptr& error)
    {
        std::cerr << label;
        try {
            if (error) std::rethrow_exception(error);
            std::cerr << "none";
        } catch (const std::exception& failure) { std::cerr << failure.what(); }
        catch (...) { std::cerr << "unknown exception"; }
        std::cerr << '\n' << std::flush;
    }

    template<class Tail>
    void finish(const std::exception_ptr& primary, Tail&& after_unlink, bool refuse_unlink = false)
    {
        std::exception_ptr cleanup_failure;
        try {
            if (live) {
                check((owned_tmp->observe(link).mode & 0170000) == 0120000, "owned cleanup entry remains a symlink");
                auto frame = owned_tmp->request(SRPT_UNLINK, owned_tmp->relative(link));
                if (refuse_unlink) frame.root = 0; // Fixed regression probes only: actual support refuses before mutation.
                const auto status = support_entry(SRPT_ENTRY_FIXTURE, &frame);
                if (status == SRPT_SUCCESS) live = false;
                check(status == SRPT_SUCCESS, "host fixture status=" + std::to_string(status) + " errno=" + std::to_string(frame.os_error));
                check(!host_names(*owned_tmp, link.parent_path()).count(link.filename().string())
                    && (owned_tmp->observe(target).mode & 0170000) == 0100000,
                    "link-only cleanup leaves its regular target intact");
                after_unlink(!primary);
            }
        } catch (...) {
            owner.preserve_wine_fixture = true; // No recursive fallback, even if later diagnostics fail.
            cleanup_failure = std::current_exception();
        }
        if (cleanup_failure) {
            diagnostic("primary: ", primary);
            diagnostic("cleanup: ", cleanup_failure);
            std::cerr << "Wine symlink fixture retained; recursive cleanup disabled\n" << std::flush;
        }
        if (primary) std::rethrow_exception(primary); // Outside cleanup catch: never replace the primary.
        if (cleanup_failure) std::rethrow_exception(cleanup_failure);
    }
};

bool same_host_object(const SrptCall& left, const SrptCall& right)
{
    return left.device == right.device && left.inode == right.inode && left.uid == right.uid
        && left.gid == right.gid && left.mode == right.mode && left.links == right.links
        && left.file_size == right.file_size;
}

struct WineCleanupDiagnostics {
    std::stringstream output;
    std::streambuf* previous = std::cerr.rdbuf(output.rdbuf());
    ~WineCleanupDiagnostics() noexcept { std::cerr.rdbuf(previous); }
};

void wine_symlink_cleanup_regressions()
{
    const std::string primary_message = "symlink fixture primary probe";
    const auto cleanup_message = "host fixture status=" + std::to_string(SRPT_INVALID_ARGUMENT) + " errno=0";
    for (int probe = 0; probe < 3; ++probe) {
        const bool primary_fault = probe != 1, cleanup_fault = probe != 0;
        fs::path root;
        SrptCall original_link {}, original_target {};
        std::string diagnostics;
        {
            WineCleanupDiagnostics capture;
            try {
                {
                    Fixture fixture;
                    root = fixture.root;
                    WineSymlinkFixture link(fixture);
                    std::exception_ptr primary, observed;
                    try {
                        owned_tmp->mutate(SRPT_CREATE, root / "record", 0600, "old");
                        link.create(root / "symlink", "record");
                        original_link = owned_tmp->observe(root / "symlink");
                        original_target = owned_tmp->observe(root / "record");
                        check((original_link.mode & 0170000) == 0120000
                            && (original_target.mode & 0170000) == 0100000 && read(root / "record") == "old",
                            "real symlink probe fixture before finalization");
                        if (primary_fault) throw std::runtime_error(primary_message);
                    } catch (...) { primary = std::current_exception(); }
                    try {
                        link.finish(primary, [&](bool) {
                            check(host_names(*owned_tmp, root) == std::set<std::string>{"record"}
                                && same_host_object(original_target, owned_tmp->observe(root / "record"))
                                && read(root / "record") == "old", "primary cleanup unlinks only the symlink");
                        }, cleanup_fault);
                    } catch (...) { observed = std::current_exception(); }
                    check(static_cast<bool>(observed), "symlink probe must propagate its expected failure");
                    const auto message = rejects([&] { std::rethrow_exception(observed); });
                    if (message != (primary_fault ? primary_message : cleanup_message)) std::rethrow_exception(observed);
                    if (primary_fault) check(observed == primary, "original primary exception identity retained");
                    check(fixture.preserve_wine_fixture == cleanup_fault, "only failed finalization retains fixture");
                    if (cleanup_fault) {
                        check(host_names(*owned_tmp, root) == std::set<std::string>{"record", "symlink"}
                            && same_host_object(original_link, owned_tmp->observe(root / "symlink"))
                            && same_host_object(original_target, owned_tmp->observe(root / "record"))
                            && read(root / "record") == "old", "failed unlink leaves both owned names unchanged");
                    }
                } // The real Fixture destructor must return, including retention paths.
                diagnostics = capture.output.str();
            } catch (...) {
                std::cerr.rdbuf(capture.previous);
                auto* buffer = capture.output.rdbuf();
                if (buffer->sgetc() != std::char_traits<char>::eof()) std::cerr << buffer;
                std::cerr << std::flush;
                throw;
            }
        }
        if (cleanup_fault) {
            check(diagnostics == "primary: " + (primary_fault ? primary_message : "none")
                + "\ncleanup: " + cleanup_message
                + "\nWine symlink fixture retained; recursive cleanup disabled\n",
                "unexpected symlink probe diagnostics: " + diagnostics);
            check(host_names(*owned_tmp, root) == std::set<std::string>{"record", "symlink"}
                && same_host_object(original_link, owned_tmp->observe(root / "symlink"))
                && same_host_object(original_target, owned_tmp->observe(root / "record"))
                && read(root / "record") == "old", "fixture retained intact across owner destruction");
            owned_tmp->mutate(SRPT_UNLINK, root / "symlink");
            check(host_names(*owned_tmp, root) == std::set<std::string>{"record"}
                && read(root / "record") == "old", "retention probe recovery removes link before target");
            owned_tmp->mutate(SRPT_UNLINK, root / "record");
            check(host_names(*owned_tmp, root).empty(), "only known probe names removed");
            owned_tmp->mutate(SRPT_RMDIR, root);
        } else {
            check(diagnostics.find("retained") == std::string::npos, "successful cleanup never retains fixture");
        }
        check(!host_names(*owned_tmp, windows_path(owned_tmp->base)).count(root.filename().string()),
            "probe fixture absent after normal destruction or checked recovery");
    }
}

void wine_host_policy()
{
    {
        Fixture layout;
        const auto home = layout.root / "home";
        const auto local = home / "local";
        owned_tmp->mutate(SRPT_MKDIR, home, 0700);
        owned_tmp->mutate(SRPT_MKDIR, local, 0700);
        owned_tmp->mutate(SRPT_CHMOD, home, 0750);
        owned_tmp->mutate(SRPT_CHMOD, local, 0775);
        check(rp::publish(local / "record", "first").committed
            && rp::publish(local / "record", "second").committed, "ordinary writable Wine host layout");
        check((owned_tmp->observe(home).mode & 07777) == 0750
            && (owned_tmp->observe(local).mode & 07777) == 0775, "ordinary host parents unchanged");
        host_private(anchor(local), true);
        host_private(local / "record", false);
        clean_anchor(local);
    }
    for (const uint32_t mode : {0750u, 0770u}) {
        Fixture fixture;
        const auto path = anchor(fixture.root);
        owned_tmp->mutate(SRPT_MKDIR, path, 0700);
        const auto descriptor = windows_policy(path);
        owned_tmp->mutate(SRPT_CHMOD, path, mode);
        const auto before = owned_tmp->observe(path);
        // Wine's synthesized descriptors may be indistinguishable from0700.
        // The actual host mode, not DACL appearance, is the privacy authority.
        check(windows_policy(path).dacl == descriptor.dacl, "Wine9 descriptor ambiguity positive control");
        rejects([&] { rp::publish(fixture.root / "record", "secret"); });
        check(same_host_object(before, owned_tmp->observe(path)) && fs::is_empty(path)
            && !fs::exists(fixture.root / "record"), "unsafe host0750/0770 anchor rejected unchanged");
    }
    Fixture fixture;
    const auto destination = fixture.root / "record";
    owned_tmp->mutate(SRPT_CREATE, destination, 0600, "old");
    for (const uint32_t mode : {0640u, 0400u, 0600u}) {
        owned_tmp->mutate(SRPT_CHMOD, destination, mode);
        auto group = owned_tmp->request(SRPT_SET_GID, owned_tmp->relative(destination));
        group.gid = owned_tmp->observe(destination).gid; // Real supported host GID, never a fake UID.
        HostRoot::invoke(group);
        const auto before = owned_tmp->observe(destination);
        const auto result = rp::publish(destination, "new");
        const auto after = owned_tmp->observe(destination);
        check(result.committed && !result.cleanup_error && read(destination) == "new"
            && before.uid == after.uid && before.gid == after.gid && before.mode == after.mode,
            "supported actual destination UID/GID/mode preserved");
        clean_anchor(fixture.root);
    }
    owned_tmp->mutate(SRPT_LINK, destination, 0, "", fixture.root / "link");
    const auto linked = owned_tmp->observe(destination);
    rejects([&] { rp::publish(destination, "blocked"); });
    check(same_host_object(linked, owned_tmp->observe(destination)) && read(destination) == "new", "multilink refusal unchanged");
    owned_tmp->mutate(SRPT_UNLINK, fixture.root / "link");
    {
        WineSymlinkFixture symlink(fixture);
        std::exception_ptr primary;
        try {
            symlink.create(fixture.root / "symlink", "record");
            rejects([&] { rp::publish(fixture.root / "symlink", "blocked"); });
            check((owned_tmp->observe(fixture.root / "symlink").mode & 0170000) == 0120000
                && read(destination) == "new", "host symlink refused without following or deleting");
        } catch (...) { primary = std::current_exception(); }
        symlink.finish(primary, [&](bool) {
            check(host_names(*owned_tmp, fixture.root) == std::set<std::string>{".space-publication", "record"}
                && read(destination) == "new", "outer link-only teardown preserves destination bytes");
        });
    }

    for (int kind = 0; kind < 5; ++kind) {
        Fixture malicious;
        WineSymlinkFixture symlink(malicious);
        const auto path = malicious.root / "record";
        bool mutated = false;
        fs::path staged;
        rp::Hooks hooks;
        std::exception_ptr primary;
        try {
            hooks.before_commit = [&] {
                staged = only_attempt(malicious.root) / "record";
                if (kind == 0) owned_tmp->mutate(SRPT_CHMOD, staged, 0666);
                if (kind == 1) owned_tmp->mutate(SRPT_LINK, staged, 0, "", malicious.root / "link");
                if (kind == 2 || kind == 3) {
                    owned_tmp->mutate(SRPT_RENAME, staged, 0, "", staged.parent_path() / "saved");
                    if (kind == 2) owned_tmp->mutate(SRPT_CREATE, staged, 0600, "foreign");
                    else symlink.create(staged, "saved");
                }
                if (kind == 4) owned_tmp->mutate(SRPT_XATTR, staged, 0, "unsupported");
                mutated = true;
            };
            if (kind == 3) std::cerr << "record publication diagnostic: kind3-rejects-begin\n" << std::flush;
            rejects([&] { rp::publish(path, "secret", hooks); });
            if (kind == 3) std::cerr << "record publication diagnostic: kind3-rejects-returned\n" << std::flush;
            check(mutated && !fs::exists(path), "actual unsafe final policy/identity cannot commit");
            if (kind == 1 || kind == 2 || kind == 3) check(fs::exists(staged), "foreign/multilink final entry not removed");
            if (kind == 3) std::cerr << "record publication diagnostic: kind3-assertions-complete\n" << std::flush;
            if (kind == 3) {
                check(host_names(*owned_tmp, staged.parent_path()) == std::set<std::string>{"record", "saved"}
                    && (owned_tmp->observe(staged).mode & 0170000) == 0120000
                    && (owned_tmp->observe(staged.parent_path() / "saved").mode & 0170000) == 0100000
                    && read(staged.parent_path() / "saved") == "secret", "known kind3 names and bytes before teardown");
            }
        } catch (...) { primary = std::current_exception(); }
        if (kind == 3) {
            symlink.finish(primary, [&](bool normal) {
                const auto workspace = staged.parent_path(), saved = workspace / "saved";
                check(host_names(*owned_tmp, workspace) == std::set<std::string>{"saved"}
                    && read(saved) == "secret", "kind3 link-only teardown preserves saved bytes");
                if (normal) {
                    owned_tmp->mutate(SRPT_UNLINK, saved);
                    check(host_names(*owned_tmp, workspace).empty(), "known kind3 workspace empty");
                    owned_tmp->mutate(SRPT_RMDIR, workspace);
                    clean_anchor(malicious.root);
                    owned_tmp->mutate(SRPT_RMDIR, anchor(malicious.root));
                    check(host_names(*owned_tmp, malicious.root).empty(), "kind3 root empty before ordinary teardown");
                }
            });
        } else if (primary) std::rethrow_exception(primary);
    }
    rp::Hooks changed;
    changed.before_commit = [&] { owned_tmp->mutate(SRPT_CHMOD, destination, 0644); };
    rejects([&] { rp::publish(destination, "blocked", changed); });
    check((owned_tmp->observe(destination).mode & 07777) == 0644 && read(destination) == "new",
        "destination final policy mutation retained, not overwritten");

    for (int kind = 0; kind < 3; ++kind) {
        Fixture metadata;
        const auto path = metadata.root / "record";
        if (kind == 0) owned_tmp->mutate(SRPT_CREATE, path, 0600, "old");
        if (kind == 1) owned_tmp->mutate(SRPT_MKDIR, anchor(metadata.root), 0700);
        const auto target = kind == 0 ? path : kind == 1 ? anchor(metadata.root) : metadata.root;
        owned_tmp->mutate(SRPT_XATTR, target, 0, "unsupported");
        const auto before = owned_tmp->observe(target);
        rejects([&] { rp::publish(path, "secret"); });
        check(same_host_object(before, owned_tmp->observe(target)), "unsupported metadata never repaired or adopted");
        if (kind == 0) check(read(path) == "old", "unsupported destination bytes unchanged");
        else check(!fs::exists(path), "unsupported parent/anchor has no publication");
        if (kind == 2) check(!fs::exists(anchor(metadata.root)), "unsupported parent fails before namespace creation");
    }
}

WineEntry production_entry()
{
    const auto module = ::GetModuleHandleW(L"space_record_publication.dll");
    win_check(module != nullptr, "loaded production pair");
    const auto entry = exported<WineEntry>(module, "SpaceRecordPublicationCall");
    SrpIdentity identity {};
    identity.size = sizeof(identity);
    identity.abi = SRP_ABI;
    identity.challenge = challenge();
    const auto original = identity.challenge;
    check(entry(SRP_ENTRY_IDENTITY, &identity) == SRP_SUCCESS, "production identity status");
    rp::wine::detail::validate_identity(identity, production_binding, original);
    return entry;
}

void wine_context_lifecycle()
{
    const auto entry = production_entry();
    for (const uint32_t phase : {SRP_START, SRP_BEFORE_WRITE, SRP_BEFORE_SECURITY, SRP_BEFORE_COMMIT, SRP_BEFORE_CLEANUP}) {
        for (bool cancel : {false, true}) {
            Fixture fixture;
            const auto destination = fixture.root / "record";
            owned_tmp->mutate(SRPT_CREATE, destination, 0600, "old");
            const auto path = host_path(destination);
            const std::string payload("new\0binary", 10);
            SrpCall call {};
            call.size = sizeof(call);
            call.abi = SRP_ABI;
            call.opcode = SRP_BEGIN;
            call.path = {reinterpret_cast<uintptr_t>(path.data()), path.size()};
            call.payload = {reinterpret_cast<uintptr_t>(payload.data()), payload.size()};
            check(entry(SRP_ENTRY_OPERATION, &call) == SRP_SUCCESS && call.context && call.event == SRP_START,
                "real bridge captures context without publication");
            while (call.event != phase) {
                check(call.event < phase, "requested bridge lifecycle phase reachable");
                call.opcode = SRP_ADVANCE;
                check(entry(SRP_ENTRY_OPERATION, &call) == SRP_SUCCESS && call.primary_state == SRP_PRIMARY_ABSENT,
                    "real bridge continuation");
            }
            const auto id = call.context;
            if (cancel) {
                call.opcode = SRP_CANCEL;
                check(entry(SRP_ENTRY_OPERATION, &call) == SRP_SUCCESS, "explicit bridge cancel");
            }
            call.opcode = SRP_RELEASE;
            check(entry(SRP_ENTRY_OPERATION, &call) == SRP_SUCCESS && (call.flags & SRP_DONE_FLAG)
                && static_cast<bool>(call.flags & SRP_COMMITTED) == (phase == SRP_BEFORE_CLEANUP),
                "release finalizes cleanup and preserves sticky commit");
            check(read(destination) == (phase == SRP_BEFORE_CLEANUP ? payload : "old"), "cancel/release never resume publication");
            if (phase != SRP_START) clean_anchor(fixture.root);
            call.opcode = SRP_SNAPSHOT;
            call.context = id;
            check(entry(SRP_ENTRY_OPERATION, &call) == SRP_INVALID_ARGUMENT && !(call.flags & SRP_VALID),
                "released context cannot be reused");
        }
    }
}

void wine_mapping_and_authority()
{
    Fixture fixture;
    for (const auto* name : {L"NUL", L"con.txt", L"COM1", L"LPT\u00b9.txt", L"record:stream", L"trailing.", L"trailing "}) {
        const auto diagnostic = rejects([&] { rp::publish(fixture.root / name, "blocked"); });
        check(diagnostic.find("Wine path syntax") != std::string::npos || diagnostic.find("Wine reserved path component") != std::string::npos,
            "reserved forms fail in production path adapter");
    }
    for (const auto* name : {L"\\\\server\\share\\record", L"\\\\?\\C:\\record", L"\\\\.\\NUL"}) {
        check(rejects([&] { rp::publish(name, "blocked"); }).find("Wine UNC/device path") != std::string::npos,
            "remote/device forms explicitly refused");
    }
    auto nul = (fixture.root / "record").native();
    nul.append(L"\0tail", 5);
    check(rejects([&] { rp::publish(fs::path(nul), "blocked"); }).find("Wine path syntax") != std::string::npos,
        "embedded path NUL cannot be truncated by mapping");
    // Discover an actually unavailable drive, never assume a Z: mapping.
    bool missing_drive = false;
    for (wchar_t drive = L'A'; drive <= L'Z'; ++drive) {
        const wchar_t root[] {drive, L':', L'\\', 0};
        if (::GetDriveTypeW(root) != DRIVE_NO_ROOT_DIR) continue;
        check(rejects([&] { rp::publish(fs::path(root) / "record", "blocked"); }).find("Wine nonlocal drive") != std::string::npos,
            "unmapped drive refuses before mapping/publication");
        missing_drive = true;
        break;
    }
    check(missing_drive, "mapping failure needs a real unavailable drive positive condition");
    int hooks = 0;
    rp::Hooks absent;
    absent.before_write = absent.before_cleanup = [&] { ++hooks; };
    rejects([&] { rp::publish(fixture.root / "missing" / "record", "blocked", absent); });
    check(hooks == 0 && !fs::exists(anchor(fixture.root)), "missing parent has no hooks/namespace");

    const auto real = fixture.root / "parent";
    owned_tmp->mutate(SRPT_MKDIR, real, 0700);
    owned_tmp->mutate(SRPT_CREATE, real / "mixed-Case", 0600, "old");
    check(rp::publish(real / "MIXED-case", "case").committed && read(real / "mixed-Case") == "case",
        "existing leaf case maps to actual host identity");
    owned_tmp->mutate(SRPT_SYMLINK, fixture.root / "alias", 0, "", "parent");
    check(rp::publish(fixture.root / "alias" / "alias-record", "alias").committed
        && read(real / "alias-record") == "alias", "parent alias acquired once then pinned on host");
    clean_anchor(real);
    owned_tmp->mutate(SRPT_UNLINK, fixture.root / "alias");

    CheckedHandle process, duplicate;
    win_check(::OpenProcessToken(::GetCurrentProcess(), TOKEN_QUERY | TOKEN_DUPLICATE, &process.value), "authority token");
    win_check(::DuplicateToken(process.value, SecurityImpersonation, &duplicate.value), "authority duplicate");
    for (int phase = -1; phase < 4; ++phase) {
        Fixture attempt;
        const auto destination = attempt.root / "record";
        owned_tmp->mutate(SRPT_CREATE, destination, 0600, "old");
        std::unique_ptr<Impersonation> impersonation;
        const auto change = [&] { impersonation = std::make_unique<Impersonation>(duplicate.value); };
        rp::Hooks callbacks;
        if (phase == -1) change();
        if (phase == 0) callbacks.before_write = change;
        if (phase == 1) callbacks.before_security = change;
        if (phase == 2) callbacks.before_commit = change;
        if (phase == 3) callbacks.before_cleanup = change;
        if (phase == 3) {
            const auto result = rp::publish(destination, "new", callbacks);
            check(result.committed && !result.cleanup_error, "cleanup remains available after postcommit authority loss");
        } else {
            const auto diagnostic = rejects([&] { rp::publish(destination, "new", callbacks); });
            check(diagnostic.find("authority") != std::string::npos, "represented authority change explicitly refused");
        }
        check(impersonation != nullptr, "authority-changing hook actually executed");
        impersonation.reset();
        check(read(destination) == (phase == 3 ? "new" : "old"), "authority change preserves correct bytes");
        if (phase >= 0) clean_anchor(attempt.root);
        else check(!fs::exists(anchor(attempt.root)), "initial authority denial creates no private namespace");
    }
    duplicate.close();
    process.close();
}

fs::path executable_path(HMODULE module = nullptr)
{
    wchar_t path[32768] {};
    const auto count = ::GetModuleFileNameW(module, path, 32768);
    win_check(count != 0 && count < 32768, "test executable path");
    return fs::path(std::wstring(path, count));
}

std::set<std::string> host_names(const HostRoot& root, const fs::path& path)
{
    const auto listing = root.observe(path);
    check((listing.mode & 0170000) == 0040000, "host directory listing");
    std::set<std::string> names;
    size_t offset = 0;
    while (offset < listing.data_size) {
        const auto* start = reinterpret_cast<const char*>(listing.data + offset);
        const auto* end = static_cast<const char*>(std::memchr(start, 0, listing.data_size - offset));
        check(end && end != start, "bounded complete directory entry");
        check(names.emplace(start, end).second, "unique directory entry");
        offset += static_cast<size_t>(end - start) + 1;
    }
    return names;
}

void verify_support_only_root(const fs::path& path)
{
    HostRoot root(path);
    check(host_names(root, path) == std::set<std::string>{"x86_64-unix", "x86_64-windows"}
        && host_names(root, path / "x86_64-windows") == std::set<std::string>{"space_record_publication_tests.dll"}
        && host_names(root, path / "x86_64-unix") == std::set<std::string>{"space_record_publication_tests.so"},
        "support-only loader root contains no production fallback");
    const auto so = root.observe(path / "x86_64-unix/space_record_publication_tests.so");
    check((so.mode & 0170000) == 0100000 && so.links == 1 && so.device == support_binding.module_device
        && so.inode == support_binding.module_inode, "support-only root matches independently bound loaded SO");
}

// Wine's Unix environment encoding is not assumed to be UTF-8. This code page
// is Wine's CP_UNIXCP (wine-9.0 include/winnls.h), used only for a checked roundtrip
// of raw mapped bytes against the Windows-visible child environment.
std::wstring unix_environment_text(const std::string& bytes)
{
    constexpr UINT unix_codepage = 65010;
    check(!bytes.empty() && bytes.size() < 32768 && bytes.find('\0') == std::string::npos, "bounded Unix environment text");
    const auto length = ::MultiByteToWideChar(unix_codepage, 0, bytes.data(), static_cast<int>(bytes.size()), nullptr, 0);
    win_check(length > 0, "Unix environment decode length");
    std::wstring text(length, L'\0');
    win_check(::MultiByteToWideChar(unix_codepage, 0, bytes.data(), static_cast<int>(bytes.size()), text.data(), length) == length,
        "Unix environment decode");
    const auto size = ::WideCharToMultiByte(unix_codepage, 0, text.data(), length, nullptr, 0, nullptr, nullptr);
    win_check(size > 0, "Unix environment encode length");
    std::string roundtrip(size, '\0');
    win_check(::WideCharToMultiByte(unix_codepage, 0, text.data(), length, roundtrip.data(), size, nullptr, nullptr) == size,
        "Unix environment encode");
    check(bytes == roundtrip && text.find(L'\0') == std::wstring::npos, "lossless raw Unix environment roundtrip");
    return text;
}

const std::array<std::string, 5> child_cases {"control", "missing-pe", "bad-pe", "missing-unix", "bad-unix"};

std::wstring child_overrides()
{
    const auto crypto = environment(L"SPACE_WINE_PUBLICATION_TEST_CRYPTO");
    check(crypto == L"b" || crypto == L"n", "exact owning test crypto handoff");
    return L"space_record_publication=b;space_record_publication_tests=b;bcryptprimitives="
        + crypto + L";advapi32,cryptbase=b";
}

int wine_child(const std::string& selected)
{
    child_phase = "location-01";
    const auto image = executable_path();
    const auto root = image.parent_path();
    child_phase = "location-02";
    const unsigned location_mask = (image.filename() == L"test_record_publication.exe" ? 1u : 0u)
        | (root.filename() == selected ? 2u : 0u)
        | (root.parent_path().filename().string().find("record-publication-") == 0 ? 4u : 0u);
    std::cerr << "record publication diagnostic: location-mask=" << location_mask << '\n' << std::flush;
    check(image.filename() == L"test_record_publication.exe" && root.filename() == selected
        && root.parent_path().filename().string().find("record-publication-") == 0,
        "closed child fixture location derives from copied executable");
    child_phase = "location-03";
    owned_tmp->relative(image); // Must be below the verified private TEMP root.
    child_phase = "location-04";
    host_private(root, true);
    child_phase = "location-05";
    check(host_path(fs::current_path()) == host_path(root), "child cwd is its owned case");
    child_phase = "location-06";
    wchar_t path_probe[2] {};
    ::SetLastError(ERROR_SUCCESS);
    const auto path_length = ::GetEnvironmentVariableW(L"PATH", path_probe, 2);
    const auto path_error = ::GetLastError();
    check(path_length == 0 && (path_error == ERROR_SUCCESS || path_error == ERROR_ENVVAR_NOT_FOUND),
        "child has no effective ambient PATH fallback after bootstrap");
    child_phase = "location-07";
    const auto overrides = environment(L"WINEDLLOVERRIDES");
    check(overrides == child_overrides(),
        "both fixed names remain forced builtin after child bootstrap");
    child_phase = "location-08";
    for (const auto& item : fs::directory_iterator(root)) {
        auto name = item.path().filename().wstring();
        std::transform(name.begin(), name.end(), name.begin(), [](wchar_t unit) {
            return unit >= L'A' && unit <= L'Z' ? unit - L'A' + L'a' : unit;
        });
        if (name.size() < 4 || name.substr(name.size() - 4) != L".dll"
            || name == L"space_record_publication.dll" || name == L"space_record_publication_tests.dll") continue;
        const auto loaded = ::GetModuleHandleW(item.path().filename().c_str());
        if (loaded) check(host_path(executable_path(loaded)) == host_path(item.path()), "non-system runtime dependency loaded from owned copy");
    }
    child_phase = "location-09";
    check(::GetModuleHandleW(L"space_record_publication.dll") == nullptr, "production DLL absent before first child publish");
    child_phase = "location-10";
    const auto module_roots = environment(L"WINEDLLPATH");
    child_phase = "location-11";
    const auto expected_prefix = unix_environment_text(host_path(root / "modules") + ":");
    child_phase = "location-12";
    check(module_roots.compare(0, expected_prefix.size(), expected_prefix) == 0, "child production module root fixed to its case");
    child_phase = "location-13";
    const auto support_root_text = module_roots.substr(expected_prefix.size());
    // Recover raw host bytes via the inverse codepage roundtrip, not a PE path
    // interpretation of a Unix path. The support root is supplied only by parent.
    constexpr UINT unix_codepage = 65010;
    const auto size = ::WideCharToMultiByte(unix_codepage, 0, support_root_text.data(), static_cast<int>(support_root_text.size()),
        nullptr, 0, nullptr, nullptr);
    win_check(size > 0 && size < 32768, "child support root encoding");
    std::string support_bytes(size, '\0');
    win_check(::WideCharToMultiByte(unix_codepage, 0, support_root_text.data(), static_cast<int>(support_root_text.size()),
        support_bytes.data(), size, nullptr, nullptr) == size, "child support root encoding");
    child_phase = "location-14";
    check(unix_environment_text(support_bytes) == support_root_text && support_bytes.find(':') == std::string::npos,
        "one independent support-only root, no extra fallback roots");
    child_phase = "location-15";
    verify_support_only_root(windows_path(support_bytes));
    child_phase = "fixture";
    const auto data = root / "data";
    owned_tmp->mutate(SRPT_MKDIR, data, 0700);
    const auto destination = data / "record";
    owned_tmp->mutate(SRPT_CREATE, destination, 0600, "old");
    const auto before = owned_tmp->observe(destination);
    int hooks = 0;
    rp::Hooks callbacks;
    callbacks.before_write = callbacks.before_security = callbacks.before_commit = callbacks.before_cleanup = [&] { ++hooks; };
    child_phase = "publication";
    if (selected == "control") {
        const auto result = rp::publish(destination, std::string("new\0bytes", 9), callbacks);
        child_phase = "identity";
        production_entry(); // Independent actual loaded Unix identity equals the copy binding.
        const auto after = owned_tmp->observe(destination);
        check(result.committed && !result.cleanup_error && hooks == 4 && read(destination) == std::string("new\0bytes", 9)
            && before.uid == after.uid && before.gid == after.gid && before.mode == after.mode && after.links == 1,
            "intact copied control must publish exact bytes with supported host policy");
        clean_anchor(data);
        std::cerr << "record publication diagnostic: control-completion=1\n" << std::flush;
    } else {
        const auto diagnostic = rejects([&] { rp::publish(destination, "secret", callbacks); });
        child_phase = "refusal";
        const bool pe = selected == "missing-pe" || selected == "bad-pe";
        const bool loader = diagnostic.find("record publication: Wine builtin load error=") == 0;
        const bool identity = diagnostic.find("record publication: Wine identity NTSTATUS=") == 0;
        check((pe ? loader : loader || identity) && diagnostic.size() < 160 && hooks == 0,
            "negative first publish fails in loader/Unix association, not binding/authority/path/fixture setup");
        check(read(destination) == "old" && same_host_object(before, owned_tmp->observe(destination))
            && !fs::exists(anchor(data)), "negative child has no commit, hook, workspace or destination mutation");
    }
    return 0;
}

SrptLaunch launch_request(uint32_t action, uint32_t case_id, uint64_t root,
                          const Binding& production, const Binding& support)
{
    SrptLaunch frame {};
    frame.size = sizeof(frame);
    frame.abi = SRPT_ABI;
    frame.action = action;
    frame.case_id = case_id;
    frame.root = root;
    std::copy(production.build_id.begin(), production.build_id.end(), frame.production_build_id);
    std::copy(support.build_id.begin(), support.build_id.end(), frame.support_build_id);
    frame.production_device = production.module_device;
    frame.production_inode = production.module_inode;
    frame.support_device = support.module_device;
    frame.support_inode = support.module_inode;
    return frame;
}

void invoke_launch(SrptLaunch& frame, Fixture* fixture)
{
    const auto input = frame;
    const auto status = support_entry(SRPT_ENTRY_LAUNCH, &frame);
    // Inspect ownership before any check can throw/unwind into recursive cleanup.
    const bool uncertain = frame.outcome == SRPT_OUTCOME_OWNERSHIP_UNCERTAIN;
    if (uncertain && fixture) fixture->preserve_wine_fixture = true;
    // C stdio keeps this fatal boundary free of C++ stream exceptions/allocations.
    std::fprintf(stderr, "record publication diagnostic: case=%u phase=%u outcome=%u errno=%u exit=%u signal=%u native-result=%u\n",
        static_cast<unsigned>(input.case_id), static_cast<unsigned>(frame.phase), static_cast<unsigned>(frame.outcome),
        static_cast<unsigned>(frame.os_error), static_cast<unsigned>(frame.exit_code), static_cast<unsigned>(frame.term_signal),
        static_cast<unsigned>(static_cast<uint32_t>(status)));
    std::fflush(nullptr);
    if (uncertain) {
        ::TerminateProcess(::GetCurrentProcess(), 125);
        std::_Exit(125); // No unwinding, atexit handlers, debugger abort or second attempt.
    }
    check(status == SRPT_SUCCESS && frame.outcome == SRPT_OUTCOME_COMPLETED
        && frame.phase == SRPT_PHASE_COMPLETE && !frame.os_error && !frame.term_signal
        && frame.exit_code == (input.action == SRPT_CONFIGURE ? UINT32_MAX : 0)
        && frame.remaining_ms <= 60000 && !frame.reserved && !frame.reserved2
        && std::memcmp(&frame, &input, offsetof(SrptLaunch, phase)) == 0,
        "closed publication launch failed (see fixed numeric native result)");
}

using Clock = std::chrono::steady_clock;
void child_budget(const Clock::time_point& deadline, int reserve_ms = 0)
{
    check(Clock::now() + std::chrono::milliseconds(reserve_ms) < deadline, "bounded children setup/execution/cleanup deadline");
}

void exclusive_copy(const fs::path& source, const HostRoot& source_root, const fs::path& destination,
                    const Clock::time_point& deadline)
{
    child_budget(deadline, 13000);
    const auto before = source_root.observe(source);
    check((before.mode & 0170000) == 0100000 && before.links == 1 && before.file_size <= 64 * 1024 * 1024,
        "copy only bounded regular verified-layout artifacts");
    win_check(::CopyFileW(source.c_str(), destination.c_str(), TRUE), "exclusive fixture artifact copy");
    const auto after = owned_tmp->observe(destination);
    check((after.mode & 0170000) == 0100000 && after.links == 1 && after.uid == owned_tmp->observe(windows_path(owned_tmp->base)).uid
        && !(after.device == before.device && after.inode == before.inode)
        && source_root.bytes(source) == owned_tmp->bytes(destination)
        && same_host_object(before, source_root.observe(source)), "independent exact owned copy, never a link or source mutation");
    child_budget(deadline, 13000);
}

void wine_loader_children()
{
    const auto call_start = Clock::now();
    auto configure = launch_request(SRPT_CONFIGURE, 0, owned_tmp->id, production_binding, support_binding);
    invoke_launch(configure, nullptr); // FIRST: native deadline/source capture precedes all fixture work.
    const auto deadline = call_start + std::chrono::milliseconds(configure.remaining_ms);
    child_budget(deadline, 13000);
    const auto image = executable_path();
    const auto overlay = image.parent_path();
    check(image.filename() == L"test_record_publication.exe" && overlay.filename() == L"windows"
        && overlay.parent_path().filename() == L"wine", "fixed verified Wine overlay executable layout");
    const auto build = overlay.parent_path().parent_path();
    const auto production_root = build / "wine-publication/modules";
    const auto support_root = build / "wine-publication-tests/modules";
    HostRoot overlay_host(overlay), production_host(production_root), support_host(support_root);
    verify_support_only_root(support_root);
    const auto so_source = production_root / "x86_64-unix/space_record_publication.so";
    const auto pe_source = production_root / "x86_64-windows/space_record_publication.dll";
    const auto source_identity = production_host.observe(so_source);
    check(source_identity.device == production_binding.module_device && source_identity.inode == production_binding.module_inode,
        "fixed production artifact source equals admitted Unix binding");
    check(overlay_host.bytes(overlay / "space_record_publication.dll") == production_host.bytes(pe_source)
        && overlay_host.bytes(overlay / "space_record_publication_tests.dll")
            == support_host.bytes(support_root / "x86_64-windows/space_record_publication_tests.dll"),
        "verified fixed-layout discovery copies match architecture images");
    Fixture fixture;
    HostRoot fixture_host(fixture.root);
    for (uint32_t case_id = 1; case_id <= child_cases.size(); ++case_id) {
        const auto& selected = child_cases[case_id - 1];
        child_budget(deadline, 13000);
        const auto root = fixture.root / selected;
        for (const auto& directory : {root, root / "modules", root / "modules/x86_64-windows", root / "modules/x86_64-unix"})
            owned_tmp->mutate(SRPT_MKDIR, directory, 0700);
        exclusive_copy(image, overlay_host, root / image.filename(), deadline);
        // All transitive non-system runtime imports are already loaded in this
        // process. Copy their admitted siblings plus any selected crypto helper;
        // unrelated application DLLs must not consume the fixed child budget.
        for (const auto& item : fs::directory_iterator(overlay)) {
            child_budget(deadline, 13000);
            auto name = item.path().filename().wstring();
            std::transform(name.begin(), name.end(), name.begin(), [](wchar_t unit) {
                return unit >= L'A' && unit <= L'Z' ? unit - L'A' + L'a' : unit;
            });
            if (name.size() < 4 || name.substr(name.size() - 4) != L".dll" || name == L"space_record_publication.dll") continue;
            if (!::GetModuleHandleW(item.path().filename().c_str()) && name != L"bcryptprimitives.dll") continue;
            exclusive_copy(item.path(), overlay_host, root / item.path().filename(), deadline);
        }
        const auto pe = root / "modules/x86_64-windows/space_record_publication.dll";
        const auto discovery = root / "space_record_publication.dll";
        const auto so = root / "modules/x86_64-unix/space_record_publication.so";
        exclusive_copy(pe_source, production_host, pe, deadline);
        exclusive_copy(pe_source, production_host, discovery, deadline);
        exclusive_copy(so_source, production_host, so, deadline);
        const auto copied = owned_tmp->observe(so);
        auto expected = production_binding;
        expected.module_device = copied.device;
        expected.module_inode = copied.inode;
        // All three exclusive copies were OBSERVEd intact after CONFIGURE, so
        // native full-source receipts precede intentional damage. Never rebind
        // from a damaged/deleted artifact or bypass native expected-copy checks.
        if (selected == "missing-pe") {
            owned_tmp->mutate(SRPT_UNLINK, pe);
            owned_tmp->mutate(SRPT_UNLINK, discovery);
        }
        if (selected == "bad-pe") {
            owned_tmp->mutate(SRPT_WRITE, pe, 0, "not-a-PE");
            owned_tmp->mutate(SRPT_WRITE, discovery, 0, "not-a-PE");
        }
        if (selected == "missing-unix") owned_tmp->mutate(SRPT_UNLINK, so);
        if (selected == "bad-unix") owned_tmp->mutate(SRPT_WRITE, so, 0, "not-an-ELF");
        child_budget(deadline, 13000);
        auto run = launch_request(SRPT_RUN, case_id, fixture_host.id, expected, support_binding);
        invoke_launch(run, &fixture); // Intact control is first and blocking.
        child_budget(deadline);
    }
    // Explicit checked cleanup is inside the same60s component bound.
    check(fs::remove_all(fixture.root) > 0, "owned child fixture cleanup");
    fixture.preserve_wine_fixture = true; // Already removed explicitly; no destructor cleanup outside the budget.
    child_budget(deadline);
}

void wine_report()
{
    verify_support();
    production_entry(); // Report the admitted production identity, never a child copy.
    const auto report = fs::temp_directory_path() / "space-record-publication-report.json";
    const auto before = owned_tmp->observe(report);
    check((before.mode & 0177777) == 0100600 && before.links == 1 && before.file_size == 0
        && before.uid == owned_tmp->observe(windows_path(owned_tmp->base)).uid, "parent-exclusive fresh0600 report origin");
    const auto json = report_json(production_binding);
    CheckedHandle output;
    output.value = ::CreateFileW(report.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    win_check(output.value != INVALID_HANDLE_VALUE, "existing report open");
    BY_HANDLE_FILE_INFORMATION info {};
    win_check(::GetFileInformationByHandle(output.value, &info), "existing report handle inspect");
    check(!(info.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT))
        && info.nNumberOfLinks == 1 && info.nFileSizeHigh == 0 && info.nFileSizeLow == 0, "fresh regular report handle");
    DWORD offset = 0;
    while (offset < json.size()) {
        DWORD written = 0;
        win_check(::WriteFile(output.value, json.data() + offset, static_cast<DWORD>(json.size() - offset), &written, nullptr),
            "report write");
        check(written > 0 && written <= json.size() - offset, "complete bounded report write");
        offset += written;
    }
    win_check(::FlushFileBuffers(output.value), "report flush");
    output.close();
    auto after = owned_tmp->observe(report);
    after.file_size = before.file_size;
    check(same_host_object(before, after) && owned_tmp->bytes(report) == json, "report origin and exact JSON preserved");
}
#endif

} // namespace

int main(int argc, char** argv)
{
    try {
        std::cerr << "record publication diagnostic: main-entry\n" << std::flush;
#ifdef _WIN32
        under_wine = rp::wine::detected();
        if (under_wine) {
            child_phase = "owned-environment";
            const auto error = space_wine_apply_owned_environment(TRUE);
            check(error == ERROR_SUCCESS, "required owned environment error=" + std::to_string(error));
        }
#endif
        std::string child;
        if (argc != 1) {
#ifdef _WIN32
            const std::string prefix = "--wine-publication-child=";
            check(under_wine && argc == 2 && std::string(argv[1]).compare(0, prefix.size(), prefix) == 0,
                "only one fixed private Wine child argument is accepted");
            child = std::string(argv[1]).substr(prefix.size());
            check(std::find(child_cases.begin(), child_cases.end(), child) != child_cases.end(), "unknown private Wine child case");
#else
            (void)argv;
            throw std::runtime_error("private Wine child modes require Wine");
#endif
        }
#ifdef _WIN32
        if (under_wine) {
            child_phase = "support-identity";
            check(::GetModuleHandleW(L"space_record_publication.dll") == nullptr, "production DLL not loaded before controlled test entry");
            load_support();
            owned_tmp = std::make_unique<HostRoot>(fs::temp_directory_path());
            check(::GetModuleHandleW(L"space_record_publication.dll") == nullptr, "support setup must not preload production DLL");
            if (!child.empty()) return wine_child(child); // No common suite or report in children.
        }
#endif
        private_contract_models();
        basic_publication();
        unicode_long_paths_and_payload_snapshot();
        phase_failures_and_cleanup();
        final_validation();
        independent_attempts();
        namespace_attacks();
#ifndef _WIN32
        ordinary_layouts();
        owned_anchor_groups();
        posix_security();
        unsafe_anchors();
        real_writer_failure();
#else
        if (under_wine) {
            std::cerr << "record publication diagnostic: wine-host-policy-begin\n" << std::flush;
            wine_host_policy();
            std::cerr << "record publication diagnostic: wine-host-policy-returned\n" << std::flush;
            wine_symlink_cleanup_regressions();
            wine_context_lifecycle();
            wine_mapping_and_authority();
            wine_loader_children();
            wine_report(); // No report unless every mandatory category completed.
        } else {
            windows_creation_boundary_diagnostics();
            windows_foreign_parent_and_private_children();
            windows_junction_anchor_attack();
            windows_security();
        }
#endif
        std::cout << "record publication tests passed\n";
        return 0;
    } catch (const std::exception& error) {
#ifdef _WIN32
        if (argc != 1) {
            std::cerr << "record publication child failed phase=" << child_phase << " error=" << child_error << '\n' << std::flush;
            return 1;
        }
#endif
        std::cerr << "record publication test failed: " << error.what() << '\n';
        return 1;
    }
}
