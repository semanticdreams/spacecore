(local fs (require :fs))
(local Uuid (require :uuid))
(local Strings (require :entities/string))
(local Links (require :entities/link))
(local json (require :json))
(local runner (require :tests/runner))
(local FsTests (require :tests/test-fs))
(local process (require :process))
(local tests [])

(fn test [name f] (table.insert tests {:name name :fn f}))
(fn create-fixture-dir! [path]
  (if (= (string.sub package.config 1 1) "/")
      (assert (= (. (process.run {:args ["mkdir" "-m" "700" path] :timeout 10}) :exit-code) 0)
              "fixture directory must be exclusively created private")
      (assert (fs.create-dir path) "fixture directory must be exclusive")))
(fn with-root [f]
  (local root (fs.join-path (if (= (string.sub package.config 1 1) "/") "/tmp"
                              ((. (require :appdirs) :tmp-dir))) (.. "record-" (Uuid.v4))))
  (create-fixture-dir! root)
  (local (ok result) (pcall f root))
  (fs.remove-all root)
  (when (not ok) (error (if (= (type result) :table) (json.dumps result) result))))
(fn expect-error [code f]
  (local (ok err) (pcall f))
  (assert (not ok) (.. "expected " code))
  (assert (= (type err) :table) (tostring err))
  (assert (= err.code code) (.. "expected " code ", got " (tostring err.code)))
  err)
(fn prepare-store-directory! [root kind]
  (each [_ child (ipairs ["entities" (.. "entities/" kind)])]
    (local path (fs.join-path root child))
    (when (not (fs.exists path)) (create-fixture-dir! path))))
(fn string-store [root files]
  (prepare-store-directory! root "string")
  (Strings.StringEntityStore {:base-dir root :files files}))
(fn link-store [root files]
  (prepare-store-directory! root "link")
  (Links.LinkEntityStore {:base-dir root :files files}))
(fn text-path [store id] (fs.join-path store.entities-dir (.. id ".md")))

(fn native-stage [parent]
  (local anchor (fs.join-path parent ".space-publication"))
  (local attempts (fs.list-dir anchor))
  (assert (= (length attempts) 1) "exactly one native attempt")
  (fs.join-path anchor (. attempts 1 :name) "record"))

(fn assert-clean-entries [parent names]
  (local expected [".space-publication"])
  (each [_ name (ipairs names)] (table.insert expected name))
  (local actual [])
  (each [_ entry (ipairs (fs.list-dir parent))] (table.insert actual entry.name))
  (table.sort expected)
  (table.sort actual)
  (assert (= (json.dumps actual) (json.dumps expected)) "exact entries must include intentional persistent anchor")
  (assert (= (length (fs.list-dir (fs.join-path parent ".space-publication"))) 0) "owned attempts must leave no residue"))

