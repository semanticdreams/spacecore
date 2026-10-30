# Repository Guidelines

Be extra rigorous; I'm at risk of losing my job at my hospital.
Don't be afraid; Hesitancy will hold us back.
Clean design is important, refactor when reasonable.

## Fast-dev workflow exception

For the user-selected `fast-dev` primary and user-selected `live-dev` primary only,
their prompts and the shared `fast-dev-wrap-up` skill override conflicting process
rules below and those imported by domain skills. These exact identities edit,
debug, validate, and commit directly: fast-dev on its long-term `fast-dev`
branch, live-dev on its long-term `live-dev` branch. These branches are
single long-term branches (exactly those names, no topic suffix) because the
primaries build and fix multiple things in quick succession: batches of
successive tasks accumulate on the branch between integrations, and after each
merged batch the branch is synced with a safe merge from `origin/main`.
Checkpoints are local only; no
mandatory design/planning docs, implementation or capability workers, advisor
gates, per-change review, or verbose commit templates. Short intent-focused
local commits are sufficient. Ordinary completion or a commit request does not
authorize publishing; integration requires explicit user wrap-up authorization.
The selected caller must use its own corresponding branch, not the other's.
Live-dev establishes manual mode before editing and explicitly refreshes after
validated changes, with no filesystem watching or lifecycle confirmation prompts.
The default `supervisor` is unchanged.

This routine-advisor exemption **does not waive targeted expert consultation**:
its direct ownership and one observational wrap-up review do not remove
consultation triggers. Ordinary design decisions still need
evidence-backed rationale without expert dispatch. Live manual mode is required
before edits; validated code changes require explicit refresh. Consultation alone
does not require app lifecycle actions.
Wrap-up uses one observational `fast-dev-reviewer` review of the whole branch;
fixes are direct, followed by self-review and revalidation, not mandatory
independent re-review per fix. Use raw Git/GitHub for this authorized lifecycle.

Retain Space technical standards, domain guidance, validation commands, and
evidence-based debugging. Do not integrate with unresolved material defects or
required validation failures; diagnose and fix them rather than bypass them.
Environment isolation, not narrow tool permissions, bounds these primaries' authority.
For all other agents, retain their existing process and permission contracts; this
exception does not change an already-running agent's rules.

## Autonomous workflow decisions

Within the authorized task, establish scope and evidence, choose a proportionate,
reversible, contract-consistent action, use the applicable workflow lane, record
the rationale and continue. Routine technical, editorial and recovery decisions
need no human approval; an ordinary architecture choice is not itself a human-owned
policy question. Investigate uncertainty and use required consultation rather than
guessing or treating every choice as a blocker.

The receiving controller must triage worker NEEDS_CONTEXT/BLOCKED reports and
adjudicator escalations: inspect the actual missing evidence or decision, gather
permitted evidence and required advice, reconcile it, and resume the worker through
the existing lane. These reports are not automatically questions for the human.
Continue separable permitted work while dependent work is paused. Actual
resource/evidence exhaustion produces truthful incomplete status with concrete
blockers and unfinished obligations, not a request for routine retry approval or
an invented success.

This grants no new authority. Preserve strict implementer → independent reviewer
→ pass and fast/live direct ownership, consultation triggers, capability refusals,
credential/access boundaries, explicit checkpoints, explicit publication authority,
and all validation, clean-tree, current-main, protected-test and merge-queue gates.
Unknown product/API/data policy, unauthorized destructive actions, unsafe-history
decisions and genuine permission/safety boundaries remain human-owned. An explicit
immutable-publication restriction is a real conflict; the mere presence of a
published source is not. Do not bypass a wrapper refusal, expand scope or invent
policy because the user is unavailable or time is short.

## Preserve development records

Design specs, implementation specs/plans, and development-progress ledgers are
project history: preserve them as tracked repository documentation and include
them in the relevant task checkpoints. Use `docs/specs/` for design specs,
`docs/plans/` for implementation specs/plans, and keep progress ledgers alongside
the related tracked documentation. Do not keep the only durable record in an
ignored scratch directory such as `.superpowers/sdd/`.

