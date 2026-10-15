# Uniform graph capabilities: contract-first slice

## Status and scope correction

This document supersedes the earlier six-method/server-oriented proposal in
this same path. The user approved the smaller design below after a read-only
contract audit. Earlier planning reports are not implementation authority.

Deliver the uniform graph contract and exercise it inside Space's runtime.
Do not build a CLI, HTTP/MCP server, voice interface, additional app runtime,
or transport lifecycle in this change. Those are later consumers, not reasons
to expand this slice. The initial single authority is the running Space process.

## Agreed goals

- Uniform access must not make consumers dispatch on concrete object types.
- Nonvisual consumers are independent of GraphMap and GraphView state.
- Participating graph-view operations use the same domain implementation now,
  rather than leaving a parallel interface to converge later.
- Replacement-style edits reject stale revisions explicitly, for participating
  GUI edits as well as nonvisual edits. No silent overwrite or automatic merge.
- The representative workflow is a project brief with two related notes.
  Strings and link records are its backing implementation, not its public API.
- Demonstrate extensibility with a second, different test-only family.

## Existing boundary and the intended refinement

Graph is an exposure/adaptor layer. Domain systems own objects and persistence.
GraphMap owns materialized topology and interaction context; GraphView owns
runtime visual projection. These ownership boundaries do not change.

Today common graph behavior includes key-loader dispatch, adapter identity,
presentation metadata, and mount/drop lifecycle. Domain access is heterogeneous:
for example, text adapters expose store methods, while filesystem adapters
expose stat/listing and UI-oriented opening methods. Menu actions are executable
callbacks, not a declared nonvisual contract. A capability must not be inferred
from a menu label or arbitrary callback.

Add explicit context-independent capabilities within the existing graph
extension/key-loader boundary. Reuse its registration ownership and cleanup,
not a second family registry or a type-specific external service. Ordinary
visual extensions remain supported without being automatically executable
through the new contract. Do not construct visual adapters to invoke a
nonvisual capability or materialize topology as a side effect of resolution.

## Public contract

Use three generic concepts, named `discover`, `describe`, and `invoke` in the
implementation plan:

1. **Discover entry points.** Return a bounded set of explicitly exposed starting
   references and summaries. Clients need not know concrete key schemes.
2. **Describe an object.** Resolve an opaque reference and return a summary and
   explicitly available capabilities. Each capability has a stable identifier,
   description, declared argument/result shapes, effect (`read` or `write`), and
   revision requirement. Descriptions contain data, not executable closures.
3. **Invoke a capability.** Resolve a key and capability identifier, validate its
   arguments and preconditions, and execute the current registered handler.

Read, search, list relationships, create, and replace content are capabilities,
not additional generic service methods. Different families may expose different
capabilities and data. Uniform access does not imply universal CRUD.

The supported argument/result-description vocabulary must be small, documented,
and actually checked; do not implement a general JSON Schema framework. Results
are detached data suitable for future serialization: no live adapters, callbacks,
view handles, or userdata. References have a uniform opaque key field.

Resolve current registrations for each call. Unload/replacement must invalidate
old behavior; a stale handle cannot remove its replacement. No executable
handler should escape inside a description or be cached by a consumer.

Creation is a discoverable collection/provider capability. Its result contains
the created reference. There is no family-specific method on the generic graph
contract and no consumer-side key-prefix dispatch.

## Representative capabilities and workflow

The initial family supplies enough capabilities to:

1. Discover a searchable text collection and a domain-relationship provider.
2. Find an existing brief by text, obtaining references and short summaries.
3. Describe/read the brief and list its direct domain relationships.
4. Create two notes through the collection's advertised creation capability.
5. Create directed persisted relationships from the brief to each note through
   the relationship provider's advertised capability.
6. Read a note and replace its text with the returned revision.
7. Read back the results and reopen the owning stores to verify persistence.

Domain relationships are not display edges. Discovery roots and collection
membership are not silently reported as persisted relationships. Limit this
example to direct stored links; no identity dereference or recursive traversal.
The first relationship provider validates its supported endpoints internally.

