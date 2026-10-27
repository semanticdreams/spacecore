;; Shared only by timestamp-equal record regression fixtures.
(fn with-record-clock [body]
  (local previous-time os.time)
  (fn clock [...]
    (assert (= (select "#" ...) 0) "record test clock accepts only zero-argument os.time")
    1700000000)
  (set os.time clock)
  (local (ok result) (pcall body))
  (set os.time previous-time)
  (if ok result (error result 0)))
with-record-clock
