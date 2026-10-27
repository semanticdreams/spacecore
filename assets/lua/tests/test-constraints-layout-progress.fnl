;; Public rule parity and synthetic-clock controls for the private rule diagnostic.
(local Layout (require :constraints.rules.layout))
(local Progress (require :tests.constraint-progress))
(local tests [])
(local rule-id "layout.interactive-context-assertion")
(local rule (. (Layout.rules) 3))
(fn add [name run] (table.insert tests {:name (.. "layout-progress " name) :fn run}))
(fn ignore-event [_] nil)

(fn same [actual expected]
  (assert (= (type actual) (type expected)) "value type differs")
  (if (= (type expected) :table)
      (do (each [key value (values next expected)] (same (rawget actual key) value))
          (each [key _ (values next actual)] (assert (not= (rawget expected key) nil))))
      (assert (= actual expected) "value differs")))

(fn snapshot [value seen]
  (when (and (= (type value) :table) (not (. seen value)))
    (local entries {})
    (tset seen value entries)
    (each [key item (values next value)]
      (tset entries key item)
      (snapshot item seen)))
  seen)

(fn unchanged [seen]
  (each [object entries (values next seen)]
    (each [key item (values next entries)] (assert (rawequal (rawget object key) item)))
    (each [key _ (values next object)] (assert (not= (rawget entries key) nil)))))

(fn definition [name form line]
  {:kind :fn : name : form :line (assert line) :column 3})

(fn fixture [defs recovered calls]
  {:facts {:files [{:path "/private/layout-progress.fnl" :module "layout-progress"
                    :definitions defs :recovered-parents recovered :calls (or calls [])
                    :accesses [{:path ["ctx" "clickables"] :text "ctx.clickables"}]}]}})

(fn diagnostic [name line]
  {:constraint-id rule-id :family "layout-rendering" :severity :error
   :file "/private/layout-progress.fnl" : line :column 3
   :message (.. "function " name " uses ctx.clickables without assert in layout-progress")
   :evidence {:function-name name :interactive-access "ctx.clickables"}
   :hint "Assert that ctx.clickables is available before using it"})

(fn parity [make expected]
  (local plain (make))
  (local active (make))
  (assert (not (rawequal plain active)))
  (local before-plain (snapshot plain {}))
  (local before-active (snapshot active {}))
  (local events [])
  (fn record-event [event] (table.insert events event))
  (tset active :observer record-event)
  ;; Observer belongs to the invocation, not the fact graph snapshot.
  (tset (. before-active active) :observer active.observer)
  (local a (table.pack (rule.run plain)))
  (local b (table.pack (rule.run active)))
  (assert (and (= a.n 1) (= b.n 1)) "exactly one return, including nil")
  (same (. a 1) expected)
  (same b a)
  (unchanged before-plain)
  (unchanged before-active)
  events)

(fn uncovered-fixture []
  (fixture [(definition "first" "(fn first [ctx] (use ctx.clickables) 1)" 10)
            (definition "second" "(fn second [ctx] (use ctx.clickables) 2)" 20)] nil nil))

(add "complete ordered diagnostics and exact returns" (fn parity-returns []
  (parity uncovered-fixture [(diagnostic "first" 10) (diagnostic "second" 20)])
  (fn empty-fixture [] (fixture [] nil nil))
  (parity empty-fixture nil)))

(fn selected-fixture []
  (fixture [{:kind :local :name "state" :form "(local state 1)"}
            (definition "render" "(fn render [ctx] (use ctx.clickables))" 10)] nil nil))

(fn assert-event [event edge subphase index ordinal definitions]
  (same event {:phase :rule : rule-id : edge : subphase : index
               :definition-index ordinal : definitions}))

