#!/usr/bin/env python3
"""Fail closed when release inputs or the resolved build policy are unsafe."""
import argparse
from pathlib import Path
import re
import subprocess

REQUIRED_OPTIONS = (
    'USE_APK', 'SIGN_FIRMWARE', 'REQUIRE_IMAGE_SIGNATURE', 'SIGNED_PACKAGES',
    'SIGN_EACH_PACKAGE', 'SIGNATURE_CHECK', 'DOWNLOAD_CHECK_CERTIFICATE',
    'PACKAGE_ucert', 'PACKAGE_luci-ssl-openssl', 'PKG_CC_STACKPROTECTOR_STRONG',
    'KERNEL_CC_STACKPROTECTOR_STRONG', 'PKG_FORTIFY_SOURCE_2', 'PKG_RELRO_FULL',
    'USE_SECCOMP', 'JSON_CYCLONEDX_SBOM',
)
PON_PACKAGES = (
    'kmod-airoha-xpon', 'kmod-airoha-pon-frontend', 'airoha-ponctl',
    'airoha-pond', 'airoha-pon-debug', 'luci-app-pon', 'luci-app-iptv',
)


def missing_pon_packages(settings):
    if settings.intersection({'CONFIG_TARGET_airoha_an7581=y', 'CONFIG_TARGET_airoha_an7583=y'}):
        return ['PACKAGE_' + package for package in PON_PACKAGES
                if 'CONFIG_PACKAGE_' + package + '=y' not in settings]
    return []


def check_pon_config(path):
    missing = missing_pon_packages(set(Path(path).read_text().splitlines()))
    if missing:
        raise ValueError('Missing core PON packages: ' + ', '.join(missing))


def check_tag(tag):
    # A leading '-' must never become an option to gh, git, or another tool.
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', tag):
        raise ValueError('Release tag must be 1-80 letters, digits, dots, underscores or hyphens, starting with a letter or digit')
    if subprocess.run(['git', 'check-ref-format', 'refs/tags/' + tag],
                      capture_output=True).returncode:
        raise ValueError('Release tag is not a valid Git reference')


def check_config(path):
    settings = set(Path(path).read_text().splitlines())
    missing = [option for option in REQUIRED_OPTIONS
               if 'CONFIG_' + option + '=y' not in settings]
    missing += missing_pon_packages(settings)
    if missing:
        raise ValueError('Missing release security settings: ' + ', '.join(missing))


def check_feeds(path, defaults='feeds.conf.default'):
    expected = {}
    for line in Path(defaults).read_text().splitlines():
        if line.startswith('src-git '):
            _, name, url = line.split()
            expected[name] = url
    actual = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        parts = line.split()
        if len(parts) != 3 or parts[0] != 'src-git':
            raise ValueError('Release feeds must use src-git')
        _, name, source = parts
        match = re.fullmatch(r'(https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git)\^([0-9a-f]{40})', source)
        if not match or name in actual:
            raise ValueError('Invalid or duplicate release feed: ' + name)
        actual[name] = match.group(1)
    if actual != expected:
        raise ValueError('Release feed names and upstream URLs must match feeds.conf.default')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag')
    parser.add_argument('--config')
    parser.add_argument('--pon-config', help='Check PON selections independently of release hardening')
    parser.add_argument('--feeds', default='feeds.conf.release')
    args = parser.parse_args()
    try:
        if args.tag is not None:
            check_tag(args.tag)
        check_feeds(args.feeds)
        if args.config:
            check_config(args.config)
        if args.pon_config:
            check_pon_config(args.pon_config)
    except ValueError as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
