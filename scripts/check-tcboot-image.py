#!/usr/bin/env python3
"""Verify the shared MD/TF tcboot factory envelope and bootable UBI payload."""
import argparse
from pathlib import Path
import struct
import zlib

KERNEL_SLOT = 8 * 1024 * 1024
ERASEBLOCK = 128 * 1024
MAX_IMAGE = 255 * 1024 * 1024
LAYOUT_VOLUME = 0x7fffefff


def valid_crc(data):
    return (zlib.crc32(data[:-4]) ^ 0xffffffff) == int.from_bytes(data[-4:], 'big')


def check_ubi(payload, fit):
    if not payload or len(payload) % ERASEBLOCK:
        raise ValueError('Factory UBI payload is not eraseblock aligned')
    tables = {}
    first_blocks = {}
    for offset in range(0, len(payload), ERASEBLOCK):
        block = payload[offset:offset + ERASEBLOCK]
        header = block[:64]
        if header[:4] != b'UBI#' or not valid_crc(header):
            raise ValueError('Invalid UBI erase-counter header')
        if header[5:8] == b'EOF':
            raise ValueError('tcboot UBI must not contain EOF markers: U-Boot may relocate the volume table past them')
        vid_offset, data_offset = struct.unpack_from('>II', header, 16)
        if (vid_offset, data_offset) != (2048, 4096):
            raise ValueError('tcboot requires VID/data offsets 2048/4096')
        vid = block[vid_offset:vid_offset + 64]
        if vid[:4] != b'UBI!' or not valid_crc(vid):
            raise ValueError('Invalid UBI volume header')
        volume, leb = struct.unpack_from('>II', vid, 8)
        data = block[data_offset:]
        if volume == LAYOUT_VOLUME:
            if leb not in (0, 1) or leb in tables:
                raise ValueError('Invalid UBI layout volume copies')
            tables[leb] = data[:128 * 172]
        elif leb == 0:
            first_blocks[volume] = data
    if set(tables) != {0, 1} or tables[0] != tables[1]:
        raise ValueError('UBI requires two matching volume tables')
    names = []
    for index in range(128):
        record = tables[0][index * 172:(index + 1) * 172]
        if len(record) != 172 or not valid_crc(record):
            raise ValueError('Invalid UBI volume table CRC')
        if not int.from_bytes(record[:4], 'big'):
            continue
        length = int.from_bytes(record[14:16], 'big')
        if not 0 < length <= 127:
            raise ValueError('Invalid UBI volume name')
        names.append((index, record[16:16 + length]))
    if names != [(0, b'kernel'), (1, b'rootfs'), (2, b'rootfs_data')]:
        raise ValueError('tcboot requires kernel/rootfs/rootfs_data IDs 0/1/2')
    # Compare the start of the UBI kernel against the raw recovery FIT.
    kernel = first_blocks.get(0, b'')
    if not kernel or kernel[:min(len(fit), len(kernel))] != fit[:len(kernel)]:
        raise ValueError('UBI kernel does not match the recovery FIT')
    if first_blocks.get(1, b'')[:4] != b'hsqs':
        raise ValueError('UBI rootfs is not SquashFS')


def check(path):
    if not KERNEL_SLOT < path.stat().st_size <= MAX_IMAGE:
        raise ValueError('Factory image size exceeds the tcboot layout')
    image = path.read_bytes()
    magic, size = struct.unpack_from('>II', image)
    if magic != 0xd00dfeed or not 40 <= size <= KERNEL_SLOT:
        raise ValueError('Factory image must start with a bounded FIT')
    check_ubi(image[KERNEL_SLOT:], image[:size])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    args = parser.parse_args()
    try:
        check(args.image)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    print('tcboot factory FIT, UBI volume layout and absence of EOF markers verified')


if __name__ == '__main__':
    main()
