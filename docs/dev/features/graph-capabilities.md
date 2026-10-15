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
