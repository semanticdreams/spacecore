"""Canonical ledger storage, transactions and mutation operations.

Strict flow per the reviewed design: every apply acquires the advisory writer
lock, loads the ledger, compares the expected revision, applies operations,
validates the complete candidate, and atomically replaces the canonical file.
Stale writers and failed replacement preserve canonical bytes; reads never
write; initialization refuses an existing ledger.
"""

import contextlib
import copy
import json
import os
import uuid
from datetime import datetime, timezone

from . import RequirementsError, schema
from .graphvalidate import canonical_conflict_pair, check_endpoint, check_self_edge
from .locking import writer_lock

DEFAULT_LEDGER = os.path.join("docs", "requirements", "ledger.json")

OPERATIONS = (
    "create-requirement",
    "revise-requirement",
    "transition-requirement",
    "supersede-requirement",
    "register-artifact",
    "update-artifact",
    "add-relation",
    "revise-relation",
    "retract-relation",
    "record-assessment",
    "record-verification",
    "record-conflict-disposition",
)


# ---------------------------------------------------------------------------
# Paths and raw storage
# ---------------------------------------------------------------------------


def ledger_file(repo_root, ledger_path=None):
    root = os.fspath(repo_root)
    relative = ledger_path or DEFAULT_LEDGER
    return relative if os.path.isabs(relative) else os.path.join(root, relative)


def base_ledger():
    return {
        "schema_version": schema.SCHEMA_VERSION,
        "revision": 0,
        "requirements": {},
        "artifacts": {},
        "relations": [],
        "assessments": [],
        "verifications": [],
        "conflict_dispositions": [],
    }


