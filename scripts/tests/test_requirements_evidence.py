"""Task 2: satisfaction assessments and verification evidence.

Covers (per docs/plans/2026-10-29-requirements-driven-engineering.md Task 2):
append-only assessment/verification/disposition history, validated source and
evidence references, requirement-revision and criterion identity, latest
failure/inconclusive/pending masking old passes, missing dependency
declarations reporting unknown, content/digest changes going stale, unrelated
repository files never invalidating currency, empirical method applicability,
independent claim/result/lifecycle state, conflict dispositions, stored
procedures never executing, and the accepted Task 1 strict-validation
corrections (non-dict map entries, deep normative snapshot validation and
supersession lifecycle coupling).
"""

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest

import helpers_requirements as h

DESIGN_NOTES = "docs/design-notes.md"
EVIDENCE_NOTE = "docs/verify-evidence.md"

EMPIRICAL = {"id": "c1", "text": "Observed latency stays under 50ms on real hardware.",
             "applicability": "empirical"}
ANALYTICAL = {"id": "c2", "text": "Strict loader rejects malformed records.",
              "applicability": "analytical"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "design-notes.md").write_text("# design notes\n")
    (docs / "impl.py").write_text("# implementation stub\n")
    (docs / "verify-evidence.md").write_text("empirical observation record\n")
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


def digests(repo):
    root = Path(repo)
    return {
        DESIGN_NOTES: sha256(root / DESIGN_NOTES),
        EVIDENCE_NOTE: sha256(root / EVIDENCE_NOTE),
        "docs/impl.py": sha256(root / "docs/impl.py"),
    }


def create_req(repo, criteria=(EMPIRICAL, ANALYTICAL), **overrides):
    result = h.run_cli(
        repo, "apply",
        request=h.apply_request(h.create_op(acceptance_criteria=list(criteria),
                                            **overrides)))
    assert result.returncode == 0, result.stdout + result.stderr
    return result.json["result"]["ops"][0]["id"]


def assessment_op(rid, state="unaddressed", **overrides):
    args = {
        "requirement_id": rid,
        "requirement_revision": 1,
        "state": state,
        "rationale": "Explicit human claim recorded under review.",
        "source_refs": [{"locator": DESIGN_NOTES}],
    }
    args.update(overrides)
    return op_args("record-assessment", **args)


def verification_op(rid, revision=1, cid="c1", method="empirical_measurement",
                    result="passed", **overrides):
    args = {
        "requirement_id": rid,
        "requirement_revision": revision,
        "criterion_id": cid,
        "method": method,
        "result": result,
        "procedure": "scripts/tests/commands/example-procedure --strict",
        "environment": "Ubuntu test host with hardware in the loop.",
        "observation": "Observed behavior recorded at run time.",
        "timestamp": "2026-10-29T10:00:00Z",
        "evidence_ref": {"locator": EVIDENCE_NOTE},
        "dependency_digests": {},
    }
    args.update(overrides)
    return op_args("record-verification", **args)


def disposition_op(relation_id, **overrides):
    args = {
        "relation_id": relation_id,
        "explanation": "Accepted as an explicit scoped exception by review.",
        "authority": "Independent review record cited in the progress ledger.",
    }
    args.update(overrides)
    return op_args("record-conflict-disposition", **args)


def register_op(kind, locator=DESIGN_NOTES, **extra):
    args = {"kind": kind, "title": f"{kind} artifact", "locator": locator}
    args.update(extra)
    return op_args("register-artifact", **args)


def conflict_op(source, target):
    return op_args("add-relation", type="conflicts_with", source=source,
                   target=target, rationale="Incompatible under conditions.",
                   confidence="explicit", provenance=h.provenance())


def ok(result):
    assert result.returncode == 0, result.stdout + result.stderr
    return result.json


def apply_op(repo, op, **overrides):
    return ok(h.run_cli(repo, "apply", request=h.apply_request(op)))


def report(repo, rid):
    result = ok(h.run_cli(repo, "query", request={"op": "get", "args": {"id": rid}}))
    assert "criteria_latest" in result["result"]
    return result["result"]["criteria_latest"]


def read_ledger(repo):
    return json.loads(h.read_ledger_bytes(repo))


# ---------------------------------------------------------------------------
# Recording assessments and verifications
# ---------------------------------------------------------------------------


def test_assessments_append_and_retain_history(inited):
    rid = create_req(inited)
    apply_op(inited, assessment_op(rid))
    apply_op(inited, assessment_op(rid, state="partial"))

    ledger = read_ledger(inited)
    assert len(ledger["assessments"]) == 2
    first, second = ledger["assessments"]
    assert first["state"] == "unaddressed" and second["state"] == "partial"
    assert first["actor"] == "test-actor" and second["actor"] == "test-actor"
    assert first["date"] and first["requirement_revision"] == 1
    assert first["source_refs"] == [{"locator": DESIGN_NOTES}]
    assert second["rationale"] != ""