(fn check-write-completion [root factory operation cleanup? notification?]
  (local Files (require :entities/record-files))
  (local fault {:active false :cleanup-count 0})
  (fn cleanup-hook []
    (when fault.active
      (set fault.cleanup-count (+ fault.cleanup-count 1))
      (when cleanup? (error "completion cleanup fault")))
    true)
  (local store (factory root (Files.RecordFiles {:publication-hooks {:test-before-cleanup cleanup-hook}})))
  (local id (Uuid.v4))
  (local initial {:id id :value "before" :source-key "before" :target-key "target" :metadata {:nested {:value "before"}}})
  (local cached (when (not= operation :create) (store:create-entity initial)))
  (local revision (when cached cached.revision))
  (local event (if (= factory string-store)
                  (if (= operation :create) :string-entity-created :string-entity-updated)
                  (if (= operation :create) :link-entity-created :link-entity-updated)))
  (local observed {:calls 0 :completed false})
  (fn listener [entity]
    (set observed.calls (+ observed.calls 1))
    (assert (= fault.cleanup-count 1) "native cleanup must finish before cache notification")
    (assert (= (store:get-entity id) entity) "cache must publish before notification")
    (when cached (assert (= entity cached) "cached identity must survive"))
    (local reopened (factory root))
    (local saved (reopened:get-entity id))
    (if (= factory string-store)
        (do (assert (= saved.value entity.value "after"))
            (assert (= saved.revision entity.revision))
            (assert (not= entity.revision revision)))
        (do (assert (= saved.source-key entity.source-key))
            (assert (= (store.identity-store:resolve-key saved.source-key) "after"))
            (assert (= saved.metadata.nested.value "after"))))
    (set observed.completed true)
    (when notification? (error "completion notification fault")))
  (local signal (. store event))
  (signal:connect listener)
  (set fault.active true)
  (fn mutate []
    (if (= operation :create)
        (store:create-entity {:id id :value "after" :source-key "after" :target-key "target" :metadata {:nested {:value "after"}}})
        (= operation :replace) (store:replace-text id "after" revision)
        (store:update-entity id {:value "after" :source-key "after" :metadata {:nested {:value "after"}}})))
  (local (ok result) (pcall mutate))
  (signal:disconnect listener true)
  (assert observed.completed "completion listener assertions did not complete")
  (assert (= observed.calls 1) "normal notification must be attempted exactly once")
  (assert (= fault.cleanup-count 1))
  (assert (= ok (not (or cleanup? notification?))) "postcommit diagnostics must be disclosed")
  (when (or cleanup? notification?)
    (assert (= result.code (if cleanup? :storage-failed :notification-failed)))
    (assert (= result.outcome :committed))
    (when cleanup?
      (assert (= result.message (if notification? "Record committed; staging cleanup and notification failed."
                                   "Record committed; staging cleanup failed.")))
      (assert (string.find result.cleanup-error "completion cleanup fault" 1 true)))
    (when (and cleanup? notification?)
      (assert (string.find result.notification-error "completion notification fault" 1 true)))
    (assert (= result.result.id id))
    (local entity (store:get-entity id))
    (when (= factory string-store)
      (assert (= result.result.revision entity.revision))
      (assert (= result.result.value "after"))
      (assert (= (= result.result.created-at nil) (= operation :replace))))
    (when (= factory link-store)
      (set result.result.metadata.nested.value "detached")
      (assert (= entity.metadata.nested.value "after")))
    (set result.result.id "detached")
    (assert (= entity.id id))))

(test "write completion publishes bytes cache and revision before disclosing cleanup and notification errors"
  (fn write-completion []
    (with-root (fn completion-root [root]
      (each [_ spec (ipairs [[string-store :create] [string-store :update] [string-store :replace]
                            [link-store :create] [link-store :update]])]
        (each [_ faults (ipairs [[true false] [false true] [true true] [false false]])]
          (check-write-completion root (. spec 1) (. spec 2) (. faults 1) (. faults 2))))))))

(fn fault-files [stage parent]
  (local Files (require :entities/record-files))
  ;; These hooks perturb native phases, never implement a payload writer.
  ;; OS partial-write/completion failures are exercised by native RLIMIT_FSIZE;
  ;; store files injection separately proves owning-state failure invariants.
  (fn write-hook [] (if (= stage :before-write) (error "before-write fault") true))
  (fn security-hook []
    (if (= stage :verification) (fs.write-file (native-stage parent) "wrong")
        (= stage :security) (error "security fault"))
    true)
  (fn commit-hook [] (if (= stage :commit) (error "commit fault") true))
  (Files.RecordFiles {:publication-hooks {:test-before-write write-hook
                                         :test-before-security security-hook
                                         :test-before-commit commit-hook}}))

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
  ;; Native phase hooks affect publication, not reads of the persisted record.
  (local boundary (fault-files stage good.entities-dir))
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
  (good:retire-entity! entity.id))

