"""Typed graph validation and repository locator safety.

Endpoint matrix (per the reviewed plan; constraint-to-constraint is explicitly
permitted because a constraint is a requirement), acyclic decomposition
(``refines`` + ``derived_from`` combined), acyclic ``supersedes`` lineage, no
self/duplicate logical edges, and once-canonical symmetric ``conflicts_with``
records. Allowed semantic cycles (`contributes_to`, `depends_on`) are legal
data; reports traverse them with visited sets, never truncating falsely.
"""

import os

from . import schema

REQUIREMENT = "requirement"

# type -> (allowed source kinds, allowed target kinds). Artifact kinds are
# denoted directly; requirements use the REQUIREMENT sentinel and constrains
# narrows its source by classification.
ENDPOINT_MATRIX = {
    "refines": ({REQUIREMENT}, {REQUIREMENT}),
    "derived_from": ({REQUIREMENT}, {REQUIREMENT}),
    "contributes_to": ({REQUIREMENT}, {REQUIREMENT}),
    "depends_on": ({REQUIREMENT}, {REQUIREMENT}),
    "conflicts_with": ({REQUIREMENT}, {REQUIREMENT}),
    "supersedes": ({REQUIREMENT}, {REQUIREMENT}),
    "constrains": ({"constraint"}, {REQUIREMENT, "design", "implementation_spec"}),
    "addresses": ({"design", "implementation_spec"}, {REQUIREMENT}),
    "realizes": ({"implementation_spec"}, {"design"}),
    "implements": ({"code"}, {"implementation_spec"}),
    "verifies": ({"test"}, {REQUIREMENT}),
    "exercises": ({"test"}, {"code"}),
    "supports": ({"evidence"}, {REQUIREMENT, "test"}),
}

DECOMPOSITION_TYPES = ("refines", "derived_from")
SUPERSSESSION_TYPE = "supersedes"


def _record_with_kind(ledger, endpoint_id):
    if endpoint_id in ledger["requirements"]:
        record = ledger["requirements"][endpoint_id]
        return record, REQUIREMENT
    artifact = ledger["artifacts"].get(endpoint_id)
    if artifact is not None:
        return artifact, artifact["kind"]
    schema.fail("broken-reference",
                f"Endpoint {endpoint_id!r} references unknown requirement/artifact.",
                {"id": endpoint_id})


def matches_candidates(kind, record, candidates):
    """Decide whether an endpoint kind (with record) satisfies candidates.

    ``REQUIREMENT`` accepts any requirement; ``"constraint"`` additionally
    requires the classification-constraint narrowing.
    """
    if kind == REQUIREMENT:
        if REQUIREMENT in candidates:
            return True
        return "constraint" in candidates and record["classification"] == "constraint"
    return kind in candidates


def check_endpoint(ledger, relation):
    rtype = relation["type"]
    if rtype not in ENDPOINT_MATRIX:
        schema.fail("invalid-record",
                    f"Relation {relation['id']} has unknown type {rtype!r}.",
                    {"relation_id": relation["id"], "type": rtype})
    sources, targets = ENDPOINT_MATRIX[rtype]
    source_record, source_kind = _record_with_kind(ledger, relation["source"])
    target_record, target_kind = _record_with_kind(ledger, relation["target"])
    if not matches_candidates(source_kind, source_record, sources) or not matches_candidates(
            target_kind, target_record, targets):
        schema.fail(
            "invalid-endpoint",
            f"Relation {relation['id']} of type {rtype!r} forbids "
            f"{source_kind!r} -> {target_kind!r} endpoints.",
            {"relation_id": relation["id"], "type": rtype,
             "source_kind": source_kind, "target_kind": target_kind},
        )


def _active_edges(ledger, types):
    edges = {}
    for relation in ledger["relations"]:
        if relation.get("retracted") or relation["type"] not in types:
            continue
        edges.setdefault(relation["source"], []).append(relation["target"])
    return edges


def _find_cycle(edges):
    state = {}

    def visit(node, path):
        state[node] = "in-stack"
        for neighbor in edges.get(node, ()):
            status = state.get(neighbor)
            if status == "in-stack":
                index = path.index(neighbor) if neighbor in path else 0
                return path[index:] + [neighbor]
            if status is None:
                found = visit(neighbor, path + [neighbor])
                if found:
                    return found
        state[node] = "done"
        return None

    for node in edges:
        if state.get(node) is None:
            cycle = visit(node, [node])
            if cycle:
                return cycle
    return None


