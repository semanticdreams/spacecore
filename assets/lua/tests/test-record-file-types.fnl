;; Kept separate from the near-limit persistence suite; its cases are included
;; there so the existing focused/full-suite entrypoint covers this boundary.
(local fs (require :fs))
(local Files (require :entities/record-files))
(local Strings (require :entities/string))
(local Links (require :entities/link))
(local tempfile (require :tempfile))
(local process (require :process))
(local tests [])
(local posix? (= (string.sub package.config 1 1) "/"))

(fn with-directory [body]
  (local dir (tempfile.TemporaryDirectory {:prefix "record-types-"}))
  (local (ok result) (pcall body dir.path))
  (dir:drop)
  (when (not ok) (error result 0)))

(fn storage-error [ok err]
  (assert (not ok) "nonregular record must fail explicitly")
  (assert (= (type err) :table))
  (assert (= err.code :storage-failed)))

(fn fifo-child-main []
  (local path (assert (os.getenv "RECORD_FILES_FIFO")))
  (local (ok err) (pcall Files.read! path 64))
  (storage-error ok err)
  (assert (string.find err.message "regular file" 1 true))
  (print "FIFO rejected before open"))

(fn fifo-root [root]
  (local path (fs.join-path root "record.md"))
  (assert (= (. (process.run {:args ["mkfifo" path] :timeout 10}) :exit-code) 0))
  ;; Real default io.open in an owned, bounded child: RED cannot hang the
  ;; synchronous parent test runner on a FIFO with no writer.
  (local child (process.run
    {:args [((. (require :tests/runtime-bin) :resolve)) "-m" "tests.test-record-file-types:fifo-child-main"]
     :env {:RECORD_FILES_FIFO path :SPACE_DISABLE_AUDIO "1" :SKIP_KEYRING_TESTS "1"
           :XDG_DATA_HOME (os.getenv "XDG_DATA_HOME") :SPACE_ASSETS_PATH (os.getenv "SPACE_ASSETS_PATH")
           :FENNEL_PATH (os.getenv "FENNEL_PATH") :FENNEL_MACRO_PATH (os.getenv "FENNEL_MACRO_PATH")}
     :timeout 5}))
  (assert (= child.exit-code 0) (.. child.stdout child.stderr))
  (assert (string.find child.stdout "FIFO rejected before open" 1 true)))

(fn fifo-read []
  (if (not posix?)
      (print "FIFO read: NOT APPLICABLE (non-POSIX)")
      (with-directory fifo-root)))

(fn scan-root [root kind]
  (each [_ spec (ipairs [[Strings.StringEntityStore ".md"] [Links.LinkEntityStore ".json"]])]
    (local store ((. spec 1) {:base-dir root}))
    (fs.create-dir (fs.join-path store.entities-dir "ignored.other"))
    (assert (= (length (. (store:scan-page {}) :items)) 0) "nonmatching nonregular entry is irrelevant")
    (local path (fs.join-path store.entities-dir (.. "bad" (. spec 2))))
    (if (= kind :directory)
        (assert (fs.create-dir path))
        (assert (= (. (process.run {:args ["mkfifo" path] :timeout 10}) :exit-code) 0)))
    (local (ok err) (pcall store.scan-page store {}))
    (storage-error ok err)))

(fn scan-nonregular [kind]
  (if (and (= kind :fifo) (not posix?))
      (print "FIFO scan: NOT APPLICABLE (non-POSIX)")
      (with-directory (fn exercise-scan [root] (scan-root root kind)))))

(table.insert tests {:name "record files reject direct FIFO reads before open" :fn fifo-read})
(table.insert tests {:name "record scans reject suffix-matching directories" :fn (fn directory-scan [] (scan-nonregular :directory))})
(table.insert tests {:name "record scans reject suffix-matching FIFOs" :fn (fn fifo-scan [] (scan-nonregular :fifo))})
(fn main [] ((. (require :tests/runner) :run-tests) {:name "record-file-types" :tests tests}))
{:tests tests :main main :fifo-child-main fifo-child-main}
