(fn SseConnect [http url opts callback]
  (assert http "sse requires http binding")
  (assert url "sse requires a url")
  (assert callback "sse requires a callback")

  (local options (or opts {}))

  (var line-buffer "")
  (var pending-cr false)
  (var done false)
  (var request-id nil)

  (fn normalize-eol [s]
    (-> s
        (string.gsub "\r\n" "\n")
        (string.gsub "\r" "\n")))

  (fn parse-event [raw]
    (local event {})
    (var data-lines [])
    (each [line (string.gmatch raw "[^\n]+")]
      (when (not (= (string.sub line 1 1) ":"))
        (local colon-pos (string.find line ":"))
        (when colon-pos
          (local field (string.sub line 1 (- colon-pos 1)))
          (local value (string.sub line (+ colon-pos 1)))
          (local trimmed-value (if (= (string.sub value 1 1) " ")
                                   (string.sub value 2)
                                   value))
          (if (= field "event")
              (tset event :event trimmed-value)
              (= field "data")
              (table.insert data-lines trimmed-value)
              (= field "id")
              (tset event :id trimmed-value)))))
    (tset event :data (table.concat data-lines "\n"))
    event)

  (fn process-chunks [chunk]
    (when (not done)
      ;; A trailing \r may be half of a \r\n pair split across chunks:
      ;; holding it back and re-joining it with the next chunk keeps
      ;; chunk-local normalization from inventing a blank-line boundary.
      (local effective (if pending-cr (.. "\r" chunk) chunk))
      (set pending-cr (and (> (# chunk) 0) (= (string.sub chunk -1) "\r")))
      (local body (if pending-cr
                     (string.sub effective 1 (- (# effective) 1))
                     effective))
      (set line-buffer (.. line-buffer (normalize-eol body)))
      (var boundary (string.find line-buffer "\n\n" 1 true))
      (while (and boundary (not done))
        (local raw (string.sub line-buffer 1 (- boundary 1)))
        (set line-buffer (string.sub line-buffer (+ boundary 1)))
        (when (> (# raw) 0)
          (local parsed (parse-event raw))
          (when (> (length parsed.data) 0)
            (callback parsed)))
        (set boundary (string.find line-buffer "\n\n" 1 true)))))

  (fn complete! []
    (set done true)
    (when options.notify-done
      (callback {:event :stream-done})))

  (fn on-result [result]
    (when (and result (not done))
      (local failure
        (if result.error result.error
            (and result.done (= result.ok false))
            (.. "HTTP stream failed: " (tostring result.status))
            nil))
      (if failure
          (do
            (set done true)
            (callback {:event "error" :data failure}))
          result.done (complete!)
          result.chunk (process-chunks result.chunk)
          (process-chunks ""))))

  (set request-id
       (http.request
         {:method "GET"
          :url url
          :headers (or options.headers {})
          :user-agent (or options.user-agent "space-opencode/1.0")
          :stream true
          :timeout-ms (or options.timeout-ms 0)
           :connect-timeout-ms (or options.connect-timeout-ms 0)
            :callback on-result}))


  (local handle {})
  (set handle.close (fn []
                      (set done true)
                      (when request-id
                        (http.cancel request-id))
                      (set request-id nil)))
  (set handle.request-id (fn [] request-id))
  (set handle.done? (fn [] done))
  handle)

SseConnect
