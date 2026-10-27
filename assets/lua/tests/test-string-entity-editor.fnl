(local BuildContext (require :build-context))
(local Strings (require :entities/string))
(local Links (require :entities/link))
(local RecordFiles (require :entities/record-files))
(local Graph (require :graph/init))
(local {:StringEntityNode StringEntityNode} (require :graph/nodes/string-entity))
(local Full (require :graph/view/views/string-entity))
(local Preview (require :graph/view/previews/string-entity))
(local tempfile (require :tempfile))
(local process (require :process))
(local fs (require :fs))
(local Uuid (require :uuid))
(local json (require :json))
(local glm (require :glm))
(local with-record-clock (require :tests/record-clock))
(local tests [])

(fn registrations []
  (assert app.clickables "editor tests require clickables")
  (assert app.hoverables "editor tests require hoverables")
  [(length app.clickables.left-click-objects)
   (length app.clickables.right-click-objects)
   (length app.clickables.double-click-objects)
   (length app.hoverables.objects)])

(fn draw-count [ctx]
  (local batcher (ctx:get-text-ssbo-batcher))
  (length (batcher:get-draw-list)))

(fn editor-directory []
  (if (not= (string.sub package.config 1 1) "/")
      (tempfile.TemporaryDirectory {:prefix "string-editor-"})
      (do
        (local path (fs.join-path "/tmp" (.. "string-editor-" (Uuid.v4))))
        (local made (process.run {:args ["mkdir" "-m" "700" path] :timeout 10}))
        (assert (= made.exit-code 0) made.stderr)
        (each [_ child (ipairs ["entities" "entities/string" "entities/link"])]
          (local created (process.run {:args ["mkdir" "-m" "700" (fs.join-path path child)] :timeout 10}))
          (assert (= created.exit-code 0) created.stderr))
        {:path path :drop (fn drop-directory [_self] (fs.remove-all path))})))

(fn error-text [err] (if (= (type err) :table) (json.dumps err) (tostring err)))

(fn assert-view-dropped [view]
  (assert view.input.__dropped "owning composite must drop Input"))

(fn with-editor [surface f]
  (local cleanup [])
  (local errors [])
  (fn own [label action resource]
    (table.insert cleanup {:label label :action action :resource resource}))
  (fn exercise []
    (local dir (editor-directory))
    (own "directory drop" dir.drop dir)
    (local files (collect [k v (pairs RecordFiles)] (values k v)))
    (local store (Strings.StringEntityStore {:base-dir dir.path :files files}))
    (local links (Links.LinkEntityStore {:base-dir dir.path}))
    (local graph (Graph {:with-start false :entity-events? false :string-store store :link-store links :morphs {}}))
    (own "graph drop" graph.drop graph)
    (local access ((. (require :graph/capabilities/entities) :access-by-scheme) {:string-store store :link-store links}))
    (each [scheme provider (pairs access)]
      (graph:register-key-loader scheme (fn no-visual [] (error "must not materialize")) {:access provider}))
    (local entity (store:create-entity {:value "initial"}))
    (local node (StringEntityNode {:entity-id entity.id :store store}))
    (fn check-node-subscription []
      (local label node.label)
      (store:update-entity entity.id {:value "after node drop"})
      (assert (= node.label label) "node store subscription leaked after drop"))
    (own "node subscription" check-node-subscription)
    (own "node drop" node.drop node)
    (local ctx (BuildContext {:clickables app.clickables :hoverables app.hoverables
                             :icons {:resolve (fn no-icon [] nil)}}))
    (local before (store:read-text entity.id))
    (local registered-before (json.dumps (registrations)))
    (fn check-registrations []
      (assert (= (json.dumps (registrations)) registered-before) "widget registrations leaked"))
    (fn check-draws [] (assert (= (draw-count ctx) 0) "text render entries leaked"))
    (own "widget registrations" check-registrations)
    (own "render entries" check-draws)
    (fn open-view [build]
      (local view ((build node) ctx))
      (own "Input teardown" assert-view-dropped view)
      (own "editor view drop" view.drop view)
      view)
    (local view (open-view surface))
    (f {:store store :files files :node node :view view :ctx ctx :open-view open-view
        :graph graph :ref {:key node.key} :before before :surface surface}))
  (local (ok err) (pcall exercise))
  (when (not ok) (table.insert errors {:label "assertion" :error err}))
  ;; Each release AND teardown assertion is independent; neither can prevent
  ;; subsequent view/node/graph/directory cleanup on success or failure.
  (for [index (length cleanup) 1 -1]
    (local entry (. cleanup index))
    (local (cleaned cleanup-error) (pcall entry.action entry.resource))
    (when (not cleaned)
      (table.insert errors {:label entry.label :error cleanup-error})))
  ;; Format only after every release, so error rendering cannot skip cleanup.
  (when (> (length errors) 0)
    (local messages (icollect [_ entry (ipairs errors)] (.. entry.label ": " (error-text entry.error))))
    (error (table.concat messages "\n") 0)))

