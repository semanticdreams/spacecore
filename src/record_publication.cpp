#include "record_publication.h"
#include "record_publication_operation.h"

#include <array>
#include <atomic>
#include <chrono>
#include <algorithm>
#include <limits>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <system_error>
#include <utility>
#include <vector>

#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#include <aclapi.h>
#include <winternl.h>
#else
#include <cerrno>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/xattr.h>
#include <unistd.h>
#ifdef __APPLE__
#include <sys/acl.h>
#endif
#endif

namespace record_publication {
namespace {

namespace fs = std::filesystem;

[[noreturn]] void fail(const std::string& message)
{
    throw std::runtime_error("record publication: " + message);
}

std::string current_error()
{
    try {
        throw;
    } catch (const std::exception& error) {
        return error.what();
    } catch (...) {
        return "unknown callback/native exception";
    }
}

void append_error(std::optional<std::string>& errors, const std::string& message)
{
    if (errors) {
        errors->append("; " + message);
    } else {
        errors = message;
    }
}

std::string workspace_name()
{
    static std::atomic<unsigned long long> sequence {0};
    return ".record-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count())
        + "-" + std::to_string(sequence.fetch_add(1));
}

#ifndef _WIN32

[[noreturn]] void os_error(const std::string& operation)
{
    const int error = errno;
    fail(operation + ": " + std::error_code(error, std::generic_category()).message());
}

class Handle {
public:
    explicit Handle(int value = -1) : value_(value) {}
    ~Handle() { if (value_ >= 0) ::close(value_); }
    Handle(Handle&& other) noexcept : value_(std::exchange(other.value_, -1)) {}
    Handle& operator=(Handle&& other) noexcept
    {
        if (value_ >= 0) ::close(value_);
        value_ = std::exchange(other.value_, -1);
        return *this;
    }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    int get() const { return value_; }
    void close_checked()
    {
        const int fd = std::exchange(value_, -1);
        // Do not retry close(EINTR): on some hosts the descriptor is already
        // released and a retry could close an unrelated descriptor.
        if (fd >= 0 && ::close(fd) != 0) os_error("close private file/directory");
    }
private:
    int value_;
};

struct stat metadata(int fd)
{
    struct stat value {};
    if (::fstat(fd, &value) != 0) os_error("fstat");
    return value;
}

bool identity(const struct stat& left, const struct stat& right)
{
    return left.st_dev == right.st_dev && left.st_ino == right.st_ino;
}

bool security(const struct stat& left, const struct stat& right)
{
    return left.st_uid == right.st_uid && left.st_gid == right.st_gid
        && left.st_mode == right.st_mode;
}

bool snapshot(const struct stat& left, const struct stat& right)
{
#ifdef __APPLE__
    const bool times = left.st_mtimespec.tv_sec == right.st_mtimespec.tv_sec
        && left.st_mtimespec.tv_nsec == right.st_mtimespec.tv_nsec
        && left.st_ctimespec.tv_sec == right.st_ctimespec.tv_sec
        && left.st_ctimespec.tv_nsec == right.st_ctimespec.tv_nsec;
#else
    const bool times = left.st_mtim.tv_sec == right.st_mtim.tv_sec
        && left.st_mtim.tv_nsec == right.st_mtim.tv_nsec
        && left.st_ctim.tv_sec == right.st_ctim.tv_sec
        && left.st_ctim.tv_nsec == right.st_ctim.tv_nsec;
#endif
    return identity(left, right) && security(left, right) && times
        && left.st_nlink == right.st_nlink && left.st_size == right.st_size;
}

void mode_only(int fd)
{
#ifdef __APPLE__
    acl_t acl = ::acl_get_fd_np(fd, ACL_TYPE_EXTENDED);
    if (acl) {
        if (::acl_valid(acl) != 0) {
            const int error = errno;
            ::acl_free(acl);
            errno = error;
            os_error("validate extended ACL");
        }
        acl_entry_t entry;
        errno = 0;
        const int found = ::acl_get_entry(acl, ACL_FIRST_ENTRY, &entry);
        const int error = errno;
        ::acl_free(acl);
        // Darwin returns0 for an entry and -1/EINVAL when a valid ACL has
        // no first entry (unlike the Linux acl_get_entry return convention).
        if (found == 0) fail("extended ACL policy is unsupported");
        if (found != -1 || error != EINVAL) {
            errno = error;
            os_error("inspect extended ACL");
        }
    } else if (errno != ENOTSUP) {
        os_error("inspect extended ACL");
    }
    const ssize_t count = ::flistxattr(fd, nullptr, 0, 0);
#else
    const ssize_t count = ::flistxattr(fd, nullptr, 0);
#endif
    if (count > 0) fail("extended security/attribute metadata is unsupported");
    // ENOTSUP means this filesystem cannot store such metadata, not that access
    // was denied. Every other inspection failure, including EACCES, is fatal.
    if (count < 0 && errno != ENOTSUP && errno != EOPNOTSUPP) os_error("inspect xattrs");
}

void regular_private_owner(const struct stat& value)
{
    if (!S_ISREG(value.st_mode) || value.st_nlink != 1 || value.st_uid != ::geteuid()
        || (value.st_mode & 07000)) {
        fail("stage must be an owned single-link regular file without special bits");
    }
}

void private_directory(int fd)
{
    const auto value = metadata(fd);
    if (!S_ISDIR(value.st_mode) || value.st_uid != ::geteuid()
        || (value.st_mode & 07777) != 0700) {
        fail("private directory must be owned with exact mode0700");
    }
    mode_only(fd);
}

class Attempt {
public:
    explicit Attempt(const fs::path& destination)
    {
        if (destination.empty() || destination.filename().empty()
            || destination.filename() == "." || destination.filename() == ".."
            || destination.filename() == ".space-publication"
            || destination.native().find('\0') != std::string::npos) fail("invalid destination path");
        const auto absolute = fs::absolute(destination);
        // Aliases are resolved only during acquisition. Every subsequent access
        // is relative to these handles, including creation, rename and cleanup.
        // Writable ancestors therefore cannot redirect private payload bytes.
        parent_ = Handle(::open(absolute.parent_path().c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC));
        if (parent_.get() < 0) os_error("pin target parent");
        mode_only(parent());
        name_ = absolute.filename().native();
        destination_ = read_destination();
    }

    ~Attempt() noexcept
    {
        if (!cleaned_) {
            try { cleanup(); } catch (...) {} // Explicit cleanup reports all normal errors.
        }
    }

