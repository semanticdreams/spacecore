(local Signal (require :signal))
(local appdirs (require :appdirs))
(local fs (require :fs))
(local Uuid (require :uuid))
(local RecordFiles (require :entities/record-files))
(local max-record-bytes 131072)

(fn fail [code message]
  (error {:code code :message message :outcome :not-committed}))

(fn storage! [f ...]
  (local (ok result) (pcall f ...))
  (if ok result
      (and (= (type result) :table) result.code) (error result)
      (fail :storage-failed (tostring result))))

(fn valid-id! [id]
  (when (not (and (= (type id) :string) (<= 1 (length id) 256)
                  (string.match id "^[%w_-]+$")))
    (fail :invalid-arguments "invalid string entity id"))
  id)

(fn snapshot [entity]
  {:id entity.id :value entity.value :revision entity.revision})

(fn copy-record [entity]
  (local result {})
  (each [k v (pairs entity)] (set (. result k) v))
  result)

(fn parse-record [content id]
  (local (header body) (string.match content "^%-%-%-\n(.-)\n%-%-%-\n(.*)$"))
  (when (not header) (fail :corrupt-data "missing string record frontmatter"))
  (local fm {})
  (each [line (string.gmatch header "[^\n]+")]
    (local (key value) (string.match line "^([^:]+):%s*(.-)%s*$"))
    (when (or (not key) (. fm key)) (fail :corrupt-data "invalid string record frontmatter"))
    (set (. fm key) value))
  (when (or (not= fm.id id) (not (tonumber fm.created-at)) (not (tonumber fm.updated-at))
            (and fm.revision (or (= fm.revision "") (> (length fm.revision) 512))))
    (error {:code :corrupt-data :message "invalid string record identity, timestamps or revision"
            :outcome :not-committed}))
  ;; The serializer owns one empty separator line, not arbitrary whitespace.
  (local value (if (= (string.sub body 1 1) "\n") (string.sub body 2) body))
  {:id id :created-at (tonumber fm.created-at) :updated-at (tonumber fm.updated-at)
   :revision (or fm.revision (.. "legacy:" id)) :value value})

(fn serialize [entity]
  (table.concat ["---" (.. "id: " entity.id)
                 (.. "created-at: " entity.created-at) (.. "updated-at: " entity.updated-at)
                 (.. "revision: " entity.revision) "---" "" entity.value] "\n"))

(fn page-limit [value default maximum]
  (local n (if (= value nil) default value))
  (when (not (and (= (type n) :number) (= n (math.floor n)) (>= n 1)))
    (fail :invalid-arguments "page limits must be positive integers"))
  (when (> n maximum) (fail :limit-exceeded "page limit exceeded"))
  n)

(fn notify! [signal entity result]
  (local (ok err) (pcall signal.emit signal entity))
  (when (not ok)
    (error {:code :notification-failed :message (tostring err) :outcome :committed :result result})))

(fn validate-fields! [data]
  (when (not (and (= (type data.value) :string)
                  (= (type data.created-at) :number) (= (type data.updated-at) :number)))
    (fail :invalid-arguments "string value and numeric timestamps required")))

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

(fn StringEntityStore [opts]
  (local options (or opts {}))
  (assert (= (type options) :table) {:code :invalid-arguments :message "store options must be a table" :outcome :not-committed})
  (local files (or options.files RecordFiles))
  (local base-dir (or options.base-dir (appdirs.user-data-dir "space")))
  (local root (fs.join-path base-dir "entities"))
  (local entities-dir (fs.join-path root "string"))
  (storage! fs.create-dirs entities-dir)
  (local cache {})
  (local string-entity-created (Signal))
  (local string-entity-updated (Signal))
  (local string-entity-deleted (Signal))

  (fn entity-path [id] (fs.join-path entities-dir (.. (valid-id! id) ".md")))
  (fn read-record [id max-bytes]
    (parse-record (storage! files.read! (entity-path id) max-bytes) id))
  (fn load-entity [id]
    (local path (entity-path id))
    (if (. cache id) (. cache id)
        (storage! fs.exists path)
        (do (local data (read-record id)) (set (. cache id) data) data)
        nil))
  (fn get-entity [_self id] (when id (load-entity id)))

  (fn write-record! [entity bounded?]
    (local content (serialize entity))
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
    (write-record! entity false)
    (set (. cache id) entity)
    (notify! string-entity-created entity (copy-record entity))
    entity)

  (fn update! [id updates expected bounded? snapshot-result?]
    (when (or (not= updates.id nil) (not= updates.revision nil))
      (fail :invalid-arguments "identity and revision are store-owned"))
    (local exists? (storage! fs.exists (entity-path id)))
    (when (and (not exists?) snapshot-result?) (fail :not-found "string entity not found"))
    (when exists?
      (local persisted (read-record id (when bounded? max-record-bytes)))
      (when (and expected (not= expected persisted.revision))
        (error {:code :conflict :message "stale text revision" :outcome :not-committed
                :current-revision persisted.revision}))
      (local staged (copy-record persisted))
      (each [k v (pairs updates)] (set (. staged k) v))
      (set staged.updated-at (os.time))
      (set staged.revision (Uuid.v4))
      (validate-fields! staged)
      (write-record! staged bounded?)
      ;; Publish only after rename, retaining references held by existing callers.
      (local entity (or (. cache id) staged))
      (each [k v (pairs staged)] (set (. entity k) v))
      (set (. cache id) entity)
      (local result (if snapshot-result? (snapshot entity) (copy-record entity)))
      (notify! string-entity-updated entity result)
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

  (fn delete-entity [_self id]
    (local entity (load-entity id))
    (when entity
      (storage! files.remove! (entity-path id))
      (set (. cache id) nil)
      (notify! string-entity-deleted entity (copy-record entity)))
    entity)

  (fn ids [] (storage! files.list-ids entities-dir ".md"))
  (fn list-entities [_self]
    (local items [])
    (each [_ id (ipairs (ids))] (table.insert items (load-entity id)))
    (table.sort items (fn [a b] (> a.updated-at b.updated-at)))
    items)

  (fn scan-page [_self opts]
    (scan-text-page ids read-record opts))

  {:base-dir base-dir :root root :entities-dir entities-dir
   :string-entity-created string-entity-created :string-entity-updated string-entity-updated
   :string-entity-deleted string-entity-deleted
   :get-entity get-entity :create-entity create-entity :update-entity update-entity
   :delete-entity delete-entity :list-entities list-entities
   :read-text read-text :replace-text replace-text :scan-page scan-page})

(var default-store nil)
(fn get-default [opts]
  (if default-store default-store
      (do (set default-store (StringEntityStore opts)) default-store)))
{:StringEntityStore StringEntityStore :get-default get-default}
