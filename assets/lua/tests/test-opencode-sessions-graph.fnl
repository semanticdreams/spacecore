(local tests [])
(local BuildContext (require :build-context))
(local OpencodeSessionsExtension (require :graph/extensions/builtins/opencode-sessions))
(local {:OpenCodeSessionNode OpenCodeSessionNode} (require :graph/nodes/opencode-session))
(local {:OpenCodeSessionsNode OpenCodeSessionsNode} (require :graph/nodes/opencode-sessions))
(local SessionViews (require :graph/view/views/opencode-session))
(local H (require :tests.opencode-graph-helpers))
(local ok-response H.ok-response)
(local err-response H.err-response)
(local make-client-stub H.make-client-stub)
(local ensure-from H.ensure-from)
(local pending-for H.pending-for)
(local deliver H.deliver)
(local make-session-node H.make-session-node)
(local install-descriptor H.install-descriptor)
(local loader-for H.loader-for)
(local make-recording-graph H.make-recording-graph)
(local viewport-head H.viewport-head)
(local make-clickables-stub H.make-clickables-stub)
(local make-hoverables-stub H.make-hoverables-stub)
(local make-view-ctx H.make-view-ctx)
(local ready-session-node H.ready-session-node)
(local body-of H.body-of)
(local fake-parent-graph H.fake-parent-graph)
(local ready-parent-with-messages H.ready-parent-with-messages)
(local make-ready-message-parent H.make-ready-message-parent)

;; -- fakes -------------------------------------------------------------------

;; -- session node fetch states ------------------------------------------------

(fn test-session-fetch-reaches-ready-with-transcript []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (assert (= node.state :loading) (.. "fetch must enter loading, got " (tostring node.state)))
  (assert (> (length client.pending) 0) "fetch must issue requests")
  (deliver client "/config" (ok-response {:theme "dark"}))
  (deliver client "/session/ses_1/message"
           (ok-response [{:info {:id "msg-1" :role "user"}
                          :parts [{:type "text" :text "Hello"}]}
                         {:info {:id "msg-2" :role "assistant"
                                 :model {:providerID "anthropic" :modelID "claude"}}
                          :parts [{:type "reasoning" :text "pondering"}
                                  {:type "text" :text "Hi!"}
                                  {:type "step-start"}]}]))
  (assert (= node.state :loading) "transcript delivery alone must not settle the session")
  (assert (= node.session nil) "metadata arrives with the session response")
  (deliver client "/session/ses_1" (ok-response {:id "ses_1" :title "Books import analysis"}))
  (deliver client "/session/ses_1/children"
           (ok-response [{:id "ses_child" :title "Child session"}]))
  (assert (= node.state :ready) (tostring node.state))
  (assert (= node.label "Books import analysis") "ready label must use the session title")
  (assert (= (length node.subagents) 1) "subagents must be captured for expansion")
  (assert (= node.children-error nil) "successful children fetch must clear the error")
  (local transcript (node:compose-transcript))
  (assert (string.find transcript "## user" 1 true) "transcript must mark roles")
  (assert (string.find transcript "[thinking]" 1 true) "transcript must mark reasoning parts")
  (assert (string.find transcript "Hi!" 1 true) "transcript must keep text parts")
  (assert (not (string.find transcript "step-start" 1 true)) "step noise must collapse out of transcripts")
  (assert (string.find transcript "pondering" 1 true) "reasoning text must be preserved")
  (assert (= node.config-error nil) "successful config fetch must clear the config error")
  (node:drop))

(fn test-session-404-resolves-not-found []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (deliver client "/session/ses_1" (err-response 404 "not found"))
  (assert (= node.state :not-found) (tostring node.state))
  (assert (string.find (tostring node.error) "not found" 1 true))
  (node:drop))

(fn test-session-transport-failure-is-unavailable-not-deletion []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (deliver client "/session/ses_1" (err-response 0 "connection refused"))
  (assert (= node.state :unavailable) "an outage must not resolve as not-found")
  (node:drop))

(fn test-session-unavailable-ensure-client []
  (local failing-ensure (fn [] (error "providers missing")))
  (local node (OpenCodeSessionNode {:id "ses_1"
                                    :ensure-client failing-ensure}))
  (node:fetch)
  (assert (= node.state :unavailable) "provider resolution failure must surface explicitly")
  (assert (string.find (tostring node.error) "providers missing" 1 true))
  (node:drop))

(fn test-session-malformed-messages-keep-session-ready []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (deliver client "/config" (ok-response {}))
  (deliver client "/session/ses_1/message" (ok-response "not-a-table"))
  (deliver client "/session/ses_1" (ok-response {:id "ses_1" :title "t"}))
  (assert (= node.state :ready))
  (assert (string.find (tostring node.transcript-error) "malformed" 1 true))
  (node:drop))

