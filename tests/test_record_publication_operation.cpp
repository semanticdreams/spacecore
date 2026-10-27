#include "record_publication.h"
#include "record_publication_operation.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

#ifndef _WIN32
#include <fcntl.h>
#include <sys/resource.h>
#include <unistd.h>
#endif

namespace fs = std::filesystem;
namespace rp = record_publication;
using rp::detail::Operation;
using rp::detail::Phase;
using rp::detail::Reply;
static_assert(static_cast<int>(Phase::start) == 0 && static_cast<int>(Phase::before_write) == 1
    && static_cast<int>(Phase::before_security) == 2 && static_cast<int>(Phase::before_commit) == 3
    && static_cast<int>(Phase::before_cleanup) == 4 && static_cast<int>(Phase::done) == 5);
static_assert(!std::is_copy_constructible_v<Operation> && !std::is_copy_assignable_v<Operation>);
static_assert(noexcept(std::declval<const Operation&>().state()));
namespace {

void check(bool condition, const std::string& message)
{
    if (!condition) throw std::runtime_error(message);
}

struct Fixture {
    fs::path root;
    Fixture()
    {
#ifdef _WIN32
        root = fs::temp_directory_path() / ("record-operation-" + std::to_string(
            std::chrono::steady_clock::now().time_since_epoch().count()));
        check(fs::create_directory(root), "exclusive fixture creation");
#else
        auto pattern = (fs::temp_directory_path() / "record-operation-XXXXXX").string();
        std::vector<char> name(pattern.begin(), pattern.end());
        name.push_back('\0');
        check(::mkdtemp(name.data()) != nullptr, "exclusive private fixture creation");
        root = name.data();
#endif
    }
    ~Fixture()
    {
        std::error_code ignored;
        fs::remove_all(root, ignored);
    }
};

std::string read(const fs::path& path)
{
    std::ifstream input(path, std::ios::binary);
    check(static_cast<bool>(input), "fixture read failed");
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

void write(const fs::path& path, const std::string& bytes)
{
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    output << bytes;
    output.close();
    check(static_cast<bool>(output), "fixture write failed");
}

template<typename Function>
std::string rejects(Function action)
{
    try { action(); }
    catch (const std::exception& error) { return error.what(); }
    throw std::runtime_error("expected explicit rejection");
}

fs::path only_attempt(const fs::path& root)
{
    std::vector<fs::path> paths;
    for (const auto& item : fs::directory_iterator(root / ".space-publication")) paths.push_back(item.path());
    check(paths.size() == 1, "one owned workspace expected");
    return paths.front();
}

void clean_anchor(const fs::path& root)
{
    check(fs::is_empty(root / ".space-publication"), "explicit cleanup must remove owned workspace");
}

Phase next(Operation& operation)
{
    return operation.advance({operation.state().phase, false, {}});
}

void reach(Operation& operation, Phase phase)
{
    while (operation.state().phase != phase) {
        check(operation.state().phase != Phase::done, "requested phase must be reachable");
        next(operation);
    }
}

void copied_public_payload()
{
    Fixture fixture;
    std::string payload = "original";
    const auto* storage = payload.data();
    rp::Hooks hooks;
    hooks.before_write = [&] {
        // Same-length in-place mutation: no reallocation or dangling string_view.
        std::fill(payload.begin(), payload.end(), 'x');
        check(payload.data() == storage, "caller storage must remain valid");
    };
    const auto destination = fixture.root / "destination";
    const auto result = rp::publish(destination, payload, hooks);
    check(result.committed && !result.cleanup_error, "snapshot publication result");
    check(read(destination) == "original", "publication must use its captured original payload bytes");
}

void successful_transitions_and_private_snapshot()
{
    Fixture fixture;
    const auto destination = fixture.root / "destination";
    write(destination, "old");
    std::string payload("original\0binary", 15);
    const std::string captured = payload;
    Operation operation(destination, payload);
    const auto& state = operation.state();
    check(state.phase == Phase::start && !state.committed && !state.failure && !state.cleanup_error,
        "initial state is queryable without creating workspace");
    check(!fs::exists(fixture.root / ".space-publication"), "constructor has no prepare side effects");
    std::fill(payload.begin(), payload.end(), 'x');
    check(next(operation) == Phase::before_write, "prepare yields before-write");
    const auto workspace = only_attempt(fixture.root);
    check(read(workspace / "record").empty(), "record is empty at before-write");
    check(next(operation) == Phase::before_security, "write yields before-security");
    check(read(workspace / "record") == captured && read(destination) == "old", "write uses owned binary snapshot");
    check(next(operation) == Phase::before_commit, "security yields before-commit");
    check(!state.committed && read(destination) == "old", "secure does not publish");
    check(next(operation) == Phase::before_cleanup, "commit yields cleanup only after latching");
    check(state.committed && !state.failure && read(destination) == captured, "commit truth and bytes available immediately");
    check(fs::exists(workspace) && !fs::exists(workspace / "record"), "cleanup hook is before actual cleanup");
    check(next(operation) == Phase::done, "cleanup yields done");
    check(&state == &operation.state() && state.committed && !state.failure && !state.cleanup_error,
        "stable state reference retains clean commit");
    clean_anchor(fixture.root);
}

void failed_replies()
{
    for (Phase phase : {Phase::start, Phase::before_write, Phase::before_security, Phase::before_commit,
                       Phase::before_cleanup}) {
        Fixture fixture;
        const auto destination = fixture.root / "destination";
        write(destination, "old");
        Operation operation(destination, "new");
        reach(operation, phase);
        const auto result = operation.advance({phase, true, "hook fault"});
        const bool committed = phase == Phase::before_cleanup;
        check(operation.state().committed == committed, "failed reply never changes commit truth");
        if (committed) {
            check(result == Phase::done && !operation.state().failure
                && operation.state().cleanup_error == "hook fault", "cleanup reply records only cleanup failure");
        } else {
            check(operation.state().failure == "hook fault", "failed precommit reply records primary text");
            check(result == (phase == Phase::start ? Phase::done : Phase::before_cleanup), "cleanup only if owned");
            if (result == Phase::before_cleanup) check(next(operation) == Phase::done, "failed hook still cleans");
        }
        check(read(destination) == (committed ? "new" : "old"), "failed hook preserves appropriate bytes");
        if (phase == Phase::start) check(!fs::exists(fixture.root / ".space-publication"), "no phantom cleanup on start failure");
        else clean_anchor(fixture.root);
    }
}

void construction_and_prepare_failures()
{
    Fixture fixture;
    const auto error = rejects([&] { Operation operation(fixture.root / "missing" / "record", "new"); });
    check(!error.empty() && !fs::exists(fixture.root / ".space-publication"), "constructor failure has no workspace");
    int hooks = 0;
    rp::Hooks callbacks;
    callbacks.before_write = callbacks.before_security = callbacks.before_commit = callbacks.before_cleanup = [&] { ++hooks; };
    rejects([&] { rp::publish(fixture.root / "missing" / "record", "new", callbacks); });
    check(hooks == 0, "constructor failure cannot call hooks");
    write(fixture.root / ".space-publication", "obstruction");
    Operation operation(fixture.root / "destination", "new");
    check(next(operation) == Phase::done && operation.state().failure && !operation.state().committed,
        "prepare failure without ownership completes without cleanup event");
    check(!operation.state().cleanup_error && read(fixture.root / ".space-publication") == "obstruction",
        "unowned obstruction is not cleanup work");
    rejects([&] { rp::publish(fixture.root / "destination", "new", callbacks); });
    check(hooks == 0, "unowned prepare failure has no phantom cleanup callback");
}

#ifndef _WIN32
void partial_prepare_failure()
{
    Fixture fixture;
    Operation operation(fixture.root / "destination", "new");
    // Leave room for the anchor and workspace descriptors, but not record creation.
    // Restore the soft limit before inspecting state/files; no injected filesystem mock.
    struct rlimit original {};
    check(::getrlimit(RLIMIT_NOFILE, &original) == 0, "read descriptor limit");
    const int available = ::open("/dev/null", O_RDONLY | O_CLOEXEC);
    check(available >= 0, "locate next descriptor");
    check(::close(available) == 0, "release descriptor probe");
    auto limited = original;
    limited.rlim_cur = static_cast<rlim_t>(available + 2);
    check(limited.rlim_cur <= original.rlim_cur && ::setrlimit(RLIMIT_NOFILE, &limited) == 0, "bound descriptors");
    Phase result;
    try { result = next(operation); }
    catch (...) { ::setrlimit(RLIMIT_NOFILE, &original); throw; }
    check(::setrlimit(RLIMIT_NOFILE, &original) == 0, "restore descriptor limit");
    check(result == Phase::before_cleanup && operation.state().failure
        && operation.state().failure->find("create private record") != std::string::npos,
        "partial prepare failure still yields cleanup for owned workspace");
    check(fs::is_empty(only_attempt(fixture.root)), "partial prepare owns an empty workspace");
    check(next(operation) == Phase::done && !operation.state().cleanup_error, "explicit partial prepare cleanup succeeds");
    clean_anchor(fixture.root);
}
#endif

void native_phase_failures()
{
    for (Phase phase : {Phase::before_write, Phase::before_security, Phase::before_commit}) {
        Fixture fixture;
        const auto destination = fixture.root / "destination";
        write(destination, "old");
        Operation operation(destination, "new");
        reach(operation, phase);
        write(only_attempt(fixture.root) / "record", "corrupt");
        check(next(operation) == Phase::before_cleanup && operation.state().failure && !operation.state().committed,
            "native phase failure records primary and requests cleanup");
        check(next(operation) == Phase::done && !operation.state().cleanup_error, "native failure explicitly cleans");
        check(read(destination) == "old", "native precommit failure preserves original");
        clean_anchor(fixture.root);
    }
}

void primary_and_cleanup_failures()
{
    Fixture fixture;
    const auto destination = fixture.root / "destination";
    write(destination, "old");
    Operation operation(destination, "new");
    reach(operation, Phase::before_write);
    const auto workspace = only_attempt(fixture.root);
    check(operation.advance({Phase::before_write, true, "primary fault"}) == Phase::before_cleanup, "primary failure");
    write(workspace / "unrelated", "keep");
    check(operation.advance({Phase::before_cleanup, true, "cleanup hook fault"}) == Phase::done, "cleanup reply always runs cleanup");
    check(operation.state().failure == "primary fault" && !operation.state().committed, "primary text retained separately");
    check(operation.state().cleanup_error && operation.state().cleanup_error->find("cleanup hook fault; ") == 0,
        "hook and native cleanup errors both visible");
    check(!fs::exists(workspace / "record") && read(workspace / "unrelated") == "keep" && read(destination) == "old",
        "actual cleanup removes only owned record despite failed cleanup hook");

    rp::Hooks hooks;
    hooks.before_write = [] { throw std::runtime_error("public primary"); };
    hooks.before_cleanup = [] { throw 42; };
    const auto error = rejects([&] { rp::publish(destination, "bad", hooks); });
    check(error.find("public primary; cleanup: unknown callback/native exception") != std::string::npos,
        "public driver preserves textual primary plus cleanup and unknown exception conversion");
}

void invalid_replies_do_no_work()
{
    Fixture fixture;
    const auto destination = fixture.root / "destination";
    write(destination, "old");
    Operation operation(destination, "new");
    for (Phase pending : {Phase::start, Phase::before_write, Phase::before_security, Phase::before_commit,
                         Phase::before_cleanup, Phase::done}) {
        check(operation.state().phase == pending, "phase for invalid reply test");
        fs::path workspace;
        if (pending != Phase::start && pending != Phase::done) workspace = only_attempt(fixture.root);
        const bool has_record = !workspace.empty() && fs::exists(workspace / "record");
        const auto bytes = has_record ? read(workspace / "record") : std::string();
        const auto published = read(destination);
        const auto committed = operation.state().committed;
        for (Phase supplied : {Phase::start, Phase::before_write, Phase::before_security, Phase::before_commit,
                               Phase::before_cleanup, Phase::done, static_cast<Phase>(99)}) {
            if (supplied == pending && pending != Phase::done) continue;
            for (bool failed : {false, true}) {
                check(!rejects([&] { operation.advance({supplied, failed, "stale fault"}); }).empty(), "invalid reply throws");
                check(operation.state().phase == pending && operation.state().committed == committed
                    && !operation.state().failure && !operation.state().cleanup_error, "invalid reply leaves state unchanged");
                check(read(destination) == published, "invalid reply cannot publish");
                if (has_record) check(read(workspace / "record") == bytes, "invalid reply cannot write/secure/cleanup");
                if (!workspace.empty()) check(fs::exists(workspace), "invalid reply cannot remove workspace");
                if (pending == Phase::start) check(!fs::exists(fixture.root / ".space-publication"), "invalid start reply cannot prepare");
            }
        }
        if (pending != Phase::done) next(operation);
    }
    clean_anchor(fixture.root);
}

void cancellations()
{
    for (Phase phase : {Phase::start, Phase::before_write, Phase::before_security, Phase::before_commit,
                       Phase::before_cleanup, Phase::done}) {
        Fixture fixture;
        const auto destination = fixture.root / "destination";
        write(destination, "old");
        Operation operation(destination, "new");
        reach(operation, phase);
        const bool committed = phase == Phase::before_cleanup || phase == Phase::done;
        const auto result = operation.cancel("cancel fault");
        check(operation.state().committed == committed, "cancel preserves sticky commit truth");
        if (!committed) check(operation.state().failure == "cancel fault", "precommit cancel records primary reason");
        else check(!operation.state().failure, "postcommit cancel never manufactures primary failure");
        if (phase == Phase::before_cleanup) check(operation.state().cleanup_error == "cancel fault", "postcommit cancellation visible as cleanup error");
        if (phase == Phase::done) check(!operation.state().cleanup_error, "cancel completed operation is a no-op");
        if (result == Phase::before_cleanup) {
            rejects([&] { operation.advance({phase, false, {}}); });
            check(next(operation) == Phase::done, "cancel can only continue cleanup, not publication");
        } else check(result == Phase::done, "cancel without pending hook finalizes");
        check(operation.cancel("again") == Phase::done, "repeated cancel cannot restart operation");
        check(read(destination) == (committed ? "new" : "old"), "cancelled bytes reflect commit boundary");
        if (phase == Phase::start) check(!fs::exists(fixture.root / ".space-publication"), "unprepared cancellation has no cleanup hook");
        else clean_anchor(fixture.root);
    }
    Fixture fixture;
    Operation operation(fixture.root / "destination", "new");
    reach(operation, Phase::before_write);
    const auto workspace = only_attempt(fixture.root);
    operation.advance({Phase::before_write, true, "primary"});
    write(workspace / "unrelated", "keep");
    check(operation.cancel("cancel during cleanup") == Phase::done, "cancel pending cleanup finalizes explicitly");
    check(operation.state().failure == "primary" && operation.state().cleanup_error
        && operation.state().cleanup_error->find("cancel during cleanup; ") == 0,
        "explicit cancellation preserves primary and reports cleanup problems");
    check(!fs::exists(workspace / "record") && read(workspace / "unrelated") == "keep", "cancel performs actual owned cleanup");
}

void destructor_safeguard()
{
    Fixture fixture;
    {
        Operation operation(fixture.root / "destination", "new");
        reach(operation, Phase::before_commit);
    }
    check(!fs::exists(fixture.root / "destination"), "abandoned operation never commits");
    clean_anchor(fixture.root);
}

void nested_independent_operations()
{
    Fixture fixture;
    Operation outer(fixture.root / "outer", "outer");
    reach(outer, Phase::before_write);
    const auto workspace = only_attempt(fixture.root);
    Operation inner(fixture.root / "inner", "inner");
    reach(inner, Phase::before_commit);
    check(outer.state().phase == Phase::before_write && read(workspace / "record").empty(), "overlapping contexts own independent progress");
    reach(inner, Phase::done);
    check(only_attempt(fixture.root) == workspace, "inner cleanup leaves outer workspace");
    reach(outer, Phase::done);
    check(read(fixture.root / "outer") == "outer" && read(fixture.root / "inner") == "inner", "overlapping exact results");
    rp::Hooks hooks;
    hooks.before_write = [&] {
        const auto nested = rp::publish(fixture.root / "nested", "nested");
        check(nested.committed && !nested.cleanup_error, "nested public call has no global session or hook lock");
    };
    check(rp::publish(fixture.root / "public", "public", hooks).committed, "outer public call commits");
    clean_anchor(fixture.root);
}

} // namespace

int main()
{
    try {
        copied_public_payload();
        successful_transitions_and_private_snapshot();
        failed_replies();
        construction_and_prepare_failures();
#ifndef _WIN32
        partial_prepare_failure();
#endif
        native_phase_failures();
        primary_and_cleanup_failures();
        invalid_replies_do_no_work();
        cancellations();
        destructor_safeguard();
        nested_independent_operations();
        std::cout << "record publication operation tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
