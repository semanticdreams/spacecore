;; Shared plumbing for the read-only OpenCode session graph exposure.
(local {:GraphEdge GraphEdge} (require :graph/edge))

(fn get-request [on-response]
  ;; Explicit deadlines: the OpenCode client defaults to no timeout.
  {:timeout-ms 15000 :on_response on-response})

(fn guarded-response [stale? request-generation on-ok]
  (fn [response]
    (when (not (stale? request-generation))
      (on-ok response))))

(fn url-safe-id? [id]
  (and (= (type id) :string) (string.match id "^[%w%-_]+$")))

(fn record-array? [value]
  ;; Lua represents empty JSON arrays and objects identically. Nonempty
  ;; lists must nevertheless be dense arrays of records, never error maps.
  (var valid? (= (type value) :table))
  (when valid?
    (local count (length value))
    (each [key item (pairs value)]
      (when (not (and (= (type key) :number) (= key (math.floor key))
                      (>= key 1) (<= key count) (= (type item) :table)))
        (set valid? false))))
  valid?)

(fn message-array? [value]
  (var valid? (record-array? value))
  (when valid?
    (each [_ message (ipairs value)]
      (when (not (and (= (type message.info) :table)
                      (record-array? message.parts)))
        (set valid? false))))
  valid?)

(local forced-info-fields {:system true :tools true :time true :path true :error true})
(local scalar-order {:id 1 :role 2 :modelID 3 :providerID 4 :agent 5 :mode 6
                     :cost 7 :tokens 8 :finish 9 :summary 10 :parentID 11})
(local scalar-labels {:id "Id" :role "Role" :modelID "Model" :providerID "Provider"
                      :agent "Agent" :mode "Mode" :cost "Cost" :tokens "Tokens"
                      :finish "Finish" :summary "Summary" :parentID "Parent"})
(local complex-order {:system 1 :tools 2 :time 3 :path 4 :error 5})

(fn escape-field-byte [byte] (string.format "%%%02X" (string.byte byte)))
(fn encode-info-field [field]
  (assert (= (type field) :string) "info field must be a string")
  (assert (utf8.len field) "info field must be valid UTF-8")
  (local encoded (string.gsub field "[^A-Za-z0-9%-]" escape-field-byte))
  (if (= field "") "~" encoded))

(fn unescape-field-byte [hex] (string.char (tonumber hex 16)))
(fn decode-info-field [segment]
  (if (= segment "~") ""
      (not (= (type segment) :string)) nil
      (= segment "") nil
      (do
        (local decoded (string.gsub segment "%%(%x%x)" unescape-field-byte))
        (when (and (utf8.len decoded) (= (encode-info-field decoded) segment)) decoded))))

(fn sort-info-fields! [keys order]
  (fn less? [left right]
    (local left-rank (if (. order left) (. order left) 999))
    (local right-rank (if (. order right) (. order right) 999))
    (if (= left-rank right-rank) (< left right) (< left-rank right-rank)))
  (table.sort keys less?))

(fn info-projection [info]
  (local scalars [])
  (local complex [])
  (each [field value (pairs info)]
    (assert (= (type field) :string) "message info must contain string field names")
    (if (or (. forced-info-fields field) (= (type value) :table))
        (table.insert complex field)
        (table.insert scalars field)))
  (sort-info-fields! scalars scalar-order)
  (sort-info-fields! complex complex-order)
  {:scalars (icollect [_ field (ipairs scalars)]
              {:field field :label (if (. scalar-labels field) (. scalar-labels field) field)
               :value (. info field)})
   :complex complex})

(fn default-ensure-client []
  (local providers (assert app.agent-providers "OpenCode sessions require app.agent-providers"))
  (local provider
    (if (. providers :opencode)
        (. providers :opencode)
        ((assert (. providers :opencode-factory)
                 "OpenCode sessions require app.agent-providers.opencode-factory"))))
  (assert provider.client "OpenCode provider requires a client")
  provider.client)

(fn disconnect-parent [self]
  (when (and self.parent self.parent-handler)
    (self.parent.changed:disconnect self.parent-handler true)
    (set self.parent-handler nil))
  (set self.parent nil))

(fn parent-observer [recompute]
  (fn [_updated] (recompute)))

(fn connect-parent [self parent-key recompute]
  (local parent (self.graph:resolve-node parent-key))
  (when parent
    (set self.parent parent)
    (set self.parent-handler
         (parent.changed:connect (parent-observer recompute))))
  parent)

