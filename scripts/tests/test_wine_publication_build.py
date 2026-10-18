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
    owner = dict(version=3, id=identifier, nonce='b' * 32, repo=str(fixture.root), uid=os.geteuid(),
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


def test_publication_builder_cli_loads_existing_immutable_session_without_wine(publication_fixture):
    fixture, session = publication_fixture
    result = subprocess.run([sys.executable, str(fixture.root / BUILDER_SOURCE)],
                            env=dict(fixture.env, SPACE_WINE_SESSION_ID=session.id),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary['version'] == 1 and summary['abi'] == 1 and summary['files'] == list(PAIR)
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
