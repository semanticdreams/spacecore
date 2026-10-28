(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Text (require :text))
(local ScrollView (require :scroll-view))
(local ProjectionList (require :graph/view/views/opencode-projection-list))
(local Parts (require :graph/nodes/opencode-parts))

;; Messages are rows only; each valid row materializes its own message node.

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))

(fn status-line [node]
  (if (= node.state :loading)
      "Waiting for the parent session snapshot..."
      (= node.state :unavailable)
      (.. "Session unavailable: " (if node.error node.error "unknown error"))
      (= node.state :not-found)
      (.. "Session not found: " (if node.error node.error "unknown error"))
      (= node.state :idle)
      "Parent session not materialized yet"
      (.. (tostring (length (if node.entries node.entries []))) " message(s)")))

(fn message-rows [node]
  (if (= node.state :ready)
      (icollect [index entry (ipairs (if node.entries node.entries []))]
        (do
          (local message entry.item.message)
          {:key (if entry.valid? (.. "id:" entry.id) (.. "invalid:" index))
           :valid? entry.valid?
           :label (.. (Parts.message-label message) (if entry.valid? "" " (invalid id — not clickable)"))
           :message message}))
      [{:key "status" :label (status-line node) :placeholder true}]))

(fn make-messages-list [node ctx]
  (fn rows [] (message-rows node))
  (fn activate [row] (node:open-message row.message))
  ((ProjectionList {:rows rows :activate activate
                    :name "opencode-session-messages-list" :paginate? true})
   ctx))

(fn content [node ctx compact?]
  (local heading ((Text {:text ""}) ctx))
  (local status ((Text {:text ""}) ctx))
  (local items (and (not compact?) (make-messages-list node ctx)))
  (fn refresh-view [_]
    (heading:set-text (tostring node.label))
    (status:set-text (status-line node))
    (when items (items:refresh!)))
  (local kids [(child heading) (child status)])
  (when (not compact?)
    (do
      (table.insert kids (child ((Text {:text "Messages"}) ctx)))
      (table.insert kids (child items))))
  (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0.3 :children kids}) ctx))
  (local handler (node.changed:connect refresh-view))
  (fn drop [_self]
    (node.changed:disconnect handler true)
    (root:drop))
  (refresh-view nil)
  {:layout root.layout :drop drop})

(fn Preview [node _opts]
  (fn build [ctx]
    (assert ctx "opencode messages preview requires context")
    (content node ctx true)))

(fn View [node _opts]
  (fn build [ctx]
    (assert ctx "opencode messages view requires context")
    (var content-view nil)
    (fn build-content [child-ctx]
      (local built (content node child-ctx false))
      (set content-view built)
      built)
    (local scroll ((ScrollView {:child build-content :padding false}) ctx))
    {:layout scroll.layout :drop scroll.drop}))

{:Preview Preview :View View}
