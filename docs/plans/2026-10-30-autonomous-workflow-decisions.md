# Autonomous Workflow Decisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve routine workflow decisions autonomously and complete the pending
daily devlog with reviewed corrections to October 28 and a new October 29 entry.

**Architecture:** AGENTS.md owns the shared decision contract; primary references
and daily automation guidance consume it. Existing generators and stage-only review
handle journal corrections; no new runtime evaluator or publication format.

**Tech Stack:** Markdown, Node node:test, Python/pytest source-contract checks,
VitePress, existing journal and development-record index generators.

**Design:** [Committed specification](../specs/2026-10-30-autonomous-workflow-decisions-design.md),
checkpoint `c62af53b`; branch `automation/daily-devlog/2026-10-30`; initial main
`15b8fe8a3779d197845a75128f359585e1033ac3`.

## Global Constraints

- Use evidence-backed autonomous decisions within existing task scope and authority.
- Do not change models, permission frontmatter, capability wrappers, engine code,
  external/home configuration, historical experiment records, or unrelated dates.
- Keep review lanes, consultation triggers, publication authorization, clean-tree,
  current-main, protected test, and merge queue gates unchanged.
- Every implementation/fix: **stage only assigned changes; return them uncommitted;
  do not commit, amend, push, or integrate**. Controller commits only after independent
  pass of complete assigned staged content, including additions/generated changes.
- Preserve accurate journal narrative, useful links, dates/frontmatter, attribution,
  and the single short paragraph; no filler or speculative claims.
- Genuine credentials/access, permission refusals, unauthorized destructive action,
  explicit checkpoints, and unknown product/API/data policy remain boundaries.
- Restart OpenCode after rollout; running roles do not hot-load revised guidance.

## Investigation and planning handoff

The spec contains seven-landing discovery accounting and five unchanged-source
controls; do not rerun them during initial implementation. Diagnostic advisor
`ses_e7433a0e4ffewgkZFNwvETq46g` confirmed the instructional cause and requested
the already-selected planned multi-file route (`too_broad_needs_plan`). No material
technical conflict or expert trigger is outstanding.

Planner `ses_e7432c4c0ffePhfaf6ZG6eQFKe` supplied a detailed Markdown plan and
self-review but expressly could not write/commit under its loaded read-only
contract. The controller authors this bounded executable version under its
coordination allowlist; this is not a claim that the planner persisted a file.

### Task 1: Shared autonomy and daily editorial workflow

**Assigned files:**
- `AGENTS.md`
- `.opencode/agents/supervisor.md`
- `.opencode/agents/fast-dev.md`
- `.opencode/agents/live-dev.md`
- `.opencode/skills/daily-devlog-automation/SKILL.md`
- `docs/dev/features/opencode-agent-workflow.md`
- `docs/dev/notes/daily-devlog-automation.md`
- `docs/scripts/test-opencode-automation-config.mjs`

**Interface:** Produce `AGENTS.md#autonomous-workflow-decisions`; all three primaries
and human-facing workflow docs reference it. Existing `loadFiles()` and
`sectionText(content, heading)` test helpers remain owners of source-contract tests.

- [ ] Write focused regression tests first, extending the existing Node test file.
  Load live-dev beside fast-dev and assert all three canonical references. Replace
  the obsolete byte-preservation/escalation test with autonomous correction and
  preservation-of-accurate-content assertions. Add shared-boundary tests and
  aligned note/trigger assertions. Retain all existing semantic coverage, date,
  no-op, freshness, staged-review, permission and merge-queue guards.

  Representative new source-contract assertion:
  ```js
  test('primary guidance references autonomous workflow decisions', async () => {
      await loadFiles()
      for (const content of [supervisorContent, fastDevContent, liveDevContent]) {
          assert.ok(content.includes('AGENTS.md#autonomous-workflow-decisions'))
      }
      const rule = sectionText(agentsContent, '## Autonomous workflow decisions')
      assert.match(rule, /evidence/i)
      assert.match(rule, /routine.*(?:choices|decisions)/i)
      assert.match(rule, /capability refusals/i)
      assert.match(rule, /unknown product\/API\/data policy/i)
  })
  ```
- [ ] Observe RED before editing guidance:
  ```bash
  node --test scripts/test-opencode-automation-config.mjs
  ```
  Run from docs. Capture expected missing-contract and obsolete-rule failures,
  not syntax/import errors; failure is intentional TDD, not a validation bypass.
- [ ] Add one canonical positive action recipe: establish scope/evidence; choose
  proportionate reversible contract-consistent action; use the applicable lane;
  record rationale and continue. Routine technical/editorial/recovery choices need
  no human approval. Controller triages worker context/blocker reports, gathers
  evidence and required advice, and resumes workers; such reports are not
  automatically human questions. Continue separable permitted work.
- [ ] Add concise primary references; replace supervisor's unconditional forwarding
  of BLOCKED/adjudicator reports with controller triage. Align active repeated
  recovery wording so an ordinary architecture choice is not itself human-owned.
  Do not change frontmatter, live manual-mode/refresh, or fast/live local-only
  checkpoint and explicit-wrap-up rules. Explain actual resource/evidence exhaustion
  as truthful incomplete status, distinct from requesting routine retry approval.
