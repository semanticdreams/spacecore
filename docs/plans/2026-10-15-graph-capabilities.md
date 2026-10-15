# Uniform Graph Capabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver discover/describe/invoke graph access with shared GUI operations, demonstrated by persisted notes and relationships and stale-edit rejection.

**Architecture:** Extend existing key-loader registrations with optional nonvisual capability definitions, retaining registration ownership and cleanup. Generic dispatch knows no object families and constructs no visual adapters. Owning stores provide persistence and revision checks shared by capabilities and participating GUI actions.

**Tech Stack:** Space Fennel/Lua, existing graph extension registry, Markdown/JSON stores, existing filesystem bindings and JSON helper, native Fennel tests.

## Global Constraints

- Authority: `docs/specs/2026-10-15-uniform-graph-access-design.md`, corrected in `545f360`; older proposals are obsolete.
- “Uniform access must not make consumers dispatch on concrete object types.”
- “Nonvisual consumers are independent of GraphMap and GraphView state.”
- “Participating graph-view operations use the same domain implementation now, rather than leaving a parallel interface to converge later.”
- “Replacement-style edits reject stale revisions explicitly, for participating GUI edits as well as nonvisual edits. No silent overwrite or automatic merge.”
- “The representative workflow is a project brief with two related notes.”
- “Demonstrate extensibility with a second, different test-only family.”
- “Execution is synchronous on the authority's Lua thread.”
- “Timestamps alone are not revision tokens.”
- “Each mutation stands alone. The workflow is not a multi-record transaction.”
- “No transport/server implementation or refactoring, additional app-wide resolver runtime, startup-network API, global store-default rebinding, headless bootstrap, general schema engine, automatic exposure of all node types, arbitrary UI action execution, migration of every adapter, generic deletion/bulk operations, view control, authentication, global/federated semantic search, or unrelated cleanup.”
- No edits to app startup, global JSON helpers, or transport modules are planned. The user explicitly authorized one native prerequisite after a reproduced failure: make existing `fs.list-dir` always strict on enumeration errors, not opt-in. Other native/global changes still require escalation.
- Implementers do not commit. Each task requires an independent reviewer PASS; the supervisor then commits reviewed files and its progress ledger.
- Use final-literal Fennel factories, `local`, canonical option keys, explicit errors, and owned teardown.

## Validation Environment

Build only if the runtime is missing/stale: `make build`, tool timeout `14400000` ms. If CMake configuration is required: `make cmake`, timeout `600000` ms.

Direct runtime checks use this environment:

```bash
export SKIP_KEYRING_TESTS=1
export XDG_DATA_HOME=/tmp/space/tests/xdg-data
export SPACE_DISABLE_AUDIO=1
export SPACE_ASSETS_PATH="$(pwd)/assets"
export FENNEL_PATH="$(pwd)/assets/lua/?.fnl;$(pwd)/assets/lua/?/init.fnl"
export FENNEL_MACRO_PATH="$FENNEL_PATH"
```

For each task run native touched-file compile, explicit-file constraints, then focused tests. `make fennel-check` / `make constraints` are acceptable broader equivalents. A non-pass constraint result is blocking. New test `main` functions actually call `tests/runner.run-tests`, rather than only returning a test array. Register new modules in `assets/lua/tests/fast.fnl`.

```bash
./build/space -m tools.fennel-check:main -- --target files --file assets/lua/graph/core.fnl
./build/space -m constraints.runner:main -- --target files --file assets/lua/graph/core.fnl
./build/space -m tests.test-graph-capabilities:main
```

Report compile, constraints, focused-test, and constraint-impact evidence. Required CI remains the full integration gate; no network smoke is required.

## File Responsibilities

