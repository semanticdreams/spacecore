(local Signal (require :signal))
(local appdirs (require :appdirs))
(local fs (require :fs))
(local Uuid (require :uuid))
(local json (require :json))
(local RecordFiles (require :entities/record-files))

(fn fail [code message]
  (error {:code code :message message :outcome :not-committed}))
(fn storage! [f ...]
  (local (ok result cleanup-error) (pcall f ...))
  (if ok (values result cleanup-error)
      (and (= (type result) :table) result.code) (error result)
      (fail :storage-failed (tostring result))))
(fn valid-id! [id]
  (when (not (and (= (type id) :string) (<= 1 (length id) 256) (string.match id "^[%w_-]+$")))
    (fail :invalid-arguments "invalid link entity id"))
  id)
(fn copy-record [entity] (json.loads (json.dumps entity)))
(fn validate-record! [entity id code]
  (when (not (and (= (type entity) :table) (= entity.id id)
                  (= (type entity.source-key) :string) (= (type entity.target-key) :string)
                  (= (type entity.created-at) :number) (= (type entity.metadata) :table)))
    (fail code "invalid link record identity or required fields"))
  entity)
(fn read-record [files path id max-bytes]
  (local content (storage! files.read! path max-bytes))
  (local (ok data) (pcall json.loads content))
  (when (not ok) (fail :corrupt-data "invalid link JSON"))
  (validate-record! data id :corrupt-data))
(fn notify! [signal entity cleanup-error]
  (local result (copy-record entity))
  (local (ok err) (pcall signal.emit signal entity))
  (when cleanup-error
    (error {:code :storage-failed :outcome :committed :result result
            :message (if ok "Record committed; staging cleanup failed."
                            "Record committed; staging cleanup and notification failed.")
            :cleanup-error cleanup-error :notification-error (when (not ok) (tostring err))}))
  (when (not ok)
    (error {:code :notification-failed :message (tostring err) :outcome :committed :result result})))
(fn page-limit [value default maximum]
  (local n (if (= value nil) default value))
  (when (not (and (= (type n) :number) (= n (math.floor n)) (>= n 1)))
    (fail :invalid-arguments "page limits must be positive integers"))
  (when (> n maximum) (fail :limit-exceeded "page limit exceeded"))
  n)