def init_ledger(repo_root, ledger_path=None):
    root = os.fspath(repo_root)
    path = ledger_file(root, ledger_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with writer_lock(path):
        if os.path.exists(path):
            raise RequirementsError(
                "already-initialized",
                f"Ledger already exists at {path}; initialization refuses to overwrite.",
                {"ledger": path},
            )
        ledger = base_ledger()
        schema.validate_ledger(ledger, root)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        _atomic_write(path, ledger)
    return {"status": "ok", "revision": 0, "result": {"ledger": path}}


def load_ledger(repo_root, ledger_path=None):
    """Load and fully validate the canonical ledger; strict, read-only."""
    root = os.fspath(repo_root)
    path = ledger_file(root, ledger_path)
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except FileNotFoundError as exc:
        raise RequirementsError(
            "ledger-missing",
            f"No requirements ledger at {path}. Run 'init' before reading or applying.",
            {"ledger": path},
        ) from exc
    except OSError as exc:
        raise RequirementsError(
            "storage-error", f"Cannot read the ledger at {path}: {exc}.",
            {"ledger": path},
        ) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RequirementsError(
            "invalid-json", f"Ledger at {path} is not UTF-8.", {"ledger": path},
        ) from exc
    context = path if os.path.isabs(path) else os.path.relpath(path, root)
    data = schema.strict_json_loads(text, context)
    return schema.validate_ledger(data, root)


def fsync_directory(directory):
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path, ledger):
    payload = (json.dumps(ledger, allow_nan=False, indent=2, sort_keys=True)
               + "\n").encode("utf-8")
    directory = os.path.dirname(path) or "."
    tmp = os.path.join(
        directory, f".{os.path.basename(path)}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    except OSError as exc:
        raise RequirementsError(
            "storage-write-failed",
            f"Cannot stage canonical ledger replacement {tmp}.",
            {"ledger": path, "temp": tmp, "reason": str(exc)},
        ) from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise RequirementsError(
            "storage-write-failed",
            f"Atomic replacement of {path} failed; canonical bytes preserved.",
            {"ledger": path, "temp": tmp, "reason": str(exc)},
        ) from exc
    with contextlib.suppress((AttributeError, OSError)):
        fsync_directory(directory)
    return payload


# ---------------------------------------------------------------------------
# Apply/query entry points
# ---------------------------------------------------------------------------


_ENVELOPE_KEYS = ("actor", "expected_revision", "ops")


def _validate_apply_envelope(request):
    if not isinstance(request, dict) or set(request) != set(_ENVELOPE_KEYS):
        raise RequirementsError(
            "invalid-request",
            f"Apply request must be an object with exactly {list(_ENVELOPE_KEYS)}.",
            {"keys": sorted(request) if isinstance(request, dict) else None},
        )
    actor = request["actor"]
    if not isinstance(actor, str) or not actor.strip():
        raise RequirementsError("invalid-request",
                                "Apply request needs a nonempty actor.", {})
    revision = request["expected_revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise RequirementsError(
            "invalid-request",
            "Apply request needs a nonnegative integer expected_revision.",
            {"expected_revision": revision},
        )
    ops = request["ops"]
    if not isinstance(ops, list) or not ops:
        raise RequirementsError(
            "invalid-request", "Apply request needs a nonempty ops list.", {})
    for index, spec in enumerate(ops):
        if not isinstance(spec, dict) or set(spec) != {"op", "args"}:
            raise RequirementsError(
                "invalid-request",
                f"ops[{index}] must be an object with exactly 'op' and 'args'.",
                {"index": index},
            )
        if spec["op"] not in OPERATIONS:
            raise RequirementsError(
                "invalid-op",
                f"Unknown operation {spec['op']!r}; supported: {OPERATIONS}.",
                {"index": index, "op": spec["op"]},
            )
        if not isinstance(spec["args"], dict):
            raise RequirementsError(
                "invalid-request", f"ops[{index}].args must be an object.",
                {"index": index},
            )


def apply(repo_root, request, ledger_path=None):
    """Apply a mutation request transactionally; one committed revision."""
    root = os.fspath(repo_root)
    _validate_apply_envelope(request)
    path = ledger_file(root, ledger_path)
    if not os.path.isfile(path):
        raise RequirementsError(
            "ledger-missing",
            f"No requirements ledger at {path}; reads and mutations never initialize.",
            {"ledger": path},
        )
    with writer_lock(path):
        ledger = load_ledger(root, ledger_path)
        committed = ledger["revision"]
        if committed != request["expected_revision"]:
            raise RequirementsError(
                "expected-revision-stale",
                f"Ledger revision {committed} does not match expected "
                f"{request['expected_revision']}; canonical bytes preserved.",
                {"expected_revision": request["expected_revision"],
                 "committed_revision": committed},
            )
        state = copy.deepcopy(ledger)
        results = []
        for spec in request["ops"]:
            results.append(
                _OPERATIONS[spec["op"]](state, spec["args"], request["actor"], root))
        state["revision"] = committed + 1
        schema.validate_ledger(state, root)
        _atomic_write(path, state)
    return {"status": "ok", "revision": state["revision"], "result": {"ops": results}}


def query(repo_root, request, ledger_path=None):
    """Read-only query; never initializes, repairs or writes."""
    root = os.fspath(repo_root)
    if not isinstance(request, dict) or set(request) != {"op", "args"}:
        raise RequirementsError(
            "invalid-request",
            "Query request must be an object with exactly 'op' and 'args'.",
            {"keys": sorted(request) if isinstance(request, dict) else None},
        )
    if request["op"] != "get":
        raise RequirementsError(
            "invalid-op",
            f"Unknown query operation {request['op']!r}; Task 1 supports ('get',).",
            {"op": request["op"]},
        )
    args = request["args"]
    if (not isinstance(args, dict) or set(args) != {"id"}
            or not isinstance(args.get("id"), str) or not args["id"].strip()):
        raise RequirementsError(
            "invalid-op-args",
            "Query get needs exactly one nonempty 'id' string argument.",
            {"args": sorted(args) if isinstance(args, dict) else args},
        )
    ledger = load_ledger(root, ledger_path)
    target = args["id"]
    if target in ledger["requirements"]:
        from .evidence import criteria_latest

        result = {"requirement": ledger["requirements"][target],
                  "criteria_latest": criteria_latest(ledger, target, root)}
    elif target in ledger["artifacts"]:
        result = {"artifact": ledger["artifacts"][target]}
    else:
        raise RequirementsError("not-found", f"No record {target!r} in the ledger.",
                                {"id": target})
    return {"status": "ok", "revision": ledger["revision"], "result": result}


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------


def _args(spec_args, required, optional, op):
    unknown = set(spec_args) - set(required) - set(optional)
    if unknown:
        raise RequirementsError(
            "invalid-op-args",
            f"{op} args carry unknown fields: {sorted(unknown)}.",
            {"op": op, "unknown": sorted(unknown)},
        )
    missing = [key for key in required if key not in spec_args]
    if missing:
        raise RequirementsError(
            "invalid-op-args", f"{op} args miss required fields: {missing}.",
            {"op": op, "missing": missing},
        )


def _nonempty(value):
    return isinstance(value, str) and value.strip() != ""


def _op_date(args, op):
    if "date" not in args:
        return datetime.now(timezone.utc).date().isoformat()
    if not schema.valid_date(args["date"]):
        raise RequirementsError(
            "invalid-op-args", f"{op} args date must be an ISO 'YYYY-MM-DD' value.",
            {"op": op, "date": args["date"]},
        )
    return args["date"]


def _or_not_found(collection, record_id, kind):
    if record_id not in collection:
        raise RequirementsError("not-found", f"No {kind} {record_id!r} in the ledger.",
                                {"id": record_id})
    return collection[record_id]


def _build_requirement(record_id, args, context):
    record = {
        "id": record_id,
        "classification": args["classification"],
        "statement": args["statement"],
        "rationale": args["rationale"],
        "acceptance_criteria": args.get("acceptance_criteria", []),
        "provenance": args["provenance"],
        "lifecycle": "proposed",
        "revision": 1,
        "history": [],
    }
    schema.validate_requirement(record, context)
    return record


def _op_create_requirement(state, args, actor, root):
    _args(args, ("classification", "statement", "rationale", "provenance"),
          ("acceptance_criteria",), "create-requirement")
    record_id = schema.new_uuid_id("REQ")
    record = _build_requirement(record_id, args, f"requirements.{record_id}")
    state["requirements"][record_id] = record
    return {"op": "create-requirement", "id": record_id}


_REVISABLE = ("statement", "classification", "acceptance_criteria", "rationale",
              "provenance")


def _op_revise_requirement(state, args, actor, root):
    _args(args, ("id", "reason"), _REVISABLE + ("date",), "revise-requirement")
    record = _or_not_found(state["requirements"], args["id"], "requirement")
    if record["lifecycle"] in ("superseded", "rejected"):
        raise RequirementsError(
            "terminal-record",
            f"Requirement {record['id']} is {record['lifecycle']}; terminal records "
            "cannot be revised or resurrected.",
            {"id": record["id"], "lifecycle": record["lifecycle"]},
        )
    if not [key for key in _REVISABLE if key in args]:
        raise RequirementsError(
            "invalid-op-args",
            "revise-requirement needs at least one change field "
            "(statement/classification/acceptance_criteria/rationale/provenance).",
            {"op": "revise-requirement"},
        )
    prior = {key: record[key] for key in _REVISABLE}
    updated = dict(record)
    for key in _REVISABLE:
        if key in args:
            updated[key] = args[key]
    updated["revision"] = record["revision"] + 1
    schema.validate_requirement(updated, f"requirements.{updated['id']}")
    updated["history"].append({
        "kind": "revision",
        "from_revision": record["revision"],
        "to_revision": updated["revision"],
        "reason": args["reason"],
        "actor": actor,
        "date": _op_date(args, "revise-requirement"),
        "prior": prior,
    })
    state["requirements"][record["id"]] = updated
    return {"op": "revise-requirement", "id": record["id"],
            "revision": updated["revision"]}


def _op_transition_requirement(state, args, actor, root):
    _args(args, ("id", "to", "reason", "authority"), ("date",),
          "transition-requirement")
    record = _or_not_found(state["requirements"], args["id"], "requirement")
    target = args["to"]
    if target not in schema.LIFECYCLES:
        raise RequirementsError(
            "invalid-transition",
            f"Unknown lifecycle {target!r}; allowed: {schema.LIFECYCLES}.",
            {"to": target, "id": record["id"]},
        )
    if target not in schema.ALLOWED_TRANSITIONS[record["lifecycle"]]:
        raise RequirementsError(
            "invalid-transition",
            f"Cannot transition {record['lifecycle']!r} to {target!r}; supersession "
            "must use the supersede-requirement operation and terminal records are final.",
            {"id": record["id"], "from": record["lifecycle"], "to": target},
        )
    for field in ("reason", "authority"):
        if not _nonempty(args[field]):
            raise RequirementsError(
                "invalid-op-args",
                f"transition-requirement requires grounded nonempty {field}.",
                {"op": "transition-requirement", "field": field},
            )
    origin = record["lifecycle"]
    record["lifecycle"] = target
    record["history"].append({
        "kind": "transition",
        "from_lifecycle": origin,
        "to_lifecycle": target,
        "reason": args["reason"],
        "authority": args["authority"],
        "actor": actor,
        "date": _op_date(args, "transition-requirement"),
    })
    return {"op": "transition-requirement", "id": record["id"], "to": target}


def _op_supersede_requirement(state, args, actor, root):
    _args(args, ("old_id", "reason", "authority", "provenance"),
          ("create", "replacement_id", "date"), "supersede-requirement")
    _require_nonempty(args, ("reason", "authority"), "supersede-requirement")
    if ("create" in args) == ("replacement_id" in args):
        raise RequirementsError(
            "invalid-op-args",
            "supersede-requirement needs exactly one of 'create' or 'replacement_id'.",
            {"op": "supersede-requirement"},
        )
    old = _or_not_found(state["requirements"], args["old_id"], "requirement")
    if old["lifecycle"] in ("superseded", "rejected"):
        raise RequirementsError(
            "terminal-record",
            f"Requirement {old['id']} is already {old['lifecycle']}.",
            {"id": old["id"], "lifecycle": old["lifecycle"]},
        )
    if "create" in args:
        create = args["create"]
        _args(create, ("classification", "statement", "rationale", "provenance"),
              ("acceptance_criteria",), "supersede-requirement create")
        replacement = _build_requirement(schema.new_uuid_id("REQ"), create,
                                         "supersede.create")
        state["requirements"][replacement["id"]] = replacement
    else:
        replacement = _or_not_found(state["requirements"], args["replacement_id"],
                                    "requirement")
        if replacement["lifecycle"] in ("superseded", "rejected"):
            raise RequirementsError(
                "terminal-record",
                f"Replacement {replacement['id']} is {replacement['lifecycle']}.",
                {"id": replacement["id"]},
            )
    relation_id = schema.new_uuid_id("REL")
    relation = {
        "id": relation_id,
        "type": "supersedes",
        "source": replacement["id"],
        "target": old["id"],
        "rationale": args["reason"],
        "provenance": args["provenance"],
        "confidence": "explicit",
        "retracted": False,
        "history": [],
    }
    schema.validate_relation(relation, f"relations[{relation_id}]")
    check_self_edge(relation)
    check_endpoint(state, relation)
    state["relations"].append(relation)
    old["history"].append({
        "kind": "transition",
        "from_lifecycle": old["lifecycle"],
        "to_lifecycle": "superseded",
        "reason": args["reason"],
        "authority": args["authority"],
        "actor": actor,
        "date": _op_date(args, "supersede-requirement"),
    })
    old["lifecycle"] = "superseded"
    return {"op": "supersede-requirement", "id": replacement["id"],
            "superseded": old["id"]}


def _op_register_artifact(state, args, actor, root):
    _args(args, ("kind", "title", "locator"), ("selector", "content_digest"),
          "register-artifact")
    record_id = schema.new_uuid_id("ART")
    record = dict(args)
    record["id"] = record_id
    schema.validate_artifact(record, f"artifacts.{record_id}")
    state["artifacts"][record_id] = record
    return {"op": "register-artifact", "id": record_id}


def _op_update_artifact(state, args, actor, root):
    _args(args, ("id",), ("title", "locator", "selector", "content_digest"),
          "update-artifact")
    record = _or_not_found(state["artifacts"], args["id"], "artifact")
    if not [key for key in ("title", "locator", "selector", "content_digest")
            if key in args]:
        raise RequirementsError(
            "invalid-op-args",
            "update-artifact needs at least one change field "
            "(title/locator/selector/content_digest).",
            {"op": "update-artifact"},
        )
    updated = dict(record)
    for key in ("title", "locator", "selector", "content_digest"):
        if key in args:
            updated[key] = args[key]
    schema.validate_artifact(updated, f"artifacts.{updated['id']}")
    state["artifacts"][record["id"]] = updated
    return {"op": "update-artifact", "id": record["id"]}


def _op_add_relation(state, args, actor, root):
    _args(args, ("type", "source", "target", "rationale", "provenance", "confidence"),
          (), "add-relation")
    record_id = schema.new_uuid_id("REL")
    source, target = args["source"], args["target"]
    if args["type"] == "conflicts_with":
        source, target = canonical_conflict_pair(source, target)
    relation = {
        "id": record_id,
        "type": args["type"],
        "source": source,
        "target": target,
        "rationale": args["rationale"],
        "provenance": args["provenance"],
        "confidence": args["confidence"],
        "retracted": False,
        "history": [],
    }
    schema.validate_relation(relation, f"relations[{record_id}]")
    check_self_edge(relation)
    check_endpoint(state, relation)
    state["relations"].append(relation)
    return {"op": "add-relation", "id": record_id}


def _find_relation(state, relation_id):
    for relation in state["relations"]:
        if relation["id"] == relation_id:
            return relation
    raise RequirementsError("not-found", f"No relation {relation_id!r}.",
                            {"id": relation_id})


def _op_revise_relation(state, args, actor, root):
    _args(args, ("id", "reason"), ("confidence", "rationale", "date"),
          "revise-relation")
    relation = _find_relation(state, args["id"])
    if relation.get("retracted"):
        raise RequirementsError(
            "invalid-op-args",
            f"Relation {relation['id']} is retracted; revise the retained lineage or "
            "record a fresh relation.",
            {"id": relation["id"]},
        )
    if not [key for key in ("confidence", "rationale") if key in args]:
        raise RequirementsError(
            "invalid-op-args",
            "revise-relation needs at least one change field "
            "(confidence/rationale).",
            {"op": "revise-relation"},
        )
    prior = {"rationale": relation["rationale"], "confidence": relation["confidence"]}
    for key in ("rationale", "confidence"):
        if key in args:
            relation[key] = args[key]
    schema.validate_relation(relation, f"relations[{relation['id']}]")
    relation["history"].append({
        "action": "update",
        "reason": args["reason"],
        "actor": actor,
        "date": _op_date(args, "revise-relation"),
        "prior": prior,
    })
    return {"op": "revise-relation", "id": relation["id"]}


def _op_retract_relation(state, args, actor, root):
    _args(args, ("id", "reason"), ("date",), "retract-relation")
    relation = _find_relation(state, args["id"])
    if relation.get("retracted"):
        raise RequirementsError(
            "invalid-op-args", f"Relation {relation['id']} is already retracted.",
            {"id": relation["id"]},
        )
    prior = {"rationale": relation["rationale"], "confidence": relation["confidence"]}
    relation["retracted"] = True
    relation["history"].append({
        "action": "retract",
        "reason": args["reason"],
        "actor": actor,
        "date": _op_date(args, "retract-relation"),
        "prior": prior,
    })
    return {"op": "retract-relation", "id": relation["id"]}


def _own_requirement(args, state, op):
    if (not schema.is_uuid_id(args["requirement_id"])
            or not args["requirement_id"].startswith("REQ-")):
        raise RequirementsError(
            "invalid-op-args", "Expected a canonical requirement ID.", {})
    record = _or_not_found(state["requirements"], args["requirement_id"],
                           "requirement")
    if args["requirement_revision"] != record["revision"]:
        raise RequirementsError(
            "invalid-op-args",
            f"{op} must reference the requirement's current revision "
            f"{record['revision']}, not {args.get('requirement_revision')!r}.",
            {"op": op, "requirement_id": record["id"],
             "current_revision": record["revision"],
             "given_revision": args.get("requirement_revision")},
        )
    return record


def _require_nonempty(args, fields, op):
    for field in fields:
        if not _nonempty(args[field]):
            raise RequirementsError(
                "invalid-op-args",
                f"{op} requires grounded nonempty {field}.",
                {"op": op, "field": field},
            )


def _op_record_assessment(state, args, actor, root):
    _args(args, ("requirement_id", "requirement_revision", "state", "rationale",
                 "source_refs"), ("date",), "record-assessment")
    _require_nonempty(args, ("rationale",), "record-assessment")
    _own_requirement(args, state, "record-assessment")
    if not isinstance(args["source_refs"], list) or not args["source_refs"]:
        raise RequirementsError(
            "invalid-op-args",
            "record-assessment requires a nonempty source_refs list.",
            {"op": "record-assessment"},
        )
    entry = {
        "requirement_id": args["requirement_id"],
        "requirement_revision": args["requirement_revision"],
        "state": args["state"],
        "rationale": args["rationale"],
        "actor": actor,
        "date": _op_date(args, "record-assessment"),
        "source_refs": args["source_refs"],
    }
    schema.validate_assessment(entry, f"assessments[{len(state['assessments'])}]",
                               root)
    state["assessments"].append(entry)
    return {"op": "record-assessment", "requirement_id": entry["requirement_id"],
            "state": entry["state"]}


def _op_record_verification(state, args, actor, root):
    _args(args, ("requirement_id", "requirement_revision", "criterion_id", "method",
                 "result", "procedure", "environment", "observation", "timestamp",
                 "evidence_ref", "dependency_digests"), (), "record-verification")
    _require_nonempty(args, ("procedure", "environment", "observation"),
                      "record-verification")
    if not isinstance(args["dependency_digests"], dict):
        raise RequirementsError(
            "invalid-op-args",
            "record-verification dependency_digests must be an object.",
            {"op": "record-verification"},
        )
    for key, value in args["dependency_digests"].items():
        if not (isinstance(key, str) and _nonempty(value)):
            raise RequirementsError(
                "invalid-op-args",
                "record-verification dependency_digests must map artifact IDs "
                "or locators to nonempty digest strings.",
                {"op": "record-verification", "key": key},
            )
    record = _own_requirement(args, state, "record-verification")
    if not isinstance(args["evidence_ref"], dict):
        raise RequirementsError(
            "invalid-op-args",
            "record-verification evidence_ref must be an object naming exactly "
            "one of 'locator' or 'artifact_id'.",
            {"op": "record-verification"},
        )
    # Record-time contracts: evidence and declared dependency locators must
    # describe files that exist now (load-time checks verify safety only).
    evidence_ref = args["evidence_ref"]
    schema.validate_ref(evidence_ref, "record-verification.evidence_ref", root)
    evidence_locator = evidence_ref.get("locator")
    if "artifact_id" in evidence_ref:
        artifact = state["artifacts"].get(evidence_ref["artifact_id"])
        if artifact is None:
            raise RequirementsError("broken-reference", "Evidence artifact is not registered.", {})
        evidence_locator = artifact["locator"]
    if evidence_locator is not None:
        schema.validate_repo_locator(root, evidence_locator)
        if not schema.locator_file_exists(root, evidence_locator):
            raise RequirementsError(
                "invalid-evidence-ref",
                f"Evidence locator {evidence_locator!r} does not exist in the "
                "repository and cannot anchor a durable verification.",
                {"op": "record-verification", "locator": evidence_locator},
            )
    for key in args["dependency_digests"]:
        if not str(key).startswith("ART-"):
            schema.validate_repo_locator(root, key)
            if not schema.locator_file_exists(root, key):
                raise RequirementsError(
                    "invalid-op-args",
                    f"Declared dependency locator {key!r} does not exist in the "
                    "repository.",
                    {"op": "record-verification", "locator": key},
                )
    if schema.criterion_at_revision(record, args["requirement_revision"],
                                    args["criterion_id"]) is None:
        raise RequirementsError(
            "invalid-op-args",
            f"Criterion {args['criterion_id']!r} does not exist on requirement "
            f"{record['id']} at revision {args['requirement_revision']}.",
            {"op": "record-verification", "criterion_id": args["criterion_id"],
             "requirement_revision": args["requirement_revision"]},
        )
    entry = {
        "requirement_id": args["requirement_id"],
        "requirement_revision": args["requirement_revision"],
        "criterion_id": args["criterion_id"],
        "method": args["method"],
        "result": args["result"],
        "procedure": args["procedure"],
        "environment": args["environment"],
        "observation": args["observation"],
        "timestamp": args["timestamp"],
        "evidence_ref": args["evidence_ref"],
        "dependency_digests": args["dependency_digests"],
        "actor": actor,
    }
    from .evidence import content_digest

    entry["evidence_digest"] = content_digest(root, evidence_locator)
    schema.validate_verification(
        entry, f"verifications[{len(state['verifications'])}]", root)
    schema.check_method_applicability(record, entry)
    state["verifications"].append(entry)
    return {"op": "record-verification", "requirement_id": entry["requirement_id"],
            "criterion_id": entry["criterion_id"], "result": entry["result"]}


def _op_record_conflict_disposition(state, args, actor, root):
    _args(args, ("relation_id", "explanation", "authority"), ("date",),
          "record-conflict-disposition")
    _require_nonempty(args, ("explanation", "authority"),
                      "record-conflict-disposition")
    relation = _find_relation(state, args["relation_id"])
    if relation["type"] != "conflicts_with" or relation.get("retracted"):
        raise RequirementsError(
            "invalid-op-args",
            "record-conflict-disposition requires an active conflicts_with "
            "relation.",
            {"op": "record-conflict-disposition", "relation_id": relation["id"],
             "relation_type": relation["type"],
             "retracted": bool(relation.get("retracted"))},
        )
    entry = {
        "relation_id": relation["id"],
        "explanation": args["explanation"],
        "authority": args["authority"],
        "actor": actor,
        "date": _op_date(args, "record-conflict-disposition"),
    }
    schema.validate_conflict_disposition(
        entry, f"conflict_dispositions[{len(state['conflict_dispositions'])}]")
    state["conflict_dispositions"].append(entry)
    return {"op": "record-conflict-disposition",
            "relation_id": entry["relation_id"]}


_OPERATIONS = {
    "create-requirement": _op_create_requirement,
    "revise-requirement": _op_revise_requirement,
    "transition-requirement": _op_transition_requirement,
    "supersede-requirement": _op_supersede_requirement,
    "register-artifact": _op_register_artifact,
    "update-artifact": _op_update_artifact,
    "add-relation": _op_add_relation,
    "revise-relation": _op_revise_relation,
    "retract-relation": _op_retract_relation,
    "record-assessment": _op_record_assessment,
    "record-verification": _op_record_verification,
    "record-conflict-disposition": _op_record_conflict_disposition,
}
