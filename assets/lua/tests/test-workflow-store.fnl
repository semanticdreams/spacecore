(local fs (require :fs))
(local json (require :json))
(local appdirs (require :appdirs))

(local tests [])
(var temp-counter 0)
(local temp-root (fs.join-path "/tmp/space/tests" "workflow-store"))
(var current-temp-user-data-dir nil)

(fn temp-user-data-dir [_appname]
  current-temp-user-data-dir)

(fn make-temp-dir []
  (set temp-counter (+ temp-counter 1))
  (fs.join-path temp-root (.. "store-" (os.time) "-" temp-counter)))

(fn with-temp-dir [f]
  (local dir (make-temp-dir))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (fs.create-dirs dir)
  (local (ok result) (pcall f dir))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (if ok
      result
      (error result)))

(fn with-temp-store [f]
  (with-temp-dir
    (fn [root]
      (local {: WorkflowStore} (require :workflows/store))
      (local store (WorkflowStore {:base-dir root}))
      (f store root))))

(fn with-temp-user-data-dir [f]
  (with-temp-dir
    (fn [root]
      (assert appdirs "appdirs module must be available")
      (local original appdirs.user-data-dir)
      (set current-temp-user-data-dir root)
      (set appdirs.user-data-dir temp-user-data-dir)
      (local (ok result) (pcall f root))
      (set current-temp-user-data-dir nil)
      (set appdirs.user-data-dir original)
      (if ok
          result
          (error result)))))

(fn assert-file-json [path message]
  (assert (fs.exists path) message)
  (json.loads (fs.read-file path)))

(fn assert-not-path-owned-by-world-or-graph-map [path]
  (assert (not (string.find path "world-123" 1 true)) "workflow path must not contain world id")
  (assert (not (string.find path "graph-map-456" 1 true)) "workflow path must not contain graph-map id"))

(fn connect-count [store signal-name counts key]
  (local signal (. store signal-name))
  (local handler (fn [_payload]
                   (local current (if (= (. counts key) nil) 0 (. counts key)))
                   (set (. counts key) (+ current 1))))
  (signal:connect handler)
  {:signal signal :handler handler})

(fn disconnect-signal-handlers [records]
  (each [_ record (ipairs records)]
    (record.signal:disconnect record.handler true)))

(fn exercise-signal-emitting-mutations [store]
  (local definition (store:create-definition {:name "signals"
                                              :steps [{:id "step-signals"
                                                       :name "step"
                                                       :code-entity-id "code-signals"}]}))
  (store:update-definition definition.id {:description "updated"})
  (local run (store:create-run definition.id {} {}))
  (store:update-run run.id {:status :running})
  (store:upsert-run-step run.id "step-signals" {:status :running})
  (store:append-event run.id {:kind :started})
  (store:delete-definition definition.id {}))

(fn assert-signal-counts [counts]
  (assert (= counts.definition-created 1) "definition-created signal should emit once")
  (assert (= counts.definition-updated 1) "definition-updated signal should emit once")
  (assert (= counts.definition-deleted 1) "definition-deleted signal should emit once")
  (assert (= counts.run-updated 1) "run-updated signal should emit once")
  (assert (= counts.run-step-updated 1) "run-step-updated signal should emit once")
  (assert (= counts.event-appended 1) "event-appended signal should emit once"))

(fn workflow-store-persists-definitions-app-scoped []
  (with-temp-store
    (fn [store root]
      (local definition (store:create-definition {:name "App scoped workflow"
                                                  :description "durable"}))
      (assert definition.id "definition should have id")
      (assert (= (string.sub definition.id 1 3) "wf-") "definition id should use wf- prefix")
      (assert (= definition.name "App scoped workflow") "definition name should persist")
      (assert (= (length definition.steps) 0) "definition starts with no steps")
      (assert (= (length definition.edges) 0) "definition starts with no edges")
      (local definition-path (fs.join-path root "workflows" "definitions" (.. definition.id ".json")))
      (assert-not-path-owned-by-world-or-graph-map definition-path)
      (local persisted (assert-file-json definition-path "definition should persist under workflows/definitions"))
      (assert (= persisted.id definition.id) "persisted definition id should match")
      (local workflow-module (require :workflows/store))
      (local reloaded-store (workflow-module.WorkflowStore {:base-dir root}))
      (local reloaded (reloaded-store:get-definition definition.id))
      (assert (= reloaded.id definition.id) "definition should reload by id")
      (assert (= (length (reloaded-store:list-definitions)) 1) "definition list should include persisted definition")
      (local updated (store:update-definition definition.id {:status :active :parameters {:topic "demo"}}))
      (assert (= updated.status :active) "definition status should update")
      (assert (= updated.parameters.topic "demo") "definition parameters should update")
      (local deleted (store:delete-definition definition.id {}))
      (assert (= deleted.id definition.id) "delete-definition should return deleted definition")
      (assert (= (store:get-definition definition.id) nil) "deleted definition should not be returned"))))

