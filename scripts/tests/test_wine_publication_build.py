"""Host publication tests: inert Wine tools plus real host-only ABI/SO checks."""
import ctypes
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))


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
        header = path / 'include/wine/wine/unixlib.h'
        header.parent.mkdir(parents=True)
        header.write_text('/* inert Wine9 header fixture */\n')
        self.files['libwine-dev:amd64'] = [str(header)]
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


@pytest.mark.parametrize('damage', ['header', 'tool', 'tool-version', 'header-version', 'runtime', 'logical-pair'])
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
        alias = fixture.bin / 'winegcc-stable'
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
    assert summary['file_count'] == 1001 and len(summary['inventory_sha256']) == 64
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


def inventory_refusal(fixture, monkeypatch):
    module = fixture.resolver()
    fixture.save()
    catalog = module._catalog(fixture.root)
    queries = []
    original_run = module._run
    def observe_query(repo, args):
        queries.append(list(args))
        return original_run(repo, args)
    monkeypatch.setattr(module, '_run', observe_query)
    # Observe the same native-candidate filesystem operations as the original
    # filter/resolve comprehension. Formatting must not add even a re-stat.
    events = []
    for name in ('stat', 'lstat', 'open', 'readlink'):
        original = getattr(os, name)
        def observe(path, *args, _name=name, _original=original, **kwargs):
            if not isinstance(path, int) and Path(path).name == 'wine64':
                events.append((_name, os.fspath(path), args, kwargs))
            return _original(path, *args, **kwargs)
        monkeypatch.setattr(os, name, observe)
    original_open = Path.open
    def observe_open(path, *args, **kwargs):
        if path.name == 'wine64':
            events.append(('Path.open', str(path), args, kwargs))
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', observe_open)
    paths = fixture.files['wine64:amd64']
    {str(Path(path).resolve()) for path in paths if Path(path).name == 'wine64' and Path(path).is_file()}
    expected = list(events)
    events.clear()
    with pytest.raises(module.ToolchainError) as error:
        module._selection(fixture.root, catalog)
    assert events == expected, 'diagnostics must use prior observations without extra filesystem probes'
    calls = fixture.calls()
    expected_queries = [
        ('dpkg-query', ['-S', str(fixture.bin / 'wine-stable')]),
        ('dpkg-query', ['-W', '-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\t${Architecture}\n', 'wine:all']),
        ('dpkg-query', ['-W', '-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\t${Architecture}\n', 'wine64:amd64']),
        ('dpkg-query', ['-L', 'wine64:amd64'])]
    assert [(Path(call[0]).name, call[1:]) for call in calls] == expected_queries
    assert [(Path(call[0]).name, call[1:]) for call in queries] == expected_queries
    assert not [call for call in calls if Path(call[0]).name in ('wine64', 'wine-stable')]
    return str(error.value)


@pytest.mark.parametrize('case,listed,regular,unique', [
    ('zero-listed', 0, 0, 0), ('zero-regular', 2, 0, 0), ('multiple', 4, 3, 2)])
def test_native_inventory_diagnostic_counts_without_extra_probes(regular_launcher_inventory, monkeypatch,
                                                                 case, listed, regular, unique):
    fixture = regular_launcher_inventory
    ignored = fixture.lib / 'not-wine64'  # Must not be probed or counted.
    missing = fixture.lib / 'missing/wine64'
    directory = fixture.lib / 'directory/wine64'
    directory.mkdir(parents=True)
    paths = [ignored]
    if case == 'zero-regular':
        paths += [missing, directory]
    elif case == 'multiple':
        second = fixture.lib / 'second/wine64'
        second.parent.mkdir()
        shutil.copy2(fixture.lib / 'wine64', second)
        alias = fixture.lib / 'alias/wine64'
        alias.parent.mkdir()
        alias.symlink_to(fixture.lib / 'wine64')
        paths += [fixture.lib / 'wine64', second, alias, directory]
    fixture.files['wine64:amd64'] = [str(path) for path in paths]
    message = inventory_refusal(fixture, monkeypatch)
    prefix = (f'Missing or ambiguous native Wine64 implementation: package=wine64:amd64 '
              f'listed={listed} regular={regular} unique-resolved={unique} ')
    assert message.startswith(prefix)
    assert 'observations-truncated=false' in message
    assert 'message-truncated=' in message and message.index('message-truncated=') < message.index('observations=[')
    assert message.count('is-file=true') == regular and message.count('is-file=false') == listed - regular
    assert len(message.encode('ascii')) <= 480
    if case == 'zero-listed':
        assert 'message-truncated=false' in message and 'observations=[]' in message


def test_native_inventory_diagnostic_escapes_caps_and_flags_observations(regular_launcher_inventory, monkeypatch):
    fixture = regular_launcher_inventory
    paths = []
    for index in range(6):
        path = fixture.lib / ('x' * 140 + f'{index}\t\x1b\x7f\u202e') / 'wine64'
        path.parent.mkdir()
        shutil.copy2(fixture.lib / 'wine64', path)
        paths.append(path)
    fixture.files['wine64:amd64'] = [str(path) for path in paths]
    message = inventory_refusal(fixture, monkeypatch)
    assert 'package=wine64:amd64 listed=6 regular=6 unique-resolved=6 ' in message
    assert 'observations-truncated=true' in message and 'message-truncated=true' in message
    assert message.count('is-file=true') == 4 and 'is-file=false' not in message
    assert all(escape in message for escape in ('\\t', '\\u001b', '\\u007f', '\\u202e'))
    assert all(' ' <= char < '\x7f' for char in message) and len(message.encode('ascii')) <= 480
    assert all(str(path) not in message for path in paths), 'do not dump complete long candidate paths'


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
BUILD_INPUTS = ('src/record_publication_wine_abi.h', 'scripts/wine/record_publication_bridge.c',
                'scripts/wine/record_publication_unix_entry.cpp', 'scripts/wine/build_publication.py')


