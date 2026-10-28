#include "record_publication_selinux.h"
#include "record_publication.h"
#include <array>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <cstdio>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <sys/xattr.h>
#include <unistd.h>

namespace fs = std::filesystem;
namespace security = record_publication::selinux;
namespace {
bool label_write_attempted = false;
bool deny_task_inspection = false;
bool simulate_override = false, override_delivered = false, simulate_policy_change = false;
int kernel_queries = 0;
void check(bool value, const char* reason) { if (!value) throw std::runtime_error(reason); }
template<typename Function> void refuses(Function action)
{
    bool refused = false;
    try { action(); } catch (const std::exception&) { refused = true; }
    check(refused, "unsafe/unstable authority must refuse");
}
struct Fd {
    int value;
    explicit Fd(const fs::path& path, int flags) : value(::open(path.c_str(), flags, 0600))
    { check(value >= 0, "open fixture"); }
    ~Fd() { ::close(value); }
};
struct Fixture {
    fs::path root = fs::temp_directory_path() / ("publication-selinux-" + std::to_string(
        std::chrono::steady_clock::now().time_since_epoch().count()));
    Fixture() { fs::create_directory(root); }
    ~Fixture() { std::error_code ignored; fs::remove_all(root, ignored); }
};
void write(const fs::path& path, const std::string& value)
{
    std::ofstream stream(path); stream << value; check(bool(stream), "write fixture");
}
void test()
{
    check(security::supported_mount_options("tmpfs", "rw", "rw,seclabel"), "ordinary tmpfs supported");
    check(!security::supported_mount_options("ext4", "rw", "rw,seclabel"), "uninspected filesystem not predicted");
    check(!security::supported_mount_options("tmpfs", "rw", "rw,notseclabel"), "exact option tokens required");
    for (const char* option : {"context=foo", "fscontext=foo", "rootcontext=foo", "defcontext=foo"})
        check(!security::supported_mount_options("tmpfs", "seclabel", std::string("rw,") + option), "override mount refused");
    Fixture fixture;
    Fd parent(fixture.root, O_RDONLY | O_DIRECTORY);
    const auto target = fs::canonical(fixture.root) / "final";
    Fd stage(fixture.root / "stage", O_RDWR | O_CREAT | O_EXCL);
    const auto label = security::inspect(stage.value);
    security::validate_metadata(stage.value, &label);
    auto mismatch = label;
    if (mismatch) mismatch->insert(0, "prefix"); else mismatch = std::string("context\0", 8);
    refuses([&] { security::validate_metadata(stage.value, &mismatch); });
    check(::fsetxattr(stage.value, "user.unsupported", "x", 1, 0) == 0, "unknown metadata fixture");
    refuses([&] { security::inspect(stage.value); });
    check(::fremovexattr(stage.value, "user.unsupported") == 0, "remove test-only user attribute");
    if (label) {
        security::NewLabelAuthority ordinary(parent.value, target);
        ordinary.validate(stage.value);
        simulate_override = true;
        override_delivered = false;
        refuses([&] { ordinary.validate(stage.value); });
        simulate_override = false;
        check(override_delivered, "fscreate override injection must execute");
        simulate_policy_change = true;
        refuses([&] { ordinary.validate(stage.value); });
        simulate_policy_change = false;
        const auto specs = fixture.root / "contexts";
        const std::string context(label->data(), label->size() - 1);
        write(specs, target.string() + " " + context + "\n");
        const auto fixed = security::default_context(target, specs);
        check(fixed.fixed == label, "positive default retains complete context");
        const int before = kernel_queries;
        security::NewLabelAuthority positive(parent.value, target, specs);
        positive.validate(stage.value);
        check(kernel_queries == before, "fixed default must never fall through to kernel prediction");
        write(specs, target.string() + " <<none>>\n");
        check(!security::default_context(target, specs).fixed, "genuine none opens kernel default branch");
        refuses([&] { positive.validate(stage.value); });
        check(::lseek(stage.value, 0, SEEK_END) == 0, "authority mismatch is detected before payload");
        security::NewLabelAuthority none(parent.value, target, specs);
        none.validate(stage.value);
        write(specs.string() + ".local", target.string() + " " + context + "\n");
        refuses([&] { none.validate(stage.value); });
        fs::remove(specs.string() + ".local");
        fs::remove(specs);
        refuses([&] { security::NewLabelAuthority missing(parent.value, target, specs); });
        deny_task_inspection = true;
        refuses([&] { ordinary.validate(stage.value); });
        deny_task_inspection = false;
        const auto moved = fixture.root.string() + "-moved";
        fs::rename(fixture.root, moved);
        fs::create_directory(fixture.root);
        refuses([&] { ordinary.validate(stage.value); });
        check(!fs::exists(fixture.root / "final"), "substituted canonical path receives no bytes");
        fs::remove(fixture.root);
        fs::rename(moved, fixture.root);
        std::cout << "enforcing-host authority/default/path tests exercised\n";
    } else {
        std::cout << "host has no SELinux labels: real-kernel authority coverage unavailable\n";
    }
    check(!label_write_attempted, "no label setter may execute");
}
} // namespace

