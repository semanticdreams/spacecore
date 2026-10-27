(local Signal (require :signal))
(local appdirs (require :appdirs))
(local fs (require :fs))
(local Uuid (require :uuid))
(local RecordFiles (require :entities/record-files))
(local R (require :reference-lifecycle/record-utils))
(local max-record-bytes 131072)

(fn fail [code message]
  (error {:code code :message message :outcome :not-committed}))

(fn storage! [f ...]
  (local (ok result cleanup-error) (pcall f ...))
  (if ok (values result cleanup-error)
      (and (= (type result) :table) result.code) (error result)
      (fail :storage-failed (tostring result))))

(fn valid-id! [id]
  (when (not (and (= (type id) :string) (<= 1 (length id) 256)
                  (string.match id "^[%w_-]+$")))
    (fail :invalid-arguments "invalid string entity id"))
  id)

(fn snapshot [entity]
  {:id entity.id :value entity.value :revision (or entity.revision (.. "legacy:" entity.id))})

(fn copy-record [entity]
  (local result {})
  (each [k v (pairs entity)] (set (. result k) v))
  result)

;; Pure owning codec: absence of a legacy revision remains absence. Only the
;; detached text-read boundary supplies the effective legacy precondition token.
(fn decode-entity [_self content]
  (local (header body) (string.match content "^%-%-%-\n(.-)\n%-%-%-\n(.*)$"))
  (when (not header) (fail :corrupt-data "missing string record frontmatter"))
  (local fm {})
  (each [line (string.gmatch header "[^\n]+")]
    (local (key value) (string.match line "^([^:]+):%s*(.-)%s*$"))
    (when (or (not key) (. fm key)) (fail :corrupt-data "invalid string record frontmatter"))
    (set (. fm key) value))
  (valid-id! fm.id)
  (when (or (not (tonumber fm.created-at)) (not (tonumber fm.updated-at))
            (and fm.revision (or (= fm.revision "") (> (length fm.revision) 512))))
    (error {:code :corrupt-data :message "invalid string record timestamps or revision" :outcome :not-committed}))
  (local value (if (= (string.sub body 1 1) "\n") (string.sub body 2) body))
  {:id fm.id :created-at (tonumber fm.created-at) :updated-at (tonumber fm.updated-at)
   :revision fm.revision :value value})

(fn validate-fields! [data]
  (valid-id! data.id)
  (when (not (and (= (type data.value) :string)
                  (= (type data.created-at) :number) (= (type data.updated-at) :number)
                  (or (= data.revision nil)
                      (and (= (type data.revision) :string) (<= 1 (length data.revision) 512)))))
    (error {:code :invalid-arguments :message "string value, numeric timestamps and optional revision required" :outcome :not-committed})))

(fn serialize-entity [_self entity]
  (validate-fields! entity)
  (local lines ["---" (.. "id: " entity.id)
                (.. "created-at: " entity.created-at) (.. "updated-at: " entity.updated-at)])
  (when entity.revision (table.insert lines (.. "revision: " entity.revision)))
  (each [_ line (ipairs ["---" "" entity.value])] (table.insert lines line))
  (table.concat lines "\n"))

(fn page-limit [value default maximum]
  (local n (if (= value nil) default value))
  (when (not (and (= (type n) :number) (= n (math.floor n)) (>= n 1)))
    (fail :invalid-arguments "page limits must be positive integers"))
  (when (> n maximum) (fail :limit-exceeded "page limit exceeded"))
  n)

(fn notify! [signal entity result cleanup-error]
  (local (ok err) (pcall signal.emit signal entity))
  (when cleanup-error
    (error {:code :storage-failed :outcome :committed :result result
            :message (if ok "Record committed; staging cleanup failed."
                            "Record committed; staging cleanup and notification failed.")
            :cleanup-error cleanup-error :notification-error (when (not ok) (tostring err))}))
  (when (not ok)
    (error {:code :notification-failed :message (tostring err) :outcome :committed :result result})))

