;; Aggregator for Layout/Rendering constraint rule tests.
;; Collects tests from split files and provides a unified suite.

(local H (require :tests.constraints-layout-helpers))
(local make-file-fact H.make-file-fact)
(local make-fact-db H.make-fact-db)

(local no-setters (require :tests.test-constraints-rules-layout-no-setters))
(local child-drop (require :tests.test-constraints-rules-layout-child-drop))
(local interactive (require :tests.test-constraints-rules-layout-interactive))
(local ancestors (require :tests.test-constraints-rules-layout-interactive-ancestors))
(local assert-calls (require :tests.test-constraints-layout-assert-calls))

(local tests [])

;; Collect tests from split modules
;; Note: interactive module already imports and merges interactive-precision tests;
;; precision module must not be imported here to avoid double-registration.
(each [_ t (ipairs no-setters.tests)] (table.insert tests t))
(each [_ t (ipairs child-drop.tests)] (table.insert tests t))
(each [_ t (ipairs interactive.tests)] (table.insert tests t))
(each [_ t (ipairs ancestors.tests)] (table.insert tests t))
(each [_ t (ipairs assert-calls.tests)] (table.insert tests t))

;; ======================================================================

(fn layout-rules-returns-table-with-three-rules []
  "Layout.rules() should return a table with exactly 3 rules."
  (local Layout (require :constraints.rules.layout))
  (local rules (Layout.rules))
  (assert (= (type rules) :table) "rules should be a table")
  (assert (= (length rules) 3) (.. "expected 3 rules, got " (length rules))))

(fn layout-rules-have-required-structure []
  "Each layout rule should have :id, :family, :targets, :kind, :run, and :fn."
  (local Layout (require :constraints.rules.layout))
  (local rules (Layout.rules))
  (each [_ rule (ipairs rules)]
    (assert (= (type rule.id) :string) (.. "rule should have string :id, got " (tostring rule.id)))
    (assert (= rule.family "layout-rendering") (.. "rule should have family layout-rendering, got " (tostring rule.family)))
    (assert (= (type rule.targets) :table) "rule should have :targets table")
    (assert (= rule.kind :static) (.. "rule should be kind static, got " (tostring rule.kind)))
    (assert (= (type rule.run) :function) (.. "rule should have :run function for id " (tostring rule.id)))
    (assert (= (type rule.fn) :function) (.. "rule should have :fn function for id " (tostring rule.id)))
    (assert (= rule.fn rule.run) (.. ":fn should alias :run for id " (tostring rule.id)))))

;; ======================================================================
;; Runner integration tests
;; ======================================================================

(fn layout-runner-executable []
  "Layout.rules() entries must be executable by constraints.runner.run."
  (local Layout (require :constraints.rules.layout))
  (local ConstraintRunner (require :constraints.runner))
  (local rules (Layout.rules))
  (local target {:kind :repo :name :test
                 :facts (make-fact-db [(make-file-fact {:path "/test/clean.fnl"
                                                         :module "test-clean"
                                                         :accesses []
                                                         :calls []
                                                         :definitions []})])
                 :files []})
  (local result (ConstraintRunner.run {:rules rules :target target
                                        :baseline-data false}))
  (assert result "runner should return a result table")
  (assert (= (type result.status) :string) "result should have a status")
  (assert (= result.status :pass) (.. "expected :pass status, got " result.status))
  (assert (= (length result.diagnostics) 0)
          (.. "expected 0 diagnostics, got " (length result.diagnostics))))

;; Structure tests
(table.insert tests {:name "layout rules returns table with three rules"
                     :fn layout-rules-returns-table-with-three-rules})
(table.insert tests {:name "layout rules have required structure"
                     :fn layout-rules-have-required-structure})

;; Runner integration
(table.insert tests {:name "layout rules executable by runner"
                     :fn layout-runner-executable})

(local main
  (fn []
    (local runner (require :tests.runner))
    (runner.run-tests {:name "constraints-rules-layout"
                        :tests tests})))

{:name "constraints-rules-layout"
 :tests tests
 :main main}