extern "C" int __real_fsetxattr(int, const char*, const void*, size_t, int);
extern "C" int __wrap_fsetxattr(int fd, const char* name, const void* value, size_t size, int flags)
{
    if (!std::strcmp(name, "security.selinux")) { label_write_attempted = true; errno = EPERM; return -1; }
    return __real_fsetxattr(fd, name, value, size, flags);
}
extern "C" int __real_setxattr(const char*, const char*, const void*, size_t, int);
extern "C" int __wrap_setxattr(const char* path, const char* name, const void* value, size_t size, int flags)
{
    if (!std::strcmp(name, "security.selinux")) { label_write_attempted = true; errno = EPERM; return -1; }
    return __real_setxattr(path, name, value, size, flags);
}
extern "C" int __real_lsetxattr(const char*, const char*, const void*, size_t, int);
extern "C" int __wrap_lsetxattr(const char* path, const char* name, const void* value, size_t size, int flags)
{
    if (!std::strcmp(name, "security.selinux")) { label_write_attempted = true; errno = EPERM; return -1; }
    return __real_lsetxattr(path, name, value, size, flags);
}
extern "C" int __real_security_compute_create_name_raw(const char*, const char*, unsigned short, const char*, char**);
extern "C" int __wrap_security_compute_create_name_raw(const char* task, const char* parent, unsigned short kind,
                                                        const char* name, char** result)
{
    ++kernel_queries;
    return __real_security_compute_create_name_raw(task, parent, kind, name, result);
}
extern "C" ssize_t __real_read(int, void*, size_t);
extern "C" ssize_t __wrap_read(int fd, void* data, size_t size)
{
    if (deny_task_inspection) { errno = EACCES; return -1; }
    if (simulate_override) {
        char name[64], target[256];
        std::snprintf(name, sizeof(name), "/proc/thread-self/fd/%d", fd);
        const ssize_t length = ::readlink(name, target, sizeof(target) - 1);
        if (length > 0) {
            target[length] = '\0';
            if (std::strstr(target, "/attr/fscreate")) {
                if (override_delivered) return 0;
                const char value[] = "fixture-context";
                check(size >= sizeof(value), "override fixture read size");
                std::memcpy(data, value, sizeof(value));
                override_delivered = true;
                return sizeof(value);
            }
        }
    }
    return __real_read(fd, data, size);
}
extern "C" int __real_selinux_status_policyload();
extern "C" int __wrap_selinux_status_policyload()
{
    const int actual = __real_selinux_status_policyload();
    return actual + (simulate_policy_change ? 1 : 0);
}
int main()
{
    try { test(); return 0; }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
