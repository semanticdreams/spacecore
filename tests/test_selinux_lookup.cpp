#include <pcre2.h>
#pragma GCC visibility push(hidden)
extern "C" {
#include <selinux/label.h>
#include <selinux/selinux.h>
}
#pragma GCC visibility pop

#include <dlfcn.h>
#include <cerrno>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;
namespace {
bool inject_match_failure = false;
bool injection_observed = false;
void check(bool condition, const char* message)
{
    if (!condition) throw std::runtime_error(message);
}
struct Fixture {
    fs::path root = fs::temp_directory_path() / ("selinux-lookup-" + std::to_string(
        std::chrono::steady_clock::now().time_since_epoch().count()));
    Fixture() { fs::create_directories(root); }
    ~Fixture() { std::error_code ignored; fs::remove_all(root, ignored); }
};
using Backend = std::unique_ptr<selabel_handle, decltype(&selabel_close)>;
Backend backend(const fs::path& file)
{
    const std::string path = file.string();
    selinux_opt options[] {{SELABEL_OPT_PATH, path.c_str()}, {SELABEL_OPT_BASEONLY, "1"}};
    Backend result(selabel_open(SELABEL_CTX_FILE, options, 2), selabel_close);
    check(bool(result), "fixture backend must open");
    return result;
}
int lookup(selabel_handle* handle, const char* path, const char* expected = nullptr)
{
    char* raw = nullptr;
    errno = 0;
    const int result = selabel_lookup_raw(handle, &raw, path, 0100600);
    const int error = errno;
    std::unique_ptr<char, decltype(&freecon)> context(raw, freecon);
    if (expected) check(result == 0 && raw && std::string(raw) == expected, "fixed default must match exactly");
    else check(result == -1, "negative/error fixture must not produce a label");
    return error;
}
void run(bool load_system_first)
{
    void* system = nullptr;
    if (load_system_first) system = dlopen("libselinux.so.1", RTLD_NOW | RTLD_GLOBAL);
    Fixture fixture;
    const auto specs = fixture.root / "file_contexts";
    {
        std::ofstream stream(specs);
        stream << "/space/fixed system_u:object_r:tmp_t:s0\n"
                  "/space/none <<none>>\n"
                  "/space/regex(/.*)? system_u:object_r:tmp_t:s0\n";
        check(bool(stream), "write fixture specs");
    }
    auto handle = backend(specs);
    lookup(handle.get(), "/space/fixed", "system_u:object_r:tmp_t:s0");
    check(lookup(handle.get(), "/space/missing") == ENOENT, "unmatched path must remain a negative");
    check(lookup(handle.get(), "/space/none") == ENOENT, "none sentinel must remain a negative");
    inject_match_failure = true;
    injection_observed = false;
    const int failure = lookup(handle.get(), "/space/regex/child");
    inject_match_failure = false;
    check(injection_observed, "PCRE2 runtime injection must execute");
    check(failure == EIO, "regex execution failure must not masquerade as ENOENT");
    if (!system) system = dlopen("libselinux.so.1", RTLD_NOW | RTLD_GLOBAL);
    check(system != nullptr, "system libselinux must be available for coexistence coverage");
    check(dlsym(system, "selabel_lookup_raw") != reinterpret_cast<void*>(&selabel_lookup_raw),
          "private and system lookup definitions must be independent");
    // Loading a global system copy cannot change private patched behavior.
    inject_match_failure = true;
    check(lookup(handle.get(), "/space/regex/child") == EIO, "global system DSO must not interpose private lookup");
    inject_match_failure = false;
    dlclose(system);
    const auto broken = fixture.root / "broken";
    { std::ofstream stream(broken); stream << "/space/broken( system_u:object_r:tmp_t:s0\n"; }
    auto invalid = backend(broken);
    check(lookup(invalid.get(), "/space/broken") == EIO, "compile failure must not masquerade as ENOENT");
}
} // namespace

extern "C" int __real_pcre2_match_8(const pcre2_code_8*, PCRE2_SPTR8, PCRE2_SIZE,
                                    PCRE2_SIZE, uint32_t, pcre2_match_data_8*, pcre2_match_context_8*);
extern "C" int __wrap_pcre2_match_8(const pcre2_code_8* code, PCRE2_SPTR8 subject, PCRE2_SIZE size,
                                    PCRE2_SIZE start, uint32_t options, pcre2_match_data_8* data,
                                    pcre2_match_context_8* context)
{
    if (inject_match_failure) { injection_observed = true; return PCRE2_ERROR_MATCHLIMIT; }
    return __real_pcre2_match_8(code, subject, size, start, options, data, context);
}
extern "C" int space_selinux_lookup_probe(int system_first)
{
    try { run(system_first != 0); std::cout << "isolated corrected SELinux lookup passed\n"; return 0; }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
#ifndef SPACE_SELINUX_SHARED_PROBE
int main(int argc, char**) { return space_selinux_lookup_probe(argc > 1); }
#endif
