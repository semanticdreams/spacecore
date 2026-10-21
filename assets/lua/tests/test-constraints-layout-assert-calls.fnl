;; Public-rule controls for assertion-call selection. No private selector dependency.
(local H (require :tests.constraints-layout-helpers))
(local tests [])
(local rule-id "layout.interactive-context-assertion")
(local quoted-comment-form "(assert \"clickables;hoverables\" ctx.hoverables) ; clickables\n")
(local quoted-keyword-form "(assert \"clickables\" ;hoverables\n ready)")

(fn snapshot [value seen]
  "Capture raw entries and table identities without exercising dynamic accessors."
  (when (and (= (type value) :table) (not (. seen value)))
    (local entries {})
    (tset seen value entries)
    (each [key item (pairs value)]
      (tset entries key item)
      (snapshot item seen)))
  seen)

(fn assert-unchanged [seen]
  (each [object entries (pairs seen)]
    (each [key value (pairs entries)]
      (assert (rawequal (rawget object key) value) "rule changed an existing fact/reference"))
    (each [key _ (pairs object)]
      (assert (not= (rawget entries key) nil) "rule added a fact field"))))

(fn assert-same [actual expected]
  (assert (= (type actual) (type expected)) "result value type differs")
  (if (= (type expected) :table)
      (do
        (each [key value (pairs expected)] (assert-same (rawget actual key) value))
        (each [key _ (pairs actual)]
          (assert (not= (rawget expected key) nil) "unexpected diagnostic field")))
      (assert (= actual expected) (.. "result differs: " (tostring actual) " / " (tostring expected)))))

(fn definition [name form line]
  {:kind :fn :name name :form form :line line :column 3 :top-level? true})

(fn call [name form]
  {:callee "assert" :enclosing-fn name :form form :line 11 :column 5})

(fn fixture [definitions calls]
  (H.make-file-fact
    {:path "/src/assert-index-control.fnl" :module "assert-index-control"
     :definitions definitions :calls calls
     :accesses [{:path ["ctx" "clickables"] :text "ctx.clickables"}
                {:path ["ctx" "hoverables"] :text "ctx.hoverables"}]}))

(fn diagnostic [name line access]
  (local display (if name name "<anonymous>"))
  {:constraint-id rule-id :family "layout-rendering" :severity :error
   :file "/src/assert-index-control.fnl" :line line :column 3
   :message (.. "function " display " uses " access " without assert in assert-index-control")
   :evidence {:function-name display :interactive-access access}
   :hint (.. "Assert that " access " is available before using it")})

(fn check [ff expected]
  (local Layout (require :constraints.rules.layout))
  (local rule (H.find-rule-by-id (Layout.rules) rule-id))
  (assert rule "interactive-context-assertion rule is required")
  (local ctx (H.make-ctx [ff]))
  (local before (snapshot ctx {}))
  (local result (table.pack (rule.run ctx)))
  (assert (= result.n 1) "rule must return exactly one value, including nil")
  (assert-same (. result 1) expected)
  (assert-unchanged before))

(fn both [name line suffix]
  (definition name (.. "(fn render [ctx] (use ctx.clickables ctx.hoverables) " suffix ")") line))

(fn named-local-collision []
  (local local-def {:kind :local :name "render" :form "(local render other)"})
  (local ff (fixture [local-def (both "render" 10 "1")]
                    [(call "render" "(assert ctx.clickables)")]))
  (check ff [(diagnostic "render" 10 "ctx.hoverables")]))

(fn duplicate-names-ignore-scope []
  (local first (both "render" 10 "1"))
  (local second (both "render" 20 "2"))
  (tset first :enclosing-fn "left")
  (tset second :enclosing-fn "right")
  (check (fixture [first second]
                  [(call "render" "(assert ctx.clickables)")
                   (call "render" "(assert ctx.hoverables)")]) nil))

