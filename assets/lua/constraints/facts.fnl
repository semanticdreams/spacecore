;; Static fact extraction for Fennel constraints.
;; Walks tree-sitter AST nodes to collect requires, definitions, exports,
;; calls, accesses, mutations, and metrics from Fennel source files.

(local M {})

;; Form node types that introduce a new nesting scope.
(local form-types
  {:local_form true
   :fn_form true
   :set_form true
   :global_form true
   :list true
   :table true
   :table_metadata true
   :sequential_table true})

(fn node-text [source node]
  "Extract the substring of source covered by a node."
  (source:sub (+ (node:start-byte) 1) (node:end-byte)))

(fn node-line-col [node]
  "Return {:line :column} for the start of a node (0-indexed to 1-indexed)."
  (let [pt (node:start-point)]
    {:line (+ pt.row 1)
     :column (+ pt.column 1)}))

(fn non-delimiter-children [node]
  "Return all children that are not delimiter tokens."
  (local result [])
  (for [i 0 (- (node:child-count) 1)]
    (let [c (node:child i)
          ct (c:type)]
      (when (not (or (= ct "(") (= ct ")") (= ct "{") (= ct "}")
                      (= ct "[") (= ct "]") (= ct ".") (= ct ":")
                      (= ct "\"") (= ct "'")))
        (table.insert result c))))
  result)

(fn split-colon-symbol [text]
  "Split a colon-style symbol like 'obj:method' into [receiver method]."
  (let [parts []]
    (each [segment (text:gmatch "[^:]+")]
      (table.insert parts segment))
    parts))

(fn split-dotted-symbol [text]
  "Split a dotted symbol like 'world.state.scene.panels' into path segments."
  (let [parts []]
    (each [segment (text:gmatch "[^%.]+")]
      (table.insert parts segment))
    parts))

(fn extract-module-name-from-string-node [source node]
  "Extract the module name from a string node (handles :keyword and \"string\")."
  (let [text (node-text source node)
        ntype (node:type)]
    (if (not= ntype "string")
        text
        (text:match "^:")
        (text:sub 2)
        (text:match "^\"")
        (text:gsub "^\"(.*)\"$" "%1")
        text)))

(fn is-table-node? [node-type]
  "Check if a node type is a table-like container."
  (or (= node-type :table)
      (= node-type :table_metadata)
      (= node-type :sequential_table)))

(fn table-pair-type [node-type]
  "Return the pair child type for table nodes."
  (if (= node-type :table) :table_pair
      (= node-type :table_metadata) :table_metadata_pair
      nil))

(fn count-table-elements [node]
  "Count key-value pairs or sequential elements in a table node."
  (let [ntype (node:type)]
    (if (= ntype :sequential_table)
        (length (non-delimiter-children node))
        (do
          (local pair-type (table-pair-type ntype))
          (if pair-type
              (do
                (var count 0)
                (for [i 0 (- (node:child-count) 1)]
                  (let [c (node:child i)]
                    (when (= (c:type) pair-type)
                      (set count (+ count 1)))))
                count)
              0)))))

(fn fn-name-from-node [source node]
  "Extract the function name from an fn_form node, or nil if anonymous.
  In the AST: fn_form children are: '(' 'symbol(fn)' [symbol(name)] args... ')'
  A named fn has a symbol as the 3rd child (index 2): '( fn name args... )'
  An anonymous fn has no name symbol: '( fn args... )'"
  (let [ndc (non-delimiter-children node)]
    (if (>= (length ndc) 2)
        (let [c2 (. ndc 2)]
          (if (= (c2:type) "symbol")
              (let [text (node-text source c2)]
                (if (not= text "fn") text nil))
              nil))
        nil)))

(fn enclosing-fn-name [fn-stack]
  "Return the name of the innermost function on fn-stack, or nil."
  (if (> (length fn-stack) 0)
      (. (. fn-stack (length fn-stack)) :name)
      nil))

