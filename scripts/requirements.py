#!/usr/bin/env python3
"""Thin CLI adapter over the requirements ledger library.

Verbs: ``init``, ``apply``, ``query``, ``validate``, ``render``. Reads never
initialize/repair/write; errors are machine-readable envelopes with nonzero
exit. ``render`` is implemented by Task 3's projection module and reports
``not-implemented`` until then — it never claims success falsely.
"""

import argparse
import json
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from requirements_lib import (  # noqa: E402
    RequirementsError,
    apply,
    init_ledger,
    load_ledger,
    query,
)

CLI_VERBS = ("init", "apply", "query", "validate", "render")


class _StrictParser(argparse.ArgumentParser):
    """Argparse that reports usage failures as machine-readable errors."""

    def error(self, message):
        raise RequirementsError("invalid-request", message, {})


def _build_parser():
    parser = _StrictParser(prog="requirements", description=__doc__)
    subparsers = parser.add_subparsers(dest="verb", required=True)
    for verb in CLI_VERBS:
        child = subparsers.add_parser(verb)
        child.add_argument("--repo-root", default=".")
        child.add_argument("--ledger", default=None,
                           help="root-relative or absolute ledger path")
        child.set_defaults(verb=verb)
        if verb in ("apply", "query"):
            child.add_argument("--request", default=None)
            child.add_argument("--stdin", action="store_true")
    return parser


def _read_request(args):
    if args.verb not in ("apply", "query"):
        return None
    if bool(args.request) == bool(args.stdin):
        raise RequirementsError(
            "invalid-request",
            f"{args.verb} needs exactly one of --request FILE or --stdin.",
            {},
        )
    if args.stdin:
        return sys.stdin.read()
    try:
        with open(args.request, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise RequirementsError(
            "invalid-request", f"Cannot read request file: {exc}.",
            {"request": args.request},
        ) from exc


def _emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False))
    sys.stdout.write("\n")


def _dispatch(args):
    request_text = _read_request(args)
    if args.verb == "init":
        return init_ledger(args.repo_root, args.ledger)
    if args.verb == "apply":
        from requirements_lib import schema as _schema

        request = _schema.strict_json_loads(request_text, "apply request")
        return apply(args.repo_root, request, args.ledger)
    if args.verb == "query":
        from requirements_lib import schema as _schema

        request = _schema.strict_json_loads(request_text, "query request")
        return query(args.repo_root, request, args.ledger)
    if args.verb == "validate":
        ledger = load_ledger(args.repo_root, args.ledger)
        return {"status": "ok", "revision": ledger["revision"],
                "result": {"valid": True}}
    if args.verb == "render":
        raise RequirementsError(
            "not-implemented",
            "render is delivered by the graph/report tasks (Task 3) and never "
            "claims success before the deterministic projection exists.",
            {"verb": "render"},
        )
    raise RequirementsError("invalid-request", f"Unknown verb {args.verb!r}.", {})


def main(argv=None):
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        payload = _dispatch(args)
    except RequirementsError as exc:
        _emit(exc.envelope())
        return 1
    except Exception:  # noqa: BLE001 - machine-readable envelope even for bugs
        traceback.print_exc(file=sys.stderr)
        _emit({
            "status": "error",
            "revision": None,
            "error": {
                "code": "internal-error",
                "message": "Unhandled internal failure; see stderr for the traceback.",
                "details": {},
            },
        })
        return 2
    _emit(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