(fn test-session-stale-responses-are-ignored []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (local stale-pending (pending-for client "/session/ses_1"))
  (assert (> (length stale-pending) 0))
  (node:fetch)
  (local stale-request (. stale-pending 1))
  (stale-request.respond (ok-response {:id "ses_1" :title "stale title"}))
  (assert (not (= node.label "stale title")) "superseded responses must not mutate the node")
  (node:drop))

(fn test-session-responses-after-drop-are-ignored []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (local pending (pending-for client "/session/ses_1"))
  (node:drop)
  (local late-request (. pending 1))
  (late-request.respond (ok-response {:id "ses_1" :title "late title"}))
  (assert (not (= node.label "late title")) "dropped nodes must ignore late responses"))

;; -- sessions root ------------------------------------------------------------

(fn make-fake-graph []
  (local graph {:resolved [] :edges []})
  (set graph.resolve-node
       (fn [_self key]
         (table.insert graph.resolved key)
         {:stub-key key}))
  (set graph.add-edge
       (fn [_self edge]
         (table.insert graph.edges edge)))
  graph)

(fn test-sessions-root-fetch-and-open []
  (local client (make-client-stub))
  (local node (OpenCodeSessionsNode {:ensure-client (ensure-from client)}))
  (node:fetch)
  (assert (= node.state :loading))
  (deliver client "/session"
           (ok-response [{:id "ses_1" :title "First" :created "2026-01-01"}
                         {:id "ses_2" :title "Second" :created "2026-01-02"}]))
  (assert (= node.state :ready))
  (assert (= (length node.sessions) 2))
  (local entry (. node.sessions 1))
  (assert (string.find (node:session-label (. node.sessions 1)) "First" 1 true)
          (.. "label should mention the title: " (node:session-label (. node.sessions 1))))
  (local graph (make-fake-graph))
  (tset node :graph graph)
  (local target (node:open-session (. node.sessions 1)))
  (assert (= (. graph.resolved 1) "opencode-session:ses_1") "open must resolve the session key")
  (assert target "open must return the resolved target")
  (node:drop))

(fn test-sessions-root-failures []
  (local client (make-client-stub))
  (local node (OpenCodeSessionsNode {:ensure-client (ensure-from client)}))
  (node:fetch)
  (deliver client "/session" (err-response 500 "boom"))
  (assert (= node.state :unavailable))
  (assert (string.find (tostring node.error) "boom" 1 true))
  (node:drop))

(fn test-session-children-failure-stays-local []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (deliver client "/config" (ok-response {}))
  (deliver client "/session/ses_1/children" (err-response 500 "children boom"))
  (deliver client "/session/ses_1/message" (ok-response []))
  (deliver client "/session/ses_1" (ok-response {:id "ses_1" :title "t"}))
  (assert (= node.state :ready) "children failure must not demote the session state")
  (assert (string.find (tostring node.children-error) "children boom" 1 true))
  (node:drop))

(fn test-session-expand-children-materializes-topology []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (deliver client "/session/ses_1/children"
           (ok-response [{:id "ses_child" :title "Child"}]))
  (local graph {:resolved [] :edges []})
  (set graph.resolve-node
       (fn [_self key]
         (table.insert graph.resolved key)
         {:stub-key key}))
  (set graph.add-edge
       (fn [_self edge] (table.insert graph.edges edge)))
  (tset node :graph graph)
  (local expand (. node.actions 2))
  (assert (= expand.name "Expand subagent sessions") "expand action must be offered")
  (expand.fn nil nil)
  (assert (= (. graph.resolved 1) "opencode-session:ses_child") "expand must resolve child session keys")
  (assert (= (length graph.edges) 1) "expand must add one edge per child")
  (node:drop))

;; -- loaders ------------------------------------------------------------------

(fn test-session-view-offers-messages-entry-point []
  (local node (ready-session-node))
  (local graph (fake-parent-graph))
  (tset node :graph graph)
  (local built ((SessionViews.View node {}) (make-view-ctx)))
  ;; Messages (transcript + list) moved into their own projection node.
  (assert (not built.body) "the session view must not embed the transcript")
  (node:open-messages)
  (node:open-messages)
  (assert (= (length graph.edges) 1) "repeated messages clicks must dedupe")
  (assert (= (. graph.edges 1 :label) "messages"))
  (built.drop))

(table.insert tests {:name "opencode session view offers messages entry point" :fn test-session-view-offers-messages-entry-point})

;; -- part projection ----------------------------------------------------------

(local Parts (require :graph/nodes/opencode-parts))

