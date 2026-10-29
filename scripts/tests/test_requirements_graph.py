"""Behavioral graph reports over real, validated ledgers (not Space graphs)."""

import hashlib
import uuid

import pytest

from helpers_requirements import (
    base_ledger, make_artifact, make_relation, make_requirement, requirements_lib,
    run_cli, write_ledger,
)


class GraphCase:
    def __init__(self, root):
        self.root = root
        self.ledger = base_ledger()

    def req(self, name, **kwargs):
        rid = "REQ-" + str(uuid.uuid5(uuid.NAMESPACE_URL, name))
        self.ledger["requirements"][rid] = make_requirement(rid, **kwargs)
        return rid

    def art(self, name, kind, **kwargs):
        aid = "ART-" + str(uuid.uuid5(uuid.NAMESPACE_URL, name))
        locator = kwargs.pop("locator", name + ".md")
        path = self.root / locator
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
        self.ledger["artifacts"][aid] = make_artifact(
            aid, kind, locator=locator, content_digest=hashlib.sha256(name.encode()).hexdigest(),
            **kwargs)
        return aid

    def edge(self, kind, source, target, **kwargs):
        if kind == "conflicts_with":
            source, target = sorted((source, target))
        edge = make_relation(rtype=kind, source=source, target=target, **kwargs)
        self.ledger["relations"].append(edge)
        return edge

    def query(self, op, **args):
        write_ledger(self.root, self.ledger)
        return requirements_lib().query(self.root, {"op": op, "args": args})["result"]


@pytest.fixture
def graph_case(tmp_path):
    return GraphCase(tmp_path)


ENDPOINTS = {
    "refines": (None, None), "derived_from": (None, None),
    "contributes_to": (None, None), "depends_on": (None, None),
    "conflicts_with": (None, None), "supersedes": (None, None),
    "constrains": ("constraint", "design"), "addresses": ("design", None),
    "realizes": ("implementation_spec", "design"),
    "implements": ("code", "implementation_spec"), "verifies": ("test", None),
    "exercises": ("test", "code"), "supports": ("evidence", "test"),
}


@pytest.mark.parametrize("kind", ENDPOINTS)
@pytest.mark.parametrize("direction", ["forward", "backward"])
def test_every_relation_both_directions_preserves_original(graph_case, kind, direction):
    c = graph_case
    def endpoint(name, typ):
        return (c.req(name, classification="constraint") if typ == "constraint"
                else c.req(name) if typ is None else c.art(name, typ))
    source, target = [endpoint(name, typ) for name, typ in zip(("a", "b"), ENDPOINTS[kind])]
    if kind == "supersedes":
        old = c.ledger["requirements"][target]
        old["lifecycle"] = "superseded"
        old["history"] = [{"kind": "transition", "from_lifecycle": "proposed",
                           "to_lifecycle": "superseded", "reason": "replacement",
                           "authority": "explicit intent", "actor": "test", "date": "2026-10-29"}]
    edge = c.edge(kind, source, target, confidence="inferred")
    start, end = ((edge["source"], edge["target"]) if direction == "forward"
                  else (edge["target"], edge["source"]))
    report = c.query("trace", id=start, direction=direction)
    assert end in report["nodes"]
    step = report["paths"][0]["steps"][0]
    assert step["relation"] == edge
    assert step["direction"] == direction
    assert step["reason"]
    assert report["paths"][0]["confidence"] == "inferred"
    assert report["truncated"] is False


def test_allowed_cycle_is_not_truncation_and_shared_paths_remain(graph_case):
    c = graph_case
    a, b, d, e = [c.req(x) for x in "abde"]
    c.edge("depends_on", a, b, confidence="uncertain")
    c.edge("depends_on", b, a)
    c.edge("depends_on", a, d)
    c.edge("depends_on", b, e)
    c.edge("depends_on", d, e)
    report = c.query("trace", id=a, direction="forward")
    assert report["cycle_diagnostics"]
    assert not report["truncated"]
    assert len([p for p in report["paths"] if p["nodes"][-1] == e]) == 2
    assert {p["confidence"] for p in report["paths"] if p["nodes"][-1] == e} == {"explicit", "uncertain"}


