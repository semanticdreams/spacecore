(local glm (require :glm))
(local {:GraphEdge GraphEdge} (require :graph/edge))
(local {:GraphNode GraphNode} (require :graph/node-base))
(local Signal (require :signal))
(local Common (require :graph/nodes/opencode-common))
(local InfoView (require :graph/view/views/opencode-session-message-info))

;; An info node is a projection of its parent message node's snapshot: no
;; network I/O. One node per decoded info field, with a canonical encoded key.
;; A missing field is ready with present? false;
;; absent is reserved for absence of the parent message.

(fn OpenCodeSessionMessageInfoNode [opts]
  (local session-id (assert opts.session-id "info node requires session-id"))
  (assert (Common.url-safe-id? session-id) "session id must be url-safe")
  (local message-id (assert opts.message-id "info node requires message-id"))
  (assert (Common.url-safe-id? message-id) "message id must be url-safe")
  (local field (assert opts.field "info node requires field"))
  (assert (= (type field) :string) "info field must be a string")
  (local base
    (GraphNode
      {:key (.. "opencode-session-message-info:" session-id "/" message-id "/" (Common.encode-info-field field))
       :label (.. "info " field)
       :color (glm.vec4 0.55 0.5 0.7 1)
       :sub-color (glm.vec4 0.65 0.6 0.85 1)
       :size 8.0
       :view InfoView.View :preview InfoView.Preview}))
  (local self (setmetatable {:session-id session-id
                             :message-id message-id
                             :field field
                             :value nil
                             :present? false
                             :parent-removed? false
                             :state :idle
                             :error nil
                             :changed (Signal)}
                            {:__index base}))

  (fn emit []
    (self.changed:emit self))

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
              (local info (if message.info message.info {}))
              (local value (. info field))
              (set self.value value)
              (set self.present? (not= value nil))
              (set self.state :ready)
              (set self.error nil))))
    (set self.label (.. "info " field))
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

{:OpenCodeSessionMessageInfoNode OpenCodeSessionMessageInfoNode}
