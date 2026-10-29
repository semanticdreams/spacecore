# OpenCode presentation-island relationship edges

## Scope and evidence

- Controller/workflow: `live-dev`, branch `live-dev`.
- Batch source/base: `4f607d36cfcb5031b669e847d8c7cf1be8d0d311` (freshly fetched
  `origin/main`, safely merged before edits). Initial worktree was clean.
- User report: opening a session's Messages reveals an ordered presentation
  island but no collection-to-message edges; clicking individual rows adds them.
- Verified the sole current checkout app in manual mode, ready and not faulted,
  generation 1. Read-only inspection found one ready messages collection with
  two island members, zero outgoing edges, and two missing member edges.
- `opencode-common.fnl:166-191` resolves island members without adding edges.
  `opencode-session-messages.fnl:98-107` adds a `message` edge on row activation.
  The parts projection has the same discrepancy (`open-part`, label `part`).
- `test-opencode-map-lifecycle.fnl:53` explicitly expects zero edges after
  enumeration. That expectation conflicts with the user's requested behavior.
- Islands remain presentation-only; graph-map topology remains separate. No
  changes to domain data, graph core, or generic island presenters are intended.
- Diagnostic script initially used unavailable `cjson`, then nonexistent
  `json.encode`; inspection of `json-utils.fnl` established `json.dumps` as the
  supported serializer. Both failed queries were read-only; the corrected query
  produced the counts above. No app refresh/recovery had occurred at this stage.

## Bounded design consultation (completed before implementation)

Candidate direction for GLM assessment: enumeration should materialize the same
explicit display edges as row activation, using `message`/`part` labels. Reuse
graph-map deduplication and persistence, retaining user-materialized topology
independently of island membership (as row-created edges already behave).
Preserve current publication/install/stale-data barriers and saved island state.

Advisor assignment identity: task `opencode-island-edges-diagnosis`, original
author `debug-advisor`, controller `live-dev`, branch `live-dev`,
source snapshot/base/head `4f607d36cfcb5031b669e847d8c7cf1be8d0d311` plus only
the diagnostic script and this ledger; mode read-only diagnostic/design question.
`correction_used=0`. Original author session `ses_e79192056ffeOWXmPHniiQZZ0f`.
The original single-JSON delivery was validated against the declared advisor
schema and unchanged assignment/source scope: eligible for normal handling,
`verdict=needs_consultation`, not approval. Original payload remains in the
retained author session; no correction/redelivery was needed.

### GLM proposal and GPT critique

GLM proposed ordinary explicit `message`/`part` edges in the shared publisher,
owner-supplied labels, existing GraphMap creation/persistence semantics, no
island-owned cleanup, and unchanged leaf-hydration/publication barriers.

Expert session `ses_e791827f0ffeuvsz3JoHx86443` answered the single bounded
enumeration-edge question after inspecting original sources. It supported the
ownership boundary but identified two material qualifications:

1. `GraphMap:add-edge` deduplicates cardinality but replaces existing explicit
   edge objects/metadata and emits notifications on repeated adds. Its identity
   excludes labels. The unit fake models different deduplication behavior.
2. Both member resolution and edge notification execute synchronous listeners.
   Entry guards alone cannot prevent a superseded pass from remounting a removed
   owner or publishing an obsolete island after reentrant changes.

Reconciliation direction (before dependent implementation): preserve any existing
explicit endpoint edge unchanged during enumeration, using the same endpoint-key
lookup pattern as `list-entity.fnl:158-160`; create only missing edges through
`GraphMap:add-edge`. Resolve the full member set before adding any edges. Recheck
full eligibility (active, ready, current mounted owner, no topology installation,
fresh/error-free snapshot) and desired-membership identity after callback-producing
steps and on every drain iteration. Abort superseded passes; drain only an eligible
latest request. Preserve explicit errors and resetting the syncing flag; publication
is not transactional and already-authored edges are not rolled back. Actual endpoint
removal still prunes incident edges; snapshot/island membership shrink retains them.
Correct the unit fake's endpoint-key lookup to reflect the real map, and use real-map
tests for callback behavior and metadata retention. The original GLM advisor's
substantive follow-up (same session and source range) returned valid ordinary JSON
`verdict=confirmed`, agreeing with this reconciliation against the cited original
sources. `correction_used=0` remains unchanged. This confirms the diagnosis and
bounded design direction, not implementation correctness or integration approval.

