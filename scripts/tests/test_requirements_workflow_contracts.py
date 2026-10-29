"""Static declared workflow contracts, NOT proof of live-agent compliance.

Controller pressure probes supply behavioral evidence separately. The gate shell
test executes the real CLI in an isolated root, never initializes this checkout.
"""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".opencode/skills/requirements-reconciliation/SKILL.md"
AGENTS = "supervisor planner implementer reviewer debug-advisor fast-dev-reviewer fast-dev live-dev".split()
SKILLS = "brainstorming writing-plans subagent-driven-development systematic-debugging finishing-a-development-branch".split()
# Task 4 must not alter model/variant/permissions (or other role configuration).
# Deliberate future configuration changes must explicitly update these pins.
FRONTMATTER = dict(zip(AGENTS, [
    "5f6865b2e67e117ee1a2e86930de3721f87a642c0b12028e8ae68a38e3d38399",
    "8e4a4e6992ecbed663f7a46753ad8205411e32295031e7e00b64670ee3cd1b0c",
    "45121cf5806585df6f0e261ed6e8c45182b140b789c4505aad33c54a25e34cce",
    "04c299cb851598f93e1571e25d33dacf19b0b15db80ac084893e8a1fad10c821",
    "321abc26a52e0d11b3207e2c923594ab99721240fd5fa348e51c36d75a926ee7",
    "367d68d5ab9dc7165cbaddfff3513ad79d042dcfbb21d3d08811fc7203b96830",
    "8a58560fc0093ac752c0696ac8a6aca7541dbbd35c2c19d16c37f64520e2b6e3",
    "7da0acf8bd975ab7aa22e92b94a68c2fa6e95d078b7e8600fa5ccd42b439bbdf",
]))


def skill_text():
    assert SKILL.is_file(), "Missing reusable requirements-reconciliation skill"
    return SKILL.read_text()


def test_skill_discovery_and_frontmatter():
    text = skill_text()
    front = text.split("---", 2)[1]
    assert "name: requirements-reconciliation" in front
    assert re.search(r"description: Use when", front)
    for trigger in ("goal", "feature", "change", "bug", "maintenance", "exploration", "clarification"):
        assert trigger in front
    assert len(front) < 1024
    assert "requirements-reconciliation" in (ROOT / "AGENTS.md").read_text()


@pytest.mark.parametrize("slot", [
    "Conclusion", "Scope and sources", "Authority and uncertainty", "Changes and impacts",
    "Constraints and verification", "Next transition",
])
def test_proportional_conclusion_slots(slot):
    assert slot in skill_text()


def test_semantics_authority_and_history_contract():
    text = skill_text()
    for phrase in ("contributes_to", "derived_from", "refines", "REQ-<uuid>", "ART-<uuid>",
                   "no automatic satisfaction", "empirical", "design defect", "implementation defect",
                   "maintenance", "report-only", "historical", "provenance", "never-auto-send",
                   "no evidence of policy change", "inferred", "supersession"):
        assert phrase in text
    assert "no synthetic requirement" in text
    assert "not a global merge freeze" in text


@pytest.mark.parametrize("path", [*(f".opencode/agents/{n}.md" for n in AGENTS),
                                  *(f".opencode/skills/{n}/SKILL.md" for n in SKILLS)])
def test_assigned_touchpoints_discover_shared_skill(path):
    assert "requirements-reconciliation" in (ROOT / path).read_text()


@pytest.mark.parametrize("name", AGENTS)
def test_role_configuration_unchanged(name):
    text = (ROOT / f".opencode/agents/{name}.md").read_text()
    assert hashlib.sha256(text.split("---", 2)[1].encode()).hexdigest() == FRONTMATTER[name]


