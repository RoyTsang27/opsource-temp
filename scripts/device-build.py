#!/usr/bin/env python3
"""Select and verify a Device Build profile before compiling firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

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


def check_config(name, path):
    entry = device(name)
    settings = set(Path(path).read_text().splitlines())
    expected = 'CONFIG_TARGET_{target}_{subtarget}_DEVICE_{profile}=y'.format(**entry)
    if selections('\n'.join(settings)) != {expected}:
        raise ValueError('Configuration must select exactly one device: ' + expected)
    required = [
        'CONFIG_TARGET_' + entry['target'] + '=y',
        'CONFIG_TARGET_' + entry['target'] + '_' + entry['subtarget'] + '=y',
        'CONFIG_TARGET_ROOTFS_SQUASHFS=y',
        'CONFIG_SIGN_FIRMWARE=y',
        'CONFIG_DOWNLOAD_CHECK_CERTIFICATE=y',
        'CONFIG_USE_APK=y',
    ]
    required += (['CONFIG_PACKAGE_kmod-mt7915e=y', 'CONFIG_PACKAGE_kmod-mt7981-firmware=y',
                  'CONFIG_PACKAGE_mt7981-wo-firmware=y', 'CONFIG_PACKAGE_luci-ssl-openssl=y']
                 if entry['target'] == 'mediatek' else
                 ['CONFIG_PACKAGE_kmod-mt7603=y', 'CONFIG_PACKAGE_kmod-mt7615e=y',
                  'CONFIG_PACKAGE_kmod-mt7663-firmware-ap=y', 'CONFIG_PACKAGE_kmod-usb2=y',
                  'CONFIG_PACKAGE_luci-ssl=y'])
    missing = [setting for setting in required if setting not in settings]
    if missing:
        raise ValueError('Resolved configuration is missing: ' + ', '.join(missing))
    if any(setting in settings for setting in
           ['CONFIG_ALL=y', 'CONFIG_ALL_KMODS=y', 'CONFIG_ALL_NONSHARED=y',
            'CONFIG_TARGET_ALL_PROFILES=y', 'CONFIG_TARGET_MULTI_PROFILE=y']):
        raise ValueError('Broad package/profile selection would defeat isolated device builds')


def check_source():
    data = manifest()
    version = data['kernel']
    series, revision = version.rsplit('.', 1)
    generic = ROOT / 'target/linux/generic'
    details = (generic / ('kernel-' + series)).read_text()
    checksum = data['kernel_sha256']
    expected = {
        'LINUX_VERSION-' + series: '.' + revision,
        'LINUX_KERNEL_HASH-' + version: checksum,
    }
    assignments = dict(re.findall(r'^([^\s=]+)[ \t]*=[ \t]*([^\s]+)$', details, re.M))
    if not re.fullmatch(r'[a-f0-9]{64}', checksum):
        raise ValueError('Invalid Linux source checksum in the Device Build manifest')
    if any(assignments.get(key) != value for key, value in expected.items()):
        raise ValueError('Linux ' + version + ' source version or checksum differs from the manifest')
    if not (generic / ('config-' + series)).is_file():
        raise ValueError('Missing generic config-' + series)
    for name, entry in data['devices'].items():
        target = ROOT / 'target/linux' / entry['target']
        subtarget = target / entry['subtarget']
        declarations = (target / 'Makefile').read_text() + '\n' + (subtarget / 'target.mk').read_text()
        selected = re.findall(r'^KERNEL_PATCHVER[ \t]*:?=[ \t]*(\d+\.\d+)[ \t]*$', declarations, re.M)
        if not selected or selected[-1] != series:
            raise ValueError(name + ': target does not select kernel ' + series)
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
        if not (subtarget / ('config-' + series)).is_file():
            raise ValueError(name + ': missing subtarget config-' + series)
        if not (target / ('patches-' + series)).is_dir():
            raise ValueError(name + ': missing patches-' + series)
    print('Source checks passed: Linux ' + data['kernel'] + ', ' + str(len(data['devices'])) + ' profiles')


def check_images(name, directory):
    entry = device(name)
    output = Path(directory)
    data = json.loads((output / 'profiles.json').read_text())
    if data.get('target') != entry['target'] + '/' + entry['subtarget']:
        raise ValueError('Firmware target does not match ' + name)
    if data.get('linux_kernel', {}).get('version') != manifest()['kernel']:
        raise ValueError('Firmware kernel does not match ' + manifest()['kernel'])
    profiles = data.get('profiles', {})
    if set(profiles) != {entry['profile']}:
        raise ValueError('Firmware output must contain exactly the selected profile')
    images = profiles[entry['profile']].get('images', [])
    if not any(image.get('type') == 'sysupgrade' for image in images):
        raise ValueError('No sysupgrade image was produced; check image size in the build log')
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


def configure(name):
    check_source()
    device(name)
    profile = ROOT / 'configs/devices' / (name + '.config')
    text = (ROOT / 'configs/devices/common.config').read_text() + '\n' + profile.read_text()
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
                       'subtarget': entry['subtarget'], 'profile': entry['profile']})
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
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
