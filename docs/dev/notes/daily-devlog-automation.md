---
type: note
tags:
  - automation
  - devlog
  - opencode
created: 2026-07-29
---

# Daily Devlog Automation

## Purpose

The daily devlog automation generates brief narrative journal entries capturing meaningful development work. It is triggered through a scheduled Orca UI prompt that invokes the repo-owned `daily-devlog-automation` OpenCode skill. The automation inspects recent changes, decides whether a new entry is warranted, validates it, and publishes it through a pull request workflow.

## Orca UI setup

1. Select OpenCode in Orca UI.
2. Use this repository checkout as the working directory.
3. Schedule the automation daily.

After any changes to `.opencode/**` (skills, agents, or configuration), restart OpenCode/Orca so the updated skill definitions are loaded.

### Remote-host automation target

When scheduling automations for a remote Orca host from a laptop or web
UI, Orca may save the automation run target as a transient remote runtime
hostId (e.g. `runtime:<uuid>`). For unattended host-side scheduling on
this repo, the automation must target the durable local project host
setup on the server, whose `runContext.hostId` should be `local`.

If the automation is bound to `runtime:<uuid>`, manual and scheduled runs
can be recorded as `skipped_unavailable` with no workspace or session
created, and may produce an error like:

> Remote-server automation scheduling is not available from this Orca
> client yet…

**Remediation:** Create or edit remote-host automations from the
server-side Orca CLI, or explicitly pass `--project-host-setup <setup-id>`.

```bash
# List available project host setups
orca project setups --json

# Inspect the current automation target
orca automations show --id <automation-id> --json

# Retarget to the local project host setup
orca automations edit --id <automation-id> \
  --project-host-setup <setup-id> --json
```

**Verification:** `runContext.hostId` must be `local`. Values starting
with `runtime:` indicate a transient runtime binding unsuitable for
durable scheduled host-side automation on current Orca versions.

## Prompt

```text
Run the repo's daily devlog automation. Recover meaningful uncovered work since the latest journal, creating a brief narrative entry for each warranted missing landing date or autonomously correcting an existing entry on its actual landing date; preserve accurate existing content. Review and validate the changes, then publish through a protected pull request on the run's automation branch and auto-merge when repository policy allows.
```

The UI prompt is intentionally short because `.opencode/skills/daily-devlog-automation/SKILL.md` owns the durable workflow.

## Repo-owned workflow

- `.opencode/opencode.json` keeps `default_agent: supervisor`.
- The skill name is `daily-devlog-automation`.
- Daily runs push `automation/daily-devlog/YYYY-MM-DD`, open a PR, and attempt auto-merge when available.
- Direct pushes to `origin/main` are not the default path.
- Daily runs include prior-day catch-up without a separate request. No-op requires a fully examined interval and no unresolved meaningful work, not merely a quiet run date.

The guarded `create-daily-devlog-branch` wrapper prepares the branch and supplies
`origin_main_sha`, `utc_date`, and `target_branch` evidence. The agent owns
meaningfulness and semantic coverage assessment, journal writing, and review
handoffs. Existing index generators list existing sources; they cannot detect
missing narratives or prove coverage. The manual devlog opener/publisher does not
assess coverage or discover missed landing days; it is not the scheduled agent's
discovery mechanism. No new CLI, coverage schema, or persistent ledger is needed.

## Landing-date attribution

`origin/main` is the source of truth for deciding what recent work belongs in a daily entry. The automation attributes work to the date it lands or merges into `origin/main`, regardless of the original author date or feature-branch commit date. Older feature-branch commits merged today are eligible for today's entry; author or original commit dates must not cause landed work to be skipped or backdated into an already-published entry.

Pin fetched `origin/main` and read the latest dated journal source's actual
narrative at that snapshot. Inspect every first-parent landing day from the start
of that journal date in UTC (00:00:00Z), inclusively, through the pinned tip,
including landed deltas and references. Do not substitute today, a fixed lookback,
or the journal publication commit. Source presence and generated indexes do not
prove semantic coverage; document filenames and author dates do not prove landing
dates. If the boundary or mainline evidence is unavailable or ambiguous,
investigate and fail closed with the missing evidence/decision rather than guess.

The UTC run date is independent of journal dates: one run may create several
warranted missing landing-date entries, with timestamps converted to UTC. An
October 23 branch can recover October 22 without creating an October 23 entry.
Skip already-covered or non-meaningful candidates with reasons, not filler.
Autonomously correct omissions in existing entries on their actual landing dates.
Preserve accurate narrative, useful links, dates/frontmatter and attribution, and
retain the single short paragraph and compression/style pass. Source presence alone
is not a human decision or successful no-op. An explicit immutable-publication
restriction is a real conflict to surface, not override. Use
`AGENTS.md#autonomous-workflow-decisions` within existing scope and authority.

Before no-op, account for the whole interval with the pinned tip, inclusive
boundary, concise covered/skipped reasons, created/corrected dates and unresolved
explicit restrictions in the normal review handoff. If
pre-PR freshness finds a different main tip, pin it and repeat discovery,
reconciling pending entries with newly published sources and reviewing any repairs.
After PR queue entry, merge queue handles freshness; do not chase main movement.

## Safety model

The automation fails closed when credentials, `gh` authentication, branch protection (classic protection or GitHub rulesets/effective branch rules), required status checks, pull-request protection, or a clean checkout are unavailable. Auto-merge uses the [guarded merge-policy proof](../features/opencode-agent-workflow.md#guarded-merge-policy-proof): complete effective rules and repository permissions must prove a safe merge or squash queue method, then the helper requests auto-merge without a client strategy because GitHub's queue controls the final method; rebase-only or unproven policy requires a human decision. Daily entries contain only frontmatter, a date heading, and one short narrative paragraph connecting concrete landed work to current project goals or milestones. Inline Markdown links are allowed when they point to relevant docs, notes, plans, specs, or feature pages and improve reader context, but separate link lists, bullet-point summaries, section headings, commit hashes, author lists, and raw file lists are forbidden.

## Validation and recovery

Fresh checkouts may lack `docs/node_modules` or `vitepress`. Install locked docs dependencies before building:

```bash
cd docs
if [ ! -d node_modules ] || [ ! -x node_modules/.bin/vitepress ]; then npm ci; fi
```

Then regenerate docs indexes and validate the build:

```bash
npm run devlog:indices
npm run docs:build
```

Generated indexes are kept up to date by the automation workflow. If a run
produces a stale or malformed entry, diagnose it and route a reviewed repair
through the owning skill's validation-failure workflow, not blanket branch
discard. Every implementation/fix handoff is stage-only and uncommitted: review
the complete assigned staged diff, including generated changes, before the
supervisor commits exact approved content. Corrections to existing dated sources
use this same reviewed repair lane, not a separate approval merely for source
presence; genuine immutable-publication restrictions remain boundaries. Keep
guarded capability boundaries, clean-tree checks, branch protection, required
tests, and merge-queue polling through actual merge unchanged.

## Orca / OpenCode project-config caveat

Orca-launched OpenCode may set `OPENCODE_DISABLE_PROJECT_CONFIG=1`, which prevents the runner from loading repo-local `.opencode/**` configuration (skills, agents, opencode.json). After any changes to `.opencode/**`, the scheduled runner must either be configured to allow repo-local config or the operator must synchronize the updated skill/agent definitions into the global OpenCode configuration and restart the OpenCode session. Without this, stale skill definitions may cause unexpected behavior or miss critical repo-owned policy updates.
