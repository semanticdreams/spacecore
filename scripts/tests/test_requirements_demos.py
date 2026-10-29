"""Composite demonstrations and the new user-facing documentation contract."""

import subprocess
import sys

from helpers_requirements import REPO_ROOT, requirements_lib, run_cli
from test_requirements_scenarios import Scenario


def test_demo_a_goal_driven_feature(tmp_path):
    c = Scenario(tmp_path)
    goal = c.req("Reduce accidental sends", "goal", empirical=True)
    capability = c.req("Manual confirmation", "capability")
    c.edge("contributes_to", capability, goal)
    design, spec, code, test = c.chain(capability)
    execution = subprocess.run([sys.executable, "test_send.py"], cwd=tmp_path,
                               capture_output=True, text=True)
    assert execution.returncode == 0, execution.stderr
    c.observe(capability)
    assert {goal, capability, design, spec} <= set(c.query("trace", id=code)["nodes"])
    assert {code, test} <= set(c.query("trace", id=goal, direction="backward")["nodes"])
    assert c.query("coverage")["requirements"][goal]["assessment"] is None
    assert run_cli(tmp_path, "render", "--check").returncode == 0


def test_demo_b_existing_behavior_change(tmp_path):
    c = Scenario(tmp_path)
    rid = c.req("Confirm once")
    design, _, code, _ = c.chain(rid)
    c.observe(rid)
    c.op("revise-requirement", id=rid, statement="Confirm twice",
         reason="Fixture user explicitly changes desired behavior")
    report = c.query("reconciliation-context", scope=[rid])
    assert {design, code} <= set(report["records"])
    assert c.query("get", id=rid)["criteria_latest"]["c1"]["currency"] == "stale"
    assert c.readiness(code, criteria=[{"requirement_id": rid, "criterion_id": "c1"}])["status"] == "needs-investigation"


def test_demo_c_bug_correction(tmp_path):
    c = Scenario(tmp_path)
    rid = c.req("Never auto-send")
    _, _, code, _ = c.chain(rid)
    # Reproduce a real fixture defect before recording its negative observation.
    (tmp_path / "send.py").write_text("def send(): return 'automatic'\n")
    c.op("update-artifact", id=code, content_digest=c.digest("send.py"))
    failed = subprocess.run([sys.executable, "test_send.py"], cwd=tmp_path,
                            capture_output=True, text=True)
    assert failed.returncode != 0 and "AssertionError" in failed.stderr
    c.observe(rid, "failed")
    selected = [{"requirement_id": rid, "criterion_id": "c1"}]
    assert c.readiness(code, criteria=selected)["status"] == "blocked"
    (tmp_path / "send.py").write_text("def send(): return 'manual'\n")
    c.op("update-artifact", id=code, content_digest=c.digest("send.py"))
    passed = subprocess.run([sys.executable, "test_send.py"], cwd=tmp_path,
                            capture_output=True, text=True)
    assert passed.returncode == 0, passed.stderr
    c.observe(rid)  # Same timestamp: later append governs; old observation retained.
    assert c.readiness(code, criteria=selected)["status"] == "no-recorded-blockers"
    assert len(c.query("reconciliation-context", scope=[code])["verifications"]) == 2
    assert c.query("get", id=rid)["requirement"]["revision"] == 1


def test_demo_d_verified_capability_outcome_not_proven(tmp_path):
    c = Scenario(tmp_path)
    outcome = c.req("Accidental sends decrease", "outcome", empirical=True)
    capability = c.req("Confirmation implemented", "capability")
    c.edge("contributes_to", capability, outcome)
    c.chain(capability)
    execution = subprocess.run([sys.executable, "test_send.py"], cwd=tmp_path,
                               capture_output=True, text=True)
    assert execution.returncode == 0, execution.stderr
    c.observe(capability)
    c.assess(capability, "satisfied")
    assert c.query("get", id=outcome)["criteria_latest"]["c1"]["result"] == "absent"
    assert c.readiness(capability)["grants_permissions"] is False
    c.observe(outcome, "failed", "empirical_measurement")
    latest = c.query("get", id=outcome)["criteria_latest"]["c1"]
    assert (latest["currency"], latest["result"]) == ("current", "failed")
    assert c.readiness(capability)["status"] == "no-recorded-blockers"


def test_documentation_contract_and_navigation():
    page = REPO_ROOT / "docs/dev/features/requirements-driven-engineering.md"
    templates = REPO_ROOT / "docs/dev/notes/requirement-templates.md"
    assert page.is_file(), "Task 5 API/limitations documentation is missing"
    assert templates.is_file(), "Task 5 requirement/reconciliation templates are missing"
    text = page.read_text()
    for term in ("expected_revision", "projection-stale", "render --check",
                 "semantic_equivalence", "empirical", "mergedAt", "npm run docs:build"):
        assert term in text
    for path in ("docs/index.md", "docs/dev/development-records.md",
                 "docs/dev/features/opencode-agent-workflow.md", "docs/.vitepress/config.mts"):
        assert "/requirements/" in (REPO_ROOT / path).read_text(), path
    assert "source_reference" in templates.read_text()
    assert "Next transition" in templates.read_text()


def test_current_task_seed_is_grounded_linked_and_honest():
    path = REPO_ROOT / "docs/requirements/ledger.json"
    assert path.is_file(), "Task 5 current-task canonical seed is missing"
    ledger = requirements_lib().load_ledger(REPO_ROOT)
    assert {r["classification"] for r in ledger["requirements"].values()} >= {
        "goal", "capability", "behavior", "constraint"}
    linked = {r[end] for r in ledger["relations"] for end in ("source", "target")}
    assert set(ledger["artifacts"]) <= linked
    for req in ledger["requirements"].values():
        assert req["provenance"]["origin"] in {"user_intent", "justified_interpretation"}
        assert req["provenance"]["excerpt"]
        assert "2026-10-29-requirements-driven-engineering" in req["provenance"]["source_reference"]
        assert any(h["kind"] == "transition" and h["to_lifecycle"] == "active"
                   for h in req["history"])
    assert {a["kind"] for a in ledger["artifacts"].values()} == {
        "design", "implementation_spec", "code", "test", "evidence"}
    for req in ledger["requirements"].values():
        if any(c["applicability"] == "empirical" for c in req["acceptance_criteria"]):
            observations = [v for v in ledger["verifications"] if v["requirement_id"] == req["id"]]
            assert all(v["method"] == "empirical_measurement" for v in observations)
        # Creation is honestly partial; later authorized assessment may progress.
        first = next(a for a in ledger["assessments"] if a["requirement_id"] == req["id"])
        assert first["state"] == "partial"
    assert run_cli(REPO_ROOT, "render", "--check").returncode == 0


def test_canonical_lock_and_projection_temporary_files_are_ignored():
    for name in ("docs/requirements/ledger.json.lock",
                 "docs/requirements/.ledger.json.123.tmp",
                 "docs/requirements/.index.md.123.tmp"):
        result = subprocess.run(["git", "check-ignore", "--quiet", name],
                                cwd=REPO_ROOT, capture_output=True, text=True)
        assert result.returncode == 0, name
