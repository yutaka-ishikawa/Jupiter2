#!/usr/bin/env python3
"""Configure OP-TEE for the Jupiter2 Pico-ITX reference RAM boot."""
import argparse
from pathlib import Path
import runpy
import struct
import subprocess
import tempfile


CORE_BASE = 0x171000000
EVENT_LOG_BASE = 0x171ff0000
BOOT_DTB_SIZE = 0x11000
PICO_ITX_OPTEE_HEAP_BYTES = 0x30000


def private_boot_dtb_buffer(elf_path, bin_path):
    """Locate the reserved writable section in the ELF paired with tee.bin."""
    try:
        from elftools.common.exceptions import ELFError
        from elftools.elf.elffile import ELFFile
    except ImportError as error:
        raise ValueError('install python3-pyelftools to inspect tee.elf') from error

    image = bin_path.read_bytes()
    with elf_path.open('rb') as stream:
        try:
            elf = ELFFile(stream)
            section = elf.get_section_by_name('.k3_boot_dtb')
            if (elf.elfclass != 64 or not elf.little_endian
                    or elf['e_machine'] != 'EM_RISCV' or elf['e_entry'] != CORE_BASE
                    or section is None or section['sh_type'] != 'SHT_NOBITS'
                    or section['sh_flags'] != 0x3):
                raise ValueError('tee.elf needs an allocated RW .k3_boot_dtb reservation')
            start, size = section['sh_addr'], section['sh_size']
            end = start + size
            if (size != BOOT_DTB_SIZE or start & 0xfff
                    or start < CORE_BASE + 0x1000 or end > EVENT_LOG_BASE):
                raise ValueError('private boot DTB overlaps another part of the Core')
            if not any(seg['p_type'] == 'PT_LOAD' and seg['p_flags'] & 2
                       and seg['p_vaddr'] == seg['p_paddr']
                       and seg['p_paddr'] + seg['p_filesz'] <= start
                       and end <= seg['p_paddr'] + seg['p_memsz']
                       for seg in elf.iter_segments()):
                raise ValueError('private boot DTB is outside a writable physical ELF segment')
            last = 0
            for loaded in elf.iter_sections():
                if (not loaded['sh_flags'] & 2 or loaded['sh_type'] == 'SHT_NOBITS'
                        or not loaded['sh_size']):
                    continue
                offset = loaded['sh_addr'] - CORE_BASE
                limit = offset + loaded['sh_size']
                if offset < 0 or image[offset:limit] != loaded.data():
                    raise ValueError('tee.bin does not match the loadable bytes in tee.elf')
                last = max(last, limit)
            if last != len(image) or len(image) > start - CORE_BASE:
                raise ValueError('tee.bin length does not match the ELF or overlaps its boot DTB')
        except ELFError as error:
            raise ValueError('invalid OP-TEE ELF') from error
    return start, size


