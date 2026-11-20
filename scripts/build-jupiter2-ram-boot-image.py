#!/usr/bin/env python3
"""Package prebuilt K3 firmware into a board-specific, unsigned RAM-boot FIT.

This is a host-side packager, not a firmware compiler or fastboot installer.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib


class Node:
    def __init__(self, name):
        self.name = name
        self.props = {}
        self.children = {}


def fail(message):
    raise ValueError(message)


def strings(value):
    if not value or not value.endswith(b'\0'):
        fail('expected a nonempty FIT string list')
    return value[:-1].decode('ascii').split('\0')


def string(node, key):
    values = strings(node.props[key])
    if len(values) != 1 or not values[0]:
        fail(f'{node.name}/{key}: expected one string')
    return values[0]


def text(value):
    return value.encode('ascii') + b'\0'


def number(value):
    if len(value) not in (4, 8):
        fail('FIT integer must have one or two cells')
    return int.from_bytes(value, 'big')


def cells(value):
    if not 0 <= value < 1 << 64:
        fail('address outside 64-bit range')
    return value.to_bytes(8, 'big')


def parse_fdt(blob):
    if len(blob) < 40:
        fail('truncated FDT header')
    magic, total, off, stroff, _, version, compatible, _, strsize, size = struct.unpack_from('>10I', blob)
    if (magic != 0xd00dfeed or version < 17 or compatible > 17
            or total > len(blob) or off < 40 or stroff < 40
            or off + size > total or stroff + strsize > total):
        fail('invalid or unsupported FDT header')
    names = blob[stroff:stroff + strsize]
    end, stack, root = off + size, [], None
    while off + 4 <= end:
        token = struct.unpack_from('>I', blob, off)[0]
        off += 4
        if token == 1:
            stop = blob.find(b'\0', off, end)
            if stop < 0:
                fail('unterminated node name')
            name = blob[off:stop].decode('ascii')
            if name and not re.fullmatch(r'[A-Za-z0-9_,.+@#-]+', name):
                fail('unsupported FIT node name')
            node = Node(name)
            if stack:
                if name in stack[-1].children:
                    fail('duplicate FIT node')
                stack[-1].children[name] = node
            elif root is not None or name:
                fail('invalid FDT root')
            else:
                root = node
            stack.append(node)
            if len(stack) > 64:
                fail('FDT nesting too deep')
            off = (stop + 4) & ~3
        elif token == 2:
            if not stack:
                fail('unbalanced FDT nodes')
            stack.pop()
        elif token == 3:
            if not stack or off + 8 > end:
                fail('invalid FDT property')
            length, nameoff = struct.unpack_from('>II', blob, off)
            off += 8
            stop = names.find(b'\0', nameoff)
            if nameoff >= len(names) or stop < 0 or off + length > end:
                fail('FDT property out of bounds')
            key = names[nameoff:stop].decode('ascii')
            if not re.fullmatch(r'[A-Za-z0-9_,.+@#?-]+', key) or key in stack[-1].props:
                fail('invalid or duplicate FDT property name')
            stack[-1].props[key] = blob[off:off + length]
            off = (off + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            if stack or root is None:
                fail('incomplete FDT tree')
            return root, total
        else:
            fail('invalid FDT structure token')
    fail('missing FDT end token')


def digest(algo, data):
    if algo == 'crc32':
        return struct.pack('>I', zlib.crc32(data))
    if algo not in ('sha1', 'sha256', 'sha384', 'sha512'):
        fail(f'unsupported hash algorithm: {algo}')
    return hashlib.new(algo, data).digest()


def reject_security(node):
    if node.name.startswith(('signature', 'cipher')):
        fail('signed/encrypted FITs are unsupported; use unsigned development inputs')
    for child in node.children.values():
        reject_security(child)


def image_data(node, blob, total):
    if 'data' in node.props:
        if any(k in node.props for k in ('data-offset', 'data-position', 'data-size')):
            fail('ambiguous inline/external FIT data')
        data = node.props['data']
    else:
        size = number(node.props['data-size'])
        if ('data-position' in node.props) == ('data-offset' in node.props):
            fail('external FIT needs exactly one data position or offset')
        pos = (number(node.props['data-position']) if 'data-position' in node.props
               else ((total + 3) & ~3) + number(node.props['data-offset']))
        if pos < total or pos + size > len(blob):
            fail('external FIT data out of bounds')
        data = blob[pos:pos + size]
    if not data:
        fail(f'empty image: {node.name}')
    hashes = [n for n in node.children.values() if n.name.startswith('hash')]
    if not hashes:
        fail(f'{node.name}: input image has no hash')
    for child in hashes:
        if digest(string(child, 'algo'), data) != child.props.get('value'):
            fail(f'{node.name}: input hash mismatch')
    return data


def read_fit(path):
    blob = path.read_bytes()
    root, total = parse_fdt(blob)
    reject_security(root)
    return root, blob, total


def imported_image(source, name, blob, total):
    node = copy.deepcopy(source)
    node.name = name
    data = image_data(source, blob, total)
    if string(node, 'compression') != 'none':
        fail(f'{source.name}: only uncompressed input images are supported')
    for key in ('data-position', 'data-offset', 'data-size'):
        node.props.pop(key, None)
    node.props['data'] = data
    return node


def make_image(name, data, kind, **props):
    node = Node(name)
    node.props = {'data': data, 'type': text(kind), 'compression': text('none')}
    node.props.update(props)
    h = Node('hash-1')
    h.props = {'algo': text('sha256')}
    node.children[h.name] = h
    return node


def emit(node, directory, indent=0):
    pad = '    ' * indent
    lines = [pad + (node.name or '/') + ' {']
    for key, value in node.props.items():
        if key == 'data':
            filename = f'payload-{len(list(directory.glob("payload-*")))}.bin'
            (directory / filename).write_bytes(value)
            lines.append(f'{pad}    data = /incbin/("{filename}");')
        else:
            encoded = ' '.join(f'{b:02x}' for b in value)
            lines.append(f'{pad}    {key} = [{encoded}];')
    for child in node.children.values():
        lines.append(emit(child, directory, indent + 1))
    lines.append(pad + '};')
    return '\n'.join(lines)


def positive(value):
    n = int(value, 0)
    if n <= 0:
        raise argparse.ArgumentTypeError('must be positive (decimal or 0x...)')
    return n


def build(args):
    if os.path.lexists(args.output):
        fail('output directory already exists; choose a new directory')
    tools = {name: shutil.which(name) for name in ('mkimage', 'dumpimage', 'dtc')}
    if not all(tools.values()):
        fail('install u-boot-tools and device-tree-compiler; mkimage/dumpimage/dtc must be on PATH')
    paths = {key: getattr(args, key).resolve() for key in ('uboot_itb', 'esos_itb', 'opensbi_bin', 'fsbl')}
    inputs = {key: path.read_bytes() for key, path in paths.items()}
    if not inputs['fsbl'] or not inputs['opensbi_bin']:
        fail('FSBL and OpenSBI BIN must be nonempty')
    if inputs['opensbi_bin'].startswith((b'\x7fELF', b'\xd0\x0d\xfe\xed')):
        fail('--opensbi-bin requires a raw BIN, not ELF or ITB')
    uroot, ub, utotal = read_fit(paths['uboot_itb'])
    eroot, eb, etotal = read_fit(paths['esos_itb'])
    config = uroot.children['configurations'].children[args.configuration]
    if string(config, 'description') != args.board:
        fail('U-Boot configuration description does not match --board')
    if config.children or 'firmware' in config.props or 'kernel' in config.props:
        fail('expected a plain vendor U-Boot configuration without firmware/kernel/signatures')
    loads = strings(config.props['loadables'])
    if len(loads) != 1:
        fail('expected exactly one U-Boot loadable in input configuration')
    fdtname = string(config, 'fdt')
    images = Node('images')
    ui = uroot.children['images'].children
    uboot = imported_image(ui[loads[0]], 'uboot', ub, utotal)
    if string(uboot, 'arch') != 'riscv' or string(uboot, 'type') not in ('standalone', 'firmware'):
        fail('U-Boot loadable must be RISC-V standalone/firmware')
    if 'os' in uboot.props and string(uboot, 'os') != 'u-boot':
        fail('unexpected U-Boot OS property')
    uboot.props['os'] = text('u-boot')
    uboot.props.setdefault('entry', uboot.props['load'])
    fdt = imported_image(ui[fdtname], 'fdt', ub, utotal)
    if string(fdt, 'type') != 'flat_dt':
        fail('selected FDT image is not a flat device tree')
    parse_fdt(fdt.props['data'])
    matches = [c for c in eroot.children['configurations'].children.values()
               if string(c, 'description') == args.board]
    if len(matches) != 1:
        fail('expected exactly one matching ESOS board configuration')
    ec = matches[0]
    if ec.children or any(k in ec.props for k in ('firmware', 'kernel', 'fdt')):
        fail('unsupported ESOS configuration: expected loadables only')
    enames = strings(ec.props['loadables'])
    if not enames or len(enames) != len(set(enames)):
        fail('ESOS configuration needs nonempty distinct loadables')
    firmware = make_image('opensbi', inputs['opensbi_bin'], 'firmware',
                          description=text('OpenSBI ' + args.variant), arch=text('riscv'),
                          os=text('opensbi'), load=cells(args.opensbi_load), entry=cells(args.opensbi_load))
    for node in (firmware, uboot, fdt):
        images.children[node.name] = node
    for index, name in enumerate(enames):
        node = imported_image(eroot.children['images'].children[name], f'esos-{index}', eb, etotal)
        images.children[node.name] = node
    regions = []
    for node in images.children.values():
        if node is not fdt and 'load' not in node.props:
            fail(f'{node.name}: missing load address')
        if 'load' in node.props:
            start = number(node.props['load'])
            size = len(node.props['data'])
            if node is firmware:
                if args.opensbi_reserve_bytes < size:
                    fail('OpenSBI reserved runtime size is smaller than its BIN')
                size = args.opensbi_reserve_bytes
            if start + size > 1 << 64:
                fail('load range overflow')
            if 'entry' in node.props and not start <= number(node.props['entry']) < start + size:
                fail(f'{node.name}: entry is outside its load range')
            for other in regions:
                if start < other['end'] and other['start'] < start + size:
                    fail(f'overlapping load/runtime ranges: {node.name} and {other["name"]}')
            regions.append({'name': node.name, 'start': start, 'end': start + size})
    root = Node('')
    root.props = {'description': text('Jupiter2 RAM boot ' + args.variant), '#address-cells': struct.pack('>I', 2)}
    root.children['images'] = images
    configs = Node('configurations')
    configs.props['default'] = text(args.configuration)
    selected = Node(args.configuration)
    selected.props = {'description': text(args.board), 'firmware': text('opensbi'), 'fdt': text('fdt'),
                      'loadables': text('uboot') + b''.join(text(f'esos-{i}') for i in range(len(enames)))}
    configs.children[selected.name] = selected
    root.children[configs.name] = configs
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.jupiter2-ram-', dir=args.output.parent) as tmp:
        stage = Path(tmp)
        outimages, records = stage / 'images', stage / 'records'
        outimages.mkdir()
        records.mkdir()
        its = stage / 'ram-boot.its'
        its.write_text('/dts-v1/;\n' + emit(root, stage) + '\n')
        filename = f'ram-boot-{args.variant}.itb'
        result = subprocess.run([tools['mkimage'], '-f', its.name, str(outimages / filename)],
                                cwd=stage, text=True, capture_output=True, check=True)
        (records / 'mkimage.txt').write_text(result.stdout + result.stderr)
        output = (outimages / filename).read_bytes()
        if len(output) > args.max_download_bytes:
            fail(f'FIT size {len(output)} exceeds SPL download limit {args.max_download_bytes}')
        built, blob, total = read_fit(outimages / filename)
        for name, source in images.children.items():
            actual = image_data(built.children['images'].children[name], blob, total)
            if actual != source.props['data']:
                fail(f'output image differs from input: {name}')
        listing = subprocess.run([tools['dumpimage'], '-l', str(outimages / filename)],
                                 capture_output=True, text=True, check=True)
        (records / 'fit-list.txt').write_text(listing.stdout)
        (outimages / 'FSBL.bin').write_bytes(inputs['fsbl'])
        manifest = {'format': 1, 'variant': args.variant, 'board': args.board,
                    'configuration': args.configuration, 'hardware_verified': False,
                    'limits': {'spl_max_download_bytes': args.max_download_bytes,
                               'opensbi_reserve_bytes': args.opensbi_reserve_bytes},
                    'load_regions': regions,
                    'unchecked': ['FSBL compatibility and FSBL ROM size limit', 'S-mode U-Boot build',
                                  'ESOS startup', 'DTB placement and fixups', 'FIT transfer buffer overlap',
                                  'SM reservations and dynamic allocations', 'automatic persistent writes'],
                    'inputs': {k: {'filename': p.name, 'bytes': len(inputs[k]),
                                   'sha256': hashlib.sha256(inputs[k]).hexdigest()} for k, p in paths.items()},
                    'payloads': {k: {'bytes': len(n.props['data']),
                                     'sha256': hashlib.sha256(n.props['data']).hexdigest()}
                                 for k, n in images.children.items()},
                    'tools': {k: subprocess.run([v, '-V'],
                                                capture_output=True, text=True).stdout.strip()
                              for k, v in tools.items()}}
        for file in outimages.iterdir():
            checksum = hashlib.sha256(file.read_bytes()).hexdigest()
            (records / (file.name + '.sha256')).write_text(f'{checksum}  images/{file.name}\n')
        (records / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        # Retain a relocatable ITS and its payloads for inspection/reproduction.
        (records / 'ram-boot.its').write_bytes(its.read_bytes())
        for payload in stage.glob('payload-*'):
            shutil.move(str(payload), records / payload.name)
        its.unlink()
        os.rename(stage, args.output)
    print(args.output / 'images' / filename)
    print('Packaged and hash-checked; hardware boot and persistent-write behavior remain unverified.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('uboot-itb', 'esos-itb', 'opensbi-bin', 'fsbl', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--configuration', required=True, help='e.g. conf_11 (must match --board)')
    parser.add_argument('--board', default='k3-pico-itx')
    parser.add_argument('--variant', choices=('vendor', 'keystone'), required=True)
    parser.add_argument('--opensbi-load', type=positive, default=0x100000000)
    parser.add_argument('--opensbi-reserve-bytes', type=positive, required=True,
                        help='verified total runtime extent, including BSS/heap/scratch; not just BIN size')
    parser.add_argument('--max-download-bytes', type=positive, required=True,
                        help='verified SPL fastboot download buffer limit, NOT NOR partition size')
    args = parser.parse_args()
    args.output = args.output.absolute()
    try:
        build(args)
    except (ValueError, KeyError, OSError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr or exc.stdout or '', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
