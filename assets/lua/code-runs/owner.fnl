;; Probe only the known owner, never enumerate processes or infer identity from PID alone.
(local fs (require :fs))
(local Uuid (require :uuid))
(fn process-start [stat]
  (local rest (assert (string.match stat "^%d+ %(.+%) (.*)$") "invalid process stat"))
  (local fields [])
  (each [field (string.gmatch rest "%S+")] (table.insert fields field))
  (assert (. fields 20) "missing process start time")
  (values (. fields 20) (. fields 1)))
(fn boot-id []
  (string.match (fs.read-file "/proc/sys/kernel/random/boot_id") "^%s*(%S+)"))
(fn current []
  (local session (Uuid.v4))
  (if (fs.exists "/proc/self/stat")
      (do
        (local stat (fs.read-file "/proc/self/stat"))
        (local start (process-start stat))
        {:session session :pid (assert (string.match stat "^(%d+)")) :start start :boot (boot-id)})
      {:session session}))
(fn alive? [owner]
  (when owner.pid
    (local path (.. "/proc/" owner.pid "/stat"))
    (if (not (fs.exists path)) false
        (not (= owner.boot (boot-id))) false
        (do (local (start state) (process-start (fs.read-file path)))
            (and (= owner.start start) (not (= state "Z")))))))
{:current current :alive? alive?}