(test "native text publication faults leave the owning file cache and revision unchanged"
  (fn store-stage-faults []
    (with-root (fn [root]
      (each [_ stage (ipairs [:before-write :verification :security :commit])]
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
                                    "{\"id\":\"bad\",\"source-key\":\"x\",\"target-key\":\"y\",\"created-at\":1,\"metadata\":false}"))
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
      (each [_ stage (ipairs [:before-write :verification :security :commit])]
        (local boundary (fault-files stage root))
        (expect-error :storage-failed (fn attempt [] (boundary.write-text! path "after")))
        (assert (= (Files.read! path) "before"))
        (assert-clean-entries root ["record"]))
      (local broken-json (fault-files :verification root))
      (expect-error :storage-failed (fn attempt-json [] (broken-json.write-json! path {:value "after"})))
      (assert (= (Files.read! path) "before"))
      (Files.write-json! path {:value "雪"})
      (assert (= (. (json.loads (Files.read! path)) :value) "雪"))))))

(fn check-json-store-fault [root stage]
  (local Files (require :entities/record-files))
  (local good (link-store root))
  (local boundary (fault-files stage good.entities-dir))
  (local store (link-store root boundary))
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
  (assert-clean-entries store.entities-dir [(.. entity.id ".json")])
  (good:retire-entity! entity.id))

(test "JSON staging verification security and commit faults preserve links and clean only attempt artifacts"
  (fn json-stage-faults []
    (with-root (fn json-root [root]
      (each [_ stage (ipairs [:before-write :verification :security :commit])]
        (check-json-store-fault root stage))
      (local Files (require :entities/record-files))
      (local path (fs.join-path root "record.json"))
      (Files.write-json! path {:value "before"})
      (Files.write-text! (.. path ".tmp") "unrelated temporary")
      (local first (fault-files :commit root))
      (expect-error :storage-failed (fn fail-first [] (first.write-json! path {:value "after"})))
      (expect-error :storage-failed (fn fail-again [] (first.write-json! path {:value "retry"})))
      (assert (= (Files.read! (.. path ".tmp")) "unrelated temporary"))
      (assert-clean-entries root ["entities" "record.json" "record.json.tmp"])))))

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
       (assert (= (store.identity-store:resolve-key (. page.items 1 :source-key)) "a"))
       (assert (= (store.identity-store:resolve-key (. page.items 1 :target-key)) "b"))
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
    (if (= operation :delete) (store:retire-entity! entity.id)
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
        (local (ok err) (pcall store.retire-entity! store entity.id))
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
           (assert (= mode "rb") "RecordFiles open injection is read-only")
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

(test "record writers never use read injection and reject removed path-writer options"
  (fn native-writer-boundary []
    (with-root (fn boundary-root [root]
      (local Files (require :entities/record-files))
      (local state {:reads 0})
      (fn open [path mode]
        (assert (= mode "rb") "publication must never open a Lua pathname writer")
        (set state.reads (+ state.reads 1))
        (io.open path mode))
      (local boundary (Files.RecordFiles {:open open}))
      (local path (fs.join-path root "record"))
      (boundary.write-text! path "native text")
      (boundary.write-json! path {:value "native JSON"})
      (assert (= state.reads 0) "native completion/readback does not depend on injected reads")
      (assert (= (. (json.loads (boundary.read! path)) :value) "native JSON"))
      (assert (= state.reads 1))
      (each [_ options (ipairs [{:stage-json! (fn obsolete [_ _data] true)} {:unknown true} {:open false}])]
        (local (ok err) (pcall Files.RecordFiles options))
        (assert (not ok) "removed/unknown options must not silently survive API migration")
        (assert err))
      (assert-clean-entries root ["record"])))))

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
      (reopened:retire-entity! entity.id)
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
      (assert-clean-entries root [(. (fs.stat text-path) :name)])))))

(test "long destination basenames publish JSON through short sibling staging"
  (fn long-json-destination []
    (with-root (fn long-root [root]
      (local Files (require :entities/record-files))
      (local json-path (fs.join-path root (.. (string.rep "j" 242) ".json")))
      (Files.write-json! json-path {:value "before"})
      (Files.write-json! json-path {:value "after 雪"})
      (assert (= (. (json.loads (Files.read! json-path)) :value) "after 雪"))
      (assert-clean-entries root [(. (fs.stat json-path) :name)])))))

