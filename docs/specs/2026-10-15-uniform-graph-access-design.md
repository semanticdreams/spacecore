# Uniform, view-independent graph access

## Intent and agreed scope

Make graph's exposure contract usable by nonvisual consumers without coupling
them to concrete object families or a GraphMap. The first authority is the
running Space process. CLI, HTTP/MCP, and voice are future consumers of the same
contract; this slice delivers the contract and one narrow MCP-over-HTTP adapter
using existing transport infrastructure. It does not implement four front ends.

The user approved trusted, explicitly enabled local access to shared app data.
No world/project restriction is inferred from graph-map visibility. An endpoint
is disabled by default and binds only to loopback; this is not authentication.

The representative acceptance workflow finds a project brief, reads it and its
domain relationships, creates two notes, links them to the brief, updates one,
and reads back persisted results. String and link entities implement this first
example behind the graph boundary. They must not determine transport verbs or
require consumers to branch on entity types.

## Existing architecture and choices

Graph is an exposure/adaptor layer, not the owner of domain objects. Owning
systems retain persistence. GraphMap owns materialized topology and interaction
context; GraphView is its runtime visual projection. Current key loaders can
create unmounted adapters, but those adapters mix UI constructors, subscriptions,
map-related callbacks, and domain methods. UI action closures are not a safe
machine-readable command interface.

Three approaches were considered:

1. Invoke unmounted visual node adapters: smallest apparent change, but retains
   presentation dependencies and request-scoped subscription/lifecycle hazards.
2. Extend existing graph extension/key-loader registrations with nonvisual
   exposure: selected. One family registration owns visual and nonvisual
   adaptation and shares domain operations between them.
3. Add a parallel domain service/registry: rejected. A type-specific entity API
   or second universal registry would bypass the intended graph interface.

Only participating families need exposure initially. Older visual extensions
continue to function; they do not acquire remotely executable actions by
reflection or by having a key-loader scheme.

## Contract and ownership

A graph-owned access facade dispatches exclusively through explicit exposure
metadata registered alongside existing owner-safe key loaders. Visual loading
and exposure registration share replacement, unload, rollback, and lifetime.
There is no separate family dispatch table in any transport. Exposures resolve
without constructing visual adapters or materializing graph topology.

The facade exposes six generic operations:

- `discover`: bounded enumeration of registered entry-point references.
- `inspect`: describe an opaque key, its summary, resources, actions, and support
  for search and direct domain relationships.
- `read`: read a named resource with schema-described arguments; return its
  value and revision when relevant.
- `search`: bounded search within an explicitly discovered searchable scope.
- `relations`: bounded one-hop domain relationship reads for a key and direction.
- `invoke`: invoke a named action with validated arguments and any required
  expected revision.

Keys remain opaque to consumers. Descriptions and results are data-only and
JSON serializable: no Lua closures, live adapters, glm values, or view handles.
Resource/action descriptors include stable IDs, descriptions, argument/result
schemas, effect information, and revision requirements. Uniform access does not
imply uniform CRUD: unsupported operations fail explicitly. Only a deliberately
supported, documented schema subset may be advertised; argument validation is
mandatory at the service boundary, not merely a promise in MCP tool schemas.

Creation is an advertised action on an entry point/collection/provider. A
consumer discovers that action and its schema and invokes it through the same
generic operation used for any other action. Results contain created references.
No `create-string` or other family-specific transport method is introduced.

Domain relationships are distinct from display edges, collection membership,
and discovery roots. Initial relationship records expose their own opaque key,
source and target references, and kind. The initial creation provider persists
directed link relationships between existing supported endpoints. There is no
implicit identity dereference, recursive traversal, or graph-map edge write.

## Runtime and UI integration

The app owns one nonvisual graph resolver/access runtime installed by the
existing extension mechanism in an explicit resolver-only role. It uses the
same owning stores as participating GUI adapters. It does not depend on an
active world, activity, map, or view, and disables topology-oriented entity
event handling. Resolver-only extension installation must not require map
refresh; ordinary world-runtime refresh behavior remains intact.

Participating UI adapters delegate context-free domain reads and mutations to
the same exposure operations. They retain explicit visual consequences such as
revealing a newly created note in their own map. Existing UI convenience
behavior must not be broken or copied into nonvisual invocation.

