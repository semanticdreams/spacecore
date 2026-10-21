# Devlog Gap Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish exactly 41 meaningful, evidence-backed historical daily entries without changing existing publishing behavior.

**Architecture:** Sequential month-sized content tasks own new journal sources and both existing generated indexes. The committed spec supplies the date/evidence/theme manifest; ignored reports retain claim verification. Existing generators and publishing workflow remain unchanged.

**Tech Stack:** Markdown, existing Node.js docs scripts, VitePress, read-only Python/Git checks.

## Global Constraints

- "Preserve every existing published journal entry byte-for-byte, including August 7 and October 21."
- "The cutoff for this retrospective is October 20; subsequent work belongs to forward automation."
- "The user explicitly approved normal Discord/Matrix announcements: **no special publishing logic**."
- "Do not modify publisher code, workflows, frontmatter schema, state, settings, scripts, tests or automation configuration."
- "Derive dates from first-parent merge committer timestamps in UTC, not feature-branch author dates or spec filenames."
- "No bullet lists, extra headings, commit hashes, author lists, separate reference lists, raw file lists or commit-summary prose."
- Spec: `docs/specs/2026-10-21-devlog-gap-backfill-design.md`. Landing baseline `435950c7c78d1288bfb0a3cbebaf20fc1f1489c8`.
- Exact entry template: `---\ntype: journal\ntags: [journal, devlog]\ncreated: YYYY-MM-DD\n---\n\n# YYYY-MM-DD\n\nOne short narrative paragraph.\n`.
- Prefer two or three compressed narrative sentences, up to two useful existing root-relative docs links. Verify target and fragment; avoid later-page claims not established at the historical landing.
- No concurrent index writers. Modify only each task's new sources plus generated `docs/dev/journal/index.md` and `docs/dev/devlog.md`. Reports/checkers/review artifacts stay ignored; no new production tests or validation tools.
- TDD is not applicable to prose-only changes. Record missing-coverage baseline, then validate entry shape/date, claim evidence, links, preservation, exact added dates, generator output and whitespace. Native/Fennel build/constraints are not applicable.
- Every task runs `npm run test:scripts` and `npm run devlog:indices` in `docs`; install locked deps with `npm ci` only if unavailable. Full docs build is the final branch gate, not a prerequisite before every paragraph checkpoint.
- Supervisor commits task changes only after independent review passes. Implementer supplies exact uncommitted working diff and evidence report; final whole-branch review covers all 41 entries. No claim of social delivery from merge alone.

Read-only validation pattern (use the task's assigned dates and completed prior tasks; save any reusable checker only in ignored scratch):

```python
import re, subprocess
from pathlib import Path
baseline = "435950c7c78d1288bfb0a3cbebaf20fc1f1489c8"
journal = Path("docs/dev/journal")
for name in subprocess.check_output(["git", "ls-tree", "-r", "--name-only", baseline,
                                     "--", str(journal)], text=True).splitlines():
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", Path(name).name):
        assert Path(name).read_bytes() == subprocess.check_output(["git", "show", f"{baseline}:{name}"])
spec = Path("docs/specs/2026-10-21-devlog-gap-backfill-design.md").read_text()
dates = re.findall(r"^\| (2026-\d{2}-\d{2}) \|", spec, re.M)
assert len(dates) == len(set(dates)) == 41
for date in dates:
    path = journal / f"{date}.md"
    if not path.exists():
        continue  # Report missing dates per task; final validation must require all 41.
    header = f"---\ntype: journal\ntags: [journal, devlog]\ncreated: {date}\n---\n\n# {date}\n\n"
    raw = path.read_text()
    assert raw.startswith(header) and raw.endswith("\n")
    body = raw[len(header):].strip()
    assert body and not re.search(r"\n\s*\n", body)
    assert not re.search(r"(?m)^\s*(?:#{1,6}\s|[-+*]\s|\d+[.)]\s|>|```|~~~)", body)
    assert not re.search(r"(?i)\b[0-9a-f]{7,40}\b", body)
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", body)
    assert len(links) <= 2
    for url in links:
        assert url.startswith("/")
        target = Path("docs") / url.split("#", 1)[0].lstrip("/")
        assert target.with_suffix(".md").is_file() or (target / "index.md").is_file()