def prepare(source, output, uboot_entry, optee_elf=None, optee_bin=None, pico_itx_pmp16=False):
    fit = runpy.run_path(str(Path(__file__).with_name('build-jupiter2-ram-boot-image.py')))
    data = source.read_bytes()
    root, _ = fit['parse_fdt'](data)
    if b'pico itx' not in root.props.get('model', b'').lower():
        raise ValueError('expected a Jupiter2 Pico-ITX reference U-Boot DTB')
    if uboot_entry != 0x102000000:
        raise ValueError('unexpected reference RAM boot U-Boot entry')
    if bool(optee_elf) != bool(optee_bin):
        raise ValueError('--optee-elf and --optee-bin must be supplied together')
    boot_buffer = private_boot_dtb_buffer(optee_elf, optee_bin) if optee_elf else None
    if pico_itx_pmp16 and not boot_buffer:
        raise ValueError('the Pico-ITX 16-slot layout requires a private OP-TEE boot DTB')
    if pico_itx_pmp16 and (root.props.get('model') != b'spacemit k3 pico itx board\0'
                            or b'spacemit,k3' not in root.props.get('compatible', b'').split(b'\0')):
        raise ValueError('the 16-slot layout requires the reference Pico-ITX firmware DTB')
    chosen = root.children.get('chosen')
    chosen_children = chosen.children if chosen else {}
    if any(name in chosen_children for name in ('opensbi-domains', 'sbi-mpxy-opteed')):
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
    shared = (
        ('core', CORE_BASE, 24, 0x38, 0, False),
        ('shm', 0x172000000, 24, 0x18, 0x18, False),
    )
    if pico_itx_pmp16:
        # Declare domain access only. The K3 firmware fixes the slot indices
        # and verifies the inherited OpenSBI, ESOS and RPMI protections.
        regions = shared + (
            ('i2c3', 0xf0614000, 12, None, 0x18, True),
            ('protected-mmio', 0xf0000000, 25, None, 0, True),
            ('pmu-main', 0xd4050000, 14, None, 0, True),
            ('dciu', 0xd8440000, 16, None, 0, True),
            ('geu-prng', 0xf0702000, 13, 0x18, None, True),
            ('te200', 0xf0718000, 14, 0x18, None, True),
            ('sec-ciu', 0xf0580000, 12, 0x18, None, True),
            ('rtc', 0xf0615000, 12, 0x18, None, True),
            ('iopmp0', 0xf0800000, 19, 0x18, None, True),
            ('iopmp1', 0xf0880000, 16, 0x18, None, True),
        )
        ram_regions = shared
    else:
        regions = shared + (
            # The first stage places the original DTB next to U-Boot.
            ('uboot-fdt', uboot_entry, 21, 0x08, 0x38, False),
            ('geu', 0xf0702000, 12, 0x18, 0, True),
            ('pmu-main', 0xd4050000, 14, 0x18, 0, True),
            ('pmu-ap', 0xd4282000, 12, 0x18, 0, True),
        )
        ram_regions = regions[:3]
    for name, base, order, _, _, _ in ram_regions:
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
    cpu_handle_start = first + 3 + len(regions)
    if cpu_handle_start + len(cpus) >= 0xffffffff:
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
            cpu_handle = fit['number'](handle) if handle else cpu_handle_start + hart
            if 'phandle' not in cpu.props:
                cells(path, 'phandle', cpu_handle)
            cpu_handles.append(cpu_handle)
            cells(path, 'opensbi-domain', tee)

        node(domains)
        string(domains, 'compatible', 'opensbi,domain,config')
        region('all-memory', all_memory, 0, 64)
        trusted_regions, host_regions = [], []
        for index, (name, base, order, trusted, untrusted, mmio) in enumerate(regions):
            handle = first + 3 + index
            region(name, handle, base, order, mmio=mmio)
            if trusted is not None:
                trusted_regions.extend((handle, trusted))
            if untrusted is not None:
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
        if boot_buffer:
            base, size = boot_buffer
            cells(dispatcher, 'spacemit,optee-boot-dtb', base >> 32,
                  base & 0xffffffff, 0, size)
        if pico_itx_pmp16:
            flag(dispatcher, 'spacemit,pico-itx-pmp16')
            # The generic per-hart default is insufficient for the three
            # domains, MPXY and all 16 harts. Use OpenSBI's existing setting.
            configs = [(name, config) for name, config in chosen_children.items()
                       if b'opensbi,config' in config.props.get('compatible', b'').split(b'\0')]
            if len(configs) > 1:
                raise ValueError('multiple opensbi,config nodes in the base DTB')
            heap_bytes = PICO_ITX_OPTEE_HEAP_BYTES
            if configs:
                name, config = configs[0]
                heap = config.props.get('heap-size')
                if heap is not None:
                    if len(heap) != 4:
                        raise ValueError('OpenSBI heap-size must be a single DTB cell')
                    heap_bytes = max(heap_bytes, fit['number'](heap))
                config_path = f'/chosen/{name}'
            else:
                if 'opensbi-config' in chosen_children:
                    raise ValueError('base /chosen/opensbi-config lacks opensbi,config compatibility')
                config_path = '/chosen/opensbi-config'
                node(config_path)
                string(config_path, 'compatible', 'opensbi,config')
            cells(config_path, 'heap-size', heap_bytes)
        if reserved is None:
            node('/reserved-memory')
            cells('/reserved-memory', '#address-cells', 2)
            cells('/reserved-memory', '#size-cells', 2)
            flag('/reserved-memory', 'ranges')
        for name, base, order, _, _, _ in shared:
            path = f'/reserved-memory/optee-{name}@{base:x}'
            node(path)
            cells(path, 'reg', base >> 32, base & 0xffffffff, 0, 1 << order)
            flag(path, 'no-map')
        blob = staged.read_bytes()
        if boot_buffer and len(blob) > boot_buffer[1]:
            raise ValueError('generated firmware DTB exceeds the private boot buffer')
        fit['validate_optee_dtb'](blob)
        output.hardlink_to(staged)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--uboot-entry', type=lambda value: int(value, 0), required=True)
    parser.add_argument('--optee-elf', type=Path)
    parser.add_argument('--optee-bin', type=Path)
    parser.add_argument('--pico-itx-pmp16', action='store_true')
    args = parser.parse_args()
    try:
        prepare(args.source, args.output, args.uboot_entry, args.optee_elf,
                args.optee_bin, args.pico_itx_pmp16)
    except (OSError, ValueError, KeyError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(1, f'ERROR: {error}\n')


if __name__ == '__main__':
    main()
