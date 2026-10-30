# Autonomous workflow decisions and devlog corrections

## Goal and authorized scope

The maintainer explicitly authorizes correcting existing journal entries and asks
agents to resolve routine problems without repeatedly requesting permission.
Use evidence-backed autonomous decisions within existing task scope and authority;
do not interpret this as unlimited access, destruction, publication authority for
local-only tasks, or permission to fabricate facts or bypass quality gates.

This task updates the shared workflow contract and its primary-role references,
repairs the daily automation's editorial decision rule, and completes the pending
October 30 automation run. It does not change models, permission frontmatter,
capability wrappers, engine code, or external/home configuration.

## Diagnosis and baseline evidence

The clean branch `automation/daily-devlog/2026-10-30` starts at pinned main
`15b8fe8a3779d197845a75128f359585e1033ac3`. Daily discovery found meaningful
October 28 SELinux publication work omitted from an existing journal source,
and meaningful October 29 work without a dated source. The prior controller
stopped to request publication treatment; the maintainer rejected that routine
editorial escalation and supplied the new authority above.

Root-cause hypothesis: the daily skill's explicit byte-for-byte preservation
requirement and existing-source human-decision table entry cause the stop. The
developer note, canonical scheduled prompt, and automation configuration tests
reinforce that obsolete rule. General instructions already permit ordinary design
judgment but do not clearly distinguish a worker's context request from a
human-owned decision across routine operational problems.

Original source evidence at the pinned snapshot:

- `.opencode/skills/daily-devlog-automation/SKILL.md`: Workflow step 6;
  Catch-up Discovery and Decision table and preservation paragraph.
- `docs/dev/notes/daily-devlog-automation.md`: Prompt, Landing-date attribution,
  and Validation and recovery repeat the same preservation/escalation rule.
- `docs/scripts/test-opencode-automation-config.mjs`: the existing-source test
  explicitly requires byte-for-byte preservation and human publication treatment.
- `AGENTS.md`: ordinary design uses evidence-backed rationale; unknown data policy
  and capability refusals remain human-owned. The new default must preserve this.

Five fresh read-only control probes (BASELINE-1 through BASELINE-5) read the full
unchanged daily skill and AGENTS contract. Every probe faced overnight user
unavailability, ten minutes remaining, and an hour of sunk setup. All five chose
to stop existing-entry treatment and ask the human, quoting "Preserve the source
and request a human publication-treatment decision". All five allowed independent
missing-day work and evidence-backed reversible choices, and retained credential
and destructive retention-policy boundaries. These are policy application probes,
not runtime enforcement or statistical reliability claims. Their immutable original
deliveries remain in the controller session; safe outcomes are recorded here.

## Alternatives and selected direction

1. **Correct the existing date through normal review (selected).** Keep accurate
   existing context, add the evidenced omission, retain date/frontmatter and one
   short paragraph, regenerate indexes. Git history preserves the prior version.
   This fixes the source of truth without inventing a second journal shape.
2. **Always create addenda.** Preserves bytes but adds navigation/format complexity
   and duplicate daily narratives without demonstrated need. Not the default.
3. **Keep asking or defer the omission.** Leaves routine unattended runs unresolved
   despite sufficient evidence and authorization. Rejected by the maintainer.

No clarifying question is necessary: the maintainer permits either correction or
addendum and delegates that editorial judgment. A diagnostic advisor independently
checks the root cause and bounded proposal before implementation.

## Shared autonomous-decision contract

Add one canonical section in AGENTS.md and concise references in supervisor,
fast-dev, and live-dev guidance plus the human-facing agent workflow page.

The action recipe is: establish scope and evidence; choose a proportionate,
reversible approach consistent with existing contracts; implement/diagnose/review
through the applicable lane; record rationale and continue. Routine technical,
editorial, recovery, and implementation choices do not need human approval.
Controller-owned evidence gathering and consultation resolve worker context
requests where possible; a non-approving worker report is not automatically a
human question. Continue separable permitted work when a real boundary blocks
one dependent operation.

Escalation states the exact unavailable authority, evidence, or external prerequisite
after permitted investigation. Explicit checkpoints, actual capability refusals,
missing credentials/access, destructive or irreversible action without authority,
and genuinely unknown product/API/data policy remain boundaries. Actual resource
or evidence exhaustion warrants truthful incomplete status, not invented success
or a request for routine retry approval. Independent review, consultation triggers,
publication authorization, clean-tree checks, current-main evaluation, and merge
queue requirements remain unchanged. Do not promise to solve literally every
possible problem or remove those safeguards.

