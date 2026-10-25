(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Text (require :text))
(local Button (require :button))
(local SearchView (require :search-view))
(local ScrollView (require :scroll-view))
(local Presentation (require :code-runs/presentation))

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))
(fn content [node ctx compact?]
  (local heading ((Text {:text ""}) ctx))
  (local body (if compact? nil ((Text {:text ""}) ctx)))
  (fn show-code [_button _event] (node:show-code))
  (local code ((Button {:text "Show Code" :icon "code" :on-click show-code}) ctx))
  (local artifacts ((SearchView {:items [] :placeholder "Run artifacts" :items-per-page 5}) ctx))
  (fn show-artifact [item] (node:show-artifact (. item 1)))
  (artifacts.submitted:connect show-artifact)
  (fn refresh [_]
    (local run (node:get-run))
    (heading:set-text (Presentation.summary run))
    (when body (body:set-text (Presentation.payload run)))
    (artifacts:set-items (icollect [_ artifact (ipairs run.artifacts)] [artifact.key artifact.label])))
  (refresh nil)
  (local handler (node.changed:connect refresh))
  (local children [(child heading) (child code) (child artifacts)])
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
{:Preview Preview :View View}
