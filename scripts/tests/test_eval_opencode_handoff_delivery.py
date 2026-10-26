"""Offline only: synthetic roots and mocked CLI; no model, auth or live evidence access."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import eval_opencode_expert_routing as original
from test_eval_opencode_expert_routing import answer, capture

SPEC = importlib.util.spec_from_file_location("delivery", ROOT / "scripts/eval_opencode_handoff_delivery.py")
helper = None
if Path(SPEC.origin).exists():
    helper = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(helper)


def test_helper_exists():
    assert helper is not None, "delivery helper not implemented"


@pytest.fixture(autouse=True)
def offline(request, monkeypatch):
    if helper is None:
        if request.node.name != "test_helper_exists":
            pytest.skip("helper not implemented")
        return
    monkeypatch.setattr(helper, "capture_process", lambda *a, **k: pytest.fail("unmocked CLI"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("actual process forbidden"))


def case(**changes):
    return dict(identity="task/author/controller/branch/base/head/mode", repair_used=0,
                payload_valid=False, scope_current=True, facts_preserved=True,
                author_available=True, excluded=False) | changes


@pytest.mark.parametrize("changes,state,count", [
    ({"payload_valid": True}, "ELIGIBLE_FOR_NORMAL_HANDLING", 0),
    ({}, "FORMAT_REPAIR_REQUIRED", 1),
    ({"repair_used": 1, "payload_valid": True}, "ELIGIBLE_FOR_NORMAL_HANDLING", 1),
    ({"repair_used": 1}, "BLOCKED", 1),
    ({"scope_current": False}, "BLOCKED", 0),
    ({"facts_preserved": False}, "BLOCKED", 0),
    ({"author_available": False}, "BLOCKED", 0),
    ({"excluded": True}, "BLOCKED", 0),
])
def test_delivery_transitions(changes, state, count):
    fixture = case(**changes)
    result = helper.evaluate_delivery(fixture)
    assert result["identity"] == fixture["identity"]
    assert result["state"] == state and result["repair_used"] == count
    assert result["reasons"] and "approved" not in result
    assert fixture == case(**changes), "evaluation mutated caller state"


def test_duplicate_renamed_counter_and_declared_json_markdown_contracts():
    for declared, text in [("JSON", '{"status":"pending"}'), ("Markdown", "# Plan\nPending review")]:
        first = helper.evaluate_delivery(case(declared_format=declared, payload=text))
        duplicate = helper.evaluate_delivery(case(repair_used=first["repair_used"], label="renamed"))
        assert duplicate["state"] == "BLOCKED" and duplicate["repair_used"] == 1
        valid = helper.evaluate_delivery(case(payload_valid=True, declared_format=declared, payload=text))
        assert valid["state"] == "ELIGIBLE_FOR_NORMAL_HANDLING"
    # Validity is explicit fixture evidence, never a universal JSON-only parser.
    for excluded in ("GPT expert", "capability wrapper refusal"):
        assert helper.evaluate_delivery(case(excluded=True, author=excluded))["state"] == "BLOCKED"


@pytest.mark.parametrize("change", [{"repair_used": -1}, {"repair_used": 2}, {"repair_used": True},
                                   {"payload_valid": "yes"}, {"identity": ""}])
def test_invalid_fixture_state_is_not_silently_defaulted(change):
    with pytest.raises(ValueError):
        helper.evaluate_delivery(case(**change))


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    old, clarified, runtime, repo = [tmp_path / p for p in ("old", "clarified", "delivery", "repo")]
    monkeypatch.setattr(helper, "OLD_ROOT", old)
    monkeypatch.setattr(helper, "CLARIFIED_ROOT", clarified)
    monkeypatch.setattr(helper, "RUN_ROOT", runtime)
    for p in (old, clarified, repo):
        p.mkdir()
    for i in range(72):
        (old / f"file-{i}").write_text("historical")
    (old / "budget.json").write_text('{"consumed_seconds":593.4621967620624}')
    (clarified / "budget.json").write_text('{"consumed_seconds":339.499002335011}')
    bad = answer()
    next(r for r in bad["decisions"] if r["case_id"] == "wrap-up-review")["workflow"] = "fast-dev-reviewer"
    ndjson, exported = capture(helper.AUTHOR, json.dumps(bad))
    for name, value in {"results/clarified-2.json": json.dumps({"session_id": helper.AUTHOR,
            "answer": json.dumps(bad), "actual_model": original.GLM}),
            "raw/clarified-2-run.stdout.txt": ndjson,
            "raw/clarified-2-export.stdout.txt": json.dumps(exported)}.items():
        p = clarified / name
        p.parent.mkdir(exist_ok=True)
        p.write_text(value)
    for name in original.SOURCES:
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("Full old policy context: " + name)
    before = helper.historical_snapshot()
    helper.prepare(repo)
    return repo, runtime, clarified, before, exported, bad


def fake_cli(monkeypatch, workspace, fault=None):
    calls, clock = [], [1000.0]
    monkeypatch.setattr(helper.time, "time", lambda: clock[0])
    monkeypatch.setattr(helper.time, "monotonic", lambda: clock[0])
    pre = copy.deepcopy(workspace[4])
    def invoke(args, control, deadline, prefix):
        calls.append((args, deadline))
        clock[0] += 2
        if "--session" in args or prefix.name == "repair-post":
            ndjson, new = capture(helper.AUTHOR, json.dumps(answer()))
            ndjson = ndjson.replace('"msg"', '"new"')
            new = json.loads(json.dumps(new).replace('"msg"', '"new"'))
            if fault:
                ndjson, new = fault(ndjson, new)
            exported = {"info": pre["info"], "messages": pre["messages"] + new["messages"]}
        elif prefix.name == "repair-pre":
            return json.dumps(pre)
        else:
            sid = "ses_fresh" + str(sum(a[0][1] == "run" for a in calls))
            ndjson, exported = capture(sid, "Five plain routing explanations, not JSON.")
            if fault:
                ndjson, exported = fault(ndjson, exported)
        return ndjson if args[1] == "run" else json.dumps(exported)
    monkeypatch.setattr(helper, "capture_process", invoke)
    return calls, clock


def test_scopes_rejected_lexically_before_any_read_or_resolve(monkeypatch):
    assert helper.RUN_ROOT == Path("/tmp/space/opencode-handoff-delivery")
    monkeypatch.setattr(Path, "resolve", lambda *a: pytest.fail("outside resolve"))
    monkeypatch.setattr(Path, "read_bytes", lambda *a: pytest.fail("outside read"))
    with pytest.raises(ValueError, match="outside"):
        helper.checked_path(Path("/private/denied"), helper.RUN_ROOT)
    with pytest.raises(ValueError, match="outside"):
        helper.checked_path(helper.RUN_ROOT / "../other/file", helper.RUN_ROOT)


@pytest.mark.parametrize("target", ["baseline/packet.txt", "control/opencode.json", "raw/baseline-1-run.stdout.txt"])
def test_symlink_rejection_before_calls(workspace, monkeypatch, tmp_path, target):
    p = workspace[1] / target
    if p.exists():
        p.unlink()
    p.symlink_to(tmp_path / "denied")
    calls, _ = fake_cli(monkeypatch, workspace)
    with pytest.raises(ValueError, match="symlink"):
        helper.micro("baseline")
    assert not calls


def test_historical_symlinks_rejected_before_content(workspace, tmp_path):
    p = workspace[2] / "raw/escape"
    p.symlink_to(tmp_path / "denied")
    with pytest.raises(ValueError, match="symlink"):
        helper.historical_snapshot()


def test_freeze_sources_questions_rubric_config_and_old_snapshots(workspace):
    repo, runtime, _, before, _, _ = workspace
    assert helper.historical_snapshot() == before
    manifest = helper.verified_manifest()
    assert manifest["historical"] == before
    assert manifest["limits"] == {"micro_per_phase": 5, "micro_seconds": 120, "repair_generations": 1, "repair_seconds": 180}
    packet = (runtime / "baseline/packet.txt").read_text()
    assert helper.QUESTION in packet and helper.RUBRIC not in packet
    assert "decisions array" not in packet and "OLD_ANSWER" not in packet
    for name in original.SOURCES:
        assert (repo / name).read_text() in packet
    config = json.loads((runtime / "control/opencode.json").read_text())
    assert next(iter(config)) == "$schema"
    assert config["permission"] == config["agent"]["routing-eval"]["permission"] == "deny"
    assert config["model"] == config["agent"]["routing-eval"]["model"] == original.GLM
    assert "variant" not in json.dumps(config)
    assert config["plugin"] == [] and config["mcp"] == {}
    with pytest.raises(FileExistsError):
        helper.prepare(repo)


def test_five_slots_each_phase_no_resampling_and_shared_120_deadlines(workspace, monkeypatch):
    calls, _ = fake_cli(monkeypatch, workspace)
    helper.micro("baseline")
    (workspace[0] / "AGENTS.md").write_text("New policy context")
    helper.micro("guidance")
    assert len(calls) == 20
    for i in range(0, 20, 2):
        assert calls[i][1] == calls[i+1][1] == 1120 + i * 2
        assert not {"--session", "--continue", "--variant"} & set(calls[i][0])
    for phase in ("baseline", "guidance"):
        with pytest.raises(FileExistsError):
            helper.micro(phase)
        assert helper.QUESTION in (workspace[1] / phase / "packet.txt").read_text()
    report = helper.report()
    assert len(report["attempts"]) == 11
    assert report["budget"] == {"micro_seconds": 40, "repair_seconds": 0}
    assert len(report["results"]) == 10 and "PRIVATE_REASONING" not in json.dumps(report)
    assert "manual" in report["interpretation"] and "no improvement" in report["interpretation"]
    assert helper.historical_snapshot() == workspace[3]


def test_source_match_and_baseline_before_guidance_guards(workspace, monkeypatch):
    calls, _ = fake_cli(monkeypatch, workspace)
    with pytest.raises(ValueError, match="baseline"):
        helper.micro("guidance")
    (workspace[0] / "AGENTS.md").write_text("changed too early")
    with pytest.raises(ValueError, match="source"):
        helper.micro("baseline")
    assert not calls


@pytest.mark.parametrize("target", ["baseline/packet.txt", "questions.txt", "rubric.txt", "control/opencode.json"])
def test_changed_frozen_files_block(workspace, monkeypatch, target):
    (workspace[1] / target).write_text("changed")
    calls, _ = fake_cli(monkeypatch, workspace)
    with pytest.raises(ValueError, match="frozen"):
        helper.micro("baseline")
    assert not calls


def test_changed_historical_raw_blocks_without_generation(workspace, monkeypatch):
    (workspace[2] / "raw/clarified-2-run.stdout.txt").write_text("changed")
    calls, _ = fake_cli(monkeypatch, workspace)
    with pytest.raises(ValueError, match="historical"):
        helper.replay()
    assert not calls


def test_crash_reserves_all_five_slots_and_budget_first(workspace, monkeypatch):
    def crash(*args):
        assert len(list((workspace[1] / "reservations").iterdir())) == 5
        assert helper.report()["budget"]["micro_seconds"] == 120
        raise KeyboardInterrupt
    monkeypatch.setattr(helper, "capture_process", crash)
    with pytest.raises(KeyboardInterrupt):
        helper.micro("baseline")
    with pytest.raises(FileExistsError):
        helper.micro("baseline")


def test_capture_interrupt_cleanup_keeps_delivery_slots_and_budget_consumed(workspace, monkeypatch):
    pilot = original.pilot
    failure = KeyboardInterrupt()
    proc = Mock(pid=987654, returncode=None)
    proc.communicate.side_effect = [failure, (None, None)]
    popen, kill = Mock(return_value=proc), Mock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(pilot.os, "killpg", kill)
    monkeypatch.setattr(helper, "capture_process", pilot.capture_process)
    with pytest.raises(KeyboardInterrupt) as raised:
        helper.micro("baseline")
    assert raised.value is failure
    kill.assert_called_once_with(proc.pid, pilot.signal.SIGKILL)
    assert proc.communicate.call_count == 2
    report = helper.report()
    assert report["budget"] == {"micro_seconds": 120, "repair_seconds": 0}
    assert all(report["attempts"][f"baseline-{i}"] == "reserved_without_result" for i in range(1, 6))
    assert helper.historical_snapshot() == workspace[3]
    with pytest.raises(FileExistsError):
        helper.micro("baseline")
    popen.assert_called_once()


def test_timeouts_consume_phase_without_retries(workspace, monkeypatch):
    calls = []
    def timeout(args, control, deadline, prefix):
        calls.append(args)
        raise subprocess.TimeoutExpired("opencode", 120)
    monkeypatch.setattr(helper, "capture_process", timeout)
    results = helper.micro("baseline")["results"]
    assert len(calls) == 5 and all(r["outcome"] == "timeout" for r in results)
    with pytest.raises(FileExistsError):
        helper.micro("baseline")


@pytest.mark.parametrize("fault", ["model", "variant", "tools", "incomplete", "extra_assistant", "wrong_session"])
def test_micro_actual_identity_and_single_completed_tool_free_message(workspace, monkeypatch, fault):
    def corrupt(ndjson, exported):
        info = exported["messages"][0]["info"]
        if fault == "model": info["modelID"] = "wrong"
        elif fault == "variant": info["variant"] = "high"
        elif fault == "tools": exported["messages"][0]["parts"].append({**exported["messages"][0]["parts"][0], "type": "tool"})
        elif fault == "incomplete": info["finish"] = "length"
        elif fault == "extra_assistant": exported["messages"].append(copy.deepcopy(exported["messages"][0]))
        else: exported["info"]["id"] = "ses_other"
        return ndjson, exported
    calls, _ = fake_cli(monkeypatch, workspace, corrupt)
    assert all(r["outcome"] != "complete" for r in helper.micro("baseline")["results"])
    assert len(calls) == 10


def test_replay_single_original_author_only_new_message_and_preserved_protected_fields(workspace, monkeypatch):
    calls, _ = fake_cli(monkeypatch, workspace)
    result = helper.replay()
    assert result["state"] == "ELIGIBLE_FOR_NORMAL_HANDLING" and result["repair_succeeded"] is True
    assert result["repair_used"] == 1 and result["session_id"] == helper.AUTHOR
    assert json.loads((workspace[1] / "repair-state.json").read_text())["state"] == "FORMAT_REPAIR_REQUIRED"
    assert result["usage"][0]["message_id"] == "new" and len(result["usage"]) == 1
    assert len(calls) == 3 and {d for _, d in calls} == {1180}
    assert calls[0][0] == calls[2][0] == ["opencode", "export", "--pure", helper.AUTHOR]
    assert calls[1][0][calls[1][0].index("--session") + 1] == helper.AUTHOR
    assert "--variant" not in calls[1][0]
    packet = (workspace[1] / "repair-packet.txt").read_text()
    assert "wrap-up-review" in packet and "workflow" in packet and "fast-dev" in packet
    assert "EXPECTED" not in packet and "evaluator-only" not in packet
    assert helper.historical_snapshot() == workspace[3]
    with pytest.raises(FileExistsError): helper.replay()
    assert len(calls) == 3


@pytest.mark.parametrize("fault", ["rationale", "route", "owner", "invalid", "still_wrong", "extra_message", "old_edit"])
def test_replay_invalid_or_changed_facts_blocks_not_second_generation(workspace, monkeypatch, fault):
    def corrupt(ndjson, exported):
        row = answer()
        if fault in ("rationale", "route", "owner"):
            row["decisions"][0][{"owner": "implementation_owner"}.get(fault, fault)] = {
                "rationale": "Changed substantive findings", "route": "blocked", "owner": "fast-dev"}[fault]
        text = json.dumps(workspace[5] if fault == "still_wrong" else row)
        exported["messages"][0]["parts"][0]["text"] = "not JSON" if fault == "invalid" else text
        # Valid protected-field changes must reach facts comparison, not fail transport checks.
        events = [json.loads(line) for line in ndjson.splitlines()]
        events[0]["part"]["text"] = exported["messages"][0]["parts"][0]["text"]
        ndjson = "\n".join(json.dumps(e) for e in events)
        if fault == "extra_message": exported["messages"].append(copy.deepcopy(exported["messages"][0]))
        return ndjson, exported
    calls, _ = fake_cli(monkeypatch, workspace, corrupt)
    if fault == "old_edit":
        invoke = helper.capture_process
        def edit(args, control, deadline, prefix):
            text = invoke(args, control, deadline, prefix)
            if prefix.name == "repair-post":
                value = json.loads(text)
                value["messages"][0]["parts"][0]["text"] = "changed historical content"
                return json.dumps(value)
            return text
        monkeypatch.setattr(helper, "capture_process", edit)
    result = helper.replay()
    assert result["state"] == "BLOCKED" and not result["repair_succeeded"]
    assert result["repair_used"] == 1 and len(calls) == 3
    assert result["generation_attempted"] is True and "append" in result["history_append"]
    if fault in ("rationale", "route", "owner"):
        assert result["reasons"] == ["protected facts changed"]
    if fault == "invalid":
        assert result["answer"] == "not JSON"
        assert result["reasons"] == ["one correction exhausted; no additional generation"]
    with pytest.raises(FileExistsError): helper.replay()


def test_unavailable_original_author_blocks_before_generation(workspace, monkeypatch):
    calls = []
    def unavailable(args, *rest):
        calls.append(args)
        raise ValueError("own author unavailable")
    monkeypatch.setattr(helper, "capture_process", unavailable)
    result = helper.replay()
    assert result["state"] == "BLOCKED" and result["repair_used"] == 0
    assert len(calls) == 1 and calls[0][1] == "export"


@pytest.mark.parametrize("field,value", [("micro_seconds", -1), ("repair_seconds", True),
    ("micro_seconds", "0"), ("repair_seconds", float("nan")), ("micro_seconds", float("inf"))])
def test_invalid_persistent_budget_never_reset(workspace, monkeypatch, field, value):
    path = workspace[1] / "budget.json"
    data = json.dumps({"micro_seconds": 0, "repair_seconds": 0} | {field: value})
    path.write_text(data)
    calls, _ = fake_cli(monkeypatch, workspace)
    with pytest.raises(ValueError, match="budget"):
        helper.micro("baseline")
    assert not calls and path.read_text() == data


@pytest.mark.parametrize("stage", ["pre", "run", "post"])
def test_replay_timeout_budget_covers_all_three_operations_no_second_attempt(workspace, monkeypatch, stage):
    calls, clock = fake_cli(monkeypatch, workspace)
    invoke = helper.capture_process
    def timeout(args, control, deadline, prefix):
        text = invoke(args, control, deadline, prefix)
        if prefix.name == "repair-" + stage:
            clock[0] += 180
            raise subprocess.TimeoutExpired("opencode", 180)
        return text
    monkeypatch.setattr(helper, "capture_process", timeout)
    result = helper.replay()
    assert result["outcome"] == "timeout" and result["state"] == "BLOCKED"
    assert result["repair_used"] == (0 if stage == "pre" else 1)
    assert {d for _, d in calls} == {1180}
    assert helper.report()["budget"]["repair_seconds"] >= 180
    assert helper.report()["budget"]["micro_seconds"] == 0
    with pytest.raises(FileExistsError): helper.replay()


def test_no_new_run_message_identity_or_hidden_history_retry(workspace):
    pre = workspace[4]
    ndjson, new = capture(helper.AUTHOR, json.dumps(answer()))
    # Reusing the original assistant ID cannot select an old or rewritten answer.
    with pytest.raises(ValueError):
        helper.correction_capture(ndjson, pre, {"info": pre["info"], "messages": pre["messages"] + new["messages"]})
    ndjson = ndjson.replace('"msg"', '"new"')
    new = json.loads(json.dumps(new).replace('"msg"', '"new"'))
    post = {"info": pre["info"], "messages": pre["messages"] + new["messages"]}
    assert helper.correction_capture(ndjson, pre, post)["usage"][0]["message_id"] == "new"
    other = copy.deepcopy(new["messages"][0])
    other["info"]["id"] = "hiddenretry"
    post["messages"].append(other)
    with pytest.raises(ValueError): helper.correction_capture(ndjson, pre, post)


def test_only_cli_time_is_charged_not_packet_or_validation_work(workspace, monkeypatch):
    _, clock = fake_cli(monkeypatch, workspace)
    retained = helper.retained_repair
    def slow_offline_validation():
        clock[0] += 10
        return retained()
    monkeypatch.setattr(helper, "retained_repair", slow_offline_validation)
    helper.replay()
    assert helper.report()["budget"] == {"micro_seconds": 0, "repair_seconds": 6}


def test_failed_micro_session_is_recorded_and_cannot_reappear_in_guidance(workspace, monkeypatch):
    def bad_model(ndjson, exported):
        exported["messages"][0]["info"]["modelID"] = "wrong"
        return ndjson, exported
    fake_cli(monkeypatch, workspace, bad_model)
    baseline = helper.micro("baseline")["results"]
    assert baseline[0]["session_id"] == "ses_fresh1"
    # New mock counter intentionally repeats the exact five failed baseline IDs.
    calls, _ = fake_cli(monkeypatch, workspace)
    results = helper.micro("guidance")["results"]
    assert all(r["outcome"] == "blocked" for r in results)
    assert len(calls) == 5  # No export for reused identities.


def test_source_change_during_preexport_cannot_authorize_generation(workspace, monkeypatch):
    calls, _ = fake_cli(monkeypatch, workspace)
    invoke = helper.capture_process
    def change_source(args, *rest):
        value = invoke(args, *rest)
        (workspace[2] / "raw/clarified-2-run.stdout.txt").write_text("changed during preexport")
        return value
    monkeypatch.setattr(helper, "capture_process", change_source)
    with pytest.raises(ValueError, match="historical"):
        helper.replay()
    assert len(calls) == 1 and calls[0][0][1] == "export"


def test_full_fixed_ledger_permits_eleven_generations_not_twelve(workspace, monkeypatch):
    calls, _ = fake_cli(monkeypatch, workspace)
    helper.micro("baseline")
    helper.micro("guidance")
    helper.replay()
    assert sum(args[1] == "run" for args, _ in calls) == 11
    assert set(helper.report()["attempts"].values()) == {"recorded"}
    assert helper.historical_snapshot() == workspace[3]
    with pytest.raises(FileExistsError): helper.replay()
    with pytest.raises(FileExistsError): helper.micro("guidance")


@pytest.mark.parametrize("command", ["prepare", "micro", "replay", "report"])
def test_cli_is_explicit_never_implicit_execution(workspace, monkeypatch, capsys, command):
    monkeypatch.setattr(helper, command, lambda *a: {"called": command})
    monkeypatch.setattr(sys, "argv", ["delivery", command] +
        (["--repo-root", str(workspace[0])] if command == "prepare" else ["--phase", "baseline"] if command == "micro" else []))
    helper.main()
    assert json.loads(capsys.readouterr().out) == {"called": command}
