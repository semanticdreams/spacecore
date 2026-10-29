"""Read-only methodology graph reports; reachability is never satisfaction.

Query arguments (unknown fields are errors): search(text, classification?, kind?);
trace(id, direction=forward|backward|both, max_depth=32, max_paths=1000);
impact(id, max_depth=32, max_paths=1000); coverage(scope?);
reconciliation-context(scope, max_depth=32, max_paths=1000);
readiness(scope, material_criteria, material_constraints, max_depth=32, max_paths=1000).
Material criteria are {requirement_id, criterion_id} pairs; scope is a nonempty
ID list. Empty material lists explicitly declare no selected material items.

Trace follows stored orientation or its inverse. Impact follows both directions
with relation-specific reasons: purpose impact is potential, prerequisites affect
dependents, constraints require rechecking, and artifact chains carry potential
solution/governing-requirement impact. No path proves behavioral dependency.
All simple paths are retained within explicit bounds; revisiting an ancestor via
a different edge diagnoses a cycle, not truncation or an invented inverse edge.

Readiness constraint applicability is narrower than impact: scope-self, or one
constrains edge followed only by inverse refines/addresses/realizes/implements,
all explicit, stopping at the supplied scope. Origin (derived_from), repeated
constrains and every other relation are context, not transitive authority.
Bounds apply separately to each constraint's applicability/context traversal.
"""

from collections import deque

from . import RequirementsError, schema
from .evidence import criteria_latest, _locator_state

OPS = ("search", "trace", "impact", "coverage", "reconciliation-context", "readiness")
DEFAULT_DEPTH = 32
DEFAULT_PATHS = 1000
CONFIDENCE = {"explicit": 0, "inferred": 1, "uncertain": 2}
PURPOSE = {"refines", "derived_from", "contributes_to"}


def invalid(message):
    raise RequirementsError("invalid-op-args", message, {})


def records(ledger):
    return {**ledger["requirements"], **ledger["artifacts"]}


def active_relations(ledger):
    return sorted((r for r in ledger["relations"] if not r.get("retracted")),
                  key=lambda r: (r["type"], r["source"], r["target"], r["id"]))


def _keys(args, required=(), optional=()):
    if not isinstance(args, dict) or set(args) - set(required) - set(optional) or set(required) - set(args):
        invalid(f"Expected required arguments {required} and optional arguments {optional}.")


def _id(ledger, value):
    if not isinstance(value, str) or not schema.is_uuid_id(value):
        invalid("Expected a canonical requirement or artifact ID.")
    if value not in records(ledger):
        raise RequirementsError("not-found", f"No record {value!r}.", {"id": value})
    return value


def _scope(ledger, value):
    if not isinstance(value, list) or not value:
        invalid("scope must be a nonempty list of record IDs.")
    result = [_id(ledger, item) for item in value]
    if len(set(result)) != len(result):
        invalid("scope must not contain duplicate IDs.")
    return sorted(result)


def _bounds(args):
    depth, paths = args.get("max_depth", DEFAULT_DEPTH), args.get("max_paths", DEFAULT_PATHS)
    for name, value, maximum in (("max_depth", depth, 1000), ("max_paths", paths, 10000)):
        if type(value) is not int or not 1 <= value <= maximum:
            invalid(f"{name} must be an integer between 1 and {maximum}.")
    return depth, paths


def _metadata(ids, depth=None, paths=None):
    return {"scope": {"ids": sorted(ids), "unregistered_history": "outside-semantic-coverage"},
            "bounds": {"max_depth": depth, "max_paths": paths},
            "unknowns": ["Unlinked behavior and unregistered history are not a complete blast radius."],
            "truncated": False}


def _reason(kind, direction, impact):
    if not impact:
        return "stored-orientation" if direction == "forward" else "inverse-trace"
    if kind in PURPOSE:
        return "potential-purpose-impact" if direction == "forward" else "potential-obligation-impact"
    if kind == "depends_on":
        return "prerequisite-recheck" if direction == "forward" else "potential-dependent-impact"
    if kind == "constrains":
        return "constraint-target-impact" if direction == "forward" else "constraint-recheck"
    if kind == "conflicts_with":
        return "conflict-reconciliation"
    if kind == "supersedes":
        return "superseded-dependents-reconciliation"
    return "potential-governing-requirement-impact" if direction == "forward" else "potential-solution-impact"


