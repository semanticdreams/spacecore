(local StringEntityEditor (require :graph/view/string-entity-editor))

(fn StringEntityNodePreview [node opts]
  (local options (or opts {}))
  (local target (or node options.node))

  (fn build [ctx]
    (local build-ctx (or ctx options.ctx (and target target.graph target.graph.ctx)))
    (assert build-ctx "StringEntityNodePreview requires a build context")
    (local editor ((StringEntityEditor target {:placeholder "Value..." :min-lines 3 :max-lines 3}) build-ctx))
    {:layout editor.layout :input editor.input :editor editor
     :drop (fn drop-preview [_self] (editor:drop))}))

StringEntityNodePreview
