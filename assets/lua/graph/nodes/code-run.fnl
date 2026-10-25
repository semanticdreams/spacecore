(local glm (require :glm))
(local {:GraphNode GraphNode} (require :graph/node-base))
(local {:GraphEdge GraphEdge} (require :graph/edge))
(local Signal (require :signal))
(local Presentation (require :code-runs/presentation))
(local View (require :graph/view/views/code-run))

(fn reveal [self key label]
  (local graph (assert self.graph "code run must be mounted to reveal a related object"))
  (local target (assert (graph:resolve-node key) (.. "could not load " key)))
  (graph:add-edge (GraphEdge {:source self :target target :label label}))
  target)
(fn get-run [self] (assert (self.store:get-run self.run-id) "code run missing"))
(fn show-code [self] (reveal self (.. "code-entity:" (. (get-run self) :code-entity-id)) "code"))
(fn show-artifact [self key]
  (var selected nil)
  (each [_ item (ipairs (. (get-run self) :artifacts))]
    (when (= item.key key) (set selected item)))
  (assert selected "artifact does not belong to this run")
  (reveal self selected.key selected.label))
;; Deletion is store-owned; this node's deleted subscription removes the adapter
;; from this and every other open map. Artifacts are independent and survive.
(fn delete-run [self] (self.store:delete-run! self.run-id))
(fn make-delete-action [node]
  {:name "Delete Run" :icon "delete"
   :fn (fn [_button _event] (delete-run node))})
(fn run-actions [node]
  (if (= (. (get-run node) :status) "running")
      []
      [(make-delete-action node)]))
(fn Node [opts]
  (local store (assert opts.store "code-run node requires store"))
  (local id (assert opts.run-id))
  (local run (assert (store:get-run id) "code run missing"))
  (local base (GraphNode {:key (.. "code-run:" id) :label (Presentation.summary run)
                          :color (glm.vec4 0.2 0.6 0.8 1) :size 8.0
                          :view View.View :preview View.Preview}))
  (local changed (Signal))
  (var handler nil)
  (var deleted-handler nil)
  (fn drop [_self]
    (when handler (store.changed:disconnect handler true) (set handler nil))
    (when deleted-handler (store.deleted:disconnect deleted-handler true) (set deleted-handler nil))
    (changed:clear))
  (local self (setmetatable {:run-id id :store store :changed changed :get-run get-run
                             :show-code show-code :show-artifact show-artifact
                             :actions run-actions :drop drop}
                            {:__index base}))
  (fn on-change [current]
    (when (= current.id id)
      (set self.label (Presentation.summary current))
      (changed:emit self)))
  (fn on-deleted [deleted]
    (when (= deleted.id id)
      (when self.graph (self.graph:remove-nodes [self] {:cause "shared-delete"}))))
  (set handler (store.changed:connect on-change))
  (set deleted-handler (store.deleted:connect on-deleted))
  self)
{:Node Node}
