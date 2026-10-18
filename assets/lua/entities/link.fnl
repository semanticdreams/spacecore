(local Signal (require :signal))
(local appdirs (require :appdirs))
(local fs (require :fs))
(local Uuid (require :uuid))
(local json (require :json))
(local RecordFiles (require :entities/record-files))
(local IdentityStore (require :entities/identity))
(local R (require :reference-lifecycle/record-utils))

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
(fn decode-entity [_self bytes]
  (fn decode []
    (local data (R.decode-json bytes))
    (assert (= (type data) :table) "link record must be an object")
    {:id (R.require-id data.id)
     :source-key (R.field data :source-key :string "")
     :target-key (R.field data :target-key :string "")
     :created-at (R.field data :created-at :number 0)
     :metadata (R.field data :metadata :table {})})
  (local (ok result) (pcall decode))
  (if ok result (fail :corrupt-data (tostring result))))

(fn read-link-record [files path id max-bytes]
  (fn read []
    (local bytes (storage! files.read! path max-bytes))
    (local entity (decode-entity nil bytes))
    (when (not= entity.id id) (fail :corrupt-data "link record id mismatch"))
    (values entity bytes))
  (local (ok result bytes) (pcall read))
  (if ok (values result bytes)
      (error {:code result.code :outcome result.outcome
              :message (.. "link record read failed at " path ": " result.message)})))
(fn serialize-entity [_self entity]
  (valid-id! entity.id)
  (validate-record! entity entity.id :invalid-arguments)
  (json.dumps {:id entity.id :source-key entity.source-key :target-key entity.target-key
               :created-at entity.created-at :metadata entity.metadata}))
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

;; Exact authored key, traversed dependency, or equal terminal meaning. This is
;; shared by bounded incident scans and ordinary owner lookups, not Graph APIs.
(fn matches-key? [store endpoint key terminal]
  (assert (= (type endpoint) :string) "link endpoint must be a string")
  (local (resolved chain) (store:resolve-key endpoint))
  (var matches? (or (= endpoint key) (= resolved terminal)))
  (each [_ dependency (ipairs chain)]
    (when (= dependency key) (set matches? true)))
  matches?)
(fn incident? [store entity key terminal]
  ;; Resolve both endpoints even if the first matches: invalid dependencies must
  ;; not be hidden behind short-circuiting or reported as successful absence.
  (local source? (matches-key? store entity.source-key key terminal))
  (local target? (matches-key? store entity.target-key key terminal))
  (if source? true target?))
(fn endpoint-in-nodes? [store endpoint nodes]
  (var found? false)
  (each [_ key (ipairs nodes)]
    (when (matches-key? store endpoint key (store:resolve-key key)) (set found? true)))
  found?)

(fn publish! [cache candidate]
  (local held (. cache candidate.id))
  (if held
      (do (each [key value (pairs candidate)] (set (. held key) value)) held)
      (do (set (. cache candidate.id) candidate) candidate)))

(fn persist-entity! [self id bytes check]
  (local candidate (decode-entity nil bytes))
  (R.verify-candidate id candidate bytes check "json")
  (assert (= (R.check-bytes bytes "json") check) "link frozen after-check mismatch")
  (local path (storage! R.record-path self.base-dir self.entities-dir (valid-id! id) ".json"))
  ;; No ensure-key, time, identity allocation, cache or signal publication here.
  (local (_written cleanup-error) (storage! self.files.write-text! path bytes))
  (when cleanup-error
    (error {:code :storage-failed :outcome :committed :result (copy-record candidate)
            :message "Record committed; staging cleanup failed." :cleanup-error cleanup-error}))
  candidate)

