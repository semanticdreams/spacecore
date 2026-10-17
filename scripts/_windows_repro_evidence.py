"""Private evidence storage/drain for the fixed Windows reproduction only.

No CLI, command profile, environment override, or shared capability-runner API.
Like the artifact manifests, ownership checks protect cooperative repo writers,
not against a hostile owner capable of rewriting this checkout.
"""
from __future__ import annotations

import codecs
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time
import uuid

from wine import prefix as _prefix
from wine.artifacts import CLEANUP_FIELDS, CLEANUP_LINE_BYTES, CLEANUP_MARKER

_LOG_CAP = 16 * 1024 * 1024
_TAIL_CAP = 4000
_LINE_CAP = CLEANUP_LINE_BYTES
_RESPONSE_CAP = 48 * 1024
_LEDGER_CAP = 4 * 1024 * 1024  # Six bounded stages, including JSON-escaped markers/tails.
_MARKER = ".space-windows-repro-v1.json"
_STEPS = ("preflight", "build-windows-from-linux", "package-windows-runtime",
          "verify-windows-outputs", "wine-admission", "wine-fast")
_RUN_NAME = re.compile(r"\d{8}T\d{12}Z-[0-9a-f]{32}")


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _safe_path(path):
    path = Path(os.path.abspath(path))
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise ValueError(f"Symlinked evidence path: {part}")
    return path


def _regular(path):
    info = _safe_path(path).lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
        raise ValueError(f"Not an exclusively owned regular evidence file: {path}")
    return info


def _exclusive(path):
    _safe_path(path)
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600), "wb", buffering=0)


def _atomic(path, value):
    _safe_path(path)
    if path.exists():
        _regular(path)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with _exclusive(temporary) as output:
            pending = memoryview((json.dumps(value, sort_keys=True) + "\n").encode())
            while pending:
                written = output.write(pending)
                if type(written) is not int or not 0 < written <= len(pending):
                    raise OSError(f"Invalid atomic write progress: {written!r}")
                pending = pending[written:]
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path, limit=_LEDGER_CAP):
    if _regular(path).st_size > limit:
        raise ValueError(f"Oversized evidence JSON: {path.name}")
    with path.open("rb") as source:
        return json.load(source)


def _identity(repo):
    return {name: [p.stat().st_dev, p.stat().st_ino]
            for name, p in (("repo", _safe_path(repo)), ("build", _safe_path(repo / "build")))}


def _ownership(repo, run_dir):
    expected_parent = _safe_path(repo / "build/windows-ci-repro")
    _safe_path(run_dir)
    info = run_dir.stat()
    if (run_dir.parent != expected_parent or not _RUN_NAME.fullmatch(run_dir.name)
            or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.geteuid()):
        raise ValueError("Invalid private reproduction directory")
    return {"version": 1, "owner": "space-windows-repro", "run": run_dir.name,
            "identity": _identity(repo), "uid": os.geteuid()}


def _assert_owned(repo, run_dir):
    marker = _read_json(run_dir / _MARKER)
    if (not isinstance(marker, dict) or marker.get("ownership") != _ownership(repo, run_dir)
            or stat.S_IMODE(_regular(run_dir / _MARKER).st_mode) != 0o600):
        raise ValueError("Reproduction ownership changed")
    return marker


def _inventory(run_dir):
    allowed = {"ledger.json"} | {f"{step}.{stream}.log" for step in _STEPS for stream in ("stdout", "stderr")}
    inventory = {}
    for path in run_dir.iterdir():
        if path.name == _MARKER:
            continue
        if path.name not in allowed:
            raise ValueError("Unknown evidence entry; quarantined, not eligible for pruning")
        info = _regular(path)
        if stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > (_LOG_CAP if path.suffix == ".log" else _LEDGER_CAP):
            raise ValueError("Invalid evidence file mode/size")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(65536):
                digest.update(chunk)
        inventory[path.name] = {"size": info.st_size, "sha256": digest.hexdigest()}
    if "ledger.json" not in inventory:
        raise ValueError("Missing run ledger")
    return inventory


def _prune(repo, current_run):
    eligible = []
    for path in (repo / "build/windows-ci-repro").iterdir():
        # Wall-clock ordering is only for the two historical slots. The current
        # run must survive even if its generated timestamp moved backwards.
        if path == current_run:
            continue
        try:
            marker = _assert_owned(repo, path)
            if marker.get("state") != "finalized" or marker.get("files") != _inventory(path):
                continue
            eligible.append(path)
        except (OSError, ValueError, TypeError, KeyError):
            # Includes symlinked, unowned, interrupted and quarantined evidence.
            continue
    for path in sorted(eligible)[:-2]:
        marker = _assert_owned(repo, path)
        if marker["files"] != _inventory(path):
            raise ValueError("Evidence changed before pruning")
        for name in marker["files"]:
            (path / name).unlink()
        (path / _MARKER).unlink()
        path.rmdir()