def test_only_actual_bounds_truncate(graph_case):
    c = graph_case
    a, b, d = [c.req(x) for x in "abd"]
    c.edge("depends_on", a, b)
    c.edge("depends_on", b, d)
    assert c.query("trace", id=a, max_depth=1)["truncated"]
    assert not c.query("trace", id=a, max_depth=2)["truncated"]
    assert c.query("trace", id=a, max_paths=1)["truncated"]
    assert not c.query("trace", id=a, max_paths=2)["truncated"]


def test_impact_up_down_artifact_chains_and_shared_locator(graph_case):
    c = graph_case
    goal = c.req("goal", classification="goal")
    child, prerequisite, constraint = c.req("child"), c.req("prereq"), c.req("constraint", classification="constraint")
    design = c.art("design", "design")
    spec = c.art("spec", "implementation_spec")
    code = c.art("code", "code", locator="shared.py")
    other = c.art("other", "code", locator="shared.py")
    test = c.art("test", "test")
    c.edge("refines", child, goal)
    c.edge("depends_on", child, prerequisite)
    c.edge("constrains", constraint, child)
    c.edge("addresses", design, child)
    c.edge("realizes", spec, design)
    c.edge("implements", code, spec)
    c.edge("implements", other, spec)
    c.edge("exercises", test, code)
    report = c.query("impact", id=child)
    assert {goal, design, spec, code, test, constraint} <= set(report["nodes"])
    assert any(s["reason"] == "potential-purpose-impact" for p in report["paths"] for s in p["steps"])
    assert child in c.query("impact", id=goal)["nodes"]
    assert child in c.query("impact", id=prerequisite)["nodes"]
    trace = c.query("trace", id=code, direction="forward")
    assert goal in trace["nodes"]
    shared = c.query("impact", id=code)["shared_locator_impacts"]
    assert any(x["id"] == other and x["confidence"] == "uncertain" for x in shared)


def test_search_is_literal_not_semantic_and_read_only(graph_case):
    c = graph_case
    a = c.req("a", statement="Literal [policy] ZEBRA")
    c.req("b", statement="striped animal")
    report = c.query("search", text="[policy]", classification="capability")
    assert report["matches"] == [a]
    assert report["semantic_equivalence"] is False
    before = {p.relative_to(c.root): p.read_bytes() for p in c.root.rglob("*") if p.is_file()}
    run = run_cli(c.root, "query", request={"op": "coverage", "args": {}})
    assert run.returncode == 0, run.stdout + run.stderr
    assert before == {p.relative_to(c.root): p.read_bytes() for p in c.root.rglob("*") if p.is_file()}


def test_coverage_separates_trace_claims_observations_and_findings(graph_case):
    c = graph_case
    goal = c.req("goal", classification="goal")
    child = c.req("child", classification="behavior")
    orphan = c.req("orphan", classification="behavior")
    constraint = c.req("constraint", classification="constraint")
    design = c.art("design", "design")
    unjustified = c.art("unjustified", "design")
    c.edge("refines", child, goal)
    c.edge("addresses", design, child)
    c.edge("constrains", constraint, child)
    (c.root / "design.md").write_text("changed")
    report = c.query("coverage")
    findings = {(f["code"], f["id"]) for f in report["findings"]}
    assert ("missing-explicit-design", orphan) in findings
    assert ("design-without-justification", unjustified) in findings
    assert ("missing-implementation", design) in findings
    assert ("stale-artifact", design) in findings
    assert ("unaddressed-constraint", constraint) in findings
    assert ("orphaned-refinement", orphan) in findings
    assert ("unsupported-outcome", goal) in findings
    assert report["requirements"][goal]["design_trace"]
    assert report["requirements"][goal]["assessment"] is None
    assert report["requirements"][goal]["criteria_latest"]["c1"]["result"] == "absent"
    assert report["scope"]["unregistered_history"] == "outside-semantic-coverage"