(fn ordered-groups-and-diagnostics []
  (local ff (fixture [(both "first" 10 "1") (both "second" 20 "2")]
                    [(call "second" "(assert ctx.clickables)")
                     (call "other" {})
                     (call "first" "(assert ctx.hoverables)")
                     (call "second" "(assert ctx.clickables)")]))
  (check ff [(diagnostic "first" 10 "ctx.clickables")
             (diagnostic "second" 20 "ctx.hoverables")]))

(fn empty-name-matches-false-and-nil-enclosure []
  (check (fixture [(both "" 10 "1")]
                  [(call nil "(assert ctx.clickables)")
                   (call false "(assert ctx.hoverables)")]) nil))

(fn matched-empty-forms-cover-all []
  (each [_ form (ipairs [false "" "(assert ready)"])]
    (check (fixture [(both "render" 10 "1")] [(call "render" form)]) nil))
  (check (fixture [(both "render" 10 "1")] [(call "render" nil)]) nil))

(fn matched-empty-does-not-expand-partial-coverage []
  (local ff (fixture [(both "render" 10 "1")]
                    [(call "render" nil) (call "render" false)
                     (call "render" "(assert ctx.clickables)")]))
  (check ff [(diagnostic "render" 10 "ctx.hoverables")]))

(fn unmatched-poison-is-never-cleaned []
  (local not-assert {:callee "print" :enclosing-fn "render" :form {}})
  (check (fixture [(both "render" 10 "1")]
                  [(call "other" {}) not-assert
                   (call "render" "(assert ctx.clickables ctx.hoverables)")]) nil))

(fn unmatched-forms-use-text-fallback []
  (local def (definition "render" "(fn render [ctx] (assert ctx.clickables) (use ctx.hoverables))" 10))
  (check (fixture [def] [(call "other" {})])
         [(diagnostic "render" 10 "ctx.hoverables")]))

(fn matched-presence-suppresses-text-fallback []
  (local def (definition "render" "(fn render [ctx] (assert ctx.hoverables) (use ctx.clickables))" 10))
  (check (fixture [def] [(call "render" "(assert ctx.clickables)")])
         [(diagnostic "render" 10 "ctx.hoverables")]))

(fn nil-false-names-do-not-use-assertions []
  (local nameless (both nil 10 "1"))
  (local falsename (both false 20 "2"))
  (check (fixture [nameless falsename]
                  [(call nil "(assert ctx.clickables ctx.hoverables)")])
         [(diagnostic nil 10 "ctx.clickables") (diagnostic false 20 "ctx.clickables")]))

(fn anonymous-uses-own-text-not-call-facts []
  (local def (definition "<anonymous>" "(fn [ctx] (assert ready) (use ctx.clickables ctx.hoverables))" 10))
  (check (fixture [def] [(call "<anonymous>" {})]) nil)
  (local uncovered (definition "<anonymous>" "(fn [ctx] (use ctx.clickables))" 20))
  (check (fixture [uncovered] [(call "<anonymous>" "(assert ctx.clickables)")])
         [(diagnostic "<anonymous>" 20 "ctx.clickables")]))

(fn recovered-parent-is-included []
  (local ff (fixture [] [(call "recovered" "(assert ctx.clickables ctx.hoverables)")]))
  (tset ff :recovered-parents [(both "recovered" 30 "1")])
  (check ff nil)
  (local uncovered (fixture [] []))
  (tset uncovered :recovered-parents [(both "recovered" 30 "1")])
  (check uncovered [(diagnostic "recovered" 30 "ctx.clickables")]))

(fn strings-comments-and-substring-quirks []
  ;; The existing cleaner is deliberately not a parser; do not normalize it here.
  (check (fixture [(both "render" 10 "1")] [(call "render" quoted-comment-form)])
         [(diagnostic "render" 10 "ctx.clickables")])
  (check (fixture [(both "render" 10 "1")]
                  [(call "render" "(assert notclickables ctx.hoverables)")]) nil)
  (check (fixture [(both "render" 10 "1")]
                  [(call "render" quoted-keyword-form)]) nil))