def check_acyclic(ledger, types, label):
    cycle = _find_cycle(_active_edges(ledger, types))
    if cycle:
        schema.fail(
            "cycle-relation",
            f"Forbidden directed {label} cycle through "
            f"{' -> '.join(cycle)}.",
            {"cycle_types": list(types), "cycle": cycle},
        )


def check_relation_uniqueness(ledger):
    logical = {}
    conflicts = set()
    for relation in ledger["relations"]:
        edge = (relation["type"], relation["source"], relation["target"])
        if relation.get("retracted"):
            continue
        if relation["type"] == "conflicts_with":
            if (relation["source"], relation["target"]) in conflicts:
                schema.fail("duplicate-relation",
                            f"Symmetric conflict pair already canonical.",
                            {"relation_id": relation["id"]})
            conflicts.add((relation["source"], relation["target"]))
        else:
            if edge in logical:
                schema.fail("duplicate-relation",
                            f"Relation {relation['id']} duplicates logical edge "
                            f"{edge} from relation {logical[edge]}.",
                            {"relation_id": relation["id"], "edge": edge,
                             "duplicate_of": logical[edge]})
            logical[edge] = relation["id"]


def check_canonical_conflicts(ledger):
    for relation in ledger["relations"]:
        if relation.get("retracted") or relation["type"] != "conflicts_with":
            continue
        if relation["source"] >= relation["target"]:
            schema.fail(
                "noncanonical-conflict",
                "conflicts_with relations must be stored once, lexicographically "
                "canonical (source < target).",
                {"relation_id": relation["id"], "source": relation["source"],
                 "target": relation["target"]},
            )


def canonical_conflict_pair(source, target):
    return (source, target) if source < target else (target, source)


def check_self_edge(relation):
    if relation["source"] == relation["target"]:
        schema.fail("self-edge",
                    f"Relation {relation['id']} is a self edge.",
                    {"relation_id": relation["id"]})


def validate_graph(ledger, repo_root):
    """Full graph-level validation of a structurally parsed ledger."""
    for artifact in ledger["artifacts"].values():
        validate_locator(repo_root, artifact["locator"])
    for relation in ledger["relations"]:
        check_self_edge(relation)
        check_endpoint(ledger, relation)
    check_relation_uniqueness(ledger)
    check_canonical_conflicts(ledger)
    check_acyclic(ledger, DECOMPOSITION_TYPES, "refinement/derivation decomposition")
    check_acyclic(ledger, (SUPERSSESSION_TYPE,), "supersession")


def _within(root, candidate):
    if candidate == root:
        return True
    try:
        relative = os.path.relpath(candidate, root)
    except ValueError:  # pragma: no cover - different drives on Windows
        return False
    return not relative.startswith(".." + os.sep) and relative != ".."


def validate_locator(repo_root, locator):
    """Validate a repository-relative artifact locator, symlinks included.

    Rejects absolute paths, Windows drive letters, traversal components,
    traversal through symlinks leaving the repository root, and (when the
    target exists) non-file artifacts. Nonexistent locators remain valid:
    they can refer to planned artifacts; existence alone never proves
    correctness or coverage.
    """
    error = schema.RequirementsError(
        "invalid-locator", "Artifact locator must be a safe repository-relative path.",
        {"locator": locator if isinstance(locator, str) else None},
    )
    if not isinstance(locator, str) or not locator.strip():
        raise error
    if "\x00" in locator or "\\" in locator:
        raise error
    if locator.startswith("/") or os.path.isabs(locator):
        raise error
    if len(locator) >= 2 and locator[1] == ":":
        raise error
    parts = [part for part in locator.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise error
    root = os.path.realpath(os.fspath(repo_root))
    current = root
    for part in parts:
        current = os.path.join(current, part)
        real = os.path.realpath(current)
        if not _within(root, real):
            raise schema.RequirementsError(
                "invalid-locator",
                f"Artifact locator {locator!r} escapes the repository root through "
                f"{part!r}.",
                {"locator": locator, "component": part},
            )
    if os.path.lexists(current) and not os.path.isfile(os.path.realpath(current)):
        raise schema.RequirementsError(
            "invalid-locator",
            f"Artifact locator {locator!r} must resolve to a file, not a directory "
            "or special node.",
            {"locator": locator},
        )
    return tuple(parts)
