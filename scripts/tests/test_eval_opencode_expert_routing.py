"""Offline only: disposable fixtures and mocked CLI; never controller artifacts."""
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
SPEC = importlib.util.spec_from_file_location("routing", ROOT / "scripts/eval_opencode_expert_routing.py")
routing = None
if Path(SPEC.origin).exists():
    routing = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(routing)


def test_helper_exists():
    assert routing is not None, "routing helper not implemented"


@pytest.fixture(autouse=True)
def require_helper(request):
    if routing is None and request.node.name != "test_helper_exists":
        pytest.skip("helper not implemented")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "RUN_ROOT", tmp_path / "runtime")
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in routing.SOURCES:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Full context for " + name + "\nmodel: baseline-gpt\n")
    routing.prepare(repo)
    return repo, routing.RUN_ROOT


def answer():
    return {"decisions": [{**case, "route": routing.EXPECTED[case["case_id"]],
                            "implementation_owner": routing.owner(case["workflow"]),
                            "rationale": "Virtual only; preserve validation and independent review gates."}
                           for case in routing.matrix() for case in
                           [{k: case[k] for k in ("case_id", "workflow", "actor")}]]}


def capture(sid, text):
    part = {"id": "text", "type": "text", "text": text, "sessionID": sid, "messageID": "msg"}
    stop = {"type": "step_finish", "sessionID": sid,
            "part": {"type": "step-finish", "sessionID": sid, "reason": "stop"}}
    events = json.dumps({"type": "text", "sessionID": sid, "part": part}) + "\n" + json.dumps(stop)
    export = {"info": {"id": sid}, "messages": [{"info": {
        "id": "msg", "sessionID": sid, "role": "assistant", "providerID": "opencode-go",
        "modelID": "glm-5.3-flash", "finish": "stop", "time": {"completed": 1}},
        "parts": [part, {**part, "type": "reasoning", "text": "PRIVATE_REASONING"}]}]}
    return events, export