(fn test-projection-covers-captured-part-types []
  (local text-block (Parts.project-part {:type "text" :text "hello"}))
  (assert (and (= text-block.kind :text) (= text-block.text "hello")))
  (local reasoning-block (Parts.project-part {:type "reasoning" :text "hmm"}))
  (assert (and (= reasoning-block.kind :reasoning) (= reasoning-block.text "hmm")))
  (local tool-block (Parts.project-part {:type "tool" :tool "apply_patch" :callID "call-1"
                                         :metadata {:k "v"}
                                         :state {:status "completed" :title "Apply patch"
                                                 :input {:patchText "x"} :output "ok"}}))
  (assert (= tool-block.kind :tool))
  (assert (= tool-block.name "apply_patch"))
  (assert (= tool-block.status "completed"))
  (assert (string.find tool-block.summary "Apply patch" 1 true))
  (assert (string.find tool-block.detail "patchText" 1 true) "tool detail must include input")
  (assert (string.find tool-block.detail "call-1" 1 true) "tool detail must be lossless (call id)")
  (assert (string.find tool-block.detail "metadata" 1 true) "tool detail must retain original fields")
  (local patch-block (Parts.project-part {:type "patch" :files ["a.txt" "b.txt"] :hash "abc"}))
  (assert (= patch-block.kind :patch))
  (assert (= patch-block.file-count 2))
  (assert (string.find patch-block.detail "a.txt" 1 true))
  (local step-block (Parts.project-part {:type "step-finish" :tokens {:input 10} :cost 0.01}))
  (assert (= step-block.kind :step))
  (local unknown-block (Parts.project-part {:type "mystery" :x 1}))
  (assert (= unknown-block.kind :unknown))
  (assert (= unknown-block.part-type "mystery")))

(fn test-transcript-lines-collapse-steps-and-summarize-tools []
  (assert (= (Parts.transcript-line {:kind :text :text "body"}) "body"))
  (assert (string.find (Parts.transcript-line {:kind :reasoning :text "deep"}) "deep" 1 true))
  (local tool-line (Parts.transcript-line {:kind :tool :name "bash" :status "running"
                                           :summary "Running tests"}))
  (assert (string.find tool-line "[tool bash (running)]" 1 true))
  (assert (string.find tool-line "Running tests" 1 true))
  (assert (string.find (Parts.transcript-line {:kind :patch :file-count 3}) "3 file(s)" 1 true))
  (assert (= (Parts.transcript-line {:kind :step :step "step-start"}) nil))
  (assert (= (Parts.transcript-line {:kind :unknown :part-type "mystery"}) "[mystery]")))

(fn test-transcript-uses-projection-with-model-labels []
  (local transcript
    (Parts.compose-transcript
      [{:info {:id "msg-1" :role "user" :modelID "glm" :providerID "opencode-go"}
        :parts [{:type "step-start" :snapshot "x"}
                {:type "text" :text "question"}
                {:type "tool" :tool "read_file" :state {:status "completed" :title "Read file"}}]}
       {:info {:id "msg-2" :role "assistant"}
        :parts [{:type "reasoning" :text "thinking"}
                {:type "text" :text "answer"}]}]))
  (assert (string.find transcript "## user (glm via opencode-go)" 1 true))
  (assert (string.find transcript "[tool read_file (completed)] Read file" 1 true))
  (assert (string.find transcript "[thinking]" 1 true))
  (assert (not (string.find transcript "step-start" 1 true)) "steps must collapse out of transcripts")
  (assert (string.find transcript "answer" 1 true)))

(table.insert tests {:name "opencode projection covers captured part types" :fn test-projection-covers-captured-part-types})
(table.insert tests {:name "opencode transcript lines collapse steps and summarize tools" :fn test-transcript-lines-collapse-steps-and-summarize-tools})
(table.insert tests {:name "opencode transcript uses projection with model labels" :fn test-transcript-uses-projection-with-model-labels})

(fn test-session-refresh-marks-transcript-stale-until-messages-settle []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (deliver client "/session/ses_1/message" (ok-response []))
  (deliver client "/session/ses_1" (ok-response {:id "ses_1" :title "t"}))
  (assert (= node.state :ready))
  (assert (not node.messages-stale) "settled transcript must not be stale")
  (node:fetch)
  (assert (= node.state :loading))
  (assert node.messages-stale "a refresh must mark the old transcript stale")
  (deliver client "/session/ses_1" (ok-response {:id "ses_1" :title "t"}))
  (assert (= node.state :ready))
  (assert node.messages-stale "metadata alone must not clear the stale marker")
  (deliver client "/session/ses_1/message" (ok-response []))
  (assert (not node.messages-stale) "transcript delivery must clear the stale marker")
  (node:drop))

(fn test-session-fetch-after-drop-is-rejected []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:drop)
  (local (ok err) (pcall (fn [] (node:fetch))))
  (assert (not ok) "fetching a dropped node must fail loudly")
  (assert (string.find (tostring err) "dropped" 1 true)))

(fn test-sessions-list-placeholders-are-not-actionable []
  (local client (make-client-stub))
  (local node (OpenCodeSessionsNode {:ensure-client (ensure-from client)}))
  (local SessionsViewModule (require :graph/view/views/opencode-sessions))
  (local loading-entries (SessionsViewModule.render-items node))
  (assert (= (length loading-entries) 1))
  (assert (. loading-entries 1 :placeholder) "loading rows must be placeholders")
  (node:fetch)
  (deliver client "/session" (ok-response []))
  (local empty-entries (SessionsViewModule.render-items node))
  (assert (. empty-entries 1 :placeholder) "empty rows must be placeholders")
  (node:drop))


