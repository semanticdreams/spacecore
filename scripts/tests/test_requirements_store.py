"""Task 1: strict ledger, mutations and serialized storage.

Covers (per docs/plans/2026-10-29-requirements-driven-engineering.md Task 1):
strict top-level/nested schema, lifecycle/authority/revisions/history, identity
across rename/reclassification, endpoint matrix (including explicit
constraint-to-constraint), canonical conflict, forbidden directed
composite/supersession cycles, allowed cycles, transaction rollback, safe
locators, all CLI errors, two real competing writers, and failed os.replace
byte preservation with lock release.
"""

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

import helpers_requirements as h

FIXED_A = "REQ-00000000-0000-4000-8000-00000000000a"
FIXED_B = "REQ-00000000-0000-4000-8000-00000000000b"


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "design-notes.md").write_text("# design notes\n")
    (root / "docs" / "impl.py").write_text("# implementation stub\n")
    (root / "docs" / "test-suite.py").write_text("# test stubs\n")
    return root


@pytest.fixture
def lib():
    return h.requirements_lib()


@pytest.fixture
def inited(repo):
    h.init_ok(repo)
    return repo


def expect_error(callable_, code):
    with pytest.raises(Exception) as exc:
        callable_()
    assert getattr(exc.value, "code", None) == code, str(exc.value)
    return exc


def op_args(op, **args):
    return {"op": op, "args": args}





def create_result(repo, statement="The tool validates requirements strictly."):
    result = h.run_cli(repo, "apply", request=h.apply_request(h.create_op(statement=statement)))
    assert result.returncode == 0, result.stdout + result.stderr
    return result.json["result"]["ops"][0]["id"]


def register_op(kind, locator="docs/design-notes.md", **extra):
    args = {"kind": kind, "title": f"{kind} artifact", "locator": locator}
    args.update(extra)
    return {"op": "register-artifact", "args": args}


def add_relation_op(rtype, source, target, rationale="Recorded rationale.", **extra):
    args = {
        "type": rtype,
        "source": source,
        "target": target,
        "rationale": rationale,
        "confidence": "explicit",
        "provenance": h.provenance(),
    }
    args.update(extra)
    return {"op": "add-relation", "args": args}


# ---------------------------------------------------------------------------
# Init and read-only behavior
# ---------------------------------------------------------------------------


def test_init_creates_canonical_ledger_with_schema(inited):
    ledger = json.loads(h.read_ledger_bytes(inited))
    assert ledger == h.base_ledger()


def test_init_refuses_existing_ledger(inited):
    result = h.run_cli(inited, "init")
    assert result.returncode != 0
    assert result.error_code() == "already-initialized"


def test_read_queries_never_initialize(inited):
    h.ledger_path(inited).unlink()
    result = h.run_cli(inited, "query", request={"op": "get", "args": {"id": "REQ-x"}})
    assert result.returncode != 0
    assert result.error_code() == "ledger-missing"
    assert not h.ledger_path(inited).exists()

    result = h.run_cli(inited, "validate")
    assert result.returncode != 0
    assert not h.ledger_path(inited).exists()

    result = h.run_cli(inited, "apply", request=h.apply_request(h.create_op()))
    assert result.error_code() == "ledger-missing"
    assert not h.ledger_path(inited).exists()


def test_cli_rejects_unknown_verb_as_error_envelope(repo):
    result = h.run_cli(repo, "explode")
    assert result.returncode != 0
    assert result.error_code() == "invalid-request"


def test_validate_passes_on_valid_ledger_and_writes_nothing(lib, inited):
    before = h.read_ledger_bytes(inited)
    result = h.run_cli(inited, "validate")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.json["status"] == "ok"
    assert h.read_ledger_bytes(inited) == before


def test_validate_fails_on_corrupt_ledger(inited):
    h.write_ledger_bytes(inited, b'{"broken": ')
    result = h.run_cli(inited, "validate")
    assert result.returncode != 0
    assert result.error_code() == "invalid-json"


# ---------------------------------------------------------------------------
# Strict JSON + schema rejection matrix (in-process library loads)
# ---------------------------------------------------------------------------


def test_load_rejects_duplicate_json_key(lib, inited):
    raw = json.dumps(h.base_ledger())
    duplicate = raw.replace('"revision": 0,', '"revision": 0, "revision": 0,', 1)
    h.write_ledger_bytes(inited, duplicate.encode())
    expect_error(lambda: lib.load_ledger(str(inited)), "duplicate-json-key")


def test_load_rejects_nan_literal(lib, inited):
    raw = json.dumps(h.base_ledger()).replace('"revision": 0', '"revision": NaN', 1)
    h.write_ledger_bytes(inited, raw.encode())
    expect_error(lambda: lib.load_ledger(str(inited)), "nonfinite-number")


def test_load_rejects_overflow_float(lib, inited):
    raw = json.dumps(h.base_ledger()).replace('"revision": 0', '"revision": 1e999', 1)
    h.write_ledger_bytes(inited, raw.encode())
    expect_error(lambda: lib.load_ledger(str(inited)), "nonfinite-number")


