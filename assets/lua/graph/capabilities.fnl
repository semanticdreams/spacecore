(local Shapes (require :graph/capability-shapes))
(local KeyLoaderUtils (require :graph/key-loader-utils))

(fn text [minimum maximum]
  {:type "string" :min-bytes minimum :max-bytes maximum})

(fn record [fields optional]
  {:type "record" :fields fields :optional (or optional [])})

(local ref-shape (record {:key (text 1 1024)}))
(local entry-shape (record {:ref ref-shape :summary (text 0 4096)}))
(local preconditions-shape (record {:revision (text 1 512)} ["revision"]))
(local codes ["invalid-arguments" "limit-exceeded" "not-found" "not-exposed"
              "unsupported-capability" "unavailable" "conflict" "storage-failed"
              "corrupt-data" "notification-failed" "invalid-result" "internal-error"])
(local error-shape
  (record {:code {:type "enum" :values codes} :message (text 1 4096)
           :outcome {:type "enum" :values ["not-committed" "committed" "unknown"]}
           :current-revision (text 1 512)} ["current-revision"]))

(fn failure [code message outcome]
  {:ok false :error {:code code :message message :outcome (or outcome "not-committed")}})

(fn invalid! [message]
  (error {:code "invalid-arguments" :message message} 0))

(fn closed! [value fields]
  (assert (and (= (type value) "table") (= (getmetatable value) nil))
          {:code "invalid-arguments" :message "Expected a plain record"})
  (each [name _ (pairs value)]
    (when (not (. fields name)) (invalid! "Unknown record field"))))

(fn prepare-access [scheme access]
  (closed! access {:entry-points true :describe true :handlers true})
  (assert (= (type access.describe) "function") "Access requires describe function")
  (assert (and (= (type access.handlers) "table") (= (getmetatable access.handlers) nil))
          "Access requires plain handler mapping")
  (local entries (Shapes.check! {:type "array" :items entry-shape :max-items 8} access.entry-points))
  (local seen {})
  (each [_ entry (ipairs entries)]
    (assert (= (KeyLoaderUtils.key-scheme entry.ref.key) scheme) "Entry point scheme mismatch")
    (assert (not (. seen entry.ref.key)) "Duplicate entry point")
    (set (. seen entry.ref.key) true))
  (local handlers {})
  (each [id handler (pairs access.handlers)]
    (Shapes.check! (text 1 256) id)
    (assert (= (type handler) "function") "Capability handler must be a function")
    (set (. handlers id) handler))
  {:entry-points entries :describe access.describe :handlers handlers})

(fn checked-input [f ...]
  (local (ok value) (pcall f ...))
  (if ok (values value nil)
      (values nil (failure (if (and (= (type value) "table") (= value.code "limit-exceeded"))
                              "limit-exceeded" "invalid-arguments")
                          "Invalid or over-budget request"))))

(fn validate-metadata! [metadata access]
  (closed! metadata {:id true :description true :arguments true :result true :effect true :revision true})
  (Shapes.check! (text 1 256) metadata.id)
  (Shapes.check! (text 0 4096) metadata.description)
  (Shapes.check! {:type "enum" :values ["read" "write"]} metadata.effect)
  (Shapes.check! {:type "enum" :values ["none" "required"]} metadata.revision)
  (Shapes.validate-shape! metadata.arguments)
  (Shapes.validate-shape! metadata.result)
  (when (not (. access.handlers metadata.id)) (invalid! "Advertised capability has no handler")))

(fn validate-description! [description ref access]
  (local detached (Shapes.detach! description))
  (closed! detached {:ref true :summary true :capabilities true})
  (Shapes.check! ref-shape detached.ref)
  (when (not (= detached.ref.key ref.key)) (invalid! "Description reference mismatch"))
  (Shapes.check! (text 0 4096) detached.summary)
  ;; Detachment already checks dense arrays. Reject string keys here as this is
  ;; specifically an array, not a data record.
  (assert (= (type detached.capabilities) "table") "Capabilities must be an array")
  (closed! detached.capabilities (collect [i _ (ipairs detached.capabilities)] (values i true)))
  (local seen {})
  (each [_ metadata (ipairs detached.capabilities)]
    (validate-metadata! metadata access)
    (when (. seen metadata.id) (invalid! "Duplicate capability identifier"))
    (set (. seen metadata.id) true))
  detached)

(fn validate-result! [result value-check]
  (closed! result {:ok true :value true :error true})
  (if (= result.ok true)
      (do
        (when (not (= result.error nil)) (invalid! "Success contains error"))
        {:ok true :value (value-check result.value)})
      (= result.ok false)
      (do
        (when (not (= result.value nil)) (invalid! "Failure contains value"))
        (closed! result.error {:code true :message true :outcome true :current-revision true :result true})
        (local error-data {:code result.error.code :message result.error.message
                          :outcome result.error.outcome :current-revision result.error.current-revision})
        (local checked (Shapes.check! error-shape error-data))
        (when (not (= result.error.result nil))
          (set checked.result (value-check result.error.result)))
        {:ok false :error checked})
      (invalid! "Result requires boolean ok")))

