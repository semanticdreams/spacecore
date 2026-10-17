"""Private generated Wine domains. Never inventory, prune, or reset a prefix.

The immutable owner is independent of mutable launch/authorization state: broken
state can neither authorize execution nor suppress cleanup of a verified owner.
This protects cooperative checkout users, not against a hostile same-UID writer.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
import ntpath
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

BOUNDS = {"init": 90, "probe": 60, "smoke60": 60, "fast1800": 1800,
          "stop": 10, "wait": 15, "kill_after": 5, "setup": 30}
BOOTSTRAP_TEMP = r'C:\windows\temp'
WINEPATH = r'C:\windows\system32\winepath.exe'
REG = r'C:\windows\system32\reg.exe'
CRASH_POLICY = [
    (r'HKLM\Software\Microsoft\Windows NT\CurrentVersion\AeDebug', 'Debugger', 'REG_SZ', 'winedbg --auto %ld %ld'),
    (r'HKLM\Software\Microsoft\Windows NT\CurrentVersion\AeDebug', 'Auto', 'REG_SZ', '1'),
    (r'HKCU\Software\Wine\WineDbg', 'ShowCrashDialog', 'REG_DWORD', '0'),
]
PRIVATE_ENV_KEYS = ('WINEPREFIX', 'WINEARCH', 'WINESERVER', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'TMPDIR', 'TEMP', 'TMP')


def _owned_environment(directory, server, windows_tmp):
    return dict(os.environ, WINEPREFIX=str(directory / 'prefix'), WINEARCH='win64', WINESERVER=server,
                XDG_DATA_HOME=str(directory / 'data'), XDG_CACHE_HOME=str(directory / 'cache'),
                TMPDIR=str(directory / 'tmp'), TEMP=windows_tmp, TMP=windows_tmp)


def _windows_absolute(value):
    return (isinstance(value, str) and re.fullmatch(r'[A-Za-z]:\\[^\x00-\x1f\x7f]*', value) is not None
            and ntpath.isabs(value) and '..' not in value.split('\\'))
VERSION_BYTES = 4096
VERSION_LINE = re.compile(
    r'(?:wine-|Wine )([0-9]+(?:\.[0-9]+)+(?:-?(?:rc[0-9]+|dev[0-9]*))?)'
    r'(?: \([^\x00-\x1f\x7f-\x9f]*\))?')


def real_directory(path, private=False):
    for part in (*reversed(path.parents), path):
        mode = part.lstat().st_mode
        if not stat.S_ISDIR(mode):
            raise ValueError(f"Linked/non-directory ownership root: {part}")
    info = path.stat()
    if info.st_uid != os.geteuid() or (private and stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError(f"Unsafe ownership/mode: {path}")
    return [info.st_dev, info.st_ino]


def read_control(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError(f"Unsafe session control: {path}")
        return json.load(stream)


def write_control(path, value, exclusive=False):
    data = json.dumps(value, sort_keys=True) + "\n"
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        fd, name = tempfile.mkstemp(prefix='.state-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _wine_lookup():
    selected = os.environ.get('WINE_CMD') or shutil.which('wine64') or shutil.which('wine')
    executable = shutil.which(selected) if selected else None
    if not executable:
        raise ValueError('Missing required command: wine64 or wine (or selected WINE_CMD)')
    return Path(executable)


def resolve_wine():
    return _wine_lookup().resolve(strict=True)


class _VersionRejection(ValueError):
    """Keep the primary cause independent of the bounded capture diagnostics."""
    def __init__(self, summary, observation):
        self.summary = summary
        super().__init__(f'{summary}; capture={json.dumps(observation, ensure_ascii=True)}')


def tool_identity(path, env):
    """Return pinned identity and a separate bounded version-query observation.

    Both streams are regular files, never descendant-held communicate pipes.
    Exact duplicate identity lines are accepted (stdout wins across streams);
    different raw identity lines, even annotation-only differences, are ambiguous.
    """
    with tempfile.TemporaryFile(dir=env['TMPDIR']) as output, tempfile.TemporaryFile(dir=env['TMPDIR']) as errors:
        code = wait_leader(['timeout', '--kill-after=5s', '60s', str(path), '--version'],
                           env=env, stdout=output, stderr=errors)
        data, observation = {}, {}
        for name, stream in [('stdout', output), ('stderr', errors)]:
            stream.seek(0)
            data[name] = stream.read(VERSION_BYTES + 1)
            observation[name] = {'bytes': os.fstat(stream.fileno()).st_size,
                                 'excerpt': repr(data[name][:160])}

    def fail(message):
        # Byte repr is ASCII/control-safe even for invalid UTF-8. Never interpolate
        # unbounded raw output or a UnicodeDecodeError's input into diagnostics.
        raise _VersionRejection(message, observation)

    if code:
        fail(f'Wine tool version failed: exit={code}')
    if any(len(raw) > VERSION_BYTES or observation[name]['bytes'] > VERSION_BYTES
           for name, raw in data.items()):
        fail('Oversized Wine tool version')
    try:
        text = {name: raw.decode('utf-8') for name, raw in data.items()}
    except UnicodeDecodeError:
        fail('Invalid UTF-8 Wine tool version')
    candidates = []
    for name, value in text.items():
        for line in value.splitlines():
            if VERSION_LINE.fullmatch(line):
                candidates.append((name, line))
            elif line.startswith(('wine-', 'Wine ')):
                fail('Unsupported Wine release identity')
    if not candidates:
        fail('Unsupported Wine release identity')
    if len({line for _, line in candidates}) != 1:
        fail('Ambiguous Wine release identity')
    stream, version = candidates[0]  # Fixed stdout-then-stderr iteration order.
    observation.update(stream=stream, release=release(version), occurrences=len(candidates))
    identity = {'executable': str(path), 'version': version,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    return identity, observation


def release(version):
    # Compare the entire numeric/rc/dev token, never the distribution annotation.
    match = VERSION_LINE.fullmatch(version)
    if not match:
        raise ValueError('Unsupported Wine release identity')
    return match[1]


@dataclass(frozen=True)
class Session:
    repo: Path
    id: str
    owner: dict

    @property
    def directory(self):
        return self.repo / 'build/wine/sessions' / self.id

    @property
    def prefix(self):
        return self.directory / 'prefix'

    @property
    def nonce(self):
        return self.owner['nonce']

    @property
    def tmp(self):
        return self.directory / 'tmp'

    def _server_environment(self):
        # Immutable ownership alone suffices for scoped cleanup. Never consult
        # derived path/policy observations here, even if setup storage is broken.
        return _owned_environment(self.directory, self.owner['tools']['server']['executable'], BOOTSTRAP_TEMP)

    def environment(self):
        setup = self.setup()
        return _owned_environment(self.directory, self.owner['tools']['server']['executable'],
                                  setup['windows_tmp'] or BOOTSTRAP_TEMP)

    def setup(self):
        value = read_control(self.directory / 'setup.json')
        if (not isinstance(value, dict) or set(value) != {'nonce', 'windows_tmp', 'roundtrip_tmp', 'policy_verified'}
                or value['nonce'] != self.nonce or type(value['policy_verified']) is not bool):
            raise ValueError('Invalid owned setup observations')
        if value['windows_tmp'] is None:
            if value['roundtrip_tmp'] is not None or value['policy_verified']:
                raise ValueError('Incomplete owned path setup')
        elif not _windows_absolute(value['windows_tmp']) or value['roundtrip_tmp'] != str(self.tmp):
            raise ValueError('Invalid owned Windows temp mapping')
        return value

    def binding(self):
        self.validate()
        setup = self.setup()
        return {'id': self.id, 'nonce': self.nonce, 'prefix': str(self.prefix),
                'identity': self.owner['roots']['prefix'], 'arch': 'win64', 'tools': self.owner['tools'],
                'roots': {name: {'path': str(self.roots()[name]), 'identity': self.owner['roots'][name]}
                          for name in ['data', 'cache', 'tmp']},
                'windows_tmp': setup['windows_tmp'],
                'crash_policy': {'values': self.owner['crash_policy'], 'verified': setup['policy_verified']}}

    def validate(self):
        expected = self.owner
        if (expected['version'] != 3 or expected['id'] != self.id
                or expected['uid'] != os.geteuid() or expected['bounds'] != BOUNDS
                or expected.get('crash_policy') != [list(row) for row in CRASH_POLICY]
                or expected['repo'] != str(self.repo) or not re.fullmatch('[0-9a-f]{32}', self.nonce)):
            raise ValueError('Invalid session ownership')
        for name, path in self.roots().items():
            identity = real_directory(path, name in ('sessions', 'session', 'prefix', 'data', 'cache', 'tmp'))
            if expected['roots'][name] != identity:
                raise ValueError(f'Substituted session root: {name}')
        if read_control(self.directory / 'owner.json') != expected:
            raise ValueError('Session owner/nonce changed')
        for identity in expected['tools'].values():
            path = Path(identity['executable'])
            if (path.resolve(strict=True) != path or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != identity['sha256']):
                raise ValueError('Pinned Wine tool changed')

    def roots(self):
        return {'repo': self.repo, 'build': self.repo / 'build', 'wine': self.repo / 'build/wine',
                'sessions': self.directory.parent, 'session': self.directory, 'prefix': self.prefix,
                **{name: self.directory / name for name in ['data', 'cache', 'tmp']}}

    def state(self):
        value = read_control(self.directory / 'state.json')
        fields = {'nonce', 'generation', 'stopped_generation', 'authorized', 'ended'}
        if (not isinstance(value, dict) or value.keys() != fields
                or value['nonce'] != self.nonce or type(value['generation']) is not int
                or value['generation'] < 0 or type(value['authorized']) is not bool
                or type(value['ended']) is not bool
                or (value['stopped_generation'] is not None
                    and (type(value['stopped_generation']) is not int
                         or not 0 <= value['stopped_generation'] <= value['generation']))):
            raise ValueError('Invalid session lifecycle state')
        return value

    def save(self, state):
        self.validate()
        write_control(self.directory / 'state.json', state)

    def launch(self, argv, kind, extra_env=None, stdout=None, stderr=None, *, on_launch=None):
        self.validate()
        setup = self.setup()
        if kind in ('probe', 'smoke60', 'fast1800') and not setup['policy_verified']:
            raise ValueError('Owned paths/debug policy not verified')
        state = self.state()
        if state['ended']:
            raise ValueError('Ended session cannot launch Wine')
        if kind == 'init':
            setup['policy_verified'] = False
            write_control(self.directory / 'setup.json', setup)
        state['generation'] += 1
        state['stopped_generation'] = None
        self.save(state)  # Durable before a child can exist.
        return bounded(self, argv, kind, extra_env, stdout=stdout, stderr=stderr, on_launch=on_launch)


def create_session(repo):
    repo = Path(os.path.abspath(repo))
    real_directory(repo)
    for path in (repo / 'build', repo / 'build/wine', repo / 'build/wine/sessions'):
        if not path.exists():
            path.mkdir(mode=0o700)
        real_directory(path, path.name == 'sessions')
    identifier = uuid.uuid4().hex
    directory = repo / 'build/wine/sessions' / identifier
    directory.mkdir(mode=0o700)
    (directory / 'prefix').mkdir(mode=0o700)
    for name in ['data', 'cache', 'tmp']:
        (directory / name).mkdir(mode=0o700)
    # Even version queries use the private prefix, never HOME/.wine.
    wine_lookup = _wine_lookup()
    match = re.fullmatch(r'wine(?:64)?(-[\w.-]+)?', wine_lookup.name)
    if not match:
        raise ValueError(f'Unsupported selected Wine installation: {wine_lookup}')
    # Pair logical siblings first: distro server links may relocate both the
    # directory and basename. Resolve only afterwards, without lexical abspath
    # normalization that would change symlink/.. filesystem lookup semantics.
    server_lookup = wine_lookup.with_name('wineserver' + (match[1] or ''))
    wine = wine_lookup.resolve(strict=True)
    server = server_lookup.resolve(strict=True)
    env = _owned_environment(directory, str(server), BOOTSTRAP_TEMP)
    tools, versions, failures = {}, {}, []
    for name, path in [('wine', wine), ('server', server)]:
        try:
            tools[name], versions[name] = tool_identity(path, env)
        except _VersionRejection as error:
            failures.append((name, error))
    paths = (f'wine lookup={ascii(str(wine_lookup))[1:-1]} canonical={ascii(str(wine))[1:-1]}; '
             f'wineserver lookup={ascii(str(server_lookup))[1:-1]} canonical={ascii(str(server))[1:-1]}')
    detail = '; '.join(f"{name} version={ascii(tools[name]['version'][:160])} "
                       f"capture={json.dumps(versions[name], ensure_ascii=True)}" for name in tools)
    if failures:
        # Wrapper evidence retains only the first 500 characters. All primary
        # role/cause summaries must precede paths, peer warnings and raw excerpts.
        summary = '; '.join(f'{name}: {error.summary}' for name, error in failures)
        diagnostics = '; '.join(f'{name}: {error}' for name, error in failures)
        raise ValueError(f'Wine tool identity rejected: {summary}; {paths}; {detail}; {diagnostics}')
    if versions['wine']['release'] != versions['server']['release']:
        raise ValueError(
            f'Wine/wineserver release mismatch; {paths}; {detail}')
    owner = {'version': 3, 'id': identifier, 'nonce': uuid.uuid4().hex,
             'repo': str(repo), 'uid': os.geteuid(), 'bounds': BOUNDS, 'tools': tools,
             'tool_versions': versions, 'crash_policy': [list(row) for row in CRASH_POLICY]}
    session = Session(repo, identifier, owner)
    owner['roots'] = {name: real_directory(path, name in ('sessions', 'session', 'prefix', 'data', 'cache', 'tmp'))
                      for name, path in session.roots().items()}
    write_control(directory / 'owner.json', owner, exclusive=True)
    write_control(directory / 'state.json', {'nonce': session.nonce, 'generation': 0,
                  'stopped_generation': None, 'authorized': False, 'ended': False}, exclusive=True)
    write_control(directory / 'setup.json', {'nonce': session.nonce, 'windows_tmp': None,
                  'roundtrip_tmp': None, 'policy_verified': False}, exclusive=True)
    session.validate()
    return session


def load_session(repo, identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{32}', identifier):
        raise ValueError('Invalid generated session ID')
    repo = Path(os.path.abspath(repo))
    directory = repo / 'build/wine/sessions' / identifier
    real_directory(directory, True)
    session = Session(repo, identifier, read_control(directory / 'owner.json'))
    session.validate()
    return session


def bounded(session, argv, kind, extra_env=None, *, stdout=None, stderr=None, on_launch=None):
    # Inherit outer capture streams. Never communicate() on Wine-descendant pipes.
    owned = session._server_environment() if kind in ('stop', 'wait') else session.environment()
    env = dict(owned, **(extra_env or {}))
    env.update({key: owned[key] for key in PRIVATE_ENV_KEYS})
    return wait_leader(['timeout', '--kill-after=5s', f'{BOUNDS[kind]}s', *argv],
                       cwd=session.repo, env=env,
                       stdout=stdout, stderr=stderr, on_launch=on_launch)


def _server_output(flag, output, stderr):
    """Observe regular files, relaying bounded control-safe diagnostics only."""
    empty = True
    for name, stream in [('stdout', output), ('stderr', stderr)]:
        stream.seek(0)
        raw = stream.read(4096)
        count = os.fstat(stream.fileno()).st_size
        if raw or count:
            empty = False
            print(f'Wine server {flag} {name}: bytes={count} excerpt={raw[:160]!r} '
                  f'excerpt_truncated={count > 160}', file=getattr(sys, name), flush=True)
    return empty


def wait_leader(argv, *, on_launch=None, **kwargs):
    # Sample at bounded-command creation, after all accounting/environment work.
    # Publish only successful creation, inside the same owning teardown path.
    launched = time.monotonic()
    process = subprocess.Popen(argv, close_fds=True, start_new_session=True, **kwargs)
    try:
        if on_launch is not None:
            on_launch(launched)
        return process.wait()
    except BaseException:
        # Own only this launched POSIX group; prefix cleanup separately handles
        # Windows descendants which escaped it. Never wait on their streams.
        with cleanup_signals():
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        raise


def initialize(session):
    return session.launch([session.owner['tools']['wine']['executable'], 'wineboot.exe', '--init'], 'init')


def _setup_utility(session, args):
    # Only fixed builtin utilities below call this private capture helper.
    with tempfile.TemporaryFile(dir=session.tmp) as output, tempfile.TemporaryFile(dir=session.tmp) as stderr:
        code = session.launch([session.owner['tools']['wine']['executable'], *args], 'setup',
                              {'WINEDLLOVERRIDES': 'winepath.exe=b;reg.exe=b'}, stdout=output, stderr=stderr)
        captured = []
        for stream in [output, stderr]:
            stream.seek(0)
            raw = stream.read(4097)
            if len(raw) > 4096 or os.fstat(stream.fileno()).st_size > 4096:
                raise ValueError('Oversized owned Wine setup output')
            captured.append(raw)
    if code:
        raise ValueError(f'Owned Wine setup {ntpath.basename(args[0])} exit={code}; stderr={captured[1][:160]!r}')
    try:
        text = [raw.decode('utf-8') for raw in captured]
    except UnicodeDecodeError:
        raise ValueError('Invalid UTF-8 owned Wine setup output') from None
    if captured[1]:
        print(f'Wine setup stderr: bytes={len(captured[1])} excerpt={captured[1][:160]!r}', file=sys.stderr, flush=True)
    return text[0]


def configure_crash_reporting(session):
    """Convert only our tmp root, then apply/query three fixed 64-bit values."""
    session.validate()
    setup = session.setup()
    setup['policy_verified'] = False
    write_control(session.directory / 'setup.json', setup)
    windows_tmp = _setup_utility(session, [WINEPATH, '-w', str(session.tmp)]).rstrip('\r\n')
    if not _windows_absolute(windows_tmp):
        raise ValueError('Owned Wine path conversion is not Windows absolute')
    roundtrip = _setup_utility(session, [WINEPATH, '-u', windows_tmp]).rstrip('\r\n')
    if roundtrip != str(session.tmp):
        raise ValueError('Owned Wine temp roundtrip mismatch')
    setup.update(windows_tmp=windows_tmp, roundtrip_tmp=roundtrip)
    session.validate()
    write_control(session.directory / 'setup.json', setup)
    for key, name, typ, value in CRASH_POLICY:
        _setup_utility(session, [REG, 'add', key, '/v', name, '/t', typ, '/d', value, '/f', '/reg:64'])
    for key, name, typ, value in CRASH_POLICY:
        output = _setup_utility(session, [REG, 'query', key, '/v', name, '/reg:64'])
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        header = key.replace('HKLM\\', 'HKEY_LOCAL_MACHINE\\', 1).replace('HKCU\\', 'HKEY_CURRENT_USER\\', 1)
        match = re.fullmatch(re.escape(name) + r'[ \t]+(REG_[A-Z]+)[ \t]+(.*)', lines[-1]) if lines else None
        accepted = [value, '0x0'] if typ == 'REG_DWORD' else [value]
        if (len(lines) != 2 or lines[0].casefold() != header.casefold() or not match
                or match[1] != typ or match[2] not in accepted):
            raise ValueError(f'Owned Wine debug policy verification failed: {name}')
    setup['policy_verified'] = True
    session.validate()
    write_control(session.directory / 'setup.json', setup)


@contextmanager
def cleanup_signals():
    # Block repeated catchable termination while the finite cleanup is in flight.
    previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


@dataclass
class CleanupResult:
    """Command-level Wine CLI completion, not independently proven quiescence."""
    ok: bool
    stop_returncode: int | None
    wait_returncode: int | None
    errors: list


def stop_session(session, end):
    errors = []
    codes = []
    silent = []
    with cleanup_signals():
        try:
            session.validate()
        except Exception as error:
            return CleanupResult(False, None, None, [str(error)])
        try:
            state = session.state()
        except Exception as error:
            errors.append(f'Lifecycle read: {error}')
            state = None
        if state is not None:
            already_stopped = state['stopped_generation'] == state['generation']
            if end:
                state.update(authorized=False, ended=True)
            try:
                session.save(state)
            except Exception as error:
                errors.append(f'Lifecycle write: {error}')
            if already_stopped:
                return CleanupResult(not errors, 0, 0, errors)
        for flag, kind in (('-k', 'stop'), ('-w', 'wait')):
            code, empty = None, False
            try:
                session.validate()  # Revalidate immediately before EACH destructive operation.
                # Regular streams avoid descendant-held pipe waits. Retain the
                # raw code even if observing/relaying its diagnostics then fails.
                with tempfile.TemporaryFile(dir=session.tmp) as output, tempfile.TemporaryFile(dir=session.tmp) as stderr:
                    code = bounded(session, [session.owner['tools']['server']['executable'], flag], kind,
                                   stdout=output, stderr=stderr)
                    empty = _server_output(flag, output, stderr)
            except Exception as error:
                errors.append(f'wineserver {flag}: {type(error).__name__}: {ascii(str(error)[:160])}')
            codes.append(code)
            silent.append(empty)
        # Wine 9 -k can silently exit1 when the owner is already gone or races
        # shutdown. Its silent -w=0 is CLI completion, not native lock/process proof.
        completed = codes == [0, 0] or (codes == [1, 0] and all(silent))
        if not completed:
            for flag, code in zip(('-k', '-w'), codes):
                if code:
                    errors.append(f'wineserver {flag} exit={code}')
        if state is not None and completed and not errors:
            state['stopped_generation'] = state['generation']
            try:
                session.save(state)
            except Exception as error:
                errors.append(f'Lifecycle write: {error}')
    return CleanupResult(not errors, *codes, errors)
