import json
import sys
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import opencode_capabilities as capabilities
import opencode_pr_operator as pr_operator


def command_result(args: list[str], stdout: str = "", returncode: int = 0, stderr: str = "") -> capabilities.CommandResult:
    return capabilities.CommandResult(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


class GhRunner:
    def __init__(self, outputs: dict[tuple[str, ...], str | capabilities.CommandResult]) -> None:
        self.outputs = outputs
        self.calls: list[list[str]] = []

    def __call__(self, args, cwd: Path, check: bool = True):
        del cwd, check
        args = list(args)
        self.calls.append(args)
        assert tuple(args) in self.outputs, f"Unexpected command: {args}"
        output = self.outputs[tuple(args)]
        if isinstance(output, capabilities.CommandResult):
            return output
        return command_result(args, output)


@pytest.fixture
def trusted_repo(monkeypatch, tmp_path: Path) -> Path:
    repo = tmp_path / "space"
    repo.mkdir()
    monkeypatch.setattr(pr_operator, "ensure_space_repo", lambda repo_root: repo)
    return repo


EFFECTIVE_ARGS = ("gh", "api", "--paginate", "--slurp", "repos/semanticdreams/spacecore/rules/branches/main?per_page=100")
METADATA_ARGS = ("gh", "api", "repos/semanticdreams/spacecore")
CLASSIC_ARGS = ("gh", "api", "repos/semanticdreams/spacecore/branches/main/protection")
BRANCH = "feature/opencode-capabilities"
MERGE_ARGS = ("gh", "pr", "merge", BRANCH, "--auto")


def safe_rules(method="MERGE"):
    return [
        {"type": "pull_request"},
        {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "test"}]}},
        {"type": "merge_queue", "parameters": {"merge_method": method}},
    ]


@pytest.mark.parametrize("missing_proof", ["pull_request", "safe_method"])
def test_incomplete_policy_cannot_authorize_auto_merge(monkeypatch, trusted_repo, missing_proof):
    rules = safe_rules("REBASE" if missing_proof == "safe_method" else "MERGE")
    if missing_proof == "pull_request":
        rules = [rule for rule in rules if rule["type"] != "pull_request"]
    runner = policy_runner(monkeypatch, pages=[rules])
    result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
    assert result["status"] == "human_decision_required"
    assert not any(call[:3] == ["gh", "pr", "merge"] for call in runner.calls)


@pytest.mark.parametrize("method", ["merge", "squash"])
def test_queue_request_has_no_strategy(monkeypatch, trusted_repo, method):
    runner = policy_runner(monkeypatch, pages=[safe_rules(method.upper())])
    result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
    assert result["status"] == "pass"
    assert runner.calls == [list(EFFECTIVE_ARGS), list(METADATA_ARGS), list(CLASSIC_ARGS), list(MERGE_ARGS)]
    assert result["evidence"]["queue_merge_method"] == method


def policy_runner(monkeypatch, *, pages=None, metadata=None, classic=None, overrides=None, merge_output=""):
    outputs = {
        EFFECTIVE_ARGS: json.dumps([safe_rules()] if pages is None else pages),
        METADATA_ARGS: json.dumps({"allow_merge_commit": True, "allow_squash_merge": True} if metadata is None else metadata),
        CLASSIC_ARGS: json.dumps({} if classic is None else classic),
        MERGE_ARGS: merge_output,
    }
    outputs.update(overrides or {})
    runner = GhRunner(outputs)
    monkeypatch.setattr(pr_operator, "run_command", runner)
    return runner


def assert_policy_refusal(trusted_repo, runner, diagnostic):
    result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
    assert result["status"] == "human_decision_required"
    proof = result["evidence"]["protection"]
    assert proof["status"] == "human_decision_required"
    assert diagnostic in " ".join(proof["evidence"]["blockers"])
    assert not any(call[:3] == ["gh", "pr", "merge"] for call in runner.calls)
    return proof["evidence"]


@pytest.mark.parametrize("method", ["MERGE", "SQUASH"])
@pytest.mark.parametrize("pr_parameters", [None, {}, {"allowed_merge_methods": ["merge", "squash"]}])
def test_complete_policy_requests_queue_method_without_strategy(monkeypatch, trusted_repo, method, pr_parameters):
    rules = safe_rules(method)
    if pr_parameters is not None:
        rules[0]["parameters"] = pr_parameters
    runner = policy_runner(monkeypatch, pages=[rules])
    result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
    assert result["status"] == "pass"
    evidence = result["evidence"]["protection"]["evidence"]
    assert evidence["repository"] == pr_operator.SPACE_REPO
    assert evidence["effective_branch_rules_complete"] is True
    assert evidence["effective_branch_rules_page_count"] == 1
    for key in ("required_pull_request_proven", "required_test_check_proven", "merge_queue_proven", "safe_merge_method_proven"):
        assert evidence[key] is True
    assert evidence["queue_merge_method"] == method.lower()
    assert evidence["blockers"] == []
    assert not any("ruleset" in key for key in evidence)
    assert runner.calls == [list(EFFECTIVE_ARGS), list(METADATA_ARGS), list(CLASSIC_ARGS), list(MERGE_ARGS)]


@pytest.mark.parametrize("missing", ["pull_request", "required_status_checks", "merge_queue"])
def test_missing_required_effective_proof_refuses_before_mutation(monkeypatch, trusted_repo, missing):
    rules = [rule for rule in safe_rules() if rule["type"] != missing]
    runner = policy_runner(monkeypatch, pages=[rules])
    assert_policy_refusal(trusted_repo, runner, {"pull_request": "pull request", "required_status_checks": "test", "merge_queue": "queue"}[missing])


@pytest.mark.parametrize("reviews", [{}, {"required_approving_review_count": 0}])
@pytest.mark.parametrize("checks", [{"contexts": ["test"]}, {"checks": [{"context": "test"}]}])
def test_classic_supplies_pr_and_test_even_without_approvals(monkeypatch, trusted_repo, reviews, checks):
    runner = policy_runner(monkeypatch, pages=[[safe_rules()[2]]], classic={
        "required_pull_request_reviews": reviews, "required_status_checks": checks,
    })
    result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
    assert result["status"] == "pass"
    evidence = result["evidence"]["protection"]["evidence"]
    assert evidence["classic_required_pull_request_proven"] is True
    assert evidence["classic_required_test_check_proven"] is True
    assert evidence["effective_branch_rules_required_pull_request_proven"] is False
    assert evidence["effective_branch_rules_required_test_check_proven"] is False
    assert runner.calls[-1] == list(MERGE_ARGS)


@pytest.mark.parametrize("field", ["required_pull_request_reviews", "required_status_checks"])
def test_classic_null_cannot_supply_missing_proof(monkeypatch, trusted_repo, field):
    missing_type = "pull_request" if field == "required_pull_request_reviews" else "required_status_checks"
    runner = policy_runner(monkeypatch, pages=[[rule for rule in safe_rules() if rule["type"] != missing_type]], classic={field: None})
    assert_policy_refusal(trusted_repo, runner, "pull request" if missing_type == "pull_request" else "test")


@pytest.mark.parametrize("missing", [None, "pull_request", "required_status_checks"])
def test_classic_explicit_404_requires_independent_effective_proof(monkeypatch, trusted_repo, missing):
    rules = [rule for rule in safe_rules() if rule["type"] != missing]
    runner = policy_runner(monkeypatch, pages=[rules], overrides={
        CLASSIC_ARGS: command_result(list(CLASSIC_ARGS), returncode=1, stderr="gh: Not Found (HTTP 404)"),
    })
    if missing:
        assert_policy_refusal(trusted_repo, runner, "pull request" if missing == "pull_request" else "test")
    else:
        result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
        assert result["status"] == "pass"
        assert result["evidence"]["protection"]["evidence"]["classic_protection_status"] == "unavailable_http_404"