def test_readiness_does_not_block_unrelated_pending_empirical_parent(graph_case):
    c = graph_case
    parent = c.req("parent", classification="outcome", acceptance_criteria=[
        {"id": "c1", "text": "real observation", "applicability": "empirical"}])
    child = c.req("child")
    c.edge("contributes_to", child, parent)
    report = c.query("readiness", scope=[child], material_criteria=[], material_constraints=[])
    assert report["blockers"] == []
    assert report["status"] == "no-recorded-blockers"
    assert report["grants_permissions"] is False
    assert report["scope"]["ids"] == [child]


def test_explicit_conflict_blocks_candidate_conflict_never_clears(graph_case):
    c = graph_case
    a, b, d = [c.req(x) for x in "abd"]
    explicit = c.edge("conflicts_with", a, b)
    c.edge("conflicts_with", a, d, confidence="uncertain")
    args = dict(scope=[a], material_criteria=[], material_constraints=[])
    report = c.query("readiness", **args)
    assert report["status"] == "blocked"
    assert report["blockers"][0]["relation_id"] == explicit["id"]
    c.ledger["conflict_dispositions"].append({"relation_id": explicit["id"],
        "explanation": "scoped resolution", "authority": "explicit intent", "actor": "test", "date": "2026-10-29"})
    report = c.query("readiness", **args)
    assert not report["blockers"]
    assert report["status"] == "needs-investigation"
    assert report["unknowns"]


@pytest.mark.parametrize("args", [
    {}, {"scope": []}, {"scope": "bad", "material_criteria": [], "material_constraints": []},
    {"scope": [], "material_criteria": [], "material_constraints": [], "force": True},
])
def test_readiness_requires_explicit_valid_scope(graph_case, args):
    with pytest.raises(requirements_lib().RequirementsError) as error:
        graph_case.query("readiness", **args)
    assert error.value.code == "invalid-op-args"


@pytest.mark.parametrize("op,args", [
    ([], {}), ("trace", {"id": []}), ("trace", {"id": "bad", "direction": "sideways"}),
    ("trace", {"id": "bad", "max_depth": True}), ("coverage", {"unexpected": 1}),
    ("search", {"text": ""}), ("search", {"text": ".*", "classification": []}),
    ("impact", {"id": "bad", "max_paths": 0}),
])
def test_malformed_queries_are_explicit_not_internal_errors(graph_case, op, args):
    write_ledger(graph_case.root, graph_case.ledger)
    result = run_cli(graph_case.root, "query", request={"op": op, "args": args})
    assert result.returncode == 1
    assert result.error_code() in {"invalid-op", "invalid-op-args"}
    assert not result.stderr


def test_reconciliation_context_exposes_original_records_and_unknowns(graph_case):
    c = graph_case
    a, b = c.req("a"), c.req("b")
    edge = c.edge("depends_on", a, b, confidence="inferred")
    result = c.query("reconciliation-context", scope=[a])
    assert result["records"][a] == c.ledger["requirements"][a]
    assert edge in result["relations"]
    assert result["impact"]["paths"]
    assert result["unknowns"]


def observe(c, rid, result="failed", timestamp="2026-10-29T11:00:00Z"):
    path = c.root / "observation.txt"
    path.write_text("actual measurement")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    c.ledger["verifications"].append({
        "requirement_id": rid, "requirement_revision": 1, "criterion_id": "c1",
        "method": "automated_test", "result": result,
        "procedure": "recorded procedure, never executed", "environment": "test host",
        "observation": "recorded observation", "timestamp": timestamp,
        "evidence_ref": {"locator": "observation.txt"}, "evidence_digest": digest,
        "dependency_digests": {"observation.txt": digest}, "actor": "test"})


