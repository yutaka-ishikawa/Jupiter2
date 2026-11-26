#!/usr/bin/env python3
"""Wire the Jupiter2 Linux DTB to the OP-TEE channels in its OpenSBI DTB."""

import argparse
from pathlib import Path
import runpy
import struct
import subprocess
import tempfile


def nodes(node, path='/'):
    yield path, node
    for name, child in node.children.items():
        yield from nodes(child, path.rstrip('/') + '/' + name)


def prepare(opensbi_dtb, linux_dtb, output):
    fit = runpy.run_path(str(Path(__file__).with_name('build-jupiter2-ram-boot-image.py')))
    firmware = opensbi_dtb.read_bytes()
    fit['validate_optee_dtb'](firmware)
    root, _ = fit['parse_fdt'](firmware)
    dispatcher = root.children['chosen'].children['sbi-mpxy-opteed']
    firmware_reserved = root.children.get('reserved-memory')
    optee_reserved = {name: child.props['reg']
                      for name, child in firmware_reserved.children.items()
                      if name.startswith(('optee-core@', 'optee-shm@'))} if firmware_reserved else {}
    channels = [cell for cell, in struct.iter_unpack(
        '>I', dispatcher.props['riscv,sbi-mpxy-channel-id'])]
    if len(channels) != 16 or len(set(channels)) != 16:
        raise ValueError('expected 16 distinct OP-TEE channels in hart order')

    data = linux_dtb.read_bytes()
    root, _ = fit['parse_fdt'](data)
    mailboxes = [(path, node) for path, node in nodes(root)
                 if b'riscv,sbi-mpxy-mbox' in node.props.get('compatible', b'').split(b'\0')
                 and node.props.get('status', b'okay\0') in (b'okay\0', b'ok\0')]
    if len(mailboxes) != 1:
        raise ValueError('Linux DTB must contain exactly one enabled SBI MPXY mailbox')
    mailbox_path, mailbox = mailboxes[0]
    if mailbox.props.get('#mbox-cells') != struct.pack('>I', 2):
        raise ValueError('Linux MPXY mailbox must use two argument cells')
    handle = mailbox.props.get('phandle', mailbox.props.get('linux,phandle'))
    add_handle = handle is None
    if add_handle:
        handles = [int.from_bytes(node.props[prop], 'big') for _, node in nodes(root)
                   for prop in ('phandle', 'linux,phandle') if prop in node.props]
        next_handle = max(handles, default=0) + 1
        if next_handle >= 0xffffffff:
            raise ValueError('no free Linux DT phandle')
        handle = struct.pack('>I', next_handle)
    if len(handle) != 4 or not int.from_bytes(handle, 'big'):
        raise ValueError('Linux MPXY mailbox requires a valid phandle')
    if any(b'linaro,optee-tz' in node.props.get('compatible', b'').split(b'\0')
           for _, node in nodes(root)):
        raise ValueError('Linux DTB already contains an OP-TEE node')

    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        staged = Path(directory) / 'linux.dtb'
        staged.write_bytes(data)

        def edit(options, *arguments):
            subprocess.run(['fdtput', *options, str(staged), *arguments], check=True)

        if optee_reserved:
            reserved = root.children.get('reserved-memory')
            if reserved is None:
                edit(['-c'], '/reserved-memory')
                for prop in ('#address-cells', '#size-cells'):
                    edit(['-t', 'x'], '/reserved-memory', prop, '2')
                edit([], '/reserved-memory', 'ranges')
            elif (reserved.props.get('#address-cells') != struct.pack('>I', 2)
                  or reserved.props.get('#size-cells') != struct.pack('>I', 2)
                  or reserved.props.get('ranges') != b''):
                raise ValueError('expected identity-mapped Linux reserved-memory with 64-bit cells')
            for name, reg in optee_reserved.items():
                start, size = struct.unpack('>QQ', reg)
                for existing in reserved.children.values() if reserved else ():
                    for base, length in struct.iter_unpack('>QQ', existing.props.get('reg', b'')):
                        if start < base + length and base < start + size:
                            raise ValueError(f'{name} overlaps Linux reservation {existing.name}')
                path = f'/reserved-memory/{name}'
                edit(['-c'], path)
                edit(['-t', 'x'], path, 'reg',
                     *(f'{cell:x}' for cell in struct.unpack('>IIII', reg)))
                edit([], path, 'no-map')
        if add_handle:
            edit(['-t', 'x'], mailbox_path, 'phandle', handle.hex())
        edit(['-p', '-c'], '/firmware/optee')
        edit(['-t', 's'], '/firmware/optee', 'compatible', 'linaro,optee-tz')
        edit(['-t', 's'], '/firmware/optee', 'method', 'smc')
        edit(['-t', 'x'], '/firmware/optee', 'mboxes',
             *(cell for channel in channels for cell in (handle.hex(), f'{channel:x}', '2')))
        output.hardlink_to(staged)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('opensbi_dtb', type=Path)
    parser.add_argument('linux_dtb', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        prepare(args.opensbi_dtb, args.linux_dtb, args.output)
    except (OSError, ValueError, KeyError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'ERROR: {exc}\n')


if __name__ == '__main__':
    main()
