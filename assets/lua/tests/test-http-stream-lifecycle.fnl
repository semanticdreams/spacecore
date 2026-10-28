(local http (require :http))
(local callbacks (require :callbacks))
(local sysinfo (require :sysinfo))
(local Server (require :http_server))
(local tests [])

(fn await-terminal [events poll!]
  (local deadline (+ (sysinfo.now-ms) 5000))
  (var terminal nil)
  (while (and (not terminal) (< (sysinfo.now-ms) deadline))
    (poll!)
    (each [_ event (ipairs events)]
      (when event.done (set terminal event))))
  (assert terminal "native stream terminal callback was lost")
  terminal)

(fn collect-event [events]
  (fn [event] (table.insert events event)))

(fn connection-failure [poll!]
  (local events [])
  (http.request {:url "http://127.0.0.1:1/" :stream true
                 :connect-timeout-ms 100 :timeout-ms 1000
                 :callback (collect-event events)})
  (local terminal (await-terminal events poll!))
  (assert terminal.error "stream completion must preserve transport errors")
  (assert (not terminal.ok))
  (assert (= (length events) 1) "terminal delivery must occur exactly once"))

(fn poll-http [] (http.poll 0))
(fn dispatch-http []
  (callbacks.run-loop {:poll-http true :sleep-ms 1 :timeout-ms 10}))

(fn failure-through-poll [] (connection-failure poll-http))
(fn failure-through-dispatch [] (connection-failure dispatch-http))

(fn finite-stream []
  (local server (Server.HttpServer))
  (server:route "GET" "/finite" (fn [_request] {:status 200 :body "data: hello\n\n"}))
  (local port (server:listen "127.0.0.1" 0))
  (local events [])
  (http.request {:url (.. "http://127.0.0.1:" port "/finite") :stream true
                 :timeout-ms 2000 :callback (collect-event events)})
  (local (ok err)
    (pcall
      (fn []
        (local terminal (await-terminal events dispatch-http))
        (assert terminal.ok)
        (assert (= terminal.status 200))
        (assert (= (. events (length events)) terminal) "terminal follows every queued chunk")
        (local chunks [])
        (each [_ event (ipairs events)]
          (when event.chunk (table.insert chunks event.chunk)))
        (assert (= (table.concat chunks) "data: hello\n\n")))))
  (server:stop)
  (assert ok err))

(table.insert tests {:name "native HTTP stream errors reach poll consumers" :fn failure-through-poll})
(table.insert tests {:name "native HTTP stream errors reach dispatch consumers" :fn failure-through-dispatch})
(table.insert tests {:name "native HTTP stream chunks precede terminal delivery" :fn finite-stream})
(fn main [] ((. (require :tests/runner) :run-tests) {:name "http-stream-lifecycle" :tests tests}))
{:name "http-stream-lifecycle" :tests tests :main main}