def test_load_rejects_unknown_top_level_field(lib, inited):
    ledger = h.base_ledger()
    ledger["extra"] = 1
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "unknown-field")


def test_load_rejects_unknown_schema_version(lib, inited):
    for version in (0, "1"):
        ledger = h.base_ledger()
        ledger["schema_version"] = version
        h.write_ledger(inited, ledger)
        expect_error(lambda: lib.load_ledger(str(inited)), "unknown-schema-version")


def test_load_rejects_unknown_requirement_field(lib, inited):
    record = h.make_requirement(status="draft")
    ledger = h.base_ledger()
    ledger["requirements"][record["id"]] = record
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "unknown-field")


def test_load_rejects_unknown_nested_provenance_field(lib, inited):
    record = h.make_requirement()
    record["provenance"]["guess"] = True
    ledger = h.base_ledger()
    ledger["requirements"][record["id"]] = record
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "unknown-field")


def test_load_rejects_unknown_artifact_field(lib, inited):
    record = h.make_artifact(digest="junk")
    ledger = h.base_ledger()
    ledger["artifacts"][record["id"]] = record
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "unknown-field")


def test_load_rejects_invalid_requirement_id(lib, inited):
    record = h.make_requirement(rid="REQ-not-a-uuid")
    ledger = h.base_ledger()
    ledger["requirements"][record["id"]] = record
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")


def test_load_rejects_bad_enum_values(lib, inited):
    for name, value in (("classification", "directive"), ("lifecycle", "done")):
        test = h.base_ledger()
        record = h.make_requirement(**{name: value})
        test["requirements"][record["id"]] = record
        h.write_ledger(inited, test)
        expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")


def test_load_rejects_bad_nested_enum_values(lib, inited):
    for field, value in (
        ("applicability", "manual"),
        ("origin", "guess"),
        ("confidence", "high"),
    ):
        test = h.base_ledger()
        record = h.make_requirement()
        if field == "applicability":
            record["acceptance_criteria"][0]["applicability"] = value
            test["requirements"][record["id"]] = record
        elif field == "origin":
            record["provenance"]["origin"] = value
            test["requirements"][record["id"]] = record
        else:
            other = h.make_requirement()
            relation = h.make_relation(rtype="contributes_to",
                                       source=record["id"], target=other["id"])
            relation["confidence"] = value
            test["relations"].append(relation)
            test["requirements"][record["id"]] = record
            test["requirements"][other["id"]] = other
        h.write_ledger(inited, test)
        expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")


def test_load_rejects_empty_statement(lib, inited):
    record = h.make_requirement(statement="   ")
    ledger = h.base_ledger()
    ledger["requirements"][record["id"]] = record
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")


def test_load_rejects_duplicate_criterion_id(lib, inited):
    record = h.make_requirement()
    record["acceptance_criteria"].append(
        {"id": "c1", "text": "Duplicate identifier.", "applicability": "analytical"}
    )
    ledger = h.base_ledger()
    ledger["requirements"][record["id"]] = record
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")


def test_load_rejects_malformed_history_entry(lib, inited):
    cases = (
        ({"kind": "revision", "from_revision": 3, "to_revision": 2, "reason": "x",
          "actor": "a", "date": "2026-10-29", "prior": {}}, "invalid-record"),
        ({"kind": "transition", "from_lifecycle": "proposed", "reason": "x",
          "actor": "a", "date": "2026-10-29"}, "invalid-record"),
        ({"kind": "transition", "from_lifecycle": "proposed", "to_lifecycle": "active",
          "reason": "x", "actor": "a", "date": "2026-10-29", "extra": 1}, "unknown-field"),
        ({"kind": "revision", "from_revision": 1, "to_revision": 2, "reason": "x",
          "actor": "a", "date": "not-a-date", "prior": {}}, "invalid-record"),
    )
    for entry, code in cases:
        test = h.base_ledger()
        record = h.make_requirement(history=[entry])
        test["requirements"][record["id"]] = record
        h.write_ledger(inited, test)
        expect_error(lambda: lib.load_ledger(str(inited)), code)


def test_load_rejects_evidence_arrays_with_wrong_shape(lib, inited):
    for field in ("assessments", "verifications", "conflict_dispositions"):
        test = h.base_ledger()
        test[field] = "not-a-list"
        h.write_ledger(inited, test)
        expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")


def test_load_rejects_relation_with_broken_reference(lib, inited):
    record = h.make_requirement()
    ledger = h.base_ledger()
    ledger["requirements"][record["id"]] = record
    ledger["relations"].append(
        h.make_relation(rtype="refines", source=record["id"], target=FIXED_A)
    )
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "broken-reference")


def test_load_rejects_invalid_endpoint(lib, inited):
    code_artifact = h.make_artifact(kind="code", locator="docs/impl.py")
    requirement = h.make_requirement()
    ledger = h.base_ledger()
    ledger["artifacts"][code_artifact["id"]] = code_artifact
    ledger["requirements"][requirement["id"]] = requirement
    ledger["relations"].append(
        h.make_relation(rtype="implements", source=requirement["id"],
                        target=code_artifact["id"])
    )
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-endpoint")


