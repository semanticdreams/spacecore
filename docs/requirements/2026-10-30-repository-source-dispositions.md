# Frozen repository source dispositions

## Reading this inventory

Frozen source **F** = `fec176453c88fa1c47f22b7fe1d447dfe0ba281b`. Every filename row below refers to `F:<first-column path>`; line references are frozen-source lines, not current report lines. The 168 specs and 194 plan/progress files exclude only their two root `index.md` files. The later baseline design, plan and controller progress are outside that denominator and listed separately in the consolidated audit.

**S** means **supporting solution/evidence**, not activated intent, verified implementation or satisfaction. These historical solution proposals are retained for subsequent source/code/test reconciliation; being S does not assert they shipped. **U** means **unresolved gap**, with a concrete question. **R** means **duplicate/reused** with existing identities. No row is declared superseded based on its date/name. No artifact registration follows from inventory alone.

Owners: **2/G** graph/entities; **2/A** application agents/workflows/MCP; **2/T** text/input; **3/P** platform/runtime/layout; **3/D** development/validation/OpenCode workflow; **3/H** hosted apps/SDK; **3/Time** temporal; **3/N** networking/security/publication. Numbers identify the later audit task, not a new product hierarchy. Mixed boundaries are handoff responsibilities, not permission to expand scope.

Plan depth is **opening Goal only** (usually L5), unless a row says otherwise. The description in each row paraphrases that inspected Goal and names the specific missing trace. This is enough to identify a solution/evidence candidate, not enough to infer current applicability or completion. Spec depth is **opening intent/context only**, with exact inspected lines stated per row. Uninspected remainder, implementation and tests are explicitly outside Task 1 semantic coverage. Later owners must inspect original full contracts before canonical linkage. Concrete missing traces are not assertions of missing functionality.

### Task 2/G continuation depth and identities

The 72 **2/G** rows below were reconsidered at continuation BASE `7e65f11c`
against ledger 33, then updated at ledger 37. `G1`–`G10` are report-only shorthand,
not a hierarchy or new schema: G1 ownership/explicit materialization
`REQ-9b38aa4b-09ec-4c75-80af-8a2923c7afda`; G2 independent maps/projections
`REQ-3fbb0fc8-8b5f-406e-993d-be340d962e41`; G3 islands
`REQ-cce7be1b-f1a4-4fea-a3d3-e89fd1b2812c`; G4 outline
`REQ-fe18aeb4-afdf-42af-a456-bf4078ca2f20`; G5 contextual commands
`REQ-1aac8981-1d70-4471-b6a7-42ff6f81a56a`; G6 string search
`REQ-04d329ec-e1a7-49fe-9670-b816c46be005`; G7 immutable browsing catalog
`REQ-b4ba940f-acb9-41f0-a4c5-7e11f63dfbdb`; G8 dictionary references
`REQ-3211043c-28c4-4777-aca7-d716dddb508d`; G9 lifecycle/passive presentation
`REQ-a69bedbc-fbf5-48c5-91ac-9b2350d1fb2b`; G10 domain ordered children
`REQ-1f81f38f-6167-4f28-81b4-9264ffe56245`. All are proposed revision 1,
without assessment/verification. G10 has design linkage only, not an invented
implementation plan. See the appended G section of the Task 2 report for exact
artifact IDs, assertion ranges, source-history reconciliation and remaining gaps.
`G L1–16` means independently reread opening scope/architecture only; it is not
a full semantic review. Supporting refinements and concrete gaps intentionally
remain rather than turning every filename into a requirement or declaring it obsolete.

## Plans and progress (194 frozen paths)

