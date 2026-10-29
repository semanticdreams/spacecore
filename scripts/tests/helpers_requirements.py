"""Shared helpers for the requirements ledger CLI/library tests.

The ledger tool lives in ``scripts/requirements.py`` with its private library
``requirements_lib``. Tests may drive the real CLI as a subprocess (favored for
transaction/lock/CLI-contract behavior) or call the library in-process (favored
for schema rejection matrices); both entry points build the same repository-root
layout: ``<repo>/docs/requirements/ledger.json`` plus sibling artifacts.
"""

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "requirements.py"
LEDGER = "docs/requirements/ledger.json"

_LIB = None


def requirements_lib():
    """Import the ledger library in-process (an active module reference)."""
    global _LIB
    if _LIB is None:
        try:
            import scripts.requirements_lib as lib
        except ImportError:
            scripts_dir = str(REPO_ROOT / "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            import requirements_lib as lib
        _LIB = lib
    return _LIB


class CliResult:
    """Subprocess result plus lazily parsed JSON body."""

    def __init__(self, proc):
        self.returncode = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr

    @property
    def json(self):
        return json.loads(self.stdout)

    def error_code(self):
        return self.json["error"]["code"]


_AUTO_REVISION = "__auto_current_revision__"


def current_revision(repo_root):
    path = ledger_path(repo_root)
    if not path.exists():
        return 0
    return json.loads(path.read_text())["revision"]


def run_cli(repo_root, verb, *flags, request=None):
    """Run ``requirements.py <verb> --repo-root repo [flags]``.

    ``request`` given as dict/list is strict-JSON dumped into a request file;
    given as a raw string it is written verbatim (for malformed-input tests).
    An apply request with the default ``expected_revision`` sentinel resolves
    against the repository's current committed revision at invocation time;
    pinned revisions (including stale ones) are passed explicitly instead.
    """
    if (verb == "apply" and isinstance(request, dict)
            and request.get("expected_revision") == _AUTO_REVISION):
        request = dict(request, expected_revision=current_revision(repo_root))
    cmd = [sys.executable, str(SCRIPT), verb, "--repo-root", str(repo_root), *flags]
    env_file = None
    if request is not None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "request.json"
            env_file.write_text(
                request if isinstance(request, str) else json.dumps(request, sort_keys=True)
            )
            cmd += ["--request", str(env_file)]
            return CliResult(subprocess.run(cmd, capture_output=True, text=True))
    return CliResult(subprocess.run(cmd, capture_output=True, text=True))


def ledger_path(repo_root):
    return Path(repo_root) / LEDGER


def read_ledger_bytes(repo_root):
    return ledger_path(repo_root).read_bytes()


def write_ledger_bytes(repo_root, blob):
    path = ledger_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)


def write_ledger(repo_root, ledger):
    blob = json.dumps(ledger, indent=2, sort_keys=True, allow_nan=False) + "\n"
    write_ledger_bytes(repo_root, blob.encode("utf-8"))


def base_ledger():
    return {
        "schema_version": 1,
        "revision": 0,
        "requirements": {},
        "artifacts": {},
        "relations": [],
        "assessments": [],
        "verifications": [],
        "conflict_dispositions": [],
    }


def provenance(date="2026-10-29"):
    return {
        "source_reference": "docs/plans/example.md",
        "actor": "implementer",
        "date": date,
        "origin": "user_intent",
    }


def make_requirement(rid=None, lifecycle="proposed", **overrides):
    record = {
        "id": rid or f"REQ-{uuid.uuid4()}",
        "classification": "capability",
        "statement": "The tool validates stored requirements strictly.",
        "rationale": "Strict storage is the reviewed design contract.",
        "acceptance_criteria": [
            {"id": "c1", "text": "Strict loader rejects malformed records.",
             "applicability": "analytical"},
        ],
        "provenance": provenance(),
        "lifecycle": lifecycle,
        "revision": 1,
        "history": [],
    }
    record.update(overrides)
    return record


def make_artifact(rid=None, kind="design", **overrides):
    record = {
        "id": rid or f"ART-{uuid.uuid4()}",
        "kind": kind,
        "title": "Ledger design",
        "locator": "docs/design-notes.md",
    }
    record.update(overrides)
    return record


def make_relation(rid=None, rtype="contributes_to", source=None, target=None, **overrides):
    record = {
        "id": rid or f"REL-{uuid.uuid4()}",
        "type": rtype,
        "source": source,
        "target": target,
        "rationale": "Uncontroversial shared purpose.",
        "provenance": provenance(),
        "confidence": "explicit",
    }
    record.update(overrides)
    return record


def create_op(**overrides):
    args = {
        "classification": "capability",
        "statement": "The tool validates stored requirements strictly.",
        "rationale": "Strict storage is the reviewed design contract.",
        "provenance": provenance(),
        "acceptance_criteria": [
            {"id": "c1", "text": "Strict loader rejects malformed records.",
             "applicability": "analytical"},
        ],
    }
    args.update(overrides)
    return {"op": "create-requirement", "args": args}


def apply_request(*ops, expected_revision=_AUTO_REVISION, actor="test-actor"):
    return {"actor": actor, "expected_revision": expected_revision, "ops": list(ops)}


def init_ok(repo):
    result = run_cli(repo, "init")
    assert result.returncode == 0, result.stdout + result.stderr
    return result
