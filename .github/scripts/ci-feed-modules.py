#!/usr/bin/env python3
"""Cross-compile optional feed modules affected by Linux 7.3 API changes."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.request


repo = Path.cwd()
temporary = Path(os.environ['RUNNER_TEMP'])
kernel = temporary / 'kernel'


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def download(urls, target, digest):
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
        except (urllib.error.URLError, TimeoutError):
            continue
        if hashlib.sha256(data).hexdigest() != digest:
            print('Rejected checksum from mirror: ' + url, flush=True)
            continue
        target.write_bytes(data)
        return
    raise RuntimeError('Cannot download ' + target.name)


# Verify the snapshots used to read recipes and apply the repository feed fixes.
feeds = (
    ('packages', 'immortalwrt/packages', 'e731ba76764082d9db71de60f1ddac43f4114101',
     '6fe6f3834c8087e4b2f89285ee86fef9c991a4182a5c3cf83210002f786a8932'),
    ('telephony', 'openwrt/telephony', '5d68d53c160a325ea9d03fce393e051573bcc736',
     'ce2c1b6eaa1a14d3e9fa40ff676a7dc7647de82cc966d8b9c55b1ef209e85c95'),
)
for feed, upstream, commit, digest in feeds:
    assert f'https://github.com/{upstream}.git^{commit}' in (repo / 'feeds.conf.release').read_text()
    archive = temporary / (feed + '.tar.gz')
    download([f'https://codeload.github.com/{upstream}/tar.gz/{commit}'], archive, digest)
    destination = temporary / feed
    destination.mkdir()
    run('tar', '-xzf', archive, '--strip-components=1', '-C', destination)
    run('python3', 'scripts/apply-feed-patches.py', feed, '--feed-dir', destination)

mirrors = ['https://sources.openwrt.org']
mirrors += json.loads((repo / 'scripts/projectsmirrors.json').read_text())['@IMMORTALWRT']
packages = (
    ('packages', 'net/xtables-addons', 'xtables-addons', '.tar.zst'),
    ('telephony', 'libs/dahdi-linux', 'dahdi-linux', '.tar.gz'),
    ('packages', 'libs/libpfring', 'libpfring', '.tar.gz'),
    ('packages', 'devel/lttng-modules', 'lttng-modules', '.tar.bz2'),
    ('packages', 'net/open-app-filter', 'open-app-filter', '.tar.zst'),
    ('packages', 'admin/netatop', 'netatop', '.tar.gz'),
    ('packages', 'net/batman-adv', 'batman-adv', '.tar.gz'),
    ('packages', 'net/coova-chilli', 'coova-chilli', '.tar.bz2'),
    ('packages', 'net/jool', 'jool', '.tar.zst'),
    ('telephony', 'net/rtpengine', 'rtpengine', '.tar.gz'),
    ('packages', 'libs/dmx_usb_module', 'dmx_usb_module', '.tar.gz'),
    ('packages', 'kernel/quectel-qmi-wwan', 'quectel-qmi-wwan', '.tar.gz'),
    ('packages', 'kernel/fibocom-qmi-wwan', 'fibocom-qmi-wwan', '.tar.gz'),
    ('packages', 'kernel/v4l2loopback', 'v4l2loopback', '.tar.zst'),
    ('packages', 'kernel/mdio-netlink', 'mdio-netlink', '.tar.zst'),
    ('packages', 'kernel/mtd-rw', 'mtd-rw', '.tar.zst'),
    ('packages', 'kernel/ovpn-dco', 'ovpn-backports', '.tar.gz'),
)


def compile_package(feed, relative, name, extension):
    package = temporary / feed / relative
    recipe = (package / 'Makefile').read_text()
    values = dict(re.findall(r'^(PKG_\w+):=\s*([^\n]+)$', recipe.replace('\\\n', ''), re.M))
    if values.get('PKG_SOURCE_PROTO') == 'git':
        version = values.get('PKG_VERSION')
        if not version:
            version = values['PKG_SOURCE_DATE'].replace('-', '.') + '~' + values['PKG_SOURCE_VERSION'][:8]
        digest = values['PKG_MIRROR_HASH']
        filename = f'{name}-{version}.tar.zst'
    else:
        version = values['PKG_VERSION']
        digest = values['PKG_HASH']
        filename = values['PKG_SOURCE'].replace('$(PKG_NAME)', name).replace('$(PKG_VERSION)', version)
    assert '$(' not in filename
    assert re.fullmatch('[0-9a-f]{64}', digest)
    archive = temporary / filename
    urls = [mirror.rstrip('/') + '/' + archive.name for mirror in mirrors]
    if name == 'dahdi-linux':
        urls.append(f'https://github.com/asterisk/dahdi-linux/releases/download/v{version}/{archive.name}')
    elif name == 'xtables-addons':
        urls.append('https://inai.de/files/xtables-addons/' + archive.name)
    elif name == 'libpfring':
        urls.append(f'https://codeload.github.com/ntop/PF_RING/tar.gz/{version}')
    elif name == 'lttng-modules':
        urls.append(f'https://lttng.org/files/lttng-modules/{archive.name}')
    elif name == 'netatop':
        urls.append('https://www.atoptool.nl/download/' + archive.name)
    if values.get('PKG_SOURCE_PROTO') != 'git':
        for upstream in values.get('PKG_SOURCE_URL', '').split():
            upstream = upstream.replace('$(PKG_NAME)', name).replace('$(PKG_VERSION)', version)
            if upstream.startswith('https://') and '$(' not in upstream:
                urls.append(upstream.rstrip('/') + '/' + archive.name)
    download(urls, archive, digest)
    source = temporary / name
    source.mkdir()
    compression = '--zstd' if extension.endswith('.zst') else ('-j' if extension.endswith('.bz2') else '-z')
    run('tar', compression, '-xf', archive, '--strip-components=1', '-C', source)
    if (package / 'src').is_dir():
        shutil.copytree(package / 'src', source, dirs_exist_ok=True)
    environment = {**os.environ, 'PATCH': 'patch --fuzz=0'}
    run('scripts/patch-kernel.sh', source, package / 'patches', env=environment)
    if name == 'xtables-addons':
        run('make', '-C', kernel, 'M=' + str(source / 'extensions'),
            'XA_ABSTOPSRCDIR=' + str(source), '-k',
            '-j' + str(os.cpu_count() or 2), 'modules')
        for module in ('rtsp/nf_conntrack_rtsp', 'rtsp/nf_nat_rtsp', 'xt_quota2',
                       'ACCOUNT/xt_ACCOUNT', 'pknock/xt_pknock', 'LUA/xt_LUA'):
            assert (source / 'extensions' / (module + '.ko')).is_file(), module
    elif name == 'dahdi-linux':
        # Also exercise the optional PPP code, which the package leaves disabled.
        run('make', '-C', source, 'KSRC=' + str(kernel), 'DAHDI_BUILD_ALL=',
            'CONFIG_DAHDI=m', 'KCFLAGS=-DCONFIG_DAHDI_PPP', 'modules')
        assert (source / 'drivers/dahdi/dahdi.ko').is_file()
    elif name == 'libpfring':
        run('make', '-C', kernel, 'M=' + str(source / 'kernel'),
            'EXTRA_CFLAGS=-I' + str(source / 'kernel'), 'modules')
        assert (source / 'kernel/pf_ring.ko').is_file()
    elif name == 'lttng-modules':
        run('make', '-C', kernel, 'M=' + str(source), 'CONFIG_LTTNG=m', '-k',
            '-j' + str(os.cpu_count() or 2), 'modules')
        assert (source / 'src/lttng-tracer.ko').is_file()
        assert (source / 'src/probes/lttng-probe-dma-fence.ko').is_file()
        assert (source / 'src/probes/lttng-probe-btrfs.ko').is_file()
    elif name in ('open-app-filter', 'netatop'):
        relative = 'oaf/src' if name == 'open-app-filter' else 'module'
        module = 'oaf' if name == 'open-app-filter' else 'netatop'
        run('make', '-C', kernel, 'M=' + str(source / relative), '-k',
            '-j' + str(os.cpu_count() or 2), 'modules')
        assert (source / relative / (module + '.ko')).is_file()
    elif name == 'jool':
        for relative, module in (('common', 'jool_common'), ('nat64', 'jool'), ('siit', 'jool_siit')):
            destination = source / 'src/mod' / relative
            run('make', '-C', kernel, 'M=' + str(destination), 'CFLAGS_MODULE=-DXTABLES_DISABLED',
                '-k', '-j' + str(os.cpu_count() or 2), 'modules')
            assert (destination / (module + '.ko')).is_file()
    elif name == 'batman-adv':
        backports = temporary / 'backports'
        flags = ['-I' + str(source / 'include')]
        flags += ['-I' + str(backports / relative) for relative in
                  ('backport-include', 'backport-include/uapi', 'include', 'include/uapi')]
        flags += ['-include backport/autoconf.h', '-include backport/backport.h',
                  '-include ' + str(source / 'compat-hacks.h'),
                  '-DBATADV_SOURCE_VERSION=\\"' + version + '\\"']
        options = ['CONFIG_BATMAN_ADV=m']
        for feature in ('BLA', 'DAT', 'MCAST', 'BATMAN_V', 'DEBUG', 'TRACING'):
            options.append('CONFIG_BATMAN_ADV_' + feature + '=y')
            flags.append('-DCONFIG_BATMAN_ADV_' + feature + '=1')
        run('make', '-C', kernel, 'M=' + str(source / 'net/batman-adv'),
            'NOSTDINC_FLAGS=' + ' '.join(flags),
            'KBUILD_EXTRA_SYMBOLS=' + str(backports / 'Module.symvers'), *options,
            '-k', '-j' + str(os.cpu_count() or 2), 'modules')
        assert (source / 'net/batman-adv/batman-adv.ko').is_file()
    else:
        layouts = {
            'coova-chilli': ('src/linux', 'xt_coova'),
            'rtpengine': ('kernel-module', 'xt_RTPENGINE'),
            'dmx_usb_module': ('', 'dmx_usb'),
            'quectel-qmi-wwan': ('', 'qmi_wwan_q'),
            'fibocom-qmi-wwan': ('', 'qmi_wwan_f'),
            'v4l2loopback': ('', 'v4l2loopback'),
            'mdio-netlink': ('kernel', 'mdio-netlink'),
            'mtd-rw': ('', 'mtd-rw'),
            'ovpn-backports': ('drivers/net/ovpn', 'ovpn'),
        }
        relative, module = layouts[name]
        options = []
        if name == 'rtpengine':
            options.append('RTPENGINE_VERSION=' + version)
        elif name == 'ovpn-backports':
            options += ['CONFIG_OVPN=m', 'NOSTDINC_FLAGS=' + ' '.join((
                '-I' + str(source / 'include'), '-I' + str(source / 'compat-include'),
                '-include ' + str(source / 'linux-compat.h')))]
        run('make', '-C', kernel, 'M=' + str(source / relative), *options,
            '-k', '-j' + str(os.cpu_count() or 2), 'modules')
        assert (source / relative / (module + '.ko')).is_file()


failures = []
for package in packages:
    print('Compiling optional module: ' + package[2], flush=True)
    try:
        compile_package(*package)
    except (subprocess.CalledProcessError, RuntimeError, AssertionError) as error:
        failures.append(package[2])
        print(f'Optional module failed: {package[2]}: {error}', flush=True)
for feed, relative, module in (('packages', 'net/siit', 'siit'),
                               ('telephony', 'libs/oslec', 'echo')):
    print('Compiling feed-local module: ' + relative, flush=True)
    source = temporary / (module + '-local')
    shutil.copytree(temporary / feed / relative / 'src', source)
    try:
        run('make', '-C', kernel, 'M=' + str(source), 'modules')
        assert (source / (module + '.ko')).is_file()
    except (subprocess.CalledProcessError, AssertionError) as error:
        failures.append(relative)
        print(f'Feed-local module failed: {relative}: {error}', flush=True)
if failures:
    raise RuntimeError('Optional module checks failed: ' + ', '.join(failures))
