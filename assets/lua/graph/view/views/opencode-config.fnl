(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Text (require :text))
(local ScrollView (require :scroll-view))
(local VirtualInput (require :virtual-input))
(local LazyTextSource (require :lazy-text-source))
(local LazyTextBuffer (require :lazy-text-buffer))
(local json (require :json))

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))

(fn status-line [node]
  (if (= node.state :loading)
      "Loading config..."
      (= node.state :unavailable)
      (.. "Unavailable: " (if node.error node.error "unknown error"))
      (= node.state :idle)
      "Not loaded yet — use Refresh Config"
      (.. "Current server config — fetched "
          (if node.fetched-at
            (os.date "!%Y-%m-%d %H:%M:%S UTC" node.fetched-at)
            "?"))))

(fn config-text [node]
  (if node.config-error
      (.. "Config unavailable: " node.config-error)
      node.config
      (json.dumps node.config)
      "(not loaded)"))

(fn providers-text [node]
  (if node.providers-error
      (.. "Providers unavailable: " node.providers-error)
      node.providers
      (json.dumps node.providers)
      "(not loaded)"))

(fn make-readonly-input [ctx name]
  ((VirtualInput {:buffer (LazyTextBuffer {:source (LazyTextSource.string "")})
                  :line-count 14
                  :column-count 90
                  :editable? false
                  :name name})
    ctx))

(fn swap-text [input last-ref text]
  ;; last-ref is a one-cell table owned by the view; identical text never
  ;; disturbs reading position.
  (when (not= text (. last-ref 1))
    (tset last-ref 1 text)
    (local buffer (LazyTextBuffer {:source (LazyTextSource.string text)}))
    (input:set-buffer! buffer)))

(fn content [node ctx compact?]
  (local heading ((Text {:text ""}) ctx))
  (local status ((Text {:text ""}) ctx))
  (local config-label ((Text {:text "Server config"}) ctx))
  (local providers-label ((Text {:text "Providers"}) ctx))
  (local config-body (make-readonly-input ctx "opencode-config-view"))
  (local providers-body (make-readonly-input ctx "opencode-providers-view"))
  (local config-ref [nil])
  (local providers-ref [nil])
  (fn refresh-view [_]
    (heading:set-text "opencode config")
    (status:set-text (status-line node))
    (swap-text config-body config-ref (config-text node))
    (swap-text providers-body providers-ref (providers-text node)))
  (refresh-view nil)
  (local handler (node.changed:connect refresh-view))
  (local children [(child heading) (child status)
                   (child config-label) (child config-body)
                   (child providers-label) (child providers-body)])
  (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0.3 :children children}) ctx))
  (fn drop [_self]
    (node.changed:disconnect handler true)
    (root:drop))
  {:layout root.layout :drop drop})

(fn Preview [node _opts]
  (fn build [ctx]
    (assert ctx "opencode config preview requires context")
    (content node ctx true)))

(fn View [node _opts]
  (fn build [ctx]
    (assert ctx "opencode config view requires context")
    (fn build-content [child-ctx] (content node child-ctx false))
    ((ScrollView {:child build-content :padding false}) ctx)))

{:Preview Preview :View View}
