(local SearchView (require :search-view))
(local Presentation (require :code-runs/presentation))
(fn History [node]
  (fn build [ctx]
    (assert ctx "code run history requires context")
    (local search ((SearchView {:items [] :placeholder "Code run history" :items-per-page 5}) ctx))
    (fn refresh [_]
      (search:set-items (icollect [_ run (ipairs (node:list-runs))] [run.id (Presentation.summary run)])))
    (fn submitted [item] (node:show-run (. item 1)))
    (refresh nil)
    (local changed (node.changed:connect refresh))
    (search.submitted:connect submitted)
    (fn drop [_self]
      (node.changed:disconnect changed true)
      (search.submitted:disconnect submitted true)
      (search:drop))
    {:layout search.layout :drop drop}))
History
