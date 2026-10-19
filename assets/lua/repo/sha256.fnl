(local Native (require :sha256))
(local fs (require :fs))

(fn hash [content]
  (assert (= (type content) "string") "sha256 requires a string")
  (Native.hash content))

(fn hash-file [path]
  (assert (= (type path) "string") "sha256 requires a string path")
  (hash (fs.read-file path)))

{:hash hash
 :hash-file hash-file}