(fn record-form-access [trace label form]
  (fn [_ key]
    (when (= key :form)
      (table.insert trace label)
      form)))

(fn ordered-form-accesses []
  (local trace [])
  (local first (call "render" nil))
  (local second (call "render" nil))
  (setmetatable first {:__index (record-form-access trace :first "(assert ctx.clickables)")})
  (setmetatable second {:__index (record-form-access trace :second "(assert ctx.hoverables)")})
  (check (fixture [(both "render" 10 "1")]
                  [first (call "unmatched" {}) second]) nil)
  ;; Existing scanner reads form once for truthiness and again for cleaning.
  (assert-same trace [:first :first :second :second]))

(table.insert tests {:name "assert calls retain named/local collisions" :fn named-local-collision})
(table.insert tests {:name "assert calls retain duplicate names across scopes" :fn duplicate-names-ignore-scope})
(table.insert tests {:name "assert calls preserve groups and complete diagnostic order" :fn ordered-groups-and-diagnostics})
(table.insert tests {:name "assert calls empty name matches nil and false enclosures" :fn empty-name-matches-false-and-nil-enclosure})
(table.insert tests {:name "assert calls matched empty forms conservatively cover both keywords" :fn matched-empty-forms-cover-all})
(table.insert tests {:name "assert calls empty forms do not expand partial coverage" :fn matched-empty-does-not-expand-partial-coverage})
(table.insert tests {:name "assert calls ignore unmatched poisonous forms" :fn unmatched-poison-is-never-cleaned})
(table.insert tests {:name "assert calls without a match retain text fallback" :fn unmatched-forms-use-text-fallback})
(table.insert tests {:name "assert calls matched presence suppresses fallback" :fn matched-presence-suppresses-text-fallback})
(table.insert tests {:name "assert calls nil and false names do not use assertions" :fn nil-false-names-do-not-use-assertions})
(table.insert tests {:name "assert calls anonymous definitions use their own text" :fn anonymous-uses-own-text-not-call-facts})
(table.insert tests {:name "assert calls include recovered parent positives and negatives" :fn recovered-parent-is-included})
(table.insert tests {:name "assert calls retain string comment and substring cleaning quirks" :fn strings-comments-and-substring-quirks})
(table.insert tests {:name "assert calls preserve ordered dynamic form accesses" :fn ordered-form-accesses})

(fn selector [ff definitions calls]
  (local Index (require :constraints.rules.layout-assert-calls))
  (Index.create {:file-fact ff :definitions definitions :calls calls}))

(fn selector-fixture [definitions calls]
  (local ff (fixture definitions calls))
  (values ff (selector ff definitions calls)))

(fn private-ordered-original-references []
  (local def (both "render" 10 "1"))
  (local first (call "render" nil))
  (local second (call "render" false))
  (local calls [(call "other" "ignored") first {:callee "print" :enclosing-fn "render"} second first])
  (local (ff lookup) (selector-fixture [def] calls))
  (local before (snapshot ff {}))
  (local group (lookup def))
  (assert (not (rawequal group calls)) "canonical facts must select a group")
  (assert (= (length group) 3))
  (assert (and (rawequal (. group 1) first) (rawequal (. group 2) second)
               (rawequal (. group 3) first)) "group must retain order, duplicates and references")
  (assert (rawequal group (lookup def)) "repeated name must reuse its group")
  (assert (= (length (lookup (definition "missing" "" 1))) 0))
  (assert-unchanged before))

(fn private-empty-name-group []
  (local def (both "" 10 "1"))
  (local first (call nil nil))
  (local second (call false false))
  (local (_ lookup) (selector-fixture [def] [first (call "other" "") second]))
  (local group (lookup def))
  (assert (= (length group) 2))
  (assert (and (rawequal (. group 1) first) (rawequal (. group 2) second))))

