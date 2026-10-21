import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import opencode_capabilities as capabilities
import opencode_git_integrate as git_integrate


def command_result(args: list[str], stdout: str = "", returncode: int = 0, stderr: str = "") -> capabilities.CommandResult:
    return capabilities.CommandResult(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


class GitRunner:
    def __init__(self, outputs: dict[tuple[str, ...], str | capabilities.CommandResult]) -> None:
        self.outputs = outputs
        self.calls: list[list[str]] = []
        self.checks: list[bool] = []

    def __call__(self, args, cwd: Path, check: bool = True):
        del cwd
        args = list(args)
        self.calls.append(args)
        self.checks.append(check)
        output = self.outputs.get(tuple(args), "")
        if isinstance(output, capabilities.CommandResult):
            if check and output.returncode != 0:
                raise capabilities.CapabilityError(
                    "command_failed",
                    "Command failed while evaluating capability guard",
                    {"args": output.args, "returncode": output.returncode, "stderr": output.stderr.strip()},
                )
            return output
        return command_result(args, output)


@pytest.fixture
def trusted_repo(monkeypatch, tmp_path: Path) -> Path:
    repo = tmp_path / "space"
    repo.mkdir()
    monkeypatch.setattr(git_integrate, "ensure_space_repo", lambda repo_root: repo)
    return repo


def test_status_reports_expanded_freshness_evidence_when_current_with_origin_main(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "HEAD"): "abc123\n",
            ("git", "rev-parse", "origin/main"): "base456\n",
            ("git", "status", "--porcelain"): " M file.py\n",
            ("git", "merge-base", "HEAD", "origin/main"): "base456\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=0,
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.git_status(trusted_repo)

    assert result["status"] == "pass"
    assert result["evidence"] == {
        "branch": "feature/opencode-capabilities",
        "head_sha": "abc123",
        "dirty": True,
        "origin_main_merge_base": "base456",
        "origin_main_sha": "base456",
        "origin_main_is_ancestor_of_head": True,
        "branch_current_with_origin_main": True,
        "safe_merge_needed": False,
    }
    assert [call for call in runner.calls if call[:3] == ["git", "merge-base", "--is-ancestor"]] == [
        ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"]
    ]
    assert runner.checks[runner.calls.index(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"])] is False


def test_status_reports_merge_needed_when_origin_main_is_not_ancestor_of_head(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "HEAD"): "abc123\n",
            ("git", "rev-parse", "origin/main"): "def789\n",
            ("git", "status", "--porcelain"): "",
            ("git", "merge-base", "HEAD", "origin/main"): "base456\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=1,
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.git_status(trusted_repo)

    assert result["status"] == "pass"
    assert result["evidence"]["origin_main_sha"] == "def789"
    assert result["evidence"]["origin_main_is_ancestor_of_head"] is False
    assert result["evidence"]["branch_current_with_origin_main"] is False
    assert result["evidence"]["safe_merge_needed"] is True


def test_status_fails_closed_on_unexpected_origin_main_ancestor_return_code(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "HEAD"): "abc123\n",
            ("git", "rev-parse", "origin/main"): "def789\n",
            ("git", "status", "--porcelain"): "",
            ("git", "merge-base", "HEAD", "origin/main"): "base456\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=128,
                stderr="fatal: not a valid object name origin/main\n",
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.git_status(trusted_repo)

    assert result["status"] == "fail"
    assert result["evidence"]["code"] == "command_failed"
    assert result["evidence"]["details"]["args"] == ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"]
    assert result["evidence"]["details"]["returncode"] == 128


def test_merge_origin_main_refuses_dirty_worktree(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): " M task.py\n",
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.merge_origin_main(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert ["git", "fetch", "origin", "main"] not in runner.calls
    assert ["git", "merge", "--no-edit", "origin/main"] not in runner.calls


def test_merge_origin_main_refuses_main_branch(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.merge_origin_main(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert ["git", "fetch", "origin", "main"] not in runner.calls


def test_merge_origin_main_runs_only_fetch_origin_main_then_no_edit_merge(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "fetch", "origin", "main"): "",
            ("git", "merge", "--no-edit", "origin/main"): "Already up to date.\n",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.merge_origin_main(trusted_repo)

    assert result["status"] == "pass"
    assert runner.calls == [
        ["git", "status", "--porcelain"],
        ["git", "branch", "--show-current"],
        ["git", "fetch", "origin", "main"],
        ["git", "merge", "--no-edit", "origin/main"],
    ]


def test_push_current_refuses_main_invalid_branch_and_pushes_only_head_to_current_branch(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)
    assert git_integrate.push_current(trusted_repo)["status"] == "human_decision_required"

    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "bad branch\n",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)
    assert git_integrate.push_current(trusted_repo)["status"] == "human_decision_required"

    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "push", "origin", "HEAD:refs/heads/feature/opencode-capabilities"): "",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)
    result = git_integrate.push_current(trusted_repo)

    assert result["status"] == "pass"
    assert runner.calls == [
        ["git", "status", "--porcelain"],
        ["git", "branch", "--show-current"],
        ["git", "push", "origin", "HEAD:refs/heads/feature/opencode-capabilities"],
    ]


def test_derive_followup_branch_name_appends_followup_suffix() -> None:
    assert (
        git_integrate._derive_followup_branch_name("juicyrebel/test-workflow-artifact-names", "caad43f")
        == "juicyrebel/test-workflow-artifact-names-followup-caad43f"
    )


def test_derive_followup_branch_name_uses_bounded_fallback_when_appended_name_would_be_too_long() -> None:
    source = "juicyrebel/" + ("nested-segment/" * 20) + "feature"

    assert git_integrate._derive_followup_branch_name(source, "caad43f") == "fix/followup-caad43f"


def test_derive_local_main_wrapup_branch_name_uses_fast_dev_local_main_prefix() -> None:
    assert git_integrate._derive_local_main_wrapup_branch_name("caad43f") == "fast-dev/local-main-caad43f"


def test_create_local_main_wrapup_branch_switches_to_deterministic_branch_from_clean_main(monkeypatch, trusted_repo: Path) -> None:
    target = "fast-dev/local-main-caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
            ("git", "fetch", "origin", "main"): "",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "rev-parse", "HEAD"): "caad43fabc123\n",
            ("git", "rev-parse", "origin/main"): "base456def789\n",
            ("git", "rev-list", "--count", "origin/main..HEAD"): "2\n",
            ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"): command_result(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
                returncode=1,
            ),
            ("git", "ls-remote", "--exit-code", "--heads", "origin", target): command_result(
                ["git", "ls-remote", "--exit-code", "--heads", "origin", target],
                returncode=2,
            ),
            ("git", "switch", "-c", target): "",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_local_main_wrapup_branch(trusted_repo)

    assert result["status"] == "pass"
    assert result["evidence"] == {
        "source_branch": "main",
        "wrapup_branch": target,
        "short_head_sha": "caad43f",
        "source_head_sha": "caad43fabc123",
        "origin_main_sha": "base456def789",
        "local_commits_beyond_origin_main": 2,
        "args": ["git", "switch", "-c", target],
    }
    assert runner.calls == [
        ["git", "status", "--porcelain"],
        ["git", "branch", "--show-current"],
        ["git", "fetch", "origin", "main"],
        ["git", "rev-parse", "--short=7", "HEAD"],
        ["git", "rev-parse", "HEAD"],
        ["git", "rev-parse", "origin/main"],
        ["git", "rev-list", "--count", "origin/main..HEAD"],
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
        ["git", "ls-remote", "--exit-code", "--heads", "origin", target],
        ["git", "switch", "-c", target],
    ]
    forbidden = {"push", "merge", "rebase", "reset", "clean"}
    assert [call for call in runner.calls if len(call) > 1 and call[0] == "git" and call[1] in forbidden] == []
    assert [call for call in runner.calls if call[:3] == ["git", "branch", "-d"]] == []


def test_create_local_main_wrapup_branch_refuses_dirty_worktree(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner({("git", "status", "--porcelain"): " M task.py\n", ("git", "branch", "--show-current"): "main\n"})
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_local_main_wrapup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_local_main_wrapup_branch_refuses_detached_head(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner({("git", "status", "--porcelain"): "", ("git", "branch", "--show-current"): "\n"})
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_local_main_wrapup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_local_main_wrapup_branch_refuses_non_main_branch(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner({("git", "status", "--porcelain"): "", ("git", "branch", "--show-current"): "feature/work\n"})
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_local_main_wrapup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_local_main_wrapup_branch_refuses_zero_local_commits(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
            ("git", "fetch", "origin", "main"): "",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "rev-parse", "HEAD"): "caad43fabc123\n",
            ("git", "rev-parse", "origin/main"): "caad43fabc123\n",
            ("git", "rev-list", "--count", "origin/main..HEAD"): "0\n",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_local_main_wrapup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_local_main_wrapup_branch_refuses_unsafe_derived_target(monkeypatch, trusted_repo: Path) -> None:
    target = "fast-dev/local main caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
            ("git", "fetch", "origin", "main"): "",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "rev-parse", "HEAD"): "caad43fabc123\n",
            ("git", "rev-parse", "origin/main"): "base456def789\n",
            ("git", "rev-list", "--count", "origin/main..HEAD"): "1\n",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)
    monkeypatch.setattr(git_integrate, "_derive_local_main_wrapup_branch_name", lambda _sha: target)

    result = git_integrate.create_local_main_wrapup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"]["code"] == "invalid_branch"
    assert result["evidence"]["wrapup_branch"] == target
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_local_main_wrapup_branch_refuses_when_local_target_exists(monkeypatch, trusted_repo: Path) -> None:
    target = "fast-dev/local-main-caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
            ("git", "fetch", "origin", "main"): "",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "rev-parse", "HEAD"): "caad43fabc123\n",
            ("git", "rev-parse", "origin/main"): "base456def789\n",
            ("git", "rev-list", "--count", "origin/main..HEAD"): "1\n",
            ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"): command_result(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
                returncode=0,
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_local_main_wrapup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_local_main_wrapup_branch_refuses_when_remote_target_exists(monkeypatch, trusted_repo: Path) -> None:
    target = "fast-dev/local-main-caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
            ("git", "fetch", "origin", "main"): "",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "rev-parse", "HEAD"): "caad43fabc123\n",
            ("git", "rev-parse", "origin/main"): "base456def789\n",
            ("git", "rev-list", "--count", "origin/main..HEAD"): "1\n",
            ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"): command_result(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
                returncode=1,
            ),
            ("git", "ls-remote", "--exit-code", "--heads", "origin", target): command_result(
                ["git", "ls-remote", "--exit-code", "--heads", "origin", target],
                returncode=0,
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_local_main_wrapup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_local_main_wrapup_branch_fails_when_fetch_fails(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
            ("git", "fetch", "origin", "main"): command_result(
                ["git", "fetch", "origin", "main"], returncode=128, stderr="fatal: fetch failed\n"
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_local_main_wrapup_branch(trusted_repo)

    assert result["status"] == "fail"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


@pytest.mark.parametrize(
    "output",
    [
        command_result(["git", "rev-list", "--count", "origin/main..HEAD"], returncode=128, stderr="fatal: bad revision\n"),
        "not-a-count\n",
    ],
)
def test_create_local_main_wrapup_branch_fails_when_local_commit_count_unavailable(monkeypatch, trusted_repo: Path, output) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
            ("git", "fetch", "origin", "main"): "",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "rev-parse", "HEAD"): "caad43fabc123\n",
            ("git", "rev-parse", "origin/main"): "base456def789\n",
            ("git", "rev-list", "--count", "origin/main..HEAD"): output,
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_local_main_wrapup_branch(trusted_repo)

    assert result["status"] == "fail"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_followup_branch_refuses_dirty_worktree(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): " M task.py\n",
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_followup_branch_refuses_main_branch(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_followup_branch_refuses_detached_head(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "\n",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_followup_branch_refuses_when_origin_main_not_in_head(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=1,
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []
    assert runner.checks[runner.calls.index(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"])] is False


def test_create_followup_branch_refuses_unsafe_current_branch_name(monkeypatch, trusted_repo: Path) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "unsafe/branch\n",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=0,
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"]["code"] == "invalid_branch"
    assert result["evidence"]["branch"] == "unsafe/branch"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_followup_branch_refuses_unsafe_derived_target_branch_name(monkeypatch, trusted_repo: Path) -> None:
    target = "feature/opencode-capabilities followup caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=0,
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)
    monkeypatch.setattr(git_integrate, "_derive_followup_branch_name", lambda _branch, _sha: target)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"]["code"] == "invalid_branch"
    assert result["evidence"]["followup_branch"] == target
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_followup_branch_refuses_when_local_target_exists(monkeypatch, trusted_repo: Path) -> None:
    target = "feature/opencode-capabilities-followup-caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=0,
            ),
            ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"): command_result(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
                returncode=0,
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []
    assert runner.checks[runner.calls.index(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"])] is False


def test_create_followup_branch_checks_local_conflict_on_bounded_fallback(monkeypatch, trusted_repo: Path) -> None:
    source = "juicyrebel/" + ("nested-segment/" * 20) + "feature"
    target = "fix/followup-caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): f"{source}\n",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=0,
            ),
            ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"): command_result(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
                returncode=0,
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"]["followup_branch"] == target
    assert ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"] in runner.calls
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_followup_branch_refuses_when_remote_target_exists(monkeypatch, trusted_repo: Path) -> None:
    target = "feature/opencode-capabilities-followup-caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=0,
            ),
            ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"): command_result(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
                returncode=1,
            ),
            ("git", "ls-remote", "--exit-code", "--heads", "origin", target): command_result(
                ["git", "ls-remote", "--exit-code", "--heads", "origin", target],
                returncode=0,
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []
    assert runner.checks[runner.calls.index(["git", "ls-remote", "--exit-code", "--heads", "origin", target])] is False


def test_create_followup_branch_checks_remote_conflict_on_bounded_fallback(monkeypatch, trusted_repo: Path) -> None:
    source = "juicyrebel/" + ("nested-segment/" * 20) + "feature"
    target = "fix/followup-caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): f"{source}\n",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=0,
            ),
            ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"): command_result(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
                returncode=1,
            ),
            ("git", "ls-remote", "--exit-code", "--heads", "origin", target): command_result(
                ["git", "ls-remote", "--exit-code", "--heads", "origin", target],
                returncode=0,
            ),
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"]["followup_branch"] == target
    assert ["git", "ls-remote", "--exit-code", "--heads", "origin", target] in runner.calls
    assert [call for call in runner.calls if call[:3] == ["git", "switch", "-c"]] == []


def test_create_followup_branch_switches_to_deterministic_absent_target(monkeypatch, trusted_repo: Path) -> None:
    target = "feature/opencode-capabilities-followup-caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=0,
            ),
            ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"): command_result(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
                returncode=1,
            ),
            ("git", "ls-remote", "--exit-code", "--heads", "origin", target): command_result(
                ["git", "ls-remote", "--exit-code", "--heads", "origin", target],
                returncode=2,
            ),
            ("git", "switch", "-c", target): "",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "pass"
    assert result["evidence"]["source_branch"] == "feature/opencode-capabilities"
    assert result["evidence"]["followup_branch"] == target
    assert runner.calls == [
        ["git", "status", "--porcelain"],
        ["git", "branch", "--show-current"],
        ["git", "rev-parse", "--short=7", "HEAD"],
        ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
        ["git", "ls-remote", "--exit-code", "--heads", "origin", target],
        ["git", "switch", "-c", target],
    ]


def test_create_followup_branch_switches_from_local_main_wrapup_branch(monkeypatch, trusted_repo: Path) -> None:
    target = "fast-dev/local-main-caad43f-followup-deadbee"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "fast-dev/local-main-caad43f\n",
            ("git", "rev-parse", "--short=7", "HEAD"): "deadbee\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=0,
            ),
            ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"): command_result(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
                returncode=1,
            ),
            ("git", "ls-remote", "--exit-code", "--heads", "origin", target): command_result(
                ["git", "ls-remote", "--exit-code", "--heads", "origin", target],
                returncode=2,
            ),
            ("git", "switch", "-c", target): "",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    result = git_integrate.create_followup_branch(trusted_repo)

    assert result["status"] == "pass"
    assert result["evidence"]["source_branch"] == "fast-dev/local-main-caad43f"
    assert result["evidence"]["followup_branch"] == target
    assert ["git", "switch", "-c", target] in runner.calls