| Source | Family/owner | Disposition | Inspected passage and resulting ID or concrete gap |
| --- | --- | --- | --- |
| `docs/plans/2026-07-25-readme-slimdown.md` | 3/D | S | L5: friendly landing-page relocation; README migration trace not established. |
| `docs/plans/2026-07-25-right-sidebar-rail.md` | 3/P | S | L5: measured rail sizing/anchoring; rail sizing tests untraced. |
| `docs/plans/2026-07-25-sandbox-scene-activity.md` | 3/P | S | L5: retained activity Scene slots; scene ownership implementation untraced. |
| `docs/plans/2026-07-26-external-unit-mcp.md` | 2/A | S | L5: loader-aware external unit tools; external/internal tool boundary untraced. |
| `docs/plans/2026-07-27-activity-owned-presentation.md` | 3/P | S | L5: activity-owned cameras/render targets/physics; ownership tests untraced. |
| `docs/plans/2026-07-27-experimental-fennel-constraints.md` | 3/D | S | L5: blocking source/scenario gate; current gate relation untraced. |
| `docs/plans/2026-07-27-opencode-instruction-split.md` | 3/D | S | L5: slim instructions plus skills; instruction migration history untraced. |
| `docs/plans/2026-07-27-remaining-presentation-test-failures.md` | 3/P | S | L5: fifteen presentation failures without global fallbacks; repaired assertions untraced. |
| `docs/plans/2026-07-27-validation-failure-recovery.md` | 3/D | S | L5: debug failed finishing validation; current recovery policy trace missing. |
| `docs/plans/2026-07-29-daily-devlog-automation.md` | 3/D | S | L5: meaningful-work daily narratives and PR publication; automation tests untraced. |
| `docs/plans/2026-07-29-retrospective-devlog-backfill.md` | 3/D | S | L5: source-grounded monthly history; source/date correspondence untraced. |
| `docs/plans/2026-07-29-sandbox-interaction-toolbar.md` | 3/P | S | L5: toolbar and force-at-anchor dragging; interaction assertions untraced. |
| `docs/plans/2026-07-30-native-log-directory.md` | 3/P | S | L5: deliberate user log location; native logging binding untraced. |
| `docs/plans/2026-07-30-runtime-asset-discovery.md` | 3/P | S | L5: executable-relative assets preserving overrides; resolver tests untraced. |
| `docs/plans/2026-07-31-ci-constraints-visibility.md` | 3/D | S | L5: explicit early Linux constraint step; workflow evidence untraced. |
| `docs/plans/2026-07-31-constraint-aware-agent-workflow.md` | 3/D | S | L5: early constraint feedback; static guidance versus live compliance unresolved. |
| `docs/plans/2026-07-31-fennel-agent-reliability.md` | 3/D | S | L5: native compile/query/MCP tools; supported-validator traces missing. |
| `docs/plans/2026-07-31-origin-main-constraint-integration.md` | 3/D | S | L5: safety integration branch; actual historical integration evidence untraced. |
| `docs/plans/2026-07-31-weekly-agent-workflow-automation.md` | 3/D | S | L5: sanitized weekly session analysis; automation risk/review traces missing. |
| `docs/plans/2026-08-01-agent-validation-continuation.md` | 3/D | S | L5: continue failed validation through recovery; current transition contract untraced. |
| `docs/plans/2026-08-01-concise-validation-output.md` | 3/D | S | L5: concise defaults preserving JSON; output-mode tests untraced. |
| `docs/plans/2026-08-01-daily-devlog-landing-date.md` | 3/D | S | L5: attribute landing rather than author date; first-parent date tests untraced. |
| `docs/plans/2026-08-01-local-quiet-cef-light-build.md` | 3/D | S | L5: quiet CEF-off local default; explicit full-build preservation untraced. |
| `docs/plans/2026-08-01-orca-opencode-workflow.md` | 3/D | S | L5: canonical setup guide; current setup/reference trace missing. |
| `docs/plans/2026-08-01-stable-fennel-constraints.md` | 3/D | S | L5: terminology-only cleanup; no synthetic new gate obligation warranted. |
| `docs/plans/2026-08-01-web-researcher-agent.md` | 3/D | S | L5: bounded research role without widening others; role permission tests untraced. |
| `docs/plans/2026-08-01-windows-artifact-fast-suite.md` | 3/D | S | L5: packaged fast-suite follow-up; exact portability assertions untraced. |
| `docs/plans/2026-08-01-windows-test-workflow.md` | 3/D | S | L5: remove Windows path assumptions; native source/test linkage missing. |
| `docs/plans/2026-08-02-merge-queue-agent-workflow.md` | 3/D | S | L5: repository references and queue workflow; queue configuration evidence untraced. |
| `docs/plans/2026-08-02-targeted-agent-validation.md` | 3/D | S | L5: focused defaults with runtime freshness/CI; high-risk escalation tests untraced. |
| `docs/plans/2026-08-02-until-merged-merge-queue.md` | 3/D | S | L5: monitor actual merge; queue versus merged-state trace missing. |
| `docs/plans/2026-08-02-workflow-debug-pr-landing.md` | 3/D | S | L5: dedicated PR rather than main push; capability boundary untraced. |
| `docs/plans/2026-08-03-hud-chrome-button-owned-padding.md` | 3/P | S | L5: button-owned padding; natural-height regression tests untraced. |
| `docs/plans/2026-08-03-hud-chrome-visual-uniformity.md` | 3/P | S | L5: natural-measurement chrome metrics; layout evidence untraced. |
| `docs/plans/2026-08-04-hud-control-button-spacing.md` | 3/P | S | L5: remove horizontal gaps retaining sizing; spacing assertions untraced. |
| `docs/plans/2026-08-04-hud-right-rail-transparent-strip.md` | 3/P | S | L5: rail-only reserve with projected panel; parent-layout tests untraced. |
| `docs/plans/2026-08-05-opencode-permission-capabilities.md` | 3/D | S | L5: guarded operations without wider role authority; wrapper tests untraced. |
| `docs/plans/2026-08-06-graph-sidebar-node-finder.md` | 2/G | S | G L1–16: sidebar membership controls versus view reveal/open callbacks; supports G2/G5 and graph-maps sidebar contract. Finder widget assertion chain not sampled. |
| `docs/plans/2026-08-06-sandbox-interaction-modes.md` | 3/P | S | L5: exclusive Fly/Walk/Move/Grab; mode transition tests untraced. |
| `docs/plans/2026-08-07-graph-ux-polish.md` | 2/G | S | G L1–16: restrained theme and integer-like restored map IDs, explicitly not relaxed safe-map IDs. Supporting G2 solution; truncation/color and restored-float assertions remain untraced. |
| `docs/plans/2026-08-07-opencode-capability-preflight.md` | 3/D | S | L5: missing wrapper/agent preflight; failure-path tests untraced. |
| `docs/plans/2026-08-08-graph-activity-theme-panel-ux.md` | 2/G | S | G L1–16: theme edge defaults, bounded panels and activity dock lifecycle, not domain mutations. Supports G2; per-edge overrides/panel-size/dock assertions not sampled. |
| `docs/plans/2026-08-08-graph-map-camera-isolation.md` | 2/G | S | G L1–16: stable live camera plus map-specific metadata; G2 also grounded by full camera design. Camera persistence assertions L71–258 sampled; activity-switch and Board camera implementation remain untraced here. |
| `docs/plans/2026-08-10-light-theme-layering.md` | 3/P | S | L5: subtle tonal tokens without widget API changes; visual evidence missing. |
| `docs/plans/2026-08-12-opencode-runtime-artifact-access.md` | 3/D | S | L5: inspect safe runtime artifacts preserving secrets; access contract untraced. |
| `docs/plans/2026-08-12-space-agent-live-development-reliability.md` | 2/A | S | L5: session-scoped live development context; reconnect/live-disk distinctions untraced. |
| `docs/plans/2026-08-13-activity-camera-boundary.md` | 3/P | S | L5: prevent cross-activity camera/raycast mutation; boundary tests untraced. |
| `docs/plans/2026-08-14-activity-aware-world-graph-exposure.md` | 2/G | S | G L1–16: world/activity/surface hierarchy and sandbox-key hydration migration preserve activity ownership, supporting G1. Graph-maps migration table read; WorldData and native surface mutation assertions deferred to platform owner. |
| `docs/plans/2026-08-14-graph-authored-agent-workflows.md` | 2/A | S | L5: durable workflows outside graph-map ownership; persistence/authoring traces missing. |
| `docs/plans/2026-08-14-workflow-user-flow-polish.md` | 2/A | S | L5: Start-to-run workflow authoring; complete-path assertions untraced. |
| `docs/plans/2026-08-15-explicit-graph-discovery.md` | 2/G | S | G L1–16: actual plan realizes full explicit-discovery design and addresses G1. Definitions then per-definition runs are deliberate controls, not hidden fan-out. Workflow control assertions remain 2/A scope. |
| `docs/plans/2026-08-15-workflow-backed-agent-sessions.md` | 2/A | S | L5: sidebar chats as long-lived runs; chat continuity tests untraced. |
| `docs/plans/2026-08-16-workflow-graph-ux.md` | 2/A | S | L5: workflow visual control surfaces; node action traces missing. |
| `docs/plans/2026-08-26-workflow-preview-decomposition.md` | 2/A | S | L5: compact previews with explicit explorers; discovery traces missing. |
| `docs/plans/2026-08-29-graph-filesystem-file-interactions.md` | 2/G | S | G L1–16: generic path adapter versus explicit file-interaction rows and bounded viewer. Supports G1; existing lazy-editor/save IDs reused rather than duplicating file-scale requirements. External-edit/module actions and native window reader remain concrete gaps. |
| `docs/plans/2026-08-30-lazy-text-buffer-virtual-input.md` | 2/T | S | Task 2 full L1–625: lazy source/buffer/widget/viewer plan; ART-9bad9647-63a6-45a5-9bef-4e82974048dc realizes its design, with source/buffer code traces. REQ-b5e94348-9fab-4aea-9cfb-31fc6553756c and REQ-ffd79d7c-9bd7-44a1-9871-84a476629de4; buffer assertions inspected, widget/native/viewer completeness still uninspected. |
| `docs/plans/2026-09-06-virtual-input-file-viewer-usability.md` | 2/T | S | L5: Vim routing/clipping/caret; regression assertions untraced. |
| `docs/plans/2026-09-07-graph-titlebar-kind-badges.md` | 2/G | S | G L1–16: render-time titlebar badge metadata, compact points unchanged. G1 ownership-compatible presentation refinement; badge normalization/dialog-prefix assertions not sampled, no separate micro-requirement imported. |
| `docs/plans/2026-09-10-virtual-input-lazy-anchor-navigation.md` | 2/T | S | L5: bounded h/l/j/k after far jumps; navigation cost evidence missing. |
| `docs/plans/2026-09-10-virtual-input-navigation-parity.md` | 2/T | S | L5: Input parity retaining lazy clipping; parity tests untraced. |
| `docs/plans/2026-09-14-reloadable-graph-node-units.md` | 2/G | S | G L1–16 plus full paired design: vertical loader/adapter/preview/morph refresh and owner handles, supporting existing live-development goal and G1. Full ModuleUnit/reload seam assertion chain remains a declared representative-depth gap. |
| `docs/plans/2026-09-14-shared-text-interaction-engine.md` | 2/T | S | L5: shared editing port/normal commands; lowercase-w proving test untraced. |
| `docs/plans/2026-09-14-virtual-input-shared-input-policies.md` | 2/T | S | L5: shared focus/caret policies; eager/lazy equivalence untraced. |
| `docs/plans/2026-09-15-built-in-graph-extensions.md` | 2/G | S | G L1–16 and full design: one descriptor mechanism, no central forwarding registrar; G1/G7 ownership context, not catalog-driven loader installation. Built-in full scheme/hydration/reload assertions not independently sampled. |
| `docs/plans/2026-09-15-graph-node-menu-separators.md` | 2/G | S | G L1–16: menu manager preserves separators; GraphView composes general actions then adapter actions. Supports G5 shared action-list semantics; divider routing/rendering assertions remain untraced. |
| `docs/plans/2026-09-15-runtime-fennel-directory-modules.md` | 3/P | S | L5: embedded directory macro/module paths; launch-path tests untraced. |
| `docs/plans/2026-09-15-string-entity-create-child.md` | 2/G | S | G L1–16: owning child/link creation then same-map reveal via derived edge. Reuse Access/text-revision IDs; later graph-capabilities L422–439 explicitly disclaims compensating committed work, so no atomic multi-record promise. Child failure assertions not newly sampled. |
| `docs/plans/2026-09-16-bugsink-sentry-error-reporting.md` | 3/P | S | L5: vendored Sentry reporting after DSN init; error-path bindings untraced. |
| `docs/plans/2026-09-16-merged-pr-followup-branch.md` | 3/D | S | L5: deterministic follow-up branch; already-merged recovery tests untraced. |
| `docs/plans/2026-09-16-release-artifact-naming.md` | 3/D | S | L5: consistent Linux/Windows artifact names; packaging assertions untraced. |
| `docs/plans/2026-09-16-runtime-asset-overlay.md` | 3/P | S | L5: project overlays before built-ins; fallback resolution tests untraced. |
| `docs/plans/2026-09-16-windows-desktop-cli-launch.md` | 3/P | S | L5: desktop exe and console companion; launcher behavior untraced. |
| `docs/plans/2026-09-16-windows-packaged-fast-suite.md` | 3/D | S | L5: portable packaged child/path fixtures; exact failure repair trace missing. |
| `docs/plans/2026-09-17-graph-presentation-islands.md` | 2/G | S | G L1–16: registered actual plan realizes full island design and addresses G3. Ordered-list presenter and island assertions sampled; domain parent-child association is distinct G10 with implementation unknown. |
| `docs/plans/2026-09-17-space-app-distribution.md` | 3/H | S | L5: apps download pinned runtimes; packaging chain untraced. |
| `docs/plans/2026-09-18-fix-snake-presentation.md` | 3/H | S | L5: upright/scaled Snake and stable status; example-specific evidence only, tests untraced. |
| `docs/plans/2026-09-18-graphical-snake-example.md` | 3/H | S | L5: 2D widget Snake; example-to-runtime teaching contract untraced. |
| `docs/plans/2026-09-18-snake-example-template.md` | 3/H | S | L5: independent app template; no general gameplay obligation inferred. |
| `docs/plans/2026-09-18-snake-orthographic-ui-surface.md` | 3/H | S | L5: reusable orthographic UI surface; reusable host tests untraced. |
| `docs/plans/2026-09-23-independent-island-bodies.md` | 2/G | S | G L1–16: absolute body position, not source-node anchor; supports G3 criterion c2. Presenter L52–77 and old-format member-fallback assertion L750–771 inspected; complete persistence chain not sampled. |
| `docs/plans/2026-09-23-island-member-drag-handles.md` | 2/G | S | G L1–16: presenter derives new body at alt-drag end; supports G3 c3. Actual second-member drag L773–795 preserves other members during drag and moves on drop; non-alt matrix remains untraced. |
| `docs/plans/2026-09-24-list-entity-compact-labels.md` | 2/G | S | G L1–16: explicit compact-label opt-out while retaining raw key access; presentation-only under G1. Compact label rendering cases not sampled; do not confuse this with identity terminal-label semantics in G9. |
| `docs/plans/2026-09-24-movable-graph-islands.md` | 2/G | S | G L1–16: aggregate participant replaces implicit membership pins, not C++ solver redesign. Supports G3; replacement/pin cleanup assertions L622–669 sampled, complete force movement matrix remains unknown. |
| `docs/plans/2026-09-24-stale-merged-pr-recovery.md` | 3/D | S | L5: guarded follow-up push/PR recovery; capability invariants untraced. |
| `docs/plans/2026-09-25-force-layout-island-behavior.md` | 2/G | S | G L1–16: visual-center force anchor converts back to persisted origin, explicit pins excluded. G3; actual presenter L90–117 conversion inspected, exhaustive force/runtime cache assertions not sampled. |
| `docs/plans/2026-09-25-hostable-space-apps.md` | 3/H | S | L5: runtime compositions over host capabilities; host/app ownership tests untraced. |
| `docs/plans/2026-09-25-hosted-app-scene-capabilities.md` | 3/H | S | L5: app-owned scene CRUD/cleanup; sandbox independence tests untraced. |
| `docs/plans/2026-09-25-hosted-app-workspace-adapters.md` | 3/H | S | L5: HUD/canvas/scene workspace adapters; mounting/composition tests untraced. |
| `docs/plans/2026-09-25-temporal-ecosystem-core.md` | 3/Time | S | L5: native temporal core and wrapper; conformance definitions untraced. |
| `docs/plans/2026-09-25-windows-ci-local-reproduction.md` | 3/D | S | L5: guarded cross-build/Wine loop; real platform observations untraced. |
| `docs/plans/2026-09-26-3d-snake-scene-view.md` | 3/H | S | L5: mirrored game state via host.scene; example not general gameplay proof. |
| `docs/plans/2026-09-26-hosted-app-command-surface.md` | 3/H | S | L5: generic command execution without visual UI; descriptor tests untraced. |
| `docs/plans/2026-09-26-hosted-app-inspector-panel.md` | 3/H | S | L5: read-only registry snapshots; inspector isolation tests untraced. |
| `docs/plans/2026-09-26-temporal-calendar-periods.md` | 3/Time | S | L5: civil periods preserving exact Duration; arithmetic edge cases untraced. |
| `docs/plans/2026-09-26-temporal-intervals.md` | 3/Time | S | L5: half-open and repeating intervals; endpoint tests untraced. |
| `docs/plans/2026-09-26-temporal-parsing-recurrence.md` | 3/Time | S | L5: layered parsing/recurrence above core; layer-independence traces missing. |
| `docs/plans/2026-09-27-hosted-app-command-confirmations.md` | 3/H | S | L5: danger metadata/two-click confirmation; confirmation scope tests untraced. |
| `docs/plans/2026-09-27-hosted-app-command-controls.md` | 3/H | S | L5: generic visual Run controls; command UI tests untraced. |
| `docs/plans/2026-09-27-hosted-app-command-payload-forms.md` | 3/H | S | L5: scalar schemas and forms; payload validation tests untraced. |
| `docs/plans/2026-09-27-hosted-async-command-progress.md` | 3/H | S | L5: opt-in async/cancel/cleanup; synchronous compatibility tests untraced. |
| `docs/plans/2026-09-27-hosted-command-history.md` | 3/H | S | L5: bounded session-local history; retention tests untraced. |
| `docs/plans/2026-09-27-hosted-command-result-ux.md` | 3/H | S | L5: latest results/double-run protection; busy-state tests untraced. |
| `docs/plans/2026-09-27-temporal-expression-projection.md` | 3/Time | S | L5: reference instant through explicit zone; projection tests untraced. |
| `docs/plans/2026-09-27-temporal-interval-period-endpoints.md` | 3/Time | S | L5: plain datetime period endpoints; zoned exclusion applicability untraced. |
| `docs/plans/2026-09-27-temporal-monthly-yearly-recurrence.md` | 3/Time | S | L5: bounded calendar recurrence; expansion assertions untraced. |
| `docs/plans/2026-09-27-temporal-rrule-bymonth.md` | 3/Time | S | L5: BYMONTH round-trip/expansion; filter semantics untraced. |
| `docs/plans/2026-09-27-temporal-rrule-bymonthday-generator.md` | 3/Time | S | L5: monthly/yearly generation versus daily filters; frequency-specific tests untraced. |
| `docs/plans/2026-09-27-temporal-rrule-bymonthday.md` | 3/Time | S | L5: positive BYMONTHDAY filtering; later generator relation untraced. |
| `docs/plans/2026-09-27-temporal-rrule-until-bound.md` | 3/Time | S | L5: inclusive finite UNTIL; expansion-bound tests untraced. |
| `docs/plans/2026-09-28-hosted-app-launcher-node.md` | 3/H | S | L5: graph launcher selected filesystem app; hosting authorization tests untraced. |
| `docs/plans/2026-09-28-sdk-docs.md` | 3/H | S | L5: builder-facing SDK section; API completeness not established. |
| `docs/plans/2026-09-28-sdk-module-reference.md` | 3/H | S | L5: module reference/imports/examples; public export coverage untraced. |
| `docs/plans/2026-09-28-temporal-complete-library-roadmap.md` | 3/Time | S | L5: complete-library executable roadmap; broad versus bounded closeout authority requires Task 3 history investigation. |
| `docs/plans/2026-09-28-temporal-dependency-data-packaging-foundation.md` | 3/Time | S | L5: manifest-first data foundation; actual packaged corpus untraced. |
| `docs/plans/2026-09-28-temporal-provider-registry.md` | 3/Time | S | L5: deterministic local provider registry; provider order tests untraced. |
| `docs/plans/2026-09-28-temporal-rfc5545-recurrence.md` | 3/Time | S | L5: in-scope RFC5545 expansion; standard corpus boundaries untraced. |
| `docs/plans/2026-09-28-temporal-rrule-byday-generator.md` | 3/Time | S | L5: non-ordinal monthly/yearly BYDAY; generator tests untraced. |
| `docs/plans/2026-09-29-opencode-ci-diagnostics-tooling.md` | 3/D | S | L5: CI logs/repo-local vcpkg bootstrap; safe bootstrap tests untraced. |
| `docs/plans/2026-09-30-temporal-full-iso-intervals.md` | 3/Time | S | L5: selected ISO zoned/exact/period endpoints; DST policies untraced. |
| `docs/plans/2026-09-30-temporal-recurrence-set-zoned.md` | 3/Time | S | L5: finite sets/zones/UTC UNTIL; ambiguity cases untraced. |
| `docs/plans/2026-10-01-extensible-leader-command-system.md` | 2/G | S | G L1–16: actual plan realizes full command design/addresses G5; provider selection gating and actual keymap/hint assertions traced. Leader state dispatch and all legacy keys not exhaustively inspected. |
| `docs/plans/2026-10-01-graph-enter-preview.md` | 2/G | S | G L1–16: idempotent focused Enter expansion versus explicit full-view opening. Supporting G5 navigation context, not selected-preview fallback. Focus activation runtime/assertions remain untraced. |
| `docs/plans/2026-10-01-temporal-business-calendar.md` | 3/Time | S | L5: deterministic US-FED corpus; holiday coverage bounds untraced. |
| `docs/plans/2026-10-01-temporal-ics-icalendar.md` | 3/Time | S | L5: selected VCALENDAR/VEVENT corpus; unsupported ICS forms untraced. |
| `docs/plans/2026-10-01-temporal-localization-calendar.md` | 3/Time | S | L5: CLDR seed facades; locale/calendar breadth untraced. |
| `docs/plans/2026-10-01-temporal-migrations.md` | 3/Time | S | L5: UTC workflow writes/legacy reads; other persistence stores untraced. |
| `docs/plans/2026-10-01-temporal-natural-language.md` | 3/Time | S | L5: three-locale candidate parsing; ambiguity/context tests untraced. |
| `docs/plans/2026-10-02-runtime-scheduler.md` | 3/Time | S | L5: typed scheduler retaining RuntimeTimers; timer compatibility tests untraced. |
| `docs/plans/2026-10-02-snackbar-system-implementation-plan.md` | 3/P | S | L5: scoped reusable snackbar host; lifetime/policy assertions untraced. |
| `docs/plans/2026-10-03-graph-selection-leader-commands.md` | 2/G | S | G L1–16: focused-node operations through native selector with map-owned persisted selection; supports G5. Actual availability/hint assertions L276–324 inspected; full selector integration remains untraced. |
| `docs/plans/2026-10-03-temporal-closeout.md` | 3/Time | S | L5: bounded smoke, not ecosystem equivalence; cannot retire broader intent without source authority. |
| `docs/plans/2026-10-04-graph-leader-command-expansion.md` | 2/G | S | G L1–16: same pointer/numeric action list and bounded focused/view/map commands; G5 plus G2 map context. Provider resolver/gating code inspected; complete action slot and map manager assertion chains not sampled. |
| `docs/plans/2026-10-04-ssh-integration-foundation.md` | 3/N | S | L5: isolated libssh async/fleet APIs; backend availability tests untraced. |
| `docs/plans/2026-10-05-focus-start-node-command.md` | 2/G | S | G L1–16: focus-start orchestrates existing Add Start then reveal options, not a new loader API. Included in G5 c3; graph-maps action semantics read, full actual command assertion not newly sampled. |
| `docs/plans/2026-10-05-opencode-fast-development-flow.md` | 3/D | S | L5: interactive lane with strict default; later lane authority untraced. |
| `docs/plans/2026-10-05-ssh-real-backend-validation.md` | 3/N | S | L5: real Linux SSH CI; fixture versus real backend observations untraced. |
| `docs/plans/2026-10-06-fast-dev-local-main-wrap-up.md` | 3/D | S | L5: local-main guarded conversion; current branch contract applicability untraced. |
| `docs/plans/2026-10-06-string-entity-text-search.md` | 2/G | S | G L1–16: actual plan realizes full search design/addresses G6. Backend and node implementations plus options/grouping/cancellation/stale/capture assertions traced; actual ripgrep process and UI submission runtime not executed. |
| `docs/plans/2026-10-07-hierarchical-focus-navigation.md` | 3/P | S | L5: generic entry/exit focus scopes; focus restoration tests untraced. |
| `docs/plans/2026-10-08-graph-outline-view.md` | 2/G | S | G L1–16: actual plan realizes full outline design/addresses G4; pure projection and L354–407 actual traversal/cycle/root assertions inspected. Later point-owned interaction and measured layout are refinements, not supersession. |
| `docs/plans/2026-10-08-windows-ci-speedups.md` | 3/D | S | L5: separate validation from packaging; release preservation tests untraced. |
| `docs/plans/2026-10-09-github-workflow-cleanup.md` | 3/D | S | L5: workflow permissions/pins/trust; protection assertions untraced. |
| `docs/plans/2026-10-09-outline-compact-projection.md` | 2/G | S | G L1–16: compact point owns click/focus/select, whitespace miss; G4 c3 reflects this later refinement. Shared projection code/teardown matrix not fully read, no visual correctness claim. |
| `docs/plans/2026-10-09-windows-main-ci.md` | 3/D | S | L5: post-merge/manual Windows validation; historical required-check changes untraced. |
| `docs/plans/2026-10-11-dict-entity.md` | 2/G | S | G L1–16: actual plan realizes full dictionary design/addresses G8. Owning persistence/mutation paths and JSON reload/item-error/no-op assertions sampled; full dictionary UI not inspected. Later stable writes reuse G9. |
| `docs/plans/2026-10-11-graph-projection-runtime.md` | 2/G | S | G full L1–252: mode-specific persistence and shared runtime, selection, activity adapters; G2. Runtime code and camera regression assertions inspected; complete activity/teardown caller matrix remains unknown. |
| `docs/plans/2026-10-11-opencode-mcp-bridge-core.md` | 2/A | S | L5: policy-neutral shared mechanism; distinct client contracts untraced. |
| `docs/plans/2026-10-12-ci-prebuilt-runtime.md` | 3/D | S | L5: trusted minimal runtime reuse; native-impact classification untraced. |
| `docs/plans/2026-10-12-outline-marker-box.md` | 2/G | S | G L1–16: stable measured marker footprint, not uniform row height; G4 presentation refinement. Marker glyph/selection layout assertions and visual evidence remain untraced. |
| `docs/plans/2026-10-12-tree-view-outline.md` | 2/G | S | G L1–16: generic measured TreeView with graph-specific compact interaction retained; G4 solution refinement. Generic widget implementation belongs to platform; no widget quality proof imported. |
| `docs/plans/2026-10-14-entity-type-catalog.md` | 2/G | S | G full L1–311 including composition-helper addendum: actual plan realizes full catalog design/addresses G7. Catalog code and mutation-isolation/order/validation assertions traced; complete Main publication/rollback and sibling-view matrix untraced. |
| `docs/plans/2026-10-15-fast-dev-independent-workflow.md` | 3/D | S | L5: direct checkpoints/explicit wrap-up; publication authority tests untraced. |
| `docs/plans/2026-10-15-graph-capabilities.md` | 2/G | S | Predecessor full L1–254 and G L1–16 retain ART-e2dae7e7-a13b-45d6-af66-1d4780d2c7cf / ART-46414157-af80-4192-8dbe-5afb6213b3e2 and Access/Isolation/revision IDs. Later DTO identity extension confirmed at 13d86a98, not retroactively part of the original plan. No fresh product/native verification. |
| `docs/plans/2026-10-15-live-dev.md` | 3/D | S | L5: checkout-scoped verified app refresh; manual lifecycle assertions untraced. |
| `docs/plans/2026-10-15-reference-lifecycle.md` | 2/G | S | G L1–361: shared ownership/frozen-image protocol, identity operations, owning normalization and coordinator interfaces; registered plan realizes full design/addresses G9. L211–236 requires resolved endpoints; later DTO amendment independently confirmed. Tasks after361 not fully read; owner/recovery coverage remains representative. |
| `docs/plans/2026-10-15-reload-boundary-contract.md` | 3/P | S | L5 opening: root-default development reload; audited narrow reload boundary needs full-body inspection. |
| `docs/plans/2026-10-16-link-endpoint-presentation.md` | 2/G | S | G L1–16: display terminal meaning without writes/allocations, preserve deliberate aliases and canonical-pair Swap; G9 c3. Snapshot/side-specific UI assertions remain untraced, not called satisfied by DTO tests. |
| `docs/plans/2026-10-16-reference-lifecycle-composition-placement.md` | 2/G | S | G L1–16: behavior-preserving placement in existing composition and HomeWorld helper, Main sequencing retained. Maintenance supporting G9, no synthetic requirement. Structural/baseline measures not revalidated here. |
| `docs/plans/2026-10-16-reference-lifecycle-deferred-morph.md` | 2/G | S | G L1–16: deferred read-only builder admitted inside serialized coordinator; G9 recovery refinement. Actual init L276–313 inspected, but source-retired frontend/restart assertions not sampled. |
| `docs/plans/2026-10-16-reference-lifecycle-full-gate-repairs.md` | 2/G | S | G L1–16: finite FXAA mock, fixture ownership and duplicate outline selection cleanup; maintenance supporting G2/G9. Opaque mode-state retention remains contractual, not re-proven by historical gate wording. |
| `docs/plans/2026-10-16-reference-lifecycle-reload-merge.md` | 2/G | S | G L1–16: preserve 21 registrations while extracting injected root-fixture support. Merge maintenance, not new product intent or G9 satisfaction; exact parent regression union not independently audited. |
| `docs/plans/2026-10-16-reference-presentation-extension.md` | 2/G | S | G L1–16 and full current lifecycle feature L56–71: passive list labels and concrete-owner notebook previews cause zero writes, preserving canonical aliases/order; G9 c3. Full actual preview/provider/callback assertion chain remains untraced. |
| `docs/plans/2026-10-16-secure-record-publication.md` | 3/N | S | L5: private publication/default editing via native draft APIs; overwrite/migration tests untraced. |
| `docs/plans/2026-10-16-windows-validation-diagnostics.md` | 3/D | S | L5: remove Wine-helper contamination; trusted reproduction provenance untraced. |
| `docs/plans/2026-10-16-wine-suite-lifecycle.md` | 3/D | S | L5: finite suite budget/isolated server cleanup; unrelated-prefix safety untraced. |
| `docs/plans/2026-10-17-wine-native-failure-diagnostics.md` | 3/D | S | L5: InputDialType defect/actionable failures; diagnostic/native boundary untraced. |
| `docs/plans/2026-10-17-wine-posix-publication.md` | 3/N | S | L5: real persistent Wine publication preserving policy; actual success evidence untraced. |
| `docs/plans/2026-10-18-constraint-scenario-ownership.md` | 3/D | S | L5: scenario ownership/caller isolation; invocation state tests untraced. |
| `docs/plans/2026-10-18-wine-diagnostics-checkpoints.md` | 3/D | S | L5: portability diagnostics in three checkpoints; complete diagnostic contract untraced. |
| `docs/plans/2026-10-18-wine-suite-portability-repairs.md` | 3/D | S | L5: zero-failure actual Wine requirement; historical observation applicability untraced. |
| `docs/plans/2026-10-20-constraints-assert-call-index.md` | 3/D | S | L5: behavior-preserving lazy assertion index; maintenance, not synthetic requirement. |
| `docs/plans/2026-10-20-devlog-branch-capability.md` | 3/D | S | L5: exact dated-branch capability; guard tests untraced. |
| `docs/plans/2026-10-20-guarded-merge-policy.md` | 3/D | S | L5: prove protection/queue method before auto-merge; policy query tests untraced. |
| `docs/plans/2026-10-21-devlog-gap-backfill.md` | 3/D | S | L5: 41 evidence-backed entries; count is historical task scope, not product target. |
| `docs/plans/2026-10-21-sse-closure-finalizers.md` | 3/N | S | L5: safe callback GC before shutdown; finalization tests untraced. |
| `docs/plans/2026-10-22-checkpoint-review-ownership.md` | 3/D | S | L5: checkpoint ownership preserving review; complete-range gates untraced. |
| `docs/plans/2026-10-23-daily-devlog-catch-up.md` | 3/D | S | L5: prior-day meaningful-work catch-up; no-op regression tests untraced. |
| `docs/plans/2026-10-24-wine-test-child-launch.md` | 3/D | S | L5: closed Unix launch boundary for five children; environment isolation untraced. |
| `docs/plans/2026-10-25-current-layout-boundary-diagnostic.md` | 3/D | S | L5: masking versus residual elapsed work; no optimization/timeout weakening inferred. |
| `docs/plans/2026-10-25-glm-default-expert-consultation.md` | 3/D | S | L5: model/consultation policy proposal; current routing authority must be compared, not activated. |
| `docs/plans/2026-10-25-interactive-canonical-candidates.md` | 3/D | S | L5: remove non-diagnostic work/resolve Wine timeout; performance evidence untraced. |
| `docs/plans/2026-10-25-opencode-model-pilot.md` | 3/D | S | L5: model architectural judgment comparison; actual evaluation evidence untraced. |
| `docs/plans/2026-10-28-development-records-progress.md` | 3/D | U | L3 navigation only: which retained observations establish development-record migration coverage? Body not reviewed. |
| `docs/plans/2026-10-28-opencode-session-graph-review-progress.md` | 2/A | U | L3 navigation only: which session-exposure assertions were independently reviewed? Body not reviewed. |
| `docs/plans/2026-10-29-autonomous-handoff-recovery-progress.md` | 3/D | U | L5 task identity only: which recovery failure ancestry and final review range apply? Body not reviewed. |
| `docs/plans/2026-10-29-autonomous-handoff-recovery.md` | 3/D | S | L5: autonomous delivery recovery with fail-closed safeguards; replacement-assessment tests untraced. |
| `docs/plans/2026-10-29-model-neutral-agent-routing-progress.md` | 3/D | U | L5 task identity only: which routing snapshot and review remain applicable? Body not reviewed. |
| `docs/plans/2026-10-29-model-neutral-agent-routing.md` | 3/D | S | L5: configuration-only role routing; routing syntax tests untraced. |
| `docs/plans/2026-10-29-opencode-island-edges-progress.md` | 2/A | U | L5 live-dev identity only: what island edge evidence was observed versus reviewed? Body not reviewed. |
| `docs/plans/2026-10-29-requirements-driven-engineering-progress.md` | 3/D | R | L5 task identity plus existing registry inspection: ART-bcf4c87c-bbac-44ce-a779-2be4b2d851e3 retained; mutable historical evidence, not fresh baseline observation. |
| `docs/plans/2026-10-29-requirements-driven-engineering.md` | 3/D | R | L5 methodology implementation Goal: reuse ART-d5aa9361-7216-43f1-99e2-1bdd9446070b and existing methodology obligations, not product goals. |
| `docs/plans/2026-10-29-sftp-success-finalization.md` | 3/N | S | L5: notify success after checked local I/O/remote close/teardown; failure-order tests untraced. |
| `docs/plans/2026-10-30-autonomous-workflow-decisions-progress.md` | 3/D | U | L5 controller/branch identity only: what authorized journal changes and gate evidence remain current? Body not reviewed. |
| `docs/plans/2026-10-30-autonomous-workflow-decisions.md` | 3/D | S | L5 opening: autonomous routine decisions; full journal-edit scope and current policy trace uninspected. |

