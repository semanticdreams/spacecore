(local tests [])

;; --- Diagnostics tests ---

(fn diagnostic-violation-normalizes-fields []
  (local Diagnostics (require :constraints.diagnostics))
  (local d (Diagnostics.violation
             {:constraint-id "test-rule"
              :family "style"
              :severity :warning
              :message "something is wrong"
              :target {:kind :files :name "test-target"}
              :file "test.fnl"
              :line 42
              :column 7
              :evidence {:found "x" :expected "y"}
              :hint "try fixing it"}))
  (assert (= d.constraint-id "test-rule") "constraint-id should be preserved")
  (assert (= d.family "style") "family should be preserved")
  (assert (= d.severity :warning) "severity should be preserved")
  (assert (= d.message "something is wrong") "message should be preserved")
  (assert (= d.target.kind :files) "target kind should be preserved")
  (assert (= d.target.name "test-target") "target name should be preserved")
  (assert (= d.file "test.fnl") "file should be preserved")
  (assert (= d.line 42) "line should be preserved")
  (assert (= d.column 7) "column should be preserved")
  (assert (= d.evidence.found "x") "evidence should be preserved")
  (assert (= d.evidence.expected "y") "evidence should be preserved")
  (assert (= d.hint "try fixing it") "hint should be preserved"))

(fn diagnostic-violation-defaults-severity-and-evidence []
  (local Diagnostics (require :constraints.diagnostics))
  (local d (Diagnostics.violation
             {:constraint-id "test-defaults"
              :family "correctness"
              :message "missing defaults"
              :hint "add them"}))
  (assert (= d.severity :error) "severity should default to :error")
  (assert (= d.evidence.found nil) "evidence should default to empty table")
  (assert (= d.constraint-id "test-defaults") "constraint-id should be preserved")
  (assert (= d.family "correctness") "family should be preserved")
  (assert (= d.message "missing defaults") "message should be preserved")
  (assert (= d.hint "add them") "hint should be preserved"))

(fn diagnostic-violation-requires-constraint-id []
  (local Diagnostics (require :constraints.diagnostics))
  (local (ok err) (pcall #(Diagnostics.violation
                            {:family "style"
                             :message "bad"
                             :hint "fix it"})))
  (assert (not ok) "expected missing constraint-id to raise an error")
  (assert (string.find (tostring err) "constraint-id" 1 true)
          (.. "error should mention constraint-id, got: " (tostring err))))

(fn diagnostic-violation-requires-family []
  (local Diagnostics (require :constraints.diagnostics))
  (local (ok err) (pcall #(Diagnostics.violation
                            {:constraint-id "test"
                             :message "bad"
                             :hint "fix it"})))
  (assert (not ok) "expected missing family to raise an error")
  (assert (string.find (tostring err) "family" 1 true)
          (.. "error should mention family, got: " (tostring err))))

(fn diagnostic-violation-requires-message []
  (local Diagnostics (require :constraints.diagnostics))
  (local (ok err) (pcall #(Diagnostics.violation
                            {:constraint-id "test"
                             :family "style"
                             :hint "fix it"})))
  (assert (not ok) "expected missing message to raise an error")
  (assert (string.find (tostring err) "message" 1 true)
          (.. "error should mention message, got: " (tostring err))))

(fn diagnostic-violation-requires-hint []
  (local Diagnostics (require :constraints.diagnostics))
  (local (ok err) (pcall #(Diagnostics.violation
                            {:constraint-id "test"
                             :family "style"
                             :message "bad"})))
  (assert (not ok) "expected missing hint to raise an error")
  (assert (string.find (tostring err) "hint" 1 true)
          (.. "error should mention hint, got: " (tostring err))))

(fn diagnostic-framework-failure-produces-normalized-diagnostic []
  (local Diagnostics (require :constraints.diagnostics))
  (local d (Diagnostics.framework-failure
             {:constraint-id "runner"
              :family "framework"
              :message "something crashed"
              :hint "check the runner"}))
  (assert (= d.constraint-id "runner") "constraint-id should be preserved")
  (assert (= d.family "framework") "family should be preserved")
  (assert (= d.severity :error) "severity should default to :error")
  (assert (= d.message "something crashed") "message should be preserved")
  (assert (= d.hint "check the runner") "hint should be preserved"))

