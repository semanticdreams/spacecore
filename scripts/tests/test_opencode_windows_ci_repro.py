import hashlib
import errno
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import opencode_capabilities as capabilities
import opencode_windows_ci_repro as windows_ci_repro


def make_space_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "space"
    repo.mkdir()
    subprocess.run(["git", "init", "--initial-branch=main"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:semanticdreams/spacecore.git"], cwd=repo, check=True)
    (repo / "AGENTS.md").write_text("# Repository Guidelines\n", encoding="utf-8")
    (repo / ".opencode").mkdir()
    (repo / ".opencode" / "opencode.json").write_text("{}\n", encoding="utf-8")
    return repo


def install_required_scripts(repo: Path) -> None:
    scripts = repo / "scripts"
    scripts.mkdir(exist_ok=True)
    for relative in windows_ci_repro.REQUIRED_SCRIPTS:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")


def install_fake_vcpkg(repo: Path) -> None:
    path = repo / "vcpkg" / "vcpkg"
    path.parent.mkdir(parents=True)
    path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def install_fake_bootstrap_script(repo: Path) -> None:
    path = repo / "vcpkg" / "bootstrap-vcpkg.sh"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def install_fake_windows_outputs(repo: Path) -> None:
    for relative in (
        "build/dist/windows/space.exe",
        "build/dist/windows/space-cli.exe",
        "build/windows/CPackConfig.cmake",
        "build/windows/space.ico",
        "scripts/windows-installer.iss",
    ):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")


def command_result(args: list[str], stdout: str = "", returncode: int = 0, stderr: str = "") -> capabilities.CommandResult:
    return capabilities.CommandResult(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def monkeypatch_required_tools_present(monkeypatch) -> None:
    monkeypatch.setattr(windows_ci_repro.shutil, "which", lambda name: f"/usr/bin/{name}")


def monkeypatch_required_tools_missing(monkeypatch, *, missing: set[str]) -> None:
    monkeypatch.setattr(windows_ci_repro.shutil, "which", lambda name: None if name in missing else f"/usr/bin/{name}")


def monkeypatch_rust_target(monkeypatch, *, installed: bool) -> None:
    target_output = f"{windows_ci_repro.WINDOWS_RUST_TARGET}\n" if installed else "x86_64-unknown-linux-gnu\n"

    def fake_run_command(args, cwd: Path, check: bool = True):
        del cwd, check
        if list(args) == ["rustup", "target", "list", "--installed"]:
            return command_result(list(args), stdout=target_output)
        return command_result(list(args))

    monkeypatch.setattr(windows_ci_repro, "run_command", fake_run_command)


def monkeypatch_linux_ubuntu_with_sudo(monkeypatch) -> None:
    monkeypatch.setattr(windows_ci_repro.sys, "platform", "linux")
    monkeypatch.setattr(windows_ci_repro, "_is_ubuntu_host", lambda: True)
    monkeypatch.setattr(windows_ci_repro.shutil, "which", lambda name: "/usr/bin/sudo" if name == "sudo" else f"/usr/bin/{name}")


def capture_run_command_calls(monkeypatch, module):
    calls: list[list[str]] = []

    def fake_run_command(args, cwd: Path, check: bool = True):
        del cwd, check
        calls.append(list(args))
        return command_result(list(args))

    monkeypatch.setattr(module, "run_command", fake_run_command)
    return calls


def monkeypatch_preflight_pass(monkeypatch, module) -> None:
    monkeypatch.setattr(module, "preflight", lambda repo_root: capabilities.success("preflight", "ok", {"missing": []}))


def test_preflight_passes_when_windows_ci_repro_prerequisites_exist(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_required_scripts(repo)
    install_fake_vcpkg(repo)
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    monkeypatch.delenv("WINE_CMD", raising=False)
    monkeypatch_required_tools_present(monkeypatch)
    monkeypatch_rust_target(monkeypatch, installed=True)

    result = windows_ci_repro.preflight(repo)

    assert result["status"] == "pass"
    assert result["action"] == "preflight"
    assert result["evidence"]["missing"] == []


def test_preflight_honors_vcpkg_root_override(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_required_scripts(repo)
    override_root = tmp_path / "custom-vcpkg"
    override_binary = override_root / "vcpkg"
    override_root.mkdir()
    override_binary.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    override_binary.chmod(0o755)
    monkeypatch.setenv("VCPKG_ROOT", str(override_root))
    monkeypatch.delenv("WINE_CMD", raising=False)
    monkeypatch_required_tools_present(monkeypatch)
    monkeypatch_rust_target(monkeypatch, installed=True)

    result = windows_ci_repro.preflight(repo)

    assert result["status"] == "pass"
    assert result["evidence"]["missing"] == []


def test_preflight_accepts_wine64_when_wine_is_unavailable(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_required_scripts(repo)
    install_fake_vcpkg(repo)
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    monkeypatch.delenv("WINE_CMD", raising=False)

    def fake_which(name: str):
        if name == "wine":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(windows_ci_repro.shutil, "which", fake_which)
    monkeypatch_rust_target(monkeypatch, installed=True)

    result = windows_ci_repro.preflight(repo)

    assert result["status"] == "pass"
    assert result["evidence"]["missing"] == []


def test_preflight_accepts_executable_wine_cmd_override(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_required_scripts(repo)
    install_fake_vcpkg(repo)
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    monkeypatch.setenv("WINE_CMD", "custom-wine")

    def fake_which(name: str):
        if name in {"wine", "wine64"}:
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(windows_ci_repro.shutil, "which", fake_which)
    monkeypatch_rust_target(monkeypatch, installed=True)

    result = windows_ci_repro.preflight(repo)

    assert result["status"] == "pass"
    assert result["evidence"]["missing"] == []


def test_preflight_rejects_invalid_wine_cmd_without_fallback(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_required_scripts(repo)
    install_fake_vcpkg(repo)
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    monkeypatch.setenv("WINE_CMD", "missing-custom-wine")

    def fake_which(name: str):
        if name == "missing-custom-wine":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(windows_ci_repro.shutil, "which", fake_which)
    monkeypatch_rust_target(monkeypatch, installed=True)

    result = windows_ci_repro.preflight(repo)

    assert result["status"] == "fail"
    assert result["evidence"]["missing"] == ["wine"]


def test_preflight_fails_with_setup_command_when_prerequisites_missing(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_required_scripts(repo)
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    monkeypatch.delenv("WINE_CMD", raising=False)
    monkeypatch_required_tools_missing(monkeypatch, missing={"wine", "wine64", "x86_64-w64-mingw32-gcc-posix"})
    monkeypatch_rust_target(monkeypatch, installed=False)

    result = windows_ci_repro.preflight(repo)

    assert result["status"] == "fail"
    assert result["evidence"]["code"] == "missing_windows_ci_repro_prerequisites"
    assert result["evidence"]["missing_by_category"]["system_tools"] == ["x86_64-w64-mingw32-gcc-posix"]
    assert result["evidence"]["missing_by_category"]["vcpkg"] == ["vcpkg/vcpkg"]
    assert result["evidence"]["missing_by_category"]["wine"] == ["wine"]
    assert result["evidence"]["missing_by_category"]["rust_targets"] == [
        f"rust-target:{windows_ci_repro.WINDOWS_RUST_TARGET}"
    ]
    assert result["evidence"]["setup_capability_command"] == "python3 scripts/opencode_windows_ci_repro.py setup-host --repo-root ."


def test_preflight_reports_local_vcpkg_bootstrap_when_only_vcpkg_missing(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_required_scripts(repo)
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    monkeypatch.delenv("WINE_CMD", raising=False)
    monkeypatch_required_tools_present(monkeypatch)
    monkeypatch_rust_target(monkeypatch, installed=True)

    result = windows_ci_repro.preflight(repo)

    assert result["status"] == "fail"
    assert result["evidence"]["code"] == "missing_local_vcpkg"
    assert result["evidence"]["missing_by_category"]["vcpkg"] == ["vcpkg/vcpkg"]
    assert (
        result["evidence"]["bootstrap_vcpkg_command"]
        == "python3 scripts/opencode_windows_ci_repro.py bootstrap-vcpkg --repo-root ."
    )
    assert "setup_capability_command" not in result["evidence"]


def test_bootstrap_vcpkg_clones_missing_repo_local_vcpkg_and_bootstraps(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    calls: list[list[str]] = []

    def fake_run_command(args, cwd: Path, check: bool = True):
        del cwd, check
        args = list(args)
        calls.append(args)
        if args[:2] == ["git", "clone"]:
            install_fake_bootstrap_script(repo)
        return command_result(args)

    monkeypatch.setattr(windows_ci_repro, "run_command", fake_run_command)

    result = windows_ci_repro.bootstrap_vcpkg(repo)

    assert result["status"] == "pass"
    assert calls == [
        [
            "git",
            "clone",
            "--branch",
            "2025.03.19",
            "https://github.com/microsoft/vcpkg",
            str(repo / "vcpkg"),
        ],
        [str(repo / "vcpkg" / "bootstrap-vcpkg.sh")],
    ]


def test_bootstrap_vcpkg_bootstraps_existing_repo_local_vcpkg_without_binary(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_fake_bootstrap_script(repo)
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    calls = capture_run_command_calls(monkeypatch, windows_ci_repro)

    result = windows_ci_repro.bootstrap_vcpkg(repo)

    assert result["status"] == "pass"
    assert calls == [[str(repo / "vcpkg" / "bootstrap-vcpkg.sh")]]


def test_bootstrap_vcpkg_does_not_accept_malformed_binary_path(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_fake_bootstrap_script(repo)
    (repo / "vcpkg" / "vcpkg").mkdir()
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    calls = capture_run_command_calls(monkeypatch, windows_ci_repro)

    result = windows_ci_repro.bootstrap_vcpkg(repo)

    assert result["status"] == "pass"
    assert calls == [[str(repo / "vcpkg" / "bootstrap-vcpkg.sh")]]


def test_bootstrap_vcpkg_does_not_accept_non_executable_binary(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_fake_bootstrap_script(repo)
    binary = repo / "vcpkg" / "vcpkg"
    binary.write_text("placeholder\n", encoding="utf-8")
    binary.chmod(0o644)
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    calls = capture_run_command_calls(monkeypatch, windows_ci_repro)

    result = windows_ci_repro.bootstrap_vcpkg(repo)

    assert result["status"] == "pass"
    assert calls == [[str(repo / "vcpkg" / "bootstrap-vcpkg.sh")]]


def test_bootstrap_vcpkg_reports_missing_bootstrap_script_with_command_evidence(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    (repo / "vcpkg").mkdir()
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    calls = capture_run_command_calls(monkeypatch, windows_ci_repro)

    result = windows_ci_repro.bootstrap_vcpkg(repo)

    assert result["status"] == "fail"
    assert result["evidence"]["code"] == "vcpkg_bootstrap_failed"
    assert result["evidence"]["failing_step"] == "bootstrap-vcpkg"
    assert result["evidence"]["args"] == [str(repo / "vcpkg" / "bootstrap-vcpkg.sh")]
    assert result["evidence"]["returncode"] != 0
    assert "stderr_tail" in result["evidence"]
    assert calls == []


def test_bootstrap_vcpkg_reports_run_command_oserror_as_command_evidence(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_fake_bootstrap_script(repo)
    monkeypatch.delenv("VCPKG_ROOT", raising=False)

    def fake_run_command(args, cwd: Path, check: bool = True):
        del cwd, check
        raise PermissionError("permission denied")

    monkeypatch.setattr(windows_ci_repro, "run_command", fake_run_command)

    result = windows_ci_repro.bootstrap_vcpkg(repo)

    assert result["status"] == "fail"
    assert result["evidence"]["code"] == "vcpkg_bootstrap_failed"
    assert result["evidence"]["args"] == [str(repo / "vcpkg" / "bootstrap-vcpkg.sh")]
    assert result["evidence"]["returncode"] != 0
    assert "permission denied" in result["evidence"]["stderr_tail"]


def test_bootstrap_vcpkg_passes_without_commands_when_binary_exists(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_fake_vcpkg(repo)
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    calls = capture_run_command_calls(monkeypatch, windows_ci_repro)

    result = windows_ci_repro.bootstrap_vcpkg(repo)

    assert result["status"] == "pass"
    assert calls == []


def test_bootstrap_vcpkg_requires_human_for_external_vcpkg_root(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    monkeypatch.setenv("VCPKG_ROOT", str(tmp_path / "external-vcpkg"))
    calls = capture_run_command_calls(monkeypatch, windows_ci_repro)

    result = windows_ci_repro.bootstrap_vcpkg(repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"]["code"] == "external_vcpkg_root_not_bootstrapped"
    assert calls == []


def test_setup_host_requires_linux_ubuntu(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_required_scripts(repo)
    monkeypatch.setattr(windows_ci_repro.sys, "platform", "darwin")

    result = windows_ci_repro.setup_host(repo)

    assert result["status"] == "human_decision_required"
    assert result["evidence"]["code"] == "unsupported_windows_ci_setup_host"


def test_setup_host_runs_existing_setup_script_on_supported_host(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_required_scripts(repo)
    monkeypatch_linux_ubuntu_with_sudo(monkeypatch)
    calls = capture_run_command_calls(monkeypatch, windows_ci_repro)

    result = windows_ci_repro.setup_host(repo)

    assert result["status"] == "pass"
    assert calls == [["scripts/setup-windows-build-host.sh"]]


def test_reproduce_runs_build_package_verify_and_wine_steps_in_order(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    result = windows_ci_repro.reproduce(repo)
    assert result["status"] == "pass"
    stages = result["evidence"]["stages"]
    assert [s["step"] for s in stages] == ["preflight", "build-windows-from-linux", "package-windows-runtime",
                                                "verify-windows-outputs", "wine-admission", "wine-fast"]
    assert [s["outcome"] for s in stages] == ["pass"] * 6
    assert (repo / "dispatch").read_text().splitlines() == ["build", "package", "admission", "fast"]
    ledger = json.loads((repo / result["evidence"]["ledger_path"]).read_text())
    assert ledger["stages"] == stages
    assert ledger["complete"] is True
    assert ledger["metadata"]["module"] == "tests.fast:main"
    assert ledger["metadata"]["deadline_seconds"] == 1800
    assert ledger["metadata"]["diagnostics"] == {"TEST_VERBOSE": "1", "SPACE_TEST_TIMINGS": "1"}


@pytest.mark.parametrize("code,outcome", [(17, "nonzero_exit"), (124, "timeout")])
def test_reproduce_reports_first_failing_step_with_bounded_output(tmp_path, monkeypatch, code, outcome):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    fixture_script(repo, "package-windows-runtime.sh", f"print('[FAIL] case deadline', file=sys.stderr)\nsys.exit({code})")
    result = windows_ci_repro.reproduce(repo)
    assert result["status"] == "fail"
    assert result["evidence"]["failing_step"] == "package-windows-runtime"
    stages = result["evidence"]["stages"]
    assert stages[1]["stdout"]["tail"] == "successful build\n"
    assert (repo / stages[1]["stdout"]["path"]).read_text() == "successful build\n"
    assert stages[-1]["outcome"] == outcome
    assert stages[-1]["returncode"] == code
    assert stages[-1]["progress"]["counts"]["fail"] == 1
    assert "case deadline" in stages[-1]["stderr"]["tail"]
    assert stages[-1]["capture_complete"] is True
    assert all(s["finished_utc"] and s["elapsed_seconds"] >= 0 for s in stages)


def test_admission_failure_stops_before_full_suite(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    fixture_script(repo, "prepare-windows-wine-runtime.sh", "print('Wine admission: probe backend=bcryptprimitives=b;advapi32,cryptbase=b deadline=60s kill-after=5s', flush=True)\nprint('Wine admission: probe exit=20', flush=True)\nsys.exit(20)")
    result = windows_ci_repro.reproduce(repo)
    assert result["status"] == "fail"
    assert result["evidence"]["failing_step"] == "wine-admission"
    assert "fast" not in (repo / "dispatch").read_text()
    assert result["evidence"]["stages"][-1]["progress"]["admission_phases"] == [
        {"backend": "builtin", "returncode": 20}]


def test_cli_invalid_repo_returns_structured_fail_json_without_traceback(tmp_path):
    not_space_repo = tmp_path / "not-space"
    not_space_repo.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_ROOT / "opencode_windows_ci_repro.py"),
            "preflight",
            "--repo-root",
            str(not_space_repo),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    result = json.loads(completed.stdout)
    assert completed.returncode == 3
    assert result["status"] == "fail"
    assert result["action"] == "preflight"
    assert set(result) == {"status", "action", "message", "evidence"}
    assert result["evidence"]["code"] in {"command_failed", "invalid_repo"}
    assert "Traceback" not in completed.stderr


def test_direct_operations_return_structured_failures_for_invalid_repo(monkeypatch, tmp_path):
    invalid_repo = tmp_path / "not-space"
    invalid_repo.mkdir()

    def reject_repo(repo_root: Path) -> Path:
        raise capabilities.CapabilityError("invalid_repo", "Repository is not trusted", {"repo_root": str(repo_root)})

    monkeypatch.setattr(windows_ci_repro, "ensure_space_repo", reject_repo)

    for action, operation in (
        ("preflight", windows_ci_repro.preflight),
        ("setup-host", windows_ci_repro.setup_host),
        ("bootstrap-vcpkg", windows_ci_repro.bootstrap_vcpkg),
        ("reproduce", windows_ci_repro.reproduce),
    ):
        result = operation(invalid_repo)

        assert result["status"] == "fail"
        assert result["action"] == action
        assert set(result) == {"status", "action", "message", "evidence"}
        assert result["evidence"]["code"] == "invalid_repo"


# These fixtures launch only Python children in a temporary fake repository.
# Never replace the fixed production argv table with a public command option.
def fixture_script(repo, name, body):
    path = repo / "scripts" / name
    path.write_text(f"#!{sys.executable}\nimport os, sys, time, pathlib, json\n" + body + "\n")
    path.chmod(0o755)


def reproduction_fixture(tmp_path, monkeypatch):
    repo = make_space_repo(tmp_path)
    install_required_scripts(repo)
    install_fake_windows_outputs(repo)
    monkeypatch_preflight_pass(monkeypatch, windows_ci_repro)
    for key in ("TEST_FILTER", "SPACE_TEST_CASE_TIMEOUT_SECONDS", "SPACE_MATRIX_TEST", "SPACE_REALTIME_TEST",
                "TEST_SUITE", "SPACE_TEST_SUITE", "TEST_MODULES", "SPACE_TEST_MODULES", "SPACE_WINE_SESSION_ID"):
        monkeypatch.delenv(key, raising=False)
    tools = repo / 'fixture-tools'
    tools.mkdir()
    for name, version in [('wine', 'wine-9.0 (fixture)'), ('wineserver', 'Wine 9.0 (fixture)')]:
        tool = tools / name
        tool.write_text(f'#!{sys.executable}\nimport sys\nif sys.argv[1:]==["--version"]: print({version!r})\n')
        tool.chmod(0o755)
    monkeypatch.setenv('WINE_CMD', str(tools / 'wine'))
    for name in ('prefix.py', 'artifacts.py'):
        shutil.copy2(SCRIPT_ROOT / 'wine' / name, repo / 'scripts/wine' / name)
    for script, label in [("build-windows-from-linux.sh", "build"), ("package-windows-runtime.sh", "package"),
                          ("prepare-windows-wine-runtime.sh", "admission"), ("test-windows-under-wine.sh", "fast")]:
        fixture_script(repo, script, f"with open('dispatch', 'a') as f: f.write('{label}\\n')\nprint('successful {label}', flush=True)")
    receipt = repo / "build/wine/windows/admission.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"version": 2,
                                  "backend": "bcryptprimitives=b;advapi32,cryptbase=b",
                                  "payload": {"space-cli.exe": "b"*64}, "package": {"space-cli.exe": "b"*64},
                                   "conditions": {"DISPLAY": "do-not-copy", "secret": "do-not-copy"}, "secret": "do-not-copy"}))
    create = windows_ci_repro._prefix.create_session
    def fixture_session(root):
        session = create(root)
        if receipt.exists():
            value = json.loads(receipt.read_text())
            value.update(ownedSession=session.binding(), tools=session.owner['tools'])
            receipt.write_text(json.dumps(value))
        return session
    monkeypatch.setattr(windows_ci_repro._prefix, 'create_session', fixture_session)
    return repo


def run_build_fixture(repo, body):
    fixture_script(repo, "build-windows-from-linux.sh", body)
    run_dir = windows_ci_repro._new_repro_run(repo)
    record = windows_ci_repro._run_repro_step(repo, run_dir, "build-windows-from-linux", ["scripts/build-windows-from-linux.sh"])
    ledger = json.loads((run_dir / "ledger.json").read_text())
    assert ledger["stages"][-1] == record
    return record, run_dir


def test_streams_drain_concurrently_after_real_16mib_caps_and_keep_last_markers(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    size = 16 * 1024 * 1024 + 2 * 1024 * 1024
    body = rf'''
import threading
def emit(fd):
    for _ in range({size} // 65536): os.write(fd, b'x' * 65536)
    os.write(fd, b'\n[LOAD] tests.final\n[RUN] final\n[PASS] final\n[TIME] tests.final 1.000ms\n')
threads = [threading.Thread(target=emit, args=(fd,)) for fd in (1, 2)]
for t in threads: t.start()
for t in threads: t.join()
'''
    record, _ = run_build_fixture(repo, body)
    suffix = b'\n[LOAD] tests.final\n[RUN] final\n[PASS] final\n[TIME] tests.final 1.000ms\n'
    assert record["outcome"] == "pass"
    for name in ("stdout", "stderr"):
        stream = record[name]
        assert stream["observed_bytes"] == size + len(suffix)
        assert stream["stored_bytes"] == 16 * 1024 * 1024
        assert (repo / stream["path"]).stat().st_size == 16 * 1024 * 1024
        assert stream["log_truncated"] is True and stream["excerpt_truncated"] is True
        assert len(stream["tail"]) <= 4000
        assert stream["oversized_lines"] == 1
        assert stream["max_pending_line_bytes"] <= 4096
    assert record["progress"]["counts"]["pass"] == 2
    assert record["progress"]["counts"]["load"] == 2
    assert record["progress"]["counts"]["run"] == 2
    assert record["progress"]["counts"]["timing"] == 2
    assert record["progress"]["latest"]["text"] == "[TIME] tests.final 1.000ms"
    assert record["progress"]["latest"]["observed_utc"]


def test_incremental_utf8_and_oversized_unterminated_line(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    record, _ = run_build_fixture(repo, "os.write(1, b'\\xe2'); time.sleep(.05); os.write(1, b'\\x82\\xac\\n'); os.write(2, b'z'*3000000 + b'\\xf0\\x9f')")
    assert record["stdout"]["tail"] == "€\n"
    assert record["stderr"]["observed_bytes"] == 3000002
    assert record["stderr"]["tail"].endswith("�")
    assert record["stderr"]["oversized_lines"] == 1
    assert record["stderr"]["max_pending_line_bytes"] <= 4096
    assert record["capture_complete"] is True


def test_eof_before_leader_exit_waits_without_poll_spin(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    start = time.monotonic()
    cpu = time.process_time()
    record, _ = run_build_fixture(repo, "os.close(1); os.close(2); time.sleep(.6); sys.exit(17)")
    assert record["returncode"] == 17
    assert time.monotonic() - start >= .6
    assert time.process_time() - cpu < .25


def test_descendant_held_pipes_have_bounded_owned_group_cleanup(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    start = time.monotonic()
    record, _ = run_build_fixture(repo, "import signal\npid=os.fork()\nif pid == 0:\n signal.signal(signal.SIGTERM, signal.SIG_IGN)\n print('[RUN] descendant', flush=True)\n time.sleep(30)\nelse:\n time.sleep(.1)")
    assert 4 <= time.monotonic() - start < 7
    assert record["returncode"] == 0
    assert record["outcome"] == "capture_error"
    assert record["capture_complete"] is False
    assert record["progress"]["latest"]["text"] == "[RUN] descendant"
    assert "pipe" in " ".join(record["capture_errors"])
    assert record["cleanup_signals"] == ["SIGTERM", "SIGKILL"]


@pytest.mark.parametrize("fault,outcome", [("launch", "launch_error"), ("interrupt", "interrupted"), ("capture", "capture_error")])
def test_partial_evidence_finalized_on_capture_lifecycle_errors(tmp_path, monkeypatch, fault, outcome):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    # Faults are injected at OS boundaries; the child/output are real.
    import _windows_repro_evidence as evidence
    if fault == "launch":
        def fail_launch(*args, **kwargs):
            raise OSError("fixture launch denied")
        monkeypatch.setattr(evidence.subprocess, "Popen", fail_launch)
    else:
        original = evidence._read_pipe
        fired = False
        def read_once(fd):
            nonlocal fired
            if fired:
                raise KeyboardInterrupt() if fault == "interrupt" else OSError("fixture read failed")
            fired = True
            return original(fd)
        monkeypatch.setattr(evidence, "_read_pipe", read_once)
    record, _ = run_build_fixture(repo, "print('[RUN] partial', flush=True)\ntime.sleep(.2)\nprint('later', flush=True)\ntime.sleep(30)")
    assert record["outcome"] == outcome
    assert record["capture_complete"] is False
    assert record["finished_utc"]
    assert record["capture_errors"]
    if fault != "launch":
        assert record["stdout"]["observed_bytes"] >= len('[RUN] partial\n')
        assert record["progress"]["counts"]["run"] == 1


def test_started_ledger_is_visible_to_child(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    record, _ = run_build_fixture(repo, "p=next(pathlib.Path('build/windows-ci-repro').glob('*/ledger.json'))\ns=json.loads(p.read_text())['stages'][-1]\nassert s['outcome']=='started' and s['started_utc'] and s['started_monotonic']\nprint('start ledger visible')")
    assert record["outcome"] == "pass"


def test_fourth_run_prunes_only_verified_owned_runs(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    first = windows_ci_repro.reproduce(repo)
    root = repo / "build/windows-ci-repro"
    foreign = root / "foreign"
    foreign.mkdir()
    (foreign / "keep").write_text("untouched")
    link = root / "linked"
    link.symlink_to(foreign, target_is_directory=True)
    quarantine = root / Path(first["evidence"]["ledger_path"]).parent.name
    (quarantine / "foreign-file").write_text("quarantine")
    runs = [windows_ci_repro.reproduce(repo) for _ in range(4)]
    assert not (repo / runs[0]["evidence"]["ledger_path"]).exists()
    assert all((repo / r["evidence"]["ledger_path"]).exists() for r in runs[1:])
    assert (quarantine / "foreign-file").read_text() == "quarantine"
    assert (foreign / "keep").read_text() == "untouched"
    assert link.is_symlink()


@pytest.mark.parametrize("component", ["build", "windows-ci-repro"])
def test_reproduction_rejects_symlinked_evidence_parent(tmp_path, monkeypatch, component):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    if component == "build":
        (repo / "build").rename(repo / "saved-build")
        (repo / "build").symlink_to(foreign, target_is_directory=True)
    else:
        (repo / "build/windows-ci-repro").symlink_to(foreign, target_is_directory=True)
    result = windows_ci_repro.reproduce(repo)
    assert result["status"] == "fail"
    assert not (repo / "dispatch").exists()
    assert list(foreign.iterdir()) == []


def test_private_logs_are_exclusive_no_follow_and_no_parent_chmod(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    (repo / "build").chmod(0o755)
    run_dir = windows_ci_repro._new_repro_run(repo)
    assert run_dir.stat().st_mode & 0o777 == 0o700
    target = tmp_path / "untouched"
    target.write_text("untouched")
    (run_dir / "build-windows-from-linux.stdout.log").symlink_to(target)
    with pytest.raises(windows_ci_repro._evidence._PersistenceError):
        windows_ci_repro._run_repro_step(repo, run_dir, "build-windows-from-linux", ["scripts/build-windows-from-linux.sh"])
    assert target.read_text() == "untouched"
    assert (repo / "build").stat().st_mode & 0o777 == 0o755
    with pytest.raises(ValueError):
        windows_ci_repro._run_repro_step(repo, run_dir, "arbitrary", ["sh", "-c", "exit 0"])


@pytest.mark.parametrize("key,value", [("TEST_FILTER", "selected"), ("SPACE_TEST_CASE_TIMEOUT_SECONDS", "0"),
                                       ("SPACE_MATRIX_TEST", "1"), ("SPACE_REALTIME_TEST", "1"),
                                       ("SPACE_TEST_SUITE", "slow"), ("TEST_MODULES", "selected")])
def test_conflicting_inherited_selection_rejected_before_dispatch(tmp_path, monkeypatch, key, value):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv(key, value)
    result = windows_ci_repro.reproduce(repo)
    assert result["status"] == "fail"
    assert result["evidence"]["failing_step"] == "preflight"
    assert not (repo / "dispatch").exists()
    assert key not in result["evidence"]["metadata"]
    assert result["evidence"]["stages"][0]["details"]["evidence"]["conflicting_keys"] == [key]


def test_encoded_total_response_budget_with_real_controls_unicode_and_all_stages(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    body = "os.write(1, ('\\x00😀' * 6000 + '\\n[PASS] final\\n').encode()); os.write(2, ('\\x01😀'*6000).encode())"
    for script in ("build-windows-from-linux.sh", "package-windows-runtime.sh", "prepare-windows-wine-runtime.sh", "test-windows-under-wine.sh"):
        fixture_script(repo, script, body)
    monkeypatch.setenv("SECRET_TOKEN", "do-not-copy")
    result = windows_ci_repro.reproduce(repo)
    assert result["status"] == "pass"
    assert len(json.dumps(result, sort_keys=True).encode()) <= 48 * 1024
    assert result["evidence"]["response_truncated"] is True
    assert len(result["evidence"]["stages"]) == 6
    assert "do-not-copy" not in json.dumps(result)
    ledger = json.loads((repo / result["evidence"]["ledger_path"]).read_text())
    assert len(ledger["stages"][1]["stdout"]["tail"]) == 4000
    for stage in result["evidence"]["stages"]:
        for name in ("stdout", "stderr"):
            stream = stage[name]
            assert not Path(stream["path"]).is_absolute()
            cleanup_bytes = sum(a[name]['stored_bytes'] for a in stage.get('cleanup', {}).get('attempts', []))
            assert (repo / stream["path"]).stat().st_size == stream["stored_bytes"] + cleanup_bytes
            assert stream["stored_bytes"] == stream["observed_bytes"]


def test_admission_metadata_read_is_allowlisted_readonly_and_preserves_receipt(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    receipt = repo / "build/wine/windows/admission.json"
    monkeypatch.setenv("WINEPREFIX", "/selected-prefix")
    monkeypatch.setenv("DISPLAY", ":private-display")
    result = windows_ci_repro.reproduce(repo)
    before = receipt.read_bytes()
    session = windows_ci_repro._prefix.load_session(repo, json.loads(before)['ownedSession']['id'])
    windows_ci_repro._admitted_metadata(repo, session)
    metadata = result["evidence"]["metadata"]
    assert metadata["wine"]["version"] == "wine-9.0 (fixture)"
    assert metadata["wine"]["sha256"] == hashlib.sha256((repo / 'fixture-tools/wine').read_bytes()).hexdigest()
    assert metadata["payload"]["space-cli.exe"] == "b"*64
    payload = json.loads(before)["payload"]
    assert metadata["payload_inventory_sha256"] == hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    assert metadata["prefix_selection"] == "generated-owned-session"
    assert metadata["effective_prefix"] == str(session.prefix)
    assert metadata["display_present"] is True
    assert metadata["effective_uid"] == os.geteuid()
    assert ":private-display" not in json.dumps(result)
    assert receipt.read_bytes() == before


def test_ready_owned_binding_matches_actual_receipt_and_readonly_parent_metadata(tmp_path):
    from test_windows_wine_runtime import Fixture
    runtime = Fixture(tmp_path)
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stderr
    receipt_file = runtime.overlay / 'admission.json'
    before = receipt_file.read_bytes()
    receipt = json.loads(before)
    session = windows_ci_repro._prefix.load_session(runtime.root, receipt['ownedSession']['id'])
    calls = runtime.calls()
    metadata = windows_ci_repro._admitted_metadata(runtime.root, session)
    assert metadata['owned_session'] == receipt['ownedSession'] == session.binding()
    assert metadata['owned_session']['crash_policy']['verified'] is True
    assert set(metadata['owned_session']['roots']) == {'data', 'cache', 'tmp'}
    assert receipt_file.read_bytes() == before and runtime.calls() == calls
    del receipt['ownedSession']['roots']
    receipt_file.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='Invalid admission metadata'):
        windows_ci_repro._admitted_metadata(runtime.root, session)
    assert runtime.calls() == calls


def test_wine_script_fixed_diagnostics_deadline_and_flushed_launch_marker(tmp_path):
    import ast
    from test_windows_wine_runtime import Fixture

    text = (SCRIPT_ROOT / "test-windows-under-wine.sh").read_text()
    assert text.splitlines()[-1] == 'exec python3 "${ROOT_DIR}/scripts/wine/artifacts.py" fast1800'
    tree = ast.parse((SCRIPT_ROOT / "wine/prefix.py").read_text())
    bounds = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "BOUNDS" for target in node.targets))
    assert bounds == {"init": 90, "probe": 60, "smoke60": 60, "fast1800": 1800,
                      "stop": 10, "wait": 15, "kill_after": 5, "setup": 30}

    runtime = Fixture(tmp_path)
    dispatcher = runtime.bin / "wine"
    dispatcher.write_text(dispatcher.read_text().replace(
        "'WINEDLLOVERRIDES','WINEPREFIX'",
        "'TEST_VERBOSE','SPACE_TEST_TIMINGS','SPACE_TEST_CASE_TIMEOUT_SECONDS','WINEDLLOVERRIDES','WINEPREFIX'"))
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    result = runtime.run("test-windows-under-wine.sh")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "[LAUNCH] Wine full fast module=tests.fast:main deadline=1800s TEST_VERBOSE=1 SPACE_TEST_TIMINGS=1"]
    app = [call for call in runtime.calls() if "wine" in call][-1]
    assert app["wine"] == [str(runtime.overlay / "space-cli.exe"), "-m", "tests.fast:main"]
    assert app["env"]["TEST_VERBOSE"] == app["env"]["SPACE_TEST_TIMINGS"] == "1"
    assert app["env"]["SPACE_TEST_CASE_TIMEOUT_SECONDS"] is None
    timeout = [call for call in runtime.calls() if "timeout" in call][-3]
    assert timeout == {"timeout": "1800s", "kill_after": "--kill-after=5s"}

    cases = SCRIPT_ROOT.parent / "assets/lua/tests"
    runner = (cases / "runner.fnl").read_text()
    assert "        parsed)\n      120))" in runner
    assert "(local timeout test.timeout-seconds)" in runner
    assert ":override 240" in (cases / "runner-regression-cases.fnl").read_text()
    assert ":timeout-seconds 240" in (cases / "test-hot-reload-integration.fnl").read_text()
    assert (cases / "test-runner.fnl").read_text().count(":timeout 120}") == 2


def test_cli_keeps_exactly_four_commands_and_no_execution_passthrough():
    for option in ("--command", "--env", "--profile", "--timeout"):
        with pytest.raises(SystemExit):
            windows_ci_repro._parse_args(["reproduce", "--repo-root", ".", option, "x"])


def test_encoded_budget_with_all_marker_kinds_and_later_failure(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    body = "\n".join(f"print('[{kind}] ' + '\\x00' * 3800 + '😀' * 40, flush=True)"
                     for kind in ("LAUNCH", "BOOT", "LOAD", "RUN", "PASS", "FAIL", "TIME"))
    for script in ("build-windows-from-linux.sh", "package-windows-runtime.sh", "prepare-windows-wine-runtime.sh", "test-windows-under-wine.sh"):
        fixture_script(repo, script, body + ("\nsys.exit(17)" if script == "test-windows-under-wine.sh" else ""))
    result = windows_ci_repro.reproduce(repo)
    assert result["status"] == "fail"
    assert result["evidence"]["failing_step"] == "wine-fast"
    assert len(json.dumps(result, sort_keys=True).encode()) <= 48 * 1024
    assert len(result["evidence"]["stages"]) == 6
    assert result["evidence"]["stages"][-1]["returncode"] == 17
    assert result["evidence"]["stages"][-1]["progress"]["counts"]["fail"] == 1
    ledger = json.loads((repo / result["evidence"]["ledger_path"]).read_text())
    assert len(ledger["stages"][-1]["progress"]["last_markers"]["fail"]["text"]) > 3800


def test_log_write_error_still_drains_and_finalizes_incomplete(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    import _windows_repro_evidence as evidence
    real_exclusive = evidence._exclusive
    class BrokenLog:
        def __init__(self, wrapped):
            self.wrapped = wrapped
        def write(self, data):
            raise OSError("fixture disk full")
        def close(self):
            self.wrapped.close()
    def exclusive(path):
        wrapped = real_exclusive(path)
        return BrokenLog(wrapped) if path.name.endswith(".stdout.log") else wrapped
    monkeypatch.setattr(evidence, "_exclusive", exclusive)
    record, _ = run_build_fixture(repo, "os.write(1, b'x'*3000000 + b'\\n[PASS] after-write-error\\n'); os.write(2, b'y'*3000000)")
    assert record["stdout"]["observed_bytes"] == 3000026
    assert record["stderr"]["observed_bytes"] == 3000000
    assert record["stdout"]["stored_bytes"] == 0
    assert record["outcome"] == "capture_error" and record["capture_complete"] is False
    assert record["progress"]["last_markers"]["pass"]["text"] == "[PASS] after-write-error"
    assert record["stdout"]["errors"] == record["capture_errors"]


def test_real_gnu_timeout_124_is_failure_with_retained_progress(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    fixture_script(repo, "package-windows-runtime.sh", "print('[RUN] active at timeout', flush=True)\nos.execvp('timeout', ['timeout', '.15s', sys.executable, '-c', 'import time; time.sleep(30)'])")
    result = windows_ci_repro.reproduce(repo)
    stage = result["evidence"]["stages"][-1]
    assert result["status"] == "fail"
    assert stage["returncode"] == 124 and stage["outcome"] == "timeout"
    assert stage["progress"]["last_markers"]["run"]["text"] == "[RUN] active at timeout"


def test_shell_diagnostics_do_not_change_admission_conditions_and_reject_filter(tmp_path):
    from test_windows_wine_runtime import Fixture
    runtime = Fixture(tmp_path)
    dispatcher = runtime.bin / "wine"
    dispatcher.write_text(dispatcher.read_text().replace("'WINEDLLOVERRIDES','WINEPREFIX'", "'TEST_VERBOSE','SPACE_TEST_TIMINGS','WINEDLLOVERRIDES','WINEPREFIX'"))
    runtime.package()
    assert runtime.prepare([10, 0]).returncode == 0
    receipt = runtime.overlay / "admission.json"
    before = receipt.read_bytes()
    assert runtime.run("test-windows-under-wine.sh").returncode == 0
    app = [c for c in runtime.calls() if "wine" in c][-1]
    assert app["env"]["TEST_VERBOSE"] == "1" and app["env"]["SPACE_TEST_TIMINGS"] == "1"
    assert receipt.read_bytes() == before
    assert runtime.prepare([0]).returncode == 0
    identifier = json.loads(receipt.read_text())["ownedSession"]["id"]
    assert identifier != json.loads(before)["ownedSession"]["id"]
    state_file = runtime.root / "build/wine/sessions" / identifier / "state.json"
    state = json.loads(state_file.read_text())
    assert state["authorized"] and not state["ended"]
    assert state["stopped_generation"] == state["generation"]
    runtime.env["TEST_FILTER"] = "unknown-selection"
    count = len(runtime.calls())
    result = runtime.run("test-windows-under-wine.sh")
    assert result.returncode != 0
    assert "Conflicting inherited full-fast setting: TEST_FILTER" in result.stderr
    assert len(runtime.calls()) == count
    state = json.loads(state_file.read_text())
    assert state["ended"] and not state["authorized"]


def test_admission_builtin_compat_phases_stay_separate_from_full_tests(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    fixture_script(repo, "prepare-windows-wine-runtime.sh", "print('Wine admission: probe backend=bcryptprimitives=b;advapi32,cryptbase=b deadline=60s kill-after=5s', flush=True)\nprint('Wine admission: probe exit=10', flush=True)\nprint('Wine admission: probe backend=bcryptprimitives=n;advapi32,cryptbase=b deadline=60s kill-after=5s', flush=True)\nprint('Wine admission: probe exit=0', flush=True)")
    result = windows_ci_repro.reproduce(repo)
    assert result["status"] == "pass"
    assert result["evidence"]["stages"][-2]["progress"]["admission_phases"] == [
        {"backend": "builtin", "returncode": 10}, {"backend": "compat", "returncode": 0}]
    assert result["evidence"]["stages"][-1]["progress"]["admission_phases"] == []


@pytest.mark.parametrize("damage", ["malformed-marker", "changed-log", "linked-log", "identity"])
def test_pruning_preserves_damaged_owned_evidence(tmp_path, monkeypatch, damage):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    first = windows_ci_repro.reproduce(repo)
    run_dir = (repo / first["evidence"]["ledger_path"]).parent
    marker = run_dir / ".space-windows-repro-v1.json"
    if damage == "malformed-marker":
        marker.write_text("[]")
    elif damage == "identity":
        data = json.loads(marker.read_text())
        data["ownership"]["identity"]["build"][1] += 1
        marker.write_text(json.dumps(data))
    else:
        log = run_dir / "build-windows-from-linux.stdout.log"
        if damage == "changed-log":
            log.write_text("quarantined modified log")
        else:
            target = tmp_path / "unrelated"
            target.write_text("unrelated")
            log.unlink()
            log.symlink_to(target)
    before = marker.read_bytes()
    for _ in range(4):
        result = windows_ci_repro.reproduce(repo)
        assert result["status"] == "pass", result
    assert marker.read_bytes() == before
    assert run_dir.is_dir()


def test_budget_retains_failure_context_with_extreme_metadata(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    for name, label in [('wine', 'wine-'), ('wineserver', 'Wine ')]:
        path = repo / 'fixture-tools' / name
        # Admit a real core token while maximizing legitimate escaped metadata:
        # 1020 non-BMP annotation characters expand to 12240 JSON ASCII bytes.
        # Keep control noise on its own non-identity line; use all 4096 stream bytes.
        output = ('\x01\x02\x03\n' + label + '9.0 (' + '😀' * 1020 + ')\n').encode('utf-8')
        assert len(output) == 4096
        path.write_text(f'#!{sys.executable}\nimport sys\nif sys.argv[1:]==["--version"]: sys.stdout.buffer.write({output!r})\n')
    monkeypatch.setenv("WINEPREFIX", "/" + "😀" * 4000)
    body = "\n".join(f"print('[{kind}] ' + '\\x01' * 3800 + '😀' * 40, flush=True)"
                     for kind in ("LAUNCH", "BOOT", "LOAD", "RUN", "PASS", "TIME"))
    for script in ("build-windows-from-linux.sh", "package-windows-runtime.sh", "prepare-windows-wine-runtime.sh"):
        fixture_script(repo, script, body)
    fixture_script(repo, "test-windows-under-wine.sh", body + "\nprint('[FAIL] important failure context: broken call', file=sys.stderr, flush=True)\nsys.exit(17)")
    result = windows_ci_repro.reproduce(repo)
    assert len(json.dumps(result, sort_keys=True).encode()) <= 48 * 1024
    assert len(result["evidence"]["stages"]) == 6
    failure = result["evidence"]["stages"][-1]
    assert "important failure context: broken call" in failure["stderr"]["tail"]
    assert failure["returncode"] == 17
    assert result["evidence"]["response_truncated"] is True


@pytest.mark.parametrize('reject_wine', [False, True])
@pytest.mark.parametrize('server_output,server_code,reason', [
    (b'Wine not-a-release\n', 0, 'Unsupported Wine release identity'),
    (b'Wine 9.0\n', 23, 'Wine tool version failed: exit=23'),
    (b'\xff', 0, 'Invalid UTF-8 Wine tool version'),
], ids=['unsupported', 'nonzero', 'invalid-utf8'])
def test_identity_rejection_survives_wrapper_error_cap_with_long_paths_and_peer_warnings(
        tmp_path, monkeypatch, reject_wine, server_output, server_code, reason):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    logical = repo / 'selected-tools' / ('s' * 180) / ('t' * 180) / ('u' * 180)
    canonical = repo / 'tool-backends' / ('c' * 170) / ('d' * 170) / ('e' * 170)
    logical.mkdir(parents=True)
    canonical.mkdir(parents=True)
    calls_path = repo / 'identity-calls.jsonl'

    def write_tool(path, stdout, stderr, code):
        path.write_text(f'''#!{sys.executable}
import json, os, sys
with open({str(calls_path)!r}, 'a') as stream:
    stream.write(json.dumps({{'tool': sys.argv[0], 'args': sys.argv[1:]}})+'\\n')
if sys.argv[1:] != ['--version']: sys.exit(91)
os.write(1, {stdout!r})
os.write(2, {stderr!r})
sys.exit({code})
''')
        path.chmod(0o755)

    wine, server = canonical / 'wine64', canonical / 'wineserver64'
    warning = b'warning: \x1b[31m' + b'x' * 2000 + b'\n'
    raw_wine = b'wine-9.0 (Ubuntu 9.0~repack-4build3)\n'
    write_tool(wine, b'wine-unsupported\n' if reject_wine else raw_wine, warning, 0)
    write_tool(server, b'', server_output, server_code)
    wine_lookup, server_lookup = logical / 'wine-stable', logical / 'wineserver-stable'
    wine_lookup.symlink_to(wine)
    server_lookup.symlink_to(server)
    assert len(str(wine_lookup)) > 500
    monkeypatch.setenv('WINE_CMD', str(wine_lookup))
    # Observe, never replace, the production create_session and its real reads of
    # our fake executables. Preserve the complete exception for detailed-fact checks.
    create = windows_ci_repro._prefix.create_session
    full_errors = []
    def observe_create(root):
        try:
            return create(root)
        except ValueError as error:
            full_errors.append(str(error))
            raise
    monkeypatch.setattr(windows_ci_repro._prefix, 'create_session', observe_create)

    result = windows_ci_repro.reproduce(repo)
    assert result['status'] == 'fail'
    assert len(json.dumps(result, sort_keys=True).encode()) <= 48 * 1024
    evidence = result['evidence']
    ledger = json.loads((repo / evidence['ledger_path']).read_text())
    assert evidence['errors'] == ledger['errors']
    assert len(evidence['errors']) == 1 and len(evidence['errors'][0]) <= len('ValueError: ') + 500
    assert 'server:' in evidence['errors'][0] and reason in evidence['errors'][0]
    if reject_wine:
        assert 'wine: Unsupported Wine release identity' in evidence['errors'][0]
    assert evidence['failing_step'] == 'wine-admission' and ledger['outcome'] == 'fail'
    assert not evidence['complete'] and not ledger['complete']
    assert evidence['sealed']
    expected_steps = ['preflight', 'build-windows-from-linux', 'package-windows-runtime', 'verify-windows-outputs']
    assert [stage['step'] for stage in evidence['stages']] == expected_steps
    assert [stage['step'] for stage in ledger['stages']] == expected_steps
    for stage in evidence['stages']:
        assert stage['outcome'] == 'pass' and stage['capture_complete']
    for returned, stage in zip(evidence['stages'][1:3], ledger['stages'][1:3]):
        for stream in ['stdout', 'stderr']:
            log = Path(stage[stream]['path'])
            assert returned[stream]['path'] == stage[stream]['path']
            assert not log.is_absolute() and (repo / log).is_file()
        assert 'successful' in (repo / stage['stdout']['path']).read_text()
    assert (repo / 'dispatch').read_text().splitlines() == ['build', 'package']
    assert [json.loads(line) for line in calls_path.read_text().splitlines()] == [
        {'tool': str(wine), 'args': ['--version']},
        {'tool': str(server), 'args': ['--version']}]
    assert len(full_errors) == 1
    assert f'wine lookup={wine_lookup} canonical={wine}' in full_errors[0]
    assert f'wineserver lookup={server_lookup} canonical={server}' in full_errors[0]
    assert 'stdout' in full_errors[0] and 'stderr' in full_errors[0]
    assert '\x1b' not in full_errors[0] and '\x00' not in full_errors[0]
    if not reject_wine:
        assert raw_wine.decode().strip() in full_errors[0] and 'warning:' in full_errors[0]


def test_missing_home_does_not_guess_default_prefix_identity(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    monkeypatch.delenv("WINEPREFIX", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    fixture_script(repo, "prepare-windows-wine-runtime.sh", "print('HOME is required', file=sys.stderr); sys.exit(1)")
    result = windows_ci_repro.reproduce(repo)
    assert result["evidence"]["metadata"]["effective_prefix"].startswith(str(repo / 'build/wine/sessions'))
    assert result["status"] == "fail"


def test_missing_admission_metadata_is_not_complete_pass_or_full_launch(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    (repo / "build/wine/windows/admission.json").unlink()
    result = windows_ci_repro.reproduce(repo)
    assert result["status"] == "fail"
    assert result["evidence"]["complete"] is False
    assert result["evidence"]["failing_step"] == "wine-admission"
    assert result["evidence"]["stages"][-1]["outcome"] == "evidence_error"
    assert result["evidence"]["stages"][-1]["returncode"] == 0
    assert "fast" not in (repo / "dispatch").read_text()


def test_long_repo_root_uses_relative_log_paths_and_encoded_response_stays_bounded(tmp_path, monkeypatch):
    parent = tmp_path
    for _ in range(16):
        parent = parent / ("r" * 200)
    parent.mkdir(parents=True)
    repo = reproduction_fixture(parent, monkeypatch)
    assert len(str(repo)) > 3200
    result = windows_ci_repro.reproduce(repo)
    assert result["status"] == "pass"
    assert len(json.dumps(result, sort_keys=True).encode()) <= 48 * 1024
    assert all(s["stdout"]["path"].startswith("build/windows-ci-repro/") for s in result["evidence"]["stages"])


def test_prefix_metadata_uses_same_working_directory_as_admission(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv("WINEPREFIX", "selected-prefix")
    result = windows_ci_repro.reproduce(repo)
    metadata = result['evidence']['metadata']
    receipt = json.loads((repo / 'build/wine/windows/admission.json').read_text())
    assert metadata['effective_prefix'] == receipt['ownedSession']['prefix']
    assert metadata['effective_prefix'] != str(repo / 'selected-prefix')


def install_atomic_writer(monkeypatch, target, write):
    import _windows_repro_evidence as evidence
    original = evidence._exclusive
    class Writer:
        def __init__(self, output):
            self.output = output
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.output.close()
        def fileno(self):
            return self.output.fileno()
        def write(self, data):
            return write(self.output, data)
    def exclusive(path):
        output = original(path)
        return Writer(output) if path.parent == target.parent and path.name.startswith(f".{target.name}.") else output
    monkeypatch.setattr(evidence, "_exclusive", exclusive)


@pytest.mark.parametrize("name", ["ledger.json", ".space-windows-repro-v1.json"])
def test_atomic_partial_then_enospc_preserves_previous_checkpoint(tmp_path, monkeypatch, name):
    import _windows_repro_evidence as evidence
    repo = reproduction_fixture(tmp_path, monkeypatch)
    run_dir = windows_ci_repro._new_repro_run(repo)
    target = run_dir / name
    before = target.read_bytes()
    calls = []
    def partial_then_fail(output, data):
        calls.append(len(data))
        if len(calls) == 1:
            return output.write(data[:7])
        raise OSError(errno.ENOSPC, "fixture atomic disk full")
    install_atomic_writer(monkeypatch, target, partial_then_fail)
    with pytest.raises(OSError, match="fixture atomic disk full"):
        evidence._atomic(target, {"replacement": "must never replace a valid checkpoint"})
    assert len(calls) == 2
    assert target.read_bytes() == before
    assert json.loads(target.read_bytes())
    assert not list(run_dir.glob(f".{target.name}.*.tmp"))


@pytest.mark.parametrize("progress", [0, -1, None, False, True, 1.5, "1", 1000000])
def test_atomic_rejects_invalid_write_progress_without_replacing(tmp_path, monkeypatch, progress):
    import _windows_repro_evidence as evidence
    repo = reproduction_fixture(tmp_path, monkeypatch)
    run_dir = windows_ci_repro._new_repro_run(repo)
    target = run_dir / "ledger.json"
    before = target.read_bytes()
    install_atomic_writer(monkeypatch, target, lambda output, data: progress)
    with pytest.raises(OSError, match="write progress"):
        evidence._atomic(target, {"replacement": "incomplete"})
    assert target.read_bytes() == before


def test_atomic_completes_short_writes_before_fsync_and_replace(tmp_path, monkeypatch):
    import _windows_repro_evidence as evidence
    repo = reproduction_fixture(tmp_path, monkeypatch)
    run_dir = windows_ci_repro._new_repro_run(repo)
    target = run_dir / "ledger.json"
    value = {"replacement": "complete 😀 checkpoint" * 20}
    expected = (json.dumps(value, sort_keys=True) + "\n").encode()
    written = 0
    def short_write(output, data):
        nonlocal written
        count = output.write(data[:7])
        written += count
        return count
    install_atomic_writer(monkeypatch, target, short_write)
    original_fsync = evidence.os.fsync
    def fsync(fd):
        assert written == len(expected)
        original_fsync(fd)
    monkeypatch.setattr(evidence.os, "fsync", fsync)
    evidence._atomic(target, value)
    assert target.read_bytes() == expected


def test_persistent_checkpoint_enospc_keeps_memory_progress_history_and_pointers(tmp_path, monkeypatch):
    import _windows_repro_evidence as evidence
    repo = reproduction_fixture(tmp_path, monkeypatch)
    suffix = "\n[RUN] checkpoint failure\n[PASS] after checkpoint failure\n"
    fixture_script(repo, "package-windows-runtime.sh", "os.write(1, b'x'*3000000 + b'\\n[RUN] checkpoint failure\\n')\ntime.sleep(.4)\nprint('[PASS] after checkpoint failure', flush=True)\nsys.exit(17)")
    original = evidence._atomic
    failed_calls = []
    before = {}
    def disk_full(path, value):
        stages = value.get("stages", [])
        trigger = (path.name == "ledger.json" and stages and stages[-1]["step"] == "package-windows-runtime"
                   and stages[-1]["outcome"] == "started" and stages[-1]["progress"]["counts"]["run"])
        if before or trigger:
            if not before:
                before["ledger"] = path.read_bytes()
                before["marker"] = (path.parent / evidence._MARKER).read_bytes()
            failed_calls.append(path.name)
            raise OSError(errno.ENOSPC, "fixture persistent checkpoint disk full")
        return original(path, value)
    monkeypatch.setattr(evidence, "_atomic", disk_full)
    result = windows_ci_repro.reproduce(repo)
    data = result["evidence"]
    assert result["status"] == "fail" and data["complete"] is False
    assert data["failing_step"] == "package-windows-runtime"
    assert [s["step"] for s in data["stages"]] == ["preflight", "build-windows-from-linux", "package-windows-runtime"]
    assert data["stages"][1]["stdout"]["tail"] == "successful build\n"
    stage = data["stages"][-1]
    assert stage["returncode"] == 17 and stage["outcome"] == "nonzero_exit"
    assert stage["capture_complete"] is False
    assert stage["stdout"]["observed_bytes"] == 3000000 + len(suffix)
    assert stage["progress"]["counts"]["run"] == stage["progress"]["counts"]["pass"] == 1
    assert stage["progress"]["latest"]["text"] == "[PASS] after checkpoint failure"
    assert "persistent checkpoint disk full" in " ".join(data["persistence_errors"])
    assert len(failed_calls) == 1  # No recursive final-save/seal retries on broken storage.
    assert data["sealed"] is False
    ledger_path = repo / data["ledger_path"]
    assert ledger_path.read_bytes() == before["ledger"]
    assert (ledger_path.parent / evidence._MARKER).read_bytes() == before["marker"]
    assert json.loads(ledger_path.read_bytes())["stages"][-1]["outcome"] == "started"
    assert all((repo / s[stream]["path"]).is_file() for s in data["stages"] for stream in ("stdout", "stderr"))
    assert len(json.dumps(result, sort_keys=True).encode()) <= 48 * 1024


@pytest.mark.parametrize("fault", ["final-save", "seal"])
@pytest.mark.parametrize("code", [0, 17, 124])
def test_finalization_storage_failure_keeps_actual_status_and_complete_history(tmp_path, monkeypatch, fault, code):
    import _windows_repro_evidence as evidence
    repo = reproduction_fixture(tmp_path, monkeypatch)
    fixture_script(repo, "test-windows-under-wine.sh", f"print('[RUN] finalized fixture', flush=True)\nsys.exit({code})")
    original = evidence._atomic
    failed_calls = []
    before = {}
    def disk_full(path, value):
        trigger = ((fault == "final-save" and path.name == "ledger.json" and value.get("finished_utc"))
                   or (fault == "seal" and path.name == evidence._MARKER and value.get("state") == "finalized"))
        if before or trigger:
            if not before:
                before["ledger"] = (path.parent / "ledger.json").read_bytes()
                before["marker"] = (path.parent / evidence._MARKER).read_bytes()
            failed_calls.append(path.name)
            raise OSError(errno.ENOSPC, f"fixture persistent {fault} disk full")
        return original(path, value)
    monkeypatch.setattr(evidence, "_atomic", disk_full)
    result = windows_ci_repro.reproduce(repo)
    data = result["evidence"]
    assert result["status"] == "fail" and data["complete"] is False
    assert len(data["stages"]) == 6
    assert data["stages"][1]["stdout"]["tail"] == "successful build\n"
    stage = data["stages"][-1]
    assert stage["returncode"] == code
    assert stage["outcome"] == {0: "pass", 17: "nonzero_exit", 124: "timeout"}[code]
    assert stage["progress"]["latest"]["text"] == "[RUN] finalized fixture"
    assert all(s["finished_utc"] for s in data["stages"])
    assert data["sealed"] is False
    assert fault in " ".join(data["persistence_errors"])
    assert len(failed_calls) == 1
    ledger_path = repo / data["ledger_path"]
    assert ledger_path.read_bytes() == before["ledger"]
    assert (ledger_path.parent / evidence._MARKER).read_bytes() == before["marker"]
    assert json.loads(ledger_path.read_bytes())
    assert all((repo / s[stream]["path"]).is_file() for s in data["stages"] for stream in ("stdout", "stderr"))
    assert len(json.dumps(result, sort_keys=True).encode()) <= 48 * 1024


def test_eof_checkpoint_is_visible_during_live_child_shutdown_without_spin(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    cpu = time.process_time()
    record, _ = run_build_fixture(repo, "print('[RUN] shutting down', flush=True)\nos.close(1); os.close(2)\ntime.sleep(.3)\np=next(pathlib.Path('build/windows-ci-repro').glob('*/ledger.json'))\ns=json.loads(p.read_text())['stages'][-1]\npathlib.Path('shutdown-checkpoint.json').write_text(json.dumps({'stage':s,'pid':os.getpid()}))\ntime.sleep(.4)")
    snapshot = json.loads((repo / "shutdown-checkpoint.json").read_text())
    assert snapshot["stage"]["outcome"] == "started"
    assert snapshot["stage"]["progress"]["latest"]["text"] == "[RUN] shutting down"
    assert snapshot["stage"]["stdout"]["eof"] is True and snapshot["stage"]["stderr"]["eof"] is True
    assert record["returncode"] == 0 and record["elapsed_seconds"] >= .7
    assert time.process_time() - cpu < .25


@pytest.mark.parametrize("step", ["wine-fast", "build-windows-from-linux"])
def test_zero_exit_runner_failure_is_rejected_only_for_wine_fast(tmp_path, monkeypatch, step):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    script = "test-windows-under-wine.sh" if step == "wine-fast" else "build-windows-from-linux.sh"
    fixture_script(repo, script, "print('[FAIL] failed runner case', file=sys.stderr, flush=True)")
    result = windows_ci_repro.reproduce(repo)
    stage = next(s for s in result["evidence"]["stages"] if s["step"] == step)
    assert stage["returncode"] == 0
    assert stage["capture_complete"] is True
    assert stage["progress"]["last_markers"]["fail"]["stream"] == "stderr"
    if step == "wine-fast":
        assert result["status"] == "fail" and result["evidence"]["complete"] is False
        assert result["evidence"]["failing_step"] == "wine-fast"
        assert stage["outcome"] == "inconsistent_result"
    else:
        assert result["status"] == "pass" and stage["outcome"] == "pass"


def test_clock_rollback_retention_always_protects_current_run(tmp_path, monkeypatch):
    import _windows_repro_evidence as evidence
    from datetime import datetime, timezone
    repo = reproduction_fixture(tmp_path, monkeypatch)
    old = [windows_ci_repro.reproduce(repo) for _ in range(3)]
    class RolledBack(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2000, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(evidence, "datetime", RolledBack)
    current = windows_ci_repro.reproduce(repo)
    data = current["evidence"]
    assert current["status"] == "pass"
    assert Path(data["ledger_path"]).parent.name.startswith("20000101T")
    assert (repo / data["ledger_path"]).is_file()
    assert all((repo / s[stream]["path"]).is_file() for s in data["stages"] for stream in ("stdout", "stderr"))
    assert not (repo / old[0]["evidence"]["ledger_path"]).exists()
    assert all((repo / result["evidence"]["ledger_path"]).exists() for result in old[1:])
    assert len(list((repo / "build/windows-ci-repro").iterdir())) == 3


def owned_reproduction_fixture(tmp_path, monkeypatch):
    """Real artifact/prefix code with host dispatchers; no PE is executed."""
    from test_windows_wine_runtime import Fixture
    runtime = Fixture(tmp_path)
    monkeypatch.setattr(windows_ci_repro, "ensure_space_repo", lambda path: runtime.root)
    monkeypatch_preflight_pass(monkeypatch, windows_ci_repro)
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("SPACE_WINE_SESSION_ID", raising=False)
    for key in ("TEST_FILTER", "SPACE_TEST_CASE_TIMEOUT_SECONDS", "TEST_SUITE", "SPACE_TEST_SUITE",
                "TEST_MODULES", "SPACE_TEST_MODULES", "SPACE_MATRIX_TEST", "SPACE_REALTIME_TEST"):
        monkeypatch.delenv(key, raising=False)
    install_fake_windows_outputs(runtime.root)
    fixture_script(runtime.root, "build-windows-from-linux.sh", "print('successful build', flush=True)")
    runtime.codes.write_text('[0]')
    return runtime


@pytest.mark.parametrize("fault,code", [("success", 0), ("init", 42), ("admission", 20),
                                         ("app", 124), ("app", 137)])
def test_parent_owns_session_before_init_and_terminally_cleans_without_receipt(tmp_path, monkeypatch, fault, code):
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    if fault == "admission":
        runtime.codes.write_text('[20]')
    elif fault in ("init", "app"):
        monkeypatch.setenv("FIXTURE_" + fault.upper() + "_CODE", str(code))
    result = windows_ci_repro.reproduce(runtime.root)
    data = result['evidence']
    assert result['status'] == ('pass' if fault == 'success' else 'fail'), result
    metadata = data['metadata']
    assert metadata['prefix_selection'] == 'generated-owned-session'
    session_id = metadata['owned_session']['id']
    state = json.loads((runtime.root / 'build/wine/sessions' / session_id / 'state.json').read_text())
    assert state['ended'] and not state['authorized']
    assert state['stopped_generation'] == state['generation']
    assert data['stages'][-1]['cleanup']['outcome'] == 'pass'
    calls = runtime.calls()
    assert all(c['env']['WINEPREFIX'] == metadata['effective_prefix'] for c in calls if 'wine' in c or 'server' in c)
    assert [c['server'] for c in calls if 'server' in c] == ([['-k'], ['-w']] if fault in ('init', 'admission')
                                                          else [['-k'], ['-w'], ['-k'], ['-w']])
    if fault == 'app':
        assert data['stages'][-1]['returncode'] == code
    if fault in ('init', 'admission'):
        assert not (runtime.overlay / 'admission.json').exists()


def test_inherited_private_session_handoff_rejected_before_any_execution(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv('SPACE_WINE_SESSION_ID', 'a' * 32)
    result = windows_ci_repro.reproduce(repo)
    assert result['status'] == 'fail'
    assert result['evidence']['failing_step'] == 'preflight'
    assert not (repo / 'dispatch').exists()
    assert 'SPACE_WINE_SESSION_ID' in result['evidence']['stages'][0]['details']['evidence']['conflicting_keys']


def test_wine_outer_vectors_are_exact_and_not_a_timeout_passthrough():
    assert dict(windows_ci_repro._REPRO_STEPS)['wine-admission'] == (
        'timeout', '--kill-after=5s', '480s', 'scripts/prepare-windows-wine-runtime.sh')
    assert dict(windows_ci_repro._REPRO_STEPS)['wine-fast'] == (
        'timeout', '--kill-after=5s', '1920s', 'scripts/test-windows-under-wine.sh')


@pytest.mark.parametrize('code', [0, 17, 124, 137])
def test_cleanup_retry_is_finite_and_preserves_primary_stage_status(tmp_path, monkeypatch, code):
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv('FIXTURE_APP_CODE', str(code))
    wine = runtime.bin / 'wine'
    wine.write_text(wine.read_text().replace(
        "sys.exit(int(os.environ.get('FIXTURE_INIT_CODE'",
        "if sys.argv[1].endswith('space-cli.exe'): pathlib.Path(os.environ['WINEPREFIX']).parent.joinpath('app-ran').touch()\n"
        "sys.exit(int(os.environ.get('FIXTURE_INIT_CODE'"))
    server = runtime.bin / 'wineserver'
    server.write_text(server.read_text().replace('import json, os, sys', 'import json, os, sys, pathlib').replace(
        "sys.exit(int(os.environ.get('FIXTURE_STOP_CODE'",
        "if sys.argv[1:] == ['-k'] and pathlib.Path(os.environ['WINEPREFIX']).parent.joinpath('app-ran').exists(): sys.exit(37)\n"
        "sys.exit(int(os.environ.get('FIXTURE_STOP_CODE'"))
    result = windows_ci_repro.reproduce(runtime.root)
    assert result['status'] == 'fail'
    stage = result['evidence']['stages'][-1]
    assert stage['step'] == 'wine-fast'
    assert stage['returncode'] == (code or 1)
    assert stage['outcome'] == ('timeout' if code == 124 else 'nonzero_exit')
    cleanup = stage['cleanup']
    assert cleanup['outcome'] == 'fail' and len(cleanup['attempts']) == 1
    attempt = cleanup['attempts'][0]
    assert attempt['server_result']['stop_returncode'] == 37
    assert attempt['server_result']['wait_returncode'] == 0
    assert attempt['started_utc'] and attempt['finished_utc']
    assert [c['server'] for c in runtime.calls() if 'server' in c] == [['-k'], ['-w']] * 3
    assert cleanup['after']['state']['stopped_generation'] is None


@pytest.mark.parametrize('fault', ['checkpoint', 'log-open', 'interrupt', 'mutable-state', 'owner-substitution'])
def test_parent_backstop_survives_failed_capture_and_uses_immutable_owner(tmp_path, monkeypatch, fault):
    import _windows_repro_evidence as evidence
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    original = windows_ci_repro._run_repro_step
    def run(repo, run_dir, step, args, session=None):
        if step == 'wine-admission':
            assert session is not None
            state = session.state()
            state.update(generation=1, stopped_generation=None, authorized=True)
            session.save(state)
            if fault == 'checkpoint':
                atomic = evidence._atomic
                def disk_full(path, value):
                    if path.name == 'ledger.json':
                        raise OSError(errno.ENOSPC, 'fixture post-acquisition storage failure')
                    return atomic(path, value)
                monkeypatch.setattr(evidence, '_atomic', disk_full)
            elif fault == 'log-open':
                exclusive = evidence._exclusive
                def denied(path):
                    if path.suffix == '.log' and path.name.startswith('wine-admission'):
                        raise OSError('fixture log unavailable')
                    return exclusive(path)
                monkeypatch.setattr(evidence, '_exclusive', denied)
            elif fault == 'mutable-state':
                (session.directory / 'state.json').write_text('corrupt initial state')
                raise ValueError('fixture state corruption before init')
            elif fault == 'owner-substitution':
                session.prefix.rename(session.prefix.with_name('preserved'))
                session.prefix.symlink_to(session.prefix.with_name('preserved'), target_is_directory=True)
                raise ValueError('fixture prefix substitution')
            else:
                raise KeyboardInterrupt()
        return original(repo, run_dir, step, args, session)
    monkeypatch.setattr(windows_ci_repro, '_run_repro_step', run)
    result = windows_ci_repro.reproduce(runtime.root)
    assert result['status'] == 'fail', result
    data = result['evidence']
    assert data['complete'] is False
    assert len(data['stages']) == 5
    assert all(s['outcome'] == 'pass' for s in data['stages'][:4])
    cleanup = data['stages'][-1]['cleanup']
    assert len(cleanup['attempts']) == 1
    servers = [c['server'] for c in runtime.calls() if 'server' in c]
    assert servers == ([] if fault == 'owner-substitution' else [['-k'], ['-w']])
    if fault in ('mutable-state', 'owner-substitution'):
        assert cleanup['outcome'] == 'fail'
        assert cleanup['after']['errors']
    else:
        assert cleanup['outcome'] == 'pass'
        assert cleanup['after']['state']['ended']
    if fault in ('log-open', 'checkpoint'):
        assert data['sealed'] is False
    assert len(json.dumps(result).encode()) <= 48 * 1024


@pytest.mark.parametrize('damage', ['missing', 'malformed'])
@pytest.mark.parametrize('handoff', ['wine-admission', 'wine-fast'])
def test_parent_terminal_backstop_ignores_damaged_setup_but_normal_handoffs_refuse(
        tmp_path, monkeypatch, damage, handoff):
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    server = runtime.bin / 'wineserver'
    server.write_text(server.read_text().replace(
        "['WINEPREFIX','WINEARCH','WINESERVER']",
        "['WINEPREFIX','WINEARCH','WINESERVER','XDG_DATA_HOME','XDG_CACHE_HOME','TMPDIR','TEMP','TMP']"))
    original = windows_ci_repro._run_repro_step
    observed = {}
    def damage_before_handoff(repo, run_dir, step, args, session=None):
        if step == handoff:
            assert session is not None
            state = session.state()
            state.update(generation=state['generation'] + 1, stopped_generation=None, authorized=True)
            session.save(state)
            setup_file = session.directory / 'setup.json'
            if damage == 'missing':
                setup_file.unlink()
            else:
                setup_file.write_text('malformed setup observations')
            observed.update(session=session, calls=len(runtime.calls()))
        return original(repo, run_dir, step, args, session)
    monkeypatch.setattr(windows_ci_repro, '_run_repro_step', damage_before_handoff)

    result = windows_ci_repro.reproduce(runtime.root)
    assert result['status'] == 'fail'
    data = result['evidence']
    assert data['failing_step'] == handoff and not data['complete']
    assert len(json.dumps(result).encode()) <= 48 * 1024
    stage = data['stages'][-1]
    assert stage['step'] == handoff and stage['outcome'] == 'launch_error'
    assert stage['returncode'] is None and stage['capture_errors']
    assert all(item['outcome'] == 'pass' for item in data['stages'][:-1])
    cleanup = stage['cleanup']
    assert len(cleanup['attempts']) == 1
    attempt = cleanup['attempts'][0]
    assert attempt['args'] == list(windows_ci_repro._TERMINAL_STOP)
    assert attempt['returncode'] == 0, attempt
    assert attempt['outcome'] == cleanup['outcome'] == 'pass'
    assert attempt['server_result']['ok'] is True
    assert (attempt['server_result']['stop_returncode'], attempt['server_result']['wait_returncode']) == (0, 0)
    assert cleanup['capture_complete'] and attempt['capture_complete']
    assert attempt['stdout']['eof'] and attempt['stderr']['eof']
    state = cleanup['after']['state']
    assert state['ended'] and not state['authorized']
    assert state['stopped_generation'] == state['generation']
    session = observed['session']
    assert session.state() == state
    with pytest.raises((OSError, ValueError)):
        session.environment()  # Normal launch environment still rejects the damaged setup.
    calls = runtime.calls()[observed['calls']:]
    assert not [call for call in calls if 'wine' in call]
    servers = [call for call in calls if 'server' in call]
    assert [call['server'] for call in servers] == [['-k'], ['-w']]
    expected_env = {'WINEPREFIX': str(session.prefix), 'WINEARCH': 'win64',
                    'WINESERVER': session.owner['tools']['server']['executable'],
                    'XDG_DATA_HOME': str(session.directory / 'data'),
                    'XDG_CACHE_HOME': str(session.directory / 'cache'), 'TMPDIR': str(session.tmp),
                    'TEMP': r'C:\windows\temp', 'TMP': r'C:\windows\temp'}
    assert all(call['env'] == expected_env for call in servers)
    ledger = json.loads((runtime.root / data['ledger_path']).read_text())
    assert ledger['stages'][-1]['cleanup']['outcome'] == 'pass'
    assert ledger['stages'][-1]['cleanup']['after']['state'] == state
    for stream in ['stdout', 'stderr']:
        assert (runtime.root / attempt[stream]['path']).is_file()


def shortened_gnu_timeouts(runtime, *, fast='0.3s', admission='4s', cleanup='1s'):
    real_timeout = shutil.which('timeout', path=os.defpath)
    assert real_timeout
    runtime.write_executable('timeout', f'''#!{sys.executable}
import os, sys
mapping = {{'1920s': {fast!r}, '480s': {admission!r}, '45s': {cleanup!r}, '--kill-after=5s': '--kill-after=0.15s'}}
args = [mapping.get(a, a) for a in sys.argv[1:]]
os.execv({real_timeout!r}, [{real_timeout!r}, *args])
''')


@pytest.mark.parametrize('resist', [False, True])
def test_real_outer_timeout_bounds_early_eof_live_helper_and_preserves_124_137(tmp_path, monkeypatch, resist):
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    shortened_gnu_timeouts(runtime)
    fixture_script(runtime.root, 'test-windows-under-wine.sh',
                   "import signal\n" + ("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" if resist else '') +
                   "print('[RUN] before early EOF', flush=True)\nos.close(1); os.close(2)\ntime.sleep(30)")
    started = time.monotonic()
    result = windows_ci_repro.reproduce(runtime.root)
    assert time.monotonic() - started < 5
    stage = result['evidence']['stages'][-1]
    # GNU timeout's own process is killed by its group escalation; keep the
    # actual Popen -SIGKILL status, not a fabricated shell-normalized 137.
    assert stage['returncode'] == (-9 if resist else 124), result
    assert stage['outcome'] == ('nonzero_exit' if resist else 'timeout')
    assert stage['progress']['last_markers']['run']['text'] == '[RUN] before early EOF'
    assert stage['cleanup']['outcome'] == 'pass'


def test_fixed_wine_vectors_require_owner_and_reject_modified_timeout(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    run_dir = windows_ci_repro._new_repro_run(repo)
    vector = dict(windows_ci_repro._REPRO_STEPS)['wine-fast']
    with pytest.raises(ValueError, match='session'):
        windows_ci_repro._run_repro_step(repo, run_dir, 'wine-fast', vector)
    for bad in [vector[3:], ('timeout', '--kill-after=5s', '9999s', *vector[3:]),
                ('timeout', '--kill-after=5s', '1920s', 'sh', '-c', 'exit 0')]:
        with pytest.raises(ValueError, match='fixed'):
            windows_ci_repro._run_repro_step(repo, run_dir, 'wine-fast', bad)


@pytest.mark.parametrize('exit_mode', ['early-exit', 'interrupted-helper', 'outer-kill'])
def test_backstop_stops_escaped_writer_but_not_unrelated_prefix_and_keeps_capture_incomplete(
        tmp_path, monkeypatch, exit_mode):
    import _windows_repro_evidence as evidence
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    shortened_gnu_timeouts(runtime, fast='0.7s')
    writer_program = ("import os,signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                      "while True:\n os.write(1,b'escaped-writer\\n'); time.sleep(.01)\n")
    fixture_script(runtime.root, 'test-windows-under-wine.sh', '''
import signal, subprocess
directory = pathlib.Path('build/wine/sessions') / os.environ['SPACE_WINE_SESSION_ID']
state_file = directory / 'state.json'
state = json.loads(state_file.read_text())
state.update(generation=state['generation']+1, stopped_generation=None, authorized=False)
state_file.write_text(json.dumps(state))
child = subprocess.Popen([sys.executable, '-c', WRITER_PROGRAM], start_new_session=True)
(directory / 'fixture-writer').write_text(str(child.pid))
print('[RUN] escaped writer', flush=True)
'''.replace('WRITER_PROGRAM', repr(writer_program)) + ('' if exit_mode == 'early-exit' else
       "signal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(30)"))
    server = runtime.bin / 'wineserver'
    server.write_text(server.read_text().replace('import json, os, sys', 'import json, os, sys, pathlib, signal').replace(
        "sys.exit(int(os.environ.get('FIXTURE_STOP_CODE'",
        "record=pathlib.Path(os.environ['WINEPREFIX']).parent/'fixture-writer'\n"
        "if sys.argv[1:]==['-k'] and record.exists():\n"
        " try: os.kill(int(record.read_text()), signal.SIGKILL)\n"
        " except ProcessLookupError: pass\n"
        "sys.exit(int(os.environ.get('FIXTURE_STOP_CODE'"))
    if exit_mode == 'interrupted-helper':
        read = evidence._read_pipe
        fired = False
        def interrupt(fd):
            nonlocal fired
            data = read(fd)
            if b'[RUN] escaped writer' in data and not fired:
                fired = True
                raise KeyboardInterrupt()
            return data
        monkeypatch.setattr(evidence, '_read_pipe', interrupt)
    control = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                               env=dict(runtime.env, WINEPREFIX=str(tmp_path / 'unrelated-prefix')),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        start = time.monotonic()
        result = windows_ci_repro.reproduce(runtime.root)
        assert time.monotonic() - start < 9
        assert result['status'] == 'fail'
        stage = result['evidence']['stages'][-1]
        assert stage['step'] == 'wine-fast'
        assert stage['capture_complete'] is False
        assert stage['outcome'] == ('interrupted' if exit_mode == 'interrupted-helper' else 'capture_error')
        assert stage['returncode'] == (0 if exit_mode == 'early-exit' else -9)
        assert stage['cleanup']['outcome'] == 'pass'
        assert stage['cleanup']['after']['state']['stopped_generation'] == stage['cleanup']['after']['state']['generation']
        assert len(stage['cleanup']['attempts']) == 1
        assert control.poll() is None
        assert not (tmp_path / 'unrelated-prefix').exists()
    finally:
        control.kill()
        control.wait()
        for path in (runtime.root / 'build/wine/sessions').glob('*/fixture-writer'):
            try:
                os.kill(int(path.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_real_parent_sigterm_has_terminal_backstop_and_does_not_leak_locks(tmp_path, monkeypatch):
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    fixture_script(runtime.root, 'test-windows-under-wine.sh', '''
import fcntl
directory = pathlib.Path('build/wine/sessions') / os.environ['SPACE_WINE_SESSION_ID']
for entry in pathlib.Path('/proc/self/fd').iterdir():
    try: target = entry.readlink()
    except FileNotFoundError: continue
    assert target not in (pathlib.Path.cwd(), pathlib.Path.cwd()/'build', directory)
for path in (pathlib.Path.cwd(), directory):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: pass
    else: raise AssertionError('parent ownership lock not held')
    os.close(fd)
(directory/'helper-ready').touch()
print('[RUN] parent signal fixture', flush=True)
time.sleep(30)
''')
    driver = (f"import sys,json,pathlib; sys.path.insert(0,{str(SCRIPT_ROOT)!r}); "
              "import opencode_windows_ci_repro as w; "
              f"repo=pathlib.Path({str(runtime.root)!r}); w.ensure_space_repo=lambda _:repo; "
              "w.preflight=lambda _:w.success('preflight','fixture',{}); "
              "print(json.dumps(w.reproduce(repo)),flush=True)")
    child = subprocess.Popen([sys.executable, '-c', driver], cwd=runtime.root,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while not list((runtime.root/'build/wine/sessions').glob('*/helper-ready')) and time.monotonic() < deadline:
            time.sleep(.01)
        assert list((runtime.root/'build/wine/sessions').glob('*/helper-ready'))
        child.send_signal(signal.SIGTERM)
        stdout, stderr = child.communicate(timeout=7)
        assert child.returncode == 0, stderr
        result = json.loads(stdout)
        assert result['status'] == 'fail'
        stage = result['evidence']['stages'][-1]
        assert stage['outcome'] == 'interrupted' and stage['capture_complete'] is False
        assert stage['cleanup']['outcome'] == 'pass'
        assert all(s['outcome'] == 'pass' for s in result['evidence']['stages'][:-1])
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_primary_success_plus_backstop_failure_is_fail_without_rewriting_primary(tmp_path, monkeypatch):
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    fixture_script(runtime.root, 'test-windows-under-wine.sh', '''
directory = pathlib.Path('build/wine/sessions')/os.environ['SPACE_WINE_SESSION_ID']
state_file = directory/'state.json'
state = json.loads(state_file.read_text())
state.update(generation=state['generation']+1, stopped_generation=None, authorized=False)
state_file.write_text(json.dumps(state))
print('[PASS] primary success before backstop', flush=True)
''')
    original = windows_ci_repro._terminal_cleanup
    def fail_stop(*args):
        monkeypatch.setenv('FIXTURE_STOP_CODE', '37')
        return original(*args)
    monkeypatch.setattr(windows_ci_repro, '_terminal_cleanup', fail_stop)
    result = windows_ci_repro.reproduce(runtime.root)
    assert result['status'] == 'fail' and result['evidence']['complete'] is False
    stage = result['evidence']['stages'][-1]
    assert stage['returncode'] == 0 and stage['outcome'] == 'pass'
    assert stage['capture_complete'] is True
    assert stage['cleanup']['outcome'] == 'fail'
    assert stage['progress']['last_markers']['pass']['text'] == '[PASS] primary success before backstop'


@pytest.mark.parametrize('when', ['after-create', 'during-fast'])
def test_owned_cleanup_after_persistent_storage_failure_retains_prior_success_and_live_markers(tmp_path, monkeypatch, when):
    import _windows_repro_evidence as evidence
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    fixture_script(runtime.root, 'test-windows-under-wine.sh',
                   "print('[RUN] after acquisition', flush=True)\ntime.sleep(.4)\n"
                   "print('[PASS] after storage failure', flush=True)\nsys.exit(137)")
    atomic = evidence._atomic
    failed_calls = []
    def disk_full(path, value):
        stages = value.get('stages', [])
        trigger = (path.name == 'ledger.json' and value.get('metadata', {}).get('owned_session')
                   and ((when == 'after-create' and len(stages) == 4)
                        or (when == 'during-fast' and stages[-1]['step'] == 'wine-fast'
                            and stages[-1]['progress']['counts']['run'])))
        if trigger or failed_calls:
            failed_calls.append(path.name)
            raise OSError(errno.ENOSPC, 'fixture owned checkpoint failure')
        return atomic(path, value)
    monkeypatch.setattr(evidence, '_atomic', disk_full)
    result = windows_ci_repro.reproduce(runtime.root)
    data = result['evidence']
    assert result['status'] == 'fail' and data['complete'] is False and data['sealed'] is False
    assert all(s['outcome'] == 'pass' for s in data['stages'][:4])
    assert len(failed_calls) == 1
    stage = data['stages'][-1]
    assert stage['cleanup']['outcome'] == 'pass'
    assert stage['cleanup']['after']['state']['ended']
    if when == 'during-fast':
        assert len(data['stages']) == 6
        assert stage['returncode'] == 137 and stage['outcome'] == 'nonzero_exit'
        assert stage['capture_complete'] is False
        assert stage['progress']['last_markers']['pass']['text'] == '[PASS] after storage failure'
    else:
        assert len(data['stages']) == 5 and stage['outcome'] == 'not_launched'
    assert len(json.dumps(result).encode()) <= 48 * 1024


@pytest.mark.parametrize('fault', ['append-open', 'append-write'])
def test_cleanup_log_failure_cannot_report_complete_success_but_still_stops(tmp_path, monkeypatch, fault):
    import fcntl
    import _windows_repro_evidence as evidence
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    if fault == 'append-open':
        open_fd = evidence.os.open
        def denied(path, flags, *args, **kwargs):
            if flags & os.O_APPEND:
                raise OSError('fixture cleanup append denied')
            return open_fd(path, flags, *args, **kwargs)
        monkeypatch.setattr(evidence.os, 'open', denied)
    else:
        fdopen = evidence.os.fdopen
        class BrokenAppend:
            def __init__(self, output):
                self.output = output
            def write(self, data):
                raise OSError('fixture cleanup append full')
            def close(self):
                self.output.close()
        def broken(fd, *args, **kwargs):
            append = fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_APPEND
            output = fdopen(fd, *args, **kwargs)
            return BrokenAppend(output) if append else output
        monkeypatch.setattr(evidence.os, 'fdopen', broken)
    result = windows_ci_repro.reproduce(runtime.root)
    assert result['status'] == 'fail' and result['evidence']['complete'] is False
    stage = result['evidence']['stages'][-1]
    assert stage['returncode'] == 0 and stage['outcome'] == 'pass'
    assert stage['capture_complete'] is True
    assert stage['cleanup']['outcome'] == 'pass'  # actual owned shutdown succeeded
    attempt = stage['cleanup']['attempts'][0]
    assert attempt['capture_complete'] is False and attempt['capture_errors']
    assert attempt['server_result']['ok'] is True
    assert stage['cleanup']['after']['state']['ended']


def test_real_gnu_backstop_bound_terminates_term_resistant_helper_after_early_eof(tmp_path, monkeypatch):
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    shortened_gnu_timeouts(runtime, fast='4s', cleanup='0.2s')
    helper = runtime.root / 'scripts/wine/artifacts.py'
    helper.write_text("import os,sys,signal,time\nif sys.argv[1:]==['terminal-stop']:\n"
                      " signal.signal(signal.SIGTERM,signal.SIG_IGN)\n os.close(1); os.close(2)\n time.sleep(30)\n"
                      + helper.read_text())
    started = time.monotonic()
    result = windows_ci_repro.reproduce(runtime.root)
    assert time.monotonic() - started < 5
    assert result['status'] == 'fail'
    stage = result['evidence']['stages'][-1]
    assert stage['outcome'] == 'pass' and stage['returncode'] == 0
    assert stage['cleanup']['outcome'] == 'fail'
    attempt = stage['cleanup']['attempts'][0]
    assert attempt['returncode'] == -9
    assert attempt['args'] == list(windows_ci_repro._TERMINAL_STOP)
    assert len(stage['cleanup']['attempts']) == 1


def test_cleanup_appends_within_existing_full_log_cap_and_keeps_marker_in_memory(tmp_path, monkeypatch):
    repo = reproduction_fixture(tmp_path, monkeypatch)
    cap = 16 * 1024 * 1024
    fixture_script(repo, 'test-windows-under-wine.sh',
                   f"os.write(1, b'x'*{cap} + b'\\n[PASS] capped primary\\n')")
    result = windows_ci_repro.reproduce(repo)
    assert result['status'] == 'pass'
    stage = result['evidence']['stages'][-1]
    assert (repo / stage['stdout']['path']).stat().st_size == cap
    assert stage['stdout']['stored_bytes'] == cap
    attempt = stage['cleanup']['attempts'][0]
    assert attempt['stdout']['stored_bytes'] == 0
    assert attempt['stdout']['observed_bytes'] > 0 and attempt['stdout']['log_truncated'] is True
    assert attempt['capture_complete'] is True and attempt['server_result']['ok'] is True
    assert stage['progress']['last_markers']['pass']['text'] == '[PASS] capped primary'


@pytest.mark.parametrize('publication_unavailable', [False, True])
@pytest.mark.parametrize('primary_code', [0, 137])
def test_malformed_cleanup_markers_keep_bounded_history_after_log_cap(
        tmp_path, monkeypatch, publication_unavailable, primary_code):
    import _windows_repro_evidence as evidence
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv('FIXTURE_APP_CODE', str(primary_code))
    helper = runtime.root / 'scripts/wine/artifacts.py'
    helper.write_text("import os,sys\nif sys.argv[1:]==['terminal-stop']:\n"
                      " os.write(1,b'x'*(16*1024*1024)+b'\\n')\n"
                      " for _ in range(2003): print('Wine cleanup: {}')\n" + helper.read_text())
    if publication_unavailable:
        atomic = evidence._atomic
        def disk_full(path, value):
            stages = value.get('stages', [])
            if (path.name == 'ledger.json' and stages and stages[-1]['step'] == 'wine-fast'
                    and stages[-1]['outcome'] != 'started'):
                raise OSError(errno.ENOSPC, 'fixture final primary checkpoint unavailable')
            return atomic(path, value)
        monkeypatch.setattr(evidence, '_atomic', disk_full)
    result = windows_ci_repro.reproduce(runtime.root)
    assert len(json.dumps(result, sort_keys=True).encode()) <= 48 * 1024
    assert result['status'] == 'fail'
    data = result['evidence']
    assert data['complete'] is False
    assert [s['step'] for s in data['stages']] == list(evidence._STEPS)
    assert all(s['outcome'] == 'pass' for s in data['stages'][:5])
    stage = data['stages'][-1]
    assert stage['returncode'] == primary_code
    expected = 'evidence_error' if primary_code == 0 and publication_unavailable else 'pass' if primary_code == 0 else 'nonzero_exit'
    assert stage['outcome'] == expected
    cleanup = stage['cleanup']
    assert cleanup['outcome'] == 'pass' and cleanup['after']['state']['ended']
    attempt = cleanup['attempts'][0]
    assert attempt['capture_complete'] is False
    assert attempt['malformed_cleanup_markers'] == 2003
    assert attempt['capture_errors'].count('Invalid owned cleanup result marker') == 1
    assert len(attempt['capture_errors']) == 1
    assert attempt['server_result']['ok'] is True
    assert attempt['server_result']['stop_returncode'] == attempt['server_result']['wait_returncode'] == 0
    assert stage['stdout']['stored_bytes'] + attempt['stdout']['stored_bytes'] == 16 * 1024 * 1024
    assert attempt['stdout']['log_truncated'] is True
    assert all((runtime.root / s[name]['path']).is_file() for s in data['stages'] for name in ('stdout', 'stderr'))
    ledger_path = runtime.root / data['ledger_path']
    assert ledger_path.is_file()
    if publication_unavailable:
        assert data['sealed'] is False and data['persistence_errors']
    else:
        assert json.loads(ledger_path.read_text())['stages'] == data['stages']


def test_cleanup_marker_keeps_stop_wait_codes_for_missing_state_under_long_unicode_repo(tmp_path, monkeypatch):
    parent = tmp_path
    for index in range(18):
        # Each component is 161 UTF-8 bytes, safely below the OS's 255-byte cap.
        parent = parent / (str(index % 10) + '😀' * 40)
    parent.mkdir(parents=True)
    runtime = owned_reproduction_fixture(parent, monkeypatch)
    run = windows_ci_repro._run_repro_step
    def missing_state(repo, run_dir, step, args, session=None):
        record = run(repo, run_dir, step, args, session)
        if step == 'wine-fast':
            (session.directory / 'state.json').unlink()
        return record
    monkeypatch.setattr(windows_ci_repro, '_run_repro_step', missing_state)
    result = windows_ci_repro.reproduce(runtime.root)
    assert result['status'] == 'fail'
    assert len(json.dumps(result).encode()) <= 48 * 1024
    data = result['evidence']
    assert len(data['stages']) == 6
    stage = data['stages'][-1]
    assert stage['returncode'] == 0 and stage['outcome'] == 'pass'
    cleanup = stage['cleanup']
    assert cleanup['outcome'] == 'fail'
    attempt = cleanup['attempts'][0]
    server = attempt['server_result']
    assert server['ok'] is False
    assert server['stop_returncode'] == server['wait_returncode'] == 0
    assert server['errors'] and 'Lifecycle read:' in server['errors'][0]
    assert server['errors_truncated'] is True
    assert server['error_count'] == 1
    assert len(server['errors']) == len(server['error_excerpt_truncated']) == 1
    assert server['error_excerpt_truncated'] == [True]
    assert attempt['stdout']['oversized_lines'] == 0
    assert [c['server'] for c in runtime.calls() if 'server' in c][-2:] == [['-k'], ['-w']]
    raw = (runtime.root / attempt['stdout']['path']).read_bytes()
    marker = next(line for line in raw.split(b'\n') if line.startswith(b'Wine cleanup: '))
    assert len(marker) <= 4096


@pytest.mark.parametrize('character', ['\x00', '😀'])
@pytest.mark.parametrize('delta', [0, 1])
def test_cleanup_marker_exact_encoded_boundary_not_character_count(tmp_path, monkeypatch, character, delta):
    import _windows_repro_evidence as evidence
    # The producer's metadata is present in both the untruncated and truncated
    # variants. Include JSON escapes in the exact 4KiB arithmetic, not UTF-8 size.
    value = {'ok': False, 'stop_returncode': 37, 'wait_returncode': 0,
             'errors': ['', ''], 'error_count': 2, 'errors_truncated': False,
             'error_excerpt_truncated': [False, False]}
    prefix = 'Wine cleanup: '
    overhead = len((prefix + json.dumps(value)).encode())
    unit = len(json.dumps(character).encode()) - 2
    count, padding = divmod(4096 - overhead, unit)
    errors = [character * (count // 2), character * (count - count // 2) + 'a' * (padding + delta)]
    value['errors'] = errors
    assert len((prefix + json.dumps(value)).encode()) == 4096 + delta
    assert all(len(error) <= 500 for error in errors)  # existing per-error char cap is not sufficient
    runtime = owned_reproduction_fixture(tmp_path, monkeypatch)
    helper = runtime.root / 'scripts/wine/artifacts.py'
    # Run the real private terminal-stop path with deterministic host-only
    # cleanup data to test the emitter/parser boundary without any PE process.
    helper.write_text(helper.read_text().replace(
        "result = prefix.stop_session(selected_session(), end=True)",
        f"result = prefix.CleanupResult(False, 37, 0, {errors!r})"))
    record = evidence._record('terminal-stop', windows_ci_repro._TERMINAL_STOP)
    for name in ('stdout', 'stderr'):
        record[name] = evidence._stream_info('fixture')
    completed = subprocess.run([sys.executable, str(helper), 'terminal-stop'], cwd=runtime.root,
                               capture_output=True, check=False, timeout=5)
    marker = completed.stdout.removesuffix(b'\n')
    assert marker.startswith(prefix.encode())
    assert len(marker) <= evidence._LINE_CAP == 4096
    evidence._marker_line(record, marker, 'stdout')
    server = record['server_result']
    assert server['stop_returncode'] == 37 and server['wait_returncode'] == 0
    assert server['error_count'] == 2 and server['ok'] is False
    assert server['errors_truncated'] is bool(delta)
    assert any(server['error_excerpt_truncated']) is bool(delta)
    if delta == 0:
        assert len(marker) == 4096 and server['errors'] == errors
    else:
        assert any(len(excerpt) < len(error) for excerpt, error in zip(server['errors'], errors))