(fn extract-file-facts [record]
  "Extract all static facts from a single file record."
  (let [source record.source
        root record.root
        facts {:target record.target
               :path record.path
               :module record.module
               :relative-path (or record.relative-path record.path)
               :requires []
               :definitions []
               :exports []
               :calls []
               :accesses []
               :mutations []
               :metrics {:module-lines 0
                         :max-nesting-depth 0
                         :max-anonymous-callback-depth 0
                         :max-table-literal-size 0
                         :functions []}}]

    ;; State during walk
    (var depth 0)
    (var fn-stack [])
    (var max-depth 0)
    (var max-anon-depth 0)

    ;; Compute module-lines from source line count
    (var line-count 1)
    (each [_ _ (source:gmatch "\n")]
      (set line-count (+ line-count 1)))
    (set facts.metrics.module-lines line-count)

    (fn visit [node]
      (let [node-type (node:type)
            is-form (. form-types node-type)]
        (when is-form
          (set depth (+ depth 1))
          (when (> depth max-depth)
            (set max-depth depth))
          ;; Update per-frame max depth for all active function frames
          (each [_ frame (ipairs fn-stack)]
            (when (> depth frame.frame-max-depth)
              (set frame.frame-max-depth depth))))

        ;; --- local_form ---
        (when (= node-type :local_form)
          (let [loc (node-line-col node)
                form (node-text source node)]
            ;; local_form children: ( symbol(local) binding_pair(symbol_binding value) )
            ;; Extract the binding name from symbol_binding inside binding_pair
            (var local-name nil)
            (var value-node nil)
            (for [i 0 (- (node:child-count) 1)]
              (let [c (node:child i)]
                (if (= (c:type) "binding_pair")
                    (for [j 0 (- (c:child-count) 1)]
                      (let [bp-c (c:child j)]
                        (if (= (bp-c:type) "symbol_binding")
                            (set local-name (node-text source bp-c))
                            (or (= (bp-c:type) "list")
                                (= (bp-c:type) "table")
                                (= (bp-c:type) "table_metadata")
                                (= (bp-c:type) "sequential_table")
                                (= (bp-c:type) "fn_form"))
                            (set value-node bp-c))))
                    (= (c:type) "symbol_binding")
                    (set local-name (node-text source c)))))
            (when local-name
              (table.insert facts.definitions
                {:kind :local
                 :name local-name
                 :top-level? (= depth 1)
                 :line loc.line
                 :column loc.column
                 :start-byte (node:start-byte)
                 :end-byte (node:end-byte)
                 :form form
                 :enclosing-fn (enclosing-fn-name fn-stack)})
              ;; If value is a require form, extract module name
              (when (and value-node (= (value-node:type) "list"))
                (let [vndc (non-delimiter-children value-node)]
                  (when (and (>= (length vndc) 2)
                             (= (node-text source (. vndc 1)) "require"))
                    (let [mod-node (. vndc 2)
                          mod-name (extract-module-name-from-string-node source mod-node)
                          mod-loc (node-line-col value-node)]
                      (table.insert facts.requires
                        {:module mod-name
                         :line mod-loc.line
                         :column mod-loc.column
                         :form (node-text source value-node)}))))))))

        ;; --- fn_form ---
        (when (= node-type :fn_form)
          (let [fn-name (fn-name-from-node source node)
                loc (node-line-col node)
                form (node-text source node)
                anonymous? (not fn-name)]
            (table.insert facts.definitions
              {:kind :fn
               :name (or fn-name "<anonymous>")
               :top-level? (= (length fn-stack) 0)
               :line loc.line
               :column loc.column
               :start-byte (node:start-byte)
               :end-byte (node:end-byte)
               :form form
               :enclosing-fn (enclosing-fn-name fn-stack)})
            (table.insert fn-stack
              {:name (or fn-name "<anonymous>")
               :start-depth depth
               :start-line loc.line
               :start-column loc.column
               :anonymous? anonymous?
               :frame-max-depth depth})
            (when anonymous?
              (let [anon-d (- depth 1)]
                (when (> anon-d max-anon-depth)
                  (set max-anon-depth anon-d))))))

        ;; --- global_form ---
        (when (= node-type :global_form)
          (let [loc (node-line-col node)
                form (node-text source node)]
            (for [i 0 (- (node:child-count) 1)]
              (let [c (node:child i)]
                (when (= (c:type) "binding_pair")
                  (for [j 0 (- (c:child-count) 1)]
                    (let [bp-c (c:child j)]
                      (when (= (bp-c:type) "symbol_binding")
                        (let [name-text (node-text source bp-c)]
                          (table.insert facts.definitions
                            {:kind :global
                             :name name-text
                             :top-level? (= depth 1)
                             :line loc.line
                             :column loc.column
                             :form form}))))))))))

        ;; --- set_form (mutation) ---
        (when (= node-type :set_form)
          (let [loc (node-line-col node)
                form (node-text source node)]
            (var path nil)
            (for [i 0 (- (node:child-count) 1)]
              (when (not path)
                (let [c (node:child i)]
                  (if (= (c:type) "binding_pair")
                      (for [j 0 (- (c:child-count) 1)]
                        (let [bp-c (c:child j)]
                          (when (and (not path) (= (bp-c:type) "multi_symbol"))
                            (let [c-text (node-text source bp-c)]
                              (set path (split-dotted-symbol c-text))))))
                      (= (c:type) "multi_symbol")
                      (let [c-text (node-text source c)]
                        (set path (split-dotted-symbol c-text)))))))
            (when path
              (table.insert facts.mutations
                {:op :set
                 :path path
                 :line loc.line
                 :column loc.column
                 :form form
                 :enclosing-fn (enclosing-fn-name fn-stack)}))))

        ;; --- list (calls, require, tset) ---
        (when (= node-type :list)
          (let [ndc (non-delimiter-children node)
                loc (node-line-col node)
                form (node-text source node)]
            (when (>= (length ndc) 1)
              (let [head (. ndc 1)
                    head-type (head:type)
                    head-text (node-text source head)]
                (if (= head-text "require")
                    (when (>= (length ndc) 2)
                      (let [mod-node (. ndc 2)
                            mod-name (extract-module-name-from-string-node source mod-node)]
                        (table.insert facts.requires
                          {:module mod-name
                           :line loc.line
                           :column loc.column
                           :form form})))
                    (= head-text "tset")
                    (let [tset-path (if (>= (length ndc) 3)
                                        (let [table-node (. ndc 2)
                                              table-name (node-text source table-node)
                                              key-node (. ndc 3)
                                              key-text (extract-module-name-from-string-node source key-node)]
                                          (if (table-name:match "%.")
                                              (do
                                                (local p (split-dotted-symbol table-name))
                                                (table.insert p key-text)
                                                p)
                                              [table-name key-text]))
                                        [])]
                       (table.insert facts.mutations
                         {:op :tset
                          :path tset-path
                          :line loc.line
                          :column loc.column
                          :form form
                          :enclosing-fn (enclosing-fn-name fn-stack)}))
                    ;; regular call
                    (let [callee head-text
                          receiver (if (= head-type "multi_symbol")
                                       (let [parts (split-dotted-symbol head-text)]
                                         (. parts 1))
                                       (= head-type "multi_symbol_method")
                                       (let [parts (split-colon-symbol head-text)]
                                         (. parts 1))
                                       nil)
                          method (if (= head-type "multi_symbol_method")
                                     (let [parts (split-colon-symbol head-text)]
                                       (if (>= (length parts) 2)
                                           (. parts (length parts))
                                           nil))
                                     (and (= head-type "multi_symbol")
                                          (>= (length (split-dotted-symbol head-text)) 2))
                                     (let [parts (split-dotted-symbol head-text)]
                                       (. parts (length parts)))
                                     nil)]
                       (table.insert facts.calls
                         {:callee callee
                          :receiver receiver
                          :method method
                          :line loc.line
                          :column loc.column
                          :form form
                          :enclosing-fn (enclosing-fn-name fn-stack)})))))))

        ;; --- multi_symbol (access path) ---
        (when (= node-type :multi_symbol)
          (let [c-text (node-text source node)
                loc (node-line-col node)
                path (split-dotted-symbol c-text)]
            (when (>= (length path) 2)
              (table.insert facts.accesses
                {:path path
                 :text c-text
                 :line loc.line
                 :column loc.column
                 :form c-text}))))

        ;; --- table/table_metadata literal (exports and size) ---
        (when (is-table-node? node-type)
          (let [table-size (count-table-elements node)
                loc (node-line-col node)]
            (when (> table-size facts.metrics.max-table-literal-size)
              (set facts.metrics.max-table-literal-size table-size))
            ;; Export keys from top-level table literals only.
            ;; These are module-return tables (the dominant Fennel export pattern).
            ;; Nested tables (e.g., (local config {:key val})) are data, not exports.
            (when (= depth 1)
              (let [pair-type (table-pair-type node-type)]
                (when pair-type
                  (for [i 0 (- (node:child-count) 1)]
                    (let [c (node:child i)]
                      (when (= (c:type) pair-type)
                        (for [j 0 (- (c:child-count) 1)]
                          (let [tp-c (c:child j)]
                            (when (= (tp-c:type) "string")
                              (let [key-text (extract-module-name-from-string-node source tp-c)
                                    key-loc (node-line-col c)]
                                (table.insert facts.exports
                                  {:key key-text
                                   :line key-loc.line
                                   :column key-loc.column
                                   :form (node-text source c)})))))))))))))

        ;; Recurse into children
        (for [i 0 (- (node:child-count) 1)]
          (visit (node:child i)))

        ;; Leave form scope
        (when is-form
          (when (= node-type :fn_form)
            (when (> (length fn-stack) 0)
              (let [fn-info (table.remove fn-stack)
                    ep (node:end-point)
                    end-line (+ ep.row 1)
                    fn-length (- end-line fn-info.start-line)]
                (table.insert facts.metrics.functions
                  {:name fn-info.name
                   :line fn-info.start-line
                   :column fn-info.start-column
                   :length (math.max 1 fn-length)
                   :max-nesting-depth (- fn-info.frame-max-depth fn-info.start-depth)}))))
          (set depth (- depth 1)))))

    (visit root)

    ;; Finalize metrics
    (set facts.metrics.max-nesting-depth (math.max 0 (- max-depth 1)))
    (set facts.metrics.max-anonymous-callback-depth max-anon-depth)

    facts))