def traverse(ledger, starts, direction="both", max_depth=DEFAULT_DEPTH,
             max_paths=DEFAULT_PATHS, impact=False, relations=None,
             stop_at=(), step_rule=None):
    edges = active_relations(ledger) if relations is None else relations
    adjacency = {}
    for edge in edges:
        for way, source, target in (("forward", edge["source"], edge["target"]),
                                    ("backward", edge["target"], edge["source"])):
            if direction in (way, "both"):
                adjacency.setdefault(source, []).append((target, edge, way))
    if stop_at:
        for neighbors in adjacency.values():
            # A known direct explicit witness must not be displaced by unrelated
            # branches or candidates when the caller requests a small path bound.
            neighbors.sort(key=lambda item: (item[0] not in stop_at,
                                             CONFIDENCE[item[1]["confidence"]]))
    queue = deque(([start], [], "explicit") for start in sorted(starts))
    result = _metadata(starts, max_depth, max_paths)
    result.update(nodes=sorted(starts), paths=[], cycle_diagnostics=[])
    nodes, cycles = set(starts), set()
    while queue:
        chain, steps, confidence = queue.popleft()
        if chain[-1] in stop_at:
            continue
        for target, edge, way in adjacency.get(chain[-1], []):
            if step_rule is not None and not step_rule(steps, edge, way):
                continue
            if any(step["relation"]["id"] == edge["id"] for step in steps):
                continue  # traversing the same stored edge backwards is not a cycle
            step = {"relation": edge, "direction": way,
                    "reason": _reason(edge["type"], way, impact)}
            if target in chain:
                key = tuple(s["relation"]["id"] for s in steps + [step])
                if key not in cycles:
                    cycles.add(key)
                    result["cycle_diagnostics"].append({"nodes": chain + [target],
                                                        "steps": steps + [step]})
                continue
            if len(steps) >= max_depth or len(result["paths"]) >= max_paths:
                result["truncated"] = True
                continue
            next_confidence = max((confidence, edge["confidence"]), key=CONFIDENCE.get)
            path = {"nodes": chain + [target], "steps": steps + [step],
                    "confidence": next_confidence, "potential": impact}
            result["paths"].append(path)
            nodes.add(target)
            queue.append((path["nodes"], path["steps"], next_confidence))
    result["nodes"] = sorted(nodes)
    if result["truncated"]:
        result["unknowns"].append("Traversal bounds omitted additional paths.")
    if any(p["confidence"] != "explicit" for p in result["paths"]):
        result["unknowns"].append("Candidate links require agent investigation; they establish no authority or clearance.")
    if impact:
        result["shared_locator_impacts"] = [
            {"id": aid, "shared_with": source, "locator": artifact["locator"],
             "confidence": "uncertain", "reason": "shared-locator-potential-impact"}
            for source in sorted(nodes & ledger["artifacts"].keys())
            for aid, artifact in sorted(ledger["artifacts"].items())
            if aid != source and artifact["locator"] == ledger["artifacts"][source]["locator"]]
        result["unknowns"].append("Traceability and shared locators indicate potential impact, not proven behavioral dependency.")
    return result


def _latest_assessment(ledger, rid):
    entries = [a for a in ledger["assessments"] if a["requirement_id"] == rid
               and a["requirement_revision"] == ledger["requirements"][rid]["revision"]]
    return entries[-1] if entries else None


def _design_justification(edges, aid):
    direct = [r for r in edges if r["source"] == aid and r["type"] == "addresses"]
    paths = [{"steps": [{"relation": r, "direction": "forward", "reason": "design-justification"}],
              "confidence": r["confidence"]} for r in direct]
    for realization in edges:
        if realization["type"] != "realizes" or realization["target"] != aid:
            continue
        for address in edges:
            if address["type"] == "addresses" and address["source"] == realization["source"]:
                paths.append({"steps": [
                    {"relation": realization, "direction": "backward", "reason": "realized-design-justification"},
                    {"relation": address, "direction": "forward", "reason": "requirement-justification"}],
                    "confidence": max((realization["confidence"], address["confidence"]), key=CONFIDENCE.get)})
    return paths