- `graph/capability-shapes.fnl`: small checked shape vocabulary and bounded detached data.
- `graph/capabilities.fnl`: generic operations over existing loader registrations.
- `entities/record-files.fnl`: local checked record reads/writes and staging, not a global persistence framework.
- `entities/string.fnl`, `entities/link.fnl`: owning record operations, scans, text revisions.
- `entities/relationships.fnl`: shared context-free domain linking for this family.
- `graph/capabilities/entities.fnl`: first family's descriptions, handlers, and detached results.
- `graph/view/string-entity-editor.fnl`: shared displayed-revision editor lifecycle.

### Task 1: Generic Capabilities Within Key-Loader Ownership

**Files:**
- Create: `assets/lua/graph/capability-shapes.fnl`, `assets/lua/graph/capabilities.fnl`
- Modify: `assets/lua/graph/core.fnl`
- Create/Test: `assets/lua/tests/test-graph-capabilities.fnl`
- Modify/Test: `assets/lua/tests/test-graph-extension-registry.fnl`
- Modify: `assets/lua/tests/fast.fnl`
- Create: `docs/dev/features/graph-capabilities.md`
- Modify: `docs/dev/features/reloadable-graph-extension-units.md`

**Interfaces:**
- Existing `graph:register-key-loader(scheme, loader, opts)` gains optional `opts.access` in its existing private registration record.
- `graph:discover({limit?, cursor?}) -> Result<Page<Entry>>`
- `graph:describe(ref) -> Result<Description>`
- `graph:invoke(ref, capability-id, args, preconditions) -> Result<Data>`
- `Ref = {key: string}`; `Entry = {ref: Ref, summary: string}`.
- `Description = {ref: Ref, summary: string, capabilities: [Metadata]}`.
- `Metadata = {id, description, arguments: Shape, result: Shape, effect: "read"|"write", revision: "none"|"required"}`.
- `Result = {ok: true, value: Data}` or `{ok: false, error: Error}`.
- `Error = {code, message, outcome: "not-committed"|"committed"|"unknown", current-revision?: string, result?: Data}`. Optional fields are omitted; their literal keys have no `?` suffix.
- `Access = {entry-points: [Entry], describe: fn(ref)->Result<Description>, handlers: {id -> fn(ref,args,preconditions)->Result<Data>}}`.
- Preconditions are a closed record with optional `revision: string`.
- `Shapes.validate-shape!(shape) -> true`, `Shapes.check!(shape,value) -> detached-value`, and `Shapes.detach!(value) -> bounded-data` raise checked validation errors.
- `Capabilities.prepare-access(scheme,access) -> private-access` validates and copies registration data. `Capabilities.discover(registrations,args)`, `Capabilities.describe(registrations,ref)`, and `Capabilities.invoke(registrations,ref,id,args,preconditions)` implement the thin Graph methods over its existing private registration records. Registration storage remains owned by Graph.

- [ ] **1. Write failing tests for checked shapes and explicit registration.** Support only string, integer, boolean, string enum, closed record with optional fields, and bounded array shapes. Example:

  ```fennel
  {:type :record
   :fields {:text {:type :string :min-bytes 0 :max-bytes 65536}}
   :optional []}
  ```

  Validate declarations and values. Reject unknown attributes, cycles, metatables, sparse arrays, userdata/functions, nonfinite integers, and undeclared fields. Limit detached traversal to depth 16, 4096 values, and 131072 aggregate string bytes. Strings must be valid UTF-8. These are local shape descriptions, not JSON Schema.

- [ ] **2. Run the regression to establish RED, then implement registration and dispatch.** Validate/copy access metadata and handler mappings before registration publication. Reuse current loader handles; no new registry or adapter construction. Every call resolves the current registration, obtains current description, validates arguments/preconditions, invokes the advertised handler, and checks/detaches results. Hidden handlers are not callable. Required revision strings have 1–512 bytes; revision-free capabilities reject supplied revisions. Unexpected write exceptions report unknown outcome, not rollback. Invalid success output after a write reports committed invalid-result without leaking unchecked data.

