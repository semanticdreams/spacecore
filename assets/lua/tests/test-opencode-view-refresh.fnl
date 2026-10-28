(local Signal (require :signal))
(local H (require :tests/opencode-graph-helpers))
(local Messages (require :graph/view/views/opencode-session-messages))
(local Parts (require :graph/view/views/opencode-session-message-parts))
(local Message (require :graph/view/views/opencode-session-message))
(local Config (require :graph/view/views/opencode-config))
(local CodeRun (require :graph/view/views/code-run))
(local tests [])

(fn context []
  (local ctx (H.make-view-ctx))
  (tset ctx.icons.codepoints :code 4242)
  (local active {})
  (set ctx.clickables.register (fn [_self object] (tset active object true)))
  (set ctx.clickables.unregister (fn [_self object]
                                  (assert (. active object) "unregistered twice")
                                  (tset active object nil)))
  (values ctx active))

(fn text-of [button]
  (when (and button.text button.text.get-codepoints)
    (utf8.char (table.unpack (button.text:get-codepoints)))))

(fn find-button [active label]
  (var found nil)
  (each [object _ (pairs active)]
    (when (and object.clicked (= (text-of object) label)) (set found object)))
  (assert found (.. "missing visible button: " label)))

(fn click [button] (button:on-click nil))
(fn assert-dropped [built active]
  (built:drop)
  (assert (= (next active) nil) "view must release every registered child"))

(fn entry [id text]
  {:id id :valid? true :item {:message {:info {:id id :role "user"} :parts [{:type "text" :text text}]}}})

(fn message-list-refresh []
  (local (ctx active) (context))
  (var opened nil)
  (local node {:state :loading :label "messages" :changed (Signal)
               :open-message (fn [_self message] (set opened message))})
  (local built ((Messages.View node {}) ctx))
  (set node.state :ready)
  (set node.entries [(entry "m1" "hello")])
  (node.changed:emit node)
  (local row (find-button active "user: hello"))
  (click row)
  (assert (= opened (. node.entries 1 :item :message)))
  ;; Identical display but replacement payload: retain widget, use current data.
  (set node.entries [(entry "m1" "hello")])
  (node.changed:emit node)
  (assert (= row (find-button active "user: hello")))
  (click row)
  (assert (= opened (. node.entries 1 :item :message)))
  (set node.entries [(entry "m2" "later")])
  (node.changed:emit node)
  (click (find-button active "user: later"))
  (assert (= opened (. node.entries 1 :item :message)))
  (assert-dropped built active))

(fn message-invalid-ids []
  (local (ctx active) (context))
  (var count 0)
  (local invalid (entry "dup" "invalid"))
  (tset invalid :valid? false)
  (local node {:state :ready :label "messages" :changed (Signal)
               :entries [invalid (entry "dup" "valid")]
               :open-message (fn [_self _message] (set count (+ count 1)))})
  (local built ((Messages.View node {}) ctx))
  (each [object _ (pairs active)]
    (when (and object.clicked (string.find (or (text-of object) "") "invalid" 1 true)) (click object)))
  (assert (= count 0) "invalid duplicate rows must not materialize or alias valid rows")
  (click (find-button active "user: valid"))
  (assert (= count 1))
  (assert-dropped built active))

(fn message-pagination-noop []
  (local (ctx active) (context))
  (local node {:state :ready :label "messages" :changed (Signal)
               :entries (icollect [_ i (ipairs [1 2 3 4 5 6 7 8 9 10])] (entry (.. "m" i) (tostring i)))
               :open-message (fn [_self _message] nil)})
  (local built ((Messages.View node {}) ctx))
  (var next-button nil)
  (each [object _ (pairs active)]
    (when (= object.icon "chevron_right") (set next-button object)))
  (click (assert next-button))
  (local row (find-button active "user: 9"))
  (node.changed:emit node)
  (assert (= row (find-button active "user: 9")) "irrelevant emission must retain page and buttons")
  (assert-dropped built active))

(fn parts-refresh []
  (local (ctx active) (context))
  (var opened nil)
  (local first {:id "p1" :valid? true :item {:id "p1" :type "text" :text "before"}})
  (local node {:state :ready :label "parts" :changed (Signal) :parts [first]
               :open-part (fn [_self part] (set opened part))})
  (local built ((Parts.View node {}) ctx))
  (local row (find-button active "before"))
  (local replacement {:id "p1" :valid? true :item {:id "p1" :type "text" :text "before"}})
  (set node.parts [replacement])
  (node.changed:emit node)
  (assert (= row (find-button active "before")))
  (click row)
  (assert (= opened replacement) "equal displayed row must use the latest part")
  (set node.parts [])
  (node.changed:emit node)
  (assert (not (. active row)) "removed parts must drop buttons")
  (assert-dropped built active))

