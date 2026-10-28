;; Read-only VirtualInput coverage; appended to tests.test-virtual-input.
(local tests [])
(local gl (require :gl))
(local BuildContext (require :build-context))
(local VirtualInput (require :virtual-input))
(local LazyTextSource (require :lazy-text-source))
(local LazyTextBuffer (require :lazy-text-buffer))

(fn make-clickables-stub []
  (local state {:register 0 :unregister 0 :register-right 0 :unregister-right 0
                :register-double 0 :unregister-double 0})
  (local stub {:state state})
  (set stub.register (fn [_self _obj] (set state.register (+ state.register 1))))
  (set stub.unregister (fn [_self _obj] (set state.unregister (+ state.unregister 1))))
  (set stub.register-right-click (fn [_self _obj] (set state.register-right (+ state.register-right 1))))
  (set stub.unregister-right-click (fn [_self _obj] (set state.unregister-right (+ state.unregister-right 1))))
  (set stub.register-double-click (fn [_self _obj] (set state.register-double (+ state.register-double 1))))
  (set stub.unregister-double-click (fn [_self _obj] (set state.unregister-double (+ state.unregister-double 1))))
  stub)

(fn make-hoverables-stub []
  (local state {:register 0 :unregister 0})
  (local stub {:state state})
  (set stub.register (fn [_self _obj] (set state.register (+ state.register 1))))
  (set stub.unregister (fn [_self _obj] (set state.unregister (+ state.unregister 1))))
  stub)

(fn make-ctx []
  (BuildContext {:clickables (make-clickables-stub)
                 :hoverables (make-hoverables-stub)}))

(fn input-with [content editable?]
  ((VirtualInput {:buffer (LazyTextBuffer {:source (LazyTextSource.string content)})
                  :line-count 1
                  :column-count 8
                  :editable? editable?})
    (make-ctx)))

(fn readonly-input [content] (input-with content false))
(fn editable-input [content] (input-with content true))

(fn viewport-text [input]
  (local viewport (input.buffer:get-viewport {:line 0 :column 0 :lines 1 :columns 80}))
  (. viewport.rows 1 :text))

(fn test-readonly-blocks-user-edits []
  (local input (readonly-input "abcdef"))
  (assert (= input.mode :normal) "readonly input should start in normal mode")
  (input:enter-insert-mode)
  (assert (= input.mode :normal) "readonly input must not enter insert mode")
  (assert (not (input:on-text-input {:text "Z"}))
          "readonly input must not accept text input")
  (assert (not (input:insert-text "Z")) "readonly insert-text must be a no-op")
  (assert (not (input:delete-at-cursor)) "readonly delete-at-cursor must be a no-op")
  (assert (= (viewport-text input) "abcdef") "readonly buffer content must not change")
  (input:drop))

(fn test-readonly-blocks-save-keeps-navigation []
  (local input (readonly-input "alpha\nbeta"))
  (assert (not (input:save)) "readonly save must be a no-op")
  (assert (input:scroll-lines 1) "readonly input must keep scrolling")
  (assert (input:move-caret-to-line-column 1 2) "readonly input must keep caret navigation")
  (input:drop))

(fn test-readonly-copies-selection []
  (var clipboard-text nil)
  (local original-clipboard-set gl.clipboard-set)
  (set gl.clipboard-set (fn [text] (set clipboard-text text)))
  (local input (readonly-input "copy me"))
  (assert (input.buffer:set-selection 0 4) "set-selection must work on readonly buffers")
  (assert (= (input:copy-selection) "copy") "readonly copy-selection must return selected text")
  (assert (= clipboard-text "copy") "readonly copy must reach the clipboard")
  (input:drop)
  (set gl.clipboard-set original-clipboard-set))

(fn test-editable-default-still-edits []
  (local input (editable-input "abcdef"))
  (assert input.editable? "default input must stay editable")
  (assert (input:insert-text "Z") "editable input must insert")
  (input:drop))

(fn test-virtual-input-registers-double-click []
  (local clickables (make-clickables-stub))
  (local hoverables (make-hoverables-stub))
  (local input
    ((VirtualInput {:buffer (LazyTextBuffer {:source (LazyTextSource.string "text")})
                    :line-count 1
                    :column-count 8})
      (BuildContext {:clickables clickables :hoverables hoverables})))
  (assert (= clickables.state.register-double 1) "VirtualInput must register for double-click dispatch")
  (assert (= (type input.on-double-click) :function) "VirtualInput must define the uniform double-click handler")
  (input:drop)
  (assert (= clickables.state.unregister-double 1) "VirtualInput drop must unregister double-click"))

(table.insert tests {:name "VirtualInput readonly blocks user edits" :fn test-readonly-blocks-user-edits})
(table.insert tests {:name "VirtualInput readonly blocks save and keeps navigation" :fn test-readonly-blocks-save-keeps-navigation})
(table.insert tests {:name "VirtualInput readonly copies selection" :fn test-readonly-copies-selection})
(table.insert tests {:name "VirtualInput editable default still edits" :fn test-editable-default-still-edits})
(table.insert tests {:name "VirtualInput registers double-click dispatch" :fn test-virtual-input-registers-double-click})

tests