def test_load_rejects_nonconstraint_constrains_source(lib, inited):
    source = h.make_requirement(classification="goal")
    target = h.make_requirement()
    ledger = h.base_ledger()
    ledger["requirements"][source["id"]] = source
    ledger["requirements"][target["id"]] = target
    ledger["relations"].append(
        h.make_relation(rtype="constrains", source=source["id"], target=target["id"])
    )
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-endpoint")


def test_load_rejects_self_edge(lib, inited):
    record = h.make_requirement()
    ledger = h.base_ledger()
    ledger["requirements"][record["id"]] = record
    ledger["relations"].append(
        h.make_relation(rtype="refines", source=record["id"], target=record["id"])
    )
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "self-edge")


def test_load_rejects_duplicate_logical_relation(lib, inited):
    a, b = h.make_requirement(), h.make_requirement()
    edge = h.make_relation(rtype="contributes_to", source=a["id"], target=b["id"])
    ledger = h.base_ledger()
    ledger["requirements"][a["id"]] = a
    ledger["requirements"][b["id"]] = b
    ledger["relations"].extend([edge, dict(edge, id=f"REL-{uuid.uuid4()}")])
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "duplicate-relation")


def test_load_rejects_noncanonical_conflict(lib, inited):
    first = h.make_requirement(rid=FIXED_B, statement="May fetch remote assets.")
    second = h.make_requirement(rid=FIXED_A, statement="Must build offline.")
    ledger = h.base_ledger()
    ledger["requirements"][first["id"]] = first
    ledger["requirements"][second["id"]] = second
    ledger["relations"].append(
        h.make_relation(rtype="conflicts_with", source=first["id"], target=second["id"])
    )
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "noncanonical-conflict")


def test_load_rejects_refines_cycle(lib, inited):
    a, b = h.make_requirement(), h.make_requirement()
    ledger = h.base_ledger()
    ledger["requirements"][a["id"]] = a
    ledger["requirements"][b["id"]] = b
    ledger["relations"].append(
        h.make_relation(rtype="refines", source=a["id"], target=b["id"]))
    ledger["relations"].append(
        h.make_relation(rtype="refines", source=b["id"], target=a["id"]))
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "cycle-relation")


def test_load_rejects_combined_refines_derived_from_cycle(lib, inited):
    a, b = h.make_requirement(), h.make_requirement()
    ledger = h.base_ledger()
    ledger["requirements"][a["id"]] = a
    ledger["requirements"][b["id"]] = b
    ledger["relations"].append(
        h.make_relation(rtype="refines", source=a["id"], target=b["id"]))
    ledger["relations"].append(
        h.make_relation(rtype="derived_from", source=b["id"], target=a["id"]))
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "cycle-relation")


def test_load_rejects_supersedes_cycle(lib, inited):
    a, b = h.make_requirement(), h.make_requirement()
    ledger = h.base_ledger()
    ledger["requirements"][a["id"]] = a
    ledger["requirements"][b["id"]] = b
    ledger["relations"].append(
        h.make_relation(rtype="supersedes", source=a["id"], target=b["id"]))
    ledger["relations"].append(
        h.make_relation(rtype="supersedes", source=b["id"], target=a["id"]))
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "cycle-relation")


def test_load_allows_contributes_to_cycle(lib, inited):
    a, b = h.make_requirement(), h.make_requirement()
    ledger = h.base_ledger()
    ledger["requirements"][a["id"]] = a
    ledger["requirements"][b["id"]] = b
    ledger["relations"].append(
        h.make_relation(rtype="contributes_to", source=a["id"], target=b["id"]))
    ledger["relations"].append(
        h.make_relation(rtype="contributes_to", source=b["id"], target=a["id"]))
    h.write_ledger(inited, ledger)
    loaded = lib.load_ledger(str(inited))
    assert len(loaded["relations"]) == 2


def test_load_allows_depends_on_cycle(lib, inited):
    a, b = h.make_requirement(), h.make_requirement()
    ledger = h.base_ledger()
    ledger["requirements"][a["id"]] = a
    ledger["requirements"][b["id"]] = b
    ledger["relations"].append(
        h.make_relation(rtype="depends_on", source=a["id"], target=b["id"]))
    ledger["relations"].append(
        h.make_relation(rtype="depends_on", source=b["id"], target=a["id"]))
    h.write_ledger(inited, ledger)
    loaded = lib.load_ledger(str(inited))
    assert len(loaded["relations"]) == 2


def test_load_allows_unresolved_conflict(lib, inited):
    first = h.make_requirement(rid=FIXED_A, statement="The build must be offline.")
    second = h.make_requirement(rid=FIXED_B,
                                statement="The build may fetch remote assets.")
    ledger = h.base_ledger()
    ledger["requirements"][first["id"]] = first
    ledger["requirements"][second["id"]] = second
    ledger["relations"].append(
        h.make_relation(rtype="conflicts_with", source=first["id"], target=second["id"]))
    ledger["revision"] = 1
    h.write_ledger(inited, ledger)
    loaded = lib.load_ledger(str(inited))
    assert loaded["revision"] == 1
    assert len(loaded["relations"]) == 1


