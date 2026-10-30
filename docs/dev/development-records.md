# Development records

Browse the project's preserved design, implementation and validation history:

- [Design specs](/specs/) — decisions, contracts and rationale.
- [Implementation plans](/plans/#implementation-plans) — how work was broken
  down and intended to be validated.
- [Progress ledgers](/plans/#progress-ledgers) — what actually happened:
  checkpoints, consultations, review outcomes, failures, recoveries and integration.
- [Requirements](/requirements/) — grounded obligations and typed trace links,
  separate from these historical inventories. See the
  [methodology/API guide](/dev/features/requirements-driven-engineering) and
  [templates](/dev/notes/requirement-templates). Historical placement does not
  establish requirement authority; no bulk backfill is required.
- [Repository baseline audit](/requirements/2026-10-30-repository-reconciliation)
  and [source dispositions](/requirements/2026-10-30-repository-source-dispositions)
  — the explicitly authorized one-time product baseline, with frozen filename
  accounting, representative semantic depth, source contradictions and honest gaps.
  These reports are not product verification or independent approval.

Each index includes every regular Markdown record in its directory and nested
directories, grouped by month with the newest dated records first. Undated records
remain listed. Titles are taken from headings, with a filename fallback. The
`-progress.md` filename convention separates ledgers from other plans; placement
does not imply that a record was approved, completed or has a matching design.

The shared sidebar stays available while reading a spec or plan. Local search
also covers these pages. Related records use explicit links in the documents;
indexes do not guess semantic relationships from similar filenames or assert
that every historical record has complete cross-links.

## Keeping indexes current

`npm run docs:dev` and `npm run docs:build` regenerate the indexes. If a record is
added while a development server is already running, run `npm run records:indices`
from `docs/` (or restart the docs server) to refresh the listing. There is no
additional index watcher. Commit the generated index changes with the records.

Preserve historical decisions and outcomes when adding links. Private scratch
payloads are not published here; safe summaries belong in tracked documentation.
See the [live-dev preservation workflow](/dev/features/live-dev#development-records)
and its [investigation and validation ledger](/plans/2026-10-28-development-records-progress).