(fn value! [result]
  (assert result.ok (json.dumps result))
  result.value)

(fn status [editor]
  (table.concat (icollect [_ cp (ipairs (editor.status-text:get-codepoints))] (utf8.char cp))))

(fn assert-conflict [c attempted]
  (c.view.input:set-text attempted)
  (assert (= (c.view.input:get-text) attempted) "conflict must retain attempted input")
  (assert (= c.view.editor.last-error.code :conflict) "displayed baseline must stay stale")
  (assert (string.find (status c.view.editor) "not saved" 1 true) "conflict must be visible")
  (c.view.editor.layout:measurer)
  (assert (> c.view.editor.layout.measure.y c.view.input.layout.measure.y) "error must own visible layout space")
  (assert (= c.view.editor.status-text.layout.parent.parent c.view.editor.layout))
  (set c.view.editor.layout.size (+ c.view.editor.layout.measure (glm.vec3 20 0 0)))
  (c.view.editor.layout:layouter))

(fn opening [c]
  (assert (= (. (c.store:read-text c.node.entity-id) :revision) c.before.revision)
          "opening a real editor must not write or advance revision")
  (assert (= (c.view.input:get-text) c.before.value))
  (assert (= c.view.input.min-lines 3))
  (assert (= (status c.view.editor) ""))
  (c.view.editor.layout:measurer)
  (c.view.input.layout:measurer)
  (assert (= c.view.editor.layout.measure.y c.view.input.layout.measure.y)
          "empty status must not add geometry"))

(fn empty-opening [c]
  (c.store:update-entity c.node.entity-id {:value ""})
  (local before (c.node:read-text))
  (local other (c.open-view c.surface))
  (assert (= (other.input:get-text) ""))
  (assert (= (. (c.node:read-text) :revision) before.revision) "opening empty text must not save")
  (local placeholder (table.concat (icollect [_ cp (ipairs (other.input.placeholder:get-codepoints))] (utf8.char cp))))
  (assert (= placeholder (if (= c.surface Full) "Enter value..." "Value..."))))

(fn failed-opening-is-nonallocating [c]
  (local registered-before (json.dumps (registrations)))
  (local drawn-before (draw-count c.ctx))
  (local original-read c.files.read!)
  (each [_ code (ipairs [:not-found :storage-failed :corrupt-data])]
    (local failure {:code code :message (.. "injected initial read: " code) :outcome :not-committed})
    (set c.files.read! (fn fail-initial-read [] (error failure 0)))
    (for [_ 1 3]
      (local (ok err) (pcall c.open-view c.surface))
      (assert (not ok) "failed initial read must prevent opening")
      (assert (= err failure) "failed opening must preserve the original structured owning error")))
  (set c.files.read! original-read)
  (assert (= (json.dumps (registrations)) registered-before)
          (.. "repeated failed opens leaked click/hover registrations: before=" registered-before
              " after=" (json.dumps (registrations))))
  (assert (= (draw-count c.ctx) drawn-before) "failed opens must not retain render entries")
  (assert (= (. (c.node:read-text) :revision) c.before.revision) "failed opens must not save"))

(fn gui-invalidates-agent [c]
  (local baseline (value! (c.graph:invoke c.ref "text.read" {} {})))
  (local changes {:count 0})
  (local handler (c.node.changed:connect (fn count-change [] (set changes.count (+ changes.count 1)))))
  (c.view.input:set-text "GUI")
  (assert (= c.node.label "GUI"))
  (assert (= changes.count 1) "one owning signal must update the label once")
  (c.node.changed:disconnect handler)
  (local result (c.graph:invoke c.ref "text.replace" {:text "agent"} {:revision baseline.revision}))
  (assert (= result.error.code :conflict))
  (assert (= (. (c.node:read-text) :value) "GUI")))

(fn agent-invalidates-gui [c]
  (local baseline (value! (c.graph:invoke c.ref "text.read" {} {})))
  (value! (c.graph:invoke c.ref "text.replace" {:text "agent"} {:revision baseline.revision}))
  (assert (= c.node.label "agent"))
  (assert (= (c.view.input:get-text) "initial") "store signals must not reload displayed content")
  (assert-conflict c "attempt one")
  (assert-conflict c "attempt two")
  (assert (= (. (c.node:read-text) :value) "agent")))

