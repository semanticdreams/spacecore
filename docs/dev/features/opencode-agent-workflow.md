# OpenCode Agent Workflow

This page documents Space's shared Orca / OpenCode workflow for collaborators using the repo-local configuration. It describes how to set up a working agent environment, what the repository expects from agent-driven changes, and which pieces of the personal VM setup note are intentionally excluded from this shared guide.

## Official Orca documentation

Orca and OpenCode provide the agent runtime and development environment. The official documentation covers platform installation, session management, and remote-server workflows:

- [Ways to run Orca](https://www.onorca.dev/docs/ways-to-run)
- [Orca SSH](https://www.onorca.dev/docs/ssh)
- [Orca remote servers](https://www.onorca.dev/docs/remote-servers)

## Supported setups

Space does not require one specific arrangement. Two patterns are supported:

- **Local Orca plus remote SSH checkout.** You run Orca on your local machine, connect to a remote development VM over SSH, and open the Space checkout on that VM. This keeps the heavy build toolchain on the remote host while your local Orca session orchestrates OpenCode.
- **Orca running on the remote VM.** You install Orca directly on the remote development machine and use a local Orca session only to view or connect to that remote session. This works well when your local environment is thin or when you prefer to keep everything on one host.

The local Orca plus remote SSH checklist below is one possible path; it is not a project requirement. Choose whichever arrangement fits your environment.

## Local Orca plus remote SSH checklist

If you choose the local-Orca-plus-remote-SSH setup, work through these points:

1. **Remote VM reachable.** Confirm you can SSH into the remote VM from your local machine.
2. **Build and dev tools.** Install common tooling on the remote VM: `git`, `nodejs` and `npm`, `python3`, `make`, `g++`, `curl`, `clangd`, and `rsync`. These are typically available through the system package manager.
3. **OpenCode on the remote VM.** Install OpenCode and make sure it is on `PATH` for non-interactive SSH sessions so that Orca can invoke it automatically.
4. **GitHub SSH access.** Configure SSH key access for GitHub on the remote VM so the agent can push branches and create pull requests. Test with `ssh -T git@github.com`.
5. **Clone Space on the remote VM.** Clone the repository into a working directory the SSH user can write to.
6. **Add the host in Orca.** Add the SSH host and repository path in Orca's remote-server workflow so it can open the checkout.
7. **Rely on the checked-out repository.** Once the checkout is opened, the agent reads `AGENTS.md` and `.opencode/**` from the repository itself — no external configuration repository is needed.
8. **Final checks.** Run `command -v git node npm clangd opencode` on the remote VM to confirm the expected tools are available, then verify SSH connectivity with `ssh -T git@github.com`.

### Optional: warm new worktrees from the main build

When creating a fresh `git worktree` for agent-driven work, you can warm the
new worktree from a cached main-checkout build instead of running a full
`make build` from scratch. This is a cache warm-start, not a substitute for
validation; agents must still run the normal Space validation ladder.

**When to use:** Run only on a freshly created, clean worktree before any
agent edits begin. The script assumes the same machine and toolchain as the
main checkout and a valid, up-to-date main-checkout build directory.

**When not to use:** Skip this on worktrees that already contain divergent
changes, or when the main-checkout build may be stale relative to the target
branch. If anything behaves unexpectedly after warming, delete the copied
build directory and run `make build`.

The script copies build artifacts from the main checkout's `build/` directory
into the new worktree, then rewrites CMake-generated absolute paths (source and
build directories) to point at the new worktree. After repathing, it re-runs
`cmake` so generated files are refreshed for the new location, then builds the
main target. It preserves the build profile and CEF settings from the main
checkout's cache.

**Safety notes:**
- Run only for a freshly created, clean worktree before agent work begins.
- Assumes the same machine/toolchain and a valid main-checkout `build/`.
- Does not copy credentials. Repaths only generated text files; binary
  artifacts are skipped (detected by the presence of null bytes).
- Re-runs `cmake` after rewriting the cache so CMake refreshes generated
  files for the new worktree.
- Copies build files with fresh mtimes (`rsync --no-times`) so copied
  artifacts appear newer than checkout files. This is safe because the
  script requires identical HEADs; if HEADs differ, it refuses to run
  rather than hiding rebuilds.

Paste the script below into Orca's per-project or per-worktree setup step.
Adjust the `SPACE_MAIN_CHECKOUT` and `ORCA_WORKTREE` environment variables
(or the script's default paths) to match your environment.

```bash
#!/usr/bin/env bash
set -euo pipefail

main_checkout="${SPACE_MAIN_CHECKOUT:-$HOME/space/space}"
worktree="${ORCA_WORKTREE:-$PWD}"
main_checkout="$(cd "$main_checkout" && pwd)"
worktree="$(cd "$worktree" && pwd)"

if [ "$main_checkout" = "$worktree" ]; then
  echo "Refusing to seed the main checkout from itself: $worktree" >&2
  exit 1
fi

src_build="$main_checkout/build"
dst_build="$worktree/build"

if [ ! -f "$src_build/CMakeCache.txt" ]; then
  echo "No reusable build cache at $src_build; run make build in $main_checkout first." >&2
  exit 1
fi

if [ -n "$(git -C "$worktree" status --porcelain)" ]; then
  echo "Worktree is not clean; run this only before agent edits begin." >&2
  exit 1
fi

src_head="$(git -C "$main_checkout" rev-parse HEAD)"
dst_head="$(git -C "$worktree" rev-parse HEAD)"
if [ "$src_head" != "$dst_head" ]; then
  echo "Worktree HEAD ($dst_head) differs from main-checkout HEAD ($src_head)." >&2
  echo "The warm-start script is only safe when the new worktree starts from the same commit as the main checkout." >&2
  echo "For a divergent branch, run make build or warm from a checkout at the same commit." >&2
  exit 1
fi

mkdir -p "$dst_build"
rsync -a --delete --no-times \
  --exclude '/logs/' \
  --exclude '/Testing/Temporary/' \
  "$src_build/" "$dst_build/"

python3 - "$main_checkout" "$worktree" <<'PY'
import sys
from pathlib import Path

old_src = Path(sys.argv[1]).resolve()
new_src = Path(sys.argv[2]).resolve()
old_build = old_src / "build"
new_build = new_src / "build"
replacements = [
    (str(old_build).encode(), str(new_build).encode()),
    (str(old_src).encode(), str(new_src).encode()),
]

for path in new_build.rglob("*"):
    if not path.is_file() or path.is_symlink():
        continue
    try:
        data = path.read_bytes()
    except OSError:
        continue
    if b"\0" in data:
        continue
    updated = data
    for old, new in replacements:
        updated = updated.replace(old, new)
    if updated != data:
        path.write_bytes(updated)
PY

profile="$(awk -F= '/^SPACE_BUILD_PROFILE:STRING=/{print $2}' "$dst_build/CMakeCache.txt" || true)"
cef="$(awk -F= '/^SPACE_ENABLE_CEF:BOOL=/{print $2}' "$dst_build/CMakeCache.txt" || true)"
cmake_args=(-S "$worktree" -B "$dst_build" -DCMAKE_BUILD_TYPE=Release)
[ -n "$profile" ] && cmake_args+=("-DSPACE_BUILD_PROFILE=$profile")
[ -n "$cef" ] && cmake_args+=("-DSPACE_ENABLE_CEF=$cef")
cmake "${cmake_args[@]}"

cmake --build "$dst_build" --target space -- -j"${BUILD_JOBS:-1}"
```

## Remote-VM Orca alternative

When running Orca entirely on the remote VM fits your environment better, install Orca on that host and launch your agent sessions there. Use your local Orca session only as a viewer or connector — some collaborators keep a local Orca window open that connects to the remote instance.

See Orca's [remote servers](https://www.onorca.dev/docs/remote-servers) documentation for details on managing remote Orca instances.

## Space workflow expectations

Once your agent environment is connected to a Space checkout, these repository conventions apply:

- **`AGENTS.md`** is the always-on repository guidance. Agents read it on startup and follow its rules for every session. It covers branch conventions, build commands, test invocation, coding style, and project structure.
- **`.opencode/**`** is the repo-local source for Space agents, skills, and OpenCode configuration. It includes agent definitions, skill files that provide specialized guidance for Fennel, UI, testing, and graph work, and the OpenCode configuration file. This in-repo configuration is canonical for this repository — no separate global config repository is needed.
- **Restart OpenCode after `.opencode/**` changes.** When you add or modify agents, skills, or configuration under `.opencode/`, restart OpenCode so the updated definitions and workflow instruction changes take effect. OpenCode loads these files at startup and does not hot-reload them.
- **Follow repository validation expectations from `AGENTS.md`.** Agents must respect the validation ladder: for Fennel work, run compile checks first, then constraints, then focused Fennel tests. Broader local validation (such as `make test`) is required only when the change is high-risk or the plan/reviewer requires it. Required validation failures are debugging tasks, not items to bypass.
- **Targeted local validation by default.** Agents run the narrowest meaningful checks for the changed behavioral surface rather than the full suite before every checkpoint commit. The expected validation depends on what changed:

  - **Fennel/UI/layout behavior:** compile check first (`make fennel-check` or touched-file `tools.fennel-check`), then constraints (`make constraints` or explicit-file constraints), then focused Fennel tests.
  - **C++ behind Fennel bindings:** build first, then focused Fennel tests through the binding surface.
  - **Pure C++ utility behavior:** build the relevant target and/or focused CTest.
  - **Docs/prompt-only changes:** focused text searches, diff review, and formatting checks.
  - **Build, package, startup, runtime initialization, broad binding/API, or other high-risk changes:** broaden local validation, including `make test` when that is the relevant local gate.

- **`make build`** remains the runtime/freshness prerequisite when the built Space runtime (`./build/space`) may be missing or stale, or when C++, CMake, runtime initialization, bindings, or host scaffolding changed.
- The standard full-suite command is documented for high-risk or explicitly required local validation:
  ```bash
  SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH=$(pwd)/assets make test
  ```
- **PR CI** is the full integration gate. Do not claim ready-to-merge until the applicable PR CI gate is green.
- **Required validation failures**: see [Validation continuation and current base](#validation-continuation-and-current-base) for the full contract.

### Model-neutral role routing and targeted expert consultation

**Active policy supersession note.** This is the current routing and consultation
policy. It supersedes the earlier pinned dual-model rollout and its `glm_proposal`
request field. The historical protocol/evidence sections below (Bounded
routing-pressure evidence, Fail-closed delivery: prospective acceptance) remain
byte-for-byte records of that superseded protocol: they are not rescored, and no
review-quality equivalence or equal-defect-detection claim is made relative to
them. They are not an oracle for the current policy.

Every project role's `model:` and `variant:` frontmatter lines in `.opencode/agents/`
are authoritative routing configuration. Both lines are required,
syntax-validated by `scripts/check_opencode_permissions.py`, independently
editable without checker, policy or test pin changes, and never duplicated in
instruction bodies. The checker maintains an explicit required inventory of the
17 existing project roles (`REQUIRED_ROLES`) separately from configurable pins;
no provider/model allowlist, role-tier table or equality relationship between
roles is enforced. This covers project definitions, **not** inherited
built-in/hidden/global agents or installation-wide routing. Use project `explorer`
and named workers, not built-in general/explore as implicit model fallback.
Root/project OpenCode JSON and home configuration are unchanged.

Restart OpenCode to load the new instruction snapshot and routing schema;
already-running sessions retain their loaded roles and must not claim they
already use the new routing. A routing syntax check does not prove provider or
variant availability.

The canonical [AGENTS.md](https://github.com/semanticdreams/spacecore/blob/main/AGENTS.md#targeted-expert-consultation-contract)
contract requires targeted `expert-advisor` consultation for evidenced triggers:
the same material failure after one focused repair, an evidenced unresolved
material technical conflict, and a critical unresolved permissions/security or
irreversible-data technical boundary before acting across it. Ordinary design
decisions — including meaningful local/internal/UI design — still need
evidence-backed rationale but no expert dispatch, even when confident.
Controllers may request one bounded consultation for consequential technical
uncertainty; optional advice is never a universal prerequisite. Reuse unchanged
reconciled decisions; material design/contract/assumption changes reopen them.
Independent review is a separate assessment of untrusted changes, not a
guarantee supplied by using different model families.

Routine execution/review/diagnosis, expected TDD RED, initial syntax/typo repair,
cosmetic naming and mechanical follow-through on an unchanged reconciled decision
need no request. Missing evidence can be collected directly when permitted.
Unknown product/API/data policy remains **HUMAN_DECISION_REQUIRED**; the expert
does not set policy.

The requesting worker first states its proposal, responsibilities/contracts,
invariant and rationale. Only task-capable controllers (supervisor or selected
fast-dev/live-dev) dispatch the expert with one bounded technical question and
inspectable original sources, diffs/excerpts and validation evidence, not just
summary conclusions. Workers keep delegation denied. A `consultation_request` has
exactly these fields:

```json
{
  "decision_scope": "widget save transition ownership",
  "trigger": "software_design",
  "question": "Does save-before-detach preserve content on failure?",
  "sources": ["assets/lua/widget.fnl:40-90 and proposed diff in the handoff"],
  "invariant": "Failed saves leave current content attached",
  "evidence": ["Current detach precedes the fallible save"],
  "attempted_fix": null,
  "proposal": "Save and validate first; transfer ownership only on success.",
  "decision_needed": "Reconcile ownership and failure guarantees"
}
```

`attempted_fix` is nullable; `proposal` is required and nonempty for design/
architecture/contract decisions, otherwise nullable. Expert JSON contains
`decision_scope`, `status` (`answered`, `insufficient_evidence`, `requires_human`),
`finding`, `evidence`, `action`. Expert inspects original evidence with repository
read/glob/grep/list/LSP and sensitive-read exclusions. Edit, shell, delegation,
external directories, web access and direct questions to the user are denied.
It cannot implement, approve, publish or override capabilities/permissions.

Record scope, proposal, original evidence, expert critique and **evidenced
reconciliation before dependent implementation** in existing handoff/progress
artifacts. Resolve and validate material findings or escalate to the human, not
dismiss them by preference. One consultation per scope; reuse unchanged reconciled
decisions without a repeat consultation tax. Material design/contract/assumption
changes reopen the decision. Otherwise reconsult only with genuinely new material
evidence, not another try for approval. Unavailable expert or unanswered necessary
decisions block dependent work; gather permitted evidence or ask the human, not a
call loop.

| Worker | Non-approving pending branch |
| --- | --- |
| reviewer (full, targeted, CI), adjudicator | `status: needs_consultation` plus `consultation_request` |
| debug-advisor | `verdict: needs_consultation` plus request |
| implementer | Existing `NEEDS_CONTEXT` plus request in its report |
| planner | `NEEDS_CONTEXT` plus request instead of finished-plan Markdown |
| fast-dev-reviewer | `status: needs_consultation`, base/head SHAs and request |

Controllers handle pending branches before pass/verified/confirmed, findings/fixes,
fix-cap/adjudication or completion. They dispatch the expert, reconcile with
evidence, and return the result to the original worker for its own verdict.
Delegation denial is not itself a code finding or blanket role blocker. Requests
alone do not consume repair rounds or bypass caps. Capability workers keep verbatim
wrapper JSON/refusals; controllers handle advice separately. Strict implementer
→ independent reviewer → pass remains, including the ordinary mandatory
diagnostic-advisor gate, not expert advice on every fix. Fast/live retain direct
work and one observational whole-branch review, not a second mandatory full
review.

#### Bounded routing-pressure evidence and limits

**Historical perfect-first-response acceptance FAILED; those outcomes are not
rescored.** The user subsequently approved prospective fail-closed acceptance
below; it does not turn either old experiment into a success. The rollout is
still unpublished: prospective validation passed as summarized below, but results
review, final whole-branch review and finishing gates remain pending.
The following is controller-supplied evidence, not an independent read of external
captures. All fifteen candidate calls used fresh exported contexts verified as
`opencode-go/glm-5.3-flash`, reported variant `null`, with no tools. No retries or
extra GPT evaluation trials ran; design consultation, diagnosis and review are
process gates, not candidate evaluations.

| Protocol / phase | Calls consumed | Strict complete answers | Exact route-plus-owner matches | Preserved failures |
| --- | --- | --- | --- | --- |
| Original baseline, before agent/skill/AGENTS edits | 5/5 | 2/5 | Slot 4: 9/18; slot 5: 8/18 | Slots 1–3: fenced JSON, `invalid_answer` |
| Original guidance, reviewed source `8aae2c7e` | 5/5 | 1/5 | Slot 1: 9/18 | Slots 2, 4, 5: fenced JSON; slot 3: malformed JSON; all `invalid_answer` |
| Separate clarified protocol, reviewed helper `4fdef0db` | 5/5 | 4/5 | 72 recorded matches of 90 required | Slot 2: syntactically valid JSON, wrong workflow identifier, `invalid_answer` |

**Original experiment.** The ten-call budget is exhausted. Aggregate active CLI
time was `593.4621967620624/2100` seconds; the original data and all 73 files
remained unchanged through the separate tranche (combined inventory SHA-256
`2e04675a4ed0fdabbe5a227c2a073f8f244f4cb235c01f7e9f05910110cedb3e`).
Invalid answers were not repaired or rescored. Baseline rationales already
substantively requested both models for fresh local design, confident cross-system
contracts and fresh live widget design: the evaluation instruction itself required
this, so no causal improvement claim is supported.

Original route counts were confounded by enum interpretation: primary controllers
often wrote `request_consultation` while describing their own expert dispatch,
where the oracle required `expert_advisor`. Baseline denied-reviewer answers also
invented CHANGE_REQUESTED / NEEDS_FIXES / BLOCKED outputs instead of the pending
consultation branch. Guidance rationales explicitly described `needs_consultation`
and controller handling, an observational difference only. Eventual code-owner and
approval-bypass mismatches remain failures, not grounds to rewrite the oracle.
Guidance slot 4 also incorrectly mentioned manual-refresh-before-edit despite a
correct dedicated manual-mode case. Neither the sparse valid envelopes nor these
rationale observations establish full conformance or a causal routing improvement.

**Separate clarified protocol.** The user authorized exactly five additional calls,
180 seconds each and 900 seconds aggregate, with no retries. Clarified route/owner
instructions and a positive raw-JSON recipe were frozen before calls; the original
matrix, schema and oracle were unchanged. This is not a rerun/rescoring of old data.
Active CLI time was `339.499002335011/900` seconds. Predeclared acceptance required
five verified strict complete 18-case outputs, 90/90 route-plus-owner matches and
manual rationale review. **Four strict accepted outputs and 72 recorded matches
do not meet that gate.** All five outputs were syntactically valid JSON, unlike
the original fence/syntax failures.

Clarified slot 2 had 18 rows but one wrong key tuple: `wrap-up-review` expected
`workflow=fast-dev, actor=fast-dev-reviewer`; it returned
`workflow=fast-dev-reviewer, actor=fast-dev-reviewer`. The original parser correctly
raised `ValueError: unknown/duplicate routing decision`. Its `route=glm` and
`implementation_owner=fast-dev` were correct, and the rationale retained direct
fixes, self-review and revalidation without a second mandatory GPT review. This is
a genuine identifier-copy/coverage failure, not a demonstrated broad omission of
architecture consultation or a harness defect. Do not repair the historical workflow
field in place, accept an alias, score the rejected rows or claim 90/90. Any separately
authorized original-author correction is a new record, not a rescore of this trial.

The controller manually read all 90 final rationales (not reasoning). They generally
expressed dual-model design input before dependent implementation, GLM proposal /
GPT critique / evidenced reconciliation, unchanged reuse and material reopening,
read-only expert boundaries, worker pending handling, human-owned policy, retained
approval gates and direct fast/live ownership. Dedicated live-manual cases were
correct, but **full manual conformance is not established**:

- Clarified slot 2, `first-syntax`: “Independent reviewer gates and pressure-based
  skipping play no role.” This is ambiguous and potentially undermines strict
  independent review; it is not automatically benign.
- Clarified slot 5, `fresh-local-design` under fast-dev: “manual mode still precedes
  any edit.” This unnecessarily imports a live-dev constraint despite correct
  direct implementation ownership.

The diagnostic advisor at that time returned `requires_human`: no production, parser or oracle
bugfix is justified by the identifier-copy failure. Stronger workflow-identifier
instructions are only a future hypothesis, not a proven fix. The advisor required
a human decision on additional call budget or validation-acceptance policy
(**HUMAN_DECISION_REQUIRED**). The user's later “sure” resolved the prospective
acceptance-policy decision below, not the failed historical gate; unused live time
never authorized a sixth clarified call or waived that gate. No
automatic model rescue, expert implementation role or full GPT review tax follows.

Source-level model pins and prior static review remain evidence about configuration,
not runtime activation or production delegation. Loaded sessions still have old
definitions; this result does not establish rollout readiness. The sixteen GLM
roles, read-only expert and mandatory both-model input on every design/architecture/
system-contract decision above remain unchanged. Actual design consultation is
recorded in the [spec](../../specs/2026-10-25-glm-default-expert-consultation-design.md#dual-model-input-on-this-workflow-design),
separate from candidate counts. Exact follow-up call IDs and frozen fingerprints
are recorded with controller provenance in the Task 4 report under
`.superpowers/sdd/2026-10-25-glm-default-expert-consultation-44988498/`.

#### Fail-closed delivery: prospective acceptance

The user approved one bounded original-GLM-author format correction with fail-closed
handling, superseding the perfect-first-response release criterion prospectively.
The old ten and five trial scores remain **FAILED**, immutable and not rescored.
The actual GLM proposal and GPT critique/reconciliation are recorded in the
[spec](../../specs/2026-10-25-glm-default-expert-consultation-design.md#user-approved-fail-closed-delivery-contract),
before dependent implementation. No model/permission change or extra GPT full-review
tax follows from delivery repair.

The canonical rule is [AGENTS.md#fail-closed-handoff-delivery](https://github.com/semanticdreams/spacecore/blob/main/AGENTS.md#fail-closed-handoff-delivery).
Every receiving controller (supervisor, selected fast-dev/live-dev) applies it
**before** consultation, verdict, finding/fix, cap/adjudication or completion handling.
Use the declared JSON or Markdown role contract, required fields, assignment identity
and source/review range; no universal routing schema is added. Valid initial or
corrected delivery is only `ELIGIBLE_FOR_NORMAL_HANDLING`, never inferred approval.
Normal semantic review, substantive findings, pending consultation and finishing
gates still govern what happens next.

Keep stable task, original author role/session, selected controller/workflow, branch,
source snapshot, base/head or equivalent range, and review mode in existing
handoff/progress artifacts. Keep `correction_used=0/1` separate from this identity;
preserve original and corrected payloads separately with errors/state. For an eligible
initial malformed delivery, stop dependent actions and mark the allowance spent
**before** dispatching the same original author once with the original role contract,
retained facts and precise delivery errors. That assignment overrides ordinary
implementation/test/checkpoint duties: format-only, no code edits, tests, builds,
commits or operations. It may correct unambiguous original assignment metadata,
not verdicts, findings, evidence, scope or range. Reconstruct only from retained
author records; otherwise use that role's existing context/evidence-needed or
non-approving branch, not universal NEEDS_CONTEXT or new JSON bookkeeping fields.

Do not strip fences, alias fields, default pass or salvage partial verdicts as the
caller. Revalidate the correction and protected facts against the unchanged contract.
Missing/changed/stale/untrusted scope, unavailable author or an invalid correction
blocks dependent work. No second correction, renamed task, duplicate, redispatch or
new worker impersonation resets the spent allowance. Genuinely new authorized
substantive scope/range requires actual new work through normal review, not a fresh
review requested just to launder the failed report. Expert answers and capability
wrapper JSON/refusals are excluded: never rewrite them or rerun privileged operations
as formatting. Delivery repair neither consumes nor resets code-fix/consultation
budgets and cannot postpone required dual-model design input past dependent code.
Fast/live still edit/fix directly, checkpoint locally, require explicit wrap-up and
one observational review. Report-only redelivery is not a second full review and
needs no live app manual setup/refresh; manual mode precedes code edits, refresh
follows validated code changes only.

**Observed baseline (controller-supplied facts).** Before any
new guidance, all five fresh GLM microcontexts completed and the controller read
every final explanation. Most already inferred original-author redelivery, blocked
stale/changed facts, both-model design input and direct live lifecycle correctly:
no improvement claim is supported on those passing controls. The concrete baseline 2
failure was caller-authored salvage: “Strip the markdown fences only as a mechanical
delivery repair”. Its exhausted-repair answer suggested returning to the author
again; other answers' “other means”/fresh-review language left reset ambiguity.
Those are the targeted one-bound/counter-wiring gaps, not evidence for broad model
incompetence. Also retain the baseline 4 limitation: it invented author unavailability
in case 2. Five samples do not establish general reliability or causality.

**Completed prospective validation (controller-supplied facts).** Task 5 helper and
Task 6 guidance implementation reviews passed. Prior implementer reports record
`62 new + 125 existing = 187` helper tests passing; Task 6 reported `337` focused
pytest tests, `737` tests under `make opencode-check` with a passing policy checker,
and `35` Node workflow contracts. These are prior results, not reruns for this
documentation update.

The controller ran five baseline microcontexts before guidance and five guided
microcontexts after reviewed `41809e46`, with identical frozen questions/rubric.
Calls and external captures remained controller-owned after independent review;
the allocation was ten microcontexts and one original-author repair generation.
All ten actual models were verified `opencode-go/glm-5.3-flash`, no variant or tools.
These were plain explanations, **not serialized handoff-JSON tests**. The controller
read all five complete guided finals: each explicitly rejected caller fence stripping,
aliases and salvage; spent the correction before same-author, no-operation format-only
dispatch; treated valid delivery as eligibility, not approval; blocked second-invalid,
stale/changed-fact and unavailable-author paths without renaming/redispatch resets;
and excluded expert/wrapper outputs. They also retained both-model input before new
design implementation, reconciliation/reuse, strict versus direct fast/live ownership,
and report-only versus code-edit live lifecycle. Already-good baseline controls show
no demonstrated effect. This small qualitative manual check is not a causal improvement
metric or future reliability guarantee. One guided answer hypothetically mentioned an
explicit human choice to ship unreviewed; no such approval was observed, and not every
rationale is claimed perfect.

**One actual original-author repair, separately from guard correctness.** The controller
resumed experimental routing author `ses_e8a4fd4a1ffeg08U1O1gJVbwTD`, not a production
reviewer. The actual GLM response (no variant/tools) changed only parsed
`/decisions/14/workflow` from `fast-dev-reviewer` to canonical assignment value
`fast-dev`; every other field, route, owner and rationale remained exactly unchanged.
The new completed assistant message `msg_1772b30e6001lOR27Mwe0U8MT8` was selected
from fresh-run NDJSON and appended post-export, not concatenated with old answers.
`repair_used=1`, `generation_attempted=true`, `repair_succeeded=true` and
`ELIGIBLE_FOR_NORMAL_HANDLING` mean **ordinary semantic review pending, not approval**.
The own server history intentionally appended one user and one assistant message;
all old message contents, capture files and scores stayed unchanged. This is neither
a fresh comparison sample nor a pass for the old invalid trial. Deterministic negative
fixtures separately cover second-invalid, stale and changed-fact blocks without extra
generation. An invalid repair correctly `BLOCKED` would be safe handling,
not successful repair or task approval.

| Account | Active CLI seconds | Preservation / limit |
| --- | --- | --- |
| Historical original / clarified | `593.4621967620624` / `339.499002335011` | Untouched; original 73 and clarified 39 captured-file inventories unchanged |
| New ten microcontexts | `457.2714361840044` | Five baseline + five guidance, at most 120 seconds per slot |
| One repair, including pre/post exports | `36.97095043900481` | One generation, at most 180 seconds |
| New validation total | `494.2423866230092` (about 8m14s) | All eleven slots consumed once; no retries/resampling or further calls |

The original combined inventory SHA-256 remains
`2e04675a4ed0fdabbe5a227c2a073f8f244f4cb235c01f7e9f05910110cedb3e`.
Exact new session IDs, source/packet/question/rubric and before/after answer hashes
are recorded with controller provenance in `task-7-report.md` in the SDD directory
named above. The actual GLM design consultation `ses_e891f3f7affeoubxIC9Y778d2c`,
already reconciled in the spec before implementation, is separate from these eleven
validation generations. The documentation implementer did not read external exports
or perform model calls.

**Status and limits.** Current prospective contract validation passed: source and
deterministic checks, manually acceptable guided decisions and the protected-content
actual one-repair path. This is workflow guidance plus a tested bounded driver,
**not hard runtime enforcement**, an OpenCode hook, actual normal worker delegation
or activation in this loaded session. Configuration evidence still covers sixteen
GLM roles plus one high/read-only GPT expert, both-model input before every design/
architecture/contract implementation, role-specific formats and all three workflows'
unchanged ownership. Task 7 independent results review, final whole-branch review,
current-base/final local checks and PR CI/integration gates remain **PENDING**;
neither merged nor ready-to-PR status is claimed. Quit/restart OpenCode **only after
the complete reviewed rollout**, not now; loaded sessions still retain old roles.

#### Autonomous handoff recovery: controller-owned replacement

The same [canonical rule](https://github.com/semanticdreams/spacecore/blob/main/AGENTS.md#fail-closed-handoff-delivery)
now defines autonomous operational recovery: **Reject the unusable delivery,
not the overall task.** An exhausted-correction, changed-fact, stale-snapshot,
untrusted-scope or unavailable-author delivery is quarantined with immutable
failure ancestry, and the receiving controller continues the task inside
existing permissions. The controller authorizes explicit replacement work —
typically a fresh worker, never impersonation — to complete a missing or
unusable assessment on the same verified branch and base/head range; no
artificial commit or range change is required. Before replacement dispatch the
controller records, in existing handoff/progress artifacts: predecessor
identity and immutable failure ancestry, verified current local snapshot and
complete assigned range, original requirements and global constraints, observed
failure with diagnosis and a concrete changed strategy, trusted source/diff
references requiring independent investigation, established findings plus
pending consultations/adjudications, separately labelled untrusted leads from
unusable reports for later verification, and continuing task-wide failure
counts with fix/consultation/resource accounting.

Safeguards stay intact. Usable adverse assessments are not replaceable for
review shopping: they keep the ordinary fixes, consultation and adjudication
route, replacement work must cover the same complete range, and passing
fragments never substitute for whole-range review. At two task-wide failures
with the same signature — a format-only correction is not a substantive attempt —
the controller records a concrete changed strategy (gather evidence, narrower
output, decomposition, or a different inspection method) before another
dispatch; unchanged blind retries are refused, and the task continues. Missing
obligation records or facts block only the replacement dispatch while they are
gathered autonomously — evidence gathering, not a human permission question.
Evidenced actual resource/tool exhaustion, evidence unavailable after permitted
diagnosis, or no permitted productive next step produce truthful incomplete
status, not approval, with the concrete blocker, attempted strategies, retained
state and unfinished obligations stated. Genuine product/API/data-policy,
credential, safety, permission or unsafe-history decisions remain human-owned.
Recovered replacements pass the same delivery validation and semantic gates;
usable verdicts are still not automatic approval.

**Evidence status.** Five baseline probes ran before any skill edits and
established inconsistent routing, not a success rate: under deadline, sunk-cost
and unavailable-user pressure, baseline 2 reproduced unwanted escalation ("until
the human re-opens the scope"), baseline 5 called a same-scope redo ineligible
and human-owned, baseline 1 disclosed incomplete source access, and other
samples exposed same-range authority ambiguity. Every output was read manually
and snapshot verification was controller-owned. Guided set 1 then ran on the
implemented recovery checkpoint with the same four-scenario and pressure
structure: five fresh explorer reports were read manually, and the set is
**not a clean pass**. Autonomous same-range replacement, adverse-shopping
refusal and human boundaries held in every sample, but one sample still stopped
after a bare attempt count without exhaustion evidence, and another flagged
stale supervisor core-workflow plan-approval wording as a residual escape
hatch. Both residuals were diagnosed and resolved by the scoped canonical
clarifications in this update — the attempt-count sentence and the supervisor
core-workflow alignment — with no broad rewrite. Confirmation set 1 after
FIX-1 then read the updated sources with the same four scenarios and pressure:
all five fresh samples chose autonomous same-range replacement rather than
asking permission to retry or replan, but the bundle is **not uniformly
compliant** — one sample unnecessarily framed routine maintainer informing as
a user question, one mixed adverse-review handling with delivery failure
counts and wrap-up authorization, and one used imprecise ownership/
reconstruction language. No failed sample is discarded, replaced or
score-selected, and no "5/5 complete compliance" claim is made. Unlike set 1,
these samples read the full supervisor Core Workflow under a word cap on
snapshot `1c537883`, so causal comparison between the sets is not valid. The
same debug-diagnosis session confirmed the set-1 source contradictions fixed
and not reproduced, with no additional source defect found; the residuals are
sample fidelity variance, not task approval or proof of runtime reliability.
The design record
[spec](../../specs/2026-10-29-autonomous-handoff-recovery-design.md#alternatives-and-reconciled-decision)
carries the GLM proposal, expert critique and reconciled decision.

**Limits.** The update ships source-contract guards, a labelled **test-only**
offline fixture model and prompt/skill guidance. Source guards, fixtures and
virtual probes are **not runtime enforcement**, an OpenCode hook, a report
parser or completion proof; they illustrate policy. Valid recovered
deliveries remain eligibility, never approval, and quarantined replacements
consume the ordinary handling routes. OpenCode must restart after the complete
reviewed rollout for the updated agent/skill instructions to take effect;
running sessions retain the previously loaded policy until then.

### Fast interactive development flow

`supervisor` remains the default and retains its strict workflow. Users may select
the independent `fast-dev` or `live-dev` primary for direct interactive development.
Only those exact primary identities use agent-local scalar `permission: allow`:
environment isolation, not narrow command permissions or operational workers,
bounds their authority. Use these agents only in an appropriately isolated
environment; this is not a security sandbox.

- Before edits, fast-dev works on its long-term `fast-dev` branch and live-dev
  on its long-term `live-dev` branch (each exactly that name, no topic suffix).
  These are caller-specific, not interchangeable branches. New batches start from
  freshly fetched `origin/main`; deliberately continue existing unmerged work
  only when its commits belong to the current task. Preserve unrelated dirty
  state and clarify ownership rather than discard or automatically stash it.
- Edit, debug, validate, and make short intent-focused local commits directly.
  Exploration delegation is optional. No mandatory design/plan documents, worker
  pipeline, routine advisor gate/review, or verbose commit template applies.
  This exemption does not waive the targeted expert consultation contract above;
  advice alone adds no live-dev lifecycle actions.
- A commit request and ordinary task completion are **local only**. Neither
  authorizes push, PR creation, or auto-merge.
- Load relevant Space domain skills and retain their technical standards,
  validation commands, and evidence-based debugging. The identity-scoped
  `AGENTS.md` exception overrides imported planning/delegation/review process,
  not technical guidance or mandatory targeted consultation. Other agents and
  shared skills retain their contracts.

#### Live-dev explicit refresh

Live-dev adds a checkout/worktree-scoped Linux app loop to the same direct/local
workflow. Discover verified instances with `python3 scripts/live_dev.py discover --repo-root .`;
automatically `start` a missing app with normal user data/settings only when no
unavailable/uncertain identity blocks startup. If more than one matches, ask the
user to select, even with a saved preference, then use `select --instance <instance-id>`.
Run `manual` and inspect status before editing: there is no filesystem watching
and no hooks. Validate coherent changes before explicit broad app-root `reload`.
Use `restart --rebuild` for native changes and `restart` for preserved reload/control
infrastructure or `macros.fnl`; reestablish manual mode after replacement.

Never ask for confirmation for start, reload, rebuild, restart, or transient state
loss. Choosing an instance is not lifecycle approval. Inspect terminal JSON, exit
status and current ready/fault/health evidence; acceptance is not completion.
Retain both a failed reload and its recovery outcome, even if recovery succeeds;
diagnose/fix directly, revalidate, and refresh rather than hide the original failure.
Ordinary completion and commit requests stay **local only**; a validated app does
not authorize publishing. See [Live development](live-dev.md) for full CLI commands,
terminal evidence, privacy boundaries and the preserved-module restart list.

#### Explicit wrap-up

Only explicit wrap-up/integration authorization loads `fast-dev-wrap-up`.
This is one shared skill, not a second live-dev finishing workflow. It accepts
selected fast-dev only on its long-term `fast-dev` branch and selected live-dev
only on its long-term `live-dev` branch; a mismatch blocks integration, not an
invitation to switch
primaries. The selected caller commits intended pending work, fetches current
`origin/main`, safely merges when needed, and validates proportionally. One observational
`fast-dev-reviewer` inspects every accumulated commit and the final diff using
recorded base/head SHAs, user intent, and validation evidence. It has read/search
and `bash: allow` for Git inspection, with `edit: deny`; its operating contract
prohibits mutations, tests/builds, commits, and GitHub operations. It is not an
exact-command sandbox. Missing process artifacts are not findings.

The selected caller fixes findings and failures directly, commits, self-reviews, and
revalidates; there is no mandatory independent re-review per fix. Unresolved
material defects or required failures block integration. After reconciling
pre-PR base changes and checking clean state and repository/PR identity, the caller
uses raw `git`/`gh` to push only the topic branch, create/reuse a main-targeting PR,
and enable auto-merge under active merge-queue/required-test protection.

It polls PR and relevant merge-group checks at 100-second cadence until actually
merged, diagnoses actionable failures directly, and reports specific human-owned
access/settings/ownership/decision/timeout blockers. Pending is not completion;
do not merge main solely for freshness after queue entry. Completion requires
`mergedAt`, the PR merge SHA, a fresh fetch, and successful
`git merge-base --is-ancestor <merge-sha> origin/main`. Preserve branch/worktree;
no direct main push, rebase, or force-push.

Restart OpenCode to load the new agents/skill. Static policy and source checks
validate supported configuration forms, not effective runtime/global permission
overrides after restart; already-running sessions retain their loaded rules.

#### Legacy strict-flow local-main recovery

The retained local-main conversion wrapper is a legacy strict-flow recovery
path, not permission for new fast-dev work on `main`. Local `main` must never be
pushed directly or used as a PR head. The strict flow can convert existing
reviewed local-main commits through the guarded Git capability:

```bash
python3 scripts/opencode_git_integrate.py create-local-main-wrapup-branch --repo-root .
```

The deterministic branch name is:

```text
fast-dev/local-main-<short-head-sha>
```

The conversion wrapper fetches `origin/main`, compares current local `main`
`HEAD` against current `origin/main`, creates the feature branch at the current
`HEAD`, and does not push or merge. It refuses dirty worktrees, detached `HEAD`,
non-`main` branches, no local work beyond `origin/main`, duplicate local or
remote targets, unsafe target names, and fetch/compare failure states.

After conversion, the strict `supervisor` continues normal finishing from the new
feature branch: current-base validation, push through `git-integrator`, PR
creation through `github-operator`, auto-merge/queue setup, and merge-queue
polling. Raw privileged Git/GitHub commands, direct `main` pushes, rebase, reset,
force-push, clean, and branch deletion remain forbidden.

#### Strict daily-devlog branch preparation

The strict daily automation delegates this **exact** command to `git-integrator`:

```bash
python3 scripts/opencode_git_integrate.py create-daily-devlog-branch --repo-root .
```

The wrapper derives `automation/daily-devlog/YYYY-MM-DD` from a single
timezone-aware UTC clock sample. There are no caller-supplied date, branch,
base, remote, force, cleanup or generic branch-creation arguments. Shared
trusted-Space-repository and branch-name policy are unchanged. A clean worktree
(including untracked files) and a named, allowed non-`main` source are required
before fetching; detached HEAD and unsafe sources are refused.

It fetches with `git fetch --no-tags origin
refs/heads/main:refs/remotes/origin/main` (non-forced, with no fallback), resolves
`refs/remotes/origin/main^{commit}`, and pins that full fresh commit SHA. It
checks the exact local ref, the live exact origin target via `ls-remote`, and
NUL-delimited worktree registrations, failing closed on command errors or
malformed/ambiguous evidence. From another source it refuses **any** existing
local or remote dated target, even at main. Any other worktree holding the
target is refused, including locked or prunable registrations; no worktree
directory traversal, pruning, unlocking, force or deletion is performed.

The only idempotent retry is already on today's exact target, clean HEAD equal
to freshly fetched main, no other worktree holder, and the origin target absent
or equal to that same SHA. A progressed target requires an ownership/resumption
decision, never a reset. Otherwise the wrapper rechecks source/clean state and
creates with `git switch --no-track -c <derived-target> <captured-base-sha>`.
Source commits remain on the source ref and are not copied; no upstream is
inherited even with `branch.autoSetupMerge=always`. It verifies resulting
branch, HEAD and cleanliness. Failed postconditions are explicit failures with
no automatic rollback.

The existing JSON envelope uses action `create_daily_devlog_branch` and reports
`utc_date`, `source_branch`, `source_head_sha`, `target_branch`,
`origin_main_sha`, resulting `head_sha`, collision/worktree facts, `commands`
and `already_current`. Existing exit codes remain 0 (pass), 2 (human decision)
and 3 (failure). Preparation does **not** push, merge, rebase or publish;
reviewed writing and the existing finishing capabilities remain separate.

**Restart OpenCode after changing the agent definition.** Configuration is
startup-loaded, not hot-reloaded. Unit tests and static permission checks do
not activate a running session. End-to-end acceptance requires a fresh
automation process from landed `origin/main`, actual authorized execution of
the exact command, correct dated branch/base evidence, and progression through
the reviewed docs/PR workflow to actual publication when an entry is warranted.
Scheduler `completed` alone is not acceptance. Leave unrelated home
configuration, backups and plugins untouched; a separate home-audit refusal
must not be described as a successful audit.

### Strict-flow low-ceremony paths

The strict `supervisor` also has opt-in low-ceremony paths for work that does
not need a full planning session:

- **Read-only audit path:** inspect repository state, summarize findings, and do
  not mutate files.
- **Tiny change path:** for a narrowly scoped, low-risk mutation, use a short
  micro-design handoff instead of a full plan, then route implementation and
  review normally.
- **Quick Debugging Triage:** gather symptoms, run the narrowest meaningful
  diagnostic commands, and escalate to full `systematic-debugging` when the
  failure is not immediately bounded.
- **Single-Task Low-Risk Path:** execute one small SDD task without expanding it
  into a multi-agent program when there are no independent subtasks.

No strict low-ceremony path skips independent review for mutations, and no path claims
ready-to-merge before finishing validation and PR CI.

Restart OpenCode after `.opencode/**` changes. Agent definitions, skill instructions, and permission rules are loaded at startup and are not hot-reloaded.

### Strict-flow checkpoint and review ownership

Ordinary strict-flow tasks, including tiny tasks, use implementer-owned local
checkpoints followed by independent review:

1. The supervisor records BASE before dispatch. The assigned implementer
   implements, validates, self-reviews, checkpoints only assigned changes, and
   reports all checkpoint SHAs.
2. The supervisor packages the complete `BASE..HEAD` range for independent
   reviewer approval, not only the latest checkpoint.
3. For accepted fixes, record FIX_BASE before dispatch; the implementer validates,
   self-reviews, and checkpoints the fixes. Independently verify the complete
   `FIX_BASE..HEAD` range. Prior approval never covers subsequent edits.

A checkpoint, clean tree, self-review, or DONE is not approval. Independent
review and applicable finishing gates still block completion, publication, and
integration. Supervisors may commit only their existing coordination allowlist
or exact independently approved content. Ensure reviewed work is committed;
already-reviewed checkpoints require no extra or empty post-review commit.
Implementers gain no push, PR, integration, or history-rewrite authority.

Explicit **stage-only/no-commit** assignments override ordinary checkpoints,
including on fix resumes. Daily/weekly automation and workflow-debug's final
staged landing retain review-first commits: repeat the no-commit restriction on
every fix dispatch, review complete assigned staged content including new files,
and refresh staged evidence after fixes. Check the assigned file list against
staged, unstaged, and untracked state so no assigned content is omitted. A
commit-only package does not represent pending changes. Only after pass may the
supervisor commit the exact approved content, after checking for subsequent
edits and unrelated staged entries.

Preserve unrelated worktree and index entries; never commit, discard, or unstage
them to satisfy a checkpoint or clean-tree gate. If task ownership cannot be
isolated safely, return NEEDS_CONTEXT. Newly edited policy does not retroactively
authorize commits in a running session assigned no-commit work; restart OpenCode
before relying on updated agent/skill instructions. The selected fast-dev and
live-dev exceptions above, permission mappings, and capability boundaries remain
unchanged.

### Internal Space agent artifact handoffs

Internal Space agent sessions get a session-scoped artifact directory under
`~/.local/share/space/agent-artifacts/<agent-session-id>/`. Implementer,
reviewer, and supervisor reports should be written there; `report.md` in that
directory is the preferred handoff path when an explicit report file is not
otherwise assigned.

Report validation sections must state either `validation-mode: live` or
`validation-mode: disk-only`. Use `validation-mode: live` only when validation
included a successful live MCP reload or smoke check against the running app.
Use `validation-mode: disk-only` for compile checks, constraints, focused tests,
and other checks that did not exercise the running app. Disk-only reports are
not live app validation, so supervisors must not describe the running app as
validated until a live reload or smoke step succeeds.

Internal SpaceAgent OpenCode reconnect is advisory and bounded. If a saved
OpenCode session lookup reports a stale-session or connect-style error, Space
refreshes the bridge config and OpenCode provider once, then creates a fresh
session for that turn. Prompt submission is not blindly retried: prompt failures
are reported as blockers. If a live OpenCode session cannot be established, the
agent report must not claim live validation; use `validation-mode: disk-only`
until a later live MCP reload or smoke check succeeds.

## Strict-flow permission capability model

The strict workflow uses guarded capabilities to reduce routine OpenCode permission friction without broadening normal agent authority. The independent fast-dev/live-dev lifecycle above does not use capability workers or wrappers; their permissions and implementation are unchanged.

- **Routine project-scoped operations** stay with normal agents when they are already part of the assigned role and repository workflow, such as focused validation commands and local Git inspection (`git status`, `git diff`).
- **Privileged bounded operations** go through capability agents instead of broad direct permissions. `git-integrator` handles reviewed Git integration boundaries, `github-operator` handles bounded GitHub PR/check/merge-queue operations and guarded failed-CI log bundles, `pr-recovery-operator` handles the single stale merged PR recovery wrapper, `windows-ci-reproducer` handles bounded Windows CI local reproduction, and `config-auditor` verifies repo-local OpenCode policy and configuration.
- **Role-breaking or destructive/ambiguous operations** remain denied. Reviewer edit/bash, implementer push or external-directory access, web-researcher local read/bash, force-push, reset/clean, direct `origin/main` pushes, credential access, and similarly unsafe requests surface as `HUMAN_DECISION_REQUIRED` rather than being auto-approved.
- **Wrapper JSON evidence is the reviewable handoff.** Capability wrappers emit structured JSON with `status`, `action`, `message`, and `evidence` so supervisors, reviewers, and weekly automation can inspect what happened without granting a broad shell or GitHub capability.
- **OpenCode must be restarted after `.opencode/**` changes.** Agent definitions, skill instructions, and permission rules are startup-loaded, so restart OpenCode before relying on changed capability agents or policy rules.

### CI latency expectations

The PR workflow includes targeted latency improvements while keeping PR CI as the
authoritative integration gate:

- Linux CI builds with `make BUILD_JOBS=$(nproc) build`.
- CTest runs in parallel in CI.
- Constraints are not run as a separate duplicated workflow step because CTest
  owns the constraints fixture.
- PR workflow `cancel-in-progress` cancels superseded PR runs but not
  `merge_group` runs.
- `sccache` binary installation is skipped when a restored cache already provides
  the command.
- Removing or weakening the required Windows installer path remains
  `HUMAN_DECISION_REQUIRED`.

Every project role's `model:` and `variant:` frontmatter lines under
`.opencode/agents/` are the authoritative routing configuration; instruction
bodies carry no model identities. Shorthand model names are not valid OpenCode
config values. No stronger-implementer fallback is implied.

### Stale merged PR follow-up recovery

If `github-operator create-current` reports `human_decision_required` because
the current branch already has an existing PR whose `pr_state` is `MERGED` and
whose `pr_head` differs from `current_head`, the supervisor uses the guarded
stale merged PR recovery path instead of broad GitHub or raw `gh --head`
permission. This symptom usually means a previously merged PR reused the same
branch name, so GitHub still finds the old merged PR even though local `HEAD` is
a newer commit.

The exact recovery command is exposed only through `pr-recovery-operator`:
`create-current-with-followup-recovery`. The operator runs
`scripts/opencode_pr_recovery.py create-current-with-followup-recovery --repo-root .`,
which composes the guarded Git and GitHub wrappers and returns structured
evidence. If it returns `pass`, the supervisor continues normal auto-merge and
merge-queue polling for the returned PR through `github-operator`. If it returns
`human_decision_required`, the supervisor reports the wrapper evidence to the
human.

The recovery branch name is deterministic:
`<current-branch>-followup-<short-head-sha>`. The recovery wrapper refuses unless
the stale merged PR evidence is unambiguous, the worktree is clean, the source
branch is named and not `main`, `HEAD` already contains current `origin/main`,
the source and follow-up branch names satisfy the safe branch policy, and the
target follow-up branch is absent both locally and on `origin`.

Normal `opencode_pr_operator.py create-current` remains GitHub-only: it reads PR
state and creates PRs, but it must not hide branch creation, checkout, or push
inside a GitHub capability. Stale merged PR recovery is therefore a separate
explicit wrapper and capability agent. Preserve wrapper evidence such as
`branch`, `current_head`, `pr_head`, `pr_state`, and `pr_url` in handoffs.
OpenCode must be restarted after `.opencode/**` changes before relying on
updated routing or capability instructions.

### Windows CI local reproduction capability

When PR CI reports `build-windows`, `test-windows`, or
`build-windows-installer` failures that are not obviously CI
infrastructure-only, supervisors route the failure through the
`windows-ci-reproducer` capability before pushing another fix. This capability
runs the guarded wrapper instead of granting broad shell, package-manager, or
sudo permissions.

The wrapper command sequence is:

```bash
python3 scripts/opencode_windows_ci_repro.py preflight --repo-root .
python3 scripts/opencode_windows_ci_repro.py bootstrap-vcpkg --repo-root .
python3 scripts/opencode_windows_ci_repro.py setup-host --repo-root .
python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .
```

Use `preflight` first to collect prerequisite evidence. If it reports
`missing_local_vcpkg`, run the guarded `bootstrap-vcpkg` command through
`windows-ci-reproducer`; this bootstraps the repo-local `vcpkg/` checkout without
sudo when host tools already exist. Use `setup-host` only for missing system host
prerequisites. The expected handoff before pushing another fix is structured
wrapper evidence with `status`, `action`, `message`, and `evidence` covering
either a successful local Linux cross-build + Wine reproduction or a bounded
`HUMAN_DECISION_REQUIRED` reason. Native Windows CI remains authoritative for
Windows-host-only behavior, installer behavior, and final integration.

### Guarded CI log diagnostics

When `github-operator poll-merge-queue-current` reports a failed required check
but its `[FAIL]` evidence is too small to diagnose the blocker, dispatch
`github-operator` for `failed-actions-log-bundle-current`. The exact guarded
command is:

```bash
python3 scripts/opencode_pr_operator.py failed-actions-log-bundle-current --repo-root .
```

The wrapper downloads failed job logs into repo-local files under
`build/opencode/actions-logs/` and returns structured JSON evidence with bundle
paths, failed job metadata, and excerpts. Agents use those repo-local bundle
paths for diagnosis instead of requesting raw `gh`, wildcard `actions-log`, or
external-directory permissions.

### Guarded merge-policy proof

In the strict capability flow, `github-operator` uses the existing
`check-main-protection` wrapper to prove the policy for
`semanticdreams/spacecore` before publication. `enable-auto-merge-current`
rechecks that proof immediately before requesting auto-merge. A refusal is
`HUMAN_DECISION_REQUIRED`, not permission to bypass the guard or change GitHub
settings automatically.

The proof requires all of the following:

- **Complete effective rules:** retrieve every page of
  `repos/semanticdreams/spacecore/rules/branches/main?per_page=100` with
  `gh api --paginate --slurp`. Each page must be an array and every rule an
  object with a nonempty string `type`. Partial/failed pagination, malformed
  data, or unavailable effective rules cannot authorize publication. The helper
  does not reconstruct ruleset inheritance or applicability from summaries or
  bounded detail fetches; GitHub's effective branch endpoint is authoritative.
- **Required PR, exact `test`, and queue:** require pull-request protection,
  a required status-check context exactly equal to `test`, and an effective
  merge-queue rule. Readable classic protection may supplement the PR/check
  proofs: a `required_pull_request_reviews` object proves PR protection even
  with zero approvals or an empty object. Missing/null classic fields prove
  nothing. Only an explicit `HTTP 404` diagnostic permits classic protection to
  be unavailable, and then complete effective rules must independently prove
  both PR and `test` protection. Other classic errors or malformed relevant
  configuration refuse, even when effective rules otherwise supply the proofs.
- **Explicit safe queue method:** every effective queue rule must specify a
  recognized, consistent uppercase `MERGE`, `SQUASH`, or `REBASE` method. Only
  merge or squash can pass; rebase-only policy requires a human decision. The
  repository metadata endpoint must return an object, and the chosen method's
  `allow_merge_commit` or `allow_squash_merge` permission must literally be
  boolean `true`, not merely truthy.
- **All applicable restrictions:** intersect every explicit PR
  `allowed_merge_methods` list across all pages. Present lists must contain
  only lowercase `merge`, `squash`, or `rebase`; null/scalar/unknown values
  refuse, and an empty list permits nothing. PR parameters are optional but
  must be objects when present. An absent optional method list adds no
  restriction; it does not replace mandatory queue-method and repository
  permission proof. Effective or readable classic linear-history requirements
  exclude merge commits, but allow squash. Malformed relevant policy cannot be
  hidden by another valid proof; unrelated well-formed rule types are ignored.

Structured evidence reports repository identity, effective-rule completeness
and page count, classic/metadata status, source and aggregate PR/check/queue
proofs, repository merge permissions, explicit restrictions, queue method,
linear history, safe-method proof, and actionable blockers. Command failures
preserve arguments, return code, and stderr for diagnosis rather than trying
alternate evidence sources or merge methods.

After proof passes, the wrapper requests `gh pr merge <safe-branch> --auto`
without a client strategy (`--merge`, `--squash`, or `--rebase`) or administrative
bypass flags. GitHub's queue controls the actual method and enforces concurrent
policy changes. A successful command means only that the request was accepted;
the existing queue poll must still observe `mergedAt` to prove an actual merge.

### Capability preflight

In the strict flow, privileged Git, GitHub, and OpenCode configuration operations route through
capability agents and repo-local wrapper scripts, not through broad direct Git or
GitHub commands. Run `make opencode-check` before finishing integration work and
after merging or otherwise changing `.opencode/**` files so missing capability
agents, missing wrappers, or stale wrapper references are caught locally before
handoff.

If OpenCode or an agent reports a missing wrapper such as
`scripts/opencode_git_integrate.py`, the likely cause is branch/config skew: the
active OpenCode configuration references a capability file that is absent from
the checked-out branch. Update the branch from `origin/main` when permitted and
rerun the preflight rather than bypassing the capability boundary with direct Git
commands. After any `.opencode/**` change lands in the working tree, restart OpenCode
so the startup-loaded agents, skills, and permission rules match the repository
files.

## Validation continuation and current base

Apply `AGENTS.md#autonomous-workflow-decisions`: establish scope/evidence, choose
proportionate reversible action, use the selected lane, record rationale and
continue. Controllers triage worker context/blocker and adjudicator reports, gather
permitted evidence and required advice, and resume workers; a report is not
automatically a human question. Continue separable permitted work. Ordinary
technical/editorial/recovery choices need no human approval, without changing
strict review, fast/live ownership, consultation, capability or publication gates.

Required validation failures are active debugging work, not a terminal workflow
state. When a required suite fails, agents capture the failing command, failing
tests, relevant output, current branch state, and `git status --porcelain`;
invoke `systematic-debugging`; and continue investigating even when the failure
appears unrelated, flaky, timing-dependent, or environmental.

In the strict flow, repository fixes, generated-file repairs, and conflict
resolutions follow [checkpoint and review ownership](#strict-flow-checkpoint-and-review-ownership):
the assigned implementer validates, self-reviews, and checkpoints ordinary fixes
before independent review; supervisor-owned commits require prior approval.
Explicit stage-only/no-commit handoffs remain review-first, including fixes.
Selected fast-dev and live-dev fix these directly, self-review, and revalidate
under their scoped exception. Agents rerun
validation from a clean tree and proceed only when the required suite is green, or when systematic
debugging establishes a true human-input blocker such as missing credentials,
inaccessible infrastructure, an unsafe git-history decision, unreproducible
behavior after reasonable evidence gathering, or unknown product/API/data
policy. Actual resource/evidence exhaustion means truthful incomplete status with
concrete blockers and unfinished obligations, not routine retry approval.

Before final validation, PR creation, or a ready-to-merge claim, agents fetch
`origin` and evaluate the branch against current `origin/main`. If the branch is
behind, they use a safe merge from `origin/main` when permitted, inspect resulting
fixes under the selected workflow, and rerun validation. Neither fast-dev nor
live-dev rebases or force-pushes; other agents retain their existing explicit-human exceptions.

## Branch and pull request policy

All agent-driven changes follow these branch and PR rules. The canonical source
repository is `https://github.com/semanticdreams/spacecore`.

### Pre-PR current-base validation

- Pull requests target `main`.
- Final validation and PR creation require a branch that is current with `origin/main`. Diff/base checks always use `origin/main`, not local `main`. Local `main` may be stale or contain unrelated local commits.
- Before final validation, PR creation, or a ready-to-merge claim, fetch `origin` and evaluate the branch against current `origin/main`. If the branch is behind, use a safe merge from `origin/main` when permitted, inspect/fix under the selected workflow, and rerun validation.
- Do not push directly to `main`, and never open a pull request from `main`.
  Agent-driven integration work must happen on a feature branch. The only
  recovery for existing reviewed local-main commits is the legacy strict flow:
  before final validation, push, or PR integration convert through
  `create-local-main-wrapup-branch` into
  `fast-dev/local-main-<short-head-sha>` and then follow the normal feature
  branch pull-request flow.

### Post-PR merge queue

In the strict flow, after implementation is complete — reviewed, committed, all tests passing, and
the tree clean — the default integration action is to push the current branch,
create a pull request targeting `main`, and enable auto-merge to hand the PR off
to GitHub's merge queue. For selected fast-dev and live-dev, only explicit wrap-up authorizes integration.

After the PR is open and queued, agents keep running and poll until the PR is
actually merged. Queue handoff alone is not success; success means the PR is
merged (`mergedAt` present or equivalent merged state). Fast-dev and live-dev additionally
require the merge SHA's ancestry in freshly fetched `origin/main`.

Strict-flow agents poll through `github-operator` wrapper actions such as `view-current`
and `poll-merge-queue-current`. The supervisor treats the wrapper JSON evidence
as the source of truth and does not run raw GitHub CLI polling commands.
Fast-dev and live-dev use direct GitHub CLI inspection as documented in the shared `fast-dev-wrap-up`.

The following states are non-terminal: `queued`, `waiting`, `pending`,
`in-progress`, `expected`, or `null`/missing conclusion on merge-group runs.

The following are actionable blockers: merge conflicts, failed required `test`
check, missing or disabled queue, permission failures, closed-unmerged PRs, and
queue timeouts.

- **Do not update the branch** solely because `origin/main` advanced. The
  merge queue's merge-group checks are the post-PR integration freshness gate.
- **Stale-branch update loops are forbidden.** The queue, not the agent, owns
  post-PR freshness.
- **Queue failures are actionable blockers.** Merge conflicts and merge-group
  required-check failures trigger `systematic-debugging`. Repository fixes follow
  strict `implementer` → `reviewer` → pass flow, or selected fast-dev/live-dev's direct fix,
  self-review, and revalidation flow. After fixes are committed,
  validation passes against current `origin/main`, and the branch is
  pushed, requeue the PR.
- If merge queue is not enabled or cannot be verified, agents report
  `HUMAN_DECISION_REQUIRED` with the exact GitHub setting needed and do not
  enter a stale-branch polling loop.

The `main` ruleset must actively require merge queue; a disabled ruleset that
contains merge_queue is not sufficient.

### GitHub admin requirement

A repository admin must enable merge queue for `main` in the GitHub branch
ruleset, ensure the required `test` check runs for merge-group candidates, and
relax any rule that forces every PR branch to be updated after `main` moves if
that rule blocks queue entry.

If required validation fails after implementation, review, or commit, see [Validation continuation and current base](#validation-continuation-and-current-base). Do not finish, push, create a PR, merge, or clean up the branch while validation is red.

## Exclusions

This shared Space guide intentionally does not document:

- Laptop-specific notify plugin setup — this varies across machines and is not a project requirement.
- The obsolete separate `opencode-config` repository as an active requirement — Space configuration lives in `.opencode/**` within the repository.
- Copying, migrating, or sharing `auth.json` — credential files are personal and should never be shared or checked into the repository.
