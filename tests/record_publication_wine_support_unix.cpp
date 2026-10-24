// Test-only Wine9 Unix entries, callable as an actual ELF in host-native tests.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "record_publication_wine_support.h"
#include "record_publication_wine_binding.h"
#include "srpt_launch_config.h"

#include <array>
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <ctime>
#include <dirent.h>
#include <fcntl.h>
#include <limits>
#include <memory>
#include <mutex>
#include <signal.h>
#include <spawn.h>
#include <string>
#include <utility>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/xattr.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

#ifndef SRPT_BUILD_ID_BYTES
#error "The test support builder must supply SRPT_BUILD_ID_BYTES"
#endif
#if !defined(__linux__) || !defined(__x86_64__)
#error "Test support requires Linux x86_64"
#endif

namespace {
const uint8_t build_id[32] = SRPT_BUILD_ID_BYTES;
const unsigned char module_marker = 0;
using Entry = int32_t (*)(void*);
static_assert(sizeof(void*) == 8 && sizeof(int32_t) == 4, "Wine9 native Unix ABI");

struct Fd {
    int value;
    explicit Fd(int fd) : value(fd) {}
    ~Fd() { if (value >= 0) ::close(value); }
    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
    Fd(Fd&& other) noexcept : value(std::exchange(other.value, -1)) {}
};

int32_t identity(void* args) noexcept
{
    auto* call = static_cast<SrptIdentity*>(args);
    if (!call || call->size != sizeof(*call) || call->abi != SRPT_ABI) return SRPT_INVALID_ARGUMENT;
    // /proc reports the actual loaded mapping, not a newly substituted pathname.
    // A private address cannot be preempted by another object's exported symbol.
    FILE* maps = std::fopen("/proc/self/maps", "re");
    if (!maps) return SRPT_MODULE_UNAVAILABLE;
    const auto address = reinterpret_cast<uintptr_t>(&module_marker);
    char line[8192];
    bool found = false;
    SrptIdentity result = *call;
    while (std::fgets(line, sizeof(line), maps)) {
        unsigned long long start = 0, end = 0, inode = 0;
        unsigned major = 0, minor = 0;
        if (std::sscanf(line, "%llx-%llx %*4s %*x %x:%x %llu", &start, &end, &major, &minor, &inode) == 5
            && start <= address && address < end && inode) {
            result.module_device = ::makedev(major, minor);
            result.module_inode = inode;
            found = true;
            break;
        }
    }
    const bool read_ok = !std::ferror(maps);
    const bool closed = std::fclose(maps) == 0;
    if (!found || !read_ok || !closed) return SRPT_MODULE_UNAVAILABLE;
    result.echo = result.challenge;
    std::memcpy(result.unix_build_id, build_id, sizeof(build_id));
    result.architecture = SRPT_ARCH_X86_64;
    result.features = SRPT_FEATURES;
    *call = result;
    return SRPT_SUCCESS;
}

struct Root { uint64_t id = 0; int fd = -1; std::string path; bool busy = false; };
std::array<Root, 64> roots;
uint64_t next_id = 1;
std::mutex root_mutex; // No locks span PE hooks; each fixture call is synchronous.
std::vector<std::string> launch_busy_paths;
int64_t sequence_deadline = 0;

bool overlaps(const std::string& first, const std::string& second)
{
    const auto below = [](const std::string& path, const std::string& base) {
        return path == base || (path.size() > base.size() && path.compare(0, base.size(), base) == 0
                               && path[base.size()] == '/');
    };
    return below(first, second) || below(second, first);
}

bool name_valid(const std::string& name, bool empty = false)
{
    if (name.empty()) return empty;
    if (name.front() == '/' || name.back() == '/') return false;
    std::size_t offset = 0;
    while (offset < name.size()) {
        const auto end = name.find('/', offset);
        const auto part = name.substr(offset, end - offset);
        if (part.empty() || part == "." || part == "..") return false;
        if (end == std::string::npos) break;
        offset = end + 1;
    }
    return true;
}

// Opening every ancestor separately makes O_NOFOLLOW meaningful for the whole
// pathname, not just the leaf. Absolute acquisition is used only by RETAIN.
int open_directory(int base, const std::string& name)
{
    Fd current(::fcntl(base, F_DUPFD_CLOEXEC, 0));
    if (current.value < 0) return -1;
    std::size_t offset = 0;
    while (offset < name.size()) {
        const auto end = name.find('/', offset);
        const auto part = name.substr(offset, end - offset);
        const int next = ::openat(current.value, part.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (next < 0) return -1;
        const int old = current.value;
        current.value = next;
        if (::close(old) != 0) return -1;
        if (end == std::string::npos) break;
        offset = end + 1;
    }
    const int result = current.value;
    current.value = -1;
    return result;
}

int parent(int root, const std::string& path, std::string& leaf)
{
    const auto split = path.rfind('/');
    leaf = split == std::string::npos ? path : path.substr(split + 1);
    return open_directory(root, split == std::string::npos ? "" : path.substr(0, split));
}

int fail_errno() { return errno ? errno : EIO; }

int observe(int base, const std::string& leaf, SrptCall& call)
{
    struct stat info {};
    if (::fstatat(base, leaf.c_str(), &info, AT_SYMLINK_NOFOLLOW) != 0) return fail_errno();
    call.data_size = 0;
    if (S_ISREG(info.st_mode) || S_ISDIR(info.st_mode)) {
        Fd object(::openat(base, leaf.c_str(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK
                          | (S_ISDIR(info.st_mode) ? O_DIRECTORY : 0)));
        if (object.value < 0 || ::fstat(object.value, &info) != 0) return fail_errno();
        if (S_ISREG(info.st_mode)) {
            if (info.st_size < 0 || call.offset > static_cast<uint64_t>(info.st_size)) return EINVAL;
            const auto length = std::min<uint64_t>(SRPT_BOUND, info.st_size - call.offset);
            while (call.data_size < length) {
                const auto count = ::pread(object.value, call.data + call.data_size, length - call.data_size,
                                           call.offset + call.data_size);
                if (count < 0 && errno == EINTR) continue;
                if (count <= 0) return count < 0 ? fail_errno() : EIO;
                call.data_size += count;
            }
        } else if (S_ISDIR(info.st_mode)) {
            if (call.offset) return EINVAL;
            DIR* directory = ::fdopendir(object.value);
            if (!directory) return fail_errno();
            object.value = -1;
            int error = 0;
            for (;;) {
                errno = 0;
                const auto* entry = ::readdir(directory);
                if (!entry) { error = errno; break; }
                if (!std::strcmp(entry->d_name, ".") || !std::strcmp(entry->d_name, "..")) continue;
                const auto length = std::strlen(entry->d_name) + 1;
                if (length > SRPT_BOUND - call.data_size) { error = EOVERFLOW; break; }
                std::memcpy(call.data + call.data_size, entry->d_name, length);
                call.data_size += length;
            }
            if (::closedir(directory) != 0 && !error) error = fail_errno();
            if (error) return error;
        } else return EINVAL;
    } else if (call.offset) return EINVAL;
    call.device = info.st_dev;
    call.inode = info.st_ino;
    call.mode = info.st_mode;
    call.uid = info.st_uid;
    call.gid = info.st_gid;
    call.links = info.st_nlink;
    call.file_size = info.st_size;
    return 0;
}

int write_bytes(int fd, const SrptCall& call)
{
    uint32_t offset = 0;
    while (offset < call.data_size) {
        const auto count = ::write(fd, call.data + offset, call.data_size - offset);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return count < 0 ? fail_errno() : EIO;
        offset += count;
    }
    return 0;
}

bool supported_gid(uint32_t gid)
{
    if (gid == ::getegid()) return true;
    const int count = ::getgroups(0, nullptr);
    if (count < 0 || count > 65536) return false;
    std::vector<gid_t> groups(count);
    if (::getgroups(count, groups.data()) != count) return false;
    for (auto group : groups) if (group == gid) return true;
    return false;
}

int mutate(int root, const std::string& path, const std::string& other, const SrptCall& call)
{
    std::string leaf, second;
    Fd base(parent(root, path, leaf));
    if (base.value < 0) return fail_errno();
    if (call.opcode == SRPT_MKDIR) return ::mkdirat(base.value, leaf.c_str(), call.mode) == 0 ? 0 : fail_errno();
    if (call.opcode == SRPT_UNLINK || call.opcode == SRPT_RMDIR)
        return ::unlinkat(base.value, leaf.c_str(), call.opcode == SRPT_RMDIR ? AT_REMOVEDIR : 0) == 0 ? 0 : fail_errno();
    if (call.opcode == SRPT_SYMLINK)
        return ::symlinkat(other.c_str(), base.value, leaf.c_str()) == 0 ? 0 : fail_errno();
    if (call.opcode == SRPT_LINK || call.opcode == SRPT_RENAME) {
        Fd target(parent(root, other, second));
        if (target.value < 0) return fail_errno();
        const int result = call.opcode == SRPT_LINK
            ? ::linkat(base.value, leaf.c_str(), target.value, second.c_str(), 0)
            : ::renameat(base.value, leaf.c_str(), target.value, second.c_str());
        return result == 0 ? 0 : fail_errno();
    }
    const bool create = call.opcode == SRPT_CREATE;
    const bool write = create || call.opcode == SRPT_WRITE;
    Fd object(::openat(base.value, leaf.c_str(), O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK
                      | (write ? O_WRONLY : O_RDONLY) | (create ? O_CREAT | O_EXCL : 0), call.mode));
    if (object.value < 0) return fail_errno();
    struct stat info {};
    if (::fstat(object.value, &info) != 0) return fail_errno();
    if (info.st_uid != ::geteuid() || (!S_ISREG(info.st_mode) && !S_ISDIR(info.st_mode))
        || (S_ISREG(info.st_mode) && info.st_nlink != 1)) return EPERM;
    int error = 0;
    if (write) {
        if (!S_ISREG(info.st_mode)) return EINVAL;
        if (!create && ::ftruncate(object.value, 0) != 0) return fail_errno();
        error = write_bytes(object.value, call);
    } else if (call.opcode == SRPT_CHMOD) {
        if (::fchmod(object.value, call.mode) != 0) error = fail_errno();
    } else if (call.opcode == SRPT_SET_GID) {
        if (!supported_gid(call.gid)) return EPERM;
        if (::fchown(object.value, static_cast<uid_t>(-1), call.gid) != 0) error = fail_errno();
    } else if (call.opcode == SRPT_XATTR) {
        if (::fsetxattr(object.value, "user.space-publication-test", call.data, call.data_size, 0) != 0) error = fail_errno();
    }
    const int fd = object.value;
    object.value = -1;
    if (::close(fd) != 0 && !error) error = fail_errno();
    return error;
}

void record_intact_observation(const Root& root, const std::string& path, const SrptCall& call);
bool root_is_busy(const Root& root, const std::vector<std::string>& targets) noexcept;

int32_t fixture(void* args) noexcept
{
    auto* call = static_cast<SrptCall*>(args);
    if (!call || call->size != sizeof(*call) || call->abi != SRPT_ABI) return SRPT_INVALID_ARGUMENT;
    call->os_error = 0;
    if (call->reserved || call->reserved2 || call->opcode < SRPT_RETAIN || call->opcode > SRPT_RMDIR
        || call->mode > 0777 || call->data_size > SRPT_BOUND || (call->opcode != SRPT_OBSERVE && call->offset)
        || !std::memchr(call->path, 0, SRPT_BOUND) || !std::memchr(call->other, 0, SRPT_BOUND)) return SRPT_INVALID_ARGUMENT;
    try {
        const std::string path(call->path), other(call->other);
        std::lock_guard<std::mutex> lock(root_mutex);
        if (call->opcode == SRPT_RETAIN) {
            if (call->root || path.empty() || path.front() != '/' || !name_valid(path.substr(1))) return SRPT_INVALID_ARGUMENT;
            for (const auto& busy : launch_busy_paths) if (overlaps(path, busy)) {
                call->os_error = EBUSY; return SRPT_UNSUCCESSFUL;
            }
            Root* slot = nullptr;
            for (auto& root : roots) if (!root.id) { slot = &root; break; }
            if (!slot || next_id == std::numeric_limits<uint64_t>::max()) { call->os_error = EMFILE; return SRPT_UNSUCCESSFUL; }
            Fd slash(::open("/", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
            Fd acquired(slash.value < 0 ? -1 : open_directory(slash.value, path.substr(1)));
            struct stat info {};
            if (acquired.value < 0 || ::fstat(acquired.value, &info) != 0) {
                call->os_error = fail_errno(); return SRPT_UNSUCCESSFUL;
            }
            if (!S_ISDIR(info.st_mode) || info.st_uid != ::geteuid() || (info.st_mode & 07777) != 0700) {
                call->os_error = EPERM; return SRPT_UNSUCCESSFUL;
            }
            Root retained {next_id, acquired.value, path, false};
            if (root_is_busy(retained, launch_busy_paths)) {
                call->os_error = EBUSY; return SRPT_UNSUCCESSFUL;
            }
            *slot = std::move(retained);
            acquired.value = -1;
            ++next_id;
            call->root = slot->id;
            return SRPT_SUCCESS;
        }
        Root* owned = nullptr;
        for (auto& root : roots) if (root.id && root.id == call->root) { owned = &root; break; }
        if (!owned) return SRPT_INVALID_ARGUMENT;
        if (owned->busy && call->opcode != SRPT_OBSERVE) {
            call->os_error = EBUSY; return SRPT_UNSUCCESSFUL;
        }
        if (call->opcode == SRPT_RELEASE) {
            const int fd = owned->fd;
            *owned = Root {};
            if (::close(fd) != 0) { call->os_error = fail_errno(); return SRPT_UNSUCCESSFUL; }
            return SRPT_SUCCESS;
        }
        if (!name_valid(path, call->opcode == SRPT_OBSERVE)
            || ((call->opcode == SRPT_LINK || call->opcode == SRPT_SYMLINK || call->opcode == SRPT_RENAME)
                && !name_valid(other))) return SRPT_INVALID_ARGUMENT;
        int error = 0;
        if (call->opcode == SRPT_OBSERVE) {
            std::string leaf;
            Fd base(parent(owned->fd, path.empty() ? "." : path, leaf));
            error = base.value < 0 ? fail_errno() : observe(base.value, leaf, *call);
            if (!error) record_intact_observation(*owned, path, *call);
        } else error = mutate(owned->fd, path, other, *call);
        call->os_error = error;
        return error ? SRPT_UNSUCCESSFUL : SRPT_SUCCESS;
    } catch (...) {
        call->os_error = EIO;
        return SRPT_UNSUCCESSFUL; // No exception escapes the native entry table.
    }
}

using Binding = record_publication::wine::detail::Binding;
struct LaunchError { int32_t status; int error; };

void require(bool value, int32_t status = SRPT_INVALID_ARGUMENT, int error = 0)
{
    if (!value) throw LaunchError {status, error};
}

void host(bool value)
{
    require(value, SRPT_UNSUCCESSFUL, fail_errno());
}

int64_t monotonic_ns()
{
    timespec now {};
    host(::clock_gettime(CLOCK_MONOTONIC, &now) == 0);
    require(now.tv_sec >= 0 && now.tv_sec < INT64_MAX / INT64_C(1000000000) - 60,
            SRPT_UNSUCCESSFUL, EOVERFLOW);
    return static_cast<int64_t>(now.tv_sec) * INT64_C(1000000000) + now.tv_nsec;
}

std::string raw_path(const unsigned char* value)
{
    const auto length = ::strnlen(reinterpret_cast<const char*>(value), SRPT_BOUND);
    require(length && length < SRPT_BOUND);
    std::string path(reinterpret_cast<const char*>(value), length);
    require(path.front() == '/' && (path == "/" || name_valid(path.substr(1))));
    return path;
}

Fd absolute_directory(const std::string& path)
{
    require(!path.empty() && path.front() == '/' && (path == "/" || name_valid(path.substr(1))));
    Fd slash(::open("/", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
    host(slash.value >= 0);
    Fd result(open_directory(slash.value, path.substr(1)));
    host(result.value >= 0);
    return result;
}

struct stat file_info(int fd)
{
    struct stat info {};
    host(::fstat(fd, &info) == 0);
    return info;
}

bool same_object(const struct stat& first, const struct stat& second)
{
    return first.st_dev == second.st_dev && first.st_ino == second.st_ino;
}

bool same_file(const struct stat& first, const struct stat& second)
{
    return same_object(first, second) && first.st_size == second.st_size && first.st_uid == second.st_uid
        && first.st_gid == second.st_gid && first.st_mode == second.st_mode && first.st_nlink == second.st_nlink
        && first.st_mtim.tv_sec == second.st_mtim.tv_sec && first.st_mtim.tv_nsec == second.st_mtim.tv_nsec
        && first.st_ctim.tv_sec == second.st_ctim.tv_sec && first.st_ctim.tv_nsec == second.st_ctim.tv_nsec;
}

void private_directory(int fd)
{
    const auto info = file_info(fd);
    require(S_ISDIR(info.st_mode) && info.st_uid == ::geteuid() && (info.st_mode & 07777) == 0700,
            SRPT_IDENTITY_MISMATCH);
}

void private_path(const std::string& path)
{
    auto fd = absolute_directory(path);
    private_directory(fd.value);
}

bool pin_matches(const struct stat& info, const SrptLaunchRuntimePin& pin)
{
    return S_ISREG(info.st_mode) && info.st_dev == pin.device && info.st_ino == pin.inode
        && info.st_size >= 0 && static_cast<uint64_t>(info.st_size) == pin.size
        && info.st_uid == pin.uid && info.st_mode == pin.mode
        && static_cast<__int128>(info.st_mtim.tv_sec) * 1000000000 + info.st_mtim.tv_nsec == pin.mtime_ns
        && static_cast<__int128>(info.st_ctim.tv_sec) * 1000000000 + info.st_ctim.tv_nsec == pin.ctime_ns;
}

Fd pinned_runtime(const SrptLaunchRuntimePin& pin, bool implementation)
{
    const auto path = raw_path(pin.path);
    require(path != "/" && pin.size <= UINT64_C(64) * 1024 * 1024 && pin.ancestor_count,
            SRPT_IDENTITY_MISMATCH);
    Fd current(::open("/", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
    host(current.value >= 0);
    std::string prefix = "/";
    std::size_t offset = 1;
    for (std::size_t index = 0; index < pin.ancestor_count; ++index) {
        const auto& expected = pin.ancestors[index];
        const auto info = file_info(current.value);
        require(raw_path(expected.path) == prefix && S_ISDIR(info.st_mode)
                && info.st_dev == expected.device && info.st_ino == expected.inode
                && info.st_uid == expected.uid && info.st_mode == expected.mode, SRPT_IDENTITY_MISMATCH);
        const auto end = path.find('/', offset);
        if (end == std::string::npos) {
            require(index + 1 == pin.ancestor_count, SRPT_IDENTITY_MISMATCH);
            Fd result(::openat(current.value, path.c_str() + offset, O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC));
            host(result.value >= 0);
            struct stat witness {};
            host(::fstatat(current.value, path.c_str() + offset, &witness, AT_SYMLINK_NOFOLLOW) == 0);
            require(pin_matches(file_info(result.value), pin) && pin_matches(witness, pin), SRPT_IDENTITY_MISMATCH);
            require((pin.mode & 0111) && !(pin.mode & 06000), SRPT_IDENTITY_MISMATCH);
            if (implementation) {
                unsigned char header[64] {};
                host(::pread(result.value, header, sizeof(header), 0) == static_cast<ssize_t>(sizeof(header)));
                require(!std::memcmp(header, "\177ELF\2\1\1", 7) && (header[7] == 0 || header[7] == 3)
                        && (header[16] == 2 || header[16] == 3) && header[17] == 0
                        && header[18] == 62 && header[19] == 0, SRPT_IDENTITY_MISMATCH);
            }
            require(pin_matches(file_info(result.value), pin), SRPT_IDENTITY_MISMATCH);
            return result;
        }
        require(index + 1 < pin.ancestor_count, SRPT_IDENTITY_MISMATCH);
        const auto component = path.substr(offset, end - offset);
        const int next = ::openat(current.value, component.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        host(next >= 0);
        const int old = std::exchange(current.value, next);
        host(::close(old) == 0);
        prefix = path.substr(0, end);
        offset = end + 1;
    }
    throw LaunchError {SRPT_IDENTITY_MISMATCH, 0};
}

struct LaunchArtifact {
    std::string path;
    Fd descriptor;
    struct stat info;
    std::vector<uint8_t> bytes;
    LaunchArtifact(std::string name, Fd fd, const struct stat& stat) : path(std::move(name)), descriptor(std::move(fd)), info(stat) {}
};

std::unique_ptr<LaunchArtifact> artifact_at(int root, const std::string& relative, const std::string& path,
                                         const uint8_t* id = nullptr)
{
    std::string leaf;
    Fd base(parent(root, relative, leaf));
    host(base.value >= 0);
    Fd fd(::openat(base.value, leaf.c_str(), O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC));
    host(fd.value >= 0);
    const auto info = file_info(fd.value);
    require(S_ISREG(info.st_mode) && info.st_uid == ::geteuid() && info.st_nlink == 1
            && !(info.st_mode & 06000) && info.st_size > 0 && info.st_size <= INT64_C(64) * 1024 * 1024,
            SRPT_IDENTITY_MISMATCH);
    auto result = std::make_unique<LaunchArtifact>(path, std::move(fd), info);
    result->bytes.resize(static_cast<std::size_t>(info.st_size));
    std::size_t offset = 0;
    while (offset < result->bytes.size()) {
        require(!sequence_deadline || monotonic_ns() < sequence_deadline, SRPT_UNSUCCESSFUL, ETIMEDOUT);
        const auto count = ::pread(result->descriptor.value, result->bytes.data() + offset, result->bytes.size() - offset, offset);
        if (count < 0 && errno == EINTR) continue;
        host(count > 0);
        offset += count;
    }
    struct stat witness {};
    host(::fstatat(base.value, leaf.c_str(), &witness, AT_SYMLINK_NOFOLLOW) == 0);
    require(same_file(info, file_info(result->descriptor.value)) && same_file(info, witness), SRPT_IDENTITY_MISMATCH);
    if (id) require(std::search(result->bytes.begin(), result->bytes.end(), id, id + 32) != result->bytes.end(),
                    SRPT_IDENTITY_MISMATCH);
    return result;
}

std::unique_ptr<LaunchArtifact> artifact(const std::string& path, const uint8_t* id = nullptr)
{
    const auto slash = path.rfind('/');
    auto base = absolute_directory(path.substr(0, slash));
    return artifact_at(base.value, path.substr(slash + 1), path, id);
}

std::vector<std::string> directory_names(const std::string& path)
{
    auto directory = absolute_directory(path);
    private_directory(directory.value);
    SrptCall listing {};
    const auto error = observe(directory.value, ".", listing);
    require(!error, SRPT_UNSUCCESSFUL, error);
    std::vector<std::string> names;
    for (std::size_t offset = 0; offset < listing.data_size;) {
        const auto* name = reinterpret_cast<const char*>(listing.data + offset);
        names.emplace_back(name);
        offset += names.back().size() + 1;
    }
    return names;
}

void exact_entries(const std::string& path, std::vector<std::string> expected)
{
    auto names = directory_names(path);
    std::sort(names.begin(), names.end());
    std::sort(expected.begin(), expected.end());
    require(names == expected, SRPT_IDENTITY_MISMATCH);
}

struct Configuration {
    uint64_t temp_id;
    int64_t deadline;
    std::string temp_path, crypto;
    Binding production, support;
    std::vector<std::string> environment;
    Fd temp, implementation, server;
    std::vector<std::unique_ptr<LaunchArtifact>> sources;
    std::vector<std::pair<std::string, struct stat>> directories;
    Configuration(uint64_t id, int64_t end, std::string path, Fd fd, Fd wine, Fd server_fd)
        : temp_id(id), deadline(end), temp_path(std::move(path)), temp(std::move(fd)),
          implementation(std::move(wine)), server(std::move(server_fd)) {}
};

bool configuration_attempted = false;
std::unique_ptr<Configuration> configuration;
bool sequence_failed = false;
uint32_t sequence_next_case = 1;
uint64_t sequence_fixture = 0;
std::string sequence_fixture_path;
const std::array<const char*, 5> case_names {"control", "missing-pe", "bad-pe", "missing-unix", "bad-unix"};
const std::array<const char*, 3> copy_names {"modules/x86_64-unix/space_record_publication.so",
                                          "modules/x86_64-windows/space_record_publication.dll", "space_record_publication.dll"};
struct CopyReceipt {
    std::string fixture_path;
    struct stat fixture_info;
    std::unique_ptr<LaunchArtifact> intact;
};
std::array<std::unique_ptr<CopyReceipt>, 15> copy_receipts;

std::vector<std::string> busy_targets(const std::string& temp)
{
    const auto checkout = raw_path(srpt_launch_checkout);
    std::vector<std::string> paths {temp, checkout + "/build/wine-publication/modules",
                                   checkout + "/build/wine-publication-tests/modules", checkout + "/build/wine/windows"};
    const auto slash = temp.rfind('/');
    if (slash != std::string::npos && temp.substr(slash) == "/tmp")
        for (const auto* name : {"prefix", "data", "cache"}) paths.emplace_back(temp.substr(0, slash) + "/" + name);
    return paths;
}

bool root_is_busy(const Root& root, const std::vector<std::string>& targets) noexcept
{
    try {
        if (targets.empty()) return false;
        for (const auto& target : targets) if (overlaps(root.path, target)) return true;
        // An acquisition-time name cannot prove the current authority of a
        // retained FD after rename. Only a fresh nofollow same-object witness
        // may establish lexical disjointness; unknown/stale roots stay busy.
        const auto held = file_info(root.fd);
        if (!S_ISDIR(held.st_mode) || held.st_uid != ::geteuid() || (held.st_mode & 07777) != 0700) return true;
        auto named = absolute_directory(root.path);
        const auto current = file_info(named.value);
        return !same_object(held, current) || held.st_mode != current.st_mode || held.st_uid != current.st_uid;
    } catch (...) {
        return true; // Conservative and nonthrowing: busy publication cannot fail partway through a lease.
    }
}

struct ConfigurationLease {
    Fd temp {-1};
    std::string path;
    int64_t deadline = 0;
    explicit ConfigurationLease(uint64_t id)
    {
        std::lock_guard<std::mutex> lock(root_mutex);
        require(!configuration_attempted);
        configuration_attempted = true;
        deadline = monotonic_ns() + INT64_C(60000000000); // Consumed before this fallible read; before any setup/validation.
        sequence_deadline = deadline;
        Root* retained = nullptr;
        for (auto& root : roots) if (root.id && root.id == id) retained = &root;
        require(retained != nullptr);
        path = retained->path;
        temp.value = ::fcntl(retained->fd, F_DUPFD_CLOEXEC, 3);
        host(temp.value >= 0);
        launch_busy_paths = busy_targets(path);
        for (auto& root : roots) if (root.id) root.busy = root_is_busy(root, launch_busy_paths);
    }
    ~ConfigurationLease()
    {
        std::lock_guard<std::mutex> lock(root_mutex);
        for (auto& root : roots) root.busy = false;
        launch_busy_paths.clear();
    }
};

std::string native_input(const char* name, bool required = true)
{
    const char* value = std::getenv(name);
    if (!value && !required) return {};
    require(value != nullptr);
    const auto length = ::strnlen(value, SRPT_BOUND);
    require(length < SRPT_BOUND && (!required || length));
    return std::string(value, length);
}

struct NativeInputs {
    std::vector<std::pair<const char*, std::string>> values;
    NativeInputs()
    {
        values.reserve(19);
        for (const auto* name : {"WINEPREFIX", "WINEARCH", "WINESERVER", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TMPDIR",
                                "TEMP", "TMP", "SPACE_WINE_WINDOWS_TMP", "SPACE_WINE_PUBLICATION_BINDING",
                                "SPACE_WINE_PUBLICATION_TEST_BINDING", "SPACE_WINE_PUBLICATION_TEST_CRYPTO"})
            values.emplace_back(name, native_input(name));
        for (const auto* name : {"HOME", "LANG", "LC_ALL", "LC_CTYPE", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"})
            if (std::getenv(name)) values.emplace_back(name, native_input(name, false));
    }
    const std::string* find(const char* name) const
    {
        for (const auto& value : values) if (!std::strcmp(value.first, name)) return &value.second;
        return nullptr;
    }
    const std::string& operator()(const char* name) const
    {
        const auto* value = find(name);
        require(value != nullptr);
        return *value;
    }
};

Binding decode_binding(const std::string& text)
{
    try { return record_publication::wine::detail::parse_binding(text); }
    catch (const std::runtime_error&) { throw LaunchError {SRPT_INVALID_ARGUMENT, 0}; }
}

bool binding_matches(const Binding& binding, const uint8_t* id, uint64_t device, uint64_t inode)
{
    return std::equal(binding.build_id.begin(), binding.build_id.end(), id)
        && binding.module_device == device && binding.module_inode == inode;
}

uint32_t remaining_ms(int64_t deadline)
{
    const auto remaining = deadline - monotonic_ns();
    require(remaining > 0, SRPT_UNSUCCESSFUL, ETIMEDOUT);
    return static_cast<uint32_t>(remaining / INT64_C(1000000));
}

void recheck_sources(const Configuration& configured)
{
    for (const auto& original : configured.sources) {
        auto current = artifact(original->path);
        require(same_file(file_info(original->descriptor.value), original->info)
                && same_file(current->info, original->info) && current->bytes == original->bytes, SRPT_IDENTITY_MISMATCH);
    }
}

void recheck_directories(const Configuration& configured)
{
    for (const auto& pin : configured.directories) {
        auto current = absolute_directory(pin.first);
        private_directory(current.value);
        const auto info = file_info(current.value);
        require(same_object(info, pin.second) && info.st_uid == pin.second.st_uid
                && info.st_mode == pin.second.st_mode, SRPT_IDENTITY_MISMATCH);
    }
}

void fixed_module_layout()
{
    const auto checkout = raw_path(srpt_launch_checkout);
    for (const auto* role : {"wine-publication", "wine-publication-tests"}) {
        const auto base = checkout + "/build/" + role + "/modules";
        const std::string name = !std::strcmp(role, "wine-publication") ? "space_record_publication" : "space_record_publication_tests";
        exact_entries(base, {"x86_64-windows", "x86_64-unix"});
        exact_entries(base + "/x86_64-windows", {name + ".dll"});
        exact_entries(base + "/x86_64-unix", {name + ".so"});
    }
}

void configure(SrptLaunch& call)
{
    ConfigurationLease lease(call.root);
    const auto deadline = lease.deadline;
    const NativeInputs inputs; // One owned snapshot, validated and later copied without rereading getenv.
    const auto checkout = raw_path(srpt_launch_checkout);
    require(srpt_launch_schema == 1, SRPT_IDENTITY_MISMATCH);
    private_directory(lease.temp.value);
    const auto tmp = inputs("TMPDIR");
    require(tmp == lease.path);
    auto reopened = absolute_directory(tmp);
    require(same_object(file_info(reopened.value), file_info(lease.temp.value)), SRPT_IDENTITY_MISMATCH);
    const auto split = tmp.rfind('/');
    require(split != std::string::npos && tmp.substr(split) == "/tmp");
    const auto session = tmp.substr(0, split);
    const auto sessions = checkout + "/build/wine/sessions/";
    require(session.compare(0, sessions.size(), sessions) == 0 && session.size() == sessions.size() + 32);
    for (const char unit : session.substr(sessions.size())) require((unit >= '0' && unit <= '9') || (unit >= 'a' && unit <= 'f'));
    private_path(session);
    private_path(checkout + "/build/wine/sessions");
    require(inputs("WINEARCH") == "win64");
    require(inputs("WINESERVER") == raw_path(srpt_launch_server.path), SRPT_IDENTITY_MISMATCH);
    for (const auto* name : {"prefix", "data", "cache"}) private_path(session + "/" + name);
    require(inputs("WINEPREFIX") == session + "/prefix"
            && inputs("XDG_DATA_HOME") == session + "/data"
            && inputs("XDG_CACHE_HOME") == session + "/cache");
    const auto windows_tmp = inputs("SPACE_WINE_WINDOWS_TMP");
    require(windows_tmp.size() >= 3 && ((windows_tmp[0] >= 'A' && windows_tmp[0] <= 'Z')
            || (windows_tmp[0] >= 'a' && windows_tmp[0] <= 'z')) && windows_tmp[1] == ':' && windows_tmp[2] == '\\'
            && inputs("TEMP") == windows_tmp && inputs("TMP") == windows_tmp);
    for (const unsigned char unit : windows_tmp) require(unit >= 32 && unit != 127);
    std::size_t component = 3;
    while (component < windows_tmp.size()) {
        const auto end = windows_tmp.find('\\', component);
        require(windows_tmp.substr(component, end - component) != "..");
        if (end == std::string::npos) break;
        component = end + 1;
    }
    const auto production = decode_binding(inputs("SPACE_WINE_PUBLICATION_BINDING"));
    const auto support = decode_binding(inputs("SPACE_WINE_PUBLICATION_TEST_BINDING"));
    require(binding_matches(production, call.production_build_id, call.production_device, call.production_inode)
            && binding_matches(support, call.support_build_id, call.support_device, call.support_inode)
            && std::equal(support.build_id.begin(), support.build_id.end(), build_id), SRPT_IDENTITY_MISMATCH);
    SrptIdentity loaded {};
    loaded.size = sizeof(loaded); loaded.abi = SRPT_ABI;
    require(identity(&loaded) == SRPT_SUCCESS, SRPT_UNSUCCESSFUL, EIO);
    require(loaded.module_device == support.module_device && loaded.module_inode == support.module_inode,
            SRPT_IDENTITY_MISMATCH);
    require(checkout.find(':') == std::string::npos && tmp.find(':') == std::string::npos);
    std::vector<std::pair<std::string, struct stat>> directory_pins;
    for (const auto& path : {session, checkout + "/build/wine/sessions", session + "/prefix", tmp,
                            session + "/data", session + "/cache", checkout + "/build/wine/windows"}) {
        auto fd = absolute_directory(path);
        private_directory(fd.value);
        directory_pins.emplace_back(path, file_info(fd.value));
    }
    for (const auto* role : {"wine-publication", "wine-publication-tests"})
        for (const auto* suffix : {"", "/modules", "/modules/x86_64-windows", "/modules/x86_64-unix"}) {
            const auto path = checkout + "/build/" + role + suffix;
            auto fd = absolute_directory(path);
            private_directory(fd.value);
            directory_pins.emplace_back(path, file_info(fd.value));
        }
    call.phase = SRPT_PHASE_RUNTIME;
    auto wine = pinned_runtime(srpt_launch_implementation, true);
    auto server = pinned_runtime(srpt_launch_server, false);
    auto result = std::make_unique<Configuration>(call.root, deadline, tmp, std::move(lease.temp), std::move(wine), std::move(server));
    result->production = production; result->support = support;
    result->directories = std::move(directory_pins);
    call.phase = SRPT_PHASE_ENVIRONMENT;
    result->crypto = inputs("SPACE_WINE_PUBLICATION_TEST_CRYPTO");
    require(result->crypto == "b" || result->crypto == "n");
    for (const auto* name : {"WINEPREFIX", "WINEARCH", "WINESERVER", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TMPDIR",
                           "TEMP", "TMP", "SPACE_WINE_WINDOWS_TMP", "SPACE_WINE_PUBLICATION_TEST_CRYPTO"})
        result->environment.emplace_back(std::string(name) + "=" + inputs(name));
    for (const auto* name : {"HOME", "LANG", "LC_ALL", "LC_CTYPE", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"}) {
        const auto* captured = inputs.find(name);
        if (!captured) continue;
        const auto& value = *captured;
        if (!std::strcmp(name, "HOME") || !std::strcmp(name, "XDG_RUNTIME_DIR")) {
            require(!value.empty() && value.front() == '/');
            if (!std::strcmp(name, "XDG_RUNTIME_DIR")) {
                auto fd = absolute_directory(value);
                private_directory(fd.value);
                result->directories.emplace_back(value, file_info(fd.value));
            }
        }
        result->environment.emplace_back(std::string(name) + "=" + value);
    }
    result->environment.emplace_back("PATH=");
    result->environment.emplace_back("WINEDLLOVERRIDES=space_record_publication=b;space_record_publication_tests=b;bcryptprimitives="
                                     + result->crypto + ";advapi32,cryptbase=b");
    call.phase = SRPT_PHASE_LAYOUT;
    const auto production_root = checkout + "/build/wine-publication/modules";
    const auto support_root = checkout + "/build/wine-publication-tests/modules";
    const auto overlay = checkout + "/build/wine/windows";
    fixed_module_layout();
    private_path(overlay);
    result->sources.emplace_back(artifact(production_root + "/x86_64-unix/space_record_publication.so", production.build_id.data()));
    require(result->sources.back()->info.st_dev == production.module_device
            && result->sources.back()->info.st_ino == production.module_inode, SRPT_IDENTITY_MISMATCH);
    result->sources.emplace_back(artifact(production_root + "/x86_64-windows/space_record_publication.dll", production.build_id.data()));
    result->sources.emplace_back(artifact(support_root + "/x86_64-unix/space_record_publication_tests.so", build_id));
    require(result->sources.back()->info.st_dev == support.module_device
            && result->sources.back()->info.st_ino == support.module_inode, SRPT_IDENTITY_MISMATCH);
    result->sources.emplace_back(artifact(support_root + "/x86_64-windows/space_record_publication_tests.dll", build_id));
    result->sources.emplace_back(artifact(overlay + "/space_record_publication.dll", production.build_id.data()));
    require(result->sources.back()->bytes == result->sources[1]->bytes, SRPT_IDENTITY_MISMATCH);
    result->sources.emplace_back(artifact(overlay + "/space_record_publication_tests.dll", build_id));
    require(result->sources.back()->bytes == result->sources[3]->bytes, SRPT_IDENTITY_MISMATCH);
    result->sources.emplace_back(artifact(overlay + "/test_record_publication.exe"));
    recheck_sources(*result);
    recheck_directories(*result);
    auto final_temp = absolute_directory(tmp);
    private_directory(final_temp.value);
    require(same_object(file_info(final_temp.value), file_info(result->temp.value)), SRPT_IDENTITY_MISMATCH);
    auto final_wine = pinned_runtime(srpt_launch_implementation, true);
    auto final_server = pinned_runtime(srpt_launch_server, false);
    require(pin_matches(file_info(result->implementation.value), srpt_launch_implementation)
            && pin_matches(file_info(result->server.value), srpt_launch_server), SRPT_IDENTITY_MISMATCH);
    call.remaining_ms = remaining_ms(deadline);
    {
        std::lock_guard<std::mutex> lock(root_mutex);
        configuration = std::move(result);
    }
    call.phase = SRPT_PHASE_COMPLETE;
    call.outcome = SRPT_OUTCOME_COMPLETED;
}

// Called under root_mutex only by the existing OBSERVE entry. Recording a proof
// is not a new ABI operation: the host independently reads the entire intact
// owned copy and retains its descriptor before PE intentionally damages it.
void record_intact_observation(const Root& root, const std::string& path, const SrptCall& call)
{
    if (!configuration || !launch_busy_paths.empty() || sequence_failed || call.offset || !S_ISREG(call.mode)) return;
    const auto& configured = *configuration;
    const auto absolute = root.path + "/" + path;
    const auto prefix = configured.temp_path + "/record-publication-";
    if (absolute.compare(0, prefix.size(), prefix)) return;
    const auto slash = absolute.find('/', prefix.size());
    if (slash == std::string::npos || slash == prefix.size()
        || absolute.find_first_not_of("0123456789", prefix.size()) != slash) return;
    const auto fixture_path = absolute.substr(0, slash);
    if (sequence_fixture && fixture_path != sequence_fixture_path) return;
    const auto relative = absolute.substr(slash + 1);
    for (std::size_t selected = 0; selected < case_names.size(); ++selected)
        for (std::size_t item = 0; item < copy_names.size(); ++item) {
            if (relative != std::string(case_names[selected]) + "/" + copy_names[item]) continue;
            if (selected + 1 < sequence_next_case) return;
            // OBSERVE stays descriptor-relative even when its retained parent
            // was renamed. RUN, not an ordinary read, revalidates original names.
            Fd fixture(-1);
            if (fixture_path.size() > root.path.size()) {
                require(fixture_path.compare(0, root.path.size() + 1, root.path + "/") == 0, SRPT_IDENTITY_MISMATCH);
                fixture.value = open_directory(root.fd, fixture_path.substr(root.path.size() + 1));
                host(fixture.value >= 0);
            } else {
                require(root.path == fixture_path || root.path.compare(0, fixture_path.size() + 1, fixture_path + "/") == 0,
                        SRPT_IDENTITY_MISMATCH);
                fixture.value = ::fcntl(root.fd, F_DUPFD_CLOEXEC, 3);
                host(fixture.value >= 0);
                const auto suffix = root.path.substr(fixture_path.size());
                const auto depth = std::count(suffix.begin(), suffix.end(), '/');
                require(depth <= 3, SRPT_IDENTITY_MISMATCH); // case/modules/architecture, never a caller-selected walk.
                for (std::ptrdiff_t index = 0; index < depth; ++index) {
                    const int next = ::openat(fixture.value, "..", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
                    host(next >= 0);
                    const int old = std::exchange(fixture.value, next);
                    host(::close(old) == 0);
                }
            }
            private_directory(fixture.value);
            for (const auto* suffix : {"", "/modules", "/modules/x86_64-windows", "/modules/x86_64-unix"}) {
                Fd directory(open_directory(fixture.value, std::string(case_names[selected]) + suffix));
                host(directory.value >= 0);
                private_directory(directory.value);
            }
            const auto& source = *configured.sources[item ? 1 : 0];
            auto copy = artifact_at(root.fd, path, absolute);
            require(copy->info.st_dev == call.device && copy->info.st_ino == call.inode, SRPT_IDENTITY_MISMATCH);
            // A later observation of damaged bytes is still an ordinary OBSERVE;
            // it must not manufacture or erase an earlier intact-copy receipt.
            if (copy->bytes != source.bytes) return;
            require(!same_object(copy->info, source.info) && same_file(file_info(source.descriptor.value), source.info),
                    SRPT_IDENTITY_MISMATCH);
            auto receipt = std::make_unique<CopyReceipt>();
            receipt->fixture_path = fixture_path;
            receipt->fixture_info = file_info(fixture.value);
            receipt->intact = std::move(copy);
            copy_receipts[selected * 3 + item] = std::move(receipt);
            return;
        }
}

struct RunContext {
    Fd fixture {-1};
    std::string path;
    uint64_t id;
    uint32_t selected;
    bool active = true;
    explicit RunContext(const SrptLaunch& call) : id(call.root), selected(call.case_id)
    {
        std::lock_guard<std::mutex> lock(root_mutex);
        // A concurrent request cannot cancel or reset the active preparation.
        require(configuration && launch_busy_paths.empty() && !sequence_failed);
        sequence_failed = true; // Every accepted attempt is terminal unless its future owner completes it.
        require(call.case_id == sequence_next_case && (!sequence_fixture || sequence_fixture == call.root));
        Root* retained = nullptr;
        bool have_temp = false;
        for (auto& root : roots) if (root.id) {
            if (root.id == call.root) retained = &root;
            if (root.id == configuration->temp_id) have_temp = true;
        }
        require(retained && have_temp);
        path = retained->path;
        const auto prefix = configuration->temp_path + "/record-publication-";
        require(path.compare(0, prefix.size(), prefix) == 0 && path.size() > prefix.size()
                && path.find_first_not_of("0123456789", prefix.size()) == std::string::npos
                && path.find(':') == std::string::npos);
        fixture.value = ::fcntl(retained->fd, F_DUPFD_CLOEXEC, 3);
        host(fixture.value >= 0);
        launch_busy_paths = busy_targets(configuration->temp_path);
        for (auto& root : roots) if (root.id) root.busy = root_is_busy(root, launch_busy_paths);
    }
    RunContext(RunContext&& other) noexcept
        : fixture(std::move(other.fixture)), path(std::move(other.path)), id(other.id), selected(other.selected),
          active(std::exchange(other.active, false)) {}
    ~RunContext()
    {
        if (!active) return;
        std::lock_guard<std::mutex> lock(root_mutex);
        for (auto& root : roots) root.busy = false;
        launch_busy_paths.clear();
    }
};

void check_run_context(SrptLaunch& call, const RunContext& context)
{
    const auto& configured = *configuration; // Published once under the registry lock; never replaced.
    require(binding_matches(configured.support, call.support_build_id, call.support_device, call.support_inode)
            && std::equal(configured.production.build_id.begin(), configured.production.build_id.end(), call.production_build_id)
            && call.production_inode && !(call.production_device == configured.production.module_device
                                         && call.production_inode == configured.production.module_inode), SRPT_IDENTITY_MISMATCH);
    private_directory(configured.temp.value);
    private_directory(context.fixture.value);
    auto temp_path = absolute_directory(configured.temp_path);
    require(same_object(file_info(temp_path.value), file_info(configured.temp.value)), SRPT_IDENTITY_MISMATCH);
    const auto name = context.path.substr(configured.temp_path.size() + 1);
    Fd child(::openat(configured.temp.value, name.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
    host(child.value >= 0);
    auto fixture_path = absolute_directory(context.path);
    private_directory(fixture_path.value);
    require(same_object(file_info(child.value), file_info(context.fixture.value))
            && same_object(file_info(fixture_path.value), file_info(context.fixture.value)), SRPT_IDENTITY_MISMATCH);
    call.phase = SRPT_PHASE_RUNTIME;
    auto wine = pinned_runtime(srpt_launch_implementation, true);
    auto server = pinned_runtime(srpt_launch_server, false);
    require(pin_matches(file_info(configured.implementation.value), srpt_launch_implementation)
            && pin_matches(file_info(configured.server.value), srpt_launch_server), SRPT_IDENTITY_MISMATCH);
    recheck_sources(configured);
    recheck_directories(configured);
    fixed_module_layout();
    call.remaining_ms = remaining_ms(configured.deadline);
    require(call.remaining_ms >= 13000, SRPT_UNSUCCESSFUL, ETIMEDOUT);
}

struct PreparedRun {
    // Declared first so the busy lease outlives the held acquisition descriptors.
    RunContext context;
    Fd cwd {-1};
    std::string path;
    std::vector<std::string> arguments, environment;
    std::array<std::unique_ptr<CopyReceipt>, 3> receipts;
    std::vector<std::unique_ptr<LaunchArtifact>> copies;
    explicit PreparedRun(RunContext&& owner) : context(std::move(owner)) {}
};

std::string binding_text(const uint8_t* id, uint64_t device, uint64_t inode)
{
    const char* digits = "0123456789abcdef";
    std::string result;
    for (std::size_t index = 0; index < 32; ++index) {
        result += digits[id[index] >> 4]; result += digits[id[index] & 15];
    }
    return result + ":" + std::to_string(device) + ":" + std::to_string(inode);
}

bool same_copy_policy(const struct stat& first, const struct stat& second)
{
    return same_object(first, second) && first.st_uid == second.st_uid && first.st_gid == second.st_gid
        && first.st_mode == second.st_mode;
}

bool absent(const std::string& path)
{
    const auto slash = path.rfind('/');
    auto directory = absolute_directory(path.substr(0, slash));
    struct stat info {};
    if (::fstatat(directory.value, path.c_str() + slash + 1, &info, AT_SYMLINK_NOFOLLOW) == 0) return false;
    require(errno == ENOENT, SRPT_UNSUCCESSFUL, fail_errno());
    return true;
}

void checked_copy(PreparedRun& prepared, const std::string& path, const LaunchArtifact& source)
{
    auto copy = artifact(path);
    require(copy->bytes == source.bytes && !same_object(copy->info, source.info), SRPT_IDENTITY_MISMATCH);
    prepared.copies.emplace_back(std::move(copy));
}

std::unique_ptr<PreparedRun> prepare_run(SrptLaunch& call)
{
    RunContext context(call); // Accept/fail the sequence before any preparation heap allocation.
    auto prepared = std::make_unique<PreparedRun>(std::move(context));
    check_run_context(call, prepared->context);
    const auto& configured = *configuration;
    const auto selected = call.case_id - 1;
    call.phase = SRPT_PHASE_LAYOUT;
    prepared->path = prepared->context.path + "/" + case_names[selected];
    auto cwd = absolute_directory(prepared->path);
    private_directory(cwd.value);
    prepared->cwd.value = std::exchange(cwd.value, -1);
    exact_entries(prepared->path + "/modules", {"x86_64-windows", "x86_64-unix"});
    exact_entries(prepared->path + "/modules/x86_64-windows",
                  selected == 1 ? std::vector<std::string>{} : std::vector<std::string>{"space_record_publication.dll"});
    exact_entries(prepared->path + "/modules/x86_64-unix",
                  selected == 3 ? std::vector<std::string>{} : std::vector<std::string>{"space_record_publication.so"});
    {
        std::lock_guard<std::mutex> lock(root_mutex);
        for (std::size_t item = 0; item < 3; ++item) {
            auto& receipt = copy_receipts[selected * 3 + item];
            require(receipt && receipt->fixture_path == prepared->context.path
                    && same_object(receipt->fixture_info, file_info(prepared->context.fixture.value))
                    && receipt->intact->path == prepared->path + "/" + copy_names[item], SRPT_IDENTITY_MISMATCH);
            prepared->receipts[item] = std::move(receipt);
        }
    }
    const auto& so = prepared->receipts[0]->intact->info;
    require(call.production_device == so.st_dev && call.production_inode == so.st_ino, SRPT_IDENTITY_MISMATCH);
    for (std::size_t item = 0; item < 3; ++item) {
        const auto& receipt = *prepared->receipts[item]->intact;
        const bool missing = item ? selected == 1 : selected == 3;
        const bool bad = item ? selected == 2 : selected == 4;
        if (missing) {
            const auto retained = file_info(receipt.descriptor.value);
            require(absent(receipt.path) && same_copy_policy(retained, receipt.info) && retained.st_nlink == 0,
                    SRPT_IDENTITY_MISMATCH);
        } else {
            auto current = artifact(receipt.path);
            require(same_copy_policy(current->info, receipt.info)
                    && same_file(file_info(receipt.descriptor.value), current->info), SRPT_IDENTITY_MISMATCH);
            if (bad) {
                const char* bytes = item ? "not-a-PE" : "not-an-ELF";
                require(current->bytes == std::vector<uint8_t>(bytes, bytes + std::strlen(bytes)), SRPT_IDENTITY_MISMATCH);
            } else require(same_file(current->info, receipt.info) && current->bytes == configured.sources[item ? 1 : 0]->bytes,
                           SRPT_IDENTITY_MISMATCH);
            prepared->copies.emplace_back(std::move(current));
        }
    }
    checked_copy(*prepared, prepared->path + "/test_record_publication.exe", *configured.sources[6]);
    checked_copy(*prepared, prepared->path + "/space_record_publication_tests.dll", *configured.sources[3]);
    const auto overlay = raw_path(srpt_launch_checkout) + "/build/wine/windows";
    for (const auto& name : directory_names(prepared->path)) {
        if (name == "modules" || name == "test_record_publication.exe" || name == "space_record_publication.dll"
            || name == "space_record_publication_tests.dll") continue;
        std::string lower = name;
        for (auto& unit : lower) if (unit >= 'A' && unit <= 'Z') unit += 'a' - 'A';
        require(lower.size() > 4 && lower.substr(lower.size() - 4) == ".dll"
                && lower != "space_record_publication.dll" && lower != "space_record_publication_tests.dll",
                SRPT_IDENTITY_MISMATCH);
        auto source = artifact(overlay + "/" + name);
        checked_copy(*prepared, prepared->path + "/" + name, *source);
        prepared->copies.emplace_back(std::move(source)); // Keep original dependency witness through ownership.
    }
    if (configured.crypto == "n") {
        bool found = false;
        for (const auto& copy : prepared->copies) {
            auto name = copy->path.substr(copy->path.rfind('/') + 1);
            for (auto& unit : name) if (unit >= 'A' && unit <= 'Z') unit += 'a' - 'A';
            if (name == "bcryptprimitives.dll" && copy->path.compare(0, prepared->path.size() + 1, prepared->path + "/") == 0) found = true;
        }
        require(found, SRPT_IDENTITY_MISMATCH);
    }
    call.phase = SRPT_PHASE_ENVIRONMENT;
    prepared->arguments = {raw_path(srpt_launch_implementation.path), prepared->path + "/test_record_publication.exe",
                           std::string("--wine-publication-child=") + case_names[selected]};
    prepared->environment = configured.environment;
    prepared->environment.emplace_back("WINEDLLPATH=" + prepared->path + "/modules:"
                                       + raw_path(srpt_launch_checkout) + "/build/wine-publication-tests/modules");
    prepared->environment.emplace_back("SPACE_WINE_PUBLICATION_BINDING="
                                       + binding_text(call.production_build_id, so.st_dev, so.st_ino));
    prepared->environment.emplace_back("SPACE_WINE_PUBLICATION_TEST_BINDING="
                                       + binding_text(configured.support.build_id.data(), configured.support.module_device, configured.support.module_inode));
    check_run_context(call, prepared->context);
    auto current_cwd = absolute_directory(prepared->path);
    private_directory(current_cwd.value);
    require(same_object(file_info(current_cwd.value), file_info(prepared->cwd.value)), SRPT_IDENTITY_MISMATCH);
    for (const auto& copy : prepared->copies) {
        auto current = artifact(copy->path);
        require(same_file(current->info, copy->info) && current->bytes == copy->bytes, SRPT_IDENTITY_MISMATCH);
    }
    call.remaining_ms = remaining_ms(configured.deadline);
    require(call.remaining_ms >= 13000, SRPT_UNSUCCESSFUL, ETIMEDOUT);
    {
        std::lock_guard<std::mutex> lock(root_mutex);
        if (!sequence_fixture) {
            sequence_fixture_path = prepared->context.path;
            sequence_fixture = call.root;
        }
    }
    call.phase = SRPT_PHASE_ENVIRONMENT;
    return prepared;
}

// Only an owner with a checked successful completion may advance the sequence.
// Packet B host tests invoke this for the internal preparation protocol, not as
// evidence of a successful public RUN or actual child execution.
[[maybe_unused]] void complete_preparation(const PreparedRun& prepared)
{
    std::lock_guard<std::mutex> lock(root_mutex);
    require(sequence_failed && sequence_fixture == prepared.context.id
            && sequence_next_case == prepared.context.selected);
    ++sequence_next_case;
    sequence_failed = false;
}

int close_owned(Fd& fd) noexcept
{
    const int value = std::exchange(fd.value, -1);
    return value >= 0 && ::close(value) != 0 ? fail_errno() : 0; // Never retry close on a possibly reused descriptor.
}

int close_prepared(PreparedRun& prepared) noexcept
{
    int first = 0;
    const auto close = [&](Fd& fd) { const auto error = close_owned(fd); if (!first) first = error; };
    for (auto& copy : prepared.copies) close(copy->descriptor);
    for (auto& receipt : prepared.receipts) if (receipt) close(receipt->intact->descriptor);
    close(prepared.cwd);
    close(prepared.context.fixture);
    return first;
}

struct SpawnResources {
    posix_spawn_file_actions_t actions {};
    posix_spawnattr_t attributes {};
    bool have_actions = false, have_attributes = false;
    Fd cwd {-1};
    int finish() noexcept
    {
        int first = 0;
        if (std::exchange(have_actions, false)) first = ::posix_spawn_file_actions_destroy(&actions);
        if (std::exchange(have_attributes, false)) {
            const auto error = ::posix_spawnattr_destroy(&attributes);
            if (!first) first = error;
        }
        const auto error = close_owned(cwd);
        return first ? first : error;
    }
};

void spawn_check(int error)
{
    require(!error, SRPT_UNSUCCESSFUL, error);
}

struct ChildOwnership {
    pid_t pid = -1;
    bool spawned = false, reaped = false, anchor_lost = false;
    int status = 0;
    int64_t last_now = 0;
    int64_t retirement_deadline = 0;
};

// The zombie leader is deliberately retained until ownership decisions finish.
// Exact-leader waitpid below is retirement, not completion observation.
int observe_child(ChildOwnership& child, siginfo_t& info) noexcept
{
    std::memset(&info, 0, sizeof(info));
    if (::waitid(P_PID, static_cast<id_t>(child.pid), &info, WEXITED | WNOHANG | WNOWAIT) != 0) {
        const int error = fail_errno();
        if (error != EINTR) child.anchor_lost = true;
        return error;
    }
    const bool empty = info.si_pid == 0 && info.si_code == 0 && info.si_status == 0;
    const bool exited = info.si_pid == child.pid && info.si_code == CLD_EXITED && info.si_status >= 0 && info.si_status <= 255;
    const bool signalled = info.si_pid == child.pid && (info.si_code == CLD_KILLED || info.si_code == CLD_DUMPED)
        && info.si_status > 0 && info.si_status < NSIG;
    if (!empty && !exited && !signalled) { child.anchor_lost = true; return ECHILD; }
    return 0;
}

int child_clock(ChildOwnership& child) noexcept
{
    try {
        const auto now = monotonic_ns();
        if (now < child.last_now) return EIO;
        child.last_now = now;
        return 0;
    }
    catch (const LaunchError& error) { return error.error ? error.error : EIO; }
    catch (...) { return EIO; }
}

int poll_pause(int64_t now, int64_t deadline) noexcept
{
    const auto next = std::min(deadline, now + INT64_C(10000000));
    const timespec until {static_cast<time_t>(next / INT64_C(1000000000)), static_cast<long>(next % INT64_C(1000000000))};
    return ::clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &until, nullptr);
}

bool reap_child(ChildOwnership& child, int64_t deadline, int& error) noexcept
{
    for (;;) {
        error = child_clock(child);
        if (error || child.last_now >= deadline) { if (!error) error = ETIMEDOUT; return false; }
        int status = 0;
        const auto result = ::waitpid(child.pid, &status, WNOHANG);
        if (result == child.pid) {
            if (!WIFEXITED(status) && !WIFSIGNALED(status)) { child.anchor_lost = true; error = ECHILD; return false; }
            child.reaped = true;
            child.status = status;
            return true;
        }
        if (result != 0 && !(result == -1 && errno == EINTR)) {
            child.anchor_lost = true; error = result == -1 ? fail_errno() : ECHILD; return false;
        }
        if (result == -1) continue;
        error = poll_pause(child.last_now, deadline);
        if (error && error != EINTR) return false;
    }
}

bool terminate_and_reap(ChildOwnership& child, SrptLaunch& call, int& error) noexcept
{
    if (child.anchor_lost || child.reaped) { error = ECHILD; return false; }
    if (!child.retirement_deadline) {
        child_clock(child); // If unavailable, the last proven timestamp gives a conservative reserve.
        child.retirement_deadline = std::min(child.last_now + INT64_C(2000000000),
                                             configuration->deadline - INT64_C(1000000000));
    }
    const auto deadline = child.retirement_deadline; // Never restart this reserve on EINTR or reap failure.
    siginfo_t info {};
    for (;;) {
        const auto clock_error = child_clock(child);
        if (clock_error || child.last_now >= deadline) { error = clock_error ? clock_error : ETIMEDOUT; return false; }
        error = observe_child(child, info);
        if (error == EINTR) continue;
        if (error) return false; // No blind kill after ECHILD or unproven/malformed ownership.
        break;
    }
    call.phase = SRPT_PHASE_TERMINATE;
    const int killed = ::kill(-child.pid, SIGKILL);
    const int kill_error = killed == 0 ? 0 : fail_errno();
    const bool group_retired = !kill_error || (kill_error == ESRCH && info.si_pid == child.pid);
    call.phase = SRPT_PHASE_REAP;
    int reap_error = 0;
    const bool reaped = reap_child(child, deadline, reap_error);
    error = kill_error && !group_retired ? kill_error : reap_error;
    return group_retired && reaped;
}

void child_result(const ChildOwnership& child, SrptLaunch& call) noexcept
{
    if (!child.reaped) return;
    if (WIFEXITED(child.status)) { call.exit_code = WEXITSTATUS(child.status); call.term_signal = 0; }
    else { call.exit_code = UINT32_MAX; call.term_signal = WTERMSIG(child.status); }
}

void runtime_recheck()
{
    auto implementation = pinned_runtime(srpt_launch_implementation, true);
    auto server = pinned_runtime(srpt_launch_server, false);
    require(pin_matches(file_info(configuration->implementation.value), srpt_launch_implementation)
            && pin_matches(file_info(configuration->server.value), srpt_launch_server), SRPT_IDENTITY_MISMATCH);
    spawn_check(close_owned(implementation));
    spawn_check(close_owned(server));
}

std::unique_ptr<PreparedRun> uncertain_preparation;
pid_t uncertain_leader = -1;

int32_t execute_run(SrptLaunch& call, std::unique_ptr<PreparedRun>& prepared) noexcept
{
    SpawnResources resources;
    ChildOwnership child;
    int32_t failure_status = SRPT_UNSUCCESSFUL;
    int failure_error = 0;
    bool timed_out = false, child_failure = false;
    try {
        call.phase = SRPT_PHASE_SPAWN;
        struct sigaction parent {};
        host(::sigaction(SIGCHLD, nullptr, &parent) == 0);
        require(parent.sa_handler != SIG_IGN && !(parent.sa_flags & SA_NOCLDWAIT), SRPT_UNSUCCESSFUL, ECHILD);
        for (const int fd : {STDOUT_FILENO, STDERR_FILENO}) {
            const int flags = ::fcntl(fd, F_GETFL), descriptor = ::fcntl(fd, F_GETFD);
            host(flags >= 0 && descriptor >= 0);
            require((flags & O_ACCMODE) != O_RDONLY && !(descriptor & FD_CLOEXEC), SRPT_UNSUCCESSFUL, EBADF);
        }
        std::vector<char*> arguments, environment;
        for (auto& value : prepared->arguments) arguments.push_back(value.data());
        arguments.push_back(nullptr);
        for (auto& value : prepared->environment) environment.push_back(value.data());
        environment.push_back(nullptr);
        spawn_check(::posix_spawn_file_actions_init(&resources.actions)); resources.have_actions = true;
        spawn_check(::posix_spawnattr_init(&resources.attributes)); resources.have_attributes = true;
        resources.cwd.value = ::fcntl(prepared->cwd.value, F_DUPFD_CLOEXEC, 3);
        host(resources.cwd.value >= 0);
        spawn_check(::posix_spawn_file_actions_addopen(&resources.actions, STDIN_FILENO, "/dev/null", O_RDONLY, 0));
        spawn_check(::posix_spawn_file_actions_addfchdir_np(&resources.actions, resources.cwd.value));
        spawn_check(::posix_spawn_file_actions_addclosefrom_np(&resources.actions, 3));
        sigset_t empty, defaults;
        host(::sigemptyset(&empty) == 0 && ::sigfillset(&defaults) == 0
             && ::sigdelset(&defaults, SIGKILL) == 0 && ::sigdelset(&defaults, SIGSTOP) == 0);
        spawn_check(::posix_spawnattr_setsigmask(&resources.attributes, &empty));
        spawn_check(::posix_spawnattr_setsigdefault(&resources.attributes, &defaults));
        spawn_check(::posix_spawnattr_setpgroup(&resources.attributes, 0));
        spawn_check(::posix_spawnattr_setflags(&resources.attributes,
                     POSIX_SPAWN_SETSIGMASK | POSIX_SPAWN_SETSIGDEF | POSIX_SPAWN_SETPGROUP));
        call.phase = SRPT_PHASE_RUNTIME;
        runtime_recheck();
        spawn_check(child_clock(child));
        require(configuration->deadline - child.last_now >= INT64_C(13000000000), SRPT_UNSUCCESSFUL, ETIMEDOUT);
        const auto wait_deadline = child.last_now + INT64_C(10000000000);
        call.phase = SRPT_PHASE_SPAWN;
        const auto spawned = ::posix_spawn(&child.pid, prepared->arguments[0].c_str(), &resources.actions,
                                           &resources.attributes, arguments.data(), environment.data());
        if (spawned) {
            if (child.pid > 0) child.anchor_lost = true; // An error does not confer ownership of an output PID.
            throw LaunchError {SRPT_UNSUCCESSFUL, spawned};
        }
        child.spawned = true; // Set before any fallible post-spawn operation.
        if (child.pid <= 0) { child.anchor_lost = true; throw LaunchError {SRPT_UNSUCCESSFUL, ECHILD}; }
        spawn_check(resources.finish());
        call.phase = SRPT_PHASE_RUNTIME;
        runtime_recheck();
        call.phase = SRPT_PHASE_WAIT;
        for (;;) {
            spawn_check(child_clock(child));
            if (child.last_now >= wait_deadline) { timed_out = true; throw LaunchError {SRPT_UNSUCCESSFUL, ETIMEDOUT}; }
            siginfo_t info {};
            const auto observed = observe_child(child, info);
            if (observed == EINTR) continue;
            spawn_check(observed);
            if (info.si_pid == child.pid) {
                if (info.si_code != CLD_EXITED || info.si_status != 0) {
                    child_failure = true;
                    throw LaunchError {SRPT_UNSUCCESSFUL, 0};
                }
                call.phase = SRPT_PHASE_REAP;
                int error = 0;
                child.retirement_deadline = std::min(child.last_now + INT64_C(2000000000),
                                                     configuration->deadline - INT64_C(1000000000));
                const bool reaped = reap_child(child, child.retirement_deadline, error);
                require(reaped, SRPT_UNSUCCESSFUL, error);
                if (!WIFEXITED(child.status) || WEXITSTATUS(child.status) != 0) {
                    child.anchor_lost = true; throw LaunchError {SRPT_UNSUCCESSFUL, ECHILD};
                }
                child_result(child, call);
                // Ownership has ended. Close errors cannot justify killing a reused group ID.
                spawn_check(close_prepared(*prepared));
                call.remaining_ms = remaining_ms(configuration->deadline);
                complete_preparation(*prepared);
                call.phase = SRPT_PHASE_COMPLETE; call.os_error = 0; call.outcome = SRPT_OUTCOME_COMPLETED;
                return SRPT_SUCCESS;
            }
            const auto paused = poll_pause(child.last_now, wait_deadline);
            if (paused != EINTR) spawn_check(paused);
        }
    } catch (const LaunchError& error) { failure_status = error.status; failure_error = error.error; }
    catch (...) { failure_error = EIO; }
    const auto resource_error = resources.finish();
    if (!failure_error) failure_error = resource_error;
    bool retired = !child.spawned && !child.anchor_lost;
    if (child.spawned && !child.reaped) {
        int error = 0;
        retired = terminate_and_reap(child, call, error);
        if (!retired && error) failure_error = error;
    } else if (child.reaped && !child.anchor_lost) retired = true;
    child_result(child, call);
    if (!retired) {
        uncertain_leader = child.pid;
        uncertain_preparation = std::move(prepared); // No allocation; evidence and busy contexts remain owned.
        call.os_error = failure_error ? failure_error : ECHILD;
        call.outcome = SRPT_OUTCOME_OWNERSHIP_UNCERTAIN;
        return SRPT_UNSUCCESSFUL;
    }
    const auto close_error = close_prepared(*prepared);
    call.os_error = close_error ? close_error : failure_error;
    call.outcome = close_error || resource_error ? SRPT_OUTCOME_HOST_FAILURE
        : timed_out ? SRPT_OUTCOME_TIMED_OUT_AND_REAPED
        : child_failure ? SRPT_OUTCOME_EXITED_OR_SIGNALLED : SRPT_OUTCOME_HOST_FAILURE;
    return close_error || resource_error ? SRPT_UNSUCCESSFUL : failure_status;
}

void end_failed_preparation()
{
    std::lock_guard<std::mutex> lock(root_mutex);
    // A rejected concurrent request must not discard an active owner's proofs.
    if (sequence_failed && launch_busy_paths.empty()) for (auto& receipt : copy_receipts) receipt.reset();
}

bool initialize_launch(SrptLaunch* call)
{
    if (!call || call->size != sizeof(*call) || call->abi != SRPT_ABI) return false;
    const bool valid = ((call->action == SRPT_CONFIGURE && call->case_id == 0)
                        || (call->action == SRPT_RUN && call->case_id >= 1 && call->case_id <= 5))
        && !call->phase && !call->os_error && !call->exit_code && !call->term_signal
        && !call->outcome && !call->reserved && !call->remaining_ms && !call->reserved2;
    call->phase = SRPT_PHASE_INPUT; call->os_error = 0; call->exit_code = UINT32_MAX;
    call->term_signal = 0; call->outcome = SRPT_OUTCOME_UNSET; call->remaining_ms = 0;
    return valid;
}

int32_t launch(void* args) noexcept
{
    auto* call = static_cast<SrptLaunch*>(args);
    if (!initialize_launch(call)) return SRPT_INVALID_ARGUMENT;
    try {
        call->phase = SRPT_PHASE_CONTEXT;
        if (call->action == SRPT_CONFIGURE) {
            configure(*call);
            return SRPT_SUCCESS;
        }
        auto prepared = prepare_run(*call);
        const auto status = execute_run(*call, prepared);
        prepared.reset();
        end_failed_preparation();
        return status;
    } catch (const LaunchError& error) {
        end_failed_preparation();
        call->os_error = error.error;
        call->outcome = SRPT_OUTCOME_HOST_FAILURE;
        return error.status;
    } catch (...) {
        end_failed_preparation();
        call->os_error = EIO;
        call->outcome = SRPT_OUTCOME_HOST_FAILURE;
        return SRPT_UNSUCCESSFUL;
    }
}
} // namespace

extern "C" {
extern __attribute__((visibility("default"))) const uint8_t SpaceRecordPublicationTestsUnixBuildId[32] = SRPT_BUILD_ID_BYTES;
extern __attribute__((visibility("default"))) const Entry __wine_unix_call_funcs[] = {identity, fixture, launch};
}
