(local tests [])
(local fs (require :fs))
(local tempfile (require :tempfile))
(local Sha256 (require :repo/sha256))
(local Process (require :process))

(fn all-bytes []
  (var content "")
  (for [i 0 255]
    (set content (.. content (string.char i))))
  content)

(local vectors
  [["" "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"]
   ["abc" "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"]
   [(string.char 0) "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"]
   ["abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"
    "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"]
   [(all-bytes) "40aff2e9d2d8922e47afd4648e6967497158785fbd1da870e7110266bf944880"]])

(fn assert-vectors [hash]
  (each [_ vector (ipairs vectors)]
    (local digest (hash (. vector 1)))
    (assert (= digest (. vector 2)) "SHA-256 exact binary vector mismatch")
    (assert (and (= (# digest) 64) (string.match digest "^[0-9a-f]+$"))
            "SHA-256 must return canonical lowercase hex")))

(fn without-process [body]
  (local original Process.run)
  (set Process.run (fn [...] (error "SHA-256 must not launch a subprocess")))
  (local (ok err) (pcall body))
  (set Process.run original)
  (when (not ok) (error err)))

(fn sha256-empty-string []
  (local h (Sha256.hash ""))
  (assert (= (# h) 64) "sha256 hex should be 64 chars")
  (assert (= h "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
          "sha256 of empty string should match known value"))

(fn sha256-known-value []
  (local h (Sha256.hash "hello"))
  (assert (= h "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")))

(fn sha256-binary-content []
  (assert-vectors Sha256.hash))

(fn sha256-file []
  (local h (tempfile.NamedTemporaryFile {:prefix "sha256test_" :suffix ".txt"}))
  (local (ok err)
    (pcall (fn []
             (each [_ vector (ipairs vectors)]
               (fs.write-file h.path (. vector 1))
               (local file-hash (Sha256.hash-file h.path))
               (assert (= file-hash (. vector 2)) "file hash must match exact binary vector")
               (assert (= file-hash (Sha256.hash (. vector 1)))
                       "file hash should match content hash")))))
  (h:drop)
  (when (not ok) (error err)))

(fn sha256-rejects-nil []
  (local (ok _err) (pcall Sha256.hash nil))
  (assert (not ok) "should reject nil"))

(table.insert tests {:name "sha256 of empty string" :fn sha256-empty-string})
(table.insert tests {:name "sha256 of known value" :fn sha256-known-value})
(table.insert tests {:name "sha256 of binary content" :fn sha256-binary-content})
(table.insert tests {:name "sha256 file hashing" :fn sha256-file})
(table.insert tests {:name "sha256 rejects nil" :fn sha256-rejects-nil})

(fn sha256-native-contract []
  (assert (= (type (. package.preload :sha256)) :function) "native SHA preload missing")
  (local Native (require :sha256))
  (assert-vectors Native.hash)
  (assert (not (pcall Native.hash)) "native hash must reject absent input")
  (assert (not (pcall Native.hash nil)) "native hash must reject nil")
  (each [_ value (ipairs [42 false {} io.stdout])]
    (assert (not (pcall Native.hash value)) "native hash must reject non-strings")))

(fn sha256-strict-wrapper []
  (assert (not (pcall Sha256.hash)) "hash must reject absent input")
  (assert (not (pcall Sha256.hash-file nil)) "hash-file must reject nil")
  (each [_ value (ipairs [42 false {} io.stdout])]
    (assert (not (pcall Sha256.hash value)) "hash must reject non-strings")
    (local (ok err) (pcall Sha256.hash-file value))
    (assert (and (not ok) (string.find (tostring err) "sha256 requires a string path" 1 true))
            "hash-file must reject non-string paths before filesystem coercion")))

(fn sha256-read-errors []
  (local h (tempfile.NamedTemporaryFile {:prefix "sha256missing_"}))
  (h:drop)
  (local (ok err) (pcall Sha256.hash-file h.path))
  (assert (and (not ok) (string.find (tostring err) "unable to open" 1 true))
          "missing-file error must propagate")
  (local dir (tempfile.TemporaryDirectory {:prefix "sha256unreadable_"}))
  ;; Opening a directory may fail at open or read depending on the host. Preserve
  ;; the actual strict filesystem error rather than prescribing host errno timing.
  (local (fs-ok fs-err) (pcall fs.read-file dir.path))
  (local (read-ok read-err) (pcall Sha256.hash-file dir.path))
  (dir:drop)
  (assert (not fs-ok) "filesystem must reject reading a directory")
  (assert (and (not read-ok) (= read-err fs-err)) "exact filesystem read error must propagate"))

(fn sha256-no-subprocess []
  (without-process (fn [] (assert-vectors Sha256.hash) (sha256-file))))

(fn sha256-process-seam-restored []
  (local original Process.run)
  (local (ok err) (pcall without-process (fn [] (error "restoration sentinel"))))
  (assert (and (not ok) (string.find (tostring err) "restoration sentinel" 1 true)))
  (assert (= Process.run original) "Process.run must be restored even after errors"))

(table.insert tests {:name "sha256 native strict binary contract" :fn sha256-native-contract})
(table.insert tests {:name "sha256 wrapper rejects non-string input and paths" :fn sha256-strict-wrapper})
(table.insert tests {:name "sha256 propagates missing-file and read errors" :fn sha256-read-errors})
(table.insert tests {:name "sha256 never launches a subprocess" :fn sha256-no-subprocess})
(table.insert tests {:name "sha256 subprocess seam restores after errors" :fn sha256-process-seam-restored})

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "repo-sha256"
                       :tests tests})))

{:name "repo-sha256"
 :tests tests
 :main main}
