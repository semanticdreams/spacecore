(local fs (require :fs))
(local H (require :tests/test-reference-lifecycle-helpers))
(local Graph (require :graph/init))
(local GraphMap (require :graph/map))
(local StringEntityStore (require :entities/string))
(local LinkEntityStore (require :entities/link))
(local {:StringEntityNode StringEntityNode
         :register-loader register-string-loader} (require :graph/nodes/string-entity))
(local tests [])
(var temp-counter 0)

(fn temp-dir []
  (set temp-counter (+ temp-counter 1))
  (fs.join-path "/tmp/space/tests/string-entity-create-child"
                (.. "case-" (os.time) "-" temp-counter)))

(fn with-temp-dir [f]
  (local dir (temp-dir))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (fs.create-dirs dir)
  (local (ok result) (pcall f dir))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (if ok result (error result)))

(fn make-stores [dir]
  {:string-store (StringEntityStore.StringEntityStore {:base-dir dir})
   :link-store (LinkEntityStore.LinkEntityStore {:base-dir dir})})

(fn find-action [node name]
  (assert node "find-action requires node")
  (assert node.actions "find-action requires node actions")
  (var found nil)
  (each [_ action (ipairs node.actions)]
    (when (= action.name name)
      (set found action)))
  found)

(fn invoke-action [action]
  (assert action "expected action to exist")
  (assert (= (type action.fn) "function") "expected action.fn to be function")
  (action.fn nil nil))

(fn assert-error-contains [f expected]
  (local (ok err) (pcall f))
  (assert (not ok) "expected function to fail")
  (assert (string.find (tostring err) expected 1 true)
          (.. "expected error to contain " expected ", got " (tostring err))))

(fn with-real-graph-map [f]
  (with-temp-dir
    (fn [dir]
      (local stores (make-stores dir))
      (local graph (Graph {:with-start false
                           :string-store stores.string-store
                            :link-store stores.link-store :identity-store stores.link-store.identity-store}))
      (register-string-loader graph {:store stores.string-store})
      (local graph-map (GraphMap.GraphMap {:graph graph :id "create-child-test"}))
      (local parent (stores.string-store:create-entity {:value "parent"}))
      (local parent-key (.. "string-entity:" parent.id))
      (local parent-node (graph-map:load-by-key parent-key))
      (assert parent-node "expected parent node to load")
      (local (ok result) (pcall f {:stores stores
                                   :graph graph
                                   :graph-map graph-map
                                   :parent parent
                                   :parent-key parent-key
                                   :parent-node parent-node}))
      (graph-map:drop)
      (graph:drop)
      (if ok result (error result)))))

(fn create-child-success-case [ctx]
  (local create-action (find-action ctx.parent-node "Create child"))
  (local delete-action (find-action ctx.parent-node "Delete Entity"))
  (assert create-action "expected Create child action")
  (assert delete-action "expected Delete Entity action to remain")
  (local result (invoke-action create-action))
  (assert result.child "expected child entity in result")
  (assert result.child.id "expected child id")
  (assert result.link "expected link entity in result")
  (local child-key (.. "string-entity:" result.child.id))
  (assert (= result.child-key child-key) "expected child-key to match id")
  (H.assert-reference ctx.stores.link-store.identity-store result.link.source-key ctx.parent-key)
  (H.assert-reference ctx.stores.link-store.identity-store result.link.target-key child-key)
  (assert (= (length (ctx.stores.string-store:list-entities)) 2) "expected parent plus child")
  (assert (= (length (ctx.stores.link-store:list-entities)) 1) "expected one link")
  (assert (ctx.graph-map:lookup child-key) "expected child in same graph map")
  (assert (= (ctx.graph-map:edge-count) 1) "expected one visible derived edge")
  (local captured (ctx.graph-map:capture-state))
  (assert (= (length captured.edges) 0) "derived edge must not persist"))

(fn create-child-unmounted-fails-case [dir]
  (local stores (make-stores dir))
  (local parent (stores.string-store:create-entity {:value "parent"}))
  (local node (StringEntityNode {:entity-id parent.id
                                 :store stores.string-store}))
  (local action (find-action node "Create child"))
  (assert-error-contains (fn [] (invoke-action action))
                         "StringEntityNode.create-child requires mounted GraphMap")
  (assert (= (length (stores.string-store:list-entities)) 1) "must not create child on unmounted failure")
  (assert (= (length (stores.link-store:list-entities)) 0) "must not create link on unmounted failure")
  (node:drop))

(fn create-child-without-load-by-key-fails-case [dir]
  (local stores (make-stores dir))
  (local parent (stores.string-store:create-entity {:value "parent"}))
  (local node (StringEntityNode {:entity-id parent.id
                                 :store stores.string-store}))
  (node:mount {:graph {:link-store stores.link-store}})
  (local action (find-action node "Create child"))
  (assert-error-contains (fn [] (invoke-action action))
                         "StringEntityNode.create-child requires a graph map")
  (assert (= (length (stores.string-store:list-entities)) 1) "must not create child without load-by-key")
  (assert (= (length (stores.link-store:list-entities)) 0) "must not create link without load-by-key")
  (node:drop))

