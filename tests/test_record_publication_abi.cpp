#include "record_publication_unix.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <new>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

// Executable-local allocator control, not a production hook or protocol opcode.
namespace allocation_test {
thread_local bool disabled = false;
thread_local unsigned attempts = 0;
struct Failure : std::bad_alloc {
    const char* what() const noexcept override
    {
        return "test allocator unavailable: "
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
    if (allocation_test::disabled) {
        ++allocation_test::attempts;
        throw allocation_test::Failure();
    }
    if (void* pointer = std::malloc(size ? size : 1)) return pointer;
    throw std::bad_alloc();
}
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* pointer) noexcept { std::free(pointer); }
void operator delete[](void* pointer) noexcept { std::free(pointer); }
void operator delete(void* pointer, std::size_t) noexcept { std::free(pointer); }
void operator delete[](void* pointer, std::size_t) noexcept { std::free(pointer); }

namespace fs = std::filesystem;
namespace {

void check(bool condition, const char* message)
{
    if (!condition) throw std::runtime_error(message);
}

uint64_t address(const void* value) { return reinterpret_cast<uintptr_t>(value); }
SrpSlice slice(const std::string& text) { return text.empty() ? SrpSlice{} : SrpSlice{address(text.data()), text.size()}; }

struct Fixture {
    fs::path root;
    Fixture()
    {
        auto pattern = (fs::temp_directory_path() / "record-abi-XXXXXX").string();
        std::vector<char> bytes(pattern.begin(), pattern.end());
        bytes.push_back('\0');
        check(::mkdtemp(bytes.data()) != nullptr, "private fixture creation");
        root = bytes.data();
    }
    ~Fixture()
    {
        std::error_code ignored;
        fs::remove_all(root, ignored);
    }
};

struct Request {
    std::array<char, 1024> primary {}, cleanup {}, transport {};
    SrpCall call {};
    Request()
    {
        call.size = sizeof(call);
        call.abi = SRP_ABI;
        call.primary_error = {address(primary.data()), primary.size(), 0};
        call.cleanup_error = {address(cleanup.data()), cleanup.size(), 0};
        call.transport_error = {address(transport.data()), transport.size(), 0};
    }
    int32_t invoke(uint32_t opcode) { call.opcode = opcode; return srp_unix_call(&call); }
    void follow(const Request& other)
    {
        call.context = other.call.context;
        call.sequence = other.call.sequence;
        call.event = other.call.event;
    }
    void advance()
    {
        check(invoke(SRP_ADVANCE) == SRP_SUCCESS, "accepted ADVANCE transport status");
        check((call.flags & SRP_VALID) != 0, "accepted ADVANCE state valid");
    }
    void reach(uint32_t event)
    {
        while (call.event != event) {
            check(call.event != SRP_DONE, "requested native phase reachable");
            advance();
        }
    }
    std::string primary_text() const { return {primary.data(), static_cast<size_t>(call.primary_error.required)}; }
    std::string cleanup_text() const { return {cleanup.data(), static_cast<size_t>(call.cleanup_error.required)}; }
    std::string transport_text() const { return {transport.data(), static_cast<size_t>(call.transport_error.required)}; }
    void begin(const fs::path& path, const std::string& payload)
    {
        const auto name = path.string();
        call.path = slice(name);
        call.payload = slice(payload);
        check(invoke(SRP_BEGIN) == SRP_SUCCESS, "BEGIN must accept and construct a real operation");
        check(call.context != 0 && call.event == SRP_START && call.sequence == 0 && call.flags == SRP_VALID,
            "BEGIN returns live START/sequence0 without publication");
    }
};

void write(const fs::path& path, const std::string& bytes)
{
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    output << bytes;
    output.close();
    check(static_cast<bool>(output), "fixture write");
}

std::string read(const fs::path& path)
{
    std::ifstream input(path, std::ios::binary);
    check(static_cast<bool>(input), "fixture read");
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

fs::path workspace(const Fixture& fixture)
{
    std::vector<fs::path> paths;
    for (const auto& entry : fs::directory_iterator(fixture.root / ".space-publication")) paths.push_back(entry.path());
    check(paths.size() == 1, "one owned workspace");
    return paths.front();
}

void clean(const Fixture& fixture)
{
    check(fs::is_empty(fixture.root / ".space-publication"), "explicit cleanup removed owned workspace");
}

void invalid_old_id(uint64_t id)
{
    Request stale;
    stale.call.context = id;
    check(stale.invoke(SRP_SNAPSHOT) == SRP_INVALID_ARGUMENT && stale.call.context == 0
        && (stale.call.flags & SRP_VALID) == 0, "retired ID cannot be recovered or reused");
}

void begin_is_capture_only()
{
    Fixture fixture;
    Request request;
    request.begin(fixture.root / "record", "binary\0payload");
    check(!fs::exists(fixture.root / ".space-publication"), "BEGIN must not implicitly prepare");
    check(request.invoke(SRP_RELEASE) == SRP_SUCCESS, "release capture-only context");
    check(request.call.primary_state == SRP_PRIMARY_PRESENT && request.call.primary_error.required == 0,
        "release cancellation may have present empty primary");
    check(!fs::exists(fixture.root / ".space-publication"), "release START has no phantom cleanup workspace");
    invalid_old_id(request.call.context);
}

void transitions_and_owned_binary_payload()
{
    Fixture fixture;
    const auto destination = fixture.root / "record";
    write(destination, "old");
    std::string payload("new\0bytes", 9);
    const auto expected = payload;
    Request request;
    request.begin(destination, payload);
    const auto id = request.call.context;
    std::fill(payload.begin(), payload.end(), 'x');
    check(request.call.path.address == 0 && request.call.payload.address == 0 && request.call.hook_error.address == 0,
        "valid response clears borrowed input slices");
    request.advance();
    check(request.call.event == SRP_BEFORE_WRITE && request.call.sequence == 1, "prepare consumes once");
    const auto attempt = workspace(fixture);
    check(read(attempt / "record").empty(), "prepare did not write bytes");
    request.advance();
    check(request.call.event == SRP_BEFORE_SECURITY && request.call.sequence == 2
        && read(attempt / "record") == expected, "write uses copied binary input");
    request.advance();
    check(request.call.event == SRP_BEFORE_COMMIT && request.call.sequence == 3 && read(destination) == "old", "security before commit");
    request.advance();
    check(request.call.event == SRP_BEFORE_CLEANUP && request.call.sequence == 4
        && (request.call.flags & SRP_COMMITTED) && read(destination) == expected, "rename and commit truth before response");
    request.advance();
    check(request.call.event == SRP_DONE && request.call.sequence == 5 && (request.call.flags & SRP_DONE_FLAG), "cleanup transition");
    check(request.invoke(SRP_CANCEL) == SRP_SUCCESS && request.call.sequence == 6
        && (request.call.flags & SRP_COMMITTED) && request.call.primary_state == SRP_PRIMARY_ABSENT, "DONE cancellation is native no-op");
    clean(fixture);
    check(request.invoke(SRP_RELEASE) == SRP_SUCCESS && request.call.sequence == 7 && request.call.context == id,
        "release copies final sticky state before retirement");
    invalid_old_id(id);
}

void empty_errors_and_constructor_transport()
{
    for (uint32_t event : {SRP_BEFORE_WRITE, SRP_BEFORE_SECURITY, SRP_BEFORE_COMMIT, SRP_BEFORE_CLEANUP}) {
        Fixture fixture;
        Request request;
        request.begin(fixture.root / "record", "new");
        request.reach(event);
        request.call.reply = SRP_FAILED;
        request.advance();
        check(request.call.reply == SRP_CONTINUE, "response resets reply after capturing it");
        if (event == SRP_BEFORE_CLEANUP) {
            check(request.call.primary_state == SRP_PRIMARY_ABSENT && (request.call.flags & SRP_CLEANUP_PRESENT)
                && request.call.cleanup_error.required == 0 && (request.call.flags & SRP_COMMITTED), "present empty cleanup is not absence");
        } else {
            check(request.call.primary_state == SRP_PRIMARY_PRESENT && request.call.primary_error.required == 0,
                "present empty primary is not operation success");
            request.reach(SRP_DONE);
        }
        check(request.invoke(SRP_RELEASE) == SRP_SUCCESS, "error-bearing native DONE releases normally");
        invalid_old_id(request.call.context);
        clean(fixture);
    }
    Fixture fixture;
    Request request;
    const auto path = (fixture.root / "missing" / "record").string();
    request.call.path = slice(path);
    request.call.flags = UINT32_MAX;
    request.call.primary_state = UINT32_MAX;
    request.call.primary_error.required = request.call.cleanup_error.required = UINT64_MAX;
    check(request.invoke(SRP_BEGIN) == SRP_UNSUCCESSFUL, "constructor acquisition error is transport error");
    check(request.call.context == 0 && request.call.sequence == 0 && request.call.event == SRP_START && request.call.flags == 0
        && request.call.primary_state == SRP_PRIMARY_ABSENT && request.call.primary_error.required == 0
        && request.call.cleanup_error.required == 0 && request.transport_text().find("pin target parent") != std::string::npos,
        "constructor detail survives without fabricated operation state");
    check(request.call.path.address == 0 && request.call.payload.address == 0 && request.call.reply == SRP_CONTINUE,
        "no-context response also clears borrowed request storage");
    Request native;
    native.begin(fixture.root / "record", "new");
    write(fixture.root / ".space-publication", "unowned obstruction");
    native.advance();
    check(native.call.event == SRP_DONE && native.call.primary_state == SRP_PRIMARY_PRESENT
        && !native.primary_text().empty() && native.call.transport_error.required == 0
        && !(native.call.flags & SRP_COMMITTED) && !(native.call.flags & SRP_POISONED),
        "native prepare failure is an accepted error-bearing operation, not constructor/transport failure");
    check(native.invoke(SRP_RELEASE) == SRP_SUCCESS, "native failed operation finalizes normally");
    invalid_old_id(native.call.context);
    check(read(fixture.root / ".space-publication") == "unowned obstruction", "unowned prepare obstruction is not cleanup work");
}

void release_done_cleanup_errors()
{
    for (bool empty : {false, true}) {
        Fixture fixture;
        Request request;
        request.begin(fixture.root / "record", "committed");
        request.reach(SRP_BEFORE_CLEANUP);
        const std::string error = empty ? "" : "cleanup callback diagnostic";
        request.call.hook_error = slice(error);
        request.call.reply = SRP_FAILED;
        request.advance();
        check(request.call.event == SRP_DONE && (request.call.flags & SRP_CLEANUP_PRESENT), "error-bearing DONE setup");
        const auto id = request.call.context;
        request.call.cleanup_error.capacity = empty ? request.cleanup.size() : 3;
        check(request.invoke(SRP_RELEASE) == SRP_SUCCESS && (request.call.flags & SRP_VALID)
            && (request.call.flags & SRP_COMMITTED) && (request.call.flags & SRP_CLEANUP_PRESENT)
            && !(request.call.flags & SRP_POISONED) && request.call.cleanup_error.required == error.size(),
            "ordinary DONE cleanup error is completed finalization, not poison");
        check(empty ? !(request.call.flags & SRP_CLEANUP_TRUNCATED) : (request.call.flags & SRP_CLEANUP_TRUNCATED),
            "release truncation visible without replaying publication");
        check(read(fixture.root / "record") == "committed", "release retains committed bytes");
        invalid_old_id(id);
        clean(fixture);
    }
    Fixture fixture;
    Request request;
    request.begin(fixture.root / "record", "committed");
    request.reach(SRP_BEFORE_CLEANUP);
    const auto attempt = workspace(fixture);
    write(attempt / "unrelated", "keep");
    check(request.invoke(SRP_RELEASE) == SRP_SUCCESS && request.call.event == SRP_DONE
        && (request.call.flags & SRP_COMMITTED) && (request.call.flags & SRP_CLEANUP_PRESENT)
        && request.call.primary_state == SRP_PRIMARY_ABSENT && !(request.call.flags & SRP_POISONED)
        && !request.cleanup_text().empty(), "native DONE cleanup failure still returns final valid snapshot and retires");
    check(read(attempt / "unrelated") == "keep", "native cleanup did not sweep unrelated entries");
    invalid_old_id(request.call.context);
}

void cancellation_and_release_each_phase()
{
    for (bool release : {false, true}) {
        for (uint32_t event = SRP_START; event <= SRP_DONE; ++event) {
            Fixture fixture;
            Request request;
            request.begin(fixture.root / "record", "new");
            request.reach(event);
            const auto sequence = request.call.sequence;
            const std::string reason = "cancel reason";
            if (!release) request.call.hook_error = slice(reason);
            check(request.invoke(release ? SRP_RELEASE : SRP_CANCEL) == SRP_SUCCESS && request.call.sequence == sequence + 1,
                "accepted cancel/release consumes exactly one logical transition");
            const bool committed = event >= SRP_BEFORE_CLEANUP;
            check(bool(request.call.flags & SRP_COMMITTED) == committed, "cancellation cannot change known commit truth");
            if (release) {
                check(request.call.event == SRP_DONE && (request.call.flags & SRP_DONE_FLAG), "release finalizes only cleanup");
                if (event >= SRP_BEFORE_CLEANUP) check(!(request.call.flags & SRP_CLEANUP_PRESENT), "release must not invent a cleanup cancellation error");
                invalid_old_id(request.call.context);
            } else {
                if (request.call.event == SRP_BEFORE_CLEANUP) request.advance();
                check(request.invoke(SRP_RELEASE) == SRP_SUCCESS, "release cancelled context");
            }
            check(fs::exists(fixture.root / "record") == committed, "cancel never resumes publication");
            if (event == SRP_START) check(!fs::exists(fixture.root / ".space-publication"), "no owned workspace, no cleanup work");
            else clean(fixture);
        }
    }
}

void validation_and_snapshot_recovery()
{
    check(srp_unix_call(nullptr) == SRP_INVALID_ARGUMENT, "null frame");
    Request header;
    header.call.flags = 123;
    header.call.size = 144;
    check(header.invoke(SRP_BEGIN) == SRP_INVALID_ARGUMENT && header.call.flags == 123, "no 144 alias or output contract");
    header.call.size = sizeof(SrpCall);
    header.call.abi = 99;
    check(header.invoke(SRP_BEGIN) == SRP_INVALID_ARGUMENT && header.call.flags == 123, "bad ABI no output contract");
    Fixture fixture;
    Request live;
    live.begin(fixture.root / "record", "new");
    live.reach(SRP_BEFORE_WRITE);
    const auto attempt = workspace(fixture);
    const std::string extra = "x";
    for (int fault = 0; fault < 16; ++fault) {
        Request bad;
        bad.follow(live);
        bad.call.opcode = SRP_ADVANCE;
        switch (fault) {
        case 0: bad.call.opcode = 99; break;
        case 1: bad.call.reserved = 1; break;
        case 2: --bad.call.sequence; break;
        case 3: bad.call.event = SRP_BEFORE_COMMIT; break;
        case 4: bad.call.reply = 99; break;
        case 5: bad.call.payload = slice(extra); break;
        case 6: bad.call.path = slice(extra); break;
        case 7: bad.call.hook_error = slice(extra); break;
        case 8: bad.call.payload = {1, 0}; break;
        case 9: bad.call.hook_error = {0, 1}; bad.call.reply = SRP_FAILED; break;
        case 10: bad.call.hook_error = {UINT64_MAX - 1, 5}; bad.call.reply = SRP_FAILED; break;
        case 11: bad.call.primary_error = {0, 1, 0}; break;
        case 12: bad.call.cleanup_error = {UINT64_MAX - 1, 5, 0}; break;
        case 13: bad.call.transport_error.address = bad.call.primary_error.address; break;
        case 14: bad.call.primary_error = {address(&bad.call), sizeof(bad.call), 0}; break;
        case 15: bad.call.hook_error = {bad.call.primary_error.address, 1}; bad.call.reply = SRP_FAILED; break;
        }
        check(srp_unix_call(&bad.call) == SRP_INVALID_ARGUMENT, "malformed request rejected before native work");
        check(bad.call.context == live.call.context && bad.call.sequence == live.call.sequence && bad.call.event == live.call.event
            && (bad.call.flags & SRP_VALID) && bad.call.primary_state == SRP_PRIMARY_ABSENT, "invalid request returns live unmutated snapshot");
        check(read(attempt / "record").empty() && !fs::exists(fixture.root / "record"), "validation cannot write or commit");
        check(bad.call.path.address == 0 && bad.call.payload.address == 0 && bad.call.hook_error.address == 0
            && bad.call.reply == SRP_CONTINUE, "invalid usable-header response clears input fields");
    }
    // Output-only fields may contain an earlier response and must not be input validation aliases.
    live.call.flags = live.call.primary_state = UINT32_MAX;
    live.call.primary_error.required = live.call.cleanup_error.required = live.call.transport_error.required = UINT64_MAX;
    live.call.event = 99;
    live.call.sequence = UINT64_MAX;
    check(live.invoke(SRP_SNAPSHOT) == SRP_SUCCESS && live.call.sequence == 1 && live.call.event == SRP_BEFORE_WRITE
        && live.call.flags == SRP_VALID && live.call.transport_error.required == 0, "snapshot ignores stale event/sequence; validation text is response-only");
    live.reach(SRP_DONE);
    const auto done_sequence = live.call.sequence;
    check(live.invoke(SRP_ADVANCE) == SRP_INVALID_ARGUMENT && live.call.sequence == done_sequence
        && (live.call.flags & SRP_COMMITTED), "DONE advance is invalid, not a reset");
    check(live.invoke(SRP_RELEASE) == SRP_SUCCESS, "release after rejected DONE advance");
    clean(fixture);

    for (const std::string path : {std::string(), std::string("relative"), std::string("/tmp/invalid\0tail", 17)}) {
        Request bad;
        bad.call.path = slice(path);
        check(bad.invoke(SRP_BEGIN) == SRP_INVALID_ARGUMENT && bad.call.context == 0 && bad.call.flags == 0
            && bad.call.primary_state == SRP_PRIMARY_ABSENT && bad.call.primary_error.required == 0
            && bad.call.cleanup_error.required == 0 && bad.call.transport_error.required > 0,
            "empty/relative/NUL path refused as argument, not constructor/native work");
    }
}

void three_channels_and_bounded_copies()
{
    Fixture fixture;
    Request request;
    request.begin(fixture.root / "record", "new");
    request.reach(SRP_BEFORE_WRITE);
    const std::string primary = "primary diagnostic";
    request.call.reply = SRP_FAILED;
    request.call.hook_error = slice(primary);
    request.advance();
    const std::string cleanup = "cleanup diagnostic";
    request.call.reply = SRP_FAILED;
    request.call.hook_error = slice(cleanup);
    request.advance();
    request.primary.fill('#'); request.cleanup.fill('#'); request.transport.fill('#');
    request.call.primary_error.capacity = 3;
    request.call.cleanup_error.capacity = 4;
    request.call.transport_error.capacity = 5;
    request.call.sequence = 0; // Stale release gives response-only transport text, without retiring.
    check(request.invoke(SRP_RELEASE) == SRP_INVALID_ARGUMENT && request.call.primary_state == SRP_PRIMARY_PRESENT
        && (request.call.flags & SRP_CLEANUP_PRESENT) && (request.call.flags & SRP_PRIMARY_TRUNCATED)
        && (request.call.flags & SRP_CLEANUP_TRUNCATED) && (request.call.flags & SRP_TRANSPORT_TRUNCATED), "three independent truncated channels");
    check(request.call.primary_error.required == primary.size() && request.call.cleanup_error.required == cleanup.size()
        && request.call.transport_error.required > 5 && request.primary[3] == '#' && request.cleanup[4] == '#'
        && request.transport[5] == '#', "byte counts/full required sizes, no implicit NUL or overrun");
    request.call.primary_error.capacity = request.primary.size();
    request.call.cleanup_error.capacity = request.cleanup.size();
    request.call.transport_error.capacity = request.transport.size();
    check(request.invoke(SRP_SNAPSHOT) == SRP_SUCCESS && request.primary_text() == primary && request.cleanup_text() == cleanup
        && request.call.transport_error.required == 0, "snapshot recovers full primary and cleanup without replay");
    check(request.invoke(SRP_RELEASE) == SRP_SUCCESS, "release error-bearing native result");
    clean(fixture);

    Request constructor;
    const auto missing = (fixture.root / "missing" / "record").string();
    constructor.call.path = slice(missing);
    constructor.call.transport_error.capacity = 2;
    check(constructor.invoke(SRP_BEGIN) == SRP_UNSUCCESSFUL && constructor.call.context == 0
        && constructor.call.flags == SRP_TRANSPORT_TRUNCATED && constructor.call.transport_error.required > 2,
        "no-context truncation is visible; there is no context to replay/recover");
}

void unused_fields_queries_and_native_errors()
{
    Fixture fixture;
    const auto destination = fixture.root / "record";
    for (int fault = 0; fault < 6; ++fault) {
        Request bad;
        const auto name = destination.string();
        bad.call.path = slice(name);
        switch (fault) {
        case 0: bad.call.sequence = 1; break;
        case 1: bad.call.event = SRP_BEFORE_WRITE; break;
        case 2: bad.call.context = UINT64_MAX; break;
        case 3: bad.call.reply = SRP_FAILED; break;
        case 4: bad.call.hook_error = slice(name); break;
        case 5: bad.call.payload = {0, 2}; break;
        }
        check(bad.invoke(SRP_BEGIN) == SRP_INVALID_ARGUMENT && !bad.call.context
            && !fs::exists(fixture.root / ".space-publication"), "malformed BEGIN has no native filesystem work");
    }
    Request request;
    request.begin(destination, "new");
    request.reach(SRP_BEFORE_WRITE);
    for (uint32_t opcode : {SRP_SNAPSHOT, SRP_RELEASE, SRP_CANCEL}) {
        Request bad;
        bad.follow(request);
        bad.call.reply = SRP_FAILED;
        check(bad.invoke(opcode) == SRP_INVALID_ARGUMENT && bad.call.sequence == request.call.sequence, "non-ADVANCE requires CONTINUE");
        if (opcode != SRP_CANCEL) {
            bad.call.hook_error = slice(std::string()); // canonical empty storage
            bad.call.reply = SRP_CONTINUE;
            const std::string error = "unused";
            bad.call.hook_error = slice(error);
            check(bad.invoke(opcode) == SRP_INVALID_ARGUMENT, "query/release cannot carry hook errors");
        }
    }
    const auto attempt = workspace(fixture);
    const std::string primary = "primary failure";
    request.call.reply = SRP_FAILED;
    request.call.hook_error = slice(primary);
    request.advance();
    write(attempt / "unrelated", "keep");
    const std::string hook_cleanup = "cleanup hook";
    request.call.reply = SRP_FAILED;
    request.call.hook_error = slice(hook_cleanup);
    request.advance();
    check(request.primary_text() == primary && request.cleanup_text().find("cleanup hook; ") == 0
        && !fs::exists(attempt / "record") && read(attempt / "unrelated") == "keep", "primary plus hook/native cleanup errors are not replaced by transport status");
    request.call.primary_error = request.call.cleanup_error = request.call.transport_error = {};
    check(request.invoke(SRP_SNAPSHOT) == SRP_SUCCESS && request.call.primary_error.required == primary.size()
        && request.call.cleanup_error.required > hook_cleanup.size() && (request.call.flags & SRP_PRIMARY_TRUNCATED)
        && (request.call.flags & SRP_CLEANUP_TRUNCATED), "zero-capacity queries report complete lengths without buffers");
    check(request.invoke(SRP_RELEASE) == SRP_SUCCESS && request.call.primary_state == SRP_PRIMARY_PRESENT
        && (request.call.flags & SRP_CLEANUP_PRESENT), "release copies presence even without text capacity");
    invalid_old_id(request.call.context);
}

void poison_and_allocation_free_postcommit_snapshot()
{
    Fixture fixture;
    Request request;
    request.begin(fixture.root / "record", "committed");
    request.reach(SRP_BEFORE_CLEANUP);
    const auto sequence = request.call.sequence;
    const std::string long_error(2000, 'e');
    request.call.reply = SRP_FAILED;
    request.call.hook_error = slice(long_error);
    allocation_test::attempts = 0;
    allocation_test::disabled = true;
    const auto status = request.invoke(SRP_ADVANCE);
    allocation_test::disabled = false;
    check(status == SRP_UNSUCCESSFUL && allocation_test::attempts > 0 && request.call.sequence == sequence + 1
        && request.call.event == SRP_BEFORE_CLEANUP && (request.call.flags & SRP_COMMITTED)
        && (request.call.flags & SRP_POISONED) && (request.call.flags & SRP_TRANSPORT_TRUNCATED), "contained live error consumes sequence and preserves sticky commit");
    check(request.call.transport_error.required == 512 && request.transport_text().find("[truncated]") != std::string::npos,
        "bounded producer diagnostic carries explicit truncation marker");
    const auto diagnostic = request.transport_text();
    const std::string cleanup = "cleanup fault";
    request.call.reply = SRP_FAILED;
    request.call.hook_error = slice(cleanup);
    request.advance(); // Poison permits cleanup, not publication.
    request.call.event = 99; request.call.sequence = UINT64_MAX;
    allocation_test::attempts = 0;
    allocation_test::disabled = true;
    const auto snapshot_status = request.invoke(SRP_SNAPSHOT);
    allocation_test::disabled = false;
    check(snapshot_status == SRP_SUCCESS && allocation_test::attempts == 0 && request.call.event == SRP_DONE
        && (request.call.flags & SRP_COMMITTED) && (request.call.flags & SRP_POISONED)
        && request.call.primary_state == SRP_PRIMARY_ABSENT && request.call.primary_error.required == 0
        && (request.call.flags & SRP_CLEANUP_PRESENT) && request.cleanup_text() == cleanup
        && request.transport_text() == diagnostic, "allocation-disabled postcommit snapshot returns all three channels without native advance");
    check(read(fixture.root / "record") == "committed", "snapshot recovery cannot replay publication");
    check(request.invoke(SRP_RELEASE) == SRP_SUCCESS && (request.call.flags & SRP_COMMITTED), "poisoned completed native context can retire");
    invalid_old_id(request.call.context);
    clean(fixture);
}

void poison_prevents_publication_and_release_recovers()
{
    Fixture fixture;
    Request request;
    request.begin(fixture.root / "record", "new");
    request.reach(SRP_BEFORE_WRITE);
    const std::string long_error(2000, 'e');
    request.call.reply = SRP_FAILED; request.call.hook_error = slice(long_error);
    allocation_test::disabled = true;
    const auto status = request.invoke(SRP_ADVANCE);
    allocation_test::disabled = false;
    check(status == SRP_UNSUCCESSFUL && (request.call.flags & SRP_POISONED), "precommit poison setup");
    const auto sequence = request.call.sequence;
    check(request.invoke(SRP_ADVANCE) == SRP_UNSUCCESSFUL && request.call.sequence == sequence
        && read(workspace(fixture) / "record").empty(), "poison cannot resume publication");
    check(request.invoke(SRP_CANCEL) == SRP_SUCCESS && request.call.primary_state == SRP_PRIMARY_PRESENT
        && request.call.primary_error.required == 0, "poison still permits explicit empty-reason cancellation");
    check(request.invoke(SRP_RELEASE) == SRP_SUCCESS && !(request.call.flags & SRP_COMMITTED), "release poison cleans only");
    clean(fixture);

    Request finalization;
    finalization.begin(fixture.root / "second", "committed");
    finalization.reach(SRP_BEFORE_CLEANUP);
    const auto attempt = workspace(fixture);
    write(attempt / "unrelated", "keep");
    const auto id = finalization.call.context;
    allocation_test::disabled = true;
    const auto release_status = finalization.invoke(SRP_RELEASE);
    allocation_test::disabled = false;
    check(release_status == SRP_UNSUCCESSFUL && finalization.call.context == id
        && (finalization.call.flags & SRP_POISONED) && (finalization.call.flags & SRP_COMMITTED), "unexpected incomplete finalization retains recoverable ownership");
    check(finalization.invoke(SRP_SNAPSHOT) == SRP_SUCCESS && finalization.call.context == id, "failed release ID remains queryable");
    fs::remove(attempt / "unrelated");
    check(finalization.invoke(SRP_RELEASE) == SRP_SUCCESS && (finalization.call.flags & SRP_COMMITTED), "explicit finalization recovery retires only after completion");
    invalid_old_id(id);
    clean(fixture);
}

void overlapping_and_racing_contexts()
{
    Fixture fixture;
    Request outer, inner;
    outer.begin(fixture.root / "outer", "outer");
    outer.reach(SRP_BEFORE_WRITE);
    inner.begin(fixture.root / "inner", "inner");
    check(inner.call.context > outer.call.context, "IDs monotonic, never recycled");
    inner.reach(SRP_DONE);
    check(inner.invoke(SRP_RELEASE) == SRP_SUCCESS && read(workspace(fixture) / "record").empty(), "inner release leaves outer live context untouched");
    outer.reach(SRP_DONE);
    check(outer.invoke(SRP_RELEASE) == SRP_SUCCESS, "outer publication completes independently");
    for (bool release_race : {false, true}) {
        for (int i = 0; i < 40; ++i) {
            Request source, first, second;
            source.begin(fixture.root / ("race-" + std::to_string(release_race) + "-" + std::to_string(i)), "race");
            source.reach(release_race ? SRP_BEFORE_COMMIT : SRP_BEFORE_WRITE);
            first.follow(source); second.follow(source);
            std::atomic<bool> start {false};
            int32_t a = SRP_UNSUCCESSFUL, b = SRP_UNSUCCESSFUL;
            std::thread one([&] { while (!start.load()) std::this_thread::yield(); a = first.invoke(SRP_ADVANCE); });
            std::thread two([&] { while (!start.load()) std::this_thread::yield(); b = second.invoke(release_race ? SRP_RELEASE : SRP_ADVANCE); });
            start = true;
            one.join(); two.join();
            check((a == SRP_SUCCESS && b == SRP_INVALID_ARGUMENT) || (b == SRP_SUCCESS && a == SRP_INVALID_ARGUMENT),
                "same-context duplicate/racing mutation consumes exact continuation once");
            Request recovery;
            recovery.follow(source);
            if (release_race && b == SRP_SUCCESS) invalid_old_id(source.call.context);
            else {
                check(recovery.invoke(SRP_SNAPSHOT) == SRP_SUCCESS && recovery.call.sequence == source.call.sequence + 1,
                    "stale racing release cannot erase newer operation state");
                if (release_race) check(recovery.call.flags & SRP_COMMITTED, "racing advance commit truth survives stale release");
                check(recovery.invoke(SRP_RELEASE) == SRP_SUCCESS, "release race survivor");
            }
            clean(fixture);
        }
    }
}

} // namespace

int main()
{
    try {
        begin_is_capture_only();
        transitions_and_owned_binary_payload();
        empty_errors_and_constructor_transport();
        release_done_cleanup_errors();
        cancellation_and_release_each_phase();
        validation_and_snapshot_recovery();
        three_channels_and_bounded_copies();
        unused_fields_queries_and_native_errors();
        poison_and_allocation_free_postcommit_snapshot();
        poison_prevents_publication_and_release_recovers();
        overlapping_and_racing_contexts();
        std::cout << "record publication ABI tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
