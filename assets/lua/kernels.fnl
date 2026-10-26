(local Signal (require :signal))
(local appdirs (require :appdirs))
(local fs (require :fs))
(local Uuid (require :uuid))
(local json (require :json))
(local JsonUtils (require :json-utils))
(local FennelEvaluator (require :fennel-evaluator))
(local process (require :process))
(local sysinfo (require :sysinfo))
(local zmq (require :zmq))

(fn ensure-dir [path]
  (when (and path fs fs.create-dirs)
    (pcall (fn [] (fs.create-dirs path))))
  path)

(fn trim-string [value]
  (local text
    (if (or (= value nil) (= value :nil))
        ""
        (tostring value)))
  (string.gsub text "^%s*(.-)%s*$" "%1"))

(fn normalize-name [value]
  (trim-string value))

(fn normalize-cmd [value]
  (trim-string value))

(fn normalize-cwd [value]
  (trim-string value))

(fn id-key [id]
  (if (= (type id) "number")
      (do
        (local integer (math.tointeger id))
        (if integer
            (tostring integer)
            (tostring id)))
      (if (= (type id) "string")
          (do
            (local numeric (tonumber id))
            (if (not (= numeric nil))
                (do
                  (local integer (math.tointeger numeric))
                  (if integer
                      (tostring integer)
                      (tostring id)))
                (tostring id)))
          (tostring id))))

(fn internal-kernel []
  {:id 0
   :name "fennel"
   :cmd ""
   :cwd ""
   :internal true})

(fn instance-label [instance]
  (.. (or instance.id "instance")
      " ["
      (or instance.status "unknown")
      "]"))

(fn kernel-label [kernel]
  (local name (normalize-name (and kernel kernel.name)))
  (local id (tostring (or (and kernel kernel.id) "?")))
  (if (> (string.len name) 0)
      (.. name " (" id ")")
      (.. "kernel " id)))

(fn file-name->id [name]
  (if (and name (string.match name "%.json$"))
      (string.gsub name "%.json$" "")
      nil))

(fn with-callback [cb payload]
  (if cb
      (cb payload)
      nil))

