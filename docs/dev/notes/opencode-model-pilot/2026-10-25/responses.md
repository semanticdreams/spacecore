# SELECTED VERBATIM EXCERPTS — not full final responses

These are controller-provided selections from the pilot, not a transcript or a
full-artifact review package. This reporting agent did not read external full
answers. Full final text is retained **only in the original allowed pilot runtime
root**, outside Git, with ephemeral retention. Original full-answer SHA-256 values
are in [records.json](records.json); they do not hash this excerpt file and do not
prove correctness. Private reasoning and raw exports are not reproduced.

Quoted/code selections below preserve supplied wording and mistakes. Code blocks
are inert. Ellipses indicate omitted material, not repaired prose. Separately
labeled summaries and normalized presentations are **not** exact raw-response
transcriptions. Unblinding is in [judgments.md](judgments.md); reviewers saw labels
and source, not model identities, timing or usage. Five timeout trials have no
final answer to excerpt. U is an invalid JSON answer, not a repaired source file.

## K — architecture selections

Controller-supplied verbatim prose selection; `...` marks an omission:

> Enforcement, not convention only: a validate-plain-data walker accepts strings, numbers, booleans, nil, and plain (metatable-free) tables recursively ... It runs at three commit boundaries: cell creation (init-state), every save-state merge, and get-retained-state is exempt (read-only). This mechanically guarantees live widgets/layouts/focus/render references can never be cached as logical state.

Two further verbatim phrases from the supplied selection:

> builder is invoked with the cell’s live data table

> items whose content writes into the cell continuously don’t need it

The latter refers to the optional `save-state` hook. The contrast between these
phrases and the claimed mechanical guarantee is substantive, not just stylistic.

Verbatim supplied transition code selection:

```fennel
(layout:set-children [button-row.layout])
(when self.current-cell
  (when (and retain? (. self.items-by-id self.current-cell.id).save-state)
    (local captured ((. (. self.items-by-id self.current-cell.id) :save-state) self.current-tab))
    (validate-plain-data captured self.current-cell.id)
    (each [k v (pairs captured)] (tset self.current-cell.data k v)))
  (set self.current-cell.active? false))
(self.current-tab:drop)
(set self.current-tab nil)
```

Verbatim initializer snippet supplied separately:

```fennel
(if item.init-state ((item.init-state)) {})
```

## M — search review coverage

**Controller-supplied verbatim review summary, not asserted to be candidate
wording or a full candidate final response:**

> A breaks child teardown (layout-only drop); B double-drops owned children (first drop errors); C leaves its external listener attached due to disconnecting from the wrong signal via a silently-allowed no-op; D is correct.

The supplied judgment credits 3/3 seeded defects and 0/1 sound-control false
positives. No additional direct candidate passage was supplied for this report;
do not reconstruct a full review from the summary. The repository cases contain
the exact mutations and evaluator expectations.

## S — handoff selections

Verbatim supplied sentence:

> Note the failure is asymmetric and therefore sneaky: the wrapper’s own reported measure updates, but the child’s constrained measurement does not.

Verbatim proposed command, **not executed**. Its unquoted semicolons are preserved:

```text
SPACE_DISABLE_AUDIO=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data SKIP_KEYRING_TESTS=1 SPACE_ASSETS_PATH=$(pwd)/assets FENNEL_PATH=$(pwd)/assets/lua/?.fnl;$(pwd)/assets/lua/?/init.fnl FENNEL_MACRO_PATH=$(pwd)/assets/lua/?.fnl;$(pwd)/assets/lua/?/init.fnl ./build/space -m tests.fast:main
```

## T — handoff selection (normalized presentation)

The controller supplied this substantive excerpt with formatting normalized;
**do not treat its punctuation/line layout as exact raw text**:

> The required results are: Wrapper measure: (0,-2,9). Child maximum: (10,20,9)

Context supplied by the controller: constructor size `(4,5,6)`, current size
`(0,-2,9)`, parent maximum `(10,20,30)`. Further test-design findings are summarized
in judgments, not invented here as verbatim candidate prose.

## U — plain implementation selections

Verbatim supplied production-code selection, preserving defects:

```fennel
(fn current-size [self] (if size size self.size))
(fn resolve-child-max [constraints]
  (local max-size (and constraints constraints.max))
  (local preferred (current-size self))
  (if max-size (glm.vec3 (if (> preferred.x 0) preferred.x max-size.x)
                       (if (> preferred.y 0) preferred.y max-size.y)
                       (if (> preferred.z 0) preferred.z max-size.z)) preferred))
(fn set-size [self ...]
  (local new-size (...))
  (when (= (type new-size) :userdata)
    (error "Sized:set-size requires an explicit size")
    (os.exit 1))
  (set size new-size)
  (self.layout:mark-measure-dirty))
```

Verbatim supplied test-code selection:

```fennel
(local opts {:size (glm.vec3 1 1 1) :child child-a.builder}) (local sized-a (opts {})) (set opts.child child-b.builder) (local sized-b (opts {}))
```

The original root JSON was malformed at EOF, position 14460, expecting a comma
delimiter. These code selections do not repair its protocol failure or establish
valid complete file extraction. No candidate source was written or run.

## V — contract implementation selections

Verbatim supplied main production-code selection. The controller identifies the
production-source excerpt assessed by the reviewer as complete; this file selects
only the main changed forms and the final literal, **not the whole source**:

```fennel
(var requested-size opts.size)
(fn measurer [self] (child.layout:measurer) (set self.measure requested-size))
(fn resolve-child-max [constraints]
  (local max-size (and constraints constraints.max))
  (if max-size (glm.vec3 (if (> requested-size.x 0) requested-size.x max-size.x)
                       (if (> requested-size.y 0) requested-size.y max-size.y)
                       (if (> requested-size.z 0) requested-size.z max-size.z)) requested-size))
(fn constrained-measurer [self constraints]
  (child.layout:measure-constrained {:max (resolve-child-max constraints)})
  (set self.measure requested-size))
(fn set-size [self new-size]
  (assert new-size "Sized:set-size requires new-size")
  (self.layout:mark-measure-dirty)
  (set requested-size new-size))
```

Verbatim supplied final widget literal:

```fennel
{: child : layout : set-size : drop}
```

Controller summary, **not verbatim source**: original direct layouter and drop
remain unchanged. Test findings rest on substantive excerpts, not the full test
source. No absence-of-blocker finding implies compile or runtime success.
