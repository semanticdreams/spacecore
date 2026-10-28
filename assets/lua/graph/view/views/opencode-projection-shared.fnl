(local VirtualInput (require :virtual-input))
(local LazyTextSource (require :lazy-text-source))
(local LazyTextBuffer (require :lazy-text-buffer))

;; Shared scaffolding for the OpenCode projection node views (parts, part,
;; info). They all render read-only lossless inputs fed from a parent
;; adapter's snapshot.

(fn status-line [node]
  (if (= node.state :loading)
      "Waiting for the parent snapshot..."
      (= node.state :unavailable)
      (.. "Unavailable: " (if node.error node.error "unknown error"))
      (= node.state :not-found)
      (.. "Not found: " (if node.error node.error "unknown error"))
      (= node.state :absent)
      (.. "Not in the current snapshot: " (if node.error node.error "unknown reason"))
      (= node.state :idle)
      "Parent not materialized yet"
      "Ready"))

(fn make-detail-input [ctx name]
  ((VirtualInput {:buffer (LazyTextBuffer {:source (LazyTextSource.string "")})
                  :line-count 10
                  :column-count 90
                  :editable? false
                  :name name})
   ctx))

(fn swap-buffer [input text last]
  ;; set-buffer! swap with per-input identical-content skip; returns the
  ;; value to store as the new last-seen content.
  (when (not= text last)
    (input:set-buffer!
      (LazyTextBuffer {:source (LazyTextSource.string text)}))
    (input:refresh-viewport))
  text)

{:status-line status-line
 :make-detail-input make-detail-input
 :swap-buffer swap-buffer}