(fn test-messages-loader-parses-session-ids []
  (local graph (make-recording-graph))
  (local handles (install-descriptor (OpencodeSessionsExtension.descriptors {}) graph))
  (local loader (loader-for handles "opencode-session-messages"))
  (local node (loader "opencode-session-messages:ses_1"))
  (assert node "well-formed messages keys must resolve")
  (assert (= node.session-id "ses_1"))
  (assert (= (loader "opencode-session-messages:") nil) "empty ids must not resolve")
  (assert (= (loader "opencode-session-messages:../etc") nil) "unsafe ids must not resolve"))

(table.insert tests {:name "opencode messages loader parses session ids" :fn test-messages-loader-parses-session-ids})

(fn test-session-open-message-resolves-and-links []
  (local parent (ready-parent-with-messages))
  (local graph (fake-parent-graph))
  (tset parent :graph graph)
  (local target (parent:open-message (. parent.messages 1)))
  (assert (= (. graph.resolved 1) "opencode-session-message:ses_1/msg-a"))
  (assert (= (length graph.edges) 1))
  (assert target))

(table.insert tests {:name "opencode session open message resolves and links" :fn test-session-open-message-resolves-and-links})
(table.insert tests {:name "opencode session refresh marks transcript stale until messages settle" :fn test-session-refresh-marks-transcript-stale-until-messages-settle})
(table.insert tests {:name "opencode session fetch after drop is rejected" :fn test-session-fetch-after-drop-is-rejected})
(table.insert tests {:name "opencode sessions list placeholders are not actionable" :fn test-sessions-list-placeholders-are-not-actionable})

;; -- abort --------------------------------------------------------------------

(fn test-abort-acknowledges-and-refreshes []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (node:abort)
  (assert (= node.abort-state :pending) "abort must enter pending")
  (node:abort)
  (local aborts (pending-for client "/session/ses_1/abort"))
  (assert (= (length aborts) 1) "duplicate clicks must be suppressed")
  (local gets-before (length (pending-for client "/session/ses_1")))
  (local request (. aborts 1))
  (request.respond (ok-response true))
  (assert (= node.abort-state :acknowledged))
  (assert (= node.abort-result "true"))
  ;; refresh only after acknowledged success: a new session GET is pending
  (assert (> (length (pending-for client "/session/ses_1")) gets-before)
          "acknowledged abort must trigger a refresh")
  (node:drop))

(fn test-abort-failure-stays-separate-from-fetch []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (deliver client "/session/ses_1/message" (ok-response []))
  (deliver client "/session/ses_1" (ok-response {:id "ses_1" :title "t"}))
  (assert (= node.state :ready))
  (node:abort)
  (local aborts (pending-for client "/session/ses_1/abort"))
  (local request (. aborts 1))
  (request.respond (err-response 500 "boom"))
  (assert (= node.abort-state :failed))
  (assert (string.find (tostring node.abort-error) "boom" 1 true))
  (assert (= node.state :ready) "abort failure must not disturb the session state")
  (local gets-after (length (pending-for client "/session/ses_1")))
  (node:abort)
  (assert (= (length (pending-for client "/session/ses_1")) gets-after)
          "failed abort must not trigger a refresh")
  (node:drop))

(fn test-abort-records-scalar-false-body-as-acknowledged []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (node:abort)
  (local aborts (pending-for client "/session/ses_1/abort"))
  (local request (. aborts 1))
  ;; Scalar JSON bodies arrive as raw strings; truthiness must not decide.
  (request.respond {:ok true :status 200 :data "false"})
  (assert (= node.abort-state :acknowledged))
  (assert (= node.abort-result "false"))
  (node:drop))

(fn test-abort-missing-session-surfaces-not-found-error []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (node:fetch)
  (node:abort)
  (local aborts (pending-for client "/session/ses_1/abort"))
  (local request (. aborts 1))
  (request.respond (err-response 404 "not found"))
  (assert (= node.abort-state :failed))
  (assert (string.find (tostring node.abort-error) "not found" 1 true))
  (node:drop))

;; -- config node --------------------------------------------------------------

(local {:OpenCodeConfigNode ConfigNode} (require :graph/nodes/opencode-config))
(local ConfigViews (require :graph/view/views/opencode-config))

(fn test-config-node-fetches-both-sections []
  (local client (make-client-stub))
  (local node (ConfigNode {:ensure-client (ensure-from client)}))
  (node:fetch)
  (deliver client "/config" (ok-response {:theme "dark"}))
  (deliver client "/config/providers" (ok-response {:default {}}))
  (assert (= node.state :ready) (tostring node.state))
  (assert (= node.config-error nil))
  (assert (= node.providers-error nil))
  (node:drop))

