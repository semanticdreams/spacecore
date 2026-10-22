;; Fixed fresh-process persistence probe; deliberately not registered in tests.fast.
(local Strings (require :entities/string))
(local Links (require :entities/link))
(local fs (require :fs))
(local text-id "wine-persistent-text")
(local link-id "wine-persistent-link")
(local final-text "  after 雪\r\n\n")

(fn store-options []
  ;; Test-only fixed external root. The owning parent creates it exclusively
  ;; beneath verified TEMP; do not use Windows known-folder defaults or create
  ;; an absent root here. Both fresh processes use ordinary real storage.
  (local temporary (os.getenv :SPACE_WINE_WINDOWS_TMP))
  (assert (and temporary (> (# temporary) 0)) "owned TEMP handoff required")
  (local base-dir (fs.join-path temporary "space-record-publication-store"))
  (assert (. (fs.stat base-dir) :is-dir) "parent-owned store root required")
  {: base-dir})

(fn assert-revision [revision]
  (assert (and (= (type revision) :string) (<= 1 (# revision) 512))
          "probe requires a stored revision"))

(fn assert-text [store entity value revision]
  (assert (= entity.id text-id) "text identity mismatch")
  (assert (= (store:get-entity text-id) entity) "text cache must publish before notification")
  (assert (= entity.value value) "text cache content mismatch")
  (assert-revision entity.revision)
  (assert (= entity.revision revision) "text cache revision mismatch")
  (local durable (store:read-text text-id))
  (assert (= durable.id text-id) "durable text identity mismatch")
  (assert (= durable.value value) "durable text bytes mismatch")
  (assert (= durable.revision revision) "durable text revision mismatch"))

(fn assert-link [store entity old-revision new-revision value]
  (assert (= entity.id link-id) "link identity mismatch")
  (assert (= (string.sub entity.source-key 1 9) "identity:") "source must be normalized")
  (assert (= (string.sub entity.target-key 1 9) "identity:") "target must be normalized")
  (assert (= (store.identity-store:resolve-key entity.source-key) "source") "source terminal mismatch")
  (assert (= (store.identity-store:resolve-key entity.target-key) "target") "target terminal mismatch")
  (assert (= entity.metadata.old-revision old-revision) "stored old revision mismatch")
  (assert (= entity.metadata.new-revision new-revision) "stored new revision mismatch")
  (assert (= entity.metadata.value value) "link metadata value mismatch")
  (var fields 0)
  (each [_ _value (pairs entity.metadata)] (set fields (+ fields 1)))
  (assert (= fields (if new-revision 3 2)) "link metadata must contain exactly the expected fields"))

(fn assert-link-publication [store entity old-revision new-revision value]
  (assert (= (store:get-entity link-id) entity) "link cache must publish before notification")
  (assert-link store entity old-revision new-revision value)
  (local durable (store:read-link link-id))
  (assert-link store durable old-revision new-revision value)
  (assert (= durable.source-key entity.source-key) "durable source identity mismatch")
  (assert (= durable.target-key entity.target-key) "durable target identity mismatch"))

(fn disconnect-listener [subscription]
  (subscription.signal:disconnect subscription.listener))

(fn with-listeners [subscriptions body]
  (local owned [])
  (fn connected-body []
    (each [_ subscription (ipairs subscriptions)]
      (subscription.signal:connect subscription.listener)
      (table.insert owned subscription))
    (body))
  (local (ok result) (pcall connected-body))
  (var cleanup-failed false)
  ;; Attempt every owned disconnect independently, even after body/cleanup errors.
  (each [_ subscription (ipairs owned)]
    (local (disconnected _err)
      (pcall disconnect-listener subscription))
    (when (not disconnected) (set cleanup-failed true)))
  (when cleanup-failed
    (error (if ok "WINE_RECORD_PUBLICATION_DISCONNECT_FAILED"
                 "WINE_RECORD_PUBLICATION_BODY_AND_DISCONNECT_FAILED") 0))
  (when (not ok) (error result 0))
  result)

(fn write-listeners [strings links observed]
  [{:signal strings.string-entity-created
    :listener (fn [entity]
                (set observed.text-created (+ observed.text-created 1))
                (assert (= observed.text-created 1) "exactly one text creation notification required")
                (assert-text strings entity "before" entity.revision)
                (set observed.text entity))}
   {:signal strings.string-entity-updated
    :listener (fn [entity]
                (set observed.text-updated (+ observed.text-updated 1))
                (assert (= observed.text-updated 1) "exactly one text update notification required")
                (assert (= entity observed.text) "text update must retain held cache identity")
                (assert (not= entity.revision observed.old-revision) "revision must change before notification")
                (assert-text strings entity final-text entity.revision)
                (set observed.new-revision entity.revision))}
   {:signal links.link-entity-created
    :listener (fn [entity]
                (set observed.link-created (+ observed.link-created 1))
                (assert (= observed.link-created 1) "exactly one link creation notification required")
                (assert-link-publication links entity observed.old-revision nil "before")
                (set observed.link entity))}
   {:signal links.link-entity-updated
    :listener (fn [entity]
                (set observed.link-updated (+ observed.link-updated 1))
                (assert (= observed.link-updated 1) "exactly one link update notification required")
                (assert (= entity observed.link) "link update must retain held cache identity")
                (assert-link-publication links entity observed.old-revision observed.new-revision "after"))}])

(fn write-records [strings links observed]
  (local first (strings:create-entity {:id text-id :value "before"}))
  (assert (= first observed.text) "text creation must return the notified cache object")
  ;; replace-text mutates the held entity: retain this token BEFORE the call.
  (local old-revision first.revision)
  (assert-revision old-revision)
  (set observed.old-revision old-revision)
  (local updated (strings:replace-text text-id final-text old-revision))
  (assert-revision updated.revision)
  (assert (not= updated.revision old-revision) "replacement must produce a new revision")
  (assert (= updated.value final-text) "replacement result must preserve exact text")
  (assert (= updated.revision observed.new-revision) "replacement and notification revisions must match")
  (assert-text strings first final-text updated.revision)
  (local link (links:create-entity {:id link-id :source-key "source" :target-key "target"
                                   :metadata {:old-revision old-revision :value "before"}}))
  (assert (= link observed.link) "link creation must return the notified cache object")
  (local updated-link (links:update-entity link-id
                                         {:metadata {:old-revision old-revision
                                                     :new-revision updated.revision :value "after"}}))
  (assert (= updated-link link) "link update must return the same cache object")
  (assert-link-publication links link old-revision updated.revision "after")
  (each [_ count (ipairs [observed.text-created observed.text-updated
                         observed.link-created observed.link-updated])]
    (assert (= count 1) "each ordinary mutation must notify exactly once")))

(fn write-body []
  (local options (store-options))
  (local strings (Strings.StringEntityStore options))
  (local links (Links.LinkEntityStore options))
  (local observed {:text-created 0 :text-updated 0 :link-created 0 :link-updated 0})
  (with-listeners (write-listeners strings links observed)
                  (fn [] (write-records strings links observed))))

(fn assert-stale-refused [strings links text link]
  (local old-revision link.metadata.old-revision)
  (local new-revision link.metadata.new-revision)
  (local before-text (strings:snapshot-entity text-id))
  (local before-link (links:snapshot-entity link-id))
  (local cached-text (strings:serialize-entity text))
  (local cached-link (links:serialize-entity link))
  (local observed {:text 0 :link 0})
  (local subscriptions
    [{:signal strings.string-entity-updated :listener (fn [_] (set observed.text (+ observed.text 1)))}
     {:signal links.link-entity-updated :listener (fn [_] (set observed.link (+ observed.link 1)))}])
  (fn stale-attempt []
    (local (ok err) (pcall strings.replace-text strings text-id "stale" old-revision))
    (assert (not ok) "stale replacement must fail")
    (assert (= (type err) :table) "stale refusal must be structured")
    (assert (= err.code :conflict) "stale refusal must be a conflict")
    (assert (= err.outcome :not-committed) "stale refusal must not commit")
    (assert (= err.current-revision new-revision) "conflict must report the current revision")
    (assert (= (. (strings:snapshot-entity text-id) :bytes) before-text.bytes) "stale text changed disk bytes")
    (assert (= (. (links:snapshot-entity link-id) :bytes) before-link.bytes) "stale text changed link disk bytes")
    (assert (= (strings:get-entity text-id) text) "stale refusal changed text cache identity")
    (assert (= (links:get-entity link-id) link) "stale refusal changed link cache identity")
    (assert (= (strings:serialize-entity text) cached-text) "stale refusal changed text cache content")
    (assert (= (links:serialize-entity link) cached-link) "stale refusal changed link cache content")
    (assert-text strings text final-text new-revision)
    (assert-link-publication links link old-revision new-revision "after")
    (assert (= observed.text 0) "stale replacement must not notify text updates")
    (assert (= observed.link 0) "stale replacement must not notify link updates"))
  (with-listeners subscriptions stale-attempt))

(fn read-body []
  ;; This entry is launched separately: no writer store/cache is retained.
  (local options (store-options))
  (local strings (Strings.StringEntityStore options))
  (local links (Links.LinkEntityStore options))
  (assert (= (next strings.cache) nil) "reader must start with an empty text cache")
  (assert (= (next links.cache) nil) "reader must start with an empty link cache")
  (local text (assert (strings:get-entity text-id) "persisted text must exist"))
  (local link (assert (links:get-entity link-id) "persisted link must exist"))
  (local old-revision link.metadata.old-revision)
  (local new-revision link.metadata.new-revision)
  (assert-revision old-revision)
  (assert-revision new-revision)
  (assert (not= old-revision new-revision) "persisted revisions must differ")
  (assert-text strings text final-text new-revision)
  (assert-link-publication links link old-revision new-revision "after")
  (assert-stale-refused strings links text link))

(fn run-probe [body failure-marker success-marker]
  ;; Protect constructors and cold reads too. Owned scopes finish their complete
  ;; teardown before this returns; discard the underlying error without inspection.
  (local ok (pcall body))
  (when (not ok) (error failure-marker 0))
  (print success-marker))

(fn write []
  (run-probe write-body "WINE_RECORD_PUBLICATION_WRITE_FAILED" "WINE_RECORD_PUBLICATION_WRITE_OK"))

(fn read []
  (run-probe read-body "WINE_RECORD_PUBLICATION_READ_FAILED" "WINE_RECORD_PUBLICATION_READ_OK"))

{: write : read}
