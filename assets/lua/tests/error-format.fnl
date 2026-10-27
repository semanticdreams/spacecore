;; Diagnostic metadata allowlist, not a PII redactor. In particular, :message
;; is producer-supplied text. Never traverse :result or stringify user objects.
(local fields [[:code 128] [:message 1536] [:outcome 96] [:current-revision 192]])
(local truncated "[truncated]")

(fn type-only [value] (.. "<" (type value) ">"))

(fn scalar-text [value]
  (local kind (type value))
  (if (= kind :string) value
      (= kind :boolean) (if value "true" "false")
      (= kind :number) (string.format (if (= (math.type value) :integer) "%d" "%.17g") value)
      (type-only value)))

(fn escaped-byte [byte]
  (if (= byte 10) "\\n"
      (= byte 13) "\\r"
      (= byte 9) "\\t"
      (= byte 34) "\\\""
      (= byte 92) "\\\\"
      (and (>= byte 32) (<= byte 126)) (string.char byte)
      (string.format "\\x%02x" byte)))

(fn encode [text limit]
  ;; Lua string length is O(1). Inspect only as many bytes as can fit in the
  ;; encoded budget (+ one byte to discover overflow), never scan a huge input.
  (local size (# text))
  (local parts [])
  (var used 0)
  (var index 1)
  (var full? false)
  (while (and (<= index size) (not full?))
    (local piece (escaped-byte (string.byte text index)))
    (if (> (+ used (# piece)) limit)
        (set full? true)
        (do
          (table.insert parts piece)
          (set used (+ used (# piece)))
          (set index (+ index 1)))))
  (when full?
    (while (> (+ used (# truncated)) limit)
      (set used (- used (# (table.remove parts)))))
    (table.insert parts truncated))
  (table.concat parts))

(fn describe [err]
  (if (= (type err) :table)
      (do
        (local parts [])
        (each [_ field (ipairs fields)]
          (local key (. field 1))
          (local value (rawget err key))
          (when (not= value nil)
            (table.insert parts (.. key "=\"" (encode (scalar-text value) (. field 2)) "\""))))
        ;; The four encoded field caps plus fixed labels/quotes/spaces total
        ;; 2001 bytes at most, independently of field order or input size.
        (if (> (# parts) 0) (table.concat parts " ") (type-only err)))
      (encode (scalar-text err) 2048)))

(fn format-error [err]
  (local (ok text) (pcall describe err))
  ;; A formatter failure must not become a different reported exception.
  (if ok text (type-only err)))

{: format-error}
