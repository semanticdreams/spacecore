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
import errno
import fcntl
import importlib.util
import stat
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
MARKER = ".space-windows-artifact-v1.json"
CATALOG_RESOURCE = 'docs/dev/features/entity-type-catalog.md'
SHA256_RESOURCE = 'docs/dev/notes/native-sha256.md'
REQUIRED_RESOURCE_PATHS = (CATALOG_RESOURCE, SHA256_RESOURCE)
NATIVE_HELPER_BASENAMES = ('BCryptPrimitives.DLL', 'SpAcE_ReCoRd_PuBlIcAtIoN.DlL',
                          'SpAcE_ReCoRd_PuBlIcAtIoN.So', 'SpAcE_ReCoRd_PuBlIcAtIoN_TeStS.DlL',
                          'SpAcE_ReCoRd_PuBlIcAtIoN_TeStS.So', 'TeSt_ReCoRd_PuBlIcAtIoN.ExE')
PUBLICATION_INPUTS = ('src/record_publication_wine_abi.h', 'src/record_publication_wine_authority.h',
                      'src/record_publication_unix.h', 'src/record_publication_unix.cpp',
                      'src/record_publication_operation.h', 'src/record_publication.h',
                      'src/record_publication.cpp', 'scripts/wine/record_publication_bridge.c',
                      'scripts/wine/record_publication_unix_entry.cpp', 'scripts/wine/build_publication.py')

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
                 module_device=info.st_dev, module_inode=info.st_ino, architecture=0x8664, features=3)
    damage = os.environ.get('FIXTURE_IDENTITY_DAMAGE')
    for kind, field in [('echo','echo'), ('pe-id','pe_build_id'), ('unix-id','unix_build_id')]:
        if damage == kind: value[field] = '0'*len(value[field])
    for kind, field in [('device','module_device'), ('inode','module_inode')]:
        if damage == kind: value[field] += 1
    if damage in ['size', 'abi', 'architecture', 'features']: value[damage] += 1
    if damage == 'feature-old': value['features'] = 1
    if damage == 'feature-extra': value['features'] = 7
    if damage == 'extra': value['unexpected'] = True
    raw = json.dumps(value)
    if damage == 'duplicate': raw = raw[:-1] + ',"abi":1}'
    if damage == 'oversize': raw += ' '*4096
    if damage == 'partial': raw = raw[:31]
    report = pathlib.Path(os.environ['TMPDIR'])/'space-record-publication-identity.json'
    initial = report.lstat()
    assert stat.S_ISREG(initial.st_mode) and stat.S_IMODE(initial.st_mode) == 0o600
    assert initial.st_uid == os.geteuid() and initial.st_nlink == 1 and initial.st_size == 0
    for entry in pathlib.Path('/proc/self/fd').iterdir():
        try: target = os.readlink(entry)
        except FileNotFoundError: continue
        assert target != str(report), 'native parent report descriptor leaked into child'
    if damage in ['symlink', 'hardlink', 'replace', 'unlink']: report.unlink()
    if damage == 'symlink': report.symlink_to(so)
    elif damage == 'hardlink': os.link(so, report)
    elif damage == 'replace':
        # Deliberate adversarial replacement: valid JSON/current challenge/0600,
        # but a different inode while the parent still holds the original.
        fd = os.open(report, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output: output.write(raw)
    elif damage not in ['missing', 'unlink']:
        if damage == 'wrong-mode': report.chmod(0o644)
        fd = os.open(report, os.O_WRONLY|os.O_NOFOLLOW)
        with os.fdopen(fd, 'w') as output: output.write(raw)
'''

SYNTHETIC_PAIR_COMPILER = '''
if '-shared' in args and any(a.startswith(('-DSRP_BUILD_ID_BYTES=', '-DSRPT_BUILD_ID_BYTES=')) for a in args):
    import struct
    definition = next(a for a in args if a.startswith(('-DSRP_BUILD_ID_BYTES=', '-DSRPT_BUILD_ID_BYTES=')))
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

PUBLICATION_FIXTURE = '''
if len(sys.argv) > 1 and (pathlib.Path(sys.argv[1]).name == 'test_record_publication.exe'
                        or (len(sys.argv) > 3 and sys.argv[3].startswith('tests.wine-record-publication:'))):
    assert 'SPACE_WINE_APPLICATION_OBSERVER_FD' not in os.environ
    root = pathlib.Path(sys.argv[1]).parents[2]
    state = json.loads((pathlib.Path(os.environ['WINEPREFIX']).parent/'state.json').read_text())
    assert state['phase'] == 'publication-consumed' and state['grant'] is None
    assert state['authorized_for'] is None
    manifest = json.loads((root/'wine-publication/build.json').read_text())
    support = json.loads((root/'wine-publication-tests/build.json').read_text())
    assert manifest['abi'] == 1 and support['abi'] == 2
    so = (root/'wine-publication/modules/x86_64-unix/space_record_publication.so').stat()
    test_so = (root/'wine-publication-tests/modules/x86_64-unix/space_record_publication_tests.so').stat()
    assert os.environ['SPACE_WINE_PUBLICATION_BINDING'] == f"{manifest['build_id']}:{so.st_dev}:{so.st_ino}"
    assert os.environ['SPACE_WINE_PUBLICATION_TEST_BINDING'] == f"{support['build_id']}:{test_so.st_dev}:{test_so.st_ino}"
    assert os.environ['WINEDLLPATH'] == ':'.join(str(root/name/'modules') for name in ['wine-publication','wine-publication-tests'])
    with open(os.environ['FIXTURE_LOG'], 'a') as stream:
        stream.write(json.dumps({'wine':sys.argv[1:], 'tool':sys.argv[0], 'args':sys.argv[1:], 'publication':True,
            'env':dict(os.environ), 'state':state, 'umask':pathlib.Path('/proc/self/status').read_text().split('Umask:')[1].splitlines()[0].strip()})+'\\n')
    if os.environ.get('FIXTURE_PUBLICATION_EXIT'): sys.exit(int(os.environ['FIXTURE_PUBLICATION_EXIT']))
    if pathlib.Path(sys.argv[1]).name == 'test_record_publication.exe':
        report = pathlib.Path(os.environ['TMPDIR'])/'space-record-publication-report.json'
        info = report.lstat()
        assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_size == 0
        assert info.st_uid == os.geteuid() and info.st_nlink == 1
        value = dict(version=1, backend='wine-posix', build_id=manifest['build_id'],
                     module_device=so.st_dev, module_inode=so.st_ino,
                     categories={'common':'passed','host-policy':'passed','mapping-authority':'passed','native-windows':'not-exercised'},
                     foreign_uid_probe='not-configured')
        damage = os.environ.get('FIXTURE_PUBLICATION_REPORT_DAMAGE')
        if damage == 'build-id': value['build_id'] = '0'*64
        if damage == 'foreign-uid': value['foreign_uid_probe'] = 'skipped'
        if damage == 'inode': value['module_inode'] += 1
        if damage == 'category': value['categories']['host-policy'] = 'failed'
        if damage == 'replace':
            report.unlink()
            report.touch(mode=0o600)
        if damage == 'mode': report.chmod(0o644)
        raw = json.dumps(value)+'\\n'
        if damage == 'duplicate': raw = raw.rstrip()[:-1]+',"version":1}\\n'
        if damage == 'oversize': raw += ' '*4096
        if damage != 'empty':
            with report.open('w') as stream: stream.write(raw)
    else:
        # Model the actual fixed Windows TEMP mapping, not Linux XDG defaults.
        mapped = os.environ['SPACE_WINE_WINDOWS_TMP']
        assert mapped.startswith('Q:')
        store_root = pathlib.Path(mapped[2:].replace('\\\\', '/'))/'space-record-publication-store'
        assert store_root == pathlib.Path(os.environ['TMPDIR'])/'space-record-publication-store'
        info = store_root.lstat()
        assert stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.geteuid()
        durable = store_root/'fixture-record'
        if sys.argv[3].endswith(':write'):
            assert list(store_root.iterdir()) == []
            durable.write_bytes(b'ordinary-persistent-record\\x00')
        else: assert durable.read_bytes() == b'ordinary-persistent-record\\x00'
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
        for relative in PUBLICATION_INPUTS:
            shutil.copy2(ROOT / relative, self.root / relative)
        (self.root / 'tests').mkdir()
        for name in ('record_publication_wine_support.h', 'record_publication_wine_support_pe.c',
                     'record_publication_wine_support_unix.cpp'):
            shutil.copy2(ROOT / 'tests' / name, self.root / 'tests' / name)
        shutil.copy2(ROOT / 'src/record_publication_wine_binding.h', self.root / 'src')
        for name in ('_windows_repro_evidence.py',):
            shutil.copy2(ROOT / 'scripts' / name, scripts / name)
        shutil.copy2(ROOT / 'src/wine_owned_environment.h', self.root / 'src')
        shutil.copytree(ROOT / "external/date/tzdata", self.root / "external/date/tzdata")
        manifest = self.root / "external/temporal/libical/DEPENDENCY_MANIFEST.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{"fixture":true}')
        self.build = self.root / "build/windows"
        self.build.mkdir(parents=True)
        for name in ("space.exe", "space-cli.exe", "test_record_publication.exe", "runtime.dll", "bcryptprimitives.dll", "BCryptPrimitives.DLL"):
            (self.build / name).write_text("unsafe-old-no-op" if "primitives" in name.lower() else name)
        assets = self.root / "assets/lua"
        assets.mkdir(parents=True)
        (assets / "fixture.fnl").write_text("packaged-assets")
        for relative in REQUIRED_RESOURCE_PATHS:
            resource = self.root / relative
            resource.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, resource)
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
        # Compiler-protocol fixture only: script tools under /tmp are not trusted
        # installed native runtimes. Supply the established inert metadata model
        # in this temporary checkout before CLI main, never in production capture.
        from test_wine_publication_build import support_compiler_launch_metadata
        self.launch_metadata = support_compiler_launch_metadata(self.root)
        builder = scripts / 'wine/build_publication.py'
        source = builder.read_text()
        main_guard = "\nif __name__ == '__main__':"
        assert source.count(main_guard) == 1
        capture = ("\ndef _capture_launch_metadata(repo, session, identity):\n"
                   f"    return {self.launch_metadata!r}\n")
        builder.write_text(source.replace(main_guard, capture + main_guard))
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
        ['WINEDLLOVERRIDES','WINEPREFIX','WINEARCH','WINESERVER','DISPLAY','SPACE_ASSETS_PATH','SPACE_BIN','FENNEL_PATH','FENNEL_MACRO_PATH','XDG_DATA_HOME','XDG_CACHE_HOME','TMPDIR','TEMP','TMP','WINEDLLPATH','SPACE_WINE_PUBLICATION_BINDING']}})+'\\n')
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
            text = first + '\nimport pathlib\n' + SETUP_UTILITIES + '\n' + IDENTITY_FIXTURE + '\n' + PUBLICATION_FIXTURE + '\n' + rest
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


def test_publication_stage_runs_four_fixed_components_before_application(runtime):
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stdout + result.stderr
    from wine import build_publication as builder
    support = builder._recognized_test_output(runtime.root / 'build/wine-publication-tests')[1]
    assert support['abi'] == 2
    assert support['toolchain']['launch'] == runtime.launch_metadata
    assert support['toolchain']['launch_header_sha256'] == hashlib.sha256(
        builder._render_launch_header(runtime.launch_metadata)).hexdigest()
    for relative in ('scripts/wine/build_publication.py', 'src/record_publication_wine_binding.h',
                     'src/record_publication_wine_abi.h'):
        assert support['toolchain']['inputs'][relative] == hashlib.sha256(
            (runtime.root / relative).read_bytes()).hexdigest()
    calls = [call for call in runtime.calls() if call.get('publication')]
    assert len(calls) == 4
    assert [call['umask'] for call in calls] == ['0022', '0002', '0002', '0002']
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    state = json.loads((runtime.root / 'build/wine/sessions' / receipt['ownedSession']['id'] / 'state.json').read_text())
    assert receipt['version'] == 4
    assert state['authorized_for'] == 'application' and state['phase'] == 'publication-passed'
    assert receipt['authorization'] == dict(purpose='application', grant=state['grant'], stopped_generation=state['generation'])
    assert receipt['publication']['reports'][0] == receipt['publication']['reports'][1]
    assert receipt['publication']['stopped_generation'] == state['generation']
    assert runtime.run('test-windows-under-wine.sh').returncode == 0


@pytest.mark.parametrize('probes,crypto', [([0], 'b'), ([10, 0], 'n')])
def test_publication_crypto_handoff_replaces_ambient_from_exact_backend(runtime, probes, crypto):
    runtime.env['SPACE_WINE_PUBLICATION_TEST_CRYPTO'] = 'hostile-ambient'
    runtime.package()
    result = runtime.prepare(probes)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [call for call in runtime.calls() if call.get('publication')]
    assert len(calls) == 4
    assert [call['umask'] for call in calls] == ['0022', '0002', '0002', '0002']
    for call in calls[:2]:
        assert call['env']['SPACE_WINE_PUBLICATION_TEST_CRYPTO'] == crypto
        assert call['env']['WINEDLLOVERRIDES'] == (
            'space_record_publication=b;space_record_publication_tests=b;'
            f'bcryptprimitives={crypto};advapi32,cryptbase=b')
    assert runtime.env['SPACE_WINE_PUBLICATION_TEST_CRYPTO'] == 'hostile-ambient'
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    proof = receipt['publication']
    assert proof['stopped_generation'] == proof['start_generation'] + 4
    assert len(proof['reports']) == len(proof['report_facts']) == 2
    assert all(stat.S_IMODE(facts[2]) == 0o600 for facts in proof['report_facts'])


@pytest.mark.parametrize('backend', ['unknown', 'bcryptprimitives=bn;advapi32,cryptbase=b',
    'prefix-bcryptprimitives=n;advapi32,cryptbase=b', 'bcryptprimitives=b;advapi32,cryptbase=b;extra=b'])
def test_publication_crypto_handoff_refuses_unknown_exact_backend(monkeypatch, backend):
    from wine import publication_validation as validation
    monkeypatch.setattr(validation.artifacts, 'configuration', lambda *args: {'backend': backend})
    stopped = []
    monkeypatch.setattr(validation.prefix, 'stop_session',
                        lambda session, end: stopped.append(end) or SimpleNamespace(ok=True))
    with pytest.raises(ValueError, match='crypto backend'):
        validation.validate_publication(object())  # Must refuse before state/store/launch access.
    assert stopped == [True]


def test_publication_cpp_failure_blocks_later_components_and_grant_promotion(runtime):
    runtime.package()
    runtime.env['FIXTURE_PUBLICATION_EXIT'] = '17'
    result = runtime.prepare([0])
    assert result.returncode != 0
    calls = [call for call in runtime.calls() if call.get('publication')]
    assert len(calls) == 1 and Path(calls[0]['wine'][0]).name == 'test_record_publication.exe'
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    assert receipt['publication'] is None and receipt['authorization']['purpose'] == 'publication'
    directory = runtime.root / 'build/wine/sessions' / receipt['ownedSession']['id']
    state = json.loads((directory / 'state.json').read_text())
    assert state['ended'] and state['authorized_for'] is None and state['grant'] is None
    assert not (directory / 'publication.json').exists()
    assert runtime.run('test-windows-under-wine.sh').returncode != 0
    assert len([call for call in runtime.calls() if call.get('publication')]) == 1
    assert not [call for call in runtime.calls() if 'tests.fast:main' in call.get('wine', [])]


def test_publication_store_root_is_parent_owned_external_and_shared(runtime):
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    directory = runtime.root / 'build/wine/sessions' / receipt['ownedSession']['id']
    root = directory / 'tmp/space-record-publication-store'
    assert root.is_dir(), 'parent must precreate the fixed external store root'
    info = root.lstat()
    assert stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.geteuid()
    assert (root / 'fixture-record').read_bytes() == b'ordinary-persistent-record\x00'
    assert not list((directory / 'data').rglob('fixture-record'))


@pytest.mark.parametrize('damage', ['build-id', 'foreign-uid', 'inode', 'category', 'replace',
                                   'mode', 'duplicate', 'oversize', 'empty'])
def test_publication_invalid_report_cannot_authorize_application(runtime, damage):
    runtime.package()
    runtime.env['FIXTURE_PUBLICATION_REPORT_DAMAGE'] = damage
    result = runtime.prepare([0])
    assert result.returncode != 0
    assert runtime.run('test-windows-under-wine.sh').returncode != 0
    assert not [call for call in runtime.calls() if 'wine' in call and 'tests.fast:main' in call['wine']]


def seed_required_resource_admission(runtime):
    """Seed real canonical bytes so negative controls also run before the fix."""
    from wine import artifacts
    runtime.package()
    for relative in REQUIRED_RESOURCE_PATHS:
        target = runtime.dist / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(runtime.root / relative, target)
    artifacts.seal(runtime.dist, 'native-package')
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stdout + result.stderr


def damage_required_resource(runtime, layer, damage, *, reseal, resource=CATALOG_RESOURCE):
    """Deliberately keep all generic ownership/receipt hashes consistent."""
    from wine import artifacts
    directory = runtime.dist if layer == 'native' else runtime.overlay
    target = directory / resource
    if damage == 'missing':
        target.unlink()
    else:
        target.write_bytes(b'not the canonical documentation')
    if reseal:
        receipt_path = runtime.overlay / 'admission.json'
        receipt = json.loads(receipt_path.read_text())
        if layer == 'native':
            artifacts.seal(directory, 'native-package')
            receipt['package'] = artifacts.inventory(directory)
        else:
            receipt['payload'] = {key: value for key, value in artifacts.inventory(directory).items()
                                  if key != 'admission.json'}
        receipt_path.write_text(json.dumps(receipt))
        artifacts.seal(runtime.overlay, 'wine-overlay')


@pytest.mark.parametrize('resource', REQUIRED_RESOURCE_PATHS)
def test_required_resource_is_canonical_owned_native_and_overlay_payload(runtime, resource):
    from wine import artifacts
    runtime.package()
    canonical = (ROOT / resource).read_bytes()
    target = runtime.dist / resource
    assert target.is_file(), 'native package must contain the canonical documentation beside assets'
    assert target.read_bytes() == canonical == (runtime.root / resource).read_bytes()
    assert artifacts.REQUIRED_RESOURCES == REQUIRED_RESOURCE_PATHS
    digest = hashlib.sha256(canonical).hexdigest()
    assert artifacts.clean_native(runtime.dist)[resource] == digest
    assert json.loads((runtime.dist / MARKER).read_text())['inventory'][resource] == digest
    assert {p.relative_to(runtime.dist / 'docs').as_posix() for p in (runtime.dist / 'docs').rglob('*') if p.is_file()} == {
        'dev/features/entity-type-catalog.md', 'dev/notes/native-sha256.md'}
    assert runtime.prepare([0]).returncode == 0
    assert (runtime.overlay / resource).read_bytes() == canonical
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    assert receipt['version'] == 4
    assert receipt['package'][resource] == receipt['payload'][resource] == digest
    assert artifacts.verify(runtime.overlay, 'wine-overlay')[resource] == digest


def test_native_sha256_page_preserves_full_vendor_notices_and_memzero_attribution():
    page = (ROOT / SHA256_RESOURCE).read_text()
    vendor = ROOT / 'external/wallet-core/trezor-crypto'
    for relative in ('crypto/sha2.c', 'include/TrezorCrypto/sha2.h'):
        header = (vendor / relative).read_text().split('*/', 1)[0] + '*/'
        assert header in page, f'{relative} BSD notice must be verbatim'
    assert (vendor / 'crypto/LICENSE').read_text().strip() in page
    attribution = next(line.removeprefix('// ') for line in (vendor / 'crypto/memzero.c').read_text().splitlines()
                       if line.startswith('// https://github.com/jedisct1/libsodium/'))
    assert attribution in page


@pytest.mark.parametrize('damage', ['missing', 'symlink', 'symlink-parent', 'directory', 'fifo'])
@pytest.mark.parametrize('resource', REQUIRED_RESOURCE_PATHS)
def test_required_resource_invalid_canonical_source_preserves_existing_output(runtime, damage, resource):
    runtime.package()
    before = hashes(runtime.dist), runtime.dist.stat().st_ino, runtime.calls()
    source = runtime.root / resource
    if damage == 'symlink-parent':
        saved = source.parent.with_name('preserved-features')
        source.parent.rename(saved)
        source.parent.symlink_to(saved, target_is_directory=True)
    else:
        source.unlink()
        if damage == 'symlink':
            source.symlink_to(ROOT / resource)
        elif damage == 'directory':
            source.mkdir()
        elif damage == 'fifo':
            os.mkfifo(source)
    result = runtime.run('package-windows-runtime.sh')
    assert result.returncode != 0, 'invalid canonical resource must not authorize replacement'
    assert (hashes(runtime.dist), runtime.dist.stat().st_ino, runtime.calls()) == before


def test_required_resource_docs_input_is_protected_against_output_overlap(runtime):
    before = hashes(runtime.root / 'docs')
    destination = runtime.root / 'docs/packaged-output'
    result = runtime.run('package-windows-runtime.sh', destination)
    assert result.returncode != 0 and 'overlaps a source tree' in result.stderr
    assert not destination.exists() and hashes(runtime.root / 'docs') == before


@pytest.mark.parametrize('mode', ['smoke60', 'fast1800'])
@pytest.mark.parametrize('layer', ['native', 'overlay'])
@pytest.mark.parametrize('damage', ['missing', 'tampered'])
@pytest.mark.parametrize('reseal', [False, True])
@pytest.mark.parametrize('resource', REQUIRED_RESOURCE_PATHS)
def test_required_resource_corruption_refuses_launch_and_cleans_owned_session(runtime, mode, layer, damage, reseal, resource):
    seed_required_resource_admission(runtime)
    damage_required_resource(runtime, layer, damage, reseal=reseal, resource=resource)
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    identifier = receipt['ownedSession']['id']
    before = len(runtime.calls())
    result = subprocess.run([sys.executable, str(runtime.root / 'scripts/wine/artifacts.py'), mode],
                            cwd=runtime.root, env=dict(runtime.env, SPACE_WINE_SESSION_ID=identifier),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0, f'{mode}/{layer}/{damage}/reseal={reseal} launched corrupt documentation'
    calls = runtime.calls()[before:]
    assert not [call for call in calls if 'wine' in call]
    # Admission already stopped this generation. Refusal before launch must end
    # ownership without starting another generation or redundantly stopping it.
    assert not [call for call in calls if 'server' in call]
    state = json.loads((runtime.root / 'build/wine/sessions' / identifier / 'state.json').read_text())
    assert state['ended'] and state['authorized_for'] is None and state['stopped_generation'] == state['generation']


@pytest.mark.parametrize('resource', REQUIRED_RESOURCE_PATHS)
def test_required_resource_is_not_a_terminal_cleanup_dependency(runtime, resource):
    from wine import prefix
    seed_required_resource_admission(runtime)
    receipt_path = runtime.overlay / 'admission.json'
    identifier = json.loads(receipt_path.read_text())['ownedSession']['id']
    session = prefix.load_session(runtime.root, identifier)
    state = session.state()
    state.update(generation=state['generation'] + 1, stopped_generation=None)
    session.save(state)  # Model an outstanding owned generation requiring stop/wait.
    for directory in (runtime.root, runtime.dist, runtime.overlay):
        (directory / resource).unlink()
    receipt_path.unlink()
    before = len(runtime.calls())
    result = subprocess.run([sys.executable, str(runtime.root / 'scripts/wine/artifacts.py'), 'terminal-stop'],
                            cwd=runtime.root, env=dict(runtime.env, SPACE_WINE_SESSION_ID=identifier),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = runtime.calls()[before:]
    assert not [call for call in calls if 'wine' in call]
    assert [call['server'] for call in calls if 'server' in call] == [['-k'], ['-w']]
    state = session.state()
    assert state['ended'] and state['authorized_for'] is None and state['stopped_generation'] == state['generation']


def report_probe_context(runtime, monkeypatch, code=0):
    from wine import artifacts, prefix
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    session = prefix.load_session(runtime.root, receipt['ownedSession']['id'])
    artifacts._remove_identity_report(session, artifacts._identity_file(session))
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    for key, value in [('ROOT', runtime.root), ('BUILD', runtime.root / 'build'),
                       ('PACKAGE', runtime.dist), ('OVERLAY', runtime.overlay)]:
        monkeypatch.setattr(artifacts, key, value)
    spec = importlib.util.spec_from_file_location('report_fixture_toolchain', runtime.root / 'scripts/wine/publication_toolchain.py')
    fixture_toolchain = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_toolchain)
    monkeypatch.setattr(artifacts.publication_toolchain, 'verify_toolchain', fixture_toolchain.verify_toolchain)
    runtime.codes.write_text(json.dumps([code]))
    manifest = json.loads((runtime.root / 'build/wine-publication/build.json').read_text())
    return artifacts, prefix, session, manifest


def report_origin_fd(path):
    info = path.stat()
    matches = []
    for entry in Path('/proc/self/fd').iterdir():
        fd = int(entry.name)
        try:
            opened = os.fstat(fd)
        except OSError:
            continue
        if ((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino)
                and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_WRONLY):
            matches.append(fd)
    assert len(matches) == 1, 'one retained native write-only report descriptor is required'
    return matches[0]


def test_parent_allocates_and_holds_private_report_through_real_child_and_validation(runtime, monkeypatch):
    artifacts, prefix, session, manifest = report_probe_context(runtime, monkeypatch)
    report = session.tmp / artifacts.IDENTITY_REPORT
    launch = prefix.Session.launch
    validate = artifacts.validate_bridge_identity
    observed = {}
    def launch_checked(self, *args, **kwargs):
        assert report.is_file(), 'parent must allocate before Session.launch'
        info = report.stat()
        assert info.st_size == 0 and info.st_mode & 0o777 == 0o600
        assert info.st_uid == os.geteuid() and info.st_nlink == 1
        fd = report_origin_fd(report)
        assert not os.get_inheritable(fd)
        observed.update(fd=fd, origin=(info.st_dev, info.st_ino))
        return launch(self, *args, **kwargs)
    def validate_checked(*args, **kwargs):
        info = os.fstat(observed['fd'])
        assert (info.st_dev, info.st_ino) == observed['origin']
        observed['validated'] = True
        return validate(*args, **kwargs)
    popen = prefix.subprocess.Popen
    def child_umask(argv, **kwargs):
        assert kwargs['close_fds'] and not kwargs.get('pass_fds')
        kwargs['umask'] = 0o002  # Child only; never change the parent's umask.
        return popen(argv, **kwargs)
    monkeypatch.setattr(prefix.Session, 'launch', launch_checked)
    monkeypatch.setattr(artifacts, 'validate_bridge_identity', validate_checked)
    monkeypatch.setattr(prefix.subprocess, 'Popen', child_umask)
    code, bridge, verified = artifacts.probe(session, artifacts.BUILTIN, manifest)
    assert code == 0 and bridge and verified and observed['validated']
    info = report.stat()
    assert (info.st_dev, info.st_ino) == observed['origin'] and info.st_mode & 0o777 == 0o600
    with pytest.raises(OSError) as closed:
        os.fstat(observed['fd'])
    assert closed.value.errno == errno.EBADF


@pytest.mark.parametrize('raw', [0, 10])
@pytest.mark.parametrize('damage', ['replace', 'wrong-mode', 'unlink', 'partial', 'oversize',
                                   'size', 'abi', 'architecture', 'features'])
def test_parent_report_origin_and_contract_cannot_be_replaced_by_child_status(runtime, monkeypatch, raw, damage):
    artifacts, _, session, manifest = report_probe_context(runtime, monkeypatch, raw)
    monkeypatch.setenv('FIXTURE_IDENTITY_DAMAGE', damage)
    code, bridge, verified = artifacts.probe(session, artifacts.BUILTIN, manifest)
    assert code == 20 and bridge is None and verified is None
    if damage == 'replace':
        # The substitute is otherwise valid, including current challenge and
        # pair/copy/SO facts. Only the mandatory retained-origin proof refuses it.
        value, facts = artifacts._identity_file(session)
        assert facts[2] & 0o777 == 0o600 and facts[4] == 1
        assert artifacts.validate_bridge_identity(manifest, value, session.repo)['identity'] == value
    assert not any('process_prng_compat.c' in ' '.join(call.get('cc', [])) for call in runtime.calls())


@pytest.mark.parametrize('outcome', ['success', 'absence', 'raw17', 'raw124', 'invalid', 'exception', 'interrupt'])
@pytest.mark.parametrize('close_error', [False, True])
def test_report_descriptor_closure_preserves_primary_and_never_qualifies_failed_close(
        runtime, monkeypatch, capsys, outcome, close_error):
    raw = {'absence': 10, 'raw17': 17, 'raw124': 124}.get(outcome, 0)
    artifacts, prefix, session, manifest = report_probe_context(runtime, monkeypatch, raw)
    if outcome == 'invalid':
        monkeypatch.setenv('FIXTURE_IDENTITY_DAMAGE', 'partial')
    launch = prefix.Session.launch
    primary = KeyboardInterrupt('fixture launch interrupted') if outcome == 'interrupt' else ValueError('fixture launch failed')
    observed = {'closes': 0}
    def selected_launch(self, *args, **kwargs):
        path = session.tmp / artifacts.IDENTITY_REPORT
        assert path.is_file(), 'origin allocation must precede even exceptional launches'
        observed['fd'] = report_origin_fd(path)
        if outcome in ('exception', 'interrupt'):
            raise primary
        return launch(self, *args, **kwargs)
    close = artifacts.os.close
    def checked_close(fd):
        if fd == observed.get('fd'):
            observed['closes'] += 1
            close(fd)
            if close_error:
                raise OSError(errno.EIO, 'fixture close failed after release')
        else:
            close(fd)
    monkeypatch.setattr(prefix.Session, 'launch', selected_launch)
    monkeypatch.setattr(artifacts.os, 'close', checked_close)
    if outcome in ('exception', 'interrupt'):
        with pytest.raises(type(primary)) as caught:
            artifacts.probe(session, artifacts.BUILTIN, manifest)
        assert caught.value is primary
    else:
        code, bridge, verified = artifacts.probe(session, artifacts.BUILTIN, manifest)
        expected = 20 if outcome == 'invalid' or (close_error and raw in (0, 10)) else raw
        assert code == expected
        if code not in (0, 10):
            assert bridge is None and verified is None
    assert observed['closes'] == 1
    with pytest.raises(OSError) as closed:
        os.fstat(observed['fd'])
    assert closed.value.errno == errno.EBADF
    stderr = capsys.readouterr().err
    if close_error:
        assert stderr.count('Wine admission: phase=report-close errno=5') == 1
    else:
        assert 'phase=report-close' not in stderr


@pytest.mark.parametrize('kind', ['empty', 'partial', 'mode', 'symlink', 'hardlink'])
def test_parent_never_adopts_or_repairs_preexisting_report(runtime, monkeypatch, kind):
    artifacts, _, session, manifest = report_probe_context(runtime, monkeypatch)
    path = session.tmp / artifacts.IDENTITY_REPORT
    target = runtime.root / 'preserved-report'
    target.write_bytes(b'preserve')
    if kind == 'symlink':
        path.symlink_to(target)
    elif kind == 'hardlink':
        os.link(target, path)
    else:
        path.write_bytes(b'partial' if kind == 'partial' else b'')
        path.chmod(0o644 if kind == 'mode' else 0o600)
    before = path.lstat(), path.read_bytes(), target.read_bytes(), runtime.calls()
    with pytest.raises(ValueError, match='already exists'):
        artifacts.probe(session, artifacts.BUILTIN, manifest)
    assert (path.lstat().st_ino, path.lstat().st_mode, path.read_bytes(), target.read_bytes(), runtime.calls()) == (
        before[0].st_ino, before[0].st_mode, before[1], before[2], before[3])


def test_parent_exclusive_open_refuses_a_racing_report(runtime, monkeypatch):
    artifacts, _, session, manifest = report_probe_context(runtime, monkeypatch)
    path = session.tmp / artifacts.IDENTITY_REPORT
    open_fd = artifacts.os.open
    observed = []
    def race(name, flags, *args, **kwargs):
        if Path(name) == path and flags & os.O_CREAT:
            assert flags == os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
            assert args == (0o600,)
            observed.append(True)
            fd = open_fd(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.write(fd, b'preserve racing report')
            os.close(fd)
        return open_fd(name, flags, *args, **kwargs)
    monkeypatch.setattr(artifacts.os, 'open', race)
    before = runtime.calls()
    with pytest.raises(FileExistsError):
        artifacts.probe(session, artifacts.BUILTIN, manifest)
    assert observed == [True] and path.read_bytes() == b'preserve racing report'
    assert runtime.calls() == before


def test_report_allocation_validates_owned_tmp_root_before_creation(runtime, monkeypatch):
    artifacts, _, session, manifest = report_probe_context(runtime, monkeypatch)
    preserved = session.tmp.with_name('preserved-tmp')
    session.tmp.rename(preserved)
    unowned = runtime.root / 'unowned-report-target'
    unowned.mkdir(mode=0o700)
    session.tmp.symlink_to(unowned, target_is_directory=True)
    before = runtime.calls()
    with pytest.raises((ValueError, OSError)):
        artifacts.probe(session, artifacts.BUILTIN, manifest)
    assert list(unowned.iterdir()) == [], 'origin ownership must be checked before creating a sink'
    assert runtime.calls() == before and preserved.is_dir()


@pytest.mark.parametrize('fault', ['nonempty', 'mode', 'hardlink', 'uid', 'type', 'inheritable'])
def test_parent_refuses_invalid_initial_sink_facts_and_closes_without_launch(runtime, monkeypatch, fault):
    artifacts, _, session, manifest = report_probe_context(runtime, monkeypatch)
    path = session.tmp / artifacts.IDENTITY_REPORT
    open_fd, fstat_fd = artifacts.os.open, artifacts.os.fstat
    observed = {}
    def altered_allocation(name, flags, *args, **kwargs):
        fd = open_fd(name, flags, *args, **kwargs)
        if Path(name) == path and flags & os.O_EXCL:
            observed['fd'] = fd
            if fault == 'nonempty':
                os.write(fd, b'partial')
            elif fault == 'mode':
                path.chmod(0o644)  # Deliberate fixture fault, never a production repair.
            elif fault == 'hardlink':
                os.link(path, runtime.root / 'extra-report-link')
            elif fault == 'inheritable':
                os.set_inheritable(fd, True)
        return fd
    def altered_facts(fd):
        info = fstat_fd(fd)
        if fd == observed.get('fd') and fault in ('uid', 'type'):
            fields = list(info)
            if fault == 'uid':
                fields[4] = os.geteuid() + 1
            else:
                fields[0] = stat.S_IFDIR | 0o600
            return os.stat_result(fields)
        return info
    monkeypatch.setattr(artifacts.os, 'open', altered_allocation)
    monkeypatch.setattr(artifacts.os, 'fstat', altered_facts)
    before = runtime.calls()
    assert artifacts.probe(session, artifacts.BUILTIN, manifest) == (20, None, None)
    assert runtime.calls() == before and path.exists()
    with pytest.raises(OSError) as closed:
        fstat_fd(observed['fd'])
    assert closed.value.errno == errno.EBADF


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
    boot, probes, app = [c for c in calls if "wine" in c and not c.get('utility') and not c.get('publication')]
    assert probes["env"]["WINEDLLOVERRIDES"] == "space_record_publication=b;bcryptprimitives=b;advapi32,cryptbase=b"
    assert app["env"]["WINEDLLOVERRIDES"] == 'space_record_publication=b;space_record_publication_tests=b;bcryptprimitives=b;advapi32,cryptbase=b'
    assert app["env"]["WINEPREFIX"] == probes["env"]["WINEPREFIX"]
    assert app["env"]["DISPLAY"] == ":fixture"
    assert app["wine"] == [str(runtime.overlay / "space-cli.exe"), "-m", "tests.fast:main"]
    assert app["env"]["SPACE_ASSETS_PATH"] == str(runtime.overlay / "assets")
    assert app["env"]["SPACE_BIN"] == str(runtime.overlay / "space-cli.exe")
    assert str(runtime.overlay / "assets/lua") in app["env"]["FENNEL_PATH"]
    assert app["env"]["FENNEL_PATH"] == app["env"]["FENNEL_MACRO_PATH"]
    assert [c["timeout"] for c in calls if "timeout" in c] == ["60s", "60s", "900s", "480s", "90s", *["30s"] * 8, "60s", "10s", "15s", "420s", "120s", "120s", "30s", "30s", "10s", "15s", "1800s", "10s", "15s"]
    assert all(c["kill_after"] == "--kill-after=5s" for c in calls if "timeout" in c)
    assert not (runtime.overlay / "bcryptprimitives.dll").exists()


def test_compat_selection_is_fixed_and_receipt_is_not_shell(runtime):
    runtime.package()
    assert runtime.prepare([10, 0]).returncode == 0
    runtime.env["WINEDLLOVERRIDES"] = "malicious=inherited"
    assert runtime.run("test-windows-under-wine.sh").returncode == 0
    wine = [c for c in runtime.calls() if "wine" in c and c['wine'][0] != 'wineboot.exe' and not c.get('utility') and not c.get('publication')]
    assert [c["env"]["WINEDLLOVERRIDES"] for c in wine] == [
        "space_record_publication=b;bcryptprimitives=b;advapi32,cryptbase=b", "space_record_publication=b;bcryptprimitives=n;advapi32,cryptbase=b",
        "space_record_publication=b;space_record_publication_tests=b;bcryptprimitives=n;advapi32,cryptbase=b"]
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


def owned_probe_environment(tmp_path, mode='normal', *, preallocate=True, **overrides):
    if preallocate:
        # Direct C-unit fixtures supply the host-owned sink, not parent admission
        # proof. Real retained-origin behavior is tested through artifacts.probe.
        path = tmp_path / 'space-record-publication-identity.json'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        os.close(fd)
    env = dict(os.environ, PROBE_FIXTURE=mode, PROBE_HOST_TMP=str(tmp_path),
                SPACE_WINE_WINDOWS_TMP=r'Q:\owned\tmp',
                SPACE_WINE_IDENTITY_CHALLENGE='0123456789abcdef',
                TEMP='C:\\registry\\temp', TMP='D:\\registry\\tmp',
                WINEDLLOVERRIDES='space_record_publication=b;bcryptprimitives=b;advapi32,cryptbase=b')
    env.update(overrides)
    return env


def test_actual_probe_opens_only_the_preallocated_report_without_create_or_truncate(tmp_path):
    exe = compile_host(tmp_path, 'probe', str(ROOT / 'scripts/wine/probe.c'))
    path = tmp_path / 'space-record-publication-identity.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    origin = os.fstat(fd)
    try:
        env = owned_probe_environment(tmp_path, preallocate=False)
        result = subprocess.run([str(exe)], env=env,
                                capture_output=True, text=True, umask=0o002)
        assert result.returncode == 0, result.stdout + result.stderr
        assert path.stat().st_ino == origin.st_ino and path.stat().st_mode & 0o777 == 0o600
        assert json.loads(path.read_text())['size'] == 112
        # OPEN_EXISTING does not implement parent freshness or truncate an
        # existing tail. Raw child0 here is not an admission/provenance claim.
        path.write_bytes(b'X' * 4096)
        stale = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
        assert stale.returncode == 0 and path.stat().st_size == 4096
        assert path.read_bytes().endswith(b'X')
    finally:
        os.close(fd)
    path.unlink()
    missing = subprocess.run([str(exe)], env=owned_probe_environment(tmp_path, preallocate=False), capture_output=True, text=True)
    assert missing.returncode == 20 and not path.exists()
    assert 'fixture-crypto-load' not in missing.stdout


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
    assert (tmp_path / 'space-record-publication-identity.json').read_bytes() == b''
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
    env = owned_probe_environment(tmp_path, preallocate=False, PROBE_ENV_CASE=case)
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
                                 'report-open', 'report-write', 'report-short', 'report-close'])
def test_actual_probe_pair_failure_never_reaches_crypto(tmp_path, mode):
    exe = compile_host(tmp_path, 'probe', str(ROOT / 'scripts/wine/probe.c'))
    result = subprocess.run([str(exe)], env=owned_probe_environment(tmp_path, mode),
                            capture_output=True, text=True)
    assert result.returncode == 20, result.stdout + result.stderr
    assert 'fixture-crypto-load' not in result.stdout
    assert 'fixture-request=' not in result.stdout


@pytest.mark.parametrize('mode', ['operation-unsupported', 'operation-denied', 'operation-success',
                                 'operation-flags', 'operation-context', 'operation-sequence', 'operation-event',
                                 'operation-primary-state', 'operation-primary-required', 'operation-cleanup-required',
                                 'operation-empty', 'operation-oversize', 'operation-short', 'operation-truncated',
                                 'operation-size', 'operation-abi', 'operation-opcode', 'operation-reply',
                                 'operation-reserved', 'operation-input', 'operation-buffer'])
def test_actual_probe_requires_benign_operation_refusal_before_report_or_crypto(tmp_path, mode):
    exe = compile_host(tmp_path, 'probe', str(ROOT / 'scripts/wine/probe.c'))
    result = subprocess.run([str(exe)], env=owned_probe_environment(tmp_path, mode), capture_output=True, text=True)
    assert result.returncode == 20, result.stdout + result.stderr
    assert 'fixture-entry1' in result.stdout and 'fixture-crypto-load' not in result.stdout
    assert 'phase=entry1 status=' in result.stderr
    assert (tmp_path / 'space-record-publication-identity.json').read_bytes() == b''
    assert '0123456789abcdef' not in result.stderr and str(tmp_path) not in result.stderr


@pytest.mark.parametrize('features', [1, 7])
def test_actual_probe_rejects_old_or_extra_pair_features_before_operation(tmp_path, features):
    exe = compile_host(tmp_path, 'probe', str(ROOT / 'scripts/wine/probe.c'))
    mode = 'pair-old-features' if features == 1 else 'pair-extra-features'
    result = subprocess.run([str(exe)], env=owned_probe_environment(tmp_path, mode), capture_output=True, text=True)
    assert result.returncode == 20
    assert 'fixture-entry1' not in result.stdout and 'fixture-crypto-load' not in result.stdout
    assert (tmp_path / 'space-record-publication-identity.json').read_bytes() == b''


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
    assert (tmp_path / 'space-record-publication-identity.json').read_bytes() == b''


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
    assert (tmp_path / 'space-record-publication-identity.json').read_bytes() == b''


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
                        architecture=0x8664, features=3)
    assert result.stdout.index('fixture-entry0') < result.stdout.index('fixture-crypto-load')
    assert result.stdout.index('fixture-entry0') < result.stdout.index('fixture-entry1') < result.stdout.index('fixture-crypto-load')
    report.unlink()
    again = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
    assert again.returncode == 20 and not report.exists()
    assert 'fixture-crypto-load' not in again.stdout


def test_receipt_v4_binds_pair_and_fixed_loader_roots(runtime):
    runtime.package()
    result = runtime.prepare([10, 0])
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    assert receipt['version'] == 4
    assert set(receipt['bridge']) == {'abi', 'build_id', 'toolchain', 'files', 'identity'}
    calls = [c for c in runtime.calls() if 'wine' in c and not c.get('utility') and not c.get('publication')]
    assert len(calls) == 3  # one initialization, two same-process capability probes
    for call in calls[1:]:
        assert call['env']['WINEDLLPATH'] == str(runtime.root / 'build/wine-publication/modules')
        assert call['env']['WINEDLLOVERRIDES'].startswith('space_record_publication=b;')
    assert len([c for c in runtime.calls() if c.get('utility')]) == 8


@pytest.mark.parametrize('mode', ['smoke60', 'fast1800'])
def test_admitted_execution_overrides_hostile_publication_binding_last(runtime, mode):
    runtime.env['SPACE_WINE_PUBLICATION_BINDING'] = 'hostile:inherited:input'
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    bridge = receipt['bridge']
    expected = f"{bridge['build_id']}:{bridge['identity']['module_device']}:{bridge['identity']['module_inode']}"
    result = subprocess.run([sys.executable, str(runtime.root / 'scripts/wine/artifacts.py'), mode],
                            cwd=runtime.root, env=runtime.env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    app = [call for call in runtime.calls() if 'wine' in call][-1]
    assert app['env']['SPACE_WINE_PUBLICATION_BINDING'] == expected
    assert app['wine'][1:] == (['--help'] if mode == 'smoke60' else ['-m', 'tests.fast:main'])


def test_application_owned_temp_initialization_precedes_all_startup_work():
    main = (ROOT / 'apps/space/main.cpp').read_text()
    body = main[main.index('int main('):]
    initialize = body.index('record_publication::wine::initialize_process_environment();')
    assert initialize < body.index('executable_path::resolve') < body.index('log_init(')
    assert initialize < body.index('dotenv::load_dotenv_file')
    assert body.index('#ifdef _WIN32') < initialize < body.index('#endif')
    early = body[:body.index('executable_path::resolve')]
    assert 'catch (const std::exception&' in early and 'return 1;' in early


@pytest.mark.parametrize('code', [0, 10])
@pytest.mark.parametrize('damage', ['missing', 'echo', 'pe-id', 'unix-id', 'device', 'inode',
                                   'extra', 'duplicate', 'oversize', 'symlink', 'hardlink', 'feature-old', 'feature-extra'])
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


@pytest.mark.parametrize('mode', ['smoke60', 'fast1800'])
@pytest.mark.parametrize('damage', ['missing-so', 'changed-so', 'extra-output', 'source', 'tool', 'identity', 'build-id', 'discovery-copy'])
def test_admitted_pair_bindings_are_rechecked_before_application(runtime, damage, mode):
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
    elif damage == 'discovery-copy':
        (runtime.overlay / 'space_record_publication.dll').write_bytes(b'foreign discovery copy')
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
    result = subprocess.run([sys.executable, str(runtime.root / 'scripts/wine/artifacts.py'), mode],
                            cwd=runtime.root, env=runtime.env, capture_output=True, text=True)
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
    assert state['ended'] and state['authorized_for'] is None and state['stopped_generation'] is None
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
    assert [c["selected"] for c in runtime.calls() if "wine" in c and not c.get('utility') and not c.get('publication')] == [
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


@pytest.mark.parametrize('name', [*NATIVE_HELPER_BASENAMES, 'space_record_publication.dll', 'space_record_publication.so'])
@pytest.mark.parametrize('relative', ['assets', 'assets/lua/nested'])
def test_forbidden_helper_in_packaged_assets_fails_final_verification(runtime, name, relative):
    source = runtime.root / relative / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("hidden helper")
    before = hashes(runtime.build), hashes(runtime.root / 'assets')
    assert runtime.run("package-windows-runtime.sh").returncode != 0
    assert not runtime.dist.exists()
    assert before == (hashes(runtime.build), hashes(runtime.root / 'assets'))


def test_native_package_excludes_fixed_wine_helpers_without_changing_sources(runtime):
    for name in NATIVE_HELPER_BASENAMES:
        (runtime.build / name).write_text('stale Wine helper')
    assets = runtime.root / 'assets/lua/nested'
    assets.mkdir()
    for name in ('unrelated.so', 'unrelated.exe'):
        (assets / name).write_text('ordinary asset')
    before = hashes(runtime.build), hashes(runtime.root / 'assets')
    forbidden = {name.casefold() for name in NATIVE_HELPER_BASENAMES}
    for _ in range(2):
        runtime.package()
        assert not forbidden & {path.name.casefold() for path in runtime.dist.rglob('*')}
        for name in ('space.exe', 'space-cli.exe', 'runtime.dll'):
            assert (runtime.dist / name).read_bytes() == (runtime.build / name).read_bytes()
        for name in ('unrelated.so', 'unrelated.exe'):
            assert (runtime.dist / 'assets/lua/nested' / name).read_text() == 'ordinary asset'
        assert before == (hashes(runtime.build), hashes(runtime.root / 'assets'))


@pytest.mark.parametrize('name', NATIVE_HELPER_BASENAMES)
def test_clean_native_rejects_resealed_nested_wine_helpers(runtime, monkeypatch, name):
    from wine import artifacts
    runtime.package()
    helper = runtime.dist / 'assets/lua/nested' / name
    helper.parent.mkdir()
    helper.write_text('sealed but forbidden helper')
    artifacts.seal(runtime.dist, 'native-package')
    assert helper.relative_to(runtime.dist).as_posix() in artifacts.verify(runtime.dist, 'native-package')
    before = hashes(runtime.dist), hashes(runtime.build), hashes(runtime.root / 'assets')
    monkeypatch.setattr(artifacts, 'ROOT', runtime.root)
    with pytest.raises(ValueError, match='Forbidden Wine helper'):
        artifacts.clean_native(runtime.dist)
    assert before == (hashes(runtime.dist), hashes(runtime.build), hashes(runtime.root / 'assets'))


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
        assert app["env"]["WINEDLLOVERRIDES"] == "space_record_publication=b;space_record_publication_tests=b;bcryptprimitives=n;advapi32,cryptbase=b"
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
