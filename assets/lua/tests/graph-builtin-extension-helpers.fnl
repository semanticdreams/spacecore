(local Registry (require :graph/extension-registry))
(local BuiltInGraphExtensions (require :graph/extensions/builtins))
(local {:EntityTypeCatalog EntityTypeCatalog} (require :entities/type-catalog))
(local fs (require :fs))
(local Graph (require :graph/init))
(local GraphMap (require :graph/map))
(local Strings (require :entities/string))
(local Links (require :entities/link))
(local tempfile (require :tempfile))

(var temp-counter 0)

(fn make-temp-dir []
  (set temp-counter (+ temp-counter 1))
  (local dir (fs.join-path "/tmp/space/tests" (.. "graph-builtins-" (os.time) "-" temp-counter)))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (fs.create-dirs dir)
  dir)

(fn make-graph [opts]
  (assert (or (= opts nil) (= (type opts) :table)) "make-graph requires options table")
  (local dir (tempfile.TemporaryDirectory {:prefix "graph-view-stores-"}))
  (local options (collect [key value (pairs (or opts {}))] (values key value)))
  (set options.string-store (or options.string-store (Strings.StringEntityStore {:base-dir dir.path})))
  (set options.link-store (or options.link-store (Links.LinkEntityStore {:base-dir dir.path})))
  (local graph (Graph options))
  (local drop graph.drop)
  (set graph.drop (fn drop-owned-graph [self]
                    (drop self)
                    (dir:drop)))
  graph)

(fn make-test-graph []
  (local graph (make-graph {:with-start false}))
  (local original-has-key-loader graph.has-key-loader-for-key)
  (set graph.has-key-loader-for-key
       (fn has-test-loader [self key]
         (if (and original-has-key-loader (original-has-key-loader self key)) true
             (if key true false))))
  graph)

(fn make-graph-map [graph opts]
  (assert (and graph graph.drop) "make-graph-map requires an owned graph")
  (local options (or opts {}))
  (local graph-map (GraphMap.GraphMap {:graph graph :id (or options.id "main")}))
  (local drop graph-map.drop)
  (set graph-map.drop (fn drop-owned-map [self]
                        (drop self)
                        (graph:drop)))
  graph-map)

(fn make-test-graph-map [opts]
  (make-graph-map (make-test-graph) opts))

(fn ordered-fixtures [first second]
  (fn run-ordered-fixtures []
    (first)
    (second)))

(fn make-default-kernels []
  (local Signal (require :signal))
  {:kernels-changed (Signal)
   :instances-changed (Signal)
   :list-kernels (fn [_self] [])
   :list-instances (fn [_self _opts] [])
   :kernel-label (fn [_self kernel] (if kernel.name kernel.name kernel.id))
   :get-kernel (fn [_self _id] nil)
   :get-instance (fn [_self _id] nil)
   :drop (fn [_self] true)})

(fn make-default-world-manager []
  (local Signal (require :signal))
  {:changed (Signal)
   :list-tabs (fn [_self] [])
   :get-world-entry (fn [_self _id] nil)})

(fn make-default-options [dir opts]
  (local StringEntityStore (require :entities/string))
  (local CodeEntityStore (require :entities/code))
  (local ListEntityStore (require :entities/list))
  (local DictEntityStore (require :entities/dict))
  (local LinkEntityStore (require :entities/link))
  (local IdentityStore (require :entities/identity))
  (local NotebookStore (require :notebooks/store))
  (local LlmStore (require :llm/conversations/store))
  (local WorkflowStore (require :workflows/store))
  (local options
    {:entity-type-catalog (EntityTypeCatalog {:types (BuiltInGraphExtensions.entity-types)})
     :string-store (StringEntityStore.StringEntityStore {:base-dir (fs.join-path dir "string")})
     :code-store (CodeEntityStore.CodeEntityStore {:base-dir (fs.join-path dir "code")})
     :list-store (ListEntityStore.ListEntityStore {:base-dir (fs.join-path dir "list")})
     :dict-store (DictEntityStore.DictEntityStore {:base-dir (fs.join-path dir "dict")})
     :link-store (LinkEntityStore.LinkEntityStore {:base-dir (fs.join-path dir "link")})
     :identity-store (IdentityStore.IdentityStore {:base-dir (fs.join-path dir "identity")})
     :notebook-store (NotebookStore.NotebookStore {:base-dir (fs.join-path dir "notebooks")})
     :llm-store (LlmStore.Store {:base-dir (fs.join-path dir "llm")})
     :workflow-store (WorkflowStore.WorkflowStore {:base-dir (fs.join-path dir "workflow")})
     :kernels (make-default-kernels)
     :world-manager (make-default-world-manager)
     :asset-path-resolver (fn [path] path)})
  (each [key value (pairs (if opts opts {}))]
    (set (. options key) value))
  options)

(fn make-scheme-set [schemes]
  (when schemes
    (local scheme-set {})
    (each [_ scheme (ipairs schemes)]
      (set (. scheme-set scheme) true))
    scheme-set))

(fn unregister-noop-handle [handle-self]
  (set handle-self.active? false)
  true)

(fn noop-loader-handle []
  {:active? true
   :unregister unregister-noop-handle})

(fn filtered-register-key-loader [target allowed-schemes _self scheme loader-fn opts]
  (if (. allowed-schemes scheme)
      (target:register-key-loader scheme loader-fn opts)
      (noop-loader-handle)))

(fn make-filtered-graph [graph allowed-schemes]
  (if allowed-schemes
      {:register-key-loader
       (fn [_self scheme loader-fn opts]
         (filtered-register-key-loader graph allowed-schemes _self scheme loader-fn opts))}
      graph))

(fn unregister-handles [handles]
  (for [i (length handles) 1 -1]
    (local handle (. handles i))
    (when (and handle handle.unregister handle.active?)
      (handle:unregister))))

(fn install-builtins! [graph opts]
  (assert graph "install-builtins! requires graph")
  (local dir (make-temp-dir))
  (local options (make-default-options dir opts))
  (local registry (Registry.GraphExtensionRegistry {:app options.app}))
  (local runtime {:graph (make-filtered-graph graph (make-scheme-set options.only-schemes))
                  :graph-map-manager options.graph-map-manager})
  (local handles (BuiltInGraphExtensions.register! registry options))
  (registry:install-runtime runtime)
  {:registry registry
   :runtime runtime
   :handles handles
   :opts options
   :drop (fn [_self]
           (registry:uninstall-runtime runtime)
           (unregister-handles handles)
           (when (fs.exists dir)
             (fs.remove-all dir)))})

{:install-builtins! install-builtins!
 :make-graph make-graph
 :make-test-graph make-test-graph
 :make-graph-map make-graph-map
 :ordered-fixtures ordered-fixtures
 :make-test-graph-map make-test-graph-map}
