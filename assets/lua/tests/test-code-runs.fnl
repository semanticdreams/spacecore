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
    (assert (= run.result "immediate"))
    ;; Even when an immediate callback completes the run during evaluation,
    ;; the deferred initial return is still recorded.
    (assert (= run.initial-result "returned"))))))

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

(fn flaky-runner [f fail-count]
  ;; A runner over a store wrapper whose first `fail-count` terminal
  ;; (status-bearing) updates throw; non-terminal updates pass through.
  (var terminal-failures 0)
  (local flaky {:create-run (fn [_self fields] (f.store:create-run fields))
                :get-run (fn [_self id] (f.store:get-run id))
                :list-runs (fn [_self] (f.store:list-runs))
                :update-run (fn [_self id fields]
                  (when (and fields.status (< terminal-failures fail-count))
                    (set terminal-failures (+ terminal-failures 1))
                    (error "storage unavailable"))
                  (f.store:update-run id fields))})
  (local globals {})
  (each [key value (pairs _G)] (tset globals key value))
  (tset globals :capture f.capture)
  (Runner {:store flaky :code-store f.codes :kernels f.kernels
           :clock (fn [] f.time.now) :wall-clock (fn [] f.time.now)
           :pump? false :owner {:session "flaky"}
           :owner-alive? (fn [_owner] true) :globals globals}))

(fn expect-deadline-supervision [f runner]
  ;; Synchronous completion: the initial evaluation commits the record.
  (local code (f.create "(+ 5 3)"))
  (local (ok err) (pcall runner.run runner code.id))
  ;; The persistence failure is surfaced explicitly...
  (assert (not ok) "expected the terminal persistence failure to surface")
  (assert (has? (tostring err) "storage unavailable"))
  ;; ...and the record is still supervised, not orphaned.
  (local record (. (f.store:list-runs) 1))
  (assert (= record.status "running"))
  (set f.time.now 901000)
  (runner:tick)
  (local final (f.store:get-run record.id))
  (assert (= final.status "timed-out"))
  (assert (has? final.error.message "deadline exceeded")))

(fn expect-timeout-retry [f runner]
  (local code (f.create "(local done (execution:defer)) (set capture.cb (execution:wrap (fn [] (done:succeed :late))))"))
  (local run (runner:run code.id {:timeout-ms 20}))
  (assert (= run.status "running"))
  (set f.time.now 31)
  ;; The first deadline interrupt hits the storage failure; the error is
  ;; explicit and the run stays supervised.
  (local (ok err) (pcall runner.tick runner))
  (assert (not ok) "expected the failed timeout commit to surface")
  (assert (has? (tostring err) "storage unavailable"))
  (assert (= (. (f.store:get-run run.id) :status) "running"))
  ;; The next tick re-drives the staged outcome to a terminal record.
  (runner:tick)
  (local final (f.store:get-run run.id))
  (assert (= final.status "timed-out"))
  (f.capture.cb)
  (assert (= (. (f.store:get-run run.id) :status) "timed-out")))

(add "a failed terminal persistence keeps the deadline supervising the run"
  (fn [] (with-fixture (fn [f]
    (expect-deadline-supervision f (flaky-runner f 1))))))

(add "a failed timeout commit retries on the next deadline tick"
  (fn [] (with-fixture (fn [f]
    (expect-timeout-retry f (flaky-runner f 1))))))

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

(add "terminal runs delete from the store and running runs refuse"
  (fn [] (with-fixture (fn [f]
    (local done-run (run-source f "42"))
    (f.store:delete-run! done-run.id)
    (assert (not (f.store:get-run done-run.id)) "deleted run must be absent")
    (assert (= (length (f.store:list-runs)) 0))
    (local running (run-source f "(execution:defer)"))
    (local (ok err) (pcall f.store.delete-run! f.store running.id))
    (assert (not ok))
    (assert (has? (tostring err) "cannot delete a running code run"))
    (assert (f.store:get-run running.id))
    (f.runner:drop)
    (set f.runner-dropped? true)))))

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

(add "opencode session attachment records a validated graph artifact"
  (fn [] (with-fixture (fn [f]
    (local run (run-source f "(local done (execution:defer)) (set capture.cb (execution:wrap (fn [] (execution:attach-opencode-session \"ses_demo-1\" \"Books import\") (done:succeed :ok)))) :started"))
    (f.capture.cb)
    (local final (f.store:get-run run.id))
    (assert (= final.status "succeeded"))
    (local artifact (. final.artifacts 1))
    (assert (= artifact.key "opencode-session:ses_demo-1"))
    (assert (= artifact.label "Books import"))))))

(add "opencode session attachment uses the default label and rejects unsafe ids"
  (fn [] (with-fixture (fn [f]
    (local run (run-source f "(execution:attach-opencode-session \"ses_abc-123\") 42"))
    (local artifact (. (f.store:get-run run.id) :artifacts 1))
    (assert (= artifact.key "opencode-session:ses_abc-123"))
    (assert (= artifact.label "OpenCode session"))
    (local rejected (run-source f "(execution:attach-opencode-session \"../etc\") 1"))
    (assert (= rejected.status "failed"))
    (assert (has? rejected.error.message "url-safe"))))))

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