(fn test-config-node-section-failures-stay-local []
  (local client (make-client-stub))
  (local node (ConfigNode {:ensure-client (ensure-from client)}))
  (node:fetch)
  (deliver client "/config" (err-response 500 "config boom"))
  (deliver client "/config/providers" (ok-response {:default {}}))
  (assert (= node.state :ready))
  (assert (string.find (tostring node.config-error) "config boom" 1 true))
  (assert (= node.providers-error nil))
  (node:drop))

(fn test-config-loader-and-link []
  (local graph (make-recording-graph))
  (local handles (install-descriptor (OpencodeSessionsExtension.descriptors {}) graph))
  (local loader (loader-for handles "opencode-config"))
  (assert (loader "opencode-config") "the config key must resolve network-free")
  (local client (make-client-stub))
  (local node (OpenCodeSessionsNode {:ensure-client (ensure-from client)}))
  (local fake {:resolved [] :edges []})
  (set fake.resolve-node (fn [_self key] (table.insert fake.resolved key) :config-node))
  (set fake.add-edge (fn [_self edge] (table.insert fake.edges edge)))
  (tset node :graph fake)
  (local show-config (. node.actions 2))
  (assert (= show-config.name "Show Server Config"))
  (show-config.fn nil nil)
  (assert (= (. fake.resolved 1) "opencode-config"))
  (assert (= (length fake.edges) 1)))

(fn test-abort-action-wiring-invokes-abort []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (local abort-action (. node.actions 3))
  (assert (= abort-action.name "Abort Session") "the abort action must be offered")
  (abort-action.fn nil nil)
  (assert (= node.abort-state :pending) "the action closure must invoke the node's abort")
  (assert (> (length (pending-for client "/session/ses_1/abort")) 0)
          "the action closure must issue the abort request")
  (node:drop))

(fn test-delete-acknowledges-and-removes-node-from-map []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (local graph (fake-parent-graph))
  (tset node :graph graph)
  (node:fetch)
  (local delete-action (. node.actions 4))
  (assert (= delete-action.name "Delete Session") "the delete action must be offered")
  (delete-action.fn nil nil)
  (assert (= node.delete-state :pending) "delete must enter pending")
  (delete-action.fn nil nil)
  (var delete-request nil)
  (each [_ r (ipairs client.pending)]
    (when (and (= r.method "DELETE") (= r.path "/session/ses_1"))
      (set delete-request r)))
  (assert delete-request "the delete request must be issued")
  (delete-action.fn nil nil)
  (var delete-count 0)
  (each [_ r (ipairs client.pending)]
    (when (and (= r.method "DELETE") (= r.path "/session/ses_1"))
      (set delete-count (+ delete-count 1))))
  (assert (= delete-count 1) "duplicate clicks must be suppressed")
  (local request delete-request)
  (request.respond (ok-response true))
  (assert (= node.delete-state :acknowledged))
  (assert (= node.delete-result "true"))
  (assert (= (. graph.removals 1 :opts :cause) "session-deleted") "acknowledged delete must remove the node from the map")
  (assert (> (length (pending-for client "/session/ses_1/message")) 0) "the initial snapshot fetch must still have happened"))

(fn test-delete-failure-stays-on-node []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (local graph (fake-parent-graph))
  (tset node :graph graph)
  (node:fetch)
  (node.delete-session nil)
  (var delete-request nil)
  (each [_ r (ipairs client.pending)]
    (when (and (= r.method "DELETE") (= r.path "/session/ses_1"))
      (set delete-request r)))
  (delete-request.respond (err-response 500 "delete boom"))
  (assert (= node.delete-state :failed))
  (assert (string.find (tostring node.delete-error) "delete boom" 1 true))
  (assert (= (length graph.edges) 0) "failed delete must not remove the node"))

(fn test-delete-missing-session-surfaces-not-found []
  (local client (make-client-stub))
  (local node (make-session-node client))
  (local graph (fake-parent-graph))
  (tset node :graph graph)
  (node:fetch)
  (node.delete-session nil)
  (var delete-request nil)
  (each [_ r (ipairs client.pending)]
    (when (and (= r.method "DELETE") (= r.path "/session/ses_1"))
      (set delete-request r)))
  (delete-request.respond (err-response 404 "not found"))
  (assert (= node.delete-state :failed))
  (assert (string.find (tostring node.delete-error) "not found" 1 true)))

(table.insert tests {:name "opencode delete acknowledges and removes node from map" :fn test-delete-acknowledges-and-removes-node-from-map})
(table.insert tests {:name "opencode delete failure stays on node" :fn test-delete-failure-stays-on-node})
(table.insert tests {:name "opencode delete missing session surfaces not found" :fn test-delete-missing-session-surfaces-not-found})

