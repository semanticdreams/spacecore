(local tests [])
(local fs (require :fs))
(local BuildContext (require :build-context))
(local {:Store Store} (require :code-runs/store))
(local {:Node code-run-node} (require :graph/nodes/code-run))
(local View (require :graph/view/views/code-run))

(var temp-counter 0)
(local temp-root (fs.join-path "/tmp/space/tests" "code-run-view"))

(fn make-dir []
  (set temp-counter (+ temp-counter 1))
  (local dir (fs.join-path temp-root (.. "case-" (os.time) "-" temp-counter)))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (fs.create-dirs dir)
  dir)

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

(fn make-icons-stub []
  (local glyph {:advance 1})
  (local font {:metadata {:metrics {:ascender 1 :descender -1}
                          :atlas {:width 1 :height 1}}
               :glyph-map {4242 glyph}
               :advance 1})
  (local stub {:font font
               :codepoints {:code 4242}})
  (set stub.get
       (fn [self name]
         (local value (. self.codepoints name))
         (assert value (.. "Missing icon " name))
         value))
  (set stub.resolve
       (fn [self name]
         (local code (self:get name))
         {:type :font
          :codepoint code
          :font self.font}))
  stub)

(fn make-ctx []
  (BuildContext {:clickables (make-clickables-stub)
                 :hoverables (make-hoverables-stub)
                 :icons (make-icons-stub)}))

(fn run-fields [overrides]
  (local base {:status "succeeded"
               :snapshot {:source "(print :hi)" :language "fnl" :name "View fixture run" :kernel "0"}
               :code-entity-id "view-fixture-entity"
               :created-at 1000
               :started-at 1000
               :started-monotonic-ms 0
               :elapsed-ms 5
               :timeout-ms 15000
               :finished-at 1005
               :completion-mode "signal"
               :output "line-one\nline-two\n"
               :initial-result ""
               :result-type "nil"
               :result ""
               :error false
               :artifacts []
               :owner {:session "view-fixture"}})
  (when overrides
    (each [key value (pairs overrides)]
      (tset base key value)))
  base)

(fn make-fixture [overrides]
  (local store (Store {:base-dir (make-dir)}))
  (local run (store:create-run (run-fields overrides)))
  {:store store
   :run run
   :node (code-run-node {:store store :run-id run.id})})

(fn payload-input-of [built key]
  ;; Full views expose output/result/error section inputs; previews expose
  ;; the single body input.
  (local accessor (or (and key (. built key)) built.body))
  (assert accessor "code-run view must expose its payload input")
  (if (= (type accessor) :function) (accessor) accessor))

(fn preview-of [fixture]
  (local built ((View.Preview fixture.node {}) (make-ctx)))
  built)

(fn full-view-of [fixture]
  (local built ((View.View fixture.node {}) (make-ctx)))
  built)

(fn row-text [input line]
  (local viewport (input.buffer:get-viewport {:line line :column 0 :lines 1 :columns 120}))
  (. viewport.rows 1 :text))

(fn test-preview-payload-is-readonly-bounded-tail []
  (local fixture (make-fixture))
  (local built (preview-of fixture))
  (local input (payload-input-of built))
  (assert (not input.editable?) "preview payload must be read-only")
  (assert (= input.line-count 8) "preview payload must bound its visible rows")
  (local lines (input.buffer:get-line-count))
  (assert (> lines 8) "fixture payload should exceed the preview viewport")
  (assert (= input.buffer.scroll-line (- lines 8)) "preview must follow the payload tail")
  (assert (= (row-text input (- lines 1)) "(none)") "preview tail row must be the payload end")
  (built.drop))

(fn test-full-view-sections-are-separate-inputs []
  (local fixture (make-fixture))
  (local built (full-view-of fixture))
  (local output (payload-input-of built :output-input))
  (local result (payload-input-of built :result-input))
  (local error-input (payload-input-of built :error-input))
  (assert (not output.editable?) "output must be read-only")
  (assert (= output.line-count 10) "output input must bound its visible rows")
  (assert (= output.buffer.scroll-line 0) "finished full views must start at the top")
  (assert (= (row-text output 0) "line-one") "output input must hold the run output")
  (assert (string.find (row-text result 0) "^Result ") "result input must hold the result section")
  (assert (= (row-text error-input 0) "(no error)") "error input must hold the error section")
  (built.drop))