@pytest.mark.parametrize("args", [EFFECTIVE_ARGS, METADATA_ARGS, CLASSIC_ARGS])
@pytest.mark.parametrize("stderr,code", [("HTTP 401: credential expired", 1), ("HTTP 403: Forbidden", 1), ("network unavailable", 2), ("Not Found", 404)])
def test_unreadable_mandatory_evidence_preserves_command_failure(monkeypatch, trusted_repo, args, stderr, code):
    # Even syntactically valid partial stdout from failed pagination cannot authorize.
    runner = policy_runner(monkeypatch, overrides={args: command_result(list(args), json.dumps([safe_rules()]), returncode=code, stderr=stderr)})
    evidence = assert_policy_refusal(trusted_repo, runner, "retrieve")
    assert {"args": list(args), "returncode": code, "stderr": stderr} in evidence["command_errors"]


@pytest.mark.parametrize("args", [EFFECTIVE_ARGS, METADATA_ARGS, CLASSIC_ARGS])
@pytest.mark.parametrize("raw", ["", "{", "null", '"scalar"', "7", "[]"])
def test_invalid_json_or_top_level_type_refuses(monkeypatch, trusted_repo, args, raw):
    runner = policy_runner(monkeypatch, overrides={args: raw})
    assert_policy_refusal(trusted_repo, runner, "Malformed")


@pytest.mark.parametrize("pages", [[], {}, [None], [safe_rules(), {}], [[None]], [[{}]], [[{"type": ""}]], [[{"type": 1}]], [[{"type": "   "}]], [safe_rules(), [False]]])
def test_invalid_effective_page_or_rule_shape_refuses(monkeypatch, trusted_repo, pages):
    runner = policy_runner(monkeypatch, pages=pages)
    evidence = assert_policy_refusal(trusted_repo, runner, "Malformed")
    assert evidence["effective_branch_rules_complete"] is False


def test_empty_effective_page_is_complete_but_proves_no_queue(monkeypatch, trusted_repo):
    runner = policy_runner(monkeypatch, pages=[[]], classic={"required_pull_request_reviews": {}, "required_status_checks": {"contexts": ["test"]}})
    evidence = assert_policy_refusal(trusted_repo, runner, "queue")
    assert evidence["effective_branch_rules_complete"] is True
    assert evidence["effective_branch_rules_page_count"] == 1


def test_effective_retrieval_is_mandatory_even_with_classic_pr_and_test(monkeypatch, trusted_repo):
    runner = policy_runner(monkeypatch, classic={"required_pull_request_reviews": {}, "required_status_checks": {"contexts": ["test"]}}, overrides={
        EFFECTIVE_ARGS: command_result(list(EFFECTIVE_ARGS), json.dumps([safe_rules()]), returncode=1, stderr="HTTP 404: Not Found"),
    })
    evidence = assert_policy_refusal(trusted_repo, runner, "retrieve effective")
    assert evidence["effective_branch_rules_complete"] is False
    assert evidence["classic_required_pull_request_proven"] is True
    assert evidence["classic_required_test_check_proven"] is True
    assert runner.calls == [list(EFFECTIVE_ARGS), list(METADATA_ARGS), list(CLASSIC_ARGS)]


def test_consistent_queue_methods_and_only_selected_permission_are_sufficient(monkeypatch, trusted_repo):
    runner = policy_runner(monkeypatch, pages=[safe_rules("SQUASH"), [{"type": "merge_queue", "parameters": {"merge_method": "SQUASH"}}]], metadata={"allow_merge_commit": False, "allow_squash_merge": True, "allow_rebase_merge": False})
    result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
    assert result["status"] == "pass"
    assert result["evidence"]["protection"]["evidence"]["queue_merge_methods"] == ["squash", "squash"]
    assert runner.calls[-1] == list(MERGE_ARGS)


def test_all_blockers_are_retained_after_positive_proofs(monkeypatch, trusted_repo):
    runner = policy_runner(monkeypatch, pages=[safe_rules(), [
        {"type": "pull_request", "parameters": {"allowed_merge_methods": []}},
        {"type": "required_linear_history"},
        {"type": "required_status_checks", "parameters": None},
    ]], metadata={"allow_merge_commit": False})
    evidence = assert_policy_refusal(trusted_repo, runner, "Malformed")
    blockers = " ".join(evidence["blockers"])
    for reason in ("allow_merge_commit", "allowed_merge_methods", "linear history"):
        assert reason in blockers
    assert evidence["required_pull_request_proven"] is True
    assert evidence["required_test_check_proven"] is True
    assert evidence["merge_queue_proven"] is True
    assert evidence["safe_merge_method_proven"] is False


@pytest.mark.parametrize("failed_args", [EFFECTIVE_ARGS, METADATA_ARGS, CLASSIC_ARGS, MERGE_ARGS])
def test_capability_command_errors_are_structured_and_fail_closed(monkeypatch, trusted_repo, failed_args):
    runner = policy_runner(monkeypatch)
    details = {"args": list(failed_args), "returncode": 2, "stderr": "command unavailable"}

    def failing_run(args, cwd, check=True):
        if list(args) == list(failed_args):
            runner.calls.append(list(args))
            raise capabilities.CapabilityError("command_failed", "Could not run command", details)
        return runner(args, cwd, check=check)

    monkeypatch.setattr(pr_operator, "run_command", failing_run)
    result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
    assert result["status"] == "human_decision_required"
    if failed_args == MERGE_ARGS:
        assert result["evidence"]["details"] == details
        assert runner.calls.count(list(MERGE_ARGS)) == 1
    else:
        evidence = result["evidence"]["protection"]["evidence"]
        assert evidence["command_errors"][0]["details"] == details
        assert not any(call[:3] == ["gh", "pr", "merge"] for call in runner.calls)


def test_later_pages_supply_proofs_and_all_restrictions(monkeypatch, trusted_repo):
    rules = safe_rules("SQUASH")
    runner = policy_runner(monkeypatch, pages=[[], [rules[2]], rules[:2], [{"type": "pull_request", "parameters": {"allowed_merge_methods": ["squash"]}}]])
    result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
    assert result["status"] == "pass"
    evidence = result["evidence"]["protection"]["evidence"]
    assert evidence["effective_branch_rules_page_count"] == 4
    assert evidence["explicit_pr_merge_method_restrictions"] == [["squash"]]
    assert runner.calls[-1] == list(MERGE_ARGS)


@pytest.mark.parametrize("later_rule,diagnostic", [
    ({"type": "pull_request", "parameters": {"allowed_merge_methods": ["squash"]}}, "allowed_merge_methods"),
    ({"type": "merge_queue", "parameters": {"merge_method": "SQUASH"}}, "Conflicting"),
    ({"type": "required_linear_history"}, "linear history"),
])
def test_later_page_blocker_cannot_be_hidden_by_positive_first_page(monkeypatch, trusted_repo, later_rule, diagnostic):
    runner = policy_runner(monkeypatch, pages=[safe_rules(), [later_rule]])
    assert_policy_refusal(trusted_repo, runner, diagnostic)


