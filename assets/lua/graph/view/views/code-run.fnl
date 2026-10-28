(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Text (require :text))
(local Button (require :button))
(local SearchView (require :search-view))
(local ScrollView (require :scroll-view))
(local VirtualInput (require :virtual-input))
(local LazyTextSource (require :lazy-text-source))
(local LazyTextBuffer (require :lazy-text-buffer))
(local Presentation (require :code-runs/presentation))
(local json (require :json))

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))

;; Preview and full view show the same payload through a bounded read-only
;; viewport: run output and results can be huge, so the payload must scroll
;; and navigate instead of overflowing. The executed source lives behind
;; Show Code, not inline.
(fn make-payload-input [ctx compact?]
  ((VirtualInput {:buffer (LazyTextBuffer {:source (LazyTextSource.string "")})
                  :line-count (if compact? 8 10)
                  :column-count 80
                  :editable? false
                  :name (if compact? "code-run-preview-payload" "code-run-payload")})
    ctx))

(fn follow-tail [input buffer]
  ;; Previews and running runs follow the outcome tail; finished full views
  ;; start at the top so the payload can be read from the beginning.
  (local lines (buffer:get-line-count))
  (local visible (assert input.visible-line-count "payload input requires visible-line-count"))
  (input:scroll-lines (math.max 0 (- lines visible)))
  (buffer:move-caret-to-byte buffer.size)
  (input:refresh-viewport))

(fn content [node ctx compact?]
  (local heading ((Text {:text ""}) ctx))
  (fn show-code [_button _event] (node:show-code))
  (local code ((Button {:text "Show Code" :icon "code" :on-click show-code}) ctx))
  (local artifacts ((SearchView {:items [] :placeholder "Run artifacts" :items-per-page 5}) ctx))
  (fn show-artifact [item] (node:show-artifact (. item 1)))
  (artifacts.submitted:connect show-artifact)
  (var last-sections nil)
  (var last-artifacts nil)
  (var last-metadata nil)
  (local metadata (and (not compact?) (make-payload-input ctx false)))
  ;; One input per ontological unit: output, result, error.
  (fn section-text [run]
    (if compact?
        [(Presentation.preview-payload run)]
        [(Presentation.output-text run)
         (Presentation.result-text run)
         (Presentation.error-text run)]))
  (local bodies
    (if compact?
        [(make-payload-input ctx true)]
        [(make-payload-input ctx false)
         (make-payload-input ctx false)
         (make-payload-input ctx false)]))
  (fn refresh [_]
    (local run (node:get-run))
    (heading:set-text (Presentation.summary run))
    (when metadata
      (local text (Presentation.metadata-text run))
      (when (not= text last-metadata)
        (set last-metadata text)
        (metadata:set-buffer! (LazyTextBuffer {:source (LazyTextSource.string text)}))))
    (local sections (section-text run))
    ;; Skip identical sections so store pings cannot disturb reading
    ;; position; changed sections swap buffers (owner-driven).
    (each [i text (ipairs sections)]
      (local known (if last-sections (. last-sections i) nil))
      (when (not= text known)
        (local input (. bodies i))
        (local buffer (LazyTextBuffer {:source (LazyTextSource.string text)}))
        (input:set-buffer! buffer)
        (local follow? (if compact? true (= run.status "running")))
        (when (and follow? (= i 1))
          (follow-tail input buffer))
        (input:refresh-viewport)))
    (set last-sections sections)
    (local rows (icollect [_ artifact (ipairs run.artifacts)] [artifact.key artifact.label]))
    (local signature (json.dumps rows))
    (when (not= signature last-artifacts)
      (set last-artifacts signature)
      (artifacts:set-items rows)))
  (refresh nil)
  (local handler (node.changed:connect refresh))
  (local children [(child heading)])
  (when metadata (table.insert children (child metadata)))
  (each [_ input (ipairs bodies)]
    (table.insert children (child input)))
  (table.insert children (child code))
  (table.insert children (child artifacts))
  (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0.3 :children children}) ctx))
  (fn drop [_self]
    (node.changed:disconnect handler true)
    (artifacts.submitted:disconnect show-artifact true)
    (root:drop))
  (local out {:layout root.layout :drop drop :metadata-input metadata})
  (if compact?
      (tset out :body (. bodies 1))
      (do
        (tset out :output-input (. bodies 1))
        (tset out :result-input (. bodies 2))
        (tset out :error-input (. bodies 3))))
  out)

(fn Preview [node _opts]
  (fn build [ctx] (assert ctx "code-run preview requires context") (content node ctx true)))
(fn View [node _opts]
  (fn build [ctx]
    (assert ctx "code-run view requires context")
    (var content-view nil)
    (fn build-content [child-ctx]
      (local built (content node child-ctx false))
      (set content-view built)
      built)
    (local scroll ((ScrollView {:child build-content :padding false}) ctx))
    (local merged {:layout scroll.layout :drop scroll.drop})
    (each [_ key (ipairs [:metadata-input :output-input :result-input :error-input])]
      (tset merged key
            (fn [_self]
              (assert content-view "code-run payload builds with the scroll layout")
              (. content-view key))))
    merged))

;; Callable table keeps preview/full-view factories together without shared widget ownership.
{:Preview Preview :View View}
