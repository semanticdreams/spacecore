(local fs (require :fs))
(local Uuid (require :uuid))
(local {:Store Store} (require :code-runs/store))
(local {:Runner Runner} (require :code-runs/runner))
(local {:CodeEntityStore CodeEntityStore} (require :entities/code))
(local {:Kernels Kernels} (require :kernels))
(local tests [])

(fn with-fixture [body]
  (local root (fs.join-path "/tmp/space/tests" (.. "code-runs-" (Uuid.v4))))
  (fs.create-dirs root)
  (local store (Store {:base-dir root}))
  (local codes (CodeEntityStore {:base-dir root}))
  (local kernels (Kernels {:base-dir root :defer-callbacks false}))
  (local time {:now 10})
  (local capture {})
  (local globals {})
  (each [key value (pairs _G)] (tset globals key value))
  (tset globals :capture capture)
  (fn clock [] time.now)
  (fn alive [_owner] true)
  (local runner (Runner {:store store :code-store codes :kernels kernels :clock clock
                        :wall-clock clock :pump? false :owner {:session "test"}
                        :owner-alive? alive :globals globals}))
  (fn create [source]
    (codes:create-entity {:name "Test" :source source :language "fnl" :kernel 0}))
  (local fixture {:store store :runner runner :codes codes :kernels kernels :time time
                  :capture capture :create create :root root})
  (local (ok err) (pcall body fixture))
  (when (not fixture.runner-dropped?) (runner:drop))
  (kernels:drop)
  (fs.remove-all root)
  (when (not ok) (error err)))

(fn run-source [f source opts]
  (local code (f.create source))
  (f.runner:run code.id opts))
(fn has? [value fragment] (not (= (string.find value fragment 1 true) nil)))
(fn add [name callback] (table.insert tests {:name (.. "code runs: " name) :fn callback}))

(add "sync values and nil complete without an explicit signal"
  (fn [] (with-fixture (fn [f]
    (each [_ source (ipairs ["(+ 5 3)" "(do nil)" "false" "{:answer 42}" "(fn [] 1)"])]
      (local run (run-source f source))
      (assert (= run.status "succeeded"))
      (assert (not (= run.finished-at false)))
      (assert (= run.snapshot.source source)))
    (assert (= (length (f.store:list-runs)) 5))))))

(add "captures print per execution and keeps it separate from return values"
  (fn [] (with-fixture (fn [f]
    (local run (run-source f "(print :hello 3) (+ 2 4)"))
    (assert (= run.status "succeeded"))
    (assert (= run.output "hello\t3\n"))
    (assert (= run.result "6"))
    (assert (= _G.execution nil))))))

(add "async completion has stable identity output and artifacts"
  (fn [] (with-fixture (fn [f]
    (local run (run-source f "(local done (execution:defer)) (set capture.cb (execution:wrap (fn [] (print :later) (execution:attach-artifact :string-entity:report :Report) (done:succeed {:answer 42})))) :started"))
    (assert (= run.status "running"))
    (assert (= run.initial-result "started"))
    (set f.time.now 35)
    (f.capture.cb)
    (local final (f.store:get-run run.id))
    (assert (= final.status "succeeded"))
    (assert (= final.elapsed-ms 25))
    (assert (= final.output "later\n"))
    (assert (= (. final.artifacts 1 :key) "string-entity:report"))
    (assert (has? final.result "42"))))))

(add "initial and callback exceptions override early completion"
  (fn [] (with-fixture (fn [f]
    (local initial (run-source f "(local done (execution:defer)) (done:succeed :early) (error :after-success)"))
    (assert (= initial.status "failed"))
    (assert (has? initial.error.message "after-success"))
    (local delayed (run-source f "(local done (execution:defer)) (set capture.cb (execution:wrap (fn [] (done:succeed :early) (error :callback-failed))))"))
    (f.capture.cb)
    (local final (f.store:get-run delayed.id))
    (assert (= final.status "failed"))
    (assert (has? final.error.message "callback-failed"))
    (assert (has? final.error.traceback "stack traceback"))))))