## Specifications (168 frozen paths)

| Source | Family/owner | Disposition | Inspected passage and resulting ID or concrete gap |
| --- | --- | --- | --- |
| `docs/specs/2026-07-25-readme-slimdown-design.md` | 3/D | S | L1–28: front door for users/builders, preserving positioning; content relocation trace missing. |
| `docs/specs/2026-07-25-right-sidebar-rail-design.md` | 3/P | S | L1–28: button-driven sizing preserving panel lifecycle; sizing/persistence regression trace missing. |
| `docs/specs/2026-07-25-sandbox-scene-activity-design.md` | 3/P | U | L5 opening: retained HomeWorld scene; how does retention remove always-on scene ownership? Full contract uninspected. |
| `docs/specs/2026-07-26-external-unit-mcp-design.md` | 2/A | U | L5 opening: existing in-app unit tools; which loader-aware tools are externally safe? Full boundary uninspected. |
| `docs/specs/2026-07-27-activity-owned-presentation-design.md` | 3/P | U | L5 opening: runtime/activity mismatch; which render/physics services must transfer ownership? Full contract uninspected. |
| `docs/specs/2026-07-27-experimental-fennel-constraints-design.md` | 3/D | S | L5: blocking Fennel constraint system; executable scenario applicability untraced. |
| `docs/specs/2026-07-27-opencode-instruction-split-design.md` | 3/D | S | L5: compact always-on guidance with domain skills; doctrine preservation trace missing. |
| `docs/specs/2026-07-27-validation-failure-recovery-design.md` | 3/D | U | L5 opening: stopped finishing validation; which recovery transitions now supersede terminal stopping? Full rules uninspected. |
| `docs/specs/2026-07-29-daily-devlog-automation-design.md` | 3/D | S | L5: narrative meaningful work in goals/milestone context, not commit list; source-grounding checks untraced. |
| `docs/specs/2026-07-29-retrospective-devlog-backfill-design.md` | 3/D | S | L5: continuous historical arcs without exact-date invention; provenance checks untraced. |
| `docs/specs/2026-07-29-sandbox-interaction-toolbar-design.md` | 3/P | U | L5 opening: richer manipulation controls in existing HUD; what owns camera versus drag state? Full transition contract uninspected. |
| `docs/specs/2026-07-30-native-log-directory-design.md` | 3/P | U | L5 opening: arbitrary-working-directory launches; which log location and overrides are authoritative? Full resolver uninspected. |
| `docs/specs/2026-07-30-runtime-asset-discovery-design.md` | 3/P | U | L5 opening: executable asset-root requirement; what search precedence preserves overrides? Full resolver uninspected. |
| `docs/specs/2026-07-31-ci-constraints-visibility-design.md` | 3/D | S | L5: explicit early CI visibility of existing gate; CI dependency/exit-code checks untraced. |
| `docs/specs/2026-07-31-constraint-aware-agent-workflow-design.md` | 3/D | S | L5: early constraint feedback without ritual; live efficiency evidence absent. |
| `docs/specs/2026-07-31-fennel-agent-reliability-design.md` | 3/D | U | L5 opening: syntax/parser repair costs; which native validation contract replaces unsupported oracles? Full tooling contract uninspected. |
| `docs/specs/2026-07-31-origin-main-constraint-integration-design.md` | 3/D | S | L5: reconcile mainline architecture with constraints; historical conflict resolution untraced. |
| `docs/specs/2026-07-31-weekly-agent-workflow-automation-design.md` | 3/D | S | L5: cross-worktree sanitized session review; confidence/privacy controls untraced. |
| `docs/specs/2026-08-01-agent-validation-continuation-design.md` | 3/D | U | L5 opening: agents stopping on validation failures; which failure classes permit termination? Full policy uninspected. |
| `docs/specs/2026-08-01-concise-validation-output-design.md` | 3/D | S | L5: reduce raw success JSON noise; machine-consumer mode preservation untraced. |
| `docs/specs/2026-08-01-daily-devlog-landing-date-design.md` | 3/D | S | L5: mainline landing date prevents missed work; timezone/first-parent checks untraced. |
| `docs/specs/2026-08-01-local-cef-light-build-design.md` | 3/D | S | L5: cold worktree build cost/noisy defaults; full CEF escape hatch untraced. |
| `docs/specs/2026-08-01-orca-opencode-workflow-design.md` | 3/D | S | L5: collaborator-visible setup guide; actual Orca ownership boundary untraced. |
| `docs/specs/2026-08-01-stable-fennel-constraints-design.md` | 3/D | S | L5: terminology/identifier cleanup explicitly no semantic change; no synthetic requirement. |
| `docs/specs/2026-08-01-web-researcher-agent-design.md` | 3/D | S | L5: research need under existing deny defaults; bounded role permission trace missing. |
| `docs/specs/2026-08-02-merge-queue-agent-workflow-design.md` | 3/D | U | L5 opening: Orca sessions in separate worktrees; which queue transitions and repo identity apply? Full flow uninspected. |
| `docs/specs/2026-08-02-targeted-agent-validation-design.md` | 3/D | S | L5: focused checks with CI/high-risk safety; current exception tests untraced. |
| `docs/specs/2026-08-02-until-merged-merge-queue-design.md` | 3/D | U | L5 opening: spacecore repository identity; what establishes terminal merged state? Full polling contract uninspected. |
| `docs/specs/2026-08-02-workflow-debug-pr-landing-design.md` | 3/D | S | L5: reject direct-main landing in debug skill; safe replacement flow untraced. |
| `docs/specs/2026-08-03-hud-chrome-button-owned-padding-design.md` | 3/P | U | L5 opening: previous chrome uniformity work; which surfaces own padding versus shell height? Full layout contract uninspected. |
| `docs/specs/2026-08-03-hud-chrome-visual-uniformity-design.md` | 3/P | U | L5 opening: related single-row HUD surfaces; which natural metrics unify them? Full metric definitions uninspected. |
| `docs/specs/2026-08-04-hud-control-button-spacing-design.md` | 3/P | U | L5 opening: height-aligned chrome; which remaining inter-button gaps are removed? Full sizing contract uninspected. |
| `docs/specs/2026-08-04-hud-right-rail-transparent-strip-design.md` | 3/P | U | L5 opening: center toolbar and extended right rail; what reserve excludes transparent panel space? Full geometry uninspected. |
| `docs/specs/2026-08-05-opencode-permission-capabilities-design.md` | 3/D | U | L5 opening: fewer permission prompts; which capability guards preserve role authority? Full permission contract uninspected. |
| `docs/specs/2026-08-06-graph-sidebar-node-finder-design.md` | 2/G | S | G L1–16: single-click reveal versus double-click open and idempotent standalone Add Start. Supports G2/G5; full finder widget and camera selection assertions remain untraced. |
| `docs/specs/2026-08-06-sandbox-interaction-modes-design.md` | 3/P | U | L5 opening: three independent toolbar controls; what transition model makes modes exclusive? Full mode contract uninspected. |
| `docs/specs/2026-08-07-graph-ux-polish-design.md` | 2/G | S | G L1–16 now reads four issues: label truncation, empty finder width, neutral theme, float map-2.0 rejection. Supporting G2 solution/defect history; exact widget and restored-ID fixes/assertions not sampled. |
| `docs/specs/2026-08-07-opencode-capability-preflight-design.md` | 3/D | U | L5 opening: privileged operations routed to workers; what missing-configuration checks fail closed? Full preflight uninspected. |
| `docs/specs/2026-08-08-graph-activity-theme-panel-ux-design.md` | 2/G | S | G L1–16 now identifies theme edges, bounded full panels, dock persistence and inline titles. G2 supporting presentation context; actual geometry/theme transitions remain unknown, not a new per-issue requirement set. |
| `docs/specs/2026-08-08-graph-map-camera-isolation-design.md` | 2/G | S | G full L1–126: registered design addresses G2; stable camera restoration, per-map metadata and one-shot centering. Camera tests L71–258 inspected; Board/Graph activity identity and every teardown path not independently traced. |
| `docs/specs/2026-08-10-light-theme-layering-design.md` | 3/P | S | L5: distinguish pale surfaces with subtle layering; visual acceptance observation absent. |
| `docs/specs/2026-08-12-space-agent-live-development-reliability-design.md` | 2/A | U | L5 opening: internal OpenCode/MCP unit tools; what reconnect/live-disk invariants are required? Full session contract uninspected. |
| `docs/specs/2026-08-13-activity-camera-boundary-design.md` | 3/P | U | L5 opening: recurring camera ownership defects; which mandatory boundary prevents cross-activity access? Full invariant uninspected. |
| `docs/specs/2026-08-14-activity-aware-world-graph-exposure-design.md` | 2/G | S | G L1–16: activity sessions, not world root, own surface data; supports G1. Full graph-maps migration table distinguishes topology normalization from scene ownership. WorldData and key migration implementation/assertions not sampled. |
| `docs/specs/2026-08-14-graph-authored-agent-workflows-design.md` | 2/A | S | L5: primary graph orchestration independent of worlds/maps; workflow persistence traces missing. |
| `docs/specs/2026-08-14-workflow-user-flow-polish-design.md` | 2/A | S | L5: discover/create/edit/connect runnable workflow; end-to-end authoring definitions untraced. |
| `docs/specs/2026-08-15-explicit-graph-discovery-design.md` | 2/G | S | G full L1–134: explicit preview/search/action controls replace hidden bulk hooks, preserving owning stores. Registered design addresses G1; map capture/clear assertions sampled, workflow hierarchy-specific coverage remains with 2/A. |
| `docs/specs/2026-08-15-workflow-backed-agent-sessions-design.md` | 2/A | U | L5 opening: converge sidebar chat/workflows; what preserves session interaction continuity? Full long-lived run contract uninspected. |
| `docs/specs/2026-08-16-workflow-graph-ux-design.md` | 2/A | U | L5 opening: removal of hidden hooks; which explicit actions form editor/control surfaces? Full UX slice uninspected. |
| `docs/specs/2026-08-26-workflow-preview-decomposition-design.md` | 2/A | U | L5 opening: crowded workflow previews; which child explorer nodes own steps/runs? Full decomposition uninspected. |
| `docs/specs/2026-08-29-graph-filesystem-file-interactions-design.md` | 2/G | U | G L1–16: regular files incorrectly appeared as empty directories in original context. Explicit interaction-row architecture read in paired plan; concrete external-edit/module-action/native-reader traces remain uninspected. Reuse lazy editor/save IDs, no new file capability claim. |
| `docs/specs/2026-08-30-lazy-text-buffer-virtual-input-design.md` | 2/T | S | Task 2 full L1–276, original introduction 995ed2feeb22a71b86fe25ce396e180aa66a20b2 inspected: overlay edits, bounded viewport and explicit conflict-preserving saves. ART-dafc623b-133c-4c39-9056-0bb08134675b addresses REQ-b5e94348-9fab-4aea-9cfb-31fc6553756c / REQ-ffd79d7c-9bd7-44a1-9871-84a476629de4. Small-control compatibility and full native/widget/viewer assertions remain a concrete coverage gap. |
| `docs/specs/2026-09-07-graph-titlebar-kind-badges-design.md` | 2/G | S | G L1–16: titlebar kind metadata, compact point rendering explicitly unchanged. G1 supporting presentation refinement; fallback badge normalization/color/dialog assertions remain unknown. |
| `docs/specs/2026-09-14-reloadable-graph-node-units-design.md` | 2/G | S | G full L1–108: owner-safe loader/morph handles, rollback, visible refresh and unload preserving topology. Supports existing live-development goal/G1; concrete registry/ModuleUnit vertical test chain not sampled, no plugin security claim. |
| `docs/specs/2026-09-14-shared-text-interaction-engine-design.md` | 2/T | S | L5: expanding modal editing beyond divergent widgets; shared port contract untraced. |
| `docs/specs/2026-09-14-virtual-input-shared-input-policies-design.md` | 2/T | S | L5 opening: eager Input/InputModel accepted behavior oracle; parity surface untraced. |
| `docs/specs/2026-09-15-built-in-graph-extensions-design.md` | 2/G | S | G full L1–111: explicitly one descriptor installation mechanism, low-level loader primitive retained. G1/G7 context; catalog intentionally does not install loaders. Absence of legacy central registrar and complete family coverage not freshly proven. |
| `docs/specs/2026-09-15-graph-node-menu-separators-design.md` | 2/G | S | G L1–16 plus retained prior L1–28: general graph actions separated from node actions. Supports G5 shared action ownership; divider close/click behavior remains untraced rather than inferred from command tests. |
| `docs/specs/2026-09-15-runtime-fennel-directory-modules-design.md` | 3/P | S | L5: flat-only embedded path misses directory init modules; native launch test trace missing. |
| `docs/specs/2026-09-15-string-entity-create-child-design.md` | 2/G | S | G L1–16: child plus directed link and same-map reveal. Reuse Access/text-revision IDs and graph-capabilities later explicit partial-outcome contract. This link-created hierarchy does not establish G10 parent-associated ordered-list implementation. |
| `docs/specs/2026-09-16-bugsink-sentry-error-reporting-design.md` | 3/P | S | L1–28: entrypoint-owned native SDK reporting; no production test events; init/failure traces missing. No service contacted. |
| `docs/specs/2026-09-16-merged-pr-followup-branch-design.md` | 3/D | U | L5 opening: finishing stuck after prior merge; what stale-head evidence authorizes follow-up? Full recovery guards uninspected. |
| `docs/specs/2026-09-16-release-artifact-naming-design.md` | 3/D | U | L5 opening: split packaging names; which canonical filenames/platform mappings apply? Full naming table uninspected. |
| `docs/specs/2026-09-16-runtime-asset-overlay-design.md` | 3/P | S | L5 opening: reusable executable runtime; project/built-in overlay precedence untraced. |
| `docs/specs/2026-09-16-windows-desktop-cli-launch-design.md` | 3/P | S | L5: console-subsystem exe context; desktop/CLI output/exit behavior untraced. |
| `docs/specs/2026-09-17-graph-presentation-islands-design.md` | 2/G | S | G full L1–200: registered design addresses G3, map-owned presenter-kind state rather than domain-specific GraphView branches. Later absolute-position/aggregate force refinements retained; representative presenter/drag assertions inspected, general presenter failure matrix unknown. |
| `docs/specs/2026-09-17-ordered-thought-children-semantics-design.md` | 2/G | U | G full L1–91: registered design addresses proposed G10. Parent-associated domain lists own order, reparent preserves identity; link order/island layout/outline traversal are not substitutes. No actual association/reparent plan, implementation or test chain established; explicitly unknown rather than missing functionality asserted. |
| `docs/specs/2026-09-17-space-app-distribution-design.md` | 3/H | U | L5 opening: runtime versus default Fennel app; what distribution boundary permits independent apps? Full packaging contract uninspected. |
| `docs/specs/2026-09-18-graphical-snake-example-design.md` | 3/H | S | L5 opening: Snake engine-window example; example-specific graphics not general gameplay achievement. |
| `docs/specs/2026-09-18-snake-example-template-design.md` | 3/H | S | L5 opening: reusable app-distribution teaching example; copyable-template assertions untraced. |
| `docs/specs/2026-09-18-snake-orthographic-ui-surface-design.md` | 3/H | S | L5: custom snake/surface context; supported reusable UI surface boundary untraced. |
| `docs/specs/2026-09-23-independent-island-bodies-design.md` | 2/G | S | G L1–16 and paired plan architecture: independent absolute bodies under G3; source node is initial placement convenience only. Actual presenter fallback and old-format assertion inspected; all restore compatibility cases not sampled. |
| `docs/specs/2026-09-23-island-member-drag-handles-design.md` | 2/G | S | G L1–16 identifies accidental first-member handle and normal snap-back; paired plan specifies explicit alt-drag-end operation. G3, actual second-member drag assertion traced; full design remainder not read. |
| `docs/specs/2026-09-24-list-entity-compact-labels-design.md` | 2/G | S | G L1–16: unnamed raw IDs are presentation noise, not invalid data; paired plan preserves raw access with compact opt-out. G1-compatible refinement, not lifecycle identity-label policy. Full rendering assertions not sampled. |
| `docs/specs/2026-09-24-stale-merged-pr-recovery-design.md` | 3/D | U | L5 opening: normal push/PR path; which stale merged branch recovery is guarded? Full failure contract uninspected. |
| `docs/specs/2026-09-25-force-layout-island-behavior-design.md` | 2/G | S | G L1–16 plus retained prior L1–28: origin-versus-center and explicit-pin exceptions. Supports G3; presenter conversion and replacement pin assertions inspected, no full solver/projection correctness claim. |
| `docs/specs/2026-09-25-hostable-space-apps-design.md` | 3/H | U | L5 opening: independent apps already run; which runtime facets separate app from host? Full hosting contract uninspected. |
| `docs/specs/2026-09-25-hosted-app-scene-capabilities-design.md` | 3/H | U | L5 opening: hosted workspace apps; which app-owned scene operations and teardown guarantees apply? Full capability uninspected. |
| `docs/specs/2026-09-25-hosted-app-workspace-adapters-design.md` | 3/H | U | L5 opening: metadata-exporting runtime contract; how do HUD/canvas/scene adapters mount compositions? Full adapter contract uninspected. |
| `docs/specs/2026-09-25-temporal-ecosystem-design.md` | 3/Time | U | L5 opening: no canonical datetime facility at that time; which core semantics are intended versus later implementations? Full design uninspected. |
| `docs/specs/2026-09-25-windows-ci-local-reproduction-design.md` | 3/D | S | L1–28: guarded preflight/setup/reproduce, not broad sudo; capability wrapper trace missing. |
| `docs/specs/2026-09-26-3d-snake-scene-view-design.md` | 3/H | S | L5 opening: host.scene-backed next Snake slice; example coverage not shared-world gameplay proof. |
| `docs/specs/2026-09-26-hosted-app-command-surface-design.md` | 3/H | U | L5 opening: inspector snapshot context; what generic execute/describe contract is added? Full command surface uninspected. |
| `docs/specs/2026-09-26-hosted-app-inspector-panel-design.md` | 3/H | U | L5 opening: mounted apps/shared capabilities; what stays read-only in inspectors? Full snapshot boundary uninspected. |
| `docs/specs/2026-09-26-temporal-calendar-periods-design.md` | 3/Time | U | L5 opening: exact primitives already present; which civil period operations preserve exact Duration? Full arithmetic contract uninspected. |
| `docs/specs/2026-09-26-temporal-intervals-design.md` | 3/Time | U | L5 opening: layered temporal foundation; what half-open interval/finite-repeat bounds apply? Full interval contract uninspected. |
| `docs/specs/2026-09-26-temporal-parsing-recurrence-design.md` | 3/Time | U | L5 opening: native core/Lua foundation; which parsing layers remain independent of core? Full facade contract uninspected. |
| `docs/specs/2026-09-27-hosted-app-command-confirmations-design.md` | 3/H | U | L5 opening: forms and command rows exist; what metadata and two-step execution guarantees are required? Full confirmation contract uninspected. |
| `docs/specs/2026-09-27-hosted-app-command-controls-design.md` | 3/H | U | L5: generic execution surface exists; how do visual controls bind without app-specific APIs? Full controls contract uninspected. |
| `docs/specs/2026-09-27-hosted-app-command-payload-forms-design.md` | 3/H | U | L5 opening: metadata rows with Run controls; which scalar types/validation rules form payloads? Full schema uninspected. |
| `docs/specs/2026-09-27-hosted-async-command-progress-design.md` | 3/H | U | L5 opening: existing confirmation/forms; what async cancellation/cleanup preserves synchronous behavior? Full lifecycle uninspected. |
| `docs/specs/2026-09-27-hosted-command-history-design.md` | 3/H | U | L5 opening: metadata/forms/confirmation context; what history retention and session bounds apply? Full history contract uninspected. |
| `docs/specs/2026-09-27-hosted-command-result-ux-design.md` | 3/H | U | L5 opening: result-capable controls context; what double-run/busy guarantees apply? Full state contract uninspected. |
| `docs/specs/2026-09-27-temporal-expression-projection-design.md` | 3/Time | S | L5 opening: exact context reference support; explicit-zone projection tests untraced. |
| `docs/specs/2026-09-27-temporal-interval-period-endpoints-design.md` | 3/Time | S | L5 opening: ISO-style interval endpoint forms; supported plain versus zoned corpus untraced. |
| `docs/specs/2026-09-27-temporal-monthly-yearly-recurrence-design.md` | 3/Time | S | L5 opening: bounded monthly/yearly occurrences; invalid-date semantics untraced. |
| `docs/specs/2026-09-27-temporal-rrule-bymonth-design.md` | 3/Time | S | L5 opening: bounded BYMONTH addition; filter/generator distinction untraced. |
| `docs/specs/2026-09-27-temporal-rrule-bymonthday-design.md` | 3/Time | S | L5: existing bounded frequencies and plain candidates; positive month-day filter trace missing. |
| `docs/specs/2026-09-27-temporal-rrule-bymonthday-generator-design.md` | 3/Time | S | L5: filter-only underpowers monthly/yearly rules; generation versus filtering tests untraced. |
| `docs/specs/2026-09-27-temporal-rrule-until-bound-design.md` | 3/Time | S | L5: parsed UNTIL ignored in expansion; retained defect/repair assertions untraced. |
| `docs/specs/2026-09-28-hosted-app-launcher-node-design.md` | 3/H | U | L5 opening: host runtime/mount/controls exist; what selected filesystem app can graph launcher execute? Full launch contract uninspected. |
| `docs/specs/2026-09-28-sdk-docs-design.md` | 3/H | S | L5: SDK for ecosystem builders beyond core contributors; builder-path navigation untraced. |
| `docs/specs/2026-09-28-sdk-module-reference-design.md` | 3/H | S | L5: module/import/API/error reference focus; actual public export completeness untraced. |
| `docs/specs/2026-09-28-temporal-complete-library-design.md` | 3/Time | S | L5: complete production platform, not deferred layers; broad original intent must be compared to bounded closeout in Task 3. |
| `docs/specs/2026-09-28-temporal-dependency-data-packaging-foundation-design.md` | 3/Time | S | L5: dependency metadata/data directories before large standards snapshots; runtime corpus trace missing. |
| `docs/specs/2026-09-28-temporal-provider-registry-design.md` | 3/Time | S | L5: deterministic trusted local registry before broad providers; trust/ordering tests untraced. |
| `docs/specs/2026-09-28-temporal-rfc5545-recurrence-design.md` | 3/Time | U | L5 opening: foundation and registry landed claim; which full in-scope RFC clauses are accepted? Full recurrence scope uninspected. |
| `docs/specs/2026-09-28-temporal-rrule-byday-generator-design.md` | 3/Time | S | L5: monthly/yearly non-ordinal BYDAY rejection context; generator behavior tests untraced. |
| `docs/specs/2026-09-29-opencode-ci-diagnostics-tooling-design.md` | 3/D | U | L5 opening: two PR191 diagnostics blockers; which log/bootstrap contract resolves them? Full blocker evidence uninspected. |
| `docs/specs/2026-09-30-temporal-full-iso-intervals-design.md` | 3/Time | U | L5 opening: landed provider/RFC layers claim; which ISO endpoint corpus and DST policies apply? Full selected Track 6 uninspected. |
| `docs/specs/2026-09-30-temporal-recurrence-set-zoned-design.md` | 3/Time | U | L5 opening: previous temporal tracks claim; which set assembly/zone ambiguities are bounded? Full set contract uninspected. |
| `docs/specs/2026-10-01-extensible-leader-command-system-design.md` | 2/G | S | G full L1–141: registered design addresses G5, contextual providers/declarative keys/shared hints and selection-only preview target. Actual provider and keymap/hint assertions sampled; complete input dispatch untouched/unexecuted. |
| `docs/specs/2026-10-01-graph-enter-preview-design.md` | 2/G | S | G L1–16: focused Enter should match compact double-click preview intent, full view stays explicit. Supports G5 interaction context; paired plan explicitly idempotent. Actual focus activation assertions untraced. |
| `docs/specs/2026-10-01-temporal-business-calendar-design.md` | 3/Time | S | L5: deliberately small holiday corpus despite category closeout; broad completeness cannot follow. Corpus tests untraced. |
| `docs/specs/2026-10-01-temporal-ics-icalendar-design.md` | 3/Time | U | L5 opening: previous recurrence/interval tracks claim; which VEVENT fields and unsupported forms are explicit? Full ICS corpus uninspected. |
| `docs/specs/2026-10-01-temporal-localization-calendar-design.md` | 3/Time | U | L5 opening: previous temporal layers claim; which locale/calendar seed versus full CLDR breadth is intended? Full corpus uninspected. |
| `docs/specs/2026-10-01-temporal-migrations-design.md` | 3/Time | S | L5: timestamp schema inventory with one workflow store integration; non-workflow migrations remain untraced. |
| `docs/specs/2026-10-01-temporal-natural-language-design.md` | 3/Time | S | L5: deterministic candidates/ambiguity/context diagnostics; three-locale breadth versus general NLP untraced. |
| `docs/specs/2026-10-02-runtime-scheduler-design.md` | 3/Time | S | L5: typed Fennel scheduling surface; scheduler/timer ownership tests untraced. |
| `docs/specs/2026-10-02-snackbar-system-design.md` | 3/P | S | L5: reusable brief actionable feedback across HUD/independent apps; policy/lifetime tests untraced. |
| `docs/specs/2026-10-03-graph-selection-leader-commands-design.md` | 2/G | S | G L1–16 and full leader feature: focused selection select/add/remove/toggle/clear are distinct from selected previews. G5; actual availability assertions inspected, native selector integration still representative-depth gap. |
| `docs/specs/2026-10-03-temporal-closeout-design.md` | 3/Time | S | L5: bounded closeout explicitly excludes ecosystem equivalence/full standards; authority to narrow earlier intent not established. |
| `docs/specs/2026-10-04-graph-leader-command-expansion-design.md` | 2/G | S | G L1–16 and full leader feature: focused actions, view navigation and map operations extend existing p/s namespaces. G5 includes declared-context non-destructive commands; complete numeric/menu/map command assertions not sampled. |
| `docs/specs/2026-10-04-ssh-integration-foundation-design.md` | 3/N | S | L5 opening: reusable SSH foundation for ecosystem; native backend/platform scope untraced. |
| `docs/specs/2026-10-05-focus-start-node-command-design.md` | 2/G | S | G L1–16 and graph-maps L594–596: reuse Add Start before reveal, not a new automatic seed. G5 c3; end-to-end command camera assertion not newly inspected. |
| `docs/specs/2026-10-05-opencode-fast-development-flow-design.md` | 3/D | U | L5 opening: strict workflow context; which interactive exemptions retain safeguards? Full original lane uninspected. |
| `docs/specs/2026-10-05-ssh-real-backend-validation-design.md` | 3/N | S | L5: close validation gap after SSH foundation; actual backend observations not inferred from definitions. |
| `docs/specs/2026-10-06-fast-dev-local-main-wrap-up-design.md` | 3/D | U | L5 opening: first interactive implementation context; which old local-main path remains applicable? Full later policy comparison needed. |
| `docs/specs/2026-10-06-string-entity-text-search-design.md` | 2/G | S | G full L1–249 plus full feature: registered design addresses G6; persisted Markdown, literal ignore-case ripgrep and runtime-only query/results. Backend/node actual options/stale/capture assertions traced. Nonvisual capability search remains deliberately case-sensitive and separate. |
| `docs/specs/2026-10-07-hierarchical-focus-navigation-design.md` | 3/P | S | L5: focus nodes/scopes and flat traversal context; hierarchical entry/exit tests untraced. |
| `docs/specs/2026-10-07-local-build-broker-design.md` | 3/D | S | L5: explicitly design-only future local architecture; remains proposed, no implementation inferred. |
| `docs/specs/2026-10-08-graph-outline-view-design.md` | 2/G | S | G full L1–147: registered design addresses G4; outgoing DFS/first occurrence over visible map edges, not domain child order. Actual pure projection and root/cycle assertions traced; complete renderer interaction/reload proof not claimed. |
| `docs/specs/2026-10-08-windows-ci-speedups-design.md` | 3/D | S | L5: speed without losing confidence/packaging; actual timing and release guarantees untraced. |
| `docs/specs/2026-10-09-github-workflow-cleanup-design.md` | 3/D | U | L7 opening: existing root workflow coverage; what permission/trust/pin invariants are strengthened? Full contract uninspected. |
| `docs/specs/2026-10-09-outline-compact-projection-design.md` | 2/G | S | G L1–16 plus paired plan scope/current doctrine: row rectangles caused interaction drift; compact points own interaction. G4 c3 retains refinement; complete hit-target/teardown and visual matrix not sampled. |
| `docs/specs/2026-10-09-windows-main-ci-design.md` | 3/D | U | L7 opening: combined Linux/Windows test context; what post-merge/manual coverage replaces queue coverage? Full workflow boundary uninspected. |
| `docs/specs/2026-10-11-dict-entity-design.md` | 2/G | S | G full L1–190: registered design addresses G8, keyed references not inline scalars. JSON reload/mutation/error/no-op assertions sampled and store paths inspected; later normalization/deletion uses G9 instead of repeating obsolete physical-delete naming. |
| `docs/specs/2026-10-11-graph-projection-runtime-design.md` | 2/G | S | G full L1–157: registered design addresses G2; common lifecycle/camera mechanism with separate mode state, map selection ownership unchanged. Runtime and camera test definitions sampled, whole activity/teardown surface not proven. |
| `docs/specs/2026-10-11-opencode-mcp-bridge-core-design.md` | 2/A | S | L14 opening: duplicated bridge mechanism in three clients; policy-neutral extraction regression traces missing. |
| `docs/specs/2026-10-12-outline-marker-box-design.md` | 2/G | S | G L1–16: stable compact marker footprint prevents focus/selection height shifts without uniform row height. G4 supporting visual refinement; marker measurement/glyph/layout assertions not independently traced. |
| `docs/specs/2026-10-12-tree-view-outline-design.md` | 2/G | S | G L1–16: measured reusable widget, graph-owned roots/selection/interaction remain separate. G4 supporting layout refinement, generic TreeView belongs to platform; no fixed-stride preservation or new hierarchy inferred. |
| `docs/specs/2026-10-14-entity-type-catalog-design.md` | 2/G | S | G full L1–118 and full feature: registered design addresses G7; immutable browsable metadata, separate loader installation, same injected code store. Actual catalog validation/order/copy assertions traced; full startup/browser callback matrix remains untraced. |
| `docs/specs/2026-10-15-fast-dev-independent-workflow-design.md` | 3/D | S | L5 opening: efficient user-selected interactive development; direct edit/review/publication boundaries untraced. |
| `docs/specs/2026-10-15-live-dev-design.md` | 3/D | S | L5 opening: user-selected live primary; verified checkout/manual refresh tests untraced. |
| `docs/specs/2026-10-15-reference-lifecycle-design.md` | 2/G | S | G full L1–251 plus original f2002a60 Git object and full feature: registered design addresses G9. Owning normalization, transitive incoming cleanup, source-last morph and no-write map presentation. Coordinator/closure/alias/history assertions sampled; world/board/recovery/preview matrix explicitly not exhaustive. |
| `docs/specs/2026-10-15-reload-boundary-contract-design.md` | 3/P | S | L5 opening: dependable whole-app reload plus future boundaries; narrow-unit readiness untraced. |
| `docs/specs/2026-10-15-uniform-graph-access-design.md` | 2/G | S | Retain predecessor full L1–193, original545f36051effc5fe73cb3fcca34e1be58c2097ff and all existing Access/Isolation/revision IDs/artifacts. G independently reread original no-dereference slice; full feature L362–381 and original13d86a985c8e9faea3154c9bffc719c7b09b85af amendment explicitly extend DTO resolution, supported by lifecycle design/plan. Actual L292–338 alias/raw-byte assertions confirm definitions, not execution; historical scope is not rewritten. |
| `docs/specs/2026-10-16-secure-record-publication-design.md` | 3/N | S | L5 opening: user-authorized native Windows overwrite correction; private publication invariants untraced. |
| `docs/specs/2026-10-16-windows-validation-diagnostics-design.md` | 3/D | S | L5 opening: failing cross-build diagnosis authorization; contamination-free evidence untraced. |
| `docs/specs/2026-10-16-wine-suite-lifecycle-design.md` | 3/D | S | L5 opening: artifact-safe instrumented reproduction at 9b261b0; finite budget/cleanup evidence untraced. |
| `docs/specs/2026-10-17-wine-native-failure-diagnostics-design.md` | 3/D | S | L5 opening: safe e4185c0 build/package/admission report; root cause assertions need original evidence. |
| `docs/specs/2026-10-17-wine-posix-publication-design.md` | 3/N | S | L5 opening: real persistent publication, not mocks; actual Wine observations untraced. |
| `docs/specs/2026-10-20-devlog-branch-capability-design.md` | 3/D | S | L5: missing exact branch capability after safe preflight; branch guard assertions untraced. |
| `docs/specs/2026-10-20-guarded-merge-policy-design.md` | 3/D | S | L5: helper cannot prove PR/method despite authentication/queue; authority query tests untraced. |
| `docs/specs/2026-10-21-devlog-gap-backfill-design.md` | 3/D | S | L5: first-parent landing history with immutable published entries; exact historical 41-entry scope not a new target. |
| `docs/specs/2026-10-21-sse-closure-finalizers-design.md` | 3/N | S | L5 opening: user-reported native SSE shutdown abort; GC/shutdown regression tests untraced. |
| `docs/specs/2026-10-22-checkpoint-review-ownership-design.md` | 3/D | S | L5 opening: assigned local checkpoints; checkpoint-versus-approval guards untraced. |
| `docs/specs/2026-10-23-daily-devlog-catch-up-design.md` | 3/D | S | L5 opening: recover meaningful uncovered development; latest-entry cutoff tests untraced. |
| `docs/specs/2026-10-24-wine-test-child-launch-design.md` | 3/D | S | L5 opening: narrow Wine POSIX acceptance extension; child environment boundary untraced. |
| `docs/specs/2026-10-25-current-layout-boundary-diagnostic-design.md` | 3/D | S | L5 opening: bounded graph/publication diagnostic transition; current-source timing observation untraced. |
| `docs/specs/2026-10-25-glm-default-expert-consultation-design.md` | 3/D | S | L5 opening: original cost-optimization model choice; compare later routing before any authority conclusion. |
| `docs/specs/2026-10-25-interactive-canonical-candidates-design.md` | 3/D | S | L5 opening: usable stopping point and documented follow-ups; timeout evidence versus completion untraced. |
| `docs/specs/2026-10-25-opencode-model-pilot-design.md` | 3/D | S | L5 opening: compare model judgment/implementation; real evaluation evidence not inferred. |
| `docs/specs/2026-10-26-opencode-session-graph-exposure-design.md` | 2/A | S | L1–28: server owns data, bounded lazy snapshots plus subagents/streaming roadmap; SSE captures and final full-range review untraced. |
| `docs/specs/2026-10-29-autonomous-handoff-recovery-design.md` | 3/D | S | L5 opening: controller-owned delivery recovery; immutable ancestry/replacement assessment guards untraced. |
| `docs/specs/2026-10-29-model-neutral-agent-routing-design.md` | 3/D | S | L5 opening: requested routing for 17 roles; authoritative frontmatter/current snapshot tests untraced. |
| `docs/specs/2026-10-29-requirements-driven-engineering-design.md` | 3/D | R | L5 opening plus existing registry/governing methodology guide: reuse ART-7121890a-8068-4b53-ba47-3c4eb4d98687 and revision-1 methodology requirements; not product coverage. |
| `docs/specs/2026-10-30-autonomous-workflow-decisions-design.md` | 3/D | S | L5 opening: explicit journal-correction authority; earlier immutable-publication rule cannot be resolved from filenames alone. Full reconciliation belongs to Task 3. |