# ---------------------------------------------------------------------------
# CLI create/apply/get basics
# ---------------------------------------------------------------------------


def test_create_assigns_immutable_uuid_and_revision(lib, inited):
    rid = create_result(inited)
    assert rid.startswith("REQ-")
    ledger = lib.load_ledger(str(inited))
    assert ledger["revision"] == 1
    record = ledger["requirements"][rid]
    assert record["lifecycle"] == "proposed"
    assert record["revision"] == 1
    assert ledger["artifacts"] == {}
    assert ledger["relations"] == []


def test_create_and_get_roundtrip(inited):
    rid = create_result(inited)
    result = h.run_cli(inited, "query", request={"op": "get", "args": {"id": rid}})
    assert result.returncode == 0, result.stdout + result.stderr
    body = result.json
    assert set(body) == {"status", "revision", "result"}
    assert body["result"]["requirement"]["id"] == rid
    assert body["result"]["requirement"]["statement"].strip()


def test_get_artifact_after_registration(lib, inited):
    result = h.run_cli(inited, "apply", request=h.apply_request(register_op("design")))
    assert result.returncode == 0, result.stdout + result.stderr
    aid = result.json["result"]["ops"][0]["id"]
    assert aid.startswith("ART-")
    found = h.run_cli(inited, "query", request={"op": "get", "args": {"id": aid}})
    assert found.returncode == 0
    record = found.json["result"]["artifact"]
    assert record["kind"] == "design"
    assert record["locator"] == "docs/design-notes.md"


def test_get_missing_id_reports_not_found(inited):
    result = h.run_cli(inited, "query", request={"op": "get", "args": {"id": "REQ-00000000-0000-4000-8000-00000000000a"}})
    assert result.returncode != 0
    assert result.error_code() == "not-found"


# ---------------------------------------------------------------------------
# Apply envelope and CLI error matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["actor", "expected_revision", "ops"])
def test_apply_requires_envelope_fields(inited, missing):
    request = h.apply_request(h.create_op())
    request.pop(missing)
    result = h.run_cli(inited, "apply", request=request)
    assert result.returncode != 0
    assert result.error_code() == "invalid-request"


def test_apply_rejects_unknown_op(inited):
    result = h.run_cli(inited, "apply", request=h.apply_request({"op": "explode", "args": {}}))
    assert result.returncode != 0
    assert result.error_code() == "invalid-op"


def test_apply_rejects_unknown_op_args(inited):
    result = h.run_cli(inited, "apply", request=h.apply_request(h.create_op(bogus=True)))
    assert result.returncode != 0
    assert result.error_code() == "invalid-op-args"
    assert json.loads(h.read_ledger_bytes(inited))["revision"] == 0


def test_apply_rejects_malformed_request_json(inited):
    result = h.run_cli(inited, "apply", request='{"actor": nope}')
    assert result.returncode != 0
    assert result.error_code() == "invalid-json"


def test_apply_rejects_duplicate_key_in_request(inited):
    raw = '{"actor": "a", "actor": "b", "expected_revision": 0, "ops": []}'
    result = h.run_cli(inited, "apply", request=raw)
    assert result.returncode != 0
    assert result.error_code() == "duplicate-json-key"


def test_apply_rejects_nonfinite_in_request(inited):
    request = ('{"actor": "a", "expected_revision": 0, "ops": [{"op": "create-requirement", '
               '"args": {"classification": "capability", "statement": "x", "rationale": "r", '
               '"provenance": {"source_reference": "d", "actor": "a", "date": "2026-10-29", '
               '"origin": "user_intent"}, "acceptance_criteria": [{"id": "c", "text": "t", '
               '"applicability": "analytical", "cost": 1e999}]}}]}')
    result = h.run_cli(inited, "apply", request=request)
    assert result.returncode != 0
    assert result.error_code() == "nonfinite-number"
    assert json.loads(h.read_ledger_bytes(inited))["revision"] == 0


def test_cli_accepts_stdin_request(inited):
    request = json.dumps(h.apply_request(h.create_op(statement="Via stdin."),
                                         expected_revision=0))
    proc = subprocess.run(
        [sys.executable, str(h.SCRIPT), "apply", "--repo-root", str(inited), "--stdin"],
        input=request, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    body = json.loads(proc.stdout)
    assert body["status"] == "ok"
    assert body["revision"] == 1


# ---------------------------------------------------------------------------
# Revisions, history, lifecycle, supersession
# ---------------------------------------------------------------------------


def test_revise_advances_revision_and_retains_snapshot(lib, inited):
    rid = create_result(inited)
    old = lib.load_ledger(str(inited))["requirements"][rid]
    result = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("revise-requirement", id=rid, reason="Sharpened wording.",
                statement="The tool strictly validates every stored requirement.",
                date="2026-10-30")))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.json["revision"] == 2
    record = lib.load_ledger(str(inited))["requirements"][rid]
    assert record["revision"] == 2
    assert record["statement"] == "The tool strictly validates every stored requirement."
    history = record["history"]
    assert len(history) == 1
    entry = history[-1]
    assert entry["kind"] == "revision"
    assert entry["from_revision"] == 1
    assert entry["to_revision"] == 2
    assert entry["reason"] == "Sharpened wording."
    assert entry["date"] == "2026-10-30"
    assert entry["prior"]["statement"] == old["statement"]
    assert entry["prior"]["classification"] == old["classification"]