def builder_module():
    assert (ROOT / BUILD_INPUTS[-1]).is_file(), 'fixed publication builder is missing'
    return importlib.import_module('wine.build_publication')


@pytest.mark.parametrize('compiler,standard', [('cc', 'c11'), ('c++', 'c++17')])
def test_publication_identity_layout_compiles_in_c_and_cpp(tmp_path, compiler, standard):
    header = ROOT / BUILD_INPUTS[0]
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
ASSERT(SRP_REQUIRED_FEATURES == SRP_FEATURE_IDENTITY, "identity only");
int main(void) { return 0; }
'''
    result = subprocess.run([compiler, '-x', 'c++' if compiler == 'c++' else 'c', f'-std={standard}',
                             '-Wall', '-Werror', '-I', str(header.parent), '-o', str(tmp_path / 'layout'), '-'],
                            input=source, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


class Identity(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('abi', ctypes.c_uint32),
                ('challenge', ctypes.c_uint64), ('echo', ctypes.c_uint64),
                ('pe_build_id', ctypes.c_uint8 * 32), ('unix_build_id', ctypes.c_uint8 * 32),
                ('module_device', ctypes.c_uint64), ('module_inode', ctypes.c_uint64),
                ('architecture', ctypes.c_uint32), ('features', ctypes.c_uint32)]


def test_publication_real_host_so_identity_and_explicit_unsupported_entry(tmp_path):
    source = ROOT / BUILD_INPUTS[2]
    assert source.is_file(), 'Unix identity entry is missing'
    expected = bytes(range(32))
    definition = '-DSRP_BUILD_ID_BYTES={' + ','.join(hex(byte) for byte in expected) + '}'
    output = tmp_path / 'identity.so'
    result = subprocess.run(['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared',
                             '-fvisibility=hidden', '-static-libgcc', '-static-libstdc++',
                             '-I', str(ROOT / 'src'), definition, str(source),
                             '-o', str(output), '-ldl'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'libc.so.6' in builder_module()._elf_dependencies(output.read_bytes())
    library = ctypes.CDLL(str(output))  # Host ELF only; never Wine or PE.
    exported = (ctypes.c_uint8 * 32).in_dll(library, 'SpaceRecordPublicationUnixBuildId')
    assert bytes(exported) == expected
    entries = (ctypes.c_void_p * 2).in_dll(library, '__wine_unix_call_funcs')
    call = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p)
    identify, unsupported = (call(entry) for entry in entries)
    value = Identity(size=112, abi=1, challenge=0x1122334455667788)
    value.pe_build_id[:] = bytes([0xA5]) * 32
    assert identify(ctypes.byref(value)) == 0
    info = output.stat()
    assert value.echo == value.challenge and value.architecture == 0x8664 and value.features == 1
    assert (value.module_device, value.module_inode) == (info.st_dev, info.st_ino)
    assert bytes(value.pe_build_id) == bytes([0xA5]) * 32 and bytes(value.unix_build_id) == expected
    assert unsupported(ctypes.byref(value)) == ctypes.c_int32(0xC00000BB).value
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
    windows = Path(fixture.files['libwine-dev:amd64'][0]).parents[1] / 'windows'
    windows.mkdir()
    for name in ['winternl.h', 'windef.h', 'winbase.h']:
        path = windows / name
        path.write_text('/* inert matched header: NOT a compilation/ABI proof */\n')
        fixture.files['libwine-dev:amd64'].append(str(path))
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
    for path in [fixture.root / BUILD_INPUTS[0], Path(fixture.files['libwine-dev:amd64'][0]), fixture.lib / 'winebuild']:
        with path.open('a') as stream:
            stream.write('\n# changed identity input\n' if path.name == 'winebuild' else '\n/* changed identity input */\n')
        next_manifest = module.build_publication(fixture.root, session)
        assert next_manifest['build_id'] != first['build_id']
        first = next_manifest


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
    result = subprocess.run([sys.executable, str(fixture.root / BUILD_INPUTS[-1])],
                            env=dict(fixture.env, SPACE_WINE_SESSION_ID=session.id),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary['version'] == 1 and summary['abi'] == 1 and summary['files'] == list(PAIR)
    assert not [call for call in fixture.calls() if Path(call[0]).name in ('wine64', 'wine-stable')]


@pytest.mark.parametrize('arguments,session_id', [(['extra'], None), ([], None), ([], 'not-a-session')])
def test_publication_builder_cli_refuses_arguments_or_missing_owned_handoff(tmp_path, arguments, session_id):
    script = ROOT / BUILD_INPUTS[-1]
    assert script.is_file(), 'fixed publication builder is missing'
    env = dict(os.environ)
    env.pop('SPACE_WINE_SESSION_ID', None)
    if session_id is not None:
        env['SPACE_WINE_SESSION_ID'] = session_id
    result = subprocess.run([sys.executable, str(script), *arguments], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and 'refused' in result.stderr.lower()
