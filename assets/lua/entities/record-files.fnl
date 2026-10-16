;; Checked publication local to the string/link owning stores. No power-loss or
;; external-writer coordination guarantee; native replacement is the commit point.
(local fs (require :fs))
(local JsonUtils (require :json-utils))

(fn fail [message]
  (error {:code :storage-failed :message (tostring message) :outcome :not-committed}))

(fn checked [value err]
  (when (not value)
    (error {:code :storage-failed :message (or err "record I/O failed") :outcome :not-committed}))
  value)

(fn RecordFiles [opts]
  (local options (if (= opts nil) {} opts))
  (assert (= (type options) :table) "RecordFiles options must be a table")
  (each [key _ (pairs options)]
    (assert (or (= key :open) (= key :publication-hooks)) (.. "RecordFiles unknown option: " (tostring key))))
  (local open (if (= options.open nil) io.open options.open))
  (assert (= (type open) :function) "RecordFiles open must be a read function")

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

  (fn publish! [path payload]
    ;; The native boundary owns every payload write, validation and replacement.
    ;; The injected open above is used only by read!, never for publication.
    (fn attempt [] (fs.publish-record path payload options.publication-hooks))
    (local (ok result) (pcall attempt))
    (when (not ok)
      (if (and (= (type result) :table) (= result.code :storage-failed))
          (error result)
          (fail result)))
    (values true result.cleanup-error))

  (fn write-text! [path text]
    (publish! path text))

  (fn write-json! [path data]
    (JsonUtils.write-json! path data {:publish! publish!}))

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
