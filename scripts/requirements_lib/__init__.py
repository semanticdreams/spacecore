"""Requirements ledger library: strict schema, graph validation and storage.

Shared entry points (per the implementation plan):

- ``load_ledger(repo_root, ledger_path=None) -> dict``
- ``apply(repo_root, request, ledger_path=None) -> dict``
- ``query(repo_root, request, ledger_path=None) -> dict``
- ``init_ledger(repo_root, ledger_path=None) -> dict``
- ``RequirementsError`` with ``.code``/``.details`` for explicit failures.

The canonical ledger is only created by explicit ``init_ledger``; no other
code path fabricates one. Defining ``RequirementsError`` first lets the
submodules bind it from this package during import.
"""


class RequirementsError(Exception):
    """Explicit ledger failure with a stable machine-readable code."""

    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def envelope(self):
        return {
            "status": "error",
            "revision": (self.details.get("committed_revision")
                         if self.code == "projection-stale" else None),
            "error": {
                "code": self.code,
                "message": str(self),
                "details": self.details,
            },
        }


from .schema import SCHEMA_VERSION, validate_ledger  # noqa: E402,F401
from .store import (  # noqa: E402,F401
    OPERATIONS,
    apply,
    base_ledger,
    init_ledger,
    ledger_file,
    load_ledger,
    query,
)
