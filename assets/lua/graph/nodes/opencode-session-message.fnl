(local glm (require :glm))
(local {:GraphEdge GraphEdge} (require :graph/edge))
(local {:GraphNode GraphNode} (require :graph/node-base))
(local Signal (require :signal))
(local Common (require :graph/nodes/opencode-common))
(local MessageView (require :graph/view/views/opencode-session-message))

;; A message node is a projection of its parent session adapter's snapshot:
;; it performs no network I/O. Per the reconciled design, parent acquisition
;; happens on mount through the graph, the message node observes the parent's
;; changed signal, and absence from a successful snapshot is an explicit
;; `absent` state — distinct from deletion or unavailability.

(fn OpenCodeSessionMessageNode [opts]
  (local session-id (assert opts.session-id "message node requires session-id"))
  (assert (Common.url-safe-id? session-id) "session id must be url-safe")
  (local message-id (assert opts.message-id "message node requires message-id"))
  (assert (Common.url-safe-id? message-id) "message id must be url-safe")
  (local base
    (GraphNode
      {:key (.. "opencode-session-message:" session-id "/" message-id)
       :label (.. "message " message-id)
       :color (glm.vec4 0.35 0.55 0.75 1)
       :sub-color (glm.vec4 0.5 0.7 0.9 1)
       :size 8.0
       :view MessageView.View :preview MessageView.Preview}))
  (local self (setmetatable {:session-id session-id
                             :message-id message-id
                             :state :idle
                             :message nil
                             :position nil
                             :message-count nil
                             ;; Freshness propagated from the parent session:
                             ;; retained data is only "last known" until a
                             ;; successful snapshot re-establishes it.
                             :transcript-error nil
                             :stale? false
                             :parent-removed? false
                             :error nil
                             :changed (Signal)}
                            {:__index base}))

  (fn emit []
    (self.changed:emit self))

  (fn find-message [messages]
    (var found nil)
    (var index 0)
    (each [i message (ipairs messages)]
      (local info (if message.info message.info {}))
      (local current-id (if (and info info.id) (tostring info.id) "?"))
      (when (and (not found) (= current-id message-id))
        (set found message)
        (set index i)))
  (if found (values found index) (values nil nil)))

  (fn recompute []
    (local parent self.parent)
    (local (lifecycle-state lifecycle-error) (Common.parent-availability self parent))
    (if lifecycle-state
        (do
          (set self.state lifecycle-state)
          (set self.error lifecycle-error))
        (= parent.messages nil)
        (set self.state :loading)
        (do
          (local (message index) (find-message parent.messages))
          (set self.transcript-error parent.transcript-error)
          (set self.stale? (and parent.messages-stale
                                (> (length parent.messages) 0)))
          (if message
              (do
                (set self.message message)
                (set self.position index)
                (set self.message-count (length parent.messages))
                (set self.state :ready)
                (set self.error nil))
              (do
                ;; Absence from a successful snapshot is not deletion.
                (set self.state :absent)
                (set self.error "message not present in the session snapshot")))))
    (set self.label
         (if (and self.message self.message.info self.message.info.role)
             (.. (tostring self.message.info.role) " message " message-id)
             (.. "message " message-id)))
    (emit))

  (local parent-key (.. "opencode-session:" session-id))
  (fn mount [mounted graph]
    (Common.projection-mount self base parent-key recompute mounted graph))

  (fn drop [_self]
    (Common.projection-drop self))

  (fn info-item-rows [node]
    ;; Parts are separate from even an info property literally named "parts".
    (local rows [{:id "parts" :label "Parts" :action :parts}])
    (local message (if node.message node.message {}))
    (local info (if message.info message.info {}))
    (each [_ field (ipairs (. (Common.info-projection info) :complex))]
      (table.insert rows {:id (.. "info:" (Common.encode-info-field field))
                          :label (if (= field "") "\"\"" field) :action :info :field field}))
    rows)

  ;; Hub actions: materialize projection children on explicit request.
  (fn open-parts [node]
    (local graph (assert node.graph "opencode message node must be mounted to open parts"))
    (local target (graph:resolve-node
                    (.. "opencode-session-message-parts:" session-id "/" message-id)))
    (graph:add-edge (GraphEdge {:source node :target target :label "parts"}))
    target)

  (fn open-info-field [node field]
    (assert (= (type field) :string) "info field must be a string")
    (local graph (assert node.graph "opencode message node must be mounted to open an info field"))
    (local target (graph:resolve-node
                     (.. "opencode-session-message-info:" session-id "/" message-id "/" (Common.encode-info-field field))))
    (graph:add-edge (GraphEdge {:source node :target target :label "info"}))
    target)

  (tset self :mount mount)
  (tset self :unmount Common.projection-unmount)
  (tset self :drop drop)
  (tset self :recompute recompute)
  (tset self :info-item-rows info-item-rows)
  (tset self :open-parts open-parts)
  (tset self :open-info-field open-info-field)
  (setmetatable self {:__index base}))

{:OpenCodeSessionMessageNode OpenCodeSessionMessageNode}
