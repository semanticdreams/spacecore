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

(local interactive-rule "layout.interactive-context-assertion")
(local rule-prefix (.. prefix "phase=rule subphase=interactive "))
(local rule-byte-limit (* 2 1024 1024))

(fn rule-number [value]
  (assert (and (finite-number? value) (>= value 0))
          "interactive progress requires finite nonnegative numbers (no overflow)")
  value)

(fn rule-count [value]
  (rule-number value)
  (assert (and (= value (math.floor value)) (<= value 9007199254740991))
          "interactive progress requires exact nonnegative integer counts")
  value)

(fn rule-index [value]
  (rule-count value)
  (assert (> value 0) "interactive progress requires positive indices")
  value)

(fn rule-text [value] (number-text (rule-number value)))

(fn rule-state [origin]
  {: origin :last origin :N nil :limit nil :started nil :done false :lines 0 :bytes 0
   :files-begun 0 :files-ended 0 :definitions 0 :masks 0 :analyses 0 :mask-ms 0
   :file 0 :def 0 :stage :none :since 0 :file-start 0 :D 0 :known false
   :file-masks 0 :file-analyses 0 :file-mask-ms 0})

(fn rule-timestamp [s now-ms]
  (local now (now-ms))
  (assert (finite-number? now) "constraint progress clock must return finite milliseconds")
  (set s.last (math.max s.last now))
  (rule-number (- s.last s.origin)))

(fn rule-stage! [s stage now]
  (set s.stage stage)
  (set s.since now))

(fn rule-definitions! [s value]
  (local D (rule-count value))
  (if s.known (assert (= s.D D) "interactive progress merged definition count changed")
      (do (set s.definitions (rule-count (+ s.definitions D)))
          (set s.D D) (set s.known true))))

(fn rule-clear-file! [s]
  (set s.file 0)
  (set s.def 0)
  (set s.D 0)
  (set s.known false)
  (set s.stage :none))

(fn rule-summary [s now outcome]
  (local elapsed (rule-number (- now s.started)))
  (local pending (if (= s.stage :none) 0 (rule-number (- now s.since))))
  (local mask (rule-number (+ s.mask-ms (if (= s.stage :mask) pending 0))))
  (.. prefix "aggregate phase=rule subphase=interactive outcome=" outcome
      " files_begun=" (rule-text s.files-begun) " files_ended=" (rule-text s.files-ended)
      " definitions=" (rule-text s.definitions) " masks=" (rule-text s.masks)
      " analyses=" (rule-text s.analyses) " elapsed_ms=" (rule-text elapsed)
      " mask_ms=" (rule-text mask) " remaining_ms=" (rule-text (- elapsed mask))
      " pending_file=" (rule-text s.file) " pending_def=" (rule-text s.def)
      " pending_stage=" s.stage " pending_definitions=" (rule-text s.D)
      " definitions_known=" (if s.known "1" "0") " pending_ms=" (rule-text pending)))

(fn rule-file-boundary! [s event now]
  (local index (rule-index (rawget event :index)))
  (if (= (rawget event :edge) :begin)
      (do
        (assert (= s.file 0) "interactive progress file BEGIN overlaps pending file")
        (set s.files-begun (rule-count (+ s.files-begun 1)))
        (assert (= index s.files-begun) "interactive progress file indices must retain order")
        (set s.file index) (set s.file-start now)
        (set s.file-masks 0) (set s.file-analyses 0) (set s.file-mask-ms 0)
        (rule-stage! s :setup now)
        (.. rule-prefix "edge=begin file_index=" (rule-text index)
            " at_ms=" (rule-text now) " stage=setup"))
      (do
        (assert (and (= index s.file) (= s.def 0)
                     (or (= s.stage :setup) (= s.stage :between))
                     (= s.file-masks s.file-analyses))
                "interactive progress file END has incomplete boundaries")
        (rule-definitions! s (rawget event :definitions))
        (set s.files-ended (rule-count (+ s.files-ended 1)))
        (local elapsed (rule-number (- now s.file-start)))
        (local line (.. rule-prefix "edge=end file_index=" (rule-text index)
                        " definitions=" (rule-text s.D) " masks=" (rule-text s.file-masks)
                        " analyses=" (rule-text s.file-analyses) " elapsed_ms=" (rule-text elapsed)
                        " mask_ms=" (rule-text s.file-mask-ms)
                        " remaining_ms=" (rule-text (- elapsed s.file-mask-ms))))
        (rule-clear-file! s)
        line)))

