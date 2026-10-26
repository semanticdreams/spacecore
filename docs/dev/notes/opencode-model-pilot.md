# Static Space Fennel model pilot

## Result and decision

> **User-superseded routing recommendation (2026-10-25):** The conservative
> strong-model routing advice below is historical, not current policy. The user
> subsequently chose GLM for all sixteen ordinary project roles plus one bounded
> read-only GPT expert, with mandatory dual input on every architecture/design/
> system-contract decision. See the [current workflow](../features/opencode-agent-workflow.md#glm-default-roles-and-bounded-expert-consultation).
> Pilot observations, findings and execution limits remain unchanged; this policy
> choice does not demonstrate hybrid success or model competence.

**Qualitative screening only: retain the current strong-model architecture and
review gates. Do not change production model routing on this evidence.** Eleven
primary candidate attempts ran exactly once: five effective complete answers, one
generation-complete but invalid implementation answer, and five timeouts. There
were no repeats. Four fresh configured GPT reviewer contexts independently judged
author-blinded **selected verbatim excerpts**, not complete artifacts, against
repository source. Neither escalation answer nor the GLM contract implementation
completed. There is no numeric ranking or demonstrated hybrid success.

This compares `opencode-go/glm-5.3-flash` and `openai/gpt-6.1-sol` on actual Space
Fennel, not Python implementation ability. Candidate code was never applied,
compiled, imported or executed. Native compile checks, constraints and tests are
**NOT RUN by user design**, not a model-evaluation defect. Proposed tests are not
passing tests. Production source, tests, agents and routing remain unchanged.

Authority: the [design](../../specs/2026-10-25-opencode-model-pilot-design.md) and
the approved [plan's Recorded execution limitation amendment](../../plans/2026-10-25-opencode-model-pilot.md#recorded-execution-limitation).
The amendment supersedes planned complete-response retention in Git, five
complete-artifact judgments, and numeric scoring. The frozen rubric was not tuned
after seeing outcomes.

## Evidence and provenance

- [records.json](opencode-model-pilot/2026-10-25/records.json): all eleven attempts,
  requested/verified identities, variants, timings, supplied usage and answer hashes.
- [responses.md](opencode-model-pilot/2026-10-25/responses.md): **SELECTED VERBATIM
  EXCERPTS**, with omissions and normalized presentation labeled; not full answers.
- [judgments.md](opencode-model-pilot/2026-10-25/judgments.md): labeled summaries of
  four independent findings, their limits, reviewer provenance and post-judgment map.

Execution facts, original answer SHA-256 values and reviewer findings were supplied
by the controller from its verified own-session results/recovery. This reporting
agent read repository sources, not external exports, private reasoning, auth,
home configuration, logs or databases. It did not personally reread full answers
or reproduce external hash verification. Full final text remains **only in the
original allowed pilot runtime root**, outside Git; retention is ephemeral. A hash
identifies bytes, not correctness, and cannot replace access to a full artifact.
Raw capture hashes were not supplied here and are explicitly unknown in records.

## Frozen design and collection

Source pin: `d6e3742f123e4fde688453eeba8e3bb9da328238`.
`scripts/evals/opencode_pilot_cases.json` freezes public briefs, source/excerpt
hashes, seeded review variants, evaluator-only expectations, static vectors,
rubric and conceptual GPT-authored contract. Cases SHA-256:
`e53ee84ec1a796608091845687107c84a696e998f6545bc746f8cf796a55cd7a`.
Records distinguish the conceptual contract hash from the shared rendered
implementation packet hash. The contract was prepared and reviewed before trials,
not generated as an extra candidate call; it contains no reference code.

Preparation selects public fields rather than sending the cases JSON wholesale.
It checks pinned public Git blobs, hashes exact rendered packet bytes, and reserves
fresh trials. Both contract arms receive identical packets; the plain arm omits
only the conceptual contract. No prompt, rubric, source, expectation or contract
changed during collection repairs.

The four reasoning cases were opt-in static TabView logical-state retention;
SearchView teardown review with three seeded defects and one sound control;
TabView escalation under undefined dynamic identity/external ownership; and a
Sized handoff whose setter leaves child constraints reading constructor size.
Three inert Sized implementations covered GLM plain brief, GPT contract, and GLM
contract. Required behavior includes both wrapper measurement paths, current-size
child maxima/fallback, per-build independence, wrapper dirtiness, stable child
lifetime and unchanged direct transform propagation.

OpenCode CLI 1.18.35 used fresh explicit all-deny trial agents, exact requested
models, public run/export, no candidate tools/delegation/repair loop/fallback.
GPT variants requested/sent were `xhigh` for reasoning and `high` for
implementation; only completed GPT exports reported those variants. GLM's variant
is unreported, not assumed equivalent. Normal internal subscription authentication
was retained without inspecting credentials or merged home configuration.

### Outcome table

Wall times include original collection; recovery is separate. Missing usage or
primary actual identity remains unknown, not zero or inferred from request flags.

| # | Trial | Effective outcome | Original wall (s) | Answer label |
| --- | --- | --- | ---: | --- |
| 1 | tab-architecture-glm | complete, same-session export recovery | 141.884 | K |
| 2 | tab-architecture-gpt | timeout | 180.088 | — |
| 3 | search-review-gpt | timeout | 180.064 | — |
| 4 | search-review-glm | complete | 100.026 | M |
| 5 | tab-escalation-glm | timeout | 180.072 | — |
| 6 | tab-escalation-gpt | timeout | 180.054 | — |
| 7 | sized-handoff-gpt | complete | 172.029 | T |
| 8 | sized-handoff-glm | complete | 21.208 | S |
| 9 | sized-glm-plain | invalid_answer, malformed root JSON | 58.038 | U |
| 10 | sized-gpt-contract | complete | 169.347 | V |
| 11 | sized-glm-contract | timeout | 360.074 | — |

Reasoning limits were 180 s and implementation limits 360 s. The persisted
90-minute absolute deadline was `1792919197.2382023`; later human pauses exceeded
it, and no further candidate calls occurred. No architecture pair completed, so
the paired repeat rule could not be applied. There was no best-of-N selection.
Framework repairs and process-agent overhead are not additional candidate trials.

### Collection limitations, not model-quality findings

1. The first GLM generation finished, but its own public export to PIPE returned
   exit 0 with exactly 65,536 bytes, an invalid JSON prefix. Regular-file export of
   the **same session** returned 73,449 bytes with final text exactly equal to the
   original run text. The independently reviewed transport fix and 2.589 s recovery
   preserved the original `infrastructure_error` / `JSONDecodeError`. There was no
   regeneration; this remains one attempt and one usage total. This establishes
   stdout-destination-dependent truncation, not the CLI's exact internal cause.
2. The CLI later inserted only its known top-level `$schema` annotation. Reviewed
   compatibility checks remove exactly that field and reconstruct the original
   frozen config hash; prompt, permission, unknown-schema or other behavioral
   changes are rejected. No relaxation of the candidate contract occurred.
3. Exported directory metadata differed from the requested control-directory cwd.
   All-deny agent metadata does **not** prove ambient global-instruction/config or
   effective cwd isolation. Do not claim a hermetic benchmark.
4. Controller followups exported only each timeout's own session: expected actual
   model IDs were present, but finish/completed were null, no final text or tools
   were present, and no late answers became usable. Primary timeout identity and
   usage fields remain null; followup identity is recorded separately.
5. U's generation completed but strict root JSON ended at position 14460 with
   `Expecting ',' delimiter`. It contained code, not Markdown fences. It was not
   repaired into a valid artifact. Static excerpt findings are separate from that
   protocol failure.

## What the independent excerpt reviews support

| Area | Concrete evidence | Bounded conclusion |
| --- | --- | --- |
| Architecture K (GLM) | Correct per-build store, opt-in compatibility and no widget caching as a goal. But live committed-state aliases defeat the claimed mechanical plain-data guarantee; fallible save follows detach; initializer snippet double-calls a returned table. | Confident architectural narrative is not sufficient. State publication and error lifecycle need strong review, not just syntax repair. GPT comparator unavailable. |
| Search review M (GLM) | Detects 3/3 seeded defects, accepts the one sound control (0/1 false positives), checks actual teardown ownership rather than inventing an input-signal leak. | Useful local advisory review in this tiny fixture; not evidence for replacing general reviewers. GPT comparator unavailable. |
| Sized handoff S/T (GLM/GPT) | Both find stale child constraint derivation and missing setter coverage, while crediting correct wrapper dirtiness. T supplies more discriminating vectors and observations; S's proposed shell command has unquoted semicolons. | Both catch the central handoff defect here. Proposed-command error is not fabricated execution. |
| Implementation U/V (GLM plain / GPT contract) | U has free `self`, invalid vararg-callee syntax, rejection of normal vec3 userdata and broken test construction/oracles. V's supplied complete production-source excerpt has no identified blocker; substantive test excerpts look sound. | Direct U needs substantial rescue. V is promising static evidence, not a runtime pass or full-test-source assessment. Different contract conditions confound a pure model comparison. |
| Escalation / hybrid GLM | Both escalation answers and GLM contract implementation timed out. | No judgment of escalation quality and **hybrid benefit untested/inconclusive**. |

Reviewers were four independent fresh contexts configured as GPT 6.1 sol `xhigh`;
their actual provider identity was not externally verified. They saw blinded
excerpts and source, not records/model/timing/usage. Same-family bias, recognizable
style and excerpt-selection bias remain. No full-artifact dimension scores,
aggregate scores or overall quality ranking are justified. The original 0–4 rubric
and 35/30/15/10/10 weights remain frozen, not replaced with post-hoc metrics.

## Responsibility recommendation

Do **not** replace the architecture lead, planner, reviewer, debug advisor,
adjudicator, or direct fast-dev/live-dev primaries with GLM on this sample.
The strong model must choose and review critical ownership, transitions and
interfaces, and inspect original code/requirements rather than trusting a cheap
worker's confidence or summary.

A next, separately authorized pilot could test this bounded split:

- **Strong architect:** define the owning abstraction, invariants, interface,
  error/cleanup lifecycle and observable test contract before delegation.
- **Cheap worker:** bounded implementation or evidence extraction/local scouting;
  no approval authority. Local search/scout wrappers are hypotheses for a future
  trial, **not capabilities tested here**.
- **Strong gate:** inspect the original artifacts and requirements, verify
  independent evidence, and require escalation for scope changes, state ownership,
  public API changes or lifecycle ambiguity. Native production validation would
  gate future adoption, not retroactively invalidate this static pilot.

A cheap scout is advisory, not a mandatory extra layer whose overhead is presumed
to save cost when the final gate remains unchanged. Contract-driven GLM execution
is an interesting hypothesis, not a validated hybrid result. Keep production
configuration untouched; trial adoption separately rather than auto-changing it.

Usage is per unique assistant message. Supplied totals already include reasoning;
do not add it again or count recovered exports twice. Missing timeout usage is
unknown. Reported cost zero is not free service; subscription charges, quota
impact and effective prices are unknown. No dollar or quota-savings claim follows
from these timings or provider-reported fields.

## Offline verification and scope

From the repository root, the evidence-only handoff runs:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/tests -p 'test_eval_opencode_pilot.py' -v
python3 -m json.tool docs/dev/notes/opencode-model-pilot/2026-10-25/records.json >/dev/null
git diff --check
```

The complete 48-test runner suite uses mocks, disposable synthetic fixtures,
public pinned Git source and deterministic subprocesses; it does not call models
or run Fennel. Its own temporary test fixtures are not reads of pilot runtime
artifacts or denied sources. It covers preparation/hash integrity, exact identity,
own-session/completion checks, inert file parsing, usage deduplication, deadlines,
no duplicate trials, large-output capture, recovery preservation and schema
compatibility. It cannot verify externally retained answers or model correctness.
JSON/count/hash reconciliation and scoped diff review check the report itself.

Compile check: **NOT RUN**. Constraints: **NOT RUN**, impact **not applicable**.
Native tests: **NOT RUN**. No production Fennel changed; candidate execution is
explicitly outside scope. This documentation checkpoint is for independent Task 2
review, not approval, publication, integration or a ready-to-merge claim.