def _new_run(repo):
    for path in (repo / "build", repo / "build/windows-ci-repro"):
        _safe_path(path).mkdir(mode=0o700, exist_ok=True)
    root = repo / "build/windows-ci-repro"
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ-") + uuid.uuid4().hex
    run_dir = root / name
    run_dir.mkdir(mode=0o700)
    _atomic(run_dir / _MARKER, {"ownership": _ownership(repo, run_dir), "state": "active"})
    _atomic(run_dir / "ledger.json", {"version": 1, "started_utc": _utc(), "complete": False,
                                     "outcome": "started", "stages": [], "metadata": {}})
    return run_dir


class _PersistenceError(Exception):
    """Carry the live ledger across failed storage, never reload stale progress."""

    def __init__(self, ledger):
        super().__init__(ledger["persistence_errors"][-1])
        self.ledger = ledger


def _persistence_failure(ledger, operation, error):
    ledger["complete"] = False
    ledger.setdefault("persistence_errors", []).append(f"{operation}: {type(error).__name__}: {str(error)[:500]}")


def _save(repo, run_dir, ledger):
    if ledger.get("persistence_errors"):
        # Latch the failure: neither capture nor finalization retries broken
        # storage. The live ledger remains available to the bounded response.
        raise _PersistenceError(ledger)
    try:
        _assert_owned(repo, run_dir)
        _atomic(run_dir / "ledger.json", ledger)
    except (OSError, ValueError) as error:
        _persistence_failure(ledger, "ledger checkpoint", error)
        raise _PersistenceError(ledger) from error


def _capture_checkpoint(repo, run_dir, ledger):
    if not ledger.get("persistence_errors"):
        try:
            _save(repo, run_dir, ledger)
        except _PersistenceError:
            # Explicitly retained in memory; _finish propagates it after drain
            # and wait so the real exit status and later progress are not lost.
            return


def _seal(repo, run_dir):
    marker = _assert_owned(repo, run_dir)
    marker.update(state="finalized", files=_inventory(run_dir))
    _atomic(run_dir / _MARKER, marker)
    _prune(repo, run_dir)


def _record(step, args):
    return {"step": step, "args": list(args), "started_utc": _utc(), "started_monotonic": time.monotonic(),
              "finished_utc": None, "finished_monotonic": None, "elapsed_seconds": None,
              "returncode": None, "outcome": "started", "capture_complete": False,
              "capture_errors": [], "cleanup_signals": [],
              "progress": {"counts": dict.fromkeys(("launch", "boot", "load", "run", "pass", "fail", "timing", "admission"), 0),
                           "latest": None, "last_markers": {}, "admission_phases": []}}


def _stream_info(path):
    return {"path": path, "tail": "", "observed_bytes": 0,
            "stored_bytes": 0, "observed_characters": 0, "excerpt_truncated": False,
            "log_truncated": False, "oversized_lines": 0, "max_pending_line_bytes": 0,
            "eof": False, "errors": []}


def _start(repo, run_dir, step, args):
    _assert_owned(repo, run_dir)
    if step not in _STEPS:
        raise ValueError("Unknown fixed reproduction stage")
    ledger = _read_json(run_dir / "ledger.json")
    if any(s["step"] == step for s in ledger["stages"]):
        raise ValueError("Stage already recorded")
    record = _record(step, args)
    logs = {}
    for stream in ("stdout", "stderr"):
        record[stream] = _stream_info((run_dir / f"{step}.{stream}.log").relative_to(repo).as_posix())
    ledger["stages"].append(record)
    try:
        for stream in ("stdout", "stderr"):
            path = run_dir / f"{step}.{stream}.log"
            logs[stream] = _exclusive(path)
        _save(repo, run_dir, ledger)
    except (OSError, ValueError) as error:
        for log in logs.values():
            log.close()
        _persistence_failure(ledger, "stage log creation", error)
        raise _PersistenceError(ledger) from error
    except BaseException:
        for log in logs.values():
            log.close()
        raise
    return ledger, record, logs