    void prepare()
    {
        if (::mkdirat(parent(), ".space-publication", 0700) != 0 && errno != EEXIST)
            os_error("create persistent private anchor");
        anchor_ = acquire_directory(parent(), ".space-publication", anchor_id_);
        for (int tries = 0; tries < 64; ++tries) {
            workspace_name_ = workspace_name();
            if (::mkdirat(anchor_.get(), workspace_name_.c_str(), 0700) == 0) {
                owned_ = true;
                break;
            }
            if (errno != EEXIST) os_error("create private workspace");
        }
        if (!owned_) fail("cannot allocate exclusive workspace");
        workspace_ = acquire_directory(anchor_.get(), workspace_name_.c_str(), workspace_id_);
        validate_workspace();
        record_ = Handle(::openat(workspace_.get(), "record",
            O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600));
        if (record_.get() < 0) os_error("create private record");
        record_id_ = metadata(record_.get());
        validate_private_record();
    }

    bool owns_workspace() const { return owned_; }

    void write(std::string_view bytes)
    {
        validate_workspace();
        validate_private_record();
        Handle writer(::fcntl(record_.get(), F_DUPFD_CLOEXEC, 0));
        if (writer.get() < 0) os_error("retain writer descriptor");
        std::size_t offset = 0;
        while (offset < bytes.size()) {
            const auto size = std::min(bytes.size() - offset, std::size_t(65536));
            const ssize_t count = ::write(writer.get(), bytes.data() + offset, size);
            if (count < 0) {
                if (errno == EINTR) continue;
                os_error("write private record");
            }
            if (count == 0 || static_cast<std::size_t>(count) > size)
                fail("private record write made invalid progress");
            offset += static_cast<std::size_t>(count);
        }
        if (::fsync(writer.get()) != 0) os_error("flush private record");
        writer.close_checked();
        verify_bytes(bytes);
    }

    void secure(std::string_view bytes)
    {
        validate_workspace();
        validate_private_record();
        const auto value = metadata(record_.get());
        struct stat named {};
        if (::fstatat(workspace_.get(), "record", &named, AT_SYMLINK_NOFOLLOW) != 0)
            os_error("inspect native record name");
        regular_private_owner(value);
        if (!record_id_ || !identity(*record_id_, value) || !identity(named, value)) fail("stage identity changed");
        verify_bytes(bytes);
        mode_only(record_.get());
        const uid_t uid = destination_ ? destination_->st_uid : ::geteuid();
        const gid_t gid = destination_ ? destination_->st_gid : value.st_gid;
        const mode_t mode = destination_ ? destination_->st_mode & 0777 : 0600;
        if ((value.st_uid != uid || value.st_gid != gid)
            && ::fchown(record_.get(), uid, gid) != 0) os_error("reproduce owner/group");
        if (::fchmod(record_.get(), mode) != 0) os_error("prepare final mode");
        final_ = metadata(record_.get());
        if (final_->st_uid != uid || final_->st_gid != gid || (final_->st_mode & 07777) != mode)
            fail("final owner/group/mode reproduction failed");
        mode_only(record_.get());
    }

    void validate(std::string_view bytes)
    {
        validate_workspace();
        struct stat named {};
        if (::fstatat(workspace_.get(), "record", &named, AT_SYMLINK_NOFOLLOW) != 0)
            os_error("revalidate stage name");
        const auto value = metadata(record_.get());
        if (!identity(named, value) || !final_ || !snapshot(*final_, value)
            || !S_ISREG(value.st_mode) || value.st_nlink != 1) fail("stage identity/security changed");
        mode_only(record_.get());
        verify_bytes(bytes);
        if (::fsync(record_.get()) != 0) os_error("flush final record policy");
        const auto current = read_destination();
        if (current.has_value() != destination_.has_value()
            || (current && !snapshot(*destination_, *current))) fail("destination identity/security changed");
    }

    void commit()
    {
        if (::renameat(workspace_.get(), "record", parent(), name_.c_str()) != 0)
            os_error("atomic renameat publication");
    }

    std::optional<std::string> cleanup()
    {
        cleaned_ = true;
        std::optional<std::string> errors;
        if (!owned_) return errors;
        if (workspace_.get() < 0 || !workspace_id_) {
            append_error(errors, "workspace identity unavailable; left untouched");
            return errors;
        }
        try {
            private_directory(anchor_.get());
            private_directory(workspace_.get());
            if (!anchor_id_ || !identity(metadata(anchor_.get()), *anchor_id_)
                || !identity(metadata(workspace_.get()), *workspace_id_))
                fail("private cleanup namespace identity changed");
        } catch (...) {
            append_error(errors, current_error());
            return errors;
        }
        cleanup_entry("record", record_id_, errors);
        struct stat named {};
        if (::fstatat(anchor_.get(), workspace_name_.c_str(), &named, AT_SYMLINK_NOFOLLOW) != 0
            || !identity(named, *workspace_id_)) {
            append_error(errors, "workspace identity changed; directory left untouched");
        } else if (::unlinkat(anchor_.get(), workspace_name_.c_str(), AT_REMOVEDIR) != 0) {
            append_error(errors, "remove workspace: " + std::error_code(errno, std::generic_category()).message());
        }
        for (Handle* handle : {&record_, &workspace_, &anchor_, &parent_}) {
            try { handle->close_checked(); }
            catch (...) { append_error(errors, current_error()); }
        }
        return errors;
    }

private:
    int parent() const { return parent_.get(); }