Search and collection reads have bounded pages, deterministic continuation,
and an explicit indication of remaining results. Provider scans have an
examined-record budget, including pages with no matches. No claim of indexed
search or snapshot pagination is made. Content/result budgets and the initial
literal search semantics are specified in the plan, not copied from UI search.
Corrupt/unreadable data is an error, not an empty successful page.

## Shared GUI/domain behavior

Participating GUI actions delegate domain reads and mutations to the same
implementation used by graph capabilities. GUI callbacks retain only their
presentation consequences. In particular, creating a child currently combines
domain creation/linking with revealing it in the containing map; preserve the
visual convenience without requiring a map for its domain operations.

Text editing reads a revision corresponding to the content actually presented
to the editor, and submits that revision when replacing it. A conflict preserves
the attempted edit and surfaces an explicit error; it does not silently retry
with a newly read revision. No new confirmation-dialog or merge-editor product
is part of this slice. Existing callers outside the participating graph UI can
remain on their existing APIs, but their persisted writes must invalidate older
revisions so nonvisual consumers cannot overwrite them unknowingly.

Nonvisual calls do not add map members, write explicit display edges, move nodes,
change focus/selection, open panels, or change projection settings. Existing
store-driven views and derived relationships may reflect underlying changes;
this is shared domain state, not view-state synchronization.

## Consistency and errors

Execution is synchronous on the authority's Lua thread. Opaque revision checks
belong at the owning mutation boundary and cover all successful changes to the
participating text record. Comparison and write do not yield. Timestamps alone
are not revision tokens. Reads of legacy records must produce stable revisions
without rewriting files; subsequent writes produce fresh persisted revisions.

A stale replacement changes neither persisted content nor the cached record,
and returns a conflict with the current revision. Missing objects, unsupported
capabilities, invalid arguments, limits, storage failures, and unavailable
registrations are explicit and distinguishable. Empty success is not failure.

Mutation success must not be reported before the owning store completes its
write. Preserve existing storage formats and exact user text on readback. Keep
necessary persistence fixes local to the participating write paths; do not turn
this into a global filesystem/persistence redesign. If a listener fails after a
write has committed, disclose the committed outcome rather than claiming that
the operation rolled back. Failure handling must not silently compensate an
already committed operation or erase unrelated state.

Each mutation stands alone. The workflow is not a multi-record transaction.
There is no exactly-once retry, automatic merge, external-writer coordination,
distributed synchronization, or power-loss durability guarantee.

## Acceptance and validation

- Run the complete workflow through only discover/describe/invoke and returned
  references/capability metadata, without an active map/view or UI adapter.
- Reopen stores and verify exact text, created references, and link direction.
- Reject an agent edit after a GUI edit, and a participating GUI edit after a
  nonvisual edit; preserve attempted GUI content. Include same-second and
  A-to-B-to-A changes.
- Verify existing creation/reveal conveniences and subscribed label updates.
- Exercise a second test-only family with different arguments/results through
  unchanged generic dispatch; test ownership, unload, replacement, rollback,
  stale handles, and description isolation.
- Test invalid arguments, unsupported operations, result bounds, pagination,
  storage failures, and post-commit failures. Never silently skip failed work.
- Confirm nonvisual calls do not mutate map interaction/materialization state.

Follow project-native compile, constraints, and focused tests. Build when the
runtime is missing/stale or native code changes, with repository timeouts.
Use isolated test data, absolute assets/macro paths, disabled audio, and skipped
keyring tests. Broaden validation for any genuinely shared runtime changes;
no live network smoke is required because no transport is built. Required CI
remains the integration gate. Report constraint impact in Fennel handoffs.

## Explicit exclusions

No transport/server implementation or refactoring, additional app-wide resolver
runtime, startup-network API, global store-default rebinding, headless bootstrap,
general schema engine, automatic exposure of all node types, arbitrary UI action
execution, migration of every adapter, generic deletion/bulk operations, view
control, authentication, global/federated semantic search, or unrelated cleanup.
