#include "record_publication.h"

#include <array>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#include <aclapi.h>
#include <sddl.h>
#include <winioctl.h>
#else
#include <cerrno>
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
    if (!condition) {
        throw std::runtime_error(message);
    }
}

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
    fs::path absolute = fs::absolute(path);
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
    try {
        action();
    } catch (const std::exception& error) {
        return error.what();
    }
    throw std::runtime_error("expected explicit precommit failure");
}

struct Fixture {
    fs::path root = fs::temp_directory_path()
        / ("record-publication-test-" + std::to_string(
            std::chrono::steady_clock::now().time_since_epoch().count()));

    Fixture()
    {
#ifdef _WIN32
        check(fs::create_directory(root), "fixture directory creation failed");
#else
        // Exclusive private fixture directly under the system temporary parent;
        // never rely on the runner's umask or chmod shared /tmp/space ancestry.
        std::string pattern = (fs::temp_directory_path() / "record-publication-XXXXXX").string();
        std::vector<char> name(pattern.begin(), pattern.end());
        name.push_back('\0');
        check(::mkdtemp(name.data()) != nullptr, "exclusive private fixture creation failed");
        root = name.data();
#endif
    }

    ~Fixture()
    {
        std::error_code ignored;
        fs::remove_all(root, ignored); // Test-owned fixture only; production never recurses.
    }
};

#ifndef _WIN32
mode_t mode(const fs::path& path)
{
    struct stat info {};
    check(::lstat(path.c_str(), &info) == 0, "fixture stat failed");
    return info.st_mode & 07777;
}

void chmod_checked(const fs::path& path, mode_t value)
{
    check(::chmod(path.c_str(), value) == 0, "fixture chmod failed");
}
#endif

#ifdef _WIN32
struct SecuritySnapshot {
    std::vector<unsigned char> owner, group, dacl;
};

SecuritySnapshot windows_policy(const fs::path& path)
{
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    PSID owner = nullptr, group = nullptr;
    PACL dacl = nullptr;
    const DWORD status = ::GetNamedSecurityInfoW(const_cast<wchar_t*>(path.c_str()), SE_FILE_OBJECT,
        OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
        &owner, &group, &dacl, nullptr, &descriptor);
    check(status == ERROR_SUCCESS && owner && group && dacl && ::IsValidAcl(dacl), "inspect native policy fixture");
    SecuritySnapshot result;
    result.owner.assign(static_cast<unsigned char*>(owner), static_cast<unsigned char*>(owner) + ::GetLengthSid(owner));
    result.group.assign(static_cast<unsigned char*>(group), static_cast<unsigned char*>(group) + ::GetLengthSid(group));
    result.dacl.assign(reinterpret_cast<unsigned char*>(dacl), reinterpret_cast<unsigned char*>(dacl) + dacl->AclSize);
    ::LocalFree(descriptor);
    return result;
}

void check_windows_private(const fs::path& path)
{
    const auto policy = windows_policy(path);
    auto* dacl = reinterpret_cast<PACL>(const_cast<unsigned char*>(policy.dacl.data()));
    check(dacl->AceCount == 1, "private file/directory must have one owner ACE");
    void* raw = nullptr;
    check(::GetAce(dacl, 0, &raw), "inspect private ACE");
    auto* ace = static_cast<ACCESS_ALLOWED_ACE*>(raw);
    check(ace->Header.AceType == ACCESS_ALLOWED_ACE_TYPE && ace->Mask == FILE_ALL_ACCESS
          && ::EqualSid(&ace->SidStart, const_cast<unsigned char*>(policy.owner.data()))
          && !(ace->Header.AceFlags & INHERIT_ONLY_ACE), "private contents have an effective owner-only DACL");
}

