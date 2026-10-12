#!/usr/bin/env python3
"""Check the actual tcboot factory image's FIT and reserved UBI volumes."""
import argparse
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

KERNEL_SLOT = 8 * 1024 * 1024
ERASEBLOCK = 128 * 1024
MAX_IMAGE = 255 * 1024 * 1024


def check(path, fdtget):
    if not KERNEL_SLOT < path.stat().st_size <= MAX_IMAGE:
        raise ValueError('Factory image size exceeds the tcboot layout')
    image = path.read_bytes()
    magic, size = struct.unpack_from('>II', image)
    if magic != 0xd00dfeed or not 40 <= size <= KERNEL_SLOT:
        raise ValueError('Factory image does not begin with a bounded FIT')

    with tempfile.TemporaryDirectory() as directory:
        fit = Path(directory) / 'kernel.itb'
        dtb = Path(directory) / 'board.dtb'
        fit.write_bytes(image[:size])

        def get(file, node, prop, kind='s'):
            return subprocess.check_output([fdtget, '-t', kind, str(file), node, prop],
                                           text=True).strip()

        config = '/configurations/' + get(fit, '/configurations', 'default')
        kernel = '/images/' + get(fit, config, 'kernel')
        cells = get(fit, kernel, 'load', 'x').split()
        load = 0
        for cell in cells:
            load = (load << 32) | int(cell, 16)
        if len(cells) not in (1, 2) or load != 0x80088000:
            raise ValueError('FIT kernel has the wrong tcboot load address')
        fdt = '/images/' + get(fit, config, 'fdt')
        dtb.write_bytes(bytes(int(byte, 16) for byte in get(fit, fdt, 'data', 'bx').split()))
        if 'nokia,xg-040g-md-tcboot' not in get(dtb, '/', 'compatible').split():
            raise ValueError('FIT contains a different board device tree')

    payload = image[KERNEL_SLOT:]
    if len(payload) % ERASEBLOCK:
        raise ValueError('Factory UBI payload is not eraseblock aligned')
    table = None
    for offset in range(0, len(payload), ERASEBLOCK):
        block = payload[offset:offset + ERASEBLOCK]
        if block[:4] != b'UBI#' or len(block) != ERASEBLOCK:
            raise ValueError('Invalid UBI eraseblock')
        if (zlib.crc32(block[:60]) ^ 0xffffffff) != struct.unpack_from('>I', block, 60)[0]:
            raise ValueError('UBI erase-counter header CRC failed')
        vid, data = struct.unpack_from('>II', block, 16)
        if not 64 <= vid <= data <= ERASEBLOCK - 64 or block[vid:vid + 4] != b'UBI!':
            raise ValueError('Invalid UBI volume header offsets')
        if struct.unpack_from('>I', block, vid + 8)[0] == 0x7fffefff:
            table = block[data:]
            break
    if table is None:
        raise ValueError('UBI volume table is missing')

    volumes = {}
    for index in range(128):
        record = table[index * 172:(index + 1) * 172]
        if len(record) != 172:
            raise ValueError('Truncated UBI volume table')
        if (zlib.crc32(record[:168]) ^ 0xffffffff) != struct.unpack_from('>I', record, 168)[0]:
            raise ValueError('UBI volume table CRC failed')
        reserved = struct.unpack_from('>I', record)[0]
        if not reserved:
            continue
        length = struct.unpack_from('>H', record, 14)[0]
        if length > 127:
            raise ValueError('Invalid UBI volume name')
        name = record[16:16 + length].decode('ascii')
        volumes[name] = (index, record[12], reserved, record[144])
    if volumes.get('kernel', (None,))[0] != 0 or volumes.get('rootfs', (None,))[0] != 1:
        raise ValueError('tcboot kernel/rootfs volume IDs changed')
    for name in ('bosa', 'ri'):
        if name not in volumes or volumes[name][1] != 2 or volumes[name][2] < 3:
            raise ValueError('Missing reserved static PON volume: ' + name)
    print('tcboot FIT/load address, board identity and reserved PON volumes verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('factory', type=Path)
    parser.add_argument('--fdtget', default='fdtget')
    args = parser.parse_args()
    try:
        check(args.factory, args.fdtget)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
