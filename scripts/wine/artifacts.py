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

import prefix

ROOT = Path(__file__).absolute().parents[2]
BUILD = ROOT / "build"
PACKAGE = BUILD / "dist/windows"
OVERLAY = BUILD / "wine/windows"
MARKER = ".space-windows-artifact-v1.json"
FORBIDDEN = "bcryptprimitives.dll"
BUILTIN = "bcryptprimitives=b;advapi32,cryptbase=b"
COMPAT = "bcryptprimitives=n;advapi32,cryptbase=b"
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
    if any(Path(name).name.casefold() == FORBIDDEN for name in entries):
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
            if dll.suffix.casefold() == ".dll" and dll.name.casefold() != FORBIDDEN:
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


def session_binding(session):
    return {"id": session.id, "nonce": session.nonce, "prefix": str(session.prefix),
            "identity": session.owner["roots"]["prefix"], "arch": "win64"}


def probe(session, backend):
    before = verify(OVERLAY, "wine-overlay")
    print(f"Wine admission: probe backend={backend} deadline=60s kill-after=5s", flush=True)
    code = session.launch([session.owner['tools']['wine']['executable'],
                           str(OVERLAY / "process-prng-probe.exe")], 'probe', {"WINEDLLOVERRIDES": backend})
    detail = (" (admission timeout, not crypto absence)" if code == 124 else
              " (SIGKILL/forced admission timeout, not crypto absence)" if code in (137, -9) else "")
    print(f"Wine admission: probe exit={code}" +
          detail, flush=True)
    if inventory(OVERLAY) != before:
        raise ValueError("Probe modified the overlay; refusing to claim unknown output")
    return code


def _prepare_payload(session):
    package_before = clean_native(PACKAGE)
    check_replace(OVERLAY, "wine-overlay")
    conditions = launch_conditions()
    code = prefix.initialize(session)
    if code:
        raise ValueError(f"Wine initialization failed: exit={code}")
    with private_stage(OVERLAY.parent) as stage:
        # Copy only the immutable, verified native package, never build leftovers.
        for item in PACKAGE.iterdir():
            if item.name == MARKER:
                continue
            copy_tree(item, stage / item.name) if item.is_dir() else shutil.copy2(item, stage / item.name)
        compiler("probe.c", stage / "process-prng-probe.exe")
        seal(stage, "wine-overlay")
        install(stage, OVERLAY, "wine-overlay")
    backend = BUILTIN
    code = probe(session, backend)
    if code == 10:
        print("Wine admission: confirmed absence; building Wine-only bridge", flush=True)
        with owned_file_write(OVERLAY, FORBIDDEN):
            build_compat(OVERLAY)
        backend = COMPAT
        code = probe(session, backend)
    if code != 0:
        raise ValueError(f"Wine API admission failed: probe exit={code}; no fallback/retry authorized")
    if clean_native(PACKAGE) != package_before:
        raise ValueError("Native package changed during Wine admission")
    cleanup = prefix.stop_session(session, end=False)
    require_cleanup(cleanup)
    receipt = {"version": 2, "ownedSession": session_binding(session),
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
    if (receipt.get("version") != 2 or backend not in (BUILTIN, COMPAT)
            or receipt.get("ownedSession") != session_binding(session)
            or receipt.get("tools") != session.owner['tools']
            or receipt.get("payload") != payload or receipt.get("package") != native
            or receipt.get("conditions") != launch_conditions()):
        raise ValueError("Wine admission receipt does not match payload/package/launch conditions")
    identity = session.owner['tools']['wine']
    if os.environ.get("WINE_CMD") and str(prefix.resolve_wine()) != identity["executable"]:
        raise ValueError("WINE_CMD differs from admitted Wine")
    if (backend == COMPAT) != (FORBIDDEN in payload):
        raise ValueError("Backend does not match overlay helper inventory")
    return {'wine': identity['executable'], 'backend': backend}


def require_cleanup(result):
    if not result.ok:
        raise ValueError('Owned Wine cleanup failed: ' + '; '.join(result.errors))


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
        env = {'WINEDLLOVERRIDES': config['backend'], 'SPACE_BIN': str(OVERLAY / 'space-cli.exe'),
               'SPACE_ASSETS_PATH': assets, 'FENNEL_PATH': fennel, 'FENNEL_MACRO_PATH': fennel}
        args = ['--help']
        if mode == 'fast1800':
            args = ['-m', 'tests.fast:main']
            env.update(TEST_VERBOSE='1', SPACE_TEST_TIMINGS='1', SKIP_KEYRING_TESTS='1',
                       XDG_DATA_HOME='/tmp/space/tests/xdg-data', PWD=str(ROOT), SPACE_DISABLE_AUDIO='1')
            print('[LAUNCH] Wine full fast module=tests.fast:main deadline=1800s TEST_VERBOSE=1 SPACE_TEST_TIMINGS=1', flush=True)
        return session.launch([config['wine'], str(OVERLAY / 'space-cli.exe'), *args], mode, env)
    return owning_operation(session, execute)


def selected_session():
    # Establish immutable cleanup authority only. All remaining receipt/binding
    # checks belong inside the consumer's owning operation, even on failure.
    identifier = os.environ.get('SPACE_WINE_SESSION_ID')
    if identifier:
        return prefix.load_session(ROOT, identifier)
    # Without a private handoff, only a schema-2 receipt can identify a session.
    # Old receipts are evidence only. Never reinterpret their default prefix.
    safe_path(OVERLAY / 'admission.json')
    receipt = json.loads((OVERLAY / 'admission.json').read_text())
    if receipt.get('version') != 2:
        raise ValueError('Unsupported Wine admission receipt (owned session schema 2 required)')
    return prefix.load_session(ROOT, receipt['ownedSession']['id'])


def main():
    action, *args = sys.argv[1:]
    with locked_build():
        if action == "package" and len(args) <= 1:
            package(Path(args[0]).absolute() if args else PACKAGE)
        elif action == "prepare" and not args:
            session = (prefix.load_session(ROOT, os.environ['SPACE_WINE_SESSION_ID'])
                       if os.environ.get('SPACE_WINE_SESSION_ID') else prefix.create_session(ROOT))
            return prepare(session)
        elif action in ('smoke60', 'fast1800') and not args:
            return execute_admitted(selected_session(), action)
        elif action == 'terminal-stop' and not args:
            require_cleanup(prefix.stop_session(selected_session(), end=True))
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
