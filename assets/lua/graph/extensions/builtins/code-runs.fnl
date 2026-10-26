(local Common (require :graph/extensions/builtins/common))
(local {:Node Node} (require :graph/nodes/code-run))
(fn descriptors [opts]
  (fn install [graph ctx]
    (fn load [key]
      (local id (string.match key "^code%-run:(.+)$"))
      (local store (assert opts.code-run-store "code-run loader requires code-run-store"))
      (when (and id (store:get-run id)) (Node {:run-id id :store store})))
    [(graph:register-key-loader "code-run" load {:owner-id ctx.owner-id :extension-id ctx.extension-id})])
  [(Common.descriptor {:id "builtin-graph-code-runs" :unit-id "builtin-graph-code-runs"
                       :schemes ["code-run"] :install-loaders install})])
{:descriptors descriptors}