def test_assessment_rejects_foreign_revision_and_empty_content(inited):
    rid = create_req(inited)
    cases = (
        assessment_op(rid, requirement_revision=2),
        assessment_op(rid, source_refs=[]),
        assessment_op(rid, rationale=" "),
    )
    for op in cases:
        result = h.run_cli(inited, "apply", request=h.apply_request(op))
        assert result.error_code() == "invalid-op-args", f"op={op}"


def test_assessment_references_are_validated(inited):
    rid = create_req(inited)
    # Unsafe locators are rejected; unknown artifact references fail loudly.
    for bad_ref, code in (
        ({"locator": "../etc/passwd"}, "invalid-locator"),
        ({"locator": "/etc/passwd"}, "invalid-locator"),
        ({"artifact_id": f"ART-{uuid.uuid4()}"}, "broken-reference"),
    ):
        result = h.run_cli(inited, "apply",
                           request=h.apply_request(
                               assessment_op(rid, source_refs=[bad_ref])))
        assert result.returncode != 0
        assert result.error_code() == code, (
            f"bad_ref={bad_ref}: {result.error_code()}")
    # A safe, not-yet-existing locator is a valid descriptive source reference.
    apply_op(inited, assessment_op(
        rid, source_refs=[{"locator": DESIGN_NOTES},
                          {"locator": "docs/missing-planned-doc.md"}]))


def test_verification_records_identity_and_fields(inited, repo):
    rid = create_req(inited)
    apply_op(inited, verification_op(rid, dependency_digests={
        EVIDENCE_NOTE: digests(repo)[EVIDENCE_NOTE]}))

    ledger = read_ledger(inited)
    (record,) = ledger["verifications"]
    assert record["requirement_id"] == rid
    assert record["requirement_revision"] == 1
    assert record["criterion_id"] == "c1"
    assert record["method"] == "empirical_measurement"
    assert record["result"] == "passed"
    assert record["evidence_ref"] == {"locator": EVIDENCE_NOTE}


def test_verification_rejects_wrong_identity_and_shape(inited):
    rid = create_req(inited)
    cases = (
        (verification_op(rid, revision=2), "invalid-op-args"),
        (verification_op(rid, cid="missing-criterion"), "invalid-op-args"),
        (verification_op(f"REQ-{uuid.uuid4()}"), "not-found"),
        (verification_op(rid, method="alien-method"), "invalid-record"),
        (verification_op(rid, result="maybe"), "invalid-record"),
        (verification_op(rid, timestamp="2026-10-29"), "invalid-record"),
        (verification_op(rid, procedure=""), "invalid-op-args"),
        (verification_op(rid, environment=""), "invalid-op-args"),
        (verification_op(rid, observation=""), "invalid-op-args"),
    )
    for op, code in cases:
        result = h.run_cli(inited, "apply", request=h.apply_request(op))
        assert result.error_code() == code, (
            f"op={op}: {result.error_code()} expected {code}")


def test_verification_declaration_and_evidence_references(inited, repo):
    rid = create_req(inited)
    # Empty string values inside declared digests are invalid.
    result = h.run_cli(inited, "apply", request=h.apply_request(
        verification_op(rid, dependency_digests={EVIDENCE_NOTE: "  "})))
    assert result.error_code() == "invalid-op-args"

    # Unsafe locator as a dependency key is rejected.
    result = h.run_cli(inited, "apply", request=h.apply_request(
        verification_op(rid,
                        dependency_digests={"../secret": "0" * 64})))
    assert result.error_code() == "invalid-locator"

    # Unsafe evidence ref and unknown artifact evidence ref fail loudly.
    result = h.run_cli(inited, "apply", request=h.apply_request(
        verification_op(rid, evidence_ref={"locator": "../secret"})))
    assert result.error_code() == "invalid-locator"

    result = h.run_cli(inited, "apply", request=h.apply_request(
        verification_op(rid, evidence_ref={"artifact_id": f"ART-{uuid.uuid4()}"})))
    assert result.error_code() == "broken-reference"

    # Nonexistent locator evidence is refused at record time.
    result = h.run_cli(inited, "apply", request=h.apply_request(
        verification_op(rid, evidence_ref={"locator": "docs/absent-now.md"})))
    assert result.returncode != 0

    # Safe existing locator evidence and existing artifact evidence commit.
    apply_op(inited, verification_op(rid, dependency_digests={EVIDENCE_NOTE: digests(repo)[EVIDENCE_NOTE]}))
    reg = apply_op(inited, register_op("evidence", locator=EVIDENCE_NOTE,
                                         content_digest=digests(repo)["docs/impl.py"]))
    aid = reg["result"]["ops"][0]["id"]
    apply_op(inited, verification_op(
        rid, result="failed", evidence_ref={"artifact_id": aid},
        dependency_digests={}))


