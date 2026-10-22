"""Fixed, owned, one-shot Wine publication validation; no executable selectors."""
import json
import math
import os
from pathlib import Path
import signal
import stat
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).absolute().parents[1]))
from wine import artifacts, prefix

REPORT = 'space-record-publication-report.json'
STORE_ROOT = 'space-record-publication-store'
LIMIT = 4096
COMPONENTS = (('cpp-022', 120, 0o022), ('cpp-002', 120, 0o002),
              ('store-write', 30, 0o002), ('store-read', 30, 0o002))


def facts(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def report_value(raw, binding):
    value = json.loads(raw, object_pairs_hook=artifacts._unique_object)
    build_id, device, inode = binding.split(':')
    expected = dict(version=1, backend='wine-posix', build_id=build_id,
                    module_device=int(device), module_inode=int(inode),
                    categories={'common': 'passed', 'host-policy': 'passed',
                                'mapping-authority': 'passed', 'native-windows': 'not-exercised'},
                    foreign_uid_probe='not-configured')
    if (not isinstance(value, dict) or set(value) != set(expected)
            or any(type(value[key]) is not int for key in ('version', 'module_device', 'module_inode'))
            or value != expected):
        # No configured real foreign-UID probe exists in this closed producer.
        raise ValueError('Publication report schema/identity/categories mismatch')
    return value


class ReportSink:
    """Parent-exclusive original object, never inherited, adopted or repaired."""
    def __init__(self, session):
        session.validate()
        self.path = session.tmp / REPORT
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            initial = os.fstat(self.fd)
            if (not stat.S_ISREG(initial.st_mode) or stat.S_IMODE(initial.st_mode) != 0o600
                    or initial.st_uid != os.geteuid() or initial.st_nlink != 1 or initial.st_size != 0
                    or os.get_inheritable(self.fd)):
                raise ValueError('Unsafe fresh publication report sink')
            self.origin = facts(initial)[:5]
        except BaseException:
            os.close(self.fd)
            raise

    def read(self, binding):
        info = os.fstat(self.fd)
        if facts(info)[:5] != self.origin or info.st_size > LIMIT:
            raise ValueError('Publication report original object changed')
        os.lseek(self.fd, 0, os.SEEK_SET)
        raw = os.read(self.fd, LIMIT + 1)
        if (len(raw) != info.st_size or len(raw) > LIMIT
                or facts(os.fstat(self.fd)) != facts(info) or facts(self.path.lstat()) != facts(info)):
            raise ValueError('Publication report path/read identity changed')
        return report_value(raw, binding), facts(info)

    def close(self):
        os.close(self.fd)


def validate_capture(session, record, proof):
    state = session.state()
    receipt = json.loads((session.repo / 'build/wine/windows/admission.json').read_text())
    authorization = receipt['authorization']
    if (not isinstance(proof, dict)
            or set(proof) != {'version', 'nonce', 'grant', 'start_generation', 'stopped_generation',
                             'bridge_build_id', 'reports', 'report_facts', 'foreign_uid_probe'}
            or type(proof['version']) is not int or proof['version'] != 1
            or proof['nonce'] != session.nonce or proof['grant'] != authorization['grant']
            or type(proof['start_generation']) is not int
            or proof['start_generation'] != authorization['stopped_generation']
            or proof['stopped_generation'] != proof['start_generation'] + 4
            or proof['stopped_generation'] != state['generation']
            or state['generation'] != state['stopped_generation'] or state['ended']
            or proof['bridge_build_id'] != receipt['bridge']['build_id']
            or proof['foreign_uid_probe'] != 'not-configured'
            or not isinstance(proof['reports'], list) or len(proof['reports']) != 2
            or not isinstance(proof['report_facts'], list) or len(proof['report_facts']) != 2):
        raise ValueError('Invalid stopped publication proof')
    identity = receipt['bridge']['identity']
    binding = f"{proof['bridge_build_id']}:{identity['module_device']}:{identity['module_inode']}"
    for report in proof['reports']:
        report_value(json.dumps(report), binding)
    path = session.tmp / REPORT
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = facts(os.fstat(fd))
        raw = os.read(fd, LIMIT + 1)
        if (before != proof['report_facts'][1] or facts(os.fstat(fd)) != before
                or facts(path.lstat()) != before or len(raw) != before[5]
                or report_value(raw, binding) != proof['reports'][1]):
            raise ValueError('Publication report changed before parent authorization')
    finally:
        os.close(fd)
    publication = record.get('publication', {})
    components = publication.get('components', [])
    terminal = dict(event='publication-result', version=1, passed=True,
                    bridge_build_id=proof['bridge_build_id'], foreign_uid_probe=proof['foreign_uid_probe'])
    if (record.get('step') != 'wine-publication' or record.get('outcome') != 'pass'
            or record.get('capture_complete') is not True or type(record.get('returncode')) is not int
            or record['returncode'] != 0 or record.get('capture_errors')
            or publication.get('result') != terminal or len(components) != 4):
        raise ValueError('Incomplete/nonpassing parent publication capture')
    for item, (name, deadline, mask) in zip(components, COMPONENTS):
        if (item.get('component') != name or item.get('deadline_seconds') != deadline
                or item.get('child_umask') != f'{mask:04o}'
                or type(item.get('command_returncode')) is not int or item['command_returncode'] != 0
                or type(item.get('launched_monotonic')) is not float
                or not math.isfinite(item['launched_monotonic'])
                or item.get('hard_deadline_monotonic') != item['launched_monotonic'] + deadline):
            raise ValueError('Invalid parent publication component capture')


def validate_publication(session):
    observer = os.environ.pop(artifacts.APPLICATION_OBSERVER_ENV, None)
    fd = int(observer) if observer is not None else None
    if fd is not None:
        os.set_inheritable(fd, False)
    def observe(event, **fields):
        if fd is not None:
            raw = (json.dumps(dict(event=event, **fields)) + '\n').encode('ascii')
            if os.write(fd, raw) != len(raw):
                raise OSError('Incomplete private publication observation')
    passed = False
    store_fd = None
    try:
        config = artifacts.configuration(session, 'publication')
        state = session.state()
        grant, start = state['grant'], state['generation']
        state.update(authorized_for=None, grant=None, phase='publication-consumed')
        session.save(state)  # Durable consumption BEFORE any component launch.
        overlay = session.repo / 'build/wine/windows'
        receipt = json.loads((overlay / 'admission.json').read_text())
        before = artifacts.verify(overlay, 'wine-overlay')
        assets = str(overlay / 'assets')
        fennel = f'{assets}/lua/?.fnl;{assets}/lua/?/init.fnl'
        env = dict(WINEDLLOVERRIDES='space_record_publication=b;space_record_publication_tests=b;' + config['backend'],
                   WINEDLLPATH=config['WINEDLLPATH'], SPACE_BIN=str(overlay / 'space-cli.exe'),
                   SPACE_ASSETS_PATH=assets, FENNEL_PATH=fennel, FENNEL_MACRO_PATH=fennel,
                   SPACE_DISABLE_AUDIO='1', SKIP_KEYRING_TESTS='1',
                   SPACE_WINE_PUBLICATION_BINDING=config['SPACE_WINE_PUBLICATION_BINDING'],
                   SPACE_WINE_PUBLICATION_TEST_BINDING=config['SPACE_WINE_PUBLICATION_TEST_BINDING'])
        # Never adopt an existing directory. The no-argument PE helpers derive
        # this exact child from the already verified Windows TEMP handoff, not
        # Windows known-folder defaults or XDG_DATA_HOME.
        store_root = session.tmp / STORE_ROOT
        store_root.mkdir(mode=0o700)
        store_identity = prefix.real_directory(store_root, True)
        store_fd = os.open(store_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        if [os.fstat(store_fd).st_dev, os.fstat(store_fd).st_ino] != store_identity or os.listdir(store_fd):
            raise ValueError('Publication store root is not fresh')
        reports, snapshots = [], []
        for name, deadline, mask in COMPONENTS:
            if prefix.real_directory(store_root, True) != store_identity:
                raise ValueError('Publication store root was substituted')
            if name == 'store-write' and os.listdir(store_fd):
                raise ValueError('Publication store root changed before writer')
            sink = ReportSink(session) if name.startswith('cpp-') else None
            try:
                print(f'Wine publication: {name} deadline={deadline}s child-umask={mask:04o}', flush=True)
                args = ([str(overlay / 'test_record_publication.exe')] if sink else
                        [str(overlay / 'space-cli.exe'), '-m', 'tests.wine-record-publication:' + name.removeprefix('store-')])
                def launched(at):
                    observe('launch', component=name, launched_monotonic=at, hard_deadline_monotonic=at + deadline)
                code = session.launch([config['wine'], *args], name, env, child_umask=mask, on_launch=launched)
                observe('result', component=name, command_returncode=code)
                if code:
                    return code
                if artifacts.verify(overlay, 'wine-overlay') != before:
                    raise ValueError('Publication changed overlay inventory')
                if artifacts.publication_manifest(session)['build_id'] != receipt['bridge']['build_id']:
                    raise ValueError('Publication pair changed during validation')
                if artifacts.support_manifest(session) != receipt['support']:
                    raise ValueError('Publication test support changed during validation')
                if prefix.real_directory(store_root, True) != store_identity:
                    raise ValueError('Publication store root was substituted')
                if sink:
                    report, snapshot = sink.read(config['SPACE_WINE_PUBLICATION_BINDING'])
                    reports.append(report)
                    snapshots.append(snapshot)
                    if name == 'cpp-022':
                        if sink.read(config['SPACE_WINE_PUBLICATION_BINDING']) != (report, snapshot):
                            raise ValueError('Stale publication report changed before removal')
                        sink.path.unlink()
            finally:
                if sink:
                    sink.close()
        artifacts.require_cleanup(prefix.stop_session(session, end=False))
        state = session.state()
        proof = dict(version=1, nonce=session.nonce, grant=grant, start_generation=start,
                     stopped_generation=state['stopped_generation'], bridge_build_id=receipt['bridge']['build_id'],
                     reports=reports, report_facts=snapshots, foreign_uid_probe='not-configured')
        prefix.write_control(session.directory / 'publication.json', proof, exclusive=True)
        state['phase'] = 'publication-checked'
        session.save(state)
        observe('publication-result', version=1, passed=True, bridge_build_id=proof['bridge_build_id'],
                foreign_uid_probe=proof['foreign_uid_probe'])
        passed = True
        return 0
    finally:
        try:
            if not passed:
                cleanup = prefix.stop_session(session, end=True)
                if not cleanup.ok:
                    print('Owned Wine cleanup failed: ' + '; '.join(cleanup.errors), file=sys.stderr, flush=True)
        finally:
            if store_fd is not None:
                os.close(store_fd)
            if fd is not None:
                os.close(fd)


def main():
    if len(sys.argv) != 1 or not os.environ.get('SPACE_WINE_SESSION_ID'):
        raise ValueError('Fixed publication validation requires owned parent handoff and no arguments')
    with artifacts.locked_build():
        session = prefix.load_session(artifacts.ROOT, os.environ['SPACE_WINE_SESSION_ID'])
        return validate_publication(session)


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise InterruptedError(f'Publication interrupted by signal {signum}')
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        code = main() or 0
        sys.exit(128 - code if code < 0 else code)
    except (OSError, ValueError, KeyError) as error:
        print(f'Wine publication: refused: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
