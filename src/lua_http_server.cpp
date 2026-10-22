#include "lua_http_server.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include "httplib.h"

using namespace std::chrono_literals;

namespace {

class HttpServer;

std::mutex g_servers_mutex;
std::vector<HttpServer*> g_servers;

bool http_lifecycle_debug_enabled()
{
    // Enable high-volume callback/request diagnostics with SPACE_HTTP_LIFECYCLE_DEBUG=1.
    static const bool enabled = []() {
        const char* value = std::getenv("SPACE_HTTP_LIFECYCLE_DEBUG");
        return value && value[0] != '\0' && value[0] != '0';
    }();
    return enabled;
}

bool native_lifecycle_diagnostics_enabled()
{
    // Sparse native lifecycle diagnostics are on by default for spontaneous crash evidence.
    // Disable with SPACE_NATIVE_LIFECYCLE_DIAGNOSTICS=0 when stderr noise is not acceptable.
    static const bool enabled = []() {
        const char* value = std::getenv("SPACE_NATIVE_LIFECYCLE_DIAGNOSTICS");
        return !(value && value[0] == '0' && value[1] == '\0');
    }();
    return enabled;
}

unsigned long long diagnostic_thread_id()
{
    return static_cast<unsigned long long>(std::hash<std::thread::id> {}(std::this_thread::get_id()));
}

void http_lifecycle_diag(const char* event,
                         const void* server,
                         bool running,
                         std::size_t pending_count,
                         std::size_t stream_count,
                         bool always_on)
{
    if (!(always_on ? native_lifecycle_diagnostics_enabled() : http_lifecycle_debug_enabled())) {
        return;
    }
    std::fprintf(stderr,
                 "space-http-lifecycle event=%s server=%p thread=%llu running=%d pending=%zu streams=%zu\n",
                 event,
                 server,
                 diagnostic_thread_id(),
                 running ? 1 : 0,
                 pending_count,
                 stream_count);
    std::fflush(stderr);
}

void http_lifecycle_diag_global(const char* event, std::size_t count, const std::vector<HttpServer*>& servers)
{
    if (!native_lifecycle_diagnostics_enabled()) {
        return;
    }
    std::fprintf(stderr,
                 "space-http-lifecycle event=%s thread=%llu server_count=%zu servers=",
                 event,
                 diagnostic_thread_id(),
                 count);
    for (HttpServer* server : servers) {
        std::fprintf(stderr, "%s%p", server == servers.front() ? "" : ",", static_cast<void*>(server));
    }
    std::fprintf(stderr, "\n");
    std::fflush(stderr);
}

class SSEStream
{
public:
    bool send(std::string data)
    {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (closed_) {
                return false;
            }
            chunks_.push(std::move(data));
        }
        cv_.notify_one();
        return true;
    }

    void close()
    {
        mark_closed();
    }

    void set_close_handler(uint64_t handler_id, std::function<void(uint64_t)> enqueue_close)
    {
        bool notify_now = false;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            close_handler_id_ = handler_id;
            enqueue_close_ = std::move(enqueue_close);
            notify_now = closed_ && !close_notified_;
        }
        if (notify_now) {
            notify_closed_once();
        }
    }

    bool write_chunks(uint64_t /*offset*/, httplib::DataSink& sink)
    {
        std::unique_lock<std::mutex> lock(mutex_);
        while (chunks_.empty() && !closed_) {
            if (cv_.wait_for(lock, 1s) == std::cv_status::timeout) {
                lock.unlock();
                const bool writable = !sink.is_writable || sink.is_writable();
                if (!writable) {
                    mark_closed();
                    return false;
                }
                lock.lock();
            }
        }

        while (!chunks_.empty()) {
            auto chunk = std::move(chunks_.front());
            chunks_.pop();
            lock.unlock();
            const bool wrote = sink.write(chunk.data(), chunk.size());
            lock.lock();
            if (!wrote) {
                lock.unlock();
                mark_closed();
                return false;
            }
        }
        return !closed_;
    }

