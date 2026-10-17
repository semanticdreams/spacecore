"""Owned-prefix tests: tools are host fixtures, never Wine/PE execution."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

import pytest

from test_windows_wine_runtime import Fixture

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_POLICY = [
    (r'HKLM\Software\Microsoft\Windows NT\CurrentVersion\AeDebug', 'Debugger', 'REG_SZ', 'winedbg --auto %ld %ld'),
    (r'HKLM\Software\Microsoft\Windows NT\CurrentVersion\AeDebug', 'Auto', 'REG_SZ', '1'),
    (r'HKCU\Software\Wine\WineDbg', 'ShowCrashDialog', 'REG_DWORD', '0'),
]


def setup_argv(session):
    reg = r'C:\windows\system32\reg.exe'
    winepath = r'C:\windows\system32\winepath.exe'
    windows_tmp = 'Q:' + str(session.tmp).replace('/', '\\')
    return ([[winepath, '-w', str(session.tmp)], [winepath, '-u', windows_tmp]] +
            [[reg, 'add', key, '/v', name, '/t', typ, '/d', value, '/f', '/reg:64']
             for key, name, typ, value in EXPECTED_POLICY] +
            [[reg, 'query', key, '/v', name, '/reg:64'] for key, name, _, _ in EXPECTED_POLICY])


@pytest.fixture
def runtime(tmp_path):
    return Fixture(tmp_path)


def test_owned_roots_are_private_isolated_and_override_inherited_data(runtime, monkeypatch):
    module = prefix_module()
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    inherited = runtime.bin.parent / 'unowned-data'
    inherited.mkdir()
    sentinel = inherited / 'sentinel'
    sentinel.write_text('leave old shared data alone')
    for key in ['XDG_DATA_HOME', 'XDG_CACHE_HOME', 'TMPDIR', 'TEMP', 'TMP']:
        monkeypatch.setenv(key, str(inherited))
    first, second = module.create_session(runtime.root), module.create_session(runtime.root)
    for session in [first, second]:
        assert all((session.directory / name).is_dir() for name in ['data', 'cache', 'tmp'])
        for name in ['data', 'cache', 'tmp']:
            path = session.directory / name
            assert path.stat().st_mode & 0o777 == 0o700
            assert session.owner['roots'][name] == [path.stat().st_dev, path.stat().st_ino]
        env = session.environment()
        assert env['XDG_DATA_HOME'] == str(session.directory / 'data')
        assert env['XDG_CACHE_HOME'] == str(session.directory / 'cache')
        assert env['TMPDIR'] == str(session.directory / 'tmp')
        assert env['TEMP'] == env['TMP'] == r'C:\windows\temp'
    assert first.binding()['roots'] != second.binding()['roots']
    assert sentinel.read_text() == 'leave old shared data alone'


def test_stale_ended_owner_is_rejected_without_adopting_or_cleaning_it(runtime, monkeypatch):
    module = prefix_module()
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    session = module.create_session(runtime.root)
    assert module.stop_session(session, end=True).ok
    owner_file = session.directory / 'owner.json'
    owner = json.loads(owner_file.read_text())
    owner['version'] = 2
    owner['bounds'].pop('setup')
    for name in ['data', 'cache', 'tmp']:
        owner['roots'].pop(name)
    owner_file.write_text(json.dumps(owner))
    before = runtime.calls()
    with pytest.raises(ValueError, match='Invalid session ownership'):
        module.load_session(runtime.root, session.id)
    assert runtime.calls() == before and session.prefix.is_dir()


def test_owned_setup_precedes_probe_and_binds_receipt_and_native_tmp(runtime):
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stderr
    module, session = load_owned(runtime)
    calls = [call['wine'] for call in runtime.calls() if call.get('utility')]
    winepath = r'C:\windows\system32\winepath.exe'
    reg = r'C:\windows\system32\reg.exe'
    windows_tmp = 'Q:' + str(session.directory / 'tmp').replace('/', '\\')
    assert calls[:2] == [[winepath, '-w', str(session.directory / 'tmp')], [winepath, '-u', windows_tmp]]
    assert module.CRASH_POLICY == EXPECTED_POLICY
    assert calls == setup_argv(session)
    assert [call['wine'] for call in runtime.calls() if 'wine' in call] == [
        ['wineboot.exe', '--init'], *setup_argv(session), [str(runtime.overlay / 'process-prng-probe.exe')]]
    utilities = [call for call in runtime.calls() if call.get('utility')]
    assert all(call['regular_streams'] for call in utilities)
    for index, call in enumerate(utilities):
        env = call['env']
        assert env['TEMP'] == env['TMP'] == (r'C:\windows\temp' if index < 2 else windows_tmp)
        assert env['TMPDIR'] == str(session.tmp)
        assert env['WINEPREFIX'] == str(session.prefix) and env['WINEARCH'] == 'win64'
        assert env['WINESERVER'] == session.owner['tools']['server']['executable']
        assert env['WINEDLLOVERRIDES'] == 'winepath.exe=b;reg.exe=b'
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    assert receipt['ownedSession'] == session.binding()
    assert session.binding()['crash_policy']['verified']
    assert session.state()['generation'] == 10
    assert runtime.run('test-windows-under-wine.sh').returncode == 0
    app = [call for call in runtime.calls() if 'wine' in call][-1]
    assert app['env']['TEMP'] == app['env']['TMP'] == windows_tmp
    assert app['env']['TMPDIR'] == str(session.directory / 'tmp')
    assert app['env']['XDG_DATA_HOME'] == str(session.directory / 'data')
    assert session.state()['generation'] == 11


@pytest.mark.parametrize('name', ['Debugger', 'Auto', 'ShowCrashDialog'])
@pytest.mark.parametrize('damage', ['add-exit', 'query-exit', 'type', 'value'])
def test_fixed_registry_setup_failure_never_admits_and_cleans_owned_prefix(runtime, name, damage):
    runtime.package()
    runtime.env['FIXTURE_REG_NAME'] = name
    if damage in ['add-exit', 'query-exit']:
        runtime.env['FIXTURE_REG_OPERATION'] = damage.split('-')[0]
        runtime.env['FIXTURE_REG_EXIT'] = '23'
    else:
        runtime.env['FIXTURE_REG_' + damage.upper()] = 'unexpected'
    result = runtime.prepare([0])
    assert result.returncode != 0
    assert not (runtime.overlay / 'admission.json').exists()
    assert not [call for call in runtime.calls() if 'wine' in call and call['wine'][0].endswith('process-prng-probe.exe')]
    assert [call['server'] for call in runtime.calls() if 'server' in call][-2:] == [['-k'], ['-w']]
    owner_file = next((runtime.root / 'build/wine/sessions').glob('*/owner.json'))
    session = prefix_module().load_session(runtime.root, owner_file.parent.name)
    state = session.state()
    assert state['ended'] and not state['authorized']
    assert not session.setup()['policy_verified']
    assert state['generation'] == 1 + len([call for call in runtime.calls() if call.get('utility')])


@pytest.mark.parametrize('setting', ['FIXTURE_BAD_WINEPATH', 'FIXTURE_BAD_ROUNDTRIP'])
def test_unverified_owned_windows_path_never_reaches_registry_or_probe(runtime, setting):
    runtime.package()
    runtime.env[setting] = '1'
    result = runtime.prepare([0])
    assert result.returncode != 0
    assert not (runtime.overlay / 'admission.json').exists()
    assert not [call for call in runtime.calls() if call.get('utility') and call['wine'][0].endswith('reg.exe')]
    assert [call['server'] for call in runtime.calls() if 'server' in call] == [['-k'], ['-w']]


@pytest.mark.parametrize('damage', ['missing', 'json', 'relative', 'roundtrip', 'flag'])
def test_setup_observation_damage_blocks_launch_not_immutable_owned_cleanup(runtime, monkeypatch, damage):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    module, session = load_owned(runtime)
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    state = session.state()
    state.update(generation=state['generation'] + 1, stopped_generation=None)
    session.save(state)
    path = session.directory / 'setup.json'
    if damage == 'missing':
        path.unlink()
    elif damage == 'json':
        path.write_text('broken observations')
    else:
        setup = json.loads(path.read_text())
        key, value = {'relative': ('windows_tmp', 'relative'), 'roundtrip': ('roundtrip_tmp', '/foreign'),
                      'flag': ('policy_verified', 'yes')}[damage]
        setup[key] = value
        path.write_text(json.dumps(setup))
    before = runtime.calls()
    with pytest.raises((OSError, ValueError)):
        module.initialize(session)
    assert runtime.calls() == before
    result = module.stop_session(session, end=True)
    assert result.ok, result.errors
    assert [call['server'] for call in runtime.calls()[len(before):] if 'server' in call] == [['-k'], ['-w']]
    assert session.state()['ended'] and not session.state()['authorized']


@pytest.mark.parametrize('name', ['data', 'cache', 'tmp'])
def test_owned_root_substitution_refuses_before_wine_launch(runtime, name):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    module, session = load_owned(runtime)
    path = session.directory / name
    path.rename(path.with_name(name + '-preserved'))
    path.mkdir(mode=0o700)
    before = runtime.calls()
    with pytest.raises(ValueError, match='Substituted session root'):
        module.initialize(session)
    assert runtime.calls() == before


def test_one_owned_prefix_for_probe_app_cleanup(runtime):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    assert runtime.run('test-windows-under-wine.sh').returncode == 0
    calls = [c for c in runtime.calls() if 'wine' in c or 'server' in c]
    prefixes = {c['env']['WINEPREFIX'] for c in calls}
    assert len(prefixes) == 1
    prefix = Path(prefixes.pop())
    assert prefix.parent.parent == runtime.root / 'build/wine/sessions'
    assert prefix.name == 'prefix'
    assert all(c['env']['WINEARCH'] == 'win64' for c in calls)
    assert all(c['env']['WINESERVER'] == str(runtime.bin / 'wineserver') for c in calls)
    assert [c['server'] for c in calls if 'server' in c] == [['-k'], ['-w'], ['-k'], ['-w']]
    assert [c['wine'] for c in calls if 'wine' in c][0] == ['wineboot.exe', '--init']
    assert not Path(runtime.env['WINEPREFIX']).exists()


def test_cleanup_failure_is_failure_waits_and_can_retry(runtime):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    runtime.env['FIXTURE_STOP_CODE'] = '37'
    result = runtime.run('test-windows-under-wine.sh')
    assert result.returncode != 0
    assert '37' in result.stderr
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    state = runtime.root / 'build/wine/sessions' / receipt['ownedSession']['id'] / 'state.json'
    assert not json.loads(state.read_text())['authorized']
    assert [c['server'] for c in runtime.calls() if 'server' in c][-2:] == [['-k'], ['-w']]
    runtime.env.pop('FIXTURE_STOP_CODE')
    command = [sys.executable, str(runtime.root / 'scripts/wine/artifacts.py'), 'terminal-stop']
    retry = subprocess.run(command, cwd=runtime.root, env=runtime.env, capture_output=True)
    assert retry.returncode == 0, retry.stderr
    before = runtime.calls()
    assert subprocess.run(command, cwd=runtime.root, env=runtime.env).returncode == 0
    assert runtime.calls() == before


def cleanup_server(runtime, stop=0, wait=0, stop_out=b'', stop_err=b'', wait_out=b'', wait_err=b''):
    """Model the public server CLI, not Wine's private server lock implementation."""
    runtime.write_executable('wineserver', '''#!/usr/bin/python3
import json, os, signal, stat, sys
if sys.argv[1:] == ['--version']:
    print('Wine 9.0 (fixture)'); sys.exit(0)
with open(os.environ['FIXTURE_LOG'], 'a') as stream:
    stream.write(json.dumps({'server':sys.argv[1:], 'regular_streams':all(
        stat.S_ISREG(os.fstat(fd).st_mode) for fd in (1, 2)), 'env':{k:os.environ.get(k)
        for k in ['WINEPREFIX','WINEARCH','WINESERVER']}})+'\\n')
kind = 'STOP' if sys.argv[1:] == ['-k'] else 'WAIT'
os.write(1, bytes.fromhex(os.environ.get('FIXTURE_'+kind+'_OUT', '')))
os.write(2, bytes.fromhex(os.environ.get('FIXTURE_'+kind+'_ERR', '')))
code = int(os.environ.get('FIXTURE_'+kind+'_CODE', '0'))
if code < 0:
    signal.signal(-code, signal.SIG_DFL)
    os.kill(os.getpid(), -code)
sys.exit(code)
''')
    runtime.env.update(FIXTURE_STOP_CODE=str(stop), FIXTURE_WAIT_CODE=str(wait),
                       FIXTURE_STOP_OUT=stop_out.hex(), FIXTURE_STOP_ERR=stop_err.hex(),
                       FIXTURE_WAIT_OUT=wait_out.hex(), FIXTURE_WAIT_ERR=wait_err.hex())


