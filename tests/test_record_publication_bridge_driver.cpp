#include "record_publication_unix.h"
#include "record_publication_wine_driver.h"

#include <algorithm>
#include <array>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <new>
#include <stdexcept>
#include <thread>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>

// Executable-local allocation faults, never a production protocol/test hook.
namespace allocation_test {
thread_local bool disabled = false;
thread_local bool fail_next = false;
thread_local unsigned one_shot_failures = 0;
thread_local long fail_after = -1;
thread_local unsigned allocations = 0;
struct Failure : std::bad_alloc {
    const char* what() const noexcept override
    {
        return "driver test allocator unavailable: "
            "0123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789"
            "0123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789"
            "0123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789"
            "0123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789"
            "0123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789"
            "0123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789";
    }
};
}
void* operator new(std::size_t size)
{
    ++allocation_test::allocations;
    if (allocation_test::fail_after == 0) {
        allocation_test::fail_after = -1;
        allocation_test::fail_next = true;
    } else if (allocation_test::fail_after > 0) --allocation_test::fail_after;
    if (allocation_test::fail_next) {
        allocation_test::fail_next = false;
        ++allocation_test::one_shot_failures;
        throw allocation_test::Failure();
    }
    if (allocation_test::disabled) throw allocation_test::Failure();
    if (auto* memory = std::malloc(size ? size : 1)) return memory;
    throw std::bad_alloc();
}
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