;; ERROR recovery: when tree-sitter produces an ERROR root (Fennel
;; grammar limitation, e.g., multi-segment fn names like ButtonWidget),
;; scan source for top-level named fn forms not captured by the walk
;; and add synthetic definitions with byte spans. Then update child def
;; enclosing-fn via byte containment — scoped, no leak.
(fn find-matching-paren [s start-byte]
  "Find the 1-indexed position of the matching close paren for the
   open paren at start-byte (also 1-indexed). Returns nil if not found."
  (var depth 0)
  (var pos start-byte)
  (var found nil)
  (while (and (<= pos (length s)) (= found nil))
    (local c (s:sub pos pos))
    (if (= c "(")
        (set depth (+ depth 1))
        (= c ")")
        (do (set depth (- depth 1))
            (when (= depth 0)
              (set found pos))))
    (set pos (+ pos 1)))
  found)

(fn line-col-at-byte [source target-byte]
  "Return {:line :column} (1-indexed) for a 1-indexed byte position."
  (var line 1)
  (var col 1)
  (for [i 1 (- target-byte 1)]
    (if (= (source:sub i i) "\n")
        (do (set line (+ line 1)) (set col 1))
        (set col (+ col 1))))
  {:line line :column col})

(fn try-recover-synthetic-parent [source fn-start definitions]
  "Given a byte position where '(fn ' starts, attempt to recover a named
  fn form as a synthetic parent. Returns the parent-def table if at least
  one orphan child is byte-contained, or nil if the fn is already known
  or has no orphan children."
  (local after-fn (+ fn-start 4))
  (local name-start after-fn)
  (local name-end (source:find "[%s%(%)%[%]]" name-start))
  (when name-end
    (local fn-name (source:sub name-start (- name-end 1)))
    (when (and (> (length fn-name) 0)
               (not= fn-name "fn")
               (not= fn-name "lambda"))
      (local close-paren (find-matching-paren source fn-start))
      (when close-paren
        (var already false)
        (each [_ d (ipairs definitions)]
          (when (= d.name fn-name) (set already true)))
        (when (not already)
          (local parent-start (- fn-start 1))
          (var has-orphan-child false)
          (each [_ child (ipairs definitions)]
            (when (and (not has-orphan-child)
                       (= child.enclosing-fn nil)
                       child.start-byte child.end-byte
                       (>= child.start-byte parent-start)
                       (<= child.end-byte close-paren))
              (set has-orphan-child true)))
          (when has-orphan-child
            (local lc (line-col-at-byte source fn-start))
            (local end-lc (line-col-at-byte source close-paren))
            {:kind :fn
             :name fn-name
             :top-level? true
             :line lc.line
             :column lc.column
             :start-byte parent-start
             :end-byte close-paren
             :end-line end-lc.line
             :form (source:sub fn-start close-paren)
             :enclosing-fn nil}))))))

