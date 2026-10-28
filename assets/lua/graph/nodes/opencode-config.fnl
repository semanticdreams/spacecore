(local glm (require :glm))
(local {:GraphNode GraphNode} (require :graph/node-base))
(local Signal (require :signal))
(local Common (require :graph/nodes/opencode-common))
(local ConfigView (require :graph/view/views/opencode-config))

;; Current OpenCode server configuration as a read-only graph node. Per the
;; reconciled design: this is CURRENT server configuration, never presented as
;; session-effective or historical configuration.

(fn config-actions [self fetch]
  [{:name "Refresh Config" :icon "refresh"
    :fn (fn [_button _event] (fetch self))}])

(fn try-submit! [client path stale? request-generation on-ok]
  (local (submitted err)
    (pcall
      (fn []
        (client.submit "GET" path
          (Common.get-request
            (Common.guarded-response stale? request-generation on-ok))))))
  (if submitted nil (tostring err)))

(fn OpenCodeConfigNode [opts]
  (local ensure (if opts.ensure-client opts.ensure-client Common.default-ensure-client))
  (local base
    (GraphNode
      {:key "opencode-config"
       :label "opencode config"
       :color (glm.vec4 0.4 0.5 0.45 1)
       :sub-color (glm.vec4 0.55 0.65 0.6 1)
       :size 8.0
       :view ConfigView.View :preview ConfigView.Preview}))
  (local self (setmetatable {:ensure-client ensure
                             :state :idle
                             :config nil :providers nil
                             :config-error nil :providers-error nil
                             :fetched-at nil :error nil
                             :changed (Signal)}
                            {:__index base}))

  (var generation 0)
  (var dropped false)
  (fn stale? [request-generation]
    (if dropped true (not= request-generation generation)))

  (fn emit []
    (self.changed:emit self))

  (fn settle [state message]
    (set self.state state)
    (set self.error message)
    (emit))

  (fn section-handler [section error-key pending request-generation]
    (fn [response]
      (when (and (not (stale? request-generation)) (. pending section))
        (tset pending section nil)
        (local valid? (and response.ok (= (type response.data) :table)))
        (if valid?
            (do (tset self section response.data) (tset self error-key nil))
            (tset self error-key
                  (if response.error (tostring response.error)
                      (.. section " response failed or was malformed"))))
        (if (next pending)
            (emit)
            (do
              (set self.fetched-at (os.time))
              (settle :ready nil))))))

  (fn submit-section [client path section error-key pending request-generation]
    (local handler (section-handler section error-key pending request-generation))
    (local failure (try-submit! client path stale? request-generation handler))
    (when failure (handler {:ok false :error failure})))

  (fn fetch [_self]
    (assert (not dropped) "dropped config node cannot fetch")
    (set generation (+ generation 1))
    (local request-generation generation)
    (local pending {:config true :providers true})
    (set self.state :loading)
    (set self.config-error nil)
    (set self.providers-error nil)
    (emit)
    (local (ok client) (pcall ensure))
    (if (not ok)
        (settle :unavailable (tostring client))
        (do
          (when (not (stale? request-generation))
            (submit-section client "/config" :config :config-error pending request-generation))
          (when (not (stale? request-generation))
            (submit-section client "/config/providers" :providers :providers-error pending request-generation)))))

  (fn drop [_self]
    (set dropped true)
    (set generation (+ generation 1))
    (self.changed:clear))

  (local base-mount base.mount)
  (fn mount [mounted graph]
    (base-mount mounted graph)
    (when (= mounted.state :idle)
      (mounted:fetch)))

  (tset self :fetch fetch)
  (tset self :drop drop)
  (tset self :mount mount)
  (tset self :actions (config-actions self fetch))
  (setmetatable self {:__index base}))

{:OpenCodeConfigNode OpenCodeConfigNode}
