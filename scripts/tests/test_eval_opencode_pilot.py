"""Offline orchestration tests: fixtures are inert strings; no model or Fennel runs."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("pilot", ROOT / "scripts/eval_opencode_pilot.py")
pilot = None
if Path(SPEC.origin).exists():
    pilot = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(pilot)

MODEL = "openai/gpt-6.1-sol"
SID = "ses_owned"


def capture():
    info = {"id": "msg_1", "sessionID": SID, "role": "assistant",
            "providerID": "openai", "modelID": "gpt-6.1-sol",
            "time": {"created": 1, "completed": 2}, "finish": "stop",
            "cost": 0, "tokens": {"input": 10, "output": 4, "reasoning": 2,
                                    "cache": {"read": 3, "write": 0}}}
    parts = [{"id": "p_reason", "sessionID": SID, "messageID": "msg_1",
              "type": "reasoning", "text": "PRIVATE_REASONING"},
             {"id": "p_text", "sessionID": SID, "messageID": "msg_1",
              "type": "text", "text": "final answer"},
             {"id": "p_step", "sessionID": SID, "messageID": "msg_1",
              "type": "step-finish", "reason": "stop", "tokens": info["tokens"], "cost": 0}]
    events = [{"type": "text", "sessionID": SID, "part": parts[1]},
              {"type": "step_finish", "sessionID": SID, "part": parts[2]}]
    return "\n".join(map(json.dumps, events)), {
        "info": {"id": SID}, "messages": [{"info": info, "parts": parts}]}


class Availability(unittest.TestCase):
    def test_runner_exists(self):
        self.assertIsNotNone(pilot, "Task 1 runner has not been implemented")


@unittest.skipIf(pilot is None, "runner not yet implemented")
class ParseTests(unittest.TestCase):
    def parse(self, ndjson=None, exported=None):
        original, exp = capture()
        return pilot.parse_capture(original if ndjson is None else ndjson,
                                   exp if exported is None else exported, MODEL, SID)

    def test_final_text_only_and_single_authoritative_usage(self):
        ndjson, exp = capture()
        result = self.parse(ndjson + "\n" + ndjson, exp)
        self.assertEqual(result["answer"], "final answer")
        self.assertNotIn("PRIVATE_REASONING", json.dumps(result))
        self.assertEqual(result["usage"], [{"message_id": "msg_1", "tokens": exp["messages"][0]["info"]["tokens"], "cost": 0}])
        self.assertIsNone(result["reported_variant"])

    def test_missing_usage_and_zero_are_not_conflated(self):
        _, exp = capture()
        del exp["messages"][0]["info"]["tokens"]
        del exp["messages"][0]["info"]["cost"]
        result = self.parse(exported=exp)
        self.assertEqual(result["usage"], [{"message_id": "msg_1", "tokens": None, "cost": None}])

    def test_model_mismatch_or_missing(self):
        for key, value in [("modelID", "wrong"), ("providerID", "wrong"), ("modelID", None), ("providerID", None)]:
            with self.subTest(key=key, value=value):
                _, exp = capture()
                exp["messages"][0]["info"][key] = value
                with self.assertRaises(ValueError):
                    self.parse(exported=exp)

    def test_wrong_session_anywhere(self):
        for location in ["export", "message", "part", "event", "event_part"]:
            ndjson, exp = capture()
            if location == "export":
                exp["info"]["id"] = "ses_other"
            elif location == "message":
                exp["messages"][0]["info"]["sessionID"] = "ses_other"
            elif location == "part":
                exp["messages"][0]["parts"][0]["sessionID"] = "ses_other"
            elif location == "event":
                ndjson = ndjson.replace(SID, "ses_other")
            else:
                events = [json.loads(line) for line in ndjson.splitlines()]
                events[0]["part"]["sessionID"] = "ses_other"
                ndjson = "\n".join(map(json.dumps, events))
            with self.subTest(location=location), self.assertRaises(ValueError):
                self.parse(ndjson, exp)

    def test_incomplete_error_or_empty_output(self):
        for mutation in ["unfinished", "length", "error", "empty", "no_assistant"]:
            _, exp = capture()
            msg = exp["messages"][0]
            if mutation == "unfinished":
                del msg["info"]["time"]["completed"]
            elif mutation == "length":
                msg["info"]["finish"] = "length"
            elif mutation == "error":
                msg["info"]["error"] = {"name": "ProviderAuthError"}
            elif mutation == "empty":
                msg["parts"] = []
            else:
                exp["messages"] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.parse(exported=exp)

    def test_malformed_or_error_ndjson(self):
        for value in ["not json", "[]", '{"type":"error","sessionID":"ses_owned"}',
                      '{"type":"text","sessionID":"ses_owned","part":null}', ""]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.parse(ndjson=value)

    def test_malformed_export_fails_closed(self):
        for exported in [[], {}, {"info": {"id": SID}, "messages": [None]},
                         {"info": {"id": SID}, "messages": "not messages"}]:
            with self.subTest(exported=exported), self.assertRaises(ValueError):
                self.parse(exported=exported)

    def test_incomplete_and_identity_outcomes_are_not_model_scores(self):
        _, exp = capture()
        exp["messages"][0]["info"]["finish"] = "length"
        with self.assertRaises(pilot.CaptureError) as incomplete:
            self.parse(exported=exp)
        self.assertEqual(incomplete.exception.outcome, "incomplete")
        exp["messages"][0]["info"]["modelID"] = "different"
        with self.assertRaises(pilot.CaptureError) as identity:
            self.parse(exported=exp)
        self.assertEqual(identity.exception.outcome, "preflight_failure")

    def test_tools_delegation_and_retry_are_protocol_violations(self):
        for kind in ["tool", "subtask", "retry"]:
            ndjson, exp = capture()
            exp["messages"][0]["parts"][0]["type"] = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.parse(ndjson, exp)
        with self.assertRaises(ValueError):
            self.parse(ndjson=json.dumps({"type": "tool_use", "sessionID": SID}))

    def test_duplicate_export_message_is_rejected_not_double_counted(self):
        _, exp = capture()
        exp["messages"].append(copy.deepcopy(exp["messages"][0]))
        with self.assertRaises(ValueError):
            self.parse(exported=exp)

    def test_reported_variant_is_not_invented(self):
        _, exp = capture()
        exp["messages"][0]["info"]["variant"] = "xhigh"
        self.assertEqual(self.parse(exported=exp)["reported_variant"], "xhigh")

    def test_files_are_exact_inert_allowlist(self):
        files = {"assets/lua/sized.fnl": "(inert)", "assets/lua/tests/test-sized.fnl": "(also inert)"}
        self.assertEqual(pilot.parse_files(json.dumps({"files": files, "notes": "not executed"})), files)
        for invalid in ["not json",
                        json.dumps({"files": {"../../outside.fnl": "x", "assets/lua/tests/test-sized.fnl": "y"}, "notes": "proposed"}),
                        json.dumps({"files": {**files, "extra.fnl": "x"}, "notes": "proposed"}),
                        '{"files":{"assets/lua/sized.fnl":"x","assets/lua/sized.fnl":"y","assets/lua/tests/test-sized.fnl":"z"},"notes":"proposed"}',
                        json.dumps({"files": {**files, "assets/lua/sized.fnl": 4}, "notes": "proposed"}),
                        json.dumps({"files": {"assets/lua/sized.fnl": "x"}, "notes": "proposed"}),
                        json.dumps({"files": files}),
                        json.dumps({"files": files, "notes": "", "extra": "bad"})]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                pilot.parse_files(invalid)


@unittest.skipIf(pilot is None, "runner not yet implemented")
class ControlRootTests(unittest.TestCase):
    def test_run_cli_rejects_outside_root_before_any_artifact_read(self):
        for outside in ["/tmp/opencode/old-run", "/outside-pilot/run"]:
            argv = ["pilot", "run", "--run-root", outside]
            with self.subTest(root=outside), patch.object(sys, "argv", argv), patch.object(Path, "resolve", autospec=True, side_effect=lambda path: path), patch.object(Path, "read_text", side_effect=AssertionError("artifact read before root rejection")) as read, patch.object(pilot.subprocess, "Popen") as popen, patch.object(pilot.subprocess, "run") as subprocess_run, patch.object(pilot, "run_trial") as run_trial:
                with self.assertRaises(ValueError):
                    pilot.main()
                read.assert_not_called()
                popen.assert_not_called()
                subprocess_run.assert_not_called()
                run_trial.assert_not_called()

    def test_run_cli_uses_validated_resolved_root_for_read_and_trials(self):
        resolved = Path("/tmp/space/opencode-model-pilot/resolved-run")
        argv = ["pilot", "run", "--run-root", "/tmp/space/opencode-model-pilot/alias-run"]
        trial = {"id": "synthetic"}
        with patch.object(sys, "argv", argv), patch.object(Path, "resolve", return_value=resolved), patch.object(Path, "read_text", autospec=True, return_value=json.dumps({"trials": [trial]})) as read, patch.object(pilot, "run_trial", return_value={"outcome": "complete"}) as run_trial, patch("builtins.print"):
            pilot.main()
        read.assert_called_once_with(resolved / "manifest.json")
        self.assertEqual(run_trial.call_args.args[:2], (trial, resolved))

    def test_only_configured_space_pilot_descendants_are_allowed(self):
        # Pure path checks: never inspect either configured or denied artifacts.
        with patch.object(Path, "resolve", autospec=True, side_effect=lambda path: path):
            allowed = Path("/tmp/space/opencode-model-pilot/task1-reviewed-2026-10-25")
            try:
                actual = pilot.control_root(allowed)
            except ValueError as exc:
                self.fail(f"configured Space pilot descendant rejected: {exc}")
            self.assertEqual(actual, allowed)
            for denied in ["/tmp/opencode/old-run", "/tmp/space/other-run",
                           "/tmp/space/opencode-model-pilot-other/run",
                           "/tmp/space/opencode-model-pilot", "/tmp/space"]:
                with self.subTest(path=denied), self.assertRaises(ValueError):
                    pilot.control_root(Path(denied))

    def test_resolved_escape_is_rejected(self):
        with patch.object(Path, "resolve", return_value=Path("/tmp/space/outside-pilot")):
            with self.assertRaises(ValueError):
                pilot.control_root(Path("/tmp/space/opencode-model-pilot/escape"))


@unittest.skipIf(pilot is None, "runner not yet implemented")
class CaptureProcessCleanupTests(unittest.TestCase):
    def assert_exception_cleanup(self, failure, kill_failure=None, drain_failure=None):
        with tempfile.TemporaryDirectory(prefix="capture-cleanup-test-") as directory:
            root = Path(directory)
            (root / "opencode.json").write_text("{}")
            prefix = root / "capture"
            proc = Mock(pid=987654, returncode=None)
            order = []

            def communicate(**kwargs):
                if kwargs:  # First call: child started and already produced raw output.
                    stdout = popen.call_args.kwargs["stdout"]
                    stderr = popen.call_args.kwargs["stderr"]
                    stdout.write(b"partial answer")
                    stderr.write(b"partial diagnostic")
                    stdout.flush()
                    stderr.flush()
                    order.append("interrupted")
                    raise failure
                order.append("drain")
                if drain_failure is not None:
                    raise drain_failure
                proc.returncode = -pilot.signal.SIGKILL

            def kill_group(pid, sig):
                order.append("kill")
                self.assertEqual((pid, sig), (proc.pid, pilot.signal.SIGKILL))
                if kill_failure is not None:
                    raise kill_failure

            def wait():
                order.append("reap")
                proc.returncode = -pilot.signal.SIGKILL
                return proc.returncode

            proc.communicate.side_effect = communicate
            proc.wait.side_effect = wait
            with patch.object(pilot.subprocess, "Popen", return_value=proc) as popen, \
                    patch.object(pilot.os, "killpg", side_effect=kill_group) as kill:
                with self.assertRaises(type(failure)) as raised:
                    pilot.capture_process(["opencode", "run"], root, time.time() + 120, prefix)
            self.assertIs(raised.exception, failure)
            if drain_failure is not None or (kill_failure is not None and not isinstance(kill_failure, ProcessLookupError)):
                self.assertIs(raised.exception.__cause__, drain_failure or kill_failure)
            popen.assert_called_once()
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            kill.assert_called_once_with(proc.pid, pilot.signal.SIGKILL)
            self.assertEqual(proc.communicate.call_count, 2)
            self.assertEqual(proc.returncode, -pilot.signal.SIGKILL)
            self.assertLess(order.index("kill"), order.index("drain"))
            if drain_failure is not None:
                proc.wait.assert_called_once_with()
                self.assertLess(order.index("drain"), order.index("reap"))
            self.assertEqual(prefix.with_suffix(".stdout.txt").read_bytes(), b"partial answer")
            self.assertEqual(prefix.with_suffix(".stderr.txt").read_bytes(), b"partial diagnostic")
            self.assertTrue(popen.call_args.kwargs["stdout"].closed)
            self.assertTrue(popen.call_args.kwargs["stderr"].closed)

    def test_capture_process_interrupt_kills_and_reaps_process_group(self):
        self.assert_exception_cleanup(KeyboardInterrupt())

    def test_capture_process_other_exceptional_exits_kill_and_reap(self):
        for failure in (SystemExit(7), OSError("communicate failed")):
            with self.subTest(failure=type(failure).__name__):
                self.assert_exception_cleanup(failure)

    def test_capture_process_exited_group_race_preserves_original_exception(self):
        for failure in (KeyboardInterrupt(), subprocess.TimeoutExpired("opencode", 120)):
            with self.subTest(failure=type(failure).__name__):
                self.assert_exception_cleanup(failure, kill_failure=ProcessLookupError())

    def test_capture_process_kill_error_still_reaps_and_preserves_original_exception(self):
        self.assert_exception_cleanup(KeyboardInterrupt(), kill_failure=PermissionError("kill denied"))

    def test_capture_process_cleanup_interrupt_still_waits_and_preserves_original_exception(self):
        self.assert_exception_cleanup(SystemExit(7), drain_failure=KeyboardInterrupt())


@unittest.skipIf(pilot is None, "runner not yet implemented")
class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pilot-test-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        # Disposable fixtures only; actual external-root preflight belongs to the
        # authorized controller, not this offline suite.
        root_patch = patch.object(pilot, "RUN_ROOT", Path(self.tmp.name).resolve())
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.root = Path(self.tmp.name) / "run"
        self.manifest = pilot.prepare(ROOT, self.root)

    def test_fresh_preparation_is_empty_and_reproducible(self):
        with patch.object(pilot.subprocess, "Popen", wraps=subprocess.Popen) as popen:
            second_root = self.root.parent / "second"
            second = pilot.prepare(ROOT, second_root)
        self.assertTrue(all(call.args[0][:2] == ["git", "show"] for call in popen.call_args_list))
        self.assertEqual(self.manifest["artifacts"], second["artifacts"])
        self.assertEqual(self.manifest["cases_sha256"], second["cases_sha256"])
        for name in self.manifest["artifacts"]:
            self.assertEqual((self.root / name).read_bytes(), (second_root / name).read_bytes())
        for root in [self.root, second_root]:
            self.assertEqual(list((root / "reservations").iterdir()), [])
            self.assertEqual(list((root / "results").iterdir()), [])
            self.assertFalse((root / "deadline.json").exists())

    def test_schedule_sources_hashes_and_contract_equality(self):
        trials = self.manifest["trials"]
        self.assertEqual(len(trials), 11)
        self.assertEqual(len({t["id"] for t in trials}), 11)
        self.assertEqual([t["id"] for t in trials], [
            "tab-architecture-glm", "tab-architecture-gpt", "search-review-gpt", "search-review-glm",
            "tab-escalation-glm", "tab-escalation-gpt", "sized-handoff-gpt", "sized-handoff-glm",
            "sized-glm-plain", "sized-gpt-contract", "sized-glm-contract"])
        self.assertEqual([t["model"] for t in trials[:4]], [pilot.GLM, pilot.GPT, pilot.GPT, pilot.GLM])
        for trial in trials:
            self.assertEqual(trial["seconds"], 360 if trial["implementation"] else 180)
            self.assertEqual(trial["variant"], ("high" if trial["implementation"] else "xhigh") if trial["model"] == pilot.GPT else "high")
        config = json.loads((self.root / "control/opencode.json").read_text())
        self.assertNotIn("variant", config)
        self.assertEqual(config["agent"]["pilot"]["variant"], "high")
        self.assertEqual(self.manifest["contract_gpt_sha256"], self.manifest["contract_glm_sha256"])
        for filename, digest in self.manifest["artifacts"].items():
            self.assertEqual(pilot.sha256((self.root / filename).read_bytes()), digest)
        self.assertGreaterEqual(len(self.manifest["sources"]), 11)
        self.assertTrue(all(s["blob_sha256"] and s["excerpt_sha256"] for s in self.manifest["sources"]))
        contract_packets = [(self.root / t["packet"]).read_bytes() for t in trials if t["id"] in ["sized-gpt-contract", "sized-glm-contract"]]
        self.assertEqual(*contract_packets)

    def test_no_private_answers_or_static_vectors_in_packets(self):
        cases = json.loads((ROOT / "scripts/evals/opencode_pilot_cases.json").read_text())
        for trial in self.manifest["trials"]:
            packet = (self.root / trial["packet"]).read_text()
            self.assertNotIn("evaluator_only", packet)
            for answer in cases["evaluator_only"]["canaries"]:
                self.assertNotIn(answer, packet)
            for answer in cases["evaluator_only"]["search-review"].values():
                self.assertNotIn(answer, packet)
        self.assertFalse(list(self.root.rglob("*.fnl")))

    def test_old_no_high_trial_and_config_are_readable_but_cannot_generate(self):
        config_path = self.root / "control/opencode.json"
        prepared_config = json.loads(config_path.read_text())
        for target in ["trial", "config", "both"]:
            for variant in [None, "low", "max"]:
                manifest, config = copy.deepcopy(self.manifest), copy.deepcopy(prepared_config)
                trial = manifest["trials"][0]
                if target in ["trial", "both"]:
                    trial["variant"] = variant
                if target in ["config", "both"]:
                    config["agent"]["pilot"].pop("variant", None)
                    if variant is not None:
                        config["agent"]["pilot"]["variant"] = variant
                pilot.save(config_path, config)
                manifest["artifacts"]["control/opencode.json"] = pilot.sha256(config_path.read_bytes())
                pilot.save(self.root / "manifest.json", manifest)
                before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
                self.assertEqual(pilot.checked_manifest(self.root)["trials"], manifest["trials"])
                with self.subTest(target=target, variant=variant), patch.object(pilot.subprocess, "Popen") as popen:
                    with self.assertRaisesRegex(ValueError, "high"):
                        pilot.run_trial(trial, self.root, time.time() + 5400)
                    # Continuation rejects before dispatch, even to a mocked run_trial.
                    with patch.object(pilot, "run_trial") as run:
                        with self.assertRaisesRegex(ValueError, "high"):
                            pilot.continue_unreserved(self.root)
                        run.assert_not_called()
                popen.assert_not_called()
                self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_glm_generation_requests_high_and_checks_reported_mode(self):
        for index, variant in enumerate(["high", None, "low", "max"]):
            trial = [t for t in self.manifest["trials"] if t["model"] == pilot.GLM][index]
            ndjson, exported = capture()
            info = exported["messages"][0]["info"]
            info.update(providerID="opencode-go", modelID="glm-5.3-flash")
            if variant is not None:
                info["variant"] = variant
            with self.subTest(variant=variant), patch.object(pilot.subprocess, "Popen", side_effect=[self.process(ndjson), self.process(json.dumps(exported))]) as popen:
                result = pilot.run_trial(trial, self.root, time.time() + 5400)
                args = popen.call_args_list[0].args[0]
                self.assertEqual(args[args.index("--variant") + 1], "high")
                self.assertEqual(result["outcome"], "complete" if variant == "high" else "protocol_violation")
                # Neutral historical parsing must not invent the requested mode.
                self.assertEqual(pilot.parse_capture(ndjson, exported, pilot.GLM, SID)["reported_variant"], variant)

    def test_seeded_variants_and_shared_public_requirements(self):
        cases = json.loads((ROOT / "scripts/evals/opencode_pilot_cases.json").read_text())
        source = subprocess.run(["git", "show", cases["source_commit"] + ":assets/lua/search-view.fnl"], cwd=ROOT, capture_output=True, check=True).stdout.decode()
        variants = {v["label"]: pilot.mutate(source, v["edits"]) for v in cases["cases"][1]["variants"]}
        self.assertIn("(self.layout:drop)", variants["A"])
        self.assertNotIn("(self.root:drop)", variants["A"])
        self.assertIn("(self.root:drop)\n                (self.input:drop)", variants["B"])
        self.assertIn("(options.external-changed:connect", variants["C"])
        self.assertIn("(self.input.model.changed:disconnect self.__external-listener true)", variants["C"])
        self.assertIn("(options.external-changed:disconnect self.__external-listener true)", variants["D"])
        plain = (self.root / "packets/sized-plain.txt").read_text()
        contract = (self.root / "packets/sized-contract.txt").read_text()
        self.assertTrue(contract.startswith(plain))
        self.assertNotIn(cases["contract"]["text"], plain)
        handoff = (self.root / "packets/sized-handoff.txt").read_text()
        self.assertIn(cases["sized_requirements"], handoff)
        self.assertIn("(set self.measure current-size)", handoff)
        self.assertIn("(if (> opts.size.x 0) opts.size.x max-size.x)", handoff)
        self.assertNotIn("Return strict JSON", handoff)

    def test_prepare_only_uses_pinned_git_not_opencode(self):
        with patch.object(pilot.subprocess, "run", wraps=subprocess.run) as run:
            pilot.prepare(ROOT, self.root.parent / "second")
        self.assertTrue(run.call_args_list)
        self.assertTrue(all(call.args[0][:2] == ["git", "show"] for call in run.call_args_list))

    def test_existing_root_and_outside_control_root_rejected(self):
        with self.assertRaises(FileExistsError):
            pilot.prepare(ROOT, self.root)
        with self.assertRaises(ValueError):
            pilot.prepare(ROOT, ROOT / "never-create-pilot")

    def legacy_config(self):
        path = self.root / "control/opencode.json"
        config = json.loads(path.read_text())
        config.pop("$schema", None)
        original = (json.dumps(config, indent=2) + "\n").encode()
        path.write_bytes(original)
        manifest = json.loads((self.root / "manifest.json").read_text())
        manifest["artifacts"]["control/opencode.json"] = pilot.sha256(original)
        pilot.save(self.root / "manifest.json", manifest)
        return path, config, original

    def test_schema_annotation_only_matches_frozen_legacy_hash(self):
        path, config, original = self.legacy_config()
        config["$schema"] = "https://opencode.ai/config.json"
        # CLI formatting may differ; the original canonical bytes still must match.
        actual = json.dumps(config).encode()
        path.write_bytes(actual)
        manifest_bytes = (self.root / "manifest.json").read_bytes()
        try:
            verified = pilot.checked_manifest(self.root)
        except ValueError as exc:
            self.fail(f"known schema-only annotation rejected: {exc}")
        self.assertEqual(verified["artifact_annotations"], [{
            "path": "control/opencode.json", "expected_sha256": pilot.sha256(original),
            "actual_sha256": pilot.sha256(actual),
            "accepted_annotation": {"$schema": "https://opencode.ai/config.json"}}])
        self.assertEqual(path.read_bytes(), actual)
        self.assertEqual((self.root / "manifest.json").read_bytes(), manifest_bytes)

    def test_schema_annotation_rejects_unknown_and_behavior_changes(self):
        path, config, _ = self.legacy_config()
        for mutation in ["schema", "permission", "agent_permission", "prompt", "other"]:
            changed = copy.deepcopy(config)
            changed["$schema"] = "https://opencode.ai/config.json"
            if mutation == "schema":
                changed["$schema"] = "https://unknown.invalid/schema"
            elif mutation == "permission":
                changed["permission"] = "allow"
            elif mutation == "agent_permission":
                changed["agent"]["pilot"]["permission"] = "allow"
            elif mutation == "prompt":
                changed["agent"]["pilot"]["prompt"] += " changed"
            else:
                changed["extra"] = True
            path.write_text(json.dumps(changed, indent=2) + "\n")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                pilot.checked_manifest(self.root)

    def test_schema_annotation_does_not_relax_other_artifacts(self):
        path, config, _ = self.legacy_config()
        config["$schema"] = "https://opencode.ai/config.json"
        path.write_text(json.dumps(config, indent=2) + "\n")
        packet = self.root / self.manifest["trials"][0]["packet"]
        packet.write_bytes(packet.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            pilot.checked_manifest(self.root)

    def test_future_preparation_includes_schema_in_strict_frozen_bytes(self):
        path = self.root / "control/opencode.json"
        self.assertEqual(json.loads(path.read_text()).get("$schema"), "https://opencode.ai/config.json")
        self.assertEqual(pilot.sha256(path.read_bytes()), self.manifest["artifacts"]["control/opencode.json"])

    def test_schema_annotation_is_explicit_recovery_metadata(self):
        path, config, original = self.legacy_config()
        config["$schema"] = "https://opencode.ai/config.json"
        path.write_text(json.dumps(config, indent=2) + "\n")
        trial, exported = self.failed_collection()
        with patch.object(pilot.subprocess, "Popen", return_value=self.process(json.dumps(exported))):
            try:
                record = pilot.recover_export(self.root, trial["id"])
            except ValueError as exc:
                self.fail(f"schema-only recovery preflight rejected: {exc}")
        self.assertEqual(record["outcome"], "complete")
        annotation = record["artifact_annotations"][0]
        self.assertEqual(annotation["expected_sha256"], pilot.sha256(original))
        self.assertEqual(annotation["actual_sha256"], pilot.sha256(path.read_bytes()))
        self.assertEqual(annotation["accepted_annotation"], {"$schema": "https://opencode.ai/config.json"})
        stored = json.loads((self.root / record["effective_result"]["collection_recovery"]).read_text())
        self.assertEqual(stored["artifact_annotations"], record["artifact_annotations"])

    def process(self, stdout, returncode=0):
        proc = Mock(pid=987654, returncode=returncode)
        def communicate(**_kwargs):
            destination = pilot.subprocess.Popen.call_args.kwargs["stdout"]
            if hasattr(destination, "write"):
                destination.write(stdout.encode())
                destination.flush()
            return stdout, ""
        proc.communicate.side_effect = communicate
        return proc

    def test_destination_sensitive_capture_preserves_exact_large_json(self):
        # A synthetic CLI chooses truncation based on the destination type, not
        # ordinary pipe capacity (communicate already handles normal large output).
        source = "import os,stat,json; data=json.dumps({'answer':'x'*73449}).encode(); regular=stat.S_ISREG(os.fstat(1).st_mode); os.write(1,data if regular else data[:65536]); os.write(2,b'diagnostic')"
        expected = json.dumps({"answer": "x" * 73449})
        actual = pilot.capture_process([sys.executable, "-c", source], self.root / "control",
                                       time.time() + 10, self.root / "raw/destination")
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(actual, expected)
        self.assertEqual(json.loads(actual)["answer"], "x" * 73449)
        self.assertEqual((self.root / "raw/destination.stderr.txt").read_text(), "diagnostic")

    def test_capture_nonzero_preserves_files_and_never_overwrites(self):
        args = [sys.executable, "-c", "import os; os.write(1,b'partial'); os.write(2,b'failed'); raise SystemExit(3)"]
        prefix = self.root / "raw/nonzero"
        with self.assertRaises(ValueError):
            pilot.capture_process(args, self.root / "control", time.time() + 10, prefix)
        self.assertEqual(prefix.with_suffix(".stdout.txt").read_text(), "partial")
        self.assertEqual(prefix.with_suffix(".stderr.txt").read_text(), "failed")
        with self.assertRaises(FileExistsError):
            pilot.capture_process(args, self.root / "control", time.time() + 10, prefix)

    def failed_collection(self):
        trial = next(t for t in self.manifest["trials"] if t["model"] == MODEL)
        ndjson, exported = capture()
        (self.root / "reservations" / trial["id"]).write_text("original reservation")
        pilot.save(self.root / "deadline.json", {"started_at": 1, "deadline": time.time() + 5000})
        result = {"trial_id": trial["id"], "outcome": "infrastructure_error", "failure_type": "JSONDecodeError"}
        pilot.save(self.root / "results" / (trial["id"] + ".json"), result)
        for suffix, text in [("run.stdout", ndjson), ("run.stderr", ""), ("export.stdout", '{"truncated":'), ("export.stderr", "old diagnostic")]:
            (self.root / "raw" / (trial["id"] + "-" + suffix + ".txt")).write_text(text)
        return trial, exported

    def test_recovery_is_explicit_same_session_and_preserves_originals(self):
        self.assertTrue(callable(getattr(pilot, "recover_export", None)), "explicit export recovery missing")
        trial, exported = self.failed_collection()
        originals = {p: p.read_bytes() for folder in ["raw", "results", "reservations"] for p in (self.root / folder).iterdir()}
        deadline = (self.root / "deadline.json").read_bytes()
        with patch.object(pilot.subprocess, "Popen", return_value=self.process(json.dumps(exported))) as popen:
            record = pilot.recover_export(self.root, trial["id"])
        self.assertEqual(record["outcome"], "complete")
        self.assertEqual(record["effective_result"]["answer"], "final answer")
        self.assertEqual(popen.call_args.args[0], ["opencode", "export", "--pure", SID])
        self.assertEqual(popen.call_count, 1)
        for path, data in originals.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual((self.root / "deadline.json").read_bytes(), deadline)
        self.assertEqual(len(list((self.root / "recoveries" / trial["id"]).glob("*/record.json"))), 1)
        with patch.object(pilot.subprocess, "Popen") as popen, self.assertRaises(ValueError):
            pilot.recover_export(self.root, trial["id"])
        popen.assert_not_called()

    def test_recovery_rejects_changed_answer_or_model_and_keeps_failure_history(self):
        self.assertTrue(callable(getattr(pilot, "recover_export", None)), "explicit export recovery missing")
        trial, exported = self.failed_collection()
        for mutation in ["answer", "model", "session", "incomplete"]:
            changed = copy.deepcopy(exported)
            if mutation == "answer":
                changed["messages"][0]["parts"][1]["text"] = "different answer"
            elif mutation == "model":
                changed["messages"][0]["info"]["modelID"] = "different-model"
            elif mutation == "session":
                changed["info"]["id"] = "ses_other"
            else:
                changed["messages"][0]["info"]["finish"] = "length"
            with patch.object(pilot.subprocess, "Popen", return_value=self.process(json.dumps(changed))):
                record = pilot.recover_export(self.root, trial["id"])
            self.assertNotEqual(record["outcome"], "complete")
        self.assertEqual(len(list((self.root / "recoveries" / trial["id"]).glob("*/record.json"))), 4)
        with patch.object(pilot, "run_trial") as run, self.assertRaises(ValueError):
            pilot.continue_unreserved(self.root)
        run.assert_not_called()

    def test_recovery_refuses_ineligible_trial_without_export(self):
        self.assertTrue(callable(getattr(pilot, "recover_export", None)), "explicit export recovery missing")
        trial, _ = self.failed_collection()
        path = self.root / "results" / (trial["id"] + ".json")
        for failure in ["ValueError", "TimeoutExpired"]:
            result = json.loads(path.read_text())
            result["failure_type"] = failure
            pilot.save(path, result)
            with patch.object(pilot.subprocess, "Popen") as popen, self.assertRaises(ValueError):
                pilot.recover_export(self.root, trial["id"])
            popen.assert_not_called()

    def test_recovery_malformed_saved_run_or_expired_deadline_never_exports(self):
        trial, _ = self.failed_collection()
        run_path = self.root / "raw" / (trial["id"] + "-run.stdout.txt")
        ndjson = run_path.read_text()
        run_path.write_text("invalid saved run")
        with patch.object(pilot.subprocess, "Popen") as popen, self.assertRaises(ValueError):
            pilot.recover_export(self.root, trial["id"])
        popen.assert_not_called()
        run_path.write_text(ndjson)
        pilot.save(self.root / "deadline.json", {"deadline": time.time() - 1})
        with patch.object(pilot.subprocess, "Popen") as popen:
            self.assertEqual(pilot.recover_export(self.root, trial["id"])["outcome"], "deadline")
        popen.assert_not_called()

    def test_recovery_timeout_preserves_failure_and_reaps_once(self):
        trial, _ = self.failed_collection()
        proc = self.process("")
        proc.communicate.side_effect = [subprocess.TimeoutExpired("export", 180), (None, None)]
        with patch.object(pilot.subprocess, "Popen", return_value=proc) as popen, patch.object(pilot.os, "killpg") as kill:
            record = pilot.recover_export(self.root, trial["id"])
        self.assertEqual(record["outcome"], "timeout")
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(proc.communicate.call_count, 2)
        kill.assert_called_once_with(proc.pid, pilot.signal.SIGKILL)
        self.assertEqual(json.loads((self.root / "results" / (trial["id"] + ".json")).read_text())["outcome"], "infrastructure_error")

    def test_continuation_revalidates_recovered_evidence(self):
        trial, exported = self.failed_collection()
        with patch.object(pilot.subprocess, "Popen", return_value=self.process(json.dumps(exported))):
            record = pilot.recover_export(self.root, trial["id"])
        (self.root / record["export_stdout"]).write_text("changed")
        with patch.object(pilot, "run_trial") as run, self.assertRaises(ValueError):
            pilot.continue_unreserved(self.root)
        run.assert_not_called()

    def test_continuation_rejects_recovery_record_identity_tampering(self):
        trial, exported = self.failed_collection()
        with patch.object(pilot.subprocess, "Popen", return_value=self.process(json.dumps(exported))):
            record = pilot.recover_export(self.root, trial["id"])
        path = self.root / record["effective_result"]["collection_recovery"]
        record["session_id"] = "ses_other"
        pilot.save(path, record)
        with patch.object(pilot, "run_trial", return_value={"outcome": "timeout"}) as run, patch("builtins.print"), self.assertRaises(ValueError):
            pilot.continue_unreserved(self.root)
        run.assert_not_called()

    def test_continuation_skips_verified_complete_and_runs_all_unreserved_once(self):
        ndjson, exported = capture()
        trial = next(t for t in self.manifest["trials"] if t["model"] == MODEL)
        with patch.object(pilot.subprocess, "Popen", side_effect=[self.process(ndjson), self.process(json.dumps(exported))]):
            pilot.run_trial(trial, self.root, time.time() + 5400)
        with patch.object(pilot, "run_trial", return_value={"outcome": "complete"}) as run, patch("builtins.print"):
            self.assertEqual(pilot.continue_unreserved(self.root)["outcome"], "complete")
        ids = [call.args[0]["id"] for call in run.call_args_list]
        self.assertEqual(ids, [t["id"] for t in self.manifest["trials"] if t["id"] != trial["id"]])
        self.assertEqual(len(ids), len(set(ids)))

    def test_recovery_and_continuation_cli_dispatch(self):
        for command in ["recover-export", "continue-unreserved"]:
            argv = ["pilot", command, "--run-root", str(self.root)]
            if command == "recover-export":
                argv += ["--trial-id", "tab-architecture-glm"]
            with patch.object(sys, "argv", argv), patch.object(pilot, "recover_export", return_value={"outcome": "complete"}) as recover, patch.object(pilot, "continue_unreserved", return_value={"outcome": "complete"}) as continuation, patch("builtins.print"):
                pilot.main()
            if command == "recover-export":
                recover.assert_called_once_with(self.root, "tab-architecture-glm")
                continuation.assert_not_called()
            else:
                continuation.assert_called_once_with(self.root)
                recover.assert_not_called()

    def test_continue_only_unreserved_preserves_deadline_and_stops_on_failure(self):
        self.assertTrue(callable(getattr(pilot, "recover_export", None)), "explicit export recovery missing")
        trial, exported = self.failed_collection()
        with patch.object(pilot.subprocess, "Popen", return_value=self.process(json.dumps(exported))):
            pilot.recover_export(self.root, trial["id"])
        deadline = (self.root / "deadline.json").read_bytes()
        with patch.object(pilot, "run_trial", return_value={"outcome": "timeout"}) as run, patch("builtins.print") as output:
            summary = pilot.continue_unreserved(self.root)
        self.assertEqual(summary["outcome"], "timeout")
        self.assertEqual(run.call_count, 1)
        self.assertNotEqual(run.call_args.args[0]["id"], trial["id"])
        self.assertEqual(run.call_args.args[2], json.loads(deadline)["deadline"])
        self.assertTrue(any('"skipped_reserved"' in str(call) for call in output.call_args_list))
        self.assertEqual((self.root / "deadline.json").read_bytes(), deadline)

    def test_continue_expired_or_unresolved_never_calls_candidate(self):
        self.assertTrue(callable(getattr(pilot, "continue_unreserved", None)), "explicit continuation missing")
        trial, _ = self.failed_collection()
        with patch.object(pilot, "run_trial") as run, self.assertRaises(ValueError):
            pilot.continue_unreserved(self.root)
        run.assert_not_called()
        # Unreserved-only run with an existing expired ledger still cannot call.
        (self.root / "reservations" / trial["id"]).unlink()
        pilot.save(self.root / "deadline.json", {"deadline": time.time() - 1})
        with patch.object(pilot, "run_trial") as run, patch("builtins.print"):
            self.assertEqual(pilot.continue_unreserved(self.root)["outcome"], "deadline")
        run.assert_not_called()

    def test_one_fresh_session_own_export_no_reasoning_and_no_retry(self):
        ndjson, exported = capture()
        trial = next(t for t in self.manifest["trials"] if t["model"] == MODEL)
        with patch.object(pilot.subprocess, "Popen", side_effect=[self.process(ndjson), self.process(json.dumps(exported))]) as popen:
            result = pilot.run_trial(trial, self.root, time.time() + 5400)
            self.assertEqual(result["outcome"], "complete")
            self.assertEqual(result["answer"], "final answer")
            self.assertEqual(popen.call_count, 2)
            run_args = popen.call_args_list[0].args[0]
            self.assertIn("--pure", run_args)
            self.assertNotIn("--session", run_args)
            self.assertNotIn("--continue", run_args)
            self.assertEqual(popen.call_args_list[1].args[0], ["opencode", "export", "--pure", SID])
            self.assertEqual(popen.call_args_list[0].kwargs["cwd"], self.root / "control")
            with self.assertRaises(FileExistsError):
                pilot.run_trial(trial, self.root, time.time() + 5400)
            self.assertEqual(popen.call_count, 2)
        self.assertNotIn("PRIVATE_REASONING", (self.root / "results" / (trial["id"] + ".json")).read_text())
        config = json.loads((self.root / "control/opencode.json").read_text())
        self.assertEqual(config["permission"], "deny")
        self.assertTrue(all(a["permission"] == "deny" for a in config["agent"].values()))

    def test_timeout_kills_group_and_is_reserved(self):
        proc = self.process("")
        proc.communicate.side_effect = [subprocess.TimeoutExpired("opencode", 180), ("", "")]
        trial = self.manifest["trials"][0]
        with patch.object(pilot.subprocess, "Popen", return_value=proc) as popen, patch.object(pilot.os, "killpg") as kill:
            result = pilot.run_trial(trial, self.root, time.time() + 5400)
        self.assertEqual(result["outcome"], "timeout")
        self.assertEqual(popen.call_count, 1)
        kill.assert_called_once_with(proc.pid, pilot.signal.SIGKILL)
        self.assertTrue((self.root / "reservations" / trial["id"]).exists())

    def test_cli_instruction_is_frozen_at_preparation(self):
        ndjson, exported = capture()
        original_instruction = pilot.INSTRUCTION
        trial = next(t for t in self.manifest["trials"] if t["model"] == MODEL)
        with patch.object(pilot, "INSTRUCTION", "changed after preparation"), patch.object(pilot.subprocess, "Popen", side_effect=[self.process(ndjson), self.process(json.dumps(exported))]) as popen:
            pilot.run_trial(trial, self.root, time.time() + 5400)
        self.assertEqual(popen.call_args_list[0].args[0][-1], original_instruction)

    def test_deadline_persists_and_cannot_be_extended(self):
        trial = self.manifest["trials"][0]
        with patch.object(pilot.subprocess, "Popen") as popen:
            first = pilot.run_trial(trial, self.root, time.time() - 1)
            second = pilot.run_trial(self.manifest["trials"][1], self.root, time.time() + 5400)
        self.assertEqual(first["outcome"], "deadline")
        self.assertEqual(second["outcome"], "deadline")
        self.assertIsNone(second["sent_variant"])
        popen.assert_not_called()

    def test_export_timeout_also_kills_group_without_retry(self):
        ndjson, _ = capture()
        proc = self.process("")
        proc.communicate.side_effect = [subprocess.TimeoutExpired("opencode", 180), ("", "")]
        with patch.object(pilot.subprocess, "Popen", side_effect=[self.process(ndjson), proc]) as popen, patch.object(pilot.os, "killpg") as kill:
            result = pilot.run_trial(self.manifest["trials"][0], self.root, time.time() + 5400)
        self.assertEqual(result["outcome"], "timeout")
        self.assertEqual(popen.call_count, 2)
        kill.assert_called_once()

    def test_implementation_response_is_parsed_but_never_applied(self):
        ndjson, exported = capture()
        exported["messages"][0]["parts"][1]["text"] = json.dumps({"files": {path: "(inert)" for path in pilot.FILES}, "notes": "proposed only"})
        trial = next(t for t in self.manifest["trials"] if t["id"] == "sized-gpt-contract")
        with patch.object(pilot.subprocess, "Popen", side_effect=[self.process(ndjson), self.process(json.dumps(exported))]):
            result = pilot.run_trial(trial, self.root, time.time() + 5400)
        self.assertEqual(result["outcome"], "complete")
        self.assertFalse(list(self.root.rglob("*.fnl")))

    def test_invalid_implementation_answer_is_not_infrastructure_failure(self):
        ndjson, exported = capture()
        trial = next(t for t in self.manifest["trials"] if t["id"] == "sized-gpt-contract")
        with patch.object(pilot.subprocess, "Popen", side_effect=[self.process(ndjson), self.process(json.dumps(exported))]):
            result = pilot.run_trial(trial, self.root, time.time() + 5400)
        self.assertEqual(result["outcome"], "invalid_answer")
        self.assertEqual(result["answer"], "final answer")

    def test_unowned_mixed_sessions_and_failed_cli_never_export(self):
        for index, (stdout, code) in enumerate([(capture()[0].replace(SID, "") , 0),
                                                (capture()[0] + '\n{"sessionID":"ses_other","type":"text"}', 0),
                                                (capture()[0], 1)]):
            with patch.object(pilot.subprocess, "Popen", return_value=self.process(stdout, code)) as popen:
                result = pilot.run_trial(self.manifest["trials"][index], self.root, time.time() + 5400)
            self.assertEqual(result["outcome"], "infrastructure_error")
            self.assertEqual(popen.call_count, 1)

    def test_tampered_packet_or_unplanned_trial_never_invokes(self):
        trial = self.manifest["trials"][0]
        for changed in [{**trial, "model": "other/model"}, trial]:
            if changed == trial:
                (self.root / trial["packet"]).write_text("changed")
            with patch.object(pilot.subprocess, "Popen") as popen, self.assertRaises(ValueError):
                pilot.run_trial(changed, self.root, time.time() + 5400)
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
