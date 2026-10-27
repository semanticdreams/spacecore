;; Tests for Scene/Sandbox constraint rules.
;; Follows TDD: these tests must FAIL before scene-sandbox.fnl and scenarios.fnl are implemented.

(local tests [])

;; --- Helper for portable path normalization ---
;; Used by the module's internal file-path-basename and path-contains? helpers.
;; These tests verify the module handles Windows-style backslash paths correctly
;; when both forward-slash and backslash path separators are in play.
;; The module itself is expected to normalize internally; these tests exercise
;; the exported rule.run functions with backslash paths to prove the fix.

;; --- Helpers for constructing synthetic fact DBs ---

(fn make-file-fact [opts]
  "Create a synthetic file-fact record for testing rule functions."
  (local o (or opts {}))
  {:target (or o.target {:kind :repo :name :test})
   :path (or o.path "/test/module.fnl")
   :module (or o.module "test-module")
   :requires (or o.requires [])
   :definitions (or o.definitions [])
   :exports (or o.exports [])
   :calls (or o.calls [])
   :accesses (or o.accesses [])
   :mutations (or o.mutations [])
   :metrics (or o.metrics {:module-lines 0
                           :max-nesting-depth 0
                           :max-anonymous-callback-depth 0
                           :max-table-literal-size 0
                           :functions []})})

(fn make-fact-db [file-facts]
  "Create a synthetic fact-db from a list of file-fact records."
  (let [by-file {}]
    (each [_ ff (ipairs file-facts)]
      (tset by-file ff.path ff))
    {:files file-facts
     :by-file by-file}))

(fn make-ctx [file-facts]
  "Create a context table for rule execution."
  {:target {:kind :repo :name :test}
   :facts (make-fact-db file-facts)
   :files []})

;; --- Rule 1: scene.no-legacy-world-state-scene ---

(fn find-rule-by-id [rules id]
  "Find a rule in a rules list by its :id field."
  (var found nil)
  (each [_ r (ipairs rules)]
    (when (= r.id id)
      (set found r)))
  found)

(fn no-legacy-allows-clean-file []
  "A file with no world.state.scene access should pass."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.no-legacy-world-state-scene"))
  (assert rule "rule scene.no-legacy-world-state-scene should be in rules list")
  (local ff (make-file-fact {:path "/src/new-module.fnl"
                             :module "new-module"
                             :accesses []}))
  (local result (rule.run (make-ctx [ff])))
  (assert (= result nil) "clean file should pass without diagnostics"))