@pytest.mark.parametrize("method", [None, "", "merge", "UNKNOWN", "REBASE", 1, {}, []])
def test_queue_method_must_be_recognized_uppercase_and_safe(monkeypatch, trusted_repo, method):
    runner = policy_runner(monkeypatch, pages=[safe_rules(method)])
    assert_policy_refusal(trusted_repo, runner, "method")


@pytest.mark.parametrize("queue", [{"type": "merge_queue"}, {"type": "merge_queue", "parameters": None}, {"type": "merge_queue", "parameters": {}}, {"type": "merge_queue", "parameters": []}])
def test_queue_parameters_and_method_are_mandatory(monkeypatch, trusted_repo, queue):
    runner = policy_runner(monkeypatch, pages=[safe_rules()[:2] + [queue]])
    assert_policy_refusal(trusted_repo, runner, "merge_queue")


@pytest.mark.parametrize("method,key", [("MERGE", "allow_merge_commit"), ("SQUASH", "allow_squash_merge")])
@pytest.mark.parametrize("permission", [None, False, "true", 1, [], {}])
def test_queue_method_permission_requires_literal_true(monkeypatch, trusted_repo, method, key, permission):
    runner = policy_runner(monkeypatch, pages=[safe_rules(method)], metadata={key: permission})
    assert_policy_refusal(trusted_repo, runner, key)


def test_missing_repository_permission_refuses(monkeypatch, trusted_repo):
    runner = policy_runner(monkeypatch, metadata={})
    assert_policy_refusal(trusted_repo, runner, "allow_merge_commit")


@pytest.mark.parametrize("restriction", [None, "merge", {}, ["MERGE"], ["unknown"], [True], ["merge", None], []])
def test_explicit_invalid_or_empty_restriction_never_grants_permission(monkeypatch, trusted_repo, restriction):
    runner = policy_runner(monkeypatch, pages=[safe_rules(), [{"type": "pull_request", "parameters": {"allowed_merge_methods": restriction}}]])
    assert_policy_refusal(trusted_repo, runner, "allowed_merge_methods")


def test_explicit_pr_restrictions_are_intersected(monkeypatch, trusted_repo):
    runner = policy_runner(monkeypatch, pages=[safe_rules(), [
        {"type": "pull_request", "parameters": {"allowed_merge_methods": ["merge", "squash"]}},
        {"type": "pull_request", "parameters": {"allowed_merge_methods": ["rebase", "squash"]}},
    ]])
    evidence = assert_policy_refusal(trusted_repo, runner, "allowed_merge_methods")
    assert evidence["explicit_pr_merge_method_restrictions"] == [["merge", "squash"], ["rebase", "squash"]]


@pytest.mark.parametrize("source", ["effective", "classic"])
@pytest.mark.parametrize("method", ["MERGE", "SQUASH"])
def test_linear_history_excludes_merge_but_allows_squash(monkeypatch, trusted_repo, source, method):
    rules = safe_rules(method)
    classic = {}
    if source == "effective":
        rules.append({"type": "required_linear_history"})
    else:
        classic = {"required_linear_history": {"enabled": True}}
    runner = policy_runner(monkeypatch, pages=[rules], classic=classic)
    if method == "MERGE":
        assert_policy_refusal(trusted_repo, runner, "linear history")
    else:
        result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
        assert result["status"] == "pass"
        assert result["evidence"]["protection"]["evidence"]["linear_history_required"] is True


@pytest.mark.parametrize("extra_rule", [
    {"type": "pull_request", "parameters": None},
    {"type": "pull_request", "parameters": []},
    {"type": "required_status_checks"},
    {"type": "required_status_checks", "parameters": None},
    {"type": "required_status_checks", "parameters": {}},
    {"type": "required_status_checks", "parameters": {"required_status_checks": None}},
    {"type": "required_status_checks", "parameters": {"required_status_checks": "test"}},
    {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "test"}, {}]}},
    {"type": "required_status_checks", "parameters": {"required_status_checks": [False]}},
    {"type": "required_linear_history", "parameters": None},
    {"type": "merge_queue", "parameters": None},
])
def test_malformed_relevant_rule_refuses_despite_other_valid_proof(monkeypatch, trusted_repo, extra_rule):
    runner = policy_runner(monkeypatch, pages=[safe_rules(), [extra_rule]])
    assert_policy_refusal(trusted_repo, runner, "Malformed")


@pytest.mark.parametrize("classic", [
    {"required_pull_request_reviews": []},
    {"required_pull_request_reviews": False},
    {"required_status_checks": []},
    {"required_status_checks": {"contexts": None}},
    {"required_status_checks": {"contexts": ["test", 1]}},
    {"required_status_checks": {"contexts": ["test"], "checks": None}},
    {"required_status_checks": {"checks": [{"context": "test"}, {}]}},
    {"required_linear_history": None},
    {"required_linear_history": {}},
    {"required_linear_history": {"enabled": "true"}},
    {"required_linear_history": {"enabled": 1}},
])
def test_malformed_classic_policy_refuses_despite_effective_proof(monkeypatch, trusted_repo, classic):
    runner = policy_runner(monkeypatch, classic=classic)
    assert_policy_refusal(trusted_repo, runner, "Malformed")


def test_unrelated_rule_types_and_disabled_classic_linear_history_do_not_restrict(monkeypatch, trusted_repo):
    runner = policy_runner(monkeypatch, pages=[safe_rules(), [{"type": "deletion"}, {"type": "future_rule", "parameters": None}]], classic={"required_linear_history": {"enabled": False}})
    result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
    assert result["status"] == "pass"
    assert runner.calls[-1] == list(MERGE_ARGS)


@pytest.mark.parametrize("context", ["tests", "Test", "test / linux", " test", "lint"])
def test_required_check_must_be_exact_test(monkeypatch, trusted_repo, context):
    rules = safe_rules()
    rules[1]["parameters"]["required_status_checks"] = [{"context": context}]
    runner = policy_runner(monkeypatch, pages=[rules])
    assert_policy_refusal(trusted_repo, runner, "test")


def test_merge_command_failure_is_structured_and_never_retried(monkeypatch, trusted_repo):
    runner = policy_runner(monkeypatch, merge_output=command_result(list(MERGE_ARGS), returncode=1, stderr="GraphQL: policy changed"))
    result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
    assert result["status"] == "human_decision_required"
    assert result["evidence"]["args"] == list(MERGE_ARGS)
    assert result["evidence"]["returncode"] == 1
    assert result["evidence"]["stderr"] == "GraphQL: policy changed"
    assert result["evidence"]["queue_merge_method"] == "merge"
    assert [call for call in runner.calls if call[:3] == ["gh", "pr", "merge"]] == [list(MERGE_ARGS)]


def test_accepted_request_is_not_rejected_for_incidental_rebase_text(monkeypatch, trusted_repo):
    policy_runner(monkeypatch, merge_output="Queue accepted; no client rebase strategy selected")
    result = pr_operator.enable_auto_merge(trusted_repo, BRANCH)
    assert result["status"] == "pass"
    assert "request" in result["message"].lower()
    assert "merged_at" not in result["evidence"]


def test_current_branch_wrapper_runs_real_proof_before_request(monkeypatch, trusted_repo):
    runner = policy_runner(monkeypatch, overrides={("git", "branch", "--show-current"): BRANCH + "\n"})
    result = pr_operator.enable_auto_merge_current(trusted_repo)
    assert result["status"] == "pass"
    assert runner.calls == [["git", "branch", "--show-current"], list(EFFECTIVE_ARGS), list(METADATA_ARGS), list(CLASSIC_ARGS), list(MERGE_ARGS)]


