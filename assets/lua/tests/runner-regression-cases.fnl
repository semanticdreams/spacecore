(local runner (require :tests/runner))
(local clock (require :sysinfo))
(local Units (require :units))
(local HotReload (require :hot-reload))
(local Temp (require :tempfile))
(local tests [])

(fn restore-hook! [hook mask count]
  (if hook (debug.sethook hook mask count) (debug.sethook nil "" 0)))

;; CLI-only cases: Engine shutdown clears process-global runtime state. Never
;; invoke these functions in the fast suite's owning process.
(fn isolated [f]
  (local previous-now clock.now-ms)
  (local (hook mask count) (debug.gethook))
  (local (ok result) (pcall f))
  (restore-hook! hook mask count)
  (set clock.now-ms previous-now)
  (local (cleanup-ok cleanup-err)
    (pcall (fn []
             (when (and _G.app app.engine (not (app.engine:is-shutdown)))
               (app.engine:shutdown)))))
  (assert cleanup-ok (tostring cleanup-err))
  (assert ok (tostring result)))

(fn contains? [text fragment]
  (string.find (tostring text) fragment 1 true))

(fn burn []
  (var total 0)
  (for [i 1 20000] (set total (+ total i)))
  total)

(fn observe-shutdown! [engine shutdown-fails?]
  (local original-shutdown engine.shutdown)
  (var calls 0)
  (set engine.shutdown
    (fn [self]
      (assert (= self engine))
      (set calls (+ calls 1))
      (original-shutdown self)
      (when shutdown-fails? (error "runner regression shutdown failure"))))
  {:restore! (fn [] (set engine.shutdown original-shutdown))
   :verify! (fn []
              (assert (= calls 1) (.. "runner shutdown calls: expected 1, got " calls))
              (assert (engine:is-shutdown) "runner must shut down the actual engine"))})

(fn observed-suite [mode fail? shutdown-fails?]
  (var observer nil)
  (fn observe! []
    (set observer (observe-shutdown! app.engine shutdown-fails?)))
  (fn body []
    (observe!)
    (when (= fail? :case) (error "runner regression ordinary failure")))
  (fn teardown [] (error "runner regression teardown failure"))
  (local suite {:name "runner regression" :tests [{:name "runner inner case" :fn body}]})
  (when (= fail? :teardown)
    (set suite.teardown teardown))
  ;; Only an ephemeral loader, not a fake runner/engine. Restore it even if the
  ;; suite throws during require, before any case can run.
  (local previous-loaded package.loaded.tests-runner-regression)
  (local previous-loader package.preload.tests-runner-regression)
  (set package.loaded.tests-runner-regression nil)
  (set package.preload.tests-runner-regression
    (fn []
      (when (= fail? :load)
        (observe!)
        (error "runner regression module load failure"))
      suite))
  (set suite.modules [:tests-runner-regression])
  (local (old-hook old-mask old-count) (debug.gethook))
  (fn sentinel [] nil)
  (debug.sethook sentinel "" 7777)
  (local (ok err) (pcall (if (= mode :modules) runner.run-modules runner.run-tests) suite))
  (local (hook mask count) (debug.gethook))
  (restore-hook! old-hook old-mask old-count)
  (set package.loaded.tests-runner-regression previous-loaded)
  (set package.preload.tests-runner-regression previous-loader)
  (assert observer "inner suite must install the engine observer")
  (observer.restore!)
  (assert (and (= hook sentinel) (= mask "") (= count 7777)) "previous hook must survive suite completion")
  (observer.verify!)
  (if (or fail? shutdown-fails?)
      (assert (not ok) "failure must not become a passing suite")
      (assert ok (tostring err)))
  (when fail?
    (assert (contains? err (if (= fail? :load) "runner regression module load failure" "1 Lua test(s) failed"))
            (.. "original failure was lost: " (tostring err))))
  (when shutdown-fails?
    (assert (contains? err "runner regression shutdown failure") "shutdown failure must remain visible")))

(each [_ mode (ipairs [:tests :modules])]
  (each [_ variant (ipairs [{:label "success"}
                            {:label "ordinary failure" :fail? :case}
                            {:label "teardown failure" :fail? :teardown}
                            {:label "shutdown failure" :shutdown-fails? true}
                            {:label "both failures" :fail? :case :shutdown-fails? true}])]
    (fn run [] (observed-suite mode variant.fail? variant.shutdown-fails?))
    (fn check [] (isolated run))
    (table.insert tests
      {:name (.. "runner " mode " shuts down once on " variant.label)
       :fn check})))

(fn loader-failure []
  (fn run [] (observed-suite :modules :load true))
  (isolated run))