(fn recover-error-root [source root definitions calls]
  "When root is ERROR, scan source for top-level named fn forms and
  recover synthetic parents for orphan children. Returns the list of
  synthetic parents (NOT inserted into definitions). Also updates child
  enclosing-fn and call enclosing-fn in-place."
  (local synthetic-parents [])
  (when (= (root:type) "ERROR")
    (var scan-pos 1)
    (local source-len (length source))
    (while (<= scan-pos source-len)
      (local fn-start (source:find "(fn " scan-pos true))
      (if (not fn-start)
          (set scan-pos (+ source-len 1))
          (do
            (local parent (try-recover-synthetic-parent source fn-start definitions))
            (local name-end (source:find "[%s%(%)%[%]]" (+ fn-start 4)))
            (when parent
              (table.insert synthetic-parents parent))
            (set scan-pos (if name-end name-end (+ fn-start 4))))))
    (each [_ child (ipairs definitions)]
      (when (and (= child.enclosing-fn nil)
                 child.start-byte child.end-byte)
        (each [_ parent (ipairs synthetic-parents)]
          (when (and (not= parent.name child.name)
                     (>= child.start-byte parent.start-byte)
                     (<= child.end-byte parent.end-byte))
            (tset child :enclosing-fn parent.name)
            (tset child :top-level? false)))))
    (each [_ call (ipairs calls)]
      (when (and (= call.enclosing-fn nil) call.line)
        (each [_ parent (ipairs synthetic-parents)]
          (when (and parent.line parent.end-line
                     (>= call.line parent.line)
                     (<= call.line parent.end-line))
            (tset call :enclosing-fn parent.name))))))
  synthetic-parents)

