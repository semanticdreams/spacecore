(local fennel (require :fennel))

(fn safe-tostring [value]
  (local (ok result) (pcall tostring value))
  (if ok result "<tostring failed>"))

(fn safe-view [value]
  (local (ok result) (pcall fennel.view value))
  (if ok result (.. "<unprintable " (type value) ": " (safe-tostring value) ">")))

(fn shallow-table-preview [value]
  (local parts [])
  (var count 0)
  (local max-items 8)
  (each [k v (pairs value)]
    (when (< count max-items)
      (table.insert parts
                    (.. (safe-tostring k)
                        "="
                        (if (= (type v) "table")
                            "<table>"
                            (safe-tostring v)))))
    (set count (+ count 1)))
  (local body (table.concat parts ", "))
  (if (> count max-items)
      (.. "{"
          body
          ", ...}"
          " ("
          (safe-tostring count)
          " keys)")
      (.. "{" body "}")))

(fn format-result [value]
  (if (= value nil)
      "nil"
      (if (= (type value) "string")
          value
          (if (= (type value) "number")
              (safe-tostring value)
              (if (= (type value) "boolean")
                  (safe-tostring value)
                  (if (= (type value) "table")
                      (shallow-table-preview value)
                      (if (= (type value) "function")
                          (.. "<function " (safe-tostring value) ">")
                          (if (= (type value) "userdata")
                              (.. "<userdata " (safe-tostring value) ">")
                              (safe-view value)))))))))

(fn format-error [value]
  (if (= value nil)
      "unknown error"
      (if (= (type value) "string")
          value
          (safe-tostring value))))

(fn eval-source [source opts]
  (local options (or opts {}))
  (assert (= (type options) :table) "eval-source options must be a table")
  (local env (or options.env _G))
  (fn evaluate [] (fennel.eval source {:env env}))
  (fn trace [err] (debug.traceback (format-error err) 2))
  (local (ok result) (if options.traceback? (xpcall evaluate trace) (pcall evaluate)))
  {:ok ok :result result})

{:format-result format-result
 :format-error format-error
 :eval-source eval-source}
