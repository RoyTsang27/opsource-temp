#!/usr/bin/env python3
"""Select and verify an op-source profile before compiling firmware."""
import argparse
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tarfile
import zlib

ROOT = Path(__file__).resolve().parents[1]


def manifest():
    return json.loads((ROOT / 'config/device-build.json').read_text())


def device(name):
    devices = manifest()['devices']
    if name not in devices:
        raise ValueError('Unknown device: ' + name)
    return devices[name]


def selections(text):
    return set(re.findall(r'^CONFIG_TARGET_[^\s=]+_DEVICE_[^\s=]+=y$', text, re.M))


def kernel_version(entry):
    return entry.get('kernel') or manifest()['kernel']


def check_config(name, path):
    entry = device(name)
    settings = set(Path(path).read_text().splitlines())
    expected = 'CONFIG_TARGET_{target}_{subtarget}_DEVICE_{profile}=y'.format(**entry)
    if selections('\n'.join(settings)) != {expected}:
        raise ValueError('Configuration must select exactly one device: ' + expected)
    required = [
        'CONFIG_TARGET_' + entry['target'] + '=y',
        'CONFIG_TARGET_' + entry['target'] + '_' + entry['subtarget'] + '=y',
        'CONFIG_TARGET_ROOTFS_JFFS2=y' if name == 'sk-d840n' else 'CONFIG_TARGET_ROOTFS_SQUASHFS=y',
        'CONFIG_SIGN_FIRMWARE=y',
        'CONFIG_DOWNLOAD_CHECK_CERTIFICATE=y',
        'CONFIG_USE_APK=y',
    ]
    if name == 'sk-d840n':
        required += ['CONFIG_KERNEL_CC_OPTIMIZE_FOR_SIZE=y',
                     'CONFIG_PACKAGE_sk-layout-check=y', 'CONFIG_PACKAGE_luci-ssl-openssl=y']
        if not any(re.fullmatch(r'CONFIG_EXTERNAL_KERNEL_TREE="[^"]+"', s) for s in settings):
            raise ValueError('SK-D840N requires the prepared external ZX279133 kernel')
        if {'CONFIG_TARGET_ROOTFS_SQUASHFS=y', 'CONFIG_TARGET_ROOTFS_INITRAMFS=y',
            'CONFIG_TARGET_ROOTFS_TARGZ=y'} & settings:
            raise ValueError('SK-D840N requires the native241 JFFS2 flash image')
    elif entry['target'] == 'mediatek':
        required += ['CONFIG_PACKAGE_kmod-mt7915e=y', 'CONFIG_PACKAGE_kmod-mt7981-firmware=y',
                     'CONFIG_PACKAGE_mt7981-wo-firmware=y', 'CONFIG_PACKAGE_luci-ssl-openssl=y']
    elif entry['target'] == 'airoha':
        required += ['CONFIG_PACKAGE_kmod-phy-airoha-en8811h=y', 'CONFIG_PACKAGE_ubi-utils=y',
                     'CONFIG_PACKAGE_luci-ssl-openssl=y']
    else:
        required += ['CONFIG_PACKAGE_kmod-mt7603=y', 'CONFIG_PACKAGE_kmod-mt7615e=y',
                     'CONFIG_PACKAGE_kmod-mt7663-firmware-ap=y', 'CONFIG_PACKAGE_kmod-usb2=y',
                     'CONFIG_PACKAGE_luci-ssl=y']
    missing = [setting for setting in required if setting not in settings]
    if missing:
        raise ValueError('Resolved configuration is missing: ' + ', '.join(missing))
    if any(setting in settings for setting in
           ['CONFIG_ALL=y', 'CONFIG_ALL_KMODS=y', 'CONFIG_ALL_NONSHARED=y',
            'CONFIG_TARGET_ALL_PROFILES=y', 'CONFIG_TARGET_MULTI_PROFILE=y']):
        raise ValueError('Broad package/profile selection would defeat isolated device builds')