## Implementation and validation

- Shared enumeration now accepts the explicit owner-supplied `message`/`part`
  edge label, resolves the full member set first, creates missing endpoint edges
  through `GraphMap:add-edge`, then publishes the presentation island.
- Existing edges retain their objects, labels, colors, and options during
  enumeration without redundant edge notifications. Existing row-click behavior
  is unchanged. Snapshot/island membership removal retains explicit topology;
  actual node removal prunes incident edges as before.
- Publication rechecks current owner, ready/fresh snapshot, topology barrier and
  desired pass identity across synchronous callbacks. Superseded passes stop;
  removal/replacement cannot resurrect old owners. Errors propagate and clear
  the syncing flag. Resolution failure authors no prefix of edges; notification
  failure retains already-authored edges, with later recompute converging.
- Unit graph helper now uses the real map's endpoint-only identity, replacement
  semantics and canonical target keys. Generic GraphMap/core/presenters and
  owning domain records were not changed.
- RED: touched-test `tools.fennel-check` and explicit-file constraints passed;
  `tests.test-opencode-map-lifecycle:main` then failed nine cases before the fix,
  including the exact missing `messages->message` edge and reentrant removal.
- GREEN, in order, using native Space runtime and standard isolated test env
  (`SPACE_DISABLE_AUDIO=1`, absolute checkout asset/macro paths,
  `XDG_DATA_HOME=/tmp/space/tests/xdg-data`, `SKIP_KEYRING_TESTS=1`):
  1. `./build/space -m tools.fennel-check:main -- --target files --file <path>`
     over the five touched Fennel files: pass, 0 diagnostics.
  2. `./build/space -m constraints.runner:main -- --target files --file <path>`
     over the same five files: pass, 0 diagnostics.
  3. `./build/space -m tests.test-opencode-map-lifecycle:main`: 12 tests passed,
     including synchronous/deferred messages and parts edges, row deduplication,
     existing metadata/event preservation, append/shrink/empty, removal,
     restore/replacement, freshness/install guards, reentrant
     invalidation/supersession/removal/replacement, and failure recovery.
  4. Eight related modules passed, 103 tests total: `test-opencode-sessions-graph`
     (41), `test-opencode-stream-protocol` (3), `test-opencode-adapter-contracts`
     (5), `test-opencode-live-lifecycle` (6), `test-opencode-info-metadata` (3),
     `test-opencode-view-refresh` (8), `test-opencode-map-lifecycle` (12), and
     `test-opencode-message-graph` (25), invoked as `tests.<module>:main`.
     The sessions suite deliberately exercises malformed SSE and emits its
     expected parse warning; it passed.
  5. `bash -n scripts/remote-control-debug.sh` and `git diff --check`: pass.
- Constraint impact: passed unchanged; regression tests, rather than structural
  constraints, catch the missing-edge contract. Focused coverage is proportional
  to this OpenCode projection-only change; no native build/full suite needed.

## Live refresh and verification

- `python3 scripts/live_dev.py reload --repo-root .`: succeeded, request 2,
  generation 1 → 2, no rollback, no recovery required.
- Immediate root status was ready, manual, not faulted. The first graph query
  briefly saw the collection unavailable while its session snapshot was being
  reacquired; this was not a failed root reload. Subsequent read-only inspection
  without another reload/restart found the parent and collection ready.
- Latest inspection: **2 island members, 2 outgoing edges, 0 missing edges,
  2 renderer edge records**. The same open graph's missing connections are now
  present without clicking the individual message rows.
- `python3 scripts/live_dev.py status --repo-root . --request-id 2` independently
  confirmed retained operation success. No failed reload or restart occurred.
- Self-reviewed the complete diff and scoped staging. Local checkpoint only;
  publication/integration and whole-branch wrap-up review are not authorized.