def fake_cli(monkeypatch, mutation=None, elapsed=2):
    calls, clock = [], [1000.0]
    monkeypatch.setattr(routing.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(routing.time, "time", lambda: clock[0])

    def invoke(args, control, deadline, prefix):
        calls.append((args, deadline))
        clock[0] += elapsed
        sid = "ses_fresh" + str((len(calls) + 1) // 2)
        ndjson, exported = capture(sid, json.dumps(answer()))
        if mutation:
            ndjson, exported = mutation(ndjson, exported)
        return ndjson if args[1] == "run" else json.dumps(exported)

    monkeypatch.setattr(routing, "capture_process", invoke)
    return calls, clock


def test_outside_root_rejected_before_read(monkeypatch):
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("unexpected read"))
    monkeypatch.setattr(Path, "resolve", lambda *a, **k: pytest.fail("outside path resolved"))
    with pytest.raises(ValueError):
        routing.checked_runtime_path(Path("/tmp/not-allowed/result.json"))


def test_symlink_escape_and_symlink_root_rejected(workspace, tmp_path):
    _, root = workspace
    (root / "escape").symlink_to(tmp_path)
    with pytest.raises(ValueError):
        routing.checked_runtime_path(root / "escape/private.json")
    root.rename(root.with_name("moved"))
    root.symlink_to(root.with_name("moved"), target_is_directory=True)
    with pytest.raises(ValueError):
        routing.checked_runtime_path(root / "manifest.json")


def test_exclusive_preparation_frozen_full_context_and_no_oracle(workspace):
    repo, root = workspace
    with pytest.raises(FileExistsError):
        routing.prepare(repo)
    packet = (root / "baseline/packet.txt").read_text()
    for name in routing.SOURCES:
        assert (repo / name).read_text() in packet
    assert "EXPECTED" not in packet and "evaluator-only" not in packet
    assert "baseline-gpt" in packet
    config = json.loads((root / "control/opencode.json").read_text())
    assert next(iter(config)) == "$schema"
    assert config["model"] == routing.GLM and config["permission"] == "deny"
    assert config["agent"]["routing-eval"]["permission"] == "deny"
    assert "variant" not in config
    assert "variant" not in config["agent"]["routing-eval"]
    assert 12 <= len(routing.matrix()) <= 18
    assert {c["workflow"] for c in routing.matrix()} == {"supervisor", "fast-dev", "live-dev"}


def test_guidance_before_baseline_and_invalid_phase_never_call(workspace, monkeypatch):
    calls, _ = fake_cli(monkeypatch)
    for phase in ["guidance", "other"]:
        with pytest.raises(ValueError):
            routing.run_phase(workspace[0], phase)
    assert not calls


def test_exact_ten_fresh_calls_frozen_matrix_sources_and_no_retries(workspace, monkeypatch):
    repo, root = workspace
    calls, clock = fake_cli(monkeypatch)
    baseline = routing.run_phase(repo, "baseline")
    assert len(baseline["results"]) == 5
    clock[0] += 100000  # Offline review/human pause must NOT consume budget.
    guidance_start = clock[0]
    (repo / "AGENTS.md").write_text("Updated same source guidance")
    guidance = routing.run_phase(repo, "guidance")
    assert len(guidance["results"]) == 5
    assert len(calls) == 20  # ten generations + ten own-session exports
    assert calls[10][1] == guidance_start + 180
    for args, _ in calls[::2]:
        assert args[:3] == ["opencode", "run", "--pure"]
        assert args[args.index("--model") + 1] == routing.GLM
        assert not set(args) & {"--variant", "--session", "--continue"}
    for args, _ in calls[1::2]:
        assert args[:3] == ["opencode", "export", "--pure"]
        assert args[3].startswith("ses_fresh")
    assert len(list((root / "reservations").iterdir())) == 10
    assert json.loads((root / "budget.json").read_text())["consumed_seconds"] == 40
    for phase in ["baseline", "guidance"]:
        with pytest.raises(FileExistsError):
            routing.run_phase(repo, phase)
    assert len(calls) == 20
    report = routing.report()
    assert report["comparison"][0]["assessment"] == "no_effect_control_already_complies"
    assert "PRIVATE_REASONING" not in json.dumps(report)
    assert "Updated same source guidance" in (root / "guidance/packet.txt").read_text()
    assert "baseline-gpt" in (root / "baseline/packet.txt").read_text()


def test_duplicate_reservation_refused_before_calls(workspace, monkeypatch):
    calls, _ = fake_cli(monkeypatch)
    (workspace[1] / "reservations/baseline-3").write_text("consumed")
    with pytest.raises(FileExistsError):
        routing.run_phase(workspace[0], "baseline")
    assert not calls


def test_changed_baseline_context_or_frozen_artifact_blocks(workspace, monkeypatch):
    repo, root = workspace
    calls, _ = fake_cli(monkeypatch)
    (repo / "AGENTS.md").write_text("premature policy edit")
    with pytest.raises(ValueError):
        routing.run_phase(repo, "baseline")
    assert not calls


def test_frozen_symlink_escape_rejected_before_content_read(workspace, tmp_path, monkeypatch):
    repo, root = workspace
    packet = root / "baseline/packet.txt"
    packet.unlink()
    packet.symlink_to(tmp_path / "private.txt")
    original = Path.read_text
    def guarded_read(path, *args, **kwargs):
        assert path != packet, "escaped packet read before rejection"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", guarded_read)
    calls, _ = fake_cli(monkeypatch)
    with pytest.raises(ValueError, match="symlink"):
        routing.run_phase(repo, "baseline")
    assert not calls


def test_exclusive_execution_guard_and_phase_guard(workspace, monkeypatch):
    repo, root = workspace
    calls, _ = fake_cli(monkeypatch)
    (root / "execution.lock").write_text("other caller")
    with pytest.raises(FileExistsError):
        routing.run_phase(repo, "baseline")
    assert (root / "execution.lock").read_text() == "other caller"
    (root / "execution.lock").unlink()
    (root / "baseline.guard").write_text("aborted phase")
    with pytest.raises(FileExistsError):
        routing.run_phase(repo, "baseline")
    assert not calls


def test_frozen_schema_matrix_or_oracle_change_blocks(workspace, monkeypatch):
    repo, root = workspace
    calls, _ = fake_cli(monkeypatch)
    (root / "schema.json").write_text("{}")
    with pytest.raises(ValueError, match="frozen artifact"):
        routing.run_phase(repo, "baseline")
    assert not calls


def test_timeouts_count_active_cli_only_and_share_run_export_deadline(workspace, monkeypatch):
    repo, root = workspace
    calls, clock = fake_cli(monkeypatch)
    invoke = routing.capture_process
    def timeout_export(args, *rest):
        text = invoke(args, *rest)
        if args[1] == "export":
            raise subprocess.TimeoutExpired("export", 180)
        return text
    monkeypatch.setattr(routing, "capture_process", timeout_export)
    results = routing.run_phase(repo, "baseline")["results"]
    assert all(r["outcome"] == "timeout" for r in results)
    assert json.loads((root / "budget.json").read_text())["consumed_seconds"] == 20
    assert all(calls[i][1] == calls[i + 1][1] for i in range(0, 10, 2))
    clock[0] += 999999
    routing.run_phase(repo, "guidance")
    assert json.loads((root / "budget.json").read_text())["consumed_seconds"] == 40
    assert routing.report()["comparison"] == []


def test_guidance_snapshot_hash_is_checked_in_report(workspace, monkeypatch):
    repo, root = workspace
    fake_cli(monkeypatch)
    routing.run_phase(repo, "baseline")
    routing.run_phase(repo, "guidance")
    (root / "guidance/packet.txt").write_text("changed")
    with pytest.raises(ValueError, match="frozen artifact"):
        routing.report()


def test_changed_evaluator_cannot_rescore_frozen_baseline(workspace, monkeypatch):
    calls, _ = fake_cli(monkeypatch)
    monkeypatch.setattr(routing, "EXPECTED", {**routing.EXPECTED, "first-syntax": "blocked"})
    with pytest.raises(ValueError, match="helper contract"):
        routing.run_phase(workspace[0], "baseline")
    assert not calls


def test_fixed_oracle_covers_all_predicates_without_ownership_transfer():
    rows = routing.matrix()
    assert len(rows) == len({(r["case_id"], r["workflow"], r["actor"]) for r in rows})
    for workflow in ["supervisor", "fast-dev", "live-dev"]:
        assert routing.owner(workflow) == ("implementer" if workflow == "supervisor" else workflow)
        for case in ["first-syntax", "tdd-red", "reviewed-reuse", "manual-refresh", "wrap-up-review"]:
            assert routing.EXPECTED[case] == "glm"
        for case in ["fresh-local-design", "confident-contract", "fresh-live-design", "ownership-transition", "same-failure", "critical-security", "material-contract-change"]:
            assert routing.EXPECTED[case] == "expert_advisor"
        for row in rows:
            if row["case_id"].startswith("denied-"):
                assert routing.EXPECTED[row["case_id"]] == "request_consultation"
        assert routing.EXPECTED["human-policy"] == "human"


def test_actor_ids_are_real_roles_and_worker_cannot_delegate():
    rows = routing.matrix()
    for row in rows:
        assert row["actor"] in {"supervisor", "fast-dev", "live-dev", "implementer", "reviewer", "planner", "adjudicator", "debug-advisor", "fast-dev-reviewer"}
    row = next(r for r in rows if r["case_id"] == "denied-reviewer")
    assert row["actor"] == "reviewer" and row["workflow"] == "supervisor"
    assert routing.EXPECTED["advice-not-approval"] == "blocked"


def test_dual_model_request_and_compact_matrix_contract():
    assert "glm_proposal" in routing.INSTRUCTION
    assert "regardless of confidence" in routing.INSTRUCTION
    assert "1–2 sentences" in routing.INSTRUCTION
    rows = routing.matrix()
    assert len({r["case_id"] for r in rows}) == len(rows)
    assert len(rows) == routing.SCHEMA["properties"]["decisions"]["minItems"]
    for name in ("fresh-local-design", "confident-contract", "fresh-live-design"):
        text = next(r["scenario"] for r in rows if r["case_id"] == name)
        assert "confident" in text
    reuse = next(r["scenario"] for r in rows if r["case_id"] == "reviewed-reuse")
    assert "unchanged" in reuse and "reconciled" in reuse


def test_report_exposes_consumed_attempt_without_result(workspace):
    _, root = workspace
    (root / "reservations/baseline-1").write_text("interrupted")
    report = routing.report()
    assert report["attempts"]["baseline-1"] == "reserved_without_result"
    assert report["attempts"]["guidance-1"] == "unreserved"


def test_cleanup_time_over_cap_is_retained_and_blocks_further_calls(workspace, monkeypatch):
    repo, root = workspace
    (root / "budget.json").write_text(json.dumps({"consumed_seconds": 2099}))
    calls, _ = fake_cli(monkeypatch, elapsed=3)
    def timeout(*args, **kwargs):
        calls.append(args)
        # Monotonic fixture increments simulate timeout cleanup overrun.
        clock[0] += 3
        raise subprocess.TimeoutExpired("opencode", 1)
    clock = [1000.0]
    monkeypatch.setattr(routing.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(routing, "capture_process", timeout)
    results = routing.run_phase(repo, "baseline")["results"]
    assert results[0]["outcome"] == "timeout"
    assert all(r["outcome"] == "budget_exhausted" for r in results[1:])
    routing.run_phase(repo, "guidance")
    assert len(calls) == 1
    assert json.loads((root / "budget.json").read_text())["consumed_seconds"] == 2102


def test_budget_exhaustion_persists_and_failures_consume_slots(workspace, monkeypatch):
    repo, root = workspace
    calls, _ = fake_cli(monkeypatch)
    (root / "budget.json").write_text(json.dumps({"consumed_seconds": 2100}))
    result = routing.run_phase(repo, "baseline")
    assert {r["outcome"] for r in result["results"]} == {"budget_exhausted"}
    assert not calls
    result = routing.run_phase(repo, "guidance")
    assert len(result["results"]) == 5 and not calls
    assert json.loads((root / "budget.json").read_text())["consumed_seconds"] == 2100


@pytest.mark.parametrize("fault", ["model", "session", "incomplete", "tool", "retry", "variant", "malformed"])
def test_capture_failures_are_not_quality_scores_or_retries(workspace, monkeypatch, fault):
    def mutate(ndjson, exp):
        msg = exp["messages"][0]
        if fault == "model":
            msg["info"]["modelID"] = "wrong"
        elif fault == "session":
            exp["info"]["id"] = "ses_other"
        elif fault == "incomplete":
            msg["info"]["finish"] = "length"
        elif fault in {"tool", "retry"}:
            msg["parts"].append({**msg["parts"][0], "type": fault})
        elif fault == "variant":
            msg["info"]["variant"] = "high"
        else:
            ndjson = "malformed"
        return ndjson, exp
    calls, _ = fake_cli(monkeypatch, mutate)
    results = routing.run_phase(workspace[0], "baseline")["results"]
    assert len(results) == 5 and all(r["outcome"] != "complete" for r in results)
    assert not any("scores" in r for r in results)
    assert len(calls) == (5 if fault == "malformed" else 10)
    assert routing.report()["comparison"] == []


def test_reused_session_is_not_a_fresh_sample(workspace, monkeypatch):
    calls, _ = fake_cli(monkeypatch, lambda n, e: (
        n.replace(json.loads(n.splitlines()[0])["sessionID"], "ses_reused"),
        json.loads(json.dumps(e).replace(e["info"]["id"], "ses_reused"))))
    results = routing.run_phase(workspace[0], "baseline")["results"]
    assert results[0]["outcome"] == "complete"
    assert all(r["outcome"] == "protocol_violation" for r in results[1:])
    assert len(calls) == 6


def test_answer_exact_coverage_and_virtual_only():
    good = answer()
    assert routing.parse_answer(json.dumps(good)) == good
    variants = ["```json\n" + json.dumps(good) + "\n```", '{"decisions":[],"decisions":[]}']
    for change in ["missing", "duplicate", "extra", "actor", "route", "owner", "execution"]:
        bad = copy.deepcopy(good)
        if change == "missing":
            bad["decisions"].pop()
        elif change == "duplicate":
            bad["decisions"].append(bad["decisions"][0])
        elif change == "extra":
            bad["decisions"][0]["dispatch"] = "done"
        elif change == "execution":
            bad["decisions"][0]["rationale"] = "I have dispatched the expert and ran tests."
        else:
            bad["decisions"][0][change if change != "owner" else "implementation_owner"] = "invalid"
        variants.append(json.dumps(bad))
    for text in variants:
        with pytest.raises(ValueError):
            routing.parse_answer(text)


@pytest.mark.parametrize("claim", ["We ran the tests.", "The expert was dispatched.", "I executed the fix."])
def test_actual_action_claims_are_not_routing_rationales(claim):
    bad = answer()
    bad["decisions"][0]["rationale"] = claim
    with pytest.raises(ValueError, match="actual action"):
        routing.parse_answer(json.dumps(bad))


def test_wrong_route_and_owner_are_scored_not_hidden_as_infrastructure(workspace, monkeypatch):
    def mutate(n, e):
        bad = answer()
        bad["decisions"][0].update(route="expert_advisor", implementation_owner="expert-advisor")
        e["messages"][0]["parts"][0]["text"] = json.dumps(bad)
        return n, e
    fake_cli(monkeypatch, mutate)
    results = routing.run_phase(workspace[0], "baseline")["results"]
    assert results[0]["outcome"] == "complete"
    assert results[0]["scores"][0]["routing_match"] is False


def test_timeout_cleanup_and_large_regular_file_capture(workspace, monkeypatch):
    _, root = workspace
    proc = Mock(pid=98765, returncode=0)
    proc.communicate.side_effect = [subprocess.TimeoutExpired("opencode", 180), (None, None)]
    monkeypatch.setattr(routing.pilot.subprocess, "Popen", Mock(return_value=proc))
    kill = Mock()
    monkeypatch.setattr(routing.pilot.os, "killpg", kill)
    with pytest.raises(subprocess.TimeoutExpired):
        routing.capture_process(["opencode"], root / "control", routing.time.time() + 180, root / "raw/timeout")
    kill.assert_called_once()
    assert proc.communicate.call_count == 2
    assert (root / "raw/timeout.stdout.txt").is_file()
    payload = json.dumps({"text": "x" * 74000})
    def write_regular(*args, **kwargs):
        import stat
        assert stat.S_ISREG(routing.pilot.os.fstat(kwargs["stdout"].fileno()).st_mode)
        kwargs["stdout"].write(payload.encode())
        return Mock(returncode=0)
    monkeypatch.setattr(routing.pilot.subprocess, "Popen", write_regular)
    assert routing.capture_process(["mock"], root / "control", routing.time.time() + 180, root / "raw/large") == payload