def test_evidence_ops_join_atomic_batches(inited, repo):
    rid = create_req(inited)
    before = h.read_ledger_bytes(inited)

    # A failing op after a valid one rolls back the whole batch.
    res = h.run_cli(inited, "apply", request=h.apply_request(
        assessment_op(rid, state="satisfied"), verification_op(rid, revision=99)))
    assert res.error_code() == "invalid-op-args"
    assert h.read_ledger_bytes(inited) == before


# ---------------------------------------------------------------------------
# Currency and latest-applicable reports via query get
# ---------------------------------------------------------------------------


def test_latest_failed_observation_is_not_hidden(inited, repo):
    rid = create_req(inited)
    declared = {EVIDENCE_NOTE: digests(repo)[EVIDENCE_NOTE]}
    apply_op(inited, verification_op(rid, result="passed",
                                     timestamp="2026-10-28T10:00:00Z",
                                     dependency_digests=declared))
    apply_op(inited, verification_op(rid, result="failed",
                                     dependency_digests=declared))
    latest = report(inited, rid)["c1"]
    assert latest["result"] == "failed"
    assert latest["currency"] == "current"


def test_pending_and_inconclusive_mask_old_pass(inited, repo):
    rid = create_req(inited)
    declared = {EVIDENCE_NOTE: digests(repo)[EVIDENCE_NOTE]}
    for result in ("passed", "inconclusive", "pending", "absent"):
        apply_op(inited, verification_op(rid, result=result,
                                         dependency_digests=declared))
        assert report(inited, rid)["c1"]["result"] == result
        assert report(inited, rid)["c1"]["currency"] == "current"
    latest = report(inited, rid)["c1"]
    assert latest["result"] == "absent"
    assert latest["currency"] == "current"
    assert len(read_ledger(inited)["verifications"]) == 4


def test_same_criterion_reports_independently(inited, repo):
    rid = create_req(inited)
    apply_op(inited, verification_op(rid, cid="c1", result="failed"))
    apply_op(inited, verification_op(rid, revision=1, cid="c2",
                                     method="inspection", result="passed"))
    latest = report(inited, rid)
    assert latest["c1"]["result"] == "failed"
    assert latest["c2"]["result"] == "passed"
    assert latest["c2"]["method"] == "inspection"


def test_missing_dependency_declarations_report_unknown(inited, repo):
    rid = create_req(inited)
    apply_op(inited, verification_op(rid, dependency_digests={}))
    latest = report(inited, rid)["c1"]
    assert latest["result"] == "passed"
    assert latest["currency"] == "unknown"


def test_declared_locators_report_current_then_stale_then_unknown(inited, repo):
    rid = create_req(inited)
    base = digests(repo)
    apply_op(inited, verification_op(
        rid, dependency_digests={EVIDENCE_NOTE: base[EVIDENCE_NOTE]}))
    assert report(inited, rid)["c1"]["currency"] == "current"

    # Same hash under churn elsewhere: currency stays current.
    (repo / "docs" / "unrelated.cpp").write_text("// unrelated churn\n")
    (repo / "src-note.md").write_text("another unrelated file\n")
    assert report(inited, rid)["c1"]["currency"] == "current"

    # Matching-path content change goes stale.
    (repo / EVIDENCE_NOTE).write_text("updated observation\n")
    assert report(inited, rid)["c1"]["currency"] == "stale"

    # Deleted content is not proven fresh.
    (repo / EVIDENCE_NOTE).unlink()
    assert report(inited, rid)["c1"]["currency"] == "unknown"


def test_artifact_digest_change_goes_stale(inited, repo):
    rid = create_req(inited)
    reg = apply_op(inited, register_op(
        "evidence", locator=EVIDENCE_NOTE, content_digest=digests(repo)[EVIDENCE_NOTE]))
    aid = reg["result"]["ops"][0]["id"]
    apply_op(inited, verification_op(
        rid, evidence_ref={"artifact_id": aid},
        dependency_digests={aid: digests(repo)[EVIDENCE_NOTE]}))
    assert report(inited, rid)["c1"]["currency"] == "current"

    apply_op(inited, op_args("update-artifact", id=aid,
                               content_digest="sha256:changed"))
    assert report(inited, rid)["c1"]["currency"] == "stale"


def test_artifact_currency_reads_actual_content(inited, repo):
    rid = create_req(inited)
    digest = digests(repo)[EVIDENCE_NOTE]
    aid = apply_op(inited, register_op(
        "evidence", locator=EVIDENCE_NOTE, content_digest=digest))["result"]["ops"][0]["id"]
    apply_op(inited, verification_op(rid, evidence_ref={"artifact_id": aid},
                                     dependency_digests={aid: digest}))
    (repo / EVIDENCE_NOTE).write_text("changed without updating registry\n")
    assert report(inited, rid)["c1"]["currency"] == "stale"