(fn reconcile-entity! [self id bytes before-check after-check]
  (assert (= (. (self:snapshot-entity id) :check) after-check) "link reconciliation after-image mismatch")
  (assert (= (R.check-bytes bytes "json") after-check) "link frozen after-check mismatch")
  (local frozen-image (if (= bytes false) before-check bytes))
  (local candidate (decode-entity nil frozen-image))
  (R.verify-candidate id candidate frozen-image
                      (if (= bytes false) before-check after-check) "json")
  (if (= bytes false)
      (do
        (local held (or (. self.cache id) candidate))
        (set (. self.cache id) nil)
        (notify! self.link-entity-deleted held)
        held)
      (do
        (local published (publish! self.cache candidate))
        (notify! (if (= before-check false) self.link-entity-created self.link-entity-updated) published)
        published)))

(fn scan-links-page [ids read-record identity-store opts]
  (local settings (or opts {}))
  (assert (= (type settings) :table) {:code :invalid-arguments :message "scan options must be a table" :outcome :not-committed})
  (local limit (page-limit settings.limit 20 50))
  (local examined-limit (page-limit settings.examined-limit 200 200))
  (when (not= settings.after-id nil) (valid-id! settings.after-id))
  (when (and (not= settings.key nil) (not= (type settings.key) :string))
    (fail :invalid-arguments "incident key must be text"))
  (local terminal (when settings.key (identity-store:resolve-key settings.key)))
  (local page {:items [] :examined 0 :has-more false})
  (each [_ id (ipairs (ids))]
    (when (or (not settings.after-id) (> id settings.after-id))
      (if (or (>= (length page.items) limit) (>= page.examined examined-limit))
          (set page.has-more true)
          (do
            (local data (read-record id 131072))
            (set page.examined (+ page.examined 1))
            (set page.last-id id)
            (when (or (not settings.key) (incident? identity-store data settings.key terminal))
              (table.insert page.items (copy-record data)))))))
  page)

