// Wine9 unixlib_entry_t is NTSTATUS (*)(void *), using the native host ABI.
// No Wine runtime is needed to compile/test this native operation/identity library.
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include "record_publication_wine_abi.h"
#include "record_publication_unix.h"

#ifndef SRP_BUILD_ID_BYTES
#error "The fixed publication builder must supply SRP_BUILD_ID_BYTES"
#endif
#if !defined(__linux__) || !defined(__x86_64__)
#error "The publication Unix module supports only Linux x86_64"
#endif

using NTSTATUS = int32_t;
using unixlib_entry_t = NTSTATUS (*)(void*);
static_assert(sizeof(NTSTATUS) == 4 && sizeof(void*) == 8, "Wine9 x64 Unix call ABI");

namespace {
const uint8_t build_id[32] = SRP_BUILD_ID_BYTES;
const unsigned char module_marker = 0;

NTSTATUS identity(void* args) noexcept
{
    try {
        auto* input = static_cast<SrpIdentity*>(args);
        if (!input || input->size != sizeof(SrpIdentity) || input->abi != SRP_ABI)
            return SRP_INVALID_ARGUMENT;
        Dl_info module {};
        // A private, non-preemptible address identifies this SO, never a symbol
        // potentially interposed by the main executable or a different library.
        if (!::dladdr(&module_marker, &module) || !module.dli_fname)
            return SRP_MODULE_UNAVAILABLE;
        const int fd = ::open(module.dli_fname, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
        if (fd < 0) return SRP_MODULE_UNAVAILABLE;
        struct stat info {};
        const bool inspected = ::fstat(fd, &info) == 0 && S_ISREG(info.st_mode);
        const bool closed = ::close(fd) == 0;
        if (!inspected || !closed) return SRP_UNSUCCESSFUL;
        static_assert(sizeof(info.st_dev) <= sizeof(uint64_t) && sizeof(info.st_ino) <= sizeof(uint64_t),
            "module identity fits private ABI");
        SrpIdentity result = *input;
        result.echo = input->challenge;
        std::memcpy(result.unix_build_id, build_id, sizeof(build_id));
        result.module_device = info.st_dev;
        result.module_inode = info.st_ino;
        result.architecture = SRP_ARCH_X86_64;
        result.features = SRP_REQUIRED_FEATURES;
        *input = result;
        return SRP_SUCCESS;
    } catch (...) {
        return SRP_UNSUCCESSFUL; // Exceptions never cross Wine's C boundary.
    }
}

NTSTATUS operation(void* args) noexcept
{
    return srp_unix_call(static_cast<SrpCall*>(args));
}
} // namespace

extern "C" {
extern __attribute__((visibility("default"))) const uint8_t SpaceRecordPublicationUnixBuildId[32] = SRP_BUILD_ID_BYTES;
extern __attribute__((visibility("default"))) const unixlib_entry_t __wine_unix_call_funcs[] = {identity, operation};
}