private:
    void mark_closed()
    {
        bool should_notify = false;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (!closed_) {
                closed_ = true;
            }
            should_notify = !close_notified_;
        }
        cv_.notify_one();
        if (should_notify) {
            notify_closed_once();
        }
    }

    void notify_closed_once()
    {
        uint64_t handler_id = 0;
        std::function<void(uint64_t)> enqueue_close;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (close_notified_) {
                return;
            }
            close_notified_ = true;
            handler_id = close_handler_id_;
            enqueue_close = enqueue_close_;
        }
        if (handler_id != 0 && enqueue_close) {
            enqueue_close(handler_id);
        }
    }

    std::mutex mutex_;
    std::condition_variable cv_;
    std::queue<std::string> chunks_;
    bool closed_ = false;
    bool close_notified_ = false;
    uint64_t close_handler_id_ = 0;
    std::function<void(uint64_t)> enqueue_close_;
};

struct RequestData
{
    std::string method;
    std::string path;
    std::string body;
    std::vector<std::pair<std::string, std::string>> headers;
    std::vector<std::pair<std::string, std::string>> params;
};

struct ResponseData
{
    int status = 200;
    std::string body;
    std::vector<std::pair<std::string, std::string>> headers;
};

struct PendingCall
{
    enum class Kind
    {
        Route,
        Sse,
        SseClose
    };

    Kind kind = Kind::Route;
    uint64_t handler_id = 0;
    RequestData request;
    std::shared_ptr<SSEStream> stream;
    ResponseData response;
    std::mutex mutex;
    std::condition_variable cv;
    bool done = false;
};

RequestData copy_request(const httplib::Request& req)
{
    RequestData data;
    data.method = req.method;
    data.path = req.path;
    data.body = req.body;
    for (const auto& [key, value] : req.headers) {
        data.headers.emplace_back(key, value);
    }
    for (const auto& [key, value] : req.params) {
        data.params.emplace_back(key, value);
    }
    return data;
}

void apply_response(ResponseData& response, sol::object& result)
{
    if (result.is<sol::table>()) {
        sol::table resp_tbl = result.as<sol::table>();
        response.status = resp_tbl.get_or("status", 200);
        response.body = resp_tbl.get_or<std::string>("body", "");
        sol::optional<sol::table> resp_headers =
            resp_tbl.get<sol::optional<sol::table>>("headers");
        if (resp_headers) {
            for (auto& [key, value] : *resp_headers) {
                if (value.template is<std::string>()) {
                    response.headers.emplace_back(key.as<std::string>(),
                                                  value.template as<std::string>());
                }
            }
        }
    } else if (result.is<sol::nil_t>()) {
        response.status = 204;
    } else {
        response.status = 200;
        response.body = result.as<std::string>();
    }
}

class HttpServer
{
public:
    explicit HttpServer(sol::state_view lua)
    {
        (void)lua;
        lifecycle_emit("ctor-enter");
        {
            std::lock_guard<std::mutex> lock(g_servers_mutex);
            g_servers.push_back(this);
        }
        lifecycle_emit("register");
    }

    ~HttpServer()
    {
        lifecycle_emit("dtor-enter");
        stop();
        bool unregistered = false;
        {
            std::lock_guard<std::mutex> lock(g_servers_mutex);
            auto it = std::find(g_servers.begin(), g_servers.end(), this);
            if (it != g_servers.end()) {
                g_servers.erase(it);
                unregistered = true;
            }
        }
        if (unregistered) {
            lifecycle_emit("unregister");
        }
        fail_pending("HTTP server stopped");
        lifecycle_emit("dtor-exit");
    }

    HttpServer(const HttpServer&) = delete;
    HttpServer& operator=(const HttpServer&) = delete;

    int listen(const std::string& hostname, int port)
    {
        if (port_ != 0 || running_) {
            throw std::runtime_error("HTTP server: listen called more than once");
        }

        svr_.set_keep_alive_max_count(100);
        svr_.set_keep_alive_timeout(30);
        svr_.set_read_timeout(30, 0);
        svr_.set_write_timeout(30, 0);
        svr_.set_idle_interval(0, 50000);

        int actual_port = port;
        if (port == 0) {
            actual_port = svr_.bind_to_any_port(hostname.c_str());
        } else if (!svr_.bind_to_port(hostname.c_str(), port)) {
            actual_port = -1;
        }
        if (actual_port < 0) {
            throw std::runtime_error("HTTP server: failed to bind to port " + std::to_string(port));
        }
        port_ = actual_port;
        running_ = true;

        server_thread_ = std::thread([this]() {
            svr_.listen_after_bind();
        });
        svr_.wait_until_ready();

        return actual_port;
    }

