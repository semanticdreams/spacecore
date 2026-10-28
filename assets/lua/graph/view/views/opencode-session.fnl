(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Text (require :text))
(local Button (require :button))
(local ScrollView (require :scroll-view))

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))

(fn delete-suffix [node]
  (if (= node.delete-state :pending)
      " — delete pending"
      (= node.delete-state :acknowledged)
      (.. " — delete acknowledged (" (tostring node.delete-result) ")")
      (= node.delete-state :failed)
      (.. " — delete failed (" (tostring node.delete-error) ")")
      ""))

(fn abort-suffix [node]
  (if (= node.abort-state :pending)
      " — abort pending"
      (= node.abort-state :acknowledged)
      (.. " — abort acknowledged (" (tostring node.abort-result) ")")
      (= node.abort-state :failed)
      (.. " — abort failed (" (tostring node.abort-error) ")")
      ""))

(fn status-line [node]
  (if (= node.state :loading)
      "Loading session..."
      (= node.state :not-found)
      (if node.error node.error "session not found")
      (= node.state :unavailable)
      (.. "Unavailable: " (if node.error node.error "unknown error"))
      (= node.state :idle)
      "Not loaded yet — use Refresh Session"
      (.. "Ready — fetched "
          (if node.fetched-at
            (os.date "!%Y-%m-%d %H:%M:%S UTC" node.fetched-at)
            "?")
          (if (= node.live-state :live) " · live" "")
          (if (= node.live-state :degraded) " · live (resynchronizing)" "")
          (abort-suffix node)
          (delete-suffix node))))

(fn session-text [node]
  (local session (if node.session node.session {}))
  (.. "Session: " (tostring node.id)
      "\nTitle: " (tostring (if session.title session.title "?"))
      "\nAgent: " (tostring (if session.agent session.agent "?"))
      "\nCreated: " (tostring (if session.created session.created "?"))))

(fn config-text [node]
  (.. "Server config: "
      (if node.config-error
        (.. "unavailable (" node.config-error ")")
        "current (see OpenCode server settings)")))

(fn children-text [node]
  ;; Children are additive content: failures stay local to this line.
  (.. "Subagent sessions: "
      (if node.children-error
        (.. "unavailable (" node.children-error ")")
        (tostring (length (if node.subagents node.subagents []))))))

;; Preview and full view share content; previews follow the transcript tail,
;; finished full views read from the top. Full views also list messages for
;; explicit per-message materialization.
(fn content [node ctx compact?]
  (local heading ((Text {:text ""}) ctx))
  (local status ((Text {:text ""}) ctx))
  (local metadata ((Text {:text ""}) ctx))
  (local config ((Text {:text ""}) ctx))
  (local subagents ((Text {:text ""}) ctx))
  ;; Messages (transcript + list) live in their own projection node; the
  ;; session view only offers the entry point.
  (fn refresh-session [_button _event] (node:fetch))
  (fn open-messages [_button _event] (node:open-messages))
  (local refresh
    ((Button {:text "Refresh" :icon "refresh" :on-click refresh-session}) ctx))
  (local messages
    ((Button {:text "Messages" :icon "format_list_bulleted" :on-click open-messages}) ctx))
  (fn refresh-view [_]
    (heading:set-text
      (if (and node.session node.session.title)
        (tostring node.session.title)
        (.. "OpenCode session " node.id)))
    (status:set-text (status-line node))
    (metadata:set-text (session-text node))
    (config:set-text (config-text node))
    (subagents:set-text (children-text node)))
  (refresh-view nil)
  (local handler (node.changed:connect refresh-view))
  (local children [(child heading) (child status) (child metadata)
                   (child config) (child subagents)
                   (child messages) (child refresh)])
  (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0.3 :children children}) ctx))
  (fn drop [_self]
    (node.changed:disconnect handler true)
    (root:drop))
  {:layout root.layout :drop drop})

(fn Preview [node _opts]
  (fn build [ctx]
    (assert ctx "opencode session preview requires context")
    (content node ctx true)))

(fn View [node _opts]
  (fn build [ctx]
    (assert ctx "opencode session view requires context")
    (var content-view nil)
    (fn build-content [child-ctx]
      (local built (content node child-ctx false))
      (set content-view built)
      built)
    (local scroll ((ScrollView {:child build-content :padding false}) ctx))
    {:layout scroll.layout :drop scroll.drop}))

{:Preview Preview :View View}
