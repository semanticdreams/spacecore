(local {: Flex : FlexChild} (require :flex))
(local Button (require :button))
(local StringEntityEditor (require :graph/view/string-entity-editor))
(local gl (require :gl))
(local Utils (require :graph/view/utils))

(fn make-title [entity]
  (if (and entity entity.value (> (string.len entity.value) 0))
      (Utils.truncate-with-ellipsis entity.value 50)
      (or (and entity entity.id) "string entity")))

(fn StringEntityNodeView [node opts]
  (local options (or opts {}))
  (local target (or node options.node))

  (fn build [ctx]
    (local build-ctx (or ctx options.ctx (and target target.graph target.graph.ctx)))
    (assert build-ctx "StringEntityNodeView requires a build context")

    ;; The owning read must succeed before any action widgets acquire resources.
    (local editor
      ((StringEntityEditor target {:placeholder "Enter value..." :min-lines 3 :max-lines 20}) build-ctx))

    (local copy-value-button
      ((Button {:icon "content_copy"
                :text "Copy Value"
                :variant :ghost
                :on-click (fn [_button _event]
                            (local current (and target target.get-entity (target:get-entity)))
                            (when (and current current.value)
                              (gl.clipboard-set current.value)))})
       build-ctx))

    (local copy-id-button
      ((Button {:icon "tag"
                :text "Copy ID"
                :variant :ghost
                :on-click (fn [_button _event]
                            (local current (and target target.get-entity (target:get-entity)))
                            (when (and current current.id)
                              (gl.clipboard-set current.id)))})
       build-ctx))

    (local delete-button
      ((Button {:icon "delete"
                :text "Delete Entity"
                :variant :ghost
                :on-click (fn [_button _event]
                            (when (and target target.delete-entity)
                              (target:delete-entity)))})
       build-ctx))

    (local action-row
      ((Flex {:axis 1
              :xspacing 0.3
              :yalign :center
              :children [(FlexChild (fn [_] copy-value-button) 0)
                         (FlexChild (fn [_] copy-id-button) 0)
                         (FlexChild (fn [_] delete-button) 0)]})
       build-ctx))

    (local flex
      ((Flex {:axis 2
              :xalign :stretch
              :yspacing 0.5
              :children [(FlexChild (fn [_] action-row) 0)
                          (FlexChild (fn [_] editor) 1)]})
       build-ctx))

    {:input editor.input :editor editor :action-row action-row :layout flex.layout
     :drop (fn drop-view [_self] (flex:drop))}))

StringEntityNodeView
