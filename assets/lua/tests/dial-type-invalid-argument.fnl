(local DialTypeModule (require :dial-type))

(fn assert-rejected [label invoke]
  (local (ok err) (pcall invoke))
  (print "DIAL_INVALID_RESULT" label ok (type err))
  (assert (not ok) "InputDialType must reject invalid InputState, not construct an adapter")
  (assert (= (type err) :string) "InputDialType rejection must be a Lua error string")
  (assert (string.find err "InputDialType requires a non-null InputState userdata" 1 true)
          err)
  (print err))

(fn foreign-userdata []
  (local foreign (DialTypeModule.DialType))
  (assert (= (type foreign) :userdata) "foreign case requires native DialType userdata")
  (local original-metatable (debug.getmetatable foreign))
  (assert (= (type original-metatable) :table) "native DialType must have a metatable")
  (local invoke (fn [] (DialTypeModule.InputDialType foreign)))
  (assert-rejected :foreign invoke)
  (debug.setmetatable foreign nil)
  (local (ok err)
    (pcall (fn []
             (assert (= (debug.getmetatable foreign) nil) "foreign metatable must be absent")
             (for [attempt 1 3]
               (assert-rejected (.. "foreign-no-metatable-" attempt) invoke)))))
  ;; Restore before any assertion error escapes, including an incorrectly accepted adapter.
  (debug.setmetatable foreign original-metatable)
  (assert (= (debug.getmetatable foreign) original-metatable) "foreign metatable must be restored")
  (print "DIAL_FOREIGN_METATABLE_RESTORED")
  (assert ok err))

(local cases
  {:omitted (fn [] (DialTypeModule.InputDialType))
   :nil (fn [] (DialTypeModule.InputDialType nil))
   :table (fn [] (DialTypeModule.InputDialType {}))
   :boolean (fn [] (DialTypeModule.InputDialType false))
   :number (fn [] (DialTypeModule.InputDialType 42))
   :string (fn [] (DialTypeModule.InputDialType "invalid-input"))
   :foreign foreign-userdata})

(fn main []
  (local case-name (os.getenv "SPACE_DIAL_TYPE_INVALID_CASE"))
  (local invoke (and case-name (. cases case-name)))
  (assert invoke "SPACE_DIAL_TYPE_INVALID_CASE must name a fixed invalid-argument case")
  (print (.. "DIAL_INVALID_BEGIN " case-name))
  (io.flush)
  (if (= case-name :foreign)
      (invoke)
      (assert-rejected case-name invoke))
  (print (.. "DIAL_INVALID_OK " case-name))
  (io.flush))

{:main main}