(fn legacy-aba [c]
  (with-record-clock (fn timestamp-equal-aba []
    (var saw-same-second false)
    (for [_ 1 5]
      (local other (c.open-view Preview))
      (local baseline (c.node:read-text))
      (local start (. (c.node:get-entity) :updated-at))
      (c.store:update-entity c.node.entity-id {:value "B"})
      (local middle (. (c.node:get-entity) :updated-at))
      (c.store:update-entity c.node.entity-id {:value "initial"})
      (when (= start middle (. (c.node:get-entity) :updated-at)) (set saw-same-second true))
      (assert (not= (. (c.node:read-text) :revision) baseline.revision))
      (other.input:set-text "ABA attempt")
      (assert (= other.editor.last-error.code :conflict))
      (assert (= (other.input:get-text) "ABA attempt")))
    (assert saw-same-second "must exercise same-second ABA writes")
    (assert-conflict c "after ABA")
    (c.store:update-entity c.node.entity-id {:value "initial"})
    (assert-conflict c "after unconditional same-value write")
    (assert (= (. (c.node:read-text) :value) "initial")))))

(fn simultaneous [c]
  (local other (c.open-view Preview))
  (c.view.input:set-text "first editor")
  (other.input:set-text "second editor")
  (assert (= other.editor.last-error.code :conflict))
  (assert (= (other.input:get-text) "second editor"))
  (assert (> (length (status other.editor)) 0))
  (c.view.input:set-text "first editor again")
  (assert (= (. (c.node:read-text) :value) "first editor again") "successful save advances only its own baseline")
  (other.input:set-text "still stale")
  (assert (= other.editor.last-error.code :conflict)))

(fn render-and-drop [c]
  (c.view.layout:measurer)
  (set c.view.layout.size (+ c.view.layout.measure (glm.vec3 20 0 0)))
  (c.view.layout:layouter)
  (assert (> (draw-count c.ctx) 0) "fixture must render text before teardown"))

(fn storage-failure [c]
  (local original c.files.write-text!)
  (set c.files.write-text! (fn fail-write [] (error "injected storage failure")))
  (c.view.input:set-text "not persisted")
  (assert (= c.view.editor.last-error.code :storage-failed))
  (assert (= (c.view.input:get-text) "not persisted"))
  (assert (string.find (status c.view.editor) "not saved" 1 true))
  (assert (= (. (c.node:read-text) :revision) c.before.revision))
  (set c.files.write-text! original)
  (c.view.input:set-text "recovered")
  (assert (= (. (c.node:read-text) :value) "recovered"))
  (assert (= c.view.editor.last-error nil))
  (assert (= (status c.view.editor) "")))

(fn notification-failure [c]
  (local handler (c.store.string-entity-updated:connect (fn fail-notify [] (error "injected listener failure"))))
  (c.view.input:set-text "committed")
  (assert (= c.view.editor.last-error.code :notification-failed))
  (assert (= c.view.editor.last-error.outcome :committed))
  (assert (= (c.view.input:get-text) "committed"))
  (assert (= (. (c.node:read-text) :value) "committed"))
  (assert (= (status c.view.editor) "Save committed; notification failed."))
  (c.store.string-entity-updated:disconnect handler)
  (c.view.input:set-text "next save")
  (assert (= (. (c.node:read-text) :value) "next save") "committed notification error must advance baseline"))

(fn committed-storage-failure [c notification?]
  (local original c.files.write-text!)
  (local boundary (RecordFiles.RecordFiles
    {:publication-hooks {:test-before-cleanup (fn cleanup-fault [] (error "editor cleanup fault"))}}))
  (set c.files.write-text! boundary.write-text!)
  (local observed {:calls 0 :completed false})
  (fn listener [entity]
    (set observed.calls (+ observed.calls 1))
    (local saved (c.node:read-text))
    (assert (= saved.value entity.value "committed"))
    (assert (= saved.revision entity.revision))
    (set observed.completed true)
    (when notification? (error "editor notification fault")))
  (local handler (c.store.string-entity-updated:connect listener))
  (c.view.input:set-text "committed")
  (c.store.string-entity-updated:disconnect handler true)
  (set c.files.write-text! original)
  (assert observed.completed "editor listener assertions must complete")
  (assert (= observed.calls 1))
  (local err c.view.editor.last-error)
  (assert err "cleanup failure must be visible")
  (assert (= err.code :storage-failed))
  (assert (= err.outcome :committed))
  (assert (string.find err.cleanup-error "editor cleanup fault" 1 true))
  (assert (= (not= err.notification-error nil) (not= notification? nil)))
  (assert (= (status c.view.editor) "Save committed; post-save error."))
  (assert (= (c.view.input:get-text) "committed"))
  (assert (= err.result.revision (. (c.node:read-text) :revision)))
  (c.view.input:set-text "next save")
  (assert (= (. (c.node:read-text) :value) "next save") "committed cleanup error must advance baseline")
  (assert (= c.view.editor.last-error nil))
  (assert (= (status c.view.editor) "")))

