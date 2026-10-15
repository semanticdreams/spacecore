(local fs (require :fs))
(local Uuid (require :uuid))
(local Strings (require :entities/string))
(local Links (require :entities/link))
(local json (require :json))
(local runner (require :tests/runner))
(local FsTests (require :tests/test-fs))
(local tests [])

(fn test [name f] (table.insert tests {:name name :fn f}))
(fn with-root [f]
  (local root (fs.join-path "/tmp/space/tests" (.. "record-" (Uuid.v4))))
  (fs.create-dirs root)
  (local (ok result) (pcall f root))
  (fs.remove-all root)
  (when (not ok) (error result)))
(fn expect-error [code f]
  (local (ok err) (pcall f))
  (assert (not ok) (.. "expected " code))
  (assert (= (type err) :table) (tostring err))
  (assert (= err.code code) (.. "expected " code ", got " (tostring err.code)))
  err)
(fn string-store [root files]
  (Strings.StringEntityStore {:base-dir root :files files}))
(fn link-store [root files]
  (Links.LinkEntityStore {:base-dir root :files files}))
(fn text-path [store id] (fs.join-path store.entities-dir (.. id ".md")))

(fn fault-files [stage]
  (local Files (require :entities/record-files))
  (fn open [name mode]
    (if (and (= stage :open) (= mode "wb"))
        (values nil "open fault")
        (do
          (local handle (assert (io.open name mode)))
          {:write (fn write [_ text] (if (= stage :write) (values nil "write fault") (handle:write text)))
           :flush (fn flush [_] (if (= stage :flush) (values nil "flush fault") (handle:flush)))
           :close (fn close [_] (local result (handle:close)) (if (= stage :close) (values nil "close fault") result))
           :read (fn read [_ count] (if (= stage :verification) "wrong" (handle:read count)))})))
  (Files.RecordFiles {:open open
                     :rename (fn [from to] (if (= stage :rename) (values nil "rename fault") (os.rename from to)))}))

(fn check-denied-store [store]
  (assert (= (length (. (store:scan-page {}) :items)) 0))
  (store:create-entity {:value "must not disappear" :source-key "a" :target-key "b"})
  (fn denied []
    (expect-error :storage-failed (fn scan-denied [] (store:scan-page {}))))
  (FsTests.with-denied-directory store.entities-dir denied)
  (assert (= (length (. (store:scan-page {}) :items)) 1) "readable scan must recover"))

(test "permission-denied directory listing is an explicit storage failure"
  (fn denied-listing []
    (with-root (fn denied-root [root]
      (check-denied-store (string-store root))
      (check-denied-store (link-store root))))))

(test "replacement compares persisted state without publishing stale cached data"
  (fn persisted-comparison []
    (with-root (fn [root]
      (local store (string-store root))
      (local entity (store:create-entity {:value "A"}))
      (local before (store:read-text entity.id))
      (local reopened (string-store root))
      (reopened:replace-text entity.id "B" before.revision)
      (local err (expect-error :conflict (fn stale [] (store:replace-text entity.id "lost" before.revision))))
      (assert (= err.current-revision (. (reopened:read-text entity.id) :revision)))
      (assert (= entity.value "A") "conflict must not alter prior cached reference")
      (local current (store:read-text entity.id))
      (store:replace-text entity.id "C" current.revision)
      (assert (= entity.value "C"))))))

(fn exercise-stage-fault [root stage]
  (local Files (require :entities/record-files))
  (local good (string-store root))
  (local entity (good:create-entity {:value "before"}))
  (local path (text-path good entity.id))
  (local bytes (Files.read! path))
  ;; Prime a reference with the real boundary before injecting the write fault.
  ;; Faulty open/read/close seams affect only staging in this test wrapper.
  (local boundary (fault-files stage))
  (local store (string-store root {:read! Files.read! :list-ids Files.list-ids :remove! Files.remove!
                                  :write-text! boundary.write-text!}))
  (local cached (store:get-entity entity.id))
  (local err (expect-error :storage-failed
              (fn fault [] (store:replace-text entity.id "after" cached.revision))))
  (assert (= err.outcome :not-committed))
  (assert (= cached.value "before"))
  (assert (= cached.revision entity.revision))
  (assert (= (store:get-entity entity.id) cached))
  (assert (= bytes (Files.read! path)))
  (assert (= (length (fs.list-dir good.entities-dir false)) 1))
  (good:delete-entity entity.id))

(test "each text staging fault leaves the owning file cache and revision unchanged"
  (fn store-stage-faults []
    (with-root (fn [root]
      (each [_ stage (ipairs [:open :write :flush :close :verification :rename])]
        (exercise-stage-fault root stage))))))