(fn private-creation-is-lazy []
  (local def (both "render" 10 "1"))
  (local calls [(call "other" "")])
  (local (_ lookup) (selector-fixture [def] calls))
  ;; Mutation before first demand is observed: creation did not build a cache.
  (tset (. calls 1) :enclosing-fn "render")
  (assert (rawequal (. (lookup def) 1) (. calls 1)))
  (local sentinel {})
  (fn forbidden [] (error sentinel))
  (local poison (setmetatable {} {:__index forbidden :__pairs forbidden :__len forbidden}))
  (local poison-lookup (selector poison poison poison))
  (assert (= (type poison-lookup) :function)))

(fn assert-fallback [ff definitions calls def]
  (local lookup (selector ff definitions calls))
  (assert (rawequal (lookup def) calls) "unsupported shape must return exact scanner input")
  (assert (rawequal (lookup def) calls) "fallback must remain invocation-local and permanent"))

(fn private-malformed-call-containers []
  (local def (both "render" 10 "1"))
  (each [_ calls (ipairs [false 7 "calls" (fn [] nil) [false] [7] ["call"]
                         {1 (call "render" "") 3 (call "render" "")}
                         {1 (call "render" "") :metadata true}])]
    (assert-fallback (fixture [def] calls) [def] calls def))
  (assert-fallback (fixture [def] []) [def] nil def))

(fn private-unsupported-record-fields []
  (local def (both "render" 10 "1"))
  (each [_ value (ipairs [true 12 {} (fn [] nil) (/ 0 0)])]
    (each [_ field (ipairs [:callee :enclosing-fn :form])]
      (local item (call "render" ""))
      (tset item field value)
      (local calls [item])
      (assert-fallback (fixture [def] calls) [def] calls def)))
  (each [_ value (ipairs [{} (fn [] nil) math.huge (- math.huge) (/ 0 0)])]
    (local item (call "render" ""))
    (tset item :ignored value)
    (local calls [item])
    (assert-fallback (fixture [def] calls) [def] calls def)))

(fn private-nonstring-record-keys []
  (local def (both "render" 10 "1"))
  (each [_ key (ipairs [true 1 {} (fn [] nil)])]
    (local item (call "render" ""))
    (tset item key "ignored")
    (local calls [item])
    (assert-fallback (fixture [def] calls) [def] calls def)))

(fn private-whole-definition-guard []
  (local def (both "render" 10 "1"))
  (each [_ value (ipairs [true 7 {} (fn [] nil) (/ 0 0)])]
    (local later (definition value "" 20))
    (local calls [(call "render" "")])
    (local definitions [def later])
    (assert-fallback (fixture definitions calls) definitions calls def)
    (local ff (fixture [def] calls))
    (tset ff :recovered-parents [later])
    (assert-fallback ff [def later] calls def))
  (each [_ definitions (ipairs [false 7 [def false] {1 def 3 def} {1 def :metadata true}])]
    (local calls [(call "render" "")])
    (assert-fallback (fixture definitions calls) [def] calls def)))

(fn private-namespace-guard-and-unrelated-payloads []
  (local def (both "render" 10 "1"))
  (local calls [(call "render" "")])
  (each [_ field (ipairs [:module :path])]
    (each [_ value (ipairs [true 7 {} (fn [] nil) (/ 0 0)])]
      (local ff (fixture [def] calls))
      (tset ff field value)
      (assert-fallback ff [def] calls def)))
  (fn forbidden [] (error "unrelated payload was inspected"))
  (local poison (setmetatable {} {:__index forbidden :__pairs forbidden :__len forbidden :__tostring forbidden}))
  (local ff (fixture [def] calls))
  (tset ff :root poison)
  (tset ff :target poison)
  (tset ff :accesses [poison])
  (local lookup (selector ff [def] calls))
  (assert (not (rawequal (lookup def) calls)) "unrelated object payloads must not disable canonical selection"))

