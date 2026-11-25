#!/usr/bin/env python3
"""Compare a Jupiter2 board capture against repository reference evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys


HARDWARE = Path(__file__).resolve().parents[1] / 'hardware/jupiter2'
CAPTURES = HARDWARE / 'captures'
LINUX_REFERENCE = CAPTURES / '20261108-075700'
STORAGE_REFERENCE = CAPTURES / '20261120-101205'
FASTBOOT_REFERENCE = CAPTURES / '20261124-165032' / 'spl-fastboot.log'
VENDOR_REFERENCE = {
    'FSBL.bin': '5aa430998807eecb65771ad9e0f2ddf158afb31d75121f7c9f4cae8b733d3ce5',
    'esos.itb': 'f6afe0f6bcc1f5448198a349819ce9c46d528d646abd358f6c11f66b9e871cd4',
    'fw_dynamic.itb': '19c9a072bd7b25077b14a48fc0bb5af5841e307ff1c123009696ed2a8b8784ee',
    'u-boot.itb': '0bfc5bf77fef9d9b9cfdee2f84ec900a2e8cc10483a984e389aa683ae02f0bb0',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def dtb_fields(path, parse_fdt):
    root, _ = parse_fdt(path.read_bytes())
    cpus = root.children.get('cpus')
    reserved = root.children.get('reserved-memory')

    def regions(nodes):
        return {node.name: {key: node.props[key].hex()
                            for key in ('reg', 'size', 'alignment', 'alloc-ranges', 'status',
                                        'compatible', 'no-map', 'reusable') if key in node.props}
                for node in nodes}

    return {
        'DTB model': root.props.get('model', b'').rstrip(b'\0').decode('ascii') or None,
        'DTB compatible': root.props.get('compatible', b'').rstrip(b'\0').decode('ascii').split('\0'),
        'DTB timebase (Hz)': int.from_bytes(cpus.props['timebase-frequency'], 'big')
        if cpus and 'timebase-frequency' in cpus.props else None,
        'DTB CPU nodes': regions(node for node in cpus.children.values()
                                 if node.props.get('device_type') == b'cpu\0') if cpus else None,
        'DTB memory': regions(node for node in root.children.values()
                              if node.props.get('device_type') == b'memory\0'),
        'DTB reserved memory': regions(reserved.children.values()) if reserved else {},
    }


def cpu_fields(path):
    if not path.is_file():
        return None
    selected = ('processor', 'hart', 'model name', 'isa', 'mmu', 'mvendorid', 'marchid', 'mimpid')
    rows = []
    for block in path.read_text().split('\n\n'):
        fields = {key.strip(): value.strip() for line in block.splitlines()
                  if ':' in line for key, value in [line.split(':', 1)]}
        if fields.get('processor', '').isdecimal():
            rows.append({key: fields[key] for key in selected if key in fields})
    return sorted(rows, key=lambda row: int(row['processor'])) or None


def nor_geometry(directory):
    report = directory / 'jupiter2-nor-capacity.json'
    if report.is_file():
        data = json.loads(report.read_text())
        if data.get('partition') != 'opensbi' or data.get('source') != 'sysfs':
            raise ValueError('expected a live opensbi NOR capacity report')
        capacity, erase = data['capacity_bytes'], data['erase_bytes']
        if type(capacity) is not int or type(erase) is not int or erase <= 0 or capacity <= 0 or capacity % erase:
            raise ValueError('invalid NOR capacity or erase size')
        return capacity, erase
    backups = sorted(directory.glob('opensbi-partition-info-*'))
    if not backups:
        return None, None
    if len(backups) != 1:
        raise ValueError('multiple OpenSBI backups; provide jupiter2-nor-capacity.json')
    backup, = backups
    if ((backup / 'name.txt').read_text().strip(), (backup / 'type.txt').read_text().strip()) != ('opensbi', 'nor'):
        raise ValueError('expected an opensbi NOR partition backup')
    return tuple(int((backup / name).read_text()) for name in ('size.txt', 'erasesize.txt'))


def compare(capture):
    scripts = Path(__file__).resolve().parent
    parse_fdt = runpy.run_path(str(scripts / 'build-jupiter2-ram-boot-image.py'))['parse_fdt']
    parse_fastboot = runpy.run_path(str(scripts / 'build-jupiter2-reference-ram-boot.py'))['fastboot_download_limit']
    rows = []

    def add(item, reference, observed):
        status = 'UNAVAILABLE' if reference is None or observed is None else (
            'MATCH' if reference == observed else 'DIFFERENT')
        rows.append((status, item, reference, observed))

    reference_dtb = LINUX_REFERENCE / 'running.dtb'
    board_dtb = capture / 'running.dtb'
    add('Linux DTB SHA-256', digest(reference_dtb), digest(board_dtb))
    if not board_dtb.is_file():
        board_dtb = capture / 'running-reconstructed.dtb'
    reference_fields = dtb_fields(reference_dtb, parse_fdt)
    observed_fields = dtb_fields(board_dtb, parse_fdt) if board_dtb.is_file() else {}
    for name, value in reference_fields.items():
        add(name, value, observed_fields.get(name))

    add('CPU and ISA per processor', cpu_fields(LINUX_REFERENCE / 'cpuinfo.txt'),
        cpu_fields(capture / 'cpuinfo.txt'))
    for name in ('uname.txt', 'cmdline.txt', 'lsblk.txt', 'findmnt.txt', 'proc-mtd.txt'):
        reference = LINUX_REFERENCE if name == 'uname.txt' else STORAGE_REFERENCE
        add(f'{name} SHA-256', digest(reference / name), digest(capture / name))
    backups = sorted(STORAGE_REFERENCE.glob('jupiter2-rollback-*/env_k3.txt'))
    add('env_k3.txt SHA-256', digest(backups[0]) if len(backups) == 1 else None,
        digest(capture / 'env_k3.txt'))
    for name, expected, actual in zip(('OpenSBI NOR capacity (bytes)', 'NOR erase size (bytes)'),
                                      nor_geometry(STORAGE_REFERENCE), nor_geometry(capture)):
        add(name, expected, actual)
    fastboot = capture / 'spl-fastboot.log'
    add('SPL Fastboot limit (bytes)', parse_fastboot(FASTBOOT_REFERENCE),
        parse_fastboot(fastboot) if fastboot.is_file() else None)
    for name, reference in VENDOR_REFERENCE.items():
        add(f'vendor/{name} SHA-256', reference,
            digest(capture / 'vendor' / name))
    return rows, board_dtb.name if board_dtb.is_file() else 'unavailable'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture_id', help='directory name under hardware/jupiter2/captures')
    args = parser.parse_args()
    capture = CAPTURES / args.capture_id
    if capture.resolve().parent != CAPTURES.resolve() or not capture.is_dir():
        parser.error('specify an existing capture ID under hardware/jupiter2/captures')

    try:
        rows, dtb = compare(capture)
    except (OSError, ValueError, KeyError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    print(f'Capture: {capture.name}; Linux DTB: {dtb}')
    print(f'References: {LINUX_REFERENCE.name}, {STORAGE_REFERENCE.name}, '
          f'{FASTBOOT_REFERENCE.parent.name} (historical transcription), pinned vendor hashes')
    for status, item, reference, observed in rows:
        print(f'{status:11} {item}')
        if status == 'DIFFERENT':
            print(f'  reference: {json.dumps(reference, ensure_ascii=False)}')
            print(f'  observed:  {json.dumps(observed, ensure_ascii=False)}')
        elif status == 'UNAVAILABLE':
            missing = [label for label, value in [('reference', reference), ('observed', observed)]
                       if value is None]
            print(f'  missing: {", ".join(missing)}')
    print('PMP CSR, boot source, and runtime behavior require separate evidence.')
    return int(any(status != 'MATCH' for status, *_ in rows))


if __name__ == '__main__':
    sys.exit(main())
