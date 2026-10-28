(local glm (require :glm))
(local {:GraphEdge GraphEdge} (require :graph/edge))
(local {:GraphNode GraphNode} (require :graph/node-base))
(local Signal (require :signal))
(local Common (require :graph/nodes/opencode-common))
(local Parts (require :graph/nodes/opencode-parts))

(local make-live (require :graph/nodes/opencode-live))

(fn default-events-factory [client]
  (local Events (require :llm/providers/opencode/events))
  (Events client))

(local SessionView (require :graph/view/views/opencode-session))

;; OpenCode sessions are owned by the OpenCode server. This node is a map-local
;; adapter: it fetches lazily through the app's OpenCode client, keeps only
;; ephemeral snapshots, and never persists or closes the borrowed provider.
;; Transcript composition uses the shared part projection (opencode-parts).

(fn submit-section! [client path stale? request-generation on-ok on-failure finished!]
  (var responded? false)
  (fn deliver! [callback value]
    (when (and (not responded?) (not (stale? request-generation)))
      (set responded? true)
      (callback value)
      (when (not (stale? request-generation)) (finished!))))
  (fn on-response [response] (deliver! on-ok response))
  (fn submit! [] (client.submit "GET" path (Common.get-request on-response)))
  (when (not (stale? request-generation))
    (local (ok err) (pcall submit!))
    (when (not ok)
      ;; Response-handler errors are not network submit failures.
      (if responded? (error err 0) (deliver! on-failure (tostring err))))))

(fn children-response! [self response emit]
  (if (not response.ok)
      (set self.children-error (if response.error (tostring response.error) "children fetch failed"))
      (Common.record-array? response.data)
      (do (set self.subagents response.data) (set self.children-error nil))
      (set self.children-error "children response was malformed"))
  (emit))

(fn make-controller [self id ensure settle emit complete!]
  ;; Requests from superseded fetches or a dropped node must never mutate it.
  (var generation 0)
  (var dropped false)
  (var required {})
  (fn stale? [request-generation]
    (if dropped true (not= request-generation generation)))
  (fn fetch-part! [request-generation client path on-ok on-submit-failure section]
    ;; The generation is captured once by fetch and passed in: rereading the
    ;; mutable counter here would let a superseded invocation's requests pass
    ;; as the newer generation (reentrant fetch during the loading signal).
    (fn finished! []
      (when section (tset required section nil))
      (when (and self.snapshot-in-flight? (not required.session) (not required.messages))
        (set self.snapshot-in-flight? false)
        (complete!)))
    (submit-section! client path stale? request-generation on-ok on-submit-failure finished!))
  (fn config-submit-failed [message]
    (set self.config-error message)
    (emit))
  (fn transcript-submit-failed [message]
    (set self.messages-stale false)
    (set self.transcript-error message)
    (emit))
  (fn session-submit-failed [message]
    (settle :unavailable message))
  (fn on-session-response [response]
    (if (not response.ok)
        (if (= response.status 404)
            (settle :not-found (.. "session " id " not found"))
            (settle :unavailable
                    (if response.error (tostring response.error) "session fetch failed")))
        (do
          (local session response.data)
          (if (and (= (type session) :table) session.id)
              (do
                (set self.session session)
                (set self.fetched-at (os.time))
                (settle :ready nil))
              (settle :unavailable "session response was malformed")))))
  (fn on-messages-response [response]
    ;; The transcript refresh completes even when it fails: stale data stays
    ;; visible but is no longer marked refreshing.
    (set self.messages-stale false)
    (if (not response.ok)
        (do
          (set self.transcript-error
               (if response.error (tostring response.error) "transcript fetch failed"))
          (emit))
        (do
          (local messages response.data)
          (if (Common.message-array? messages)
              (do
                (set self.messages messages)
                (set self.transcript-error nil)
                (emit))
              (do
                (set self.transcript-error "messages response was malformed")
                (emit))))))
  (fn on-config-response [response]
    (set self.config-error
         (if response.ok
             nil
             (if response.error (tostring response.error) "config unavailable")))
    (emit))
  (fn children-submit-failed [message]
    (set self.children-error message)
    (emit))
  (fn on-children-response [response]
    (children-response! self response emit))
  (fn fetch [_self]
    (assert (not dropped) "dropped session node cannot fetch")
    (set generation (+ generation 1))
    (local request-generation generation)
    (set required {:session true :messages true})
    (set self.snapshot-in-flight? true)
    (set self.state :loading)
    ;; Old messages stay visible during a refresh but are marked stale until
    ;; this generation's transcript settles, so stale content cannot pose as
    ;; current.
    (set self.messages-stale true)
    (emit)
    (local (ok client) (pcall ensure))
    (if (not ok)
        (do
          (set self.messages-stale false)
          (set self.snapshot-in-flight? false)
          (settle :unavailable (tostring client))
          (complete!))
        (do
          (fetch-part! request-generation client "/config" on-config-response config-submit-failed)
          (fetch-part! request-generation client (.. "/session/" id "/children") on-children-response children-submit-failed)
          (fetch-part! request-generation client (.. "/session/" id "/message") on-messages-response transcript-submit-failed :messages)
          (fetch-part! request-generation client (.. "/session/" id) on-session-response session-submit-failed :session))))
  (fn drop [_self]
    (set dropped true)
    (set generation (+ generation 1))
    (set self.snapshot-in-flight? false)
    (set self.pending-invalidation false)
    (self.changed:clear))
  {:fetch fetch :drop drop :dropped? (fn [] dropped) :emit emit})

