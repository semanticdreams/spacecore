# Devlog

## 2026-10-22
Strict agent work now separates [local checkpoints from independent approval](/dev/features/opencode-agent-workflow#strict-flow-checkpoint-and-review-ownership): implementers can checkpoint validated tasks and fixes, while complete change ranges still require review before completion or publication. Daily and weekly automation retain their stage-only, review-first handoffs, keeping unattended publication safeguards intact as ordinary iteration becomes more direct.

## 2026-10-21
Scheduled devlog automation can now prepare its writing branch through a [guarded capability](/dev/features/opencode-agent-workflow#strict-daily-devlog-branch-preparation) that pins freshly fetched `origin/main`, derives the UTC-dated branch internally, and fails closed on collisions or ambiguous safety evidence rather than resetting existing work. This removes a branch-creation blocker without broadening Git permissions, while keeping reviewed writing and publication as separate steps.

## 2026-10-20
The [guarded merge-policy proof](/dev/features/opencode-agent-workflow#guarded-merge-policy-proof) began requiring complete paginated branch rules, PR protection, the exact required test check and a compatible queue method before publication. Auto-merge requests leave strategy selection to GitHub's verified queue policy; incomplete or malformed evidence blocks the request, and polling must still establish an actual merge.

## 2026-10-17
[Reference lifecycle coordination](/dev/features/reference-lifecycle) moved normalization into owning stores and made logical deletion and string-to-code morphs resumable across domain records and their presentations. Frozen pending intents preserve recovery work and detect conflicting edits; they do not make multiple files atomic. Preview cleanup also moved to single-owner teardown, avoiding repeated drops during these transitions.

## 2026-10-15
An immutable [entity-type catalog](/dev/features/entity-type-catalog) unified browser metadata, with application composition supplying stores and map-local loaders opening each type. [Live development](/dev/features/live-dev) gained checkout-scoped instance discovery and explicit watcherless reloads under process-owned control. Health checks and restart-required boundaries kept refresh outcomes visible instead of treating an accepted request as a successful reload.

## 2026-10-12
A shared [graph projection runtime](/dev/graph-maps) consolidated capture, restoration and teardown across spatial and outline views. The reusable [TreeView widget](/dev/features/tree-view-widget) measured row heights so inline content could expand without fixed spacing assumptions. Targeted PR validation separated docs-only changes, asset changes using a trusted prebuilt runtime, and changes requiring native builds.

## 2026-10-11
[Dictionary entities](/dev/notes/dict-entities) added persistent named reference slots alongside ordered lists, with graph browsing and editing for keyed collections. The [OpenCode MCP bridges](/dev/notes/remote-mcp) also gained shared server and configuration lifecycle machinery, while agent, external-unit and validation surfaces retained separate tool registries and permission policies rather than inheriting one another's authority.

## 2026-10-10
Spatial and [outline projections](/dev/graph-maps#outline-mode) began sharing a compact-node lifecycle for clicking, selection, focus, activation and teardown, rather than giving outline rows a parallel interaction system. Outline activation could expand content inline, and collapsing it returned focus to the compact node instead of stranding it inside a removed preview.

## 2026-10-09
[Outline interaction](/dev/graph-maps#outline-mode) moved closer to spatial behavior: clicks changed focus without replacing selection, selector state stayed synchronized, and rebuilds respected focus held by outside controls. [CI responsibilities](/dev/notes/github-actions-hygiene) also became clearer, separating the Linux PR gate from Windows main-branch validation and centralizing release publication instead of letting builders race.

## 2026-10-08
[Outline mode](/dev/graph-maps#outline-mode) introduced a second projection of the active map, traversing visible outgoing edges from chosen roots without expanding hidden domain relationships. Unreachable nodes stayed in the map for spatial use, while visible select-all and shared focused actions began carrying graph interaction into the new presentation.

## 2026-10-07
[Hierarchical focus navigation](/specs/2026-10-07-hierarchical-focus-navigation-design) added explicit movement into and out of nested controls, with sibling traversal scoped to the current level rather than flattening the whole interface. Normal builds also began refreshing copied runtime assets even when the executable needed no relink, so asset-only fixes would reach the built app.

## 2026-10-06
[Full-text search](/dev/features/string-entity-full-text-search) made string entities discoverable by content through asynchronous, case-insensitive literal matching confined to their Markdown store. Opening a result materialized only the chosen entity in the active map, keeping temporary queries and result rows out of persisted topology and avoiding invented domain relationships.

## 2026-10-05
[SSH integration](/dev/subsystems/ssh#current-status-and-future-work) gained real-backend fixture coverage and SDK examples, with cancellation waiting for remote readiness rather than racing command startup. Interactive shell round trips remained quarantined behind an opt-in switch. A focus-start command restored a graph navigation anchor, while the initial [fast-development flow](/dev/features/opencode-agent-workflow#fast-interactive-development-flow) offered smaller reviewed iterations without replacing the strict supervisor.

## 2026-10-04
New [graph map commands](/dev/graph-maps#leader-map-commands) could create empty maps, copy selected topology and clear a workspace without deleting its backing objects. The [SSH foundation](/dev/subsystems/ssh) introduced backend-neutral asynchronous operations with explicit host-key decisions, cancellation and structured failures, opening a remote-control path without exposing transport-library handles to application code.

## 2026-10-03
Temporal closeout added cross-surface smoke coverage and documented the [supported acceptance boundary](/dev/features/temporal-complete-acceptance), keeping seed corpora and unsupported calendar behavior explicit rather than claiming ecosystem-wide completeness. [Scoped snackbars](/dev/features/snackbar-system) brought transient HUD feedback, while focused-node selection commands separated keyboard focus from the selection being edited.

## 2026-10-02
Workflow persistence moved to canonical UTC timestamp strings through [explicit migration boundaries](/dev/features/temporal-migrations), retaining legacy integer-second reads without a blanket startup rewrite. A [runtime scheduler](/dev/features/runtime-scheduler) connected typed durations and bounded, explicitly zoned recurrence to cancellable callbacks, giving hosted apps scheduling that follows runtime advancement rather than mixing wall-clock timestamps with elapsed timers.

## 2026-10-01
The [temporal library](/dev/features/temporal) gained bounded iCalendar interchange, seed-backed localization and business calendars, plus natural-language candidates that require explicit context rather than guessing dates. Alongside that calendar work, [contextual leader commands](/dev/features/leader-command-system) made graph actions discoverable through extensible command providers instead of a fixed shortcut table.

## 2026-09-30
[Recurrence sets](/dev/features/temporal-parsing-recurrence#recurrence-sets-and-zoned-expansion) now combine inclusions and exclusions before resolving occurrences through an explicit timezone and daylight-saving policy. Expanded [interval semantics](/dev/features/temporal-intervals) preserve the distinction between exact-duration and calendar-period steps across clock changes, giving time-aware apps a firmer basis for repeated spans without assuming full calendar-file interoperability.

## 2026-09-29
[Guarded CI diagnostics](/dev/features/opencode-agent-workflow#guarded-ci-log-diagnostics) now expose bounded log searches and failure bundles, with stronger Windows reproduction support to make cross-platform failures easier to investigate. Source-path normalization repairs app discovery across path conventions, while island drag completion now preserves an already-running force layout instead of interrupting it.

## 2026-09-28
The new [SDK documentation](/sdk/) connects app-building guides to module references, while a graph launcher brings source apps into the hosted workspace. Temporal provider registration creates an extension seam, and [RRULE expansion](/dev/features/temporal-parsing-recurrence) now handles richer candidate sets for plain date-times. Dependency manifests prepare later integrations; they do not yet deliver the external libraries those integrations need.

## 2026-09-27
The [hosted command workbench](/dev/features/hosted-runtime-apps) now turns command metadata into payload forms and confirmations, with readable results and cancellable asynchronous progress. A bounded, session-local recent-runs history makes those interactions traceable without implying durable background jobs. Meanwhile, [monthly and yearly recurrence](/dev/features/temporal-parsing-recurrence) gained date selectors and finite end bounds, making more calendar patterns expressible without broad natural-language guessing.

## 2026-09-26
[Hosted apps](/dev/features/hosted-runtime-apps) gained owned scene handles and a workspace inspection and command surface, so tools can observe and control an app without reaching into raw scene objects. Above the temporal core, [strict parsing and bounded recurrence](/dev/features/temporal-parsing-recurrence) now connect text to typed values. Interval arithmetic and calendar periods extend that foundation while keeping elapsed time distinct from calendar movement.

## 2026-09-25
Apps can now use the same composition factory [standalone or hosted inside Space](/dev/features/hosted-runtime-apps), receiving services from the host rather than taking over the workspace engine. The new [temporal core](/dev/features/temporal) similarly makes context explicit through typed instants, elapsed durations and zoned values, laying groundwork for time-aware tools without relying on the machine's local timezone.

## 2026-09-24
Dragging an ordered-list member with Alt now moves its whole [presentation island](/dev/graph-maps#presentation-islands), and force layout treats unpinned members as one aggregate body. Explicitly pinned members keep their positions, letting grouped content participate in map arrangement without discarding the user's local anchors.

## 2026-09-23
[Presentation islands](/dev/graph-maps#presentation-islands) now retain their own absolute positions instead of being re-anchored to the list node that created them. Refreshing list membership preserves that placement, so an arranged group can stay where the user put it while its source remains elsewhere on the map.

## 2026-09-18
Snake became a graphical example of the [app distribution path](/dev/features/app-distribution), connecting a playable board to a reusable release template. Its [orthographic UI surface](/dev/features/orthographic-ui-surface) presents normal retained widgets with upright text and viewport-scaled layout without importing the product HUD, giving small apps a lighter starting point.

## 2026-09-17
Ordered lists can now appear as persisted [presentation islands](/dev/graph-maps#presentation-islands), arranging graph members together without transferring ownership of their underlying records. Alongside that richer workspace presentation, a reusable [app bundle workflow](/dev/features/app-distribution) packages independent Fennel apps against a pinned Space release, opening a distribution path that does not rebuild the engine in each app repository.

## 2026-09-16
Ordered [asset overlays](/dev/notes/runtime-asset-overlays) now let project modules override packaged defaults while retaining fallback discovery, giving independent apps a practical runtime layout. Separate Windows GUI and console launch modes support desktop use and command-line tooling. Explicitly initialized [error reporting](/dev/features/error-reporting) adds a diagnostic foundation for runtime failures as those packaging paths expand.

## 2026-09-15
[Reloadable graph extensions](/dev/features/reloadable-graph-extension-units) can refresh visible adapters without restarting the app root, with owner-safe registration and rollback keeping failed reloads from leaving stale hooks. Built-in node families now use the same descriptor lifecycle, while store-backed child creation keeps domain records separate from their map presentation, giving extension work a clearer ownership boundary.

## 2026-09-14
Small inputs and file-backed editors now share a [text command engine](/dev/features/shared-text-interaction-engine), including forward word motion, instead of maintaining separate modal command behavior. Shared [interaction policies](/dev/features/text-input-policies) align focus, caret and pointer geometry while leaving lazy storage behind its own adapter, so consistency does not require loading large files into memory.

## 2026-09-10
Ordinary movement in the [lazy editor](/dev/features/lazy-text-buffer-virtual-input#virtualinput-widget) now resumes from cached cursor and viewport anchors, so navigation far into long files need not repeatedly rediscover the prefix. Exact commands such as jumping to the document end can still scan, preserving their meaning without imposing that cost on every adjacent move.

## 2026-09-07
Kind badges now distinguish [graph nodes](/dev/notes/graph) beside their titles in cards and dialogs, making mixed maps easier to read. Clicking into the [lazy editor](/dev/features/lazy-text-buffer-virtual-input) targets the editor rather than its surrounding dialog, and text events insert only in insert mode, making the transition from browsing to editing more predictable.

## 2026-09-06
The [lazy file editor](/dev/features/lazy-text-buffer-virtual-input#virtualinput-widget) gained modal movement and insertion with UTF-8-safe navigation, bringing familiar editing gestures to file-backed text. Viewport-aware clipping and caret scrolling keep the active edit visible in narrow containers without turning the document into an eager text widget.

## 2026-08-30
[Lazy text editing](/dev/features/lazy-text-buffer-virtual-input) replaces yesterday's read-only window viewer with a piece-table buffer, sparse line indexing and viewport-sized rendering instead of loading an entire file into an ordinary text control. Explicit saves check for external changes and leave edits dirty on conflict, adding a practical save boundary rather than a race-free guarantee against other writers.

## 2026-08-29
Filesystem nodes now offer explicit actions based on conservative file classification: known text and source files can open an [internal viewer](/specs/2026-08-29-graph-filesystem-file-interactions-design) or module view, while unknown files retain an external-editor path. The internal viewer reads bounded windows only when requested and stays read-only, bringing file inspection into the graph without copying content into its saved topology.

## 2026-08-26
Everyday [workflow authoring](/user/workflows/edit-workflow-topology) now includes naming new workflows, renaming existing definitions and deleting steps with their dependent edges. Compact definition previews hand off browsing to dedicated step and run explorers, keeping the graph's overview small while making the next edit or past run easier to reach.

## 2026-08-16
[Workflow inspection](/dev/features/workflow-graph-ux) now separates focused step browsing, run timelines and multiline payload views, so debugging can follow a failed step or selected event without filling the graph with every record. Runs can also start with selected graph nodes as context, and [cancellation](/user/workflows/monitor-and-cancel-running-workflow) appears only while the run status permits it.

## 2026-08-15
[Workflow authoring](/dev/features/workflows) now has a discoverable path from the Workflows root to new definitions, steps and linked code, with related records revealed only by explicit actions. [Sidebar chats](/dev/features/workflow-backed-agent-sessions) now persist as long-lived workflow runs whose events supply the transcript, so the graph and chat panel inspect the same underlying session rather than separate copies.

## 2026-08-14
[Activities](/dev/features/activities#activity-camera-boundary) now enforce ownership of their cameras and presentation boundaries, and the graph exposes scene data through a world/activity/surface hierarchy rather than flattening it onto the world. Alongside that clearer ownership, [graph-authored workflows](/dev/features/workflows) gained durable definitions and runs backed by executable Fennel code entities, giving automation a home outside any particular world or graph map.

## 2026-08-12
Restoring a board now prunes references to deleted string entities and their connectors, letting saved work reopen without stale items blocking activation. [Reloadable units](/dev/reloadable-units) return activity-reactivation evidence, making recovery observable rather than merely reporting that code reloaded. [Space agent sessions](/dev/features/opencode-agent-workflow#internal-space-agent-artifact-handoffs) also record artifact paths and live-versus-disk validation context, with one bounded reconnect for stale OpenCode connections rather than blindly retrying prompts.

## 2026-08-10
The [light theme](/dev/notes/light-theme-layering) now separates rails, graph background, panel chrome and cards through a consistent tonal hierarchy, with darker outlines keeping boundaries visible. A distinct tertiary tone also gives dialog titlebars and depth faces their own place in that hierarchy without introducing a new elevation API.

## 2026-08-09
Switching [graph maps](/dev/graph-maps) now restores each map's camera instead of carrying the previous task's viewpoint along, while maps without saved camera state center on their first or start node. Bounded inline panels and height-constrained sidebar layout keep surrounding controls contained, and malformed JSON now surfaces an explicit Lua error so broken saved state is easier to diagnose.

## 2026-08-08
August 7 introduced Sandbox's explicit [Fly, Walk, Move and Grab modes](/dev/notes/sandbox-interaction-toolbar#canonical-modes) and a capability preflight for agent tooling. On August 8, canvas Alt-drag was restored and graph views began rebuilding on theme changes, keeping everyday interaction consistent. Agent automation also tightened permission boundaries and repository trust checks while treating transient pull-request states as waiting rather than failure, making the [guarded development loop](/dev/features/opencode-agent-workflow#capability-preflight) more predictable.

## 2026-08-07
Space's graph workspace became easier to recover, search, and trust in motion: the [Graph Sidebar Node Finder](/specs/2026-08-06-graph-sidebar-node-finder-design) added Add Start recovery and Find Node rows that reveal or open graph-addressable objects through activity callbacks while keeping GraphMap as the interaction-context owner, and [Graph UX Polish](/specs/2026-08-07-graph-ux-polish-design) stabilized sidebar width, restored-map identity, truncation, and theme-resolved graph/chrome backgrounds so the graph view can stay a visual navigation surface instead of absorbing domain ownership. In parallel, weekly-agent workflow hardening tightened OpenCode capability boundaries and PR-protection polling, making the scheduled-agent path safer as graph work accelerates.

## 2026-08-05
The HUD chrome work moved from broad visual alignment into sharper layout contracts: real Material icon metrics now shape the chrome instead of idealized icon boxes, toolbar and rail rows share natural height, [HUD-scoped control and world-selector spacing](/specs/2026-08-04-hud-control-button-spacing-design) removes stray gaps without changing global widget defaults, and the [right rail now reserves only rail width](/specs/2026-08-04-hud-right-rail-transparent-strip-design) while projecting terminal/chat panels below the toolbar reserve so expanded side panels no longer steal transparent render space. Together these refinements keep Space's HUD polish tied to measurable widget behavior, making future layout changes easier to validate instead of hand-tune.

## 2026-08-04
Yesterday's HUD chrome pass turned scattered top/bottom/side/toolbar surfaces into a unified, naturally measured widget system: [shared HUD chrome metrics](/specs/2026-08-03-hud-chrome-visual-uniformity-design) made side rails the visual source of truth, the Sandbox toolbar gained real chrome inside a Card/Padding shell, and focused tests captured equal natural sizing and consistent behavior across the HUD boundary. A second pass [corrected single-row HUD icon scale](/plans/2026-08-03-hud-chrome-visual-uniformity) to keep icon rows at their natural chrome height, then a [follow-up refinement](/specs/2026-08-03-hud-chrome-button-owned-padding-design) moved control-panel and Sandbox toolbar height into button-owned padding with zero shell padding—preserving Card backgrounds and status-panel sizing while making the visual match architectural instead of fixed-size. This supports Space's UI/layout engine goals by making chrome composition easier to reason about and validate as future activities grow.

## 2026-08-03
Agent workflow reliability pushed through the finish line late on August 2 as five more PRs connected the remaining guardrails into one coherent loop: [targeted local validation](/plans/2026-08-02-targeted-agent-validation) replaced unconditional full-suite runs with narrowest-meaningful checks across every agent role, the [daily devlog automation](/dev/notes/daily-devlog-automation) added a locked-dependency preflight so fresh checkouts never fail on a missing VitePress, [workflow-debug landing](/plans/2026-08-02-workflow-debug-pr-landing) now routes final branches through `origin/main`-based PRs instead of local `main`, a [worktree build-warm recipe](/dev/features/opencode-agent-workflow) with exact-HEAD safety checks lets fresh Orca checkouts clone the build cache without stale-artifact risk, and the [merge queue agent workflow](/plans/2026-08-02-merge-queue-agent-workflow)—paired with [until-merged polling](/plans/2026-08-02-until-merged-merge-queue)—completed the repository migration to `semanticdreams/spacecore`, tying the `merge_group` CI trigger and auto-merge into one closed loop that owns every PR through to merge.

## 2026-08-02
Agent-driven development tightened its grip on reliability across the board: a [canonical Orca/OpenCode workflow page](/dev/features/opencode-agent-workflow) now gives collaborators a single setup entry point with supported remote-SSH and remote-VM patterns minus personal-machine noise, a dedicated web-researcher subagent isolates untrusted web evidence from the mutation-capable supervisor, and every workflow surface—from implementation to daily and weekly automation—shares a validation-continuation contract that reroutes required-test failures through systematic debugging and current-`origin/main` freshness checks instead of stopping dead at red. The [daily devlog automation](/dev/notes/daily-devlog-automation) hardened its own guardrails by verifying GitHub-ruleset branch protection before auto-merge and pinning landing-date attribution to `origin/main` merges so stale commit-author timestamps cannot skip or backdate landed work. Local builds got quieter and faster: the [default `make build` profile](/dev/building) is now minimal and CEF-off with summary-only output and a complete log file, reserving `make build-full` for browser-surface iteration. On the [Windows side](/plans/2026-08-01-windows-artifact-fast-suite), backslash normalization, `SPACE_ASSETS_PATH` fixture resolution, and POSIX-symlink skips brought the artifact fast-suite to green—together making the agent loop and cross-platform tooling faster and harder to trip over.

## 2026-08-01
Fennel constraints graduated from experimental to stable infrastructure, with validation output now summarized by default while preserving full detail behind a verbose flag for debugging, and agent workflows tightened in parallel through skill routing, MCP-accessible lint and repair tools, and hardened enclosing-form lookup — together sharpening the compile-check-and-iterate loop so constraint-aware development stays fast and reliable as the project scales.

## 2026-07-31
Runtime portability tightened with asset discovery that resolves from the executable through a deduplicated search order while preserving explicit overrides, and native logging now settles in a deliberate user log directory after dotenv has a chance to provide `SPACE_LOG_DIR`, keeping CLI, REPL, module, developer, installed, and portable runs predictable instead of scattering assets or `gl.log` around arbitrary launch directories.

## 2026-07-30
Late July added grounded camera controls and physics anchor dragging through a new sandbox interaction toolbar, migrated the presentation layer from app-global assumptions to activity-owned delegates, shipped external-unit MCP tooling for loader-neutral user code, and matured the daily devlog automation with a retrospective journal backfill — giving the project a durable narrative record as it builds toward the next graph and world-editing milestones.

## 2026-07-14
By mid-July, the project consolidated its operating loop around panel transfer, the repository workbench, conversation-first supervision, and the new VitePress knowledge base, turning months of scattered architecture notes into a navigable map for future graph, world-building, and live-development milestones.

## 2026-06-15
June pushed Space toward portability and broader authoring workflows, pairing Windows cross-compilation and packaging smoke-test work with board canvas mode, semantic connectors, item selection, and hot-reload cache cleanup so the workspace could travel beyond the original Linux development loop.

## 2026-05-08
May shifted the project toward live agent-assisted development: the agent runner, presets, MCP transport, OpenCode streaming, reloadable units, user-code scanning, and Lua-owned HTTP pieces started turning Space into an environment that can inspect and reshape itself while it runs.

## 2026-04-16
April was a stabilization pass for the growing world-building system, tightening lifecycle ownership, signal cleanup, composable state handling, stylus drawing, Yojimbo experiments, and canvas modes so interactive surfaces could grow without silent callbacks or tangled mode logic.

## 2026-03-18
March turned the newly merged Lua/Fennel stack into a world-building platform: terrain heightfields, graph editing, exposed world entities, lighting, and containment work converged so scenes were no longer just rendered surfaces but editable environments connected through the graph.

## 2026-02-16
Restructured docs: combined public docs with dev docs in a new VitePress project, deployed via GitHub Pages to spaceui.org.
A recent attempt at creating a new instanced quad based rectangle and text rendering system stalled, see code in next-app. Live development is needed to understand the system and harmonize layout and rendering designs.

## 2026-02-09
Added Xapian bindings for in-app search. Fixed input text alignment for inputs with extra space. Main challenge is how to structure the graph system to support specific features such as agentic coding, live state exploration, visual programming, knowledge management, etc. while remaining generic and convenient. A possible next step is to add notebooks with notebook pages (or nested notebooks) inspired by gtoolkit in order to provide a structure for the implementation of new features and to keep track of the alignment of development efforts with project goals.

## 2026-02-08
Status: Most features from the Python prototype have been recreated in the new Fennel/C++ implementation over the last few months.

## 2025-10-01
By October, Space's Python prototype had become a staging ground for a deeper Lua/Fennel migration: the long-lived branch carried the engine toward a scriptable UI and graph-centered runtime, keeping the momentum from the September Fennel rendering experiments while avoiding noisy mainline churn until the new architecture could land as a coherent replacement.

## 2025-09-24
Changed to load classes in Python prototype directly from z folder rather than through DB-based entities
to avoid a strange system-dependent problem.
As a result, editing class entities from within the prototype world will no longer work.
Prototype is reaching its end of life so this is ok.

Fixed fbo update issue by updating Lua's fbo handle on viewport change.

## 2025-09-17
Fennel implementation has basic triangle renderering and initial UI code (rectangles, layout, widget).
Output is rendered to a framebuffer displayed on a texture within the scene created by the prototype.
Entities will be file-based.

## 2025-09-16
In the process of replacing Python prototype with C++/Fennel implementation.
Prototype has skybox, line, triangle, text (msdf), image, point, mesh and sub-world **renderers**.
**UI layout system** has measure pass and layout pass. Layout nodes have to be assembled manually,
no uniform widget system. Since there is no widget hierarchy, every object stores
references to anything it creates, to be able to drop it when it's dropped.
**Entities** (base units of knowledge management in space), stored in sqlite, subclasses of `Entity`.
Each entity class defines view, preview, color, load & dump methods plus custom behavior. Entity
superclass tracks type, id, color and changed signal, has base get, create, save, delete methods.
Class entities are used for most of the prototype code. Jump to internal entities was problematic 
due to lacking internal development tools. Currently, 2-way sync between file system based classes
and class entities enables working from both external and internal environments.
**Space graph**, called dynamic graph in the prototype, implemented in classes `DynamicGraph`
and `DynamicGraphChild`. Nodes positioned using force layout, multiple LOD levels and full view added to HUD on selection.
Root graph entity (ID 18) is mounted into dynamic graph.

![Space Prototype Screenshot](./space-prototype-screenshot1.png)
