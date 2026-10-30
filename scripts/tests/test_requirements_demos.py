"""Composite demonstrations and the new user-facing documentation contract."""

import subprocess
import sys
import hashlib
import shutil
from datetime import datetime, timedelta

import pytest

from helpers_requirements import REPO_ROOT, apply_request, create_op, requirements_lib, run_cli
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


# Immutable historical seed membership, not a filter on every future task's intent.
SEED_IDS = {
    "goal": "REQ-9d648a91-af2e-40e6-8e4e-41a2972373cf",
    "entity": "REQ-0a846556-20fb-4bd3-aff2-eedbda9a96d6",
    "graph": "REQ-eb1aed20-d61f-419e-97cd-79f35b32aa59",
    "trace": "REQ-1970c4a9-a5dc-4d1b-93ce-dc88ed42df84",
    "transactions": "REQ-0bf07879-9bbb-421a-85ab-37f495b6e552",
    "evidence": "REQ-2824ad77-fbc5-4db6-ac9a-732af10eeabc",
    "reports": "REQ-9abdf9a9-e9b5-437d-8175-549de16d9c87",
    "reconciliation": "REQ-8e50a634-76ae-4100-9f60-90e4552ec954",
    "reviews": "REQ-49e62b92-aada-447d-9d15-531625fa0dcc",
    "compatibility": "REQ-26f18ef2-15f6-4278-b9a1-9c7b4b246e5c",
    "documentation": "REQ-e0275d31-a048-4f5c-850e-40bdb647d812",
    "integration": "REQ-454f6972-1fb2-49f3-b39c-41c04a67012a",
}


def assert_seed_contract(root):
    path = root / "docs/requirements/ledger.json"
    assert path.is_file(), "Task 5 current-task canonical seed is missing"
    # Strict schema and graph validation cover the entire live ledger. Historical
    # capture conventions below belong only to these twelve retained identities.
    ledger = requirements_lib().load_ledger(root)
    assert set(SEED_IDS.values()) <= ledger["requirements"].keys()
    seed_requirements = [ledger["requirements"][rid] for rid in SEED_IDS.values()]
    assert {r["classification"] for r in seed_requirements} >= {
        "goal", "capability", "behavior", "constraint"}
    linked = {r[end] for r in ledger["relations"] for end in ("source", "target")}
    assert set(ledger["artifacts"]) <= linked
    for req in seed_requirements:
        assert req["provenance"]["origin"] in {"user_intent", "justified_interpretation"}
        assert req["provenance"]["excerpt"]
        assert "2026-10-29-requirements-driven-engineering" in req["provenance"]["source_reference"]
        assert any(h["kind"] == "transition" and h["to_lifecycle"] == "active"
                   for h in req["history"])
    assert {a["kind"] for a in ledger["artifacts"].values()} == {
        "design", "implementation_spec", "code", "test", "evidence"}
    for req in seed_requirements:
        if any(c["applicability"] == "empirical" for c in req["acceptance_criteria"]):
            observations = [v for v in ledger["verifications"] if v["requirement_id"] == req["id"]]
            assert all(v["method"] == "empirical_measurement" for v in observations)
        # Creation is honestly partial; later authorized assessment may progress.
        first = next(a for a in ledger["assessments"] if a["requirement_id"] == req["id"])
        assert first["state"] == "partial"
    assert run_cli(root, "render", "--check").returncode == 0


def test_current_task_seed_is_grounded_linked_and_honest():
    assert_seed_contract(REPO_ROOT)


def copy_seed_fixture(root):
    """Copy a snapshot, then mutate only through real CLI operations.

    Copy declared source/evidence bytes too: no symlink to the working checkout,
    so the workflow mutation regression cannot edit real supervisor guidance.
    """
    ledger = requirements_lib().load_ledger(REPO_ROOT)
    paths = {"docs/requirements/ledger.json", "docs/requirements/index.md",
             ".opencode/agents/supervisor.md"}
    paths.update(a["locator"] for a in ledger["artifacts"].values())
    for verification in ledger["verifications"]:
        paths.update(ledger["artifacts"][key]["locator"] if key.startswith("ART-") else key
                     for key in verification["dependency_digests"])
        ref = verification["evidence_ref"]
        paths.add(ref.get("locator") or ledger["artifacts"][ref["artifact_id"]]["locator"])
    for path in sorted(paths):
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / path, destination)
    return ledger