(fn private-metatables-never-invoked []
  (local def (both "render" 10 "1"))
  (fn forbidden [] (error "eligibility invoked a metamethod"))
  (local meta {:__index forbidden :__pairs forbidden :__len forbidden :__eq forbidden :__metatable false})
  (for [location 1 7]
    (local calls [(call "render" "")])
    (local later (definition "later" "" 20))
    (local definitions [def later])
    (local ff (fixture definitions calls))
    (local recovered [(definition "recovered" "" 30)])
    (local all-defs [def later (. recovered 1)])
    (tset ff :recovered-parents recovered)
    (local objects [ff definitions calls (. calls 1) later recovered all-defs])
    (setmetatable (. objects location) meta)
    (assert-fallback ff all-defs calls def))
  (local calls [(call "render" "")])
  (local recovered (setmetatable (definition "recovered" "" 30) meta))
  (local ff (fixture [def] calls))
  (tset ff :recovered-parents [recovered])
  (assert-fallback ff [def recovered] calls def))

(fn private-current-definition-guard []
  (local def (both "render" 10 "1"))
  (local calls [(call "render" "")])
  (fn forbidden [] (error "definition accessor was invoked"))
  (setmetatable def {:__index forbidden :__eq forbidden :__metatable false})
  (assert-fallback (fixture [def] calls) [def] calls def))

(fn private-invocations-do-not-share-cache []
  (local def (both "render" 10 "1"))
  (local calls [(call "render" "")])
  (local (ff first) (selector-fixture [def] calls))
  (local selected (first def))
  (tset (. calls 1) :enclosing-fn "other")
  (local second (selector ff [def] calls))
  (assert (= (length (second def)) 0))
  (assert (= (length selected) 1)))

(table.insert tests {:name "assert index retains ordered original references and duplicate queries" :fn private-ordered-original-references})
(table.insert tests {:name "assert index retains empty name nil and false grouping" :fn private-empty-name-group})
(table.insert tests {:name "assert index factory only captures references" :fn private-creation-is-lazy})
(table.insert tests {:name "assert index returns malformed call containers unchanged" :fn private-malformed-call-containers})
(table.insert tests {:name "assert index declines unsupported scalar and poison record fields" :fn private-unsupported-record-fields})
(table.insert tests {:name "assert index declines nonstring record keys without equality" :fn private-nonstring-record-keys})
(table.insert tests {:name "assert index guards current later original and recovered definitions" :fn private-whole-definition-guard})
(table.insert tests {:name "assert index guards namespace without inspecting unrelated payloads" :fn private-namespace-guard-and-unrelated-payloads})
(table.insert tests {:name "assert index raw eligibility never invokes protected metamethods" :fn private-metatables-never-invoked})
(table.insert tests {:name "assert index declines a dynamic current definition" :fn private-current-definition-guard})
(table.insert tests {:name "assert index cache is private to each invocation" :fn private-invocations-do-not-share-cache})

(fn public-definition-merge-access-order []
  (for [mode 1 3]
    (local trace [])
    (local def (both "render" 10 "1"))
    (local calls [(call "render" "(assert ctx.clickables ctx.hoverables)")])
    (local definitions (if (= mode 1) [def] (= mode 2) false nil))
    (local recovered (if (= mode 1) [] [def]))
    (local ff (fixture [] []))
    (tset ff :calls nil)
    (tset ff :definitions nil)
    (fn read-field [_ key]
      (when (if (= key :calls) true (= key :definitions) true (= key :recovered-parents))
        (table.insert trace key))
      (if (= key :calls) calls
          (= key :definitions) definitions
          (= key :recovered-parents) recovered))
    (setmetatable ff {:__index read-field})
    (check ff nil)
    (assert-same trace [:calls :definitions :recovered-parents :recovered-parents])))

(table.insert tests {:name "assert calls merge preserves calls first single definitions read and repeated recovered reads" :fn public-definition-merge-access-order})

(fn main []
  (local runner (require :tests.runner))
  (runner.run-tests {:name "constraints-layout-assert-calls" :tests tests}))

{:name "constraints-layout-assert-calls" :tests tests :main main}