(fn session-actions [self fetch expand-children abort delete-session]
  [{:name "Refresh Session" :icon "refresh"
    :fn (fn [_button _event] (fetch self))}
   {:name "Expand subagent sessions" :icon "account_tree"
    :fn (fn [_button _event] (expand-children self))}
   {:name "Abort Session" :icon "close"
    :fn (fn [_button _event] (abort self))}
   {:name "Delete Session" :icon "delete"
    :fn (fn [_button _event] (delete-session self))}])

(fn expand-children [node]
  ;; Children are sessions; the tree is topology over the existing scheme.
  (local graph (assert node.graph "opencode session node must be mounted to expand children"))
  (local subagents (if node.subagents node.subagents []))
  (each [_ child (ipairs subagents)]
    (when child.id
      (local target (graph:resolve-node (.. "opencode-session:" (tostring child.id))))
      (graph:add-edge (GraphEdge {:source node :target target :label "subagent"})))))

(fn try-submit-abort! [client id on-ok]
  (local (submitted err)
    (pcall
      (fn []
        (client.submit "POST" (.. "/session/" id "/abort")
          (Common.get-request on-ok)))))
  (if submitted nil (tostring err)))

(fn make-abort [self id ensure fetch dropped? emit]
  ;; Acknowledged (HTTP ok) is not observed termination: the raw result is
  ;; recorded (scalar JSON bodies arrive as raw strings — truthiness must not
  ;; decide success), ambiguous outcomes are never retried, and the refresh
  ;; runs only after acknowledgment. Abort outcome stays separate from fetch
  ;; outcome.
  (fn on-abort-response [response]
    (set self.abort-state (if response.ok :acknowledged :failed))
    (set self.abort-result
         (if response.ok
             (if response.data (tostring response.data) "no body")
             nil))
    (set self.abort-error
         (if response.ok
             nil
             (if response.error (tostring response.error) "abort failed")))
    (emit)
    (when response.ok
      (fetch self)))
  (fn submit-abort! [client]
    (try-submit-abort! client id
                       (fn [response]
                         (when (not (dropped?))
                           (on-abort-response response)))))
  (fn acquire-client! []
    ;; Returns the client, or nil after surfacing the failure on the node.
    (local (ok client) (pcall ensure))
    (if ok
        client
        (do
          (set self.abort-state :failed)
          (set self.abort-error (tostring client))
          (emit)
          nil)))
  (fn abort [_abort-self]
    (assert (not (dropped?)) "dropped session node cannot abort")
    (if (= self.abort-state :pending)
        nil
        (do
          (set self.abort-state :pending)
          (set self.abort-error nil)
          (set self.abort-result nil)
          (emit)
          (local client (acquire-client!))
          (local failure (if client (submit-abort! client) nil))
          (when failure
            (set self.abort-state :failed)
            (set self.abort-error failure)
            (emit)))))
  abort)

(fn try-submit-session-delete! [client id on-ok]
  (local (submitted err)
    (pcall
      (fn []
        (client.submit "DELETE" (.. "/session/" id)
          (Common.get-request on-ok)))))
  (if submitted nil (tostring err)))

(fn make-delete [self id ensure dropped? emit]
  ;; Deleting the session removes the server-owned record (messages go with
  ;; it). Acknowledgment records the raw body; the node then removes itself
  ;; from the map — the run's artifact reference survives as provenance, and
  ;; re-materializing a deleted session surfaces an explicit not-found.
  (fn on-delete-response [response]
    (set self.delete-state (if response.ok :acknowledged :failed))
    (set self.delete-result
         (if response.ok
             (if response.data (tostring response.data) "no body")
             nil))
    (set self.delete-error
         (if response.ok
             nil
             (if response.error (tostring response.error) "delete failed")))
    (emit)
    (when (and response.ok self.graph)
      (self.graph:remove-nodes [self] {:cause "session-deleted"})))
  (fn submit-delete! [client]
    (try-submit-session-delete! client id
                                (fn [response]
                                  (when (not (dropped?))
                                    (on-delete-response response)))))
  (fn acquire-client! []
    (local (ok client) (pcall ensure))
    (if ok
        client
        (do
          (set self.delete-state :failed)
          (set self.delete-error (tostring client))
          (emit)
          nil)))
  (fn delete-session [_delete-self]
    (assert (not (dropped?)) "dropped session node cannot delete")
    (if (= self.delete-state :pending)
        nil
        (do
          (set self.delete-state :pending)
          (set self.delete-error nil)
          (set self.delete-result nil)
          (emit)
          (local client (acquire-client!))
          (local failure (if client (submit-delete! client) nil))
          (when failure
            (set self.delete-state :failed)
            (set self.delete-error failure)
            (emit)))))
  delete-session)