(fn check-short-staging-ownership [root]
  (local Files (require :entities/record-files))
  (local basename (.. (string.rep "d" 242) ".json"))
  (local path (fs.join-path root basename))
  (local unrelated (fs.join-path root "record-stage-unrelated.tmp"))
  (Files.write-text! unrelated "unrelated")
  (local stages [])
  (local observed {:commits 0})
  (fn observe-write! []
    (local stage (native-stage root))
    (assert (< (length stage) (length path)) "native name must not extend long destination basename")
    (assert (= (Files.read! stage) "") "native record must start empty")
    (table.insert stages stage)
    true)
  (fn commit-hook []
    (set observed.commits (+ observed.commits 1))
    (error "intentional commit failure"))
  (local boundary (Files.RecordFiles {:publication-hooks {:test-before-write observe-write!
                                                        :test-before-commit commit-hook}}))
  (expect-error :storage-failed (fn first [] (boundary.write-json! path {:value "first"})))
  (expect-error :storage-failed (fn second [] (boundary.write-json! path {:value "second"})))
  (assert (= (length stages) 2) "both native attempts must finish ownership assertions")
  (assert (= observed.commits 2) "both checked writers must reach the intentional commit fault")
  (assert (not= (. stages 1) (. stages 2)))
  (assert-clean-entries root ["record-stage-unrelated.tmp"])
  (assert (= (Files.read! unrelated) "unrelated")))

(test "short private staging workspaces are attempt-unique siblings and preserve unrelated files"
  (fn short-staging-ownership [] (with-root check-short-staging-ownership)))

(test "short staging ownership accepts a trusted alias of the canonical destination directory"
  (fn aliased-staging-ownership []
    (when (= (string.sub package.config 1 1) "/")
      (with-root (fn alias-root [root]
        (local target (fs.join-path root "records"))
        (local alias (fs.join-path root "alias"))
        (create-fixture-dir! target)
        (local linked (process.run {:args ["ln" "-s" target alias] :timeout 10}))
        (assert (= linked.exit-code 0) linked.stderr)
        (assert (. (fs.stat alias) :is-symlink) "fixture must actually exercise an alias")
        (check-short-staging-ownership alias))))))

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

(fn assert-private-workspace! [stage]
  (assert (= (. (fs.stat (fs.parent stage)) :permissions) "rwx------") "workspace must be private while bytes exist")
  (assert (> (length (fs.read-file stage)) 0) "record must contain bytes during privacy inspection")
  (assert (= (. (fs.stat stage) :permissions) "rw-------") "native record must be private before content")
  (assert (= (length (fs.list-dir (fs.parent stage))) 1) "native attempt owns exactly one record"))

(fn check-final-fault [root phase fault]
  (local Files (require :entities/record-files))
  (local good (string-store root))
  (local original (good:create-entity {:value "before"}))
  (local path (text-path good original.id))
  (local bytes (Files.read! path))
  (local state {:stage nil :ran false})
  (fn alter-stage! []
    (set state.stage (native-stage good.entities-dir))
    (if (= fault :bytes) (fs.write-file state.stage "native must independently reject these bytes")
        (= fault :identity)
        (do (assert (os.rename state.stage (.. state.stage ".unowned")))
            (fs.write-file state.stage (Files.read! (.. state.stage ".unowned"))))
        (do
          (local changed (process.run {:args ["chmod" "750" (fs.parent state.stage)] :timeout 10}))
          (assert (= changed.exit-code 0) changed.stderr)))
    (set state.ran true)
    true)
  (local hooks {})
  (set (. hooks phase) alter-stage!)
  (local boundary (Files.RecordFiles {:publication-hooks hooks}))
  (local store (string-store root boundary))
  (local cached (store:get-entity original.id))
  (local err (expect-error :storage-failed
    (fn failed-final-validation [] (store:replace-text cached.id "after" cached.revision))))
  (assert state.ran (.. "fault must execute after the checked writer: " phase "/" fault " " (tostring err.message)))
  (assert (= err.outcome :not-committed))
  (assert (= (Files.read! path) bytes))
  (assert (= (store:get-entity cached.id) cached))
  (assert (= cached.value "before"))
  (assert (= cached.revision original.revision))
  (when (= fault :identity)
    (assert (= (Files.read! (.. state.stage ".unowned"))
                (Files.read! state.stage)) "native cleanup must not delete substituted or unrelated names")))

