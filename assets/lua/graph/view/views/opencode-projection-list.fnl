(local ListView (require :list-view))
(local Button (require :button))

(fn same-row? [left right]
  (and (= left.key right.key) (= left.label right.label)
       (= left.action right.action) (= left.valid? right.valid?)
       (= left.placeholder right.placeholder)))

(fn same-rows? [left right]
  (if (not left) false
      (not= (length left) (length right)) false
      (do
        (var same? true)
        (each [i row (ipairs right)]
          (when (not (same-row? (. left i) row)) (set same? false)))
        same?)))

;; Own a ListView and its current row lookup. Presentation equality never keeps
;; stale payloads in buttons; invalid rows have disjoint keys and cannot open.
(fn ProjectionList [options]
  (local rows-for-node (assert options.rows "projection list requires rows"))
  (local activate (assert options.activate "projection list requires activate"))
  (fn build [ctx]
    (var current {})
    (var applied nil)
    (var dropped? false)
    (fn row-builder [row child-ctx]
      (fn on-click [_button _event]
        (local latest (. current row.key))
        (when (and (not dropped?) latest latest.valid?) (activate latest)))
      ((Button {:text row.label :variant :ghost :on-click on-click}) child-ctx))
    (local list ((ListView {:items [] :name options.name :show-head false
                            :items-per-page 8 :paginate options.paginate?
                            :builder row-builder}) ctx))
    (fn refresh! [_self]
      (assert (not dropped?) "projection list refresh after drop")
      (local rows (rows-for-node))
      (local lookup {})
      (each [_ row (ipairs rows)]
        (assert row.key "projection row requires a key")
        (assert (not (. lookup row.key)) "projection row keys must be unique")
        (tset lookup row.key row))
      (set current lookup)
      (when (not (same-rows? applied rows)) (list:set-items rows))
      (set applied rows))
    (fn drop [_self] (set dropped? true) (set current {}) (list:drop))
    (refresh! nil)
    {:layout list.layout :refresh! refresh! :drop drop}))

ProjectionList
