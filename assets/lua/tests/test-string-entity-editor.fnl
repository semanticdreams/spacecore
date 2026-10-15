(local BuildContext (require :build-context))
(local Strings (require :entities/string))
(local Links (require :entities/link))
(local RecordFiles (require :entities/record-files))
(local Graph (require :graph/init))
(local {:StringEntityNode StringEntityNode} (require :graph/nodes/string-entity))
(local Full (require :graph/view/views/string-entity))
(local Preview (require :graph/view/previews/string-entity))
(local tempfile (require :tempfile))
(local json (require :json))
(local glm (require :glm))
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

(fn with-editor [surface f]
  (local dir (tempfile.TemporaryDirectory {:prefix "string-editor-"}))
  (local files (collect [k v (pairs RecordFiles)] (values k v)))
  (local store (Strings.StringEntityStore {:base-dir dir.path :files files}))
  (local links (Links.LinkEntityStore {:base-dir dir.path}))
  (local graph (Graph {:with-start false :entity-events? false :string-store store :link-store links :morphs {}}))
  (local access ((. (require :graph/capabilities/entities) :access-by-scheme) {:string-store store :link-store links}))
  (each [scheme provider (pairs access)]
    (graph:register-key-loader scheme (fn no-visual [] (error "must not materialize")) {:access provider}))
  (local entity (store:create-entity {:value "initial"}))
  (local node (StringEntityNode {:entity-id entity.id :store store}))
  (local ctx (BuildContext {:clickables app.clickables :hoverables app.hoverables
                           :icons {:resolve (fn no-icon [] nil)}}))
  (local before (store:read-text entity.id))
  (local registered-before (registrations))
  (local view ((surface node) ctx))
  (local (ok err) (pcall f {:store store :files files :node node :view view :ctx ctx
                           :graph graph :ref {:key node.key} :before before :surface surface}))
  (view:drop)
  (when ok
    (assert view.input.__dropped "owning composite must drop Input")
    (assert (= (json.dumps (registrations)) (json.dumps registered-before)) "widget registrations leaked")
    (assert (= (draw-count ctx) 0) "text render entries leaked"))
  (node:drop)
  (when ok
    (local label node.label)
    (store:update-entity entity.id {:value "after node drop"})
    (assert (= node.label label) "node store subscription leaked after drop"))
  (graph:drop)
  (dir:drop)
  (when (not ok) (error (if (= (type err) :table) (json.dumps err) err))))

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
  (local other ((c.surface c.node) c.ctx))
  (assert (= (other.input:get-text) ""))
  (assert (= (. (c.node:read-text) :revision) before.revision) "opening empty text must not save")
  (local placeholder (table.concat (icollect [_ cp (ipairs (other.input.placeholder:get-codepoints))] (utf8.char cp))))
  (assert (= placeholder (if (= c.surface Full) "Enter value..." "Value...")))
  (other:drop))

(fn failed-opening-is-nonallocating [c]
  (local registered-before (json.dumps (registrations)))
  (local drawn-before (draw-count c.ctx))
  (local original-read c.files.read!)
  (each [_ code (ipairs [:not-found :storage-failed :corrupt-data])]
    (local failure {:code code :message (.. "injected initial read: " code) :outcome :not-committed})
    (set c.files.read! (fn fail-initial-read [] (error failure 0)))
    (for [_ 1 3]
      (local builder (c.surface c.node))
      (local (ok err) (pcall builder c.ctx))
      (when ok (err:drop))
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
  ;; Exercise real timestamp-equal ABA writes without rebinding the global clock.
  (var saw-same-second false)
  (for [_ 1 5]
    (local other ((Preview c.node) c.ctx))
    (local baseline (c.node:read-text))
    (local start (. (c.node:get-entity) :updated-at))
    (c.store:update-entity c.node.entity-id {:value "B"})
    (local middle (. (c.node:get-entity) :updated-at))
    (c.store:update-entity c.node.entity-id {:value "initial"})
    (when (= start middle (. (c.node:get-entity) :updated-at)) (set saw-same-second true))
    (assert (not= (. (c.node:read-text) :revision) baseline.revision))
    (other.input:set-text "ABA attempt")
    (assert (= other.editor.last-error.code :conflict))
    (assert (= (other.input:get-text) "ABA attempt"))
    (other:drop))
  (assert saw-same-second "must exercise same-second ABA writes")
  (assert-conflict c "after ABA")
  (c.store:update-entity c.node.entity-id {:value "initial"})
  (assert-conflict c "after unconditional same-value write")
  (assert (= (. (c.node:read-text) :value) "initial")))

(fn simultaneous [c]
  (local other ((Preview c.node) c.ctx))
  (c.view.input:set-text "first editor")
  (other.input:set-text "second editor")
  (assert (= other.editor.last-error.code :conflict))
  (assert (= (other.input:get-text) "second editor"))
  (assert (> (length (status other.editor)) 0))
  (c.view.input:set-text "first editor again")
  (assert (= (. (c.node:read-text) :value) "first editor again") "successful save advances only its own baseline")
  (other.input:set-text "still stale")
  (assert (= other.editor.last-error.code :conflict))
  (other:drop))

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
  (assert (string.find (status c.view.editor) "Save committed" 1 true))
  (c.store.string-entity-updated:disconnect handler)
  (c.view.input:set-text "next save")
  (assert (= (. (c.node:read-text) :value) "next save") "committed notification error must advance baseline"))

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
                         {:name "notification failure advances committed baseline" :run notification-failure}])]
    (table.insert tests {:name (.. surface.name " " scenario.name)
                         :fn (fn run-scenario [] (with-editor surface.build
                                      (fn check-surface [c]
                                        (assert (= c.view.input.max-lines surface.max-lines))
                                        (scenario.run c))))})))

(fn main [] ((. (require :tests/runner) :run-tests) {:name "string-entity-editor" :tests tests}))
{:name "string-entity-editor" :tests tests :main main}
