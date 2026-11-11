#!/usr/bin/env python3
"""Install the LLVM-BPF speed fix into an existing OpenWrt/op-source build tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile

BUNDLE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def safe_path(root, relative):
    parts = PurePosixPath(relative)
    if not parts.parts or parts.is_absolute() or '..' in parts.parts:
        raise ValueError('Unsafe bundle path: ' + relative)
    path = root
    for part in parts.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Update path contains a symbolic link: ' + str(path))
    return path


def plan(root, bundle=BUNDLE):
    if not (root / 'rules.mk').is_file() or not (root / 'tools/llvm-bpf/Makefile').is_file():
        raise ValueError('Pass the build root containing rules.mk and tools/llvm-bpf/Makefile')
    changes = []
    for entry in json.loads((bundle / 'manifest.json').read_text())['files']:
        updated = safe_path(bundle / 'files', entry['path']).read_bytes()
        if digest(updated) != entry['after']:
            raise ValueError('Bundle checksum mismatch: ' + entry['path'])
        path = safe_path(root, entry['path'])
        original = path.read_bytes() if path.exists() else None
        current = digest(original)
        if current == entry['after']:
            continue
        if current not in entry['before']:
            raise ValueError('Locally modified or unsupported file; no files changed: ' + entry['path'])
        changes.append(dict(path=entry['path'], original=original, updated=updated,
                            mode=stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644))
    return changes


def atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply(root, changes):
    if not changes:
        print('LLVM-BPF speed fix is already installed.')
        return None
    parent = safe_path(root, '.llvm-bpf-backups')
    parent.mkdir(mode=0o700, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='speed-', dir=parent))
    journal = []
    for entry in changes:
        if entry['original'] is not None:
            atomic_write(safe_path(backup, entry['path']), entry['original'], entry['mode'])
        journal.append(dict(path=entry['path'], before=digest(entry['original']),
                            after=digest(entry['updated']), mode=entry['mode']))
    (backup / 'manifest.json').write_text(json.dumps(journal, indent=2) + '\n')
    written = []
    try:
        for entry in changes:
            path = safe_path(root, entry['path'])
            original = path.read_bytes() if path.exists() else None
            if original != entry['original']:
                raise ValueError('File changed after preflight: ' + entry['path'])
            written.append(entry)
            atomic_write(path, entry['updated'], entry['mode'])
    except BaseException:
        for entry in reversed(written):
            path = safe_path(root, entry['path'])
            if entry['original'] is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, entry['original'], entry['mode'])
        raise
    print('Installed LLVM-BPF speed fix. Originals: ' + str(backup))
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, help='existing Linux OpenWrt/op-source build root')
    parser.add_argument('--check', action='store_true', help='check compatibility without writing files')
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        changes = plan(root)
        if args.check:
            print('Compatible: {} file(s) to update.'.format(len(changes)))
        else:
            apply(root, changes)
            print('Fastest on Linux x86-64: python3 scripts/setup-llvm-bpf.py')
            print('Source build: make tools/llvm-bpf/compile LLVM_BPF_JOBS=auto V=s')
    except (OSError, ValueError) as error:
        parser.exit(1, 'LLVM-BPF update failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
