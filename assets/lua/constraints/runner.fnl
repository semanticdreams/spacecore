;; Runner module for Fennel constraints.
;; Aggregates rule execution, status precedence, and JSON output.

(local Baseline (require :constraints.baseline))
(local Diagnostics (require :constraints.diagnostics))
(local Facts (require :constraints.facts))
(local RuleRegistry (require :constraints.rules.init))
(local Source (require :constraints.source))
(local Targets (require :constraints.targets))
(local json (require :json))

(local M {})

;; Status precedence: :interrupted > :fail > :violations > :pass
(local status-precedence {:interrupted 4
                          :fail 3
                          :violations 2
                          :pass 1})

(fn worse-status [a b]
  "Return the worse (higher precedence) of two statuses."
  (let [pa (or (. status-precedence a) 0)
        pb (or (. status-precedence b) 0)]
    (if (>= pa pb) a b)))

(fn make-error-handler [diagnostics rule-id target timed-out]
  "Build an xpcall error handler that differentiates crash vs interrupt."
  (fn [err-obj]
    (if (. timed-out :flag)
        (let [d (Diagnostics.framework-failure
                  {:constraint-id rule-id
                   :family :framework
                   :message (.. "rule interrupted: " (tostring err-obj))
                   :evidence {}
                   :target target
                   :hint "check the rule for hangs or infinite loops"})]
          (tset d :interrupted true)
          (table.insert diagnostics d))
        (let [tb (if _G.debug
                     (_G.debug.traceback err-obj 3)
                     (tostring err-obj))]
          (table.insert diagnostics
            (Diagnostics.framework-failure
              {:constraint-id rule-id
               :family :framework
               :message (.. "rule crashed: " (tostring err-obj))
               :evidence {:traceback tb}
               :target target
                :hint "check the rule implementation for errors"}))))))

(fn execute-guarded [diagnostics rule target on-error]
  "Execute rule within xpcall and collect diagnostics."
  (let [(ok result) (xpcall (fn [] (rule target)) on-error)]
    (when (and ok result (= (type result) :table))
      (if (. result :constraint-id)
          (table.insert diagnostics result)
          (each [_ d (ipairs result)]
            (table.insert diagnostics d))))))

(fn make-timeout-hook [started-at timeout-seconds timed-out]
  "Build a debug.sethook callback that errors on timeout."
  (fn []
    (when (>= (- (os.clock) started-at) timeout-seconds)
      (tset timed-out :flag true)
      (error (.. "rule timed out after " timeout-seconds "s") 2))))