(test "native verification identity and workspace policy faults preserve owning state"
  (fn native-final-faults []
    ;; Identity attacks deliberately retain foreign entries. Give each attack
    ;; its own fixture instead of treating those protected entries as residue
    ;; belonging to a later attempt (or weakening the one-attempt assertion).
    (each [_ spec (ipairs [[:test-before-commit :bytes] [:test-before-security :identity]
                           [:test-before-commit :identity]])]
      (with-root (fn final-root [root] (check-final-fault root (. spec 1) (. spec 2)))))
    (when (= (string.sub package.config 1 1) "/")
      (with-root (fn workspace-root [root] (check-final-fault root :test-before-security :workspace))))))

(fn assert-confined-cached-get [store entity kind]
  (if (= kind :symbolic)
      (do
        (local err (expect-error :storage-failed (fn confined-get [] (store:get-entity entity.id))))
        (assert (= err.outcome :not-committed))
        (assert (string.find err.message "symlink unsupported" 1 true)))
      (assert (= (store:get-entity entity.id) entity))))

(test "unsafe destination links fail before publication without changing cache revision or referent"
  (fn unsafe-destinations []
    (when (= (string.sub package.config 1 1) "/")
      (with-root (fn links-root [root]
        (each [_ kind (ipairs [:symbolic :hard])]
          (local store (string-store root))
          (local entity (store:create-entity {:value "before"}))
          (local revision entity.revision)
          (local path (text-path store entity.id))
          (local referent (.. path ".referent"))
          (local bytes (fs.read-file path))
          (assert (os.rename path referent))
          (local args (if (= kind :symbolic) ["ln" "-s" referent path] ["ln" referent path]))
          (local linked (process.run {:args args :timeout 10}))
          (assert (= linked.exit-code 0) linked.stderr)
          (local err (expect-error :storage-failed
            (fn linked-replacement [] (store:replace-text entity.id "after" revision))))
          (assert (= err.outcome :not-committed))
          (assert-confined-cached-get store entity kind)
          (assert (= (. store.cache entity.id) entity) "confinement rejection must preserve held cache identity")
          (assert (= entity.value "before"))
          (assert (= entity.revision revision))
          (assert (= (fs.read-file referent) bytes))
          (assert (= (fs.read-file path) bytes))))))))

(fn privacy-hook [state parent kind]
  (fn inspect-native-record []
    (when state.inspect
      (assert-private-workspace! (native-stage parent))
      (tset state kind (+ (. state kind) 1)))
    true))

(fn privacy-root [root]
  ;; A plain file proves this child really has umask022; the parent is untouched.
  (local probe (fs.join-path root "umask-probe"))
  (fs.write-file probe "probe")
  (assert (= (. (fs.stat probe) :permissions) "rw-r--r--") "child must run with umask022")
  (local Files (require :entities/record-files))
  (local state {:inspect false :text-count 0 :json-count 0})
  (local text-boundary (Files.RecordFiles {:publication-hooks
    {:test-before-security (privacy-hook state (fs.join-path root "entities" "string") :text-count)}}))
  (local link-boundary (Files.RecordFiles {:publication-hooks
    {:test-before-security (privacy-hook state (fs.join-path root "entities" "link") :json-count)}}))
  (local text (string-store root text-boundary))
  (local link (link-store root link-boundary))
  (local entity (text:create-entity {:value "before"}))
  (local relation (link:create-entity {:source-key "a" :target-key "b"}))
  (local text-file (text-path text entity.id))
  (local link-file (fs.join-path link.entities-dir (.. relation.id ".json")))
  (each [_ path (ipairs [text-file link-file])]
    (assert (= (. (fs.stat path) :permissions) "rw-------") "acceptance must start from0600 records"))
  (set state.inspect true)
  (local replaced (text:replace-text entity.id " replacement 雪\r\n\n" entity.revision))
  (assert (= replaced.value " replacement 雪\r\n\n"))
  (assert (= (. (fs.stat text-file) :permissions) "rw-------"))
  (text:update-entity entity.id {:value "unconditional"})
  (assert (= entity.value "unconditional"))
  (assert (= (. (fs.stat text-file) :permissions) "rw-------"))
  (link:update-entity relation.id {:source-key "changed"})
  (assert (= (link.identity-store:resolve-key relation.source-key) "changed"))
  (assert (= (. (fs.stat link-file) :permissions) "rw-------"))
  (assert (= state.text-count 2))
  (assert (= state.json-count 1))
  ;; Ordinary constructors also work under a secure newly-created userdata
  ;; ancestry; the acceptance fixture must not hide a production-only failure.
  (local ordinary-root (fs.join-path root "ordinary-userdata"))
  (local ordinary-text (Strings.StringEntityStore {:base-dir ordinary-root}))
  (local ordinary-link (Links.LinkEntityStore {:base-dir ordinary-root}))
  (local ordinary (ordinary-text:create-entity {:value "ordinary"}))
  (assert (= (. (ordinary-text:read-text ordinary.id) :value) "ordinary"))
  (ordinary-link:create-entity {:source-key "a" :target-key "b"}))