(add "delete action removes terminal run nodes from every open map"
  (fn [] (with-fixture (fn [f]
    (fn exercise [map-a map-b _graph]
      (local code (f.create "42"))
      (local source (assert (map-a:load-by-key (.. "code-entity:" code.id))))
      (local run (source:run-entity))
      (local node-a (assert (map-a:lookup (.. "code-run:" run.id))))
      (assert (map-b:load-by-key (.. "code-run:" run.id)))
      (assert (= (map-a:node-count) 2))
      (assert (= (map-b:node-count) 1))
      (var delete-action nil)
      (each [_ action (ipairs (node-a.actions node-a))]
        (when (= action.name "Delete Run") (set delete-action action)))
      (assert delete-action "terminal run must expose Delete Run")
      (delete-action.fn {} {})
      (assert (= (map-a:node-count) 1))
      (assert (= (map-b:node-count) 0))
      (assert (not (f.store:get-run run.id)) "deleted run must be absent"))
    (with-run-maps f exercise)))))

(add "running runs hide Delete Run until terminal"
  (fn [] (with-fixture (fn [f]
    (fn exercise [map-a _map-b _graph]
      (local code (f.create "(execution:defer)"))
      (local source (assert (map-a:load-by-key (.. "code-entity:" code.id))))
      (local run (source:run-entity))
      (local node (assert (map-a:lookup (.. "code-run:" run.id))))
      (assert (= (length (node.actions node)) 0))
      (f.runner:drop)
      (set f.runner-dropped? true)
      (assert (= (. (f.store:get-run run.id) :status) "interrupted"))
      (assert (= (length (node.actions node)) 1))
      (assert (= (. (node.actions node) 1 :name) "Delete Run")))
    (with-run-maps f exercise)))))

(add "preview output tail is bounded aligned and carries the error head"
  (fn []
    (local Presentation (require :code-runs/presentation))
    (assert (= (Presentation.output-tail {:output ""}) "(no output yet)"))
    (assert (= (Presentation.output-tail {:output "one\ntwo\n"}) "two"))
    (local long (string.rep "x" 900))
    (local tail (Presentation.output-tail {:output (.. long "\nfinal\n")}))
    (assert (<= (# tail) 800) "tail must stay bounded")
    (assert (has? tail "final"))
    (local error-tail (Presentation.output-tail {:output "" :error {:message "boom" :traceback ""}}))
    (assert (= error-tail "Error: boom"))
    (local combined (Presentation.output-tail {:output "progress\n" :error {:message "boom" :traceback ""}}))
    (assert (has? combined "progress"))
    (assert (has? combined "Error: boom"))))

(add "payloads share content across preview and view without inline source"
  (fn []
    (local Presentation (require :code-runs/presentation))
    (local run {:id "run-1" :code-entity-id "code-1" :status "succeeded" :elapsed-ms 12.0
                :snapshot {:kernel 0 :language "fnl" :source "SECRET SOURCE" :name "x"}
                :completion-mode "synchronous"
                :output (.. (string.rep "x" 900) "\nfinal\n") :initial-result ""
                :result "7" :result-type "number" :error false :artifacts []})
    (local full (Presentation.payload run))
    (local compact (Presentation.preview-payload run))
    (local shared-suffix (.. "\n\nInitial return\n" run.initial-result
                             "\n\nResult (" run.result-type ")\n" run.result
                             "\n\nError\n(none)"))
    (each [_ text (ipairs [full compact])]
      (assert (has? text "Run: run-1"))
      (assert (has? text "Output"))
      (assert (has? text shared-suffix))
      (assert (not (has? text "SECRET SOURCE")) "payload must not inline source"))
    (assert (has? full (string.rep "x" 100)) "full payload keeps all output")
    (assert (not (has? compact (string.rep "x" 100))) "preview payload bounds the tail")
    (assert (has? compact "final"))))

(add "progress streams the tail while running and the outcome when terminal"
  (fn []
    (local Presentation (require :code-runs/presentation))
    (local base {:id "run-2" :code-entity-id "code-1" :elapsed-ms 5.0 :created-at 0
                 :snapshot {:kernel 0 :language "fnl" :source "" :name "job"}
                 :completion-mode "deferred" :initial-result "started"})
    (local running (setmetatable {:status "running" :output "alpha\nbeta\n"
                                  :result "" :result-type "nil" :error false}
                                 {:__index base}))
    (local running-text (Presentation.progress running))
    (assert (has? running-text "running"))
    (assert (has? running-text "beta"))
    (local failed (setmetatable {:status "failed" :output ""
                                 :result "" :result-type "nil"
                                 :error {:message "boom" :traceback ""}}
                                {:__index base}))
    (assert (has? (Presentation.progress failed) "Error: boom"))
    (local succeeded (setmetatable {:status "succeeded" :output "noise\n"
                                    :result "7" :result-type "number" :error false}
                                   {:__index base}))
    (assert (has? (Presentation.progress succeeded) "Result: 7"))
    (local quiet (setmetatable {:status "succeeded" :output ""
                                :result "" :result-type "nil" :error false}
                               {:__index base}))
    (assert (has? (Presentation.progress quiet) "(no output)"))))

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
