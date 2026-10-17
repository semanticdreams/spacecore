"""Publication build/provisioning fixtures: no real Wine, APT or compiler build."""
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