(fn on-parent-replaced [self parent-key recompute payload]
  (when (and self.projection-active? self.parent payload.new (= payload.old self.parent))
    (disconnect-parent self)
    (connect-parent self parent-key recompute)
    (recompute)))

(fn parent-in-removal [self payload]
  (var found? false)
  (each [_ removed (ipairs (if payload.nodes payload.nodes []))]
    (when (= removed self.parent)
      (set found? true)))
  found?)

(fn on-parent-removed [self recompute payload]
  (when (and self.projection-active? (parent-in-removal self payload))
    (set self.parent-removed? true)
    (disconnect-parent self)
    (recompute)))

(fn projection-mount [self base parent-key recompute mounted graph]
  ;; Common mount for snapshot-projection nodes: they read a parent
  ;; adapter's snapshot instead of fetching. Base mount first so self.graph
  ;; exists; parent binding by key; graph replacement/removal signals rebind
  ;; or mark the parent gone. A deliberately removed parent is never
  ;; recreated automatically — the node stays explicitly non-ready.
  ;; The mounted graph is retained separately: GraphMap unmounts (clearing
  ;; self.graph) BEFORE drop on the normal removal path, so drop-time
  ;; cleanup (graph handlers, islands) needs the retained reference.
  (base.mount mounted graph)
  (set self.mounted-graph graph)
  (set self.projection-active? true)
  (set self.preserve-island? false)
  (set self.replaced-handler
       (graph.node-replaced:connect
          (fn [payload]
            (on-parent-replaced self parent-key recompute payload)
            (when (and self.projection-active? (= payload.new self)) (recompute)))))
  (set self.removed-handler
       (graph.node-removed:connect
          (fn [payload] (on-parent-removed self recompute payload))))
  (set self.published-handler
       (graph.node-added:connect
         (fn [payload] (when (= payload.node self) (recompute)))))
  (set self.installed-handler (graph.topology-installed:connect (parent-observer recompute)))
  (local parent (connect-parent self parent-key recompute))
  (when (and parent (= parent.state :idle))
    (parent:fetch))
  (recompute))

(fn island-origin [graph node]
  (local point (and graph graph.presentation-points
                    (. graph.presentation-points node.key)))
  (local position (and point point.position))
  (if position
      [(+ position.x 24) position.y position.z]
      [24 0 0]))

(fn island-publication-current? [node graph member-keys]
  (and node.projection-active? (= node.state :ready)
       (= node.mounted-graph graph) (not graph.installing-topology?)
       (not node.stale?) (not node.transcript-error)
       (= (graph:lookup node.key) node)
       (= node.desired-island-keys member-keys)))

(fn publish-ordered-island [node island-id member-keys edge-label]
  ;; Publish an ordered-list island over the node's children. Islands do
  ;; not hydrate: every member is resolved into the mounted map BEFORE
  ;; publication, in snapshot order; resolution failure is explicit.
  ;; Existing islands (including ownerless restored ones) are adopted:
  ;; members re-sync, saved position/state preserved (state omitted).
  ;; The enumeration owner authors ordinary display edges, independently of
  ;; island membership. Resolve the full pass first; failures remain explicit,
  ;; not transactional. Synchronous listeners may supersede or drop this pass.
  (local graph (assert node.mounted-graph "island sync requires a mounted graph"))
  (local resolved [])
  (local targets [])
  (var current? true)
  (each [_ key (ipairs member-keys)]
    (when current?
      (local target (graph:resolve-node key))
      (set current? (island-publication-current? node graph member-keys))
      (when current?
        (assert target (.. "island member failed to materialize: " (tostring key)))
        (table.insert resolved key)
        (table.insert targets target))))
  (each [i target (ipairs targets)]
    (when current?
      (set current? (and (island-publication-current? node graph member-keys)
                        (= (graph:lookup (. resolved i)) target)))
      (when current?
        ;; GraphMap explicit identity excludes the label. Preserve existing
        ;; edges (including custom metadata) without redundant notifications.
        (when (not (. graph.edge-map (.. node.key "->" target.key)))
          (graph:add-edge (GraphEdge {:source node :target target :label edge-label})))
        (set current? (island-publication-current? node graph member-keys)))))
  (each [i target (ipairs targets)]
    (when (not (= (graph:lookup (. resolved i)) target))
      (set current? false)))
  (when current?
    (local existing (graph:get-island island-id))
    (if (> (length resolved) 0)
        (if existing
            (graph:upsert-island {:id island-id :kind "ordered-list" :members resolved})
            (graph:upsert-island {:id island-id :kind "ordered-list"
                                  :members resolved
                                  :state {:list-key node.key
                                          :interaction-policy "snap-back"
                                          :spacing 24
                                          :position (island-origin graph node)}}))
        (when existing
          (graph:remove-island island-id))))
  resolved)

