#!/usr/bin/env python3
"""Fixed static Space Fennel pilot. No candidate source is ever written or run.

Preparation uses public pinned git blobs only. `run` is a separate, review-gated
operation: eleven fresh sessions, no continuation, repair, retry or fallback.
Raw captures stay under /tmp/space/opencode-model-pilot; review final text before publishing.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import uuid

GPT = "openai/gpt-6.1-sol"
GLM = "opencode-go/glm-5.3-flash"
GLM_VARIANT = "high"
CONFIG_SCHEMA = "https://opencode.ai/config.json"
RUN_ROOT = Path("/tmp/space/opencode-model-pilot")
CASES = Path(__file__).resolve().parent / "evals/opencode_pilot_cases.json"
FILES = {"assets/lua/sized.fnl", "assets/lua/tests/test-sized.fnl"}
INSTRUCTION = "Answer the attached frozen packet only. No tools or delegation. Return final answer text; never claim unexecuted validation passed."


class CaptureError(ValueError):
    def __init__(self, outcome, message):
        super().__init__(message)
        self.outcome = outcome


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def load_json(text):
    return json.loads(text, object_pairs_hook=unique_object)


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def control_root(path):
    path = path.resolve()
    if not path.is_relative_to(RUN_ROOT) or path == RUN_ROOT:
        raise ValueError(f"run root must be a new directory beneath {RUN_ROOT}")
    return path


def mutate(source, edits):
    for edit in edits:
        if source.count(edit["old"]) != edit["count"]:
            raise ValueError("fixture mutation no longer matches pinned source")
        source = source.replace(edit["old"], edit["new"])
    return source


def prepare(repo_root: Path, run_root: Path) -> dict:
    repo_root, run_root = repo_root.resolve(), control_root(run_root)
    if run_root.is_relative_to(repo_root) or repo_root.is_relative_to(run_root):
        raise ValueError("control directory must be outside repository ancestry")
    run_root.mkdir(mode=0o700)  # exclusive: never replace a previously frozen run
    for name in ["sources", "packets", "control", "raw", "results", "reservations"]:
        (run_root / name).mkdir()
    cases_bytes = CASES.read_bytes()
    cases = load_json(cases_bytes)
    artifacts, sources, excerpts = {}, {}, {}

    def freeze(name, data):
        (run_root / name).write_bytes(data)
        artifacts[name] = sha256(data)

    freeze("evaluator-only.json", cases_bytes)
    for index, ref in enumerate(cases["sources"]):
        blob = subprocess.run(["git", "show", cases["source_commit"] + ":" + ref["path"]],
                              cwd=repo_root, capture_output=True, check=True).stdout
        excerpt = (b"".join(b"".join(blob.splitlines(keepends=True)[a - 1:z])
                            for a, z in ref["ranges"]) if ref["ranges"] else blob)
        if sha256(blob) != ref["blob_sha256"] or sha256(excerpt) != ref["excerpt_sha256"]:
            raise ValueError("pinned source/excerpt hash mismatch: " + ref["path"])
        freeze(f"sources/{index}-blob.txt", blob)
        freeze(f"sources/{index}-excerpt.txt", excerpt)
        sources[ref["path"]], excerpts[ref["path"]] = blob.decode(), excerpt.decode()

    def block(label, text, language="fennel"):
        return "\n## " + label + "\n```" + language + "\n" + text + "\n```\n"

    def packet(case):
        module = case["module"]
        text = "# Static Space Fennel case\n" + cases["conventions"] + "\n\n" + case["brief"] + "\n"
        if module == "sized":
            text += "\nPublic feature requirements:\n" + cases["sized_requirements"] + "\n"
        for path in [f"assets/lua/{module}.fnl", f"assets/lua/tests/test-{module}.fnl"]:
            text += block(path + " @ " + cases["source_commit"], sources[path])
        for ref in cases["sources"][6:]:
            text += block(ref["path"] + " ranges " + json.dumps(ref["ranges"]) + " @ " + cases["source_commit"], excerpts[ref["path"]],
                          "fennel" if ref["path"].endswith(".fnl") else "text")
        for variant in case.get("variants", []):
            text += block("Independent variant " + variant["label"], mutate(sources[f"assets/lua/{module}.fnl"], variant["edits"]))
        if "edits" in case:
            text += block("Synthetic author patch (inert complete module)", mutate(sources[f"assets/lua/{module}.fnl"], case["edits"]))
        return text

    trials = []
    for index, case in enumerate(cases["cases"]):
        filename = "packets/" + case["id"] + ".txt"
        freeze(filename, packet(case).encode())
        for model in ([GLM, GPT] if index % 2 == 0 else [GPT, GLM]):
            trials.append({"id": case["id"] + ("-gpt" if model == GPT else "-glm"),
                           "model": model, "variant": "xhigh" if model == GPT else GLM_VARIANT,
                           "packet": filename, "seconds": 180, "implementation": False})
    plain = packet(cases["implementation"])
    contracted = plain + "\n## Frozen conceptual contract\n" + cases["contract"]["text"] + "\n"
    freeze("packets/sized-plain.txt", plain.encode())
    freeze("packets/sized-contract.txt", contracted.encode())
    for label, model, contract in [("sized-glm-plain", GLM, False),
                                   ("sized-gpt-contract", GPT, True),
                                   ("sized-glm-contract", GLM, True)]:
        trials.append({"id": label, "model": model, "variant": "high" if model == GPT else GLM_VARIANT,
                       "packet": "packets/sized-contract.txt" if contract else "packets/sized-plain.txt",
                       "seconds": 360, "implementation": True})
    config = {"$schema": CONFIG_SCHEMA, "permission": "deny", "plugin": [], "mcp": {},
              "agent": {"pilot": {"mode": "primary", "variant": GLM_VARIANT, "permission": "deny",
                                  "description": "Static fixed-context pilot, no tools",
                                  "prompt": INSTRUCTION}}}
    freeze("control/opencode.json", (json.dumps(config, indent=2) + "\n").encode())
    digest = sha256(cases["contract"]["text"].encode())
    manifest = {"source_commit": cases["source_commit"], "sources": cases["sources"],
                "instruction": INSTRUCTION,
                "cases_sha256": sha256(cases_bytes), "artifacts": artifacts, "trials": trials,
                "contract_gpt_sha256": digest, "contract_glm_sha256": digest,
                "isolation": "Generated all-deny global/agent config; --pure disables external plugins. Normal auth and roots unchanged; ambient global instructions/providers/config and skill discovery not proven isolated. Skill/tool use denied and exported parts checked.",
                "review_gate": "Independent Task 1 packet/runner review required before run. No results yet."}
    save(run_root / "manifest.json", manifest)
    return manifest


def events_from(ndjson):
    events = [load_json(line) for line in ndjson.splitlines() if line.strip()]
    if not events or any(not isinstance(e, dict) for e in events):
        raise ValueError("missing or malformed CLI events")
    for event in events:
        if "part" in event and not isinstance(event["part"], dict):
            raise ValueError("malformed CLI part")
        if event.get("type") == "error":
            raise CaptureError("preflight_failure", "CLI reported an error; inspect own raw capture")
        if event.get("type") in {"tool", "tool_use", "tool_result", "retry", "subtask"}:
            raise CaptureError("protocol_violation", "CLI tool/delegation/retry protocol violation")
        if event.get("part", {}).get("type") in {"tool", "subtask", "retry"}:
            raise CaptureError("protocol_violation", "CLI tool/delegation/retry protocol violation")
        if "part" in event and event["part"].get("sessionID") != event.get("sessionID"):
            raise ValueError("CLI part belongs to another session")
    return events


def own_session(ndjson):
    events = events_from(ndjson)
    ids = {e.get("sessionID") for e in events}
    if len(ids) != 1 or not isinstance(next(iter(ids)), str) or not re.fullmatch(r"ses_[A-Za-z0-9]+", next(iter(ids))):
        raise ValueError("missing or mixed own-session ID")
    return next(iter(ids))


def parse_capture(ndjson: str, exported: dict, expected_model: str, owned_session_id: str) -> dict:
    try:
        return _parse_capture(ndjson, exported, expected_model, owned_session_id)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("malformed CLI/export structure") from exc


def _parse_capture(ndjson, exported, expected_model, owned_session_id):
    if own_session(ndjson) != owned_session_id or exported.get("info", {}).get("id") != owned_session_id:
        raise ValueError("wrong own-session ID")
    events = events_from(ndjson)
    if not any(e.get("type") == "step_finish" and e.get("part", {}).get("reason") == "stop" for e in events):
        raise CaptureError("incomplete", "CLI completion missing")
    answers, usage, variants, seen = [], [], [], set()
    for message in exported.get("messages", []):
        info = message["info"]
        if info.get("sessionID") != owned_session_id or not info.get("id") or info["id"] in seen:
            raise ValueError("wrong session or duplicate/missing message ID")
        seen.add(info["id"])
        for part in message["parts"]:
            if part.get("sessionID") != owned_session_id or part.get("messageID") != info["id"]:
                raise ValueError("wrong part ownership")
            if part.get("type") in {"tool", "subtask", "retry", "patch", "agent", "compaction"}:
                raise CaptureError("protocol_violation", "export tool/delegation/retry protocol violation")
        if info["role"] != "assistant":
            continue
        if f"{info.get('providerID')}/{info.get('modelID')}" != expected_model:
            raise CaptureError("preflight_failure", "actual assistant model missing or mismatched")
        if info.get("error") is not None:
            raise CaptureError("preflight_failure", "assistant error; inspect own raw export")
        if info.get("time", {}).get("completed") is None or info.get("finish") != "stop":
            raise CaptureError("incomplete", "incomplete assistant output")
        # AssistantMessage is authoritative. Never add StepFinishPart/NDJSON usage.
        usage.append({"message_id": info["id"], "tokens": info.get("tokens"), "cost": info.get("cost")})
        variants.append(info.get("variant"))
        answers.extend(p["text"] for p in message["parts"] if p["type"] == "text" and not p.get("synthetic") and not p.get("ignored"))
    answer = "\n".join(answers)
    if not usage or not answer.strip():
        raise CaptureError("incomplete", "no completed assistant final text")
    return {"session_id": owned_session_id, "actual_model": expected_model, "answer": answer,
            "usage": usage, "reported_variant": variants[0] if len(set(variants)) == 1 else None,
            "reported_variants_by_message": variants}


def parse_files(answer: str) -> dict[str, str]:
    value = load_json(answer)
    if not isinstance(value, dict) or set(value) != {"files", "notes"} or not isinstance(value["notes"], str) or not value["notes"].strip():
        raise ValueError("implementation JSON requires files and nonempty validation notes only")
    files = value.get("files") if isinstance(value, dict) else None
    if not isinstance(files, dict) or set(files) != FILES or any(not isinstance(v, str) or not v.strip() for v in files.values()):
        raise ValueError("implementation must contain exactly the two allowlisted inert source strings")
    return files


def capture_process(args, control, deadline, raw_prefix):
    remaining = deadline - time.time()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(args[0], 0)
    env = os.environ.copy()  # retain normal CLI internal subscription auth; never dump it
    env["OPENCODE_CONFIG"] = str(control / "opencode.json")
    env["OPENCODE_CONFIG_CONTENT"] = (control / "opencode.json").read_text()
    # The CLI can truncate export output when its destination is a pipe. Supply
    # regular files directly; exclusive creation also preserves failed originals.
    with raw_prefix.with_suffix(".stdout.txt").open("xb") as stdout, raw_prefix.with_suffix(".stderr.txt").open("xb") as stderr:
        proc = subprocess.Popen(args, cwd=control, env=env, stdout=stdout,
                                stderr=stderr, text=True, start_new_session=True)
        try:
            proc.communicate(timeout=remaining)
        except BaseException as failure:
            # Every unwind owns the detached child group, not only deadline expiry.
            try:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Child group already exited; still reap the started child.
                finally:
                    try:
                        proc.communicate()
                    finally:
                        proc.wait()  # Reap even if draining is itself interrupted.
            except BaseException as cleanup_failure:
                # Keep cancellation/timeout primary, but never hide cleanup failures.
                raise failure from cleanup_failure
            raise
    if proc.returncode != 0:
        raise ValueError("CLI exited nonzero: " + str(proc.returncode))
    return raw_prefix.with_suffix(".stdout.txt").read_text(encoding="utf-8")


def checked_manifest(run_root):
    manifest = load_json((run_root / "manifest.json").read_text())
    annotations = []
    for name, digest in manifest["artifacts"].items():
        data = (run_root / name).read_bytes()
        actual = sha256(data)
        if actual == digest:
            continue
        if name == "control/opencode.json":
            config = load_json(data)
            if isinstance(config, dict) and config.pop("$schema", None) == CONFIG_SCHEMA:
                # Only the known CLI annotation may differ. Reproduce the old
                # preparation bytes, including key order, indentation and newline.
                original_format = (json.dumps(config, indent=2) + "\n").encode()
                if sha256(original_format) == digest:
                    annotations.append({"path": name, "expected_sha256": digest, "actual_sha256": actual,
                                        "accepted_annotation": {"$schema": CONFIG_SCHEMA}})
                    continue
        raise ValueError("frozen artifact changed: " + name)
    manifest["artifact_annotations"] = annotations  # observation only; never rewrite frozen files
    return manifest


def require_glm_high(config, agent, trials=()):
    """Generation preflight only; historical manifests/captures remain unmodified."""
    if config.get("agent", {}).get(agent, {}).get("variant") != GLM_VARIANT:
        raise ValueError("GLM generation requires a newly prepared high-variant config")
    if any(t.get("variant") != GLM_VARIANT for t in trials if t["model"] == GLM):
        raise ValueError("GLM generation requires newly prepared high-variant trials")


def verify_glm_high(parsed):
    if not parsed["reported_variants_by_message"] or any(v != GLM_VARIANT for v in parsed["reported_variants_by_message"]):
        raise CaptureError("protocol_violation", "reported GLM variant must be high; missing mode is unknown")


def run_trial(trial: dict, run_root: Path, overall_deadline: float) -> dict:
    run_root = control_root(run_root)
    manifest = checked_manifest(run_root)
    if trial not in manifest["trials"]:
        raise ValueError("unplanned trial")
    require_glm_high(load_json((run_root / "control/opencode.json").read_text()), "pilot", manifest["trials"])
    # A run lock serializes the persistent deadline and exclusive reservations.
    lock = run_root / "execution.lock"
    with lock.open("x"):
        pass
    try:
        ledger_path = run_root / "deadline.json"
        if not ledger_path.exists():
            save(ledger_path, {"started_at": time.time(), "deadline": min(overall_deadline, time.time() + 5400)})
        deadline = min(overall_deadline, load_json(ledger_path.read_text())["deadline"])
        reservation = run_root / "reservations" / trial["id"]
        with reservation.open("x") as handle:
            handle.write(str(time.time()))
        started = time.time()
        result = {"trial_id": trial["id"], "requested_model": trial["model"],
                  "requested_variant": trial["variant"], "sent_variant": None,
                  "reported_variant": None, "variant_uncertainty": "Effective variant unknown unless own export reports it; request is not proof.",
                  "packet_sha256": manifest["artifacts"][trial["packet"]], "assessment": "static-only; candidate code never executed"}
        if started >= deadline:
            result["outcome"] = "deadline"
        else:
            call_deadline = min(deadline, started + trial["seconds"])
            args = ["opencode", "run", "--pure", "--format", "json", "--agent", "pilot", "--model", trial["model"]]
            if trial["variant"]:
                args += ["--variant", trial["variant"]]
            args += ["--file", str(run_root / trial["packet"]), "--", manifest["instruction"]]
            try:
                result["sent_variant"] = trial["variant"]
                ndjson = capture_process(args, run_root / "control", call_deadline, run_root / "raw" / (trial["id"] + "-run"))
                session_id = own_session(ndjson)  # never list sessions or export an unrelated ID
                exported = capture_process(["opencode", "export", "--pure", session_id], run_root / "control",
                                           call_deadline, run_root / "raw" / (trial["id"] + "-export"))
                result.update(parse_capture(ndjson, load_json(exported), trial["model"], session_id))
                if trial["model"] == GLM:
                    verify_glm_high(result)
                result["outcome"] = "complete"
                if trial["implementation"]:
                    try:
                        parse_files(result["answer"])  # inert data only, never write source paths
                    except ValueError:
                        result["outcome"] = "invalid_answer"
            except subprocess.TimeoutExpired:
                result["outcome"] = "timeout"
            except CaptureError as exc:
                result["outcome"] = exc.outcome
                result["failure_reason"] = str(exc)
            except (ValueError, KeyError, TypeError, OSError) as exc:
                result["outcome"] = "infrastructure_error"
                result["failure_type"] = type(exc).__name__  # raw diagnostics remain outside git
        result["wall_seconds"] = time.time() - started
        save(run_root / "results" / (trial["id"] + ".json"), result)
        return result
    finally:
        lock.unlink()  # crash leaves a lock for manual investigation, never automatic retry


def run_answer(ndjson):
    texts = {}
    for event in events_from(ndjson):
        part = event.get("part", {})
        if event.get("type") == "text" and part.get("type") == "text" and not part.get("synthetic") and not part.get("ignored"):
            if not part.get("id") or (part["id"] in texts and texts[part["id"]] != part["text"]):
                raise ValueError("ambiguous saved final text")
            texts[part["id"]] = part["text"]
    return "\n".join(texts.values())


def verify_collection(trial, ndjson, exported):
    parsed = parse_capture(ndjson, exported, trial["model"], own_session(ndjson))
    if parsed["answer"] != run_answer(ndjson):
        raise ValueError("recovered final text differs from saved run")
    if trial["implementation"]:
        parse_files(parsed["answer"])
    return parsed


def recovered_result(run_root, trial, original, ndjson):
    directory = run_root / "recoveries" / trial["id"]
    records = [(p, load_json(p.read_text())) for p in directory.glob("*/record.json")]
    successes = [(p, r) for p, r in records if r["outcome"] == "complete"]
    if len(successes) != 1:
        raise ValueError("reserved trial has no unique successful recovery: " + trial["id"])
    path, record = successes[0]
    export_path = path.parent / "export.stdout.txt"
    if record["trial_id"] != trial["id"] or record["session_id"] != own_session(ndjson) or record["kind"] != "export_collection_recovery" or record["export_stdout"] != str(export_path.relative_to(run_root)):
        raise ValueError("wrong recovery ownership")
    original_bytes = (run_root / "results" / (trial["id"] + ".json")).read_bytes()
    export_bytes = export_path.read_bytes()
    if record["original_result_sha256"] != sha256(original_bytes) or record["run_sha256"] != sha256(ndjson.encode()) or record["export_sha256"] != sha256(export_bytes):
        raise ValueError("recovery evidence changed")
    parsed = verify_collection(trial, ndjson, load_json(export_bytes))
    effective = record["effective_result"]
    if effective["trial_id"] != original["trial_id"] or effective["outcome"] != "complete" or effective["collection_recovery"] != str(path.relative_to(run_root)) or any(effective[k] != v for k, v in parsed.items()):
        raise ValueError("invalid effective recovery record")
    return effective


def recover_export(run_root, trial_id):
    """Explicit collection repair only: never run a candidate or alter its ledger."""
    run_root = control_root(run_root)
    manifest = checked_manifest(run_root)
    trial = next((t for t in manifest["trials"] if t["id"] == trial_id), None)
    if trial is None or not (run_root / "reservations" / trial_id).is_file():
        raise ValueError("recovery requires a scheduled reserved trial")
    lock = run_root / "execution.lock"
    with lock.open("x"):
        pass
    try:
        original_path = run_root / "results" / (trial_id + ".json")
        original_bytes = original_path.read_bytes()
        original = load_json(original_bytes)
        if original.get("trial_id") != trial_id or original.get("outcome") != "infrastructure_error" or original.get("failure_type") != "JSONDecodeError":
            raise ValueError("recovery is restricted to failed JSON export collection")
        ndjson = (run_root / "raw" / (trial_id + "-run.stdout.txt")).read_text()
        session_id = own_session(ndjson)  # only the observed saved run ID, never caller input
        directory = run_root / "recoveries" / trial_id
        if any(load_json(p.read_text())["outcome"] == "complete" for p in directory.glob("*/record.json")):
            raise ValueError("collection already recovered")
        deadline = load_json((run_root / "deadline.json").read_text())["deadline"]
        attempt = directory / uuid.uuid4().hex
        attempt.mkdir(parents=True)  # new append-only namespace, never the old raw prefix
        prefix = attempt / "export"
        record = {"trial_id": trial_id, "session_id": session_id, "kind": "export_collection_recovery",
                  "artifact_annotations": manifest["artifact_annotations"],
                  "original_result_sha256": sha256(original_bytes), "run_sha256": sha256(ndjson.encode()),
                  "export_stdout": str(prefix.with_suffix(".stdout.txt").relative_to(run_root))}
        started = time.time()
        try:
            if started >= deadline:
                record["outcome"] = "deadline"
            else:
                exported = capture_process(["opencode", "export", "--pure", session_id], run_root / "control",
                                           min(deadline, started + 180), prefix)
                parsed = verify_collection(trial, ndjson, load_json(exported))
                record.update(outcome="complete", export_sha256=sha256(prefix.with_suffix(".stdout.txt").read_bytes()))
                record["effective_result"] = {**original, **parsed, "outcome": "complete",
                                              "collection_recovery": str((attempt / "record.json").relative_to(run_root))}
        except subprocess.TimeoutExpired:
            record["outcome"] = "timeout"
        except (ValueError, KeyError, TypeError, OSError) as exc:
            record.update(outcome="infrastructure_error", failure_type=type(exc).__name__)
        record["collection_wall_seconds"] = time.time() - started
        with (attempt / "record.json").open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(record, indent=2) + "\n")
        return record
    finally:
        lock.unlink()


def continue_unreserved(run_root):
    """Preflight every reservation, then attempt only untouched schedule entries."""
    run_root = control_root(run_root)
    manifest = checked_manifest(run_root)
    require_glm_high(load_json((run_root / "control/opencode.json").read_text()), "pilot", manifest["trials"])
    deadline = load_json((run_root / "deadline.json").read_text())["deadline"]
    reserved = {p.name for p in (run_root / "reservations").iterdir()}
    if reserved - {t["id"] for t in manifest["trials"]}:
        raise ValueError("unrecognized reservation")
    # Preflight the entire reserved set before any candidate is invoked.
    for trial in manifest["trials"]:
        if trial["id"] not in reserved:
            continue
        original = load_json((run_root / "results" / (trial["id"] + ".json")).read_text())
        ndjson = (run_root / "raw" / (trial["id"] + "-run.stdout.txt")).read_text()
        if original["trial_id"] != trial["id"]:
            raise ValueError("wrong reserved trial result")
        if original["outcome"] == "complete":
            exported = load_json((run_root / "raw" / (trial["id"] + "-export.stdout.txt")).read_text())
            parsed = verify_collection(trial, ndjson, exported)
            if any(original[k] != v for k, v in parsed.items()):
                raise ValueError("completed result differs from its capture")
        elif original["outcome"] == "infrastructure_error" and original.get("failure_type") == "JSONDecodeError":
            recovered_result(run_root, trial, original, ndjson)
        else:
            raise ValueError("unresolved reserved trial: " + trial["id"])
    summary = {"outcome": "complete", "executed": []}
    for trial in manifest["trials"]:
        if trial["id"] in reserved:
            print(json.dumps({"trial_id": trial["id"], "outcome": "skipped_reserved"}))
    for trial in manifest["trials"]:
        if trial["id"] in reserved:
            continue
        if time.time() >= deadline:
            summary["outcome"] = "deadline"
            print(json.dumps({"outcome": "deadline", "additional_model_calls": 0}))
            break
        result = run_trial(trial, run_root, deadline)
        summary["executed"].append(result)
        print(json.dumps({"trial_id": trial["id"], "outcome": result["outcome"]}))
        if result["outcome"] != "complete":
            summary["outcome"] = result["outcome"]
            break
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--repo-root", type=Path, required=True)
    prep.add_argument("--run-root", type=Path, required=True)
    run = commands.add_parser("run", help="only after independent preparation review")
    run.add_argument("--run-root", type=Path, required=True)
    recover = commands.add_parser("recover-export", help="explicit same-session collection repair; no generation")
    recover.add_argument("--run-root", type=Path, required=True)
    recover.add_argument("--trial-id", required=True)
    continuation = commands.add_parser("continue-unreserved", help="explicit continuation with original deadline")
    continuation.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        manifest = prepare(args.repo_root, args.run_root)
        print(json.dumps({"prepared": len(manifest["trials"]), "run_root": str(args.run_root), "model_calls": 0}))
    elif args.command == "recover-export":
        record = recover_export(args.run_root, args.trial_id)
        print(json.dumps({"trial_id": args.trial_id, "outcome": record["outcome"]}))
        if record["outcome"] != "complete":
            raise SystemExit(1)
    elif args.command == "continue-unreserved":
        if continue_unreserved(args.run_root)["outcome"] != "complete":
            raise SystemExit(1)
    else:
        run_root = control_root(args.run_root)
        manifest = load_json((run_root / "manifest.json").read_text())
        deadline = time.time() + 5400
        for trial in manifest["trials"]:
            result = run_trial(trial, run_root, deadline)
            print(json.dumps({"trial_id": trial["id"], "outcome": result["outcome"]}))
            if result["outcome"] != "complete":
                raise SystemExit(1)


if __name__ == "__main__":
    main()