- [ ] **3. Add bounded discovery and lifecycle regressions.** Discovery defaults to 20 items, maximum 50, sorts by opaque key, and accepts a versioned opaque continuation of at most 2048 bytes. Limit each registration to 8 entry points belonging to its registered scheme. Pages return `{items, has-more, cursor?}`. Test detached metadata, visual-only registrations, unload/replacement, inactive/stale/foreign handles, graph drop, partial installer rollback with `ctx:record-handle`, and installation rollback across two runtimes. Use existing registry behavior; do not introduce resolver-only roles.

  Errors distinguish `invalid-arguments`, `limit-exceeded`, `not-found`, `not-exposed`, `unsupported-capability`, `unavailable`, `conflict`, `storage-failed`, `corrupt-data`, `notification-failed`, `invalid-result`, and `internal-error`.

- [ ] **4. Prove generic dispatch with a different test-only family.** Its visual loader throws; its `meter.adjust` capability takes integer `delta` and string `reason`, returning integer `level` and boolean `changed`:

  ```fennel
  (local result (graph:invoke {:key "test-meter:one"} "meter.adjust"
                             {:delta 3 :reason "calibration"} {}))
  (assert result.ok)
  (assert (= result.value.level 3))
  (assert (= visual-loader-calls 0))
  ```

  Assert the generic modules import no entity/node/view/map modules. An old data description cannot retain a removed handler; after replacement invocation reaches current behavior.

- [ ] **5. Document the public methods, shapes, outcomes, and registration example; validate and hand off for review.** Compile/constraints for touched files, then run `tests.test-graph-capabilities:main`, `tests.test-graph-extension-registry:main`, and `tests.test-graph-loaders:main`. Supervisor commits only after reviewer PASS.

### Task 2: Owning Text Revisions and Local Checked Persistence

**Files:**
- Modify: `src/lua_fs.cpp` (strict directory enumeration only)
- Modify/Test: `assets/lua/tests/test-fs.fnl`
- Create: `assets/lua/entities/record-files.fnl`
- Modify: `assets/lua/entities/string.fnl`, `assets/lua/entities/link.fnl`
- Create/Test: `assets/lua/tests/test-entity-record-persistence.fnl`
- Modify: `assets/lua/tests/fast.fnl`, `docs/dev/features/graph-capabilities.md`
- Regression: `assets/lua/tests/test-string-entities.fnl`, `assets/lua/tests/test-link-entities.fnl`

**Interfaces:**
- Preserve existing successful CRUD return shapes and signals.
- `string-store:read-text(id) -> {id, value, revision}` returns a detached snapshot.
- `string-store:replace-text(id,value,expected-revision) -> snapshot`, raising structured errors on failure.
- Existing text `update-entity` always advances persisted opaque revision, even without a precondition.
- Both stores add `scan-page(opts) -> {items, examined, has-more, last-id?}`.
- Scan options: `after-id?`, `limit` 1–50/default 20, `examined-limit` 1–200/default 200; text additionally accepts literal `query?`, links accept incident endpoint `key?`.
- Constructors optionally accept `files` for a local injected record-file boundary, never a global default replacement.
- RecordFiles exports `read!(path,max-bytes?)`, `write-text!(path,text)`, `write-json!(path,data)`, `list-ids(dir,suffix)`, `remove!(path)`.
- Store errors use the Task 1 outcome vocabulary, with committed owning records/snapshots in `result` where applicable.
- Existing `fs.list-dir(path,include-hidden?)` always raises enumeration errors; no new option/mode/alias. Readable empty/nonempty results and hidden filtering are unchanged. Remove `skip_permission_denied` at iterator construction; retain checked increments. The systematic-debugging report in `task-2-report.md` establishes the reproduced native suppression gap; debug-advisor confirmed it and the user approved strictness for all callers.

