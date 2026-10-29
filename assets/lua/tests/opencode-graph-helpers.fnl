(local BuildContext (require :build-context))
(local OpencodeSessionsExtension (require :graph/extensions/builtins/opencode-sessions))
(local {:OpenCodeSessionNode OpenCodeSessionNode} (require :graph/nodes/opencode-session))
(local {:OpenCodeSessionMessageNode MessageNode} (require :graph/nodes/opencode-session-message))
(local Signal (require :signal))

;; Shared fixtures for the OpenCode graph test modules. Real-map island and
;; hydration coverage lives in test-opencode-map-lifecycle, not this unit fake.

(fn ok-response [data] {:ok true :status 200 :data data})
(fn err-response [status error] {:ok false :status status :error error})

(fn make-client-stub []
  (local stub {:pending []})
  (set stub.submit
       ;; The real OpenCode client.submit is a plain function (dot call).
       (fn [_method _path request]
         (assert (= (type request.on_response) :function) "stub requires on_response")
         (table.insert stub.pending {:method _method :path _path :respond request.on_response})
         nil))
  stub)

(fn ensure-from [client]
  (fn [] client))

(fn pending-for [client path]
  (local matched [])
  (each [_ request (ipairs client.pending)]
    (when (= request.path path)
      (table.insert matched request)))
  matched)

(fn deliver [client path response]
  ;; Delivers to the most recent matching request: superseded older requests
  ;; stay deliverable via pending-for when a test wants to exercise staleness.
  (var target nil)
  (each [_ request (ipairs client.pending)]
    (when (= request.path path)
      (set target request)))
  (assert target (.. "no pending request for path " path))
  (target.respond response))

(fn make-session-node [client-stub]
  (fn unsubscribe [] nil)
  (fn subscribe [_on-event _on-health] {:unsubscribe unsubscribe})
  (fn events [_client] {:subscribe-with-health subscribe})
  (local node (OpenCodeSessionNode {:id "ses_1"
                                    :ensure-client (ensure-from client-stub) :events-factory events}))
  node)

(fn install-descriptor [descriptors graph]
  (local handles [])
  (each [_ descriptor (ipairs descriptors)]
    (each [_ handle (ipairs (descriptor.install-loaders graph
                              {:owner-id descriptor.id :extension-id descriptor.id}))]
      (table.insert handles handle)))
  handles)

(fn loader-for [handles scheme]
  (var loader nil)
  (each [_ handle (ipairs handles)]
    (when (and (not loader) (= handle.scheme scheme))
      (set loader handle.loader)))
  (assert loader (.. "no loader registered for " scheme))
  loader)

(fn make-recording-graph []
  (local registrations [])
  (fn register-key-loader [_self scheme loader-fn _opts]
    (table.insert registrations {:scheme scheme :loader loader-fn})
    {:scheme scheme :loader loader-fn :unregister (fn [_self] nil)})
  {:register-key-loader register-key-loader})

;; -- session view -------------------------------------------------------------

(fn viewport-head [input]
  (local viewport (input.buffer:get-viewport {:line 0 :column 0 :lines 24 :columns 120}))
  (local parts [])
  (each [_ row (ipairs viewport.rows)]
    (table.insert parts (if row.text row.text "")))
  (table.concat parts "\n"))

(fn noop-handler [_self _obj] nil)

(fn make-clickables-stub []
  (assert {:register noop-handler :unregister noop-handler
           :register-right-click noop-handler :unregister-right-click noop-handler
           :register-double-click noop-handler :unregister-double-click noop-handler}
          "view test requires clickables stub"))

(fn make-hoverables-stub []
  {:register noop-handler :unregister noop-handler})

(fn make-view-ctx []
  (local glyph {:advance 1})
  (local font {:metadata {:metrics {:ascender 1 :descender -1}
                          :atlas {:width 1 :height 1}}
               :glyph-map {4242 glyph}
               :advance 1})
  (local icons {:font font :codepoints {:refresh 4242 :format_list_bulleted 4242 :first_page 4242
                                        :chevron_left 4242 :chevron_right 4242
                                        :last_page 4242}})
  (set icons.get
       (fn [self name]
         (local value (. self.codepoints name))
         (assert value (.. "Missing icon " name))
         value))
  (set icons.resolve
       (fn [self name]
         (local code (self:get name))
         {:type :font :codepoint code :font self.font}))
  (BuildContext {:clickables (make-clickables-stub)
                 :hoverables (make-hoverables-stub)
                 :icons icons}))