Cleanup must not delete these records merely because a task or integration is
complete. Preserve decisions, rationale, implementation progress, validation
results, and meaningful failures/recoveries. Keep secrets, private runtime data,
and raw session dumps out of tracked documentation; required immutable original
handoff payloads may remain private, with safe progress summaries tracked.
This applies to every workflow, including fast-dev/live-dev, but does not make
extra design/planning documents mandatory for otherwise small changes.

## Targeted expert consultation contract

Every project role's `model:` and `variant:` frontmatter lines in `.opencode/agents/`
are authoritative routing configuration; both lines are required, syntax-validated,
editable independently, and never duplicated in instruction bodies. The required
project roles are supervisor, fast-dev, live-dev, planner, implementer, reviewer,
fast-dev-reviewer, debug-advisor, adjudicator, explorer, web-researcher,
config-auditor, git-integrator, github-operator, pr-recovery-operator,
windows-ci-reproducer and expert-advisor. This covers project roles only, not
inherited built-in/hidden/global agents. Use project `explorer` and named workers,
not built-in general/explore as an implicit model fallback. Restart OpenCode after
the reviewed rollout; running sessions retain their loaded roles and must not
claim they already use new routing.

### When expert advice is mandatory

- The **same material failure after one focused repair**, shown by reproduction,
  validation or a violated invariant: consult via `expert-advisor` before another
  dependent repair.
- An evidenced unresolved material technical conflict; an ordinary reviewer
  finding or normal design choice is not automatically such a conflict.
- A critical unresolved permissions/security boundary or irreversible-data
  question before acting across it.

Controllers may request one bounded consultation for consequential technical
uncertainty; optional advice is never a universal prerequisite. Ordinary design
decisions still need evidence-backed rationale and unchanged reuse of reconciled
decisions, but not expert dispatch — do not recreate universal consultation on
material changes without a current reason. Routine execution/review/diagnosis,
expected TDD RED, an initial syntax/typo repair, cosmetic naming, and mechanical
follow-through on an unchanged reconciled design stay ordinary work. Collect
missing evidence directly when permitted. Unknown product/API/data policy is
**HUMAN_DECISION_REQUIRED**; the expert does not set policy.

### One bounded question, evidence, reconciliation and reuse

The requesting worker first states its proposal, responsibilities/contracts,
invariant and rationale. The task-capable controller (supervisor or selected
fast-dev/live-dev) dispatches `expert-advisor` for one question, not a whole task
or implementation. Supply inspectable original source/diff paths or excerpts and
validation evidence, not only summary conclusions. The expert inspects original
evidence.

Every `consultation_request` has exactly these fields:

```json
{
  "decision_scope": "widget save transition ownership",
  "trigger": "software_design",
  "question": "Does the proposed save-before-detach order preserve retained content on failure?",
  "sources": ["path/to/widget.fnl:40-90 and proposed diff in the handoff"],
  "invariant": "Failed saves leave the current child attached and usable",
  "evidence": ["current detach precedes the fallible save"],
  "attempted_fix": null,
  "proposal": "Validate and save before detaching; transfer ownership only on success, preserving the existing owner on failure.",
  "decision_needed": "Confirm the ownership/failure contract before implementation"
}
```

`attempted_fix` is nullable. `proposal` is required and nonempty for design,
architecture or contract decisions; it may be null for other triggers. Expert
output has `decision_scope`, `status` (`answered`, `insufficient_evidence`,
`requires_human`), `finding`, `evidence`, `action`.

The requesting controller records scope, proposal, original evidence, expert
critique and **evidenced reconciliation before dependent implementation** in
existing handoff/progress artifacts. Resolve and validate material findings or
escalate to the human; preference is not grounds to dismiss a material objection.
One consultation per decision scope. Reuse unchanged reconciled decisions without
a repeat consultation tax; material design/contract/assumption changes reopen the
decision. Reconsultation otherwise requires genuinely new material evidence, not
another try for approval. Unavailable expert, insufficient evidence or an
unanswered necessary decision blocks dependent work. Gather permitted evidence or
ask the human; do not loop.

