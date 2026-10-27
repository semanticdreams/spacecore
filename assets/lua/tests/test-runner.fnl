(local process (require :process))
(local callbacks (require :callbacks))
(local RuntimeBin (require :tests.runtime-bin))
(local cases (require :tests.runner-regression-cases))
(local tests [])

;; Check the real caller's native ownership, not just Lua app restoration or a
;; successful child exit. Register before the invocation; dispatch only after it.
(fn with-parent-runtime [f]
  (local parent-app app)
  (local parent-engine app.engine)
  (local parent-filter (os.getenv "TEST_FILTER"))
  (local parent-timeout (os.getenv "SPACE_TEST_CASE_TIMEOUT_SECONDS"))
  (var sentinel nil)
  (var job-result nil)
  (fn receive [payload] (set sentinel payload))
  (local id (callbacks.register receive))
  (local (ok err) (pcall f))
  (fn receive-job [result] (set job-result result))
  (fn job-received? [] job-result)
  (fn check-jobs []
    (parent-engine.jobs.submit {:kind "echo" :payload "parent jobs still usable"
                                :callback receive-job})
    (callbacks.run-loop {:poll-jobs true :poll-http false :sleep-ms 0
                         :timeout-ms 2000 :until job-received?}))
  (local (jobs-ok jobs-err) (pcall check-jobs))
  (callbacks.enqueue id "parent callback survived")
  (callbacks.dispatch)
  (callbacks.unregister id)
  (assert ok (tostring err))
  (assert (= sentinel "parent callback survived")
          (.. "parent callback registry was cleared; jobs-ok=" (tostring jobs-ok) " jobs-error=" (tostring jobs-err)))
  (assert jobs-ok (tostring jobs-err))
  (assert (and job-result job-result.ok (= job-result.result "parent jobs still usable"))
          "parent jobs must remain usable after runner regression")
  (assert (and (= app parent-app) (= app.engine parent-engine) (not (parent-engine:is-shutdown))))
  (assert (= (os.getenv "TEST_FILTER") parent-filter) "parent filter must be unchanged")
  (assert (= (os.getenv "SPACE_TEST_CASE_TIMEOUT_SECONDS") parent-timeout) "parent deadline must be unchanged"))

(fn assert-child [result marker]
  (local diagnostic (.. "runner child exit=" (tostring result.exit-code)
                        " timed-out=" (tostring result.timed-out)
                        "\nstdout:\n" result.stdout "\nstderr:\n" result.stderr))
  (assert (and (= result.exit-code 0) (not result.timed-out)) diagnostic)
  (local (first last) (string.find result.stdout marker 1 true))
  (assert first (.. "runner child did not complete its selected case/count\n" diagnostic))
  (assert (not (string.find result.stdout marker (+ last 1) true)) "runner child ran selected case more than once"))

(fn run-case [index name]
  (local configured-timeout (. cases.configured-timeouts index))
  (for [variant 1 (. cases.variant-counts index)]
    (local result
      (process.run {:args [(RuntimeBin.resolve) "-m" "tests.runner-regression-cases:main"]
                    ;; Override inherited selection/settings only in the child.
                    ;; Most cases exercise default120; policy controls use 10/0.
                    :env {:TEST_FILTER ""
                          :SPACE_TEST_CASE_TIMEOUT_SECONDS (if configured-timeout configured-timeout "")
                          :SPACE_RUNNER_REGRESSION_CASE (tostring index)
                          :SPACE_RUNNER_REGRESSION_VARIANT (tostring variant)}
                    :timeout 120}))
    (assert-child result (.. "RUNNER_REGRESSION_OK " index "/" variant " " name))))