(fn LinkEntityStore [opts]
  (local options (or opts {}))
  (assert (= (type options) :table) {:code :invalid-arguments :message "store options must be a table" :outcome :not-committed})
  (local files (or options.files RecordFiles))
  (local base-dir (or options.base-dir (appdirs.user-data-dir "space")))
  (local root (fs.join-path base-dir "entities"))
  (local entities-dir (fs.join-path root "link"))
  (storage! fs.create-dirs entities-dir)
  (local cache {})
  (local link-entity-created (Signal))
  (local link-entity-updated (Signal))
  (local link-entity-deleted (Signal))

  (fn entity-path [id] (fs.join-path entities-dir (.. (valid-id! id) ".json")))
  (fn load-entity [id]
    (local path (entity-path id))
    (if (. cache id) (. cache id)
        (storage! fs.exists path)
        (do (local data (read-record files path id)) (set (. cache id) data) data)
        nil))
  (fn get-entity [_self id] (when id (load-entity id)))
  ;; Participating nonvisual reads are bounded, detached and never prime cache.
  ;; Legacy get-entity retains its existing lookup/cache semantics.
  (fn read-link [_self id]
    (valid-id! id)
    (when (not (storage! fs.exists (entity-path id))) (fail :not-found "link entity not found"))
    (read-record files (entity-path id) id 131072))
  (fn write-record! [entity]
    (storage! files.write-json! (entity-path entity.id) entity))

  (fn create-entity [_self opts]
    (local settings (or opts {}))
    (assert (= (type settings) :table) {:code :invalid-arguments :message "create options must be a table" :outcome :not-committed})
    (when (not= settings.revision nil) (fail :invalid-arguments "revision cannot be supplied"))
    (local id (valid-id! (or settings.id (Uuid.v4))))
    (when (or (. cache id) (storage! fs.exists (entity-path id)))
      (fail :conflict "link entity already exists"))
    (local entity {:id id :source-key (or settings.source-key "") :target-key (or settings.target-key "")
                  :created-at (or settings.created-at (os.time)) :metadata (or settings.metadata {})})
    (validate-record! entity id :invalid-arguments)
    (local detached (copy-record entity))
    (local (_written cleanup-error) (write-record! detached))
    (set (. cache id) detached)
    (notify! link-entity-created detached cleanup-error)
    detached)

  (fn update-entity [_self id updates]
    (local changes (or updates {}))
    (assert (= (type changes) :table) {:code :invalid-arguments :message "updates must be a table" :outcome :not-committed})
    (when (or (not= changes.id nil) (not= changes.revision nil))
      (fail :invalid-arguments "identity and revision cannot be overridden"))
    (local entity (load-entity id))
    (when entity
      (local staged (copy-record entity))
      (each [k v (pairs changes)] (set (. staged k) v))
      (validate-record! staged id :invalid-arguments)
      (local detached (copy-record staged))
      (local (_written cleanup-error) (write-record! detached))
      (each [k v (pairs detached)] (set (. entity k) v))
      (notify! link-entity-updated entity cleanup-error))
    entity)

  (fn delete-entity [_self id]
    (local entity (load-entity id))
    (when entity
      (storage! files.remove! (entity-path id))
      (set (. cache id) nil)
      (notify! link-entity-deleted entity))
    entity)

  (fn ids [] (storage! files.list-ids entities-dir ".json"))
  (fn list-entities [_self]
    (local items [])
    (each [_ id (ipairs (ids))] (table.insert items (load-entity id)))
    (table.sort items (fn [a b] (> a.created-at b.created-at)))
    items)
  (fn find-edges-for-nodes [self node-keys]
    (assert (or (= node-keys nil) (= (type node-keys) :table))
            {:code :invalid-arguments :message "node keys must be a table" :outcome :not-committed})
    (local key-set {})
    (each [_ key (ipairs (or node-keys []))] (set (. key-set (tostring key)) true))
    (local results [])
    (each [_ data (ipairs (list-entities self))]
      (when (and (. key-set data.source-key) (. key-set data.target-key)) (table.insert results data)))
    results)
  (fn find-entities-for-key [self key]
    (assert (= (type key) :string) {:code :invalid-arguments :message "key must be text" :outcome :not-committed})
    (local key-str (tostring key))
    (local results [])
    (each [_ data (ipairs (list-entities self))]
      (when (or (= data.source-key key-str) (= data.target-key key-str)) (table.insert results data)))
    results)

  (fn scan-page [_self opts]
    (local settings (or opts {}))
    (assert (= (type settings) :table) {:code :invalid-arguments :message "scan options must be a table" :outcome :not-committed})
    (local limit (page-limit settings.limit 20 50))
    (local examined-limit (page-limit settings.examined-limit 200 200))
    (when (not= settings.after-id nil) (valid-id! settings.after-id))
    (when (and (not= settings.key nil) (not= (type settings.key) :string))
      (fail :invalid-arguments "incident key must be text"))
    (local page {:items [] :examined 0 :has-more false})
    (each [_ id (ipairs (ids))]
      (when (or (not settings.after-id) (> id settings.after-id))
        (if (or (>= (length page.items) limit) (>= page.examined examined-limit))
            (set page.has-more true)
            (do
              (local data (read-record files (entity-path id) id 131072))
              (set page.examined (+ page.examined 1))
              (set page.last-id id)
              (when (or (not settings.key) (= settings.key data.source-key) (= settings.key data.target-key))
                (table.insert page.items (copy-record data)))))))
    page)

  {:base-dir base-dir :root root :entities-dir entities-dir
   :link-entity-created link-entity-created :link-entity-updated link-entity-updated
   :link-entity-deleted link-entity-deleted
   :get-entity get-entity :read-link read-link :create-entity create-entity :update-entity update-entity
   :delete-entity delete-entity :list-entities list-entities :scan-page scan-page
   :find-edges-for-nodes find-edges-for-nodes :find-entities-for-key find-entities-for-key})

(var default-store nil)
(fn get-default [opts]
  (if default-store default-store
      (do (set default-store (LinkEntityStore opts)) default-store)))
{:LinkEntityStore LinkEntityStore :get-default get-default}
