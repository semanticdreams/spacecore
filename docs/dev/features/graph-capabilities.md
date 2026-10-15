# Nonvisual graph capabilities

Graph capabilities are an explicit exposure contract over extension-owned domain
objects. They do not turn Graph into a domain store. Consumers use returned
references and capability metadata, not concrete node types or key-prefix
dispatch. Calls are synchronous on the authority's Lua thread and need neither
GraphMap nor GraphView. No visual adapter is constructed by these methods.

## Public methods and data

- `graph:discover({limit?, cursor?}) -> Result<Page<Entry>>`
- `graph:describe(ref) -> Result<Description>`
- `graph:invoke(ref, capability-id, args, preconditions) -> Result<Data>`

Optional fields are omitted, not literally suffixed with `?`:

```text
Ref         = {key: string}
Entry       = {ref: Ref, summary: string}
Description = {ref: Ref, summary: string, capabilities: [Metadata]}
Metadata    = {id: string, description: string, arguments: Shape, result: Shape,
               effect: "read" | "write", revision: "none" | "required"}
Page<Entry> = {items: [Entry], has-more: boolean, cursor?: string}
Result<T>   = {ok: true, value: T} | {ok: false, error: Error}
Error       = {code: string, message: string,
               outcome: "not-committed" | "committed" | "unknown",
               current-revision?: string, result?: Data}
```

References are opaque UTF-8 keys (1–1024 bytes); IDs are 1–256 bytes. Summaries and
capability descriptions are at most 4096 bytes. Records are closed: undeclared
fields are errors. Descriptions and returned values are checked, detached data,
not executable handlers or live object handles. Changing a returned description,
page, or result does not change extension state or future validation.

Discovery exposes only explicitly registered entry points, sorts by key, defaults
to 20 items and accepts limits 1–50. Each registration can expose at most eight
distinct entry points belonging to its own scheme. `has-more` always indicates
whether there are more entries; `cursor` is present only when true. Pass that
opaque versioned string back unchanged; it is bounded to 2048 bytes. The current
implementation uses a `v1:` key continuation internally. Pagination is live, not
a snapshot: unload/replacement may change later pages.

An absent scheme is `unavailable`; a registered visual-only scheme is
`not-exposed`. The owning description callback reports `not-found` for missing
domain objects. Only currently advertised IDs can be invoked, even if a hidden
handler exists. Every invocation obtains and validates the current description,
including *all* advertised argument/result declarations. Metadata is never a
cached executable handle. Unregister, reload replacement, installer rollback,
runtime uninstall, and Graph drop remove access with its loader registration.
Stale or foreign handles cannot remove an active replacement.

## Small shape vocabulary

Only these declarations are supported. All listed attributes are required;
unknown attributes are rejected. No aliases, unions, implicit coercions, open
records, or general JSON Schema features are supported.

```fennel
{:type :string :min-bytes 0 :max-bytes 65536}
{:type :integer :min -100 :max 100}
{:type :boolean}
{:type :enum :values ["low" "high"]}
{:type :record
 :fields {:text {:type :string :min-bytes 0 :max-bytes 65536}
          :label {:type :string :min-bytes 0 :max-bytes 128}}
 :optional ["label"]}
{:type :array :items {:type :boolean} :max-items 50}
```

String lengths are **bytes**, not characters, and strings must be valid UTF-8.
Integer bounds use the canonical attributes `min` and `max`; bounds and values
are finite, integral, and within ±9007199254740991 (portable exact integers).
Bounds are inclusive and ordered. Enum `values` is a nonempty dense array of
unique strings. Record `fields` has string names; `optional` is a dense array of
unique names declared in `fields`. Missing optional fields are omitted; `false`
is a real boolean value, not a missing field. Arrays are dense and have a
nonnegative integral `max-items`. An empty Lua table can represent an empty
record or array, as determined by the declared shape.

`graph/capability-shapes` exports:

- `validate-shape!(shape) -> true`: checks the declaration itself.
- `check!(shape, value) -> detached-value`: checks declaration and data.
- `detach!(value) -> bounded-data`: checks/copies plain data without a shape.

These helpers raise validation errors with `code` and `message`. Detached
traversal is bounded to depth **16** (root is depth 1), **4096 value nodes**
(including table containers), and **131072 aggregate UTF-8 string bytes**
(including record-key bytes). Shared acyclic tables are copied per occurrence.
Metatables, cycles, sparse/mixed arrays, non-string record keys, functions,
threads, userdata, nil data, and nonfinite numbers are rejected. Plain data may
contain finite fractional numbers, but integer shapes do not accept them.
Declarations are themselves subject to the detached-data budgets.

