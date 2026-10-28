(local glm (require :glm))
(local {:GraphEdge GraphEdge} (require :graph/edge))
(local {:GraphNode GraphNode} (require :graph/node-base))
(local Signal (require :signal))
(local Common (require :graph/nodes/opencode-common))
(local PartView (require :graph/view/views/opencode-session-message-part))

;; A part node is a projection of its parent message node's snapshot: no
;; network I/O. Keyed by the raw part id; a part id that disappears from a
;; successful snapshot is an explicit `absent` state and may return to
;; `ready` if the same id reappears.

(fn OpenCodeSessionMessagePartNode [opts]
  (local session-id (assert opts.session-id "part node requires session-id"))
  (assert (Common.url-safe-id? session-id) "session id must be url-safe")
  (local message-id (assert opts.message-id "part node requires message-id"))
  (assert (Common.url-safe-id? message-id) "message id must be url-safe")
  (local part-id (assert opts.part-id "part node requires part-id"))
  (assert (Common.url-safe-id? part-id) "part id must be url-safe")
  (local base
    (GraphNode
      {:key (.. "opencode-session-message-part:" session-id "/" message-id "/" part-id)
       :label (.. "part " part-id)
       :color (glm.vec4 0.5 0.6 0.65 1)
       :sub-color (glm.vec4 0.6 0.75 0.8 1)
       :size 8.0
       :view PartView.View :preview PartView.Preview}))
  (local self (setmetatable {:session-id session-id
                             :message-id message-id
                             :part-id part-id
                             :state :idle
                             :part nil
                             :parent-removed? false
                             :error nil
                             :changed (Signal)}
                            {:__index base}))

  (fn emit []
    (self.changed:emit self))

  (fn find-part [parts]
    (var found nil)
    (each [_ part (ipairs (if parts parts []))]
      (when (and (not found) part part.id
                 (= (tostring part.id) part-id))
        (set found part)))
    found)

  (fn recompute []
    (local parent self.parent)
    (local (lifecycle-state lifecycle-error) (Common.parent-availability self parent))
    (if lifecycle-state
        (do
          (set self.state lifecycle-state)
          (set self.error lifecycle-error))
        (if (= parent.state :idle)
            (do
              (set self.state :absent)
              (set self.error "message not present in the session snapshot"))
            (do
              (local message (if parent.message parent.message {}))
              (local part (find-part message.parts))
              (if part
                  (do
                    (set self.part part)
                    (set self.state :ready)
                    (set self.error nil))
                  (do
                    (set self.state :absent)
                    (set self.error "part not present in the message snapshot"))))))
    (set self.label (.. "part " part-id))
    (emit))

  (local parent-key (.. "opencode-session-message:" session-id "/" message-id))
  (fn mount [mounted graph]
    (Common.projection-mount self base parent-key recompute mounted graph))

  (fn drop [_self]
    (Common.projection-drop self))

  (tset self :mount mount)
  (tset self :unmount Common.projection-unmount)
  (tset self :drop drop)
  (tset self :recompute recompute)
  (setmetatable self {:__index base}))

{:OpenCodeSessionMessagePartNode OpenCodeSessionMessagePartNode}
