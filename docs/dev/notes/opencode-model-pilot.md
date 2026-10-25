# Static Space Fennel model pilot

## Status and boundaries

**Collection repair pending; no judgments, scores, or responsibility recommendation
yet.** Initial preparation and the root fix passed independent review. The first
GLM architecture candidate completed, but its export-to-pipe capture was truncated;
no further candidate calls followed. The collection fix requires independent
review before controller recovery/continuation. The frozen conceptual
GPT-authored contract is not a generated candidate answer. Its authorship is the
preparing GPT agent, not an extra generative trial;
it contains no reference implementation.

This is a bounded comparison of architecture/design in **actual Space Fennel**:
`opencode-go/glm-5.3-flash` versus `openai/gpt-6.1-sol`. Python is thin orchestration,
not the evaluated language. No production Fennel, agent definitions or routing are
changed. Source answers remain inert response text: never apply, compile, import,
or execute them. No Space build, compile check, constraints or native tests are
needed or authorized for this pilot. Proposed candidate tests are assessed
statically, not reported as passing.

The design authority is
[`2026-10-25-opencode-model-pilot-design.md`](../../specs/2026-10-25-opencode-model-pilot-design.md).

## Frozen material

`scripts/evals/opencode_pilot_cases.json` holds public briefs, neutral review
mutations, private expectations/static vectors, rubric and contract. Preparation
explicitly selects public fields; it never sends the whole cases JSON to a model.
Evaluator-only material is *evaluation-private*, not a security secret; it is
versioned for independent review and absent from candidate attachments.

Source is pinned to `d6e3742f123e4fde688453eeba8e3bb9da328238`, including complete
TabView, SearchView, Sized and their actual focused tests. Short Layout, Flex,
Input/InputModel and Signal excerpts establish ownership, dirtiness and signal
semantics. A short pinned AGENTS excerpt establishes coding conventions. No
historical worked lifecycle solution is candidate context. Full blobs and selected
excerpts have SHA-256 hashes in the cases file. Ranges are inclusive, one-indexed;
excerpt bytes concatenate those ranges in order, preserving line endings.

Preparation verifies those hashes against `git show <pin>:<path>`, captures public
blobs/excerpts as `.txt`, renders packets, and hashes **exact rendered bytes** in
`manifest.json`. The cases snapshot/hash also freezes prompts, mutations,
evaluator expectations, vectors, rubric and contract. Both contract arms point to
the exact same packet bytes and contract hash. All three implementation arms share
the exact same public requirements and baseline source; only the conceptual
contract is appended for the two contract arms.

### Cases to review before calls

1. **Tab architecture:** opt-in logical-state retention for static items, keeping
   widget rebuild/drop behavior and public index/button/events compatibility.
   Multiple bounded APIs and explicit static identity strategies are acceptable;
   a single preferred spelling is not the answer key.
2. **Search review:** A uses layout-only teardown; B recursively drops through
   Flex then drops its children again; C connects a fixture-only long-lived
   caller-owned external signal but disconnects from the input signal; D is its
   matched sound cleanup. C/D supply the external source's lifetime explicitly.
   **Do not call omission of baseline input disconnect a proven lasting leak:**
   Input.drop calls InputModel.drop, which clears its signals. No external signal
   feature is claimed to exist in baseline SearchView.
3. **Tab escalation:** dynamic items, duplicate/absent IDs and external updates
   leave identity, ownership, lifetime and precedence decisions genuinely open.
   Reward specific questions and safe bounded work, not invented policy or total
   refusal.
4. **Sized handoff:** synthetic author patch updates ordinary and constrained
   wrapper measurements and dirties the wrapper, but leaves `resolve-child-max`
   reading constructor `opts.size`. Original tests are unchanged. The author claim
   is explicitly synthetic, not a test transcript. Expected defect is stale child
   constraints plus absent relevant coverage, **not** missing wrapper dirtiness.