def _finish(repo, run_dir, ledger, record, outcome, code, complete):
    end = time.monotonic()
    record.update(finished_utc=_utc(), finished_monotonic=end, elapsed_seconds=end - record["started_monotonic"],
                  outcome=outcome, returncode=code, capture_complete=complete)
    try:
        _save(repo, run_dir, ledger)
    except _PersistenceError:
        record["capture_complete"] = False
        if record["outcome"] == "pass":
            record["outcome"] = "evidence_error"
        raise
    return record


def _marker_line(record, raw, stream):
    # Only newline-terminated, bounded lines are treated as flushed markers.
    text = raw.decode("utf-8", errors="replace").rstrip("\r")
    if record["step"] == "terminal-stop" and text.startswith(CLEANUP_MARKER):
        try:
            value = json.loads(text.removeprefix(CLEANUP_MARKER))
            if (set(value) != CLEANUP_FIELDS
                    or type(value["ok"]) is not bool
                    or any(type(value[k]) is not int and value[k] is not None
                           for k in ("stop_returncode", "wait_returncode"))
                    or not isinstance(value["errors"], list)
                    or len(value["errors"]) > 8
                    or any(not isinstance(e, str) or len(e) > 500 for e in value["errors"])
                    or type(value['error_count']) is not int or value['error_count'] < len(value['errors'])
                    or type(value['errors_truncated']) is not bool
                    or not isinstance(value['error_excerpt_truncated'], list)
                    or len(value['error_excerpt_truncated']) != len(value['errors'])
                    or any(type(flag) is not bool for flag in value['error_excerpt_truncated'])
                    or value['errors_truncated'] != (value['error_count'] > len(value['errors'])
                                                     or any(value['error_excerpt_truncated']))):
                raise ValueError("Invalid cleanup result")
            record["server_result"] = value
        except (ValueError, TypeError):
            record['malformed_cleanup_markers'] = record.get('malformed_cleanup_markers', 0) + 1
            if record['malformed_cleanup_markers'] == 1:
                record["capture_errors"].append("Invalid owned cleanup result marker")
    match = re.match(r"^\[(LAUNCH|BOOT|LOAD|RUN|PASS|FAIL|TIME|TIMINGS)\](?: |$)", text)
    kind = None
    if match:
        kind = {"TIME": "timing", "TIMINGS": "timing"}.get(match[1], match[1].lower())
    elif text.startswith("Wine admission:"):
        kind = "admission"
        phases = record["progress"]["admission_phases"]
        if text.startswith("Wine admission: probe backend="):
            backend = "compat" if "backend=bcryptprimitives=n;" in text else "builtin"
            if len(phases) < 2:
                phases.append({"backend": backend, "returncode": None})
        elif phases and (code := re.match(r"Wine admission: probe exit=(-?\d{1,4})(?!\d)", text)):
            phases[-1]["returncode"] = int(code[1])
    if kind:
        progress = record["progress"]
        marker = {"kind": kind, "text": text, "stream": stream, "observed_utc": _utc(), "observed_monotonic": time.monotonic()}
        progress["counts"][kind] += 1
        progress["latest"] = marker
        progress["last_markers"][kind] = marker


class _Stream:
    def __init__(self, record, name, output, offset=0):
        self.record, self.name, self.output = record, name, output
        self.info = record[name]
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.pending = bytearray()
        self.discard_line = False
        self.write_failed = False
        self.offset = offset

    def _text(self, text):
        self.info["observed_characters"] += len(text)
        self.info["tail"] = (self.info["tail"] + text)[-_TAIL_CAP:]
        self.info["excerpt_truncated"] = self.info["observed_characters"] > _TAIL_CAP

    def feed(self, data):
        info = self.info
        info["observed_bytes"] += len(data)
        if not self.write_failed:
            try:
                saved = data[:max(0, _LOG_CAP - self.offset - info["stored_bytes"])]
                while saved:
                    written = self.output.write(saved)
                    if not written:
                        raise OSError("Short evidence write")
                    info["stored_bytes"] += written
                    saved = saved[written:]
            except OSError as error:
                self.write_failed = True
                message = f"{self.name} log write: {type(error).__name__}: {str(error)[:500]}"
                info["errors"].append(message)
                self.record["capture_errors"].append(message)
        info["log_truncated"] = info["observed_bytes"] > info["stored_bytes"]
        self._text(self.decoder.decode(data))
        # Chunks are <=64KiB; neither a single huge line nor splitlines creates
        # an unbounded pending buffer. Discard an oversized line until newline.
        for index, part in enumerate(data.split(b"\n")):
            if index:
                if not self.discard_line:
                    _marker_line(self.record, bytes(self.pending), self.name)
                self.pending.clear()
                self.discard_line = False
            if not self.discard_line:
                if len(self.pending) + len(part) > _LINE_CAP:
                    self.pending.clear()
                    self.discard_line = True
                    info["oversized_lines"] += 1
                else:
                    self.pending.extend(part)
                    info["max_pending_line_bytes"] = max(info["max_pending_line_bytes"], len(self.pending))

    def eof(self):
        self._text(self.decoder.decode(b"", final=True))
        self.info["eof"] = True


