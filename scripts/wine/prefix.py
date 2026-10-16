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
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import uuid

BOUNDS = {"init": 90, "probe": 60, "smoke60": 60, "fast1800": 1800,
          "stop": 10, "wait": 15, "kill_after": 5}


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


def resolve_wine():
    selected = os.environ.get('WINE_CMD') or shutil.which('wine64') or shutil.which('wine')
    executable = shutil.which(selected) if selected else None
    if not executable:
        raise ValueError('Missing required command: wine64 or wine (or selected WINE_CMD)')
    return Path(executable).resolve(strict=True)


def tool_identity(path, env):
    # A regular temporary stream cannot be retained as a pipe by descendants.
    with tempfile.TemporaryFile(mode='w+') as output:
        code = wait_leader(['timeout', '--kill-after=5s', '60s', str(path), '--version'],
                           env=env, stdout=output)
        if code:
            raise ValueError(f'Wine tool version failed: {path} exit={code}')
        output.seek(0)
        version = output.read(4097).strip()
        if len(version) > 4096:
            raise ValueError('Oversized Wine tool version')
    return {'executable': str(path), 'version': version,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def release(version):
    match = re.fullmatch(r'(?:wine-|Wine )(.+)', version)
    if not match:
        raise ValueError(f'Unsupported Wine release identity: {version}')
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

    def environment(self):
        return dict(os.environ, WINEPREFIX=str(self.prefix), WINEARCH='win64',
                    WINESERVER=self.owner['tools']['server']['executable'])

    def validate(self):
        expected = self.owner
        if (expected['version'] != 2 or expected['id'] != self.id
                or expected['uid'] != os.geteuid() or expected['bounds'] != BOUNDS
                or expected['repo'] != str(self.repo) or not re.fullmatch('[0-9a-f]{32}', self.nonce)):
            raise ValueError('Invalid session ownership')
        for name, path in self.roots().items():
            identity = real_directory(path, name in ('sessions', 'session', 'prefix'))
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
                'sessions': self.directory.parent, 'session': self.directory, 'prefix': self.prefix}

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

    def launch(self, argv, kind, extra_env=None):
        self.validate()
        state = self.state()
        if state['ended']:
            raise ValueError('Ended session cannot launch Wine')
        state['generation'] += 1
        state['stopped_generation'] = None
        self.save(state)  # Durable before a child can exist.
        return bounded(self, argv, kind, extra_env)


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
    # Even version queries use the private prefix, never HOME/.wine.
    wine = resolve_wine()
    match = re.fullmatch(r'wine(?:64)?(-[\w.-]+)?', wine.name)
    if not match:
        raise ValueError(f'Unsupported selected Wine installation: {wine}')
    server = wine.with_name('wineserver' + (match[1] or '')).resolve(strict=True)
    if server.parent != wine.parent or server.name != 'wineserver' + (match[1] or ''):
        raise ValueError('Wine/wineserver must share a canonical installation and suffix')
    env = dict(os.environ, WINEPREFIX=str(directory / 'prefix'), WINEARCH='win64', WINESERVER=str(server))
    tools = {'wine': tool_identity(wine, env), 'server': tool_identity(server, env)}
    if release(tools['wine']['version']) != release(tools['server']['version']):
        raise ValueError('Wine/wineserver release mismatch')
    owner = {'version': 2, 'id': identifier, 'nonce': uuid.uuid4().hex,
             'repo': str(repo), 'uid': os.geteuid(), 'bounds': BOUNDS, 'tools': tools}
    session = Session(repo, identifier, owner)
    owner['roots'] = {name: real_directory(path, name in ('sessions', 'session', 'prefix'))
                      for name, path in session.roots().items()}
    write_control(directory / 'owner.json', owner, exclusive=True)
    write_control(directory / 'state.json', {'nonce': session.nonce, 'generation': 0,
                  'stopped_generation': None, 'authorized': False, 'ended': False}, exclusive=True)
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


def bounded(session, argv, kind, extra_env=None):
    # Inherit outer capture streams. Never communicate() on Wine-descendant pipes.
    return wait_leader(['timeout', '--kill-after=5s', f'{BOUNDS[kind]}s', *argv],
                       cwd=session.repo, env=dict(session.environment(), **(extra_env or {})))


def wait_leader(argv, **kwargs):
    process = subprocess.Popen(argv, close_fds=True, start_new_session=True, **kwargs)
    try:
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
    ok: bool
    stop_returncode: int | None
    wait_returncode: int | None
    errors: list


def stop_session(session, end):
    errors = []
    codes = []
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
            try:
                session.validate()  # Revalidate immediately before EACH destructive operation.
                code = bounded(session, [session.owner['tools']['server']['executable'], flag], kind)
                codes.append(code)
                if code:
                    errors.append(f'wineserver {flag} exit={code}')
            except Exception as error:
                codes.append(None)
                errors.append(f'wineserver {flag}: {error}')
        if state is not None and codes == [0, 0]:
            state['stopped_generation'] = state['generation']
            try:
                session.save(state)
            except Exception as error:
                errors.append(f'Lifecycle write: {error}')
    return CleanupResult(not errors, *codes, errors)
