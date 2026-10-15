;; A deliberately small, checked data vocabulary; no domain or visual imports.
(fn invalid! [message]
  (error {:code "invalid-arguments" :message message} 0))

(fn limit! [message]
  (error {:code "limit-exceeded" :message message} 0))

(fn plain-table! [value]
  (assert (and (= (type value) "table") (= (getmetatable value) nil))
          {:code "invalid-arguments" :message "Expected a plain table"}))

(fn integer? [value]
  (and (= (type value) "number") (= value value)
       (<= -9007199254740991 value 9007199254740991) (= value (math.floor value))))

(fn string! [value]
  (assert (and (= (type value) "string") (utf8.len value))
          {:code "invalid-arguments" :message "Expected a UTF-8 string"}))

(fn array-length! [value remaining-values]
  (plain-table! value)
  (local allowance (if (= remaining-values nil) 4095 remaining-values))
  (var count 0)
  (var maximum 0)
  (each [key _ (pairs value)]
    (when (>= count allowance) (limit! "Data value budget exceeded"))
    (assert (and (integer? key) (>= key 1))
            {:code "invalid-arguments" :message "Expected a dense array"})
    (set maximum (math.max maximum key))
    (set count (+ count 1)))
  (when (not (= count maximum)) (invalid! "Sparse arrays are not data"))
  count)

(fn charge-string! [budget value]
  (assert (= (type value) "string") {:code "invalid-arguments" :message "Expected a string"})
  (local bytes (+ budget.bytes (length value)))
  (when (> bytes 131072) (limit! "Aggregate string byte budget exceeded"))
  (string! value)
  (set budget.bytes bytes))

(fn detach-value! [value budget ancestors depth]
  (when (> depth 16) (limit! "Data depth exceeds 16"))
  (set budget.values (+ budget.values 1))
  (when (> budget.values 4096) (limit! "Data value budget exceeded"))
  (local kind (type value))
  (if (= kind "string") (do (charge-string! budget value) value)
      (= kind "boolean") value
      (= kind "number")
      (do
        (assert (and (= value value) (not (= (math.abs value) math.huge)))
                {:code "invalid-arguments" :message "Nonfinite numbers are not data"})
        value)
      (= kind "table")
      (do
        (plain-table! value)
        (when (. ancestors value) (invalid! "Cyclic data"))
        (set (. ancestors value) true)
        (local out {})
        (local array? (= (type (next value)) "number"))
        (when array? (array-length! value (- 4096 budget.values)))
        (each [key child (pairs value)]
          (when (not array?) (charge-string! budget key))
          (set (. out key) (detach-value! child budget ancestors (+ depth 1))))
        (set (. ancestors value) nil)
        out)
      (invalid! "Expected data, not nil, executable values or userdata")))

(fn detach! [value]
  (detach-value! value {:values 0 :bytes 0} {} 1))

(fn attributes! [value allowed]
  (plain-table! value)
  (each [key _ (pairs value)]
    (when (not (. allowed key)) (invalid! "Unknown shape attribute"))))

(fn bounds! [minimum maximum nonnegative?]
  (assert (and (integer? minimum) (integer? maximum) (<= minimum maximum)
               (if nonnegative? (>= minimum 0) true))
          {:code "invalid-arguments" :message "Expected ordered finite integer bounds"}))

(var validate-declaration! nil)

(fn validate-record! [shape]
  (attributes! shape {:type true :fields true :optional true})
  (plain-table! shape.fields)
  (each [name child (pairs shape.fields)]
    (string! name)
    (validate-declaration! child))
  (array-length! shape.optional)
  (local seen {})
  (each [_ name (ipairs shape.optional)]
    (string! name)
    (assert (and (not (= (. shape.fields name) nil)) (not (. seen name)))
            {:code "invalid-arguments" :message "Optional names must be unique declared fields"})
    (set (. seen name) true)))

(fn validate-enum! [shape]
  (attributes! shape {:type true :values true})
  (when (= (array-length! shape.values) 0) (invalid! "Enum requires values"))
  (local seen {})
  (each [_ value (ipairs shape.values)]
    (string! value)
    (when (. seen value) (invalid! "Duplicate enum value"))
    (set (. seen value) true)))

(set validate-declaration!
  (fn [shape]
    (plain-table! shape)
    (if (= shape.type "string")
        (do
          (attributes! shape {:type true :min-bytes true :max-bytes true})
          (bounds! shape.min-bytes shape.max-bytes true))
        (= shape.type "integer")
        (do
          (attributes! shape {:type true :min true :max true})
          (bounds! shape.min shape.max false))
        (= shape.type "boolean") (attributes! shape {:type true})
        (= shape.type "enum") (validate-enum! shape)
        (= shape.type "record") (validate-record! shape)
        (= shape.type "array")
        (do
          (attributes! shape {:type true :items true :max-items true})
          (bounds! 0 shape.max-items true)
          (validate-declaration! shape.items))
        (invalid! "Unsupported shape type"))))

(fn validate-shape! [shape]
  ;; Detach first so cycles, metatables and declaration budgets are checked too.
  (validate-declaration! (detach! shape))
  true)

(var check-value! nil)

(fn check-record! [shape value]
  (plain-table! value)
  (local optional {})
  (each [_ name (ipairs shape.optional)] (set (. optional name) true))
  (each [name child (pairs shape.fields)]
    (if (= (. value name) nil)
        (when (not (. optional name)) (invalid! "Missing required field"))
        (check-value! child (. value name))))
  (each [name _ (pairs value)]
    (when (= (. shape.fields name) nil) (invalid! "Unknown record field"))))

(set check-value!
  (fn [shape value]
    (if (= shape.type "string")
        (do
          (string! value)
          (assert (<= shape.min-bytes (length value) shape.max-bytes)
                  {:code "invalid-arguments" :message "String outside declared byte bounds"}))
        (= shape.type "integer")
        (assert (and (integer? value) (<= shape.min value shape.max))
                {:code "invalid-arguments" :message "Integer outside declared bounds"})
        (= shape.type "boolean")
        (when (not (= (type value) "boolean")) (invalid! "Expected boolean"))
        (= shape.type "enum")
        (do
          (var found false)
          (each [_ item (ipairs shape.values)] (when (= value item) (set found true)))
          (when (not found) (invalid! "Value is not in enum")))
        (= shape.type "record") (check-record! shape value)
        (= shape.type "array")
        (do
          (when (> (array-length! value) shape.max-items) (invalid! "Array exceeds max-items"))
          (each [_ item (ipairs value)] (check-value! shape.items item))))))

(fn check! [shape value]
  (validate-shape! shape)
  (local detached (detach! value))
  (check-value! shape detached)
  detached)

{:validate-shape! validate-shape! :check! check! :detach! detach!}
