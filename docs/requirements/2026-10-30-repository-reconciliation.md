# One-time repository requirements baseline — consolidated audit

## Identity, authority and current boundary

- Task 1 author/CLI actor: `implementer/baseline-task-1`, this implementation session. Runtime session UUID was not supplied; this logical actor does not impersonate a platform session ID.
- Controller/workflow: supervisor, strict serial implementer → independent reviewer → pass; branch `juicyrebel/ridley`.
- Frozen source **F**: `fec176453c88fa1c47f22b7fe1d447dfe0ba281b`; Task 1 BASE: `3c9d6434897bb32a8a0ee1dc35f4e1fb740503e6`. Task checkpoint is a review input, not approval.
- Governing design: `docs/specs/2026-10-30-repository-requirements-baseline-design.md`, full design checkpoint `6fd7c0bcdc16444d18ad4332662eb6c4da0f5b52`; independent pass supplied by the controller (reviewer session `ses_e72c340f1ffet4XVnib8r2Ew4I`). Implementation consumes the Task 1 brief, not the whole plan.
- [Filename dispositions](./2026-10-30-repository-source-dispositions.md) preserve all frozen spec/plan paths and distinguish source inventory from semantic depth. [Task 1 report](./2026-10-30-baseline-task-1-report.md) preserves interruption/recovery and validation evidence.

This is authorized product-intent backfill beyond the original methodology seed, not bulk activation or application repair. Read all 12 existing revision-1 requirement bodies and all 26 artifact identities before creation. Existing obligations describe requirements methodology, not Space graph UX, runtime worlds or application agent tools. The lexical matches for graph, agent, native and live refer to methodology/tool internals, not equivalent product obligations. Source/provenance searches for README, milestone paths and graph goal returned no existing records. Semantic comparison of canonical bodies plus original intent, not empty substring matches alone, justifies new product records.

Reuse unchanged revision-1 methodology obligations: reconciliation `REQ-8e50a634-76ae-4100-9f60-90e4552ec954`; historical preservation `REQ-26f18ef2-15f6-4278-b9a1-9c7b4b246e5c`; traceability `REQ-1970c4a9-a5dc-4d1b-93ce-dc88ed42df84`; evidence separation `REQ-2824ad77-fbc5-4db6-ac9a-732af10eeabc`; transaction safety `REQ-0bf07879-9bbb-421a-85ab-37f495b6e552`; reviewed progression `REQ-49e62b92-aada-447d-9d15-531625fa0dcc`. These govern audit execution; no new `constrains` edge is inferred to product goals from mere relevance.

## Original-source Git evidence and authority decisions

All source references below are original repository Git objects, not mutable audit reports:

- `git log F -- README.md docs/dev/project/goals.md docs/dev/project/milestones docs/dev/features/{agent-tools,graph-foundation,world-building,core-platform}.md` inspected introduction/modification history. `git show 9649221083c26d5eb56db35d28b92c00108c6161:README.md` shows the slim landing page already contains **“Free Your System”**, spatial/live/shared/user-owned positioning and the four product bullets. Later repository-link changes do not establish product achievement. Current F README L7–18 retains those intents.
- `git show a709a28991798ba988291708ee156aa60a9a8119:docs/dev/project/goals.md` shows the same three active goals and completed-label platform foundation at their docs reintegration. F goal index and all four goal-page summaries/why/success criteria were read in full.
- Original goal-page text at `a709a28991798ba988291708ee156aa60a9a8119` was compared to F. `8eee15bf44262e20b16c99446439257a772cf675` clarifies graph exposure versus universal storage: conversations exposed through graph, terrain backed by world state, view-agnostic graph foundation. This is not authority to discard graph-linked UX, nor to make graph own all domain data.
- Goal history lists platform changes at `305f50addcd4fb37e91df13acf692cb444ea8a73`, `6f2b87d6c570322b18f2c225699393f7be683911`, and `08500bfaa18307555b08a0f19c855ad3b97d5359`; F platform summary explicitly describes HomeWorld activities and lists known bugs. Its `done` label is descriptive historical status, not empirical verification. The new platform record stays proposed pending capability-family reconciliation.
- All 12 F milestone bodies were read in full. M00/M01/M03/M05 overlap the four goal pages and are reused as source corroboration rather than four extra requirements. M02/M04/M06–M11 contain independently meaningful proposed/planned work. Milestone history at the frozen snapshot shows introduction at `a709a28991798ba988291708ee156aa60a9a8119`; original M04 and M08 bodies were inspected directly with `git show`, retaining `planned` and `proposed`, respectively. No execution authority or achievement follows from milestone order.
- F `docs/dev/project/{features,ideas,research}.md` are navigation statements, not independent backlog obligations. F project history is a retrospective through July, not October completion evidence. Its prototype references do not authorize Python-derived requirements.