(test "false and nonstring scan filters are not silently treated as omission"
  (fn invalid-filters []
    (with-root (fn [root]
      (local text (string-store root))
      (local links (link-store root))
      (expect-error :invalid-arguments (fn query [] (text:scan-page {:query false})))
      (expect-error :invalid-arguments (fn key [] (links:scan-page {:key false})))
      (expect-error :invalid-arguments (fn after [] (text:scan-page {:after-id false})))
      (expect-error :invalid-arguments (fn after-link [] (links:scan-page {:after-id false})))))))

(test "text snapshots preserve exact bytes and are detached"
  (fn exact-text []
    (with-root (fn [root]
      (local store (string-store root))
      (each [_ value (ipairs ["" "  \n\n hello \n \n" "a\r\nb\r\n" "雪 🐈" "---\nid: body\n---\n\n"])]
        (local entity (store:create-entity {:value value}))
        (local snapshot (store:read-text entity.id))
        (assert (= snapshot.value value))
        (set snapshot.value "detached")
        (assert (= (. (store:read-text entity.id) :value) value))
        (local reopened (string-store root))
        (assert (= (. (reopened:read-text entity.id) :value) value)))))))

(test "all updates advance revisions and stale ABA writes cannot publish"
  (fn revisions []
    (with-root (fn [root]
      (local store (string-store root))
      (local entity (store:create-entity {:value "A"}))
      (local first (store:read-text entity.id))
      (var revision first.revision)
      (each [_ changes (ipairs [{:value "A"} {:created-at 123} {:value "B"} {:value "A"}])]
        (assert (= (store:update-entity entity.id changes) entity) "cached reference must survive")
        (local current (store:read-text entity.id))
        (assert (not= revision current.revision))
        (set revision current.revision)
        (local reopened (string-store root))
        (assert (= (. (reopened:read-text entity.id) :revision) revision)))
      (local bytes (fs.read-file (text-path store entity.id)))
      (local err (expect-error :conflict (fn stale [] (store:replace-text entity.id "lost" first.revision))))
      (assert (= err.current-revision revision))
      (assert (= err.outcome :not-committed))
      (assert (= bytes (fs.read-file (text-path store entity.id))))
      (assert (= entity.value "A"))
      (local replaced (store:replace-text entity.id "new" revision))
      (assert (= replaced.value "new"))
      (assert (not= replaced.revision revision))
      (assert (= entity.value "new"))))))

(test "legacy tokens survive reopen without rewriting or trimming"
  (fn legacy []
    (with-root (fn [root]
      (local store (string-store root))
      (local path (text-path store "legacy"))
      (local bytes "---\nid: legacy\ncreated-at: 1\nupdated-at: 2\n---\n\n  body\r\n\n")
      (fs.write-file path bytes)
      (local first (store:read-text "legacy"))
      (assert (= first.value "  body\r\n\n"))
      (assert (= first.revision "legacy:legacy"))
      (local reopened (string-store root))
      (assert (= (. (reopened:read-text "legacy") :revision) first.revision))
      (assert (= bytes (fs.read-file path)))))))

(test "stores reject traversal identity revision overrides and collisions"
  (fn identities []
    (with-root (fn [root]
      (each [_ store (ipairs [(string-store root) (link-store root)])]
        (expect-error :invalid-arguments (fn traverse [] (store:create-entity {:id "../escape"})))
        (expect-error :invalid-arguments (fn traverse-read [] (store:get-entity "../escape")))
        (expect-error :invalid-arguments (fn forged-create [] (store:create-entity {:revision "fake"})))
        (local entity (store:create-entity {:id "fixed" :value "ok" :source-key "a" :target-key "b"}))
        (expect-error :conflict (fn collide [] (store:create-entity {:id "fixed"})))
        (expect-error :invalid-arguments (fn change-id [] (store:update-entity entity.id {:id "other"})))
        (expect-error :invalid-arguments (fn forge-revision [] (store:update-entity entity.id {:revision "fake"})))
        (assert (= (store:get-entity entity.id) entity)))))))

(test "store write faults preserve persisted bytes cached references and revisions"
  (fn write-faults []
    (with-root (fn [root]
      (local Files (require :entities/record-files))
      (each [_ factory (ipairs [string-store link-store])]
        (local fault {:active false})
        (local files {:read! Files.read! :list-ids Files.list-ids :remove! Files.remove!
                      :write-text! (fn write-text [path text]
                                     (if fault.active (error "injected write failure") (Files.write-text! path text)))
                      :write-json! (fn write-json [path data]
                                     (if fault.active (error "injected write failure") (Files.write-json! path data)))})
        (local store (factory root files))
        (local entity (store:create-entity {:value "before" :source-key "a" :target-key "b"}))
        (local revision entity.revision)
        (local before (factory root))
        (set fault.active true)
        (expect-error :storage-failed (fn fail-update [] (store:update-entity entity.id {:value "after" :source-key "c"})))
        (assert (= (store:get-entity entity.id) entity))
        (assert (= entity.revision revision))
        (assert (= entity.value (. (before:get-entity entity.id) :value)))
        (local reopened (factory root))
        (assert (= entity.source-key (. (reopened:get-entity entity.id) :source-key)))
        (expect-error :storage-failed (fn fail-create [] (store:create-entity {:id "failed"})))
        (assert (= (store:get-entity "failed") nil)))))))