- [ ] **1. Add RED persistence/concurrency cases.** Verify empty text, spaces/blank lines, CRLF, Unicode, and delimiter-looking text round-trip exactly. Legacy records receive stable `legacy:<id>` tokens across reopen without rewriting. Include same-second, same-value, metadata-only, and A-to-B-to-A writes. Reject caller-provided identity/revision overrides and create collisions.

  ```fennel
  (local before (store:read-text entity.id))
  (store:update-entity entity.id {:value "B"})
  (store:update-entity entity.id {:value before.value})
  (local (ok err) (pcall store.replace-text store entity.id "attempt" before.revision))
  (assert (not ok))
  (assert (= err.code :conflict))
  (assert (= (. (store:read-text entity.id) :value) before.value))
  ```

- [ ] **2. Implement checked local record publication.** Use checked binary Lua I/O for text staging, checking write, flush, and close before same-directory rename. Use `json-utils.write-json!` for JSON staging and verify staged serialized bytes before destination replacement, because the current native write binding does not check completion. Use unique attempt-owned staging paths and clean only those artifacts. Never delete a destination to make rename succeed. Inject failures at open/write/close/verification/rename. Include the approved strict native directory-listing prerequisite and its RED/GREEN regression, rebuild with timeout 14400000 ms, and do not expand other native/global behavior.

- [ ] **3. Add owning-store revision comparison and exact text parsing.** Remove only format-owned frontmatter/separator bytes, not user whitespace. Validate IDs against path traversal and record/filename mismatch; malformed required data is explicit corruption. Stage an independent record, compare expected revision without yielding, persist with fresh UUID revision, then publish cache and emit. Precommit failure/conflict leaves prior cache/file unchanged. Preserve compatible cached reference behavior where existing callers rely on it; snapshots remain detached. No rewrite on legacy reads.

- [ ] **4. Make scans and outcomes explicit.** Scan sorted filename IDs and advance last examined ID on nonmatches; bound each scan to 200 decoded records and each capability record to 131072 stored bytes. Directory enumeration is not indexed/bounded total work. Corruption, unreadable/oversized records, and listing failure fail the page rather than silently skipping. Cache publication follows persistence for both stores. Listener errors after persistence report committed `notification-failed`, including the owning result; do not silently swallow link creation errors or undo committed data.

- [ ] **5. Test reopen and failure invariants, document, and validate.** Check file/cache/revision unchanged at each precommit fault; committed record survives listener fault; empty-match pagination makes progress. Cover readable empty/nonempty, hidden filtering, missing/non-directory errors, and real denied enumeration through both stores; restore fixture permissions reliably and state platform/privilege applicability honestly. Build native binding first, then run compile/constraints, `tests.test-fs:main`, `tests.test-entity-record-persistence:main`, `tests.test-string-entities:main`, `tests.test-link-entities:main`, and `tests.test-board-activity-string-entities:main`. Hand off for independent review before commit.

### Task 3: First Family and Complete Nonvisual Workflow

**Files:**
- Create: `assets/lua/entities/relationships.fnl`, `assets/lua/graph/capabilities/entities.fnl`
- Modify: `assets/lua/graph/extensions/builtins/entities.fnl`, `assets/lua/graph/core.fnl`
- Create/Test: `assets/lua/tests/test-graph-entity-capabilities.fnl`
- Modify/Test: `assets/lua/tests/test-graph-loaders.fnl`, `assets/lua/tests/test-graph-core.fnl`
- Modify: `assets/lua/tests/fast.fnl`, `docs/dev/features/graph-capabilities.md`, `docs/dev/notes/graph.md`

**Interfaces:**
- `relationships.create!(string-store,link-store,source-ref,target-ref) -> LinkEntity` validates existing supported endpoints without graph loading.
- `EntityCapabilities.access-by-scheme({string-store,link-store}) -> {scheme -> Access}` attaches to existing string/link record and collection registrations.
- Text read DTO: `{ref, text, revision}`; text create/replace DTO: `{ref, revision}`.
- Relation DTO: `{ref, source: Ref, target: Ref}`.