(fn scan-text-page [ids read-record opts]
  (local settings (or opts {}))
  (assert (= (type settings) :table) {:code :invalid-arguments :message "scan options must be a table" :outcome :not-committed})
  (local limit (page-limit settings.limit 20 50))
  (local examined-limit (page-limit settings.examined-limit 200 200))
  (when (not= settings.after-id nil) (valid-id! settings.after-id))
  (when (and (not= settings.query nil) (not= (type settings.query) :string))
    (fail :invalid-arguments "query must be literal text"))
  (local page {:items [] :examined 0 :has-more false})
  (each [_ id (ipairs (ids))]
    (when (or (not settings.after-id) (> id settings.after-id))
      (if (or (>= (length page.items) limit) (>= page.examined examined-limit))
          (set page.has-more true)
          (do
            (local data (read-record id max-record-bytes))
            (when (not (utf8.len data.value))
              (fail :corrupt-data "string record body is not valid UTF-8"))
            (set page.examined (+ page.examined 1))
            (set page.last-id id)
            (when (or (not settings.query) (string.find data.value settings.query 1 true))
              (table.insert page.items (copy-record data)))))))
  page)

(fn publish! [cache candidate]
  (local held (. cache candidate.id))
  (if held
      (do
        ;; pairs cannot clear an optional field absent in a frozen after-image.
        (set held.revision candidate.revision)
        (each [key value (pairs candidate)] (set (. held key) value))
        held)
      (do (set (. cache candidate.id) candidate) candidate)))

(fn record-path [store id]
  (storage! R.record-path store.base-dir store.entities-dir (valid-id! id) ".md"))

;; Prepared bytes already contain identity, time and revision. Publication of
;; held objects/signals is the lifecycle reconciliation phase, not this write.
(fn persist-entity! [self id bytes check]
  (local candidate (decode-entity nil bytes))
  (R.verify-candidate id candidate bytes check "string")
  (assert (= (R.check-bytes bytes "string") check) "string frozen after-check mismatch")
  (local (_written cleanup-error) (storage! self.files.write-text! (record-path self id) bytes))
  (when cleanup-error
    (error {:code :storage-failed :outcome :committed :result (copy-record candidate)
            :message "Record committed; staging cleanup failed." :cleanup-error cleanup-error}))
  candidate)

(fn reconcile-entity! [self id bytes before-check after-check]
  (assert (= (. (self:snapshot-entity id) :check) after-check) "string reconciliation after-image mismatch")
  (assert (= (R.check-bytes bytes "string") after-check) "string frozen after-check mismatch")
  (local frozen-image (if (= bytes false) before-check bytes))
  (local candidate (decode-entity nil frozen-image))
  (R.verify-candidate id candidate frozen-image
                      (if (= bytes false) before-check after-check) "string")
  (if (= bytes false)
      (do
        (local held (or (. self.cache id) candidate))
        (set (. self.cache id) nil)
        (notify! self.string-entity-deleted held (copy-record held))
        held)
      (do
        (local published (publish! self.cache candidate))
        (notify! (if (= before-check false) self.string-entity-created self.string-entity-updated)
                 published (copy-record published))
        published)))