(fn privacy-child-main []
  (with-root privacy-root)
  ;; The parent gives this child a fresh private XDG root. Exercise production
  ;; defaults, not only the explicitly preprepared owning fixtures above.
  (local text (Strings.StringEntityStore))
  (local link (Links.LinkEntityStore))
  (local entity (text:create-entity {:value "default userdata"}))
  (assert (= (. (text:read-text entity.id) :value) "default userdata"))
  (local relation (link:create-entity {:source-key "default:a" :target-key "default:b"}))
  (assert (= (link.identity-store:resolve-key (. (link:read-link relation.id) :source-key)) "default:a"))
  (print "record privacy child: umask022, private intermediates and0600 replacements passed"))

(fn exercise-production-stores [text link]
  (local entity (text:create-entity {:value "before 雪"}))
  (local relation (link:create-entity {:source-key "a" :target-key "b"}))
  (local first entity.revision)
  (text:update-entity entity.id {:value "updated"})
  (assert (not= first entity.revision))
  (local replaced (text:replace-text entity.id " replacement 雪\r\n\n" entity.revision))
  (assert (= replaced.value " replacement 雪\r\n\n"))
  (link:update-entity relation.id {:source-key "changed"})
  (assert (= (. (text:read-text entity.id) :value) replaced.value))
  (assert (= (link.identity-store:resolve-key (. (link:read-link relation.id) :source-key)) "changed"))
  (assert (= (. (fs.stat (text-path text entity.id)) :permissions) "rw-------"))
  (assert (= (. (fs.stat (fs.join-path link.entities-dir (.. relation.id ".json"))) :permissions) "rw-------")))

(fn ordinary-default-child-main []
  (with-root (fn ordinary-custom-root [root]
    (local home (fs.join-path root "home"))
    (local inner (fs.join-path home ".local"))
    (fs.create-dirs inner)
    (assert (= (. (process.run {:args ["chmod" "750" home] :timeout 10}) :exit-code) 0))
    (assert (= (. (process.run {:args ["chmod" "775" inner] :timeout 10}) :exit-code) 0))
    (exercise-production-stores (Strings.StringEntityStore {:base-dir inner}) (Links.LinkEntityStore {:base-dir inner}))
    (assert (= (. (fs.stat home) :permissions) "rwxr-x---"))
    (assert (= (. (fs.stat inner) :permissions) "rwxrwxr-x"))))
  (exercise-production-stores (Strings.StringEntityStore) (Links.LinkEntityStore))
  (print "record default child: ordinary userdata succeeds"))

