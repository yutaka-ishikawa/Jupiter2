#!/usr/bin/env python3
"""Build a pinned K3 reference FSBL/U-Boot pair and package ESOS on the host."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zlib

COMMIT = '4c294a06c14e46e9c9cc934373c3e63919703017'
REPOSITORY = 'https://github.com/ganboing/u-boot-k3.git'
SETTINGS = {
    'CONFIG_BOOTCOMMAND': '""',
    'CONFIG_BOOTDELAY': '-1',
    'CONFIG_DDR_TRAINING_SAVE_RESTORE': None,
    'CONFIG_DDR_TRAINING_UPDATE_FSBL': None,
    'CONFIG_AUTOBOOT_KEYED': None,
    'CONFIG_ENV_IS_NOWHERE': 'y',
    'CONFIG_ENV_IS_IN_MTD': None,
    'CONFIG_ENV_IS_IN_MMC': None,
    'CONFIG_ENV_IS_IN_UFS': None,
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_runtime_tools(release):
    """同じreleaseへPC操作用テキストだけを同梱する。実機操作は行わない。"""
    scripts = Path(__file__).resolve().parent
    tools = release / 'tools'
    tools.mkdir(exist_ok=True)
    shutil.copyfile(scripts / 'run-jupiter2-ram-boot.py', tools / 'ram-boot.py')
    shutil.copyfile(scripts / 'jupiter2-ram-boot-tools/README.md', release / 'README-RAM-BOOT.md')
    paths = [tools / 'ram-boot.py', release / 'README-RAM-BOOT.md']
    hashes = {p.relative_to(release).as_posix(): sha(p) for p in paths}
    (release / 'records/host-tools.sha256').write_text(
        ''.join(f'{digest}  {name}\n' for name, digest in hashes.items()))
    return hashes


def elf_load_map(data):
    """Inspect the actual RISC-V executable consumed by the remoteproc loader."""
    if len(data) < 64 or data[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('RCPU firmware must be little-endian ELF64')
    header = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)
    kind, machine, version, entry, phoff = header[:5]
    ehsize, phsize, count = header[7:10]
    if (kind != 2 or machine != 243 or version != 1 or ehsize != 64
            or phsize != 56 or not 0 < count <= 1024
            or phoff < 64 or phoff + phsize * count > len(data)):
        raise ValueError('invalid/unsupported RISC-V ELF executable headers')
    segments = []
    for index in range(count):
        values = struct.unpack_from('<IIQQQQQQ', data, phoff + phsize * index)
        kind, flags, offset, virtual, physical, filesz, memsz, align = values
        if kind != 1:
            continue
        if (filesz > memsz or offset + filesz > len(data)
                or physical + memsz > 1 << 64 or virtual + memsz > 1 << 64):
            raise ValueError('invalid RCPU ELF LOAD extent')
        segments.append({'virtual': virtual, 'physical': physical,
                         'file_bytes': filesz, 'memory_bytes': memsz,
                         'flags': flags, 'alignment': align})
    # K3 remoteproc loads p_paddr, but starts the literal DT fw_boot_entry.
    # Do not silently treat a translated virtual entry as a physical address.
    if entry % 2 or not any(s['flags'] & 1 and s['virtual'] == s['physical']
                           and s['physical'] <= entry < s['physical'] + s['file_bytes']
                           for s in segments):
        raise ValueError('RCPU ELF entry is not in an identity-mapped executable LOAD')
    return {'entry': entry, 'entry_hex': hex(entry), 'segments': segments,
            'elf_bytes': len(data), 'elf_sha256': hashlib.sha256(data).hexdigest()}


def set_rcpu_entries(dts, firmwares):
    for core, info in enumerate(firmwares):
        pattern = (r'(\brcpu@' + str(core) + r'\s*\{[^{}]*?'
                   r'\bfw_boot_entry\s*=\s*)<([^>]+)>')
        match = re.search(pattern, dts)
        if not match or len(re.findall(pattern, dts)) != 1:
            raise ValueError(f'expected one fixed-source rcpu@{core}/fw_boot_entry')
        old = re.findall(r'0x[0-9a-fA-F]+|\d+', match[2])
        if len(old) != 2:
            raise ValueError('expected two-cell RCPU boot entry')
        info['source_dt_entry'] = (int(old[0], 0) << 32) | int(old[1], 0)
        info['source_dt_entry_hex'] = hex(info['source_dt_entry'])
        entry = info['entry']
        dts = re.sub(pattern, lambda m: m[1] + f'<0x{entry >> 32:x} 0x{entry & 0xffffffff:x}>',
                     dts, count=1)
    return dts


def verify_rcpu_dtb(fit, path, firmwares):
    root, _ = fit.parse_fdt(path.read_bytes())

    def find(node, name):
        result = [node] if node.name == name else []
        for child in node.children.values():
            result.extend(find(child, name))
        return result

    for core, info in enumerate(firmwares):
        nodes = find(root, f'rcpu@{core}')
        if len(nodes) != 1 or fit.number(nodes[0].props['fw_boot_entry']) != info['entry']:
            raise ValueError(f'compiled SPL DT boot entry differs from rcpu{core} ELF')


def fit_payload(fit, node, blob, total):
    payload = fit.image_data(node, blob, total)
    compression = fit.string(node, 'compression')
    if compression == 'none':
        return payload
    if compression != 'lzo' or not shutil.which('lzop'):
        raise ValueError('ESOS inspection requires none/LZO compression and lzop for LZO')
    return subprocess.run(['lzop', '-d', '-c'], input=payload,
                          capture_output=True, check=True).stdout


def enabled_nodes(fit, node):
    if 'status' in node.props and fit.string(node, 'status') not in ('okay', 'ok'):
        return
    yield node
    for child in node.children.values():
        yield from enabled_nodes(fit, child)


def rpmi_contract(fit, trees):
    candidates = []
    for core, tree in enumerate(trees):
        nodes = list(enabled_nodes(fit, tree))
        for node in nodes:
            if ('compatible' not in node.props or 'spacemit,k3-os0-rpmi'
                    not in fit.strings(node.props['compatible'])):
                continue
            values = {k: fit.number(node.props[k]) for k in
                      ('shmem-base', 'shmem-size', 'slot-size',
                       'a2p-queue-size', 'p2a-queue-size')}
            queue = values['a2p-queue-size']
            slot = values['slot-size']
            if (not queue or queue != values['p2a-queue-size'] or not slot
                    or queue % slot or values['shmem-size'] < queue * 4):
                raise ValueError('unsupported ESOS RPMI four-queue layout')
            cells = node.props['mboxes']
            if len(cells) != 8 or int.from_bytes(cells[4:], 'big') != 0:
                raise ValueError('expected ESOS RPMI mailbox channel zero')
            phandle = int.from_bytes(cells[:4], 'big')
            providers = [n for n in nodes if 'phandle' in n.props
                         and fit.number(n.props['phandle']) == phandle]
            if (len(providers) != 1 or len(providers[0].props['reg']) != 8
                    or fit.number(providers[0].props['#mbox-cells']) != 1):
                raise ValueError('unsupported ESOS RPMI mailbox provider')
            doorbell = int.from_bytes(providers[0].props['reg'][:4], 'big')
            if (doorbell != 0xcac90c00 or 'compatible' not in providers[0].props
                    or 'spacemit,k3-mailbox3' not in fit.strings(providers[0].props['compatible'])):
                raise ValueError('unsupported Pico RPMI doorbell provider')
            if values['shmem-base'] + queue * 4 > 1 << 64:
                raise ValueError('RPMI shared-memory range overflow')
            candidates.append({**values, 'active_core': core, 'doorbell_base': doorbell,
                               'shmem_base_hex': hex(values['shmem-base'])})
    if len(candidates) != 1:
        raise ValueError('expected exactly one enabled RPMI server in selected ESOS board DTs')
    return candidates[0]


def rpmi_reg_cells(contract):
    result = []
    for index in range(4):
        address = contract['shmem-base'] + index * contract['a2p-queue-size']
        result += [address >> 32, address & 0xffffffff, 0, contract['a2p-queue-size']]
    # Preserve the existing AP doorbell register extent, not the ESOS controller extent.
    return result + [0, contract['doorbell_base'], 0, 0x100]


def rpmi_board_override(contract):
    cells = rpmi_reg_cells(contract)
    rows = ['<' + ' '.join(f'0x{v:x}' for v in cells[i:i + 4]) + '>'
            for i in range(0, len(cells), 4)]
    return ('\n/* Match the enabled server in the selected ESOS board DT. */\n'
            '&rpmi_shmem_mbox {\n\treg = ' + ',\n\t      '.join(rows) + ';\n'
            f'\triscv,slot-size = <0x{contract["slot-size"]:x}>;\n}};\n')


def verify_rpmi_dtb(fit, data, contract):
    root, _ = fit.parse_fdt(data)
    nodes = [n for n in enabled_nodes(fit, root) if 'compatible' in n.props
             and 'riscv,rpmi-shmem-mbox' in fit.strings(n.props['compatible'])]
    expected = b''.join(v.to_bytes(4, 'big') for v in rpmi_reg_cells(contract))
    names = ['a2p-req', 'p2a-ack', 'p2a-req', 'a2p-ack', 'db-reg']
    if (len(nodes) != 1 or nodes[0].props['reg'] != expected
            or fit.strings(nodes[0].props['reg-names']) != names
            or fit.number(nodes[0].props['riscv,slot-size']) != contract['slot-size']):
        raise ValueError('U-Boot/OpenSBI DT RPMI transport differs from enabled ESOS server')


def configure(text, settings=SETTINGS):
    # Remove active settings and both standard and vendor-style commented forms.
    lines = [line for line in text.splitlines()
             if not any(line.lstrip('# ').split('=', 1)[0].split(' ', 1)[0] == key
                        for key in settings)]
    for key, value in settings.items():
        lines.append(f'# {key} is not set' if value is None else f'{key}={value}')
    return '\n'.join(lines) + '\n'


def verify_config(path, settings=SETTINGS):
    config = config_values(path)
    expected = {**settings, 'CONFIG_RISCV_SMODE': 'y',
                'CONFIG_SPL_LOAD_FIT': 'y', 'CONFIG_SPL_OPENSBI': 'y',
                'CONFIG_SPL_REMOTEPROC_K3_PROC': 'y', 'CONFIG_SPL_LZO': 'y',
                'CONFIG_SPL_FIT_IMAGE_POST_PROCESS': 'y',
                'CONFIG_SPL_OPENSBI_LOAD_ADDR': '0x100000000',
                'CONFIG_SPL_LOAD_FIT_ADDRESS': '0x140000000',
                'CONFIG_FASTBOOT_BUF_ADDR': '0x140000000',
                'CONFIG_FASTBOOT_BUF_SIZE': '0x20000000'}
    for key, value in expected.items():
        if (value is None and config.get(key, 'n') != 'n') or (
                value is not None and config.get(key) != value):
            raise ValueError(f'generated .config mismatch: {key}, expected {value}')


def verify_fsbl(path):
    data = path.read_bytes()
    if not 0x1120 <= len(data) <= 0x74000:
        raise ValueError('FSBL wrapped size outside expected ROM envelope (max 0x74000)')
    # fsbl.json: ROTPK 256 bytes; SPL header at 0xfe0, payload at 0x1000.
    for offset in (0x100, 0xfe0):
        header = data[offset:offset + 24]
        if header[:8] != b'AIHD\x01\x00\x00\x00':
            raise ValueError('unexpected FSBL AIHD/version/secure flag')
        crc, = struct.unpack_from('<I', data, offset + 24)
        if zlib.crc32(header) != crc:
            raise ValueError('FSBL AIHD header CRC mismatch')
    size, = struct.unpack_from('<Q', data, 0xfe8)
    crc, = struct.unpack_from('<I', data, 0xffc)
    if not size or 0x1000 + size + 256 != len(data):
        raise ValueError('FSBL SPL payload extent/signature length mismatch')
    if zlib.crc32(data[0x1000:0x1000 + size]) != crc:
        raise ValueError('FSBL SPL payload CRC mismatch')


def config_values(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines()
                if line.startswith('CONFIG_') and '=' in line)


def automatic_reservation(args, fit, dtb, records):
    """Mirror generic OpenSBI's fw_base.S and platform.c size calculation."""
    tree, _ = fit.parse_fdt(dtb)
    prefix = args.cross_compile
    elf = args.opensbi_elf.resolve(strict=True)
    symbols = subprocess.check_output([prefix + 'nm', '--defined-only', elf], text=True)
    addresses = {fields[-1]: int(fields[0], 16) for line in symbols.splitlines()
                 if len(fields := line.split()) == 3 and fields[-1] in
                 ('_fw_start', '_fw_end', 'fw_fdt_bin')}
    if 'fw_fdt_bin' in addresses:
        raise ValueError('automatic reservation requires OpenSBI without an embedded DTB')
    # Confirm that the ELF describes the exact raw binary being packaged.
    rebuilt = records / 'opensbi-from-elf.bin'
    subprocess.run([prefix + 'objcopy', '-S', '-O', 'binary', elf, rebuilt], check=True)
    if sha(rebuilt) != sha(args.opensbi_bin):
        raise ValueError('OpenSBI ELF and BIN do not match')
    rebuilt.unlink()

    cpus = tree.children['cpus'].children.values()
    hart_ids = [fit.number(node.props['reg']) for node in cpus
                if node.props.get('device_type') == b'cpu\0' and
                node.props.get('status', b'okay\0') in (b'okay\0', b'ok\0')]
    if not hart_ids or len(set(hart_ids)) != len(hart_ids) or max(hart_ids) >= 128:
        raise ValueError('unsupported OpenSBI hart list in the generated DTB')
    hart_count = len(hart_ids)
    chosen = tree.children.get('chosen')
    configs = [node for node in chosen.children.values()
               if b'opensbi,config' in node.props.get('compatible', b'').split(b'\0')] if chosen else []
    if len(configs) > 1:
        raise ValueError('multiple opensbi,config nodes in the generated DTB')
    heap = configs[0].props.get('heap-size') if configs else None
    if heap is not None and len(heap) != 4:
        raise ValueError('OpenSBI heap-size must be a single DTB cell')

    # Compile constants from the bundled OpenSBI headers for the RV64 ABI.
    headers = Path(__file__).resolve().parent.parent / 'opensbi/include'
    probe = records / 'opensbi-runtime-layout.o'
    subprocess.run([prefix + 'gcc', '-ffreestanding', '-march=rv64imac', '-mabi=lp64',
                    '-I', headers, '-x', 'c', '-c', '-o', probe, '-'],
                   input=f"""#include <sbi/sbi_platform.h>
#include <sbi/sbi_heap.h>
#include <sbi/sbi_tlb.h>
#include <sbi/sbi_scratch.h>
char stack_bytes[SBI_PLATFORM_DEFAULT_HART_STACK_SIZE];
char default_heap_bytes[SBI_PLATFORM_DEFAULT_HEAP_SIZE({hart_count})
                        + SBI_TLB_INFO_SIZE * {hart_count} * {hart_count}];
char heap_align_bytes[HEAP_BASE_ALIGN];
char scratch_bytes[SBI_SCRATCH_SIZE];
""", text=True, check=True)
    sizes = subprocess.check_output([prefix + 'nm', '-S', '--defined-only', probe], text=True)
    sizes = {parts[3]: int(parts[1], 16) for line in sizes.splitlines()
             if len(parts := line.split()) == 4}
    probe.unlink()
    align = sizes['heap_align_bytes']
    heap_bytes = fit.number(heap) if heap is not None else sizes['default_heap_bytes']
    heap_bytes = (heap_bytes + align - 1) // align * align
    static_bytes = addresses['_fw_end'] - addresses['_fw_start']
    if static_bytes < args.opensbi_bin.stat().st_size:
        raise ValueError('OpenSBI ELF static span is smaller than the BIN')
    runtime_bytes = static_bytes + max(hart_count * sizes['stack_bytes'] + heap_bytes,
                                      2 * sizes['scratch_bytes'])
    # The K3 FIT loads OpenSBI at 4 GiB. Cover the runtime span and any
    # naturally aligned PMP rounding of its read-only and writable regions.
    if not 0 < runtime_bytes <= 0x100000000:
        raise ValueError('OpenSBI runtime span exceeds the supported K3 load window')
    reserve_bytes = max(4096, 1 << (runtime_bytes - 1).bit_length())
    return {'source': 'OpenSBI ELF, bundled generic platform headers and generated U-Boot FIT DTB',
            'elf_sha256': sha(elf), 'dtb_sha256': hashlib.sha256(dtb).hexdigest(),
            'static_bytes': static_bytes, 'hart_count': hart_count,
            'stack_bytes_per_hart': sizes['stack_bytes'], 'heap_bytes': heap_bytes,
            'runtime_bytes': runtime_bytes, 'reserve_bytes': reserve_bytes}


