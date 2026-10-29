"""Strict schema definitions and validation for the requirements ledger.

The reviewed design is authoritative: opaque immutable ``REQ-``/``ART-``
identifiers, five initial classifications without hierarchy, lifecycle separate
from satisfaction, strict allowed/required fields, and rejection of duplicate
JSON keys, nonfinite numbers, unknown fields/versions and malformed records.
"""

import json
import math
import os
import re
import uuid
from datetime import date, datetime

from . import RequirementsError

SCHEMA_VERSION = 1

CLASSIFICATIONS = ("goal", "outcome", "capability", "behavior", "constraint")
LIFECYCLES = ("proposed", "active", "superseded", "rejected")
ARTIFACT_KINDS = ("design", "implementation_spec", "code", "test", "evidence")
CONFIDENCE_LEVELS = ("explicit", "inferred", "uncertain")
APPLICABILITY = ("empirical", "analytical")
ORIGINS = ("user_intent", "justified_interpretation", "descriptive_evidence")

ASSESSMENT_STATES = ("unaddressed", "partial", "satisfied")
EMPIRICAL_METHODS = ("empirical_measurement",)
ANALYTICAL_METHODS = ("scenario", "automated_test", "audit", "analysis",
                      "inspection")
VERIFICATION_METHODS = EMPIRICAL_METHODS + ANALYTICAL_METHODS
VERIFICATION_RESULTS = ("absent", "pending", "passed", "failed", "inconclusive")

ALLOWED_TRANSITIONS = {
    "proposed": ("active", "rejected"),
    "active": ("rejected",),
    "superseded": (),
    "rejected": (),
}

TOP_LEVEL_REQUIRED = ("schema_version", "revision", "requirements", "artifacts",
                      "relations", "assessments", "verifications",
                      "conflict_dispositions")

REQUIREMENT_FIELDS = ("id", "classification", "statement", "rationale",
                      "acceptance_criteria", "provenance", "lifecycle",
                      "revision", "history")
CRITERION_FIELDS = ("id", "text", "applicability")
PROVENANCE_FIELDS = ("source_reference", "actor", "date", "origin")
PROVENANCE_OPTIONAL = ("excerpt",)
ARTIFACT_FIELDS = ("id", "kind", "title", "locator")
ARTIFACT_OPTIONAL = ("selector", "content_digest")
RELATION_FIELDS = ("id", "type", "source", "target", "rationale", "provenance",
                   "confidence")
RELATION_OPTIONAL = ("retracted", "history")

ASSESSMENT_FIELDS = ("requirement_id", "requirement_revision", "state",
                     "rationale", "actor", "date", "source_refs")
VERIFICATION_FIELDS = ("requirement_id", "requirement_revision", "criterion_id",
                       "method", "result", "procedure", "environment",
                       "observation", "timestamp", "evidence_ref",
                       "dependency_digests", "actor", "evidence_digest")
CONFLICT_DISPOSITION_FIELDS = ("relation_id", "explanation", "authority",
                               "actor", "date")
REF_FIELDS = ("locator", "artifact_id")

REVISION_HISTORY_FIELDS = ("kind", "from_revision", "to_revision", "reason",
                           "actor", "date", "prior")
TRANSITION_HISTORY_FIELDS = ("kind", "from_lifecycle", "to_lifecycle", "reason",
                             "authority", "actor", "date")
PRIOR_SNAPSHOT_FIELDS = ("statement", "classification", "acceptance_criteria",
                         "rationale", "provenance")
PRIOR_SNAPSHOT_OPTIONAL = ()
RELATION_HISTORY_FIELDS = ("action", "reason", "actor", "date", "prior")
RELATION_PRIOR_FIELDS = ("rationale", "confidence")

