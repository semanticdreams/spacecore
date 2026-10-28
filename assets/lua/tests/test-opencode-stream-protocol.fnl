(local Sse (require :llm/providers/opencode/sse))
(local Events (require :llm/providers/opencode/events))
(local tests [])

(fn fixture []
  (local state {:options nil :cancelled 0 :events [] :health []})
  (fn request [options] (set state.options options) 1)
  (fn cancel [_id] (set state.cancelled (+ state.cancelled 1)))
  (local binding {:request request :cancel cancel})
  (local client {:base-url (fn [] "http://fixture") :http-binding (fn [] binding)})
  (local events (Events client))
  (local handle
    (events.subscribe-with-health
      (fn [event] (table.insert state.events event))
      (fn [health] (table.insert state.health health))))
  {:state state :handle handle})

(fn dataless-blocks []
  (local f (fixture))
  (f.state.options.callback {:chunk ": keepalive\n\nid: 12\n\nevent: ping\n\ndata:\n\n"})
  (assert (= (length f.state.events) 0))
  (assert (= (length f.state.health) 0) "keepalives cannot exhaust reconnect budgets")
  (f.handle:unsubscribe))

(fn terminal-errors []
  (local f (fixture))
  (f.state.options.callback {:done true :ok false :error "connection reset"})
  (f.state.options.callback {:done true})
  (f.state.options.callback {:chunk "data: {}\n\n"})
  (assert (= (length f.state.events) 0))
  (assert (= (length f.state.health) 1) "terminal notification is idempotent")
  (assert (= (. f.state.health 1 :kind) :stream-error))
  (assert (= (. f.state.health 1 :raw) "connection reset"))
  (f.handle:unsubscribe))

(fn close-during-chunk []
  (var callback nil)
  (var handle nil)
  (var received 0)
  (local http {:request (fn [options] (set callback options.callback) 1)
               :cancel (fn [_id] nil)})
  (set handle (Sse http "http://fixture" {}
                   (fn [_event] (set received (+ received 1)) (handle.close))))
  (callback {:chunk "data: 1\n\ndata: 2\n\n"})
  (assert (= received 1) "closing within a callback stops the rest of the same chunk"))

(table.insert tests {:name "SSE keepalives do not dispatch JSON" :fn dataless-blocks})
(table.insert tests {:name "SSE transport failure is health, exactly once" :fn terminal-errors})
(table.insert tests {:name "SSE close stops buffered dispatch" :fn close-during-chunk})
(fn main [] ((. (require :tests/runner) :run-tests) {:name "opencode-stream-protocol" :tests tests}))
{:name "opencode-stream-protocol" :tests tests :main main}
