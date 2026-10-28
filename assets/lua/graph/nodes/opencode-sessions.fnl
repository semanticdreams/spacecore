(local glm (require :glm))
(local {:GraphEdge GraphEdge} (require :graph/edge))
(local {:GraphNode GraphNode} (require :graph/node-base))
(local Signal (require :signal))
(local Common (require :graph/nodes/opencode-common))
(local SessionNodeModule (require :graph/nodes/opencode-session))
(local SessionsView (require :graph/view/views/opencode-sessions))

;; Root adapter over the OpenCode server's session list (GET /session).
;; Sessions themselves stay owned by the OpenCode server; this node holds only
;; an ephemeral list snapshot for discovery and explicit graph materialization.

(fn session-label [_self session]
  (local id (if session.id (tostring session.id) "?"))
  (local title (and session session.title))
  (if (and title (> (length (tostring title)) 0))
      (.. (tostring title) " — " id)
      (.. "OpenCode session " id)))

(fn try-submit-list! [client stale? request-generation on-list-response]
  ;; Returns nil on a successful submit, or the failure message.
  (local (submitted err)
    (pcall
      (fn []
        (client.submit "GET" "/session"
          (Common.get-request
            (Common.guarded-response stale? request-generation on-list-response))))))
  (if submitted nil (tostring err)))

(fn make-controller [self ensure settle emit]
  (var generation 0)
  (var dropped false)
  (fn stale? [request-generation]
    (if dropped true (not= request-generation generation)))
  (fn on-list-response [response]
    (if (not response.ok)
        (settle :unavailable
                (if response.error (tostring response.error) "session list fetch failed"))
        (do
          (local sessions response.data)
          (if (Common.record-array? sessions)
              (do
                (set self.sessions sessions)
                (set self.fetched-at (os.time))
                (settle :ready nil))
              (settle :unavailable "session list response was malformed")))))
  (fn fetch [_self]
    (assert (not dropped) "dropped sessions node cannot fetch")
    (set generation (+ generation 1))
    (local request-generation generation)
    (set self.state :loading)
    (emit)
    (local (ok client) (pcall ensure))
    (if (not ok)
        (settle :unavailable (tostring client))
        (do
          (local failure (try-submit-list! client stale? request-generation on-list-response))
          (when failure
            (settle :unavailable failure)))))
  (fn drop [_self]
    (set dropped true)
    (set generation (+ generation 1))
    (self.changed:clear))
  {:fetch fetch :drop drop})

(fn sessions-actions [self fetch show-config]
  [{:name "Refresh Sessions" :icon "refresh"
    :fn (fn [_button _event] (fetch self))}
   {:name "Show Server Config" :icon "settings"
    :fn (fn [_button _event] (show-config self))}])

(fn OpenCodeSessionsNode [opts]
  (local ensure (if opts.ensure-client opts.ensure-client Common.default-ensure-client))
  (local base
    (GraphNode
      {:key "opencode-sessions"
       :label "opencode sessions"
       :color (glm.vec4 0.45 0.35 0.75 1)
       :sub-color (glm.vec4 0.6 0.5 0.9 1)
       :size 8.0
       :view SessionsView.View :preview SessionsView.Preview}))
  (local self (setmetatable {:ensure-client ensure
                             :state :idle
                             :sessions []
                             :error nil
                             :fetched-at nil
                             :changed (Signal)}
                            {:__index base}))
  (fn emit []
    (self.changed:emit self))
  (fn settle [state message]
    (set self.state state)
    (set self.error message)
    (emit))
  (fn open-session [node session]
    (local graph (assert node.graph "opencode sessions root must be mounted to open a session"))
    (local id (assert session.id "session entry requires id"))
    (local target (graph:resolve-node (.. "opencode-session:" id)))
    (graph:add-edge (GraphEdge {:source node :target target :label "session"}))
    target)
  (fn show-config [node]
    (local graph (assert node.graph "opencode sessions root must be mounted to show config"))
    (local target (graph:resolve-node "opencode-config"))
    (graph:add-edge (GraphEdge {:source node :target target :label "config"}))
    target)

  (fn make-session-node [_self session]
    (SessionNodeModule.OpenCodeSessionNode
      {:id (assert session.id "session entry requires id")
       :session session
       :ensure-client ensure}))
  (local controller (make-controller self ensure settle emit))
  (local base-mount base.mount)
  (fn mount [mounted graph]
    (base-mount mounted graph)
    (when (= mounted.state :idle)
      (mounted:fetch)))
  (tset self :fetch controller.fetch)
  (tset self :drop controller.drop)
  (tset self :mount mount)
  (tset self :open-session open-session)
  (tset self :show-config show-config)
  (tset self :session-label session-label)
  (tset self :make-session-node make-session-node)
  (tset self :actions (sessions-actions self controller.fetch show-config))
  (setmetatable self {:__index base}))

{:OpenCodeSessionsNode OpenCodeSessionsNode
 :session-label session-label}
