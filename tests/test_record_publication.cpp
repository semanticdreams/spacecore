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

struct Fixture {
    fs::path root;
    Fixture()
    {
#ifdef _WIN32
        root = fs::temp_directory_path() / ("record-publication-" + std::to_string(
            std::chrono::steady_clock::now().time_since_epoch().count()));
        check(fs::create_directory(root), "exclusive fixture creation");
#else
        auto pattern = (fs::temp_directory_path() / "record-publication-XXXXXX").string();
        std::vector<char> name(pattern.begin(), pattern.end());
        name.push_back('\0');
        check(::mkdtemp(name.data()) != nullptr, "exclusive private fixture creation");
        root = name.data();
#endif
    }
    ~Fixture()
    {
        std::error_code ignored;
        fs::remove_all(root, ignored); // Test-owned fixture only; production never sweeps.
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
void private_object(const fs::path& path, bool)
{
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

} // namespace

int main()
{
    try {
        basic_publication();
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
        windows_creation_boundary_diagnostics();
        windows_foreign_parent_and_private_children();
        windows_junction_anchor_attack();
        windows_security();
#endif
        std::cout << "record publication tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "record publication test failed: " << error.what() << '\n';
        return 1;
    }
}
