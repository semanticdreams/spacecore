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
3. **Selected:** fixed-context architecture/review cases plus a bounded executable
   implementation comparison. This separates design ability from ability to
   execute a stronger model's contract without building a benchmark platform.

Use the existing OpenCode CLI and a thin Python standard-library runner. Preserve
normal internal CLI subscription authentication; never inspect/copy auth files,
home configuration, private logs, credentials, or databases. Trial artifacts are
public-source/synthetic context, not production runtime data.

## Cases and frozen requirements

Create four reasoning cases, answered independently by each model:

1. **Architecture:** extend a small synchronous Python command-availability
   service with role/evidence-aware projection. Require ownership, lifecycle,
   interfaces, and an implementable cross-file contract.
2. **Review:** assess a seeded defective patch and a sound patch; identify concrete
   failures while avoiding speculative redesign and false positives.
3. **Escalation:** a separate request introduces automatic role switching and
   asynchronous updates without specifying ownership/delivery semantics. Name
   required decisions and safe bounded work rather than inventing policy.
4. **Evidence handoff:** a claimed completed change omits the authoritative
   state-layer revision/notification update; all relevant code is supplied.

The architecture case uses a roughly 150–180-line baseline across
`command_policy.py`, `workspace_state.py`, and `workspace_service.py`. Commands
are inert data, never shell execution. Planner, implementer, reviewer, and
capability role names ground the task in the project's agent separation without
claiming this is a real application subsystem.

Public API: immutable `Snapshot(enabled, evidence, revision)`;
`WorkspaceStore.snapshot`, `set_enabled`, `set_evidence`, `subscribe`;
`WorkspaceService.commands(workspace, role=None)`,
`watch(workspace, callback, *, role=None)`, and `close`.

Eligibility: `plan` belongs to planner with no evidence requirement; `apply` to
implementer requiring `planned`; `review` to reviewer requiring `validated`;
`publish` to capability requiring `validated` and `approved`.

Publish these invariants to candidates; hold out test inputs, not requirements:

- Role omitted preserves existing enabled order and role-neutral behavior.
- Explicit roles return exactly enabled eligible commands; unknown roles error.
- Semantic enabled/evidence changes increment revision once and notify once;
  no-op changes do neither; snapshots are immutable.
- Reads are immediately fresh and caches do not leak across roles/workspaces.
- Watches deliver immediately once, then exactly once per projected tuple change.
- One upstream subscription per active service/workspace; reads create none;
  removing one watcher preserves others; removing the last releases upstream.
- Unsubscribe/close are idempotent; closed service reads/watches error and no
  callbacks reach it.
- Services on the same store have independent lifetimes; replacement is fresh.

Compare three implementations from identical baseline bytes: GPT contract to
GPT, GLM contract to GLM, and the identical GPT contract to GLM. Include the same
explicit invariants with each implementation prompt. Preserve weak plans and
escalations instead of silently repairing them.

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

Apply returned fixture files only to new scratch copies using an exact filename
allowlist and reject unsafe paths. Execute generated code only inside an available
credential-free OS sandbox with no network and bounded resources; do not install
host packages or widen privileges. If unavailable, continue reasoning evaluation
and label implementation assessment static-only, with no test-pass claim.

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

Deliver a small reproducible runner with mocked tests, frozen cases and fixture
contract tests, and a concise evidence report with a proposed responsibility
split. Keep large raw own-session artifacts outside version control; commit
sanitized summaries and sufficient synthetic artifacts for independent review.
Validate baseline tests before calls, runner handling of malformed output,
identity mismatch, completion/errors, timeouts, unsafe paths, and missing usage.
Review preparation independently before calls and results independently before
reporting findings. No Space build, Fennel suite, or production config change is
required; PR CI is the integration gate for any landed tooling.

This is a screening pilot, not statistical proof. Fixed context excludes live
repository search, autonomous tools, recovery loops, long-context performance,
Fennel/C++, and broad refactors. Treat successful shared-contract execution as
evidence for narrower GLM duties, not authorization to downgrade architecture or
review gates. Final recommendations may change role boundaries, but adopting
production routing changes is a separate evidence-informed task.
