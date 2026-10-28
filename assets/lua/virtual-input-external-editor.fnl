(local Editor (require :external-editor))

;; Each launch owns one completion. Owner swaps and newer launches invalidate it;
;; same-buffer edits are protected by the launch text baseline as well.
(fn install! [input options notify-change]
  (var launch-id 0)
  (fn launch [_self _event]
    (assert (not input.__dropped) "cannot open external editor for dropped VirtualInput")
    (local current (assert input.buffer "VirtualInput requires a buffer"))
    (local baseline (current:get-text))
    (local editable? input.editable?)
    (local generation (assert input.buffer-generation "VirtualInput requires buffer generation"))
    (set launch-id (+ launch-id 1))
    (local id launch-id)
    (var completed? false)
    (fn complete [value err]
      (local consumed? completed?)
      (set completed? true)
      (local rejection
        (if consumed? "completion already consumed"
            input.__dropped "input dropped"
            (not= id launch-id) "newer editor launch"
            (not= generation input.buffer-generation) "owner replaced buffer"
            (not= input.buffer current) "owner replaced buffer"
            (not (and editable? input.editable?)) "read-only viewer"
            err (tostring err)
            (not= (type value) :string) "editor returned no text"
            (not= (current:get-text) baseline) "content changed while editor was open"
            nil))
      (if rejection
          (values false rejection)
          (= value baseline) (values true "unchanged")
          (do
            (current:replace-all value)
            (set current.scroll-line 0)
            (current:move-caret-to-byte 0)
            ;; replace-all invalidates buffer anchors, but input caches also need
            ;; the canonical reset. Synchronize before a callback may drop/swap.
            (input:set-buffer! current)
            (notify-change input)
            (values true "applied"))))
    (Editor.edit-string baseline complete options))
  (set input.on-double-click launch))

{:install! install!}
