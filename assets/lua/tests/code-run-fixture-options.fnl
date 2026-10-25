(local {:Store Store} (require :code-runs/store))
(fn options [stores]
  (assert stores.base-dir "code-run fixture requires isolated base-dir")
  (local result (collect [key value (pairs stores)] key value))
  (set result.code-run-store (Store {:base-dir stores.base-dir}))
  result)
options
