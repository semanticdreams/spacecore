from pathlib import Path

import pytest


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


def assert_actual_reporter_evidence_limitations(text):
    section = text.split('### Owned data roots and automatic crash reporting\n', 1)[1].split('\n##', 1)[0]
    evidence = ' '.join(section.split())
    assert 'neither observed a root native fatal' in evidence
    assert ('Actual reporter/grace behavior therefore remains unexercised, not verified '
            'fixed by either those runs or the host fixtures.') in evidence


def test_wine_notes_describe_one_shot_root_fatal_reporting_and_status_authority():
    text = read('docs/dev/notes/windows-wine-build-and-test.md')
    for phrase in ('one30-second reporting grace', 'newline-terminated', 'wine-fast stderr',
                   'private application observation pipe', 'command_returncode', 'unknown',
                   'early EOF', 'held pipes', 'native_fatal', 'fatal_report_timeout',
                   'never resets', '1800-second application hard deadline'):
        assert phrase in text
    assert 'launch-observation changes belong to the separate follow-up' not in text
    assert_actual_reporter_evidence_limitations(text)


@pytest.mark.parametrize('limitation,overclaim', [
    ('neither observed', 'both observed'),
    ('remains unexercised, not verified', 'was exercised and verified'),
    ('fixed by either those runs or the host fixtures.', 'verified by host fixtures alone.'),
])
def test_actual_reporter_evidence_guard_rejects_overclaims(limitation, overclaim):
    text = read('docs/dev/notes/windows-wine-build-and-test.md')
    assert limitation in text
    with pytest.raises(AssertionError):
        assert_actual_reporter_evidence_limitations(text.replace(limitation, overclaim, 1))


PUBLICATION_PAGE = 'docs/dev/features/record-publication.md'
WINE_NOTES = 'docs/dev/notes/windows-wine-build-and-test.md'


def normalized(text):
    return ' '.join(text.split())


def test_record_publication_documents_phase_abi_and_host_security_boundaries():
    text = normalized(read(PUBLICATION_PAGE))
    for phrase in (
        'publish(destination, payload, hooks) -> Result',
        'before-write', 'before-security', 'before-commit', 'before-cleanup',
        'final validation, rename and immediate committed assignment',
        'ABI1/112', 'ABI1/168', 'SNAPSHOT', 'CANCEL', 'RELEASE',
        'MemoryWineUnixFuncs', '__wine_unix_call', 'WINEDLLPATH',
        'SPACE_WINE_PUBLICATION_BINDING', 'HeapFree', 'process lifetime',
        'TokenGroups', 'TokenPrivileges', 'TokenElevationType',
        '0700', '0600', '0750', '0770', 'No parent chmod',
        'No C++ objects', 'creating module',
        'Application death, memory corruption and power loss have no stronger guarantee',
    ):
        assert phrase in text


@pytest.mark.parametrize('path', [PUBLICATION_PAGE, WINE_NOTES])
def test_publication_docs_describe_current_eight_stage_closed_harness(path):
    text = normalized(read(path))
    stages = ('preflight', 'build-windows-from-linux', 'package-windows-runtime',
              'verify-windows-outputs', 'wine-publication-build', 'wine-admission',
              'wine-publication', 'wine-fast')
    # The current table is deliberately separate from historical run evidence.
    table = text.split('<!-- publication-stages -->', 1)[1].split('<!-- /publication-stages -->', 1)[0]
    assert tuple(part.split('`')[0] for part in table.split('| `')[1:]) == stages
    for phrase in ('900 seconds', '480 seconds', '420 seconds', '1920 seconds',
                   '1800 seconds', '45 seconds', '120 seconds', '30 seconds',
                   'cpp-022', 'cpp-002', 'store-write', 'store-read',
                   'schema-4', 'publication grant', 'application grant',
                   'five private PE children', '60-second', 'discovery copy',
                   'parent-pinned', 'fixed base-dir', 'not default-root coverage'):
        assert phrase in text


def assert_publication_evidence_limits(text):
    evidence = normalized(text.split('<!-- publication-evidence -->', 1)[1]
                          .split('<!-- /publication-evidence -->', 1)[0])
    for phrase in ('a8012ef002c1bc21ae2c2685e788ddbcc7bb2c8e',
                   'Earlier compatibility proof is not final Wine publication success',
                   'Actual Wine/PE publication categories and the full Wine gate remain pending',
                   'Native NT assertions remain intact and unexercised under Wine',
                   'foreign_uid_probe=not-configured'):
        assert phrase in evidence


@pytest.mark.parametrize('path', [PUBLICATION_PAGE, WINE_NOTES])
def test_publication_docs_separate_source_contract_from_actual_wine_evidence(path):
    assert_publication_evidence_limits(read(path))


@pytest.mark.parametrize('limitation,overclaim', [
    ('not final Wine publication success', 'final Wine publication success'),
    ('full Wine gate remain pending', 'full Wine gate passed'),
    ('intact and unexercised under Wine', 'verified under Wine'),
    ('foreign_uid_probe=not-configured', 'foreign_uid_probe=passed'),
])
def test_publication_evidence_guard_rejects_overclaims(limitation, overclaim):
    text = read(PUBLICATION_PAGE)
    assert limitation in text
    with pytest.raises(AssertionError):
        assert_publication_evidence_limits(text.replace(limitation, overclaim, 1))


def test_wine_notes_supersede_native_substitution_and_six_stage_contract():
    text = normalized(read(WINE_NOTES))
    assert 'supersedes the old native-substitution proposal and six-stage wording' in text
    assert 'The next requirements are native Windows persistent-ACL validation' not in text
    assert 'No seventh stage or extra log inventory is introduced' not in text
    assert '[Record publication](../features/record-publication.md)' in text