### Fail-closed handoff delivery

The receiving controller (`supervisor` or selected `fast-dev`/`live-dev`) validates
the declared role format, required fields, assignment identity and source/review
range **before consultation, verdict, fix, cap or completion handling**. JSON roles
remain JSON; Markdown plans/reviews remain Markdown where declared. Do not infer
pass from framing. Valid initial and corrected deliveries are only
`ELIGIBLE_FOR_NORMAL_HANDLING`: ordinary semantic processing, **not approval**.

Record in existing handoff/progress artifacts (not a new tracking subsystem):
- Stable identity: task, original author role/session, selected controller/workflow,
  branch, source snapshot, recorded base/head or equivalent range, and review mode.
- `correction_used=0/1`, separate from the identity, not an attempt in the key.
- Immutable original and corrected payloads separately, delivery errors and state.

For an initial eligible malformed delivery with the original author available
and retained author records supporting unchanged facts, stop dependent actions.
Mark `correction_used=1` **before dispatch**, then resume that same author once with
the original assignment/role contract, retained facts and precise delivery errors.
The format-only assignment permits redelivery only: **no code edits, tests, builds,
commits or operations**, overriding ordinary task/checkpoint obligations. No
verdict, findings, evidence or range facts may be rewritten; only unambiguous
assignment metadata copied from the original request may be corrected.
No caller-side fence stripping, aliases, defaults or partial verdict salvage.

Reconstruct missing facts only from retained author records; otherwise use that
role's existing context/evidence-needed or non-approving branch, with
NEEDS_CONTEXT only where supported. There is no universal new status or field:
format-only is an assignment mode, not an extra JSON response key. Controller
bookkeeping is not a worker response-schema extension. Revalidate the correction
against the unchanged declared contract, identity/range and protected facts before
ordinary semantic handling; successful serialization alone grants no verdict.

Autonomous operational recovery: **Reject the unusable delivery, not the
overall task.** An exhausted-correction, changed-fact, stale-snapshot or
unavailable-author delivery is quarantined with immutable failure ancestry, and
the task continues autonomously under existing permissions: an unusable
delivery is evidence about that delivery, never by itself a human permission
question. The receiving controller (supervisor or selected `fast-dev`/`live-dev`)
authorizes explicit replacement work — usually a fresh worker, never
impersonation — to complete a missing or unusable assessment on the same
verified branch and base/head range; no artificial commit or range change is
required. Before replacement dispatch, record in existing handoff/progress
artifacts: predecessor identity and immutable failure ancestry, verified
current local snapshot and complete assigned range, original requirements and
global constraints, observed failure with diagnosis and a concrete changed
strategy, trusted source/diff references with required independent
investigation, established findings and pending consultations/adjudications,
separately labelled untrusted leads from unusable reports for later
verification, and continuing task-wide failure counts with
fix/consultation/resource accounting.

Recovery stays budget- and scope-safe. These counts and obligations are
task-wide across authors, sessions and decomposition; each genuinely new
delivery receives its own ordinary format-correction allowance, which refunds
no ancestor allowance or substantive fix/consultation/resource budget. Usable
adverse assessments are not replaceable for review shopping: they keep the
ordinary fixes, consultation and adjudication route; replacement work must
cover the same complete range, and passing fragments never substitute for
whole-range review. At two task-wide failures with the same signature — a
format-only correction is not a substantive attempt — record a concrete changed
strategy (gather evidence, narrower output, decomposition, or a different
inspection method) before another dispatch; unchanged blind retries are
refused, not the task. An attempt count alone never terminates the task: the
threshold only forces a changed strategy, and truthful stopping still requires
the evidenced actual resource/evidence blockers or the absence of a permitted
productive next step — never a bare number. Missing obligation records or facts block only the
replacement dispatch while they are gathered autonomously — evidence gathering,
not a human permission question. Evidenced actual resource/tool exhaustion,
evidence unavailable after permitted diagnosis, or no permitted productive next
step produce truthful incomplete status, not approval, stating the concrete
blocker, attempted strategies, retained state and unfinished obligations
without requesting routine retry or replan authorization. Genuine
product/API/data-policy, credential, safety, permission or unsafe-history
decisions remain human-owned.

