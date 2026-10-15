;; Checked publication local to the string/link owning stores. No power-loss or
;; external-writer coordination guarantee; rename is the commit point.
(local fs (require :fs))
(local json (require :json))
(local JsonUtils (require :json-utils))
(local Uuid (require :uuid))

(fn fail [message]
  (error {:code :storage-failed :message (tostring message) :outcome :not-committed}))

(fn checked [value err]
  (when (not value)
    (error {:code :storage-failed :message (or err "record I/O failed") :outcome :not-committed}))
  value)

(fn RecordFiles [opts]
  (local options (or opts {}))
  (assert (= (type options) :table) "RecordFiles options must be a table")
  (local open (or options.open io.open))
  (local rename (or options.rename os.rename))
  (local stage-json! (or options.stage-json! JsonUtils.write-json!))

  (fn read! [path max-bytes]
    (local handle (checked (open path "rb")))
    (local (ok content err) (pcall handle.read handle (if max-bytes (+ max-bytes 1) "a")))
    (local (close-ok closed close-err) (pcall handle.close handle))
    (when (not ok) (fail content))
    (when err (fail err))
    (when (not close-ok) (fail closed))
    (checked closed close-err)
    (local text (or content ""))
    (when (and max-bytes (> (length text) max-bytes))
      (error {:code :limit-exceeded :message "record exceeds stored-byte limit" :outcome :not-committed}))
    text)

  (fn stage-text! [path text]
    (local handle (checked (open path "wb")))
    (fn write-and-flush []
      (checked (handle:write text))
      (checked (handle:flush)))
    (local (ok err) (pcall write-and-flush))
    (local (close-ok closed close-err) (pcall handle.close handle))
    (when (not ok) (error err))
    (when (not close-ok) (fail closed))
    (checked closed close-err))

  (fn publish! [path payload stage!]
    ;; Keep staging a same-directory sibling, independent of destination length.
    (local staging (fs.join-path (fs.parent path) (.. "record-stage-" (Uuid.v4))))
    (fn attempt []
      (stage! staging)
      (when (not= (read! staging (+ (length payload) 1)) payload)
        (fail "staged record verification failed"))
      (checked (rename staging path)))
    (local (ok err) (pcall attempt))
    (when (not ok)
      ;; Both names belong exclusively to this attempt, including json-utils'
      ;; private atomic-write temporary. Never remove the destination.
      (os.remove staging)
      (os.remove (.. staging ".tmp"))
      (if (and (= (type err) :table) (= err.code :storage-failed))
          (error err)
          (fail err)))
    true)

  (fn write-text! [path text]
    (fn stage [staging] (stage-text! staging text))
    (publish! path text stage))

  (fn write-json! [path data]
    (local payload (json.dumps data))
    (fn stage [staging] (stage-json! staging data))
    (publish! path payload stage))

  (fn list-ids [dir suffix]
    (local (ok entries) (pcall fs.list-dir dir false))
    (when (not ok) (fail entries))
    (when (not= (type entries) :table) (fail "directory enumeration failed"))
    (local ids [])
    (each [_ entry (ipairs entries)]
      (when entry.error (fail (.. "directory entry stat failed: " (tostring entry.error))))
      (when (and entry.is-file (= (string.sub entry.name (- (length suffix))) suffix))
        (table.insert ids (string.sub entry.name 1 (- (- (length suffix)) 1)))))
    (table.sort ids)
    ids)

  (fn remove! [path] (checked (os.remove path)))

  {:read! read! :write-text! write-text! :write-json! write-json!
   :list-ids list-ids :remove! remove!})

(local default (RecordFiles))
{:RecordFiles RecordFiles
 :read! default.read! :write-text! default.write-text! :write-json! default.write-json!
 :list-ids default.list-ids :remove! default.remove!}