def test_evidence_content_is_anchored_independently(inited, repo):
    rid = create_req(inited)
    apply_op(inited, verification_op(rid, dependency_digests={
        DESIGN_NOTES: digests(repo)[DESIGN_NOTES]}))
    record = read_ledger(inited)["verifications"][0]
    assert record["actor"] == "test-actor"
    assert record["evidence_digest"] == digests(repo)[EVIDENCE_NOTE]
    (repo / EVIDENCE_NOTE).write_text("rewritten evidence\n")
    assert report(inited, rid)["c1"]["currency"] == "stale"


def test_latest_observation_uses_time_not_import_order(inited, repo):
    rid = create_req(inited)
    declared = {EVIDENCE_NOTE: digests(repo)[EVIDENCE_NOTE]}
    apply_op(inited, verification_op(rid, result="failed",
                                     dependency_digests=declared))
    apply_op(inited, verification_op(rid, result="passed",
                                     timestamp="2026-10-28T10:00:00Z",
                                     dependency_digests=declared))
    assert report(inited, rid)["c1"]["result"] == "failed"


def test_artifact_dependency_uses_bytes_not_only_registry(inited, repo):
    rid = create_req(inited)
    digest = digests(repo)["docs/impl.py"]
    aid = apply_op(inited, register_op(
        "code", locator="docs/impl.py", content_digest=digest))["result"]["ops"][0]["id"]
    apply_op(inited, verification_op(rid, dependency_digests={aid: digest}))
    assert report(inited, rid)["c1"]["currency"] == "current"
    (repo / "docs/impl.py").write_text("# modified dependency\n")
    assert report(inited, rid)["c1"]["currency"] == "stale"
    (repo / "docs/impl.py").unlink()
    assert report(inited, rid)["c1"]["currency"] == "unknown"


def test_unrelated_git_commit_does_not_invalidate_evidence(inited, repo):
    env = {**os.environ, "GIT_AUTHOR_NAME": "Requirements Test",
           "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Requirements Test",
           "GIT_COMMITTER_EMAIL": "test@example.invalid"}

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], env=env,
                              check=True, capture_output=True, text=True).stdout

    git("init")
    git("add", "docs")
    git("commit", "-m", "Initial fixture")
    before_head = git("rev-parse", "HEAD")
    rid = create_req(inited)
    apply_op(inited, verification_op(rid, dependency_digests={
        EVIDENCE_NOTE: digests(repo)[EVIDENCE_NOTE]}))
    (repo / "unrelated.txt").write_text("unrelated change\n")
    git("add", "unrelated.txt")
    git("commit", "-m", "Unrelated fixture change")
    assert git("rev-parse", "HEAD") != before_head
    assert report(inited, rid)["c1"]["currency"] == "current"


def test_new_revision_observation_supersedes_old_revision_time(inited, repo):
    rid = create_req(inited)
    apply_op(inited, verification_op(rid, result="passed",
                                     timestamp="2026-10-30T10:00:00Z"))
    apply_op(inited, assessment_op(rid))
    apply_op(inited, op_args("revise-requirement", id=rid,
                            reason="Clarify", statement="Revised statement."))
    apply_op(inited, verification_op(rid, revision=2, result="failed"))
    latest = report(inited, rid)["c1"]
    assert latest["result"] == "failed"
    assert latest["requirement_revision"] == 2
    assert len(read_ledger(inited)["verifications"]) == 2
    ok(h.run_cli(inited, "validate"))


def test_evidence_missing_artifact_file_rejected_and_read_never_repairs(inited, repo):
    rid = create_req(inited)
    aid = apply_op(inited, register_op(
        "evidence", locator="docs/planned.md"))["result"]["ops"][0]["id"]
    before = h.read_ledger_bytes(inited)
    result = h.run_cli(inited, "apply", request=h.apply_request(
        verification_op(rid, evidence_ref={"artifact_id": aid})))
    assert result.error_code() == "invalid-evidence-ref"
    assert h.read_ledger_bytes(inited) == before
    apply_op(inited, verification_op(rid, dependency_digests={
        DESIGN_NOTES: digests(repo)[DESIGN_NOTES]}))
    (repo / EVIDENCE_NOTE).unlink()
    before = h.read_ledger_bytes(inited)
    assert report(inited, rid)["c1"]["currency"] == "unknown"
    assert h.read_ledger_bytes(inited) == before


@pytest.mark.parametrize("field,value", [("actor", None), ("actor", ""),
                                         ("evidence_digest", []),
                                         ("evidence_ref", {"locator": None}),
                                         ("timestamp", "2026-02-30T10:00:00Z"),
                                         ("dependency_digests", [])])