def test_silent_kill_one_wait_zero_admits_cold_prefix_and_owns_consumer(runtime):
    cleanup_server(runtime, stop=1)
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stderr
    module, session = load_owned(runtime)
    state = session.state()
    assert state['authorized'] and not state['ended']
    assert state['stopped_generation'] == state['generation'] == 10
    assert [call['wine'] for call in runtime.calls() if 'wine' in call and not call.get('utility')][:2] == [
        ['wineboot.exe', '--init'], [str(runtime.overlay / 'process-prng-probe.exe')]]
    result = runtime.run('test-windows-under-wine.sh')
    assert result.returncode == 0, result.stderr
    calls = [call for call in runtime.calls() if 'server' in call]
    assert [call['server'] for call in calls] == [['-k'], ['-w'], ['-k'], ['-w']]
    assert all(call['regular_streams'] for call in calls)
    assert all(call['env']['WINEPREFIX'] == str(session.prefix) for call in calls)
    assert all(call['env']['WINEARCH'] == 'win64' for call in calls)
    before = runtime.calls()
    assert module.stop_session(session, end=True).ok
    assert runtime.calls() == before
    assert session.state()['ended'] and not session.state()['authorized']
    assert session.state()['stopped_generation'] == session.state()['generation'] == 11


def test_silent_terminal_cleanup_marker_preserves_raw_pair_and_idempotence(runtime):
    cleanup_server(runtime)
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    _, session = load_owned(runtime)
    state = session.state()
    state.update(generation=state['generation'] + 1, stopped_generation=None)
    session.save(state)
    runtime.env['FIXTURE_STOP_CODE'] = '1'
    command = [sys.executable, str(runtime.root / 'scripts/wine/artifacts.py'), 'terminal-stop']
    result = subprocess.run(command, cwd=runtime.root, env=runtime.env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    marker = next(line for line in result.stdout.splitlines() if line.startswith('Wine cleanup: '))
    status = json.loads(marker.removeprefix('Wine cleanup: '))
    assert status['ok'] and (status['stop_returncode'], status['wait_returncode']) == (1, 0)
    assert status['errors'] == []
    before = runtime.calls()
    assert subprocess.run(command, cwd=runtime.root, env=runtime.env, capture_output=True).returncode == 0
    assert runtime.calls() == before


@pytest.mark.parametrize('stop,wait,stop_out,stop_err,wait_out,wait_err,ok', [
    (1, 0, b'', b'', b'', b'', True),
    (0, 0, b'normal stdout\n', b'normal stderr\n', b'', b'', True),
    (1, 0, b'error\n', b'', b'', b'', False),
    (1, 0, b'', b'error\n', b'', b'', False),
    (1, 0, b' ', b'', b'', b'', False),
    (1, 0, b'', b'', b'error\n', b'', False),
    (1, 0, b'', b'', b'', b'error\n', False),
    (1, 7, b'', b'', b'', b'', False),
    (1, 124, b'', b'', b'', b'', False),
    (0, 137, b'', b'', b'', b'', False),
    (124, 0, b'', b'', b'', b'', False),
    (137, 0, b'', b'', b'', b'', False),
    (37, 0, b'', b'', b'', b'', False),
    (-signal.SIGTERM, 0, b'', b'', b'', b'', False),
    (1, -signal.SIGTERM, b'', b'', b'', b'', False),
    (1, 0, b'\x1b\x00' + b'x' * 10000, b'', b'', b'', False),
])
def test_cleanup_cli_completion_policy_preserves_status_and_retry(
        runtime, monkeypatch, capsys, stop, wait, stop_out, stop_err, wait_out, wait_err, ok):
    cleanup_server(runtime)
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    module, session = load_owned(runtime)
    state = session.state()
    state.update(generation=state['generation'] + 1, stopped_generation=None)
    session.save(state)
    for key, value in dict(runtime.env, FIXTURE_STOP_CODE=str(stop), FIXTURE_WAIT_CODE=str(wait),
                           FIXTURE_STOP_OUT=stop_out.hex(), FIXTURE_STOP_ERR=stop_err.hex(),
                           FIXTURE_WAIT_OUT=wait_out.hex(), FIXTURE_WAIT_ERR=wait_err.hex()).items():
        monkeypatch.setenv(key, value)
    before = len(runtime.calls())
    result = module.stop_session(session, end=True)
    assert result.ok == ok
    assert (result.stop_returncode, result.wait_returncode) == (stop, wait)
    calls = [call for call in runtime.calls()[before:] if 'server' in call]
    assert [call['server'] for call in calls] == [['-k'], ['-w']]
    assert all(call['regular_streams'] and call['env']['WINEPREFIX'] == str(session.prefix) for call in calls)
    output = capsys.readouterr()
    combined = output.out + output.err
    if any((stop_out, stop_err, wait_out, wait_err)):
        assert 'Wine server' in combined and 'bytes=' in combined
    assert '\x1b' not in combined and '\x00' not in combined and len(combined) < 2000
    assert session.state()['ended'] and not session.state()['authorized']
    assert session.state()['stopped_generation'] == (state['generation'] if ok else None)
    if not ok:
        for key in ['FIXTURE_STOP_CODE', 'FIXTURE_WAIT_CODE']:
            monkeypatch.setenv(key, '0')
        for key in ['FIXTURE_STOP_OUT', 'FIXTURE_STOP_ERR', 'FIXTURE_WAIT_OUT', 'FIXTURE_WAIT_ERR']:
            monkeypatch.setenv(key, '')
        assert module.stop_session(session, end=True).ok
    before = runtime.calls()
    assert module.stop_session(session, end=True).ok
    assert runtime.calls() == before


@pytest.mark.parametrize('damage', ['owner', 'mutable', 'write', 'invocation', 'capture'])
def test_silent_cleanup_pair_does_not_hide_other_errors(runtime, monkeypatch, damage):
    cleanup_server(runtime)
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    module, session = load_owned(runtime)
    state = session.state()
    state.update(generation=state['generation'] + 1, stopped_generation=None)
    session.save(state)
    for key, value in dict(runtime.env, FIXTURE_STOP_CODE='1').items():
        monkeypatch.setenv(key, value)
    if damage == 'owner':
        owner_file = session.directory / 'owner.json'
        owner = json.loads(owner_file.read_text())
        owner['nonce'] = '0' * 32
        owner_file.write_text(json.dumps(owner))
    elif damage == 'mutable':
        (session.directory / 'state.json').write_text('corrupt state')
    elif damage == 'write':
        def fail_write(*args, **kwargs):
            raise OSError('fixture state write failure')
        monkeypatch.setattr(module, 'write_control', fail_write)
    elif damage == 'capture':
        def fail_capture(*args):
            raise OSError('fixture capture failure')
        monkeypatch.setattr(module, '_server_output', fail_capture)
    else:
        wait_leader = module.wait_leader
        def fail_stop(argv, **kwargs):
            if argv[-1] == '-k':
                raise OSError('fixture stop invocation failure')
            return wait_leader(argv, **kwargs)
        monkeypatch.setattr(module, 'wait_leader', fail_stop)
    before = len(runtime.calls())
    result = module.stop_session(session, end=True)
    assert not result.ok and result.errors
    calls = [call['server'] for call in runtime.calls()[before:] if 'server' in call]
    expected = [] if damage == 'owner' else [['-w']] if damage == 'invocation' else [['-k'], ['-w']]
    assert calls == expected
    assert result.stop_returncode == (None if damage in ['owner', 'invocation'] else 1)
    assert result.wait_returncode == (None if damage == 'owner' else 0)
    if damage in ['write', 'capture']:
        assert session.state()['stopped_generation'] is None


@pytest.mark.parametrize('app_code,diagnostic,expected', [(19, b'', 19), (0, b'error\n', 1), (19, b'error\n', 19)])
def test_cli_cleanup_policy_preserves_helper_primary_result(runtime, app_code, diagnostic, expected):
    cleanup_server(runtime)
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    runtime.env.update(FIXTURE_STOP_CODE='1', FIXTURE_STOP_ERR=diagnostic.hex(), FIXTURE_APP_CODE=str(app_code))
    result = runtime.run('test-windows-under-wine.sh')
    assert result.returncode == expected, result.stderr
    assert ('Owned Wine cleanup failed:' in result.stderr) == bool(diagnostic)
    _, session = load_owned(runtime)
    state = session.state()
    assert state['ended'] and not state['authorized']
    assert state['stopped_generation'] == (None if diagnostic else state['generation'])


@pytest.mark.parametrize('init_code,probe_code,diagnostic', [
    (42, 0, 'Wine initialization failed: exit=42'),
    (0, 20, 'Wine API admission failed: probe exit=20'),
])
def test_silent_cleanup_does_not_hide_preparation_primary_failure(runtime, init_code, probe_code, diagnostic):
    cleanup_server(runtime, stop=1)
    runtime.env['FIXTURE_INIT_CODE'] = str(init_code)
    runtime.package()
    result = runtime.prepare([probe_code])
    assert result.returncode != 0 and diagnostic in result.stderr
    assert 'Owned Wine cleanup failed:' not in result.stderr
    assert not (runtime.overlay / 'admission.json').exists()
    assert [call['server'] for call in runtime.calls() if 'server' in call] == [['-k'], ['-w']]


def test_old_receipt_rejected_without_default_prefix_cleanup(runtime):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    receipt = runtime.overlay / 'admission.json'
    value = json.loads(receipt.read_text())
    value['version'] = 1
    receipt.write_text(json.dumps(value))
    before = runtime.calls()
    assert runtime.run('test-windows-under-wine.sh').returncode != 0
    assert runtime.calls() == before


def test_missing_matching_server_fails_before_boot(runtime):
    runtime.package()
    (runtime.bin / 'wineserver').unlink()
    assert runtime.prepare([0]).returncode != 0
    assert not [c for c in runtime.calls() if 'wine' in c]


def relocate_tools(runtime, backend_name='wineserver'):
    # Record actual exec paths, including the two existing identity queries.
    # All executables remain inert host fixtures, not installed Wine tools.
    for name in ('wine', 'wineserver'):
        path = runtime.bin / name
        path.write_text(path.read_text().replace(
            "if sys.argv[1:] == ['--version']:",
            "with open(os.environ['FIXTURE_LOG'], 'a') as f:\n"
            "    f.write(json.dumps({'tool':sys.argv[0], 'args':sys.argv[1:], 'env':{k:os.environ.get(k) for k in\n"
            "        ['WINEPREFIX','WINEARCH','WINESERVER']}})+'\\n')\n"
            "if sys.argv[1:] == ['--version']:"))
    wine = runtime.bin / 'wine-stable'
    (runtime.bin / 'wine').rename(wine)
    backend = runtime.bin.parent / 'lib/wine' / backend_name
    backend.parent.mkdir(parents=True)
    (runtime.bin / 'wineserver').rename(backend)
    (runtime.bin / 'wineserver-stable').symlink_to(backend)
    runtime.env['WINE_CMD'] = str(wine)
    return wine, backend


@pytest.mark.parametrize('backend_name', ['wineserver', 'wineserver64'])
@pytest.mark.parametrize('selection', ['explicit', 'command', 'alias', 'default64'])
def test_logical_sibling_server_can_resolve_to_backend(runtime, monkeypatch, backend_name, selection):
    wine, server = relocate_tools(runtime, backend_name)
    assert wine.is_file() and not wine.is_symlink()
    assert (runtime.bin / 'wineserver-stable').is_symlink()
    if selection == 'command':
        runtime.env['WINE_CMD'] = 'wine-stable'
    elif selection in ('alias', 'default64'):
        alias = runtime.bin / ('wine' if selection == 'alias' else 'wine64')
        alias.symlink_to(wine)
        (runtime.bin / 'wineserver').symlink_to(server)
        # A resolver that pairs beside the canonical launcher must not pass.
        (runtime.bin / 'wineserver-stable').unlink()
        if selection == 'alias':
            runtime.env['WINE_CMD'] = str(alias)
        else:
            runtime.env.pop('WINE_CMD')
            monkeypatch.delenv('WINE_CMD', raising=False)
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stderr
    module, session = load_owned(runtime)
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    assert module.resolve_wine() == wine  # Preserve the canonical public contract.
    assert session.owner['tools'] == {
        name: {'executable': str(path), 'version': version,
               'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        for name, path, version in [('wine', wine, 'wine-9.0 (fixture)'),
                                    ('server', server, 'Wine 9.0 (fixture)')]}
    result = runtime.run('test-windows-under-wine.sh')
    assert result.returncode == 0, result.stderr
    calls = [c for c in runtime.calls() if 'tool' in c]
    assert [(c['tool'], c['args']) for c in calls] == [
        (str(wine), ['--version']), (str(server), ['--version']),
        (str(wine), ['wineboot.exe', '--init']),
        *[(str(wine), args) for args in setup_argv(session)],
        (str(wine), [str(runtime.overlay / 'process-prng-probe.exe')]),
        (str(server), ['-k']), (str(server), ['-w']),
        (str(wine), [str(runtime.overlay / 'space-cli.exe'), '-m', 'tests.fast:main']),
        (str(server), ['-k']), (str(server), ['-w'])]
    assert all({key: c['env'][key] for key in ['WINEPREFIX', 'WINEARCH', 'WINESERVER']} ==
               {'WINEPREFIX': str(session.prefix), 'WINEARCH': 'win64', 'WINESERVER': str(server)} for c in calls)
    state = session.state()
    assert state['ended'] and not state['authorized']
    assert state['stopped_generation'] == state['generation'] == 11
    assert not Path(runtime.env['WINEPREFIX']).exists()


@pytest.mark.parametrize('damage', ['missing', 'dangling', 'directory', 'non-executable', 'wrong-suffix'])
@pytest.mark.parametrize('selection', ['explicit', 'alias'])
def test_invalid_logical_server_never_falls_back_to_path(runtime, damage, selection):
    wine, server = relocate_tools(runtime)
    logical_server = wine.with_name('wineserver-stable')
    if selection == 'alias':
        selected = runtime.bin / 'selected'
        selected.mkdir()
        alias = selected / 'wine-custom'
        alias.symlink_to(wine)
        runtime.env['WINE_CMD'] = str(alias)
        logical_server = selected / 'wineserver-custom'
        # The canonical launcher's valid sibling also cannot replace the
        # missing/invalid logical sibling of the selected alias.
    else:
        logical_server.unlink()
    # A valid unrelated unsuffixed server is on PATH, but cannot substitute for
    # the explicitly selected suffixed launcher's logical sibling.
    (runtime.bin / 'wineserver').symlink_to(server)
    if damage == 'dangling':
        logical_server.symlink_to(server.with_name('missing'))
    elif damage == 'directory':
        logical_server.mkdir()
    elif damage == 'non-executable':
        logical_server.write_text('not executable')
    elif damage == 'wrong-suffix':
        logical_server.with_name('wineserver-other').symlink_to(server)
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode != 0
    assert not [c for c in runtime.calls() if 'wine' in c or 'server' in c]


@pytest.mark.parametrize('version', ['Wine 8.0', 'unrecognized-release'])
def test_release_failure_reports_captured_versions_and_both_path_pairs(runtime, version):
    wine, server = relocate_tools(runtime)
    # Distinct logical/canonical launcher as well as relocated server paths.
    alias = runtime.bin / 'wine'
    alias.symlink_to(wine)
    logical_server = runtime.bin / 'wineserver'
    logical_server.symlink_to(server)
    runtime.env['WINE_CMD'] = str(alias)
    server.write_text(server.read_text().replace('Wine 9.0 (fixture)', version))
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode != 0
    assert ('Unsupported Wine release identity' if version == 'unrecognized-release'
            else 'Wine/wineserver release mismatch') in result.stderr
    if version == 'unrecognized-release':
        assert result.stderr.startswith('Windows runtime: Wine tool identity rejected: server: '
                                        'Unsupported Wine release identity;')
    else:
        assert result.stderr.startswith('Windows runtime: Wine/wineserver release mismatch;')
    assert f"wine lookup={alias} canonical={wine}" in result.stderr
    assert f"wineserver lookup={logical_server} canonical={server}" in result.stderr
    assert 'wine-9.0 (fixture)' in result.stderr and version in result.stderr
    assert [(c['tool'], c['args']) for c in runtime.calls() if 'tool' in c] == [
        (str(wine), ['--version']), (str(server), ['--version'])]
    assert not [c for c in runtime.calls() if 'wine' in c or 'server' in c]


def version_output(path, stdout, stderr, code=0):
    """Change only the fake tool's existing --version branch, preserving call logging."""
    source = path.read_text()
    branch = "if sys.argv[1:] == ['--version']:\n"
    start = source.index(branch) + len(branch)
    end = source.index('\n', start)
    path.write_text(source[:start] +
                    f'    os.write(1, {stdout!r}); os.write(2, {stderr!r}); sys.exit({code})' + source[end:])


@pytest.mark.parametrize('mode', ['fast1800', 'smoke60'])
def test_observed_stdout_stderr_vendor_layout_admits_and_owns_execution(runtime, mode):
    wine, server = relocate_tools(runtime)
    raw_wine = 'wine-9.0 (Ubuntu 9.0~repack-4build3)'
    version_output(wine, (raw_wine + '\n').encode(), b'')
    version_output(server, b'', b'Wine 9.0\n')
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stderr
    _, session = load_owned(runtime)
    assert session.owner['tools'] == {
        'wine': {'executable': str(wine), 'version': raw_wine,
                 'sha256': hashlib.sha256(wine.read_bytes()).hexdigest()},
        'server': {'executable': str(server), 'version': 'Wine 9.0',
                   'sha256': hashlib.sha256(server.read_bytes()).hexdigest()}}
    captures = session.owner['tool_versions']
    assert captures['wine']['stream'] == 'stdout' and captures['server']['stream'] == 'stderr'
    assert captures['wine']['release'] == captures['server']['release'] == '9.0'
    assert captures['wine']['stdout']['bytes'] == len(raw_wine.encode()) + 1
    assert captures['server']['stdout']['bytes'] == 0
    assert captures['server']['stderr']['bytes'] == len(b'Wine 9.0\n')
    if mode == 'fast1800':
        result = runtime.run('test-windows-under-wine.sh')
    else:
        result = subprocess.run([sys.executable, str(runtime.root / 'scripts/wine/artifacts.py'), mode],
                                cwd=runtime.root, env=runtime.env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    calls = [call for call in runtime.calls() if 'tool' in call]
    assert [(call['tool'], call['args']) for call in calls[:2]] == [
        (str(wine), ['--version']), (str(server), ['--version'])]
    assert sum(call['args'] == ['--version'] for call in calls) == 2
    assert calls[2]['args'] == ['wineboot.exe', '--init']
    assert calls[-3]['args'] == [str(runtime.overlay / 'space-cli.exe'), *(
        ['-m', 'tests.fast:main'] if mode == 'fast1800' else ['--help'])]
    assert [call['args'] for call in calls[-2:]] == [['-k'], ['-w']]
    assert all(call['env']['WINEPREFIX'] == str(session.prefix) for call in calls)
    assert session.state()['ended'] and not session.state()['authorized']
    assert not Path(runtime.env['WINEPREFIX']).exists()


@pytest.mark.parametrize('wine_stream,server_stream', [('stdout', 'stdout'), ('stdout', 'stderr'),
                                                       ('stderr', 'stdout'), ('stderr', 'stderr')])
@pytest.mark.parametrize('release', ['9.0', '9.0rc1', '9.0-rc1', '9.0dev2', '9.0-dev'])
def test_version_streams_keep_exact_core_and_ignore_vendor_annotation(runtime, wine_stream, server_stream, release):
    wine, server = relocate_tools(runtime)
    for path, stream, line in [(wine, wine_stream, f'wine-{release} (Ubuntu)'),
                               (server, server_stream, f'Wine {release} (Fixture)')]:
        output = ('wine: warning: bounded diagnostic noise\n' + line + '\n').encode()
        version_output(path, output if stream == 'stdout' else b'warning: other stream\n',
                       output if stream == 'stderr' else b'warning: other stream\n')
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stderr
    _, session = load_owned(runtime)
    for name, stream in [('wine', wine_stream), ('server', server_stream)]:
        capture = session.owner['tool_versions'][name]
        assert capture['release'] == release and capture['stream'] == stream
        assert capture['occurrences'] == 1
        assert 'bounded diagnostic noise' in capture[stream]['excerpt']
    assert [(call['tool'], call['args']) for call in runtime.calls() if 'tool' in call][:2] == [
        (str(wine), ['--version']), (str(server), ['--version'])]


@pytest.mark.parametrize('cross_stream', [False, True])
def test_identical_version_lines_are_accepted_with_explicit_stdout_precedence(runtime, cross_stream):
    wine, server = relocate_tools(runtime)
    version_output(server, b'Wine 9.0\n' if cross_stream else b'Wine 9.0\nWine 9.0\n',
                   b'Wine 9.0\n' if cross_stream else b'')
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stderr
    _, session = load_owned(runtime)
    capture = session.owner['tool_versions']['server']
    assert session.owner['tools']['server']['version'] == 'Wine 9.0'
    assert capture['stream'] == 'stdout' and capture['occurrences'] == 2


def test_version_limit_is_per_stream_bytes_and_retains_full_selected_line(runtime):
    wine, server = relocate_tools(runtime)
    raw_version = 'Wine 9.0 (' + 'é' * 2042 + 'x)'
    assert len(raw_version.encode()) == 4096
    warning = b'warning: ' + b'x' * (4096 - len(b'warning: '))
    version_output(server, warning, raw_version.encode())
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode == 0, result.stderr
    _, session = load_owned(runtime)
    assert session.owner['tools']['server']['version'] == raw_version
    capture = session.owner['tool_versions']['server']
    assert capture['release'] == '9.0' and capture['stream'] == 'stderr'
    assert capture['stdout']['bytes'] == capture['stderr']['bytes'] == 4096
    assert all(len(capture[name]['excerpt']) <= 800 for name in ['stdout', 'stderr'])


def test_version_queries_wait_leaders_without_communicating(runtime, monkeypatch):
    module = prefix_module()
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    def no_communicate(*args, **kwargs):
        raise AssertionError('Version queries must not communicate on descendant pipes')
    monkeypatch.setattr(module.subprocess.Popen, 'communicate', no_communicate)
    session = module.create_session(runtime.root)
    assert session.owner['tool_versions']['wine']['release'] == '9.0'
    assert module.stop_session(session, end=True).ok


BAD_VERSIONS = [
    (b'', b'', 0, 'Unsupported Wine release identity'),
    (b'Wine v9.0\n', b'', 0, 'Unsupported Wine release identity'),
    (b'wine-9.0-custom\n', b'', 0, 'Unsupported Wine release identity'),
    (b'warning: Wine 9.0\n', b'', 0, 'Unsupported Wine release identity'),
    (b'Wine 9.0\nWine 8.0\n', b'', 0, 'Ambiguous Wine release identity'),
    (b'Wine 9.0 (A)\nWine 9.0 (B)\n', b'', 0, 'Ambiguous Wine release identity'),
    (b'Wine 9.0\n', b'Wine 9.1\n', 0, 'Ambiguous Wine release identity'),
    (b'x' * 4097, b'Wine 9.0\n', 0, 'Oversized Wine tool version'),
    (b'Wine 9.0\n', b'x' * 4097, 0, 'Oversized Wine tool version'),
    (('é' * 2050).encode(), b'Wine 9.0\n', 0, 'Oversized Wine tool version'),
    (b'\xff', b'Wine 9.0\n', 0, 'Invalid UTF-8 Wine tool version'),
    (b'Wine 9.0\n', b'\xff', 0, 'Invalid UTF-8 Wine tool version'),
    (b'Wine 9.0\n', b'warning: error\n', 23, 'exit=23'),
    (b'\x1b[31mwarning\x00\n', b'not a version\n', 0, 'Unsupported Wine release identity'),
]


@pytest.mark.parametrize('tool', ['wine', 'server'])
@pytest.mark.parametrize('stdout,stderr,code,diagnostic', BAD_VERSIONS,
                         ids=['empty', 'unsupported', 'unsupported-suffix', 'unanchored', 'conflict',
                              'ambiguous-annotation', 'cross-conflict', 'stdout-overflow', 'stderr-overflow',
                              'multibyte-overflow', 'stdout-invalid', 'stderr-invalid', 'nonzero', 'controls'])
def test_invalid_identity_queries_both_tools_then_fails_before_any_lifecycle(runtime, tool, stdout, stderr, code, diagnostic):
    wine, server = relocate_tools(runtime)
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    _, old_session = load_owned(runtime)
    old_files = {path: path.read_bytes() for path in [old_session.directory / 'owner.json',
                 old_session.directory / 'state.json', runtime.overlay / 'admission.json']}
    version_output(wine if tool == 'wine' else server, stdout, stderr, code)
    before = len(runtime.calls())
    result = runtime.prepare([0])
    assert result.returncode != 0
    assert diagnostic in result.stderr
    assert result.stderr.startswith(f'Windows runtime: Wine tool identity rejected: {tool}: ')
    assert diagnostic in result.stderr[:500]
    assert f'wine lookup={wine} canonical={wine}' in result.stderr
    assert f'wineserver lookup={runtime.bin / "wineserver-stable"} canonical={server}' in result.stderr
    assert 'stdout' in result.stderr and 'stderr' in result.stderr and 'bytes' in result.stderr
    assert len(result.stderr) < 5000
    assert '\x1b' not in result.stderr and '\x00' not in result.stderr
    added = [call for call in runtime.calls()[before:] if 'tool' in call]
    assert [(call['tool'], call['args']) for call in added] == [
        (str(wine), ['--version']), (str(server), ['--version'])]
    assert not [call for call in runtime.calls()[before:] if 'wine' in call or 'server' in call]
    assert all(path.read_bytes() == data for path, data in old_files.items())
    assert not Path(runtime.env['WINEPREFIX']).exists()


@pytest.mark.parametrize('wine_core,server_core', [('9.0', '9.1'), ('9.0rc1', '9.0rc2'),
                                                  ('9.0-rc1', '9.0-rc2'), ('9.0dev1', '9.0dev2'),
                                                  ('9.0-dev', '9.0-dev1'), ('9.0', '9.0-dev')])
def test_core_release_difference_is_not_hidden_by_annotation_parsing(runtime, wine_core, server_core):
    wine, server = relocate_tools(runtime)
    version_output(wine, f'wine-{wine_core} (Ubuntu)\n'.encode(), b'')
    version_output(server, b'', f'Wine {server_core}\n'.encode())
    runtime.package()
    result = runtime.prepare([0])
    assert result.returncode != 0
    assert 'Wine/wineserver release mismatch' in result.stderr
    assert wine_core in result.stderr and server_core in result.stderr
    assert [(call['tool'], call['args']) for call in runtime.calls() if 'tool' in call] == [
        (str(wine), ['--version']), (str(server), ['--version'])]


def test_admission_failure_still_stops_owned_prefix(runtime):
    runtime.package()
    assert runtime.prepare([20]).returncode != 0
    assert [c['server'] for c in runtime.calls() if 'server' in c] == [['-k'], ['-w']]


def test_authorization_is_one_shot(runtime):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    assert runtime.run('test-windows-under-wine.sh').returncode == 0
    before = runtime.calls()
    assert runtime.run('test-windows-under-wine.sh').returncode != 0
    assert runtime.calls() == before


@pytest.mark.parametrize('kind,code', [('init', 42), ('app', 19), ('app', 124)])
def test_primary_failure_survives_cleanup_failure(runtime, kind, code):
    runtime.package()
    if kind == 'app':
        assert runtime.prepare([0]).returncode == 0
    runtime.env['FIXTURE_' + kind.upper() + '_CODE'] = str(code)
    runtime.env['FIXTURE_STOP_CODE'] = '37'
    result = runtime.prepare([0]) if kind == 'init' else runtime.run('test-windows-under-wine.sh')
    assert result.returncode == (1 if kind == 'init' else code)
    assert '37' in result.stderr
    if kind == 'init':
        assert 'exit=42' in result.stderr
    assert [c['server'] for c in runtime.calls() if 'server' in c][-2:] == [['-k'], ['-w']]


def prefix_module():
    spec = importlib.util.spec_from_file_location('owned_prefix_tests', ROOT / 'scripts/wine/prefix.py')
    assert spec is not None, 'owned-prefix module is required'
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_owned(runtime):
    module = prefix_module()
    receipt = json.loads((runtime.overlay / 'admission.json').read_text())
    return module, module.load_session(runtime.root, receipt['ownedSession']['id'])


@pytest.mark.parametrize('active', [False, True])
@pytest.mark.parametrize('damage', ['nonce', 'handoff-missing', 'handoff-malformed'])
def test_verified_session_receipt_errors_end_authorization_before_return(runtime, active, damage):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    _, session = load_owned(runtime)
    receipt = runtime.overlay / 'admission.json'
    marker = runtime.overlay / '.space-windows-artifact-v1.json'
    original_receipt, original_marker = receipt.read_bytes(), marker.read_bytes()
    if active:
        state = session.state()
        state['generation'] += 1
        state['stopped_generation'] = None
        session.save(state)
    if damage == 'nonce':
        value = json.loads(original_receipt)
        value['ownedSession']['nonce'] = '0' * 32
        receipt.write_text(json.dumps(value))
        # Preserve a valid artifact inventory so the binding itself is rejected.
        manifest = json.loads(original_marker)
        manifest['inventory']['admission.json'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
        marker.write_text(json.dumps(manifest))
    else:
        runtime.env['SPACE_WINE_SESSION_ID'] = session.id
        if damage == 'handoff-missing':
            receipt.unlink()
        else:
            receipt.write_text('not JSON')
    before = runtime.calls()
    result = runtime.run('test-windows-under-wine.sh')
    assert result.returncode != 0
    state = session.state()
    assert state['ended'] and not state['authorized']
    added = runtime.calls()[len(before):]
    assert not [call for call in added if 'wine' in call]
    assert [call['server'] for call in added if 'server' in call] == ([['-k'], ['-w']] if active else [])
    assert all(call['env']['WINEPREFIX'] == str(session.prefix) for call in added if 'server' in call)
    receipt.write_bytes(original_receipt)
    marker.write_bytes(original_marker)
    before = runtime.calls()
    replay = runtime.run('test-windows-under-wine.sh')
    assert replay.returncode != 0
    assert 'authorization ended/consumed' in replay.stderr
    assert runtime.calls() == before


def test_private_handoff_does_not_bypass_unsafe_owner(runtime):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    _, session = load_owned(runtime)
    runtime.env['SPACE_WINE_SESSION_ID'] = session.id
    (runtime.overlay / 'admission.json').unlink()
    session.prefix.rename(session.prefix.with_name('preserved'))
    session.prefix.symlink_to(session.prefix.with_name('preserved'), target_is_directory=True)
    before = runtime.calls()
    assert runtime.run('test-windows-under-wine.sh').returncode != 0
    assert runtime.calls() == before


@pytest.mark.parametrize('control', ['state.json', 'owner.json'])
def test_fifo_control_is_rejected_promptly_with_only_verified_owned_cleanup(runtime, control):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    _, session = load_owned(runtime)
    path = session.directory / control
    path.unlink()
    os.mkfifo(path, 0o600)
    before = runtime.calls()
    command = [sys.executable, str(runtime.root / 'scripts/wine/artifacts.py'), 'terminal-stop']
    started = time.monotonic()
    # Independent watchdog kills the stuck helper on RED, even when it ignores
    # catchable signals during cleanup. No Wine/PE or arbitrary prefix is used.
    try:
        result = subprocess.run(command, cwd=runtime.root,
                                env=dict(runtime.env, SPACE_WINE_SESSION_ID=session.id),
                                capture_output=True, text=True, timeout=2)
    except subprocess.TimeoutExpired:
        pytest.fail(f'{control} FIFO blocked owned cleanup before the bounded server commands')
    assert time.monotonic() - started < 2
    assert result.returncode != 0
    assert 'Unsafe session control:' in result.stderr
    added = runtime.calls()[len(before):]
    assert not [call for call in added if 'wine' in call]
    expected = [['-k'], ['-w']] if control == 'state.json' else []
    assert [call['server'] for call in added if 'server' in call] == expected
    assert all(call['env']['WINEPREFIX'] == str(session.prefix) for call in added if 'server' in call)


@pytest.mark.parametrize('root', ['repo', 'build', 'wine', 'sessions', 'session', 'prefix', 'data', 'cache', 'tmp'])
def test_substituted_root_refuses_server_commands(runtime, monkeypatch, root):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    module, session = load_owned(runtime)
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    path = session.roots()[root]
    saved = path.with_name(path.name + '-preserved')
    path.rename(saved)
    path.mkdir(mode=0o700)
    before = runtime.calls()
    try:
        result = module.stop_session(session, end=True)
        assert not result.ok
        assert result.stop_returncode is None and result.wait_returncode is None
        assert runtime.calls() == before
    finally:
        path.rmdir()
        saved.rename(path)


@pytest.mark.parametrize('change', ['nonce', 'mode', 'symlink', 'wine', 'server'])
def test_changed_immutable_ownership_refuses_cleanup(runtime, monkeypatch, change):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    module, session = load_owned(runtime)
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    if change == 'nonce':
        owner = session.directory / 'owner.json'
        value = json.loads(owner.read_text())
        value['nonce'] = '0' * 32
        owner.write_text(json.dumps(value))
    elif change == 'mode':
        session.directory.chmod(0o755)
    elif change == 'symlink':
        session.prefix.rename(session.prefix.with_name('preserved'))
        session.prefix.symlink_to(session.prefix.with_name('preserved'), target_is_directory=True)
    else:
        path = Path(session.owner['tools'][change]['executable'])
        path.write_text(path.read_text() + '\n# substituted tool\n')
    before = runtime.calls()
    assert not module.stop_session(session, end=True).ok
    assert runtime.calls() == before


@pytest.mark.parametrize('damage', [
    'invalid-json', 'missing-field', 'missing-nonce', 'missing-generation',
    'missing-authorized', 'missing-ended', 'array', 'null', 'boolean',
    'generation-bool', 'generation-negative', 'generation-string',
    'stopped-bool', 'stopped-negative', 'stopped-future', 'stopped-string',
    'authorized-number', 'ended-number', 'wrong-nonce', 'extra-field',
    'ended-string', 'authorized-null',
])
def test_mutable_state_failure_does_not_block_owned_stop_or_follow_dosdevices(runtime, monkeypatch, tmp_path, damage):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    module, session = load_owned(runtime)
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    target = tmp_path / 'unrelated'
    target.mkdir()
    (target / 'sentinel').write_text('never touch')
    devices = session.prefix / 'dosdevices'
    devices.mkdir()
    (devices / 'z:').symlink_to(target, target_is_directory=True)
    state_file = session.directory / 'state.json'
    if damage == 'invalid-json':
        state_file.write_text('broken mutable state')
    else:
        state = json.loads(state_file.read_text())
        if damage == 'missing-field':
            del state['stopped_generation']
        elif damage.startswith('missing-'):
            del state[damage.removeprefix('missing-')]
        elif damage in ('array', 'null', 'boolean'):
            state = {'array': [], 'null': None, 'boolean': True}[damage]
        else:
            changes = {
                'generation-bool': ('generation', True),
                'generation-negative': ('generation', -1),
                'generation-string': ('generation', '2'),
                'stopped-bool': ('stopped_generation', True),
                'stopped-negative': ('stopped_generation', -1),
                'stopped-future': ('stopped_generation', state['generation'] + 1),
                'stopped-string': ('stopped_generation', '2'),
                'authorized-number': ('authorized', 1),
                'ended-number': ('ended', 0),
                'wrong-nonce': ('nonce', '0' * 32),
                'extra-field': ('unknown', 'not lifecycle data'),
                'ended-string': ('ended', 'false'),
                'authorized-null': ('authorized', None),
            }
            key, value = changes[damage]
            state[key] = value
        state_file.write_text(json.dumps(state))
    damaged_bytes = state_file.read_bytes()
    owner_bytes = (session.directory / 'owner.json').read_bytes()
    before = runtime.calls()
    with pytest.raises(ValueError):
        session.state()
    with pytest.raises(ValueError):
        module.initialize(session)
    assert runtime.calls() == before
    result = module.stop_session(session, end=True)
    assert not result.ok and result.stop_returncode == result.wait_returncode == 0
    assert result.errors and result.errors[0].startswith('Lifecycle read:')
    assert [c['server'] for c in runtime.calls() if 'server' in c][-2:] == [['-k'], ['-w']]
    assert state_file.read_bytes() == damaged_bytes  # No invented generation or authorization.
    assert (session.directory / 'owner.json').read_bytes() == owner_bytes
    assert (target / 'sentinel').read_text() == 'never touch'
    assert (devices / 'z:').is_symlink()
    assert session.prefix.is_dir()


def test_state_write_failure_cannot_launch_and_cannot_block_cleanup(runtime, monkeypatch):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    module, session = load_owned(runtime)
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    # Mark an active generation, then simulate storage loss independently of owner reads.
    state = session.state()
    state['generation'] += 1
    state['stopped_generation'] = None
    session.save(state)
    def fail_write(*args, **kwargs):
        raise OSError('fixture storage unavailable')
    monkeypatch.setattr(module, 'write_control', fail_write)
    before = len([c for c in runtime.calls() if 'wine' in c])
    with pytest.raises(OSError, match='storage unavailable'):
        module.initialize(session)
    result = module.stop_session(session, end=True)
    assert not result.ok and result.stop_returncode == result.wait_returncode == 0
    assert len([c for c in runtime.calls() if 'wine' in c]) == before


def test_launch_waits_leader_without_communicating_on_descendant_streams(runtime, monkeypatch):
    runtime.package()
    assert runtime.prepare([0]).returncode == 0
    module, session = load_owned(runtime)
    for key, value in runtime.env.items():
        monkeypatch.setenv(key, value)
    def no_communicate(*args, **kwargs):
        raise AssertionError('Wine children must wait leaders, not communicate descendant pipes')
    monkeypatch.setattr(module.subprocess.Popen, 'communicate', no_communicate)
    assert module.initialize(session) == 0
    assert module.stop_session(session, end=True).ok


def test_mismatched_release_fails_before_init(runtime):
    runtime.package()
    runtime.write_executable('wineserver', '#!/bin/sh\nprintf "Wine 8.0\\n"\n')
    result = runtime.prepare([0])
    assert result.returncode != 0
    assert not [c for c in runtime.calls() if 'wine' in c]


def test_parent_lock_held_and_child_does_not_inherit_directory_fds(runtime):
    runtime.package()
    runtime.write_executable('wine', '''#!/usr/bin/python3
import fcntl, json, os, pathlib, sys
if sys.argv[1:] == ['--version']:
    print('wine-9.0 (fixture)'); sys.exit(0)
root = pathlib.Path(os.environ['FIXTURE_ROOT'])
for entry in pathlib.Path('/proc/self/fd').iterdir():
    try: target = entry.readlink()
    except FileNotFoundError: continue
    assert target != root/'build', 'ownership FD leaked into child'
fd = os.open(root/'build', os.O_RDONLY | os.O_DIRECTORY)
try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError: pass
else: sys.exit(77)
if sys.argv[1].endswith('space-cli.exe'):
    receipt = json.loads((root/'build/wine/windows/admission.json').read_text())
    state = json.loads((root/'build/wine/sessions'/receipt['ownedSession']['id']/'state.json').read_text())
    assert not state['authorized'], 'authorization was not revoked before launch'
''')
    runtime.env['FIXTURE_ROOT'] = str(runtime.root)
    assert runtime.prepare([0]).returncode == 0
    result = runtime.run('test-windows-under-wine.sh')
    assert result.returncode == 0, result.stderr


def test_different_pgid_pipe_holder_stopped_before_helper_exit_with_unrelated_control(runtime):
    runtime.package()
    real_timeout = shutil.which('timeout', path=os.defpath)
    assert real_timeout
    runtime.write_executable('timeout', f'''#!/usr/bin/python3
import os, sys
args = ['0.3s' if a == '1800s' else a for a in sys.argv[1:]]
os.execv({real_timeout!r}, [{real_timeout!r}, *args])
''')
    runtime.write_executable('wine', '''#!/usr/bin/python3
import os, pathlib, signal, subprocess, sys, time
if sys.argv[1:] == ['--version']:
    print('wine-9.0 (fixture)'); sys.exit(0)
if not sys.argv[1].endswith('space-cli.exe'): sys.exit(0)
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
pathlib.Path(os.environ['WINEPREFIX']).parent.joinpath('fixture-child').write_text(str(child.pid))
print('fixture child holding both streams', flush=True)
time.sleep(30)
''')
    runtime.write_executable('wineserver', '''#!/usr/bin/python3
import os, pathlib, signal, sys
if sys.argv[1:] == ['--version']:
    print('Wine 9.0 (fixture)'); sys.exit(0)
record = pathlib.Path(os.environ['WINEPREFIX']).parent/'fixture-child'
if sys.argv[1:] == ['-k'] and record.exists():
    try: os.kill(int(record.read_text()), signal.SIGKILL)
    except ProcessLookupError: pass
''')
    control = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                               start_new_session=True, env=dict(runtime.env, WINEPREFIX='/unrelated-fixture-prefix'),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    process = None
    try:
        assert runtime.prepare([0]).returncode == 0
        process = subprocess.Popen(['bash', str(runtime.root/'scripts/test-windows-under-wine.sh')],
                                   cwd=runtime.root, env=runtime.env, start_new_session=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(timeout=4)
        assert process.returncode == 124, (stdout, stderr)
        assert b'holding both streams' in stdout
        assert control.poll() is None
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        for record in (runtime.root/'build/wine/sessions').glob('*/fixture-child'):
            try: os.kill(int(record.read_text()), signal.SIGKILL)
            except ProcessLookupError: pass
        control.kill()
        control.wait()


@pytest.mark.parametrize('first_signal', [signal.SIGINT, signal.SIGTERM])
def test_interruption_and_repeated_signals_cannot_skip_finite_cleanup(runtime, first_signal):
    runtime.package()
    runtime.write_executable('wine', '''#!/usr/bin/python3
import os, pathlib, sys, time
if sys.argv[1:] == ['--version']:
    print('wine-9.0 (fixture)'); sys.exit(0)
if sys.argv[1].endswith('space-cli.exe'):
    pathlib.Path(os.environ['WINEPREFIX']).parent.joinpath('fixture-app').write_text(str(os.getpid()))
    time.sleep(30)
''')
    runtime.write_executable('wineserver', '''#!/usr/bin/python3
import os, pathlib, sys, time
if sys.argv[1:] == ['--version']:
    print('Wine 9.0 (fixture)'); sys.exit(0)
directory = pathlib.Path(os.environ['WINEPREFIX']).parent
if sys.argv[1:] == ['-k'] and (directory/'fixture-app').exists():
    (directory/'cleanup-started').write_text('yes')
    time.sleep(0.4)
with (directory/'fixture-cleanup').open('a') as stream: stream.write(sys.argv[1]+'\\n')
''')
    assert runtime.prepare([0]).returncode == 0
    _, session = load_owned(runtime)
    process = subprocess.Popen(['bash', str(runtime.root/'scripts/test-windows-under-wine.sh')],
                               cwd=runtime.root, env=runtime.env, start_new_session=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    def wait_for(path):
        deadline = time.monotonic() + 4
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert path.exists(), f'fixture never reached {path.name}'
    try:
        wait_for(session.directory/'fixture-app')
        process.send_signal(first_signal)
        wait_for(session.directory/'cleanup-started')
        for _ in range(3):
            process.send_signal(signal.SIGINT)
            process.send_signal(signal.SIGTERM)
            time.sleep(0.02)
        stdout, stderr = process.communicate(timeout=4)
        assert process.returncode != 0, (stdout, stderr)
        assert b'interrupted by signal' in stderr
        assert (session.directory/'fixture-cleanup').read_text().splitlines() == ['-k', '-w', '-k', '-w']
        assert session.state()['ended'] and not session.state()['authorized']
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        record = session.directory/'fixture-app'
        if record.exists():
            try: os.kill(int(record.read_text()), signal.SIGKILL)
            except ProcessLookupError: pass


def test_forced_app_timeout_normalizes_only_process_exit_and_still_stops(runtime):
    runtime.package()
    real_timeout = shutil.which('timeout', path=os.defpath)
    runtime.write_executable('timeout', f'''#!/usr/bin/python3
import os, sys
args = ['0.2s' if a == '1800s' else '--kill-after=0.2s' if a == '--kill-after=5s' else a for a in sys.argv[1:]]
os.execv({real_timeout!r}, [{real_timeout!r}, *args])
''')
    runtime.write_executable('wine', '''#!/usr/bin/python3
import signal, sys, time
if sys.argv[1:] == ['--version']:
    print('wine-9.0 (fixture)'); sys.exit(0)
if not sys.argv[1].endswith('space-cli.exe'): sys.exit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
while True: time.sleep(0.01)
''')
    assert runtime.prepare([0]).returncode == 0
    result = runtime.run('test-windows-under-wine.sh')
    assert result.returncode == 137, result.stderr
    _, session = load_owned(runtime)
    assert session.state()['ended']
    assert [c['server'] for c in runtime.calls() if 'server' in c][-2:] == [['-k'], ['-w']]
