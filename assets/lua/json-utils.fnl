(local fs (require :fs))
(local json (require :json))

(assert fs "json-utils requires fs module")
(assert json "json-utils requires json module")

(fn write-json-atomic! [path payload]
    (local tmp-path (.. path ".tmp"))
    (fs.write-file tmp-path payload)
    (local (ok err) (pcall fs.rename tmp-path path))
    (when (not ok)
        (pcall (fn [] (fs.remove tmp-path)))
        (local message (string.format "json-utils failed to rename %s to %s: %s"
                                      tmp-path
                                      path
                                      err))
        (error message))
    true)

(fn write-json! [path data opts]
    (local options (if (= opts nil) {} opts))
    (assert (= (type options) :table) "json-utils options must be a table")
    (each [key value (pairs options)]
        (assert (= key :publish!) (.. "json-utils unknown option: " (tostring key)))
        (assert (= (type value) :function) "json-utils publish! must be a function"))
    (local payload (json.dumps data))
    (if options.publish!
        (options.publish! path payload)
        (write-json-atomic! path payload)))

(fn array-table? [value]
    (var count 0)
    (var array? true)
    (each [key _item (pairs value)]
        (set count (+ count 1))
        (when (not (and (= (type key) :number)
                        (= key (math.floor key))
                        (>= key 1)))
            (set array? false)))
    (and array? (= count (length value))))

(fn sorted-keys [value]
    (local keys [])
    (each [key _item (pairs value)]
        (table.insert keys key))
    (table.sort keys (fn [left right]
                       (< (tostring left) (tostring right))))
    keys)

(fn stable-json [value]
    (if (= (type value) :table)
        (if (array-table? value)
            (do
                (local parts [])
                (each [_ item (ipairs value)]
                    (table.insert parts (stable-json item)))
                (.. "[" (table.concat parts ",") "]"))
            (do
                (local parts [])
                (each [_ key (ipairs (sorted-keys value))]
                    (table.insert parts (.. (json.dumps (tostring key)) ":" (stable-json (. value key)))))
                (.. "{" (table.concat parts ",") "}")))
        (if (= value nil)
            "null"
            (json.dumps value))))

{:write-json! write-json!
 :stable-json stable-json}