(fn Kernels [opts]
  (local options (or opts {}))
  (local defer-callbacks? (if (= options.defer-callbacks nil) true options.defer-callbacks))
  (local base-dir (or options.base-dir
                      (and appdirs (appdirs.user-data-dir "space"))))
  (local kernels-dir (and base-dir fs (fs.join-path base-dir "kernels")))
  (local runtime-dir (and kernels-dir fs (fs.join-path kernels-dir "runtime")))
  (local log-dir (and kernels-dir fs (fs.join-path kernels-dir "logs")))
  (ensure-dir kernels-dir)
  (ensure-dir runtime-dir)
  (ensure-dir log-dir)

  (local definitions-by-id {})
  (var instances-by-id {})
  (var instance-order {})

  (local kernels-changed (Signal))
  (local instances-changed (Signal))

  (set (. definitions-by-id "0") (internal-kernel))

  (fn kernel-path [id]
    (and kernels-dir fs (fs.join-path kernels-dir (.. (tostring id) ".json"))))

  (fn log-path-for-kernel [kernel-id]
    (and log-dir fs (fs.join-path log-dir (.. (tostring kernel-id) ".log"))))

  (fn timestamp-prefix []
    (.. "[" (os.date "%Y-%m-%d %H:%M:%S") "] "))

  (fn append-log [kernel-id text]
    (local payload (or text ""))
    (when (> (string.len payload) 0)
      (local path (log-path-for-kernel kernel-id))
      (when path
        (ensure-dir log-dir)
        (pcall (fn [] (fs.append-file path payload))))))

  (fn log-line [kernel-id text]
    (append-log kernel-id (.. (timestamp-prefix) text "\n")))

  (fn emit-kernels-changed []
    (kernels-changed:emit true))

  (fn emit-instances-changed []
    (instances-changed:emit true))

  (fn schedule-callback [cb payload immediate?]
    (if (and (not immediate?) defer-callbacks? app app.next-frame)
        (app.next-frame (fn [] (with-callback cb payload)))
        (with-callback cb payload)))

  (fn read-kernel [path]
    (when (and path fs fs.exists (fs.exists path))
      (local (ok content-or-error) (pcall fs.read-file path))
      (when ok
        (local (parse-ok data-or-error) (pcall json.loads content-or-error))
        (when parse-ok
          (local id (tostring (or data-or-error.id "")))
          (when (> (string.len id) 0)
            {:id id
             :name (normalize-name data-or-error.name)
             :cmd (normalize-cmd data-or-error.cmd)
             :cwd (normalize-cwd data-or-error.cwd)
             :internal false})))))

  (fn write-kernel [kernel]
    (when (and kernel (not kernel.internal))
      (local path (kernel-path kernel.id))
      (when path
        (ensure-dir kernels-dir)
        (JsonUtils.write-json!
          path
          {:id (tostring kernel.id)
           :name (normalize-name kernel.name)
           :cmd (normalize-cmd kernel.cmd)
           :cwd (normalize-cwd kernel.cwd)}))))

  (fn load-kernels []
    (when (and kernels-dir fs fs.list-dir (fs.exists kernels-dir))
      (local (ok entries-or-error) (pcall fs.list-dir kernels-dir false))
      (when ok
        (each [_ entry (ipairs (or entries-or-error []))]
          (when (and entry entry.is-file entry.name)
            (local id (file-name->id entry.name))
            (when (and id (not (= id "0")))
              (local kernel (read-kernel entry.path))
              (when kernel
                (set (. definitions-by-id (id-key kernel.id)) kernel))))))))

  (fn sorted-kernels []
    (local items [])
    (each [_ kernel (pairs definitions-by-id)]
      (table.insert items kernel))
    (table.sort items
                (fn [a b]
                  (if (= (tostring a.id) "0")
                      true
                      (if (= (tostring b.id) "0")
                          false
                          (< (tostring a.id) (tostring b.id))))))
    items)

  (fn get-kernel-by-id [id]
    (. definitions-by-id (id-key id)))

  (fn kernels-with-name [name]
    (local target-name (normalize-name name))
    (local matches [])
    (each [_ kernel (pairs definitions-by-id)]
      (when (= (normalize-name kernel.name) target-name)
        (table.insert matches kernel)))
    matches)

  (fn cleanup-instance-socket [instance]
    (when instance
      (when instance.socket
        (pcall (fn [] (instance.socket:close)))
        (set instance.socket nil))
      (when instance.zmq-context
        (pcall (fn [] (instance.zmq-context:close)))
        (set instance.zmq-context nil))))

  (fn fail-request [request err]
    (when (and request request.callback)
      (schedule-callback request.callback
                         {:output ""
                          :error err
                           :registers (or request.registers {})}
                         request.callback-immediate?)))

  (fn fail-pending-requests [instance err]
    (when (and instance instance.current-request)
      (fail-request instance.current-request err)
      (set instance.current-request nil))
    (each [_ request (ipairs (or instance.queue []))]
      (fail-request request err))
    (set instance.queue []))

  (fn complete-instance-exit [instance result]
    (when instance
      (set instance.process-id nil)
      (set instance.process-result result)
      (local exit-code (or (and result result.exit-code) -1))
      (log-line instance.kernel-id
                (.. "instance " instance.id " process exited with " (tostring exit-code)))
      (local stdout (or (and result result.stdout) ""))
      (local stderr (or (and result result.stderr) ""))
      (when (> (string.len stdout) 0)
        (append-log instance.kernel-id (.. stdout "\n")))
      (when (> (string.len stderr) 0)
        (append-log instance.kernel-id (.. stderr "\n")))

      (if (= instance.status "stopping")
          (do
            (set instance.status "stopped")
            (set instance.last-error nil))
          (if (= instance.status "running")
              (do
                (set instance.status "error")
                (set instance.last-error
                     (.. "Kernel process exited unexpectedly (code "
                         (tostring exit-code)
                         ")")))
              (if (= instance.status "starting")
                  (do
                    (set instance.status "error")
                    (set instance.last-error
                         (.. "Kernel failed during startup (code "
                             (tostring exit-code)
                             ")")))
                  (do
                    (set instance.status "stopped")
                    (set instance.last-error nil)))))
      (set instance.updated-at (os.time))
      (emit-instances-changed)
      (fail-pending-requests instance (or instance.last-error "Kernel stopped"))
      (cleanup-instance-socket instance)))

  (fn send-next-request [instance]
    (when (and instance
               (= instance.status "running")
               (not instance.current-request)
               (> (length (or instance.queue [])) 0))
      (local request (table.remove instance.queue 1))
      (local payload {:code request.source
                      :registers (json.dumps (or request.registers {}))
                      :catch_errors (if (= request.catch-errors nil)
                                        true
                                        request.catch-errors)})
      (local (ok err)
             (pcall
               (fn []
                 (instance.socket:send (json.dumps payload)))))
      (if ok
          (do
            (set instance.current-request request)
            (log-line instance.kernel-id
                      (.. "instance " instance.id " request sent")))
          (do
            (set instance.status "error")
            (set instance.last-error (.. "Kernel request send failed: " err))
            (set instance.updated-at (os.time))
            (emit-instances-changed)
            (fail-request request (.. "Kernel request send failed: " err))
            (cleanup-instance-socket instance)))))

  (fn consume-kernel-reply [instance]
    (local recv-flags (. zmq :recv-flags))
    (local msg (and instance.socket (instance.socket:recv recv-flags.DONTWAIT)))
    (if (not msg)
        false
        (do
          (local text (msg:to-string))
          (local (ok response-or-error) (pcall json.loads text))
          (if (not ok)
              (do
                (set instance.status "error")
                (set instance.last-error (.. "Kernel response parse failed: " response-or-error))
                (set instance.updated-at (os.time))
                (emit-instances-changed)
                (fail-pending-requests instance (.. "Kernel response parse failed: " response-or-error))
                (cleanup-instance-socket instance))
              (do
                (local output (or response-or-error.output ""))
                (local err-text (or response-or-error.error ""))
                (var registers {})
                (local registers-json (or response-or-error.registers "null"))
                (local (regs-ok parsed-registers) (pcall json.loads registers-json))
                (when regs-ok
                  (set registers parsed-registers))

                (when (> (string.len output) 0)
                  (append-log instance.kernel-id output))
                (when (> (string.len err-text) 0)
                  (append-log instance.kernel-id err-text))

                (local request instance.current-request)
                (set instance.current-request nil)
                (when (and request request.callback)
                  (schedule-callback request.callback
                                     {:output output
                                      :error err-text
                                       :registers registers}
                                     request.callback-immediate?))
                (send-next-request instance)))
          true)))

  (fn tick-instance [instance]
    (when instance
      (if (= instance.status "starting")
          (do
            (var endpoint nil)
            (var endpoint-error "Connection file not found")
            (when (and instance.connection-file fs fs.exists (fs.exists instance.connection-file))
              (local (ok-read content-or-error) (pcall fs.read-file instance.connection-file))
              (if (not ok-read)
                  (set endpoint-error (.. "Failed to read connection file: " content-or-error))
                  (if (or (not content-or-error) (= (string.len content-or-error) 0))
                      (set endpoint-error "Connection file not ready")
                      (do
                        (local (ok-parse parsed-or-error) (pcall json.loads content-or-error))
                        (if (not ok-parse)
                            (set endpoint-error (.. "Failed to parse connection file: " parsed-or-error))
                            (do
                              (local candidate (and parsed-or-error parsed-or-error.endpoint))
                              (if (and candidate (> (string.len candidate) 0))
                                  (do
                                    (set endpoint candidate)
                                    (set endpoint-error nil))
                                  (set endpoint-error "Connection file missing endpoint"))))))))
            (if endpoint
                (do
                  (local socket-types (. zmq :socket-types))
                  (set instance.zmq-context (zmq.Context 1))
                  (set instance.socket (instance.zmq-context:socket socket-types.REQ))
                  (instance.socket:set-option-int "linger" 0)
                  (instance.socket:connect endpoint)
                  (set instance.endpoint endpoint)
                  (set instance.status "running")
                  (set instance.last-error nil)
                  (set instance.updated-at (os.time))
                  (emit-instances-changed)
                  (log-line instance.kernel-id
                            (.. "instance " instance.id " connected to " endpoint)))
                (when (> (sysinfo.now-ms) (or instance.start-deadline 0))
                  (when instance.process-id
                    (pcall (fn [] (process.kill instance.process-id 15))))
                  (set instance.status "error")
                  (set instance.last-error (or endpoint-error "Kernel startup timed out"))
                  (set instance.updated-at (os.time))
                  (emit-instances-changed))))
          nil)

      (if (= instance.status "running")
          (do
            (when instance.current-request
              (consume-kernel-reply instance))
            (send-next-request instance))
          nil)

      (if (= instance.status "stopping")
          (when (and instance.process-id
                     (> (sysinfo.now-ms) (or instance.stop-deadline 0)))
            (pcall (fn [] (process.kill instance.process-id 9))))
          nil)))

  (fn tick-all []
    (local completed (process.poll))
    (each [_ finished (ipairs (or completed []))]
      (local finished-id (and finished finished.id))
      (when finished-id
        (each [_ instance-id (ipairs instance-order)]
          (local instance (. instances-by-id instance-id))
          (when (and instance instance.process-id (= instance.process-id finished-id))
            (complete-instance-exit instance finished)))))
    (each [_ instance-id (ipairs instance-order)]
      (local instance (. instances-by-id instance-id))
      (tick-instance instance)))

  (fn run-internal [source registers callback]
    (local eval-result (FennelEvaluator.eval-source (or source "")))
    (if eval-result.ok
        (schedule-callback callback
                           {:output (FennelEvaluator.format-result eval-result.result)
                            :error ""
                            :registers (or registers {})})
        (schedule-callback callback
                           {:output ""
                            :error (FennelEvaluator.format-error eval-result.result)
                            :registers (or registers {})})))

  (fn create-instance [kernel]
    (local instance-id (Uuid.v4))
    (local instance
      {:id instance-id
       :kernel-id kernel.id
       :kernel-name kernel.name
       :status "starting"
       :created-at (os.time)
       :updated-at (os.time)
       :connection-file (and runtime-dir fs (fs.join-path runtime-dir (.. instance-id ".connection.json")))
       :endpoint nil
       :queue []
       :current-request nil
       :process-id nil
       :process-result nil
       :socket nil
       :zmq-context nil
       :last-error nil
       :start-deadline (+ (sysinfo.now-ms) 5000)
       :stop-deadline nil})
    (set (. instances-by-id instance-id) instance)
    (table.insert instance-order instance-id)
    (emit-instances-changed)
    instance)

  (fn remove-instance-from-order [instance-id]
    (for [i (length instance-order) 1 -1]
      (when (= (. instance-order i) instance-id)
        (table.remove instance-order i))))

  (fn stop-instance-internal [instance]
    (when instance
      (if (= instance.status "running")
          (do
            (set instance.status "stopping")
            (set instance.last-error nil)
            (set instance.updated-at (os.time))
            (emit-instances-changed)
            (set instance.stop-deadline (+ (sysinfo.now-ms) 3000))
            (when instance.process-id
              (pcall (fn [] (process.kill instance.process-id 15))))
            true)
          (if (= instance.status "starting")
              (do
                (set instance.status "stopping")
                (set instance.last-error nil)
                (set instance.updated-at (os.time))
                (emit-instances-changed)
                (set instance.stop-deadline (+ (sysinfo.now-ms) 3000))
                (when instance.process-id
                  (pcall (fn [] (process.kill instance.process-id 15))))
                true)
              false))))

  (fn spawn-instance-process [instance kernel]
    (local cmd (normalize-cmd kernel.cmd))
    (if (= (string.len cmd) 0)
        (do
          (set instance.status "error")
          (set instance.last-error "Kernel command is empty")
          (set instance.updated-at (os.time))
          (emit-instances-changed)
          instance)
        (do
          (when (and fs fs.exists instance.connection-file (fs.exists instance.connection-file))
            (pcall (fn [] (fs.remove instance.connection-file))))
          (local spawn-opts {:args ["/bin/bash" "-lc" cmd]
                             :env {:KERNEL_CONNECTION_FILE instance.connection-file}})
          (local cwd (normalize-cwd kernel.cwd))
          (when (> (string.len cwd) 0)
            (set spawn-opts.cwd cwd))
          (local (ok process-id-or-error)
                 (pcall (fn [] (process.spawn spawn-opts))))
          (if ok
              (do
                (set instance.process-id process-id-or-error)
                (log-line kernel.id
                          (.. "instance " instance.id " spawned process " (tostring process-id-or-error)))
                instance)
              (do
                (set instance.status "error")
                (set instance.last-error (.. "Kernel process spawn failed: " process-id-or-error))
                (set instance.updated-at (os.time))
                (emit-instances-changed)
                instance)))))

  (fn resolve-kernel-spec [spec]
    (if (= spec nil)
        (values (get-kernel-by-id 0) nil)
        (= (type spec) "number")
        (do
          (local kernel (get-kernel-by-id spec))
          (if kernel
              (values kernel nil)
              (values nil (.. "Unknown kernel id: " (tostring spec)))))
        (= (type spec) "string")
        (do
          (local by-id (get-kernel-by-id spec))
          (if by-id
              (values by-id nil)
              (do
                (local matches (kernels-with-name spec))
                (if (= (length matches) 1)
                    (values (. matches 1) nil)
                    (= (length matches) 0)
                    (values nil (.. "Unknown kernel name: " spec))
                    (values nil (.. "Kernel name is ambiguous: " spec))))))
        (values nil (.. "Invalid kernel spec type: " (type spec)))))

  (fn choose-running-instance [kernel-id]
    (local running [])
    (each [_ instance-id (ipairs instance-order)]
      (local instance (. instances-by-id instance-id))
      (when (and instance
                 (= (id-key instance.kernel-id) (id-key kernel-id))
                 (= instance.status "running"))
        (table.insert running instance)))
    (if (= (length running) 0)
        nil
        ;; If several are running, use the most recently created/ran one.
        (. running (length running))))

  (fn enqueue-run-request [instance source registers catch-errors callback immediate?]
    (table.insert instance.queue
                  {:source source
                   :registers (or registers {})
                   :catch-errors catch-errors
                    :callback callback :callback-immediate? immediate?})
    (send-next-request instance))

  (fn list-kernels [_self]
    (sorted-kernels))

  (fn get-kernel [_self id]
    (get-kernel-by-id id))

  (fn create-kernel [_self opts]
    (local create-opts (or opts {}))
    (if (or (not (= create-opts.id nil))
            (not (= create-opts.kernel-id nil))
            (not (= create-opts.kernel_id nil)))
        (values nil "Kernel id is generated automatically")
        (do
          (var id nil)
          (var tries 0)
          (while (and (not id) (< tries 10))
            (local candidate (tostring (Uuid.v4)))
            (when (not (. definitions-by-id (id-key candidate)))
              (set id candidate))
            (set tries (+ tries 1)))
          (if (not id)
              (values nil "Failed to allocate a unique kernel id")
              (do
                (local kernel {:id id
                               :name (normalize-name create-opts.name)
                               :cmd (normalize-cmd create-opts.cmd)
                               :cwd (normalize-cwd create-opts.cwd)
                               :internal false})
                (set (. definitions-by-id (id-key id)) kernel)
                (write-kernel kernel)
                (emit-kernels-changed)
                (values kernel nil))))))

  (fn update-kernel [_self id updates]
    (local kernel (get-kernel-by-id id))
    (if (not kernel)
        (values nil (.. "Unknown kernel id: " (tostring id)))
        (if kernel.internal
            (values nil "Kernel 0 is immutable")
            (do
              (each [k v (pairs (or updates {}))]
                (if (or (= k :name) (= k "name"))
                    (set kernel.name (normalize-name v))
                    (if (or (= k :cmd) (= k "cmd"))
                        (set kernel.cmd (normalize-cmd v))
                        (if (or (= k :cwd) (= k "cwd"))
                            (set kernel.cwd (normalize-cwd v))))))
              (write-kernel kernel)
              (emit-kernels-changed)
              (values kernel nil)))))

  (fn delete-kernel [_self id]
    (local kernel (get-kernel-by-id id))
    (if (not kernel)
        (values nil (.. "Unknown kernel id: " (tostring id)))
        (if kernel.internal
            (values nil "Kernel 0 is immutable")
            (do
              (local active-instances [])
              (local to-remove [])
              (each [_ instance-id (ipairs instance-order)]
                (local instance (. instances-by-id instance-id))
                (when (and instance (= (id-key instance.kernel-id) (id-key kernel.id)))
                  (if (or (= instance.status "starting")
                          (= instance.status "running")
                          (= instance.status "stopping"))
                      (table.insert active-instances instance)
                      (table.insert to-remove instance))))
              (if (> (length active-instances) 0)
                  (values nil (.. "Kernel has running instances ("
                                  (tostring (length active-instances))
                                  "); stop them before deleting"))
                  (do
                    (each [_ instance (ipairs to-remove)]
                      (set (. instances-by-id instance.id) nil)
                      (remove-instance-from-order instance.id)
                      (cleanup-instance-socket instance))
                    (local path (kernel-path kernel.id))
                    (when (and path fs fs.exists (fs.exists path))
                      (pcall (fn [] (fs.remove path))))
                    (set (. definitions-by-id (id-key kernel.id)) nil)
                    (emit-kernels-changed)
                    (emit-instances-changed)
                    (values kernel nil)))))))

  (fn list-instances [_self opts]
    (local options-list (or opts {}))
    (local kernel-id (or options-list.kernel-id options-list.kernel_id options-list.kernel))
    (if (= kernel-id nil)
        (icollect [_ instance-id (ipairs instance-order)] (. instances-by-id instance-id))
        (do
          (local produced [])
          (each [_ instance-id (ipairs instance-order)]
            (local instance (. instances-by-id instance-id))
            (when (and instance (= (id-key instance.kernel-id) (id-key kernel-id)))
              (table.insert produced instance)))
          produced)))

  (fn get-instance [_self instance-id]
    (. instances-by-id (tostring instance-id)))

  (fn run-kernel [_self kernel-id]
    (local kernel (get-kernel-by-id kernel-id))
    (if (not kernel)
        (values nil (.. "Unknown kernel id: " (tostring kernel-id)))
        (if kernel.internal
            (values nil "Kernel 0 does not spawn process instances")
            (do
              (local instance (create-instance kernel))
              (spawn-instance-process instance kernel)
              (values instance nil)))))

  (fn stop-instance [_self instance-id]
    (local instance (. instances-by-id (tostring instance-id)))
    (if (not instance)
        (values nil (.. "Unknown kernel instance id: " (tostring instance-id)))
        (values instance (if (stop-instance-internal instance) nil "Instance is not running"))))

  (fn run-code [_self opts callback]
    (local run-opts (or opts {}))
    (local spec
      (if (not (= run-opts.kernel nil))
          run-opts.kernel
          (if (not (= run-opts.kernel-id nil))
              run-opts.kernel-id
              (if (not (= run-opts.kernel_name nil))
                  run-opts.kernel_name
                  0))))
    (local (kernel resolve-err) (resolve-kernel-spec spec))
    (if resolve-err
        (do
          (schedule-callback callback {:output "" :error resolve-err :registers (or run-opts.registers {})}
                             run-opts.callback-immediate?)
          nil)
        (if (= (tostring kernel.id) "0")
            (run-internal run-opts.source run-opts.registers callback)
            (do
              (local instance (choose-running-instance kernel.id))
              (if (not instance)
                  (schedule-callback
                    callback
                    {:output ""
                     :error (.. "No running instance for kernel " (kernel-label kernel))
                      :registers (or run-opts.registers {})}
                    run-opts.callback-immediate?)
                  (enqueue-run-request
                    instance
                    (or run-opts.source "")
                    run-opts.registers
                    (if (= run-opts.catch-errors nil) true run-opts.catch-errors)
                    callback run-opts.callback-immediate?)))))
    true)

  (fn drop [_self]
    (each [_ instance-id (ipairs instance-order)]
      (local instance (. instances-by-id instance-id))
      (when instance
        (when instance.process-id
          (pcall (fn [] (process.kill instance.process-id 9))))
        (set instance.process-id nil)
        (set instance.status "stopped")
        (cleanup-instance-socket instance)))
    (set instances-by-id {})
    (set instance-order {})
    (kernels-changed:clear)
    (instances-changed:clear))

  (load-kernels)

  {:base-dir base-dir
   :kernels-dir kernels-dir
   :runtime-dir runtime-dir
   :log-dir log-dir
   :kernels-changed kernels-changed
   :instances-changed instances-changed
   :tick tick-all
   :list-kernels list-kernels
   :get-kernel get-kernel
   :create-kernel create-kernel
   :update-kernel update-kernel
   :delete-kernel delete-kernel
   :list-instances list-instances
   :get-instance get-instance
   :run-kernel run-kernel
   :stop-instance stop-instance
   :run-code run-code
   :resolve-kernel (fn [_self selector] (resolve-kernel-spec selector))
   :instance-label instance-label
   :kernel-label kernel-label
   :drop drop})

(var default-kernels nil)

(fn get-default [opts]
  (if default-kernels
      default-kernels
      (do
        (set default-kernels (Kernels (or opts {})))
        default-kernels)))

{:Kernels Kernels
 :get-default get-default}
