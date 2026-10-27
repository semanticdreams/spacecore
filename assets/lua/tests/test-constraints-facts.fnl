;; Tests for static Fennel fact extraction.
;; Follows TDD: these tests must FAIL before facts.fnl is implemented.

(local tests [])
(local fs (require :fs))

(var temp-counter 0)
(local temp-root (fs.join-path "/tmp/space/tests" "constraints-facts-test"))

(fn temp-dir-name []
  (set temp-counter (+ temp-counter 1))
  (fs.join-path temp-root (.. "test-" (os.time) "-" temp-counter)))

(fn make-file [dir name content]
  "Create a file in dir with given name and content."
  (local path (fs.join-path dir name))
  (fs.write-file path content)
  path)

(fn with-temp-dir [f]
  (local dir (temp-dir-name))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (fs.create-dirs dir)
  (local (ok result) (pcall f dir))
  (fs.remove-all dir)
  (if ok
      result
      (error result)))

;; Helper: extract facts from a Fennel source string via temp file.
(fn extract-from-source [source]
  (with-temp-dir (fn [dir]
    (make-file dir "test.fnl" source)
    (local target {:kind :unit
                   :name "facts-test"
                   :roots [dir]
                   :module-roots [dir]})
    (local Source (require :constraints.source))
    (local Facts (require :constraints.facts))
    (local records (Source.discover target))
    (Facts.extract records))))

;; --- Test: Fact extraction of a simple module ---

(fn extracts-require-module []
  (local source "(local Scene (require :scene))\n(fn build [world]\n  (set world.state.scene.panels [])\n  (Scene.activate world)\n  {:render build})\n")
  (local fact-db (extract-from-source source))
  (assert fact-db "fact-db should not be nil")
  (assert fact-db.files "fact-db should have :files")
  (assert fact-db.by-file "fact-db should have :by-file")
  (assert (= (length fact-db.files) 1) "should have one file fact")
  (local ff (. fact-db.files 1))
  ;; require module "scene"
  (assert ff.requires "file-fact should have :requires")
  (assert (> (length ff.requires) 0) "should have at least one require")
  (local req (. ff.requires 1))
  (assert (= req.module "scene") (.. "expected require module 'scene', got " (tostring req.module))))

