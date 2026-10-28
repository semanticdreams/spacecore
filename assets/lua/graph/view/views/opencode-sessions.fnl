(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Text (require :text))
(local Button (require :button))
(local ListView (require :list-view))
(local ScrollView (require :scroll-view))

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))

(fn status-line [node]
  (if node.error
      (.. "Error: " node.error)
      (= node.state :loading)
      "Loading sessions..."
      (= node.state :idle)
      "Not loaded yet — use Refresh Sessions"
      (.. (tostring (length (if node.sessions node.sessions []))) " sessions"
          (if node.fetched-at
            (.. " — fetched " (os.date "!%Y-%m-%d %H:%M:%S UTC" node.fetched-at))
            ""))))

(fn session-entry-button [node entry child-ctx]
  ;; Placeholder rows are informational, not session references.
  (if entry.placeholder
      ((Text {:text entry.label}) child-ctx)
      (do
        (local on-click (fn [_btn _event] (node:open-session entry)))
        ((Button {:text entry.label
                  :variant :ghost
                  :on-click on-click})
         child-ctx))))

(fn make-sessions-list [node ctx compact?]
  (local builder (fn [entry child-ctx] (session-entry-button node entry child-ctx)))
  (local name (if compact? "opencode-sessions-preview" "opencode-sessions-list"))
  (local per-page (if compact? 6 12))
  ((ListView {:items []
              :name name
              :show-head false
              :items-per-page per-page
              :paginate true
              :builder builder})
   ctx))

(fn render-items [node]
  (if node.error
      [{:id "error" :label (.. "Error: " node.error) :placeholder true}]
      (= node.state :loading)
      [{:id "loading" :label "Loading sessions..." :placeholder true}]
      (= (length (if node.sessions node.sessions [])) 0)
      [{:id "empty" :label "No sessions found on the OpenCode server" :placeholder true}]
      (icollect [_ session (ipairs node.sessions)]
        {:id (if session.id (tostring session.id) "?")
         :label (node:session-label session)
         :item session})))

;; Preview and full view share content; the list is bounded by ListView paging.
(fn content [node ctx compact?]
  (local heading ((Text {:text ""}) ctx))
  (local status ((Text {:text ""}) ctx))
  (local list (make-sessions-list node ctx compact?))
  (fn refresh [_]
    (heading:set-text "OpenCode sessions")
    (status:set-text (status-line node))
    (list:set-items (render-items node)))
  (refresh nil)
  (local handler (node.changed:connect refresh))
  (local children [(child heading) (child status) (child list)])
  (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0.3 :children children}) ctx))
  (fn drop [_self]
    (node.changed:disconnect handler true)
    (root:drop))
  {:layout root.layout :drop drop})

(fn make-scroll-view [build-content ctx]
  ((ScrollView {:child build-content :padding false}) ctx))

(fn Preview [node _opts]
  (fn build [ctx]
    (assert ctx "opencode sessions preview requires context")
    (content node ctx true)))

(fn View [node _opts]
  (fn build [ctx]
    (assert ctx "opencode sessions view requires context")
    (fn build-content [child-ctx] (content node child-ctx false))
    (make-scroll-view build-content ctx)))

{:Preview Preview :View View :render-items render-items}
