;; Tests for RuleRegistry and default repo execution.

(local tests [])

(local fs (require :fs))
(fn asset-lua-root []
  (local env (os.getenv "SPACE_ASSETS_PATH"))
  (local rt (require :runtime))
  (local assets-path (if env env rt.assets-path rt.assets-path "assets"))
  (fs.join-path assets-path "lua"))

(var temp-counter 0)
(local temp-root (fs.join-path "/tmp/opencode" "constraints-default-run-test"))

(fn temp-dir-name []
  (set temp-counter (+ temp-counter 1))
  (fs.join-path temp-root (.. "test-" (os.time) "-" temp-counter)))

(fn with-temp-dir [f]
  (local dir (temp-dir-name))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (fs.create-dirs dir)
  (local (ok result) (pcall f dir))
  (fs.remove-all dir)
  (if ok result (error result)))

(fn write-fixture [dir]
  (local path (fs.join-path dir "bad-style.fnl"))
  (local lines [])
  (for [i 1 1201]
    (table.insert lines (.. "(local x" i " " i ")")))
  (fs.write-file path (.. (table.concat lines "\n") "\n"))
  path)

(fn write-clean-fixture [dir]
  (local path (fs.join-path dir "clean.fnl"))
  (fs.write-file path "(local x 1)\nx\n")
  path)

(fn missing-required? [diagnostic]
  (assert diagnostic "diagnostic is required")
  (or diagnostic.missing-required
      (and diagnostic.constraint-id
           (= diagnostic.family "baseline")
           (string.find diagnostic.message "required constraint missing" 1 true))))

(fn has-constraint-id? [diagnostics id]
  (var found false)
  (each [_ d (ipairs diagnostics)]
    (when (= d.constraint-id id)
      (set found true)))
  found)

(fn baseline-diagnostic? [diagnostic]
  (= diagnostic.family "baseline"))

(fn assert-non-repo-target-runs-static-rules-with-default-baseline [kind]
  (assert kind "target kind is required")
  (local Runner (require :constraints.runner))
  (with-temp-dir (fn [dir]
    (local file-path (write-fixture dir))
    (local target (if (= kind :files)
                    {:kind :files
                     :name "files-fixture"
                     :roots []
                     :files [file-path]
                     :module-roots []
                     :suites [:scene-sandbox :lifecycle :test-isolation :layout-rendering :structure-formatting]}
                    {:kind kind
                     :name (.. (tostring kind) "-fixture")
                     :roots [dir]
                     :files []
                     :module-roots [dir]
                     :suites [:scene-sandbox :lifecycle :test-isolation :layout-rendering :structure-formatting]}))
    (local result (Runner.run-target target {}))
    (each [_ d (ipairs result.diagnostics)]
      (assert (not (missing-required? d))
              (.. "non-repo target should not emit baseline.required-rule-missing; got "
                  (or d.constraint-id "nil") " " (or d.message ""))))
    (assert (has-constraint-id? result.diagnostics "structure.max-module-length")
            (.. (tostring kind) " target should execute static structure rules")))))

(fn assert-clean-non-repo-target-default-baseline-passes [kind]
  (assert kind "target kind is required")
  (local Runner (require :constraints.runner))
  (with-temp-dir (fn [dir]
    (local file-path (write-clean-fixture dir))
    (local target (if (= kind :files)
                    {:kind :files
                     :name "clean-files-fixture"
                     :roots []
                     :files [file-path]
                     :module-roots []
                     :suites [:scene-sandbox :lifecycle :test-isolation :layout-rendering :structure-formatting]}
                    {:kind kind
                     :name (.. "clean-" (tostring kind) "-fixture")
                     :roots [dir]
                     :files []
                     :module-roots [dir]
                     :suites [:scene-sandbox :lifecycle :test-isolation :layout-rendering :structure-formatting]}))
    (local result (Runner.run-target target {}))
    (assert (= result.status :pass)
            (.. (tostring kind) " clean target should pass with default baseline, got "
                (tostring result.status)))
    (each [_ d (ipairs result.diagnostics)]
      (assert (not (baseline-diagnostic? d))
              (.. "clean non-repo target should not emit baseline diagnostics; got "
                  (or d.constraint-id "nil") " " (or d.message "")))))))

;; --- RuleRegistry tests ---

