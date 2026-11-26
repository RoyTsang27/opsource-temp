#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare the pinned external ZX279133 kernel for Device Build."""

import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DTS = ROOT / 'target/linux/zte/dts/zx279133-sk-d840n.dts'


def checkout(source, path, sparse=()):
    git = ['git', '-C', str(path)]
    path.mkdir()
    subprocess.run(git + ['init', '-q'], check=True, stdout=sys.stderr)
    subprocess.run(git + ['remote', 'add', 'origin', source['url']], check=True)
    fetch = git + ['fetch', '--depth=1', '--no-tags']
    if sparse:
        subprocess.run(git + ['sparse-checkout', 'set', '--no-cone', *sparse], check=True)
        fetch += ['--filter=blob:none']
    subprocess.run(fetch + ['origin', source['commit']], check=True, stdout=sys.stderr)
    subprocess.run(git + ['checkout', '--detach', 'FETCH_HEAD'], check=True, stdout=sys.stderr)
    actual = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
    if actual != source['commit']:
        raise ValueError(f'Expected {source["commit"]} in {path}, got {actual}')


def register_nand(tree):
    header = tree / 'include/linux/mtd/spinand.h'
    core = tree / 'drivers/mtd/nand/spi/core.c'
    makefile = tree / 'drivers/mtd/nand/spi/Makefile'
    for file, anchor, replacement in (
        (header, 'extern const struct spinand_manufacturer ',
         'extern const struct spinand_manufacturer unim_spinand_manufacturer;\n'
         'extern const struct spinand_manufacturer '),
        (core, 'spinand_manufacturers[] = {\n',
         'spinand_manufacturers[] = {\n\t&unim_spinand_manufacturer,\n'),
    ):
        text = file.read_text()
        if anchor not in text or 'unim_spinand_manufacturer' in text:
            raise ValueError(f'Unexpected SPI-NAND registration in {file}')
        file.write_text(text.replace(anchor, replacement, 1))
    with makefile.open('a') as stream:
        stream.write('\nspinand-objs += unim.o\n')


def prepare(entry):
    work = ROOT / 'build_dir/sk-d840n-kernel'
    work.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps(entry, sort_keys=True).encode() +
                         DTS.read_bytes() + Path(__file__).read_bytes()).hexdigest()[:16]
    result = work / key
    # Publish a complete tree only after every source and patch check succeeds.
    with (work / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if result.is_dir():
            return result
        with tempfile.TemporaryDirectory(prefix='prepare-', dir=work) as temporary:
            workspace = Path(temporary)
            board = workspace / 'board'
            kernel = workspace / 'kernel'
            checkout(entry['board_source'], board, (
                '/configs/sk-d840n-stable.json', '/tools/prepare-sk-kernel.py',
                '/kernel-patches/', '/kernel-overlays/',
                '/overlays/target/linux/zte/zx279133/firmware/',
            ))
            checkout(entry['kernel_source'], kernel)
            report = kernel / 'sk-d840n-kernel-provenance.json'
            subprocess.run([
                sys.executable, str(board / 'tools/prepare-sk-kernel.py'),
                '--tree', str(kernel), '--version', entry['kernel'],
                '--cache', str(ROOT / 'dl/sk-d840n-stable'), '--report', str(report),
            ], check=True, stdout=sys.stderr)
            shutil.copytree(board / 'kernel-overlays', kernel, dirs_exist_ok=True)
            shutil.copyfile(DTS, kernel / 'arch/arm64/boot/dts/zte' / DTS.name)
            shutil.copytree(board / 'overlays/target/linux/zte/zx279133/firmware',
                            kernel / 'firmware', dirs_exist_ok=True)
            register_nand(kernel)
            provenance = json.loads(report.read_text())
            provenance.update({
                'board_source': entry['board_source'],
                'kernel_source': entry['kernel_source'],
                'board_dts_sha256': hashlib.sha256(DTS.read_bytes()).hexdigest(),
                'source_directory': result.relative_to(ROOT).as_posix(),
            })
            report.write_text(json.dumps(provenance, indent=2) + '\n')
            kernel.rename(result)
    return result


if __name__ == '__main__':
    data = json.loads((ROOT / 'config/device-build.json').read_text())
    print(prepare(data['devices']['sk-d840n']))