(fn create-child-shared-graph-fails-case [dir]
  (local stores (make-stores dir))
  (local graph (Graph {:with-start false
                       :string-store stores.string-store
                        :link-store stores.link-store :identity-store stores.link-store.identity-store}))
  (register-string-loader graph {:store stores.string-store})
  (local parent (stores.string-store:create-entity {:value "parent"}))
  (local node (StringEntityNode {:entity-id parent.id
                                  :store stores.string-store}))
  (node:mount graph)
  (local action (find-action node "Create child"))
  (assert-error-contains (fn [] (invoke-action action))
                         "StringEntityNode.create-child requires a graph map")
  (assert (= (length (stores.string-store:list-entities)) 1) "must not create child on shared Graph mount failure")
  (assert (= (length (stores.link-store:list-entities)) 0) "must not create link on shared Graph mount failure")
  (node:drop)
  (graph:drop))

(fn create-child-load-failure-fails-loudly-case [ctx]
  (local original-load-by-key ctx.graph-map.load-by-key)
  (set ctx.graph-map.load-by-key (fn [_self _key] nil))
  (local action (find-action ctx.parent-node "Create child"))
  (local (ok err) (pcall invoke-action action))
  (assert (not ok))
  (assert (= (type err) :table) "partial failure must report structured outcomes")
  (assert (= err.stage :reveal))
  (assert (= err.outcomes.child :committed))
  (assert (= err.outcomes.link :committed))
  (assert err.result.child-key)
  (assert err.result.link-key)
  (assert (= (length (ctx.stores.string-store:list-entities)) 2) "committed child must survive reveal failure")
  (assert (= (length (ctx.stores.link-store:list-entities)) 1) "committed link must survive reveal failure")
  (set ctx.graph-map.load-by-key original-load-by-key))

(fn create-child-preflight-case [ctx]
  (local created {:count 0})
  (local handler (ctx.stores.string-store.string-entity-created:connect
                   (fn count-child [] (set created.count (+ created.count 1)))))
  (local original ctx.graph-map.load-by-key)
  (set ctx.graph-map.load-by-key true)
  (local (ok _err) (pcall ctx.parent-node.create-child ctx.parent-node))
  (set ctx.graph-map.load-by-key original)
  (ctx.stores.string-store.string-entity-created:disconnect handler)
  (assert (not ok))
  (assert (= created.count 0) "preflight must not write then compensate")
  (assert (= (length (ctx.stores.string-store:list-entities)) 1) "reveal API must be callable before writes")
  (assert (= (length (ctx.stores.link-store:list-entities)) 0)))

(fn child-link-storage-failure [ctx]
  (local original ctx.stores.link-store.create-entity)
  (set ctx.stores.link-store.create-entity
       (fn fail-link [_self _opts] (error {:code :storage-failed :message "injected" :outcome :not-committed})))
  (local (ok err) (pcall ctx.parent-node.create-child ctx.parent-node))
  (set ctx.stores.link-store.create-entity original)
  (assert (not ok))
  (assert (= err.stage :link))
  (assert (= err.code :storage-failed))
  (assert (= err.outcomes.child :committed))
  (assert (= err.outcomes.link :not-committed))
  (assert (= err.outcomes.reveal :not-attempted))
  (assert err.result.child-key)
  (assert (= err.result.link nil))
  (assert (= (length (ctx.stores.string-store:list-entities)) 2))
  (assert (= (length (ctx.stores.link-store:list-entities)) 0))
  (assert (= (ctx.graph-map:node-count) 1) "failed domain step must not reveal child"))

(fn child-notification-failure [ctx]
  (local handler (ctx.stores.string-store.string-entity-created:connect
                   (fn fail-notify [] (error "injected child notification"))))
  (local (ok err) (pcall ctx.parent-node.create-child ctx.parent-node))
  (ctx.stores.string-store.string-entity-created:disconnect handler)
  (assert (not ok))
  (assert (= err.stage :child))
  (assert (= err.code :notification-failed))
  (assert (= err.outcomes.child :committed))
  (assert (= err.outcomes.link :not-attempted))
  (assert err.result.child-key)
  (assert (= (. (ctx.stores.string-store:read-text err.result.child.id) :value) ""))
  (assert (= (length (ctx.stores.string-store:list-entities)) 2))
  (assert (= (length (ctx.stores.link-store:list-entities)) 0))
  (assert (= (ctx.graph-map:node-count) 1)))