(fn workflow-store-creates-updates-steps-and-edges []
  (with-temp-store
    (fn [store _root]
      (local definition (store:create-definition {:name "steps"}))
      (local (missing-code-ok _) (pcall store.add-step store definition.id {:name "missing code"}))
      (assert (not missing-code-ok) "steps must require :code-entity-id")
      (local first-step (store:add-step definition.id {:name "first" :code-entity-id "code-first"}))
      (local second-step (store:add-step definition.id {:name "second" :code-entity-id "code-second" :config {:limit 1}}))
      (assert (= (string.sub first-step.id 1 5) "step-") "step id should use step- prefix")
      (assert (= second-step.config.limit 1) "step config should persist")
      (local updated-step (store:update-step definition.id first-step.id {:name "renamed" :retry {:max-attempts 2}}))
      (assert (= updated-step.name "renamed") "step name should update")
      (assert (= updated-step.retry.max-attempts 2) "step retry should update")
      (local edge (store:add-edge definition.id {:source-step-id first-step.id :target-step-id second-step.id}))
      (assert (= (string.sub edge.id 1 5) "edge-") "edge id should use edge- prefix")
      (assert (= edge.kind :control) "edge kind should default to control")
      (local updated-edge (store:update-edge definition.id edge.id {:kind :data :source-port "result" :target-port "input"}))
      (assert (= updated-edge.kind :data) "edge kind should update")
      (assert (= updated-edge.source-port "result") "edge source port should update")
      (local deleted-edge (store:delete-edge definition.id edge.id))
      (assert (= deleted-edge.id edge.id) "delete-edge should return deleted edge")
      (local definition-after-delete (store:get-definition definition.id))
      (assert (= (length definition-after-delete.edges) 0) "edge should be removed from definition"))))

(fn workflow-store-delete-step-requires-dependent-edge-decision []
  (with-temp-store
    (fn [store _root]
      (local definition (store:create-definition {:name "delete"}))
      (local first-step (store:add-step definition.id {:name "first" :code-entity-id "code-first"}))
      (local second-step (store:add-step definition.id {:name "second" :code-entity-id "code-second"}))
      (local edge (store:add-edge definition.id {:source-step-id first-step.id :target-step-id second-step.id}))
      (local run (store:create-run definition.id {} {}))
      (store:upsert-run-step run.id first-step.id {:status :succeeded :output {:value 1}})
      (local (ok _) (pcall store.delete-step store definition.id first-step.id {}))
      (assert (not ok) "delete-step should require explicit dependent edge decision")
      (local deleted-step (store:delete-step definition.id first-step.id {:delete-dependent-edges? true}))
      (assert (= deleted-step.id first-step.id) "delete-step should return deleted step")
      (local updated-definition (store:get-definition definition.id))
      (assert (= (length updated-definition.edges) 0) "dependent definition edges should be removed")
      (local historical-run-step (store:get-run-step run.id first-step.id))
      (assert (= historical-run-step.output.value 1) "existing run history should remain intact"))))

(fn workflow-store-persists-runs-steps-events-and-waits []
  (with-temp-store
    (fn [store root]
      (local definition (store:create-definition {:name "runs"}))
      (local step (store:add-step definition.id {:name "wait" :code-entity-id "code-wait"}))
      (local run (store:create-run definition.id {:prompt "go"} {:world-id "world-123" :graph-map-id "graph-map-456"}))
      (assert (= (string.sub run.id 1 4) "wfr-") "run id should use wfr- prefix")
      (assert (= run.context.world-id "world-123") "run context may record world id")
      (local run-path (fs.join-path root "workflows" "runs" (.. run.id ".json")))
      (assert-not-path-owned-by-world-or-graph-map run-path)
      (local run-step (store:upsert-run-step run.id step.id {:status :waiting
                                                             :attempt 1
                                                             :wait {:kind :human-input :request {:prompt "continue?"}}
                                                             :state {:token "abc"}}))
      (assert (= run-step.status :waiting) "run-step status should persist")
      (assert (= run-step.wait.kind :human-input) "run-step wait should persist")
      (local event (store:append-event run.id {:kind :step-waiting :step-id step.id :data {:reason "human"}}))
      (assert (= (string.sub event.id 1 6) "event-") "event id should use event- prefix")
      (local persisted-run (assert-file-json run-path "run should persist under workflows/runs"))
      (assert (= persisted-run.id run.id) "persisted run id should match")
      (assert persisted-run.steps "run JSON should contain nested steps")
      (assert persisted-run.events "run JSON should contain nested events")
      (local workflow-module (require :workflows/store))
      (local reloaded-store (workflow-module.WorkflowStore {:base-dir root}))
      (local reloaded-run (reloaded-store:get-run run.id))
      (local reloaded-run-step (reloaded-store:get-run-step run.id step.id))
      (assert (= reloaded-run.input.prompt "go") "run should reload by id")
      (assert (= reloaded-run-step.wait.request.prompt "continue?") "run-step wait should reload")
      (assert (= (length (reloaded-store:list-run-steps run.id)) 1) "run-step list should reload")
      (assert (= (length (reloaded-store:list-events run.id)) 1) "event list should reload")
      (assert (= (length (reloaded-store:list-runs {:definition-id definition.id})) 1) "run list should filter by definition id")
      (local updated-run (store:update-run run.id {:status :waiting :current-step-ids [step.id]}))
      (assert (= updated-run.status :waiting) "run status should update"))))

