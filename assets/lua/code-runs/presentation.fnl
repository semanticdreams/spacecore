(fn summary [run]
  (.. (if (= run.snapshot.name "") "Code run" run.snapshot.name)
      " — " run.status " — " (if (= run.status "running") "in progress" (string.format "%.0f ms" run.elapsed-ms))
      " — " (os.date "!%Y-%m-%d %H:%M:%S UTC" (math.floor (/ run.created-at 1000)))))

;; Previews stay compact: a bounded tail of recent output, aligned so the
;; last complete line survives cropping.
(fn output-tail [run]
  (local limit 480)
  (local body (string.gsub run.output "\n$" ""))
  (local cropped (if (> (# body) limit) (string.sub body (- (# body) (- limit 1))) body))
  (local nl (string.find cropped "\n"))
  (local aligned (if (and nl (> nl 1)) (string.sub cropped (+ nl 1)) cropped))
  (local parts [])
  (when (> (# aligned) 0) (table.insert parts aligned))
  (when run.error (table.insert parts (.. "Error: " run.error.message)))
  (if (= (length parts) 0) "(no output yet)" (table.concat parts "\n")))

(fn payload [run output-text]
  (.. "Run: " run.id "\nCode: code-entity:" run.code-entity-id
      "\nKernel: " (tostring run.snapshot.kernel) " (" run.snapshot.language ")"
      "\nElapsed: " (if (= run.status "running") "in progress" (string.format "%.0f ms" run.elapsed-ms))
      "\nCompletion: " run.completion-mode
      "\n\nOutput\n" output-text
      "\n\nInitial return\n" run.initial-result
      "\n\nResult (" run.result-type ")\n" run.result
      "\n\nError\n" (if run.error (.. run.error.message "\n" run.error.traceback) "(none)")))

(fn full-payload [run] (payload run run.output))
(fn preview-payload [run] (payload run (output-tail run)))

{:summary summary :payload full-payload :preview-payload preview-payload
 :output-tail output-tail}