def coverage(ledger, root, ids):
    result = _metadata(ids, DEFAULT_DEPTH, DEFAULT_PATHS)
    result.update(requirements={}, artifacts={}, findings=[])
    edges = active_relations(ledger)
    result["relations"] = [r for r in edges if r["source"] in ids or r["target"] in ids]
    def finding(code, rid, reason, **extra):
        result["findings"].append({"code": code, "id": rid, "reason": reason, **extra})
    # A purpose has design trace via incoming decomposition/contribution, then
    # incoming addresses. Restrict this search: conflicts/dependencies aren't design justification.
    justification = [r for r in edges if r["type"] in PURPOSE | {"addresses", "realizes"}]
    for rid in sorted(ids):
        if rid not in ledger["requirements"]:
            continue
        req = ledger["requirements"][rid]
        trace = traverse(ledger, [rid], direction="backward", relations=justification)
        design_paths = [p for p in trace["paths"] if ledger["artifacts"].get(p["nodes"][-1], {}).get("kind") == "design"]
        # Specs address requirements too; follow realizes to their design without
        # letting arbitrary artifact reachability establish design justification.
        for path in list(trace["paths"]):
            end = path["nodes"][-1]
            for edge in justification:
                if (edge["type"] == "realizes" and edge["source"] == end
                        and edge["target"] not in path["nodes"]):
                    if len(path["steps"]) >= DEFAULT_DEPTH or len(design_paths) >= DEFAULT_PATHS:
                        trace["truncated"] = True
                        continue
                    design_paths.append({"nodes": path["nodes"] + [edge["target"]],
                        "steps": path["steps"] + [{"relation": edge, "direction": "forward", "reason": "design-justification"}],
                        "confidence": max((path["confidence"], edge["confidence"]), key=CONFIDENCE.get)})
        latest = criteria_latest(ledger, rid, root)
        assessment = _latest_assessment(ledger, rid)
        result["requirements"][rid] = {"design_trace": design_paths,
            "assessment": assessment, "criteria_latest": latest,
            "trace_truncated": trace["truncated"], "trace_bounds": trace["bounds"]}
        if trace["truncated"]:
            result["truncated"] = True
        explicit = any(p["confidence"] == "explicit" for p in design_paths)
        if req["classification"] in ("behavior", "capability") and not explicit:
            finding("missing-explicit-design", rid, "Unknown/unlinked explicit design justification; not proof of absent behavior.")
        if req["classification"] in ("behavior", "capability") and not any(r["source"] == rid and r["type"] in PURPOSE for r in edges):
            finding("orphaned-refinement", rid, "No recorded refinement, derivation or contribution to purpose.")
        if req["classification"] in ("goal", "outcome") and (not latest or not all(
                v["result"] == "passed" and v["currency"] == "current" for v in latest.values())):
            finding("unsupported-outcome", rid, "Design trace does not demonstrate outcome achievement.")
        if req["classification"] == "constraint" and (not assessment or assessment["state"] != "satisfied"):
            finding("unaddressed-constraint", rid, "No current explicit satisfied constraint assessment.")
        if not any(r["target"] == rid and r["type"] in ("verifies", "supports") for r in edges):
            finding("missing-linked-evidence", rid, "No registered test/evidence trace; observations are reported separately.")
        for cid, observation in latest.items():
            if observation["currency"] == "stale":
                finding("stale-evidence", rid, "Latest observation has stale revision/content dependencies.", criterion_id=cid)
        for edge in edges:
            if edge["source"] == rid and edge["type"] == "depends_on" and ledger["requirements"][edge["target"]]["lifecycle"] == "superseded":
                finding("superseded-dependency", rid, "Dependency requires reconciliation with supersession lineage.", relation=edge)
    for aid in sorted(set(ids) & ledger["artifacts"].keys()):
        artifact = ledger["artifacts"][aid]
        state = _locator_state(artifact["locator"], artifact.get("content_digest"), root)
        if not artifact.get("content_digest") and state == "stale":
            state = "unknown"
        justification_paths = _design_justification(edges, aid) if artifact["kind"] == "design" else []
        result["artifacts"][aid] = {"currency": "current" if state == "fresh" else state,
                                     "justification_paths": justification_paths}
        if state != "fresh":
            finding("stale-artifact" if state == "stale" else "unknown-artifact", aid, "Actual content differs or content identity is unavailable.")
        kind = artifact["kind"]
        if kind == "design" and not any(p["confidence"] == "explicit" for p in justification_paths):
            finding("design-without-justification", aid, "Registered design lacks explicit requirement justification; unregistered legacy is outside scope.")
        needed = {"design": "realizes", "implementation_spec": "implements", "code": "exercises", "test": "supports"}.get(kind)
        if needed and not any(r["target"] == aid and r["type"] == needed for r in edges):
            finding("missing-implementation" if kind in ("design", "implementation_spec") else "missing-linked-evidence", aid, f"No incoming {needed} trace.")
    return result


def _constraint_step(steps, edge, direction):
    if not steps:
        return edge["type"] == "constrains" and direction == "forward"
    return (edge["type"] in {"refines", "addresses", "realizes", "implements"}
            and direction == "backward")


