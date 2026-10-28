# OpenCode session exposure through the graph — full roadmap design

## Status

Reviewed by the expert (2026-10-26, consultation recorded in-session); the
reconciliation below is authoritative where it supersedes earlier sections.
Implementation proceeds stepwise: A → C → E/F → D. D additionally requires the
SSE evidence captures listed at the end.

## Context

`builtin-graph-opencode-sessions` already exposes OpenCode-owned sessions as
read-only graph nodes: `opencode-sessions` list root, `opencode-session:<id>`
adapter (metadata, current server config, bounded read-only transcript with
roles and `[thinking]` markers), lazy fetch through the app's OpenCode client,
generation-guarded responses, explicit state machine
(idle/loading/ready/unavailable/not-found). Code runs record
`opencode-session:<id>` artifacts automatically. This design extends the
exposure to subagent trees, per-message browsing, abort, config, and live
streaming without reworking v1.

## Invariants (all steps)

1. **Ownership**: the OpenCode server owns all session data. Space stores only
   ephemeral snapshots in node adapters and artifact references in run records.
   New node types follow the same adapter pattern; no Space-side session store.
2. **Identity**: graph keys address the app's current OpenCode backing server
   (the bridge data dir). Adapters resolve the client at fetch time, so provider
   replacement (`app.agent-providers.refresh-opencode`) is followed
   automatically; ids that no longer resolve surface explicit `not-found`, never
   silent deletion. Outages surface `unavailable` and never masquerade as
   deletion (hydration prunes only unresolved keys, so loaders always resolve
   well-formed keys).
3. **Key charset**: ids are `[A-Za-z0-9_-]` (`url-safe-id?` in
   `graph/nodes/opencode-common.fnl`). `/` is therefore safe as an intra-key
   separator and `:` is reserved as the scheme separator.
4. **Read-only default**: browsing never mutates. The only mutating action in
   this roadmap is abort (E), which is explicit and user-initiated.
5. **Failure surfacing**: per-part error fields and the existing state machine;
   no silent fallbacks, no dropped content (unknown part types stay visible).

## A — session trees (children)

Children are sessions. No new scheme: the session node gains an
**Expand subagent sessions** action (`GET /session/<id>/children`, endpoint
already wrapped in `llm/providers/opencode/session.fnl`). Each child resolves
`opencode-session:<child-id>` through the graph and adds a parent→child edge
labeled `subagent`.

- Fetch is generation-guarded like other parts; failure surfaces as an explicit
  `children-error` field on the node (children are additive content, so a
  children failure does not demote the whole session's `ready` state).
- Cycles: parent→child edges are directed; a child session that lists its
  parent among children would create a visual cycle — acceptable in the graph
  (edges are explicit), no extra guard needed. Re-expanding an already
  materialized child reuses `graph:resolve-node` (map-local adapter), so no
  duplicate nodes per map.
- Children metadata (id/title) arrives from the children response; child nodes
  start with that metadata and fetch their own details on mount.

## C — message projection + per-message nodes

**Step C0 (capture) — DONE** (captured live from the app's OpenCode server
across 100 sessions, 2026-10-26):

- Part types observed: `text`, `reasoning`, `step-start`, `step-finish`,
  `tool`, `patch`.
- `text`/`reasoning`: `{id, messageID, sessionID, text, time, type[, metadata]}`.
- `step-start`: `{id, messageID, sessionID, snapshot, type}`;
  `step-finish` adds `{cost, reason, tokens}` — future token/cost surfacing.
- `tool`: `{id, messageID, sessionID, type, tool, callID, state, metadata}`;
  `state = {status, input, output, error, time, title, attachments, metadata}`;
  observed example: `tool=apply_patch, status=completed,
  input={patchText}, output` is a string. `state.status` drives
  running/completed/error presentation; `state.title` is a human label.
- `patch`: `{id, messageID, sessionID, type, files, hash}` — file-change
  parts are distinct from tool parts; `files` element shape still to confirm
  (elements may be plain strings).
- `message.info`: `{role, modelID, providerID, agent, mode, cost, tokens,
  parentID, summary, system, finish, error, path, variant, time, tools}` —
  `parentID` relates to subagent structure and may enrich the session tree
  later.

Projection rules from the capture: `text`/`reasoning` as before; `tool`
blocks carry `name = part.tool`, `status = part.state.status`,
`summary = part.state.title` (fallback tool name), `detail` = serialized
`{tool, callID, input, output, error}`; `patch` blocks are file-change
blocks (`detail` = serialized `{files, hash}`); `step-start`/`step-finish`
collapse to nothing in the transcript (noise) but remain available to
message nodes (tokens/cost); anything else stays `:unknown` and visible.

**Projection module** (`graph/nodes/opencode-parts.fnl`): project a message's
`parts` into an ordered block list:

- `{:kind :text :text}` — text content
- `{:kind :reasoning :text}` — reasoning/thinking
- `{:kind :tool :name :summary :detail}` — tool call/result; `name`/`summary`
  from captured schema; `detail` is the full serialized part (JSON) for deep
  views; conservative fallback when fields are missing: kind `:tool-unknown`
  with the serialized part as detail.
- `{:kind :unknown :part-type :detail}` — anything else, always visible.

Consumers:
1. **Transcript composition** (`compose-transcript`) switches to the projection
   and renders one thin line per tool block
   (`[tool <name>] <summary>`), keeping the transcript a skim surface.
2. **Message nodes**: new scheme
   `opencode-session-message:<session-id>/<message-id>`. Loader: synchronous,
   network-free, requires both ids url-safe; resolves to a node that projects
   its parent session's already-fetched messages (message nodes are
   projections of the session adapter's snapshot — no separate fetch; a
   `stale` state appears if the session snapshot lacks that message id, with
   an explicit Refresh-session path).
