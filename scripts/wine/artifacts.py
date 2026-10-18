"""Private Windows artifact lifecycle; never execute generated configuration as code.

Manifests are ownership/integrity inventories, not a security boundary against a
hostile user who can rewrite this checkout. Cooperative writers lock build/.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import signal
import secrets
import re
import errno

if __package__:
    from . import prefix, build_publication, publication_toolchain
else:
    sys.path.insert(0, str(Path(__file__).absolute().parents[1]))
    from wine import prefix, build_publication, publication_toolchain

ROOT = Path(__file__).absolute().parents[2]
BUILD = ROOT / "build"
PACKAGE = BUILD / "dist/windows"
OVERLAY = BUILD / "wine/windows"
MARKER = ".space-windows-artifact-v1.json"
FORBIDDEN = "bcryptprimitives.dll"
PAIR_NAMES = {'space_record_publication.dll', 'space_record_publication.so'}
IDENTITY_REPORT = 'space-record-publication-identity.json'
IDENTITY_LIMIT = 4096
PUBLICATION_BUILD = ('timeout', '--kill-after=5s', '900s', 'python3', 'scripts/wine/build_publication.py')
BOOTSTRAP = ('timeout', '--kill-after=5s', '480s', 'python3', 'scripts/wine/artifacts.py', 'prepare-bootstrap')
BUILTIN = "bcryptprimitives=b;advapi32,cryptbase=b"
COMPAT = "bcryptprimitives=n;advapi32,cryptbase=b"
# Producer and capture parser share the encoded, newline-excluding line budget.
CLEANUP_LINE_BYTES = 4096
CLEANUP_MARKER = 'Wine cleanup: '
CLEANUP_FIELDS = {'ok', 'stop_returncode', 'wait_returncode', 'errors',
                  'error_count', 'errors_truncated', 'error_excerpt_truncated'}
APPLICATION_OBSERVER_ENV = 'SPACE_WINE_APPLICATION_OBSERVER_FD'
TZ_FILES = ("africa antarctica asia australasia backward etcetera europe northamerica "
            "southamerica leapseconds version windowsZones.xml LICENSE CLDR-LICENSE.txt").split()


def safe_path(path):
    path = Path(os.path.abspath(path))
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise ValueError(f"Symlinked artifact path: {part}")
    return path


def inventory(path):
    safe_path(path)
    if not path.is_dir():
        raise ValueError(f"Not an artifact directory: {path}")
    entries = {}
    for item in sorted(path.rglob("*")):
        mode = item.lstat().st_mode
        relative = item.relative_to(path).as_posix()
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError(f"Unsafe artifact entry: {item}")
        if relative == MARKER:
            continue
        entries[relative] = "directory" if item.is_dir() else hashlib.sha256(item.read_bytes()).hexdigest()
    return entries


def seal(path, kind):
    (path / MARKER).write_text(json.dumps({"version": 1, "owner": "space-windows-diagnostics",
                                         "kind": kind, "inventory": inventory(path)}, sort_keys=True) + "\n")


def verify(path, kind):
    entries = inventory(path)
    marker = path / MARKER
    expected = {"version": 1, "owner": "space-windows-diagnostics", "kind": kind, "inventory": entries}
    if json.loads(marker.read_text()) != expected:
        raise ValueError(f"Unrecognized or changed owned output: {path}")
    return entries


def clean_native(path):
    entries = verify(path, "native-package")
    if any(Path(name).name.casefold() in {FORBIDDEN, *PAIR_NAMES} for name in entries):
        raise ValueError(f"Forbidden Wine helper in native package: {path}")
    for name in ("space.exe", "space-cli.exe", "assets"):
        if name not in entries:
            raise ValueError(f"Missing native payload entry: {name}")
    return entries


@contextmanager
def locked_build():
    safe_path(BUILD)
    BUILD.mkdir(exist_ok=True)
    fd = os.open(BUILD, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def check_replace(path, kind):
    safe_path(path)
    if not path.exists():
        return
    if (path / MARKER).exists():
        verify(path, kind)
        return
    # The only legacy migration is the fixed, recognizable standard package.
    # Preserve the ENTIRE tree, including unrelated files and stale helpers.
    saved = PACKAGE.with_name("windows.pre-diagnostics")
    if path != PACKAGE or kind != "native-package":
        raise ValueError(f"Unowned output, refusing replacement: {path}")
    inventory(path)
    if not all((path / name).is_file() for name in ("space.exe", "space-cli.exe")):
        raise ValueError(f"Ambiguous legacy package: {path}")
    safe_path(saved)
    if saved.exists():
        raise ValueError(f"Legacy evidence destination already exists: {saved}")


def install(stage, path, kind):
    check_replace(path, kind)
    if path.exists():
        if (path / MARKER).exists():
            # Delete exactly the verified inventory, never an arbitrary tree.
            entries = verify(path, kind)
            for name in sorted(entries, key=lambda s: (s.count("/"), s), reverse=True):
                item = path / name
                item.rmdir() if entries[name] == "directory" else item.unlink()
            (path / MARKER).unlink()
            path.rmdir()
        else:
            path.rename(PACKAGE.with_name("windows.pre-diagnostics"))
    stage.rename(path)


@contextmanager
def private_stage(parent):
    safe_path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    # Generated private (0700) temporary only; never accept a cleanup argument.
    stage = Path(tempfile.mkdtemp(prefix=".space-windows-", dir=parent))
    try:
        yield stage
    finally:
        if stage.exists():
            # Refuse linked/special entries even in our private temporary.
            inventory(stage)
            shutil.rmtree(stage)


def copy_tree(source, dest):
    inventory(source)  # Reject links before copytree can follow them.
    shutil.copytree(source, dest)


def package(destination):
    source = safe_path(Path(os.environ.get("BUILD_DIR", BUILD / "windows")))
    destination = safe_path(destination)
    # Never allow a requested output to replace source inputs or their parents.
    inputs = (source, ROOT / "assets", ROOT / "external", ROOT / "scripts")
    if any(destination == p or destination in p.parents or p in destination.parents for p in inputs):
        raise ValueError("Package destination overlaps a source tree")
    check_replace(destination, "native-package")
    for item in source.iterdir():
        if item.is_symlink():
            raise ValueError(f"Symlink in native build output: {item}")
    for name in ("space.exe", "space-cli.exe"):
        if not (source / name).is_file():
            raise ValueError(f"Missing target executable: {source / name}")
    tzdata = ROOT / "external/date/tzdata"
    for name in TZ_FILES:
        if not (safe_path(tzdata / name)).is_file():
            raise ValueError(f"Missing bundled Windows temporal tzdata file: {name}")
    manifests = sorted((ROOT / "external/temporal").glob("*/DEPENDENCY_MANIFEST.json"))
    if ROOT / "external/temporal/libical/DEPENDENCY_MANIFEST.json" not in manifests:
        raise ValueError("Missing temporal dependency manifest: libical")
    # Native dependency staging remains native-only; Wine preparation never calls it.
    for name in ("space.exe", "space-cli.exe"):
        subprocess.run([str(ROOT / "scripts/prepare-windows-runtime.sh"), str(source / name)], check=True)
    with private_stage(destination.parent) as stage:
        for name in ("space.exe", "space-cli.exe"):
            shutil.copy2(safe_path(source / name), stage / name)
        copy_tree(ROOT / "assets", stage / "assets")
        copy_tree(tzdata, stage / "tzdata")
        for manifest in manifests:
            safe_path(manifest)
            dest = stage / "external/temporal" / manifest.parent.name
            dest.mkdir(parents=True)
            shutil.copy2(manifest, dest / manifest.name)
        for dll in source.iterdir():
            if dll.suffix.casefold() == ".dll" and dll.name.casefold() not in {FORBIDDEN, *PAIR_NAMES}:
                safe_path(dll)
                if not dll.is_file():
                    raise ValueError(f"Invalid native DLL: {dll}")
                shutil.copy2(dll, stage / dll.name)
        seal(stage, "native-package")
        clean_native(stage)
        install(stage, destination, "native-package")
    clean_native(destination)
    print(f"Windows runtime package prepared in {destination}", flush=True)


def compiler(source, output, *flags):
    subprocess.run([os.environ.get("CC", "x86_64-w64-mingw32-gcc-posix"),
                    "-Wall", "-Wextra", "-Werror", "-Os", "-o", str(output),
                    str(ROOT / "scripts/wine" / source), *flags], check=True)


def build_compat(path):
    compiler("process_prng_compat.c", path / FORBIDDEN, "-shared", "-ladvapi32")


@contextmanager
def owned_file_write(path, name):
    before = verify(path, "wine-overlay")
    try:
        yield
    finally:
        after = inventory(path)
        changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
        if changed - {name} or after.get(name) == "directory":
            raise ValueError(f"Unexpected overlay writes; refusing to claim ownership: {changed}")
        seal(path, "wine-overlay")


def launch_conditions():
    return {key: os.environ.get(key) for key in ("DISPLAY", "WAYLAND_DISPLAY")}


def publication_manifest(session):
    session.validate()
    recognized = build_publication._recognized_output(session.repo / 'build/wine-publication')
    if recognized is None:
        raise ValueError('Missing owned publication builtin pair')
    manifest = recognized[1]
    if (manifest['runtime'] != session.owner['tools']['wine']
            or manifest['toolchain']['inputs'] != build_publication._sources(session.repo)):
        raise ValueError('Publication runtime/source binding changed')
    publication_toolchain.verify_toolchain(manifest['toolchain']['identity'])
    return manifest


def _verify_discovery_copy(manifest, overlay):
    prefix.real_directory(overlay, True)
    path = safe_path(overlay / Path(build_publication.PAIR[0]).name)
    digest = hashlib.sha256(build_publication._regular(path)).hexdigest()
    if digest != manifest['files'][build_publication.PAIR[0]]['sha256']:
        raise ValueError('Publication discovery copy does not match the verified pair')


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate publication identity field')
        value[key] = item
    return value


def _identity_file(session):
    session.validate()
    path = session.tmp / IDENTITY_REPORT
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or info.st_size > IDENTITY_LIMIT or info.st_mode & 0o022):
            raise ValueError('Unsafe publication identity report')
        def stable(value):
            return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_nlink,
                    value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        raw = os.read(fd, IDENTITY_LIMIT + 1)
        if (len(raw) != info.st_size or len(raw) > IDENTITY_LIMIT
                or stable(os.fstat(fd)) != stable(info) or stable(path.lstat()) != stable(info)):
            raise ValueError('Publication identity report changed')
    finally:
        os.close(fd)
    return json.loads(raw, object_pairs_hook=_unique_object), stable(info)


def validate_bridge_identity(manifest, identity, repo, challenge=None):
    fields = {'version', 'size', 'abi', 'challenge', 'echo', 'pe_build_id', 'unix_build_id',
              'module_device', 'module_inode', 'architecture', 'features'}
    if not isinstance(identity, dict) or set(identity) != fields:
        raise ValueError('Invalid publication identity fields')
    expected = dict(version=1, size=112, abi=manifest['abi'], architecture=0x8664, features=1)
    if (any(type(identity[key]) is not int or identity[key] != value for key, value in expected.items())
            or not isinstance(identity['challenge'], str) or not re.fullmatch('[0-9a-f]{16}', identity['challenge'])
            or identity['echo'] != identity['challenge']
            or (challenge is not None and identity['challenge'] != challenge)
            or identity['pe_build_id'] != manifest['build_id'] or identity['unix_build_id'] != manifest['build_id']):
        raise ValueError('Publication identity ABI/challenge/build mismatch')
    info = (repo / 'build/wine-publication' / build_publication.PAIR[1]).lstat()
    if (any(type(identity[key]) is not int or not 0 <= identity[key] < 2**64
            for key in ('module_device', 'module_inode'))
            or identity['module_device'] != info.st_dev or identity['module_inode'] != info.st_ino):
        raise ValueError('Publication Unix module device/inode mismatch')
    overlay = repo / 'build/wine/windows'
    _verify_discovery_copy(manifest, overlay)
    entries = verify(overlay, 'wine-overlay')
    if 'admission.json' in entries:
        receipt = json.loads((overlay / 'admission.json').read_text())
        if receipt.get('payload') != {key: value for key, value in entries.items() if key != 'admission.json'}:
            raise ValueError('Publication discovery copy/payload receipt binding changed')
    return {key: manifest[key] for key in ('abi', 'build_id', 'toolchain', 'files')} | {'identity': identity}


def _remove_identity_report(session, verified):
    value, info = _identity_file(session)
    if (value, info) != verified:
        raise ValueError('Publication retry report changed; refusing removal')
    (session.tmp / IDENTITY_REPORT).unlink()


def probe(session, backend, manifest):
    session.validate()
    _verify_discovery_copy(manifest, OVERLAY)
    before = verify(OVERLAY, "wine-overlay")
    report = session.tmp / IDENTITY_REPORT
    if report.exists() or report.is_symlink():
        raise ValueError('Publication report already exists; refusing unverified removal')
    challenge = secrets.token_hex(8)
    try:
        fd = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    except OSError as error:
        print(f'Wine admission: phase=report-allocate errno={error.errno or errno.EIO}', file=sys.stderr, flush=True)
        raise OSError(error.errno or errno.EIO, 'Publication report allocation refused') from None
    code = 20
    bridge = verified = None
    try:
        try:
            initial = os.fstat(fd)
            origin = (initial.st_dev, initial.st_ino, initial.st_mode, initial.st_uid, initial.st_nlink)
            if (not stat.S_ISREG(initial.st_mode) or stat.S_IMODE(initial.st_mode) != 0o600
                    or initial.st_uid != os.geteuid() or initial.st_nlink != 1 or initial.st_size != 0
                    or os.get_inheritable(fd)):
                raise ValueError('Invalid fresh report origin')
        except (OSError, ValueError) as error:
            print(f'Wine admission: phase=report-allocate errno={getattr(error, "errno", None) or errno.EINVAL}',
                  file=sys.stderr, flush=True)
        else:
            print(f"Wine admission: probe backend={backend} deadline=60s kill-after=5s", flush=True)
            code = session.launch([session.owner['tools']['wine']['executable'],
                                   str(OVERLAY / "process-prng-probe.exe")], 'probe', {
                                       'WINEDLLOVERRIDES': 'space_record_publication=b;' + backend,
                                       'WINEDLLPATH': str(BUILD / 'wine-publication/modules'),
                                       'SPACE_WINE_IDENTITY_CHALLENGE': challenge})
            if code in (0, 10):
                try:
                    verified = _identity_file(session)
                    if publication_manifest(session) != manifest:
                        raise ValueError('Publication pair changed during probe')
                    bridge = validate_bridge_identity(manifest, verified[0], session.repo, challenge)
                    held = os.fstat(fd)
                    facts = (held.st_dev, held.st_ino, held.st_mode, held.st_uid, held.st_nlink,
                             held.st_size, held.st_mtime_ns, held.st_ctime_ns)
                    # Legitimate writes change size/times, never the original
                    # dev/inode/type/mode/UID/link identity retained by this fd.
                    if facts[:5] != origin or facts != verified[1]:
                        raise ValueError('Publication report origin changed')
                except (OSError, ValueError, KeyError, TypeError) as error:
                    print(f'Wine admission: phase=report-verify errno={getattr(error, "errno", None) or errno.EINVAL}',
                          file=sys.stderr, flush=True)
                    code, bridge, verified = 20, None, None
        if inventory(OVERLAY) != before:
            raise ValueError("Probe modified the overlay; refusing to claim unknown output")
    finally:
        try:
            os.close(fd)
        except OSError as error:
            print(f'Wine admission: phase=report-close errno={error.errno or errno.EIO}', file=sys.stderr, flush=True)
            if code in (0, 10):
                code, bridge, verified = 20, None, None
    detail = (" (admission timeout, not crypto absence)" if code == 124 else
              " (SIGKILL/forced admission timeout, not crypto absence)" if code in (137, -9) else "")
    print(f"Wine admission: probe exit={code}" +
          detail, flush=True)
    return code, bridge, verified


def _prepare_payload(session):
    manifest = publication_manifest(session)
    package_before = clean_native(PACKAGE)
    check_replace(OVERLAY, "wine-overlay")
    conditions = launch_conditions()
    code = prefix.initialize(session)
    if code:
        raise ValueError(f"Wine initialization failed: exit={code}")
    prefix.configure_crash_reporting(session)
    with private_stage(OVERLAY.parent) as stage:
        # Copy only the immutable, verified native package, never build leftovers.
        for item in PACKAGE.iterdir():
            if item.name == MARKER:
                continue
            copy_tree(item, stage / item.name) if item.is_dir() else shutil.copy2(item, stage / item.name)
        definition = '-DSRP_BUILD_ID_BYTES={' + ','.join(hex(byte) for byte in bytes.fromhex(manifest['build_id'])) + '}'
        compiler("probe.c", stage / "process-prng-probe.exe", '-I', str(ROOT / 'src'), definition)
        # Wine9 needs a Windows-side discovery image before basename loading
        # reaches the builtin architecture pair through the fixed WINEDLLPATH.
        source = BUILD / 'wine-publication' / build_publication.PAIR[0]
        shutil.copy2(source, stage / source.name)
        _verify_discovery_copy(manifest, stage)
        if publication_manifest(session) != manifest:
            raise ValueError('Publication pair changed while staging the discovery copy')
        seal(stage, "wine-overlay")
        install(stage, OVERLAY, "wine-overlay")
    backend = BUILTIN
    code, bridge, report = probe(session, backend, manifest)
    if code == 10:
        _remove_identity_report(session, report)
        print("Wine admission: confirmed absence; building Wine-only bridge", flush=True)
        with owned_file_write(OVERLAY, FORBIDDEN):
            build_compat(OVERLAY)
        backend = COMPAT
        code, bridge, report = probe(session, backend, manifest)
    if code != 0:
        raise ValueError(f"Wine API admission failed: probe exit={code}; no fallback/retry authorized")
    if clean_native(PACKAGE) != package_before:
        raise ValueError("Native package changed during Wine admission")
    cleanup = prefix.stop_session(session, end=False)
    require_cleanup(cleanup)
    receipt = {"version": 3, "ownedSession": session.binding(), 'bridge': bridge,
               "tools": session.owner["tools"], "conditions": conditions,
               "backend": backend, "package": package_before,
               "payload": verify(OVERLAY, "wine-overlay")}
    with owned_file_write(OVERLAY, "admission.json"):
        (OVERLAY / "admission.json").write_text(json.dumps(receipt, sort_keys=True) + "\n")
    print("Wine admission: API contract admitted (not entropy certification)", flush=True)
    state = session.state()
    state['authorized'] = True
    session.save(state)
    return 0


def configuration(session):
    session.validate()
    state = session.state()
    if (state['ended'] or not state['authorized']
            or state['stopped_generation'] != state['generation']):
        raise ValueError('Wine session authorization ended/consumed or not quiescent')
    entries = verify(OVERLAY, "wine-overlay")
    native = clean_native(PACKAGE)
    receipt = json.loads((OVERLAY / "admission.json").read_text())
    backend = receipt.get("backend")
    payload = {k: v for k, v in entries.items() if k != "admission.json"}
    if (type(receipt.get('version')) is not int or receipt.get("version") != 3 or backend not in (BUILTIN, COMPAT)
            or receipt.get("ownedSession") != session.binding()
            or receipt.get("tools") != session.owner['tools']
            or receipt.get("payload") != payload or receipt.get("package") != native
            or receipt.get("conditions") != launch_conditions()):
        raise ValueError("Wine admission receipt does not match payload/package/launch conditions")
    manifest = publication_manifest(session)
    bridge = receipt.get('bridge')
    if (not isinstance(bridge, dict) or set(bridge) != {'abi', 'build_id', 'toolchain', 'files', 'identity'}
            or bridge != validate_bridge_identity(manifest, bridge['identity'], session.repo)):
        raise ValueError('Wine admission bridge binding changed')
    identity = session.owner['tools']['wine']
    if os.environ.get("WINE_CMD") and str(prefix.resolve_wine()) != identity["executable"]:
        raise ValueError("WINE_CMD differs from admitted Wine")
    if (backend == COMPAT) != (FORBIDDEN in payload):
        raise ValueError("Backend does not match overlay helper inventory")
    return {'wine': identity['executable'], 'backend': backend,
            'WINEDLLPATH': str(BUILD / 'wine-publication/modules')}


def require_cleanup(result):
    if not result.ok:
        raise ValueError('Owned Wine cleanup failed: ' + '; '.join(result.errors))


def cleanup_marker(result):
    errors = [str(error) for error in result.errors[:8]]
    excerpts = [error[:500] for error in errors]
    truncated = [excerpt != error for excerpt, error in zip(excerpts, errors)]
    value = {'ok': result.ok, 'stop_returncode': result.stop_returncode,
             'wait_returncode': result.wait_returncode, 'errors': excerpts,
             'error_count': len(result.errors), 'errors_truncated': len(result.errors) > len(errors) or any(truncated),
             'error_excerpt_truncated': truncated}
    while True:
        marker = CLEANUP_MARKER + json.dumps(value, ensure_ascii=True)
        if len(marker.encode('utf-8')) <= CLEANUP_LINE_BYTES:
            return marker
        # At most eight 500-character excerpts; shrink only diagnostic text,
        # never native stop/wait fields, counts or explicit truncation flags.
        index = max(range(len(excerpts)), key=lambda i: len(excerpts[i]))
        excerpts[index] = excerpts[index][:len(excerpts[index]) // 2]
        truncated[index] = True
        value['errors_truncated'] = True


def owning_operation(session, operation):
    primary = None
    code = 1
    try:
        code = operation()
    except BaseException as error:
        primary = error
    finally:
        result = prefix.stop_session(session, end=True)
        if not result.ok:
            print('Owned Wine cleanup failed: ' + '; '.join(result.errors), file=sys.stderr, flush=True)
    if primary is not None:
        raise primary
    return code if code else (0 if result.ok else 1)


def prepare(session):
    """Public composite: independently bounded children, no held build inode lock."""
    def composite():
        env = dict(session.environment(), SPACE_WINE_SESSION_ID=session.id)
        for args in (PUBLICATION_BUILD, BOOTSTRAP):
            code = prefix.wait_leader(list(args), cwd=ROOT, env=env)
            if code:
                return code
        return 0
    try:
        code = composite()
    except BaseException:
        result = prefix.stop_session(session, end=True)
        if not result.ok:
            print('Owned Wine cleanup failed: ' + '; '.join(result.errors), file=sys.stderr, flush=True)
        raise
    if code:
        result = prefix.stop_session(session, end=True)
        if not result.ok:
            print('Owned Wine cleanup failed: ' + '; '.join(result.errors), file=sys.stderr, flush=True)
    return code


def prepare_bootstrap(session):
    try:
        return _prepare_payload(session)
    except BaseException:
        result = prefix.stop_session(session, end=True)
        if not result.ok:
            print('Owned Wine cleanup failed: ' + '; '.join(result.errors), file=sys.stderr, flush=True)
        raise


def execute_admitted(session, mode):
    def execute():
        if mode not in ('smoke60', 'fast1800'):
            raise ValueError('Invalid private execution mode')
        config = configuration(session)
        if mode == 'fast1800':
            for key in ('TEST_FILTER', 'SPACE_TEST_CASE_TIMEOUT_SECONDS', 'TEST_SUITE',
                        'SPACE_TEST_SUITE', 'TEST_MODULES', 'SPACE_TEST_MODULES'):
                if os.environ.get(key):
                    raise ValueError(f'Conflicting inherited full-fast setting: {key}')
            for key in ('SPACE_MATRIX_TEST', 'SPACE_REALTIME_TEST'):
                if os.environ.get(key) == '1':
                    raise ValueError(f'Conflicting inherited full-fast setting: {key}')
        # One authorization, durably revoked BEFORE any application launch.
        state = session.state()
        state['authorized'] = False
        session.save(state)
        assets = str(OVERLAY / 'assets')
        fennel = f'{assets}/lua/?.fnl;{assets}/lua/?/init.fnl'
        env = {'WINEDLLOVERRIDES': 'space_record_publication=b;' + config['backend'], 'WINEDLLPATH': config['WINEDLLPATH'],
               'SPACE_BIN': str(OVERLAY / 'space-cli.exe'),
               'SPACE_ASSETS_PATH': assets, 'FENNEL_PATH': fennel, 'FENNEL_MACRO_PATH': fennel}
        args = ['--help']
        if mode == 'fast1800':
            args = ['-m', 'tests.fast:main']
            env.update(TEST_VERBOSE='1', SPACE_TEST_TIMINGS='1', SKIP_KEYRING_TESTS='1',
                       PWD=str(ROOT), SPACE_DISABLE_AUDIO='1')
            print('[LAUNCH] Wine full fast module=tests.fast:main deadline=1800s TEST_VERBOSE=1 SPACE_TEST_TIMINGS=1', flush=True)
        # A parent-only pipe, never application output or an inherited app FD.
        # Observe successful bounded-command creation, not caller entry/shutdown.
        observer = os.environ.pop(APPLICATION_OBSERVER_ENV, None) if mode == 'fast1800' else None
        fd = int(observer) if observer is not None else None
        if fd is not None:
            os.set_inheritable(fd, False)
        def observe(event, **fields):
            if fd is not None:
                data = (json.dumps(dict(event=event, **fields)) + '\n').encode('ascii')
                if os.write(fd, data) != len(data):
                    raise OSError('Incomplete private application observation')
        def launched(at):
            observe('launch', launched_monotonic=at,
                    hard_deadline_monotonic=at + prefix.BOUNDS[mode])
        try:
            code = session.launch([config['wine'], str(OVERLAY / 'space-cli.exe'), *args], mode, env,
                                  on_launch=launched if fd is not None else None)
            observe('result', command_returncode=code)
            return code
        finally:
            if fd is not None:
                os.close(fd)
    return owning_operation(session, execute)


def selected_session():
    # Establish immutable cleanup authority only. All remaining receipt/binding
    # checks belong inside the consumer's owning operation, even on failure.
    identifier = os.environ.get('SPACE_WINE_SESSION_ID')
    if identifier:
        return prefix.load_session(ROOT, identifier)
    # Without a private handoff, only a schema-3 receipt can identify a session.
    # Old receipts are evidence only. Never reinterpret their default prefix.
    safe_path(OVERLAY / 'admission.json')
    receipt = json.loads((OVERLAY / 'admission.json').read_text())
    if type(receipt.get('version')) is not int or receipt.get('version') != 3:
        raise ValueError('Unsupported Wine admission receipt (owned session schema 3 required)')
    return prefix.load_session(ROOT, receipt['ownedSession']['id'])


def main():
    action, *args = sys.argv[1:]
    if action == 'prepare' and not args:
        # Same repo-inode serialization as the reproducer. Child helpers may
        # acquire build/ themselves; no build lock/FD crosses that handoff.
        fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            with locked_build():
                session = (prefix.load_session(ROOT, os.environ['SPACE_WINE_SESSION_ID'])
                           if os.environ.get('SPACE_WINE_SESSION_ID') else prefix.create_session(ROOT))
            return prepare(session)
        finally:
            os.close(fd)
    with locked_build():
        if action == "package" and len(args) <= 1:
            package(Path(args[0]).absolute() if args else PACKAGE)
        elif action == 'prepare-bootstrap' and not args:
            identifier = os.environ.get('SPACE_WINE_SESSION_ID')
            if not identifier:
                raise ValueError('prepare-bootstrap requires owned parent Session handoff')
            return prepare_bootstrap(prefix.load_session(ROOT, identifier))
        elif action in ('smoke60', 'fast1800') and not args:
            return execute_admitted(selected_session(), action)
        elif action == 'terminal-stop' and not args:
            result = prefix.stop_session(selected_session(), end=True)
            print(cleanup_marker(result), flush=True)
            require_cleanup(result)
        elif action == "compat" and not args:
            verify(OVERLAY, "wine-overlay")
            if (OVERLAY / "admission.json").exists():
                raise ValueError("Cannot replace a helper in an admitted runtime; prepare a fresh overlay")
            with owned_file_write(OVERLAY, FORBIDDEN):
                build_compat(OVERLAY)
        else:
            raise ValueError("Invalid private artifact operation")


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise InterruptedError(f'Wine operation interrupted by signal {signum}')
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        code = main() or 0
        sys.exit(128 - code if code < 0 else code)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"Windows runtime: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
