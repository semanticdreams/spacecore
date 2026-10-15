(local Graph (require :graph/init))
(local tests [])
(local ref {:key "test-meter:one"})

(fn succeeds [result]
  (assert (= result.ok true) (.. "expected success, got " (or (and result.error result.error.code) "invalid envelope")))
  result.value)

(fn fails [result code outcome]
  (assert (= result.ok false) "expected explicit failure")
  (assert (= result.error.code code) (.. "expected " code ", got " (tostring result.error.code)))
  (assert (= result.error.outcome (or outcome "not-committed")))
  (assert (= result.error.result nil) "unchecked payload must not escape"))

(fn rejects [f]
  (local (ok _err) (pcall f))
  (assert (not ok) "expected validation rejection"))

(fn invalid-callback [] true)

(fn hidden-handler [] (error "hidden handler executed"))

(fn meter-handler [state]
  (fn adjust [_ref args _preconditions]
    (set state.calls (+ state.calls 1))
    (set state.level (+ state.level args.delta))
    (if (= state.mode "throw") (error "after mutation")
        (= state.mode "bad") {:ok true :value {:level "bad" :changed true}}
        (= state.mode "callback") {:ok true :value {:level state.level :changed invalid-callback}}
        {:ok true :value {:level state.level :changed (not (= args.delta 0))}})))

(fn meter []
  (local integer {:type "integer" :min -100 :max 100})
  (local metadata {:id "meter.adjust" :description "Adjust meter"
                   :arguments {:type "record" :fields {:delta integer :reason {:type "string" :min-bytes 0 :max-bytes 64}} :optional []}
                   :result {:type "record" :fields {:level integer :changed {:type "boolean"}} :optional []}
                   :effect "write" :revision "none"})
  (local state {:level 0 :calls 0 :mode "normal"})
  (fn describe-meter [requested]
    (if (= requested.key ref.key)
        {:ok true :value {:ref ref :summary "A test meter" :capabilities [metadata]}}
        {:ok false :error {:code "not-found" :message "No meter" :outcome "not-committed"}}))
  (local access {:entry-points [{:ref ref :summary "A test meter"}]
                :describe describe-meter
                :handlers {"meter.adjust" (meter-handler state) "hidden" hidden-handler}})
  (values access state metadata))

(fn install [graph access]
  (graph:register-key-loader "test-meter" (fn [_key] (error "visual loader must never execute"))
                             {:owner-id "test-owner" :access access}))

(fn generic-nonvisual-meter []
  (local graph (Graph {:entity-events? false}))
  (assert (= (type graph.discover) "function") "Graph must expose generic discover")
  (local (access state _metadata) (meter))
  (install graph access)
  (local page (succeeds (graph:discover {})))
  (assert (= (. page.items 1 :ref :key) ref.key))
  (assert (= page.has-more false))
  (local description (succeeds (graph:describe (. page.items 1 :ref))))
  (local capability (. description.capabilities 1))
  (local result (succeeds (graph:invoke description.ref capability.id {:delta 3 :reason "calibrate λ"} {})))
  (assert (= result.level 3))
  (assert (= result.changed true))
  (assert (= state.calls 1))
  (assert (= (graph:node-count) 0))
  (assert (= (graph:edge-count) 0))
  (graph:drop))

(fn arguments-and-preconditions []
  (local graph (Graph {:entity-events? false}))
  (local (access state metadata) (meter))
  (install graph access)
  (each [_ args (ipairs [{:delta 1.5 :reason "x"} {:delta 101 :reason "x"} {:delta 1} {:delta 1 :reason "x" :extra true} {:delta 1 :reason (string.rep "x" 65)}])]
    (fails (graph:invoke ref "meter.adjust" args {}) "invalid-arguments"))
  (each [_ pre (ipairs [{:revision "r"} {:extra true} false])]
    (fails (graph:invoke ref "meter.adjust" {:delta 1 :reason "x"} pre) "invalid-arguments"))
  (assert (= state.calls 0))
  (set metadata.revision "required")
  (each [_ pre (ipairs [{} {:revision ""} {:revision (string.rep "x" 513)}])]
    (fails (graph:invoke ref "meter.adjust" {:delta 1 :reason "x"} pre) "invalid-arguments"))
  (succeeds (graph:invoke ref "meter.adjust" {:delta 1 :reason "x"} {:revision "revision-1"}))
  (assert (= state.calls 1))
  (graph:drop))

