(local tests [])
(local glm (require :glm))
(local runner (require :tests/runner))
(local Canvas (require :canvas))
(local Camera (require :camera))
(local {: FocusManager} (require :focus))
(local Activities (require :activities))
(local BoardActivityUnit (require :board-activity-unit))
(local StringEntityStore (require :entities/string))

(fn make-test-font []
  (local glyph {:advance 1
                :planeBounds {:left 0 :right 1 :bottom 0 :top 1}
                :atlasBounds {:left 0 :right 1 :bottom 0 :top 1}})
  {:metadata {:metrics {:ascender 1 :descender 0 :lineHeight 1}
              :atlas {:width 1 :height 1}}
   :glyph-map {32 glyph 65 glyph 66 glyph 65533 glyph}})

(fn make-scene-stub []
  {:ensure-activity-slot (fn [_self _activity-id] {})
   :activate-activity-slot (fn [self activity-id]
                             (local slot (self:ensure-activity-slot activity-id))
                             (set self.active-activity-slot slot)
                             slot)
   :deactivate-activity-slot (fn [self _activity-id]
                               (set self.active-activity-slot nil)
                               nil)
   :capture-activity-slot-state (fn [_self _activity-id] {})
   :restore-activity-slot-state (fn [_self _activity-id _state] true)})

(fn make-canvas-fixture []
  (local camera (Camera {:position (glm.vec3 0 0 100)}))
  (local focus-manager (FocusManager {:root-name "board-string-entity-test"}))
  (local canvas (Canvas {:camera camera :focus-manager focus-manager}))
  {:canvas canvas
   :drop (fn [_self]
           (canvas:drop)
           (focus-manager:drop)
           (camera:drop))})

(local policy-and-hook-fields
  [:active-interaction-surface :preferred-interaction-surface :active-pointer-controls
   :scene-interactive? :canvas-interactive? :canvas-visible? :canvas-surface-interactive?
   :activity-root-actions :activity-selection-actions :activity-left-dock-builder
   :activity-command-hints-provider :activity-leader-command-providers
   :activity-delete-selection :activity-activate-focused :activity-drawing-enabled?
   :activity-context-enricher :activity-input-handlers :activity-target-enabled?
   :activity-update :activity-preferred-interaction-surface :activity-surface-state
   :activity-top-toolbar-builder :activity-object-drag-mode-provider])

(fn snapshot-app-fields [keys]
  ;; Keep a record for absent fields too: pairs over a value map loses nils.
  (icollect [_ key (ipairs keys)] {:key key :value (. app key)}))

(fn restore-app-fields! [snapshot]
  (each [_ entry (ipairs snapshot)] (set (. app entry.key) entry.value)))

(fn board-test-theme []
  {:font app.text-style.font
   :text {:scale 1.0 :foreground (glm.vec4 1 1 1 1)}})

(fn with-board-runtime [body board-state]
  (local previous-policy (snapshot-app-fields policy-and-hook-fields))
  (local previous-runtime
    (snapshot-app-fields [:canvas :active-world-runtime :active-activity-id
                      :activity-registry :activities-changed :board :board-view
                      :text-style :themes :hud :workspace-shell-changed :activity-dock-changed]))
  (var fixture nil)
  (set app.activity-registry nil)
  (set app.activities-changed nil)
  ;; The fixture owns these presentations, not observers on the surrounding app.
  (set app.hud nil)
  (set app.workspace-shell-changed nil)
  (set app.activity-dock-changed nil)
  (local (ok err)
    (pcall
      (fn []
        (set fixture (make-canvas-fixture))
        (set app.canvas fixture.canvas)
        (set app.text-style {:font (make-test-font)
                             :scale 1.0
                             :color (glm.vec4 1 1 1 1)})
        (set app.themes {:get-active-theme board-test-theme})
        (set app.active-interaction-surface :canvas)
        (set app.active-world-runtime {:canvas fixture.canvas
                                       :activity-cameras {:canvas {} :scene {}}
                                       :activity-controls {:canvas {} :scene {}}
                                       :scene (make-scene-stub)
                                       :board-state board-state})
        (BoardActivityUnit.load-board-activity!)
        (Activities.activate-activity "board")
        (body))))
  (local (unload-ok unload-err) (pcall BoardActivityUnit.unload-board-activity!))
  (local (drop-ok drop-err) (pcall (fn [] (when fixture (fixture:drop)))))
  (restore-app-fields! previous-runtime)
  ;; Restore inputs AND derived fields verbatim, including nil and pointer controls.
  ;; Re-running a setter here would normalize nils or mutate the restored runtime.
  (restore-app-fields! previous-policy)
  (local errors [])
  (when (not ok) (table.insert errors (tostring err)))
  (when (not unload-ok) (table.insert errors (.. "Board unload failed: " (tostring unload-err))))
  (when (not drop-ok) (table.insert errors (.. "Board fixture drop failed: " (tostring drop-err))))
  (if (= (length errors) 0) true (error (table.concat errors "\n"))))