    void stop()
    {
        lifecycle_emit("stop-enter");
        const bool was_running = running_.exchange(false);
        if (was_running) {
            lifecycle_emit("stop-close-streams-before");
            close_streams();
            lifecycle_emit("stop-close-streams-after");
            lifecycle_emit("stop-svr-stop-before");
            svr_.stop();
            lifecycle_emit("stop-svr-stop-after");
            lifecycle_emit("stop-fail-pending-before");
            fail_pending("HTTP server stopped");
            lifecycle_emit("stop-fail-pending-after");
            if (server_thread_.joinable()) {
                lifecycle_emit("stop-join-before");
                server_thread_.join();
                lifecycle_emit("stop-join-after");
            }
        }
        lifecycle_emit("stop-exit");
    }

    int port() const { return port_; }

    void route(const std::string& method, const std::string& path, sol::function handler)
    {
        assert_can_register_route();

        uint64_t handler_id = next_handler_id_++;
        handlers_.emplace(handler_id, std::move(handler));

        auto handler_func = [this, handler_id](const httplib::Request& req, httplib::Response& res) {
            auto pending = std::make_shared<PendingCall>();
            pending->kind = PendingCall::Kind::Route;
            pending->handler_id = handler_id;
            pending->request = copy_request(req);
            wait_for_lua(pending);
            res.status = pending->response.status;
            res.body = std::move(pending->response.body);
            for (const auto& [key, value] : pending->response.headers) {
                res.set_header(key, value);
            }
        };

        if (method == "GET") {
            svr_.Get(path, handler_func);
        } else if (method == "POST") {
            svr_.Post(path, handler_func);
        } else {
            throw std::runtime_error("HTTP server: unsupported route method " + method);
        }
    }

    void route_sse(const std::string& path, sol::function handler)
    {
        assert_can_register_route();

        uint64_t handler_id = next_handler_id_++;
        handlers_.emplace(handler_id, std::move(handler));

        svr_.Get(path, [this, handler_id](const httplib::Request& req, httplib::Response& res) {
            diagnostic_emit("sse-route-begin");
            auto stream = std::make_shared<SSEStream>();
            track_stream(stream);
            auto pending = std::make_shared<PendingCall>();
            pending->kind = PendingCall::Kind::Sse;
            pending->handler_id = handler_id;
            pending->request = copy_request(req);
            pending->stream = stream;
            wait_for_lua(pending);

            if (pending->response.status >= 400) {
                res.status = pending->response.status;
                res.body = std::move(pending->response.body);
                for (const auto& [key, value] : pending->response.headers) {
                    res.set_header(key, value);
                }
                diagnostic_emit("sse-route-end-error");
                return;
            }

            res.set_header("Cache-Control", "no-cache");
            res.set_header("Connection", "keep-alive");
            res.set_chunked_content_provider(
                "text/event-stream",
                [stream = std::move(stream)](uint64_t offset, httplib::DataSink& sink) -> bool {
                    return stream->write_chunks(offset, sink);
                });
            diagnostic_emit("sse-route-end");
        });
    }

    void dispatch(sol::state_view lua)
    {
        while (true) {
            std::shared_ptr<PendingCall> pending;
            {
                std::lock_guard<std::mutex> lock(pending_mutex_);
                if (pending_.empty()) {
                    return;
                }
                pending = std::move(pending_.front());
                pending_.pop_front();
            }
            dispatch_one(lua, pending);
        }
    }

    void diagnostic_emit(const char* event)
    {
        if (!http_lifecycle_debug_enabled()) {
            return;
        }
        http_lifecycle_diag(event, this, running_.load(), pending_count(), stream_count(), false);
    }

    void lifecycle_emit(const char* event)
    {
        if (!native_lifecycle_diagnostics_enabled()) {
            return;
        }
        http_lifecycle_diag(event, this, running_.load(), pending_count(), stream_count(), true);
    }

private:
    // sol2 derives GC metatable names from callable types. Named types keep
    // these differently laid-out captures on distinct finalizer identities.
    struct SseSend
    {
        std::shared_ptr<SSEStream> stream;