All new provenance uses `justified_interpretation`: product documentation is explicit repository intent, but not a verbatim maintainer conversation. Strategic records retain empirical criteria with measurement/protocol/threshold gaps. Roadmap scenario criteria are bounded analysis obligations, not invented numeric performance targets. Financial/security policies remain unspecified; no scenario description authorizes actual operations.

## Transaction journal and canonical identities

Initial ledger revision **29**: 12 requirements, 26 artifacts. No original observations, normative histories, assessment states or artifact digests are edited.

### Batch 1 — revision 29 → 30

Executed existing CLI `apply --stdin` with actor `implementer/baseline-task-1`, expected revision 29. Result `status: ok`, returned revision 30. Created the following **16** records, each normative revision 1 and initially proposed. Aliases below are report shorthand only; canonical identities are the returned opaque IDs.

| Audit alias | Returned requirement ID | Original F source / completed top-down scope | Later owner |
| --- | --- | --- | --- |
| Spatial | REQ-260bf539-61dc-404e-b182-0692acbf744d | README Spatial Computing | 3 |
| Live | REQ-4546e4f3-1a73-4811-8e10-7815d31776c3 | README Live Programming | 3 |
| Shared | REQ-1fdd5124-6c03-4b71-b7c7-400278f8e82c | README Shared Worlds | 3 |
| Owned | REQ-80869160-7ee8-4062-902d-b90f0d9507aa | README User-Owned Infrastructure | 3 |
| Agent | REQ-e7bad2ed-a3b7-40d7-83ef-f4f61d6d2461 | features/agent-tools Summary/Success criteria; M05 reused | 2 |
| Graph | REQ-1bfc6cf6-25ea-4c94-9440-6cfe534d2ea6 | features/graph-foundation Summary/Success criteria; M01 reused | 2 |
| World | REQ-5d09d4e2-2cd6-4c62-8d6a-f1070825a172 | features/world-building Summary/Success criteria; M03 reused | 3 |
| Core | REQ-c8ffc754-34a3-4c0f-aeda-89f7ac7de1e5 | features/core-platform Summary/Success criteria; M00 reused | 3 |
| Workspace | REQ-1d7a72a9-2614-4508-955f-ffd0455546f8 | project/milestones/m02-workspace-loop.md | 2 with 3 |
| Malleable | REQ-3ec80f9e-aef5-4b29-88ad-0721b9951370 | project/milestones/m04-live-development.md | 3 |
| Compiled | REQ-e08c9e47-df7b-4894-9bc6-42e701c5bcb2 | project/milestones/m06-compiled-update.md | 3 |
| JIT | REQ-4966274c-ebaf-4826-b7ea-0f4826d49430 | project/milestones/m07-native-generation.md | 3 |
| Matrix | REQ-c9bba90c-9d93-4f7d-a530-f79cb197ae88 | project/milestones/m08-matrix-worlds.md | 3 |
| Social | REQ-5babb6e9-88c4-43f5-8904-d6321f5bf795 | project/milestones/m09-social.md | 3 |
| Gameplay | REQ-b08e4d4b-38c4-4096-874b-a4f46aaaafc2 | project/milestones/m10-gameplay.md | 3 |
| Services | REQ-73f67424-c7a6-450b-a8ce-feb67ac00a14 | project/milestones/m11-services.md | 3 |

Product goals are not a new hierarchy: overlaps use contribution without sufficiency; only a genuine precision relation warrants refinement. Artifact registration count is zero in this top-down batch: goal pages and milestones are intent provenance, not invented design artifacts to fill an otherwise missing chain. Existing methodology artifact IDs remain intact. Later owners must link actual inspected designs/plans/code/test definitions, not infer implementation from filenames or tests from completion reports.

### Batch 2 — revision 30 → 31

Existing CLI `apply --stdin`, expected revision 30, returned `status: ok`, revision 31. Separately activated only **Agent, Graph and World**, grounded by F goal index `Active`, their `status: active` frontmatter and substantive Summary/Success criteria. Their normative revisions remain 1; transitions retain authority/history. Core and all README positioning/roadmap records remain proposed. No assessment or verification was recorded.

Added **14** requirement relations: one refinement and thirteen contributions. No derivation, dependency or constraint applicability is invented. Three contributions are deliberately `inferred`, preserving a plausible-help interpretation rather than claiming explicit derivation or behavioral dependence.