(fn test-refresh-swaps-buffer-and-running-runs-follow-tail []
  (local fixture (make-fixture {:status "running" :finished-at false}))
  (local built (preview-of fixture))
  (local input (payload-input-of built))
  (local before-lines (input.buffer:get-line-count))
  (local updated-run (fixture.store:update-run fixture.run.id
                                              {:output "line-one\nline-two\nline-three\nline-four\nline-five\nline-six\nline-seven\nline-eight\nline-nine\nline-ten\nline-eleven\nline-twelve\n"}))
  (assert (> (input.buffer:get-line-count) before-lines) "refresh must swap in the grown payload")
  (local lines (input.buffer:get-line-count))
  (assert (= input.buffer.scroll-line (- lines 8)) "running run preview must follow the new tail")
  (assert (= (row-text input (- lines 10)) "line-twelve") "the newest output line must open the tail viewport")
  (assert (= (row-text input (- lines 1)) "(none)") "tail row must stay the payload end")
  (assert (= updated-run.status "running"))
  (built.drop))

(fn test-identical-payload-refresh-preserves-reading-position []
  (local many-lines
    (table.concat
      (icollect [index line (ipairs ["a" "b" "c" "d" "e" "f" "g" "h" "i" "j" "k" "l"
                                     "m" "n" "o" "p" "q" "r" "s" "t" "u" "v" "w" "x"
                                     "y" "z" "1" "2" "3" "4"])]
        (.. line "\n"))))
  (local fixture (make-fixture {:output many-lines}))
  (local built (full-view-of fixture))
  (local input (payload-input-of built :output-input))
  (assert (> (input.buffer:get-line-count) 26) "fixture must have more lines than the viewport")
  (input:scroll-lines 2)
  (assert (= input.buffer.scroll-line 2) "scroll must move before the no-op refresh")
  (fixture.store.changed:emit (fixture.store:get-run fixture.run.id))
  (assert (= input.buffer.scroll-line 2) "identical payload refresh must preserve reading position")
  (built.drop))

(fn test-view-drop-tears-down []
  (local fixture (make-fixture))
  (local built (preview-of fixture))
  (built.drop))

(fn test-double-click-opens-payload-in-external-editor-as-viewer []
  (local fixture (make-fixture))
  (local built (preview-of fixture))
  (local input (payload-input-of built))
  (local Presentation (require :code-runs/presentation))
  (local ExternalEditor (require :external-editor))
  (local original-edit-string ExternalEditor.edit-string)
  (var recorded nil)
  (var callback-ran? false)
  (set ExternalEditor.edit-string
       (fn [text callback _opts]
         (set recorded text)
         (callback "mutated")
         (set callback-ran? true)
         "/tmp/space/tests/external-editor-fixture"))
  (local head-before (row-text input 0))
  (local lines-before (input.buffer:get-line-count))
  (input.on-double-click input nil)
  (set ExternalEditor.edit-string original-edit-string)
  (assert callback-ran? "double-click must invoke the external editor")
  ;; Uniform contract: the editor opens exactly what the input displays.
  ;; The preview shows the bounded preview payload; the full view shows the
  ;; full payload.
  (assert (= recorded (Presentation.preview-payload fixture.run))
          "double-click must open the preview's displayed content")
  (assert (and (= (row-text input 0) head-before)
               (= (input.buffer:get-line-count) lines-before))
          "payload buffer must be unchanged after the editor returns")
  (assert (not input.editable?) "payload input must stay read-only")
  (built.drop))

(table.insert tests {:name "code-run preview payload is a read-only bounded tail" :fn test-preview-payload-is-readonly-bounded-tail})
(table.insert tests {:name "code-run full view sections are separate inputs" :fn test-full-view-sections-are-separate-inputs})
(table.insert tests {:name "code-run refresh swaps buffer and running runs follow tail" :fn test-refresh-swaps-buffer-and-running-runs-follow-tail})
(table.insert tests {:name "code-run identical payload refresh preserves reading position" :fn test-identical-payload-refresh-preserves-reading-position})
(table.insert tests {:name "code-run view drop tears down" :fn test-view-drop-tears-down})
(table.insert tests {:name "code-run double-click opens payload in external editor as viewer" :fn test-double-click-opens-payload-in-external-editor-as-viewer})

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "code-run-view"
                       :tests tests})))

{:name "code-run-view"
 :tests tests
 :main main}
