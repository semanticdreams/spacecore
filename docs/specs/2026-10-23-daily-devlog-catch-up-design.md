# Daily devlog catch-up contract

## Goal and observed failure

Daily automation must recover meaningful uncovered development since the latest
journal, including missed prior days, without assigning that work to the run date.
This run must create the missing October 22 entry and publish the reviewed change.
The user additionally requests agent/workflow/script changes to prevent recurrence.

On October 23 the supervisor found meaningful uncovered work in PR #276, then
incorrectly declared no-op because nothing had landed on October 23. It described
October 22 recovery as requiring a separate request. A read-only adjudicator agreed
with that erroneous scope interpretation. The user explicitly rejected the result.

Read-only mainline evidence: freshly fetched `origin/main` at
`8b32ae73b2c03dcf93f98456ad749ea3a4c1f709`; its first-parent merge #276 landed
`2026-10-22T08:34:39Z`. The latest journal source is October 21 and describes
guarded daily branch preparation, not checkpoint/review ownership. Subsequent
October 21 merges are #274 (narrow SSE repair) and #275 (historical devlog
backfill); assess them under the meaningful-change and already-covered filters,
not merely by their dates. Inspect first-parent deltas, not only subjects.

## Diagnosis and evidence limitations

The existing skill already instructs inspection since the latest entry and
landing-date attribution. The failure is the supervisor's today-only scope
interpretation, enabled by the trigger's “today's” wording and the workflow's
optional “recent day boundary” with no explicit catch-up/no-op decision contract.
The index generators only index existing sources and cannot detect this omission.

Five fresh-context read-only control samples using unchanged guidance all correctly
selected an October 22 entry on an October 23 branch. Thus the failure is not
universal, and these samples do not establish that the old skill always fails.
The actual run and adjudicator decision are the observed failing baseline. New
contract tests must fail before guidance edits; fresh-context tests afterward
must check both the original scenario and pressured scope/no-op variants.

## Options and selected design

1. **Selected:** clarify the owning skill, supervisor routing and canonical note;
   extend the existing automation-config test script; recover October 22 using
   existing generators. This corrects the decision boundary without new state.
2. Add a read-only Git candidate CLI. Potentially useful later, but it cannot
   judge meaningfulness or narrative coverage and adds unnecessary surface now.
3. Add an evidence-inventory schema/coverage ledger. Rejected: more maintained
   state without proof of semantic completeness.

## Behavior contract

- Prepare the automation branch using the existing guarded
  `create-daily-devlog-branch` action. Its UTC run date is independent of journal
  filenames, frontmatter and headings. Do not change wrapper safety or permissions.
- Pin fetched `origin/main`. Read the latest dated journal's actual narrative and
  inspect all first-parent landing days from the start of that source's UTC date,
  inclusively, through the pinned tip. Do not replace the boundary with today,
  yesterday, a fixed lookback, or the journal publication commit. If no reliable
  initial boundary/evidence exists, surface the missing decision rather than guess.
- Determine UTC landing dates from mainline evidence; author dates and document
  filenames are not attribution evidence. Inspect landed deltas and references.
- Classify candidates as already covered, not meaningful, or meaningful uncovered.
  Ordinary daily scope includes recovery for every warranted missing date in the
  window, without asking permission merely because the date predates the run.
- Create one brief narrative entry per warranted missing landing date. Preserve
  all pre-existing dated journal sources byte-for-byte. Source presence is not
  proof of semantic coverage. If meaningful uncovered work belongs to an existing
  published source, preserve it and request a publication-treatment decision;
  do not claim successful no-op or misdate the work.
- No-op requires a fully examined interval and no unresolved meaningful work.
  Report the pinned tip, inclusive boundary and concise covered/skipped reasons.
  Keep evidence in normal review handoffs; introduce no persistent ledger.
- If pre-PR freshness discovers a new main tip, refresh coverage assessment.
  After queue entry, retain merge-queue freshness rules; do not chase main.
- Preserve paragraph format, compression/style pass, meaningful-change filtering,
  independent review, stage-only automation, capability boundaries and queue gates.

## Implementation surface

- `.opencode/skills/daily-devlog-automation/SKILL.md`: owning contract and example.
- `.opencode/agents/supervisor.md`: concise catch-up routing reminder only.
- `docs/dev/notes/daily-devlog-automation.md`: unambiguous trigger, date distinction,
  script responsibilities, safe repair instructions and restart caveat.
- `docs/scripts/test-opencode-automation-config.mjs`: RED/GREEN contract checks.
- `docs/dev/journal/2026-10-22.md`: checkpoint/review ownership narrative with a
  useful link to the canonical agent workflow documentation.
- `docs/dev/journal/index.md` and `docs/dev/devlog.md`: generated outputs only.

No changes to Git/GitHub capability implementation, permissions, generators,
publisher, scheduled infrastructure, global OpenCode files, engine or Fennel.
Repository changes require a fresh OpenCode session; do not claim hot reload or
global deployment. Existing project-config-disabled documentation remains.

## Acceptance and validation

1. Original October 23 scenario yields October 22 recovery, not no-op or an
   October 23 entry. Multiple missed days yield separate warranted dated sources;
   quiet/covered days yield no filler. Same-day unresolved work cannot disappear.
2. Tests fail against old wording and pass against the corrected contract, while
   existing attribution, safety, preservation and style checks stay green.
3. Fresh-context decisions cover run/landing separation, multiple gaps, existing
   published sources, UTC offset conversion, older author dates, valid no-op and
   ambiguous evidence. Record results honestly; static checks are not semantic
   coverage proof or an actual scheduler execution.
4. Verify PR #276 first-parent delta supports the paragraph, the relative/root
   documentation link resolves, entry shape is exact, and all prior dated sources
   remain byte-identical. Verify both indexes are unique, sorted and idempotent.
5. Run focused Node tests, full docs script tests, permission checks, relevant
   daily-branch wrapper tests, `make opencode-check`, docs index generation and
   VitePress build. Use locked npm dependencies. Native/Fennel tests are not relevant.
6. Every implementation/fix handoff is stage-only, uncommitted; independent review
   covers complete assigned pending diffs, additions and any generated edits.
   Only exact approved changes may then be committed. Finish from a clean branch
   evaluated against current `origin/main`; push via capability and poll protected
   PR auto-merge through `mergedAt`.

## Self-review

Scope is limited to incremental daily recovery and this missing entry, not a new
historical reconstruction. No semantic automation or deployment is claimed.
Run dates, source dates and existing-source conflict behavior are explicit.