(test "listener failures disclose committed owning results including link creation"
  (fn notifications []
    (with-root (fn [root]
      (each [_ spec (ipairs [[string-store :string-entity-created] [link-store :link-entity-created]])]
        (local factory (. spec 1))
        (local store (factory root))
        (local signal (. store (. spec 2)))
        (local listener (fn listener [_] (error "listener failed")))
        (signal:connect listener)
        (local (ok err) (pcall store.create-entity store {:value "committed" :source-key "a" :target-key "b"}))
        (signal:disconnect listener true)
        (assert (not ok))
        (assert (= err.code :notification-failed))
        (assert (= err.outcome :committed))
        (assert err.result.id)
        (local reopened (factory root))
        (assert (= (. (reopened:get-entity err.result.id) :id) err.result.id)))))))

(test "scans bound examined records and continue after nonmatches in filename order"
  (fn pagination []
    (with-root (fn [root]
      (each [_ store (ipairs [(string-store root) (link-store root)])]
        (each [_ id (ipairs ["c" "a" "b"])]
          (store:create-entity {:id id :value "literal .*" :source-key "x" :target-key "y"}))
        (local page (store:scan-page {:limit 1 :examined-limit 2 :query "absent" :key "absent"}))
        (assert (= (length page.items) 0))
        (assert (= page.examined 2))
        (assert (= page.last-id "b"))
        (assert page.has-more)
        (local final (store:scan-page {:after-id page.last-id :query "absent" :key "absent"}))
        (assert (= final.examined 1))
        (assert (not final.has-more))
        (local matched (store:scan-page {:query ".*" :key "x" :limit 1}))
        (assert (= (. matched.items 1 :id) "a"))
        (set (. matched.items 1 :id) "detached")
        (assert (= (. (store:get-entity "a") :id) "a"))
        (expect-error :invalid-arguments (fn zero-limit [] (store:scan-page {:limit 0})))
        (expect-error :limit-exceeded (fn over-limit [] (store:scan-page {:examined-limit 201}))))))))

(test "scans fail explicitly on corruption oversize unreadable records and listing faults"
  (fn corrupt-scans []
    (with-root (fn [root]
      (local Files (require :entities/record-files))
      (each [_ spec (ipairs [[string-store ".md"] [link-store ".json"]])]
        (local factory (. spec 1))
        (local store (factory root))
        (local path (fs.join-path store.entities-dir (.. "bad" (. spec 2))))
        (fs.write-file path "malformed")
        (expect-error :corrupt-data (fn corrupt [] (store:scan-page {})))
        (fs.write-file path (string.rep "x" 131073))
        (expect-error :limit-exceeded (fn oversized [] (store:scan-page {})))
        (fs.remove path)
        (local broken (factory root {:read! (fn unreadable [_ _max] (error "unreadable"))
                                    :list-ids (fn listed [_ _suffix] ["bad"])}))
        (expect-error :storage-failed (fn read-failure [] (broken:scan-page {})))
        (local unlisted (factory root {:list-ids (fn unlisted [_ _suffix] (error "listing failed"))}))
        (expect-error :storage-failed (fn listing-failure [] (unlisted:scan-page {})))
        (Files.write-text! path (if (= (. spec 2) ".md")
                                   "---\nid: bad\ncreated-at: 1\n---\n\nbody"
                                   "{\"id\":\"bad\",\"source-key\":\"x\",\"target-key\":\"y\",\"created-at\":1}"))
        (expect-error :corrupt-data (fn required-fields [] (store:scan-page {})))
        (Files.write-text! path (if (= (. spec 2) ".md")
                                   "---\nid: wrong\ncreated-at: 1\nupdated-at: 1\n---\n\nbody"
                                   "{\"id\":\"wrong\",\"source-key\":\"x\",\"target-key\":\"y\",\"created-at\":1,\"metadata\":{}}"))
        (expect-error :corrupt-data (fn mismatch [] (store:scan-page {})))
        (fs.remove path))))))

(test "checked record files isolate staging and preserve destination on every I/O fault"
  (fn checked-files []
    (with-root (fn [root]
      (local Files (require :entities/record-files))
      (local path (fs.join-path root "record"))
      (Files.write-text! path "before")
      (each [_ stage (ipairs [:open :write :flush :close :verification :rename])]
        (local boundary (fault-files stage))
        (expect-error :storage-failed (fn attempt [] (boundary.write-text! path "after")))
        (assert (= (Files.read! path) "before"))
        (assert (= (length (fs.list-dir root false)) 1) "only attempt staging may be cleaned"))
      (local broken-json (Files.RecordFiles {:stage-json! (fn truncate [stage _data] (Files.write-text! stage "{}"))}))
      (expect-error :storage-failed (fn attempt-json [] (broken-json.write-json! path {:value "after"})))
      (assert (= (Files.read! path) "before"))
      (Files.write-json! path {:value "雪"})
      (assert (= (. (json.loads (Files.read! path)) :value) "雪"))))))

