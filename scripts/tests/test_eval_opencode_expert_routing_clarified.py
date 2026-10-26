"""Offline fixtures only: no live roots, CLI calls, auth or candidate execution."""
import importlib.util
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import eval_opencode_expert_routing as original
from test_eval_opencode_expert_routing import answer, capture

SPEC = importlib.util.spec_from_file_location(
    "clarified", ROOT / "scripts/eval_opencode_expert_routing_clarified.py")
helper = None
if Path(SPEC.origin).exists():
    helper = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(helper)


def test_helper_exists():
    assert helper is not None, "clarification helper not implemented"


@pytest.fixture(autouse=True)
def offline(request, monkeypatch):
    if helper is None:
        if request.node.name != "test_helper_exists":
            pytest.skip("helper not implemented")
        return
    monkeypatch.setattr(helper, "capture_process", lambda *a, **k: pytest.fail("unmocked CLI"))


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    old = tmp_path / "original"
    new = tmp_path / "clarified"
    monkeypatch.setattr(helper, "OLD_ROOT", old)
    monkeypatch.setattr(helper, "RUN_ROOT", new)
    old.mkdir()
    for name in helper.OLD_FILES:
        path = old / name
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {"untouched": name}
        if name == "budget.json":
            value = {"consumed_seconds": 593.462}
        elif name.startswith("results/"):
            value = {"session_id": "ses_old" + path.stem.replace("-", ""),
                     "answer": "OLD_ANSWER_NOT_FOR_MODEL", "outcome": "invalid_answer"}
        path.write_text(json.dumps(value))
    (old / "raw").mkdir()
    (old / "raw/untouched.stdout.txt").write_bytes(b"```json\nmalformed old answer\xff\n```")
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in original.SOURCES:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Public context for " + name)
    before = {str(p.relative_to(old)): p.read_bytes() for p in old.rglob("*") if p.is_file()}
    helper.prepare(repo)
    return repo, new, old, before