## Exhaustive documentation-family membership and inspection bounds

Membership is every tracked descendant at F of the stated directory, unless “direct” is specified. Counts include non-Markdown files and indexes; these disjoint rows sum to **1,201** frozen docs files. Counting every filename is not line-by-line semantic review. Later tasks own deeper inspection; Task 4 owns cross-family consistency and the final all-family second sweep.

| Family membership | Frozen files | Task 1 semantic depth / uninspected bounds | Follow-up owner |
| --- | ---: | --- | --- |
| `docs/` direct files | 4 | package.json read; index, package-lock and .gitignore filename inventory only. Home navigation/build policy not re-audited. | 4 |
| `docs/.vitepress/` | 3 | Config/theme filenames only; routing/render semantics uninspected. | 4 |
| `docs/dev/` direct files | 23 | 21 Markdown files + 2 images. No full review of direct subsystem/lifecycle/runtime guides; methodology located in features below. Includes lifecycle-hardening-plan outside the canonical plans directory. | 3, graph maps to 2 |
| `docs/dev/adrs/` | 7 | Graph exposure ADR read in full; other six filenames only. Historical architecture decisions do not prove current behavior. | 2 graph, 3 platform |
| `docs/dev/features/` | 61 | Includes root index, hence **60 bodies**, not 61 bodies. Four goal pages and index read fully; methodology guide read fully. Remaining 55 bodies are filename inventory only. Index itself lists a subset, so directory membership—not navigation links—is denominator. | 2 graph/agents/text; 3 remainder |
| `docs/dev/fennel/` | 9 | Filenames only; style/lifecycle guidance not used to authorize Fennel edits. | 3 |
| `docs/dev/journal/` | 70 | Filenames only, including any index; no historical test claims promoted to fresh observations. Narrative history is descriptive evidence requiring source checks. | 3 dev workflow, 4 consistency |
| `docs/dev/notes/` | 99 | Filenames only, including indexes; graph/terrain/agent/security and other notes require original-text follow-through by family owners. No normative inference from note titles. | 2/3 by subject |
| `docs/dev/openai/` | 410 | All descendant filenames counted; third-party API mirror/reference, not independent Space intent. API body semantics uninspected. | 2 agent/API context only |
| `docs/dev/project/` | 26 | Five direct pages read fully; 12 milestone bodies + index read fully. Four bug-family files and four tech-debt-family files (each including index) filename-only. Their concrete defect obligations need source reconciliation, not automatic creation. | 2/3 by defect, 4 consistency |
| `docs/dev/reports/` | 1 | Agent-workflow report index filename only; no evaluation conclusions inferred. | 3 |
| `docs/dev/subsystems/` | 9 | Filenames only including index; eight subsystem contracts need targeted native/Fennel inspection. | 3 |
| `docs/dev/zai/` | 1 | Provider reference filename only; external API material, not Space authority. | 2 context only |
| `docs/plans/` | 195 | Root generated index excluded from 194-row manifest above. Opening Goals/progress identity snippets only, exact per-row gaps retained. | 2/3 row owners |
| `docs/specs/` | 169 | Root generated index excluded from 168-row manifest above. Opening context/intent only except seven explicitly deeper L1–28 reads; not full normative coverage. | 2/3 row owners |
| `docs/requirements/` | 9 | Canonical 12 requirement bodies, 26 artifact identities and shared bounded query context inspected. Existing seven evidence/audit Markdown pages not semantically rereviewed; index is a projection, not a fresh result. This row describes F, not the three new baseline pages. | 4, all tasks reuse canonical records |
| `docs/scripts/` | 13 | Filenames plus package script entrypoints inspected; implementation not changed or audited. Generator will run under existing command. | 4 |
| `docs/sdk/` | 83 | All Markdown: 61 module-family, 8 reference-family, 6 guide-family, 4 tutorial-family, 1 examples index and 3 direct pages. Root index read fully; all remaining bodies filename-only. Stability/version policy explicitly undefined; do not invent guarantees. | 3 host/runtime; 2 graph/workflow/API |
| `docs/user/` | 9 | Two direct pages + seven workflow-family pages including index. Root index read fully; quick start and workflow procedures filename-only. User flows are candidates for focused test tracing, not observed runs. | 2 workflows, 3 installation |

