"""Deterministic ledger-only Markdown projection (no volatile content checks).

Projection writes run under the canonical writer lock. Apply passes its committed
in-memory ledger while holding that same lock, avoiding an older writer replacing
a newer projection. Check-only never creates directories, locks or output files.
"""

import contextlib
import html
import os
import uuid
from pathlib import Path

from . import RequirementsError, schema

DEFAULT_PROJECTION = "docs/requirements/index.md"


def validate_distinct_destinations(repo_root, canonical_path):
    """Reject resolved canonical/projection aliases before either replacement."""
    projection_path = Path(repo_root) / DEFAULT_PROJECTION
    if (os.path.normcase(os.path.realpath(canonical_path))
            == os.path.normcase(os.path.realpath(projection_path))):
        raise RequirementsError(
            "ledger-projection-collision",
            "Canonical ledger and derived projection must have distinct resolved paths; no replacement performed.",
            {"ledger": os.fspath(canonical_path), "projection": DEFAULT_PROJECTION})


def _cell(value):
    return html.escape(str(value), quote=False).replace("|", "&#124;").replace("\r", "").replace("\n", "<br>")


def markdown(ledger):
    lines = ["# Requirements index", "", "> Generated from the canonical ledger; do not edit.",
             "", f"Revision: {ledger['revision']}", "",
             "Trace links, lifecycle and observations never imply satisfaction.", "",
             "## Requirements", "", "| ID | Classification | Lifecycle | Revision | Statement |",
             "| --- | --- | --- | --- | --- |"]
    for rid, req in sorted(ledger["requirements"].items()):
        lines.append("| " + " | ".join(_cell(v) for v in (rid, req["classification"], req["lifecycle"], req["revision"], req["statement"])) + " |")
    lines += ["", "## Artifacts", "", "| ID | Kind | Title | Locator |", "| --- | --- | --- | --- |"]
    for aid, art in sorted(ledger["artifacts"].items()):
        lines.append("| " + " | ".join(_cell(v) for v in (aid, art["kind"], art["title"], art["locator"])) + " |")
    lines += ["", "## Relations", "", "| ID | Type | Source → Target | Confidence | Rationale |", "| --- | --- | --- | --- | --- |"]
    for edge in sorted(ledger["relations"], key=lambda r: r["id"]):
        if not edge.get("retracted"):
            lines.append("| " + " | ".join(_cell(v) for v in (edge["id"], edge["type"], edge["source"] + " → " + edge["target"], edge["confidence"], edge["rationale"])) + " |")
    return "\n".join(lines) + "\n"


def write_projection(repo_root, ledger):
    schema.validate_repo_locator(repo_root, DEFAULT_PROJECTION)
    path = Path(repo_root) / DEFAULT_PROJECTION
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(markdown(ledger))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def refresh_committed(repo_root, ledger):
    try:
        write_projection(repo_root, ledger)
    except (OSError, UnicodeError, RequirementsError) as exc:
        raise RequirementsError("projection-stale",
            "Canonical ledger committed; derived projection is stale. Run render to recover.",
            {"committed_revision": ledger["revision"], "projection_stale": True,
             "projection": DEFAULT_PROJECTION, "reason": str(exc)}) from exc


def render(repo_root, ledger_path=None, check=False):
    from .store import ledger_file, load_ledger
    from .locking import writer_lock

    path = Path(repo_root) / DEFAULT_PROJECTION
    if check:
        ledger = load_ledger(repo_root, ledger_path)
        validate_distinct_destinations(repo_root, ledger_file(repo_root, ledger_path))
        schema.validate_repo_locator(repo_root, DEFAULT_PROJECTION)
        try:
            actual = path.read_bytes()
        except FileNotFoundError:
            actual = None
        except OSError as exc:
            raise RequirementsError("storage-error", f"Cannot read projection: {exc}", {}) from exc
        try:
            expected = markdown(ledger).encode("utf-8")
        except UnicodeError as exc:
            raise RequirementsError("projection-stale", "Cannot encode projection; check-only made no changes.",
                {"committed_revision": ledger["revision"], "projection_stale": True,
                 "projection": DEFAULT_PROJECTION, "reason": str(exc)}) from exc
        if actual != expected:
            raise RequirementsError("projection-stale", "Projection missing or stale; check-only made no changes.",
                {"committed_revision": ledger["revision"], "projection_stale": True})
    else:
        load_ledger(repo_root, ledger_path)  # fail before lock creation if absent
        with writer_lock(ledger_file(repo_root, ledger_path)):
            ledger = load_ledger(repo_root, ledger_path)
            validate_distinct_destinations(repo_root, ledger_file(repo_root, ledger_path))
            refresh_committed(repo_root, ledger)
    return {"status": "ok", "revision": ledger["revision"],
            "result": {"projection": DEFAULT_PROJECTION, "current": True, "check_only": check}}