def test_latest_negative_blocks_material_criterion_and_stale_is_not_clearance(graph_case):
    c = graph_case
    a = c.req("a")
    observe(c, a, "passed", "2026-10-29T10:00:00Z")
    observe(c, a)
    args = dict(scope=[a], material_criteria=[{"requirement_id": a, "criterion_id": "c1"}], material_constraints=[])
    report = c.query("readiness", **args)
    assert report["status"] == "blocked"
    assert report["blockers"][0]["reason"] == "current-negative-observation"
    assert report["blockers"][0]["observation"]["currency"] == "current"
    (c.root / "observation.txt").write_text("changed evidence")
    report = c.query("readiness", **args)
    assert report["status"] == "needs-investigation"
    assert report["unknowns"][0]["observation"]["currency"] == "stale"
    assert any(f["code"] == "stale-evidence" for f in c.query("coverage")["findings"])


def test_explicit_constraint_negative_blocks_but_candidate_is_only_uncertainty(graph_case):
    c = graph_case
    a = c.req("a")
    constraint = c.req("constraint", classification="constraint")
    edge = c.edge("constrains", constraint, a)
    observe(c, constraint)
    args = dict(scope=[a], material_criteria=[], material_constraints=[constraint])
    assert c.query("readiness", **args)["status"] == "blocked"
    edge["confidence"] = "inferred"
    report = c.query("readiness", **args)
    assert report["blockers"] == []
    assert report["status"] == "needs-investigation"


def test_constraint_assessment_is_independent_from_passing_observation(graph_case):
    c = graph_case
    a = c.req("a")
    constraint = c.req("constraint", classification="constraint")
    c.edge("constrains", constraint, a)
    observe(c, constraint, "passed")
    args = dict(scope=[a], material_criteria=[], material_constraints=[])
    assert c.query("readiness", **args)["status"] == "needs-investigation"
    c.ledger["assessments"].append({"requirement_id": constraint, "requirement_revision": 1,
        "state": "partial", "rationale": "Known violation remains", "actor": "test", "date": "2026-10-29",
        "source_refs": [{"locator": "observation.txt"}]})
    assert c.query("readiness", **args)["status"] == "blocked"


def test_superseded_dependencies_reported_and_impact_reaches_old_dependents(graph_case):
    c = graph_case
    new, old, dependent = [c.req(x) for x in ("new", "old", "dependent")]
    record = c.ledger["requirements"][old]
    record["lifecycle"] = "superseded"
    record["history"] = [{"kind": "transition", "from_lifecycle": "proposed", "to_lifecycle": "superseded",
        "reason": "replacement", "authority": "explicit intent", "actor": "test", "date": "2026-10-29"}]
    c.edge("supersedes", new, old)
    edge = c.edge("depends_on", dependent, old)
    report = c.query("coverage")
    assert any(f["code"] == "superseded-dependency" and f["relation"] == edge for f in report["findings"])
    assert dependent in c.query("impact", id=new)["nodes"]


def test_indirect_spec_design_justification_is_not_reported_unjustified(graph_case):
    c = graph_case
    req = c.req("req")
    design, spec = c.art("design", "design"), c.art("spec", "implementation_spec")
    c.edge("realizes", spec, design)
    c.edge("addresses", spec, req)
    report = c.query("coverage")
    assert report["requirements"][req]["design_trace"]
    assert not any(f["code"] == "design-without-justification" and f["id"] == design for f in report["findings"])


def test_coverage_does_not_invent_a_repeated_inverse_realization_path(graph_case):
    c = graph_case
    req = c.req("req")
    design, spec = c.art("design", "design"), c.art("spec", "implementation_spec")
    c.edge("realizes", spec, design)
    c.edge("addresses", design, req)
    report = c.query("coverage")
    paths = report["requirements"][req]["design_trace"]
    assert len(paths) == 1
    assert all(len(p["nodes"]) == len(set(p["nodes"])) for p in paths)