(fn extracts-definition []
  (local source "(local Scene (require :scene))\n(fn build [world]\n  (set world.state.scene.panels [])\n  (Scene.activate world)\n  {:render build})\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (assert ff.definitions "file-fact should have :definitions")
  (local defs ff.definitions)
  ;; Should have both the local and the fn
  (assert (>= (length defs) 2) (.. "expected at least 2 definitions, got " (length defs)))
  ;; Find the fn build definition
  (var found-build false)
  (each [_ d (ipairs defs)]
    (when (and (= d.kind :fn) (= d.name "build"))
      (assert d.top-level? "build should be top-level")
      (assert d.line "should have line")
      (assert d.column "should have column")
      (set found-build true)))
  (assert found-build "should find definition for fn build"))

(fn extracts-export-key []
  (local source "{:render (fn [] :ok)}\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (assert ff.exports "file-fact should have :exports")
  (var found-render false)
  (each [_ e (ipairs ff.exports)]
    (when (= e.key "render")
      (set found-render true)))
  (assert found-render "should find export key 'render'"))

(fn extracts-call []
  (local source "(local Scene (require :scene))\n(fn build [world]\n  (Scene.activate world))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (assert ff.calls "file-fact should have :calls")
  (var found-call false)
  (each [_ c (ipairs ff.calls)]
    (when (= c.callee "Scene.activate")
      (set found-call true)))
  (assert found-call "should find call to Scene.activate"))

(fn extracts-access-path []
  (local source "(fn build [world]\n  (set world.state.scene.panels []))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (assert ff.accesses "file-fact should have :accesses")
  (var found-access false)
  (each [_ a (ipairs ff.accesses)]
    (when (= a.text "world.state.scene.panels")
      (assert a.path "access should have :path")
      (assert (>= (length a.path) 4) "path should have at least 4 segments")
      (assert (= (. a.path 1) "world"))
      (assert (= (. a.path 2) "state"))
      (assert (= (. a.path 3) "scene"))
      (assert (= (. a.path 4) "panels"))
      (set found-access true)))
  (assert found-access "should find access to world.state.scene.panels"))

(fn extracts-mutation []
  (local source "(fn build [world]\n  (set world.state.scene.panels []))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (assert ff.mutations "file-fact should have :mutations")
  (var found-mutation false)
  (each [_ m (ipairs ff.mutations)]
    (when (and (= m.op :set)
               (= (. m.path 1) "world")
               (= (. m.path 2) "state")
               (= (. m.path 3) "scene")
               (= (. m.path 4) "panels"))
      (set found-mutation true)))
  (assert found-mutation "should find set mutation of world.state.scene.panels"))

(fn extracts-positive-module-lines []
  (local source "(local Scene (require :scene))\n(fn build [world]\n  (set world.state.scene.panels [])\n  (Scene.activate world)\n  {:render build})\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (assert ff.metrics "file-fact should have :metrics")
  (assert (> ff.metrics.module-lines 0) "module-lines should be positive")
  (assert ff.metrics.functions "metrics should have :functions")
  (assert (>= (length ff.metrics.functions) 1) "should have at least one function metric"))

;; --- Test: Metrics extraction ---

(fn extracts-nesting-depth []
  (local source "(fn outer [x]\n  (fn inner [y]\n    (fn deep [z]\n      (each [_ v (ipairs z)]\n        (print v))))\n  {:values [1 2 3 4 5 6 7 8 9 10]})\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (assert (>= ff.metrics.max-nesting-depth 2)
          (.. "max-nesting-depth should be >= 2 for nested fns, got " (tostring ff.metrics.max-nesting-depth))))

(fn extracts-table-literal-size []
  (local source "(fn outer [x]\n  {:values [1 2 3 4 5 6 7 8 9 10]})\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (assert (> ff.metrics.max-table-literal-size 0)
          "max-table-literal-size should be positive"))

(fn extracts-anonymous-callback-depth []
  (local source "(fn process [items]\n  (table.sort items (fn [a b]\n    (< a b))))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  ;; Should have an anonymous fn callback
  (assert (>= ff.metrics.max-anonymous-callback-depth 0)
          "max-anonymous-callback-depth should be non-negative"))

(fn extracts-function-metrics []
  (local source "(fn outer [x]\n  (fn inner [y]\n    (print y)))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (assert (>= (length ff.metrics.functions) 2)
          (.. "expected >= 2 function metrics, got " (length ff.metrics.functions)))
  (var found-outer false)
  (each [_ f (ipairs ff.metrics.functions)]
    (when (= f.name "outer")
      (assert f.line "function metric should have :line")
      (assert f.length "function metric should have :length")
      (assert f.max-nesting-depth "function metric should have :max-nesting-depth")
      (set found-outer true)))
  (assert found-outer "should find metric for function outer"))

;; --- Test: global definitions ---

(fn extracts-global-definition []
  (local source "(global CONFIG {:version 1})\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (var found-global false)
  (each [_ d (ipairs ff.definitions)]
    (when (and (= d.kind :global) (= d.name "CONFIG"))
      (assert d.top-level? "global should be top-level")
      (set found-global true)))
  (assert found-global "should find global CONFIG"))

;; --- Test: tset mutation ---

(fn extracts-tset-mutation []
  (local source "(fn update [world]\n  (tset world.state :active true))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (var found-tset false)
  (each [_ m (ipairs ff.mutations)]
    (when (= m.op :tset)
      (assert m.path "tset mutation should have :path")
      (assert m.form "tset mutation should have :form")
      (set found-tset true)))
  (assert found-tset "should find tset mutation"))

;; --- R1-1: local definition name ---

(fn local-definition-names-the-bound-symbol []
  "A (local Scene (require :scene)) should emit a local definition named 'Scene'."
  (local source "(local Scene (require :scene))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (var found-scene false)
  (each [_ d (ipairs ff.definitions)]
    (when (and (= d.kind :local) (= d.name "Scene"))
      (assert d.top-level? "local Scene should be top-level")
      (set found-scene true)))
  (assert found-scene "should find local definition named 'Scene'"))

;; --- R1-2: method-style call ---

(fn extracts-method-call []
  "A (receiver:method arg) call should populate :callee, :receiver, and :method."
  (local source "(fn activate [obj]\n  (obj:activate world))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (var found-method-call false)
  (each [_ c (ipairs ff.calls)]
    (when (and c.receiver c.method (= c.receiver "obj") (= c.method "activate"))
      (assert c.callee "method call should have :callee")
      (set found-method-call true)))
  (assert found-method-call "should find method call with receiver 'obj' and method 'activate'"))

;; --- R1-3: top-level export table ---

(fn extracts-top-level-export []
  "A top-level module-return table {:main main} should produce export keys."
  (local source "{:main main}\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (var found-main false)
  (each [_ e (ipairs ff.exports)]
    (when (= e.key "main")
      (set found-main true)))
  (assert found-main "should find export key 'main' from top-level table"))

;; --- R1-4: per-function nesting depth ---

(fn per-function-nesting-depth-is-scoped []
  "Sibling functions should each report their own nesting depth,
  not be contaminated by earlier deeper siblings."
  (local source "(fn deep-fn [x]\n  (fn inner [y]\n    (fn innermost [z]\n      (print z))))\n(fn shallow-fn [a]\n  (print a))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (var deep-nesting nil)
  (var shallow-nesting nil)
  (each [_ f (ipairs ff.metrics.functions)]
    (if (= f.name "deep-fn")
        (set deep-nesting f.max-nesting-depth)
        (= f.name "shallow-fn")
        (set shallow-nesting f.max-nesting-depth)))
  (assert deep-nesting "should find metric for deep-fn")
  (assert shallow-nesting "should find metric for shallow-fn")
  (assert (>= deep-nesting 2)
          (.. "deep-fn should have nesting >= 2, got " (tostring deep-nesting)))
  (assert (<= shallow-nesting 1)
          (.. "shallow-fn should have nesting <= 1, got " (tostring shallow-nesting))))

;; --- R2-1: export extraction is restricted to top-level tables ---

(fn exports-are-restricted-to-top-level-tables []
  "A nested data table like (local config {:main false}) must NOT produce export keys,
  while a top-level module-return table {:main main} must produce 'main'."
  (local source "(local config {:main false})\n{:main main}\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  ;; There should be exactly one export: "main" from the top-level table.
  ;; The nested {:main false} inside local_form must not appear.
  (assert (= (length ff.exports) 1)
          (.. "expected exactly 1 export key, got " (length ff.exports)))
  (assert (= (. ff.exports 1 :key) "main")
          "the single export should be 'main'"))

;; --- R2-2: Enclosing function uses smallest containing span ---

(fn enclosing-fn-uses-smallest-containing-span []
  "Nested sibling functions should be attributed to the smallest containing
   function, not an earlier sibling. Regression for scroll-view.fnl where
   register-hoverables was misattributed to pointer-from-payload."
  (local assets-path (or (os.getenv "SPACE_ASSETS_PATH") "/home/ubuntu/space/space/assets"))
  (local scroll-path (fs.join-path assets-path "lua/scroll-view.fnl"))
  (assert (fs.exists scroll-path)
          (.. "scroll-view.fnl fixture required at " scroll-path " — set SPACE_ASSETS_PATH"))
  (local target {:kind :files
                 :name "facts-enclosing-test"
                 :files [scroll-path]
                 :module-roots [(fs.join-path assets-path "lua")]})
  (local Source (require :constraints.source))
  (local Facts (require :constraints.facts))
  (local records (Source.discover target))
  (local fact-db (Facts.extract records))
  (local ff (. fact-db.files 1))

  ;; Helper: find definition by name (also checks recovered parents)
  (fn find-def [name]
    (var result nil)
    (each [_ d (ipairs ff.definitions)]
      (when (= d.name name)
        (set result d)))
    (when (not result)
      (local rps (if ff.recovered-parents ff.recovered-parents []))
      (each [_ rp (ipairs rps)]
        (when (= rp.name name)
          (set result rp))))
    result)

  (local build-def (find-def "build"))
  (local scrollview-def (find-def "ScrollView"))
  (local reg-hoverables (find-def "register-hoverables"))
  (local unreg-hoverables (find-def "unregister-hoverables"))

  (assert build-def "should find build definition")
  (assert scrollview-def "should find ScrollView definition")
  (assert reg-hoverables "should find register-hoverables definition")
  (assert unreg-hoverables "should find unregister-hoverables definition")

  ;; build should be enclosed by ScrollView
  (assert (= build-def.enclosing-fn "ScrollView")
          (.. "build should have enclosing-fn=ScrollView, got " (tostring build-def.enclosing-fn)))

  ;; register-hoverables should be enclosed by build, NOT pointer-from-payload
  (assert (= reg-hoverables.enclosing-fn "build")
          (.. "register-hoverables should have enclosing-fn=build, got " (tostring reg-hoverables.enclosing-fn)))

  ;; unregister-hoverables should be enclosed by build, NOT pointer-from-payload
  (assert (= unreg-hoverables.enclosing-fn "build")
          (.. "unregister-hoverables should have enclosing-fn=build, got " (tostring unreg-hoverables.enclosing-fn)))

  ;; R1-3: helpers must be non-top-level
  (assert (= reg-hoverables.top-level? false)
          "register-hoverables should not be top-level")
  (assert (= unreg-hoverables.top-level? false)
          "unregister-hoverables should not be top-level")

  ;; R1-3: assert call for hoverables in build's scope must precede helpers
  (var hoverables-assert-line nil)
  (each [_ c (ipairs (or ff.calls []))]
    (when (and (= c.callee "assert") (= c.enclosing-fn "build"))
      (local form-str (if c.form c.form ""))
      (when (form-str:find "hoverables" 1 true)
        (set hoverables-assert-line c.line))))
  (assert hoverables-assert-line
          "should find assert(hoverables ...) call enclosed by build")
  (assert (< hoverables-assert-line reg-hoverables.line)
          "assert for hoverables must precede register-hoverables")
  (assert (< hoverables-assert-line unreg-hoverables.line)
          "assert for hoverables must precede unregister-hoverables")

  ;; R1-3: no layout.interactive-context-assertion diagnostics for scroll-view
  (local Layout (require :constraints.rules.layout))
  (var rule nil)
  (each [_ r (ipairs (Layout.rules))]
    (when (= r.id "layout.interactive-context-assertion")
      (set rule r)))
  (assert rule "should find interactive-context-assertion rule")
  (local diags (rule.run {:facts fact-db :target {:kind :repo :name :test}}))
  (var scroll-diags 0)
  (each [_ d (ipairs (or diags []))]
    (when (= d.file scroll-path)
      (set scroll-diags (+ scroll-diags 1))))
  (assert (= scroll-diags 0)
          (.. "expected 0 ScrollView interactive diagnostics, got " scroll-diags)))

;; --- R1-1: Enclosing function parent at byte zero ---

(fn enclosing-fn-parent-at-byte-zero []
  "A parent function at the very start of the file (byte 0) should
   still be found by span-for-fn-def. The search init must be clamped."
  (local source "(fn outer [x]\n  (fn inner [y]\n    (+ x y)))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (var inner-fixture nil)
  (each [_ d (ipairs ff.definitions)]
    (when (and (= d.kind :fn) (= d.name "inner"))
      (set inner-fixture d)))
  (assert inner-fixture "should find inner definition")
  (assert (= inner-fixture.enclosing-fn "outer")
          (.. "inner should have enclosing-fn=outer, got " (tostring inner-fixture.enclosing-fn)))
  (assert (= inner-fixture.top-level? false)
          "inner should not be top-level"))

;; --- R1-1: Enclosing function parent with hyphens ---

(fn enclosing-fn-parent-with-hyphens []
  "A parent function with hyphens in its name (e.g. make-widget) should
   be found by span-for-fn-def. The hyphen must be escaped."
  (local source "(fn make-widget [opts]\n  (fn helper [x]\n    (+ x 1)))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (var helper-fixture nil)
  (each [_ d (ipairs ff.definitions)]
    (when (and (= d.kind :fn) (= d.name "helper"))
      (set helper-fixture d)))
  (assert helper-fixture "should find helper definition")
  (assert (= helper-fixture.enclosing-fn "make-widget")
          (.. "helper should have enclosing-fn=make-widget, got " (tostring helper-fixture.enclosing-fn))))

;; --- R1-1: Enclosing function parent with question mark ---

(fn enclosing-fn-parent-with-question-mark []
  "A parent function with ? in its name (Fennel convention for predicates)
   should be found by span-for-fn-def."
  (local source "(fn valid? [x]\n  (fn check [y]\n    x))\n")
  (local fact-db (extract-from-source source))
  (local ff (. fact-db.files 1))
  (var check-fixture nil)
  (each [_ d (ipairs ff.definitions)]
    (when (and (= d.kind :fn) (= d.name "check"))
      (set check-fixture d)))
  (assert check-fixture "should find check definition")
  (assert (= check-fixture.enclosing-fn "valid?")
          (.. "check should have enclosing-fn=valid?, got " (tostring check-fixture.enclosing-fn))))

;; --- R1-2: Corrected child span used for containment ---

(fn fix-enclosing-fn-uses-corrected-child-span []
  "When a child definition has a wrong tree-sitter span (e.g. end-byte
   extends past the parent), fix-enclosing-fn-by-span should use the
   corrected source-text span from span-for-fn-def for containment.
   Without R1-2 fix, the child would not be contained by any parent and
   would be marked top-level."
  (local Facts (require :constraints.facts))
  (local source "(fn outer [x]\n  (fn inner [y]\n    (+ x y)))\n")
  ;; Simulate definitions with wrong tree-sitter spans:
  ;; inner's end-byte is 9999 — way past outer's real span of ~41
  (local definitions
    [{:kind :fn :name "outer" :start-byte 0  :end-byte 41   :line 1 :column 1}
     {:kind :fn :name "inner" :start-byte 20 :end-byte 9999 :line 2 :column 3}])
  ;; No recovered parents
  (local recovered-parents [])
  (Facts.fix-enclosing-fn-by-span source definitions recovered-parents)
  ;; inner should be enclosed by outer (corrected span used, not tree-sitter 9999)
  (assert (= (. definitions 2 :enclosing-fn) "outer")
          (.. "inner should have enclosing-fn=outer, got "
              (tostring (. definitions 2 :enclosing-fn))))
  (assert (= (. definitions 2 :top-level?) false)
          "inner should not be top-level"))

(fn assert-fact-parity [expected actual]
  (assert (= (type expected) (type actual)) "observer changed fact type")
  (if (= (type expected) :table)
      (do
        (each [key value (pairs expected)] (assert-fact-parity value (. actual key)))
        (each [key _ (pairs actual)] (assert (not= (. expected key) nil) "observer added a fact")))
      (assert (= expected actual) "observer changed a fact")))

(fn assert-fact-events [events files]
  (assert (= (# events) (* 6 (# files))) "expected extract/recover/span per file")
  (each [i file (ipairs files)]
    (each [j subphase (ipairs [:extract :recover :span])]
      (local offset (+ (* (- i 1) 6) (* (- j 1) 2)))
      (local begin (. events (+ offset 1)))
      (local end (. events (+ offset 2)))
      (assert (= begin.edge :begin))
      (assert (= end.edge :end))
      (assert (= begin.phase :facts end.phase))
      (assert (= begin.subphase subphase end.subphase))
      (assert (= begin.index i end.index))
      (assert (= end.definitions (# file.definitions)))
      (assert (= end.calls (# file.calls))))))

(fn facts-observer-parity-including-error-recovery []
  (local Source (require :constraints.source))
  (local Facts (require :constraints.facts))
  (local assets (assert (os.getenv "SPACE_ASSETS_PATH")))
  (local records (Source.discover {:kind :files
                                  :files [(fs.join-path assets "lua/scroll-view.fnl")]
                                  :module-roots [(fs.join-path assets "lua")]}))
  (local root (. records 1 :root))
  (assert (= (root:type) "ERROR") "fixture must exercise ERROR recovery")
  (local expected (Facts.extract records))
  (local events [])
  (fn record-event [event] (table.insert events event))
  (local actual (Facts.extract records record-event))
  (assert-fact-parity expected (Facts.extract records nil))
  (assert-fact-parity expected actual)
  (assert (> (# (. actual.files 1 :recovered-parents)) 0) "must compare recovered parents")
  (assert-fact-events events actual.files)
  (each [_ event (ipairs events)]
    (assert (= event.file "scroll-view.fnl"))
    (each [key value (pairs event)]
      (assert (. {:edge true :phase true :subphase true :file true :index true
                  :definitions true :calls true} key) "unexpected fact event payload")
      (assert (or (= (type value) :string) (= (type value) :number))))))

(fn facts-observer-rejects-unsafe-file-metadata []
  (fn check [dir]
    (make-file dir "safe.fnl" "(fn outer [x] (fn inner [] (print x)))")
    (local Source (require :constraints.source))
    (local Facts (require :constraints.facts))
    (local records (Source.discover {:roots [dir]}))
    (local record (. records 1))
    (each [_ unsafe (ipairs ["/private/x.fnl" "C:/private/x.fnl" "C:\\private\\x.fnl"
                            "\\\\server\\x.fnl" "../private.fnl" "a/../x.fnl" "a/./x.fnl"
                            "a//x.fnl" "a\nx.fnl" ""])]
      (set record.relative-path unsafe)
      (local events [])
      (fn record-event [event] (table.insert events event))
      (local actual (Facts.extract records record-event))
      (assert-fact-events events actual.files)
      (each [_ event (ipairs events)] (assert (= event.file nil) "unsafe file must use index")))
    (set record.relative-path nil)
    (local events [])
    (fn record-event [event] (table.insert events event))
    (Facts.extract records record-event)
    (each [_ event (ipairs events)] (assert (= event.file nil) "never fall back to record.path")))
  (with-temp-dir check))

(fn facts-observer-failed-extract-stays-open []
  (local Facts (require :constraints.facts))
  (local sentinel {})
  (fn fail-index [...] (error sentinel 0))
  (local broken-source (setmetatable {} {:__index fail-index}))
  (local records [{:path "/private/error.fnl" :source broken-source :root {}}])
  (local events [])
  (fn record-event [event] (table.insert events event))
  (local (plain-ok plain-err) (pcall Facts.extract records))
  (local (ok err) (pcall Facts.extract records record-event))
  (assert (not plain-ok))
  (assert (not ok))
  (assert (= plain-err sentinel err) "fact extraction must preserve error identity")
  (assert (= (# events) 1) "failed extract must not emit an end")
  (assert (= (. events 1 :edge) :begin))
  (assert (= (. events 1 :subphase) :extract)))

(table.insert tests {:name "facts observer preserves all projections including ERROR recovery"
                     :fn facts-observer-parity-including-error-recovery})
(table.insert tests {:name "facts observer uses indices for unsafe file metadata"
                     :fn facts-observer-rejects-unsafe-file-metadata})
(table.insert tests {:name "facts observer retains unmatched extract begin on error"
                     :fn facts-observer-failed-extract-stays-open})

;; Register all tests
(table.insert tests {:name "facts extracts require module"
                     :fn extracts-require-module})
(table.insert tests {:name "facts extracts definition"
                     :fn extracts-definition})
(table.insert tests {:name "facts extracts export key"
                     :fn extracts-export-key})
(table.insert tests {:name "facts extracts call"
                     :fn extracts-call})
(table.insert tests {:name "facts extracts access path"
                     :fn extracts-access-path})
(table.insert tests {:name "facts extracts mutation"
                     :fn extracts-mutation})
(table.insert tests {:name "facts extracts positive module lines"
                     :fn extracts-positive-module-lines})
(table.insert tests {:name "facts extracts nesting depth"
                     :fn extracts-nesting-depth})
(table.insert tests {:name "facts extracts table literal size"
                     :fn extracts-table-literal-size})
(table.insert tests {:name "facts extracts anonymous callback depth"
                     :fn extracts-anonymous-callback-depth})
(table.insert tests {:name "facts extracts function metrics"
                     :fn extracts-function-metrics})
(table.insert tests {:name "facts extracts global definition"
                     :fn extracts-global-definition})
(table.insert tests {:name "facts extracts tset mutation"
                     :fn extracts-tset-mutation})
(table.insert tests {:name "facts local definition names the bound symbol"
                     :fn local-definition-names-the-bound-symbol})
(table.insert tests {:name "facts extracts method call"
                     :fn extracts-method-call})
(table.insert tests {:name "facts extracts top-level export"
                     :fn extracts-top-level-export})
(table.insert tests {:name "facts per-function nesting depth is scoped"
                     :fn per-function-nesting-depth-is-scoped})
(table.insert tests {:name "facts exports are restricted to top-level tables"
                     :fn exports-are-restricted-to-top-level-tables})
(table.insert tests {:name "facts enclosing fn uses smallest containing span"
                     :fn enclosing-fn-uses-smallest-containing-span})
(table.insert tests {:name "facts enclosing fn parent at byte zero"
                     :fn enclosing-fn-parent-at-byte-zero})
(table.insert tests {:name "facts enclosing fn parent with hyphens"
                     :fn enclosing-fn-parent-with-hyphens})
(table.insert tests {:name "facts enclosing fn parent with question mark"
                     :fn enclosing-fn-parent-with-question-mark})
(table.insert tests {:name "facts fix-enclosing-fn uses corrected child span"
                     :fn fix-enclosing-fn-uses-corrected-child-span})

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "constraints-facts"
                        :tests tests})))

{:name "constraints-facts"
 :tests tests
 :main main}