(fn workflow-store-signals-fire []
  (with-temp-store
    (fn [store _root]
      (local counts {})
      (local records [(connect-count store :definition-created counts :definition-created)
                      (connect-count store :definition-updated counts :definition-updated)
                      (connect-count store :definition-deleted counts :definition-deleted)
                      (connect-count store :run-updated counts :run-updated)
                      (connect-count store :run-step-updated counts :run-step-updated)
                      (connect-count store :event-appended counts :event-appended)])
      (exercise-signal-emitting-mutations store)
      (disconnect-signal-handlers records)
      (assert-signal-counts counts))))

(fn workflow-store-update-definition-rejects-invalid-steps []
  (with-temp-store
    (fn [store root]
      (local definition (store:create-definition {:name "metadata only"}))
      (local (ok _) (pcall store.update-definition store definition.id {:steps [{:id "bad-step" :name "bad"}]}))
      (assert (not ok) "update-definition should reject steps missing :code-entity-id")
      (local persisted (assert-file-json (fs.join-path root "workflows" "definitions" (.. definition.id ".json"))
                                         "definition should still persist"))
      (assert (= (length persisted.steps) 0) "invalid definition step update must not persist"))))

(fn workflow-store-update-step-rejects-id-changes []
  (with-temp-store
    (fn [store _root]
      (local definition (store:create-definition {:name "immutable step ids"}))
      (local first-step (store:add-step definition.id {:id "step-a" :name "first" :code-entity-id "code-first"}))
      (local second-step (store:add-step definition.id {:id "step-b" :name "second" :code-entity-id "code-second"}))
      (store:add-edge definition.id {:id "edge-a-b" :source-step-id first-step.id :target-step-id second-step.id})
      (local (ok _) (pcall store.update-step store definition.id first-step.id {:id "renamed"}))
      (assert (not ok) "update-step should reject :id changes")
      (local updated-definition (store:get-definition definition.id))
      (local updated-first-step (. updated-definition.steps 1))
      (local updated-edge (. updated-definition.edges 1))
      (assert (= updated-first-step.id first-step.id) "step id should remain unchanged")
      (assert (= updated-edge.source-step-id first-step.id) "dependent edge source should remain valid"))))

(fn assert-get-default-uses-user-data-dir [root]
  (local {: get-default} (require :workflows/store))
  (local store (get-default))
  (assert (= store.base-dir (fs.absolute root)) "get-default should use canonical appdirs user data dir when opts omit :base-dir")
  (local definition (store:create-definition {:name "default"}))
  (local definition-path (fs.join-path root "workflows" "definitions" (.. definition.id ".json")))
  (assert-file-json definition-path "default store should persist below app user data dir"))

(fn workflow-store-get-default-uses-app-user-data-dir []
  (with-temp-user-data-dir assert-get-default-uses-user-data-dir))

(fn assert-explicit-default-second-root [first-root second-root]
  (local {: get-default} (require :workflows/store))
  (assert (not (= (fs.absolute first-root) (fs.absolute second-root))) "fixture roots must be canonically distinct")
  (local first-store (get-default {:base-dir first-root}))
  (assert (= first-store.base-dir (fs.absolute first-root))
          "get-default should use explicit app/user base dir")
  (local first-definition (first-store:create-definition {:id "isolated-owner" :name "first root"}))
  (local second-store (get-default {:base-dir second-root}))
  (assert (not (= second-store first-store)) "distinct roots must have different owners")
  (assert (= (second-store:get-definition first-definition.id) nil) "second root must not see the first cache or output")
  (assert (= second-store.base-dir (fs.absolute second-root))
          "get-default should not keep a stale default when a new explicit app/user base dir is passed")
  (local definition (second-store:create-definition {:id first-definition.id :name "explicit default"}))
  (assert (not (= definition first-definition)) "same record id in distinct roots must not share cache identity")
  (local definition-path (fs.join-path second-root "workflows" "definitions" (.. definition.id ".json")))
  (local persisted (assert-file-json definition-path "explicit default store should persist below the passed app user data dir"))
  (assert (= persisted.id definition.id))
  (assert (= persisted.name "explicit default"))
  (local first-path (fs.join-path first-root "workflows" "definitions" (.. first-definition.id ".json")))
  (assert (= (. (assert-file-json first-path "first owner output must remain separate") :name) "first root")))

