#!/usr/bin/env python3
"""Guarded Windows CI local reproduction capability for OpenCode agents."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import signal
import sys
import time
from pathlib import Path
from typing import Sequence

import _windows_repro_evidence as _evidence
from wine import prefix as _prefix
from wine import publication_toolchain as _publication_toolchain
from opencode_capabilities import CapabilityError, CommandResult, ensure_space_repo, failure, human_decision, run_command, success


REQUIRED_TOOLS = (
    "cmake",
    "git",
    "pkg-config",
    "nasm",
    "llvm-ml-14",
    "curl",
    "zip",
    "pwsh",
    "autoconf",
    "g++",
    "x86_64-w64-mingw32-gcc-posix",
    "x86_64-w64-mingw32-g++-posix",
    "rustc",
)
REQUIRED_SCRIPTS = (
    "scripts/setup-windows-build-host.sh",
    "scripts/build-windows-from-linux.sh",
    "scripts/package-windows-runtime.sh",
    "scripts/prepare-windows-wine-runtime.sh",
    "scripts/build-wine-bcryptprimitives-compat.sh",
    "scripts/wine/prefix.py",
    "scripts/wine/artifacts.py",
    "scripts/wine/publication_toolchain.py",
    "scripts/wine/probe.c",
    "scripts/wine/process_prng_compat.c",
    "scripts/test-windows-under-wine.sh",
)
WINDOWS_RUST_TARGET = "x86_64-pc-windows-gnu"
VCPKG_BRANCH = "2025.03.19"

_WINDOWS_OUTPUTS = (
    "build/dist/windows/space.exe",
    "build/dist/windows/space-cli.exe",
    "build/windows/CPackConfig.cmake",
    "build/windows/space.ico",
    "scripts/windows-installer.iss",
)
_SETUP_COMMAND = "python3 scripts/opencode_windows_ci_repro.py setup-host --repo-root ."
_BOOTSTRAP_VCPKG_COMMAND = "python3 scripts/opencode_windows_ci_repro.py bootstrap-vcpkg --repo-root ."


def _exit_code_for(status: str) -> int:
    return {"pass": 0, "human_decision_required": 2, "fail": 3}.get(status, 3)


def _tail(output: str, *, limit: int = 4000) -> str:
    if len(output) <= limit:
        return output
    return output[-limit:]


def _command_evidence(result: CommandResult) -> dict[str, object]:
    return {
        "args": result.args,
        "returncode": result.returncode,
        "stdout_tail": _tail(result.stdout),
        "stderr_tail": _tail(result.stderr),
    }


def _command_start_failure(args: Sequence[str], error: OSError) -> CommandResult:
    return CommandResult(list(args), 127, "", f"{type(error).__name__}: {error}")


def _missing_executable_failure(args: Sequence[str], path: Path) -> CommandResult:
    return CommandResult(list(args), 127, "", f"Executable file is missing or not executable: {path}")


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _script_exists(repo: Path, relative: str) -> bool:
    return (repo / relative).is_file()


def _wine_available() -> bool:
    configured_wine = os.environ.get("WINE_CMD")
    if configured_wine:
        return shutil.which(configured_wine) is not None
    return shutil.which("wine64") is not None or shutil.which("wine") is not None


def _vcpkg_binary(repo: Path) -> Path:
    vcpkg_root = os.environ.get("VCPKG_ROOT")
    if vcpkg_root:
        return Path(vcpkg_root) / "vcpkg"
    return repo / "vcpkg" / "vcpkg"


def _vcpkg_root(repo: Path) -> Path:
    vcpkg_root = os.environ.get("VCPKG_ROOT")
    if vcpkg_root:
        return Path(vcpkg_root)
    return repo / "vcpkg"


def _is_under_repo(path: Path, repo: Path) -> bool:
    try:
        path.resolve().relative_to(repo.resolve())
    except ValueError:
        return False
    return True


def _display_path(repo: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo))
    except ValueError:
        return str(path)


def _rust_target_installed(repo: Path) -> bool:
    try:
        result = run_command(["rustup", "target", "list", "--installed"], repo, check=False)
    except OSError:
        return False
    if result.returncode != 0:
        return False
    return WINDOWS_RUST_TARGET in {line.strip() for line in result.stdout.splitlines()}


def _is_ubuntu_host() -> bool:
    try:
        lines = Path("/etc/os-release").read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    values = dict(line.split("=", 1) for line in lines if "=" in line)
    return values.get("ID", "").strip('"') == "ubuntu"


def preflight(repo_root: Path) -> dict[str, object]:
    try:
        repo = ensure_space_repo(repo_root)
    except CapabilityError as error:
        return _failure_for_exception("preflight", error)
    missing: list[str] = []
    missing_by_category: dict[str, list[str]] = {
        "system_tools": [],
        "scripts": [],
        "vcpkg": [],
        "wine": [],
        "rust_targets": [],
        "publication_toolchain": [],
    }

    missing_by_category["system_tools"].extend(tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None)
    missing_by_category["scripts"].extend(script for script in REQUIRED_SCRIPTS if not _script_exists(repo, script))
    vcpkg_binary = _vcpkg_binary(repo)
    if not _is_executable_file(vcpkg_binary):
        missing_by_category["vcpkg"].append(_display_path(repo, vcpkg_binary))
    if not _wine_available():
        missing_by_category["wine"].append("wine")
    if not _rust_target_installed(repo):
        missing_by_category["rust_targets"].append(f"rust-target:{WINDOWS_RUST_TARGET}")
    toolchain = None
    toolchain_error = None
    try:
        toolchain = _publication_toolchain.resolve_toolchain(repo)
    except (ValueError, OSError) as error:
        toolchain_error = str(error)[:1000]
        missing_by_category['publication_toolchain'].extend(getattr(error, 'missing', []) or ['wine-publication-toolchain'])

    for category_missing in missing_by_category.values():
        category_missing.sort()
        missing.extend(category_missing)

    evidence: dict[str, object] = {
        "repo_root": str(repo),
        "missing": sorted(set(missing)),
        "missing_by_category": missing_by_category,
    }
    if toolchain is not None:
        summary = dict(toolchain)
        headers = dict(toolchain['headers'])
        files = headers.pop('files')
        headers.update(file_count=len(files), inventory_sha256=hashlib.sha256(
            json.dumps(files, sort_keys=True).encode()).hexdigest())
        summary['headers'] = headers
        evidence['publication_toolchain'] = summary
    if toolchain_error is not None:
        evidence['publication_toolchain_error'] = toolchain_error
    if not missing:
        return success("preflight", "Windows CI reproduction prerequisites are available", evidence)

    if evidence["missing"] == ["vcpkg/vcpkg"] and missing_by_category["vcpkg"] == ["vcpkg/vcpkg"]:
        evidence["code"] = "missing_local_vcpkg"
        evidence["bootstrap_vcpkg_command"] = _BOOTSTRAP_VCPKG_COMMAND
        return failure("preflight", "Repository-local vcpkg is missing", evidence)

    evidence["code"] = "missing_windows_ci_repro_prerequisites"
    evidence["setup_capability_command"] = _SETUP_COMMAND
    return failure("preflight", "Windows CI reproduction prerequisites are missing", evidence)


def setup_host(repo_root: Path) -> dict[str, object]:
    try:
        repo = ensure_space_repo(repo_root)
    except CapabilityError as error:
        return _failure_for_exception("setup-host", error)
    if sys.platform != "linux" or not _is_ubuntu_host() or shutil.which("sudo") is None:
        return human_decision(
            "setup-host",
            "Windows CI reproduction host setup requires an Ubuntu Linux host with sudo",
            {
                "code": "unsupported_windows_ci_setup_host",
                "platform": sys.platform,
                "ubuntu": _is_ubuntu_host(),
                "sudo_available": shutil.which("sudo") is not None,
            },
        )

    try:
        _publication_toolchain.plan_setup(repo)
    except (ValueError, OSError) as error:
        return human_decision('setup-host', 'Matched Wine publication provisioning refused',
                              {'code': 'wine_publication_setup_refused', 'error': str(error)[:1000]})
    result = run_command(["scripts/setup-windows-build-host.sh"], repo, check=False)
    evidence = _command_evidence(result)
    if result.returncode == 0:
        return success("setup-host", "Windows CI reproduction host setup completed", evidence)
    evidence["code"] = "windows_ci_setup_host_failed"
    return human_decision("setup-host", "Windows CI reproduction host setup failed", evidence)


def bootstrap_vcpkg(repo_root: Path) -> dict[str, object]:
    try:
        repo = ensure_space_repo(repo_root)
    except CapabilityError as error:
        return _failure_for_exception("bootstrap-vcpkg", error)

    root = _vcpkg_root(repo).expanduser()
    if os.environ.get("VCPKG_ROOT") and not _is_under_repo(root, repo):
        return human_decision(
            "bootstrap-vcpkg",
            "External VCPKG_ROOT cannot be bootstrapped by this repo-local capability",
            {
                "code": "external_vcpkg_root_not_bootstrapped",
                "repo_root": str(repo),
                "vcpkg_root": str(root.resolve()),
            },
        )

    binary = root / "vcpkg"
    if _is_executable_file(binary):
        return success(
            "bootstrap-vcpkg",
            "Repository-local vcpkg is already bootstrapped",
            {"repo_root": str(repo), "vcpkg_root": str(root.resolve()), "commands": []},
        )

    commands: list[list[str]] = []
    if not root.exists():
        clone_args = [
            "git",
            "clone",
            "--branch",
            VCPKG_BRANCH,
            "https://github.com/microsoft/vcpkg",
            str(root),
        ]
        try:
            clone_result = run_command(clone_args, repo, check=False)
        except OSError as error:
            clone_result = _command_start_failure(clone_args, error)
        commands.append(clone_result.args)
        if clone_result.returncode != 0:
            evidence = _command_evidence(clone_result)
            evidence["code"] = "vcpkg_clone_failed"
            evidence["failing_step"] = "clone-vcpkg"
            return failure("bootstrap-vcpkg", "Repository-local vcpkg clone failed", evidence)

    if not _is_executable_file(binary):
        bootstrap_args = [str(root / "bootstrap-vcpkg.sh")]
        bootstrap_script = root / "bootstrap-vcpkg.sh"
        if not _is_executable_file(bootstrap_script):
            bootstrap_result = _missing_executable_failure(bootstrap_args, bootstrap_script)
        else:
            try:
                bootstrap_result = run_command(bootstrap_args, repo, check=False)
            except OSError as error:
                bootstrap_result = _command_start_failure(bootstrap_args, error)
        commands.append(bootstrap_result.args)
        if bootstrap_result.returncode != 0:
            evidence = _command_evidence(bootstrap_result)
            evidence["code"] = "vcpkg_bootstrap_failed"
            evidence["failing_step"] = "bootstrap-vcpkg"
            return failure("bootstrap-vcpkg", "Repository-local vcpkg bootstrap failed", evidence)

    return success(
        "bootstrap-vcpkg",
        "Repository-local vcpkg bootstrap completed",
        {"repo_root": str(repo), "vcpkg_root": str(root.resolve()), "commands": commands},
    )


def _verify_windows_outputs(repo: Path) -> list[str]:
    return [relative for relative in _WINDOWS_OUTPUTS if not (repo / relative).is_file()]


def reproduce(repo_root: Path) -> dict[str, object]:
    try:
        repo = ensure_space_repo(repo_root)
    except CapabilityError as error:
        return _evidence._bounded_response(_failure_for_exception("reproduce", error))
    # Serialize the complete fixed operation without a replaceable lockfile.
    # Artifact preparation/consumption independently locks build/ as well.
    fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    previous = {}
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        def interrupted(signum, frame):
            # selectors treats InterruptedError as a retryable syscall EINTR.
            # A lifecycle exit must escape that retry path and reach finally.
            raise KeyboardInterrupt(f"Reproduction interrupted by signal {signum}")
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, interrupted)
        return _reproduce_steps(repo)
    except (OSError, ValueError) as error:
        return _evidence._bounded_response(_failure_for_exception("reproduce", error))
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        os.close(fd)


_REPRO_STEPS = (
    ("preflight", ()),
    ("build-windows-from-linux", ("scripts/build-windows-from-linux.sh",)),
    ("package-windows-runtime", ("scripts/package-windows-runtime.sh",)),
    ("verify-windows-outputs", ()),
    ("wine-admission", ("timeout", "--kill-after=5s", "480s", "scripts/prepare-windows-wine-runtime.sh")),
    ("wine-fast", ("timeout", "--kill-after=5s", "1920s", "scripts/test-windows-under-wine.sh")),
)
_TERMINAL_STOP = ("timeout", "--kill-after=5s", "45s", "python3", "scripts/wine/artifacts.py", "terminal-stop")


def _selection_conflicts() -> list[str]:
    # Runner's actual overrides, plus reject inherited suite/module selectors
    # rather than silently accepting an unknown selection contract.
    forbidden = ("TEST_FILTER", "SPACE_TEST_CASE_TIMEOUT_SECONDS", "TEST_SUITE", "SPACE_TEST_SUITE",
                 "TEST_MODULES", "SPACE_TEST_MODULES")
    conflicts = [key for key in forbidden if os.environ.get(key)]
    conflicts.extend(key for key in ("SPACE_MATRIX_TEST", "SPACE_REALTIME_TEST") if os.environ.get(key) == "1")
    if "SPACE_WINE_SESSION_ID" in os.environ:
        conflicts.append("SPACE_WINE_SESSION_ID")
    if _evidence.APPLICATION_OBSERVER_ENV in os.environ:
        conflicts.append(_evidence.APPLICATION_OBSERVER_ENV)
    return sorted(conflicts)


def _launch_metadata(repo: Path) -> dict[str, object]:
    return {"module": "tests.fast:main", "deadline_seconds": 1800, "admission_deadline_seconds": 60,
            "bounds": dict(_prefix.BOUNDS, admission_outer=480, fast_outer=1920, cleanup_backstop=45),
            "case_deadline_seconds": 120, "case_deadline_policy": "existing per-case overrides unchanged",
            "diagnostics": {"TEST_VERBOSE": "1", "SPACE_TEST_TIMINGS": "1"}, "skip_keyring_tests": True,
            "prefix_selection": "generated-owned-session", "effective_prefix": None,
            "display_present": bool(os.environ.get("DISPLAY")),
            "wayland_display_present": bool(os.environ.get("WAYLAND_DISPLAY")),
            "effective_uid": os.geteuid(), "effective_gid": os.getegid()}


def _admitted_metadata(repo: Path, session: _prefix.Session) -> dict[str, object]:
    # Read the existing receipt only. Do not call configuration(), run --version,
    # reseal the overlay, or copy receipt conditions/private prefix contents.
    session.validate()
    build = _evidence._safe_path(repo / "build")
    fd = os.open(build, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        receipt = _evidence._read_json(repo / "build/wine/windows/admission.json", 16 * 1024 * 1024)
        tools = receipt["tools"]
        payload = receipt["payload"]
        if (receipt["version"] != 2 or not isinstance(tools, dict) or not isinstance(payload, dict)
                or tools != session.owner['tools'] or receipt['ownedSession'] != session.binding()
                or not all(isinstance(identity[key], str) and len(identity[key]) <= 4096
                           for identity in tools.values() for key in ("executable", "version", "sha256"))
                or receipt["backend"] not in ("bcryptprimitives=b;advapi32,cryptbase=b", "bcryptprimitives=n;advapi32,cryptbase=b")):
            raise ValueError("Invalid admission metadata")
        return {"owned_session": session.binding(),
                "wine": {key: tools['wine'][key] for key in ("executable", "version", "sha256")},
                "backend": receipt["backend"],
                "payload": {name: payload[name] for name in ("space.exe", "space-cli.exe") if name in payload},
                "payload_inventory_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}
    finally:
        os.close(fd)


def _new_repro_run(repo: Path) -> Path:
    return _evidence._new_run(repo)


def _run_repro_step(repo: Path, run_dir: Path, step: str, args: Sequence[str],
                    session: _prefix.Session | None = None) -> dict:
    # No arbitrary commands even via this private interface: only the fixed
    # internal stage table can supply argv; CLI accepts no command/env/profile.
    if (step, tuple(args)) not in _REPRO_STEPS:
        raise ValueError("Not a fixed Windows reproduction command")
    if step in ('wine-admission', 'wine-fast'):
        if not isinstance(session, _prefix.Session) or session.repo != repo:
            raise ValueError("Wine stage requires the generated owned session")
        session.validate()
    elif session is not None:
        raise ValueError("Session handoff is private to known Wine steps")
    ledger, record, logs = _evidence._start(repo, run_dir, step, args)
    if session is not None:
        record['session_before'] = _session_state(session)
    if args:
        return _evidence._capture(repo, run_dir, ledger, record, logs, list(args), session)
    outcome, code, complete = "pass", 0, True
    try:
        if step == "preflight":
            conflicts = _selection_conflicts()
            result = (failure("preflight", "Conflicting inherited test selection/deadline settings",
                              {"code": "conflicting_test_settings", "conflicting_keys": conflicts})
                      if conflicts else preflight(repo))
            record["details"] = result
            if result["status"] != "pass":
                outcome, code = "nonzero_exit", 1
        else:
            missing = _verify_windows_outputs(repo)
            record["missing"] = missing
            if missing:
                outcome, code = "nonzero_exit", 1
    except KeyboardInterrupt:
        outcome, code, complete = "interrupted", None, False
        record["capture_errors"].append("KeyboardInterrupt during in-process stage")
    except Exception as error:
        outcome, code, complete = "capture_error", None, False
        record["capture_errors"].append(f"{type(error).__name__}: {str(error)[:500]}")
    finally:
        for stream, output in logs.items():
            output.close()
            record[stream]["eof"] = True
    return _evidence._finish(repo, run_dir, ledger, record, outcome, code, complete)


def _session_state(session):
    try:
        session.validate()
        return {"state": session.state(), "errors": []}
    except Exception as error:
        return {"state": None, "errors": [f"{type(error).__name__}: {str(error)[:500]}"]}


def _terminal_cleanup(repo, run_dir, ledger, stage, session):
    cleanup = {"started_utc": _evidence._utc(), "started_monotonic": time.monotonic(),
               "before": _session_state(session), "attempts": []}
    stage["cleanup"] = cleanup
    # Helpers already own teardown. One bounded backstop retries failed cleanup;
    # verified stopped generations merely revoke authorization, no server calls.
    attempt = _evidence._cleanup_capture(repo, run_dir, stage, list(_TERMINAL_STOP), session)
    cleanup["attempts"].append(attempt)
    cleanup["after"] = _session_state(session)
    state = cleanup['after']['state']
    result = attempt.get('server_result', {})
    cleanup['outcome'] = ('pass' if result.get('ok') is True and attempt['returncode'] == 0
                          and state is not None and state['ended'] and not state['authorized']
                          and state['stopped_generation'] == state['generation'] else 'fail')
    cleanup['finished_utc'] = _evidence._utc()
    cleanup['finished_monotonic'] = time.monotonic()
    cleanup['elapsed_seconds'] = cleanup['finished_monotonic'] - cleanup['started_monotonic']
    cleanup['capture_complete'] = attempt['capture_complete']
    return cleanup['outcome'] == 'pass' and cleanup['capture_complete']


def _reproduce_steps(repo: Path) -> dict[str, object]:
    run_dir = _new_repro_run(repo)
    ledger = _evidence._read_json(run_dir / "ledger.json")
    ledger["metadata"] = _launch_metadata(repo)
    failed = None
    step = "preflight"
    session = None
    session_fd = None
    try:
        _evidence._save(repo, run_dir, ledger)
        for step, args in _REPRO_STEPS:
            record = _run_repro_step(repo, run_dir, step, args,
                                     session if step in ('wine-admission', 'wine-fast') else None)
            # Keep the known history in memory, including the current record.
            # A stale disk checkpoint is never the recovery source of truth.
            ledger["stages"].append(record)
            if session is not None and step in ('wine-admission', 'wine-fast'):
                record['session_after'] = _session_state(session)
            if record["outcome"] != "pass":
                failed = step
                break
            if step == 'verify-windows-outputs':
                # Output verification has succeeded. Ownership/metadata failures
                # belong to admission, never rewrite that earlier success.
                step = 'wine-admission'
                build_fd = os.open(repo / 'build', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    fcntl.flock(build_fd, fcntl.LOCK_EX)
                    session = _prefix.create_session(repo)
                    session_fd = os.open(session.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    fcntl.flock(session_fd, fcntl.LOCK_EX)
                finally:
                    os.close(build_fd)
                ledger['metadata'].update(owned_session=session.binding(),
                                          effective_prefix=str(session.prefix), tools=session.owner['tools'])
                _evidence._save(repo, run_dir, ledger)
            if record['step'] == "wine-admission":
                ledger["metadata"].update(_admitted_metadata(repo, session))
                _evidence._save(repo, run_dir, ledger)
    except _evidence._PersistenceError as error:
        ledger = error.ledger
        failed = step
        if ledger["stages"] and ledger["stages"][-1]["step"] == step:
            partial = ledger["stages"][-1]
            partial["capture_complete"] = False
            if partial["outcome"] in ("started", "pass"):
                partial["outcome"] = "evidence_error"
            if partial["finished_utc"] is None:
                end = time.monotonic()
                partial.update(finished_utc=_evidence._utc(), finished_monotonic=end,
                               elapsed_seconds=end - partial["started_monotonic"])
    except (Exception, KeyboardInterrupt) as error:
        # Even a storage/metadata failure retains previous successful evidence.
        failed = step
        ledger["errors"] = [f"{type(error).__name__}: {str(error)[:500]}"]
        ledger["complete"] = False
        if ledger["stages"] and ledger["stages"][-1]["step"] == step:
            partial = ledger["stages"][-1]
            if partial['outcome'] in ('started', 'pass'):
                partial["outcome"] = "interrupted" if isinstance(error, (KeyboardInterrupt, InterruptedError)) else "evidence_error"
            partial["capture_complete"] = False
            partial["capture_errors"].extend(ledger["errors"])
    finally:
        if session is not None:
            with _prefix.cleanup_signals():
                try:
                    stage = ledger['stages'][-1]
                    # Ownership can precede wine-admission's first checkpoint.
                    # Use its fixed log names, without adding a seventh stage.
                    if stage['step'] not in ('wine-admission', 'wine-fast'):
                        stage = _evidence._record('wine-admission', dict(_REPRO_STEPS)['wine-admission'])
                        for name in ('stdout', 'stderr'):
                            path = run_dir / f'wine-admission.{name}.log'
                            stage[name] = _evidence._stream_info(path.relative_to(repo).as_posix())
                            try:
                                _evidence._exclusive(path).close()
                            except (OSError, ValueError):
                                pass  # Cleanup capture records unavailable logs explicitly.
                        end = time.monotonic()
                        stage.update(outcome='not_launched', finished_utc=_evidence._utc(),
                                     finished_monotonic=end, elapsed_seconds=end-stage['started_monotonic'])
                        ledger['stages'].append(stage)
                    if not _terminal_cleanup(repo, run_dir, ledger, stage, session):
                        failed = failed or stage['step']
                except (Exception, KeyboardInterrupt) as error:
                    failed = failed or step
                    ledger.setdefault('errors', []).append(f'Terminal cleanup: {type(error).__name__}: {str(error)[:500]}')
                finally:
                    if session_fd is not None:
                        os.close(session_fd)
    ledger.update(outcome="fail" if failed else "pass", finished_utc=_evidence._utc(),
                  complete=not failed and all(s["capture_complete"] for s in ledger["stages"]))
    sealed = False
    if not ledger.get("persistence_errors"):
        try:
            _evidence._save(repo, run_dir, ledger)
            _evidence._seal(repo, run_dir)
            sealed = True
        except _evidence._PersistenceError as error:
            ledger = error.ledger
        except (Exception, KeyboardInterrupt) as error:
            _evidence._persistence_failure(ledger, "seal/finalization", error)
    if ledger.get("persistence_errors"):
        failed = failed or "finalize-evidence"
        ledger.update(outcome="fail", complete=False)
    evidence = {"ledger_path": (run_dir / "ledger.json").relative_to(repo).as_posix(),
                "metadata": ledger["metadata"], "stages": ledger["stages"], "complete": ledger["complete"], "sealed": sealed}
    if "persistence_errors" in ledger:
        evidence["persistence_errors"] = ledger["persistence_errors"]
    if "errors" in ledger:
        evidence["errors"] = ledger["errors"]
    if failed:
        evidence["failing_step"] = failed
        result = failure("reproduce", "Windows CI reproduction step failed", evidence)
    else:
        evidence["checked_outputs"] = list(_WINDOWS_OUTPUTS)
        result = success("reproduce", "Windows CI reproduction completed successfully", evidence)
    return _evidence._bounded_response(result)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "setup-host", "bootstrap-vcpkg", "reproduce"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--repo-root", required=True, type=Path)
    return parser.parse_args(argv)


def _failure_for_exception(action: str, error: Exception) -> dict[str, object]:
    if isinstance(error, CapabilityError):
        return failure(action, error.message, {"code": error.code, "details": error.details})
    return failure(
        action,
        "Windows CI reproduction wrapper failed unexpectedly",
        {"code": "unexpected_windows_ci_repro_error", "error_type": type(error).__name__, "error": str(error)},
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "preflight":
            result = preflight(args.repo_root)
        elif args.command == "setup-host":
            result = setup_host(args.repo_root)
        elif args.command == "bootstrap-vcpkg":
            result = bootstrap_vcpkg(args.repo_root)
        else:
            result = reproduce(args.repo_root)
    except Exception as error:
        result = _failure_for_exception(args.command, error)
    print(json.dumps(result, sort_keys=True))
    return _exit_code_for(str(result["status"]))


if __name__ == "__main__":
    raise SystemExit(main())
