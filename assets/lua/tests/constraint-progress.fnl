;; Bounded, test-only consumer of the constraints pipeline's scalar events.
;; No environment, clock selection, hook, workload wrapper or retained history.
(local phase-subphases {:discover [:scan :read :parse]
                       :facts [:extract :recover :span]
                       :select [] :rule [] :baseline [] :summarize []})
(local subphase-owners {:scan :discover :read :discover :parse :discover
                        :extract :facts :recover :facts :span :facts})
(local registered-rules {})
(each [_ rule (ipairs ((. (require :constraints.rules.init) :all-rules)))]
  (tset registered-rules rule.id true))
(local prefix "[CONSTRAINT-PROGRESS] ")

(fn finite-number? [value]
  (and (= (type value) :number) (= value value) (< (math.abs value) math.huge)))

(fn count-value [value]
  (when (and (finite-number? value) (>= value 0) (= value (math.floor value))) value))

(fn number-text [value] (string.format "%.6g" value))

(fn safe-file? [value]
  (and (= (type value) :string) (> (# value) 0)
       (not (value:find "^/")) (not (value:find "[\\:%c]"))
       (not (value:find "//" 1 true)) (not (value:find "/$"))
       (not= value ".") (not= value "..")
       (not (value:find "^%./")) (not (value:find "^%.%./"))
       (not (value:find "/%./")) (not (value:find "/%.%./"))
       (not (value:find "/%.$")) (not (value:find "/%.%.$"))))

(fn encoded-label [text limit]
  (local parts ["\""])
  (local marker "[truncated]")
  (var bytes 0)
  (var index 1)
  (while (<= index (# text))
    (local byte (string.byte text index))
    (local piece (if (= byte 34) "\\\""
                     (= byte 92) "\\\\"
                     (and (>= byte 32) (<= byte 126)) (string.char byte)
                     (string.format "\\x%02x" byte)))
    (if (> (+ bytes (# piece)) (- limit (# marker)))
        (do (table.insert parts marker) (set index (+ (# text) 1)))
        (do (table.insert parts piece)
            (set bytes (+ bytes (# piece)))
            (set index (+ index 1)))))
  (table.insert parts "\"")
  (table.concat parts))

(fn append-count [parts key value]
  (local count (count-value value))
  (when count (table.insert parts (.. key "=" (number-text count)))))

(fn event-line [event at elapsed subphase]
  (local phase (rawget event :phase))
  (local parts [(.. prefix "at_ms=" (number-text at))
                (.. "edge=" (rawget event :edge)) (.. "phase=" phase)])
  (when subphase (table.insert parts (.. "subphase=" subphase)))
  (when elapsed (table.insert parts (.. "elapsed_ms=" (number-text elapsed))))
  (each [_ key (ipairs [:count :definitions :calls :index])]
    (local value (rawget event key))
    (when (if (not= key :index) true (and (count-value value) (> value 0)))
      (append-count parts key value)))
  (local rule-id (rawget event :rule-id))
  (when (and (= phase :rule) (= (type rule-id) :string) (. registered-rules rule-id))
    (table.insert parts (.. "rule=" (encoded-label rule-id 72))))
  (local file (rawget event :file))
  (when (and subphase (safe-file? file))
    (table.insert parts (.. "file=" (encoded-label file 128))))
  (table.concat parts " "))

(fn aggregate-line [phase subphase slot]
  (.. prefix "aggregate phase=" phase " subphase=" subphase
      " begins=" (number-text slot.begins) " ends=" (number-text slot.ends)
      " elapsed_ms=" (number-text slot.elapsed)
      " definitions=" (number-text slot.definitions) " calls=" (number-text slot.calls)))

(fn new-slot [] {:begins 0 :ends 0 :elapsed 0 :definitions 0 :calls 0})

(fn update-slot [slot event now]
  (local index (count-value (rawget event :index)))
  (var elapsed nil)
  (if (= (rawget event :edge) :begin)
      (do (set slot.begins (+ slot.begins 1))
          (set slot.started now)
          (set slot.index index))
      (do (set slot.ends (+ slot.ends 1))
          (when (and slot.started (= slot.index index))
            (set elapsed (- now slot.started))
            (set slot.elapsed (+ slot.elapsed elapsed)))
          (set slot.started nil)
          (each [_ key (ipairs [:definitions :calls])]
            (local value (count-value (rawget event key)))
            (when value (tset slot key (+ (. slot key) value))))))
  elapsed)

(fn create [opts]
  (assert (= (type opts) :table) "constraint progress options are required")
  (assert (= (type opts.now-ms) :function) "constraint progress requires now-ms")
  (assert (= (type opts.write) :function) "constraint progress requires write")
  (local detail-phase opts.detail-phase)
  (assert (or (= detail-phase nil) (and (= (type detail-phase) :string) (. phase-subphases detail-phase)))
          "constraint progress detail-phase must be a pipeline phase or nil")
  (local now-ms opts.now-ms)
  (local write opts.write)
  (local origin (now-ms))
  (assert (finite-number? origin) "constraint progress clock must return finite milliseconds")
  (var last-time origin)
  (var lines 0)
  (var bytes 0)
  (var capped false)
  (local max-line (if detail-phase 512 256))
  (local max-bytes (if detail-phase (* 2 1024 1024) (* 256 256)))
  ;; Text-mode stdout may expand LF to CRLF. Reserve both bytes on every host.
  (local ending-bytes 2)
  (local cap-line (.. prefix "cap reached mode=" (if detail-phase "detail" "phase")))
  ;; Fixed phase/subphase slots, never keyed by files, indices or incoming labels.
  (local phases {})
  (local subphases {})
  (each [phase subs (pairs phase-subphases)]
    (tset phases phase (new-slot))
    (each [_ subphase (ipairs subs)] (tset subphases subphase (new-slot))))
  (fn emit [line]
    (when (not capped)
      (assert (<= (+ (# line) ending-bytes) max-line) "constraint progress encoded line exceeds budget")
      (if (or (and (not detail-phase) (>= lines 255))
              (> (+ bytes (# line) ending-bytes (# cap-line) ending-bytes) max-bytes))
          (do (set capped true) (write cap-line))
          (do (set lines (+ lines 1))
              (set bytes (+ bytes (# line) ending-bytes))
              (write line)))))
  (fn timestamp []
    (local raw (now-ms))
    (assert (finite-number? raw) "constraint progress clock must return finite milliseconds")
    (set last-time (math.max last-time raw))
    (- last-time origin))
  (fn observe-phase [event phase now]
    (local subs (. phase-subphases phase))
    (when (= (rawget event :edge) :begin)
      (each [_ subphase (ipairs subs)] (tset subphases subphase (new-slot))))
    (local elapsed (update-slot (. phases phase) event now))
    (emit (event-line event now elapsed nil))
    (when (= (rawget event :edge) :end)
      (each [_ subphase (ipairs subs)]
        (local slot (. subphases subphase))
        (when (> (+ slot.begins slot.ends) 0)
          (emit (aggregate-line phase subphase slot))))))
  (fn observer [event]
    (when (and (not capped) (= (type event) :table))
      (local phase (rawget event :phase))
      (local edge (rawget event :edge))
      (local subphase (rawget event :subphase))
      (local valid-phase (and (= (type phase) :string) (. phase-subphases phase)))
      (local valid-subphase (and (= (type subphase) :string) (= (. subphase-owners subphase) phase)))
      (when (and valid-phase (if (= edge :begin) true (= edge :end))
                 (if (= subphase nil) true valid-subphase))
        (local now (timestamp))
        (if subphase
            (do (local elapsed (update-slot (. subphases subphase) event now))
                (when (= phase detail-phase) (emit (event-line event now elapsed subphase))))
            (observe-phase event phase now))))
    nil)
  observer)

{: create}