def test_seed_contract_allows_independently_sourced_proposed_requirement(tmp_path):
    ledger = copy_seed_fixture(tmp_path)
    result = run_cli(tmp_path, "apply", request=apply_request(create_op(
        statement="New user request: retain unsent drafts offline.",
        provenance={"source_reference": "independent user request for next task",
                    "excerpt": "Keep my unsent drafts offline", "actor": "new-user",
                    "date": "2026-10-30", "origin": "user_intent"}),
        expected_revision=ledger["revision"]))
    assert result.returncode == 0, result.stdout + result.stderr
    rid = result.json["result"]["ops"][0]["id"]
    after = requirements_lib().load_ledger(tmp_path)
    assert after["requirements"][rid]["lifecycle"] == "proposed"
    assert not any(a["requirement_id"] == rid for a in after["assessments"])
    assert_seed_contract(tmp_path)


def latest_verification(ledger, rid):
    return max((v for v in ledger["verifications"] if v["requirement_id"] == rid),
               key=lambda v: (v["timestamp"], ledger["verifications"].index(v)))


@pytest.mark.parametrize("name", [n for n in SEED_IDS if n not in ("goal", "integration")])
def test_seed_verification_declares_material_tested_inputs(name):
    ledger = requirements_lib().load_ledger(REPO_ROOT)
    declared = latest_verification(ledger, SEED_IDS[name])["dependency_digests"]
    required = {"scripts/requirements_lib/__init__.py", "scripts/requirements_lib/locking.py",
                "scripts/tests/helpers_requirements.py", "scripts/tests/test_requirements_demos.py"}
    if name in ("reconciliation", "reviews", "documentation"):
        required |= {"AGENTS.md", "Makefile", ".opencode/agents/supervisor.md",
                     ".opencode/skills/brainstorming/SKILL.md"}
    if name in ("compatibility", "documentation"):
        required |= {"docs/.vitepress/config.mts", "docs/package.json", "docs/package-lock.json",
                     "docs/scripts/check-record-navigation.mjs", "docs/scripts/generate-record-indexes.mjs"}
    assert required <= declared.keys(), sorted(required - declared.keys())


@pytest.mark.parametrize("name", ["reconciliation", "reviews"])
def test_seed_workflow_observation_stales_when_tested_supervisor_changes(tmp_path, name):
    ledger = copy_seed_fixture(tmp_path)
    rid = SEED_IDS[name]
    original = latest_verification(ledger, rid)
    # New fixture observation at the copied source snapshot, preserving the seed's
    # declared dependency membership. This isolates omissions from incidental test
    # edits in the current checkout; it does not rewrite any canonical observation.
    args = {k: v for k, v in original.items() if k not in ("actor", "evidence_digest")}
    args["timestamp"] = (datetime.fromisoformat(original["timestamp"].replace("Z", "+00:00"))
                         + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    args["procedure"] = "Fixture-only dependency currency inspection at copied source snapshot"
    args["dependency_digests"] = {
        key: hashlib.sha256((tmp_path / (ledger["artifacts"][key]["locator"]
            if key.startswith("ART-") else key)).read_bytes()).hexdigest()
        for key in original["dependency_digests"]}
    result = run_cli(tmp_path, "apply", request=apply_request(
        {"op": "record-verification", "args": args}, expected_revision=ledger["revision"]))
    assert result.returncode == 0, result.stdout + result.stderr
    def currency():
        return requirements_lib().query(tmp_path, {"op": "get", "args": {"id": rid}})["result"]["criteria_latest"]["c1"]["currency"]
    assert currency() == "current"
    source = tmp_path / ".opencode/agents/supervisor.md"
    source.write_text(source.read_text() + "\nChanged fixture discovery/approval guidance.\n")
    assert currency() == "stale"


def test_canonical_lock_and_projection_temporary_files_are_ignored():
    for name in ("docs/requirements/ledger.json.lock",
                 "docs/requirements/.ledger.json.123.tmp",
                 "docs/requirements/.index.md.123.tmp"):
        result = subprocess.run(["git", "check-ignore", "--quiet", name],
                                cwd=REPO_ROOT, capture_output=True, text=True)
        assert result.returncode == 0, name