(fn json-fault-files [stage]
  (local Files (require :entities/record-files))
  (local JsonUtils (require :json-utils))
  (fn stage-json! [path data]
    (if (= stage :stage)
        (do (Files.write-text! (.. path ".tmp") "partial") (error "JSON staging fault"))
        (= stage :verification) (Files.write-text! path "{}")
        (JsonUtils.write-json! path data)))
  (fn rename [from to]
    (if (= stage :rename) (values nil "JSON rename fault") (os.rename from to)))
  (Files.RecordFiles {:stage-json! stage-json! :rename rename}))

(fn check-json-store-fault [root stage]
  (local Files (require :entities/record-files))
  (local boundary (json-fault-files stage))
  (local store (link-store root boundary))
  (local good (link-store root))
  (local entity (good:create-entity {:source-key "a" :target-key "b" :metadata {:nested {:value "before"}}}))
  (local path (fs.join-path store.entities-dir (.. entity.id ".json")))
  (local bytes (Files.read! path))
  (local cached (store:get-entity entity.id))
  (expect-error :storage-failed
    (fn update-fault [] (store:update-entity entity.id {:metadata {:nested {:value "after"}}})))
  (assert (= (store:get-entity entity.id) cached))
  (assert (= cached.metadata.nested.value "before"))
  (assert (= bytes (Files.read! path)))
  (expect-error :storage-failed
    (fn create-fault [] (store:create-entity {:id "failed-json" :source-key "a" :target-key "b"})))
  (assert (= (store:get-entity "failed-json") nil))
  (assert (= (length (fs.list-dir store.entities-dir)) 1) "attempt-owned JSON staging must be cleaned")
  (good:delete-entity entity.id))

(test "JSON staging verification and rename faults preserve links and clean only attempt artifacts"
  (fn json-stage-faults []
    (with-root (fn json-root [root]
      (each [_ stage (ipairs [:stage :verification :rename])]
        (check-json-store-fault root stage))
      (local Files (require :entities/record-files))
      (local path (fs.join-path root "record.json"))
      (Files.write-json! path {:value "before"})
      (Files.write-text! (.. path ".tmp") "unrelated temporary")
      (local first (json-fault-files :rename))
      (expect-error :storage-failed (fn fail-first [] (first.write-json! path {:value "after"})))
      (expect-error :storage-failed (fn fail-again [] (first.write-json! path {:value "retry"})))
      (assert (= (Files.read! (.. path ".tmp")) "unrelated temporary"))
      (assert (= (length (fs.list-dir root)) 3) "only entities dir and original files should remain")))))

(test "link metadata inputs and scan results detach while updates preserve cached identity"
  (fn detached-links []
    (with-root (fn [root]
      (local store (link-store root))
      (local metadata {:nested {:value "original"}})
      (local entity (store:create-entity {:source-key "a" :target-key "b" :metadata metadata}))
      (set metadata.nested.value "caller changed")
      (assert (= entity.metadata.nested.value "original"))
      (local replacement {:nested {:value "updated"}})
      (assert (= (store:update-entity entity.id {:metadata replacement}) entity))
      (set replacement.nested.value "caller changed again")
      (local page (store:scan-page {:key "b"}))
      (assert (= (. page.items 1 :source-key) "a"))
      (assert (= (. page.items 1 :target-key) "b"))
      (set (. page.items 1 :metadata :nested :value) "page changed")
      (assert (= entity.metadata.nested.value "updated"))
      (local reopened (link-store root))
      (assert (= (. (reopened:get-entity entity.id) :metadata :nested :value) "updated"))))))

(fn check-notification [root factory event operation snapshot? force-assertion-failure?]
  (local store (factory root))
  (local entity (store:create-entity {:value "before" :source-key "a" :target-key "b"}))
  (local revision entity.revision)
  (local signal (. store event))
  (var listener-completed? false)
  (fn listener [committed]
    (assert (= committed entity) "existing signal argument identity must survive update/delete")
    (local reopened (factory root))
    (local saved (reopened:get-entity entity.id))
    (if (= operation :delete) (assert (= saved nil))
        (do
          (assert (= saved.id entity.id))
          (assert (= saved.value committed.value))
          (assert (= saved.source-key committed.source-key))
          (assert (= saved.revision committed.revision))))
    (assert (not force-assertion-failure?) "deliberate listener assertion failure")
    (set listener-completed? true)
    (error "postcommit listener fault"))
  (signal:connect listener)
  (fn mutate []
    (if (= operation :delete) (store:delete-entity entity.id)
        snapshot? (store:replace-text entity.id "committed" revision)
        (store:update-entity entity.id (if (= factory string-store)
                                          {:value "committed"}
                                          {:source-key "changed"}))))
  (local (ok err) (pcall mutate))
  (signal:disconnect listener true)
  (assert listener-completed? "listener assertions did not complete")
  (assert (not ok))
  (assert (= err.code :notification-failed))
  (assert (= err.outcome :committed))
  (assert (= err.result.id entity.id))
  (when snapshot? (assert (= err.result.created-at nil) "replacement error result is a snapshot"))
  (set err.result.id "detached")
  (assert (not= entity.id "detached")))