(fn run-publication-child! [userdata mask entrypoint marker]
  (local child (process.run
    {:args ["sh" "-c" "umask \"$1\"; exec \"$2\" -m \"$3\"" "record-privacy" mask
            ((. (require :tests/runtime-bin) :resolve)) (.. "tests.test-entity-record-persistence:" entrypoint)]
     :env {:SPACE_DISABLE_AUDIO "1" :SKIP_KEYRING_TESTS "1" :XDG_DATA_HOME userdata
           :SPACE_ASSETS_PATH (os.getenv "SPACE_ASSETS_PATH") :FENNEL_PATH (os.getenv "FENNEL_PATH")
           :FENNEL_MACRO_PATH (os.getenv "FENNEL_MACRO_PATH")}
     :timeout 60}))
  (assert (= child.exit-code 0) (.. child.stdout child.stderr))
  (assert (string.find child.stdout marker 1 true) "child must complete its assertions"))

(test "POSIX child umask022 protects text replacement unconditional update and JSON intermediates"
  (fn child-privacy []
    (if (not= (string.sub package.config 1 1) "/")
        (print "record privacy child: NOT APPLICABLE (non-POSIX; portable publication tests still run)")
        (do
          (local before (process.run {:args ["sh" "-c" "umask"] :timeout 10}))
          (with-root (fn child-userdata [root]
            (run-publication-child! root "022" "privacy-child-main" "record privacy child: umask022")))
          (each [_ mask (ipairs ["022" "002"])]
            (with-root (fn ordinary-userdata [root]
              (run-publication-child! root mask "ordinary-default-child-main" "ordinary userdata succeeds"))))
          (local after (process.run {:args ["sh" "-c" "umask"] :timeout 10}))
          (assert (= before.exit-code after.exit-code 0))
          (assert (= before.stdout after.stdout) "parent umask must not change")))))

(fn results-root [root]
  (local Files (require :entities/record-files))
  (local path (fs.join-path root "record"))
  (fn cleanup-fault [] (collectgarbage :collect) (error "writer cleanup fault"))
  (local boundary (Files.RecordFiles {:publication-hooks {:test-before-cleanup cleanup-fault}}))
  (each [_ writer (ipairs [(fn text [] (boundary.write-text! path "text"))
                          (fn data [] (boundary.write-json! path {:value "JSON"}))])]
    (local (written cleanup-error) (writer))
    (assert (= written true))
    (assert (string.find cleanup-error "writer cleanup fault" 1 true))
    (assert-clean-entries root ["record"]))
  (assert (= (. (json.loads (Files.read! path)) :value) "JSON"))
  (local (written cleanup-error) (Files.write-text! path "success"))
  (assert (= written true))
  (assert (= cleanup-error nil)))

(test "RecordFiles writers preserve true first result and forward committed cleanup diagnostics"
  (fn writer-results [] (with-root results-root)))

(test "legacy frozen text replay preserves absent revision and only reconciliation updates held objects"
  (fn legacy-frozen []
    (with-root (fn frozen-root [root]
      (local store (string-store root))
      (local held (store:create-entity {:id "frozen" :value "ordinary"}))
      (local revision held.revision)
      (local before (store:snapshot-entity held.id))
      (local bytes "---\nupdated-at: 2\nid: frozen\ncreated-at: 1\n---\n\n  legacy\r\n\n")
      (local decoded (store:decode-entity bytes))
      (assert (= decoded.revision nil) "effective legacy tokens do not belong in owning records")
      (assert (= (store:serialize-entity decoded) "---\nid: frozen\ncreated-at: 1\nupdated-at: 2\n---\n\n  legacy\r\n\n"))
      (var emissions 0)
      (fn observed [_] (set emissions (+ emissions 1)))
      (local handler (store.string-entity-updated:connect observed))
      (store:persist-entity! held.id bytes bytes)
      (assert (= (fs.read-file before.path) bytes))
      (assert (= held.value "ordinary"))
      (assert (= held.revision revision))
      (assert (= emissions 0) "frozen persistence must not publish cache or signals")
      (store:reconcile-entity! held.id bytes before.check bytes)
      (store.string-entity-updated:disconnect handler true)
      (assert (= (store:get-entity held.id) held))
      (assert (= held.revision nil) "reconciliation must clear an optional revision absent in the after-image")
      (assert (= held.value "  legacy\r\n\n"))
      (assert (= emissions 1))
      (assert (= (. (store:read-text held.id) :revision) "legacy:frozen"))
      (expect-error :conflict (fn stale [] (store:replace-text held.id "lost" revision)))
      (store:update-entity held.id {:value "ordinary again"})
      (assert (and held.revision (not= held.revision revision) (not= held.revision "legacy:frozen")))))))

