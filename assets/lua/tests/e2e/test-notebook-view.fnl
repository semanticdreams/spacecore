(local Harness (require :tests.e2e.harness))
(local Dialog (require :dialog))
(local Sized (require :sized))
(local Graph (require :graph/init))
(local {:register-loader register-string-entity-loader} (require :graph/nodes/string-entity))
(local {:NotebookNode NotebookNode} (require :graph/nodes/notebook))
(local NotebookNodeView (require :graph/view/views/notebook))
(local StringEntityStore (require :entities/string))
(local NotebookStore (require :notebooks/store))
(local fs (require :fs))
(local glm (require :glm))

(var temp-counter 0)
(local temp-root (fs.join-path "/tmp/space/tests" "e2e-notebook"))

(fn make-temp-dir []
  (set temp-counter (+ temp-counter 1))
  (fs.join-path temp-root (.. "e2e-" (os.time) "-" temp-counter)))

(fn with-temp-stores [f]
  (local dir (make-temp-dir))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (fs.create-dirs dir)
  (local string-store (StringEntityStore.StringEntityStore {:base-dir (fs.join-path dir "string")}))
  (local notebook-store (NotebookStore.NotebookStore {:base-dir (fs.join-path dir "notebooks")}))
  (local (ok result) (pcall f {:root dir
                               :string-store string-store
                               :notebook-store notebook-store}))
  (fs.remove-all dir)
  (if ok
      result
      (error result)))

(fn run [ctx]
  (with-temp-stores
    (fn [deps]
      (local graph (Graph {:with-start false}))
      (register-string-entity-loader graph {:store deps.string-store})

      (local s1 (deps.string-store:create-entity {:value "Patient summary: stable vitals"}))
      (local s2 (deps.string-store:create-entity {:value "Plan: follow-up labs tomorrow"}))
      (local notebook (deps.notebook-store:create-notebook
                        {:name "Rounds Notes"
                         :items [(.. "string-entity:" s1.id)
                                 (.. "string-entity:" s2.id)]}))
      (local node (NotebookNode {:notebook-id notebook.id
                                 :store deps.notebook-store}))
      (graph:add-node node {})

      (local view-builder (NotebookNodeView node))
      (local dialog-builder
        (Dialog {:title (or node.label "Notebook")
                 :child (fn [child-ctx]
                          (view-builder child-ctx))}))
      (local sized
        (Sized {:size (glm.vec3 34 24 0)
                :child (fn [child-ctx]
                         (dialog-builder child-ctx))}))
      (local target
        (Harness.make-screen-target {:width ctx.width
                                     :height ctx.height
                                     :world-units-per-pixel ctx.units-per-pixel
                                     :builder (fn [child-ctx]
                                                (sized child-ctx))}))

      (Harness.draw-targets ctx.width ctx.height [{:target target}])
      (Harness.capture-snapshot {:name "notebook-view"
                                 :width ctx.width
                                 :height ctx.height
                                 :tolerance 3})

      (Harness.cleanup-target target)
      (graph:drop))))

(local H (require :tests/test-reference-lifecycle-helpers))
(local Code (require :graph/nodes/code-entity))
(local CodeTests (require :tests/test-code-entities))

(fn native-code-draw [canvas]
  (Harness.draw-targets 640 360 [{:target canvas}])
  ((. (require :gl) :glFinish)))