3. **Materialization boundary**: the session view gains a message list
   (ListView, same as the sessions root) where each row opens one message node
   + edge via `graph:resolve-node`/`add-edge`. No automatic N-node
   materialization. Message node views render the projected blocks: text and
   reasoning in a read-only VirtualInput, tool blocks with name + summary plus
   the full `detail` behind an external-editor open (viewer semantics,
   content discarded — same contract as the code-run payload).
4. Message nodes drop with the map; they hold no fetch state and subscribe to
   nothing (pure projections), so teardown is trivial.

**Sequencing note**: per-message fetch does not exist in the OpenCode API
(the whole transcript arrives in one `GET /session/<id>/message`), which is why
message nodes are projections. If lazy per-message loading becomes necessary
for very long sessions, that is an OpenCode wrapper/API question, explicitly
out of scope here.

## E — abort (first mutating action)

Session node action **Abort Session** → `POST /session/<id>/abort`
(already wrapped in the SDK), followed by an automatic `fetch` refresh.

- Abort is user-initiated and explicit; no confirmation dialog (consistent
  with Delete Run, which has none).
- The action is always offered: OpenCode tolerates aborting non-running
  sessions (idempotent no-op); the response surfaces in run output via the
  node's error field on failure.
- This action does not change the read-only contract of *views*; it mutates
  server state through the owning system's own API, which is the owner-sanctioned
  mutation path.

## F — config browsing node

New scheme `opencode-config` (exact key). Node over `GET /config` and
`GET /config/providers`: two sections rendered as read-only text
(serialized JSON pretty-printed), same state machine, explicit deadlines.
Navigation: the `opencode-sessions` root and session views link to it
(config section becomes an action/link: `graph:resolve-node "opencode-config"`
+ edge). Server config stays labeled *current server config* — it is not
session-effective configuration and must not be presented as historical.

## D — live sessions (SSE) — contract now, implementation last

`llm/providers/opencode/events.fnl` + `sse.fnl` exist but currently
log-and-discard malformed events and end silently on normal stream completion.
Before any streaming code:

1. **Snapshot/subscribe ordering**: fetch snapshot → subscribe → replay/reorder:
   events buffered during snapshot fetch apply after the snapshot, deduplicated
   by message id + monotonic event ordering when available.
2. **Gap detection**: OpenCode SSE event identity must be established from a
   real capture (step D0). Without a reliable sequence number, the contract
   degrades to "reconnect = full snapshot refresh", which is acceptable and
   simpler: reconnects trigger a session refetch, no event replay.
3. **Reconnect**: bounded exponential backoff with a surfaced connection state
   (`live/degraded/reconnecting/off`), never silent.
4. **Ownership**: the session node owns the subscription (one per node),
   unsubscribe on drop, coexists with Refresh (refresh re-subscribes),
   generation-guarded like all other responses.
5. **Scope**: live updates apply to the session node's own data (messages,
   transcript); the projection layer renders incremental blocks.

## Deletion (user, 2026-10-27)

