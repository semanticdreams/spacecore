(local Input (require :input))
(local Text (require :text))
(local {: Layout} (require :layout))
(local {: Flex : FlexChild} (require :flex))
(local glm (require :glm))

(fn StringEntityEditor [node opts]
  (local options (or opts {}))
  (assert (and node node.read-text node.replace-text) "StringEntityEditor requires text operations")
  (fn build [ctx]
    (assert ctx "StringEntityEditor requires a build context")
    ;; This snapshot belongs to this editor, not the node's live store cache.
    (var baseline (node:read-text))
    (var editor nil)
    (var status-visible? false)
    (local status-text ((Text {:text ""}) ctx))
    ;; An empty Text still has a line height. Collapse its owned slot completely
    ;; until there is something to report, preserving both surfaces' geometry.
    (fn measure-status [layout]
      (if status-visible?
          (do (status-text.layout:measurer)
              (set layout.measure (+ status-text.layout.measure (glm.vec3 0 0.3 0))))
          (set layout.measure (glm.vec3 0))))
    (fn layout-status [layout]
      (set status-text.layout.position layout.position)
      (set status-text.layout.rotation layout.rotation)
      (set status-text.layout.size status-text.layout.measure)
      (set status-text.layout.depth-offset-index layout.depth-offset-index)
      (set status-text.layout.clip-region layout.clip-region)
      (status-text.layout:layouter))
    (local status-layout (Layout {:name "string-entity-save-status"
                                 :children [status-text.layout]
                                 :measurer measure-status :layouter layout-status}))
    (local status-slot {:layout status-layout
                        :drop (fn drop-status [_self]
                                (status-layout:drop)
                                (status-text:drop))})
    (fn show-status [message]
      (set status-visible? (not= message ""))
      (status-text:set-text message)
      (status-layout:mark-measure-dirty))
    (fn save [_input value]
      (local (ok result) (pcall node.replace-text node value baseline.revision))
      (if ok
          (do (set baseline result)
              (set editor.last-error nil)
              (show-status ""))
          (do
            (local err (if (and (= (type result) :table) result.code) result
                           {:code :internal-error :message (tostring result) :outcome :unknown}))
            (set editor.last-error err)
            (when (and (= err.outcome :committed) err.result err.result.revision)
              (set baseline err.result))
            (show-status
              (if (= err.outcome :committed) "Save committed; notification failed."
                  (= err.code :conflict) "Changes not saved: stale revision."
                  (= err.outcome :unknown) "Save outcome unknown; input preserved."
                  (.. "Changes not saved: " err.code "."))))))
    (local input ((Input {:text baseline.value
                         :placeholder options.placeholder
                         :multiline? true :min-lines options.min-lines :max-lines options.max-lines
                         :on-change save}) ctx))
    (local root ((Flex {:axis 2 :xalign :stretch :yspacing 0
                        :children [(FlexChild (fn input-child [_] input) 1)
                                   (FlexChild (fn status-child [_] status-slot) 0)]}) ctx))
    (set editor {:layout root.layout :input input :status-text status-text :last-error nil
                 :drop (fn drop-editor [_self] (root:drop))})
    editor))

StringEntityEditor
