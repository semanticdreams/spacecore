(local fs (require :fs))

(local tests [])

(var temp-counter 0)
(local temp-root (fs.join-path "/tmp/space/tests" "code-entities"))

(fn make-temp-dir []
  (set temp-counter (+ temp-counter 1))
  (fs.join-path temp-root (.. "code-" (os.time) "-" temp-counter)))

(fn with-temp-dir [f]
  (local dir (make-temp-dir))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (fs.create-dirs dir)
  (local (ok result) (pcall f dir))
  (fs.remove-all dir)
  (if ok
      result
      (error result)))

(fn with-temp-store [f]
  (with-temp-dir
    (fn [root]
      (local CodeEntityStore (require :entities/code))
      (local store (CodeEntityStore.CodeEntityStore {:base-dir root}))
      (f store root))))

(fn disconnect-signal-handlers [records]
  (each [_ record (ipairs records)]
    (record.signal:disconnect record.handler true)))

(fn exercise-code-entity-signals [store counts]
  (local entity (store:create-entity {:source ""}))
  (store:update-entity entity.id {:source "x"})
  (store:retire-entity! entity.id)
  (assert (= counts.created 1) "created signal should emit once")
  (assert (= counts.updated 1) "updated signal should emit once")
  (assert (= counts.deleted 1) "deleted signal should emit once"))

(fn code-entity-store-creates-entities []
  (with-temp-store
    (fn [store _root]
      (local entity (store:create-entity {:source "(print :ok)"}))
      (assert entity "entity should be created")
      (assert entity.id "entity should have id")
      (assert (= entity.name "") "default name should be empty")
      (assert (= entity.language "fnl") "default language should be fnl")
      (assert (= entity.source "(print :ok)") "source should be stored")
      (assert (= entity.kernel 0) "default kernel should be id 0"))))

(fn code-entity-store-updates-entities []
  (with-temp-store
    (fn [store _root]
      (local entity (store:create-entity {:source ""}))
      (store:update-entity entity.id {:name "sample"
                                      :language "lua"
                                      :source "print('ok')"
                                      :kernel "python-default"})
      (local updated (store:get-entity entity.id))
      (assert (= updated.name "sample") "name should update")
      (assert (= updated.language "lua") "language should update")
      (assert (= updated.source "print('ok')") "source should update")
      (assert (= updated.kernel "python-default") "kernel should update"))))

(fn code-entity-store-emits-signals []
  (with-temp-store
    (fn [store _root]
      (local counts {:created 0 :updated 0 :deleted 0})
      (local created-handler (fn [_] (set counts.created (+ counts.created 1))))
      (local updated-handler (fn [_] (set counts.updated (+ counts.updated 1))))
      (local deleted-handler (fn [_] (set counts.deleted (+ counts.deleted 1))))
      (store.code-entity-created:connect created-handler)
      (store.code-entity-updated:connect updated-handler)
      (store.code-entity-deleted:connect deleted-handler)
      (local cleanup-records [{:signal store.code-entity-created :handler created-handler}
                              {:signal store.code-entity-updated :handler updated-handler}
                              {:signal store.code-entity-deleted :handler deleted-handler}])
      (local (ok result) (pcall exercise-code-entity-signals store counts))
      (local (cleanup-ok cleanup-result) (pcall disconnect-signal-handlers cleanup-records))
      (if (not ok)
          (error result)
          (not cleanup-ok)
          (error cleanup-result)))))

(fn code-entity-node-loads []
  (local {:CodeEntityNode CodeEntityNode} (require :graph/nodes/code-entity))
  (assert CodeEntityNode "CodeEntityNode should load")
  (assert (= (type CodeEntityNode) "function") "CodeEntityNode should be a function"))

(fn code-entity-node-creates-with-correct-properties []
  (with-temp-store
    (fn [store _root]
      (local entity (store:create-entity {:source "x"}))
      (local {:CodeEntityNode CodeEntityNode} (require :graph/nodes/code-entity))
      (local node (CodeEntityNode {:entity-id entity.id :store store}))
      (assert (= node.key (.. "code-entity:" entity.id)) "key should be prefixed entity id")
      (assert node.get-entity "node should expose get-entity")
      (assert node.update-name "node should expose update-name")
      (assert node.update-language "node should expose update-language")
      (assert node.update-source "node should expose update-source")
      (assert node.delete-entity "node should expose delete-entity")
      (node:drop))))

(fn code-entity-node-view-loads []
  (local CodeEntityNodeView (require :graph/view/views/code-entity))
  (assert CodeEntityNodeView "CodeEntityNodeView should load")
  (assert (= (type CodeEntityNodeView) "function") "CodeEntityNodeView should be a function"))

