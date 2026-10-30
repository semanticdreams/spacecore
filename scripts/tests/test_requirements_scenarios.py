"""Fifteen reconciliation inputs over real CLI transactions.

Agents own the semantic conclusions described in each test, not the CLI. These
fixtures test retrieval, retained facts and consequences of an agent's decision;
there is deliberately no keyword-to-conclusion routing implementation.
"""

import hashlib

import pytest

from helpers_requirements import (
    apply_request, create_op, init_ok, provenance, requirements_lib, run_cli,
)


class Scenario:
    """A temporary repository whose canonical bytes are written only by the CLI."""

    def __init__(self, root):
        self.root = root
        self.revision = init_ok(root).json["revision"]

    def apply(self, *ops):
        result = run_cli(self.root, "apply", request=apply_request(
            *ops, expected_revision=self.revision, actor="implementer/scenario"))
        assert result.returncode == 0, result.stdout + result.stderr
        self.revision = result.json["revision"]
        return result.json["result"]["ops"]

    def op(self, operation, **args):
        return self.apply({"op": operation, "args": args})[0]

    def req(self, statement, classification="behavior", empirical=False):
        return self.apply(create_op(
            statement=statement, classification=classification,
            acceptance_criteria=[{"id": "c1", "text": statement,
                                  "applicability": "empirical" if empirical else "analytical"}],
            provenance=dict(provenance(), excerpt=statement)))[0]["id"]

    def art(self, locator, kind, content):
        path = self.root / locator
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return self.op("register-artifact", kind=kind, title=locator,
                       locator=locator, content_digest=self.digest(locator))["id"]

    def digest(self, locator):
        return hashlib.sha256((self.root / locator).read_bytes()).hexdigest()

    def edge(self, kind, source, target, confidence="explicit"):
        return self.op("add-relation", type=kind, source=source, target=target,
                       confidence=confidence, rationale="Fixture source supports this link.",
                       provenance=provenance())["id"]

    def query(self, operation, **args):
        result = run_cli(self.root, "query", request={"op": operation, "args": args})
        assert result.returncode == 0, result.stdout + result.stderr
        return result.json["result"]

    def readiness(self, *scope, criteria=(), constraints=()):
        return self.query("readiness", scope=list(scope), material_criteria=list(criteria),
                          material_constraints=list(constraints))

    def observe(self, rid, result="passed", method="automated_test"):
        locator = "evidence/" + rid + ".txt"
        path = self.root / locator
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Fixture observation: " + result)
        revision = self.query("get", id=rid)["requirement"]["revision"]
        self.op("record-verification", requirement_id=rid, requirement_revision=revision,
                criterion_id="c1", method=method, result=result,
                procedure="Fixture procedure; not production measurement.",
                environment="temporary fixture repository", observation=result,
                timestamp="2026-10-29T12:00:00Z", evidence_ref={"locator": locator},
                dependency_digests={locator: self.digest(locator)})

    def assess(self, rid, state, source="docs/intent.md"):
        self.op("record-assessment", requirement_id=rid,
                requirement_revision=self.query("get", id=rid)["requirement"]["revision"],
                state=state, rationale="Explicit fixture assessment, not derived from links.",
                source_refs=[{"locator": source}])

    def chain(self, rid, design_text="Manual send only"):
        design = self.art("design.md", "design", design_text)
        spec = self.art("plan.md", "implementation_spec", "Implement manual send")
        code = self.art("send.py", "code", "def send(): return 'manual'\n")
        test = self.art("test_send.py", "test", "from send import send\nassert send() == 'manual'\n")
        self.edge("addresses", design, rid)
        self.edge("realizes", spec, design)
        self.edge("implements", code, spec)
        self.edge("verifies", test, rid)
        self.edge("exercises", test, code)
        return design, spec, code, test


@pytest.fixture
def scenario(tmp_path):
    return Scenario(tmp_path)


def test_scenario_01_missing_requirement_intake(scenario):
    c = scenario
    assert c.query("search", text="manual send")["matches"] == []
    rid = c.req("manual send requires confirmation")
    assert c.query("get", id=rid)["requirement"]["provenance"]["origin"] == "user_intent"
    assert c.query("search", text="manual send")["matches"] == [rid]


