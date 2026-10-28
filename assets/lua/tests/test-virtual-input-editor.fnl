(local VirtualInput (require :virtual-input))
(local LazyTextBuffer (require :lazy-text-buffer))
(local LazyTextSource (require :lazy-text-source))
(local Editor (require :external-editor))
(local H (require :tests/opencode-graph-helpers))
(local tests [])

(fn buffer [text] (LazyTextBuffer {:source (LazyTextSource.string text)}))

(fn with-editor [body]
  (local original Editor.edit-string)
  (local pending [])
  (set Editor.edit-string (fn [text callback _opts]
                           (table.insert pending {:text text :callback callback})
                           "test-editor"))
  (local (ok err) (pcall body pending))
  (set Editor.edit-string original)
  (assert ok err))

(fn input-with [editable? on-change]
  ((VirtualInput {:buffer (buffer "original\nsecond\nthird")
                  :line-count 2 :column-count 12
                  :editable? editable? :on-change on-change})
   (H.make-view-ctx)))

(fn accepted-edit []
  (fn exercise [pending]
      (var notifications 0)
      (fn changed [self _buffer]
        (set notifications (+ notifications 1))
        (assert (= (. self.viewport.rows 1 :text) "new")))
      (local input (input-with true changed))
      (input:scroll-lines 1)
      (input.on-double-click input nil)
      ((. pending 1 :callback) "new\ncontent")
      (assert (= (input.buffer:get-text) "new\ncontent"))
      (assert (= notifications 1) "editor writeback must notify once after cache reset")
      (assert (= input.buffer.scroll-line 0))
      ((. pending 1 :callback) "duplicate completion")
      (assert (= notifications 1) "completion is consumed exactly once")
      (input:drop))
  (with-editor exercise))

(fn empty-and-unchanged []
  (fn exercise [pending]
      (var notifications 0)
      (fn changed [_self _buffer] (set notifications (+ notifications 1)))
      (local input (input-with true changed))
      (input:scroll-lines 1)
      (input.on-double-click input nil)
      ((. pending 1 :callback) (. pending 1 :text))
      (assert (= notifications 0) "unchanged editor text cannot dirty the document")
      (assert (= input.buffer.scroll-line 1))
      (input.on-double-click input nil)
      ((. pending 2 :callback) "")
      (assert (= (input.buffer:get-text) "") "empty content is an edit, not cancellation")
      (assert (= notifications 1))
      (input:drop))
  (with-editor exercise))

(fn rejects-conflicts []
  (each [_ kind (ipairs [:typing :owner-replace :swap :swap-back :drop :readonly-launch :readonly-now :error])]
    (fn exercise [pending]
        (var notifications 0)
        (fn changed [_self _buffer] (set notifications (+ notifications 1)))
        (local input (input-with (not= kind :readonly-launch) changed))
        (local initial input.buffer)
        (input.on-double-click input nil)
        (if (= kind :typing) (input:insert-text "typed")
            (= kind :owner-replace) (initial:replace-all "owner changed")
            (= kind :swap) (input:set-buffer! (buffer "replacement"))
            (= kind :swap-back) (do (input:set-buffer! (buffer "temporary")) (input:set-buffer! initial))
            (= kind :drop) (input:drop)
            (= kind :readonly-launch) (set input.editable? true)
            (= kind :readonly-now) (set input.editable? false))
        (local expected (input.buffer:get-text))
        (local before notifications)
        ((. pending 1 :callback) "stale edited content" (if (= kind :error) "editor error" nil))
        (assert (= (input.buffer:get-text) expected) (.. "must reject stale result: " kind))
        (assert (= notifications before) (.. "rejection cannot notify: " kind))
        (when (not input.__dropped) (input:drop)))
    (with-editor exercise)))

(fn newest-launch-wins []
  (fn exercise [pending]
      (local input (input-with true nil))
      (input.on-double-click input nil)
      (input.on-double-click input nil)
      ((. pending 1 :callback) "older")
      (assert (= (input.buffer:get-text) "original\nsecond\nthird"))
      ((. pending 2 :callback) "newest")
      (assert (= (input.buffer:get-text) "newest"))
      (input:drop))
  (with-editor exercise))

(fn notification-can-transfer-ownership []
  (each [_ action (ipairs [:drop :swap])]
    (fn exercise [pending]
        (fn changed [self _buffer]
          (if (= action :drop) (self:drop)
              (self:set-buffer! (buffer "owner replacement"))))
        (local input (input-with true changed))
        (input.on-double-click input nil)
        ((. pending 1 :callback) "accepted")
        (if (= action :drop)
            (assert input.__dropped)
            (do (assert (= (input.buffer:get-text) "owner replacement")) (input:drop))))
    (with-editor exercise)))

(table.insert tests {:name "editor writeback resets caches and notifies exactly once" :fn accepted-edit})
(table.insert tests {:name "editor accepts empty text but skips unchanged content" :fn empty-and-unchanged})
(table.insert tests {:name "editor rejects stale readonly errored and dropped completions" :fn rejects-conflicts})
(table.insert tests {:name "newest editor launch invalidates earlier completions" :fn newest-launch-wins})
(table.insert tests {:name "editor notification may synchronously transfer ownership" :fn notification-can-transfer-ownership})
(fn main [] ((. (require :tests/runner) :run-tests) {:name "virtual-input-editor" :tests tests}))
{:name "virtual-input-editor" :tests tests :main main}