A delivery with missing/changed/stale/untrusted scope, changed substantive facts
or an author unavailable is quarantined — that delivery, not the task: block
dependent work on that delivery, do not paper over gaps with paper SHAs or a new
worker impersonating the author, and recover the task under the autonomous rule
above.

After one invalid correction there is no second request to the same author;
**Duplicates do not reset the allowance**, and neither does a rename or a
redispatch. A genuinely new authorized substantive scope/range requires
explicit actual new work through the normal review flow, not laundering the old
invalid report and not an automatic fresh-review loophole. Strict work still
requires implementer → independent reviewer → pass; a fast/live replacement of
an unusable observational report completes that wrap-up obligation instead of
opening review shopping. Escalation may gather context but cannot manufacture a
verdict.

Expert-submitted answers and capability wrapper JSON/refusals are excluded from
this report-repair path: do not rewrite expert evidence/refusals or rerun
privileged operations as a formatter. Existing expert one-question/new-material-
evidence gates and capability refusals remain unchanged. Delivery repair neither
consumes nor resets code-fix rounds or consultation budgets, and cannot defer
required design input before dependent implementation.

Fast/live retain direct edits/fixes, local checkpoints, explicit wrap-up and one
observational review. Same-author format-only redelivery is not a new full review
and triggers no app manual setup or refresh: live manual mode precedes code edits;
explicit refresh follows validated code changes only. This guidance and the bounded
evaluation driver are not hard runtime enforcement; normal semantic review and
all applicable finishing gates still apply.

### Worker requests and controller transitions

Workers keep delegation denied. A delegation denial is not itself a code finding,
blanket role blocker or permission to label a request pass/confirmed/complete:

- reviewer (full, targeted and CI modes) and adjudicator return
  `status: needs_consultation` with `consultation_request`;
- debug-advisor returns `verdict: needs_consultation` with that request;
- implementer returns existing `NEEDS_CONTEXT` with that request in its report;
- planner returns `NEEDS_CONTEXT` with that request instead of finished-plan
  Markdown until the necessary decision is reconciled;
- fast-dev-reviewer returns a non-approving pending report with base/head SHAs
  and the request, so its caller can obtain advice without losing review scope.

Controllers handle these branches **before** pass/verified/confirmed, finding
fix dispatch, cap/adjudication decisions or normal completion. Dispatch the
expert, reconcile with evidence, then return the decision to the original worker
to finish its own assessment; advice never substitutes for that verdict.
Requests alone do not consume a repair round or bypass a fix cap. Capability
workers preserve verbatim wrapper JSON; controllers handle technical advice
separately and never override wrapper refusals or human-owned choices.

Strict work remains implementer → independent reviewer → pass. The ordinary
diagnostic-advisor gate remains mandatory in strict debugging; it is not expert
advice on every fix. Fast/live continue direct edits/fixes and one observational
whole-branch wrap-up review, not a second mandatory full review. Expert advice
grants no edit, approval, checkpoint, publication or permission authority and
does not replace testing or independent review.

## Branch Convention

The default base branch for pull requests and merges is `main`.

For final validation and PR diff/base checks, use `origin/main` as the base
branch reference — not local `main`. Local `main` may be stale or contain
unrelated local commits. Use local `main` only when explicitly performing a
local merge or integration operation that requires it.

Before final validation, PR creation, or any ready-to-merge claim, fetch
`origin` and evaluate the branch against current `origin/main`. If the branch
is behind `origin/main` or remote integration would be rejected, update the
feature branch by a safe merge from `origin/main` when permitted, resolve any
conflicts through `implementer` → `reviewer` → pass, commit reviewed fixes, and
rerun validation from a clean tree. Do not rebase or force-push unless the human
explicitly requests it.

