#include <sol/sol.hpp>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "http_client.h"
#include "lua_callbacks.h"

namespace {

bool lua_http_debug_enabled()
{
    // Share the SPACE_HTTP_CLIENT_DEBUG gate with http_client.cpp so the
    // Lua-side dispatch boundary is visible in the same per-request trace.
    static const bool enabled = []() {
        const char* value = std::getenv("SPACE_HTTP_CLIENT_DEBUG");
        return value && value[0] != '\0' && value[0] != '0';
    }();
    return enabled;
}

void lua_http_diag(const char* event, uint64_t id, const char* detail)
{
    if (!lua_http_debug_enabled()) {
        return;
    }
    std::fprintf(stderr,
                 "space-http-lua event=%s id=%llu detail=\"%s\"\n",
                 event,
                 static_cast<unsigned long long>(id),
                 detail ? detail : "-");
    std::fflush(stderr);
}

struct LuaHttp
{
    HttpClient* client { nullptr };
    std::unordered_map<uint64_t, uint64_t> callback_ids;
    std::unordered_map<uint64_t, uint64_t> stream_callback_ids;
    std::vector<HttpResponse> buffered;

    void cleanup_stream_callback(uint64_t request_id)
    {
        auto it = stream_callback_ids.find(request_id);
        if (it != stream_callback_ids.end()) {
            lua_callbacks_unregister(it->second);
            stream_callback_ids.erase(it);
        }
    }

    uint64_t request(sol::table opts)
    {
        HttpRequest req;
        req.method = opts.get_or<std::string>("method", "GET");
        req.url = opts.get_or<std::string>("url", "");
        req.body = opts.get_or<std::string>("body", "");
        req.timeout_ms = opts.get_or<long>("timeout-ms", 0);
        req.connect_timeout_ms = opts.get_or<long>("connect-timeout-ms", 0);
        req.delay_ms = opts.get_or<long>("delay-ms", 0);
        sol::optional<bool> follow_redirects = opts.get<sol::optional<bool>>("follow-redirects");
        req.follow_redirects = follow_redirects.value_or(true);
        req.user_agent = opts.get_or<std::string>("user-agent", "space-http/1.0");
        sol::object cb_obj = opts.get<sol::object>("callback");
        sol::optional<sol::function> cb_func;
        if (cb_obj.is<sol::function>()) {
            cb_func = cb_obj.as<sol::function>();
        } else {
            cb_func = opts.get<sol::optional<sol::function>>("cb");
        }

        sol::optional<sol::table> headers = opts.get<sol::optional<sol::table>>("headers");
        if (headers) {
            for (auto& kv : *headers) {
                sol::object key = kv.first;
                sol::object value = kv.second;
                if (key.is<std::string>() && value.is<std::string>()) {
                    req.headers.emplace_back(key.as<std::string>(), value.as<std::string>());
                }
            }
        }

        sol::optional<bool> stream_opt = opts.get<sol::optional<bool>>("stream");
        bool stream = stream_opt.value_or(false);

        if (req.url.empty()) {
            throw sol::error("http.request requires a url");
        }

        if (stream) {
            if (!cb_func) {
                throw sol::error("http.request with stream=true requires a callback");
            }
            uint64_t stream_cb_id = lua_callbacks_register(cb_func.value());
            req.chunk_callback = [stream_cb_id](const char* data, std::size_t len) {
                lua_callbacks_enqueue(stream_cb_id,
                    [chunk = std::string(data, len)](sol::state_view l) {
                        sol::table item = l.create_table();
                        item["chunk"] = chunk;
                        return sol::make_object(l, item);
                    });
            };
            uint64_t id = client->submit(req);
            stream_callback_ids[id] = stream_cb_id;
            return id;
        }

        uint64_t id = client->submit(req);
        if (cb_func) {
            uint64_t cb_id = lua_callbacks_register(cb_func.value());
            callback_ids[id] = cb_id;
        }
        return id;
    }

    bool cancel(uint64_t id)
    {
        return client->cancel(id);
    }

    sol::table poll(sol::state_view lua, sol::optional<uint64_t> max_results)
    {
        std::vector<HttpResponse> responses;
        // consume buffered first
        std::size_t max = max_results.value_or(0);
        if (!buffered.empty()) {
            if (max == 0 || max >= buffered.size()) {
                responses.swap(buffered);
            } else {
                responses.insert(responses.end(),
                                 std::make_move_iterator(buffered.begin()),
                                 std::make_move_iterator(buffered.begin() + static_cast<std::ptrdiff_t>(max)));
                buffered.erase(buffered.begin(), buffered.begin() + static_cast<std::ptrdiff_t>(max));
                max = 0;
            }
        }

        std::vector<HttpResponse> polled = client->poll(max);
        for (auto& r : polled) {
            auto stream_it = stream_callback_ids.find(r.id);
            if (stream_it != stream_callback_ids.end()) {
                lua_callbacks_enqueue(stream_it->second, [](sol::state_view l) {
                    sol::table item = l.create_table();
                    item["done"] = true;
                    return sol::make_object(l, item);
                });
            }
            cleanup_stream_callback(r.id);
            auto it = callback_ids.find(r.id);
            if (it != callback_ids.end()) {
                uint64_t cb_id = it->second;
                lua_callbacks_enqueue(cb_id, [resp = std::move(r)](sol::state_view l) {
                    sol::table item = make_response_table(l, resp);
                    return sol::make_object(l, item);
                });
                callback_ids.erase(it);
            } else {
                responses.push_back(std::move(r));
            }
        }
        sol::table out = lua.create_table();
        std::size_t idx = 1;
        for (auto& res : responses) {
            out[idx++] = make_response_table(lua, res);
        }
        lua_callbacks_dispatch(lua);
        return out;
    }

