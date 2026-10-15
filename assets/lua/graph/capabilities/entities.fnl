(local Shapes (require :graph/capability-shapes))
(local Relationships (require :entities/relationships))
(local json (require :json))

(fn text [minimum maximum] {:type :string :min-bytes minimum :max-bytes maximum})
(fn record [fields optional] {:type :record :fields fields :optional (or optional [])})
(local ref-shape (record {:key (text 1 256)}))
(local entry-shape (record {:ref ref-shape :summary (text 0 160)}))
(local written-shape (record {:ref ref-shape :revision (text 1 512)}))
(local read-shape (record {:ref ref-shape :text (text 0 65536) :revision (text 1 512)}))
(local relation-shape (record {:ref ref-shape :source ref-shape :target ref-shape}))
(local page-fields {:limit {:type :integer :min 1 :max 50} :cursor (text 1 2048)})
(local page-args (record page-fields [:limit :cursor]))
(local search-args (record {:limit page-fields.limit :cursor page-fields.cursor :query (text 1 256)} [:limit :cursor]))
(local relation-args (record {:limit page-fields.limit :cursor page-fields.cursor :subject ref-shape} [:limit :cursor]))
(local cursor-shape (record {:operation (text 1 64) :key (text 1 256)
                            :query (text 0 256) :after-id (text 1 256)}))

(fn page-shape [item]
  (record {:items {:type :array :items item :max-items 50} :has-more {:type :boolean}
           :cursor page-fields.cursor} [:cursor]))

(fn metadata [id description arguments result effect revision]
  {:id id :description description :arguments arguments :result result
   :effect effect :revision revision})
(local collection-metadata
  [(metadata "collection.list" "List stored texts" page-args (page-shape entry-shape) :read :none)
   (metadata "collection.search" "Search text bodies with a case-sensitive literal substring"
             search-args (page-shape entry-shape) :read :none)
   (metadata "collection.create" "Create a text" (record {:text (text 0 65536)}) written-shape :write :none)])
(local text-metadata
  [(metadata "text.read" "Read exact text and its revision" (record {}) read-shape :read :none)
   (metadata "text.replace" "Replace text if the supplied revision is current"
             (record {:text (text 0 65536)}) written-shape :write :required)])
(local relationship-metadata
  [(metadata "relationships.list" "List direct incident persisted relationships"
             relation-args (page-shape relation-shape) :read :none)
   (metadata "relationships.create" "Create a directed relationship between existing texts"
             (record {:source ref-shape :target ref-shape}) relation-shape :write :none)])

(fn fail! [code message]
  (error {:code code :message message :outcome :not-committed}))
(fn ref-for [scheme id] {:key (.. scheme ":" id)})
(fn id! [scheme ref]
  (Shapes.check! ref-shape ref)
  (local id (string.match ref.key (.. "^" (string.gsub scheme "%-" "%%-") ":([A-Za-z0-9_-]+)$")))
  (when (not id) (fail! :invalid-arguments "Invalid record reference"))
  id)
(fn summary! [value]
  (when (not (and (= (type value) :string) (utf8.len value)))
    (fail! :corrupt-data "Stored summary is not UTF-8 text"))
  (var end-byte (math.min 160 (length value)))
  (while (not (utf8.len (string.sub value 1 end-byte))) (set end-byte (- end-byte 1)))
  (string.sub value 1 end-byte))
(fn entry [entity] {:ref (ref-for "string-entity" entity.id) :summary (summary! entity.value)})
(fn written [entity] {:ref (ref-for "string-entity" entity.id) :revision entity.revision})
(fn read-dto [entity]
  (when (> (length entity.value) 65536) (fail! :limit-exceeded "Text exceeds capability byte limit"))
  {:ref (ref-for "string-entity" entity.id) :text entity.value :revision entity.revision})
(fn relation [entity]
  {:ref (ref-for "link-entity" entity.id) :source {:key entity.source-key} :target {:key entity.target-key}})

(fn failure [err write?]
  (if (and (= (type err) :table) err.code)
      {:ok false :error {:code err.code :message err.message
                         :outcome (if (not= err.outcome nil) err.outcome write? :unknown :not-committed)
                         :current-revision err.current-revision}}
      {:ok false :error {:code :internal-error :message "Entity operation failed"
                         :outcome (if write? :unknown :not-committed)}}))

;; Convert owning exceptions, including post-publication notifications, to the
;; declared DTO. Unexpected exceptions remain explicit and do not invent rollback.
(fn attempt [write? shape convert operation]
  (local (ok result) (pcall operation))
  (local structured? (and (= (type result) :table) result.code))
  (when (and (not ok) (not structured?))
    (lua "return failure(result, write_3f)"))
  (local raw (if ok result result.result))
  (var checked nil)
  (when (not= raw nil)
    (local (valid dto) (pcall (fn check-output [] (Shapes.check! shape (convert raw)))))
    (when (not valid)
      (local outcome (if (not write?) :not-committed
                         ok :committed
                         (= result.outcome :committed) :committed
                         (= result.outcome :not-committed) :not-committed
                         :unknown))
      (local code (if (and (= (type dto) :table) (= dto.code :limit-exceeded)) :limit-exceeded :invalid-result))
      (local output (failure {:code code :message "Entity result exceeds or violates declared bounds"
                             :outcome outcome} false))
      (lua "return output"))
    (set checked dto))
  (if ok {:ok true :value checked}
      (do (local output (failure result write?))
          (set output.error.result checked)
          output)))

