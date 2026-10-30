"""Evidence freshness and per-criterion verification reports.

Pure computation over an already-validated ledger plus the repository
contents: latest applicable observation per acceptance criterion governs, an
older pass never hides a later failed/inconclusive/pending result, and
currency depends only on the requirement revision, evidence content and declared
dependency content identities — never on unrelated repository churn or Git HEAD. Stored
procedures are data only: this module never executes them, and reports never
derive satisfaction claims from results or lifecycle.
"""

import hashlib
import os

from . import schema

FRESH = "fresh"
STALE = "stale"
UNKNOWN = "unknown"


def criteria_latest(ledger, requirement_id, repo_root):
    """Latest applicable observation and currency per current criterion."""
    requirement = ledger["requirements"].get(requirement_id)
    if requirement is None:
        schema.fail("not-found", f"No requirement {requirement_id!r} in the ledger.",
                    {"id": requirement_id})
    report = {}
    for criterion in requirement["acceptance_criteria"]:
        report[criterion["id"]] = _criterion_report(
            ledger, requirement, criterion, repo_root)
    return report


def _criterion_report(ledger, requirement, criterion, repo_root):
    own_records = [
        verification for verification in ledger["verifications"]
        if verification["requirement_id"] == requirement["id"]
        and verification["criterion_id"] == criterion["id"]
    ]
    snapshot = {
        "criterion": {"id": criterion["id"],
                      "applicability": criterion["applicability"]},
        "observations": len(own_records),
        "result": "absent",
        "currency": "unknown",
    }
    if not own_records:
        return snapshot
    applicable = [record for record in own_records
                  if record["requirement_revision"] == requirement["revision"]]
    # Prefer the applicable normative revision, then observation time. Stable
    # append order breaks ties without hiding an imported newer observation.
    latest = max(enumerate(applicable or own_records),
                 key=lambda item: (item[1]["timestamp"], item[0]))[1]
    snapshot.update({
        "result": latest["result"],
        "currency": _currency(latest, requirement, ledger, repo_root),
        "method": latest["method"],
        "requirement_revision": latest["requirement_revision"],
        "timestamp": latest["timestamp"],
        "actor": latest["actor"],
        "evidence_ref": latest["evidence_ref"],
    })
    return snapshot


def _currency(latest, requirement, ledger, repo_root):
    if latest["requirement_revision"] != requirement["revision"]:
        return "stale"
    ref = latest["evidence_ref"]
    locator = (ref["locator"] if "locator" in ref
               else ledger["artifacts"][ref["artifact_id"]]["locator"])
    states = [_locator_state(locator, latest["evidence_digest"], repo_root)]
    states.extend(_dependency_state(key, expected, ledger, repo_root)
                  for key, expected in latest["dependency_digests"].items())
    if not latest["dependency_digests"]:
        states.append(UNKNOWN)
    if STALE in states:
        return "stale"
    if UNKNOWN in states:
        return "unknown"
    return "current"


def _dependency_state(key, expected, ledger, repo_root):
    artifact = ledger["artifacts"].get(key)
    if artifact is not None:
        registered = artifact.get("content_digest")
        if registered and registered != expected:
            return STALE
        return _locator_state(artifact["locator"], expected, repo_root)
    return _locator_state(key, expected, repo_root)


def _locator_state(locator, expected, repo_root):
    schema.validate_repo_locator(repo_root, locator)
    path = os.path.join(os.fspath(repo_root), locator)
    if not os.path.isfile(path):
        return UNKNOWN
    return STALE if content_digest(repo_root, locator) != expected else FRESH


def content_digest(repo_root, locator):
    """Hash safe local content only; references and procedures never execute."""
    schema.validate_repo_locator(repo_root, locator)
    path = os.path.join(os.fspath(repo_root), locator)
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError as exc:
        raise schema.RequirementsError(
            "storage-error", f"Cannot read evidence/dependency {locator!r}: {exc}",
            {"locator": locator}) from exc
    return digest.hexdigest()
