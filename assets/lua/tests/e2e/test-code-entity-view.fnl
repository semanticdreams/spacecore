(local Harness (require :tests.e2e.harness))
(local Dialog (require :dialog))
(local Graph (require :graph/init))
(local {:CodeEntityNode CodeEntityNode} (require :graph/nodes/code-entity))
(local CodeEntityNodeView (require :graph/view/views/code-entity))
(local CodeEntityStore (require :entities/code))
(local CodeRunStore (require :code-runs/store))
(local fs (require :fs))
(local glm (require :glm))

(var temp-counter 0)
(local temp-root (fs.join-path "/tmp/space/tests" "e2e-code-entity"))

(fn make-temp-dir []
  (set temp-counter (+ temp-counter 1))
  (fs.join-path temp-root (.. "e2e-" (os.time) "-" temp-counter)))

(fn with-temp-store [f]
  (local dir (make-temp-dir))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (fs.create-dirs dir)
  (local store (CodeEntityStore.CodeEntityStore {:base-dir dir}))
  (local run-store (CodeRunStore.Store {:base-dir dir}))
  (local (ok result) (pcall f {:root dir
                               :store store
                               :run-store run-store}))
  (fs.remove-all dir)
  (if ok
      result
      (error result)))

(fn run [ctx]
  (with-temp-store
    (fn [deps]
      (local graph (Graph {:with-start false}))
      (local entity
        (deps.store:create-entity
          {:name "Medication helper"
           :language "fnl"
           :source "(+ 40 2)"
           :kernel 0}))
      (local node (CodeEntityNode {:entity-id entity.id
                                    :store deps.store
                                    :run-store deps.run-store}))
      (set node.last-run-result "42")
      (graph:add-node node {})

      (local view-builder (CodeEntityNodeView node))
      (local dialog-builder
        (Dialog {:title (or node.label "Code Entity")
                 :child (fn [child-ctx]
                          (view-builder child-ctx))}))
      (local target
        (Harness.make-screen-target {:width ctx.width
                                     :height ctx.height
                                     :world-units-per-pixel ctx.units-per-pixel
                                     :builder (fn [child-ctx]
                                                (dialog-builder child-ctx))}))

      (Harness.draw-targets ctx.width ctx.height [{:target target}])
      (Harness.capture-snapshot {:name "code-entity-view"
                                 :width ctx.width
                                 :height ctx.height
                                 :tolerance 3})

      (Harness.cleanup-target target)
      (graph:drop))))

(fn main []
  (Harness.with-app {:width 800
                     :height 600}
                    (fn [ctx]
                      (run ctx)))
  (print "E2E code entity view snapshot complete"))

{:run run
 :main main}