(fn ready-session-node []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (deliver client "/config" (ok-response {:theme "dark"}))
  (deliver client "/session/ses_1/message"
           (ok-response [{:info {:id "msg-1" :role "user"}
                          :parts [{:type "text" :text "Analyze the books file."}]}
                         {:info {:id "msg-2" :role "assistant"}
                          :parts [{:type "reasoning" :text "reading the file"}
                                  {:type "text" :text "Done."}]}]))
  (deliver client "/session/ses_1" (ok-response {:id "ses_1" :title "Books import analysis"}))
  (deliver client "/session/ses_1/children" (ok-response []))
  node)

(fn body-of [built]
  ;; Message views expose preview-input (the compact transcript input);
  ;; session/code-run views expose body or section inputs.
  (local accessor (or built.preview-input built.content-input built.body))
  (assert accessor "view must expose a payload input")
  (if (= (type accessor) :function) (accessor) accessor))

(fn edge-identity [edge]
  (.. edge.source.key "->" edge.target.key))

(fn add-deduped-edge [graph edge]
  ;; Real-map explicit identity is endpoint-only. Re-adding replaces the
  ;; record rather than adding another edge, even when its label differs.
  (local key (edge-identity edge))
  (local existing (. graph.edge-map key))
  (if existing
      (do
        (each [i e (ipairs graph.edges)]
          (when (= e existing) (tset graph.edges i edge)))
        ;; Real-map add-edge replacement emits edge-added alongside record replacement.
        (when graph.edge-added
          (graph.edge-added:emit {:edge edge})))
      (table.insert graph.edges edge))
  (tset graph.edge-map key edge)
  edge)

(fn fake-parent-graph []
  (local graph {:resolved [] :edges [] :edge-map {} :nodes {} :removals []
                :islands {} :island-history []
                :node-added (Signal) :edge-added (Signal)
                :topology-installed (Signal)
                :node-replaced (Signal) :node-removed (Signal)})
  (set graph.lookup (fn [_self key] (. graph.nodes key)))
  (set graph.upsert-island
       (fn [_self island]
         (local existing (. graph.islands island.id))
         (local record
           (if (and existing (not island.state))
               ;; update without state preserves the existing record state
               (do
                 (local merged {})
                 (each [k v (pairs existing)] (tset merged k v))
                 (tset merged :members island.members)
                 merged)
               island))
         (tset graph.islands island.id record)
         (table.insert graph.island-history {:id island.id :members island.members
                                             :state island.state})
         record))
  (set graph.get-island
       (fn [_self id] (. graph.islands id)))
  (set graph.remove-island
       (fn [_self id]
         (local existing (. graph.islands id))
         (tset graph.islands id nil)
         existing))
  (set graph.resolve-node
       (fn [_self key]
         (table.insert graph.resolved key)
         (local existing (. graph.nodes key))
         (if existing
             existing
             (do
               (local created (make-session-node (make-client-stub)))
               (set created.key key)
               (tset graph.nodes key created)
               created))))
  (set graph.add-edge
       (fn [_self edge] (add-deduped-edge graph edge)))
  (set graph.remove-nodes
       (fn [_self nodes opts]
         (table.insert graph.removals {:nodes nodes :opts opts})))
  graph)

(fn ready-parent-with-messages []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (deliver client "/session/ses_1/message"
           (ok-response [{:info {:id "msg-a" :role "user"}
                          :parts [{:type "text" :text "question"}]}
                         {:info {:id "msg-b" :role "assistant"
                                 :modelID "glm" :providerID "opencode-go"}
                          :parts [{:type "tool" :tool "read" :callID "c1"
                                   :state {:status "completed" :title "Read file"
                                           :input {:path "x"} :output "data"}}
                                  {:type "text" :text "answer"}]}]))
  (deliver client "/session/ses_1" (ok-response {:id "ses_1" :title "t"}))
  node)

(fn make-ready-message-parent [parts]
  (local parent (MessageNode {:session-id "ses_1" :message-id "msg-b"}))
  (set parent.state :ready)
  (set parent.message {:info {:id "msg-b" :role "assistant"} :parts parts})
  parent)

{:ok-response ok-response
 :err-response err-response
 :make-client-stub make-client-stub
 :ensure-from ensure-from
 :pending-for pending-for
 :deliver deliver
 :make-session-node make-session-node
 :install-descriptor install-descriptor
 :loader-for loader-for
 :make-recording-graph make-recording-graph
 :viewport-head viewport-head
 :noop-handler noop-handler
 :make-clickables-stub make-clickables-stub
 :make-hoverables-stub make-hoverables-stub
 :make-view-ctx make-view-ctx
 :ready-session-node ready-session-node
 :body-of body-of
 :fake-parent-graph fake-parent-graph
 :ready-parent-with-messages ready-parent-with-messages
 :make-ready-message-parent make-ready-message-parent}
