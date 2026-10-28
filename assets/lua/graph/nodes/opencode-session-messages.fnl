(local glm (require :glm))
(local {:GraphEdge GraphEdge} (require :graph/edge))
(local {:GraphNode GraphNode} (require :graph/node-base))
(local Signal (require :signal))
(local Common (require :graph/nodes/opencode-common))
(local MessagesView (require :graph/view/views/opencode-session-messages))

;; A messages node is a projection of its parent session adapter's snapshot:
;; it performs no network I/O. It holds the transcript and the message list
;; that used to live inside the session view; clicking a message row
;; materializes that message's own node.

(fn OpenCodeSessionMessagesNode [opts]
  (local session-id (assert opts.session-id "messages node requires session-id"))
  (assert (Common.url-safe-id? session-id) "session id must be url-safe")
  (local base
    (GraphNode
      {:key (.. "opencode-session-messages:" session-id)
       :label (.. "messages " session-id)
       :color (glm.vec4 0.35 0.5 0.75 1)
       :sub-color (glm.vec4 0.5 0.65 0.9 1)
       :size 8.0
       :view MessagesView.View :preview MessagesView.Preview}))
  (local self (setmetatable {:session-id session-id
                             :state :idle
                             :messages nil
                             :entries nil
                             :transcript-error nil
                             :stale? false
                             :parent-removed? false
                             :error nil
                             :changed (Signal)}
                            {:__index base}))

  (fn emit []
    (self.changed:emit self))

  (fn message-entries [messages]
    ;; Rows keyed by validated unique url-safe message ids.
    (local wrapped [])
    (each [_ message (ipairs (if messages messages []))]
      (local info (if message.info message.info {}))
      (table.insert wrapped {:id (if info.id (tostring info.id) nil)
                             :message message}))
    (Common.validated-ids wrapped))

  (local island-id (.. "opencode-messages:" session-id))
  (set self.cleanup-island! (Common.island-cleaner self island-id))

  (fn member-keys []
    (local keys [])
    (each [_ entry (ipairs (if self.entries self.entries []))]
      (when (and entry.valid? entry.id)
        (table.insert keys
          (.. "opencode-session-message:" session-id "/" (tostring entry.id)))))
    keys)

  (fn island-teardown? []
    (if (= self.state :absent) true
        (= self.state :unavailable) true
        (= self.state :not-found) true
        false))

  (fn sync-island! []
    (if (= self.state :ready)
        (Common.sync-ordered-island self island-id (member-keys))
        (when (island-teardown?)
          (self:cleanup-island!))))

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
          (set self.messages parent.messages)
          (set self.entries (message-entries parent.messages))
          (set self.transcript-error parent.transcript-error)
          (set self.stale? (and parent.messages-stale
                                (> (length parent.messages) 0)))
          (set self.state :ready)
          (set self.error nil)))
    (set self.label (.. "messages " session-id))
    (sync-island!)
    (emit))

  (local parent-key (.. "opencode-session:" session-id))
  (fn mount [mounted graph]
    (Common.projection-mount self base parent-key recompute mounted graph))

  (fn drop [_self]
    (Common.projection-drop self))

  (fn open-message [node message]
    (local info (if message.info message.info {}))
    (local message-id (assert info.id "message requires id"))
    (assert (Common.url-safe-id? message-id) "message id must be url-safe")
    (local graph (assert node.graph "opencode messages node must be mounted to open a message"))
    (local target
      (graph:resolve-node
        (.. "opencode-session-message:" (tostring session-id) "/" (tostring message-id))))
    (graph:add-edge (GraphEdge {:source node :target target :label "message"}))
    target)

  (tset self :mount mount)
  (tset self :unmount Common.projection-unmount)
  (tset self :drop drop)
  (tset self :recompute recompute)
  (tset self :open-message open-message)
  (setmetatable self {:__index base}))

{:OpenCodeSessionMessagesNode OpenCodeSessionMessagesNode}