## Daily editorial contract

Missing sources receive brief entries for their actual UTC landing dates.
Meaningful uncovered work on an existing source is corrected autonomously on that
date through the same stage-only implementation, complete pending-diff review,
validation, and commit flow. Preserve accurate existing narrative, useful links,
date/frontmatter, and attribution; do not delete unrelated history, rewrite other
dates gratuitously, misdate work, create filler, or introduce a second paragraph.
Whole-window coverage remains mandatory, including corrected and created dates.
An explicit task-specific immutable-publication constraint would be a genuine
conflict to resolve, not implied by source presence alone.

Update the owning skill, its developer note and trigger, and focused regression
assertions together. Retain boundary/uncertainty, semantic coverage, freshness,
protection, stage-only review and merge-queue tests. General "architecture choice"
wording must not turn ordinary evidenced technical judgment into a human gate.

## Pending journal work and complete discovery window

Inclusive boundary: `2026-10-28T00:00:00Z`, through pinned main above. First-parent
landing timestamps, not author dates or record filenames, establish attribution:

| Landing | UTC date/time | Decision |
| --- | --- | --- |
| `9e919028` / PR285 | Oct 28 04:23:27 | October 27 journal publication only; covered |
| `6dfada36` / PR286 | Oct 28 17:47:06 | Session topology/branch wiring covered; bounded native SELinux publication and full-text external-editor interaction omitted |
| `a4b05700` / PR287 | Oct 28 22:24:44 | Development records/navigation covered |
| `4f607d36` / PR288 | Oct 29 04:14:23 | October 28 journal publication only; covered |
| `e34e4c05` / PR289 | Oct 29 11:23:14 | Autonomous handoff recovery; meaningful uncovered |
| `5cc254b0` / PR290 | Oct 29 17:02:48 | Model-neutral routing/targeted advice and SFTP finalization; meaningful uncovered |
| `15b8fe8a` / PR291 | Oct 29 18:23:30 | Enumerated message/part edges and actual JSON; meaningful uncovered |

Correct `docs/dev/journal/2026-10-28.md` without losing its current topology and
record-preservation story. Add `docs/dev/journal/2026-10-29.md` with one dense
narrative connecting agent resilience/inspection and truthful transfer completion.
There are no October 30 landings at the pinned snapshot: do not narrate this
unmerged workflow change as already landed or create an October 30 filler entry.
Relevant references are the existing SELinux, virtual-input, agent-workflow and SSH
feature pages. Avoid claims of general SELinux certification, arbitrary SSH
concurrency safety, lossless original JSON bytes, runtime-enforced recovery, or
activation of updated roles in running sessions.

## Validation and acceptance

- Add/update focused contract tests first and observe expected RED for the old
  escalation rule and missing autonomy contract, then GREEN after guidance changes.
- Run `node --test scripts/test-opencode-automation-config.mjs` and `npm run
  test:scripts` from docs; run the OpenCode permission checker and relevant Python
  policy/handoff tests for touched primary guidance. No engine/runtime changes are
  intended, so no engine rebuild or full engine suite is required solely for this.
- Five fresh guided probes read full revised sources with the same control
  scenarios. Manually inspect every result: correct existing entries without
  editorial permission, proceed on routine choices, retain credential and
  unauthorized-destructive-policy stops. Residual defects follow ordinary diagnosis,
  consultation triggers and independent review, not score selection.
- Ensure locked docs dependencies; run `npm run devlog:indices && npm run
  docs:build`. Use an evidence-backed Node heap setting if the known docs size
  needs it; do not hide failed validation. Review every generated change.
- Every implementation/fix is stage-only, uncommitted, and independently reviewed
  in its complete assigned pending diff before the controller commits exact
  approved content. Preserve design/plan/progress history. Finalize from a clean
  current-main tree, repeat discovery if fetched main changes, push only the
  automation branch, create/auto-merge through wrappers and poll to actual merge.
- Restart OpenCode after the reviewed rollout; repository changes do not hot-load
  the currently running roles. No home configuration edit/deployment is authorized
  by this task.