## Preconditions and outcomes

`preconditions` is a closed record with optional `revision`; omission of the
record means `{}`. `revision: "required"` needs a UTF-8 token of 1–512 bytes;
`revision: "none"` rejects any supplied revision. The generic layer validates and
forwards it. The owning domain mutation must compare the revision synchronously
at its write boundary; timestamps alone are not revision tokens.

Errors distinguish `invalid-arguments`, `limit-exceeded`, `not-found`,
`not-exposed`, `unsupported-capability`, `unavailable`, `conflict`,
`storage-failed`, `corrupt-data`, `notification-failed`, `invalid-result`, and
`internal-error`. Budget exhaustion is `limit-exceeded`; ordinary shape mismatch
is `invalid-arguments`. Invalid provider descriptions/results are `invalid-result`.
Unexpected callback exceptions are `internal-error`, without leaking arbitrary
exception payloads.

An error is not a rollback guarantee:

- Validation/resolution failures before invocation are `not-committed`.
- A thrown write handler has `unknown` outcome: it may already have committed.
- A write handler reporting success with invalid output yields **committed
  `invalid-result`**, without the unchecked payload.
- A malformed write failure/envelope yields `unknown` rather than inventing a
  rollback or commit. Read failures from the generic layer are `not-committed`.
- Checked domain failures preserve their declared outcome, optional current
  revision, and optional result. Any included result must satisfy the capability's
  result shape, including for `notification-failed` after a committed write.

Each mutation stands alone; there is no multi-record transaction, automatic
merge, automatic retry, or compensation of already committed work.

### Owning text and relationship stores

`entities/string` owns Markdown text records; `entities/link` owns directed JSON
relationship records. Their existing successful CRUD methods and signals remain
available. Updates preserve cached record identity for existing subscribers, but
write an independent staged record **before** publishing fields to that cache.

The text store additionally provides:

- `store:read-text(id) -> {id, value, revision}`: a detached snapshot, limited to
  **131072 stored bytes**, including frontmatter.
- `store:replace-text(id, value, expected-revision) -> snapshot`: checks the
  persisted revision and writes synchronously, without yielding. A stale token
  raises `conflict`, `outcome: "not-committed"`, and `current-revision`, without
  changing the prior file or cached record. There is no external-writer lock.

Every successful text update, including unconditional `update-entity`, same-value
and metadata-only updates, persists a fresh UUID revision. Legacy Markdown files
without a revision receive stable `legacy:<id>` tokens on reads, without file
rewrites. Only format-owned frontmatter and one empty separator line are removed;
user body whitespace, CRLF, Unicode, blank lines, and delimiter-looking text are
preserved byte-for-byte. IDs must be 1–256 ASCII letters/digits/underscore/hyphen;
path traversal, record/filename identity mismatches, caller revision overrides,
identity changes, and create collisions are errors.

The link store also provides `store:read-link(id) -> LinkEntity`: a detached
persisted read limited to **131072 stored bytes**, including serialized metadata.
Missing records raise `not-found`. It bypasses and never primes the legacy getter
cache. Capability link descriptions use this bounded read, not `get-entity`;
legacy CRUD getter/cache behavior is unchanged.

Both stores expose `store:scan-page(opts) -> {items, examined, has-more, last-id?}`:

- `limit`: 1–50, default 20; `examined-limit`: 1–200, default 200.
- `after-id`: optional last **examined** filename ID, exclusive; IDs are sorted.
- Text `query` is an optional case-sensitive literal substring, not a pattern.
  Link `key` optionally matches either incident endpoint; direction is preserved.
- Items are detached owning records. Each decoded record is limited to 131072
  stored bytes. A page may have zero matches and still have `has-more: true`;
  continue from its `last-id`. The last examined ID is also returned on a final
  nonempty examination; it is absent when nothing was examined.
- Corrupt, unreadable, oversized records or listing failure fail the whole page.
  Every examined text body is checked for valid UTF-8 before query filtering;
  corrupt nonmatches cannot be reported as a successful absence.
  Directory enumeration/sorting itself is not indexed or bounded total work.
  Continuations are live, not snapshot pagination.

Store methods raise structured Error records using the vocabulary above, rather
than Result envelopes. Missing legacy CRUD lookup/update/delete still returns
nil; missing `read-text`/`replace-text` raises `not-found`. A listener exception
after persistence raises committed `notification-failed` with the owning record
in `result` (a text snapshot for `replace-text`). It does not undo the mutation;
in particular link creation errors are no longer swallowed.