def check_source():
    data = manifest()
    match = re.fullmatch(r'(6\.18)\.(\d+)', data['kernel'])
    if not match:
        raise ValueError('Unsupported kernel series: ' + data['kernel'])
    series, patchlevel = match.groups()
    checksum = data['kernel_sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', checksum):
        raise ValueError('Invalid kernel source SHA256 in device manifest')
    details = (ROOT / ('target/linux/generic/kernel-' + series)).read_text()
    if not re.search(r'^LINUX_VERSION-' + re.escape(series) + r'\s*=\s*\.' + patchlevel + '$', details, re.M):
        raise ValueError('op-source requires Linux ' + data['kernel'])
    if not re.search(r'^LINUX_KERNEL_HASH-' + re.escape(data['kernel']) + r'\s*=\s*' + checksum + '$', details, re.M):
        raise ValueError('Linux source checksum does not match the device manifest')
    for name, entry in data['devices'].items():
        target = ROOT / 'target/linux' / entry['target']
        target_makefile = (target / 'Makefile').read_text()
        if 'KERNEL_PATCHVER:=6.18' not in target_makefile:
            raise ValueError(name + ': target does not select kernel 6.18')
        image = (target / 'image' / (entry['subtarget'] + '.mk')).read_text()
        match = re.search(r'^define Device/' + re.escape(entry['profile']) + r'\n(.*?)^endef$', image, re.M | re.S)
        if not match or not re.search(r'^TARGET_DEVICES \+= ' + re.escape(entry['profile']) + '$', image, re.M):
            raise ValueError(name + ': device image recipe is missing')
        dts = (target / 'dts' / (entry['dts'] + '.dts')).read_text()
        if '"' + entry['compatible'] + '"' not in dts:
            raise ValueError(name + ': device-tree compatible is missing')
        board = (target / entry['subtarget'] / 'base-files/etc/board.d/02_network').read_text()
        if entry['compatible'] not in board:
            raise ValueError(name + ': board network setup is missing')
        profile = (ROOT / 'configs/devices' / (name + '.config')).read_text()
        expected = 'CONFIG_TARGET_{target}_{subtarget}_DEVICE_{profile}=y'.format(**entry)
        if selections(profile) != {expected}:
            raise ValueError(name + ': preset selects the wrong device')
        if not (target / entry['subtarget'] / 'config-6.18').exists():
            raise ValueError(name + ': missing subtarget config-6.18')
        if 'kernel_source' in entry:
            sublevel = kernel_version(entry).rsplit('.', 1)[-1]
            if f'override LINUX_VERSION-6.18 := .{sublevel}' not in target_makefile:
                raise ValueError(name + ': target kernel version must match the source pin')
            for source in (entry['kernel_source'], entry['board_source']):
                if not re.fullmatch(r'[0-9a-f]{40}', source['commit']):
                    raise ValueError(name + ': source must pin a full commit')
        elif not (target / 'patches-6.18').exists():
            raise ValueError(name + ': missing patches-6.18')
    print('Source checks passed: Linux ' + data['kernel'] + ', ' + str(len(data['devices'])) + ' profiles')


def check_sk_d840n_image(image, rootfs, version):
    prefix = 'sysupgrade-skyworth_sk-d840n/'
    limits = {'CONTROL': 64, 'kernel': 8 << 20, 'dtb': 1 << 20, 'root': 241 << 20}
    with tarfile.open(image, 'r:') as archive:
        members = archive.getmembers()
        files = [member for member in members if member.isreg()]
        if (sorted(member.name for member in files) != sorted(prefix + name for name in limits)
                or any(not member.isreg() and
                       (not member.isdir() or member.name != prefix.rstrip('/')) for member in members)):
            raise ValueError('SK-D840N sysupgrade has invalid archive members')
        for name, limit in limits.items():
            if not 0 < archive.getmember(prefix + name).size <= limit:
                raise ValueError('SK-D840N sysupgrade has empty or oversized ' + name)
        if archive.extractfile(prefix + 'CONTROL').read() != b'BOARD=skyworth_sk-d840n\n':
            raise ValueError('SK-D840N sysupgrade has the wrong CONTROL board')
        with archive.extractfile(prefix + 'kernel') as stream:
            header = stream.read(64)
            payload = stream.read()
        if len(header) != 64:
            raise ValueError('SK-D840N kernel is missing its uImage header')
        magic, header_crc, _, size, load, entry, data_crc, os_id, arch, kind, codec = (
            struct.unpack_from('>7I4B', header))
        if (magic != 0x27051956 or (os_id, arch, kind, codec) != (5, 22, 2, 1)
                or load != 0x80200000 or entry != load or size != len(payload)
                or header_crc != zlib.crc32(header[:4] + bytes(4) + header[8:])
                or data_crc != zlib.crc32(payload)):
            raise ValueError('SK-D840N kernel is not a valid ARM64 gzip uImage')
        with gzip.GzipFile(fileobj=BytesIO(payload)) as kernel:
            raw = kernel.read(64 << 20)
            if kernel.read(1) or not re.search(
                    rb'Linux version ' + re.escape(version.encode()) + rb'(?:[ +\-])', raw):
                raise ValueError('SK-D840N uImage kernel version does not match ' + version)
        with archive.extractfile(prefix + 'dtb') as stream:
            dtb = stream.read()
            if (len(dtb) < 40 or dtb[:4] != b'\xd0\x0d\xfe\xed'
                    or b'skyworth,sk-d840n\0' not in dtb):
                raise ValueError('SK-D840N sysupgrade is missing its board DTB')
        with archive.extractfile(prefix + 'root') as stream, rootfs.open('rb') as standalone:
            if stream.read(2) != b'\x85\x19':
                raise ValueError('SK-D840N sysupgrade root is not little-endian JFFS2')
            stream.seek(0)
            if hashlib.file_digest(stream, 'sha256').digest() != hashlib.file_digest(standalone, 'sha256').digest():
                raise ValueError('SK-D840N sysupgrade root differs from the standalone JFFS2 image')