(fn no-legacy-flags-world-state-scene-access []
  "A non-allowlisted file with world.state.scene.* access should produce a diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.no-legacy-world-state-scene"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/src/new-module.fnl"
                             :module "new-module"
                             :accesses [{:path ["world" "state" "scene" "panels"]
                                         :text "world.state.scene.panels"
                                         :line 42
                                         :column 5
                                         :form "world.state.scene.panels"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics")
  (assert (= (type result) :table) "diagnostics should be a table")
  (assert (> (length result) 0) "should have at least one diagnostic")
  (local d (. result 1))
  (assert (= d.constraint-id "scene.no-legacy-world-state-scene")
          "diagnostic should have correct constraint-id")
  (assert (= d.family "scene-sandbox") "diagnostic should have family scene-sandbox")
  (assert (= d.file ff.path) "diagnostic should include file path")
  (assert (= d.line 42) "diagnostic should include line")
  (assert (= d.column 5) "diagnostic should include column")
  (assert d.evidence "diagnostic should include evidence"))

(fn no-legacy-allows-allowlisted-migration-files []
  "An allowlisted migration file with world.state.scene access should pass."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.no-legacy-world-state-scene"))
  (assert rule "rule should be in rules list")
  ;; home-world.fnl is an allowed migration file
  (local ff (make-file-fact {:path "/lua/home-world.fnl"
                             :module "home-world"
                             :accesses [{:path ["world" "state" "scene" "panels"]
                                         :text "world.state.scene.panels"
                                         :line 10
                                         :column 1
                                         :form "world.state.scene.panels"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert (= result nil) "allowlisted migration file should pass"))

;; Windows-style path tests for allowlist matching
;; Regression: backslash paths (e.g. D:\a\space\space\build\...\home-world.fnl)
;; must match the slash-only allowlist fragments "/home-world.fnl", "/tests/", "/e2e/".

(fn no-legacy-allows-home-world-windows-path []
  "home-world.fnl with Windows-style backslash path should be allowlisted."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.no-legacy-world-state-scene"))
  (assert rule "rule should be in rules list")
  ;; Windows-style path with backslashes — must be recognized as allowlisted
  (local ff (make-file-fact {:path "D:\\a\\space\\space\\build\\dist\\windows\\assets\\lua\\home-world.fnl"
                             :module "home-world"
                             :accesses [{:path ["world" "state" "scene" "panels"]
                                         :text "world.state.scene.panels"
                                         :line 10
                                         :column 1
                                         :form "world.state.scene.panels"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert (= result nil) (.. "home-world.fnl with backslash path should pass, got "
                             (if result (length result) 0) " diagnostics")))

(fn no-legacy-allows-tests-dir-windows-path []
  "A file under \\tests\\ with Windows-style backslash path should pass."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.no-legacy-world-state-scene"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "D:\\a\\space\\space\\build\\dist\\windows\\assets\\lua\\tests\\legacy-migration.fnl"
                             :module "legacy-migration"
                             :accesses [{:path ["world" "state" "scene" "panels"]
                                         :text "world.state.scene.panels"
                                         :line 10
                                         :column 1
                                         :form "world.state.scene.panels"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert (= result nil) (.. "tests/ with backslash path should pass, got "
                             (if result (length result) 0) " diagnostics")))

(fn no-legacy-allows-e2e-dir-windows-path []
  "A file under \\e2e\\ with Windows-style backslash path should pass."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.no-legacy-world-state-scene"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "D:\\a\\space\\space\\e2e\\sandbox-test.fnl"
                             :module "sandbox-test"
                             :accesses [{:path ["world" "state" "scene" "panels"]
                                         :text "world.state.scene.panels"
                                         :line 10
                                         :column 1
                                         :form "world.state.scene.panels"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert (= result nil) (.. "e2e/ with backslash path should pass, got "
                             (if result (length result) 0) " diagnostics")))

(fn no-legacy-flags-non-allowlisted-windows-path []
  "A non-allowlisted file with Windows-style backslash path should still be flagged."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.no-legacy-world-state-scene"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "D:\\a\\space\\space\\src\\new-module.fnl"
                             :module "new-module"
                             :accesses [{:path ["world" "state" "scene" "panels"]
                                         :text "world.state.scene.panels"
                                         :line 42
                                         :column 5
                                         :form "world.state.scene.panels"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics for non-allowlisted backslash path")
  (assert (> (length result) 0) "should have at least one diagnostic")
  (local d (. result 1))
  (assert (= d.constraint-id "scene.no-legacy-world-state-scene")
          "diagnostic should have correct constraint-id"))

;; Activity-slot-ownership with Windows-style paths (tests file-path-basename)
(fn slot-ownership-allows-correct-graph-slot-windows-path []
  "graph-activity-unit with Windows-style backslash path should match basename correctly."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.activity-slot-ownership"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "D:\\a\\space\\space\\build\\dist\\windows\\assets\\lua\\graph-activity-unit.fnl"
                             :module "graph-activity-unit"
                             :calls [{:callee "scene:ensure-activity-slot"
                                       :receiver nil
                                       :method nil
                                       :line 10 :column 1
                                       :form "(scene:ensure-activity-slot \"graph\")"}
                                      {:callee "scene:activate-activity-slot"
                                       :receiver nil
                                       :method nil
                                       :line 11 :column 1
                                       :form "(scene:activate-activity-slot \"graph\")"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert (= result nil) "correct slot ownership with backslash path should pass"))

(fn slot-ownership-flags-wrong-id-windows-path []
  "graph-activity-unit with backslash path using wrong slot id should be flagged."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.activity-slot-ownership"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "D:\\a\\space\\space\\build\\dist\\windows\\assets\\lua\\graph-activity-unit.fnl"
                             :module "graph-activity-unit"
                             :calls [{:callee "scene:ensure-activity-slot"
                                       :receiver nil
                                       :method nil
                                       :line 10 :column 1
                                       :form "(scene:ensure-activity-slot \"sandbox\")"}
                                      {:callee "scene:activate-activity-slot"
                                       :receiver nil
                                       :method nil
                                       :line 11 :column 1
                                       :form "(scene:activate-activity-slot \"sandbox\")"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics for wrong slot with backslash path")
  (assert (> (length result) 0) "should have at least one diagnostic"))

;; --- Rule 2: scene.activity-slot-ownership ---

(fn slot-ownership-allows-correct-graph-slot []
  "graph-activity-unit calling ensure/activate with 'graph' should pass."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.activity-slot-ownership"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/graph-activity-unit.fnl"
                             :module "graph-activity-unit"
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil
                                      :method nil
                                      :line 10 :column 1
                                      :form "(scene:ensure-activity-slot \"graph\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil
                                      :method nil
                                      :line 11 :column 1
                                      :form "(scene:activate-activity-slot \"graph\")"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert (= result nil) "correct slot ownership should pass"))

(fn slot-ownership-flags-graph-using-sandbox []
  "graph-activity-unit calling ensure/activate with 'sandbox' should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.activity-slot-ownership"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/graph-activity-unit.fnl"
                             :module "graph-activity-unit"
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil
                                      :method nil
                                      :line 10 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil
                                      :method nil
                                      :line 11 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics")
  (assert (> (length result) 0) "should have at least one diagnostic")
  (local d (. result 1))
  (assert (= d.constraint-id "scene.activity-slot-ownership")
          "diagnostic should have correct constraint-id")
  (assert (= d.family "scene-sandbox") "diagnostic should have family scene-sandbox"))

(fn slot-ownership-flags-drawing-using-sandbox []
  "drawing-activity-unit calling ensure/activate with 'sandbox' should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.activity-slot-ownership"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/drawing-activity-unit.fnl"
                             :module "drawing-activity-unit"
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil
                                      :method nil
                                      :line 10 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics")
  (assert (> (length result) 0) "should have at least one diagnostic"))

(fn slot-ownership-flags-board-using-sandbox []
  "board-activity-unit calling ensure/activate with 'sandbox' should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.activity-slot-ownership"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/board-activity-unit.fnl"
                             :module "board-activity-unit"
                             :calls [{:callee "scene:activate-activity-slot"
                                      :receiver nil
                                      :method nil
                                      :line 10 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics")
  (assert (> (length result) 0) "should have at least one diagnostic"))

(fn slot-ownership-flags-missing-ensure-call []
  "graph-activity-unit missing scene:ensure-activity-slot should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.activity-slot-ownership"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/graph-activity-unit.fnl"
                             :module "graph-activity-unit"
                             :calls [{:callee "scene:activate-activity-slot"
                                      :receiver nil
                                      :method nil
                                      :line 10 :column 1
                                      :form "(scene:activate-activity-slot \"graph\")"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics for missing ensure-activity-slot")
  (assert (> (length result) 0) "should have at least one diagnostic")
  ;; Verify at least one diagnostic references the missing call
  (var found-missing false)
  (each [_ d (ipairs result)]
    (when (. d.evidence :missing-call)
      (set found-missing true)))
  (assert found-missing "should include diagnostic for missing call"))

(fn slot-ownership-flags-wrong-id-not-sandbox []
  "graph-activity-unit calling ensure with 'drawing' (non-sandbox wrong id) should be flagged."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.activity-slot-ownership"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/graph-activity-unit.fnl"
                             :module "graph-activity-unit"
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil
                                      :method nil
                                      :line 10 :column 1
                                      :form "(scene:ensure-activity-slot \"drawing\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil
                                      :method nil
                                      :line 11 :column 1
                                      :form "(scene:activate-activity-slot \"graph\")"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics for wrong slot id")
  (assert (> (length result) 0) "should have at least one diagnostic")
  (var found-wrong false)
  (each [_ d (ipairs result)]
    (when (= d.evidence.actual-arg "drawing")
      (set found-wrong true)))
  (assert found-wrong "should flag call with unexpected non-sandbox id 'drawing'"))

(fn slot-ownership-flags-second-call-after-correct-one []
  "A graph module with a correct first call and a later incorrect call should still flag the foreign call."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.activity-slot-ownership"))
  (assert rule "rule should be in rules list")
  ;; Two ensure-activity-slot calls: first correct ("graph"), second foreign ("sandbox")
  (local ff (make-file-fact {:path "/lua/graph-activity-unit.fnl"
                             :module "graph-activity-unit"
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 10 :column 1
                                      :form "(scene:ensure-activity-slot \"graph\")"}
                                     {:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 20 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 11 :column 1
                                      :form "(scene:activate-activity-slot \"graph\")"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics for foreign call after correct one")
  (assert (> (length result) 0) "should have at least one diagnostic")
  (var found-sandbox-flag false)
  (each [_ d (ipairs result)]
    (when (= d.evidence.actual-arg "sandbox")
      (set found-sandbox-flag true)))
  (assert found-sandbox-flag "should flag the 'sandbox' call even when a correct 'graph' call exists"))

;; --- Rule 3: scene.sandbox-activation-contract ---

(fn sandbox-contract-passes-when-all-calls-present []
  "sandbox-activity-unit with all required calls should pass.
  The activation function definition must contain both contract calls and
  a runtime.scene / world-runtime.scene reference in its form text."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.sandbox-activation-contract"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/sandbox-activity-unit.fnl"
                             :module "sandbox-activity-unit"
                             :requires [{:module "runtime"
                                         :line 10 :column 1
                                         :form "(require :runtime)"}]
                             :accesses [{:path ["runtime" "scene"]
                                         :text "runtime.scene"
                                         :line 11 :column 1
                                         :form "runtime.scene"}]
                             :definitions [{:kind :fn
                                            :name "activate-sandbox-activity!"
                                            :top-level? true
                                            :line 15 :column 1
                                            :length 1200
                                            :form "(fn activate-sandbox-activity! [ctx]
  (local scene (assert world-runtime.scene \"requires runtime.scene\"))
  (scene:ensure-activity-slot \"sandbox\")
  (scene:activate-activity-slot \"sandbox\")
  (ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})
  (ctx:set-preferred-interaction-surface! :scene)
  (ctx:set-root-actions! sandbox-root-actions)
  (ctx:set-target-enabled! sandbox-target-enabled?)
  (ctx:set-update! sandbox-activity-update))"}]
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 20 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 21 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}
                                     {:callee "ctx:set-surface-state!"
                                      :receiver nil :method nil
                                      :line 22 :column 1
                                      :form "(ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})"}
                                     {:callee "ctx:set-preferred-interaction-surface!"
                                      :receiver nil :method nil
                                      :line 23 :column 1
                                      :form "(ctx:set-preferred-interaction-surface! :scene)"}
                                     {:callee "ctx:set-root-actions!"
                                      :receiver nil :method nil
                                      :line 24 :column 1
                                      :form "(ctx:set-root-actions! sandbox-root-actions)"}
                                     {:callee "ctx:set-target-enabled!"
                                      :receiver nil :method nil
                                      :line 25 :column 1
                                      :form "(ctx:set-target-enabled! sandbox-target-enabled?)"}
                                     {:callee "ctx:set-update!"
                                      :receiver nil :method nil
                                      :line 26 :column 1
                                      :form "(ctx:set-update! sandbox-activity-update)"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert (= result nil) (.. "complete sandbox contract should pass, got " (if result (length result) 0) " diagnostics")))

(fn sandbox-contract-flags-missing-requires-runtime []
  "sandbox-activity-unit missing require of runtime should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.sandbox-activation-contract"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/sandbox-activity-unit.fnl"
                             :module "sandbox-activity-unit"
                             :requires []
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 20 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 21 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}
                                     {:callee "ctx:set-surface-state!"
                                      :receiver nil :method nil
                                      :line 22 :column 1
                                      :form "(ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})"}
                                     {:callee "ctx:set-preferred-interaction-surface!"
                                      :receiver nil :method nil
                                      :line 23 :column 1
                                      :form "(ctx:set-preferred-interaction-surface! :scene)"}
                                     {:callee "ctx:set-root-actions!"
                                      :receiver nil :method nil
                                      :line 24 :column 1
                                      :form "(ctx:set-root-actions! sandbox-root-actions)"}
                                     {:callee "ctx:set-target-enabled!"
                                      :receiver nil :method nil
                                      :line 25 :column 1
                                      :form "(ctx:set-target-enabled! sandbox-target-enabled?)"}
                                     {:callee "ctx:set-update!"
                                      :receiver nil :method nil
                                      :line 26 :column 1
                                      :form "(ctx:set-update! sandbox-activity-update)"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics")
  (assert (> (length result) 0) "should have at least one diagnostic")
  (local d (. result 1))
  (assert (= d.constraint-id "scene.sandbox-activation-contract")
          "diagnostic should have correct constraint-id")
  (assert (= d.family "scene-sandbox") "diagnostic should have family scene-sandbox"))

(fn sandbox-contract-flags-missing-activate-sandbox []
  "sandbox-activity-unit missing scene:activate-activity-slot call should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.sandbox-activation-contract"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/sandbox-activity-unit.fnl"
                             :module "sandbox-activity-unit"
                             :requires [{:module "runtime"
                                         :line 10 :column 1
                                         :form "(require :runtime)"}]
                             :calls [{:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 21 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}
                                     {:callee "ctx:set-surface-state!"
                                      :receiver nil :method nil
                                      :line 22 :column 1
                                      :form "(ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})"}
                                     {:callee "ctx:set-preferred-interaction-surface!"
                                      :receiver nil :method nil
                                      :line 23 :column 1
                                      :form "(ctx:set-preferred-interaction-surface! :scene)"}
                                     {:callee "ctx:set-root-actions!"
                                      :receiver nil :method nil
                                      :line 24 :column 1
                                      :form "(ctx:set-root-actions! sandbox-root-actions)"}
                                     {:callee "ctx:set-target-enabled!"
                                      :receiver nil :method nil
                                      :line 25 :column 1
                                      :form "(ctx:set-target-enabled! sandbox-target-enabled?)"}
                                     {:callee "ctx:set-update!"
                                      :receiver nil :method nil
                                      :line 26 :column 1
                                      :form "(ctx:set-update! sandbox-activity-update)"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics")
  (assert (> (length result) 0) "should have at least one diagnostic"))

(fn sandbox-contract-flags-missing-set-surface-state []
  "sandbox-activity-unit missing ctx:set-surface-state! call should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.sandbox-activation-contract"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/sandbox-activity-unit.fnl"
                             :module "sandbox-activity-unit"
                             :requires [{:module "runtime"
                                         :line 10 :column 1
                                         :form "(require :runtime)"}]
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 20 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 21 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}
                                     {:callee "ctx:set-preferred-interaction-surface!"
                                      :receiver nil :method nil
                                      :line 23 :column 1
                                      :form "(ctx:set-preferred-interaction-surface! :scene)"}
                                     {:callee "ctx:set-root-actions!"
                                      :receiver nil :method nil
                                      :line 24 :column 1
                                      :form "(ctx:set-root-actions! sandbox-root-actions)"}
                                     {:callee "ctx:set-target-enabled!"
                                      :receiver nil :method nil
                                      :line 25 :column 1
                                      :form "(ctx:set-target-enabled! sandbox-target-enabled?)"}
                                     {:callee "ctx:set-update!"
                                      :receiver nil :method nil
                                      :line 26 :column 1
                                      :form "(ctx:set-update! sandbox-activity-update)"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics")
  (assert (> (length result) 0) "should have at least one diagnostic"))

(fn sandbox-contract-flags-missing-runtime-scene-access []
  "sandbox-activity-unit with all calls and runtime require but no runtime.scene access should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.sandbox-activation-contract"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/sandbox-activity-unit.fnl"
                             :module "sandbox-activity-unit"
                             :requires [{:module "runtime"
                                         :line 10 :column 1
                                         :form "(require :runtime)"}]
                             ;; No runtime.scene access — should be flagged
                             :accesses []
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 20 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 21 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}
                                     {:callee "ctx:set-surface-state!"
                                      :receiver nil :method nil
                                      :line 22 :column 1
                                      :form "(ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})"}
                                     {:callee "ctx:set-preferred-interaction-surface!"
                                      :receiver nil :method nil
                                      :line 23 :column 1
                                      :form "(ctx:set-preferred-interaction-surface! :scene)"}
                                     {:callee "ctx:set-root-actions!"
                                      :receiver nil :method nil
                                      :line 24 :column 1
                                      :form "(ctx:set-root-actions! sandbox-root-actions)"}
                                     {:callee "ctx:set-target-enabled!"
                                      :receiver nil :method nil
                                      :line 25 :column 1
                                      :form "(ctx:set-target-enabled! sandbox-target-enabled?)"}
                                     {:callee "ctx:set-update!"
                                      :receiver nil :method nil
                                      :line 26 :column 1
                                      :form "(ctx:set-update! sandbox-activity-update)"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics for missing runtime.scene access")
  (assert (> (length result) 0) "should have at least one diagnostic")
  ;; Verify at least one diagnostic mentions runtime.scene
  (var found false)
  (each [_ d (ipairs result)]
    (when (= d.evidence.required-access "runtime.scene")
      (set found true)))
  (assert found "should flag missing runtime.scene access"))

(fn sandbox-contract-flags-unrelated-runtime-scene-access []
  "An unrelated runtime.scene access in a helper function should NOT satisfy the
  activation contract when the activation function itself lacks scene access.
  The rule ties runtime.scene evidence to the activation function definition."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.sandbox-activation-contract"))
  (assert rule "rule should be in rules list")
  ;; Activation function definition has contract calls but NO runtime.scene reference.
  ;; Helper function definition has runtime.scene but NO contract calls.
  ;; File-wide accesses have a matching runtime.scene access.
  ;; Expected: VIOLATION because the activation function itself does not access runtime.scene.
  (local ff (make-file-fact {:path "/lua/sandbox-activity-unit.fnl"
                             :module "sandbox-activity-unit"
                             :requires [{:module "runtime"
                                         :line 10 :column 1
                                         :form "(require :runtime)"}]
                             ;; File-wide access exists (from helper fn), but it's unrelated to activation
                             :accesses [{:path ["runtime" "scene"]
                                         :text "runtime.scene"
                                         :line 100 :column 1
                                         :form "runtime.scene"}]
                             :definitions
                             [{:kind :fn
                               :name "activate-sandbox-activity!"
                               :top-level? true
                               :line 15 :column 1
                               :length 500
                                :form "(fn activate-sandbox-activity! [ctx]
  ;; activation function: has contract calls but does NOT access the scene
  (scene:ensure-activity-slot \"sandbox\")
  (scene:activate-activity-slot \"sandbox\")
  (ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})
  (ctx:set-preferred-interaction-surface! :scene)
  (ctx:set-root-actions! sandbox-root-actions)
  (ctx:set-target-enabled! sandbox-target-enabled?)
  (ctx:set-update! sandbox-activity-update))"}
                              {:kind :fn
                               :name "some-unrelated-helper"
                               :top-level? true
                               :line 95 :column 1
                               :length 100
                                                               :form "(fn some-unrelated-helper []
  ;; unrelated helper accesses the scene — should NOT satisfy the activation contract
  (print world-runtime.scene))"}]
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 20 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 21 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}
                                     {:callee "ctx:set-surface-state!"
                                      :receiver nil :method nil
                                      :line 22 :column 1
                                      :form "(ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})"}
                                     {:callee "ctx:set-preferred-interaction-surface!"
                                      :receiver nil :method nil
                                      :line 23 :column 1
                                      :form "(ctx:set-preferred-interaction-surface! :scene)"}
                                     {:callee "ctx:set-root-actions!"
                                      :receiver nil :method nil
                                      :line 24 :column 1
                                      :form "(ctx:set-root-actions! sandbox-root-actions)"}
                                     {:callee "ctx:set-target-enabled!"
                                      :receiver nil :method nil
                                      :line 25 :column 1
                                      :form "(ctx:set-target-enabled! sandbox-target-enabled?)"}
                                     {:callee "ctx:set-update!"
                                      :receiver nil :method nil
                                      :line 26 :column 1
                                      :form "(ctx:set-update! sandbox-activity-update)"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics — unrelated runtime.scene access does not satisfy activation contract")
  (assert (> (length result) 0) "should have at least one diagnostic")
  (var found-access-diag false)
  (each [_ d (ipairs result)]
    (when (= d.evidence.required-access "runtime.scene")
      (set found-access-diag true)))
  (assert found-access-diag "should flag missing runtime.scene access in activation function"))

(fn sandbox-contract-flags-helper-with-contract-call-plus-scene []
  "A helper function that has both a contract-call pattern (e.g. ctx:set-update!)
  and a scene access (world-runtime.scene) should NOT satisfy the activation
  contract when the real activation function (activate-sandbox-activity!) lacks
  scene access.  The rule must tie runtime.scene evidence specifically to the
  activation-owning definition, not to any definition that happens to contain a
  contract-call-like pattern."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.sandbox-activation-contract"))
  (assert rule "rule should be in rules list")
  ;; Activation function has ALL contract calls but NO runtime.scene reference.
  ;; Helper function has BOTH world-runtime.scene AND a contract-call pattern (ctx:set-update!).
  ;; File-wide accesses have a matching runtime.scene access.
  ;; Expected: VIOLATION — the helper's evidence does not satisfy activation contract.
  (local ff (make-file-fact {:path "/lua/sandbox-activity-unit.fnl"
                             :module "sandbox-activity-unit"
                             :requires [{:module "runtime"
                                         :line 10 :column 1
                                         :form "(require :runtime)"}]
                             :accesses [{:path ["runtime" "scene"]
                                         :text "runtime.scene"
                                         :line 100 :column 1
                                         :form "runtime.scene"}]
                             :definitions
                             [{:kind :fn
                               :name "activate-sandbox-activity!"
                               :top-level? true
                               :line 15 :column 1
                               :length 500
                               :form "(fn activate-sandbox-activity! [ctx]
   ;; activation function: has contract calls but NO scene access
   (scene:ensure-activity-slot \"sandbox\")
   (scene:activate-activity-slot \"sandbox\")
   (ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})
   (ctx:set-preferred-interaction-surface! :scene)
   (ctx:set-root-actions! sandbox-root-actions)
   (ctx:set-target-enabled! sandbox-target-enabled?)
   (ctx:set-update! sandbox-activity-update))"}
                              {:kind :fn
                               :name "some-helper"
                               :top-level? true
                               :line 95 :column 1
                               :length 120
                               :form "(fn some-helper [ctx]
   ;; helper has BOTH a scene access AND a contract-call-like pattern
   (ctx:set-update! helper-update)
   (let [wr world-runtime.scene]
     (print wr))"}]
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 20 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 21 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}
                                     {:callee "ctx:set-surface-state!"
                                      :receiver nil :method nil
                                      :line 22 :column 1
                                      :form "(ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})"}
                                     {:callee "ctx:set-preferred-interaction-surface!"
                                      :receiver nil :method nil
                                      :line 23 :column 1
                                      :form "(ctx:set-preferred-interaction-surface! :scene)"}
                                     {:callee "ctx:set-root-actions!"
                                      :receiver nil :method nil
                                      :line 24 :column 1
                                      :form "(ctx:set-root-actions! sandbox-root-actions)"}
                                     {:callee "ctx:set-target-enabled!"
                                      :receiver nil :method nil
                                      :line 25 :column 1
                                      :form "(ctx:set-target-enabled! sandbox-target-enabled?)"}
                                     {:callee "ctx:set-update!"
                                      :receiver nil :method nil
                                      :line 26 :column 1
                                      :form "(ctx:set-update! helper-update)"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics — helper scene+contract access does not satisfy activation contract")
  (assert (> (length result) 0) "should have at least one diagnostic")
  (var found-access-diag false)
  (each [_ d (ipairs result)]
    (when (= d.evidence.required-access "runtime.scene")
      (set found-access-diag true)))
  (assert found-access-diag "should flag missing runtime.scene access in activation function"))

(fn sandbox-contract-flags-wrong-require-module []
  "sandbox-activity-unit requiring 'not-runtime' instead of 'runtime' should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.sandbox-activation-contract"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/sandbox-activity-unit.fnl"
                             :module "sandbox-activity-unit"
                             :requires [{:module "not-runtime"
                                         :line 10 :column 1
                                         :form "(require :not-runtime)"}]
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 20 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 21 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}
                                     {:callee "ctx:set-surface-state!"
                                      :receiver nil :method nil
                                      :line 22 :column 1
                                      :form "(ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})"}
                                     {:callee "ctx:set-preferred-interaction-surface!"
                                      :receiver nil :method nil
                                      :line 23 :column 1
                                      :form "(ctx:set-preferred-interaction-surface! :scene)"}
                                     {:callee "ctx:set-root-actions!"
                                      :receiver nil :method nil
                                      :line 24 :column 1
                                      :form "(ctx:set-root-actions! sandbox-root-actions)"}
                                     {:callee "ctx:set-target-enabled!"
                                      :receiver nil :method nil
                                      :line 25 :column 1
                                      :form "(ctx:set-target-enabled! sandbox-target-enabled?)"}
                                     {:callee "ctx:set-update!"
                                      :receiver nil :method nil
                                      :line 26 :column 1
                                      :form "(ctx:set-update! sandbox-activity-update)"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics for wrong require module")
  (assert (> (length result) 0) "should have at least one diagnostic")
  (var found-require false)
  (each [_ d (ipairs result)]
    (when (= d.evidence.required-require "runtime")
      (set found-require true)))
  (assert found-require "should flag missing runtime require"))

(fn sandbox-contract-flags-wrong-ensure-slot-id []
  "sandbox-activity-unit calling ensure-activity-slot with 'graph' should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.sandbox-activation-contract"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/sandbox-activity-unit.fnl"
                             :module "sandbox-activity-unit"
                             :requires [{:module "runtime"
                                         :line 10 :column 1
                                         :form "(require :runtime)"}]
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 20 :column 1
                                      :form "(scene:ensure-activity-slot \"graph\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 21 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}
                                     {:callee "ctx:set-surface-state!"
                                      :receiver nil :method nil
                                      :line 22 :column 1
                                      :form "(ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})"}
                                     {:callee "ctx:set-preferred-interaction-surface!"
                                      :receiver nil :method nil
                                      :line 23 :column 1
                                      :form "(ctx:set-preferred-interaction-surface! :scene)"}
                                     {:callee "ctx:set-root-actions!"
                                      :receiver nil :method nil
                                      :line 24 :column 1
                                      :form "(ctx:set-root-actions! sandbox-root-actions)"}
                                     {:callee "ctx:set-target-enabled!"
                                      :receiver nil :method nil
                                      :line 25 :column 1
                                      :form "(ctx:set-target-enabled! sandbox-target-enabled?)"}
                                     {:callee "ctx:set-update!"
                                      :receiver nil :method nil
                                      :line 26 :column 1
                                      :form "(ctx:set-update! sandbox-activity-update)"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics for wrong ensure slot id")
  (assert (> (length result) 0) "should have at least one diagnostic")
  (var found-wrong false)
  (each [_ d (ipairs result)]
    (when (= d.evidence.expected-arg "sandbox")
      (set found-wrong true)))
  (assert found-wrong "should flag call with wrong sandbox id"))

(fn sandbox-contract-flags-canvas-not-hidden []
  "sandbox-activity-unit calling set-surface-state! without canvas hidden should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.sandbox-activation-contract"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/sandbox-activity-unit.fnl"
                             :module "sandbox-activity-unit"
                             :requires [{:module "runtime"
                                         :line 10 :column 1
                                         :form "(require :runtime)"}]
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 20 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 21 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}
                                     {:callee "ctx:set-surface-state!"
                                      :receiver nil :method nil
                                      :line 22 :column 1
                                      :form "(ctx:set-surface-state! {:canvas {:visible? true}})"}
                                     {:callee "ctx:set-preferred-interaction-surface!"
                                      :receiver nil :method nil
                                      :line 23 :column 1
                                      :form "(ctx:set-preferred-interaction-surface! :scene)"}
                                     {:callee "ctx:set-root-actions!"
                                      :receiver nil :method nil
                                      :line 24 :column 1
                                      :form "(ctx:set-root-actions! sandbox-root-actions)"}
                                     {:callee "ctx:set-target-enabled!"
                                      :receiver nil :method nil
                                      :line 25 :column 1
                                      :form "(ctx:set-target-enabled! sandbox-target-enabled?)"}
                                     {:callee "ctx:set-update!"
                                      :receiver nil :method nil
                                      :line 26 :column 1
                                      :form "(ctx:set-update! sandbox-activity-update)"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics for canvas not hidden")
  (assert (> (length result) 0) "should have at least one diagnostic"))

(fn sandbox-contract-flags-wrong-preferred-surface []
  "sandbox-activity-unit calling set-preferred-interaction-surface! with :canvas should produce diagnostic."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.sandbox-activation-contract"))
  (assert rule "rule should be in rules list")
  (local ff (make-file-fact {:path "/lua/sandbox-activity-unit.fnl"
                             :module "sandbox-activity-unit"
                             :requires [{:module "runtime"
                                         :line 10 :column 1
                                         :form "(require :runtime)"}]
                             :calls [{:callee "scene:ensure-activity-slot"
                                      :receiver nil :method nil
                                      :line 20 :column 1
                                      :form "(scene:ensure-activity-slot \"sandbox\")"}
                                     {:callee "scene:activate-activity-slot"
                                      :receiver nil :method nil
                                      :line 21 :column 1
                                      :form "(scene:activate-activity-slot \"sandbox\")"}
                                     {:callee "ctx:set-surface-state!"
                                      :receiver nil :method nil
                                      :line 22 :column 1
                                      :form "(ctx:set-surface-state! {:canvas {:visible? false :interactive? false}})"}
                                     {:callee "ctx:set-preferred-interaction-surface!"
                                      :receiver nil :method nil
                                      :line 23 :column 1
                                      :form "(ctx:set-preferred-interaction-surface! :canvas)"}
                                     {:callee "ctx:set-root-actions!"
                                      :receiver nil :method nil
                                      :line 24 :column 1
                                      :form "(ctx:set-root-actions! sandbox-root-actions)"}
                                     {:callee "ctx:set-target-enabled!"
                                      :receiver nil :method nil
                                      :line 25 :column 1
                                      :form "(ctx:set-target-enabled! sandbox-target-enabled?)"}
                                     {:callee "ctx:set-update!"
                                      :receiver nil :method nil
                                      :line 26 :column 1
                                      :form "(ctx:set-update! sandbox-activity-update)"}]}))
  (local result (rule.run (make-ctx [ff])))
  (assert result "should produce diagnostics for wrong preferred surface")
  (assert (> (length result) 0) "should have at least one diagnostic"))

;; --- Rule 4: scene.active-render-context-routing ---

(fn active-render-context-routing-scenario []
  "Executable scenario verifies active Scene slot context supplies render vectors.
  This test requires a real app environment — the rule runner handles setup/teardown."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local rule (find-rule-by-id rules "scene.active-render-context-routing"))
  (assert rule "rule should be in rules list")
  ;; The rule internally uses Scenarios.with-test-app;
  ;; the test must NOT double-wrap in with-test-app.
  ;; Call rule.run directly with a context that has the expected shape.
  (local caller app)
  (local canvas caller.canvas)
  (local runtime caller.active-world-runtime)
  (local registry caller.activity-registry)
  (local lights caller.lights)
  (local projection-factory caller.create-default-projection)
  (local result (rule.run {:target {:kind :repo :name :test}
                            :facts (make-fact-db [])
                            :files []}))
  (assert (= app caller) "routing scenario restores the borrowed caller")
  (assert (and (= caller.canvas canvas) (= caller.active-world-runtime runtime)
               (= caller.activity-registry registry) (= caller.lights lights)
               (= caller.create-default-projection projection-factory))
          "routing scenario owns its shell, registry, lights and projection factory")
  ;; The real scenario should pass (nil) when the sandbox activation works correctly.
  (assert (= result nil) (.. "expected scenario to pass (nil), got diagnostics count: " (if result (length result) 0))))

(fn render-context-routing-flags-broken-slot []
  "The slot-checking helper should produce diagnostics for a nil slot (missing slot),
  a slot without ctx (missing render context), and a slot without layout-root."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  ;; Use the exported check-scene-slot-routing helper directly
  (local diagnostics [])
  ;; Case 1: nil slot → missing slot diagnostic
  (SceneSandbox.check-scene-slot-routing diagnostics nil)
  (assert (> (length diagnostics) 0) "should diagnose nil slot")
  (assert (= (. diagnostics 1 :constraint-id) "scene.active-render-context-routing")
          "should use correct constraint-id")
  ;; Case 2: slot without ctx → missing context diagnostic
  (local d2 [])
  (SceneSandbox.check-scene-slot-routing d2 {:ctx nil :layout-root true})
  (assert (> (length d2) 0) "should diagnose missing ctx")
  (var found-ctx false)
  (each [_ d (ipairs d2)]
    (when (d.message:find "ctx" 1 true)
      (set found-ctx true)))
  (assert found-ctx "should include diagnostic about missing render context")
  ;; Case 3: slot without layout-root → missing layout-root diagnostic
  (local d3 [])
  (SceneSandbox.check-scene-slot-routing d3 {:ctx true :layout-root nil})
  (assert (> (length d3) 0) "should diagnose missing layout-root")
  (var found-lr false)
  (each [_ d (ipairs d3)]
    (when (d.message:find "layout root" 1 true)
      (set found-lr true)))
  (assert found-lr "should mention layout-root in message")
  ;; Case 4: healthy slot → no diagnostics
  (local d4 [])
  (SceneSandbox.check-scene-slot-routing d4 {:ctx true :layout-root true})
  (assert (= (length d4) 0) "healthy slot should produce no diagnostics"))

;; --- Rules list structure tests ---

(fn rules-returns-table-with-four-rules []
  "SceneSandbox.rules() should return a table with exactly 4 rules."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (assert (= (type rules) :table) "rules should be a table")
  (assert (= (length rules) 4) (.. "expected 4 rules, got " (length rules))))

(fn rules-have-required-structure []
  "Each rule should have :id, :family, :targets, :kind, :run, and :fn."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local rules (SceneSandbox.rules))
  (local expected-ids {"scene.no-legacy-world-state-scene" "static"
                       "scene.activity-slot-ownership" "static"
                       "scene.sandbox-activation-contract" "static"
                       "scene.active-render-context-routing" "scenario"})
  (each [_ rule (ipairs rules)]
    (assert (= (type rule.id) :string) (.. "rule should have string :id, got " (tostring rule.id)))
    (assert (= rule.family "scene-sandbox") "rule should have family scene-sandbox")
    (assert (= (type rule.targets) :table) "rule should have :targets table")
    (assert (or (= rule.kind :static) (= rule.kind :scenario))
            (.. "rule kind should be static or scenario, got " (tostring rule.kind)))
    (assert (= (type rule.run) :function) (.. "rule should have :run function for id " (tostring rule.id)))
    (assert (= (type rule.fn) :function) (.. "rule should have :fn function for id " (tostring rule.id)))
    (assert (= rule.fn rule.run) (.. ":fn should alias :run for id " (tostring rule.id)))
    ;; Check expected kind for known ids
    (when (. expected-ids rule.id)
      (assert (= rule.kind (. expected-ids rule.id))
              (.. "rule " rule.id " should be kind " (. expected-ids rule.id))))))

;; Register all tests
(table.insert tests {:name "scene sandbox rules returns table with four rules"
                     :fn rules-returns-table-with-four-rules})
(table.insert tests {:name "scene sandbox rules have required structure"
                     :fn rules-have-required-structure})
(table.insert tests {:name "no-legacy-world-state-scene allows clean file"
                     :fn no-legacy-allows-clean-file})
(table.insert tests {:name "no-legacy-world-state-scene flags world.state.scene access"
                     :fn no-legacy-flags-world-state-scene-access})
(table.insert tests {:name "no-legacy-world-state-scene allows allowlisted migration files"
                     :fn no-legacy-allows-allowlisted-migration-files})
(table.insert tests {:name "no-legacy-world-state-scene allows home-world with Windows backslash path"
                     :fn no-legacy-allows-home-world-windows-path})
(table.insert tests {:name "no-legacy-world-state-scene allows tests/ with Windows backslash path"
                     :fn no-legacy-allows-tests-dir-windows-path})
(table.insert tests {:name "no-legacy-world-state-scene allows e2e/ with Windows backslash path"
                     :fn no-legacy-allows-e2e-dir-windows-path})
(table.insert tests {:name "no-legacy-world-state-scene flags non-allowlisted Windows backslash path"
                     :fn no-legacy-flags-non-allowlisted-windows-path})
(table.insert tests {:name "activity-slot-ownership allows correct graph slot with Windows backslash path"
                     :fn slot-ownership-allows-correct-graph-slot-windows-path})
(table.insert tests {:name "activity-slot-ownership flags wrong id with Windows backslash path"
                     :fn slot-ownership-flags-wrong-id-windows-path})
(table.insert tests {:name "activity-slot-ownership allows correct graph slot"
                     :fn slot-ownership-allows-correct-graph-slot})
(table.insert tests {:name "activity-slot-ownership flags graph using sandbox"
                     :fn slot-ownership-flags-graph-using-sandbox})
(table.insert tests {:name "activity-slot-ownership flags drawing using sandbox"
                     :fn slot-ownership-flags-drawing-using-sandbox})
(table.insert tests {:name "activity-slot-ownership flags board using sandbox"
                     :fn slot-ownership-flags-board-using-sandbox})
(table.insert tests {:name "activity-slot-ownership flags missing ensure-activity-slot call"
                     :fn slot-ownership-flags-missing-ensure-call})
(table.insert tests {:name "activity-slot-ownership flags wrong id (not sandbox)"
                     :fn slot-ownership-flags-wrong-id-not-sandbox})
(table.insert tests {:name "activity-slot-ownership flags second foreign call after correct one"
                     :fn slot-ownership-flags-second-call-after-correct-one})
(table.insert tests {:name "sandbox-activation-contract passes when all calls present"
                     :fn sandbox-contract-passes-when-all-calls-present})
(table.insert tests {:name "sandbox-activation-contract flags missing requires runtime"
                     :fn sandbox-contract-flags-missing-requires-runtime})
(table.insert tests {:name "sandbox-activation-contract flags missing activate sandbox"
                     :fn sandbox-contract-flags-missing-activate-sandbox})
(table.insert tests {:name "sandbox-activation-contract flags missing set-surface-state"
                     :fn sandbox-contract-flags-missing-set-surface-state})
(table.insert tests {:name "sandbox-activation-contract flags wrong require module"
                     :fn sandbox-contract-flags-wrong-require-module})
(table.insert tests {:name "sandbox-activation-contract flags missing runtime.scene access"
                     :fn sandbox-contract-flags-missing-runtime-scene-access})
(table.insert tests {:name "sandbox-activation-contract flags unrelated runtime.scene access"
                     :fn sandbox-contract-flags-unrelated-runtime-scene-access})
(table.insert tests {:name "sandbox-activation-contract flags helper with contract call + scene but activation lacks scene"
                     :fn sandbox-contract-flags-helper-with-contract-call-plus-scene})
(table.insert tests {:name "sandbox-activation-contract flags wrong ensure slot id"
                     :fn sandbox-contract-flags-wrong-ensure-slot-id})
(table.insert tests {:name "sandbox-activation-contract flags canvas not hidden"
                     :fn sandbox-contract-flags-canvas-not-hidden})
(table.insert tests {:name "sandbox-activation-contract flags wrong preferred surface"
                     :fn sandbox-contract-flags-wrong-preferred-surface})
(table.insert tests {:name "active-render-context-routing scenario"
                     :fn active-render-context-routing-scenario})
(table.insert tests {:name "render-context-routing flags broken slot"
                     :fn render-context-routing-flags-broken-slot})

;; --- Runner integration test: verify rules are executable by constraints.runner ---

(fn runner-rules-executable []
  "SceneSandbox.rules() entries must be executable by constraints.runner.run.
  Runs static rules through the runner with synthetic data, and separately runs
  the scenario rule through the runner with baseline-data false."
  (local SceneSandbox (require :constraints.rules.scene-sandbox))
  (local ConstraintRunner (require :constraints.runner))
  (local rules (SceneSandbox.rules))
  ;; Run static rules through the runner with synthetic data
  (local static-rules [])
  (each [_ r (ipairs rules)]
    (when (= r.kind :static)
      (table.insert static-rules r)))
  (local target {:kind :repo :name :test
                 :facts (make-fact-db [(make-file-fact {:path "/test/module.fnl"
                                                        :module "test-module"
                                                        :accesses []
                                                        :calls []})])
                 :files []})
  (local result (ConstraintRunner.run {:rules static-rules :target target
                                        :baseline-data false}))
  (assert result "runner should return a result table")
  (assert (= (type result.status) :string) "result should have a status")
  (assert (= result.status :pass) (.. "expected :pass status, got " result.status))
  (assert (= (length result.diagnostics) 0)
          (.. "expected 0 diagnostics, got " (length result.diagnostics)))
  ;; Run the scenario rule through the runner — it uses Scenarios.with-test-app internally.
  ;; The scenario rule ignores facts, just needs a target to satisfy the runner contract.
  (local scenario-rule (find-rule-by-id rules "scene.active-render-context-routing"))
  (assert scenario-rule "scenario rule should exist")
  (assert (= (type scenario-rule.fn) :function) "scenario rule should have :fn")
  (assert (= (type scenario-rule.run) :function) "scenario rule should have :run")
  (local scenario-result (ConstraintRunner.run {:rules [scenario-rule]
                                                 :target {:kind :repo :name :test}
                                                 :baseline-data false}))
  (assert scenario-result "scenario runner should return a result table")
  (assert (= (type scenario-result.status) :string) "scenario result should have a status")
  (assert (= scenario-result.status :pass)
          (.. "expected scenario :pass, got " scenario-result.status))
  (assert (= (length scenario-result.diagnostics) 0)
          (.. "expected 0 scenario diagnostics, got " (length scenario-result.diagnostics))))

(table.insert tests {:name "runner recognizes scene sandbox rules"
                     :fn runner-rules-executable})

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "constraints-rules-scene-sandbox"
                        :tests tests})))

{:name "constraints-rules-scene-sandbox"
 :tests tests
 :main main}
