(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Text (require :text))
(local ScrollView (require :scroll-view))
(local ProjectionList (require :graph/view/views/opencode-projection-list))
(local Shared (require :graph/view/views/opencode-projection-shared))
(local Parts (require :graph/nodes/opencode-parts))

;; The parts view lists the parent message's raw parts. Rows with a
;; validated unique url-safe id are clickable and materialize their own
;; part node; parts without one stay visible but inert.

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))

(fn parts-summary [node]
  (if (not (= node.state :ready))
      (Shared.status-line node)
      (do
        (local count (length (if node.parts node.parts [])))
        (.. (tostring count) " part(s) in the message"))))

(fn parts-list-rows [entries]
  (icollect [index entry (ipairs entries)]
    (do
      (local suffix (if entry.valid? "" " (no id — not clickable)"))
      {:key (if entry.valid? (.. "id:" entry.id) (.. "invalid:" index))
       :valid? entry.valid?
       :label (.. (Parts.part-row-label entry.item) suffix)
       :entry entry})))

(fn parts-rows [node]
  (if (= node.state :ready)
      (parts-list-rows (if node.parts node.parts []))
      [{:key "status" :label (Shared.status-line node) :placeholder true}]))

(fn make-parts-list [node ctx]
  (fn rows [] (parts-rows node))
  (fn activate [row] (node:open-part row.entry))
  ((ProjectionList {:rows rows :activate activate
                    :name "opencode-message-parts" :paginate? true})
   ctx))

(fn content [node ctx compact?]
  (local heading ((Text {:text ""}) ctx))
  (local status ((Text {:text ""}) ctx))
  (local items (and (not compact?) (make-parts-list node ctx)))
  (fn refresh-view [_]
    (heading:set-text (tostring node.label))
    (status:set-text (parts-summary node))
    (when items (items:refresh!)))
  (refresh-view nil)
  (local handler (node.changed:connect refresh-view))
  (local children [(child heading) (child status)])
  (if (not compact?)
      (do
        (table.insert children (child ((Text {:text "Parts"}) ctx)))
        (table.insert children (child items))))
  (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0.3 :children children}) ctx))
  (fn drop [_self]
    (node.changed:disconnect handler true)
    (root:drop))
  {:layout root.layout :drop drop})

(fn Preview [node _opts]
  (fn build [ctx]
    (assert ctx "opencode parts preview requires context")
    (content node ctx true)))

(fn View [node _opts]
  (fn build [ctx]
    (assert ctx "opencode parts view requires context")
    (var content-view nil)
    (fn build-content [child-ctx]
      (local built (content node child-ctx false))
      (set content-view built)
      built)
    (local scroll ((ScrollView {:child build-content :padding false}) ctx))
    {:layout scroll.layout :drop scroll.drop}))

{:Preview Preview :View View}
