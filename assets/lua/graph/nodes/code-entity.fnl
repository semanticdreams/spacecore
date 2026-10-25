(local glm (require :glm))
(local {:GraphNode GraphNode} (require :graph/node-base))
(local {:GraphEdge GraphEdge} (require :graph/edge))
(local Signal (require :signal))
(local CodeEntityStore (require :entities/code))
(local Utils (require :graph/view/utils))
(local KeyLoaderUtils (require :graph/key-loader-utils))
(local Presentation (require :code-runs/presentation))
(local SCHEME "code-entity")

(fn make-label [entity]
  (assert entity "code entity missing")
  (if (> (# entity.name) 0) (Utils.truncate-with-ellipsis entity.name 50)
      (.. "code (" entity.language ")")))
(fn resolve-reference-lifecycle! [self]
  (local mounted (and self.graph self.graph.reference-lifecycle))
  (assert (or (not self.lifecycle) (not mounted) (= self.lifecycle mounted)) "reference lifecycle node/graph conflict")
  (local service (assert (or self.lifecycle mounted) "node requires reference lifecycle"))
  (assert (service:owns-store? SCHEME self.store) "reference lifecycle store ownership mismatch")
  service)
(fn delete-entity [self]
  (local lifecycle (self:resolve-reference-lifecycle!))
  (. (lifecycle:delete! self.key) :source-record))
(fn get-entity [self] (self.store:get-entity self.entity-id))
(fn refresh-label [self]
  (set self.label (make-label (self:get-entity)))
  (self.changed:emit self))
(fn update [self field value]
  (assert (self.store:update-entity self.entity-id {field value}) "code entity missing"))
(fn update-name [self value] (update self :name value))
(fn update-source [self value] (update self :source value))
(fn update-language [self value] (update self :language value))
(fn update-kernel [self value] (update self :kernel value))
(fn list-runs [self]
  (local store (assert self.run-store "code entity requires run store"))
  (store:list-runs self.entity-id))
(fn show-run [self id]
  (local run (assert (self.run-store:get-run id) "code run missing"))
  (assert (= run.code-entity-id self.entity-id) "run belongs to another code entity")
  (local graph (assert self.graph "show run requires mounted graph map"))
  (local target (assert (graph:load-by-key (.. "code-run:" id)) "code-run loader unavailable"))
  (graph:add-edge (GraphEdge {:source self :target target :label "run"}))
  target)
(fn show-latest-run [self]
  (local runs (self:list-runs))
  (assert (. runs 1) "this code entity has no runs")
  (self:show-run (. runs 1 :id)))
(fn run-entity [self]
  (local runner (assert self.runner "code entity requires code runner"))
  (local run (runner:run self.entity-id))
  (set self.latest-run-id run.id)
  (set self.last-run-result (Presentation.summary run))
  (self.run-result-changed:emit self.last-run-result)
  (when self.graph (self:show-run run.id))
  run)
(fn set-kernel-from-selection [self]
  (local graph (assert self.graph "kernel selection requires mounted graph map"))
  (local selected (assert graph.selected_node_keys "graph selection unavailable"))
  (assert (= (# selected) 1) "Select exactly one kernel node")
  (local node (assert (graph:resolve-node (. selected 1)) "selected node missing"))
  (local kernel-id (assert node.kernel-id "Selected node is not a kernel"))
  (self:update-kernel kernel-id)
  true)

(fn CodeEntityNode [opts]
  (local options (or opts {}))
  (local id (assert options.entity-id "CodeEntityNode requires entity-id"))
  (local store (or options.store (CodeEntityStore.get-default)))
  (local entity (assert (store:get-entity id) "code entity missing"))
  (local base (GraphNode {:key (.. "code-entity:" id) :label (make-label entity)
    :color (glm.vec4 0.2 0.35 0.85 1) :sub-color (glm.vec4 0.3 0.45 0.9 1) :size 8.0
    :view (require :graph/view/views/code-entity) :preview (require :graph/view/previews/code-entity)}))
  (local changed (Signal))
  (local deleted (Signal))
  (local result-changed (Signal))
  (var updated-handler nil)
  (var deleted-handler nil)
  (var run-handler nil)
  (fn drop [self]
    (when updated-handler (store.code-entity-updated:disconnect updated-handler true))
    (when deleted-handler (store.code-entity-deleted:disconnect deleted-handler true))
    (when run-handler (self.run-store.changed:disconnect run-handler true))
    (changed:clear) (deleted:clear) (result-changed:clear))
  (fn actions [self]
    (fn delete-action [_button _event] (self:delete-entity))
    [{:name "Delete Entity" :icon "delete" :fn delete-action}])
  (local self (setmetatable
    {:entity-id id :store store :lifecycle options.lifecycle :runner options.runner :run-store options.run-store
     :changed changed :entity-deleted deleted :run-result-changed result-changed :last-run-result ""
     :get-entity get-entity :refresh-label refresh-label :resolve-reference-lifecycle! resolve-reference-lifecycle!
     :delete-entity delete-entity :run-entity run-entity :list-runs list-runs :show-run show-run
     :show-latest-run show-latest-run :set-kernel-from-selection set-kernel-from-selection
     :update-name update-name :update-source update-source
     :update-language update-language :update-kernel update-kernel
     :actions actions :drop drop}
    {:__index base}))
  (fn on-update [current] (when (= current.id id) (self:refresh-label)))
  (fn on-delete [current]
    (when (= current.id id)
      (deleted:emit current)
      (when self.graph (self.graph:remove-nodes [self] {:cause "shared-delete"}))))
  (fn on-run [run]
    (when (= run.code-entity-id id)
      (when (= run.id self.latest-run-id)
        (set self.last-run-result (Presentation.summary run))
        (result-changed:emit self.last-run-result))
      (changed:emit self)))
  (set updated-handler (store.code-entity-updated:connect on-update))
  (set deleted-handler (store.code-entity-deleted:connect on-delete))
  (when options.run-store (set run-handler (options.run-store.changed:connect on-run)))
  self)

(local register-loader
  (KeyLoaderUtils.make-register-loader SCHEME CodeEntityStore.get-default
    (fn [id store options]
      (CodeEntityNode {:entity-id id :store store :lifecycle options.lifecycle
                       :runner options.runner :run-store options.run-store}))))
{:CodeEntityNode CodeEntityNode :register-loader register-loader}
