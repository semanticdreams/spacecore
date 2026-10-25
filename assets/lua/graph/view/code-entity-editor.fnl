(local {:Flex Flex :FlexChild FlexChild} (require :flex))
(local Button (require :button))
(local Input (require :input))
(local Text (require :text))
(local History (require :graph/view/code-run-history))

(fn child [widget]
  (fn build [_ctx] widget)
  (FlexChild build 0))
(fn add-kernel-controls [node entity ctx children]
  (local kernel ((Text {:text (.. "Kernel: " (tostring entity.kernel))}) ctx))
  (fn kernel-changed [_input value]
    (node:update-kernel (if (= value "") 0 value))
    (kernel:set-text (.. "Kernel: " (tostring (. (node:get-entity) :kernel)))))
  (local selector ((Input {:text (tostring entity.kernel) :placeholder "Kernel" :on-change kernel-changed}) ctx))
  (fn selected [_button _event]
    (node:set-kernel-from-selection)
    (kernel:set-text (.. "Kernel: " (tostring (. (node:get-entity) :kernel)))))
  (local selection ((Button {:icon "my_location" :text "Use Selected" :on-click selected}) ctx))
  (table.insert children 2 (child kernel))
  (table.insert children 3 (child selector))
  (table.insert children 4 (child selection)))
(fn Editor [node compact?]
  (fn build [ctx]
    (assert ctx "code entity editor requires context")
    (local entity (assert (node:get-entity) "code entity missing"))
    (fn source-changed [_input value] (node:update-source value))
    (local source ((Input {:text "" :placeholder "Source..." :multiline? true
                           :min-lines (if compact? 3 6) :max-lines (if compact? 8 12)
                           :on-change source-changed}) ctx))
    (source:set-text entity.source {:reset-cursor? false})
    (local result ((Text {:text node.last-run-result}) ctx))
    (fn run [_button _event] (node:run-entity))
    (fn latest [_button _event] (node:show-latest-run))
    (local run-button ((Button {:icon "play_arrow" :text "Run" :on-click run}) ctx))
    (local latest-button ((Button {:icon "history" :text "Latest Run" :on-click latest}) ctx))
    (local controls ((Flex {:axis 1 :xspacing 0.2
      :children [(child run-button) (child latest-button)]}) ctx))
    (local children [(child controls) (child source) (child result)])
    (when (not compact?)
      (add-kernel-controls node entity ctx children)
      (table.insert children (child ((History node) ctx))))
    (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0.3 :children children}) ctx))
    (fn submitted [_value] (node:run-entity))
    (fn result-changed [value] (result:set-text value))
    (source.submitted:connect submitted)
    (local handler (node.run-result-changed:connect result-changed))
    (fn drop [_self]
      (source.submitted:disconnect submitted true)
      (node.run-result-changed:disconnect handler true)
      (root:drop))
    {:layout root.layout :drop drop}))
Editor
