#!/usr/bin/env python3
"""Apply repository feed fixes before feeds are indexed; safe to run twice."""
import argparse
import re
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('feed')
    parser.add_argument('--feed-dir', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.feed):
        parser.error('invalid feed name')
    root = Path(__file__).resolve().parent.parent
    directory = (args.feed_dir or root / 'feeds' / args.feed).resolve()
    for patch in sorted((root / 'config/feeds-patches' / args.feed).glob('*.patch')):
        command = ['git', '-C', str(directory), 'apply']
        check = subprocess.run([*command, '--check', str(patch)], capture_output=True, text=True)
        if check.returncode == 0:
            subprocess.run([*command, str(patch)], check=True)
            print(f'Applied {args.feed}/{patch.name}', flush=True)
            continue
        reverse = subprocess.run([*command, '--reverse', '--check', str(patch)], capture_output=True)
        if reverse.returncode == 0:
            print(f'Already applied {args.feed}/{patch.name}', flush=True)
            continue
        raise SystemExit(f'Feed patch {patch.name} does not match {directory}:\n{check.stderr}')


if __name__ == '__main__':
    main()