Session nodes expose a Delete Session action (right-click/point menu and
expanded-card menu), following the abort contract: explicit
pending/acknowledged/failed state with duplicate suppression and no auto-retry.
Acknowledged deletion (server-owned `DELETE /session/<id>` — messages go with
the session) removes the node from its maps; the run's
`opencode-session:<id>` artifact reference survives as a provenance link, and
re-materializing a deleted session surfaces an explicit not-found. Captured:
deleting a missing session returns 200/true (idempotent).

## Sequencing

1. **A** (children expansion) — small, independent.
2. **C** (capture → projection → transcript thin lines → message list + nodes).
3. **E + F** (abort rider + config node) — small, independent.
4. **D** (live) — only after expert review of this design, plus the D0 capture.

## Validation per step

Focused suites for each touched surface (loader network-freedom, state
transitions, projection fixtures, stale-generation behavior, teardown), plus
`fennel-check`, `make constraints`, live reload, and RC smoke tests against the
running app. The scheme-coverage test list grows with each new scheme
(`opencode-session-message`, `opencode-config`).

## Open questions for expert review

Resolved by the 2026-10-26 expert review — see "Expert reconciliation" below.

## Expert reconciliation (2026-10-26)

Corrections that supersede earlier sections where they conflict:

1. **API premise corrected (C.2)**: the installed OpenCode SDK 1.18.8 exposes
   `GET /session/{id}/message/{messageID}` and message-list query options
   (limits, before cursor). The Fennel wrapper lacks them — that is a wrapper
   gap, not proof the server lacks them. Message nodes may therefore use
   per-message fetch later; the snapshot-projection first version stands, and
   deployed-server behavior must be verified with a capture before relying on
   it.
2. **Tree edge semantics (A)**: parent→child edges mean *user-materialized
   relationships observed in a snapshot*, not authoritative current parentage.
   Re-parenting server-side leaves the old edge (expansion only adds edges);
   this is intended. Deleted children surface as explicit `not-found` adapters.
3. **Message-node update lifetime (C.2)**: message views must define parent
   acquisition on mount (re-resolve the parent session key; create the session
   node if absent), map-local lookup/replacement, and how an open message view
   observes session refresh. Absence from a successful snapshot is shown
   explicitly, distinct from deletion/unavailable.
4. **Abort (E) contract**: do not gate visibility on message completion
   metadata; explicit action with finite deadline, separate pending/result/
   error state, duplicate-click suppression, captured client/session target;
   never auto-retry an ambiguous timed-out POST; refresh only after
   acknowledged success; keep abort outcome separate from refresh outcome; the
   client returns scalar JSON bodies as raw strings, so `response.data`
   truthiness alone must not decide success. Requires captures for
   active/idle/repeated/missing-session abort responses before implementation.
5. **SSE (D) contract**: "reconnect = full snapshot refresh" is acceptable;
   event replay is not required. But ordering must be **subscribe-then-
   snapshot** (fetch-then-subscribe would lose pre-subscription events
   permanently); resynchronize on parse/schema failures too, not only
   transport reconnects; reconnect reacquires the current provider. The SSE
   plumbing has known defects to fix first: malformed JSON is logged and
   dropped, scalar JSON triggers table mutation, SSE envelope IDs are
   discarded, chunk-local CRLF normalization can invent blank-line
   boundaries, and normal completion ends silently.
6. **Provider identity invariant weakened**: the bridge data dir is a
   *configuration* root (XDG_CONFIG_HOME / OPENCODE_CONFIG_CONTENT), not an
   OpenCode storage root; storage continuity across `refresh-opencode` is
   plausible but unproven. Adapters follow the current client at next fetch
   (implemented); automatic snapshot/subscription migration on provider
   replacement is NOT implemented. Do not silently change storage to make the
   invariant true.
7. **Inherited defects — fixed 2026-10-26** (validated in
   test-opencode-sessions-graph): reentrant-fetch generation race
   (generation now captured once by fetch and passed to fetch-part!);
   post-drop fetch now fails loudly; transcript refresh marks old messages
   `messages-stale` until the current generation's transcript settles;
   sessions-list placeholder rows render as text, not actionable buttons;
   ListView pagination actually enabled (`paginate true`); tool/patch
   projections are lossless (`detail` serializes the full original part);
   the session view's subagent count reads the correct field.

Remaining evidence tasks: deployed server version + supported message
endpoints; abort responses for active and repeated-abort sessions; SSE
framing/lifecycle capture; storage continuity across provider refresh.

