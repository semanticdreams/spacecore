(local tests [])
(local fs (require :fs))

(var temp-counter 0)
(local temp-root (fs.join-path "/tmp/space/tests" "constraints-source-test"))

(fn temp-dir-name []
  (set temp-counter (+ temp-counter 1))
  (fs.join-path temp-root (.. "test-" (os.time) "-" temp-counter)))

(fn make-file [dir name content]
  "Create a file in dir with given name and content."
  (local path (fs.join-path dir name))
  (fs.write-file path content)
  path)

(fn with-temp-dir [f]
  (local dir (temp-dir-name))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (fs.create-dirs dir)
  (local (ok result) (pcall f dir))
  (fs.remove-all dir)
  (if ok
      result
      (error result)))

;; --- Target resolution tests ---

(fn targets-resolve-defaults-to-repo []
  (local Targets (require :constraints.targets))
  (local result (Targets.resolve [] {}))
  (assert (= result.kind :repo) (.. "expected :repo, got " (tostring result.kind)))
  (assert (= result.name "repo") "default target name should be repo")
  (assert result.roots "should have roots")
  (assert (> (# result.roots) 0) "roots should not be empty")
  ;; At least one root should contain assets/lua
  (var found false)
  (each [_ root (ipairs result.roots)]
    (when (or (string.find root "assets/lua" 1 true)
              (string.find root "assets" 1 true))
      (set found true)))
  (assert found "roots should include assets/lua")
  (assert result.suites "should have suites")
  ;; All four families should be present
  (local suite-set {})
  (each [_ s (ipairs result.suites)]
    (tset suite-set s true))
  (assert (. suite-set :scene-sandbox) "suites should include :scene-sandbox")
  (assert (. suite-set :lifecycle) "suites should include :lifecycle")
  (assert (. suite-set :test-isolation) "suites should include :test-isolation")
  (assert (. suite-set :layout-rendering) "suites should include :layout-rendering")
  (assert (. suite-set :structure-formatting) "suites should include :structure-formatting")
  (assert result.module-roots "should have module-roots"))

(fn targets-resolve-unit-with-root []
  (local Targets (require :constraints.targets))
  (local result (Targets.resolve ["--target" "unit"
                                   "--root" "/tmp/space/constraints-unit"] {}))
  (assert (= result.kind :unit) (.. "expected :unit, got " (tostring result.kind)))
  (assert result.name "unit target should have a name")
  (assert result.roots "unit target should have roots")
  (assert (> (# result.roots) 0) "unit root list should not be empty")
  ;; Check that --root value is reflected
  (var found-root false)
  (each [_ root (ipairs result.roots)]
    (when (string.find root "constraints-unit" 1 true)
      (set found-root true)))
  (assert found-root "unit roots should include constraints-unit"))

(fn targets-resolve-app-with-root []
  (local Targets (require :constraints.targets))
  (local result (Targets.resolve ["--target" "app"
                                   "--root" "/tmp/space/constraints-app"] {}))
  (assert (= result.kind :app) (.. "expected :app, got " (tostring result.kind)))
  (assert result.name "app target should have a name")
  (assert result.roots "app target should have roots")
  (var found-root false)
  (each [_ root (ipairs result.roots)]
    (when (string.find root "constraints-app" 1 true)
      (set found-root true)))
  (assert found-root "app roots should include constraints-app"))

(fn targets-resolve-files-with-file []
  (local Targets (require :constraints.targets))
  (local result (Targets.resolve ["--target" "files"
                                   "--file" "/tmp/space/constraints-one.fnl"] {}))
  (assert (= result.kind :files) (.. "expected :files, got " (tostring result.kind)))
  (assert result.files "files target should have files list")
  (assert (> (# result.files) 0) "files list should not be empty")
  (assert (= (. result.files 1) (fs.absolute "/tmp/space/constraints-one.fnl"))
          "files list should contain the absolute specified file"))

(fn targets-resolve-refuses-unsupported-target []
  (local Targets (require :constraints.targets))
  (local (ok err) (pcall #(Targets.resolve ["--target" "bogus"] {})))
  (assert (not ok) "should fail for unsupported target")
  (assert (string.find (tostring err) "unsupported" 1 true)
          "error should mention unsupported"))

(fn targets-resolve-refuses-missing-target-value []
  (local Targets (require :constraints.targets))
  (local (ok err) (pcall #(Targets.resolve ["--target"] {})))
  (assert (not ok) "should fail when --target has no value"))

(fn targets-resolve-refuses-missing-root-for-unit []
  (local Targets (require :constraints.targets))
  (local (ok err) (pcall #(Targets.resolve ["--target" "unit"] {})))
  (assert (not ok) "should fail when unit target has no --root"))

(fn targets-resolve-refuses-unknown-flag []
  (local Targets (require :constraints.targets))
  (local (ok err) (pcall #(Targets.resolve ["--traget" "files" "--file" "/tmp/bad.fnl"] {})))
  (assert (not ok) "should fail for an unrecognized flag")
  (assert (string.find (tostring err) "unrecognized flag" 1 true)
          (.. "error should mention unrecognized flag, got: " (tostring err))))

(fn targets-resolve-refuses-stray-positional []
  (local Targets (require :constraints.targets))
  (local (ok err) (pcall #(Targets.resolve ["--target" "files" "stray" "--file" "/tmp/bad.fnl"] {})))
  (assert (not ok) "should fail for a stray positional argument")
  (assert (string.find (tostring err) "unexpected positional argument" 1 true)
          (.. "error should mention positional argument, got: " (tostring err))))

;; --- Source discovery tests ---

(fn source-discovers-fnl-files-recursively []
  (with-temp-dir (fn [dir]
    (local subdir (fs.join-path dir "sub"))
    (fs.create-dirs subdir)
    (make-file dir "alpha.fnl" "(print :alpha)")
    (make-file subdir "beta.fnl" "(print :beta)")
    (make-file dir "readme.txt" "text file")
    (local target {:kind :unit :name "test-unit" :roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (local paths {})
    (each [_ r (ipairs records)]
      (tset paths r.path true))
    (assert (. paths (fs.absolute (fs.join-path dir "alpha.fnl"))) "alpha.fnl should be discovered")
    (assert (. paths (fs.absolute (fs.join-path subdir "beta.fnl"))) "sub/beta.fnl should be discovered")
    (assert (not (. paths (fs.join-path dir "readme.txt"))) "readme.txt should be excluded")
    (assert (= (# records) 2) (.. "expected 2 records, got " (# records))))))

(fn source-excludes-non-fennel-files []
  (with-temp-dir (fn [dir]
    (make-file dir "code.fnl" "(+ 1 2)")
    (make-file dir "config.lua" "return {}")
    (make-file dir "notes.md" "# notes")
    (local target {:kind :unit :name "filter-test" :roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1) (.. "expected 1 fennel record, got " (# records)))
    (assert (= (fs.parent (. records 1 :path)) (fs.absolute dir))))))

(fn source-parses-files-with-tree-sitter []
  (with-temp-dir (fn [dir]
    (make-file dir "sample.fnl" "(fn add [a b]\n  (+ a b))\n")
    (local target {:kind :unit :name "parse-test" :roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1) "should discover one file")
    (local r (. records 1))
    (assert r.tree "file record should have a tree")
    (assert r.root "file record should have a root node")
    (assert (not (r.root:is-null)) "root node should not be null")
    (assert (> (r.root:child-count) 0) "root should have children"))))

(fn source-files-outside-assets-lua-parse-and-retain-target []
  (with-temp-dir (fn [dir]
    (local file-path (make-file dir "external.fnl" "(+ 1 2)"))
    (local target {:kind :files
                    :name "external-files"
                    :files [file-path]
                    :roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1) "should discover the external file")
    (local r (. records 1))
    (assert (= r.path (fs.absolute file-path)) "path should match the absolute original file")
    (assert r.target "record should retain target")
    (assert (= r.target.kind :files) "target kind should be :files")
    (assert (= r.target.name "external-files") "target name should be preserved")
    (assert r.tree "external file should have a parsed tree"))))

(fn source-node-text-returns-substring []
  (with-temp-dir (fn [dir]
    (make-file dir "sample.fnl" "(fn hello [name]\n  (print name))\n")
    (local target {:kind :unit :name "node-text-test" :roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (local r (. records 1))
    ;; Grab a child node and verify node-text extracts correct substring
    (local root r.root)
    (assert (> (root:child-count) 0) "root should have children")
    (local child (root:child 0))
    (local text (Source.node-text r.source child))
    (assert text "node-text should return a non-empty string")
    (assert (> (# text) 0) "node-text should return something"))))

(fn source-node-location-returns-line-and-column []
  (with-temp-dir (fn [dir]
    (make-file dir "sample.fnl" "(fn hello [name]\n  (print name))\n")
    (local target {:kind :unit :name "loc-test" :roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (local r (. records 1))
    (local loc (Source.node-location r.root))
    (assert loc "node-location should return a table")
    (assert (= (. loc :line) 1)
            (.. "root should start on one-based line 1, got " (tostring (. loc :line))))
    (assert (= (. loc :column) 1)
            (.. "root should start on one-based column 1, got " (tostring (. loc :column)))))))

(fn source-walk-visits-all-nodes-depth-first []
  (with-temp-dir (fn [dir]
    (make-file dir "sample.fnl" "(print :hello)")
    (local target {:kind :unit :name "walk-test" :roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (local r (. records 1))
    (var visited 0)
    (Source.walk r.root (fn [_node] (set visited (+ visited 1))))
    (assert (> visited 1) (.. "walk should visit more than 1 node, got " visited)))))

;; --- Multiple --root tests ---

(fn targets-resolve-repeated-root []
  (local Targets (require :constraints.targets))
  (local result (Targets.resolve ["--target" "unit"
                                   "--root" "/tmp/space/constraints-r1"
                                   "--root" "/tmp/space/constraints-r2"] {}))
  (assert (= result.kind :unit) "kind should be :unit")
  (assert (= (# result.roots) 2) (.. "expected 2 roots, got " (# result.roots))))

;; --- Module name computation tests (R1-1) ---

(fn source-computes-module-name-from-root []
  "A file under a module root should produce a dotted module name (no .fnl, / -> .)"
  (with-temp-dir (fn [dir]
    (local subdir (fs.join-path dir "foo"))
    (fs.create-dirs subdir)
    (make-file subdir "bar.fnl" "(+ 1 2)")
    (local target {:kind :unit :name "module-test" :roots [dir] :module-roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1) (.. "expected 1 record, got " (# records)))
    (local r (. records 1))
    (assert r.module "record should have :module")
    (assert (= (type r.module) :string) "module should be a string")
    (assert (= r.module "foo.bar")
            (.. "expected module 'foo.bar', got '" (tostring r.module) "'")))))

(fn source-computes-module-name-for-init-fnl []
  "init.fnl files should produce a module name ending in .init"
  (with-temp-dir (fn [dir]
    (local subdir (fs.join-path dir "baz"))
    (fs.create-dirs subdir)
    (make-file subdir "init.fnl" "(+ 1 2)")
    (local target {:kind :unit :name "init-test" :roots [dir] :module-roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1) (.. "expected 1 record, got " (# records)))
    (local r (. records 1))
    (assert r.module "record should have :module")
    (assert (= r.module "baz.init")
            (.. "expected module 'baz.init', got '" (tostring r.module) "'")))))

(fn source-first-matching-root-wins-for-overlap []
  "Overlapping module roots: [root, root/foo] with file root/foo/bar.fnl
  should yield module 'foo.bar' (first match), NOT 'bar' (second overwrite)."
  (with-temp-dir (fn [dir]
    (local subdir (fs.join-path dir "foo"))
    (fs.create-dirs subdir)
    (make-file subdir "bar.fnl" "(+ 1 2)")
    ;; Overlapping roots: dir and dir/foo both match
    (local target {:kind :unit :name "overlap-test"
                    :roots [dir] :module-roots [dir subdir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1) (.. "expected 1 record, got " (# records)))
    (local r (. records 1))
    (assert r.module "record should have :module")
    (assert (= r.module "foo.bar")
            (.. "expected first-match module 'foo.bar', got '" (tostring r.module) "'")))))

;; --- Relative path computation tests (R1-1 path portability) ---

(fn source-computes-relative-path-from-module-root []
  "File records should include a portable :relative-path under the module root."
  (with-temp-dir (fn [dir]
    (local subdir (fs.join-path dir "nested"))
    (fs.create-dirs subdir)
    (make-file subdir "deep.fnl" "(+ 1 2)")
    (local target {:kind :unit :name "relpath-test" :roots [dir] :module-roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1) (.. "expected 1 record, got " (# records)))
    (local r (. records 1))
    (assert r.relative-path "record should have :relative-path")
    (assert (= (type r.relative-path) :string) "relative-path should be a string")
    (assert (= r.relative-path "nested/deep.fnl")
            (.. "expected 'nested/deep.fnl', got '" (tostring r.relative-path) "'")))))

(fn source-relative-path-falls-back-to-absolute []
  "When no module root matches, :relative-path should be the absolute path."
  (with-temp-dir (fn [dir]
    (make-file dir "orphan.fnl" "(+ 1 2)")
    (local target {:kind :unit :name "orphan-test" :roots [dir] :module-roots []})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1) (.. "expected 1 record, got " (# records)))
    (local r (. records 1))
    (assert r.relative-path "record should have :relative-path even with no module root")
    ;; With empty module-roots, relative-path should equal path
    (assert (= r.relative-path r.path)
            (.. "expected relative-path to equal path when no module root matches, got "
                (tostring r.relative-path) " vs " (tostring r.path))))))

(fn source-relative-path-uses-forward-slashes []
  "Relative paths produced by source discovery must always use forward slashes,
  regardless of the platform's native path separator."
  (with-temp-dir (fn [dir]
    (local subdir (fs.join-path dir "nested"))
    (fs.create-dirs subdir)
    (make-file subdir "deep.fnl" "(+ 1 2)")
    (local target {:kind :unit :name "slash-test" :roots [dir] :module-roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1) (.. "expected 1 record, got " (# records)))
    (local r (. records 1))
    (assert (not (string.find r.relative-path "\\" 1 true))
            (.. "relative-path must not contain backslash, got: " (tostring r.relative-path)))
    (assert (not (string.find r.module "\\" 1 true))
            (.. "module must not contain backslash, got: " (tostring r.module))))))

(fn source-module-uses-dots-not-slashes []
  "Module names derived from file paths must use dots as separators
  and must never contain forward slashes or backslashes."
  (with-temp-dir (fn [dir]
    (local subdir (fs.join-path dir "core"))
    (fs.create-dirs subdir)
    (make-file subdir "utils.fnl" "(+ 1 2)")
    (local target {:kind :unit :name "module-slash-test" :roots [dir] :module-roots [dir]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1) (.. "expected 1 record, got " (# records)))
    (local r (. records 1))
    (assert (= r.module "core.utils")
            (.. "expected module 'core.utils', got '" (tostring r.module) "'"))
    (assert (not (string.find r.module "/" 1 true))
            (.. "module must not contain forward slash, got: " (tostring r.module)))
    (assert (not (string.find r.module "\\" 1 true))
            (.. "module must not contain backslash, got: " (tostring r.module))))))

;; --- Windows-separator regression tests (R1-2) ---

(fn source-normalize-path-separators-handles-backslashes []
  "The normalize-path-separators helper must map \\\\ to / in any path string."
  (local Source (require :constraints.source))
  (local nps Source._normalize-path-separators)
  (assert nps "helper should be exported")
  (assert (= (nps "C:\\tmp\\space\\unit\\foo\\bar.fnl")
             "C:/tmp/space/unit/foo/bar.fnl")
          "backslash path should be normalized to forward slashes")
  (assert (= (nps "C:\\tmp\\space\\unit")
             "C:/tmp/space/unit")
          "backslash root should be normalized")
  (assert (= (nps "already/forward/slashes.fnl")
             "already/forward/slashes.fnl")
          "forward-slash path should be unchanged")
  (assert (= (nps nil) "")
          "nil should produce empty string")
  (assert (= (nps "") "")
          "empty string should stay empty"))

(fn source-path-under-root-accepts-backslash []
  "path-under-root? must correctly compare backslash paths against backslash roots
  after normalization."
  (local Source (require :constraints.source))
  (local pur? Source._path-under-root?)
  (assert pur? "helper should be exported")
  ;; File under root with backslashes on both sides.
  (assert (pur? "C:\\tmp\\space\\unit\\foo\\bar.fnl"
                "C:\\tmp\\space\\unit")
          "file under backslash root should match")
  ;; File equals root.
  (assert (pur? "C:\\tmp\\space\\unit\\bar.fnl"
                "C:\\tmp\\space\\unit\\bar.fnl")
          "file equal to backslash root should match")
  ;; Different root — should not match.
  (assert (not (pur? "C:\\tmp\\space\\unit\\foo\\bar.fnl"
                     "C:\\tmp\\other"))
          "file under different backslash root should not match")
  ;; File not a direct child (no trailing separator boundary).
  (assert (not (pur? "C:\\tmp\\space\\unit-other\\bar.fnl"
                     "C:\\tmp\\space\\unit"))
          "file with similar prefix should not match")
  ;; Mixed separators: file with /, root with \\.
  (assert (pur? "C:/tmp/space/unit/foo/bar.fnl"
                "C:\\tmp\\space\\unit")
          "forward-slash file should match backslash root after normalization")
  ;; Case-insensitive match.
  (assert (pur? "c:\\TMP\\Space\\Unit\\foo\\bar.fnl"
                "C:\\tmp\\SPACE\\unit")
          "case-insensitive backslash match should work"))

;; --- Non-Fennel explicit file tests (R1-2) ---

(fn source-files-target-rejects-non-fennel-paths []
  "Explicit --file paths that are not .fnl should be excluded from discovery."
  (with-temp-dir (fn [dir]
    (local txt-path (make-file dir "readme.txt" "hello"))
    (local target {:kind :files
                    :name "file-filter"
                    :files [txt-path]
                    :roots []})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 0)
            (.. "expected 0 records for non-fnl explicit file, got " (# records))))))

(fn source-files-target-includes-fennel-and-excludes-others []
  "Mixed explicit files: .fnl should be included, non-.fnl excluded."
  (with-temp-dir (fn [dir]
    (local fnl-path (make-file dir "code.fnl" "(+ 1 2)"))
    (local txt-path (make-file dir "notes.txt" "text"))
    (local target {:kind :files
                    :name "mixed-files"
                    :files [fnl-path txt-path]
                    :roots []})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1)
            (.. "expected 1 fennel record, got " (# records)))
    (local r (. records 1))
    (assert (= r.path (fs.absolute fnl-path)) "only .fnl file should be discovered"))))

;; --- Missing/unreadable root tests (R1-3) ---

(fn source-fails-loudly-on-nonexistent-root []
  "A target root that does not exist should cause discovery to fail, not silently skip."
  (with-temp-dir (fn [dir]
    (local missing-root (fs.join-path dir "does-not-exist"))
    (local target {:kind :unit :name "broken" :roots [missing-root]})
    (local Source (require :constraints.source))
    (local (ok err) (pcall #(Source.discover target)))
    (assert (not ok)
            "discover should fail for missing root, not silently skip")
    (assert (string.find (tostring err) missing-root 1 true)
            (.. "error should mention the missing root path, got: " (tostring err))))))

;; --- Noncanonical module root regression test (R1-4) ---

(fn source-module-root-is-canonicalized []
  "When a module root is a noncanonical path (e.g. with .. segments),
  it should be canonicalized through fs.absolute before computing module names
  and relative paths, so that it matches discovered file paths which are always
  absolute.  Regression test for root-prefix matching failure on Windows/Wine."
  (with-temp-dir (fn [dir]
    (local sub (fs.join-path dir "mod"))
    (fs.create-dirs sub)
    (make-file sub "helper.fnl" "(+ 1 2)")
    ;; Build a noncanonical root by inserting ../ to create a path that
    ;; refers to the same directory but differs lexically from its
    ;; fs.absolute form.
    (local noncanonical-root (dir:gsub "/([^/]+)/([^/]+)$" "/%1/../%1/%2"))
    (local target {:kind :unit
                   :name "canonicalize-test"
                   :roots [dir]
                   :module-roots [noncanonical-root]})
    (local Source (require :constraints.source))
    (local records (Source.discover target))
    (assert (= (# records) 1) (.. "expected 1 record, got " (# records)))
    (local r (. records 1))
    (assert (= r.module "mod.helper")
            (.. "expected module 'mod.helper', got '" (tostring r.module) "'"))
    (assert (= r.relative-path "mod/helper.fnl")
            (.. "expected relative-path 'mod/helper.fnl', got '"
                (tostring r.relative-path) "'")))))

;; --- Repeated --file tests ---

(fn targets-resolve-repeated-file []
  (local Targets (require :constraints.targets))
  (local result (Targets.resolve ["--target" "files"
                                   "--file" "/tmp/a.fnl"
                                   "--file" "/tmp/b.fnl"] {}))
  (assert (= result.kind :files) "kind should be :files")
  (assert (= (# result.files) 2) (.. "expected 2 files, got " (# result.files))))

(fn assert-record-parity [expected actual]
  (assert (= (# expected) (# actual)) "observer changed discovery count")
  (each [i record (ipairs expected)]
    (local observed (. actual i))
    (each [_ key (ipairs [:target :path :module :relative-path :source])]
      (assert (= (. record key) (. observed key)) (.. "observer changed " key)))
    (assert (= (record.root:type) (observed.root:type)))
    (assert (= (record.root:sexpr) (observed.root:sexpr)))))

(fn assert-source-event-schema [events]
  (local allowed {:edge true :phase true :subphase true :file true :index true :count true})
  (each [_ event (ipairs events)]
    (assert (= event.phase :discover))
    (each [key value (pairs event)]
      (assert (. allowed key))
      (assert (or (= (type value) :string) (= (type value) :number))))))

(fn source-observer-preserves-discovery-and-order []
  (fn check [dir]
    (local z (make-file dir "z.fnl" "(print :private-source)"))
    (make-file dir "a.fnl" "(+ 1 2)")
    (local Source (require :constraints.source))
    (local target {:kind :files :roots [dir] :files [z] :module-roots [dir]})
    (local expected (Source.discover target))
    (local events [])
    (fn record-event [event] (table.insert events event))
    (local actual (Source.discover target record-event))
    (assert-record-parity expected (Source.discover target nil))
    (assert-record-parity expected actual)
    (assert (= (# events) 10) "expected scan and two read/parse pairs")
    (assert (= (. events 1 :edge) :begin))
    (assert (= (. events 1 :subphase) :scan))
    (assert (= (. events 2 :edge) :end))
    (assert (= (. events 2 :count) 2))
    (each [i file (ipairs ["a.fnl" "z.fnl"])]
      (each [j subphase (ipairs [:read :parse])]
        (local offset (+ 2 (* (- i 1) 4) (* (- j 1) 2)))
        (local begin (. events (+ offset 1)))
        (local end (. events (+ offset 2)))
        (assert (= begin.edge :begin))
        (assert (= end.edge :end))
        (assert (= begin.subphase subphase end.subphase))
        (assert (= begin.file file end.file))
        (assert (= begin.index i end.index))))
    (assert-source-event-schema events))
  (with-temp-dir check))

(fn source-observer-hides-absolute-fallback []
  (fn check [dir]
    (local path (make-file dir "private.fnl" "(print :private-source)"))
    (local Source (require :constraints.source))
    (local events [])
    (fn record-event [event] (table.insert events event))
    (local records (Source.discover {:kind :files :files [path] :module-roots []} record-event))
    (assert (= (. records 1 :relative-path) (fs.absolute path)))
    (assert (= (# events) 6) "expected scan/read/parse events")
    (each [i event (ipairs events)]
      (assert (= event.file nil) "absolute fallback must not escape")
      (when (> i 2) (assert (= event.index 1)))))
  (with-temp-dir check))

(fn source-observer-leaves-failed-operation-open [operation subphase]
  (fn check [dir]
    (local path (make-file dir "error.fnl" "(+ 1 2)"))
    (local Source (require :constraints.source))
    (local ts (require :tree-sitter))
    (local owner (if (= operation :read-file) fs ts))
    (local previous (. owner operation))
    (local sentinel {})
    (local events [])
    (fn fail [...] (error sentinel 0))
    (fn record-event [event] (table.insert events event))
    (tset owner operation fail)
    (local (ok err) (pcall Source.discover {:kind :files :files [path] :module-roots [dir]}
                           record-event))
    (tset owner operation previous)
    (assert (not ok))
    (assert (= err sentinel) "workload error identity must be preserved")
    (local last (. events (# events)))
    (assert last "failure must retain its begin event")
    (assert (= last.edge :begin))
    (assert (= last.subphase subphase)))
  (with-temp-dir check))

(fn source-observer-scan-failure-stays-open []
  (fn check [dir]
    (local Source (require :constraints.source))
    (local target {:roots [(fs.join-path dir "missing")]})
    (local events [])
    (fn record-event [event] (table.insert events event))
    (local (plain-ok plain-err) (pcall Source.discover target))
    (local (ok err) (pcall Source.discover target record-event))
    (assert (not plain-ok))
    (assert (not ok))
    (assert (= err plain-err) "scan errors must be unchanged")
    (assert (= (# events) 1) "failed scan must not emit an end")
    (assert (= (. events 1 :edge) :begin))
    (assert (= (. events 1 :subphase) :scan)))
  (with-temp-dir check))

(table.insert tests {:name "source observer preserves discovery and order"
                     :fn source-observer-preserves-discovery-and-order})
(table.insert tests {:name "source observer hides absolute fallback"
                     :fn source-observer-hides-absolute-fallback})
(table.insert tests {:name "source observer retains unmatched read begin on error"
                     :fn #(source-observer-leaves-failed-operation-open :read-file :read)})
(table.insert tests {:name "source observer retains unmatched parse begin on error"
                     :fn #(source-observer-leaves-failed-operation-open :parse :parse)})
(table.insert tests {:name "source observer retains unmatched scan begin on error"
                     :fn source-observer-scan-failure-stays-open})

;; Register all tests
(table.insert tests {:name "targets resolve defaults to repo"
                     :fn targets-resolve-defaults-to-repo})
(table.insert tests {:name "targets resolve unit with --root"
                     :fn targets-resolve-unit-with-root})
(table.insert tests {:name "targets resolve app with --root"
                     :fn targets-resolve-app-with-root})
(table.insert tests {:name "targets resolve files with --file"
                     :fn targets-resolve-files-with-file})
(table.insert tests {:name "targets resolve refuses unsupported target"
                     :fn targets-resolve-refuses-unsupported-target})
(table.insert tests {:name "targets resolve refuses missing target value"
                     :fn targets-resolve-refuses-missing-target-value})
(table.insert tests {:name "targets resolve refuses missing root for unit"
                      :fn targets-resolve-refuses-missing-root-for-unit})
(table.insert tests {:name "targets resolve refuses unknown flag"
                      :fn targets-resolve-refuses-unknown-flag})
(table.insert tests {:name "targets resolve refuses stray positional"
                      :fn targets-resolve-refuses-stray-positional})
(table.insert tests {:name "source discovers fnl files recursively"
                     :fn source-discovers-fnl-files-recursively})
(table.insert tests {:name "source excludes non-fennel files"
                     :fn source-excludes-non-fennel-files})
(table.insert tests {:name "source parses files with tree-sitter"
                     :fn source-parses-files-with-tree-sitter})
(table.insert tests {:name "source files outside assets/lua parse and retain target"
                     :fn source-files-outside-assets-lua-parse-and-retain-target})
(table.insert tests {:name "source node-text returns substring"
                     :fn source-node-text-returns-substring})
(table.insert tests {:name "source node-location returns line and column"
                     :fn source-node-location-returns-line-and-column})
(table.insert tests {:name "source walk visits all nodes depth-first"
                     :fn source-walk-visits-all-nodes-depth-first})
(table.insert tests {:name "source computes module name from root"
                     :fn source-computes-module-name-from-root})
(table.insert tests {:name "source computes module name for init.fnl"
                     :fn source-computes-module-name-for-init-fnl})
(table.insert tests {:name "source first matching root wins for overlap"
                      :fn source-first-matching-root-wins-for-overlap})
(table.insert tests {:name "source computes relative path from module root (R1-1)"
                      :fn source-computes-relative-path-from-module-root})
(table.insert tests {:name "source relative path falls back to absolute (R1-1)"
                      :fn source-relative-path-falls-back-to-absolute})
(table.insert tests {:name "source relative path uses forward slashes"
                      :fn source-relative-path-uses-forward-slashes})
(table.insert tests {:name "source module uses dots not slashes"
                      :fn source-module-uses-dots-not-slashes})
(table.insert tests {:name "source normalize-path-separators handles backslashes (R1-2)"
                      :fn source-normalize-path-separators-handles-backslashes})
(table.insert tests {:name "source path-under-root accepts backslash (R1-2)"
                      :fn source-path-under-root-accepts-backslash})
(table.insert tests {:name "source canonicalizes noncanonical module root (R1-4)"
                     :fn source-module-root-is-canonicalized})
(table.insert tests {:name "source files target rejects non-fennel paths"
                     :fn source-files-target-rejects-non-fennel-paths})
(table.insert tests {:name "source files target includes fennel and excludes others"
                     :fn source-files-target-includes-fennel-and-excludes-others})
(table.insert tests {:name "source fails loudly on nonexistent root"
                     :fn source-fails-loudly-on-nonexistent-root})
(table.insert tests {:name "targets resolve repeated --root"
                     :fn targets-resolve-repeated-root})
(table.insert tests {:name "targets resolve repeated --file"
                     :fn targets-resolve-repeated-file})

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "constraints-source"
                        :tests tests})))

{:name "constraints-source"
 :tests tests
 :main main}
