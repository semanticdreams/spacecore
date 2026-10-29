#include "ssh_backend_libssh.h"
#include "ssh_service.h"

#include <libssh/libssh.h>
#include <libssh/sftp.h>

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <unistd.h>

namespace
{
using namespace space::ssh;
using namespace std::chrono_literals;

void require(bool value, const char* message)
{
    if (!value) throw std::runtime_error(message);
}

// Executable-local wrappers always call the real backend. Injection changes only
// the reported close status AFTER the real, consuming close has returned.
struct Observation
{
    std::mutex mutex;
    std::condition_variable changed;
    std::string gate;
    bool entered { false };
    bool released { false };
    bool gate_expired { false };
    bool inject_close_error { false };
    std::string invalidate_local_input;
    bool local_input_invalidated { false };
    bool invalid_lifetime { false };
    unsigned opens { 0 }, closes { 0 }, frees { 0 };
    std::map<sftp_file, sftp_session> files;
    std::map<sftp_session, ssh_session> sessions;
    std::vector<std::string> order;

    void pause(const char* point)
    {
        std::unique_lock<std::mutex> lock(mutex);
        order.emplace_back(point);
        if (gate != point) return;
        entered = true;
        changed.notify_all();
        if (!changed.wait_for(lock, 5s, [&] { return released; }))
            gate_expired = true;
    }

    void release()
    {
        std::lock_guard<std::mutex> lock(mutex);
        released = true;
        changed.notify_all();
    }

    void reset(std::string point = {}, bool inject = false)
    {
        std::lock_guard<std::mutex> lock(mutex);
        require(files.empty() && sessions.empty(), "previous transfer did not drain");
        gate = std::move(point);
        entered = released = gate_expired = invalid_lifetime = false;
        inject_close_error = inject;
        invalidate_local_input.clear();
        local_input_invalidated = false;
        opens = closes = frees = 0;
        order.clear();
    }
} observation;

std::string env(const char* key)
{
    const char* value = std::getenv(key);
    require(value && *value, "missing required fixture environment");
    return value;
}

bool terminal(EventKind kind)
{
    return kind == EventKind::OperationSuccess || kind == EventKind::OperationError
        || kind == EventKind::OperationCancelled || kind == EventKind::OperationTimeout;
}

struct Fixture
{
    Service service { make_libssh_backend() };
    SessionId session { 0 };
    std::vector<Event> events;
    std::string root { env("SPACE_TEST_SSH_ROOT") };

    Fixture()
    {
        ConnectOptions options;
        options.target = { env("SPACE_TEST_SSH_HOST"),
            static_cast<uint16_t>(std::stoi(env("SPACE_TEST_SSH_PORT"))), env("SPACE_TEST_SSH_USER") };
        AuthMethod auth;
        auth.type = AuthMethodType::PrivateKey;
        auth.key_path = env("SPACE_TEST_SSH_KEY");
        options.auth_methods = { auth };
        options.known_hosts_path = env("SPACE_TEST_SSH_KNOWN_HOSTS");
        options.known_host_policy = KnownHostPolicy::AcceptOnce;
        options.timeout_ms = 5000;
        auto id = service.connect(options);
        require(wait(id).kind == EventKind::OperationSuccess, "real fixture connect failed");
        for (const auto& event : events)
            if (event.kind == EventKind::Connected) session = event.session_id;
        require(session != 0, "missing connected session");
        events.clear();
        std::lock_guard<std::mutex> lock(observation.mutex);
        observation.order.clear();
    }

    ~Fixture()
    {
        // Release before shutdown joins workers, including when an assertion throws.
        observation.release();
        service.shutdown();
    }

    void poll()
    {
        auto next = service.poll();
        for (const auto& event : next)
        {
            if (event.kind == EventKind::SftpComplete || event.kind == EventKind::OperationSuccess)
            {
                std::lock_guard<std::mutex> lock(observation.mutex);
                observation.order.emplace_back(event.kind == EventKind::SftpComplete ? "complete" : "success");
            }
            events.push_back(event);
        }
    }

