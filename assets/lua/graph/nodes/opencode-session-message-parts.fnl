(local glm (require :glm))
(local {:GraphEdge GraphEdge} (require :graph/edge))
(local {:GraphNode GraphNode} (require :graph/node-base))
(local Signal (require :signal))
(local Common (require :graph/nodes/opencode-common))
(local PartsView (require :graph/view/views/opencode-session-message-parts))

;; A parts node is a projection of its parent message node's snapshot: no
;; network I/O, no independent fetching. It enumerates the message's raw
;; parts by validated unique url-safe part.id; parts without a valid id stay
;; addressable in the view but never become clickable nodes. A removed part
;; id is an explicit `absent` state and may return to `ready` if the same id
;; reappears in a later snapshot.

(fn OpenCodeSessionMessagePartsNode [opts]
  (local session-id (assert opts.session-id "parts node requires session-id"))
  (assert (Common.url-safe-id? session-id) "session id must be url-safe")
  (local message-id (assert opts.message-id "parts node requires message-id"))
  (assert (Common.url-safe-id? message-id) "message id must be url-safe")
  (local base
    (GraphNode
      {:key (.. "opencode-session-message-parts:" session-id "/" message-id)
       :label (.. "parts " message-id)
       :color (glm.vec4 0.45 0.55 0.7 1)
       :sub-color (glm.vec4 0.55 0.7 0.85 1)
       :size 8.0
       :view PartsView.View :preview PartsView.Preview}))
  (local self (setmetatable {:session-id session-id
                             :message-id message-id
                             :state :idle
                             :parts nil
                             :parent-removed? false
                             :error nil
                             :changed (Signal)}
                            {:__index base}))

  (fn emit []
    (self.changed:emit self))

  (local island-id (.. "opencode-parts:" session-id "/" message-id))
  (set self.cleanup-island! (Common.island-cleaner self island-id))

  (fn member-keys []
    (local keys [])
    (each [_ entry (ipairs (if self.parts self.parts []))]
      (when (and entry.valid? entry.id)
        (table.insert keys
          (.. "opencode-session-message-part:" session-id "/" message-id
              "/" (tostring entry.id)))))
    keys)

  (fn island-teardown? []
    (if (= self.state :absent) true
        (= self.state :unavailable) true
        (= self.state :not-found) true
        false))

  (fn sync-island! []
    (if (= self.state :ready)
        (Common.sync-ordered-island self island-id (member-keys) "part")
        (when (island-teardown?)
          (self:cleanup-island!))))

  (fn recompute []
    (local parent self.parent)
    (local (lifecycle-state lifecycle-error) (Common.parent-availability self parent))
    (if lifecycle-state
        (do
          (set self.state lifecycle-state)
          (set self.error lifecycle-error))
        (if (= parent.state :idle)
            (do
              ;; The parent message itself is not in the current snapshot.
              (set self.state :absent)
              (set self.error "message not present in the session snapshot"))
            (do
              (local message (if parent.message parent.message {}))
              (set self.parts (Common.validated-ids (if message.parts message.parts [])))
              (set self.state :ready)
              (set self.error nil))))
    (set self.label (.. "parts " message-id))
    (sync-island!)
    (emit))

  (local parent-key (.. "opencode-session-message:" session-id "/" message-id))
  (fn mount [mounted graph]
    (Common.projection-mount self base parent-key recompute mounted graph))

  (fn drop [_self]
    (Common.projection-drop self))

  (fn open-part [node entry]
    ;; entry is a Common.validated-ids row; only valid ids materialize.
    (assert (and entry entry.valid? entry.id)
            "part requires a validated unique url-safe id")
    (local graph (assert node.graph "opencode parts node must be mounted to open a part"))
    (local target
      (graph:resolve-node
        (.. "opencode-session-message-part:" session-id "/" message-id "/" (tostring entry.id))))
    (graph:add-edge (GraphEdge {:source node :target target :label "part"}))
    target)

  (tset self :mount mount)
  (tset self :unmount Common.projection-unmount)
  (tset self :drop drop)
  (tset self :recompute recompute)
  (tset self :open-part open-part)
  (setmetatable self {:__index base}))

{:OpenCodeSessionMessagePartsNode OpenCodeSessionMessagePartsNode}
