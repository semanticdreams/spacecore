;; HTTP server binding tests.
;; Run: SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH=$(pwd)/assets ./build/space -m tests.test-http-server:main

(local tests [])
(local http-server-mod (require :http_server))
(local http (require :http))
(local callbacks (require :callbacks))
(local sysinfo (require :sysinfo))

(fn poll-http []
  (callbacks.run-loop {:poll-http true :sleep-ms 5 :timeout-ms 50}))

(fn wait-for [_srv pred timeout-ms]
  "Poll until pred returns truthy, or timeout."
  (local deadline (+ (sysinfo.now-ms) (or timeout-ms 5000)))
  (var result nil)
  (while (and (not result) (< (sysinfo.now-ms) deadline))
    (poll-http)
    (local val (pred))
    (set result val))
  (assert result (.. "timeout after " (or timeout-ms 5000) "ms")))

(fn stream-body [chunks]
  (var body "")
  (each [_ chunk (ipairs chunks)]
    (if (= (type chunk) "string")
        (set body (.. body chunk))
        (= (type chunk.chunk) "string")
        (set body (.. body chunk.chunk))))
  body)

;; ── Server lifecycle ──

(fn test-server-create-and-start []
  (local srv (http-server-mod.HttpServer))
  (assert srv "should create server")
  (local port (srv:listen "127.0.0.1" 0))
  (assert (> port 0) "should get a valid port")
  (assert (= (srv:port) port) "port() should return the port")
  (srv:stop))

(table.insert tests {:name "http-server: create and start on random port" :fn test-server-create-and-start})

(fn test-server-fixed-port []
  (local probe (http-server-mod.HttpServer))
  (local port (probe:listen "127.0.0.1" 0))
  (probe:stop)

  (local srv (http-server-mod.HttpServer))
  (local actual-port (srv:listen "127.0.0.1" port))
  (assert (= actual-port port) (.. "fixed port listen should return requested port, got " actual-port))
  (assert (= (srv:port) port) "port() should return requested fixed port")
  (srv:stop))

(table.insert tests {:name "http-server: fixed port listen uses requested port" :fn test-server-fixed-port})

(fn test-server-stop []
  (local srv (http-server-mod.HttpServer))
  (srv:listen "127.0.0.1" 0)
  (srv:stop)
  (srv:stop)
  (assert true "stop should be idempotent"))

(table.insert tests {:name "http-server: stop is idempotent" :fn test-server-stop})

(fn test-listen-twice-fails []
  (local srv (http-server-mod.HttpServer))
  (srv:listen "127.0.0.1" 0)
  (local (ok err) (pcall srv.listen srv "127.0.0.1" 0))
  (assert (not ok) "second listen should fail")
  (assert (string.find (tostring err) "listen called more than once" 1 true)
          (.. "error should mention second listen, got: " (tostring err)))
  (srv:stop))

(table.insert tests {:name "http-server: listen twice fails" :fn test-listen-twice-fails})

(fn test-route-after-listen-fails []
  (local srv (http-server-mod.HttpServer))
  (srv:listen "127.0.0.1" 0)
  (local (ok err) (pcall srv.route srv "GET" "/late" (fn [_] {:status 200})))
  (assert (not ok) "route after listen should fail")
  (assert (string.find (tostring err) "routes must be registered before listen" 1 true)
          (.. "error should mention route order, got: " (tostring err)))
  (srv:stop))

(table.insert tests {:name "http-server: route after listen fails" :fn test-route-after-listen-fails})

;; ── Route handling ──