(table.insert tests {:name "opencode abort action wiring invokes abort" :fn test-abort-action-wiring-invokes-abort})
(table.insert tests {:name "opencode abort acknowledges and refreshes" :fn test-abort-acknowledges-and-refreshes})
(table.insert tests {:name "opencode abort failure stays separate from fetch" :fn test-abort-failure-stays-separate-from-fetch})
(table.insert tests {:name "opencode abort records scalar false body as acknowledged" :fn test-abort-records-scalar-false-body-as-acknowledged})
(table.insert tests {:name "opencode abort missing session surfaces not found error" :fn test-abort-missing-session-surfaces-not-found-error})
(table.insert tests {:name "opencode config node fetches both sections" :fn test-config-node-fetches-both-sections})
(table.insert tests {:name "opencode config node section failures stay local" :fn test-config-node-section-failures-stay-local})
(table.insert tests {:name "opencode config loader and link" :fn test-config-loader-and-link})

;; -- SSE plumbing health (D) --------------------------------------------------

(fn make-stream-http []
  (local http {:requests []})
  (set http.request
       (fn [opts]
         (table.insert http.requests opts)
         "req-1"))
  (set http.cancel (fn [_id] nil))
  (fn last-callback []
    (local opts (. http.requests (length http.requests)))
    opts.callback)
  http)

(fn pump [http chunks]
  (local callback
         (do
           (local opts (. http.requests (length http.requests)))
           opts.callback))
  (each [_ chunk (ipairs chunks)]
    (callback {:chunk chunk})))

(fn close-stream [http]
  (local opts (. http.requests (length http.requests)))
  (opts.callback {:done true}))

(fn test-events-health-variant-detects-parse-and-completion []
  (local http (make-stream-http))
  (local Events (require :llm/providers/opencode/events))
  (local fake-client {:base-url (fn [] "http://x")
                      :http-binding (fn [] http)})
  (local events (Events fake-client))
  (local events-received [])
  (local health-received [])
  (local handle (events.subscribe-with-health
                  (fn [event] (table.insert events-received event))
                  (fn [health] (table.insert health-received health))))
  (pump http ["data: not-json\n\n"
              "id: 7\ndata: {\"a\":1}\n\n"
              "data: 42\n\n"])
  (assert (= (length health-received) 1) "malformed JSON must surface as parse-error health")
  (assert (= (. health-received 1 :kind) :parse-error))
  (assert (= (length events-received) 2) "valid events must still be delivered")
  (assert (= (. events-received 1 :_sse_id) "7") "SSE envelope ids must be preserved")
  (assert (= (. events-received 2 :_event_type) "message") "scalar JSON must be wrapped, not mutated")
  (close-stream http)
  (assert (= (length health-received) 2) "stream completion must surface as health")
  (assert (= (. health-received 2 :kind) :stream-done))
  (handle:unsubscribe))

(fn test-sse-split-crlf-does-not-invent-boundaries []
  (local http (make-stream-http))
  (local Sse (require :llm/providers/opencode/sse))
  (local parsed [])
  (Sse http "http://x/event" {} (fn [event] (table.insert parsed event)))
  ;; The \r in chunk 1 is half of a \r\n data-line separator split across
  ;; chunks: chunk-local normalization must not turn it into a blank line
  ;; (which would invent an event boundary with the trailing \n).
  (pump http ["data: {\"n\":1}\r"
              "\ndata: {\"n\":2}\r\n"
              "\n"])
  (assert (= (length parsed) 1) (tostring (length parsed)))
  (assert (string.find (. parsed 1 :data) "\"n\":1" 1 true))
  (assert (string.find (. parsed 1 :data) "\"n\":2" 1 true)))

(table.insert tests {:name "opencode events health variant detects parse and completion" :fn test-events-health-variant-detects-parse-and-completion})
(table.insert tests {:name "opencode sse split crlf does not invent boundaries" :fn test-sse-split-crlf-does-not-invent-boundaries})


;; -- live subscription (D) ----------------------------------------------------

(fn make-events-fake []
  (local fake {:subs [] :unsubscribed 0})
  (local unsubscribe (fn [] (set fake.unsubscribed (+ fake.unsubscribed 1))))
  (set fake.subscribe-with-health
        (fn [on-event on-health]
         (local entry {:on-event on-event :on-health on-health
                       :unsubscribe unsubscribe})
         (table.insert fake.subs entry)
         entry))
  (fn last [] (. fake.subs (length fake.subs)))
  (set fake.last last)
  fake)

(fn live-session-node []
  (local client (make-client-stub))
  (local events (make-events-fake))
  (local events-factory (fn [_client] events))
  (var retry-callback nil)
  (fn timer-factory [options]
    (set retry-callback options.callback)
    {:start (fn [_self] nil) :cancel (fn [_self] nil)})
  (fn retry! [] ((assert retry-callback "expected delayed retry")))
  (local node (OpenCodeSessionNode {:id "ses_1"
                                    :ensure-client (ensure-from client)
                                    :events-factory events-factory :timer-factory timer-factory}))
  (local graph (make-recording-graph))
  {:client client :events events :node node :graph graph :retry! retry!})