def fastboot_download_limit(path):
    pattern = (r'^[ \t]*(?:\(bootloader\)[ \t]*)?max-download-size:[ \t]*'
               r'(0[xX][0-9a-fA-F]+|[0-9]+)[ \t]*$')
    values = {int(value, 16 if value.lower().startswith('0x') else 10)
              for value in re.findall(pattern, path.read_text(), re.MULTILINE)}
    if len(values) != 1 or min(values) <= 0:
        raise ValueError('expected one unambiguous max-download-size in the Fastboot log')
    return values.pop()


def build(args):
    if os.path.lexists(args.output):
        raise ValueError('output exists; use a new directory (failed builds are retained)')
    args.opensbi_bin = args.opensbi_bin.resolve(strict=True)
    args.esos_itb = args.esos_itb.resolve(strict=True)
    data = args.opensbi_bin.read_bytes()
    if not data or data.startswith((b'\x7fELF', b'\xd0\x0d\xfe\xed')):
        raise ValueError('--opensbi-bin must be a nonempty raw BIN')
    if args.opensbi_reserve_bytes is not None and len(data) > args.opensbi_reserve_bytes:
        raise ValueError('OpenSBI BIN exceeds declared runtime reservation')
    if args.fastboot_log:
        args.fastboot_log = args.fastboot_log.resolve(strict=True)
        args.max_download_bytes = fastboot_download_limit(args.fastboot_log)
    if args.max_download_bytes is not None and args.max_download_bytes > 0x20000000:
        raise ValueError('download limit exceeds pinned SPL fastboot buffer (0x20000000)')
    packager = Path(__file__).with_name('build-jupiter2-ram-boot-image.py')
    spec = importlib.util.spec_from_file_location('jupiter2_fit', packager)
    fit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fit)
    if args.optee_bin and not (args.opensbi_dtb or args.opensbi_overlay):
        raise ValueError('--optee-bin requires --opensbi-overlay or --opensbi-dtb for the actual board')
    if args.opensbi_overlay:
        args.opensbi_overlay = args.opensbi_overlay.resolve(strict=True)
        if not args.opensbi_overlay.is_file():
            raise ValueError('--opensbi-overlay must point to a compiled DT overlay')
        fit.parse_fdt(args.opensbi_overlay.read_bytes())
        if not args.prepare_only and not shutil.which('fdtoverlay'):
            raise ValueError('install device-tree-compiler for fdtoverlay')
    if args.opensbi_dtb:
        args.opensbi_dtb = args.opensbi_dtb.resolve(strict=True)
        if args.optee_bin:
            fit.validate_optee_dtb(args.opensbi_dtb.read_bytes())
    root, esos_blob, esos_total = fit.read_fit(args.esos_itb)
    configs = root.children['configurations'].children
    if args.esos_configuration not in configs:
        raise ValueError('selected ESOS configuration is missing')
    names = fit.strings(configs[args.esos_configuration].props['loadables'])
    if not {'rcpu0-fw', 'rcpu1-fw', 'rcpu-data-null'}.issubset(names):
        raise ValueError('reference workflow requires both RCPU firmware images and rcpu-data-null')
    firmwares = []
    for core in range(2):
        name = f'rcpu{core}-fw'
        node = root.children['images'].children[name]
        payload = fit_payload(fit, node, esos_blob, esos_total)
        info = elf_load_map(payload)
        info['name'] = name
        firmwares.append(info)
    board_trees = []
    board_hashes = {}
    for core in range(2):
        name = f'rcpu{core}-dtb-pico-itx'
        if name not in names:
            raise ValueError('selected ESOS configuration lacks ' + name)
        payload = fit_payload(fit, root.children['images'].children[name], esos_blob, esos_total)
        board_trees.append(fit.parse_fdt(payload)[0])
        board_hashes[name] = hashlib.sha256(payload).hexdigest()
    contract = rpmi_contract(fit, board_trees)
    contract['board_dtb_sha256'] = board_hashes
    args.output.mkdir(parents=True)
    source, records = args.output / 'source', args.output / 'records'
    records.mkdir()

    def run(command, cwd=None):
        with (records / 'commands.jsonl').open('a') as file:
            file.write(json.dumps({'argv': list(map(str, command)), 'cwd': str(cwd)}) + '\n')
        with (records / 'build.log').open('a') as log:
            subprocess.run(list(map(str, command)), cwd=cwd, stdout=log,
                           stderr=subprocess.STDOUT, check=True)

    run(['git', 'init', source])
    run(['git', '-C', source, 'fetch', '--depth=1', args.source_repository, COMMIT])
    run(['git', '-C', source, 'checkout', '--detach', 'FETCH_HEAD'])
    actual = subprocess.check_output(['git', '-C', source, 'rev-parse', 'HEAD'], text=True).strip()
    if actual != COMMIT:
        raise ValueError('reference source commit mismatch')
    diagnostic_patch = Path(__file__).resolve().parents[1] / 'patches/jupiter2-reference-ram-boot-diagnostics.patch'
    run(['git', 'apply', '--check', diagnostic_patch], cwd=source)
    run(['git', 'apply', diagnostic_patch], cwd=source)
    settings = dict(SETTINGS)
    measurement_patches = []
    if args.spl_measurement_log:
        settings['CONFIG_SPL_JUPITER2_MEASURED_BOOT'] = 'y'
        patches = diagnostic_patch.parent
        for name in ('jupiter2-spl-measured-boot-log.patch',
                     'jupiter2-spl-measured-boot-fit.patch',
                     'jupiter2-spl-measured-boot-handoff.patch',
                     'jupiter2-spl-measured-boot-payloads.patch',
                     'jupiter2-spl-measured-boot-dtb.patch'):
            patch = patches / name
            run(['git', 'apply', '--check', patch], cwd=source)
            run(['git', 'apply', '--intent-to-add', patch], cwd=source)
            measurement_patches.append({'file': name, 'sha256': sha(patch)})
    spl_dts = source / 'arch/riscv/dts/k3_spl.dts'
    spl_dts.write_text(set_rcpu_entries(spl_dts.read_text(), firmwares))
    (records / 'rcpu-elf.json').write_text(json.dumps(firmwares, indent=2) + '\n')
    board_dts = source / 'arch/riscv/dts/k3-pico-itx.dts'
    board_dts.write_text(board_dts.read_text() + rpmi_board_override(contract))
    (records / 'rpmi-contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    # Vendor config.mk writes to srctree, so each run uses its own checkout.
    shutil.copyfile(args.opensbi_bin, source / 'board/spacemit/k3/fw_dynamic.bin')
    defconfig = source / 'configs/k3_defconfig'
    defconfig.write_text(configure(defconfig.read_text(), settings))
    # The board USB path overrides CONFIG_BOOTCOMMAND after environment init.
    # Override that path too; changing defconfig alone does not stop autoboot.
    board = source / 'board/spacemit/k3/k3.c'
    content = board.read_text()
    old = '\t\tenv_set("bootcmd", USB_BOOT_COMMAND);'
    if content.count(old) != 1:
        raise ValueError('pinned board USB bootcmd override changed unexpectedly')
    board.write_text(content.replace(old, '\t\tenv_set("bootcmd", "");\n'
                                    '\t\tenv_set("bootdelay", "-1");'))
    diff = subprocess.check_output(['git', '-C', source, 'diff', '--'])
    (records / 'source.patch').write_bytes(diff)
    manifest = {'source_repository': args.source_repository, 'source_commit': actual,
                'variant': args.variant, 'board': 'k3-pico-itx', 'configuration': 'conf_11',
                'esos_configuration': args.esos_configuration,
                'inputs': {str(p): sha(p) for p in (args.opensbi_bin, args.esos_itb)},
                'settings': settings, 'diagnostic_patch_sha256': sha(diagnostic_patch),
                'spl_measurement_patches': measurement_patches,
                'rcpu_firmwares': firmwares,
                'rpmi_contract': contract,
                'hardware_verified': False, 'status': 'prepared'}
    (records / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if args.prepare_only:
        print(f'Prepared pinned source and patch: {args.output}; no images built.')
        return
    compiler = shutil.which(args.cross_compile + 'gcc')
    if not compiler:
        raise ValueError('cross GCC not found; install K3 toolchain and set --cross-compile')
    for tool in ('make', 'bison', 'flex', 'swig', 'openssl', 'mkimage', 'dumpimage', 'dtc', 'lzop'):
        if not shutil.which(tool):
            raise ValueError(f'missing host tool: {tool}')
    manifest['compiler'] = subprocess.check_output([compiler, '--version'], text=True)
    make = ['make', f'CROSS_COMPILE={args.cross_compile}']
    run(make + ['k3_defconfig'], cwd=source)
    verify_config(source / '.config', settings)
    shutil.copyfile(source / '.config', records / 'uboot.config')
    run(make + [f'-j{args.jobs}', 'all'], cwd=source)
    verify_config(source / '.config', settings)
    verify_fsbl(source / 'FSBL.bin')
    compiled_dtb = source / 'spl/u-boot-spl.dtb'
    verify_rcpu_dtb(fit, compiled_dtb, firmwares)
    if compiled_dtb.read_bytes() not in (source / 'FSBL.bin').read_bytes():
        raise ValueError('verified SPL DTB not found in wrapped FSBL')
    shutil.copyfile(compiled_dtb, records / 'spl.dtb')
    manifest['spl_dtb_sha256'] = sha(compiled_dtb)
    uroot, ublob, utotal = fit.read_fit(source / 'u-boot.itb')
    selected = uroot.children['configurations'].children['conf_11']
    dtname = fit.string(selected, 'fdt')
    dtdata = fit.image_data(uroot.children['images'].children[dtname], ublob, utotal)
    if args.opensbi_dtb:
        dtdata = args.opensbi_dtb.read_bytes()
    elif args.opensbi_overlay:
        base_dtb = records / 'opensbi-uboot-base.dtb'
        base_dtb.write_bytes(dtdata)
        merged_dtb = records / 'opensbi-uboot.dtb'
        run(['fdtoverlay', '-i', base_dtb, '-o', merged_dtb, args.opensbi_overlay])
        dtdata = merged_dtb.read_bytes()
        manifest['opensbi_overlay'] = {
            'path': str(args.opensbi_overlay), 'sha256': sha(args.opensbi_overlay),
        }
    verify_rpmi_dtb(fit, dtdata, contract)
    if args.optee_bin:
        fit.validate_optee_dtb(dtdata)
    (records / 'opensbi-uboot.dtb').write_bytes(dtdata)
    if args.opensbi_elf:
        reservation = automatic_reservation(args, fit, dtdata, records)
    else:
        reservation = {'source': 'explicit argument', 'reserve_bytes': args.opensbi_reserve_bytes}
    # verify_config validated the generated Kconfig used to build SPL.
    spl_limit = int(config_values(source / '.config')['CONFIG_FASTBOOT_BUF_SIZE'], 0)
    if args.max_download_bytes is not None and args.max_download_bytes > spl_limit:
        raise ValueError('requested download limit exceeds the generated SPL buffer')
    download_limit = args.max_download_bytes or spl_limit
    manifest['ram_boot_limits'] = {
        'opensbi': reservation,
        'spl_config': 'records/uboot.config:CONFIG_FASTBOOT_BUF_SIZE',
        'spl_buffer_bytes': spl_limit,
        'effective_download_bytes': download_limit,
        'download_source': 'explicit argument' if args.max_download_bytes else 'generated config',
    }
    if args.fastboot_log:
        manifest['ram_boot_limits']['download_source'] = {
            'fastboot_log': str(args.fastboot_log), 'sha256': sha(args.fastboot_log),
        }
    (records / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')

    run([sys.executable, packager, '--fsbl', source / 'FSBL.bin',
         '--uboot-itb', source / 'u-boot.itb', '--uboot-layout', 'reference',
         '--esos-itb', args.esos_itb, '--esos-configuration', args.esos_configuration,
         '--opensbi-bin', args.opensbi_bin, '--configuration', 'conf_11',
         '--variant', args.variant, '--opensbi-reserve-bytes', reservation['reserve_bytes'],
         '--max-download-bytes', download_limit, '--output', args.output / 'release']
        + (['--spl-measurement-log'] if args.spl_measurement_log else [])
        + (['--opensbi-dtb', records / 'opensbi-uboot.dtb'] if args.opensbi_dtb or args.opensbi_overlay else [])
        + (['--optee-bin', args.optee_bin] if args.optee_bin else []))
    manifest['host_tools'] = package_runtime_tools(args.output / 'release')
    manifest.update(status='packaged',
                    artifacts={p.name: sha(p) for p in (args.output / 'release/images').iterdir()})
    (records / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(args.output / 'release/images')
    print('Host build complete; DDR/ESOS/RPMI/UFS and persistent writes require hardware tests.')


def positive(value):
    number = int(value, 0)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('opensbi-bin', 'esos-itb', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-repository', default=REPOSITORY)
    parser.add_argument('--cross-compile', default=os.environ.get('CROSS_COMPILE', 'riscv64-unknown-linux-gnu-'))
    parser.add_argument('--esos-configuration', required=True)
    parser.add_argument('--variant', choices=('vendor', 'keystone'), required=True)
    reservation = parser.add_mutually_exclusive_group(required=True)
    reservation.add_argument('--opensbi-reserve-bytes', type=positive)
    reservation.add_argument('--opensbi-elf', type=Path,
                             help='matching bundled generic OpenSBI ELF for automatic sizing')
    download = parser.add_mutually_exclusive_group()
    download.add_argument('--max-download-bytes', type=positive,
                          help='override the generated SPL download limit with a lower value')
    download.add_argument('--fastboot-log', type=Path,
                          help='use max-download-size from a saved SPL Fastboot getvar log')
    parser.add_argument('--jobs', type=positive, default=min(os.cpu_count() or 1, 8))
    dtb = parser.add_mutually_exclusive_group()
    dtb.add_argument('--opensbi-dtb', type=Path, help='board DTB passed to OpenSBI')
    dtb.add_argument('--opensbi-overlay', type=Path,
                     help='board OP-TEE overlay applied to the reference U-Boot DTB')
    parser.add_argument('--optee-bin', type=Path, help='raw K3 OP-TEE Core tee.bin')
    parser.add_argument('--spl-measurement-log', action='store_true',
                        help='emit experimental OpenSBI/U-Boot measurements on UART')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    args.output = args.output.absolute()
    try:
        build(args)
    except (ValueError, KeyError, OSError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}\nInspect {args.output}/records/build.log; output retained.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