        bool operator()(sol::variadic_args args) const
        {
            for (auto arg : args) {
                sol::object obj = arg;
                if (obj.is<std::string>()) {
                    return stream->send(obj.as<std::string>());
                }
            }
            throw sol::error("SSEStream.send requires a string");
            return false;
        }
    };

    struct SseClose
    {
        std::shared_ptr<SSEStream> stream;

        void operator()(sol::variadic_args) const
        {
            stream->close();
        }
    };

    struct SseOnClose
    {
        HttpServer* server;
        std::shared_ptr<SSEStream> stream;

        void operator()(sol::variadic_args args) const;
    };

    void assert_can_register_route() const
    {
        if (port_ != 0 || running_) {
            throw std::runtime_error("HTTP server: routes must be registered before listen");
        }
    }

    std::size_t pending_count()
    {
        std::lock_guard<std::mutex> lock(pending_mutex_);
        return pending_.size();
    }

    std::size_t stream_count()
    {
        std::lock_guard<std::mutex> lock(streams_mutex_);
        return active_streams_.size();
    }

    void track_stream(const std::shared_ptr<SSEStream>& stream)
    {
        std::lock_guard<std::mutex> lock(streams_mutex_);
        active_streams_.push_back(stream);
    }

    void close_streams()
    {
        std::vector<std::shared_ptr<SSEStream>> streams;
        {
            std::lock_guard<std::mutex> lock(streams_mutex_);
            std::vector<std::weak_ptr<SSEStream>> live;
            live.reserve(active_streams_.size());
            for (auto& weak : active_streams_) {
                if (auto stream = weak.lock()) {
                    streams.push_back(stream);
                    live.push_back(stream);
                }
            }
            active_streams_.swap(live);
        }
        for (auto& stream : streams) {
            stream->close();
        }
    }

    uint64_t register_sse_close_handler(sol::function handler)
    {
        uint64_t handler_id = next_handler_id_++;
        handlers_.emplace(handler_id, std::move(handler));
        return handler_id;
    }

    void enqueue_sse_close(uint64_t handler_id, const std::shared_ptr<SSEStream>& stream)
    {
        if (!running_) {
            return;
        }

        auto pending = std::make_shared<PendingCall>();
        pending->kind = PendingCall::Kind::SseClose;
        pending->handler_id = handler_id;
        pending->stream = stream;
        {
            std::lock_guard<std::mutex> lock(pending_mutex_);
            if (!running_) {
                return;
            }
            pending_.push_back(pending);
        }
    }

    void wait_for_lua(const std::shared_ptr<PendingCall>& pending)
    {
        {
            std::lock_guard<std::mutex> lock(pending_mutex_);
            if (!running_) {
                pending->response.status = 503;
                pending->response.body = "HTTP server stopped";
                pending->done = true;
            } else {
                pending_.push_back(pending);
            }
        }

        std::unique_lock<std::mutex> lock(pending->mutex);
        pending->cv.wait(lock, [&pending]() { return pending->done; });
    }

    void finish_call(const std::shared_ptr<PendingCall>& pending)
    {
        {
            std::lock_guard<std::mutex> lock(pending->mutex);
            pending->done = true;
        }
        pending->cv.notify_one();
    }

    void fail_pending(const std::string& message)
    {
        std::deque<std::shared_ptr<PendingCall>> calls;
        {
            std::lock_guard<std::mutex> lock(pending_mutex_);
            calls.swap(pending_);
        }
        for (auto& pending : calls) {
            pending->response.status = 503;
            pending->response.body = message;
            if (pending->stream) {
                pending->stream->close();
            }
            finish_call(pending);
        }
    }

    sol::table make_request_table(sol::state_view lua, const PendingCall& pending)
    {
        sol::table req_tbl = lua.create_table();
        req_tbl["method"] = pending.request.method;
        req_tbl["path"] = pending.request.path;
        req_tbl["body"] = pending.request.body;

        sol::table headers_tbl = lua.create_table();
        for (const auto& [key, value] : pending.request.headers) {
            headers_tbl[key] = value;
        }
        req_tbl["headers"] = headers_tbl;

        sol::table query_tbl = lua.create_table();
        for (const auto& [key, value] : pending.request.params) {
            query_tbl[key] = value;
        }
        req_tbl["query_params"] = query_tbl;

        if (pending.stream) {
            auto stream = pending.stream;
            sol::table stream_tbl = lua.create_table();
            stream_tbl["send"] = SseSend{stream};
            stream_tbl["close"] = SseClose{stream};
            stream_tbl["on-close"] = SseOnClose{this, stream};
            req_tbl["stream"] = stream_tbl;
        }

        return req_tbl;
    }