def _read_pipe(fd):
    return os.read(fd, 65536)


def _signal_group(proc, sig, record):
    try:
        os.killpg(proc.pid, sig)
        record["cleanup_signals"].append(sig.name)
    except ProcessLookupError:
        pass


def _stop_group(proc, record):
    _signal_group(proc, signal.SIGTERM, record)
    # Do not use proc.wait(timeout) alone: the leader can already have exited
    # while an owned descendant ignores TERM and retains the pipe handles.
    until = time.monotonic() + 2
    while time.monotonic() < until:
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(.05)
    _signal_group(proc, signal.SIGKILL, record)
    proc.wait()


def _capture(repo, run_dir, ledger, record, logs, args, session=None, *, persist=True, offsets=None):
    proc = None
    selector = selectors.DefaultSelector()
    streams = {name: _Stream(record, name, output, (offsets or {}).get(name, 0)) for name, output in logs.items()}
    outcome = None
    try:
        env = dict(os.environ)
        if session is not None:
            session.validate()
            env.update(session.environment(), SPACE_WINE_SESSION_ID=session.id)
        env.update(TEST_VERBOSE="1", SPACE_TEST_TIMINGS="1")
        proc = subprocess.Popen(args, cwd=repo, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True,
                                close_fds=True, env=env)
        for name in streams:
            pipe = getattr(proc, name)
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, streams[name])
        leader_exited = None
        checkpoint = time.monotonic()
        while selector.get_map():
            now = time.monotonic()
            if proc.poll() is not None:
                if leader_exited is None:
                    leader_exited = now
                if now - leader_exited >= 2:
                    record["capture_errors"].append("Descendant-held pipes exceeded 2s EOF grace; forced closure")
                    outcome = "capture_error"
                    break
            for key, _ in selector.select(.1):
                try:
                    data = _read_pipe(key.fd)
                except BlockingIOError:
                    continue
                if data:
                    key.data.feed(data)
                else:
                    key.data.eof()
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
            if persist and time.monotonic() - checkpoint >= .25:
                _capture_checkpoint(repo, run_dir, ledger)
                checkpoint = time.monotonic()
        if outcome is None:
            # EOF may precede a long shutdown before the periodic checkpoint.
            # Persist the observed markers/EOF flags while the leader is alive.
            if persist:
                _capture_checkpoint(repo, run_dir, ledger)
            # Pipes may close long before the process exits. Blocking wait, not
            # a zero-FD selector/status-spin, preserves both status and CPU.
            proc.wait()
    except (KeyboardInterrupt, InterruptedError):
        outcome = "interrupted"
        record["capture_errors"].append("KeyboardInterrupt during reproduction capture")
    except Exception as error:
        outcome = "launch_error" if proc is None else "capture_error"
        record["capture_errors"].append(f"{type(error).__name__}: {str(error)[:500]}")
    finally:
        if proc is not None and outcome is not None:
            with _prefix.cleanup_signals():
                _stop_group(proc, record)
        # Drain what is immediately available after cleanup, without another
        # grace or relying on descendants to close their copies of the pipes.
        for key in list(selector.get_map().values()):
            try:
                # An escaped descendant could keep writing even after group
                # cleanup. Final drain is bounded too, then close our pipes.
                until = time.monotonic() + .1
                data = b""
                for _ in range(64):
                    if time.monotonic() >= until:
                        break
                    data = os.read(key.fd, 65536)
                    if not data:
                        key.data.eof()
                        break
                    key.data.feed(data)
            except (OSError, ValueError):
                pass
            key.fileobj.close()
        selector.close()
        for output in logs.values():
            output.close()
    code = proc.returncode if proc is not None else None
    complete = outcome is None and not record["capture_errors"] and all(s["eof"] for s in (record["stdout"], record["stderr"]))
    outcome = outcome or ("capture_error" if not complete else "timeout" if code == 124 else "pass" if code == 0 else "nonzero_exit")
    if outcome == "pass" and record["step"] == "wine-fast" and record["progress"]["counts"]["fail"]:
        outcome = "inconsistent_result"  # Keep actual code 0, but never a contradictory runner PASS.
    if persist:
        return _finish(repo, run_dir, ledger, record, outcome, code, complete)
    end = time.monotonic()
    record.update(finished_utc=_utc(), finished_monotonic=end, elapsed_seconds=end - record["started_monotonic"],
                  outcome=outcome, returncode=code, capture_complete=complete)
    return record