def _constraint_applicability(ledger, rid, scope, depth, paths):
    if rid in scope:
        return {"status": "established", "reason": "scope-self",
                "paths": [{"nodes": [rid], "steps": [], "confidence": "explicit"}],
                "context_paths": [], "context_shared_locator_impacts": [],
                "cycle_diagnostics": [], "truncated": False}
    walk = traverse(ledger, [rid], max_depth=depth, max_paths=paths,
                    stop_at=scope, step_rule=_constraint_step)
    witnesses = [p for p in walk["paths"] if p["nodes"][-1] in scope]
    for path in witnesses:
        for step in path["steps"]:
            step["reason"] = ("constrained-target" if step["direction"] == "forward"
                              else "downward-constraint-applicability")
    established = any(p["confidence"] == "explicit" for p in witnesses)
    # Broad context is deliberately separate: an explicit context path is not an
    # applicability witness. It can explain excluded routes/cycles, never block.
    context = (None if established else traverse(
        ledger, [rid], max_depth=depth, max_paths=paths, stop_at=scope, impact=True))
    context_paths = ([p for p in context["paths"] if p["nodes"][-1] in scope]
                     if context else [])
    truncated = walk["truncated"] or bool(context and context["truncated"])
    reason = ("explicit-downward-witness" if established else
              "candidate-applicability" if witnesses else
              "applicability-bounds-exceeded" if truncated else
              "excluded-context-route" if context_paths else
              "shared-locator-context-only" if context and context["shared_locator_impacts"] else
              "unlinked-applicability")
    return {"status": "established" if established else "unknown", "reason": reason,
            "paths": witnesses, "context_paths": context_paths,
            "context_shared_locator_impacts": context["shared_locator_impacts"] if context else [],
            "cycle_diagnostics": context["cycle_diagnostics"] if context else walk["cycle_diagnostics"],
            "truncated": truncated}


def readiness(ledger, root, args):
    _keys(args, ("scope", "material_criteria", "material_constraints"),
          ("max_depth", "max_paths"))
    depth, paths = _bounds(args)
    ids = _scope(ledger, args["scope"])
    pairs = args["material_criteria"]
    if not isinstance(pairs, list) or not isinstance(args["material_constraints"], list):
        invalid("material_criteria and material_constraints must be lists.")
    constraints = [_id(ledger, rid) for rid in args["material_constraints"]]
    if len(set(constraints)) != len(constraints):
        invalid("Duplicate material constraints.")
    selected, seen = [], set()
    for pair in pairs:
        _keys(pair, ("requirement_id", "criterion_id"))
        rid = _id(ledger, pair["requirement_id"])
        cid = pair["criterion_id"]
        req = ledger["requirements"].get(rid)
        if not isinstance(cid, str) or not req or cid not in {c["id"] for c in req["acceptance_criteria"]}:
            invalid("Material criterion must name a current requirement criterion.")
        if (rid, cid) in seen:
            invalid("Duplicate material criterion.")
        seen.add((rid, cid))
        selected.append((rid, cid))
    edges = active_relations(ledger)
    for rid in constraints:
        req = ledger["requirements"].get(rid)
        if not req or req["classification"] != "constraint":
            invalid("material_constraints must name constraint requirements.")
    discovered = {r["source"] for r in edges if r["type"] == "constrains"
                  and r["target"] in ids and r["confidence"] == "explicit"}
    criterion_constraints = {rid for rid, _ in selected
                            if ledger["requirements"][rid]["classification"] == "constraint"}
    considered = sorted(set(constraints) | discovered | criterion_constraints)
    applicability = {rid: _constraint_applicability(ledger, rid, set(ids), depth, paths)
                     for rid in considered}
    applicable = [rid for rid in considered if applicability[rid]["status"] == "established"]
    selected = [(rid, cid) for rid, cid in selected
                if rid not in criterion_constraints or rid in applicable]
    affected = set(ids) | set(applicable) | {rid for rid, _ in selected}
    report = _metadata(ids, depth, paths)
    report.update(blockers=[], dispositions=[], material_criteria=pairs,
                  material_constraints=applicable, grants_permissions=False,
                  requested_material_constraints=sorted(constraints),
                  constraint_applicability=applicability,
                  limitation="Not test, independent-review, Git permission or merge approval.")
    context_ids = affected | set(constraints)
    report["relations"] = [r for r in edges if r["source"] in context_ids or r["target"] in context_ids]
    unknowns = [{"reason": "constraint-applicability-unknown", "id": rid,
                 "applicability_reason": applicability[rid]["reason"]}
                for rid in considered if applicability[rid]["status"] == "unknown"]
    report["truncated"] = any(item["truncated"] for item in applicability.values())
    if report["truncated"]:
        unknowns.append({"reason": "constraint-applicability-paths-truncated"})
    for edge in edges:
        if edge["source"] not in affected and edge["target"] not in affected:
            continue
        if edge["confidence"] != "explicit":
            unknowns.append({"reason": "candidate-link-needs-investigation", "relation": edge})
        elif edge["type"] == "conflicts_with":
            dispositions = [d for d in ledger["conflict_dispositions"] if d["relation_id"] == edge["id"]]
            if dispositions:
                report["dispositions"].append(dispositions[-1])
            else:
                report["blockers"].append({"reason": "unresolved-material-conflict", "relation_id": edge["id"], "relation": edge})
    for rid in applicable:
        req = ledger["requirements"][rid]
        assessment = _latest_assessment(ledger, rid)
        if assessment and assessment["state"] != "satisfied":
            report["blockers"].append({"reason": "unaddressed-material-constraint", "id": rid, "assessment": assessment})
        elif not assessment:
            unknowns.append({"reason": "constraint-assessment-unknown", "id": rid})
        selected.extend((rid, criterion["id"]) for criterion in req["acceptance_criteria"])
    for rid, cid in sorted(set(selected)):
        observation = criteria_latest(ledger, rid, root)[cid]
        item = {"id": rid, "criterion_id": cid, "observation": observation}
        if observation["result"] == "failed" and observation["currency"] == "current":
            report["blockers"].append({"reason": "current-negative-observation", **item})
        elif observation["result"] != "passed" or observation["currency"] != "current":
            unknowns.append({"reason": "material-verification-unresolved", **item})
    report["unknowns"] = unknowns
    report["status"] = "blocked" if report["blockers"] else "needs-investigation" if unknowns else "no-recorded-blockers"
    return report


