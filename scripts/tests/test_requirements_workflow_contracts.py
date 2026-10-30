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
# Protect every nonrouting frontmatter byte, including mode and permissions.
# These fixed fingerprints come from trusted parent 2692081f79b6898deb6822a161360086d428f1bc,
# after verifying its full-frontmatter hashes against the original Task 4 pins.
# Only top-level model/variant lines are excluded: their presence and syntax are
# independently guarded by check_opencode_permissions.py and its mutation tests.
# Never regenerate expected configuration from the current role files.
FRONTMATTER = dict(zip(AGENTS, [
    "0c5356f5fc4bc38041d42aeb66026449499cfa033148dcaaa19a1655b8dc4b89",
    "3ea1a597a44232b4363f5e6cddf28d1b04aa32373cf2dde407fe7c01a3bfb31f",
    "e92ddc220756d86d9cc7d29efb1fa1081c1ed0c1194a960c91daf34a0a7f4c98",
    "5c55b760eb62d6d94c5a9036f170ec550b3212630d72dae1d6af597cba1e817d",
    "263487c1ca81f82de997f544326ee7b5ef814723f87dd956e39757896bb27141",
    "28e02a1866f7a1c46018fac96d84a53660d5022a55873e9b82d2c2c6e4b68c7d",
    "e159d07483db7490553a7c5248e68f760880163d24a4147adba0834ad5d5da9b",
    "fbc800fc5478ffc5beddec61dae08f09ba9975fe056ffeeaf42923e259433787",
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


def assert_role_configuration(name, text):
    front = re.sub(r"(?m)^(?:model|variant):[^\n]*\n", "", text.split("---", 2)[1])
    assert hashlib.sha256(front.encode()).hexdigest() == FRONTMATTER[name]


@pytest.mark.parametrize("name", AGENTS)
def test_role_configuration_unchanged(name):
    assert_role_configuration(name, (ROOT / f".opencode/agents/{name}.md").read_text())


@pytest.mark.parametrize("name", AGENTS)
def test_routing_edits_do_not_change_protected_configuration(name):
    text = (ROOT / f".opencode/agents/{name}.md").read_text()
    for key, value in (("model", "example-provider/another-model"), ("variant", "another-variant")):
        changed = re.sub(rf"(?m)^{key}:[^\n]*$", f"{key}: {value}", text)
        assert changed != text
        assert_role_configuration(name, changed)


@pytest.mark.parametrize("name", AGENTS)
def test_every_nonrouting_frontmatter_line_remains_protected(name):
    text = (ROOT / f".opencode/agents/{name}.md").read_text()
    before, front, after = text.split("---", 2)
    lines = front.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.strip() or re.match(r"^(?:model|variant):", line):
            continue
        changed = lines.copy()
        changed[index] = line.rstrip("\n") + " changed\n"
        with pytest.raises(AssertionError):
            assert_role_configuration(name, before + "---" + "".join(changed) + "---" + after)


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
