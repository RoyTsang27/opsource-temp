#!/usr/bin/env python3
"""Track OpenWrt's Airoha kernel patch level without switching kernel series."""
import argparse
import json
import os
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'PonWrt-kernel-check'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(1024 * 1024).decode('utf-8')


def kernel_series(makefile):
    match = re.search(r'^KERNEL_PATCHVER\s*:?=\s*(\d+\.\d+)\s*$', makefile, re.M)
    if not match:
        raise ValueError('Cannot determine the Airoha kernel series')
    return match.group(1)


def kernel_details(content, series):
    # Accept only the two expected Make assignments, never upstream shell code.
    pattern = (r'LINUX_VERSION-' + re.escape(series) + r'\s*=\s*\.(\d+)\s*\n'
               r'LINUX_KERNEL_HASH-' + re.escape(series) + r'\.(\d+)\s*=\s*([0-9a-f]{64})\s*')
    match = re.fullmatch(pattern, content)
    if not match or match.group(1) != match.group(2):
        raise ValueError('Invalid upstream kernel version/checksum file')
    return int(match.group(1)), match.group(3)


def sync(write=False):
    local_series = kernel_series((ROOT / 'target/linux/airoha/Makefile').read_text())
    ref = json.loads(fetch('https://api.github.com/repos/openwrt/openwrt/git/ref/heads/master'))
    sha = ref['object']['sha']
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid upstream commit')
    base = 'https://raw.githubusercontent.com/openwrt/openwrt/' + sha + '/'
    upstream_series = kernel_series(fetch(base + 'target/linux/airoha/Makefile'))
    if upstream_series != local_series:
        raise ValueError('OpenWrt Airoha now uses Linux ' + upstream_series +
                         '; rebase and test PonWrt drivers before changing from ' + local_series)
    path = ROOT / ('target/linux/generic/kernel-' + local_series)
    local_patch, local_hash = kernel_details(path.read_text(), local_series)
    content = fetch(base + 'target/linux/generic/kernel-' + local_series)
    patch, checksum = kernel_details(content, local_series)
    if patch < local_patch:
        raise ValueError('Refusing to downgrade the kernel')
    if patch == local_patch and checksum != local_hash:
        raise ValueError('Kernel checksum changed without a version bump; investigate upstream')
    changed = patch > local_patch
    if write and changed:
        path.write_text('LINUX_VERSION-' + local_series + ' = .' + str(patch) + '\n' +
                        'LINUX_KERNEL_HASH-' + local_series + '.' + str(patch) + ' = ' + checksum + '\n')
    result = {'changed': str(changed).lower(), 'version': local_series + '.' + str(patch),
              'upstream_sha': sha}
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            for key, value in result.items():
                output.write(key + '=' + value + '\n')
    print('OpenWrt Airoha: Linux ' + result['version'] + ' at ' + sha)
    if changed:
        print('Updated kernel version/checksum' if write else 'Kernel update available')
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Apply a newer patch level in the same series')
    args = parser.parse_args()
    try:
        changed = sync(args.write)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, str(error) + '\n')
    if changed and not args.write:
        parser.exit(1, 'Run with --write, then prepare/build both Airoha targets\n')


if __name__ == '__main__':
    main()