(fn M.run-rule [rule target timeout-seconds rule-id]
  "Run a single rule function against a target using xpcall.
  Returns nil on pass, or a list of diagnostics on failure/crash/interrupt.
  Uses debug.traceback for crash diagnostics, debug.sethook for timeouts."
  (let [diagnostics []
        rule-id (or rule-id
                    (and (= (type rule) :table) (. rule :constraint-id))
                    :unknown-rule)
        timed-out {:flag false}
        on-error (make-error-handler diagnostics rule-id target timed-out)]
    (if (and timeout-seconds (> timeout-seconds 0)
             _G.debug _G.debug.sethook _G.debug.gethook)
        ;; Timeout-enabled execution
        (let [debug-lib _G.debug
              started-at (os.clock)
              (old-hook old-mask old-count) (debug-lib.gethook)
              hook (make-timeout-hook started-at timeout-seconds timed-out)]
          (debug-lib.sethook hook "" 10000)
          (execute-guarded diagnostics rule target on-error)
          ;; Restore original hook immediately after rule completes
          (debug-lib.sethook old-hook old-mask old-count))
        ;; No timeout — simple execution
        (execute-guarded diagnostics rule target on-error))
    (if (= (# diagnostics) 0) nil diagnostics)))

(fn compute-status [diagnostics]
  "Compute the worst-case status from a list of diagnostics."
  (var status :pass)
  (each [_ d (ipairs diagnostics)]
    (if (. d :interrupted)
        (set status (worse-status status :interrupted))
        (= d.family :framework)
        (set status (worse-status status :fail))
        (set status (worse-status status :violations))))
  status)

(fn M.run [opts]
  "Run a set of rules against a target.
  opts: {:rules [] :target <target> :timeout-seconds <int|nil>
         :baseline-data <table|nil|false>}
  Rules may be functions, or tables with :fn or :run (callable) and :id/:constraint-id.
  Defaults to loading the versioned baseline data; pass :baseline-data false to skip.
  Returns {:status :pass|:violations|:fail|:interrupted
           :counts {:total <int> :by-family <table> :by-severity <table>}
           :diagnostics []}"
  (let [rules (or opts.rules [])
        target (or opts.target {:kind :repo :name "default"})
        all-diagnostics []
        present-rule-ids []
        ;; Default to loading versioned baseline data; false to skip; table to inject
        baseline-data (if (= false opts.baseline-data)
                         nil
                         (or opts.baseline-data (Baseline.load)))]
    (each [_ rule (ipairs rules)]
      ;; Resolve the callable and rule id from the rule entry
      (let [rule-fn (if (and (= (type rule) :table) (. rule :fn))
                       (. rule :fn)
                       (and (= (type rule) :table) (. rule :run))
                       (. rule :run)
                       rule)
            rule-id (or (and (= (type rule) :table)
                             (or (. rule :id) (. rule :constraint-id)))
                        :unknown-rule)]
        (table.insert present-rule-ids rule-id)
        (let [result (M.run-rule rule-fn target opts.timeout-seconds rule-id)]
          (when result
            ;; result is a list of diagnostics
            (each [_ d (ipairs result)]
              ;; Ensure every diagnostic identifies the target
              (when (not (. d :target))
                (tset d :target target))
              (table.insert all-diagnostics d))))))
    ;; Apply baseline policy after all rules run, if baseline data is available
    (if baseline-data
        (let [baseline-result (Baseline.apply all-diagnostics baseline-data present-rule-ids)
              ;; Replace all-diagnostics with the baseline-filtered list
              filtered-diagnostics baseline-result.diagnostics]
          ;; Append baseline diagnostics (worsened, stale, missing-required)
          (each [_ bd (ipairs baseline-result.baseline-diagnostics)]
            (when (not (. bd :target))
              (tset bd :target target))
            (table.insert filtered-diagnostics bd))
          ;; Recompute status from the final filtered diagnostics
          ;; so that exact-match-suppressed diagnostics yield :pass when appropriate
          (let [final-status (compute-status filtered-diagnostics)
                counts (Diagnostics.summary final-status filtered-diagnostics)]
            {:status final-status
             :counts counts
             :diagnostics filtered-diagnostics}))
        ;; No baseline data — compute status from unfiltered diagnostics
        (do
          (local final-status (compute-status all-diagnostics))
          (local counts (Diagnostics.summary final-status all-diagnostics))
          {:status final-status
           :counts counts
           :diagnostics all-diagnostics}))))


(fn table-contains? [tbl val]
  "Check whether a sequential table contains a value."
  (var found false)
  (each [_ v (ipairs tbl)]
    (when (= v val)
      (set found true)))
  found)

(fn rule-applicable-to-target? [rule target target-suites]
  (assert rule "rule is required")
  (assert target "target is required")
  (local rule-targets (or rule.targets [:repo :unit :app :files]))
  (local rule-family (or rule.family ""))
  (and (table-contains? rule-targets target.kind)
       (or (= (length target-suites) 0)
           (table-contains? target-suites rule-family))))

(fn target-baseline-data [baseline-data target applicable-rule-ids]
  "Scope baseline policy to the target being analyzed.
  Repo targets enforce reviewed entries and all configured required ids against
  executed rules. Non-repo targets still enforce required ids for rules that are
  applicable to that target, but repo-specific baseline entries do not become
  stale/worsened for unrelated external files."
  (if (= target.kind :repo)
      baseline-data
      {:required-rule-ids applicable-rule-ids
       :entries []}))

(fn M.run-target [target opts]
  "Execute the full constraint pipeline for a target:
   1. Discover source files
   2. Extract static facts
   3. Select applicable rules from the registry
   4. Execute each rule independently with fact context
   5. Apply baseline policy
   opts: {:baseline-data <table|nil|false> :timeout-seconds <int|nil>
          :observer <(event) -> nil|nil>}
  Returns {:status :pass|:violations|:fail|:interrupted
           :counts {:total <int> :by-family <table> :by-severity <table>}
           :diagnostics []}"
  (local o (or opts {}))
  (local observer o.observer)
  ;; 1. Discover source files
  (when observer (observer {:edge :begin :phase :discover}))
  (local file-records (Source.discover target observer))
  (when observer (observer {:edge :end :phase :discover :count (# file-records)}))
  ;; 2. Extract static facts
  (when observer (observer {:edge :begin :phase :facts}))
  (local fact-db (Facts.extract file-records observer))
  (when observer (observer {:edge :end :phase :facts :count (# fact-db.files)}))
  ;; 3. Get all rules from registry and filter by target kind & suite
  (when observer (observer {:edge :begin :phase :select}))
  (local all-rules (RuleRegistry.all-rules))
  (local target-suites (or target.suites []))
  (local applicable-rules [])
  (local applicable-rule-ids [])
  (each [_ rule (ipairs all-rules)]
    (when (rule-applicable-to-target? rule target target-suites)
      (table.insert applicable-rules rule)
      (table.insert applicable-rule-ids (or rule.id rule.constraint-id "unknown-rule"))))
  (when observer (observer {:edge :end :phase :select :count (# applicable-rules)}))
  ;; 4. Execute each applicable rule with fact context
  (local all-diagnostics [])
  (local present-rule-ids [])
  (local ctx {:facts fact-db})
  (each [index rule (ipairs applicable-rules)]
    (let [rule-id (or rule.id rule.constraint-id "unknown-rule")
          rule-fn (or rule.run rule.fn)]
      (table.insert present-rule-ids rule-id)
      ;; Wrap rule-fn so it discards the target arg that run-rule passes
      ;; and calls the real rule function with the fact context instead.
      (when observer (observer {:edge :begin :phase :rule :rule-id rule-id :index index}))
      (let [result (M.run-rule (fn [_ignored-target] (rule-fn ctx))
                                target
                                o.timeout-seconds
                                rule-id)]
        (when result
          (each [_ d (ipairs result)]
            ;; Ensure every diagnostic identifies the target
            (when (not (. d :target))
              (tset d :target target))
            (table.insert all-diagnostics d)))
        (when observer
          (observer {:edge :end :phase :rule :rule-id rule-id :index index
                     :count (if result (# result) 0)})))))
  ;; 5. Apply baseline policy
  (when observer (observer {:edge :begin :phase :baseline}))
  (let [baseline-data (if (= false o.baseline-data)
                          nil
                          (or o.baseline-data (Baseline.load)))]
    (local final-diagnostics
      (if baseline-data
        (do
          (local scoped-baseline-data (target-baseline-data baseline-data target applicable-rule-ids))
          (local baseline-result (Baseline.apply all-diagnostics
                                                 scoped-baseline-data
                                                 present-rule-ids))
          (local filtered-diagnostics baseline-result.diagnostics)
          ;; Append baseline diagnostics (worsened, stale, missing-required)
          (each [_ bd (ipairs baseline-result.baseline-diagnostics)]
            (when (not (. bd :target))
              (tset bd :target target))
            (table.insert filtered-diagnostics bd))
           filtered-diagnostics)
        all-diagnostics))
    (when observer (observer {:edge :end :phase :baseline :count (# final-diagnostics)}))
    (when observer (observer {:edge :begin :phase :summarize}))
    (local final-status (compute-status final-diagnostics))
    (local counts (Diagnostics.summary final-status final-diagnostics))
    (local result {:status final-status :counts counts :diagnostics final-diagnostics})
    (when observer (observer {:edge :end :phase :summarize :count counts.total}))
    result))

(local Output (require :tools/validation-output))

(fn normalized-global-argv []
  (local source (if _G.arg _G.arg []))
  (local start (if (= (. source 1) "--") 2 1))
  (local result [])
  (var index start)
  (while (<= index (# source))
    (table.insert result (. source index))
    (set index (+ index 1)))
  result)

(fn M.main [opts-or-argv]
  "Entry point for the constraints runner.
  Supports two calling conventions:
  1. New argv-based: (Runner.main [\"--target\" \"repo\"]) or nil — runs full pipeline.
  2. Old opts-based: (Runner.main {:rules [] :target ...}) — backwards compatible.
  Tolerates nil (runtime's zero-argument entry-point convention).
  When running with nil/empty argv, defaults to repo target."
  (local arg (or opts-or-argv {}))
  (if (and (= (type arg) :table) (. arg :rules))
      ;; Old interface: {:rules [] :target ... :print fn :exit fn :baseline-data tbl}
       (do
         (local o arg)
         (local print-fn (or o.print print))
         (local exit-fn (or o.exit os.exit))
         (local output (if o.output o.output :json))
         (local rules (or o.rules []))
         (local target (or o.target {:kind :repo :name "default"}))
         (local result (M.run {:rules rules
                               :target target
                               :baseline-data o.baseline-data}))
         (print-fn (if (= output :summary)
                       (Output.constraints-summary result)
                       (json.dumps result)))
         (if (= result.status :pass)
             (exit-fn 0)
             (exit-fn 1)))
      ;; New interface: argv (sequential table) or nil → full pipeline
       (do
         (local argv (if opts-or-argv
                         (if (= (type arg) :table) arg [])
                         (normalized-global-argv)))
         ;; Check if old-style injected print/exit are present
         (local print-fn (or (. arg :print) print))
         (local exit-fn (or (. arg :exit) os.exit))
         (local parsed (Output.split-output-argv argv :json))
         (local result (if parsed.error
                           {:status :fail
                            :counts {:total 1 :by-family {:input 1} :by-severity {:error 1}}
                            :diagnostics [{:constraint-id "constraints.runner/output"
                                           :family "input"
                                           :severity :error
                                           :message parsed.error
                                           :hint "Use --output json or --output summary."}]}
                           (do
                             (local target (Targets.resolve parsed.argv {}))
                             (M.run-target target {}))))
         (print-fn (if (= parsed.output :summary)
                       (Output.constraints-summary result)
                       (json.dumps result)))
         (if (= result.status :pass)
             (exit-fn 0)
             (exit-fn 1)))))

M