def test_revise_reclassification_preserves_identity(lib, inited):
    rid = create_result(inited, statement="The pipeline must run nightly.")
    result = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("revise-requirement", id=rid, reason="Reclassified as behavior.",
                classification="behavior")))
    assert result.returncode == 0, result.stdout + result.stderr
    record = lib.load_ledger(str(inited))["requirements"][rid]
    assert record["id"] == rid
    assert record["classification"] == "behavior"
    assert record["revision"] == 2
    assert record["history"][-1]["prior"]["classification"] == "capability"


def test_revise_requires_reason(lib, inited):
    rid = create_result(inited)
    result = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("revise-requirement", id=rid, statement="Changed without reason.")))
    assert result.returncode != 0
    assert result.error_code() == "invalid-op-args"


def test_revise_terminal_record_rejected(lib, inited):
    rid = create_result(inited)
    transition = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("transition-requirement", id=rid, to="rejected",
                reason="Duplicated intent.", authority="User instruction at meeting.")))
    assert transition.returncode == 0, transition.stdout + transition.stderr
    result = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("revise-requirement", id=rid, reason="No.", statement="Resurrected?")))
    assert result.returncode != 0
    assert result.error_code() == "terminal-record"


def test_transition_requires_authority_and_reason(lib, inited):
    rid = create_result(inited)
    missing = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("transition-requirement", id=rid, to="active")))
    assert missing.returncode != 0
    assert missing.error_code() == "invalid-op-args"

    ok = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("transition-requirement", id=rid, to="active", reason="Reviewed design.",
                authority="Explicit user contract.", date="2026-10-30")))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    record = lib.load_ledger(str(inited))["requirements"][rid]
    assert record["lifecycle"] == "active"
    entry = record["history"][-1]
    assert entry["kind"] == "transition"
    assert entry["from_lifecycle"] == "proposed"
    assert entry["to_lifecycle"] == "active"
    assert entry["authority"] == "Explicit user contract."


def test_transition_rejects_forbidden_moves(lib, inited):
    rid = create_result(inited)
    direct = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("transition-requirement", id=rid, to="superseded",
                reason="Shortcut.", authority="User instruction.")))
    assert direct.returncode != 0
    assert direct.error_code() == "invalid-transition"

    active = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("transition-requirement", id=rid, to="active",
                reason="Approved.", authority="User instruction.")))
    assert active.returncode == 0
    rejected = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("transition-requirement", id=rid, to="rejected",
                reason="Withdrawn.", authority="User instruction.")))
    assert rejected.returncode == 0
    revive = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("transition-requirement", id=rid, to="active",
                reason="Second try.", authority="User instruction.")))
    assert revive.returncode != 0
    assert revive.error_code() == "invalid-transition"
    assert lib.load_ledger(str(inited))["requirements"][rid]["lifecycle"] == "rejected"


def test_supersede_creates_replacement_relation_and_terminal_state(lib, inited):
    old_id = create_result(inited, statement="Validate requirements nightly.")
    result = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("supersede-requirement", old_id=old_id,
                reason="Replaced by hourly validation.",
                authority="User contract revision.",
                provenance=h.provenance(),
                create={"classification": "capability",
                        "statement": "Validate requirements hourly.",
                        "rationale": "Tighter cadence requested.",
                        "provenance": h.provenance()})))
    assert result.returncode == 0, result.stdout + result.stderr
    new_id = result.json["result"]["ops"][-1]["id"]
    assert new_id != old_id
    ledger = lib.load_ledger(str(inited))
    old = ledger["requirements"][old_id]
    assert old["lifecycle"] == "superseded"
    assert old["history"][-1]["kind"] == "transition"
    assert old["history"][-1]["to_lifecycle"] == "superseded"
    edges = [r for r in ledger["relations"]
             if r["type"] == "supersedes" and r["source"] == new_id and r["target"] == old_id]
    assert len(edges) == 1
    assert ledger["requirements"][new_id]["lifecycle"] == "proposed"

    again = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("supersede-requirement", old_id=old_id, reason=" Twice.",
                authority="No authority.", provenance=h.provenance(),
                create={"classification": "capability",
                        "statement": "Third.",
                        "rationale": "No.",
                        "provenance": h.provenance()})))
    assert again.returncode != 0
    assert again.error_code() == "terminal-record"