Nonvisual operations never change map membership, explicit display edges,
selection, focus, layout, expanded cards, or panels. Existing views may still
reflect changes to the underlying objects through existing store subscriptions.

## Consistency, persistence, and limits

Requests execute on the authority's Lua dispatch thread. Serialization alone is
not stale-edit protection. Revision-guarded resource updates compare an opaque
expected revision at the owning store mutation boundary, without yielding
between comparison and persistence. Every successful store mutation, including
GUI-originated writes, changes the persisted revision. Timestamps are not
revision tokens. Legacy records have stable read tokens until first mutation;
reads do not rewrite them. Conflicts perform no write and identify the current
revision. There is no multi-editor merge or retrofit of GUI conflict dialogs.

Mutation success means checked atomic replacement of the individual record,
followed by cache publication. Failed persistence leaves prior data/cache/token
authoritative. Preserve existing Markdown/JSON formats and exact user text.
If notification fails after persistence, report the committed outcome explicitly
rather than claiming rollback. This requires localized fixes in owning stores
and native write-completion checks where existing helpers are insufficient.

Each action commits independently. No cross-record transaction, rollback of
earlier successful actions, exactly-once retry, power-loss durability guarantee,
or coordination with independent external file writers is promised.

Initial limits: default page size 20, maximum 100; search query 1–256 UTF-8 bytes;
summary previews at most 240 UTF-8 bytes; inspected/written text at most 64 KiB;
each provider search/relationship page examines at most 1,000 records. Provider
pagination uses deterministic ordering and last-examined continuation, including
empty pages. Cursors are opaque at the generic boundary. Pages are not snapshots
across concurrent changes. Directory enumeration is not claimed to be indexed
or bounded independently of directory size. Oversized/corrupt/unreadable records
produce explicit errors rather than silently incomplete successful results.

Errors distinguish invalid arguments, unsupported capabilities, missing objects,
conflicts, exhausted budgets, storage failures, post-commit notification failures,
and unavailable/dropped services. No silent fallback to the UI's active map or
another runtime is permitted.

## Transport and lifecycle

Expose the six generic operations through a dedicated narrow MCP registry using
the existing loopback HTTP/SSE server and bridge lifecycle. Keep it separate from
the internal agent endpoint: the existing SSE mode supports one active stream
and external reconnects must not displace internal agent ownership. Document
that limitation; this slice does not promise general multi-client SSE sessions.
Independent clients can share the service authority without sharing view state.

Explicit app startup/stop APIs enable the endpoint and return connection
information. Startup must not modify global client configuration or launch a
second Space runtime. Shutdown stops ingress before releasing the facade and
resolver. Failed starts clean up; retained dropped references fail explicitly.
Requests resolve current registrations afresh rather than retaining executable
handlers across extension reloads.

## Acceptance and validation

1. Run the brief-and-notes workflow entirely through generic calls and schemas.
2. Reopen stores and recover exact text, created references, and domain links.
3. Persist a GUI-style edit between read and invocation; reject stale update
   without overwriting it, including same-second and A→B→A edits.
4. Exercise no-view/no-map operation, app lifetime, and world/map independence.
5. Register a second test-only family with different resources/actions; use it
   through the unchanged generic transport, then unload and replace it safely.
6. Verify owner-safe replacement, rollback, failed startup, shutdown, invalid
   inputs, unsupported operations, bounds, storage errors, and committed errors.
7. Confirm participating UI behavior still works and no nonvisual operation
   materializes or changes map interaction state.

Validation follows native build freshness, Fennel compile, constraints, focused
store/access/extension/MCP tests, and a final full local suite. A live-process
transport smoke is required; no model-backed test is necessary. Native write
changes require `make build` with the repository's explicit timeout. Use isolated
XDG test data, absolute assets/macro paths, disabled audio, and skipped keyring
tests. Required CI and merge-group checks remain the integration gate.

## Explicit exclusions

No separate writable runtime, distributed synchronization, headless bootstrap,
CLI or voice front end, separate REST API, view control protocol, universal CRUD,
generic deletion, bulk actions, semantic/global federated search, relationship
ontology, arbitrary UI callback invocation, automatic exposure of all schemes,
authentication system, or unrelated adapter/store redesign.
