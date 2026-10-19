;; Helper ownership only. Real Scene/Sandbox caller-state isolation is Task1B.
(local Scenarios (require :constraints.scenarios))
(local Runner (require :tests/runner))
(local tests [])

(fn traceback [err] (debug.traceback (tostring err) 2))

(fn raise-outcome! [ok result cleanup-errors]
  (local messages [])
  (when (not ok) (table.insert messages (tostring result)))
  (each [_ message (ipairs cleanup-errors)] (table.insert messages message))
  (if (> (# messages) 0) (error (table.concat messages "\n") 0) result))

(fn attempt-safety! [errors stage f ...]
  (local (ok err) (pcall f ...))
  (when (not ok) (table.insert errors (.. stage " also failed: " (tostring err)))))

(fn finish-probe [ok result finish]
  (local errors [])
  (attempt-safety! errors "native caller probe" finish)
  (when (> (# errors) 0) (raise-outcome! ok result errors)))

(fn with-patches [patches f]
  (local saved [])
  (each [_ patch (ipairs patches)]
    (table.insert saved {:object patch.object :key patch.key
                         :value (rawget patch.object patch.key)})
    (rawset patch.object patch.key patch.value))
  (local (ok result) (xpcall f traceback))
  (for [i (# saved) 1 -1]
    (local patch (. saved i))
    (rawset patch.object patch.key patch.value))
  (if ok result (error result 0)))

(fn copy-slots [object]
  (local slots {})
  (each [key value (pairs object)] (tset slots key value))
  slots)

(fn assert-slots [object slots label]
  (each [key value (pairs slots)]
    (assert (= (rawget object key) value) (.. label " changed existing slot " (tostring key))))
  (each [key value (pairs object)]
    (assert (= (rawget slots key) value) (.. label " retained new slot " (tostring key)))))

(fn restore-slots! [target snapshot]
  (local keys [])
  (each [key _ (pairs target)] (table.insert keys key))
  (each [_ key (ipairs keys)] (rawset target key nil))
  (each [key value (pairs snapshot)] (rawset target key value)))

(fn native-probe []
  (local callbacks (require :callbacks))
  (local owner app)
  (local engine owner.engine)
  (local preload package.preload.jobs)
  (local loaded package.loaded.jobs)
  (local main package.loaded.main)
  (local reset _G.reset-engine-events)
  (local state {})
  (fn receive [value] (set state.callback value))
  (fn receive-job [value] (set state.job value))
  (fn receive-next [value] (set state.next value))
  (local id (callbacks.register receive))
  (callbacks.enqueue id :pending-caller-callback)
  (engine.jobs.submit {:kind :echo :payload :pending-caller-job :callback receive-job})
  (fn delivered? [] (and state.callback state.job))
  (fn next-delivered? [] state.next)
  (fn finish []
    (local (ok err)
      (pcall callbacks.run-loop {:poll-jobs true :poll-http false :sleep-ms 0
                                :timeout-ms 2000 :until delivered?}))
    (callbacks.unregister id)
    (assert ok (tostring err))
    (assert (= state.callback :pending-caller-callback) "pending caller callback must survive unwind")
    (assert (and state.job state.job.ok (= state.job.result :pending-caller-job))
            "pending caller job must be delivered after unwind")
    (engine.jobs.submit {:kind :echo :payload :subsequent-caller-job :callback receive-next})
    (callbacks.run-loop {:poll-jobs true :poll-http false :sleep-ms 0
                         :timeout-ms 2000 :until next-delivered?})
    (assert (and state.next state.next.ok (= state.next.result :subsequent-caller-job))
            "subsequent caller jobs must remain usable")
    (assert (= app owner) "restore exact caller app")
    (assert (= app.engine engine) "preserve exact caller Engine")
    (assert (= package.preload.jobs preload) "preserve jobs preload identity")
    (assert (= package.loaded.jobs loaded) "preserve cached jobs identity and membership")
    (assert (= (preload) engine.jobs) "preload must still resolve to owner jobs")
    (assert (= package.loaded.main main) "preserve cached main identity")
    (assert (= _G.reset-engine-events reset) "preserve reset-engine-events identity")
    (assert (and (engine:is-started) (not (engine:is-shutdown))) "caller must stay started, not shutdown"))
  finish)

(fn lifecycle-guard [f]
  (local engine-module (require :engine))
  (local calls [])
  (fn forbidden [name]
    (fn reject-lifecycle [] (table.insert calls name) (error (.. "borrow attempted " name))))
  (local patches [{:object Runner :key :setup-test-env :value (forbidden :setup)}
                 {:object Runner :key :shutdown-test-env :value (forbidden :teardown)}
                 {:object engine-module :key :Engine :value (forbidden :construct)}
                 {:object app.engine :key :start :value (forbidden :start)}
                 {:object app.engine :key :shutdown :value (forbidden :shutdown)}
                 {:object app :key :drop :value (forbidden :drop)}])
  (local (ok result) (pcall with-patches patches f))
  (assert (= (# calls) 0) (.. "borrow must perform zero lifecycle calls: " (table.concat calls ",")))
  (if ok result (error result 0)))

(fn invoke-borrow [f failure]
  (local finish (native-probe))
  (local (ok result) (pcall Scenarios.with-test-app f))
  ;; Check native delivery after every unwind, including each nested invocation.
  (finish-probe ok result finish)
  (if failure
      (do
        (assert (not ok) "body failure must propagate")
        (assert (string.find (tostring result) "scenario failed: " 1 true) "retain scenario error prefix")
        (assert (string.find (tostring result) failure 1 true) "retain primary failure")
        (assert (string.find (tostring result) "stack traceback:" 1 true) "retain body traceback"))
      (assert ok (tostring result)))
  result)

(fn borrowed-success []
  (fn check []
    (local owner app)
    (fn body [] (assert (= app owner)) (values false :ignored))
    (assert (= (invoke-borrow body nil) false)))
  (lifecycle-guard check))

(fn borrowed-failure []
  (fn check []
    (fn body [] (global app {:replacement true}) (error "borrowed body fault"))
    (invoke-borrow body "borrowed body fault"))
  (lifecycle-guard check))

(fn borrowed-nested [failure]
  (fn check []
    (fn inner []
      (when failure (global app {:inner-replacement true}) (error "inner body fault"))
      (values :inner-result :ignored))
    (fn outer []
      (local value (invoke-borrow inner (when failure "inner body fault")))
      (when (not failure) (assert (= value :inner-result)))
      (when failure (global app {:outer-replacement true}) (error "outer body fault"))
      (values :outer-result :ignored))
    (local value (invoke-borrow outer (when failure "outer body fault")))
    (when (not failure) (assert (= value :outer-result))))
  (lifecycle-guard check))

(fn first-nil-result []
  (fn check []
    (local finish (native-probe))
    (fn body [] (values nil :ignored))
    (fn count-results [] (select "#" (Scenarios.with-test-app body)))
    (local (ok count) (pcall count-results))
    (finish-probe ok count finish)
    (assert ok (tostring count))
    (assert (= count 1) "with-test-app returns exactly its first result, even nil"))
  (lifecycle-guard check))

(fn nested-success [] (borrowed-nested false))
(fn nested-failure [] (borrowed-nested true))

(table.insert tests {:name "scenario helper borrows native caller without lifecycle operations" :fn borrowed-success})
(table.insert tests {:name "scenario helper restores native caller after body failure" :fn borrowed-failure})
(table.insert tests {:name "scenario helper preserves native caller after each nested success" :fn nested-success})
(table.insert tests {:name "scenario helper preserves native caller after each nested failure" :fn nested-failure})
(table.insert tests {:name "scenario helper returns exactly first nil result" :fn first-nil-result})

(fn invalid-caller [change]
  (local parent app)
  (local candidate (copy-slots parent))
  (set candidate.engine (copy-slots parent.engine))
  (local finish (native-probe))
  (local patches [])
  (change candidate patches)
  (table.insert patches {:object _G :key :app :value candidate})
  (var called false)
  (fn body [] (set called true))
  (fn reject []
    (local (ok err) (pcall Scenarios.with-test-app body))
    (assert (not ok) "invalid nonnil caller must be rejected")
    (assert (string.find (tostring err) "scenario caller" 1 true) "identify invalid caller")
    (assert (not called) "reject before body")
    (assert (= _G.app candidate) "retain invalid caller reference"))
  (fn guarded [] (with-patches patches reject))
  (local (ok err) (pcall lifecycle-guard guarded))
  (finish-probe ok err finish)
  (assert ok (tostring err)))

(fn not-started [_] false)
(fn already-shutdown [_] true)
(fn wrong-jobs-owner [] {})
(fn invalidate-testing [a _] (set a.testing false))
(fn invalidate-engine [a _] (set a.engine nil))
(fn invalidate-started [a _] (set a.engine.is-started not-started))
(fn invalidate-shutdown [a _] (set a.engine.is-shutdown already-shutdown))
(fn invalidate-physics [a _] (set a.engine.physics nil))
(fn invalidate-jobs [a _] (set a.engine.jobs {}))
(fn invalidate-intersectables [a _] (set a.intersectables {}))
(fn invalidate-clickables [candidate _]
  (assert (= (type candidate.clickables) :table) "negative fixture starts with caller clickables")
  (assert (= (type candidate.clickables.register) :function) "caller clickables must be initialized")
  (set candidate.clickables nil))
(fn invalidate-hoverables [candidate _]
  (assert (= (type candidate.hoverables) :table) "negative fixture starts with caller hoverables")
  (assert (= (type candidate.hoverables.register) :function) "caller hoverables must be initialized")
  (set candidate.hoverables {}))
(fn invalidate-themes [a _] (set a.themes {}))
(fn invalidate-lights [a _] (set a.lights {}))
(fn invalidate-main [_ p] (table.insert p {:object package.loaded :key :main :value nil}))
(fn invalidate-preload [_ p] (table.insert p {:object package.preload :key :jobs :value nil}))
(fn invalidate-preload-owner [_ p] (table.insert p {:object package.preload :key :jobs :value wrong-jobs-owner}))
(fn invalidate-cached-jobs [_ p] (table.insert p {:object package.loaded :key :jobs :value {}}))

(local invalid-cases
  [{:name :testing :change invalidate-testing}
   {:name :engine :change invalidate-engine}
   {:name :unstarted :change invalidate-started}
   {:name :shutdown :change invalidate-shutdown}
   {:name :physics :change invalidate-physics}
   {:name :jobs :change invalidate-jobs}
   {:name :intersectables :change invalidate-intersectables}
   {:name :clickables :change invalidate-clickables}
   {:name :hoverables :change invalidate-hoverables}
   {:name :themes :change invalidate-themes}
   {:name :lights :change invalidate-lights}
   {:name :main :change invalidate-main}
   {:name :preload-missing :change invalidate-preload}
   {:name :preload-owner :change invalidate-preload-owner}
   {:name :cached-jobs :change invalidate-cached-jobs}])

(each [_ invalid (ipairs invalid-cases)]
  (fn reject-invalid [] (invalid-caller invalid.change))
  (table.insert tests {:name (.. "scenario helper rejects invalid caller " invalid.name)
                       :fn reject-invalid}))

(fn reject-scalar [value]
  (local finish (native-probe))
  (fn reject []
    (fn body [] (error "must not call invalid caller body"))
    (local (ok err) (pcall Scenarios.with-test-app body))
    (assert (not ok))
    (assert (string.find (tostring err) "scenario caller" 1 true)))
  (fn check [] (with-patches [{:object _G :key :app : value}] reject))
  (local (ok err) (pcall lifecycle-guard check))
  (finish-probe ok err finish)
  (assert ok (tostring err)))

(each [_ value (ipairs [false 12 :not-a-test-app])]
  (fn reject-non-table [] (reject-scalar value))
  (table.insert tests {:name (.. "scenario helper rejects non-table caller " (tostring value))
                       :fn reject-non-table}))

(fn uncached-jobs []
  (fn check []
    (fn body [] (values :uncached :ignored))
    (assert (= (invoke-borrow body nil) :uncached))
    (assert (= package.loaded.jobs nil) "eligibility must not populate cached jobs"))
  (fn guarded [] (with-patches [{:object package.loaded :key :jobs :value nil}] check))
  (lifecycle-guard guarded))

(table.insert tests {:name "scenario helper accepts owner jobs with uncached module" :fn uncached-jobs})

(fn pristine-bootstrap? [candidate]
  (and (= (type candidate) :table)
       (= (getmetatable candidate) nil)
       (= (next candidate) nil)
       (= (rawget candidate :engine) nil)
       (= (rawget package.loaded :main) nil)
       (= (rawget package.preload :jobs) nil)
       (= (rawget package.loaded :jobs) nil)))

(fn make-fake-namespace [prior-package prior-loaded prior-preload pristine?]
  (local namespace (copy-slots prior-package))
  (local loaded (copy-slots prior-loaded))
  (local preload (copy-slots prior-preload))
  (set namespace.loaded loaded)
  (set namespace.preload preload)
  (tset loaded :scenario-owned-false false)
  (tset preload :scenario-owned-false false)
  (tset loaded :scenario-owned-added nil)
  (tset preload :scenario-owned-added nil)
  (when pristine?
    (tset loaded :main nil)
    (tset loaded :jobs nil)
    (tset preload :jobs nil))
  (local caller (when pristine? {}))
  {: namespace : loaded : preload
   : caller :caller-slots (when pristine? (copy-slots caller))
   :namespace-slots (copy-slots namespace)
   :loaded-slots (copy-slots loaded) :preload-slots (copy-slots preload)
   :reset (rawget _G :reset-engine-events)
   :originals {:namespace prior-package :loaded prior-loaded :preload prior-preload
               :namespace-slots (copy-slots prior-package)
               :loaded-slots (copy-slots prior-loaded) :preload-slots (copy-slots prior-preload)}})

(fn with-fake-namespace [state f]
  (local prior-package _G.package)
  (local prior-loaded package.loaded)
  (local prior-preload package.preload)
  (local prior-app (rawget _G :app))
  (local prior-reset (rawget _G :reset-engine-events))
  (local loaded-slots (copy-slots prior-loaded))
  (local preload-slots (copy-slots prior-preload))
  (local fixture (make-fake-namespace prior-package prior-loaded prior-preload state.options.pristine))
  (local (ok result)
    (pcall
      (fn []
        (global package fixture.namespace)
        (set package.loaded fixture.loaded)
        (set package.preload fixture.preload)
        (global app fixture.caller)
        (f state fixture))))
  (local cleanup-errors [])
  (attempt-safety! cleanup-errors "original loaded slots" restore-slots! prior-loaded loaded-slots)
  (attempt-safety! cleanup-errors "original preload slots" restore-slots! prior-preload preload-slots)
  ;; Retained plain namespace tables; no faults are injected into these writes.
  (global package prior-package)
  (set package.loaded prior-loaded)
  (set package.preload prior-preload)
  (rawset _G :reset-engine-events prior-reset)
  (rawset _G :app prior-app)
  (raise-outcome! ok result cleanup-errors))

(fn make-owned-state [options]
  (local calls {:setup 0 :body 0 :teardown 0 :drop 0 :finalizer 0 :shutdown 0})
  (local messages [])
  (fn is-started [_] (not (= options.setup :unstarted)))
  (fn is-shutdown [_] (= options.already-shutdown true))
  (fn shutdown [_]
    (set calls.shutdown (+ calls.shutdown 1))
    (global app {:shutdown-replacement true})
    (when options.shutdown (error "owned shutdown fault")))
  (local owner-engine {: is-started : is-shutdown : shutdown})
  (fn drop []
    (set calls.drop (+ calls.drop 1))
    (assert (= app.drop drop) "teardown uses captured app, not body replacement")
    (global app nil)
    (when options.drop (error "owned drop fault")))
  (local owner {:engine owner-engine :drop drop})
  (local jobs {})
  (fn reset [] :owned-reset)
  (fn loader [] :owned)
  (fn jobs-loader [] jobs)
  ;; Capture dependencies before installing detached metadata tables. Replacing
  ;; global package does NOT redirect require's native registry cache.
  {: options : calls : messages : owner :engine owner-engine
   :reset reset :loader loader :jobs jobs :jobs-loader jobs-loader :added {} :main {}
   :replacement-engine {} :body-replacement {:body-replacement true}
   :engine-module (require :engine)
   :actual-teardown Runner.shutdown-test-env :actual-finalizer Runner.with-owned-engine})

(fn make-fake-setup [state fixture]
  (fn setup [_]
    (assert (= package fixture.namespace) "fixture namespace must actually be installed")
    (assert (= package.loaded fixture.loaded) "helper must observe detached loaded table")
    (assert (= package.preload fixture.preload) "helper must observe detached preload table")
    (set state.calls.setup (+ state.calls.setup 1))
    (global reset-engine-events state.reset)
    (tset fixture.preload :scenario-owned-added state.loader)
    (tset fixture.loaded :scenario-owned-added state.added)
    (tset fixture.preload :scenario-owned-false state.loader)
    (tset fixture.loaded :scenario-owned-false true)
    (tset fixture.preload :jobs state.jobs-loader)
    (tset fixture.loaded :jobs state.jobs)
    (tset fixture.loaded :main state.main)
    (when (= state.options.setup :before-allocation) (error "owned setup fault"))
    (global app state.owner)
    (when state.options.setup (error "owned setup fault")))
  setup)

(fn make-fake-body [state fixture]
  (fn body []
    (set state.calls.body (+ state.calls.body 1))
    (assert (= app state.owner))
    (when state.options.replace-engine (set state.owner.engine state.replacement-engine))
    (global app state.body-replacement)
    (when state.options.replace-modules
      (set fixture.namespace.preload {})
      (set fixture.namespace.loaded {}))
    (when state.options.body (error "owned body fault"))
    (values state.options.result :ignored))
  body)

(fn make-owned-patches [state fixture]
  (local calls state.calls)
  (fn delegate-teardown []
    (set calls.teardown (+ calls.teardown 1))
    (assert (= app state.owner) "restore captured owner before runner teardown")
    (state.actual-teardown))
  (fn finalize [captured body trace]
    (set calls.finalizer (+ calls.finalizer 1))
    (assert (= captured state.engine) "finalize exact setup owner")
    (state.actual-finalizer captured body trace))
  (fn forbidden [] (error "fake ownership tests must never construct a native Engine"))
  (fn capture-print [message] (table.insert state.messages message))
  [{:object Runner :key :setup-test-env :value (make-fake-setup state fixture)}
   {:object Runner :key :shutdown-test-env :value delegate-teardown}
   {:object Runner :key :with-owned-engine :value finalize}
   {:object state.engine-module :key :Engine :value forbidden}
   {:object _G :key :print :value capture-print}])

(fn assert-original-namespace [fixture]
  (local originals fixture.originals)
  (assert-slots originals.namespace originals.namespace-slots "untouched original namespace")
  (assert-slots originals.loaded originals.loaded-slots "untouched original loaded")
  (assert-slots originals.preload originals.preload-slots "untouched original preload"))

(fn assert-owned-restoration [fixture]
  ;; These observations MUST precede the fixture owner's independent safety.
  (assert (= _G.app fixture.caller) "helper must restore exact absent/pristine caller after setup/body/cleanup failure")
  (when fixture.caller
    (assert (= (getmetatable fixture.caller) nil) "helper must preserve pristine caller metatable absence")
    (assert-slots fixture.caller fixture.caller-slots "helper pristine caller"))
  (assert (= _G.reset-engine-events fixture.reset) "helper must restore reset-engine-events")
  (assert (= package fixture.namespace) "helper must preserve installed namespace identity")
  (assert (= package.preload fixture.preload) "helper must restore preload table identity")
  (assert (= package.loaded fixture.loaded) "helper must restore loaded table identity")
  (assert-slots fixture.namespace fixture.namespace-slots "helper namespace")
  (assert-slots fixture.preload fixture.preload-slots "helper preload")
  (assert-slots fixture.loaded fixture.loaded-slots "helper loaded")
  (assert (= (rawget fixture.loaded :scenario-owned-false) false))
  (assert (= (rawget fixture.preload :scenario-owned-false) false))
  (assert (= (rawget fixture.loaded :scenario-owned-added) nil))
  (assert (= (rawget fixture.preload :scenario-owned-added) nil))
  (assert-original-namespace fixture))

(fn assert-owned-outcome [state ok result]
  (local calls state.calls)
  (local options state.options)
  (assert (= calls.setup 1))
  (assert (= calls.body (if options.setup 0 1)))
  (local acquired? (not (= options.setup :before-allocation)))
  (assert (= calls.teardown (if acquired? 1 0)) "one acquired-app teardown attempt")
  (assert (= calls.drop (if acquired? 1 0)) "one acquired-app drop attempt")
  (assert (= calls.finalizer (if acquired? 1 0)) "use existing captured-engine finalizer")
  (local started? (and acquired? (not (= options.setup :unstarted)) (not options.already-shutdown)))
  (assert (= calls.shutdown (if started? 1 0)) "one started-owner shutdown, no unstarted/already-shutdown attempt")
  (local failed? (if options.setup true options.body true options.drop true options.shutdown true false))
  (assert (= ok (not failed?)) "failure outcome must include cleanup failures")
  (if failed?
      (do
        (each [_ stage (ipairs [:setup :body :drop :shutdown])]
          (when (. options stage)
            (assert (string.find (tostring result) (.. "owned " stage " fault") 1 true)
                    (.. "retain " stage " failure"))))
        (when options.body
          (assert (string.find (tostring result) "scenario failed: " 1 true))
          (assert (string.find (tostring result) "stack traceback:" 1 true))))
      (assert (= result options.result) "return first body result"))
  (when options.shutdown (assert (> (# state.messages) 0) "existing finalizer reports shutdown failure")))

(fn run-owned-case [state fixture]
  (when state.options.pristine
    (assert (pristine-bootstrap? fixture.caller) "owned pristine fixture must satisfy every bootstrap predicate"))
  (local body (make-fake-body state fixture))
  (local patches (make-owned-patches state fixture))
  (fn invoke []
    (local (ok result) (pcall Scenarios.with-test-app body))
    (assert-owned-restoration fixture)
    (assert-owned-outcome state ok result))
  (with-patches patches invoke))

(fn owned-case [options]
  (local finish (native-probe))
  (local state (make-owned-state options))
  (local (ok err) (pcall with-fake-namespace state run-owned-case))
  (finish-probe ok err finish)
  (assert ok (tostring err)))

(local owned-cases
  [{:name "nil result"}
   {:name "false result" :result false}
   {:name "table result" :result {}}
   {:name "setup before allocation" :setup :before-allocation}
   {:name "setup assigned unstarted owner" :setup :unstarted}
   {:name "setup started owner" :setup :started}
   {:name "body failure" :body true}
   {:name "drop failure" :drop true}
   {:name "shutdown failure" :shutdown true}
   {:name "body drop shutdown failures" :body true :drop true :shutdown true}
   {:name "setup drop shutdown failures" :setup :started :drop true :shutdown true}
   {:name "already shutdown owner" :already-shutdown true}
   {:name "replaced module tables" :replace-modules true}
   {:name "body replaces engine reference" :replace-engine true}])

(each [_ options (ipairs owned-cases)]
  (fn check-owned [] (owned-case options))
  (table.insert tests {:name (.. "scenario standalone fake ownership " options.name)
                       :fn check-owned}))

(assert (= (# owned-cases) 14) "retain complete owned failure matrix")
(assert (= (# tests) 38) "retain every helper case")

(each [_ options (ipairs owned-cases)]
  (local pristine-options (copy-slots options))
  (set pristine-options.pristine true)
  (fn check-pristine-owned [] (owned-case pristine-options))
  (table.insert tests {:name (.. "scenario pristine fake ownership " options.name)
                       :fn check-pristine-owned}))

(fn bootstrap-parent-preload [state fixture] (tset fixture.preload :jobs state.parent-preload))
(fn bootstrap-parent-cache [state fixture] (tset fixture.loaded :jobs state.parent-jobs))
(fn bootstrap-parent-main [state fixture] (tset fixture.loaded :main state.parent-main))
(fn bootstrap-false-preload [_ fixture] (tset fixture.preload :jobs false))
(fn bootstrap-false-cache [_ fixture] (tset fixture.loaded :jobs false))
(fn bootstrap-false-main [_ fixture] (tset fixture.loaded :main false))
(fn bootstrap-metatable [_ fixture] (setmetatable fixture.caller {}))
(fn bootstrap-nonempty [_ fixture] (set fixture.caller.unrelated true))
(fn bootstrap-unstarted [_ fixture]
  (set fixture.caller.engine {:is-started not-started :is-shutdown not-started}))
(fn bootstrap-false-engine [_ fixture] (set fixture.caller.engine false))

(local invalid-bootstrap-cases
  [{:name :parent-preload :change bootstrap-parent-preload}
   {:name :parent-cache :change bootstrap-parent-cache}
   {:name :parent-main :change bootstrap-parent-main}
   {:name :false-preload :change bootstrap-false-preload}
   {:name :false-cache :change bootstrap-false-cache}
   {:name :false-main :change bootstrap-false-main}
   {:name :metatable :change bootstrap-metatable}
   {:name :nonempty :change bootstrap-nonempty}
   {:name :unstarted :change bootstrap-unstarted}
   {:name :false-engine :change bootstrap-false-engine}])

(fn reject-bootstrap-lookalike [state fixture]
  (assert (pristine-bootstrap? fixture.caller) "invalid fixture starts from strict pristine state")
  (state.change state fixture)
  (assert (not (pristine-bootstrap? fixture.caller)) "lookalike must violate pristine eligibility")
  (local caller-slots (copy-slots fixture.caller))
  (local metatable (getmetatable fixture.caller))
  (local loaded-slots (copy-slots fixture.loaded))
  (local preload-slots (copy-slots fixture.preload))
  (var called false)
  (fn body [] (set called true))
  (local (ok err) (pcall Scenarios.with-test-app body))
  ;; Observe rejection/restoration before the fixture's safety cleanup.
  (assert (not called) "reject bootstrap lookalike before body")
  (assert (= _G.app fixture.caller) "retain exact rejected bootstrap lookalike")
  (assert (= (getmetatable fixture.caller) metatable))
  (assert-slots fixture.caller caller-slots "rejected caller")
  (assert (= package fixture.namespace))
  (assert (= package.loaded fixture.loaded))
  (assert (= package.preload fixture.preload))
  (assert-slots fixture.loaded loaded-slots "rejected loaded")
  (assert-slots fixture.preload preload-slots "rejected preload")
  (assert (= _G.reset-engine-events fixture.reset))
  (assert-original-namespace fixture)
  (assert (not ok) "reject non-pristine lookalike before setup")
  (assert (string.find (tostring err) "scenario caller" 1 true) "identify invalid bootstrap caller"))

(fn invalid-bootstrap [invalid]
  (local finish (native-probe))
  ;; Retain actual owner binding values before installing any detached namespace.
  (local state {:options {:pristine true} :change invalid.change
                :parent-preload package.preload.jobs :parent-jobs app.engine.jobs
                :parent-main package.loaded.main})
  (fn invoke [] (with-fake-namespace state reject-bootstrap-lookalike))
  (local (ok err) (pcall lifecycle-guard invoke))
  (finish-probe ok err finish)
  (assert ok (tostring err)))

(each [_ invalid (ipairs invalid-bootstrap-cases)]
  (fn check-lookalike [] (invalid-bootstrap invalid))
  (table.insert tests {:name (.. "scenario helper rejects bootstrap lookalike " invalid.name)
                       :fn check-lookalike}))

(assert (= (# tests) 62) "retain original38 plus14 pristine-owned and10 invalid bootstrap cases")

(fn make-standalone-body [observed-engines]
  (fn standalone-body []
    ;; Retain the exact acquired owner before assertions/probes or app replacement.
    ;; Safety cannot depend on the helper returning this body result successfully.
    (local engine app.engine)
    (table.insert observed-engines engine)
    (assert app.testing)
    (assert (and (engine:is-started) (not (engine:is-shutdown))))
    (local finish (native-probe))
    (finish)
    (global app {:standalone-body-replacement true})
    (values {:marker :standalone-first : engine} :ignored))
  standalone-body)

(fn run-standalone-checks [before observed-engines]
  (local body (make-standalone-body observed-engines))
  (local (record second) (Scenarios.with-test-app body))
  (assert (= record.marker :standalone-first))
  (assert (= second nil) "return first result only, ignoring second body value")
  (assert (= _G.app before.app) "helper must restore exact native bootstrap app")
  (assert (= (getmetatable before.app) nil))
  (assert-slots before.app before.app-slots "native bootstrap app")
  (local engine (. observed-engines 1))
  (assert (= record.engine engine) "first result must retain the exact independently captured Engine")
  (assert (engine:is-shutdown) "real standalone must finalize the exact acquired Engine")
  (assert (= _G.reset-engine-events before.reset))
  (assert (= package.preload before.preload))
  (assert (= package.loaded before.loaded))
  (assert-slots before.preload before.preload-slots "standalone preload")
  (assert-slots before.loaded before.loaded-slots "standalone loaded"))

(fn finalize-observed-engine! [engine]
  (when (and (engine:is-started) (not (engine:is-shutdown)))
    (engine:shutdown)))

(fn standalone-main []
  (local bootstrap-app _G.app)
  (assert (pristine-bootstrap? bootstrap-app) "real standalone smoke requires strict pristine native bootstrap")
  (local before {:app bootstrap-app :app-slots (copy-slots bootstrap-app)
                 :namespace package :namespace-slots (copy-slots package)
                 :preload package.preload :preload-slots (copy-slots package.preload)
                 :loaded package.loaded :loaded-slots (copy-slots package.loaded)
                 :reset (rawget _G :reset-engine-events)})
  (local observed-engines [])
  ;; Capture the original outcome BEFORE any safety cleanup. Never re-evaluate
  ;; a helper ownership assertion after the fixture has finalized its leak.
  (local (ok result) (pcall run-standalone-checks before observed-engines))
  (local cleanup-errors [])
  (each [_ engine (ipairs observed-engines)]
    (attempt-safety! cleanup-errors "observed standalone Engine" finalize-observed-engine! engine))
  (attempt-safety! cleanup-errors "standalone loaded slots" restore-slots! before.loaded before.loaded-slots)
  (attempt-safety! cleanup-errors "standalone preload slots" restore-slots! before.preload before.preload-slots)
  (attempt-safety! cleanup-errors "standalone namespace slots" restore-slots! before.namespace before.namespace-slots)
  (attempt-safety! cleanup-errors "standalone bootstrap slots" restore-slots! before.app before.app-slots)
  (attempt-safety! cleanup-errors "standalone bootstrap metatable" setmetatable before.app nil)
  (attempt-safety! cleanup-errors "standalone namespace pointer" rawset _G :package before.namespace)
  (attempt-safety! cleanup-errors "standalone loaded pointer" rawset before.namespace :loaded before.loaded)
  (attempt-safety! cleanup-errors "standalone preload pointer" rawset before.namespace :preload before.preload)
  (attempt-safety! cleanup-errors "standalone reset" rawset _G :reset-engine-events before.reset)
  (attempt-safety! cleanup-errors "standalone bootstrap pointer" rawset _G :app before.app)
  (raise-outcome! ok result cleanup-errors)
  (print "SCENARIO_STANDALONE_OK 1 real owned lifecycle"))

(fn main [] (Runner.run-tests {:name :constraints-scenarios : tests}))

{: tests : main : standalone-main}