5. **Sized implementation:** current size must drive all three size-dependent
   paths (normal wrapper, constrained wrapper, child maxima including fallback).
   Preserve original tests, direct transforms, child identity and per-build
   independence without mutating shared options. Static vectors hold out inputs,
   not requirements; e.g. current `[7,0,-2]`, parent max `[20,30,40]` implies child
   max `[7,30,40]`. Require proposed focused tests and honest validation notes.

## Preparation and offline checks

Offline checks from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/tests -p 'test_eval_opencode_pilot.py' -v
python3 -m json.tool scripts/evals/opencode_pilot_cases.json >/dev/null
git diff --check
```

The offline suite uses disposable fixtures with a patched artifact-root constant;
configured/denied path checks mock resolution and never inspect those external
paths. It is not evidence that an agent has effective external-directory access.

After independent fix review, the authorized controller owns external read/list
preflight and fresh preparation. Verify `/tmp/space` exists and is accessible,
then verify/create only the narrow `opencode-model-pilot` parent if needed. Do not
widen permissions or try another access mechanism after a denial. The original
denied `/tmp/opencode` artifacts must remain entirely untouched: never read or
copy them, even to compare hashes. Generate new artifacts from pinned public Git
source and the unchanged cases instead:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/eval_opencode_pilot.py prepare --repo-root . --run-root /tmp/space/opencode-model-pilot/task1-reviewed-2026-10-25
```

Choose a **new** run root; preparation rejects reuse and paths outside
`/tmp/space/opencode-model-pilot` or inside repository ancestry. This command only
reads pinned public Git blobs and creates local text/JSON evidence. It does not invoke OpenCode
or a model. `manifest.json` records source/excerpt/packet hashes, schedule and
contract equality. Review the rendered packets as well as the JSON seeds; rendered
variants are complete inert modules, not just mutation descriptions.

The controller/reviewer must read the new root's `manifest.json`, confirm eleven
trials and source/cases/packet hashes plus identical contract hashes, and verify
empty `reservations/` and `results/` with no `deadline.json` before any candidate
call. New external preparation is deferred to that authorized controller; offline
tests or this repository fix checkpoint do not substitute for the access check.

## Later execution (not part of preparation)

**Only after independent preparation review passes**, an authorized later stage
may use:

```bash
python3 scripts/eval_opencode_pilot.py run --run-root /tmp/space/opencode-model-pilot/task1-reviewed-2026-10-25
```

OpenCode 1.18.35 public `run`/`export` help and installed public SDK v2 types ground
the invocation/export schema. Generated global and explicit `pilot` agent
permissions are both the supported `"deny"` form. Invocation uses `--pure`, fresh
`run --format json --agent pilot --model <exact-id> [--variant ...] --file <packet>`
from the generated control directory, not repository ancestry. No continuation,
delegation, repair conversation, fallback or runner retry exists. A single
subprocess is started per trial, followed by its own public export. Never inspect
session lists, other sessions, auth files, home config, private logs or databases.

The runner preserves normal internal CLI subscription authentication and normal
HOME/XDG roots. It only supplies its generated public config via config path and
content overrides; it does not read/copy auth or home configuration and does not
dump the environment or merged config. Absence of an injected
`OPENCODE_AUTH_CONTENT` is **not** authentication failure. `--pure` suppresses
external plugins; public run help/SDK does not establish full skill-discovery or
global-instruction isolation. All tool/skill permissions remain denied, and any
exported tool/delegation/retry part invalidates the trial. Ambient instructions,
providers and CLI internals can still affect both models. Do not claim hermetic
config isolation or that no provider-internal transport retry can occur.
Controller evidence also found exported directory metadata reporting the repository
path despite the requested subprocess control-directory cwd. Preserve that ambient
isolation limitation; requested cwd and all-deny permissions do not prove actual
cwd/global-instruction isolation.

### Fixed primary schedule