(fn escape-lua-pattern [s]
  "Escape Lua pattern magic characters in s for use in string.find patterns."
  (s:gsub "([%^%$%(%)%%%.%[%]%*%+%-%?])" "%%%1"))

(fn span-for-fn-def [source d]
  "Compute the real byte span of a fn definition from source text
   by finding its '(fn <name>' pattern and matching parens.
   Returns nil if the span cannot be determined."
  (local name-str (if (= d.name "<anonymous>") nil d.name))
  (when name-str
    (local escaped-name (escape-lua-pattern name-str))
    (local pattern (.. "%(fn " escaped-name "[%s%(%)%[%]]"))
    (local search-pos (if d.start-byte (math.max 1 d.start-byte) 1))
    (local init (math.max 1 (- search-pos 20)))
    (local match-pos (source:find pattern init))
    (when match-pos
      (local end-pos (find-matching-paren source match-pos))
      (when end-pos
        {:start-byte match-pos :end-byte end-pos}))))

(fn fix-enclosing-fn-by-span [source definitions recovered-parents]
  "Correct enclosing-fn for all function definitions using smallest
   containing function span. Uses source-text paren matching to compute
   accurate byte spans, since tree-sitter assigns wrong spans in ERROR trees."
  (local all-fns [])

  ;; Collect function spans: use source-text spans for parsed definitions,
  ;; and trust recovered-parent spans (they come from source-text matching).
  (each [_ d (ipairs definitions)]
    (when (= d.kind :fn)
      (local span (span-for-fn-def source d))
      (when span
        (table.insert all-fns {:name d.name
                               :start-byte span.start-byte
                               :end-byte span.end-byte}))))
  (each [_ rp (ipairs (if recovered-parents recovered-parents []))]
    (when (and rp.start-byte rp.end-byte)
      (table.insert all-fns {:name rp.name
                             :start-byte rp.start-byte
                             :end-byte rp.end-byte})))

  ;; For each child definition, find the smallest containing parent.
  ;; Use corrected source-text spans for the child when available;
  ;; fall back to tree-sitter spans only when source-text matching fails.
  (each [_ child (ipairs definitions)]
    (local child-span (span-for-fn-def source child))
    (local child-start (if child-span
                           child-span.start-byte
                           child.start-byte))
    (local child-end (if child-span
                         child-span.end-byte
                         child.end-byte))
    (when (and child-start child-end)
      (var best-parent nil)
      (var best-span nil)
      (each [_ parent (ipairs all-fns)]
        (when (and (not= parent.name child.name)
                   (>= child-start parent.start-byte)
                   (<= child-end parent.end-byte))
          (local span (- parent.end-byte parent.start-byte))
          (when (if (= best-parent nil) true (< span best-span) true false)
            (set best-parent parent)
            (set best-span span))))
      (if best-parent
          (do
            (tset child :enclosing-fn best-parent.name)
            (tset child :top-level? false))
          (do
            (tset child :enclosing-fn nil)
            (tset child :top-level? true))))))

