;; Constraint scenarios borrow verified test runtimes or own standalone setup.
;; Borrowing never starts a nested native Engine: native jobs ownership is global.
(local TestRunner (require :tests/runner))

(fn traceback [err]
  (if (and _G.debug _G.debug.traceback)
      (_G.debug.traceback (tostring err) 3)
      (tostring err)))

(fn copy-slots [object]
  (local slots {})
  (each [key value (pairs object)] (tset slots key value))
  slots)

(fn restore-slots! [object slots]
  (local keys [])
  (each [key _ (pairs object)] (table.insert keys key))
  (each [_ key (ipairs keys)] (rawset object key nil))
  (each [key value (pairs slots)] (rawset object key value)))

(fn attempt! [errors stage f ...]
  (local (ok err) (pcall f ...))
  (when (not ok)
    (table.insert errors (.. "scenario cleanup " stage " failed: " (tostring err)))))

(fn finish [ok result errors prefix]
  (local messages [])
  (when (not ok) (table.insert messages (.. prefix (tostring result))))
  (each [_ message (ipairs errors)] (table.insert messages message))
  (if (> (# messages) 0) (error (table.concat messages "\n") 2) result))

(fn pristine-bootstrap? [caller]
  (and (= (type caller) :table)
       (= (getmetatable caller) nil)
       (= (next caller) nil)
       (= (rawget caller :engine) nil)
       (= (rawget package.loaded :main) nil)
       (= (rawget package.preload :jobs) nil)
       (= (rawget package.loaded :jobs) nil)))

(fn require-service [caller key methods]
  (local service (rawget caller key))
  (assert (= (type service) :table) (.. "scenario caller requires " key))
  (each [_ method (ipairs methods)]
    (assert (= (type (. service method)) :function)
            (.. "scenario caller requires " key "." method))))

(fn verify-caller! [caller]
  (assert (= (type caller) :table) "scenario caller must be an initialized test app")
  (assert (= (rawget caller :testing) true) "scenario caller must be marked testing")
  (local engine (rawget caller :engine))
  (assert (= (type engine) :table) "scenario caller requires its Engine")
  (assert (and (= (type engine.is-started) :function) (= (type engine.is-shutdown) :function))
          "scenario caller requires Engine lifecycle queries")
  (assert (= (engine:is-started) true) "scenario caller Engine must be started")
  (assert (= (engine:is-shutdown) false) "scenario caller Engine must not be shutdown")
  (assert engine.physics "scenario caller requires Engine physics")
  (assert (and (= (type engine.jobs) :table)
               (= (type engine.jobs.submit) :function)
               (= (type engine.jobs.poll) :function))
          "scenario caller requires Engine jobs")
  (assert (rawget package.loaded :main) "scenario caller requires cached main")
  (each [_ [key methods] (ipairs [[:intersectables [:select-entry :resolve-ray :pointer :drop]]
                                 [:clickables [:register :unregister :drop]]
                                 [:hoverables [:register :unregister :drop]]
                                 [:themes [:get-active-theme]]
                                 [:lights [:get-state :clear]]])]
    (require-service caller key methods))
  (local loader (rawget package.preload :jobs))
  (assert (= (type loader) :function) "scenario caller requires jobs preload")
  (local (ok jobs) (pcall loader))
  (assert ok (.. "scenario caller jobs preload failed: " (tostring jobs)))
  (assert (= jobs engine.jobs) "scenario caller jobs preload must resolve to its Engine jobs")
  (local cached (rawget package.loaded :jobs))
  (when (not (= cached nil))
    (assert (= cached engine.jobs) "scenario caller cached jobs must match its Engine jobs")))

(fn with-borrowed-app [caller f]
  (local (valid err) (pcall verify-caller! caller))
  (rawset _G :app caller)
  (when (not valid) (error (.. "scenario caller rejected: " (tostring err)) 2))
  (local (ok result) (xpcall f traceback))
  (rawset _G :app caller)
  (finish ok result [] "scenario failed: "))

(fn snapshot-context [caller]
  {:app caller :app-slots (when caller (copy-slots caller))
   :reset (rawget _G :reset-engine-events)
   :namespace package :namespace-slots (copy-slots package)
   :loaded package.loaded :loaded-slots (copy-slots package.loaded)
   :preload package.preload :preload-slots (copy-slots package.preload)})

(fn capture-owned! [owner caller]
  (local candidate (rawget _G :app))
  (when (and (not owner.app) (= (type candidate) :table) (not (= candidate caller)))
    (set owner.app candidate)
    (set owner.engine (rawget candidate :engine))))

(fn setup-owned [owner caller]
  (fn setup []
    (TestRunner.setup-test-env false)
    (capture-owned! owner caller)
    (assert owner.app "scenario setup did not allocate its app")
    (assert owner.engine "scenario setup did not allocate its Engine"))
  (fn failed [err]
    ;; Capture at the setup error boundary, before any teardown can replace app.
    ;; Runner assigns the new app and Engine before main loading / Engine.start.
    (capture-owned! owner caller)
    (traceback err))
  (xpcall setup failed))

(fn idle [] nil)

(fn cleanup-owned! [owner errors]
  (fn teardown []
    (rawset _G :app owner.app)
    (TestRunner.shutdown-test-env))
  (when owner.app (attempt! errors "owned app teardown" teardown))
  ;; App teardown may throw, clear app, replace its Engine field, or shut down
  ;; the owner itself. Always use the captured Engine and the runner's policy.
  (when owner.engine
    (attempt! errors "owned Engine finalization" TestRunner.with-owned-engine owner.engine idle traceback)))

(fn restore-context! [before errors]
  (attempt! errors "loaded slots" restore-slots! before.loaded before.loaded-slots)
  (attempt! errors "preload slots" restore-slots! before.preload before.preload-slots)
  (attempt! errors "namespace slots" restore-slots! before.namespace before.namespace-slots)
  (when before.app
    (attempt! errors "bootstrap app slots" restore-slots! before.app before.app-slots)
    (attempt! errors "bootstrap app metatable" setmetatable before.app nil))
  (attempt! errors "namespace pointer" rawset _G :package before.namespace)
  (attempt! errors "loaded pointer" rawset before.namespace :loaded before.loaded)
  (attempt! errors "preload pointer" rawset before.namespace :preload before.preload)
  (attempt! errors "reset-engine-events" rawset _G :reset-engine-events before.reset)
  (attempt! errors "caller app" rawset _G :app before.app))

(fn with-owned-app [caller f]
  (local before (snapshot-context caller))
  (local owner {})
  (local (setup-ok setup-result) (setup-owned owner caller))
  (local (ok result) (if setup-ok (xpcall f traceback) (values false setup-result)))
  (local errors [])
  (cleanup-owned! owner errors)
  (restore-context! before errors)
  (finish ok result errors (if setup-ok "scenario failed: " "scenario setup failed: ")))

(fn with-test-app [f]
  "Return only f's first result, preserving nil/false and body traceback errors.
  Borrow a verified initialized test caller without setup/teardown/native rebinding.
  Only nil or a strict pristine native bootstrap permits owned setup/finalization."
  (local caller (rawget _G :app))
  (if (= caller nil) (with-owned-app caller f)
      (pristine-bootstrap? caller) (with-owned-app caller f)
      (with-borrowed-app caller f)))

{: with-test-app}