def test_supersede_uses_existing_replacement(lib, inited):
    old_id = create_result(inited)
    other = h.run_cli(inited, "apply", request=h.apply_request(
        h.create_op(statement="Potential replacement.")))
    assert other.returncode == 0
    replacement_id = other.json["result"]["ops"][0]["id"]
    result = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("supersede-requirement", old_id=old_id, replacement_id=replacement_id,
                reason="Folding duplicates.", authority="User instruction.",
                provenance=h.provenance())))
    assert result.returncode == 0, result.stdout + result.stderr
    ledger = lib.load_ledger(str(inited))
    assert ledger["requirements"][old_id]["lifecycle"] == "superseded"
    edges = [r for r in ledger["relations"]
             if r["type"] == "supersedes" and r["source"] == replacement_id
             and r["target"] == old_id]
    assert len(edges) == 1


# ---------------------------------------------------------------------------
# Artifact registration and relations
# ---------------------------------------------------------------------------


def test_register_and_update_artifact_preserves_identity(lib, inited):
    result = h.run_cli(inited, "apply", request=h.apply_request(register_op("code", "docs/impl.py")))
    assert result.returncode == 0, result.stdout + result.stderr
    aid = result.json["result"]["ops"][0]["id"]
    update = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("update-artifact", id=aid, title="CLI implementation",
                content_digest="sha256:abc123", selector="scripts/requirements.py:main")))
    assert update.returncode == 0
    ledger = lib.load_ledger(str(inited))
    assert len(ledger["artifacts"]) == 1
    record = ledger["artifacts"][aid]
    assert record["id"] == aid
    assert record["kind"] == "code"
    assert record["title"] == "CLI implementation"
    assert record["selector"] == "scripts/requirements.py:main"
    assert record["content_digest"] == "sha256:abc123"