(fn description-and-registration-isolation []
  (local graph (Graph {:entity-events? false}))
  (local (access state _metadata) (meter))
  (install graph access)
  (set (. access.entry-points 1 :summary) "changed by installer")
  (set (. access.handlers "meter.adjust") (fn [] (error "mutated handler mapping")))
  (local first (succeeds (graph:describe ref)))
  (set (. first.capabilities 1 :arguments :fields :delta :max) 999)
  (set (. first.capabilities 1 :id) "hidden")
  (local second (succeeds (graph:describe ref)))
  (assert (= (. second.capabilities 1 :id) "meter.adjust"))
  (assert (= (. second.capabilities 1 :arguments :fields :delta :max) 100))
  (assert (= (. (succeeds (graph:discover {})) :items 1 :summary) "A test meter"))
  (fails (graph:invoke ref "hidden" {} {}) "unsupported-capability")
  (succeeds (graph:invoke ref "meter.adjust" {:delta 1 :reason "x"} {}))
  (assert (= state.calls 1))
  (graph:drop))

(fn current-description-is-validated []
  (local graph (Graph {:entity-events? false}))
  (local (access state metadata) (meter))
  (install graph access)
  (set metadata.effect "execute")
  (fails (graph:describe ref) "invalid-result")
  (fails (graph:invoke ref "meter.adjust" {:delta 1 :reason "x"} {}) "invalid-result")
  (assert (= state.calls 0))
  (set metadata.effect "write")
  (set metadata.arguments.extra true)
  (fails (graph:describe ref) "invalid-result")
  (set metadata.arguments.extra nil)
  (set metadata.id "missing-handler")
  (fails (graph:describe ref) "invalid-result")
  (graph:drop))

(fn invalid-write-results-and-exceptions []
  (local graph (Graph {:entity-events? false}))
  (local (access state metadata) (meter))
  (install graph access)
  (each [_ mode (ipairs ["bad" "callback"])]
    (set state.mode mode)
    (fails (graph:invoke ref "meter.adjust" {:delta 1 :reason "x"} {}) "invalid-result" "committed"))
  (set state.mode "throw")
  (fails (graph:invoke ref "meter.adjust" {:delta 1 :reason "x"} {}) "internal-error" "unknown")
  (set metadata.effect "read")
  (fails (graph:invoke ref "meter.adjust" {:delta 0 :reason "x"} {}) "internal-error")
  (set state.mode "bad")
  (fails (graph:invoke ref "meter.adjust" {:delta 0 :reason "x"} {}) "invalid-result")
  (graph:drop))