def test_retracted_links_excluded_and_exact_bound_cycle_not_truncated(graph_case):
    c = graph_case
    a, b, d = [c.req(x) for x in "abd"]
    c.edge("depends_on", a, b)
    c.edge("depends_on", b, a)
    edge = c.edge("depends_on", a, d)
    edge.update(retracted=True, history=[{"action": "retract", "reason": "obsolete",
        "actor": "test", "date": "2026-10-29", "prior": {"confidence": "explicit", "rationale": edge["rationale"]}}])
    report = c.query("trace", id=a, max_depth=1, max_paths=1)
    assert report["cycle_diagnostics"]
    assert not report["truncated"]
    assert d not in report["nodes"]


def test_coverage_missing_files_unknown_not_corruption_and_broken_refs_fail(graph_case):
    c = graph_case
    a = c.req("a")
    design = c.art("design", "design")
    edge = c.edge("addresses", design, a)
    (c.root / "design.md").unlink()
    report = c.query("coverage")
    assert report["artifacts"][design]["currency"] == "unknown"
    edge["target"] = "REQ-" + str(uuid.uuid4())
    with pytest.raises(requirements_lib().RequirementsError) as error:
        c.query("coverage")
    assert error.value.code == "broken-reference"


def readiness_for(c, scope, constraints, **bounds):
    return c.query("readiness", scope=scope, material_criteria=[],
                   material_constraints=constraints, **bounds)


@pytest.mark.parametrize("route", ["design-spec-code", "requirement-refinement-solution", "direct-spec-addresses", "scope-self"])
def test_reconciled_applicability_establishes_only_downward_witnesses(graph_case, route):
    c = graph_case
    constraint = c.req("constraint", classification="constraint")
    observe(c, constraint)
    design, spec = c.art("design", "design"), c.art("spec", "implementation_spec")
    code = c.art("code", "code")
    parent, child = c.req("parent"), c.req("child")
    c.edge("realizes", spec, design)
    c.edge("implements", code, spec)
    if route == "design-spec-code":
        first = c.edge("constrains", constraint, design)
        scope = [code]
        expected = ["constrains", "realizes", "implements"]
    elif route == "requirement-refinement-solution":
        first = c.edge("constrains", constraint, parent)
        c.edge("refines", child, parent)
        c.edge("addresses", design, child)
        scope = [code]
        expected = ["constrains", "refines", "addresses", "realizes", "implements"]
    elif route == "direct-spec-addresses":
        first = c.edge("constrains", constraint, child)
        c.edge("addresses", spec, child)
        scope = [code]
        expected = ["constrains", "addresses", "implements"]
    else:
        first = None
        scope = [constraint]
        expected = []
    report = readiness_for(c, scope, [constraint])
    assert report["requested_material_constraints"] == [constraint]
    assert report["material_constraints"] == [constraint]
    applicability = report["constraint_applicability"][constraint]
    assert applicability["status"] == "established"
    path = applicability["paths"][0]
    assert path["nodes"][0] == constraint and path["nodes"][-1] in scope
    assert path["confidence"] == "explicit"
    assert [s["relation"]["type"] for s in path["steps"]] == expected
    if first:
        assert path["steps"][0]["relation"] == first
        assert [s["direction"] for s in path["steps"]] == ["forward"] + ["backward"] * (len(expected) - 1)
    assert report["status"] == "blocked"
    assert report["blockers"][0]["reason"] == "current-negative-observation"


