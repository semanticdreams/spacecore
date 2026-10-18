"""Fixed identity-only Wine builtin pair builder. Never execute Wine or PE here."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
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
INPUTS = ('src/record_publication_wine_abi.h', 'scripts/wine/record_publication_bridge.c',
          'scripts/wine/record_publication_unix_entry.cpp', 'scripts/wine/build_publication.py')
DIRECTORIES = ('modules', 'modules/x86_64-windows', 'modules/x86_64-unix')
MAX_ARTIFACT = 64 * 1024 * 1024


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


def _inventory(path, relative, build_id):
    raw = _regular(path)
    if bytes.fromhex(build_id) not in raw:
        raise BuildError('Publication artifact is missing the embedded build ID')
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
            result = subprocess.run(args, cwd=stage, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=log, timeout=120)
        except (OSError, subprocess.SubprocessError) as error:
            raise BuildError(f'Publication build command failed: {Path(args[0]).name}: {error}') from error
        if result.returncode:
            log.seek(0)
            raw = log.read(4097)
            detail = raw[:4096].decode('utf-8', 'backslashreplace')
            if len(raw) > 4096:
                detail += ' [truncated]'
            raise BuildError(f'Publication compiler failed ({result.returncode}): {detail}')


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
                  '-I', str(repo / 'src'), definition, str(repo / INPUTS[2]), '-o', str(unix), '-ldl'], stage)
        _compile([tools['mingw_cc']['executable'], '-std=c11', '-O2', '-Wall', '-Werror', '-shared', '-static-libgcc',
                  '-I', str(windows_headers), '-I', str(wine_headers), '-I', str(repo / 'src'), definition,
                  str(repo / INPUTS[1]), '-o', str(pe)], stage)
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


def main():
    if len(sys.argv) != 1:
        raise BuildError('Fixed publication builder takes no arguments')
    identifier = os.environ.get('SPACE_WINE_SESSION_ID')
    if not identifier:
        raise BuildError('SPACE_WINE_SESSION_ID owned handoff is required')
    repo = Path(__file__).resolve().parents[2]
    session = prefix.load_session(repo, identifier)
    manifest = build_publication(repo, session)
    print(json.dumps(dict(version=1, abi=1, build_id=manifest['build_id'], files=list(PAIR)), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        message = str(error)
        print('Publication build refused: ' + message[:1024] + (' [truncated]' if len(message) > 1024 else ''),
              file=sys.stderr)
        sys.exit(2)
