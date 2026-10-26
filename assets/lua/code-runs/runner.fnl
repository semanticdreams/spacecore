(local sysinfo (require :sysinfo))
(local callbacks (require :callbacks))
(local Evaluator (require :fennel-evaluator))
(local {:Execution Execution} (require :code-runs/execution))
(local Owner (require :code-runs/owner))
(local R (require :reference-lifecycle/record-utils))

(fn prepare-run [context]
  ;; Builds the persistence closures and evaluation environment for one run.
  ;; Kept as a named top-level function so the per-run callbacks stay shallow.
  (local {:active active :clock clock :code-id code-id :entity entity
          :globals globals :kernels kernels :run run :started started
          :store store :timeout-ms timeout-ms :wall-clock wall-clock} context)
  (assert (and store run entity kernels) "prepare-run requires store run entity and kernels")
  (fn update [fields] (store:update-run run.id fields))
  (fn finish [outcome]
    (local held (assert (store:get-run run.id) "code run disappeared"))
    (when (>= (- (clock) started) timeout-ms)
      (set outcome.status "timed-out")
      (set outcome.error {:message "Code run deadline exceeded" :traceback ""}))
    (set outcome.finished-at (wall-clock))
    (set outcome.elapsed-ms (math.max 0 (- (clock) started)))
    (when (= held.status "running") (store:update-run run.id outcome))
    (tset active run.id nil))
  (fn write [text]
    (local current (assert (store:get-run run.id)))
    (assert (<= (+ (# current.output) (# text)) 1048576) "code-run output exceeds 1 MiB")
    (update {:output (.. current.output text)}))
  (fn artifact [ref]
    (local current (assert (store:get-run run.id)))
    (var present? false)
    (each [_ held (ipairs current.artifacts)] (when (= held.key ref.key) (set present? true)))
    (when (not present?) (table.insert current.artifacts ref) (update {:artifacts current.artifacts})))
  (local execution (Execution {:id run.id :code-entity-id code-id :update update
                               :finish finish :write write :artifact artifact}))
  (tset active run.id {:execution execution :started started :timeout-ms timeout-ms})
  (local environment {})
  (each [key value (pairs (or globals _G))] (tset environment key value))
  (tset environment :execution execution.context)
  (fn captured-print [...]
    (local arguments (table.pack ...))
    (local text [])
    (for [index 1 arguments.n] (table.insert text (tostring (. arguments index))))
    (write (.. (table.concat text "\t") "\n")))
  (tset environment :print captured-print)
  (local evaluate-options {:env environment :traceback? true})
  (var external-completion nil)
  (fn receive [result]
    (write result.output)
    (if (not (= result.error ""))
        (error result.error)
        (external-completion:succeed nil)))
  (fn submit []
    (kernels:run-code {:source entity.source :kernel entity.kernel :language entity.language
                       :callback-immediate? true}
      (execution.context:wrap receive)))
  ;; Internal evaluation must run inside the boundary, with its raw return preserved.
  (fn invoke []
    (local (kernel resolve-error) (kernels:resolve-kernel entity.kernel))
    (assert kernel resolve-error)
    (update {:resolved-kernel-id kernel.id :kernel-snapshot (R.clone kernel)})
    (if (= (tostring kernel.id) "0")
        (do
          (assert (or (= entity.language "fnl") (= entity.language "fennel")) "internal kernel requires Fennel")
          (local result (Evaluator.eval-source entity.source evaluate-options))
          (if result.ok result.result (error result.result)))
        (do (set external-completion (execution.context:defer)) (submit))))
  {:execution execution :invoke invoke})

(fn Runner [opts]
  (local options (assert opts))
  (local store (assert options.store "code runner requires store"))
  (local codes (assert options.code-store "code runner requires code-store"))
  (local kernels (assert options.kernels "code runner requires kernels"))
  (local clock (or options.clock sysinfo.now-ms))
  (local wall-clock (or options.wall-clock (fn [] (* 1000 (os.time)))))
  (local owner (or options.owner (Owner.current)))
  (local owner-alive? (or options.owner-alive? Owner.alive?))
  (local active {})
  (var dropped? false)
  (var callback-id nil)
  (var pump-queued? false)
  (fn assert-live [] (assert (not dropped?) "code runner called after drop"))
  (fn tick [_self]
    (assert-live)
    (local expired [])
    (each [id state (pairs active)]
      (when (>= (- (clock) state.started) state.timeout-ms) (table.insert expired id)))
    ;; One record's persistence failure must not starve the others: process
    ;; every expired deadline, then surface the first error.
    (var tick-error nil)
    (each [_ id (ipairs expired)]
      (local execution (. active id :execution))
      (local (ok err) (pcall execution.interrupt execution
                        "timed-out" "Code run deadline exceeded"))
      (when (and (not ok) (not tick-error)) (set tick-error err)))
    (when tick-error (error tick-error 0)))
  (fn queue-pump []
    (when (and callback-id (not pump-queued?) (next active) (not dropped?))
      (set pump-queued? true)
      (callbacks.enqueue callback-id nil)))
  (fn begin [self code-id opts]
    (assert-live)
    (local settings (or opts {}))
    (local entity (R.clone (assert (codes:get-entity code-id) "missing code entity")))
    ;; Default generous: LLM-backed entities can run many minutes. Short
    ;; synchronous code is unaffected; the deadline only bounds still-running runs.
    (local timeout-ms (if (= settings.timeout-ms nil) 900000 settings.timeout-ms))
    (assert (and (= (type timeout-ms) :number) (> timeout-ms 0) (< timeout-ms math.huge)) "invalid code-run timeout-ms")
    (local started (clock))
    (local now (wall-clock))
    (local run (store:create-run
      {:code-entity-id code-id :snapshot {:source entity.source :name entity.name
        :language entity.language :kernel entity.kernel}
       :status "running" :owner owner :created-at now :started-at now :finished-at false
       :started-monotonic-ms started :elapsed-ms 0 :timeout-ms timeout-ms :completion-mode "synchronous"
       :output "" :result "" :result-type "nil" :initial-result "" :error false :artifacts []}))
    (local prepared (prepare-run {:active active :clock clock :code-id code-id
                                  :entity entity :globals options.globals
                                  :kernels kernels :run run :started started
                                  :store store :timeout-ms timeout-ms
                                  :wall-clock wall-clock}))
    ;; Supervision must survive evaluation or persistence failures: the pump
    ;; stays queued even when the initial evaluation threw, and the original
    ;; error is still surfaced to the caller.
    (local (evaluate-ok evaluate-err)
      (pcall prepared.execution.evaluate prepared.execution prepared.invoke))
    (queue-pump)
    (when (not evaluate-ok) (error evaluate-err 0))
    (assert (store:get-run run.id)))
  (fn drop [_self]
    (assert-live)
    (local states [])
    (each [_ state (pairs active)] (table.insert states state))
    (each [_ state (ipairs states)] (state.execution:interrupt "interrupted" "Application runtime stopped or reloaded"))
    (set dropped? true)
    (when callback-id (callbacks.unregister callback-id) (set callback-id nil)))
  (local self {:store store :code-store codes :run begin :tick tick :drop drop})
  ;; Cold recovery is permitted only when the specific persisted owner is proven dead.
  (each [_ run (ipairs (store:list-runs))]
    (when (and (= run.status "running") (= (owner-alive? run.owner) false))
      (store:update-run run.id {:status "interrupted" :finished-at (wall-clock)
        :error {:message "Execution owner exited before completion" :traceback ""}})))
  (when (not (= options.pump? false))
    (fn pump [_payload]
      (set pump-queued? false)
      (when (not dropped?)
        ;; A persistence failure inside tick must not drop supervision: requeue
        ;; unconditionally, then re-raise so the error stays explicitly visible.
        (local (tick-ok tick-err) (pcall tick self))
        (queue-pump)
        (when (not tick-ok) (error tick-err 0))))
    (set callback-id (callbacks.register pump)))
  self)

{:Runner Runner}