| Reference | Capability | Arguments | Result | Effect/revision |
|---|---|---|---|---|
| Text collection | `collection.list` | page | page of entries | read/none |
| Text collection | `collection.search` | page + query | page of entries | read/none |
| Text collection | `collection.create` | text | written text DTO | write/none |
| Text record | `text.read` | empty record | text DTO | read/none |
| Text record | `text.replace` | text | written text DTO | write/required |
| Relationship provider | `relationships.list` | page + subject Ref | page of relations | read/none |
| Relationship provider | `relationships.create` | source Ref + target Ref | relation DTO | write/none |

- [ ] **1. Add the RED complete workflow using only generic methods.** Fixture setup may seed a brief directly; the workflow uses discovered references and advertised capabilities to find/read the brief, create/link two notes, replace one with a read revision, and read back. Install through existing registry machinery; instrument visual loaders to fail if invoked. Describe link records with endpoint summaries and no incidental CRUD capabilities.

  ```fennel
  (local created (graph:invoke collection.ref "collection.create" {:text "  note\n\n"} {}))
  (assert created.ok)
  (local readback (graph:invoke created.value.ref "text.read" {} {}))
  (assert (= readback.value.text "  note\n\n"))
  (assert (= (graph:node-count) 0))
  ```

- [ ] **2. Register the first family beside its current visual loaders.** Reuse owning read/create/replace and `relationships.create!`; adapt structured failures to detached declared outcomes, including committed results. Record handles immediately with `ctx:record-handle` for installer rollback. No generic module may import the family. No provider callback may touch a map/view or build a visual adapter.

- [ ] **3. Implement documented bounded provider behavior.** Text search is literal case-sensitive `string.find(value,query,1,true)` over stored body only; query 1–256 bytes, text 65536 bytes, UTF-8-safe summaries 160 bytes, references 256 bytes. Pages use Task 2 budgets and opaque versioned continuation scoped to operation/reference/query and last examined ID. Validate scope and closed cursor shape. Empty pages can have continuation. List direct incident domain links, preserving direction; no map edges, implicit identity traversal, or invented membership relations. Validate supported endpoints inside the relationship operation.

- [ ] **4. Prevent implicit materialization from domain writes.** Raw Graph's current entity-event handlers can load newly created strings and hidden link endpoints. Make those event paths update only already-materialized references, never invoke loaders for unseen objects. Preserve explicit loading/resolution APIs and derived edges for visible endpoints; HomeWorld's existing events-disabled setup is unchanged. Update old implicit-loading tests to explicitly load endpoints before expecting derived edges. This change directly enforces the approved nonvisual-isolation guarantee, not a graph subsystem redesign.

- [ ] **5. Validate persistence, isolation, and the integrated family.** Reopen both stores and verify exact text/keys/link direction. Test events-enabled and events-disabled Graph plus a sentinel GraphMap: membership, explicit edges, selection, focus, islands, and projection state unchanged by nonvisual calls. Existing labels/derived edges may reflect domain changes. Cover invalid endpoints, literal search metacharacters, limits, cursor mismatch, faults, and empty-page continuation. Run compile/constraints and complete modules `test-graph-entity-capabilities`, `test-graph-capabilities`, `test-graph-loaders`, `test-graph-core`, `test-graph-map`, `test-builtin-graph-extensions`; reviewer PASS before commit.

### Task 4: Revision-Aware GUI Operations and Final Acceptance

**Files:**
- Create: `assets/lua/graph/view/string-entity-editor.fnl`
- Modify: `assets/lua/graph/view/views/string-entity.fnl`, `assets/lua/graph/view/previews/string-entity.fnl`, `assets/lua/graph/nodes/string-entity.fnl`
- Create/Test: `assets/lua/tests/test-string-entity-editor.fnl`
- Modify/Test: `assets/lua/tests/test-string-entities.fnl`, `assets/lua/tests/test-string-entity-create-child.fnl`
- Modify: `assets/lua/tests/fast.fnl`, `docs/dev/features/graph-capabilities.md`, `docs/dev/graph-maps.md`

