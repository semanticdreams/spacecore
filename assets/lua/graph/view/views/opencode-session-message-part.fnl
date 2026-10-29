(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Text (require :text))
(local ScrollView (require :scroll-view))
(local Shared (require :graph/view/views/opencode-projection-shared))
(local json (require :json))

;; A part node view. Cards build views once, so the section set is fixed:
;; Content, Detail, Tool input, Tool output, Tool error, Raw part. Sections
;; that do not apply to the current part kind say so explicitly — never
;; silently empty. The Raw part input keeps the complete original part so
;; leaf separation never regresses losslessness.

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))

(fn scalars-text [node]
  (local part (if node.part node.part {}))
  (.. "Id: " (tostring (if part.id part.id node.part-id))
      "\nType: " (tostring (if part.type part.type "?"))
      "\nMessage: opencode-session-message:" (tostring node.session-id)
      "/" (tostring node.message-id)))

(fn content-text [node part]
  (local ptype (if part.type (tostring part.type) "?"))
  (if (= ptype "text")
      (if (and part.text (> (length part.text) 0))
          (tostring part.text)
          "(empty)")
      (= ptype "reasoning")
      (if (and part.text (> (length part.text) 0))
          (tostring part.text)
          "(empty)")
      (= ptype "tool")
      (do
        (local state (if part.state part.state {}))
        (.. "Name: " (tostring (if part.tool part.tool "?"))
            "\nStatus: " (tostring (if state.status state.status "?"))
            (if state.title (.. "\nTitle: " (tostring state.title)) "")))
      (= ptype "patch")
      (json.dumps {:files part.files :hash part.hash})
      (json.dumps part)))

(fn detail-text [node part]
  (local ptype (if part.type (tostring part.type) "?"))
  (if (= ptype "text")
      (json.dumps {:time part.time :metadata part.metadata})
      (= ptype "reasoning")
      (json.dumps {:time part.time :metadata part.metadata})
      (= ptype "tool")
      (do
        (local state (if part.state part.state {}))
        (json.dumps {:callID part.callID
                     :attachments state.attachments
                     :metadata part.metadata}))
      (json.dumps part)))

(fn tool-state-text [key part]
  (local ptype (if part.type (tostring part.type) "?"))
  (if (= ptype "tool")
      (do
        (local state (if part.state part.state {}))
        (if (not= (. state key) nil)
            (json.dumps (. state key))
            (.. "(no " key ")")))
      "(not a tool part)"))

(fn section-status-texts [status]
  [(.. "Content — " status)
   (.. "Detail — " status)
   (.. "Tool input — " status)
   (.. "Tool output — " status)
   (.. "Tool error — " status)
   (.. "Raw part — " status)])

(fn section-texts [node]
  ;; Ordered section texts for the fixed section set. Non-ready states fill
  ;; every section with the status line — no silent empties.
  (if (not (= node.state :ready))
      (section-status-texts (Shared.status-line node))
      (do
        (local part (if node.part node.part {}))
        [(content-text node part)
         (detail-text node part)
         (tool-state-text :input part)
         (tool-state-text :output part)
         (tool-state-text :error part)
         (json.dumps part)])))

(fn content [node ctx compact?]
  (local heading ((Text {:text ""}) ctx))
  (local status ((Text {:text ""}) ctx))
  (local scalars ((Text {:text ""}) ctx))
  (local labels ["Content" "Detail" "Tool input" "Tool output" "Tool error" "Raw part"])
  (local label-widgets (icollect [_ label (ipairs labels)]
                         ((Text {:text label}) ctx)))
  (local sections
    (icollect [index _label (ipairs labels)]
      {:input (Shared.make-detail-input ctx (.. "opencode-part-section-" (tostring index)))
       :last nil}))
  (fn refresh-view [_]
    (heading:set-text (tostring node.label))
    (status:set-text (Shared.status-line node))
    (local texts (section-texts node))
    (scalars:set-text (if (= node.state :ready) (scalars-text node) ""))
    (each [index built (ipairs sections)]
      (local text (. texts index))
      (tset built :last (Shared.swap-buffer built.input text built.last))))
  (local kids [(child heading) (child status) (child scalars)])
  (each [_ widget (ipairs label-widgets)]
    (table.insert kids (child widget)))
  (each [_ built (ipairs sections)]
    (table.insert kids (child built.input)))
  (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0.3 :children kids}) ctx))
  (local handler (node.changed:connect refresh-view))
  (fn drop [_self]
    (node.changed:disconnect handler true)
    (root:drop))
  (refresh-view nil)
  (local out {:layout root.layout :drop drop
              :inputs (icollect [_ built (ipairs sections)] built.input)
              :labels labels})
  out)

(fn Preview [node _opts]
  (fn build [ctx]
    (assert ctx "opencode part preview requires context")
    (content node ctx true)))

(fn View [node _opts]
  (fn build [ctx]
    (assert ctx "opencode part view requires context")
    (var content-view nil)
    (fn build-content [child-ctx]
      (local built (content node child-ctx false))
      (set content-view built)
      built)
    (local scroll ((ScrollView {:child build-content :padding false}) ctx))
    (local merged {:layout scroll.layout :drop scroll.drop})
    (each [_ key (ipairs [:inputs :labels])]
      (tset merged key
            (fn [_self]
              (assert content-view "opencode part view builds with the scroll layout")
              (. content-view key))))
    merged))

{:Preview Preview :View View}
