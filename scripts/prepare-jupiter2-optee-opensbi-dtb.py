#!/usr/bin/env python3
"""Configure OP-TEE for the Jupiter2 Pico-ITX reference RAM boot."""
import argparse
from pathlib import Path
import runpy
import struct
import subprocess
import tempfile


def prepare(source, output, uboot_entry):
    fit = runpy.run_path(str(Path(__file__).with_name('build-jupiter2-ram-boot-image.py')))
    data = source.read_bytes()
    root, _ = fit['parse_fdt'](data)
    if b'pico itx' not in root.props.get('model', b'').lower():
        raise ValueError('expected a Jupiter2 Pico-ITX reference U-Boot DTB')
    if uboot_entry != 0x102000000:
        raise ValueError('unexpected reference RAM boot U-Boot entry')
    chosen = root.children.get('chosen')
    if chosen and any(name in chosen.children for name in ('opensbi-domains', 'sbi-mpxy-opteed')):
        raise ValueError('base DTB already contains domain or OP-TEE settings')
    if any(root.props.get(key) != struct.pack('>I', 2) for key in ('#address-cells', '#size-cells')):
        raise ValueError('expected 64-bit RAM and reservation ranges')

    memory = [extent for node in root.children.values()
              if node.props.get('device_type') == b'memory\0'
              for extent in struct.iter_unpack('>QQ', node.props['reg'])]
    _, _, _, _, offset = struct.unpack_from('>5I', data)
    occupied = []
    while offset + 16 <= len(data):
        base, size = struct.unpack_from('>QQ', data, offset)
        if not (base or size):
            break
        occupied.append((base, size))
        offset += 16
    reserved = root.children.get('reserved-memory')
    if reserved:
        occupied.extend(extent for node in reserved.children.values()
                        for extent in struct.iter_unpack('>QQ', node.props.get('reg', b'')))
    # The first stage places the supervisor FDT next to U-Boot in this
    # reference RAM layout. Keep the window read-only in the trusted domain.
    regions = (
        ('core', 0x171000000, 24, 0x38, 0),
        ('shm', 0x172000000, 24, 0x18, 0x18),
        ('uboot-fdt', uboot_entry, 21, 0x08, 0x38),
        ('geu', 0xf0702800, 10, 0x18, 0),
        ('pmu-main', 0xd4050000, 14, 0x18, 0),
        ('pmu-ap', 0xd4282000, 12, 0x18, 0),
    )
    for name, base, order, _, _ in regions[:3]:
        end = base + (1 << order)
        if not any(start <= base and end <= start + size for start, size in memory):
            raise ValueError(f'{name} lies outside reference RAM')
        if name != 'uboot-fdt' and any(base < start + size and start < end for start, size in occupied):
            raise ValueError(f'{name} overlaps an existing reservation')

    cpus = sorted((fit['number'](cpu.props['reg']), name, cpu)
                  for name, cpu in root.children['cpus'].children.items()
                  if cpu.props.get('device_type') == b'cpu\0')
    if ([hart for hart, _, _ in cpus] != list(range(16))
            or any(cpu.props.get('status', b'okay\0') not in (b'okay\0', b'ok\0')
                   or 'opensbi-domain' in cpu.props for _, _, cpu in cpus)):
        raise ValueError('expected unassigned, enabled reference harts 0–15')

    def handles(node):
        for key in ('phandle', 'linux,phandle'):
            if key in node.props:
                yield fit['number'](node.props[key])
        for child in node.children.values():
            yield from handles(child)

    first = max(handles(root), default=0) + 1
    if first + 25 >= 0xffffffff:
        raise ValueError('insufficient phandles')
    tee, host, all_memory = first, first + 1, first + 2
    domains = '/chosen/opensbi-domains'
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        staged = Path(directory) / 'firmware.dtb'
        staged.write_bytes(data)

        def put(*args):
            subprocess.run(['fdtput', *args[:2], str(staged), *args[2:]], check=True)

        def node(path):
            subprocess.run(['fdtput', '-p', '-c', str(staged), path], check=True)

        def cells(path, prop, *values):
            put('-t', 'x', path, prop, *(f'{value:x}' for value in values))

        def string(path, prop, value):
            put('-t', 's', path, prop, value)

        def flag(path, prop):
            subprocess.run(['fdtput', str(staged), path, prop], check=True)

        def region(name, handle, base, order, mmio=False):
            path = f'{domains}/{name}'
            node(path)
            string(path, 'compatible', 'opensbi,domain,memregion')
            cells(path, 'phandle', handle)
            cells(path, 'base', base >> 32, base & 0xffffffff)
            cells(path, 'order', order)
            if mmio:
                flag(path, 'mmio')

        cpu_handles = []
        for hart, name, cpu in cpus:
            path = f'/cpus/{name}'
            handle = cpu.props.get('phandle', cpu.props.get('linux,phandle'))
            cpu_handle = fit['number'](handle) if handle else first + 9 + hart
            if 'phandle' not in cpu.props:
                cells(path, 'phandle', cpu_handle)
            cpu_handles.append(cpu_handle)
            cells(path, 'opensbi-domain', tee)

        node(domains)
        string(domains, 'compatible', 'opensbi,domain,config')
        region('all-memory', all_memory, 0, 64)
        trusted_regions, host_regions = [], []
        for index, (name, base, order, trusted, untrusted) in enumerate(regions):
            handle = first + 3 + index
            region(name, handle, base, order, mmio=index >= 3)
            trusted_regions.extend((handle, trusted))
            host_regions.extend((handle, untrusted))
        host_regions.extend((all_memory, 0x38))
        for name, handle, entry, permissions in (
                ('optee-domain', tee, regions[0][1], trusted_regions),
                ('untrusted-domain', host, uboot_entry, host_regions)):
            path = f'{domains}/{name}'
            node(path)
            string(path, 'compatible', 'opensbi,domain,instance')
            cells(path, 'phandle', handle)
            cells(path, 'possible-harts', *cpu_handles)
            cells(path, 'regions', *permissions)
            cells(path, 'next-addr', entry >> 32, entry & 0xffffffff)
        cells(f'{domains}/untrusted-domain', 'boot-hart', cpu_handles[0])
        flag(f'{domains}/untrusted-domain', 'system-reset-allowed')

        dispatcher = '/chosen/sbi-mpxy-opteed'
        node(dispatcher)
        string(dispatcher, 'compatible', 'riscv,sbi-mpxy-opteed')
        cells(dispatcher, 'opensbi-domain-instance', tee)
        cells(dispatcher, 'riscv,sbi-mpxy-channel-id', *range(0x1000, 0x1010))
        if reserved is None:
            node('/reserved-memory')
            cells('/reserved-memory', '#address-cells', 2)
            cells('/reserved-memory', '#size-cells', 2)
            flag('/reserved-memory', 'ranges')
        for name, base, order, _, _ in regions[:2]:
            path = f'/reserved-memory/optee-{name}@{base:x}'
            node(path)
            cells(path, 'reg', base >> 32, base & 0xffffffff, 0, 1 << order)
            flag(path, 'no-map')
        fit['validate_optee_dtb'](staged.read_bytes())
        output.hardlink_to(staged)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--uboot-entry', type=lambda value: int(value, 0), required=True)
    args = parser.parse_args()
    try:
        prepare(args.source, args.output, args.uboot_entry)
    except (OSError, ValueError, KeyError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(1, f'ERROR: {error}\n')


if __name__ == '__main__':
    main()