(local valid-entity-id "board-prune-valid-string-entity")
(local missing-entity-id "board-prune-missing-string-entity")

(fn stale-string-entity-state []
  {:items [{:id "valid-string"
            :type "string-entity"
            :subject-key (.. "string-entity:" valid-entity-id)
            :position [0 0 0]
            :rotation [1 0 0 0]
            :size [32 16 0]}
           {:id "missing-string"
            :type "string-entity"
            :subject-key (.. "string-entity:" missing-entity-id)
            :position [40 0 0]
            :rotation [1 0 0 0]
            :size [32 16 0]}]
   :connectors [{:id "stale-connector"
                 :source-item-id "valid-string"
                 :target-item-id "missing-string"}]})

(fn cleanup-string-entities [store]
  (pcall (fn [] (store:delete-entity valid-entity-id)))
  (pcall (fn [] (store:delete-entity missing-entity-id))))

(fn with-valid-string-entity [body]
  (local store (StringEntityStore.get-default))
  (cleanup-string-entities store)
  (store:create-entity {:id valid-entity-id :value "valid"})
  (local (ok err) (pcall body))
  (cleanup-string-entities store)
  (if ok true (error err)))

(fn assert-stale-item-pruned []
  (assert app.board "Board activity should activate")
  (assert (. app.board.items "valid-string")
          "Valid string entity item should remain restored")
  (assert (not (. app.board.items "missing-string"))
          "Stale string entity item should be pruned")
  (assert (= (length app.board.connectors-in-order) 0)
          "Connector referencing stale item should be pruned"))

(fn activation-restore-runtime []
  (with-board-runtime assert-stale-item-pruned (stale-string-entity-state)))

(fn active-restore-body []
  (Activities.restore-active-activity {:active? true
                                       :board-state (stale-string-entity-state)})
  (assert-stale-item-pruned))

(fn active-restore-runtime []
  (with-board-runtime active-restore-body {:items [] :connectors []}))

(fn activation-restore-prunes-stale-string-entity-item []
  (with-valid-string-entity activation-restore-runtime))

(fn active-restore-prunes-stale-string-entity-item []
  (with-valid-string-entity active-restore-runtime))

(fn assert-board-fixture-restores [expected fail?]
  (fn body [] (when fail? (error "board fixture assertion sentinel")))
  (local (body-ok body-err)
    (pcall with-board-runtime body {:items [] :connectors []}))
  (assert (= body-ok (not fail?)) "Board fixture must preserve body outcome")
  (when fail?
    (assert (string.find (tostring body-err) "board fixture assertion sentinel" 1 true)))
  (each [_ entry (ipairs expected)]
    (assert (= (. app entry.key) entry.value)
            (.. "Board fixture leaked " entry.key))))

(fn check-board-fixture-restoration []
  (local marker (fn [] true))
  ;; Non-nil hooks must survive activation/unload, not just the initial nils.
  (each [i key (ipairs policy-and-hook-fields)]
    (when (string.find key "activity-" 1 true)
      (set (. app key) (if (= (% i 3) 0) nil (= (% i 3) 1) false marker))))
  (local expected (snapshot-app-fields policy-and-hook-fields))
  (assert-board-fixture-restores expected false)
  (assert-board-fixture-restores expected true)
  ;; An absent policy is also owned state; setters must not normalize it on exit.
  (each [_ key (ipairs policy-and-hook-fields)] (set (. app key) nil))
  (local absent (snapshot-app-fields policy-and-hook-fields))
  (assert-board-fixture-restores absent false)
  (assert-board-fixture-restores absent true))

(fn board-fixture-restores-policy-and-hooks []
  (local original (snapshot-app-fields policy-and-hook-fields))
  (local (ok err) (pcall check-board-fixture-restoration))
  (restore-app-fields! original)
  (if ok true (error err)))

(table.insert tests {:name "Board activity activation restore prunes stale string entity item"
                     :fn activation-restore-prunes-stale-string-entity-item})
(table.insert tests {:name "Board activity active restore prunes stale string entity item"
                     :fn active-restore-prunes-stale-string-entity-item})
(table.insert tests {:name "Board fixture restores interaction policy and activity hooks on success and assertion"
                     :fn board-fixture-restores-policy-and-hooks})

(fn main []
  (runner.run-tests {:name "board-activity-string-entities"
                     :tests tests}))

{:name "board-activity-string-entities"
 :tests tests
 :main main}