def test_autonomous_independent_artifact_review_contract():
    supervisor = (ROOT / ".opencode/agents/supervisor.md").read_text()
    for stale in ("get design approval", "present for human approval"):
        assert stale not in supervisor
    text = skill_text()
    for phrase in ("independent", "pending diff", "BASE..HEAD", "requirements", "design",
                   "implementation-spec", "resume automatically", "user artifact approval"):
        assert phrase in text
    for name in ("brainstorming", "writing-plans"):
        assert "independent" in (ROOT / f".opencode/skills/{name}/SKILL.md").read_text()


def test_fast_live_exceptions_and_manual_lifecycle_remain():
    for name in ("fast-dev", "live-dev"):
        text = (ROOT / f".opencode/agents/{name}.md").read_text()
        assert "requirements-reconciliation" in text
        assert "explicit user wrap-up/integration authorization" in text
        assert "no" in text and "per-change review" in text
    live = (ROOT / ".opencode/agents/live-dev.md").read_text()
    assert "confirm `mode: manual` before editing" in live
    assert "Validate before refresh" in live
    assert "no filesystem watching" in live


def test_cli_examples_use_actual_interfaces():
    text = skill_text()
    for phrase in ("python3 scripts/requirements.py query --repo-root . --stdin",
                   '"op":"reconciliation-context"', '"scope"', '"op":"readiness"',
                   '"material_criteria"', '"material_constraints"',
                   '"actor"', '"expected_revision"', '"ops"', '"op":"revise-requirement"',
                   "render --check", "implementer-owned"):
        assert phrase in text
    assert "bash-denied" in text


def gate_recipe():
    text = (ROOT / "Makefile").read_text()
    assert "requirements-check" in text.splitlines()[0]
    assert re.search(r"^opencode-check:.*\brequirements-check\b", text, re.M)
    match = re.search(r"^requirements-check:\n((?:\t.*\n)+)", text, re.M)
    assert match, "Missing requirements gate recipe"
    recipe = match[1]
    assert "pytest scripts/tests/test_requirements" in recipe
    assert "$(MAKE)" not in recipe and "opencode-check" not in recipe
    return recipe


def test_nonrecursive_make_gate():
    gate_recipe()
    run = subprocess.run(["make", "-n", "opencode-check"], cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout.count("pytest scripts/tests/test_requirements") == 1


def test_conditional_seed_gate_real_cli(tmp_path):
    # Execute only the shell conditional, not pytest (which would recurse).
    recipe = gate_recipe()
    conditional = recipe[recipe.index("\t@if "):].replace("\t@", "").replace("\t", "")
    (tmp_path / "scripts").symlink_to(ROOT / "scripts", target_is_directory=True)
    def run():
        return subprocess.run(["sh", "-c", conditional], cwd=tmp_path, capture_output=True, text=True)
    absent = run()
    assert absent.returncode == 0, absent.stdout + absent.stderr
    assert "seed absent" in absent.stdout
    assert not (tmp_path / "docs").exists(), "Gate must not initialize missing canonical data"
    init = subprocess.run(["python3", str(ROOT / "scripts/requirements.py"), "init",
                           "--repo-root", str(tmp_path)], capture_output=True, text=True)
    assert init.returncode == 0, init.stdout + init.stderr
    missing_projection = run()
    assert missing_projection.returncode != 0
    assert "projection-stale" in missing_projection.stdout
    render = subprocess.run(["python3", str(ROOT / "scripts/requirements.py"), "render",
                             "--repo-root", str(tmp_path)], capture_output=True, text=True)
    assert render.returncode == 0, render.stdout + render.stderr
    valid = run()
    assert valid.returncode == 0, valid.stdout + valid.stderr
    (tmp_path / "docs/requirements/index.md").write_text("stale\n")
    stale = run()
    assert stale.returncode != 0
    assert "projection-stale" in stale.stdout
    (tmp_path / "docs/requirements/ledger.json").write_text("{}\n")
    corrupt = run()
    assert corrupt.returncode != 0
    assert '"status": "error"' in corrupt.stdout