(fn link-notification-failure [ctx]
  (local handler (ctx.stores.link-store.link-entity-created:connect
                   (fn fail-notify [] (error "injected link notification"))))
  (local (ok err) (pcall ctx.parent-node.create-child ctx.parent-node))
  (ctx.stores.link-store.link-entity-created:disconnect handler)
  (assert (not ok))
  (assert (= err.stage :link))
  (assert (= err.code :notification-failed))
  (assert (= err.outcomes.child :committed))
  (assert (= err.outcomes.link :committed))
  (assert (= err.outcomes.reveal :not-attempted))
  (assert err.result.child-key)
  (assert err.result.link-key)
  (H.assert-reference ctx.stores.link-store.identity-store err.result.link.target-key err.result.child-key)
  (assert (= (length (ctx.stores.string-store:list-entities)) 2))
  (assert (= (length (ctx.stores.link-store:list-entities)) 1))
  (assert (= (ctx.graph-map:node-count) 1)))

(fn child-storage-failure [ctx]
  (local original ctx.stores.string-store.create-entity)
  (set ctx.stores.string-store.create-entity
       (fn fail-create [] (error {:code :storage-failed :message "injected" :outcome :not-committed})))
  (local (ok err) (pcall ctx.parent-node.create-child ctx.parent-node))
  (set ctx.stores.string-store.create-entity original)
  (assert (not ok))
  (assert (= err.stage :child))
  (assert (= err.outcome :not-committed))
  (assert (= err.outcomes.child :not-committed))
  (assert (= err.outcomes.link :not-attempted))
  (assert (= err.result.child-key nil))
  (assert (= (length (ctx.stores.string-store:list-entities)) 1)))

(fn relationship-validation [ctx]
  ;; A persisted endpoint disappears without a store event; cached data cannot
  ;; satisfy the shared relationship operation's owning validation boundary.
  ((. (require :entities/record-files) :remove!)
    (fs.join-path ctx.stores.string-store.entities-dir (.. ctx.parent.id ".md")))
  (local (ok err) (pcall ctx.parent-node.create-child ctx.parent-node))
  (assert (not ok))
  (assert (= err.stage :link))
  (assert (= err.code :not-found))
  (assert (= err.outcomes.child :committed))
  (assert (= err.outcomes.link :not-committed))
  (assert err.result.child-key)
  (assert (= (length (ctx.stores.link-store:list-entities)) 0)))

(fn reveal-notification-failure [ctx]
  (local handler (ctx.graph-map.node-added:connect (fn fail-reveal [] (error "injected reveal notification"))))
  (local (ok err) (pcall ctx.parent-node.create-child ctx.parent-node))
  (ctx.graph-map.node-added:disconnect handler)
  (assert (not ok))
  (assert (= err.stage :reveal))
  (assert (= err.outcomes.child :committed))
  (assert (= err.outcomes.link :committed))
  (assert (= err.outcomes.reveal :unknown))
  (assert err.result.child-key)
  (assert err.result.link-key)
  (assert (ctx.graph-map:lookup err.result.child-key) "reveal may already have materialized child before throwing")
  (assert (= (length (ctx.stores.string-store:list-entities)) 2))
  (assert (= (length (ctx.stores.link-store:list-entities)) 1)))

(fn test-create-child-success []
  (with-real-graph-map create-child-success-case))

(fn test-create-child-unmounted-fails []
  (with-temp-dir create-child-unmounted-fails-case))

(fn test-create-child-without-load-by-key-fails []
  (with-temp-dir create-child-without-load-by-key-fails-case))

(fn test-create-child-shared-graph-fails []
  (with-temp-dir create-child-shared-graph-fails-case))

(fn test-create-child-load-failure-fails-loudly []
  (with-real-graph-map create-child-load-failure-fails-loudly-case))

(table.insert tests {:name "Create child creates child link and derived edge" :fn test-create-child-success})
(table.insert tests {:name "Create child fails when unmounted" :fn test-create-child-unmounted-fails})
(table.insert tests {:name "Create child fails without load-by-key" :fn test-create-child-without-load-by-key-fails})
(table.insert tests {:name "Create child rejects shared Graph mount" :fn test-create-child-shared-graph-fails})
(table.insert tests {:name "Create child fails when child load fails" :fn test-create-child-load-failure-fails-loudly})
(each [_ scenario (ipairs [{:name "Create child preflights callable reveal" :run create-child-preflight-case}
                           {:name "Create child retains child on link storage failure" :run child-link-storage-failure}
                           {:name "Create child reports committed child notification failure" :run child-notification-failure}
                           {:name "Create child reports committed link notification failure" :run link-notification-failure}
                           {:name "Create child reports child storage failure" :run child-storage-failure}
                           {:name "Create child uses shared relationship endpoint validation" :run relationship-validation}
                           {:name "Create child retains records after reveal notification failure" :run reveal-notification-failure}])]
  (table.insert tests {:name scenario.name :fn (fn run-scenario [] (with-real-graph-map scenario.run))}))

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "string-entity-create-child" :tests tests})))

{:name "string-entity-create-child"
 :tests tests
 :main main}