`entities/record-files` is the local publication boundary. It exports
`read!(path, max-bytes?)`, `write-text!(path, text)`, `write-json!(path, data)`,
`list-ids(dir, suffix)`, and `remove!(path)`. Text uses checked binary Lua I/O,
including write/flush/close, followed by staged-byte verification and a
same-directory rename. Attempt-owned sibling staging basenames are short and
independent of the destination basename, so valid long record filenames remain
replaceable. JSON uses `json-utils.write-json!` on a unique staging
path and verifies the exact serialized bytes before destination replacement.
Failure cleans only that attempt's staging artifacts, never the destination or
unrelated temporary files. This is checked publication, not power-loss durability.
Constructors may accept a local `files` boundary for fault injection; the helper's
`RecordFiles({open?, rename?, stage-json!?})` factory provides checked staging
seams for local tests. No module defaults or native/global helpers are rebound.

Directory enumeration uses the existing `fs.list-dir(path, include-hidden?)`,
which is now **always strict** for every caller: permission-denied and other
enumeration errors raise instead of being suppressed. There is no opt-in flag or
second listing API. Previously an inaccessible directory could appear to be an
empty successful listing; callers now receive an error. Readable empty/nonempty
result shapes, default inclusion of hidden entries, explicit hidden filtering,
and checked iterator increments are unchanged.

### First family: texts and directed relationships

The built-in entities descriptor attaches access to its existing loader
registrations. Discover entry points and choose them by their **advertised
capabilities**, not their key schemes. The text collection advertises list,
literal search, and creation; the relationship provider advertises incident
listing and directed creation. Text records advertise read and revision-required
replacement. Link records describe their endpoints in a short summary but expose
no incidental CRUD operations. Other entity/UX registrations remain visual-only.

| Capability | Arguments (closed record) | Result | Effect / revision |
|---|---|---|---|
| `collection.list` | `{limit?, cursor?}` | `Page<Entry>` | read / none |
| `collection.search` | `{query, limit?, cursor?}` | `Page<Entry>` | read / none |
| `collection.create` | `{text}` | `{ref, revision}` | write / none |
| `text.read` | `{}` | `{ref, text, revision}` | read / none |
| `text.replace` | `{text}` | `{ref, revision}` | write / required |
| `relationships.list` | `{subject: Ref, limit?, cursor?}` | `Page<Relation>` | read / none |
| `relationships.create` | `{source: Ref, target: Ref}` | `Relation` | write / none |

`Relation` is `{ref, source: Ref, target: Ref}`. The first family's references are
limited to **256 bytes**, text to **65536 bytes**, queries to **1–256 bytes**, and
summaries to **160 bytes**, truncated only at a valid UTF-8 boundary. Empty text
is allowed and whitespace/CRLF/Unicode are preserved. Oversized existing text
reads fail with `limit-exceeded`; invalid stored UTF-8 is `corrupt-data`. All
requests/results also obey the generic aggregate DTO budgets. Generic shape
mismatches (including declared per-field argument bounds) are `invalid-arguments`.

Search is the case-sensitive literal `string.find(body, query, 1, true)`, never a
Lua pattern, and searches the stored body only, not IDs/frontmatter. Pages default
to 20 results, accept limits 1–50, and delegate to the owning `scan-page` with at
most **200 examined/decoded records** per call. IDs sort lexicographically. A
zero-result page may still have `has-more: true`: pass its cursor back unchanged.
Continuation is live, not a snapshot. Directory enumeration/sorting is not an
indexed or globally bounded search.

Provider cursors are opaque, versioned `v1:` continuations, bounded to 2048 bytes.
Their closed payload binds the operation, provider reference, query (or incident
subject key), and last **examined** ID. Unknown versions, malformed/extra fields,
invalid IDs, and mismatched scope are rejected. Limits may change between pages.
A cursor is returned only with `has-more: true`. It is not an authorization token.

Relationship listing returns only direct incident persisted links and preserves
source/target direction. It does not traverse identities, inspect display edges,
or invent collection membership. Creation currently accepts **existing text record
endpoints only**, validated synchronously inside the context-free
`entities/relationships.create!(string-store, link-store, source-ref, target-ref)`
operation. Listing can report direct links to other bounded opaque references
already stored by their owners; it does not make those endpoints executable.

The family delegates creation/read/replacement to the owning string store and
link creation to `relationships.create!`. Notification failures after persistence
retain `outcome: "committed"` and map their owning result to the declared written
text/relation DTO; failed storage writes remain explicit. No compensation or
automatic retry occurs. These are the domain operations for participating GUI
actions as well, as described below.