(fn M.fix-enclosing-fn-by-span [source definitions recovered-parents]
  "Correct enclosing-fn for all function definitions using smallest
   containing function span. Uses source-text paren matching to compute
   accurate byte spans, since tree-sitter assigns wrong spans in ERROR trees.
   Exported for testing R1-2 corrected-child-span coverage."
  (fix-enclosing-fn-by-span source definitions recovered-parents))

(fn observe-file [observer edge subphase file index file-facts]
  (when observer
    (observer {:edge edge :phase :facts :subphase subphase :file file :index index
               :definitions (when file-facts (# file-facts.definitions))
               :calls (when file-facts (# file-facts.calls))})))

(fn M.extract [file-records observer]
  "Extract static facts from a list of file records.
   Optional observer receives scalar facts extract/recover/span edges.
  Returns a fact-db:
  {:files [file-facts ...]
   :by-file {path file-facts}}"
  (local by-file {})
  (local files [])
  (each [index record (ipairs file-records)]
       ;; Only the existing relative projection may be observed; never path.
       (local file (when (and observer (= (type record.relative-path) :string))
                     record.relative-path))
       (local safe-file (and file (not= file "")
                             (not (file:find "^/"))
                             (not (file:find "[%c:\\]"))
                             (not (file:find "//" 1 true))
                             (not (file:find "/$"))
                             (not (string.find (.. "/" file "/") "/%.%.?/"))))
       (local event-file (if safe-file file nil))
       (observe-file observer :begin :extract event-file index nil)
       (local file-facts (extract-file-facts record))
       (observe-file observer :end :extract event-file index file-facts)
       (observe-file observer :begin :recover event-file index nil)
       (local recovered (recover-error-root record.source record.root
                                            file-facts.definitions
                                            file-facts.calls))
       (observe-file observer :end :recover event-file index file-facts)
      (when (> (length recovered) 0)
        (tset file-facts :recovered-parents recovered))
       ;; Fix enclosing-fn using smallest containing span (byte containment
       ;; is more reliable than fn-stack when tree-sitter produces ERROR)
       (observe-file observer :begin :span event-file index nil)
       (fix-enclosing-fn-by-span record.source file-facts.definitions recovered)
       (observe-file observer :end :span event-file index file-facts)
      (table.insert files file-facts)
      (tset by-file record.path file-facts))
    {:files files
     :by-file by-file})

M
