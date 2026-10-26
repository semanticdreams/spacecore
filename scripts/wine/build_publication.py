"""Fixed operation/identity Wine builtin pair builder. Never execute Wine or PE here."""
from __future__ import annotations

import hashlib
from contextlib import ExitStack, contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import stat
import struct
import subprocess
import sys
import tempfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wine import prefix, publication_toolchain

PAIR = ('modules/x86_64-windows/space_record_publication.dll',
        'modules/x86_64-unix/space_record_publication.so')
ABI_HEADER = 'src/record_publication_wine_abi.h'
PE_SOURCE = 'scripts/wine/record_publication_bridge.c'
UNIX_SOURCE = 'scripts/wine/record_publication_unix_entry.cpp'
BUILDER_SOURCE = 'scripts/wine/build_publication.py'
AUTHORITY_HEADER = 'src/record_publication_wine_authority.h'
UNIX_HEADER = 'src/record_publication_unix.h'
UNIX_ADAPTER_SOURCE = 'src/record_publication_unix.cpp'
OPERATION_HEADER = 'src/record_publication_operation.h'
PUBLICATION_HEADER = 'src/record_publication.h'
PUBLICATION_SOURCE = 'src/record_publication.cpp'
INPUTS = (ABI_HEADER, AUTHORITY_HEADER, UNIX_HEADER, UNIX_ADAPTER_SOURCE, OPERATION_HEADER,
          PUBLICATION_HEADER, PUBLICATION_SOURCE, PE_SOURCE, UNIX_SOURCE, BUILDER_SOURCE)
DIRECTORIES = ('modules', 'modules/x86_64-windows', 'modules/x86_64-unix')
MAX_ARTIFACT = 64 * 1024 * 1024

# Dormant until the fixed publication stage opts in. Never added to INPUTS/PAIR:
# production-only runtime fixture checkouts must not need any test sources.
TEST_HEADER = 'tests/record_publication_wine_support.h'
TEST_PE_SOURCE = 'tests/record_publication_wine_support_pe.c'
TEST_UNIX_SOURCE = 'tests/record_publication_wine_support_unix.cpp'
TEST_INPUTS = (TEST_HEADER, TEST_PE_SOURCE, TEST_UNIX_SOURCE, BUILDER_SOURCE,
               'scripts/wine/publication_toolchain.py', 'scripts/wine/prefix.py',
               'src/record_publication_wine_binding.h', ABI_HEADER)
TEST_PAIR = ('modules/x86_64-windows/space_record_publication_tests.dll',
             'modules/x86_64-unix/space_record_publication_tests.so')
TEST_DISCOVERY = 'space_record_publication_tests.dll'
TEST_KIND = 'record-publication-test-support'
LAUNCH_HEADER = 'srpt_launch_config.h'
MAX_LAUNCH_PATH = 4095


class BuildError(ValueError):
    pass


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _regular(path, *, private=True):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
            or (private and stat.S_IMODE(info.st_mode) != 0o600)):
        raise BuildError(f'Unsafe publication file: {path.name}')
    if info.st_size > MAX_ARTIFACT:
        raise BuildError('Oversized publication input/artifact')
    return path.read_bytes()


def _span(raw, offset, size):
    if offset < 0 or size < 0 or offset + size > len(raw):
        raise BuildError('Truncated publication image')
    return raw[offset:offset + size]


def _unpack(fmt, raw, offset):
    return struct.unpack(fmt, _span(raw, offset, struct.calcsize(fmt)))


def _dependency(raw, offset):
    end = raw.find(b'\0', offset, offset + 256)
    if offset < 0 or end < offset:
        raise BuildError('Truncated/oversized dependency name')
    name = raw[offset:end].decode('ascii')
    if not re.fullmatch(r'[A-Za-z0-9_+.-]+', name) or name in ('.', '..'):
        raise BuildError('Unsupported dependency name')
    return name


