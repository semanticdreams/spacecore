(local Signal (require :signal))

;; Installing saved topology is authoritative. Derived adapters may reconcile
;; only once publication and saved presentation installation have finished.
(fn wrap [map method]
  (fn [_self state]
    (assert (not map.installing-topology?) "nested graph topology installation")
    (set map.installing-topology? true)
    (local (ok result) (pcall method map state))
    (set map.installing-topology? false)
    (when (not ok) (error result 0))
    (map.topology-installed:emit map)
    result))

(fn install [map]
  (set map.topology-installed (Signal))
  (set map.installing-topology? false)
  (set map.restore-state (wrap map map.restore-state))
  (set map.install-reference-state! (wrap map map.install-reference-state!))
  (local drop map.drop)
  (fn drop-with-installation [_self]
    (drop map)
    (map.topology-installed:clear))
  (set map.drop drop-with-installation)
  map)

{:install install}
