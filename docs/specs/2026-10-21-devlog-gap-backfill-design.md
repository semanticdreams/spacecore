# August–October 2026 Devlog Gap Backfill

## Intent and approved direction

Restore the public development narrative interrupted after August 7, using actual first-parent landing history on `origin/main`. Add 41 historical entries: ten August, sixteen September and fifteen October dates. Preserve every existing published journal entry byte-for-byte, including August 7 and October 21. The cutoff for this retrospective is October 20; subsequent work belongs to forward automation.

The user explicitly approved normal Discord/Matrix announcements: **no special publishing logic**. This is a content-only pass. Do not modify publisher code, workflows, frontmatter schema, state, settings, scripts, tests or automation configuration. Normal publishing and per-channel deduplication remain unchanged, including eligibility of unsent historical IDs after site deployment.

## Approach and boundaries

Daily landed-day narratives retain more useful chronology than a single catch-up post, and verified merge evidence supports that precision. Monthly summaries would compress distinct milestones; a post for every missing calendar date would invent progress. Use the researched meaningful dates below, excluding quiet days and standalone maintenance churn.

Original research baseline: e2a6c1ed5dec847dcffe74053ab96a2fbb2a7b84. Fresh implementation baseline: 435950c7c78d1288bfb0a3cbebaf20fc1f1489c8. The intervening October 21 SSE change is outside the historical cutoff and must not be inserted into earlier entries. Derive dates from first-parent merge committer timestamps in UTC, not feature-branch author dates or spec filenames. Inspect landed deltas/source/docs to verify claims; a plan alone is not implementation proof.

Create entries under `docs/dev/journal/YYYY-MM-DD.md`; regenerate only the existing journal index and aggregate devlog. Use exactly:

```markdown
---
type: journal
tags: [journal, devlog]
created: YYYY-MM-DD
---

# YYYY-MM-DD

One short narrative paragraph.
```

Each paragraph connects concrete landed changes to what they enable and project momentum, normally two or three compressed sentences. Add one or two useful existing documentation links where they improve context. No bullet lists, extra headings, commit hashes, author lists, separate reference lists, raw file lists or commit-summary prose. Avoid repetitive milestone boilerplate and unsupported claims of deployment, performance, portability or historical test success. Canonical docs may contain later additions; the historical merge bounds the claim.

## Evidence-backed entry manifest

The following merge anchors and PR ranges establish the content source; they belong in review evidence, not public paragraphs. Reviewers must check every target date and paragraph against landed content. Link targets are suggestions, not an obligation to reproduce future claims on their current pages.

### August: 10 entries

| Date | Representative merge / PRs | Narrative and useful context |
|---|---|---|
| 2026-08-08 | dd1141b6 / #79–83 | Canvas dragging/theme restoration plus bounded permissions, transient PR handling and repository trust; graph maps and agent workflow. |
| 2026-08-09 | c9538e29 / #84–85 | Persisted per-map cameras, centering, contained panels/sidebar and explicit JSON failures; graph maps. |
| 2026-08-10 | 4d324b81 / #86–87 | Coherent light-theme tonal hierarchy and dialog titlebars; light-theme-layering note. |
| 2026-08-12 | 5290f062 / #88–89 | Stale-reference restoration and observable live-development/session recovery; agent workflow and reloadable units. |
| 2026-08-14 | 9c9592f8 / #90–92 | Activity-owned presentation/cameras, world/activity/surface hierarchy and durable graph-authored workflows; activities and workflows. |
| 2026-08-15 | 56e21c9f / #93–97 | Accessible workflow authoring, workflow-backed chat persistence and explicit discovery; workflow-backed-agent-sessions. |
| 2026-08-16 | 93de1d29 / #98 | Focused step inspection, timelines/payloads and start/cancel flows; workflow graph UX and user guides. |
| 2026-08-26 | c23f90f0 / #99–103 | Naming/renaming/deleting steps, focused step/run explorers and contained previews; workflow graph UX. |
| 2026-08-29 | a3139675 / #104 | Classified filesystem nodes and lazy bounded read-only text inspection; graph-filesystem-file-interactions. |
| 2026-08-30 | 7dafb4b3 / #105 | Lazy file-scale editing, piece table/sparse index and explicit conflict-aware saves; lazy-text-buffer-virtual-input. |

August 6 was active but its substantive graph/agent changes are already covered by published August 7: no duplicate entry. The later August 7 landing 731038fb / #78 (Sandbox Fly/Walk/Move/Grab and capability preflight) is not covered there. Preserve the published text; incorporate a brief **explicitly August 7** contextual bridge in August 8's paragraph, then describe August 8 changes without misdating the earlier work. No invented extra dated file or alteration to a published paragraph.

### September: 16 entries

