# Guarded daily-devlog branch preparation

## Observed failure and scope

Fresh automation run84 started at landed main a60bc99, loaded the repaired GitHub helper and passed PR/test/queue/method checks, but stopped clean before writing: no approved Git operation creates the required dated automation branch. `scripts/opencode_git_integrate.py` exposes follow-up/local-main branch operations only; `.opencode/agents/git-integrator.md` and the permission checker enumerate those exact operations. The existing daily skill requires an `automation/daily-devlog/YYYY-MM-DD` branch.

The user explicitly wants automation restored without decisions about unrelated home files. Leave all home configuration, backups and plugins untouched. The separate home auditor's refusal does not establish an application failure and is not a prerequisite to changing project-local capability definitions. Do not broaden home access or declare that audit passed. Verify activation by a fresh OpenCode process in the landed project checkout and actual authorized invocation, not by assuming an old process reloads permissions.

## Chosen approach

Add one exact Git capability invocation:

```text
python3 scripts/opencode_git_integrate.py create-daily-devlog-branch --repo-root .
```

Derive today's UTC date internally. No caller-supplied date, branch, base, remote, force, cleanup or generic branch-creation arguments. Existing trust and branch-name policy already cover the required repository and dated branch pattern. Extend the existing wrapper, exact agent allowlist, permission checker, two existing test modules and canonical workflow docs. Do not edit skills or the supervisor.

Reusing follow-up creation would copy source HEAD rather than fresh main. Granting raw Git or wildcard permissions would unnecessarily widen authority. The new bounded operation supplies the missing behavior without either compromise.

## Operation contract

1. Require trusted Space repository, clean status including untracked files, named non-main source accepted by existing branch policy. Refuse unsafe source before fetching. Capture source ref/SHA without mutating that ref.
2. Sample timezone-aware UTC date once. Fetch with non-forced explicit refspec `git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main`; resolve `refs/remotes/origin/main^{commit}` and pin the returned commit SHA.
3. Check exact local target, live origin target and NUL-delimited worktree registrations. Validate remote/worktree outputs and fail closed on errors or ambiguity. Refuse target held elsewhere, including locked/prunable records. No pruning, unlocking, force or deletion.
4. From any other source branch, refuse any existing local/remote dated target even if it points at main. Only no-op retry allowed: already on today's exact target, clean HEAD exactly equal freshly fetched main, no other worktree holder, and remote target absent or equal same SHA. A progressed/colliding branch requires ownership/resumption decision, not automatic reset.
5. Recheck source and clean state before creating. Create with `git switch --no-track -c <derived-target> <captured-base-sha>`. Verify branch, HEAD and clean state afterward. Failed postconditions are explicit failures, without rollback.
6. Return existing structured envelope/exit codes with action `create_daily_devlog_branch`, date/source/target/base/HEAD, collision evidence, commands and `already_current`. No push, merge, rebase or implicit publication.

## Validation and delivery

Write focused failing tests before implementation. Cover UTC rollover, literal exact target/base, preservation of source commits, no inherited upstream, dirty/main/detached/untrusted sources, local/remote/worktree collisions, strict idempotency, malformed/error evidence, extra CLI arguments, exact allowlist enforcement, no wildcard permission and no destructive commands. Use disposable real Git repositories for base/upstream/worktree behavior, plus mocked command failures. Run affected pytest, `make opencode-check`, PR-recovery regressions, whitespace review and docs build with process-local Node heap if needed.

Run implementer/reviewer gates, commit, evaluate current origin/main, integrate with required CI/queue and actual mergedAt. This session retains its old permissions and must not invoke the new operation as an activation test. Start a fresh automation OpenCode session from landed origin/main; require the exact capability invocation, correct dated branch and progression through the existing reviewed docs/PR workflow to actual publication. Keep historical backfill separate. The actual run is the end-to-end acceptance gate, not scheduler `completed` alone.

Self-review: the scope is one missing project capability; no unrelated home cleanup, skill rewrite, credential access, generic branch API or change to GitHub protection is required.