@pytest.mark.parametrize("branch", ["main", "bad branch", "--admin"])
@pytest.mark.parametrize("current", [False, True])
def test_unsafe_branch_never_reads_policy_or_mutates(monkeypatch, trusted_repo, branch, current):
    runner = GhRunner({("git", "branch", "--show-current"): branch})
    monkeypatch.setattr(pr_operator, "run_command", runner)
    result = pr_operator.enable_auto_merge_current(trusted_repo) if current else pr_operator.enable_auto_merge(trusted_repo, branch)
    assert result["status"] == "human_decision_required"
    assert runner.calls == ([["git", "branch", "--show-current"]] if current else [])


def test_auth_status_runs_only_gh_auth_status(monkeypatch, trusted_repo: Path) -> None:
    runner = GhRunner({("gh", "auth", "status"): "Logged in\n"})
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.pr_auth_status(trusted_repo)

    assert result["status"] == "pass"
    assert runner.calls == [["gh", "auth", "status"]]


def test_create_always_targets_base_main_validates_head_and_rejects_invalid_branch(monkeypatch, trusted_repo: Path) -> None:
    runner = GhRunner(
        {
            (
                "gh",
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                "feature/opencode-capabilities",
                "--fill",
            ): "https://github.com/semanticdreams/spacecore/pull/123\n"
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.create_pr(trusted_repo, "feature/opencode-capabilities")

    invalid = pr_operator.create_pr(trusted_repo, "bad branch")


    assert result["status"] == "pass"
    assert invalid["status"] == "human_decision_required"
    assert runner.calls == [
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            "feature/opencode-capabilities",
            "--fill",
        ]
    ]


def test_create_current_uses_validated_current_branch_without_cli_branch_argument(monkeypatch, trusted_repo: Path) -> None:
    runner = GhRunner(
        {
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            (
                "gh",
                "pr",
                "view",
                "feature/opencode-capabilities",
                "--json",
                "state,mergedAt,mergeStateStatus,mergeable,autoMergeRequest,statusCheckRollup,headRefName,headRefOid,url",
            ): command_result(
                ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS],
                returncode=1,
                stderr="no pull requests found",
            ),
            (
                "gh",
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                "feature/opencode-capabilities",
                "--fill",
            ): "https://github.com/semanticdreams/spacecore/pull/123\n",
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.create_current_pr(trusted_repo)

    assert result["status"] == "pass"
    assert runner.calls == [
        ["git", "branch", "--show-current"],
        [
            "gh",
            "pr",
            "view",
            "feature/opencode-capabilities",
            "--json",
            "state,mergedAt,mergeStateStatus,mergeable,autoMergeRequest,statusCheckRollup,headRefName,headRefOid,url",
        ],
        ["gh", "pr", "create", "--base", "main", "--head", "feature/opencode-capabilities", "--fill"],
    ]


def test_create_current_returns_existing_pr_without_creating(monkeypatch, trusted_repo: Path) -> None:
    head = "31c62bc214b483adc95cbe234ce826b085f66225"
    pr = {"url": "https://github.com/semanticdreams/spacecore/pull/123", "state": "OPEN", "headRefOid": head}
    runner = GhRunner(
        {
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "HEAD"): f"{head}\n",
            (
                "gh",
                "pr",
                "view",
                "feature/opencode-capabilities",
                "--json",
                "state,mergedAt,mergeStateStatus,mergeable,autoMergeRequest,statusCheckRollup,headRefName,headRefOid,url",
            ): json.dumps(pr),
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.create_current_pr(trusted_repo)

    assert result["status"] == "pass"
    assert result["evidence"]["url"] == pr["url"]
    assert result["evidence"]["pr"] == pr
    assert runner.calls == [
        ["git", "branch", "--show-current"],
        ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS],
        ["git", "rev-parse", "HEAD"],
    ]


def test_create_current_rejects_stale_existing_pr_with_different_head(monkeypatch, trusted_repo: Path) -> None:
    current_head = "31c62bc214b483adc95cbe234ce826b085f66225"
    pr_head = "ef51e29ec41341b874e5528b5634a22497192100"
    pr = {
        "url": "https://github.com/semanticdreams/spacecore/pull/119",
        "state": "MERGED",
        "mergedAt": "2026-09-15T12:34:56Z",
        "headRefOid": pr_head,
    }
    runner = GhRunner(
        {
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "HEAD"): f"{current_head}\n",
            (
                "gh",
                "pr",
                "view",
                "feature/opencode-capabilities",
                "--json",
                "state,mergedAt,mergeStateStatus,mergeable,autoMergeRequest,statusCheckRollup,headRefName,headRefOid,url",
            ): json.dumps(pr),
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.create_current_pr(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"] == {
        "branch": "feature/opencode-capabilities",
        "current_head": current_head,
        "pr_head": pr_head,
        "pr_state": "MERGED",
        "pr_url": "https://github.com/semanticdreams/spacecore/pull/119",
        "args": ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS],
    }
    assert runner.calls == [
        ["git", "branch", "--show-current"],
        ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS],
        ["git", "rev-parse", "HEAD"],
    ]


def test_create_current_rejects_matching_head_pr_that_is_not_open(monkeypatch, trusted_repo: Path) -> None:
    head = "31c62bc214b483adc95cbe234ce826b085f66225"
    pr = {
        "url": "https://github.com/semanticdreams/spacecore/pull/119",
        "state": "MERGED",
        "mergedAt": "2026-09-15T12:34:56Z",
        "headRefOid": head,
    }
    runner = GhRunner(
        {
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "HEAD"): f"{head}\n",
            (
                "gh",
                "pr",
                "view",
                "feature/opencode-capabilities",
                "--json",
                pr_operator.PR_VIEW_FIELDS,
            ): json.dumps(pr),
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.create_current_pr(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"]["branch"] == "feature/opencode-capabilities"
    assert result["evidence"]["current_head"] == head
    assert result["evidence"]["pr_head"] == head
    assert result["evidence"]["pr_state"] == "MERGED"
    assert result["evidence"]["pr_url"] == "https://github.com/semanticdreams/spacecore/pull/119"


def test_create_current_creates_when_view_reports_no_existing_pr(monkeypatch, trusted_repo: Path) -> None:
    calls: list[tuple[list[str], bool]] = []

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd
        args = list(args)
        calls.append((args, check))
        if args == ["git", "branch", "--show-current"]:
            return command_result(args, "feature/opencode-capabilities\n")
        if args == ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS]:
            return command_result(args, returncode=1, stderr="no pull requests found for branch feature/opencode-capabilities")
        if args == ["gh", "pr", "create", "--base", "main", "--head", "feature/opencode-capabilities", "--fill"]:
            return command_result(args, "https://github.com/semanticdreams/spacecore/pull/124\n")
        raise AssertionError(args)

    monkeypatch.setattr(pr_operator, "run_command", fake_run)

    result = pr_operator.create_current_pr(trusted_repo)

    assert result["status"] == "pass"
    assert result["evidence"]["url"] == "https://github.com/semanticdreams/spacecore/pull/124"
    assert calls == [
        (["git", "branch", "--show-current"], True),
        (["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS], False),
        (["gh", "pr", "create", "--base", "main", "--head", "feature/opencode-capabilities", "--fill"], False),
    ]


def test_create_current_unsafe_view_failure_preserves_command_details_and_does_not_create(monkeypatch, trusted_repo: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd, check
        args = list(args)
        calls.append(args)
        if args == ["git", "branch", "--show-current"]:
            return command_result(args, "feature/opencode-capabilities\n")
        if args == ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS]:
            return command_result(args, returncode=2, stderr="HTTP 401: credential expired\nauth detail from gh")
        raise AssertionError(args)

    monkeypatch.setattr(pr_operator, "run_command", fake_run)

    result = pr_operator.create_current_pr(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"]["returncode"] == 2
    assert result["evidence"]["stderr"] == "HTTP 401: credential expired\nauth detail from gh"
    assert result["evidence"]["args"] == ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS]
    assert calls == [
        ["git", "branch", "--show-current"],
        ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS],
    ]


def test_create_current_generic_not_found_view_failure_does_not_create(monkeypatch, trusted_repo: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd, check
        args = list(args)
        calls.append(args)
        if args == ["git", "branch", "--show-current"]:
            return command_result(args, "feature/opencode-capabilities\n")
        if args == ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS]:
            return command_result(args, returncode=1, stderr="HTTP 404: Not Found")
        raise AssertionError(f"unexpected create attempt: {args}")

    monkeypatch.setattr(pr_operator, "run_command", fake_run)

    result = pr_operator.create_current_pr(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"]["returncode"] == 1
    assert result["evidence"]["stderr"] == "HTTP 404: Not Found"
    assert result["evidence"]["args"] == ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS]
    assert calls == [
        ["git", "branch", "--show-current"],
        ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS],
    ]


def test_create_current_create_failure_preserves_command_details(monkeypatch, trusted_repo: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd, check
        args = list(args)
        calls.append(args)
        if args == ["git", "branch", "--show-current"]:
            return command_result(args, "feature/opencode-capabilities\n")
        if args == ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS]:
            return command_result(args, returncode=1, stderr="no pull requests found")
        if args == ["gh", "pr", "create", "--base", "main", "--head", "feature/opencode-capabilities", "--fill"]:
            return command_result(args, returncode=1, stderr="GraphQL: Validation failed")
        raise AssertionError(args)

    monkeypatch.setattr(pr_operator, "run_command", fake_run)

    result = pr_operator.create_current_pr(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"]["returncode"] == 1
    assert result["evidence"]["stderr"] == "GraphQL: Validation failed"
    assert result["evidence"]["args"] == ["gh", "pr", "create", "--base", "main", "--head", "feature/opencode-capabilities", "--fill"]
    assert calls == [
        ["git", "branch", "--show-current"],
        ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS],
        ["gh", "pr", "create", "--base", "main", "--head", "feature/opencode-capabilities", "--fill"],
    ]


def test_view_pr_no_existing_pr_returns_explicit_non_human_evidence(monkeypatch, trusted_repo: Path) -> None:
    calls: list[tuple[list[str], bool]] = []

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd
        args = list(args)
        calls.append((args, check))
        result = command_result(args, returncode=1, stderr="no pull requests found for branch juicyrebel/no-pr-repro-branch")
        if check and result.returncode != 0:
            raise capabilities.CapabilityError(
                "command_failed",
                "Command failed while evaluating capability guard",
                {"args": result.args, "returncode": result.returncode, "stderr": result.stderr.strip()},
            )
        return result

    monkeypatch.setattr(pr_operator, "run_command", fake_run)

    result = pr_operator.view_pr(trusted_repo, "juicyrebel/no-pr-repro-branch")

    assert result["status"] == "fail"
    assert result["message"] == "No pull request exists for branch"
    assert result["evidence"] == {
        "branch": "juicyrebel/no-pr-repro-branch",
        "args": ["gh", "pr", "view", "juicyrebel/no-pr-repro-branch", "--json", pr_operator.PR_VIEW_FIELDS],
        "returncode": 1,
        "stderr": "no pull requests found for branch juicyrebel/no-pr-repro-branch",
    }
    assert calls == [(["gh", "pr", "view", "juicyrebel/no-pr-repro-branch", "--json", pr_operator.PR_VIEW_FIELDS], False)]


def test_view_pr_nonzero_failure_preserves_command_evidence(monkeypatch, trusted_repo: Path) -> None:
    calls: list[tuple[list[str], bool]] = []

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd
        args = list(args)
        calls.append((args, check))
        result = command_result(args, returncode=2, stderr="HTTP 401: credential expired\nauth detail from gh")
        if check and result.returncode != 0:
            raise capabilities.CapabilityError(
                "command_failed",
                "Command failed while evaluating capability guard",
                {"args": result.args, "returncode": result.returncode, "stderr": result.stderr.strip()},
            )
        return result

    monkeypatch.setattr(pr_operator, "run_command", fake_run)

    result = pr_operator.view_pr(trusted_repo, "feature/opencode-capabilities")

    assert result["status"] == "human_decision_required"
    assert result["message"] == "Could not load pull request status safely"
    assert result["evidence"] == {
        "branch": "feature/opencode-capabilities",
        "args": ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS],
        "returncode": 2,
        "stderr": "HTTP 401: credential expired\nauth detail from gh",
    }
    assert calls == [(["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS], False)]


def test_poll_merge_queue_treats_pending_states_as_nonterminal_until_merged(monkeypatch, trusted_repo: Path) -> None:
    states = iter(
        [
            {"mergedAt": None, "state": "OPEN", "mergeStateStatus": "queued", "statusCheckRollup": []},
            {"mergedAt": None, "state": "OPEN", "mergeStateStatus": "waiting", "statusCheckRollup": []},
            {"mergedAt": None, "state": "OPEN", "mergeStateStatus": "pending", "statusCheckRollup": []},
            {"mergedAt": None, "state": "OPEN", "mergeStateStatus": "in_progress", "statusCheckRollup": []},
            {"mergedAt": None, "state": "OPEN", "mergeStateStatus": "expected", "statusCheckRollup": []},
            {"mergedAt": None, "state": "OPEN", "mergeStateStatus": None, "statusCheckRollup": [{"conclusion": None}]},
            {"mergedAt": "2026-08-06T00:00:00Z", "state": "MERGED", "mergeStateStatus": "clean", "statusCheckRollup": []},
        ]
    )

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd, check
        assert list(args) == [
            "gh",
            "pr",
            "view",
            "feature/opencode-capabilities",
            "--json",
            "state,mergedAt,mergeStateStatus,mergeable,autoMergeRequest,statusCheckRollup,headRefName,headRefOid,url",
        ]
        return command_result(list(args), json.dumps(next(states)))

    monkeypatch.setattr(pr_operator, "run_command", fake_run)
    monkeypatch.setattr(pr_operator.time, "sleep", lambda seconds: None)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 60, 1)

    assert result["status"] == "pass"
    assert result["evidence"]["merged_at"] == "2026-08-06T00:00:00Z"


def test_poll_merge_queue_waits_for_open_clean_mergeable_pr_with_successful_checks(
    monkeypatch,
    trusted_repo: Path,
) -> None:
    states = iter(
        [
            {
                "mergedAt": None,
                "state": "OPEN",
                "mergeStateStatus": "CLEAN",
                "mergeable": "MERGEABLE",
                "statusCheckRollup": [
                    {
                        "__typename": "CheckRun",
                        "name": "test",
                        "workflowName": "test",
                        "status": "COMPLETED",
                        "conclusion": "SUCCESS",
                    }
                ],
            },
            {
                "mergedAt": "2026-08-08T00:00:00Z",
                "state": "MERGED",
                "mergeStateStatus": "CLEAN",
                "mergeable": "MERGEABLE",
                "statusCheckRollup": [],
            },
        ]
    )
    calls = []

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd, check
        calls.append(list(args))
        return command_result(list(args), json.dumps(next(states)))

    monkeypatch.setattr(pr_operator, "run_command", fake_run)
    monkeypatch.setattr(pr_operator.time, "sleep", lambda seconds: None)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 60, 1)

    assert result["status"] == "pass"
    assert result["evidence"]["merged_at"] == "2026-08-08T00:00:00Z"
    assert len(calls) == 2


def test_poll_merge_queue_waits_for_open_unknown_mergeability_with_successful_checks(
    monkeypatch,
    trusted_repo: Path,
) -> None:
    states = iter(
        [
            {
                "mergedAt": None,
                "state": "OPEN",
                "mergeStateStatus": "UNKNOWN",
                "mergeable": "UNKNOWN",
                "statusCheckRollup": [
                    {
                        "__typename": "CheckRun",
                        "name": "test",
                        "workflowName": "test",
                        "status": "COMPLETED",
                        "conclusion": "SUCCESS",
                    }
                ],
            },
            {
                "mergedAt": "2026-08-08T01:00:00Z",
                "state": "MERGED",
                "mergeStateStatus": "CLEAN",
                "mergeable": "MERGEABLE",
                "statusCheckRollup": [],
            },
        ]
    )
    calls = []

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd, check
        calls.append(list(args))
        return command_result(list(args), json.dumps(next(states)))

    monkeypatch.setattr(pr_operator, "run_command", fake_run)
    monkeypatch.setattr(pr_operator.time, "sleep", lambda seconds: None)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 60, 1)

    assert result["status"] == "pass"
    assert result["evidence"]["merged_at"] == "2026-08-08T01:00:00Z"
    assert len(calls) == 2


def test_poll_merge_queue_rejects_conflict_even_with_pending_rollup(
    monkeypatch,
    trusted_repo: Path,
) -> None:
    calls = []

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd, check
        calls.append(list(args))
        return command_result(
            list(args),
            json.dumps(
                {
                    "mergedAt": None,
                    "state": "OPEN",
                    "mergeStateStatus": "DIRTY",
                    "mergeable": "CONFLICTING",
                    "statusCheckRollup": [
                        {
                            "__typename": "CheckRun",
                            "name": "test",
                            "workflowName": "test",
                            "status": "IN_PROGRESS",
                            "conclusion": None,
                        }
                    ],
                }
            ),
        )

    monkeypatch.setattr(pr_operator, "run_command", fake_run)
    monkeypatch.setattr(pr_operator.time, "sleep", lambda seconds: pytest.fail("conflict should not wait"))

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 0, 1)

    assert result["status"] == "human_decision_required"
    assert result["message"] == "Pull request has merge conflicts or is not mergeable"
    assert len(calls) == 1


