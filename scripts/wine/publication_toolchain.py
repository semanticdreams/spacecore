"""Fixed host-only Wine9 publication toolchain and provisioning admission.

Never run Wine here. Package metadata describes a build installation, not runtime
release/ABI proof. Runtime identities, when supplied, were observed by Session.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

SETUP_PACKAGES = (
    'mingw-w64', 'gcc-mingw-w64-x86-64-posix', 'g++-mingw-w64-x86-64-posix',
    'binutils-mingw-w64-x86-64', 'winbind', 'g++', 'cmake', 'ninja-build', 'ccache',
    'git', 'pkg-config', 'nasm', 'llvm-14', 'curl', 'autoconf', 'automake', 'libtool',
    'python3', 'python3-pil', 'ripgrep', 'zip')
_DEV = ('wine64-tools:amd64', 'libwine-dev:amd64')
_APT_QUERY = '''
import apt, json, sys
cache = apt.Cache()
result = {}
requested = set(json.loads(sys.argv[1]))
def entry(v):
 return dict(version=v.version, source=v.source_name, source_version=v.source_version,
             architecture=v.architecture,
             origins=[dict(origin=o.origin, trusted=o.trusted, archive=o.archive, site=o.site) for o in v.origins])
def slot(name, architecture):
 return result.setdefault(name + ':' + architecture, dict(installed=None, versions=[]))
for p in cache:
 name = p.name.split(':')[0]
 versions = list(p.versions)
 observed = versions + ([p.installed] if p.installed else [])
 if name not in requested and name not in ('wine', 'wine64', 'libwine', 'wine64-tools', 'libwine-dev') and not any(v.source_name == 'wine' or v.source_name.startswith('wine-') for v in observed):
  continue
 for v in versions:
  value = entry(v)
  rows = slot(name, v.architecture)['versions']
  if value not in rows: rows.append(value)
 if p.installed:
  v = p.installed
  value = dict(version=v.version, source=v.source_name, source_version=v.source_version, architecture=v.architecture)
  row = slot(name, v.architecture)
  if row['installed'] is not None and row['installed'] != value:
   raise ValueError('Conflicting installed architecture identity')
  row['installed'] = value
print(json.dumps(result, sort_keys=True))
'''


class ToolchainError(ValueError):
    def __init__(self, message, missing=()):
        super().__init__(message)
        self.missing = list(missing)


def _run(repo, args):
    try:
        result = subprocess.run(args, cwd=repo, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=30, env=dict(os.environ, LC_ALL='C'))
    except (OSError, subprocess.SubprocessError) as error:
        raise ToolchainError(f'Host tool unavailable: {args[0]}: {error}') from error
    if result.returncode:
        raise ToolchainError(f'Host tool failed: {args[0]}: {result.stderr[:500]}')
    return result.stdout


def _catalog(repo, requested=()):
    # Use the distro interpreter, which owns python3-apt, not a virtualenv's apt.
    try:
        return json.loads(_run(repo, ['/usr/bin/python3', '-c', _APT_QUERY, json.dumps(sorted(requested))]))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise ToolchainError(f'Ubuntu package metadata unavailable: {error}', ['python3-apt']) from error


def _file(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ToolchainError(f'Not a regular toolchain file: {path}')
    return {'executable': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def _package(repo, path):
    owner = _run(repo, ['dpkg-query', '-S', str(path)]).strip().splitlines()
    if len(owner) != 1 or ': ' not in owner[0]:
        raise ToolchainError(f'Ambiguous package owner: {path}')
    name, owned = owner[0].rsplit(': ', 1)
    if owned != str(path) or not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?', name):
        raise ToolchainError(f'Invalid package owner: {path}')
    return _installed(repo, name)


def _installed(repo, name):
    try:
        fields = _run(repo, ['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\t${Architecture}\n', name]).strip().split('\t')
    except ToolchainError as error:
        raise ToolchainError(f'Missing installed package: {name}', [name]) from error
    if len(fields) != 5:
        raise ToolchainError(f'Invalid installed package metadata: {name}')
    binary, version, source, source_version, architecture = fields
    return dict(name=binary.split(':')[0] + ':' + architecture, version=version, source=source or binary.split(':')[0],
                source_version=source_version or version, architecture=architecture)


def _ubuntu(version):
    origins = [origin for origin in version['origins'] if origin['origin'] or origin['site']]
    return bool(origins) and all(origin['origin'] == 'Ubuntu' and origin['trusted'] is True for origin in origins)


def _version(catalog, name, *, binary=None, source_version=None):
    if ':' not in name:
        raise ToolchainError(f'Architecture-qualified package identity required: {name}')
    for version in catalog.get(name, {}).get('versions', []):
        if version['architecture'] != name.split(':')[1]:
            continue
        if binary is not None and version['version'] != binary:
            continue
        if source_version is not None and version['source_version'] != source_version:
            continue
        if version['source'] == 'wine' and re.match(r'(?:\d+:)?9\.', version['source_version']) and _ubuntu(version):
            return dict(version, name=name)
    raise ToolchainError(f'No exact matching trusted Ubuntu Wine9 package: {name}', [name])


def _diagnostic_tail(value, limit):
    # Keep complete JSON escape units, including Unicode surrogate pairs.
    # A bounded suffix retains useful layout without dumping private ancestors.
    # This helper only renders already-observed strings; it never inspects paths.
    parts, size = [], 0
    for char in reversed(value):
        escaped = json.dumps(char, ensure_ascii=True)[1:-1]
        if size + len(escaped) > limit - 3:
            return '...' + ''.join(reversed(parts)), True
        parts.append(escaped)
        size += len(escaped)
    return ''.join(reversed(parts)), False


def _native_inventory_diagnostic(package, listed, regular, unique, observations):
    package, truncated = _diagnostic_tail(package, 32)
    rendered = []
    for path, is_file in observations:
        path, clipped = _diagnostic_tail(path, 40)
        truncated = truncated or clipped
        rendered.append(f'"{path}" is-file={str(is_file).lower()}')
    while True:
        message = (f'Missing or conflicting native Wine64 role: package={package} '
                   f'listed={listed} regular={regular} unique-resolved={unique} '
                   f'observations-truncated={str(listed > len(rendered)).lower()} '
                   f'message-truncated={str(truncated).lower()} observations=[' + '; '.join(rendered) + ']')
        if len(message) <= 480:
            return message
        # Counts originate from this process's finite package list, so the
        # count/flag prefix fits by itself. Drop whole observations, not escapes.
        rendered.pop()
        truncated = True


def _selection(repo, catalog, runtime=None, *, provisioning=False):
    lookup = os.environ.get('WINE_CMD') or shutil.which('wine64') or shutil.which('wine')
    logical = shutil.which(lookup) if lookup else None
    if logical is None:
        if not provisioning or lookup:
            raise ToolchainError('Selected Wine installation missing', ['wine'])
        version = _version(catalog, 'wine64:amd64')
        return dict(logical=None, file=None, package=version, implementation=dict(file=None, package=version))
    logical = Path(logical).absolute()
    file = _file(logical)
    package = _package(repo, file['executable'])
    if package['architecture'] not in ('amd64', 'all'):
        raise ToolchainError('Unsupported selected Wine package architecture')
    if package['source'] != 'wine' or not re.match(r'(?:\d+:)?9\.', package['source_version']):
        raise ToolchainError('Selected installation is not supported distro Wine9')
    _version(catalog, package['name'], binary=package['version'], source_version=package['source_version'])
    native = _matched_package(repo, catalog, 'wine64:amd64', package['source_version'])
    if native['name'] != 'wine64:amd64' or native['architecture'] != 'amd64':
        raise ToolchainError('Unsupported native Wine64 package architecture/identity')
    selected = Path(file['executable'])
    if package['name'] == 'wine64:amd64':
        if selected.parts[-3:] != ('lib', 'wine', 'wine64'):
            raise ToolchainError('Unsupported Wine9 native-loader layout')
        installation = selected.parents[2]
    elif package['name'] == 'wine:all':
        if selected.parts[-2:] != ('bin', 'wine-stable'):
            raise ToolchainError('Unsupported Wine9 launcher layout')
        installation = selected.parent.parent
    else:
        raise ToolchainError('Unsupported distro Wine launcher package')
    # This distro profile has one native role, not every regular basename in
    # the package (which also owns a regular lintian override named wine64).
    role = installation / 'lib/wine/wine64'
    paths = _run(repo, ['dpkg-query', '-L', native['name']]).splitlines()
    candidates, observations = set(), []
    listed, regular = 0, 0
    role_listed = False
    for path in paths:
        candidate = Path(path)
        if candidate.parts[-3:] != ('lib', 'wine', 'wine64'):
            continue
        role_listed = role_listed or candidate == role
        listed += 1
        is_file = candidate.is_file()
        if is_file:
            regular += 1
            candidates.add(str(candidate.resolve()))
        if len(observations) < 4:
            observations.append((path, is_file))
    if not role_listed or regular != listed or candidates != {str(role)}:
        raise ToolchainError(_native_inventory_diagnostic(native['name'], listed, regular,
                                                          len(candidates), observations))
    if not os.access(role, os.X_OK):
        raise ToolchainError('Native Wine64 role is not executable')
    implementation = _file(role)
    if package['name'] == 'wine64:amd64' and file != implementation:
        raise ToolchainError('Selected native Wine64 role identity changed')
    if _package(repo, implementation['executable']) != native:
        raise ToolchainError('Wine64 implementation does not match native package')
    if runtime is not None:
        if (set(runtime) != {'executable', 'sha256', 'version'}
                or file != {key: runtime[key] for key in ('executable', 'sha256')}
                or not re.fullmatch(r'(?:wine-|Wine )9\.[^\x00-\x1f]*', runtime['version'])):
            raise ToolchainError('Pinned Session Wine identity changed or unsupported')
    return dict(logical=str(logical), file=file, package=package,
                implementation=dict(file=implementation, package=native))


def _matched_package(repo, catalog, name, source_version):
    package = _installed(repo, name)
    if package['source'] != 'wine' or package['source_version'] != source_version:
        raise ToolchainError(f'Mismatched development package: {name}')
    _version(catalog, name, binary=package['version'], source_version=source_version)
    return package


def _wine_tool_diagnostic(name, reason, selection, role, canonical, candidates):
    fields, truncated = [], len(candidates) > 2
    for label, value in [('wine-logical', selection['logical']),
                         ('wine-canonical', selection['file']['executable']),
                         ('tool-role', str(role)), ('tool-canonical', canonical or 'unavailable')]:
        value, clipped = _diagnostic_tail(value, 40)
        truncated = truncated or clipped
        fields.append(f'{label}="{value}"')
    entries = []
    for candidate in sorted(candidates)[:2]:
        value, clipped = _diagnostic_tail(str(candidate), 40)
        truncated = truncated or clipped
        entries.append(f'"{value}"')
    # Two fixed tool names/reasons, four bounded fields and at most two profile
    # candidates fit below480 ASCII bytes, including their truncation flag.
    return (f'Wine tool membership refused: name={name} reason={reason} pkg-roles={len(candidates)} '
            f'context-truncated={str(truncated).lower()} ' + ' '.join(fields)
            + ' candidates=[' + ','.join(entries) + ']')


def _wine_tool(repo, name, selection, package):
    if name not in ('winegcc', 'winebuild'):
        raise ToolchainError('Unsupported required Wine tool role')
    if package['name'] != 'wine64-tools:amd64' or package['architecture'] != 'amd64':
        raise ToolchainError('Unsupported Wine tools package architecture/identity')
    selected = Path(selection['file']['executable'])
    if selected.parts[-2:] == ('bin', 'wine-stable'):
        role = selected.with_name(name + '-stable')
        providers = {role, selected.parent.parent / 'lib/wine' / name}
    elif selected.parts[-3:] == ('lib', 'wine', 'wine64'):
        role = selected.with_name(name)
        providers = {role}
    else:
        raise ToolchainError('Unsupported canonical Wine installation for tool roles')
    files = {Path(path) for path in _run(repo, ['dpkg-query', '-L', package['name']]).splitlines()}
    candidates = files & providers
    if role not in files:
        raise ToolchainError(_wine_tool_diagnostic(name, 'unlisted-role', selection, role, None, candidates))
    if not role.is_file() or not os.access(role, os.X_OK):
        raise ToolchainError(f'Missing/non-executable {name} role', [name])
    canonical = str(role.resolve(strict=True))
    if Path(canonical) not in candidates:
        raise ToolchainError(_wine_tool_diagnostic(name, 'provider-not-in-role', selection, role, canonical, candidates))
    # Canonical providers retain the requested C winegcc/winebuild argv0 role.
    # C++ aliases are not supported roles, even when they share a canonical file.
    if _package(repo, canonical) != package:
        raise ToolchainError(f'Wrong {name} package owner')
    result = _file(canonical)
    if result['executable'] != canonical:
        raise ToolchainError(f'Canonical {name} role identity changed')
    result['version'] = _run(repo, [result['executable'], '--version']).strip()[:4096]
    return result


def resolve_toolchain(repo: Path, runtime: dict | None = None) -> dict:
    if sys.platform != 'linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise ToolchainError('Only Linux x86_64 publication build architecture is supported')
    repo = Path(repo).absolute()
    catalog = _catalog(repo)
    selection = _selection(repo, catalog, runtime)
    source_version = selection['package']['source_version']
    package = _matched_package(repo, catalog, 'wine64-tools:amd64', source_version)
    headers = _matched_package(repo, catalog, 'libwine-dev:amd64', source_version)
    tools = {name: _wine_tool(repo, name, selection, package) for name in ('winegcc', 'winebuild')}
    for key, command in [('host_cxx', 'g++'), ('mingw_cc', 'x86_64-w64-mingw32-gcc-posix'),
                         ('mingw_cxx', 'x86_64-w64-mingw32-g++-posix')]:
        path = shutil.which(command)
        if path is None:
            raise ToolchainError(f'Missing host build tool: {command}', [command])
        tools[key] = _file(path)
        tools[key]['version'] = _run(repo, [path, '--version']).strip()[:4096]
        target = _run(repo, [path, '-dumpmachine']).strip()
        valid = bool(re.fullmatch(r'x86_64-(?:pc-)?linux-gnu', target)) if key == 'host_cxx' else target == 'x86_64-w64-mingw32'
        if not valid:
            raise ToolchainError(f'Unsupported build tool target: {command}: {target}')
        tools[key]['target'] = target
        major = _run(repo, [path, '-dumpversion']).strip().split('.')[0]
        if not major.isdecimal() or int(major) < 7:
            raise ToolchainError(f'GCC C++17-capable toolchain required: {command}')
    paths = _run(repo, ['dpkg-query', '-L', headers['name']]).splitlines()
    files = {entry['executable']: entry['sha256'] for path in paths if path.endswith('.h') for entry in [_file(path)]}
    if not files or not any(path.endswith('/wine/unixlib.h') for path in files):
        raise ToolchainError('Wine development headers missing', ['libwine-dev'])
    return dict(version=1, repo=str(repo), runtime=runtime, installation=selection, tools=tools,
                tool_package=package, headers=dict(package=headers, files=files))


def verify_toolchain(identity: dict) -> None:
    if identity != resolve_toolchain(Path(identity['repo']), identity['runtime']):
        raise ToolchainError('Pinned publication toolchain changed')


def _selector(name):
    # APT's unqualified spelling selects Architecture:all; identity stays qualified.
    return name.removesuffix(':all')


def _wine_source(source):
    return source == 'wine' or source.startswith('wine-')


def _transaction(repo, packages, protected, source_version):
    output = _run(repo, ['apt-get', '--simulate', '--no-remove', 'install', '-y', *packages])
    actions = []
    for line in output.splitlines():
        match = re.match(r'^(Inst|Remv) ([a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?)(.*)$', line)
        if match:
            actions.append(match.groups())
        elif line.startswith(('Inst ', 'Remv ')):
            raise ToolchainError(f'Unclassifiable simulated package action: {line}')
    catalog = _catalog(repo, {name.split(':')[0] for _, name, _ in actions}) if actions else {}
    admitted = {}
    for action, name, rest in actions:
        if ':' not in name:
            arch = re.search(r'\[([a-z0-9-]+)\]\)\s*$', rest)
            name += ':' + (arch[1] if arch else 'amd64' if name + ':amd64' in catalog else 'all')
        if action == 'Remv':
            raise ToolchainError(f'Simulated transaction changes selected Wine runtime or removes package: {name}')
        version = re.search(r'\((\S+)', rest)
        if version is None:
            raise ToolchainError(f'Unclassifiable simulated package version: {name}')
        if name in protected and version[1] != protected[name]:
            raise ToolchainError(f'Simulated transaction changes selected Wine runtime: {name}')
        rows = [row for row in catalog.get(name, {}).get('versions', []) if row['version'] == version[1]]
        if not rows or any(not row['source'] for row in rows):
            raise ToolchainError(f'Missing source metadata for simulated package: {name}')
        if any(_wine_source(row['source']) for row in rows) or name.split(':')[0].startswith(('wine', 'libwine')):
            _version(catalog, name, binary=version[1], source_version=source_version)
            admitted[name] = version[1]
    return admitted


def plan_setup(repo: Path, operation='main') -> dict:
    """Only fixed setup transactions; no arbitrary package or source argument."""
    if operation not in ('main', 'sccache', 'powershell'):
        raise ToolchainError('Unknown fixed host setup operation')
    catalog = _catalog(repo)
    selection = _selection(repo, catalog, provisioning=True)
    source_version = selection['package']['source_version']
    protected = {name: item['installed']['version'] for name, item in catalog.items()
                 if item['installed'] and _wine_source(item['installed']['source']) and name not in _DEV}
    if selection['file'] is not None:
        protected[selection['package']['name']] = selection['package']['version']
    pins = dict(protected)
    if not pins:
        pins['wine64:amd64'] = selection['implementation']['package']['version']
    for name in _DEV:
        pins[name] = _version(catalog, name, source_version=source_version)['version']
    base = list(SETUP_PACKAGES if operation == 'main' else [operation])
    packages = base + [f'{_selector(name)}={version}' for name, version in sorted(pins.items())]
    admitted = _transaction(repo, packages, protected, source_version)
    additions = {name: version for name, version in admitted.items() if pins.get(name) != version}
    if additions:
        pins.update(additions)
        packages = base + [f'{_selector(name)}={version}' for name, version in sorted(pins.items())]
        repeated = _transaction(repo, packages, protected, source_version)
        if any(pins.get(name) != version for name, version in repeated.items()):
            raise ToolchainError('Wine dependency transaction changed after exact pinning')
    return dict(packages=packages, protected=protected, installation=selection)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3 or sys.argv[1] != 'setup-packages':
            raise ToolchainError('Private fixed host setup operation required')
        plan = plan_setup(Path(__file__).resolve().parents[2], sys.argv[2])
        print('\n'.join(plan['packages']))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'Wine publication setup refused: {error}', file=sys.stderr)
        sys.exit(2)
