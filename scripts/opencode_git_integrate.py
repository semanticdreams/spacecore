#!/usr/bin/env python3
"""Guarded Git integration operations for OpenCode capability agents."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from opencode_capabilities import (
    CapabilityError,
    CommandResult,
    ensure_space_repo,
    failure,
    human_decision,
    run_command,
    success,
    validate_branch_name,
)


_GITHUB_REF_BYTE_LIMIT = 255
_GIT_HEAD_REF_PREFIX = "refs/heads/"
_LOCAL_REF_COMPONENT_BYTE_LIMIT = 255


def _exit_code_for(result: dict[str, object]) -> int:
    if result.get("status") == "pass":
        return 0
    if result.get("status") == "human_decision_required":
        return 2
    return 3


def _current_branch(repo: Path) -> str:
    return run_command(["git", "branch", "--show-current"], repo).stdout.strip()


def _dirty_output(repo: Path) -> str:
    return run_command(["git", "status", "--porcelain"], repo).stdout


def _origin_main_is_ancestor_of_head(repo: Path) -> bool:
    result = run_command(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"], repo, check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise CapabilityError(
        "command_failed",
        "Command failed while evaluating capability guard",
        {"args": result.args, "returncode": result.returncode, "stderr": result.stderr.strip()},
    )


def _is_safe_ref_name(branch: str) -> bool:
    full_ref = f"{_GIT_HEAD_REF_PREFIX}{branch}"
    return len(full_ref.encode("utf-8")) <= _GITHUB_REF_BYTE_LIMIT and all(
        len(part.encode("utf-8")) <= _LOCAL_REF_COMPONENT_BYTE_LIMIT for part in full_ref.split("/")
    )


def _derive_followup_branch_name(source_branch: str, short_head_sha: str) -> str:
    candidate = f"{source_branch}-followup-{short_head_sha}"
    if _is_safe_ref_name(candidate):
        return candidate
    return f"fix/followup-{short_head_sha}"



def _derive_local_main_wrapup_branch_name(short_head_sha: str) -> str:
    return f"fast-dev/local-main-{short_head_sha}"


def _local_commits_beyond_origin_main(repo: Path) -> int:
    args = ["git", "rev-list", "--count", "origin/main..HEAD"]
    raw = run_command(args, repo).stdout.strip()
    try:
        return int(raw)
    except ValueError as error:
        raise CapabilityError(
            "command_failed",
            "Command failed while evaluating local-main wrap-up commit range",
            {"args": args, "stdout": raw},
        ) from error


def _local_branch_exists(repo: Path, branch: str) -> bool:
    ref = f"refs/heads/{branch}"
    result = run_command(["git", "show-ref", "--verify", "--quiet", ref], repo, check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise CapabilityError(
        "command_failed",
        "Command failed while evaluating capability guard",
        {"args": result.args, "returncode": result.returncode, "stderr": result.stderr.strip()},
    )


def _remote_branch_exists(repo: Path, branch: str) -> bool:
    result = run_command(["git", "ls-remote", "--exit-code", "--heads", "origin", branch], repo, check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 2:
        return False
    raise CapabilityError(
        "command_failed",
        "Command failed while evaluating capability guard",
        {"args": result.args, "returncode": result.returncode, "stderr": result.stderr.strip()},
    )


def _guard_clean_non_main(action: str, repo: Path) -> tuple[str | None, dict[str, object] | None]:
    dirty = _dirty_output(repo).strip()
    branch = _current_branch(repo)
    if dirty:
        return None, human_decision(action, "Worktree is dirty; privileged Git operation requires a clean tree", {"branch": branch, "dirty": True})
    if branch == "main":
        return None, human_decision(action, "Refusing privileged Git operation on protected main branch", {"branch": branch})
    try:
        validate_branch_name(branch)
    except CapabilityError as error:
        return None, human_decision(action, error.message, {"code": error.code, "details": error.details, "branch": branch})
    return branch, None


def git_status(repo_root: Path) -> dict[str, object]:
    action = "git_status"
    try:
        repo = ensure_space_repo(repo_root)
        branch = _current_branch(repo)
        head_sha = run_command(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        origin_main_sha = run_command(["git", "rev-parse", "origin/main"], repo).stdout.strip()
        dirty = bool(_dirty_output(repo).strip())
        merge_base = run_command(["git", "merge-base", "HEAD", "origin/main"], repo).stdout.strip()
        origin_main_is_ancestor = _origin_main_is_ancestor_of_head(repo)
        return success(
            action,
            "Git status collected for bounded integration decision",
            {
                "branch": branch,
                "head_sha": head_sha,
                "dirty": dirty,
                "origin_main_merge_base": merge_base,
                "origin_main_sha": origin_main_sha,
                "origin_main_is_ancestor_of_head": origin_main_is_ancestor,
                "branch_current_with_origin_main": origin_main_is_ancestor,
                "safe_merge_needed": not origin_main_is_ancestor,
            },
        )
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})


def fetch_origin(repo_root: Path) -> dict[str, object]:
    action = "fetch_origin"
    try:
        repo = ensure_space_repo(repo_root)
        result = run_command(["git", "fetch", "origin", "main"], repo)
        return success(action, "Fetched origin/main for bounded integration", {"args": result.args})
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})


def merge_origin_main(repo_root: Path) -> dict[str, object]:
    action = "merge_origin_main"
    try:
        repo = ensure_space_repo(repo_root)
        branch, unsafe = _guard_clean_non_main(action, repo)
        if unsafe is not None:
            return unsafe
        fetch = run_command(["git", "fetch", "origin", "main"], repo)
        merge = run_command(["git", "merge", "--no-edit", "origin/main"], repo)
        return success(action, "Merged origin/main into current branch", {"branch": branch, "commands": [fetch.args, merge.args]})
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})


def push_current(repo_root: Path) -> dict[str, object]:
    action = "push_current"
    try:
        repo = ensure_space_repo(repo_root)
        branch, unsafe = _guard_clean_non_main(action, repo)
        if unsafe is not None:
            return unsafe
        destination = f"HEAD:refs/heads/{branch}"
        result = run_command(["git", "push", "origin", destination], repo)
        return success(action, "Pushed current branch to matching origin branch", {"branch": branch, "args": result.args})
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})


def create_followup_branch(repo_root: Path) -> dict[str, object]:
    action = "create_followup_branch"
    try:
        repo = ensure_space_repo(repo_root)
        dirty = _dirty_output(repo).strip()
        branch = _current_branch(repo)
        if dirty:
            return human_decision(action, "Worktree is dirty; follow-up branch creation requires a clean tree", {"branch": branch, "dirty": True})
        if not branch:
            return human_decision(action, "Refusing follow-up branch creation from detached HEAD", {"branch": branch})
        if branch == "main":
            return human_decision(action, "Refusing follow-up branch creation on protected main branch", {"branch": branch})

        short_head_sha = run_command(["git", "rev-parse", "--short=7", "HEAD"], repo).stdout.strip()
        if not _origin_main_is_ancestor_of_head(repo):
            return human_decision(
                action,
                "Current HEAD does not contain origin/main; update through the bounded merge workflow before creating a follow-up branch",
                {"branch": branch, "origin_main_is_ancestor_of_head": False},
            )

        target_branch = _derive_followup_branch_name(branch, short_head_sha)
        try:
            validate_branch_name(branch)
            validate_branch_name(target_branch)
        except CapabilityError as error:
            return human_decision(action, error.message, {"code": error.code, "details": error.details, "branch": branch, "followup_branch": target_branch})

        if _local_branch_exists(repo, target_branch):
            return human_decision(action, "Follow-up branch already exists locally", {"branch": branch, "followup_branch": target_branch})
        if _remote_branch_exists(repo, target_branch):
            return human_decision(action, "Follow-up branch already exists on origin", {"branch": branch, "followup_branch": target_branch})

        switch = run_command(["git", "switch", "-c", target_branch], repo)
        return success(
            action,
            "Created and switched to deterministic follow-up branch",
            {"source_branch": branch, "followup_branch": target_branch, "short_head_sha": short_head_sha, "args": switch.args},
        )
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})


def create_local_main_wrapup_branch(repo_root: Path) -> dict[str, object]:
    action = "create_local_main_wrapup_branch"
    try:
        repo = ensure_space_repo(repo_root)
        dirty = _dirty_output(repo).strip()
        branch = _current_branch(repo)
        if dirty:
            return human_decision(action, "Worktree is dirty; local-main wrap-up requires a clean tree", {"branch": branch, "dirty": True})
        if not branch:
            return human_decision(action, "Refusing local-main wrap-up branch creation from detached HEAD", {"branch": branch})
        if branch != "main":
            return human_decision(action, "Refusing local-main wrap-up branch creation from non-main branch", {"branch": branch})

        run_command(["git", "fetch", "origin", "main"], repo)
        short_head_sha = run_command(["git", "rev-parse", "--short=7", "HEAD"], repo).stdout.strip()
        source_head_sha = run_command(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        origin_main_sha = run_command(["git", "rev-parse", "origin/main"], repo).stdout.strip()
        local_commits = _local_commits_beyond_origin_main(repo)
        if local_commits == 0:
            return human_decision(
                action,
                "Local main has no commits beyond origin/main; no wrap-up branch is needed",
                {"branch": branch, "origin_main_sha": origin_main_sha, "source_head_sha": source_head_sha, "local_commits_beyond_origin_main": local_commits},
            )

        target_branch = _derive_local_main_wrapup_branch_name(short_head_sha)
        try:
            validate_branch_name(target_branch)
        except CapabilityError as error:
            return human_decision(action, error.message, {"code": error.code, "details": error.details, "wrapup_branch": target_branch})

        if _local_branch_exists(repo, target_branch):
            return human_decision(action, "Local-main wrap-up branch already exists locally", {"wrapup_branch": target_branch})
        if _remote_branch_exists(repo, target_branch):
            return human_decision(action, "Local-main wrap-up branch already exists on origin", {"wrapup_branch": target_branch})

        switch = run_command(["git", "switch", "-c", target_branch], repo)
        return success(
            action,
            "Created and switched to deterministic local-main wrap-up branch",
            {
                "source_branch": branch,
                "wrapup_branch": target_branch,
                "short_head_sha": short_head_sha,
                "source_head_sha": source_head_sha,
                "origin_main_sha": origin_main_sha,
                "local_commits_beyond_origin_main": local_commits,
                "args": switch.args,
            },
        )
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})


def _daily_commit_sha(sha: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
        raise CapabilityError("invalid_git_evidence", "Expected one full Git commit SHA", {"sha": sha})
    return sha


def _daily_remote_sha(result: CommandResult, target: str) -> str | None:
    if result.returncode == 2 and not result.stdout:
        return None
    if result.returncode not in (0, 2):
        raise CapabilityError("command_failed", "Cannot inspect live origin target", {
            "args": result.args, "returncode": result.returncode, "stderr": result.stderr.strip(),
        })
    fields = result.stdout.removesuffix("\n").split("\t")
    if result.returncode != 0 or len(fields) != 2 or fields[1] != f"refs/heads/{target}":
        raise CapabilityError("invalid_git_evidence", "Expected one exact live origin ref", {"stdout": result.stdout})
    return _daily_commit_sha(fields[0])


def _daily_worktree_records(raw: str) -> list[dict[str, str]]:
    """Parse Git's NUL fields, never traverse or repair worktree directories."""
    if not raw or not raw.endswith("\0\0"):
        raise CapabilityError("invalid_git_evidence", "Worktree registrations must be NUL-delimited")
    records = []
    for record in raw[:-2].split("\0\0"):
        fields: dict[str, str] = {}
        for field in record.split("\0"):
            key, separator, value = field.partition(" ")
            if key not in {"worktree", "HEAD", "branch", "detached", "bare", "locked", "prunable"} or key in fields:
                raise CapabilityError("invalid_git_evidence", "Unknown or duplicate worktree field", {"field": field})
            if key in {"worktree", "HEAD", "branch"} and (not separator or not value):
                raise CapabilityError("invalid_git_evidence", "Missing worktree field value", {"field": field})
            if key in {"bare", "detached"} and separator:
                raise CapabilityError("invalid_git_evidence", "Malformed worktree marker", {"field": field})
            fields[key] = value
        if not Path(fields.get("worktree", "")).is_absolute():
            raise CapabilityError("invalid_git_evidence", "Worktree registration lacks an absolute path")
        modes = sum(key in fields for key in ("branch", "detached", "bare"))
        if modes != 1 or ("bare" in fields and "HEAD" in fields) or ("bare" not in fields and "HEAD" not in fields):
            raise CapabilityError("invalid_git_evidence", "Ambiguous worktree registration", {"record": fields})
        if "HEAD" in fields:
            _daily_commit_sha(fields["HEAD"])
        if "branch" in fields:
            ref = fields["branch"]
            # Other worktrees need valid Git refs, not the capability's narrower
            # allowed-source policy. Do not reject legitimate unrelated topics.
            if (not ref.startswith("refs/heads/") or ref.endswith(".") or ".." in ref or "@{" in ref
                    or re.search(r"[\x00-\x20\x7f~^:?*\[\\]", ref)
                    or any(not part or part.startswith(".") or part.endswith(".lock") for part in ref.split("/"))):
                raise CapabilityError("invalid_git_evidence", "Worktree branch is not a valid full local ref", {"record": fields})
        records.append(fields)
    if len({record["worktree"] for record in records}) != len(records):
        raise CapabilityError("invalid_git_evidence", "Duplicate worktree registrations")
    return records