def test_poll_merge_queue_treats_blocked_in_progress_check_with_blank_conclusion_as_nonterminal(
    monkeypatch,
    trusted_repo: Path,
) -> None:
    states = iter(
        [
            {
                "mergedAt": None,
                "state": "OPEN",
                "mergeStateStatus": "BLOCKED",
                "statusCheckRollup": [
                    {
                        "__typename": "CheckRun",
                        "name": "test",
                        "workflowName": "test",
                        "status": "IN_PROGRESS",
                        "conclusion": "",
                        "completedAt": "0001-01-01T00:00:00Z",
                    }
                ],
            },
            {"mergedAt": "2026-08-07T00:00:00Z", "state": "MERGED", "mergeStateStatus": "clean", "statusCheckRollup": []},
        ]
    )
    calls = []

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd, check
        calls.append(list(args))
        return command_result(list(args), json.dumps(next(states)))

    monkeypatch.setattr(pr_operator, "run_command", fake_run)
    monkeypatch.setattr(pr_operator.time, "sleep", lambda seconds: None)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 60, 1)

    assert result["status"] == "pass"
    assert result["evidence"]["merged_at"] == "2026-08-07T00:00:00Z"
    assert len(calls) == 2


def test_poll_merge_queue_rejects_blocked_state_with_non_pending_rollup_missing_conclusion(
    monkeypatch,
    trusted_repo: Path,
) -> None:
    runner = GhRunner(
        {
            (
                "gh",
                "pr",
                "view",
                "feature/opencode-capabilities",
                "--json",
                "state,mergedAt,mergeStateStatus,mergeable,autoMergeRequest,statusCheckRollup,headRefName,headRefOid,url",
            ): json.dumps(
                {
                    "mergedAt": None,
                    "state": "OPEN",
                    "mergeStateStatus": "BLOCKED",
                    "statusCheckRollup": [{"__typename": "StatusContext", "state": "SUCCESS"}],
                }
            )
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 0, 1)

    assert result["status"] == "human_decision_required"
    assert result["message"] == "Pull request merge queue state is ambiguous or unsupported"


@pytest.mark.parametrize("conclusion", ["TIMED_OUT", "ACTION_REQUIRED"])
def test_poll_merge_queue_rejects_completed_terminal_failed_check_conclusions(
    monkeypatch,
    trusted_repo: Path,
    conclusion: str,
) -> None:
    runner = GhRunner(
        {
            (
                "gh",
                "pr",
                "view",
                "feature/opencode-capabilities",
                "--json",
                "state,mergedAt,mergeStateStatus,mergeable,autoMergeRequest,statusCheckRollup,headRefName,headRefOid,url",
            ): json.dumps(
                {
                    "mergedAt": None,
                    "state": "OPEN",
                    "mergeStateStatus": "pending",
                    "statusCheckRollup": [
                        {
                            "__typename": "CheckRun",
                            "name": "test",
                            "workflowName": "test",
                            "status": "COMPLETED",
                            "conclusion": conclusion,
                        }
                    ],
                }
            )
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 0, 1)

    assert result["status"] == "human_decision_required"
    assert result["message"] == "Required merge queue check failed"


def test_poll_merge_queue_failed_check_includes_metadata_and_bounded_log_excerpt(
    monkeypatch,
    trusted_repo: Path,
) -> None:
    details_url = "https://github.com/semanticdreams/spacecore/actions/runs/35993871852/job/107614091892"
    runner = GhRunner(
        {
            (
                "gh",
                "pr",
                "view",
                "feature/opencode-capabilities",
                "--json",
                pr_operator.PR_VIEW_FIELDS,
            ): json.dumps(
                {
                    "mergedAt": None,
                    "state": "OPEN",
                    "mergeStateStatus": "pending",
                    "statusCheckRollup": [
                        {
                            "__typename": "CheckRun",
                            "name": "test",
                            "workflowName": "test",
                            "status": "COMPLETED",
                            "conclusion": "FAILURE",
                            "detailsUrl": details_url,
                            "startedAt": "2026-09-24T11:35:11Z",
                            "completedAt": "2026-09-24T11:50:53Z",
                        }
                    ],
                }
            ),
            (
                "gh",
                "run",
                "view",
                "35993871852",
                "--job",
                "107614091892",
                "--log",
            ): "setup\npytest failed\nsummary\n",
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 0, 1)

    failed_check = result["evidence"]["failed_checks"][0]
    assert result["status"] == "human_decision_required"
    assert result["message"] == "Required merge queue check failed"
    assert failed_check["name"] == "test"
    assert failed_check["workflowName"] == "test"
    assert failed_check["status"] == "COMPLETED"
    assert failed_check["conclusion"] == "FAILURE"
    assert failed_check["detailsUrl"] == details_url
    assert failed_check["startedAt"] == "2026-09-24T11:35:11Z"
    assert failed_check["completedAt"] == "2026-09-24T11:50:53Z"
    assert failed_check["run_id"] == "35993871852"
    assert failed_check["job_id"] == "107614091892"
    assert failed_check["log_excerpt"] == "setup\npytest failed\nsummary"
    assert "log_unavailable" not in failed_check
    assert runner.calls == [
        ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS],
        ["gh", "run", "view", "35993871852", "--job", "107614091892", "--log"],
    ]


def test_poll_merge_queue_failed_check_includes_fail_markers_outside_tail(
    monkeypatch,
    trusted_repo: Path,
) -> None:
    details_url = "https://github.com/semanticdreams/spacecore/actions/runs/35993871852/job/107614091892"
    filler = [f"filler {index}" for index in range(pr_operator.MAX_FAILED_CHECK_LOG_LINES + 5)]
    log = "\n".join(
        [
            "setup",
            "[FAIL] recurrence windows boundary",
            "expected Tuesday, got Monday",
            *filler,
            "Lua error: lua: error: tests/runner.fnl:397: 1 Lua test(s) failed",
        ]
    )
    runner = GhRunner(
        {
            (
                "gh",
                "pr",
                "view",
                "feature/opencode-capabilities",
                "--json",
                pr_operator.PR_VIEW_FIELDS,
            ): json.dumps(
                {
                    "mergedAt": None,
                    "state": "OPEN",
                    "mergeStateStatus": "pending",
                    "statusCheckRollup": [
                        {
                            "__typename": "CheckRun",
                            "name": "test",
                            "workflowName": "test",
                            "status": "COMPLETED",
                            "conclusion": "FAILURE",
                            "detailsUrl": details_url,
                        }
                    ],
                }
            ),
            ("gh", "run", "view", "35993871852", "--job", "107614091892", "--log"): log,
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 0, 1)

    failed_check = result["evidence"]["failed_checks"][0]
    assert "log_excerpt" in failed_check
    assert failed_check["failure_markers"] == [
        {
            "line": 2,
            "match": "[FAIL] recurrence windows boundary",
            "context": ["setup", "[FAIL] recurrence windows boundary", "expected Tuesday, got Monday"],
        }
    ]


def test_actions_log_returns_tail_slice_search_and_full_modes(monkeypatch, trusted_repo: Path) -> None:
    full_log = "line1\nline2\nline3\n[FAIL] bad test\nline4\nline5\x00"
    runner = GhRunner({("gh", "run", "view", "123", "--job", "456", "--log"): full_log})
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.actions_log(
        trusted_repo,
        "123",
        "456",
        tail_lines=2,
        start_line=None,
        line_count=None,
        contains=None,
        context_lines=2,
        max_matches=20,
        full=False,
    )
    assert result["evidence"]["mode"] == "tail"
    assert result["evidence"]["log"] == "line4\nline5"

    result = pr_operator.actions_log(
        trusted_repo,
        "123",
        "456",
        tail_lines=None,
        start_line=2,
        line_count=2,
        contains=None,
        context_lines=2,
        max_matches=20,
        full=False,
    )
    assert result["evidence"]["mode"] == "slice"
    assert result["evidence"]["start_line"] == 2
    assert result["evidence"]["log"] == "line2\nline3"

    result = pr_operator.actions_log(
        trusted_repo,
        "123",
        "456",
        tail_lines=None,
        start_line=None,
        line_count=None,
        contains="[FAIL]",
        context_lines=1,
        max_matches=2,
        full=False,
    )
    assert result["evidence"]["mode"] == "search"
    assert result["evidence"]["matches"][0]["match"] == "[FAIL] bad test"

    result = pr_operator.actions_log(
        trusted_repo,
        "123",
        "456",
        tail_lines=None,
        start_line=None,
        line_count=None,
        contains=None,
        context_lines=2,
        max_matches=20,
        full=True,
    )
    assert result["evidence"]["mode"] == "full"
    assert result["evidence"]["log"] == "line1\nline2\nline3\n[FAIL] bad test\nline4\nline5"


def test_actions_log_search_bounds_oversized_matching_line(monkeypatch, trusted_repo: Path) -> None:
    oversized_match = "[FAIL] " + ("x" * (pr_operator.MAX_FAILED_CHECK_LOG_CHARS * 2))
    full_log = f"setup\n{oversized_match}\nexpected true\n"
    runner = GhRunner({("gh", "run", "view", "123", "--job", "456", "--log"): full_log})
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.actions_log(
        trusted_repo,
        "123",
        "456",
        tail_lines=None,
        start_line=None,
        line_count=None,
        contains="[FAIL]",
        context_lines=1,
        max_matches=20,
        full=False,
    )

    match = result["evidence"]["matches"][0]
    serialized_match = json.dumps(match)
    assert result["status"] == "pass"
    assert match["line"] == 2
    assert "[FAIL]" in match["match"]
    assert len(serialized_match) <= pr_operator.MAX_FAILED_CHECK_LOG_CHARS
    assert oversized_match not in serialized_match


def test_poll_merge_queue_failure_markers_bound_oversized_matching_line(monkeypatch, trusted_repo: Path) -> None:
    details_url = "https://github.com/semanticdreams/spacecore/actions/runs/35993871852/job/107614091892"
    oversized_match = "[FAIL] " + ("x" * (pr_operator.MAX_FAILED_CHECK_LOG_CHARS * 2))
    log = f"setup\n{oversized_match}\nexpected true\n"
    runner = GhRunner(
        {
            ("gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS): json.dumps(
                {
                    "mergedAt": None,
                    "state": "OPEN",
                    "mergeStateStatus": "pending",
                    "statusCheckRollup": [
                        {
                            "__typename": "CheckRun",
                            "name": "test",
                            "workflowName": "test",
                            "status": "COMPLETED",
                            "conclusion": "FAILURE",
                            "detailsUrl": details_url,
                        }
                    ],
                }
            ),
            ("gh", "run", "view", "35993871852", "--job", "107614091892", "--log"): log,
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 0, 1)

    marker = result["evidence"]["failed_checks"][0]["failure_markers"][0]
    serialized_marker = json.dumps(marker)
    assert result["status"] == "human_decision_required"
    assert marker["line"] == 2
    assert "[FAIL]" in marker["match"]
    assert len(serialized_marker) <= pr_operator.MAX_FAILED_CHECK_LOG_CHARS
    assert oversized_match not in serialized_marker


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"run_id": "abc", "job_id": "456"}, "invalid_run_id"),
        ({"run_id": "123", "job_id": "job"}, "invalid_job_id"),
        ({"start_line": 0, "line_count": 1}, "invalid_start_line"),
        ({"start_line": 1, "line_count": 0}, "invalid_line_count"),
        ({"tail_lines": 0}, "invalid_tail_lines"),
        ({"context_lines": -1}, "invalid_context_lines"),
        ({"max_matches": 0}, "invalid_max_matches"),
    ],
)
def test_actions_log_invalid_bounds_return_structured_failures(trusted_repo: Path, kwargs: dict[str, object], code: str) -> None:
    params = {
        "run_id": "123",
        "job_id": "456",
        "tail_lines": 1,
        "start_line": None,
        "line_count": None,
        "contains": None,
        "context_lines": 2,
        "max_matches": 20,
        "full": False,
    }
    params.update(kwargs)

    result = pr_operator.actions_log(trusted_repo, **params)

    assert result["status"] == "fail"
    assert result["evidence"]["code"] == code


