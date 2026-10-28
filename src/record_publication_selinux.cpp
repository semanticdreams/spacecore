#include "record_publication_selinux.h"
#ifdef SPACE_RECORD_PUBLICATION_SELINUX
// Hidden references force extraction of our private archive even when another
// consumer already brings a global system libselinux into the process.
#pragma GCC visibility push(hidden)
extern "C" {
#include <selinux/label.h>
#include <selinux/avc.h>
#include <selinux/selinux.h>
}
#pragma GCC visibility pop

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <sys/stat.h>
#include <sys/vfs.h>
#include <sys/xattr.h>
#include <unistd.h>

namespace record_publication::selinux {
namespace {
[[noreturn]] void fail(const std::string& reason)
{
    throw std::runtime_error("record publication: SELinux " + reason);
}
[[noreturn]] void os_error(const char* reason)
{
    const int error = errno;
    fail(std::string(reason) + ": " + std::strerror(error));
}
struct Fd {
    int value;
    explicit Fd(int fd) : value(fd) { if (fd < 0) os_error("open inspection input"); }
    ~Fd() { if (value >= 0) ::close(value); }
    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
};
struct stat metadata(int fd)
{
    struct stat value {};
    if (::fstat(fd, &value) != 0) os_error("inspect inode");
    return value;
}
bool same_inode(const struct stat& left, const struct stat& right)
{
    return left.st_dev == right.st_dev && left.st_ino == right.st_ino
        && left.st_mode == right.st_mode && left.st_uid == right.st_uid && left.st_gid == right.st_gid
        && left.st_ctim.tv_sec == right.st_ctim.tv_sec && left.st_ctim.tv_nsec == right.st_ctim.tv_nsec;
}
std::string read_file(const std::string& path, std::size_t bound)
{
    Fd fd(::open(path.c_str(), O_RDONLY | O_CLOEXEC));
    std::string result;
    std::array<char, 4096> chunk;
    for (;;) {
        const ssize_t size = ::read(fd.value, chunk.data(), chunk.size());
        if (size < 0 && errno == EINTR) continue;
        if (size < 0) os_error("read inspection input");
        if (!size) break;
        if (result.size() + size > bound) fail("inspection input exceeds bound");
        result.append(chunk.data(), size);
    }
    const int owned = fd.value;
    fd.value = -1;
    if (::close(owned) != 0) os_error("close inspection input");
    return result;
}
bool unsupported(int error) { return error == ENOTSUP || error == EOPNOTSUPP; }
struct RawLabel {
    std::array<char, 4096> bytes {};
    std::size_t size = 0;
    bool operator==(const RawLabel& other) const
    {
        return size == other.size && std::memcmp(bytes.data(), other.bytes.data(), size) == 0;
    }
};
RawLabel read_label(int fd)
{
    const ssize_t count = ::flistxattr(fd, nullptr, 0);
    if (count < 0 && !unsupported(errno)) os_error("enumerate xattrs");
    if (count > 65536) fail("xattr list exceeds bound");
    if (count > 0) {
        static constexpr char supported[] = "security.selinux";
        if (count != sizeof(supported)) fail("extended security/attribute metadata is unsupported");
        std::array<char, sizeof(supported)> names;
        if (::flistxattr(fd, names.data(), names.size()) != count) fail("xattr enumeration changed or failed");
        if (std::memcmp(names.data(), supported, sizeof(supported)))
            fail("extended security/attribute metadata is unsupported");
    }
    const ssize_t size = ::fgetxattr(fd, "security.selinux", nullptr, 0);
    if (size < 0) {
        if (count <= 0 && (errno == ENODATA || unsupported(errno))) return {};
        os_error("read listed label");
    }
    if (count <= 0) fail("label was not present in attribute enumeration");
    if (size < 2 || size > 4096) fail("label length is invalid");
    RawLabel label;
    label.size = static_cast<std::size_t>(size);
    if (::fgetxattr(fd, "security.selinux", label.bytes.data(), label.size) != size)
        fail("label read changed or failed");
    if (label.bytes[label.size - 1] != '\0'
        || std::memchr(label.bytes.data(), '\0', label.size - 1))
        fail("label must have exactly one trailing NUL");
    return label;
}
std::mutex private_mutex;
int policy_generation()
{
    // Only this private copy's status/global mapping state is initialized here.
    if (::selinux_status_open(0) != 0) os_error("open authoritative kernel status");
    const int policy = ::selinux_status_policyload();
    if (policy < 0) os_error("read kernel policy generation");
    return policy;
}
std::string task_context()
{
    auto value = read_file("/proc/thread-self/attr/current", 4096);
    if (!value.empty() && value.back() == '\0') value.pop_back();
    if (value.empty() || value.find('\0') != std::string::npos || value.find('\n') != std::string::npos)
        fail("calling-task context is malformed");
    return value;
}
void require_no_override()
{
    if (!read_file("/proc/thread-self/attr/fscreate", 4096).empty())
        fail("ambient fscreate override is unsupported");
}
bool token(const std::string& options, const std::string& expected)
{
    std::istringstream stream(options);
    std::string item;
    while (std::getline(stream, item, ',')) if (item == expected) return true;
    return false;
}
bool override_options(const std::string& options)
{
    std::istringstream stream(options);
    std::string item;
    while (std::getline(stream, item, ',')) {
        for (const char* prefix : {"context=", "fscontext=", "rootcontext=", "defcontext="})
            if (item.compare(0, std::strlen(prefix), prefix) == 0) return true;
    }
    return false;
}
std::string mount_for_fd(int fd)
{
    const auto info = read_file("/proc/thread-self/fdinfo/" + std::to_string(fd), 65536);
    std::istringstream fields(info);
    std::string line, id;
    while (std::getline(fields, line)) {
        if (line.compare(0, 7, "mnt_id:") != 0) continue;
        if (!id.empty()) fail("ambiguous descriptor mount id");
        std::istringstream value(line.substr(7));
        std::string extra;
        if (!(value >> id) || (value >> extra) || id.find_first_not_of("0123456789") != std::string::npos)
            fail("invalid descriptor mount id");
    }
    if (id.empty()) fail("missing descriptor mount id");
    std::istringstream mounts(read_file("/proc/thread-self/mountinfo", 4 * 1024 * 1024));
    std::string found;
    while (std::getline(mounts, line)) {
        std::istringstream values(line);
        std::vector<std::string> parts;
        std::string value;
        while (values >> value) parts.push_back(value);
        if (parts.empty() || parts.front() != id) continue;
        if (!found.empty()) fail("ambiguous mountinfo association");
        const auto separator = std::find(parts.begin(), parts.end(), "-");
        if (separator == parts.end() || separator - parts.begin() < 6 || parts.end() - separator != 4)
            fail("malformed mountinfo association");
        if (!supported_mount_options(*(separator + 1), parts[5], *(separator + 3)))
            fail("new labeled record requires ordinary seclabel tmpfs");
        found = line;
    }
    if (found.empty()) fail("descriptor mount is missing from current namespace");
    struct statfs filesystem {};
    if (::fstatfs(fd, &filesystem) != 0) os_error("inspect descriptor filesystem");
    if (filesystem.f_type != 0x01021994) fail("descriptor filesystem is not tmpfs");
    return found;
}
std::string counted_context(const char* raw)
{
    if (!raw) fail("context query returned no context");
    const std::size_t size = ::strnlen(raw, 4096);
    if (!size || size == 4096) fail("context query returned invalid length");
    return std::string(raw, size + 1);
}
DefaultContext lookup_default(const std::filesystem::path& destination, const std::filesystem::path& specs)
{
    std::vector<selinux_opt> options {{SELABEL_OPT_VALIDATE, "1"}, {SELABEL_OPT_DIGEST, "1"}};
    const std::string path = specs.string();
    if (!specs.empty()) options.push_back({SELABEL_OPT_PATH, path.c_str()});
    using Backend = std::unique_ptr<selabel_handle, decltype(&selabel_close)>;
    Backend handle(::selabel_open(SELABEL_CTX_FILE, options.data(), options.size()), selabel_close);
    if (!handle) os_error("load file-context backend");
    char* raw = nullptr;
    errno = 0;
    const int status = ::selabel_lookup_raw(handle.get(), &raw, destination.c_str(), S_IFREG | 0600);
    const int error = errno;
    std::unique_ptr<char, decltype(&freecon)> context(raw, freecon);
    DefaultContext result;
    if (status == 0) result.fixed = counted_context(raw);
    else if (error != ENOENT) { errno = error; os_error("inspect final-path default"); }
    unsigned char* digest = nullptr;
    std::size_t length = 0, count = 0;
    char** files = nullptr;
    if (::selabel_digest(handle.get(), &digest, &length, &files, &count) != 0 || !digest || !length)
        fail("file-context provenance unavailable");
    result.digest.assign(reinterpret_cast<char*>(digest), length);
    for (std::size_t i = 0; i < count; ++i) result.files.emplace_back(files[i]);
    return result;
}
} // namespace

Label inspect(int fd)
{
    const auto before = metadata(fd);
    const auto first = read_label(fd);
    const auto second = read_label(fd);
    const auto after = metadata(fd);
    if (!same_inode(before, after) || !(first == second)) fail("inode metadata changed during inspection");
    if (!first.size) return std::nullopt;
    return std::string(first.bytes.data(), first.size);
}
void validate_metadata(int fd, const Label* expected)
{
    const auto before = metadata(fd);
    const auto first = read_label(fd);
    const auto second = read_label(fd);
    if (!same_inode(before, metadata(fd)) || !(first == second)) fail("inode metadata changed during inspection");
    if (expected) {
        const std::size_t size = *expected ? (*expected)->size() : 0;
        if (first.size != size || (size && std::memcmp(first.bytes.data(), (*expected)->data(), size)))
            fail("label presence or complete context changed/mismatched");
    }
}
void require_equal(const Label& actual, const Label& expected)
{
    if (actual != expected) fail("label presence or complete context changed/mismatched");
}
bool supported_mount_options(const std::string& filesystem, const std::string& mount_options,
                             const std::string& super_options)
{
    return filesystem == "tmpfs" && (token(mount_options, "seclabel") || token(super_options, "seclabel"))
        && !override_options(mount_options) && !override_options(super_options);
}
bool DefaultContext::operator==(const DefaultContext& other) const
{
    return fixed == other.fixed && digest == other.digest && files == other.files;
}
DefaultContext default_context(const std::filesystem::path& destination, const std::filesystem::path& specs)
{
    std::lock_guard<std::mutex> guard(private_mutex);
    return lookup_default(destination, specs);
}
bool NewLabelAuthority::State::operator==(const State& other) const
{
    return defaults == other.defaults && expected == other.expected && task == other.task
        && mount == other.mount && policy == other.policy && enforcing == other.enforcing;
}
NewLabelAuthority::NewLabelAuthority(int parent_fd, const std::filesystem::path& destination,
                                   const std::filesystem::path& specs)
    : parent_fd_(parent_fd), destination_(destination), specs_(specs), parent_label_(inspect(parent_fd))
{
    if (!parent_label_) fail("new labeled record requires a labeled final parent");
    const auto parent = metadata(parent_fd_);
    parent_device_ = parent.st_dev;
    parent_inode_ = parent.st_ino;
    baseline_ = read();
}
NewLabelAuthority::State NewLabelAuthority::read() const
{
    std::lock_guard<std::mutex> guard(private_mutex);
    State state;
    state.policy = policy_generation();
    state.enforcing = ::selinux_status_getenforce();
    if (state.enforcing < 0) os_error("read kernel enforcing status");
    state.task = task_context();
    require_no_override();
    state.mount = mount_for_fd(parent_fd_);
    Fd named(::open(destination_.parent_path().c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
    const auto parent = metadata(named.value);
    if (parent.st_dev != parent_device_ || parent.st_ino != parent_inode_)
        fail("final-path parent no longer matches pinned parent");
    require_equal(inspect(parent_fd_), parent_label_);
    state.defaults = lookup_default(destination_, specs_);
    if (state.defaults.fixed) state.expected = *state.defaults.fixed;
    else {
        const auto file_class = ::string_to_security_class("file");
        if (!file_class) fail("file security class is unavailable");
        char* raw = nullptr;
        const int status = ::security_compute_create_name_raw(state.task.c_str(), parent_label_->c_str(),
            file_class, destination_.filename().c_str(), &raw);
        std::unique_ptr<char, decltype(&freecon)> context(raw, freecon);
        if (status != 0) os_error("compute final-name ordinary creation context");
        state.expected = counted_context(raw);
    }
    if (!(lookup_default(destination_, specs_) == state.defaults))
        fail("file-context defaults changed during inspection");
    require_no_override();
    if (task_context() != state.task || policy_generation() != state.policy
        || ::selinux_status_getenforce() != state.enforcing || mount_for_fd(parent_fd_) != state.mount)
        fail("creation authority changed during inspection");
    require_equal(inspect(parent_fd_), parent_label_);
    Fd recheck(::open(destination_.parent_path().c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
    const auto current = metadata(recheck.value);
    if (current.st_dev != parent_device_ || current.st_ino != parent_inode_)
        fail("final-path association changed during inspection");
    return state;
}
void NewLabelAuthority::validate(int stage_fd) const
{
    if (!(read() == baseline_)) fail("creation authority changed since acquisition");
    if (mount_for_fd(stage_fd) != baseline_.mount) fail("stage and final parent mount differ");
    require_equal(inspect(stage_fd), Label(baseline_.expected));
}
} // namespace record_publication::selinux
#endif