(each [_ surface (ipairs [{:name "full" :build Full :max-lines 20} {:name "preview" :build Preview :max-lines 3}])]
  (each [_ scenario (ipairs [{:name "opening is read-only" :run opening}
                         {:name "empty opening preserves placeholder and revision" :run empty-opening}
                         {:name "repeated failed opening preserves error and registrations" :run failed-opening-is-nonallocating}
                         {:name "GUI invalidates agent" :run gui-invalidates-agent}
                         {:name "agent invalidates displayed GUI baseline repeatedly" :run agent-invalidates-gui}
                         {:name "unconditional writes and ABA invalidate GUI" :run legacy-aba}
                         {:name "simultaneous editors have independent baselines" :run simultaneous}
                         {:name "rendered children and registrations are dropped" :run render-and-drop}
                         {:name "storage failure preserves input and baseline" :run storage-failure}
                          {:name "notification failure advances committed baseline" :run notification-failure}
                          {:name "cleanup failure advances committed baseline" :run committed-storage-failure}
                          {:name "cleanup and notification failure advance committed baseline"
                           :run (fn both-failures [c] (committed-storage-failure c true))}])]
    (table.insert tests {:name (.. surface.name " " scenario.name)
                         :fn (fn run-scenario [] (with-editor surface.build
                                      (fn check-surface [c]
                                        (assert (= c.view.input.max-lines surface.max-lines))
                                        (scenario.run c))))})))

(fn secondary-failure-control [surface cleanup-fault?]
  (local before (json.dumps (registrations)))
  (local held {})
  (fn fail-with-secondary [c]
    (set held.ctx c.ctx)
    (fn failing-surface [node]
      (local builder (surface node))
      (fn build-secondary [ctx]
        (local view (builder ctx))
        (set held.view view)
        (local drop view.drop)
        (fn drop-secondary [self]
          (drop self)
          (when cleanup-fault? (error "secondary cleanup fault")))
        (fn fail-secondary-assertion [_]
          (view.layout:measurer)
          (set view.layout.size (+ view.layout.measure (glm.vec3 20 0 0)))
          (view.layout:layouter)
          (assert (> (draw-count ctx) 0) "control must allocate render entries")
          (error "secondary assertion fault"))
        (set view.drop drop-secondary)
        (set view.input.get-text fail-secondary-assertion)
        view))
    (set c.surface failing-surface)
    (empty-opening c))
  (local (ok err) (pcall with-editor surface fail-with-secondary))
  (local after (json.dumps (registrations)))
  (local drawn (draw-count (assert held.ctx)))
  ;; RED must not leak its deliberately stranded secondary into other tests.
  ;; Snapshot before this emergency fixture cleanup so it cannot hide the leak.
  (when (and held.view (not held.view.input.__dropped))
    (local (dropped drop-error) (pcall held.view.drop held.view))
    (assert (or dropped (and cleanup-fault? (string.find drop-error "secondary cleanup fault" 1 true)))))
  (assert (not ok))
  (assert (string.find err "secondary assertion fault" 1 true) "original assertion must survive teardown")
  (when cleanup-fault?
    (assert (string.find err "secondary cleanup fault" 1 true) "cleanup failure must be retained alongside assertion"))
  (assert (= before after) "secondary assertion failure leaked widget registrations")
  (assert (= drawn 0) "secondary assertion failure leaked render entries"))

(each [_ surface (ipairs [{:name "full" :build Full} {:name "preview" :build Preview}])]
  (each [_ cleanup-fault? (ipairs [false true])]
    (table.insert tests {:name (.. surface.name " secondary assertion cleanup control " (tostring cleanup-fault?))
                         :fn (fn cleanup-control [] (secondary-failure-control surface.build cleanup-fault?))})))

(fn clock-restoration-control []
  (local original os.time)
  (with-record-clock (fn fixed-time [] (assert (= (os.time) 1700000000))))
  (assert (= os.time original) "successful scope must restore clock identity")
  (local sentinel {})
  (fn throw-in-clock [] (error sentinel 0))
  (local (ok err) (pcall with-record-clock throw-in-clock))
  (assert (and (not ok) (= err sentinel)) "clock scope must preserve the original thrown object")
  (assert (= os.time original) "throwing scope must restore clock identity"))
(table.insert tests {:name "record clock restores after success and assertion failure" :fn clock-restoration-control})

(fn main [] ((. (require :tests/runner) :run-tests) {:name "string-entity-editor" :tests tests}))
{:name "string-entity-editor" :tests tests :main main}