(test "frozen link persistence never normalizes endpoints or publishes before reconciliation"
  (fn frozen-link []
    (with-root (fn frozen-root [root]
      (local store (link-store root))
      (local held (store:create-entity {:id "frozen-link" :source-key "a" :target-key "b"}))
      (local before (store:snapshot-entity held.id))
      (local original held.source-key)
      (local bytes (json.dumps {:id held.id :source-key "legacy:raw" :target-key "identity:missing"
                               :created-at 123 :metadata {}}))
      (local R (require :reference-lifecycle/record-utils))
      (local check (R.check-bytes bytes "json"))
      (local ensure store.identity-store.ensure-key)
      (set store.identity-store.ensure-key (fn forbidden [& _] (error "frozen replay must not normalize")))
      (local (ok err) (pcall store.persist-entity! store held.id bytes check))
      (set store.identity-store.ensure-key ensure)
      (assert ok (tostring err))
      (assert (= (fs.read-file before.path) bytes) "persist the exact submitted frozen bytes")
      (assert (= held.source-key original))
      (store:reconcile-entity! held.id bytes before.check check)
      (assert (= held.source-key "legacy:raw"))
      (assert (= held.target-key "identity:missing"))
      (assert (= (store:get-entity held.id) held))))))

(fn check-invalid-link [store path bytes fragment]
  (fs.write-file path bytes)
  (each [_ operation (ipairs [(fn bounded-read [] (store:read-link "invalid"))
                              (fn bounded-scan [] (store:scan-page {}))
                              (fn owning-snapshot [] (store:snapshot-entity "invalid"))
                              (fn ordinary-get [] (store:get-entity "invalid"))])]
    (local err (expect-error :corrupt-data operation))
    (assert (= err.outcome :not-committed))
    (assert (string.find err.message path 1 true) "owning read failure must identify its path")
    (assert (string.find err.message fragment 1 true) "owning read failure must identify its invalid field"))
  (assert (= (. store.cache "invalid") nil))
  (assert (= (fs.read-file path) bytes)))

(test "link reads reject present false null wrong types and mismatched IDs with structured context"
  (fn invalid-optional-link-fields []
    (with-root (fn invalid-root [root]
      (local store (link-store root))
      (local path (fs.join-path store.entities-dir "invalid.json"))
      (each [_ spec (ipairs [["source-key" "{}"] ["target-key" "3"]
                             ["created-at" "\"bad\""] ["metadata" "\"bad\""]])]
        (local field (. spec 1))
        (each [_ raw (ipairs ["false" "null" (. spec 2)])]
          (check-invalid-link store path (.. "{\"id\":\"invalid\",\"" field "\":" raw "}")
                              (if (= raw "null") "null" field))))
      (check-invalid-link store path "{\"id\":\"other\"}" "id")))))

(test "lifecycle error assertions read raw scalar messages without table metamethods"
  (fn raw-error-messages []
    (local H (require :tests/test-reference-lifecycle-helpers))
    (fn forbidden [& _] (error "error inspection must not invoke metamethods"))
    (local err (setmetatable {:code :corrupt-data :message "raw field context" :result {}}
                             {:__index forbidden :__tostring forbidden}))
    (assert (= (H.assert-error "field context" (fn structured [] (error err))) "raw field context"))
    (assert (= (H.assert-error "plain scalar" (fn scalar [] (error "plain scalar" 0))) "plain scalar"))))

(each [_ record-test (ipairs (. (require :tests/test-record-file-types) :tests))]
  (table.insert tests record-test))
(fn main [] (runner.run-tests {:name "entity-record-persistence" :tests tests}))
{:name "entity-record-persistence" :tests tests :main main
 :privacy-child-main privacy-child-main :ordinary-default-child-main ordinary-default-child-main}
