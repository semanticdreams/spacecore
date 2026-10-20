#!/usr/bin/env python3
"""Guarded GitHub PR operations for OpenCode capability agents."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from opencode_capabilities import CapabilityError, ensure_space_repo, failure, human_decision, run_command, success, validate_branch_name

SPACE_REPO = "semanticdreams/spacecore"
PR_VIEW_FIELDS = "state,mergedAt,mergeStateStatus,mergeable,autoMergeRequest,statusCheckRollup,headRefName,headRefOid,url"
NONTERMINAL_STATES = {"queued", "waiting", "pending", "in_progress", "in-progress", "expected", "clean", "unknown", None}
PENDING_ROLLUP_STATUSES = {"queued", "pending", "in-progress", "expected"}
FAILED_ROLLUP_CONCLUSIONS = {"failure", "failed", "cancelled", "timed-out", "action-required"}
DEFAULT_POLL_TIMEOUT_SECONDS = 7200
DEFAULT_POLL_INTERVAL_SECONDS = 100
MAX_FAILED_CHECK_LOG_LINES = 80
MAX_FAILED_CHECK_LOG_CHARS = 12000
GITHUB_ACTIONS_JOB_URL = re.compile(r"^https://github\.com/[^/]+/[^/]+/actions/runs/(\d+)/job/(\d+)(?:[/?#].*)?$")


def _exit_code_for(result: dict[str, object]) -> int:
    if result.get("status") == "pass":
        return 0
    if result.get("status") == "human_decision_required":
        return 2
    return 3


def _safe_branch(action: str, branch: str) -> tuple[str | None, dict[str, object] | None]:
    try:
        return validate_branch_name(branch), None
    except CapabilityError as error:
        return None, human_decision(action, error.message, {"code": error.code, "details": error.details, "branch": branch})


def _current_branch(repo: Path) -> str:
    return run_command(["git", "branch", "--show-current"], repo).stdout.strip()


def _current_head(repo: Path) -> str:
    return run_command(["git", "rev-parse", "HEAD"], repo).stdout.strip()


def _safe_current_branch(action: str, repo: Path) -> tuple[str | None, dict[str, object] | None]:
    return _safe_branch(action, _current_branch(repo))


def _json_loads(text: str) -> Any:
    return json.loads(text) if text.strip() else None


def _command_result_evidence(result: Any, branch: str) -> dict[str, object]:
    return {"branch": branch, "args": result.args, "returncode": result.returncode, "stderr": result.stderr.strip()}


def _is_no_pr_view_result(result: Any) -> bool:
    if result.returncode == 0:
        return False
    output = f"{result.stdout}\n{result.stderr}".lower()
    no_pr_markers = (
        "no pull requests found",
        "no pull request found",
        "could not find any pull requests",
        "could not find any pull request",
    )
    return any(marker in output for marker in no_pr_markers)


def _existing_pr_reuse_evidence(data: dict[str, Any], branch: str, current_head: str, args: list[str]) -> dict[str, object]:
    return {
        "branch": branch,
        "current_head": current_head,
        "pr_head": data.get("headRefOid"),
        "pr_state": data.get("state"),
        "pr_url": data.get("url"),
        "args": args,
    }


def _read_policy_json(
    repo: Path, args: list[str], source: str, blockers: list[str], command_errors: list[dict[str, object]],
    *, allow_classic_404: bool = False,
) -> tuple[Any, str]:
    try:
        result = run_command(args, repo, check=False)
    except CapabilityError as error:
        blockers.append(f"Could not retrieve {source}: {error.message}")
        command_errors.append({"args": args, "code": error.code, "details": error.details})
        return None, "command_failed"
    command = {"args": result.args, "returncode": result.returncode, "stderr": result.stderr.strip()}
    if result.returncode != 0:
        command_errors.append(command)
        if allow_classic_404 and re.search(r"\bHTTP 404\b", result.stderr):
            return None, "unavailable_http_404"
        blockers.append(f"Could not retrieve {source}; inspect command_errors for access or command failure")
        return None, "command_failed"
    try:
        return json.loads(result.stdout), "available"
    except json.JSONDecodeError as error:
        blockers.append(f"Malformed {source} JSON: {error.msg}")
        command_errors.append({**command, "error": str(error)})
        return None, "malformed"


def _complete_effective_rules(pages: Any, blockers: list[str]) -> tuple[list[dict[str, Any]], bool, int]:
    if not isinstance(pages, list) or not pages:
        blockers.append("Malformed effective branch rules: expected a nonempty slurped array of pages")
        return [], False, 0
    for page_index, page in enumerate(pages, 1):
        if not isinstance(page, list):
            blockers.append(f"Malformed effective branch rules page {page_index}: expected an array")
            return [], False, len(pages)
        for rule_index, rule in enumerate(page, 1):
            if not isinstance(rule, dict) or not isinstance(rule.get("type"), str) or not rule["type"].strip():
                blockers.append(f"Malformed effective branch rule {page_index}/{rule_index}: expected an object with nonempty type")
                return [], False, len(pages)
    return [rule for page in pages for rule in page], True, len(pages)


def _check_collection_has_test(checks: Any, source: str, blockers: list[str], *, contexts: bool = False) -> bool:
    if not isinstance(checks, list):
        blockers.append(f"Malformed {source}: expected a check array")
        return False
    has_test = False
    for check in checks:
        context = check if contexts else check.get("context") if isinstance(check, dict) else None
        if not isinstance(context, str) or not context.strip():
            blockers.append(f"Malformed {source}: expected nonempty check context strings")
        elif context == "test":
            has_test = True
    return has_test


def _classic_policy_proofs(protection: dict[str, Any], blockers: list[str]) -> tuple[bool, bool, bool]:
    reviews = protection.get("required_pull_request_reviews")
    has_pr = isinstance(reviews, dict)
    if reviews is not None and not has_pr:
        blockers.append("Malformed classic required_pull_request_reviews: expected an object or null")
    required_checks = protection.get("required_status_checks")
    has_test = False
    if isinstance(required_checks, dict):
        for key in ("contexts", "checks"):
            if key in required_checks:
                found = _check_collection_has_test(required_checks[key], f"classic required_status_checks.{key}", blockers, contexts=key == "contexts")
                has_test = has_test or found
    elif required_checks is not None:
        blockers.append("Malformed classic required_status_checks: expected an object or null")
    linear_history = False
    if "required_linear_history" in protection:
        linear = protection["required_linear_history"]
        if not isinstance(linear, dict) or not isinstance(linear.get("enabled"), bool):
            blockers.append("Malformed classic required_linear_history: expected an object with boolean enabled")
        else:
            linear_history = linear["enabled"]
    return has_pr, has_test, linear_history


def _effective_policy_proofs(rules: list[dict[str, Any]], blockers: list[str]) -> dict[str, Any]:
    has_pr = False
    has_test = False
    has_queue = False
    linear_history = False
    queue_methods: list[str] = []
    restrictions: list[list[str]] = []
    relevant_types = {"pull_request", "required_status_checks", "merge_queue", "required_linear_history"}
    for rule in rules:
        rule_type = rule["type"]
        if rule_type not in relevant_types:
            continue
        parameters = rule.get("parameters", {})
        if not isinstance(parameters, dict):
            blockers.append(f"Malformed effective {rule_type} parameters: expected an object")
            continue
        if rule_type == "pull_request":
            has_pr = True
            if "allowed_merge_methods" in parameters:
                allowed = parameters["allowed_merge_methods"]
                if not isinstance(allowed, list) or any(not isinstance(method, str) or method not in {"merge", "squash", "rebase"} for method in allowed):
                    blockers.append("Malformed pull_request allowed_merge_methods: expected a list of lowercase merge, squash or rebase")
                else:
                    restrictions.append(allowed)
        elif rule_type == "required_status_checks":
            found = _check_collection_has_test(parameters.get("required_status_checks"), "effective required_status_checks", blockers)
            has_test = has_test or found
        elif rule_type == "merge_queue":
            has_queue = True
            method = parameters.get("merge_method")
            if not isinstance(method, str) or method not in {"MERGE", "SQUASH", "REBASE"}:
                blockers.append("Malformed merge_queue merge_method: require explicit MERGE, SQUASH or REBASE")
            else:
                queue_methods.append(method.lower())
        elif rule_type == "required_linear_history":
            linear_history = True
    return {
        "has_pr": has_pr, "has_test": has_test, "has_queue": has_queue,
        "queue_methods": queue_methods, "restrictions": restrictions, "linear_history": linear_history,
    }


def pr_auth_status(repo_root: Path) -> dict[str, object]:
    action = "pr_auth_status"
    try:
        repo = ensure_space_repo(repo_root)
        result = run_command(["gh", "auth", "status"], repo, check=False)
        if result.returncode != 0:
            return human_decision(action, "GitHub CLI authentication is missing or invalid", {"returncode": result.returncode})
        return success(action, "GitHub CLI authentication is available", {"args": result.args})
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})


def check_main_protection(repo_root: Path) -> dict[str, object]:
    action = "check_main_protection"
    try:
        repo = ensure_space_repo(repo_root)
    except CapabilityError as error:
        return human_decision(action, "Could not verify repository for main protection", {"code": error.code, "details": error.details})

    blockers: list[str] = []
    command_errors: list[dict[str, object]] = []
    pages, effective_status = _read_policy_json(
        repo, ["gh", "api", "--paginate", "--slurp", f"repos/{SPACE_REPO}/rules/branches/main?per_page=100"],
        "effective branch rules", blockers, command_errors,
    )
    rules, complete, page_count = [], False, 0
    if effective_status == "available":
        rules, complete, page_count = _complete_effective_rules(pages, blockers)
        if not complete:
            effective_status = "malformed"
    metadata, metadata_status = _read_policy_json(
        repo, ["gh", "api", f"repos/{SPACE_REPO}"], "repository metadata", blockers, command_errors,
    )
    if metadata_status == "available" and not isinstance(metadata, dict):
        blockers.append("Malformed repository metadata: expected an object")
        metadata_status = "malformed"
    protection, classic_status = _read_policy_json(
        repo, ["gh", "api", f"repos/{SPACE_REPO}/branches/main/protection"], "classic protection", blockers, command_errors,
        allow_classic_404=True,
    )
    if classic_status == "available" and not isinstance(protection, dict):
        blockers.append("Malformed classic protection: expected an object")
        classic_status = "malformed"

    effective = _effective_policy_proofs(rules, blockers)
    classic_has_pr, classic_has_test, classic_linear = _classic_policy_proofs(protection, blockers) if classic_status == "available" else (False, False, False)
    has_pr = classic_has_pr or effective["has_pr"]
    has_test = classic_has_test or effective["has_test"]
    if not has_pr:
        blockers.append("Require proof of required pull request protection on main")
    if not has_test:
        blockers.append("Require proof of exact required test check on main")
    if not effective["has_queue"]:
        blockers.append("Require effective merge queue protection on main")

    queue_methods = effective["queue_methods"]
    method = None
    if queue_methods and len(set(queue_methods)) == 1:
        method = queue_methods[0]
    elif queue_methods:
        blockers.append("Conflicting effective merge_queue methods; require one consistent queue method")
    else:
        blockers.append("Require an explicit recognized merge_queue method")

    permissions = {
        key: metadata.get(key) if metadata_status == "available" else None
        for key in ("allow_merge_commit", "allow_squash_merge", "allow_rebase_merge")
    }
    permission_keys = {"merge": "allow_merge_commit", "squash": "allow_squash_merge"}
    linear_history = classic_linear or effective["linear_history"]
    if method == "rebase":
        blockers.append("Queue method rebase is unsupported; a human must decide a safe merge or squash policy")
    if method in permission_keys and permissions[permission_keys[method]] is not True:
        blockers.append(f"Repository {permission_keys[method]} must literally be true for queue method {method}")
    if method and any(method not in allowed for allowed in effective["restrictions"]):
        blockers.append(f"Queue method {method} is excluded by explicit pull_request allowed_merge_methods restrictions")
    if method == "merge" and linear_history:
        blockers.append("Queue method merge conflicts with required linear history; require a compatible queue policy")

    safe_method = method in permission_keys and not blockers
    evidence = {
        "repository": SPACE_REPO,
        "effective_branch_rules_status": effective_status,
        "effective_branch_rules_complete": complete,
        "effective_branch_rules_page_count": page_count,
        "metadata_status": metadata_status,
        "classic_protection_status": classic_status,
        "repository_merge_permissions": permissions,
        "classic_required_pull_request_proven": classic_has_pr,
        "classic_required_test_check_proven": classic_has_test,
        "effective_branch_rules_required_pull_request_proven": effective["has_pr"],
        "effective_branch_rules_required_test_check_proven": effective["has_test"],
        "effective_branch_rules_merge_queue_proven": effective["has_queue"],
        "required_pull_request_proven": has_pr,
        "required_test_check_proven": has_test,
        "merge_queue_proven": effective["has_queue"],
        "queue_merge_methods": queue_methods,
        "queue_merge_method": method,
        "explicit_pr_merge_method_restrictions": effective["restrictions"],
        "effective_linear_history_required": effective["linear_history"],
        "classic_linear_history_required": classic_linear,
        "linear_history_required": linear_history,
        "safe_merge_method_proven": safe_method,
        "command_errors": command_errors,
        "blockers": blockers,
    }
    if blockers:
        return human_decision(action, "Could not prove required PR/test protection and a safe merge queue method on main", evidence)
    return success(action, "Main protection proves required PR/test protection and a safe merge queue method", evidence)


def create_pr(repo_root: Path, head: str) -> dict[str, object]:
    action = "create_pr"
    try:
        repo = ensure_space_repo(repo_root)
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})
    branch, unsafe = _safe_branch(action, head)
    if unsafe is not None:
        return unsafe
    try:
        result = run_command(["gh", "pr", "create", "--base", "main", "--head", branch, "--fill"], repo)
        return success(action, "Created pull request targeting main", {"branch": branch, "url": result.stdout.strip(), "args": result.args})
    except CapabilityError as error:
        return human_decision(action, error.message, {"code": error.code, "details": error.details, "branch": branch})


def create_current_pr(repo_root: Path) -> dict[str, object]:
    action = "create_pr"
    try:
        repo = ensure_space_repo(repo_root)
        branch, unsafe = _safe_current_branch(action, repo)
        if unsafe is not None:
            return unsafe
        view_result = run_command(["gh", "pr", "view", branch, "--json", PR_VIEW_FIELDS], repo, check=False)
        if view_result.returncode == 0:
            data = _json_loads(view_result.stdout)
            if not isinstance(data, dict):
                return human_decision(action, "GitHub PR view response was ambiguous", _command_result_evidence(view_result, branch))
            current_head = _current_head(repo)
            reuse_evidence = _existing_pr_reuse_evidence(data, branch, current_head, view_result.args)
            if data.get("headRefOid") != current_head:
                return human_decision(action, "Existing pull request does not match current branch HEAD", reuse_evidence)
            if data.get("state") != "OPEN":
                return human_decision(action, "Existing pull request is not open for the current branch HEAD", reuse_evidence)
            return success(
                action,
                "Pull request already exists targeting main",
                {"branch": branch, "url": data.get("url"), "state": data.get("state"), "pr": data, "args": view_result.args},
            )
        if not _is_no_pr_view_result(view_result):
            return human_decision(action, "Could not determine whether pull request already exists", _command_result_evidence(view_result, branch))
        result = run_command(["gh", "pr", "create", "--base", "main", "--head", branch, "--fill"], repo, check=False)
        if result.returncode != 0:
            return human_decision(action, "Could not create pull request safely", _command_result_evidence(result, branch))
        return success(action, "Created pull request targeting main", {"branch": branch, "url": result.stdout.strip(), "args": result.args})
    except CapabilityError as error:
        return human_decision(action, error.message, {"code": error.code, "details": error.details})


def enable_auto_merge(repo_root: Path, branch: str) -> dict[str, object]:
    action = "enable_auto_merge"
    try:
        repo = ensure_space_repo(repo_root)
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})
    safe, unsafe = _safe_branch(action, branch)
    if unsafe is not None:
        return unsafe
    protection = check_main_protection(repo_root)
    if protection.get("status") != "pass":
        return human_decision(action, "Auto-merge requires proven main protection and merge queue", {"branch": safe, "protection": protection})
    evidence = {"branch": safe, "queue_merge_method": protection["evidence"]["queue_merge_method"], "protection": protection}
    try:
        result = run_command(["gh", "pr", "merge", safe, "--auto"], repo, check=False)
        if result.returncode != 0:
            return human_decision(action, "Auto-merge request could not be accepted safely", {**evidence, **_command_result_evidence(result, safe)})
        return success(action, "Auto-merge request accepted under the verified queue policy; merge is not yet proven", {**evidence, "args": result.args})
    except CapabilityError as error:
        return human_decision(action, error.message, {**evidence, "code": error.code, "details": error.details})


def enable_auto_merge_current(repo_root: Path) -> dict[str, object]:
    action = "enable_auto_merge"
    try:
        repo = ensure_space_repo(repo_root)
        safe, unsafe = _safe_current_branch(action, repo)
        if unsafe is not None:
            return unsafe
        return enable_auto_merge(repo_root, safe)
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})


def view_pr(repo_root: Path, branch: str) -> dict[str, object]:
    action = "view_pr"
    try:
        repo = ensure_space_repo(repo_root)
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})
    safe, unsafe = _safe_branch(action, branch)
    if unsafe is not None:
        return unsafe
    try:
        result = run_command(["gh", "pr", "view", safe, "--json", PR_VIEW_FIELDS], repo, check=False)
        if result.returncode != 0:
            if _is_no_pr_view_result(result):
                return failure(action, "No pull request exists for branch", _command_result_evidence(result, safe))
            return human_decision(action, "Could not load pull request status safely", _command_result_evidence(result, safe))
        data = _json_loads(result.stdout)
        if not isinstance(data, dict):
            return human_decision(action, "GitHub PR view response was ambiguous", _command_result_evidence(result, safe))
        return success(action, "Loaded pull request status", {"branch": safe, "pr": data})
    except (CapabilityError, json.JSONDecodeError) as error:
        return human_decision(action, "Could not load pull request status safely", {"error_type": type(error).__name__, "error": str(error), "branch": safe})


def view_current_pr(repo_root: Path) -> dict[str, object]:
    action = "view_pr"
    try:
        repo = ensure_space_repo(repo_root)
        safe, unsafe = _safe_current_branch(action, repo)
        if unsafe is not None:
            return unsafe
        return view_pr(repo_root, safe)
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})


def _failed_rollup_checks(data: dict[str, Any]) -> list[dict[str, Any]]:
    failed_checks = []
    for check in data.get("statusCheckRollup") or []:
        if not isinstance(check, dict):
            continue
        conclusion = _normalized_rollup_value(check.get("conclusion"))
        if conclusion in FAILED_ROLLUP_CONCLUSIONS:
            failed_checks.append(check)
    return failed_checks


def _bounded_log_excerpt(log_text: str) -> str:
    lines = _clean_log_text(log_text).splitlines()
    excerpt = "\n".join(lines[-MAX_FAILED_CHECK_LOG_LINES:])
    if len(excerpt) > MAX_FAILED_CHECK_LOG_CHARS:
        return excerpt[-MAX_FAILED_CHECK_LOG_CHARS:]
    return excerpt


def _valid_numeric_id(value: str) -> bool:
    return isinstance(value, str) and value.isdigit()


def _clean_log_text(text: str) -> str:
    return text.replace("\x00", "")


def _bounded_log_text(text: str) -> str:
    if len(text) > MAX_FAILED_CHECK_LOG_CHARS:
        return text[-MAX_FAILED_CHECK_LOG_CHARS:]
    return text


def _truncate_around_literal(text: str, literal: str, budget: int) -> str:
    if budget < 1:
        return ""
    if len(text) <= budget:
        return text
    if not literal or literal not in text:
        return text[:budget]

    prefix = "...[truncated]"
    suffix = "[truncated]..."
    if budget <= len(prefix) + len(suffix) + len(literal):
        start = text.index(literal)
        return text[start : start + budget]

    content_budget = budget - len(prefix) - len(suffix)
    literal_index = text.index(literal)
    start = max(0, literal_index - ((content_budget - len(literal)) // 2))
    end = min(len(text), start + content_budget)
    start = max(0, end - content_budget)
    bounded = text[start:end]
    if start > 0:
        bounded = f"{prefix}{bounded}"
    if end < len(text):
        bounded = f"{bounded}{suffix}"
    return bounded[:budget]


def _line_slice(lines: list[str], start_line: int, line_count: int) -> tuple[str, int, int]:
    start_index = start_line - 1
    bounded_count = min(line_count, MAX_FAILED_CHECK_LOG_LINES)
    selected = lines[start_index : start_index + bounded_count]
    end_line = start_line + len(selected) - 1 if selected else start_line - 1
    return _bounded_log_text("\n".join(selected)), start_line, end_line


def _search_log_lines(lines: list[str], contains: str, context_lines: int, max_matches: int) -> list[dict[str, object]]:
    bounded_context = min(context_lines, MAX_FAILED_CHECK_LOG_LINES)
    bounded_matches = min(max_matches, MAX_FAILED_CHECK_LOG_LINES)
    matches: list[dict[str, object]] = []
    for index, line in enumerate(lines):
        if contains not in line:
            continue
        start = max(0, index - bounded_context)
        end = min(len(lines), index + bounded_context + 1)
        raw_context = lines[start:end]
        text_budget = MAX_FAILED_CHECK_LOG_CHARS - 1024
        match_budget = max(1, text_budget // 2)
        context_item_budget = max(1, (text_budget - match_budget) // max(1, len(raw_context)))
        candidate = {
            "line": index + 1,
            "match": _truncate_around_literal(line, contains, match_budget),
            "context": [_truncate_around_literal(context, contains, context_item_budget) for context in raw_context],
        }
        if len(json.dumps([*matches, candidate])) > MAX_FAILED_CHECK_LOG_CHARS and matches:
            break
        matches.append(candidate)
        if len(matches) >= bounded_matches:
            break
    return matches


def _fail_markers(log_text: str) -> list[dict[str, object]]:
    lines = _clean_log_text(log_text).splitlines()
    return _search_log_lines(lines, "[FAIL]", 1, MAX_FAILED_CHECK_LOG_LINES)


def _fetch_actions_log(repo: Path, run_id: str, job_id: str) -> tuple[str | None, dict[str, object] | None]:
    result = run_command(["gh", "run", "view", run_id, "--job", job_id, "--log"], repo, check=False)
    if result.returncode == 0:
        return _clean_log_text(result.stdout), None
    return None, {"args": result.args, "returncode": result.returncode, "stderr": result.stderr.strip()}


def _invalid_log_request(action: str, code: str, **details: object) -> dict[str, object]:
    evidence = {"code": code}
    evidence.update(details)
    return failure(action, "Invalid GitHub Actions log request", evidence)


def _validate_actions_log_bounds(
    action: str,
    run_id: str,
    job_id: str,
    tail_lines: int | None,
    start_line: int | None,
    line_count: int | None,
    context_lines: int,
    max_matches: int,
) -> dict[str, object] | None:
    if not _valid_numeric_id(run_id):
        return _invalid_log_request(action, "invalid_run_id", run_id=run_id)
    if not _valid_numeric_id(job_id):
        return _invalid_log_request(action, "invalid_job_id", job_id=job_id)
    if tail_lines is not None and tail_lines < 1:
        return _invalid_log_request(action, "invalid_tail_lines", tail_lines=tail_lines)
    if start_line is not None and start_line < 1:
        return _invalid_log_request(action, "invalid_start_line", start_line=start_line)
    if line_count is not None and line_count < 1:
        return _invalid_log_request(action, "invalid_line_count", line_count=line_count)
    if context_lines < 0:
        return _invalid_log_request(action, "invalid_context_lines", context_lines=context_lines)
    if max_matches < 1:
        return _invalid_log_request(action, "invalid_max_matches", max_matches=max_matches)
    return None


def _validate_actions_log_combinations(
    action: str,
    *,
    tail_lines: int | None,
    start_line: int | None,
    line_count: int | None,
    contains: str | None,
    full: bool,
) -> dict[str, object] | None:
    if full and any(value is not None for value in (tail_lines, start_line, line_count, contains)):
        return _invalid_log_request(action, "invalid_mode_combination")
    if contains is not None and any(value is not None for value in (tail_lines, start_line, line_count)):
        return _invalid_log_request(action, "invalid_mode_combination")
    if tail_lines is not None and any(value is not None for value in (start_line, line_count)):
        return _invalid_log_request(action, "invalid_mode_combination")
    if start_line is not None and line_count is None:
        return _invalid_log_request(action, "missing_line_count")
    if line_count is not None and start_line is None:
        return _invalid_log_request(action, "missing_start_line")
    return None


def _failed_check_metadata(check: dict[str, Any]) -> dict[str, object]:
    fields = ("name", "workflowName", "status", "conclusion", "detailsUrl", "startedAt", "completedAt")
    return {field: check[field] for field in fields if field in check}


def _actions_run_job_ids(details_url: Any) -> tuple[str, str] | None:
    if not isinstance(details_url, str):
        return None
    match = GITHUB_ACTIONS_JOB_URL.fullmatch(details_url)
    if match is None:
        return None
    return match.group(1), match.group(2)


def _failed_check_evidence(check: dict[str, Any], repo: Path) -> dict[str, object]:
    evidence = _failed_check_metadata(check)
    details_url = check.get("detailsUrl")
    run_job_ids = _actions_run_job_ids(details_url)
    if run_job_ids is None:
        if details_url:
            evidence["log_unavailable"] = "detailsUrl did not contain a parseable GitHub Actions run/job id"
        else:
            evidence["log_unavailable"] = "detailsUrl was missing"
        return evidence

    run_id, job_id = run_job_ids
    evidence["run_id"] = run_id
    evidence["job_id"] = job_id
    log_text, log_error = _fetch_actions_log(repo, run_id, job_id)
    if log_text is not None:
        evidence["log_excerpt"] = _bounded_log_excerpt(log_text)
        markers = _fail_markers(log_text)
        if markers:
            evidence["failure_markers"] = markers
        return evidence
    evidence["log_unavailable"] = "gh run view --job failed"
    evidence["log_command"] = log_error or {}
    return evidence


def _failed_rollup_evidence(data: dict[str, Any], repo: Path) -> list[dict[str, object]]:
    return [_failed_check_evidence(check, repo) for check in _failed_rollup_checks(data)]


def _failed_check_log_waits_for_in_progress_run(evidence: dict[str, object]) -> bool:
    if evidence.get("log_unavailable") != "gh run view --job failed":
        return False
    log_command = evidence.get("log_command")
    if not isinstance(log_command, dict):
        return False
    stderr = log_command.get("stderr")
    if not isinstance(stderr, str):
        return False
    normalized = stderr.lower()
    return "is still in progress" in normalized and "logs will be available when it is complete" in normalized


def _failed_check_evidence_waits_for_in_progress_logs(failed_checks: list[dict[str, object]], data: dict[str, Any]) -> bool:
    if not _has_pending_rollup_check(data):
        return False
    return any(_failed_check_log_waits_for_in_progress_run(check) for check in failed_checks)


def _normalized_rollup_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return value.strip().lower().replace("_", "-")


def _rollup_check_is_completed(check: dict[str, Any]) -> bool:
    return _normalized_rollup_value(check.get("status")) == "completed"


def _rollup_check_is_check_run(check: dict[str, Any]) -> bool:
    return check.get("__typename") == "CheckRun"


def _rollup_conclusion_is_blank_or_missing(check: dict[str, Any]) -> bool:
    conclusion = check.get("conclusion")
    return conclusion is None or (isinstance(conclusion, str) and conclusion.strip() == "")


def _rollup_has_explicit_pending_state(check: dict[str, Any]) -> bool:
    return (
        _normalized_rollup_value(check.get("status")) in PENDING_ROLLUP_STATUSES
        or _normalized_rollup_value(check.get("state")) in PENDING_ROLLUP_STATUSES
    )


def _has_pending_rollup_check(data: dict[str, Any]) -> bool:
    for check in data.get("statusCheckRollup") or []:
        if not isinstance(check, dict):
            continue
        if _rollup_has_explicit_pending_state(check):
            return True
        if _rollup_check_is_check_run(check) and _rollup_conclusion_is_blank_or_missing(check) and not _rollup_check_is_completed(check):
            return True
    return False


def poll_merge_queue(repo_root: Path, branch: str, timeout_seconds: int, interval_seconds: int) -> dict[str, object]:
    action = "poll_merge_queue"
    try:
        repo = ensure_space_repo(repo_root)
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})
    safe, unsafe = _safe_branch(action, branch)
    if unsafe is not None:
        return unsafe
    deadline = time.monotonic() + max(timeout_seconds, 0)
    attempts = 0
    try:
        while True:
            attempts += 1
            result = run_command(["gh", "pr", "view", safe, "--json", PR_VIEW_FIELDS], repo)
            data = _json_loads(result.stdout)
            if not isinstance(data, dict):
                return human_decision(action, "GitHub PR view response was ambiguous", {"branch": safe, "attempts": attempts})
            if data.get("mergedAt"):
                return success(action, "Pull request has merged", {"branch": safe, "merged_at": data.get("mergedAt"), "attempts": attempts})
            if data.get("state") == "CLOSED":
                return human_decision(action, "Pull request closed without mergedAt", {"branch": safe, "attempts": attempts})
            failed_checks = _failed_rollup_evidence(data, repo)
            if failed_checks:
                if _failed_check_evidence_waits_for_in_progress_logs(failed_checks, data):
                    if time.monotonic() >= deadline:
                        return human_decision(action, "Timed out waiting for merge queue to merge pull request", {"branch": safe, "attempts": attempts})
                    time.sleep(interval_seconds)
                    continue
                return human_decision(action, "Required merge queue check failed", {"branch": safe, "attempts": attempts, "failed_checks": failed_checks})
            merge_state = data.get("mergeStateStatus")
            normalized_merge_state = merge_state.lower() if isinstance(merge_state, str) else merge_state
            mergeable = data.get("mergeable")
            normalized_mergeable = mergeable.lower() if isinstance(mergeable, str) else mergeable
            if normalized_merge_state == "dirty" or normalized_mergeable == "conflicting":
                return human_decision(
                    action,
                    "Pull request has merge conflicts or is not mergeable",
                    {"branch": safe, "merge_state": merge_state, "mergeable": mergeable, "attempts": attempts},
                )
            if normalized_merge_state not in NONTERMINAL_STATES and not _has_pending_rollup_check(data):
                return human_decision(action, "Pull request merge queue state is ambiguous or unsupported", {"branch": safe, "merge_state": merge_state, "attempts": attempts})
            if time.monotonic() >= deadline:
                return human_decision(action, "Timed out waiting for merge queue to merge pull request", {"branch": safe, "attempts": attempts})
            time.sleep(interval_seconds)
    except (CapabilityError, json.JSONDecodeError) as error:
        return human_decision(action, "Could not poll merge queue safely", {"error_type": type(error).__name__, "error": str(error), "branch": safe})


def poll_current_merge_queue(repo_root: Path) -> dict[str, object]:
    action = "poll_merge_queue"
    try:
        repo = ensure_space_repo(repo_root)
        safe, unsafe = _safe_current_branch(action, repo)
        if unsafe is not None:
            return unsafe
        return poll_merge_queue(repo_root, safe, DEFAULT_POLL_TIMEOUT_SECONDS, DEFAULT_POLL_INTERVAL_SECONDS)
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})


def actions_log(
    repo_root: Path,
    run_id: str,
    job_id: str,
    *,
    tail_lines: int | None,
    start_line: int | None,
    line_count: int | None,
    contains: str | None,
    context_lines: int,
    max_matches: int,
    full: bool,
) -> dict[str, object]:
    action = "actions_log"
    invalid = _validate_actions_log_bounds(action, run_id, job_id, tail_lines, start_line, line_count, context_lines, max_matches)
    if invalid is not None:
        return invalid
    invalid_combination = _validate_actions_log_combinations(
        action,
        tail_lines=tail_lines,
        start_line=start_line,
        line_count=line_count,
        contains=contains,
        full=full,
    )
    if invalid_combination is not None:
        return invalid_combination
    try:
        repo = ensure_space_repo(repo_root)
        log_text, log_error = _fetch_actions_log(repo, run_id, job_id)
    except CapabilityError as error:
        return failure(action, error.message, {"code": error.code, "details": error.details})
    if log_text is None:
        return human_decision(action, "Could not retrieve GitHub Actions log", log_error or {})

    lines = log_text.splitlines()
    common: dict[str, object] = {"run_id": run_id, "job_id": job_id}
    if full:
        evidence = {**common, "mode": "full", "log": log_text}
    elif contains is not None:
        evidence = {**common, "mode": "search", "contains": contains, "matches": _search_log_lines(lines, contains, context_lines, max_matches)}
    elif start_line is not None and line_count is not None:
        sliced, actual_start, end_line = _line_slice(lines, start_line, line_count)
        evidence = {**common, "mode": "slice", "start_line": actual_start, "end_line": end_line, "log": sliced}
    else:
        requested_tail = tail_lines or MAX_FAILED_CHECK_LOG_LINES
        bounded_tail = min(requested_tail, MAX_FAILED_CHECK_LOG_LINES)
        evidence = {**common, "mode": "tail", "tail_lines": bounded_tail, "log": _bounded_log_text("\n".join(lines[-bounded_tail:]))}
    return success(action, "Retrieved GitHub Actions log", evidence)


def failed_actions_log_bundle_current(repo_root: Path) -> dict[str, object]:
    action = "failed_actions_log_bundle_current"
    try:
        repo = ensure_space_repo(repo_root)
        branch, unsafe = _safe_current_branch(action, repo)
        if unsafe is not None:
            return unsafe
        view_result = run_command(["gh", "pr", "view", branch, "--json", PR_VIEW_FIELDS], repo, check=False)
        if view_result.returncode != 0:
            return human_decision(action, "Could not load current pull request status", _command_result_evidence(view_result, branch))
        data = _json_loads(view_result.stdout)
        if not isinstance(data, dict):
            return human_decision(action, "GitHub PR view response was ambiguous", _command_result_evidence(view_result, branch))
        output_dir = repo / "build" / "opencode" / "actions-logs"
        output_dir.mkdir(parents=True, exist_ok=True)
        logs: list[dict[str, object]] = []
        for check in _failed_rollup_checks(data):
            run_job_ids = _actions_run_job_ids(check.get("detailsUrl"))
            if run_job_ids is None:
                continue
            run_id, job_id = run_job_ids
            log_text, log_error = _fetch_actions_log(repo, run_id, job_id)
            if log_text is None:
                logs.append({"run_id": run_id, "job_id": job_id, "log_unavailable": "gh run view --job failed", "log_command": log_error or {}})
                continue
            path = output_dir / f"{run_id}-{job_id}.log"
            path.write_text(log_text)
            entry = {
                "run_id": run_id,
                "job_id": job_id,
                "path": str(path.relative_to(repo)),
                "failure_markers": _fail_markers(log_text),
            }
            logs.append(entry)
        return success(action, "Wrote failed GitHub Actions logs", {"branch": branch, "logs": logs})
    except (CapabilityError, json.JSONDecodeError, OSError) as error:
        if isinstance(error, CapabilityError):
            return failure(action, error.message, {"code": error.code, "details": error.details})
        return failure(action, "Could not write failed GitHub Actions log bundle", {"error_type": type(error).__name__, "error": str(error)})


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("auth-status", "check-main-protection", "create-current", "enable-auto-merge-current", "view-current", "poll-merge-queue-current"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--repo-root", required=True, type=Path)
    create = subparsers.add_parser("create")
    create.add_argument("--repo-root", required=True, type=Path)
    create.add_argument("--head", required=True)
    for command in ("enable-auto-merge", "view"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--repo-root", required=True, type=Path)
        subparser.add_argument("--branch", required=True)
    poll = subparsers.add_parser("poll-merge-queue")
    poll.add_argument("--repo-root", required=True, type=Path)
    poll.add_argument("--branch", required=True)
    poll.add_argument("--timeout-seconds", required=True, type=int)
    poll.add_argument("--interval-seconds", required=True, type=int)
    actions = subparsers.add_parser("actions-log")
    actions.add_argument("--repo-root", required=True, type=Path)
    actions.add_argument("--run-id", required=True)
    actions.add_argument("--job-id", required=True)
    actions.add_argument("--tail-lines", type=int)
    actions.add_argument("--start-line", type=int)
    actions.add_argument("--line-count", type=int)
    actions.add_argument("--contains")
    actions.add_argument("--context-lines", type=int, default=2)
    actions.add_argument("--max-matches", type=int, default=20)
    actions.add_argument("--full", action="store_true")
    bundle = subparsers.add_parser("failed-actions-log-bundle-current")
    bundle.add_argument("--repo-root", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "auth-status":
            result = pr_auth_status(args.repo_root)
        elif args.command == "check-main-protection":
            result = check_main_protection(args.repo_root)
        elif args.command == "create-current":
            result = create_current_pr(args.repo_root)
        elif args.command == "enable-auto-merge-current":
            result = enable_auto_merge_current(args.repo_root)
        elif args.command == "view-current":
            result = view_current_pr(args.repo_root)
        elif args.command == "poll-merge-queue-current":
            result = poll_current_merge_queue(args.repo_root)
        elif args.command == "create":
            result = create_pr(args.repo_root, args.head)
        elif args.command == "enable-auto-merge":
            result = enable_auto_merge(args.repo_root, args.branch)
        elif args.command == "view":
            result = view_pr(args.repo_root, args.branch)
        elif args.command == "poll-merge-queue":
            result = poll_merge_queue(args.repo_root, args.branch, args.timeout_seconds, args.interval_seconds)
        elif args.command == "actions-log":
            result = actions_log(
                args.repo_root,
                args.run_id,
                args.job_id,
                tail_lines=args.tail_lines,
                start_line=args.start_line,
                line_count=args.line_count,
                contains=args.contains,
                context_lines=args.context_lines,
                max_matches=args.max_matches,
                full=args.full,
            )
        else:
            result = failed_actions_log_bundle_current(args.repo_root)
    except Exception as error:  # noqa: BLE001 - CLIs must fail closed with structured JSON.
        result = failure(args.command.replace("-", "_"), "Local GitHub capability wrapper failed unexpectedly", {"error_type": type(error).__name__, "error": str(error)})
    print(json.dumps(result, indent=2, sort_keys=True))
    return _exit_code_for(result)


if __name__ == "__main__":
    raise SystemExit(main())