def test_actions_log_rejects_tail_plus_slice_combination(trusted_repo: Path) -> None:
    result = pr_operator.actions_log(
        trusted_repo,
        "123",
        "456",
        tail_lines=20,
        start_line=100,
        line_count=5,
        contains=None,
        context_lines=2,
        max_matches=20,
        full=False,
    )

    assert result["status"] == "fail"
    assert result["evidence"]["code"] == "invalid_mode_combination"


def test_failed_actions_log_bundle_current_writes_full_logs_and_markers(monkeypatch, trusted_repo: Path) -> None:
    details_url = "https://github.com/semanticdreams/spacecore/actions/runs/123/job/456"
    log = "setup\n[FAIL] bad test\nexpected true\n"
    runner = GhRunner(
        {
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS): json.dumps(
                {
                    "statusCheckRollup": [
                        {
                            "__typename": "CheckRun",
                            "name": "test",
                            "status": "COMPLETED",
                            "conclusion": "FAILURE",
                            "detailsUrl": details_url,
                        }
                    ]
                }
            ),
            ("gh", "run", "view", "123", "--job", "456", "--log"): log,
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.failed_actions_log_bundle_current(trusted_repo)

    assert result["status"] == "pass"
    entry = result["evidence"]["logs"][0]
    assert entry["run_id"] == "123"
    assert entry["job_id"] == "456"
    assert entry["path"] == "build/opencode/actions-logs/123-456.log"
    assert (trusted_repo / "build/opencode/actions-logs/123-456.log").read_text() == log
    assert entry["failure_markers"] == [
        {"line": 2, "match": "[FAIL] bad test", "context": ["setup", "[FAIL] bad test", "expected true"]}
    ]


def test_poll_merge_queue_continues_when_failed_check_log_waits_for_in_progress_workflow_run(
    monkeypatch,
    trusted_repo: Path,
) -> None:
    details_url = "https://github.com/semanticdreams/spacecore/actions/runs/35997448859/job/107625178432"
    states = iter(
        [
            {
                "mergedAt": None,
                "state": "OPEN",
                "mergeStateStatus": "pending",
                "statusCheckRollup": [
                    {
                        "__typename": "CheckRun",
                        "name": "test",
                        "workflowName": "test",
                        "status": "COMPLETED",
                        "conclusion": "FAILURE",
                        "detailsUrl": details_url,
                    },
                    {
                        "__typename": "CheckRun",
                        "name": "build-windows",
                        "workflowName": "test",
                        "status": "IN_PROGRESS",
                        "conclusion": None,
                    },
                ],
            },
            {
                "mergedAt": None,
                "state": "OPEN",
                "mergeStateStatus": "pending",
                "statusCheckRollup": [
                    {
                        "__typename": "CheckRun",
                        "name": "test",
                        "workflowName": "test",
                        "status": "COMPLETED",
                        "conclusion": "FAILURE",
                        "detailsUrl": details_url,
                        "completedAt": "2026-09-24T18:12:00Z",
                    }
                ],
            },
        ]
    )
    calls = []

    def fake_run(args, cwd: Path, check: bool = True):
        del cwd, check
        args = list(args)
        calls.append(args)
        if args == ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS]:
            return command_result(args, json.dumps(next(states)))
        if args == ["gh", "run", "view", "35997448859", "--job", "107625178432", "--log"]:
            log_attempts = sum(1 for call in calls if call == args)
            if log_attempts == 1:
                return command_result(
                    args,
                    returncode=1,
                    stderr="run 35997448859 is still in progress; logs will be available when it is complete",
                )
            return command_result(args, "collect logs\npytest failed\n")
        raise AssertionError(args)

    monkeypatch.setattr(pr_operator, "run_command", fake_run)
    monkeypatch.setattr(pr_operator.time, "sleep", lambda seconds: None)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 60, 1)

    failed_check = result["evidence"]["failed_checks"][0]
    assert result["status"] == "human_decision_required"
    assert result["message"] == "Required merge queue check failed"
    assert failed_check["name"] == "test"
    assert failed_check["workflowName"] == "test"
    assert failed_check["run_id"] == "35997448859"
    assert failed_check["job_id"] == "107625178432"
    assert failed_check["log_excerpt"] == "collect logs\npytest failed"
    assert calls == [
        ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS],
        ["gh", "run", "view", "35997448859", "--job", "107625178432", "--log"],
        ["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS],
        ["gh", "run", "view", "35997448859", "--job", "107625178432", "--log"],
    ]


