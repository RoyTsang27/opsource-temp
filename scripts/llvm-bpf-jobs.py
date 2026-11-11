#!/usr/bin/env python3
"""Choose LLVM concurrency from RAM headroom, independently of firmware make -j."""
import argparse
import os
from pathlib import Path
import re
import sys

GIB = 1024 ** 3
RAM_PER_JOB = 3 * GIB


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ''


def number(path):
    value = read(path)
    return int(value) if value.isdecimal() else None


def unescape_mount(value):
    return re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), value)


def cgroup_memory(proc):
    """Read this process's v1/v2 memory limits, including visible ancestors."""
    memberships = []
    for line in read(proc / 'self/cgroup').splitlines():
        fields = line.split(':', 2)
        if len(fields) == 3:
            memberships.append((fields[1].split(','), Path(fields[2])))
    seen = set()
    for line in read(proc / 'self/mountinfo').splitlines():
        before, separator, after = line.partition(' - ')
        fields, options = before.split(), after.split()
        if not separator or len(fields) < 5 or len(options) < 3:
            continue
        kind = options[0]
        if kind != 'cgroup2' and not (kind == 'cgroup' and 'memory' in options[2].split(',')):
            continue
        mount_root, mount = (Path(unescape_mount(fields[i])) for i in (3, 4))
        for controllers, member in memberships:
            if (kind == 'cgroup2' and controllers != ['']) or (kind == 'cgroup' and 'memory' not in controllers):
                continue
            try:
                relative = member.relative_to(mount_root)
            except ValueError:
                # A cgroup namespace can expose membership '/' on a subtree mount.
                if member != Path('/'):
                    continue
                relative = Path('.')
            if '..' in relative.parts:
                continue
            current = mount / relative
            while True:
                if current not in seen:
                    seen.add(current)
                    if kind == 'cgroup2':
                        usage = number(current / 'memory.current')
                        limits = ('memory.max', 'memory.high')
                    else:
                        usage = number(current / 'memory.usage_in_bytes')
                        limits = ('memory.limit_in_bytes',)
                    for name in limits:
                        limit = number(current / name)
                        if limit is not None:
                            # Unknown usage must not be treated as an empty container.
                            yield limit, max(0, limit - usage) if usage is not None else 0
                if current == mount:
                    break
                current = current.parent


def cpu_count():
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def auto_jobs(proc=Path('/proc')):
    memory = {}
    for line in read(proc / 'meminfo').splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[1].isdecimal() and fields[2] == 'kB':
            memory[fields[0].rstrip(':')] = int(fields[1]) * 1024
    capacity = memory.get('MemTotal', 0)
    available = min(capacity, memory.get('MemAvailable', 0))
    for limit, headroom in cgroup_memory(proc):
        capacity = min(capacity, limit)
        available = min(available, headroom)
    # Leave space for a linker, the OS and other build tasks. Swap is not RAM.
    reserve = max(2 * GIB, capacity // 4)
    jobs = max(1, min(cpu_count(), max(0, available - reserve) // RAM_PER_JOB))
    return jobs, available, reserve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', default='auto', help='auto (default) or a positive integer')
    parser.add_argument('--explain', action='store_true', help='write the memory budget to stderr')
    args = parser.parse_args()
    if args.jobs == 'auto':
        jobs, available, reserve = auto_jobs()
        if args.explain:
            print('LLVM-BPF: {} worker(s), {:.1f} GiB available, {:.1f} GiB reserved, '
                  '3 GiB budget per worker'.format(jobs, available / GIB, reserve / GIB), file=sys.stderr)
    elif re.fullmatch(r'[1-9][0-9]*', args.jobs):
        jobs = int(args.jobs)
    else:
        parser.error('--jobs must be auto or a positive integer (zero means unlimited in Ninja)')
    print(jobs)


if __name__ == '__main__':
    main()
