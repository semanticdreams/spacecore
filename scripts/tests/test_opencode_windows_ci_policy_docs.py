from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_supervisor_routes_windows_ci_failures_to_reproducer():
    text = read(".opencode/agents/supervisor.md")
    assert "windows-ci-reproducer" in text
    assert "build-windows" in text
    assert "test-windows" in text
    assert "build-windows-installer" in text
    assert "not obviously CI infrastructure-only" in text
    assert "Linux cross-build + Wine" in text


def test_finishing_and_github_workflow_debug_require_local_windows_reproduction():
    for path in [
        ".opencode/skills/finishing-a-development-branch/SKILL.md",
        ".opencode/skills/github-workflow-debug/SKILL.md",
    ]:
        text = read(path)
        assert "windows-ci-reproducer" in text
        assert "before pushing another" in text or "before another push" in text
        assert "not obviously CI infrastructure-only" in text


def test_runtime_and_dev_docs_name_wrapper_commands():
    for path in [
        ".opencode/skills/space-testing-runtime/SKILL.md",
        "docs/dev/features/opencode-agent-workflow.md",
        "docs/dev/notes/windows-wine-build-and-test.md",
    ]:
        text = read(path)
        assert "opencode_windows_ci_repro.py" in text
        assert "preflight --repo-root ." in text
        assert "setup-host --repo-root ." in text
        assert "reproduce --repo-root ." in text


def test_runtime_skill_requires_capability_for_agent_windows_ci_failures():
    text = read(".opencode/skills/space-testing-runtime/SKILL.md")
    assert "dispatch `windows-ci-reproducer`" in text
    assert "use the guarded wrapper or dispatch" not in text


def test_github_workflow_debug_reruns_reproducer_after_fix_before_push():
    text = read(".opencode/skills/github-workflow-debug/SKILL.md")
    assert "After implementer commits" in text
    assert "rerun `windows-ci-reproducer` before pushing" in text
    assert "Only push when reproduction passes" in text
    assert "HUMAN_DECISION_REQUIRED with wrapper evidence" in text


def test_windows_notes_match_post_merge_manual_policy_and_keep_native_authority():
    text = read("docs/dev/notes/windows-wine-build-and-test.md")
    policy = read("docs/dev/notes/github-actions-hygiene.md")
    assert "Windows validation lives in the `windows` workflow and runs on pushes to\n`main` plus manual dispatch" in policy
    assert "`test.yml` Linux PR/merge-queue validation path" in text
    assert "`windows.yml` Windows main-push/manual validation path" in text
    assert "Windows validation is post-merge, not a PR or merge-queue gate" in text
    assert "`windows.yml` runs on pushes to `main` plus `workflow_dispatch`, not on PRs, merge groups or a schedule" in text
    assert "- `test.yml` PR/merge-queue validation path" not in text
    assert "Manual dispatch remains applicable to Windows validation and release packaging" in text
    assert "native Windows CI remains authoritative" in text
    assert "not a substitute for native Windows CI" in " ".join(text.split())


def test_current_wine_notes_describe_owned_lifecycle_not_retired_default_prefix_contract():
    text = read('docs/dev/notes/windows-wine-build-and-test.md')
    current = text.split('## Reproducible Workflow (Current)', 1)[1]
    for phrase in ('1800 seconds', '480 seconds', '1920 seconds', '45 seconds',
                   'immutable ownership', 'quiescence', 'terminal', 'SIGKILL', '93 RUN', '92 PASS',
                   'FD', 'retained', 'stopped_generation'):
        assert phrase in current
    for retired in ('retains180 seconds', 'still uses **180 seconds**', "application's180-second bound is unchanged",
                    'inherited/default prefix selection', 'Default-prefix identity is derived'):
        assert retired not in current
    assert 'scripts/wine/runtime.sh' not in text
    assert '{runtime.sh,' not in text