(fn test-live-subscribes-before-snapshot-and-refreshes-on-relevant-events []
  (local fixture (live-session-node))
  (local node fixture.node)
  (node:mount node fixture.graph)
  (assert (= (length fixture.events.subs) 1) "mount must subscribe before the snapshot")
  (assert (= node.live-state :live))
  (assert (> (length fixture.client.pending) 0) "the snapshot fetch must follow subscription")
  (deliver fixture.client "/session/ses_1/message" (ok-response []))
  (deliver fixture.client "/session/ses_1" (ok-response {:id "ses_1" :title "t"}))
  (assert (= node.state :ready))
  (local gets-before (length (pending-for fixture.client "/session/ses_1")))
  (local sub (fixture.events.last))
  (sub.on-event {:properties {:info {:sessionID "ses_other"}}})
  (assert (= (length (pending-for fixture.client "/session/ses_1")) gets-before)
          "irrelevant events must not refresh")
  (sub.on-event {:type "message.updated" :properties {:sessionID "ses_1"}})
  (assert (> (length (pending-for fixture.client "/session/ses_1")) gets-before)
          "relevant events must refresh the snapshot")
  (node:drop)
  (assert (= fixture.events.unsubscribed 1) "drop must unsubscribe the live stream")
  (assert (= node.live-state :stopped)))

(fn test-live-event-during-loading-schedules-one-followup []
  (local fixture (live-session-node))
  (local node fixture.node)
  (node:mount node fixture.graph)
  (assert (= node.state :loading))
  (local sub (fixture.events.last))
  ;; Events while the snapshot is in flight must not be silently dropped.
  (sub.on-event {:type "message.updated" :properties {:sessionID "ses_1"}})
  (assert node.pending-invalidation "the event must schedule a follow-up")
  (local gets-before (length (pending-for fixture.client "/session/ses_1")))
  (deliver fixture.client "/session/ses_1" (ok-response {:id "ses_1" :title "t"}))
  (assert node.pending-invalidation "metadata alone cannot consume invalidation")
  (deliver fixture.client "/session/ses_1/message" (ok-response []))
  ;; The required pair consumed the flag and started one follow-up.
  (assert (= node.state :loading) "the follow-up refresh must be in flight")
  (assert (not node.pending-invalidation) "the follow-up must be consumed by the settle")
  (assert (> (length (pending-for fixture.client "/session/ses_1")) gets-before)
          "the settle must trigger exactly one follow-up refresh")
  (deliver fixture.client "/session/ses_1" (ok-response {:id "ses_1" :title "t"}))
  (deliver fixture.client "/session/ses_1/message" (ok-response []))
  (assert (= node.state :ready) "the follow-up settles ready without another follow-up")
  (node:drop))

(table.insert tests {:name "opencode live event during loading schedules one followup" :fn test-live-event-during-loading-schedules-one-followup})

(fn test-live-health-resynchronizes-with-refresh []
  (local fixture (live-session-node))
  (local node fixture.node)
  (node:mount node fixture.graph)
  (deliver fixture.client "/session/ses_1/message" (ok-response []))
  (deliver fixture.client "/session/ses_1" (ok-response {:id "ses_1" :title "t"}))
  (assert (= node.state :ready))
  (local gets-before (length (pending-for fixture.client "/session/ses_1")))
  (local sub (fixture.events.last))
  (sub.on-health {:kind :parse-error})
  (assert (= (length fixture.events.subs) 1) "reconnect waits for backoff")
  (fixture.retry!)
  (assert (= (length fixture.events.subs) 2) "health loss must resubscribe")
  (assert (= node.live-state :live) "resubscription must restore the live state")
  (assert (> (length (pending-for fixture.client "/session/ses_1")) gets-before)
          "resynchronization must refresh the snapshot")
  (node:drop))

(fn test-live-stream-done-resubscribes []
  (local fixture (live-session-node))
  (local node fixture.node)
  (node:mount node fixture.graph)
  (local sub (fixture.events.last))
  (sub.on-health {:kind :stream-done})
  (fixture.retry!)
  (assert (= (length fixture.events.subs) 2) "stream end must resubscribe")
  (node:drop))

(fn test-live-unavailable-provider-is-explicit []
  (local events (make-events-fake))
  (local failing-ensure (fn [] (error "providers missing")))
  (local events-factory (fn [_client] events))
  (local node (OpenCodeSessionNode {:id "ses_1"
                                    :ensure-client failing-ensure
                                    :events-factory events-factory}))
  (node:mount node (make-recording-graph))
  (assert (= node.live-state :unavailable) "provider failure must surface as unavailable live state")
  (node:drop))