def fake_cli(monkeypatch, mutation=None, elapsed=2):
    calls, clock = [], [1000.0]
    monkeypatch.setattr(helper.time, "time", lambda: clock[0])
    monkeypatch.setattr(helper.time, "monotonic", lambda: clock[0])

    def invoke(args, control, deadline, prefix):
        calls.append((args, deadline))
        clock[0] += elapsed
        sid = "ses_fresh" + str((len(calls) + 1) // 2)
        ndjson, exported = capture(sid, json.dumps(answer()))
        if mutation:
            ndjson, exported = mutation(ndjson, exported)
        return ndjson if args[1] == "run" else json.dumps(exported)

    monkeypatch.setattr(helper, "capture_process", invoke)
    return calls, clock


def test_fixed_separate_root_and_outside_rejection_before_resolve_or_read(monkeypatch):
    assert helper.RUN_ROOT == Path("/tmp/space/opencode-expert-routing-clarified")
    assert helper.OLD_ROOT == original.RUN_ROOT
    monkeypatch.setattr(Path, "read_bytes", lambda *a, **k: pytest.fail("read before scope check"))
    monkeypatch.setattr(Path, "resolve", lambda *a, **k: pytest.fail("resolve before lexical check"))
    for path in [original.RUN_ROOT / "manifest.json", Path("/tmp/private"),
                 helper.RUN_ROOT / ".." / "opencode-expert-routing/manifest.json"]:
        with pytest.raises(ValueError, match="outside"):
            helper.checked_path(path)
    with pytest.raises(ValueError, match="allowlist"):
        helper.read("raw/private.json", old=True)


@pytest.mark.parametrize("target", ["packet.txt", "control/opencode.json", "raw/clarified-1-run.stdout.txt"])
def test_symlink_escape_rejected_before_artifact_read(workspace, tmp_path, monkeypatch, target):
    _, new, _, _ = workspace
    path = new / target
    if path.exists():
        path.unlink()
    path.symlink_to(tmp_path / "denied")
    real_read = Path.read_bytes
    def guarded(path, *a, **k):
        assert path != new / target, "escaped artifact was read"
        return real_read(path, *a, **k)
    monkeypatch.setattr(Path, "read_bytes", guarded)
    calls, _ = fake_cli(monkeypatch)
    if target.startswith("raw/"):
        result = helper.run()["results"]
        assert result[0]["outcome"] != "complete"
        assert len(calls) <= 8
    else:
        with pytest.raises(ValueError, match="symlink"):
            helper.run()
        assert not calls


def test_symlink_root_and_original_metadata_fail_closed(workspace, tmp_path):
    _, new, old, _ = workspace
    new.rename(tmp_path / "moved")
    new.symlink_to(tmp_path / "moved", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        helper.report()
    new.unlink()
    (tmp_path / "moved").rename(new)
    path = old / "budget.json"
    path.unlink()
    path.symlink_to(tmp_path / "private")
    with pytest.raises(ValueError, match="symlink"):
        helper.report()


def test_freezes_same_contract_context_config_acceptance_and_no_old_answers(workspace):
    repo, new, old, _ = workspace
    with pytest.raises(FileExistsError):
        helper.prepare(repo)
    for name, expected in [("matrix.json", original.matrix()), ("schema.json", original.SCHEMA),
                           ("evaluator-only.json", original.EXPECTED)]:
        assert json.loads((new / name).read_text()) == expected
    packet = (new / "packet.txt").read_text()
    assert packet.startswith(original.INSTRUCTION)
    assert "OLD_ANSWER_NOT_FOR_MODEL" not in packet
    assert "evaluator-only" not in packet and "EXPECTED" not in packet
    for name in original.SOURCES:
        assert (repo / name).read_text() in packet
    manifest = json.loads((new / "manifest.json").read_text())
    assert manifest["original"]["consumed_generations"] == 10
    assert manifest["original"]["budget"] == {"consumed_seconds": 593.462}
    assert manifest["original"]["sha256"]["budget.json"] == original.pilot.sha256((old / "budget.json").read_bytes())
    assert manifest["limits"] == {"generations": 5, "run_and_export_seconds": 180, "aggregate_cli_seconds": 900}
    assert manifest["acceptance"] == helper.ACCEPTANCE
    assert "5/5" in helper.ACCEPTANCE and "90/90" in helper.ACCEPTANCE
    assert "manual" in helper.ACCEPTANCE and "18" in helper.ACCEPTANCE
    config = json.loads((new / "control/opencode.json").read_text())
    assert next(iter(config)) == "$schema"
    assert config["permission"] == config["agent"]["routing-eval"]["permission"] == "deny"
    assert config["model"] == config["agent"]["routing-eval"]["model"] == original.GLM
    assert "variant" not in config and "variant" not in config["agent"]["routing-eval"]
    assert config["plugin"] == [] and config["mcp"] == {}
    assert list((new / "results").iterdir()) == list((new / "reservations").iterdir()) == []


def test_appended_protocol_is_general_definitions_and_positive_raw_json_recipe():
    text = helper.CLARIFICATION
    for token in ["expert_advisor", "request_consultation", "needs_consultation", "glm", "human", "blocked",
                  "supervisor", "implementer", "fast-dev", "live-dev", "FIRST", "LAST", "{", "}",
                  "18", "six", "decisions", "1–2", "escaping", "markdown"]:
        assert token in text
    assert all(case[0] not in text for case in original.CASES)
    assert helper.INSTRUCTION == original.INSTRUCTION + helper.CLARIFICATION
    for text in ["```json\n" + json.dumps(answer()) + "\n```", '{"decisions": [}',
                 '{"decisions": [], "decisions": []}']:
        with pytest.raises(ValueError):
            original.parse_answer(text)


def test_exact_five_calls_no_sixth_no_continuation_shared_deadline_and_old_preservation(workspace, monkeypatch):
    _, new, old, before = workspace
    constants = copy.deepcopy((original.RUN_ROOT, original.INSTRUCTION, original.CASES,
                               original.SCHEMA, original.EXPECTED, original.SOURCES))
    calls, clock = fake_cli(monkeypatch)
    result = helper.run()
    assert all(r["outcome"] == "complete" for r in result["results"])
    assert len(calls) == 10
    assert all(calls[i][1] == calls[i + 1][1] for i in range(0, 10, 2))
    assert calls[0][1] == 1180
    for args, _ in calls[::2]:
        assert args[:3] == ["opencode", "run", "--pure"]
        assert args[args.index("--model") + 1] == original.GLM
        assert not set(args) & {"--variant", "--session", "--continue"}
        assert str(new / "packet.txt") in args
    for args, _ in calls[1::2]:
        assert args[:3] == ["opencode", "export", "--pure"]
        assert args[3].startswith("ses_fresh")
    clock[0] += 999999  # Human/offline pauses are not active CLI time.
    with pytest.raises(FileExistsError):
        helper.run()
    report = helper.report()
    assert report["strict_completed"] == 5 and report["routing_matches"] == 90
    assert report["acceptance"] == helper.ACCEPTANCE
    assert report["budget"] == {"consumed_seconds": 20}
    assert "PRIVATE_REASONING" not in json.dumps(report)
    assert {str(p.relative_to(old)): p.read_bytes() for p in old.rglob("*") if p.is_file()} == before
    assert original.RUN_ROOT != new
    assert constants == (original.RUN_ROOT, original.INSTRUCTION, original.CASES,
                         original.SCHEMA, original.EXPECTED, original.SOURCES)


@pytest.mark.parametrize("name", ["execution.lock", "clarified.guard", "reservations/clarified-3"])
def test_exclusive_guards_block_all_calls(workspace, monkeypatch, name):
    (workspace[1] / name).write_text("consumed")
    calls, _ = fake_cli(monkeypatch)
    with pytest.raises(FileExistsError):
        helper.run()
    assert not calls


@pytest.mark.parametrize("name", ["matrix.json", "schema.json", "evaluator-only.json", "packet.txt", "control/opencode.json"])
def test_frozen_changes_block_before_call(workspace, monkeypatch, name):
    (workspace[1] / name).write_text("{}")
    calls, _ = fake_cli(monkeypatch)
    with pytest.raises(ValueError, match="frozen"):
        helper.run()
    assert not calls


def test_changed_old_metadata_blocks_read_only_without_scoring(workspace, monkeypatch):
    (workspace[2] / "budget.json").write_text('{"consumed_seconds": 1}')
    calls, _ = fake_cli(monkeypatch)
    monkeypatch.setattr(original, "parse_answer", lambda *a: pytest.fail("old outputs rescored"))
    with pytest.raises(ValueError, match="original"):
        helper.report()
    with pytest.raises(ValueError, match="original"):
        helper.run()
    assert not calls


def test_report_only_uses_recorded_scores_never_reparses_old_or_new_answers(workspace, monkeypatch):
    fake_cli(monkeypatch)
    helper.run()
    monkeypatch.setattr(original, "parse_answer", lambda *a: pytest.fail("report reparsed answers"))
    assert helper.report()["routing_matches"] == 90


def test_crash_consumes_all_slots_and_reserves_budget_before_call(workspace, monkeypatch):
    _, new, _, _ = workspace
    def crash(*args):
        assert len(list((new / "reservations").iterdir())) == 5
        assert json.loads((new / "budget.json").read_text())["consumed_seconds"] == 180
        raise KeyboardInterrupt
    monkeypatch.setattr(helper, "capture_process", crash)
    with pytest.raises(KeyboardInterrupt):
        helper.run()
    with pytest.raises(FileExistsError):
        helper.run()
    assert helper.report()["attempts"] == {f"clarified-{i}": "reserved_without_result" for i in range(1, 6)}
    assert helper.report()["budget"]["consumed_seconds"] == 180


def test_timeout_cleanup_counts_and_900_budget_never_resets(workspace, monkeypatch):
    new = workspace[1]
    (new / "budget.json").write_text('{"consumed_seconds": 899}')
    calls, clock = fake_cli(monkeypatch)
    def timeout(args, control, deadline, prefix):
        calls.append((args, deadline))
        assert deadline == clock[0] + 1
        clock[0] += 3  # Timeout cleanup overrun is charged, not discarded.
        raise subprocess.TimeoutExpired("opencode", 1)
    monkeypatch.setattr(helper, "capture_process", timeout)
    results = helper.run()["results"]
    assert results[0]["outcome"] == "timeout"
    assert all(r["outcome"] == "budget_exhausted" for r in results[1:])
    assert len(calls) == 1 and helper.report()["budget"]["consumed_seconds"] == 902
    with pytest.raises(FileExistsError):
        helper.run()


def test_export_timeouts_consume_five_slots_and_full_shared_900_budget(workspace, monkeypatch):
    calls, _ = fake_cli(monkeypatch, elapsed=90)
    invoke = helper.capture_process
    def timeout_export(args, *rest):
        text = invoke(args, *rest)
        if args[1] == "export":
            raise subprocess.TimeoutExpired("export", 90)
        return text
    monkeypatch.setattr(helper, "capture_process", timeout_export)
    results = helper.run()["results"]
    assert len(calls) == 10 and all(r["outcome"] == "timeout" for r in results)
    assert all(calls[i][1] == calls[i + 1][1] == 1180 + 180 * (i // 2) for i in range(0, 10, 2))
    assert helper.report()["budget"] == {"consumed_seconds": 900}
    assert helper.report()["strict_completed"] == helper.report()["routing_matches"] == 0
    with pytest.raises(FileExistsError):
        helper.run()


@pytest.mark.parametrize("value", [-1, True, "0", float("nan"), float("inf")])
def test_invalid_budget_blocks_calls_without_reset(workspace, monkeypatch, value):
    path = workspace[1] / "budget.json"
    data = json.dumps({"consumed_seconds": value})
    path.write_text(data)
    calls, _ = fake_cli(monkeypatch)
    with pytest.raises(ValueError, match="budget"):
        helper.run()
    assert not calls and path.read_text() == data


@pytest.mark.parametrize("command", ["prepare", "run", "report"])
def test_fixed_cli_json_interfaces(workspace, monkeypatch, capsys, command):
    monkeypatch.setattr(helper, command, lambda *args: {"results": []})
    monkeypatch.setattr(sys, "argv", ["clarified", command] +
                        (["--repo-root", str(workspace[0])] if command == "prepare" else []))
    helper.main()
    assert json.loads(capsys.readouterr().out) == {"results": []}


def test_wrong_route_or_owner_is_unpassed_not_rescued(workspace, monkeypatch, capsys):
    def mutate(ndjson, exported):
        bad = answer()
        bad["decisions"][0]["implementation_owner"] = "expert-advisor"
        exported["messages"][0]["parts"][0]["text"] = json.dumps(bad)
        return ndjson, exported
    fake_cli(monkeypatch, mutate)
    monkeypatch.setattr(sys, "argv", ["clarified", "run"])
    with pytest.raises(SystemExit) as exc:
        helper.main()
    assert exc.value.code == 1
    assert len(json.loads(capsys.readouterr().out)["results"]) == 5
    report = helper.report()
    assert report["strict_completed"] == 5 and report["routing_matches"] == 85


@pytest.mark.parametrize("fault", ["wrong_model", "missing_model", "error", "tools", "variant", "incomplete", "old_session", "reused_session", "fences", "malformed"])
def test_failed_samples_unpassed_no_rescue_and_fresh_own_sessions(workspace, monkeypatch, fault):
    def mutate(ndjson, exported):
        info = exported["messages"][0]["info"]
        parts = exported["messages"][0]["parts"]
        if fault == "wrong_model":
            info["modelID"] = "wrong"
        elif fault == "missing_model":
            info.pop("modelID")
        elif fault == "error":
            info["error"] = {"message": "failed"}
        elif fault == "tools":
            parts.append({**parts[0], "type": "tool"})
        elif fault == "variant":
            info["variant"] = "high"
        elif fault == "incomplete":
            info["finish"] = "length"
        elif fault in {"old_session", "reused_session"}:
            sid = "ses_oldbaseline1" if fault == "old_session" else "ses_same"
            old_sid = exported["info"]["id"]
            ndjson = ndjson.replace(old_sid, sid)
            exported = json.loads(json.dumps(exported).replace(old_sid, sid))
        else:
            parts[0]["text"] = "```json\n" + parts[0]["text"] + "\n```" if fault == "fences" else '{"decisions": [}'
        return ndjson, exported
    calls, _ = fake_cli(monkeypatch, mutate)
    results = helper.run()["results"]
    assert len(results) == 5
    assert sum(r["outcome"] == "complete" for r in results) == (1 if fault == "reused_session" else 0)
    assert not any("scores" in r for r in results if r["outcome"] != "complete")
    assert len(calls) <= 10
    assert helper.report()["strict_completed"] < 5
    with pytest.raises(FileExistsError):
        helper.run()