(assert (= (# cases.names) 35) "retain the 15 original, seven budget and thirteen readable-error regressions")
(each [index name (ipairs cases.names)]
  (fn invoke [] (run-case index name))
  (fn check [] (with-parent-runtime invoke))
  (table.insert tests {: name :fn check}))

;; Normal outer TEST_FILTER must select one exported wrapper, not accidentally
;; filter its differently named inner case. The grandchild still uses default120.
(fn filtered-case [name timeout]
  (local result
    (process.run {:args [(RuntimeBin.resolve) "-m" "tests.test-runner:main"]
                  :env {:TEST_FILTER name :SPACE_TEST_CASE_TIMEOUT_SECONDS timeout}
                  :timeout 120}))
  (assert-child result "Executed 1 Lua tests")
  (assert (not (string.find result.stdout "[FAIL]" 1 true)) "successful parent must not print deliberate child failures")
  (assert (not (string.find result.stdout "Executed 0 Lua tests" 1 true)) "selected regression must not execute zero cases"))

(fn filtered-shutdown []
  (fn invoke [] (filtered-case "runner tests shuts down once on success" "30"))
  (with-parent-runtime invoke))

(fn filtered-timeout []
  (fn invoke [] (filtered-case "runner restores prior hook after caught timeout" "0"))
  (with-parent-runtime invoke))

(fn filtered-override []
  (fn invoke [] (filtered-case "runner per-test budget overrides default with caught timeout" "30"))
  (with-parent-runtime invoke))

(table.insert tests {:name "runner outer filter selects shutdown regression with custom deadline" :fn filtered-shutdown})
(table.insert tests {:name "runner outer filter selects timeout regression with disabled parent deadline" :fn filtered-timeout})
(table.insert tests {:name "runner outer filter selects per-test budget override" :fn filtered-override})

(fn filtered-diagnostics []
  (fn invoke [] (filtered-case "runner prints safe readable errors tests body" "30"))
  (with-parent-runtime invoke))
(table.insert tests {:name "runner outer filter captures deliberate structured child failures" :fn filtered-diagnostics})

(fn formatter-allowlist []
  (local {:format-error format-error} (require :tests.error-format))
  (local state {:calls 0})
  (fn hostile [_] (set state.calls (+ state.calls 1)) (error "hostile metatable"))
  (local err {:code :storage-failed :message "readable first failure" :outcome :not-committed
             :current-revision "revision-1" :result {:private "PRIVATE_RESULT_SENTINEL"}
             :credential "PRIVATE_RESULT_SENTINEL"})
  (set err.result.cycle err)
  (setmetatable err {:__index hostile :__pairs hostile :__tostring hostile :__len hostile})
  (assert (= (format-error err)
             "code=\"storage-failed\" message=\"readable first failure\" outcome=\"not-committed\" current-revision=\"revision-1\""))
  (assert (= (format-error (setmetatable {} {:__index hostile :__pairs hostile :__tostring hostile})) "<table>"))
  (set err.code err)
  (set err.message (fn unsupported [] nil))
  (assert (= (format-error err)
             "code=\"<table>\" message=\"<function>\" outcome=\"not-committed\" current-revision=\"revision-1\""))
  (assert (= state.calls 0)))

(fn formatter-bounds []
  (local {:format-error format-error} (require :tests.error-format))
  (assert (= (format-error "plain readable error") "plain readable error"))
  (assert (= (format-error (.. "line\n\r\t" (string.char 27 0) "雪\\\"")) "line\\n\\r\\t\\x1b\\x00\\xe9\\x9b\\xaa\\\\\\\""))
  (local huge (string.rep (.. (string.char 27) "雪") 1048576))
  (each [_ err (ipairs [huge {:code huge :message huge :outcome huge :current-revision huge}])]
    (local formatted (format-error err))
    (assert (<= (# formatted) 2048) "bound encoded bytes, not raw input bytes")
    (assert (string.find formatted "[truncated]" 1 true) "truncation must be visible")
    (for [index 1 (# formatted)]
      (local byte (string.byte formatted index))
      (assert (and (>= byte 32) (<= byte 126)) "only printable ASCII in base error"))
    (when (= (type err) :table)
      (assert (string.find formatted "message=" 1 true) "huge code must not crowd out message")
      (assert (string.find formatted "outcome=" 1 true))
      (assert (string.find formatted "current-revision=" 1 true)))))

(fn formatter-primitives []
  (local {:format-error format-error} (require :tests.error-format))
  (local state {:calls 0})
  (fn hostile [_] (set state.calls (+ state.calls 1)) (error "primitive tostring invoked"))
  (local old-number (debug.getmetatable 1))
  (local old-boolean (debug.getmetatable true))
  (debug.setmetatable 1 {:__tostring hostile})
  (debug.setmetatable true {:__tostring hostile})
  (local (ok formatted) (pcall format-error {:code 123 :message false :outcome true}))
  (debug.setmetatable 1 old-number)
  (debug.setmetatable true old-boolean)
  (assert ok)
  (assert (= formatted "code=\"123\" message=\"false\" outcome=\"true\""))
  (assert (= state.calls 0))
  (assert (= (format-error nil) "<nil>"))
  (assert (= (format-error io.stdout) "<userdata>")))

(each [_ test (ipairs [{:name "runner error formatter whitelists raw scalar fields without traversing objects" :fn formatter-allowlist}
                       {:name "runner error formatter bounds encoded output and escapes controls" :fn formatter-bounds}
                       {:name "runner error formatter never stringifies primitive or unsupported objects" :fn formatter-primitives}])]
  (fn invoke [] (with-parent-runtime test.fn))
  (table.insert tests {:name test.name :fn invoke}))

(fn main []
  (local runner (require :tests/runner))
  (runner.run-tests {: tests}))

{: tests : main}
