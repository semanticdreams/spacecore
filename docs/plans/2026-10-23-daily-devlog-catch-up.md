# Daily Devlog Catch-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover October 22 and prevent today-only no-ops when prior-day work remains uncovered.

**Architecture:** Clarify the existing daily skill, supervisor routing and canonical note; extend the existing Node contract-test script. Reuse guarded branch preparation and existing index generators. Meaningfulness and semantic coverage remain evidence-based agent judgments, not automatic title classification.

**Tech Stack:** Markdown, OpenCode instructions, Node `node:test`, Git first-parent evidence, VitePress, existing Python safety checks.

## Global Constraints

- Spec: `docs/specs/2026-10-23-daily-devlog-catch-up-design.md`.
- Every implementation/fix handoff: **stage only assigned changes; return them uncommitted; do not commit, amend, push, or integrate**.
- Preserve all pre-existing dated journal sources byte-for-byte.
- Ordinary daily scope includes recovery for every warranted missing date in the window, without asking permission merely because the date predates the run.
- No-op requires a fully examined interval and no unresolved meaningful work.
- No changes to Git/GitHub capability implementation, permissions, generators, publisher, scheduled infrastructure, global OpenCode files, engine or Fennel.
- Preserve paragraph format, compression/style pass, meaningful-change filtering, independent review, stage-only automation, capability boundaries and queue gates.
- Do not claim hot reload, global deployment, automated semantic proof or universal prevention of judgment errors.
- Actual run/adjudicator are failing behavioral baseline. Five old-guidance samples correctly selected catch-up; preserve that evidence. Contract tests must demonstrate RED before guidance edits.

---

## Task 1: Catch-up contract and regression script

**Files:**
- Modify `.opencode/skills/daily-devlog-automation/SKILL.md`.
- Modify `.opencode/agents/supervisor.md` (body routing reminder only).
- Modify `docs/dev/notes/daily-devlog-automation.md`.
- Test/modify `docs/scripts/test-opencode-automation-config.mjs`.

**Interfaces:** Consume existing `create-daily-devlog-branch` wrapper evidence (`origin_main_sha`, `utc_date`, `target_branch`); produce an explicit discovery/decision contract and tests in existing `npm run test:scripts`. No new CLI or state schema.

- [ ] Read all four owning sections and existing regression-test conventions; retain safety/style assertions.
- [ ] Add section-scoped, whitespace-tolerant contract tests before guidance edits. Example intent:

```js
test('daily devlog recovers missing landing days before no-op', () => {
  const skill = readRepoFile('.opencode/skills/daily-devlog-automation/SKILL.md');
  assert.match(skill, /catch-up/i);
  assert.match(skill, /inclusiv/i);
  assert.match(skill, /no unresolved meaningful work/i);
  assert.doesNotMatch(skill, /latest relevant journal entry or recent day boundary/);
});
```

Use the test file's existing read helper instead of adding a duplicate. Add separate checks for run/entry date separation, source preservation, missing-day recovery, updated trigger, supervisor routing, and pre-PR changed-snapshot reassessment. Do not merely assert one keyword globally.

- [ ] Run `node --test docs/scripts/test-opencode-automation-config.mjs`; record expected missing-contract assertion failures, not incidental import/syntax failures.
- [ ] Update skill discovery to pin fetched main, read latest source, and inspect every first-parent landing day from the start of that journal date in UTC inclusively through tip. Author dates, source presence, generated indexes, document filenames, today-only or fixed lookbacks are not coverage evidence.
- [ ] Add a concise decision table: missing dated source + meaningful uncovered work → create; already covered/noise → skip with reason; meaningful uncovered work on existing source → preserve and human publication-treatment decision; uncertain evidence/boundary → investigate/fail closed, not guess/no-op.
- [ ] Distinguish run branch UTC date from potentially several journal landing dates. Require whole-window accounting and no unresolved meaningful work before no-op. Repeat discovery on changed pre-PR main tip; leave queue freshness unchanged.
- [ ] Add supervisor routing reminder pointing to the owning skill. Update the canonical note trigger to request recovery since latest journal, preserve sources, validate and publish protected PRs. Explain wrapper/agent/generator/manual-opener responsibilities, existing restart caveat, and reviewed repair instead of blanket branch discard.
- [ ] Re-run focused test GREEN, then `python3 scripts/check_opencode_permissions.py --repo-root .` and `python3 -m pytest scripts/tests/test_opencode_git_integrate.py -k daily_devlog`.
- [ ] Submit the complete four-file staged diff with RED/GREEN evidence, unchanged permission-frontmatter confirmation, and no unstaged/untracked assigned changes. Supervisor dispatches independent reviewer before commit. Fixes repeat stage-only restriction and refresh complete staged review.

