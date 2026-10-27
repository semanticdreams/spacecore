;; Scene/Sandbox constraint rules for Fennel constraints.
;; Four rules covering legacy state, activity slot ownership,
;; sandbox activation contract, and render context routing.

(local Diagnostics (require :constraints.diagnostics))

(local M {})

;; ---------------------------------------------------------------------------
;; Helpers
;; ---------------------------------------------------------------------------

(fn normalize-path [path]
  "Replace backslash path separators with forward slashes for portable matching."
  (path:gsub "\\" "/"))

(fn file-path-basename [path]
  "Return the basename of a file path, stripping the .fnl extension if present."
  (var result (normalize-path path))
  (each [part (result:gmatch "[^/]+")]
    (set result part))
  ;; Strip .fnl extension
  (result:gsub "%.fnl$" ""))

(fn path-contains? [path fragment]
  "Check if path contains the given fragment (literal match)."
  (local normalized (normalize-path path))
  (not (not (string.find normalized fragment 1 true))))

(fn extract-string-arg-from-form [form]
  "Extract a string or keyword argument from a Fennel form string.
  Prefers the last quoted string or last keyword (the argument, not method name).
  Returns the extracted string or nil."
  ;; Try quoted string first (e.g. \"sandbox\")
  (var result (form:match "\"([^\"]+)\""))
  ;; If no quoted string, find the LAST keyword (argument comes after method name)
  (when (not result)
    (each [kw (form:gmatch ":[a-z][a-z-]*")]
      ;; Strip the leading : to get just the name
      (set result (kw:sub 2))))
  result)

(fn call-exists-with-method? [calls callee]
  "Check if any call in the list has the given callee name."
  (var found false)
  (each [_ c (ipairs calls)]
    (when (= c.callee callee)
      (set found true)))
  found)

(fn require-exists? [requires module-name]
  "Check if any require entry has the given module name."
  (var found false)
  (each [_ r (ipairs requires)]
    (when (= r.module module-name)
      (set found true)))
  found)

(fn find-call-with-method [calls callee]
  "Find the first call with the given callee, returning the call record or nil."
  (var found nil)
  (each [_ c (ipairs calls)]
    (when (and (= c.callee callee) (not found))
      (set found c)))
  found)

(fn find-all-calls-with-method [calls callee]
  "Find all calls with the given callee, returning a list of call records."
  (var found [])
  (each [_ c (ipairs calls)]
    (when (= c.callee callee)
      (table.insert found c)))
  found)

(fn form-contains-any? [form patterns]
  "Check if form string contains any of the given literal substrings."
  (var found false)
  (each [_ p (ipairs patterns)]
    (when (string.find form p 1 true)
      (set found true)))
  found)

;; ---------------------------------------------------------------------------
;; Rule 1: scene.no-legacy-world-state-scene
;; ---------------------------------------------------------------------------

(fn is-allowlisted-migration-file? [path]
  "Return true if the file path is an allowlisted migration file
  that is permitted to access world.state.scene.*."
  (or (path-contains? path "/home-world.fnl")
      (path-contains? path "/tests/")
      (path-contains? path "/e2e/")))

(fn legacy-world-state-rule-run [ctx]
  "Rule: flag world.state.scene.* access outside allowlisted migration files."
  (let [fact-db ctx.facts
        diagnostics []]
    (each [_ ff (ipairs (or fact-db.files []))]
      (when (not (is-allowlisted-migration-file? ff.path))
        (each [_ access (ipairs (or ff.accesses []))]
          (when (and (>= (length (or access.path [])) 3)
                     (= (. access.path 1) "world")
                     (= (. access.path 2) "state")
                     (= (. access.path 3) "scene"))
            (table.insert diagnostics
              (Diagnostics.violation
                {:constraint-id "scene.no-legacy-world-state-scene"
                 :family "scene-sandbox"
                 :message (.. "legacy world.state.scene access: " access.text)
                 :file ff.path
                 :line (or access.line 0)
                 :column (or access.column 0)
                 :evidence {:access access.text :form (or access.form "")}
                 :hint (.. "replace world.state.scene.* access with "
                           "runtime.scene slot API (ensure-activity-slot / activate-activity-slot) "
                           "or add this file to the migration allowlist if it is a known migration file")}))))))
    (if (> (length diagnostics) 0) diagnostics nil)))

;; ---------------------------------------------------------------------------
;; Rule 2: scene.activity-slot-ownership
;; ---------------------------------------------------------------------------

(local activity-module-ids
  {"graph-activity-unit" "graph"
   "drawing-activity-unit" "drawing"
   "board-activity-unit" "board"})

(fn check-activity-slot-call [diagnostics ff basename expected-id method-name]
  "Check that the module has the required Scene slot call with the correct id.
  Iterates over ALL matching calls: flags any call with wrong id, and
  separately detects when a required correct call is entirely absent."
  (let [full-method (.. "scene:" method-name)
        matching-calls (find-all-calls-with-method ff.calls full-method)]
    (if (= (length matching-calls) 0)
        ;; Missing the required call entirely
        (table.insert diagnostics
          (Diagnostics.violation
            {:constraint-id "scene.activity-slot-ownership"
             :family "scene-sandbox"
             :message (.. basename " is missing required call: " full-method)
             :file ff.path
             :line 0 :column 0
             :evidence {:missing-call full-method
                        :expected-id expected-id}
             :hint (.. "add (" full-method " \"" expected-id "\") to " basename)}))
        ;; Calls exist — check each one's slot id argument
        (each [_ call-rec (ipairs matching-calls)]
          (let [arg (extract-string-arg-from-form (or call-rec.form ""))]
            (when (not (= arg expected-id))
              (table.insert diagnostics
                (Diagnostics.violation
                  {:constraint-id "scene.activity-slot-ownership"
                   :family "scene-sandbox"
                   :message (.. basename " calls " method-name " with \""
                                (or arg "?") "\" instead of \"" expected-id "\"")
                   :file ff.path
                   :line (or call-rec.line 0)
                   :column (or call-rec.column 0)
                   :evidence {:call full-method
                              :form (or call-rec.form "")
                              :actual-arg (or arg "unknown")
                              :expected-arg expected-id}
                   :hint (.. "replace the id argument with \""
                             expected-id "\" in the " method-name " call")}))))))))

(fn activity-slot-ownership-rule-run [ctx]
  "Rule: Graph, Drawing, and Board modules must call ensure/activate-activity-slot
  with their own ids; missing calls or any wrong slot id are violations."
  (let [fact-db ctx.facts
        diagnostics []]
    (each [_ ff (ipairs (or fact-db.files []))]
      (let [basename (file-path-basename ff.path)
            expected-id (. activity-module-ids basename)]
        (when expected-id
          (check-activity-slot-call diagnostics ff basename expected-id "ensure-activity-slot")
          (check-activity-slot-call diagnostics ff basename expected-id "activate-activity-slot"))))
    (if (> (length diagnostics) 0) diagnostics nil)))

;; ---------------------------------------------------------------------------
;; Rule 3: scene.sandbox-activation-contract
;; ---------------------------------------------------------------------------

(local sandbox-contract-required-calls
  [;; The core Scene slot management calls — must use "sandbox" id
   {:callee "scene:ensure-activity-slot" :label "ensure-activity-slot sandbox"
    :validate-arg "sandbox"}
   {:callee "scene:activate-activity-slot" :label "activate-activity-slot sandbox"
    :validate-arg "sandbox"}
   ;; Surface configuration: hide Canvas, prefer Scene
   {:callee "ctx:set-surface-state!" :label "set-surface-state! (hide Canvas)"
    :form-patterns [":visible? false" ":interactive? false"]}
   {:callee "ctx:set-preferred-interaction-surface!"
    :label "set-preferred-interaction-surface! (prefer Scene)"
    :validate-arg "scene"}
   ;; Action and routing installation — presence only
   {:callee "ctx:set-root-actions!" :label "set-root-actions!"}
   {:callee "ctx:set-target-enabled!" :label "set-target-enabled!"}
   ;; Update hook installation — presence only
   {:callee "ctx:set-update!" :label "set-update!"}])

(fn check-sandbox-requires-runtime [diagnostics ff]
  "Check that sandbox-activity-unit.fnl requires the runtime module
  (which provides the runtime.scene / world-runtime.scene namespaces)."
  (when (not (require-exists? ff.requires "runtime"))
    (table.insert diagnostics
      (Diagnostics.violation
        {:constraint-id "scene.sandbox-activation-contract"
         :family "scene-sandbox"
         :message "sandbox-activity-unit.fnl must require 'runtime' (for runtime.scene)"
         :file ff.path
         :line 0 :column 0
         :evidence {:required-require "runtime"}
         :hint "add (local runtime (require :runtime)) to sandbox-activity-unit.fnl"}))))

(fn access-matches-scene-path? [access]
  "Check whether an access record matches a runtime.scene path.
  Recognises paths ending in [...]/scene where the parent segment is
  runtime, world-runtime, or active-world-runtime."
  (let [p (or access.path [])
        plen (length p)]
    (and (>= plen 2)
         (= (. p plen) "scene")
         (or (= (. p (- plen 1)) "runtime")
             (= (. p (- plen 1)) "world-runtime")
             (= (. p (- plen 1)) "active-world-runtime")))))

(local scene-access-patterns
  ["runtime.scene"
   "world-runtime.scene"
   "active-world-runtime.scene"])

(local core-activation-call-patterns
  ["scene:ensure-activity-slot"
   "scene:activate-activity-slot"])

(fn check-sandbox-uses-runtime-scene [diagnostics ff]
  "Check that sandbox-activity-unit.fnl activation function accesses runtime.scene.
  Ties evidence specifically to the activation-owning definition:
  prefers the function named activate-sandbox-activity!; otherwise requires the
  same definition that contains core slot activation calls (ensure/activate-activity-slot)
  to contain the runtime.scene evidence.  Falls back to a file-wide access scan
  only when no activation-owning definition is identified."
  (var found-scene false)
  (var activation-defs-checked false)
  ;; First pass: look for the specifically-named activation function
  (each [_ def (ipairs (or ff.definitions []))]
    (when (and def.name (= def.name "activate-sandbox-activity!") def.form)
      (set activation-defs-checked true)
      (when (form-contains-any? def.form scene-access-patterns)
        (set found-scene true))))
  ;; If no named activation function found, fall back to definitions that
  ;; contain core slot activation calls (ensure/activate)
  (when (not activation-defs-checked)
    (each [_ def (ipairs (or ff.definitions []))]
      (when (and def.form (form-contains-any? def.form core-activation-call-patterns))
        (set activation-defs-checked true)
        (when (form-contains-any? def.form scene-access-patterns)
          (set found-scene true)))))
  (if activation-defs-checked
      ;; At least one activation-owning definition identified — verify it also
      ;; references the runtime scene.
      (when (not found-scene)
        (table.insert diagnostics
          (Diagnostics.violation
            {:constraint-id "scene.sandbox-activation-contract"
             :family "scene-sandbox"
             :message "sandbox-activity-unit.fnl activation function must access runtime.scene (world-runtime.scene)"
             :file ff.path
             :line 0 :column 0
             :evidence {:required-access "runtime.scene"}
             :hint "ensure sandbox activation obtains and uses runtime.scene / world-runtime.scene"})))
      ;; No activation-owning definition found — fall back to
      ;; file-wide access check (activation code may be at top level).
      (do
        (set found-scene false)
        (each [_ a (ipairs (or ff.accesses []))]
          (when (access-matches-scene-path? a)
            (set found-scene true)))
        (when (not found-scene)
          (table.insert diagnostics
            (Diagnostics.violation
              {:constraint-id "scene.sandbox-activation-contract"
               :family "scene-sandbox"
               :message "sandbox-activity-unit.fnl must access runtime.scene (world-runtime.scene)"
               :file ff.path
               :line 0 :column 0
               :evidence {:required-access "runtime.scene"}
               :hint "ensure sandbox activation obtains and uses runtime.scene / world-runtime.scene"}))))))

(fn check-single-contract-call [diagnostics ff req]
  "Check a single required call in sandbox-activity-unit.fnl.
  When validate-arg is set, checks that the first string/keyword argument matches.
  When form-patterns is set, checks that the call form contains all expected patterns."
  (let [existing-call (find-call-with-method ff.calls req.callee)]
    (if (not existing-call)
        ;; Missing the required call entirely
        (table.insert diagnostics
          (Diagnostics.violation
            {:constraint-id "scene.sandbox-activation-contract"
             :family "scene-sandbox"
             :message (.. "sandbox-activity-unit.fnl missing required call: " req.label)
             :file ff.path
             :line 0 :column 0
             :evidence {:missing-call req.callee}
             :hint (.. "add (" req.callee " ...) to the sandbox activation function")}))
        ;; Call exists — check argument validation if specified
        (let [form (or existing-call.form "")]
          (when req.validate-arg
            (let [arg (extract-string-arg-from-form form)]
              (when (not (= arg req.validate-arg))
                (table.insert diagnostics
                  (Diagnostics.violation
                    {:constraint-id "scene.sandbox-activation-contract"
                     :family "scene-sandbox"
                     :message (.. "sandbox-activity-unit.fnl " req.callee " should use \""
                                  req.validate-arg "\" but got \"" (or arg "?") "\"")
                     :file ff.path
                     :line (or existing-call.line 0)
                     :column (or existing-call.column 0)
                     :evidence {:call req.callee
                                :form form
                                :expected-arg req.validate-arg
                                :actual-arg (or arg "unknown")}
                     :hint (.. "change the argument in (" req.callee " ...) to \""
                               req.validate-arg "\"")})))))
          (when req.form-patterns
            (let [missing-patterns []]
              (each [_ p (ipairs req.form-patterns)]
                (when (not (string.find form p 1 true))
                  (table.insert missing-patterns p)))
              (when (> (length missing-patterns) 0)
                (table.insert diagnostics
                  (Diagnostics.violation
                    {:constraint-id "scene.sandbox-activation-contract"
                     :family "scene-sandbox"
                     :message (.. "sandbox-activity-unit.fnl " req.callee " missing required patterns: "
                                  (table.concat missing-patterns ", "))
                     :file ff.path
                     :line (or existing-call.line 0)
                     :column (or existing-call.column 0)
                     :evidence {:call req.callee
                                :form form
                                :missing-patterns missing-patterns}
                     :hint (.. "ensure (" req.callee " ...) includes the required configuration")})))))))))

(fn sandbox-activation-contract-rule-run [ctx]
  "Rule: sandbox-activity-unit.fnl must follow the activation contract."
  (let [fact-db ctx.facts
        diagnostics []]
    (each [_ ff (ipairs (or fact-db.files []))]
      (when (path-contains? ff.path "sandbox-activity-unit.fnl")
        (check-sandbox-requires-runtime diagnostics ff)
        (check-sandbox-uses-runtime-scene diagnostics ff)
        (each [_ req (ipairs sandbox-contract-required-calls)]
          (check-single-contract-call diagnostics ff req))))
    (if (> (length diagnostics) 0) diagnostics nil)))

;; ---------------------------------------------------------------------------
;; Rule 4: scene.active-render-context-routing
;; ---------------------------------------------------------------------------

(fn check-scene-slot-routing [diagnostics slot]
  "Check that an active Scene activity slot provides render context routing.
  Accepts a slot table (or nil) and appends diagnostics for missing ctx or layout-root.
  Exported for testable injection."
  (when (not slot)
    (table.insert diagnostics
      (Diagnostics.violation
        {:constraint-id "scene.active-render-context-routing"
         :family "scene-sandbox"
         :message "no Scene activity slot for sandbox after activation"
         :file "sandbox-activity-unit.fnl"
         :line 0 :column 0
         :evidence {:assertion "scene:activity-slot(\"sandbox\")"}
         :hint "ensure sandbox activation creates a Scene activity slot via ensure-activity-slot"})))
  (when (and slot (not slot.ctx))
    (table.insert diagnostics
      (Diagnostics.violation
        {:constraint-id "scene.active-render-context-routing"
         :family "scene-sandbox"
         :message "active Scene slot missing render context (ctx)"
         :file "sandbox-activity-unit.fnl"
         :line 0 :column 0
         :evidence {:assertion "slot.ctx render context"}
         :hint "ensure the Scene slot provides a build context for render vectors"})))
  (when (and slot (not slot.layout-root))
    (table.insert diagnostics
      (Diagnostics.violation
        {:constraint-id "scene.active-render-context-routing"
         :family "scene-sandbox"
         :message "active Scene slot missing layout root for render routing"
         :file "sandbox-activity-unit.fnl"
         :line 0 :column 0
         :evidence {:assertion "slot.layout-root render routing"}
         :hint "ensure the Scene slot provides a layout root for render routing"}))))

(fn fixture-traceback [err]
  (debug.traceback (tostring err) 2))

(fn attempt-fixture-cleanup! [fixture errors stage f ...]
  ;; A failing operation must not change the app used by later owned cleanup.
  (rawset _G :app fixture)
  (local (ok err) (pcall f ...))
  (when (not ok)
    (table.insert errors (.. "scene fixture cleanup " stage " failed: " (tostring err)))))

(fn initialize-scene-fixture! [fixture Activities]
  (local Intersectables (require :intersectables))
  (local Clickables (require :clickables))
  (local Hoverables (require :hoverables))
  (local {: LightSystem} (require :light-system))
  (local Signal (require :signal))
  (local Camera (require :camera))
  (local Scene (require :scene))
  (local glm (require :glm))
  ;; Record each returned owner before the next constructor/call can fail.
  (set fixture.intersectables (Intersectables))
  (local intersectables (assert fixture.intersectables "scene fixture requires intersectables"))
  (set fixture.clickables (Clickables {: intersectables}))
  (set fixture.hoverables (Hoverables {: intersectables}))
  (set fixture.lights (LightSystem {}))
  (set fixture.create-default-projection (. (require :app-projection) :create-default-projection))
  (set fixture.activities-changed (Signal))
  (set fixture.activity-dock-changed (Signal))
  (set fixture.workspace-shell-changed (Signal))
  (Activities.ensure-registry)
  (set fixture.camera (Camera {:position (glm.vec3 0 0 100)}))
  (local camera (assert fixture.camera "scene fixture requires camera"))
  (set fixture.scene (Scene {: camera}))
  (set fixture.active-world-runtime.scene (assert fixture.scene "scene fixture requires scene")))

(fn cleanup-fixture-activities! [fixture errors Activities]
  (local registry fixture.activity-registry)
  (when registry
    (when registry.active-activity-spec
      (attempt-fixture-cleanup! fixture errors "activity deactivation" Activities.deactivate-active-activity))
    ;; Unregister calls deactivation and session drop internally. Detach each
    ;; already-attempted owner even on failure so that it cannot be retried.
    (set registry.active-activity-id nil)
    (set registry.active-activity-spec nil)
    (set registry.active-activity-session nil)
    (set fixture.active-activity-id nil)
    (set fixture.active-world-runtime.active-activity-id nil)
    (when (. registry.sessions :sandbox)
      (attempt-fixture-cleanup! fixture errors "sandbox session" Activities.drop-activity-session! "sandbox"))
    (tset registry.sessions :sandbox nil)
    (when (. registry.activities :sandbox)
      (attempt-fixture-cleanup! fixture errors "sandbox unregistration" Activities.unregister-activity "sandbox"))))

(fn with-scene-fixture [f]
  (local caller app)
  (local Activities (require :activities))
  ;; No shallow copy: only Engine and read-only themes are borrowed. Scene
  ;; services, shell state, activity signals/registry and sessions belong here.
  (local fixture {:testing true :engine caller.engine :themes caller.themes
                  :canvas {:visible? false :interactive? false}
                  :active-world-runtime {:activity-sessions {} :activity-session-state {}}})
  (fn run []
    (initialize-scene-fixture! fixture Activities)
    (f fixture.scene))
  (rawset _G :app fixture)
  (local (ok result) (xpcall run fixture-traceback))
  (local errors [])
  (attempt-fixture-cleanup! fixture errors "activities" cleanup-fixture-activities! fixture errors Activities)
  (each [_ key (ipairs [:scene :camera :hoverables :clickables :intersectables])]
    (local resource (. fixture key))
    (when resource
      (attempt-fixture-cleanup! fixture errors key resource.drop resource)))
  ;; LightSystem has no drop API. All fixture references can now be released.
  (rawset _G :app caller)
  (local messages [])
  (when (not ok) (table.insert messages (tostring result)))
  (each [_ err (ipairs errors)] (table.insert messages err))
  (if (> (# messages) 0) (error (table.concat messages "\n") 0) result))

(fn active-render-context-routing-rule-run [ctx]
  "Scenario: verify that the active Scene slot context supplies render vectors."
  (local Scenarios (require :constraints.scenarios))
  (local diagnostics [])
  (fn check-routing [scene]
    (local SandboxActivityUnit (require :sandbox-activity-unit))
    (local Activities (require :activities))
    (SandboxActivityUnit.load-sandbox-activity!)
    (Activities.activate-activity "sandbox")
    ;; Keep the actual Sandbox activation and original slot-routing assertions.
    (local slot (scene:activity-slot "sandbox"))
    (check-scene-slot-routing diagnostics slot))
  (fn run [] (with-scene-fixture check-routing))
  (Scenarios.with-test-app run)
  (if (> (length diagnostics) 0) diagnostics nil))

;; ---------------------------------------------------------------------------
;; Rule registry
;; ---------------------------------------------------------------------------

(fn M.rules []
  "Return the list of scene-sandbox rules."
  [{:id "scene.no-legacy-world-state-scene"
    :family "scene-sandbox"
    :targets [:repo :unit :app :files]
    :kind :static
    :run legacy-world-state-rule-run
    :fn legacy-world-state-rule-run}
   {:id "scene.activity-slot-ownership"
    :family "scene-sandbox"
    :targets [:repo :unit :app :files]
    :kind :static
    :run activity-slot-ownership-rule-run
    :fn activity-slot-ownership-rule-run}
   {:id "scene.sandbox-activation-contract"
    :family "scene-sandbox"
    :targets [:repo :unit :app :files]
    :kind :static
    :run sandbox-activation-contract-rule-run
    :fn sandbox-activation-contract-rule-run}
   {:id "scene.active-render-context-routing"
    :family "scene-sandbox"
    :targets [:repo]
    :kind :scenario
    :run active-render-context-routing-rule-run
    :fn active-render-context-routing-rule-run}])

(set M.check-scene-slot-routing check-scene-slot-routing)

M