(fn code-interactions []
  (assert (and app.clickables app.hoverables) "native Code preview requires caller interactions")
  [(# app.clickables.left-click-objects) (# app.clickables.right-click-objects)
   (# app.clickables.double-click-objects) (# app.hoverables.objects)])

(fn assert-code-value [actual expected]
  (local J (require :json-utils))
  (assert (= (J.stable-json actual) (J.stable-json expected)) "native Code preview value mismatch"))

(fn notebook-row-remove [view]
  (local row (assert (. view.list.item-widgets 1) "expected real Code notebook row"))
  (. row.children 2 :element :children 1 :element :children 3 :element))

(fn code-notebook-cycle [f]
  (local baseline (code-interactions))
  (local canvas ((require :canvas) {:camera f.camera :focus-manager f.focus
                                   :icons app.icons :states app.states}))
  (set f.canvas canvas) (set f.drop-attempted? false)
  (var view nil)
  (fn builder [ctx] (set view ((NotebookNodeView f.node) ctx)) view)
  (canvas:on-viewport-changed {:width 640 :height 360})
  (canvas:add-panel-child {:builder builder :position (glm.vec3 0) :size (glm.vec3 80 45 0)})
  (native-code-draw canvas)
  (assert (= (# view.list.item-widgets) 1) "registered Code preview must appear inline")
  (for [_ 1 2]
    (view:refresh-items)
    (native-code-draw canvas))
  (local remove-button (notebook-row-remove view))
  (remove-button:on-click {})
  (assert (= (# f.notebook.items) 0) "actual Notebook Remove updates owning membership")
  (assert (= (# view.list.item-widgets) 0) "removal drops inline Code preview")
  (f.adapter.run-result-changed:emit "after-removal")
  (f.deps.notebook-store:add-item f.notebook.id f.adapter.key)
  (native-code-draw canvas)
  (assert (= (# view.list.item-widgets) 1) "registered Code preview rebuilds after re-add")
  (assert (> (# (canvas:get-text-ssbo-draw-list)) 0) "Notebook must draw real native text")
  (set f.drop-attempted? true)
  (canvas:drop) (set f.canvas nil)
  (each [_ row (ipairs f.rows)] (assert (= row.drops 1) "every rebuilt Code preview drops once"))
  (assert-code-value (code-interactions) baseline)
  (assert (= (# (canvas:get-text-ssbo-draw-list)) 0) "Notebook releases live glyph ranges")
  (local quads (canvas.build-context:get-rectangle-quad-batcher))
  (assert (= (quads:get-instance-count) 0) "Notebook releases live native quads")
  (assert (= (# f.focus.root.children) 0) "Notebook Canvas detaches focus scope")
  (f.adapter.run-result-changed:emit "after-notebook-drop")
  (assert (= f.adapter-drops 0) "Notebook preview borrows registered adapter")
  (assert (= (f.code-store:get-entity f.entity.id) f.entity) "Code store/held record survive")
  (assert (= (f.graph:lookup f.adapter.key) f.adapter) "registered Code adapter survives rebuild/drop"))

(fn exercise-code-notebook [deps]
  (local code-store ((. (require :entities/code) :CodeEntityStore)
                     {:base-dir (fs.join-path deps.root "code")}))
  (local entity (code-store:create-entity {:source "(+ 20 22)"}))
  (local graph (Graph {:with-start false :identity-store deps.notebook-store.identity-store}))
  (Code.register-loader graph {:store code-store})
  (local adapter (assert (graph:load-by-key (.. "code-entity:" entity.id)) "actual registered Code loader"))
  (local notebook (deps.notebook-store:create-notebook {:name "Code teardown" :items [adapter.key]}))
  (local node (NotebookNode {:notebook-id notebook.id :store deps.notebook-store}))
  (graph:add-node node {})
  (local f {:deps deps :code-store code-store :entity entity :graph graph :adapter adapter
            :notebook notebook :node node :rows [] :adapter-drops 0
            :focus ((. (require :focus) :FocusManager) {:root-name "native-Code-notebook"})
            :camera ((require :camera) {:position (glm.vec3 0 0 100)})})
  (local preview adapter.preview)
  (local adapter-drop adapter.drop)
  (fn observed-preview [target opts]
    (local build (preview target opts))
    (fn [ctx]
      (local widget (build ctx))
      (local row {:drops 0})
      (table.insert f.rows row)
      (local drop widget.drop)
      (set widget.drop (fn [self] (set row.drops (+ row.drops 1)) (drop self)))
      widget))
  (fn observed-drop [self]
    (set f.adapter-drops (+ f.adapter-drops 1)) (adapter-drop self))
  (fn body [] (for [_ 1 3] (code-notebook-cycle f)))
  (local (ok result) (pcall H.with-fields adapter {:preview observed-preview :drop observed-drop} body))
  (when (and f.canvas (not f.drop-attempted?)) (pcall f.canvas.drop f.canvas))
  (graph:drop) (f.camera:drop) (f.focus:drop)
  (when (not ok) (error result))
  (assert (= (# f.rows) 12) "three cycles each build initial, two refreshes and re-added Code previews"))

(fn code-lifecycle [_ctx]
  ;; Caller engine is the sole native Harness engine. This helper never invokes
  ;; the unit runner; it exercises the same real lifecycle assertions with GL.
  (CodeTests.exercise-preview-lifecycle native-code-draw)
  (with-temp-stores exercise-code-notebook)
  (print "Native Code preview: 3 standalone cycles and 12 registered Notebook previews passed"))

(fn main []
  (Harness.with-app {}
                   (fn [ctx]
                      (run ctx)
                      (code-lifecycle ctx)))
  (print "E2E notebook view snapshot complete"))

{:run run
 :main main}
