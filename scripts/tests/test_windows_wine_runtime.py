"""Artifact tests use a fake repository/dispatcher, NEVER a real Wine process."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
MARKER = ".space-windows-artifact-v1.json"

# Inert host implementation of the two fixed builtin setup utilities. Every call
# remains visible in both argv inventories; no actual Wine or registry is used.
SETUP_UTILITIES = '''
import json, os, pathlib, stat, sys
_utility = pathlib.PureWindowsPath(sys.argv[1]).name.lower() if len(sys.argv) > 1 else ''
if _utility in ['winepath.exe', 'reg.exe']:
    with open(os.environ['FIXTURE_LOG'], 'a') as _stream:
        _stream.write(json.dumps({'wine':sys.argv[1:], 'tool':sys.argv[0], 'args':sys.argv[1:],
            'utility':True, 'regular_streams':all(stat.S_ISREG(os.fstat(fd).st_mode) for fd in [1,2]),
            'env':{k:os.environ.get(k) for k in
            ['WINEPREFIX','WINEARCH','WINESERVER','XDG_DATA_HOME','XDG_CACHE_HOME','TMPDIR','TEMP','TMP','WINEDLLOVERRIDES']}})+'\\n')
    if _utility == 'winepath.exe':
        _path = sys.argv[3]
        if os.environ.get('FIXTURE_BAD_WINEPATH'): print('relative-temp'); sys.exit(0)
        if sys.argv[2] == '-u' and os.environ.get('FIXTURE_BAD_ROUNDTRIP'): print('/not-owned'); sys.exit(0)
        print('Q:' + _path.replace('/', '\\\\') if sys.argv[2] == '-w' else _path[2:].replace('\\\\', '/'))
        sys.exit(0)
    _name = sys.argv[sys.argv.index('/v') + 1]
    _operation = sys.argv[2]
    _selected = os.environ.get('FIXTURE_REG_NAME') == _name
    if _selected and os.environ.get('FIXTURE_REG_OPERATION', 'query') == _operation:
        if os.environ.get('FIXTURE_REG_EXIT'): sys.exit(int(os.environ['FIXTURE_REG_EXIT']))
    if _operation == 'query':
        _type, _value = {'Debugger':('REG_SZ','winedbg --auto %ld %ld'),
                        'Auto':('REG_SZ','1'), 'ShowCrashDialog':('REG_DWORD','0x0')}[_name]
        if _selected:
            _type = os.environ.get('FIXTURE_REG_TYPE', _type)
            _value = os.environ.get('FIXTURE_REG_VALUE', _value)
        print(sys.argv[3].replace('HKLM', 'HKEY_LOCAL_MACHINE').replace('HKCU', 'HKEY_CURRENT_USER'))
        print('    ' + _name + '    ' + _type + '    ' + _value)
    sys.exit(0)
'''

# Inert report producer for dispatcher tests only. Actual probe C behavior is
# exercised separately against the host API adapter, including report failures.
IDENTITY_FIXTURE = '''
if len(sys.argv) > 1 and pathlib.Path(sys.argv[1]).name == 'process-prng-probe.exe':
    root = pathlib.Path(sys.argv[1]).parents[2]
    assert os.environ['WINEDLLPATH'] == str(root/'wine-publication/modules')
    manifest = json.loads((root/'wine-publication/build.json').read_text())
    so = root/'wine-publication/modules/x86_64-unix/space_record_publication.so'
    info = so.stat()
    challenge = os.environ['SPACE_WINE_IDENTITY_CHALLENGE']
    value = dict(version=1, size=112, abi=1, challenge=challenge, echo=challenge,
                 pe_build_id=manifest['build_id'], unix_build_id=manifest['build_id'],
                 module_device=info.st_dev, module_inode=info.st_ino, architecture=0x8664, features=1)
    damage = os.environ.get('FIXTURE_IDENTITY_DAMAGE')
    for kind, field in [('echo','echo'), ('pe-id','pe_build_id'), ('unix-id','unix_build_id')]:
        if damage == kind: value[field] = '0'*len(value[field])
    for kind, field in [('device','module_device'), ('inode','module_inode')]:
        if damage == kind: value[field] += 1
    if damage == 'extra': value['unexpected'] = True
    raw = json.dumps(value)
    if damage == 'duplicate': raw = raw[:-1] + ',"abi":1}'
    if damage == 'oversize': raw += ' '*4096
    report = pathlib.Path(os.environ['TMPDIR'])/'space-record-publication-identity.json'
    if damage == 'symlink': report.symlink_to(so)
    elif damage == 'hardlink': os.link(so, report)
    elif damage != 'missing':
        fd = os.open(report, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output: output.write(raw)
'''

SYNTHETIC_PAIR_COMPILER = '''
if '-shared' in args and any(a.startswith('-DSRP_BUILD_ID_BYTES=') for a in args):
    import struct
    definition = next(a for a in args if a.startswith('-DSRP_BUILD_ID_BYTES='))
    identity = bytes(int(v, 16) for v in definition.split('=', 1)[1].strip('{}').split(','))
    if 'mingw' in sys.argv[0]:
        data = bytearray(1024)
        data[:2] = b'MZ'; struct.pack_into('<I', data, 60, 128)
        data[64:80] = b'Wine builtin DLL'
        data[128:132] = b'PE\\0\\0'
        struct.pack_into('<HHIIIHH', data, 132, 0x8664, 0, 0, 0, 0, 240, 0x2022)
        struct.pack_into('<H', data, 152, 0x20b); data[-32:] = identity
    else:
        header = struct.pack('<16sHHIQQQIHHHHHH', b'\\x7fELF\\x02\\x01\\x01' + bytes(9),
                             3, 62, 1, 0, 0, 64, 0, 64, 0, 0, 64, 1, 0)
        data = header + bytes(64) + identity
    pathlib.Path(args[args.index('-o')+1]).write_bytes(data)
    sys.exit(0)
'''


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
        (self.root / 'src').mkdir()
        shutil.copy2(ROOT / 'src/record_publication_wine_abi.h', self.root / 'src')
        shutil.copy2(ROOT / 'src/wine_owned_environment.h', self.root / 'src')
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
                        WINE_CMD=str(self.bin / "wine"), WINEPREFIX=str(path / "unchanged-prefix"),
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
        cc = self.bin / 'x86_64-w64-mingw32-gcc-posix'
        cc.write_text(cc.read_text().replace("pathlib.Path(args[args.index('-o')+1]).write_text",
                                           SYNTHETIC_PAIR_COMPILER + "\npathlib.Path(args[args.index('-o')+1]).write_text"))
        self.write_executable('publication-cxx', cc.read_text())
        self.write_executable('winebuild', '#!/bin/sh\nexit 0\n')
        headers = self.root / 'fixture-headers/wine/wine'
        for relative in ('windows/winternl.h', 'windows/windef.h', 'windows/winbase.h'):
            path = headers / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('/* inert fixture header, not Wine ABI proof */\n')
        # Override discovery only inside this fake checkout, retaining the real
        # shared public-SDK root helper instead of copying its parser into a stub.
        toolchain = scripts / 'wine/publication_toolchain.py'
        toolchain.write_text(toolchain.read_text() + f'''
import hashlib
from pathlib import Path
def resolve_toolchain(repo, runtime=None):
    tools = {{key: dict(executable=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
             for key, path in {{'host_cxx': Path({str(self.bin / 'publication-cxx')!r}),
                               'mingw_cc': Path({str(cc)!r}),
                               'winebuild': Path({str(self.bin / 'winebuild')!r})}}.items()}}
    files = {{str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in Path({str(headers)!r}).rglob('*.h')}}
    return dict(version=1, repo=str(repo), runtime=runtime, tools=tools, headers=dict(files=files))
def verify_toolchain(identity):
    if identity != resolve_toolchain(Path(identity['repo']), identity['runtime']):
        raise ValueError('Fixture pinned toolchain changed')
''')
        self.write_executable("wineserver", '''#!/usr/bin/python3
import json, os, sys
if sys.argv[1:] == ['--version']:
    print('Wine 9.0 (fixture)'); sys.exit(0)
with open(os.environ['FIXTURE_LOG'], 'a') as f:
    f.write(json.dumps({'server':sys.argv[1:], 'env':{k:os.environ.get(k) for k in
        ['WINEPREFIX','WINEARCH','WINESERVER'] + ['SPACE_WINE_WINDOWS_TMP']}})+'\\n')
sys.exit(int(os.environ.get('FIXTURE_STOP_CODE', '0')) if sys.argv[1:] == ['-k'] else 0)
''')
        self.write_executable("wine", '''#!/usr/bin/python3
import json, os, pathlib, sys
if sys.argv[1:] == ['--version']:
    print('wine-9.0 (fixture)'); sys.exit(0)
with open(os.environ['FIXTURE_LOG'], 'a') as f:
    f.write(json.dumps({'wine':sys.argv[1:], 'env':{k:os.environ.get(k) for k in
        ['WINEDLLOVERRIDES','WINEPREFIX','WINEARCH','WINESERVER','DISPLAY','SPACE_ASSETS_PATH','SPACE_BIN','FENNEL_PATH','FENNEL_MACRO_PATH','XDG_DATA_HOME','XDG_CACHE_HOME','TMPDIR','TEMP','TMP','WINEDLLPATH']}})+'\\n')
if pathlib.Path(sys.argv[1]).name == 'process-prng-probe.exe':
    p = pathlib.Path(os.environ['FIXTURE_CODES']); codes = json.loads(p.read_text())
    code = codes.pop(0); p.write_text(json.dumps(codes)); sys.exit(code)
sys.exit(int(os.environ.get('FIXTURE_INIT_CODE', '0')) if sys.argv[1] == 'wineboot.exe' else int(os.environ.get('FIXTURE_APP_CODE', '0')))
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
        if name == 'wine':
            first, rest = text.split('\n', 1)
            text = first + '\nimport pathlib\n' + SETUP_UTILITIES + '\n' + IDENTITY_FIXTURE + '\n' + rest
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


def bind_discovery_fixture(runtime):
    """Prepare valid discovery-copy inputs for consumer-negative tests only."""
    from wine import artifacts, build_publication
    source = runtime.root / 'build/wine-publication' / build_publication.PAIR[0]
    copy = runtime.overlay / 'space_record_publication.dll'
    shutil.copy2(source, copy)
    receipt = runtime.overlay / 'admission.json'
    value = json.loads(receipt.read_text())
    value['payload'][copy.name] = hashlib.sha256(copy.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(value))
    artifacts.seal(runtime.overlay, 'wine-overlay')
    return copy


def test_overlay_discovery_copy_is_owned_pair_identical_and_repeatable(runtime):
    from wine import build_publication
    # A stale helper in native build leftovers must never become the Wine copy.
    (runtime.build / 'space_record_publication.dll').write_text('not the admitted pair')
    runtime.package()
    native_before = hashes(runtime.build), hashes(runtime.dist)
    assert runtime.prepare([0]).returncode == 0
    source = runtime.root / 'build/wine-publication' / build_publication.PAIR[0]
    copy = runtime.overlay / 'space_record_publication.dll'
    assert copy.is_file(), 'Wine basename discovery needs the verified overlay PE copy'
    assert copy.read_bytes() == source.read_bytes()
    info = copy.lstat()
    assert info.st_uid == os.geteuid() and info.st_nlink == 1 and info.st_mode & 0o777 == 0o600
    assert (info.st_dev, info.st_ino) != (source.stat().st_dev, source.stat().st_ino)
    pair_before = hashes(source.parents[2])
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    digest = hashlib.sha256(copy.read_bytes()).hexdigest()
    assert receipt['payload'][copy.name] == receipt['bridge']['files'][build_publication.PAIR[0]]['sha256'] == digest
    assert not any(p.name.casefold() in {'space_record_publication.dll', 'space_record_publication.so'}
                   for p in runtime.dist.rglob('*'))
    assert runtime.prepare([0]).returncode == 0
    assert hashes(source.parents[2]) == pair_before
    assert copy.read_bytes() == source.read_bytes()
    assert (hashes(runtime.build), hashes(runtime.dist)) == native_before


@pytest.mark.parametrize('damage', ['missing', 'tampered', 'resealed', 'hardlink', 'symlink', 'mode'])
def test_discovery_copy_damage_cannot_authorize_application(runtime, damage):
    from wine import artifacts
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    copy = bind_discovery_fixture(runtime)
    receipt = runtime.overlay / 'admission.json'
    value = json.loads(receipt.read_text())
    if damage == 'missing':
        copy.unlink()
        del value['payload'][copy.name]
    elif damage in ('hardlink', 'symlink'):
        # Keep the inventoried source pair valid: reject the copy's link, not
        # merely a link-count change in the source artifact.
        preserved = runtime.root / 'preserved-discovery-image'
        shutil.copy2(copy, preserved)
        copy.unlink()
        os.link(preserved, copy) if damage == 'hardlink' else copy.symlink_to(preserved)
    elif damage == 'mode':
        copy.chmod(0o644)
    else:
        copy.write_bytes(b'wrong discovery image')
        value['payload'][copy.name] = hashlib.sha256(copy.read_bytes()).hexdigest()
    if damage not in ('tampered', 'symlink'):
        receipt.write_text(json.dumps(value))
        artifacts.seal(runtime.overlay, 'wine-overlay')
    before = runtime.calls()
    result = runtime.run('test-windows-under-wine.sh')
    assert result.returncode != 0, result.stdout + result.stderr
    assert not [call for call in runtime.calls()[len(before):] if 'wine' in call]


def test_probe_refuses_wrong_discovery_copy_before_any_launch(runtime, monkeypatch):
    from wine import artifacts, prefix
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    copy = bind_discovery_fixture(runtime)
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    session = prefix.load_session(runtime.root, receipt['ownedSession']['id'])
    artifacts._remove_identity_report(session, artifacts._identity_file(session))
    copy.write_bytes(b'wrong discovery image')
    artifacts.seal(runtime.overlay, 'wine-overlay')
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(artifacts, 'OVERLAY', runtime.overlay)
    monkeypatch.setattr(artifacts, 'BUILD', runtime.root / 'build')
    runtime.codes.write_text('[0]')
    manifest = json.loads((runtime.root / 'build/wine-publication/build.json').read_text())
    before = runtime.calls(), session.state()
    with pytest.raises(ValueError, match='discovery'):
        artifacts.probe(session, artifacts.BUILTIN, manifest)
    assert (runtime.calls(), session.state()) == before


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
    assert len([c for c in runtime.calls() if "wine" in c and c['wine'][0].endswith('process-prng-probe.exe')]) == 2
    assert not (runtime.overlay / "admission.json").exists()


def test_builtin_success_never_builds_bridge_and_app_uses_receipt(runtime):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    result = runtime.run("test-windows-under-wine.sh")
    assert result.returncode == 0, result.stderr
    calls = runtime.calls()
    boot, probes, app = [c for c in calls if "wine" in c and not c.get('utility')]
    assert probes["env"]["WINEDLLOVERRIDES"] == "space_record_publication=b;bcryptprimitives=b;advapi32,cryptbase=b"
    assert app["env"]["WINEDLLOVERRIDES"] == probes["env"]["WINEDLLOVERRIDES"]
    assert app["env"]["WINEPREFIX"] == probes["env"]["WINEPREFIX"]
    assert app["env"]["DISPLAY"] == ":fixture"
    assert app["wine"] == [str(runtime.overlay / "space-cli.exe"), "-m", "tests.fast:main"]
    assert app["env"]["SPACE_ASSETS_PATH"] == str(runtime.overlay / "assets")
    assert app["env"]["SPACE_BIN"] == str(runtime.overlay / "space-cli.exe")
    assert str(runtime.overlay / "assets/lua") in app["env"]["FENNEL_PATH"]
    assert app["env"]["FENNEL_PATH"] == app["env"]["FENNEL_MACRO_PATH"]
    assert [c["timeout"] for c in calls if "timeout" in c] == ["60s", "60s", "900s", "480s", "90s", *["30s"] * 8, "60s", "10s", "15s", "1800s", "10s", "15s"]
    assert all(c["kill_after"] == "--kill-after=5s" for c in calls if "timeout" in c)
    assert not (runtime.overlay / "bcryptprimitives.dll").exists()


def test_compat_selection_is_fixed_and_receipt_is_not_shell(runtime):
    runtime.package()
    assert runtime.prepare([10, 0]).returncode == 0
    runtime.env["WINEDLLOVERRIDES"] = "malicious=inherited"
    assert runtime.run("test-windows-under-wine.sh").returncode == 0
    wine = [c for c in runtime.calls() if "wine" in c and c['wine'][0] != 'wineboot.exe' and not c.get('utility')]
    assert [c["env"]["WINEDLLOVERRIDES"] for c in wine] == [
        "space_record_publication=b;bcryptprimitives=b;advapi32,cryptbase=b", "space_record_publication=b;bcryptprimitives=n;advapi32,cryptbase=b",
        "space_record_publication=b;bcryptprimitives=n;advapi32,cryptbase=b"]
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
    runtime.write_executable("wine", f'''#!/usr/bin/python3
import pathlib, sys
if sys.argv[1:] == ['--version']:
    print('wine-9.0 (fixture)'); sys.exit(0)
if sys.argv[1:] == ['wineboot.exe', '--init']: sys.exit(0)
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
                                 '-I', str(ROOT / 'src'), '-DSRP_BUILD_ID_BYTES={1}',
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
                    "-I", str(ROOT / "src"), '-DSRP_BUILD_ID_BYTES={1}',
                    str(ROOT / "scripts/tests/wine_adapters" / f"{source}.c"),
                    "-o", str(output)], check=True, capture_output=True, text=True)
    return output


def owned_probe_environment(tmp_path, mode='normal', **overrides):
    env = dict(os.environ, PROBE_FIXTURE=mode, PROBE_HOST_TMP=str(tmp_path),
                SPACE_WINE_WINDOWS_TMP=r'Q:\owned\tmp',
                SPACE_WINE_IDENTITY_CHALLENGE='0123456789abcdef',
                TEMP='C:\\registry\\temp', TMP='D:\\registry\\tmp',
                WINEDLLOVERRIDES='space_record_publication=b;bcryptprimitives=b;advapi32,cryptbase=b')
    env.update(overrides)
    return env


@pytest.mark.parametrize('case', ['missing', 'empty', 'oversize', 'truncated', 'relative', 'unc', 'device', 'mixed',
                                 'drive-digit', 'dos-device', 'ads', 'trailing-dot', 'trailing-space',
                                 'traversal', 'control', 'high-surrogate', 'low-surrogate',
                                 'api-read', 'set-temp', 'set-tmp', 'set-temp-no-error', 'set-tmp-no-error',
                                 'read-temp', 'read-tmp', 'read-temp-truncated', 'read-tmp-truncated',
                                 'mismatch-temp', 'mismatch-tmp'])
def test_required_owned_environment_failure_precedes_all_probe_work(tmp_path, case):
    exe = compile_host(tmp_path, 'probe', str(ROOT / 'scripts/wine/probe.c'))
    env = owned_probe_environment(tmp_path, PROBE_ENV_CASE=case)
    if case == 'missing':
        env.pop('SPACE_WINE_WINDOWS_TMP')
    result = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
    assert result.returncode == 20, result.stdout + result.stderr
    assert result.stderr.startswith('Owned Wine environment: phase=apply error=')
    error = result.stderr.strip().removeprefix('Owned Wine environment: phase=apply error=')
    assert error.isdecimal() and 0 < int(error) < 2**32
    expected = {'missing': 203, 'empty': 87, 'oversize': 122, 'truncated': 122,
                'api-read': 5, 'set-temp': 5, 'set-tmp': 5, 'read-temp': 5, 'read-tmp': 5,
                'set-temp-no-error': 31, 'set-tmp-no-error': 31,
                'read-temp-truncated': 122, 'read-tmp-truncated': 122,
                'mismatch-temp': 13, 'mismatch-tmp': 13}
    assert int(error) == expected.get(case, 87)
    if case.startswith('set-temp'):
        assert 'fixture-set-tmp' not in result.stdout
    if case.startswith('set-tmp'):
        assert 'fixture-set-temp' in result.stdout and 'fixture-set-tmp' not in result.stdout
    assert 'fixture-owned-before-load' not in result.stdout
    assert 'fixture-entry0' not in result.stdout and 'fixture-crypto-load' not in result.stdout
    assert not (tmp_path / 'space-record-publication-identity.json').exists()
    assert '0123456789abcdef' not in result.stderr and str(tmp_path) not in result.stderr
    assert all(len(line.encode()) < 160 for line in result.stderr.splitlines())


@pytest.mark.parametrize('root', [r'R:\private\tmp', r'S:\private' + '\\雪', r'T:\private' + '\\' + '\U0001f680'])
def test_actual_probe_applies_and_verifies_distinct_registry_temp_before_first_load(tmp_path, root):
    exe = compile_host(tmp_path, 'probe', str(ROOT / 'scripts/wine/probe.c'))
    # Explicit UTF-16 units, not host wchar_t's Unicode-code-point representation.
    units = root.encode('utf-16-le').hex()
    env = owned_probe_environment(tmp_path, PROBE_HANDOFF_UTF16=units)
    result = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[:5] == ['fixture-set-temp', 'fixture-set-tmp', 'fixture-read-temp',
                         'fixture-read-tmp', 'fixture-owned-before-load']
    assert lines.index('fixture-owned-before-load') < lines.index('fixture-entry0')
    assert (tmp_path / 'space-record-publication-identity.json').is_file()


@pytest.mark.parametrize('case,expected', [('missing', 0), ('empty', 20), ('relative', 20), ('api-read', 20)])
def test_optional_owned_environment_only_genuine_absence_is_a_noop(tmp_path, case, expected):
    header = ROOT / 'src/wine_owned_environment.h'
    assert header.is_file(), 'private generic Win32 initializer header is required'
    source = tmp_path / 'optional.c'
    source.write_text('''#include "wine_owned_environment.h"
extern int fixture_environment_unchanged(void);
int main(void) {
    DWORD result = space_wine_apply_owned_environment(FALSE);
    if (!fixture_environment_unchanged()) return 77;
    return result == ERROR_SUCCESS ? 0 : 20;
}
''')
    exe = compile_host(tmp_path, 'probe', str(source))
    env = owned_probe_environment(tmp_path, PROBE_ENV_CASE=case)
    if case == 'missing':
        env.pop('SPACE_WINE_WINDOWS_TMP')
    result = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
    assert result.returncode == expected, result.stdout + result.stderr


@pytest.mark.parametrize('compiler,standard', [('x86_64-w64-mingw32-gcc-posix', 'c11'),
                                             ('x86_64-w64-mingw32-g++-posix', 'c++17')])
def test_owned_environment_header_compiles_with_real_win16_c_and_cpp(tmp_path, compiler, standard):
    header = ROOT / 'src/wine_owned_environment.h'
    assert header.is_file(), 'private generic Win32 initializer header is required'
    cc = shutil.which(compiler)
    assert cc, 'tiny MinGW C/C++ compilation is required; no PE execution'
    source = '''#include "wine_owned_environment.h"
#ifdef __cplusplus
static_assert(sizeof(WCHAR) == 2, "Windows UTF-16 units");
#else
_Static_assert(sizeof(WCHAR) == 2, "Windows UTF-16 units");
#endif
int main(void) { return space_wine_apply_owned_environment(FALSE) ? 1 : 0; }
'''
    output = tmp_path / 'owned-environment.exe'
    result = subprocess.run([cc, '-x', 'c++' if standard == 'c++17' else 'c', f'-std={standard}',
                             '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'src'), '-o', str(output), '-'],
                            input=source, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes()[:2] == b'MZ'


@pytest.mark.parametrize('mode', ['pair-missing', 'pair-export', 'pair-owner', 'pair-status',
                                 'pair-echo', 'pair-pe-id', 'pair-unix-id', 'pair-size',
                                 'pair-abi', 'pair-arch', 'pair-features', 'pair-inode',
                                 'report-create', 'report-write', 'report-short', 'report-close'])
def test_actual_probe_pair_failure_never_reaches_crypto(tmp_path, mode):
    exe = compile_host(tmp_path, 'probe', str(ROOT / 'scripts/wine/probe.c'))
    result = subprocess.run([str(exe)], env=owned_probe_environment(tmp_path, mode),
                            capture_output=True, text=True)
    assert result.returncode == 20, result.stdout + result.stderr
    assert 'fixture-crypto-load' not in result.stdout
    assert 'fixture-request=' not in result.stdout


@pytest.mark.parametrize('mode,error', [('pair-missing', 126), ('pair-bad-image', 193),
                                      ('pair-init-failed', 1114), ('pair-access-denied', 5)])
def test_actual_probe_reports_numeric_publication_loader_error(tmp_path, mode, error):
    exe = compile_host(tmp_path, 'probe', str(ROOT / 'scripts/wine/probe.c'))
    result = subprocess.run([str(exe)], env=owned_probe_environment(tmp_path, mode),
                            capture_output=True, text=True)
    assert result.returncode == 20, result.stdout + result.stderr
    lines = result.stderr.splitlines()
    assert lines[0] == f'Publication probe: phase=load-library error={error}'
    assert all(len(line.encode()) < 160 for line in lines)
    assert 'fixture-entry0' not in result.stdout and 'fixture-crypto-load' not in result.stdout
    assert '0123456789abcdef' not in result.stderr and str(tmp_path) not in result.stderr
    assert not (tmp_path / 'space-record-publication-identity.json').exists()


@pytest.mark.parametrize('mode,status', [('pair-status', -1073741515),
                                       ('pair-status--2147483648', -2147483648),
                                       ('pair-status-2147483647', 2147483647),
                                       ('pair-echo', 0)])
def test_actual_probe_reports_raw_entry0_status_before_identity_failure(tmp_path, mode, status):
    exe = compile_host(tmp_path, 'probe', str(ROOT / 'scripts/wine/probe.c'))
    result = subprocess.run([str(exe)], env=owned_probe_environment(tmp_path, mode),
                            capture_output=True, text=True)
    assert result.returncode == 20, result.stdout + result.stderr
    assert result.stderr.splitlines()[0] == f'Publication probe: phase=entry0 status={status}'
    assert all(len(line.encode()) < 160 for line in result.stderr.splitlines())
    assert 'fixture-entry0' in result.stdout and 'fixture-crypto-load' not in result.stdout
    assert '0123456789abcdef' not in result.stderr and str(tmp_path) not in result.stderr
    assert not (tmp_path / 'space-record-publication-identity.json').exists()


@pytest.mark.parametrize('mode,code', [('normal', 0), ('load-126', 10), ('export-127', 10)])
def test_actual_probe_writes_identity_before_crypto_in_same_process(tmp_path, mode, code):
    exe = compile_host(tmp_path, 'probe', str(ROOT / 'scripts/wine/probe.c'))
    env = owned_probe_environment(tmp_path, mode)
    result = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
    assert result.returncode == code, result.stdout + result.stderr
    report = tmp_path / 'space-record-publication-identity.json'
    assert report.is_file(), 'actual probe must emit identity, not just stdout'
    assert report.stat().st_size <= 4096
    value = json.loads(report.read_text())
    assert value == dict(version=1, size=112, abi=1, challenge='0123456789abcdef',
                        echo='0123456789abcdef', pe_build_id='01' + '00'*31,
                        unix_build_id='01' + '00'*31, module_device=7, module_inode=19,
                        architecture=0x8664, features=1)
    assert result.stdout.index('fixture-entry0') < result.stdout.index('fixture-crypto-load')
    before = report.read_bytes()
    again = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
    assert again.returncode == 20 and report.read_bytes() == before
    assert 'fixture-crypto-load' not in again.stdout


def test_receipt_v3_binds_pair_and_fixed_loader_root(runtime):
    runtime.package()
    result = runtime.prepare([10, 0])
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    assert receipt['version'] == 3
    assert set(receipt['bridge']) == {'abi', 'build_id', 'toolchain', 'files', 'identity'}
    calls = [c for c in runtime.calls() if 'wine' in c and not c.get('utility')]
    assert len(calls) == 3  # one initialization, two same-process capability probes
    for call in calls[1:]:
        assert call['env']['WINEDLLPATH'] == str(runtime.root / 'build/wine-publication/modules')
        assert call['env']['WINEDLLOVERRIDES'].startswith('space_record_publication=b;')
    assert len([c for c in runtime.calls() if c.get('utility')]) == 8


@pytest.mark.parametrize('code', [0, 10])
@pytest.mark.parametrize('damage', ['missing', 'echo', 'pe-id', 'unix-id', 'device', 'inode',
                                   'extra', 'duplicate', 'oversize', 'symlink', 'hardlink'])
def test_host_refuses_unproved_pair_even_when_crypto_claims_success_or_absence(runtime, damage, code):
    runtime.package()
    runtime.env['FIXTURE_IDENTITY_DAMAGE'] = damage
    result = runtime.prepare([code, 0])
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'probe exit=20' in result.stdout
    assert not (runtime.overlay / 'admission.json').exists()
    assert not any('process_prng_compat.c' in ' '.join(c.get('cc', [])) for c in runtime.calls())


def test_schema2_receipt_cannot_authorize_execution(runtime):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    receipt = runtime.overlay / 'admission.json'
    value = json.loads(receipt.read_text())
    value['version'] = 2
    receipt.write_text(json.dumps(value))
    # Reseal only in fixture so rejection tests schema, not stale inventory.
    marker = runtime.overlay / MARKER
    seal = json.loads(marker.read_text())
    seal['inventory']['admission.json'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    marker.write_text(json.dumps(seal))
    before = len([c for c in runtime.calls() if 'wine' in c])
    result = runtime.run('test-windows-under-wine.sh')
    assert result.returncode != 0
    assert len([c for c in runtime.calls() if 'wine' in c]) == before


@pytest.mark.parametrize('damage', ['missing-so', 'changed-so', 'extra-output', 'source', 'tool', 'identity', 'build-id'])
def test_admitted_pair_bindings_are_rechecked_before_application(runtime, damage):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    output = runtime.root / 'build/wine-publication'
    so = output / 'modules/x86_64-unix/space_record_publication.so'
    if damage == 'missing-so':
        so.unlink()
    elif damage == 'changed-so':
        so.write_bytes(so.read_bytes() + b'changed')
    elif damage == 'extra-output':
        (output / 'foreign').write_text('keep')
    elif damage == 'source':
        (runtime.root / 'src/record_publication_wine_abi.h').write_text('changed source')
    elif damage == 'tool':
        with (runtime.bin / 'publication-cxx').open('a') as stream:
            stream.write('\n# changed compiler\n')
    else:
        receipt = runtime.overlay / 'admission.json'
        value = json.loads(receipt.read_text())
        if damage == 'identity':
            value['bridge']['identity']['module_inode'] += 1
        else:
            value['bridge']['build_id'] = '0'*64
        receipt.write_text(json.dumps(value))
        marker = runtime.overlay / MARKER
        seal = json.loads(marker.read_text())
        seal['inventory']['admission.json'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
        marker.write_text(json.dumps(seal))
    before = len([c for c in runtime.calls() if 'wine' in c])
    result = runtime.run('test-windows-under-wine.sh')
    assert result.returncode != 0, result.stdout + result.stderr
    assert len([c for c in runtime.calls() if 'wine' in c]) == before


def test_private_bootstrap_requires_parent_handoff_without_default_prefix(runtime):
    runtime.package()
    before = runtime.calls()
    result = subprocess.run([sys.executable, str(runtime.root / 'scripts/wine/artifacts.py'), 'prepare-bootstrap'],
                            cwd=runtime.root, env=runtime.env, capture_output=True, text=True)
    assert result.returncode != 0 and 'requires owned parent Session handoff' in result.stderr
    assert runtime.calls() == before
    assert not (runtime.root / 'build/wine/sessions').exists()


def test_composite_serializes_with_reproducer_without_holding_child_build_lock(runtime):
    runtime.package()
    compiler = runtime.bin / 'publication-cxx'
    source = compiler.read_text()
    check = '''
import fcntl
repo = pathlib.Path.cwd().parents[1]
repo_fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
try:
    fcntl.flock(repo_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    pass
else:
    sys.exit(77)
os.close(repo_fd)
build_fd = os.open(repo/'build', os.O_RDONLY | os.O_DIRECTORY)
fcntl.flock(build_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
os.close(build_fd)
'''
    compiler.write_text(source.replace('args = sys.argv[1:]', 'args = sys.argv[1:]\n' + check))
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('stage', ['builder', 'bootstrap'])
@pytest.mark.parametrize('code', [17, 124])
def test_prepare_preserves_child_failure_with_one_failed_scoped_cleanup(runtime, stage, code):
    runtime.env['FIXTURE_STOP_CODE'] = '37'
    builder = runtime.root / 'scripts/wine/build_publication.py'
    builder.write_text(f'''
import json, os, sys
if __name__ == '__main__':
    with open(os.environ['FIXTURE_LOG'], 'a') as stream:
        stream.write(json.dumps({{'prepare_child': 'builder'}}) + '\\n')
    sys.exit({code if stage == 'builder' else 0})
''')
    # Only the fake checkout's bootstrap branch is inert. The parent executes
    # actual public prepare/main, Session ownership and scoped stop/wait code.
    artifact = runtime.root / 'scripts/wine/artifacts.py'
    artifact.write_text(f'''
import json, os, sys
if __name__ == '__main__' and sys.argv[1:] == ['prepare-bootstrap']:
    with open(os.environ['FIXTURE_LOG'], 'a') as stream:
        stream.write(json.dumps({{'prepare_child': 'bootstrap'}}) + '\\n')
    sys.exit({code})
''' + artifact.read_text())
    result = runtime.run('prepare-windows-wine-runtime.sh')
    calls = runtime.calls()
    servers = [call for call in calls if 'server' in call]
    commands = [call['server'] for call in servers]
    assert (result.returncode, commands) == (code, [['-k'], ['-w']]), (
        f'primary={result.returncode}; scoped_cleanup={commands}; stderr={result.stderr}')
    assert result.stderr.count('Owned Wine cleanup failed:') == 1
    assert 'wineserver -k exit=37' in result.stderr
    assert [call['prepare_child'] for call in calls if 'prepare_child' in call] == (
        ['builder'] if stage == 'builder' else ['builder', 'bootstrap'])
    assert [call['timeout'] for call in calls if 'timeout' in call] == (
        ['60s', '60s', '900s'] + ([] if stage == 'builder' else ['480s']) + ['10s', '15s'])
    prefix = Path(servers[0]['env']['WINEPREFIX'])
    assert prefix.parent.parent == runtime.root / 'build/wine/sessions'
    assert all(call['env']['WINEPREFIX'] == str(prefix) for call in servers)
    state = json.loads((prefix.parent / 'state.json').read_text())
    assert state['ended'] and not state['authorized'] and state['stopped_generation'] is None
    assert not Path(runtime.env['WINEPREFIX']).exists()


@pytest.mark.parametrize('error_type', [ValueError, KeyboardInterrupt])
def test_prepare_execution_exception_cleans_once_and_rethrows_original(runtime, monkeypatch, capsys, error_type):
    from wine import artifacts, prefix
    runtime.env['FIXTURE_STOP_CODE'] = '37'
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    session = prefix.create_session(runtime.root)
    primary = error_type('fixture composite execution failure')
    environment = prefix.Session.environment
    def failed_environment(self):
        if self is session:
            raise primary
        return environment(self)
    monkeypatch.setattr(prefix.Session, 'environment', failed_environment)
    with pytest.raises(error_type) as caught:
        artifacts.prepare(session)
    assert caught.value is primary
    servers = [call for call in runtime.calls() if 'server' in call]
    assert [call['server'] for call in servers] == [['-k'], ['-w']]
    assert all(call['env']['WINEPREFIX'] == str(session.prefix) for call in servers)
    stderr = capsys.readouterr().err
    assert stderr.count('Owned Wine cleanup failed:') == 1
    assert 'wineserver -k exit=37' in stderr


def test_retry_refuses_changed_or_unowned_fixed_report_without_deleting_it(runtime):
    from wine import artifacts, prefix
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    session = prefix.load_session(runtime.root, receipt['ownedSession']['id'])
    verified = artifacts._identity_file(session)
    path = session.tmp / artifacts.IDENTITY_REPORT
    value = verified[0] | {'echo': '0'*16}
    path.write_text(json.dumps(value))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='retry report changed'):
        artifacts._remove_identity_report(session, verified)
    assert path.read_bytes() == before
    path.unlink()
    target = runtime.root / 'sentinel'
    target.write_text('preserve')
    path.symlink_to(target)
    with pytest.raises((ValueError, OSError)):
        artifacts._remove_identity_report(session, verified)
    assert path.is_symlink() and target.read_text() == 'preserve'


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
    result = subprocess.run([str(exe)], env=owned_probe_environment(tmp_path, mode),
                            capture_output=True, text=True)
    assert result.returncode == code, result.stdout + result.stderr
    if code == 0:
        assert [s for s in result.stdout.splitlines() if s.startswith("fixture-request=")] == [
            "fixture-request=65536", "fixture-request=65536", "fixture-request=65539",
            "fixture-request=0", "fixture-request=0"]


def test_probe_compat_identity_uses_own_overlay_directory(tmp_path):
    exe = compile_host(tmp_path, "probe", str(ROOT / "scripts/wine/probe.c"))
    result = subprocess.run([str(exe)], env=owned_probe_environment(tmp_path,
                            WINEDLLOVERRIDES="space_record_publication=b;bcryptprimitives=n;advapi32,cryptbase=b"),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("change", ["owned-prefix", "display", "wine", "app", "helper", "package"])
def test_receipt_rejects_changed_runtime_conditions_and_payload(runtime, change):
    runtime.package()
    assert runtime.prepare([10, 0]).returncode == 0
    if change == "owned-prefix":
        receipt = json.loads((runtime.overlay / 'admission.json').read_text())
        path = Path(receipt['ownedSession']['prefix'])
        path.rename(path.with_name('preserved-prefix'))
        path.mkdir(mode=0o700)
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
    assert result.returncode == 0, result.stderr
    receipt = json.loads((runtime.overlay / "admission.json").read_text())
    assert Path(receipt['ownedSession']['prefix']).parent.parent == runtime.root / 'build/wine/sessions'
    assert not home_a.exists() and not home_b.exists()


def test_relative_selected_wine_is_same_identity_at_admission_and_consumption(runtime):
    tools = runtime.root / "tools"
    tools.mkdir()
    shutil.copy2(runtime.bin / "wine", tools / "wine")
    shutil.copy2(runtime.bin / "wineserver", tools / "wineserver")
    runtime.env["WINE_CMD"] = "./tools/wine"
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    result = runtime.run("test-windows-under-wine.sh")
    assert result.returncode == 0, result.stderr
    receipt = json.loads((runtime.overlay / "admission.json").read_text())
    assert receipt["tools"]["wine"]["executable"] == str(tools / "wine")
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
    dispatcher = (runtime.bin / "wine").read_text()
    for directory, identity in ((versions, "filesystem-selected"), (tools, "lexical-decoy")):
        executable = directory / "wine"
        executable.write_text(dispatcher
                              .replace("'wine':sys.argv[1:]", f"'selected':{identity!r}, 'wine':sys.argv[1:]"))
        executable.chmod(0o755)
        shutil.copy2(runtime.bin / 'wineserver', directory / 'wineserver')
    # Kernel lookup follows alias -> versions/active, THEN '..' -> versions.
    # Both targets exist, so lexical abspath would silently select the decoy.
    runtime.env["WINE_CMD"] = str(tools / "alias" / ".." / "wine")
    before_executables = hashes(versions), hashes(tools)
    expected = {"executable": str(versions / "wine"),
                 "version": "wine-9.0 (fixture)",
                "sha256": hashlib.sha256((versions / "wine").read_bytes()).hexdigest()}
    assert expected["sha256"] != hashlib.sha256((tools / "wine").read_bytes()).hexdigest()
    runtime.package()
    before_native = hashes(runtime.build), hashes(runtime.dist)
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stderr
    receipt = (runtime.overlay / "admission.json").read_bytes()
    assert json.loads(receipt)["tools"]["wine"] == expected
    result = runtime.run("test-windows-under-wine.sh")
    assert result.returncode == 0, result.stderr
    assert [c["selected"] for c in runtime.calls() if "wine" in c and not c.get('utility')] == [
        "filesystem-selected", "filesystem-selected", "filesystem-selected"]
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
args = ['0.2s' if a == '60s' else '--kill-after=0.2s' if a == '--kill-after=5s' else a for a in args]
pathlib.Path({str(timeout_pid)!r}).write_text(str(os.getpid()))
os.execv({real_timeout!r}, [{real_timeout!r}, *args])
''')
    runtime.write_executable("wine", f'''#!/usr/bin/python3
import pathlib, signal, sys, time
if sys.argv[1:] == ['--version']:
    print('wine-9.0 (fixture)'); sys.exit(0)
if sys.argv[1:] == ['wineboot.exe', '--init']: sys.exit(0)
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


@pytest.mark.parametrize('name', ['BCryptPrimitives.DLL', 'space_record_publication.dll', 'space_record_publication.so'])
def test_forbidden_helper_in_packaged_assets_fails_final_verification(runtime, name):
    (runtime.root / 'assets' / name).write_text("hidden helper")
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
        assert app["env"]["WINEDLLOVERRIDES"] == "space_record_publication=b;bcryptprimitives=n;advapi32,cryptbase=b"
        assert Path(app["env"]["WINEPREFIX"]).parent.parent == runtime.root / 'build/wine/sessions'
        assert app["env"]["SPACE_ASSETS_PATH"] == str(runtime.overlay / "assets")
        assert [c for c in runtime.calls() if "timeout" in c][-3]["timeout"] == "60s"


def test_prepare_and_app_consumption_serialize_with_artifact_writers(runtime):
    import fcntl
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    # Block the fixture application after configuration and prove a second
    # package writer cannot enter while the consumer holds build/'s inode lock.
    runtime.write_executable("wine", '''#!/usr/bin/python3
import fcntl, os, pathlib, sys
if sys.argv[1:] == ['--version']:
    print('wine-9.0 (fixture)'); sys.exit(0)
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