(fn rule-mask-boundary! [s event now ordinal]
  (if (= (rawget event :edge) :begin)
      (do
        (assert (and (= s.def 0) (= s.file-masks s.file-analyses)
                     (or (= s.stage :setup) (= s.stage :between))
                     (= ordinal (+ s.file-masks 1)))
                "interactive progress mask BEGIN is out of order")
        (rule-definitions! s (rawget event :definitions))
        (set s.def ordinal)
        (rule-stage! s :mask now))
      (do
        (assert (and (= s.stage :mask) (= ordinal s.def))
                "interactive progress mask END has no matching BEGIN")
        (local elapsed (rule-number (- now s.since)))
        (set s.mask-ms (rule-number (+ s.mask-ms elapsed)))
        (set s.file-mask-ms (rule-number (+ s.file-mask-ms elapsed)))
        (set s.masks (rule-count (+ s.masks 1)))
        (set s.file-masks (rule-count (+ s.file-masks 1)))
        (rule-stage! s :between now))))

(fn rule-analysis-boundary! [s event now ordinal]
  (if (= (rawget event :edge) :begin)
      (do
        (assert (and (= s.stage :between) (= ordinal s.def)
                     (= s.file-masks (+ s.file-analyses 1)))
                "interactive progress analysis BEGIN is out of order")
        (rule-stage! s :analysis now))
      (do
        (assert (and (= s.stage :analysis) (= ordinal s.def))
                "interactive progress analysis END has no matching BEGIN")
        (set s.analyses (rule-count (+ s.analyses 1)))
        (set s.file-analyses (rule-count (+ s.file-analyses 1)))
        (set s.def 0)
        (rule-stage! s :between now))))

(fn rule-boundary! [s event subphase now]
  (if (= subphase :interactive-file) (rule-file-boundary! s event now)
      (do
        (assert (= (rule-index (rawget event :index)) s.file)
                "interactive progress definition has no matching file")
        (local ordinal (rule-index (rawget event :definition-index)))
        (if (= subphase :interactive-mask) (rule-mask-boundary! s event now ordinal)
            (rule-analysis-boundary! s event now ordinal))
        nil)))

(fn make-rule-progress [now-ms write]
  (local origin (now-ms))
  (assert (finite-number? origin) "constraint progress clock must return finite milliseconds")
  (local s (rule-state origin))
  (fn terminal! [now outcome]
    (set s.done true)
    (local line (rule-summary s now outcome))
    (assert (and s.limit (< s.lines s.limit) (<= (+ (# line) 2) 512)
                 (<= (+ s.bytes (# line) 2) rule-byte-limit))
            "interactive progress terminal record exceeds reserved budget")
    (write line))
  (fn emit! [line now]
    (assert (<= (+ (# line) 2) 512) "interactive progress line exceeds budget")
    ;; Reserve the largest terminal record including its CRLF before any write.
    (if (or (>= (+ s.lines 1) s.limit) (> (+ s.bytes (# line) 2 512) rule-byte-limit))
        (terminal! now :cap)
        (do (set s.lines (+ s.lines 1)) (set s.bytes (+ s.bytes (# line) 2)) (write line))))
  (fn observer [event]
    (when (and (not s.done) (= (type event) :table))
      (local phase (rawget event :phase))
      (local edge (rawget event :edge))
      (local subphase (rawget event :subphase))
      (if (and (= phase :facts) (= edge :end) (= subphase nil))
          (do (local N (rule-count (rawget event :count)))
              (assert (= s.started nil) "interactive progress Facts END follows rule BEGIN")
              (set s.N N) (set s.limit (rule-count (+ (* 2 N) 1))))
          (and (= phase :rule) (= (rawget event :rule-id) interactive-rule)
               (or (= edge :begin) (= edge :end))
               (or (= subphase nil) (= subphase :interactive-file)
                   (= subphase :interactive-mask) (= subphase :interactive-analysis)))
          (do
            (assert s.N "interactive progress requires actual Facts END count")
            (local now (rule-timestamp s now-ms))
            (if (= subphase nil)
                (if (= edge :begin)
                    (do (assert (= s.started nil) "interactive progress rule BEGIN repeated")
                        (set s.started now))
                    (do (assert s.started "interactive progress rule END without BEGIN")
                        (terminal! now (if (and (= s.file 0) (= s.files-ended s.N))
                                           :complete :unfinished))))
                (do (assert s.started "interactive progress boundary before rule BEGIN")
                    (local line (rule-boundary! s event subphase now))
                    (when line (emit! line now)))))))
    nil)
  observer)

(fn make-phase-progress [now-ms write detail-phase]
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

(fn create [opts]
  (assert (= (type opts) :table) "constraint progress options are required")
  (assert (= (type opts.now-ms) :function) "constraint progress requires now-ms")
  (assert (= (type opts.write) :function) "constraint progress requires write")
  (local detail-phase opts.detail-phase)
  (assert (or (= detail-phase nil) (and (= (type detail-phase) :string) (. phase-subphases detail-phase)))
          "constraint progress detail-phase must be a pipeline phase or nil")
  (if (= detail-phase :rule) (make-rule-progress opts.now-ms opts.write)
      (make-phase-progress opts.now-ms opts.write detail-phase)))

{: create}
