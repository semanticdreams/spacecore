"""Host publication tests: inert Wine tools plus real host-only ABI/SO checks."""
import ctypes
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))


def test_publication_closed_binding_codec_and_identity(tmp_path):
    source = r'''
#include "record_publication_wine_binding.h"
#include <cassert>
#include <string>
using namespace record_publication::wine::detail;
int main() {
    const std::string id(64, 'a');
    const auto binding = parse_binding(id + ":0:18446744073709551615");
    assert(binding.build_id[0] == 0xaa && binding.module_device == 0 && binding.module_inode == UINT64_MAX);
    const auto maximum = parse_binding(id + ":18446744073709551615:18446744073709551615");
    assert(maximum.module_device == UINT64_MAX && maximum.module_inode == UINT64_MAX);
    const std::string invalid[] = {"", id, id+":1", id+":1:1:1", id+":01:1", id+":1:01",
        id+":+1:1", id+":-1:1", id+": 1:1", id+":1:0", id+":1:", id+"::1",
        id+":18446744073709551616:1", id+":1:18446744073709551616", std::string(64, 'A')+":1:1",
        std::string(63, 'a')+":1:1", id+":1:1\n", id+":1:1\xc2\xa0", id+std::string(107, '0'),
        std::string(1, '\0')+id.substr(1)+":1:1", " "+id+":1:1", id+":1: 1"};
    for (const auto& input : invalid) {
        bool rejected = false;
        try { parse_binding(input); } catch (const std::exception&) { rejected = true; }
        assert(rejected);
    }
    SrpIdentity identity {};
    identity.size = 112; identity.abi = 1; identity.challenge = identity.echo = 42;
    for (unsigned i = 0; i < 32; ++i) identity.pe_build_id[i] = identity.unix_build_id[i] = 0xaa;
    identity.module_inode = UINT64_MAX; identity.architecture = SRP_ARCH_X86_64; identity.features = 3;
    validate_identity(identity, binding, 42);
    for (int field = 0; field < 11; ++field) {
        auto bad = identity;
        switch (field) {
        case 0: ++bad.size; break; case 1: ++bad.abi; break;
        case 2: ++bad.challenge; break; case 3: ++bad.echo; break;
        case 4: ++bad.pe_build_id[31]; break; case 5: ++bad.unix_build_id[0]; break;
        case 6: ++bad.module_device; break; case 7: --bad.module_inode; break;
        case 8: ++bad.architecture; break; case 9: bad.features = 1; break; case 10: bad.features = 7; break;
        }
        bool rejected = false;
        try { validate_identity(bad, binding, 42); } catch (const std::exception&) { rejected = true; }
        assert(rejected);
    }
}
'''
    result = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'src'),
                             '-x', 'c++', '-', '-o', str(tmp_path / 'codec')], input=source,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(tmp_path / 'codec')], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def compile_publication_client_model(output, client_source):
    result = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-D_WIN64', '-pthread',
                             '-I', str(ROOT / 'scripts/tests/wine_adapters'), '-I', str(ROOT / 'src'),
                             str(ROOT / 'scripts/tests/wine_adapters/publication_client.cpp'),
                             str(client_source),
                             str(ROOT / 'src/record_publication_unix.cpp'), str(ROOT / 'src/record_publication.cpp'),
                             '-o', str(output)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope='module')
def publication_client_model(tmp_path_factory):
    output = tmp_path_factory.mktemp('publication-client') / 'client'
    compile_publication_client_model(output, ROOT / 'src/record_publication_wine.cpp')
    return output


@pytest.fixture(scope='module', params=[('fullpath', 'changed'), ('fullpath', 'dropped'),
                                      ('mapper', 'changed'), ('mapper', 'dropped')],
                ids=['fullpath-changed', 'fullpath-dropped', 'mapper-changed', 'mapper-dropped'])
def publication_client_path_mutant(tmp_path_factory, request):
    stage, mutation = request.param
    directory = tmp_path_factory.mktemp(f'publication-client-{stage}-{mutation}')
    source = (ROOT / 'src/record_publication_wine.cpp').read_text()
    leaf = r'Q:\\wrong-leaf' if mutation == 'changed' else 'Q:\\\\'
    argument = 'L"' + leaf + '"'
    if stage == 'mapper':
        argument = f'(static_cast<void>(path), {argument})'
    original, replacement = (("GetFullPathNameW(input.c_str(),", f"GetFullPathNameW({argument},")
                             if stage == 'fullpath' else
                             ("mapper(path.c_str())", f"mapper({argument})"))
    assert source.count(original) == 1
    # Temporary test-only copy: no production fault hook or source edit.
    mutant = directory / 'client-mutated.cpp'
    mutant.write_text(source.replace(original, replacement))
    output = directory / 'client'
    compile_publication_client_model(output, mutant)
    return output, stage


@pytest.mark.parametrize('case', ['normal', 'relative', 'drive-relative', 'dotfile'])
def test_publication_actual_client_path_oracle_rejects_leaf_mutation(publication_client_path_mutant, tmp_path, case):
    executable, stage = publication_client_path_mutant
    path = tmp_path / 'mutant-destination'
    result = subprocess.run([str(executable), case, str(path)], capture_output=True, text=True, timeout=15)
    assert result.returncode == -signal.SIGABRT, f'{case}/{stage}: {result.returncode}: {result.stderr}'
    assertion = 'value == expected_input' if stage == 'fullpath' else 'std::wstring(path) == expected_resolved'
    assert assertion in result.stderr
    assert not path.exists(), 'path corruption must fail before host publication'


@pytest.mark.parametrize('case', ['native', 'unsupported', 'normal', 'relative', 'dotfile', 'drive-relative', 'raw-bytes',
    'pin-once', 'load-fail', 'export-missing', 'export-foreign', 'owner-fail', 'pin-fail', 'mapper-missing',
    'binding-missing', 'binding-empty', 'binding-long', 'binding-wide', 'fresh-binding', 'fresh-identity',
    'identity-status', 'identity-size', 'identity-abi', 'identity-challenge', 'identity-echo', 'identity-pe',
    'identity-unix', 'identity-device', 'identity-inode', 'identity-arch', 'identity-features', 'identity-extra-feature',
    'map-null', 'copy-oom', 'free-fail', 'random-fail', 'remote', 'fullpath-fail', 'fullpath-long',
    'nul', 'reserved', 'reserved-parent', 'reserved-spaced', 'ads', 'unc', 'device', 'slash-unc', 'trailing-dot', 'wildcard',
    'authority', 'hook-denial', 'temp-valid', 'temp-empty', 'temp-malformed', 'temp-set-fail', 'temp-readback'])
def test_publication_actual_client_host_model(publication_client_model, tmp_path, case):
    root = tmp_path / ('root-' + ('\udcff' if case == 'raw-bytes' else 'ascii'))
    (root / 'base').mkdir(parents=True)
    path = root / ('base/record' if case in ('relative', 'drive-relative') else '.record' if case == 'dotfile' else 'missing-leaf')
    result = subprocess.run([str(publication_client_model), case, str(root)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, f'{case}: {result.stdout} {result.stderr}'
    assert not result.stdout and not result.stderr
    if case in ('normal', 'relative', 'dotfile', 'drive-relative', 'raw-bytes', 'pin-once', 'temp-valid', 'fresh-binding', 'fresh-identity'):
        assert path.read_bytes() == (b'second publication' if case == 'pin-once' else b'raw host publication')
        assert path.stat().st_mode & 0o777 == 0o600
        assert not list((path.parent / '.space-publication').iterdir())
        if case in ('normal', 'relative', 'drive-relative', 'dotfile', 'raw-bytes'):
            second = root / ('base/other-record' if case in ('relative', 'drive-relative') else '.other-record' if case == 'dotfile' else 'other-leaf')
            assert second != path and second.read_bytes() == b'second destination'
            assert second.stat().st_mode & 0o777 == 0o600
            assert not list((second.parent / '.space-publication').iterdir())
    else:
        assert not path.exists()


def test_publication_activation_and_all_direct_core_target_wiring():
    # Source gate only; an actual Windows application cross-build is capability-owned.
    source = (ROOT / 'src/record_publication.cpp').read_text()
    dispatch = source[source.index('Result publish('):]
    assert dispatch.index('if (wine::detected())') < dispatch.index('detail::Operation operation')
    early = dispatch[:dispatch.index('detail::Operation operation')]
    assert '#ifdef _WIN32' in early and '#endif' in early
    assert 'return wine::publish(destination, expected_bytes, hooks);' in early
    cmake = (ROOT / 'CMakeLists.txt').read_text()
    assert 'if(NOT WIN32)\n    list(REMOVE_ITEM SOURCES ${CMAKE_CURRENT_SOURCE_DIR}/src/record_publication_wine.cpp)\nendif()' in cmake
    for target in ('test_record_publication', 'test_record_publication_operation'):
        assert f'target_sources({target} PRIVATE src/record_publication_wine.cpp)' in cmake
        assert f'target_link_libraries({target} advapi32)' in cmake
    assert 'list(REMOVE_ITEM SOURCES ${CMAKE_CURRENT_SOURCE_DIR}/src/record_publication_unix.cpp)' in cmake


def test_publication_windows_reserved_component_pure_model(tmp_path):
    # Linux fs::path::wstring cannot model native Windows UTF16. Compile the
    # actual pure production predicate for BMP device digits, not another policy.
    client = (ROOT / 'src/record_publication_wine.cpp').read_text()
    predicate = client[client.index('bool component_valid('):client.index('std::wstring windows_path(')]
    source = '#include "wine_owned_environment.h"\n#include <string>\n#include <cassert>\n' + predicate + r'''
int main() {
    for (const auto* value : {L"COM\u00b9.txt", L"lpt\u00b2", L"COM\u00b3 .txt", L"CON .txt",
                             L"NUL", L"PRN.log", L"AUX", L"CONIN$", L"CONOUT$", L"LPT9", L"name.", L"name "})
        assert(!component_valid(value));
    for (const auto* value : {L".record", L"ordinary", L"com10", L"COM0", L"com1-extra", L"report\u00b9.txt"})
        assert(component_valid(value));
}
'''
    result = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                             '-I', str(ROOT / 'scripts/tests/wine_adapters'), '-I', str(ROOT / 'src'),
                             '-x', 'c++', '-', '-o', str(tmp_path / 'components')], input=source,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(tmp_path / 'components')], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


class ToolchainFixture:
    version = '9.0~repack-4build3'

    def __init__(self, path, monkeypatch):
        self.root = path / 'repo'
        self.root.mkdir()
        (self.root / 'scripts/wine').mkdir(parents=True)
        shutil.copy2(ROOT / 'scripts/setup-windows-build-host.sh', self.root / 'scripts/setup-windows-build-host.sh')
        module = ROOT / 'scripts/wine/publication_toolchain.py'
        if module.exists():
            shutil.copy2(module, self.root / 'scripts/wine/publication_toolchain.py')
        self.bin = path / 'bin'
        self.bin.mkdir()
        self.lib = path / 'lib/wine'
        self.lib.mkdir(parents=True)
        self.log = path / 'calls.jsonl'
        self.db_path = path / 'packages.json'
        self.packages = {}
        self.files = {}
        for name in ('wine', 'wine64', 'libwine', 'wine64-tools', 'libwine-dev'):
            architecture = 'all' if name == 'wine' else 'amd64'
            self.packages[f'{name}:{architecture}'] = dict(installed=self.version, source='wine', source_version=self.version,
                                       version=self.version, architecture=architecture,
                                       origins=[dict(origin='Ubuntu', trusted=True, archive='noble', site='mirror.example')])
        self.tool('wine64', self.lib, runtime=True)
        (self.bin / 'wine-stable').symlink_to(self.lib / 'wine64')
        self.files['wine:all'] = [str(self.bin / 'wine-stable')]
        self.files['wine64:amd64'] = [str(self.lib / 'wine64')]
        self.files['libwine:amd64'] = []
        self.files['wine64-tools:amd64'] = []
        for name in ('winegcc', 'winebuild'):
            self.tool(name, self.lib)
            alias = self.bin / (name + '-stable')
            alias.symlink_to(self.lib / name)
            self.files['wine64-tools:amd64'].extend([str(alias), str(self.lib / name)])
        windows = path / 'include/wine/wine/windows'
        windows.mkdir(parents=True)
        self.files['libwine-dev:amd64'] = []
        for name in ('winternl.h', 'windef.h', 'winbase.h'):
            header = windows / name
            header.write_text('/* inert installed public Wine9 header fixture */\n')
            self.files['libwine-dev:amd64'].append(str(header))
        for name in ('g++', 'x86_64-w64-mingw32-gcc-posix', 'x86_64-w64-mingw32-g++-posix'):
            self.tool(name, self.bin)
        for name in ('cmake', 'git', 'pkg-config', 'nasm', 'llvm-ml-14', 'curl', 'zip', 'pwsh',
                     'autoconf', 'rustc', 'ccache', 'ninja', 'rg'):
            self.executable(name, 'pass')
        self.executable('rustup', "print('x86_64-pc-windows-gnu')")
        self.executable('sudo', 'pass')  # Log only; NEVER delegate to a real elevated command.
        self.executable('apt-get', "print(os.environ.get('FIXTURE_TRANSACTION', ''))")
        self.executable('dpkg-query', '''
data = json.loads(pathlib.Path(os.environ['FIXTURE_DB']).read_text())
packages, files = data['packages'], data['files']
args = sys.argv[1:]
if args[0] == '-S':
 for name, paths in files.items():
  if args[1] in paths: print(name + ': ' + args[1]); sys.exit(0)
 sys.exit(1)
name = args[-1]
if ':' not in name:
 matches = [key for key in packages if key in (name+':amd64', name+':all')]
 if len(matches) != 1: sys.exit(1)
 name = matches[0]
if name not in packages or not packages[name]['installed']: sys.exit(1)
if args[0] == '-L':
 print('\\n'.join(files[name])); sys.exit(0)
p = packages[name]
print('\\t'.join([name, p['installed'], p['source'], p['source_version'], p['architecture']]))
''')
        # Supply inert python-apt metadata to the actual resolver/CLI. The trust
        # and signed Origin fields are data, not inferred from a mirror hostname.
        apt_dir = path / 'python'
        apt_dir.mkdir()
        (apt_dir / 'apt.py').write_text('''
import json, os
from types import SimpleNamespace as NS
class Cache(dict):
 def __init__(self):
  data=json.load(open(os.environ['FIXTURE_DB']))
  for name,p in data['packages'].items():
   version=NS(version=p['version'], source_name=p['source'], source_version=p['source_version'],
              architecture=p['architecture'], origins=[NS(**v) for v in p['origins']])
   installed=NS(version=p['installed'], source_name=p['source'], source_version=p['source_version'], architecture=p['architecture']) if p['installed'] else None
   self[name]=NS(name=name.split(':')[0], fullname=name, installed=installed, versions=[version] if p['version'] else [])
 def __iter__(self): return iter(self.values())
''')
        self.env = dict(os.environ, PATH=f'{self.bin}:/usr/bin:/bin', PYTHONPATH=str(apt_dir),
                        WINE_CMD=str(self.bin / 'wine-stable'), FIXTURE_DB=str(self.db_path), FIXTURE_LOG=str(self.log),
                        VCPKG_ROOT=str(path / 'vcpkg'), HOME=str(path / 'home'))
        Path(self.env['HOME']).mkdir()
        Path(self.env['VCPKG_ROOT']).mkdir()
        binary = Path(self.env['VCPKG_ROOT']) / 'vcpkg'
        binary.write_text('#!/bin/sh\nexit 0\n')
        binary.chmod(0o755)
        for key, value in self.env.items():
            monkeypatch.setenv(key, value)
        # The apt module may already have been loaded by an earlier case.
        monkeypatch.syspath_prepend(str(apt_dir))
        monkeypatch.delitem(sys.modules, 'apt', raising=False)
        self.save()

    def executable(self, name, body, directory=None):
        path = (directory or self.bin) / name
        path.write_text(f'#!{sys.executable}\nimport json, os, pathlib, sys\n'
                        "with open(os.environ['FIXTURE_LOG'], 'a') as f: f.write(json.dumps([sys.argv[0], *sys.argv[1:]])+'\\n')\n" + body + '\n')
        path.chmod(0o755)

    def tool(self, name, directory, runtime=False):
        target = 'x86_64-w64-mingw32' if name.startswith('x86_64-') else 'x86_64-linux-gnu'
        self.executable(name, "raise AssertionError('Wine must never run')" if runtime else
                        f"print({target!r} if '-dumpmachine' in sys.argv else '13.2.0' if '-dumpversion' in sys.argv else 'fixture host build tool 9.0')", directory)

    def save(self):
        self.db_path.write_text(json.dumps(dict(packages=self.packages, files=self.files)))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def resolver(self):
        module_path = ROOT / 'scripts/wine/publication_toolchain.py'
        assert module_path.is_file(), 'matched publication toolchain resolver is not implemented'
        return importlib.import_module('wine.publication_toolchain')

    def preflight(self, monkeypatch):
        import opencode_windows_ci_repro as wrapper
        monkeypatch.setattr(wrapper, 'ensure_space_repo', lambda root: self.root)
        for relative in wrapper.REQUIRED_SCRIPTS:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        target = self.root / 'vcpkg/vcpkg'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('#!/bin/sh\nexit 0\n')
        target.chmod(0o755)
        return wrapper.preflight(self.root)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    return ToolchainFixture(tmp_path, monkeypatch)


def test_missing_winegcc_preflight_reports_without_wine_or_build_calls(fixture, monkeypatch):
    (fixture.lib / 'winegcc').unlink()
    result = fixture.preflight(monkeypatch)
    assert result['status'] == 'fail'
    assert 'winegcc' in result['evidence']['missing']
    assert not [call for call in fixture.calls() if Path(call[0]).name.startswith('wine')]


@pytest.mark.parametrize('pinned', [False, True])
def test_resolve_records_matched_stable_logical_pair_headers_and_host_identity(fixture, pinned):
    module = fixture.resolver()
    runtime = dict(executable=str(fixture.lib / 'wine64'), version='wine-9.0 (fixture)',
                   sha256=hashlib.sha256((fixture.lib / 'wine64').read_bytes()).hexdigest()) if pinned else None
    identity = module.resolve_toolchain(fixture.root, runtime)
    assert identity['runtime'] == runtime
    assert identity['tools']['winegcc']['executable'] == str(fixture.lib / 'winegcc')
    assert identity['tools']['winebuild']['executable'] == str(fixture.lib / 'winebuild')
    assert identity['headers']['package']['version'] == fixture.version
    assert identity['headers']['files']
    module.verify_toolchain(identity)
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable')]
    assert all(call[1:] in (['--version'], ['-dumpversion'], ['-dumpmachine']) for call in fixture.calls()
               if Path(call[0]).name in ('g++', 'winegcc', 'winebuild'))


def test_public_sdk_resolver_accepts_only_installed_public_headers(fixture):
    module = fixture.resolver()
    identity = module.resolve_toolchain(fixture.root)
    files = identity['headers']['files']
    windows = Path(fixture.files['libwine-dev:amd64'][0]).parent
    assert set(files) == {str(windows / name) for name in ('winternl.h', 'windef.h', 'winbase.h')}
    assert not any(path.endswith('/unixlib.h') for path in files)
    assert builder_module()._headers(identity) == (windows, windows.parent.parent)
    module.verify_toolchain(identity)
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable', 'wine')]


@pytest.mark.parametrize('damage', ['missing-winternl', 'missing-windef', 'missing-winbase',
                                    'mixed-root', 'duplicate-root', 'system-mingw', 'wrong-source'])
def test_public_sdk_resolver_and_builder_refuse_incomplete_or_mixed_inventory(fixture, damage):
    paths = [Path(path) for path in fixture.files['libwine-dev:amd64']]
    if damage.startswith('missing-'):
        name = damage.removeprefix('missing-') + '.h'
        fixture.files['libwine-dev:amd64'] = [str(path) for path in paths if path.name != name]
    elif damage in ('mixed-root', 'duplicate-root'):
        other = fixture.root / 'other/include/wine/wine/windows'
        other.mkdir(parents=True)
        copies = paths[-1:] if damage == 'mixed-root' else paths
        for path in copies:
            shutil.copy2(path, other / path.name)
        retained = paths[:-1] if damage == 'mixed-root' else paths
        fixture.files['libwine-dev:amd64'] = [str(path) for path in retained] + [str(other / path.name) for path in copies]
    elif damage == 'system-mingw':
        other = fixture.root / 'system-mingw/include'
        other.mkdir(parents=True)
        for path in paths:
            shutil.copy2(path, other / path.name)
        fixture.files['libwine-dev:amd64'] = [str(other / path.name) for path in paths]
    else:
        fixture.packages['libwine-dev:amd64']['source'] = 'other-sdk'
    fixture.save()
    with pytest.raises(ValueError):
        fixture.resolver().resolve_toolchain(fixture.root)
    if damage != 'wrong-source':
        inventory = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                     for path in fixture.files['libwine-dev:amd64']}
        with pytest.raises(ValueError):
            builder_module()._headers(dict(headers=dict(files=inventory)))


def test_public_sdk_all_header_hashes_remain_pinned(fixture):
    windows = Path(fixture.files['libwine-dev:amd64'][0]).parent
    extra = windows.parent / 'wine-public-extra.h'
    extra.write_text('/* additional installed public SDK input */\n')
    fixture.files['libwine-dev:amd64'].append(str(extra))
    fixture.save()
    module = fixture.resolver()
    identity = module.resolve_toolchain(fixture.root)
    assert identity['headers']['files'][str(extra)] == hashlib.sha256(extra.read_bytes()).hexdigest()
    extra.write_text('/* modified installed SDK input */\n')
    with pytest.raises(ValueError, match='changed'):
        module.verify_toolchain(identity)


def test_public_sdk_bridge_declarations_compile_as_host_abi_model(tmp_path):
    # This checks the actual minimal C declaration/assertion block, NOT the PE
    # or installed Wine SDK. No fake public/private Wine header is created.
    bridge = (ROOT / 'scripts/wine/record_publication_bridge.c').read_text()
    assert '#include <wine/unixlib.h>' not in bridge
    assert 'wine-9.0/include/wine/unixlib.h' in bridge
    assert '__typeof__(&__wine_unix_call)' not in bridge
    start = bridge.index('typedef uint64_t SrpUnixHandle;')
    end = bridge.index('static const uint8_t build_id', start)
    source = '''#include <stdint.h>
typedef int32_t NTSTATUS;
#define WINAPI __attribute__((ms_abi))
enum { MemoryWineUnixFuncs = 1000 };
''' + bridge[start:end] + '''
_Static_assert(__builtin_types_compatible_p(SrpUnixCall,
    int32_t (WINAPI *)(uint64_t, unsigned int, void *)), "dispatch signature");
_Static_assert(!__builtin_types_compatible_p(SrpUnixCall,
    int32_t (*)(uint64_t, unsigned int, void *)), "dispatch must not become SysV");
'''
    result = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-x', 'c', '-c',
                             '-o', str(tmp_path / 'bridge-abi-model.o'), '-'],
                            input=source, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope='module')