def _elf_dependencies(raw):
    header = _unpack('<16sHHIQQQIHHHHHH', raw, 0)
    if header[0][:7] != b'\x7fELF\x02\x01\x01' or header[1:4] != (3, 62, 1):
        raise BuildError('Expected Linux x86_64 ELF shared library')
    offset, stride, count = header[6], header[11], header[12]
    if stride != 64 or not 0 < count <= 4096:
        raise BuildError('Unsupported ELF section table')
    sections = [_unpack('<IIQQQQIIQQ', raw, offset + index * stride) for index in range(count)]
    needed = []
    for section in sections:
        if section[1] != 6:  # SHT_DYNAMIC, linked to its own string table.
            continue
        if section[9] != 16 or section[5] % 16 or section[6] >= count:
            raise BuildError('Invalid ELF dynamic section')
        strings = sections[section[6]]
        names = _span(raw, strings[4], strings[5])
        for index in range(section[5] // 16):
            tag, value = _unpack('<QQ', raw, section[4] + index * 16)
            if tag == 0:
                break
            if tag == 1:  # DT_NEEDED
                needed.append(_dependency(names, value))
    return sorted(set(needed))


def _pe_dependencies(raw):
    if raw[:2] != b'MZ' or raw[64:80] != b'Wine builtin DLL':
        raise BuildError('Expected builtin-marked publication PE')
    pe, = _unpack('<I', raw, 60)
    if _span(raw, pe, 4) != b'PE\0\0':
        raise BuildError('Invalid PE signature')
    machine, count, _, _, _, size, _ = _unpack('<HHIIIHH', raw, pe + 4)
    optional = pe + 24
    if machine != 0x8664 or size < 240 or count > 96 or _unpack('<H', raw, optional)[0] != 0x20b:
        raise BuildError('Expected x86_64 PE32+ publication library')
    _span(raw, optional, size)
    sections = [_unpack('<8sIIIIIIHHI', raw, optional + size + index * 40) for index in range(count)]

    def rva_offset(rva, length):
        for section in sections:
            if section[2] <= rva and rva + length <= section[2] + section[3]:
                offset = section[4] + rva - section[2]
                _span(raw, offset, length)
                return offset
        raise BuildError('Unmapped/truncated PE import data')

    needed = []
    if _unpack('<I', raw, optional + 108)[0] <= 1:
        return needed
    rva, length = _unpack('<II', raw, optional + 120)
    if not rva and not length:
        return needed
    if not rva or length < 20 or length > MAX_ARTIFACT:
        raise BuildError('Invalid PE import directory')
    for index in range(length // 20):
        descriptor = _unpack('<IIIII', raw, rva_offset(rva + index * 20, 20))
        if not any(descriptor):
            return sorted(set(needed))
        needed.append(_dependency(raw, rva_offset(descriptor[3], 1)).lower())
    raise BuildError('Unterminated PE import directory')


def _inventory(path, relative, build_id, *, windows=None):
    raw = _regular(path)
    if bytes.fromhex(build_id) not in raw:
        raise BuildError('Publication artifact is missing the embedded build ID')
    if windows is None:
        windows = relative == PAIR[0]
    return dict(sha256=_sha(raw), size=len(raw), architecture='x86_64',
                format='pe32+' if windows else 'elf64',
                dependencies=_pe_dependencies(raw) if windows else _elf_dependencies(raw))


def _build_id(runtime, toolchain):
    value = dict(abi=1, runtime=runtime, toolchain=toolchain)
    return _sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def _recognized_output(output):
    if not output.exists() and not output.is_symlink():
        return None
    identity = prefix.real_directory(output, True)
    for directory in DIRECTORIES:
        prefix.real_directory(output / directory, True)
    if {str(path.relative_to(output)) for path in output.rglob('*')} != {*DIRECTORIES, *PAIR, 'build.json'}:
        raise BuildError('Extra/missing publication output entry')
    _regular(output / 'build.json')
    manifest = prefix.read_control(output / 'build.json')
    if (not isinstance(manifest, dict) or set(manifest) != {'version', 'abi', 'build_id', 'runtime', 'toolchain', 'files'}
            or type(manifest['version']) is not int or manifest['version'] != 1
            or type(manifest['abi']) is not int or manifest['abi'] != 1
            or not isinstance(manifest['build_id'], str) or not re.fullmatch('[0-9a-f]{64}', manifest['build_id'])
            or not isinstance(manifest['runtime'], dict) or not isinstance(manifest['toolchain'], dict)
            or not isinstance(manifest['files'], dict)
            or set(manifest['files']) != set(PAIR)
            or _build_id(manifest['runtime'], manifest['toolchain']) != manifest['build_id']):
        raise BuildError('Unrecognized publication build manifest')
    for relative in PAIR:
        if _inventory(output / relative, relative, manifest['build_id']) != manifest['files'][relative]:
            raise BuildError('Publication output inventory changed')
    return identity, manifest


def _sources(repo):
    return {relative: _sha(_regular(repo / relative, private=False)) for relative in INPUTS}


def _headers(identity):
    return publication_toolchain._public_sdk_roots(identity['headers']['files'])


def _compile(args, stage):
    # Fixed argv only. Do not inherit compiler search-path/loader injection knobs.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('LD_') and key not in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
                                                        'LIBRARY_PATH', 'COMPILER_PATH', 'GCC_EXEC_PREFIX')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C')
    with tempfile.TemporaryFile(dir=stage) as log:
        try:
            process = subprocess.Popen(args, cwd=stage, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, close_fds=True, start_new_session=True)
            try:
                code = process.wait(timeout=120)
            except BaseException:
                # Keep staging/log ownership until our entire POSIX group has
                # received bounded termination and the direct child is reaped.
                with prefix.cleanup_signals():
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    finally:
                        # The leader may exit before descendants. Always kill
                        # the remaining owned group, not just a live leader.
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=5)
                raise
        except (OSError, subprocess.SubprocessError) as error:
            raise BuildError(f'Publication build command failed: {Path(args[0]).name}: {error}') from error
        if code:
            log.seek(0)
            raw = log.read(4097)
            detail = raw[:4096].decode('utf-8', 'backslashreplace')
            if len(raw) > 4096:
                detail += ' [truncated]'
            raise BuildError(f'Publication compiler failed ({code}): {detail}')


