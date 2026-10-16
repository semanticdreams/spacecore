"""Artifact tests use a fake repository/dispatcher, NEVER a real Wine process."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
MARKER = ".space-windows-artifact-v1.json"


def hashes(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file()}


class Fixture:
    def __init__(self, path):
        self.root = path / "repo"
        scripts = self.root / "scripts"
        scripts.mkdir(parents=True)
        for source in (ROOT / "scripts").glob("*.sh"):
            shutil.copy2(source, scripts)
        if (ROOT / "scripts/wine").exists():
            shutil.copytree(ROOT / "scripts/wine", scripts / "wine")
        shutil.copytree(ROOT / "external/date/tzdata", self.root / "external/date/tzdata")
        manifest = self.root / "external/temporal/libical/DEPENDENCY_MANIFEST.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{"fixture":true}')
        self.build = self.root / "build/windows"
        self.build.mkdir(parents=True)
        for name in ("space.exe", "space-cli.exe", "runtime.dll", "bcryptprimitives.dll", "BCryptPrimitives.DLL"):
            (self.build / name).write_text("unsafe-old-no-op" if "primitives" in name.lower() else name)
        assets = self.root / "assets/lua"
        assets.mkdir(parents=True)
        (assets / "fixture.fnl").write_text("packaged-assets")
        self.dist = self.root / "build/dist/windows"
        self.overlay = self.root / "build/wine/windows"
        self.bin = path / "bin"
        self.bin.mkdir()
        self.log = path / "calls.jsonl"
        self.codes = path / "codes.json"
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        FIXTURE_LOG=str(self.log), FIXTURE_CODES=str(self.codes),
                        WINE_CMD=str(self.bin / "fake-wine"), WINEPREFIX=str(path / "unchanged-prefix"),
                        DISPLAY=":fixture", CC="x86_64-w64-mingw32-gcc-posix")
        self.write_executable("x86_64-w64-mingw32-objdump", "#!/bin/sh\nexit 0\n")
        self.write_executable("x86_64-w64-mingw32-gcc-posix", '''#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
if args[0].startswith('-print-file-name='):
    print(args[0].split('=', 1)[1]); sys.exit(0)
with open(os.environ['FIXTURE_LOG'], 'a') as f: f.write(json.dumps({'cc':args})+'\\n')
pathlib.Path(args[args.index('-o')+1]).write_text('fixture PE, not executable')
''')
        self.write_executable("fake-wine", '''#!/usr/bin/python3
import json, os, pathlib, sys
if sys.argv[1:] == ['--version']:
    print('fixture-only Wine dispatcher'); sys.exit(0)
with open(os.environ['FIXTURE_LOG'], 'a') as f:
    f.write(json.dumps({'wine':sys.argv[1:], 'env':{k:os.environ.get(k) for k in
        ['WINEDLLOVERRIDES','WINEPREFIX','DISPLAY','SPACE_ASSETS_PATH','SPACE_BIN','FENNEL_PATH','FENNEL_MACRO_PATH']}})+'\\n')
if pathlib.Path(sys.argv[1]).name == 'process-prng-probe.exe':
    p = pathlib.Path(os.environ['FIXTURE_CODES']); codes = json.loads(p.read_text())
    code = codes.pop(0); p.write_text(json.dumps(codes)); sys.exit(code)
sys.exit(0)
''')
        self.write_executable("timeout", '''#!/usr/bin/python3
import json, os, sys
args = sys.argv[1:]
kill_after = args.pop(0) if args[0].startswith('--kill-after=') else None
with open(os.environ['FIXTURE_LOG'], 'a') as f:
    f.write(json.dumps({'timeout':args[0], 'kill_after':kill_after})+'\\n')
os.execvp(args[1], args[1:])
''')

    def write_executable(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)

    def run(self, script, *args):
        return subprocess.run(["bash", str(self.root / "scripts" / script), *map(str, args)],
                              cwd=self.root, env=self.env, text=True, capture_output=True)

    def package(self):
        result = self.run("package-windows-runtime.sh")
        assert result.returncode == 0, result.stderr

    def prepare(self, codes):
        self.codes.write_text(json.dumps(codes))
        return self.run("prepare-windows-wine-runtime.sh")

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []


@pytest.fixture
def runtime(tmp_path):
    return Fixture(tmp_path)


def test_repeat_packaging_excludes_stale_helpers_and_wine_never_mutates_native(runtime):
    runtime.package()
    assert not any(p.name.casefold() == "bcryptprimitives.dll" for p in runtime.dist.rglob("*"))
    before = hashes(runtime.build), hashes(runtime.dist)
    assert runtime.prepare([10, 0]).returncode == 0
    assert (runtime.overlay / "bcryptprimitives.dll").is_file()
    assert (runtime.overlay / "assets/lua/fixture.fnl").read_text() == "packaged-assets"
    assert before == (hashes(runtime.build), hashes(runtime.dist))
    runtime.package()
    assert not any(p.name.casefold() == "bcryptprimitives.dll" for p in runtime.dist.rglob("*"))
    assert (runtime.build / "bcryptprimitives.dll").read_text() == "unsafe-old-no-op"
    assert (runtime.build / "BCryptPrimitives.DLL").read_text() == "unsafe-old-no-op"


@pytest.mark.parametrize("prior_package", [True, False])
def test_make_wine_target_packages_current_executables_and_assets(runtime, prior_package):
    shutil.copy2(ROOT / "Makefile", runtime.root / "Makefile")
    # Never allow this host-only fixture to initiate an application cross-build.
    for name in ("build-windows-from-linux.sh", "build-windows.sh"):
        (runtime.root / "scripts" / name).write_text("#!/bin/sh\nexit 99\n")
    runtime.write_executable("cmake", "#!/bin/sh\nexit 99\n")
    if prior_package:
        runtime.package()  # Package A, before the current build/asset change B.
    for name in ("space.exe", "space-cli.exe"):
        (runtime.build / name).write_text("build-B")
    (runtime.root / "assets/lua/fixture.fnl").write_text("assets-B")
    runtime.codes.write_text('[0]')
    result = subprocess.run(["make", "test-windows-wine"], cwd=runtime.root,
                            env=runtime.env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    for tree in (runtime.dist, runtime.overlay):
        for name in ("space.exe", "space-cli.exe"):
            assert (tree / name).read_text() == "build-B"
        assert (tree / "assets/lua/fixture.fnl").read_text() == "assets-B"
    assert [c for c in runtime.calls() if "wine" in c][-1]["wine"] == [
        str(runtime.overlay / "space-cli.exe"), "-m", "tests.fast:main"]


@pytest.mark.parametrize("code", [1, 20, 124, 139, 127])
def test_only_confirmed_absence_permits_fallback(runtime, code):
    runtime.package()
    result = runtime.prepare([code])
    assert result.returncode != 0
    assert not any("process_prng_compat.c" in " ".join(c.get("cc", [])) for c in runtime.calls())
    assert not (runtime.overlay / "admission.json").exists()


@pytest.mark.parametrize("second", [10, 20, 124, 139])
def test_absence_retries_once_and_second_failure_never_admits(runtime, second):
    runtime.package()
    result = runtime.prepare([10, second])
    assert result.returncode != 0
    assert len([c for c in runtime.calls() if "wine" in c]) == 2
    assert not (runtime.overlay / "admission.json").exists()


def test_builtin_success_never_builds_bridge_and_app_uses_receipt(runtime):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    result = runtime.run("test-windows-under-wine.sh")
    assert result.returncode == 0, result.stderr
    calls = runtime.calls()
    probes, app = [c for c in calls if "wine" in c]
    assert probes["env"]["WINEDLLOVERRIDES"] == "bcryptprimitives=b;advapi32,cryptbase=b"
    assert app["env"]["WINEDLLOVERRIDES"] == probes["env"]["WINEDLLOVERRIDES"]
    assert app["env"]["WINEPREFIX"] == probes["env"]["WINEPREFIX"]
    assert app["env"]["DISPLAY"] == ":fixture"
    assert app["wine"] == [str(runtime.overlay / "space-cli.exe"), "-m", "tests.fast:main"]
    assert app["env"]["SPACE_ASSETS_PATH"] == str(runtime.overlay / "assets")
    assert app["env"]["SPACE_BIN"] == str(runtime.overlay / "space-cli.exe")
    assert str(runtime.overlay / "assets/lua") in app["env"]["FENNEL_PATH"]
    assert app["env"]["FENNEL_PATH"] == app["env"]["FENNEL_MACRO_PATH"]
    assert [c["timeout"] for c in calls if "timeout" in c] == ["60s", "180s"]
    assert [c["kill_after"] for c in calls if "timeout" in c] == ["--kill-after=5s", None]
    assert not (runtime.overlay / "bcryptprimitives.dll").exists()


def test_compat_selection_is_fixed_and_receipt_is_not_shell(runtime):
    runtime.package()
    assert runtime.prepare([10, 0]).returncode == 0
    runtime.env["WINEDLLOVERRIDES"] = "malicious=inherited"
    assert runtime.run("test-windows-under-wine.sh").returncode == 0
    wine = [c for c in runtime.calls() if "wine" in c]
    assert [c["env"]["WINEDLLOVERRIDES"] for c in wine] == [
        "bcryptprimitives=b;advapi32,cryptbase=b", "bcryptprimitives=n;advapi32,cryptbase=b",
        "bcryptprimitives=n;advapi32,cryptbase=b"]
    receipt = runtime.overlay / "admission.json"
    receipt.write_text('$(touch must-not-execute)')
    assert runtime.run("test-windows-under-wine.sh").returncode != 0
    assert not (runtime.root / "must-not-execute").exists()


def test_legacy_standard_package_is_preserved_including_unsafe_helper(runtime):
    runtime.dist.mkdir(parents=True)
    for name in ("space.exe", "space-cli.exe", "bcryptprimitives.dll", "unrelated-sentinel"):
        (runtime.dist / name).write_text(name)
    before = hashes(runtime.dist)
    runtime.package()
    saved = runtime.dist.with_name("windows.pre-diagnostics")
    assert hashes(saved) == before
    assert not (runtime.dist / "bcryptprimitives.dll").exists()


@pytest.mark.parametrize("kind", ["collision", "ambiguous", "unknown-owned-entry", "modified-owned-file"])
def test_no_unverified_output_is_removed(runtime, kind):
    if kind in ("unknown-owned-entry", "modified-owned-file"):
        runtime.package()
        target = runtime.dist / ("sentinel" if kind == "unknown-owned-entry" else "space.exe")
        target.write_text("preserve")
    else:
        runtime.dist.mkdir(parents=True)
        (runtime.dist / "sentinel").write_text("preserve")
        if kind == "collision":
            (runtime.dist / "space.exe").write_text("exe")
            (runtime.dist / "space-cli.exe").write_text("exe")
            runtime.dist.with_name("windows.pre-diagnostics").mkdir()
    before = hashes(runtime.dist)
    result = runtime.run("package-windows-runtime.sh")
    assert result.returncode != 0
    assert hashes(runtime.dist) == before


@pytest.mark.parametrize("relative", ["build/dist", "build/dist/windows", "build/wine", "build/wine/windows"])
def test_symlinked_outputs_fail_without_mutation(runtime, tmp_path, relative):
    external = tmp_path / "external"
    external.mkdir()
    (external / "sentinel").write_text("keep")
    if "wine" in relative:
        runtime.package()
    target = runtime.root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(external, target_is_directory=True)
    before = hashes(external), hashes(runtime.build)
    result = runtime.prepare([0]) if "wine" in relative else runtime.run("package-windows-runtime.sh")
    assert result.returncode != 0
    assert before == (hashes(external), hashes(runtime.build))


def test_overlay_unknown_entry_and_package_tampering_are_not_overwritten(runtime):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    (runtime.overlay / "sentinel").write_text("preserve")
    assert runtime.prepare([0]).returncode != 0
    assert (runtime.overlay / "sentinel").read_text() == "preserve"
    (runtime.dist / "space.exe").write_text("tampered")
    assert runtime.run("test-windows-under-wine.sh").returncode != 0


def test_probe_cannot_silently_claim_new_or_modified_overlay_files(runtime):
    runtime.package()
    runtime.write_executable("fake-wine", f'''#!/usr/bin/python3
import pathlib, sys
if sys.argv[1:] == ['--version']:
    print('fixture-only'); sys.exit(0)
pathlib.Path({str(runtime.overlay / 'unrelated-sentinel')!r}).write_text('preserve')
sys.exit(0)
''')
    assert runtime.prepare([0]).returncode != 0
    assert not (runtime.overlay / "admission.json").exists()
    assert runtime.prepare([0]).returncode != 0
    assert (runtime.overlay / "unrelated-sentinel").read_text() == "preserve"


def test_no_args_interfaces_reject_paths_and_builder_cannot_create_native_helper(runtime):
    before = hashes(runtime.build)
    for name in ("prepare-windows-wine-runtime.sh", "build-wine-bcryptprimitives-compat.sh"):
        assert runtime.run(name, runtime.build / "bcryptprimitives.dll").returncode != 0
    assert before == hashes(runtime.build)
    assert runtime.run("build-wine-bcryptprimitives-compat.sh").returncode != 0


def test_standalone_builder_never_grants_admission(runtime):
    runtime.package()
    before = hashes(runtime.build), hashes(runtime.dist)
    assert runtime.prepare([20]).returncode != 0
    assert runtime.run("build-wine-bcryptprimitives-compat.sh").returncode == 0
    assert runtime.run("test-windows-under-wine.sh").returncode != 0
    assert before == (hashes(runtime.build), hashes(runtime.dist))


def test_real_mingw_compilation_of_tiny_bridge_and_probe(tmp_path):
    cc = shutil.which("x86_64-w64-mingw32-gcc-posix")
    assert cc, "Task 1 requires actual MinGW fixture compilation (no PE execution)"
    for source, flags, output in [
        ("process_prng_compat.c", ["-shared", "-ladvapi32"], "bcryptprimitives.dll"),
        ("probe.c", [], "probe.exe"),
    ]:
        result = subprocess.run([cc, "-Wall", "-Wextra", "-Werror", "-o", str(tmp_path / output),
                                 str(ROOT / "scripts/wine" / source), *flags], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert (tmp_path / output).read_bytes()[:2] == b"MZ"
        if source == "process_prng_compat.c":
            imports = subprocess.run(["x86_64-w64-mingw32-objdump", "-p", str(tmp_path / output)],
                                     check=True, capture_output=True, text=True).stdout
            assert "dll name: advapi32.dll" in imports.lower()
            assert "SystemFunction036" in imports
            assert "ProcessPrng" in imports
            assert "TerminateProcess" in imports
            assert "GetCurrentProcess" in imports


def compile_host(tmp_path, source, *extra):
    output = tmp_path / source
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "scripts/tests/wine_adapters"),
                    "-I", str(ROOT / "scripts/wine"), *extra,
                    str(ROOT / "scripts/tests/wine_adapters" / f"{source}.c"),
                    "-o", str(output)], check=True, capture_output=True, text=True)
    return output


@pytest.mark.parametrize("mode,code,chunks", [
    ("normal", 0, [7, 7, 2]), ("fail-second", 20, [7, 7]),
    ("zero", 0, []), ("null", 20, []),
])
def test_real_bridge_loop_with_deterministic_host_adapter(tmp_path, mode, code, chunks):
    exe = compile_host(tmp_path, "bridge", "-DPROCESS_PRNG_CHUNK_MAX=7")
    result = subprocess.run([str(exe), mode], capture_output=True, text=True)
    assert result.returncode == code, result.stderr
    assert [int(s.split("=")[1]) for s in result.stdout.splitlines() if s.startswith("chunk=")] == chunks
    assert ("success" in result.stdout) == (code == 0)
    assert ("backend unresolved/failed" in result.stderr) == (code != 0)
    assert ("terminate=current-process code=20" in result.stdout) == (code != 0)


def test_bridge_never_returns_if_hard_termination_unexpectedly_returns(tmp_path):
    import resource
    exe = compile_host(tmp_path, "bridge", "-DPROCESS_PRNG_CHUNK_MAX=7")

    def no_core_dump():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    result = subprocess.run([str(exe), "terminate-returns"], capture_output=True, text=True,
                            preexec_fn=no_core_dump, timeout=2)
    assert result.returncode < 0, result.stdout + result.stderr
    assert "terminate=current-process code=20" in result.stdout
    assert "success" not in result.stdout


@pytest.mark.parametrize("mode,code", [
    ("normal", 0), ("no-op", 20), ("partial", 20), ("odd-partial", 20),
    ("repeat", 20), ("stuck", 20), ("guard", 20), ("zero-damage", 20),
    ("false", 20), ("wrong-owner", 20), ("wrong-name", 20), ("wrong-name-export", 20),
    ("long-name", 20), ("missing-name", 20), ("wrong-directory", 20),
    ("load-126", 10), ("load-5", 20), ("load-193", 20), ("load-1114", 20),
    ("export-127", 10), ("export-5", 20),
])
def test_real_probe_logic_with_host_api_adapter(tmp_path, mode, code):
    exe = compile_host(tmp_path, "probe", str(ROOT / "scripts/wine/probe.c"))
    result = subprocess.run([str(exe)], env=dict(os.environ, PROBE_FIXTURE=mode,
                                                WINEDLLOVERRIDES="bcryptprimitives=b;advapi32,cryptbase=b"),
                            capture_output=True, text=True)
    assert result.returncode == code, result.stdout + result.stderr
    if code == 0:
        assert [s for s in result.stdout.splitlines() if s.startswith("fixture-request=")] == [
            "fixture-request=65536", "fixture-request=65536", "fixture-request=65539",
            "fixture-request=0", "fixture-request=0"]


def test_probe_compat_identity_uses_own_overlay_directory(tmp_path):
    exe = compile_host(tmp_path, "probe", str(ROOT / "scripts/wine/probe.c"))
    result = subprocess.run([str(exe)], env=dict(os.environ, PROBE_FIXTURE="normal",
                                                WINEDLLOVERRIDES="bcryptprimitives=n;advapi32,cryptbase=b"),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("change", ["prefix", "display", "wine", "app", "helper", "package"])
def test_receipt_rejects_changed_runtime_conditions_and_payload(runtime, change):
    runtime.package()
    assert runtime.prepare([10, 0]).returncode == 0
    if change == "prefix":
        runtime.env["WINEPREFIX"] += "-other"
    elif change == "display":
        runtime.env["DISPLAY"] = ":other"
    elif change == "wine":
        runtime.write_executable("other-wine", "#!/bin/sh\nexit 0\n")
        runtime.env["WINE_CMD"] = str(runtime.bin / "other-wine")
    else:
        path = {"app": runtime.overlay / "space-cli.exe", "helper": runtime.overlay / "bcryptprimitives.dll",
                "package": runtime.dist / "space.exe"}[change]
        path.write_text("modified")
    before = len([c for c in runtime.calls() if "wine" in c])
    assert runtime.run("test-windows-under-wine.sh").returncode != 0
    assert len([c for c in runtime.calls() if "wine" in c]) == before


@pytest.mark.parametrize("explicit_prefix", [False, True])
def test_receipt_binds_effective_prefix_without_reading_home(runtime, explicit_prefix):
    if not explicit_prefix:
        runtime.env.pop("WINEPREFIX", None)
    home_a = runtime.root / "nonexistent-home-A"
    home_b = runtime.root / "nonexistent-home-B"
    runtime.env["HOME"] = str(home_a)
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    before = len([c for c in runtime.calls() if "wine" in c])
    runtime.env["HOME"] = str(home_b)
    result = runtime.run("test-windows-under-wine.sh")
    if explicit_prefix:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert len([c for c in runtime.calls() if "wine" in c]) == before
    receipt = json.loads((runtime.overlay / "admission.json").read_text())
    assert receipt["conditions"]["effective_prefix"] == (
        runtime.env["WINEPREFIX"] if explicit_prefix else str(home_a / ".wine"))
    assert not home_a.exists() and not home_b.exists()


def test_relative_selected_wine_is_same_identity_at_admission_and_consumption(runtime):
    tools = runtime.root / "tools"
    tools.mkdir()
    shutil.copy2(runtime.bin / "fake-wine", tools / "wine")
    runtime.env["WINE_CMD"] = "./tools/wine"
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    result = runtime.run("test-windows-under-wine.sh")
    assert result.returncode == 0, result.stderr
    receipt = json.loads((runtime.overlay / "admission.json").read_text())
    assert receipt["wine"]["executable"] == str(tools / "wine")
    # Same name/version is not enough: a changed binary must still invalidate it.
    with (tools / "wine").open("a") as executable:
        executable.write("\n# changed fixture executable\n")
    before = len([c for c in runtime.calls() if "wine" in c])
    assert runtime.run("test-windows-under-wine.sh").returncode != 0
    assert len([c for c in runtime.calls() if "wine" in c]) == before


def test_selected_wine_resolves_symlink_before_parent_directory(runtime):
    tools = runtime.root / "tools"
    versions = runtime.root / "versions"
    tools.mkdir()
    (versions / "active").mkdir(parents=True)
    (tools / "alias").symlink_to(versions / "active", target_is_directory=True)
    dispatcher = (runtime.bin / "fake-wine").read_text()
    for directory, identity in ((versions, "filesystem-selected"), (tools, "lexical-decoy")):
        executable = directory / "wine"
        executable.write_text(dispatcher.replace("fixture-only Wine dispatcher", f"fixture-only {identity}")
                              .replace("'wine':sys.argv[1:]", f"'selected':{identity!r}, 'wine':sys.argv[1:]"))
        executable.chmod(0o755)
    # Kernel lookup follows alias -> versions/active, THEN '..' -> versions.
    # Both targets exist, so lexical abspath would silently select the decoy.
    runtime.env["WINE_CMD"] = str(tools / "alias" / ".." / "wine")
    before_executables = hashes(versions), hashes(tools)
    expected = {"executable": str(versions / "wine"),
                "version": "fixture-only filesystem-selected",
                "sha256": hashlib.sha256((versions / "wine").read_bytes()).hexdigest()}
    assert expected["sha256"] != hashlib.sha256((tools / "wine").read_bytes()).hexdigest()
    runtime.package()
    before_native = hashes(runtime.build), hashes(runtime.dist)
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stderr
    receipt = (runtime.overlay / "admission.json").read_bytes()
    assert json.loads(receipt)["wine"] == expected
    result = runtime.run("test-windows-under-wine.sh")
    assert result.returncode == 0, result.stderr
    assert [c["selected"] for c in runtime.calls() if "wine" in c] == [
        "filesystem-selected", "filesystem-selected"]
    assert (runtime.overlay / "admission.json").read_bytes() == receipt
    assert before_executables == (hashes(versions), hashes(tools))
    assert before_native == (hashes(runtime.build), hashes(runtime.dist))


def test_term_ignoring_host_probe_is_killed_and_never_admitted(runtime):
    runtime.package()
    real_timeout = shutil.which("timeout", path=os.defpath)
    assert real_timeout, "GNU timeout is required for the host kill-escalation fixture"
    timeout_pid = runtime.root / "fixture-timeout.pid"
    term_received = runtime.root / "fixture-term-received"
    # This fixture adapter ONLY shortens the production timeout arguments; the
    # actual GNU timeout and actual TERM-ignoring host process do the signaling.
    # No production execution mode, test-budget option or Wine process is added.
    runtime.write_executable("timeout", f'''#!/usr/bin/python3
import os, pathlib, sys
args = sys.argv[1:]
assert '60s' in args
args = ['0.2s' if a == '60s' else '--kill-after=0.2s' if a == '--kill-after=5s' else a for a in args]
pathlib.Path({str(timeout_pid)!r}).write_text(str(os.getpid()))
os.execv({real_timeout!r}, [{real_timeout!r}, *args])
''')
    runtime.write_executable("fake-wine", f'''#!/usr/bin/python3
import pathlib, signal, sys, time
if sys.argv[1:] == ['--version']:
    print('fixture-only TERM-ignoring host'); sys.exit(0)
def ignore_term(signum, frame):
    pathlib.Path({str(term_received)!r}).write_text('TERM ignored')
signal.signal(signal.SIGTERM, ignore_term)
while True: time.sleep(0.05)
''')
    started = time.monotonic()
    process = subprocess.Popen(["bash", str(runtime.root / "scripts/prepare-windows-wine-runtime.sh")],
                               cwd=runtime.root, env=runtime.env, start_new_session=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    completed = False
    try:
        stdout, stderr = process.communicate(timeout=3)
        completed = True
    except subprocess.TimeoutExpired:
        # Independent test watchdog cleans up the RED implementation too.
        for group in ([int(timeout_pid.read_text())] if timeout_pid.exists() else []) + [process.pid]:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        stdout, stderr = process.communicate(timeout=3)
    assert completed, "TERM-ignoring host probe exceeded watchdog; kill escalation missing"
    assert time.monotonic() - started < 3
    assert term_received.read_text() == "TERM ignored"
    assert process.returncode != 0, stdout + stderr
    # Python reports a signal-killed timeout process as -9; a shell wrapper may
    # normalize the same SIGKILL status to137. Both must be recorded as failure.
    assert any(f"probe exit={code}" in stdout for code in (-signal.SIGKILL, 137)), stdout + stderr
    assert "forced" in stdout and "timeout" in stdout
    assert not (runtime.overlay / "admission.json").exists()
    assert not (runtime.overlay / "bcryptprimitives.dll").exists()
    assert not any("process_prng_compat.c" in " ".join(c.get("cc", [])) for c in runtime.calls())


@pytest.mark.parametrize("where", ["native", "overlay", "assets"])
def test_linked_entries_are_never_copied_or_removed(runtime, tmp_path, where):
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("preserve")
    if where == "native":
        (runtime.build / "runtime.dll").unlink()
        (runtime.build / "runtime.dll").symlink_to(sentinel)
        result = runtime.run("package-windows-runtime.sh")
    elif where == "assets":
        (runtime.root / "assets/linked").symlink_to(sentinel)
        result = runtime.run("package-windows-runtime.sh")
    else:
        runtime.package()
        assert runtime.prepare([0]).returncode == 0
        (runtime.overlay / "linked").symlink_to(sentinel)
        result = runtime.prepare([0])
    assert result.returncode != 0
    assert sentinel.read_text() == "preserve"


def test_unowned_arbitrary_package_argument_is_not_removed(runtime, tmp_path):
    output = tmp_path / "unowned"
    output.mkdir()
    (output / "sentinel").write_text("keep")
    assert runtime.run("package-windows-runtime.sh", output).returncode != 0
    assert (output / "sentinel").read_text() == "keep"


def test_forbidden_helper_in_packaged_assets_fails_final_verification(runtime):
    (runtime.root / "assets/BCryptPrimitives.DLL").write_text("hidden helper")
    assert runtime.run("package-windows-runtime.sh").returncode != 0
    assert not runtime.dist.exists()


def test_workflow_smoke_executes_admitted_overlay_under_same_configuration(runtime):
    import yaml
    runtime.package()
    for name in ("build.yml", "windows.yml"):
        assert runtime.prepare([10, 0]).returncode == 0
        workflow = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
        step = next(s for s in workflow["jobs"]["build-windows"]["steps"] if s.get("name", "").startswith("Smoke test Windows"))
        # Execute just the real shared configuration + existing smoke command;
        # objdump/rg are independent subsystem checks, not Wine dispatch.
        smoke = step["run"][step["run"].index('ROOT_DIR="${GITHUB_WORKSPACE}"'):]
        result = subprocess.run(["bash", "-euc", smoke], cwd=runtime.root,
                                env=dict(runtime.env, GITHUB_WORKSPACE=str(runtime.root)),
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        app = [c for c in runtime.calls() if "wine" in c][-1]
        assert app["wine"] == [str(runtime.overlay / "space-cli.exe"), "--help"]
        assert app["env"]["WINEDLLOVERRIDES"] == "bcryptprimitives=n;advapi32,cryptbase=b"
        assert app["env"]["WINEPREFIX"] == runtime.env["WINEPREFIX"]
        assert app["env"]["SPACE_ASSETS_PATH"] == str(runtime.overlay / "assets")
        assert [c for c in runtime.calls() if "timeout" in c][-1]["timeout"] == "60s"


def test_prepare_and_app_consumption_serialize_with_artifact_writers(runtime):
    import fcntl
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    # Block the fixture application after configuration and prove a second
    # package writer cannot enter while the consumer holds build/'s inode lock.
    runtime.write_executable("fake-wine", '''#!/usr/bin/python3
import fcntl, os, pathlib, sys
if sys.argv[1:] == ['--version']:
    print('fixture-only Wine dispatcher'); sys.exit(0)
root = pathlib.Path(os.environ['FIXTURE_ROOT'])
fd = os.open(root/'build', os.O_RDONLY | os.O_DIRECTORY)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(0)
sys.exit(77)
''')
    # Refresh the receipt for this deliberately changed fake dispatcher.
    # Its probe also verifies preparation holds the same lock.
    runtime.env["FIXTURE_ROOT"] = str(runtime.root)
    assert runtime.prepare([0]).returncode == 0
    assert runtime.run("test-windows-under-wine.sh").returncode == 0
    lock = os.open(runtime.root / "build", os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        runtime.codes.write_text('[0]')
        process = subprocess.Popen(["bash", str(runtime.root / "scripts/prepare-windows-wine-runtime.sh")],
                                   cwd=runtime.root, env=runtime.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            with pytest.raises(subprocess.TimeoutExpired):
                process.wait(timeout=0.2)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, (stdout, stderr)
    finally:
        os.close(lock)
