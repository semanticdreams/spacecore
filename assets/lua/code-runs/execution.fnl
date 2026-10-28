(local fennel (require :fennel))
(local Evaluator (require :fennel-evaluator))

(fn describe [value]
  (if (= (type value) :string) value
      (do (local (ok result) (pcall fennel.view value))
          (if ok result (Evaluator.format-result value)))))

(fn error-data [err]
  {:message (Evaluator.format-error err) :traceback (debug.traceback "" 2)})

;; A private execution boundary stages completion until the whole callback/evaluation
;; unwinds. A subsequent exception therefore wins over an early success signal.
(fn Execution [opts]
  (local options (assert opts))
  (var deferred? false)
  (var terminal? false)
  (var committing? false)
  (var pending nil)
  (var depth 0)
  (fn live! [] (assert (and (not terminal?) (not committing?)) "code run is already terminal or committing"))
  (fn flush [force?]
    (when (and pending (or force? (= depth 0)) (not terminal?) (not committing?))
      (local outcome pending)
      (set committing? true)
      (local (ok err) (pcall options.finish outcome))
      (set committing? false)
      (when (not ok) (error err))
      (set terminal? true)
      (set pending nil)))
  (fn settle [status value]
    (live!)
    (assert (not pending) "code run completion already signalled")
    (set pending (if (= status "succeeded")
                    {:status status :result (describe value) :result-type (type value) :error false}
                    {:status status :error (error-data value)}))
    (flush))
  (fn succeed [_self value] (settle "succeeded" value))
  (fn fail [_self err] (settle "failed" err))
  (local completion {:succeed succeed :fail fail})
  (fn defer [_self]
    (live!)
    (assert (not deferred?) "execution:defer may only be called once")
    (assert (> depth 0) "defer must be called during initial evaluation")
    (set deferred? true)
    (options.update {:completion-mode "deferred"})
    completion)
  (fn boundary [f ...]
    (live!)
    (set depth (+ depth 1))
    (local result (table.pack (xpcall f error-data ...)))
    (set depth (- depth 1))
    (when (not (. result 1))
      (set pending {:status "failed" :error (. result 2)}))
    (flush)
    result)
  (fn wrap [_self callback]
    (live!)
    (assert (= (type callback) :function) "execution:wrap requires a function")
    (fn wrapped [...]
      ;; External late callbacks are non-mutating after timeout, drop, or completion.
      (when (and (not terminal?) (not committing?))
        (local result (boundary callback ...))
        (when (. result 1) (table.unpack result 2 result.n)))))
  (fn write [_self text]
    (live!)
    (assert (= (type text) :string) "execution:write requires text")
    (options.write text))
  (fn attach-artifact [_self key label]
    (live!)
    (assert (and (= (type key) :string) (string.find key "%S")) "artifact requires a graph key")
    (assert (or (= label nil) (= (type label) :string)) "artifact label must be text")
    (options.artifact {:key key :label (if label label key)}))
  (fn attach-opencode-session [_self id label]
    ;; Records the run's OpenCode session as a graph-addressable artifact
    ;; reference. The session itself stays owned by the OpenCode server.
    (live!)
    (assert (and (= (type id) :string) (string.match id "^[%w%-_]+$"))
            "opencode session id must be a non-empty url-safe identifier")
    (attach-artifact _self (.. "opencode-session:" id) (or label "OpenCode session")))
  (local context {:id options.id :code-entity-id options.code-entity-id
                  :defer defer :wrap wrap :write write :attach-artifact attach-artifact
                  :attach-opencode-session attach-opencode-session})
  (fn evaluate [_self callback]
    ;; The initial evaluation shares the boundary discipline but keeps the
    ;; stack alive until its return is recorded, so a deferred run's
    ;; initial result persists before any immediate callback's staged
    ;; outcome commits.
    (live!)
    (set depth (+ depth 1))
    (local result (table.pack (xpcall callback error-data)))
    (set depth (- depth 1))
    (when (not (. result 1))
      (set pending {:status "failed" :error (. result 2)}))
    (when (and (. result 1) deferred?)
      (options.update {:initial-result (describe (. result 2))}))
    (flush)
    (when (and (. result 1) (not deferred?) (not terminal?) (not pending))
      (settle "succeeded" (. result 2)))
    result)
  (fn interrupt [_self status reason]
    (when (and (not terminal?) (not committing?))
      ;; A repeat interrupt (deadline retry after a persistence failure) must
      ;; re-drive the already-staged outcome instead of asserting on it; the
      ;; completion's own deadline override still decides the final status.
      (when (not pending)
        (set pending {:status status :error {:message reason :traceback ""}}))
      ;; Teardown/deadline is terminal even if an external callback still holds us.
      (flush true)))
  {:context context :evaluate evaluate :interrupt interrupt :terminal? (fn [_self] terminal?)})

{:Execution Execution :describe describe}
