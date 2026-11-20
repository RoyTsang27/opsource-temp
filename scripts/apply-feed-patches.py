#!/usr/bin/env python3
"""Apply repository feed fixes before feeds are indexed; safe to run twice."""
import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def apply(directory, patch, *options):
    return subprocess.run(['git', '-C', str(directory), 'apply', *options, '-'],
                          input=patch, capture_output=True,
                          env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(directory.parent)))


def previous_patches(root, patch, receipt):
    """Find prior project patches without treating arbitrary feed edits as ours."""
    if receipt.is_file():
        yield receipt.read_bytes()
    top = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                         capture_output=True, text=True)
    if top.returncode or Path(top.stdout.strip()).resolve() != root.resolve():
        return
    relative = str(patch.relative_to(root))
    history = subprocess.run(['git', '-C', str(root), 'log', '-16', '--format=%H',
                              '--', relative], capture_output=True, text=True)
    for revision in history.stdout.splitlines():
        old = subprocess.run(['git', '-C', str(root), 'show', f'{revision}:{relative}'],
                             capture_output=True)
        if old.returncode == 0:
            yield old.stdout


def migrate(directory, previous, current):
    """Stage a patch replacement and apply only its delta, preserving local edits."""
    if apply(directory, previous, '--reverse', '--check').returncode:
        return False
    paths = set()
    for patch in (previous, current):
        for name in re.findall(rb'^(?:--- a/|\+\+\+ b/)(\S+)', patch, re.M):
            path = Path(name.decode())
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe feed patch path: ' + str(path))
            paths.add(path)
    if not paths:
        return False
    with tempfile.TemporaryDirectory(prefix='openwrt-feed-patch-') as temporary:
        staging = Path(temporary)
        for side in ('before', 'after'):
            (staging / side).mkdir()
            for path in paths:
                source = directory / path
                if not source.resolve().is_relative_to(directory) or source.is_symlink():
                    raise ValueError('Feed patch traverses a symlink: ' + str(path))
                if source.is_file():
                    destination = staging / side / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
        after = staging / 'after'
        if apply(after, previous, '--reverse').returncode or apply(after, current).returncode:
            return False
        delta = subprocess.run(['git', 'diff', '--no-index', '--no-ext-diff',
                                '--no-textconv', '--', 'before', 'after'],
                               cwd=staging, capture_output=True)
        if delta.returncode != 1:
            return False
        if apply(directory, delta.stdout, '-p2', '--check').returncode:
            return False
        result = apply(directory, delta.stdout, '-p2')
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace'))
    return True


def apply_patches(root, feed, directory):
    receipts = root / 'feeds' / (feed + '.tmp') / 'applied-patches'
    for patch in sorted((root / 'config/feeds-patches' / feed).glob('*.patch')):
        current = patch.read_bytes()
        receipt = receipts / patch.name
        check = apply(directory, current, '--check')
        if check.returncode == 0:
            result = apply(directory, current)
            if result.returncode:
                raise RuntimeError(result.stderr.decode(errors='replace'))
            print(f'Applied {feed}/{patch.name}', flush=True)
        elif apply(directory, current, '--reverse', '--check').returncode == 0:
            print(f'Already applied {feed}/{patch.name}', flush=True)
        else:
            for previous in previous_patches(root, patch, receipt):
                if previous != current and migrate(directory, previous, current):
                    print(f'Updated {feed}/{patch.name}', flush=True)
                    break
            else:
                raise RuntimeError(f'Feed patch {patch.name} does not match {directory}:\n' +
                                   check.stderr.decode(errors='replace'))
        receipts.mkdir(parents=True, exist_ok=True)
        pending = receipt.with_suffix('.new')
        pending.write_bytes(current)
        pending.replace(receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('feed')
    parser.add_argument('--feed-dir', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.feed):
        parser.error('invalid feed name')
    root = Path(__file__).resolve().parent.parent
    directory = (args.feed_dir or root / 'feeds' / args.feed).resolve()
    try:
        apply_patches(root, args.feed, directory)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