class _UnavailableLog:
    def write(self, data):
        raise OSError("Owned cleanup log unavailable; retained in memory")

    def close(self):
        pass


def _cleanup_capture(repo, run_dir, stage, args, session):
    """Append within the existing stage caps, even when ledger storage failed.

    Separate stream records never change the primary capture's EOF/completeness.
    A missing/unsafe log is explicit, but cannot suppress owned terminal cleanup.
    """
    record = _record("terminal-stop", args)
    logs, offsets = {}, {}
    for name in ("stdout", "stderr"):
        path = run_dir / f'{stage["step"]}.{name}.log'
        record[name] = _stream_info(path.relative_to(repo).as_posix())
        try:
            _assert_owned(repo, run_dir)
            info = _regular(path)
            if stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > _LOG_CAP:
                raise ValueError("Invalid cleanup log mode/size")
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
            opened = os.fstat(fd)
            if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                os.close(fd)
                raise ValueError("Cleanup log substituted")
            logs[name] = os.fdopen(fd, "wb", buffering=0)
            offsets[name] = info.st_size
        except (OSError, ValueError) as error:
            record["capture_errors"].append(f"{name} cleanup log: {str(error)[:500]}")
            logs[name] = _UnavailableLog()
    return _capture(repo, run_dir, {}, record, logs, args, session, persist=False, offsets=offsets)


def _bounded_response(result):
    """Bound the *encoded whole response*, including JSON control/Unicode escapes.

    Preserve every stage, counter, outcome, timestamp, error and log pointer.
    Compact successful excerpts first, then other excerpts/marker text/metadata.
    The owned ledger remains the richer source of truth.
    """
    result = copy.deepcopy(result)
    evidence = result["evidence"]
    evidence["response_truncated"] = False

    def size():
        return len(json.dumps(result, sort_keys=True).encode("utf-8"))

    def excerpts(stage, tail_limit, marker_limit):
        for name in ("stdout", "stderr"):
            stream = stage[name]
            tail = stream["tail"]
            if len(tail) > tail_limit:
                stream["tail"] = tail[-tail_limit:] if tail_limit else ""
                stream["response_excerpt_truncated"] = True
                evidence["response_truncated"] = True
        progress = stage["progress"]
        for marker in [progress["latest"], *progress["last_markers"].values()]:
            if marker and len(marker["text"]) > marker_limit:
                marker["text"] = marker["text"][:marker_limit]
                marker["response_text_truncated"] = True
                evidence["response_truncated"] = True

    stages = [capture for stage in evidence.get("stages", [])
              for capture in (stage, *stage.get("cleanup", {}).get("attempts", []))]
    # Exhaust compaction of success excerpts BEFORE touching failure context.
    for tail_limit, marker_limit in ((512, 128), (0, 32)):
        for stage in stages:
            if size() <= _RESPONSE_CAP:
                return result
            if stage["outcome"] == "pass":
                excerpts(stage, tail_limit, marker_limit)
    # Allowlisted path/version metadata can itself be long (e.g. a 4KiB root).
    # Fixed stage log pointers are repo-relative and never subject to this cut.
    def compact(value):
        if isinstance(value, str):
            return value[:128]
        if isinstance(value, dict):
            return {key: compact(v) for key, v in value.items()}
        if isinstance(value, list):
            return [compact(v) for v in value]
        return value
    if size() > _RESPONSE_CAP:
        evidence["metadata"] = compact(evidence.get("metadata", {}))
        for stage in stages:
            if "details" in stage:
                stage["details"] = compact(stage["details"])
        if "details" in evidence:
            evidence["details"] = compact(evidence["details"])
        if "error" in evidence:
            evidence["error"] = compact(evidence["error"])
        evidence["response_truncated"] = True
    for stage in stages:
        if size() <= _RESPONSE_CAP:
            return result
        if stage["outcome"] != "pass":
            excerpts(stage, 512, 128)
    if size() > _RESPONSE_CAP:
        raise ValueError("Fixed reproduction evidence exceeded encoded response budget")
    return result
