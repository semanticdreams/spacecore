;; IO observations and path-selective checked-read faults for the native Notebook
;; presentation fixture. Resource/signal ownership stays in test-notebooks.
(local fs (require :fs))
(local json (require :json))
(local J (require :json-utils))
(local RecordFiles (require :entities/record-files))
(local H (require :tests/test-reference-lifecycle-helpers))

(fn observed-methods [f store methods]
  (local out {})
  (each [_ method (ipairs methods)]
    (local original (assert (. store method) "owning observation requires method"))
    (fn operation [self ...]
      (table.insert f.calls {:store store.base-dir :method method
                            :args (json.loads (J.stable-json [...]))})
      (if (= method :replace-text)
          (do
            (local result (original self ...))
            (assert (= (type result) :table) "replace-text must return its owning snapshot")
            (set f.replacement-result (json.loads (J.stable-json result)))
            result)
          (original self ...)))
    (tset out method operation))
  out)

(fn with-observations [f body]
  (local write fs.write-file)
  (local publish fs.publish-record)
  (fn count-write! [path]
    (when (= (string.sub path 1 (# f.root)) f.root)
      (set f.writes (+ f.writes 1))))
  (fn write-file [path bytes]
    (count-write! path)
    (write path bytes))
  (fn publish-record [path payload options]
    ;; Native publication never calls the Lua fs.write-file binding: count its
    ;; logical owning write once, alongside other owners' legacy pathname writes.
    (count-write! path)
    (publish path payload options))
  (fn run [] (body f))
  (fn content []
    (H.with-fields f.content (observed-methods f f.content [:replace-text]) run))
  (fn notebook []
    (H.with-fields f.store
      (observed-methods f f.store [:update-notebook :add-item :remove-item :move-item]) content))
  (H.with-fields fs {:write-file write-file :publish-record publish-record} notebook))

(fn with-denied-read [store path action]
  (local target (fs.absolute path))
  (local files (assert store.files "required read fixture needs owning RecordFiles"))
  (local previous-read files.read!)
  (local hits [])
  (fn open-record [candidate mode]
    (if (= (fs.absolute candidate) target)
        (do
          (table.insert hits {:path candidate :mode mode})
          (values nil (.. "injected permission denied: RecordFiles read " target)))
        (io.open candidate mode)))
  ;; Replace the owning read method, not io.open after its closure was captured.
  ;; The actual RecordFiles checked-open/error path still executes for each read.
  (local denied (RecordFiles.RecordFiles {:open open-record}))
  (local (ok result) (pcall H.with-fields files {:read! denied.read!} action))
  (assert (= files.read! previous-read) "owning read fault must always restore")
  (when (not ok) (error result 0))
  (assert (> (# hits) 0) "required target read fault must actually fire")
  (each [_ hit (ipairs hits)]
    (assert (= hit.path target) "fault must hit the requested concrete record path")
    (assert (= hit.mode "rb") "fault must exercise the owning checked binary read"))
  result)

{:with-observations with-observations :with-denied-read with-denied-read}
