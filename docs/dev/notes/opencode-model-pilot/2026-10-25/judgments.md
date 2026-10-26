# Independent excerpt judgments — labeled summaries

These are **summaries of controller-provided judgments**, not full verbatim JSON
reviewer reports. Four fresh independent contexts were configured as
`openai/gpt-6.1-sol`, `xhigh`; their actual provider identity was not externally
verified. Each assessed author-blinded substantive excerpts against repository
source without seeing records, model identity, timing or usage. The map at the end
was supplied after judgments. The reporting agent made no new judging calls.

The approved plan's Recorded execution limitation amendment changes the reporting
scope: no complete-artifact dimension scores, aggregate score or overall ranking.
The original 0–4 rubric and weights (architecture 35%, correctness 30%, validation
15%, scope/escalation 10%, evidence accuracy 10%) remain frozen. Partial coverage
does not justify invented numbers or extrapolated whole-answer approval.

Native validation was NOT RUN by user design. Suggested production compile,
constraints and test gates are future-adoption requirements, not pilot defects.
No reviewer supplied runtime evidence. Same-family bias, style recognition,
excerpt selection, small sample and incomplete paired coverage limit all findings.

## Architecture K

Reviewer context: `ses_e8cae9f49ffeTmkFHf3BNjFnyV`.

**Strengths:** per-built-view state storage, default opt-in compatibility and the
explicit requirement not to retain live widgets are appropriate. These do not
establish the claimed enforcement guarantee.

**Material architectural defect — writable committed-state aliases:** the builder
receives live `cell.data`, the save hook is optional for continuous writers, and a
state-table accessor exposes live state. A builder can insert a callback closing
over a widget into that already committed table. Validation at initialization or
only of a later save-hook return cannot prevent this; the prior store can already
be changed before rejection. Calling a live table “read-only” does not make it so.
The bounded conceptual correction is to validate a full new snapshot before
publishing it and avoid writable aliases into committed state, not to build an
arbitrary state-management framework.

**Material transition defect — detach before fallible work:** the code removes
the content layout before invoking fallible save/validation. If the caller catches
that failure, the old widget remains alive but detached, with old current-tab
bookkeeping. Selecting that same index remains a no-op and cannot restore it.
Validation/error ordering and commit semantics need design-level correction.
This is grounded in `assets/lua/tab-view.fnl:235–266`, whose switch/reload paths
establish the compatibility and attachment lifecycle the proposal must preserve.

**Concrete snippet defect:** `((item.init-state))` invokes the initializer and
then attempts to call its returned plain table. Separate minor issues include
`let` rather than `local` and placeholder uniqueness validation. Those are not a
substitute explanation for the ownership and transition defects.

**Limit:** no GPT architecture answer completed. The excerpts support these
concrete findings, not a comparative architecture score or full-artifact judgment.

## Search review M

Reviewer context: `ses_e8cae9ee7ffeUJZW9Uz1JwtTze`.

**Observed fixture coverage: 3/3 seeded defects detected; 0/1 sound-control false
positives.** These are fixture counts, not general reviewer accuracy estimates.

| Variant | Confirmed assessment and ownership evidence |
| --- | --- |
| A | Layout-only drop skips widget teardown. `Layout.drop` detaches/clears layout children, not child widgets; restore the owning root widget drop. |
| B | Flex root drop already drops owned children. Manual Input/ListView drops are redundant; the first repeated child drop errors. Keep one root drop. |
| C | A fixture-only caller-owned external signal outlives the view. Disconnecting the callback from the input signal with allow-missing silently leaves the original external listener attached. Disconnect that exact callback from the external source, without clearing the shared signal. |
| D | Correctly disconnects from the same external source, then drops the root once; accepted as sound. |

Relevant source: `assets/lua/search-view.fnl:69–74,103–115`,
`assets/lua/layout.fnl:337–371`, `assets/lua/flex.fnl:215–226`,
`assets/lua/input.fnl:910–941`, `assets/lua/input-model.fnl:319–321` and
`assets/lua/signal.fnl:38–63`. The external signal is a seeded fixture, not a
baseline SearchView feature. M correctly did **not** turn omission of redundant
baseline input disconnection into a lasting leak: InputModel.drop clears its
signals. M suggests filtered `tests.fast` but omits a concrete `TEST_FILTER`
assignment: `TEST_FILTER='SearchView'` would select existing tests; without the
filter, the command runs the broader fast suite, not an unsupported command.