(fn message-hub-lifetime []
  (local (ctx active) (context))
  (var fields [{:id "parts" :label "Parts" :action :parts}])
  (var opened nil)
  (local node {:state :ready :label "message" :position 1 :message-count 1
               :message-id "m1" :session-id "s1" :message {:info {:role "user"} :parts []}
               :changed (Signal) :info-item-rows (fn [_self] fields)
               :open-parts (fn [_self] (set opened :parts))
               :open-info-field (fn [_self field] (set opened field))})
  (local built ((Message.View node {}) ctx))
  (each [object _ (pairs active)]
    (assert (not object.buffer) "full message view must not allocate a hidden transcript input"))
  (set fields [{:id "parts" :label "Parts" :action :parts}
               {:id "info:system" :label "system" :action :info :field "system"}])
  (node.changed:emit node)
  (click (find-button active "system"))
  (assert (= opened "system"))
  (local system-row (find-button active "system"))
  (set fields [{:id "parts" :label "Parts" :action :parts}])
  (node.changed:emit node)
  (assert (not (. active system-row)) "removed info fields must drop their rows")
  (assert-dropped built active))

(fn unchanged-loading-preview []
  (local (ctx active) (context))
  (local node {:state :loading :label "message" :changed (Signal)})
  (local built ((Message.Preview node {}) ctx))
  (local before built.preview-input.buffer)
  (node.changed:emit node)
  (assert (= built.preview-input.buffer before) "identical non-ready status must preserve its buffer")
  (assert-dropped built active))

(fn config-lossless-and-cache-refresh []
  (local (ctx active) (context))
  (local node {:state :ready :label "config" :changed (Signal)
               :config {:large (string.rep "x" 21000)} :providers {}})
  (local built ((Config.View node {}) ctx))
  (var input nil)
  (each [object _ (pairs active)]
    (when (and object.buffer (> (length (object.buffer:get-text)) 100)) (set input object)))
  (assert input)
  (assert (> (length (input.buffer:get-text)) 21000) "complete config JSON cannot be truncated")
  (input:move-caret-to-line-column 0 20500)
  (set node.config {:small "replacement"})
  (node.changed:emit node)
  (local expected (input.buffer:get-viewport {:line 0 :column 0 :lines 1 :columns 90}))
  (assert (= (. input.viewport.rows 1 :text) (. expected.rows 1 :text)) "config must reset viewport anchors")
  (local unchanged input.buffer)
  (node.changed:emit node)
  (assert (= input.buffer unchanged))
  (assert-dropped built active))

(fn independent-run-sections []
  (local (ctx active) (context))
  (local run {:status "running" :snapshot {:name "run" :language "fnl" :kernel "kernel-1"} :id "run-1"
              :code-entity-id "entity-1" :completion-mode "signal"
              :created-at 1000 :output "initial" :result "value" :result-type "string" :error false
              :artifacts [{:key "artifact:1" :label "First artifact"}]})
  (local node {:changed (Signal) :get-run (fn [_self] run)
               :show-code (fn [_self] nil) :show-artifact (fn [_self _artifact] nil)})
  (local built ((CodeRun.View node {}) ctx))
  (local result ((. built :result-input)))
  (local error-input ((. built :error-input)))
  (local result-before result.buffer)
  (local error-before error-input.buffer)
  (assert (= (type built.metadata-input) :function) "full run view must retain run metadata")
  (local metadata (built:metadata-input))
  (each [_ expected (ipairs ["Run: run-1" "Code: code-entity:entity-1" "Kernel: kernel-1 (fnl)" "Completion: signal"])]
    (assert (string.find (metadata.buffer:get-text) expected 1 true)))
  (set run.completion-mode "new-mode")
  (node.changed:emit node)
  (assert (= result.buffer result-before) "metadata-only refresh cannot replace result")
  (assert (= error-input.buffer error-before))
  (assert (string.find (metadata.buffer:get-text) "Completion: new-mode" 1 true))
  (local artifact-before (find-button active "First artifact"))
  (set run.output (string.rep "new output\n" 15))
  (node.changed:emit node)
  (assert (= result.buffer result-before) "output growth cannot reset result reading")
  (assert (= error-input.buffer error-before) "output growth cannot reset error reading")
  (assert (= artifact-before (find-button active "First artifact")) "unchanged artifacts must retain their list")
  (assert (> (. (built:output-input) :buffer :scroll-line) 0) "running output still follows its tail")
  (assert (= metadata.buffer.scroll-line 0) "metadata must not follow the output tail")
  (assert-dropped built active))

(table.insert tests {:name "messages list reconciles snapshots and current click payload" :fn message-list-refresh})
(table.insert tests {:name "messages invalid duplicate ids remain inert" :fn message-invalid-ids})
(table.insert tests {:name "messages irrelevant emissions preserve pagination" :fn message-pagination-noop})
(table.insert tests {:name "parts reconcile current payload and removal" :fn parts-refresh})
(table.insert tests {:name "message hub refresh owns no hidden preview" :fn message-hub-lifetime})
(table.insert tests {:name "message loading preview preserves identical buffer" :fn unchanged-loading-preview})
(table.insert tests {:name "configuration input is lossless and refreshes cache" :fn config-lossless-and-cache-refresh})
(table.insert tests {:name "code-run output updates preserve other section buffers" :fn independent-run-sections})
(fn main [] ((. (require :tests/runner) :run-tests) {:name "opencode-view-refresh" :tests tests}))
{:name "opencode-view-refresh" :tests tests :main main}
