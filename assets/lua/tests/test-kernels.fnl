(local fs (require :fs))
(local json (require :json))
(local tests [])
(local sysinfo (require :sysinfo))
(local platform-os (. (sysinfo.platform) :os))
(local is-windows (= platform-os "windows"))

(var temp-counter 0)
(local temp-root (fs.join-path "/tmp/space/tests" "kernels"))

(fn make-temp-dir []
  (set temp-counter (+ temp-counter 1))
  (fs.join-path temp-root (.. "kernels-" (os.time) "-" temp-counter)))

(fn with-temp-dir [f]
  (local dir (make-temp-dir))
  (when (fs.exists dir)
    (fs.remove-all dir))
  (fs.create-dirs dir)
  (local (ok result) (pcall f dir))
  (fs.remove-all dir)
  (if ok
      result
      (error result)))

(fn with-kernels [f]
  (with-temp-dir
    (fn [root]
      (local Kernels (require :kernels))
      (local kernels (Kernels.Kernels {:base-dir root
                                       :defer-callbacks false}))
      (local (ok result) (pcall f kernels root))
      (kernels:drop)
      (if ok
          result
          (error result)))))

(fn sandbox-startup-error? [instance]
  (local process-result (and instance instance.process-result))
  (local stderr-text (or (and process-result process-result.stderr) ""))
  (local stdout-text (or (and process-result process-result.stdout) ""))
  (or (string.find stderr-text "Operation not permitted" 1 true)
      (string.find stdout-text "Operation not permitted" 1 true)))

(fn wait-until [kernels timeout-seconds pred]
  (local deadline (+ (sysinfo.now-ms) (* 1000 (or timeout-seconds 5.0))))
  (var done? false)
  (while (and (not done?) (< (sysinfo.now-ms) deadline))
    (kernels:tick)
    (set done? (pred)))
  done?)

(fn kernels-create-update-delete []
  (with-kernels
    (fn [kernels _root]
      (local created (kernels:create-kernel {:name "Py kernel"
                                             :cmd "python3 script.py"
                                             :cwd "/tmp"}))
      (assert created "kernel should be created")
      (assert (not (= (tostring created.id) "0")) "created id should not be 0")
      (local listed (kernels:list-kernels))
      (assert (>= (length listed) 2) "should include internal kernel plus created")
      (local (updated update-err)
             (kernels:update-kernel created.id {:name "Renamed"}))
      (assert (not update-err) "update should succeed")
      (assert (= updated.name "Renamed") "name should update")
      (local (_deleted delete-err) (kernels:delete-kernel created.id))
      (assert (not delete-err) "delete should succeed")
      (assert (= (kernels:get-kernel created.id) nil) "deleted kernel should be absent"))))

(fn kernels-internal-immutable []
  (with-kernels
    (fn [kernels _root]
      (local (_k err1) (kernels:update-kernel 0 {:name "nope"}))
      (assert err1 "internal kernel should not be editable")
      (local (_d err2) (kernels:delete-kernel 0))
      (assert err2 "internal kernel should not be deletable")
      (local (_i err3) (kernels:run-kernel 0))
      (assert err3 "internal kernel should not spawn instances"))))

(fn kernels-run-internal-code []
  (with-kernels
    (fn [kernels _root]
      (var received nil)
      (kernels:run-code {:kernel 0
                         :source "(+ 1 2)"}
                        (fn [result]
                          (set received result)))
      (assert received "run-code callback should fire")
      (assert (= received.error "") "internal kernel should not error")
      (assert (= (tostring received.output) "3") "internal kernel should return result"))))

(fn kernels-run-internal-code-normalizes-float-id []
  (with-kernels
    (fn [kernels _root]
      (var received-number nil)
      (kernels:run-code {:kernel 0.0
                         :source "(+ 2 3)"}
                        (fn [result]
                          (set received-number result)))
      (assert received-number "run-code callback should fire for float id")
      (assert (= received-number.error "") "float id should resolve builtin kernel")
      (assert (= (tostring received-number.output) "5") "float id should execute on builtin kernel")

      (var received-string nil)
      (kernels:run-code {:kernel "0.0"
                         :source "(+ 3 4)"}
                        (fn [result]
                          (set received-string result)))
      (assert received-string "run-code callback should fire for float-like string id")
      (assert (= received-string.error "") "float-like string id should resolve builtin kernel")
      (assert (= (tostring received-string.output) "7")
              "float-like string id should execute on builtin kernel"))))

(fn kernels-name-ambiguity-errors []
  (with-kernels
    (fn [kernels _root]
      (kernels:create-kernel {:name "dup" :cmd "python3 a.py"})
      (kernels:create-kernel {:name "dup" :cmd "python3 b.py"})
      (var received nil)
      (kernels:run-code {:kernel "dup"
                         :source "print('x')"}
                        (fn [result]
                          (set received result)))
      (assert received "callback should fire")
      (assert (string.find (or received.error "") "ambiguous")
              "duplicate names should produce ambiguity error"))))

