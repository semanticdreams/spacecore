(local {:Store Store} (require :code-runs/store))
(local {:Runner Runner} (require :code-runs/runner))
(fn init! [application]
  (assert (not application.code-runner) "code-run runtime already initialized")
  (set application.code-run-store (Store {:base-dir application.user-data-dir}))
  (set application.code-runner
    (Runner {:store application.code-run-store :code-store application.code-store
             :kernels application.kernels})))
(fn drop! [application]
  (when application.code-runner (application.code-runner:drop))
  (set application.code-runner nil)
  (set application.code-run-store nil))
{:init! init! :drop! drop!}
