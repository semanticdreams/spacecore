(local glm (require :glm))
(local {:GraphNode GraphNode} (require :graph/node-base))
(local Signal (require :signal))
(local StringEntityStore (require :entities/string))
(local Utils (require :graph/view/utils))
(local KeyLoaderUtils (require :graph/key-loader-utils))

(local DARK_BLUE (glm.vec4 0.1 0.2 0.5 1))
(local DARK_BLUE_ACCENT (glm.vec4 0.15 0.25 0.55 1))

(local SCHEME "string-entity")
(local KEY_PREFIX (KeyLoaderUtils.key-prefix SCHEME))

(fn make-label [entity]
  (if (and entity entity.value (> (string.len entity.value) 0))
      (do
        (local first-line (or (string.match entity.value "([^\r\n]+)") entity.value))
        (Utils.truncate-with-ellipsis first-line 50))
      (or (and entity entity.id) "string entity")))

(local LinkEntityStore (require :entities/link))
(local Relationships (require :entities/relationships))
(local GraphMapContext (require :graph/map-context))

(fn require-graph-map [node]
  (local graph-map node.graph)
  (assert graph-map "StringEntityNode.create-child requires mounted GraphMap")
  (GraphMapContext.assert-graph-map graph-map "StringEntityNode.create-child")
  (assert (= (type graph-map.load-by-key) :function)
          "StringEntityNode.create-child requires callable GraphMap.load-by-key")
  graph-map)

(fn resolve-link-store [graph-map]
  (local store
    (if (and graph-map graph-map.graph graph-map.graph.link-store)
        graph-map.graph.link-store
        (and graph-map graph-map.link-store)
        graph-map.link-store
        (LinkEntityStore.get-default)))
  (assert store "StringEntityNode.create-child requires link store"))

(fn child-stage! [stage outcomes result operation]
  (var (ok value) (pcall operation))
  (when ok
    (if (= stage :reveal)
        (when (not value)
          (set ok false)
          (set value {:code :reveal-failed :message "GraphMap did not return the child" :outcome :unknown}))
        (when (not (and (= (type value) :table) value.id))
          (set ok false)
          (set value {:code :invalid-result :message "Created entity is missing id" :outcome :unknown}))))
  (if ok
      (do (set (. outcomes stage) (if (= stage :reveal) :revealed :committed)) value)
      (do
        (local cause (if (and (= (type value) :table) value.code) value
                         {:code :internal-error :message (tostring value) :outcome :unknown}))
        (set (. outcomes stage) (if (= stage :reveal) :unknown (or cause.outcome :unknown)))
        (when (and (= cause.outcome :committed) cause.result cause.result.id)
          (set (. result stage) cause.result)
          (set (. result (.. stage "-key"))
               (.. (if (= stage :child) KEY_PREFIX "link-entity:") cause.result.id)))
        (error {:code cause.code :message (.. "Create child failed at " stage ": " cause.message)
                :stage stage :outcome (if (or (= outcomes.child :committed) (= outcomes.link :committed))
                                        :committed (or cause.outcome :unknown))
                :outcomes outcomes :result result :cause cause}))))

(fn create-child [self]
  ;; Resolve and validate presentation dependencies before any owning mutation.
  (local graph-map (require-graph-map self))
  (local link-store (resolve-link-store graph-map))
  (assert (= (type link-store.create-entity) :function) "Create child requires link creation")
  (local result {})
  (local outcomes {:child :not-attempted :link :not-attempted :reveal :not-attempted})
  (local child (child-stage! :child outcomes result
                (fn create-string [] (self.store:create-entity {}))))
  (set result.child child)
  (set result.child-key (.. KEY_PREFIX child.id))
  (local link (child-stage! :link outcomes result
               (fn create-link []
                 (Relationships.create! self.store link-store {:key self.key} {:key result.child-key}))))
  (set result.link link)
  (set result.link-key (.. "link-entity:" link.id))
  (set result.child-node (child-stage! :reveal outcomes result
                          (fn reveal [] (graph-map:load-by-key result.child-key))))
  result)

(fn resolve-reference-lifecycle! [self]
  (local mounted (and self.graph self.graph.reference-lifecycle))
  (assert (or (not self.lifecycle) (not mounted) (= self.lifecycle mounted)) "reference lifecycle node/graph conflict")
  (local service (assert (or self.lifecycle mounted) "node requires reference lifecycle"))
  (assert (service:owns-store? SCHEME self.store) "reference lifecycle store ownership mismatch")
  service)

(fn StringEntityNode [opts]
  (local options (or opts {}))
  (local entity-id (assert options.entity-id "StringEntityNode requires entity-id"))
  (local store (or options.store (StringEntityStore.get-default)))
  (local StringEntityNodeView (require :graph/view/views/string-entity))
  (local StringEntityNodePreview (require :graph/view/previews/string-entity))

  (local entity (store:get-entity entity-id))
  (local initial-label (make-label entity))

  (local node
    (GraphNode {:key (.. KEY_PREFIX entity-id)
                :label initial-label
                :color DARK_BLUE
                :sub-color DARK_BLUE_ACCENT
                :size 8.0
                :view StringEntityNodeView
                :preview StringEntityNodePreview}))

  (set node.entity-id entity-id)
  (set node.store store)
  (set node.lifecycle options.lifecycle)
  (set node.resolve-reference-lifecycle! resolve-reference-lifecycle!)
  (set node.entity-deleted (Signal))
  (set node.changed (Signal))

  (fn refresh-label [self]
    (local current (self.store:get-entity self.entity-id))
    (set self.label (make-label current))
    (when self.changed
      (self.changed:emit self)))

  (set node.refresh-label refresh-label)

  (set node.get-entity
       (fn [self]
         (self.store:get-entity self.entity-id)))

  (set node.read-text
       (fn [self] (self.store:read-text self.entity-id)))
  (set node.replace-text
       (fn [self value revision]
         (self.store:replace-text self.entity-id value revision)))

  (set node.delete-entity
       (fn [self]
         (local service (self:resolve-reference-lifecycle!))
         (. (service:delete! self.key) :source-record)))

  (set node.create-child create-child)

  (set node.actions
       [{:name "Create child"
         :icon "subdirectory_arrow_right"
         :fn (fn [_button _event]
               (node:create-child))}
        {:name "Delete Entity"
         :icon "delete"
         :fn (fn [_button _event]
               (node:delete-entity))}])

  (var deleted-handler nil)
  (var updated-handler nil)

  (set deleted-handler
       (store.string-entity-deleted:connect
         (fn [deleted]
           (when (= (tostring deleted.id) (tostring entity-id))
             (node.entity-deleted:emit deleted)
              (when (and node.graph node.graph.remove-nodes)
                (node.graph:remove-nodes [node] {:cause "shared-delete"}))))))

  (set updated-handler
       (store.string-entity-updated:connect
         (fn [updated]
           (when (= (tostring updated.id) (tostring entity-id))
             (node:refresh-label)))))

  (set node.drop
       (fn [self]
         (when deleted-handler
           (store.string-entity-deleted:disconnect deleted-handler true)
           (set deleted-handler nil))
         (when updated-handler
           (store.string-entity-updated:disconnect updated-handler true)
           (set updated-handler nil))
         (self.entity-deleted:clear)
         (when self.changed
           (self.changed:clear))))

  node)

(local register-loader
  (KeyLoaderUtils.make-register-loader SCHEME
    StringEntityStore.get-default
    (fn [entity-id store options]
      (StringEntityNode {:entity-id entity-id :store store :lifecycle options.lifecycle}))))

{:StringEntityNode StringEntityNode
 :register-loader register-loader}