def report(ledger, root, op, args):
    if op == "readiness":
        return readiness(ledger, root, args)
    if op in ("trace", "impact"):
        _keys(args, ("id",), ("direction", "max_depth", "max_paths") if op == "trace" else ("max_depth", "max_paths"))
        direction = args.get("direction", "forward" if op == "trace" else "both")
        if not isinstance(direction, str) or direction not in ("forward", "backward", "both"):
            invalid("direction must be forward, backward or both.")
        depth, paths = _bounds(args)
        return traverse(ledger, [_id(ledger, args["id"])], direction, depth, paths, op == "impact")
    if op == "coverage":
        _keys(args, (), ("scope",))
        ids = _scope(ledger, args["scope"]) if "scope" in args else sorted(records(ledger))
        return coverage(ledger, root, ids)
    if op == "reconciliation-context":
        _keys(args, ("scope",), ("max_depth", "max_paths"))
        ids = _scope(ledger, args["scope"])
        depth, paths = _bounds(args)
        impact = traverse(ledger, ids, "both", depth, paths, True)
        selected = set(impact["nodes"])
        result = _metadata(ids, depth, paths)
        result.update(records={rid: records(ledger)[rid] for rid in sorted(selected)},
            relations=[r for r in active_relations(ledger) if r["source"] in selected and r["target"] in selected],
            impact=impact, coverage=coverage(ledger, root, sorted(selected)),
            assessments=[a for a in ledger["assessments"] if a["requirement_id"] in selected],
            verifications=[v for v in ledger["verifications"] if v["requirement_id"] in selected],
            conflict_dispositions=[d for d in ledger["conflict_dispositions"] if any(r["id"] == d["relation_id"] for r in active_relations(ledger) if r["source"] in selected or r["target"] in selected)])
        result["truncated"] = impact["truncated"] or result["coverage"]["truncated"]
        result["unknowns"] = impact["unknowns"]
        return result
    _keys(args, ("text",), ("classification", "kind"))
    text = args["text"]
    if not isinstance(text, str) or not text.strip():
        invalid("search text must be a nonempty literal string.")
    for key, allowed in (("classification", schema.CLASSIFICATIONS), ("kind", schema.ARTIFACT_KINDS)):
        if key in args and (not isinstance(args[key], str) or args[key] not in allowed):
            invalid(f"Invalid search {key}.")
    if "classification" in args and "kind" in args:
        invalid("Search cannot combine requirement classification and artifact kind.")
    matches = [rid for rid, record in sorted(records(ledger).items())
               if all(record.get(k) == args[k] for k in ("classification", "kind") if k in args)
               and any(text.casefold() in str(record.get(k, "")).casefold() for k in ("id", "statement", "rationale", "title", "locator"))]
    result = _metadata(matches)
    result.update(matches=matches, semantic_equivalence=False, confidence="literal-only",
                  reason="Case-insensitive literal substring match; no semantic inference.")
    return result