    Event wait(OperationId id)
    {
        const auto end = std::chrono::steady_clock::now() + 8s;
        do
        {
            poll();
            for (const auto& event : events)
                if (event.operation_id == id && terminal(event.kind)) return event;
            std::this_thread::sleep_for(2ms);
        } while (std::chrono::steady_clock::now() < end);
        throw std::runtime_error("operation did not terminate within bound");
    }

    OperationId transfer(bool upload, const std::string& local, const std::string& remote, uint64_t timeout = 0)
    {
        SftpTransferOptions options { local, remote, timeout };
        return upload ? service.sftp_upload(session, options) : service.sftp_download(session, options);
    }

    void no_success(OperationId id)
    {
        poll();
        for (const auto& event : events)
            require(event.operation_id != id || (event.kind != EventKind::SftpComplete
                && event.kind != EventKind::OperationSuccess), "premature/late successful transfer notification");
    }

    void drain()
    {
        observation.release();
        {
            std::unique_lock<std::mutex> lock(observation.mutex);
            require(observation.changed.wait_for(lock, 8s, [] {
                return observation.files.empty() && observation.sessions.empty();
            }), "native resources did not drain within bound");
        }
        const auto end = std::chrono::steady_clock::now() + 60ms;
        while (std::chrono::steady_clock::now() < end)
        {
            poll();
            std::this_thread::sleep_for(2ms);
        }
        service.shutdown();
        poll();
        std::lock_guard<std::mutex> lock(observation.mutex);
        require(!observation.gate_expired, "test gate timed out");
        require(!observation.invalid_lifetime, "invalid native resource lifetime");
        require(observation.files.empty() && observation.sessions.empty(), "native resources not drained");
        require(observation.opens == observation.closes, "file not closed exactly once");
        require(observation.frees <= 1, "SFTP session freed more than once");
    }
};

void write_file(const std::string& path, const std::string& bytes)
{
    std::ofstream out(path, std::ios::binary);
    out.write(bytes.data(), bytes.size());
    out.close();
    require(bool(out), "fixture file write failed");
}

std::string read_file(const std::string& path)
{
    std::ifstream in(path, std::ios::binary);
    require(bool(in), "fixture file read failed");
    return { std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>() };
}

void wait_gate(Fixture& fixture)
{
    std::unique_lock<std::mutex> lock(observation.mutex);
    require(observation.changed.wait_for(lock, 4s, [] { return observation.entered; }), "worker did not reach gate");
    lock.unlock();
    // Poll a bounded interval: absence at a single instant would miss queued events.
    const auto end = std::chrono::steady_clock::now() + 60ms;
    while (std::chrono::steady_clock::now() < end)
    {
        fixture.poll();
        std::this_thread::sleep_for(2ms);
    }
}

void success_case(bool upload, const std::string& data, const std::string& gate)
{
    observation.reset(gate);
    Fixture f;
    const auto local = f.root + "/local";
    const auto remote = f.root + "/remote";
    write_file(upload ? local : remote, data);
    auto id = f.transfer(upload, local, remote);
    wait_gate(f);
    f.no_success(id);
    observation.release();
    require(f.wait(id).kind == EventKind::OperationSuccess, "transfer should succeed");
    require(read_file(upload ? remote : local) == data, "success did not expose exact bytes immediately");
    f.drain();
    std::lock_guard<std::mutex> lock(observation.mutex);
    const auto& order = observation.order;
    auto close = std::find(order.begin(), order.end(), "close-exit");
    auto free = std::find(order.begin(), order.end(), "free-exit");
    auto complete = std::find(order.begin(), order.end(), "complete");
    auto success = std::find(order.begin(), order.end(), "success");
    require(close < free && free < complete && complete < success && success != order.end(), "close/free/success ordering violated");
    require(std::count(order.begin(), order.end(), "complete") == 1
        && std::count(order.begin(), order.end(), "success") == 1, "duplicate successful transfer notification");
    require(observation.opens == 1 && observation.frees == 1, "expected real native transfer");
}

void error_case(bool upload, const std::string& local_kind, bool inject, ErrorCode code)
{
    observation.reset({}, inject);
    Fixture f;
    auto local = f.root + "/local";
    auto remote = f.root + "/remote";
    write_file(remote, "buffered final bytes");
    if (local_kind == "missing") local += "/missing";
    else if (local_kind == "directory") local = f.root;
    else if (local_kind == "full") local = "/dev/full";
    else write_file(local, "upload bytes");
    if (local_kind == "read-error")
    {
        std::lock_guard<std::mutex> lock(observation.mutex);
        observation.invalidate_local_input = local;
    }
    auto id = f.transfer(upload, local, remote);
    auto event = f.wait(id);
    require(event.kind == EventKind::OperationError && event.error_code == code, "wrong/missing finalization error");
    f.drain();
    f.no_success(id);
    if (local_kind == "normal" || local_kind == "read-error" || local_kind == "full")
    {
        std::lock_guard<std::mutex> lock(observation.mutex);
        require(observation.opens == 1 && observation.closes == 1 && observation.frees == 1,
            "error case did not exercise real close/free exactly once");
    }
    if (local_kind == "read-error")
    {
        std::lock_guard<std::mutex> lock(observation.mutex);
        require(observation.local_input_invalidated, "local read-error seam did not execute");
    }
}

void interrupted_case(bool upload, const std::string& gate, bool timeout)
{
    observation.reset(gate);
    Fixture f;
    auto local = f.root + "/local";
    auto remote = f.root + "/remote";
    write_file(upload ? local : remote, "cancelled bytes");
    auto id = f.transfer(upload, local, remote, timeout ? 500 : 0);
    wait_gate(f);
    f.no_success(id);
    // cancel queues its terminal first, but its caller can block in backend
    // close. Keep that caller off the gate-controlling thread and always join.
    struct CancelCaller
    {
        std::thread thread;
        bool accepted { false };
        ~CancelCaller()
        {
            observation.release();
            if (thread.joinable()) thread.join();
        }
    } caller;
    if (!timeout) caller.thread = std::thread([&] { caller.accepted = f.service.cancel(id); });
    const auto expected = timeout ? EventKind::OperationTimeout : EventKind::OperationCancelled;
    require(f.wait(id).kind == expected, "terminal winner was not preserved while gated");
    // Close the public session while transfer teardown still holds the parent.
    auto close = f.service.close_session(f.session);
    require(f.wait(close).kind == EventKind::OperationSuccess, "session close failed");
    observation.release();
    if (caller.thread.joinable())
    {
        caller.thread.join();
        require(caller.accepted, "cancellation rejected");
    }
    f.drain();
    f.no_success(id);
    unsigned terminals = 0;
    for (const auto& event : f.events)
        if (event.operation_id == id && terminal(event.kind)) ++terminals;
    require(terminals == 1, "more than one terminal winner");
}
}