@contextmanager
def _locked_build(build):
    """Same build-directory inode lock as admitted consumers; never compile here."""
    prefix.real_directory(build)
    fd = os.open(build, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _remove_recognized(output):
    _recognized_output(output)
    for relative in (*PAIR, 'build.json'):
        (output / relative).unlink()
    for directory in reversed(DIRECTORIES):
        (output / directory).rmdir()
    output.rmdir()


def build_publication(repo: Path, session: prefix.Session) -> dict:
    """Build only the fixed pair, using this Session's immutable runtime identity."""
    repo = Path(os.path.abspath(repo))
    if session.repo != repo:
        raise BuildError('Publication Session belongs to another repository')
    session.validate()
    build = repo / 'build'
    prefix.real_directory(build)
    output = build / 'wine-publication'
    previous = _recognized_output(output)  # Refuse foreign output before compilation.
    runtime = dict(session.owner['tools']['wine'])
    identity = publication_toolchain.resolve_toolchain(repo, runtime)
    publication_toolchain.verify_toolchain(identity)
    sources = _sources(repo)
    toolchain = dict(identity=identity, inputs=sources)
    build_id = _build_id(runtime, toolchain)
    definition = '-DSRP_BUILD_ID_BYTES={' + ','.join(hex(byte) for byte in bytes.fromhex(build_id)) + '}'
    windows_headers, wine_headers = _headers(identity)
    with tempfile.TemporaryDirectory(prefix='.wine-publication-', dir=build) as name:
        stage = Path(name)
        new = stage / 'new'
        new.mkdir(mode=0o700)
        for directory in DIRECTORIES:
            (new / directory).mkdir(mode=0o700)
        unix, pe = new / PAIR[1], new / PAIR[0]
        tools = identity['tools']
        _compile([tools['host_cxx']['executable'], '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                  '-fPIC', '-shared', '-fvisibility=hidden', '-static-libgcc', '-static-libstdc++',
                  '-I', str(repo / 'src'), definition, str(repo / UNIX_SOURCE),
                  str(repo / UNIX_ADAPTER_SOURCE), str(repo / PUBLICATION_SOURCE),
                  '-pthread', '-o', str(unix), '-ldl'], stage)
        _compile([tools['mingw_cc']['executable'], '-std=c11', '-O2', '-Wall', '-Werror', '-shared', '-static-libgcc',
                  '-I', str(windows_headers), '-I', str(wine_headers), '-I', str(repo / 'src'), definition,
                  str(repo / PE_SOURCE), '-o', str(pe), '-ladvapi32'], stage)
        _compile([tools['winebuild']['executable'], '--builtin', str(pe)], stage)
        for path in (unix, pe):
            _regular(path, private=False)
            path.chmod(0o600)
        manifest = dict(version=1, abi=1, build_id=build_id, runtime=runtime, toolchain=toolchain,
                        files={relative: _inventory(new / relative, relative, build_id) for relative in PAIR})
        prefix.write_control(new / 'build.json', manifest, exclusive=True)
        _recognized_output(new)
        session.validate()
        publication_toolchain.verify_toolchain(identity)
        if _sources(repo) != sources:
            raise BuildError('Publication source inputs changed during build')
        with _locked_build(build):
            if _recognized_output(output) != previous:
                raise BuildError('Publication output changed during build')
            backup = stage / 'old'
            if previous is not None:
                output.rename(backup)
            try:
                new.rename(output)
            except OSError:
                if previous is not None:
                    backup.rename(output)
                raise
            if previous is not None:
                _remove_recognized(backup)
    return manifest


def _test_build_id(runtime, toolchain):
    value = dict(kind=TEST_KIND, abi=2, runtime=runtime, toolchain=toolchain)
    return _sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def _launch_path(path):
    raw = os.fsencode(path)
    if (not raw.startswith(b'/') or len(raw) > MAX_LAUNCH_PATH or b'\0' in raw
            or (raw != b'/' and any(part in (b'', b'.', b'..') for part in raw[1:].split(b'/')))):
        raise BuildError('Unsafe/oversized absolute launch path')
    return raw


def _launch_snapshot(info):
    return dict(device=info.st_dev, inode=info.st_ino, size=info.st_size,
                uid=info.st_uid, mode=info.st_mode, mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns)


def _launch_ancestor_snapshot(info):
    # Ancestors pin directory identity and trust, not directory contents. Sibling
    # activity may change size/timestamps without changing this declared tuple.
    return dict(device=info.st_dev, inode=info.st_ino, uid=info.st_uid, mode=info.st_mode)


def _launch_trusted(info, *, directory=False):
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (not kind or info.st_uid != 0 or info.st_mode & 0o022
            or (not directory and (info.st_mode & 0o6000 or not info.st_mode & 0o111))):
        raise BuildError('Unsafe launch runtime ownership/type/mode')


def _capture_runtime_pin(expected, *, implementation):
    """Hash only nofollow-acquired trusted installed files, retaining the full walk."""
    raw = _launch_path(expected['executable'])
    digest = expected['sha256']
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or raw == b'/':
        raise BuildError('Invalid launch runtime pin')
    with ExitStack() as stack:
        def acquire(name, flags, parent=None):
            fd = os.open(name, flags | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            stack.callback(os.close, fd)
            return fd

        flags = os.O_RDONLY | os.O_DIRECTORY
        root = acquire(b'/', flags)
        # Keep both descriptor and parent/name witnesses. Retained descriptors alone
        # would not notice replacement of an ancestor's directory entry during hashing.
        walk = [(root, None, b'/', os.fstat(root), b'/')]
        parent = root
        current = b''
        for component in raw[1:].split(b'/')[:-1]:
            current += b'/' + component
            fd = acquire(component, flags, parent)
            walk.append((fd, parent, component, os.fstat(fd), current))
            parent = fd
        ancestors = []
        for _, _, _, info, path in walk:
            _launch_trusted(info, directory=True)
            ancestors.append(dict(path_hex=path.hex(), **_launch_ancestor_snapshot(info)))
        leaf = raw.rsplit(b'/', 1)[1]
        fd = acquire(leaf, os.O_RDONLY | os.O_NONBLOCK, parent)
        before = os.fstat(fd)
        _launch_trusted(before)
        if before.st_size > MAX_ARTIFACT:
            raise BuildError('Oversized launch runtime')
        if not os.access(leaf, os.X_OK, dir_fd=parent, effective_ids=True, follow_symlinks=False):
            raise BuildError('Launch runtime is not executable')
        hasher = hashlib.sha256()
        size = 0
        header = bytearray()
        while size < MAX_ARTIFACT:
            chunk = os.read(fd, min(1024 * 1024, MAX_ARTIFACT - size))
            if not chunk:
                break
            header.extend(chunk[:max(0, 64 - len(header))])
            hasher.update(chunk)
            size += len(chunk)
        if (size != before.st_size or hasher.hexdigest() != digest
                or _launch_snapshot(os.fstat(fd)) != _launch_snapshot(before)
                or _launch_snapshot(os.stat(leaf, dir_fd=parent, follow_symlinks=False)) != _launch_snapshot(before)):
            raise BuildError('Launch runtime hash/identity changed')
        if implementation:
            elf = _unpack('<16sHHIQQQIHHHHHH', header, 0)
            if (elf[0][:7] != b'\x7fELF\x02\x01\x01' or elf[0][7] not in (0, 3)
                    or elf[1] not in (2, 3) or elf[2:4] != (62, 1) or elf[8] != 64):
                raise BuildError('Launch runtime must be Linux x86_64 executable ELF')
        for descriptor, ancestor_parent, name, info, _ in walk:
            if (_launch_ancestor_snapshot(os.fstat(descriptor)) != _launch_ancestor_snapshot(info)
                    or _launch_ancestor_snapshot(os.stat(name, dir_fd=ancestor_parent, follow_symlinks=False))
                    != _launch_ancestor_snapshot(info)):
                raise BuildError('Launch runtime ancestor changed')
        return dict(path_hex=raw.hex(), sha256=digest, **_launch_snapshot(before), ancestors=ancestors)


def _capture_launch_metadata(repo: Path, session: prefix.Session, identity: dict) -> dict:
    # The logical Session Wine may be a distro script. Only the independently
    # verified installation implementation is suitable for direct native spawn.
    # The immutable Session server may itself be a trusted distro wrapper. Keep
    # all acquisition/hash/identity checks, but require ELF only for native spawn.
    # Never expose path-bearing OS exceptions through the builder's diagnostics.
    try:
        implementation = _capture_runtime_pin(identity['installation']['implementation']['file'], implementation=True)
    except (BuildError, OSError):
        raise BuildError('Unsafe launch implementation runtime pin') from None
    try:
        server = _capture_runtime_pin(session.owner['tools']['server'], implementation=False)
    except (BuildError, OSError):
        raise BuildError('Unsafe launch server runtime pin') from None
    return dict(schema=1, checkout_path_hex=_launch_path(repo).hex(),
                implementation=implementation, server=server)


def _render_launch_header(metadata: dict) -> bytes:
    """Private, deterministic C/C++ metadata; never interpolate pathname literals."""
    lines = ['/* Generated private launch pins. Not a public ABI. */',
             '#ifndef SRPT_LAUNCH_CONFIG_H', '#define SRPT_LAUNCH_CONFIG_H',
             '#include <stdint.h>', '#include <stddef.h>',
             'typedef struct { const unsigned char *path; uint64_t device, inode; uint32_t uid, mode; } SrptLaunchAncestor;',
             'typedef struct { const unsigned char *path, *sha256; uint64_t device, inode, size;',
             '    uint32_t uid, mode; int64_t mtime_ns, ctime_ns;',
             '    const SrptLaunchAncestor *ancestors; size_t ancestor_count; } SrptLaunchRuntimePin;']

    def array(name, raw):
        lines.append('static const unsigned char ' + name + '[] = {' + ','.join(str(byte) for byte in raw) + '};')

    def number(value, bits=64, signed=False):
        if type(value) is not int or not (-(1 << (bits - 1)) if signed else 0) <= value < (1 << (bits - int(signed))):
            raise BuildError('Launch pin integer is out of range')
        macro = 'INT' if signed else 'UINT'
        return ('-' if value < 0 else '') + f'{macro}{bits}_C({abs(value)})'

    if metadata['schema'] != 1:
        raise BuildError('Unknown launch metadata schema')
    lines.append('static const uint32_t srpt_launch_schema = UINT32_C(1);')
    array('srpt_launch_checkout', bytes.fromhex(metadata['checkout_path_hex']) + b'\0')
    for key in ('implementation', 'server'):
        pin = metadata[key]
        name = 'srpt_launch_' + key
        array(name + '_path', bytes.fromhex(pin['path_hex']) + b'\0')
        array(name + '_sha256', bytes.fromhex(pin['sha256']))
        for index, row in enumerate(pin['ancestors']):
            array(f'{name}_ancestor_{index}', bytes.fromhex(row['path_hex']) + b'\0')
        lines.append(f'static const SrptLaunchAncestor {name}_ancestors[] = {{')
        for index, row in enumerate(pin['ancestors']):
            values = [number(row[field], 32 if field in ('uid', 'mode') else 64)
                      for field in ('device', 'inode', 'uid', 'mode')]
            lines.append('    {' + f'{name}_ancestor_{index}, ' + ', '.join(values) + '},')
        lines.append('};')
        values = [number(pin[field], 32 if field in ('uid', 'mode') else 64,
                         signed=field in ('mtime_ns', 'ctime_ns'))
                  for field in ('device', 'inode', 'size', 'uid', 'mode', 'mtime_ns', 'ctime_ns')]
        lines.append(f'static const SrptLaunchRuntimePin {name} = {{' +
                     f'{name}_path, {name}_sha256, ' + ', '.join(values) +
                     f', {name}_ancestors, sizeof({name}_ancestors)/sizeof({name}_ancestors[0])' + '};')
    return ('\n'.join([*lines, '#endif', ''])).encode('ascii')


def _test_sources(repo):
    return {relative: _sha(_regular(repo / relative, private=False)) for relative in TEST_INPUTS}


def _test_inventory(output, build_id):
    files = {relative: _inventory(output / relative, relative, build_id,
                                 windows=relative != TEST_PAIR[1])
             for relative in (*TEST_PAIR, TEST_DISCOVERY)}
    if files[TEST_DISCOVERY] != files[TEST_PAIR[0]]:
        raise BuildError('Test support discovery copy differs from paired PE')
    return files


def _recognized_test_output(output: Path, *, for_replacement: bool = False) -> tuple | None:
    if not output.exists() and not output.is_symlink():
        return None
    identity = prefix.real_directory(output, True)
    for directory in DIRECTORIES:
        prefix.real_directory(output / directory, True)
    expected = {*DIRECTORIES, *TEST_PAIR, TEST_DISCOVERY, 'build.json'}
    if {str(path.relative_to(output)) for path in output.rglob('*')} != expected:
        raise BuildError('Extra/missing test support output entry')
    _regular(output / 'build.json')
    manifest = prefix.read_control(output / 'build.json')
    if (not isinstance(manifest, dict)
            or set(manifest) != {'version', 'abi', 'kind', 'build_id', 'runtime', 'toolchain', 'files'}
            or type(manifest['version']) is not int or manifest['version'] != 1
            or type(manifest['abi']) is not int or manifest['abi'] not in ((1, 2) if for_replacement else (2,))
            or manifest['kind'] != TEST_KIND
            or not isinstance(manifest['runtime'], dict) or not isinstance(manifest['toolchain'], dict)
            or not isinstance(manifest['build_id'], str) or not re.fullmatch('[0-9a-f]{64}', manifest['build_id'])
            or not isinstance(manifest['files'], dict)
            or set(manifest['files']) != {*TEST_PAIR, TEST_DISCOVERY}):
        raise BuildError('Unrecognized test support manifest')
    if manifest['abi'] == 2:
        expected_id = _test_build_id(manifest['runtime'], manifest['toolchain'])
    else:
        # Historical ABI1 calculation, only reachable for builder replacement or
        # cleanup. Never reinterpret its ID as ABI2 or admit it for execution.
        value = dict(kind=TEST_KIND, abi=1, runtime=manifest['runtime'], toolchain=manifest['toolchain'])
        expected_id = _sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())
    if expected_id != manifest['build_id']:
        raise BuildError('Unrecognized test support manifest')
    if _test_inventory(output, manifest['build_id']) != manifest['files']:
        raise BuildError('Test support output inventory changed')
    return identity, manifest


def build_test_support(repo: Path, session: prefix.Session) -> dict:
    """Build the separate fixed test-only pair/copy; no CLI or admission activation."""
    repo = Path(os.path.abspath(repo))
    if session.repo != repo:
        raise BuildError('Test support Session belongs to another repository')
    session.validate()
    build = repo / 'build'
    prefix.real_directory(build)
    output = build / 'wine-publication-tests'
    previous = _recognized_test_output(output, for_replacement=True)
    runtime = dict(session.owner['tools']['wine'])
    identity = publication_toolchain.resolve_toolchain(repo, runtime)
    publication_toolchain.verify_toolchain(identity)
    sources = _test_sources(repo)
    launch = _capture_launch_metadata(repo, session, identity)
    launch_header = _render_launch_header(launch)
    toolchain = dict(identity=identity, inputs=sources, launch=launch, launch_header_sha256=_sha(launch_header))
    build_id = _test_build_id(runtime, toolchain)
    definition = '-DSRPT_BUILD_ID_BYTES={' + ','.join(hex(byte) for byte in bytes.fromhex(build_id)) + '}'
    windows_headers, wine_headers = _headers(identity)
    with tempfile.TemporaryDirectory(prefix='.wine-publication-tests-', dir=build) as name:
        stage = Path(name)
        header = stage / LAUNCH_HEADER
        fd = os.open(header, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(launch_header)
        new = stage / 'new'
        new.mkdir(mode=0o700)
        for directory in DIRECTORIES:
            (new / directory).mkdir(mode=0o700)
        unix, pe = new / TEST_PAIR[1], new / TEST_PAIR[0]
        tools = identity['tools']
        _compile([tools['host_cxx']['executable'], '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                  '-fPIC', '-shared', '-fvisibility=hidden', '-static-libgcc', '-static-libstdc++',
                  '-I', str(stage), '-I', str(repo / 'tests'), '-I', str(repo / 'src'), definition, str(repo / TEST_UNIX_SOURCE),
                  '-pthread', '-o', str(unix), '-ldl'], stage)
        _compile([tools['mingw_cc']['executable'], '-std=c11', '-O2', '-Wall', '-Werror', '-shared', '-static-libgcc',
                  '-I', str(stage), '-I', str(windows_headers), '-I', str(wine_headers), '-I', str(repo / 'tests'), definition,
                  str(repo / TEST_PE_SOURCE), '-o', str(pe)], stage)
        _compile([tools['winebuild']['executable'], '--builtin', str(pe)], stage)
        for path in (unix, pe):
            _regular(path, private=False)
            path.chmod(0o600)
        # Exclusive byte-identical Windows-side basename discovery, Wine overlay only.
        copy = new / TEST_DISCOVERY
        fd = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(_regular(pe))
        manifest = dict(version=1, abi=2, kind=TEST_KIND, build_id=build_id, runtime=runtime,
                        toolchain=toolchain, files=_test_inventory(new, build_id))
        prefix.write_control(new / 'build.json', manifest, exclusive=True)
        _recognized_test_output(new)
        session.validate()
        publication_toolchain.verify_toolchain(identity)
        if _test_sources(repo) != sources:
            raise BuildError('Test support source inputs changed during build')
        if _capture_launch_metadata(repo, session, identity) != launch or _regular(header) != launch_header:
            raise BuildError('Test support launch pins/header changed during build')
        with _locked_build(build):
            if _recognized_test_output(output, for_replacement=True) != previous:
                raise BuildError('Test support output changed during build')
            backup = stage / 'old'
            if previous is not None:
                output.rename(backup)
            try:
                new.rename(output)
            except OSError:
                if previous is not None:
                    backup.rename(output)
                raise
            if previous is not None:
                _recognized_test_output(backup, for_replacement=True)
                for relative in (*TEST_PAIR, TEST_DISCOVERY, 'build.json'):
                    (backup / relative).unlink()
                for directory in reversed(DIRECTORIES):
                    (backup / directory).rmdir()
                backup.rmdir()
    return manifest


def main():
    if len(sys.argv) != 1:
        raise BuildError('Fixed publication builder takes no arguments')
    identifier = os.environ.get('SPACE_WINE_SESSION_ID')
    if not identifier:
        raise BuildError('SPACE_WINE_SESSION_ID owned handoff is required')
    repo = Path(__file__).resolve().parents[2]
    session = prefix.load_session(repo, identifier)
    manifest = build_publication(repo, session)
    build_test_support(repo, session)
    print(json.dumps(dict(version=1, abi=1, build_id=manifest['build_id'], files=list(PAIR)), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        message = str(error)
        print('Publication build refused: ' + message[:1024] + (' [truncated]' if len(message) > 1024 else ''),
              file=sys.stderr)
        sys.exit(2)
