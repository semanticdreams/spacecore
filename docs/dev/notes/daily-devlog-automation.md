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
Run the repo's daily devlog automation. Inspect recent meaningful development changes, write today's brief narrative devlog entry if warranted, validate it, commit it, push an automation branch, and open/auto-merge a pull request when repository policy allows.
```

The UI prompt is intentionally short because `.opencode/skills/daily-devlog-automation/SKILL.md` owns the durable workflow.

## Repo-owned workflow

- `.opencode/opencode.json` keeps `default_agent: supervisor`.
- The skill name is `daily-devlog-automation`.
- Daily runs push `automation/daily-devlog/YYYY-MM-DD`, open a PR, and attempt auto-merge when available.
- Direct pushes to `origin/main` are not the default path.
- Daily runs skip entry creation when no meaningful changes exist.

## Landing-date attribution

`origin/main` is the source of truth for deciding what recent work belongs in a daily entry. The automation attributes work to the date it lands or merges into `origin/main`, regardless of the original author date or feature-branch commit date. Older feature-branch commits merged today are eligible for today's entry; author or original commit dates must not cause landed work to be skipped or backdated into an already-published entry.

Agents should inspect mainline/first-parent history, merge commits, PR merges, or equivalent landed ranges on `origin/main` since the latest relevant journal entry or recent day boundary. If `origin/main` cannot be fetched or inspected, or if the mainline/merge evidence is ambiguous, the run fails closed with a BLOCKED summary instead of guessing from local branch history.

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

Generated indexes are kept up to date by the automation workflow. If a run produces a stale or malformed entry, discard the branch and re-run from a clean state.

## Orca / OpenCode project-config caveat

Orca-launched OpenCode may set `OPENCODE_DISABLE_PROJECT_CONFIG=1`, which prevents the runner from loading repo-local `.opencode/**` configuration (skills, agents, opencode.json). After any changes to `.opencode/**`, the scheduled runner must either be configured to allow repo-local config or the operator must synchronize the updated skill/agent definitions into the global OpenCode configuration and restart the OpenCode session. Without this, stale skill definitions may cause unexpected behavior or miss critical repo-owned policy updates.
