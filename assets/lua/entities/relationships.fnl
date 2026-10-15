;; Context-free directed relationships between existing text records.
;; Domain validation deliberately needs neither graph loaders nor adapters.
(fn endpoint-id! [ref]
  (assert (and (= (type ref) :table) (= (getmetatable ref) nil))
          {:code :invalid-arguments :message "endpoint must be a reference" :outcome :not-committed})
  (each [key _ (pairs ref)]
    (assert (= key :key) {:code :invalid-arguments :message "unknown reference field" :outcome :not-committed}))
  (local key ref.key)
  (assert (and (= (type key) :string) (<= 1 (length key) 256) (utf8.len key))
          {:code :invalid-arguments :message "invalid endpoint key" :outcome :not-committed})
  (local id (string.match key "^string%-entity:([A-Za-z0-9_-]+)$"))
  (assert id {:code :invalid-arguments :message "unsupported relationship endpoint" :outcome :not-committed})
  id)

(fn create! [string-store link-store source-ref target-ref]
  (local source-id (endpoint-id! source-ref))
  (local target-id (endpoint-id! target-ref))
  ;; Validate at the domain write boundary, not through graph materialization.
  (string-store:read-text source-id)
  (string-store:read-text target-id)
  (link-store:create-entity {:source-key source-ref.key :target-key target-ref.key}))

{:create! create!}
