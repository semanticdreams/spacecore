from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_opencode_permissions.py"


def load_checker():
    assert CHECKER.exists(), "policy checker script should exist"
    spec = importlib.util.spec_from_file_location("check_opencode_permissions", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def agent(name: str, permission_text: str) -> str:
    return f"""---
description: Test {name} agent
mode: subagent
model: opencode-go/glm-5.3-flash
variant: high
permission:
{permission_text}
---

Test agent body.
"""


def skill(name: str) -> str:
    return f"""---
name: {name}
description: Use when testing {name}
---

# {name}
"""


def write_capability_files(root: Path) -> None:
    git_integrator_permissions = (
        '  edit: deny\n'
        '  task: deny\n'
        '  external_directory: deny\n'
        '  webfetch: deny\n'
        '  websearch: deny\n'
        '  question: deny\n'
        '  bash:\n'
        '    "python3 scripts/opencode_git_integrate.py status --repo-root .": allow\n'
        '    "python3 scripts/opencode_git_integrate.py fetch-origin --repo-root .": allow\n'
        '    "python3 scripts/opencode_git_integrate.py merge-origin-main --repo-root .": allow\n'
        '    "python3 scripts/opencode_git_integrate.py push-current --repo-root .": allow\n'
        '    "python3 scripts/opencode_git_integrate.py create-followup-branch --repo-root .": allow\n'
        '    "python3 scripts/opencode_git_integrate.py create-local-main-wrapup-branch --repo-root .": allow\n'
        '    "python3 scripts/opencode_git_integrate.py create-daily-devlog-branch --repo-root .": allow\n'
    )
    write_file(
        root / ".opencode" / "agents" / "git-integrator.md",
        agent("git-integrator", git_integrator_permissions),
    )
    write_file(
        root / ".opencode" / "agents" / "github-operator.md",
        agent(
            "github-operator",
            '  edit: deny\n  task: deny\n  external_directory: deny\n  webfetch: deny\n  websearch: deny\n  question: deny\n  bash:\n    "python3 scripts/opencode_pr_operator.py auth-status --repo-root .": allow\n    "python3 scripts/opencode_pr_operator.py check-main-protection --repo-root .": allow\n    "python3 scripts/opencode_pr_operator.py create-current --repo-root .": allow\n    "python3 scripts/opencode_pr_operator.py enable-auto-merge-current --repo-root .": allow\n    "python3 scripts/opencode_pr_operator.py view-current --repo-root .": allow\n    "python3 scripts/opencode_pr_operator.py poll-merge-queue-current --repo-root .": allow\n    "python3 scripts/opencode_pr_operator.py failed-actions-log-bundle-current --repo-root .": allow\n',
        ),
    )
    write_file(
        root / ".opencode" / "agents" / "config-auditor.md",
        agent(
            "config-auditor",
            '  edit: deny\n  task: deny\n  webfetch: deny\n  websearch: deny\n  question: deny\n  external_directory:\n    "~/.config/opencode/**": allow\n    "~/.config/opencode/**/*auth.json*": deny\n    "~/.config/opencode/**/*auth.jsonc*": deny\n    "~/.config/opencode/**/*secret*": deny\n    "~/.config/opencode/**/*token*": deny\n  bash:\n    "python3 scripts/verify_opencode_home_config.py --repo-root . --require-clean": allow\n',
        ),
    )
    write_file(
        root / ".opencode" / "agents" / "pr-recovery-operator.md",
        agent(
            "pr-recovery-operator",
            '  edit: deny\n  task: deny\n  external_directory: deny\n  webfetch: deny\n  websearch: deny\n  question: deny\n  bash:\n    "python3 scripts/opencode_pr_recovery.py create-current-with-followup-recovery --repo-root .": allow\n',
        ),
    )
    write_file(
        root / ".opencode" / "agents" / "windows-ci-reproducer.md",
        agent(
            "windows-ci-reproducer",
            '  edit: deny\n  task: deny\n  external_directory: deny\n  webfetch: deny\n  websearch: deny\n  question: deny\n  bash:\n    "python3 scripts/opencode_windows_ci_repro.py preflight --repo-root .": allow\n    "python3 scripts/opencode_windows_ci_repro.py setup-host --repo-root .": allow\n    "python3 scripts/opencode_windows_ci_repro.py bootstrap-vcpkg --repo-root .": allow\n    "python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .": allow\n',
        ),
    )
    for script in [
        "opencode_capabilities.py",
        "opencode_git_integrate.py",
        "opencode_pr_operator.py",
        "opencode_pr_recovery.py",
        "opencode_windows_ci_repro.py",
        "verify_opencode_home_config.py",
    ]:
        write_file(root / "scripts" / script, "#!/usr/bin/env python3\n")


def make_repo(tmp_path: Path, *, agent_name: str = "example-agent", permission_text: str = "  bash: deny\n") -> Path:
    root = tmp_path / "repo"
    write_file(root / ".opencode" / "opencode.json", json.dumps({"default_agent": "supervisor"}))
    write_capability_files(root)
    write_file(root / ".opencode/agents/expert-advisor.md", expert_agent())
    write_file(root / ".opencode" / "agents" / f"{agent_name}.md", agent(agent_name, permission_text))
    write_file(root / ".opencode" / "skills" / "example" / "SKILL.md", skill("example"))
    return root


def violation_codes(repo: Path) -> set[str]:
    checker = load_checker()
    return {violation.code for violation in checker.check_repo(repo)}


def permission_entries(repo: Path, agent_name: str, parent: str) -> dict[str, str]:
    checker = load_checker()
    path = repo / ".opencode" / "agents" / f"{agent_name}.md"
    _, raw = checker._frontmatter(path.read_text(encoding="utf-8"))
    assert raw is not None
    return dict(checker._mapping_entries(raw, parent))


def test_current_repo_policy_passes_after_task_3_changes():
    checker = load_checker()
    assert checker.check_repo(REPO_ROOT) == []


def test_git_integrator_allows_exact_guarded_git_wrapper_commands():
    bash_entries = permission_entries(REPO_ROOT, "git-integrator", "bash")

    allowed_entries = {pattern for pattern, action in bash_entries.items() if action == "allow"}
    assert allowed_entries == {
        "python3 scripts/opencode_git_integrate.py status --repo-root .",
        "python3 scripts/opencode_git_integrate.py fetch-origin --repo-root .",
        "python3 scripts/opencode_git_integrate.py merge-origin-main --repo-root .",
        "python3 scripts/opencode_git_integrate.py push-current --repo-root .",
        "python3 scripts/opencode_git_integrate.py create-followup-branch --repo-root .",
        "python3 scripts/opencode_git_integrate.py create-local-main-wrapup-branch --repo-root .",
        "python3 scripts/opencode_git_integrate.py create-daily-devlog-branch --repo-root .",
    }


def test_pr_recovery_operator_allows_only_exact_guarded_recovery_command():
    bash_entries = permission_entries(REPO_ROOT, "pr-recovery-operator", "bash")

    allowed_entries = {pattern for pattern, action in bash_entries.items() if action == "allow"}
    assert allowed_entries == {
        "python3 scripts/opencode_pr_recovery.py create-current-with-followup-recovery --repo-root ."
    }


def test_daily_devlog_exact_permission_is_required(tmp_path):
    repo = make_repo(tmp_path)
    path = repo / ".opencode/agents/git-integrator.md"
    text = path.read_text()
    exact = '    "python3 scripts/opencode_git_integrate.py create-daily-devlog-branch --repo-root .": allow\n'
    assert exact in text
    path.write_text(text.replace(exact, ""))
    issues = load_checker().check_repo(repo)
    assert any(issue.code == "capability-boundary" and "must allow guarded wrapper command exactly" in issue.message
               and "create-daily-devlog-branch" in issue.message for issue in issues)


@pytest.mark.parametrize("grant", [
    "python3 scripts/opencode_git_integrate.py *",
    "python3 scripts/opencode_git_integrate.py create-daily-devlog-branch *",
    "python3 scripts/opencode_git_integrate.py create-daily-devlog-branch --repo-root *",
    "python3 scripts/opencode_git_integrate.py create-daily-devlog-branch --repo-root . *",
    "python3 scripts/opencode_git_integrate.py create-daily-devlog-branch --repo-root . --date *",
    "python3 scripts/opencode_git_integrate.py create-daily-devlog-branch --repo-root . --branch * --base *",
    "git switch -c *", "git branch *", "*",
])
def test_daily_devlog_rejects_wildcard_freeform_suffix_and_raw_git_grants(tmp_path, grant):
    repo = make_repo(tmp_path)
    path = repo / ".opencode/agents/git-integrator.md"
    path.write_text(path.read_text().replace("  bash:\n", f'  bash:\n    "{grant}": allow\n', 1))
    issues = load_checker().check_repo(repo)
    assert any(issue.code == "capability-boundary" and grant in issue.message and "limited to approved" in issue.message for issue in issues)


def test_daily_devlog_agent_keeps_default_deny():
    assert permission_entries(REPO_ROOT, "git-integrator", "bash")["*"] == "deny"


def test_github_operator_allows_exact_guarded_wrapper_commands():
    bash_entries = permission_entries(REPO_ROOT, "github-operator", "bash")

    allowed_entries = {pattern for pattern, action in bash_entries.items() if action == "allow"}
    assert allowed_entries == {
        "python3 scripts/opencode_pr_operator.py auth-status --repo-root .",
        "python3 scripts/opencode_pr_operator.py check-main-protection --repo-root .",
        "python3 scripts/opencode_pr_operator.py create-current --repo-root .",
        "python3 scripts/opencode_pr_operator.py enable-auto-merge-current --repo-root .",
        "python3 scripts/opencode_pr_operator.py view-current --repo-root .",
        "python3 scripts/opencode_pr_operator.py poll-merge-queue-current --repo-root .",
        "python3 scripts/opencode_pr_operator.py failed-actions-log-bundle-current --repo-root .",
    }


def test_windows_ci_reproducer_allows_exact_guarded_wrapper_commands():
    bash_entries = permission_entries(REPO_ROOT, "windows-ci-reproducer", "bash")

    allowed_entries = {pattern for pattern, action in bash_entries.items() if action == "allow"}
    assert allowed_entries == {
        "python3 scripts/opencode_windows_ci_repro.py preflight --repo-root .",
        "python3 scripts/opencode_windows_ci_repro.py setup-host --repo-root .",
        "python3 scripts/opencode_windows_ci_repro.py bootstrap-vcpkg --repo-root .",
        "python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .",
    }


def test_windows_ci_reproducer_agent_is_required(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / ".opencode" / "agents" / "windows-ci-reproducer.md").unlink(missing_ok=True)

    checker = load_checker()
    issues = checker.check_repo(repo)

    assert any(
        violation.code == "capability-dependency"
        and ".opencode/agents/windows-ci-reproducer.md" in violation.message
        for violation in issues
    )


def test_windows_ci_reproducer_allows_only_wrapper_commands(tmp_path: Path):
    repo = make_repo(tmp_path)
    write_file(repo / "scripts" / "opencode_windows_ci_repro.py", "#!/usr/bin/env python3\n")
    windows_permissions = (
        '  edit: deny\n'
        '  task: deny\n'
        '  external_directory: deny\n'
        '  webfetch: deny\n'
        '  websearch: deny\n'
        '  question: deny\n'
        '  bash:\n'
        '    "python3 scripts/opencode_windows_ci_repro.py preflight --repo-root .": allow\n'
        '    "python3 scripts/opencode_windows_ci_repro.py setup-host --repo-root .": allow\n'
        '    "python3 scripts/opencode_windows_ci_repro.py bootstrap-vcpkg --repo-root .": allow\n'
        '    "python3 scripts/opencode_windows_ci_repro.py reproduce --repo-root .": allow\n'
        '    "gh *": allow\n'
    )
    write_file(
        repo / ".opencode" / "agents" / "windows-ci-reproducer.md",
        agent("windows-ci-reproducer", windows_permissions),
    )

    assert "capability-boundary" in violation_codes(repo)


def test_windows_ci_reproducer_requires_wrapper_script(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "scripts" / "opencode_windows_ci_repro.py").unlink(missing_ok=True)

    checker = load_checker()
    issues = checker.check_repo(repo)

    assert any(
        violation.code == "capability-dependency"
        and "scripts/opencode_windows_ci_repro.py" in violation.message
        for violation in issues
    )


@pytest.mark.parametrize(
    "extra_entry",
    [
        '    "git switch -c *": allow\n',
        '    "git push *": allow\n',
        '    "gh pr create *": allow\n',
        '    "python3 scripts/opencode_pr_recovery.py *": allow\n',
        '    "python3 scripts/opencode_pr_recovery.py create-current-with-followup-recovery --repo-root *": allow\n',
    ],
)
def test_pr_recovery_operator_rejects_extra_bash_allow(tmp_path: Path, extra_entry: str):
    repo = make_repo(tmp_path)
    write_file(repo / "scripts" / "opencode_pr_recovery.py", "#!/usr/bin/env python3\n")
    recovery_permissions = (
        '  edit: deny\n'
        '  task: deny\n'
        '  external_directory: deny\n'
        '  webfetch: deny\n'
        '  websearch: deny\n'
        '  question: deny\n'
        '  bash:\n'
        '    "python3 scripts/opencode_pr_recovery.py create-current-with-followup-recovery --repo-root .": allow\n'
        + extra_entry
    )
    write_file(
        repo / ".opencode" / "agents" / "pr-recovery-operator.md",
        agent("pr-recovery-operator", recovery_permissions),
    )

    assert "capability-boundary" in violation_codes(repo)


def test_stale_merged_pr_recovery_routes_through_recovery_operator():
    required_terms = [
        "pr-recovery-operator",
        "create-current-with-followup-recovery",
        "stale merged PR",
    ]
    documented_paths = [
        REPO_ROOT / ".opencode" / "skills" / "finishing-a-development-branch" / "SKILL.md",
        REPO_ROOT / ".opencode" / "agents" / "supervisor.md",
        REPO_ROOT / "docs" / "dev" / "features" / "opencode-agent-workflow.md",
    ]

    for path in documented_paths:
        text = path.read_text(encoding="utf-8")
        missing_terms = [term for term in required_terms if term not in text]
        assert missing_terms == [], f"{path.relative_to(REPO_ROOT)} missing {missing_terms}"


def test_legacy_strict_local_main_recovery_remains_documented():
    required = {
        REPO_ROOT / ".opencode" / "agents" / "supervisor.md": [
            "create-local-main-wrapup-branch",
            "fast-dev/local-main-",
            "local `main`",
            "git-integrator",
        ],
        REPO_ROOT / ".opencode" / "skills" / "finishing-a-development-branch" / "SKILL.md": [
            "create-local-main-wrapup-branch",
            "fast-dev/local-main-",
            "local `main`",
            "Do not push",
        ],
        REPO_ROOT / "docs" / "dev" / "features" / "opencode-agent-workflow.md": [
            "Legacy strict-flow local-main recovery",
            "create-local-main-wrapup-branch",
            "fast-dev/local-main-<short-head-sha>",
        ],
    }

    for path, terms in required.items():
        text = path.read_text(encoding="utf-8")
        missing = [term for term in terms if term not in text]
        assert missing == [], f"{path.relative_to(REPO_ROOT)} missing {missing}"


def test_strict_workflow_does_not_recommend_raw_github_polling_commands():
    forbidden_commands = [
        "gh pr view",
        "gh run list",
        "gh run watch",
    ]
    documented_paths = [
        REPO_ROOT / ".opencode" / "skills" / "finishing-a-development-branch" / "SKILL.md",
        REPO_ROOT / ".opencode" / "agents" / "supervisor.md",
    ]

    for path in documented_paths:
        text = path.read_text(encoding="utf-8")
        if text.startswith("---\n"):
            text = text.split("---\n", 2)[2]
        present_commands = [command for command in forbidden_commands if command in text]
        assert present_commands == [], f"{path.relative_to(REPO_ROOT)} recommends {present_commands}"


def scalar_agent(name: str, mode: str, action: str) -> str:
    return agent(name, "  bash: deny\n").replace(
        "mode: subagent", f"mode: {mode}"
    ).replace("permission:\n  bash: deny", f"permission: {action}")


@pytest.mark.parametrize("name", ["fast-dev", "live-dev"])
def test_direct_primary_accepts_scalar_allow(tmp_path: Path, name: str):
    repo = make_repo(tmp_path)
    write_file(repo / f".opencode/agents/{name}.md", scalar_agent(name, "primary", "allow"))
    assert load_checker().check_repo(repo) == []


@pytest.mark.parametrize(
    "name,mode,action",
    [
        ("example-agent", "primary", "allow"),
        ("fast-dev-copy", "primary", "allow"),
        ("fast-dev", "subagent", "allow"),
        ("fast-dev", "all", "allow"),
        ("fast-dev", "primary", "ask"),
        ("fast-dev", "primary", "deny"),
        ("live-dev-copy", "primary", "allow"),
        ("live-dev", "subagent", "allow"),
        ("live-dev", "all", "allow"),
        ("live-dev", "primary", "ask"),
        ("live-dev", "primary", "deny"),
        ("example-agent", "subagent", "ask"),
    ],
)
def test_direct_scalar_grant_is_exact_name_mode_and_action_only(tmp_path: Path, name: str, mode: str, action: str):
    repo = make_repo(tmp_path)
    write_file(repo / f".opencode/agents/{name}.md", scalar_agent(name, mode, action))
    assert "permission-profile" in violation_codes(repo)


@pytest.mark.parametrize("name", ["fast-dev", "live-dev"])
def test_direct_primary_requires_broad_scalar_profile(tmp_path: Path, name: str):
    repo = make_repo(tmp_path, agent_name=name)
    assert "permission-profile" in violation_codes(repo)


FAST_DEV_REVIEWER_PERMISSIONS = (
    "  read: allow\n  glob: allow\n  grep: allow\n  list: allow\n  lsp: allow\n"
    "  edit: deny\n  task: deny\n  external_directory: deny\n"
    "  webfetch: deny\n  websearch: deny\n  question: deny\n  bash: allow\n"
)


def test_fast_dev_reviewer_observational_profile_passes(tmp_path: Path):
    repo = make_repo(tmp_path, agent_name="fast-dev-reviewer", permission_text=FAST_DEV_REVIEWER_PERMISSIONS)
    assert load_checker().check_repo(repo) == []


@pytest.mark.parametrize("key", ["edit", "task", "external_directory", "webfetch", "websearch", "question"])
def test_fast_dev_reviewer_rejects_operational_grants(tmp_path: Path, key: str):
    permissions = FAST_DEV_REVIEWER_PERMISSIONS.replace(f"  {key}: deny", f"  {key}: allow")
    repo = make_repo(tmp_path, agent_name="fast-dev-reviewer", permission_text=permissions)
    assert "role-boundary" in violation_codes(repo)


@pytest.mark.parametrize("key", ["read", "glob", "grep", "list", "lsp", "bash"])
def test_fast_dev_reviewer_requires_inspection_access(tmp_path: Path, key: str):
    permissions = FAST_DEV_REVIEWER_PERMISSIONS.replace(f"  {key}: allow", f"  {key}: deny")
    repo = make_repo(tmp_path, agent_name="fast-dev-reviewer", permission_text=permissions)
    assert "role-boundary" in violation_codes(repo)


def test_fast_dev_reviewer_requires_subagent_mode(tmp_path: Path):
    repo = make_repo(tmp_path)
    text = agent("fast-dev-reviewer", FAST_DEV_REVIEWER_PERMISSIONS).replace("mode: subagent", "mode: primary")
    write_file(repo / ".opencode/agents/fast-dev-reviewer.md", text)
    assert "role-boundary" in violation_codes(repo)


def flat(text: str) -> str:
    """Whitespace-normalized text so wrapped contract phrases stay assertable."""
    return " ".join(text.split())


def test_fast_dev_primary_contract_is_direct_branch_scoped_and_local_only():
    text = (REPO_ROOT / ".opencode/agents/fast-dev.md").read_text(encoding="utf-8")
    keys, _ = load_checker()._frontmatter(text)
    assert keys["permission"] == "allow"
    assert keys["mode"] == "primary"
    for term in ["long-term `fast-dev` branch", "origin/main", "before edits", "unmerged", "dirty", "local only", "explicit", "fast-dev-wrap-up", "space-fennel", "space-graph-doctrine"]:
        assert term in flat(text)
    for term in ["supervisor", "micro-design", "dispatch `implementer`", "capability agents", "vertical slice handoff"]:
        assert term not in text.lower()


def test_fast_dev_reviewer_contract_covers_all_commits_without_operations():
    text = (REPO_ROOT / ".opencode/agents/fast-dev-reviewer.md").read_text(encoding="utf-8")
    for term in ["base/head SHAs", "every accumulated commit", "final diff", "file/line", "coverage gaps", "Do not run tests", "GitHub", "process artifacts"]:
        assert term in text
    assert "supervisor" not in text.lower()


def test_fast_dev_wrap_up_contract_requires_review_direct_fixes_and_fetched_main_proof():
    text = (REPO_ROOT / ".opencode/skills/fast-dev-wrap-up/SKILL.md").read_text(encoding="utf-8")
    for term in [
        "explicit", "commit request", "git fetch origin", "git merge origin/main",
        "git log origin/main..HEAD", "git diff origin/main...HEAD", "base/head SHAs",
        "fast-dev-reviewer", "one independent review", "Fix findings", "self-review",
        "no mandatory independent re-review", "gh pr create", "gh pr merge", "--auto",
        "gh pr view", "gh run list", "gh run watch", "100", "mergedAt", "mergeCommit",
        "git merge-base --is-ancestor <merge-sha> origin/main", "merge queue", "required `test`",
        "space-testing-runtime", "unresolved material", "required validation failures",
    ]:
        assert term in flat(text)
    assert "supervisor" not in text.lower()


def test_fast_dev_agents_exception_retains_technical_guidance_and_overrides_imported_process():
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    exception = text.split("## Fast-dev workflow exception", 1)[1].split("## Branch Convention", 1)[0]
    for term in ["selected `fast-dev` primary", "imported by domain skills", "planning", "review", "commit", "explicit", "technical", "evidence", "unresolved material", "required validation failures"]:
        assert term in exception


def live_dev_prompt() -> str:
    path = REPO_ROOT / ".opencode/agents/live-dev.md"
    assert path.exists(), "the user-selected live-dev primary must exist"
    return path.read_text(encoding="utf-8")


def test_live_dev_primary_is_exact_direct_local_only_profile():
    text = live_dev_prompt()
    keys, _ = load_checker()._frontmatter(text)
    assert {key: keys[key] for key in ("mode", "model", "steps", "permission")} == {
        "mode": "primary", "model": "opencode-go/glm-5.3-flash",
        "steps": "180", "permission": "allow",
    }
    assert keys["variant"] == "high"
    for term in [
        "long-term `live-dev` branch", "before edits", "freshly fetched `origin/main`", "unmerged",
        "dirty", "local only", "task completion", "commit request", "PR creation",
        "explicit user wrap-up/integration", "fast-dev-wrap-up", "space-fennel",
        "space-fennel-ui", "space-graph-doctrine", "space-testing-runtime",
        "quit and restart OpenCode",
    ]:
        assert term in flat(text)


def test_live_dev_loop_establishes_manual_mode_before_edits_and_validates_before_refresh():
    text = live_dev_prompt()
    for term in [
        "discover --repo-root .", "start --repo-root .", "normal user data/settings",
        "more than one", "ask the user to select", "select --repo-root . --instance <instance-id>",
        "manual --repo-root .", "confirm `mode: manual` before editing",
        "no filesystem watching", "no hooks", "Validate before refresh",
        "reload --repo-root .", "broad app-root", "restart --repo-root . --rebuild",
        "preserved", "restart --repo-root .", "macros.fnl", "Never request confirmation",
        "transient state loss", "status --repo-root . --request-id <request-id>",
        "terminal", "health", "acceptance alone is not success", "nonzero",
        "both the failed reload and recovery", "Diagnose", "fix directly",
    ]:
        assert term in text
    assert text.index("manual --repo-root .") < text.index("Validate before refresh") < text.index("reload --repo-root .")


def test_live_dev_scoped_exception_preserves_default_and_other_agent_contracts():
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    exception = text.split("## Fast-dev workflow exception", 1)[1].split("## Branch Convention", 1)[0]
    for term in [
        "selected `fast-dev` primary", "selected `live-dev` primary", "`live-dev` branch",
        "exact identities", "default `supervisor`", "local only", "explicit user wrap-up",
        "imported by domain skills", "technical", "no filesystem watching",
        "all other agents", "already-running agent",
    ]:
        assert term in flat(exception)
    config = json.loads((REPO_ROOT / ".opencode/opencode.json").read_text(encoding="utf-8"))
    assert config["default_agent"] == "supervisor"


def test_shared_wrap_up_matches_selected_caller_to_its_own_branch_only():
    text = (REPO_ROOT / ".opencode/skills/fast-dev-wrap-up/SKILL.md").read_text(encoding="utf-8")
    keys, _ = load_checker()._frontmatter(text)
    assert keys["description"] == (
        "Use ONLY when the selected fast-dev or live-dev primary receives explicit user wrap-up/integration authorization."
    )
    for term in [
        "| `fast-dev` | `fast-dev` (long-term branch, exactly this name) |",
        "| `live-dev` | `live-dev` (long-term branch, exactly this name) |",
        "selected caller", "mismatch", "Do not switch primaries", "not interchangeable",
        "ordinary task completion", "commit request", "do not authorize publishing",
    ]:
        assert term in flat(text)
    assert not (REPO_ROOT / ".opencode/skills/live-dev-wrap-up").exists()
    reviewer = (REPO_ROOT / ".opencode/agents/fast-dev-reviewer.md").read_text(encoding="utf-8")
    assert "fast-dev and live-dev" in reviewer


@pytest.mark.parametrize("path", ["docs/dev/features/opencode-agent-workflow.md", "docs/dev/features/live-dev.md"])
def test_live_dev_documented_local_loop_and_shared_explicit_wrap_up(path: str):
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    for term in [
        "long-term `live-dev` branch", "local only", "fast-dev-wrap-up", "fast-dev-reviewer",
        "manual", "before editing", "validated", "more than one", "select",
        "no filesystem watching", "confirmation", "failed reload", "recovery",
        "Restart OpenCode", "origin/main",
    ]:
        assert term in flat(text)


def test_finishing_skill_does_not_recommend_branch_deletion():
    path = REPO_ROOT / ".opencode" / "skills" / "finishing-a-development-branch" / "SKILL.md"
    text = path.read_text(encoding="utf-8")

    assert "git branch -d" not in text
    assert "Cleanup Branch" not in text
    assert "| 1. Merge locally | yes | — | — | yes |" not in text


def test_git_integrator_rejects_extra_bash_allow(tmp_path: Path):
    repo = make_repo(tmp_path)
    agent_path = repo / ".opencode" / "agents" / "git-integrator.md"
    agent_text = agent_path.read_text(encoding="utf-8")
    agent_path.write_text(
        agent_text.replace(
            '    "python3 scripts/opencode_git_integrate.py create-followup-branch --repo-root .": allow\n',
            '    "python3 scripts/opencode_git_integrate.py create-followup-branch --repo-root .": allow\n    "python3 scripts/opencode_git_integrate.py create-local-main-wrapup-branch --repo-root .": allow\n    "git switch -c *": allow\n',
        ),
        encoding="utf-8",
    )

    assert "capability-boundary" in violation_codes(repo)


@pytest.mark.parametrize(
    "extra_entry",
    [
        '    "git switch -c *": "allow"\n',
        '    "git switch -c *": allow # broad raw git permission\n',
        '    "git switch -c *": "allow" # broad raw git permission\n',
        "    'git switch -c *': 'ask' # broad raw git permission\n",
    ],
)
def test_git_integrator_rejects_extra_bash_allow_or_ask_with_quotes_or_comments(tmp_path: Path, extra_entry: str):
    repo = make_repo(tmp_path)
    agent_path = repo / ".opencode" / "agents" / "git-integrator.md"
    agent_text = agent_path.read_text(encoding="utf-8")
    agent_path.write_text(
        agent_text.replace(
            '    "python3 scripts/opencode_git_integrate.py create-followup-branch --repo-root .": allow\n',
            '    "python3 scripts/opencode_git_integrate.py create-followup-branch --repo-root .": allow\n    "python3 scripts/opencode_git_integrate.py create-local-main-wrapup-branch --repo-root .": allow\n' + extra_entry,
        ),
        encoding="utf-8",
    )

    assert "capability-boundary" in violation_codes(repo)


def test_check_repo_fails_when_permission_frontmatter_contains_ask(tmp_path: Path):
    repo = make_repo(tmp_path, permission_text='  bash:\n    "*": ask\n')

    checker = load_checker()
    issues = checker.check_repo(repo)

    assert any(
        violation.code == "no-ask-permission"
        and '.opencode/agents/example-agent.md' in violation.message
        and 'bash "*": ask' in violation.message
        for violation in issues
    )


def test_supervisor_allows_routine_bash_by_default_and_denies_capability_commands():
    bash_entries = permission_entries(REPO_ROOT, "supervisor", "bash")

    assert bash_entries["*"] == "allow"
    assert bash_entries["git push*"] == "deny"
    assert bash_entries["git fetch*"] == "deny"
    assert bash_entries["git pull*"] == "deny"
    assert bash_entries["git merge*"] == "deny"
    assert bash_entries["git -C * fetch*"] == "deny"
    assert bash_entries["git -C * pull*"] == "deny"
    assert bash_entries["git -C * merge*"] == "deny"
    assert bash_entries["git -C * push*"] == "deny"
    assert bash_entries["gh *"] == "deny"


def test_supervisor_denies_destructive_branch_bash_operations():
    bash_entries = permission_entries(REPO_ROOT, "supervisor", "bash")

    for pattern in [
        "git branch -d*",
        "git branch -D*",
        "git branch --delete*",
        "git switch -C*",
        "git checkout -B*",
        "git -C * branch -d*",
        "git -C * branch -D*",
        "git -C * branch --delete*",
        "git -C * switch -C*",
        "git -C * checkout -B*",
    ]:
        assert bash_entries[pattern] == "deny"


def test_supervisor_denies_secret_env_reads_and_broad_external_directories():
    read_entries = permission_entries(REPO_ROOT, "supervisor", "read")
    external_entries = permission_entries(REPO_ROOT, "supervisor", "external_directory")

    assert read_entries["*.env"] == "deny"
    assert read_entries["*.env.*"] == "deny"
    assert read_entries["*.env.example"] == "allow"
    assert external_entries["*"] == "deny"


@pytest.mark.parametrize(
    "permission_text",
    [
        "  bash: ask # trailing comment\n",
        "  bash: 'ask'\n",
        "  bash: \"ask\" # trailing comment\n",
        "  bash:\n    \"*\": ask # trailing comment\n",
        "  bash:\n    \"*\": 'ask'\n",
        "  bash:\n    \"*\": \"ask\" # trailing comment\n",
    ],
)
def test_check_repo_fails_when_permission_frontmatter_contains_ask_variants(tmp_path: Path, permission_text: str):
    repo = make_repo(tmp_path, permission_text=permission_text)

    assert "no-ask-permission" in violation_codes(repo)


def test_cli_emits_pass_or_fail_json(tmp_path: Path):
    repo = make_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--repo-root", str(repo)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload == {"status": "pass", "violations": []}
    assert result.stderr == ""


def test_check_repo_fails_when_required_capability_agent_missing(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / ".opencode" / "agents" / "git-integrator.md").unlink()

    checker = load_checker()
    issues = checker.check_repo(repo)

    assert any(
        violation.code == "capability-dependency"
        and ".opencode/agents/git-integrator.md" in violation.message
        for violation in issues
    )


def test_check_repo_fails_when_required_wrapper_missing(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "scripts" / "opencode_git_integrate.py").unlink()

    checker = load_checker()
    issues = checker.check_repo(repo)

    assert any(
        violation.code == "capability-dependency"
        and "scripts/opencode_git_integrate.py" in violation.message
        for violation in issues
    )


def test_check_repo_fails_when_agent_allowlist_references_missing_wrapper(tmp_path: Path):
    repo = make_repo(tmp_path)
    agent_path = repo / ".opencode" / "agents" / "git-integrator.md"
    agent_text = agent_path.read_text(encoding="utf-8")
    agent_path.write_text(
        agent_text.replace(
            '    "python3 scripts/opencode_git_integrate.py status --repo-root .": allow\n',
            '    "python3 scripts/opencode_git_integrate.py status --repo-root .": allow\n    "python3 scripts/missing_wrapper.py status --repo-root .": allow\n',
        ),
        encoding="utf-8",
    )

    checker = load_checker()
    issues = checker.check_repo(repo)

    assert any(
        violation.code == "capability-dependency"
        and "missing wrapper script" in violation.message
        and "scripts/missing_wrapper.py" in violation.message
        for violation in issues
    )


def test_reviewer_with_bash_allow_fails(tmp_path: Path):
    repo = make_repo(tmp_path, agent_name="reviewer", permission_text="  bash: allow\n")
    assert "role-boundary" in violation_codes(repo)


def test_implementer_with_git_push_allow_fails(tmp_path: Path):
    repo = make_repo(tmp_path, agent_name="implementer", permission_text="  bash:\n    \"git push*\": allow\n")
    assert "role-boundary" in violation_codes(repo)


def test_web_researcher_with_local_read_fails(tmp_path: Path):
    repo = make_repo(tmp_path, agent_name="web-researcher", permission_text="  read:\n    \"*\": allow\n")
    assert "role-boundary" in violation_codes(repo)


def test_capability_agent_with_edit_allow_fails(tmp_path: Path):
    repo = make_repo(tmp_path, agent_name="git-integrator", permission_text="  edit: allow\n  bash: deny\n")
    assert "capability-boundary" in violation_codes(repo)


@pytest.mark.parametrize(
    "permission_text",
    [
        '  bash:\n    "git push origin main": allow\n',
        '  bash:\n    "git -C * push origin main": allow\n',
        '  bash:\n    "git push origin HEAD:refs/heads/main": allow\n',
        '  bash:\n    "git push origin HEAD:main": allow\n',
        '  bash:\n    "git push origin refs/heads/main": allow\n',
        '  bash:\n    "git -C * push origin HEAD:refs/heads/main": ask\n',
        '  bash:\n    "git -C * push origin HEAD:main": ask\n',
        '  bash:\n    "git -C * push origin refs/heads/main": ask\n',
        "  bash:\n    'git push origin main': ask\n",
        '  bash:\n    "git push *--force*": allow\n',
        '  bash:\n    "git -C * push *--force*": allow\n',
        "  bash:\n    'git push -f *': ask\n",
        '  bash:\n    "git commit --amend*": allow\n',
        '  bash:\n    "git -C * commit --amend*": allow\n',
        '  bash:\n    "git rebase*": allow\n',
        '  bash:\n    "git -C * rebase*": allow\n',
        "  bash:\n    'git rebase*': ask\n",
        "  bash:\n    'git -C * rebase*': ask\n",
        '  bash:\n    "git reset*": allow\n',
        '  bash:\n    "git -C * reset*": allow\n',
        "  bash:\n    'git reset*': ask\n",
        "  bash:\n    'git -C * reset*': ask\n",
        '  bash:\n    "git clean*": allow\n',
        '  bash:\n    "git -C * clean*": allow\n',
        "  bash:\n    'git clean*': ask\n",
        '  bash:\n    "git push origin --delete *": allow\n',
        '  bash:\n    "rm -rf*": allow\n',
        "  bash:\n    'rm -r*': ask\n",
        '  bash:\n    "find * -delete*": allow\n',
        '  bash:\n    "sudo *": allow\n',
        "  bash:\n    'sudo *': ask\n",
        '  bash:\n    "su *": allow\n',
        '  bash:\n    "doas *": ask\n',
        '  bash:\n    "apt *": allow\n',
        "  bash:\n    'apt-get *': ask\n",
        '  bash:\n    "dnf *": allow\n',
        '  bash:\n    "pacman *": ask\n',
        '  bash:\n    "brew *": allow\n',
        '  bash:\n    "gh *": ask\n',
        "  bash:\n    'gh *': allow\n",
        '  external_directory:\n    "*": allow\n',
        "  external_directory:\n    '~/**': ask\n",
        '  external_directory:\n    "/**": allow\n',
        '  external_directory:\n    "/home/**": ask\n',
    ],
)
def test_each_unsafe_permission_pattern_fails_independently(tmp_path: Path, permission_text: str):
    repo = make_repo(tmp_path, agent_name="supervisor", permission_text=permission_text)
    codes = violation_codes(repo)
    assert "unsafe-permission" in codes


def test_opencode_json_must_parse_and_keep_supervisor_default(tmp_path: Path):
    repo = make_repo(tmp_path)
    write_file(repo / ".opencode" / "opencode.json", '{"default_agent":"implementer"}')
    assert "opencode-json" in violation_codes(repo)


def test_agent_and_skill_frontmatter_required(tmp_path: Path):
    repo = make_repo(tmp_path)
    write_file(repo / ".opencode" / "agents" / "broken.md", "---\ndescription: Broken\n---\n")
    write_file(repo / ".opencode" / "skills" / "broken" / "SKILL.md", "---\nname: broken\n---\n")
    codes = violation_codes(repo)
    assert "agent-frontmatter" in codes
    assert "skill-frontmatter" in codes


@pytest.mark.parametrize(
    "permission_text",
    [
        '  edit: deny\n  task: deny\n  external_directory: deny\n  webfetch: deny\n  websearch: deny\n  question: deny\n  bash:\n    "python3 scripts/opencode_pr_operator.py create --repo-root . --head *": allow\n',
        '  edit: deny\n  task: deny\n  external_directory: deny\n  webfetch: deny\n  websearch: deny\n  question: deny\n  bash:\n    "python3 scripts/opencode_pr_operator.py enable-auto-merge --repo-root . --branch *": allow\n',
        '  edit: deny\n  task: deny\n  external_directory: deny\n  webfetch: deny\n  websearch: deny\n  question: deny\n  bash:\n    "python3 scripts/opencode_pr_operator.py poll-merge-queue --repo-root . --branch * --timeout-seconds * --interval-seconds *": allow\n',
    ],
)
def test_github_operator_rejects_wrapper_bash_permissions_with_untrusted_suffix_wildcards(
    tmp_path: Path, permission_text: str
):
    repo = make_repo(tmp_path, agent_name="github-operator", permission_text=permission_text)

    codes = violation_codes(repo)

    assert "capability-boundary" in codes


def test_github_operator_rejects_actions_log_wildcard_permission(tmp_path: Path):
    repo = make_repo(tmp_path)
    github_permissions = (
        '  edit: deny\n'
        '  task: deny\n'
        '  external_directory: deny\n'
        '  webfetch: deny\n'
        '  websearch: deny\n'
        '  question: deny\n'
        '  bash:\n'
        '    "python3 scripts/opencode_pr_operator.py auth-status --repo-root .": allow\n'
        '    "python3 scripts/opencode_pr_operator.py check-main-protection --repo-root .": allow\n'
        '    "python3 scripts/opencode_pr_operator.py create-current --repo-root .": allow\n'
        '    "python3 scripts/opencode_pr_operator.py enable-auto-merge-current --repo-root .": allow\n'
        '    "python3 scripts/opencode_pr_operator.py view-current --repo-root .": allow\n'
        '    "python3 scripts/opencode_pr_operator.py poll-merge-queue-current --repo-root .": allow\n'
        '    "python3 scripts/opencode_pr_operator.py failed-actions-log-bundle-current --repo-root .": allow\n'
        '    "python3 scripts/opencode_pr_operator.py actions-log --repo-root . --run-id * --job-id * --full": allow\n'
    )
    write_file(
        repo / ".opencode" / "agents" / "github-operator.md",
        agent("github-operator", github_permissions),
    )

    assert "capability-boundary" in violation_codes(repo)


ORDINARY_ROLES = (
    "adjudicator", "config-auditor", "debug-advisor", "explorer", "fast-dev-reviewer",
    "fast-dev", "git-integrator", "github-operator", "implementer", "live-dev",
    "planner", "pr-recovery-operator", "reviewer", "supervisor", "web-researcher",
    "windows-ci-reproducer",
)
EXPERT_PERMISSIONS = '''  "*": deny
  read:
    "*": allow
    "*.env": deny
    "*.env.*": deny
    "*.env.example": allow
    "*auth*": deny
    "*secret*": deny
    "*token*": deny
    "*credential*": deny
    "*keyring*": deny
  glob: allow
  grep: allow
  list: allow
  lsp: allow
  edit: deny
  bash: deny
  task: deny
  external_directory: deny
  webfetch: deny
  websearch: deny
  question: deny
'''


def expert_agent():
    return agent("expert-advisor", EXPERT_PERMISSIONS).replace(
        "model: opencode-go/glm-5.3-flash", "model: openai/gpt-6.1-sol"
    )


@pytest.mark.parametrize("name", ORDINARY_ROLES)
def test_ordinary_model(name):
    keys, _ = load_checker()._frontmatter((REPO_ROOT / f".opencode/agents/{name}.md").read_text())
    assert keys["model"] == "opencode-go/glm-5.3-flash"
    assert keys["variant"] == "high"


@pytest.mark.parametrize("name", [*ORDINARY_ROLES, "future-worker"])
@pytest.mark.parametrize("drift", ["model", "missing", "low", "max"])
def test_checker_rejects_ordinary_and_future_role_model_drift(tmp_path, name, drift):
    repo = make_repo(tmp_path)
    text = agent(name, "  bash: deny\n").replace("openai/gpt-6.1-sol", "opencode-go/glm-5.3-flash")
    if name in {"fast-dev", "live-dev"}:
        text = text.replace("mode: subagent", "mode: primary").replace("permission:\n  bash: deny", "permission: allow")
    if drift == "model":
        text = text.replace("opencode-go/glm-5.3-flash", "openai/gpt-6.1-sol")
    else:
        text = text.replace("variant: high\n", "" if drift == "missing" else f"variant: {drift}\n")
    write_file(repo / f".opencode/agents/{name}.md", text)
    assert "agent-model" in violation_codes(repo)


def test_expert_is_required(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".opencode/agents/expert-advisor.md").unlink(missing_ok=True)
    assert "expert-profile" in violation_codes(repo)


def test_expert_exact_safe_profile_passes(tmp_path):
    repo = make_repo(tmp_path)
    write_file(repo / ".opencode/agents/expert-advisor.md", expert_agent())
    assert load_checker().check_repo(repo) == []


def test_checked_in_expert_profile_passes():
    checker = load_checker()
    path = REPO_ROOT / ".opencode/agents/expert-advisor.md"
    keys, raw = checker._frontmatter(path.read_text())
    assert checker._check_expert_profile(path, REPO_ROOT, keys, raw) == []


def test_expert_rejects_default_deny_moved_after_inspection_grants(tmp_path):
    repo = make_repo(tmp_path)
    text = (REPO_ROOT / ".opencode/agents/expert-advisor.md").read_text()
    default_deny = '  "*": deny\n'
    assert text.count(default_deny) == 1
    # Preserve every key/action but move the broad last-matching rule to the tail.
    reordered = text.replace(default_deny, "", 1).replace("\n---\n", "\n" + default_deny + "---\n", 1)
    write_file(repo / ".opencode/agents/expert-advisor.md", reordered)
    assert "expert-profile" in violation_codes(repo)


@pytest.mark.parametrize("old,new", [
    ("model: openai/gpt-6.1-sol", "model: opencode-go/glm-5.3-flash"),
    ("variant: high", "variant: medium"), ("variant: high\n", ""),
    ("mode: subagent", "mode: primary"),
    *[(f"  {key}: deny", f"  {key}: allow") for key in
      ("edit", "bash", "task", "external_directory", "webfetch", "websearch", "question")],
    *[(f"  {key}: allow", f"  {key}: deny") for key in ("glob", "grep", "list", "lsp")],
    ('    "*.env": deny\n', ""), ('    "*auth*": deny\n', ""),
    ('    "*": allow', '    "*": deny'),
    ('  "*": deny', '  "*": allow'),
    ("  bash: deny", '  bash:\n    "*": deny\n    "git status*": allow'),
    ('    "*auth*": deny', '    "*auth*": deny\n    "*": allow'),
    ("  task: deny", '  task: deny\n  skill: allow'),
])
def test_expert_rejects_pin_access_and_operational_drift(tmp_path, old, new):
    repo = make_repo(tmp_path)
    text = expert_agent()
    assert old in text
    write_file(repo / ".opencode/agents/expert-advisor.md", text.replace(old, new))
    assert "expert-profile" in violation_codes(repo)


@pytest.mark.parametrize("name", ORDINARY_ROLES)
def test_existing_permission_mode_and_budget_bytes_preserved(name):
    # Frozen from task BASE dafba78e; no old Git objects needed in shallow CI.
    permission_sha256 = {
        "adjudicator": "c3495c0e68af55c922a3002cb9cecb277c6b580993cf409c70d516bea09328d4",
        "config-auditor": "0edcb176fe5954aa31aaa3c7b44395e97d0b50b92cef510bbf2d54260d200ac2",
        "debug-advisor": "c3495c0e68af55c922a3002cb9cecb277c6b580993cf409c70d516bea09328d4",
        "explorer": "d853f26c3465ccdce97c941fbd7f889bac43c3367153241671fbb2012c84eef4",
        "fast-dev-reviewer": "653215903d7664cbb233b88feea1931108b30c978dc2ba1530b3b465857035b5",
        "fast-dev": "874c3ddefbae0b53cf9360a397ec991333c0a5310fcd57f96204e5548861b2c4",
        "git-integrator": "4df9acae621192f2e4a8ab3b9a9980ae7d7a244db6810105d25e1f2d3b8ab01d",
        "github-operator": "5f9803d89382041f90b43be6dc76c700a3913434a9f4604409cb2978a08e149e",
        "implementer": "db407b6a8b61434d684bd8c1ea900895f6b12945bab4b75873aa39fd36970b55",
        "live-dev": "874c3ddefbae0b53cf9360a397ec991333c0a5310fcd57f96204e5548861b2c4",
        "planner": "c3495c0e68af55c922a3002cb9cecb277c6b580993cf409c70d516bea09328d4",
        "pr-recovery-operator": "2a8ab717b46a6be8c268a3f681206500eb0b2070152d9878242f2fd4da9c5942",
        "reviewer": "c3495c0e68af55c922a3002cb9cecb277c6b580993cf409c70d516bea09328d4",
        "supervisor": "13be0d4073768da038b1dbafd7baa30d518dba5206c3e4d40e2502de00324ed7",
        "web-researcher": "55842260df665dff1b772553dfc53ad8345bfcc90a0f5296d62438af4e0f573b",
        "windows-ci-reproducer": "1d3632121914c29bc8267b6ef47978fb26705669292f4ee9ba5f9a624d14a8dd",
    }
    steps = dict(zip(ORDINARY_ROLES, (40, 15, 35, 20, 55, 180, 18, 25, 100, 180, 35, 15, 55, 500, 35, 20)))
    path = f".opencode/agents/{name}.md"
    current = (REPO_ROOT / path).read_text()
    keys, raw = load_checker()._frontmatter(current)
    assert hashlib.sha256(raw.split("permission:", 1)[1].encode()).hexdigest() == permission_sha256[name]
    mode = "primary" if name in {"supervisor", "fast-dev", "live-dev"} else "subagent"
    assert (keys["mode"], keys["steps"]) == (mode, str(steps[name]))


REQUEST_FIELDS = {"decision_scope", "trigger", "question", "sources", "invariant",
                  "evidence", "attempted_fix", "glm_proposal", "decision_needed"}


@pytest.mark.parametrize("name,key", [("reviewer", "status"), ("adjudicator", "status"),
                                      ("debug-advisor", "verdict"), ("fast-dev-reviewer", "status")])
def test_pending_worker_examples_are_nonapproving_complete_json(name, key):
    import re
    text = (REPO_ROOT / f".opencode/agents/{name}.md").read_text()
    examples = [json.loads(body) for body in re.findall(r"```json\n(.*?)\n```", text, re.S)]
    pending = [item for item in examples if item.get(key) == "needs_consultation"]
    assert pending, "delegation denial requires explicit pending consultation, not own findings or approval"
    for item in pending:
        assert REQUEST_FIELDS == set(item["consultation_request"])
        assert item["consultation_request"]["glm_proposal"]
        if name == "fast-dev-reviewer":
            assert item["base_sha"] and item["head_sha"]


def test_context_worker_and_controller_consultation_transitions():
    for name in ("implementer", "planner"):
        text = (REPO_ROOT / f".opencode/agents/{name}.md").read_text()
        assert "NEEDS_CONTEXT" in text and "consultation_request" in text
        assert "glm_proposal" in text
    supervisor = (REPO_ROOT / ".opencode/agents/supervisor.md").read_text()
    for term in ("needs_consultation", "NEEDS_CONTEXT", "expert-advisor", "planner", "adjudicator", "TARGETED", "confirmed"):
        assert term in supervisor
    sdd = (REPO_ROOT / ".opencode/skills/subagent-driven-development/SKILL.md").read_text()
    for term in ("needs_consultation", "consultation_request", "before normal", "new material evidence", "before another repair"):
        assert term in sdd
    debugging = (REPO_ROOT / ".opencode/skills/systematic-debugging/SKILL.md").read_text()
    assert "needs_consultation" in debugging and "before `confirmed`" in debugging
    assert "opencode-go/glm-5.3-flash" in debugging
    assert "smarter model" not in debugging


def test_implementer_escalation_keeps_glm_implementation_without_model_fallback():
    import re
    text = (REPO_ROOT / ".opencode/agents/implementer.md").read_text()
    assert not re.search(r"(?:more capable|stronger|smarter)\s+model", text, re.I)
    escalation = text.split("**How to escalate:**", 1)[1].split("## Self-Review", 1)[0]
    for term in ("context", "smaller pieces", "bounded consultation", "`AGENTS.md`", "GLM retains implementation"):
        assert term in escalation


def test_direct_exemption_does_not_waive_dual_design_input():
    agents = (REPO_ROOT / "AGENTS.md").read_text()
    exception = agents.split("## Fast-dev workflow exception", 1)[1].split("## Branch Convention", 1)[0]
    assert "does not waive" in exception and "dual-model" in exception
    for name in ("fast-dev", "live-dev"):
        text = (REPO_ROOT / f".opencode/agents/{name}.md").read_text()
        for term in ("expert-advisor", "GLM proposal", "GPT critique", "reconciliation", "project `explorer`"):
            assert term in text
    wrap = (REPO_ROOT / ".opencode/skills/fast-dev-wrap-up/SKILL.md").read_text()
    assert "needs_consultation" in wrap and "expert-advisor" in wrap
    assert "before direct fixes" in wrap and "new material evidence" in wrap


def test_delivery_gate_is_canonical_and_wired_into_all_receiving_controllers():
    agents = (REPO_ROOT / "AGENTS.md").read_text()
    assert "### Fail-closed handoff delivery" in agents
    for name in ("supervisor", "fast-dev", "live-dev"):
        text = (REPO_ROOT / f".opencode/agents/{name}.md").read_text()
        assert "## Handoff delivery gate (before all report handling)" in text
        assert "AGENTS.md#fail-closed-handoff-delivery" in text
        assert "before consultation, verdict, fix, cap or completion handling" in " ".join(text.split())
