(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Text (require :text))
(local ScrollView (require :scroll-view))
(local Shared (require :graph/view/views/opencode-projection-shared))
(local json (require :json))

;; An info node view retains one decoded snapshot value: strings render as text;
;; structured and other scalar values serialize as JSON data, never table ids.

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))

(fn value-text [node]
  (if (not (= node.state :ready))
      (Shared.status-line node)
      (if (not node.present?)
          "(absent from the current message)"
          (= (type node.value) :string)
          node.value
          (json.dumps node.value))))

(fn content [node ctx compact?]
  (local heading ((Text {:text ""}) ctx))
  (local status ((Text {:text ""}) ctx))
  (local input (Shared.make-detail-input ctx "opencode-message-info-value"))
  (var last-value nil)
  (fn refresh-view [_]
    (heading:set-text (tostring node.label))
    (status:set-text (Shared.status-line node))
    (set last-value (Shared.swap-buffer input (value-text node) last-value)))
  (local kids [(child heading) (child status) (child input)])
  (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0.3 :children kids}) ctx))
  (local handler (node.changed:connect refresh-view))
  (fn drop [_self]
    (node.changed:disconnect handler true)
    (root:drop))
  (refresh-view nil)
  {:layout root.layout :drop drop})

(fn Preview [node _opts]
  (fn build [ctx]
    (assert ctx "opencode info preview requires context")
    (content node ctx true)))

(fn View [node _opts]
  (fn build [ctx]
    (assert ctx "opencode info view requires context")
    (var content-view nil)
    (fn build-content [child-ctx]
      (local built (content node child-ctx false))
      (set content-view built)
      built)
    (local scroll ((ScrollView {:child build-content :padding false}) ctx))
    {:layout scroll.layout :drop scroll.drop}))

{:Preview Preview :View View}