void windows_ancestor_acl(const fs::path& path, DWORD foreign_rights)
{
    auto policy = windows_policy(path);
    alignas(DWORD) std::array<unsigned char, SECURITY_MAX_SID_SIZE> everyone {};
    DWORD size = everyone.size();
    check(::CreateWellKnownSid(WinWorldSid, nullptr, everyone.data(), &size), "ancestor Everyone SID fixture");
    std::vector<unsigned char> bytes(sizeof(ACL) + 2 * (sizeof(ACCESS_ALLOWED_ACE) - sizeof(DWORD))
                                     + size + policy.owner.size());
    auto* acl = reinterpret_cast<PACL>(bytes.data());
    check(::InitializeAcl(acl, bytes.size(), ACL_REVISION)
          && ::AddAccessAllowedAce(acl, ACL_REVISION, FILE_ALL_ACCESS, policy.owner.data())
          && ::AddAccessAllowedAce(acl, ACL_REVISION, foreign_rights, everyone.data()), "ancestor ACL fixture");
    check(::SetNamedSecurityInfoW(const_cast<wchar_t*>(path.c_str()), SE_FILE_OBJECT,
          DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
          nullptr, nullptr, acl, nullptr) == ERROR_SUCCESS, "install test-owned ancestor ACL");
}

void windows_foreign_writable_ancestry()
{
    Fixture fixture;
    const auto ancestor = fixture.root / "ancestor";
    check(fs::create_directory(ancestor), "exclusive ancestor fixture");
    const std::array<DWORD, 3> unsafe_rights {GENERIC_WRITE, FILE_WRITE_DATA, FILE_GENERIC_WRITE};
    for (const DWORD rights : unsafe_rights) {
        windows_ancestor_acl(ancestor, rights);
        bool callback_ran = false;
        const auto error = rejects([&] {
            rp::publish(ancestor / "record", "private", [&](const fs::path& path) {
                callback_ran = true;
                write(path, "private");
            });
        });
        check(!callback_ran, "foreign reparse-mutable ancestry must be refused BEFORE callback/private bytes");
        check(error.find("untrusted mutable ancestry DACL") != std::string::npos,
              "refusal must come from ancestry permissions, not another unsupported fixture policy");
        check(fs::is_empty(ancestor), "unsafe ancestry refusal must not create a workspace or destination");
    }
    // Preserve supported ordinary read/traverse and directory-creation grants:
    // FILE_ADD_SUBDIRECTORY is not FILE_WRITE_DATA/FILE_ADD_FILE.
    windows_ancestor_acl(ancestor, GENERIC_READ | GENERIC_EXECUTE | FILE_ADD_SUBDIRECTORY);
    bool callback_ran = false;
    const auto result = rp::publish(ancestor / "record", "private", [&](const fs::path& path) {
        callback_ran = true;
        write(path, "private");
    });
    check(callback_ran && result.committed && !result.cleanup_error,
          "ordinary non-mutating foreign ancestry grants remain supported");
}

struct WindowsTestHandle {
    HANDLE value = INVALID_HANDLE_VALUE;
    ~WindowsTestHandle()
    {
        if (value != INVALID_HANDLE_VALUE && value != nullptr) ::CloseHandle(value);
    }
    WindowsTestHandle() = default;
    WindowsTestHandle(const WindowsTestHandle&) = delete;
    WindowsTestHandle& operator=(const WindowsTestHandle&) = delete;
};

struct RestrictedImpersonation {
    explicit RestrictedImpersonation(HANDLE token)
    {
        check(::ImpersonateLoggedOnUser(token), "impersonate test-only restricted token");
    }
    ~RestrictedImpersonation()
    {
        // A failure must never allow later tests to proceed under another token.
        if (!::RevertToSelf()) std::abort();
    }
    RestrictedImpersonation(const RestrictedImpersonation&) = delete;
    RestrictedImpersonation& operator=(const RestrictedImpersonation&) = delete;
};