def test_artifact_locator_safety(lib, inited, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n")
    os.symlink(str(outside), str(inited / "docs" / "escape.md"))
    out_dir = tmp_path / "outside-dir"
    out_dir.mkdir()
    os.symlink(str(out_dir), str(inited / "docs" / "out-link"))
    os.symlink(str(inited / "docs" / "design-notes.md"), str(out_dir / "back-in.md"))
    os.symlink(str(inited / "docs" / "design-notes.md"), str(inited / "docs" / "alias.md"))

    def register(locator):
        return h.run_cli(inited, "apply", request=h.apply_request(register_op("code", locator)))

    for bad in ("/tmp/x-absolute.py", "../outside.txt", "docs/../outside.txt",
                "C:\\x\\impl.py", "docs/escape.md", "docs/out-link/back-in.md", "docs"):
        result = register(bad)
        assert result.returncode != 0, bad
        assert result.error_code() == "invalid-locator", bad

    ok = register("docs/alias.md")
    assert ok.returncode == 0, ok.stdout + ok.stderr

    planned = register("docs/planned-later.py")
    assert planned.returncode == 0, planned.stdout + planned.stderr


def test_add_relation_stores_endpoint_matrix(lib, inited):
    rid = create_result(inited)
    design = register_result(inited, "design")
    impl = register_result(inited, "implementation_spec", "docs/impl.py")
    for rtype, source, target in (
        ("addresses", design, rid),
        ("realizes", impl, design),
        ("implements", register_result(inited, "code", "docs/impl.py"), impl),
        ("verifies", register_result(inited, "test", "docs/test-suite.py"), rid),
        ("exercises", register_result(inited, "test", "docs/test-suite.py"),
         register_result(inited, "code", "docs/impl.py")),
        ("supports", register_result(inited, "evidence", "docs/impl.py"), rid),
    ):
        result = h.run_cli(inited, "apply", request=h.apply_request(
            add_relation_op(rtype, source, target)))
        assert result.returncode == 0, f"{rtype}: {result.stdout + result.stderr}"
    ledger = lib.load_ledger(str(inited))
    assert len(ledger["relations"]) == 6


def register_result(repo, kind, locator="docs/design-notes.md"):
    result = h.run_cli(repo, "apply", request=h.apply_request(register_op(kind, locator)))
    assert result.returncode == 0, result.stdout + result.stderr
    return result.json["result"]["ops"][0]["id"]


def test_constraint_to_constraint_is_permitted(lib, inited):
    first = h.run_cli(inited, "apply", request=h.apply_request(
        h.create_op(classification="constraint",
                    statement="No network access in CI sandbox.",
                    rationale="Sandbox isolation contract.")))
    assert first.returncode == 0
    cid = first.json["result"]["ops"][0]["id"]
    second = h.run_cli(inited, "apply", request=h.apply_request(
        h.create_op(classification="constraint",
                    statement="Artifacts rebuild offline.",
                    rationale="Reproducible builds contract.")))
    sid = second.json["result"]["ops"][0]["id"]
    result = h.run_cli(inited, "apply", request=h.apply_request(
        add_relation_op("constrains", cid, sid,
                        rationale="Build isolation narrows sandbox rules.")))
    assert result.returncode == 0, result.stdout + result.stderr
    design = register_result(inited, "design")
    toward_design = h.run_cli(inited, "apply", request=h.apply_request(
        add_relation_op("constrains", cid, design)))
    assert toward_design.returncode == 0

    goal = h.run_cli(inited, "apply", request=h.apply_request(
        h.create_op(classification="goal", statement="Ship weekly.",
                    rationale="User intent.")))
    gid = goal.json["result"]["ops"][0]["id"]
    bad_source = h.run_cli(inited, "apply", request=h.apply_request(
        add_relation_op("constrains", gid, sid)))
    assert bad_source.returncode != 0
    assert bad_source.error_code() == "invalid-endpoint"
    goal_target = h.run_cli(inited, "apply", request=h.apply_request(
        add_relation_op("constrains", cid, gid)))
    assert goal_target.returncode == 0, goal_target.stdout + goal_target.stderr


def test_relation_endpoint_rejections(lib, inited):
    rid = create_result(inited)
    code = register_result(inited, "code", "docs/impl.py")
    impl = register_result(inited, "implementation_spec", "docs/impl.py")
    bad_source = h.run_cli(inited, "apply", request=h.apply_request(
        add_relation_op("verifies", impl, rid)))
    assert bad_source.returncode != 0
    assert bad_source.error_code() == "invalid-endpoint"
    bad_target = h.run_cli(inited, "apply", request=h.apply_request(
        add_relation_op("exercises", code, impl)))
    assert bad_target.returncode != 0
    assert bad_target.error_code() == "invalid-endpoint"


def test_relationship_conflict_canonical_and_duplicates(lib, inited):
    first = h.run_cli(inited, "apply", request=h.apply_request(
        h.create_op(statement="Offline builds.", rationale="Contract.")))
    fid = first.json["result"]["ops"][0]["id"]
    second = h.run_cli(inited, "apply", request=h.apply_request(
        h.create_op(statement="Remote assets required.", rationale="Need.")))
    sid = second.json["result"]["ops"][0]["id"]
    if sid < fid:
        fid, sid = sid, fid
    result = h.run_cli(inited, "apply", request=h.apply_request(
        add_relation_op("conflicts_with", fid, sid)))
    assert result.returncode == 0, result.stdout + result.stderr
    reversed_duplicate = h.run_cli(inited, "apply", request=h.apply_request(
        add_relation_op("conflicts_with", sid, fid)))
    assert reversed_duplicate.returncode != 0
    assert reversed_duplicate.error_code() == "duplicate-relation"
    same_again = h.run_cli(inited, "apply", request=h.apply_request(
        add_relation_op("conflicts_with", fid, sid)))
    assert same_again.error_code() == "duplicate-relation"
    ledger = lib.load_ledger(str(inited))
    assert fid < sid
    assert all(r["source"] < r["target"] for r in ledger["relations"]
               if r["type"] == "conflicts_with")


def test_add_relation_rejects_self_edge(lib, inited):
    rid = create_result(inited)
    result = h.run_cli(inited, "apply", request=h.apply_request(
        add_relation_op("refines", rid, rid)))
    assert result.returncode != 0
    assert result.error_code() == "self-edge"


def test_decomposition_cycles_rejected_through_cli(lib, inited):
    ids = []
    for statement in ("Coverage first.", "Fast coverage.", "Coverage under six seconds."):
        ids.append(create_result(inited, statement=statement))
    a, b = ids[0], ids[1]
    ok = h.run_cli(inited, "apply", request=h.apply_request(add_relation_op("refines", a, b)))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    cycle = h.run_cli(inited, "apply", request=h.apply_request(add_relation_op("refines", b, a)))
    assert cycle.returncode != 0
    assert cycle.error_code() == "cycle-relation"
    combined = h.run_cli(inited, "apply", request=h.apply_request(
        add_relation_op("derived_from", b, a)))
    assert combined.returncode != 0
    assert combined.error_code() == "cycle-relation"


def test_supersedes_cycles_rejected_through_cli(lib, inited):
    a = create_result(inited)
    b = create_result(inited)
    ok = h.run_cli(inited, "apply", request=h.apply_request(add_relation_op("supersedes", a, b)))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    cycle = h.run_cli(inited, "apply", request=h.apply_request(add_relation_op("supersedes", b, a)))
    assert cycle.returncode != 0
    assert cycle.error_code() == "cycle-relation"


def test_allowed_cycles_accepted_through_cli(lib, inited):
    a = create_result(inited)
    b = create_result(inited)
    forward = h.run_cli(inited, "apply", request=h.apply_request(add_relation_op("contributes_to", a, b)))
    backward = h.run_cli(inited, "apply", request=h.apply_request(add_relation_op("contributes_to", b, a)))
    assert forward.returncode == 0, forward.stdout + forward.stderr
    assert backward.returncode == 0, backward.stdout + backward.stderr
    assert lib.load_ledger(str(inited))["revision"] == 4


def test_revise_and_retract_relation_retains_history(lib, inited):
    a = create_result(inited)
    b = create_result(inited)
    added = h.run_cli(inited, "apply", request=h.apply_request(add_relation_op("depends_on", a, b)))
    assert added.returncode == 0
    relation_id = added.json["result"]["ops"][0]["id"]
    revised = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("revise-relation", id=relation_id, reason="Weaker dependency.",
                confidence="uncertain", date="2026-10-30")))
    assert revised.returncode == 0, revised.stdout + revised.stderr
    ledger = lib.load_ledger(str(inited))
    relation = next(r for r in ledger["relations"] if r["id"] == relation_id)
    assert relation["confidence"] == "uncertain"
    entry = relation["history"][-1]
    assert entry["action"] == "update"
    assert entry["prior"]["confidence"] == "explicit"

    retracted = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("retract-relation", id=relation_id, reason="Dependency unclear.",
                date="2026-10-31")))
    assert retracted.returncode == 0, retracted.stdout + retracted.stderr
    ledger = lib.load_ledger(str(inited))
    relation = next(r for r in ledger["relations"] if r["id"] == relation_id)
    assert relation["retracted"] is True
    assert relation["history"][-1]["action"] == "retract"