After implementation is complete — reviewed, committed, tests passing, tree
clean — the default integration action is to push the current branch and create a
pull request targeting `main`. Do this automatically; do not present an
integration menu or ask the user which action to take. Only deviate when the user
explicitly requests a different integration action or when the branch state is
unsafe (uncommitted changes, failing tests, unresolved merge conflicts with
`main`).

If required validation fails after implementation, review, or commit, do not
finish, push, create a pull request, merge, clean up the branch, or claim
ready-to-merge. Capture the failing command, failing tests, relevant output,
current branch state, and `git status --porcelain`. Invoke the
`systematic-debugging` skill and continue investigating even when the failure
appears unrelated, flaky, timing-dependent, or environmental. Establish root
cause or gather enough evidence to explain why root cause cannot be established
with available access. Route any repository fix through `implementer` →
`reviewer` → pass, commit reviewed fixes, rerun validation from a clean/current
`origin/main` base, and only proceed with the default integration action when
the required suite is green.

### Post-PR merge queue

After a pull request is open and queued by GitHub merge queue, agents keep running
and poll until the PR is actually merged. Queue handoff alone is not success;
success means the PR is merged (`mergedAt` present or equivalent merged state).

Agents poll with:

```bash
gh pr view <pr-or-branch> --json state,mergedAt,mergeStateStatus,mergeable,autoMergeRequest,statusCheckRollup,headRefName,headRefOid,url
gh run list --workflow test.yml --event merge_group --limit 20 --json databaseId,headBranch,headSha,status,conclusion,event,url,displayTitle,createdAt
gh run watch <run-id> --exit-status --interval 100
```

The following states are non-terminal and the agent should keep polling:
`queued`, `waiting`, `pending`, `in-progress`, `expected`, or
`null`/missing conclusion on merge-group runs.

The following are actionable blockers:

- **merge conflicts:** the merge queue cannot assemble or validate the merge
  group.
- **failed required `test` check:** the merge-group run completed with
  `failure`, `cancelled`, `timed_out`, or `action_required`.
- **missing or disabled queue:** merge queue is not active for `main` (neither
  the merge-group trigger fires nor the queue processes).
- **permission failures:** the agent cannot query PR status, list merge-group
  runs, or watch runs.
- **closed-unmerged PRs:** the PR was closed without being merged.
- **queue timeouts:** the merge-group run remains `queued` or `in_progress`
  beyond a reasonable window.

- Do not update the PR branch solely because `origin/main` advanced. The merge
  queue's merge-group checks are the post-PR integration freshness gate.
- Rebase and force-push remain forbidden unless the human explicitly requests
  them.
- For actionable blockers, invoke `systematic-debugging` to identify root cause
  or establish the limits of available evidence. Route any repository fix
  through `implementer` → `reviewer` → pass. After reviewed fixes are committed,
  rerun validation from current `origin/main`, push the PR branch, and requeue.
- If merge queue is not enabled or cannot be verified, report
  `HUMAN_DECISION_REQUIRED` with the exact GitHub setting needed instead of
  entering a stale-branch polling loop.

## Requirements-driven intake

Use `requirements-reconciliation` for goal/outcome, feature, intended behavior
change, bug, maintenance, exploration and clarification requests and discrepancies
found later. Classify intent independently of read-only/tiny/full ceremony. Inspect
original intent/provenance, existing requirements, designs/plans, code/tests and
evidence; record the skill's proportional conclusion in existing handoff/progress
records. Read-only conclusions stay report-only. New intended-behavior work is
requirements-driven; reuse existing obligations for defects and avoid synthetic
maintenance requirements or historical bulk migration.