(fn assert-explicit-default-first-root [first-root]
  (with-temp-dir
    (fn [second-root]
      (assert-explicit-default-second-root first-root second-root))))

(fn workflow-store-get-default-honors-explicit-app-base-dir []
  (with-temp-dir assert-explicit-default-first-root))

(fn assert-default-equivalent-spellings [root]
  (local {: get-default} (require :workflows/store))
  (local canonical (assert (fs.absolute root)))
  (local relative (assert (fs.relative root)))
  (local spellings [root canonical relative])
  (each [_ spelling (ipairs spellings)]
    (assert (= (fs.absolute spelling) canonical) "cache equivalence requires exactly equal fs.absolute results"))
  (assert (not (= relative canonical)) "relative spelling must exercise a noncanonical request")
  (local owner (get-default {:base-dir root}))
  (local definition (owner:create-definition {:id "canonical-owner" :name "before"}))
  (local counts {})
  (local handlers [(connect-count owner :definition-updated counts :updated)])
  (fn exercise []
    (each [_ spelling (ipairs spellings)]
      (local candidate (get-default {:base-dir spelling}))
      (assert (= candidate owner) "equivalent spellings must retain the same default store")
      (assert (= (candidate:get-definition definition.id) definition) "equivalent requests must retain the cached definition")
      (assert (= candidate.definition-updated owner.definition-updated) "equivalent requests must retain the subscription owner"))
    (local candidate (get-default {:base-dir relative}))
    (local updated (candidate:update-definition definition.id {:name "after"}))
    (assert (= updated definition) "mutation must update the original cached object")
    (assert (= definition.name "after"))
    (each [_ spelling (ipairs spellings)]
      (local reused (get-default {:base-dir spelling}))
      (assert (= reused owner))
      (assert (= (reused:get-definition definition.id) definition)))
    (assert (= counts.updated 1) "original subscription must observe exactly one mutation event")
    (local path (fs.join-path canonical "workflows" "definitions" (.. definition.id ".json")))
    (local persisted (assert-file-json path "equivalent request must persist below the canonical root"))
    (assert (= persisted.id definition.id))
    (assert (= persisted.name "after")))
  (local (ok result) (pcall exercise))
  (disconnect-signal-handlers handlers)
  (when (not ok) (error result 0)))

(fn workflow-store-get-default-retains-equivalent-owner []
  (with-temp-dir assert-default-equivalent-spellings))

(table.insert tests {:name "workflow-store-persists-definitions-app-scoped"
                     :fn workflow-store-persists-definitions-app-scoped})
(table.insert tests {:name "workflow-store-creates-updates-steps-and-edges"
                     :fn workflow-store-creates-updates-steps-and-edges})
(table.insert tests {:name "workflow-store-delete-step-requires-dependent-edge-decision"
                     :fn workflow-store-delete-step-requires-dependent-edge-decision})
(table.insert tests {:name "workflow-store-persists-runs-steps-events-and-waits"
                     :fn workflow-store-persists-runs-steps-events-and-waits})
(table.insert tests {:name "workflow-store-signals-fire"
                      :fn workflow-store-signals-fire})
(table.insert tests {:name "workflow-store-update-definition-rejects-invalid-steps"
                     :fn workflow-store-update-definition-rejects-invalid-steps})
(table.insert tests {:name "workflow-store-update-step-rejects-id-changes"
                     :fn workflow-store-update-step-rejects-id-changes})
(table.insert tests {:name "workflow-store-get-default-uses-app-user-data-dir"
                      :fn workflow-store-get-default-uses-app-user-data-dir})
(table.insert tests {:name "workflow-store-get-default-honors-explicit-app-base-dir"
                      :fn workflow-store-get-default-honors-explicit-app-base-dir})
(table.insert tests {:name "workflow-store-get-default-retains-equivalent-owner"
                     :fn workflow-store-get-default-retains-equivalent-owner})

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "workflow-store"
                       :tests tests})))

{:name "workflow-store"
 :tests tests
 :main main}