**Interfaces:**
- `node:read-text() -> snapshot`; `node:replace-text(value,revision) -> snapshot` delegate to the same owning operations as capabilities.
- Migrate production `node:update-value` callers in full view and preview; no alias bypassing required revisions.
- `StringEntityEditor(node,opts) -> build(ctx) -> {layout,input,status-text,last-error?,drop}`; options preserve surface placeholder/line settings.
- Preserve successful `node:create-child()` fields `child`, `child-key`, `child-node`, `link` and same-map reveal convenience.

- [ ] **1. Add RED real-editor concurrency cases.** Building preview/full editor must not write or advance revision; current `set-text` initialization can emit a change. Test GUI write invalidates nonvisual baseline, nonvisual write invalidates displayed GUI baseline, two editor instances, same-second/A-to-B-to-A changes, and an unconditional store write. On conflict attempted text remains and an explicit visible error is present.

  ```fennel
  (local editor ((StringEntityEditor node {}) ctx))
  (node.store:update-entity node.entity-id {:value "external"})
  (editor.input:set-text "attempted GUI edit")
  (assert (= (editor.input:get-text) "attempted GUI edit"))
  (assert (= editor.last-error.code :conflict))
  (assert (= (. (node:read-text) :value) "external"))
  ```

- [ ] **2. Implement the shared displayed-revision editor.** Capture detached value/revision on build and initialize through Input's `text` option. Each change submits that editor's baseline revision. Advance only on success or an explicit committed result. Never silently refresh from a conflict/store signal or retry. Preserve attempted content on errors; a committed notification error says the save committed. Compose full view/preview around the shared widget; final literals and explicit direct-child ownership, with one drop path.

- [ ] **3. Share creation/linking and preserve presentation separation.** `Create child` preflights GraphMap/reveal requirements, creates via the owning string operation, links via `relationships.create!`, then explicitly reveals in its containing map. No map is needed for the domain operations. No transaction is promised: after linking/reveal/notification failure report failed stage and committed child/link keys; do not silently delete committed records as compensation. Update that failure regression while preserving nonmutating preflight and successful same-map/derived-edge behavior.

- [ ] **4. Verify and document GUI compatibility.** Cover label subscriptions, editor teardown/no leaks, both surface settings, repeated conflicts preserving input, committed error status, child reveal, and partial outcomes. Run compile/constraints and `test-string-entity-editor`, `test-string-entities`, `test-string-entity-create-child`, `test-graph-entity-capabilities`, `test-graph-view-labels`. If editor geometry changes, run focused string-view E2E outside sandbox and visually inspect any image/golden changes; do not silently update snapshots.

- [ ] **5. Final regression and scope review, then independent review.** Run `make fennel-check`, `make constraints`, and these complete modules with the isolated environment:

  ```bash
  for suite in test-graph-capabilities test-entity-record-persistence \
    test-graph-entity-capabilities test-string-entity-editor \
    test-string-entities test-link-entities test-string-entity-create-child \
    test-string-entity-search test-board-activity-string-entities \
    test-identity-entities test-list-entities test-notebooks \
    test-graph-core test-graph-loaders test-graph-map \
    test-graph-extension-registry test-builtin-graph-extensions \
    test-graph-extension-units test-graph-extension-runtime-plumbing \
    test-graph-extension-morphs test-graph-view test-graph-view-labels \
    test-link-entity-crash; do
    ./build/space -m "tests.$suite:main" || exit 1
  done
  ```

  This covers changed owning stores, shared graph API, lifecycle, maps, and editor embedding. The user-approved always-strict filesystem binding affects shared utility behavior, so additionally run `SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH=$(pwd)/assets make test` as the final broad gate after the native rebuild. No startup/transport changes are planned. Check `git diff --check`, review against freshly fetched `origin/main`, report constraints impact, and obtain reviewer PASS before final commit. Required PR/merge-group CI remains authoritative for integration.