(fn after-id! [cursor operation ref query]
  (when cursor
    (when (not= (string.sub cursor 1 3) "v1:") (fail! :invalid-arguments "Unknown page cursor version"))
    (local (ok data) (pcall json.loads (string.sub cursor 4)))
    (when (not ok) (fail! :invalid-arguments "Malformed page cursor"))
    (local checked (Shapes.check! cursor-shape data))
    (assert (and (= checked.operation operation) (= checked.key ref.key) (= checked.query query)
                 (string.match checked.after-id "^[A-Za-z0-9_-]+$"))
            {:code :invalid-arguments :message "Page cursor scope mismatch" :outcome :not-committed})
    checked.after-id))

(fn page [store operation ref args query scan-field convert]
  (local scan-opts {:limit (if (= args.limit nil) 20 args.limit) :examined-limit 200
                   :after-id (after-id! args.cursor operation ref query)})
  (when scan-field (set (. scan-opts scan-field) query))
  (local scanned (store:scan-page scan-opts))
  (local result {:items (icollect [_ entity (ipairs scanned.items)] (convert entity)) :has-more scanned.has-more})
  (when scanned.has-more
    (set result.cursor (.. "v1:" (json.dumps {:operation operation :key ref.key :query query :after-id scanned.last-id}))))
  result)

(fn identity [value] value)
(fn access-by-scheme [opts]
  (local strings (assert opts.string-store "Entity capabilities require string-store"))
  (local links (assert opts.link-store "Entity capabilities require link-store"))
  (local collection-ref {:key "string-entity-list"})
  (local relationships-ref {:key "link-entity-list"})
  (fn describe-collection [ref]
    (if (= ref.key collection-ref.key)
        {:ok true :value {:ref ref :summary "Stored texts" :capabilities collection-metadata}}
        {:ok false :error {:code :not-found :message "Collection not found" :outcome :not-committed}}))
  (fn describe-relationships [ref]
    (if (= ref.key relationships-ref.key)
        {:ok true :value {:ref ref :summary "Directed relationships" :capabilities relationship-metadata}}
        {:ok false :error {:code :not-found :message "Relationship provider not found" :outcome :not-committed}}))
  (fn describe-text [ref]
    (local (ok result) (pcall (fn read-description []
                              (local snapshot (strings:read-text (id! "string-entity" ref)))
                              {:ref ref :summary (summary! snapshot.value) :capabilities text-metadata})))
    (if ok {:ok true :value result} (failure result false)))
  (fn describe-link [ref]
    (local (ok result) (pcall (fn read-description []
                              (local entity (links:read-link (id! "link-entity" ref)))
                              (Shapes.check! relation-shape (relation entity))
                              {:ref ref :summary (summary! (.. entity.source-key " -> " entity.target-key)) :capabilities []})))
    (if ok {:ok true :value result} (failure result false)))
  (fn list-texts [ref args _pre]
    (attempt false (page-shape entry-shape) identity
      (fn scan [] (page strings "collection.list" ref args "" nil entry))))
  (fn search-texts [ref args _pre]
    (attempt false (page-shape entry-shape) identity
      (fn scan [] (page strings "collection.search" ref args args.query :query entry))))
  (fn create-text [_ref args _pre]
    (attempt true written-shape written (fn create [] (strings:create-entity {:value args.text}))))
  (fn read-text [ref _args _pre]
    (attempt false read-shape read-dto (fn read [] (strings:read-text (id! "string-entity" ref)))))
  (fn replace-text [ref args pre]
    (attempt true written-shape written
      (fn replace [] (strings:replace-text (id! "string-entity" ref) args.text pre.revision))))
  (fn list-relationships [ref args _pre]
    (attempt false (page-shape relation-shape) identity
      (fn scan [] (page links "relationships.list" ref args args.subject.key :key relation))))
  (fn create-relationship [_ref args _pre]
    (attempt true relation-shape relation
      (fn create [] (Relationships.create! strings links args.source args.target))))
  {:string-entity-list {:entry-points [{:ref collection-ref :summary "Stored texts"}]
                        :describe describe-collection
                        :handlers {"collection.list" list-texts "collection.search" search-texts "collection.create" create-text}}
   :string-entity {:entry-points [] :describe describe-text :handlers {"text.read" read-text "text.replace" replace-text}}
   :link-entity-list {:entry-points [{:ref relationships-ref :summary "Directed relationships"}]
                      :describe describe-relationships
                      :handlers {"relationships.list" list-relationships "relationships.create" create-relationship}}
   :link-entity {:entry-points [] :describe describe-link :handlers {}}})

{:access-by-scheme access-by-scheme}
