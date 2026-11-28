#!/usr/bin/env python3
"""Verify or install the mt76 security patches in an OpenWrt or ImmortalWrt source tree."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import tempfile


PIN = '0936617dc529ff9da0385221d3fa6de732231177'
UPSTREAM = 'https://github.com/openwrt/mt76'
PACKAGE = Path('package/kernel/mt76')
MARKER = '.mt76-security-20261128.json'
RELEASE = re.compile(rb'^(PKG_RELEASE[ \t]*:?=[ \t]*)([0-9]+)([ \t]*(?:#[^\r\n]*)?\r?)$', re.M)


class InstallError(Exception):
    pass


def regular(path):
    if path.is_symlink() or not path.is_file():
        raise InstallError(f'Expected a regular file at {path}')
    return path.read_bytes()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bundle():
    here = Path(__file__).resolve().parent
    patch_dir = here / 'patches'
    if not patch_dir.is_dir():
        patch_dir = here.parent / PACKAGE / 'patches'
    checksums = json.loads(regular(here / 'mt76-security-sha256.json'))
    patches = {}
    for name, expected in checksums.items():
        if not re.fullmatch(r'[0-9][0-9a-zA-Z_.-]*\.patch', name):
            raise InstallError(f'Invalid name in the bundle manifest: {name}')
        data = regular(patch_dir / name)
        if digest(data) != expected:
            raise InstallError(f'Bundle checksum mismatch for {name}')
        patches[name] = data
    if not patches:
        raise InstallError('Empty patch bundle')
    return patches, checksums


def setting(data, name):
    values = re.findall(rb'^' + name + rb'[ \t]*:?=[ \t]*([^\r\n#]+)', data, re.M)
    if len(values) != 1:
        raise InstallError(f'Expected exactly one {name.decode()} assignment')
    return values[0].strip().decode()


def read_recipe(recipe):
    data = regular(recipe)
    pin = setting(data, b'PKG_SOURCE_VERSION')
    if pin != PIN:
        raise InstallError(f'This bundle requires mt76 {PIN}, but the package pins {pin}')
    if setting(data, b'PKG_SOURCE_PROTO') != 'git' or setting(data, b'PKG_SOURCE_URL') not in (UPSTREAM, UPSTREAM + '.git'):
        raise InstallError('Expected the official openwrt/mt76 Git source')
    if len(RELEASE.findall(data)) != 1:
        raise InstallError('Expected a single numeric PKG_RELEASE')
    return data, RELEASE.search(data)[2].decode()


def with_release(recipe, release):
    return RELEASE.sub(lambda match: match[1] + release.encode() + match[3], recipe, count=1)


def target(root):
    package = root.resolve()
    for part in PACKAGE.parts:
        package /= part
        if package.is_symlink() or not package.is_dir():
            raise InstallError(f'Expected a package directory at {package}')
    folder = package / 'patches'
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise InstallError(f'Expected a patch directory at {folder}')
    return package, folder


@contextmanager
def package_lock(package):
    fd = os.open(package, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def installed(folder, checksums):
    marker = folder / MARKER
    if not marker.exists() and not marker.is_symlink():
        return None
    data = json.loads(regular(marker))
    if data['pin'] != PIN or data['patches'] != checksums:
        raise InstallError('The installation manifest does not match this bundle')
    original, current = data['original_release'], data['installed_release']
    if not (re.fullmatch(r'[0-9]+', original) and current == str(int(original) + 1)):
        raise InstallError('Invalid package release in the installation manifest')
    for name, expected in checksums.items():
        if digest(regular(folder / name)) != expected:
            raise InstallError(f'Installed patch changed: {name}')
    return original, current


def existing(folder, checksums, managed):
    patches = {}
    for path in folder.glob('*'):
        if path.name.startswith('.'):
            continue
        if path.name in checksums:
            if not managed:
                raise InstallError(f'Existing patch would be overwritten: {path.name}')
            continue
        if path.suffix not in ('.patch', '.diff'):
            raise InstallError(f'Unsupported entry in patch directory: {path.name}')
        patches[path.name] = regular(path)
    return patches


def run(*args, cwd=None, data=None):
    result = subprocess.run(args, cwd=cwd, input=data, capture_output=True)
    if result.returncode:
        output = (result.stdout + result.stderr).decode(errors='replace').strip()
        raise InstallError(f'{args[0]} failed: {output[-4000:]}')
    return result.stdout


def preflight(source, patches):
    with tempfile.TemporaryDirectory(prefix='mt76-security-') as scratch:
        scratch = Path(scratch)
        if source is None:
            source = scratch / 'source'
            run('git', 'init', '-q', str(source))
            run('git', '-C', str(source), 'fetch', '-q', '--depth=1', UPSTREAM, PIN)

        archive = scratch / 'source.tar'
        run('git', '-C', str(source), 'archive', '--format=tar', '-o', str(archive), PIN)
        tree = scratch / 'tree'
        tree.mkdir()
        with tarfile.open(archive) as tar:
            for member in tar:
                name = Path(member.name)
                if name.is_absolute() or '..' in name.parts:
                    raise InstallError(f'Unexpected archive path: {name}')
                if member.isfile():
                    path = tree / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as file:
                        path.write_bytes(file.read())
        for name in sorted(patches):
            try:
                run('patch', '-f', '-F', '0', '-p1', cwd=tree, data=patches[name])
            except InstallError as error:
                raise InstallError(f'Preflight failed at {name}\n{error}') from error


def replace(path, data, mode):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.mt76-', delete=False) as file:
        temporary = Path(file.name)
    try:
        temporary.write_bytes(data)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def transaction(changes):
    originals = {
        path: (regular(path), stat.S_IMODE(path.stat().st_mode))
        if path.exists() or path.is_symlink() else (None, 0o644)
        for path in changes
    }
    applied = []
    try:
        for path, contents in changes.items():
            if contents is None:
                path.unlink()
            else:
                replace(path, contents, originals[path][1])
            applied.append(path)
    except BaseException:
        for path in reversed(applied):
            contents, mode = originals[path]
            if contents is None:
                path.unlink()
            else:
                replace(path, contents, mode)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'apply', 'status', 'rollback'))
    parser.add_argument('--root', '--openwrt', required=True, type=Path, help='OpenWrt or ImmortalWrt build root')
    parser.add_argument('--source', type=Path, help='local mt76 Git repository containing the pinned commit')
    args = parser.parse_args()
    package, folder = target(args.root)
    recipe = package / 'Makefile'
    patches, checksums = bundle()

    with package_lock(package):
        contents, release = read_recipe(recipe)
        state = installed(folder, checksums)
        if state and release != state[1]:
            raise InstallError('PKG_RELEASE changed after installation')
        if args.action == 'status':
            print(f'Installed: {len(patches)} patches, package release {release}' if state else 'Bundle absent')
            return

        marker = folder / MARKER
        if args.action == 'rollback':
            if not state:
                raise InstallError('This bundle has no installation to roll back')
            changes = {folder / name: None for name in patches}
            transaction({**changes, recipe: with_release(contents, state[0]), marker: None})
            print(f'Rolled back {len(patches)} patches and restored package release {state[0]}')
            return

        extra = existing(folder, checksums, state)
        preflight(args.source, {**extra, **patches})
        if (regular(recipe) != contents or installed(folder, checksums) != state
                or existing(folder, checksums, state) != extra):
            raise InstallError('The package changed during verification. Retry with a stable checkout.')
        print(f'Verified {len(extra)} existing patches and {len(patches)} bundle patches against {PIN[:8]}')
        if args.action == 'verify' or state:
            return

        updated = str(int(release) + 1)
        record = {'pin': PIN, 'patches': checksums, 'original_release': release, 'installed_release': updated}
        folder.mkdir(exist_ok=True)
        changes = {folder / name: data for name, data in patches.items()}
        transaction({**changes, recipe: with_release(contents, updated),
                     marker: (json.dumps(record, indent=2, sort_keys=True) + '\n').encode()})
        print(f'Installed {len(patches)} patches and bumped package release to {updated}')


if __name__ == '__main__':
    try:
        main()
    except (InstallError, KeyError, OSError, TypeError, ValueError) as error:
        print(f'mt76 installer: {error}', file=sys.stderr)
        sys.exit(1)
