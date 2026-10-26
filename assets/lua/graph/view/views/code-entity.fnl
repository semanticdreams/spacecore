(local Editor (require :graph/view/code-entity-editor))
(local ScrollView (require :scroll-view))
(fn View [node _opts]
  (fn build [ctx]
    (assert ctx "code entity view requires context")
    ((ScrollView {:child (Editor node false) :padding false}) ctx)))
View
