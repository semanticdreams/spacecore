"""Durable progress must not inherit the private scratch workspace's ignores."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".opencode/skills/subagent-driven-development/scripts/sdd-workspace"


def run(repo, *args, env=None):
    return subprocess.run([str(SCRIPT), *map(str, args)], cwd=repo, env=env,
                          text=True, capture_output=True, timeout=10)


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, text=True,
                          capture_output=True, timeout=10, check=True)


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / ".gitignore").write_text((ROOT / ".gitignore").read_text())
    plans = repo / "docs/plans"
    plans.mkdir(parents=True)
    plan = plans / "a plan.md"
    plan.write_text("# A plan\n\n### Task 1: Example\n\nKeep progress.\n")
    return repo, plan


def snapshot(repo):
    return {str(path.relative_to(repo)): (path.lstat().st_mode,
            path.lstat().st_mtime_ns, os.readlink(path) if path.is_symlink()
            else path.read_bytes() if path.is_file() else None)
            for path in repo.rglob("*")}


def test_default_workspace_keeps_private_reports_ignored(project):
    repo, plan = project
    result = run(repo, plan)
    assert result.returncode == 0, result.stderr
    scratch = Path(result.stdout.strip())
    assert scratch.parent == repo / ".superpowers/sdd"
    assert (scratch / ".plan-path").read_text().strip() == str(plan.relative_to(repo))
    assert (scratch.parent / ".gitignore").read_text() == "*\n"
    assert git(repo, "check-ignore", str(scratch / "report.md")).stdout
    assert run(repo, plan).stdout == result.stdout


@pytest.mark.parametrize("existing", [False, True])
def test_progress_resolution_is_non_ignored_and_read_only(project, existing):
    repo, plan = project
    ledger = plan.with_name("a plan-progress.md")
    if existing:
        ledger.write_text("# Existing ledger; never overwrite\n")
    before = snapshot(repo)
    result = run(repo, "--progress", plan)
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(ledger) + "\n"
    assert snapshot(repo) == before
    assert not (repo / ".superpowers").exists()


@pytest.mark.parametrize("kind", ["outside-plan", "plan-symlink", "parent-symlink",
                                  "dangling-ledger", "outside-ledger", "inside-ledger", "directory"])
def test_invalid_public_paths_refuse_without_mutation(project, kind):
    repo, plan = project
    ledger = plan.with_name("a plan-progress.md")
    outside = repo / "other.md"
    outside.write_text("# Not in docs/plans\n")
    if kind == "outside-plan":
        plan = outside
    elif kind == "plan-symlink":
        plan.unlink()
        plan.symlink_to(outside)
    elif kind == "parent-symlink":
        (repo / "docs/plans/escape").symlink_to(repo, target_is_directory=True)
        plan = repo / "docs/plans/escape/other.md"
    elif kind == "dangling-ledger":
        ledger.symlink_to(repo / "missing")
    elif kind == "outside-ledger":
        ledger.symlink_to(outside)
    elif kind == "inside-ledger":
        ledger.symlink_to(plan)
    else:
        ledger.mkdir()
    before = snapshot(repo)
    result = run(repo, "--progress", plan)
    assert result.returncode != 0
    assert result.stderr and not result.stdout
    assert snapshot(repo) == before


@pytest.mark.parametrize("tracked", [False, True])
def test_ignored_progress_refuses_even_when_already_tracked(project, tracked):
    repo, plan = project
    ledger = plan.with_name("a plan-progress.md")
    ledger.write_text("# Original ledger\n")
    with (repo / ".gitignore").open("a") as stream:
        stream.write("docs/plans/*-progress.md\n")
    if tracked:
        git(repo, "add", "-f", str(ledger))
    before = snapshot(repo)
    result = run(repo, "--progress", plan)
    assert result.returncode != 0
    assert "ignored" in result.stderr
    assert snapshot(repo) == before


def test_git_inspection_error_is_not_treated_as_non_ignored(project, tmp_path):
    repo, plan = project
    binary = tmp_path / "bin"
    binary.mkdir()
    wrapper = binary / "git"
    wrapper.write_text('#!/bin/sh\nif [ "$1" = check-ignore ]; then exit 2; fi\n'
                       f'exec "{shutil.which("git")}" "$@"\n')
    wrapper.chmod(0o755)
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ["PATH"])
    before = snapshot(repo)
    result = run(repo, "--progress", plan, env=env)
    assert result.returncode != 0
    assert "ignore" in result.stderr
    assert snapshot(repo) == before


def test_explicit_unignore_is_respected(project):
    repo, plan = project
    with (repo / ".gitignore").open("a") as stream:
        stream.write("docs/plans/*.md\n!docs/plans/*-progress.md\n")
    before = snapshot(repo)
    result = run(repo, "--progress", plan)
    assert result.returncode == 0, result.stderr
    assert snapshot(repo) == before


def test_symlinked_docs_root_cannot_route_records_elsewhere(project):
    repo, plan = project
    moved = repo / "other-plans"
    plan.parent.rename(moved)
    (repo / "docs/plans").symlink_to(moved, target_is_directory=True)
    before = snapshot(repo)
    result = run(repo, "--progress", plan)
    assert result.returncode != 0
    assert "canonical" in result.stderr
    assert snapshot(repo) == before


def test_same_named_plans_in_distinct_directories_have_distinct_ledgers(project):
    repo, plan = project
    nested = plan.parent / "nested"
    nested.mkdir()
    other = nested / plan.name
    other.write_text("# Another plan\n")
    first = run(repo, "--progress", plan)
    second = run(repo, "--progress", other)
    assert first.returncode == second.returncode == 0
    assert first.stdout != second.stdout
    assert Path(second.stdout.strip()).parent == nested


def test_mismatched_private_workspace_keeps_original_records(project):
    repo, plan = project
    scratch = Path(run(repo, plan).stdout.strip())
    marker = scratch / ".plan-path"
    marker.write_text("docs/plans/some-other-plan.md\n")
    legacy = scratch / "progress.md"
    legacy.write_text("# Original retained progress\n")
    result = run(repo, plan)
    assert result.returncode != 0
    assert "preserve" in result.stderr
    assert marker.read_text() == "docs/plans/some-other-plan.md\n"
    assert legacy.read_text() == "# Original retained progress\n"


def test_private_legacy_ledger_is_never_automatically_published(project):
    repo, plan = project
    scratch = Path(run(repo, plan).stdout.strip())
    legacy = scratch / "progress.md"
    legacy.write_text("# Private original\ncorrection_used=1\n")
    before = snapshot(repo)
    result = run(repo, "--progress", plan)
    assert result.returncode == 0, result.stderr
    assert snapshot(repo) == before
    assert not Path(result.stdout.strip()).exists()


def test_task_brief_default_output_still_uses_private_scratch(project):
    repo, plan = project
    brief = SCRIPT.with_name("task-brief")
    result = subprocess.run([str(brief), str(plan), "1"], cwd=repo,
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    scratch = Path(run(repo, plan).stdout.strip())
    assert "Task 1: Example" in (scratch / "task-1-brief.md").read_text()
    assert not plan.with_name("a plan-progress.md").exists()


def test_record_guidance_routes_durable_state_out_of_scratch():
    sdd = (ROOT / ".opencode/skills/subagent-driven-development/SKILL.md").read_text()
    supervisor = (ROOT / ".opencode/agents/supervisor.md").read_text()
    finishing = (ROOT / ".opencode/skills/finishing-a-development-branch/SKILL.md").read_text()
    assert "sdd-workspace --progress PLAN_FILE" in sdd
    assert "reconcile" in sdd and "correction_used" in sdd
    assert "docs/plans/**/*-progress.md" in supervisor
    assert "`.superpowers/sdd/**/progress.md`" not in supervisor
    assert "`.superpowers/sdd/**/progress.md`" not in finishing
    assert "durable" in finishing and "committed or discarded here" not in finishing
    assert "retain development records" in finishing
    for role in ("fast-dev", "live-dev"):
        text = (ROOT / f".opencode/agents/{role}.md").read_text()
        assert "docs/plans/" in text and "tracked" in text