extern "C"
{
sftp_file __real_sftp_open(sftp_session, const char*, int, mode_t);
int __real_sftp_close(sftp_file);
void __real_sftp_free(sftp_session);
ssize_t __real_sftp_read(sftp_file, void*, size_t);
ssize_t __real_sftp_write(sftp_file, const void*, size_t);
void __real_ssh_free(ssh_session);

sftp_file __wrap_sftp_open(sftp_session session, const char* path, int flags, mode_t mode)
{
    auto file = __real_sftp_open(session, path, flags, mode);
    if (file)
    {
        std::lock_guard<std::mutex> lock(observation.mutex);
        observation.files.emplace(file, session);
        observation.sessions.emplace(session, session->session);
        ++observation.opens;
        // Test-only Linux seam: after size/seek and real remote open, invalidate
        // the already-open local input descriptor. The next real ifstream read
        // fails with EBADF, not EOF. No production injection API is introduced.
        if (!observation.invalidate_local_input.empty())
        {
            for (const auto& entry : std::filesystem::directory_iterator("/proc/self/fd"))
            {
                std::error_code error;
                auto path = std::filesystem::read_symlink(entry.path(), error);
                if (!error && path == observation.invalidate_local_input)
                {
                    observation.local_input_invalidated = ::close(std::stoi(entry.path().filename().string())) == 0;
                    break;
                }
            }
        }
    }
    return file;
}

int __wrap_sftp_close(sftp_file file)
{
    observation.pause("close-enter");
    {
        std::lock_guard<std::mutex> lock(observation.mutex);
        auto it = observation.files.find(file);
        if (it == observation.files.end() || !observation.sessions.count(it->second))
        {
            observation.invalid_lifetime = true;
            return SSH_ERROR; // Do not dereference an already consumed handle.
        }
    }
    int result = __real_sftp_close(file);
    std::lock_guard<std::mutex> lock(observation.mutex);
    observation.files.erase(file);
    ++observation.closes;
    observation.order.emplace_back("close-exit");
    return observation.inject_close_error ? SSH_ERROR : result;
}

void __wrap_sftp_free(sftp_session session)
{
    observation.pause("free-enter");
    {
        std::lock_guard<std::mutex> lock(observation.mutex);
        for (const auto& [file, parent] : observation.files)
            if (parent == session) observation.invalid_lifetime = true;
    }
    __real_sftp_free(session);
    std::lock_guard<std::mutex> lock(observation.mutex);
    observation.sessions.erase(session);
    ++observation.frees;
    observation.order.emplace_back("free-exit");
    observation.changed.notify_all();
}

ssize_t __wrap_sftp_read(sftp_file file, void* buffer, size_t size)
{
    {
        std::lock_guard<std::mutex> lock(observation.mutex);
        if (!observation.files.count(file)) observation.invalid_lifetime = true;
    }
    return __real_sftp_read(file, buffer, size);
}

ssize_t __wrap_sftp_write(sftp_file file, const void* buffer, size_t size)
{
    {
        std::lock_guard<std::mutex> lock(observation.mutex);
        if (!observation.files.count(file)) observation.invalid_lifetime = true;
    }
    return __real_sftp_write(file, buffer, size);
}

void __wrap_ssh_free(ssh_session session)
{
    {
        std::lock_guard<std::mutex> lock(observation.mutex);
        for (const auto& [sftp, parent] : observation.sessions)
            if (parent == session) observation.invalid_lifetime = true;
    }
    __real_ssh_free(session);
}
}

