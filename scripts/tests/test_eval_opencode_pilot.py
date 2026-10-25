"""Offline orchestration tests: fixtures are inert strings; no model or Fennel runs."""
import copy
import importlib.util
import json
from pathlib import Path
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
class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pilot-test-", dir="/tmp/opencode")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "run"
        self.manifest = pilot.prepare(ROOT, self.root)

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
            self.assertEqual(trial["variant"], ("high" if trial["implementation"] else "xhigh") if trial["model"] == pilot.GPT else None)
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

    def process(self, stdout, returncode=0):
        proc = Mock(pid=987654, returncode=returncode)
        proc.communicate.return_value = (stdout, "")
        return proc

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
