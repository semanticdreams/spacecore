#include "http_client.h"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdio>
#include <curl/curl.h>
#include <cstdlib>
#include <functional>
#include <stdexcept>
#include <utility>

namespace {

struct WriteContext {
    std::string* body { nullptr };
    const std::function<void(const char*, std::size_t)>* chunk_callback { nullptr };
};

std::size_t write_body(char* ptr, std::size_t size, std::size_t nmemb, void* userdata)
{
    WriteContext* ctx = static_cast<WriteContext*>(userdata);
    std::size_t total = size * nmemb;
    if (ctx->body) {
        ctx->body->append(ptr, total);
    }
    if (ctx->chunk_callback && *ctx->chunk_callback) {
        (*ctx->chunk_callback)(ptr, total);
    }
    return total;
}

std::size_t write_header(char* buffer, std::size_t size, std::size_t nitems, void* userdata)
{
    std::vector<std::pair<std::string, std::string>>* headers =
        static_cast<std::vector<std::pair<std::string, std::string>>*>(userdata);

    const std::size_t total = size * nitems;
    std::string line(buffer, total);

    auto colon = line.find(':');
    if (colon != std::string::npos) {
        std::string key = line.substr(0, colon);
        std::string value = line.substr(colon + 1);
        // Trim leading spaces and trailing CRLF
        value.erase(value.begin(), std::find_if(value.begin(), value.end(), [](unsigned char c) {
            return !std::isspace(static_cast<unsigned char>(c));
        }));
        while (!value.empty() && (value.back() == '\r' || value.back() == '\n')) {
            value.pop_back();
        }
        headers->emplace_back(std::move(key), std::move(value));
    }
    return total;
}

curl_slist* build_header_list(const std::vector<std::pair<std::string, std::string>>& headers)
{
    curl_slist* list = nullptr;
    for (const auto& kv : headers) {
        std::string line = kv.first + ": " + kv.second;
        list = curl_slist_append(list, line.c_str());
    }
    return list;
}

class CurlGlobalInit {
public:
    CurlGlobalInit()
    {
        curl_global_init(CURL_GLOBAL_DEFAULT);
    }