(fn rule-registry-all-rules-returns-all-required-ids []
  "Prove that RuleRegistry.all-rules returns every id in baseline-data.required-rule-ids."
  (local RuleRegistry (require :constraints.rules.init))
  (local BaselineData (require :constraints.baseline-data))
  (local rules (RuleRegistry.all-rules))
  (assert (= (type rules) "table") "all-rules should return a table")
  (assert (> (# rules) 0) "should return at least one rule")

  ;; Collect all rule IDs from the registry
  (local registry-ids {})
  (each [_ rule (ipairs rules)]
    (local id (or rule.id rule.constraint-id "unknown"))
    (tset registry-ids id true))

  ;; Verify every required rule ID is present
  (each [_ required-id (ipairs BaselineData.required-rule-ids)]
    (assert (. registry-ids required-id)
            (.. "required rule not in registry: " required-id)))

  ;; Verify deterministic family order:
  ;; scene-sandbox first, lifecycle second, test-isolation third,
  ;; layout-rendering fourth, structure-formatting last.
  (var last-family nil)
  (local family-order [])
  (each [_ rule (ipairs rules)]
    (local fam (or rule.family ""))
    (when (or (= (# family-order) 0)
              (not= fam (. family-order (# family-order))))
      (table.insert family-order fam)))
  (assert (>= (# family-order) 5) "expected at least 5 families")
  (assert (or (= (. family-order 1) "scene-sandbox")
              (string.find (. family-order 1) "scene" 1 true))
          (.. "first family should be scene-sandbox, got " (. family-order 1)))
  (assert (= (. family-order 5) "structure-formatting")
          (.. "last family should be structure-formatting, got " (. family-order 5))))

(fn rule-registry-all-rules-are-well-formed []
  "Each rule entry must have :id, :family, :targets, :kind, :run, and :fn."
  (local RuleRegistry (require :constraints.rules.init))
  (local rules (RuleRegistry.all-rules))
  (each [_ rule (ipairs rules)]
    (assert (or rule.id rule.constraint-id)
            (.. "rule missing id: " (tostring (or rule.id rule.constraint-id "nil"))))
    (assert rule.family (.. "rule missing family: " (or rule.id "nil")))
    (assert rule.targets (.. "rule missing targets: " (or rule.id "nil")))
    (assert rule.kind (.. "rule missing kind: " (or rule.id "nil")))
    (assert rule.run (.. "rule missing run: " (or rule.id "nil")))
    (assert rule.fn (.. "rule missing fn: " (or rule.id "nil")))
    ;; Verify target is a known target kind
    (each [_ tgt (ipairs rule.targets)]
      (local allowed {:repo true :unit true :app true :files true})
      (assert (. allowed tgt) (.. "unknown target kind: " (tostring tgt))))))

;; --- Runner.run-target tests ---

(fn runner-run-target-returns-structured-result []
  "Prove run-target returns a proper result with status, counts, and diagnostics."
  (local Runner (require :constraints.runner))
  ;; Build a files target pointing to the minimal test fixture
  (local fixture-path (fs.absolute (fs.join-path (asset-lua-root) "tests" "data" "constraint-fixture.fnl")))
  (local target {:kind :files
                 :name "constraint-fixture"
                 :roots []
                 :files [fixture-path]
                  :module-roots []
                  :suites [:scene-sandbox :lifecycle :test-isolation :layout-rendering :structure-formatting]})
  (local result (Runner.run-target target {:baseline-data false}))
  ;; Verify result structure
  (assert (= (type result) "table") "result should be a table")
  (assert result.status (.. "result should have status, got " (tostring result)))
  (assert result.counts (.. "result should have counts, got " (tostring result)))
  (assert result.diagnostics (.. "result should have diagnostics, got " (tostring result)))
  (assert (= (type result.diagnostics) "table") "diagnostics should be a table")
  ;; Verify counts structure
  (assert (>= result.counts.total 0) "counts.total should be non-negative")
  (assert result.counts.by-family (.. "counts should have by-family, got " (tostring result)))
  (assert result.counts.by-severity (.. "counts should have by-severity, got " (tostring result))))

(fn runner-run-target-diagnostics-include-target-metadata []
  "Prove that every diagnostic from run-target includes target.kind and target.name."
  (local Runner (require :constraints.runner))
  ;; Use a minimal files target — any diagnostics produced must carry target metadata
  (local fixture-path (fs.absolute (fs.join-path (asset-lua-root) "tests" "data" "constraint-fixture.fnl")))
  (local target {:kind :files
                 :name "metadata-test-target"
                 :roots []
                 :files [fixture-path]
                 :module-roots []
                 :suites [:scene-sandbox :lifecycle :test-isolation :layout-rendering :structure-formatting]})
  (local result (Runner.run-target target {:baseline-data false}))
  ;; Check that all diagnostics include target metadata
  (each [_ d (ipairs result.diagnostics)]
    (assert (. d :target) (.. "diagnostic missing target, constraint-id: " (or d.constraint-id "nil")))
    (if (. d :target)
        (do
          (assert (. d.target :kind)
                  (.. "diagnostic target missing kind, constraint-id: " (or d.constraint-id "nil")))
          (assert (. d.target :name)
                  (.. "diagnostic target missing name, constraint-id: " (or d.constraint-id "nil")))))))

(fn runner-run-target-explicit-files-target-works []
  "Prove that a non-repo files target can run through the same pipeline."
  (local Runner (require :constraints.runner))
  (local fixture-path (fs.absolute (fs.join-path (asset-lua-root) "tests" "data" "constraint-fixture.fnl")))
  (local target {:kind :files
                 :name "explicit-files-test"
                 :roots []
                 :files [fixture-path]
                 :module-roots []
                 :suites [:scene-sandbox :lifecycle :test-isolation :layout-rendering :structure-formatting]})
  (local result (Runner.run-target target {:baseline-data false}))
  ;; Should not crash; the fixture file is well-formed Fennel
  (assert (= (type result) "table") "run-target should return a table")
  (assert result.status "run-target should return a status")
  (assert (or (= result.status :pass)
              (= result.status :violations)
              (= result.status :fail)
              (= result.status :interrupted))
           (.. "status should be one of :pass, :violations, :fail, :interrupted, got "
               (tostring result.status))))

(fn runner-run-target-files-default-baseline-runs-static-rules []
  "Files targets should run applicable static rules under the default baseline
  and should not fail with baseline.required-rule-missing false positives."
  (assert-non-repo-target-runs-static-rules-with-default-baseline :files))

(fn runner-run-target-unit-default-baseline-runs-static-rules []
  "Unit targets should run applicable static rules under the default baseline
  and should not fail with baseline.required-rule-missing false positives."
  (assert-non-repo-target-runs-static-rules-with-default-baseline :unit))

(fn runner-run-target-app-default-baseline-runs-static-rules []
  "App targets should run applicable static rules under the default baseline
  and should not fail with baseline.required-rule-missing false positives."
  (assert-non-repo-target-runs-static-rules-with-default-baseline :app))

(fn runner-run-target-clean-files-default-baseline-has-no-false-baseline []
  "A clean files target should pass with the default baseline and must not be
  blocked by unrelated repo stale/worsened baseline entries."
  (assert-clean-non-repo-target-default-baseline-passes :files))

(fn runner-run-target-clean-unit-default-baseline-has-no-false-baseline []
  "A clean unit target should pass with the default baseline and must not be
  blocked by unrelated repo stale/worsened baseline entries."
  (assert-clean-non-repo-target-default-baseline-passes :unit))

(fn runner-run-target-clean-app-default-baseline-has-no-false-baseline []
  "A clean app target should pass with the default baseline and must not be
  blocked by unrelated repo stale/worsened baseline entries."
  (assert-clean-non-repo-target-default-baseline-passes :app))

(fn default-baseline-does-not-false-missing-required []
  "Prove that the default baseline does not report missing-required diagnostics
  for rules that exist in the registry, when all rule families are active.
  Uses a small temp repo to keep execution fast."
  (local Runner (require :constraints.runner))
  (local RuleRegistry (require :constraints.rules.init))
  (local BaselineData (require :constraints.baseline-data))
  ;; Collect all rule IDs from the registry
  (local all-rules (RuleRegistry.all-rules))
  (local registry-ids {})
  (each [_ rule (ipairs all-rules)]
    (local id (or rule.id rule.constraint-id "unknown"))
    (tset registry-ids id true))
  ;; Static check: every baseline-data required-rule-id must be in registry
  (each [_ required-id (ipairs BaselineData.required-rule-ids)]
    (assert (. registry-ids required-id)
            (.. "baseline-data requires \"" required-id
                "\" but it is not in the rule registry")))
  ;; Dynamic check: run a small repo target with all suites and default
  ;; baseline.  No registry-known rule should produce a missing-required
  ;; diagnostic.
  (with-temp-dir (fn [dir]
    (write-clean-fixture dir)
    (local target {:kind :repo
                   :name "small-repo-required-check"
                   :roots [dir]
                   :files []
                   :module-roots [dir]
                   :suites [:scene-sandbox :lifecycle :test-isolation :layout-rendering :structure-formatting]})
    (local result (Runner.run-target target {}))
    (each [_ d (ipairs result.diagnostics)]
      (when (and (. d :missing-required) d.constraint-id)
        (assert (not (. registry-ids d.constraint-id))
                (.. "required rule \"" d.constraint-id "\" should not be missing — "
                    "it is in the registry but was filtered out")))))))

(fn runner-run-target-repo-required-filtered-rule-is-missing []
  "Repo required-rule validation must use executed/applicable ids, not every
  registered id, so filtering out a required repo rule fails loudly."
  (local Runner (require :constraints.runner))
  (with-temp-dir (fn [dir]
    (write-clean-fixture dir)
    (local target {:kind :repo
                   :name "repo-filter-regression"
                   :roots [dir]
                   :files []
                   :module-roots [dir]
                   :suites [:lifecycle]})
    (local baseline-data {:required-rule-ids ["structure.style-doctrine"]
                          :entries []})
    (local result (Runner.run-target target {:baseline-data baseline-data}))
    (var found-missing false)
    (each [_ d (ipairs result.diagnostics)]
      (when (and d.missing-required
                 (= d.constraint-id "structure.style-doctrine"))
        (set found-missing true)))
    (assert found-missing
            "repo target should report baseline.required-rule-missing when a required rule is filtered out"))))

(fn write-progress-line [line]
  (local (written write-error) (io.write line "\n"))
  (assert written write-error)
  (local (flushed flush-error) (io.flush))
  (assert flushed flush-error)
  nil)

(fn full-repo-observer [raw-timings now-ms write]
  ;; No environment selector for detail. First experiment is phase-first only.
  (local detail-phase nil)
  (when (= raw-timings "1")
    ((. (require :tests.constraint-progress) :create) {: now-ms : write : detail-phase})))

(fn runner-run-target-with-repo-target-runs-full-pipeline []
  "Prove that run-target with a repo target discovers files, extracts facts,
  runs rules, and applies baseline — returns a structured, non-empty result."
  (local Runner (require :constraints.runner))
  (local lua-dir (fs.absolute (asset-lua-root)))
  (local target {:kind :repo
                 :name "repo"
                 :roots [lua-dir]
                 :files []
                 :module-roots [lua-dir]
                 :suites [:scene-sandbox :lifecycle :test-isolation :layout-rendering :structure-formatting]})
  (local observer (full-repo-observer (os.getenv "SPACE_TEST_TIMINGS")
                                    (. (require :sysinfo) :now-ms) write-progress-line))
  (local result (Runner.run-target target {:baseline-data false : observer}))
  ;; Should complete without crash; the real repo will have violations.
  (assert (= (type result) "table") "run-target should return a table")
  (assert result.status "run-target should return a status")
  (assert (>= result.counts.total 0) "counts.total should be non-negative")
  ;; The real repo should produce some diagnostics (our codebase has violations)
  (assert (> result.counts.total 0) "repo target should produce diagnostics")
  ;; Verify diagnostics include actual file paths and constraint-ids
  (var has-file false)
  (var has-constraint-id false)
  (each [_ d (ipairs result.diagnostics)]
    (when (and d.file (> (length d.file) 0)) (set has-file true))
    (when (and d.constraint-id (> (length d.constraint-id) 0)) (set has-constraint-id true)))
  (assert has-file "at least one diagnostic should have a file")
  (assert has-constraint-id "at least one diagnostic should have a constraint-id"))

;; --- Runner.main argv tests ---

(fn default-target-suites-match-rule-families []
  "Prove that all registry rule families are represented in the default target
  suites so that no required rule is filtered out before execution."
  (local RuleRegistry (require :constraints.rules.init))
  (local Targets (require :constraints.targets))
  (local BaselineData (require :constraints.baseline-data))
  ;; Resolve the default repo target — same path Runner.main nil-argv takes.
  (local target (Targets.resolve [] {}))
  (local target-suites (or target.suites []))
  ;; Collect all unique family names from the registry
  (local registry-families {})
  (local all-rules (RuleRegistry.all-rules))
  (each [_ rule (ipairs all-rules)]
    (tset registry-families rule.family true))
  ;; Every target suite name should match a real rule family
  (each [_ suite (ipairs target-suites)]
    (assert (. registry-families suite)
            (.. "target suite \"" suite "\" should match a rule family")))
  ;; Every registry family should be in the target suites
  (each [fam _ (pairs registry-families)]
    (var found false)
    (each [_ suite (ipairs target-suites)]
      (when (= suite fam) (set found true)))
    (assert found (.. "rule family \"" fam "\" should be in default target suites"))))

(fn required-rules-registry-consistency []
  "Prove baseline-data required-rule-ids all exist in the rule registry
  without executing the pipeline.  The dynamic missing-required check is
  covered by default-baseline-does-not-false-missing-required."
  (local RuleRegistry (require :constraints.rules.init))
  (local BaselineData (require :constraints.baseline-data))
  (local rules (RuleRegistry.all-rules))
  (local registry-ids {})
  (each [_ rule (ipairs rules)]
    (local id (or rule.id rule.constraint-id "unknown"))
    (tset registry-ids id true))
  (each [_ required-id (ipairs BaselineData.required-rule-ids)]
    (assert (. registry-ids required-id)
            (.. "baseline-data requires \"" required-id
                "\" but it is not in the rule registry"))))

(fn bounded-str [v]
  "Return tostring(v) truncated to 120 chars with ellipsis if longer."
  (local raw (tostring v))
  (if (> (length raw) 120)
      (.. (string.sub raw 1 120) "...")
      raw))

(fn format-diag-entry [i d]
  "Format a single diagnostic table entry as a bounded string."
  (local msg-str (if (. d :message) (.. " msg=" (bounded-str (. d :message))) ""))
  (local hint-str (if (. d :hint) (.. " hint=" (bounded-str (. d :hint))) ""))
  (local fam (bounded-str (if (. d :family) (. d :family) "?")))
  (local sev (bounded-str (if (. d :severity) (. d :severity) "?")))
  (local fil (bounded-str (if (. d :file) (. d :file) "?")))
  (local cid (bounded-str (. d :constraint-id)))
  (.. "  [" i "] " cid
      " family=" fam
      " severity=" sev
      " file=" fil
      msg-str hint-str))

(fn diag-first5-impl [diags]
  "Collect first 5 diagnostic entries into a string, bounded."
  (local lines [])
  (var i 0)
  (each [_ d (ipairs diags) &until (>= i 5)]
    (set i (+ i 1))
    (if (= (type d) :table)
        (table.insert lines (format-diag-entry i d))
        (table.insert lines (.. "  [" i "] (malformed: " (bounded-str d) ")"))))
  (table.concat lines "\n"))

(fn diag-sample-first-5 [diags]
  "Return a bounded string from the first 5 diagnostic entries, or tostring if not a table."
  (if (= (type diags) :table)
      (diag-first5-impl diags)
      (tostring diags)))

(fn runner-main-argv-defaults-to-repo []
  "Runner.main() with nil argv should default to repo target and wire print/exit correctly.
  The run-target pipeline is stubbed to avoid redundant full-repo execution."
  (local Runner (require :constraints.runner))
  (local previous-run-target Runner.run-target)
  (var printed nil)
  (var exit-code nil)
  (local fake-print (fn [msg] (set printed msg)))
  (local fake-exit (fn [code] (set exit-code code)))
  (tset Runner :run-target (fn [_target _opts]
                             {:status :pass
                              :counts {:total 0 :by-family {} :by-severity {}}
                              :diagnostics []}))
  (local (ok err) (pcall #(Runner.main {:print fake-print :exit fake-exit})))
  (tset Runner :run-target previous-run-target)
  (assert ok (.. "Runner.main with stubbed pipeline should not crash, got: " (tostring err)))
  (assert printed "expected JSON output from default repo execution")
  (local json (require :json))
  (local (ok-parsed parsed) (pcall json.loads printed))
  (assert ok-parsed (.. "expected valid JSON, got: " (tostring printed)))
  (assert (= (type parsed) "table") "parsed JSON should be a table")
  (assert parsed.status (.. "parsed JSON should have status, got: " (tostring printed)))
  (assert parsed.counts (.. "parsed JSON should have counts, got: " (tostring printed)))
  (assert parsed.diagnostics (.. "parsed JSON should have diagnostics, got: " (tostring printed)))
  (assert exit-code "expected exit to be called")
  ;; Build diagnostic summary when assertion fails.
  (local diag-header (.. "exit-code=" (tostring exit-code)
                         " status=" (tostring parsed.status)))
  (local count-tbl (if (= (type parsed.counts) :table) parsed.counts nil))
  (local diag-total (.. " total=" (tostring (or (and count-tbl count-tbl.total) "?"))))
  (local diag-sample (diag-sample-first-5 parsed.diagnostics))
   (assert (= exit-code 0)
           (.. "repo target with stubbed pass should exit zero\n"
               diag-header diag-total "\n" diag-sample)))

;; Test-only constraint progress regressions; clocks and sinks are synthetic.
(fn progress-harness [detail-phase ending]
  (local (available Progress) (pcall require :tests.constraint-progress))
  (assert available "test-only constraint progress writer is required")
  (local newline (if (= ending nil) "\n" ending))
  (local state {:now 100 :lines [] :serialized [] :clock-calls 0})
  (fn now-ms []
    (set state.clock-calls (+ state.clock-calls 1))
    state.now)
  (fn write [line]
    (table.insert state.lines line)
    (table.insert state.serialized (.. line newline)))
  (local observer (Progress.create {: now-ms : write : detail-phase}))
  {: state : observer})

(fn contains? [text part] (not= (string.find text part 1 true) nil))

(fn progress-emits-immediate-monotonic-edges []
  (local h (progress-harness nil))
  (h.observer {:edge :begin :phase :discover})
  (assert (= (# h.state.lines) 1) "begin must reach the sink immediately")
  (assert (contains? (. h.state.lines 1) "at_ms=0 edge=begin phase=discover"))
  (set h.state.now 125)
  (h.observer {:edge :end :phase :discover :count 2})
  (assert (= (# h.state.lines) 2))
  (assert (contains? (. h.state.lines 2) "at_ms=25 edge=end phase=discover elapsed_ms=25 count=2"))
  (set h.state.now 110)
  (h.observer {:edge :begin :phase :facts})
  (assert (contains? (. h.state.lines 3) "at_ms=25 edge=begin phase=facts")))

(fn progress-aggregates-without-file-history []
  (local h (progress-harness nil))
  (h.observer {:edge :begin :phase :facts})
  (for [index 1 1000]
    (h.observer {:edge :begin :phase :facts :subphase :extract : index :file "safe.fnl"})
    (set h.state.now (+ h.state.now 2))
    (h.observer {:edge :end :phase :facts :subphase :extract : index :definitions 3 :calls 4}))
  (assert (= (# h.state.lines) 1) "phase-first mode must not write file events")
  (h.observer {:edge :end :phase :facts :count 1000})
  (assert (= (# h.state.lines) 3))
  (local summary (. h.state.lines 3))
  (assert (contains? summary "aggregate phase=facts subphase=extract begins=1000 ends=1000 elapsed_ms=2000"))
  (assert (contains? summary "definitions=3000 calls=4000"))
  (assert (not (contains? (table.concat h.state.lines) "safe.fnl"))))

(fn assert-progress-lines [lines max-lines max-line max-total]
  (assert (<= (# lines) max-lines))
  (var bytes 0)
  (each [_ line (ipairs lines)]
    (assert (contains? line "[CONSTRAINT-PROGRESS] "))
    (assert (<= (+ (# line) 2) max-line) "CRLF is part of the encoded line budget")
    (for [i 1 (# line)]
      (local byte (string.byte line i))
      (assert (and (>= byte 32) (<= byte 126)) "output must be single-line printable ASCII"))
    (set bytes (+ bytes (# line) 2)))
  (assert (<= bytes max-total))
  bytes)

(fn assert-progress-stream [state ending max-lines max-line max-total]
  (local stream (table.concat state.serialized))
  (assert (<= (# stream) max-total) "actual serialized progress stream exceeds byte cap")
  (assert (= (# state.serialized) (# state.lines)))
  (assert (<= (# state.serialized) max-lines))
  (each [_ chunk (ipairs state.serialized)]
    (assert (<= (# chunk) max-line) "actual serialized progress line exceeds byte cap")
    (assert (= (string.sub chunk (- (# ending))) ending)))
  (local cap-line (. state.lines (# state.lines)))
  (assert (= (. state.serialized (# state.serialized)) (.. cap-line ending))
          "serialized cap marker must include the complete line ending")
  (# stream))

(fn assert-progress-phase-cap [ending]
  (local h (progress-harness nil ending))
  (for [_ 1 1000]
    (h.observer {:edge :begin :phase :select})
    (h.observer {:edge :end :phase :select :count 1}))
  (assert (= (# h.state.lines) 256))
  (assert-progress-lines h.state.lines 256 256 (* 256 256))
  (assert (= (. h.state.lines 256) "[CONSTRAINT-PROGRESS] cap reached mode=phase"))
  (assert-progress-stream h.state ending 256 256 (* 256 256))
  (local calls h.state.clock-calls)
  (h.observer {:edge :end :phase :summarize})
  (assert (= h.state.clock-calls calls) "capped observer must stop all observation work"))

(fn progress-caps-phase-output []
  (assert-progress-phase-cap "\r\n")
  (assert-progress-phase-cap "\n"))

(fn assert-progress-detail-cap [ending]
  (local h (progress-harness :discover ending))
  (h.observer {:edge :begin :phase :facts :subphase :extract :index 1})
  (assert (= (# h.state.lines) 0) "only the selected phase has file detail")
  (for [index 1 30000]
    (h.observer {:edge :begin :phase :discover :subphase :parse : index :file (string.rep "a" 1024)})
    (h.observer {:edge :end :phase :discover :subphase :parse : index}))
  (local bytes (assert-progress-stream h.state ending 60001 512 (* 2 1024 1024)))
  (assert-progress-lines h.state.lines 60001 512 (* 2 1024 1024))
  ;; LF serializes one byte less per line than the conservative CRLF reservation.
  (local reserved-bytes (+ bytes (if (= ending "\n") (# h.state.lines) 0)))
  (assert (> reserved-bytes (- (* 2 1024 1024) 512)) "detail should reach its conservative byte cap")
  (assert (= (. h.state.lines (# h.state.lines)) "[CONSTRAINT-PROGRESS] cap reached mode=detail"))
  (assert (contains? (. h.state.lines 1) "[truncated]"))
  (local calls h.state.clock-calls)
  (local written (# h.state.serialized))
  (h.observer {:edge :end :phase :discover :subphase :parse :index 30001})
  (assert (= h.state.clock-calls calls) "detail cap must stop the clock")
  (assert (= (# h.state.serialized) written) "detail cap must stop writes"))

(fn progress-caps-selected-detail []
  (assert-progress-detail-cap "\r\n")
  (assert-progress-detail-cap "\n"))

(fn progress-rejects-private-metadata []
  (local h (progress-harness :discover))
  (local private "PRIVATE_PAYLOAD_SENTINEL")
  (each [_ file (ipairs [(.. "/private/" private) (.. "C:/" private) (.. "//server/" private)
                         (.. "a/../" private) (.. "a/./" private) (.. "a//" private)
                         (.. "a\\" private) (.. "a/" private "\n") (.. private "/") ""])]
    (h.observer {:edge :begin :phase :discover :subphase :read : file :index 7
                 :source private :ast {:secret private} :result private :data private}))
  (h.observer {:edge :begin :phase :rule :rule-id (.. "/private/" private) :index 9})
  (local text (table.concat h.state.lines "\n"))
  (assert (not (contains? text private)))
  (assert (not (contains? text "file=")))
  (assert (contains? text "index=7"))
  (assert (contains? text "index=9"))
  (assert (not (contains? text "rule="))))

(fn progress-escapes-and-allows-only-scalars []
  (local h (progress-harness :discover))
  (h.observer {:edge :begin :phase :discover :subphase :read :file "dir/a\"雪.fnl" :index 1})
  (assert (contains? (. h.state.lines 1) "file=\"dir/a\\\"\\xe9\\x9b\\xaa.fnl\""))
  (local calls {:count 0})
  (fn hostile [_] (set calls.count (+ calls.count 1)) (error "must not stringify or traverse"))
  (local object (setmetatable {} {:__tostring hostile :__index hostile :__pairs hostile}))
  (h.observer {:edge :end :phase :discover :subphase :read :file object :index object
               :count object :definitions object :calls object :rule-id object})
  (h.observer (setmetatable {:edge :begin :phase :select} {:__index hostile}))
  (h.observer {:edge object :phase object})
  (assert (= calls.count 0))
  (assert-progress-lines h.state.lines 256 512 (* 2 1024 1024)))

(fn progress-retains-missing-ends-and-propagates-failures []
  (local h (progress-harness nil))
  (fn workload []
    (h.observer {:edge :begin :phase :discover})
    (error "workload failed"))
  (local (ok _) (pcall workload))
  (assert (not ok))
  (assert (= (# h.state.lines) 1))
  (assert (not (contains? (. h.state.lines 1) "edge=end")))
  (local Progress (require :tests.constraint-progress))
  (local failure {})
  (fn broken-write [_] (error failure))
  (fn constant-now-ms [] 1)
  (local observer (Progress.create {:now-ms constant-now-ms :write broken-write}))
  (local (wrote err) (pcall observer {:edge :begin :phase :select}))
  (assert (and (not wrote) (= err failure)) "sink errors must propagate unchanged"))

(fn progress-validates-options-and-clock []
  (local Progress (require :tests.constraint-progress))
  (fn now-ms [] 1)
  (fn write [_] nil)
  (each [_ opts (ipairs [{} {: now-ms} {: write} {: now-ms : write :detail-phase "arbitrary"}])]
    (assert (not (pcall Progress.create opts))))
  (fn bad-clock [] (/ 0 0))
  (assert (not (pcall Progress.create {:now-ms bad-clock : write}))))

(fn progress-exact-opt-in-and-disabled-output []
  (local state {:clocks 0 :writes 0})
  (fn now-ms [] (set state.clocks (+ state.clocks 1)) 0)
  (fn write [_] (set state.writes (+ state.writes 1)))
  (each [_ raw (ipairs ["" "0" "true" "01" "1 " "2"])]
    (assert (= (full-repo-observer raw now-ms write) nil)))
  (assert (= (full-repo-observer nil now-ms write) nil))
  (assert (and (= state.clocks 0) (= state.writes 0)) "disabled observation must be inert")
  (local observer (full-repo-observer "1" now-ms write))
  (assert (= (type observer) :function))
  (observer {:edge :begin :phase :discover})
  (observer {:edge :begin :phase :discover :subphase :read :index 1})
  (assert (= state.writes 1) "live selection must remain phase-first"))

(fn progress-live-sink-adds-newline-and-flushes []
  (local old-write io.write)
  (local old-flush io.flush)
  (local output [])
  (fn fake-write [line newline] (table.insert output (.. line newline)) true)
  (fn fake-flush [] (table.insert output :flushed) true)
  (fn now-ms [] 0)
  (fn exercise []
    (local observer (full-repo-observer "1" now-ms write-progress-line))
    (observer {:edge :begin :phase :discover})
    (assert (= (# output) 2) "begin must be written and flushed before returning")
    (observer {:edge :end :phase :discover :count 0}))
  (set io.write fake-write)
  (set io.flush fake-flush)
  (local (ok err) (pcall exercise))
  (set io.write old-write)
  (set io.flush old-flush)
  (assert ok (tostring err))
  (assert (= (# output) 4))
  (assert (= (. output 2) :flushed))
  (assert (= (. output 4) :flushed))
  (assert (= (string.sub (. output 1) -1) "\n"))
  (assert (= (string.sub (. output 3) -1) "\n")))

(fn assert-same-progress-result [actual expected]
  (assert (= (type actual) (type expected)))
  (if (= (type actual) :table)
      (do (each [key value (pairs expected)] (assert-same-progress-result (. actual key) value))
          (each [key _ (pairs actual)] (assert (not= (. expected key) nil))))
      (assert (= actual expected))))

(fn assert-progress-io-failure [failed-stage]
  (local old-write io.write)
  (local old-flush io.flush)
  (local state {:writes 0 :flushes 0})
  (fn fake-write [_line _newline]
    (set state.writes (+ state.writes 1))
    (if (= failed-stage :write) (values nil "synthetic progress write failure") true))
  (fn fake-flush []
    (set state.flushes (+ state.flushes 1))
    (if (= failed-stage :flush) (values nil "synthetic progress flush failure") true))
  (set io.write fake-write)
  (set io.flush fake-flush)
  (local (ok err) (pcall write-progress-line "[CONSTRAINT-PROGRESS] synthetic I/O failure"))
  (set io.write old-write)
  (set io.flush old-flush)
  (assert (not ok) "live progress sink must raise returned I/O failures")
  (assert (contains? err (.. "synthetic progress " failed-stage " failure")))
  (assert (= state.writes 1))
  (assert (= state.flushes (if (= failed-stage :write) 0 1))))

(fn progress-live-sink-rejects-io-failures []
  (assert-progress-io-failure :write)
  (assert-progress-io-failure :flush))

(fn progress-integration-preserves-results []
  (local Runner (require :constraints.runner))
  (local fixture (fs.absolute (fs.join-path (asset-lua-root) "tests" "data" "constraint-fixture.fnl")))
  (local target {:kind :files :name "progress-parity" :roots [] :files [fixture]
                 :module-roots [(asset-lua-root)]
                 :suites [:scene-sandbox :lifecycle :test-isolation :layout-rendering :structure-formatting]})
  (local h (progress-harness nil))
  (local plain (Runner.run-target target {:baseline-data false}))
  (local observed (Runner.run-target target {:baseline-data false :observer h.observer}))
  (assert-same-progress-result observed plain)
  (assert (> (# h.state.lines) 10))
  (assert-progress-lines h.state.lines 256 256 (* 256 256)))

(fn assert-hook-equals [expected-hook expected-mask expected-count]
  (local (hook mask count) (debug.gethook))
  (assert (and (= hook expected-hook) (= mask expected-mask) (= count expected-count))
          "progress must preserve the runner's installed/restored deadline hook"))

(fn progress-under-deadline [mode]
  (local Runner (require :tests.runner))
  (local Progress (require :tests.constraint-progress))
  (local (old-hook old-mask old-count) (debug.gethook))
  (local state {:now 0 :lines [] :teardown false :caught false})
  (var installed nil)
  (fn now-ms [] state.now)
  (fn write [line]
    (assert-hook-equals installed "" 10000)
    (table.insert state.lines line)
    (when (= mode :sink-error) (error "synthetic sink failure")))
  (local observer (Progress.create {: now-ms : write}))
  (fn inner-work []
    (set state.now 1000)
    (var total 0)
    (for [i 1 20000] (set total (+ total i)))
    (error "deadline did not fire"))
  (fn body []
    (local (hook mask count) (debug.gethook))
    (assert (and hook (not= hook old-hook) (= mask "") (= count 10000)))
    (set installed hook)
    (observer {:edge :begin :phase :discover})
    (if (= mode :caught-timeout)
        (do (local (ok err) (pcall inner-work))
            (set state.caught (and (not ok) (contains? err "test timed out after 1s"))))
        (observer {:edge :end :phase :discover :count 0})))
  (fn teardown []
    (assert-hook-equals old-hook old-mask old-count)
    (set state.teardown true))
  (local (ok err cleanup-errors)
    (Runner.run-case {:name "synthetic constraint progress" :fn body : teardown} 1 nil now-ms))
  (assert-hook-equals old-hook old-mask old-count)
  (assert (and state.teardown (= (# cleanup-errors) 0)))
  (if (= mode :success)
      (assert (and ok (= (# state.lines) 2)))
      (= mode :caught-timeout)
      (do (assert (and (not ok) state.caught (contains? err "test timed out after 1s")))
          (assert (= (# state.lines) 1) "caught timeout must not fabricate an end"))
      (assert (and (not ok) (contains? err "synthetic sink failure") (= (# state.lines) 1)))))

(fn progress-deadline-success [] (progress-under-deadline :success))
(fn progress-deadline-latched [] (progress-under-deadline :caught-timeout))
(fn progress-deadline-sink-error [] (progress-under-deadline :sink-error))

(fn progress-valid-rule-and-unmatched-aggregate []
  (local h (progress-harness :facts))
  (h.observer {:edge :begin :phase :rule :rule-id "structure.style-doctrine" :index 1})
  (set h.state.now 105)
  (h.observer {:edge :end :phase :rule :rule-id "structure.style-doctrine" :index 1 :count 0})
  (assert (contains? (. h.state.lines 1) "rule=\"structure.style-doctrine\""))
  (assert (contains? (. h.state.lines 2) "elapsed_ms=5"))
  (h.observer {:edge :begin :phase :facts})
  (h.observer {:edge :begin :phase :facts :subphase :extract :index 1})
  (h.observer {:edge :begin :phase :facts :subphase :recover :index 1})
  (set h.state.now 110)
  (h.observer {:edge :end :phase :facts :subphase :extract :index 1 :definitions 2 :calls 3})
  (h.observer {:edge :end :phase :facts :count 1})
  (local text (table.concat h.state.lines "\n"))
  (assert (contains? text "subphase=recover begins=1 ends=0 elapsed_ms=0"))
  (assert (not (contains? text "edge=end phase=facts subphase=recover"))))

;; Register tests
(table.insert tests {:name "constraint progress exact opt-in and disabled output" :fn progress-exact-opt-in-and-disabled-output})
(table.insert tests {:name "constraint progress live sink adds newline and flushes immediately" :fn progress-live-sink-adds-newline-and-flushes})
(table.insert tests {:name "constraint progress live sink rejects returned I/O failures" :fn progress-live-sink-rejects-io-failures})
(table.insert tests {:name "constraint progress integration preserves ordered results" :fn progress-integration-preserves-results})
(table.insert tests {:name "constraint progress leaves deadline installed and restores after success" :fn progress-deadline-success})
(table.insert tests {:name "constraint progress latched deadline survives caught inner exception" :fn progress-deadline-latched})
(table.insert tests {:name "constraint progress restores deadline and teardown after sink failure" :fn progress-deadline-sink-error})
(table.insert tests {:name "constraint progress labels registered rules and preserves unmatched aggregate" :fn progress-valid-rule-and-unmatched-aggregate})
(table.insert tests {:name "constraint progress emits immediate monotonic edges" :fn progress-emits-immediate-monotonic-edges})
(table.insert tests {:name "constraint progress aggregates without file history" :fn progress-aggregates-without-file-history})
(table.insert tests {:name "constraint progress caps phase output including newline and marker" :fn progress-caps-phase-output})
(table.insert tests {:name "constraint progress caps only selected detail within two MiB" :fn progress-caps-selected-detail})
(table.insert tests {:name "constraint progress rejects private metadata with index fallback" :fn progress-rejects-private-metadata})
(table.insert tests {:name "constraint progress escapes and allows only scalars" :fn progress-escapes-and-allows-only-scalars})
(table.insert tests {:name "constraint progress retains missing ends and propagates failures" :fn progress-retains-missing-ends-and-propagates-failures})
(table.insert tests {:name "constraint progress validates options and clock" :fn progress-validates-options-and-clock})
(table.insert tests {:name "rule-registry all-rules returns all required ids"
                     :fn rule-registry-all-rules-returns-all-required-ids})
(table.insert tests {:name "rule-registry all rules are well-formed"
                     :fn rule-registry-all-rules-are-well-formed})
(table.insert tests {:name "runner run-target returns structured result"
                     :fn runner-run-target-returns-structured-result})
(table.insert tests {:name "runner run-target diagnostics include target metadata"
                     :fn runner-run-target-diagnostics-include-target-metadata})
(table.insert tests {:name "runner run-target explicit files target works"
                      :fn runner-run-target-explicit-files-target-works})
(table.insert tests {:name "runner run-target files default baseline runs static rules"
                      :fn runner-run-target-files-default-baseline-runs-static-rules})
(table.insert tests {:name "runner run-target unit default baseline runs static rules"
                      :fn runner-run-target-unit-default-baseline-runs-static-rules})
(table.insert tests {:name "runner run-target app default baseline runs static rules"
                      :fn runner-run-target-app-default-baseline-runs-static-rules})
(table.insert tests {:name "runner run-target clean files default baseline has no false baseline"
                      :fn runner-run-target-clean-files-default-baseline-has-no-false-baseline})
(table.insert tests {:name "runner run-target clean unit default baseline has no false baseline"
                      :fn runner-run-target-clean-unit-default-baseline-has-no-false-baseline})
(table.insert tests {:name "runner run-target clean app default baseline has no false baseline"
                      :fn runner-run-target-clean-app-default-baseline-has-no-false-baseline})
(table.insert tests {:name "default baseline does not false-missing-required"
                      :fn default-baseline-does-not-false-missing-required})
(table.insert tests {:name "runner run-target repo required filtered rule is missing"
                      :fn runner-run-target-repo-required-filtered-rule-is-missing})
(table.insert tests {:name "runner run-target with repo target runs full pipeline"
                      :fn runner-run-target-with-repo-target-runs-full-pipeline})
(table.insert tests {:name "default target suites match rule families"
                     :fn default-target-suites-match-rule-families})
(table.insert tests {:name "required rules registry consistency"
                      :fn required-rules-registry-consistency})
(table.insert tests {:name "runner main argv defaults to repo"
                     :fn runner-main-argv-defaults-to-repo})

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "constraints-default-run"
                       :tests tests})))

{:name "constraints-default-run"
 :tests tests
 :main main}