(test "update replacement and delete listener failures disclose committed detached results"
  (fn committed-notifications []
    (with-root (fn notification-root [root]
      (check-notification root string-store :string-entity-updated :update false)
      (check-notification root string-store :string-entity-updated :replace true)
      (check-notification root string-store :string-entity-deleted :delete false)
      (check-notification root link-store :link-entity-updated :update false)
      (check-notification root link-store :link-entity-deleted :delete false)))))

(test "notification test rejects listener assertion failures rather than mistaking them for the intended error"
  (fn notification-test-guard []
    (with-root (fn guard-root [root]
      (local (ok err) (pcall check-notification root string-store :string-entity-updated :replace true true))
      (assert (not ok) "notification helper swallowed a listener assertion failure")
      (assert (string.find (tostring err) "listener assertions did not complete" 1 true))))))

(test "failed deletes preserve files and cached records and do not emit"
  (fn failed-deletes []
    (with-root (fn delete-root [root]
      (local Files (require :entities/record-files))
      (each [_ spec (ipairs [[string-store :string-entity-deleted] [link-store :link-entity-deleted]])]
        (local factory (. spec 1))
        (local store (factory root {:read! Files.read! :write-text! Files.write-text! :write-json! Files.write-json!
                                   :remove! (fn remove-fault [_path] (error "remove failed"))}))
        (local entity (store:create-entity {:value "before" :source-key "a" :target-key "b"}))
        (local seen {:count 0})
        (local signal (. store (. spec 2)))
        (fn listener [_record] (set seen.count (+ seen.count 1)))
        (signal:connect listener)
        (local (ok err) (pcall store.delete-entity store entity.id))
        (signal:disconnect listener true)
        (assert (not ok))
        (assert (= err.code :storage-failed))
        (assert (= err.outcome :not-committed))
        (assert (= seen.count 0))
        (assert (= (store:get-entity entity.id) entity))
        (local reopened (factory root))
        (assert (= (. (reopened:get-entity entity.id) :id) entity.id)))))))

(fn check-page-defaults [store]
  (for [n 1 205]
    (store:create-entity {:id (string.format "item-%03d" n) :value "literal" :source-key "a" :target-key "b"}))
  (local first (store:scan-page {}))
  (assert (= (length first.items) 20))
  (assert (= first.examined 20))
  (assert (= first.last-id "item-020"))
  (local maximum (store:scan-page {:after-id first.last-id :limit 50 :examined-limit 200}))
  (assert (= (length maximum.items) 50))
  (assert (= maximum.last-id "item-070"))
  (local no-matches (store:scan-page {:query "absent" :key "absent"}))
  (assert (= no-matches.examined 200))
  (assert (= (length no-matches.items) 0))
  (assert (= no-matches.last-id "item-200"))
  (assert no-matches.has-more)
  (local tail (store:scan-page {:after-id no-matches.last-id :query "absent" :key "absent"}))
  (assert (= tail.examined 5))
  (assert (not tail.has-more))
  (local empty (store:scan-page {:after-id "item-205"}))
  (assert (= empty.examined 0))
  (assert (= empty.last-id nil))
  (assert (not empty.has-more))
  (expect-error :limit-exceeded (fn too-many [] (store:scan-page {:limit 51})))
  (expect-error :invalid-arguments (fn fractional [] (store:scan-page {:limit 1.5})))
  (expect-error :invalid-arguments (fn zero-examined [] (store:scan-page {:examined-limit 0}))))

(test "both stores enforce default and maximum item examined and continuation budgets"
  (fn page-defaults []
    (with-root (fn pages-root [root]
      (check-page-defaults (string-store root))
      (check-page-defaults (link-store root))))))

(fn check-byte-boundary [root]
  (local store (string-store root))
  (local entity (store:create-entity {:value ""}))
  (local path (text-path store entity.id))
  (local header-bytes (length (fs.read-file path)))
  (local value (string.rep "x" (- 131072 header-bytes)))
  (local current (store:replace-text entity.id value entity.revision))
  (assert (= (length (fs.read-file path)) 131072))
  (assert (= (. (store:read-text entity.id) :value) value))
  (assert (= (length (. (store:scan-page {}) :items)) 1))
  (local bytes (fs.read-file path))
  (local oversized (.. value "x"))
  (expect-error :limit-exceeded
    (fn over-budget [] (store:replace-text entity.id oversized current.revision)))
  (assert (= bytes (fs.read-file path)))
  (assert (= entity.revision current.revision))
  (local large (store:create-entity {:value (string.rep "x" 131072)}))
  (expect-error :limit-exceeded (fn over-read [] (store:read-text large.id))))