def test_scenario_02_reuses_existing_requirements(scenario):
    c = scenario
    rid = c.req("manual send requires confirmation")
    before = c.revision
    found = c.query("search", text="confirmation")
    assert found["semantic_equivalence"] is False
    assert c.query("reconciliation-context", scope=found["matches"])["records"][rid]["statement"]
    assert c.revision == before  # Agent reuses inspected intent; no synthetic duplicate.


def test_scenario_03_goal_decomposition_refines(scenario):
    c = scenario
    goal = c.req("Safer communication", "goal")
    precise = c.req("Never send without confirmation")
    c.edge("refines", precise, goal)
    assert goal in c.query("trace", id=precise)["nodes"]
    assert precise in c.query("trace", id=goal, direction="backward")["nodes"]
    assert c.query("coverage")["requirements"][goal]["assessment"] is None


def test_scenario_04_multi_capability_outcomes(scenario):
    c = scenario
    outcome = c.req("Fewer accidental sends", "outcome", empirical=True)
    children = [c.req(s, "capability") for s in ("Preview", "Confirm")]
    for child in children:
        c.edge("contributes_to", child, outcome)
    assert set(children) <= set(c.query("impact", id=outcome)["nodes"])
    assert c.query("get", id=outcome)["criteria_latest"]["c1"]["result"] == "absent"


def test_scenario_05_capability_contributes_multiple_goals(scenario):
    c = scenario
    capability = c.req("Preview before sending", "capability")
    goals = [c.req(s, "goal") for s in ("Fewer errors", "Better confidence")]
    for goal in goals:
        c.edge("contributes_to", capability, goal)
    report = c.query("impact", id=capability)
    assert set(goals) <= set(report["nodes"])
    assert any(s["reason"] == "potential-purpose-impact" for p in report["paths"] for s in p["steps"])


def test_scenario_06_cross_branch_constraint_readiness(scenario):
    c = scenario
    constraint = c.req("Never auto-send", "constraint")
    branches = [c.req("Email preview"), c.req("Chat preview")]
    for branch in branches:
        c.edge("constrains", constraint, branch)
    c.assess(constraint, "partial")
    for branch in branches:
        report = c.readiness(branch, constraints=[constraint])
        assert report["status"] == "blocked"
        assert report["material_constraints"] == [constraint]


def test_scenario_07_conflict_disposition_readiness(scenario):
    c = scenario
    manual, automatic = c.req("Only manual send"), c.req("Always automatic send")
    edge = c.edge("conflicts_with", manual, automatic)
    assert c.readiness(manual)["status"] == "blocked"
    c.op("record-conflict-disposition", relation_id=edge,
         explanation="Only manual applies in this fixture scope", authority="Fixture explicit policy")
    assert c.readiness(manual)["dispositions"][0]["relation_id"] == edge
    assert c.readiness(manual)["status"] == "blocked"
    assert c.query("get", id=automatic)["requirement"]["lifecycle"] == "proposed"


def test_scenario_08_intent_design_conflict_finding(scenario):
    c = scenario
    rid = c.req("Never auto-send")
    design, *_ = c.chain(rid, "Auto-send immediately")
    context = c.query("reconciliation-context", scope=[design])
    assert context["records"][rid]["provenance"]["excerpt"] == "Never auto-send"
    assert (c.root / context["records"][design]["locator"]).read_text() == "Auto-send immediately"
    # Agent finding: contrary solution is a design defect, not new product policy.
    assert not any(r["type"] == "conflicts_with" for r in context["relations"])


def test_scenario_09_implementation_defect_reuses_requirement(scenario):
    c = scenario
    rid = c.req("Never auto-send")
    _, _, code, test = c.chain(rid)
    c.observe(rid, "failed")
    assert rid in c.query("trace", id=code)["nodes"]
    assert test in c.query("impact", id=code)["nodes"]
    assert c.readiness(code, criteria=[{"requirement_id": rid, "criterion_id": "c1"}])["status"] == "blocked"
    assert len(requirements_lib().load_ledger(c.root)["requirements"]) == 1