Captured (2026-10-26, missing-session probe): `POST /session/<missing>/abort`
returns `200 OK` with boolean body `true` — the server treats aborting a
nonexistent session as an idempotent success, which is why the Abort action is
always offered and why "acknowledged" records the raw body rather than claiming
observed termination.

## Follow-on decision (user, 2026-10-27): expanded cards render node views

The graph view's expanded card presentation now builds the node's `view`
instead of its `preview` (universal, all node types; `node.view` falling back
to `node.preview` for nodes without a view factory). Previews remain available
for inline embedding in other widgets. The preview/expanded toggle and its
persistence are unchanged — only the widget rendered while expanded swapped.
Performance implications deferred until observed.

## G — message hub restructure (message → parts/info → part nodes), 2026-10-27

Product direction: message node views become projection hubs instead of
dumped text. Scalar `info` fields render directly; complex items (parts,
system, tools, time, path, error detail) render as clickable rows that
materialize their own projection child node on click. A parts node lists
raw parts; each part materializes its own part node.

**Proposed taxonomy (GLM):** new schemes `opencode-session-message-parts:<s>/<m>`,
`opencode-session-message-part:<s>/<m>/<part-id>`, `opencode-session-message-info:<s>/<m>/<field>`;
two-level projection chain (session → message → parts/part/info), click-only
materialization via `graph:resolve-node` + `add-edge` (no automatic fan-out),
part nodes keyed by raw `part.id`, `:absent` on disappearance from a successful
snapshot, tool input/output/error as leaf lossless inputs.

**Expert reconciliation (expert-advisor, answered; scope: node taxonomy,
keys, projection ownership, materialization trigger, stale semantics):**
Decomposition sound; lifecycle contract must not be copied literally from the
message adapter. Accepted findings and resolutions:

1. Message node never calls captured `base.mount` → `self.graph` unset;
   hub navigation impossible. **Fix:** call base.mount in the message node
   mount (and in every new projection node).
2. Message state machine can present stale content as current (metadata and
   transcript settle independently; `messages-stale`/`transcript-error`
   ignored; removed messages retained in `self.message`). **Fix:** propagate
   parent freshness (`transcript-error`, `messages-stale`) through the
   projection; retained payload shown only with explicit last-known/stale
   labeling; only a successful snapshot establishes current absence.
3. Parent adapter replacement/removal leaves children bound to a dead
   adapter. **Fix:** projection children observe `graph` node-replaced
   (`{old,new}`) and node-removed (`{nodes,...}`) signals, rebind to the
   replacement map-local adapter, and show explicit non-ready state on
   parent removal (no automatic parent recreation).
4. Part identity across snapshots unproven; projections discard ids.
   **Fix:** parts nodes enumerate raw `message.parts` by validated unique
   url-safe `part.id` (not block indexes, snippets, callID, or fabricated
   fallbacks); parts without a valid id render non-clickable; a removed id
   stays `:absent` and may return to `:ready` if the same id reappears.
5. Loaders must parse exact segment counts, validate ids, whitelist canonical
   info-field names, and construct well-formed references even when data is
   absent; standalone hydration acquires ancestors (session → message) via
   the projection mount chain without materializing siblings or auto-adding
   edges. **Accepted** — matches the message-loader pattern.
6. Leaf separation must not regress losslessness. **Fix:** every part node
   carries a complete "Raw part" input (full original part) alongside
   structured content inputs; table-valued info fields (tokens) serialize
   structured, never assumed string.
7. Session SSE handling ignores relevant events during `:loading` (events
   after transcript response but before metadata settle can be lost).
   **Fix at session owner (separate commit):** pending-invalidation — events
   observed while loading schedule exactly one follow-up refresh after the
   in-flight fetch settles; children never fetch independently.

Validation additions required: transcript/metadata settle orders, failed
refresh with retained data, part/field disappearance+reappearance, parent
replacement/removal rebinding, repeated-click deduplication, child-only
hydration, malformed keys, empty/unknown parts, complete tool metadata.

## H — automatic ordered-list islands for messages and parts, 2026-10-27

Product decision: messages and parts render as ordered-list islands
(existing list-entity machinery, ordered-list kind as-is), with automatic
creation and automatic membership updates, at both levels: the messages
node owns an island of message nodes; the parts node owns an island of
part nodes.