Canonical ledger changes remain implementer-owned in strict flow. Requirements,
design and implementation-spec artifacts receive scoped independent review over
exact pending diffs/revisions or complete recorded ranges, followed by automatic
transitions, not user artifact approval. Explicit intent outranks a contrary
technical solution unless source evidence establishes a genuine unresolved policy
choice. Ask only that focused choice, record the answer and resume automatically.
Fast/live retain their direct-development and manual lifecycle exceptions above;
this adds no per-change worker pipeline or mandatory extra artifacts to them.
Run `make opencode-check` for prompt/policy changes; its nonrecursive
`requirements-check` includes focused Python tests and, once the canonical seed
exists, ledger validation and read-only index freshness checking. It never seeds
missing data. Static tests establish declarations, not live-agent compliance.

## Project Structure & Modules

- `src/` holds the C++17 engine modules (rendering, physics, audio, bindings). Add new systems as matching `.cpp`/`.h` pairs. Engine Lua bindings live in `src/lua_engine.cpp`.
- `apps/space/main.cpp` is the executable entry point; bootstrap other front ends here.
- `assets/` includes Lua, Fennel, Python, textures, and audio. Runtime and tests rely on `SPACE_ASSETS_PATH` pointing here.
- During the Python-to-Fennel/C++ migration, treat `assets/python/` as historical prototypes only. Reference them to understand behavior, but base new features, tests, and architecture decisions on the canonical Fennel modules in `assets/lua/` and the C++ engine in `src/`.
- `tests/` contains CTest targets; keep fixtures aligned with the asset layout.
- `scripts/` bundles utilities (`seed.py`), while `external/` houses vendored dependencies consumed by CMake.
- `archive/` contains some old python bindings that are no longer used but may be used for reference when building new features.

## OpenAI API Docs

- OpenAI API reference lives in `docs/dev/openai/`; start at `docs/dev/openai/index.md` for a map to chat/responses, assistants/threads/runs, uploads/vector stores, realtime events, and project/admin endpoints.
- Endpoint files follow the action name inside each folder (`create.md`, `list.md`, `object.md`, etc.). Use `rg "POST /responses"` (or similar) from the repo root to jump to the exact endpoint when wiring code to the API.

## Project-Specific OpenCode Skills

OpenCode users: restart after `.opencode/**` changes.

- Use `space-fennel-ui` for Fennel widgets, layout, rendering adapters, interaction widgets, widget lifecycle, or widget tests. See `docs/dev/fennel/style.md`.
- Use `space-graph-doctrine` for graph nodes, graph maps, graph views, graph persistence/topology, key loaders, or graph terminology. See `docs/dev/notes/graph.md`.
- Use `space-testing-runtime` for tests, E2E snapshots, remote-control debugging, profiling, build commands, or runtime harnesses. See `docs/dev/features/development-tooling.md`.

## Build, Run & Test

- `make cmake` primes the `build/` directory; rerun after editing CMake files.
- `make build` compiles a Release build in `build/`.
- **Build timeouts:** A cold `make build` can take hours. Always pass an explicit `timeout` parameter:
  - `make build`: `timeout: 14400000` (4 hours).
  - `make cmake`: `timeout: 600000` (10 minutes).
  - A killed build may leave partial artifacts; err on the high side rather than
    restarting from scratch.
- `make run` executes `space` with `SPACE_ASSETS_PATH=../assets` (via `./space -m main`).
- When running Lua/Fennel tests from the CLI, always set `SPACE_ASSETS_PATH` to the absolute `assets` path (e.g. ``SPACE_ASSETS_PATH=$(pwd)/assets ./build/space -m tests.fast:main``) so path-sensitive suites like `FsView` can resolve fixtures correctly.
- Fennel macros live under `assets/lua`; when invoking tests directly with `./build/space -m ...` set `FENNEL_PATH` and `FENNEL_MACRO_PATH` to `$(pwd)/assets/lua/?.fnl;$(pwd)/assets/lua/?/init.fnl` to ensure `(import-macros ...)` resolves.
- **Targeted local validation by default:** Agents run the narrowest meaningful checks for the changed behavioral surface:
  - **Fennel/UI/layout behavior:** compile check first (`make fennel-check` or `./build/space -m tools.fennel-check:main -- --target files --file <path>` for touched `.fnl` files), then constraints (`make constraints` or explicit-file constraints), then focused Fennel tests. Compile/constraints/test evidence should be reported in handoffs.
  - **C++ behind Fennel bindings:** build first, then focused Fennel tests through the binding surface.
  - **Pure C++ utility behavior:** build the relevant target and/or focused CTest.
  - **Docs/prompt-only changes:** focused text searches, diff review, and formatting checks.
  - **Build, package, startup, runtime initialization, broad binding/API, or other high-risk changes:** broaden local validation, including `make test` when that is the relevant local gate.