def test_loaded_verification_fields_reject_malformed_types(lib, inited, field, value):
    rid = create_req(inited)
    apply_op(inited, verification_op(rid))
    ledger = read_ledger(inited)
    ledger["verifications"][0][field] = value
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")


@pytest.mark.parametrize("timestamp", ["2026-10-29T99:00:00Z",
                                      "2026-10-29T10:60:00Z",
                                      "2026-10-29T10:00:60Z",
                                      "2026-10-29T10:00:00Z\n", None, 42])
def test_impossible_timestamps_rejected(inited, timestamp):
    rid = create_req(inited)
    before = h.read_ledger_bytes(inited)
    result = h.run_cli(inited, "apply", request=h.apply_request(
        verification_op(rid, timestamp=timestamp)))
    assert result.error_code() == "invalid-record"
    assert h.read_ledger_bytes(inited) == before


@pytest.mark.parametrize("field,value", [("requirement_id", []),
                                         ("requirement_id", None),
                                         ("requirement_revision", True),
                                         ("criterion_id", {}),
                                         ("method", []),
                                         ("result", {})])
def test_malformed_verification_types_are_explicit(inited, field, value):
    rid = create_req(inited)
    op = verification_op(rid)
    op["args"][field] = value
    result = h.run_cli(inited, "apply", request=h.apply_request(op))
    assert result.error_code() in {"invalid-record", "invalid-op-args"}


def test_loaded_evidence_endpoints_and_revisions_are_strict(lib, inited):
    rid = create_req(inited)
    apply_op(inited, verification_op(rid))
    apply_op(inited, assessment_op(rid))
    original = read_ledger(inited)
    for collection, field, value in (
        ("verifications", "criterion_id", "missing"),
        ("verifications", "requirement_revision", 9),
        ("verifications", "requirement_id", None),
        ("assessments", "requirement_revision", 9),
        ("assessments", "requirement_id", []),
    ):
        ledger = json.loads(json.dumps(original))
        ledger[collection][0][field] = value
        h.write_ledger(inited, ledger)
        expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")


def test_requirement_revision_advancement_goes_stale(inited, repo):
    rid = create_req(inited)
    apply_op(inited, verification_op(rid))
    apply_op(inited, op_args("revise-requirement", id=rid,
                               reason="Sharpened wording.",
                               statement="Updated normative statement."))
    latest = report(inited, rid)["c1"]
    assert latest["result"] == "passed"
    assert latest["currency"] == "stale"


# ---------------------------------------------------------------------------
# Method applicability and empirical authority
# ---------------------------------------------------------------------------


def test_empirical_criteria_reject_inapplicable_methods(inited, repo):
    rid = create_req(inited)
    result = h.run_cli(inited, "apply", request=h.apply_request(
        verification_op(rid, method="automated_test")))
    assert result.error_code() == "method-applicability"

    analytical = create_req(inited, criteria=[ANALYTICAL])
    result = h.run_cli(inited, "apply", request=h.apply_request(
        verification_op(analytical, revision=1, cid="c2",
                        method="empirical_measurement")))
    assert result.error_code() == "method-applicability"

    # Declared analytical methods behave as declared.
    for method in ("scenario", "automated_test", "audit", "analysis", "inspection"):
        apply_op(inited, verification_op(analytical, revision=1, cid="c2",
                                         method=method, dependency_digests={}))


def test_method_applicability_is_enforced_at_load(lib, inited, repo):
    rid = create_req(inited)
    apply_op(inited, verification_op(rid))
    ledger = read_ledger(inited)
    ledger["verifications"][0]["method"] = "automated_test"
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "method-applicability")


def test_stored_procedures_never_execute(inited, repo):
    marker = repo / "docs" / "never-executed-marker.txt"
    rid = create_req(inited)
    procedure = f"python3 -c \"open({str(marker)!r}, 'w').write('executed')\""
    apply_op(inited, verification_op(rid, procedure=procedure,
                                     dependency_digests={}))
    ok(h.run_cli(inited, "query", request={"op": "get", "args": {"id": rid}}))
    assert not marker.exists()
    stored = read_ledger(inited)["verifications"][0]["procedure"]
    assert stored == procedure


def test_claims_results_and_lifecycle_stay_independent(inited, repo):
    rid = create_req(inited)
    apply_op(inited, assessment_op(rid, state="unaddressed"))
    apply_op(inited, verification_op(rid, dependency_digests={}))

    ledger = read_ledger(inited)
    assert len(ledger["assessments"]) == 1
    assert ledger["assessments"][0]["state"] == "unaddressed"

    # Explicit claim appended; verification pass did not create or alter claims.
    apply_op(inited, assessment_op(rid, state="satisfied"))
    apply_op(inited, op_args("transition-requirement", id=rid, to="active",
                               reason="Activated by grounded authority.",
                               authority="Independent review record."))
    ledger = read_ledger(inited)
    assert [e["state"] for e in ledger["assessments"]] == ["unaddressed", "satisfied"]
    assert ledger["verifications"][0]["result"] == "passed"
    assert ledger["requirements"][rid]["lifecycle"] == "active"
    assert report(inited, rid)["c1"]["result"] == "passed"