(fn resolve [registrations ref]
  (local (checked err) (checked-input Shapes.check! ref-shape ref))
  (if err (values nil nil err)
      (do
        (local registration (. registrations (KeyLoaderUtils.key-scheme checked.key)))
        (if (not registration) (values nil nil (failure "unavailable" "No current registration"))
            (not registration.access) (values nil nil (failure "not-exposed" "Registration has no nonvisual access"))
            (values checked registration nil)))))

(fn describe-current [registration ref]
  (local access registration.access)
  (local (ok result) (pcall access.describe (Shapes.detach! ref)))
  (when (not ok) (lua "return failure('internal-error', 'Description handler failed')"))
  (fn check-description [value] (validate-description! value ref access))
  (local (valid checked) (pcall validate-result! result check-description))
  (if valid checked (failure "invalid-result" "Invalid description result")))

(fn describe [registrations ref]
  (local (checked registration err) (resolve registrations ref))
  (if err err (describe-current registration checked)))

(fn invoke [registrations ref id args preconditions]
  (local (checked registration err) (resolve registrations ref))
  (when err (lua "return err"))
  (local (_id id-error) (checked-input Shapes.check! (text 1 256) id))
  (when id-error (lua "return id_error"))
  (local description (describe-current registration checked))
  (when (not description.ok) (lua "return description"))
  (var metadata nil)
  (each [_ candidate (ipairs description.value.capabilities)]
    (when (= candidate.id id) (set metadata candidate)))
  (when (not metadata) (lua "return failure('unsupported-capability', 'Capability is not advertised')"))
  (local (arguments arguments-error) (checked-input Shapes.check! metadata.arguments args))
  (when arguments-error (lua "return arguments_error"))
  (local (pre pre-error) (checked-input Shapes.check! preconditions-shape (if (= preconditions nil) {} preconditions)))
  (when pre-error (lua "return pre_error"))
  (when (not (= (= metadata.revision "required") (not (= pre.revision nil))))
    (lua "return failure('invalid-arguments', 'Revision precondition does not match capability')"))
  (local write (= metadata.effect "write"))
  (local (ok result) (pcall (. registration.access.handlers id) checked arguments pre))
  (when (not ok)
    (lua "return failure('internal-error', 'Capability handler failed', write and 'unknown' or 'not-committed')"))
  (fn check-output [value] (Shapes.check! metadata.result value))
  (local (valid output) (pcall validate-result! result check-output))
  (local invalid-outcome
    (if (not write) "not-committed"
        (and (= (type result) "table") (= (getmetatable result) nil) (= (rawget result "ok") true)) "committed"
        "unknown"))
  (if valid output
      (failure "invalid-result" "Invalid capability result" invalid-outcome)))

(fn discovery-args! [args]
  (closed! args {:limit true :cursor true})
  (local limit (if (= args.limit nil) 20 args.limit))
  (Shapes.check! {:type "integer" :min 1 :max 9007199254740991} limit)
  (when (> limit 50) (error {:code "limit-exceeded"} 0))
  (var after "")
  (when (not (= args.cursor nil))
    (when (and (= (type args.cursor) "string") (> (length args.cursor) 2048))
      (error {:code "limit-exceeded"} 0))
    (Shapes.check! (text 1 2048) args.cursor)
    (when (not (= (string.sub args.cursor 1 3) "v1:")) (invalid! "Unknown discovery cursor"))
    (set after (string.sub args.cursor 4))
    (Shapes.check! (text 1 1024) after))
  {:limit limit :after after})

(fn discover [registrations args]
  (local (options err) (checked-input discovery-args! (if (= args nil) {} args)))
  (when err (lua "return err"))
  (local entries [])
  (each [_ registration (pairs registrations)]
    (when registration.access
      (each [_ entry (ipairs registration.access.entry-points)]
        (when (> entry.ref.key options.after) (table.insert entries entry)))))
  (table.sort entries (fn by-key [a b] (< a.ref.key b.ref.key)))
  (local items [])
  (for [i 1 (math.min options.limit (length entries))] (table.insert items (. entries i)))
  (local more (> (length entries) options.limit))
  (local page {:items items :has-more more})
  (when more (set page.cursor (.. "v1:" (. items (length items) :ref :key))))
  (local (valid detached) (pcall Shapes.detach! page))
  (if valid {:ok true :value detached} (failure "limit-exceeded" "Discovery page exceeds data budget")))

{:prepare-access prepare-access :discover discover :describe describe :invoke invoke}