(fn OpenCodeSessionNode [opts]
  (local id (assert opts.id "opencode session node requires id"))
  (assert (Common.url-safe-id? id) "opencode session id must be a non-empty url-safe identifier")
  (local ensure (if opts.ensure-client opts.ensure-client Common.default-ensure-client))
  (local events-factory (if opts.events-factory opts.events-factory default-events-factory))
  (local base
    (GraphNode
      {:key (.. "opencode-session:" id)
       :label (if (and opts.session opts.session.title)
                (tostring opts.session.title)
                (.. "OpenCode session " id))
       :color (glm.vec4 0.45 0.35 0.75 1)
       :sub-color (glm.vec4 0.6 0.5 0.9 1)
       :size 8.0
       :view SessionView.View :preview SessionView.Preview}))
  (local self (setmetatable {:id id :ensure-client ensure
                             :state :idle :session nil :messages nil
                             :subagents nil :children-error nil
                             :transcript-error nil :config-error nil
                             :messages-stale nil
                             :abort-state nil :abort-error nil :abort-result nil
                             :delete-state nil :delete-error nil :delete-result nil
                             :live-state nil
                             :pending-invalidation false
                             :fetched-at nil :error nil
                             :changed (Signal)}
                            {:__index base}))
  (fn refresh-label []
    (set self.label
         (if (and self.session self.session.title)
             (tostring self.session.title)
             (.. "OpenCode session " id))))
  (fn emit []
    (refresh-label)
    (self.changed:emit self))
  (var invalidate! nil)
  (fn settle [state message]
    (set self.state state)
    (set self.error message)
    (emit))
  (fn snapshot-complete! []
    (local pending? self.pending-invalidation)
    (set self.pending-invalidation false)
    (when (and pending? (= self.state :ready) (not self.transcript-error)) (invalidate!)))
  (fn compose [_self]
    (Parts.compose-transcript self.messages))
  (fn open-messages [node]
    ;; Messages (transcript + list) are a projection child of this adapter.
    (local graph (assert node.graph "opencode session node must be mounted to open messages"))
    (local target (graph:resolve-node (.. "opencode-session-messages:" (tostring node.id))))
    (graph:add-edge (GraphEdge {:source node :target target :label "messages"}))
    target)

  (fn open-message [node message]
    ;; Message nodes are projections of this adapter's snapshot; the graph
    ;; resolves the message key to a map-local message node.
    (local graph (assert node.graph "opencode session node must be mounted to open a message"))
    (local info (if message.info message.info {}))
    (local message-id (assert info.id "message requires id"))
    (local target (graph:resolve-node (.. "opencode-session-message:" (tostring node.id) "/" (tostring message-id))))
    (graph:add-edge (GraphEdge {:source node :target target :label "message"}))
    target)

  (local controller (make-controller self id ensure settle emit snapshot-complete!))
  (set invalidate! (fn []
                    (when (not (controller.dropped?))
                      (if self.snapshot-in-flight?
                          (set self.pending-invalidation true)
                          (controller.fetch self)))))
  (local delete-session (make-delete self id ensure controller.dropped? emit))
  (local base-mount base.mount)
  (local live (make-live self id ensure invalidate! emit opts.timer-factory))
  (fn mount [mounted graph]
    (base-mount mounted graph)
    (when (= mounted.state :idle)
      (mounted:fetch)))
  (fn drop-with-live [dropped]
    (live.stop!)
    (controller.drop dropped))
  ;; Every fetch re-ensures the live stream first: a refresh after a
  ;; previously-unavailable provider brings the subscription up too, keeping
  ;; subscribe-then-snapshot ordering on every snapshot.
  (fn fetch-with-live [fetched]
    (assert (not (controller.dropped?)) "dropped session node cannot fetch")
    (set self.pending-invalidation false)
    (live.start! true)
    (controller.fetch fetched))
  (local abort (make-abort self id ensure fetch-with-live controller.dropped? emit))
  (tset self :fetch fetch-with-live)
  (tset self :abort abort)
  (tset self :delete-session delete-session)
  (tset self :drop drop-with-live)
  (tset self :mount mount)
  (tset self :compose-transcript compose)
  (tset self :open-message open-message)
  (tset self :open-messages open-messages)
  (tset self :events-factory events-factory)
  (tset self :actions (session-actions self fetch-with-live expand-children abort delete-session))
  (setmetatable self {:__index base}))

{:OpenCodeSessionNode OpenCodeSessionNode
 :compose-transcript Parts.compose-transcript}