    Handle acquire_directory(int parent, const char* name, std::optional<struct stat>& expected)
    {
        struct stat named {};
        if (::fstatat(parent, name, &named, AT_SYMLINK_NOFOLLOW) != 0) os_error("inspect private directory");
        Handle handle(::openat(parent, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
        if (handle.get() < 0) os_error("open private directory");
        private_directory(handle.get());
        const auto value = metadata(handle.get());
        if (!identity(named, value)) fail("private directory acquisition identity changed");
        expected = value;
        return handle;
    }

    void validate_workspace()
    {
        // Identity is device/inode, not volatile timestamps or directory link
        // counts: independent attempts may add/remove children concurrently.
        struct stat named {};
        if (::fstatat(parent(), ".space-publication", &named, AT_SYMLINK_NOFOLLOW) != 0)
            os_error("revalidate anchor name");
        if (!anchor_id_ || !identity(named, *anchor_id_)
            || !identity(metadata(anchor_.get()), *anchor_id_)) fail("anchor identity changed");
        private_directory(anchor_.get());
        if (::fstatat(anchor_.get(), workspace_name_.c_str(), &named, AT_SYMLINK_NOFOLLOW) != 0)
            os_error("revalidate workspace");
        const auto value = metadata(workspace_.get());
        if (!workspace_id_ || !identity(named, *workspace_id_) || !identity(value, *workspace_id_)
            || !S_ISDIR(value.st_mode) || value.st_uid != ::geteuid()
            || (value.st_mode & 07777) != 0700) fail("workspace identity/privacy changed");
        private_directory(workspace_.get());
    }

    std::optional<struct stat> read_destination()
    {
        Handle fd(::openat(parent(), name_.c_str(), O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC));
        if (fd.get() < 0) {
            if (errno == ENOENT) return std::nullopt;
            os_error("inspect destination");
        }
        const auto value = metadata(fd.get());
        if (!S_ISREG(value.st_mode) || value.st_nlink != 1 || (value.st_mode & 07000))
            fail("destination must be a single-link regular mode-only file without special bits");
        mode_only(fd.get());
        return value;
    }

    void verify_bytes(std::string_view bytes)
    {
        std::array<char, 65536> buffer;
        std::size_t offset = 0;
        for (;;) {
            const ssize_t count = ::pread(record_.get(), buffer.data(), buffer.size(), offset);
            if (count < 0) {
                if (errno == EINTR) continue;
                os_error("verify stage bytes");
            }
            if (count == 0) break;
            if (static_cast<std::size_t>(count) > bytes.size() - offset
                || std::memcmp(buffer.data(), bytes.data() + offset, count) != 0)
                fail("stage bytes differ from expected bytes");
            offset += count;
        }
        if (offset != bytes.size()) fail("stage byte length differs from expected bytes");
    }

    void cleanup_entry(const char* name, const std::optional<struct stat>& expected,
                       std::optional<std::string>& errors)
    {
        struct stat value {};
        if (::fstatat(workspace_.get(), name, &value, AT_SYMLINK_NOFOLLOW) != 0) {
            if (errno != ENOENT) append_error(errors, std::string("inspect cleanup entry: ") + name);
            return;
        }
        if (!expected || !identity(value, *expected) || !S_ISREG(value.st_mode) || value.st_nlink != 1) {
            append_error(errors, std::string("unowned/substituted cleanup entry left untouched: ") + name);
            return;
        }
        if (::unlinkat(workspace_.get(), name, 0) != 0)
            append_error(errors, std::string("remove owned entry failed: ") + name);
    }

    void validate_private_record()
    {
        const auto value = metadata(record_.get());
        regular_private_owner(value);
        struct stat named {};
        if (::fstatat(workspace_.get(), "record", &named, AT_SYMLINK_NOFOLLOW) != 0)
            os_error("inspect private record name");
        if (!record_id_ || !identity(value, *record_id_) || !identity(named, value)
            || (value.st_mode & 07777) != 0600) fail("private record identity/privacy changed");
        mode_only(record_.get());
    }

    std::string name_, workspace_name_;
    Handle parent_, anchor_, workspace_, record_;
    std::optional<struct stat> destination_, anchor_id_, workspace_id_, record_id_, final_;
    bool owned_ = false, cleaned_ = false;
};

#else

// Windows deliberately uses native handles/security descriptors, never CRT
// rename, copy fallbacks, or process-wide privilege/security-policy changes.
[[noreturn]] void win_error(const std::string& operation, DWORD error = ::GetLastError())
{
    fail(operation + ": " + std::error_code(error, std::system_category()).message());
}

std::wstring native_path(const fs::path& path)
{
    // All callers supply verified absolute drive paths, not UNC/device aliases.
    // Use long-path native spelling so a long basename does not reintroduce a
    // MAX_PATH-dependent publication fallback.
    fs::path preferred = path;
    preferred.make_preferred();
    return L"\\\\?\\" + preferred.native();
}

using Blob = std::vector<unsigned char>;

struct DescriptorInput {
    bool present = false, valid = false;
    const char* owner_match = "unavailable";
    const char* protected_dacl = "unavailable";
    const char* dacl_present = "unavailable";
    const char* dacl_valid = "unavailable";
    const char* dacl_match = "unavailable";
    std::optional<DWORD> dacl_bytes, ace_count;

    std::string metrics() const
    {
        return std::string("{sd-present=") + (present ? "true" : "false")
            + " sd-valid=" + (valid ? "true" : "false") + " owner-match=" + owner_match
            + " protected=" + protected_dacl + " dacl-present=" + dacl_present
            + " dacl-valid=" + dacl_valid + " dacl-match=" + dacl_match
            + " dacl-bytes=" + (dacl_bytes ? std::to_string(*dacl_bytes) : "unavailable")
            + " ace-count=" + (ace_count ? std::to_string(*ace_count) : "unavailable") + "}";
    }
};

DescriptorInput diagnostic_input(PSECURITY_DESCRIPTOR descriptor, const Blob& owner, const Blob& expected_dacl)
{
    // Read only the actual OBJECT_ATTRIBUTES input. These observations neither
    // validate for acceptance nor change policy; failed diagnostic queries stay
    // explicitly unavailable. Preserve the native operation's error context.
    const DWORD saved_error = ::GetLastError();
    DescriptorInput input;
    input.present = descriptor != nullptr;
    input.valid = descriptor && ::IsValidSecurityDescriptor(descriptor);
    if (input.valid) {
        PSID actual_owner = nullptr;
        BOOL defaulted = FALSE, present = FALSE;
        PACL dacl = nullptr;
        SECURITY_DESCRIPTOR_CONTROL control = 0;
        DWORD revision = 0;
        if (::GetSecurityDescriptorOwner(descriptor, &actual_owner, &defaulted)
            && actual_owner && ::IsValidSid(actual_owner)) {
            input.owner_match = ::EqualSid(actual_owner, const_cast<unsigned char*>(owner.data())) ? "true" : "false";
        }
        if (::GetSecurityDescriptorControl(descriptor, &control, &revision))
            input.protected_dacl = (control & SE_DACL_PROTECTED) ? "true" : "false";
        if (::GetSecurityDescriptorDacl(descriptor, &present, &dacl, &defaulted)) {
            input.dacl_present = present ? "true" : "false";
            const bool valid_dacl = present && dacl && ::IsValidAcl(dacl);
            input.dacl_valid = valid_dacl ? "true" : "false";
            if (valid_dacl) {
                input.dacl_bytes = dacl->AclSize;
                input.ace_count = dacl->AceCount;
                input.dacl_match = dacl->AclSize == expected_dacl.size()
                    && std::memcmp(dacl, expected_dacl.data(), expected_dacl.size()) == 0 ? "true" : "false";
            }
        }
    }
    ::SetLastError(saved_error);
    return input;
}

struct Acquisition {
    unsigned long long attempt_id = 0, id = 0;
    const char* phase = "acquire";
    const char* kind = "uncompleted";
    DescriptorInput input;
    bool complete = false, file_created = false, initial_private = false;
    struct Collision { unsigned long long id; DescriptorInput input; };
    std::optional<Collision> collision;
};

class Handle {
public:
    explicit Handle(HANDLE value = INVALID_HANDLE_VALUE, Acquisition acquisition = {})
        : value_(value), acquisition_(std::move(acquisition)) {}
    ~Handle() { close(); }
    Handle(Handle&& other) noexcept
        : value_(std::exchange(other.value_, INVALID_HANDLE_VALUE)), acquisition_(std::move(other.acquisition_)) {}
    Handle& operator=(Handle&& other) noexcept
    {
        close();
        value_ = std::exchange(other.value_, INVALID_HANDLE_VALUE);
        acquisition_ = std::move(other.acquisition_);
        return *this;
    }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    HANDLE get() const { return value_; }
    const Acquisition& acquisition() const { return acquisition_; }
    void note_completion(bool create, ULONG_PTR information)
    {
        acquisition_.complete = true;
        acquisition_.file_created = information == 2; // FILE_CREATED, from checked completion only.
        acquisition_.kind = create ? "exclusive-create" : "open";
    }
    void note_collision(const Acquisition& collision)
    {
        acquisition_.collision = Acquisition::Collision {collision.id, collision.input};
        acquisition_.kind = "collision-reopen";
    }
    void note_initial_private() { acquisition_.initial_private = true; }
    void close() noexcept
    {
        if (value_ != INVALID_HANDLE_VALUE && value_ != nullptr) ::CloseHandle(value_);
        value_ = INVALID_HANDLE_VALUE;
    }
    void close_checked()
    {
        const HANDLE handle = std::exchange(value_, INVALID_HANDLE_VALUE);
        if (handle != INVALID_HANDLE_VALUE && handle != nullptr && !::CloseHandle(handle))
            win_error("close private handle");
    }
private:
    HANDLE value_;
    Acquisition acquisition_;
};

struct LocalMemory {
    HLOCAL value = nullptr;
    ~LocalMemory() { if (value) ::LocalFree(value); }
};

Blob copy_sid(PSID sid)
{
    if (!sid || !::IsValidSid(sid)) fail("invalid/uninspectable owner/group SID");
    const auto size = ::GetLengthSid(sid);
    Blob result(size);
    if (!::CopySid(size, result.data(), sid)) win_error("copy SID");
    return result;
}

struct Policy {
    Blob owner, group, dacl;
    bool protected_dacl = false;
};

std::string diagnostic_ace_count(const Blob& bytes)
{
    // Diagnostics must not introduce an out-of-bounds ACL header/ACE read.
    if (bytes.size() < sizeof(ACL)) return "unavailable";
    ACL header {};
    std::memcpy(&header, bytes.data(), sizeof(header));
    if (header.AclSize < sizeof(ACL) || header.AclSize > bytes.size()
        || !::IsValidAcl(reinterpret_cast<PACL>(const_cast<unsigned char*>(bytes.data())))) return "invalid";
    return std::to_string(header.AceCount);
}

Policy inspect_policy(HANDLE handle)
{
    PSID owner = nullptr, group = nullptr;
    PACL dacl = nullptr;
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    LocalMemory memory;
    const DWORD error = ::GetSecurityInfo(handle, SE_FILE_OBJECT,
        OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
        &owner, &group, &dacl, nullptr, &descriptor);
    memory.value = descriptor;
    if (error != ERROR_SUCCESS) win_error("inspect owner/group/DACL", error);
    if (!dacl || !::IsValidAcl(dacl)) fail("absent/null/invalid DACL is unsupported");
    for (DWORD index = 0; index < dacl->AceCount; ++index) {
        void* raw = nullptr;
        if (!::GetAce(dacl, index, &raw)) win_error("inspect DACL ACE");
        const auto* ace = static_cast<ACE_HEADER*>(raw);
        if (ace->AceType != ACCESS_ALLOWED_ACE_TYPE && ace->AceType != ACCESS_DENIED_ACE_TYPE)
            fail("only ordinary allow/deny DACL ACEs are supported");
    }
    SECURITY_DESCRIPTOR_CONTROL control = 0;
    DWORD revision = 0;
    if (!::GetSecurityDescriptorControl(descriptor, &control, &revision)) win_error("inspect DACL control");
    Policy policy {copy_sid(owner), copy_sid(group), Blob(dacl->AclSize), (control & SE_DACL_PROTECTED) != 0};
    std::memcpy(policy.dacl.data(), dacl, dacl->AclSize);
    // Selective queries do not request an audit SACL or enable SeSecurityPrivilege.
    // These are the documented LABEL, ATTRIBUTE, SCOPE, PROCESS_TRUST_LABEL and
    // ACCESS_FILTER_SECURITY_INFORMATION values. An unsupported/denied query
    // fails closed, including on older hosts; no platform floor is assumed.
    for (const SECURITY_INFORMATION information : {0x10UL, 0x20UL, 0x40UL, 0x80UL, 0x100UL}) {
        PACL sacl = nullptr;
        PSECURITY_DESCRIPTOR extra = nullptr;
        LocalMemory extra_memory;
        const DWORD status = ::GetSecurityInfo(handle, SE_FILE_OBJECT, information,
            nullptr, nullptr, nullptr, &sacl, &extra);
        extra_memory.value = extra;
        if (status != ERROR_SUCCESS) win_error("inspect selective security policy", status);
        if (sacl && (!::IsValidAcl(sacl) || sacl->AceCount != 0))
            fail("explicit label/resource/scoped/trust/access-filter policy is unsupported");
    }
    return policy;
}

bool same_policy(const Policy& left, const Policy& right, bool allow_protection = false)
{
    return left.owner == right.owner && left.group == right.group && left.dacl == right.dacl
        && (left.protected_dacl == right.protected_dacl || (allow_protection && right.protected_dacl));
}

BY_HANDLE_FILE_INFORMATION metadata(HANDLE handle, bool directory = false)
{
    BY_HANDLE_FILE_INFORMATION value {};
    if (!::GetFileInformationByHandle(handle, &value)) win_error("inspect file identity");
    if (::GetFileType(handle) != FILE_TYPE_DISK
        || (value.dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_ENCRYPTED))
        || static_cast<bool>(value.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != directory
        || (!directory && value.nNumberOfLinks != 1)) fail("unsupported reparse/EFS/nonregular/multiple-link object");
    return value;
}

bool identity(const BY_HANDLE_FILE_INFORMATION& left, const BY_HANDLE_FILE_INFORMATION& right)
{
    return left.dwVolumeSerialNumber == right.dwVolumeSerialNumber
        && left.nFileIndexHigh == right.nFileIndexHigh && left.nFileIndexLow == right.nFileIndexLow;
}

bool snapshot(const BY_HANDLE_FILE_INFORMATION& left, const BY_HANDLE_FILE_INFORMATION& right)
{
    return identity(left, right) && left.nNumberOfLinks == right.nNumberOfLinks
        && left.dwFileAttributes == right.dwFileAttributes
        && left.nFileSizeHigh == right.nFileSizeHigh && left.nFileSizeLow == right.nFileSizeLow
        && ::CompareFileTime(&left.ftLastWriteTime, &right.ftLastWriteTime) == 0;
}

// This is the Native FILE_RENAME_INFORMATION ABI, not Win32
// FILE_RENAME_INFO (whose RootDirectory is documented as always NULL).
struct NativeRenameInformation {
    BOOLEAN ReplaceIfExists;
    HANDLE RootDirectory;
    ULONG FileNameLength;
    WCHAR FileName[1];
};
static_assert(offsetof(NativeRenameInformation, RootDirectory) == sizeof(void*));
static_assert(offsetof(NativeRenameInformation, FileName) == 2 * sizeof(void*) + sizeof(ULONG));

class NativeFiles {
public:
    using Create = NTSTATUS (NTAPI*)(PHANDLE, ACCESS_MASK, POBJECT_ATTRIBUTES,
        PIO_STATUS_BLOCK, PLARGE_INTEGER, ULONG, ULONG, ULONG, ULONG, PVOID, ULONG);
    using SetInformation = NTSTATUS (NTAPI*)(HANDLE, PIO_STATUS_BLOCK, PVOID, ULONG, FILE_INFORMATION_CLASS);
    using StatusError = ULONG (NTAPI*)(NTSTATUS);
    using Wait = NTSTATUS (NTAPI*)(HANDLE, BOOLEAN, PLARGE_INTEGER);

    NativeFiles(const Blob& owner, const Blob& private_acl) : owner_(owner), private_acl_(private_acl)
    {
        const HMODULE module = ::GetModuleHandleW(L"ntdll.dll");
        if (!module) win_error("load existing ntdll");
        create_ = reinterpret_cast<Create>(::GetProcAddress(module, "NtCreateFile"));
        set_ = reinterpret_cast<SetInformation>(::GetProcAddress(module, "NtSetInformationFile"));
        status_error_ = reinterpret_cast<StatusError>(::GetProcAddress(module, "RtlNtStatusToDosError"));
        wait_ = reinterpret_cast<Wait>(::GetProcAddress(module, "NtWaitForSingleObject"));
        if (!create_ || !set_ || !status_error_ || !wait_) fail("required ntdll file operations unavailable");
    }

    void set_phase(const char* phase) { phase_ = phase; }
    const char* phase() const { return phase_; }

    Handle relative(HANDLE root, const std::wstring& name, bool directory, bool create,
                    ACCESS_MASK access, PSECURITY_DESCRIPTOR security = nullptr,
                    bool* collision = nullptr, bool* missing = nullptr)
    {
        if (name.empty() || name == L"." || name == L".." || name.find_first_of(L"\\/:") != std::wstring::npos
            || name.find(L'\0') != std::wstring::npos
            || name.size() > std::numeric_limits<USHORT>::max() / sizeof(WCHAR)) fail("invalid relative Native leaf");
        UNICODE_STRING unicode {};
        unicode.Length = static_cast<USHORT>(name.size() * sizeof(WCHAR));
        unicode.MaximumLength = unicode.Length;
        unicode.Buffer = const_cast<PWSTR>(name.data());
        OBJECT_ATTRIBUTES attributes {};
        attributes.Length = sizeof(attributes);
        attributes.RootDirectory = root;
        attributes.ObjectName = &unicode;
        attributes.Attributes = 0x40; // OBJ_CASE_INSENSITIVE
        attributes.SecurityDescriptor = security;
        IO_STATUS_BLOCK completion {};
        HANDLE raw = INVALID_HANDLE_VALUE;
        // FILE_CREATE=2 / FILE_OPEN=1. FILE_DIRECTORY_FILE=1 /
        // FILE_NON_DIRECTORY_FILE=0x40; FILE_SYNCHRONOUS_IO_NONALERT=0x20
        // requires SYNCHRONIZE. FILE_OPEN_REPARSE_POINT=0x200000 opens the
        // entry itself, which metadata then refuses if it is a reparse point.
        Acquisition acquisition;
        acquisition.attempt_id = attempt_id_;
        acquisition.id = ++acquisition_sequence_;
        acquisition.phase = phase_;
        acquisition.input = diagnostic_input(attributes.SecurityDescriptor, owner_, private_acl_);
        const NTSTATUS status = create_(&raw, access | SYNCHRONIZE, &attributes, &completion,
            nullptr, FILE_ATTRIBUTE_NORMAL, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            create ? 2 : 1, (directory ? 1 : 0x40) | 0x20 | 0x200000, nullptr, 0);
        if (collision && status == static_cast<NTSTATUS>(0xC0000035UL)) {
            *collision = true;
            return Handle(INVALID_HANDLE_VALUE, std::move(acquisition));
        }
        if (missing && status == static_cast<NTSTATUS>(0xC0000034UL)) { *missing = true; return Handle(); }
        Handle result(raw, std::move(acquisition));
        complete(status, raw, completion, "NtCreateFile relative acquisition");
        if (create && completion.Information != 2) fail("exclusive Native creation did not create a new object");
        result.note_completion(create, completion.Information);
        metadata(result.get(), directory);
        return result;
    }

    void information(HANDLE source, void* data, ULONG length, FILE_INFORMATION_CLASS kind,
                     const char* operation) const
    {
        IO_STATUS_BLOCK completion {};
        const NTSTATUS status = set_(source, &completion, data, length, kind);
        complete(status, source, completion, operation);
    }

private:
    static unsigned long long next_attempt_id()
    {
        static std::atomic<unsigned long long> sequence {0};
        return sequence.fetch_add(1) + 1;
    }

    void complete(NTSTATUS status, HANDLE handle, const IO_STATUS_BLOCK& completion, const char* operation) const
    {
        if (status == 0x103) { // STATUS_PENDING is not a completed operation.
            const NTSTATUS waited = wait_(handle, FALSE, nullptr);
            if (waited != 0) win_error("await Native file completion", status_error_(waited));
            status = completion.Status;
            if (status == 0x103) fail(std::string(operation) + ": completion remained pending");
        }
        if (status < 0) win_error(operation, status_error_(status));
        if (completion.Status < 0) win_error(operation, status_error_(completion.Status));
        if (completion.Status == 0x103) fail(std::string(operation) + ": incomplete status block");
    }
    Create create_ = nullptr;
    SetInformation set_ = nullptr;
    StatusError status_error_ = nullptr;
    Wait wait_ = nullptr;
    const Blob& owner_;
    const Blob& private_acl_;
    const unsigned long long attempt_id_ = next_attempt_id();
    unsigned long long acquisition_sequence_ = 0;
    const char* phase_ = "acquire";
};

class Attempt {
public:
    explicit Attempt(const fs::path& destination)
    {
        if (destination.empty() || destination.filename().empty() || destination.filename() == L"."
            || destination.filename() == L".." || destination.native().find(L'\0') != std::wstring::npos
            || destination.filename().native().find(L':') != std::wstring::npos)
            fail("invalid destination path/alternate stream");
        if (::_wcsicmp(destination.filename().c_str(), L".space-publication") == 0)
            fail("reserved publication anchor destination");
        const auto absolute = fs::absolute(destination).lexically_normal();
        const auto parent_path = absolute.parent_path();
        name_ = absolute.filename().native();
        if (parent_path.native().rfind(L"\\\\", 0) == 0) fail("remote/device ancestry is unsupported");
        HANDLE raw_token = nullptr;
        if (!::OpenThreadToken(::GetCurrentThread(), TOKEN_QUERY, TRUE, &raw_token)) {
            if (::GetLastError() != ERROR_NO_TOKEN) win_error("open effective thread token");
            if (!::OpenProcessToken(::GetCurrentProcess(), TOKEN_QUERY, &raw_token)) win_error("open process token");
        }
        Handle token(raw_token);
        DWORD size = 0;
        ::GetTokenInformation(token.get(), TokenUser, nullptr, 0, &size);
        if (::GetLastError() != ERROR_INSUFFICIENT_BUFFER) win_error("size token owner");
        Blob data(size);
        if (!::GetTokenInformation(token.get(), TokenUser, data.data(), size, &size)) win_error("read effective token user");
        owner_ = copy_sid(reinterpret_cast<TOKEN_USER*>(data.data())->User.Sid);
        parent_ = Handle(::CreateFileW(native_path(parent_path).c_str(), directory_access,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
        if (parent_.get() == INVALID_HANDLE_VALUE) win_error("pin target parent");
        parent_id_ = metadata(parent_.get(), true);
        inspect_policy(parent_.get());
        std::array<wchar_t, MAX_PATH + 1> volume {};
        if (!::GetVolumePathNameW(parent_path.c_str(), volume.data(), volume.size())) win_error("inspect local volume");
        const UINT type = ::GetDriveTypeW(volume.data());
        DWORD flags = 0;
        if ((type != DRIVE_FIXED && type != DRIVE_REMOVABLE)
            || !::GetVolumeInformationW(volume.data(), nullptr, 0, nullptr, nullptr, &flags, nullptr, 0))
            fail("local filesystem semantics unavailable");
        if (!(flags & FILE_PERSISTENT_ACLS)) fail("persistent ACL filesystem required");
        auto destination_handle = optional_destination();
        if (destination_handle.get() != INVALID_HANDLE_VALUE) {
            destination_ = metadata(destination_handle.get());
            destination_policy_ = inspect_policy(destination_handle.get());
        }
    }

    ~Attempt() noexcept
    {
        if (!cleaned_) { try { cleanup(); } catch (...) {} }
    }

    void prepare()
    {
        native_.set_phase("initial-prepare");
        private_acl_.resize(sizeof(ACL) + sizeof(ACCESS_ALLOWED_ACE) - sizeof(DWORD) + owner_.size());
        auto* dacl = reinterpret_cast<PACL>(private_acl_.data());
        if (!::InitializeAcl(dacl, private_acl_.size(), ACL_REVISION)
            || !::AddAccessAllowedAceEx(dacl, ACL_REVISION, OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE,
                FILE_ALL_ACCESS, owner_.data())) win_error("construct owner-only DACL");
        SECURITY_DESCRIPTOR descriptor;
        if (!::InitializeSecurityDescriptor(&descriptor, SECURITY_DESCRIPTOR_REVISION)
            || !::SetSecurityDescriptorOwner(&descriptor, owner_.data(), FALSE)
            || !::SetSecurityDescriptorDacl(&descriptor, TRUE, dacl, FALSE)
            || !::SetSecurityDescriptorControl(&descriptor, SE_DACL_PROTECTED, SE_DACL_PROTECTED))
            win_error("construct private security descriptor");
        bool collision = false;
        anchor_ = native_.relative(parent_.get(), L".space-publication", true, true,
            directory_access, &descriptor, &collision);
        if (collision) {
            auto reopened = native_.relative(parent_.get(), L".space-publication", true, false, directory_access);
            reopened.note_collision(anchor_.acquisition());
            anchor_ = std::move(reopened);
        }
        anchor_id_ = metadata(anchor_.get(), true);
        require_private(inspect_policy(anchor_.get()), "anchor", anchor_, true);
        for (int tries = 0; tries < 64; ++tries) {
            workspace_name_ = fs::path(workspace_name()).wstring();
            collision = false;
            workspace_ = native_.relative(anchor_.get(), workspace_name_, true, true,
                directory_access | DELETE, &descriptor, &collision);
            if (!collision) { owned_ = true; break; }
        }
        if (!owned_) fail("cannot allocate exclusive workspace");
        workspace_id_ = metadata(workspace_.get(), true);
        require_private(inspect_policy(workspace_.get()), "attempt", workspace_, true);
        record_ = native_.relative(workspace_.get(), L"record", false, true,
            GENERIC_READ | GENERIC_WRITE | READ_CONTROL | WRITE_DAC | WRITE_OWNER | DELETE, &descriptor);
        record_id_ = metadata(record_.get());
        require_private(inspect_policy(record_.get()), "record", record_, true);
        validate_workspace();
    }

    bool owns_workspace() const { return owned_; }

    void write(std::string_view bytes)
    {
        native_.set_phase("write-validation");
        validate_workspace();
        validate_record_name();
        require_private(inspect_policy(record_.get()), "record", record_);
        std::size_t offset = 0;
        while (offset < bytes.size()) {
            DWORD count = 0;
            const auto size = static_cast<DWORD>(std::min(bytes.size() - offset, std::size_t(65536)));
            if (!::WriteFile(record_.get(), bytes.data() + offset, size, &count, nullptr)) win_error("write private record");
            if (!count || count > size) fail("private record write completion made invalid progress");
            offset += count;
        }
        if (!::FlushFileBuffers(record_.get())) win_error("flush private record");
        verify_bytes(bytes);
    }

    void secure(std::string_view bytes)
    {
        native_.set_phase("security-validation");
        validate_workspace();
        validate_record_name();
        const auto policy = inspect_policy(record_.get());
        require_private(policy, "record", record_);
        verify_bytes(bytes);
        if (destination_policy_) {
            auto& desired = *destination_policy_;
            const DWORD error = ::SetSecurityInfo(record_.get(), SE_FILE_OBJECT,
                OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
                    | PROTECTED_DACL_SECURITY_INFORMATION,
                desired.owner.data(), desired.group.data(), reinterpret_cast<PACL>(desired.dacl.data()), nullptr);
            if (error != ERROR_SUCCESS) win_error("reproduce destination owner/group/DACL", error);
            final_policy_ = inspect_policy(record_.get());
            if (!same_policy(desired, *final_policy_, true)) fail("final destination policy reproduction failed");
        } else {
            const DWORD error = ::SetSecurityInfo(record_.get(), SE_FILE_OBJECT,
                DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                nullptr, nullptr, reinterpret_cast<PACL>(const_cast<unsigned char*>(policy.dacl.data())), nullptr);
            if (error != ERROR_SUCCESS) win_error("protect new record DACL", error);
            final_policy_ = inspect_policy(record_.get());
            if (!same_policy(policy, *final_policy_, true)) fail("new record policy reproduction failed");
        }
        final_ = metadata(record_.get());
    }

    void validate(std::string_view bytes)
    {
        native_.set_phase("commit-validation");
        validate_workspace();
        validate_record_name();
        const auto value = metadata(record_.get());
        if (!final_ || !snapshot(*final_, value)
            || !same_policy(*final_policy_, inspect_policy(record_.get()))) fail("stage identity/security changed");
        verify_bytes(bytes);
        auto current = optional_destination();
        if ((current.get() != INVALID_HANDLE_VALUE) != destination_.has_value()) fail("destination existence changed");
        if (destination_ && (!snapshot(*destination_, metadata(current.get()))
            || !same_policy(*destination_policy_, inspect_policy(current.get()))))
            fail("destination identity/security changed");
        if (value.dwVolumeSerialNumber != parent_id_.dwVolumeSerialNumber)
            fail("cross-volume publication is forbidden");
    }

    void commit()
    {
        const auto bytes = name_.size() * sizeof(WCHAR);
        const auto size = offsetof(NativeRenameInformation, FileName) + bytes;
        if (size > std::numeric_limits<ULONG>::max()) fail("Native rename name too long");
        Blob storage(std::max(size, sizeof(NativeRenameInformation)), 0);
        auto* rename = reinterpret_cast<NativeRenameInformation*>(storage.data());
        rename->ReplaceIfExists = destination_.has_value();
        rename->RootDirectory = parent_.get();
        rename->FileNameLength = static_cast<ULONG>(bytes);
        std::memcpy(rename->FileName, name_.data(), bytes);
        native_.information(record_.get(), rename, static_cast<ULONG>(size),
            static_cast<FILE_INFORMATION_CLASS>(10), "atomic NtSetInformationFile rename");
    }

    std::optional<std::string> cleanup()
    {
        native_.set_phase("cleanup");
        cleaned_ = true;
        std::optional<std::string> errors;
        if (!owned_) return errors;
        try {
            auto named = native_.relative(anchor_.get(), workspace_name_, true, false, directory_access);
            if (!workspace_id_ || !identity(metadata(named.get(), true), *workspace_id_))
                fail("workspace identity changed; left untouched");
            require_private(inspect_policy(anchor_.get()), "anchor", anchor_);
            require_private(inspect_policy(workspace_.get()), "attempt", workspace_);
            cleanup_entry(errors);
            record_.close_checked(); // Complete delete-pending children first.
            BOOLEAN remove = TRUE; // FILE_DISPOSITION_INFORMATION.DeleteFile
            native_.information(workspace_.get(), &remove, sizeof(remove),
                static_cast<FILE_INFORMATION_CLASS>(13), "remove owned attempt by handle");
        } catch (...) { append_error(errors, current_error()); return errors; }
        for (Handle* handle : {&workspace_, &anchor_, &parent_}) {
            try { handle->close_checked(); }
            catch (...) { append_error(errors, current_error()); }
        }
        return errors;
    }

private:
    Handle optional_destination()
    {
        bool missing = false;
        return native_.relative(parent_.get(), name_, false, false,
            READ_CONTROL | FILE_READ_ATTRIBUTES | FILE_READ_DATA, nullptr, nullptr, &missing);
    }

    std::string private_policy_metrics(const Policy& policy, const char* role, const Handle& handle, bool initial) const
    {
        const auto& acquisition = handle.acquisition();
        std::string metrics = std::string("role=") + role
            + " owner-match=" + (policy.owner == owner_ ? "true" : "false")
            + " expected-protected=true actual-protected=" + (policy.protected_dacl ? "true" : "false")
            + " dacl-match=" + (policy.dacl == private_acl_ ? "true" : "false")
            + " expected-dacl-bytes=" + std::to_string(private_acl_.size())
            + " actual-dacl-bytes=" + std::to_string(policy.dacl.size())
            + " expected-ace-count=" + diagnostic_ace_count(private_acl_)
            + " actual-ace-count=" + diagnostic_ace_count(policy.dacl)
            + " attempt-id=" + std::to_string(acquisition.attempt_id)
            + " phase=" + native_.phase()
            + " initial-private=" + (initial ? "refused" : acquisition.initial_private ? "accepted" : "unobserved")
            + " acquisition-id=" + std::to_string(acquisition.id)
            + " acquisition-phase=" + acquisition.phase
            + " acquisition=" + acquisition.kind
            + " native-complete=" + (acquisition.complete ? "true" : "false")
            + " file-created=" + (acquisition.file_created ? "true" : "false")
            + " input" + acquisition.input.metrics();
        if (acquisition.collision) {
            metrics += " collision-id=" + std::to_string(acquisition.collision->id)
                + " collision-input" + acquisition.collision->input.metrics();
        }
        return metrics;
    }

    void require_private(const Policy& policy, const char* role, Handle& handle, bool initial = false)
    {
        if (policy.owner != owner_ || !policy.protected_dacl || policy.dacl != private_acl_)
            fail("private owner/protected DACL changed: " + private_policy_metrics(policy, role, handle, initial));
        const auto* acl = reinterpret_cast<const ACL*>(policy.dacl.data());
        if (acl->AceCount != 1) fail("stage must inherit only the owner ACE: " + private_policy_metrics(policy, role, handle, initial));
        void* raw = nullptr;
        if (!::GetAce(const_cast<PACL>(acl), 0, &raw)) {
            const DWORD error = ::GetLastError();
            win_error("inspect private stage ACE: " + private_policy_metrics(policy, role, handle, initial), error);
        }
        auto* ace = static_cast<ACCESS_ALLOWED_ACE*>(raw);
        if (ace->Header.AceType != ACCESS_ALLOWED_ACE_TYPE || !::EqualSid(&ace->SidStart, owner_.data())
            || ace->Mask != FILE_ALL_ACCESS || (ace->Header.AceFlags & INHERIT_ONLY_ACE))
            fail("stage is not owner-only before publication: " + private_policy_metrics(policy, role, handle, initial));
        if (initial) handle.note_initial_private();
    }

    void validate_workspace()
    {
        auto anchor = native_.relative(parent_.get(), L".space-publication", true, false, directory_access);
        if (!anchor_id_ || !identity(metadata(anchor.get(), true), *anchor_id_)
            || !identity(metadata(anchor_.get(), true), *anchor_id_)) fail("anchor identity changed");
        require_private(inspect_policy(anchor_.get()), "anchor", anchor_);
        auto named = native_.relative(anchor_.get(), workspace_name_, true, false, directory_access);
        if (!workspace_id_ || !identity(metadata(named.get(), true), *workspace_id_)
            || !identity(metadata(workspace_.get(), true), *workspace_id_))
            fail("workspace identity/security changed");
        require_private(inspect_policy(workspace_.get()), "attempt", workspace_);
    }

    void validate_record_name()
    {
        auto named = native_.relative(workspace_.get(), L"record", false, false, READ_CONTROL | FILE_READ_ATTRIBUTES);
        const auto value = metadata(record_.get());
        if (!record_id_ || !identity(value, *record_id_) || !identity(metadata(named.get()), value))
            fail("private record identity changed");
    }

    void verify_bytes(std::string_view bytes)
    {
        LARGE_INTEGER zero {};
        if (!::SetFilePointerEx(record_.get(), zero, nullptr, FILE_BEGIN)) win_error("seek stage");
        std::array<char, 65536> buffer;
        std::size_t offset = 0;
        for (;;) {
            DWORD count = 0;
            if (!::ReadFile(record_.get(), buffer.data(), buffer.size(), &count, nullptr)) win_error("verify stage bytes");
            if (count == 0) break;
            if (count > bytes.size() - offset || std::memcmp(buffer.data(), bytes.data() + offset, count) != 0)
                fail("stage bytes differ from expected bytes");
            offset += count;
        }
        if (offset != bytes.size()) fail("stage byte length differs from expected bytes");
    }

    void cleanup_entry(std::optional<std::string>& errors)
    {
        try {
            bool missing = false;
            auto handle = native_.relative(workspace_.get(), L"record", false, false,
                DELETE | READ_CONTROL | FILE_READ_ATTRIBUTES, nullptr, nullptr, &missing);
            if (missing) return;
            if (!record_id_ || !identity(metadata(handle.get()), *record_id_)) fail("unowned/substituted cleanup entry");
            BOOLEAN remove = TRUE;
            native_.information(handle.get(), &remove, sizeof(remove), static_cast<FILE_INFORMATION_CLASS>(13),
                "remove owned record by handle");
            handle.close_checked();
        } catch (...) { append_error(errors, current_error()); }
    }

    static constexpr ACCESS_MASK directory_access = READ_CONTROL | FILE_READ_ATTRIBUTES | FILE_LIST_DIRECTORY
        | FILE_TRAVERSE | FILE_ADD_FILE | FILE_ADD_SUBDIRECTORY | SYNCHRONIZE;
    std::wstring name_, workspace_name_;
    Blob owner_, private_acl_;
    NativeFiles native_ {owner_, private_acl_};
    Handle parent_, anchor_, workspace_, record_;
    BY_HANDLE_FILE_INFORMATION parent_id_ {};
    std::optional<BY_HANDLE_FILE_INFORMATION> destination_, anchor_id_, workspace_id_, record_id_, final_;
    std::optional<Policy> destination_policy_, final_policy_;
    bool owned_ = false, cleaned_ = false;
};

#endif

} // namespace

namespace detail {

struct Operation::Impl {
    Impl(const fs::path& destination, std::string_view bytes)
        : payload(bytes), attempt(destination) {}

    Phase finish_cleanup()
    {
        try {
            const auto error = attempt.cleanup();
            if (error) append_error(state.cleanup_error, *error);
        } catch (...) { append_error(state.cleanup_error, current_error()); }
        state.phase = Phase::done;
        return state.phase;
    }

    Phase enter_cleanup()
    {
        if (!attempt.owns_workspace()) return finish_cleanup();
        state.phase = Phase::before_cleanup;
        return state.phase;
    }

    const std::string payload;
    Attempt attempt;
    State state;
};

Operation::Operation(const fs::path& destination, std::string_view payload)
    : impl_(std::make_unique<Impl>(destination, payload)) {}

Operation::~Operation() = default;

const State& Operation::state() const noexcept
{
    return impl_->state;
}

Phase Operation::advance(const Reply& reply)
{
    auto& operation = *impl_;
    auto& state = operation.state;
    if (state.phase == Phase::done || reply.phase != state.phase)
        fail("invalid operation reply phase");
    if (state.phase == Phase::before_cleanup) {
        if (reply.failed) append_error(state.cleanup_error, reply.error);
        return operation.finish_cleanup();
    }
    if (reply.failed) {
        state.failure = reply.error;
        return operation.enter_cleanup();
    }
    try {
        switch (state.phase) {
        case Phase::start:
            operation.attempt.prepare();
            state.phase = Phase::before_write;
            return state.phase;
        case Phase::before_write:
            operation.attempt.write(operation.payload);
            state.phase = Phase::before_security;
            return state.phase;
        case Phase::before_security:
            operation.attempt.secure(operation.payload);
            state.phase = Phase::before_commit;
            return state.phase;
        case Phase::before_commit:
            operation.attempt.validate(operation.payload);
            operation.attempt.commit();
            state.committed = true; // Irreversible latch: no callback/adapter work before assignment.
            break;
        default:
            fail("invalid operation phase");
        }
    } catch (...) {
        state.failure = current_error();
    }
    return operation.enter_cleanup();
}

Phase Operation::cancel(std::string_view reason)
{
    auto& operation = *impl_;
    auto& state = operation.state;
    if (state.phase == Phase::done) return Phase::done;
    if (state.phase == Phase::before_cleanup) {
        append_error(state.cleanup_error, std::string(reason));
        return operation.finish_cleanup();
    }
    state.failure = std::string(reason);
    return operation.enter_cleanup();
}

} // namespace detail

Result publish(const fs::path& destination, std::string_view expected_bytes, const Hooks& hooks)
{
    detail::Operation operation(destination, expected_bytes);
    auto phase = operation.advance({detail::Phase::start, false, {}});
    while (phase != detail::Phase::done) {
        const std::function<void()>* hook = nullptr;
        switch (phase) {
        case detail::Phase::before_write: hook = &hooks.before_write; break;
        case detail::Phase::before_security: hook = &hooks.before_security; break;
        case detail::Phase::before_commit: hook = &hooks.before_commit; break;
        case detail::Phase::before_cleanup: hook = &hooks.before_cleanup; break;
        default: fail("unexpected publication hook phase");
        }
        detail::Reply reply {phase, false, {}};
        try { if (*hook) (*hook)(); }
        catch (...) {
            reply.failed = true;
            reply.error = current_error();
        }
        phase = operation.advance(reply);
    }
    const auto& state = operation.state();
    if (state.failure) {
        auto failure = *state.failure;
        if (state.cleanup_error) failure.append("; cleanup: " + *state.cleanup_error);
        fail(failure);
    }
    return {state.committed, state.cleanup_error};
}

} // namespace record_publication