(fn ownership-replacement-and-drop []
  (local graph (Graph {:entity-events? false}))
  (local other (Graph {:entity-events? false}))
  (local (access _state _metadata) (meter))
  (local handle (install graph access))
  (local foreign (install other access))
  (rejects #(install graph access))
  (rejects #(graph:unregister-key-loader foreign))
  (rejects #(graph:unregister-key-loader "test-meter" {:owner-id "wrong"}))
  (succeeds (graph:describe ref))
  (handle:unregister)
  (assert (handle:unregister) "inactive unregister is idempotent")
  (fails (graph:describe ref) "unavailable")
  (assert (= (length (. (succeeds (graph:discover {})) :items)) 0))
  (local (new-access state metadata) (meter))
  (local handler (. new-access.handlers "meter.adjust"))
  (set metadata.id "meter.adjust-v2")
  (set (. new-access.handlers "meter.adjust-v2") handler)
  (local replacement (install graph new-access))
  (rejects #(handle:unregister))
  (fails (graph:invoke ref "meter.adjust" {:delta 1 :reason "old"} {}) "unsupported-capability")
  (succeeds (graph:invoke ref "meter.adjust-v2" {:delta 2 :reason "new"} {}))
  (assert (= state.level 2))
  (graph:drop)
  (assert (= replacement.active? false))
  (fails (graph:describe ref) "unavailable")
  (fails (graph:invoke ref "meter.adjust-v2" {} {}) "unavailable")
  (assert (= (length (. (succeeds (graph:discover {})) :items)) 0))
  (other:drop))

(fn visual-only-and-invalid-requests []
  (local graph (Graph {:entity-events? false}))
  (graph:register-key-loader "visual" (fn [] (error "not nonvisual")))
  (fails (graph:describe {:key "visual:one"}) "not-exposed")
  (fails (graph:invoke {:key "visual:one"} "anything" {} {}) "not-exposed")
  (fails (graph:describe {:key "absent:one"}) "unavailable")
  (each [_ bad (ipairs [false {} {:key ""} {:key 3} {:key "x" :extra true}])]
    (fails (graph:describe bad) "invalid-arguments"))
  (local (access _state _metadata) (meter))
  (install graph access)
  (fails (graph:describe {:key "test-meter:missing"}) "not-found")
  (fails (graph:invoke ref false {} {}) "invalid-arguments")
  (graph:drop))

(fn discovery-pagination-and-registration-validation []
  (local graph (Graph {:entity-events? false}))
  (fn visual-loader [] (error "visual"))
  (fn unused-description [] nil)
  (for [i 1 8]
    (local scheme (string.format "test-%02d" i))
    (local entries [])
    (for [j 8 1 -1]
      (table.insert entries {:ref {:key (.. scheme ":" j)} :summary "entry"}))
    (graph:register-key-loader scheme visual-loader
                               {:access {:entry-points entries :describe unused-description :handlers {}}}))
  (assert (= (length (. (succeeds (graph:discover {})) :items)) 20))
  (assert (= (length (. (succeeds (graph:discover {:limit 50})) :items)) 50))
  (var cursor nil)
  (var last "")
  (var count 0)
  (var more true)
  (while more
    (local page (succeeds (graph:discover {:limit 7 :cursor cursor})))
    (each [_ entry (ipairs page.items)]
      (assert (> entry.ref.key last))
      (set last entry.ref.key)
      (set count (+ count 1)))
    (set more page.has-more)
    (set cursor page.cursor)
    (assert (= (not (= cursor nil)) more)))
  (assert (= count 64))
  (each [_ args (ipairs [{:limit 0} {:limit 1.5} {:extra true} {:cursor "garbage"}])]
    (fails (graph:discover args) "invalid-arguments"))
  (fails (graph:discover {:limit 51}) "limit-exceeded")
  (fails (graph:discover {:cursor (string.rep "x" 2049)}) "limit-exceeded")
  (local (access _state _metadata) (meter))
  (set access.entry-points [{:ref {:key "foreign:one"} :summary "bad"}])
  (rejects #(install graph access))
  (assert (= (graph:has-key-loader-for-key ref.key) false) "invalid access must not publish loader")
  (set access.entry-points [])
  (for [_ 1 9] (table.insert access.entry-points {:ref ref :summary "too many"}))
  (rejects #(install graph access))
  (graph:drop))

(fn shape-vocabulary-and-declarations []
  (local Shapes (require :graph/capability-shapes))
  (local examples [[{:type "string" :min-bytes 0 :max-bytes 8} "λ"]
                   [{:type "integer" :min -3 :max 3} 0]
                   [{:type "boolean"} false]
                   [{:type "enum" :values ["yes" "no"]} "yes"]
                   [{:type "array" :items {:type "boolean"} :max-items 3} [true false]]
                   [{:type "record" :fields {:flag {:type "boolean"}} :optional ["flag"]} {}]])
  (each [_ example (ipairs examples)]
    (assert (= (Shapes.validate-shape! (. example 1)) true))
    (Shapes.check! (. example 1) (. example 2)))
  (each [_ shape (ipairs [{:type "any"} {:type "boolean" :extra true}
                         {:type "string" :min-bytes 2 :max-bytes 1}
                         {:type "integer" :min 0} {:type "integer" :min 0 :max math.huge}
                         {:type "integer" :min 0.5 :max 1}
                         {:type "enum" :values []} {:type "enum" :values ["a" "a"]}
                         {:type "enum" :values [1]}
                         {:type "record" :fields {} :optional ["absent"]}
                         {:type "record" :fields {:a {:type "boolean"}} :optional ["a" "a"]}
                         {:type "array" :items {:type "boolean"} :max-items -1}])]
    (rejects #(Shapes.validate-shape! shape)))
  (local cycle {:type "array" :max-items 1})
  (set cycle.items cycle)
  (rejects #(Shapes.validate-shape! cycle)))

(fn shape-data-and-detachment-bounds []
  (local Shapes (require :graph/capability-shapes))
  (local record {:type "record" :fields {:flag {:type "boolean"}} :optional []})
  (each [_ value (ipairs [{} {:flag 1} {:flag false :extra true}])]
    (rejects #(Shapes.check! record value)))
  (local integer {:type "integer" :min -10 :max 10})
  (each [_ value (ipairs [math.huge (- math.huge) (/ 0 0) 1.5 11 "1"])]
    (rejects #(Shapes.check! integer value)))
  (rejects #(Shapes.check! {:type "enum" :values ["a"]} "b"))
  (rejects #(Shapes.check! {:type "string" :min-bytes 0 :max-bytes 1} "λ"))
  (rejects #(Shapes.check! {:type "array" :items {:type "boolean"} :max-items 1} [true false]))
  (rejects #(Shapes.check! {:type "array" :items {:type "boolean"} :max-items 2} [true "false"]))
  (rejects #(Shapes.validate-shape! (setmetatable {:type "boolean"} {})))
  (rejects #(Shapes.validate-shape! {:type "enum" :values {1 "a" 3 "b"}}))
  (rejects #(Shapes.detach! nil))
  (rejects #(Shapes.detach! (string.char 255)))
  (rejects #(Shapes.detach! {1 true 3 false}))
  (rejects #(Shapes.detach! {1 true :mixed false}))
  (rejects #(Shapes.detach! (setmetatable {} {})))
  (rejects #(Shapes.detach! (fn [] nil)))
  (rejects #(Shapes.detach! io.stdout))
  (local cycle {})
  (set cycle.self cycle)
  (rejects #(Shapes.detach! cycle))
  (local original {:nested {:flag false}})
  (local detached (Shapes.detach! original))
  (set detached.nested.flag true)
  (assert (= original.nested.flag false))
  (Shapes.detach! (string.rep "a" 131072))
  (rejects #(Shapes.detach! [(string.rep "a" 65537) (string.rep "b" 65536)]))
  (local many [])
  (for [_ 1 4095] (table.insert many true))
  (Shapes.detach! many)
  (table.insert many false)
  (rejects #(Shapes.detach! many))
  (var deep true)
  (for [_ 1 15] (set deep [deep]))
  (Shapes.detach! deep)
  (set deep [deep])
  (rejects #(Shapes.detach! deep)))

(fn integer-declarations-reject-unsafe-runtime-extremes []
  (local Shapes (require :graph/capability-shapes))
  (rejects #(Shapes.validate-shape! {:type "integer" :min math.mininteger :max 100}))
  (rejects #(Shapes.validate-shape! {:type "integer" :min 0 :max 9007199254740992})))

(fn measured-detach [value]
  (local Shapes (require :graph/capability-shapes))
  (local debug-lib (assert _G.debug))
  (local (old-hook old-mask old-count) (debug-lib.gethook))
  (var instructions 0)
  (var utf8-scans 0)
  (var exceeded false)
  (fn measure [event]
    (if (= event "count")
        (do
          (set instructions (+ instructions 1000))
          (when (and (> instructions 500000) (not exceeded))
            (set exceeded true)
            (error "detachment exceeded bounded validation work")))
        (= event "call")
        (when (= (. (debug-lib.getinfo 2 "f") :func) utf8.len)
          (set utf8-scans (+ utf8-scans 1)))))
  (debug-lib.sethook measure "c" 1000)
  (local (ok result) (pcall Shapes.detach! value))
  (debug-lib.sethook old-hook old-mask old-count)
  (assert (not exceeded) "detachment must reject oversized input within 500000 Lua instructions")
  (assert (not ok) "oversized input must be rejected")
  (assert (= result.code "limit-exceeded") "oversized input must fail its budget check")
  utf8-scans)

(fn oversized-arrays-reject-with-bounded-work []
  (local oversized [])
  ;; Allocation is outside the meter: only validation work is bounded.
  (for [i 1 1000000] (set (. oversized i) true))
  (measured-detach oversized)
  (measured-detach [oversized]))

(fn oversized-strings-reject-before-utf8-scanning []
  (local oversized (string.rep "a" 1048576))
  (assert (= (measured-detach oversized) 0) "oversized strings must not reach the UTF-8 scanner")
  (assert (= (measured-detach (.. oversized (string.char 255))) 0)
          "an over-budget invalid suffix must not trigger a full UTF-8 scan")
  ;; A single string can fit the global maximum but exceed the remaining budget.
  (assert (= (measured-detach [(string.rep "a" 65536) (string.rep "b" 65537)]) 1)
          "only the first in-budget string may reach the UTF-8 scanner"))

(fn error-results-are-checked-and-detached []
  (local graph (Graph {:entity-events? false}))
  (local (access _state _metadata) (meter))
  (local response {:ok false :error {:code "conflict" :message "Stale revision" :outcome "not-committed"
                                    :current-revision "r2"}})
  (fn respond [_ref _args _pre] response)
  (set (. access.handlers "meter.adjust") respond)
  (install graph access)
  (each [_ code (ipairs ["conflict" "storage-failed" "corrupt-data" "notification-failed"])]
    (set response.error.code code)
    (set response.error.outcome (if (= code "notification-failed") "committed" "not-committed"))
    (local result (graph:invoke ref "meter.adjust" {:delta 0 :reason "x"} {}))
    (assert (= result.ok false))
    (assert (= result.error.code code))
    (assert (= result.error.outcome response.error.outcome))
    (assert (= result.error.current-revision "r2"))
    (set result.error.current-revision "edited")
    (assert (= response.error.current-revision "r2")))
  (set response.error.result {:level 1 :changed true})
  (local with-result (graph:invoke ref "meter.adjust" {:delta 0 :reason "x"} {}))
  (assert (= with-result.error.result.level 1))
  (set with-result.error.result.level 9)
  (assert (= response.error.result.level 1))
  (set response.error.result {:level "unchecked" :changed true})
  (fails (graph:invoke ref "meter.adjust" {:delta 0 :reason "x"} {}) "invalid-result" "unknown")
  (set response.error.result nil)
  (set response.error.code "invented-error")
  (fails (graph:invoke ref "meter.adjust" {:delta 0 :reason "x"} {}) "invalid-result" "unknown")
  (graph:drop))

(fn generic-modules-have-no-domain-or-visual-imports []
  (local fs (require :fs))
  (each [_ module (ipairs ["capability-shapes" "capabilities"])]
    (local source (fs.read-file (app.engine.get-asset-path (.. "lua/graph/" module ".fnl"))))
    (each [import (string.gmatch source "%(require%s+([^%)]+)%)")]
      (assert (not (string.find import "entities" 1 true)))
      (assert (not (string.find import "node" 1 true)))
      (assert (not (string.find import "view" 1 true)))
      (assert (not (string.find import "map" 1 true))))))

(local cases
  [["generic nonvisual meter" generic-nonvisual-meter]
   ["closed arguments and revision preconditions" arguments-and-preconditions]
   ["description and registration isolation" description-and-registration-isolation]
   ["current description validation" current-description-is-validated]
   ["write result validation and exception outcomes" invalid-write-results-and-exceptions]
   ["registration ownership replacement and drop" ownership-replacement-and-drop]
   ["visual-only registration and invalid requests" visual-only-and-invalid-requests]
   ["bounded discovery pagination and registration validation" discovery-pagination-and-registration-validation]
   ["shape vocabulary and declarations" shape-vocabulary-and-declarations]
   ["shape data and detached traversal budgets" shape-data-and-detachment-bounds]
   ["integer declarations reject unsafe runtime extremes" integer-declarations-reject-unsafe-runtime-extremes]
   ["oversized arrays reject within bounded validation work" oversized-arrays-reject-with-bounded-work]
   ["oversized strings reject before UTF-8 scanning" oversized-strings-reject-before-utf8-scanning]
   ["explicit checked error results and detached committed data" error-results-are-checked-and-detached]
   ["generic modules have no domain or visual imports" generic-modules-have-no-domain-or-visual-imports]])

(each [_ test (ipairs cases)]
  (table.insert tests {:name (. test 1) :fn (. test 2)}))

(fn main []
  (local runner (require :tests/runner))
  (runner.run-tests {:name "graph-capabilities" :tests tests}))

{:name "graph-capabilities" :tests tests :main main}