(add "immediate callbacks settle only after successful evaluation"
  (fn [] (with-fixture (fn [f]
    (local run (run-source f "(local done (execution:defer)) ((execution:wrap (fn [] (done:succeed :immediate)))) :returned"))
    (assert (= run.status "succeeded"))
    (assert (= run.result "immediate"))))))

(add "runs can finish out of order without sharing contexts"
  (fn [] (with-fixture (fn [f]
    (local first (run-source f "(local done (execution:defer)) (set capture.first (execution:wrap (fn [] (print :first) (done:succeed execution.id))))"))
    (local second (run-source f "(local done (execution:defer)) (set capture.second (execution:wrap (fn [] (print :second) (done:succeed execution.id))))"))
    (f.capture.second)
    (f.capture.first)
    (assert (= (. (f.store:get-run first.id) :result) first.id))
    (assert (= (. (f.store:get-run second.id) :output) "second\n"))))))

(add "timeouts and drop invalidate external late callbacks"
  (fn [] (with-fixture (fn [f]
    (local run (run-source f "(local done (execution:defer)) (set capture.cb (execution:wrap (fn [] (done:succeed :late))))" {:timeout-ms 20}))
    (set f.time.now 31)
    (f.runner:tick)
    (assert (= (. (f.store:get-run run.id) :status) "timed-out"))
    (f.capture.cb)
    (assert (= (. (f.store:get-run run.id) :status) "timed-out"))))))

(add "multiple deferrals and completions fail explicitly"
  (fn [] (with-fixture (fn [f]
    (local twice (run-source f "(execution:defer) (execution:defer)"))
    (assert (= twice.status "failed"))
    (local completion (run-source f "(local done (execution:defer)) (done:succeed 1) (done:succeed 2)"))
    (assert (= completion.status "failed"))))))

(add "source snapshots survive edits deletion and cold store reopen"
  (fn [] (with-fixture (fn [f]
    (local code (f.create "(+ 1 2)"))
    (local run (f.runner:run code.id))
    (f.codes:update-entity code.id {:source "(+ 8 9)"})
    (f.codes:retire-entity! code.id)
    (local reopened (Store {:base-dir f.root}))
    (assert (= (. (reopened:get-run run.id) :snapshot :source) "(+ 1 2)"))
    (assert (= (length (reopened:list-runs code.id)) 1))
    (assert (not (pcall reopened.update-run reopened run.id {:status "running"})))))))

(add "invalid source errors include original source traceback"
  (fn [] (with-fixture (fn [f]
    (local run (run-source f "(fn boom [] (error :boom)) (boom)"))
    (assert (= run.status "failed"))
    (assert (has? run.error.message "boom"))
    (assert (has? run.error.message "stack traceback"))))))

(add "a peer runner does not interrupt another live owner"
  (fn [] (with-fixture (fn [f]
    (local run (run-source f "(local done (execution:defer)) (set capture.cb (execution:wrap (fn [] (done:succeed 1))))"))
    ;; A separate runner simulates another generation, without disturbing fixture teardown.
    (local other (Runner {:store f.store :code-store f.codes :kernels f.kernels :pump? false
                          :owner {:session "other"} :owner-alive? (fn known-live [_] true)}))
    (other:drop)
    (assert (not (pcall other.run other run.code-entity-id)))
    (assert (= (. (f.store:get-run run.id) :status) "running"))))))

(add "drop interrupts active runs and wrapped callbacks cannot revive them"
  (fn [] (with-fixture (fn [f]
    (local run (run-source f "(local done (execution:defer)) (set capture.cb (execution:wrap (fn [] (done:succeed 1))))"))
    (f.runner:drop)
    (set f.runner-dropped? true)
    (f.capture.cb)
    (assert (= (. (f.store:get-run run.id) :status) "interrupted"))
    (assert (not (pcall f.runner.run f.runner run.code-entity-id)))))))

(add "cold recovery interrupts only proven dead owners"
  (fn [] (with-fixture (fn [f]
    (local run (run-source f "(execution:defer)"))
    (local other (Runner {:store f.store :code-store f.codes :kernels f.kernels :pump? false
                          :owner {:session "new"} :owner-alive? (fn known-dead [_] false)}))
    (assert (= (. (f.store:get-run run.id) :status) "interrupted"))
    (other:drop)))))

