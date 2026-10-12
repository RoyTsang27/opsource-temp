#!/usr/bin/env python3
"""Build the pinned OpenWrt host signing tools for integration tests."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def field(source, name, pattern):
    match = re.search(r'^' + name + r'\s*:?=\s*(' + pattern + r')\s*$', source, re.M)
    if not match:
        raise ValueError('Invalid package field: ' + name)
    return match.group(1)


def build(work):
    prefix = work / 'install'
    env = dict(os.environ)
    env['PKG_CONFIG_PATH'] = str(prefix / 'lib/pkgconfig')
    packages = (
        ('json-c', 'package/libs/libjson-c', ['-DBUILD_SHARED_LIBS=OFF', '-DDISABLE_EXTRA_LIBS=TRUE']),
        ('libubox', 'package/libs/libubox', ['-DBUILD_LUA=OFF', '-DBUILD_EXAMPLES=OFF']),
        ('usign', 'package/system/usign', []),
        ('ucert', 'package/system/ucert', ['-DUCERT_FULL=1', '-DUCERT_HOST_BUILD=1',
                                        '-DUSE_RPATH=' + str(prefix / 'lib')]),
        ('fwtool', 'package/system/fwtool', []),
    )
    for name, package, options in packages:
        package = ROOT / package
        makefile = (package / 'Makefile').read_text()
        if name == 'json-c':
            version = field(makefile, 'PKG_VERSION', r'\d+(?:\.\d+)+')
            filename = 'json-c-' + version + '-nodoc.tar.gz'
            url = 'https://s3.amazonaws.com/json-c_releases/releases/' + filename
            checksum = field(makefile, 'PKG_HASH', '[0-9a-f]{64}')
        else:
            date = field(makefile, 'PKG_SOURCE_DATE', r'\d{4}-\d{2}-\d{2}')
            commit = field(makefile, 'PKG_SOURCE_VERSION', '[0-9a-f]{40}')
            filename = name + '-' + date.replace('-', '.') + '~' + commit[:8] + '.tar.zst'
            url = 'https://sources.openwrt.org/' + filename
            checksum = field(makefile, 'PKG_MIRROR_HASH', '[0-9a-f]{64}')
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError('Source checksum failed: ' + filename)
        archive = work / filename
        archive.write_bytes(data)
        source = work / name
        source.mkdir()
        # Extract only after matching the package's trusted source checksum.
        subprocess.run(['tar', '-xf', str(archive), '-C', str(source),
                        '--strip-components=1', '--no-same-owner'], check=True)
        for patch in sorted((package / 'patches').glob('*.patch')):
            with patch.open('rb') as stream:
                subprocess.run(['patch', '-p1', '-d', str(source)], stdin=stream, check=True)
        output = work / (name + '-build')
        subprocess.run(['cmake', '-S', str(source), '-B', str(output),
                        '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
                        '-DCMAKE_INSTALL_PREFIX=' + str(prefix),
                        '-DCMAKE_PREFIX_PATH=' + str(prefix),
                        '-DCMAKE_INSTALL_RPATH=' + str(prefix / 'lib')] + options,
                       env=env, check=True)
        subprocess.run(['cmake', '--build', str(output), '-j2'], env=env, check=True)
        subprocess.run(['cmake', '--install', str(output)], env=env, check=True)
    print('Signing test tools: ' + str(prefix / 'bin'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path, help='New empty build directory')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    build(work)


if __name__ == '__main__':
    main()
