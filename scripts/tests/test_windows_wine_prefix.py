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


@pytest.fixture
def runtime(tmp_path):
    return Fixture(tmp_path)


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
        (str(wine), [str(runtime.overlay / 'process-prng-probe.exe')]),
        (str(server), ['-k']), (str(server), ['-w']),
        (str(wine), [str(runtime.overlay / 'space-cli.exe'), '-m', 'tests.fast:main']),
        (str(server), ['-k']), (str(server), ['-w'])]
    assert all(c['env'] == {'WINEPREFIX': str(session.prefix), 'WINEARCH': 'win64',
                            'WINESERVER': str(server)} for c in calls)
    state = session.state()
    assert state['ended'] and not state['authorized']
    assert state['stopped_generation'] == state['generation'] == 3
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


@pytest.mark.parametrize('version', ['Wine 8.0', 'Wine 9.0', 'Wine 9.0 (Fixture)', 'unrecognized-release'])
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
    assert f"wine lookup={alias} canonical={wine} version='wine-9.0 (fixture)'" in result.stderr
    assert f"wineserver lookup={logical_server} canonical={server} version={version!r}" in result.stderr
    assert [(c['tool'], c['args']) for c in runtime.calls() if 'tool' in c] == [
        (str(wine), ['--version']), (str(server), ['--version'])]
    assert not [c for c in runtime.calls() if 'wine' in c or 'server' in c]


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


@pytest.mark.parametrize('root', ['repo', 'build', 'wine', 'sessions', 'session', 'prefix'])
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