@pytest.mark.parametrize("route", ["upward", "sibling", "derived_from", "constraint-chain", "contributes_to", "depends_on", "conflicts_with", "supersedes", "verifies", "exercises", "supports", "shared-locator", "unlinked", "retracted"])
def test_reconciled_excluded_routes_are_unknown_never_violation_or_clearance(graph_case, route):
    c = graph_case
    constraint = c.req("constraint", classification="constraint")
    observe(c, constraint)
    parent, child, sibling = [c.req(x) for x in ("parent", "child", "sibling")]
    c.edge("refines", child, parent)
    c.edge("refines", sibling, parent)
    scope = [parent if route == "upward" else sibling if route == "sibling" else child]
    if route in ("upward", "sibling"):
        c.edge("constrains", constraint, child)
    elif route in ("derived_from", "contributes_to", "depends_on", "conflicts_with"):
        c.edge("constrains", constraint, sibling)
        edge = c.edge(route, child, sibling)
        if route == "conflicts_with":
            # Isolate applicability from the independent, scoped conflict blocker.
            c.ledger["conflict_dispositions"].append({"relation_id": edge["id"],
                "explanation": "Resolved scoped conflict", "authority": "explicit intent",
                "actor": "test", "date": "2026-10-29"})
    elif route == "supersedes":
        c.edge("constrains", constraint, sibling)
        c.edge("supersedes", child, sibling)
        record = c.ledger["requirements"][sibling]
        record["lifecycle"] = "superseded"
        record["history"] = [{"kind": "transition", "from_lifecycle": "proposed", "to_lifecycle": "superseded",
            "reason": "replacement", "authority": "explicit intent", "actor": "test", "date": "2026-10-29"}]
    elif route == "constraint-chain":
        other = c.req("other", classification="constraint")
        c.edge("constrains", constraint, other)
        c.edge("constrains", other, child)
    elif route in ("verifies", "exercises", "supports"):
        design = c.art("design", "design")
        spec, code = c.art("spec", "implementation_spec"), c.art("code", "code")
        test, evidence = c.art("test", "test"), c.art("evidence", "evidence")
        c.edge("constrains", constraint, design)
        c.edge("realizes", spec, design)
        c.edge("implements", code, spec)
        c.edge("exercises", test, code)
        c.edge("supports", evidence, test)
        c.edge("verifies", test, child)
        scope = [{"verifies": child, "exercises": test, "supports": evidence}[route]]
    elif route == "shared-locator":
        design = c.art("design", "design", locator="shared.md")
        other = c.art("other", "design", locator="shared.md")
        c.edge("constrains", constraint, design)
        scope = [other]
    elif route == "retracted":
        edge = c.edge("constrains", constraint, child)
        edge.update(retracted=True, history=[{"action": "retract", "reason": "obsolete",
            "actor": "test", "date": "2026-10-29", "prior": {"confidence": "explicit", "rationale": edge["rationale"]}}])
    report = readiness_for(c, scope, [constraint])
    assert constraint not in report["material_constraints"]
    applicability = report["constraint_applicability"][constraint]
    assert applicability["status"] == "unknown"
    assert applicability["reason"]
    if route == "shared-locator":
        shared = applicability["context_shared_locator_impacts"]
        assert any(item["id"] == scope[0] and item["confidence"] == "uncertain"
                   and item["reason"] == "shared-locator-potential-impact" for item in shared)
    if route == "derived_from":
        assert any(step["relation"]["type"] == "derived_from"
                   for path in applicability["context_paths"] for step in path["steps"])
    assert report["status"] == "needs-investigation"
    assert not report["blockers"]
    assert any(u.get("id") == constraint and u["reason"] == "constraint-applicability-unknown" for u in report["unknowns"])


def test_reconciled_candidate_and_explicit_alternatives_preserve_confidence(graph_case):
    c = graph_case
    constraint = c.req("constraint", classification="constraint")
    design, spec, code = c.art("design", "design"), c.art("spec", "implementation_spec"), c.art("code", "code")
    c.edge("constrains", constraint, design)
    c.edge("realizes", spec, design, confidence="inferred")
    c.edge("implements", code, spec)
    report = readiness_for(c, [code], [constraint])
    item = report["constraint_applicability"][constraint]
    assert item["status"] == "unknown"
    assert item["paths"][0]["confidence"] == "inferred"
    direct = c.edge("constrains", constraint, spec)
    report = readiness_for(c, [code], [constraint])
    item = report["constraint_applicability"][constraint]
    assert item["status"] == "established"
    assert {p["confidence"] for p in item["paths"]} == {"explicit", "inferred"}
    assert any(p["steps"][0]["relation"] == direct for p in item["paths"])
    assert report["status"] == "needs-investigation"  # assessment/verification unknown, not inherited satisfaction


