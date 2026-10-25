(local fs (require :fs))
(local appdirs (require :appdirs))
(local Uuid (require :uuid))
(local Signal (require :signal))
(local J (require :json-utils))
(local R (require :reference-lifecycle/record-utils))

(local statuses {:running true :succeeded true :failed true :interrupted true :timed-out true})

(fn text! [value name]
  (assert (= (type value) :string) (.. name " must be text"))
  value)

(fn validate [run]
  (assert (= run.schema-version 1) "unsupported code-run schema")
  (R.require-id run.id)
  (assert (. statuses run.status) "invalid code-run status")
  (assert (= (type run.snapshot) :table) "code-run requires source snapshot")
  (each [_ field (ipairs [:source :language :name])]
    (text! (. run.snapshot field) field))
  (assert (or (= (type run.snapshot.kernel) :number) (= (type run.snapshot.kernel) :string)) "invalid kernel selector")
  (text! run.code-entity-id "code-entity-id")
  (each [_ field (ipairs [:created-at :started-at :started-monotonic-ms :elapsed-ms :timeout-ms])]
    (local value (. run field))
    (assert (and (= (type value) :number) (>= value 0) (< value math.huge)) (.. "invalid " field)))
  (assert (or (= run.finished-at false) (= (type run.finished-at) :number)) "invalid finished-at")
  (assert (= (= run.status "running") (= run.finished-at false)) "run status/finish mismatch")
  (each [_ field (ipairs [:output :result :result-type :initial-result])]
    (text! (. run field) field))
  (assert (or (= run.error false) (and (= (type run.error) :table)
                (= (type run.error.message) :string) (= (type run.error.traceback) :string))) "invalid run error")
  (R.require-array run.artifacts)
  (each [_ artifact (ipairs run.artifacts)]
    (assert (and (= (type artifact.key) :string) (string.find artifact.key "%S")
                 (= (type artifact.label) :string)) "invalid run artifact"))
  (assert (= (type run.owner) :table) "code-run requires execution owner")
  (assert (and (= (type run.owner.session) :string) (> (# run.owner.session) 0)) "invalid execution owner session")
  (when run.owner.pid
    (assert (and (= (type run.owner.pid) :string) (string.match run.owner.pid "^%d+$")
                 (= (type run.owner.start) :string) (string.match run.owner.start "^%d+$")
                 (= (type run.owner.boot) :string)) "invalid process owner identity"))
  run)

(fn Store [opts]
  (local options (or opts {}))
  (assert (= (type options) :table) "code-run store requires options")
  (local base-dir (fs.absolute (or options.base-dir (appdirs.user-data-dir "space"))))
  (local directory (fs.join-path base-dir "code-runs"))
  (local changed (Signal))
  (fn path [id] (R.record-path base-dir directory id ".json"))
  (fn get-run [_self id]
    (fn decode [bytes] (validate (R.decode-json bytes)))
    (local snapshot (R.snapshot (path id) "json" decode))
    (when snapshot.value
      (assert (= snapshot.value.id id) "code-run record id mismatch")
      (R.clone snapshot.value)))
  (fn persist [run]
    (validate run)
    (fs.create-dirs directory)
    (J.write-json! (path run.id) run)
    ;; Persistence is committed before observers see it. Observer failures remain explicit.
    (local (ok err) (pcall changed.emit changed (R.clone run)))
    (when (not ok)
      (io.stderr:write (.. "code-run observer failed after persistence: " (tostring err) "\n")))
    (R.clone run))
  (fn create-run [self data]
    (local run (R.clone data))
    (set run.id (Uuid.v4))
    (set run.schema-version 1)
    (assert (not (self:get-run run.id)) "code-run id collision")
    (persist run))
  (fn update-run [self id updates]
    (local run (assert (self:get-run id) "missing code run"))
    (assert (= run.status "running") "cannot modify a terminal code run")
    (each [field value (pairs updates)]
      (assert (not (or (= field :id) (= field :snapshot) (= field :code-entity-id)
                       (= field :owner) (= field :created-at) (= field :started-at) (= field :started-monotonic-ms)
                       (= field :schema-version))) "cannot modify code-run provenance")
      (tset run field (R.clone value)))
    (persist run))
  (fn list-runs [self code-id]
    (local runs [])
    (each [_ entry (ipairs (R.record-entries directory ".json"))]
      (local run (assert (self:get-run (string.sub entry.name 1 -6))))
      (when (or (= code-id nil) (= run.code-entity-id code-id)) (table.insert runs run)))
    (table.sort runs (fn newest [a b]
      (if (not (= a.created-at b.created-at)) (> a.created-at b.created-at)
          (not (= a.started-monotonic-ms b.started-monotonic-ms)) (> a.started-monotonic-ms b.started-monotonic-ms)
          (> a.id b.id))))
    runs)
  {:base-dir base-dir :directory directory :changed changed
   :get-run get-run :create-run create-run :update-run update-run :list-runs list-runs})

{:Store Store :validate validate}