def test_poll_merge_queue_failed_check_reports_unavailable_log_without_parseable_details_url(
    monkeypatch,
    trusted_repo: Path,
) -> None:
    runner = GhRunner(
        {
            (
                "gh",
                "pr",
                "view",
                "feature/opencode-capabilities",
                "--json",
                pr_operator.PR_VIEW_FIELDS,
            ): json.dumps(
                {
                    "mergedAt": None,
                    "state": "OPEN",
                    "mergeStateStatus": "pending",
                    "statusCheckRollup": [
                        {
                            "__typename": "CheckRun",
                            "name": "test",
                            "workflowName": "test",
                            "status": "COMPLETED",
                            "conclusion": "FAILURE",
                            "detailsUrl": "https://example.invalid/not-a-github-actions-job",
                        }
                    ],
                }
            )
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 0, 1)

    failed_check = result["evidence"]["failed_checks"][0]
    assert result["status"] == "human_decision_required"
    assert failed_check["name"] == "test"
    assert failed_check["detailsUrl"] == "https://example.invalid/not-a-github-actions-job"
    assert failed_check["log_unavailable"] == "detailsUrl did not contain a parseable GitHub Actions run/job id"
    assert "log_excerpt" not in failed_check
    assert runner.calls == [["gh", "pr", "view", "feature/opencode-capabilities", "--json", pr_operator.PR_VIEW_FIELDS]]


def test_poll_merge_queue_requires_merged_at_for_success(monkeypatch, trusted_repo: Path) -> None:
    runner = GhRunner(
        {
            (
                "gh",
                "pr",
                "view",
                "feature/opencode-capabilities",
                "--json",
                "state,mergedAt,mergeStateStatus,mergeable,autoMergeRequest,statusCheckRollup,headRefName,headRefOid,url",
            ): json.dumps({"mergedAt": None, "state": "CLOSED", "mergeStateStatus": "clean", "statusCheckRollup": []})
        }
    )
    monkeypatch.setattr(pr_operator, "run_command", runner)

    result = pr_operator.poll_merge_queue(trusted_repo, "feature/opencode-capabilities", 0, 1)

    assert result["status"] == "human_decision_required"


def test_cli_emits_json_and_returns_human_decision_for_invalid_branch(monkeypatch, trusted_repo: Path, capsys) -> None:
    exit_code = pr_operator.main(["create", "--repo-root", str(trusted_repo), "--head", "bad branch"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "human_decision_required"
    assert set(payload) == {"status", "action", "message", "evidence"}


def test_cli_current_branch_operations_take_no_untrusted_branch_or_timeout_arguments(monkeypatch, trusted_repo: Path, capsys) -> None:
    calls = []

    def fake_create_current(repo_root: Path):
        calls.append(repo_root)
        return {"status": "pass", "action": "create_pr", "message": "ok", "evidence": {}}

    monkeypatch.setattr(pr_operator, "create_current_pr", fake_create_current)

    exit_code = pr_operator.main(["create-current", "--repo-root", str(trusted_repo)])

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "pass"
    assert calls == [trusted_repo]