**Limit:** the GPT comparator timed out. One strong local result does not support
replacing general reviewers or making a scout an approval gate.

## Sized handoff S and T

Reviewer context: `ses_e8cae9ea4ffeMlg773ml1L4PUq`.

**Both:** correctly identify that the synthetic patch updates wrapper measurement
but leaves child maxima/fallback reading `opts.size`. Both reject the synthetic
completion claim because unchanged original tests do not cover the setter. They
credit existing per-build state, wrapper dirtiness and child identity rather than
inventing those as missing defects. Source: `assets/lua/sized.fnl:8–22` and the
frozen `sized-handoff` edits; the real original test suite is constructor/transform/
drop coverage, not proof of this new feature.

**T's more discriminating proposed tests:** varying-axis examples (including
current `(0,-2,9)` under parent maximum `(10,20,30)` producing wrapper `(0,-2,9)`
and child maximum `(10,20,9)`); nil **and** empty constraints; positive fixed size
larger than the parent's maximum to preserve no-clamping behavior; dirtiness from
a clean state or root queue; A/B builds sharing options plus new factory C; and
all five direct transforms (size, position, rotation, depth and clip).

**S's command defect:** unquoted semicolons in `FENNEL_PATH` and
`FENNEL_MACRO_PATH` split the proposed shell command. The exact command is retained
in responses. This was a proposed command, not fabricated passing test evidence.

**Limit:** one completed pair of excerpt reviews supports this specific difference
in test precision, not an overall model-quality ranking.

## Sized implementations U and V

Reviewer context: `ses_e8cae9e6effecGvXqBUE8bBKOm`.

### U — substantive defects, separate from malformed JSON

- `resolve-child-max` references free `self`; a sibling function's argument is not
  a lexical binding for this function. The child resolver cannot reliably obtain
  the current requested size through that name.
- `(local new-size (...))` uses the vararg expression as callee, rejected by the
  vendored Fennel source. This is static source analysis, not a claimed compile run.
- Even after syntax repair, the userdata rejection rejects valid `glm.vec3`
  values. `src/lua_glm.cpp:73–150` registers the engine vector as a usertype.
- Proposed tests call the ordinary options table as if it were a build closure
  (`(opts {})`), assert a dirty flag already true, and compare a child's chosen
  measure rather than spying on the maximum constraints actually forwarded.

U thus needs substantial rescue, not merely JSON formatting repair. Its generation
finished, but the original malformed root JSON remains `invalid_answer`; it was
not repaired or executed to obtain these observations.

### V — bounded positive static finding

No blocker was identified in the supplied complete production-source excerpt.
One per-build `requested-size` binding drives ordinary/constrained wrapper
measurement and child maxima/fallback. The setter dirties the wrapper **before**
assigning the new binding, so an in-pass dirtying rejection cannot first mutate
the requested size. It retains the direct layouter/drop and final widget literal.
No new framework is needed. Substantive test excerpts looked sound, but full test
source and runtime correctness remain unknown to this review.

**Confounders:** U received the plain brief; V received the conceptual GPT
contract. This is not pure model isolation. The GLM contract arm timed out, so the
contract's benefit for GLM and the proposed hybrid division remain **untested /
inconclusive**. No passing compile/test or full-artifact quality score follows.

## Unavailable escalation judgment

Both escalation candidates timed out without final text. The fifth judgment is
unavailable, not a zero-quality score or an inference about escalation ability.
There are no paired architecture/review/escalation baselines and no repeat pair.

## Post-judgment unblinding map

| Label | Candidate / arm | Trial |
| --- | --- | --- |
| K | GLM 5.3 Flash | tab-architecture-glm |
| M | GLM 5.3 Flash | search-review-glm |
| S | GLM 5.3 Flash | sized-handoff-glm |
| T | GPT 6.1 sol | sized-handoff-gpt |
| U | GLM 5.3 Flash, plain brief | sized-glm-plain |
| V | GPT 6.1 sol, conceptual contract | sized-gpt-contract |

This qualitative screen supports retaining strong architecture, ownership and
review authority. Bounded cheap-worker evidence gathering or implementation may
be worth a separate trial, with strong original-artifact review and objective
escalation conditions. It does not support production routing changes, financial
claims, a demonstrated hybrid success, or publication/integration approval.