(fn test-get-route []
  (local srv (http-server-mod.HttpServer))
  (srv:route "GET" "/hello"
    (fn [req]
      {:status 200
       :body (.. "Hello " (or req.query_params.name "world"))
       :headers {:x-test "value"}}))
  (local port (srv:listen "127.0.0.1" 0))

  (var response nil)
  (http.request
    {:method "GET"
     :url (.. "http://127.0.0.1:" port "/hello?name=space")
     :callback (fn [res] (set response res))})

  (wait-for srv #(and response response.ok))
  (assert (= response.status 200))
  (assert (string.find (or response.body "") "Hello space") "should contain greeting")
  (srv:stop))

(table.insert tests {:name "http-server: GET route with query params" :fn test-get-route})

(fn test-post-route-echo []
  (local srv (http-server-mod.HttpServer))
  (srv:route "POST" "/echo"
    (fn [req]
      {:status 200 :body req.body}))
  (local port (srv:listen "127.0.0.1" 0))

  (var response nil)
  (http.request
    {:method "POST"
     :url (.. "http://127.0.0.1:" port "/echo")
     :headers {:Content-Type "text/plain"}
     :body "hello-from-post"
     :callback (fn [res] (set response res))})

  (wait-for srv #response)
  (assert (= response.status 200) (.. "expected 200 got " (tostring response.status)))
  (assert (string.find (or response.body "") "hello-from-post" 1 true) (.. "should echo body, got: " (tostring response.body)))
  (srv:stop))

(table.insert tests {:name "http-server: POST route echo" :fn test-post-route-echo})

(fn test-route-handler-error []
  (local srv (http-server-mod.HttpServer))
  (srv:route "GET" "/crash"
    (fn [_req]
      (error "intentional handler error")))
  (local port (srv:listen "127.0.0.1" 0))

  (var response nil)
  (http.request
    {:method "GET"
     :url (.. "http://127.0.0.1:" port "/crash")
     :callback (fn [res] (set response res))})

  (wait-for srv #response)
  (assert (= response.status 500) "should return 500 on handler error")
  (assert (string.find (or response.body "") "Handler error") "should mention handler error")
  (srv:stop))

(table.insert tests {:name "http-server: handler errors return 500" :fn test-route-handler-error})

(fn test-route-nil-response []
  (local srv (http-server-mod.HttpServer))
  (srv:route "POST" "/no-content"
    (fn [_req] nil))
  (local port (srv:listen "127.0.0.1" 0))

  (var response nil)
  (http.request
    {:method "POST" :headers {:Content-Length "0"}
     :url (.. "http://127.0.0.1:" port "/no-content")
     :callback (fn [res] (set response res))})

  (wait-for srv #(and response response.ok))
  (assert (= (or response.status 0) 204) "nil handler result should return 204")
  (srv:stop))

(table.insert tests {:name "http-server: nil handler returns 204" :fn test-route-nil-response})

(fn test-multiple-routes []
  (local srv (http-server-mod.HttpServer))
  (srv:route "GET" "/a" (fn [_] {:status 200 :body "AAA"}))
  (srv:route "GET" "/b" (fn [_] {:status 200 :body "BBB"}))
  (local port (srv:listen "127.0.0.1" 0))

  (var response-a nil)
  (http.request {:method "GET" :url (.. "http://127.0.0.1:" port "/a")
                 :callback (fn [res] (set response-a res))})
  (wait-for srv #(and response-a response-a.ok))
  (assert (string.find (or response-a.body "") "AAA") "route A")

  (var response-b nil)
  (http.request {:method "GET" :url (.. "http://127.0.0.1:" port "/b")
                 :callback (fn [res] (set response-b res))})
  (wait-for srv #(and response-b response-b.ok))
  (assert (string.find (or response-b.body "") "BBB") "route B")

  (srv:stop))

(table.insert tests {:name "http-server: multiple routes" :fn test-multiple-routes})

(fn test-sse-route []
  (local srv (http-server-mod.HttpServer))
  (srv:route_sse "/events"
    (fn [req]
      (local stream req.stream)
      (assert stream "SSE handler should receive a stream")
      (stream:send "event: test\ndata: {\"count\":1}\n\n")
      (stream:send "event: test\ndata: {\"count\":2}\n\n")
      (stream:close)))

  (local port (srv:listen "127.0.0.1" 0))

  (var chunks [])
  (http.request
    {:method "GET"
     :url (.. "http://127.0.0.1:" port "/events")
     :headers {:Accept "text/event-stream"}
     :stream true
     :callback (fn [result]
                 (if result.chunk
                     (table.insert chunks result.chunk)
                     result.done
                     (table.insert chunks {:done true})
                     result.error
                     (table.insert chunks {:error result.error})))})

  (var done false)
  (for [_ 1 200]
    (when (not done)
      (poll-http)
      (local body (stream-body chunks))
      (when (or (string.find body "\"count\":2" 1 true)
                (and (> (# chunks) 0)
                     (or (. chunks (# chunks) :done) (. chunks (# chunks) :error))))
        (set done true))
      (when (not done)
        (sysinfo.sleep 0.02))))

  (assert done "SSE stream should complete")

  (local body (stream-body chunks))
  (assert (string.find body "\"count\":1" 1 true) (.. "SSE body should contain count 1, got: " (string.sub body 1 200)))
  (srv:stop))

(table.insert tests {:name "http-server: SSE route sends events" :fn test-sse-route})

(fn test-sse-close-callback []
  (local srv (http-server-mod.HttpServer))
  (var closed false)
  (srv:route_sse "/close"
    (fn [req]
      (req.stream:on-close
        (fn []
          (set closed true)))
      (req.stream:send "event: close-test\ndata: {}\n\n")
      (req.stream:close)))

  (local port (srv:listen "127.0.0.1" 0))
  (var chunks [])
  (http.request
    {:method "GET"
     :url (.. "http://127.0.0.1:" port "/close")
     :headers {:Accept "text/event-stream"}
     :stream true
     :callback (fn [result] (table.insert chunks result))})

  (wait-for srv #closed 5000)
  (assert closed "SSE on-close callback should run on Lua dispatch")
  (srv:stop))

(table.insert tests {:name "http-server: SSE close callback runs on Lua thread" :fn test-sse-close-callback})

(fn test-sse-cleanup []
  (local srv (http-server-mod.HttpServer))
  (var stream-ref nil)
  (srv:route_sse "/keepalive"
    (fn [req]
      (set stream-ref req.stream)
      (stream-ref:send "event: alive\ndata: {}\n\n")))

  (local port (srv:listen "127.0.0.1" 0))

  (var chunks [])
  (http.request
    {:method "GET"
     :url (.. "http://127.0.0.1:" port "/keepalive")
     :headers {:Accept "text/event-stream"}
     :stream true
     :callback (fn [result]
                 (table.insert chunks result))})

  (for [_ 1 30]
    (poll-http)
    (sysinfo.sleep 0.02))

  ;; Should have received the alive event
  (local body (stream-body chunks))

  (assert (string.find body "alive") (.. "should receive alive event, got: " (string.sub body 1 200)))

  (srv:stop)
  (for [_ 1 20]
    (poll-http)
    (sysinfo.sleep 0.02))

  (assert true "SSE cleanup completes without error"))

(table.insert tests {:name "http-server: SSE connection closes on server stop" :fn test-sse-cleanup})

;; ── SSE callable finalizers ──
;; Only state owns strong server/stream references. Callbacks capture state, not
;; aliases of its mutable fields, so clearing those fields really permits GC.
(fn sse-log [message]
  (print (.. "[SSE-FINALIZERS] " message))
  (io.flush))

(fn collect-twice []
  (collectgarbage :collect)
  (collectgarbage :collect))

(fn wait-sse [state pred]
  ;; lua_http_dispatch buffers completed responses for http.poll. Its streaming
  ;; callback is unregistered before the queued done item can dispatch, so use
  ;; the request-id-matched completion response rather than depending on done.
  (wait-for nil (fn []
                  (each [_ response (ipairs (http.poll))]
                    (when (= response.id state.request)
                      (set state.done true)
                      (set state.cancelled (= response.error "cancelled"))))
                  (pred)) 5000))

(fn teardown-sse [state]
  (local errors [])
  (fn attempt [label action]
    (local (ok err) (pcall action))
    (when (not ok)
      (table.insert errors (.. label ": " (tostring err)))))
  (attempt "cancel" (fn []
                      (when (and state.request (not state.done))
                        (http.cancel state.request))))
  (attempt "stop" (fn [] (when state.server (state.server:stop))))
  (attempt "completion drain" (fn []
                                (when state.request
                                  (wait-sse state #state.done))))
  ;; Always release roots, even when cancellation/stop/draining raised an error.
  (set state.stream nil)
  (set state.server nil)
  (set state.request nil)
  (attempt "collection" collect-twice)
  (assert (= (# errors) 0) (table.concat errors "\n")))

(fn add-sse-finalizer-case [name body]
  (local state {:weak (setmetatable {} {:__mode "v"})
                :body "" :done false :close-count 0})
  (table.insert tests {:name (.. "http-server: SSE finalizers " name)
                       :timeout-seconds 25
                       :fn #(body state)
                       :teardown #(teardown-sse state)}))

(fn assert-sse-error [action expected]
  (local (ok err) (pcall action))
  (assert (not ok) (.. "expected error: " expected))
  (assert (string.find (tostring err) expected 1 true)
          (.. "expected " expected ", got: " (tostring err))))

(fn configure-sse [state colon?]
  (assert-sse-error (fn [] (if colon? (state.stream:send {} true)
                                    (state.stream.send {} true)))
                    "SSEStream.send requires a string")
  (assert-sse-error (fn [] (if colon? (state.stream:on-close {} false)
                                    (state.stream.on-close {} false)))
                    "SSEStream.on-close requires a function")
  ;; This temporary strong reference ends before any collection phase. Once
  ;; registered, only native ownership and a weak diagnostic witness remain.
  (local handler (fn [] (set state.close-count (+ state.close-count 1))))
  (set state.weak.handler handler)
  (local registered-values
    (if colon?
        (select "#" (state.stream:on-close {} true handler))
        (select "#" (state.stream.on-close {} false handler))))
  (assert (= registered-values 0) "on-close must return no values")
  (local first "event: finalizer\ndata: finalizer-one\n\n")
  (local second "event: finalizer\ndata: finalizer-two\n\n")
  (assert (= (if colon? (state.stream:send {} true first)
                       (state.stream.send {} false first)) true)
          "first send must succeed after scanning table/boolean arguments")
  (assert (= (if colon? (state.stream:send {} false second)
                       (state.stream.send {} true second)) true)
          "second send must succeed")
  (wait-sse state #(and (string.find state.body "finalizer-one" 1 true)
                       (string.find state.body "finalizer-two" 1 true)))
  (assert (= state.close-count 0) "open stream must not notify close")
  (assert (not state.done) "stream must still be active after delivery")
  (sse-log "two payloads delivered; stream active; close-count=0"))

(fn start-sse [state colon?]
  (set state.server (http-server-mod.HttpServer))
  (set state.weak.server state.server)
  (state.server:route_sse "/finalizers"
    (fn [req]
      (set state.stream req.stream)
      (set state.weak.stream req.stream)
      (set state.weak.send req.stream.send)
      (set state.weak.close req.stream.close)
      (set state.weak.on-close req.stream.on-close)))
  (local port (state.server:listen "127.0.0.1" 0))
  (assert (> port 0) "fixture must bind an ephemeral loopback port")
  (set state.request
       (http.request {:method "GET"
                      :url (.. "http://127.0.0.1:" port "/finalizers")
                      :headers {:Accept "text/event-stream"}
                      :stream true
                      :callback (fn [result]
                                  (when result.chunk
                                    (set state.body (.. state.body result.chunk)))
                                  (when result.done (set state.done true)))}))
  (wait-sse state #state.stream)
  (configure-sse state colon?))

;; This helper's userdata/metatable/finalizer locals die on return. Its result
;; contains primitives only, never a diagnostic root to a callable's userdata.
(fn sse-identity-snapshot [stream]
  (local identities [])
  (each [_ key (ipairs [:send :close :on-close])]
    (local (upvalue-name userdata) (debug.getupvalue (. stream key) 2))
    (assert (= (type userdata) "userdata")
            (.. key " upvalue 2 must be actual callable userdata"))
    (local mt (debug.getmetatable userdata))
    (assert (= (type mt) "table") "callable userdata must have a metatable")
    (assert (= (type mt.__gc) "function") "callable metatable must have __gc")
    (local names [])
    (each [name value (pairs (debug.getregistry))]
      (when (and (= (type name) "string") (rawequal value mt))
        (table.insert names name)))
    (table.sort names)
    (assert (> (# names) 0) "callable metatable must have a registry name")
    (table.insert identities {:key key :mt mt :gc mt.__gc})
    (sse-log (.. key " upvalue2-name=" upvalue-name
                 " type=" (type userdata) " registry=" (table.concat names " | "))))
  (local comparisons [])
  (for [i 1 2]
    (for [j (+ i 1) 3]
      (local a (. identities i))
      (local b (. identities j))
      (local comparison {:pair (.. a.key "/" b.key)
                         :same-metatable (rawequal a.mt b.mt)
                         :same-gc (rawequal a.gc b.gc)})
      (table.insert comparisons comparison)
      (sse-log (.. comparison.pair " same-metatable=" (tostring comparison.same-metatable)
                   " same-__gc=" (tostring comparison.same-gc)))))
  comparisons)

(fn test-sse-identities [state]
  (start-sse state false)
  (local comparisons (sse-identity-snapshot state.stream))
  (each [_ comparison (ipairs comparisons)]
    (assert (not comparison.same-metatable)
            (.. "SSE callable finalizer identities must be distinct: " comparison.pair))))

(fn close-sse-twice [state colon?]
  (for [_ 1 2]
    (assert (= (if colon? (select "#" (state.stream:close {} true))
                         (select "#" (state.stream.close {} false))) 0)
            "close must return no values"))
  (assert (= (if colon? (state.stream:send {} true "after-close")
                       (state.stream.send {} false "after-close")) false)
          "send after close must return false"))

(fn await-sse-close [state]
  (wait-sse state #(and state.done (= state.close-count 1)))
  (poll-http)
  (assert (= state.close-count 1) "close must dispatch exactly once")
  (sse-log "client completion observed; close-count=1"))

(fn collect-sse-before-stop [state closed?]
  (set state.stream nil)
  (sse-log "collecting stream and callables before server stop")
  (collect-twice)
  (each [_ key (ipairs [:stream :send :close :on-close])]
    (assert (= (. state.weak key) nil) (.. key " must be collected before server stop")))
  (when closed?
    (assert (= state.weak.handler nil) "dispatched Lua close handler must be released"))
  (assert (rawequal state.weak.server state.server) "server must remain rooted through stream GC")
  (assert state.server "server root must be live")
  (sse-log (.. "weak stream/send/close/on-close cleared; server rooted; close-count=" state.close-count))
  (state.server:stop)
  (sse-log "server stop returned")
  (wait-sse state #state.done)
  (set state.request nil)
  (set state.server nil)
  (collect-twice)
  (assert (= state.weak.server nil) "server must collect after releasing its root")
  (assert (= state.weak.handler nil) "Lua close handler must release with server")
  (sse-log "weak server/handler cleared after stop and collection"))

(fn test-sse-explicit-close [state colon?]
  (start-sse state colon?)
  (close-sse-twice state colon?)
  (assert (= state.close-count 0) "close notification must wait for Lua polling")
  (await-sse-close state)
  (close-sse-twice state colon?)
  (poll-http)
  (assert (= state.close-count 1) "repeated close must not dispatch again")
  (collect-sse-before-stop state true))

(fn test-sse-client-disconnect [state]
  (start-sse state false)
  (assert (= (http.cancel state.request) true) "active SSE cancellation must succeed")
  (sse-log "active client cancellation succeeded")
  (await-sse-close state)
  (assert state.cancelled "client completion must report cancellation")
  (close-sse-twice state false)
  (poll-http)
  (assert (= state.close-count 1) "close after disconnect must not notify again")
  (collect-sse-before-stop state true))

(fn test-sse-open-collection [state]
  (start-sse state true)
  ;; Intentionally neither cancel nor close: collect before stopping a live SSE
  ;; connection. stop suppresses enqueue, so no stop-time Lua notice is required.
  (collect-sse-before-stop state false))

(add-sse-finalizer-case "distinct callable identities" test-sse-identities)
(add-sse-finalizer-case "dot explicit-close" #(test-sse-explicit-close $ false))
(add-sse-finalizer-case "colon explicit-close" #(test-sse-explicit-close $ true))
(add-sse-finalizer-case "client-disconnect" test-sse-client-disconnect)
(add-sse-finalizer-case "open-stream collection before stop" test-sse-open-collection)

(fn main []
  (local runner (require :tests/runner))
  (runner.run-tests {:name "http-server" :tests tests}))

{:tests tests
 :main main}
