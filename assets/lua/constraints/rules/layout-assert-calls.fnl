;; Private invocation-local selection only. Coverage and dynamic scanning stay
;; in layout.fnl. Canonical Facts are immutable for the duration of a rule run.

(fn plain-table? [value]
  ;; A protected __metatable=false is still a metatable, not an absent one.
  (and (= (type value) :table) (= (getmetatable value) nil)))

(fn string-or-absent? [value]
  (if (= (type value) :nil) true
      (= (type value) :string) true
      (rawequal value false)))

(fn scalar? [value]
  (local kind (type value))
  (if (= kind :string) true
      (= kind :boolean) true
      (and (= kind :number) (= value value) (< value math.huge) (> value (- math.huge)))))

(fn scalar-record? [record]
  (if (not (plain-table? record))
      false
      (do
        (var safe true)
        (each [key value (values next record)]
          (when (if (not= (type key) :string) true (not (scalar? value)))
            (set safe false)))
        (and safe
             (string-or-absent? (rawget record :name))
             (string-or-absent? (rawget record :enclosing-fn))
             (string-or-absent? (rawget record :callee))
             (string-or-absent? (rawget record :form))))))

(fn array-count [array]
  ;; Metadata pass only: no record fields, #, ipairs or metamethods. Counting
  ;; positive integral keys with max=count proves density without sorting.
  (when (plain-table? array)
    (var count 0)
    (var maximum 0)
    (var safe true)
    (each [key _ (values next array)]
      (if (and (= (type key) :number) (> key 0) (< key math.huge) (= (% key 1) 0))
          (do (set count (+ count 1)) (set maximum (math.max maximum key)))
          (set safe false)))
    (when (and safe (= count maximum)) count)))

(fn namespace-safe? [ff]
  (when (plain-table? ff)
    (var safe true)
    ;; FileFact also owns AST/target/metrics/access arrays. Do not inspect those
    ;; payloads; only its namespace and definition/call graph matter here.
    (each [key _ (values next ff)]
      (when (not= (type key) :string) (set safe false)))
    (and safe (string-or-absent? (rawget ff :module))
         (string-or-absent? (rawget ff :path)))))

(fn definitions-safe? [ff definitions]
  (local original (rawget ff :definitions))
  (local recovered (rawget ff :recovered-parents))
  (local original-count (array-count original))
  (local recovered-count (if (= (type recovered) :nil) 0 (array-count recovered)))
  (local count (array-count definitions))
  (when (and original-count recovered-count count (= count (+ original-count recovered-count)))
    (var safe true)
    ;; Validate every merged definition, not only the first/current query. The
    ;; raw identity check also covers the original and recovered containers.
    (for [index 1 count]
      (local def (rawget definitions index))
      (local source (if (<= index original-count)
                         (rawget original index)
                         (rawget recovered (- index original-count))))
      (when (if (not (rawequal def source)) true (not (scalar-record? def)))
        (set safe false)))
    safe))

(fn classify [ff definitions calls]
  (when (and (namespace-safe? ff) (definitions-safe? ff definitions)
             (rawequal (rawget ff :calls) calls))
    (local count (array-count calls))
    (when count
      (local groups {})
      (var safe true)
      ;; One ordered entry pass combines record eligibility and tentative
      ;; grouping. A failed guard discards the entire tentative index.
      (for [index 1 count]
        (local call (rawget calls index))
        (if (not (scalar-record? call))
            (set safe false)
            (when (= (rawget call :callee) "assert")
              (local enclosure (rawget call :enclosing-fn))
              (local name (if enclosure enclosure ""))
              (when (not (rawget groups name)) (tset groups name []))
              (table.insert (rawget groups name) call))))
      (when safe groups))))

(fn create [opts]
  ;; Capture references only: no classification/eligibility or fact reads until
  ;; the old named branch demands lookup. Nothing is shared across invocations.
  (local ff opts.file-fact)
  (local definitions opts.definitions)
  (local calls opts.calls)
  (var ready false)
  (var groups nil)
  (local empty [])
  (fn lookup [def]
    (when (not ready)
      (set groups (classify ff definitions calls))
      (set ready true))
    (if (and groups (plain-table? def) (string-or-absent? (rawget def :name)))
        (do
          (local name (rawget def :name))
          (local key (if name name ""))
          (local group (rawget groups key))
          (if group group empty))
        calls))
  lookup)

{: create}
