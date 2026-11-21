#!/usr/bin/env python3
"""Check device package defaults after make defconfig, without building firmware."""
import argparse
import json
from pathlib import Path
import re


def read_config(path):
    return dict(re.findall(r'^CONFIG_([^=]+)=(.*)$', Path(path).read_text(), re.M))


def read_providers(path):
    providers = {}
    package = None
    for line in Path(path).read_text().splitlines():
        if line.startswith('Source-Makefile:'):
            package = None
        elif line.startswith('Package: '):
            package = line.split(': ', 1)[1]
            providers.setdefault(package, set()).add(package)
        elif package and line.startswith('Provides: '):
            for name in line.split(': ', 1)[1].split():
                providers.setdefault(name.lstrip('@'), set()).add(package)
    return providers


def check_defaults(settings, providers):
    profiles = sorted(name for name, value in settings.items()
                      if value == 'y' and re.fullmatch(
                          r'TARGET_(?:DEVICE_)?[a-z0-9_]+_DEVICE_.+', name))
    required = {}
    for name, value in settings.items():
        if (name.startswith('DEFAULT_') and not name.startswith('DEFAULT_TARGET_')
                and value == 'y'):
            required[name[len('DEFAULT_'):]] = {'y'}
        elif name.startswith('MODULE_DEFAULT_') and value in ('y', 'm'):
            required.setdefault(name[len('MODULE_DEFAULT_'):], {'y', 'm'})
    if not profiles or not required:
        raise ValueError('No resolved device defaults; run make defconfig first')
    missing = []
    resolved = {}
    for package, allowed in sorted(required.items()):
        selected = {name: settings.get('PACKAGE_' + name)
                    for name in providers.get(package, {package})
                    if settings.get('PACKAGE_' + name) in allowed}
        if selected:
            resolved[package] = selected
        else:
            missing.append(package + ' (expected ' + '/'.join(sorted(allowed)) + ')')
    if missing:
        raise ValueError('Device defaults are missing: ' + ', '.join(missing))
    return {'profiles': profiles, 'defaults': resolved}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='.config')
    parser.add_argument('--packageinfo', default='tmp/.packageinfo')
    parser.add_argument('--json', type=Path, help='Write the selected defaults and providers')
    args = parser.parse_args()
    try:
        result = check_defaults(read_config(args.config), read_providers(args.packageinfo))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('Verified {} device profile(s), {} package defaults'.format(
        len(result['profiles']), len(result['defaults'])))


if __name__ == '__main__':
    main()