## Task 2: October 22 source and generated outputs

**Files:**
- Create `docs/dev/journal/2026-10-22.md`.
- Regenerate `docs/dev/journal/index.md` and `docs/dev/devlog.md`.
- Read-only references: latest source, `docs/dev/features/opencode-agent-workflow.md`, October 22 checkpoint design, first-parent deltas.

**Interfaces:** Consume Task 1 contract, baseline source blobs and fetched snapshot. Produce one dated source plus two derived outputs and preservation/idempotence evidence.

- [ ] Confirm fresh main snapshot and full inclusive October 21–tip window. Verify merge #276 `8b32ae73b2c03dcf93f98456ad749ea3a4c1f709` at `2026-10-22T08:34:39Z` from first-parent evidence and inspect delta. Assess October 21 #274 SSE repair and #275 historical backfill against filters, not date alone. Surface any material uncovered existing-day work instead of silently ignoring it.
- [ ] Record all pre-existing dated journal source blobs. Verify the October 22 path is absent; do not overwrite it if unexpectedly present.
- [ ] Create exact journal schema, date `2026-10-22`, one compressed narrative paragraph. Bounded draft:

```md
---
type: journal
tags: [journal, devlog]
created: 2026-10-22
---

# 2026-10-22

Strict agent work now separates [local checkpoints from independent approval](/dev/features/opencode-agent-workflow#strict-flow-checkpoint-and-review-ownership): implementers can checkpoint validated tasks and fixes, while complete change ranges still require review before completion or publication. Daily and weekly automation retain their stage-only, review-first handoffs, keeping unattended publication safeguards intact as ordinary iteration becomes more direct.
```

- [ ] Verify every claim in landed delta and the link anchor. No public commit hashes, raw file lists, extra sections or bullet summaries. Do not create an October 23 filler entry.
- [ ] Install locked dependencies only if missing: run `npm ci` in `docs` after verifying directory. Then run `npm run devlog:indices` in `docs` twice and verify byte-identical outputs on second run.
- [ ] Compare all pre-existing source bytes with baseline; confirm only October 22 was added, both generated outputs include it once in descending order, and `git diff --check` passes.
- [ ] Run `npm run test:scripts` and `NODE_OPTIONS=--max-old-space-size=4096 npm run docs:build` in `docs`, plus `make opencode-check` at root. Native/Fennel validation is not applicable.
- [ ] Submit all three assigned files staged/uncommitted with landing evidence, preservation results, generator idempotence and successful validation. Reviewer examines the complete pending diff before supervisor commits.

## Behavioral validation and finishing

Use fresh read-only contexts reading revised repository skill/note directly, not assumptions about hot reload. For the original scenario run five independent samples matching the five old-guidance controls; also run five samples with narrow-scope/time pressure. Each must choose recovery without asking permission solely because it is a prior day. Record all decisions, including contrary evidence.

Fixed scenarios and expected decisions:

| Scenario | Expected |
| --- | --- |
| Oct23 run, latest Oct21, uncovered Oct22 meaningful merge, no Oct23 | Create Oct22 on Oct23 run branch |
| Several missed meaningful days with a quiet day between | Separate correct-date entries, no quiet-day filler |
| Existing source, later meaningful same-day uncovered merge | Preserve source, explicit publication-treatment decision; not no-op |
| All candidates already covered or noise | Evidence-backed no-op after full window |
| Old author date and merge offset crossing UTC midnight | Normalize mainline landing to UTC, not author/local date |
| Missing/ambiguous mainline evidence or initial boundary | Investigate, then fail closed if unresolved; never guess |

Independent review includes these decisions and full assigned staged changes including additions. Refresh staged package after every fix; cap two fix rounds before adjudication. Commit only exact approved changes with no unrelated staged entries or subsequent edits.

After commit invoke finishing flow: clean tree, fetch and compare current `origin/main`, safe merge if needed, refreshed discovery on new snapshot, rerun `npm run test:scripts`, `make opencode-check`, `npm run devlog:indices` and docs build. Generated edits restart stage/review/commit/current-base gates. Validation failures require systematic debugging, not bypasses. Fetch/recheck again before guarded push/PR; enable safe auto-merge and poll queue until `mergedAt`. Never chase main solely for post-queue advancement.

## Plan self-review

All spec requirements map to Task 1, Task 2 or the explicit finishing/scenario gates. No new interfaces or placeholders; tests use the repository's existing helpers. Stage-only overrides ordinary checkpoints throughout. Production change range stays the seven listed files, plus supervisor-owned spec/plan and progress ledger.