def create_daily_devlog_branch(repo_root: Path) -> dict[str, object]:
    action = "create_daily_devlog_branch"
    commands: list[list[str]] = []
    evidence: dict[str, object] = {"commands": commands, "already_current": False}
    try:
        repo = ensure_space_repo(repo_root)

        def execute(args: list[str], *, check: bool = True) -> CommandResult:
            commands.append(args)
            return run_command(args, repo, check=check)

        def state() -> tuple[str, str, str]:
            dirty = execute(["git", "status", "--porcelain", "--untracked-files=all"]).stdout
            branch = execute(["git", "branch", "--show-current"]).stdout.strip()
            head = _daily_commit_sha(execute(["git", "rev-parse", "--verify", "HEAD^{commit}"]).stdout.removesuffix("\n"))
            return dirty, branch, head

        dirty = execute(["git", "status", "--porcelain", "--untracked-files=all"]).stdout
        source = execute(["git", "branch", "--show-current"]).stdout.strip()
        evidence.update(source_branch=source, dirty=bool(dirty))
        if dirty or not source or source == "main":
            return human_decision(action, "Daily devlog preparation requires a clean, named non-main source", evidence)
        try:
            validate_branch_name(source)
        except CapabilityError as error:
            return human_decision(action, error.message, {**evidence, "code": error.code, "details": error.details})
        source_sha = _daily_commit_sha(execute(["git", "rev-parse", "--verify", "HEAD^{commit}"]).stdout.removesuffix("\n"))
        utc_date = datetime.now(timezone.utc).date().isoformat()
        target = f"automation/daily-devlog/{utc_date}"
        validate_branch_name(target)
        evidence.update(utc_date=utc_date, source_head_sha=source_sha, target_branch=target)

        execute(["git", "fetch", "--no-tags", "origin", "refs/heads/main:refs/remotes/origin/main"])
        base_sha = _daily_commit_sha(execute(["git", "rev-parse", "--verify", "refs/remotes/origin/main^{commit}"]).stdout.removesuffix("\n"))
        evidence["origin_main_sha"] = base_sha
        local = execute(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"], check=False)
        if local.returncode not in (0, 1):
            raise CapabilityError("command_failed", "Cannot inspect exact local target", {
                "args": local.args, "returncode": local.returncode, "stderr": local.stderr.strip(),
            })
        if local.stdout:
            raise CapabilityError("invalid_git_evidence", "Quiet local ref check returned unexpected output", {"stdout": local.stdout})
        local_sha = None
        if local.returncode == 0:
            local_sha = _daily_commit_sha(execute(["git", "rev-parse", "--verify", f"refs/heads/{target}^{{commit}}"]).stdout.removesuffix("\n"))
        evidence.update(local_target_exists=local.returncode == 0, local_target_sha=local_sha)
        remote_sha = _daily_remote_sha(execute([
            "git", "ls-remote", "--exit-code", "--heads", "origin", f"refs/heads/{target}",
        ], check=False), target)
        evidence["remote_target_sha"] = remote_sha
        worktrees = _daily_worktree_records(execute(["git", "worktree", "list", "--porcelain", "-z"]).stdout)
        current = [record for record in worktrees if record["worktree"] == str(repo)]
        if len(current) != 1 or current[0].get("branch") != f"refs/heads/{source}" or current[0].get("HEAD") != source_sha:
            raise CapabilityError("invalid_git_evidence", "Current worktree registration does not match captured source", {"worktrees": worktrees})
        holders = [record for record in worktrees if record["worktree"] != str(repo) and record.get("branch") == f"refs/heads/{target}"]
        evidence.update(worktrees=worktrees, other_worktree_holders=holders)
        if holders:
            return human_decision(action, "Daily target is registered in another worktree; no cleanup is permitted", evidence)
        already_target = source == target
        if not already_target and (local_sha is not None or remote_sha is not None):
            return human_decision(action, "Daily target already exists; ownership/resumption decision required", evidence)
        if already_target and (source_sha != base_sha or local_sha != base_sha or remote_sha not in (None, base_sha)):
            return human_decision(action, "Daily target is not an untouched retry at fresh origin/main", evidence)

        dirty, branch, head = state()
        if dirty or branch != source or head != source_sha:
            return human_decision(action, "Source state changed during daily devlog preparation", {**evidence, "observed_branch": branch, "head_sha": head, "dirty": bool(dirty)})
        if not already_target:
            execute(["git", "switch", "--no-track", "-c", target, base_sha])
            dirty, branch, head = state()
            if dirty or branch != target or head != base_sha:
                return failure(action, "Daily branch postconditions failed; no rollback attempted", {**evidence, "observed_branch": branch, "head_sha": head, "dirty": bool(dirty)})
        evidence.update(already_current=already_target, head_sha=head, branch=branch, dirty=False)
        return success(action, "Daily devlog branch prepared at freshly fetched origin/main without publication", evidence)
    except CapabilityError as error:
        return failure(action, error.message, {**evidence, "code": error.code, "details": error.details})


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "fetch-origin", "merge-origin-main", "push-current", "create-followup-branch", "create-local-main-wrapup-branch", "create-daily-devlog-branch"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--repo-root", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    operations = {
        "status": git_status,
        "fetch-origin": fetch_origin,
        "merge-origin-main": merge_origin_main,
        "push-current": push_current,
        "create-followup-branch": create_followup_branch,
        "create-local-main-wrapup-branch": create_local_main_wrapup_branch,
        "create-daily-devlog-branch": create_daily_devlog_branch,
    }
    try:
        result = operations[args.command](args.repo_root)
    except Exception as error:  # noqa: BLE001 - CLIs must fail closed with structured JSON.
        result = failure(args.command.replace("-", "_"), "Local Git capability wrapper failed unexpectedly", {"error_type": type(error).__name__, "error": str(error)})
    print(json.dumps(result, indent=2, sort_keys=True))
    return _exit_code_for(result)


if __name__ == "__main__":
    raise SystemExit(main())