(fn StringEntityStore [opts]
  (local options (or opts {}))
  (assert (= (type options) :table) {:code :invalid-arguments :message "store options must be a table" :outcome :not-committed})
  (local files (or options.files RecordFiles))
  (local base-dir (fs.absolute (or options.base-dir (appdirs.user-data-dir "space"))))
  (local root (fs.join-path base-dir "entities"))
  (local entities-dir (fs.join-path root "string"))
  (storage! fs.create-dirs entities-dir)
  (local cache {})
  (local string-entity-created (Signal))
  (local string-entity-updated (Signal))
  (local string-entity-deleted (Signal))

  (fn entity-path [id] (storage! R.record-path base-dir entities-dir (valid-id! id) ".md"))
  (fn read-record [id max-bytes]
    (local data (decode-entity nil (storage! files.read! (entity-path id) max-bytes)))
    (when (not= data.id id) (fail :corrupt-data "string record identity mismatch"))
    data)
  (fn load-entity [id]
    (local path (entity-path id))
    (if (. cache id) (. cache id)
        (storage! fs.exists path) (publish! cache (read-record id))
        nil))
  (fn get-entity [_self id] (when id (load-entity id)))
  (fn snapshot-entity [_self id]
    (local path (entity-path id))
    (if (not (storage! fs.exists path)) {:path path :bytes false :value false :check false}
        (do
          (local bytes (storage! files.read! path))
          (local value (decode-entity nil bytes))
          (when (not= value.id id) (fail :corrupt-data "string record identity mismatch"))
          {:path path :bytes bytes :value value :check (R.check-bytes bytes "string")})))
  (fn write-record! [entity bounded?]
    (local content (serialize-entity nil entity))
    (when (and bounded? (> (length content) max-record-bytes))
      (fail :limit-exceeded "record exceeds stored-byte limit"))
    (storage! files.write-text! (entity-path entity.id) content))

  (fn create-entity [_self opts]
    (local settings (or opts {}))
    (assert (= (type settings) :table) {:code :invalid-arguments :message "create options must be a table" :outcome :not-committed})
    (when (not= settings.revision nil) (fail :invalid-arguments "revision is store-owned"))
    (local id (valid-id! (or settings.id (Uuid.v4))))
    (when (or (. cache id) (storage! fs.exists (entity-path id)))
      (fail :conflict "string entity already exists"))
    (local now (os.time))
    (local entity {:id id :value (or settings.value "") :revision (Uuid.v4)
                  :created-at (or settings.created-at now) :updated-at (or settings.updated-at now)})
    (validate-fields! entity)
    (local (_written cleanup-error) (write-record! entity false))
    (publish! cache entity)
    (notify! string-entity-created entity (copy-record entity) cleanup-error)
    entity)
  (fn update! [id updates expected bounded? snapshot-result?]
    (when (or (not= updates.id nil) (not= updates.revision nil))
      (fail :invalid-arguments "identity and revision are store-owned"))
    (local exists? (storage! fs.exists (entity-path id)))
    (when (and (not exists?) snapshot-result?) (fail :not-found "string entity not found"))
    (when exists?
      (local persisted (read-record id (when bounded? max-record-bytes)))
      (local current-revision (. (snapshot persisted) :revision))
      (when (and expected (not= expected current-revision))
        (error {:code :conflict :message "stale text revision" :outcome :not-committed
                :current-revision current-revision}))
      (local staged (copy-record persisted))
      (each [k v (pairs updates)] (set (. staged k) v))
      (set staged.updated-at (os.time))
      (set staged.revision (Uuid.v4))
      (validate-fields! staged)
      (local (_written cleanup-error) (write-record! staged bounded?))
      (local entity (publish! cache staged))
      (local result (if snapshot-result? (snapshot entity) (copy-record entity)))
      (notify! string-entity-updated entity result cleanup-error)
      (if snapshot-result? result entity)))
  (fn update-entity [_self id updates]
    (assert (or (= updates nil) (= (type updates) :table))
            {:code :invalid-arguments :message "updates must be a table" :outcome :not-committed})
    (update! id (or updates {}) nil false false))
  (fn read-text [_self id]
    (valid-id! id)
    (when (not (storage! fs.exists (entity-path id))) (fail :not-found "string entity not found"))
    (snapshot (read-record id max-record-bytes)))
  (fn replace-text [_self id value expected-revision]
    (when (not (and (= (type expected-revision) :string) (<= 1 (length expected-revision) 512)
                    (= (type value) :string)))
      (fail :invalid-arguments "text and expected revision required"))
    (update! id {:value value} expected-revision true true))
  (fn retire-entity! [_self id]
    (local entity (load-entity id))
    (when entity
      (storage! files.remove! (entity-path id))
      (set (. cache id) nil)
      (notify! string-entity-deleted entity (copy-record entity)))
    entity)
  (fn ids [] (storage! files.list-ids entities-dir ".md"))
  (fn list-entities [_self]
    ;; Re-read durable records so reconciliation and cold inventories never
    ;; return a stale cached after-image, while preserving held object identity.
    (local entries (storage! R.record-entries entities-dir ".md"))
    (local candidates (icollect [_ entry (ipairs entries)] (read-record (string.sub entry.name 1 -4))))
    (local items (icollect [_ data (ipairs candidates)] (publish! cache data)))
    (table.sort items (fn [a b] (> a.updated-at b.updated-at)))
    items)
  (fn scan-page [_self opts] (scan-text-page ids read-record opts))

  {:base-dir base-dir :root root :entities-dir entities-dir :cache cache :files files
   :string-entity-created string-entity-created :string-entity-updated string-entity-updated
   :string-entity-deleted string-entity-deleted
   :get-entity get-entity :create-entity create-entity :update-entity update-entity
   :retire-entity! retire-entity! :list-entities list-entities
   :read-text read-text :replace-text replace-text :scan-page scan-page
   :snapshot-entity snapshot-entity :serialize-entity serialize-entity :decode-entity decode-entity
   :persist-entity! persist-entity! :reconcile-entity! reconcile-entity!})

(var default-store nil)
(fn get-default [opts]
  (when (not default-store) (set default-store (StringEntityStore opts)))
  default-store)
{:StringEntityStore StringEntityStore :get-default get-default}
