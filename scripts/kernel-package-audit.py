#!/usr/bin/env python3
"""Check in-tree kmod metadata against a prepared Linux source tree.

This verifies Kconfig and Kbuild references, not compilation or runtime ABI.
Package definitions and version filters are evaluated by the repository's make
macros. Target restrictions are followed through kmod dependencies.
"""
import argparse
import fnmatch
import json
import re
import subprocess
import tempfile
from pathlib import Path


def enabled_expression(expression, values):
    tokens = re.findall(r'\w[\w-]*|&&|\|\||[!()]', expression)
    position = 0

    def atom():
        nonlocal position
        token = tokens[position]
        position += 1
        if token == '!':
            return not atom()
        if token == '(':
            result = either()
            if tokens[position] != ')':
                raise ValueError(expression)
            position += 1
            return result
        return values.get('CONFIG_' + token, '') not in ('', 'n')

    def both():
        nonlocal position
        result = atom()
        while position < len(tokens) and tokens[position] == '&&':
            position += 1
            right = atom()
            result = result and right
        return result

    def either():
        nonlocal position
        result = both()
        while position < len(tokens) and tokens[position] == '||':
            position += 1
            right = both()
            result = result or right
        return result

    result = either()
    if position != len(tokens):
        raise ValueError(expression)
    return result


def resolve(repo, kernel, arch, board, subtarget, version, config):
    values = {
        'CONFIG_LINUX_' + version.replace('.', '_'): 'y',
        'CONFIG_TARGET_' + board: 'y',
        'CONFIG_TARGET_' + board + '_' + subtarget: 'y',
        'CONFIG_USB_SUPPORT': 'y', 'CONFIG_USB_GADGET_SUPPORT': 'y',
        'CONFIG_GPIO_SUPPORT': 'y', 'CONFIG_PCI_SUPPORT': 'y',
        'CONFIG_IPV6': 'y',
    }
    if arch == 'arm64':
        values['CONFIG_ARCH_64BIT'] = 'y'
    if config:
        for line in config.read_text().splitlines():
            match = re.match(r'(CONFIG_\w+)=(.*)', line)
            if match:
                values[match[1]] = match[2]
            match = re.match(r'# (CONFIG_\w+) is not set', line)
            if match:
                values[match[1]] = 'n'
    helpers = (repo / 'include/kernel.mk').read_text().split('version_filter_perl=', 1)[1]
    text = f'''TOPDIR:={repo}
INCLUDE_DIR:=$(TOPDIR)/include
SCRIPT_DIR:=$(TOPDIR)/scripts
LINUX_DIR:={kernel}
ARCH:={'aarch64' if arch == 'arm64' else 'mipsel'}
BOARD:={board}
SUBTARGET:={subtarget}
LINUX_KARCH:={arch}
KERNEL_PATCHVER:={version}
empty:=
space:=$(empty) $(empty)
split_version=$(subst ., ,$(1))
'''
    text += '\n'.join(f'{name}:={value}' for name, value in values.items()) + '\n'
    text += 'version_filter_perl=' + helpers + '''
define KernelPackage
$(eval FILES:=)
$(eval KCONFIG:=)
$(eval AUTOLOAD:=)
$(eval DEPENDS:=)
$(eval $(call KernelPackage/$(1)))
$(eval $(call KernelPackage/$(1)/$(BOARD)))
$(eval $(call KernelPackage/$(1)/$(BOARD)/$(SUBTARGET)))
$(info AUDIT\t$(1)\t$(call version_filter,$(KCONFIG))\t$(call version_filter,$(FILES))\t$(DEPENDS)\t$(AUTOLOAD))
endef
include $(sort $(wildcard $(TOPDIR)/package/kernel/linux/modules/*.mk))
all:
\t@:
'''
    with tempfile.NamedTemporaryFile(mode='w', suffix='.mk') as source:
        source.write(text)
        source.flush()
        result = subprocess.run(['make', '-rR', '-f', source.name], cwd=repo,
                                text=True, capture_output=True, check=True)
    rows = {}
    for line in result.stdout.splitlines():
        if line.startswith('AUDIT\t'):
            _, name, kconfig, files, depends, autoload = line.split('\t', 5)
            rows[name] = dict(kconfig=kconfig.split(), files=files.split(),
                              depends=depends.split(), autoload=autoload.split())
    return rows, values


def audit(repo, kernel, arch, board, subtarget, version, config=None):
    rows, values = resolve(repo, kernel, arch, board, subtarget, version, config)
    symbols = set()
    objects = set()
    files = set()
    for path in kernel.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(kernel)
        files.add(str(relative))
        if path.name.startswith('Kconfig'):
            symbols.update(re.findall(r'^\s*(?:config|menuconfig)\s+(\w+)', path.read_text(errors='replace'), re.M))
        elif path.name in ('Makefile', 'Kbuild'):
            for name in re.findall(r'([\w.+-]+)\.o\b', path.read_text(errors='replace')):
                objects.add(str(relative.parent / (name + '.ko')))

    def available(name, seen=()):
        if name in seen or name not in rows:
            return True
        for item in rows[name]['depends']:
            if item.startswith('@') and not enabled_expression(item[1:], values):
                return False
            if item.startswith('+kmod-') and not available(item[6:], (*seen, name)):
                return False
        return True

    errors = []
    checked = []
    for name, row in rows.items():
        if not available(name):
            continue
        checked.append(name)
        primary = [c[7:] for c in row['kconfig'] if c.startswith('CONFIG_') and '=' not in c]
        if primary and not any(c in symbols for c in primary):
            errors.append(f'{name}: no requested module Kconfig exists: {", ".join(primary)}')
        for filename in row['files']:
            path = Path(filename)
            if not path.is_relative_to(kernel):
                continue
            module = str(path.relative_to(kernel))
            source = module.removesuffix('.ko')
            candidates = [module] if not any(c in module for c in '*?[') else fnmatch.filter(objects, module)
            if not any(candidate in objects for candidate in candidates) and source + '.c' not in files and source + '.S' not in files:
                errors.append(f'{name}: no source or Kbuild object for {module}')
        if any(':' in entry for entry in row['autoload']):
            errors.append(f'{name}: unresolved autoload condition: {row["autoload"]}')
    return dict(kernel=version, target=board + '/' + subtarget,
                definitions=len(rows), checked=len(checked), errors=errors,
                packages=checked)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-tree', type=Path, required=True)
    parser.add_argument('--arch', choices=['arm64', 'mips'], required=True)
    parser.add_argument('--board', required=True)
    parser.add_argument('--subtarget', required=True)
    parser.add_argument('--version', default='7.3')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    result = audit(repo, args.kernel_tree.resolve(), args.arch, args.board,
                   args.subtarget, args.version, args.config)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + '\n')
    print(f'{result["target"]}: checked {result["checked"]} of {result["definitions"]} kernel package definitions')
    for error in result['errors']:
        print('ERROR:', error)
    raise SystemExit(bool(result['errors']))


if __name__ == '__main__':
    main()