(fn kernels-create-rejects-custom-id []
  (with-kernels
    (fn [kernels _root]
      (local (created err)
             (kernels:create-kernel {:id "custom-id"
                                     :name "bad"}))
      (assert (not created) "create with custom id should fail")
      (assert err "create with custom id should return error"))))

(fn kernels-delete-fails-while-instance-active []
  (with-kernels
    (fn [kernels _root]
      (local (kernel create-err)
             (kernels:create-kernel {:name "active"
                                     :cmd "sleep 30"}))
      (assert kernel "kernel should be created")
      (assert (not create-err) "create should not error")
      (local (instance run-err) (kernels:run-kernel kernel.id))
      (assert instance "run-kernel should create instance")
      (assert (not run-err) "run-kernel should not error")
      (local (_deleted delete-err) (kernels:delete-kernel kernel.id))
      (assert delete-err "delete should fail while instance is active")
      (assert (string.find delete-err "running instances")
              "delete error should explain active instances"))))

(fn kernels-subprocess-launcher-integration []
  (when is-windows
    (print "Skipping kernels subprocess launcher integration on Windows: Python runtime unavailable in Wine")
    (lua "return true"))
  (with-kernels
    (fn [kernels _root]
      (assert (and app app.engine app.engine.get-asset-path)
              "app.engine.get-asset-path should be available")
      (local launcher-path (app.engine.get-asset-path "python/subprocess_kernel_launcher.py"))
      (assert (and launcher-path (fs.exists launcher-path))
              "subprocess kernel launcher script should exist")

      (local (kernel create-err)
             (kernels:create-kernel
               {:name "py-launcher"
                :cmd (string.format "python3 %q" launcher-path)}))
      (assert kernel "process kernel should be created")
      (assert (not create-err) "process kernel create should not error")

      (local (instance run-err) (kernels:run-kernel kernel.id))
      (assert instance "run-kernel should return an instance")
      (assert (not run-err) "run-kernel should not error")

      (local running?
        (wait-until
          kernels
          8.0
          (fn []
            (local current (kernels:get-instance instance.id))
            (and current (= current.status "running")))))
      (local current-instance (kernels:get-instance instance.id))
      (when (and current-instance
                 (= current-instance.status "error")
                 (sandbox-startup-error? current-instance))
        (print "[SKIP] kernels subprocess launcher integration: sandbox blocks launcher socket bind")
        (lua "return true"))
      (assert running?
              (.. "launcher instance should reach running status"
                  (if current-instance
                      (.. "; status="
                          (tostring current-instance.status)
                          ", error="
                           (tostring (or current-instance.last-error "")) "; process=" (json.dumps current-instance.process-result))
                      "; instance disappeared")))

      (var success-result nil)
      (kernels:run-code
        {:kernel kernel.id
         :registers {:seed 1}
         :source "print(6 * 7)\n_registers['answer'] = 42"}
        (fn [result]
          (set success-result result)))
      (local got-success?
        (wait-until kernels 5.0 (fn [] (not (= success-result nil)))))
      (assert got-success? "run-code should callback for subprocess kernel")
      (assert (= (or success-result.error "") "")
              (.. "subprocess success run should not error: "
                  (tostring (or success-result.error ""))))
      (assert (string.find (or success-result.output "") "42")
              "subprocess success run should include printed output")
      (assert (= (. (or success-result.registers {}) :answer) 42)
              "subprocess run should return updated registers")

      (var error-result nil)
      (kernels:run-code
        {:kernel kernel.id
         :source "raise Exception('boom')"}
        (fn [result]
          (set error-result result)))
      (local got-error?
        (wait-until kernels 5.0 (fn [] (not (= error-result nil)))))
      (assert got-error? "run-code should callback for subprocess error case")
      (assert (string.find (or error-result.error "") "boom")
              "subprocess error run should include traceback message")

      (local (_stopped stop-err) (kernels:stop-instance instance.id))
      (assert (not stop-err) "stop-instance should succeed")
      (local stopped?
        (wait-until
          kernels
          5.0
          (fn []
            (local current (kernels:get-instance instance.id))
            (and current (= current.status "stopped")))))
      (assert stopped? "instance should stop cleanly"))))

(table.insert tests {:name "kernels create update delete"
                     :fn kernels-create-update-delete})
(table.insert tests {:name "kernels internal kernel immutable"
                     :fn kernels-internal-immutable})
(table.insert tests {:name "kernels run internal code"
                     :fn kernels-run-internal-code})
(table.insert tests {:name "kernels normalize numeric kernel ids"
                     :fn kernels-run-internal-code-normalizes-float-id})
(table.insert tests {:name "kernels duplicate names are errors"
                     :fn kernels-name-ambiguity-errors})
(table.insert tests {:name "kernels reject custom kernel ids"
                     :fn kernels-create-rejects-custom-id})
(table.insert tests {:name "kernels delete fails while active instance exists"
                     :fn kernels-delete-fails-while-instance-active})
(table.insert tests {:name "kernels subprocess launcher integration"
                     :fn kernels-subprocess-launcher-integration})

(local main
  (fn []
    (local runner (require :tests/runner))
    (runner.run-tests {:name "kernels"
                       :tests tests})))

{:name "kernels"
 :tests tests
 :main main}