def test_scenario_10_design_defect_routes_to_design_revision(scenario):
    c = scenario
    rid = c.req("Never auto-send")
    design, _, code, _ = c.chain(rid, "Auto-send immediately")
    (c.root / "design.md").write_text("Wait for explicit confirmation")
    assert any(f["code"] == "stale-artifact" and f["id"] == design
               for f in c.query("coverage")["findings"])
    c.op("update-artifact", id=design, content_digest=c.digest("design.md"))
    assert code in c.query("impact", id=design)["nodes"]
    assert c.query("get", id=rid)["requirement"]["revision"] == 1


def test_scenario_11_bug_reveals_missing_requirement(scenario):
    c = scenario
    old = c.req("Preview messages")
    assert c.query("search", text="offline")["matches"] == []
    # Inspected fixture user intent establishes the gap; a bug alone cannot.
    gap = c.req("Preserve draft offline")
    c.edge("derived_from", gap, old, confidence="uncertain")
    report = c.query("reconciliation-context", scope=[gap])
    assert report["unknowns"]
    assert report["records"][gap]["provenance"]["excerpt"] == "Preserve draft offline"


def test_scenario_12_maintenance_reporting_explicit(scenario):
    c = scenario
    rid = c.req("Never auto-send")
    _, _, code, _ = c.chain(rid)
    before = requirements_lib().load_ledger(c.root)
    context = c.query("reconciliation-context", scope=[code])
    assert rid in context["records"]
    assert before == requirements_lib().load_ledger(c.root)
    # Report-only maintenance conclusion belongs in the agent handoff, not a REQ.
    assert context["coverage"]["scope"]["unregistered_history"] == "outside-semantic-coverage"


def test_scenario_13_revision_invalidates_design_traces(scenario):
    c = scenario
    rid = c.req("Confirm once")
    design, _, code, _ = c.chain(rid)
    second = c.art("second-design.md", "design", "Also confirms once")
    c.edge("addresses", second, rid)
    c.observe(rid)
    c.op("revise-requirement", id=rid, reason="Fixture user changes confirmation policy",
         statement="Confirm twice", provenance=dict(provenance(), excerpt="Confirm twice"))
    record = c.query("get", id=rid)
    assert record["requirement"]["history"][0]["prior"]["statement"] == "Confirm once"
    assert record["criteria_latest"]["c1"]["currency"] != "current"
    assert {design, second, code} <= set(c.query("impact", id=rid)["nodes"])
    # Links identify re-review scope; the CLI does not semantically invalidate text.


def test_scenario_14_design_discovery_returns_to_reconciliation(scenario):
    c = scenario
    rid = c.req("Preview messages")
    design, *_ = c.chain(rid)
    discovery = c.req("Preview unavailable attachments explicitly")
    c.edge("refines", discovery, rid)
    c.edge("addresses", design, discovery, confidence="inferred")
    context = c.query("reconciliation-context", scope=[discovery], max_depth=1)
    assert context["unknowns"] and context["truncated"]
    assert c.query("get", id=discovery)["requirement"]["lifecycle"] == "proposed"


def test_scenario_15_verified_capability_outcome_not_satisfied(scenario):
    c = scenario
    outcome = c.req("Fewer accidental sends in practice", "outcome", empirical=True)
    capability = c.req("Confirmation available", "capability")
    c.edge("contributes_to", capability, outcome)
    c.observe(capability)
    c.assess(capability, "satisfied")
    report = c.query("coverage")
    assert report["requirements"][capability]["criteria_latest"]["c1"]["result"] == "passed"
    assert report["requirements"][outcome]["assessment"] is None
    assert c.readiness(capability, criteria=[{"requirement_id": capability, "criterion_id": "c1"}])["status"] == "no-recorded-blockers"
    assert c.readiness(outcome, criteria=[{"requirement_id": outcome, "criterion_id": "c1"}])["status"] == "needs-investigation"