| Returned relation ID | Source → target (aliases above) | Type / confidence |
| --- | --- | --- |
| REL-e2aec03f-d85e-49b2-9321-0790a8b39b7b | Malleable → Live | refines / explicit |
| REL-f2a47c68-b0c4-4216-a988-ec8ade38cceb | World → Spatial | contributes_to / explicit |
| REL-64f09fd3-2039-440f-aab5-f29812080170 | Core → Spatial | contributes_to / explicit |
| REL-7cc7fa61-7c98-4390-a840-2434e2d10a77 | Core → Live | contributes_to / explicit |
| REL-ad79af31-2df2-4ddb-90f5-bc2c93ad3493 | Agent → Graph | contributes_to / explicit |
| REL-3e6c811e-28ff-45fc-97ce-b32313435f62 | Workspace → Graph | contributes_to / explicit |
| REL-53ddeed1-8d2a-4b13-8398-de2e1da27d58 | Compiled → Live | contributes_to / inferred |
| REL-c902b722-30eb-4012-bbe6-41301432b465 | JIT → Live | contributes_to / inferred |
| REL-705cd6da-c6cd-4953-971c-0a860b965013 | Matrix → Shared | contributes_to / explicit |
| REL-9dc1f389-441e-46e1-ac29-cb4ce10b2fc6 | Matrix → Owned | contributes_to / inferred |
| REL-a70fc602-d3fd-4a03-8f3c-cb1ed5acba70 | Social → Shared | contributes_to / explicit |
| REL-6927cd89-3054-4247-bad4-6780006b87a4 | Gameplay → Shared | contributes_to / explicit |
| REL-d809b141-24b5-43ab-9c12-84698afe66d9 | Gameplay → Spatial | contributes_to / explicit |
| REL-fa83e28c-dc01-42f9-b5b3-5e571e663174 | Services → Owned | contributes_to / explicit |

Completed canonical scope: top-down goals/roadmaps only, 28 total requirements / 26 artifacts at revision 31. Counts are definitions, not targets: 16 new unique requirements; 6 governing existing requirements reused without mutation; 4 overlapping milestone sources reused against goal records (not four extra reused canonical IDs); 0 normative revisions to existing records; 3 lifecycle transitions; 1 refinement link; 13 contribution links; 0 registered artifacts; 0 assessments/verifications/supersessions/retractions. Existing three methodology design/spec/progress artifacts are recognized in dispositions without duplicate registration. No new code/test trace is claimed.

## Task 1 source coverage, gaps and handoff

Frozen filename accounting: **362/362** spec/plan paths exactly once (168 specs, 194 plans), no missing/extraneous/duplicate paths. Dispositions: **287 supporting solution/evidence, 72 unresolved gaps, 3 duplicate/reused**. All 72 U rows state a concrete unanswered source question and assigned family owner. S rows name the inspected solution/Goal and a specific untraced contract; they do not assert implementation. All 1,201 docs files and all non-doc root families have disjoint membership/counts and depth/unknown boundaries in the disposition page. The 61 feature files include one index (60 bodies); 12 milestone bodies exclude their index (13 files).

The additions after F are three governing baseline spec/plan/progress records and the three Task 1 audit/disposition/report pages. Generated spec/plan indexes add navigation to the governing records; they do not add to the frozen denominator. The controller's progress edit is unrelated worker state and must not be staged or committed by this author.

Status axes for **each of the 16 new records**:

| Axis | Current result / honest denominator |
| --- | --- |
| Documented intent | 16 grounded records, normative revision 1; 3 explicitly active goal sources, 13 proposed records. |
| Implementation presence/partiality | **Unknown for all 16**: Task 1 did not inspect code bodies. No implementation-presence numerator can honestly be reported. |
| Registered design trace | **0/16** new product records; existing methodology **12/12**. This is registry trace coverage, not physical implementation coverage. |
| Test definitions | No new product test artifacts traced; whether relevant assertions already exist is unknown, not “no tests.” |
| Historical verification | Existing reports retained; no historical tests recast as fresh product observations. |
| Fresh observations | Source inventory/provenance and ledger/docs checks only. All 16 new c1 observations are `absent`, currency `unknown`. |
| Satisfaction | No new assessment, not even partial. Qualitative goal usefulness/naturalness/performance/ownership remains unverified. |

Task 2 consumes Agent, Graph and Workspace IDs, plus row-assigned graph/entities/workflows/application-agent/text sources. Task 3 consumes Spatial/Live/Shared/Owned, World/Core and remaining roadmap IDs plus row-assigned platform/runtime/hosted/temporal/networking/security/development sources. Task 4 reconciles cross-family identity/relations, unresolved gaps and every-family second sweep, then runs broader docs build/navigation checks. Tasks 2/3 must inspect full contracts and actual code/assertions before linking artifacts; Task 1 opening excerpts are not a shortcut around that work.