def test_query_get_includes_criteria_latest_and_artifacts_do_not(inited, repo):
    rid = create_req(inited)
    apply_op(inited, verification_op(rid, dependency_digests={}))
    reg = apply_op(inited, register_op("design"))
    aid = reg["result"]["ops"][0]["id"]
    req_result = ok(h.run_cli(inited, "query",
                              request={"op": "get", "args": {"id": rid}}))
    assert set(req_result["result"]) == {"requirement", "criteria_latest"}
    assert set(req_result["result"]["criteria_latest"]) == {"c1", "c2"}
    art_result = ok(h.run_cli(inited, "query",
                              request={"op": "get", "args": {"id": aid}}))
    assert set(art_result["result"]) == {"artifact"}


# ---------------------------------------------------------------------------
# Conflict dispositions
# ---------------------------------------------------------------------------


def test_conflict_disposition_records_explanation_and_authority(inited):
    a = create_req(inited, statement="Constraint A obligations.")
    b = create_req(inited, statement="Constraint B obligations.")
    rel_id = apply_op(inited, conflict_op(a, b))["result"]["ops"][0]["id"]

    apply_op(inited, disposition_op(rel_id))
    (record,) = read_ledger(inited)["conflict_dispositions"]
    assert record["relation_id"] == rel_id
    assert record["explanation"] and record["authority"]
    assert record["actor"] == "test-actor"

    result = h.run_cli(inited, "apply", request=h.apply_request(
        disposition_op(f"REL-{uuid.uuid4()}")))
    assert result.error_code() == "not-found"


def test_disposition_rejects_nonconflict_and_retracted_relations(inited):
    a = create_req(inited)
    b = create_req(inited)
    nonconflict = apply_op(inited, op_args(
        "add-relation", type="depends_on", source=a, target=b,
        rationale="Sequenced obligations.", confidence="explicit",
        provenance=h.provenance()))["result"]["ops"][0]["id"]
    result = h.run_cli(inited, "apply",
                       request=h.apply_request(disposition_op(nonconflict)))
    assert result.error_code() == "invalid-op-args"

    conflict = apply_op(inited, conflict_op(a, b))["result"]["ops"][0]["id"]
    apply_op(inited, disposition_op(conflict))
    apply_op(inited, op_args("retract-relation", id=conflict,
                               reason="Reconciled later."))
    result = h.run_cli(inited, "apply",
                       request=h.apply_request(disposition_op(conflict)))
    assert result.error_code() == "invalid-op-args"

    # Retained historical disposition survives retraction and strict load.
    assert len(read_ledger(inited)["conflict_dispositions"]) == 1
    ok(h.run_cli(inited, "validate"))


def test_disposition_fields_are_strict(inited):
    a = create_req(inited)
    b = create_req(inited)
    rel_id = apply_op(inited, conflict_op(a, b))["result"]["ops"][0]["id"]
    for op, code in (
        (disposition_op(rel_id, explanation=""), "invalid-op-args"),
        (disposition_op(rel_id, authority=""), "invalid-op-args"),
        (disposition_op(rel_id, explanation="x", authority="y", bogus=1),
         "invalid-op-args"),
    ):
        result = h.run_cli(inited, "apply", request=h.apply_request(op))
        assert result.error_code() == code, f"op={op}: {result.error_code()}"


def test_disposition_arrays_are_strictly_shaped(lib, inited):
    ledger = h.base_ledger()
    ledger["conflict_dispositions"] = ["stripped"]
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")

    ledger = h.base_ledger()
    ledger["verifications"] = [42]
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")


# ---------------------------------------------------------------------------
# Accepted Task 1 strict-validation corrections
# ---------------------------------------------------------------------------


def test_non_dict_map_entries_fail_explicitly(lib, inited):
    ledger = h.base_ledger()
    ledger["requirements"]["REQ-not-an-object"] = "plain string"
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")

    ledger = h.base_ledger()
    ledger["artifacts"]["ART-not-an-object"] = ["list"]
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")

    ledger = h.base_ledger()
    ledger["assessments"] = ["not-a-dict"]
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")


def _revision_entry(prior):
    prior = {"rationale": "Original rationale.", "provenance": h.provenance(),
             **prior}
    return {"kind": "revision", "from_revision": 1, "to_revision": 2,
            "reason": "Reworked.", "actor": "a", "date": "2026-10-29",
            "prior": prior}