def publication_bridge_model(tmp_path_factory):
    directory = tmp_path_factory.mktemp('publication-bridge-model')
    output = directory / 'bridge-model'
    definition = '-DSRP_BUILD_ID_BYTES={' + ','.join(['1'] * 32) + '}'
    result = subprocess.run(['cc', '-std=c11', '-Wall', '-Werror', '-D_WIN64', definition,
                             '-I', str(ROOT / 'scripts/tests/wine_adapters'), '-I', str(ROOT / 'src'),
                             str(ROOT / 'scripts/wine/record_publication_bridge.c'),
                             str(ROOT / 'scripts/tests/wine_adapters/publication_bridge.c'), '-o', str(output)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return output


@pytest.mark.parametrize('case', ['thread', 'close-thread', 'thread-error', 'thread-zero-error', 'process-error',
    'process-zero-error', 'close-zero-error', 'close-process', 'close-preserve', 'deny-disabled', 'deny-enabled', 'groups-oversized', 'groups-tiny',
    'groups-count', 'groups-short', 'sid-null', 'sid-before', 'sid-header', 'sid-short', 'sid-unaligned',
    'sid-revision', 'sid-count', 'sid-extent', 'priv-count', 'priv-short', 'duplicate', 'extra',
    'limited', 'elevation-unknown', 'elevation-size', 'ordinary', 'default', 'groups-max', 'identity',
    'identity-corrupt', 'unknown', 'bad-header', 'bad-opcode', 'bad-event', 'snapshot', 'cancel', 'release',
    'cleanup', 'self-error', 'ntdll-error', 'export-error', 'zero-handle', 'module-query-error'])
def test_publication_direct_bridge_authority(publication_bridge_model, case):
    result = subprocess.run([str(publication_bridge_model), case], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'publication bridge host model passed\n'


@pytest.mark.parametrize('case,count', [('missing', 21), ('high', 21), ('unknown-low', 21), ('removed', 21),
                                      ('unknown-attributes', 21), ('attributes', 4), ('authority-event', 4),
                                      ('size-error', 3), ('size-success', 3), ('size-zero', 3),
                                      ('read-error', 3), ('read-zero', 3), ('read-overflow', 3),
                                      ('size-zero-error', 3), ('read-zero-error', 3)])
def test_publication_direct_bridge_authority_matrix(publication_bridge_model, case, count):
    for index in range(count):
        result = subprocess.run([str(publication_bridge_model), case, str(index)],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, f'{case}/{index}: {result.stderr}'


@pytest.mark.parametrize('compiler,standard', [('x86_64-w64-mingw32-gcc-posix', 'c11'),
                                             ('x86_64-w64-mingw32-g++-posix', 'c++17')])
def test_publication_authority_header_windows_width_compile_only(tmp_path, compiler, standard):
    cc = shutil.which(compiler)
    assert cc, 'tiny header-only MinGW C/C++ compilation is required, no PE execution'
    source = '''#include "record_publication_wine_authority.h"
DWORD callable(void) { return space_record_publication_check_authority(); }
'''
    result = subprocess.run([cc, '-x', 'c++' if standard == 'c++17' else 'c', f'-std={standard}',
                             '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'src'), '-c',
                             '-o', str(tmp_path / 'authority.o'), '-'],
                            input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_publication_direct_bridge_real_native_cleanup_cannot_resume_commit(tmp_path):
    definition = '-DSRP_BUILD_ID_BYTES={' + ','.join(['1'] * 32) + '}'
    objects = []
    for name, relative in [('bridge', 'scripts/wine/record_publication_bridge.c'),
                           ('model', 'scripts/tests/wine_adapters/publication_bridge.c')]:
        obj = tmp_path / (name + '.o')
        result = subprocess.run(['cc', '-std=c11', '-Wall', '-Werror', '-D_WIN64', '-DSRP_MODEL_NATIVE', definition,
                                 '-I', str(ROOT / 'scripts/tests/wine_adapters'), '-I', str(ROOT / 'src'),
                                 '-c', str(ROOT / relative), '-o', str(obj)], capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        objects.append(str(obj))
    executable = tmp_path / 'native-bridge-model'
    result = subprocess.run(['c++', '-std=c++17', '-pthread', '-I', str(ROOT / 'src'), *objects,
                             str(ROOT / 'src/record_publication_unix.cpp'), str(ROOT / 'src/record_publication.cpp'),
                             '-o', str(executable)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    destination = tmp_path / 'record'
    result = subprocess.run([str(executable), 'native-recovery', str(destination)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'native bridge recovery passed\n'
    assert destination.read_bytes() == b'native guarded bytes'
    assert not list((tmp_path / '.space-publication').iterdir())


@pytest.mark.parametrize('compiler,standard', [('cc', 'c11'), ('c++', 'c++17')])
def test_publication_authority_optimized_raw_records(tmp_path, compiler, standard):
    objects = []
    definition = '-DSRP_BUILD_ID_BYTES={' + ','.join(['1'] * 32) + '}'
    for name, relative in [('bridge', PE_SOURCE), ('model', 'scripts/tests/wine_adapters/publication_bridge.c')]:
        obj = tmp_path / (name + '.o')
        result = subprocess.run(['cc', '-std=c11', '-O2', '-fstrict-aliasing', '-Wall', '-Werror',
                                 '-D_WIN64', definition, '-Dmain=publication_model_main',
                                 '-I', str(ROOT / 'scripts/tests/wine_adapters'), '-I', str(ROOT / 'src'),
                                 '-c', str(ROOT / relative), '-o', str(obj)],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        objects.append(str(obj))
    source = '''#include "record_publication_wine_authority.h"
#include <stdlib.h>
#ifdef __cplusplus
extern "C" void publication_model_configure(const char *);
#else
void publication_model_configure(const char *);
#endif
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    publication_model_configure(argv[1]);
    return space_record_publication_check_authority() == (DWORD)strtoul(argv[2], NULL, 10) ? 0 : 1;
}
'''
    obj = tmp_path / 'authority.o'
    result = subprocess.run([compiler, f'-std={standard}', '-O2', '-fstrict-aliasing', '-Wall', '-Werror',
                             '-I', str(ROOT / 'scripts/tests/wine_adapters'), '-I', str(ROOT / 'src'),
                             '-x', 'c++' if standard == 'c++17' else 'c', '-c', '-o', str(obj), '-'],
                            input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    executable = tmp_path / 'optimized-authority-model'
    result = subprocess.run([compiler, '-O2', '-fstrict-aliasing', *objects, str(obj), '-o', str(executable)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    cases = [(case, 0) for case in ['ordinary', 'default', 'groups-max']]
    cases += [(case, 5) for case in ['deny-disabled', 'deny-enabled', 'missing', 'extra', 'duplicate',
                                   'high', 'unknown-low', 'removed', 'unknown-attributes', 'limited', 'elevation-unknown']]
    cases += [(case, 13) for case in ['groups-count', 'groups-short', 'sid-short', 'sid-revision',
                                    'sid-count', 'sid-extent', 'priv-count', 'priv-short']]
    for case, error in cases:
        result = subprocess.run([str(executable), case, str(error)], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, f'{case}: {result.stderr}'
        assert not result.stdout and not result.stderr


def test_publication_authority_cpp_runtime_rejects_unknown_scalar_without_enum_ub(tmp_path):
    objects = []
    definition = '-DSRP_BUILD_ID_BYTES={' + ','.join(['1'] * 32) + '}'
    for name, relative in [('bridge', PE_SOURCE), ('model', 'scripts/tests/wine_adapters/publication_bridge.c')]:
        obj = tmp_path / (name + '.o')
        result = subprocess.run(['cc', '-std=c11', '-Wall', '-Werror', '-D_WIN64', definition,
                                 '-Dmain=publication_model_main', '-I', str(ROOT / 'scripts/tests/wine_adapters'),
                                 '-I', str(ROOT / 'src'), '-c', str(ROOT / relative), '-o', str(obj)],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        objects.append(str(obj))
    source = '''#include "record_publication_wine_authority.h"
extern "C" void publication_model_configure(const char *);
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    publication_model_configure(argv[1]);
    const DWORD error = space_record_publication_check_authority();
    return error == (argv[1][0] == 'o' ? 0 : ERROR_ACCESS_DENIED) ? 0 : 1;
}
'''
    obj = tmp_path / 'cpp.o'
    result = subprocess.run(['c++', '-std=c++17', '-fsanitize=undefined', '-fno-sanitize-recover=undefined',
                             '-I', str(ROOT / 'scripts/tests/wine_adapters'), '-I', str(ROOT / 'src'),
                             '-x', 'c++', '-c', '-o', str(obj), '-'], input=source,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    executable = tmp_path / 'cpp-authority-model'
    result = subprocess.run(['c++', '-fsanitize=undefined', *objects, str(obj), '-o', str(executable)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    for case in ['ordinary', 'elevation-unknown']:
        result = subprocess.run([str(executable), case], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert not result.stdout and not result.stderr


COMPILER_ROLES = [('host_cxx', 'g++', 'x86_64-linux-gnu'),
                  ('mingw_cc', 'x86_64-w64-mingw32-gcc-posix', 'x86_64-w64-mingw32'),
                  ('mingw_cxx', 'x86_64-w64-mingw32-g++-posix', 'x86_64-w64-mingw32')]


def compiler_version_fixture(fixture, command, token, target):
    fixture.executable(command,
                       f"print({target!r} if '-dumpmachine' in sys.argv else "
                       f"{token!r} if '-dumpversion' in sys.argv else 'fixture compiler --version')")


@pytest.mark.parametrize('cc,cxx', [('13-posix', '13.2.0'), ('13.2.0', '13-posix'),
                                  ('13-posix', '13-posix'), ('7-posix', '7.2-posix'),
                                  ('13.2.0-posix', '13.2-posix')])
def test_mingw_dumpversion_accepts_scoped_posix_versions(fixture, cc, cxx):
    for (_, command, target), token in zip(COMPILER_ROLES, ['13', cc, cxx]):
        compiler_version_fixture(fixture, command, token, target)
    module = fixture.resolver()
    identity = module.resolve_toolchain(fixture.root)
    for key, command, target in COMPILER_ROLES:
        assert set(identity['tools'][key]) == {'executable', 'sha256', 'version', 'target'}
        assert identity['tools'][key]['target'] == target
        assert identity['tools'][key]['version'] == 'fixture compiler --version'
    module.verify_toolchain(identity)
    dumped = [Path(call[0]).name for call in fixture.calls() if call[1:] == ['-dumpversion']]
    assert all(dumped.count(command) == 2 for _, command, _ in COMPILER_ROLES)
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable', 'wine')]


@pytest.mark.parametrize('key,command,target', COMPILER_ROLES)
@pytest.mark.parametrize('token', ['7', '13', '13.2', '13.2.0'])
def test_mingw_dumpversion_preserves_supported_numeric_versions(fixture, key, command, target, token):
    compiler_version_fixture(fixture, command, token, target)
    identity = fixture.resolver().resolve_toolchain(fixture.root)
    assert identity['tools'][key]['target'] == target


@pytest.mark.parametrize('key,command,target', COMPILER_ROLES)
@pytest.mark.parametrize('token', ['6', '6.9.0', '6-posix', '13-win32', '13.2-win32',
                                  'garbage', '13junk', '13.bad', '13.2junk', '13.2-posix-junk', '13.2\n14',
                                  '13\n\n', 'True', 'False'])
def test_mingw_dumpversion_rejects_old_or_malformed_tokens(fixture, key, command, target, token):
    compiler_version_fixture(fixture, command, token, target)
    with pytest.raises(ValueError, match='GCC C\\+\\+17-capable toolchain required'):
        fixture.resolver().resolve_toolchain(fixture.root)
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable', 'wine')]


@pytest.mark.parametrize('token', ['13-posix', '13.2-posix', '13.2.0-posix'])
def test_mingw_dumpversion_never_allows_posix_suffix_for_host(fixture, token):
    compiler_version_fixture(fixture, 'g++', token, 'x86_64-linux-gnu')
    with pytest.raises(ValueError, match='GCC C\\+\\+17-capable toolchain required: g\\+\\+'):
        fixture.resolver().resolve_toolchain(fixture.root)


def test_mingw_dumpversion_error_bounds_and_escapes_raw_token(fixture):
    token = 'x' * 200 + '\t\x1b\u202eFalse'
    compiler_version_fixture(fixture, COMPILER_ROLES[1][1], token, COMPILER_ROLES[1][2])
    with pytest.raises(ValueError) as error:
        fixture.resolver().resolve_toolchain(fixture.root)
    message = str(error.value)
    assert 'dumpversion=' in message and 'token-truncated=true' in message
    assert all(escape in message for escape in ('\\t', '\\u001b', '\\u202e'))
    assert all(' ' <= char < '\x7f' for char in message) and len(message.encode('ascii')) <= 240


def test_mingw_dumpversion_posix_does_not_bypass_target_check(fixture):
    command = COMPILER_ROLES[2][1]
    compiler_version_fixture(fixture, command, '13-posix', 'i686-w64-mingw32')
    with pytest.raises(ValueError, match='Unsupported build tool target'):
        fixture.resolver().resolve_toolchain(fixture.root)
    assert not [call for call in fixture.calls() if Path(call[0]).name == command and call[1:] == ['-dumpversion']]


@pytest.mark.parametrize('damage', ['header', 'tool', 'tool-version', 'header-version', 'runtime', 'tool-role'])
def test_toolchain_verification_rejects_changed_pinned_files_or_package_mismatch(fixture, damage):
    module = fixture.resolver()
    identity = module.resolve_toolchain(fixture.root)
    if damage == 'header':
        Path(fixture.files['libwine-dev:amd64'][0]).write_text('changed header')
    elif damage == 'tool':
        (fixture.lib / 'winegcc').write_text('changed tool')
    elif damage in ('tool-version', 'header-version'):
        fixture.packages['wine64-tools:amd64' if damage == 'tool-version' else 'libwine-dev:amd64']['source_version'] = '8.0'
        fixture.save()
    elif damage == 'runtime':
        (fixture.lib / 'wine64').write_text('changed selected runtime')
    else:
        # The selected Wine is canonical lib/wine/wine64 in this fixture, so
        # corrupt its actual backend role, not an unrelated requested sibling.
        alias = fixture.lib / 'winegcc'
        alias.unlink()
        alias.symlink_to(fixture.bin / 'g++')
    with pytest.raises((ValueError, OSError)):
        module.verify_toolchain(identity)


@pytest.mark.parametrize('origin,trusted', [('WineHQ', True), ('Ubuntu', False)])
def test_setup_refuses_unsupported_origin_before_any_elevated_call(fixture, origin, trusted):
    fixture.packages['libwine-dev:amd64']['origins'][0].update(origin=origin, trusted=trusted)
    fixture.save()
    result = subprocess.run([str(ROOT / 'scripts/setup-windows-build-host.sh')], env=fixture.env,
                            text=True, capture_output=True, timeout=20)
    assert result.returncode != 0
    assert not [call for call in fixture.calls() if Path(call[0]).name == 'sudo']


@pytest.mark.parametrize('transaction', ['Remv wine64 [9.0]', 'Inst wine64 [9.0] (10.0 Ubuntu:24.04 [amd64])',
                                     'Inst libwine [9.0] (8.0 Ubuntu:24.04 [amd64])'])
def test_setup_simulated_runtime_removal_upgrade_or_replacement_refuses_without_sudo(fixture, monkeypatch, transaction):
    import opencode_windows_ci_repro as wrapper
    monkeypatch.setenv('FIXTURE_TRANSACTION', transaction)
    monkeypatch.setattr(wrapper, 'ensure_space_repo', lambda root: fixture.root)
    monkeypatch.setattr(wrapper, '_is_ubuntu_host', lambda: True)
    result = wrapper.setup_host(fixture.root)
    assert result['status'] == 'human_decision_required'
    assert not [call for call in fixture.calls() if Path(call[0]).name == 'sudo']
    assert any(Path(call[0]).name == 'apt-get' and '--simulate' in call for call in fixture.calls())


def test_setup_plan_pins_exact_development_and_existing_runtime_packages(fixture):
    module = fixture.resolver()
    plan = module.plan_setup(fixture.root)
    assert f'wine64-tools:amd64={fixture.version}' in plan['packages']
    assert f'libwine-dev:amd64={fixture.version}' in plan['packages']
    assert f'wine64:amd64={fixture.version}' in plan['packages']
    assert f'libwine:amd64={fixture.version}' in plan['packages']
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('sudo', 'wine64')]


# Official primary-archive metadata observed during the fix diagnosis; offline
# fixtures deliberately do not consult the runner's packages or the network.
UBUNTU_WINE_CATALOGS = {
    'ubuntu-22.04': ('jammy', '6.0.3~repack-1'),
    'ubuntu-24.04': ('noble', '9.0~repack-4build3'),
}


def use_ubuntu_wine_catalog(fixture, host):
    archive, version = UBUNTU_WINE_CATALOGS[host]
    for package in fixture.packages.values():
        package.update(installed=version, version=version, source_version=version)
        package['origins'][0]['archive'] = archive
    fixture.save()
    return version


@pytest.mark.parametrize('workflow', ['windows.yml', 'build.yml'])
def test_workflow_cross_build_hosts_have_matched_official_wine9_setup(fixture, workflow):
    import yaml
    job = yaml.safe_load((ROOT / '.github/workflows' / workflow).read_text())['jobs']['build-windows']
    version = use_ubuntu_wine_catalog(fixture, job['runs-on'])
    plan = fixture.resolver().plan_setup(fixture.root)
    runtime = {'wine:all', 'wine64:amd64', 'libwine:amd64'}
    assert plan['protected'] == dict.fromkeys(runtime, version)
    for name in runtime | {'wine64-tools:amd64', 'libwine-dev:amd64'}:
        selector = name.removesuffix(':all')
        assert f'{selector}={version}' in plan['packages']
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('sudo', 'wine64', 'wine-stable')]
    assert any(Path(call[0]).name == 'apt-get' and '--simulate' in call for call in fixture.calls())


@pytest.mark.parametrize('selected', [True, False])
def test_jammy_catalog_cannot_provision_supported_wine9(fixture, monkeypatch, selected):
    use_ubuntu_wine_catalog(fixture, 'ubuntu-22.04')
    module = fixture.resolver()
    if not selected:
        for package in fixture.packages.values():
            package['installed'] = None
        fixture.save()
        monkeypatch.delenv('WINE_CMD')
        which = module.shutil.which
        monkeypatch.setattr(module.shutil, 'which', lambda name: None if name in ('wine', 'wine64') else which(name))
    with pytest.raises(module.ToolchainError, match='Wine9'):
        module.plan_setup(fixture.root)
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('sudo', 'wine64', 'wine-stable', 'apt-get')]


def test_setup_refuses_unavailable_exact_dev_package_even_with_newer_candidate(fixture):
    module = fixture.resolver()
    fixture.packages['wine64-tools:amd64']['version'] = '10.0'
    fixture.packages['wine64-tools:amd64']['source_version'] = '10.0'
    fixture.save()
    with pytest.raises(ValueError, match='matching|exact'):
        module.plan_setup(fixture.root)


@pytest.mark.parametrize('damage', ['host', 'mingw', 'architecture'])
def test_resolution_refuses_unsupported_build_architecture_or_target(fixture, damage):
    module = fixture.resolver()
    if damage == 'architecture':
        fixture.packages['wine64:amd64']['architecture'] = 'i386'
        fixture.save()
    else:
        name = 'g++' if damage == 'host' else 'x86_64-w64-mingw32-gcc-posix'
        fixture.executable(name, "print('aarch64-linux-gnu' if '-dumpmachine' in sys.argv else '13.2.0')")
    with pytest.raises(ValueError, match='architecture|target'):
        module.resolve_toolchain(fixture.root)


def test_setup_success_uses_pinned_fixed_transactions_without_running_wine(fixture):
    result = subprocess.run([str(ROOT / 'scripts/setup-windows-build-host.sh')], env=fixture.env,
                            text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    installs = [call for call in fixture.calls() if Path(call[0]).name == 'sudo' and 'install' in call]
    assert len(installs) == 2
    for call in installs:
        assert '--no-remove' in call
        assert all(f'{name}:amd64={fixture.version}' in call for name in ('wine64', 'libwine', 'wine64-tools', 'libwine-dev'))
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable')]


def test_preflight_summarizes_large_header_inventory_without_response_growth(fixture, monkeypatch):
    parent = Path(fixture.files['libwine-dev:amd64'][0]).parent
    for index in range(1000):
        path = parent / f'fixture-{index}.h'
        path.write_text('/* host fixture */\n')
        fixture.files['libwine-dev:amd64'].append(str(path))
    fixture.save()
    result = fixture.preflight(monkeypatch)
    assert result['status'] == 'pass'
    assert len(json.dumps(result).encode()) <= 48 * 1024
    summary = result['evidence']['publication_toolchain']['headers']
    assert summary['file_count'] == 1003 and len(summary['inventory_sha256']) == 64
    assert 'files' not in summary


@pytest.mark.parametrize('damage', ['origin', 'source', 'missing-version'])
def test_setup_host_returns_human_decision_for_unapproved_or_unavailable_packages(fixture, monkeypatch, damage):
    import opencode_windows_ci_repro as wrapper
    if damage == 'origin':
        fixture.packages['wine64:amd64']['origins'][0]['origin'] = 'WineHQ'
    elif damage == 'source':
        fixture.packages['wine64:amd64']['source'] = 'wine-stable'
    else:
        fixture.packages['libwine-dev:amd64']['version'] = None
    fixture.save()
    monkeypatch.setattr(wrapper, 'ensure_space_repo', lambda root: fixture.root)
    monkeypatch.setattr(wrapper, '_is_ubuntu_host', lambda: True)
    result = wrapper.setup_host(fixture.root)
    assert result['status'] == 'human_decision_required'
    assert result['evidence']['code'] == 'wine_publication_setup_refused'
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('sudo', 'wine64')]


def test_installed_selected_source_version_must_match_archive_metadata(fixture, monkeypatch):
    module = fixture.resolver()
    catalog = module._catalog(fixture.root)
    catalog['wine64:amd64']['versions'][0]['source_version'] = '9.1'
    monkeypatch.setattr(module, '_catalog', lambda repo: catalog)
    with pytest.raises(ValueError, match='matching'):
        module.resolve_toolchain(fixture.root)


@pytest.mark.parametrize('name', ['wine32:i386', 'publication-helper:i386'])
@pytest.mark.parametrize('damage', ['origin', 'source-version', 'source-family'])
def test_setup_refuses_new_unapproved_wine_dependency_before_sudo(fixture, monkeypatch, name, damage):
    import opencode_windows_ci_repro as wrapper
    package = dict(fixture.packages['libwine:amd64'], installed=None, architecture='i386')
    package['origins'] = [dict(package['origins'][0])]
    if damage == 'origin':
        package['origins'][0]['origin'] = 'WineHQ'
    elif damage == 'source-version':
        package['source_version'] = '9.1'
    else:
        package['source'] = 'wine-stable'
    fixture.packages[name] = package
    fixture.save()
    monkeypatch.setenv('FIXTURE_TRANSACTION', f'Inst {name} ({fixture.version} fixture [i386])')
    monkeypatch.setattr(wrapper, 'ensure_space_repo', lambda root: fixture.root)
    monkeypatch.setattr(wrapper, '_is_ubuntu_host', lambda: True)
    result = wrapper.setup_host(fixture.root)
    assert result['status'] == 'human_decision_required'
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('sudo', 'wine64', 'wine-stable')]


@pytest.mark.parametrize('name', ['wine32:i386', 'publication-helper:i386'])
def test_setup_pins_new_matching_ubuntu_wine_dependency_and_resimulates(fixture, monkeypatch, name):
    module = fixture.resolver()
    fixture.packages[name] = dict(fixture.packages['libwine:amd64'], installed=None, architecture='i386')
    fixture.save()
    monkeypatch.setenv('FIXTURE_TRANSACTION', f'Inst {name} ({fixture.version} fixture [i386])')
    plan = module.plan_setup(fixture.root)
    pin = f'{name}={fixture.version}'
    assert pin in plan['packages']
    simulations = [call for call in fixture.calls() if Path(call[0]).name == 'apt-get']
    assert len(simulations) == 2 and pin in simulations[-1]


@pytest.mark.parametrize('source', [None, 'gcc-13'])
def test_simulated_unknown_package_requires_source_metadata_not_name_guess(fixture, monkeypatch, source):
    module = fixture.resolver()
    if source is not None:
        fixture.packages['ordinary-helper:amd64'] = dict(fixture.packages['libwine:amd64'], installed=None, source=source)
        fixture.save()
    monkeypatch.setenv('FIXTURE_TRANSACTION', f'Inst ordinary-helper:amd64 ({fixture.version} fixture [amd64])')
    if source is None:
        with pytest.raises(ValueError, match='metadata|classif'):
            module.plan_setup(fixture.root)
    else:
        assert module.plan_setup(fixture.root)['packages']


@pytest.mark.parametrize('pinned', [False, True])
@pytest.mark.parametrize('route', ['explicit', 'alternative'])
def test_regular_arch_all_wine_stable_launcher_matches_native_implementation(fixture, monkeypatch, pinned, route):
    module = fixture.resolver()
    launcher = fixture.bin / 'wine-stable'
    launcher.unlink()
    launcher.write_text('#!/bin/sh\nexit 97 # inert regular distro launcher; never execute\n')
    launcher.chmod(0o755)
    selected_logical = launcher
    if route == 'alternative':
        selected_logical = fixture.bin / 'wine'
        selected_logical.symlink_to(launcher)
        monkeypatch.delenv('WINE_CMD')
        which = module.shutil.which
        monkeypatch.setattr(module.shutil, 'which', lambda name: None if name == 'wine64' else which(name))
    runtime = dict(executable=str(launcher), version='wine-9.0 (fixture)',
                   sha256=hashlib.sha256(launcher.read_bytes()).hexdigest()) if pinned else None
    identity = module.resolve_toolchain(fixture.root, runtime)
    selected = identity['installation']
    assert selected['file']['executable'] == str(launcher)
    assert selected['logical'] == str(selected_logical)
    assert selected['package']['name'] == 'wine:all'
    assert selected['implementation']['file']['executable'] == str(fixture.lib / 'wine64')
    assert selected['implementation']['package']['name'] == 'wine64:amd64'
    module.verify_toolchain(identity)
    monkeypatch.setenv('FIXTURE_TRANSACTION', f'Inst wine [{fixture.version}] ({fixture.version} Ubuntu:24.04/noble [all])')
    assert module.plan_setup(fixture.root)['packages']
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable')]


@pytest.fixture
def regular_launcher_inventory(fixture):
    launcher = fixture.bin / 'wine-stable'
    launcher.unlink()
    launcher.write_text('#!/bin/sh\nexit 97 # regular fixture launcher; never execute\n')
    launcher.chmod(0o755)
    return fixture


@pytest.fixture
def noble_native_inventory(regular_launcher_inventory):
    fixture = regular_launcher_inventory
    share = fixture.bin.parent / 'share'
    bug, doc = share / 'bug/wine64', share / 'doc/wine64'
    bug.mkdir(parents=True)
    doc.mkdir(parents=True)
    metadata = share / 'lintian/overrides/wine64'
    metadata.parent.mkdir(parents=True)
    metadata.write_text('# regular lintian package metadata, not a native loader\n')
    fixture.files['wine64:amd64'] = [str(fixture.lib / 'wine64'), str(bug), str(doc), str(metadata)]
    fixture.save()
    return fixture


@pytest.fixture
def noble_tool_roles(noble_native_inventory):
    fixture = noble_native_inventory
    fixture.executable('wine-stable', "raise AssertionError('Wine must never run')")
    for name in ('winegcc', 'winebuild'):
        (fixture.bin / (name + '-stable')).unlink()
        fixture.executable(name + '-stable',
                           f"assert pathlib.Path(sys.argv[0]).name == {name + '-stable'!r}\n"
                           f"print('fixture {name} stable C-role')")
        fixture.executable(name,
                           f"assert pathlib.Path(sys.argv[0]).name == {name!r}\n"
                           f"print('fixture {name} backend C-role')", fixture.lib)
    alternatives = fixture.bin.parent / 'alternatives'
    alternatives.mkdir()
    for name in ('wine', 'winegcc', 'winebuild'):
        stable = fixture.bin / ('wine-stable' if name == 'wine' else name + '-stable')
        (alternatives / name).symlink_to(stable)
        (fixture.bin / name).symlink_to(alternatives / name)
    # Generic master/slave alternatives are not package payload paths. The
    # package owns the regular stable wrappers and distinct native backends.
    fixture.save()
    return fixture


@pytest.mark.parametrize('route', ['stable', 'generic', 'generic-wrong-slave', 'unstable-name',
                                  'custom-directory', 'native', 'native-alias'])
def test_canonical_wine_tools_select_correct_packaged_c_roles(noble_tool_roles, monkeypatch, route):
    fixture = noble_tool_roles
    canonical = fixture.bin / 'wine-stable'
    selected = canonical
    if route in ('generic', 'generic-wrong-slave'):
        selected = fixture.bin / 'wine'
        if route == 'generic-wrong-slave':
            foreign = fixture.root / 'foreign'
            foreign.mkdir()
            fixture.executable('winegcc', "raise AssertionError('unrelated alternatives provider must not run')", foreign)
            slave = fixture.bin.parent / 'alternatives/winegcc'
            slave.unlink()
            slave.symlink_to(foreign / 'winegcc')
    elif route == 'unstable-name':
        selected = fixture.bin / 'wine-unstable'
        selected.symlink_to(canonical)
        for name in ('winegcc', 'winebuild'):
            fixture.executable(name + '-unstable', "raise AssertionError('unrelated sibling must not run')")
    elif route in ('custom-directory', 'native-alias'):
        directory = fixture.root / 'user-aliases'
        directory.mkdir()
        selected = directory / 'wine-stable'
        if route == 'native-alias':
            canonical = fixture.lib / 'wine64'
        selected.symlink_to(canonical)
        for name in ('winegcc', 'winebuild'):
            for suffix in ('', '-stable'):
                fixture.executable(name + suffix, "raise AssertionError('unrelated sibling must not run')", directory)
    elif route == 'native':
        selected = canonical = fixture.lib / 'wine64'
    monkeypatch.setenv('WINE_CMD', str(selected))
    runtime = dict(executable=str(canonical), version='wine-9.0 (fixture)',
                   sha256=hashlib.sha256(canonical.read_bytes()).hexdigest())
    module = fixture.resolver()
    identity = module.resolve_toolchain(fixture.root, runtime)
    backend = canonical == fixture.lib / 'wine64'
    for name in ('winegcc', 'winebuild'):
        expected = fixture.lib / name if backend else fixture.bin / (name + '-stable')
        assert identity['tools'][name] == {
            'executable': str(expected), 'sha256': hashlib.sha256(expected.read_bytes()).hexdigest(),
            'version': f"fixture {name} {'backend' if backend else 'stable'} C-role"}
    module.verify_toolchain(identity)
    called = [Path(call[0]) for call in fixture.calls() if Path(call[0]).name.startswith(('winegcc', 'winebuild'))]
    assert called and set(called) == {
        fixture.lib / name if backend else fixture.bin / (name + '-stable') for name in ('winegcc', 'winebuild')}
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable', 'wine')]


def test_canonical_wine_tools_refuse_cpp_alias_even_with_shared_canonical_file(noble_tool_roles):
    fixture = noble_tool_roles
    cpp = fixture.bin / 'wineg++-stable'
    cpp.symlink_to(fixture.bin / 'winegcc-stable')
    fixture.files['wine64-tools:amd64'].append(str(cpp))
    fixture.save()
    module = fixture.resolver()
    catalog = module._catalog(fixture.root)
    selection = module._selection(fixture.root, catalog)
    package = module._matched_package(fixture.root, catalog, 'wine64-tools:amd64', fixture.version)
    before = len(fixture.calls())
    with pytest.raises(module.ToolchainError):
        module._wine_tool(fixture.root, 'wineg++', selection, package)
    assert not [call for call in fixture.calls()[before:] if Path(call[0]).name.startswith('wineg')]


@pytest.mark.parametrize('damage', [
    'unlisted-role', 'unlisted-canonical', 'missing-wrapper', 'non-executable',
    'wrong-provider', 'cpp-provider', 'wrong-tool', 'runtime-provider', 'wrong-owner',
    'wrong-source', 'wrong-source-version', 'wrong-origin', 'wrong-architecture'])
def test_canonical_wine_tools_refuse_invalid_provider_or_provenance(noble_tool_roles, monkeypatch, damage):
    fixture = noble_tool_roles
    role = fixture.bin / 'winegcc-stable'
    denied = set()
    if damage == 'unlisted-role':
        fixture.files['wine64-tools:amd64'].remove(str(role))
        denied.add(role)
    elif damage == 'unlisted-canonical':
        role.unlink()
        role.symlink_to(fixture.lib / 'winegcc')
        fixture.files['wine64-tools:amd64'].remove(str(fixture.lib / 'winegcc'))
        denied.add(fixture.lib / 'winegcc')
    elif damage == 'missing-wrapper':
        role.unlink()
        denied.add(fixture.lib / 'winegcc')  # No unique-backend fallback for a missing frontend role.
    elif damage == 'non-executable':
        role.chmod(0o644)
        denied.add(role)
    elif damage in ('wrong-provider', 'cpp-provider'):
        directory = fixture.root / ('x' * 100 + '\t\x1b\u202e') if damage == 'wrong-provider' else fixture.bin
        directory.mkdir(exist_ok=True)
        name = 'winegcc' if damage == 'wrong-provider' else 'wineg++-stable'
        fixture.executable(name, "print('wrong provider 9.0')", directory)
        target = directory / name
        fixture.files['wine64-tools:amd64'].append(str(target))
        role.unlink()
        role.symlink_to(target)
        denied.add(target)
    elif damage == 'wrong-tool':
        role = fixture.bin / 'winebuild-stable'
        role.unlink()
        role.symlink_to(fixture.bin / 'winegcc-stable')
    elif damage == 'runtime-provider':
        role.unlink()
        role.symlink_to(fixture.bin / 'wine-stable')
        denied.add(fixture.bin / 'wine-stable')
    elif damage == 'wrong-owner':
        query = fixture.bin / 'dpkg-query'
        query.write_text(query.read_text().replace("if args[0] == '-S':",
                         f"if args[0] == '-S' and args[1] == {str(role)!r}:\n print('libwine:amd64: ' + args[1]); sys.exit(0)\nif args[0] == '-S':"))
        denied.add(role)
    elif damage == 'wrong-source':
        fixture.packages['wine64-tools:amd64']['source'] = 'wine-staging'
    elif damage == 'wrong-source-version':
        fixture.packages['wine64-tools:amd64']['source_version'] = '8.0'
    elif damage == 'wrong-origin':
        fixture.packages['wine64-tools:amd64']['origins'][0]['origin'] = 'WineHQ'
    elif damage == 'wrong-architecture':
        fixture.packages['wine64-tools:amd64']['architecture'] = 'i386'
    fixture.save()
    module = fixture.resolver()
    queries = []
    run = module._run
    def observe(repo, args):
        queries.append(list(args))
        return run(repo, args)
    monkeypatch.setattr(module, '_run', observe)
    with pytest.raises(module.ToolchainError) as error:
        module.resolve_toolchain(fixture.root)
    assert not [args for args in queries if Path(args[0]) in denied and args[1:] == ['--version']]
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable', 'wine')]
    if damage in ('unlisted-role', 'unlisted-canonical', 'wrong-provider', 'cpp-provider', 'wrong-tool', 'runtime-provider'):
        message = str(error.value)
        assert all(field in message for field in ('wine-logical=', 'wine-canonical=', 'tool-role=',
                                                  'tool-canonical=', 'candidates=', 'context-truncated='))
        assert len(message.encode('ascii')) <= 480 and all(' ' <= char < '\x7f' for char in message)


@pytest.mark.parametrize('route', ['stable', 'generic', 'native', 'native-alias', 'role-alias'])
def test_native_loader_role_accepts_real_noble_inventory(noble_native_inventory, monkeypatch, route):
    fixture = noble_native_inventory
    role = fixture.lib / 'wine64'
    selected = fixture.bin / 'wine-stable'
    canonical = selected
    if route == 'generic':
        selected = fixture.bin / 'wine'
        selected.symlink_to(canonical)
    elif route == 'native':
        selected = canonical = role
    elif route == 'native-alias':
        selected = fixture.bin / 'wine64'
        selected.symlink_to(role)
        canonical = role
        fixture.files['wine64:amd64'] += [str(selected), str(role)]
    elif route == 'role-alias':
        merged = fixture.bin.parent / 'merged'
        merged.mkdir()
        (merged / 'lib').symlink_to(fixture.lib.parent, target_is_directory=True)
        selected = merged / 'lib/wine/wine64'
        canonical = role
        fixture.files['wine64:amd64'] += [str(selected), str(role)]
    monkeypatch.setenv('WINE_CMD', str(selected))
    fixture.save()
    runtime = dict(executable=str(canonical), version='wine-9.0 (fixture)',
                   sha256=hashlib.sha256(canonical.read_bytes()).hexdigest())
    module = fixture.resolver()
    identity = module.resolve_toolchain(fixture.root, runtime)
    assert identity['installation']['file']['executable'] == str(canonical)
    assert identity['installation']['implementation']['file'] == {
        'executable': str(role), 'sha256': hashlib.sha256(role.read_bytes()).hexdigest()}
    assert identity['installation']['implementation']['package']['name'] == 'wine64:amd64'
    module.verify_toolchain(identity)
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable', 'wine')]


@pytest.mark.parametrize('damage', [
    'direct-metadata', 'unsupported-native-layout', 'unsupported-launcher-layout',
    'missing-role-inventory', 'missing-role-file', 'directory-role', 'non-executable-role', 'non-executable-wrapper',
    'role-symlink-metadata', 'wrapper-symlink-metadata', 'native-alias-metadata',
    'wrong-owner', 'wrong-source', 'wrong-origin', 'wrong-architecture', 'conflicting-role'])
def test_native_loader_role_refuses_invalid_provenance(noble_native_inventory, monkeypatch, damage):
    fixture = noble_native_inventory
    role = fixture.lib / 'wine64'
    launcher = fixture.bin / 'wine-stable'
    metadata = fixture.bin.parent / 'share/lintian/overrides/wine64'
    metadata.chmod(0o755)  # Executability alone must never confer the loader role.
    if damage == 'direct-metadata':
        monkeypatch.setenv('WINE_CMD', str(metadata))
    elif damage == 'unsupported-native-layout':
        other = fixture.lib / 'other/wine64'
        other.parent.mkdir()
        shutil.copy2(role, other)
        fixture.files['wine64:amd64'].append(str(other))
        monkeypatch.setenv('WINE_CMD', str(other))
    elif damage == 'unsupported-launcher-layout':
        other = fixture.bin.parent / 'unsupported/wine-stable'
        other.parent.mkdir()
        launcher.rename(other)
        fixture.files['wine:all'] = [str(other)]
        monkeypatch.setenv('WINE_CMD', str(other))
    elif damage == 'missing-role-inventory':
        fixture.files['wine64:amd64'].remove(str(role))
    elif damage == 'missing-role-file':
        role.unlink()
    elif damage == 'directory-role':
        role.unlink()
        role.mkdir()
    elif damage == 'non-executable-role':
        role.chmod(0o644)
        fixture.files['wine64:amd64'].remove(str(metadata))
    elif damage == 'non-executable-wrapper':
        launcher.chmod(0o644)
    elif damage == 'role-symlink-metadata':
        role.unlink()
        role.symlink_to(metadata)
    elif damage == 'wrapper-symlink-metadata':
        launcher.unlink()
        launcher.symlink_to(metadata)
    elif damage == 'native-alias-metadata':
        alias = fixture.bin / 'wine64'
        alias.symlink_to(metadata)
        fixture.files['wine64:amd64'].append(str(alias))
        monkeypatch.setenv('WINE_CMD', str(alias))
    elif damage == 'wrong-owner':
        query = fixture.bin / 'dpkg-query'
        query.write_text(query.read_text().replace("if args[0] == '-S':",
                         f"if args[0] == '-S' and args[1] == {str(role)!r}:\n print('libwine:amd64: ' + args[1]); sys.exit(0)\nif args[0] == '-S':"))
    elif damage == 'wrong-source':
        fixture.packages['wine64:amd64']['source'] = 'wine-stable'
    elif damage == 'wrong-origin':
        fixture.packages['wine64:amd64']['origins'][0]['origin'] = 'WineHQ'
    elif damage == 'wrong-architecture':
        fixture.packages['wine64:amd64']['architecture'] = 'i386'
    elif damage == 'conflicting-role':
        other = fixture.bin.parent / 'unsupported/lib/wine/wine64'
        other.parent.mkdir(parents=True)
        shutil.copy2(role, other)
        fixture.files['wine64:amd64'].append(str(other))
    fixture.save()
    module = fixture.resolver()
    with pytest.raises(module.ToolchainError):
        module._selection(fixture.root, module._catalog(fixture.root))
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable', 'wine')]


@pytest.mark.parametrize('case,listed,regular,unique', [
    ('unlisted-role', 0, 0, 0), ('nonregular-role', 1, 0, 0), ('conflicting-role', 2, 2, 2)])
def test_native_loader_role_refusal_diagnostics(noble_native_inventory, monkeypatch, case, listed, regular, unique):
    fixture = noble_native_inventory
    role = fixture.lib / 'wine64'
    if case == 'unlisted-role':
        fixture.files['wine64:amd64'].remove(str(role))
    elif case == 'nonregular-role':
        role.unlink()
        role.mkdir()
    else:
        # An unsupported second-prefix claim is refused, not tolerated as a
        # hypothetical second legitimate loader or selected by inventory order.
        foreign = fixture.bin.parent / 'unsupported/lib/wine/wine64'
        foreign.parent.mkdir(parents=True)
        shutil.copy2(role, foreign)
        fixture.files['wine64:amd64'].append(str(foreign))
    fixture.save()
    inspected = []
    original = Path.is_file
    def observe(path):
        if path.name == 'wine64':
            inspected.append(path)
        return original(path)
    monkeypatch.setattr(Path, 'is_file', observe)
    module = fixture.resolver()
    with pytest.raises(module.ToolchainError) as error:
        module._selection(fixture.root, module._catalog(fixture.root))
    message = str(error.value)
    assert message.startswith(f'Missing or conflicting native Wine64 role: package=wine64:amd64 '
                              f'listed={listed} regular={regular} unique-resolved={unique} ')
    assert all(path.parts[-3:] == ('lib', 'wine', 'wine64') for path in inspected)
    assert 'observations-truncated=false' in message and 'message-truncated=' in message
    assert message.count('is-file=true') == regular and message.count('is-file=false') == listed - regular
    assert len(message.encode('ascii')) <= 480
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable', 'wine')]


def test_native_inventory_diagnostic_escapes_caps_and_flags_observations(monkeypatch):
    # Formatting remains string-only; synthetic observations exercise encoding,
    # not an obsolete rule that every regular basename is a candidate loader.
    module = importlib.import_module('wine.publication_toolchain')
    def unexpected_probe(*args, **kwargs):
        pytest.fail('diagnostic formatting must not probe paths or packages')
    for name in ('is_file', 'resolve'):
        original = getattr(Path, name)
        def observe(path, *args, _original=original, **kwargs):
            if path.name == 'wine64':
                unexpected_probe()
            return _original(path, *args, **kwargs)
        monkeypatch.setattr(Path, name, observe)
    monkeypatch.setattr(module, '_run', unexpected_probe)
    paths = ['/' + 'x' * 140 + f'{index}\t\x1b\x7f\u202e/wine64' for index in range(6)]
    message = module._native_inventory_diagnostic('wine64:amd64', 6, 6, 6, [(path, True) for path in paths[:4]])
    assert 'package=wine64:amd64 listed=6 regular=6 unique-resolved=6 ' in message
    assert 'observations-truncated=true' in message and 'message-truncated=true' in message
    assert message.count('is-file=true') == 4 and 'is-file=false' not in message
    assert all(escape in message for escape in ('\\t', '\\u001b', '\\u007f', '\\u202e'))
    assert all(' ' <= char < '\x7f' for char in message) and len(message.encode('ascii')) <= 480
    assert all(path not in message for path in paths), 'do not dump complete long candidate paths'


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('foreign_installed', [False, True])
def test_multiarch_catalog_preserves_native_resolution_and_every_runtime_pin(fixture, reverse, foreign_installed):
    module = fixture.resolver()
    for name in ('libwine', 'libwine-dev'):
        fixture.packages[name + ':i386'] = dict(fixture.packages[name + ':amd64'], architecture='i386',
                                               installed=fixture.version if foreign_installed else None)
        if not foreign_installed:
            fixture.packages[name + ':i386'].update(version='8.0', source_version='8.0')
    if reverse:
        fixture.packages = dict(reversed(list(fixture.packages.items())))
    fixture.save()
    catalog = module._catalog(fixture.root)
    assert {'libwine-dev:amd64', 'libwine-dev:i386', 'libwine:amd64', 'libwine:i386'} <= catalog.keys()
    identity = module.resolve_toolchain(fixture.root)
    assert identity['headers']['package']['name'] == 'libwine-dev:amd64'
    plan = module.plan_setup(fixture.root)
    assert f'libwine:amd64={fixture.version}' in plan['packages']
    assert (f'libwine:i386={fixture.version}' in plan['packages']) is foreign_installed
    if foreign_installed:
        assert f'libwine-dev:i386={fixture.version}' in plan['packages']


@pytest.mark.parametrize('architecture', ['amd64', 'i386'])
def test_multiarch_simulation_cannot_change_either_installed_runtime(fixture, monkeypatch, architecture):
    module = fixture.resolver()
    fixture.packages['libwine:i386'] = dict(fixture.packages['libwine:amd64'], architecture='i386')
    fixture.save()
    monkeypatch.setenv('FIXTURE_TRANSACTION', f'Inst libwine:{architecture} [{fixture.version}] (9.1 fixture [{architecture}])')
    with pytest.raises(ValueError, match='changes selected Wine runtime'):
        module.plan_setup(fixture.root)


def test_setup_rechecks_new_wine_dependency_in_pinned_second_simulation(fixture, monkeypatch):
    import opencode_windows_ci_repro as wrapper
    fixture.packages['wine32:i386'] = dict(fixture.packages['libwine:amd64'], installed=None, architecture='i386')
    bad = dict(fixture.packages['wine32:i386'])
    bad['origins'] = [dict(bad['origins'][0], origin='WineHQ')]
    fixture.packages['new-dependency:i386'] = bad
    fixture.save()
    fixture.executable('apt-get', f'''
print('Inst wine32:i386 ({fixture.version} fixture [i386])')
if any(arg.startswith('wine32:i386=') for arg in sys.argv):
 print('Inst new-dependency:i386 ({fixture.version} fixture [i386])')
''')
    monkeypatch.setattr(wrapper, 'ensure_space_repo', lambda root: fixture.root)
    monkeypatch.setattr(wrapper, '_is_ubuntu_host', lambda: True)
    assert wrapper.setup_host(fixture.root)['status'] == 'human_decision_required'
    assert len([call for call in fixture.calls() if Path(call[0]).name == 'apt-get']) == 2
    assert not [call for call in fixture.calls() if Path(call[0]).name == 'sudo']


PAIR = ('modules/x86_64-windows/space_record_publication.dll',
        'modules/x86_64-unix/space_record_publication.so')
ABI_HEADER = 'src/record_publication_wine_abi.h'
PE_SOURCE = 'scripts/wine/record_publication_bridge.c'
UNIX_SOURCE = 'scripts/wine/record_publication_unix_entry.cpp'
BUILDER_SOURCE = 'scripts/wine/build_publication.py'
AUTHORITY_HEADER = 'src/record_publication_wine_authority.h'
ADAPTER_SOURCE = 'src/record_publication_unix.cpp'
PUBLICATION_SOURCE = 'src/record_publication.cpp'
BUILD_INPUTS = (ABI_HEADER, AUTHORITY_HEADER, 'src/record_publication_unix.h', ADAPTER_SOURCE,
                'src/record_publication_operation.h', 'src/record_publication.h', PUBLICATION_SOURCE,
                PE_SOURCE, UNIX_SOURCE, BUILDER_SOURCE)


def builder_module():
    assert (ROOT / BUILDER_SOURCE).is_file(), 'fixed publication builder is missing'
    return importlib.import_module('wine.build_publication')


@pytest.mark.parametrize('compiler,standard', [('cc', 'c11'), ('c++', 'c++17')])
def test_publication_identity_layout_compiles_in_c_and_cpp(tmp_path, compiler, standard):
    header = ROOT / ABI_HEADER
    assert header.is_file(), 'shared publication ABI header is missing'
    source = '''#include "record_publication_wine_abi.h"
#ifdef __cplusplus
#define ASSERT static_assert
#else
#define ASSERT _Static_assert
#endif
ASSERT(sizeof(SrpIdentity) == 112, "size");
ASSERT(offsetof(SrpIdentity, challenge) == 8, "challenge");
ASSERT(offsetof(SrpIdentity, echo) == 16, "echo");
ASSERT(offsetof(SrpIdentity, pe_build_id) == 24, "PE ID");
ASSERT(offsetof(SrpIdentity, unix_build_id) == 56, "Unix ID");
ASSERT(offsetof(SrpIdentity, module_device) == 88, "device");
ASSERT(offsetof(SrpIdentity, module_inode) == 96, "inode");
ASSERT(offsetof(SrpIdentity, architecture) == 104, "architecture");
ASSERT(offsetof(SrpIdentity, features) == 108, "features");
ASSERT(SRP_ABI == 1 && SRP_FEATURE_IDENTITY == 1 && SRP_FEATURE_OPERATION == 2, "ABI/features");
ASSERT(SRP_REQUIRED_FEATURES == (SRP_FEATURE_IDENTITY | SRP_FEATURE_OPERATION), "complete pair");
int main(void) { return 0; }
'''
    result = subprocess.run([compiler, '-x', 'c++' if compiler == 'c++' else 'c', f'-std={standard}',
                             '-Wall', '-Werror', '-I', str(header.parent), '-o', str(tmp_path / 'layout'), '-'],
                            input=source, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('compiler,standard', [('cc', 'c11'), ('c++', 'c++17')])
def test_publication_operation_layout_compiles_in_c_and_cpp(tmp_path, compiler, standard):
    source = '''#include "record_publication_wine_abi.h"
#ifdef __cplusplus
#define ASSERT static_assert
#else
#define ASSERT _Static_assert
#endif
ASSERT(sizeof(SrpIdentity) == 112 && SRP_REQUIRED_FEATURES == 3, "identity layout, complete features");
ASSERT(sizeof(SrpSlice) == 16 && sizeof(SrpBuffer) == 24, "spans");
ASSERT(sizeof(SrpCall) == 168, "first operation frame, no 144 alias");
ASSERT(offsetof(SrpCall, context) == 16, "context");
ASSERT(offsetof(SrpCall, sequence) == 24, "sequence");
ASSERT(offsetof(SrpCall, path) == 32, "path");
ASSERT(offsetof(SrpCall, payload) == 48, "payload");
ASSERT(offsetof(SrpCall, hook_error) == 64, "hook");
ASSERT(offsetof(SrpCall, primary_error) == 80, "primary");
ASSERT(offsetof(SrpCall, cleanup_error) == 104, "cleanup");
ASSERT(offsetof(SrpCall, transport_error) == 128, "transport");
ASSERT(offsetof(SrpCall, reply) == 152, "reply");
ASSERT(offsetof(SrpCall, flags) == 156, "flags");
ASSERT(offsetof(SrpCall, primary_state) == 160, "primary presence");
ASSERT(offsetof(SrpCall, reserved) == 164, "reserved");
ASSERT(SRP_BEGIN == 1 && SRP_ADVANCE == 2 && SRP_SNAPSHOT == 3 && SRP_CANCEL == 4 && SRP_RELEASE == 5, "opcodes");
ASSERT(SRP_CONTINUE == 0 && SRP_FAILED == 1, "replies");
ASSERT(SRP_START == 0 && SRP_BEFORE_WRITE == 1 && SRP_BEFORE_SECURITY == 2 && SRP_BEFORE_COMMIT == 3
       && SRP_BEFORE_CLEANUP == 4 && SRP_DONE == 5, "events");
ASSERT(SRP_VALID == 1 && SRP_COMMITTED == 2 && SRP_DONE_FLAG == 4 && SRP_PRIMARY_TRUNCATED == 8
       && SRP_CLEANUP_TRUNCATED == 16 && SRP_CLEANUP_PRESENT == 32 && SRP_POISONED == 64
       && SRP_TRANSPORT_TRUNCATED == 128, "flags");
ASSERT(SRP_PRIMARY_ABSENT == 0 && SRP_PRIMARY_PRESENT == 1, "presence not status");
int main(void) { return 0; }
'''
    result = subprocess.run([compiler, '-x', 'c++' if compiler == 'c++' else 'c', f'-std={standard}',
                             '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'src'),
                             '-o', str(tmp_path / 'operation-layout'), '-'],
                            input=source, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_publication_operation_layout_native_header_refuses_pe_use(tmp_path):
    result = subprocess.run(['c++', '-std=c++17', '-D_WIN32', '-I', str(ROOT / 'src'),
                             '-x', 'c++', '-c', '-o', str(tmp_path / 'not-pe.o'), '-'],
                            input='#include "record_publication_unix.h"\n',
                            text=True, capture_output=True, timeout=30)
    assert result.returncode != 0
    assert 'requires native Linux x86_64' in result.stderr


class Identity(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('abi', ctypes.c_uint32),
                ('challenge', ctypes.c_uint64), ('echo', ctypes.c_uint64),
                ('pe_build_id', ctypes.c_uint8 * 32), ('unix_build_id', ctypes.c_uint8 * 32),
                ('module_device', ctypes.c_uint64), ('module_inode', ctypes.c_uint64),
                ('architecture', ctypes.c_uint32), ('features', ctypes.c_uint32)]


class Slice(ctypes.Structure):
    _fields_ = [('address', ctypes.c_uint64), ('size', ctypes.c_uint64)]


class Buffer(ctypes.Structure):
    _fields_ = [('address', ctypes.c_uint64), ('capacity', ctypes.c_uint64), ('required', ctypes.c_uint64)]


class OperationCall(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('abi', ctypes.c_uint32),
                ('opcode', ctypes.c_uint32), ('event', ctypes.c_uint32),
                ('context', ctypes.c_uint64), ('sequence', ctypes.c_uint64),
                ('path', Slice), ('payload', Slice), ('hook_error', Slice),
                ('primary_error', Buffer), ('cleanup_error', Buffer), ('transport_error', Buffer),
                ('reply', ctypes.c_uint32), ('flags', ctypes.c_uint32),
                ('primary_state', ctypes.c_uint32), ('reserved', ctypes.c_uint32)]


def test_publication_real_host_so_identity_and_operation_route(tmp_path):
    source = ROOT / UNIX_SOURCE
    assert source.is_file(), 'Unix identity entry is missing'
    expected = bytes(range(32))
    definition = '-DSRP_BUILD_ID_BYTES={' + ','.join(hex(byte) for byte in expected) + '}'
    output = tmp_path / 'identity.so'
    result = subprocess.run(['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared',
                             '-fvisibility=hidden', '-static-libgcc', '-static-libstdc++',
                             '-I', str(ROOT / 'src'), definition, str(source),
                             str(ROOT / ADAPTER_SOURCE), str(ROOT / PUBLICATION_SOURCE),
                             '-pthread', '-o', str(output), '-ldl'], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert 'libc.so.6' in builder_module()._elf_dependencies(output.read_bytes())
    library = ctypes.CDLL(str(output))  # Host ELF only; never Wine or PE.
    exported = (ctypes.c_uint8 * 32).in_dll(library, 'SpaceRecordPublicationUnixBuildId')
    assert bytes(exported) == expected
    entries = (ctypes.c_void_p * 2).in_dll(library, '__wine_unix_call_funcs')
    call = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p)
    identify, operate = (call(entry) for entry in entries)
    value = Identity(size=112, abi=1, challenge=0x1122334455667788)
    value.pe_build_id[:] = bytes([0xA5]) * 32
    assert identify(ctypes.byref(value)) == 0
    info = output.stat()
    assert value.echo == value.challenge and value.architecture == 0x8664
    assert (value.module_device, value.module_inode) == (info.st_dev, info.st_ino)
    assert bytes(value.pe_build_id) == bytes([0xA5]) * 32 and bytes(value.unix_build_id) == expected
    assert ctypes.sizeof(OperationCall) == 168
    transport = ctypes.create_string_buffer(4096)
    request = OperationCall(size=168, abi=1, opcode=1,
                            transport_error=Buffer(ctypes.addressof(transport), 4096, 0))
    before = set(tmp_path.iterdir())
    assert operate(ctypes.byref(request)) == ctypes.c_int32(0xC000000D).value
    assert (request.context, request.sequence, request.event, request.flags, request.primary_state) == (0, 0, 0, 0, 0)
    assert request.primary_error.required == request.cleanup_error.required == 0
    assert 0 < request.transport_error.required <= 4096
    assert b'nonempty absolute' in transport.raw[:request.transport_error.required]
    assert set(tmp_path.iterdir()) == before
    assert value.features == 3
    # Empty-path refusal did not register a context or touch the filesystem.
    path = ctypes.create_string_buffer(str(tmp_path / 'not-created').encode())
    begin = OperationCall(size=168, abi=1, opcode=1, path=Slice(ctypes.addressof(path), len(path.value)))
    assert operate(ctypes.byref(begin)) == 0 and begin.context == 1
    assert set(tmp_path.iterdir()) == before
    release = OperationCall(size=168, abi=1, opcode=5, context=begin.context)
    assert operate(ctypes.byref(release)) == 0
    assert set(tmp_path.iterdir()) == before
    assert identify(None) != 0
    for size, abi in [(111, 1), (113, 1), (112, 2)]:
        invalid = Identity(size=size, abi=abi)
        assert identify(ctypes.byref(invalid)) != 0
    output.unlink()
    value.echo = 0
    assert identify(ctypes.byref(value)) != 0 and value.echo == 0


@pytest.fixture
def publication_fixture(fixture):
    from wine import prefix
    # Build admission gets an existing immutable Session, without launching even
    # a fake Wine --version. Real Session ownership validation remains active.
    build = fixture.root / 'build'
    build.mkdir(mode=0o700)
    identifier = 'a' * 32
    directory = build / 'wine/sessions' / identifier
    directory.mkdir(parents=True, mode=0o700)
    for path in [build / 'wine', directory.parent, directory]:
        path.chmod(0o700)
    for name in ['prefix', 'data', 'cache', 'tmp']:
        (directory / name).mkdir(mode=0o700)
    wine = fixture.lib / 'wine64'
    runtime = dict(executable=str(wine), sha256=hashlib.sha256(wine.read_bytes()).hexdigest(), version='wine-9.0 (fixture)')
    owner = dict(version=4, id=identifier, nonce='b' * 32, repo=str(fixture.root), uid=os.geteuid(),
                 bounds=prefix.BOUNDS, tools=dict(wine=runtime, server=runtime),
                 crash_policy=[list(row) for row in prefix.CRASH_POLICY])
    session = prefix.Session(fixture.root, identifier, owner)
    owner['roots'] = {key: prefix.real_directory(path, key not in ('repo', 'build', 'wine'))
                      for key, path in session.roots().items()}
    prefix.write_control(directory / 'owner.json', owner, exclusive=True)
    session.validate()
    shutil.copy2(ROOT / 'scripts/wine/prefix.py', fixture.root / 'scripts/wine/prefix.py')
    for relative in BUILD_INPUTS:
        source = ROOT / relative
        assert source.is_file(), f'publication build input missing: {relative}'
        target = fixture.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Structurally sufficient synthetic ELF/PE files let the real fixed builder
    # check architecture/dependency inventories. They are NOT real tool outputs.
    compile_body = '''
if '-o' not in sys.argv:
 print('x86_64-w64-mingw32' if '-dumpmachine' in sys.argv and 'mingw32' in sys.argv[0] else 'x86_64-linux-gnu' if '-dumpmachine' in sys.argv else '13.2.0' if '-dumpversion' in sys.argv else 'fixture host build tool 9.0')
 sys.exit(0)
import struct
definition = next(a for a in sys.argv if a.startswith('-DSRP_BUILD_ID_BYTES='))
identity = bytes(int(v, 16) for v in definition.split('=', 1)[1].strip('{}').split(','))
if 'mingw32' in sys.argv[0]:
 data = bytearray(1024)
 data[:2] = b'MZ'; struct.pack_into('<I', data, 60, 128)
 data[128:132] = b'PE\\0\\0'; struct.pack_into('<HHIIIHH', data, 132, 0x8664, 0, 0, 0, 0, 240, 0x2022)
 struct.pack_into('<H', data, 152, 0x20b)
 data[-32:] = identity
else:
 strings = b'\\0libc.so.6\\0'
 header = struct.pack('<16sHHIQQQIHHHHHH', b'\\x7fELF\\x02\\x01\\x01' + bytes(9), 3, 62, 1, 0, 0, 64, 0, 64, 0, 0, 64, 3, 0)
 section = lambda typ, off, size, link=0, ent=0: struct.pack('<IIQQQQIIQQ', 0, typ, 0, 0, off, size, link, 0, 1, ent)
 data = header + bytes(64) + section(3, 256, len(strings)) + section(6, 256+len(strings), 32, 1, 16) + strings + struct.pack('<QQQQ', 1, 1, 0, 0) + identity
pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_bytes(data)
'''
    fixture.executable('g++', compile_body)
    fixture.executable('x86_64-w64-mingw32-gcc-posix', compile_body)
    fixture.executable('winebuild', '''
if '--builtin' not in sys.argv:
 print('fixture host build tool 9.0'); sys.exit(0)
path = pathlib.Path(sys.argv[-1]); data = bytearray(path.read_bytes())
data[64:80] = b'Wine builtin DLL'; path.write_bytes(data)
''', fixture.lib)
    fixture.save()
    return fixture, session


def test_publication_main_builds_production_then_support_with_same_owned_session(monkeypatch, tmp_path):
    module = builder_module()
    repo = tmp_path / 'repo'
    session = object()
    calls = []
    monkeypatch.setattr(module, '__file__', str(repo / 'scripts/wine/build_publication.py'))
    monkeypatch.setattr(module.sys, 'argv', ['build_publication.py'])
    monkeypatch.setenv('SPACE_WINE_SESSION_ID', 'a' * 32)
    monkeypatch.setattr(module.prefix, 'load_session', lambda root, identifier: session)
    def production(root, owned):
        assert root == repo and owned is session
        calls.append('production')
        return {'build_id': 'b' * 64}
    def support(root, owned):
        assert root == repo and owned is session
        calls.append('support')
    monkeypatch.setattr(module, 'build_publication', production)
    monkeypatch.setattr(module, 'build_test_support', support)
    module.main()
    assert calls == ['production', 'support']


def test_publication_fixed_builder_seals_pair_and_replaces_only_recognized_output(publication_fixture):
    fixture, session = publication_fixture
    module = builder_module()
    manifest = module.build_publication(fixture.root, session)
    assert set(manifest) == {'version', 'abi', 'build_id', 'runtime', 'toolchain', 'files'}
    assert manifest['version'] == 1 and manifest['abi'] == 1
    assert manifest['runtime'] == session.owner['tools']['wine'] and set(manifest['files']) == set(PAIR)
    output = fixture.root / 'build/wine-publication'
    assert json.loads((output / 'build.json').read_text()) == manifest
    assert {str(path.relative_to(output)) for path in output.rglob('*') if path.is_file()} == {*PAIR, 'build.json'}
    for relative in PAIR:
        raw = (output / relative).read_bytes()
        assert bytes.fromhex(manifest['build_id']) in raw
        assert manifest['files'][relative]['sha256'] == hashlib.sha256(raw).hexdigest()
        assert manifest['files'][relative]['architecture'] == 'x86_64'
    assert manifest['files'][PAIR[1]]['dependencies'] == ['libc.so.6']
    assert manifest['files'][PAIR[0]]['dependencies'] == []
    assert module.build_publication(fixture.root, session) == manifest
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable')]
    builtins = [call for call in fixture.calls() if '--builtin' in call]
    assert len(builtins) == 2 and all(Path(call[-1]).name == 'space_record_publication.dll' for call in builtins)


@pytest.mark.parametrize('damage', ['extra', 'symlink-root', 'symlink-file', 'unrecognized', 'tamper', 'unowned'])
def test_publication_builder_refuses_unsafe_existing_output_without_compiling(publication_fixture, monkeypatch, damage):
    fixture, session = publication_fixture
    module = builder_module()
    module.build_publication(fixture.root, session)
    output = fixture.root / 'build/wine-publication'
    if damage == 'extra':
        (output / 'foreign').write_text('keep')
    elif damage == 'symlink-root':
        output.rename(output.with_name('saved'))
        output.symlink_to(output.with_name('saved'), target_is_directory=True)
    elif damage == 'symlink-file':
        path = output / PAIR[0]
        path.unlink()
        path.symlink_to(fixture.lib / 'wine64')
    elif damage == 'unrecognized':
        (output / 'build.json').write_text('{}')
    elif damage == 'tamper':
        (output / PAIR[0]).write_bytes(b'foreign')
    else:
        original = os.stat
        def foreign_owner(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            if Path(path) == output:
                fields = list(value)
                fields[4] = os.geteuid() + 1
                return os.stat_result(fields)
            return value
        monkeypatch.setattr(os, 'stat', foreign_owner)
    before = len([call for call in fixture.calls() if '-o' in call])
    with pytest.raises((ValueError, OSError)):
        module.build_publication(fixture.root, session)
    assert len([call for call in fixture.calls() if '-o' in call]) == before
    if damage == 'extra':
        assert (output / 'foreign').read_text() == 'keep'


def test_publication_builder_binds_source_header_and_tool_inputs(publication_fixture):
    fixture, session = publication_fixture
    module = builder_module()
    first = module.build_publication(fixture.root, session)
    assert set(first['toolchain']['inputs']) == set(BUILD_INPUTS)
    for path in [fixture.root / ABI_HEADER, fixture.root / AUTHORITY_HEADER,
                 Path(fixture.files['libwine-dev:amd64'][0]), fixture.lib / 'winebuild']:
        with path.open('a') as stream:
            stream.write('\n# changed identity input\n' if path.name == 'winebuild' else '\n/* changed identity input */\n')
        next_manifest = module.build_publication(fixture.root, session)
        assert next_manifest['build_id'] != first['build_id']
        first = next_manifest


@pytest.mark.parametrize('relative', BUILD_INPUTS)
def test_every_complete_pair_input_changes_build_id(publication_fixture, relative):
    fixture, session = publication_fixture
    module = builder_module()
    first = module.build_publication(fixture.root, session)
    path = fixture.root / relative
    path.write_bytes(path.read_bytes() + b'\n/* changed fixed pair input */\n')
    second = module.build_publication(fixture.root, session)
    assert second['build_id'] != first['build_id'], relative


def test_complete_pair_inventory_is_exact_not_identity_only():
    assert tuple(builder_module().INPUTS) == BUILD_INPUTS


def test_publication_builder_uses_named_units_and_links_authority_api(publication_fixture, monkeypatch):
    fixture, session = publication_fixture
    module = builder_module()
    monkeypatch.setattr(module, 'INPUTS', tuple(reversed(module.INPUTS)))
    module.build_publication(fixture.root, session)
    commands = [call for call in fixture.calls() if '-o' in call]
    assert len(commands) == 2
    host = next(call for call in commands if Path(call[0]).name == 'g++')
    pe = next(call for call in commands if Path(call[0]).name == 'x86_64-w64-mingw32-gcc-posix')
    assert str(fixture.root / UNIX_SOURCE) in host and str(fixture.root / PE_SOURCE) not in host
    assert str(fixture.root / PE_SOURCE) in pe and '-ladvapi32' in pe
    assert str(fixture.root / ADAPTER_SOURCE) in host and str(fixture.root / PUBLICATION_SOURCE) in host
    assert '-pthread' in host and '-ldl' in host
    assert all(str(fixture.root / relative) not in pe for relative in (UNIX_SOURCE, ADAPTER_SOURCE, PUBLICATION_SOURCE))


@pytest.mark.parametrize('field,value', [('files', None), ('toolchain', None), ('runtime', None)])
def test_publication_builder_malformed_manifest_fails_explicitly(publication_fixture, field, value):
    fixture, session = publication_fixture
    module = builder_module()
    manifest = module.build_publication(fixture.root, session)
    manifest[field] = value
    (fixture.root / 'build/wine-publication/build.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='[Mm]anifest'):
        module.build_publication(fixture.root, session)


def test_publication_builder_compiler_failure_is_bounded_and_preserves_previous_pair(publication_fixture):
    fixture, session = publication_fixture
    module = builder_module()
    old = module.build_publication(fixture.root, session)
    compiler = fixture.bin / 'g++'
    compiler.write_text(compiler.read_text().replace("if '-o' not in sys.argv:",
                        "if '-o' in sys.argv:\n sys.stderr.write('x' * 20000); sys.exit(7)\nif '-o' not in sys.argv:"))
    with pytest.raises(ValueError, match='compiler failed') as error:
        module.build_publication(fixture.root, session)
    assert len(str(error.value)) < 4400 and str(error.value).endswith('[truncated]')
    assert json.loads((fixture.root / 'build/wine-publication/build.json').read_text()) == old
    assert not list((fixture.root / 'build').glob('.wine-publication-*'))


@pytest.mark.parametrize('damage', ['pe-machine', 'elf-machine', 'builtin', 'build-id'])
def test_publication_builder_checks_images_before_installing(publication_fixture, monkeypatch, damage):
    fixture, session = publication_fixture
    module = builder_module()
    compile_fixed = module._compile
    def damaged(args, stage):
        compile_fixed(args, stage)
        if '-o' in args:
            path = Path(args[args.index('-o') + 1])
            raw = bytearray(path.read_bytes())
            if damage == 'pe-machine' and path.suffix == '.dll':
                raw[132:134] = bytes(2)
            if damage == 'elf-machine' and path.suffix == '.so':
                raw[18:20] = bytes(2)
            if damage == 'build-id':
                raw[-32:] = bytes(32)
            path.write_bytes(raw)
        elif '--builtin' in args and damage == 'builtin':
            path = Path(args[-1])
            raw = bytearray(path.read_bytes())
            raw[64:80] = bytes(16)
            path.write_bytes(raw)
    monkeypatch.setattr(module, '_compile', damaged)
    with pytest.raises(ValueError):
        module.build_publication(fixture.root, session)
    assert not (fixture.root / 'build/wine-publication').exists()


def test_publication_builder_cli_loads_existing_immutable_session_without_wine(support_builder_fixture):
    fixture, session = support_builder_fixture
    # Exercise the real CLI main with an explicit compiler-protocol metadata
    # model. Inert script tools under /tmp are deliberately NOT trusted runtimes.
    driver = ("import sys; from wine import build_publication as b; "
              f"b._capture_launch_metadata = lambda *args: {fixture.launch_metadata!r}; "
              "sys.argv = [b.__file__]; b.main()")
    result = subprocess.run([sys.executable, '-c', driver],
                             env=dict(fixture.env, SPACE_WINE_SESSION_ID=session.id,
                                      PYTHONPATH=str(fixture.root / 'scripts') + os.pathsep + fixture.env['PYTHONPATH']),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary['version'] == 1 and summary['abi'] == 1 and summary['files'] == list(PAIR)
    module = builder_module()
    production = module._recognized_output(fixture.root / 'build/wine-publication')[1]
    support = module._recognized_test_output(fixture.root / 'build/wine-publication-tests')[1]
    assert summary['build_id'] == production['build_id'] != support['build_id']
    assert production['runtime'] == support['runtime'] == session.owner['tools']['wine']
    assert set(production['files']) == set(PAIR)
    assert set(support['files']) == {*SUPPORT_PAIR, SUPPORT_COPY}
    assert support['kind'] == 'record-publication-test-support'
    assert support['files'][SUPPORT_COPY] == support['files'][SUPPORT_PAIR[0]]
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable')]


@pytest.mark.parametrize('arguments,session_id', [(['extra'], None), ([], None), ([], 'not-a-session')])
def test_publication_builder_cli_refuses_arguments_or_missing_owned_handoff(tmp_path, arguments, session_id):
    script = ROOT / BUILDER_SOURCE
    assert script.is_file(), 'fixed publication builder is missing'
    env = dict(os.environ)
    env.pop('SPACE_WINE_SESSION_ID', None)
    if session_id is not None:
        env['SPACE_WINE_SESSION_ID'] = session_id
    result = subprocess.run([sys.executable, str(script), *arguments], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and 'refused' in result.stderr.lower()


# Task7A1: the support pair is deliberately independent of the production ABI.
SUPPORT_HEADER = 'tests/record_publication_wine_support.h'
SUPPORT_PE = 'tests/record_publication_wine_support_pe.c'
SUPPORT_UNIX = 'tests/record_publication_wine_support_unix.cpp'
SUPPORT_INPUTS = (SUPPORT_HEADER, SUPPORT_PE, SUPPORT_UNIX, BUILDER_SOURCE,
                  'scripts/wine/publication_toolchain.py', 'scripts/wine/prefix.py',
                  'src/record_publication_wine_binding.h', 'src/record_publication_wine_abi.h')
SUPPORT_PAIR = ('modules/x86_64-windows/space_record_publication_tests.dll',
                'modules/x86_64-unix/space_record_publication_tests.so')
SUPPORT_COPY = 'space_record_publication_tests.dll'


def support_host_launch_header(directory, checkout, runtime_source='int main(void) { return 97; }\n'):
    """Native model pins use actual host facts, never production capture exceptions."""
    runtime = directory / 'inert-wine64'
    result = subprocess.run(['cc', '-x', 'c', '-', '-o', str(runtime)],
                            input=runtime_source, text=True,
                            capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    server = directory / 'inert-wineserver'
    shutil.copy2(runtime, server)
    def pin(path):
        info = path.stat()
        return dict(path_hex=os.fsencode(path).hex(), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    device=info.st_dev, inode=info.st_ino, size=info.st_size, uid=info.st_uid, mode=info.st_mode,
                    mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns,
                    ancestors=[dict(path_hex=os.fsencode(parent).hex(), device=parent.stat().st_dev,
                                    inode=parent.stat().st_ino, uid=parent.stat().st_uid, mode=parent.stat().st_mode)
                               for parent in reversed(path.parents)])
    metadata = dict(schema=1, checkout_path_hex=os.fsencode(checkout).hex(),
                    implementation=pin(runtime), server=pin(server))
    (directory / 'srpt_launch_config.h').write_bytes(builder_module()._render_launch_header(metadata))
    return metadata


class SupportCall(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('abi', ctypes.c_uint32),
                ('opcode', ctypes.c_uint32), ('reserved', ctypes.c_uint32),
                ('root', ctypes.c_uint64), ('mode', ctypes.c_uint32), ('gid', ctypes.c_uint32),
                ('data_size', ctypes.c_uint32), ('os_error', ctypes.c_uint32),
                ('device', ctypes.c_uint64), ('inode', ctypes.c_uint64),
                ('links', ctypes.c_uint64), ('file_size', ctypes.c_uint64),
                ('uid', ctypes.c_uint32), ('reserved2', ctypes.c_uint32),
                ('offset', ctypes.c_uint64),
                ('path', ctypes.c_char * 4096), ('other', ctypes.c_char * 4096),
                ('data', ctypes.c_ubyte * 4096)]


@pytest.fixture(scope='module')
def support_elf(tmp_path_factory):
    source = ROOT / SUPPORT_UNIX
    assert source.is_file(), 'test-only Unix support is missing'
    directory = tmp_path_factory.mktemp('real-publication-support')
    support_host_launch_header(directory, ROOT)
    output = directory / 'support.so'
    expected = bytes(range(32))
    definition = '-DSRPT_BUILD_ID_BYTES={' + ','.join(hex(b) for b in expected) + '}'
    result = subprocess.run(['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                             '-fPIC', '-shared', '-fvisibility=hidden', '-static-libgcc', '-static-libstdc++',
                             '-I', str(directory), '-I', str(ROOT / 'tests'), '-I', str(ROOT / 'src'),
                             definition, str(source), '-pthread', '-o', str(output), '-ldl'],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    library = ctypes.CDLL(str(output))
    entries = (ctypes.c_void_p * 2).in_dll(library, '__wine_unix_call_funcs')
    entry = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p)
    return output, library, entry(entries[0]), entry(entries[1]), expected


def support_call(operate, opcode, root=0, path='', other='', data=b'', mode=0, gid=0, offset=0):
    value = SupportCall(size=ctypes.sizeof(SupportCall), abi=2, opcode=opcode, root=root,
                        path=os.fsencode(path), other=os.fsencode(other), mode=mode, gid=gid,
                        offset=offset, data_size=len(data))
    value.data[:len(data)] = data
    status = operate(ctypes.byref(value))
    return status, value


def support_ok(operate, opcode, **kwargs):
    status, value = support_call(operate, opcode, **kwargs)
    assert status == 0, (opcode, status, value.os_error, kwargs)
    return value


def test_support_real_elf_identity_is_loaded_object_not_replacement(support_elf):
    output, library, identify, _, expected = support_elf
    value = Identity(size=112, abi=2, challenge=0x12345678)
    value.pe_build_id[:] = bytes([0xa5]) * 32
    info = output.stat()
    assert identify(ctypes.byref(value)) == 0
    assert (value.module_device, value.module_inode) == (info.st_dev, info.st_ino)
    assert value.echo == value.challenge and value.architecture == 0x8664 and value.features == 7
    assert bytes(value.pe_build_id) == bytes([0xa5]) * 32
    assert bytes(value.unix_build_id) == expected
    assert bytes((ctypes.c_uint8 * 32).in_dll(library, 'SpaceRecordPublicationTestsUnixBuildId')) == expected
    saved = output.with_suffix('.loaded')
    output.rename(saved)
    output.write_bytes(b'not the loaded ELF')
    try:
        assert identify(ctypes.byref(value)) == 0
        assert (value.module_device, value.module_inode) == (info.st_dev, info.st_ino)
        assert value.module_inode != output.stat().st_ino
    finally:
        output.unlink()
        saved.rename(output)
    assert identify(None) != 0
    for size, abi in [(111, 2), (113, 2), (112, 1), (112, 3)]:
        assert identify(ctypes.byref(Identity(size=size, abi=abi))) != 0


def test_support_real_elf_observations_mutations_and_retained_parent(support_elf, tmp_path):
    import stat
    _, _, _, operate, _ = support_elf
    root_path = tmp_path / 'fixture'
    root_path.mkdir(mode=0o700)
    root = support_ok(operate, 1, path=str(root_path)).root
    try:
        support_ok(operate, 4, root=root, path='anchor', mode=0o700)
        support_ok(operate, 4, root=root, path='anchor/attempt', mode=0o700)
        support_ok(operate, 5, root=root, path='anchor/attempt/record', mode=0o600)
        for name in ['', 'anchor', 'anchor/attempt', 'anchor/attempt/record']:
            value = support_ok(operate, 3, root=root, path=name)
            actual = (root_path / name).stat()
            assert (value.device, value.inode, value.mode, value.uid, value.gid, value.links, value.file_size) == (
                actual.st_dev, actual.st_ino, actual.st_mode, actual.st_uid, actual.st_gid, actual.st_nlink, actual.st_size)
        assert support_ok(operate, 3, root=root, path='anchor/attempt/record').data_size == 0
        listing = support_ok(operate, 3, root=root, path='anchor/attempt')
        assert bytes(listing.data[:listing.data_size]) == b'record\0'
        data = b'\x00binary\xff\xe9\x9b\xaa' * 300
        support_ok(operate, 6, root=root, path='anchor/attempt/record', data=data)
        value = support_ok(operate, 3, root=root, path='anchor/attempt/record')
        assert value.file_size == len(data) and bytes(value.data[:value.data_size]) == data
        assert stat.S_IMODE(value.mode) == 0o600
        support_ok(operate, 7, root=root, path='anchor/attempt/record', mode=0o640)
        support_ok(operate, 13, root=root, path='anchor/attempt/record', gid=os.getegid())
        assert (root_path / 'anchor/attempt/record').stat().st_mode & 0o777 == 0o640
        support_ok(operate, 12, root=root, path='anchor/attempt/record', data=b'unsafe')
        assert os.getxattr(root_path / 'anchor/attempt/record', 'user.space-publication-test') == b'unsafe'
        support_ok(operate, 8, root=root, path='anchor/attempt/record', other='hard')
        assert support_ok(operate, 3, root=root, path='hard').links == 2
        # Mutating through an unexpected hardlink is refused, not a host escape.
        assert support_call(operate, 7, root=root, path='hard', mode=0o777)[0] != 0
        support_ok(operate, 11, root=root, path='hard')
        support_ok(operate, 9, root=root, path='sym', other='anchor/attempt/record')
        assert stat.S_ISLNK(support_ok(operate, 3, root=root, path='sym').mode)
        support_ok(operate, 10, root=root, path='anchor/attempt/record', other='saved')
        support_ok(operate, 5, root=root, path='anchor/attempt/record', data=b'foreign', mode=0o600)
        # The retained descriptor survives replacement of its original path.
        moved = tmp_path / 'moved'
        root_path.rename(moved)
        root_path.mkdir(mode=0o700)
        support_ok(operate, 6, root=root, path='saved', data=b'retained')
        assert (moved / 'saved').read_bytes() == b'retained' and not (root_path / 'saved').exists()
        support_ok(operate, 11, root=root, path='sym')
        support_ok(operate, 11, root=root, path='anchor/attempt/record')
        support_ok(operate, 14, root=root, path='anchor/attempt')
    finally:
        support_ok(operate, 2, root=root)
    assert support_call(operate, 3, root=root)[0] != 0


@pytest.mark.parametrize('bad', ['../escape', 'a/../escape', '/absolute', './record', 'a//b', 'a/'])
def test_support_real_elf_refuses_non_fixture_names(support_elf, tmp_path, bad):
    operate = support_elf[3]
    root = support_ok(operate, 1, path=str(tmp_path)).root
    try:
        assert support_call(operate, 5, root=root, path=bad, mode=0o600)[0] != 0
        assert support_call(operate, 9, root=root, path='sym', other=bad)[0] != 0
        assert not list(tmp_path.iterdir())
    finally:
        support_ok(operate, 2, root=root)


def test_support_real_elf_refuses_unsafe_roots_links_frames_and_oversize(support_elf, tmp_path):
    operate = support_elf[3]
    outside = tmp_path / 'outside'
    outside.mkdir(mode=0o700)
    (outside / 'keep').write_bytes(b'keep')
    root_path = tmp_path / 'fixture'
    root_path.mkdir(mode=0o750)
    assert support_call(operate, 1, path=str(root_path))[0] != 0
    assert root_path.stat().st_mode & 0o777 == 0o750
    root_path.chmod(0o700)
    root = support_ok(operate, 1, path=str(root_path)).root
    try:
        (root_path / 'escape').symlink_to(outside, target_is_directory=True)
        assert support_call(operate, 1, path=str(root_path / 'escape'))[0] != 0
        for opcode in [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]:
            assert support_call(operate, opcode, root=root, path='escape/keep', other='x', mode=0o600)[0] != 0
        (root_path / 'leaf').symlink_to(outside / 'keep')
        for opcode in [6, 7, 12, 13]:
            assert support_call(operate, opcode, root=root, path='leaf', data=b'x', mode=0o600)[0] != 0
        assert (outside / 'keep').read_bytes() == b'keep'
        # A directory listing is bounded and must never silently omit entries.
        (root_path / 'large').mkdir()
        for index in range(100):
            (root_path / 'large' / (str(index) + 'x' * 50)).touch()
        status, value = support_call(operate, 3, root=root, path='large')
        assert status != 0 and value.os_error != 0
        assert operate(None) != 0
        for changes in [dict(size=1), dict(abi=1), dict(abi=3), dict(opcode=99), dict(reserved=1),
                        dict(reserved2=1), dict(data_size=4097), dict(mode=0o10000), dict(root=0)]:
            value = SupportCall(size=ctypes.sizeof(SupportCall), abi=2, opcode=3, root=root)
            for key, val in changes.items():
                setattr(value, key, val)
            assert operate(ctypes.byref(value)) != 0, changes
        value = SupportCall(size=ctypes.sizeof(SupportCall), abi=2, opcode=3, root=root)
        value.path = b'x' * 4096
        assert operate(ctypes.byref(value)) != 0
    finally:
        support_ok(operate, 2, root=root)


@pytest.mark.parametrize('compiler,standard', [('cc', 'c11'), ('c++', 'c++17')])
def test_support_closed_abi_layout(tmp_path, compiler, standard):
    assert (ROOT / SUPPORT_HEADER).is_file(), 'test-only ABI is missing'
    offsets = dict(size=0, abi=4, action=8, case_id=12, root=16,
                   production_build_id=24, support_build_id=56, production_device=88,
                   production_inode=96, support_device=104, support_inode=112,
                   phase=120, os_error=124, exit_code=128, term_signal=132,
                   outcome=136, reserved=140, remaining_ms=144, reserved2=148)
    assertion = 'static_assert' if compiler == 'c++' else '_Static_assert'
    alignment = 'alignof' if compiler == 'c++' else '_Alignof'
    source = '#include "record_publication_wine_support.h"\n'
    for field, offset in offsets.items():
        source += f'{assertion}(offsetof(SrptLaunch, {field}) == {offset}, "{field}");\n'
    source += f'''{assertion}(sizeof(SrptLaunch) == 152 && {alignment}(SrptLaunch) == 8, "launch layout");
{assertion}(SRPT_ABI == 2 && SRPT_FEATURES == 7 && SRPT_ENTRY_LAUNCH == 2, "support only ABI2");
{assertion}(SRPT_CONFIGURE == 1 && SRPT_RUN == 2, "launch actions");
int main(void) {{ return sizeof(SrptCall) != 12376 || sizeof(SrptIdentity) != 112; }}
'''
    result = subprocess.run([compiler, f'-std={standard}', '-Wall', '-Wextra', '-Werror',
                             '-I', str(ROOT / 'tests'), '-x', 'c++' if compiler == 'c++' else 'c',
                             '-', '-o', str(tmp_path / 'layout')], input=source,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert subprocess.run([str(tmp_path / 'layout')], timeout=10).returncode == 0


def test_support_launch_native_abi_validation(tmp_path):
    support_host_launch_header(tmp_path, ROOT)
    model = tmp_path / 'launch.cpp'
    model.write_text(r'''
#include "record_publication_wine_support.h"
#include <cassert>
#include <cerrno>
#include <cstring>
using Entry = int32_t (*)(void*);
extern "C" const Entry __wine_unix_call_funcs[];
int main() {
    const auto launch = __wine_unix_call_funcs[SRPT_ENTRY_LAUNCH];
    assert(launch(nullptr) == SRPT_INVALID_ARGUMENT);
    SrptLaunch input {};
    input.size = sizeof(input); input.abi = 2; input.action = SRPT_CONFIGURE;
    input.root = 123;
    for (unsigned field = 0; field < 16; ++field) {
        auto bad = input;
        switch (field) {
        case 0: --bad.size; break; case 1: ++bad.size; break;
        case 2: bad.abi = 1; break; case 3: bad.abi = 3; break;
        case 4: bad.action = 0; break; case 5: bad.action = 3; break;
        case 6: bad.case_id = 1; break;
        case 7: bad.action = SRPT_RUN; bad.case_id = 0; break;
        case 8: bad.action = SRPT_RUN; bad.case_id = 6; break;
        case 9: bad.phase = 1; break; case 10: bad.os_error = 1; break;
        case 11: bad.exit_code = 1; break; case 12: bad.term_signal = 1; break;
        case 13: bad.outcome = 1; break; case 14: bad.remaining_ms = 1; break;
        case 15: bad.reserved = 1; break;
        }
        assert(launch(&bad) == SRPT_INVALID_ARGUMENT);
    }
    auto bad = input; bad.reserved2 = 1;
    assert(launch(&bad) == SRPT_INVALID_ARGUMENT);
}
''')
    definition = '-DSRPT_BUILD_ID_BYTES={' + ','.join(['1'] * 32) + '}'
    result = subprocess.run(['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                             '-I', str(tmp_path), '-I', str(ROOT / 'tests'), '-I', str(ROOT / 'src'),
                             definition, str(ROOT / SUPPORT_UNIX),
                             str(model), '-pthread', '-o', str(tmp_path / 'launch'), '-ldl'],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(tmp_path / 'launch')], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert not result.stdout and not result.stderr


SUPPORT_FIXED_NATIVE_RUNTIME = r'''
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>
extern char **environ;
#define CHECK(value) do { if (!(value)) return 81; } while (0)
int main(int argc, char **argv) {
    char cwd[8192], expected[16384];
    CHECK(argc == 3 && getcwd(cwd, sizeof(cwd)));
    CHECK(!strncmp(argv[1], cwd, strlen(cwd)) && !strcmp(argv[1] + strlen(cwd), "/test_record_publication.exe"));
    CHECK(!strncmp(argv[2], "--wine-publication-child=", 25));
    struct stat info;
    CHECK(!stat(argv[1], &info) && S_ISREG(info.st_mode)); /* Never interpret/execute PE bytes. */
    CHECK(getpgrp() == getpid());
    CHECK(fcntl(0, F_GETFL) >= 0 && fcntl(1, F_GETFL) >= 0 && fcntl(2, F_GETFL) >= 0);
    CHECK(!fstat(0, &info) && S_ISCHR(info.st_mode) && major(info.st_rdev) == 1 && minor(info.st_rdev) == 3);
    char input;
    CHECK(read(0, &input, 1) == 0);
    for (int fd = 3; fd < 512; ++fd) CHECK(fcntl(fd, F_GETFD) == -1);
    sigset_t mask;
    CHECK(!sigprocmask(SIG_SETMASK, NULL, &mask));
    for (int sig = 1; sig < NSIG; ++sig) CHECK(sigismember(&mask, sig) != 1);
    for (int sig = 1; sig < NSIG; ++sig) {
        if (sig == SIGKILL || sig == SIGSTOP || sig == 32 || sig == 33) continue;
        struct sigaction action;
        if (!sigaction(sig, NULL, &action)) CHECK(action.sa_handler == SIG_DFL);
    }
    CHECK(getenv("PATH") && !*getenv("PATH"));
    const char *crypto = getenv("SPACE_WINE_PUBLICATION_TEST_CRYPTO");
    CHECK(crypto && (!strcmp(crypto, "b") || !strcmp(crypto, "n")));
    snprintf(expected, sizeof(expected), "space_record_publication=b;space_record_publication_tests=b;bcryptprimitives=%s;advapi32,cryptbase=b", crypto);
    CHECK(getenv("WINEDLLOVERRIDES") && !strcmp(getenv("WINEDLLOVERRIDES"), expected));
    snprintf(expected, sizeof(expected), "%s/modules:%s/build/wine-publication-tests/modules", cwd, (const char*)checkout);
    CHECK(getenv("WINEDLLPATH") && !strcmp(getenv("WINEDLLPATH"), expected));
    const char *allowed[] = {"WINEPREFIX", "WINEARCH", "WINESERVER", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TMPDIR", "TEMP", "TMP",
        "SPACE_WINE_WINDOWS_TMP", "SPACE_WINE_PUBLICATION_TEST_CRYPTO", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "DISPLAY",
        "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "PATH", "WINEDLLOVERRIDES", "WINEDLLPATH", "SPACE_WINE_PUBLICATION_BINDING",
        "SPACE_WINE_PUBLICATION_TEST_BINDING"};
    for (char **item = environ; *item; ++item) {
        int found = 0;
        for (unsigned index = 0; index < sizeof(allowed) / sizeof(allowed[0]); ++index)
            if (!strncmp(*item, allowed[index], strlen(allowed[index])) && (*item)[strlen(allowed[index])] == '=') found = 1;
        CHECK(found);
    }
    printf("SRPT_NATIVE_CHILD %s\n", argv[2] + 25);
    fflush(stdout);
    RUNTIME_RESULT
}
'''


SUPPORT_CHILD_SYSCALL_WRAPPERS = r'''
#define CHILD_FAIL(tag, function, signature, arguments) \
    static std::atomic<bool> child_fault_##tag {false}; \
    extern "C" int __real_##function signature; \
    extern "C" int __wrap_##function signature { if (child_fault_##tag.exchange(false)) return EIO; return __real_##function arguments; } \
    extern "C" __attribute__((visibility("default"))) void srpt_host_fault_##tag() { child_fault_##tag = true; }
#define CHILD_DESTROY(tag, function, signature, arguments) \
    static std::atomic<bool> child_fault_##tag {false}; \
    extern "C" int __real_##function signature; \
    extern "C" int __wrap_##function signature { const int result = __real_##function arguments; return child_fault_##tag.exchange(false) ? EIO : result; } \
    extern "C" __attribute__((visibility("default"))) void srpt_host_fault_##tag() { child_fault_##tag = true; }
CHILD_FAIL(action_init, posix_spawn_file_actions_init, (posix_spawn_file_actions_t* value), (value))
CHILD_FAIL(attr_init, posix_spawnattr_init, (posix_spawnattr_t* value), (value))
CHILD_FAIL(action_open, posix_spawn_file_actions_addopen, (posix_spawn_file_actions_t* value, int fd, const char* path, int flags, mode_t mode), (value, fd, path, flags, mode))
CHILD_FAIL(action_cwd, posix_spawn_file_actions_addfchdir_np, (posix_spawn_file_actions_t* value, int fd), (value, fd))
CHILD_FAIL(action_closefrom, posix_spawn_file_actions_addclosefrom_np, (posix_spawn_file_actions_t* value, int fd), (value, fd))
CHILD_FAIL(attr_mask, posix_spawnattr_setsigmask, (posix_spawnattr_t* value, const sigset_t* mask), (value, mask))
CHILD_FAIL(attr_default, posix_spawnattr_setsigdefault, (posix_spawnattr_t* value, const sigset_t* mask), (value, mask))
CHILD_FAIL(attr_group, posix_spawnattr_setpgroup, (posix_spawnattr_t* value, pid_t group), (value, group))
CHILD_DESTROY(action_destroy, posix_spawn_file_actions_destroy, (posix_spawn_file_actions_t* value), (value))
CHILD_DESTROY(attr_destroy, posix_spawnattr_destroy, (posix_spawnattr_t* value), (value))
static std::atomic<bool> child_fault_flags {false}, child_fault_reserve {false}, child_fault_spawn {false},
    child_fault_post_pin {false}, child_fault_partial_spawn {false}, child_fault_post_alloc {false}, child_fault_waitid_late {false},
    child_fault_waitid_wrong {false}, child_fault_waitid_badcode {false}, child_fault_waitid_badstatus {false},
    child_fault_waitid_echild {false}, child_fault_waitpid_echild {false}, child_fault_waitpid_late {false},
    child_fault_kill {false}, child_fault_reaper {false}, child_fault_close_spawn {false}, child_fault_close_reap {false}, child_fault_clock {false};
static std::atomic<int> child_fault_waitid_eintr {0}, child_fault_waitpid_eintr {0};
static std::atomic<pid_t> host_child {-1};
static int host_spawns = 0, host_kills = 0, host_waitids = 0, host_created = 0, host_native_reaps = 0,
    host_backstop_kills = 0, host_backstop_reaps = 0;
static bool host_force_reap_poll = false;
static std::atomic<bool> host_reaped {false};
static bool host_zeroed = true, host_anchor = true, host_waitid_preserved = false;
extern "C" int __real_posix_spawnattr_setflags(posix_spawnattr_t*, short);
extern "C" int __wrap_posix_spawnattr_setflags(posix_spawnattr_t* value, short flags) {
    if (child_fault_flags.exchange(false)) return EIO;
    const int result = __real_posix_spawnattr_setflags(value, flags);
    if (!result && child_fault_reserve.exchange(false)) host_advance = true;
    return result;
}
extern "C" int __real_posix_spawn(pid_t*, const char*, const posix_spawn_file_actions_t*, const posix_spawnattr_t*, char* const[], char* const[]);
extern "C" int __wrap_posix_spawn(pid_t* pid, const char* path, const posix_spawn_file_actions_t* actions,
                                  const posix_spawnattr_t* attrs, char* const argv[], char* const env[]) {
    ++host_spawns;
    if (child_fault_spawn.exchange(false)) return ENOENT;
    const int result = __real_posix_spawn(pid, path, actions, attrs, argv, env);
    if (!result) {
        ++host_created;
        host_child = *pid; host_reaped = false;
        host_clock_count = 0; host_clock_overflow = false; host_clock_trace = true;
        host_clock_event(0, host_last_native_clock, configuration->deadline);
        if (child_fault_post_pin.exchange(false)) {
            if (::rename(reinterpret_cast<const char*>(host_pin_replacement),
                         reinterpret_cast<const char*>(srpt_launch_implementation.path))) std::abort();
        }
        if (child_fault_post_alloc.exchange(false)) host_fail_allocation = true;
        if (child_fault_clock.exchange(false)) host_child_clock_failure = true;
        if (child_fault_partial_spawn.exchange(false)) return EIO;
    }
    return result;
}
extern "C" int __real_waitid(idtype_t, id_t, siginfo_t*, int);
extern "C" pid_t __real_waitpid(pid_t, int*, int);
extern "C" int __wrap_waitid(idtype_t kind, id_t pid, siginfo_t* info, int flags) {
    ++host_waitids;
    const auto* bytes = reinterpret_cast<const unsigned char*>(info);
    for (std::size_t index = 0; index < sizeof(*info); ++index) if (bytes[index]) host_zeroed = false;
    if (kind != P_PID || pid != static_cast<id_t>(host_child) || flags != (WEXITED | WNOHANG | WNOWAIT)) std::abort();
    if (child_fault_waitid_eintr.load() > 0) { --child_fault_waitid_eintr; errno = EINTR; return -1; }
    if (child_fault_waitid_late.exchange(false)) {
        host_clock_event(2, host_last_native_clock, INT64_C(48000000000));
        host_advance = true; host_force_reap_poll = true; errno = EINTR; return -1;
    }
    if (child_fault_waitid_echild.exchange(false)) { errno = ECHILD; return -1; }
    if (child_fault_reaper.exchange(false)) {
        int status = 0;
        if (__real_waitpid(host_child, &status, 0) != host_child) std::abort();
        errno = ECHILD; return -1; // Another reaper really consumed the exact leader, not merely a fake errno.
    }
    const int result = __real_waitid(kind, pid, info, flags);
    if (!result && info->si_pid == host_child) {
        siginfo_t again {};
        host_waitid_preserved = __real_waitid(kind, pid, &again, flags) == 0 && again.si_pid == host_child && ::getpgid(host_child) == host_child;
    }
    if (!result && child_fault_waitid_wrong.exchange(false)) { info->si_pid = host_child + 1; info->si_code = CLD_EXITED; info->si_status = 0; }
    if (!result && child_fault_waitid_badcode.exchange(false)) { info->si_pid = host_child; info->si_code = CLD_STOPPED; info->si_status = SIGSTOP; }
    if (!result && child_fault_waitid_badstatus.exchange(false)) { info->si_pid = host_child; info->si_code = CLD_EXITED; info->si_status = 256; }
    return result;
}
extern "C" pid_t __real_waitpid(pid_t, int*, int);
extern "C" pid_t __wrap_waitpid(pid_t pid, int* status, int flags) {
    if (pid != host_child || flags != WNOHANG) std::abort();
    if (child_fault_waitpid_eintr.load() > 0) { --child_fault_waitpid_eintr; errno = EINTR; return -1; }
    if (child_fault_waitpid_late.exchange(false)) {
        host_clock_event(7, host_last_native_clock, INT64_C(48000000000));
        host_advance = true; errno = EINTR; return -1;
    }
    if (child_fault_waitpid_echild.exchange(false)) { errno = ECHILD; return -1; }
    if (std::exchange(host_force_reap_poll, false)) return 0; // Exercise one absolute poll sleep after the clock offset.
    const auto result = __real_waitpid(pid, status, flags);
    if (result == pid) { host_reaped = true; ++host_native_reaps; host_clock_event(5, host_last_native_clock, pid); }
    return result;
}
extern "C" int __real_kill(pid_t, int);
extern "C" int __wrap_kill(pid_t group, int sig) {
    ++host_kills;
    host_clock_event(4, host_last_native_clock, group);
    siginfo_t proof {};
    host_anchor = host_anchor && group == -host_child && sig == SIGKILL && !host_reaped
        && __real_waitid(P_PID, host_child, &proof, WEXITED | WNOHANG | WNOWAIT) == 0 && ::getpgid(host_child) == host_child;
    if (child_fault_kill.exchange(false)) { errno = EPERM; return -1; }
    return __real_kill(group, sig);
}
extern "C" int __real_close(int);
extern "C" int __wrap_close(int fd) {
    const int result = __real_close(fd);
    if ((!host_reaped && host_child > 0 && child_fault_close_spawn.exchange(false))
        || (host_reaped && child_fault_close_reap.exchange(false))) { errno = EIO; return -1; }
    return result;
}
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_flags() { child_fault_flags = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_reserve() { child_fault_reserve = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_spawn() { child_fault_spawn = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_post_pin() { child_fault_post_pin = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_pre_pin() {
    if (::rename(reinterpret_cast<const char*>(host_pin_replacement),
                 reinterpret_cast<const char*>(srpt_launch_implementation.path))) std::abort();
}
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_partial_spawn() { child_fault_partial_spawn = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_reaper() { child_fault_reaper = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_post_alloc() { child_fault_post_alloc = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_waitid_eintr() { child_fault_waitid_eintr = 3; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_waitid_late() { child_fault_waitid_late = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_waitid_wrong() { child_fault_waitid_wrong = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_waitid_badcode() { child_fault_waitid_badcode = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_waitid_badstatus() { child_fault_waitid_badstatus = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_waitid_echild() { child_fault_waitid_echild = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_waitpid_echild() { child_fault_waitpid_echild = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_waitpid_eintr() { child_fault_waitpid_eintr = 3; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_waitpid_late() { child_fault_waitpid_late = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_kill() { child_fault_kill = true; child_fault_post_pin = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_close_spawn() { child_fault_close_spawn = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_close_reap() { child_fault_close_reap = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_fault_clock() { child_fault_clock = true; }
extern "C" __attribute__((visibility("default"))) int srpt_host_spawn_count() { return host_spawns; }
extern "C" __attribute__((visibility("default"))) int srpt_host_kill_count() { return host_kills; }
extern "C" __attribute__((visibility("default"))) int srpt_host_zeroed() { return host_zeroed; }
extern "C" __attribute__((visibility("default"))) int srpt_host_anchor() { return host_anchor; }
extern "C" __attribute__((visibility("default"))) int srpt_host_observation_preserved() { return host_waitid_preserved; }
extern "C" __attribute__((visibility("default"))) int srpt_host_created() { return host_created; }
extern "C" __attribute__((visibility("default"))) int srpt_host_child_pid() { return host_child; }
extern "C" __attribute__((visibility("default"))) int srpt_host_native_reaps() { return host_native_reaps; }
extern "C" __attribute__((visibility("default"))) int srpt_host_reaped() { return host_reaped; }
extern "C" __attribute__((visibility("default"))) int srpt_host_kernel_echild() {
    siginfo_t info {}; errno = 0;
    return host_child > 0 && __real_waitid(P_PID, host_child, &info, WEXITED | WNOHANG | WNOWAIT) == -1 && errno == ECHILD;
}
extern "C" __attribute__((visibility("default"))) int srpt_host_evidence_held() { return uncertain_preparation && !launch_busy_paths.empty(); }
extern "C" __attribute__((visibility("default"))) int srpt_host_backstop_kills() { return host_backstop_kills; }
extern "C" __attribute__((visibility("default"))) int srpt_host_backstop_reaps() { return host_backstop_reaps; }
extern "C" __attribute__((visibility("default"))) int64_t srpt_host_clock_field(unsigned row, unsigned field) {
    if (row >= host_clock_count) return -1;
    const auto& value = host_clock_rows[row];
    return field == 0 ? value.kind : field == 1 ? value.first : value.second;
}
extern "C" __attribute__((visibility("default"))) int srpt_host_clock_rows() { return host_clock_count; }
extern "C" __attribute__((visibility("default"))) int srpt_host_clock_overflowed() { return host_clock_overflow; }
extern "C" __attribute__((visibility("default"))) void srpt_host_no_cldwait() {
    struct sigaction value {}; value.sa_handler = SIG_DFL; value.sa_flags = SA_NOCLDWAIT; ::sigemptyset(&value.sa_mask);
    if (::sigaction(SIGCHLD, &value, nullptr)) std::abort();
}
extern "C" __attribute__((visibility("default"))) int srpt_host_sigchld_flags() {
    struct sigaction value {}; if (::sigaction(SIGCHLD, nullptr, &value)) std::abort(); return value.sa_flags;
}
extern "C" __attribute__((visibility("default"))) void srpt_host_cleanup_child() {
    if (host_child <= 0 || host_reaped) return;
    siginfo_t proof {};
    if (__real_waitid(P_PID, host_child, &proof, WEXITED | WNOHANG | WNOWAIT)) return;
    ++host_backstop_kills;
    if (__real_kill(-host_child, SIGKILL) && errno != ESRCH) std::abort();
    int status = 0; while (__real_waitpid(host_child, &status, 0) < 0) { if (errno != EINTR) std::abort(); }
    host_reaped = true; ++host_backstop_reaps;
}
'''


@pytest.fixture
def support_native_configuration(tmp_path, request):
    import struct
    repo = tmp_path / 'checkout-\udcff'
    repo.mkdir(mode=0o700)
    directories = ('build', 'build/wine', 'build/wine/windows', 'build/wine/sessions',
                   'build/wine-publication', 'build/wine-publication/modules',
                   'build/wine-publication/modules/x86_64-windows', 'build/wine-publication/modules/x86_64-unix',
                   'build/wine-publication-tests', 'build/wine-publication-tests/modules',
                   'build/wine-publication-tests/modules/x86_64-windows',
                   'build/wine-publication-tests/modules/x86_64-unix')
    for name in directories:
        (repo / name).mkdir(mode=0o700)
    session = repo / 'build/wine/sessions' / ('a' * 32)
    session.mkdir(mode=0o700)
    for name in ('prefix', 'tmp', 'data', 'cache'):
        (session / name).mkdir(mode=0o700)
    behavior = getattr(request, 'param', 'success')
    ending = {'success': 'return 0;', 'nonzero': 'return 23;', 'signal': 'raise(SIGUSR1); return 82;',
              'timeout': 'for (;;) pause();',
              'paused': 'if (!strcmp(argv[2] + 25, "control")) raise(SIGSTOP); return 0;'}[behavior]
    declaration = 'static const unsigned char checkout[] = {' + ','.join(str(value) for value in os.fsencode(repo) + b'\0') + '};\n'
    metadata = support_host_launch_header(tmp_path, repo, declaration + SUPPORT_FIXED_NATIVE_RUNTIME.replace('RUNTIME_RESULT', ending))
    pin_replacement = tmp_path / 'inert-wine64-replacement'
    shutil.copy2(tmp_path / 'inert-wine64', pin_replacement)
    assert pin_replacement.stat().st_ino != (tmp_path / 'inert-wine64').stat().st_ino
    production_id, support_id = bytes([0xa5]) * 32, bytes(range(32))
    def pe(identity):
        raw = bytearray(1024)
        raw[:2] = b'MZ'
        struct.pack_into('<I', raw, 60, 128)
        raw[64:80] = b'Wine builtin DLL'
        raw[128:132] = b'PE\0\0'
        struct.pack_into('<HHIIIHH', raw, 132, 0x8664, 0, 0, 0, 0, 240, 0x2022)
        struct.pack_into('<H', raw, 152, 0x20b)
        raw[-32:] = identity
        return raw
    def artifact(relative, data):
        path = repo / relative
        path.write_bytes(data)
        path.chmod(0o600)
        return path
    production = artifact('build/wine-publication/modules/x86_64-unix/space_record_publication.so',
                          (tmp_path / 'inert-wine64').read_bytes() + production_id)
    artifact('build/wine-publication/modules/x86_64-windows/space_record_publication.dll', pe(production_id))
    artifact('build/wine-publication-tests/modules/x86_64-windows/space_record_publication_tests.dll', pe(support_id))
    artifact('build/wine/windows/space_record_publication.dll', pe(production_id))
    artifact('build/wine/windows/space_record_publication_tests.dll', pe(support_id))
    artifact('build/wine/windows/test_record_publication.exe', pe(bytes([0x77]) * 32))
    artifact('build/wine/windows/libfixture.dll', pe(bytes([0x44]) * 32))
    artifact('build/wine/windows/bcryptprimitives.dll', pe(bytes([0x55]) * 32))
    output = repo / 'build/wine-publication-tests/modules/x86_64-unix/space_record_publication_tests.so'
    wrapper = tmp_path / 'support-host.cpp'
    # Test-only inspection/barrier exports wrap the ACTUAL source, never the
    # production ABI or capture policy. No launcher algorithm is copied here.
    replacement_declaration = 'static const unsigned char host_pin_replacement[] = {' + ','.join(
        str(value) for value in os.fsencode(pin_replacement) + b'\0') + '};\n'
    wrapper.write_text('#include <atomic>\n#include ' + json.dumps(str(ROOT / SUPPORT_UNIX)) + '\n' + replacement_declaration + r'''
static std::atomic<bool> host_pause {false}, host_held {false};
static std::atomic<bool> host_advance {false};
struct HostClockRow { int kind; int64_t first, second; };
static std::array<HostClockRow, 32> host_clock_rows;
static unsigned host_clock_count = 0;
static bool host_clock_trace = false, host_clock_overflow = false;
static int64_t host_last_native_clock = 0;
static void host_clock_event(int kind, int64_t first, int64_t second) {
    if (!host_clock_trace) return;
    if (host_clock_count == host_clock_rows.size()) { host_clock_overflow = true; return; }
    host_clock_rows[host_clock_count++] = {kind, first, second};
}
static std::atomic<bool> host_child_clock_failure {false};
static std::atomic<unsigned> host_monotonic_calls {0};
static std::atomic<bool> host_fail_allocation {false};
static std::atomic<bool> host_fail_identity {false};
static std::atomic<bool> host_move_retained_admission {false};
static dev_t host_admission_device = 0;
static ino_t host_admission_inode = 0;
static std::string host_admission_from, host_admission_to;
extern "C" int __real_fstat(int, struct stat*);
extern "C" int __wrap_fstat(int fd, struct stat* info) {
    const int result = __real_fstat(fd, info);
    if (!result && host_move_retained_admission.load() && info->st_dev == host_admission_device
        && info->st_ino == host_admission_inode && host_move_retained_admission.exchange(false)) {
        if (::rename(host_admission_from.c_str(), host_admission_to.c_str())) std::abort();
    }
    return result;
}
extern "C" __attribute__((visibility("default"))) void srpt_host_arm_retained_admission() {
    host_admission_from = configuration->temp_path.substr(0, configuration->temp_path.rfind('/')) + "/retained-late";
    host_admission_to = configuration->temp_path + "/record-publication-123/control/late-root";
    struct stat info {};
    if (::stat(host_admission_from.c_str(), &info)) std::abort();
    host_admission_device = info.st_dev; host_admission_inode = info.st_ino;
    host_move_retained_admission = true;
}
extern "C" FILE* __real_fopen(const char*, const char*);
extern "C" FILE* __wrap_fopen(const char* path, const char* mode) {
    if (!std::strcmp(path, "/proc/self/maps") && host_fail_identity.exchange(false)) { errno = EACCES; return nullptr; }
    return __real_fopen(path, mode);
}
extern "C" __attribute__((visibility("default"))) void srpt_host_fail_identity() { host_fail_identity = true; }
extern "C" void* __real__Znwm(size_t);
extern "C" void* __wrap__Znwm(size_t size) {
    if (host_fail_allocation.exchange(false)) throw std::bad_alloc();
    return __real__Znwm(size);
}
extern "C" __attribute__((visibility("default"))) void srpt_host_fail_allocation() { host_fail_allocation = true; }
extern "C" int __real_clock_gettime(clockid_t, struct timespec*);
extern "C" int __wrap_clock_gettime(clockid_t clock, struct timespec* value) {
    if (clock == CLOCK_MONOTONIC) ++host_monotonic_calls;
    if (clock == CLOCK_MONOTONIC && host_child_clock_failure.exchange(false)) { errno = EIO; return -1; }
    const int result = __real_clock_gettime(clock, value);
    if (!result && clock == CLOCK_MONOTONIC) {
        if (host_advance.load()) value->tv_sec += 48;
        host_last_native_clock = static_cast<int64_t>(value->tv_sec) * INT64_C(1000000000) + value->tv_nsec;
        host_clock_event(1, host_last_native_clock, 0);
    }
    return result;
}
extern "C" int __real_clock_nanosleep(clockid_t, int, const struct timespec*, struct timespec*);
extern "C" int __wrap_clock_nanosleep(clockid_t clock, int flags, const struct timespec* request, struct timespec* remainder) {
    auto translated = *request;
    if (clock == CLOCK_MONOTONIC && flags == TIMER_ABSTIME) {
        if (host_advance.load()) translated.tv_sec -= 48;
        host_clock_event(3, static_cast<int64_t>(request->tv_sec) * INT64_C(1000000000) + request->tv_nsec,
                         static_cast<int64_t>(translated.tv_sec) * INT64_C(1000000000) + translated.tv_nsec);
    }
    return __real_clock_nanosleep(clock, flags, &translated, remainder);
}
extern "C" __attribute__((visibility("default"))) void srpt_host_no_reserve() { host_advance = true; }
extern "C" __attribute__((visibility("default"))) void srpt_host_initial_clock_failure() { host_child_clock_failure = true; }
extern "C" __attribute__((visibility("default"))) unsigned srpt_host_monotonic_calls() { return host_monotonic_calls; }
extern "C" ssize_t __real_pread(int, void*, size_t, off_t);
extern "C" ssize_t __wrap_pread(int fd, void* data, size_t size, off_t offset) {
    if (host_pause.exchange(false)) {
        host_held = true;
        while (host_held.load()) ::usleep(1000);
    }
    return __real_pread(fd, data, size, offset);
}
extern "C" __attribute__((visibility("default"))) void srpt_host_arm() { host_pause = true; }
extern "C" __attribute__((visibility("default"))) int srpt_host_held() { return host_held; }
extern "C" __attribute__((visibility("default"))) void srpt_host_resume() { host_held = false; }
extern "C" __attribute__((visibility("default"))) const char* srpt_host_environment(unsigned index) {
    return configuration && index < configuration->environment.size() ? configuration->environment[index].c_str() : nullptr;
}
static std::unique_ptr<PreparedRun> host_prepared;
extern "C" __attribute__((visibility("default"))) int32_t srpt_host_prepare(void* args) noexcept {
    auto* call = static_cast<SrptLaunch*>(args);
    if (!initialize_launch(call) || call->action != SRPT_RUN) return SRPT_INVALID_ARGUMENT;
    try { host_prepared = prepare_run(*call); return SRPT_SUCCESS; }
    catch (const LaunchError& error) {
        end_failed_preparation(); call->outcome = SRPT_OUTCOME_HOST_FAILURE; call->os_error = error.error;
        return error.status;
    } catch (...) { end_failed_preparation(); call->outcome = SRPT_OUTCOME_HOST_FAILURE; call->os_error = EIO; return SRPT_UNSUCCESSFUL; }
}
extern "C" __attribute__((visibility("default"))) int32_t srpt_host_complete() noexcept {
    try { require(host_prepared != nullptr); complete_preparation(*host_prepared); host_prepared.reset(); return SRPT_SUCCESS; }
    catch (...) { return SRPT_UNSUCCESSFUL; }
}
extern "C" __attribute__((visibility("default"))) const char* srpt_host_argument(unsigned index) {
    return host_prepared && index < host_prepared->arguments.size() ? host_prepared->arguments[index].c_str() : nullptr;
}
extern "C" __attribute__((visibility("default"))) const char* srpt_host_prepared_environment(unsigned index) {
    return host_prepared && index < host_prepared->environment.size() ? host_prepared->environment[index].c_str() : nullptr;
}
extern "C" __attribute__((visibility("default"))) int srpt_host_cwd() { return host_prepared ? host_prepared->cwd.value : -1; }
''' + SUPPORT_CHILD_SYSCALL_WRAPPERS)
    definition = '-DSRPT_BUILD_ID_BYTES={' + ','.join(hex(value) for value in support_id) + '}'
    child_wrappers = ['posix_spawn', 'waitid', 'waitpid', 'kill', 'close', 'fstat', 'posix_spawn_file_actions_init',
                      'posix_spawnattr_init', 'posix_spawn_file_actions_addopen', 'posix_spawn_file_actions_addfchdir_np',
                      'posix_spawn_file_actions_addclosefrom_np', 'posix_spawnattr_setsigmask',
                      'posix_spawnattr_setsigdefault', 'posix_spawnattr_setpgroup', 'posix_spawnattr_setflags',
                      'posix_spawn_file_actions_destroy', 'posix_spawnattr_destroy']
    result = subprocess.run(['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared',
                             '-fvisibility=hidden', '-static-libgcc', '-static-libstdc++',
                             '-I', str(tmp_path), '-I', str(ROOT / 'tests'),
                             '-I', str(ROOT / 'src'), definition, str(wrapper), '-pthread',
                             '-Wl,--wrap=pread', '-Wl,--wrap=clock_gettime', '-Wl,--wrap=clock_nanosleep',
                             '-Wl,--wrap=_Znwm', '-Wl,--wrap=fopen',
                             *['-Wl,--wrap=' + name for name in child_wrappers],
                             '-o', str(output), '-ldl'], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    output.chmod(0o600)
    def binding(path, identity):
        info = path.stat()
        return f'{identity.hex()}:{info.st_dev}:{info.st_ino}'
    production_binding, support_binding = binding(production, production_id), binding(output, support_id)
    env = dict(os.environ, WINEPREFIX=str(session / 'prefix'), WINEARCH='win64',
               WINESERVER=str(tmp_path / 'inert-wineserver'), XDG_DATA_HOME=str(session / 'data'),
               XDG_CACHE_HOME=str(session / 'cache'), TMPDIR=str(session / 'tmp'),
               TEMP='Q:\\owned\\tmp', TMP='Q:\\owned\\tmp', SPACE_WINE_WINDOWS_TMP='Q:\\owned\\tmp',
               SPACE_WINE_PUBLICATION_BINDING=production_binding,
               SPACE_WINE_PUBLICATION_TEST_BINDING=support_binding, SPACE_WINE_PUBLICATION_TEST_CRYPTO='b')
    # Optional parent paths are admitted separately; avoid accidental host-specific inputs.
    env.pop('XDG_RUNTIME_DIR', None)
    return SimpleNamespace(repo=repo, session=session, library=output, env=env, metadata=metadata,
                           production=production, production_binding=production_binding, support_binding=support_binding,
                           behavior=behavior)


SUPPORT_CONFIG_DRIVER = r'''
import ctypes, fcntl, json, os, shutil, signal, socket, sys, threading, time
class SupportCall(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in ('size', 'abi', 'opcode', 'reserved')] + [
        ('root', ctypes.c_uint64)] + [(name, ctypes.c_uint32) for name in ('mode', 'gid', 'data_size', 'os_error')] + [
        (name, ctypes.c_uint64) for name in ('device', 'inode', 'links', 'file_size')] + [
        ('uid', ctypes.c_uint32), ('reserved2', ctypes.c_uint32), ('offset', ctypes.c_uint64),
        ('path', ctypes.c_char * 4096), ('other', ctypes.c_char * 4096), ('data', ctypes.c_ubyte * 4096)]
class Launch(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in ('size', 'abi', 'action', 'case_id')] + [
        ('root', ctypes.c_uint64), ('production_build_id', ctypes.c_ubyte * 32), ('support_build_id', ctypes.c_ubyte * 32)] + [
        (name, ctypes.c_uint64) for name in ('production_device', 'production_inode', 'support_device', 'support_inode')] + [
        (name, ctypes.c_uint32) for name in ('phase', 'os_error', 'exit_code', 'term_signal', 'outcome', 'reserved', 'remaining_ms', 'reserved2')]
assert ctypes.sizeof(SupportCall) == 12376 and SupportCall.path.offset == 88
assert ctypes.sizeof(Launch) == 152 and ctypes.alignment(Launch) == 8 and Launch.phase.offset == 120
library = ctypes.CDLL(sys.argv[2])
entries = (ctypes.c_void_p * 3).in_dll(library, '__wine_unix_call_funcs')
entry = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p)
fixture, launch = entry(entries[1]), entry(entries[2])
sentinels = []
if sys.argv[6].startswith('prepare-execute'):
    sentinels.extend(os.pipe())
    sockets = socket.socketpair()
    sentinels.extend(item.fileno() for item in sockets)
    for fd in sentinels: os.set_inheritable(fd, True)
    signal.signal(signal.SIGUSR1, signal.SIG_IGN)
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR2})
    if sys.argv[6] == 'prepare-execute-ignore': signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    if sys.argv[6] == 'prepare-execute-no_cldwait': library.srpt_host_no_cldwait()
def parent_state():
    status = open('/proc/thread-self/status').read()
    return (dict(os.environ), os.getcwdb(), os.getpgrp(), library.srpt_host_sigchld_flags(),
            tuple(line for line in status.splitlines() if line.startswith(('Umask:', 'SigBlk:', 'SigIgn:', 'SigCgt:'))))
def native_run(call):
    created_before = library.srpt_host_created()
    reaped_before = library.srpt_host_native_reaps()
    started = time.monotonic()
    caller_state = parent_state()
    try:
        status = launch(ctypes.byref(call))
        assert parent_state() == caller_state
        snapshot = dict(created=library.srpt_host_created() - created_before,
            native_reaps=library.srpt_host_native_reaps() - reaped_before,
            native_reaped=library.srpt_host_reaped(), kernel_echild=library.srpt_host_kernel_echild(),
            evidence_held=library.srpt_host_evidence_held(), seconds=time.monotonic() - started)
        if call.outcome == 5:
            snapshot['fd_delta'] = len(os.listdir('/proc/self/fd')) - base_fds
            snapshot['fixture_exists'] = os.path.isdir(owned)
            assert snapshot['evidence_held'] and snapshot['fd_delta'] > 0 and snapshot['fixture_exists']
            for token in (root.root, retained.root):
                request = SupportCall(size=12376, abi=2, opcode=2, root=token)
                assert fixture(ctypes.byref(request)) != 0 and request.os_error == 16
            request = SupportCall(size=12376, abi=2, opcode=5, root=retained.root, path=b'blocked', mode=0o600)
            assert fixture(ctypes.byref(request)) != 0 and request.os_error == 16
        return status, snapshot
    finally:
        # Safety cleanup always runs, but proof assertions use the PRE-cleanup snapshot.
        library.srpt_host_cleanup_child()
root = SupportCall(size=ctypes.sizeof(SupportCall), abi=2, opcode=1, path=os.fsencode(sys.argv[5]))
assert fixture(ctypes.byref(root)) == 0
if 'moved_retained_root' in sys.argv[6]:
    staging_path = os.path.dirname(sys.argv[5]) + '/retained-staging'
    os.mkdir(staging_path, 0o700)
    moved = SupportCall(size=12376, abi=2, opcode=1, path=os.fsencode(staging_path))
    assert fixture(ctypes.byref(moved)) == 0
    fresh_path = os.path.dirname(sys.argv[5]) + '/fresh-unrelated'
    os.mkdir(fresh_path, 0o700)
    fresh = SupportCall(size=12376, abi=2, opcode=1, path=os.fsencode(fresh_path))
    assert fixture(ctypes.byref(fresh)) == 0
    if sys.argv[6].startswith('busy'):
        with open(staging_path + '/marker', 'wb') as output: output.write(b'intact')
        os.rename(staging_path, sys.argv[5] + '/moved-ordinary')
def fixture_request(opcode, token, name=b'', data=b'', mode=0):
    request = SupportCall(size=12376, abi=2, opcode=opcode, root=token, path=name, data_size=len(data), mode=mode)
    request.data[:len(data)] = data
    return [fixture(ctypes.byref(request)), request.os_error], request
def moved_root_probe(name):
    written, _ = fixture_request(6, moved.root, name, b'forbidden-during-lease')
    released, _ = fixture_request(2, moved.root)
    fresh_write, _ = fixture_request(5, fresh.root, b'marker', b'unrelated', 0o600)
    fresh_read, observed = fixture_request(3, fresh.root, b'marker')
    fresh_release, _ = fixture_request(2, fresh.root)
    return dict(write=written, release=released, fresh_write=fresh_write, fresh_read=fresh_read,
                fresh_match=bytes(observed.data[:observed.data_size]) == b'unrelated', fresh_release=fresh_release)
def moved_root_after_lease(name):
    written, _ = fixture_request(6, moved.root, name, b'ordinary-after-lease')
    observed, data = fixture_request(3, moved.root, name)
    released, _ = fixture_request(2, moved.root)
    return dict(write=written, observe=observed, bytes_match=bytes(data.data[:data.data_size]) == b'ordinary-after-lease',
                release=released)
if sys.argv[6] == 'path-replace':
    os.rename(sys.argv[5], sys.argv[5] + '-moved'); os.mkdir(sys.argv[5], 0o700)
value = Launch(size=152, abi=2, action=1, root=root.root)
for prefix, text in [('production', sys.argv[3]), ('support', sys.argv[4])]:
    identity, device, inode = text.split(':')
    getattr(value, prefix + '_build_id')[:] = bytes.fromhex(identity)
    setattr(value, prefix + '_device', int(device)); setattr(value, prefix + '_inode', int(inode))
before = parent_state()
fd_count = len(os.listdir('/proc/self/fd'))
if sys.argv[6] == 'identity-host-failure': library.srpt_host_fail_identity()
if sys.argv[6] == 'initial_clock_failure': library.srpt_host_initial_clock_failure()
busy_results = {}
if sys.argv[6].startswith('busy'):
    library.srpt_host_arm()
    statuses = []
    caller_states = []
    ready, proceed = threading.Event(), threading.Event()
    def invoke_configuration():
        ready.set(); proceed.wait()
        caller_before = parent_state()
        returned = launch(ctypes.byref(value))
        caller_states.append((caller_before, parent_state()))
        statuses.append(returned)
    worker = threading.Thread(target=invoke_configuration)
    worker.start(); assert ready.wait(5)
    before = parent_state()  # Fixed thread topology before entering native code.
    proceed.set()
    changed_environment = None
    try:
        end = time.monotonic() + 5
        while not library.srpt_host_held():
            assert time.monotonic() < end
            time.sleep(0.001)
        for name, opcode, path in [('release', 2, b''), ('mutation', 5, b'blocked'), ('observe', 3, b'')]:
            call = SupportCall(size=12376, abi=2, opcode=opcode, root=root.root, path=path, mode=0o600)
            busy_results[name] = (fixture(ctypes.byref(call)), call.os_error)
        alias = SupportCall(size=12376, abi=2, opcode=1, path=os.fsencode(sys.argv[5]))
        busy_results['alias'] = (fixture(ctypes.byref(alias)), alias.os_error)
        unrelated = os.path.dirname(sys.argv[5]) + '/unrelated'
        os.mkdir(unrelated, 0o700)
        call = SupportCall(size=12376, abi=2, opcode=1, path=os.fsencode(unrelated))
        assert fixture(ctypes.byref(call)) == 0
        call.opcode = 2
        busy_results['unrelated'] = (fixture(ctypes.byref(call)), call.os_error)
        if sys.argv[6] == 'busy-moved_retained_root':
            busy_results['moved'] = moved_root_probe(b'marker')
            fd_count -= int(busy_results['moved']['release'][0] == 0) + int(busy_results['moved']['fresh_release'][0] == 0)
        if sys.argv[6] == 'busy-path-replace':
            os.rename(sys.argv[5], sys.argv[5] + '-moved'); os.mkdir(sys.argv[5], 0o700)
        if sys.argv[6] == 'busy-pin-change':
            with open(os.path.dirname(os.environ['WINESERVER']) + '/inert-wine64', 'ab') as output:
                output.write(b'changed during acquisition')
        if sys.argv[6] == 'busy-environment-change':
            changed_environment = {name: os.environ[name] for name in ('WINEPREFIX', 'SPACE_WINE_PUBLICATION_TEST_CRYPTO')}
            os.environ['WINEPREFIX'] = '/unvalidated/other-prefix'
            os.environ['SPACE_WINE_PUBLICATION_TEST_CRYPTO'] = 'n'
        time.sleep(0.13)
    finally:
        library.srpt_host_resume()
        worker.join(5)
        if changed_environment is not None: os.environ.update(changed_environment)
    assert not worker.is_alive() and len(statuses) == len(caller_states) == 1
    caller_before, caller_after = caller_states[0]
    assert caller_before[1:] == caller_after[1:]  # Actual caller mask/dispositions/SIGCHLD/cwd/group/umask.
    if changed_environment is None:
        assert caller_before[0] == caller_after[0]
    else:
        expected_during_call = dict(caller_before[0], WINEPREFIX='/unvalidated/other-prefix',
                                   SPACE_WINE_PUBLICATION_TEST_CRYPTO='n')
        assert caller_after[0] == expected_during_call  # The counterexample stays active through native resume.
    status = statuses[0]
else:
    status = launch(ctypes.byref(value))
after = parent_state()
assert before == after
result = dict(status=status, phase=value.phase, error=value.os_error, exit=value.exit_code,
              outcome=value.outcome, remaining=value.remaining_ms)
result['busy'] = busy_results
library.srpt_host_environment.restype = ctypes.c_char_p
values = []
for index in range(32):
    item = library.srpt_host_environment(index)
    if item is None: break
    values.append(os.fsdecode(item))
else: raise AssertionError('unbounded native environment')
result['environment'] = dict(item.split('=', 1) for item in values)
result['retained_fd_delta'] = len(os.listdir('/proc/self/fd')) - fd_count
if sys.argv[6] == 'busy-moved_retained_root' and busy_results['moved']['release'][0] != 0:
    result['after_lease'] = moved_root_after_lease(b'marker')
if sys.argv[6] in ('replay', 'failed-replay', 'initial_clock_failure'):
    result['first_clock_calls'] = library.srpt_host_monotonic_calls()
    if sys.argv[6] == 'failed-replay': os.environ['WINEARCH'] = 'win64'
    value.phase = value.os_error = value.exit_code = value.term_signal = value.outcome = value.remaining_ms = 0
    result['replay'] = launch(ctypes.byref(value))
    result['replay_fd_delta'] = len(os.listdir('/proc/self/fd')) - fd_count
    result['final_clock_calls'] = library.srpt_host_monotonic_calls()
    result['created'] = library.srpt_host_created()
    if sys.argv[6] != 'initial_clock_failure': assert result['replay_fd_delta'] == result['retained_fd_delta']
if sys.argv[6].startswith('run-context-'):
    assert status == 0
    name = 'record-publication-123' if sys.argv[6] != 'run-context-wrong-name' else 'record-publication-x'
    path = sys.argv[5] + '/' + name
    if sys.argv[6] == 'run-context-foreign': path = os.path.dirname(sys.argv[5]) + '/' + name
    os.mkdir(path, 0o700)
    if sys.argv[6] == 'run-context-nested':
        path += '/nested'; os.mkdir(path, 0o700)
    retained = SupportCall(size=12376, abi=2, opcode=1, path=os.fsencode(path))
    assert fixture(ctypes.byref(retained)) == 0
    value.phase = value.os_error = value.exit_code = value.term_signal = value.outcome = value.remaining_ms = 0
    value.action = 2; value.case_id = 2 if sys.argv[6] == 'run-context-skipped' else 1; value.root = retained.root
    # Even malformed-context tests supply an actual copy identity, never a fabricated inode.
    for suffix in ('/control', '/control/modules', '/control/modules/x86_64-unix'):
        os.mkdir(path + suffix, 0o700)
    original = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(sys.argv[2]))))
    copy = path + '/control/modules/x86_64-unix/space_record_publication.so'
    shutil.copyfile(original + '/wine-publication/modules/x86_64-unix/space_record_publication.so', copy)
    copied_info = os.stat(copy)
    value.production_device = copied_info.st_dev; value.production_inode = copied_info.st_ino
    if sys.argv[6] == 'run-context-binding': value.support_inode += 1
    if sys.argv[6] == 'run-context-path-replace':
        os.rename(path, path + '-moved'); os.mkdir(path, 0o700)
    if sys.argv[6] == 'run-context-source-change':
        with open(os.path.dirname(sys.argv[2]) + '/space_record_publication_tests.so', 'ab') as output:
            output.write(b'changed after configure')
    before_run = len(os.listdir('/proc/self/fd'))
    run_status = launch(ctypes.byref(value))
    result['run'] = dict(status=run_status, phase=value.phase, error=value.os_error,
                         outcome=value.outcome, exit=value.exit_code)
    assert len(os.listdir('/proc/self/fd')) == before_run
    value.phase = value.os_error = value.exit_code = value.term_signal = value.outcome = value.remaining_ms = 0
    result['run_replay'] = launch(ctypes.byref(value))
    retained.opcode = 2
    assert fixture(ctypes.byref(retained)) == 0
if sys.argv[6].startswith('prepare-'):
    assert status == 0
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(sys.argv[2]))))
    owned = sys.argv[5] + '/record-publication-123'
    os.mkdir(owned, 0o700)
    retained = SupportCall(size=12376, abi=2, opcode=1, path=os.fsencode(owned))
    assert fixture(ctypes.byref(retained)) == 0
    scenario = sys.argv[6].removeprefix('prepare-')
    def make_case(selected):
        relocate = scenario.startswith('execute-moved_retained_root') and selected == 'control'
        case = staging_path if relocate else owned + '/' + selected
        for directory in ('', '/modules', '/modules/x86_64-windows', '/modules/x86_64-unix'):
            if relocate and directory == '': continue
            os.mkdir(case + directory, 0o700)
        overlay = repo + '/wine/windows'
        production = repo + '/wine-publication/modules'
        pairs = [('test_record_publication.exe', overlay + '/test_record_publication.exe'),
                 ('space_record_publication_tests.dll', overlay + '/space_record_publication_tests.dll'),
                 ('libfixture.dll', overlay + '/libfixture.dll'),
                 ('bcryptprimitives.dll', overlay + '/bcryptprimitives.dll'),
                 ('space_record_publication.dll', production + '/x86_64-windows/space_record_publication.dll'),
                 ('modules/x86_64-windows/space_record_publication.dll', production + '/x86_64-windows/space_record_publication.dll'),
                 ('modules/x86_64-unix/space_record_publication.so', production + '/x86_64-unix/space_record_publication.so')]
        for name, source in pairs:
            shutil.copyfile(source, case + '/' + name); os.chmod(case + '/' + name, 0o600)
        if relocate:
            os.rename(staging_path, owned + '/control'); case = owned + '/control'
            if scenario.endswith('-replaced'): os.mkdir(staging_path, 0o700)
            elif scenario.endswith('-symlink'): os.symlink(case, staging_path, target_is_directory=True)
        copied = os.stat(case + '/modules/x86_64-unix/space_record_publication.so')
        for name in ('space_record_publication.dll', 'modules/x86_64-windows/space_record_publication.dll',
                     'modules/x86_64-unix/space_record_publication.so'):
            if name.endswith('.so') and selected == 'bad-unix' and scenario in ('missing-receipt', 'receipt-after-damage'):
                continue
            relative = os.path.relpath(case + '/' + name, sys.argv[5])
            observer = None
            if scenario == 'receipt-roots':
                base = os.path.dirname(case + '/' + name)
                observer = SupportCall(size=12376, abi=2, opcode=1, path=os.fsencode(base))
                assert fixture(ctypes.byref(observer)) == 0
                relative = os.path.basename(name)
            call = SupportCall(size=12376, abi=2, opcode=3, root=observer.root if observer else root.root,
                               path=os.fsencode(relative))
            assert fixture(ctypes.byref(call)) == 0
            if observer:
                observer.opcode = 2
                assert fixture(ctypes.byref(observer)) == 0
        return case, copied
    def damage(case, selected):
        names = ['modules/x86_64-unix/space_record_publication.so'] if selected.endswith('unix') else [
            'space_record_publication.dll', 'modules/x86_64-windows/space_record_publication.dll']
        if selected == 'control': return
        for name in names:
            data = b'not-an-ELF' if selected.endswith('unix') else b'not-a-PE'
            relative = os.path.relpath(case + '/' + name, sys.argv[5])
            call = SupportCall(size=12376, abi=2, opcode=11 if selected.startswith('missing') else 6,
                               root=root.root, path=os.fsencode(relative), data_size=0 if selected.startswith('missing') else len(data))
            call.data[:len(data)] = data
            if scenario == 'missing-renamed' and selected == 'missing-unix':
                os.rename(case + '/' + name, case + '/renamed-away')
                os.rename(case + '/renamed-away', owned + '/renamed-away')
            else: assert fixture(ctypes.byref(call)) == 0
    target = 5 if scenario in ('missing-receipt', 'receipt-after-damage', 'receipt-replaced', 'wrong-mutation') else (
        4 if scenario == 'missing-renamed' else 2 if scenario in ('changed-fixture', 'alias-fixture', 'wrong-order') else 1)
    stages = []
    base_fds = len(os.listdir('/proc/self/fd'))
    for index, selected in enumerate(('control', 'missing-pe', 'bad-pe', 'missing-unix', 'bad-unix'), 1):
        if index == target and scenario in ('changed-fixture', 'alias-fixture'):
            if scenario == 'changed-fixture':
                owned = sys.argv[5] + '/record-publication-456'; os.mkdir(owned, 0o700)
            retained = SupportCall(size=12376, abi=2, opcode=1, path=os.fsencode(owned))
            assert fixture(ctypes.byref(retained)) == 0
            base_fds += 1  # One deliberately retained extra context, not a preparation descriptor.
        case, copied = make_case(selected)
        damage(case, selected)
        value.phase = value.os_error = value.exit_code = value.term_signal = value.outcome = value.remaining_ms = 0
        value.action = 2; value.case_id = index; value.root = retained.root
        value.production_device = copied.st_dev; value.production_inode = copied.st_ino
        if index == target:
            if scenario == 'copy-bytes':
                with open(case + '/test_record_publication.exe', 'ab') as output: output.write(b'changed')
            elif scenario in ('copy-symlink', 'copy-hardlink'):
                path = case + '/test_record_publication.exe'; os.unlink(path)
                if scenario == 'copy-symlink': os.symlink(repo + '/wine/windows/test_record_publication.exe', path)
                else: os.link(repo + '/wine/windows/test_record_publication.exe', path)
            elif scenario == 'copy-multiple-links':
                os.link(case + '/test_record_publication.exe', owned + '/another-link')
            elif scenario == 'extra-file': open(case + '/untrusted.txt', 'wb').close()
            elif scenario == 'extra-root': os.mkdir(case + '/modules/extra', 0o700)
            elif scenario == 'support-copy': os.unlink(case + '/space_record_publication_tests.dll')
            elif scenario == 'dependency-bytes':
                with open(case + '/libfixture.dll', 'ab') as output: output.write(b'changed')
            elif scenario == 'copy-binding': value.production_inode += 1
            elif scenario == 'production-id': value.production_build_id[0] ^= 1
            elif scenario == 'receipt-after-damage':
                call = SupportCall(size=12376, abi=2, opcode=3, root=root.root,
                    path=os.fsencode('record-publication-123/bad-unix/modules/x86_64-unix/space_record_publication.so'))
                assert fixture(ctypes.byref(call)) == 0
            elif scenario == 'receipt-replaced':
                path = case + '/modules/x86_64-unix/space_record_publication.so'; os.unlink(path)
                with open(path, 'wb') as output: output.write(b'not-an-ELF')
                os.chmod(path, 0o600)
                value.production_inode = os.stat(path).st_ino  # Caller cannot rebind the captured intact-copy proof.
            elif scenario == 'wrong-mutation':
                with open(case + '/modules/x86_64-unix/space_record_publication.so', 'ab') as output: output.write(b'!')
            elif scenario == 'session-replaced':
                cache = os.environ['XDG_CACHE_HOME']; os.rename(cache, cache + '-moved'); os.mkdir(cache, 0o700)
            elif scenario == 'mode': os.chmod(case + '/modules/x86_64-unix', 0o755)
            elif scenario == 'missing-exe': os.unlink(case + '/test_record_publication.exe')
            elif scenario == 'support-root': open(repo + '/wine-publication-tests/modules/x86_64-unix/extra.so', 'wb').close()
            elif scenario == 'wrong-order': value.case_id += 1
            elif scenario == 'no-reserve': library.srpt_host_no_reserve()
            elif scenario == 'allocation-failure': library.srpt_host_fail_allocation()
            elif scenario == 'retained-parent':
                os.rename(sys.argv[5], sys.argv[5] + '-moved'); os.mkdir(sys.argv[5], 0o700)
                call = SupportCall(size=12376, abi=2, opcode=3, root=root.root,
                    path=b'record-publication-123/control/modules/x86_64-unix/space_record_publication.so')
                result['retained_observation'] = dict(status=fixture(ctypes.byref(call)), device=call.device,
                    inode=call.inode, size=call.file_size, bytes=call.data_size)
                result['observed_copy'] = [copied.st_dev, copied.st_ino]
        if scenario == 'control':
            returned, retirement = native_run(value)
            result['prepared'] = dict(status=returned, phase=value.phase, error=value.os_error,
                                      exit=value.exit_code, outcome=value.outcome, remaining=value.remaining_ms,
                                      retirement=retirement)
            assert len(os.listdir('/proc/self/fd')) == base_fds
            value.phase = value.os_error = value.exit_code = value.term_signal = value.outcome = value.remaining_ms = 0
            assert launch(ctypes.byref(value)) == ctypes.c_int32(0xc000000d).value
            break
        if scenario.startswith('execute-fault-') and index == 1:
            getattr(library, 'srpt_host_fault_' + scenario.removeprefix('execute-fault-'))()
        library.srpt_host_prepare.argtypes = [ctypes.c_void_p]
        state_before = parent_state()
        if scenario == 'busy' and index == 1:
            library.srpt_host_arm()
            returned = []
            caller_states = []
            ready, proceed = threading.Event(), threading.Event()
            def invoke_preparation():
                ready.set(); proceed.wait()
                caller_before = parent_state()
                prepared = library.srpt_host_prepare(ctypes.byref(value))
                caller_states.append((caller_before, parent_state()))
                returned.append(prepared)
            worker = threading.Thread(target=invoke_preparation)
            worker.start(); assert ready.wait(5)
            state_before = parent_state()
            proceed.set()
            try:
                until = time.monotonic() + 5
                while not library.srpt_host_held():
                    assert time.monotonic() < until; time.sleep(0.001)
                concurrent = Launch.from_buffer_copy(value)
                concurrent.phase = concurrent.os_error = concurrent.exit_code = concurrent.term_signal = concurrent.outcome = concurrent.remaining_ms = 0
                assert launch(ctypes.byref(concurrent)) == ctypes.c_int32(0xc000000d).value
                for token in (root.root, retained.root):
                    call = SupportCall(size=12376, abi=2, opcode=2, root=token)
                    assert fixture(ctypes.byref(call)) != 0 and call.os_error == 16
                call = SupportCall(size=12376, abi=2, opcode=5, root=retained.root, path=b'blocked', mode=0o600)
                assert fixture(ctypes.byref(call)) != 0 and call.os_error == 16
                call.opcode = 3; call.path = b''
                assert fixture(ctypes.byref(call)) == 0
            finally:
                library.srpt_host_resume(); worker.join(5)
            assert not worker.is_alive() and len(returned) == len(caller_states) == 1
            assert caller_states[0][0] == caller_states[0][1]
            prepared_status = returned[0]
        elif (scenario == 'execute-busy' or scenario.startswith('execute-moved_retained_root')) and index == 1:
            concurrent = Launch.from_buffer_copy(value)
            ready, proceed = threading.Event(), threading.Event()
            returned = []
            def invoke():
                ready.set(); proceed.wait(); returned.append(native_run(value))
            worker = threading.Thread(target=invoke)
            worker.start(); assert ready.wait(5)
            state_before = parent_state()  # Exclude thread creation's libc setup, measure native calls.
            proceed.set()
            child = -1
            try:
                until = time.monotonic() + 5
                while True:
                    child = library.srpt_host_child_pid()
                    stopped = os.waitid(os.P_PID, child, os.WSTOPPED | os.WNOHANG | os.WNOWAIT) if child > 0 else None
                    if stopped and stopped.si_pid == child: break
                    assert time.monotonic() < until; time.sleep(0.001)
                assert stopped.si_code == os.CLD_STOPPED and stopped.si_status == signal.SIGSTOP
                if scenario.startswith('execute-moved_retained_root'):
                    original_bytes = open(case + '/libfixture.dll', 'rb').read()
                    result['moved'] = moved_root_probe(b'libfixture.dll')
                    result['moved']['bytes_unchanged'] = open(case + '/libfixture.dll', 'rb').read() == original_bytes
                    base_fds -= int(result['moved']['release'][0] == 0) + int(result['moved']['fresh_release'][0] == 0)
                    if scenario.endswith('-replaced'):
                        admission = SupportCall(size=12376, abi=2, opcode=1, path=os.fsencode(staging_path))
                        admitted = fixture(ctypes.byref(admission))
                        result['moved']['new_fresh_admission'] = [admitted, admission.os_error]
                        if admitted == 0:
                            used, _ = fixture_request(5, admission.root, b'new-marker', b'fresh-name', 0o600)
                            released, _ = fixture_request(2, admission.root)
                            result['moved']['new_fresh_use'] = used
                            result['moved']['new_fresh_release'] = released
                    if scenario.endswith('-late'):
                        late_path = os.path.dirname(sys.argv[5]) + '/retained-late'
                        os.mkdir(late_path, 0o700)
                        library.srpt_host_arm_retained_admission()
                        admission = SupportCall(size=12376, abi=2, opcode=1, path=os.fsencode(late_path))
                        result['moved']['new_stale_admission'] = [fixture(ctypes.byref(admission)), admission.os_error]
                assert launch(ctypes.byref(concurrent)) == ctypes.c_int32(0xc000000d).value
                for token in (root.root, retained.root):
                    request = SupportCall(size=12376, abi=2, opcode=2, root=token)
                    assert fixture(ctypes.byref(request)) != 0 and request.os_error == 16
                request = SupportCall(size=12376, abi=2, opcode=5, root=retained.root, path=b'blocked', mode=0o600)
                assert fixture(ctypes.byref(request)) != 0 and request.os_error == 16
                request.opcode = 3; request.path = b''
                assert fixture(ctypes.byref(request)) == 0
                alias = SupportCall(size=12376, abi=2, opcode=1, path=os.fsencode(owned))
                assert fixture(ctypes.byref(alias)) != 0 and alias.os_error == 16
            finally:
                if child > 0: os.kill(child, signal.SIGCONT)
                worker.join(5)
            assert not worker.is_alive() and len(returned) == 1
            prepared_status, retirement = returned[0]
        elif scenario.startswith('execute'): prepared_status, retirement = native_run(value)
        else: prepared_status = library.srpt_host_prepare(ctypes.byref(value))
        assert state_before == parent_state()
        stage = dict(status=prepared_status, phase=value.phase, error=value.os_error, exit=value.exit_code,
                     outcome=value.outcome, signal=value.term_signal)
        if scenario.startswith('execute'): stage['retirement'] = retirement
        stages.append(stage)
        if prepared_status != 0:
            stage['fd_delta'] = len(os.listdir('/proc/self/fd')) - base_fds
            if scenario == 'allocation-failure':
                value.phase = value.os_error = value.exit_code = value.term_signal = value.outcome = value.remaining_ms = 0
                result['after_failure'] = library.srpt_host_prepare(ctypes.byref(value))
                if result['after_failure'] == 0: assert library.srpt_host_complete() == 0
            elif value.outcome == 5:
                assert stage['fd_delta'] > 0 and os.path.isdir(owned)
                for token in (root.root, retained.root):
                    call = SupportCall(size=12376, abi=2, opcode=2, root=token)
                    assert fixture(ctypes.byref(call)) != 0 and call.os_error == 16
                call = SupportCall(size=12376, abi=2, opcode=5, root=retained.root, path=b'blocked', mode=0o600)
                assert fixture(ctypes.byref(call)) != 0 and call.os_error == 16
            else: assert stage['fd_delta'] == 0
            if scenario.startswith('execute'):
                value.phase = value.os_error = value.exit_code = value.term_signal = value.outcome = value.remaining_ms = 0
                result['after_failure'] = launch(ctypes.byref(value))
            break
        if scenario.startswith('execute'):
            assert len(os.listdir('/proc/self/fd')) == base_fds
            if scenario.startswith('execute-moved_retained_root') and index == 1 and result['moved']['release'][0] != 0:
                result['after_lease'] = moved_root_after_lease(b'libfixture.dll')
                base_fds -= int(result['after_lease']['release'][0] == 0)
            continue
        def texts(name):
            function = getattr(library, name); function.restype = ctypes.c_char_p
            output = []
            for item in range(32):
                text = function(item)
                if text is None: return output
                output.append(os.fsdecode(text))
            raise AssertionError('bounded prepared text')
        stage['arguments'] = texts('srpt_host_argument')
        stage['environment'] = dict(item.split('=', 1) for item in texts('srpt_host_prepared_environment'))
        cwd = library.srpt_host_cwd()
        assert fcntl.fcntl(cwd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC
        assert (os.fstat(cwd).st_dev, os.fstat(cwd).st_ino) == (os.stat(case).st_dev, os.stat(case).st_ino)
        assert library.srpt_host_complete() == 0  # Internal PREPARATION protocol only; no child was executed.
        assert len(os.listdir('/proc/self/fd')) == base_fds
    if len(stages) == 5 and stages[-1]['status'] == 0:
        value.phase = value.os_error = value.exit_code = value.term_signal = value.outcome = value.remaining_ms = 0
        result['after_end'] = launch(ctypes.byref(value)) if scenario.startswith('execute') else library.srpt_host_prepare(ctypes.byref(value))
        assert len(os.listdir('/proc/self/fd')) == base_fds
    result['stages'] = stages
    result['spawn_count'] = library.srpt_host_spawn_count()
    result['kill_count'] = library.srpt_host_kill_count()
    result['zeroed_info'] = library.srpt_host_zeroed()
    result['anchored_kills'] = library.srpt_host_anchor()
    result['observation_preserved'] = library.srpt_host_observation_preserved()
    result['native_reaps'] = library.srpt_host_native_reaps()
    result['created'] = library.srpt_host_created()
    result['backstop_kills'] = library.srpt_host_backstop_kills()
    result['backstop_reaps'] = library.srpt_host_backstop_reaps()
    library.srpt_host_clock_field.restype = ctypes.c_int64
    result['clock_history'] = [[library.srpt_host_clock_field(row, field) for field in range(3)]
                               for row in range(library.srpt_host_clock_rows())]
    result['clock_overflow'] = library.srpt_host_clock_overflowed()
print(json.dumps(result))
'''


def run_support_configuration(fixture, *, env=None, mode='normal'):
    result = subprocess.run([sys.executable, '-c', SUPPORT_CONFIG_DRIVER, str(ROOT / 'scripts/tests'),
                             str(fixture.library), fixture.production_binding, fixture.support_binding,
                             str(fixture.session / 'tmp'), mode], env=env or fixture.env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    lines = result.stdout.splitlines()
    decoded = json.loads(lines[-1])
    assert all(line.startswith('SRPT_NATIVE_CHILD ') for line in lines[:-1]), lines[:-1]
    decoded['child_lines'] = lines[:-1]
    observed = decoded.get('stages', []) + ([decoded['prepared']] if 'prepared' in decoded else [])
    for stage in observed:
        snapshot = stage.get('retirement')
        if not snapshot: continue
        if stage['outcome'] == 5:
            assert snapshot['evidence_held'] and snapshot['fd_delta'] > 0 and snapshot['fixture_exists']
        elif snapshot['created']:
            assert snapshot['native_reaps'] == snapshot['created'] == 1
            assert snapshot['native_reaped'] and snapshot['kernel_echild'], snapshot
        else:
            assert snapshot['native_reaps'] == 0
    if observed and all(stage.get('outcome') != 5 for stage in observed):
        assert decoded['backstop_reaps'] == decoded['backstop_kills'] == 0
    return decoded


@pytest.mark.parametrize('crypto', ['b', 'n'])
def test_support_native_configure_accepts_closed_native_inputs(support_native_configuration, crypto):
    fixture = support_native_configuration
    env = dict(fixture.env, SPACE_WINE_PUBLICATION_TEST_CRYPTO=crypto, LD_UNRELATED='not-admitted',
               WINE_UNRELATED='not-admitted', SPACE_WINE_APPLICATION_OBSERVER_FD='999')
    result = run_support_configuration(fixture, env=env, mode='replay')
    assert result['status'] == 0, result
    assert result['phase'] == 9 and result['outcome'] == 1 and result['exit'] == 0xffffffff
    assert 0 < result['remaining'] <= 60000 and result['error'] == 0
    assert result['replay'] == ctypes.c_int32(0xc000000d).value
    optional = {'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'DISPLAY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR'}
    required = {'WINEPREFIX', 'WINEARCH', 'WINESERVER', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'TMPDIR',
                'TEMP', 'TMP', 'SPACE_WINE_WINDOWS_TMP', 'SPACE_WINE_PUBLICATION_TEST_CRYPTO'}
    expected = {key: env[key] for key in required | (optional & env.keys())}
    expected.update(PATH='', WINEDLLOVERRIDES='space_record_publication=b;space_record_publication_tests=b;'
                    f'bcryptprimitives={crypto};advapi32,cryptbase=b')
    assert result['environment'] == expected  # RUN adds only its fixed roots/bindings later.
    assert result['retained_fd_delta'] == 10  # TEMP+Wine/server and seven retained originals, not leaked parents.


@pytest.mark.parametrize('key,value', [('WINEARCH', 'win32'), ('WINESERVER', '/wrong/server'),
    ('TMPDIR', '/wrong/tmp'), ('XDG_DATA_HOME', '/wrong/data'), ('XDG_CACHE_HOME', '/wrong/cache'),
    ('WINEPREFIX', '/wrong/prefix'), ('TEMP', 'Q:\\wrong'), ('TMP', 'Q:\\wrong'),
    ('SPACE_WINE_WINDOWS_TMP', 'relative'), ('SPACE_WINE_PUBLICATION_TEST_CRYPTO', 'builtin'),
    ('SPACE_WINE_PUBLICATION_TEST_CRYPTO', ''), ('HOME', 'relative'), ('XDG_RUNTIME_DIR', '/missing/runtime'),
    ('LANG', 'x' * 4096), ('SPACE_WINE_PUBLICATION_BINDING', 'invalid'),
    ('SPACE_WINE_PUBLICATION_TEST_BINDING', 'invalid')])
def test_support_native_configure_rejects_wrong_native_inputs(support_native_configuration, key, value):
    fixture = support_native_configuration
    result = run_support_configuration(fixture, env=dict(fixture.env, **{key: value}))
    assert result['status'] != 0 and result['outcome'] == 4 and result['exit'] == 0xffffffff, result
    assert result['retained_fd_delta'] == 0


@pytest.mark.parametrize('name', ['WINEPREFIX', 'WINEARCH', 'WINESERVER', 'XDG_DATA_HOME', 'XDG_CACHE_HOME',
    'TMPDIR', 'TEMP', 'TMP', 'SPACE_WINE_WINDOWS_TMP', 'SPACE_WINE_PUBLICATION_BINDING',
    'SPACE_WINE_PUBLICATION_TEST_BINDING', 'SPACE_WINE_PUBLICATION_TEST_CRYPTO'])
def test_support_native_configure_requires_every_closed_input(support_native_configuration, name):
    fixture = support_native_configuration
    env = dict(fixture.env); del env[name]
    result = run_support_configuration(fixture, env=env)
    assert result['status'] == ctypes.c_int32(0xc000000d).value and result['outcome'] == 4
    assert result['exit'] == 0xffffffff and result['retained_fd_delta'] == 0


def test_support_native_configure_failed_attempt_cannot_reset(support_native_configuration):
    fixture = support_native_configuration
    result = run_support_configuration(fixture, env=dict(fixture.env, WINEARCH='win32'), mode='failed-replay')
    assert result['status'] == result['replay'] == ctypes.c_int32(0xc000000d).value
    assert result['retained_fd_delta'] == 0


def test_support_native_configure_initial_clock_failure_consumes_attempt(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='initial_clock_failure')
    assert result['status'] == ctypes.c_int32(0xc0000001).value and result['error'] == 5 and result['outcome'] == 4
    assert result['exit'] == 0xffffffff and result['remaining'] == 0 and result['first_clock_calls'] == 1
    assert result['replay'] == ctypes.c_int32(0xc000000d).value
    assert result['final_clock_calls'] == 1 and result['retained_fd_delta'] == result['replay_fd_delta'] == 0
    assert result['environment'] == {} and result['created'] == 0


def assert_moved_retained_root_protected(result):
    failure = [ctypes.c_int32(0xc0000001).value, 16]
    assert result['write'] == result['release'] == failure
    assert result['fresh_write'] == result['fresh_read'] == result['fresh_release'] == [0, 0]
    assert result['fresh_match']


def assert_moved_root_usable_after_lease(result):
    assert result['write'] == result['observe'] == result['release'] == [0, 0]
    assert result['bytes_match']


def test_support_native_configure_moved_retained_root_is_protected(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='busy-moved_retained_root')
    assert result['status'] == 0
    assert_moved_retained_root_protected(result['busy']['moved'])
    assert_moved_root_usable_after_lease(result['after_lease'])


@pytest.mark.parametrize('witness', ['missing', 'replaced', 'symlink', 'late'])
@pytest.mark.parametrize('support_native_configuration', ['paused'], indirect=True)
def test_support_native_launch_moved_retained_root_is_protected(support_native_configuration, witness):
    result = run_support_configuration(support_native_configuration, mode='prepare-execute-moved_retained_root-' + witness)
    assert_moved_retained_root_protected(result['moved'])
    assert result['moved']['bytes_unchanged']
    assert_moved_root_usable_after_lease(result['after_lease'])
    assert len(result['stages']) == 5 and all(stage['status'] == 0 for stage in result['stages'])
    assert result['created'] == result['native_reaps'] == 5
    assert result['backstop_reaps'] == result['backstop_kills'] == 0
    if witness == 'replaced':
        assert result['moved']['new_fresh_admission'] == result['moved']['new_fresh_use'] == result['moved']['new_fresh_release'] == [0, 0]
    if witness == 'late': assert result['moved']['new_stale_admission'] == [ctypes.c_int32(0xc0000001).value, 16]


def test_support_native_configure_identity_io_failure_is_host_failure(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='identity-host-failure')
    assert result['status'] == ctypes.c_int32(0xc0000001).value and result['outcome'] == 4
    assert result['exit'] == 0xffffffff and result['retained_fd_delta'] == 0


def test_support_native_configure_busy_contexts_and_deadline(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='busy')
    assert result['status'] == 0 and 0 < result['remaining'] <= 59870, result
    for name in ('release', 'mutation', 'alias'):
        assert result['busy'][name] == [ctypes.c_int32(0xc0000001).value, 16]
    assert result['busy']['observe'] == result['busy']['unrelated'] == [0, 0]
    assert result['retained_fd_delta'] == 10


def test_support_native_configure_captures_one_validated_environment_snapshot(support_native_configuration):
    fixture = support_native_configuration
    result = run_support_configuration(fixture, mode='busy-environment-change')
    assert result['status'] == 0, result
    assert result['environment']['WINEPREFIX'] == fixture.env['WINEPREFIX']
    assert result['environment']['SPACE_WINE_PUBLICATION_TEST_CRYPTO'] == 'b'
    assert 'bcryptprimitives=b;' in result['environment']['WINEDLLOVERRIDES']


def test_support_native_configure_revalidates_retained_temp_path(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='path-replace')
    assert result['status'] == ctypes.c_int32(0xc000007b).value and result['outcome'] == 4
    assert result['retained_fd_delta'] == 0


@pytest.mark.parametrize('mode', ['busy-path-replace', 'busy-pin-change'])
def test_support_native_configure_rechecks_after_acquisition(support_native_configuration, mode):
    result = run_support_configuration(support_native_configuration, mode=mode)
    assert result['status'] == ctypes.c_int32(0xc000007b).value and result['outcome'] == 4, result
    assert result['exit'] == 0xffffffff and result['retained_fd_delta'] == 0


@pytest.mark.parametrize('damage', ['wine-bytes', 'server-bytes', 'wine-mode', 'runtime-ancestor-mode',
    'support-binding-actual-so', 'production-binding-source', 'source-symlink', 'source-hardlink',
    'discovery-bytes', 'support-extra', 'production-extra', 'windows-dotdot', 'windows-control'])
def test_support_native_configure_rejects_pins_bindings_and_original_layout(support_native_configuration, damage):
    fixture = support_native_configuration
    directory = Path(os.fsdecode(bytes.fromhex(fixture.metadata['implementation']['path_hex']))).parent
    env = dict(fixture.env)
    if damage in ('wine-bytes', 'server-bytes'):
        path = directory / ('inert-wine64' if damage == 'wine-bytes' else 'inert-wineserver')
        path.write_bytes(path.read_bytes() + b'changed')
    elif damage == 'wine-mode': (directory / 'inert-wine64').chmod(0o700)
    elif damage == 'runtime-ancestor-mode': directory.chmod(0o755)
    elif damage == 'support-binding-actual-so':
        fixture.support_binding = fixture.support_binding.split(':')[0] + ':' + fixture.production_binding.split(':', 1)[1]
        env['SPACE_WINE_PUBLICATION_TEST_BINDING'] = fixture.support_binding
    elif damage == 'production-binding-source':
        fixture.production_binding = fixture.production_binding.split(':')[0] + ':' + fixture.support_binding.split(':', 1)[1]
        env['SPACE_WINE_PUBLICATION_BINDING'] = fixture.production_binding
    elif damage in ('source-symlink', 'source-hardlink'):
        source = fixture.repo / 'build/wine-publication/modules/x86_64-windows/space_record_publication.dll'
        saved = source.with_suffix('.saved')
        source.rename(saved)
        if damage == 'source-symlink': source.symlink_to(saved)
        else: os.link(saved, source)
    elif damage == 'discovery-bytes':
        path = fixture.repo / 'build/wine/windows/space_record_publication.dll'
        path.write_bytes(path.read_bytes() + b'changed')
    elif damage in ('support-extra', 'production-extra'):
        root = 'wine-publication-tests' if damage == 'support-extra' else 'wine-publication'
        (fixture.repo / f'build/{root}/modules/x86_64-unix/extra.so').write_bytes(b'unadmitted')
    else:
        value = 'Q:\\owned\\..\\tmp' if damage == 'windows-dotdot' else 'Q:\\owned\\\x01tmp'
        env.update(TEMP=value, TMP=value, SPACE_WINE_WINDOWS_TMP=value)
    result = run_support_configuration(fixture, env=env)
    assert result['status'] != 0 and result['outcome'] == 4 and result['exit'] == 0xffffffff, result
    assert result['retained_fd_delta'] == 0


@pytest.mark.parametrize('mode', ['wrong-name', 'foreign', 'nested', 'skipped', 'binding', 'path-replace', 'source-change'])
def test_support_native_run_context_refuses_bad_roots_bindings_and_replay(support_native_configuration, mode):
    result = run_support_configuration(support_native_configuration, mode='run-context-' + mode)
    run = result['run']
    assert run['status'] != 0 and run['error'] != 38, run  # Refuse the bad context before the WIP layout boundary.
    assert run['outcome'] == 4 and run['exit'] == 0xffffffff
    assert result['run_replay'] == ctypes.c_int32(0xc000000d).value


def test_support_native_launch_control_runs_checked_inert_child(support_native_configuration):
    prepared = run_support_configuration(support_native_configuration, mode='prepare-control')['prepared']
    assert prepared['status'] == 0 and prepared['error'] == 0
    assert prepared['phase'] == 9 and prepared['outcome'] == 1 and prepared['exit'] == 0
    assert prepared['remaining'] >= 13000


@pytest.mark.parametrize('crypto', ['b', 'n'])
def test_support_native_launch_actual_five_case_children_and_parent_isolation(support_native_configuration, crypto):
    fixture = support_native_configuration
    result = run_support_configuration(fixture, env=dict(fixture.env, SPACE_WINE_PUBLICATION_TEST_CRYPTO=crypto,
        LD_TEST_INPUT='not-inherited', WINE_TEST_INPUT='not-inherited', SPACE_WINE_APPLICATION_OBSERVER_FD='999'),
        mode='prepare-execute')
    assert len(result['stages']) == 5
    assert all(stage['status'] == 0 and stage['exit'] == 0 and stage['signal'] == 0
               and stage['outcome'] == 1 and stage['phase'] == 9 for stage in result['stages'])
    assert result['child_lines'] == ['SRPT_NATIVE_CHILD ' + name for name in ('control', 'missing-pe', 'bad-pe', 'missing-unix', 'bad-unix')]
    assert result['after_end'] == ctypes.c_int32(0xc000000d).value
    assert result['spawn_count'] == 5 and result['kill_count'] == 0
    assert result['zeroed_info'] and result['observation_preserved']


@pytest.mark.parametrize('support_native_configuration', ['nonzero', 'signal', 'timeout'], indirect=True)
def test_support_native_launch_actual_child_failures_are_retired_and_terminal(support_native_configuration):
    fixture = support_native_configuration
    started = __import__('time').monotonic()
    result = run_support_configuration(fixture, mode='prepare-execute')
    elapsed = __import__('time').monotonic() - started
    assert len(result['stages']) == 1
    stage = result['stages'][0]
    assert stage['status'] == ctypes.c_int32(0xc0000001).value
    assert stage['outcome'] == (3 if fixture.behavior == 'timeout' else 2)
    assert stage['exit'] == (23 if fixture.behavior == 'nonzero' else 0xffffffff)
    assert stage['signal'] == (signal.SIGUSR1 if fixture.behavior == 'signal' else signal.SIGKILL if fixture.behavior == 'timeout' else 0)
    assert result['after_failure'] == ctypes.c_int32(0xc000000d).value
    assert result['child_lines'] == ['SRPT_NATIVE_CHILD control']
    if fixture.behavior == 'timeout': assert 9 <= elapsed < 14


def test_support_native_launch_refuses_ignored_sigchld_without_parent_mutation(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='prepare-execute-ignore')
    assert result['stages'][0]['status'] == ctypes.c_int32(0xc0000001).value
    assert result['stages'][0]['outcome'] == 4 and result['stages'][0]['error'] == 10
    assert not result['child_lines']


def test_support_native_launch_refuses_no_cldwait_without_parent_mutation(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='prepare-execute-no_cldwait')
    assert result['stages'][0]['status'] == ctypes.c_int32(0xc0000001).value
    assert result['stages'][0]['outcome'] == 4 and result['spawn_count'] == 0 and not result['child_lines']


@pytest.mark.parametrize('fault', ['action_init', 'attr_init', 'action_open', 'action_cwd', 'action_closefrom',
    'attr_mask', 'attr_default', 'attr_group', 'flags', 'reserve', 'spawn'])
def test_support_native_launch_checks_pre_spawn_failures_without_retry(support_native_configuration, fault):
    result = run_support_configuration(support_native_configuration, mode='prepare-execute-fault-' + fault)
    stage = result['stages'][0]
    assert len(result['stages']) == 1 and stage['status'] == ctypes.c_int32(0xc0000001).value
    assert stage['outcome'] == 4 and stage['exit'] == 0xffffffff and stage['signal'] == 0
    assert result['spawn_count'] == (1 if fault == 'spawn' else 0) and result['kill_count'] == 0
    assert not result['child_lines'] and result['after_failure'] == ctypes.c_int32(0xc000000d).value


@pytest.mark.parametrize('fault', ['action_destroy', 'attr_destroy', 'post_pin', 'post_alloc', 'clock', 'close_spawn', 'close_reap'])
def test_support_native_launch_post_spawn_errors_retire_exact_leader(support_native_configuration, fault):
    result = run_support_configuration(support_native_configuration, mode='prepare-execute-fault-' + fault)
    stage = result['stages'][0]
    assert len(result['stages']) == 1 and stage['status'] != 0 and stage['outcome'] == 4
    assert result['spawn_count'] == 1 and result['kill_count'] == (0 if fault == 'close_reap' else 1)
    assert result['anchored_kills'] and result['zeroed_info']
    assert result['after_failure'] == ctypes.c_int32(0xc000000d).value


@pytest.mark.parametrize('fault', ['waitid_wrong', 'waitid_badcode', 'waitid_badstatus', 'waitid_echild',
                                  'waitpid_echild', 'waitpid_late', 'kill', 'partial_spawn', 'reaper'])
def test_support_native_launch_uncertain_ownership_preserves_busy_evidence(support_native_configuration, fault):
    result = run_support_configuration(support_native_configuration, mode='prepare-execute-fault-' + fault)
    stage = result['stages'][0]
    assert len(result['stages']) == 1 and stage['status'] == ctypes.c_int32(0xc0000001).value
    assert stage['outcome'] == 5 and stage['fd_delta'] > 0
    assert result['spawn_count'] == 1 and result['kill_count'] == (1 if fault == 'kill' else 0)
    assert result['anchored_kills'] and result['after_failure'] == ctypes.c_int32(0xc000000d).value


def test_support_native_launch_refuses_pre_spawn_pin_replacement(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='prepare-execute-fault-pre_pin')
    assert result['stages'][0]['status'] == ctypes.c_int32(0xc000007b).value
    assert result['stages'][0]['outcome'] == 4 and result['spawn_count'] == result['created'] == 0
    assert not result['child_lines']


@pytest.mark.parametrize('support_native_configuration', ['paused'], indirect=True)
def test_support_native_launch_wait_keeps_context_busy_without_registry_lock(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='prepare-execute-busy')
    assert len(result['stages']) == 5 and all(stage['status'] == 0 for stage in result['stages'])
    assert result['native_reaps'] == result['created'] == 5
    assert result['backstop_reaps'] == result['backstop_kills'] == result['kill_count'] == 0


@pytest.mark.parametrize('fault', ['waitid_eintr', 'waitpid_eintr'])
def test_support_native_launch_eintr_preserves_absolute_wait_and_reap(support_native_configuration, fault):
    result = run_support_configuration(support_native_configuration, mode='prepare-execute-fault-' + fault)
    assert len(result['stages']) == 5 and all(stage['status'] == 0 for stage in result['stages'])
    assert result['spawn_count'] == 5 and result['kill_count'] == 0 and result['observation_preserved']


def test_support_native_launch_interrupted_wait_does_not_restart_budget(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='prepare-execute-fault-waitid_late')
    assert len(result['stages']) == 1 and result['stages'][0]['outcome'] == 3
    assert result['spawn_count'] == 1 and result['kill_count'] == 1 and result['anchored_kills']
    assert not result['clock_overflow']
    history = result['clock_history']
    origin = next(row for row in history if row[0] == 0)
    interrupt = next(index for index, row in enumerate(history) if row[0] == 2)
    late = next(row[1] for row in history[interrupt + 1:] if row[0] == 1)
    assert late > origin[1] + 10_000_000_000
    sleeps = [row for row in history if row[0] == 3]
    assert sleeps and all(row[1] - row[2] == 48_000_000_000 for row in sleeps)
    retired = [row[1] for row in history if row[0] == 5]
    assert len(retired) == 1 and late <= retired[0] <= late + 2_000_000_000
    assert retired[0] <= origin[2] - 1_000_000_000
    assert result['stages'][0]['retirement']['seconds'] < 3


@pytest.mark.parametrize('crypto', ['b', 'n'])
def test_support_native_preparation_sequence_closed_argv_env_and_receipts(support_native_configuration, crypto):
    fixture = support_native_configuration
    env = dict(fixture.env, SPACE_WINE_PUBLICATION_TEST_CRYPTO=crypto, PATH='/not-inherited',
               WINEDLLPATH='/not-inherited', WINEDLLOVERRIDES='not-inherited', LD_TEST_INPUT='not-inherited',
               WINE_TEST_INPUT='not-inherited', SPACE_WINE_APPLICATION_OBSERVER_FD='999')
    result = run_support_configuration(fixture, env=env, mode='prepare-sequence')
    assert len(result['stages']) == 5
    assert result['after_end'] == ctypes.c_int32(0xc000000d).value
    for selected, stage in zip(('control', 'missing-pe', 'bad-pe', 'missing-unix', 'bad-unix'), result['stages']):
        assert stage['status'] == 0 and stage['phase'] == 4 and stage['exit'] == 0xffffffff
        case = str(fixture.session / 'tmp/record-publication-123' / selected)
        assert stage['arguments'] == [str(fixture.session.parents[4] / 'inert-wine64'),
                                       case + '/test_record_publication.exe', '--wine-publication-child=' + selected]
        expected = dict(result['environment'], WINEDLLPATH=case + '/modules:' + str(fixture.repo / 'build/wine-publication-tests/modules'),
                        SPACE_WINE_PUBLICATION_TEST_BINDING=fixture.support_binding)
        copied = os.stat(Path(case) / 'modules/x86_64-unix/space_record_publication.so') if selected != 'missing-unix' else None
        binding = stage['environment']['SPACE_WINE_PUBLICATION_BINDING']
        identity, device, inode = binding.split(':')
        assert identity == fixture.production_binding.split(':')[0] and binding != fixture.production_binding
        if copied: assert (int(device), int(inode)) == (copied.st_dev, copied.st_ino)
        expected['SPACE_WINE_PUBLICATION_BINDING'] = binding
        assert stage['environment'] == expected


@pytest.mark.parametrize('damage', ['copy-bytes', 'copy-symlink', 'copy-hardlink', 'copy-multiple-links', 'extra-file', 'extra-root',
    'support-copy', 'dependency-bytes', 'copy-binding', 'production-id', 'missing-receipt', 'receipt-after-damage',
    'receipt-replaced', 'wrong-mutation', 'missing-renamed', 'session-replaced', 'mode', 'missing-exe', 'support-root',
    'changed-fixture', 'alias-fixture', 'wrong-order', 'no-reserve'])
def test_support_native_preparation_refuses_layout_mutation_and_unproved_binding(support_native_configuration, damage):
    result = run_support_configuration(support_native_configuration, mode='prepare-' + damage)
    expected = 5 if damage in ('missing-receipt', 'receipt-after-damage', 'receipt-replaced', 'wrong-mutation') else (
        4 if damage == 'missing-renamed' else 2 if damage in ('changed-fixture', 'alias-fixture', 'wrong-order') else 1)
    assert len(result['stages']) == expected and all(stage['status'] == 0 for stage in result['stages'][:-1])
    assert result['stages'][-1]['status'] != 0 and result['stages'][-1]['error'] != 38, result['stages']
    assert result['stages'][-1]['exit'] == 0xffffffff


def test_support_native_preparation_busy_context_survives_rejected_concurrent_run(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='prepare-busy')
    assert len(result['stages']) == 5 and all(stage['status'] == 0 for stage in result['stages'])


def test_support_native_preparation_allocation_failure_is_terminal_and_releases_proofs(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='prepare-allocation-failure')
    assert result['stages'][0]['status'] == ctypes.c_int32(0xc0000001).value
    assert result['stages'][0]['fd_delta'] == 0
    assert result['after_failure'] == ctypes.c_int32(0xc000000d).value


def test_support_native_preparation_receipts_preserve_retained_parent_observe(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='prepare-retained-parent')
    observed = result['retained_observation']
    assert observed['status'] == 0 and [observed['device'], observed['inode']] == result['observed_copy']
    assert observed['size'] > 0 and observed['bytes'] > 0
    assert result['stages'][-1]['status'] != 0  # Launch still refuses the replaced acquisition path.


def test_support_native_preparation_receipts_accept_retained_case_and_architecture_roots(support_native_configuration):
    result = run_support_configuration(support_native_configuration, mode='prepare-receipt-roots')
    assert len(result['stages']) == 5 and all(stage['status'] == 0 for stage in result['stages'])
    assert result['after_end'] == ctypes.c_int32(0xc000000d).value


def test_support_real_elf_bounded_reads_cover_multichunk_content(support_elf, tmp_path):
    operate = support_elf[3]
    payload = bytes(range(256)) * 300
    (tmp_path / 'multichunk').write_bytes(payload)
    root = support_ok(operate, 1, path=str(tmp_path)).root
    try:
        observed = bytearray()
        for offset in range(0, len(payload), 4096):
            value = support_ok(operate, 3, root=root, path='multichunk', offset=offset)
            assert value.file_size == len(payload)
            assert value.data_size == min(4096, len(payload) - offset)
            observed.extend(value.data[:value.data_size])
        assert observed == payload
        assert support_ok(operate, 3, root=root, path='multichunk', offset=len(payload)).data_size == 0
        assert support_call(operate, 3, root=root, path='multichunk', offset=len(payload) + 1)[0] != 0
    finally:
        support_ok(operate, 2, root=root)


def support_compiler_launch_metadata(repo):
    """Baked inert records for synthetic compiler output, never runtime admission."""
    def pin(name):
        return dict(path_hex=os.fsencode('/inert-compiler-model/' + name).hex(), sha256='12' * 32,
                    device=1, inode=2, size=64, uid=0, mode=0o100755, mtime_ns=3, ctime_ns=4,
                    ancestors=[dict(path_hex='2f', device=1, inode=1, uid=0, mode=0o40755)])
    return dict(schema=1, checkout_path_hex=os.fsencode(repo).hex(),
                implementation=pin('wine64'), server=pin('wineserver'))


@pytest.fixture
def support_builder_fixture(publication_fixture, monkeypatch):
    fixture, session = publication_fixture
    # Support-aware API/main tests supply extra inputs; production-only API
    # checkouts remain independently valid without these files.
    for relative in SUPPORT_INPUTS:
        target = fixture.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    for command in ['g++', 'x86_64-w64-mingw32-gcc-posix']:
        path = fixture.bin / command
        path.write_text(path.read_text().replace("a.startswith('-DSRP_BUILD_ID_BYTES=')",
                                                 "a.startswith(('-DSRP_BUILD_ID_BYTES=', '-DSRPT_BUILD_ID_BYTES='))"))
    fixture.launch_metadata = support_compiler_launch_metadata(fixture.root)
    monkeypatch.setattr(builder_module(), '_capture_launch_metadata',
                        lambda *args: json.loads(json.dumps(fixture.launch_metadata)), raising=False)
    return fixture, session


def test_support_builder_is_independent_dormant_and_seals_discovery(support_builder_fixture):
    fixture, session = support_builder_fixture
    module = builder_module()
    assert hasattr(module, 'build_test_support'), 'independent test support builder is missing'
    production = module.build_publication(fixture.root, session)
    manifest = module.build_test_support(fixture.root, session)
    assert set(manifest['toolchain']['inputs']) == set(SUPPORT_INPUTS)
    assert manifest['kind'] == 'record-publication-test-support'
    assert manifest['build_id'] != production['build_id']
    assert manifest['runtime'] == production['runtime'] and manifest['abi'] == 2
    assert production['abi'] == 1
    assert set(manifest['files']) == {*SUPPORT_PAIR, SUPPORT_COPY}
    output = fixture.root / 'build/wine-publication-tests'
    assert json.loads((output / 'build.json').read_text()) == manifest
    assert (output / SUPPORT_COPY).read_bytes() == (output / SUPPORT_PAIR[0]).read_bytes()
    assert manifest['files'][SUPPORT_COPY] == manifest['files'][SUPPORT_PAIR[0]]
    assert module.build_test_support(fixture.root, session) == manifest
    assert module.build_publication(fixture.root, session) == production
    commands = [call for call in fixture.calls() if '-o' in call]
    support = [call for call in commands if any('SRPT_BUILD_ID_BYTES=' in arg for arg in call)]
    assert len(support) == 4
    assert all(str(fixture.root / PUBLICATION_SOURCE) not in call for call in support)
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable')]


@pytest.mark.parametrize('relative', SUPPORT_INPUTS)
def test_support_builder_pins_every_input(support_builder_fixture, relative):
    fixture, session = support_builder_fixture
    module = builder_module()
    assert hasattr(module, 'build_test_support'), 'independent test support builder is missing'
    first = module.build_test_support(fixture.root, session)
    path = fixture.root / relative
    path.write_bytes(path.read_bytes() + b'\n/* identity change */\n')
    assert module.build_test_support(fixture.root, session)['build_id'] != first['build_id']


def test_support_active_build_id_uses_abi2():
    module = builder_module()
    runtime, toolchain = {'runtime': 'inert'}, {'inputs': {}}
    expected = dict(kind='record-publication-test-support', abi=2, runtime=runtime, toolchain=toolchain)
    assert module._test_build_id(runtime, toolchain) == hashlib.sha256(
        json.dumps(expected, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@pytest.fixture
def retired_support_output(support_builder_fixture):
    """Exactly inventoried synthetic ABI1, using the historical ID calculation.

    No retired source is compiled/executed. These compiler-protocol artifacts
    embed the ID in the final 32 bytes, as in the existing synthetic fixtures.
    """
    fixture, session = support_builder_fixture
    module = builder_module()
    manifest = module.build_test_support(fixture.root, session)
    output = fixture.root / 'build/wine-publication-tests'
    manifest['abi'] = 1
    for relative in ('src/record_publication_wine_binding.h', 'src/record_publication_wine_abi.h'):
        manifest['toolchain']['inputs'].pop(relative, None)
    original = dict(kind=module.TEST_KIND, abi=1, runtime=manifest['runtime'], toolchain=manifest['toolchain'])
    manifest['build_id'] = hashlib.sha256(json.dumps(original, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    for relative in (*SUPPORT_PAIR, SUPPORT_COPY):
        path = output / relative
        path.write_bytes(path.read_bytes()[:-32] + bytes.fromhex(manifest['build_id']))
    manifest['files'] = module._test_inventory(output, manifest['build_id'])
    module.prefix.write_control(output / 'build.json', manifest)
    return fixture, session, output, manifest


def test_support_retired_abi1_replacement_only_never_active(retired_support_output):
    fixture, session, output, retired = retired_support_output
    module = builder_module()
    with pytest.raises(ValueError, match='manifest'):
        module._recognized_test_output(output)
    assert module._recognized_test_output(output, for_replacement=True)[1] == retired
    from wine import artifacts
    with pytest.raises(ValueError, match='manifest'):
        artifacts.support_manifest(session)
    replacement = module.build_test_support(fixture.root, session)
    assert replacement['abi'] == 2 and replacement['build_id'] != retired['build_id']
    assert module._recognized_test_output(output)[1] == replacement
    assert module._recognized_test_output(output, for_replacement=True)[1] == replacement
    assert not list((fixture.root / 'build').glob('.wine-publication-tests-*'))


@pytest.mark.parametrize('damage', ['abi-bool', 'abi3', 'new-id', 'build-id', 'runtime', 'toolchain',
                                  'inventory', 'copy', 'so', 'extra', 'missing', 'symlink', 'hardlink',
                                  'file-mode', 'directory-mode'])
def test_support_retired_abi1_tamper_refuses_before_compile(retired_support_output, damage):
    fixture, session, output, retired = retired_support_output
    module = builder_module()
    if damage == 'abi-bool': retired['abi'] = True
    elif damage == 'abi3': retired['abi'] = 3
    elif damage == 'new-id': retired['build_id'] = module._test_build_id(retired['runtime'], retired['toolchain'])
    elif damage == 'build-id': retired['build_id'] = '0' * 64
    elif damage == 'runtime': retired['runtime']['sha256'] = '0' * 64
    elif damage == 'toolchain': retired['toolchain']['inputs'][SUPPORT_HEADER] = '0' * 64
    elif damage == 'inventory': retired['files'][SUPPORT_PAIR[1]]['sha256'] = '0' * 64
    elif damage in ('copy', 'so'):
        (output / (SUPPORT_COPY if damage == 'copy' else SUPPORT_PAIR[1])).write_bytes(b'bad')
    elif damage == 'extra': (output / 'keep').write_bytes(b'keep')
    elif damage == 'missing': (output / SUPPORT_COPY).unlink()
    elif damage in ('symlink', 'hardlink'):
        path = output / SUPPORT_COPY
        path.unlink()
        if damage == 'symlink': path.symlink_to(output / SUPPORT_PAIR[0])
        else: os.link(output / SUPPORT_PAIR[0], path)
    elif damage == 'file-mode': (output / SUPPORT_PAIR[1]).chmod(0o644)
    elif damage == 'directory-mode': (output / 'modules').chmod(0o755)
    module.prefix.write_control(output / 'build.json', retired)
    before = len([call for call in fixture.calls() if '-o' in call])
    with pytest.raises((ValueError, OSError)):
        module.build_test_support(fixture.root, session)
    assert len([call for call in fixture.calls() if '-o' in call]) == before
    assert not list((fixture.root / 'build').glob('.wine-publication-tests-*'))


def test_support_retired_abi1_build_failure_preserves_exact_previous(retired_support_output, monkeypatch):
    fixture, session, output, retired = retired_support_output
    module = builder_module()
    def refuse(*args):
        raise module.BuildError('inert compiler refusal')
    monkeypatch.setattr(module, '_compile', refuse)
    before = {str(path.relative_to(output)): path.read_bytes() for path in output.rglob('*') if path.is_file()}
    with pytest.raises(ValueError, match='inert compiler refusal'):
        module.build_test_support(fixture.root, session)
    assert before == {str(path.relative_to(output)): path.read_bytes() for path in output.rglob('*') if path.is_file()}
    assert module._recognized_test_output(output, for_replacement=True)[1] == retired
    with pytest.raises(ValueError, match='manifest'):
        module._recognized_test_output(output)
    assert not list((fixture.root / 'build').glob('.wine-publication-tests-*'))


@pytest.mark.parametrize('damage', ['copy', 'so', 'extra', 'symlink', 'manifest'])
def test_support_builder_refuses_tampered_output_before_compile(support_builder_fixture, damage):
    fixture, session = support_builder_fixture
    module = builder_module()
    assert hasattr(module, 'build_test_support'), 'independent test support builder is missing'
    module.build_test_support(fixture.root, session)
    output = fixture.root / 'build/wine-publication-tests'
    if damage in ('copy', 'so'):
        (output / (SUPPORT_COPY if damage == 'copy' else SUPPORT_PAIR[1])).write_bytes(b'bad')
    elif damage == 'extra':
        (output / 'keep').write_bytes(b'keep')
    elif damage == 'symlink':
        path = output / SUPPORT_COPY
        path.unlink()
        path.symlink_to(output / SUPPORT_PAIR[0])
    else:
        (output / 'build.json').write_text('{}')
    before = len([call for call in fixture.calls() if '-o' in call])
    with pytest.raises((ValueError, OSError)):
        module.build_test_support(fixture.root, session)
    assert len([call for call in fixture.calls() if '-o' in call]) == before


@pytest.fixture(scope='module')
def support_bridge_model(tmp_path_factory):
    directory = tmp_path_factory.mktemp('support-bridge-model')
    model = directory / 'model.c'
    model.write_text(r'''
#include <windef.h>
#include <winbase.h>
#include <winternl.h>
#include "record_publication_wine_support.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
int32_t WINAPI SpaceRecordPublicationTestsCall(uint32_t, void*);
static int selected, dispatches;
static void* original;
static const uint64_t opaque = UINT64_C(0x1122334455667788);
HANDLE WINAPI GetCurrentProcess(void) { return (HANDLE)(uintptr_t)5; }
BOOL GetModuleHandleExW(DWORD flags, LPCWSTR address, HMODULE* self) {
    assert(flags == 6 && address == (LPCWSTR)(uintptr_t)&SpaceRecordPublicationTestsCall);
    *self = (HMODULE)(uintptr_t)1;
    return selected != 1;
}
HMODULE GetModuleHandleW(LPCWSTR name) {
    assert(!wcscmp(name, L"ntdll.dll"));
    return selected == 2 ? NULL : (HMODULE)(uintptr_t)2;
}
static NTSTATUS WINAPI query(HANDLE process, const void* self, MEMORY_INFORMATION_CLASS kind,
                             void* out, SIZE_T size, SIZE_T* length) {
    assert(process == (HANDLE)(uintptr_t)5 && self == (HMODULE)(uintptr_t)1);
    assert(kind == 1000 && size == 8 && length == NULL);
    *(uint64_t*)out = selected == 6 ? 0 : opaque;
    return selected == 5 ? -127 : 0;
}
static NTSTATUS WINAPI dispatch(uint64_t handle, unsigned int entry, void* args) {
    assert(handle == opaque); /* Not a callable address. */
    ++dispatches;
    if (entry == SRPT_ENTRY_FIXTURE) {
        assert(args == original);
        ((SrptCall*)args)->os_error = 73;
        return -123;
    }
    if (entry == SRPT_ENTRY_LAUNCH) {
        SrptLaunch* value = args;
        const SrptLaunch* input = original;
        assert(value->size == 152 && value->abi == 2);
        assert(!memcmp(value, input, offsetof(SrptLaunch, phase)));
        assert(!value->phase && !value->os_error && !value->exit_code && !value->term_signal);
        assert(!value->outcome && !value->remaining_ms && !value->reserved && !value->reserved2);
        value->phase = SRPT_PHASE_COMPLETE; value->outcome = SRPT_OUTCOME_COMPLETED;
        value->exit_code = 0; value->remaining_ms = 1234;
        return selected == 30 ? -123 : SRPT_SUCCESS;
    }
    assert(entry == SRPT_ENTRY_IDENTITY);
    SrptIdentity* value = args;
    assert(value->size == 112 && value->abi == 2 && value->challenge == 42);
    for (unsigned i = 0; i < 32; ++i) {
        assert(value->pe_build_id[i] == 1);
        value->unix_build_id[i] = 1;
    }
    value->echo = value->challenge;
    value->architecture = SRPT_ARCH_X86_64;
    value->features = SRPT_FEATURES;
    value->module_device = 7; value->module_inode = 9;
    switch (selected) {
    case 10: ++value->size; break;
    case 11: ++value->abi; break;
    case 12: ++value->challenge; ++value->echo; break;
    case 13: ++value->echo; break;
    case 14: ++value->pe_build_id[0]; break;
    case 15: ++value->unix_build_id[31]; break;
    case 16: ++value->architecture; break;
    case 17: value->features = 1; break;
    case 18: value->features = 15; break;
    case 19: value->module_inode = 0; break;
    case 20: return -126;
    }
    return 0;
}
FARPROC GetProcAddress(HMODULE ntdll, const char* name) {
    assert(ntdll == (HMODULE)(uintptr_t)2);
    if (!strcmp(name, "NtQueryVirtualMemory")) return selected == 3 ? NULL : (FARPROC)query;
    assert(!strcmp(name, "__wine_unix_call"));
    return selected == 4 ? NULL : (FARPROC)dispatch;
}
int main(int argc, char** argv) {
    assert(argc == 2); selected = atoi(argv[1]);
    if (selected >= 30) {
        for (unsigned case_id = 0; case_id <= 5; ++case_id) {
            SrptLaunch value = {0}; value.size = sizeof(value); value.abi = 2;
            value.action = case_id ? SRPT_RUN : SRPT_CONFIGURE; value.case_id = case_id;
            value.root = 42; value.production_device = 1; value.production_inode = 2;
            value.support_device = 3; value.support_inode = 4;
            memset(value.production_build_id, 1, 32); memset(value.support_build_id, 2, 32);
            SrptLaunch before = value; original = &before;
            int prior = dispatches;
            assert(SpaceRecordPublicationTestsCall(2, &value) == (selected == 30 ? -123 : SRPT_SUCCESS));
            assert(dispatches == prior + 1 && value.phase == SRPT_PHASE_COMPLETE);
            assert(value.outcome == SRPT_OUTCOME_COMPLETED && value.remaining_ms == 1234);
            assert(!memcmp(&value, &before, offsetof(SrptLaunch, phase)));
        }
        int prior = dispatches;
        for (unsigned field = 0; field < 17; ++field) {
            SrptLaunch value = {0}; value.size = sizeof(value); value.abi = 2; value.action = SRPT_CONFIGURE;
            switch (field) {
            case 0: --value.size; break; case 1: ++value.size; break;
            case 2: value.abi = 1; break; case 3: value.abi = 3; break;
            case 4: value.action = 0; break; case 5: value.action = 3; break;
            case 6: value.case_id = 1; break;
            case 7: value.action = SRPT_RUN; value.case_id = 0; break;
            case 8: value.action = SRPT_RUN; value.case_id = 6; break;
            case 9: value.phase = 1; break; case 10: value.os_error = 1; break;
            case 11: value.exit_code = 1; break; case 12: value.term_signal = 1; break;
            case 13: value.outcome = 1; break; case 14: value.remaining_ms = 1; break;
            case 15: value.reserved = 1; break; case 16: value.reserved2 = 1; break;
            }
            assert(SpaceRecordPublicationTestsCall(2, &value) == SRPT_INVALID_ARGUMENT);
        }
        assert(SpaceRecordPublicationTestsCall(2, NULL) == SRPT_INVALID_ARGUMENT);
        assert(dispatches == prior);
        return 0;
    }
    SrptIdentity value = {0}; value.size = 112; value.abi = 2; value.challenge = 42;
    int32_t status = SpaceRecordPublicationTestsCall(SRPT_ENTRY_IDENTITY, &value);
    if (selected >= 1 && selected <= 6) {
        assert(status == (selected == 5 ? -127 : SRPT_MODULE_UNAVAILABLE) && !dispatches);
    } else if (selected >= 10 && selected <= 20) {
        assert(status == (selected == 20 ? -126 : SRPT_IDENTITY_MISMATCH));
        assert(value.echo == 0); /* Never return a half-validated identity. */
    } else {
        assert(status == 0 && value.echo == 42 && value.module_device == 7 && value.module_inode == 9);
        SrptCall call = {0}; call.size = sizeof(call); call.abi = 2; call.opcode = SRPT_OBSERVE;
        original = &call;
        assert(SpaceRecordPublicationTestsCall(SRPT_ENTRY_FIXTURE, &call) == -123 && call.os_error == 73);
        unsigned before = dispatches;
        call.opcode = 99;
        assert(SpaceRecordPublicationTestsCall(1, &call) == SRPT_INVALID_ARGUMENT);
        call.opcode = SRPT_OBSERVE; call.abi = 1;
        assert(SpaceRecordPublicationTestsCall(1, &call) == SRPT_INVALID_ARGUMENT);
        assert(SpaceRecordPublicationTestsCall(0, NULL) == SRPT_INVALID_ARGUMENT);
        assert(SpaceRecordPublicationTestsCall(1, NULL) == SRPT_INVALID_ARGUMENT);
        assert(SpaceRecordPublicationTestsCall(9, &value) == SRPT_INVALID_ARGUMENT);
        assert(before == (unsigned)dispatches);
    }
}
''')
    definition = '-DSRPT_BUILD_ID_BYTES={' + ','.join(['1'] * 32) + '}'
    output = directory / 'model'
    result = subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Werror', '-D_WIN64', definition,
                             '-I', str(ROOT / 'scripts/tests/wine_adapters'), '-I', str(ROOT / 'tests'),
                             str(ROOT / SUPPORT_PE), str(model), '-o', str(output)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return output


@pytest.mark.parametrize('case', [0, 1, 2, 3, 4, 5, 6, *range(10, 21), 30, 31])
def test_support_exact_pe_forwarder_host_model(support_bridge_model, case):
    result = subprocess.run([str(support_bridge_model), str(case)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert not result.stdout and not result.stderr


def test_support_pe_dispatch_declarations_have_wine9_calling_convention(tmp_path):
    bridge = (ROOT / SUPPORT_PE).read_text()
    assert '<wine/unixlib.h>' not in bridge and 'wine-9.0/include/wine/unixlib.h' in bridge
    block = bridge[bridge.index('typedef uint64_t SrptUnixHandle;'):bridge.index('static const uint8_t build_id')]
    source = '''#include <stdint.h>
typedef int32_t NTSTATUS;
#define WINAPI __attribute__((ms_abi))
enum { MemoryWineUnixFuncs = 1000 };
''' + block + '''
_Static_assert(__builtin_types_compatible_p(SrptUnixCall,
    int32_t (WINAPI *)(uint64_t, unsigned int, void*)), "Wine9 dispatch signature");
_Static_assert(!__builtin_types_compatible_p(SrptUnixCall,
    int32_t (*)(uint64_t, unsigned int, void*)), "not SysV");
'''
    result = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-x', 'c', '-c',
                             '-', '-o', str(tmp_path / 'abi.o')], input=source,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_publication_pe_closed_launch_sequence_activation_and_intact_receipts():
    source = (ROOT / 'tests/test_record_publication.cpp').read_text()
    body = source.split('void wine_loader_children()', 1)[1].split('void wine_report()', 1)[0]
    assert 'CreateProcessW' not in source and 'child_environment(' not in source and 'void run_child(' not in source
    configure = body.index('launch_request(SRPT_CONFIGURE, 0, owned_tmp->id, production_binding, support_binding)')
    assert body.index('const auto call_start = Clock::now()') < configure < body.index('invoke_launch(configure, nullptr)')
    assert body.index('call_start + std::chrono::milliseconds(configure.remaining_ms)') < body.index('executable_path()')
    assert body.index('invoke_launch(configure, nullptr)') < body.index('Fixture fixture;') < body.index('HostRoot fixture_host(fixture.root)')
    assert body.index('exclusive_copy(pe_source, production_host, pe, deadline)') < body.index('if (selected == "missing-pe")')
    assert body.index('exclusive_copy(pe_source, production_host, discovery, deadline)') < body.index('if (selected == "missing-pe")')
    assert body.index('exclusive_copy(so_source, production_host, so, deadline)') < body.index('const auto copied = owned_tmp->observe(so)')
    assert body.index('const auto copied = owned_tmp->observe(so)') < body.index('if (selected == "missing-unix")')
    assert 'launch_request(SRPT_RUN, case_id, fixture_host.id, expected, support_binding)' in body
    assert 'invoke_launch(run, &fixture)' in body and 'child_budget(deadline, 13000)' in body
    assert body.index('invoke_launch(run, &fixture)') < body.index('fs::remove_all(fixture.root)') < body.rindex('child_budget(deadline)')
    copy = source.split('void exclusive_copy(', 1)[1].split('void wine_loader_children()', 1)[0]
    assert 'owned_tmp->observe(destination)' in copy and 'source_root.bytes(source) == owned_tmp->bytes(destination)' in copy
    assert 'same_host_object(before, source_root.observe(source))' in copy
    assert '"control", "missing-pe", "bad-pe", "missing-unix", "bad-unix"' in source
    child = source.split('int wine_child(', 1)[1].split('using Clock =', 1)[0]
    assert 'overrides == child_overrides()' in child
    assert child.index('production_entry();') < child.index('clean_anchor(data);') < child.index('control-completion=1')
    for guard in ('std::string("new\\0bytes", 9)', 'hooks == 4', 'hooks == 0',
                  'same_host_object(before, owned_tmp->observe(destination))', '!fs::exists(anchor(data))',
                  'production DLL absent before first child publish', 'one independent support-only root'):
        assert guard in child


@pytest.fixture(scope='module')
def publication_private_child_startup(tmp_path_factory):
    """Run verbatim CPP startup/helper/known-dependency guard against host APIs."""
    source = (ROOT / 'tests/test_record_publication.cpp').read_text()
    helper_start = source.find('void initialize_wine_child_path()')
    # Before the repair, run the actual old startup to expose its nonempty PATH.
    helper = '' if helper_start < 0 else source[helper_start:source.index('std::wstring child_overrides()')]
    prefix = source[source.index('int main(int argc, char** argv)'):source.index('        private_contract_models();')]
    prefix = prefix.replace('int main(', 'int application_entry(', 1)
    catch = source[source.index('    } catch (const std::exception& error) {', source.index('int main(')):]
    check = source[source.index('void check(bool condition,'):source.index('using Binding =')]
    win_check = source[source.index('void win_check(BOOL ok,'):source.index('struct CheckedHandle')]
    cases = source[source.index('const std::array<std::string, 5> child_cases'):source.index('std::wstring child_overrides()')]
    if helper_start >= 0:
        cases = cases[:cases.index('void initialize_wine_child_path()')]
    guard_start = source.index('    for (const auto& item : fs::directory_iterator(root)) {', source.index('int wine_child('))
    guard = source[guard_start:source.index('    child_phase = "location-09";', guard_start)]
    adapter = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <filesystem>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include "wine_owned_environment.h"
namespace fs = std::filesystem;
bool under_wine = false, model_wine;
const char* child_phase = "entry";
DWORD child_error = ERROR_SUCCESS, last_error = 77;
std::string mode;
std::vector<std::string> events;
std::map<std::wstring, std::wstring> variables;
fs::path case_root;
bool private_request;
namespace rp::wine { bool detected() { events.emplace_back("detect"); return model_wine; } }
extern "C" void SetLastError(DWORD value) { last_error = value; }
extern "C" DWORD GetLastError() { return last_error; }
extern "C" BOOL SetEnvironmentVariableW(const WCHAR* key, const WCHAR* value) {
    assert(last_error == ERROR_SUCCESS);
    assert(value);
    const std::wstring name(key);
    events.emplace_back(name == L"PATH" ? "path-set" : name == L"TEMP" ? "temp-set" : "tmp-set");
    if ((name == L"TEMP" && mode == "temp-set-fail") ||
        (name == L"PATH" && (mode == "set-fail" || mode == "set-fail-no-error"))) {
        last_error = mode == "set-fail-no-error" ? ERROR_SUCCESS : ERROR_ACCESS_DENIED;
        return FALSE;
    }
    variables[name] = value;
    last_error = 77; // Successful sets need not clear LastError; read must reset it.
    return TRUE;
}
extern "C" DWORD GetEnvironmentVariableW(const WCHAR* key, WCHAR* out, DWORD capacity) {
    assert(last_error == ERROR_SUCCESS);
    const std::wstring name(key);
    if (name == L"PATH") {
        events.emplace_back("path-read");
        assert(capacity == 2 && out[0] != 0); // Seeded terminator witness, not zero-initialization.
        if (mode == "read-missing" || mode == "read-missing-terminated") {
            if (mode == "read-missing-terminated") out[0] = 0;
            last_error = ERROR_ENVVAR_NOT_FOUND;
            return 0;
        }
        if (mode == "read-error" || mode == "read-error-terminated") {
            if (mode == "read-error-terminated") out[0] = 0;
            last_error = ERROR_ACCESS_DENIED;
            return 0;
        }
        if (mode == "read-nonempty") { out[0] = L'x'; out[1] = 0; return 1; }
        if (mode == "read-size") return 3;
        if (mode == "read-no-terminator") return 0;
    } else if (name == L"TEMP" || name == L"TMP") {
        events.emplace_back(name == L"TEMP" ? "temp-read" : "tmp-read");
        if (name == L"TEMP" && mode == "temp-read-fail") { last_error = ERROR_ACCESS_DENIED; return 0; }
    }
    const auto found = variables.find(name);
    if (found == variables.end()) { last_error = ERROR_ENVVAR_NOT_FOUND; return 0; }
    const auto& value = found->second;
    if (value.size() >= capacity) return static_cast<DWORD>(value.size() + 1);
    std::copy(value.begin(), value.end(), out);
    out[value.size()] = 0;
    return static_cast<DWORD>(value.size());
}
extern "C" HMODULE GetModuleHandleW(const WCHAR* name) {
    if (!wcscmp(name, L"space_record_publication.dll")) return nullptr;
    if (!wcscmp(name, L"libgcc_s_seh-1.dll")) return reinterpret_cast<HMODULE>(1);
    if (!wcscmp(name, L"libstdc++-6.dll")) return reinterpret_cast<HMODULE>(2);
    if (!wcscmp(name, L"libwinpthread-1.dll")) return reinterpret_cast<HMODULE>(3);
    return nullptr;
}
// Host fs::path stores bytes; the verbatim Win32 guard uses its native c_str().
HMODULE GetModuleHandleW(const char* name) {
    const std::string bytes(name);
    const std::wstring wide(bytes.begin(), bytes.end());
    return GetModuleHandleW(wide.c_str());
}
fs::path executable_path(HMODULE module) {
    const auto id = reinterpret_cast<uintptr_t>(module);
    const std::array<std::string, 3> names {"libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll"};
    assert(id >= 1 && id <= names.size());
    const auto& name = names[id - 1];
    return (mode == "fallback-" + name ? case_root.parent_path() / "outside-case" : case_root) / name;
}
std::string host_path(const fs::path& path) { return path.string(); }
struct HostRoot { explicit HostRoot(const fs::path&) {} };
std::unique_ptr<HostRoot> owned_tmp;
void load_support();
int wine_child(const std::string&);
'''
    services = r'''
void load_support() {
    events.emplace_back("support");
    if (private_request) {
        check(variables[L"PATH"].empty(), "private PATH still contains registry seed");
        check(variables[L"TEMP"] == variables[L"SPACE_WINE_WINDOWS_TMP"] &&
              variables[L"TMP"] == variables[L"SPACE_WINE_WINDOWS_TMP"], "owned temp must precede support");
    }
}
int wine_child(const std::string&) {
    events.emplace_back("child");
    child_phase = "location-08";
    const auto root = case_root;
'''
    driver = r'''
int main(int argc, char** argv) {
    assert(argc >= 4);
    mode = argv[1]; model_wine = std::string(argv[2]) == "wine"; case_root = argv[3];
    private_request = argc != 4;
    variables = {{L"PATH", mode == "already-empty" ? L"" : L"registry-path-must-not-leak"},
                 {L"TEMP", L"registry-temp-must-not-leak"}, {L"TMP", L"registry-tmp-must-not-leak"},
                 {L"SPACE_WINE_WINDOWS_TMP", LR"(R:\owned\tmp)"}};
    const auto result = application_entry(argc - 3, argv + 3);
    for (const auto& event : events) std::cout << event << '\n';
    std::cout << "result=" << result << '\n';
    if (!private_request) {
        assert(variables[L"PATH"] == (mode == "already-empty" ? L"" : L"registry-path-must-not-leak"));
    }
}
'''
    directory = tmp_path_factory.mktemp('publication-private-child-startup')
    outputs = {}
    for platform in ('windows', 'posix'):
        # Define _WIN32 after the native standard-library headers, not as a host ABI claim.
        code = adapter + ('\n#define _WIN32\n' if platform == 'windows' else '\n')
        code += check + win_check + cases
        if platform == 'windows':
            code += helper
        code += services + guard + '\n    return 0;\n}\n'
        code += prefix + '        return 0;\n' + catch + driver
        model = directory / f'{platform}.cpp'
        model.write_text(code)
        output = directory / platform
        result = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                 '-I', str(ROOT / 'scripts/tests/wine_adapters'), '-I', str(ROOT / 'src'),
                                 str(model), '-o', str(output)], capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        assert not result.stdout and not result.stderr
        outputs[platform] = output
    return outputs


def run_private_child_startup(model, tmp_path, *, mode='normal', runtime='wine', args=(), platform='windows'):
    case = tmp_path / 'case'
    case.mkdir()
    for name in ('libgcc_s_seh-1.dll', 'libstdc++-6.dll', 'libwinpthread-1.dll'):
        (case / name).write_bytes(b'host fixture, not PE')
    result = subprocess.run([str(model[platform]), mode, runtime, str(case), *args],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert all(value not in result.stdout + result.stderr for value in
               ('registry-path-must-not-leak', 'registry-temp-must-not-leak', 'registry-tmp-must-not-leak', str(case)))
    assert all(len(line) < 160 for line in result.stdout.splitlines() + result.stderr.splitlines())
    lines = result.stdout.splitlines()
    return int(lines[-1].removeprefix('result=')), lines[:-1], result.stderr


@pytest.mark.parametrize('case', ['control', 'missing-pe', 'bad-pe', 'missing-unix', 'bad-unix'])
@pytest.mark.parametrize('mode', ['normal', 'already-empty'])
def test_publication_private_child_path_initializer_host_model(publication_private_child_startup, tmp_path, case, mode):
    code, events, stderr = run_private_child_startup(publication_private_child_startup, tmp_path, mode=mode,
                                                   args=['--wine-publication-child=' + case])
    assert code == 0, stderr
    assert events == ['detect', 'temp-set', 'tmp-set', 'temp-read', 'tmp-read',
                      'path-set', 'path-read', 'support', 'child']
    assert stderr == 'record publication diagnostic: main-entry\n'


@pytest.mark.parametrize('mode,error', [('set-fail', 5), ('set-fail-no-error', 0),
    ('read-missing', 203), ('read-missing-terminated', 203), ('read-error', 5),
    ('read-error-terminated', 5), ('read-nonempty', 0), ('read-size', 0), ('read-no-terminator', 0)])
def test_publication_private_child_path_failures_refuse_before_support(publication_private_child_startup, tmp_path, mode, error):
    code, events, stderr = run_private_child_startup(publication_private_child_startup, tmp_path, mode=mode,
                                                   args=['--wine-publication-child=control'])
    assert code == 1
    assert events == ['detect', 'temp-set', 'tmp-set', 'temp-read', 'tmp-read', 'path-set'] + (
        [] if mode.startswith('set-') else ['path-read'])
    phase = 'child-path-set' if mode.startswith('set-') else 'child-path-readback'
    assert stderr == ('record publication diagnostic: main-entry\n'
                      f'record publication child failed phase={phase} error={error}\n')


@pytest.mark.parametrize('platform,runtime,args,code', [
    ('windows', 'wine', [], 0), ('windows', 'native', [], 0), ('posix', 'native', [], 0),
    ('windows', 'native', ['--wine-publication-child=control'], 1),
    ('windows', 'wine', ['--wine-publication-child=unknown'], 1),
    ('windows', 'wine', ['--wine-publication-child='], 1),
    ('windows', 'wine', ['--other=control'], 1),
    ('windows', 'wine', ['--wine-publication-child=control', 'extra'], 1),
    ('posix', 'native', ['--wine-publication-child=control'], 1)])
def test_publication_private_child_startup_gates_preserve_other_entry_modes(publication_private_child_startup, tmp_path,
                                                                          platform, runtime, args, code):
    actual, events, _ = run_private_child_startup(publication_private_child_startup, tmp_path, platform=platform,
                                                 runtime=runtime, args=args, mode='set-fail')
    assert actual == code
    assert 'path-set' not in events and 'path-read' not in events and 'child' not in events
    assert ('support' in events) == (platform == 'windows' and runtime == 'wine' and not args)


@pytest.mark.parametrize('mode', ['temp-set-fail', 'temp-read-fail'])
def test_publication_private_child_startup_temp_failure_precedes_path(publication_private_child_startup, tmp_path, mode):
    code, events, _ = run_private_child_startup(publication_private_child_startup, tmp_path, mode=mode,
                                              args=['--wine-publication-child=control'])
    assert code == 1
    assert 'path-set' not in events and 'path-read' not in events and 'support' not in events


@pytest.mark.parametrize('name', ['libgcc_s_seh-1.dll', 'libstdc++-6.dll', 'libwinpthread-1.dll'])
def test_publication_private_child_known_dependency_fallback_still_refuses(publication_private_child_startup, tmp_path, name):
    code, events, stderr = run_private_child_startup(publication_private_child_startup, tmp_path, mode='fallback-' + name,
                                                   args=['--wine-publication-child=control'])
    assert code == 1
    assert events[-4:] == ['path-set', 'path-read', 'support', 'child']
    assert stderr.endswith('record publication child failed phase=location-08 error=0\n')


def test_publication_pe_uncertain_ownership_diagnostic_cannot_unwind():
    source = (ROOT / 'tests/test_record_publication.cpp').read_text()
    body = source.split('void invoke_launch(', 1)[1].split('using Clock =', 1)[0]
    fatal = body[:body.index('check(')]
    assert 'std::fprintf(stderr,' in fatal and 'std::fflush(nullptr)' in fatal
    assert 'std::cerr' not in fatal and 'std::cout' not in fatal and 'std::abort' not in fatal
    assert 'const bool acknowledged =' in fatal
    assert fatal.index('const bool acknowledged =') < fatal.index('fixture->preserve_wine_fixture = true') < fatal.index('std::fprintf(stderr,')
    assert 'untrusted-launch-result' in fatal
    assert fatal.index('std::fflush(nullptr)') < fatal.index('::TerminateProcess(::GetCurrentProcess(), 125)') < fatal.index('std::_Exit(125)')


@pytest.fixture(scope='module')
def publication_pe_launch_consumer(tmp_path_factory):
    """Compile actual consumer functions as native code, never execute PE/Wine."""
    source = (ROOT / 'tests/test_record_publication.cpp').read_text()
    assert 'SrptLaunch launch_request(' in source, 'PE closed launch consumer is missing'
    functions = source[source.index('SrptLaunch launch_request('):source.index('using Clock =')]
    directory = tmp_path_factory.mktemp('pe-launch-consumer')
    model = directory / 'model.cpp'
    model.write_text(r'''
#include "record_publication_wine_support.h"
#include "record_publication_wine_binding.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <cassert>
using Binding = record_publication::wine::detail::Binding;
void check(bool ok, const std::string& message) { if (!ok) throw std::runtime_error(message); }
struct Fixture { bool preserve_wine_fixture = false; ~Fixture() { std::cerr << "DESTRUCTOR\n"; } };
Fixture* active_fixture;
bool fail_run;
void* GetCurrentProcess() { return reinterpret_cast<void*>(42); }
int TerminateProcess(void* process, unsigned code) {
    assert(process == reinterpret_cast<void*>(42) && code != 0);
    assert(!fail_run || (active_fixture && active_fixture->preserve_wine_fixture));
    std::cerr << "TERMINATE\n" << std::flush;
    return 0; // Exercise the mandatory _Exit fallback, not debugger abort.
}
struct Result {
    int32_t status;
    uint32_t outcome, phase, error, exit, signal, remaining, mutation;
} result;
int32_t entry(uint32_t selected, void* raw) {
    assert(selected == SRPT_ENTRY_LAUNCH);
    auto& frame = *static_cast<SrptLaunch*>(raw);
    assert(frame.size == 152 && frame.abi == 2 && frame.root == 42);
    assert(!frame.phase && !frame.os_error && !frame.exit_code && !frame.term_signal);
    assert(!frame.outcome && !frame.remaining_ms && !frame.reserved && !frame.reserved2);
    assert(frame.production_device == 1 && frame.production_inode == 2);
    assert(frame.support_device == 3 && frame.support_inode == 4);
    assert(std::all_of(frame.production_build_id, frame.production_build_id + 32, [](auto byte) { return byte == 0xaa; }));
    assert(std::all_of(frame.support_build_id, frame.support_build_id + 32, [](auto byte) { return byte == 0xbb; }));
    frame.phase = SRPT_PHASE_COMPLETE; frame.outcome = SRPT_OUTCOME_COMPLETED;
    frame.exit_code = frame.action == SRPT_CONFIGURE ? UINT32_MAX : 0;
    frame.remaining_ms = 59000;
    if ((frame.action == SRPT_RUN) != fail_run) return SRPT_SUCCESS;
    frame.outcome = result.outcome; frame.phase = result.phase; frame.os_error = result.error;
    frame.exit_code = result.exit; frame.term_signal = result.signal; frame.remaining_ms = result.remaining;
    switch (result.mutation) {
    case 1: ++frame.size; break;
    case 2: ++frame.abi; break;
    case 3: ++frame.action; break;
    case 4: ++frame.case_id; break;
    case 5: ++frame.root; break;
    case 6: ++frame.production_build_id[0]; break;
    case 7: ++frame.support_build_id[31]; break;
    case 8: ++frame.production_device; break;
    case 9: ++frame.production_inode; break;
    case 10: ++frame.support_device; break;
    case 11: ++frame.support_inode; break;
    case 12: ++frame.reserved; break;
    case 13: ++frame.reserved2; break;
    }
    return result.status;
}
auto support_entry = entry;
''' + functions + r'''
int main(int argc, char** argv) {
    assert(argc == 10); fail_run = std::string(argv[1]) == "run";
    result.status = static_cast<int32_t>(std::stoll(argv[2]));
    result.outcome = std::stoul(argv[3]); result.phase = std::stoul(argv[4]); result.error = std::stoul(argv[5]);
    result.exit = std::stoul(argv[6]); result.signal = std::stoul(argv[7]);
    result.remaining = std::stoul(argv[8]); result.mutation = std::stoul(argv[9]);
    Binding production {}, support {};
    production.build_id.fill(0xaa); production.module_device = 1; production.module_inode = 2;
    support.build_id.fill(0xbb); support.module_device = 3; support.module_inode = 4;
    Fixture fixture;
    active_fixture = &fixture;
    try {
        auto frame = launch_request(SRPT_CONFIGURE, 0, 42, production, support);
        invoke_launch(frame, nullptr);
        for (uint32_t id = 1; id <= 5; ++id) {
            frame = launch_request(SRPT_RUN, id, 42, production, support);
            invoke_launch(frame, &fixture);
        }
        return 0;
    } catch (const std::exception& error) {
        assert(!fixture.preserve_wine_fixture);
        std::cout << "REJECTED\n";
        return 0;
    }
}
''')
    output = directory / 'model'
    result = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'src'),
                             '-I', str(ROOT / 'tests'), str(model), '-o', str(output)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return output


def publication_pe_result_cases():
    """Explicit native contract tuples, not an alternate ownership classifier."""
    failed, invalid, mismatch, unavailable = (-1073741823, -1073741811, -1073741701, -1073741515)
    no_exit = 0xffffffff
    cases = []
    def add(action, name, values, disposition):
        # status/outcome/phase/errno/exit/signal/remaining/prefix-or-reserved mutation
        cases.append(pytest.param(action, values, disposition, id=action + '-' + name))
    for action in ('configure', 'run'):
        success = (0, 1, 9, 0, no_exit if action == 'configure' else 0, 0, 59000, 0)
        add(action, 'completed', success, 'completed')
        for status in (failed, invalid, mismatch):
            for phase in range(1, 5 if action == 'configure' else 6):
                for error in (0, 5):
                    add(action, f'no-child-{status}-{phase}-{error}',
                        (status, 4, phase, error, no_exit, 0, 0, 0), 'retired')
        malformed = {
            'unset-success-old-mode11': (0, 0, 9, 0, success[4], 0, 59000, 0),
            'unset-failure': (failed, 0, 0, 0, no_exit, 0, 0, 0),
            'unset-acquisition-shaped': (unavailable, 0, 0, 0, no_exit, 0, 0, 0),
            'unknown-outcome': (failed, 6, 8, 5, no_exit, 9, 59000, 0),
            'max-outcome': (failed, no_exit, 8, 5, no_exit, 9, 59000, 0),
            'explicit-uncertain': (failed, 5, 8, 5, no_exit, 9, 59000, 0),
            'uncertain-success': (0, 5, 8, 5, no_exit, 9, 59000, 0),
            'completed-failure-status': (failed, *success[1:]),
            'completed-unknown-status': (1, *success[1:]),
            'completed-phase-wait': (0, 1, 6, 0, success[4], 0, 59000, 0),
            'completed-errno': (0, 1, 9, 5, success[4], 0, 59000, 0),
            'completed-wrong-exit': (0, 1, 9, 0, 7, 0, 59000, 0),
            'completed-signal': (0, 1, 9, 0, success[4], 9, 59000, 0),
            'oversized-budget': (*success[:6], 60001, 0),
            'host-failure-success-status': (0, 4, 1, 0, no_exit, 0, 0, 0),
            'host-failure-unknown-status': (unavailable, 4, 1, 0, no_exit, 0, 0, 0),
            'host-failure-phase-complete': (failed, 4, 9, 5, 0, 0, 0, 0),
            'host-failure-phase-wait': (failed, 4, 6, 5, no_exit, 0, 0, 0),
            'host-failure-phase-terminate': (failed, 4, 7, 5, no_exit, 0, 0, 0),
            'host-failure-phase-input': (invalid, 4, 0, 0, no_exit, 0, 0, 0),
            'host-failure-pre-spawn-exit': (failed, 4, 3, 5, 0, 0, 0, 0),
            'host-failure-pre-spawn-signal': (failed, 4, 3, 5, no_exit, 9, 0, 0),
        }
        for name, values in malformed.items():
            add(action, name, values, 'fatal')
        for mutation in range(1, 14):
            add(action, f'changed-frame-{mutation}', (*success[:7], mutation), 'fatal')
    for status in (failed, invalid, mismatch):
        for error in (0, 5):
            for exit_code, term_signal in ((0, 0), (23, 0), (no_exit, 1), (no_exit, 64)):
                add('run', f'retired-host-{status}-{error}-{exit_code}-{term_signal}',
                    (status, 4, 8, error, exit_code, term_signal, 0, 0), 'retired')
    for outcome, error in ((2, 0), (3, 110)):
        for exit_code, term_signal in ((23, 0), (255, 0), (no_exit, 1), (no_exit, 64)):
            add('run', f'retired-{outcome}-{exit_code}-{term_signal}',
                (failed, outcome, 8, error, exit_code, term_signal, 0, 0), 'retired')
        if outcome == 3:
            add('run', 'timeout-exit-zero-race', (failed, 3, 8, 110, 0, 0, 0, 0), 'retired')
        for status in (0, invalid, mismatch, 1):
            add('run', f'bad-status-{outcome}-{status}', (status, outcome, 8, error, 23, 0, 0, 0), 'fatal')
        add('run', f'bad-errno-{outcome}', (failed, outcome, 8, 5, 23, 0, 0, 0), 'fatal')
    for outcome, error in ((2, 0), (3, 110), (4, 5)):
        for exit_code, term_signal in ((no_exit, 0), (256, 0), (23, 9), (no_exit, 65), (no_exit, no_exit)):
            add('run', f'bad-disposition-{outcome}-{exit_code}-{term_signal}',
                (failed, outcome, 8, error, exit_code, term_signal, 0, 0), 'fatal')
        add('configure', f'run-only-retired-{outcome}', (failed, outcome, 8, error, 23, 0, 0, 0), 'fatal')
    add('run', 'child-failure-exit-zero', (failed, 2, 8, 0, 0, 0, 0, 0), 'fatal')
    add('run', 'timeout-no-errno', (failed, 3, 8, 0, 23, 0, 0, 0), 'fatal')
    add('configure', 'host-failure-spawn-phase', (failed, 4, 5, 5, no_exit, 0, 0, 0), 'fatal')
    return cases


@pytest.mark.parametrize('action,values,disposition', publication_pe_result_cases())
def test_publication_pe_launch_consumer_status_and_failstop(publication_pe_launch_consumer, action, values, disposition):
    result = subprocess.run([str(publication_pe_launch_consumer), action, *map(str, values)],
                            capture_output=True, text=True, timeout=10)
    case_id = 1 if action == 'run' else 0
    lines = result.stderr.splitlines()
    normal = [line for line in lines if line.startswith('record publication diagnostic: case=')]
    fatal = [line for line in lines if 'untrusted-launch-result' in line]
    if disposition == 'fatal':
        assert result.returncode == 125, result.stdout + result.stderr
        assert 'TERMINATE' in result.stderr and 'DESTRUCTOR' not in result.stderr and 'REJECTED' not in result.stdout
        assert len(fatal) == 1 and f'case={case_id} ' in fatal[0]
        assert lines.index(fatal[0]) < lines.index('TERMINATE')
        assert not any(f'case={case_id} ' in line for line in normal)
    else:
        assert result.returncode == 0, result.stderr
        assert 'DESTRUCTOR' in result.stderr and 'TERMINATE' not in result.stderr
        assert ('REJECTED' in result.stdout) == (disposition == 'retired')
        assert not fatal and any(f'case={case_id} ' in line for line in normal)
        if disposition == 'completed':
            assert len(normal) == 6 and 'case=5 ' in normal[-1]
    if disposition != 'completed':
        assert 'case=2 ' not in result.stderr  # Failure never advances/retries the fixed sequence.
    diagnostics = [line for line in lines if line.startswith('record publication diagnostic:')]
    for line in diagnostics:
        assert len(line) < 256 and 'native-result=' in line
        assert str(ROOT) not in line and 'BINDING' not in line and 'PATH' not in line


@pytest.mark.parametrize('crypto', ['b', 'n', 'bn', 'native', ''])
def test_publication_pe_child_overrides_require_exact_owning_crypto(tmp_path, crypto):
    source = (ROOT / 'tests/test_record_publication.cpp').read_text()
    assert 'std::wstring child_overrides()' in source
    function = source[source.index('std::wstring child_overrides()'):source.index('int wine_child(')]
    model = tmp_path / 'overrides.cpp'
    model.write_text(r'''
#include <string>
#include <stdexcept>
#include <cassert>
std::wstring owner;
std::wstring environment(const wchar_t* name) {
    assert(std::wstring(name) == L"SPACE_WINE_PUBLICATION_TEST_CRYPTO"); return owner;
}
void check(bool ok, const char* message) { if (!ok) throw std::runtime_error(message); }
''' + function + r'''
int main(int argc, char** argv) {
    assert(argc == 2); const std::string input = argv[1]; owner.assign(input.begin(), input.end());
    try {
        const auto value = child_overrides();
        assert(input == "b" || input == "n");
        assert(value == L"space_record_publication=b;space_record_publication_tests=b;bcryptprimitives="
            + owner + L";advapi32,cryptbase=b");
        assert(value != L"space_record_publication=b;space_record_publication_tests=b;bcryptprimitives="
            + std::wstring(owner == L"b" ? L"n" : L"b") + L";advapi32,cryptbase=b");
        assert(value.find(L"space_record_publication,space_record_publication_tests") == std::wstring::npos);
    } catch (const std::exception&) { assert(input != "b" && input != "n"); }
}
''')
    output = tmp_path / 'overrides'
    compiled = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(model), '-o', str(output)],
                              capture_output=True, text=True, timeout=60)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run([str(output), crypto], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and not result.stdout and not result.stderr


def test_support_real_elf_bounded_owned_roots_and_target_parent_refusals(support_elf, tmp_path):
    operate = support_elf[3]
    for mode in [0o750, 0o770]:
        unsafe = tmp_path / str(mode)
        unsafe.mkdir(mode=0o700)
        unsafe.chmod(mode)
        assert support_call(operate, 1, path=str(unsafe))[0] != 0
        assert unsafe.stat().st_mode & 0o777 == mode
    alias = tmp_path / 'alias'
    alias.symlink_to(tmp_path, target_is_directory=True)
    assert support_call(operate, 1, path=str(alias / str(0o750)))[0] != 0
    root_ids = []
    try:
        for _ in range(64):
            root_ids.append(support_ok(operate, 1, path=str(tmp_path)).root)
        assert len(set(root_ids)) == 64
        assert support_call(operate, 1, path=str(tmp_path))[0] != 0
        root = root_ids[0]
        support_ok(operate, 5, root=root, path='record', data=b'kept', mode=0o600)
        for opcode in [8, 10]:
            assert support_call(operate, opcode, root=root, path='record', other='alias/target')[0] != 0
        assert (tmp_path / 'record').read_bytes() == b'kept'
        assert not (tmp_path / 'target').exists()
        # No arbitrary UID takeover or root metadata mutation commands exist.
        for opcode in [4, 5, 6, 7, 12, 13, 14]:
            assert support_call(operate, opcode, root=root, mode=0o777)[0] != 0
        assert tmp_path.stat().st_mode & 0o777 == 0o700
        # Both sides use validated byte names; no UTF8 assumption or MAX_PATH cap.
        parent = ''
        for index in range(5):
            parent += ('/' if parent else '') + str(index) + 'd' * 80
            support_ok(operate, 4, root=root, path=parent, mode=0o700)
        name = parent + '/雪-\udcff'
        support_ok(operate, 5, root=root, path=name, data=b'raw host name', mode=0o600)
        assert bytes(support_ok(operate, 3, root=root, path=name).data[:13]) == b'raw host name'
    finally:
        for root in root_ids:
            support_ok(operate, 2, root=root)
    new = support_ok(operate, 1, path=str(tmp_path)).root
    try:
        assert new > max(root_ids)
        assert support_call(operate, 2, root=root_ids[-1])[0] != 0
        assert support_call(operate, 3, root=new)[0] == 0
    finally:
        support_ok(operate, 2, root=new)


@pytest.mark.parametrize('damage', ['compiler', 'source-drift', 'tool-drift', 'discovery', 'image'])
def test_support_builder_failure_preserves_previous_pair(support_builder_fixture, monkeypatch, damage):
    fixture, session = support_builder_fixture
    module = builder_module()
    previous = module.build_test_support(fixture.root, session)
    original = module._compile
    def fail_build(args, stage):
        if damage == 'compiler':
            raise module.BuildError('test-only compiler refusal')
        original(args, stage)
        if '--builtin' not in args:
            return
        if damage in ('source-drift', 'tool-drift'):
            path = fixture.root / SUPPORT_HEADER if damage == 'source-drift' else fixture.lib / 'winebuild'
            path.write_bytes(path.read_bytes() + b'\n# changed while building\n')
        elif damage == 'image':
            path = Path(args[-1])
            raw = bytearray(path.read_bytes())
            raw[132:134] = bytes(2)  # Real image validation, not a fake inventory.
            path.write_bytes(raw)
    monkeypatch.setattr(module, '_compile', fail_build)
    if damage == 'discovery':
        inventory = module._test_inventory
        def damage_copy(output, build_id):
            if output.name == 'new':
                # Differing but structurally valid staging copy; paired PE intact.
                path = output / SUPPORT_COPY
                raw = bytearray(path.read_bytes())
                raw[-33] ^= 1
                path.write_bytes(raw)
            return inventory(output, build_id)
        monkeypatch.setattr(module, '_test_inventory', damage_copy)
    with pytest.raises((ValueError, OSError)):
        module.build_test_support(fixture.root, session)
    output = fixture.root / 'build/wine-publication-tests'
    assert json.loads((output / 'build.json').read_text()) == previous
    assert module._recognized_test_output(output)[1] == previous
    assert not list((fixture.root / 'build').glob('.wine-publication-tests-*'))


# Closed launcher builder tests. These never execute Wine or produce a real PE.
def support_runtime_api():
    module = builder_module()
    assert hasattr(module, '_capture_launch_metadata'), 'support runtime capture is missing'
    assert hasattr(module, '_render_launch_header'), 'support runtime header is missing'
    return module


@pytest.fixture
def support_native_runtime(tmp_path, monkeypatch):
    """Real inert ELF files, with only their installed-path trust facts modelled.

    The unprivileged host cannot create root-owned installed fixtures. Restrict the
    stat protocol model to these files and their ancestors; all opens, nofollow
    traversal, access checks, reads, hashes and races still use the real filesystem.
    Separate unmodelled tests below exercise the host's actual unsafe /tmp ancestry.
    This is not evidence about installed Wine or a relaxation in production capture.
    """
    directory = tmp_path / 'native-\udcff'
    directory.mkdir()
    binary = directory / 'wine64'
    result = subprocess.run(['cc', '-x', 'c', '-', '-o', str(binary)],
                            input='int main(void) { return 97; }\n', text=True,
                            capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    # Isolate server-only ancestry failures without invalidating Wine64 first.
    # The common directory remains available for both-role ancestor race tests.
    server_directory = directory / 'server-runtime'
    server_directory.mkdir()
    server = server_directory / 'wineserver'
    shutil.copy2(binary, server)
    wrapper = directory / 'wine'
    wrapper.write_text('#!/bin/sh\nexit 98\n')
    wrapper.chmod(0o755)
    expected = lambda path: dict(executable=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    identity = dict(installation=dict(file=expected(wrapper), implementation=dict(file=expected(binary))))
    session = SimpleNamespace(owner=dict(tools=dict(wine=expected(wrapper), server=expected(server))))
    real_os = os
    trusted = {path.stat().st_ino for path in [binary, server, server_directory, directory, *directory.parents]}
    overrides = {}
    def info(value):
        if value.st_ino not in trusted:
            return value
        fields = {name: getattr(value, name) for name in dir(value) if name.startswith('st_')}
        fields.update(st_uid=0, st_mode=value.st_mode & ~0o022)
        fields.update(overrides.get(value.st_ino, {}))
        return SimpleNamespace(**fields)
    # A module-local os proxy avoids changing pytest/pathlib's stat semantics.
    proxy = SimpleNamespace(**{name: getattr(real_os, name) for name in dir(real_os)})
    proxy.fstat = lambda fd: info(real_os.fstat(fd))
    proxy.stat = lambda *args, **kwargs: info(real_os.stat(*args, **kwargs))
    monkeypatch.setattr(builder_module(), 'os', proxy)
    return SimpleNamespace(repo=tmp_path / 'checkout-\udcff', session=session, identity=identity,
                           binary=binary, server=server, directory=directory, overrides=overrides, os=proxy)


def test_support_runtime_capture_selects_native_implementation_and_owner_server(support_native_runtime):
    module = support_runtime_api()
    fixture = support_native_runtime
    value = module._capture_launch_metadata(fixture.repo, fixture.session, fixture.identity)
    assert value['schema'] == 1
    assert bytes.fromhex(value['checkout_path_hex']) == os.fsencode(fixture.repo)
    for key, path in [('implementation', fixture.binary), ('server', fixture.server)]:
        pin = value[key]
        assert set(pin) == {'path_hex', 'sha256', 'device', 'inode', 'size', 'uid', 'mode',
                            'mtime_ns', 'ctime_ns', 'ancestors'}
        assert bytes.fromhex(pin['path_hex']) == os.fsencode(path)
        assert pin['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert pin['inode'] == path.stat().st_ino and pin['uid'] == 0
        assert [bytes.fromhex(row['path_hex']) for row in pin['ancestors']] == [
            os.fsencode(parent) for parent in reversed(path.parents)]
        assert all(set(row) == {'path_hex', 'device', 'inode', 'uid', 'mode'} for row in pin['ancestors'])
    assert module._capture_launch_metadata(fixture.repo, fixture.session, fixture.identity) == value


@pytest.fixture
def support_runtime_server_wrapper(support_native_runtime):
    fixture = support_native_runtime
    # Exact Ubuntu Wine9 wrapper bytes from the recorded server pin. Capture only:
    # never execute this script or the runtime paths named in its contents.
    raw = b'''#!/bin/sh -e

wineserver32=/usr/lib/wine/wineserver32
wineserver64=/usr/lib/wine/wineserver64

if test -x "$wineserver64"; then
    wineserver=$wineserver64
elif test -x "$wineserver32"; then
    wineserver=$wineserver32
else
    echo "error: unable to find wineserver executable." >&2
    echo "wine32 and/or wine64 must be installed." >&2
    exit 1
fi

exec $wineserver -p0 "$@"
'''
    fixture.server.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == 'a0d0ce13ed039949a30dc261cf93f4d6c4606cab5783980cd42f476dfb3b881a'
    fixture.session.owner['tools']['server']['sha256'] = digest
    return fixture


def test_support_runtime_capture_accepts_pinned_server_wrapper_without_execution(
        support_runtime_server_wrapper, monkeypatch):
    fixture = support_runtime_server_wrapper
    module = support_runtime_api()
    def refuse_execution(*args, **kwargs):
        pytest.fail('Runtime pin capture must not execute the server wrapper')
    monkeypatch.setattr(subprocess, 'run', refuse_execution)
    value = module._capture_launch_metadata(fixture.repo, fixture.session, fixture.identity)
    for role, path in [('implementation', fixture.binary), ('server', fixture.server)]:
        pin = value[role]
        assert bytes.fromhex(pin['path_hex']) == os.fsencode(path)
        assert pin['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot = module._launch_snapshot(fixture.os.stat(path))
        assert {field: pin[field] for field in snapshot} == snapshot
    assert value['server']['sha256'] == fixture.session.owner['tools']['server']['sha256']
    assert module._capture_launch_metadata(fixture.repo, fixture.session, fixture.identity) == value


@pytest.mark.parametrize('role', ['implementation', 'server'])
@pytest.mark.parametrize('failure', ['hash', 'open'])
def test_support_runtime_capture_failure_diagnostics_are_fixed_role_only(
        support_native_runtime, monkeypatch, role, failure):
    fixture = support_native_runtime
    module = support_runtime_api()
    path = fixture.binary if role == 'implementation' else fixture.server
    pin = (fixture.identity['installation']['implementation']['file'] if role == 'implementation'
           else fixture.session.owner['tools']['server'])
    if failure == 'hash':
        pin['sha256'] = '0' * 64
    else:
        original_open = fixture.os.open
        def refuse_leaf(name, *args, **kwargs):
            if name == os.fsencode(path.name):
                raise OSError(13, 'private-contents-environment-must-not-leak', str(path))
            return original_open(name, *args, **kwargs)
        monkeypatch.setattr(fixture.os, 'open', refuse_leaf)
    with pytest.raises(module.BuildError) as caught:
        module._capture_launch_metadata(fixture.repo, fixture.session, fixture.identity)
    assert str(caught.value) == f'Unsafe launch {role} runtime pin'
    assert caught.value.__suppress_context__  # Do not expose path-bearing OSError context.


@pytest.mark.parametrize('damage', ['leaf-link', 'ancestor-link', 'file-uid', 'ancestor-uid',
    'file-mode', 'ancestor-mode', 'setuid', 'setgid', 'not-executable', 'access', 'hash',
    'mtime', 'ctime', 'ancestor-policy', 'oversize', 'relative', 'dotdot', 'long-path'])
def test_support_runtime_capture_refuses_unsafe_or_changed_server_wrapper(
        support_runtime_server_wrapper, monkeypatch, damage):
    fixture = support_runtime_server_wrapper
    module = support_runtime_api()
    path = fixture.server
    pin = fixture.session.owner['tools']['server']
    if damage == 'leaf-link':
        path.unlink()
        path.symlink_to(fixture.binary)
    elif damage == 'ancestor-link':
        moved = path.parent.with_name('moved')
        path.parent.rename(moved)
        path.parent.symlink_to(moved, target_is_directory=True)
    elif damage in ('file-uid', 'ancestor-uid', 'file-mode', 'ancestor-mode', 'setuid', 'setgid'):
        target = path.parent if damage.startswith('ancestor') else path
        info = target.stat()
        fixture.overrides[info.st_ino] = (dict(st_uid=12345) if damage.endswith('uid') else
            dict(st_mode=info.st_mode | {'setuid': 0o4000, 'setgid': 0o2000}.get(damage, 0o022)))
    elif damage == 'not-executable':
        path.chmod(0o644)
    elif damage == 'access':
        original_access = fixture.os.access
        monkeypatch.setattr(fixture.os, 'access', lambda name, *args, **kwargs:
            False if name == os.fsencode(path.name) else original_access(name, *args, **kwargs))
    elif damage == 'hash':
        pin['sha256'] = '0' * 64
    elif damage in ('mtime', 'ctime', 'ancestor-policy'):
        original_read = fixture.os.read
        def changed(fd, size):
            raw = original_read(fd, size)
            if fixture.os.fstat(fd).st_ino == path.stat().st_ino:
                target = fixture.directory if damage == 'ancestor-policy' else path
                info = target.stat()
                fixture.overrides[info.st_ino] = (dict(st_mode=info.st_mode | 0o020)
                    if damage == 'ancestor-policy' else {f'st_{damage}_ns': getattr(info, f'st_{damage}_ns') + 1})
            return raw
        monkeypatch.setattr(fixture.os, 'read', changed)
    elif damage == 'oversize':
        fixture.overrides[path.stat().st_ino] = dict(st_size=64 * 1024 * 1024 + 1)
    else:
        pin['executable'] = {'relative': 'relative/wineserver', 'dotdot': str(path.parent / '..' / path.name),
                             'long-path': '/' + 'x' * 4095}[damage]
    with pytest.raises(module.BuildError) as caught:
        module._capture_launch_metadata(fixture.repo, fixture.session, fixture.identity)
    assert str(caught.value) == 'Unsafe launch server runtime pin'


@pytest.mark.parametrize('role', ['implementation', 'server'])
def test_support_runtime_capture_accepts_real_benign_ancestor_sibling_churn(
        support_runtime_server_wrapper, monkeypatch, role):
    fixture = support_runtime_server_wrapper
    module = support_runtime_api()
    path = fixture.binary if role == 'implementation' else fixture.server
    pin = (fixture.identity['installation']['implementation']['file'] if role == 'implementation'
           else fixture.session.owner['tools']['server'])
    control = module._capture_runtime_pin(pin, implementation=role == 'implementation')
    original_read = fixture.os.read
    sibling = b'benign-sibling-' + os.urandom(16).hex().encode('ascii')
    parent = os.open(fixture.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    directory_before = os.fstat(parent)
    file_before = module._launch_snapshot(fixture.os.stat(path, follow_symlinks=False))
    actions = []
    try:
        def churn_once(fd, size):
            data = original_read(fd, size)
            info = os.fstat(fd)
            assert (info.st_dev, info.st_ino) == (control['device'], control['inode'])
            if data and not actions:
                created = os.open(sibling, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  0o600, dir_fd=parent)
                try:
                    os.close(created)
                finally:
                    os.unlink(sibling, dir_fd=parent)
                actions.append('created-and-unlinked')
            return data
        with monkeypatch.context() as patch:
            patch.setattr(fixture.os, 'read', churn_once)
            captured = module._capture_runtime_pin(pin, implementation=role == 'implementation')
        directory_after = os.fstat(parent)
    finally:
        os.close(parent)
    assert actions == ['created-and-unlinked']
    assert any(getattr(directory_before, field) != getattr(directory_after, field)
               for field in ('st_size', 'st_mtime_ns', 'st_ctime_ns')), 'real sibling action must change directory metadata'
    assert all(getattr(directory_before, field) == getattr(directory_after, field)
               for field in ('st_dev', 'st_ino', 'st_uid', 'st_mode'))
    assert module._launch_snapshot(fixture.os.stat(path, follow_symlinks=False)) == file_before
    assert hashlib.sha256(path.read_bytes()).hexdigest() == captured['sha256'] == control['sha256']
    assert captured == control  # Includes the full file tuple and exact ancestor schema/pins.


@pytest.mark.parametrize('target,field', [
    *(('ancestor', field) for field in ('device', 'inode', 'uid', 'mode', 'type')),
    *(('file', field) for field in ('device', 'inode', 'uid', 'mode', 'size', 'mtime_ns', 'ctime_ns')),
])
@pytest.mark.parametrize('witness', ['descriptor', 'path'])
@pytest.mark.parametrize('role', ['implementation', 'server'])
def test_support_runtime_capture_revalidates_required_fields_on_both_witnesses(
        support_runtime_server_wrapper, monkeypatch, target, field, witness, role):
    # Drift after the real file read, not an unsafe initial acquisition. Restrict
    # the existing fixture's stat-protocol model to exactly one witness/field.
    import stat
    fixture = support_runtime_server_wrapper
    module = support_runtime_api()
    runtime = fixture.binary if role == 'implementation' else fixture.server
    pin = (fixture.identity['installation']['implementation']['file'] if role == 'implementation'
           else fixture.session.owner['tools']['server'])
    path = fixture.directory if target == 'ancestor' else runtime
    original_info = path.stat()
    original_read, original_fstat, original_stat = fixture.os.read, fixture.os.fstat, fixture.os.stat
    armed = False
    observations = []
    attributes = dict(device='st_dev', inode='st_ino', uid='st_uid', mode='st_mode',
                      size='st_size', mtime_ns='st_mtime_ns', ctime_ns='st_ctime_ns', type='st_mode')
    def drift(info, kind):
        if not armed or kind != witness or (info.st_dev, info.st_ino) != (original_info.st_dev, original_info.st_ino):
            return info
        attribute = attributes[field]
        changed = (stat.S_IFREG | stat.S_IMODE(info.st_mode) if field == 'type' else
                   info.st_mode ^ 0o100 if field == 'mode' else getattr(info, attribute) + 1)
        values = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
        values[attribute] = changed
        observations.append((kind, attribute))
        return SimpleNamespace(**values)
    def after_read(fd, size):
        nonlocal armed
        data = original_read(fd, size)
        armed = True
        return data
    monkeypatch.setattr(fixture.os, 'read', after_read)
    monkeypatch.setattr(fixture.os, 'fstat', lambda fd: drift(original_fstat(fd), 'descriptor'))
    monkeypatch.setattr(fixture.os, 'stat', lambda *args, **kwargs: drift(original_stat(*args, **kwargs), 'path'))
    with pytest.raises(module.BuildError, match='ancestor changed' if target == 'ancestor' else 'hash/identity changed'):
        module._capture_runtime_pin(pin, implementation=role == 'implementation')
    assert observations == [(witness, attributes[field])]


@pytest.mark.parametrize('replacement', ['directory', 'symlink', 'file'])
@pytest.mark.parametrize('role', ['implementation', 'server'])
def test_support_runtime_capture_refuses_real_ancestor_replacement_after_read(
        support_runtime_server_wrapper, monkeypatch, replacement, role):
    fixture = support_runtime_server_wrapper
    module = support_runtime_api()
    pin = (fixture.identity['installation']['implementation']['file'] if role == 'implementation'
           else fixture.session.owner['tools']['server'])
    original_read, original_stat = fixture.os.read, fixture.os.stat
    changed = False
    path_checks = []
    def replace_once(fd, size):
        nonlocal changed
        data = original_read(fd, size)
        if data and not changed:
            changed = True
            moved = fixture.directory.with_name('moved-during-read')
            fixture.directory.rename(moved)
            if replacement == 'directory':
                fixture.directory.mkdir()
            elif replacement == 'symlink':
                fixture.directory.symlink_to(moved, target_is_directory=True)
            else:
                fixture.directory.write_bytes(b'not a directory')
        return data
    def observe_path(name, *args, **kwargs):
        info = original_stat(name, *args, **kwargs)
        if changed and name == os.fsencode(fixture.directory.name):
            path_checks.append(kwargs.get('follow_symlinks'))
        return info
    monkeypatch.setattr(fixture.os, 'read', replace_once)
    monkeypatch.setattr(fixture.os, 'stat', observe_path)
    with pytest.raises(module.BuildError, match='ancestor changed'):
        module._capture_runtime_pin(pin, implementation=role == 'implementation')
    assert changed and path_checks == [False]  # The retained directory alone cannot prove the path.


@pytest.mark.parametrize('damage', ['script', 'machine', 'class', 'endian', 'type', 'osabi',
    'leaf-link', 'ancestor-link', 'file-uid', 'ancestor-uid', 'file-mode', 'ancestor-mode',
    'setuid', 'setgid', 'not-executable', 'access', 'hash', 'tuple', 'ancestor-policy',
    'oversize', 'growing-read', 'relative', 'dotdot', 'long-path', 'server-hash'])
def test_support_runtime_capture_refuses_unsafe_or_changed_native_pin(support_native_runtime, monkeypatch, damage):
    module = support_runtime_api()
    fixture = support_native_runtime
    path = fixture.binary
    pin = fixture.identity['installation']['implementation']['file']
    if damage in ('script', 'machine', 'class', 'endian', 'type', 'osabi'):
        raw = bytearray(path.read_bytes())
        if damage == 'script':
            raw = bytearray(b'#!/bin/sh\nexit 0\n')
        else:
            offset, value = {'machine': (18, 3), 'class': (4, 1), 'endian': (5, 2),
                             'type': (16, 1), 'osabi': (7, 9)}[damage]
            raw[offset] = value
        path.write_bytes(raw)
        pin['sha256'] = hashlib.sha256(raw).hexdigest()
    elif damage == 'leaf-link':
        path.unlink()
        path.symlink_to(fixture.server)
    elif damage == 'ancestor-link':
        moved = fixture.directory.with_name('moved')
        fixture.directory.rename(moved)
        fixture.directory.symlink_to(moved, target_is_directory=True)
    elif damage in ('file-uid', 'ancestor-uid', 'file-mode', 'ancestor-mode', 'setuid', 'setgid'):
        target = fixture.directory if damage.startswith('ancestor') else path
        info = target.stat()
        fields = dict(st_uid=12345) if damage.endswith('uid') else dict(
            st_mode=info.st_mode | {'setuid': 0o4000, 'setgid': 0o2000}.get(damage, 0o022))
        fixture.overrides[info.st_ino] = fields
    elif damage == 'not-executable':
        path.chmod(0o644)
    elif damage == 'access':
        monkeypatch.setattr(fixture.os, 'access', lambda *args, **kwargs: False)
    elif damage in ('hash', 'server-hash'):
        target = pin if damage == 'hash' else fixture.session.owner['tools']['server']
        target['sha256'] = '0' * 64
    elif damage in ('tuple', 'ancestor-policy', 'growing-read'):
        original = fixture.os.read
        def changed(fd, size):
            raw = original(fd, size)
            if damage == 'growing-read':
                return b'x' * size
            target = fixture.directory if damage == 'ancestor-policy' else path
            info = target.stat()
            fixture.overrides[info.st_ino] = (dict(st_mode=info.st_mode | 0o020) if damage == 'ancestor-policy'
                                            else dict(st_ctime_ns=info.st_ctime_ns + 1))
            return raw
        monkeypatch.setattr(fixture.os, 'read', changed)
    elif damage == 'oversize':
        fixture.overrides[path.stat().st_ino] = dict(st_size=64 * 1024 * 1024 + 1)
    else:
        pin['executable'] = {'relative': 'relative/wine64', 'dotdot': str(path.parent / '..' / path.name),
                             'long-path': '/' + 'x' * 4095}[damage]
    with pytest.raises((module.BuildError, OSError)):
        module._capture_launch_metadata(fixture.repo, fixture.session, fixture.identity)


def test_support_runtime_real_untrusted_ancestry_is_not_admitted(tmp_path):
    module = support_runtime_api()
    path = tmp_path / 'runtime'
    path.write_bytes(b'#!/bin/sh\nexit 99\n')
    path.chmod(0o755)
    pin = dict(executable=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    session = SimpleNamespace(owner=dict(tools=dict(server=pin)))
    identity = dict(installation=dict(implementation=dict(file=pin)))
    with pytest.raises(module.BuildError, match='[Tt]rust|[Uu]nsafe'):
        module._capture_launch_metadata(tmp_path, session, identity)


@pytest.mark.parametrize('role', ['implementation', 'server'])
def test_support_runtime_capture_never_reads_more_than_64_mib(support_native_runtime, monkeypatch, role):
    module = support_runtime_api()
    fixture = support_native_runtime
    bytes_read = 0
    def endless_read(fd, size):
        nonlocal bytes_read
        bytes_read += size
        return b'x' * size
    monkeypatch.setattr(fixture.os, 'read', endless_read)
    pin = (fixture.identity['installation']['implementation']['file'] if role == 'implementation'
           else fixture.session.owner['tools']['server'])
    with pytest.raises(module.BuildError):
        module._capture_runtime_pin(pin, implementation=role == 'implementation')
    assert bytes_read <= 64 * 1024 * 1024


@pytest.mark.parametrize('compiler,standard', [('cc', 'c11'), ('c++', 'c++17')])
def test_support_runtime_header_is_deterministic_raw_bytes_without_build_id(support_native_runtime, tmp_path, compiler, standard):
    module = support_runtime_api()
    fixture = support_native_runtime
    metadata = module._capture_launch_metadata(fixture.repo, fixture.session, fixture.identity)
    header = module._render_launch_header(metadata)
    assert header == module._render_launch_header(json.loads(json.dumps(metadata, sort_keys=True)))
    assert b'SRPT_BUILD_ID' not in header and b'\xff' not in header
    (tmp_path / 'srpt_launch_config.h').write_bytes(header)
    def expected_array(name, path):
        return 'static const unsigned char ' + name + '[] = {' + ','.join(
            str(byte) for byte in os.fsencode(path) + b'\0') + '};\n'
    source = '''#include "srpt_launch_config.h"
#include <string.h>
''' + expected_array('checkout', fixture.repo) + expected_array('implementation', fixture.binary) + expected_array(
        'server', fixture.server) + '''
int main(void) {
    return srpt_launch_schema != 1 || srpt_launch_implementation.uid != 0 ||
        srpt_launch_server.size == 0 || srpt_launch_implementation.ancestor_count == 0 ||
        sizeof(srpt_launch_checkout) != sizeof(checkout) ||
        sizeof(srpt_launch_implementation_path) != sizeof(implementation) ||
        sizeof(srpt_launch_server_path) != sizeof(server) ||
        memcmp(srpt_launch_checkout, checkout, sizeof(checkout)) ||
        memcmp(srpt_launch_implementation.path, implementation, sizeof(implementation)) ||
        memcmp(srpt_launch_server.path, server, sizeof(server)) ||
        memcmp(srpt_launch_implementation.sha256, srpt_launch_server.sha256, 32);
}
'''
    executable = tmp_path / 'header-model'
    result = subprocess.run([compiler, f'-std={standard}', '-Wall', '-Wextra', '-Werror', '-I', str(tmp_path),
                             '-x', 'c' if compiler == 'cc' else 'c++', '-', '-o', str(executable)],
                            input=source, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(executable)], capture_output=True, timeout=10)
    assert result.returncode == 0 and not result.stdout and not result.stderr


def test_support_runtime_builder_seals_private_header_and_all_launch_values(support_builder_fixture, monkeypatch):
    module = support_runtime_api()
    fixture, session = support_builder_fixture
    compile_fixed = module._compile
    headers = []
    def inspect(args, stage):
        if '-DSRPT_BUILD_ID_BYTES=' in ' '.join(args):
            header = stage / 'srpt_launch_config.h'
            assert header.is_file() and header.stat().st_mode & 0o777 == 0o600
            assert str(stage) in args and args[args.index(str(stage)) - 1] == '-I'
            headers.append(header.read_bytes())
        compile_fixed(args, stage)
    monkeypatch.setattr(module, '_compile', inspect)
    manifest = module.build_test_support(fixture.root, session)
    assert len(headers) == 2 and headers[0] == headers[1]
    assert manifest['toolchain']['launch'] == fixture.launch_metadata
    assert manifest['toolchain']['launch_header_sha256'] == hashlib.sha256(headers[0]).hexdigest()
    assert set(manifest['toolchain']) == {'identity', 'inputs', 'launch', 'launch_header_sha256'}
    assert manifest['abi'] == 2  # Support-only migration; production remains ABI1.
    output = fixture.root / 'build/wine-publication-tests'
    assert {str(path.relative_to(output)) for path in output.rglob('*') if path.is_file()} == {
        *SUPPORT_PAIR, SUPPORT_COPY, 'build.json'}
    assert not list((fixture.root / 'build').glob('.wine-publication-tests-*'))


@pytest.mark.parametrize('field', ['checkout_path_hex', 'path_hex', 'sha256', 'device', 'inode', 'size',
    'uid', 'mode', 'mtime_ns', 'ctime_ns', 'ancestor-path_hex', 'ancestor-device', 'ancestor-inode',
    'ancestor-uid', 'ancestor-mode', 'server-inode'])
def test_support_runtime_every_generated_value_changes_build_id(support_builder_fixture, field):
    module = support_runtime_api()
    fixture, session = support_builder_fixture
    old = module.build_test_support(fixture.root, session)
    value = fixture.launch_metadata
    key = field
    if field.startswith('ancestor-'):
        value = value['implementation']['ancestors'][0]
        key = field.removeprefix('ancestor-')
    elif field == 'server-inode':
        value, key = value['server'], 'inode'
    elif field != 'checkout_path_hex':
        value = value['implementation']
    value[key] = value[key] + ('61' if key.endswith('_hex') else 1) if key != 'sha256' else '34' * 32
    new = module.build_test_support(fixture.root, session)
    assert new['build_id'] != old['build_id']
    assert new['toolchain']['launch_header_sha256'] != old['toolchain']['launch_header_sha256']


@pytest.mark.parametrize('damage', ['pin-drift', 'header-drift', 'capture-refusal'])
def test_support_runtime_changed_during_build_preserves_prior_pair(support_builder_fixture, monkeypatch, damage):
    module = support_runtime_api()
    fixture, session = support_builder_fixture
    previous = module.build_test_support(fixture.root, session)
    original = module._compile
    def mutate(args, stage):
        original(args, stage)
        if '--builtin' in args:
            if damage == 'pin-drift':
                fixture.launch_metadata['implementation']['ctime_ns'] += 1
            elif damage == 'header-drift':
                (stage / 'srpt_launch_config.h').write_bytes(b'changed header')
            else:
                def refuse(*args):
                    raise module.BuildError('launch runtime changed')
                monkeypatch.setattr(module, '_capture_launch_metadata', refuse)
    monkeypatch.setattr(module, '_compile', mutate)
    with pytest.raises(module.BuildError, match='[Ll]aunch'):
        module.build_test_support(fixture.root, session)
    output = fixture.root / 'build/wine-publication-tests'
    assert module._recognized_test_output(output)[1] == previous
    assert not list((fixture.root / 'build').glob('.wine-publication-tests-*'))


def test_support_runtime_actual_gnu_spawn_prerequisites_and_unchanged_parent(tmp_path):
    # A prerequisite measurement, NOT a copy of the future support launch entry
    # and NOT installed Wine feasibility. Both programs are ordinary native ELFs.
    child_source = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
extern char **environ;
int main(int argc, char **argv) {
    assert(argc == 2);
    char cwd[4096], byte;
    assert(getcwd(cwd, sizeof(cwd)) && !strcmp(cwd, argv[1]));
    struct stat actual, expected;
    assert(fstat(0, &actual) == 0 && stat("/dev/null", &expected) == 0);
    assert(S_ISCHR(actual.st_mode) && actual.st_rdev == expected.st_rdev);
    assert(read(0, &byte, 1) == 0);
    for (int fd = 3; fd < 512; ++fd) {
        errno = 0; assert(fcntl(fd, F_GETFD) == -1 && errno == EBADF);
    }
    sigset_t mask;
    assert(sigprocmask(SIG_SETMASK, NULL, &mask) == 0);
    for (int sig = 1; sig < NSIG; ++sig) assert(sigismember(&mask, sig) == 0);
    const int signals[] = {SIGUSR1, SIGUSR2, SIGPIPE};
    for (unsigned i = 0; i < sizeof(signals)/sizeof(signals[0]); ++i) {
        struct sigaction action;
        assert(sigaction(signals[i], NULL, &action) == 0 && action.sa_handler == SIG_DFL);
    }
    assert(getpgrp() == getpid());
    assert(environ[0] && !strcmp(environ[0], "SRPT_NATIVE_PREREQUISITE=only") && !environ[1]);
    assert(puts("native child stdout retained") >= 0 && fflush(stdout) == 0);
    assert(fputs("native child stderr retained\n", stderr) >= 0 && fflush(stderr) == 0);
    assert(raise(SIGSTOP) == 0); /* Driver observes closure while leader is alive. */
    return 0;
}
'''
    driver_source = r'''
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>
static pid_t child;
static void failed(int line) {
    fprintf(stderr, "native prerequisite failed at line %d, errno %d\n", line, errno);
    if (child > 0) {
        kill(-child, SIGKILL);
        while (waitpid(child, NULL, 0) < 0 && errno == EINTR) {}
    }
    exit(1);
}
#define CHECK(value) do { if (!(value)) failed(__LINE__); } while (0)
static unsigned read_umask(void) {
    FILE *stream = fopen("/proc/self/status", "r");
    CHECK(stream != NULL);
    char line[4096]; unsigned value = 0; int found = 0;
    while (fgets(line, sizeof(line), stream))
        if (sscanf(line, "Umask:\t%o", &value) == 1) { found = 1; break; }
    CHECK(fclose(stream) == 0 && found);
    return value;
}
int main(int argc, char **argv) {
    CHECK(argc == 3);
    char before_cwd[4096], after_cwd[4096];
    CHECK(getcwd(before_cwd, sizeof(before_cwd)) != NULL);
    unsigned before_umask = read_umask();
    const char *marker = getenv("SRPT_PARENT_MARKER");
    CHECK(marker && !strcmp(marker, "unchanged"));
    CHECK(signal(SIGUSR1, SIG_IGN) != SIG_ERR && signal(SIGPIPE, SIG_IGN) != SIG_ERR);
    sigset_t blocked, empty, defaults, after_mask;
    CHECK(sigemptyset(&blocked) == 0 && sigaddset(&blocked, SIGUSR2) == 0);
    CHECK(sigprocmask(SIG_BLOCK, &blocked, NULL) == 0);
    CHECK(sigemptyset(&empty) == 0 && sigfillset(&defaults) == 0);
    int cwd = open(argv[2], O_RDONLY | O_DIRECTORY); CHECK(cwd >= 3 && cwd < 512);
    int sentinel[2], server[2];
    CHECK(pipe(sentinel) == 0 && socketpair(AF_UNIX, SOCK_STREAM, 0, server) == 0);
    for (unsigned i = 0; i < 2; ++i) {
        CHECK(sentinel[i] >= 3 && sentinel[i] < 512 && server[i] >= 3 && server[i] < 512);
        CHECK(fcntl(sentinel[i], F_GETFD) == 0 && fcntl(server[i], F_GETFD) == 0);
    }
    posix_spawn_file_actions_t actions;
    posix_spawnattr_t attributes;
    CHECK(posix_spawn_file_actions_init(&actions) == 0);
    CHECK(posix_spawn_file_actions_addopen(&actions, 0, "/dev/null", O_RDONLY, 0) == 0);
    CHECK(posix_spawn_file_actions_addfchdir_np(&actions, cwd) == 0);
    CHECK(posix_spawn_file_actions_addclosefrom_np(&actions, 3) == 0);
    CHECK(posix_spawnattr_init(&attributes) == 0);
    CHECK(posix_spawnattr_setsigmask(&attributes, &empty) == 0);
    CHECK(posix_spawnattr_setsigdefault(&attributes, &defaults) == 0);
    CHECK(posix_spawnattr_setpgroup(&attributes, 0) == 0);
    CHECK(posix_spawnattr_setflags(&attributes,
        POSIX_SPAWN_SETSIGMASK | POSIX_SPAWN_SETSIGDEF | POSIX_SPAWN_SETPGROUP) == 0);
    char *child_argv[] = {argv[1], argv[2], NULL};
    char *child_env[] = {"SRPT_NATIVE_PREREQUISITE=only", NULL};
    CHECK(posix_spawn(&child, argv[1], &actions, &attributes, child_argv, child_env) == 0);
    CHECK(posix_spawnattr_destroy(&attributes) == 0);
    CHECK(posix_spawn_file_actions_destroy(&actions) == 0);
    CHECK(close(server[1]) == 0);
    int status;
    CHECK(waitpid(child, &status, WUNTRACED) == child && WIFSTOPPED(status) && WSTOPSIG(status) == SIGSTOP);
    struct pollfd connection = {server[0], POLLIN | POLLHUP, 0};
    CHECK(poll(&connection, 1, 1000) == 1);
    char byte; CHECK(read(server[0], &byte, 1) == 0); /* No leaked server connection. */
    CHECK(getpgid(child) == child && getpgrp() != child);
    CHECK(kill(-child, SIGCONT) == 0);
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    child = 0;
    CHECK(close(cwd) == 0 && close(server[0]) == 0);
    CHECK(close(sentinel[0]) == 0 && close(sentinel[1]) == 0);
    CHECK(getcwd(after_cwd, sizeof(after_cwd)) && !strcmp(before_cwd, after_cwd));
    CHECK(read_umask() == before_umask && !strcmp(getenv("SRPT_PARENT_MARKER"), "unchanged"));
    CHECK(sigprocmask(SIG_SETMASK, NULL, &after_mask) == 0 && sigismember(&after_mask, SIGUSR2) == 1);
    struct sigaction action;
    CHECK(sigaction(SIGUSR1, NULL, &action) == 0 && action.sa_handler == SIG_IGN);
    CHECK(sigaction(SIGPIPE, NULL, &action) == 0 && action.sa_handler == SIG_IGN);
    return 0;
}
'''
    parent_before = (dict(os.environ), os.getcwdb(), next(
        line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('Umask:')))
    for name, source in [('child', child_source), ('driver', driver_source)]:
        result = subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                                 '-x', 'c', '-', '-o', str(tmp_path / name)], input=source,
                                text=True, capture_output=True, timeout=60)
        assert result.returncode == 0, result.stderr
        assert (tmp_path / name).read_bytes()[:7] == b'\x7fELF\x02\x01\x01'
    cwd = tmp_path / 'exact-cwd-\udcff'
    cwd.mkdir()
    result = subprocess.run([str(tmp_path / 'driver'), str(tmp_path / 'child'), str(cwd)],
                            env=dict(os.environ, SRPT_PARENT_MARKER='unchanged'),
                            input=b'stdin must not reach the child', capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == b'native child stdout retained\n'
    assert result.stderr == b'native child stderr retained\n'
    parent_after = (dict(os.environ), os.getcwdb(), next(
        line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('Umask:')))
    assert parent_after == parent_before
