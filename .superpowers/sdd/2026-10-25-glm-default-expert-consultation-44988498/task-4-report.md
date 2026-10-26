# Task 4 — factual pressure-results documentation

## Status and scope

**DONE_WITH_CONCERNS for results documentation only. Overall rollout BLOCKED,
HUMAN_DECISION_REQUIRED, not published.** Independent review of this checkpoint
still follows; this report does not approve the rollout or waive its failed gate.

BASE: `4fdef0dbfe0b1bce7e52009e8989fbea4e140783`.
Assigned files (complete list, including this addition):

- `docs/dev/features/opencode-agent-workflow.md` — pressure-evidence section only.
- `.superpowers/sdd/2026-10-25-glm-default-expert-consultation-44988498/task-4-report.md` — this report.

Replaced stale guidance-pending text with separate original/clarified outcome
summaries, strict failure diagnosis, manual-review caveats, provenance and the
human-owned blocker. No code, agents, skills, parser, oracle, tests, old evidence,
plan, spec or ledger changed. No policy or design decisions were introduced.
All sixteen ordinary GLM pins and mandatory both-model input on every architecture,
design and system-contract decision remain intact. No expert implementation or
automatic full GPT review was added. Loaded runtime definitions remain old; no
activation, production delegation or readiness is claimed, and no restart is
recommended by this task. No model calls, external reads, native execution,
push, PR or integration were performed.

## Evidence and provenance

Evidence below comes from the task's supplied controller DATA and repository
`task-4-brief.md` / `progress.md` (especially latest outcomes and diagnosis).
I did not read external captures, full answers, reasoning or private logs. Runtime
root names below identify controller evidence only, not locations I accessed.

### Original ten calls — preserved, not rescored

| Phase | Verified calls | Strict complete | Recorded matches | Invalid answers |
| --- | --- | --- | --- | --- |
| Baseline | 5 | 2 | Slot 4: 9/18; slot 5: 8/18 | Three fenced JSON outputs |
| Guidance | 5 | 1 | Slot 1: 9/18 | Three fenced JSON outputs; one malformed JSON output |

All were fresh exported actual `opencode-go/glm-5.3-flash`, reported variant null,
no tools. Original active CLI time: `593.4621967620624/2100` seconds. All ten slots
were consumed without retries. Original root: `/tmp/space/opencode-expert-routing`.
All 73 original files and data remained unchanged through the new tranche;
controller's before/after combined inventory SHA-256:
`2e04675a4ed0fdabbe5a227c2a073f8f244f4cb235c01f7e9f05910110cedb3e`.

Baseline already substantively honored dual-model architecture input because the
evaluation instruction required it; no causal improvement claim is justified.
Guidance worker pending-branch handling differed observationally, not causally.
Enum definitions confounded original route counts; owner/bypass mismatches and
all original invalid outcomes remain visible. Guidance slot 4's incorrect
manual-refresh-before-edit wording is retained as a caveat in the documentation.

### Separately authorized five-call clarified protocol

Controller root: `/tmp/space/opencode-expert-routing-clarified`.
Reviewed helper: `4fdef0db`. Frozen before calls:

| Fingerprint | SHA-256 |
| --- | --- |
| Clarified packet | `43103ced0249f56870617dfcc6caebf10b0388f5a036985257f5780c9c9ebf4d` |
| Source context | `2fab7a694c04e5590b24eff15bc8306b08160878dbee02d8df794ce247158584` |
| Matrix (equal to original) | `42d4f3da540ef5628e43db16e14273c2e49222e0a7a8d6e8c8adc31c77fef77c` |
| Schema (equal to original) | `cb771ebb37ab5508472e79e5e012ce17e7e76d7b2405fd11ad8162dc70a5e95a` |
| Oracle (equal to original) | `b3ae40c42013f3d128cf2fd4aa2fe318b556bac7934eca7bee30341b35412ad5` |

| Call | Controller own-session ID | Outcome | CLI seconds | Recorded matches |
| --- | --- | --- | --- | --- |
| Clarified 1 | `ses_e8a50e0b2ffePzjKMQBlG3FJmV` | complete | 69.008 | 18/18 |
| Clarified 2 | `ses_e8a4fd4a1ffeg08U1O1gJVbwTD` | invalid_answer | 44.668 | Not scored |
| Clarified 3 | `ses_e8a4f2599ffeaU55mP1rJWbTNa` | complete | 68.473 | 18/18 |
| Clarified 4 | `ses_e8a4e1a56ffe81LIQjhbvYqbB7` | complete | 75.385 | 18/18 |
| Clarified 5 | `ses_e8a4cf379ffe36IjtFrIRVoPXB` | complete | 81.965 | 18/18 |

All five were actual GLM `opencode-go/glm-5.3-flash`, reported variant null, no
tools; all five texts were syntactically valid JSON. Exact aggregate active CLI
time: `339.499002335011/900` seconds (table durations rounded). Five authorized
slots consumed; no retries. No extra GPT candidate evaluation trials were run;
design consultation and diagnostic/review gates are not evaluation trials.

