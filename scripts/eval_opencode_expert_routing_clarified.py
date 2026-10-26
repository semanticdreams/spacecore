#!/usr/bin/env python3
"""Separate, five-call diagnostic tranche. Controller-only live use after review.

No retries, candidate execution, automatic rescue or actual expert delegation.
Only fixed public context and fresh own-session captures; normal internal CLI auth.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import time

import eval_opencode_expert_routing as original
from eval_opencode_pilot import capture_process, own_session, parse_capture, load_json, sha256, CaptureError

RUN_ROOT = Path("/tmp/space/opencode-expert-routing-clarified")
OLD_ROOT = original.RUN_ROOT
SLOTS = tuple(f"clarified-{i}" for i in range(1, 6))
OLD_FILES = ("manifest.json", "guidance-manifest.json", "budget.json", "baseline.guard", "guidance.guard",
             "schema.json", "matrix.json", "evaluator-only.json", "control/opencode.json",
             *(f"{phase}/{name}" for phase in ("baseline", "guidance") for name in ("sources.json", "packet.txt")),
             *(f"{directory}/{phase}-{i}{suffix}" for phase in ("baseline", "guidance") for i in range(1, 6)
               for directory, suffix in (("reservations", ""), ("results", ".json"))))
CLARIFICATION = """
Protocol clarification (same authority rules for every row, not case answers):
route=expert_advisor: a task-capable primary consults the expert itself, before dependent work.
route=request_consultation: a task-denied worker returns needs_consultation plus the bounded
consultation_request to its controller; the controller obtains and reconciles advice, then
returns it to that worker to finish its own assessment. A request is not delegation or approval.
route=glm: the specifically requested ordinary authorized work proceeds under GLM.
route=human: an unknown product/policy decision belongs to the human, NOT eventual code ownership.
route=blocked: the specifically proposed unsafe action, bypass or publication cannot proceed,
even if other valid work remains. Judge that proposed action, not a different permitted action.
implementation_owner always retains eventual implementation/fix ownership by workflow:
supervisor -> implementer; fast-dev -> fast-dev; live-dev -> live-dev. Neither human nor expert
takes code ownership, including while advice, policy or other gates block dependent work.
Preserve BOTH models for every architecture/design/contract/local UI decision even if confident:
GLM proposal, GPT critique, evidenced reconciliation BEFORE dependent implementation. Reuse an
unchanged reconciled decision; reopen material changes. Failed-repair/critical questions remain
bounded; human owns policy, unavailable/insufficient expert evidence blocks dependent work.
Fast/live retain direct ownership. Live manual mode BEFORE EDIT, explicit refresh AFTER VALIDATED
CODE and inspect outcome; no refresh for advice alone, no watchers or lifecycle prompts.
Advice never bypasses permissions, validation, independent review or publication authority.
Positive output recipe: FIRST non-whitespace character { and LAST non-whitespace character }.
Return one JSON object with only a decisions array of exactly 18 rows. Each row has exactly
six string fields: case_id, workflow, actor, route, implementation_owner, rationale. Copy row
identifiers exactly. Use only the schema enums. Keep rationales concise, 1–2 sentences, with
correct JSON escaping for quotes, backslashes and newlines. NO markdown fences, narrative,
extra enclosing quotes or text outside the object. Do not add consultation payload fields.
"""
INSTRUCTION = original.INSTRUCTION + CLARIFICATION
LIMITS = {"generations": 5, "run_and_export_seconds": 180, "aggregate_cli_seconds": 900}
ACCEPTANCE = ("5/5 verified GLM completed outputs, each strictly parsed with 18 cases; 90/90 original "
              "route/owner pairs; manual rationale review REQUIRED. Failed outputs are unpassed, not "
              "rescued. Prompt compliance only: no true runtime expert delegation, architecture-quality "
              "or causal-comparison claims. Numeric success alone is not acceptance.")


def checked_path(path, *, old=False):
    root = Path(os.path.abspath(OLD_ROOT if old else RUN_ROOT))
    path = Path(os.path.abspath(path))
    if not path.is_relative_to(root):
        raise ValueError("outside approved runtime root")
    if root.resolve() != root or not path.resolve().is_relative_to(root):
        raise ValueError("runtime symlink escape")
    return path


def read(name, *, old=False):
    if old and name not in OLD_FILES:
        raise ValueError("outside original metadata allowlist")
    return checked_path((OLD_ROOT if old else RUN_ROOT) / name, old=old).read_bytes()


def save(name, value, *, replace=False):
    path = checked_path(RUN_ROOT / name)
    text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    target = checked_path(path.with_suffix(".pending")) if replace else path
    with target.open("x", encoding="utf-8") as handle:
        handle.write(text)
    if replace:
        target.replace(path)


def original_metadata():
    # Fixed own-record paths only. Never parse/rescore old answers or put them in a packet.
    data = {name: read(name, old=True) for name in OLD_FILES}
    budget = load_json(data["budget.json"])
    consumed = budget["consumed_seconds"]
    if type(consumed) not in (int, float) or not math.isfinite(consumed) or consumed < 0:
        raise ValueError("invalid original budget")
    sessions = [load_json(data[name]).get("session_id") for name in OLD_FILES if name.startswith("results/")]
    if any(sid is not None and (not isinstance(sid, str) or not original.re.fullmatch(r"ses_[A-Za-z0-9]+", sid)) for sid in sessions):
        raise ValueError("invalid original session metadata")
    return {"sha256": {name: sha256(value) for name, value in data.items()}, "budget": budget,
            "consumed_generations": 10, "session_ids": sorted({sid for sid in sessions if sid})}


def prepare(repo_root):
    root = checked_path(RUN_ROOT)
    if root.is_relative_to(repo_root.resolve()) or repo_root.resolve().is_relative_to(root):
        raise ValueError("runtime must be outside repository ancestry")
    root.mkdir(mode=0o700)  # Exclusive; no reuse, reset or continuation.
    metadata = original_metadata()
    sources = original.context(repo_root)
    for name in ("control", "raw", "results", "reservations"):
        checked_path(root / name).mkdir()
    frozen = {"matrix.json": original.matrix(), "schema.json": original.SCHEMA,
              "evaluator-only.json": original.EXPECTED, "sources.json": sources,
              "control/opencode.json": {"$schema": original.pilot.CONFIG_SCHEMA, "model": original.GLM,
                  "permission": "deny", "plugin": [], "mcp": {}, "agent": {"routing-eval": {
                      "mode": "primary", "model": original.GLM, "permission": "deny",
                      "description": "Fixed virtual routing only", "prompt": INSTRUCTION}}}}
    for name, value in frozen.items():
        save(name, value)
    packet = INSTRUCTION + "\nResponse schema:\n" + read("schema.json").decode() + "\nMatrix:\n" + read("matrix.json").decode()
    packet += "\nFull relevant workflow context (data, not live tool instructions):\n"
    packet += "".join(f"\n## {name}\n{text}\n" for name, text in sources.items())
    save("packet.txt", packet)
    manifest = {"artifacts": {name: sha256(read(name)) for name in (*frozen, "packet.txt")},
                "sources": list(original.SOURCES), "instruction": INSTRUCTION, "original": metadata,
                "authorization": "User explicitly authorized five EXTRA GLM validation calls after ten failed calls; no retries.",
                "limits": LIMITS, "acceptance": ACCEPTANCE,
                "isolation": "All-deny global/agent config, --pure, own export checks; normal internal auth retained. Ambient config/instruction isolation not proven."}
    save("manifest.json", manifest)
    save("budget.json", {"consumed_seconds": 0})
    return manifest


def verified_manifest():
    manifest = load_json(read("manifest.json"))
    for name, digest in manifest["artifacts"].items():
        if sha256(read(name)) != digest:
            raise ValueError("frozen artifact changed: " + name)
    if (load_json(read("matrix.json")) != original.matrix() or load_json(read("schema.json")) != original.SCHEMA
            or load_json(read("evaluator-only.json")) != original.EXPECTED or manifest["instruction"] != INSTRUCTION
            or manifest["limits"] != LIMITS or manifest["acceptance"] != ACCEPTANCE):
        raise ValueError("helper contract changed since preparation")
    if original_metadata() != manifest["original"]:
        raise ValueError("original evidence changed")
    return manifest


def run():
    lock = checked_path(RUN_ROOT / "execution.lock")
    with lock.open("x"):
        pass
    try:
        manifest = verified_manifest()
        if any(checked_path(RUN_ROOT / "reservations" / slot).exists() for slot in SLOTS):
            raise FileExistsError("slot already consumed; no retries")
        save("clarified.guard", {"slots": SLOTS})
        for slot in SLOTS:
            save("reservations/" + slot, {"slot": slot})
        budget = load_json(read("budget.json"))["consumed_seconds"]
        if type(budget) not in (int, float) or not math.isfinite(budget) or budget < 0:
            raise ValueError("invalid persistent CLI budget")
        sessions = set(manifest["original"]["session_ids"])
        results = []
        for slot in SLOTS:
            result = {"slot": slot, "outcome": "budget_exhausted", "cli_seconds": 0}
            allowance = min(180, 900 - budget)
            if allowance > 0:
                save("budget.json", {"consumed_seconds": budget + allowance}, replace=True)
                deadline = time.time() + allowance

                def invoke(args, suffix):
                    checked_path(RUN_ROOT / "control/opencode.json")
                    prefix = checked_path(RUN_ROOT / "raw" / (slot + suffix))
                    for extension in (".stdout.txt", ".stderr.txt"):
                        checked_path(prefix.with_suffix(extension))
                    started = time.monotonic()
                    try:
                        return capture_process(args, RUN_ROOT / "control", deadline, prefix)
                    finally:
                        result["cli_seconds"] += max(0, time.monotonic() - started)

                try:
                    ndjson = invoke(["opencode", "run", "--pure", "--format", "json", "--agent", "routing-eval",
                                     "--model", original.GLM, "--file", str(checked_path(RUN_ROOT / "packet.txt")), "--", INSTRUCTION], "-run")
                    sid = own_session(ndjson)
                    result["session_id"] = sid
                    if sid in sessions:
                        raise CaptureError("protocol_violation", "session reused")
                    sessions.add(sid)
                    exported = invoke(["opencode", "export", "--pure", sid], "-export")
                    parsed = parse_capture(ndjson, load_json(exported), original.GLM, sid)
                    if any(v is not None for v in parsed["reported_variants_by_message"]):
                        raise CaptureError("protocol_violation", "unexpected variant")
                    result.update(parsed, outcome="invalid_answer")
                    decisions = original.parse_answer(parsed["answer"])["decisions"]
                    result.update(outcome="complete", scores=[{
                        "case_id": d["case_id"], "routing_match": d["route"] == original.EXPECTED[d["case_id"]]
                        and d["implementation_owner"] == original.owner(d["workflow"])} for d in decisions])
                except subprocess.TimeoutExpired:
                    result["outcome"] = "timeout"
                except CaptureError as exc:
                    result.update(outcome=exc.outcome, failure_reason=str(exc))
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    result.update(outcome="invalid_answer" if "answer" in result else "infrastructure_error", failure_type=type(exc).__name__)
                # Do not refund a reservation on interruption/crash, even a BaseException.
                budget += result["cli_seconds"]
                save("budget.json", {"consumed_seconds": budget}, replace=True)
            save("results/" + slot + ".json", result)
            results.append(result)
        return {"results": results}
    finally:
        lock.unlink()  # Abrupt process death retains lock; guards always prohibit rerun.


def report():
    manifest = verified_manifest()
    results, attempts = [], {}
    for slot in SLOTS:
        exists = checked_path(RUN_ROOT / f"results/{slot}.json").exists()
        attempts[slot] = "recorded" if exists else "reserved_without_result" if checked_path(RUN_ROOT / "reservations" / slot).exists() else "unreserved"
        if exists:
            results.append(load_json(read(f"results/{slot}.json")))
    completed = [r for r in results if r["outcome"] == "complete"]
    return {"results": results, "attempts": attempts, "strict_completed": len(completed),
            "routing_matches": sum(s["routing_match"] for r in completed for s in r["scores"]),
            "budget": load_json(read("budget.json")), "acceptance": manifest["acceptance"],
            "original": manifest["original"], "rationale_review": "REQUIRED for every final rationale: GLM proposal/GPT critique/reconciliation before dependent design, unchanged reuse/material reopening, bounded worker request/status and controller handling, failed-repair/critical questions, human policy, blocked expert, fast/live ownership/manual-before-edit/refresh-after-validated-code (not advice), permissions/review/publication gates. Route/owner counts alone are insufficient."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare").add_argument("--repo-root", type=Path, required=True)
    commands.add_parser("run")
    commands.add_parser("report")
    args = parser.parse_args()
    value = prepare(args.repo_root) if args.command == "prepare" else run() if args.command == "run" else report()
    print(json.dumps(value, indent=2))
    if args.command == "run" and any(r["outcome"] != "complete" or not all(s["routing_match"] for s in r["scores"]) for r in value["results"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