(test "capability stored-byte boundary includes headers and oversized replacement cannot publish"
  (fn byte-boundary [] (with-root check-byte-boundary)))

(test "same-second writes still receive distinct persisted revisions"
  (fn same-second []
    (with-root (fn [root]
      (local store (string-store root))
      (local entity (store:create-entity {:value "A"}))
      (var saw-same-second false)
      (for [_ 1 5]
        (local time entity.updated-at)
        (local revision entity.revision)
        (store:update-entity entity.id {:value "A"})
        (when (= entity.updated-at time) (set saw-same-second true))
        (assert (not= revision entity.revision)))
      (assert saw-same-second "fixture must exercise timestamp-equal writes, without rebinding os.time")))))

(test "invalid required link fields fail before publication"
  (fn invalid-link-data []
    (with-root (fn invalid-link-root [root]
      (local store (link-store root))
      (local entity (store:create-entity {:source-key "a" :target-key "b"}))
      (local path (fs.join-path store.entities-dir (.. entity.id ".json")))
      (local bytes (fs.read-file path))
      (local err (expect-error :invalid-arguments
                  (fn invalid-update [] (store:update-entity entity.id {:metadata "not a table"}))))
      (assert (= err.outcome :not-committed))
      (assert (= (store:get-entity entity.id) entity))
      (assert (= (type entity.metadata) :table))
      (assert (= bytes (fs.read-file path)))
      (expect-error :invalid-arguments
        (fn invalid-create [] (store:create-entity {:id "bad-fields" :source-key {}})))
      (assert (= (store:get-entity "bad-fields") nil))))))

(test "missing text preconditions are explicit and persisted collisions survive reopen"
  (fn missing-and-collisions []
    (with-root (fn missing-root [root]
      (local store (string-store root))
      (expect-error :not-found (fn missing-read [] (store:read-text "missing")))
      (expect-error :not-found (fn missing-replace [] (store:replace-text "missing" "value" "revision")))
      (local entity (store:create-entity {:id "persisted" :value "before"}))
      (expect-error :invalid-arguments (fn no-token [] (store:replace-text entity.id "after" nil)))
      (expect-error :invalid-arguments (fn empty-token [] (store:replace-text entity.id "after" "")))
      (expect-error :invalid-arguments (fn no-text [] (store:replace-text entity.id false entity.revision)))
      (local reopened (string-store root))
      (expect-error :conflict (fn collision [] (reopened:create-entity {:id "persisted" :value "lost"})))
      (assert (= (. (store:read-text entity.id) :value) "before"))
      (local links (link-store root))
      (links:create-entity {:id "persisted" :source-key "a" :target-key "b"})
      (local reopened-links (link-store root))
      (expect-error :conflict (fn link-collision [] (reopened-links:create-entity {:id "persisted"})))))))

(test "missing or non-directory owning paths fail scans instead of succeeding empty"
  (fn missing-directories []
    (with-root (fn missing-dir-root [root]
      (each [_ store (ipairs [(string-store root) (link-store root)])]
        (fs.remove-all store.entities-dir)
        (expect-error :storage-failed (fn missing [] (store:scan-page {})))
        (fs.write-file store.entities-dir "not a directory")
        (expect-error :storage-failed (fn not-directory [] (store:scan-page {}))))))))

(fn check-link-byte-budget [root]
  (local store (link-store root))
  (local entity (store:create-entity {:source-key "a" :target-key "b" :metadata {:payload ""}}))
  (local path (fs.join-path store.entities-dir (.. entity.id ".json")))
  (local overhead (length (fs.read-file path)))
  (local payload (string.rep "x" (- 131072 overhead)))
  (store:update-entity entity.id {:metadata {:payload payload}})
  (assert (= (length (fs.read-file path)) 131072))
  (assert (= (length (. (store:scan-page {}) :items)) 1))
  (assert (= (. (store:read-link entity.id) :metadata :payload) payload))
  (store:update-entity entity.id {:metadata {:payload (.. payload "x")}})
  (expect-error :limit-exceeded (fn link-read-oversized [] (store:read-link entity.id)))
  (expect-error :limit-exceeded (fn link-oversized [] (store:scan-page {}))))

(test "link scan byte budget is inclusive and counts serialized metadata"
  (fn link-byte-budget [] (with-root check-link-byte-budget)))

