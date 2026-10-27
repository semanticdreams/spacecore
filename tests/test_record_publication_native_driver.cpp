#include "record_publication.h"
#include "record_publication_operation.h"

#include <array>
#include <cerrno>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

namespace allocation_test {
extern thread_local bool disabled, fail_next;
extern thread_local long fail_after;
extern thread_local unsigned allocations, one_shot_failures;
}

// Executable-local syscall adapter: consume a real descriptor, then report a
// close error and fail its diagnostic allocation. Never installed in production.
namespace {
thread_local int fault_close = -1;
thread_local unsigned fault_closes = 0;
}
extern "C" int __real_close(int);
extern "C" int __wrap_close(int fd)
{
    const int result = __real_close(fd);
    if (fd == fault_close) {
        fault_close = -1;
        ++fault_closes;
        allocation_test::fail_next = true;
        errno = EIO;
        return -1;
    }
    return result;
}

namespace {
namespace fs = std::filesystem;
namespace rp = record_publication;
using rp::detail::Operation;
using rp::detail::Phase;

void check(bool value, const char* message)
{
    if (!value) throw std::runtime_error(message);
}

struct Fixture {
    fs::path root, path, attempt;
    std::array<int, 4> retained {};
    Fixture()
    {
        std::string name = (fs::temp_directory_path() / "record-native-XXXXXX").string();
        check(::mkdtemp(name.data()), "native fixture");
        root = name; path = root / "record";
    }
    ~Fixture() { std::error_code error; fs::remove_all(root, error); }
    void capture()
    {
        attempt = fs::directory_iterator(root / ".space-publication")->path();
        std::array<struct stat, 4> identities {};
        unsigned index = 0;
        for (const auto& name : {path, attempt, root / ".space-publication", root})
            check(::stat(name.c_str(), &identities[index++]) == 0, "capture identity");
        index = 0;
        for (int fd = 3; fd < 1024; ++fd) {
            struct stat value {};
            if (::fstat(fd, &value)) continue;
            for (const auto& identity : identities) {
                if (identity.st_dev != value.st_dev || identity.st_ino != value.st_ino) continue;
                check(index < retained.size(), "only four retained descriptors");
                retained[index++] = fd;
            }
        }
        check(index == retained.size(), "capture all retained descriptors");
    }
    void finalized() const
    {
        for (int fd : retained)
            check(::fcntl(fd, F_GETFD) == -1 && errno == EBADF, "explicit finalization while Operation is alive");
    }
    void committed() const
    {
        std::ifstream in(path);
        std::string bytes; in >> bytes;
        check(bytes == "committed", "native driver really committed bytes");
    }
    void obstruct()
    {
        std::ofstream out(attempt / "unrelated"); out << "keep"; out.close();
        check(bool(out), "obstruction fixture");
    }
};

void reach_cleanup(Operation& operation)
{
    while (operation.state().phase != Phase::before_cleanup) {
        check(operation.state().phase != Phase::done, "reach native cleanup");
        operation.advance({operation.state().phase, false, {}});
    }
}

unsigned cleanup_allocations()
{
    Fixture fixture;
    Operation operation(fixture.path, "committed");
    reach_cleanup(operation);
    fixture.capture(); fixture.obstruct();
    const auto start = allocation_test::allocations;
    operation.advance({Phase::before_cleanup, false, {}});
    const auto count = allocation_test::allocations - start;
    fixture.finalized();
    check(count >= 2 && operation.state().cleanup_error.has_value(), "calibrate native diagnostic allocations");
    return count;
}

void native_one_shot(unsigned mode, unsigned cleanup_count)
{
    Fixture fixture;
    const std::runtime_error hook_error(std::string(5000, 'n'));
    unsigned hooks = 0;
    rp::Hooks callbacks;
    callbacks.before_cleanup = [&] {
        ++hooks;
        fixture.capture();
        if (mode >= 2 && mode != 3) fixture.obstruct();
        if (mode == 3) fault_close = fixture.retained[0];
        else allocation_test::fail_after = mode < 2 ? mode : mode == 2 ? 0 :
            mode == 4 ? cleanup_count - 1 : cleanup_count;
        if (mode < 2) throw hook_error;
    };
    const auto before = allocation_test::one_shot_failures;
    const auto result = rp::publish(fixture.path, "committed", callbacks); // DIRECT native driver.
    check(allocation_test::one_shot_failures == before + 1 && allocation_test::fail_after == -1
        && !allocation_test::fail_next, "exactly one intended native allocation failed");
    check(result.committed && result.cleanup_error && !result.cleanup_error->empty(), "truthful native recovery diagnostic");
    check(hooks == 1, "native cleanup hook never replayed");
    fixture.finalized(); fixture.committed();
    if (mode >= 2 && mode != 3) {
        std::ifstream in(fixture.attempt / "unrelated");
        std::string bytes; in >> bytes;
        check(bytes == "keep", "native recovery preserves unowned entries");
    } else check(fs::is_empty(fixture.root / ".space-publication"), "bounded native namespace cleanup");
}

void alive_finalization(unsigned mode)
{
    Fixture fixture;
    Operation operation(fixture.path, "committed");
    reach_cleanup(operation);
    fixture.capture();
    if (mode == 0) {
        // Refused identity must still finalize every retained descriptor.
        fs::rename(fixture.attempt, fixture.attempt.string() + "-moved");
        fs::create_directory(fixture.attempt);
    } else if (mode == 1) fixture.obstruct();
    else fault_close = fixture.retained[0];
    if (mode != 2) allocation_test::fail_next = true;
    operation.advance({Phase::before_cleanup, false, {}});
    check(operation.state().phase == Phase::done, "diagnostic interruption reaches terminal cleanup");
    fixture.finalized(); fixture.committed(); // Before Operation's destructor can conceal omissions.
    if (mode == 0) check(fs::is_directory(fixture.attempt), "substituted namespace preserved");
}

template<class Action>
void child_check(Action action, int expected)
{
    const auto pid = ::fork(); check(pid >= 0, "native fault fork");
    if (!pid) {
        std::set_terminate([] { ::_exit(86); });
        try { action(); ::_exit(0); } catch (...) { ::_exit(87); }
    }
    int status = 0;
    check(::waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == expected,
        "native fault child must return truthful result or explicitly fail-stop, never escape");
}
}

void native_driver_allocation_tests()
{
    const unsigned count = cleanup_allocations();
    for (unsigned mode = 0; mode < 6; ++mode)
        child_check([=] { native_one_shot(mode, count); }, 0);
    for (unsigned mode = 0; mode < 3; ++mode)
        child_check([=] { alive_finalization(mode); }, 0);
    Fixture fixture; // Parent owns cleanup even when the child fail-stops via _exit.
    child_check([&] {
        rp::Hooks hooks;
        hooks.before_cleanup = [] { allocation_test::disabled = true; };
        // Force a postcommit diagnostic with an allocation-free exception copy.
        const std::runtime_error error(std::string(5000, 'p'));
        hooks.before_cleanup = [&] { allocation_test::disabled = true; throw error; };
        rp::publish(fixture.path, "committed", hooks);
    }, 86);
}