**Proposed contract (GLM):** projection turns :ready with >=1 valid entry →
upsert deterministic island ("opencode-messages:<sid>",
"opencode-parts:<sid>/<mid>"); recompute re-syncs members; empty/drop/
parent-removal tears down; members are keys hydrated by the map.

**Expert reconciliation (answered); corrections adopted:**
1. Island publication does NOT hydrate members (island-host resolves via
   map lookup and asserts on missing nodes). Every valid member is resolved
   into the mounted map BEFORE publishing; resolution failure is explicit;
   zero valid members removes any existing island. Snapshot order is
   preserved; validated-ids rows without valid? are never members.
2. Membership updates preserve presentation state: upserts omit :state
   (GraphMap.update-island preserves state when omitted); initial state
   (snap-back, spacing 24, origin position) only on creation. Live
   append/remove during a drag can reconcile positions synchronously —
   documented accepted behavior, not silently assumed away.
3. Teardown lifetime: GraphMap unmounts (clearing self.graph) before drop
   on the normal removal path, so projection cleanup retains a separate
   mounted-graph reference; island removal is idempotent. Pruning by
   map cleanup is not owner cleanup; the projection owns its island while
   mounted and removes it on :absent/:unavailable/:not-found/parent-removed
   (never inferring membership from retained payloads). :loading/:idle keep
   the island (refresh cycles must not reset user positions).
4. Absence propagation: parent-availability now maps parent :absent to a
   projection :absent so a removed message cannot leave its parts
   projection :ready with retained parts (stale island).
5. Restoration policy (ownerless restored islands, restore/reference
   duplicate ids): adopt-if-owner-mounts — a projection finding its
   deterministic island already present adopts it (members re-synced,
   saved position/state preserved); ownerless islands remain static saved
   presentations until their owner mounts. No silent deletion of saved
   state.
6. Known cost: per-message recompute scans the full message array (O(N²)
   across a materialized session per notification); acceptable at current
   session sizes, revisit with an id-index if large sessions hurt.
Click-only materialization is superseded for these children by the
explicit automatic-islands product decision (bounded OpenCode exception).

## I — review corrections: snapshot lifetime and complete metadata, 2026-10-28

The GLM proposals and bounded expert critiques are reconciled as follows:

- The live owner uses subscription epochs, permanent drop guards, cancelled
  delayed retries (250/500/1000 ms, three automatic retries per consecutive
  outage) and explicit stream errors. A received event resets the outage budget;
  subscription submission alone does not prove server readiness. Explicit
  Refresh Session and acknowledged abort may restart a stopped subscription.
- Snapshot invalidations coalesce until **both** session metadata and transcript
  responses settle, in either order. Optional configuration and children do not
  hold the barrier. Duplicate, obsolete and post-drop responses cannot settle a
  newer generation. No client-side SSE event replay becomes domain truth.
- Saved topology installation suppresses derived island hydration/teardown until
  its success signal; same-key adapter replacement preserves island presentation.
  Owner publication precedes hydration, and reentrant membership sync coalesces.
- List projections compare ordered identity/label/action/eligibility fields,
  updating current click payloads even when their display is unchanged. Invalid
  duplicate rows remain inert; irrelevant emissions preserve pagination.
- Info admission is no longer a fixed whitelist: system/tools/time/path/error
  always get info rows, other tables get info rows, and every remaining present
  scalar renders inline. Canonical labels/order affect presentation only. Unknown
  fields are retained, false/zero/empty string are present, and only nil is absent.
- `Parts` and an info property named `parts` have disjoint row identities/actions.
  The field segment uses ASCII alphanumeric/hyphen bytes literally, uppercase
  percent escapes for every other byte, `~` for an empty field and `%7E` for a
  literal tilde. Loaders decode exactly once and accept only canonical round-trip
  forms; session/message id restrictions are unchanged. Existing five field keys
  remain unchanged, without aliases. Presence/type changes do not invalidate a
  retained field reference. Strings render directly; structured system values
  serialize as JSON instead of displaying a Lua table identity.
- Full runs retain a separate readonly Run/Code/Kernel/Elapsed/Completion metadata
  input above the independent Output/Result/Error inputs. Metadata and each outcome
  cache text independently; output remains the tail-following section. Previews
  are unchanged. Full message hubs allocate no hidden transcript input.

“Lossless” refers to the decoded snapshot, not original wire bytes: the existing
JSON binding maps null to nil and does not preserve empty-object/empty-array
distinction. These corrections do not change that representation contract.
