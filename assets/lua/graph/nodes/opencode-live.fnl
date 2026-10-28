(local json (require :json))
(local Timers (require :runtime-timers))
(fn relevant? [event id] (string.find (json.dumps event) id 1 true))
(fn retry-delay [attempts] (* 250 (^ 2 (- attempts 1))))

;; Submission precedes snapshots; only received events prove stream health.
(fn make-live [self id ensure invalidate! emit timer-factory]
  (local timeout (if timer-factory timer-factory Timers.Timeout))
  (var handle nil)
  (var retry nil)
  (var epoch 0)
  (var attempts 0)
  (var dropped? false)
  (var starting? false)
  (var start! nil)
  (fn active? [token] (and (not dropped?) (= token epoch)))
  (fn cancel-retry! []
    (when retry (retry:cancel))
    (set retry nil))
  (fn detach! []
    (set epoch (+ epoch 1))
    (local old handle)
    (set handle nil)
    (when old (old.unsubscribe)))
  (fn schedule! []
    (when (and (not dropped?) (not retry) (<= attempts 3))
      (local token epoch)
      (fn retry! []
        (when (active? token)
          (set retry nil)
          (start! false)
          (invalidate!)))
      (set retry (timeout {:delay-ms (retry-delay attempts) :callback retry!}))
      (retry:start)))
  (fn failed! [token reason state]
    (when (active? token)
      (detach!)
      (set attempts (+ attempts 1))
      (set self.live-error (tostring reason))
      (set self.live-state (if (> attempts 3) :stopped state))
      (schedule!)
      (emit)
      (when (not starting?) (invalidate!))))
  (fn connect! [token]
    (local client (ensure))
    (local events (self.events-factory client))
    (fn on-event [event]
      (when (active? token)
        (set attempts 0)
        (set self.live-error nil)
        (when (relevant? event id) (invalidate!))))
    (fn on-health [health]
      (failed! token (if health.kind health.kind "unknown stream failure") :degraded))
    ;; Canonical Events API is a plain function, not a self-taking method.
    (local subscribed (events.subscribe-with-health on-event on-health))
    (assert (and subscribed (= (type subscribed.unsubscribe) :function))
            "OpenCode events subscription requires unsubscribe")
    subscribed)
  (set start!
    (fn [explicit?]
      (assert (not dropped?) "dropped OpenCode live owner cannot restart")
      (when explicit? (cancel-retry!) (set attempts 0))
      (when (and (not handle) (not retry) (<= attempts 3))
        (set epoch (+ epoch 1))
        (local token epoch)
        (set starting? true)
        (local (ok subscribed) (pcall connect! token))
        (if (not ok)
            (failed! token subscribed :unavailable)
            (active? token)
            (do (set handle subscribed) (set self.live-state :live) (set self.live-error nil) (emit))
            (subscribed.unsubscribe))
        (set starting? false))))
  (fn stop! []
    (set dropped? true)
    (cancel-retry!)
    (detach!)
    (set self.live-state :stopped))
  {:start! start! :stop! stop!})

make-live