namespace fs = std::filesystem;
using record_publication::Hooks;
namespace {
void check(bool value, const char* message)
{
    if (!value) throw std::runtime_error(message);
}
struct Fixture {
    fs::path root;
    Fixture()
    {
        std::string name = (fs::temp_directory_path() / "record-driver-XXXXXX").string();
        check(::mkdtemp(name.data()) != nullptr, "mkdtemp");
        root = name;
    }
    ~Fixture() { std::error_code ignored; fs::remove_all(root, ignored); }
};
void write(const fs::path& path, const std::string& text)
{
    std::ofstream out(path, std::ios::binary); out << text; out.close();
    check(bool(out), "fixture write");
}
std::string read(const fs::path& path)
{
    std::ifstream in(path, std::ios::binary);
    check(bool(in), "fixture read");
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}
void clean(const Fixture& fixture)
{
    const auto parent = fixture.root / ".space-publication";
    check(!fs::exists(parent) || fs::is_empty(parent), "owned workspaces retired");
}
fs::path workspace(const Fixture& fixture)
{
    const auto parent = fixture.root / ".space-publication";
    check(std::distance(fs::directory_iterator(parent), fs::directory_iterator()) == 1, "one workspace");
    return fs::directory_iterator(parent)->path();
}
uint32_t allowed() { return 0; }
struct Entry {
    std::vector<SrpCall> requests;
    std::function<void(SrpCall&)> before;
    std::function<void(const SrpCall&, SrpCall&, int32_t&)> after;
    uint64_t id = 0;
    int32_t operator()(uint32_t slot, void* frame)
    {
        check(slot == SRP_ENTRY_OPERATION, "operation entry channel");
        auto& call = *static_cast<SrpCall*>(frame);
        check(call.size == sizeof(call) && call.abi == SRP_ABI && call.reserved == 0
            && call.flags == 0 && call.primary_state == 0 && call.primary_error.required == 0
            && call.cleanup_error.required == 0 && call.transport_error.required == 0, "fresh zero request/output fields");
        for (auto buffer : {call.primary_error, call.cleanup_error, call.transport_error})
            check(buffer.address && buffer.capacity >= 4096 && buffer.capacity <= 65536
                && (!requests.empty() || buffer.capacity == 4096), "bounded independent buffers, initially4096");
        if (call.opcode != SRP_BEGIN) check(!call.path.address && !call.path.size && !call.payload.address && !call.payload.size,
            "borrowed begin input never replayed");
        if (call.opcode != SRP_CANCEL && !(call.opcode == SRP_ADVANCE && call.reply == SRP_FAILED))
            check(!call.hook_error.address && !call.hook_error.size && call.reply == SRP_CONTINUE, "legal reply channel");
        requests.push_back(call);
        const auto request = call;
        if (before) before(call);
        auto status = srp_unix_call(&call);
        if (call.context) id = call.context;
        if (after) after(request, call, status);
        return status;
    }
    void retired()
    {
        if (!id) return;
        SrpCall query {}; query.size = sizeof(query); query.abi = SRP_ABI;
        query.opcode = SRP_SNAPSHOT; query.context = id;
        check(srp_unix_call(&query) == SRP_INVALID_ARGUMENT && !query.context, "native context retired");
    }
    size_t count(uint32_t opcode) const
    {
        return std::count_if(requests.begin(), requests.end(), [=](const auto& r) { return r.opcode == opcode; });
    }
};
template<class Authority = decltype(&allowed)>
record_publication::Result drive(Entry& entry, const fs::path& path, std::string_view payload,
                                const Hooks& hooks = {}, Authority authority = allowed)
{
    return record_publication::wine::detail::drive(entry, path.native(), payload, hooks, authority);
}
template<class Function>
std::string failure(Function function)
{
    try { function(); }
    catch (const std::runtime_error& e) { return e.what(); }
    throw std::runtime_error("expected runtime_error");
}

void real_success_and_nesting()
{
    for (const auto& payload : {std::string(), std::string("new\0bytes", 9)}) {
        Fixture f; Entry entry;
        const auto path = f.root / std::string("raw-\xff", 5);
        write(path, "old");
        std::vector<int> order;
        const auto caller = std::this_thread::get_id();
        Hooks hooks;
        hooks.before_write = [&] {
            check(std::this_thread::get_id() == caller, "caller hook context");
            order.push_back(1);
            check(read(path) == "old" && read(workspace(f) / "record").empty(), "prepare only before_write");
            Entry nested;
            check(drive(nested, f.root / "inner", "inner").committed, "nested publication");
            nested.retired();
        };
        hooks.before_security = [&] { order.push_back(2); check(read(workspace(f) / "record") == payload, "binary native write"); };
        hooks.before_commit = [&] { order.push_back(3); check(read(path) == "old", "old bytes until final native validation/rename"); };
        hooks.before_cleanup = [&] { order.push_back(4); check(read(path) == payload, "committed before cleanup hook"); };
        entry.after = [&](const auto& request, auto& response, auto&) {
            if (request.opcode == SRP_BEGIN) {
                check(response.event == SRP_START && !response.sequence && order.empty()
                    && !fs::exists(f.root / ".space-publication"), "START sequence0 has no workspace or hook");
                check(std::string(reinterpret_cast<const char*>(request.path.address), request.path.size) == path.native(), "raw host bytes unchanged");
            }
        };
        const auto result = drive(entry, path, payload, hooks);
        check(result.committed && !result.cleanup_error && order == std::vector<int>({1,2,3,4}), "four ordered once-only hooks");
        check(read(path) == payload && read(f.root / "inner") == "inner", "real destination/cache-relevant bytes");
        entry.retired(); clean(f);
        check(entry.count(SRP_BEGIN) == 1 && entry.count(SRP_ADVANCE) == 5 && entry.count(SRP_RELEASE) == 1, "single publication no replay");
    }
}

void native_errors_and_empty_presence()
{
    for (int phase = 1; phase <= 4; ++phase) {
        Fixture f; Entry entry;
        const auto path = f.root / "record"; write(path, "old");
        Hooks hooks;
        auto fail = [] { throw std::runtime_error(""); };
        if (phase == 1) hooks.before_write = fail;
        if (phase == 2) hooks.before_security = fail;
        if (phase == 3) hooks.before_commit = fail;
        if (phase == 4) hooks.before_cleanup = fail;
        if (phase < 4) {
            check(failure([&] { drive(entry, path, "new", hooks); }) == "record publication: ", "present empty primary matches native exception");
            check(read(path) == "old" && entry.count(SRP_CANCEL) == 1, "publication hook failure cancels, never failed publication ADVANCE");
        } else {
            const auto result = drive(entry, path, "new", hooks);
            check(result.committed && result.cleanup_error && result.cleanup_error->empty(), "present empty cleanup remains present");
            check(entry.requests[5].reply == SRP_FAILED, "cleanup may send failed ADVANCE");
        }
        entry.retired(); clean(f);
    }
    Fixture f; Entry constructor;
    check(failure([&] { drive(constructor, f.root / "missing" / "record", "new"); }).find("pin target parent") != std::string::npos,
        "constructor error detail without live context");
    check(constructor.count(SRP_BEGIN) == 1 && constructor.requests.size() == 1, "no replay of no-context BEGIN");
    Entry prepare; write(f.root / ".space-publication", "obstruction");
    const auto error = failure([&] { drive(prepare, f.root / "record", "new"); });
    check(error.find("record publication: ") == 0 && error.find("publication") != std::string::npos, "native preparation exception");
    prepare.retired(); check(read(f.root / ".space-publication") == "obstruction", "unowned obstruction preserved");
}

void authority_loss()
{
    for (int phase = 0; phase <= 3; ++phase) {
        Fixture f; Entry entry; bool denied = false; int calls = 0;
        Hooks hooks;
        auto lose = [&] { denied = true; };
        if (phase == 1) hooks.before_write = lose;
        if (phase == 2) hooks.before_security = lose;
        if (phase == 3) hooks.before_commit = lose;
        entry.after = [&](const auto& request, auto&, auto&) { if (phase == 0 && request.opcode == SRP_BEGIN) denied = true; };
        const auto text = failure([&] {
            drive(entry, f.root / "record", "new", hooks, [&]() -> uint32_t { ++calls; if (denied) { denied = false; return 5; } return 0; });
        });
        check(text.find("authority") != std::string::npos && text.find("5") != std::string::npos && calls >= 2, "authority loss diagnostic retains error code");
        check(entry.count(SRP_CANCEL) == 1 && !fs::exists(f.root / "record"), "loss at0..3 cancels and cannot resume after authority returns");
        entry.retired(); clean(f);
    }
    Fixture f; Entry denied;
    check(failure([&] { drive(denied, f.root / "record", "new", {}, []() -> uint32_t { return 5; }); }).find("authority") != std::string::npos,
        "authority checked before BEGIN");
    check(denied.requests.empty() && !fs::exists(f.root / ".space-publication"), "denial before native capture");
}

void transport_and_release_recovery()
{
    for (int fault = 0; fault < 6; ++fault) {
        Fixture f; Entry entry; bool damaged = false;
        write(f.root / "record", "old");
        entry.before = [&](auto& call) {
            if (!damaged && fault == 0 && call.opcode == SRP_ADVANCE && call.event == SRP_BEFORE_SECURITY) {
                damaged = true; --call.sequence; // Real native stale continuation rejection.
            }
            if (!damaged && fault == 4 && call.opcode == SRP_RELEASE) { damaged = true; --call.sequence; }
        };
        entry.after = [&](const auto& request, auto& response, auto& status) {
            if (damaged) return;
            if ((fault == 1 || fault == 2) && request.opcode == SRP_ADVANCE && request.event == SRP_BEFORE_COMMIT) {
                damaged = true;
                if (fault == 1) { response.context = 0; response.flags = 0; response.sequence = 0; response.event = 0; status = SRP_ACCESS_DENIED; }
                else { response.sequence = 0; } // Invalid successful protocol response after actual rename.
            }
            if (fault == 3 && request.opcode == SRP_ADVANCE && request.event == SRP_BEFORE_WRITE) {
                damaged = true; response.flags |= SRP_POISONED; status = SRP_UNSUCCESSFUL;
            }
            if (fault == 5 && request.opcode == SRP_RELEASE) {
                // Ordinary RELEASE's final native cleanup errors must be consumed.
                damaged = true; response.flags |= SRP_CLEANUP_PRESENT;
                response.cleanup_error.required = 0;
            }
        };
        if (fault == 0 || fault == 3) {
            check(failure([&] { drive(entry, f.root / "record", "new"); }).find("bridge") != std::string::npos, "protocol/poison failure explicit");
            check(read(f.root / "record") == "old", "no publication replay after protocol/poison");
        } else {
            const auto result = drive(entry, f.root / "record", "new");
            check(result.committed && result.cleanup_error, "known commit returns cleanup/lifecycle diagnostic");
            check(read(f.root / "record") == "new", "sticky commit truth");
        }
        check(damaged && entry.count(SRP_BEGIN) == 1 && entry.count(SRP_RELEASE) <= 2, "bounded retirement and single BEGIN");
        if (fault < 5) check(entry.count(SRP_SNAPSHOT) >= 1, "snapshot recovery not publication replay");
        entry.retired(); clean(f);
    }
}

void bounded_diagnostics()
{
    for (size_t length : {size_t(5000), size_t(70000)}) {
        Fixture f; Entry entry;
        const std::string text(length, 'e');
        Hooks hooks; hooks.before_write = [&] { throw std::runtime_error(text); };
        const auto error = failure([&] { drive(entry, f.root / "record", "new", hooks); });
        check(error.find(std::string(std::min<size_t>(length, 65536), 'e')) != std::string::npos, "counted diagnostic bytes recovered");
        check(length <= 65536 || error.find("truncated") != std::string::npos, "capacity truncation visible");
        check(entry.count(SRP_SNAPSHOT) == 1 && entry.count(SRP_CANCEL) == 1, "one bounded snapshot growth, no cancellation replay");
        entry.retired(); clean(f);
    }
    Fixture f; Entry entry;
    Hooks hooks;
    hooks.before_write = [] { throw std::runtime_error("primary"); };
    hooks.before_cleanup = [] { throw std::runtime_error("cleanup"); };
    bool stale = false;
    entry.before = [&](auto& call) { if (!stale && call.opcode == SRP_RELEASE) { stale = true; --call.sequence; } };
    const auto error = failure([&] { drive(entry, f.root / "record", "new", hooks); });
    check(error.find("primary") != std::string::npos && error.find("cleanup") != std::string::npos
        && error.find("stale or incompatible") != std::string::npos, "primary cleanup and original transient transport survive snapshot");
    entry.retired(); clean(f);
}

void real_poison_and_bounded_cleanup()
{
    for (bool cleanup_fault : {false, true}) {
        Fixture f; Entry entry; bool injected = false; int hook_count = 0;
        const std::string long_error(5000, 'p');
        Hooks hooks;
        auto fail = [&] { ++hook_count; throw std::runtime_error(long_error); };
        if (cleanup_fault) hooks.before_cleanup = fail;
        else hooks.before_write = fail;
        entry.before = [&](auto& call) {
            if (!injected && call.opcode == (cleanup_fault ? SRP_ADVANCE : SRP_CANCEL)
                    && call.event == (cleanup_fault ? SRP_BEFORE_CLEANUP : SRP_BEFORE_WRITE)) {
                injected = true;
                allocation_test::disabled = true; // Actual native error capture fails and poisons the real context.
            }
        };
        entry.after = [](const auto&, auto&, auto&) { allocation_test::disabled = false; };
        if (cleanup_fault) {
            const auto result = drive(entry, f.root / "record", "new", hooks);
            check(result.committed && result.cleanup_error && result.cleanup_error->find("bridge") != std::string::npos
                && result.cleanup_error->find("producer truncated") != std::string::npos,
                "real postcommit poison returns explicit lifecycle diagnostic");
        } else {
            check(failure([&] { drive(entry, f.root / "record", "new", hooks); }).find("producer truncated") != std::string::npos,
                "real precommit poison diagnostic");
            check(!fs::exists(f.root / "record"), "real poison never resumes publication");
        }
        check(injected && hook_count == 1, "poison must not replay hooks");
        check(entry.count(SRP_CANCEL) <= 1 && entry.count(SRP_RELEASE) <= 2, "poison has bounded cleanup-only retirement");
        entry.retired(); clean(f);
    }
}

void response_protocol_and_terminal_text()
{
    for (int fault = 0; fault < 2; ++fault) {
        Fixture f; Entry entry; bool damaged = false;
        entry.after = [&](const auto& request, auto& response, auto&) {
            if (!damaged && request.opcode == SRP_ADVANCE && request.event == SRP_BEFORE_WRITE) {
                damaged = true;
                if (fault == 0) response.event = SRP_BEFORE_WRITE;
                else response.flags |= 0x80000000u;
            }
        };
        check(failure([&] { drive(entry, f.root / "record", "new"); }).find("bridge") != std::string::npos,
            "invalid successful protocol response diagnosed");
        check(!fs::exists(f.root / "record") && entry.count(SRP_CANCEL) == 1, "invalid response cancels recovered native phase");
        entry.retired(); clean(f);
    }
    for (bool release : {false, true}) {
        Fixture f; Entry entry;
        entry.after = [&](const auto& request, auto& response, auto&) {
            if (request.opcode == (release ? SRP_RELEASE : SRP_BEGIN)) {
                auto& channel = release ? response.cleanup_error : response.transport_error;
                std::memset(reinterpret_cast<void*>(channel.address), 't', channel.capacity);
                channel.required = 70000;
                response.flags |= release ? SRP_CLEANUP_PRESENT | SRP_CLEANUP_TRUNCATED : SRP_TRANSPORT_TRUNCATED;
            }
        };
        if (release) {
            const auto result = drive(entry, f.root / "record", "new");
            check(result.committed && result.cleanup_error && result.cleanup_error->find("capacity truncated") != std::string::npos,
                "retiring release text truncated visibly without replay");
        } else {
            const auto text = failure([&] { drive(entry, f.root / "missing" / "record", "new"); });
            check(text.find("capacity truncated") != std::string::npos, "no-context transport truncated visibly without replay");
        }
        check(entry.count(SRP_SNAPSHOT) == 0 && entry.count(SRP_BEGIN) == 1, "no retired/no-context text replay");
        entry.retired(); clean(f);
    }
    Fixture f; Entry counted;
    counted.after = [](const auto& request, auto& response, auto&) {
        if (request.opcode == SRP_RELEASE) {
            std::memcpy(reinterpret_cast<void*>(response.cleanup_error.address), "a\0b", 3);
            response.cleanup_error.required = 3; response.flags |= SRP_CLEANUP_PRESENT;
        }
    };
    const auto result = drive(counted, f.root / "record", "new");
    check(result.committed && result.cleanup_error == std::optional<std::string>(std::string("a\0b", 3)),
        "diagnostics use exact byte counts, not NUL termination");
    counted.retired(); clean(f);
}

void independent_channels_and_native_cleanup()
{
    Fixture f; Entry entry;
    const std::string primary(5000, 'p'), cleanup_error(7000, 'c');
    Hooks hooks;
    hooks.before_write = [&] { throw std::runtime_error(primary); };
    hooks.before_cleanup = [&] { throw std::runtime_error(cleanup_error); };
    bool stale = false;
    entry.before = [&](auto& call) { if (!stale && call.opcode == SRP_RELEASE) { stale = true; --call.sequence; } };
    const auto text = failure([&] { drive(entry, f.root / "record", "new", hooks); });
    check(text.find(primary) != std::string::npos && text.find(cleanup_error) != std::string::npos
        && text.find("stale or incompatible") != std::string::npos, "independent grown native primary/cleanup and transient transport channels");
    check(entry.count(SRP_SNAPSHOT) == 3, "one growth per affected channel plus release recovery snapshot");
    entry.retired(); clean(f);

    Entry native;
    Hooks obstruct;
    fs::path attempt;
    obstruct.before_cleanup = [&] { attempt = workspace(f); write(attempt / "unrelated", "keep"); };
    const auto result = drive(native, f.root / "committed", "new", obstruct);
    check(result.committed && result.cleanup_error && !result.cleanup_error->empty(), "ordinary native DONE cleanup error remains retiring result");
    check(read(f.root / "committed") == "new" && read(attempt / "unrelated") == "keep", "native cleanup preserves unrelated entries");
    native.retired();
}

void denied_inline_response_and_real_release_fault()
{
    Fixture f; Entry denied;
    write(f.root / "record", "old");
    denied.before = [](auto& call) {
        // Native validation prevents work, then the response wrapper models the
        // PE guard's denial (which clears inline state without following spans).
        if (call.opcode == SRP_ADVANCE && call.event == SRP_BEFORE_COMMIT) call.reserved = 1;
    };
    denied.after = [](const auto& request, auto& response, auto& status) {
        if (request.opcode == SRP_ADVANCE && request.event == SRP_BEFORE_COMMIT) {
            response.context = response.sequence = 0; response.event = SRP_START;
            response.flags = response.primary_state = 0;
            response.primary_error.required = response.cleanup_error.required = response.transport_error.required = 0;
            status = SRP_ACCESS_DENIED;
        }
    };
    check(failure([&] { drive(denied, f.root / "record", "new"); }).find("NTSTATUS") != std::string::npos,
        "NTSTATUS denial is not native success");
    check(read(f.root / "record") == "old" && denied.count(SRP_CANCEL) == 1 && denied.count(SRP_SNAPSHOT) == 1,
        "saved ID recovers cleared inline response and cancels without commit");
    denied.retired(); clean(f);

    Entry entry; Hooks hooks; fs::path attempt; unsigned releases = 0, cleanup_hooks = 0;
    hooks.before_cleanup = [&] { ++cleanup_hooks; attempt = workspace(f); write(attempt / "unrelated", "keep"); };
    entry.before = [&](auto& call) {
        if (call.opcode == SRP_ADVANCE && call.event == SRP_BEFORE_CLEANUP) --call.sequence;
        if (call.opcode == SRP_RELEASE && ++releases == 1) allocation_test::disabled = true;
    };
    entry.after = [&](const auto& request, auto& response, auto& status) {
        allocation_test::disabled = false;
        if (request.opcode == SRP_RELEASE && releases == 1) {
            check(status == SRP_UNSUCCESSFUL && (response.flags & SRP_POISONED)
                && (response.flags & SRP_COMMITTED), "real first RELEASE fault retains poisoned ownership and truth");
            check(read(f.root / "record") == "new" && read(attempt / "unrelated") == "keep",
                "single cleanup pass preserves committed bytes and exact foreign bytes");
            check(!fs::exists(attempt / "record"), "single namespace pass leaves no owned record entry");
            fs::remove(attempt / "unrelated");
        } else if (request.opcode == SRP_RELEASE) {
            check(status == SRP_SUCCESS && (response.flags & SRP_COMMITTED) && response.event == SRP_DONE,
                "second RELEASE retires finalized committed context");
        }
    };
    const auto result = drive(entry, f.root / "record", "new", hooks);
    check(result.committed && result.cleanup_error && result.cleanup_error->find("stale or incompatible") != std::string::npos,
        "original transport failure survives real release-recovery poison");
    check(releases == 2 && cleanup_hooks == 1 && read(f.root / "record") == "new", "exactly one cleanup-only release recovery, no hook/rename replay");
    entry.retired();
    check(fs::is_directory(attempt) && fs::is_empty(attempt), "terminal retirement never replays namespace removal");
    fs::remove(attempt); // Explicit fixture cleanup after terminal-state assertions.
    clean(f);
}

void failed_response_text_and_precommit_allocation()
{
    Fixture f; Entry text;
    const std::string primary(5000, 'p');
    Hooks hooks; hooks.before_write = [&] { throw std::runtime_error(primary); };
    text.after = [](const auto& request, auto&, auto& status) {
        if (request.opcode == SRP_CANCEL) status = SRP_UNSUCCESSFUL;
    };
    const auto error = failure([&] { drive(text, f.root / "record", "new", hooks); });
    check(error.find(primary) != std::string::npos, "failed mutation recovers complete native primary via bounded snapshot growth");
    text.retired(); clean(f);

    Entry terminal; Hooks cleanup;
    cleanup.before_cleanup = [&] { throw std::runtime_error(primary); };
    terminal.after = [](const auto& request, auto&, auto& status) {
        if (request.opcode == SRP_ADVANCE && request.event == SRP_BEFORE_CLEANUP) status = SRP_UNSUCCESSFUL;
    };
    const auto result = drive(terminal, f.root / "committed", "new", cleanup);
    check(result.committed && result.cleanup_error && result.cleanup_error->find(primary) != std::string::npos,
        "failed terminal mutation grows retained cleanup text via snapshot before retirement");
    terminal.retired(); clean(f);

    Entry allocation; allocation.requests.reserve(32); bool injected = false;
    allocation.after = [&](const auto& request, auto& response, auto&) {
        if (!injected && request.opcode == SRP_ADVANCE && request.event == SRP_BEFORE_WRITE) {
            injected = true;
            response.primary_state = SRP_PRIMARY_PRESENT;
            response.primary_error.required = 5000; response.flags |= SRP_PRIMARY_TRUNCATED;
            std::memset(reinterpret_cast<void*>(response.primary_error.address), 'p', response.primary_error.capacity);
            allocation_test::disabled = true;
        }
    };
    bool caught = false;
    try { drive(allocation, f.root / "record", "new"); }
    catch (const std::bad_alloc&) { caught = true; }
    allocation_test::disabled = false;
    check(caught && !fs::exists(f.root / "record"), "precommit diagnostic allocation failure propagates only after explicit retirement");
    check(allocation.count(SRP_RELEASE) == 1, "allocation-free emergency release is bounded");
    allocation.retired(); clean(f);
}

void throwing_entry_after_real_begin()
{
    for (bool cleared : {false, true}) {
        Fixture f; Entry entry; bool threw = false;
        const auto path = f.root / "record"; write(path, "old");
        entry.before = [&](auto& call) {
            if (cleared && call.opcode == SRP_ADVANCE && call.event == SRP_BEFORE_COMMIT) call.reserved = 1;
        };
        entry.after = [&](const auto& request, auto& response, auto& status) {
            if (!threw && !cleared && request.opcode == SRP_BEGIN) {
                check(status == SRP_SUCCESS && response.context && response.flags == SRP_VALID
                    && response.event == SRP_START && !response.sequence, "real BEGIN acquired coherent ownership before Entry throws");
                threw = true;
                throw std::runtime_error("Entry bookkeeping after BEGIN");
            }
            if (!threw && cleared && request.opcode == SRP_ADVANCE && request.event == SRP_BEFORE_COMMIT) {
                response.context = response.sequence = 0; response.event = SRP_START;
                response.flags = response.primary_state = 0;
                response.primary_error.required = response.cleanup_error.required = response.transport_error.required = 0;
                status = SRP_ACCESS_DENIED;
                threw = true;
                throw std::runtime_error("Entry bookkeeping after denial");
            }
        };
        check(failure([&] { drive(entry, path, "new"); }) == (cleared ? "Entry bookkeeping after denial" : "Entry bookkeeping after BEGIN"),
            "original precommit Entry exception propagates");
        entry.retired(); clean(f);
        check(threw && entry.count(SRP_BEGIN) == 1 && entry.count(SRP_RELEASE) == 1
            && entry.count(SRP_SNAPSHOT) == 1 && (cleared || entry.count(SRP_ADVANCE) == 0),
            "throwing Entry gets bounded explicit retirement without BEGIN replay");
        check(read(path) == "old" && (cleared || !fs::exists(f.root / ".space-publication")),
            "throwing BEGIN changes no destination or workspace; cleared denial cannot commit");
    }
}

void one_shot_postcommit_allocation()
{
    for (unsigned mode = 0; mode < 3; ++mode) {
        const bool obstruct_cleanup = mode != 0;
        const bool poison_release = mode == 2;
        Fixture f;
        const auto child = ::fork(); check(child >= 0, "fork");
        if (!child) {
            std::set_terminate([] { ::_exit(86); });
            try {
                Entry entry; entry.requests.reserve(32);
                const std::runtime_error long_error(std::string(5000, 'e'));
                unsigned cleanup_hooks = 0;
                unsigned releases = 0;
                bool final_poison = false;
                fs::path attempt;
                Hooks hooks;
                hooks.before_cleanup = [&] {
                    ++cleanup_hooks;
                    if (obstruct_cleanup) { attempt = workspace(f); write(attempt / "unrelated", "keep"); }
                    allocation_test::fail_next = true;
                    throw long_error; // noexcept exception copy; only driver diagnostic capture allocates next.
                };
                entry.before = [&](auto& call) {
                    if (call.opcode == SRP_RELEASE && ++releases == 1 && poison_release)
                        allocation_test::disabled = true;
                };
                entry.after = [&](const auto& request, auto& response, auto& status) {
                    if (!poison_release || request.opcode != SRP_RELEASE) return;
                    allocation_test::disabled = false;
                    check((response.flags & SRP_POISONED) && (response.flags & SRP_COMMITTED)
                        && (response.flags & SRP_TRANSPORT_TRUNCATED) && response.transport_error.required == 512,
                        "real emergency RELEASE retains native poison bytes and producer truncation");
                    if (releases == 1) {
                        check(status == SRP_UNSUCCESSFUL, "first real emergency RELEASE is allocation-poisoned, not retired");
                        check(read(attempt / "unrelated") == "keep", "poisoned native cleanup preserved obstruction");
                        check(read(f.root / "record") == "committed" && !fs::exists(attempt / "record"),
                            "single namespace pass retains committed bytes and no owned record entry");
                        fs::remove(attempt / "unrelated");
                    } else {
                        check(status == SRP_SUCCESS && response.event == SRP_DONE, "second real emergency RELEASE retires");
                        final_poison = true;
                    }
                };
                const auto result = drive(entry, f.root / "record", "committed", hooks);
                check(allocation_test::one_shot_failures == 1 && !allocation_test::fail_next && !allocation_test::disabled,
                    "only the next diagnostic allocation failed");
                check(result.committed && result.cleanup_error && result.cleanup_error->find("bridge") != std::string::npos,
                    "recovered postcommit allocation returns explicit truthful lifecycle result");
                entry.retired();
                if (poison_release) {
                    check(fs::is_directory(attempt) && fs::is_empty(attempt),
                        "second RELEASE cannot replay terminal namespace cleanup");
                    check(final_poison && result.cleanup_error->find("driver test allocator unavailable:") != std::string::npos
                        && result.cleanup_error->find("[truncated]") != std::string::npos
                        && result.cleanup_error->find("[producer truncated]") != std::string::npos,
                         "combined one-shot OOM and emergency RELEASE recovery preserves native poison detail/truncation");
                    fs::remove(attempt); // Fixture cleanup only after all retained-state assertions.
                    clean(f);
                } else if (obstruct_cleanup) {
                    check(result.cleanup_error->find("remove workspace:") != std::string::npos
                         && read(attempt / "unrelated") == "keep", "recovery consumes final native RELEASE errors, preserves unrelated bytes");
                    check(fs::is_directory(attempt) && !fs::exists(attempt / "record"),
                        "obstructed terminal attempt remains without an owned record");
                } else clean(f);
                check(cleanup_hooks == 1 && entry.count(SRP_BEGIN) == 1 && entry.count(SRP_SNAPSHOT) == (poison_release ? 2 : 1)
                    && entry.count(SRP_RELEASE) == (poison_release ? 2 : 1) && entry.count(SRP_ADVANCE) == 4,
                    "one-shot recovery retires without replaying cleanup hook or publication");
                check(read(f.root / "record") == "committed", "one-shot diagnostic failure preserves committed bytes");
                ::_exit(0);
            } catch (const std::exception& e) { std::cerr << e.what() << '\n'; ::_exit(87); }
            catch (...) { ::_exit(87); }
        }
        int status = 0; check(::waitpid(child, &status, 0) == child, "waitpid");
        check(read(f.root / "record") == "committed", "one-shot regression really committed before diagnostic failure");
        check(WIFEXITED(status) && WEXITSTATUS(status) == 0,
            "one-shot postcommit diagnostic allocation must return truthful Result, not terminate or throw");
    }
}

template<class Function>
void fatal(Function function)
{
    const auto child = ::fork(); check(child >= 0, "fork");
    if (!child) {
        std::set_terminate([] { ::_exit(86); });
        try { function(); } catch (...) { ::_exit(87); }
        ::_exit(88);
    }
    int status = 0; check(::waitpid(child, &status, 0) == child, "waitpid");
    check(WIFEXITED(status) && WEXITSTATUS(status) == 86, "fatal invariant must terminate, not return or throw");
}
void fatal_invariants()
{
    // Fixtures belong to the parent so even terminated child artifacts are removed.
    for (int fault = 0; fault < 6; ++fault) {
        Fixture f;
        fatal([&] {
            Entry entry; entry.requests.reserve(32);
            entry.after = [&](const auto& request, auto& response, auto& status) {
                if (fault == 0 && ((request.opcode == SRP_ADVANCE && request.event == SRP_BEFORE_COMMIT)
                        || request.opcode == SRP_SNAPSHOT)) {
                    response.context = 0; response.flags = 0; status = SRP_UNSUCCESSFUL;
                }
                if (fault == 2 && request.opcode == SRP_ADVANCE && request.event == SRP_BEFORE_COMMIT) {
                    response.flags |= SRP_CLEANUP_PRESENT | SRP_CLEANUP_TRUNCATED;
                    response.cleanup_error.required = 5000;
                    std::memset(reinterpret_cast<void*>(response.cleanup_error.address), 'e', response.cleanup_error.capacity);
                    allocation_test::disabled = true;
                }
                if (fault == 3 && request.opcode == SRP_ADVANCE && request.event == SRP_BEFORE_WRITE)
                    status = SRP_UNSUCCESSFUL;
                if (fault >= 4 && request.opcode == SRP_BEGIN) {
                    if (fault == 4) response.reserved = 1; // Acquired but incoherent ownership cannot be trusted or silently leaked.
                    throw std::runtime_error("Entry bookkeeping after BEGIN");
                }
            };
            entry.before = [&](auto& call) {
                if ((fault == 1 || fault == 3 || fault == 5) && call.opcode == SRP_RELEASE) --call.sequence; // Both bounded release attempts refused.
            };
            drive(entry, f.root / "record", "new");
        });
        if (fault >= 3) check(!fs::exists(f.root / "record"), "unretirable/untrustworthy precommit ownership is fatal too");
        else check(read(f.root / "record") == "new", "fatal postcommit cases did really publish");
    }
}
} // namespace

void native_driver_allocation_tests();

int main()
{
    try {
        native_driver_allocation_tests();
        throwing_entry_after_real_begin();
        one_shot_postcommit_allocation();
        real_success_and_nesting();
        native_errors_and_empty_presence();
        authority_loss();
        transport_and_release_recovery();
        bounded_diagnostics();
        real_poison_and_bounded_cleanup();
        response_protocol_and_terminal_text();
        independent_channels_and_native_cleanup();
        denied_inline_response_and_real_release_fault();
        failed_response_text_and_precommit_allocation();
        fatal_invariants();
        std::cout << "record publication bridge driver tests passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
