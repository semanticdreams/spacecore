(local H (require :tests/opencode-graph-helpers))
(local Common (require :graph/nodes/opencode-common))
(local {:OpenCodeConfigNode Config} (require :graph/nodes/opencode-config))
(local {:OpenCodeSessionsNode Sessions} (require :graph/nodes/opencode-sessions))
(local tests [])

(fn configuration-completion []
  (each [_ first (ipairs ["/config" "/config/providers"])]
    (local client (H.make-client-stub))
    (local node (Config {:ensure-client (H.ensure-from client)}))
    (node:fetch)
    (assert (= node.state :loading))
    (assert (= node.fetched-at nil))
    (H.deliver client first (H.ok-response {}))
    (assert (= node.state :loading) "one section cannot settle both")
    (local second (if (= first "/config") "/config/providers" "/config"))
    (H.deliver client second (H.err-response 500 "section failed"))
    (assert (= node.state :ready))
    (assert node.fetched-at)
    (node:drop)))

(fn default-client-acquisition []
  (local previous app.agent-providers)
  (local client (H.make-client-stub))
  (set app.agent-providers {:opencode {:client client}})
  (local node (Config {}))
  (local (ok err) (pcall node.fetch node))
  (set app.agent-providers previous)
  (assert ok err)
  (assert (= (length client.pending) 2) "default ensure must return a client, not a function")
  (node:drop))

(fn malformed-transcript-keeps-snapshot []
  (local client (H.make-client-stub))
  (local node (H.make-session-node client))
  (local messages [{:info {:id "msg-1"} :parts []}])
  (node:fetch)
  (H.deliver client "/session/ses_1/message" (H.ok-response messages))
  (H.deliver client "/session/ses_1" (H.ok-response {:id "ses_1"}))
  (node:fetch)
  (H.deliver client "/session/ses_1/message" (H.ok-response {:error "not an array"}))
  (assert node.transcript-error)
  (assert (= node.messages messages) "malformed data cannot erase valid content")
  (node:drop))

(fn array-validation []
  (assert (Common.record-array? []))
  (assert (Common.message-array? [{:info {} :parts []}]))
  (each [_ invalid (ipairs [{:error "envelope"} [false] {1 {} 3 {}}])]
    (assert (not (Common.record-array? invalid))))
  (assert (not (Common.message-array? [{}])))
  (assert (not (Common.message-array? [{:info {} :parts [false]}]))))

(fn root-fetch-after-drop []
  (local client (H.make-client-stub))
  (local node (Sessions {:ensure-client (H.ensure-from client)}))
  (node:drop)
  (local ok (pcall node.fetch node))
  (assert (not ok))
  (assert (= (length client.pending) 0)))

(table.insert tests {:name "config waits for both response orders" :fn configuration-completion})
(table.insert tests {:name "config invokes the default provider resolver" :fn default-client-acquisition})
(table.insert tests {:name "malformed transcript preserves valid snapshot" :fn malformed-transcript-keeps-snapshot})
(table.insert tests {:name "OpenCode endpoint list validation is dense and structural" :fn array-validation})
(table.insert tests {:name "sessions root rejects fetch after drop without IO" :fn root-fetch-after-drop})
(fn main [] ((. (require :tests/runner) :run-tests) {:name "opencode-adapter-contracts" :tests tests}))
{:name "opencode-adapter-contracts" :tests tests :main main}
