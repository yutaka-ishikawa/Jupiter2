#!/usr/bin/env python3
"""Build a pinned K3 reference FSBL/U-Boot pair and package ESOS on the host."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
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


def configure(text):
    # Remove active settings and both standard and vendor-style commented forms.
    lines = [line for line in text.splitlines()
             if not any(line.lstrip('# ').split('=', 1)[0].split(' ', 1)[0] == key
                        for key in SETTINGS)]
    for key, value in SETTINGS.items():
        lines.append(f'# {key} is not set' if value is None else f'{key}={value}')
    return '\n'.join(lines) + '\n'


def verify_config(path):
    config = dict(line.split('=', 1) for line in path.read_text().splitlines()
                  if line.startswith('CONFIG_') and '=' in line)
    expected = {**SETTINGS, 'CONFIG_RISCV_SMODE': 'y',
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


def build(args):
    if os.path.lexists(args.output):
        raise ValueError('output exists; use a new directory (failed builds are retained)')
    args.opensbi_bin = args.opensbi_bin.resolve(strict=True)
    args.esos_itb = args.esos_itb.resolve(strict=True)
    data = args.opensbi_bin.read_bytes()
    if not data or data.startswith((b'\x7fELF', b'\xd0\x0d\xfe\xed')):
        raise ValueError('--opensbi-bin must be a nonempty raw BIN')
    if len(data) > args.opensbi_reserve_bytes:
        raise ValueError('OpenSBI BIN exceeds declared runtime reservation')
    if args.max_download_bytes > 0x20000000:
        raise ValueError('download limit exceeds pinned SPL fastboot buffer (0x20000000)')
    packager = Path(__file__).with_name('build-jupiter2-ram-boot-image.py')
    spec = importlib.util.spec_from_file_location('jupiter2_fit', packager)
    fit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fit)
    root, _, _ = fit.read_fit(args.esos_itb)
    configs = root.children['configurations'].children
    if args.esos_configuration not in configs:
        raise ValueError('selected ESOS configuration is missing')
    names = fit.strings(configs[args.esos_configuration].props['loadables'])
    if not {'rcpu0-fw', 'rcpu1-fw', 'rcpu-data-null'}.issubset(names):
        raise ValueError('reference workflow requires both RCPU firmware images and rcpu-data-null')
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
    # Vendor config.mk writes to srctree, so each run uses its own checkout.
    shutil.copyfile(args.opensbi_bin, source / 'board/spacemit/k3/fw_dynamic.bin')
    defconfig = source / 'configs/k3_defconfig'
    defconfig.write_text(configure(defconfig.read_text()))
    # The board USB path overrides CONFIG_BOOTCOMMAND after environment init.
    # Override that path too; changing defconfig alone does not stop autoboot.
    board = source / 'board/spacemit/k3/k3.c'
    content = board.read_text()
    old = '\t\tenv_set("bootcmd", USB_BOOT_COMMAND);'
    if content.count(old) != 1:
        raise ValueError('pinned board USB bootcmd override changed unexpectedly')
    board.write_text(content.replace(old, '\t\tenv_set("bootcmd", "");\n'
                                    '\t\tenv_set("bootdelay", "-1");'))
    diff = subprocess.check_output(['git', '-C', source, 'diff', '--',
                                    'configs/k3_defconfig', 'board/spacemit/k3/k3.c'])
    (records / 'source.patch').write_bytes(diff)
    manifest = {'source_repository': args.source_repository, 'source_commit': actual,
                'variant': args.variant, 'board': 'k3-pico-itx', 'configuration': 'conf_11',
                'esos_configuration': args.esos_configuration,
                'inputs': {str(p): sha(p) for p in (args.opensbi_bin, args.esos_itb)},
                'settings': SETTINGS, 'hardware_verified': False, 'status': 'prepared'}
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
    verify_config(source / '.config')
    shutil.copyfile(source / '.config', records / 'uboot.config')
    run(make + [f'-j{args.jobs}', 'all'], cwd=source)
    verify_config(source / '.config')
    verify_fsbl(source / 'FSBL.bin')
    run([sys.executable, packager, '--fsbl', source / 'FSBL.bin',
         '--uboot-itb', source / 'u-boot.itb', '--uboot-layout', 'reference',
         '--esos-itb', args.esos_itb, '--esos-configuration', args.esos_configuration,
         '--opensbi-bin', args.opensbi_bin, '--configuration', 'conf_11',
         '--variant', args.variant, '--opensbi-reserve-bytes', args.opensbi_reserve_bytes,
         '--max-download-bytes', args.max_download_bytes, '--output', args.output / 'release'])
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
    parser.add_argument('--opensbi-reserve-bytes', type=positive, required=True)
    parser.add_argument('--max-download-bytes', type=positive, required=True)
    parser.add_argument('--jobs', type=positive, default=min(os.cpu_count() or 1, 8))
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