    ~CurlGlobalInit()
    {
        curl_global_cleanup();
    }
};

CurlGlobalInit curl_global_init_guard;

bool http_client_debug_enabled()
{
    // Enable high-volume request diagnostics with SPACE_HTTP_CLIENT_DEBUG=1.
    static const bool enabled = []() {
        const char* value = std::getenv("SPACE_HTTP_CLIENT_DEBUG");
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

void http_client_diag(const char* event,
                      const void* client,
                      uint64_t id,
                      const char* url,
                      std::size_t active_count,
                      bool always_on,
                      const char* detail = nullptr)
{
    if (!(always_on ? native_lifecycle_diagnostics_enabled() : http_client_debug_enabled())) {
        return;
    }
    std::fprintf(stderr,
                 "space-http-client event=%s client=%p thread=%llu id=%llu active=%zu url=%s%s%s\n",
                 event,
                 client,
                 diagnostic_thread_id(),
                 static_cast<unsigned long long>(id),
                 active_count,
                 url ? url : "-",
                 detail ? " detail=\"" : "",
                 detail ? detail : "");
    std::fflush(stderr);
}

} // namespace

HttpClient::HttpClient(std::size_t thread_count)
{
    if (thread_count == 0) {
        thread_count = std::max<std::size_t>(1, std::thread::hardware_concurrency());
    }

    workers.reserve(thread_count);
    for (std::size_t i = 0; i < thread_count; ++i) {
        workers.emplace_back([this]() { worker_loop(); });
    }
}

HttpClient::~HttpClient()
{
    shutdown();
}

uint64_t HttpClient::submit(const HttpRequest& request)
{
    if (request.url.empty()) {
        throw std::runtime_error("http.request requires a url");
    }

    uint64_t id = next_id.fetch_add(1);
    auto cancel_flag = std::make_shared<std::atomic<bool>>(false);
    {
        std::lock_guard<std::mutex> lock(queue_mutex);
        pending.push(QueuedRequest { id, request, cancel_flag });
        cancel_flags[id] = cancel_flag;
        http_client_diag("submit", this, id, request.url.c_str(), cancel_flags.size(), false);
    }
    queue_cv.notify_one();
    return id;
}

bool HttpClient::cancel(uint64_t id)
{
    std::lock_guard<std::mutex> lock(queue_mutex);
    auto it = cancel_flags.find(id);
    if (it == cancel_flags.end()) {
        http_client_diag("cancel-miss", this, id, nullptr, cancel_flags.size(), false);
        return false;
    }
    it->second->store(true);
    http_client_diag("cancel-hit", this, id, nullptr, cancel_flags.size(), false);
    return true;
}

std::vector<HttpResponse> HttpClient::poll(std::size_t max_results)
{
    std::vector<HttpResponse> out;
    std::lock_guard<std::mutex> lock(completed_mutex);
    if (max_results == 0 || max_results > completed.size()) {
        max_results = completed.size();
    }
    out.reserve(max_results);
    for (std::size_t i = 0; i < max_results; ++i) {
        out.push_back(std::move(completed[i]));
    }
    completed.erase(completed.begin(), completed.begin() + static_cast<long>(max_results));
    return out;
}

void HttpClient::shutdown()
{
    bool expected = false;
    if (!stop.compare_exchange_strong(expected, true)) {
        lifecycle_emit("shutdown-already-stopped");
        return;
    }

    lifecycle_emit("shutdown-begin");
    queue_cv.notify_all();
    for (auto& worker : workers) {
        if (worker.joinable()) {
            worker.join();
        }
    }

    {
        std::lock_guard<std::mutex> lock(queue_mutex);
        std::queue<QueuedRequest> empty;
        pending.swap(empty);
        cancel_flags.clear();
    }
    lifecycle_emit("shutdown-end");
}

bool HttpClient::pop_request(QueuedRequest& out)
{
    std::unique_lock<std::mutex> lock(queue_mutex);
    queue_cv.wait(lock, [this]() { return stop.load() || !pending.empty(); });
    if (stop.load()) {
        return false;
    }
    out = std::move(pending.front());
    pending.pop();
    return true;
}

std::size_t HttpClient::active_count()
{
    std::lock_guard<std::mutex> lock(queue_mutex);
    return cancel_flags.size();
}

void HttpClient::diagnostic_emit(const char* event, uint64_t id, const char* url)
{
    if (!http_client_debug_enabled()) {
        return;
    }
    http_client_diag(event, this, id, url, active_count(), false);
}

void HttpClient::lifecycle_emit(const char* event, uint64_t id, const char* url)
{
    if (!native_lifecycle_diagnostics_enabled()) {
        return;
    }
    http_client_diag(event, this, id, url, active_count(), true);
}

void HttpClient::worker_loop()
{
    diagnostic_emit("worker-start");
    while (!stop.load()) {
        QueuedRequest req;
        if (!pop_request(req)) {
            break;
        }

        if (req.cancel_flag && req.cancel_flag->load()) {
            HttpResponse cancelled = make_cancelled_response(req);
            {
                std::lock_guard<std::mutex> lock(completed_mutex);
                completed.push_back(std::move(cancelled));
            }
            {
                std::lock_guard<std::mutex> lock(queue_mutex);
                cancel_flags.erase(req.id);
            }
            continue;
        }

        HttpResponse resp = perform(req);
        {
            std::lock_guard<std::mutex> lock(completed_mutex);
            completed.push_back(std::move(resp));
        }
        {
            std::lock_guard<std::mutex> lock(queue_mutex);
            cancel_flags.erase(req.id);
        }
    }
    diagnostic_emit("worker-exit");
}

HttpResponse HttpClient::make_cancelled_response(const QueuedRequest& req)
{
    HttpResponse resp;
    resp.id = req.id;
    resp.cancelled = true;
    resp.ok = false;
    resp.status = 0;
    resp.error = "cancelled";
    return resp;
}

HttpResponse HttpClient::perform(const QueuedRequest& req)
{
    HttpResponse out;
    out.id = req.id;
    CURL* curl = curl_easy_init();
    if (!curl) {
        out.error = "curl_easy_init failed";
        return out;
    }
    diagnostic_emit("perform-begin", req.id, req.request.url.c_str());

    std::string body;
    std::vector<std::pair<std::string, std::string>> headers_out;
    WriteContext ctx;
    ctx.body = &body;
    ctx.chunk_callback = &req.request.chunk_callback;

    curl_easy_setopt(curl, CURLOPT_URL, req.request.url.c_str());
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, req.request.follow_redirects ? 1L : 0L);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, req.request.user_agent.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_body);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &ctx);
    curl_easy_setopt(curl, CURLOPT_HEADERFUNCTION, write_header);
    curl_easy_setopt(curl, CURLOPT_HEADERDATA, &headers_out);
    curl_easy_setopt(curl, CURLOPT_ACCEPT_ENCODING, "");

    if (!req.request.body.empty()) {
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, req.request.body.c_str());
        curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, req.request.body.size());
    }

    if (!req.request.method.empty()) {
        curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, req.request.method.c_str());
    }

    curl_slist* header_list = build_header_list(req.request.headers);
    if (header_list) {
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, header_list);
    }

    if (req.request.timeout_ms > 0) {
        curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, req.request.timeout_ms);
    }
    if (req.request.connect_timeout_ms > 0) {
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS, req.request.connect_timeout_ms);
    }

    std::shared_ptr<std::atomic<bool>> cancel_flag = req.cancel_flag;
    curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION,
        +[](void* clientp, curl_off_t, curl_off_t, curl_off_t, curl_off_t) -> int {
            auto* flag = static_cast<std::atomic<bool>*>(clientp);
            return (flag && flag->load()) ? 1 : 0;
        });
    curl_easy_setopt(curl, CURLOPT_XFERINFODATA, cancel_flag.get());
    curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 0L);

    if (req.request.delay_ms > 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(req.request.delay_ms));
    }

    CURLcode code = curl_easy_perform(curl);
    if (cancel_flag && cancel_flag->load()) {
        out = make_cancelled_response(req);
    } else if (code != CURLE_OK) {
        out.ok = false;
        out.error = curl_easy_strerror(code);
    } else {
        long status = 0;
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
        out.ok = (status >= 200 && status < 400);
        out.status = status;
        out.body = std::move(body);
        out.headers = std::move(headers_out);
    }

    if (header_list) {
        curl_slist_free_all(header_list);
    }
    long result_status = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &result_status);
    curl_easy_cleanup(curl);
    diagnostic_emit("perform-end", req.id, req.request.url.c_str());
    char result_detail[192];
    std::snprintf(result_detail, sizeof(result_detail),
                  "curl=%d(%s) status=%ld body=%zu cancelled=%d",
                  static_cast<int>(code),
                  curl_easy_strerror(code),
                  result_status,
                  out.body.size(),
                  out.cancelled ? 1 : 0);
    http_client_diag("perform-result", this, req.id, req.request.url.c_str(), 0, false, result_detail);
    return out;
}
