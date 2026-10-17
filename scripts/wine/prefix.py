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
import sys
import tempfile
import uuid

BOUNDS = {"init": 90, "probe": 60, "smoke60": 60, "fast1800": 1800,
          "stop": 10, "wait": 15, "kill_after": 5}
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
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
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
    env = dict(os.environ, WINEPREFIX=str(directory / 'prefix'), WINEARCH='win64', WINESERVER=str(server))
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
    owner = {'version': 2, 'id': identifier, 'nonce': uuid.uuid4().hex,
             'repo': str(repo), 'uid': os.geteuid(), 'bounds': BOUNDS, 'tools': tools,
             'tool_versions': versions}
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


def bounded(session, argv, kind, extra_env=None, *, stdout=None, stderr=None):
    # Inherit outer capture streams. Never communicate() on Wine-descendant pipes.
    return wait_leader(['timeout', '--kill-after=5s', f'{BOUNDS[kind]}s', *argv],
                       cwd=session.repo, env=dict(session.environment(), **(extra_env or {})),
                       stdout=stdout, stderr=stderr)


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
                with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as stderr:
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
