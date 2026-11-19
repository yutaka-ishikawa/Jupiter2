#!/usr/bin/env python3
"""Read the opensbi NOR partition capacity; never open a device for writing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


def positive_size(value):
    try:
        size = int(value, 16 if value.lower().startswith('0x') else 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('use decimal bytes or 0x hexadecimal') from exc
    if size <= 0:
        raise argparse.ArgumentTypeError('capacity must be positive')
    return size


def mtd_capacity(device=None, root=Path('/sys/class/mtd')):
    if device:
        name = device.removeprefix('/dev/')
        if not re.fullmatch(r'mtd[0-9]+', name):
            raise ValueError('--mtd must be mtdN or /dev/mtdN (not mtdblockN)')
        candidates = [root / name]
    else:
        candidates = [p for p in root.glob('mtd[0-9]*')
                      if re.fullmatch(r'mtd[0-9]+', p.name)
                      and (p / 'name').read_text().strip() == 'opensbi']
    if len(candidates) != 1:
        raise ValueError('expected exactly one opensbi MTD partition; use --mtd mtdN')
    entry = candidates[0]
    if (entry / 'name').read_text().strip() != 'opensbi':
        raise ValueError('selected partition is not named opensbi')
    if (entry / 'type').read_text().strip() != 'nor':
        raise ValueError('selected partition is not NOR; do not apply this check to NAND/GPT')
    size = int((entry / 'size').read_text().strip())
    erase = int((entry / 'erasesize').read_text().strip())
    if size <= 0 or erase <= 0 or size % erase:
        raise ValueError('invalid NOR size/erase geometry')
    return {'source': 'sysfs', 'mtd': entry.name, 'partition': 'opensbi',
            'capacity_bytes': size, 'erase_bytes': erase}


def check_image(path, report):
    if not path.is_file():
        raise ValueError('image must be a regular file')
    with path.open('rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
            raise ValueError('image must be a nonempty regular file')
        header = stream.read(4)
        # FIT and DTB share this magic. Capacity validation is not FIT authentication.
        if header != b'\xd0\x0d\xfe\xed':
            raise ValueError('expected final FIT/ITB (FDT magic missing); do not use raw BIN')
        digest = hashlib.sha256(header)
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    result = dict(report)
    result.update(image=str(path), image_bytes=info.st_size,
                  sha256=digest.hexdigest(),
                  remaining_bytes=report['capacity_bytes'] - info.st_size,
                  fits=info.st_size <= report['capacity_bytes'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, help='final fw_dynamic.itb; omit to report capacity')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--mtd', help='live board: opensbi MTD, otherwise auto-discover')
    source.add_argument('--capacity-bytes', type=positive_size,
                        help='offline capacity previously measured on the board')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        report = ({'source': 'offline-explicit', 'capacity_bytes': args.capacity_bytes}
                  if args.capacity_bytes else mtd_capacity(args.mtd))
        if args.image:
            report = check_image(args.image, report)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"Capacity: {report['capacity_bytes']} bytes ({report['source']})")
            if 'mtd' in report:
                print(f"Partition: {report['mtd']} opensbi; erase: {report['erase_bytes']} bytes")
            if args.image:
                print(f"Image: {report['image_bytes']} bytes; remaining: {report['remaining_bytes']} bytes")
                print('FITS (capacity only)' if report['fits'] else 'TOO LARGE: do not flash')
            print('Capacity does not establish the active boot source or firmware compatibility.')
        return 0 if report.get('fits', True) else 1
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
