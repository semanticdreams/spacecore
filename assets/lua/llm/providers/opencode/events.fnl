(local json (require :json))
(local Sse (require :llm/providers/opencode/sse))
(local logging (require :logging))

(fn make-sse-callback [on-event on-health]
  ;; The health variant surfaces parse failures and stream completion as
  ;; explicit health events so subscribe-then-snapshot consumers can
  ;; resynchronize instead of silently missing data. Scalar JSON payloads
  ;; cannot carry annotations, so they are wrapped, never mutated.
  (fn [event]
    (if (= event.event :stream-done)
        (when on-health
          (on-health {:kind :stream-done}))
        (when (and event event.data)
           (if (= event.event "error")
               (if on-health
                   (on-health {:kind :stream-error :raw event.data})
                   (on-event {:error event.data :_event_type "error"}))
              (do
                (local (ok parsed) (pcall json.loads event.data))
                (if (not ok)
                    (do
                      (logging.warn "[opencode] failed to parse SSE event data: " event.data)
                      (when on-health
                        (on-health {:kind :parse-error :raw event.data})))
                    (do
                      (if (= (type parsed) :table)
                          (do
                            (tset parsed :_event_type
                                  (if event.event event.event "message"))
                            (when event.id
                              (tset parsed :_sse_id event.id))
                            (on-event parsed))
                          (on-event {:data parsed
                                     :_event_type
                                     (if event.event event.event "message")
                                     :_sse_id (if event.id event.id nil)}))))))))))

(fn build-handle [sse-handle]
  (local handle {})
  (set handle.unsubscribe (fn [] (sse-handle.close)))
  (set handle.closed? (fn [] (sse-handle.done?)))
  handle)

(fn connect! [client path on-event on-health notify-done?]
  (build-handle
    (Sse (client.http-binding)
         (.. (client.base-url) path)
         {:user-agent "space-opencode/1.0"
          :timeout-ms 0
          :connect-timeout-ms 5000
          :notify-done notify-done?}
         (make-sse-callback on-event on-health))))

(fn Events [client]
  (assert client "Events requires an opencode client")
  (assert (= (type client.base-url) "function") "client.base-url must be a function")

  (fn subscribe [on-event]
    (assert on-event "events.subscribe requires on_event callback")
    (connect! client "/event" on-event nil false))

  (fn subscribe-with-health [on-event on-health]
    ;; Subscribe-then-snapshot consumers use this: parse failures and stream
    ;; completion become explicit health events.
    (assert on-event "events.subscribe-with-health requires on_event callback")
    (assert on-health "events.subscribe-with-health requires on_health callback")
    (connect! client "/event" on-event on-health true))

  (fn subscribe-global [on-event]
    (assert on-event "events.subscribe-global requires on_event callback")
    (connect! client "/global/event" on-event nil false))

  {:subscribe subscribe
   :subscribe-with-health subscribe-with-health
   :subscribe-global subscribe-global})

Events
