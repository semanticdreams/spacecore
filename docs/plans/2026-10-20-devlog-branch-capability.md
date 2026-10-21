# Daily Devlog Branch Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the strict daily automation to prepare its required dated branch through one exact guarded capability.

**Architecture:** Add an internal UTC-derived operation to the current Git wrapper, expose only its exact invocation in the Git agent and permission checker, and retain existing trust/branch policy. Use a captured freshly fetched main SHA, conservative collision checks and no-track creation; validate activation in a fresh automation process without modifying unrelated home configuration.

**Tech Stack:** Python standard library, Git, pytest, OpenCode agent Markdown, VitePress.

## Global Constraints

- "No caller-supplied date, branch, base, remote, force, cleanup or generic branch-creation arguments."
- "No pruning, unlocking, force or deletion."
- "No push, merge, rebase or implicit publication."
- "Leave all home configuration, backups and plugins untouched."
- "Do not edit skills or the supervisor."
- Specification: `docs/specs/2026-10-20-devlog-branch-capability-design.md`.
- Existing JSON envelope, exit codes, trust and branch policy remain unchanged.

---

### Task 1: Implement and Authorize Exact Dated Branch Preparation

**Files:**
- Modify `scripts/opencode_git_integrate.py`: new operation, CLI dispatch, bounded private readers.
- Modify `.opencode/agents/git-integrator.md`: one exact allow entry and usage contract.
- Modify `scripts/check_opencode_permissions.py`: one exact expected command.
- Modify `scripts/tests/test_opencode_git_integrate.py`: behavior and real-Git regression coverage.
- Modify `scripts/tests/test_check_opencode_permissions.py`: exact permission fixtures and denial cases.
- Modify `docs/dev/features/opencode-agent-workflow.md`: canonical operation/reference and fresh-session guidance.

**Interfaces:** Add `create_daily_devlog_branch(repo_root: Path) -> dict[str, object]`, CLI/action `create-daily-devlog-branch` / `create_daily_devlog_branch`. Reuse `ensure_space_repo`, `validate_branch_name`, `run_command` and result helpers. Consume no user-controlled branch/date/base inputs. Produce date, source branch/SHA, target branch, fresh origin/main SHA, resulting HEAD, collision facts, command list and `already_current` evidence.

- [ ] **Step 1: Establish baseline and write RED tests.** Run affected existing modules first. Add `test_daily_devlog_*` tests for missing operation and exact allowlist requirement. Assert meaningful failure, not collection/setup errors. Example source guard:

```python
def test_daily_devlog_refuses_main_before_fetch(monkeypatch, trusted_repo):
    runner = GitRunner({
        ("git", "status", "--porcelain", "--untracked-files=all"): "",
        ("git", "branch", "--show-current"): "main\n",
    })
    monkeypatch.setattr(git_integrate, "run_command", runner)
    result = git_integrate.create_daily_devlog_branch(trusted_repo)
    assert result["status"] == "human_decision_required"
    assert not any(call[1] in {"fetch", "switch"} for call in runner.calls)
```

- [ ] **Step 2: Implement ordered guards and pinned creation.** Check trusted repo, tracked/untracked cleanliness, named non-main allowed source before fetch. Capture source branch/SHA and sample UTC once. Use exactly:

```python
utc_date = datetime.now(timezone.utc).date().isoformat()
target = f"automation/daily-devlog/{utc_date}"
fetch_args = ["git", "fetch", "--no-tags", "origin",
              "refs/heads/main:refs/remotes/origin/main"]
base_args = ["git", "rev-parse", "--verify", "refs/remotes/origin/main^{commit}"]
switch_args = ["git", "switch", "--no-track", "-c", target, base_sha]
```

Validate full SHA and errors; no forced fetch/fallback. Inspect exact local ref, `git ls-remote --exit-code --heads origin refs/heads/<target>` and `git worktree list --porcelain -z`. Remote exit2 means absent; success must supply one valid exact ref/SHA; other status/malformed data refuses. Parse worktree NUL fields and refuse another holder, including locked/prunable records. No directory traversal/pruning. Refuse existing local/remote target from another source. Idempotent pass only already target, clean HEAD==fresh base, no other holder and remote absent/equal base. Recheck source/clean state before switch; verify resulting branch/SHA/clean state after. Failed postconditions remain failures without rollback.

- [ ] **Step 3: Add exact authorization and document.** Add only `python3 scripts/opencode_git_integrate.py create-daily-devlog-branch --repo-root .` to agent allowlist and checker set; preserve wildcard deny. Update agent body and canonical doc with UTC derivation, fresh pinned base, no-track creation, conservative collisions/no-op rules, no-push boundary and mandatory fresh session after agent updates. Do not modify skills, generic permissions, shared trust helper or home files.

- [ ] **Step 4: Complete tests and GREEN.** Cover UTC midnight/single clock sample; all unsafe sources; source commits not copied; exact fresh SHA; local/live-remote/worktree collisions and exact matching; locked/prunable entries; strict no-op and progressed-target refusal; malformed/error Git evidence; fetch/switch/postcondition failures; CLI envelope/status/extra argument denial; exact permission required, wildcard/freeform/suffix/raw Git grants rejected. Explicitly supply all mock responses so missing mocks cannot imply safe absence. Use disposable real Git repos and bare remotes for creation, preservation, `branch.autoSetupMerge=always` no-upstream, and another-worktree collision. Mock repository trust only inside disposable fixtures; no real network/mutation smoke on implementation branch.

- [ ] **Step 5: Run relevant validation and package review.** Focused affected tests, then `make opencode-check`, `python3 -m pytest scripts/tests/test_opencode_pr_recovery.py -q`, whitespace check, and docs build with `NODE_OPTIONS=--max-old-space-size=4096` if needed. No native/Fennel checks apply. Capture RED/GREEN coverage rationale and write an ignored report plus exact uncommitted `git diff -U10 <task-base> -- <six files>` review package. Dispatch reviewer before committing. Fix through implementer/reviewer until pass. No broad Git/GitHub permission requests.

- [ ] **Step 6: Commit and integrate reviewed repair.** Commit only reviewed six files. Fetch current origin/main through capability; safe merge if necessary and rerun validation from clean committed tree. Full branch review covers spec/plan/task. Push through git-integrator, create PR via github-operator, recover stale merged branch PR through pr-recovery-operator if required, queue and poll until actual mergedAt. Existing Git operations are sufficient; do not invoke newly granted operation from this old session.

- [ ] **Step 7: Fresh-run end-to-end acceptance.** Start a new automation OpenCode process from landed origin/main; this is the required restart for project-local agent permissions. Verify landed operation ancestry, successful exact wrapper invocation, today's dated branch at freshly fetched base, and progression past run84 blocker. Inspect actual agent output, not scheduler completion. If meaningful entry warranted, require implementer/reviewer, docs validation, commit/push and actual devlog PR merge. Existing home audit remains accurately recorded as refused; no claim of home audit success is needed to observe project-local capability activation. Do not start historical backfill or change unrelated host settings.

Self-review: one coherent task covers missing behavior, exact authorization, regressions and owning docs; all spec guards and end-to-end acceptance are mapped. Home preservation and new-session activation avoid an unrelated cleanup project.