(fn drain-island [node island-id edge-label]
  (local graph node.mounted-graph)
  (while (and node.island-dirty?
              (island-publication-current? node graph node.desired-island-keys))
    (set node.island-dirty? false)
    (publish-ordered-island node island-id node.desired-island-keys edge-label)))

(fn sync-ordered-island [node island-id member-keys edge-label]
  (local graph (assert node.mounted-graph "island sync requires a mounted graph"))
  (assert (and (= (type edge-label) :string) (> (length edge-label) 0))
          "island enumeration requires a relationship edge label")
  (set node.desired-island-keys member-keys)
  (set node.island-dirty? true)
  ;; Mount happens before map publication. Saved topology is authoritative
  ;; until its installation barrier completes. Neither window may hydrate.
  (when (and (island-publication-current? node graph member-keys)
             (not node.island-syncing?))
    (set node.island-syncing? true)
    (local (ok err) (pcall drain-island node island-id edge-label))
    (set node.island-syncing? false)
    (when (not ok) (error err 0))))

(fn island-cleaner [node island-id]
  ;; Idempotent island teardown bound to the node's drop path.
  (fn []
    (local graph (if node.graph node.graph node.mounted-graph))
    (when (and graph (not graph.installing-topology?) (not node.preserve-island?)
               (graph:get-island island-id))
      (graph:remove-island island-id))))

(fn projection-unmount [self context]
  (set self.preserve-island? (and context (= context.cause "replacement")))
  (set self.graph nil))

(fn parent-availability [self parent]
  ;; Shared prefix of every projection node's recompute: parent lifecycle
  ;; maps to projection state before any data is read. Returns (state error)
  ;; to apply directly, or (nil nil) when the parent is ready and the caller
  ;; resolves data presence itself.
  (when parent
    (set self.transcript-error parent.transcript-error)
    (set self.stale? (if parent.messages-stale parent.messages-stale parent.stale?)))
  (if self.parent-removed?
      (values :unavailable "parent adapter was removed from the map")
      (not parent)
      (values :idle nil)
      (= parent.state :loading)
      (values :loading nil)
      (= parent.state :unavailable)
      (values :unavailable parent.error)
      (= parent.state :not-found)
      (values :not-found parent.error)
      (= parent.state :absent)
      (values :absent
              (if parent.error parent.error
                "parent not present in the current snapshot"))
      (values nil nil)))

(fn projection-drop [self]
  (set self.projection-active? false)
  (local graph (if self.graph self.graph self.mounted-graph))
  (when (and graph self.replaced-handler)
    (graph.node-replaced:disconnect self.replaced-handler true))
  (when (and graph self.removed-handler)
    (graph.node-removed:disconnect self.removed-handler true))
  (when (and graph self.published-handler)
    (graph.node-added:disconnect self.published-handler true))
  (when (and graph self.installed-handler)
    (graph.topology-installed:disconnect self.installed-handler true))
  (set self.replaced-handler nil)
  (set self.removed-handler nil)
  (set self.published-handler nil)
  (set self.installed-handler nil)
  (disconnect-parent self)
  (self.changed:clear)
  (when self.cleanup-island! (self:cleanup-island!))
  (set self.mounted-graph nil))

(fn validated-ids [items]
  ;; Parts/info enumeration keys on validated, unique url-safe ids. Items
  ;; without one are addressable in views but never clickable nodes.
  (local out {})
  (var seen {})
  (each [_ item (ipairs (if items items []))]
    (local id (if (and item item.id) (tostring item.id) nil))
    (local valid? (and id (url-safe-id? id) (not (. seen id))))
    (table.insert out {:id id :valid? valid? :item item})
    (when valid?
      (tset seen id true)))
  out)

{:encode-info-field encode-info-field
 :decode-info-field decode-info-field
 :info-projection info-projection
 :record-array? record-array?
 :message-array? message-array?
 :parent-availability parent-availability
 :sync-ordered-island sync-ordered-island
 :island-cleaner island-cleaner
 :get-request get-request
 :guarded-response guarded-response
 :url-safe-id? url-safe-id?
 :default-ensure-client default-ensure-client
 :projection-mount projection-mount
 :projection-drop projection-drop
 :projection-unmount projection-unmount
 :validated-ids validated-ids}
