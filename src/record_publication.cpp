#include "record_publication.h"

#include <array>
#include <atomic>
#include <chrono>
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

void trusted_directory(int fd)
{
    const auto value = metadata(fd);
    if (!S_ISDIR(value.st_mode) || (value.st_uid != 0 && value.st_uid != ::geteuid())
        || ((value.st_mode & 0022) && !(value.st_mode & S_ISVTX))) {
        fail("untrusted writable/foreign directory ancestry");
    }
    mode_only(fd);
}

struct PinnedDirectory {
    fs::path path;
    Handle handle;
    struct stat original;
};

class Attempt {
public:
    explicit Attempt(const fs::path& destination)
    {
        if (destination.empty() || destination.filename().empty()
            || destination.filename() == "." || destination.filename() == ".."
            || destination.native().find('\0') != std::string::npos) fail("invalid destination path");
        const auto absolute = fs::absolute(destination);
        // Resolve only trusted aliases. The callback receives the canonical path,
        // never a mutable alias. Check each original prefix before resolving it.
        fs::path prefix = absolute.root_path();
        for (const auto& part : absolute.parent_path().relative_path()) {
            prefix /= part;
            struct stat link {};
            if (::lstat(prefix.c_str(), &link) != 0) os_error("inspect ancestry");
            if (S_ISLNK(link.st_mode) && link.st_uid != 0 && link.st_uid != ::geteuid())
                fail("foreign ancestry alias");
            Handle fd(::open(prefix.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC));
            if (fd.get() < 0) os_error("open ancestry");
            trusted_directory(fd.get());
        }
        parent_path_ = fs::canonical(absolute.parent_path());
        name_ = absolute.filename().native();
        pin(parent_path_.root_path());
        prefix = parent_path_.root_path();
        for (const auto& part : parent_path_.relative_path()) {
            prefix /= part;
            pin(prefix);
        }
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
        for (int tries = 0; tries < 64; ++tries) {
            workspace_name_ = workspace_name();
            if (::mkdirat(parent(), workspace_name_.c_str(), 0700) == 0) {
                owned_ = true;
                break;
            }
            if (errno != EEXIST) os_error("create private workspace");
        }
        if (!owned_) fail("cannot allocate exclusive workspace");
        workspace_ = Handle(::openat(parent(), workspace_name_.c_str(),
            O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
        if (workspace_.get() < 0) os_error("open private workspace");
        workspace_id_ = metadata(workspace_.get());
        validate_workspace();
        temporary_ = Handle(::openat(workspace_.get(), "record.tmp",
            O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600));
        if (temporary_.get() < 0) os_error("precreate private temporary");
        temporary_id_ = metadata(temporary_.get());
        regular_private_owner(*temporary_id_);
        if ((temporary_id_->st_mode & 0777) != 0600) fail("temporary mode must be0600");
        mode_only(temporary_.get());
    }

    fs::path stage_path() const { return parent_path_ / workspace_name_ / "record"; }
    bool owns_workspace() const { return owned_; }

    void observe_stage()
    {
        if (record_id_ || workspace_.get() < 0) return;
        Handle fd(::openat(workspace_.get(), "record", O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC));
        if (fd.get() < 0) return; // secure/cleanup surface any missing or unsafe entry.
        struct stat value {};
        if (::fstat(fd.get(), &value) == 0
            && S_ISREG(value.st_mode) && value.st_uid == ::geteuid() && value.st_nlink == 1) {
            record_id_ = value;
            record_ = std::move(fd); // Pin identity across the before-security callback too.
        }
    }

    void secure(std::string_view bytes)
    {
        validate_workspace();
        if (record_.get() < 0) fail("callback record is missing, unreadable or unsafe");
        const auto value = metadata(record_.get());
        struct stat named {};
        if (::fstatat(workspace_.get(), "record", &named, AT_SYMLINK_NOFOLLOW) != 0)
            os_error("inspect callback record name");
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
        validate_temporary();
        struct stat named {};
        if (::fstatat(workspace_.get(), "record", &named, AT_SYMLINK_NOFOLLOW) != 0)
            os_error("revalidate stage name");
        const auto value = metadata(record_.get());
        if (!identity(named, value) || !final_ || !snapshot(*final_, value)
            || !S_ISREG(value.st_mode) || value.st_nlink != 1) fail("stage identity/security changed");
        mode_only(record_.get());
        verify_bytes(bytes);
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
        cleanup_entry("record", record_id_, errors);
        cleanup_entry("record.tmp", temporary_id_, errors);
        struct stat named {};
        if (::fstatat(parent(), workspace_name_.c_str(), &named, AT_SYMLINK_NOFOLLOW) != 0
            || !identity(named, *workspace_id_)) {
            append_error(errors, "workspace identity changed; directory left untouched");
        } else if (::unlinkat(parent(), workspace_name_.c_str(), AT_REMOVEDIR) != 0) {
            append_error(errors, "remove workspace: " + std::error_code(errno, std::generic_category()).message());
        }
        return errors;
    }

private:
    int parent() const { return ancestry_.back().handle.get(); }

    void pin(const fs::path& path)
    {
        Handle handle(::open(path.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
        if (handle.get() < 0) os_error("pin ancestry");
        trusted_directory(handle.get());
        const auto value = metadata(handle.get());
        ancestry_.push_back({path, std::move(handle), value});
    }

    void validate_workspace()
    {
        for (const auto& directory : ancestry_) {
            struct stat named {};
            if (::lstat(directory.path.c_str(), &named) != 0) os_error("revalidate ancestry");
            const auto value = metadata(directory.handle.get());
            if (!identity(named, directory.original) || !identity(value, directory.original)
                || !security(value, directory.original)) fail("ancestry identity/security changed");
            trusted_directory(directory.handle.get());
        }
        struct stat named {};
        if (::fstatat(parent(), workspace_name_.c_str(), &named, AT_SYMLINK_NOFOLLOW) != 0)
            os_error("revalidate workspace");
        const auto value = metadata(workspace_.get());
        if (!workspace_id_ || !identity(named, *workspace_id_) || !identity(value, *workspace_id_)
            || !S_ISDIR(value.st_mode) || value.st_uid != ::geteuid()
            || (value.st_mode & 07777) != 0700) fail("workspace identity/privacy changed");
        mode_only(workspace_.get());
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

    void validate_temporary()
    {
        Handle fd(::openat(workspace_.get(), "record.tmp", O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC));
        if (fd.get() < 0) {
            if (errno == ENOENT) return; // Canonical JSONUtils moved it to record.
            os_error("revalidate temporary");
        }
        const auto value = metadata(fd.get());
        regular_private_owner(value);
        if (!temporary_id_ || !identity(value, *temporary_id_)) fail("temporary identity changed");
        mode_only(fd.get());
    }

    fs::path parent_path_;
    std::string name_, workspace_name_;
    std::vector<PinnedDirectory> ancestry_;
    Handle workspace_, temporary_, record_;
    std::optional<struct stat> destination_, workspace_id_, temporary_id_, record_id_, final_;
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
    // MAX_PATH-dependent publication fallback. Lua's short stage path is unchanged.
    fs::path preferred = path;
    preferred.make_preferred();
    return L"\\\\?\\" + preferred.native();
}

class Handle {
public:
    explicit Handle(HANDLE value = INVALID_HANDLE_VALUE) : value_(value) {}
    ~Handle() { close(); }
    Handle(Handle&& other) noexcept : value_(std::exchange(other.value_, INVALID_HANDLE_VALUE)) {}
    Handle& operator=(Handle&& other) noexcept
    {
        close();
        value_ = std::exchange(other.value_, INVALID_HANDLE_VALUE);
        return *this;
    }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    HANDLE get() const { return value_; }
    void close() noexcept
    {
        if (value_ != INVALID_HANDLE_VALUE && value_ != nullptr) ::CloseHandle(value_);
        value_ = INVALID_HANDLE_VALUE;
    }
private:
    HANDLE value_;
};

struct LocalMemory {
    HLOCAL value = nullptr;
    ~LocalMemory() { if (value) ::LocalFree(value); }
};

using Blob = std::vector<unsigned char>;

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

Handle open_path(const fs::path& path, bool directory = false, bool writable_security = false)
{
    const DWORD access = READ_CONTROL | FILE_READ_ATTRIBUTES
        | (directory ? 0 : FILE_READ_DATA)
        | (writable_security ? WRITE_DAC | WRITE_OWNER : 0);
    Handle handle(::CreateFileW(native_path(path).c_str(), access,
        FILE_SHARE_READ | FILE_SHARE_WRITE | (directory ? 0 : FILE_SHARE_DELETE), nullptr,
        OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT | (directory ? FILE_FLAG_BACKUP_SEMANTICS : 0), nullptr));
    if (handle.get() == INVALID_HANDLE_VALUE) win_error("open pinned object");
    metadata(handle.get(), directory);
    return handle;
}

struct PinnedDirectory {
    fs::path path;
    Handle handle;
    BY_HANDLE_FILE_INFORMATION original;
    Policy policy;
};

class Attempt {
public:
    explicit Attempt(const fs::path& destination)
    {
        if (destination.empty() || destination.filename().empty() || destination.filename() == L"."
            || destination.filename() == L".." || destination.native().find(L'\0') != std::wstring::npos
            || destination.filename().native().find(L':') != std::wstring::npos)
            fail("invalid destination path/alternate stream");
        destination_path_ = fs::absolute(destination).lexically_normal();
        parent_path_ = destination_path_.parent_path();
        if (parent_path_.native().rfind(L"\\\\", 0) == 0) fail("remote/device ancestry is unsupported");
        HANDLE raw_token = nullptr;
        if (!::OpenThreadToken(::GetCurrentThread(), TOKEN_QUERY, TRUE, &raw_token)) {
            if (::GetLastError() != ERROR_NO_TOKEN) win_error("open effective thread token");
            if (!::OpenProcessToken(::GetCurrentProcess(), TOKEN_QUERY, &raw_token)) win_error("open process token");
        }
        Handle token(raw_token);
        DWORD size = 0;
        ::GetTokenInformation(token.get(), TokenOwner, nullptr, 0, &size);
        if (::GetLastError() != ERROR_INSUFFICIENT_BUFFER) win_error("size token owner");
        Blob data(size);
        if (!::GetTokenInformation(token.get(), TokenOwner, data.data(), size, &size)) win_error("read token owner");
        owner_ = copy_sid(reinterpret_cast<TOKEN_OWNER*>(data.data())->Owner);
        fs::path prefix = parent_path_.root_path();
        pin(prefix);
        for (const auto& part : parent_path_.relative_path()) {
            prefix /= part;
            pin(prefix);
        }
        std::array<wchar_t, MAX_PATH + 1> volume {};
        if (!::GetVolumePathNameW(parent_path_.c_str(), volume.data(), volume.size())) win_error("inspect local volume");
        const UINT type = ::GetDriveTypeW(volume.data());
        DWORD flags = 0;
        if ((type != DRIVE_FIXED && type != DRIVE_REMOVABLE)
            || !::GetVolumeInformationW(volume.data(), nullptr, 0, nullptr, nullptr, &flags, nullptr, 0))
            fail("local filesystem semantics unavailable");
        if (!(flags & FILE_PERSISTENT_ACLS)) fail("persistent ACL filesystem required");
        destination_handle_ = optional_destination();
        if (destination_handle_.get() != INVALID_HANDLE_VALUE) {
            destination_ = metadata(destination_handle_.get());
            destination_policy_ = inspect_policy(destination_handle_.get());
        }
    }

    ~Attempt() noexcept
    {
        if (!cleaned_) { try { cleanup(); } catch (...) {} }
    }

    void prepare()
    {
        Blob acl(sizeof(ACL) + sizeof(ACCESS_ALLOWED_ACE) - sizeof(DWORD) + owner_.size());
        auto* dacl = reinterpret_cast<PACL>(acl.data());
        if (!::InitializeAcl(dacl, acl.size(), ACL_REVISION)
            || !::AddAccessAllowedAceEx(dacl, ACL_REVISION, OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE,
                FILE_ALL_ACCESS, owner_.data())) win_error("construct owner-only DACL");
        SECURITY_DESCRIPTOR descriptor;
        if (!::InitializeSecurityDescriptor(&descriptor, SECURITY_DESCRIPTOR_REVISION)
            || !::SetSecurityDescriptorOwner(&descriptor, owner_.data(), FALSE)
            || !::SetSecurityDescriptorDacl(&descriptor, TRUE, dacl, FALSE)
            || !::SetSecurityDescriptorControl(&descriptor, SE_DACL_PROTECTED, SE_DACL_PROTECTED))
            win_error("construct private security descriptor");
        SECURITY_ATTRIBUTES attributes {sizeof(SECURITY_ATTRIBUTES), &descriptor, FALSE};
        for (int tries = 0; tries < 64; ++tries) {
            workspace_path_ = parent_path_ / workspace_name();
            if (::CreateDirectoryW(native_path(workspace_path_).c_str(), &attributes)) { owned_ = true; break; }
            if (::GetLastError() != ERROR_ALREADY_EXISTS) win_error("create private workspace");
        }
        if (!owned_) fail("cannot allocate exclusive workspace");
        workspace_ = open_path(workspace_path_, true);
        workspace_id_ = metadata(workspace_.get(), true);
        workspace_policy_ = inspect_policy(workspace_.get());
        if (workspace_policy_->owner != owner_ || !workspace_policy_->protected_dacl
            || workspace_policy_->dacl != acl) fail("private workspace DACL reproduction failed");
        const auto temporary_path = workspace_path_ / L"record.tmp";
        temporary_ = Handle(::CreateFileW(native_path(temporary_path).c_str(), GENERIC_READ | GENERIC_WRITE | READ_CONTROL,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, &attributes, CREATE_NEW,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
        if (temporary_.get() == INVALID_HANDLE_VALUE) win_error("precreate private temporary");
        temporary_id_ = metadata(temporary_.get());
        const auto policy = inspect_policy(temporary_.get());
        if (policy.owner != owner_ || !policy.protected_dacl || policy.dacl != acl)
            fail("temporary owner-only DACL reproduction failed");
    }

    fs::path stage_path() const { return workspace_path_ / L"record"; }
    bool owns_workspace() const { return owned_; }

    void observe_stage()
    {
        if (record_id_ || !owned_) return;
        // Failed/unsafe entries are deliberately left for diagnostic cleanup,
        // never adopted through a reparse point or a multiple-link alias.
        try {
            auto handle = open_path(stage_path(), false, true);
            const auto policy = inspect_policy(handle.get());
            if (policy.owner == owner_) {
                record_id_ = metadata(handle.get());
                record_ = std::move(handle);
            }
        } catch (...) {}
    }

    void secure(std::string_view bytes)
    {
        validate_workspace();
        if (record_.get() == INVALID_HANDLE_VALUE) fail("callback record is missing, unreadable or unsafe");
        const auto value = metadata(record_.get());
        auto named = open_path(stage_path());
        if (!record_id_ || !identity(*record_id_, value) || !identity(metadata(named.get()), value))
            fail("stage identity changed");
        const auto policy = inspect_policy(record_.get());
        require_private_file(policy);
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
        validate_workspace();
        const auto temporary_path = workspace_path_ / L"record.tmp";
        const DWORD attributes = ::GetFileAttributesW(native_path(temporary_path).c_str());
        if (attributes != INVALID_FILE_ATTRIBUTES) {
            auto temporary = open_path(temporary_path);
            if (!temporary_id_ || !identity(metadata(temporary.get()), *temporary_id_))
                fail("temporary identity changed");
            require_private_file(inspect_policy(temporary.get()));
        } else if (::GetLastError() != ERROR_FILE_NOT_FOUND) {
            win_error("revalidate temporary");
        }
        auto named = open_path(stage_path());
        const auto value = metadata(record_.get());
        if (!identity(metadata(named.get()), value) || !final_ || !snapshot(*final_, value)
            || !same_policy(*final_policy_, inspect_policy(record_.get()))) fail("stage identity/security changed");
        verify_bytes(bytes);
        auto current = optional_destination();
        if ((current.get() != INVALID_HANDLE_VALUE) != destination_.has_value()) fail("destination existence changed");
        if (destination_ && (!snapshot(*destination_, metadata(current.get()))
            || !same_policy(*destination_policy_, inspect_policy(current.get()))))
            fail("destination identity/security changed");
        if (value.dwVolumeSerialNumber != ancestry_.back().original.dwVolumeSerialNumber)
            fail("cross-volume publication is forbidden");
    }

    void commit()
    {
        if (!::MoveFileExW(native_path(stage_path()).c_str(), native_path(destination_path_).c_str(),
                destination_ ? MOVEFILE_REPLACE_EXISTING : 0)) win_error("atomic MoveFileExW publication");
    }

    std::optional<std::string> cleanup()
    {
        cleaned_ = true;
        std::optional<std::string> errors;
        if (!owned_) return errors;
        try {
            auto named = open_path(workspace_path_, true);
            if (!workspace_id_ || !identity(metadata(named.get(), true), *workspace_id_))
                fail("workspace identity changed; left untouched");
            cleanup_entry(stage_path(), record_id_, errors);
            cleanup_entry(workspace_path_ / L"record.tmp", temporary_id_, errors);
        } catch (...) { append_error(errors, current_error()); return errors; }
        record_.close();
        temporary_.close(); // Complete delete-pending child removals first.
        workspace_.close(); // Only our pinned workspace handle blocks rmdir.
        if (!::RemoveDirectoryW(native_path(workspace_path_).c_str()))
            append_error(errors, "remove workspace: " + std::error_code(::GetLastError(), std::system_category()).message());
        return errors;
    }

private:
    Handle optional_destination()
    {
        const DWORD attributes = ::GetFileAttributesW(native_path(destination_path_).c_str());
        if (attributes == INVALID_FILE_ATTRIBUTES) {
            const DWORD error = ::GetLastError();
            if (error == ERROR_FILE_NOT_FOUND) return Handle();
            win_error("inspect destination existence", error);
        }
        return open_path(destination_path_);
    }

    bool trusted_sid(PSID sid)
    {
        alignas(DWORD) std::array<unsigned char, SECURITY_MAX_SID_SIZE> system {}, administrators {};
        DWORD system_size = system.size(), admin_size = administrators.size();
        if (!::CreateWellKnownSid(WinLocalSystemSid, nullptr, system.data(), &system_size)
            || !::CreateWellKnownSid(WinBuiltinAdministratorsSid, nullptr, administrators.data(), &admin_size))
            win_error("inspect trusted ancestry identities");
        return ::EqualSid(sid, owner_.data()) || ::EqualSid(sid, system.data())
            || ::EqualSid(sid, administrators.data());
    }

    void pin(const fs::path& path)
    {
        auto handle = open_path(path, true);
        const auto policy = inspect_policy(handle.get());
        if (!trusted_sid(const_cast<unsigned char*>(policy.owner.data()))) fail("foreign ancestry owner");
        const auto* acl = reinterpret_cast<const ACL*>(policy.dacl.data());
        for (DWORD index = 0; index < acl->AceCount; ++index) {
            void* raw = nullptr;
            if (!::GetAce(const_cast<PACL>(acl), index, &raw)) win_error("inspect ancestry ACE");
            auto* ace = static_cast<ACCESS_ALLOWED_ACE*>(raw);
            if (ace->Header.AceType != ACCESS_ALLOWED_ACE_TYPE || (ace->Header.AceFlags & INHERIT_ONLY_ACE)) continue;
            // Denying delete sharing pins names, not directory reparse data:
            // FSCTL_SET_REPARSE_POINT can use a foreign write-data handle even
            // while our handle remains open. Refuse that authority BEFORE Lua
            // receives a path or can write bytes. Map generic file rights first;
            // testing only GENERIC_ALL misses GENERIC_WRITE and its specific bits.
            GENERIC_MAPPING mapping {FILE_GENERIC_READ, FILE_GENERIC_WRITE, FILE_GENERIC_EXECUTE, FILE_ALL_ACCESS};
            DWORD granted = ace->Mask;
            ::MapGenericMask(&granted, &mapping);
            const DWORD mutation = DELETE | FILE_DELETE_CHILD | WRITE_DAC | WRITE_OWNER | FILE_WRITE_DATA;
            if ((granted & mutation) && !trusted_sid(&ace->SidStart)) fail("untrusted mutable ancestry DACL");
        }
        const auto value = metadata(handle.get(), true);
        ancestry_.push_back({path, std::move(handle), value, policy});
    }

    void require_private_file(const Policy& policy)
    {
        if (policy.owner != owner_) fail("stage owner changed");
        const auto* acl = reinterpret_cast<const ACL*>(policy.dacl.data());
        if (acl->AceCount != 1) fail("stage must inherit only the owner ACE");
        void* raw = nullptr;
        if (!::GetAce(const_cast<PACL>(acl), 0, &raw)) win_error("inspect private stage ACE");
        auto* ace = static_cast<ACCESS_ALLOWED_ACE*>(raw);
        if (ace->Header.AceType != ACCESS_ALLOWED_ACE_TYPE || !::EqualSid(&ace->SidStart, owner_.data())
            || ace->Mask != FILE_ALL_ACCESS || (ace->Header.AceFlags & INHERIT_ONLY_ACE))
            fail("stage is not owner-only before publication");
    }

    void validate_workspace()
    {
        for (const auto& directory : ancestry_) {
            // Handles deny ancestor rename/deletion. pin's initial ACL gate
            // separately excludes foreign reparse writes before any callback;
            // these later reopens are not a substitute for that privacy gate.
            auto named = open_path(directory.path, true);
            if (!identity(metadata(named.get(), true), directory.original)
                || !same_policy(directory.policy, inspect_policy(directory.handle.get())))
                fail("ancestry identity/security changed");
        }
        auto named = open_path(workspace_path_, true);
        if (!workspace_id_ || !identity(metadata(named.get(), true), *workspace_id_)
            || !same_policy(*workspace_policy_, inspect_policy(workspace_.get())))
            fail("workspace identity/security changed");
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

    void cleanup_entry(const fs::path& path, const std::optional<BY_HANDLE_FILE_INFORMATION>& expected,
                       std::optional<std::string>& errors)
    {
        if (::GetFileAttributesW(native_path(path).c_str()) == INVALID_FILE_ATTRIBUTES && ::GetLastError() == ERROR_FILE_NOT_FOUND)
            return;
        try {
            auto handle = open_path(path);
            if (!expected || !identity(metadata(handle.get()), *expected)) fail("unowned/substituted cleanup entry");
            if (!::DeleteFileW(native_path(path).c_str())) win_error("remove owned entry");
        } catch (...) { append_error(errors, current_error()); }
    }

    fs::path parent_path_, destination_path_, workspace_path_;
    Blob owner_;
    std::vector<PinnedDirectory> ancestry_;
    Handle destination_handle_, workspace_, temporary_, record_;
    std::optional<BY_HANDLE_FILE_INFORMATION> destination_, workspace_id_, temporary_id_, record_id_, final_;
    std::optional<Policy> destination_policy_, workspace_policy_, final_policy_;
    bool owned_ = false, cleaned_ = false;
};

#endif

} // namespace

Result publish(const fs::path& destination, std::string_view expected_bytes, const Stage& stage, const Hooks& hooks)
{
    if (!stage) fail("stage callback is required");
    Attempt attempt(destination);
    Result result;
    std::optional<std::string> failure;
    try {
        attempt.prepare();
        try {
            stage(attempt.stage_path());
        } catch (...) {
            attempt.observe_stage();
            throw;
        }
        attempt.observe_stage();
        if (hooks.before_security) hooks.before_security();
        attempt.secure(expected_bytes);
        if (hooks.before_commit) hooks.before_commit();
        attempt.validate(expected_bytes);
        attempt.commit();
        result.committed = true; // Irreversible latch: no Lua/fallible work before this assignment.
    } catch (...) {
        failure = current_error();
    }
    if (attempt.owns_workspace() && hooks.before_cleanup) {
        try { hooks.before_cleanup(); }
        catch (...) { append_error(result.cleanup_error, current_error()); }
    }
    try {
        const auto cleanup = attempt.cleanup();
        if (cleanup) append_error(result.cleanup_error, *cleanup);
    } catch (...) { append_error(result.cleanup_error, current_error()); }
    if (failure) {
        if (result.cleanup_error) failure->append("; cleanup: " + *result.cleanup_error);
        fail(*failure);
    }
    return result;
}

} // namespace record_publication