(fn diagnostic-summary-counts-by-family []
  (local Diagnostics (require :constraints.diagnostics))
  (local diags
    [(Diagnostics.violation
       {:constraint-id "r1" :family "style" :message "m1" :hint "h1"})
     (Diagnostics.violation
       {:constraint-id "r2" :family "style" :message "m2" :hint "h2"})
     (Diagnostics.violation
       {:constraint-id "r3" :family "correctness" :severity :warning :message "m3" :hint "h3"})
     (Diagnostics.framework-failure
       {:constraint-id "f1" :family "framework" :message "m4" :hint "h4"})])
  (local summary (Diagnostics.summary :violations diags))
  (assert (= summary.total 4) "total should be 4")
  (assert (= summary.by-family.style 2) "style count should be 2")
  (assert (= summary.by-family.correctness 1) "correctness count should be 1")
  (assert (= summary.by-family.framework 1) "framework count should be 1")
  (assert (= summary.by-severity.error 3) "error count should be 3")
  (assert (= summary.by-severity.warning 1) "warning count should be 1"))

;; --- Runner tests ---

(fn runner-noop-rule-returns-pass []
  (local Runner (require :constraints.runner))
  (local result (Runner.run
                  {:rules [(fn [_target] nil)]
                   :target {:kind :files :name "test-target"}
                   :baseline-data false}))
  (assert (= result.status :pass) (.. "expected :pass, got " (tostring result.status)))
  (assert (= result.counts.total 0) "expected 0 diagnostics for no-op rule")
  (assert (= (# result.diagnostics) 0) "expected empty diagnostics list"))

(fn runner-violation-rule-returns-violations []
  (local Runner (require :constraints.runner))
  (local Diagnostics (require :constraints.diagnostics))
  (local result (Runner.run
                  {:rules [(fn [_target]
                             (Diagnostics.violation
                               {:constraint-id "test-rule"
                                :family "style"
                                :message "something wrong"
                                :hint "fix it"}))]
                   :target {:kind :files :name "test-target"}
                   :baseline-data false}))
  (assert (= result.status :violations) (.. "expected :violations, got " (tostring result.status)))
  (assert (= result.counts.total 1) "expected 1 diagnostic")
  (assert (= (# result.diagnostics) 1) "expected 1 diagnostic in list")
  (local d (. result.diagnostics 1))
  (assert (= (. d :constraint-id) "test-rule") "diagnostic should include constraint-id")
  ;; R1-2: every emitted diagnostic includes the runner's target
  (assert (. d :target) "diagnostic should include target")
  (assert (= (. d :target :kind) :files) "target kind should be files")
  (assert (= (. d :target :name) "test-target") "target name should be test-target"))

(fn runner-crashing-rule-returns-fail []
  (local Runner (require :constraints.runner))
  (local result (Runner.run
                  {:rules [(fn [_target]
                             (error "boom"))]
                   :target {:kind :files :name "test-target"}
                   :baseline-data false}))
  (assert (= result.status :fail) (.. "expected :fail, got " (tostring result.status)))
  (assert (= result.counts.total 1) "expected 1 diagnostic for crashing rule")
  (assert (= (# result.diagnostics) 1) "expected 1 diagnostic in list")
  (local d (. result.diagnostics 1))
  (assert (= (. d :family) "framework") "crash diagnostic should have family framework")
  ;; R1-2: framework-failure diagnostic includes the runner's target
  (assert (. d :target) "crash diagnostic should include target")
  (assert (= (. d :target :kind) :files) "target kind should be files")
  (assert (= (. d :target :name) "test-target") "target name should be test-target"))

(fn runner-status-precedence []
  (local Runner (require :constraints.runner))
  (local Diagnostics (require :constraints.diagnostics))
  ;; pass + violations = violations
  (local result1 (Runner.run
                   {:rules [(fn [_target] nil)
                            (fn [_target]
                              (Diagnostics.violation
                                {:constraint-id "r1"
                                 :family "style"
                                 :message "issue"
                                 :hint "fix it"}))]
                    :target {:kind :files :name "precedence-test"}
                    :baseline-data false}))
  (assert (= result1.status :violations) (.. "pass + violations should be :violations, got " (tostring result1.status)))
  ;; violations + fail = fail
  (local result2 (Runner.run
                   {:rules [(fn [_target]
                              (Diagnostics.violation
                                {:constraint-id "r1"
                                 :family "style"
                                 :message "issue"
                                 :hint "fix it"}))
                            (fn [_target]
                              (error "crash"))]
                    :target {:kind :files :name "precedence-test"}
                    :baseline-data false}))
  (assert (= result2.status :fail) (.. "violations + fail should be :fail, got " (tostring result2.status))))

(fn runner-main-prints-json-and-exits-zero-on-pass []
  (local Runner (require :constraints.runner))
  (var printed nil)
  (var exit-code nil)
  (local fake-print (fn [msg] (set printed msg)))
  (local fake-exit (fn [code] (set exit-code code)))
  (Runner.main {:rules [(fn [_target] nil)]
                :target {:kind :files :name "test"}
                :print fake-print
                :exit fake-exit
                :baseline-data false})
  (assert printed "expected print to be called")
  (local json (require :json))
  (local (ok parsed) (pcall json.loads printed))
  (assert ok (.. "expected valid JSON, got: " (tostring printed)))
  (assert (= parsed.status :pass) (.. "no rules should yield :pass, got " (tostring parsed.status)))
  (assert (= parsed.counts.total 0) "no rules should yield 0 diagnostics")
  (assert exit-code "expected exit to be called")
  (assert (= exit-code 0) "pass should exit 0"))

(fn runner-main-prints-json-and-exits-nonzero-on-violations []
  (local Runner (require :constraints.runner))
  (local Diagnostics (require :constraints.diagnostics))
  (var printed nil)
  (var exit-code nil)
  (local fake-print (fn [msg] (set printed msg)))
  (local fake-exit (fn [code] (set exit-code code)))
  (Runner.main {:rules [(fn [_target]
                          (Diagnostics.violation
                            {:constraint-id "test"
                             :family "style"
                             :message "bad"
                             :hint "fix"}))]
                :target {:kind :files :name "test"}
                :print fake-print
                :exit fake-exit
                :baseline-data false})
  (assert printed "expected print to be called")
  (local json (require :json))
  (local (ok parsed) (pcall json.loads printed))
  (assert ok (.. "expected valid JSON, got: " (tostring printed)))
  (assert (= parsed.status :violations) (.. "expected :violations, got " (tostring parsed.status)))
  (assert (= parsed.counts.total 1) "expected 1 diagnostic")
  (assert exit-code "expected exit to be called")
  (assert (not= exit-code 0) (.. "violations should exit non-zero, got " (tostring exit-code))))

(fn run-runner-main-capturing [opts]
  (local Runner (require :constraints.runner))
  (var printed nil)
  (var exit-code nil)
  (local merged opts)
  (tset merged :print (fn [msg] (set printed msg)))
  (tset merged :exit (fn [code] (set exit-code code)))
  (Runner.main merged)
  {:printed printed :exit-code exit-code})

(fn runner-main-summary-pass-is-concise []
  (local captured
    (run-runner-main-capturing {:rules [(fn [_target] nil)]
                                :target {:kind :files :name "test"}
                                :output :summary
                                :baseline-data false}))
  (assert (= captured.exit-code 0))
  (assert (= captured.printed "constraints: pass (0 diagnostics)")))

(fn runner-main-summary-violations-include-diagnostic-and-rerun []
  (local Diagnostics (require :constraints.diagnostics))
  (local captured
    (run-runner-main-capturing {:rules [(fn [_target]
                                          (Diagnostics.violation
                                            {:constraint-id "test"
                                             :family "style"
                                             :file "assets/lua/example.fnl"
                                             :line 3
                                             :column 4
                                             :message "bad"
                                             :hint "fix"}))]
                                :target {:kind :files :name "test"}
                                :output :summary
                                :baseline-data false}))
  (assert (not= captured.exit-code 0))
  (assert (string.find captured.printed "constraints: violations (1 diagnostic)" 1 true))
  (assert (string.find captured.printed "assets/lua/example.fnl:3:4" 1 true))
  (assert (string.find captured.printed "bad" 1 true))
  (assert (string.find captured.printed "hint: fix" 1 true))
  (assert (string.find captured.printed "rerun with --output json" 1 true)))

(fn runner-main-global-argv-summary-parses-output-flag []
  (local Runner (require :constraints.runner))
  (local previous-arg _G.arg)
  (local previous-print print)
  (local previous-exit os.exit)
  (local previous-run-target Runner.run-target)
  (var printed nil)
  (var exit-code nil)
  (set _G.arg ["--" "--output" "summary" "--target" "repo"])
  (tset _G :print (fn [msg] (set printed msg)))
  (tset os :exit (fn [code] (set exit-code code)))
  (tset Runner :run-target (fn [_target _opts]
                             {:status :pass
                              :counts {:total 0 :by-family {} :by-severity {}}
                              :diagnostics []}))
  (local (ok err) (pcall #(Runner.main)))
  (set _G.arg previous-arg)
  (tset _G :print previous-print)
  (tset os :exit previous-exit)
  (tset Runner :run-target previous-run-target)
  (assert ok (.. "Runner.main global argv summary should not crash, got: " (tostring err)))
  (assert (= exit-code 0))
  (assert (= printed "constraints: pass (0 diagnostics)")))

;; R1-1: Runner.main tolerates nil opts (runtime zero-arg entry point)
(fn runner-main-handles-nil-opts []
  (local Runner (require :constraints.runner))
  (local previous-run-target Runner.run-target)
  ;; The runtime calls module functions with no arguments.
  ;; Verify Runner.main does not crash when opts is nil.
  ;; We stub os.exit because the real one would terminate the test process,
  ;; and we stub run-target to avoid redundant full-repo execution.
  (var exit-code nil)
  (var printed nil)
  (local orig-exit os.exit)
  (local orig-print print)
  (tset os :exit (fn [code] (set exit-code code)))
  (tset _G :print (fn [msg] (set printed msg)))
  (tset Runner :run-target (fn [_target _opts]
                             {:status :pass
                              :counts {:total 0 :by-family {} :by-severity {}}
                              :diagnostics []}))
  (local (ok err) (pcall #(Runner.main)))  ;; nil opts
  (tset Runner :run-target previous-run-target)
  (tset os :exit orig-exit)
  (tset _G :print orig-print)
  (assert ok (.. "Runner.main(nil) must not crash, got: " (tostring err)))
  (assert printed "print should have been called")
  (assert exit-code "exit should have been called"))

;; R1-3: timeout produces :interrupted status
(fn runner-timeout-produces-interrupted []
  (local Runner (require :constraints.runner))
  ;; A busy-loop rule with a short timeout should be interrupted.
  (fn busy-rule [_target]
    ;; Tight loop: keep CPU busy so the timer hook fires
    (var i 0)
    (while true
      (set i (+ i 1))))
  (local result (Runner.run
                  {:rules [busy-rule]
                   :target {:kind :files :name "timeout-test"}
                   :timeout-seconds 0.1
                   :baseline-data false}))
  (assert (= result.status :interrupted)
          (.. "expected :interrupted for timed-out rule, got " (tostring result.status)))
  (assert (= result.counts.total 1) "expected 1 diagnostic for interrupted rule")
  (assert (= (# result.diagnostics) 1) "expected 1 diagnostic in list")
  (local d (. result.diagnostics 1))
  (assert (. d :interrupted) "interrupted diagnostic should have :interrupted flag")
  (assert (. d :target) "interrupted diagnostic should include target"))

;; R1-3: interrupted wins precedence over fail
(fn runner-interrupted-precedence-over-fail []
  (local Runner (require :constraints.runner))
  (local Diagnostics (require :constraints.diagnostics))
  ;; A violation rule first, then a timed-out rule. Result should be :interrupted.
  (fn busy-rule [_target]
    (var i 0)
    (while true
      (set i (+ i 1))))
  (local result (Runner.run
                  {:rules [(fn [_target]
                             (Diagnostics.violation
                               {:constraint-id "v1"
                                :family "style"
                                :message "violation"
                                :hint "fix"}))
                           busy-rule]
                   :target {:kind :files :name "precedence-interrupt"}
                   :timeout-seconds 0.1
                   :baseline-data false}))
  (assert (= result.status :interrupted)
          (.. "violations + interrupted should be :interrupted, got " (tostring result.status))))

(fn assert-result-parity [expected actual]
  (assert (= (type expected) (type actual)) "observer changed result type")
  (if (= (type expected) :table)
      (do
        (each [key value (pairs expected)] (assert-result-parity value (. actual key)))
        (each [key _ (pairs actual)] (assert (not= (. expected key) nil) "observer added result data")))
      (assert (= expected actual) "observer changed result data")))

(fn with-observer-target [body]
  (local fs (require :fs))
  (local dir (fs.join-path "/tmp/space/tests" "constraints-observer-runner"))
  (fs.create-dirs dir)
  (local path (fs.join-path dir "sample.fnl"))
  (fs.write-file path "(fn fixture [] (let [private-value 1] private-value))")
  (local target {:kind :files :name "private-target" :files [path] :module-roots [dir]
                :suites [:structure-formatting]})
  (local (ok result) (pcall body target))
  (fs.remove-all dir)
  (if ok result (error result 0)))

(fn assert-runner-event-schema [events]
  (local allowed {:edge true :phase true :subphase true :file true :index true
                  :rule-id true :count true :definitions true :calls true})
  (local phases {:discover true :facts true :select true :rule true :baseline true :summarize true})
  (local subphases {:scan true :read true :parse true :extract true :recover true :span true})
  (each [_ event (ipairs events)]
    (assert (or (= event.edge :begin) (= event.edge :end)))
    (assert (. phases event.phase))
    (when event.subphase (assert (. subphases event.subphase)))
    (when event.file (assert (= event.file "sample.fnl")))
    (each [key value (pairs event)]
      (assert (. allowed key) (.. "unexpected event field " key))
      (assert (or (= (type value) :string) (= (type value) :number)))
      (when (= (type value) :number)
        (assert (= value (math.floor value)))
        (assert (>= value (if (= key :index) 1 0)))))))

(fn assert-runner-phase-order [events]
  (local Registry (require :constraints.rules.init))
  (local expected [[:begin :discover] [:end :discover] [:begin :facts] [:end :facts]
                   [:begin :select] [:end :select]])
  (each [_ rule (ipairs (Registry.all-rules))]
    (when (= rule.family :structure-formatting)
      (table.insert expected [:begin :rule rule.id])
      (table.insert expected [:end :rule rule.id])))
  (each [_ phase (ipairs [:baseline :summarize])]
    (table.insert expected [:begin phase])
    (table.insert expected [:end phase]))
  (local actual [])
  (each [_ event (ipairs events)]
    (when (not event.subphase) (table.insert actual [event.edge event.phase event.rule-id])))
  (assert-result-parity expected actual)
  (local last (. events (# events)))
  (assert (= last.count 1) "summarize must report unchanged diagnostic count"))

(fn runner-observer-parity-and-phase-order []
  (fn check [target]
    (local Runner (require :constraints.runner))
    (each [_ baseline (ipairs [false {:required-rule-ids [] :entries []}])]
      (local expected (Runner.run-target target {:baseline-data baseline}))
      (local events [])
      (fn record-event [event] (table.insert events event))
      (local actual (Runner.run-target target {:baseline-data baseline
                                               :observer record-event}))
      (assert (= expected.status :violations))
      (assert (= expected.counts.total 1) "fixture should yield exactly one style diagnostic")
      (assert-result-parity expected actual)
      (assert-runner-event-schema events)
      (assert-runner-phase-order events)))
  (with-observer-target check))

(fn runner-observer-old-call-compatibility []
  (local Runner (require :constraints.runner))
  (local target {:kind :files :files [] :suites [:structure-formatting]})
  (local expected (Runner.run-target target))
  (assert-result-parity expected (Runner.run-target target {}))
  (assert-result-parity expected (Runner.run-target target {:observer nil})))

(fn runner-observer-workload-error-stays-open [module operation phase subphase]
  (fn check [target]
    (local Runner (require :constraints.runner))
    (local owner (require module))
    (local previous (. owner operation))
    (local sentinel {})
    (local events [])
    (fn fail [...] (error sentinel 0))
    (fn record-event [event] (table.insert events event))
    (tset owner operation fail)
    (local (ok err) (pcall Runner.run-target target
                           {:baseline-data {:required-rule-ids [] :entries []}
                            :observer record-event}))
    (tset owner operation previous)
    (assert (not ok))
    (assert (= err sentinel) "observer must preserve escaping workload errors")
    (local last (. events (# events)))
    (assert last "failure must retain begin")
    (assert (= last.edge :begin))
    (assert (= last.phase phase))
    (assert (= last.subphase subphase)))
  (with-observer-target check))

(fn runner-observer-error-propagates-directly []
  (local Runner (require :constraints.runner))
  (local sentinel {})
  (fn fail [_event] (error sentinel 0))
  (local (ok err) (pcall Runner.run-target {:kind :files :files []}
                         {:observer fail}))
  (assert (not ok) "observer failure must not be swallowed or made into diagnostics")
  (assert (= err sentinel)))

(fn with-synthetic-rule [rule body]
  (local Runner (require :constraints.runner))
  (local Source (require :constraints.source))
  (local Facts (require :constraints.facts))
  (local Registry (require :constraints.rules.init))
  (local discover Source.discover)
  (local extract Facts.extract)
  (local all-rules Registry.all-rules)
  (local target {:kind :files :files [] :suites []})
  (local records [{}])
  (local facts {:files records :private-token {}})
  (set Source.discover (fn [actual _observer] (assert (= actual target)) records))
  (set Facts.extract (fn [actual _observer] (assert (= actual records)) facts))
  (set Registry.all-rules (fn [] [{:id :synthetic :family :test :run rule}]))
  (local (ok result) (pcall body Runner target facts))
  (set Source.discover discover)
  (set Facts.extract extract)
  (set Registry.all-rules all-rules)
  (if ok result (error result 0)))

(fn raw-snapshot [value]
  (local snapshot {})
  (each [key item (values next value)] (tset snapshot key item))
  snapshot)

(fn assert-raw-unchanged [expected actual]
  (each [key item (values next expected)] (assert (= item (rawget actual key))))
  (each [key item (values next actual)] (assert (= item (rawget expected key)))))

(fn runner-forwards-rule-observer [returns-nil?]
  (local event {:phase :rule :subphase :synthetic :edge :begin})
  (var context nil)
  (var active? false)
  (fn rule [ctx]
    (set context ctx)
    (if active?
        (do (assert (= (type ctx.observer) :function) "rule context must forward observer")
            (assert (= (ctx.observer event) nil) "notify returns nil"))
        (assert (= (rawget ctx :observer) nil) "inactive context has no observer field"))
    (if returns-nil? nil
        [{:constraint-id :synthetic :family :test :severity :warning :message "first" :hint "fix"}
         {:constraint-id :synthetic :family :test :severity :error :message "second" :hint "fix"}]))
  (fn check [Runner target facts]
    (local target-before (raw-snapshot target))
    (local facts-before (raw-snapshot facts))
    (local files-before (raw-snapshot facts.files))
    (local expected (Runner.run-target target {:baseline-data false}))
    (assert (= context.facts facts) "Facts identity must be exact")
    (set active? true)
    (var deliveries 0)
    (fn observe [actual]
      (when actual.subphase
        (assert (= actual event) "callback receives exact event reference")
        (set deliveries (+ deliveries 1))))
    (local actual (Runner.run-target target {:baseline-data false :observer observe}))
    (assert (= deliveries 1))
    (assert (= context.facts facts))
    (assert-result-parity expected actual)
    (each [_ diagnostic (ipairs actual.diagnostics)] (assert (= diagnostic.target target)))
    (assert-raw-unchanged target-before target)
    (assert-raw-unchanged facts-before facts)
    (assert-raw-unchanged files-before facts.files))
  (with-synthetic-rule rule check))

(fn find-upvalue [owner wanted]
  (var index 1)
  (var found nil)
  (while (and (not found) (debug.getupvalue owner index))
    (local (name value) (debug.getupvalue owner index))
    (when (= name wanted) (set found {:index index :value value}))
    (set index (+ index 1)))
  (assert found (.. "missing private upvalue " wanted))
  found)

(fn runner-inactive-does-not-enter-observer-factory []
  (fn check [Runner target _facts]
    (local factory (find-upvalue Runner.run-target :make_rule_observer))
    (local sentinel {})
    (fn fail [_observer] (error sentinel 0))
    (debug.setupvalue Runner.run-target factory.index fail)
    (fn check-inactive []
      (local expected (Runner.run-target target))
      (assert-result-parity expected (Runner.run-target target {}))
      (assert-result-parity expected (Runner.run-target target {:observer nil})))
    (fn ignore-event [_event] nil)
    (local (ok err) (pcall check-inactive))
    (local (active-ok active-err) (pcall Runner.run-target target {:observer ignore-event}))
    (debug.setupvalue Runner.run-target factory.index factory.value)
    (assert ok (tostring err))
    (assert (not active-ok) "active control must enter factory spy")
    (assert (= active-err sentinel)))
  (with-synthetic-rule (fn [_ctx] nil) check))

(fn with-sentinel-hook [body]
  (local (old-hook old-mask old-count) (debug.gethook))
  (fn sentinel [] nil)
  (debug.sethook sentinel "" 7777)
  (local (ok err) (pcall body sentinel))
  (if old-hook (debug.sethook old-hook old-mask old-count) (debug.sethook nil "" 0))
  (if ok err (error err 0)))

(fn assert-sentinel-hook [sentinel]
  (local (hook mask count) (debug.gethook))
  (assert (and (= hook sentinel) (= mask "") (= count 7777))
          "previous hook must be restored before outside propagation/teardown"))

(fn runner-relays-raw-observer-error [failure timeout]
  (local second {})
  (var calls 0)
  (var ended? false)
  (fn rule [ctx]
    ;; A rule may catch a callback error, but cannot erase or replace its ownership.
    (local (ok err) (pcall ctx.observer {:subphase :synthetic}))
    (assert (not ok))
    (assert (= err failure))
    (ctx.observer {:subphase :synthetic}))
  (fn check [Runner target _facts]
    (fn observe [event]
      (when (and (= event.phase :rule) (= event.edge :end)) (set ended? true))
      (when event.subphase
        (set calls (+ calls 1))
        (error (if (= calls 1) failure second) 0)))
    (fn guarded [sentinel]
      (local (ok err) (pcall Runner.run-target target
                             {:baseline-data false :timeout-seconds timeout :observer observe}))
      (assert-sentinel-hook sentinel)
      (assert (not ok) "callback failure must escape, not become a framework result")
      (assert (= err failure) "first raw callback failure must win, including false/nil")
      (assert (= calls 2))
      (assert (not ended?) "relay must escape before top-level rule END"))
    (with-sentinel-hook guarded))
  (with-synthetic-rule rule check))

(fn runner-rule-workload-error-keeps-guard []
  (local failure {})
  (var ended? false)
  (fn observe [event]
    (when (and (= event.phase :rule) (= event.edge :end)) (set ended? true)))
  (fn check [Runner target _facts]
    (local result (Runner.run-target target {:baseline-data false :observer observe}))
    (assert (= result.status :fail))
    (assert (= result.counts.total 1))
    (assert (= (. result.diagnostics 1 :family) :framework))
    (assert ended? "ordinary rule failure still emits top-level END"))
  (with-synthetic-rule (fn [_ctx] (error failure 0)) check))

(fn runner-outer-timeout-ownership [location secondary-failure?]
  (local TestRunner (require :tests.runner))
  (local secondary {})
  (var now 0)
  (var ended? false)
  (var teardown? false)
  (fn now-ms [] now)
  (fn expire []
    (set now 120001)
    (local hook (debug.gethook))
    (assert hook)
    (hook))
  (fn rule [ctx]
    (if (= location :work) (expire) (ctx.observer {:subphase :synthetic})))
  (fn check [Runner target _facts]
    (fn observe [event]
      (when event.subphase (expire))
      (when (and (= event.phase :rule) (= event.edge :end))
        (set ended? true)
        (when secondary-failure? (error secondary 0))))
    (fn guarded [sentinel]
      (fn body []
        (local result (Runner.run-target target {:baseline-data false :observer observe}))
        (assert (= result.status :fail) "caught outer work timeout remains ordinary rule failure"))
      (fn teardown [] (assert-sentinel-hook sentinel) (set teardown? true))
      (local (ok err cleanup-errors)
        (TestRunner.run-case {:name "nested observer deadline" :fn body :teardown teardown}
                             120 nil now-ms))
      (assert-sentinel-hook sentinel)
      (assert (not ok))
      (assert (= err "test timed out after 120s: nested observer deadline")
              "original timeout latch must win over later observer errors")
      (assert teardown?)
      (assert (= (# cleanup-errors) 0))
      (assert (= ended? (= location :work)) "only caught work timeout may reach rule END"))
    (with-sentinel-hook guarded))
  (with-synthetic-rule rule check))

(table.insert tests {:name "runner forwards internal observer with complete diagnostic parity"
                     :fn #(runner-forwards-rule-observer false)})
(table.insert tests {:name "runner forwards internal observer with nil rule result parity"
                     :fn #(runner-forwards-rule-observer true)})
(table.insert tests {:name "runner nil observer never enters private relay factory"
                     :fn runner-inactive-does-not-enter-observer-factory})
(each [_ failure (ipairs [{:label :table :value {}} {:label :false :value false} {:label :nil}])]
  (each [_ mode (ipairs [{:label :unguarded} {:label :timed :timeout 60}])]
    (table.insert tests {:name (.. "runner relays first raw " failure.label " observer error " mode.label)
                         :fn #(runner-relays-raw-observer-error failure.value mode.timeout)})))
(table.insert tests {:name "runner observed ordinary rule failure retains guard semantics"
                     :fn runner-rule-workload-error-keeps-guard})
(each [_ variant (ipairs [{:location :work} {:location :work :secondary? true} {:location :observer}])]
  (table.insert tests {:name (.. "runner outer timeout ownership in " variant.location
                                (if variant.secondary? " with secondary sink failure" ""))
                       :fn #(runner-outer-timeout-ownership variant.location variant.secondary?)}))

(table.insert tests {:name "runner observer preserves results and registered phase/rule order"
                     :fn runner-observer-parity-and-phase-order})
(table.insert tests {:name "runner observer preserves old call compatibility"
                     :fn runner-observer-old-call-compatibility})
(table.insert tests {:name "runner observer leaves discovery failure open"
                     :fn #(runner-observer-workload-error-stays-open :constraints.source :discover :discover nil)})
(table.insert tests {:name "runner observer leaves facts failure open"
                     :fn #(runner-observer-workload-error-stays-open :constraints.facts :extract :facts nil)})
(table.insert tests {:name "runner observer leaves selection failure open"
                     :fn #(runner-observer-workload-error-stays-open :constraints.rules.init :all-rules :select nil)})
(table.insert tests {:name "runner observer leaves escaping rule failure open"
                     :fn #(runner-observer-workload-error-stays-open :constraints.runner :run-rule :rule nil)})
(table.insert tests {:name "runner observer leaves baseline failure open"
                     :fn #(runner-observer-workload-error-stays-open :constraints.baseline :apply :baseline nil)})
(table.insert tests {:name "runner observer leaves summary failure open"
                     :fn #(runner-observer-workload-error-stays-open :constraints.diagnostics :summary :summarize nil)})
(table.insert tests {:name "runner observer failures propagate directly"
                     :fn runner-observer-error-propagates-directly})

;; Register tests
(table.insert tests {:name "diagnostic violation normalizes fields"
                     :fn diagnostic-violation-normalizes-fields})
(table.insert tests {:name "diagnostic violation defaults severity and evidence"
                     :fn diagnostic-violation-defaults-severity-and-evidence})
(table.insert tests {:name "diagnostic violation requires constraint-id"
                     :fn diagnostic-violation-requires-constraint-id})
(table.insert tests {:name "diagnostic violation requires family"
                     :fn diagnostic-violation-requires-family})
(table.insert tests {:name "diagnostic violation requires message"
                     :fn diagnostic-violation-requires-message})
(table.insert tests {:name "diagnostic violation requires hint"
                     :fn diagnostic-violation-requires-hint})
(table.insert tests {:name "diagnostic framework-failure produces normalized diagnostic"
                     :fn diagnostic-framework-failure-produces-normalized-diagnostic})
(table.insert tests {:name "diagnostic summary counts by family"
                     :fn diagnostic-summary-counts-by-family})
(table.insert tests {:name "runner noop rule returns pass"
                     :fn runner-noop-rule-returns-pass})
(table.insert tests {:name "runner violation rule returns violations"
                     :fn runner-violation-rule-returns-violations})
(table.insert tests {:name "runner crashing rule returns fail"
                     :fn runner-crashing-rule-returns-fail})
(table.insert tests {:name "runner status precedence"
                     :fn runner-status-precedence})
(table.insert tests {:name "runner main prints JSON and exits zero on pass"
                     :fn runner-main-prints-json-and-exits-zero-on-pass})
(table.insert tests {:name "runner main prints JSON and exits nonzero on violations"
                      :fn runner-main-prints-json-and-exits-nonzero-on-violations})
(table.insert tests {:name "runner main summary pass is concise"
                     :fn runner-main-summary-pass-is-concise})
(table.insert tests {:name "runner main summary violations include diagnostic and rerun"
                     :fn runner-main-summary-violations-include-diagnostic-and-rerun})
(table.insert tests {:name "runner main global argv summary parses output flag"
                     :fn runner-main-global-argv-summary-parses-output-flag})
(table.insert tests {:name "runner main handles nil opts (runtime convention)"
                     :fn runner-main-handles-nil-opts})
(table.insert tests {:name "runner timeout produces interrupted status"
                     :fn runner-timeout-produces-interrupted})
(table.insert tests {:name "runner interrupted precedence over fail"
                     :fn runner-interrupted-precedence-over-fail})

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "constraints-runner"
                       :tests tests})))

{:name "constraints-runner"
 :tests tests
 :main main}