Nonvisual writes do not materialize graph adapters. Raw Graph's string-created
auto-loading is removed; link/identity events reconcile only already-visible
endpoints, using owning identity data without loaders. Explicit `load-by-key`,
`resolve-key`, and `resolve-node` retain their loading behavior. Existing visible
labels and derived domain edges may update, but nonvisual access does not change
GraphMap membership, explicit display edges, focus, selection, islands, or
projection settings. No map/view is required or consulted by a provider callback.

### Participating GUI text editors and child creation

Full string-entity views and previews compose the shared
`graph/view/string-entity-editor` widget. The node's `read-text()` and
`replace-text(value, revision)` delegate directly to the same owning string-store
operations as `text.read` and `text.replace`. There is no revisionless node edit
alias. Full views retain the `Enter value...` placeholder and 3–20 lines; previews
retain `Value...` and exactly three visible lines.

Each mounted editor owns a detached content/revision baseline. Opening initializes
Input through its `text` option, without emitting a save or advancing the revision.
Edits submit the revision that produced that editor's displayed content, never a
fresh revision borrowed from a store signal or a conflict. Only a successful save
or an explicit committed error result advances that baseline. Thus two editors,
GUI/agent edits in either direction, unconditional legacy writes, and same-second
A-to-B-to-A writes all reject stale replacement rather than silently overwriting.
Store signals continue to update node labels, not editor content or baselines.

Conflicts and storage errors retain attempted input and the prior baseline, and
display an owned status line. A committed notification error retains the input,
advances to its committed result, and explicitly says **Save committed**. There is
no automatic reload, retry, or merge. Empty status occupies no extra layout space;
dropping the surface recursively drops its editor, Input, and status renderables.

`node:create-child()` is a GUI convenience, not a generic deletion or transaction
capability. It preflights its containing GraphMap and callable reveal API before
writing, creates an empty string through the owning store, links through
`entities/relationships.create!`, then explicitly reveals that child in the same
map. The link supplies a derived edge; no explicit persisted display edge is added.
Successful results retain `child`, `child-key`, `child-node`, and `link`, and also
include `link-key`.

Once a child or link commits it is **not deleted as compensation** if a subsequent
step fails. Errors include `stage` (`child`, `link`, or `reveal`), the original
`code` and `cause`, a `result` holding known created records/keys, and per-step
`outcomes`. Domain outcomes are `not-attempted`, `not-committed`, `committed`, or
`unknown`; reveal is `not-attempted`, `revealed`, or `unknown` (a throwing reveal
may already have inserted the child). The top-level `outcome` is `committed` when
any known domain record committed, otherwise the failing operation's outcome.
Committed notification failures retain the created keys from their owning result,
stop the sequence, and do not imply that later steps ran. Inspect per-step outcomes
and retained keys rather than blindly repeating the whole action.

## Registration and ownership

Descriptor installers add optional `access` to the **existing** key-loader opts:

```fennel
(fn install-loaders [graph ctx]
  (local object-ref {:key "test-meter:one"})
  (local integer {:type :integer :min -100 :max 100})
  (local metadata
    {:id "meter.adjust" :description "Adjust the meter"
     :arguments {:type :record
                 :fields {:delta integer
                          :reason {:type :string :min-bytes 0 :max-bytes 64}}
                 :optional []}
     :result {:type :record
              :fields {:level integer :changed {:type :boolean}}
              :optional []}
     :effect :write :revision :none})
  (fn describe-meter [ref]
    ;; Real providers check object existence here.
    {:ok true :value {:ref ref :summary "A meter" :capabilities [metadata]}})
  [(graph:register-key-loader
     "test-meter" make-visual-meter
     {:owner-id ctx.owner-id :extension-id ctx.extension-id
      :access {:entry-points [{:ref object-ref :summary "A meter"}]
               :describe describe-meter
               :handlers {"meter.adjust" adjust-domain-meter}}})])
```

`describe` and handlers are ordinary functions, called without implicit `self`.
Handler arguments are `(ref, args, preconditions)`; return the Result envelope.
Owning systems implement/persist domain behavior and disclose commit outcomes.
No capability is inferred from menu actions. Visual-only registrations remain
valid and are not automatically exposed.

`graph/capabilities` exports `prepare-access`, `discover`, `describe`, and `invoke`.
Graph retains registration storage privately; the generic implementation imports
no domain, node, view, or map modules. Preparation checks/copies entry metadata
and handler mappings before publication. Dynamic descriptions are checked/copied
on every call. Use `ctx:record-handle` before later installer steps that can throw
so the existing extension registry can roll back partial installs. See
[Reloadable Graph Extension Units](/dev/features/reloadable-graph-extension-units).

This slice adds no transport, server, headless bootstrap, resolver runtime,
universal CRUD, schema engine, view control, or automatic exposure of node types.