Goal/milestone source decisions are recorded in the consolidated audit: README positioning, four goal bodies and 12 milestone bodies are semantic top-down coverage; other filename families have explicitly limited depth. No “historical/replaced” label was assigned from an unread source. The source-disposition S/U split intentionally preserves unresolved applicability instead of manufacturing a canonical requirement for every document.

## Implementation, tests, assets and infrastructure inventory

Every tracked non-doc path at F belongs to one of the following disjoint root memberships. These are **filename inventory only**, not implementation/test coverage or a new normative hierarchy. No code or test body was audited in Task 1. Tests were not run against the application. Family owners must inspect real exports, ownership, persistence and assertions before registering trace artifacts.

| Root membership | Files | Subfamilies / authority and follow-up bounds |
| --- | ---: | --- |
| `src/` | 203 | 198 direct native files, 4 realtime, 1 profiler. Canonical C++ implementation evidence; 3 owns native/platform, 2 follows its binding surfaces. |
| `apps/` | 3 | space executable/host scaffolding. Canonical runtime evidence, Task 3. |
| `assets/` | 2441 | lua 1519 (1417 .fnl + one partial-addition filename, 3 .lua, 11 JSON, 1 Markdown, 59 PNG, 17 ICS, 10 MP4); python 233 historical prototypes excluded from normative authority; seed 552; data 23; temporal 12; shaders 33; models 2; pics 2; skyboxes 12; sounds 4; tree-sitter 10; material icons 12; emoji 3; fonts 24. Fennel tests/constraints live inside lua membership. Task 2 graph/agents/text, Task 3 rest; partial-addition filename is inventory, not claimed runnable code. |
| `tests/` | 41 | 40 direct files + one CMake fixture. Definitions/registration only until Task 3 inspection; no run or conformance inferred. |
| `scripts/` | 172 | 62 direct, evals 1, requirements_lib 8, tests 55, vcpkg ports 35/triplets 2, Wine 9. CLI/library/test entrypoints used under existing contract, not audited as product behavior. Tasks 3/4. |
| `examples/` | 12 | Snake teaching app; incidental examples are not independent product authority. Task 3. |
| `external/` | 9992 | Vendor content; excluded from independent Space intent. Conditional backends must be traced from Space configuration. |
| `ffi/` | 5 | Native/foreign support evidence only; Task 3 follows platform/API availability. |
| `cmake/` | 7 | Build/package support evidence, Task 3. |
| `.github/` | 8 | CI declarations, not live CI results. Task 3. |
| `.opencode/` | 46 | 17 project roles, 28 skill files, 1 direct file. Read-only development workflow evidence distinct from application agents; no prompt edits. Task 3. |
| `.superpowers/` | 3 | Workflow metadata/templates; not product intent or canonical goal hierarchy. No private payload registration. |
| `.vscode/` | 1 | Editor configuration, descriptive only. |
| `archived/` | 1 | Historical archived source, no independent current obligation. |
| `pod/` | 2 | Service-related implementation evidence only; does not activate M11. Task 3. |
| root files (no slash) | 7 | .gitattributes, .gitignore, AGENTS.md, CLAUDE.md, CMakeLists.txt, Makefile, README.md. README read fully; existing instructions govern audit, build declarations are not runtime verification. |

Added after F, outside the 362 frozen-row denominator: the baseline governing design, implementation plan and controller-owned progress record; this audit, source-disposition page and Task 1 report. Root spec/plan indexes are regenerated, not additional source records. No hidden automatic migration or completion inference is made for these additions.
