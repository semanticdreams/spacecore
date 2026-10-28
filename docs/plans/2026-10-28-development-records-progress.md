# Development-record preservation progress

## Scope and source

The user requested preserving design specs, implementation plans and progress
ledgers in the repository, then challenged whether adding instructions alone
fixed why records were ignored. This follow-up addresses the concrete storage
and workflow mismatch, not a new requirement to write plans for every small task.

- Controller/workflow: `live-dev`; branch: `live-dev`.
- Source HEAD: `ebbc538f5189bc8fc9bf8130c6acfe4ab0b6a5e5`.
- Existing policy checkpoint: `ebbc538f` (not yet published).
- Investigation task: `preserve-development-records-root-cause`.
- Original author: project `explorer`, session `ses_e7c4422d2ffe6Z9a3JM198oHwq`.
- Review mode: read-only investigation; source HEAD as above.
- Delivery: valid raw JSON, matching task/role/branch/source/mode;
  `correction_used=0`, separate from assignment identity. Eligible evidence,
  not an approval. Original payload is retained unchanged in the tool transcript.

## Verified root cause

- `git check-ignore -v .superpowers/sdd/review30-progress.md` identifies the
  root `.gitignore` rule `.superpowers/`.
- `sdd-workspace` also writes an ignore-all `.superpowers/sdd/.gitignore`.
- The helper and SDD setup group the progress ledger with private scratch
  artifacts, while the supervisor allowlist and finishing skill explicitly name
  that ignored ledger as committable. Removing one ignore rule would not fix
  both mechanisms and could expose private reports and raw handoff evidence.
- `docs/specs/` and `docs/plans/` are not ignored. The existing session-graph
  design spec is tracked; the review30 progress ledger is not.
- No active ledger-deletion mechanism was established. The demonstrated defect
  is ignored-only storage and contradictory commit guidance, not proven deletion.

## Decision and implementation status

Keep private scratch artifacts ignored, and give durable progress a tracked home
beside its plan. A bounded GLM proposal and original-source GPT critique are
pending before changing the workspace helper's interface or workflow ownership.
Existing private originals must not be overwritten or automatically published.

GLM proposal received from the same explorer session for new bounded scope
`preserve-development-records-ledger-interface`, mode `bounded design proposal`,
same source HEAD/branch/controller; valid raw JSON with required proposal and
canonical consultation request, `correction_used=0`. Original payload remains
unchanged in the transcript. Proposal: keep existing scratch stdout unchanged;
add read-only `sdd-workspace --progress PLAN_FILE` resolving a non-ignored
`<plan-stem>-progress.md` alongside a canonical `docs/plans/` plan; the controller
owns ledger writes/checkpoints. Update existing allowlist, SDD setup/resume and
finishing instructions. Preserve legacy private ledgers and explicitly publish
only safe summaries. GPT critique is pending.

Controller corrections to the proposal before consultation: implementers still
write their assigned private reports; this does not grant any worker ledger
ownership. Safe stable identity/correction bookkeeping may be tracked (not
excluded categorically by AGENTS.md). No automatic pointer insertion or other
mutation of existing private originals is authorized.

GPT critique: expert `ses_e7c1fd27fffehj3ng43h9dUATc` answered the bounded
storage/interface question after inspecting original sources. Reconciliation
before implementation: accept the split, with all concrete corrections:

- Resolver success means a validated candidate path, not a tracked/checkpointed
  file. Confirm actual checkpoint inclusion separately.
- Use `git check-ignore --no-index`, including already-tracked destinations;
  distinguish exit 1 (not ignored) from exit 0 (ignored) and actual Git errors.
- Branch before scratch initialization; successful and failed public resolution
  must create/copy/write nothing. Canonical containment covers plan, parent chain
  and destination; reject dangling/escaping symlinks and non-file collisions.
- A filename does not establish ownership. Before appending, the controller
  verifies the ledger's plan/task identity and range; stop on ambiguity.
- Resume reconciles public and private retained progress, including later work
  and spent correction allowances. Do not blindly prefer stale public state,
  overwrite legacy originals, reset bookkeeping, or manufacture missing verdicts.
- Publish only a privacy-reviewed summary with provenance, then checkpoint it;
  leave raw originals private and unchanged. Apply the same rule to planless
  fast/live records without requiring plans for small tasks.

These are accepted requirements, not task approval. Regression checks will cover
read-only resolution, ignore rules, path escapes, existing destinations, default
consumer compatibility and the actual ownership/resume/finishing guidance.

## Validation so far