    static sol::table make_response_table(sol::state_view lua, const HttpResponse& res)
    {
        sol::table item = lua.create_table();
        item["id"] = res.id;
        item["ok"] = res.ok;
        item["status"] = res.status;
        if (res.cancelled) {
            item["error"] = "cancelled";
        } else {
            item["error"] = res.error.empty() ? sol::lua_nil : sol::make_object(lua, res.error);
        }
        item["body"] = res.body;
        sol::table headers_tbl = lua.create_table();
        std::size_t hidx = 1;
        for (auto& h : res.headers) {
            sol::table pair = lua.create_table();
            pair[1] = h.first;
            pair[2] = h.second;
            headers_tbl[hidx++] = pair;
        }
        item["headers"] = headers_tbl;
        return item;
    }

    void dispatch(sol::state_view lua)
    {
        std::vector<HttpResponse> responses = client->poll(0);
        for (auto& res : responses) {
            auto stream_it = stream_callback_ids.find(res.id);
            if (stream_it != stream_callback_ids.end()) {
                lua_callbacks_enqueue(stream_it->second, [](sol::state_view l) {
                    sol::table item = l.create_table();
                    item["done"] = true;
                    return sol::make_object(l, item);
                });
            }
            cleanup_stream_callback(res.id);
            char detail[192];
            std::snprintf(detail, sizeof(detail),
                          "callback=%s status=%ld body=%zu error=%s",
                          callback_ids.count(res.id) ? "found" : "MISSING-buffered",
                          res.status,
                          res.body.size(),
                          res.error.empty() ? "-" : res.error.c_str());
            lua_http_diag("dispatch-response", res.id, detail);
            auto it = callback_ids.find(res.id);
            if (it != callback_ids.end()) {
                uint64_t cb_id = it->second;
                lua_callbacks_enqueue(cb_id, [resp = std::move(res)](sol::state_view l) {
                    sol::table item = make_response_table(l, resp);
                    return sol::make_object(l, item);
                });
                callback_ids.erase(it);
            } else {
                buffered.push_back(std::move(res));
            }
        }
        lua_callbacks_dispatch(lua);
    }
};

LuaHttp* get_lua_http(sol::state& lua)
{
    sol::object obj = lua["http-handle"];
    if (obj.is<LuaHttp*>()) {
        return obj.as<LuaHttp*>();
    }
    return nullptr;
}

} // namespace

namespace {

sol::table create_http_table(sol::state_view lua, LuaHttp* state)
{
    sol::table http = lua.create_table();
    http.set_function("request", [state](sol::table opts) {
        return state->request(opts);
    });
    http.set_function("cancel", [state](uint64_t id) {
        return state->cancel(id);
    });
    http.set_function("poll", [state, lua](sol::optional<uint64_t> max_results) {
        return state->poll(lua, max_results);
    });
    return http;
}

} // namespace

void lua_bind_http(sol::state& lua, HttpClient& client)
{
    auto* state = new LuaHttp();
    state->client = &client;
    lua["http-handle"] = state;
    sol::table package = lua["package"];
    sol::table preload = package["preload"];

    preload.set_function("http", [state](sol::this_state st) {
        sol::state_view lua(st);
        return create_http_table(lua, state);
    });
}

void lua_http_drop(sol::state& lua)
{
    LuaHttp* state = get_lua_http(lua);
    if (state != nullptr) {
        for (auto& kv : state->stream_callback_ids) {
            lua_callbacks_unregister(kv.second);
        }
        state->stream_callback_ids.clear();
        for (auto& kv : state->callback_ids) {
            lua_callbacks_unregister(kv.second);
        }
        state->callback_ids.clear();
        sol::table package = lua["package"];
        sol::table loaded = package["loaded"];
        loaded["http"] = sol::lua_nil;
        sol::table preload = package["preload"];
        preload["http"] = sol::lua_nil;
        lua["http-handle"] = sol::lua_nil;
        delete state;
    }
}

void lua_http_dispatch(sol::state& lua)
{
    LuaHttp* state = get_lua_http(lua);
    if (state == nullptr) {
        return;
    }
    sol::state_view sv(lua);
    state->dispatch(sv);
}