std::vector<unsigned char> junction_payload(const fs::path& target)
{
    // Documented IO_REPARSE_TAG_MOUNT_POINT layout, with both counted names and
    // terminating UTF-16 NULs. No SDK-private REPARSE_DATA_BUFFER dependency.
    struct Header {
        DWORD tag;
        WORD length, reserved;
        WORD substitute_offset, substitute_length, print_offset, print_length;
    };
    static_assert(sizeof(Header) == 16, "mount-point reparse header layout");
    auto absolute = fs::absolute(target);
    absolute.make_preferred();
    const std::wstring print = absolute.native();
    const std::wstring substitute = L"\\??\\" + print;
    const auto substitute_bytes = substitute.size() * sizeof(wchar_t);
    const auto print_bytes = print.size() * sizeof(wchar_t);
    const auto names_bytes = substitute_bytes + print_bytes + 2 * sizeof(wchar_t);
    check(names_bytes + sizeof(Header) <= 16384, "bounded junction fixture payload");
    const Header header {IO_REPARSE_TAG_MOUNT_POINT, static_cast<WORD>(8 + names_bytes), 0,
        0, static_cast<WORD>(substitute_bytes), static_cast<WORD>(substitute_bytes + sizeof(wchar_t)),
        static_cast<WORD>(print_bytes)};
    std::vector<unsigned char> payload(sizeof(Header) + names_bytes, 0);
    std::memcpy(payload.data(), &header, sizeof(header));
    std::memcpy(payload.data() + sizeof(Header), substitute.c_str(), substitute_bytes);
    std::memcpy(payload.data() + sizeof(Header) + substitute_bytes + sizeof(wchar_t), print.c_str(), print_bytes);
    return payload;
}