Fresh fetch: branch is zero commits behind `origin/main`. The live app was
verified ready/non-faulted and manual mode reestablished before local edits.
Only repository tooling/documentation is in scope; no app-code refresh is needed
for these records themselves.

## Implementation and regression evidence

- Added read-only `sdd-workspace --progress PLAN_FILE` resolution. Existing
  positional scratch output remains compatible with `task-brief`/`review-package`.
  Git-ignore checking includes tracked files; path escapes, symlink destinations,
  non-file collisions and Git errors refuse rather than silently routing progress
  to ignored/private storage. No public record is created or migrated by the tool.
- Changed the SDD setup/resume/completion route, supervisor coordination allowlist,
  strict finishing gate and fast/live wrap-up guidance to use tracked durable
  records. The old private-workspace mismatch diagnostic no longer suggests
  removing a workspace with retained records.
- Kept both private ignore mechanisms intentionally; clarified root `.gitignore`
  rationale rather than exposing scratch. No spec/plan ignore rule was found.
- Added a privacy-reviewed historical summary at
  `2026-10-28-opencode-session-graph-review-progress.md`, with source provenance,
  decisions, checkpoint/review identities, failures/recoveries and integration.
  The original private ledger SHA256 remains
  `269df3110ddc71e67b5944e03cab51391010d1262092e604388efc483af7f788`.
- Initial regression run before implementation: seven failures/nine passes,
  including absence of `--progress` and routing guidance. Initial GREEN:
  291 tests passed (16 workspace + 275 existing contract tests). Expanded workspace
  coverage now has 20 tests, wired into `make opencode-check`.
- Broad tooling gate initially failed: 17 failed/1164 passed under uv's managed
  Python 3.12.13. Inspection established that this interpreter lacks
  `os.pidfd_open`/`signal.pidfd_send_signal`, unlike system Python 3.14.6; two
  helper timeout assertions failed there as well. No repository fix or weakened
  assertions were applied. Explicit system-interpreter rerun of lifecycle,
  failing timeout cases and all workspace tests: 137 passed.
- Full system-Python gate: 1180 passed, one failure in the unchanged
  `test_real_parent_sigterm_has_terminal_backstop_and_does_not_leak_locks`:
  its five-second readiness deadline expired before the fixture emitted
  `helper-ready`. Retained stage evidence shows all preceding setup stages passed
  and consumed about 4.52 seconds before the fast-helper startup; that stage was
  only `started`, with empty output, at failure. The isolated unchanged test then
  passed. This establishes a setup-budget/timing failure at a different test,
  not evidence of a ledger regression or a reason to relax assertions. A final
  full rerun was requested; neither earlier nonzero result is called success.

## Guidance application check

Project explorer `ses_e7c4422d2ffe6Z9a3JM198oHwq` completed new read-only scenario
`preserve-development-records-resume-scenario` at source HEAD above plus SDD skill
blob `74399a4d92973f3fc61f8d84f35fba0c5793e676`. Raw JSON delivery validated
against task/role/branch/head/blob/mode; `correction_used=0`. This is a bounded
guidance application test, not an independent review/approval.

Under finish-now pressure, a committed public ledger claimed allowance zero and
older work, while private retained evidence said allowance one and later work.
The author correctly refused finishing from clean status, another format-only
correction, deleting private originals, or overwriting an unrelated colliding
ledger. It required controller identity/evidence reconciliation, retaining spent
allowance and independently verified work, privacy-reviewed public bookkeeping,
and ordinary finishing gates. The original scenario answer remains unchanged in
the tool transcript; no expert or review verdict was manufactured from it.

## Final local validation and preservation

The final full tooling gate passed: `make opencode-check` under system Python
3.14.6 in an isolated pytest environment, **1181 passed** with zero permission
violations. Command:

```sh
UV_CACHE_DIR=/tmp/opencode/uv-cache uv run --isolated --no-project \
  --python /usr/bin/python3 --with pytest make opencode-check
```

The new 20-case regression suite is part of that gate, not a manual-only check.
`bash -n` and `git diff --check` passed. A real plan resolved to its adjacent
non-ignored ledger path without creating it. The preserved review30 original's
SHA256 still matches the value above. The safe history summary and this active
progress record are included in the local task checkpoint; raw originals and
scratch remain private. No app/runtime source changed, so no app reload/restart
is indicated for this tooling/documentation-only change.

`.opencode/**` changed: quit and restart OpenCode to load the corrected workflows.
The running session keeps its previously loaded rules. Local checkpoint only;
no push or new integration is authorized by this follow-up.
