#!/usr/bin/env python3
"""Upgrade a compatible OpenWrt source/build directory to Linux 6.18.59."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import stat
import tempfile
import urllib.request

BUNDLE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def safe_path(root, relative):
    parts = PurePosixPath(relative)
    if not parts.parts or parts.is_absolute() or '..' in parts.parts:
        raise ValueError('Unsafe update path: ' + relative)
    path = root
    for part in parts.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Update path contains a symbolic link: ' + str(path))
    return path


def load_bundle(bundle):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest['kernel'] != '6.18.59':
        raise ValueError('This updater only supports Linux 6.18.59')
    patch = safe_path(bundle, manifest['patch'])
    if digest(patch.read_bytes()) != manifest['patch_sha256']:
        raise ValueError('The bundled source patch failed its checksum check')
    for entry in manifest['files']:
        if entry['after'] is not None:
            payload = safe_path(bundle, entry['payload']).read_bytes()
            if digest(payload) != entry['after']:
                raise ValueError('Update payload failed its checksum check: ' + entry['path'])
    return manifest


def build_plan(root, manifest, bundle):
    if not (root / 'rules.mk').is_file() or not (root / 'target/linux/generic/kernel-6.18').is_file():
        raise ValueError('Pass the OpenWrt build root, such as /home/ubuntu_2604/op')
    changes, conflicts = [], []
    for entry in manifest['files']:
        path = safe_path(root, entry['path'])
        original = path.read_bytes() if path.exists() else None
        current = digest(original)
        if current == entry['after']:
            continue
        if current not in entry['before']:
            conflicts.append(entry['path'])
            continue
        updated = safe_path(bundle, entry['payload']).read_bytes() if entry['after'] else None
        changes.append({'path': entry['path'], 'original': original, 'updated': updated,
                        'mode': stat.S_IMODE(path.stat().st_mode) if original is not None else 0o644})

    relative = 'config/device-build.json'
    path = safe_path(root, relative)
    if path.is_file():
        original = path.read_bytes()
        data = json.loads(original)
        if not isinstance(data, dict):
            raise ValueError('Unsupported device build manifest: ' + relative)
        version = data.get('kernel')
        if version not in manifest['supported_kernels'] or data.get('kernel_sha256') != manifest['supported_kernels'].get(version):
            conflicts.append(relative)
        elif version != manifest['kernel']:
            data['kernel'] = manifest['kernel']
            data['kernel_sha256'] = manifest['kernel_sha256']
            changes.append({'path': relative, 'original': original,
                            'updated': (json.dumps(data, indent=2) + '\n').encode(),
                            'mode': stat.S_IMODE(path.stat().st_mode)})
    if conflicts:
        raise ValueError('No source files were changed. Review these locally modified or unsupported files:\n  ' + '\n  '.join(conflicts))
    return changes


def atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.update-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply(root, changes, version):
    if not changes:
        return None
    parent = safe_path(root, '.kernel-update-backups')
    parent.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path(tempfile.mkdtemp(prefix=version + '-' + stamp + '-', dir=parent))
    journal = []
    for entry in changes:
        if entry['original'] is not None:
            atomic_write(safe_path(backup / 'files', entry['path']), entry['original'], entry['mode'])
        journal.append({'path': entry['path'], 'existed': entry['original'] is not None,
                        'before': digest(entry['original']), 'after': digest(entry['updated']),
                        'mode': entry['mode']})
    (backup / 'manifest.json').write_text(json.dumps({'kernel': version, 'files': journal}, indent=2) + '\n')
    print('Source backup: ' + str(backup), flush=True)
    written = []
    try:
        for entry in changes:
            path = safe_path(root, entry['path'])
            current = path.read_bytes() if path.exists() else None
            if digest(current) != digest(entry['original']):
                raise ValueError('File changed after preflight: ' + entry['path'])
            written.append(entry)
            if entry['updated'] is None:
                path.unlink()
            else:
                atomic_write(path, entry['updated'], entry['mode'])
    except BaseException:
        for entry in reversed(written):
            path = safe_path(root, entry['path'])
            if entry['original'] is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, entry['original'], entry['mode'])
        raise
    return backup


def file_checksum(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def download_kernel(root, manifest):
    if manifest['kernel_url'] != 'https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-' + manifest['kernel'] + '.tar.xz':
        raise ValueError('Unexpected kernel download URL')
    directory = safe_path(root, 'dl')
    directory.mkdir(exist_ok=True)
    target = safe_path(root, 'dl/linux-' + manifest['kernel'] + '.tar.xz')
    expected = manifest['kernel_sha256']
    if target.is_file() and file_checksum(target) == expected:
        print('Using the verified kernel archive already in dl/')
        return
    fd, temporary = tempfile.mkstemp(prefix='.kernel-download-', dir=directory)
    try:
        checksum, size = hashlib.sha256(), 0
        request = urllib.request.Request(manifest['kernel_url'], headers={'User-Agent': 'op-source-kernel-update'})
        with os.fdopen(fd, 'wb') as output, urllib.request.urlopen(request, timeout=60) as response:
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > 512 * 1024 * 1024:
                    raise ValueError('Kernel download exceeds the size limit')
                checksum.update(block)
                output.write(block)
                if size % (32 * 1024 * 1024) == 0:
                    print('Kernel download: ' + str(size // (1024 * 1024)) + ' MiB', flush=True)
        if checksum.hexdigest() != expected:
            raise ValueError('Kernel archive checksum mismatch; source files were not changed')
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
        print('Downloaded and verified Linux ' + manifest['kernel'])
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Existing OpenWrt source/build root')
    parser.add_argument('--check', action='store_true', help='Check compatibility without changing files')
    parser.add_argument('--download', action='store_true', help='Also download the checksum-verified kernel into dl/')
    args = parser.parse_args()
    if args.check and args.download:
        parser.error('--check and --download cannot be combined')
    root = args.directory.resolve()
    try:
        manifest = load_bundle(BUNDLE)
        changes = build_plan(root, manifest, BUNDLE)
        print('Preflight passed: ' + str(len(changes)) + ' source file updates')
        if args.check:
            return
        if args.download:
            download_kernel(root, manifest)
        apply(root, changes, manifest['kernel'])
        print('Source is ready for Linux ' + manifest['kernel'] + '. Rebuild the selected target:')
        print('  cd ' + shlex.quote(str(root)))
        print('  make defconfig\n  make target/linux/clean\n  make package/kernel/mac80211/clean')
        print('  make target/linux/prepare -j1 V=s\n  make -j2 V=s')
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