(test "checked bounded reads close handles and disclose read or close failure"
  (fn checked-reads []
    (with-root (fn read-root [root]
      (local Files (require :entities/record-files))
      (local path (fs.join-path root "record"))
      (Files.write-text! path "before")
      (each [_ stage (ipairs [:read :close])]
        (local state {:closed false})
        (fn open [name mode]
          (local handle (assert (io.open name mode)))
          {:read (fn read [_ count] (if (= stage :read) (values nil "read fault") (handle:read count)))
           :close (fn close [_]
                    (handle:close)
                    (set state.closed true)
                    (if (= stage :close) (values nil "close fault") true))})
        (local boundary (Files.RecordFiles {:open open}))
        (expect-error :storage-failed (fn failed-read [] (boundary.read! path 100)))
        (assert state.closed))
      (assert (= (Files.read! path 6) "before"))
      (expect-error :limit-exceeded (fn too-small [] (Files.read! path 5)))
      (expect-error :storage-failed (fn absent [] (Files.read! (fs.join-path root "missing"))))))))

(fn check-unsearchable-store [store]
  (store:create-entity {:value "not an empty page" :source-key "a" :target-key "b"})
  (fn unreadable-entries []
    (local entries (fs.list-dir store.entities-dir false))
    (assert (= (length entries) 1) "mode 0400 must allow name enumeration")
    (assert (. entries 1 :error) "mode 0400 must produce native per-entry stat errors")
    (assert (not (. entries 1 :is-file)))
    (expect-error :storage-failed (fn scan [] (store:scan-page {}))))
  (FsTests.with-denied-directory store.entities-dir unreadable-entries "400")
  (assert (= (length (. (store:scan-page {}) :items)) 1) "original mode must be restored"))

(test "read-without-search directories fail both store scans on native entry errors"
  (fn unsearchable-listing []
    (with-root (fn unsearchable-root [root]
      (check-unsearchable-store (string-store root))
      (check-unsearchable-store (link-store root))))))

(test "replacement reads are bounded from the first read and do not prime cache before failure"
  (fn bounded-replacement []
    (with-root (fn bounded-root [root]
      (local Files (require :entities/record-files))
      (local original (string-store root))
      (local entity (original:create-entity {:value "before"}))
      (local oversized (original:create-entity {:value (string.rep "x" 262144)}))
      (local reads {:count 0 :unbounded 0})
      (local fault {:active true})
      (fn read [path max-bytes]
        (set reads.count (+ reads.count 1))
        (if (= max-bytes nil)
            (set reads.unbounded (+ reads.unbounded 1))
            (assert (= max-bytes 131072)))
        (Files.read! path max-bytes))
      (fn write [path value]
        (assert (not fault.active) "injected write failure")
        (Files.write-text! path value))
      (local reopened (string-store root {:read! read :write-text! write}))
      (expect-error :storage-failed
        (fn failed-write [] (reopened:replace-text entity.id "attempt" entity.revision)))
      (expect-error :limit-exceeded
        (fn oversized-read [] (reopened:replace-text oversized.id "attempt" oversized.revision)))
      (assert (> reads.count 0))
      (assert (= reads.unbounded 0) "every replacement read, including the first, must be bounded")
      ;; A normal lookup must read again: neither failed replacement may prime cache.
      (local before reads.count)
      (assert (= (. (reopened:get-entity entity.id) :value) "before"))
      (assert (> reads.count before) "failed replacement published a record into cache")
      (local before-large reads.count)
      (assert (= (. (reopened:get-entity oversized.id) :revision) oversized.revision))
      (assert (> reads.count before-large) "oversized replacement published a record into cache")
      (set fault.active false)
      (set reads.unbounded 0)
      (local replaced (reopened:replace-text entity.id "committed" entity.revision))
      (assert (= replaced.value "committed"))
      (assert (= reads.unbounded 0))))))

(test "replacement of a cached record deleted through a reopened store is not-found without mutation"
  (fn cached-deletion []
    (with-root (fn deleted-root [root]
      (local store (string-store root))
      (local entity (store:create-entity {:value "cached"}))
      (local revision entity.revision)
      (local reopened (string-store root))
      (reopened:delete-entity entity.id)
      (local err (expect-error :not-found
                  (fn replace-deleted [] (store:replace-text entity.id "resurrected" revision))))
      (assert (= err.outcome :not-committed))
      (assert (not (fs.exists (text-path store entity.id))))
      (assert (= entity.value "cached"))
      (assert (= entity.revision revision))
      (assert (= (store:get-entity entity.id) entity))))))

(test "replacement preserves permission and read failures as storage-failed for existing records"
  (fn replacement-read-errors []
    (with-root (fn read-errors-root [root]
      (local store (string-store root))
      (local entity (store:create-entity {:value "unchanged"}))
      (local revision entity.revision)
      (fn denied []
        (local err (expect-error :storage-failed
                    (fn permission-error [] (store:replace-text entity.id "attempt" revision))))
        (assert (= err.outcome :not-committed)))
      (FsTests.with-denied-directory store.entities-dir denied)
      (local broken (string-store root {:read! (fn read-error [_path _maximum] (error "record read failed"))}))
      (local err (expect-error :storage-failed
                  (fn read-error [] (broken:replace-text entity.id "attempt" revision))))
      (assert (= err.outcome :not-committed))
      (assert (= entity.value "unchanged"))
      (assert (= entity.revision revision))
      (assert (= (. (store:read-text entity.id) :value) "unchanged"))))))

