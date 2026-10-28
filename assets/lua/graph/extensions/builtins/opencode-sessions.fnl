(local Common (require :graph/extensions/builtins/common))
(local OpencodeCommon (require :graph/nodes/opencode-common))
(local {:OpenCodeSessionsNode SessionsRootNode} (require :graph/nodes/opencode-sessions))
(local SessionNodeModule (require :graph/nodes/opencode-session))
(local {:OpenCodeSessionNode SessionNode} SessionNodeModule)
(local {:OpenCodeSessionMessageNode MessageNode} (require :graph/nodes/opencode-session-message))
(local {:OpenCodeSessionMessagePartsNode PartsNode} (require :graph/nodes/opencode-session-message-parts))
(local {:OpenCodeSessionMessagePartNode PartNode} (require :graph/nodes/opencode-session-message-part))
(local {:OpenCodeSessionMessageInfoNode InfoNode} (require :graph/nodes/opencode-session-message-info))
(local {:OpenCodeSessionMessagesNode MessagesListNode} (require :graph/nodes/opencode-session-messages))
(local {:OpenCodeConfigNode ConfigNode} (require :graph/nodes/opencode-config))

;; Read-only exposure of OpenCode-owned sessions. Loaders stay synchronous and
;; network-free: they mint fresh reference adapters; data is fetched lazily by
;; the nodes through the app's OpenCode client (ensure-client injection, like
;; the hackernews extension).

(fn make-session-loader-node [ensure-client id]
  ;; Malformed ids resolve to nil so hydration prunes them; only well-formed
  ;; ids become adapters.
  (when (OpencodeCommon.url-safe-id? id)
    (SessionNode {:id id :ensure-client ensure-client})))

(fn make-sessions-root [ensure-client]
  (SessionsRootNode {:ensure-client ensure-client}))

(fn sessions-loader [ensure-client]
  (Common.exact-key-loader "opencode-sessions"
                           (fn [] (make-sessions-root ensure-client))))

(fn session-loader [ensure-client]
  (Common.prefix-loader "opencode-session:"
                        (fn [id _key] (make-session-loader-node ensure-client id))))

(fn make-message-loader-node [ids]
  ;; Only well-formed `<url-safe-session>/<url-safe-message>` keys become
  ;; adapters; anything else resolves to nil so hydration prunes it.
  (local (session-id message-id) (string.match ids "^([%w%-_]+)/([%w%-_]+)$"))
  (when (and session-id message-id)
    (MessageNode {:session-id session-id :message-id message-id})))

(fn message-loader [ensure-client]
  (Common.prefix-loader "opencode-session-message:"
                        (fn [ids _key] (make-message-loader-node ids))))

(fn make-parts-loader-node [ids]
  (local (session-id message-id) (string.match ids "^([%w%-_]+)/([%w%-_]+)$"))
  (when (and session-id message-id)
    (PartsNode {:session-id session-id :message-id message-id})))

(fn parts-loader [ensure-client]
  (Common.prefix-loader "opencode-session-message-parts:"
                        (fn [ids _key] (make-parts-loader-node ids))))

(fn make-part-loader-node [ids]
  (local (session-id message-id part-id)
         (string.match ids "^([%w%-_]+)/([%w%-_]+)/([%w%-_]+)$"))
  (when (and session-id message-id part-id)
    (PartNode {:session-id session-id :message-id message-id :part-id part-id})))

(fn part-loader [ensure-client]
  (Common.prefix-loader "opencode-session-message-part:"
                        (fn [ids _key] (make-part-loader-node ids))))

(fn make-info-loader-node [ids]
  (local (session-id message-id segment)
         (string.match ids "^([%w%-_]+)/([%w%-_]+)/([^/]+)$"))
  (local field (OpencodeCommon.decode-info-field segment))
  (when (and session-id message-id (not= field nil))
    (InfoNode {:session-id session-id :message-id message-id :field field})))

(fn info-loader [ensure-client]
  (Common.prefix-loader "opencode-session-message-info:"
                        (fn [ids _key] (make-info-loader-node ids))))

(fn messages-list-loader [ensure-client]
  (Common.prefix-loader "opencode-session-messages:"
                        (fn [id _key]
                          (when (OpencodeCommon.url-safe-id? id)
                            (MessagesListNode {:session-id id})))))

(fn config-loader [ensure-client]
  (Common.exact-key-loader "opencode-config" (fn [] (ConfigNode {:ensure-client ensure-client}))))

(fn descriptors [opts]
  (fn install [graph ctx]
    (local ensure-client opts.opencode-ensure-client)
    [(graph:register-key-loader "opencode-sessions" (sessions-loader ensure-client)
                                {:owner-id ctx.owner-id :extension-id ctx.extension-id})
     (graph:register-key-loader "opencode-session" (session-loader ensure-client)
                                {:owner-id ctx.owner-id :extension-id ctx.extension-id})
     (graph:register-key-loader "opencode-session-message" (message-loader ensure-client)
                                {:owner-id ctx.owner-id :extension-id ctx.extension-id})
     (graph:register-key-loader "opencode-session-messages" (messages-list-loader ensure-client)
                                {:owner-id ctx.owner-id :extension-id ctx.extension-id})
     (graph:register-key-loader "opencode-session-message-parts" (parts-loader ensure-client)
                                {:owner-id ctx.owner-id :extension-id ctx.extension-id})
     (graph:register-key-loader "opencode-session-message-part" (part-loader ensure-client)
                                {:owner-id ctx.owner-id :extension-id ctx.extension-id})
     (graph:register-key-loader "opencode-session-message-info" (info-loader ensure-client)
                                {:owner-id ctx.owner-id :extension-id ctx.extension-id})
     (graph:register-key-loader "opencode-config" (config-loader ensure-client)
                                {:owner-id ctx.owner-id :extension-id ctx.extension-id})])
  [(Common.descriptor {:id "builtin-graph-opencode-sessions"
                       :unit-id "builtin-graph-opencode-sessions"
                       :schemes ["opencode-sessions" "opencode-session"
                                 "opencode-session-message" "opencode-session-messages" "opencode-session-message-parts"
                                 "opencode-session-message-part" "opencode-session-message-info"
                                 "opencode-config"]
                       :install-loaders install})])

{:descriptors descriptors}