| Date | Representative merge / PRs | Narrative and useful context |
|---|---|---|
| 2026-09-06 | 6b7200b6 / #106 | Modal lazy-editor interaction, UTF-8 navigation, clipping/caret visibility; lazy-text-buffer-virtual-input. |
| 2026-09-07 | fa96c88e / #107–109 | Kind badges and predictable click/insert routing; graph doctrine and lazy editor. |
| 2026-09-10 | 6880e04e / #110 | Anchor-based logical navigation without eager indexing; lazy editor, without claiming all commands avoid scans. |
| 2026-09-14 | e71d849a / #111–113 | Shared text editing/interaction policies for eager and lazy inputs; shared-text-interaction-engine and text-input-policies. |
| 2026-09-15 | 478233c5 / #114–120 | Owner-safe reloadable graph extensions, built-in descriptors and store-backed child creation; reloadable-graph-extension-units. |
| 2026-09-16 | b6486411 / #121–130 | Runtime asset overlays/module discovery, Windows GUI/CLI modes and error reporting foundations; runtime-asset-overlays/error-reporting. |
| 2026-09-17 | ab6f95cd / #131–142 | Ordered-list presentation islands plus reusable app bundles; graph maps/app-distribution. |
| 2026-09-18 | f3518229 / #143–151 | Snake as concrete distributable graphical example and orthographic UI; app-distribution/orthographic-ui-surface. |
| 2026-09-23 | 2dc460eb / #152 | Independent persisted presentation-island positions; graph maps. |
| 2026-09-24 | 86b797f7 / #153–156 | Member dragging, aggregate island movement and explicit pin preservation; graph maps. |
| 2026-09-25 | 006365d8 / #157–162 | Shared standalone/hosted app composition and explicit temporal value foundations; hosted-runtime-apps/temporal. |
| 2026-09-26 | d0979e78 / #163–169 | Host scene handles, inspections/commands, and bounded temporal parsing/interval arithmetic; hosted-runtime-apps/temporal-parsing-recurrence. |
| 2026-09-27 | c03f727b / #170–182 | Hosted command forms/results/async progress/history and richer recurrence; session-local history, not durable jobs. |
| 2026-09-28 | a5db5bf6 / #183–191 | SDK/module docs, graph-to-app launcher, temporal providers and RRULE expansion; SDK/hosted-runtime-apps. Dependency manifests are scaffolding, not imported-library completion. |
| 2026-09-29 | 3a113842 / #192–196 | Guarded CI diagnostics/Windows reproduction, path handling and island-force reliability; agent workflow. No new temporal feature despite branch names. |
| 2026-09-30 | 8ffecaaf / #197–198 | Explicit-zone recurrence sets/exclusions and interval semantics across DST; temporal-parsing-recurrence/temporal-intervals. |

### October: 15 entries

| Date | Representative merge / PRs | Narrative and useful context |
|---|---|---|
| 2026-10-01 | c508aa10 / #199–206 | Bounded ICS/localization/business calendars/natural candidates and contextual leader commands; temporal/leader-command-system. |
| 2026-10-02 | b337a7cf / #207–211 | Explicit timestamp migration and runtime scheduling; temporal-migrations/runtime-scheduler. |
| 2026-10-03 | c625ff09 / #212–214 | Documented temporal acceptance boundary, snackbars and focused selection; temporal-complete-acceptance/snackbar-system. |
| 2026-10-04 | fe49b36a / #215–217 | Non-destructive graph commands and backend-neutral asynchronous SSH foundation; graph maps/SSH subsystem. |
| 2026-10-05 | cfe63514 / #218–221,#223–224 | Concrete SSH integration, focus recovery and fast development; acknowledge shell round-trip quarantine, no universal conformance claim. |
| 2026-10-06 | 461d424a / #225–226 | Bounded asynchronous string-entity full-text search/navigation; string-entity-full-text-search. |
| 2026-10-07 | 1cc00a74 / #227–231 | Hierarchical focus and runtime asset freshness; hierarchical-focus design. Build broker was design only. |
| 2026-10-08 | df0845be / #232–237 | Outline projection over map topology, visible select-all and supporting reliability/CI; graph-outline-view design. |
| 2026-10-09 | 0b6ec360 / #238–247 | Substantive outline focus/selection parity and clearer CI/release responsibilities; graph maps/Actions hygiene. |
| 2026-10-10 | 62bd29ec / #248–249 | Shared compact projection lifecycle, inline activation and focus-preserving collapse; outline-compact-projection design. |
| 2026-10-11 | a04c3096 / #250–252 | Keyed dictionary entities and reusable MCP infrastructure with separate policies; dict-entities/opencode-mcp-bridges. |
| 2026-10-12 | 91135495 / #253–263 | Shared projection runtime, measured TreeView and reusable targeted CI; tree-view-widget/graph maps. |
| 2026-10-15 | b255778e / #265–268 | Entity-type catalog/map-local browsing and controlled watcherless live development; entity-type-catalog/live-dev. |
| 2026-10-17 | 0a0d1742 / #269–270 | Store-owned normalized references, resumable deletion/morph recovery and single-owner preview teardown; reference-lifecycle. Not a multi-file atomic transaction. |
| 2026-10-20 | a60bc99c / #271 | Complete PR/test/queue policy proof before strategy-free auto-merge; agent workflow. Distinct from published October 21 branch preparation. |

Skip October 14's model configuration refresh as standalone maintenance with no measured user outcome. Other absent days have no first-parent landing and need no filler.

## Execution, review and validation

Implement in three month-sized tasks with implementer/reviewer gates and compression passes. Each task owns its new entries and regenerated indexes; no concurrent index writers. Record date-to-evidence coverage and preserved-file verification in ignored task reports. Final whole-branch review checks all 41 entries against landing evidence, chronology, scope, bounded wording and useful links.

Run focused entry-shape/date/coverage/link checks, existing `npm run test:scripts`, index regeneration and `NODE_OPTIONS=--max-old-space-size=4096 npm run docs:build`. No native/Fennel build is relevant to prose-only changes. Check whitespace, expected scope and byte-identical pre-existing journal sources. Commit reviewed work; fetch/evaluate current origin/main, safely merge if needed and rerun validation. Publish a normal protected PR and poll through actual merge. Do not claim that social deliveries occurred merely because the content merged.

Self-review: exact 41-date manifest, historical cutoff, August boundary, content contract, normal-announcement consent and preservation requirements are explicit. No unresolved product choice remains.