(test "long destination basenames publish text through short sibling staging"
  (fn long-text-destination []
    (with-root (fn long-root [root]
      (local Files (require :entities/record-files))
      (local text-path (fs.join-path root (.. (string.rep "t" 242) ".md")))
      (Files.write-text! text-path "before")
      (Files.write-text! text-path "  after 雪\r\n\n")
      (assert (= (Files.read! text-path) "  after 雪\r\n\n"))
      (assert (= (length (fs.list-dir root)) 1) "successful publication must leave no staging files")))))

(test "long destination basenames publish JSON through short sibling staging"
  (fn long-json-destination []
    (with-root (fn long-root [root]
      (local Files (require :entities/record-files))
      (local json-path (fs.join-path root (.. (string.rep "j" 242) ".json")))
      (Files.write-json! json-path {:value "before"})
      (Files.write-json! json-path {:value "after 雪"})
      (assert (= (. (json.loads (Files.read! json-path)) :value) "after 雪"))
      (assert (= (length (fs.list-dir root)) 1) "successful publication must leave no staging files")))))

(test "short staging names are attempt-unique siblings and cleanup preserves unrelated files"
  (fn short-staging-ownership []
    (with-root (fn stage-root [root]
      (local Files (require :entities/record-files))
      (local path (fs.join-path root (.. (string.rep "d" 242) ".json")))
      (local unrelated (fs.join-path root "record-stage-unrelated.tmp"))
      (Files.write-text! unrelated "unrelated")
      (local stages [])
      (fn rename [from to]
        (assert (= (fs.parent from) (fs.parent to)) "rename must stay in the destination directory")
        (assert (< (length from) (length to)) "staging basename must not extend the long destination basename")
        (table.insert stages from)
        (values nil "intentional rename failure"))
      (local boundary (Files.RecordFiles {:rename rename}))
      (expect-error :storage-failed (fn first [] (boundary.write-json! path {:value "first"})))
      (expect-error :storage-failed (fn second [] (boundary.write-json! path {:value "second"})))
      (assert (= (length stages) 2))
      (assert (not= (. stages 1) (. stages 2)))
      (assert (= (length (fs.list-dir root)) 1) "only each attempt's stage and JSON temporary may be cleaned")
      (assert (= (Files.read! unrelated) "unrelated"))))))

(test "text scans validate every examined body before applying a nonmatching query"
  (fn nonmatching-corruption []
    (with-root (fn corrupt-root [root]
      (local store (string-store root))
      (local value (string.char 255))
      (store:create-entity {:id "invalid-utf8" :value value})
      (assert (= (. (store:get-entity "invalid-utf8") :value) value) "legacy getter semantics remain unchanged")
      (local err (expect-error :corrupt-data (fn scan [] (store:scan-page {:query "absent literal"}))))
      (assert (= err.outcome :not-committed))))))

(test "bounded owning link reads are detached and bypass rather than populate the legacy cache"
  (fn detached-bounded-links []
    (with-root (fn bounded-root [root]
      (local Files (require :entities/record-files))
      (local original (link-store root))
      (local entity (original:create-entity {:id "bounded" :source-key "a" :target-key "b"
                                            :metadata {:payload "before"}}))
      (local reads {:count 0 :unbounded 0})
      (fn read [path maximum]
        (set reads.count (+ reads.count 1))
        (if (= maximum nil) (set reads.unbounded (+ reads.unbounded 1))
            (assert (= maximum 131072)))
        (Files.read! path maximum))
      (local cold (link-store root {:read! read}))
      (expect-error :not-found (fn missing [] (cold:read-link "missing")))
      (local snapshot (cold:read-link entity.id))
      (set snapshot.metadata.payload "caller changed")
      (assert (= (. (cold:read-link entity.id) :metadata :payload) "before"))
      (assert (= reads.count 2))
      (assert (= reads.unbounded 0))
      (local cached (cold:get-entity entity.id))
      (assert (= reads.count 3) "successful bounded reads must not prime legacy cache")
      (assert (= reads.unbounded 1) "legacy getter's unbounded semantics remain available")
      (original:update-entity entity.id {:metadata {:payload "after"}})
      (assert (= (. (cold:read-link entity.id) :metadata :payload) "after"))
      (assert (= (cold:get-entity entity.id) cached))
      (assert (= cached.metadata.payload "before"))
      (assert (= reads.unbounded 1))))))

(fn main [] (runner.run-tests {:name "entity-record-persistence" :tests tests}))
{:name "entity-record-persistence" :tests tests :main main}