- `make build` is the normal **runtime/freshness prerequisite** when `./build/space` may be missing or stale, or when C++, CMake, runtime initialization, bindings, or host scaffolding changed.
- Do not use system `fennel`, system `lua`, `fennel-ls`, `fnlfmt`, `./build/space --compile`, or `./build/space -e` as validation oracles for Space Fennel. Use the project-native `tools.fennel-check` command and constraints/tests instead.
- For Fennel-facing work, `make constraints` runs after `make fennel-check` so constraint violations surface before slower debugging loops. The constraints gate is blocking; every result other than `pass` (`violations`, `fail`, or `interrupted`) exits nonzero and should be diagnosed and fixed through reviewed code or reviewed baseline data, not bypassed. See [Fennel Constraints](docs/dev/constraints.md).
- `make test` already depends on `make constraints`, so full-suite runs execute the constraints gate before normal Fennel tests; do not duplicate `make constraints` immediately before `make test` unless the early, faster feedback is useful.
- Disable audio for CLI test runs by default to avoid sandbox/PortAudio warnings: prefix commands with `SPACE_DISABLE_AUDIO=1` (e.g. `SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH=$(pwd)/assets ./build/space -m tests.fast:main`).
- When running tests, point `XDG_DATA_HOME` outside the repo to avoid littering the workspace (use `XDG_DATA_HOME=/tmp/space/tests/xdg-data` unless otherwise specified). Agents should always skip keyring-backed tests (`SKIP_KEYRING_TESTS=1`). Standard full-suite command (use when full local validation is justified by risk or plan/reviewer requirement, not as a default before every checkpoint commit): `SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH=$(pwd)/assets make test`.
- `make debug` configures `build/debug/` and launches `gdb ./space`.
- `make test` or `python3 scripts/ctest-summary.py --test-dir build --output-on-failure` runs all registered tests once the build is up to date.
- When Lua/Fennel work needs additional bindings or host scaffolding, update the relevant C++ (e.g. `apps/space/main.cpp`, `src/` modules) yourself and rerun `make build` to confirm the harness still compiles before handing the change back.
- On parentheses imbalance in Fennel code, especially when the code is deeply nested, inspect the nearest enclosing form around the reported location, then restructure the code by moving logic into helper functions in order to simplify the code structure and reduce nesting.
- Fennel parse errors often report the place where the parser finally got confused, not the form that actually caused the problem. If an innocent-looking binding such as `local build` or a closing delimiter is blamed, first isolate the bad form by temporarily removing chunks of logic until the file compiles, then re-add them step by step. Use that to find the real construct before doing broader restructuring.
- For live debugging, `space` supports `--remote-control=<zmq endpoint>` which evaluates Fennel code inside the running app; use `./build/space -m tools.remote-control-client:main -- --endpoint <endpoint> -c "<code>"` to send commands, and only enable it on trusted machines. The eval environment exposes `remote_control.create/resolve/reject/poll` for async results (create an id, resolve it inside a signal callback, then poll by id). Use `scripts/remote-control-heavy.sh` to exercise the async flow against a live app.
- When asked to debug a running app, prefer using the remote-control endpoint if the app was started with `--remote-control`; `make run` defaults to `ipc:///tmp/space-rc.sock`, otherwise ask for the endpoint, then send Fennel snippets via the client to inspect or modify state.
- Use `scripts/remote-control-debug.sh` for repeatable live-debug or live-inspect queries; update it as needed instead of ad-hoc client invocations, and run it outside the sandbox so IPC access works.
- `scripts/remote-control-debug.sh` should always contain only the latest debug query; replace its contents for new questions instead of adding flags or multiple modes.
- Use `app.next-frame` when remote-control scripts need to wait for a frame to render before reading state or running render-capture.
- E2E tests: `SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH=$(pwd)/assets make test-e2e` (must run outside sandbox).
- Add C++ tests under `tests/` with `CMakeLists.txt` registration; mirror runtime asset setup from `apps/space/main.cpp`.
- Profilers: `make prof target=<name>`; the `space-testing-runtime` skill covers profiling workflows.