(table.insert tests
  {:name "runner modules shuts down once after a loader failure"
   :fn loader-failure})

(fn with-expired-clock [f]
  (var now 0)
  (var expired-reads 0)
  (set clock.now-ms (fn []
                      (when (> now 120000) (set expired-reads (+ expired-reads 1)))
                      now))
  (fn expire! [] (set now 120001))
  (local (old-hook old-mask old-count) (debug.gethook))
  (fn sentinel [] nil)
  (debug.sethook sentinel "" 7777)
  (local (ok err) (pcall f expire!))
  (local (hook mask count) (debug.gethook))
  (restore-hook! old-hook old-mask old-count)
  (assert ok (tostring err))
  (assert (and (= hook sentinel) (= mask "") (= count 7777)) "previous debug hook must be restored")
  (assert (= expired-reads 1) (.. "timeout must be delivered once, expired reads=" expired-reads)))

(fn timeout-suite [body]
  (local (ok err)
    (pcall runner.run-tests {:tests [{:name "runner inner timeout" :fn body}]}))
  (assert (not ok) "caught timeout must still fail the case")
  (assert (contains? err "1 Lua test(s) failed") (tostring err)))

(fn timeout-case [caught?]
  (fn check [expire!]
    (var continued? false)
    (fn body []
      (expire!)
      (if caught?
          (do
            (local (ok err) (pcall burn))
            (assert (not ok))
            (assert (contains? err "test timed out after 120s"))
            (burn)
            (set continued? true))
          (burn)))
    (timeout-suite body)
    (assert (= continued? caught?) "cleanup must run after caught delivery"))
  (fn run [] (with-expired-clock check))
  (isolated run))

(each [_ caught? (ipairs [false true])]
  (table.insert tests
    {:name (.. "runner restores prior hook after " (if caught? "caught" "uncaught") " timeout")
     :fn (fn [] (timeout-case caught?))}))

(fn rollback-after-timeout [rollback-fails? expire!]
  (local directory (Temp.TemporaryDirectory {:prefix "runner-deadline-"}))
  (var loads 0)
  (var cleanups 0)
  (var restores 0)
  (fn load [ctx]
    (set loads (+ loads 1))
    (when (= loads 2) (expire!))
    (when (> loads 1) (burn))
    (when (and rollback-fails? ctx (= ctx.reload-phase "rollback"))
      (error "deliberate rollback failure")))
  (fn unload [_ctx]
    (burn)
    (set cleanups (+ cleanups 1)))
  (fn snapshot [_ctx] {:saved true})
  (fn restore [state _ctx]
    (burn)
    (assert state.saved)
    (set restores (+ restores 1)))
  (local unit
    (Units.Unit
      {:id "runner-deadline" :owned-paths [directory.path]
       : load : unload : snapshot : restore}))
  (local controller
    (HotReload.HotReloadController
      {:unit unit :watch-paths [directory.path]
       :preserve-modules ["hot-reload" "units" "tests/runner" "tests.test-runner"]}))
  (local (ok err)
    (pcall (fn []
             (unit:load)
             (local (reload-ok reload-err) (pcall controller.reload-now! controller {:changes []}))
             (if rollback-fails?
                 (do
                   (assert (not reload-ok) "failed rollback must throw")
                   (assert (contains? reload-err "test timed out after 120s")))
                 (assert (and reload-ok (= reload-err false)) "restored rollback must return false, not success"))
             (assert (= loads 3) "rollback initialization must be attempted")
             (assert (= cleanups (if rollback-fails? 3 2)) "failed-load cleanup must complete")
             (assert (= restores (if rollback-fails? 0 1)) "rollback restore must complete")
             (when rollback-fails?
               (assert (contains? reload-err "deliberate rollback failure")))
             (burn))))
  (controller:drop)
  (directory:drop)
  (assert ok (tostring err)))

(fn rollback-case [rollback-fails?]
  (fn check [expire!]
    (var completed? false)
    (fn body []
      (rollback-after-timeout rollback-fails? expire!)
      (set completed? true))
    (timeout-suite body)
    (assert completed? "cleanup/rollback assertions must finish before latched failure"))
  (fn run [] (with-expired-clock check))
  (isolated run))

(each [_ rollback-fails? (ipairs [false true])]
  (table.insert tests
    {:name (.. "runner timeout permits Unit cleanup and " (if rollback-fails? "failed rollback cleanup" "HotReload rollback"))
     :fn (fn [] (rollback-case rollback-fails?))}))