def test_prior_snapshots_are_deep_validated(lib, inited):
    cases = (
        ({"statement": "Old text.", "classification": "alien",
          "acceptance_criteria": []}, "invalid-record"),
        ({"statement": "Old text.", "classification": "capability",
          "acceptance_criteria": [{"id": "c1", "text": "",
                                   "applicability": "analytical"}]},
         "invalid-record"),
        ({"statement": "Old text.", "classification": "capability",
          "acceptance_criteria": [{"id": "c1", "text": "x",
                                   "applicability": "alien"}]}, "invalid-record"),
        ({"statement": "", "classification": "capability",
          "acceptance_criteria": []}, "invalid-record"),
        ({"statement": "Old text.", "classification": "capability",
          "acceptance_criteria": [],
          "provenance": {"source_reference": "s", "actor": "a", "date": "bad",
                         "origin": "user_intent"}}, "invalid-record"),
        ({"statement": "Old text.", "classification": "capability",
          "acceptance_criteria": [], "bogus": 1}, "unknown-field"),
    )
    for prior, expected in cases:
        record = h.make_requirement(revision=2, history=[_revision_entry(prior)])
        ledger = h.base_ledger()
        ledger["requirements"][record["id"]] = record
        h.write_ledger(inited, ledger)
        expect_error(lambda: lib.load_ledger(str(inited)), expected)

    # A complete retained snapshot still loads.
    minimal = {"statement": "Old text.", "classification": "capability",
               "acceptance_criteria": [{"id": "c1", "text": "Old criterion.",
                                        "applicability": "analytical"}]}
    record = h.make_requirement(revision=2, history=[_revision_entry(minimal)])
    ledger = h.base_ledger()
    ledger["requirements"][record["id"]] = record
    h.write_ledger(inited, ledger)
    lib.load_ledger(str(inited))


def test_supersession_edges_cannot_bypass_lifecycle(inited):
    rid = create_req(inited)
    other = create_req(inited, statement="Second requirement.")

    # Manual supersedes edge at record time when the target is not terminal.
    result = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("add-relation", type="supersedes", source=other, target=rid,
                  rationale="Replacement lineage.", confidence="explicit",
                  provenance=h.provenance())))
    assert result.error_code() == "invalid-supersession"

    # Manual transition into superseded stays forbidden; the terminal mark and
    # lineage edge only arise together through the supersede operation.
    result = h.run_cli(inited, "apply", request=h.apply_request(
        op_args("transition-requirement", id=rid, to="superseded",
                  reason="Hand bypass attempt.", authority="review")))
    assert result.error_code() == "invalid-transition"


def test_supersession_coupling_is_enforced_at_load(lib, inited):
    rid = create_req(inited)
    other = create_req(inited, statement="Second requirement.")

    # Active record targeted by a hand-written supersedes edge.
    ledger = read_ledger(inited)
    ledger["relations"].append(
        h.make_relation(rtype="supersedes", source=other, target=rid))
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-supersession")


def test_supersede_requires_authority_and_rolls_back(inited):
    rid = create_req(inited)
    replacement = create_req(inited)
    before = h.read_ledger_bytes(inited)
    result = h.run_cli(inited, "apply", request=h.apply_request(op_args(
        "supersede-requirement", old_id=rid, replacement_id=replacement,
        reason="Replaced", authority="", provenance=h.provenance())))
    assert result.error_code() == "invalid-op-args"
    assert h.read_ledger_bytes(inited) == before


def test_prior_snapshot_rationale_has_live_validation(lib, inited):
    prior = {"statement": "Old", "classification": "capability",
             "acceptance_criteria": [], "rationale": []}
    record = h.make_requirement(revision=2, history=[_revision_entry(prior)])
    ledger = h.base_ledger()
    ledger["requirements"][record["id"]] = record
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")


@pytest.mark.parametrize("missing", ["rationale", "provenance"])
def test_retained_snapshots_preserve_original_required_fields(lib, inited, missing):
    entry = _revision_entry({"statement": "Old", "classification": "capability",
                             "acceptance_criteria": []})
    del entry["prior"][missing]
    record = h.make_requirement(revision=2, history=[entry])
    ledger = h.base_ledger()
    ledger["requirements"][record["id"]] = record
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-record")

def test_superseded_mark_requires_lineage(lib, inited):
    # Terminal lifecycle mark without any retained supersedes lineage.
    record = h.make_requirement(lifecycle="superseded", history=[{
        "kind": "transition", "from_lifecycle": "proposed", "to_lifecycle": "superseded",
        "reason": "Replace", "authority": "Explicit intent", "actor": "test", "date": "2026-10-29"}])
    ledger = h.base_ledger()
    ledger["revision"] = 1
    ledger["requirements"][record["id"]] = record
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(str(inited)), "invalid-supersession")