void windows_junction_mutation_protection()
{
    Fixture fixture;
    const auto probe = fixture.root / "junction-probe";
    const auto target = fixture.root / "junction-target";
    const auto protected_ancestor = fixture.root / "protected-ancestor";
    check(fs::create_directory(probe) && fs::create_directory(target)
          && fs::create_directory(protected_ancestor), "exclusive junction test directories");
    write(target / "marker", "junction target");
    windows_ancestor_acl(probe, GENERIC_READ | GENERIC_WRITE);
    windows_ancestor_acl(protected_ancestor, GENERIC_READ | GENERIC_EXECUTE);

    WindowsTestHandle process_token, restricted;
    check(::OpenProcessToken(::GetCurrentProcess(), TOKEN_QUERY | TOKEN_DUPLICATE, &process_token.value),
          "open current token for junction fixture");
    alignas(DWORD) std::array<unsigned char, SECURITY_MAX_SID_SIZE> everyone {};
    DWORD sid_size = everyone.size();
    check(::CreateWellKnownSid(WinWorldSid, nullptr, everyone.data(), &sid_size), "junction restricted SID");
    SID_AND_ATTRIBUTES limiting_sid {everyone.data(), 0};
    // Access must pass both the ordinary user DACL check and the World-only
    // restricted-SID check. Owner's full-access ACE cannot mask missing foreign
    // write access. No credentials, privilege enabling or elevated fallback.
    check(::CreateRestrictedToken(process_token.value, DISABLE_MAX_PRIVILEGE, 0, nullptr,
          0, nullptr, 1, &limiting_sid, &restricted.value), "create restricted junction fixture token");
    const auto payload = junction_payload(target);
    DWORD status = ERROR_SUCCESS;
    {
        WindowsTestHandle pin;
        pin.value = ::CreateFileW(probe.c_str(), READ_CONTROL | FILE_READ_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        check(pin.value != INVALID_HANDLE_VALUE, "pin probe without delete sharing");
        RestrictedImpersonation impersonation(restricted.value);
        WindowsTestHandle writer;
        writer.value = ::CreateFileW(probe.c_str(), GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        check(writer.value != INVALID_HANDLE_VALUE, "foreign-write positive-control handle must open");
        DWORD returned = 0;
        if (!::DeviceIoControl(writer.value, FSCTL_SET_REPARSE_POINT,
                const_cast<unsigned char*>(payload.data()), static_cast<DWORD>(payload.size()),
                nullptr, 0, &returned, nullptr)) status = ::GetLastError();
    }
    if (status == ERROR_PRIVILEGE_NOT_HELD || status == ERROR_NOT_SUPPORTED || status == ERROR_INVALID_FUNCTION) {
        std::cout << "junction mutation execution NOT APPLICABLE/NOT VERIFIED on this host: native error "
                  << status << "; mandatory pre-callback ACL-refusal cases still run\n";
        return;
    }
    check(status == ERROR_SUCCESS, "actual junction positive control must succeed, not merely fail to rename");
    check((::GetFileAttributesW(probe.c_str()) & FILE_ATTRIBUTE_REPARSE_POINT) != 0
          && read(probe / "marker") == "junction target", "FSCTL positive control actually redirects paths");
    check(::RemoveDirectoryW(probe.c_str()), "remove test-owned junction without following target");
    check(read(target / "marker") == "junction target", "junction cleanup preserves its owned target");

    bool checked = false;
    const auto result = rp::publish(protected_ancestor / "record", "private", [&](const fs::path& stage) {
        write(stage, "private");
        RestrictedImpersonation impersonation(restricted.value);
        WindowsTestHandle writer;
        writer.value = ::CreateFileW(protected_ancestor.c_str(), GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        const DWORD error = ::GetLastError();
        check(writer.value == INVALID_HANDLE_VALUE && error == ERROR_ACCESS_DENIED,
              "supported ancestry denies the foreign handle needed for proven junction mutation while bytes exist");
        checked = true;
    });
    check(checked && result.committed && !result.cleanup_error,
          "foreign junction mutation prevented for the complete private-byte callback");
}
#endif

void basic_publication(bool check_umask022_mode = false)
{
    Fixture fixture;
    const fs::path destination = fixture.root / std::string(220, 'r');
    for (const std::string text : {std::string("before"), std::string("after \xE9\x9B\xAA\0tail", 14)}) {
        fs::path workspace;
        const auto result = rp::publish(destination, text, [&](const fs::path& stage) {
            workspace = stage.parent_path();
            check(stage.filename() == "record", "fixed callback target");
            check(!fs::exists(stage), "callback target must start absent");
            check(fs::is_empty(stage.string() + ".tmp"), "precreated temporary must be empty");
#ifndef _WIN32
            check(mode(workspace) == 0700, "workspace private before bytes");
            check(mode(stage.string() + ".tmp") == 0600, "temporary private before bytes");
#else
            check_windows_private(workspace);
            check_windows_private(stage.string() + ".tmp");
#endif
            write(stage.string() + ".tmp", text);
            write(stage, text);
            check(read(stage) == text && read(stage.string() + ".tmp") == text,
                  "both intermediate files contain private bytes");
#ifndef _WIN32
            check(mode(workspace) == 0700, "intermediate effective confidentiality");
            if (check_umask022_mode)
                check(mode(stage) == 0644, "ordinary writer mode0644 is confidential inside directory0700");
#else
            check_windows_private(stage);
            check_windows_private(stage.string() + ".tmp");
#endif
        });
        check(result.committed && !result.cleanup_error, "successful publication result");
        check(read(destination) == text, "exact published bytes");
        check(!fs::exists(workspace), "owned workspace cleaned");
#ifndef _WIN32
        check(mode(destination) == 0600, "new and replaced destination private");
#endif
    }
}

#ifdef _WIN32
void windows_security()
{
    Fixture fixture;
    const auto destination = fixture.root / "restricted";
    write(destination, "old");
    auto original = windows_policy(destination);
    std::array<unsigned char, SECURITY_MAX_SID_SIZE> everyone {};
    DWORD sid_size = everyone.size();
    check(::CreateWellKnownSid(WinWorldSid, nullptr, everyone.data(), &sid_size), "everyone SID fixture");
    std::vector<unsigned char> acl(sizeof(ACL) + 2 * (sizeof(ACCESS_ALLOWED_ACE) - sizeof(DWORD))
                                   + sid_size + original.owner.size());
    auto* dacl = reinterpret_cast<PACL>(acl.data());
    check(::InitializeAcl(dacl, acl.size(), ACL_REVISION)
          && ::AddAccessDeniedAce(dacl, ACL_REVISION, FILE_WRITE_DATA, everyone.data())
          && ::AddAccessAllowedAce(dacl, ACL_REVISION, FILE_ALL_ACCESS, original.owner.data()),
          "ordered deny/allow fixture");
    check(::SetNamedSecurityInfoW(const_cast<wchar_t*>(destination.c_str()), SE_FILE_OBJECT,
          DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
          nullptr, nullptr, dacl, nullptr) == ERROR_SUCCESS, "set restrictive DACL fixture");
    original = windows_policy(destination);
    const rp::Stage stage = [](const fs::path& path) { write(path, "new"); check_windows_private(path); };
    const auto result = rp::publish(destination, "new", stage);
    check(result.committed && !result.cleanup_error && read(destination) == "new", "native Windows existing overwrite");
    const auto replacement = windows_policy(destination);
    check(original.owner == replacement.owner && original.group == replacement.group
          && original.dacl == replacement.dacl, "exact Windows owner/group/ordered allow-deny restrictions preserved");
    bool changed = false;
    rejects([&] {
        rp::publish(destination, "new", stage, {{}, [&] {
            check(::SetNamedSecurityInfoW(const_cast<wchar_t*>(destination.c_str()), SE_FILE_OBJECT,
                  DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                  nullptr, nullptr, reinterpret_cast<PACL>(windows_policy(fixture.root).dacl.data()), nullptr)
                  == ERROR_SUCCESS, "inject destination policy change");
            changed = true;
        }, {}});
    });
    check(changed, "Windows destination policy change fixture actually executed");
    check(read(destination) == "new", "changed destination policy refusal preserves bytes");
    fs::path staged;
    changed = false;
    rejects([&] {
        rp::publish(destination, "new", [&](const fs::path& path) { staged = path; stage(path); },
            {{}, [&] {
                check(::SetNamedSecurityInfoW(const_cast<wchar_t*>(staged.c_str()), SE_FILE_OBJECT,
                      DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                      nullptr, nullptr, dacl, nullptr) == ERROR_SUCCESS, "inject stage DACL change");
                changed = true;
            }, {}});
    });
    check(changed && read(destination) == "new", "stage final DACL change is rejected after hook");
    const auto pinned = rp::publish(fixture.root / "pinned", "new", [&](const fs::path& path) {
        staged = path;
        stage(path);
    }, {{}, [&] {
        const auto moved = fixture.root / "moved-workspace";
        check(!::MoveFileExW(staged.parent_path().c_str(), moved.c_str(), 0), "workspace handle prevents path substitution");
        const auto error = ::GetLastError();
        check(error == ERROR_SHARING_VIOLATION || error == ERROR_ACCESS_DENIED,
              "workspace rename failed due to pinning, not a malformed fixture");
    }, {}});
    check(pinned.committed && !pinned.cleanup_error, "blocked Windows workspace substitution leaves usable stage");
    const auto readonly = fixture.root / "pinned";
    check(::SetFileAttributesW(readonly.c_str(), FILE_ATTRIBUTE_READONLY), "readonly commit-failure fixture");
    const auto commit_error = rejects([&] {
        rp::publish(readonly, "replacement", [](const fs::path& path) { write(path, "replacement"); });
    });
    check(commit_error.find("atomic MoveFileExW publication") != std::string::npos
          && read(readonly) == "new", "native publication FALSE is explicit and preserves old bytes");
    check(::SetFileAttributesW(readonly.c_str(), FILE_ATTRIBUTE_NORMAL), "restore test-owned readonly fixture");
    const auto linked = fixture.root / "hardlink";
    check(::CreateHardLinkW(linked.c_str(), destination.c_str(), nullptr), "hardlink fixture");
    rejects([&] { rp::publish(destination, "new", stage); });
    fs::remove(linked);
    PSECURITY_DESCRIPTOR label = nullptr;
    check(::ConvertStringSecurityDescriptorToSecurityDescriptorW(L"S:(ML;;NW;;;LW)", SDDL_REVISION_1,
          &label, nullptr), "explicit label fixture");
    BOOL present = FALSE, defaulted = FALSE;
    PACL sacl = nullptr;
    check(::GetSecurityDescriptorSacl(label, &present, &sacl, &defaulted) && present, "inspect fixture label");
    const DWORD label_status = ::SetNamedSecurityInfoW(const_cast<wchar_t*>(destination.c_str()), SE_FILE_OBJECT,
        LABEL_SECURITY_INFORMATION, nullptr, nullptr, nullptr, sacl);
    ::LocalFree(label);
    check(label_status == ERROR_SUCCESS, "install explicit low label without elevated privileges");
    rejects([&] { rp::publish(destination, "new", stage); });
    check(read(destination) == "new", "unsupported Windows label does not publish");
}
#endif

void failure_and_cleanup_contract()
{
    Fixture fixture;
    const auto destination = fixture.root / "destination";
    write(destination, "old");
    fs::path workspace;
    const rp::Stage stage = [&](const fs::path& path) {
        workspace = path.parent_path();
        write(path, "new");
    };
    const auto fault = [] { throw std::runtime_error("injected fault"); };
    for (int phase = 0; phase < 3; ++phase) {
        rp::Hooks hooks;
        if (phase == 0) hooks.before_security = fault;
        if (phase == 1) hooks.before_commit = fault;
        if (phase == 2) hooks.before_cleanup = fault;
        if (phase < 2) {
            const auto error = rejects([&] { rp::publish(destination, "new", stage, hooks); });
            check(error.find("injected fault") != std::string::npos, "original fault retained");
            check(read(destination) == "old", "precommit failure preserves destination");
        } else {
            const auto result = rp::publish(destination, "new", stage, hooks);
            check(result.committed && result.cleanup_error, "cleanup failure is committed diagnostic");
            check(read(destination) == "new", "cleanup fault cannot roll back");
        }
        check(!fs::exists(workspace), "cleanup still attempted after hook failure");
    }
    rejects([&] { rp::publish(destination, "wrong", stage); });
    check(read(destination) == "new", "byte mismatch does not publish");
    rejects([&] {
        rp::publish(destination, "new", [&](const fs::path& path) {
            stage(path);
            throw std::runtime_error("writer failed");
        });
    });
    check(!fs::exists(workspace), "throwing stage cleaned synchronously");
    rejects([&] { rp::publish(fixture.root / "missing" / "record", "new", stage); });
    rejects([&] { rp::publish(destination, "", {}); });

    const auto result = rp::publish(destination, "new", stage,
        {{}, {}, [&] { write(workspace / "unrelated", "keep"); }});
    check(result.committed && result.cleanup_error, "unexpected entry gives cleanup diagnostic");
    check(read(workspace / "unrelated") == "keep", "cleanup never removes unrelated entries");
    check(!fs::exists(workspace / "record.tmp"), "known temporary still cleaned");

    const auto combined = rejects([&] {
        rp::publish(destination, "new", stage, {{}, fault, [] { throw std::runtime_error("cleanup fault"); }});
    });
    check(combined.find("injected fault") != std::string::npos
          && combined.find("cleanup fault") != std::string::npos, "original and cleanup errors both retained");
    check(!fs::exists(workspace), "combined errors still clean owned entries");

    const auto substituted = rp::publish(destination, "new", stage,
        {{}, {}, [&] { write(workspace / "record", "foreign"); }});
    check(substituted.committed && substituted.cleanup_error, "substituted fixed entry diagnosed after commit");
    check(read(workspace / "record") == "foreign", "postcommit foreign fixed entry never removed");
    check(read(destination) == "new", "postcommit cleanup substitution cannot change destination");

    const auto empty = fixture.root / "empty";
    check(rp::publish(empty, "", [](const fs::path& path) { write(path, ""); }).committed,
          "empty expected bytes are valid");
    rejects([&] { rp::publish(destination, "new", [](const fs::path&) {}); });
    const auto appeared = fixture.root / "appeared";
    rejects([&] { rp::publish(appeared, "new", stage, {{}, [&] { write(appeared, "external"); }, {}}); });
    check(read(appeared) == "external", "new destination appearing before commit is not overwritten");
    const auto directory = fixture.root / "directory";
    fs::create_directory(directory);
    rejects([&] { rp::publish(directory, "new", stage); });
}

#ifndef _WIN32
void child_umask022()
{
    const pid_t child = ::fork();
    check(child >= 0, "fork umask fixture");
    if (child == 0) {
        ::umask(0022); // Child only: neither production nor parent changes umask.
        try {
            basic_publication(true);
            ::_exit(0);
        } catch (const std::exception& error) {
            std::cerr << "umask022 child: " << error.what() << '\n';
            ::_exit(1);
        }
    }
    int status = 0;
    pid_t waited;
    do { waited = ::waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    check(waited == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
          "private new/existing publication under child umask022");
}

void posix_security()
{
    Fixture fixture;
    const auto destination = fixture.root / "destination";
    const rp::Stage stage = [](const fs::path& path) { write(path, "new"); };
    write(destination, "old");
    chmod_checked(destination, 0640);
    struct stat original {};
    check(::stat(destination.c_str(), &original) == 0, "destination stat");
    check(rp::publish(destination, "new", stage).committed, "restricted replacement");
    struct stat replaced {};
    check(::stat(destination.c_str(), &replaced) == 0, "replacement stat");
    check(mode(destination) == 0640 && original.st_uid == replaced.st_uid
          && original.st_gid == replaced.st_gid, "owner/group/mode preserved");
    const auto readonly = fixture.root / "readonly";
    write(readonly, "old");
    chmod_checked(readonly, 0400);
    check(rp::publish(readonly, "new", stage).committed && mode(readonly) == 0400,
          "readonly final restriction is established before publication using retained validation handle");

    rejects([&] {
        rp::publish(destination, "new", stage,
            {{}, [&] { chmod_checked(destination, 0600); }, {}});
    });
    check(mode(destination) == 0600, "changed destination security not overwritten");
    rejects([&] {
        rp::publish(destination, "new", stage,
            {{}, [&] {
                fs::rename(destination, fixture.root / "original");
                write(destination, "foreign");
            }, {}});
    });
    check(read(destination) == "foreign", "changed destination identity preserved");
    chmod_checked(destination, 04600);
    rejects([&] { rp::publish(destination, "new", stage); });
    chmod_checked(destination, 0600);

    const auto hardlink = fixture.root / "hardlink";
    fs::create_hard_link(destination, hardlink);
    rejects([&] { rp::publish(destination, "new", stage); });
    fs::remove(hardlink);
    const auto symlink = fixture.root / "symlink";
    fs::create_symlink(destination, symlink);
    rejects([&] { rp::publish(symlink, "new", stage); });
    fs::path staged;
    rejects([&] {
        rp::publish(destination, "new", [&](const fs::path& path) {
            staged = path;
            fs::create_symlink(destination, path);
        });
    });
    check(fs::is_symlink(staged), "unsafe substituted entry is not removed");
    rejects([&] {
        rp::publish(destination, "new", [&](const fs::path& path) {
            staged = path;
            fs::create_hard_link(destination, path);
        });
    });
    fs::remove(staged); // Restore fixture link count so subsequent tests reach their phase hooks.

    rejects([&] {
        rp::publish(destination, "new", [&](const fs::path& path) { staged = path; stage(path); },
            {{}, [&] { chmod_checked(staged, 0666); }, {}});
    });
    rejects([&] {
        rp::publish(destination, "new", [&](const fs::path& path) { staged = path; stage(path); },
            {{}, [&] { write(staged, "bad"); }, {}});
    });
    rejects([&] {
        rp::publish(destination, "new", [&](const fs::path& path) { staged = path; stage(path); },
            {{}, [&] {
                fs::rename(staged, staged.parent_path() / "saved");
                write(staged, "new");
            }, {}});
    });
    check(fs::exists(staged), "foreign replacement not cleaned");

    bool before_security_ran = false;
    rejects([&] {
        rp::publish(destination, "new", [&](const fs::path& path) { staged = path; stage(path); },
            {[&] {
                before_security_ran = true;
                fs::rename(staged, staged.parent_path() / "saved");
                write(staged, "new");
            }, {}, {}});
    });
    check(before_security_ran && read(staged) == "new", "before-security substitution detected and left untouched");

    fs::path workspace, moved;
    const auto workspace_error = rejects([&] {
        rp::publish(destination, "new", [&](const fs::path& path) {
            workspace = path.parent_path();
            moved = workspace.string() + "-moved";
            stage(path);
        }, {{}, [&] {
            fs::rename(workspace, moved);
            check(::mkdir(workspace.c_str(), 0700) == 0, "workspace substitute fixture");
            write(workspace / "foreign", "keep");
        }, {}});
    });
    check(workspace_error.find("cleanup") != std::string::npos, "workspace substitution reports cleanup diagnostic");
    check(read(workspace / "foreign") == "keep", "substitute directory untouched");
    check(fs::is_empty(moved), "original pinned workspace cleans only its owned entries");

    rejects([&] {
        rp::publish(destination, "new", stage,
            {{}, [&] { chmod_checked(fixture.root, 0750); }, {}});
    });
    chmod_checked(fixture.root, 0700);
    const auto alias = fixture.root / "owned-alias";
    fs::create_directory_symlink(fixture.root, alias);
    check(rp::publish(alias / "alias-record", "new", stage).committed, "trusted owner alias resolves to pinned parent");
    fs::remove(alias); // Test fixture recursion must not encounter this self-alias.

    rejects([&] {
        rp::publish(destination, "new", [&](const fs::path& path) { staged = path; stage(path); },
            {{}, [&] { fs::create_hard_link(staged, fixture.root / "stage-link"); }, {}});
    });
    check(fs::hard_link_count(staged) == 2, "stage hardlink substitution not removed");
    fs::remove(staged);
    fs::remove(fixture.root / "stage-link");
    const auto fifo = fixture.root / "fifo";
    check(::mkfifo(fifo.c_str(), 0600) == 0, "FIFO fixture");
    rejects([&] { rp::publish(fifo, "new", stage); });

#ifdef __linux__
    // A real extended attribute is an unsupported policy, not a mocked failure.
    const auto metadata = fixture.root / "metadata";
    write(metadata, "old");
    check(::setxattr(metadata.c_str(), "user.publication-test", "x", 1, 0) == 0,
          "xattr fixture requires supported local filesystem");
    rejects([&] { rp::publish(metadata, "new", stage); });
    check(read(metadata) == "old", "unsupported destination metadata preserved");
    rejects([&] {
        rp::publish(fixture.root / "new", "new", [&](const fs::path& path) {
            staged = path;
            stage(path);
        }, {{}, [&] {
            check(::setxattr(staged.c_str(), "user.publication-test", "x", 1, 0) == 0,
                  "stage xattr injection");
        }, {}});
    });
    const auto inherited = fixture.root / "metadata-parent";
    check(::mkdir(inherited.c_str(), 0700) == 0, "metadata parent fixture");
    check(::setxattr(inherited.c_str(), "user.publication-test", "x", 1, 0) == 0, "parent metadata injection");
    rejects([&] { rp::publish(inherited / "record", "new", stage); });
#endif
    const auto untrusted = fixture.root / "untrusted";
    fs::create_directory(untrusted);
    chmod_checked(untrusted, 0777);
    rejects([&] { rp::publish(untrusted / "record", "new", stage); });
}
#endif

} // namespace

int main()
{
    try {
        basic_publication();
        failure_and_cleanup_contract();
#ifndef _WIN32
        child_umask022();
        posix_security();
#else
        windows_foreign_writable_ancestry();
        windows_junction_mutation_protection();
        windows_security();
#endif
        std::cout << "record publication tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "record publication test failed: " << error.what() << '\n';
        return 1;
    }
}