;; Also called by native E2E, under its already-started engine. Never start an
;; Engine/Harness here: tests.runner owns the unit engine.
(local H (require :tests/test-reference-lifecycle-helpers))

(fn count-entries [entries]
  (var count 0)
  (each [_ _ (pairs entries)] (set count (+ count 1)))
  count)

(fn interaction-counts []
  (assert (and app.clickables app.hoverables) "preview fixture requires caller interactions")
  [(# app.clickables.left-click-objects) (# app.clickables.right-click-objects)
   (# app.clickables.double-click-objects) (# app.hoverables.objects)])

(fn same-preview-value [actual expected]
  (local J (require :json-utils))
  (assert (= (J.stable-json actual) (J.stable-json expected))
          (.. "preview expected " (J.stable-json expected) ", got " (J.stable-json actual))))

(fn patch-preview-method [f target key replacement]
  (table.insert f.restores {:target target :key key :original (. target key)})
  (tset target key replacement))

(fn observe-preview-signal [f signal]
  (local observation {:active {} :disconnected 0})
  (local connect signal.connect)
  (local disconnect signal.disconnect)
  (local clear signal.clear)
  (patch-preview-method f signal :connect
    (fn [self handler]
      (tset observation.active handler true)
      (connect self handler)))
  (patch-preview-method f signal :disconnect
    (fn [self handler ...]
      (when (. observation.active handler)
        (tset observation.active handler nil)
        (set observation.disconnected (+ observation.disconnected 1)))
      (disconnect self handler ...)))
  (patch-preview-method f signal :clear
    (fn [self] (set observation.active {}) (clear self)))
  observation)

(fn observe-preview-tree [f widget]
  (assert (and widget.layout widget.drop) "preview descendants must be real widgets")
  (when (not (. f.widgets widget))
    (local record {:count 0 :name widget.layout.name})
    (tset f.widgets widget record)
    (local drop widget.drop)
    (patch-preview-method f widget :drop
      (fn [self]
        (set record.count (+ record.count 1))
        ;; Delegate even on duplicate calls: preserve Input's real RED error.
        (drop self)))
    (when (not (. f.layouts widget.layout))
      (tset f.layouts widget.layout {:name widget.layout.name}))
    (each [_ value (pairs widget)]
      (when (and (= (type value) :table) value.layout value.drop)
        (observe-preview-tree f value)))
    (each [_ child (ipairs (or widget.children []))]
      (observe-preview-tree f (or child.element child)))))

(fn preview-text [widget]
  (table.concat (icollect [_ cp (ipairs (widget:get-codepoints))] (utf8.char cp))))

(fn preview-resource-counts [canvas]
  (var count 0)
  (each [_ draw (ipairs (canvas:get-text-ssbo-draw-list))]
    (assert (> (draw.glyph-vector:length) 0) "preview requires native glyph allocations")
    (each [_ batch (ipairs draw.batches)]
      (each [_ size (ipairs batch.counts)] (set count (+ count size)))))
  (local quads (canvas.build-context:get-rectangle-quad-batcher))
  [count (quads:get-instance-count)])

(fn restore-preview-methods [f]
  (for [i (# f.restores) 1 -1]
    (local entry (. f.restores i))
    (tset entry.target entry.key entry.original))
  (set f.restores []))

(fn assert-preview-layout-detached [layout canvas]
  ;; A detached wrapper may still link its child; no ancestor may retain a live
  ;; layout root. Weak-reference checks below verify this whole graph is freed.
  (var ancestor layout)
  (local seen {})
  (while ancestor
    (assert (not (. seen ancestor)) "layout parent chain must terminate")
    (tset seen ancestor true)
    (assert (= ancestor.root nil) "dropped layout graph detached from root")
    (set ancestor ancestor.parent))
  (assert (not (. canvas.layout-root.measure-dirt.lookup layout)) "no measure dirt retention")
  (assert (not (. canvas.layout-root.layout-dirt.lookup layout)) "no layout dirt retention"))

(fn release-preview-observation [f canvas]
  (local weak (setmetatable [] {:__mode "v"}))
  (var index 0)
  (each [widget _ (pairs f.widgets)]
    (set index (+ index 1)) (tset weak index widget))
  (each [layout _ (pairs f.layouts)]
    (set index (+ index 1)) (tset weak index layout))
  (tset weak (+ index 1) canvas)
  (restore-preview-methods f)
  (set f.widgets {}) (set f.layouts {})
  weak)

(fn exercise-preview-cycle [f draw]
  (local glm (require :glm))
  (local canvas ((require :canvas) {:camera f.camera :focus-manager f.focus
                                   :icons f.icons :states app.states}))
  (set f.canvas canvas)
  (set f.drop-attempted? false)
  (local resources (preview-resource-counts canvas))
  (local interactions (interaction-counts))
  (local scopes (# f.focus.root.children))
  (local run-observation (observe-preview-signal f f.node.run-result-changed))
  (var external-results 0)
  (local external-handler (f.node.run-result-changed:connect
    (fn [_] (set external-results (+ external-results 1)))))
  (local flexes [])
  (local FlexModule (require :flex))
  (local original-flex FlexModule.Flex)
  (fn observed-flex [opts]
    (local build (original-flex opts))
    (fn [ctx]
      (local widget (build ctx))
      (table.insert flexes widget)
      widget))
  ;; Fresh-load only this factory under delegating constructor instrumentation.
  ;; Restore the require cache and module field immediately; no global wrapper
  ;; persists into other tests. The node still uses actual production source.
  (fn make-node []
    ((. (require :graph/nodes/code-entity) :CodeEntityNode)
      {:entity-id f.entity.id :store f.store}))
  (local observed-node
    (H.with-fields FlexModule {:Flex observed-flex}
      (fn [] (H.with-fields package.loaded {:graph/view/previews/code-entity false :graph/view/code-entity-editor false} make-node))))
  (local register app.clickables.register)
  (var submitted nil)
  (fn observe-register [self widget]
    (when widget.submitted
      (set submitted (observe-preview-signal f widget.submitted)))
    (register self widget))
  (fn builder [ctx]
    ;; Preview borrows the primary adapter, not the temporary factory carrier.
    ((observed-node.preview f.node) ctx))
  (canvas:on-viewport-changed {:width 640 :height 360})
  (H.with-fields app.clickables {:register observe-register}
    (fn [] (canvas:add-panel-child {:builder builder :position (glm.vec3 0)
                                   :size (glm.vec3 80 45 0)})))
  (observed-node:drop)
  (assert (= (# flexes) 2) "actual preview controls and editor root must be constructed")
  (local root (. flexes 2))
  (local input (. root.children 2 :element))
  (local label (. root.children 3 :element))
  (local button (. root.children 1 :element :children 1 :element))
  (observe-preview-tree f root)
  (assert (> (count-entries f.widgets) 6) "must observe real visual descendants too")
  (same-preview-value (input:get-text) f.entity.source)
  (same-preview-value (preview-text label) f.node.last-run-result)
  (same-preview-value [(count-entries run-observation.active) (count-entries submitted.active)] [2 1])
  (input:set-text "(+ 4 5)\n(+ 6 7)")
  (same-preview-value (. (f.store:get-entity f.entity.id) :source) (input:get-text))
  (button:on-click {})
  (assert (string.find (preview-text label) "result-1" 1 true))
  (input.submitted:emit {})
  (assert (string.find (preview-text label) "result-2" 1 true))
  (same-preview-value (# f.runs) 2)
  (each [_ request (ipairs f.runs)]
    (same-preview-value [request.source request.id request.language request.kernel]
                        [(input:get-text) f.entity.id "fnl" 0]))
  (input.focus-node:request-focus)
  (assert (= (f.focus:get-focused-node) input.focus-node))
  (local input-focus input.focus-node)
  (local button-focus button.focus-node)
  (canvas:update)
  (assert (> label.layout.measure.x 0) "results participate in real measurement")
  (assert input.layout-happened? "edited Input must lay out")
  (local allocated (preview-resource-counts canvas))
  (assert (> (. allocated 1) (. resources 1)) "preview must allocate native glyph draw ranges")
  (assert (> (. allocated 2) (. resources 2)) "preview must allocate native quad instances")
  (when draw (draw canvas))
  ;; Disconnects must happen before descendants drop, not only via signal.clear.
  (local input-drop input.drop)
  (patch-preview-method f input :drop
    (fn [self]
      (same-preview-value [submitted.disconnected (count-entries submitted.active)] [1 0])
      (same-preview-value [run-observation.disconnected (count-entries run-observation.active)] [1 1])
      (input-drop self)))
  (input.layout:mark-measure-dirty)
  (each [layout _ (pairs f.layouts)]
    (layout:mark-measure-dirty)
    (layout:mark-layout-dirty))
  (set f.drop-attempted? true)
  (canvas:drop)
  (set f.canvas nil)
  (each [_ record (pairs f.widgets)]
    (assert (= record.count 1) (.. "widget drop exactly once: " record.name)))
  (each [layout _ (pairs f.layouts)] (assert-preview-layout-detached layout canvas))
  (same-preview-value [(count-entries canvas.layout-root.measure-dirt.lookup)
                       (count-entries canvas.layout-root.layout-dirt.lookup)] [0 0])
  (same-preview-value (interaction-counts) interactions)
  (same-preview-value (preview-resource-counts canvas) resources)
  (same-preview-value (# f.focus.root.children) (- scopes 1))
  (assert (and (= input-focus.parent nil) (= button-focus.parent nil)) "focus nodes detached")
  (assert (= (f.focus:get-focused-node) nil) "drop releases focused Input")
  (assert (and (= input.__model-changed nil) (= input.__mode-changed nil)
               (= input.focus-node nil) (= button.focus-node nil)) "internal subscriptions/focus released")
  (local last-label (preview-text label))
  (f.node.run-result-changed:emit "after-drop")
  (same-preview-value (preview-text label) last-label)
  (same-preview-value external-results 3)
  (same-preview-value (count-entries run-observation.active) 1)
  (f.node.run-result-changed:disconnect external-handler)
  (same-preview-value (count-entries run-observation.active) 0)
  (assert (= (f.node:get-entity) f.entity) "borrowed adapter/store retain held record")
  (same-preview-value f.node-drops 0)
  (f.node:update-source "still-live")
  (same-preview-value f.entity.source "still-live")
  (release-preview-observation f canvas))

(fn run-preview-fixture [draw store _root]
  (local f {:store store :restores [] :widgets {} :layouts {} :runs [] :node-drops 0 :weak []})
  (set f.entity (store:create-entity {:source "(+ 1 2)"}))
  (fn run-code [_self id]
    (local entity (assert (store:get-entity id)))
    (table.insert f.runs {:source entity.source :id id :language entity.language :kernel entity.kernel})
    {:id (.. "run-" (# f.runs)) :code-entity-id id :status "succeeded" :elapsed-ms 0 :created-at 0
     :snapshot {:name (.. "result-" (# f.runs))} :output "" :initial-result ""
     :result "" :result-type "nil" :error false :artifacts []})
  (local code-runner {:run run-code})
  (set f.node ((. (require :graph/nodes/code-entity) :CodeEntityNode)
                {:entity-id f.entity.id :store store :runner code-runner}))
  (local node-drop f.node.drop)
  (set f.node.drop (fn [self] (set f.node-drops (+ f.node-drops 1)) (node-drop self)))
  (set f.node.last-run-result "initial-result")
  (set f.focus ((. (require :focus) :FocusManager) {:root-name "code-preview"}))
  (set f.camera ((require :camera) {:position ((. (require :glm) :vec3) 0 0 100)}))
  (set f.icons ((require :icons)))
  (local kernel {:run-code (fn obsolete-kernel-call [] (error "code entity must use its code runner"))})
  (fn body []
    (for [_ 1 3]
      (set f.runs [])
      (table.insert f.weak (exercise-preview-cycle f draw))))
  (local (ok result) (pcall H.with-fields app {:kernels kernel} body))
  ;; A failed owner drop is terminal: preserve the original RED, don't retry.
  (when (and f.canvas (not f.drop-attempted?)) (pcall f.canvas.drop f.canvas))
  (restore-preview-methods f)
  (f.icons:drop) (f.camera:drop) (f.focus:drop)
  ;; The fixture focus manager intentionally remembers its last focus node.
  ;; Release that owner before testing reachability, while engine/node/store live.
  (when ok
    (collectgarbage :collect) (collectgarbage :collect)
    (each [_ weak (ipairs f.weak)] (same-preview-value (count-entries weak) 0)))
  (f.node:drop)
  (when (not ok) (error result)))

(fn exercise-preview-lifecycle [draw]
  (assert (and app.engine (app.engine:is-started) (not (app.engine:is-shutdown)))
          "Code preview fixture requires initialized caller engine")
  (fn stored [store root] (run-preview-fixture draw store root))
  (with-temp-store stored))

(fn code-preview-lifecycle [] (exercise-preview-lifecycle nil))

(table.insert tests {:name "code preview recursively releases caller-owned Canvas subtree"
                     :fn code-preview-lifecycle})

(table.insert tests {:name "code entity store creates entities"
                     :fn code-entity-store-creates-entities})
(table.insert tests {:name "code entity store updates entities"
                     :fn code-entity-store-updates-entities})
(table.insert tests {:name "code entity store emits signals"
                     :fn code-entity-store-emits-signals})
(table.insert tests {:name "code entity node loads"
                     :fn code-entity-node-loads})
(table.insert tests {:name "code entity node creates with correct properties"
                     :fn code-entity-node-creates-with-correct-properties})
(table.insert tests {:name "code entity node view loads"
                      :fn code-entity-node-view-loads})

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "code-entities"
                       :tests tests})))

{:name "code-entities"
 :tests tests
 :exercise-preview-lifecycle exercise-preview-lifecycle
 :main main}
