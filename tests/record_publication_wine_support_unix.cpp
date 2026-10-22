// Test-only Wine9 Unix entries, callable as an actual ELF in host-native tests.
#include "record_publication_wine_support.h"

#include <array>
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <limits>
#include <mutex>
#include <string>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/xattr.h>
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

struct Root { uint64_t id = 0; int fd = -1; };
std::array<Root, 64> roots;
uint64_t next_id = 1;
std::mutex root_mutex; // No locks span PE hooks; each fixture call is synchronous.

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
            slot->fd = acquired.value;
            acquired.value = -1;
            slot->id = next_id++;
            call->root = slot->id;
            return SRPT_SUCCESS;
        }
        Root* owned = nullptr;
        for (auto& root : roots) if (root.id && root.id == call->root) { owned = &root; break; }
        if (!owned) return SRPT_INVALID_ARGUMENT;
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
        } else error = mutate(owned->fd, path, other, *call);
        call->os_error = error;
        return error ? SRPT_UNSUCCESSFUL : SRPT_SUCCESS;
    } catch (...) {
        call->os_error = EIO;
        return SRPT_UNSUCCESSFUL; // No exception escapes the native entry table.
    }
}
} // namespace

extern "C" {
extern __attribute__((visibility("default"))) const uint8_t SpaceRecordPublicationTestsUnixBuildId[32] = SRPT_BUILD_ID_BYTES;
extern __attribute__((visibility("default"))) const Entry __wine_unix_call_funcs[] = {identity, fixture};
}
