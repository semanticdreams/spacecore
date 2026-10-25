(fn summary [run]
  (.. (if (= run.snapshot.name "") "Code run" run.snapshot.name)
      " — " run.status " — " (if (= run.status "running") "in progress" (string.format "%.0f ms" run.elapsed-ms))
      " — " (os.date "!%Y-%m-%d %H:%M:%S UTC" (math.floor (/ run.created-at 1000)))))
(fn payload [run]
  (.. "Run: " run.id "\nCode entity: " run.code-entity-id
      "\nStatus: " run.status "\nCompletion: " run.completion-mode
      "\nLanguage: " run.snapshot.language "\nKernel: " (tostring run.snapshot.kernel)
      "\nCreated: " (os.date "!%Y-%m-%d %H:%M:%S UTC" (math.floor (/ run.created-at 1000)))
      "\nElapsed: " (if (= run.status "running") "in progress" (string.format "%.0f ms" run.elapsed-ms))
      "\n\nExecuted source\n" run.snapshot.source
      "\n\nCaptured output\n" run.output
      "\n\nInitial return\n" run.initial-result
      "\n\nResult (" run.result-type ")\n" run.result
      "\n\nError\n" (if run.error (.. run.error.message "\n" run.error.traceback) "(none)")))
{:summary summary :payload payload}