(add "startup persistence failure prevents execution"
  (fn [] (with-fixture (fn [f]
    (local code (f.create "(set capture.executed true)"))
    (local create f.store.create-run)
    (fn fail-write [_self _data] (error "disk unavailable"))
    (set f.store.create-run fail-write)
    (local (ok err) (pcall f.runner.run f.runner code.id))
    (set f.store.create-run create)
    (assert (not ok))
    (assert (has? (tostring err) "disk unavailable"))
    (assert (not f.capture.executed))))))

(add "real owner probe rejects PID reuse and recognizes the current process"
  (fn []
    (local Owner (require :code-runs/owner))
    (local current (Owner.current))
    (when current.pid
      (assert (= (Owner.alive? current) true))
      (set current.start "0")
      (assert (= (Owner.alive? current) false)))))

(add "external kernel replies complete independently of next-frame presentation"
  (fn [] (with-fixture (fn [f]
    (local external {:id "external" :name "Python"})
    (var reply nil)
    (fn resolve [_self selector] (assert (= selector "external")) external)
    (fn submit [_self request callback]
      (assert request.callback-immediate?)
      (set reply callback))
    (local kernel {:resolve-kernel resolve :run-code submit})
    (local runner (Runner {:store f.store :code-store f.codes :kernels kernel :pump? false
                          :owner {:session "external-test"} :owner-alive? (fn alive [_] true)}))
    (local code (f.codes:create-entity {:language "python" :kernel "external" :source "print(42)"}))
    (local run (runner:run code.id))
    (assert (= run.status "running"))
    (reply {:output "42\n" :error "" :registers {}})
    (assert (= (. (f.store:get-run run.id) :status) "succeeded"))
    (assert (= (. (f.store:get-run run.id) :output) "42\n"))
    (runner:drop)))))

(add "persistence observers cannot reenter a completing callback"
  (fn [] (with-fixture (fn [f]
    (local run (run-source f "(local done (execution:defer)) (set capture.calls 0) (set capture.cb (execution:wrap (fn [] (set capture.calls (+ capture.calls 1)) (done:succeed :done))))"))
    (fn reenter [current]
      (when (and (= current.id run.id) (= current.status "succeeded")) (f.capture.cb)))
    (local handler (f.store.changed:connect reenter))
    (f.capture.cb)
    (f.store.changed:disconnect handler true)
    (assert (= f.capture.calls 1))
    (assert (= (. (f.store:get-run run.id) :status) "succeeded"))))))

(add "native callback queue enforces a deferred deadline without UI frames"
  (fn [] (with-fixture (fn [f]
    (fn clock [] f.time.now)
    (local runner (Runner {:store f.store :code-store f.codes :kernels f.kernels :clock clock
                          :owner {:session "pump-test"} :owner-alive? (fn alive [_] true)}))
    (local code (f.create "(execution:defer)"))
    (local run (runner:run code.id {:timeout-ms 20}))
    (set f.time.now 31)
    ((. (require :callbacks) :dispatch))
    (assert (= (. (f.store:get-run run.id) :status) "timed-out"))
    (runner:drop)))))

(fn with-run-maps [f body]
  (local Graph (require :graph/init))
  (local {:GraphMap GraphMap} (require :graph/map))
  (local {:GraphNode GraphNode} (require :graph/node-base))
  (local Code (require :graph/nodes/code-entity))
  (local Runs (require :graph/extensions/builtins/code-runs))
  (local graph (Graph {:with-start false :entity-events? false}))
  (local descriptor (. (Runs.descriptors {:code-run-store f.store}) 1))
  (local handles (descriptor.install-loaders graph {:owner-id descriptor.id :extension-id descriptor.id}))
  (fn load-code [key]
    (local id (string.match key "^code%-entity:(.+)$"))
    (when (and id (f.codes:get-entity id))
      (Code.CodeEntityNode {:entity-id id :store f.codes :runner f.runner :run-store f.store})))
  (local code-handle (graph:register-key-loader "code-entity" load-code))
  (fn load-artifact [key] (GraphNode {:key key :label "Report"}))
  (local artifact-handle (graph:register-key-loader "test-artifact" load-artifact))
  (local map-a (GraphMap {:graph graph :id "code-runs-a"}))
  (local map-b (GraphMap {:graph graph :id "code-runs-b"}))
  (local (ok err) (pcall body map-a map-b graph))
  (map-a:drop) (map-b:drop) (graph:drop)
  (code-handle:unregister) (artifact-handle:unregister)
  (each [_ handle (ipairs handles)] (handle:unregister))
  (when (not ok) (error err)))