    void dispatch_one(sol::state_view lua, const std::shared_ptr<PendingCall>& pending)
    {
        auto it = handlers_.find(pending->handler_id);
        if (it == handlers_.end()) {
            pending->response.status = 500;
            pending->response.body = "Handler not found";
            if (pending->stream) {
                pending->stream->close();
            }
            finish_call(pending);
            return;
        }

        sol::protected_function pf = it->second;
        sol::protected_function_result result =
            pending->kind == PendingCall::Kind::SseClose ? pf() : pf(make_request_table(lua, *pending));
        if (!result.valid()) {
            sol::error err = result;
            pending->response.status = 500;
            pending->response.body = std::string("Handler error: ") + err.what();
            if (pending->stream) {
                pending->stream->close();
            }
        } else if (pending->kind == PendingCall::Kind::Route) {
            sol::object obj = result;
            apply_response(pending->response, obj);
        } else {
            pending->response.status = 200;
        }
        if (pending->kind == PendingCall::Kind::SseClose) {
            handlers_.erase(pending->handler_id);
        }
        finish_call(pending);
    }

    httplib::Server svr_;
    std::thread server_thread_;
    std::atomic<bool> running_{false};
    int port_ = 0;

    uint64_t next_handler_id_ = 1;
    std::unordered_map<uint64_t, sol::function> handlers_;

    std::mutex pending_mutex_;
    std::deque<std::shared_ptr<PendingCall>> pending_;
    std::mutex streams_mutex_;
    std::vector<std::weak_ptr<SSEStream>> active_streams_;
};

void HttpServer::SseOnClose::operator()(sol::variadic_args args) const
{
    for (auto arg : args) {
        sol::object obj = arg;
        if (obj.is<sol::function>()) {
            uint64_t handler_id = server->register_sse_close_handler(obj.as<sol::function>());
            stream->set_close_handler(
                handler_id,
                [server = server, stream = stream](uint64_t close_handler_id) {
                    server->diagnostic_emit("sse-on-close-callback-begin");
                    server->enqueue_sse_close(close_handler_id, stream);
                    server->diagnostic_emit("sse-on-close-callback-end");
                });
            return;
        }
    }
    throw sol::error("SSEStream.on-close requires a function");
}

} // namespace

void lua_bind_http_server(sol::state& lua)
{
    sol::table preload = lua["package"]["preload"];
    preload.set_function("http_server", [](sol::this_state state) -> sol::table {
        sol::state_view lua(state);

        sol::table module = lua.create_table();

        module.new_usertype<SSEStream>("SSEStream",
            sol::no_constructor,
            "send", &SSEStream::send,
            "close", &SSEStream::close);

        module.new_usertype<HttpServer>("HttpServer",
            sol::no_constructor,
            "listen", &HttpServer::listen,
            "stop", &HttpServer::stop,
            "port", &HttpServer::port,
            "route", &HttpServer::route,
            "route_sse", &HttpServer::route_sse);

        module.set_function("HttpServer", [lua]() {
            return std::make_unique<HttpServer>(lua);
        });

        return module;
    });
}

void lua_http_server_dispatch(sol::state_view lua)
{
    std::vector<HttpServer*> servers;
    {
        std::lock_guard<std::mutex> lock(g_servers_mutex);
        servers = g_servers;
    }
    for (HttpServer* server : servers) {
        if (server) {
            server->dispatch(lua);
        }
    }
}

void lua_http_server_shutdown_all()
{
    std::vector<HttpServer*> servers;
    {
        std::lock_guard<std::mutex> lock(g_servers_mutex);
        servers = g_servers;
    }
    http_lifecycle_diag_global("shutdown-all-copy", servers.size(), servers);
    for (HttpServer* server : servers) {
        if (server) {
            server->lifecycle_emit("shutdown-all-stop-before");
            server->stop();
            server->lifecycle_emit("shutdown-all-stop-after");
        }
    }
}