(fn budget-case [options]
  (fn run []
    (var now 0)
    (var finished? false)
    (var observer nil)
    (set clock.now-ms (fn [] now))
    (local (old-hook old-mask old-count) (debug.gethook))
    (fn sentinel [] nil)
    (debug.sethook sentinel "" 7777)
    (fn body []
      (set observer (observe-shutdown! app.engine false))
      (set now options.before-ms)
      (burn)
      (set now options.after-ms)
      (local (ok err) (pcall burn))
      (if options.expires?
          (do
            (assert (not ok) "requested budget must expire")
            (assert (contains? err (.. "test timed out after " options.seconds "s"))))
          (assert ok (tostring err)))
      (burn)
      (set finished? true))
    (local test {:name "runner inner budget" :fn body})
    (when (not= options.override nil) (set test.timeout-seconds options.override))
    (local (ok err) (pcall runner.run-tests {:tests [test]}))
    (local (hook mask count) (debug.gethook))
    (restore-hook! old-hook old-mask old-count)
    (assert observer "budget case must run its body")
    (observer.restore!)
    (observer.verify!)
    (assert finished? "budget boundaries and post-delivery cleanup must finish")
    (assert (and (= hook sentinel) (= mask "") (= count 7777)) "budget case must restore the prior hook")
    (if options.expires?
        (do
          (assert (not ok) "caught override timeout must remain a failed case")
          (assert (contains? err "1 Lua test(s) failed")))
        (assert ok (tostring err))))
  (isolated run))

(each [_ options (ipairs [{:name "inherits default120" :before-ms 119000 :after-ms 120001 :seconds 120 :expires? true}
                          {:name "inherits configured global" :configured-timeout "10"
                           :before-ms 9000 :after-ms 10001 :seconds 10 :expires? true}
                          {:name "inherits disabled global when absent" :configured-timeout "0"
                           :before-ms 120001 :after-ms 240001 :expires? false}
                          {:name "overrides default with caught timeout" :override 240
                           :before-ms 120001 :after-ms 240001 :seconds 240 :expires? true}
                          {:name "overrides disabled global" :override 240 :configured-timeout "0"
                           :before-ms 120001 :after-ms 240001 :seconds 240 :expires? true}])]
  (fn check [] (budget-case options))
  (table.insert tests {:name (.. "runner per-test budget " options.name)
                       :configured-timeout options.configured-timeout :fn check}))

(local invalid-budgets [false "240" 0 -1 (/ 0 0) math.huge (- math.huge)])

(fn invalid-budget []
  (fn run []
    (var entered? false)
    (local variant (assert (tonumber (os.getenv "SPACE_RUNNER_REGRESSION_VARIANT")) "invalid budget variant required"))
    (fn body [] (set entered? true))
    (local (ok err)
      (pcall runner.run-tests {:tests [{:name "runner invalid budget" :fn body
                                        :timeout-seconds (. invalid-budgets variant)}]}))
    (assert (not ok) "invalid descriptor timeout must fail, not fall back")
    (assert (contains? err ":timeout-seconds must be a positive finite number") (tostring err))
    (assert (not entered?) "invalid budget must be rejected before running the body")
    (assert (app.engine:is-shutdown) "invalid descriptor must still shut down its owned engine"))
  (isolated run))

(table.insert tests {:name "runner per-test budget rejects invalid explicit values"
                     :variants (# invalid-budgets) :fn invalid-budget})

(local names (icollect [_ test (ipairs tests)] test.name))
(local configured-timeouts {})
(local variant-counts {})
(each [index test (ipairs tests)]
  (tset configured-timeouts index test.configured-timeout)
  (tset variant-counts index (if test.variants test.variants 1)))

(fn main []
  (local filter (os.getenv "TEST_FILTER"))
  (local timeout (os.getenv "SPACE_TEST_CASE_TIMEOUT_SECONDS"))
  (assert (or (= filter nil) (= filter "")) "regression child must be unfiltered")
  (assert (not (and _G.app app.engine)) "regression child must not create an outer Engine")
  (local index (assert (tonumber (os.getenv "SPACE_RUNNER_REGRESSION_CASE")) "regression case index required"))
  (local test (assert (. tests index) "unknown regression case index"))
  (local expected-timeout test.configured-timeout)
  (assert (if expected-timeout (= timeout expected-timeout) (or (= timeout nil) (= timeout "")))
          "regression child must use its explicit configured policy, not an inherited parent deadline")
  (local variant (assert (tonumber (os.getenv "SPACE_RUNNER_REGRESSION_VARIANT")) "regression variant required"))
  (assert (and (>= variant 1) (<= variant (. variant-counts index))) "unknown regression variant")
  (test.fn)
  (print (.. "RUNNER_REGRESSION_OK " index "/" variant " " test.name)))

{: names : configured-timeouts : variant-counts : main}