@pytest.mark.parametrize("collection", ["assessments", "verifications"])
def test_load_rejects_future_snapshot_evidence(lib, inited, collection):
    rid = create_req(inited)
    apply_op(inited, assessment_op(rid))
    apply_op(inited, verification_op(rid))
    apply_op(inited, op_args("revise-requirement", id=rid, reason="Clarify",
                            statement="Revision two."))
    ledger = read_ledger(inited)
    entry = ledger["requirements"][rid]["history"][0]
    entry.update(from_revision=9, to_revision=10)
    ledger[collection][0]["requirement_revision"] = 9
    ledger["verifications" if collection == "assessments" else "assessments"] = []
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(inited), "invalid-record")


@pytest.mark.parametrize("pairs,current", [
    ([(0, 1)], 1), ([(-1, 0)], 1), ([(1, 1)], 1),
    ([(1, 3)], 3), ([(1, 2)], 1), ([], 2),
    ([(1, 2)], 3), ([(2, 3)], 3),
    ([(1, 2), (1, 2)], 2),
    ([(2, 3), (1, 2)], 3),
    ([(True, 2)], 2), ([(1, 2.0)], 2),
])
def test_load_rejects_inconsistent_revision_sequence(lib, inited, pairs, current):
    history = []
    for index, (from_revision, to_revision) in enumerate(pairs):
        entry = _revision_entry({"statement": f"Snapshot {index}",
                                 "classification": "capability",
                                 "acceptance_criteria": []})
        entry.update(from_revision=from_revision, to_revision=to_revision)
        history.append(entry)
    record = h.make_requirement(revision=current, history=history)
    ledger = h.base_ledger()
    ledger["requirements"][record["id"]] = record
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(inited), "invalid-record")


def test_valid_multirevision_evidence_survives_load(lib, inited):
    rid = create_req(inited)
    for revision in (1, 2, 3):
        apply_op(inited, assessment_op(rid, requirement_revision=revision))
        apply_op(inited, verification_op(rid, revision=revision))
        if revision == 1:
            apply_op(inited, op_args("transition-requirement", id=rid, to="active",
                                    reason="Activate", authority="Explicit intent"))
        if revision < 3:
            apply_op(inited, op_args("revise-requirement", id=rid,
                                    reason="Clarify", statement=f"Revision {revision + 1}"))
    ledger = lib.load_ledger(inited)
    assert [v["requirement_revision"] for v in ledger["verifications"]] == [1, 2, 3]
    assert [a["requirement_revision"] for a in ledger["assessments"]] == [1, 2, 3]
    assert report(inited, rid)["c1"]["requirement_revision"] == 3


@pytest.mark.parametrize("mutation,code", [
    ("missing", "invalid-record"),
    ("rejected-origin", "invalid-record"),
    ("duplicate", "invalid-record"),
    ("later-transition", "invalid-record"),
    ("authority", "invalid-record"),
    ("reason", "invalid-record"),
])
def test_superseded_lineage_requires_valid_retained_transition(lib, inited, mutation, code):
    old = create_req(inited)
    replacement = create_req(inited)
    apply_op(inited, op_args("supersede-requirement", old_id=old,
                            replacement_id=replacement, reason="Replace",
                            authority="Explicit intent", provenance=h.provenance()))
    ledger = read_ledger(inited)
    history = ledger["requirements"][old]["history"]
    if mutation == "missing":
        history.clear()
    elif mutation == "rejected-origin":
        history[0]["from_lifecycle"] = "rejected"
    elif mutation == "duplicate":
        history.append(dict(history[0]))
    elif mutation == "later-transition":
        history.append({**history[0], "from_lifecycle": "superseded",
                        "to_lifecycle": "active"})
    else:
        history[0][mutation] = " "
    h.write_ledger(inited, ledger)
    expect_error(lambda: lib.load_ledger(inited), code)


def test_supersession_chain_retains_transition_with_retracted_lineage(lib, inited):
    old, replacement, latest = [create_req(inited) for _ in range(3)]
    apply_op(inited, op_args("transition-requirement", id=old, to="active",
                            reason="Activate", authority="Explicit intent"))
    for predecessor, successor in ((old, replacement), (replacement, latest)):
        apply_op(inited, op_args("supersede-requirement", old_id=predecessor,
                                replacement_id=successor, reason="Replace",
                                authority="Explicit intent", provenance=h.provenance()))
    relation_id = read_ledger(inited)["relations"][0]["id"]
    apply_op(inited, op_args("retract-relation", id=relation_id,
                            reason="Retain historical lineage only"))
    ledger = lib.load_ledger(inited)
    assert ledger["relations"][0]["retracted"] is True
    for rid in (old, replacement):
        record = ledger["requirements"][rid]
        assert record["lifecycle"] == "superseded"
        assert record["history"][-1]["to_lifecycle"] == "superseded"