```

---

### Task 1: August — 10 Entries

**Files:** Create `docs/dev/journal/2026-08-{08,09,10,12,14,15,16,26,29,30}.md` (brace notation enumerates exact files, not a filename). Regenerate `docs/dev/journal/index.md` and `docs/dev/devlog.md`.

**Interfaces:** Consume spec's August evidence/theme table and boundary paragraph; produce ten validated August entries and refreshed indexes for Task 2. No code/API interface changes.

- [ ] **Step 1: Baseline and verify evidence.** Require assigned dates absent and existing sources preserved. Inspect first-parent anchors and complete daily PR ranges from spec. Record date → landed UTC evidence → bounded claim → link in ignored report. August 6 is already covered; preserve August 7. Include later August 7 Sandbox/preflight work only as an explicitly August 7 contextual bridge inside August 8, without attributing it to August 8.
- [ ] **Step 2: Write ten paragraphs.** Themes by date: 08 interaction/automation reliability plus dated bridge; 09 retained camera context/contained chrome; 10 light-theme hierarchy; 12 recoverable state/observable live development; 14 activity ownership/workflow execution; 15 workflow-backed chat/explicit discovery; 16 workflow inspection; 26 everyday workflow authoring/explorers; 29 read-only bounded filesystem viewing; 30 lazy editing/conflict-aware saves. Use exact template, prose and link contract; no feature claims imported from later canonical docs.
- [ ] **Step 3: Compress and validate.** Crosscheck every statement with historical implementation, then remove change-list phrasing and redundant clauses. Run read-only shape/date/link/preservation/coverage checks, `npm run test:scripts` and `npm run devlog:indices` in docs, and `git diff --check`. Require exact ten added dates, descending indexes and all paragraphs present once. Inspect scope including untracked files.
- [ ] **Step 4: Review and commit.** Write ignored report and exact working review diff from task base including untracked sources, generated outputs and name manifest. Reviewer checks all ten narratives/evidence and both outputs. Fix through implementer/reviewer to pass; supervisor commits only reviewed task files before Task 2.

### Task 2: September — 16 Entries

**Files:** Create `docs/dev/journal/2026-09-{06,07,10,14,15,16,17,18,23,24,25,26,27,28,29,30}.md`. Regenerate `docs/dev/journal/index.md` and `docs/dev/devlog.md`.

**Interfaces:** Consume Task 1's ten entries/indexes and spec's September evidence/theme table; produce sixteen September entries and indexes covering 26 additions. Preserve Task 1 sources and all original published sources; no code/API change.

- [ ] **Step 1: Baseline and verify evidence.** Require all sixteen dates absent and August complete/unchanged. Inspect spec anchors, daily PR ranges and actual landed deltas, using merge UTC dates. Record date-to-claim/link proof in ignored report. Do not infer temporal features from September 29 branch names.
- [ ] **Step 2: Write sixteen paragraphs.** Themes: 06 modal lazy editor; 07 kind badges/input routing; 10 anchor navigation; 14 shared text interaction; 15 graph extension lifecycle; 16 portable runtime/asset/error foundations; 17 islands/app bundles; 18 Snake/orthographic UI; 23 independent island placement; 24 aggregate movement; 25 hosted composition/temporal core; 26 host capabilities/bounded temporal layers; 27 command workbench/richer recurrence; 28 SDK/launcher/providers; 29 cross-platform diagnostics; 30 zoned recurrence/intervals. Keep scan bounds, session-local history and dependency scaffolding claims appropriately limited. Use exact template, compressed prose, useful verified links and no retrospective feature inflation.
- [ ] **Step 3: Compress and validate.** Verify each paragraph against historical implementation and retain enablement rather than an exhaustive checklist. Run read-only shape/date/link/preservation/coverage checks, `npm run test:scripts` and `npm run devlog:indices` in docs, and `git diff --check`. Require exactly sixteen September additions and 26 total additions with descending indexes and no duplicate body sections.
- [ ] **Step 4: Review and commit.** Write ignored evidence report and complete working review package including new sources. Reviewer checks sixteen narratives and output deltas. Fix through implementer/reviewer to pass; supervisor commits only reviewed task files before Task 3.

### Task 3: October — 15 Entries and Complete Coverage

**Files:** Create `docs/dev/journal/2026-10-{01,02,03,04,05,06,07,08,09,10,11,12,15,17,20}.md`. Regenerate `docs/dev/journal/index.md` and `docs/dev/devlog.md`.

**Interfaces:** Consume Tasks 1–2's 26 entries/indexes and spec's October evidence/theme table; produce fifteen October entries, complete 41-date coverage and final indexes. Preserve all previous sources, especially October 21. No code/API or publication behavior change.

- [ ] **Step 1: Baseline and verify evidence.** Require all fifteen target dates absent and earlier26 additions unchanged. Inspect spec anchors/daily PR ranges and actual implementation deltas. Record proof and exclusions: October14 maintenance, design-only build broker, shell-round-trip quarantine, bounded reference recovery, October20 policy vs October21 branch preparation, and no post-cutoff SSE work.
- [ ] **Step 2: Write fifteen paragraphs.** Themes: 01 calendar interoperability/contextual commands; 02 timestamp migration/scheduling; 03 bounded temporal completion/feedback; 04 graph commands/SSH foundation; 05 concrete remote integration/iteration; 06 content search; 07 nested focus/asset freshness; 08 outline projection; 09 interaction parity/CI responsibility; 10 shared compact lifecycle; 11 dictionary/MCP infrastructure; 12 measured projection widgets/targeted CI; 15 composition/catalog/live development; 17 reference lifecycle; 20 guarded queue policy proof. Use exact template and compressed meaningful narrative, with no unsupported conformance, deployment or atomicity claims.
- [ ] **Step 3: Compress and validate.** Run read-only shape/date/link/preservation checks, require all41 manifest sources and no unexpected added dates, then docs `npm run test:scripts`/`npm run devlog:indices` and whitespace check. Ensure both indexes include each date/body once in descending order.
- [ ] **Step 4: Review and commit.** Package all fifteen sources, both generated deltas and evidence in ignored scratch. Reviewer inspects every entry and preserves prior sources. Fix through implementer/reviewer to pass; supervisor commits reviewed files.
- [ ] **Step 5: Final review and validation.** Whole-branch reviewer checks all41 narratives plus spec/plan/indexes and source preservation. After current-origin/main fetch/evaluation and permitted safe merge, rerun docs script tests, index generation, all coverage checks and `NODE_OPTIONS=--max-old-space-size=4096 npm run docs:build`. Verify regeneration/build idempotence, `git diff --check`, exact content-only diff and clean committed tree. No native/Fennel runtime validation applies. Diagnose required failures rather than bypassing or broadening scope silently.
- [ ] **Step 6: Protected integration.** Recheck current origin/main before push/PR through capability agents; safely merge/review/revalidate if necessary. Create normal main-targeting PR, enable guarded auto-merge, and poll until actual mergedAt with required test/merge-group checks green. Do not chase main movement after queue entry; no direct-main push, rebase or force. Report entry totals and actual merge evidence without asserting channel delivery.

Self-review: all41 spec dates map to exactly one task; preservation, August bridge, historical cutoff, normal announcements, prose/evidence/link checks, generator validation and protected merge are covered. No unresolved choice or special publishing implementation remains.