def test_reconciled_stops_at_scope_without_searching_siblings_or_false_truncation(graph_case):
    c = graph_case
    constraint = c.req("constraint", classification="constraint")
    parent, child = c.req("parent"), c.req("child")
    c.edge("constrains", constraint, parent)
    c.edge("refines", child, parent)
    report = readiness_for(c, [parent, child], [constraint], max_depth=1, max_paths=1)
    item = report["constraint_applicability"][constraint]
    assert item["status"] == "established"
    assert [p["nodes"] for p in item["paths"]] == [[constraint, parent]]
    assert not item["truncated"] and not report["truncated"]


def test_reconciled_actual_bounds_preserve_unknown_not_clearance(graph_case):
    c = graph_case
    constraint = c.req("constraint", classification="constraint")
    parent, child = c.req("parent"), c.req("child")
    c.edge("constrains", constraint, parent)
    c.edge("refines", child, parent)
    for bounds in ({"max_depth": 1}, {"max_paths": 1}):
        report = readiness_for(c, [child], [constraint], **bounds)
        item = report["constraint_applicability"][constraint]
        assert item["status"] == "unknown"
        assert item["truncated"] and report["truncated"]
        assert report["status"] == "needs-investigation"
        assert not report["blockers"]
    assert readiness_for(c, [child], [constraint], max_depth=2, max_paths=2)["constraint_applicability"][constraint]["status"] == "established"


def test_reconciled_context_cycle_not_false_truncation_and_other_blockers_dominate(graph_case):
    c = graph_case
    constraint = c.req("constraint", classification="constraint")
    a, b, outside = [c.req(x) for x in ("a", "b", "outside")]
    c.edge("constrains", constraint, a)
    c.edge("depends_on", a, b)
    c.edge("depends_on", b, a)
    report = readiness_for(c, [outside], [constraint])
    item = report["constraint_applicability"][constraint]
    assert item["cycle_diagnostics"] and not item["truncated"]
    assert report["status"] == "needs-investigation"
    c.edge("conflicts_with", outside, b)
    report = readiness_for(c, [outside], [constraint])
    assert report["constraint_applicability"][constraint]["status"] == "unknown"
    assert report["status"] == "blocked"
    assert report["blockers"][0]["reason"] == "unresolved-material-conflict"


def test_reconciled_invalid_constraint_ids_still_fail(graph_case):
    c = graph_case
    a = c.req("a")
    for rid in (a, "REQ-" + str(uuid.uuid4())):
        with pytest.raises(requirements_lib().RequirementsError) as error:
            readiness_for(c, [a], [rid])
        assert error.value.code in ("invalid-op-args", "not-found")


def test_reconciled_direct_discovery_not_hidden_by_unrelated_bounded_paths(graph_case):
    c = graph_case
    constraint = c.req("constraint", classification="constraint")
    a, b = sorted([c.req("a"), c.req("b")])
    c.edge("constrains", constraint, a)
    direct = c.edge("constrains", constraint, b)
    observe(c, constraint)
    report = readiness_for(c, [b], [], max_paths=1)
    assert report["requested_material_constraints"] == []
    assert report["material_constraints"] == [constraint]
    assert report["constraint_applicability"][constraint]["paths"][0]["steps"][0]["relation"] == direct
    assert report["status"] == "blocked"


@pytest.mark.parametrize("listed", [True, False])
def test_reconciled_constraint_criteria_cannot_bypass_applicability_gate(graph_case, listed):
    c = graph_case
    constraint, a = c.req("constraint", classification="constraint"), c.req("a")
    observe(c, constraint)
    report = c.query("readiness", scope=[a], material_constraints=[constraint] if listed else [],
        material_criteria=[{"requirement_id": constraint, "criterion_id": "c1"}])
    assert report["constraint_applicability"][constraint]["status"] == "unknown"
    assert not report["blockers"]
    assert report["status"] == "needs-investigation"
    c.edge("constrains", constraint, a)
    assert c.query("readiness", scope=[a], material_constraints=[constraint] if listed else [],
        material_criteria=[{"requirement_id": constraint, "criterion_id": "c1"}])["status"] == "blocked"