def check_images(name, directory):
    entry = device(name)
    output = Path(directory)
    data = json.loads((output / 'profiles.json').read_text())
    if data.get('target') != entry['target'] + '/' + entry['subtarget']:
        raise ValueError('Firmware target does not match ' + name)
    version = kernel_version(entry)
    if data.get('linux_kernel', {}).get('version') != version:
        raise ValueError('Firmware kernel does not match ' + version)
    profiles = data.get('profiles', {})
    if set(profiles) != {entry['profile']}:
        raise ValueError('Firmware output must contain exactly the selected profile')
    images = profiles[entry['profile']].get('images', [])
    if not any(image.get('type') == 'sysupgrade' for image in images):
        raise ValueError('No sysupgrade image was produced; check image size in the build log')
    if entry.get('factory_image') and not any(image.get('type') == 'factory' for image in images):
        raise ValueError('No factory image was produced; check image size in the build log')
    for image in images:
        if Path(image['name']).name != image['name']:
            raise ValueError('Invalid image filename in profiles.json')
        path = output / image['name']
        if not path.is_file() or path.stat().st_size != image['size']:
            raise ValueError('Missing or incomplete firmware image: ' + image['name'])
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != image['sha256']:
            raise ValueError('Firmware image checksum mismatch: ' + image['name'])
    if name == 'sk-d840n':
        if sorted(image['type'] for image in images) != ['rootfs', 'sysupgrade']:
            raise ValueError('SK-D840N requires one JFFS2 root and one sysupgrade image')
        paths = {image['type']: output / image['name'] for image in images}
        check_sk_d840n_image(paths['sysupgrade'], paths['rootfs'], version)



def configure(name):
    check_source()
    entry = device(name)
    profile = ROOT / 'configs/devices' / (name + '.config')
    text = (ROOT / 'configs/devices/common.config').read_text() + '\n' + profile.read_text()
    if 'kernel_source' in entry:
        kernel = subprocess.check_output(
            [sys.executable, str(ROOT / 'scripts/prepare-sk-d840n-kernel.py')], text=True
        ).strip()
        # Override the shared SquashFS default and point Kconfig at the pinned tree.
        text = text.replace('CONFIG_TARGET_ROOTFS_SQUASHFS=y\n', '')
        text += f'CONFIG_EXTERNAL_KERNEL_TREE="{kernel}"\n'
    config = ROOT / '.config'
    if config.exists():
        (ROOT / '.config.device-build.backup').write_bytes(config.read_bytes())
    config.write_text(text)
    subprocess.run(['make', 'defconfig'], cwd=ROOT, check=True)
    check_config(name, config)
    print('Configured ' + name + '; previous configuration saved in .config.device-build.backup when present')


def matrix(name):
    data = manifest()
    names = data['default_devices'] if name == 'all' else [name]
    result = []
    for selected in names:
        entry = device(selected)
        result.append({'device': selected, 'target': entry['target'],
                       'subtarget': entry['subtarget'], 'profile': entry['profile'],
                       'kernel': kernel_version(entry)})
    return {'include': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    commands.add_parser('check-source')
    select = commands.add_parser('configure')
    select.add_argument('device')
    build_matrix = commands.add_parser('matrix')
    build_matrix.add_argument('device', nargs='?', default='all')
    check = commands.add_parser('check-config')
    check.add_argument('device')
    check.add_argument('path', nargs='?', default=str(ROOT / '.config'))
    images = commands.add_parser('check-images')
    images.add_argument('device')
    images.add_argument('directory')
    args = parser.parse_args()
    try:
        if args.command == 'list':
            for name, entry in manifest()['devices'].items():
                print(name + '\t' + entry['name'])
        elif args.command == 'check-source':
            check_source()
        elif args.command == 'configure':
            configure(args.device)
        elif args.command == 'matrix':
            print(json.dumps(matrix(args.device), separators=(',', ':')))
        elif args.command == 'check-config':
            check_config(args.device, args.path)
            print('Resolved configuration checks passed for ' + args.device)
        else:
            check_images(args.device, args.directory)
            print('Firmware image checks passed for ' + args.device)
    except (OSError, ValueError, KeyError, EOFError, tarfile.TarError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
