(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Text (require :text))
(local ScrollView (require :scroll-view))
(local ProjectionList (require :graph/view/views/opencode-projection-list))
(local Shared (require :graph/view/views/opencode-projection-shared))
(local VirtualInput (require :virtual-input))
(local LazyTextSource (require :lazy-text-source))
(local LazyTextBuffer (require :lazy-text-buffer))
(local Parts (require :graph/nodes/opencode-parts))
(local json (require :json))
(local Common (require :graph/nodes/opencode-common))

;; The message view is a projection hub: scalar info fields render directly
;; as labeled lines; complex items (parts and structured info fields) render as
;; clickable rows that materialize their own projection child node.

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))

(fn status-line [node]
  (local base
    (if (= node.state :loading)
        "Waiting for the parent session snapshot..."
        (= node.state :unavailable)
        (.. "Session unavailable: " (if node.error node.error "unknown error"))
        (= node.state :not-found)
        (.. "Session not found: " (if node.error node.error "unknown error"))
        (= node.state :absent)
        (.. "Not in the current session snapshot: " (if node.error node.error "unknown reason"))
        (= node.state :idle)
        "Parent session not materialized yet"
        (.. "Message " (tostring node.position) " of " (tostring node.message-count))))
  (if node.stale?
      (.. base " (last known data; refresh failed)")
      (and node.transcript-error (= node.state :ready))
      (.. base " (refresh failed: " (tostring node.transcript-error) ")")
      base))

(fn scalar-line [name value]
  ;; Structured values serialize as data, never assumed strings.
  (local rendered
    (if (= value nil) "-"
        (= (type value) :string) value
        (json.dumps value)))
  (.. name ": " rendered))

(fn scalars-text [node]
  (local message (if node.message node.message {}))
  (local info (if message.info message.info {}))
  (local out [])
  (each [_ entry (ipairs (. (Common.info-projection info) :scalars))]
    (table.insert out (scalar-line entry.label entry.value)))
  (table.insert out (.. "Session: opencode-session:" (tostring node.session-id)))
  (table.concat out "\n"))

(fn make-items-list [node ctx]
  (fn rows []
    (if (= node.state :ready)
        (icollect [_ row (ipairs (node:info-item-rows))]
          {:key row.id :label row.label :action row.action :field row.field :valid? true})
        [{:key "status" :label (status-line node) :placeholder true}]))
  (fn activate [row]
    (if (= row.action :parts) (node:open-parts) (node:open-info-field row.field)))
  ((ProjectionList {:rows rows :activate activate
                    :name "opencode-message-items" :paginate? false}) ctx))

(fn transcript-text [node]
  ;; Compact previews keep the canonical transcript rendering of the message.
  (if (not (= node.state :ready))
      (status-line node)
      (do
        (local transcript (Parts.compose-transcript [(if node.message node.message {})]))
        (if (> (length transcript) 0) transcript "(no renderable content)"))))

(fn make-preview-input [ctx]
  ((VirtualInput {:buffer (LazyTextBuffer {:source (LazyTextSource.string "")})
                  :line-count 8
                  :column-count 90
                  :editable? false
                  :name "opencode-message-preview"})
   ctx))

(fn content [node ctx compact?]
  (local heading ((Text {:text ""}) ctx))
  (local status ((Text {:text ""}) ctx))
  (local scalars ((Text {:text ""}) ctx))
  (local preview-input (and compact? (make-preview-input ctx)))
  (local items (and (not compact?) (make-items-list node ctx)))
  (var last-transcript nil)
  (fn refresh-view [_]
    (heading:set-text (tostring node.label))
    (status:set-text (status-line node))
    (scalars:set-text (if (= node.state :ready) (scalars-text node) ""))
    (when preview-input
      (set last-transcript (Shared.swap-buffer preview-input (transcript-text node) last-transcript)))
    (when items (items:refresh!)))
  (refresh-view nil)
  (local handler (node.changed:connect refresh-view))
  (local children [(child heading) (child status) (child scalars)])
  (if compact?
      (table.insert children (child preview-input))
      (do
        (table.insert children (child ((Text {:text "Complex items"}) ctx)))
        (table.insert children (child items))))
  (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0.3 :children children}) ctx))
  (fn drop [_self]
    (node.changed:disconnect handler true)
    (root:drop))
  (local out {:layout root.layout :drop drop
              :header-text (fn [_self] (scalars-text node))
              :preview-input preview-input})
  out)

(fn Preview [node _opts]
  (fn build [ctx]
    (assert ctx "opencode message preview requires context")
    (content node ctx true)))

(fn View [node _opts]
  (fn build [ctx]
    (assert ctx "opencode message view requires context")
    (var content-view nil)
    (fn build-content [child-ctx]
      (local built (content node child-ctx false))
      (set content-view built)
      built)
    (local scroll ((ScrollView {:child build-content :padding false}) ctx))
    (local merged {:layout scroll.layout :drop scroll.drop})
    (each [_ key (ipairs [:header-text])]
      (tset merged key
            (fn [_self]
              (assert content-view "opencode message detail builds with the scroll layout")
              (. content-view key))))
    merged))

{:Preview Preview :View View}
