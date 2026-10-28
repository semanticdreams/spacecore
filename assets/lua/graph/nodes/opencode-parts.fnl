(local json (require :json))
(local {:truncate-with-ellipsis truncate-with-ellipsis} (require :graph/view/utils))

;; Shared message/part projection for the OpenCode session exposure.
;; Built from the C0 payload capture (see
;; docs/specs/2026-10-26-opencode-session-graph-exposure-design.md): text,
;; reasoning, tool (state.status/input/output/title), patch (files/hash),
;; step-start/step-finish (tokens/cost), and unknown types kept explicit.
;; Consumers: the session transcript (thin lines), message nodes (full
;; blocks), and later the live stream.

(fn part-kind [part]
  (if part.type (tostring part.type) "?"))

(fn project-text [part]
  (local text (if part.text (tostring part.text) ""))
  (if (> (length text) 0)
      {:kind :text :text text}
      nil))

(fn project-reasoning [part]
  {:kind :reasoning
   :text (if part.text (tostring part.text) "")})

(fn tool-name [part]
  (if part.tool (tostring part.tool) "?"))

(fn tool-summary [part]
  (local state (if part.state part.state {}))
  (if (and state.title (> (length (tostring state.title)) 0))
      (tostring state.title)
      (tool-name part)))

(fn project-tool [part]
  (local state (if part.state part.state {}))
  {:kind :tool
   :name (tool-name part)
   :status (if state.status (tostring state.status) "?")
   :summary (tool-summary part)
   ;; Lossless: the full original part is retained for deep views (inputs,
   ;; outputs, attachments, metadata) per the roadmap contract.
   :detail (json.dumps part)})

(fn project-patch [part]
  (local files (if part.files part.files []))
  {:kind :patch
   :file-count (length files)
   ;; Lossless original part for deep views.
   :detail (json.dumps part)})

(fn project-step [part]
  {:kind :step
   :step (part-kind part)
   :tokens (if part.tokens part.tokens nil)
   :cost (if part.cost part.cost nil)})

(fn project-unknown [part]
  {:kind :unknown
   :part-type (part-kind part)
   :detail (json.dumps part)})

(fn project-part [part]
  (local kind (part-kind part))
  (if (= kind "text")
      (project-text part)
      (= kind "reasoning")
      (project-reasoning part)
      (= kind "tool")
      (project-tool part)
      (= kind "patch")
      (project-patch part)
      (= kind "step-start")
      (project-step part)
      (= kind "step-finish")
      (project-step part)
      (project-unknown part)))

(fn project-message [message]
  (local blocks [])
  (each [_ part (ipairs (if message.parts message.parts []))]
    (local block (project-part part))
    (when block
      (table.insert blocks block)))
  blocks)

(fn render-reasoning [text]
  (if (> (length text) 0)
      (.. "[thinking]\n" text "\n[/thinking]")
      "[thinking]"))

(fn patch-line [block]
  (.. "[patch: " (tostring block.file-count) " file(s)]"))

(fn transcript-line [block]
  (if (= block.kind :text)
      block.text
      (= block.kind :reasoning)
      (render-reasoning block.text)
      (= block.kind :tool)
      (.. "[tool " block.name " (" block.status ")] " block.summary)
      (= block.kind :patch)
      (patch-line block)
      (= block.kind :step)
      nil
      (.. "[" block.part-type "]")))

(fn compose-transcript [messages]
  (local out [])
  (each [_ message (ipairs (if messages messages []))]
    (local info (if message.info message.info {}))
    (local role (if info.role (tostring info.role) "?"))
    (local model (if info.modelID (tostring info.modelID) ""))
    (local provider (if info.providerID (tostring info.providerID) ""))
    (local model-label
      (if (> (length model) 0)
          (.. " (" model (if (> (length provider) 0) (.. " via " provider) "") ")")
          ""))
    (table.insert out (.. "## " role model-label))
    (when info.system
      (table.insert out (.. "[system prompt: " (tostring (length (tostring info.system))) " chars — see the message node for the full text]")))
    (each [_ block (ipairs (project-message message))]
      (local line (transcript-line block))
      (when line
        (table.insert out line))))
  (if (= (length out) 0) "(no messages)" (table.concat out "\n")))

(fn first-content-label [message]
  (local blocks (project-message message))
  (var label nil)
  (each [_ block (ipairs blocks)]
    (when (and (not label) (= block.kind :text))
      (set label block.text)))
  (each [_ block (ipairs blocks)]
    (when (and (not label) (= block.kind :reasoning))
      (set label block.text)))
  (each [_ block (ipairs blocks)]
    (when (and (not label) (= block.kind :tool))
      (set label (.. "[tool " block.name "] " block.summary))))
  (each [_ block (ipairs blocks)]
    (when (not label)
      (set label (.. "[" (tostring block.kind) "]"))))
  (if label label "(no content)"))

(fn first-line [text]
  (local nl (string.find text "\n" 1 true))
  (if nl (string.sub text 1 (- nl 1)) text))

(fn tool-row-body [part]
  (local state (if part.state part.state {}))
  (.. (if part.tool (tostring part.tool) "tool")
      " (" (tostring (if state.status state.status "?")) ")"
      (if state.title (.. " " (tostring state.title)) "")))

(fn part-row-body [part ptype]
  (if (and (= ptype "text") part.text)
      (if (> (length part.text) 0) part.text "(empty text)")
      (and (= ptype "reasoning") part.text)
      (if (> (length part.text) 0) part.text "(empty reasoning)")
      (= ptype "tool")
      (tool-row-body part)
      (= ptype "patch")
      (.. "patch: " (tostring (length (if part.files part.files []))) " file(s)")
      ptype))

(fn part-row-label [part]
  ;; One-line summary of a raw part for parts-list rows: first line of the
  ;; first content, truncated by the shared utility.
  (local ptype (if (and part part.type) (tostring part.type) "part"))
  (truncate-with-ellipsis (first-line (part-row-body part ptype)) 100))

(fn message-label [message]
  (local info (if message.info message.info {}))
  (local role (if info.role (tostring info.role) "?"))
  (local content (truncate-with-ellipsis (first-line (first-content-label message)) 100))
  (.. role ": " content))

{:project-part project-part
 :project-message project-message
 :compose-transcript compose-transcript
 :transcript-line transcript-line
 :message-label message-label
 :part-row-label part-row-label}
