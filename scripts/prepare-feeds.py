#!/usr/bin/env python3
"""Make all configured feed packages available before interactive configuration."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(root, *arguments, capture=False):
    return subprocess.run([str(root / 'scripts/feeds'), *arguments], cwd=root,
                          check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def configured_feeds(root):
    # Delegate config parsing (including src-include and src-link) to feeds.
    return [line.split('\t', 3) for line in
            run(root, 'list', '-s', '-d', '\t', capture=True).splitlines()]


def state(root, feeds):
    digest = hashlib.sha256()

    def add(value):
        digest.update(str(value).encode() + b'\0')

    add(feeds)
    inputs = [root / 'scripts' / name for name in
              ('feeds', 'prepare-feeds.py', 'apply-feed-patches.py')]
    inputs += sorted((root / 'config/feeds-patches').rglob('*.patch'))
    for path in inputs:
        add(path.relative_to(root))
        digest.update(path.read_bytes())
    for name, _, _, _ in feeds:
        directory = root / 'feeds' / name
        if not directory.is_dir():
            return None
        for suffix in ('.index', '.targetindex'):
            index = root / 'feeds' / (name + suffix)
            if not index.is_file():
                return None
            digest.update(index.read_bytes())
        # Also notice locally added or edited recipes without fetching Git.
        for path in sorted(directory.rglob('Makefile')):
            info = path.stat()
            add((str(path.relative_to(root)), info.st_mtime_ns, info.st_size))
    for path in sorted((root / 'package/feeds').glob('*/*')):
        add((str(path.relative_to(root)), os.readlink(path) if path.is_symlink() else '',
             path.exists()))
    return digest.hexdigest()


def prepare(root):
    temporary = root / 'tmp'
    temporary.mkdir(exist_ok=True)
    marker = temporary / '.feeds-ready.json'
    # Recursive metadata scans do not invoke this helper. Serialize separate
    # interactive frontends so they cannot update the same indexes together.
    with (temporary / '.feeds-prepare.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        feeds = configured_feeds(root)
        current = state(root, feeds)
        if marker.is_file() and current is not None:
            try:
                if json.loads(marker.read_text()) == current:
                    return
            except (ValueError, OSError):
                pass
        marker.unlink(missing_ok=True)
        missing = [name for name, _, _, _ in feeds
                   if not (root / 'feeds' / name).is_dir()]
        if missing:
            print('Downloading missing feeds for the complete package menu: ' +
                  ', '.join(missing), flush=True)
            run(root, 'update', *missing)
        existing = [name for name, _, _, _ in feeds if name not in missing]
        if existing:
            # Index existing sources in place; never reset or fetch user edits.
            run(root, 'update', '-i', *existing)
        if feeds:
            run(root, 'install', '-a')
        # Force the caller to rescan the newly installed package links.
        for name in ('.packageinfo', '.config-package.in', 'info/.scan-packageinfo.stamp',
                     'info/.scan-targetinfo.stamp'):
            (temporary / name).unlink(missing_ok=True)
        current = state(root, configured_feeds(root))
        if current is None:
            raise RuntimeError('Feed indexes are incomplete; package menu was not generated')
        pending = marker.with_suffix('.new')
        pending.write_text(json.dumps(current) + '\n')
        pending.replace(marker)


def main():
    try:
        prepare(ROOT)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f'Unable to prepare the complete package menu: {error}\n'
                 'Check the feed error above and your feeds.conf overrides. '
                 'Use feeds.conf.default pins with the Linux 7.3 compatibility patches; '
                 'existing feed edits have not been reset.')


if __name__ == '__main__':
    main()