| Case | Order | GPT requested variant | Deadline |
| --- | --- | --- | --- |
| Tab architecture | GLM, GPT | `xhigh` | 180 s each |
| Search review | GPT, GLM | `xhigh` | 180 s each |
| Tab escalation | GLM, GPT | `xhigh` | 180 s each |
| Sized handoff | GPT, GLM | `xhigh` | 180 s each |
| Sized GLM plain | GLM | none | 360 s |
| Sized GPT contract | GPT | `high` | 360 s |
| Sized GLM contract | GLM | none | 360 s |

Eleven candidate calls total. GLM receives no assumed GPT variant name. Evidence
separates requested/sent/reported variants; absent export metadata means unknown
effective variant even if a variant flag was sent. Never infer effective variant
from requested settings. Actual assistant provider/model IDs and completion must
be present and correct before scoring; missing/mismatched identity or an auth
error is preflight failure, not evidence of poor model quality.

Each trial is exclusively reserved before invocation. A persisted deadline starts
on the first attempted trial and caps all model execution at 90 minutes, even
across later direct `run_trial` invocations; caller deadlines can shorten but not
extend it. Each trial's wall deadline includes export. A timeout kills/reaps its
process group and remains consumed, never retried. A run lock serializes
reservations/deadline creation; a crash-left lock/reservation is evidence requiring
manual investigation, not permission to retry. The CLI stops on a non-complete
outcome, and re-running the CLI refuses existing reservations rather than
continuing or silently selecting fresh answers. There is no automatic resume.

### Explicit collection recovery and continuation

The observed CLI export produced an exit-0 65,536-byte JSON prefix when stdout was
a pipe, while a controlled **non-generative** regular-file capture returned the
complete 73,449-byte own export with the same final answer as the original run.
This proves destination-dependent truncation, not the CLI's exact buffering
internals or a model failure. Capture now supplies exclusive regular-file stdout
and stderr handles directly, retaining partial files on timeout/nonzero exit and
killing/reaping the process group on timeout. It never repairs malformed JSON by
guessing missing content or bypassing identity/completion verification.

The reviewed recovery subsequently stopped **before export** because the CLI had
inserted only top-level `"$schema": "https://opencode.ai/config.json"` into the
generated control config. The narrow compatibility check accepts that annotation
only for `control/opencode.json`, and only if removing exactly that known property
and serializing with the original preparation's two-space indentation, key order
and trailing newline reproduces the **original frozen SHA-256**. Unknown schema
values, permission/prompt/other field changes, and every other changed artifact
remain errors. This is not general semantic JSON equivalence or a hash-gate bypass.
The explicit recovery record's `artifact_annotations` lists the config path,
expected and actual SHA-256 hashes, and accepted annotation. No current config,
manifest or deadline is rewritten. Future preparation includes the known schema
from the start and hashes those exact bytes normally. This additional collection
fix requires independent review before controller recovery; no new model attempt
or fresh overall deadline is authorized.

