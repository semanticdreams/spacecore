(local {: Flex : FlexChild} (require :flex))
(local Button (require :button))
(local Input (require :input))
(local Text (require :text))

(fn CodeEntityNodePreview [node opts]
  (local options (or opts {}))
  (local target (or node options.node))

  (fn build [ctx]
    (local build-ctx (or ctx options.ctx (and target target.graph target.graph.ctx)))
    (assert build-ctx "CodeEntityNodePreview requires a build context")
    (local view {})
    (local entity (and target target.get-entity (target:get-entity)))

    (local source-input
      ((Input {:text ""
               :placeholder "Source..."
               :multiline? true
               :min-lines 3
               :max-lines 8
               :on-change (fn [_input new-value]
                            (when (and target target.update-source)
                              (target:update-source new-value)))})
       build-ctx))
    (when (and source-input source-input.set-text entity)
      (source-input:set-text (or entity.source "") {:reset-cursor? false}))

    (fn run-source []
      (when (and target target.run-entity)
        (target:run-entity)))
    (local source-submitted-handler
      (and source-input source-input.submitted
           (fn [_payload]
             (run-source))))
    (when source-submitted-handler
      (source-input.submitted:connect source-submitted-handler))

    (local run-button
      ((Button {:icon "play_arrow"
                :text ""
                :variant :ghost
                :padding [0.2 0.2]
                :on-click (fn [_button _event]
                            (run-source))})
       build-ctx))

    (local result-label
      ((Text {:text ""})
       build-ctx))
    (when (and target target.last-run-result)
      (result-label:set-text target.last-run-result))

    (local content-column
      ((Flex {:axis 2
              :xalign :stretch
              :yspacing 0.25
              :children [(FlexChild (fn [_] source-input) 1)
                         (FlexChild (fn [_] result-label) 0)]})
       build-ctx))

    (local controls-column
      ((Flex {:axis 2
              :xalign :center
              :yalign :start
              :yspacing 0.25
              :children [(FlexChild (fn [_] run-button) 0)]})
       build-ctx))

    (local flex
      ((Flex {:axis 1
              :xalign :stretch
              :yalign :stretch
              :xspacing 0.25
              :children [(FlexChild (fn [_] content-column) 1)
                         (FlexChild (fn [_] controls-column) 0)]})
       build-ctx))

    (local run-signal (and target target.run-result-changed))
    (local run-handler
      (and run-signal
           (fn [value]
             (result-label:set-text (or value "")))))
    (when run-signal
      (run-signal:connect run-handler))

    (set view.layout flex.layout)
    (set view.drop
         (fn [_self]
           (when run-signal
             (run-signal:disconnect run-handler true))
           (when source-submitted-handler
             (source-input.submitted:disconnect source-submitted-handler true))
           (flex:drop)))
    view))

CodeEntityNodePreview