_ID_PATTERN = re.compile(
    r"^(REQ|ART|REL)-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def fail(code, message, details=None):
    raise RequirementsError(code, message, details or {})


def is_uuid_id(value):
    return isinstance(value, str) and bool(_ID_PATTERN.match(value))


def valid_date(value):
    if not isinstance(value, str) or not _DATE_PATTERN.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def valid_timestamp(value):
    """Strict UTC wall-clock stamp: 'YYYY-MM-DDTHH:MM:SSZ'."""
    if not isinstance(value, str) or not _TIMESTAMP_PATTERN.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def new_uuid_id(prefix):
    return f"{prefix}-{uuid.uuid4()}"


def strict_json_loads(text, context):
    """Parse JSON rejecting duplicate keys and nonfinite numbers explicitly."""
    def no_duplicates(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                raise _DuplicateKey(key)
            seen.add(key)
        return dict(pairs)

    def reject_constant(name):
        raise _Nonfinite(name)

    try:
        data = json.loads(text, object_pairs_hook=no_duplicates,
                          parse_constant=reject_constant)
    except (_DuplicateKey, _Nonfinite) as exc:
        code = "duplicate-json-key" if isinstance(exc, _DuplicateKey) else "nonfinite-number"
        raise RequirementsError(
            code,
            f"JSON request violating strict contracts in {context}: {exc}",
            {"context": context, "offending": str(exc)},
        ) from exc
    except json.JSONDecodeError as exc:
        raise RequirementsError(
            "invalid-json", f"Malformed JSON in {context}: {exc.msg}",
            {"context": context, "position": exc.pos},
        ) from exc
    _reject_nonfinite(data, context)
    return data


class _DuplicateKey(Exception):
    pass


class _Nonfinite(Exception):
    pass


def _reject_nonfinite(data, context):
    stack = [("", data)]
    while stack:
        path, value = stack.pop()
        if isinstance(value, float) and not math.isfinite(value):
            raise RequirementsError(
                "nonfinite-number",
                f"Nonfinite number at {path or '<root>'} in {context}.",
                {"path": path, "context": context},
            )
        if isinstance(value, dict):
            stack.extend((f"{path}.{key}", item) for key, item in value.items())
        elif isinstance(value, list):
            stack.extend((f"{path}[{index}]", item) for index, item in enumerate(value))


def _check_keys(obj, required, optional, where):
    if not isinstance(obj, dict):
        fail("invalid-record", f"{where} must be an object.", {"where": where})
    if set(obj) - set(required) - set(optional):
        fail("unknown-field",
             f"{where} carries unknown fields: {sorted(set(obj) - set(required) - set(optional))}.",
             {"where": where, "unknown": sorted(set(obj) - set(required) - set(optional))})
    missing = [key for key in required if key not in obj]
    if missing:
        fail("invalid-record", f"{where} misses required fields: {missing}.",
             {"where": where, "missing": missing})


def _nonempty_string(value, where):
    return isinstance(value, str) and value.strip() != ""


def _int(value, where):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_provenance(provenance, where):
    _check_keys(provenance, PROVENANCE_FIELDS, PROVENANCE_OPTIONAL, where)
    for field in ("source_reference", "actor"):
        if not _nonempty_string(provenance[field], f"{where}.{field}"):
            fail("invalid-record", f"{where}.{field} must be a nonempty string.",
                 {"field": field})
    if not valid_date(provenance["date"]):
        fail("invalid-record", f"{where}.date must be an ISO 'YYYY-MM-DD' date.",
             {"date": provenance["date"]})
    if provenance["origin"] not in ORIGINS:
        fail("invalid-record", f"{where}.origin must be one of {ORIGINS}.",
             {"origin": provenance["origin"]})
    if "excerpt" in provenance and not isinstance(provenance["excerpt"], str):
        fail("invalid-record", f"{where}.excerpt must be a string.", {"field": "excerpt"})


def validate_acceptance_criteria(criteria, where):
    if not isinstance(criteria, list):
        fail("invalid-record", f"{where} must be a list.", {"where": where})
    seen = set()
    for index, criterion in enumerate(criteria):
        spot = f"{where}[{index}]"
        _check_keys(criterion, CRITERION_FIELDS, (), spot)
        if not _nonempty_string(criterion["id"], f"{spot}.id"):
            fail("invalid-record", f"{spot}.id must be a nonempty string.", {})
        if criterion["id"] in seen:
            fail("invalid-record", f"{spot}.id duplicates a criterion id.",
                 {"criterion": criterion["id"]})
        seen.add(criterion["id"])
        if not _nonempty_string(criterion["text"], f"{spot}.text"):
            fail("invalid-record", f"{spot}.text must be a nonempty string.", {})
        if criterion["applicability"] not in APPLICABILITY:
            fail("invalid-record",
                 f"{spot}.applicability must be one of {APPLICABILITY}.", {})


def validate_history(record, where):
    for index, entry in enumerate(record.get("history", [])):
        spot = f"{where}.history[{index}]"
        kind = None
        if not isinstance(entry, dict) or "kind" not in entry:
            fail("invalid-record", f"{spot} must name its kind.", {})
        kind = entry["kind"]
        if kind == "revision":
            _check_keys(entry, REVISION_HISTORY_FIELDS, (), spot)
            from_rev, to_rev = entry["from_revision"], entry["to_revision"]
            if not (_int(from_rev, f"{spot}.from_revision")
                    and _int(to_rev, f"{spot}.to_revision") and from_rev <= to_rev):
                fail("invalid-record",
                     f"{spot} revisions must be integers with from_revision <= to_revision.",
                     {"from_revision": from_rev, "to_revision": to_rev})
            validate_prior_snapshot(entry["prior"], f"{spot}.prior")
        elif kind == "transition":
            _check_keys(entry, TRANSITION_HISTORY_FIELDS, (), spot)
            if entry["from_lifecycle"] not in LIFECYCLES or entry["to_lifecycle"] not in LIFECYCLES:
                fail("invalid-record", f"{spot} lifecycle values are unknown.",
                     {"from_lifecycle": entry["from_lifecycle"],
                       "to_lifecycle": entry["to_lifecycle"]})
            if not _nonempty_string(entry["authority"], f"{spot}.authority"):
                fail("invalid-record", f"{spot}.authority must be nonempty.", {})
        else:
            fail("invalid-record", f"{spot}.kind must be 'revision' or 'transition'.",
                 {"kind": kind})
        for field in ("reason", "actor"):
            if not _nonempty_string(entry[field], f"{spot}.{field}"):
                fail("invalid-record", f"{spot}.{field} must be a nonempty string.",
                     {"field": field})
        if not valid_date(entry["date"]):
            fail("invalid-record", f"{spot}.date must be an ISO 'YYYY-MM-DD' date.",
                 {"date": entry["date"]})


def validate_requirement(record, where):
    _check_keys(record, REQUIREMENT_FIELDS, (), where)
    if not is_uuid_id(record["id"]) or not record["id"].startswith("REQ-"):
        fail("invalid-record",
             f"{where}.id must be a canonical lowercase REQ-<uuid> identifier.",
             {"id": record["id"]})
    if record["classification"] not in CLASSIFICATIONS:
        fail("invalid-record",
             f"{where}.classification must be one of {CLASSIFICATIONS}.", {})
    for field in ("statement", "rationale"):
        if not _nonempty_string(record[field], f"{where}.{field}"):
            fail("invalid-record", f"{where}.{field} must be a nonempty string.",
                 {"field": field})
    validate_acceptance_criteria(record["acceptance_criteria"], f"{where}.acceptance_criteria")
    validate_provenance(record["provenance"], f"{where}.provenance")
    if record["lifecycle"] not in LIFECYCLES:
        fail("invalid-record", f"{where}.lifecycle must be one of {LIFECYCLES}.",
             {"lifecycle": record["lifecycle"]})
    if not _int(record["revision"], f"{where}.revision") or record["revision"] < 1:
        fail("invalid-record", f"{where}.revision must be a positive integer.",
             {"revision": record["revision"]})
    if not isinstance(record["history"], list):
        fail("invalid-record", f"{where}.history must be a list.", {"where": where})
    validate_history(record, where)


def validate_artifact(record, where):
    _check_keys(record, ARTIFACT_FIELDS, ARTIFACT_OPTIONAL, where)
    if not is_uuid_id(record["id"]) or not record["id"].startswith("ART-"):
        fail("invalid-record",
             f"{where}.id must be a canonical lowercase ART-<uuid> identifier.",
             {"id": record["id"]})
    if record["kind"] not in ARTIFACT_KINDS:
        fail("invalid-record", f"{where}.kind must be one of {ARTIFACT_KINDS}.",
             {"kind": record["kind"]})
    if not _nonempty_string(record["title"], f"{where}.title"):
        fail("invalid-record", f"{where}.title must be a nonempty string.", {})
    if not isinstance(record["locator"], str) or not record["locator"].strip():
        fail("invalid-record", f"{where}.locator must be a nonempty string.", {})
    for field in ARTIFACT_OPTIONAL:
        if field in record and not isinstance(record[field], str):
            fail("invalid-record", f"{where}.{field} must be a string.", {"field": field})


def validate_relation(record, where):
    if isinstance(record, dict) and "retracted" in record and not isinstance(
            record["retracted"], bool):
        fail("invalid-record", f"{where}.retracted must be a boolean.", {})
    _check_keys(record, RELATION_FIELDS, RELATION_OPTIONAL, where)
    if not is_uuid_id(record["id"]) or not record["id"].startswith("REL-"):
        fail("invalid-record",
             f"{where}.id must be a canonical lowercase REL-<uuid> identifier.",
             {"id": record["id"]})
    if not _nonempty_string(record["rationale"], f"{where}.rationale"):
        fail("invalid-record", f"{where}.rationale must be a nonempty string.", {})
    validate_provenance(record["provenance"], f"{where}.provenance")
    if record["confidence"] not in CONFIDENCE_LEVELS:
        fail("invalid-record",
             f"{where}.confidence must be one of {CONFIDENCE_LEVELS}.",
             {"confidence": record["confidence"]})
    for index, entry in enumerate(record.get("history", [])):
        spot = f"{where}.history[{index}]"
        _check_keys(entry, RELATION_HISTORY_FIELDS, (), spot)
        if entry["action"] not in ("update", "retract"):
            fail("invalid-record", f"{spot}.action must be 'update' or 'retract'.",
                 {"action": entry["action"]})
        for field in ("reason", "actor"):
            if not _nonempty_string(entry[field], f"{spot}.{field}"):
                fail("invalid-record", f"{spot}.{field} must be a nonempty string.",
                     {"field": field})
        if not valid_date(entry["date"]):
            fail("invalid-record", f"{spot}.date must be an ISO 'YYYY-MM-DD' date.",
                 {"date": entry["date"]})
        _check_keys(entry["prior"], RELATION_PRIOR_FIELDS, (), f"{spot}.prior")
        if entry["prior"]["confidence"] not in CONFIDENCE_LEVELS:
            fail("invalid-record", f"{spot}.prior.confidence must be one of {CONFIDENCE_LEVELS}.",
                 {"confidence": entry["prior"]["confidence"]})


def validate_prior_snapshot(prior, where):
    """Validate retained pre-revision content with the live record rules."""
    _check_keys(prior, PRIOR_SNAPSHOT_FIELDS, PRIOR_SNAPSHOT_OPTIONAL, where)
    if not _nonempty_string(prior["statement"], f"{where}.statement"):
        fail("invalid-record", f"{where}.statement must be a nonempty string.", {})
    if prior["classification"] not in CLASSIFICATIONS:
        fail("invalid-record",
             f"{where}.classification must be one of {CLASSIFICATIONS}.", {})
    validate_acceptance_criteria(prior["acceptance_criteria"],
                                 f"{where}.acceptance_criteria")
    if not _nonempty_string(prior["rationale"], where):
        fail("invalid-record", f"{where}.rationale must be a nonempty string.", {})
    validate_provenance(prior["provenance"], f"{where}.provenance")


def validate_ref(ref, where, repo_root):
    """Validate a source/evidence reference: locator on disk or ART identity.

    Locator references must be safe repository-relative file paths (existence
    is a record-time contract, not a load-time one); artifact references name
    an existing registered artifact checked at ledger level.
    """
    _check_keys(ref, (), REF_FIELDS, where)
    locator = ref.get("locator")
    artifact_id = ref.get("artifact_id")
    if len(ref) != 1:
        fail("invalid-record",
             f"{where} must name exactly one of 'locator' or 'artifact_id'.",
             {"where": where})
    if locator is not None:
        validate_repo_locator(repo_root, locator)
    elif not (is_uuid_id(artifact_id) and artifact_id.startswith("ART-")):
        fail("invalid-record",
             f"{where}.artifact_id must be a canonical ART-<uuid> identifier.",
             {"artifact_id": artifact_id})


def validate_dependency_digests(digests, where, repo_root):
    if not isinstance(digests, dict):
        fail("invalid-record", f"{where} must be an object.", {"where": where})
    for key, value in digests.items():
        if _nonempty_string(value, f"{where}[{key}]") and isinstance(key, str):
            if is_uuid_id(key) and key.startswith("ART-"):
                continue
            validate_repo_locator(repo_root, key)
        else:
            fail("invalid-record",
                 f"{where} values must be nonempty strings and keys artifact "
                 "IDs or safe locators.",
                 {"key": key, "value": value if isinstance(value, str) else None})


def check_method_applicability(requirement, verification):
    """A verification's method must match its criterion applicability.

    Empirical criteria demand empirical observations: capability test and
    scenario evidence can never establish an empirical verification.
    """
    criterion = criterion_at_revision(
        requirement, verification["requirement_revision"],
        verification["criterion_id"])
    if criterion is None:
        return
    empirical = verification["method"] in EMPIRICAL_METHODS
    required_empirical = criterion["applicability"] == "empirical"
    if empirical != required_empirical:
        fail("method-applicability",
             f"Criterion {criterion['id']!r} declares {criterion['applicability']!r} "
             f"applicability, incompatible with {verification['method']!r}.",
             {"requirement_id": requirement["id"],
              "requirement_revision": verification["requirement_revision"],
              "criterion_id": verification["criterion_id"],
              "applicability": criterion["applicability"],
              "method": verification["method"]})


def validate_assessment(record, where, repo_root):
    _check_keys(record, ASSESSMENT_FIELDS, (), where)
    if (not is_uuid_id(record["requirement_id"])
            or not record["requirement_id"].startswith("REQ-")):
        fail("invalid-record",
             f"{where}.requirement_id must be a canonical REQ-<uuid> identifier.",
             {"requirement_id": record["requirement_id"]})
    if not _int(record["requirement_revision"], f"{where}.requirement_revision") \
            or record["requirement_revision"] < 1:
        fail("invalid-record",
             f"{where}.requirement_revision must be a positive integer.",
             {"requirement_revision": record["requirement_revision"]})
    if record["state"] not in ASSESSMENT_STATES:
        fail("invalid-record",
             f"{where}.state must be one of {ASSESSMENT_STATES}.",
             {"state": record["state"]})
    for field in ("rationale", "actor"):
        if not _nonempty_string(record[field], f"{where}.{field}"):
            fail("invalid-record", f"{where}.{field} must be a nonempty string.",
                 {"field": field})
    if not valid_date(record["date"]):
        fail("invalid-record", f"{where}.date must be an ISO 'YYYY-MM-DD' date.",
             {"date": record["date"]})
    if not isinstance(record["source_refs"], list) or not record["source_refs"]:
        fail("invalid-record",
             f"{where}.source_refs must be a nonempty list of references.",
             {"where": where})
    for index, ref in enumerate(record["source_refs"]):
        validate_ref(ref, f"{where}.source_refs[{index}]", repo_root)


def validate_verification(record, where, repo_root):
    _check_keys(record, VERIFICATION_FIELDS, (), where)
    if (not is_uuid_id(record["requirement_id"])
            or not record["requirement_id"].startswith("REQ-")):
        fail("invalid-record",
             f"{where}.requirement_id must be a canonical REQ-<uuid> identifier.",
             {"requirement_id": record["requirement_id"]})
    if not _int(record["requirement_revision"], f"{where}.requirement_revision") \
            or record["requirement_revision"] < 1:
        fail("invalid-record",
             f"{where}.requirement_revision must be a positive integer.",
             {"requirement_revision": record["requirement_revision"]})
    if not _nonempty_string(record["criterion_id"], f"{where}.criterion_id"):
        fail("invalid-record", f"{where}.criterion_id must be a nonempty string.",
             {"field": "criterion_id"})
    if record["method"] not in VERIFICATION_METHODS:
        fail("invalid-record",
             f"{where}.method must be one of {VERIFICATION_METHODS}.",
             {"method": record["method"]})
    if record["result"] not in VERIFICATION_RESULTS:
        fail("invalid-record",
             f"{where}.result must be one of {VERIFICATION_RESULTS}.",
             {"result": record["result"]})
    for field in ("procedure", "environment", "observation", "actor"):
        if not _nonempty_string(record[field], f"{where}.{field}"):
            fail("invalid-record", f"{where}.{field} must be a nonempty string.",
                 {"field": field})
    if not valid_timestamp(record["timestamp"]):
        fail("invalid-record",
             f"{where}.timestamp must be a 'YYYY-MM-DDTHH:MM:SSZ' stamp.",
             {"timestamp": record["timestamp"]})
    validate_ref(record["evidence_ref"], f"{where}.evidence_ref", repo_root)
    if not isinstance(record["evidence_digest"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", record["evidence_digest"]):
        fail("invalid-record", f"{where}.evidence_digest must be a SHA-256 digest.", {})
    validate_dependency_digests(record["dependency_digests"],
                                f"{where}.dependency_digests", repo_root)


def validate_conflict_disposition(record, where):
    _check_keys(record, CONFLICT_DISPOSITION_FIELDS, (), where)
    if (not is_uuid_id(record["relation_id"])
            or not record["relation_id"].startswith("REL-")):
        fail("invalid-record",
             f"{where}.relation_id must be a canonical REL-<uuid> identifier.",
             {"relation_id": record["relation_id"]})
    for field in ("explanation", "authority", "actor"):
        if not _nonempty_string(record[field], f"{where}.{field}"):
            fail("invalid-record", f"{where}.{field} must be a nonempty string.",
                 {"field": field})
    if not valid_date(record["date"]):
        fail("invalid-record", f"{where}.date must be an ISO 'YYYY-MM-DD' date.",
             {"date": record["date"]})


def criterion_at_revision(record, revision, criterion_id):
    """Return the criterion dict at a historical requirement revision, or None.

    Current revision reads live `acceptance_criteria`; earlier revisions are
    reconstructed from the retained history prior snapshots.
    """
    if revision == record["revision"]:
        criteria = record["acceptance_criteria"]
    else:
        snapshot = next((entry for entry in record["history"]
                         if entry["kind"] == "revision"
                         and entry["from_revision"] == revision), None)
        if snapshot is None:
            fail("invalid-record",
                 f"Requirement {record['id']} has no retained snapshot for "
                 f"revision {revision}.",
                 {"requirement_id": record["id"], "revision": revision})
        criteria = snapshot["prior"]["acceptance_criteria"]
    return next((criterion for criterion in criteria
                 if criterion["id"] == criterion_id), None)


def validate_evidence_coupling(ledger):
    """Ledger-level endpoint/reference coupling of assessments and verifications."""
    requirements = ledger["requirements"]
    for index, assessment in enumerate(ledger["assessments"]):
        if assessment["requirement_id"] not in requirements:
            fail("broken-reference",
                 f"assessments[{index}] references unknown requirement "
                 f"{assessment['requirement_id']!r}.",
                 {"requirement_id": assessment["requirement_id"]})
        requirement = requirements[assessment["requirement_id"]]
        revision = assessment["requirement_revision"]
        if revision != requirement["revision"] and not any(
                entry["kind"] == "revision" and entry["from_revision"] == revision
                for entry in requirement["history"]):
            fail("invalid-record", "Assessment references an unretained revision.", {})
        for position, ref in enumerate(assessment["source_refs"]):
            if "artifact_id" in ref and ref["artifact_id"] not in ledger["artifacts"]:
                fail("broken-reference",
                     f"assessments[{index}].source_refs[{position}] references "
                     f"unknown artifact {ref['artifact_id']!r}.",
                     {"artifact_id": ref["artifact_id"]})
    for index, verification in enumerate(ledger["verifications"]):
        requirement = requirements.get(verification["requirement_id"])
        if requirement is None:
            fail("broken-reference",
                 f"verifications[{index}] references unknown requirement "
                 f"{verification['requirement_id']!r}.",
                 {"requirement_id": verification["requirement_id"]})
        if criterion_at_revision(requirement, verification["requirement_revision"],
                                 verification["criterion_id"]) is None:
            fail("invalid-record", "Verification references an unknown criterion.", {})
        check_method_applicability(requirement, verification)
        for key in verification["dependency_digests"]:
            if key.startswith("ART-") and key not in ledger["artifacts"]:
                fail("broken-reference",
                     f"verifications[{index}].dependency_digests references "
                     f"unknown artifact {key!r}.",
                     {"artifact_id": key})
        evidence_ref = verification["evidence_ref"]
        if ("artifact_id" in evidence_ref
                and evidence_ref["artifact_id"] not in ledger["artifacts"]):
            fail("broken-reference",
                 f"verifications[{index}].evidence_ref references unknown "
                 f"artifact {evidence_ref['artifact_id']!r}.",
                 {"artifact_id": evidence_ref["artifact_id"]})
    for index, disposition in enumerate(ledger["conflict_dispositions"]):
        relation = next((relation for relation in ledger["relations"]
                         if relation["id"] == disposition["relation_id"]), None)
        if relation is None:
            fail("broken-reference",
                 f"conflict_dispositions[{index}] references unknown relation "
                 f"{disposition['relation_id']!r}.",
                 {"relation_id": disposition["relation_id"]})
        if relation["type"] != "conflicts_with":
            fail("invalid-record",
                 f"conflict_dispositions[{index}] must reference a "
                 "conflicts_with relation.",
                 {"relation_id": disposition["relation_id"]})


def validate_ledger(ledger, repo_root):
    """Validate a parsed ledger dict fully; raises RequirementsError on violation."""
    if not isinstance(ledger, dict):
        fail("invalid-record", "Top-level ledger must be an object.", {})
    _check_keys(ledger, TOP_LEVEL_REQUIRED, (), "<ledger>")
    if ledger["schema_version"] != SCHEMA_VERSION or isinstance(ledger["schema_version"], bool):
        fail("unknown-schema-version",
             f"Unknown schema version {ledger['schema_version']!r}; expected {SCHEMA_VERSION}.",
             {"schema_version": ledger["schema_version"]})
    if not _int(ledger["revision"], "ledger.revision") or ledger["revision"] < 0:
        fail("invalid-record", "Ledger revision must be a nonnegative integer.",
             {"revision": ledger["revision"]})
    for field in ("assessments", "verifications", "conflict_dispositions"):
        if not isinstance(ledger[field], list):
            fail("invalid-record", f"Ledger {field} must be a list (append-only array).",
                 {"field": field})
        for index, record in enumerate(ledger[field]):
            if not isinstance(record, dict):
                fail("invalid-record",
                     f"{field}[{index}] must be an object.", {"field": field})
    if not isinstance(ledger["relations"], list):
        fail("invalid-record", "Ledger relations must be a list.", {"field": "relations"})
    if not isinstance(ledger["requirements"], dict) or not isinstance(ledger["artifacts"], dict):
        fail("invalid-record", "Requirements/artifacts must be ID maps.", {})
    for rid, record in ledger["requirements"].items():
        if not isinstance(record, dict):
            fail("invalid-record",
                 f"Requirement map entry {rid!r} must be an object.", {"key": rid})
        if rid != record.get("id") or not record.get("id", "").startswith("REQ-"):
            fail("invalid-record",
                 f"Requirement map key {rid!r} must match the record's REQ-<uuid> id.",
                 {"key": rid})
        validate_requirement(record, f"requirements.{rid}")
    for aid, record in ledger["artifacts"].items():
        if not isinstance(record, dict):
            fail("invalid-record",
                 f"Artifact map entry {aid!r} must be an object.", {"key": aid})
        if aid != record.get("id") or not record.get("id", "").startswith("ART-"):
            fail("invalid-record",
                 f"Artifact map key {aid!r} must match the record's ART-<uuid> id.",
                 {"key": aid})
        validate_artifact(record, f"artifacts.{aid}")
    for index, assessment in enumerate(ledger["assessments"]):
        validate_assessment(assessment, f"assessments[{index}]", repo_root)
    for index, verification in enumerate(ledger["verifications"]):
        validate_verification(verification, f"verifications[{index}]", repo_root)
    for index, disposition in enumerate(ledger["conflict_dispositions"]):
        validate_conflict_disposition(disposition, f"conflict_dispositions[{index}]")
    known = set(ledger["requirements"]) | set(ledger["artifacts"])
    identifiers = set()
    for index, relation in enumerate(ledger["relations"]):
        where = f"relations[{index}]"
        validate_relation(relation, where)
        if relation["id"] in identifiers:
            fail("invalid-record", f"{where}.id duplicates another relation id.",
                 {"id": relation["id"]})
        identifiers.add(relation["id"])
        for endpoint in ("source", "target"):
            if not is_uuid_id(relation[endpoint]):
                fail("invalid-record", f"{where}.{endpoint} must be a canonical ID.",
                     {endpoint: relation[endpoint]})
            if relation[endpoint] not in known:
                fail("broken-reference",
                     f"{where}.{endpoint} references unknown record {relation[endpoint]!r}.",
                     {"endpoint": endpoint, "id": relation[endpoint],
                      "relation_id": relation["id"]})
    validate_evidence_coupling(ledger)
    from .graphvalidate import validate_graph

    validate_graph(ledger, repo_root)
    return ledger


def validate_repo_locator(repo_root, locator):
    from .graphvalidate import validate_locator

    validate_locator(repo_root, locator)


def locator_file_exists(repo_root, locator):
    """Record-time contract: evidence/dependency locator paths must exist as files."""
    root = os.path.realpath(os.fspath(repo_root))
    parts = [part for part in locator.split("/") if part not in ("", ".")]
    return os.path.isfile(os.path.join(root, *parts))