(fn LinkEntityStore [opts]
  (local options (or opts {}))
  (assert (= (type options) :table) {:code :invalid-arguments :message "store options must be a table" :outcome :not-committed})
  (local files (or options.files RecordFiles))
  (local base-dir (fs.absolute (or options.base-dir (appdirs.user-data-dir "space"))))
  (local identity-store (or options.identity-store (IdentityStore.IdentityStore {:base-dir base-dir})))
  (assert (= identity-store.base-dir base-dir) "LinkEntityStore identity-store base-dir mismatch")
  (local root (fs.join-path base-dir "entities"))
  (local entities-dir (fs.join-path root "link"))
  (storage! fs.create-dirs entities-dir)
  (local cache {})
  (local link-entity-created (Signal))
  (local link-entity-updated (Signal))
  (local link-entity-deleted (Signal))

  (fn entity-path [id] (storage! R.record-path base-dir entities-dir (valid-id! id) ".json"))
  (fn read-record [id max-bytes]
    (read-link-record files (entity-path id) id max-bytes))
  (fn load-entity [id]
    (local path (entity-path id))
    (if (. cache id) (. cache id)
        (storage! fs.exists path) (publish! cache (read-record id))
        nil))
  (fn get-entity [_self id] (when id (load-entity id)))
  (fn read-link [_self id]
    (valid-id! id)
    (when (not (storage! fs.exists (entity-path id))) (fail :not-found "link entity not found"))
    (read-record id 131072))
  (fn snapshot-entity [_self id]
    (local path (entity-path id))
    (if (not (storage! fs.exists path)) {:path path :bytes false :value false :check false}
        (do
          (local (value bytes) (read-link-record files path id))
          {:path path :bytes bytes :value value :check (R.check-bytes bytes "json")})))
  (fn write-record! [entity]
    (storage! files.write-json! (entity-path entity.id) entity))

  (fn create-entity [_self opts]
    (local settings (or opts {}))
    (assert (= (type settings) :table) {:code :invalid-arguments :message "create options must be a table" :outcome :not-committed})
    (when (not= settings.revision nil) (fail :invalid-arguments "revision cannot be supplied"))
    (local id (valid-id! (or settings.id (Uuid.v4))))
    (when (or (. cache id) (storage! fs.exists (entity-path id)))
      (fail :conflict "link entity already exists"))
    (local candidate {:id id :source-key (or settings.source-key "") :target-key (or settings.target-key "")
                      :created-at (or settings.created-at (os.time)) :metadata (or settings.metadata {})})
    (validate-record! candidate id :invalid-arguments)
    (set candidate.source-key (identity-store:ensure-key candidate.source-key))
    (set candidate.target-key (identity-store:ensure-key candidate.target-key))
    (local entity (copy-record candidate))
    (local (_written cleanup-error) (write-record! entity))
    (publish! cache entity)
    (notify! link-entity-created entity cleanup-error)
    entity)
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
      ;; Normalize only authored fields; never replace an untouched explicit alias.
      (each [_ field (ipairs [:source-key :target-key])]
        (when (not= (. changes field) nil)
          (set (. staged field) (identity-store:ensure-key (. staged field)))))
      (local detached (copy-record staged))
      (local (_written cleanup-error) (write-record! detached))
      (publish! cache detached)
      (notify! link-entity-updated entity cleanup-error))
    entity)
  (fn retire-entity! [_self id]
    (local entity (load-entity id))
    (when entity
      (storage! files.remove! (entity-path id))
      (set (. cache id) nil)
      (notify! link-entity-deleted entity))
    entity)
  (fn ids [] (storage! files.list-ids entities-dir ".json"))
  (fn list-entities [_self]
    (local entries (storage! R.record-entries entities-dir ".json"))
    (local candidates (icollect [_ entry (ipairs entries)] (read-record (string.sub entry.name 1 -6))))
    (local items (icollect [_ data (ipairs candidates)] (publish! cache data)))
    (table.sort items (fn [a b] (> a.created-at b.created-at)))
    items)
  (fn find-edges-for-nodes [self node-keys]
    (assert (or (= node-keys nil) (= (type node-keys) :table))
            {:code :invalid-arguments :message "node keys must be a table" :outcome :not-committed})
    (local results [])
    (each [_ data (ipairs (list-entities self))]
      (when (and (not= data.source-key "") (not= data.target-key "")
                 (endpoint-in-nodes? identity-store data.source-key (or node-keys []))
                 (endpoint-in-nodes? identity-store data.target-key (or node-keys [])))
        (table.insert results data)))
    results)
  (fn find-entities-for-key [self key]
    (assert (= (type key) :string) {:code :invalid-arguments :message "key must be text" :outcome :not-committed})
    (local terminal (identity-store:resolve-key key))
    (local results [])
    (each [_ data (ipairs (list-entities self))]
      (when (incident? identity-store data key terminal) (table.insert results data)))
    results)
  (fn scan-page [_self opts]
    (scan-links-page ids read-record identity-store opts))

  {:base-dir base-dir :root root :entities-dir entities-dir :identity-store identity-store :cache cache :files files
   :link-entity-created link-entity-created :link-entity-updated link-entity-updated
   :link-entity-deleted link-entity-deleted
   :get-entity get-entity :read-link read-link :create-entity create-entity :update-entity update-entity
   :retire-entity! retire-entity! :list-entities list-entities :scan-page scan-page
   :find-edges-for-nodes find-edges-for-nodes :find-entities-for-key find-entities-for-key
   :snapshot-entity snapshot-entity :serialize-entity serialize-entity :decode-entity decode-entity
   :persist-entity! persist-entity! :reconcile-entity! reconcile-entity!})

(var default-store nil)
(fn get-default [opts]
  (local options (or opts {}))
  (when default-store
    (assert (or (not options.base-dir) (= (fs.absolute options.base-dir) default-store.base-dir))
            "LinkEntityStore default base-dir mismatch")
    (assert (or (not options.identity-store) (= options.identity-store default-store.identity-store))
            "LinkEntityStore default identity-store mismatch"))
  (when (not default-store)
    (local base-dir (fs.absolute (or options.base-dir (appdirs.user-data-dir "space"))))
    (local identity-store (or options.identity-store (IdentityStore.get-default {:base-dir base-dir})))
    (set default-store (LinkEntityStore {:base-dir base-dir :identity-store identity-store :files options.files})))
  default-store)
{:LinkEntityStore LinkEntityStore :get-default get-default}