(fn test-virtual-input-set-buffer-renders-fresh-content []
  (local LazyTextBuffer (require :lazy-text-buffer))
  (local LazyTextSource (require :lazy-text-source))
  (local VirtualInput (require :virtual-input))
  (local input
    ((VirtualInput {:buffer (LazyTextBuffer {:source (LazyTextSource.string "## user\nfirst line only here\nmore\n")})
                    :line-count 4
                    :column-count 40
                    :editable? false})
      (make-view-ctx)))
  (local next-buffer (LazyTextBuffer
                       {:source (LazyTextSource.string "## user\nbrand new content\nsecond line\nthird\n")}))
  ;; Simulate the refresh swap: old buffer had established anchors/caches.
  (input:scroll-lines 1)
  (input:set-buffer! next-buffer)
  (local viewport (input.buffer:get-viewport {:line 0 :column 0 :lines 4 :columns 40}))
  (local rendered (table.concat (icollect [_ row (ipairs viewport.rows)] (or row.text "")) "\n"))
  (assert (= rendered "## user\nbrand new content\nsecond line\nthird")
          (.. "swapped buffer must render fresh rows, got: " rendered))
  (assert (= input.scroll-column 0) "scroll column must reset on swap")
  (input:drop))

(table.insert tests {:name "opencode virtual input set-buffer renders fresh content" :fn test-virtual-input-set-buffer-renders-fresh-content})

(table.insert tests {:name "opencode live subscribes before snapshot and refreshes on relevant events" :fn test-live-subscribes-before-snapshot-and-refreshes-on-relevant-events})
(table.insert tests {:name "opencode live health resynchronizes with refresh" :fn test-live-health-resynchronizes-with-refresh})
(table.insert tests {:name "opencode live stream done resubscribes" :fn test-live-stream-done-resubscribes})
(fn test-live-refresh-retries-unavailable-subscription []
  (local events (make-events-fake))
  (local client (make-client-stub))
  ;; The provider is down at mount, then comes up: ensure resolves through a
  ;; mutable box to model the server starting later.
  (local ensure-box {})
  (local ensure (fn [] (assert ensure-box.client "providers missing") ensure-box.client))
  (local events-factory (fn [_c] events))
  (local node (OpenCodeSessionNode {:id "ses_1"
                                    :ensure-client ensure
                                    :events-factory events-factory}))
  (node:mount node (make-recording-graph))
  (assert (= node.live-state :unavailable))
  (tset ensure-box :client client)
  (node:fetch)
  (assert (= (length events.subs) 1) "refresh must retry the live subscription")
  (assert (= node.live-state :live))
  (node:drop))

(table.insert tests {:name "opencode live refresh retries unavailable subscription" :fn test-live-refresh-retries-unavailable-subscription})
(table.insert tests {:name "opencode live unavailable provider is explicit" :fn test-live-unavailable-provider-is-explicit})

(table.insert tests {:name "opencode session fetch reaches ready with transcript" :fn test-session-fetch-reaches-ready-with-transcript})

(table.insert tests {:name "opencode session 404 resolves not-found" :fn test-session-404-resolves-not-found})
(table.insert tests {:name "opencode session transport failure is unavailable not deletion" :fn test-session-transport-failure-is-unavailable-not-deletion})
(table.insert tests {:name "opencode session unavailable ensure-client" :fn test-session-unavailable-ensure-client})
(table.insert tests {:name "opencode session malformed messages keep session ready" :fn test-session-malformed-messages-keep-session-ready})
(table.insert tests {:name "opencode session stale responses are ignored" :fn test-session-stale-responses-are-ignored})
(table.insert tests {:name "opencode session responses after drop are ignored" :fn test-session-responses-after-drop-are-ignored})
(table.insert tests {:name "opencode session children failure stays local" :fn test-session-children-failure-stays-local})
(table.insert tests {:name "opencode session expand children materializes topology" :fn test-session-expand-children-materializes-topology})
(table.insert tests {:name "opencode sessions root fetch and open" :fn test-sessions-root-fetch-and-open})
(table.insert tests {:name "opencode sessions root failures" :fn test-sessions-root-failures})
(fn test-loaders-are-network-free-and-validate-ids []
  (local graph (make-recording-graph))
  (local handles (install-descriptor (OpencodeSessionsExtension.descriptors {}) graph))
  (var ensure-called false)
  (local session-loader (loader-for handles "opencode-session"))
  (local node (session-loader "opencode-session:ses_1"))
  (assert node "a well-formed key must resolve without any network activity")
  (assert (= node.id "ses_1"))
  (assert (= (session-loader "opencode-session:") nil) "empty ids must not resolve")
  (assert (= (session-loader "opencode-session:../etc") nil) "unsafe ids must not resolve")
  (local root-loader (loader-for handles "opencode-sessions"))
  (assert (root-loader "opencode-sessions") "the list root must resolve without network activity"))


(table.insert tests {:name "opencode loaders are network free and validate ids" :fn test-loaders-are-network-free-and-validate-ids})

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "opencode-sessions-graph"
                       :tests tests})))

{:name "opencode-sessions-graph"
 :tests tests
 :main main}