Material source issues retained, not silently resolved:

- Temporal complete-platform original opening versus bounded closeout opening: original breadth is not superseded by a later small-corpus success claim. Task 3 must investigate original commits/full contracts/current temporal feature and acceptance pages/tests, preserving explicit intent over technical narrowing absent policy authority.
- Graph exposure versus storage: inspected original/current goal text and accepted graph ADR support domain ownership with view-agnostic exposure. Do not accidentally backfill “graph owns everything.” Task 2 must reconcile topology/reference/presentation details.
- Core `done` versus known bugs and platform-conditional media backends: neither source label nor feature listing proves stability/performance/universal availability. Task 3 must inspect actual platform declarations and tests.
- Old model/consultation/fast-flow proposals may differ from current instructions. No supersession decision was made from filenames; Task 3 owns original policy comparisons, not policy changes in this audit.
- Proposed Matrix permission, wallet tipping and services scopes lack resolved operational/security policy. These are recorded proposed intent only; no credential, network, fund movement, migration or irreversible action was attempted. SDK stability/versioning policy remains explicitly undefined.

## Task 1 verification and bounded repeatability

- CLI `validate` and `render --check`: revision **31**, `valid: true`, `current: true`.
- `make requirements-check`: **348 passed in 169.02s**, then canonical validation and projection check succeeded at revision 31. First invocation was terminated at the caller's 120-second timeout; unchanged rerun with a 600-second allowance completed. The observed 169-second run explains why the first allowance was insufficient; no repository gate was weakened or code repaired.
- Existing `npm run records:indices` in `docs`: successful; generated only the assigned spec/plan indexes (two plan/progress entries, one design entry).
- In-memory manifest check compares first-column exact paths to `git ls-tree -r -z --name-only F`: **362 rows/362 unique, 0 missing/extras/duplicates**, docs count 1,201, root files 7. No tracked importer/tool was created.
- In-memory preservation assertions against Task 1 BASE passed: all **12 original requirements, 26 artifacts, 148 relations, 17 assessments and 63 verifications** unchanged. New relation tuples are unique, endpoints are the inspected new IDs; all artifact locator/selector tuples remain unique. New relations: 1 refines/13 contributes_to, 11 explicit/3 inferred.
- Initial all-record `coverage` at revision 29: scope 38, depth 32/paths 1000, not truncated. Shared six-governor combined `reconciliation-context`, each single-governor context and each `trace(direction=both)` at depth 32/paths 1000 were **truncated** in the dense existing methodology component. Narrowing each governor to depth 2 still truncates; no complete impact/no-blocker claim is made. Canonical governor bodies were inspected directly; no old record or relation is mutated and no inferred applicability to product records is asserted.
- New 16-ID scoped `coverage` and `reconciliation-context` at depth 32/paths 1000: **not truncated**. Each of the 16 individual `trace(direction=both)` calls at the same bounds: **not truncated**, with 2 paths for Agent/Graph/Workspace and 12 paths for each other record. Whole-ledger coverage at revision 31: 54 records, **not truncated**. Unknowns retained: unlinked behavior/unregistered history outside complete blast radius; candidate links require investigation and establish no authority/clearance; reachability/shared locators are potential impact, not proven behavioral dependence.
- A scoped second **top-down-only** sweep rechecked all 16 actual original-source excerpts, criteria/statuses and 14 typed relation tuples; zero further justified creations/revisions/transitions/links were identified. No no-op apply was issued. Revision stayed **31** and ledger/index bytes stayed identical. This is **not** the final every-family idempotence claim; Task 4 still owes that after family reconciliation.

SHA-256 before/after that scoped sweep:

- ledger: `6296584778800c106bebefb943c9611ccffead63e7335ba59d61f9f44ccd24bc`
- index: `3d8bea5e8598fce5d77855f8d7b8776ce35f5d54ba27f7bd14187e1d8f2938cd`

Coverage rationale: schema/history/projection checks cover the only canonical mutations; source-set equality covers exact frozen accounting; original-source/excerpt checks and semantic self-review cover provenance/duplication; typed bounded queries expose missing traces/unknowns without satisfaction inflation. The existing record generator covers touched navigation indexes. Runtime/Fennel compile checks, application constraints and runtime tests are not applicable: no application, Fennel, C++, test, prompt, infrastructure or tooling source changed. Full VitePress build/navigation and final every-family repeatability belong to Task 4, not an implicit Task 1 completion claim. Independent exact-range review remains required.