(add "graph exposes runs and artifacts only in the requesting map"
  (fn [] (with-fixture (fn [f]
    (fn exercise [map-a map-b _graph]
      (local code (f.create "(execution:attach-artifact :test-artifact:report :Report) 42"))
      (local source (assert (map-a:load-by-key (.. "code-entity:" code.id))))
      (assert (= (map-a:node-count) 1))
      (local run (source:run-entity))
      (assert (= (map-a:node-count) 2))
      (assert (= (map-b:node-count) 0))
      (local a (assert (map-a:lookup (.. "code-run:" run.id))))
      (local b (assert (map-b:load-by-key (.. "code-run:" run.id))))
      (assert (not (= a b)))
      (b:show-artifact "test-artifact:report")
      (assert (= (map-b:node-count) 2))
      (assert (= (map-a:node-count) 2))
      (assert (not (pcall a.show-artifact a "test-artifact:foreign")))
      (f.codes:retire-entity! code.id)
      (assert (= (. (f.store:get-run run.id) :snapshot :source) code.source)))
    (with-run-maps f exercise)))))

(add "dropping a graph adapter leaves deferred execution owned by the runner"
  (fn [] (with-fixture (fn [f]
    (fn exercise [map-a _map-b _graph]
      (local code (f.create "(local done (execution:defer)) (set capture.cb (execution:wrap (fn [] (done:succeed 7))))"))
      (local source (assert (map-a:load-by-key (.. "code-entity:" code.id))))
      (local run (source:run-entity))
      (map-a:remove-nodes [source])
      (f.capture.cb)
      (assert (= (. (f.store:get-run run.id) :result) "7")))
    (with-run-maps f exercise)))))

(fn exercise-run-widget [node compact?]
  (local glm (require :glm))
  (local focus ((. (require :focus) :FocusManager) {:root-name "code-run-widget"}))
  (local camera ((require :camera) {:position (glm.vec3 0 0 100)}))
  (local icons ((require :icons)))
  (local canvas ((require :canvas) {:camera camera :focus-manager focus :icons icons :states app.states}))
  (fn build [ctx]
    (if compact? ((node.preview node) ctx) ((node.view node) ctx)))
  (fn body []
    (canvas:on-viewport-changed {:width 640 :height 360})
    (canvas:add-panel-child {:builder build :position (glm.vec3 0) :size (glm.vec3 80 45 0)})
    (canvas:update)
    (node.changed:emit node)
    (canvas:update))
  (local (ok err) (pcall body))
  (canvas:drop)
  (icons:drop) (camera:drop) (focus:drop)
  (when (not ok) (error err))
  ;; No widget callback may remain after its caller-owned Canvas is gone.
  (node.changed:emit node))

(add "run preview and full view build with caller context and detach on drop"
  (fn [] (with-fixture (fn [f]
    (fn exercise [map-a _map-b _graph]
      (local code (f.create "(print :captured) {:answer 42}"))
      (local source (assert (map-a:load-by-key (.. "code-entity:" code.id))))
      (local run (source:run-entity))
      (local node (assert (map-a:lookup (.. "code-run:" run.id))))
      (for [_ 1 3] (exercise-run-widget node true) (exercise-run-widget node false)))
    (with-run-maps f exercise)))))

(fn main [] ((. (require :tests/runner) :run-tests) {:name "code-runs" :tests tests}))
{:tests tests :main main}
