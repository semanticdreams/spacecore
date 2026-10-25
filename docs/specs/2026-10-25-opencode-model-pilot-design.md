# Bounded OpenCode model and responsibility pilot

## Goal and authorization

Evaluate `opencode-go/glm-5.3-flash` against `openai/gpt-6.1-sol`, prioritizing
architectural judgment and clean software design. The user has subscriptions for
both, permits consideration of changed responsibilities, and prioritizes useful
evidence within one session rather than a multi-day benchmark. Do not change
production agent definitions or model routing during this pilot.

## Approaches and decision

1. General benchmark scores are fast to consult but weak evidence about these
   agents' ownership, review, and escalation duties.
2. Broad historical task replay is realistic but expensive, confounded by changing
   context, and likely to exceed the requested time horizon.
3. **Selected:** fixed-context architecture/review cases using actual Space Fennel
   modules and a bounded Fennel implementation comparison. This separates design
   ability from ability to execute a stronger model's contract without building a
   benchmark platform. The user explicitly corrected the original synthetic
   Python proposal: project pattern adherence is the primary evaluation target.

Use the existing OpenCode CLI and a thin Python standard-library runner. Preserve
normal internal CLI subscription authentication; never inspect/copy auth files,
home configuration, private logs, credentials, or databases. Trial artifacts are
public-source/synthetic context, not production runtime data.

## Cases and frozen requirements

Create four reasoning cases, answered independently by each model. Source packets
pin exact repository bytes and short public convention excerpts, not worked
solutions from historical lifecycle documentation:

1. **Architecture:** propose opt-in retained logical content state for real
   `assets/lua/tab-view.fnl` while disposing/rebuilding widget subtrees. Supply its
   focused tests. Require ownership, identity, lifecycle, compatibility,
   interfaces, and bounded validation; do not retain widgets as model state.
2. **Review:** assess seeded defective and sound variants of real
   `assets/lua/search-view.fnl`, with focused tests. Defects concern widget versus
   layout ownership, recursive double drop, and listener cleanup. Identify concrete
   failures and avoid speculative redesign or false positives.
3. **Escalation:** request persistent tab state across dynamic tab-list updates,
   duplicate/absent IDs, and external updates without specifying identity or state
   ownership. Identify missing decisions and safe bounded work rather than inventing
   policy or refusing everything.
4. **Evidence handoff:** assess a claimed completed `Sized.set-size` change that
   omits one measurement path or invalidation, with unchanged relevant code supplied.
   Distinguish reported tests from actual behavioral coverage.

One implementation surface is the actual 40-line `assets/lua/sized.fnl` and its
88-line focused suite: add canonical runtime `set-size` without rebuilding its
child. Python may orchestrate calls and evidence; it is not the evaluated language.

Publish these requirements; hold out test inputs, not requirements:

- Both ordinary and constrained measurement use the current requested size.
- Preserve existing nonpositive-axis constraint inheritance.
- Invalidate the wrapper's measurement, not an unrelated root or sibling.
- Preserve child identity/lifetime; changing size never rebuilds or drops it.
- Layouters retain direct transform writes, not dirtying setters during layout.
- Own size state per built instance; do not mutate shared constructor options.
- Follow applicable final-self-literal, factory/build-context, `local`, canonical
  key, and explicit-error conventions.
- Test ordinary/constrained updates, dirtiness, independent instances, and child
  lifetime; preserve existing tests and compatible default behavior.

Compare three implementations from identical baseline bytes: the public feature
brief to GLM (plain substitution); a frozen independently reviewed GPT-authored
contract to GPT; and the identical contract to GLM (hybrid). Include identical
requirements and source in all three. Prepare the contract before outputs; it is
not a reference implementation. Contract effects versus model randomness cannot
be isolated in this sample. TabView separately measures originating architecture.

## Execution and evidence boundaries

Use generated, all-deny trial agents and fresh sessions in a control directory
under `/tmp/opencode` outside repository ancestry. Supply fixed context directly;
candidates return text or complete fixture files, not tool-driven edits. Disable
external plugin/skill discovery where supported. Normal CLI authentication may
operate internally. Do not claim perfect global-instruction/config isolation;
record the same ambient conditions for both candidates and their limitations.

Export only sessions created by the pilot using the public CLI. Verify actual
assistant provider/model IDs, completion, and errors before scoring. Record
requested and reported variants separately; do not transfer GPT variant names to
GLM. Match deployed GPT roles (`xhigh` reasoning, `high` implementation) where
supported. Missing actual identity or authentication is an explicit preflight
failure, not evidence about model quality. Never fall back to another model.

The user clarified that executing candidate code is unnecessary for this pilot:
comparative architectural analysis and stronger-model assessment are the target.
Keep returned Fennel as inert response text and parse requested filenames against
an exact allowlist; never apply, import, compile, or execute candidate code.
Label implementation assessment static-only, with no test-pass claim. Do not
build Space or add sandbox infrastructure for this evaluation.

Record wall time and available input/output/reasoning/cache usage without double
counting. Preserve unknown usage as unknown and reported zero cost as reported
zero, not proof of zero subscription cost. Do not infer actual charges, quota
consumption, or financial savings from token totals alone.

## Scoring and time limits

Freeze prompts, fixture hashes, seeded answers, and rubric before candidate calls.
Weights: architecture/design 35, correctness/invariants 30, validation 15,
scope/escalation 10, evidence accuracy 10. Score each dimension 0–4 (absent or
violated; materially deficient; incomplete; solid; exceptionally clear/complete
without needless machinery). Material defects and fabricated evidence remain
explicit failures regardless of average score. Sound controls measure restraint.

Use independent fresh GPT reviewer contexts, anonymized artifact labels, actual
test/static evidence, and frozen answers. This is automated judgment, not human
ground truth; same-family bias and imperfect blinding are limitations. Report
concrete findings and per-case results rather than an overall winner alone.

Budget: 11 primary candidate calls, at most 2 repeats total (paired architecture
repeat only for a score gap at most five points or low-confidence judgment),
5 independent judging calls plus at most 1 repeat judgment. Reasoning/judging
deadline 3 minutes each, implementation deadline 6 minutes each; overall model
execution cap 90 minutes. No repair conversations or retries until success.
Infrastructure failures, timeouts, and incomplete sessions are distinct outcomes.

## Deliverables, validation, and limits

Deliver a small reproducible runner with mocked tests, frozen cases and static
acceptance vectors, and a concise report with a proposed responsibility split.
Keep large raw own-session artifacts outside version control; commit
sanitized summaries and sufficient synthetic artifacts for independent review.
Validate runner handling of malformed output, identity mismatch, completion/errors,
timeouts, unsafe paths, and missing usage. Candidate test code is a proposed
validation strategy to inspect, not executed evidence.
Review preparation independently before calls and results independently before
reporting findings. All candidate compile, constraints, and focused runtime tests
are explicitly not run by design. Assess whether each response understands the
native compile-first, constraints-second, focused-test-third workflow, including
asset/macro environment and runtime-freshness prerequisites. Do not use system
Lua/Fennel as substitute evidence. The workspace has no `build/` directory; do not
start a build. PR CI is the integration gate for any landed orchestration tooling;
production agent configuration remains unchanged.

This is a screening pilot, not statistical proof. Fixed context excludes live
repository search, autonomous tools, recovery loops, long-context performance,
C++ bindings, and broad refactors. Static-only implementation review cannot
establish compilation or runtime correctness. Treat successful shared-contract
execution as evidence for narrower GLM duties, not authorization to downgrade architecture or
review gates. Final recommendations may change role boundaries, but adopting
production routing changes is a separate evidence-informed task.
