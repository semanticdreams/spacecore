(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Text (require :text))
(local Button (require :button))
(local SearchView (require :search-view))
(local ScrollView (require :scroll-view))
(local Presentation (require :code-runs/presentation))

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))

;; Previews stay compact: a bounded tail of recent output plus the error head.
;; Dense payloads remain in the full view.
(fn output-tail [run]
  (local limit 480)
  ;; Ignore a trailing newline so the last complete line survives cropping.
  (local body (string.gsub run.output "\n$" ""))
  (local cropped (if (> (# body) limit) (string.sub body (- (# body) (- limit 1))) body))
  (local nl (string.find cropped "\n"))
  (local aligned (if (and nl (> nl 1)) (string.sub cropped (+ nl 1)) cropped))
  (local parts [])
  (when (> (# aligned) 0) (table.insert parts aligned))
  (when run.error (table.insert parts (.. "Error: " run.error.message)))
  (if (= (length parts) 0) "(no output yet)" (table.concat parts "\n")))

(fn content [node ctx compact?]
  (local heading ((Text {:text ""}) ctx))
  (local tail (if compact? ((Text {:text ""}) ctx) nil))
  (local body (if compact? nil ((Text {:text ""}) ctx)))
  (fn show-code [_button _event] (node:show-code))
  (local code ((Button {:text "Show Code" :icon "code" :on-click show-code}) ctx))
  (local artifacts ((SearchView {:items [] :placeholder "Run artifacts" :items-per-page 5}) ctx))
  (fn show-artifact [item] (node:show-artifact (. item 1)))
  (artifacts.submitted:connect show-artifact)
  (fn refresh [_]
    (local run (node:get-run))
    (heading:set-text (Presentation.summary run))
    (when tail (tail:set-text (output-tail run)))
    (when body (body:set-text (Presentation.payload run)))
    (artifacts:set-items (icollect [_ artifact (ipairs run.artifacts)] [artifact.key artifact.label])))
  (refresh nil)
  (local handler (node.changed:connect refresh))
  (local children [(child heading)])
  (when tail (table.insert children (child tail)))
  (table.insert children (child code))
  (table.insert children (child artifacts))
  (when body (table.insert children (child body)))
  (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0.3 :children children}) ctx))
  (fn drop [_self]
    (node.changed:disconnect handler true)
    (artifacts.submitted:disconnect show-artifact true)
    (root:drop))
  {:layout root.layout :drop drop})

(fn Preview [node _opts]
  (fn build [ctx] (assert ctx "code-run preview requires context") (content node ctx true)))
(fn View [node _opts]
  (fn build [ctx]
    (assert ctx "code-run view requires context")
    (fn build-content [child-ctx] (content node child-ctx false))
    ((ScrollView {:child build-content :padding false}) ctx)))

;; Callable table keeps preview/full-view factories together without shared widget ownership.
{:Preview Preview :View View :output-tail output-tail}