def test_retracted_relations_stop_counting_for_cycles(lib, inited):
    a = create_result(inited)
    b = create_result(inited)
    added = h.run_cli(inited, "apply", request=h.apply_request(add_relation_op("refines", a, b)))
    relation_id = added.json["result"]["ops"][0]["id"]
    retracted = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("retract-relation", id=relation_id, reason="Wrong direction.")))
    assert retracted.returncode == 0, retracted.stdout + retracted.stderr
    future = h.run_cli(inited, "apply", request=h.apply_request(add_relation_op("refines", b, a)))
    assert future.returncode == 0, future.stdout + future.stderr


# ---------------------------------------------------------------------------
# Transactions, stale writers, atomic storage, concurrency
# ---------------------------------------------------------------------------


def test_transaction_rollback_on_any_failure(inited):
    rid = create_result(inited)
    before = h.read_ledger_bytes(inited)
    design = h.run_cli(inited, "apply", request=h.apply_request(register_op("code", "docs/impl.py")))
    design_id = design.json["result"]["ops"][0]["id"]
    before = h.read_ledger_bytes(inited)
    batch = h.apply_request(
        h.create_op(statement="Additional requirement."),
        add_relation_op("implements", design_id, "REQ-00000000-0000-4000-8000-00000000000a"))
    result = h.run_cli(inited, "apply", request=batch)
    assert result.returncode != 0
    assert result.error_code() == "broken-reference"
    assert h.read_ledger_bytes(inited) == before
    ledger = json.loads(h.read_ledger_bytes(inited))
    assert ledger["revision"] == 2
    assert len(ledger["requirements"]) == 1


def test_stale_writer_preserves_bytes(inited):
    before = h.read_ledger_bytes(inited)
    result = h.run_cli(inited, "apply", request={
        "actor": "test", "expected_revision": 999,
        "ops": [{"op": "transition-requirement", "args": {"id": "missing"}}]})
    assert result.returncode != 0
    assert json.loads(result.stdout)["error"]["code"] == "expected-revision-stale"
    assert h.read_ledger_bytes(inited) == before
    after = h.run_cli(inited, "apply", request=h.apply_request(h.create_op()))
    assert after.returncode == 0, after.stdout + after.stderr


def test_failed_replace_preserves_bytes_and_releases_lock(lib, inited, tmp_path, monkeypatch):
    rid = create_result(inited)
    before = h.read_ledger_bytes(inited)

    def boom(src, dst):
        raise OSError("simulated atomic replacement failure")

    request = h.apply_request(h.create_op(statement="Second requirement."),
                              expected_revision=h.current_revision(inited))
    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", boom)
        expect_error(lambda: lib.apply(str(inited), request), "storage-write-failed")
    assert h.read_ledger_bytes(inited) == before

    released = h.run_cli(inited, "apply", request=request)
    assert released.returncode == 0, released.stdout + released.stderr
    ledger = lib.load_ledger(str(inited))
    assert len(ledger["requirements"]) == 2


class FakeProc:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_two_real_competing_writers_on_same_revision(inited):
    requests = [
        h.apply_request(h.create_op(statement="Writer A record."), expected_revision=0),
        h.apply_request(h.create_op(statement="Writer B record."), expected_revision=0),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for request in requests:
            path = Path(tmp) / f"request-{len(paths)}.json"
            path.write_text(json.dumps(request))
            paths.append(path)
        procs = []
        for path in paths:
            procs.append(subprocess.Popen(
                [sys.executable, str(h.SCRIPT), "apply", "--repo-root", str(inited),
                 "--request", str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        results = []
        for proc in procs:
            stdout, stderr = proc.communicate()
            results.append(h.CliResult(FakeProc(proc.returncode, stdout, stderr)))

    codes = sorted(result.returncode for result in results)
    assert codes == [0, 1]
    losers = [result for result in results if result.returncode != 0]
    winners = [result for result in results if result.returncode == 0]
    assert len(winners) == 1
    assert losers[0].error_code() == "expected-revision-stale"
    ledger = json.loads(h.read_ledger_bytes(inited))
    assert ledger["revision"] == 1
    assert len(ledger["requirements"]) == 1


def test_apply_rejects_empty_ops(inited):
    result = h.run_cli(inited, "apply", request=h.apply_request())
    assert result.returncode != 0
    assert result.error_code() == "invalid-request"