- [ ] Align daily Workflow step 6, decision table, whole-window accounting, developer
  note, and canonical prompt: correct an existing entry on its actual landing date
  autonomously through unchanged stage-only review/validation. Preserve accurate
  narrative, useful links, dates/frontmatter and attribution. An explicitly imposed
  immutable-publication restriction is a real conflict, not source presence alone.
  Do not introduce addendum infrastructure or a different journal shape.
- [ ] GREEN: rerun focused Node test, then `npm run test:scripts` from docs.
  From root run:
  ```bash
  python3 scripts/check_opencode_permissions.py --repo-root .
  python3 -m pytest -q scripts/tests/test_check_opencode_permissions.py scripts/tests/test_opencode_handoff_delivery_contract.py scripts/tests/test_opencode_handoff_recovery_contract.py scripts/tests/test_opencode_windows_ci_policy_docs.py
  git diff --check
  ```
- [ ] Stage only the eight files; self-review and return report with RED/GREEN,
  complete assigned staged list, no omitted unstaged/untracked work, and no commit.
- [ ] Controller runs five fresh guided probes, one for each retained control:
  full revised AGENTS/daily skill and same overnight/unavailable-user, ten-minute,
  sunk-hour pressures; omitted existing date, independent missing day, ordinary
  reversible decision, refused credentials, unauthorized destructive-retention
  policy. Manually read every answer and retain counterexamples. Source guards and
  probes are not runtime enforcement or statistical reliability guarantees.
- [ ] Independent full pending-diff review; fixes keep stage-only mode and refresh
  whole staged review. After pass, controller commits exact approved content.

### Task 2: Journal correction, catch-up entry, and generated indexes

**Assigned files:** `docs/dev/journal/2026-10-28.md`, new
`docs/dev/journal/2026-10-29.md`, `docs/dev/journal/index.md`, `docs/dev/devlog.md`,
`docs/plans/index.md`, `docs/specs/index.md`.

**Interface:** Consume approved Task 1 editorial rule and the spec's complete
inclusive `2026-10-28T00:00:00Z` through `15b8fe8a` landing accounting. Produce
canonical dated sources plus generator-owned navigation. No October 30 source.

- [ ] Read current October 28 narrative and SELinux/virtual-input feature references.
  Preserve its topology, branch wiring and development-records story. Integrate
  bounded read-only native SELinux-aware publication (no relabeling/certification)
  and full-text external editing with stale-completion refusal into the same paragraph.
- [ ] Add October 29 with canonical frontmatter, date heading and one dense paragraph:
  agent recovery retains evidence/review; model-neutral routing uses targeted advice;
  enumerated message/part edges and real JSON improve inspection; SFTP success follows
  checked local I/O, remote close and session teardown. Reference existing feature
  pages. Do not imply runtime-enforced policy, original-wire lossless JSON,
  arbitrary SSH concurrency safety, durability, or current-session hot loading.
- [ ] Compression/semantic pass: all meaningful themes fit one brief narrative per
  date, useful inline links only; no lists, extra headings, raw files, hashes or
  misdated unmerged work. Verify other dated sources remain unchanged.
- [ ] Ensure locked docs dependencies: from docs, run `npm ci` only if node_modules
  or executable `.bin/vitepress` is absent. Run:
  ```bash
  npm run test:scripts
  npm run devlog:indices && npm run docs:build
  ```
  Retained earlier project evidence records default-heap OOM and success with
  `NODE_OPTIONS=--max-old-space-size=6144`; inspect it before using that bounded
  setting. Capture any new failure and systematically diagnose it.
- [ ] Inspect all generated output, including record indexes and icon sync.
  Unexpected tracked edits require bounded diagnosis, not blanket staging. Run
  generators again and confirm identical output; verify aggregate October 28 text,
  exactly one October 29 entry, valid links and development-record navigation.
- [ ] Stage only assigned changed files, self-review and report successful checks
  and full build. Independent complete pending-diff review precedes controller commit.

## Controller finishing and acceptance

- Maintain adjacent progress ledger with stable assignment/session/source identity,
  independent verdicts, correction_used, probes, validation and meaningful recoveries.
  Keep original reports private and safe summaries tracked; no new coverage schema.
- No engine build/Fennel/runtime suite is needed for this guidance/docs-only change.
- All reviewed content committed; no unrelated state absorbed; tree clean. Fetch
  through git-integrator and evaluate current origin/main, never stale local main.
- If main tip changes, repeat catch-up discovery, safely merge when needed, route
  repairs through stage-only implementation and complete review, and restart checks.
- Run final Node/Python guidance checks and full docs build from clean current-base
  tree. Generated deltas reopen review. Re-fetch and assess freshness before push.
- Push dated automation branch through git-integrator. GitHub operator checks
  protections, creates PR, enables auto-merge and polls until mergedAt exists.
  Required PR CI is the integration gate; queue entry alone is not success.
- Do not chase normal main movement after queue entry. Diagnose actionable queue
  failures, preserve consultation/review gates, and requeue only reviewed fixes.
- Report actual journal dates, PR/merge evidence, validation and restart requirement.

## Plan self-review

Both deliverables cover all spec requirements with explicit owners, tests, pending
review and safety boundaries. Baseline/discovery facts are retained, not recreated;
no unrun test or unpublished change is claimed complete. No placeholders or new
runtime interfaces. Controller commits this coordination plan before execution.