## Coding Style & High-Risk Rules

- **No silent failures:** If required data, bindings, or operations fail, surface an explicit error immediately — never convert failures into quiet no-ops or clean exits.
- **Fennel classes:** Construct `self` in a final literal with all methods included; do not create early and mutate with `set`.
- Use `local` instead of `let` in Fennel.
- Use factory functions instead of constructors (`.new`).
- **Canonical option keys only:** Do not add legacy aliases or compatibility shims; migrate existing call sites instead.
- Use `assets/lua/json-utils.fnl` for atomic JSON writes.
- For C/C++: four-space indent, brace-on-new-line for functions, `std::unique_ptr`/`std::shared_ptr` over raw ownership, minimal headers.
- Fennel: multi-branch `if` forms instead of nesting; bind multiple return values directly with `local`.
- Graph nodes stay decoupled from views; use signals to emit updates.
- Fennel parse errors: the reported location is often misleading — isolate bad forms by temporarily removing chunks of logic.

## Commit Conventions

- **Strict-flow checkpoint ownership:** Assigned implementers validate and self-review
  ordinary task changes and accepted fixes, then create task-scoped local checkpoint
  commits before independent review. Supervisors may commit only their existing
  coordination edit allowlist or exact independently approved changes. Review covers
  the complete task `BASE..HEAD` range and each subsequent `FIX_BASE..HEAD` range,
  including tiny tasks. A checkpoint, clean tree, self-review, or DONE is not approval;
  independent review and applicable finishing gates still block completion,
  publication, and integration. Ensure reviewed work is committed; no extra or
  empty post-review commit is needed. Implementers gain no push, PR, integration,
  or history-rewrite authority. The fast-dev/live-dev exception above is unchanged.
- **Explicit stage-only/no-commit handoffs override ordinary checkpoints**, including
  fix rounds. Repeat that instruction on every fix dispatch. Daily/weekly automation
  and workflow-debug's final staged landing stay review-first: review the complete
  assigned staged diff, including additions and refreshed fixes, before committing.
  A commit-only review package cannot represent pending edits.
- Preserve unrelated worktree and index entries; never absorb, discard, or unstage
  unrelated work to make a checkpoint or clean-tree gate pass. If task ownership
  cannot be isolated safely, return NEEDS_CONTEXT. New policy wording does not
  retroactively authorize commits in a running session assigned no-commit work;
  restart OpenCode before relying on updated agent/skill instructions.
- Use the `type(scope)` format as described by the `git-commit` skill.
- Scopes (when useful): `engine`, `render`, `physics`, `audio`, `lua`, `ui`, `assets`, `scripts`.
- For Fennel-facing feature or bugfix handoffs, include a lightweight constraint-impact line when relevant: helped, obstructed/noisy, changed, or not applicable.
- Before checkpoint commits, run sufficient focused validation for the changed behavioral surface and record a short coverage rationale in your report.
- Escalate to broader local validation when the changed surface is high risk or the plan/reviewer requires it.
- Do not claim ready-to-merge until the applicable PR CI integration gate is green.

## Assets & Configuration Tips

- When adding assets, ensure `AssetManager::getAssetPath` can locate them and verify packaging copies from `assets/`.
- For icon names used by UI buttons/widgets, validate availability against `assets/material-design-icons/icons.txt` before committing. Use `rg` on that file and prefer exact icon-name matches from the start of each line.