Predeclared acceptance was five verified strict complete outputs covering all
18 cases, 90/90 route-plus-owner matches **and** manual rationale review. Actual:
**4/5 strict accepted outputs, 72 recorded matches of 90 required; gate failed.**
Four accepted JSON outputs do not by themselves establish manual acceptance.

Clarified 2's original parser reproduction raised
`ValueError: unknown/duplicate routing decision`. Its 18 rows contain exactly
one wrong key tuple, for `wrap-up-review`:

- Expected: `workflow=fast-dev, actor=fast-dev-reviewer`.
- Returned: `workflow=fast-dev-reviewer, actor=fast-dev-reviewer`.
- Correct route/owner in that row: `glm` / `fast-dev`.

Controller-supplied exact rationale:

> The authorized observational whole-branch review records its finding, base/head SHAs and validation normally, since a wrap-up typo under an unchanged reconciled design is ordinary GLM work. The fast-dev identity fixes directly, self-reviews, and revalidates with no second mandatory GPT review, no identity switch and no supervisor worker pipeline.

The parser correctly rejects a genuine identifier-copy/coverage error; it is not
a code-fence, JSON syntax, transport/auth, alias or demonstrated broad architecture
consultation omission. No answer repair, alias acceptance, invalid-row scoring,
oracle change or old-run rescoring was performed or proposed as acceptance.

Controller manually read all 90 final rationales, not reasoning. They generally
express mandatory dual-model design-before-implementation, proposal/critique/
evidenced reconciliation, reuse/material reopening, read-only expert boundaries,
worker pending-consultation handling, human policy ownership, no approval bypass
and direct fast/live ownership. Dedicated live-manual scenarios were correct.
This is not universal conformance; preserve both concerns:

- Clarified 2 `first-syntax`: “Independent reviewer gates and pressure-based
  skipping play no role.” Ambiguous wording potentially undermines strict review;
  it is not automatically benign.
- Clarified 5 `fresh-local-design` under fast-dev: “manual mode still precedes any
  edit.” Unnecessary live-specific constraint despite correct direct owner.

The diagnostic advisor returned `requires_human`: residual failure is model
identifier copying, not a harness defect; no production/parser/oracle fix is
justified. Strengthening workflow-identifier instructions is a future hypothesis,
not a validated fix. Additional human call-budget authorization or an explicit
validation-acceptance policy decision is required. Unused time is not authority
for a sixth call. This task grants neither an acceptance waiver nor expanded GPT
roles. No completion/publication/integration while this gate remains unresolved.

## Validation

`validation-mode: disk-only`.

Compile-check evidence: not applicable (documentation only; no Fennel/native
changes or execution). Constraint status: not applicable; no constraint or policy
edits. **Constraint Impact: not applicable.** TDD: not required for this factual
documentation-only assignment; no behavioral implementation or test changes.

Focused checks and self-review cover documentation accuracy and scope only;
they cannot turn the behavioral
failure green. Prior controller-reported passes (324 focused pytest, 736 policy,
35 Node; clarified helper 41 focused / 125 combined offline) were **not rerun**
and are not new test evidence from this task. Source-level checks and static
review remain valid as configuration evidence only, not runtime activation or
production-delegation proof.

- `git diff --check` and `git diff --staged --check`: exit 0, no whitespace errors
  in the guide or complete staged diff including the report addition.
- Focused repository text searches compared all five exact clarified session IDs,
  durations, both aggregate times, packet/source/matrix/schema fingerprints and
  inventory hash with `progress.md` and supplied DATA. The oracle fingerprint was
  compared with supplied DATA. These are text consistency checks, not independent
  rehashing of external artifacts.
- `rg --count` with the five exact clarified session-ID alternatives against
  `progress.md` and `task-4-report.md`: five matching call-table lines in each file.
- Read/diff review verified original 2/5 and 1/5 complete counts, clarified 4/5 and
  four times 18 = 72 recorded matches, failed 5/5 + 90/90 gate, both manual-review
  concerns and stale pending-text removal. No old invalid answer was scored.

## Design decisions, self-review and handoff

No design/refactor decision: mechanically document supplied outcomes under the
approved contract. Keep original and separate protocol counts distinct, preserve
all failures and wording concerns, and leave policy/model/authority boundaries
unchanged. The existing workflow guide is large; edits are isolated to its
pressure-evidence subsection rather than restructuring it.

Self-review found no factual discrepancy against the supplied evidence. The
report directory is ignored by `.gitignore`; only this explicitly assigned new
report is force-added, with no ignore-policy edit or other coordination artifacts
included. Full staged diff review covers the addition as well as the guide.

Independent review must inspect the complete `BASE..HEAD` diff for both assigned
files, including this addition, rather than only the guide. This local docs
checkpoint is not approval or a ready-to-merge claim. Resolve the report-bearing
checkpoint SHA with `git log -1 --format='%h %s' -- .superpowers/sdd/2026-10-25-glm-default-expert-consultation-44988498/task-4-report.md`;
the exact SHA is also supplied in the handoff message.