(add "selected ordinal differs from merged D" (fn selected-ordinal []
  (local events (parity selected-fixture [(diagnostic "render" 10)]))
  (assert (= (# events) 6) "missing guarded boundary events")
  (assert-event (. events 1) :begin :interactive-file 1 nil nil)
  (assert-event (. events 2) :begin :interactive-mask 1 1 2)
  (assert-event (. events 3) :end :interactive-mask 1 1 nil)
  (assert-event (. events 4) :begin :interactive-analysis 1 1 nil)
  (assert-event (. events 5) :end :interactive-analysis 1 1 nil)
  (assert-event (. events 6) :end :interactive-file 1 nil 2)
  (each [i event (ipairs events)]
    (each [j other (ipairs events)] (when (not= i j) (assert (not (rawequal event other))))))))

(fn recovered-fixture []
  (local duplicate (definition "dup" "(fn dup [ctx] (use ctx.clickables))" 20))
  (fixture [(definition "outer" "(fn outer [ctx] (fn dup [ctx] (use ctx.clickables)))" 10)
            duplicate (definition "dup" "(fn dup [ctx] (use ctx.clickables))" 20)]
           [(definition "recovered" "(fn recovered [ctx] (use ctx.clickables) 3)" 30)] nil))

(add "recovered duplicate identical and nested masking order" (fn recovered-order []
  ;; Identical duplicate forms mask each other; the outer is masked too.
  (local events (parity recovered-fixture [(diagnostic "recovered" 30)]))
  (assert (= (# events) 18))
  (for [i 1 4] (assert-event (. events (+ 2 (* (- i 1) 4))) :begin :interactive-mask 1 i 4))))

(fn unsafe-fixture []
  (local ctx (selected-fixture))
  (setmetatable (. ctx.facts.files 1) {})
  ctx)

(add "unsafe fallback retains all entries" (fn unsafe-ordinals []
  (local events (parity unsafe-fixture [(diagnostic "render" 10)]))
  (assert (= (# events) 10))
  (assert-event (. events 2) :begin :interactive-mask 1 1 2)
  (assert-event (. events 6) :begin :interactive-mask 1 2 2)))

(fn dynamic-form [trace label form]
  (fn [_ key]
    (when (= key :form) (table.insert trace label) form)))

(fn read-fixture [trace]
  (local first {:kind :fn :name "first" :line 1})
  (local second {:kind :fn :name "second" :line 2})
  (setmetatable first {:__index (dynamic-form trace :first "(fn first [] 1)")})
  (setmetatable second {:__index (dynamic-form trace :second "(fn second [] 2)")})
  (fixture [first second] nil nil))

(add "dynamic definition reads through unchanged masking" (fn definition-reads []
  (local plain-trace [])
  (local active-trace [])
  (local active (read-fixture active-trace))
  (local masks [])
  (var start 0)
  (tset active :observer (fn record-mask [event]
    (when (= event.subphase :interactive-mask)
      (if (= event.edge :begin) (set start (# active-trace))
          (do (local reads [])
              (for [i (+ start 1) (# active-trace)] (table.insert reads (. active-trace i)))
              (table.insert masks reads))))))
  (same (table.pack (rule.run active)) (table.pack (rule.run (read-fixture plain-trace))))
  (same active-trace plain-trace)
  (same masks [[:first :second :second] [:second :first :first]])))

(fn file-read-fixture [trace]
  (assert trace)
  (local ctx (fixture [] nil nil))
  (local ff (. ctx.facts.files 1))
  (tset ff :calls nil)
  (tset ff :definitions nil)
  (fn read [_ key]
    (when (if (= key :calls) true (= key :definitions) true (= key :recovered-parents))
      (table.insert trace key)
      []))
  (setmetatable ff {:__index read})
  ctx)

(add "calls definitions and both recovered reads" (fn file-reads []
  (each [_ active? (ipairs [false true])]
    (local trace [])
    (local ctx (file-read-fixture trace))
    (when active? (tset ctx :observer ignore-event))
    (same (table.pack (rule.run ctx)) {:n 1})
    (same trace [:calls :definitions :recovered-parents :recovered-parents]))))

(add "dynamic assertion read sequence" (fn assertion-reads []
  (each [_ active? (ipairs [false true])]
    (local trace [])
    (local first {:callee "assert" :enclosing-fn "render"})
    (local second {:callee "assert" :enclosing-fn "render"})
    (setmetatable first {:__index (dynamic-form trace :first "(assert ctx.clickables)")})
    (setmetatable second {:__index (dynamic-form trace :second "(assert ctx.hoverables)")})
    (local ctx (fixture [(definition "render" "(fn render [ctx] (use ctx.clickables))" 1)]
                        nil [first second]))
    (when active? (tset ctx :observer ignore-event))
    (same (table.pack (rule.run ctx)) {:n 1})
    (same trace [:first :first :second :second]))))

(add "throwing dynamic accessor preserves raw identity and missing END" (fn throwing-accessor []
  (each [_ active? (ipairs [false true])]
    (local failure {})
    (fn throw-form [_ key] (when (= key :form) (error failure 0)))
    (local def (setmetatable {:kind :fn :name "render"}
                            {:__index throw-form}))
    (local ctx (fixture [def] nil nil))
    (local before (snapshot ctx {}))
    (local events [])
    (fn record-event [event] (table.insert events event))
    (when active? (tset ctx :observer record-event)
          (tset (. before ctx) :observer ctx.observer))
    (local (ok err) (pcall rule.run ctx))
    (assert (and (not ok) (rawequal err failure)))
    (unchanged before)
    (when active?
      (assert (= (# events) 2))
      (assert-event (. events 2) :begin :interactive-mask 1 1 1)))))

(fn harness [N ending]
  (local state {:now 0 :clock-calls 0 :lines [] :stream []})
  (fn now-ms [] (set state.clock-calls (+ state.clock-calls 1)) state.now)
  (fn write [line]
    (table.insert state.lines line)
    (table.insert state.stream (.. line (if ending ending "\n"))))
  (local observer (Progress.create {: now-ms : write :detail-phase :rule}))
  (observer {:phase :discover :edge :begin})
  (observer {:phase :facts :edge :end :count N})
  (observer {:phase :rule :edge :begin : rule-id})
  {: state : observer})

(fn boundary [h now edge subphase index ordinal D]
  (set h.state.now now)
  (h.observer {:phase :rule : rule-id : edge : subphase : index
               :definition-index ordinal :definitions D}))

(fn finish [h now]
  (set h.state.now now)
  (h.observer {:phase :rule : rule-id :edge :end}))

(fn record [line]
  (assert (= (line:sub 1 22) "[CONSTRAINT-PROGRESS] "))
  (local result {})
  (each [key value (line:gmatch "([%w_]+)=([^ ]+)")]
    (assert (= (. result key) nil) "duplicate output field")
    (tset result key (if (tonumber value) (tonumber value) value)))
  result)

(fn summary [outcome begun ended D masks analyses elapsed mask pending-file pending-def stage pending-D known pending-ms]
  {:phase :rule :subphase :interactive : outcome :files_begun begun :files_ended ended
   :definitions D : masks : analyses :elapsed_ms elapsed :mask_ms mask :remaining_ms (- elapsed mask)
   :pending_file pending-file :pending_def pending-def :pending_stage stage
   :pending_definitions pending-D :definitions_known known :pending_ms pending-ms})

(fn exercise-one [h index base D]
  (boundary h (+ base 2) :begin :interactive-file index)
  (boundary h (+ base 5) :begin :interactive-mask index 1 D)
  (boundary h (+ base 12) :end :interactive-mask index 1)
  (boundary h (+ base 14) :begin :interactive-analysis index 1)
  (boundary h (+ base 18) :end :interactive-analysis index 1)
  (boundary h (+ base 20) :end :interactive-file index nil D))

(add "consumer exact complete times and distinct selected population" (fn consumer-complete []
  (local h (harness 2))
  (assert (= (# h.state.lines) 0) "other pipeline events must be silent")
  (exercise-one h 1 0 2)
  (boundary h 23 :begin :interactive-file 2)
  (boundary h 25 :end :interactive-file 2 nil 0)
  (finish h 30)
  (assert (= (# h.state.lines) 5))
  (same (record (. h.state.lines 1))
        {:phase :rule :subphase :interactive :edge :begin :file_index 1 :at_ms 2 :stage :setup})
  (same (record (. h.state.lines 2))
        {:phase :rule :subphase :interactive :edge :end :file_index 1 :definitions 2
         :masks 1 :analyses 1 :elapsed_ms 18 :mask_ms 7 :remaining_ms 11})
  (same (record (. h.state.lines 5)) (summary :complete 2 2 2 1 1 30 7 0 0 :none 0 0 0))
  (assert (= (string.sub (. h.state.lines 5) 23 32) "aggregate "))
  (local calls h.state.clock-calls)
  (finish h 40)
  (assert (= h.state.clock-calls calls) "summary only once, no subsequent clocks")))

(add "consumer empty inventory completes with one summary" (fn consumer-empty []
  (local h (harness 0))
  (finish h 4)
  (assert (= (# h.state.lines) 1))
  (same (record (. h.state.lines 1)) (summary :complete 0 0 0 0 0 4 0 0 0 :none 0 0 0))))

(fn pending-case [stage]
  (local h (harness 1))
  (boundary h 2 :begin :interactive-file 1)
  (when (not= stage :setup) (boundary h 5 :begin :interactive-mask 1 1 2))
  (when (or (= stage :between) (= stage :analysis)) (boundary h 12 :end :interactive-mask 1 1))
  (when (= stage :analysis) (boundary h 14 :begin :interactive-analysis 1 1))
  (assert (= (# h.state.lines) 1) "definition boundaries aggregate without output history")
  (finish h 30)
  (local mask (if (= stage :mask) 25 (= stage :setup) 0 7))
  (local masks (if (or (= stage :between) (= stage :analysis)) 1 0))
  (local since (if (= stage :setup) 2 (= stage :mask) 5 (= stage :between) 12 14))
  (same (record (. h.state.lines 2))
        (summary :unfinished 1 0 (if (= stage :setup) 0 2) masks 0 30 mask
                 1 (if (= stage :setup) 0 1) stage (if (= stage :setup) 0 2)
                 (if (= stage :setup) 0 1) (- 30 since))))

(add "consumer honest pending setup mask analysis between" (fn consumer-pending []
  (each [_ stage (ipairs [:setup :mask :between :analysis])] (pending-case stage))
  (local h (harness 1))
  (finish h 10)
  (same (record (. h.state.lines 1)) (summary :unfinished 0 0 0 0 0 10 0 0 0 :none 0 0 0))))

(add "consumer workload unwind retains pending ordinal and END-only counts" (fn consumer-unwind []
  (local h (harness 1))
  (boundary h 2 :begin :interactive-file 1)
  (boundary h 5 :begin :interactive-mask 1 1 4)
  (boundary h 8 :end :interactive-mask 1 1)
  (boundary h 9 :begin :interactive-analysis 1 1)
  (boundary h 10 :end :interactive-analysis 1 1)
  (boundary h 12 :begin :interactive-mask 1 2 4)
  (fn fail-work [] (error "synthetic workload failure"))
  (assert (not (pcall fail-work)))
  (assert (= (# h.state.lines) 1) "workload unwind alone must not manufacture summary")
  (finish h 40)
  (same (record (. h.state.lines 2)) (summary :unfinished 1 0 4 1 1 40 31 1 2 :mask 4 1 28))))

(fn stream-budget [h N ending]
  (assert (<= (# h.state.lines) (+ (* 2 N) 1)))
  (var reserved 0)
  (each [i line (ipairs h.state.lines)]
    (assert (<= (+ (# line) 2) 512))
    (assert (not (line:find "[%c]")))
    (assert (= (. h.state.stream i) (.. line ending)))
    (set reserved (+ reserved (# line) 2)))
  (assert (<= reserved (* 2 1024 1024)))
  (assert (<= (# (table.concat h.state.stream)) reserved))
  reserved)

(fn cap-case [N ending]
  (local h (harness N ending))
  (for [index 1 (+ N 1)]
    (boundary h 1 :begin :interactive-file index)
    (boundary h 2 :end :interactive-file index nil 0))
  (local last (. h.state.lines (# h.state.lines)))
  (assert (= (. (record last) :outcome) :cap) "single terminal cap uses canonical summary schema")
  (local calls h.state.clock-calls)
  (local count (# h.state.lines))
  (finish h 50)
  (h.observer (setmetatable {} {:__index (fn forbidden [_ _key] (error "capped observer read"))}))
  (assert (= calls h.state.clock-calls))
  (assert (= count (# h.state.lines)))
  (local reserved (stream-budget h N ending))
  (if (= N 0) (do (assert (= count 1))
                  (same (record last) (summary :cap 1 0 0 0 0 1 0 1 0 :setup 0 0 0)))
      (> N 10000) (assert (> reserved (- (* 2 1024 1024) 1024)))
      (assert (= count (+ (* 2 N) 1)))))

(add "consumer caps entire mode with LF and CRLF terminal reservation" (fn consumer-caps []
  (each [_ ending (ipairs ["\n" "\r\n"])]
    (cap-case 0 ending)
    (cap-case 2 ending)
    (cap-case 20000 ending))))

(add "consumer hostile extras private sentinels and maximum finite clock" (fn consumer-privacy []
  (local h (harness 1))
  (local private "PRIVATE_LAYOUT_PROGRESS_SENTINEL")
  (fn forbidden [...] (error "must not traverse or stringify"))
  (local poison (setmetatable {} {:__index forbidden :__pairs forbidden :__tostring forbidden}))
  (local event (setmetatable {:phase :rule : rule-id :edge :begin :subphase :interactive-file :index 1
                             :file private :form poison :source private :name poison :environment poison}
                            {:__index forbidden :__pairs forbidden}))
  (h.observer event)
  (set h.state.now 1.7976931348623157e308)
  (finish h h.state.now)
  (assert (= (# h.state.lines) 2))
  (local text (table.concat h.state.lines))
  (assert (not (text:find private 1 true)))
  (assert (not (text:find "inf" 1 true)))
  (stream-budget h 1 "\n")))

(fn invalid-number-case [value field]
  (local h (harness 1))
  (local event {:phase :rule : rule-id :edge :begin :subphase :interactive-file :index 1})
  (if (= field :clock) (set h.state.now value)
      (= field :count) (do (set event.phase :facts) (set event.edge :end)
                          (set event.subphase nil) (set event.count value))
      (= field :definitions) (do (boundary h 1 :begin :interactive-file 1)
                                (set event.subphase :interactive-mask)
                                (set event.definition-index 1) (set event.definitions value))
      (= field :definition-index) (do (boundary h 1 :begin :interactive-file 1)
                                     (set event.subphase :interactive-mask)
                                     (set event.definitions 2) (set event.definition-index value))
      (set event.index value))
  (assert (not (pcall h.observer event)) "invalid numeric input must fail explicitly"))

(add "consumer rejects invalid indices counts and arithmetic overflow" (fn consumer-invalid []
  (each [_ value (ipairs [(/ 0 0) math.huge (- math.huge) -1])]
    (each [_ field (ipairs [:index :definition-index :definitions :count :clock])]
      ;; Backward finite clock readings are intentionally clamped, as in other modes.
      (when (not (and (= field :clock) (= value -1))) (invalid-number-case value field))))
  (invalid-number-case 0 :index)
  (invalid-number-case 0 :definition-index)
  (invalid-number-case 1.5 :count)
  (invalid-number-case 1.7976931348623157e308 :count)
  (local h (harness 1))
  (set h.state.now (- 1.7976931348623157e308))
  (h.observer {:phase :select :edge :begin})
  ;; A fresh origin at -maxfinite makes subtracting +maxfinite overflow.
  (fn now-ms [] h.state.now)
  (local observer (Progress.create {: now-ms :write ignore-event :detail-phase :rule}))
  (observer {:phase :facts :edge :end :count 0})
  (set h.state.now 1.7976931348623157e308)
  (assert (not (pcall observer {:phase :rule : rule-id :edge :begin})))))

(fn upvalue [owner wanted]
  (var index 1)
  (var found nil)
  (while (and (not found) (debug.getupvalue owner index))
    (local (name value) (debug.getupvalue owner index))
    (when (= name wanted) (set found {: index : value}))
    (set index (+ index 1)))
  (assert found (.. "missing private upvalue " wanted))
  found)

(add "inactive factory and raw context read with active control" (fn inactive-factory []
  (local factory (upvalue rule.run :make_interactive_observation))
  (local failure {})
  (var reads 0)
  (fn forbidden [_] (error failure 0))
  (fn context-read [_ key] (when (= key :observer) (set reads (+ reads 1)) (error failure 0)))
  (local ctx (fixture [] nil nil))
  (setmetatable ctx {:__index context-read})
  (debug.setupvalue rule.run factory.index forbidden)
  (local (ok result) (pcall rule.run ctx))
  (tset ctx :observer ignore-event)
  (local (active-ok active-error) (pcall rule.run ctx))
  (debug.setupvalue rule.run factory.index factory.value)
  (assert (and ok (= result nil) (= reads 0)))
  (assert (and (not active-ok) (rawequal active-error failure)))))

(fn private-owner []
  (local suite (require :tests.test-constraints-default-run))
  (var owner nil)
  (each [_ test-case (ipairs suite.tests)]
    (when (= test-case.name "constraint progress exact opt-in and disabled output")
      (set owner (. (upvalue test-case.fn :full_repo_observer) :value))))
  (assert owner)
  owner)

(add "nil owner factory clock writer spies and active controls" (fn inactive-owner []
  (local owner (private-owner))
  (local original Progress.create)
  (local failure {})
  (var calls 0)
  (fn forbidden [...] (set calls (+ calls 1)) (error failure 0))
  (set Progress.create forbidden)
  (fn disabled []
    (same (table.pack (owner nil forbidden forbidden)) {:n 1})
    (each [_ raw (ipairs ["" "0" "true" "01" "1 " "2"])]
      (same (table.pack (owner raw forbidden forbidden)) {:n 1})))
  (local (ok err) (pcall disabled))
  (local (active-ok active-error) (pcall owner "1" forbidden forbidden))
  (set Progress.create original)
  (assert ok (tostring err))
  (assert (= calls 1) "only the active control enters any observation factory")
  (assert (and (not active-ok) (rawequal active-error failure)))
  (local (clock-ok clock-error) (pcall owner "1" forbidden ignore-event))
  (assert (and (not clock-ok) (rawequal clock-error failure)))
  (fn zero [] 0)
  (local observer (owner "1" zero forbidden))
  (observer {:phase :facts :edge :end :count 1})
  (observer {:phase :rule : rule-id :edge :begin})
  (local (write-ok write-error)
    (pcall observer {:phase :rule : rule-id :edge :begin :subphase :interactive-file :index 1}))
  (assert (and (not write-ok) (rawequal write-error failure)))))

(add "active consumer clock failure preserves raw identity" (fn consumer-clock-error []
  (local failure {})
  (var broken false)
  (var writes 0)
  (fn now-ms [] (if broken (error failure 0) 0))
  (fn write [_] (set writes (+ writes 1)))
  (local observer (Progress.create {: now-ms : write :detail-phase :rule}))
  (observer {:phase :facts :edge :end :count 0})
  (set broken true)
  (local (ok err) (pcall observer {:phase :rule : rule-id :edge :begin}))
  (assert (and (not ok) (rawequal err failure) (= writes 0)))))

(fn with-pipeline [facts run body]
  (local Runner (require :constraints.runner))
  (local Source (require :constraints.source))
  (local Facts (require :constraints.facts))
  (local Registry (require :constraints.rules.init))
  (local old-discover Source.discover)
  (local old-extract Facts.extract)
  (local old-rules Registry.all-rules)
  (fn discover [_target _observer] facts.files)
  (fn extract [records _observer] (assert (rawequal records facts.files)) facts)
  (fn all-rules [] [{:id rule-id :family :layout-rendering :kind :static :targets [:files] : run}])
  (set Source.discover discover)
  (set Facts.extract extract)
  (set Registry.all-rules all-rules)
  (local (ok result) (pcall body Runner {:kind :files :files [] :suites []}))
  (set Source.discover old-discover)
  (set Facts.extract old-extract)
  (set Registry.all-rules old-rules)
  (if ok result (error result 0)))

(add "public pipeline complete boundaries do not imply acceptance or D counts" (fn pipeline-complete []
  (local ctx (selected-fixture))
  (local h (harness 1))
  ;; Use a fresh consumer: the runner, not this harness, owns Facts/rule edges.
  (fn now-ms [] 0)
  (fn write [line] (table.insert h.state.lines line))
  (local observer (Progress.create {: now-ms : write :detail-phase :rule}))
  (fn check [Runner target]
    (local plain (Runner.run-target target {:baseline-data false}))
    (local actual (Runner.run-target target {:baseline-data false : observer}))
    (same actual plain)
    (assert (= actual.status :violations))
    (same (record (. h.state.lines 3)) (summary :complete 1 1 2 1 1 0 0 0 0 :none 0 0 0)))
  (with-pipeline ctx.facts rule.run check)))

(fn hook-equals [expected expected-mask expected-count]
  (local (hook mask count) (debug.gethook))
  (assert (and (= hook expected) (= mask expected-mask) (= count expected-count))
          "deadline hook must be restored before teardown/outside propagation"))

(fn with-hook [body]
  (local (old mask count) (debug.gethook))
  (fn sentinel [] nil)
  (debug.sethook sentinel "" 7777)
  (local (ok result) (pcall body sentinel))
  (if old (debug.sethook old mask count) (debug.sethook nil "" 0))
  (if ok result (error result 0)))

(fn callback-failure [location]
  (local failure {})
  (local lines [])
  (fn now-ms [] 0)
  (fn write [line]
    (when (and (= location :summary) (= (. (record line) :outcome) :complete)) (error failure 0))
    (table.insert lines line))
  (local consumer (Progress.create {: now-ms : write :detail-phase :rule}))
  (var top-ended false)
  (fn observer [event]
    (when (and (= event.phase :rule) (= event.edge :end) (= event.subphase nil)) (set top-ended true))
    (when (and (= event.edge :begin)
               (= event.subphase (if (= location :file) :interactive-file :interactive-mask))
               (not= location :summary)) (error failure 0))
    (consumer event))
  (fn check [Runner target]
    (fn guarded [sentinel]
      (local (ok err) (pcall Runner.run-target target {:baseline-data false :timeout-seconds 10 : observer}))
      (hook-equals sentinel "" 7777)
      (assert (and (not ok) (rawequal err failure)))
      (assert (= top-ended (= location :summary)))
      (assert (= (# lines) (if (= location :file) 0 (= location :mask) 1 2)))
      (each [_ line (ipairs lines)] (assert (= (. (record line) :outcome) nil))))
    (with-hook guarded))
  (with-pipeline (. (selected-fixture) :facts) rule.run check))

(add "file mask and summary callback errors escape without fabricated summary" (fn callback-errors []
  (callback-failure :file)
  (callback-failure :mask)
  (callback-failure :summary)))

(fn deadline-result [mode state ok err]
  (when (= mode :secondary-error) (assert state.secondary-raised "exercise the secondary sink error"))
  (if (= mode :success)
      (do (assert ok) (assert (= (. (record (. state.lines 3)) :outcome) :complete)))
      (= mode :sink-error)
      (assert (and (not ok) (err:find "synthetic secondary sink failure" 1 true) (= (# state.lines) 0)))
      (do (assert (and (not ok) (err:find "test timed out after 1s" 1 true)))
          (assert (= (# state.lines) (if (= mode :caught-timeout) 2 1)))
          (when (= mode :caught-timeout)
            (local pending (record (. state.lines 2)))
            (assert (= pending.outcome :unfinished))
            (assert (= pending.pending_stage :mask))
            (assert (= pending.masks 0))
            (assert (= pending.analyses 0))))))

(fn deadline-case [mode]
  (local TestRunner (require :tests.runner))
  (local state {:now 0 :lines [] :teardown false :installed nil})
  (fn now-ms [] state.now)
  (fn expire []
    (set state.now 1001)
    (local hook (debug.gethook))
    (assert hook)
    (hook))
  (fn form-read [_ key]
    (when (= key :form)
      (if (= mode :caught-timeout) (expire)
          (= mode :secondary-error) (expire)
          "(fn render [ctx] (use ctx.clickables))")))
  (local def (setmetatable {:kind :fn :name "render" :line 1} {:__index form-read}))
  (local ctx (fixture [def] nil nil))
  (fn write [line]
    ;; The original timeout hook disables itself after delivery so unwind can run.
    (if (>= state.now 1000) (hook-equals nil nil nil) (hook-equals state.installed "" 10000))
    (when (if (= mode :sink-error) true
              (and (= mode :secondary-error) (. (record line) :outcome)))
      (set state.secondary-raised true)
      (error "synthetic secondary sink failure"))
    (table.insert state.lines line))
  (local consumer (Progress.create {: now-ms : write :detail-phase :rule}))
  (fn observer [event]
    (when (and (= mode :relay-timeout) (= event.edge :begin) (= event.subphase :interactive-mask)) (expire))
    (consumer event))
  (fn check [Runner target]
    (fn guarded [sentinel]
      (fn body []
        (set state.installed (debug.gethook))
        (assert (not= state.installed sentinel))
        (Runner.run-target target {:baseline-data false : observer}))
      (fn teardown [] (hook-equals sentinel "" 7777) (set state.teardown true))
      (local (ok err cleanup) (TestRunner.run-case {:name "synthetic interactive progress" :fn body : teardown}
                                                 1 nil now-ms))
      (hook-equals sentinel "" 7777)
      (assert (and state.teardown (= (# cleanup) 0)))
      (deadline-result mode state ok err))
    (with-hook guarded))
  (with-pipeline ctx.facts rule.run check))

(add "nested deadline success restores hook before teardown" (fn deadline-success [] (deadline-case :success)))
(add "nested deadline sink failure restores hook before teardown" (fn deadline-sink [] (deadline-case :sink-error)))
(add "nested caught timeout preserves unfinished mask and latch" (fn deadline-caught [] (deadline-case :caught-timeout)))
(add "original timeout latch wins secondary summary failure" (fn deadline-secondary [] (deadline-case :secondary-error)))
(add "relay timeout leaves summary missing and restores hook" (fn deadline-relay [] (deadline-case :relay-timeout)))

(add "skipped parameter analysis still emits normal boundaries" (fn skipped-analysis []
  (fn make [] (fixture [(definition "skip" "(fn skip [clickables] (use clickables))" 1)] nil nil))
  (local events (parity make nil))
  (assert (= (# events) 6))
  (assert-event (. events 5) :end :interactive-analysis 1 1 nil)))

(add "between after completed analysis has no pending ordinal" (fn completed-between []
  (local h (harness 1))
  (boundary h 2 :begin :interactive-file 1)
  (boundary h 3 :begin :interactive-mask 1 1 2)
  (boundary h 7 :end :interactive-mask 1 1)
  (boundary h 9 :begin :interactive-analysis 1 1)
  (boundary h 12 :end :interactive-analysis 1 1)
  (finish h 20)
  (same (record (. h.state.lines 2)) (summary :unfinished 1 0 2 1 1 20 4 1 0 :between 2 1 8))))

(add "capped consumer ceases formatting with active control" (fn capped-formatting []
  (local capped (harness 0))
  (boundary capped 1 :begin :interactive-file 1)
  (local active (harness 1))
  (local original string.format)
  (local failure {})
  (fn forbidden [...] (error failure 0))
  (set string.format forbidden)
  (local (ok err) (pcall boundary capped 2 :end :interactive-file 1 nil 0))
  (local (active-ok active-error) (pcall boundary active 1 :begin :interactive-file 1))
  (set string.format original)
  (assert ok (tostring err))
  (assert (and (not active-ok) (rawequal active-error failure)))))

(add "rule mode ignores unrelated payloads and uses actual Facts inventory" (fn actual-inventory []
  (local h (harness 1))
  (local calls h.state.clock-calls)
  (h.observer {:phase :rule :rule-id "structure.style-doctrine" :edge :begin :count math.huge})
  (h.observer {:phase :facts :edge :end :subphase :extract :count math.huge})
  (h.observer {:phase :rule : rule-id :edge :begin :subphase :unknown :index math.huge})
  (assert (= calls h.state.clock-calls))
  (exercise-one h 1 0 2)
  (finish h 10) ;; Backward samples clamp to the preceding file END at 20.
  (same (record (. h.state.lines 3)) (summary :complete 1 1 2 1 1 20 7 0 0 :none 0 0 0))))

(add "aggregate count overflow is explicit without terminal fabrication" (fn count-overflow []
  (local h (harness 2))
  (boundary h 1 :begin :interactive-file 1)
  (boundary h 2 :end :interactive-file 1 nil 9007199254740991)
  (boundary h 3 :begin :interactive-file 2)
  (local (ok _) (pcall boundary h 4 :end :interactive-file 2 nil 1))
  (assert (not ok))
  (assert (= (# h.state.lines) 3))
  (each [_ line (ipairs h.state.lines)] (assert (= (. (record line) :outcome) nil)))
  (stream-budget h 2 "\n")))

(fn main [] ((. (require :tests.runner) :run-tests) {:name "constraints-layout-progress" : tests}))
{:name "constraints-layout-progress" : tests : main}
