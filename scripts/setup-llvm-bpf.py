#!/usr/bin/env python3
"""Install the official prebuilt BPF tools instead of compiling LLVM locally."""
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://downloads.openwrt.org/snapshots/targets/mediatek/filogic/'
TOOLS = ('clang', 'llc', 'opt', 'llvm-dis', 'llvm-strip')
MAX_ARCHIVE = 128 * 1024 * 1024


def request(name):
    return urllib.request.urlopen(urllib.request.Request(
        BASE + name, headers={'User-Agent': 'op-source-llvm-setup'}), timeout=60)


def archive_checksum(name):
    with request('sha256sums') as response:
        total = 0
        for line in response:
            total += len(line)
            if total > 64 * 1024 * 1024:
                raise ValueError('OpenWrt checksum list exceeds the size limit')
            fields = line.decode('ascii').strip().split(maxsplit=1)
            if len(fields) != 2:
                continue
            if fields[1] in (name, './' + name, '*' + name, '*./' + name):
                if not re.fullmatch(r'[0-9a-f]{64}', fields[0]):
                    raise ValueError('Invalid archive SHA256 in OpenWrt checksum list')
                return fields[0]
    raise ValueError('OpenWrt no longer publishes ' + name + '; no configuration was changed')


def download(name, checksum, destination):
    digest = hashlib.sha256()
    size = 0
    with request(name) as response, destination.open('wb') as output:
        while block := response.read(1024 * 1024):
            size += len(block)
            if size > MAX_ARCHIVE:
                raise ValueError('LLVM archive exceeds the size limit')
            digest.update(block)
            output.write(block)
            if size % (16 * 1024 * 1024) == 0:
                print('Downloaded ' + str(size // (1024 * 1024)) + ' MiB', flush=True)
    if digest.hexdigest() != checksum:
        raise ValueError('LLVM archive SHA256 mismatch; retry to fetch a consistent snapshot')


def extract(archive, destination, prefix, zstd):
    if not hasattr(tarfile, 'data_filter'):
        raise ValueError('Safe archive extraction requires Python 3.12 or a patched Python 3.11')

    def checked(member, path):
        parts = Path(member.name).parts
        if not parts or parts[0] not in (prefix, 'llvm-bpf'):
            raise ValueError('Unexpected LLVM archive member: ' + member.name)
        return tarfile.data_filter(member, path)

    with subprocess.Popen([zstd, '-dc', str(archive)], stdout=subprocess.PIPE) as process:
        try:
            with tarfile.open(fileobj=process.stdout, mode='r|') as source:
                source.extractall(destination, filter=checked)
        finally:
            process.stdout.close()
        if process.wait():
            raise ValueError('Cannot decompress the LLVM archive')
    if (destination / 'llvm-bpf').resolve() != (destination / prefix).resolve():
        raise ValueError('Unexpected LLVM archive toolchain link')


def smoke_test(prefix, version, work):
    if (prefix / '.llvm-version').read_text().strip() != version:
        raise ValueError('Prebuilt LLVM version does not match the source recipe')
    for tool in TOOLS:
        result = subprocess.run([str(prefix / 'bin' / tool), '--version'],
                                text=True, capture_output=True)
        if result.returncode:
            raise ValueError(tool + ' cannot run: ' + result.stderr.strip())
        if version not in result.stdout + result.stderr:
            raise ValueError(tool + ' has an unexpected version')
    source = work / 'probe.c'
    source.write_text('int packet_filter(void *ctx) { return ctx != 0; }\n')
    bitcode, optimized, assembly, obj = (work / name for name in
                                       ('probe.bc', 'probe.opt', 'probe.ll', 'probe.o'))
    subprocess.run([str(prefix / 'bin/clang'), '-target', 'bpfel', '-g', '-O2',
                    '-emit-llvm', '-Xclang', '-disable-llvm-passes', '-c', str(source),
                    '-o', str(bitcode)], check=True)
    for tool, arguments, src, dst in (
        ('opt', ['-O2', '-mtriple=bpfel'], bitcode, optimized),
        ('llvm-dis', [], optimized, assembly),
        ('llc', ['-march=bpfel', '-mcpu=v3', '-filetype=obj'], assembly, obj),
    ):
        with src.open('rb') as stdin, dst.open('wb') as stdout:
            subprocess.run([str(prefix / 'bin' / tool)] + arguments,
                           stdin=stdin, stdout=stdout, check=True)
    subprocess.run([str(prefix / 'bin/llvm-strip'), '--strip-debug', str(obj)], check=True)
    header = obj.read_bytes()[:20]
    if len(header) != 20 or header[:4] != b'\x7fELF' or header[5] != 1 or int.from_bytes(header[18:20], 'little') != 247:
        raise ValueError('LLVM smoke test did not produce a BPF ELF object')


def prebuilt_config(text):
    for option in ('BUILD_ALL_HOST_TOOLS', 'BUILDBOT'):
        if 'CONFIG_' + option + '=y' in text.splitlines():
            raise ValueError('Disable CONFIG_' + option + ' for a local prebuilt-toolchain build')
    options = ('BPF_TOOLCHAIN_NONE', 'BPF_TOOLCHAIN_HOST', 'BPF_TOOLCHAIN_BUILD_LLVM',
               'BPF_TOOLCHAIN_PREBUILT', 'USE_LLVM_BUILD', 'USE_LLVM_HOST', 'USE_LLVM_PREBUILT')
    pattern = re.compile(r'^(?:# )?CONFIG_(' + '|'.join(options) + r')(?:=| is not set$)')
    lines = [line for line in text.splitlines() if not pattern.match(line)]
    lines += ['CONFIG_BPF_TOOLCHAIN_PREBUILT=y', 'CONFIG_USE_LLVM_PREBUILT=y']
    lines += ['# CONFIG_' + option + ' is not set' for option in options
              if option not in ('BPF_TOOLCHAIN_PREBUILT', 'USE_LLVM_PREBUILT')]
    return '\n'.join(lines) + '\n'


def configure(root):
    config = root / '.config'
    original = config.read_text()
    selected = prebuilt_config(original)
    backup = root / '.config.llvm-bpf.backup'
    if not backup.exists():
        backup.write_text(original)
    try:
        config.write_text(selected)
        subprocess.run(['make', 'defconfig'], cwd=root, check=True)
        resolved = config.read_text().splitlines()
        if 'CONFIG_USE_LLVM_PREBUILT=y' not in resolved or 'CONFIG_USE_LLVM_BUILD=y' in resolved:
            raise ValueError('Kconfig did not select the prebuilt LLVM toolchain')
    except Exception:
        config.write_text(original)
        raise


def setup(root):
    if (platform.system(), platform.machine()) != ('Linux', 'x86_64'):
        raise ValueError('This official prebuilt archive supports Linux x86-64 only')
    prebuilt_config((root / '.config').read_text())
    recipe = (root / 'tools/llvm-bpf/Makefile').read_text()
    version = re.search(r'^PKG_VERSION:=(\d+\.\d+\.\d+)$', recipe, re.M)[1]
    prefix = 'llvm-bpf-' + version + '.Linux-x86_64'
    name = prefix + '.tar.zst'
    print('Checking OpenWrt prebuilt LLVM ' + version + '...', flush=True)
    checksum = archive_checksum(name)
    print('Official prebuilt LLVM ' + version + ', SHA256 ' + checksum, flush=True)
    path = str(root / 'staging_dir/host/bin') + os.pathsep + os.environ.get('PATH', '')
    zstd = shutil.which('zstd', path=path)
    if not zstd:
        raise ValueError('Install zstd or build tools/zstd before running this helper')
    link = root / 'llvm-bpf'
    if link.exists() and not link.is_symlink():
        raise ValueError('llvm-bpf exists as a directory or file; preserve it before installing')
    target = root / prefix
    with tempfile.TemporaryDirectory(prefix='llvm-bpf-setup-', dir=root) as tmp:
        work = Path(tmp)
        if target.exists():
            marker = target / '.op-source-archive-sha256'
            if not marker.is_file() or marker.read_text().strip() != checksum:
                raise ValueError('An existing toolchain has different provenance; preserve it before installing')
        else:
            archive = work / name
            print('Downloading the prebuilt tools...', flush=True)
            download(name, checksum, archive)
            extract(archive, work, prefix, zstd)
            smoke_test(work / prefix, version, work)
            (work / prefix / '.op-source-archive-sha256').write_text(checksum + '\n')
            (work / prefix).rename(target)
        smoke_test(target, version, work)
        previous_link = link.readlink() if link.is_symlink() else None
        temporary_link = work / 'selected-llvm-bpf'
        temporary_link.symlink_to(prefix)
        temporary_link.replace(link)
        try:
            configure(root)
        except Exception:
            if previous_link is None:
                link.unlink()
            else:
                temporary_link.symlink_to(previous_link)
                temporary_link.replace(link)
            raise
    print('Prebuilt LLVM is selected and passed the BPF compiler smoke test.')
    print('Resume the firmware build; completed source builds were retained.')


if __name__ == '__main__':
    try:
        setup(ROOT)
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as error:
        raise SystemExit('LLVM setup failed: ' + str(error))