int main(int argc, char** argv)
{
    if (argc != 3 || std::string(argv[1]) != "-m" || std::string(argv[2]) != "ssh-sftp-finalization") return 2;
    unsigned failures = 0, cases = 0;
    auto run = [&](const std::string& name, auto test) {
        ++cases;
        try { test(); std::cout << "PASS " << name << '\n'; }
        catch (const std::exception& error)
        {
            observation.release();
            ++failures;
            std::cerr << "FAIL " << name << ": " << error.what() << '\n';
        }
    };
    std::string binary(32771, '\0');
    for (size_t i = 0; i < binary.size(); ++i) binary[i] = static_cast<char>(i % 256);
    for (bool upload : { true, false })
    {
        const std::string direction = upload ? "upload " : "download ";
        for (const std::string gate : { "close-enter", "free-enter" })
        {
            run(direction + gate + " binary", [&] { success_case(upload, binary, gate); });
            run(direction + gate + " empty", [&] { success_case(upload, {}, gate); });
            run(direction + gate + " cancel/session-close", [&] { interrupted_case(upload, gate, false); });
            run(direction + gate + " timeout/session-close", [&] { interrupted_case(upload, gate, true); });
        }
        run(direction + "injected close error (real close first)", [&] { error_case(upload, "normal", true, ErrorCode::RemoteFileError); });
        for (bool inject : { false, true })
        {
            run(direction + "invalid local path" + (inject ? " + injected close" : ""), [&] { error_case(upload, "missing", inject, ErrorCode::LocalFileError); });
            run(direction + "directory local path" + (inject ? " + injected close" : ""), [&] { error_case(upload, "directory", inject, ErrorCode::LocalFileError); });
            if (upload) run(direction + "non-EOF read failure" + (inject ? " + injected close" : ""), [&] { error_case(true, "read-error", inject, ErrorCode::LocalFileError); });
            if (!upload) run(direction + "buffered /dev/full" + (inject ? " + injected close" : ""), [&] { error_case(false, "full", inject, ErrorCode::LocalFileError); });
        }
    }
    std::cout << cases - failures << '/' << cases << " cases passed\n";
    return failures ? 1 : 0;
}
