(local ErrorFormat (require :tests.error-format))

(fn log-line [msg]
  (print msg)
  (io.flush))

(fn describe-error [err]
  (local (ok message) (pcall ErrorFormat.format-error err))
  (if (and ok (= (type message) :string)) message (.. "<" (type err) ">")))

(fn protected-call [traceback f]
  (fn report-error [err]
    (local message (describe-error err))
    (if traceback (traceback message 2) message))
  (xpcall f report-error))

(fn copy-array [items]
  (local out [])
  (each [_ item (ipairs items)]
    (table.insert out item))
  out)

(fn env-enabled? [name]
  (= (os.getenv name) "1"))

(fn configured-test-timeout-seconds []
  (local raw (os.getenv "SPACE_TEST_CASE_TIMEOUT_SECONDS"))
  (if (and raw (> (# raw) 0))
      (do
        (local parsed (tonumber raw))
        (assert parsed "SPACE_TEST_CASE_TIMEOUT_SECONDS must be numeric")
        (assert (>= parsed 0) "SPACE_TEST_CASE_TIMEOUT_SECONDS must be non-negative")
        parsed)
      120))

(fn restore-debug-hook! [debug-lib old-hook old-mask old-count]
  (if old-hook
      (debug-lib.sethook old-hook old-mask old-count)
      (debug-lib.sethook nil "" 0)))

(fn make-now-ms []
  (local (ok sysinfo) (pcall (fn []
                               (require :sysinfo))))
  (if (and ok sysinfo sysinfo.now-ms)
      sysinfo.now-ms
      (fn [] (* (os.clock) 1000))))

(fn test-timeout-seconds [test configured-timeout]
  (local timeout test.timeout-seconds)
  (if (= timeout nil)
      configured-timeout
      (do
        (assert (and (= (type timeout) :number) (> timeout 0) (< timeout math.huge))
                (.. "test " test.name " :timeout-seconds must be a positive finite number"))
        timeout)))

(fn protected-call-with-timeout [traceback test configured-timeout]
  (local timeout-seconds (test-timeout-seconds test configured-timeout))
  (local debug-lib _G.debug)
  (if (or (= timeout-seconds 0)
          (not debug-lib)
          (not debug-lib.sethook)
          (not debug-lib.gethook))
      (protected-call traceback test.fn)
      (do
        (local now-ms (make-now-ms))
        (local started-at (now-ms))
        (local timeout-ms (* timeout-seconds 1000))
        (var timed-out? false)
        (var timeout-message nil)
        (local (old-hook old-mask old-count) (debug-lib.gethook))
        (fn timeout-hook []
          (when (and (not timed-out?) (>= (- (now-ms) started-at) timeout-ms))
            (set timed-out? true)
            (set timeout-message (.. "test timed out after " timeout-seconds "s: " test.name))
            ;; Deliver once, then allow protected cleanup/rollback to finish.
            ;; The latch below still fails cases that catch this exception.
            (debug-lib.sethook nil "" 0)
            (error timeout-message 2)))
        (debug-lib.sethook timeout-hook "" 10000)
        (local (ok err) (protected-call traceback test.fn))
        (restore-debug-hook! debug-lib old-hook old-mask old-count)
        (if timed-out?
            (values false timeout-message)
            (values ok err)))))

(local windows-default-skip-modules
  {:tests.test-terminal true
   :tests.test-terminal-widget true
   :tests.test-terminal-renderer true
   :tests.test-terminal-scrollback true
   :tests.test-external-editor true
   :tests.test-ripgrep true
   :tests.test-ripgrep-view true
   :tests.test-flamegraph true
   :tests.test-llm-tools true})

(fn apply-module-overrides [modules]
  (var result (copy-array modules))
  (var platform-os nil)
  (local (sys-ok sysinfo-or-err) (pcall (fn []
                                          (require :sysinfo))))
  (when sys-ok
    (local platform (sysinfo-or-err.platform))
    (when (and platform platform.os)
      (set platform-os platform.os)))

  (when (= platform-os "windows")
    ;; Keep Windows/Wine test filtering explicit and centralized.
    ;; `lua "return true"` per-test skips remain valid for feature-level gates.
    (local excluded {})
    (each [module-name enabled? (pairs windows-default-skip-modules)]
      (when enabled?
        (set (. excluded module-name) true)))
    (local (terminal-ok _terminal) (pcall (fn []
                                            (require :terminal))))
    (when terminal-ok
      (set (. excluded :tests.test-terminal) nil)
      (set (. excluded :tests.test-terminal-widget) nil)
      (set (. excluded :tests.test-terminal-renderer) nil)
      (set (. excluded :tests.test-terminal-scrollback) nil))
    (local filtered [])
    (each [_ module-name (ipairs result)]
      (when (not (. excluded module-name))
        (table.insert filtered module-name)))
    (set result filtered))

  (when (env-enabled? "SPACE_MATRIX_TEST")
    (table.insert result :tests.test-matrix))
  (when (env-enabled? "SPACE_REALTIME_TEST")
    (table.insert result :tests.test-realtime-online))
  (when (env-enabled? "SKIP_KEYRING_TESTS")
    (local filtered [])
    (each [_ module-name (ipairs result)]
      (when (not (= module-name :tests.test-keyring))
        (table.insert filtered module-name)))
    (set result filtered))
  result) (fn ensure-test-interactions [Intersectables Clickables Hoverables] (when (not app.intersectables) (set app.intersectables (Intersectables))) (when (not app.clickables) (set app.clickables (Clickables {:intersectables app.intersectables}))) (when (not app.hoverables) (set app.hoverables (Hoverables {:intersectables app.intersectables}))) (assert app.clickables "test runner requires app.clickables") (assert app.hoverables "test runner requires app.hoverables"))

(fn setup-test-env [test-verbose]
  (global app {})
  (set app.testing true)
  (when test-verbose
    (log-line "[BOOT] loading bindings"))
  (when test-verbose
    (log-line "[BOOT] require :engine"))
  (local EngineModule (require :engine))
  (when test-verbose
    (log-line "[BOOT] require :intersectables"))
  (local Intersectables (require :intersectables))
  (when test-verbose
    (log-line "[BOOT] require :clickables"))
  (local Clickables (require :clickables))
  (when test-verbose
    (log-line "[BOOT] require :hoverables"))
  (local Hoverables (require :hoverables))
  (local Runtime (require :state-runtime))
  (when test-verbose
    (log-line "[BOOT] require :textures"))
  (local textures (require :textures))
  (when test-verbose
    (log-line "[BOOT] test runner"))

  (global reset-engine-events
    (fn []
      (assert (and app.engine app.engine.events) "app.engine.events missing in tests")
      (each [_ signal (pairs app.engine.events)]
        (signal:clear))
      (Runtime.reset)))

  ;; Ensure font textures and loaders are available during tests; do not fall back to stubs.
  (set app.disable_font_textures false)
  (local loaded {})
  (local stub
    (fn [name path]
      (local tex {:id (tonumber (tostring (string.byte name 1) 10))
                  :name name :path path
                  :ready true
                  :width 1
                  :height 1})
      (set tex.allocate
           (fn [_self width height _channels]
             (set tex.width width)
             (set tex.height height)
             (set tex.ready true)))
      (set tex.update-full
           (fn [_self _bytes]
             (set tex.ready true)))
      (tset tex "update-full" tex.update-full)
      (set tex.update-sub-rect
           (fn [_self _x _y _width _height _bytes]
             (set tex.ready true)))
      (tset tex "update-sub-rect" tex.update-sub-rect)
      (set (. loaded name) tex)
      tex))
  (set textures.load-texture stub)
  (set textures.load-texture-async stub)
  (set textures.load-texture-from-bytes
       (fn [name _bytes]
         (stub name "<bytes>")))
  (set textures.load-texture-from-bytes-async textures.load-texture-from-bytes)
  (set textures.load-texture-from-pixels
       (fn [name width height _channels _bytes]
         (local tex (stub name "<pixels>"))
         (set tex.width width)
         (set tex.height height)
         tex))
  (set textures.allocate-texture
       (fn [name width height channels]
         (local tex (stub name "<allocated>"))
         (tex:allocate width height channels)
         tex))
  (tset textures "allocate-texture" textures.allocate-texture)
  (set textures.get-texture
       (fn [name]
         (or (. loaded name)
             (stub name "<lazy>"))))
  (set textures.drop-texture
       (fn [name]
         (if (. loaded name)
             (do
               (set (. loaded name) nil)
               true)
             false)))
  (tset textures "drop-texture" textures.drop-texture)
  (when (not textures.load-cubemap)
    (local cube-stub (fn [_files] {:id 1 :ready true}))
    (set textures.load-cubemap cube-stub)
    (set textures.load-cubemap-async cube-stub))

  (do
    (local MockOpenGL (require :mock-opengl))
    (local global-mock (MockOpenGL))
    (global-mock:install))
  (require :gl)

  (set app.engine (EngineModule.Engine {:headless true}))

  (require :main)

  (app.engine:start)

  (ensure-test-interactions Intersectables Clickables Hoverables)






  ;; Reapply texture stubs in case bindings overwrote them.
  (when textures
    (set textures.load-texture
         (fn [name path]
           (stub name path)))
    (set textures.load-texture-async textures.load-texture)
    (set textures.load-texture-from-bytes
         (fn [name _bytes]
           (textures.load-texture name "<bytes>")))
    (set textures.load-texture-from-bytes-async textures.load-texture-from-bytes)
    (set textures.load-texture-from-pixels
         (fn [name width height _channels _bytes]
           (local tex (stub name "<pixels>"))
           (set tex.width width)
           (set tex.height height)
           tex))
    (set textures.allocate-texture
         (fn [name width height channels]
           (local tex (stub name "<allocated>"))
           (tex:allocate width height channels)
           tex))
    (tset textures "allocate-texture" textures.allocate-texture)
    (set textures.get-texture
         (fn [name]
           (or (. loaded name)
               (stub name "<lazy>"))))
    (set textures.drop-texture
         (fn [name]
           (if (. loaded name)
               (do
                 (set (. loaded name) nil)
                 true)
               false)))
    (tset textures "drop-texture" textures.drop-texture)
    (when (not textures.load-cubemap)
      (set textures.load-cubemap (fn [_files] {:id 1}))
      (set textures.load-cubemap-async textures.load-cubemap)))

  (when (not (and app.themes app.themes.get-active-theme))
    (set app.themes ((require :themes)))
    (app.themes.add-theme :dark (require :dark-theme))
    (app.themes.add-theme :light (require :light-theme))
    (app.themes.set-theme :dark))
  (when (not app.lights)
    (local {:LightSystem LightSystem} (require :light-system))
    (set app.lights (LightSystem {})))
  )

(fn execute-test-list [suite tests test-verbose traceback timeout-seconds]
  (local registered-tests [])
  (each [_ test (ipairs tests)]
    (when (not (= (type test.name) "string"))
      (error "suite test missing name"))
    (when (not (= (type test.fn) "function"))
      (error (.. "suite test " test.name " missing fn")))
    (table.insert registered-tests test))

  (var failures 0)
  (each [_ test (ipairs registered-tests)]
    (when test-verbose
      (log-line (.. "[RUN] " test.name)))
    (local (ok err) (protected-call-with-timeout traceback test timeout-seconds))
    (if ok
        (when test-verbose
          (log-line (.. "[PASS] " test.name)))
        (do
          (log-line (.. "[FAIL] " test.name))
          (log-line err)
          (set failures (+ failures 1)))))

  (values failures (# registered-tests)))

(fn execute-tests [suite test-verbose test-filter traceback timeout-seconds]
  (local registered-tests [])
  (each [_ test (ipairs suite.tests)]
    (when (or (not test-filter)
              (string.find test.name test-filter 1 true))
      (table.insert registered-tests test)))

  (local (initial-failures initial-executed)
    (execute-test-list suite registered-tests test-verbose traceback timeout-seconds))
  (var failures initial-failures)
  (local executed initial-executed)

  (when suite.teardown
    (local (_ok err) (protected-call traceback suite.teardown))
    (when (not _ok)
      (log-line (.. "[FAIL] teardown " err))
      (set failures (+ failures 1))))

  (when (> failures 0)
    (error (.. failures " Lua test(s) failed")))

  (log-line (.. "Executed " executed " Lua tests"))

  suite)

(fn with-engine-shutdown [engine f]
  (local (ok result) (pcall f))
  (local (shutdown-ok shutdown-err) (pcall engine.shutdown engine))
  (local shutdown-message (when (not shutdown-ok) (describe-error shutdown-err)))
  (when (not shutdown-ok)
    (log-line (.. "[FAIL] engine shutdown " shutdown-message)))
  (if (and (not ok) (not shutdown-ok))
      ;; String failures here are runner-generated counts/validation or the
      ;; already-normalized load error + traceback. Do not escape that stack a
      ;; second time. Raw nonstring failures still use the same safe formatter.
      (error (.. (if (= (type result) :string) result (describe-error result))
                 "\nengine shutdown also failed: " shutdown-message) 0)
      (not ok) (error result 0)
      (not shutdown-ok) (error shutdown-err 0)
      result))

(fn run-tests [suite]
  (assert (and suite suite.tests) "tests.runner: suite missing tests")
  (local test-verbose (os.getenv "TEST_VERBOSE"))
  (local test-filter (os.getenv "TEST_FILTER"))
  (local traceback (and _G.debug _G.debug.traceback))
  (local timeout-seconds (configured-test-timeout-seconds))
  (setup-test-env test-verbose)

  (with-engine-shutdown app.engine
    (fn [] (execute-tests suite test-verbose test-filter traceback timeout-seconds))))

(fn execute-modules [suite test-verbose test-filter traceback timeout-seconds print-timings]
  (local modules (apply-module-overrides suite.modules))
  (local now-ms (make-now-ms))
  (var failures 0)
  (var executed 0)
  (local suite-start (now-ms))

  (fn run-module-tests [module-name]
    (when test-verbose
      (log-line (.. "[LOAD] " module-name)))
    (local (ok result)
      (protected-call traceback (fn []
                                  (require module-name))))
    (when (not ok)
      (log-line (.. "[FAIL] load " module-name))
      (log-line result)
      (error (.. "Failed to load " module-name ":\n" result)))
    (do
      (when (not (= (type result) "table"))
        (error (.. module-name " must return a test suite")))
      (local tests (or (. result :tests) result))
      (local registered-tests [])
      (each [_ test (ipairs tests)]
        (when (not (= (type test.name) "string"))
          (error (.. module-name " test missing name")))
        (when (not (= (type test.fn) "function"))
          (error (.. module-name " test " test.name " missing fn")))
        (when (or (not test-filter)
                  (string.find test.name test-filter 1 true))
          (table.insert registered-tests test)))
      (local (module-failures module-executed)
        (execute-test-list {:name module-name} registered-tests test-verbose traceback timeout-seconds))
      (set failures (+ failures module-failures))
      (set executed (+ executed module-executed))))

  (each [_ module-name (ipairs modules)]
    (local module-start (now-ms))
    (run-module-tests module-name)
    (when print-timings
      (log-line (.. "[TIME] " module-name " " (string.format "%.3f" (- (now-ms) module-start)) "ms"))))

  (when suite.teardown
    (local (_ok err) (protected-call traceback suite.teardown))
    (when (not _ok)
      (log-line (.. "[FAIL] teardown " err))
      (set failures (+ failures 1))))

  (when print-timings
    (log-line (.. "[TIME] total suite " (string.format "%.3f" (- (now-ms) suite-start)) "ms")))

  (when (> failures 0)
    (error (.. failures " Lua test(s) failed")))

  (log-line (.. "Executed " executed " Lua tests"))

  suite)

(fn run-modules [suite]
  (assert (and suite suite.modules) "tests.runner: suite missing modules")
  (local test-verbose (os.getenv "TEST_VERBOSE"))
  (local test-filter (os.getenv "TEST_FILTER"))
  (local traceback (and _G.debug _G.debug.traceback))
  (local timeout-seconds (configured-test-timeout-seconds))
  (local print-timings (or (os.getenv "SPACE_TEST_TIMINGS")
                          (os.getenv "TEST_VERBOSE")))
  (setup-test-env test-verbose)
  (with-engine-shutdown app.engine
    (fn [] (execute-modules suite test-verbose test-filter traceback timeout-seconds print-timings))))

(fn shutdown-test-env []
  "Shut down the test environment: drop the app and reset it to an empty table."
  (when (and app app.drop)
    (app.drop))
  (set app {}))

{:run-modules run-modules
 :run-tests run-tests
 :setup-test-env setup-test-env
 :shutdown-test-env shutdown-test-env}