def test_cli_create_followup_branch_emits_json_and_returns_success(monkeypatch, trusted_repo: Path, capsys) -> None:
    target = "feature/opencode-capabilities-followup-caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "feature/opencode-capabilities\n",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"): command_result(
                ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                returncode=0,
            ),
            ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"): command_result(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
                returncode=1,
            ),
            ("git", "ls-remote", "--exit-code", "--heads", "origin", target): command_result(
                ["git", "ls-remote", "--exit-code", "--heads", "origin", target],
                returncode=2,
            ),
            ("git", "switch", "-c", target): "",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    exit_code = git_integrate.main(["create-followup-branch", "--repo-root", str(trusted_repo)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "pass"
    assert payload["action"] == "create_followup_branch"
    assert payload["evidence"]["followup_branch"] == target


def test_cli_create_local_main_wrapup_branch_emits_json_and_returns_success(monkeypatch, trusted_repo: Path, capsys) -> None:
    target = "fast-dev/local-main-caad43f"
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
            ("git", "fetch", "origin", "main"): "",
            ("git", "rev-parse", "--short=7", "HEAD"): "caad43f\n",
            ("git", "rev-parse", "HEAD"): "caad43fabc123\n",
            ("git", "rev-parse", "origin/main"): "base456def789\n",
            ("git", "rev-list", "--count", "origin/main..HEAD"): "1\n",
            ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"): command_result(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
                returncode=1,
            ),
            ("git", "ls-remote", "--exit-code", "--heads", "origin", target): command_result(
                ["git", "ls-remote", "--exit-code", "--heads", "origin", target],
                returncode=2,
            ),
            ("git", "switch", "-c", target): "",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    exit_code = git_integrate.main(["create-local-main-wrapup-branch", "--repo-root", str(trusted_repo)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "pass"
    assert payload["action"] == "create_local_main_wrapup_branch"
    assert payload["evidence"]["wrapup_branch"] == target


def test_cli_emits_json_and_returns_nonzero_on_unsafe_state(monkeypatch, trusted_repo: Path, capsys) -> None:
    runner = GitRunner(
        {
            ("git", "status", "--porcelain"): "",
            ("git", "branch", "--show-current"): "main\n",
        }
    )
    monkeypatch.setattr(git_integrate, "run_command", runner)

    exit_code = git_integrate.main(["push-current", "--repo-root", str(trusted_repo)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "human_decision_required"
    assert set(payload) == {"status", "action", "message", "evidence"}


DAILY_TARGET = "automation/daily-devlog/2026-10-21"
DAILY_BASE = "a" * 40
DAILY_SOURCE = "b" * 40
DAILY_STATUS = ["git", "status", "--porcelain", "--untracked-files=all"]
DAILY_BRANCH = ["git", "branch", "--show-current"]
DAILY_HEAD = ["git", "rev-parse", "--verify", "HEAD^{commit}"]
DAILY_FETCH = ["git", "fetch", "--no-tags", "origin", "refs/heads/main:refs/remotes/origin/main"]
DAILY_MAIN = ["git", "rev-parse", "--verify", "refs/remotes/origin/main^{commit}"]
DAILY_LOCAL = ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{DAILY_TARGET}"]
DAILY_LOCAL_SHA = ["git", "rev-parse", "--verify", f"refs/heads/{DAILY_TARGET}^{{commit}}"]
DAILY_REMOTE = ["git", "ls-remote", "--exit-code", "--heads", "origin", f"refs/heads/{DAILY_TARGET}"]
DAILY_WORKTREES = ["git", "worktree", "list", "--porcelain", "-z"]
DAILY_SWITCH = ["git", "switch", "--no-track", "-c", DAILY_TARGET, DAILY_BASE]


class DailyRunner:
    """Ordered, exhaustive responses: an omitted mock can never mean absence."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    def __call__(self, args, cwd, check=True):
        self.calls.append(list(args))
        assert self.steps, f"Unmocked command: {args}"
        expected, output = self.steps.pop(0)
        assert list(args) == expected
        result = output if isinstance(output, capabilities.CommandResult) else command_result(expected, output)
        if check and result.returncode:
            raise capabilities.CapabilityError("command_failed", "Mock Git command failed", {"args": expected, "returncode": result.returncode})
        return result


def daily_operation(repo):
    operation = getattr(git_integrate, "create_daily_devlog_branch", None)
    assert callable(operation), "Missing bounded daily-devlog branch operation"
    return operation(repo)


@pytest.fixture
def daily_clock(monkeypatch):
    class Clock:
        calls = []

        @classmethod
        def now(cls, tz):
            cls.calls.append(tz)
            # A second sample crosses midnight and must never be used.
            return datetime(2026, 10, 21 if len(cls.calls) == 1 else 22, 23, 59, 59, tzinfo=timezone.utc)

    monkeypatch.setattr(git_integrate, "datetime", Clock, raising=False)
    return Clock


def daily_worktree(path, branch="feature/source", sha=DAILY_SOURCE, extra=""):
    return f"worktree {path}\0HEAD {sha}\0branch refs/heads/{branch}\0{extra}\0"


def daily_steps(repo, *, current=False, remote_sha=None):
    source = DAILY_TARGET if current else "feature/source"
    sha = DAILY_BASE if current else DAILY_SOURCE
    local = command_result(DAILY_LOCAL, returncode=0 if current else 1)
    remote = command_result(DAILY_REMOTE, f"{remote_sha}\trefs/heads/{DAILY_TARGET}\n" if remote_sha else "", 0 if remote_sha else 2)
    steps = [(DAILY_STATUS, ""), (DAILY_BRANCH, source + "\n"), (DAILY_HEAD, sha + "\n"),
             (DAILY_FETCH, ""), (DAILY_MAIN, DAILY_BASE + "\n"), (DAILY_LOCAL, local)]
    if current:
        steps.append((DAILY_LOCAL_SHA, DAILY_BASE + "\n"))
    steps.extend([(DAILY_REMOTE, remote), (DAILY_WORKTREES, daily_worktree(repo, source, sha)),
                  (DAILY_STATUS, ""), (DAILY_BRANCH, source + "\n"), (DAILY_HEAD, sha + "\n")])
    if not current:
        steps.extend([(DAILY_SWITCH, ""), (DAILY_STATUS, ""), (DAILY_BRANCH, DAILY_TARGET + "\n"), (DAILY_HEAD, DAILY_BASE + "\n")])
    return steps


def install_daily_runner(monkeypatch, steps):
    runner = DailyRunner(steps)
    monkeypatch.setattr(git_integrate, "run_command", runner)
    return runner


def test_daily_devlog_pins_fresh_base_and_samples_utc_once(monkeypatch, trusted_repo, daily_clock):
    runner = install_daily_runner(monkeypatch, daily_steps(trusted_repo))
    result = daily_operation(trusted_repo)
    assert result["status"] == "pass"
    assert result["action"] == "create_daily_devlog_branch"
    evidence = result["evidence"]
    for key, value in {"utc_date": "2026-10-21", "source_branch": "feature/source", "source_head_sha": DAILY_SOURCE,
                       "target_branch": DAILY_TARGET, "origin_main_sha": DAILY_BASE, "head_sha": DAILY_BASE,
                       "already_current": False, "local_target_exists": False, "remote_target_sha": None,
                       "other_worktree_holders": []}.items():
        assert evidence[key] == value
    assert evidence["commands"] == runner.calls
    assert not runner.steps
    assert daily_clock.calls == [timezone.utc]
    assert all(call[1] not in {"push", "merge", "rebase", "reset", "clean", "prune"} for call in runner.calls)


@pytest.mark.parametrize("branch,dirty", [("main", ""), ("", ""), ("unsafe/source", ""), ("bad branch", ""),
                                          ("feature/../bad", ""), ("feature/source", " M tracked\n"),
                                          ("feature/source", "?? untracked\n")])
def test_daily_devlog_refuses_unsafe_source_before_fetch(monkeypatch, trusted_repo, daily_clock, branch, dirty):
    runner = install_daily_runner(monkeypatch, [(DAILY_STATUS, dirty), (DAILY_BRANCH, branch + "\n")])
    assert daily_operation(trusted_repo)["status"] == "human_decision_required"
    assert not any(call[1] in {"fetch", "switch"} for call in runner.calls)
    assert not daily_clock.calls


def test_daily_devlog_untrusted_repo_cannot_execute_git(monkeypatch, tmp_path):
    def untrusted(_):
        raise capabilities.CapabilityError("invalid_repo", "Untrusted origin")
    monkeypatch.setattr(git_integrate, "ensure_space_repo", untrusted)
    runner = install_daily_runner(monkeypatch, [])
    result = daily_operation(tmp_path)
    assert result["status"] == "fail"
    assert result["evidence"]["code"] == "invalid_repo"
    assert not runner.calls


@pytest.mark.parametrize("remote_sha", [None, DAILY_BASE])
def test_daily_devlog_strict_retry_is_noop(monkeypatch, trusted_repo, daily_clock, remote_sha):
    runner = install_daily_runner(monkeypatch, daily_steps(trusted_repo, current=True, remote_sha=remote_sha))
    result = daily_operation(trusted_repo)
    assert result["status"] == "pass"
    assert result["evidence"]["already_current"] is True
    assert result["evidence"]["head_sha"] == DAILY_BASE
    assert not runner.steps
    assert not any(call[1] == "switch" for call in runner.calls)


@pytest.mark.parametrize("collision", ["local", "remote", "remote-other", "holder", "locked", "prunable", "progressed", "retry-remote-other"])
def test_daily_devlog_refuses_collisions_without_switch(monkeypatch, trusted_repo, daily_clock, collision):
    current = collision in {"progressed", "retry-remote-other"}
    steps = daily_steps(trusted_repo, current=current, remote_sha=DAILY_SOURCE if "other" in collision else DAILY_BASE if collision == "remote" else None)
    if collision == "local":
        index = next(i for i, (args, _) in enumerate(steps) if args == DAILY_LOCAL)
        steps[index] = (DAILY_LOCAL, command_result(DAILY_LOCAL))
        steps.insert(index + 1, (DAILY_LOCAL_SHA, DAILY_BASE + "\n"))
    if collision in {"holder", "locked", "prunable"}:
        index = next(i for i, (args, _) in enumerate(steps) if args == DAILY_WORKTREES)
        extra = f"{collision} reason with\nnewline\0" if collision != "holder" else ""
        steps[index] = (DAILY_WORKTREES, steps[index][1] + daily_worktree("/missing/other\nworktree", DAILY_TARGET, DAILY_BASE, extra))
    if collision == "progressed":
        steps = [(args, DAILY_SOURCE + "\n" if args in (DAILY_HEAD, DAILY_LOCAL_SHA) else output) for args, output in steps]
        steps = [(args, daily_worktree(trusted_repo, DAILY_TARGET, DAILY_SOURCE) if args == DAILY_WORKTREES else output) for args, output in steps]
    runner = install_daily_runner(monkeypatch, steps)
    result = daily_operation(trusted_repo)
    assert result["status"] == "human_decision_required"
    assert not any(call[1] == "switch" for call in runner.calls)
    if collision in {"holder", "locked", "prunable"}:
        assert result["evidence"]["other_worktree_holders"][0]["worktree"] == "/missing/other\nworktree"


@pytest.mark.parametrize("command", [DAILY_STATUS, DAILY_BRANCH, DAILY_HEAD, DAILY_FETCH, DAILY_MAIN, DAILY_LOCAL, DAILY_REMOTE, DAILY_WORKTREES, DAILY_SWITCH])
def test_daily_devlog_git_errors_fail_closed(monkeypatch, trusted_repo, daily_clock, command):
    steps = daily_steps(trusted_repo)
    index = next(i for i, (args, _) in enumerate(steps) if args == command)
    steps[index] = (command, command_result(command, returncode=128, stderr="fatal: unavailable"))
    runner = install_daily_runner(monkeypatch, steps)
    result = daily_operation(trusted_repo)
    assert result["status"] == "fail"
    assert result["evidence"]["code"] == "command_failed"
    assert runner.calls[-1] == command


@pytest.mark.parametrize("command,output", [
    (DAILY_HEAD, "short\n"), (DAILY_MAIN, "a" * 39 + "z\n"), (DAILY_MAIN, DAILY_BASE + "\n" + DAILY_SOURCE),
    (DAILY_REMOTE, ""), (DAILY_REMOTE, f"{DAILY_BASE}\trefs/heads/{DAILY_TARGET}-suffix\n"),
    (DAILY_REMOTE, f"short\trefs/heads/{DAILY_TARGET}\n"),
    (DAILY_REMOTE, f"{DAILY_BASE}\n\trefs/heads/{DAILY_TARGET}\n"),
    (DAILY_REMOTE, f"{DAILY_BASE}\trefs/heads/{DAILY_TARGET}\n" * 2),
    (DAILY_REMOTE, command_result(DAILY_REMOTE, "unexpected", 2)),
    (DAILY_LOCAL, command_result(DAILY_LOCAL, "unexpected", 1)),
    (DAILY_WORKTREES, ""), (DAILY_WORKTREES, "worktree /missing\nHEAD bad\n"),
    (DAILY_WORKTREES, "worktree /missing\0branch refs/heads/feature/source\0\0"),
    (DAILY_WORKTREES, f"worktree /missing\0HEAD {DAILY_BASE}\0detached\0unknown field\0\0"),
    (DAILY_WORKTREES, f"worktree /missing\0HEAD {DAILY_BASE}\0HEAD {DAILY_BASE}\0detached\0\0"),
    (DAILY_WORKTREES, f"worktree /missing\0HEAD {DAILY_BASE}\n\0detached\0\0"),
])
def test_daily_devlog_malformed_evidence_fails_closed(monkeypatch, trusted_repo, daily_clock, command, output):
    steps = daily_steps(trusted_repo)
    index = next(i for i, (args, _) in enumerate(steps) if args == command)
    steps[index] = (command, output)
    runner = install_daily_runner(monkeypatch, steps)
    assert daily_operation(trusted_repo)["status"] == "fail"
    assert not any(call[1] == "switch" for call in runner.calls)


@pytest.mark.parametrize("command,output", [(DAILY_STATUS, "?? raced\n"), (DAILY_BRANCH, "feature/changed\n"), (DAILY_HEAD, "c" * 40 + "\n")])
@pytest.mark.parametrize("postcondition", [False, True])
def test_daily_devlog_rechecks_state_and_never_rolls_back(monkeypatch, trusted_repo, daily_clock, command, output, postcondition):
    steps = daily_steps(trusted_repo)
    indices = [i for i, (args, _) in enumerate(steps) if args == command]
    steps[indices[2 if postcondition else 1]] = (command, output)
    runner = install_daily_runner(monkeypatch, steps)
    result = daily_operation(trusted_repo)
    assert result["status"] == ("fail" if postcondition else "human_decision_required")
    assert (DAILY_SWITCH in runner.calls) is postcondition
    assert not any(call[1] in {"reset", "clean", "checkout", "branch"} and call != DAILY_BRANCH for call in runner.calls)


@pytest.mark.parametrize("status,exit_code", [("pass", 0), ("human_decision_required", 2), ("fail", 3)])
def test_daily_devlog_cli_envelope(monkeypatch, trusted_repo, daily_clock, capsys, status, exit_code):
    steps = daily_steps(trusted_repo) if status == "pass" else [(DAILY_STATUS, ""), (DAILY_BRANCH, "main\n")]
    if status == "fail":
        steps[0] = (DAILY_STATUS, command_result(DAILY_STATUS, returncode=128))
    install_daily_runner(monkeypatch, steps)
    assert git_integrate.main(["create-daily-devlog-branch", "--repo-root", str(trusted_repo)]) == exit_code
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"status", "action", "message", "evidence"}
    assert payload["action"] == "create_daily_devlog_branch"
    assert payload["status"] == status


@pytest.mark.parametrize("argument", ["--date", "--branch", "--base", "--remote", "--force", "--cleanup", "arbitrary"])
def test_daily_devlog_cli_rejects_extra_inputs(monkeypatch, trusted_repo, argument):
    runner = install_daily_runner(monkeypatch, [])
    with pytest.raises(SystemExit) as error:
        git_integrate.main(["create-daily-devlog-branch", "--repo-root", str(trusted_repo), argument])
    assert error.value.code == 2
    assert not runner.calls


@pytest.fixture
def daily_real_repo(monkeypatch, tmp_path, daily_clock):
    # No host config, hooks, credentials or network: all remotes are disposable paths.
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "absent-config"))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Fixture")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "fixture@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Fixture")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "fixture@example.invalid")
    origin = tmp_path / "origin.git"
    repo = tmp_path / "checkout"

    def git(*args, cwd=repo, check=True):
        return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)

    git("init", "--bare", "--initial-branch=main", str(origin), cwd=tmp_path)
    git("init", "--initial-branch=main", str(repo), cwd=tmp_path)
    git("commit", "--allow-empty", "-m", "base")
    git("remote", "add", "origin", str(origin))
    git("push", "origin", "main")
    git("switch", "-c", "feature/source")
    git("commit", "--allow-empty", "-m", "source-only")
    source = git("rev-parse", "HEAD").stdout.strip()
    # Origin moves independently; the local tracking ref is deliberately stale.
    git("clone", str(origin), str(tmp_path / "writer"), cwd=tmp_path)
    git("commit", "--allow-empty", "-m", "fresh-main", cwd=tmp_path / "writer")
    git("push", "origin", "main", cwd=tmp_path / "writer")
    base = git("rev-parse", "HEAD", cwd=tmp_path / "writer").stdout.strip()
    monkeypatch.setattr(git_integrate, "ensure_space_repo", lambda root: repo if root == repo else pytest.fail("unexpected repository"))
    return repo, git, source, base


def test_daily_devlog_real_git_uses_fresh_main_preserves_source_and_has_no_upstream(daily_real_repo, daily_clock):
    repo, git, source, base = daily_real_repo
    git("config", "branch.autoSetupMerge", "always")
    result = daily_operation(repo)
    assert result["status"] == "pass", result
    assert git("branch", "--show-current").stdout.strip() == DAILY_TARGET
    assert git("rev-parse", "HEAD").stdout.strip() == base
    assert git("rev-parse", "feature/source").stdout.strip() == source
    assert git("merge-base", "--is-ancestor", source, "HEAD", check=False).returncode == 1
    assert git("rev-parse", "--abbrev-ref", "@{upstream}", check=False).returncode != 0
    assert git("status", "--porcelain", "--untracked-files=all").stdout == ""
    daily_clock.calls.clear()
    retry = daily_operation(repo)
    assert retry["status"] == "pass", retry
    assert retry["evidence"]["already_current"] is True
    git("commit", "--allow-empty", "-m", "progress")
    daily_clock.calls.clear()
    assert daily_operation(repo)["status"] == "human_decision_required"


@pytest.mark.parametrize("collision", ["local", "remote", "worktree"])
def test_daily_devlog_real_git_collisions_preserve_source(daily_real_repo, collision):
    repo, git, source, base = daily_real_repo
    # Collision setup needs the independent writer's object locally. The fresh
    # creation test above deliberately leaves it absent until the capability fetch.
    git("fetch", "--no-tags", "origin", "refs/heads/main:refs/remotes/origin/main")
    if collision == "remote":
        git("push", "origin", f"{base}:refs/heads/{DAILY_TARGET}")
    elif collision == "local":
        git("branch", DAILY_TARGET, base)
    else:
        git("worktree", "add", "-b", DAILY_TARGET, str(repo.parent / "other worktree"), base)
        git("worktree", "lock", "--reason", "fixture lock", str(repo.parent / "other worktree"))
    result = daily_operation(repo)
    assert result["status"] == "human_decision_required", result
    assert git("branch", "--show-current").stdout.strip() == "feature/source"
    assert git("rev-parse", "HEAD").stdout.strip() == source


@pytest.mark.parametrize("branch", ["refs/heads/", "refs/heads/feature/../bad", "refs/heads/feature/a.lock",
                                   "refs/heads/feature/a b", "refs/heads/feature/a@{b", "refs/heads/.hidden",
                                   "refs/heads/feature/a.", "refs/heads/feature/a//b"])
def test_daily_devlog_rejects_malformed_other_worktree_refs(monkeypatch, trusted_repo, daily_clock, branch):
    steps = daily_steps(trusted_repo)
    index = next(i for i, (args, _) in enumerate(steps) if args == DAILY_WORKTREES)
    steps[index] = (DAILY_WORKTREES, steps[index][1] + f"worktree /other\0HEAD {DAILY_BASE}\0branch {branch}\0\0")
    runner = install_daily_runner(monkeypatch, steps)
    assert daily_operation(trusted_repo)["status"] == "fail"
    assert DAILY_SWITCH not in runner.calls


@pytest.mark.parametrize("output", ["short\n", command_result(DAILY_LOCAL_SHA, returncode=128)])
def test_daily_devlog_local_sha_must_be_available_and_valid(monkeypatch, trusted_repo, daily_clock, output):
    steps = daily_steps(trusted_repo, current=True)
    index = next(i for i, (args, _) in enumerate(steps) if args == DAILY_LOCAL_SHA)
    steps[index] = (DAILY_LOCAL_SHA, output)
    runner = install_daily_runner(monkeypatch, steps)
    assert daily_operation(trusted_repo)["status"] == "fail"
    assert DAILY_SWITCH not in runner.calls


def test_daily_devlog_rejects_newline_inside_other_worktree_head(monkeypatch, trusted_repo, daily_clock):
    steps = daily_steps(trusted_repo)
    index = next(i for i, (args, _) in enumerate(steps) if args == DAILY_WORKTREES)
    steps[index] = (DAILY_WORKTREES, steps[index][1] + f"worktree /other\0HEAD {DAILY_BASE}\n\0detached\0\0")
    runner = install_daily_runner(monkeypatch, steps)
    assert daily_operation(trusted_repo)["status"] == "fail"
    assert DAILY_SWITCH not in runner.calls


@pytest.mark.parametrize("kind", ["bare", "detached", "suffix", "unrelated-locked"])
def test_daily_devlog_accepts_valid_unrelated_worktree_registrations(monkeypatch, trusted_repo, daily_clock, kind):
    records = {
        "bare": "worktree /origin.git\0bare\0\0",
        "detached": f"worktree /detached\0HEAD {DAILY_BASE}\0detached\0\0",
        "suffix": daily_worktree("/suffix", DAILY_TARGET + "-suffix", DAILY_BASE),
        "unrelated-locked": daily_worktree("/other\npath", "unrestricted/topic", DAILY_BASE, "locked reason\0"),
    }
    steps = daily_steps(trusted_repo)
    index = next(i for i, (args, _) in enumerate(steps) if args == DAILY_WORKTREES)
    steps[index] = (DAILY_WORKTREES, steps[index][1] + records[kind])
    runner = install_daily_runner(monkeypatch, steps)
    assert daily_operation(trusted_repo)["status"] == "pass"
    assert not runner.steps


@pytest.mark.parametrize("kind", ["missing-current", "duplicate-current", "wrong-current-branch", "wrong-current-head", "truncated"])
def test_daily_devlog_refuses_ambiguous_worktree_registration(monkeypatch, trusted_repo, daily_clock, kind):
    steps = daily_steps(trusted_repo)
    index = next(i for i, (args, _) in enumerate(steps) if args == DAILY_WORKTREES)
    current = steps[index][1]
    outputs = {"missing-current": daily_worktree("/different"), "duplicate-current": current * 2,
               "wrong-current-branch": daily_worktree(trusted_repo, "feature/other"),
               "wrong-current-head": daily_worktree(trusted_repo, sha=DAILY_BASE), "truncated": current[:-1]}
    steps[index] = (DAILY_WORKTREES, outputs[kind])
    runner = install_daily_runner(monkeypatch, steps)
    assert daily_operation(trusted_repo)["status"] == "fail"
    assert DAILY_SWITCH not in runner.calls


@pytest.mark.parametrize("command,output", [(DAILY_STATUS, "?? raced\n"), (DAILY_BRANCH, "feature/other\n"),
                                          (DAILY_HEAD, DAILY_SOURCE + "\n")])
def test_daily_devlog_noop_retry_rechecks_state(monkeypatch, trusted_repo, daily_clock, command, output):
    steps = daily_steps(trusted_repo, current=True)
    index = [i for i, (args, _) in enumerate(steps) if args == command][-1]
    steps[index] = (command, output)
    runner = install_daily_runner(monkeypatch, steps)
    assert daily_operation(trusted_repo)["status"] == "human_decision_required"
    assert DAILY_SWITCH not in runner.calls