After independent fix review, only the authorized controller performs actual
artifact recovery (the implementation agent's tests use disposable fixtures):

```bash
python3 scripts/eval_opencode_pilot.py recover-export --run-root /tmp/space/opencode-model-pilot/task1-reviewed-2026-10-25 --trial-id tab-architecture-glm
python3 scripts/eval_opencode_pilot.py continue-unreserved --run-root /tmp/space/opencode-model-pilot/task1-reviewed-2026-10-25
```

`recover-export` is **collection repair, not a candidate retry**. It requires an
existing scheduled reservation and original `infrastructure_error` /
`JSONDecodeError` result. The session ID comes only from that trial's saved run
NDJSON; there is no caller-supplied session option. It invokes only `opencode
export` for that same ID, never `run`. The recovered export must verify actual
provider/model, session ownership and completion, and its final text must equal
the saved run final text exactly. Returned implementation files remain inert.

Every explicit recovery attempt gets a new
`recoveries/<trial-id>/<unique-attempt>/` directory containing new export captures
and an exclusively created `record.json`. Failures remain in that append-only
history. A successful record embeds the `effective_result` and hashes the original
failed result, saved run and recovered export; it does **not** overwrite
`results/<trial-id>.json` or any original raw capture. The original failure and
recovered evidence represent **one candidate attempt**, never two samples or two
usage totals. Repeating recovery after success is refused; failed recovery is
never automatically retried. A crash-left attempt directory is retained for
investigation, not silently removed.

`continue-unreserved` first checks the frozen artifact hashes and every scheduled
reservation. Each must have a verified complete original capture/result or a
unique successful recovery whose hashes, identity/completion and unchanged final
text are revalidated. An unresolved, missing or changed record refuses continuation
before any new candidate call. It prints all `skipped_reserved` entries, then calls
only never-reserved scheduled trials in order, stopping on the first non-complete
outcome. Existing exclusive reservations still prevent duplicate invocations.

Neither command resets or extends the persisted 90-minute deadline or clears a
reservation. Recovery export is bounded by remaining overall time and 180 seconds;
continuation uses the exact saved deadline, not a fresh 90-minute window. With no
remaining time, no export/new candidate is invoked. If already expired at the
continuation check, no future candidate is reserved. Independent review and explicit controller execution
gate both commands; this tooling checkpoint is not permission to run them.

Outcomes distinguish complete, deadline exhausted, timeout, incomplete,
preflight failure, protocol violation, invalid implementation answer and other
infrastructure error. Inspect raw own-session evidence to diagnose failures;
never count failed infrastructure as a model score. Strict implementation JSON
requires exactly the two allowlisted filenames and nonempty notes; duplicate,
extra/missing/unsafe paths and non-string sources are rejected without writing
any `.fnl` file.

## Evidence, scoring and eventual recommendation

Raw stdout/stderr and exports (which may contain reasoning) remain under the
private-mode run root, **outside version control**. Only exported assistant final
text is extracted; reasoning parts are never copied into result summaries. Usage
comes once per unique assistant message from message metadata, never summed again
from step-finish parts or duplicate NDJSON events. Preserve absent usage as null,
zero as reported zero, and reasoning/cache subfields without collapsing unknowns.
Zero reported cost is not proof of zero subscription cost; no financial-savings
claim is justified. All final text still needs manual sanitization review before
publication; the runner is not a general secret redactor.

Later stages retain complete sanitized responses, anonymize artifacts, obtain five
fresh independent GPT judging contexts, freeze scores/findings, then unblind.
Weights (0–4 per dimension): architecture/design 35%, correctness/invariants 30%,
validation 15%, scope/escalation 10%, evidence accuracy 10%. Material defects and
fabricated evidence remain explicit irrespective of aggregate scores. At most two
additional candidate calls are permitted, only a paired architecture repeat for
a gap at most five points or low confidence; at most one repeat judgment. The
Task 1 runner deliberately provides **no automatic repeat/judging loop or budget
extension**; any later extension must reserve the additional reviewed calls, not
reuse a primary trial ID or retry to success.

The eventual sanitized evidence belongs in
`docs/dev/notes/opencode-model-pilot/2026-10-25/{records.json,responses.md,judgments.md}`;
those results do not exist yet. Recommend responsibilities only after that
evidence and independent results review, not from this tooling checkpoint.

This is a small static screening sample, not statistical proof. It excludes live
repository search, autonomous tools, recovery loops, long-context work, C++ and
broad refactoring. Static assessment cannot establish compilation/runtime
correctness. GPT judging brings same-family bias and imperfect blinding; shared
contract effects cannot be separated from model randomness here. Successful
contract execution would support considering narrower GLM duties, not downgrading
architecture/review gates or changing production routing automatically. PR CI
remains the integration gate for any landed orchestration tooling.
