# OpenCode session-graph review and integration progress

## Provenance and limits

This is a privacy-reviewed development-history summary, not a new review or a
verbatim copy of private handoffs. Prepared on 2026-10-28 from the retained
`.superpowers/sdd/review30-progress.md` and the controller's integration/cleanup
transcript. The private ledger and original/corrected deliveries remain unchanged.

Private ledger SHA256 at preservation:
`269df3110ddc71e67b5944e03cab51391010d1262092e604388efc483af7f788`.

Controller/workflow and branch: `live-dev`. Original fixed 30-commit review range:
`f2ea35a53d0c43385f503dacffd54339b873cefa..0a00556f3a295c9dbf26ea72fc807a350f968f03`.
The final batch was integrated by [PR #286](https://github.com/semanticdreams/spacecore/pull/286)
at `6dfada36c24cb93ae3adc09a2c2416724a2de93e`.

The source ledger contains historical snapshots, including intermediate blockers
and later recoveries; those are not simultaneous current states. This summary
omits runtime endpoints, machine-specific paths, raw dumps and worker payloads.
Do not use a summary's omission as evidence of an unused correction allowance,
a successful verdict, or authority to reconstruct missing facts. Reconcile the
retained originals before resuming any historical assignment.

## Design and ownership retained

- OpenCode server owns session truth. HTTP snapshots are an ephemeral read model;
  SSE invalidates them rather than persisting or replaying domain deltas.
- Graph nodes are adapters; Space persists topology, not an independent session
  domain store. Hierarchy: sessions → session → messages → message → parts → part,
  with separately addressable information projections.
- Views use one input per ontological unit. Expanded cards render node views;
  previews remain for embedding. Unchanged row/section projections preserve
  widgets, pagination and buffers while actions use current payloads.
- Ordered-list islands at message and part levels require owner hydration,
  balanced topology-installation barriers and presentation-preserving replacement.
- External-editor results retain buffer identity, generation and baseline text;
  stale/readonly/errored results cannot overwrite edits. Accepted changes reset
  caches before exactly-once notification.
- Live subscriptions use epochs, permanent-drop guards and bounded delayed retry;
  metadata and transcript form a required completion pair. Optional sections do
  not block it. Scalar/structured metadata classification is exhaustive.

See the tracked [design spec](../specs/2026-10-26-opencode-session-graph-exposure-design.md)
and [SELinux publication contract](../dev/features/record-publication-selinux.md)
for the reconciled contracts rather than treating this summary as a new spec.

## Review delivery history

The following records preserve stable identity and separate correction usage.
Original/corrected payloads are private and were not normalized into this summary.
The first three assignments have the original fixed full-review range above.

| Assignment | Original role/session | correction_used | Recorded delivery disposition |
| --- | --- | --- | --- |
| `review30-session` | reviewer `ses_e80b399abffefR7qA5DvFqqP2y` | 1 | Valid corrected delivery; normal semantic handling |
| `review30-projections` | reviewer `ses_e80b3998effeHSGSspXsBXtB3w` | 0 | Valid delivery; normal semantic handling |
| `review30-ui` | reviewer `ses_e80b3997dffeqgVaiQx62bVwVb` | 1 | Exhausted/invalid; never a usable verdict |
| `review30-ui-integrated` | reviewer `ses_e7eae387cffe2fRmASptEFMsLO` | 1 | Human-authorized genuinely new integrated scope; valid corrected `candidates_found` |
| `review30-wrapup` | fast-dev-reviewer `ses_e7c89a64effeizyZqs12w35ww3` | 0 | Valid observational report; recorded pass with non-blocking findings |

Integrated UI scope: base `f2ea35a53d0c43385f503dacffd54339b873cefa`,
HEAD `8a0b3ab53fd051c78f07736a3bad1c45982b79c3` plus the original working-diff
blob `8ca14929eccee92e6cb1bedfbad1adda60bb35d4`. This did not repair/reset the
exhausted original UI assignment.

Wrap-up scope: base `9e91902801d1b2ef1ba2a71fdcc3952b3245a6d4`,
head `a6ad16fc61138237efd5bdff34d9e2a074b81db2`, observational whole-branch mode.
Recorded non-blocking follow-ups: stale-label wording during healthy refresh,
action-time ID-validation consistency, and substring-based event relevance churn.

## Implementation checkpoints (before squash)

| Checkpoint | Intent and validation recorded at that stage |
| --- | --- |
| `f4a97f86` | Deliver HTTP terminal health before callback cleanup; focused native/SSE regressions |
| `8a0b3ab5` | Validate snapshots, await both config sections, guard stale/duplicate callbacks |
| `c637dab5` | Guard external-editor writeback lifetime; five new tests and VirtualInput 74 pass |
| `08b96f13` | Reconcile live snapshot rows and independent section buffers; eight UI tests |
| `f5a43678` | Reconcile derived islands after topology installation; real-map lifecycle coverage |
| `e88ea19e` | Bound live recovery and coalesce required snapshot pair; six lifecycle tests |
| `778f3aa3` | Preserve complete decoded message/run metadata; canonical info-field codec |
| `30c0d7c0` | Read-only SELinux label preservation and corrected private lookup dependency |

The user authorized consolidation: 41 commits were squashed to `a6ad16fc` on
`origin/main`; a tree comparison proved identical content. The user separately
authorized force-with-lease on `origin/live-dev` only; `origin/main` was never
force-pushed. After integration, the user authorized removal of the local
pre-squash backup ref and task-specific temporary A/B artifacts. No design spec
or ledger was deleted by that cleanup; the ignored ledger's lack of Git protection
is the defect addressed by the later preservation work.

## Meaningful failures, recoveries and coverage limits

- Earlier full local validation failed: 30/35 CTests passed and the Fennel runner
  reported 472 failures. A derived 431 direct-storage classification was evidence,
  not proof that all failures had one cause. Storage-backed setup refused
  `security.selinux` under the original blanket xattr policy.
- SELinux support required human policy/scope choices and GLM/GPT reconciliation.
  System libselinux conflated regex failures and genuine negative lookups. The
  user authorized a pinned, narrowly corrected private backend, not label writes,
  security disabling, custom policy parsing or weakening fixed-default priority.
- The unpatched backend's real PCRE2 fault injection was RED in both system-DSO
  load orders, then GREEN with the exact patch. A cleanup allocation regression
  was repaired with stack-only successful metadata validation. Capability-absent
  standalone Wine helpers retain explicit unsupported-metadata refusal.
- Final local canonical `make test`: 42/42 CTests; Fennel compile 1417 files;
  constraints zero diagnostics; focused publication/lookup/isolation group 11/11.
- Initial broad Python publication run: 733 passed, 77 failed, 143 setup errors.
  These were mixed causes, not all pre-existing: the added header was missing
  from fixed test inventories, which was corrected. Subsequent builder focus:
  92 passed; broader reclassification: 117 passed, two environment failures;
  Wine-runtime tests: 359 passed, three failures for missing MinGW compilers.
  Other environment limits included static libstdc++ and UBSan availability.
  A/B comparison established identical baseline/working refusal for tested
  capability-absent host models on labeled temporary storage, not for every
  originally failing test. Failures were not represented as skips or green runs.
- A failed reload and successful CLI recovery remained separate evidence. Later,
  manual request 11 on the old app failed `restart-required: executable changed`;
  explicit validated rebuild/restart succeeded, followed by manual request 1 and
  ready/non-faulted status on the replacement. Successful recovery did not erase
  the original failure.

## Integration and final state

- One observational whole-branch report was recorded as pass with minor findings.
- First required PR `test` run failed five capability-wiring text assertions:
  tests/docs still expected topic-suffixed branches, wrapping broke one phrase,
  and prompt continuation guidance had been dropped. Local reproduction was
  five failed/270 passed. Fix `4df947f9` restored consistent exact-name contracts;
  permission checker passed and 275 tests passed. This gate had been omitted
  from the earlier local validation; the omission was acknowledged.
- PR run `40736131409` passed at `4df947f9`; merge-group run `40739031220`
  passed, including runtime and E2E tests. PR #286 merged at
  `2026-10-28T18:11:11Z` with merge SHA `6dfada36c24cb93ae3adc09a2c2416724a2de93e`.
  A fresh fetch and ancestry check proved it was in `origin/main`.
- The long-term `live-dev` branch was safely fast-forwarded and pushed to the
  merged main tip (zero ahead/behind). The later preservation policy checkpoint
  `ebbc538f` begins the next batch; it was not part of PR #286.
