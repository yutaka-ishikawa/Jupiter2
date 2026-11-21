#!/usr/bin/env python3
"""開発PCからJupiter2のRAM転送とUART用Linux起動コマンド生成を行う。

fsbl/fitは実機を操作する運用スクリプト。linuxはU-Boot用テキストを生成するだけ。
fastboot flash/eraseやsaveenvを使わない。Linuxのrootfsは通常どおりrwで起動する。
ホスト検査だけの回帰テストはscripts/tests/jupiter2-ram-boot/に置く。
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import uuid


def checked_release(directory):
    directory = directory.resolve(strict=True)
    manifest = json.loads((directory / 'records/manifest.json').read_text())
    if manifest.get('uboot_layout') != 'reference':
        raise ValueError('requires the reference builder release (uboot_layout=reference)')
    if manifest.get('board') != 'k3-pico-itx' or manifest.get('configuration') != 'conf_11':
        raise ValueError('this operation tool requires the Jupiter2 k3-pico-itx/conf_11 release')
    variant = manifest.get('variant')
    if variant not in ('vendor', 'keystone'):
        raise ValueError('unknown firmware variant')
    files = [directory / 'images/FSBL.bin', directory / f'images/ram-boot-{variant}.itb']
    for path in files:
        line = (directory / 'records' / (path.name + '.sha256')).read_text().strip()
        relative = path.relative_to(directory).as_posix()
        match = re.fullmatch(r'([0-9a-fA-F]{64})\s+\*?' + re.escape(relative), line)
        if not match or hashlib.sha256(path.read_bytes()).hexdigest() != match[1].lower():
            raise ValueError(f'checksum mismatch: {relative}')
    return directory, files


def linux_commands(kernel, initrd, dtb, root_partuuid, boot_partition):
    for path in (kernel, initrd, dtb):
        if (not re.fullmatch(r'/[A-Za-z0-9_./-]+', path)
                or any(p in ('', '.', '..') for p in path[1:].split('/'))):
            raise ValueError('Linux paths must be absolute paths without spaces or ..')
    root_partuuid = str(uuid.UUID(root_partuuid))
    if not re.fullmatch(r'[1-9][0-9]*', boot_partition):
        raise ValueError('boot partition must be a positive partition number')
    dtpath = Path(dtb)
    return f'''# 目的: 既存UFSからLinuxを一時起動する。UARTのU-Bootへ全文を貼り付ける。
# 開発PCのBashで実行しない。env_k3.txtや保存済みenvは変更しない。
# 各load成功時だけ次へ進む。Linux rootfsは通常のrwで起動する。
setenv kernel_addr_r 0x140000000
setenv ramdisk_addr 0x130000000
setenv fdt_addr_r 0x138000000
setenv knl_name {kernel[1:]}
setenv ramdisk_name {initrd[1:]}
setenv dtb_dir {dtpath.parent.as_posix().lstrip('/')}
setenv fdtfile {dtpath.name}
if load scsi 0:{boot_partition} ${{kernel_addr_r}} /${{knl_name}}; then
    if load scsi 0:{boot_partition} ${{ramdisk_addr}} /${{ramdisk_name}}; then
        setenv initrd_size ${{filesize}}
        if load scsi 0:{boot_partition} ${{fdt_addr_r}} /${{dtb_dir}}/${{fdtfile}}; then
            printenv kernel_addr_r ramdisk_addr initrd_size fdt_addr_r fdtfile
            setenv bootargs console=ttyS0,115200 earlycon=sbi root=PARTUUID={root_partuuid} rootwait rw loglevel=8
            booti ${{kernel_addr_r}} ${{ramdisk_addr}}:${{initrd_size}} ${{fdt_addr_r}}
        else
            echo RAMBOOT_DTB_LOAD_FAILED
        fi
    else
        echo RAMBOOT_INITRD_LOAD_FAILED
    fi
else
    echo RAMBOOT_KERNEL_LOAD_FAILED
fi
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('fsbl', 'fit', 'linux'), required=True)
    default_release = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == 'tools' else None
    parser.add_argument('--release', type=Path, default=default_release,
                        help='reference build output/release; bundled tools default to their release')
    parser.add_argument('--serial', help='SPL fastboot serial (required for phase fit)')
    parser.add_argument('--fastboot', default='fastboot')
    parser.add_argument('--sudo', action='store_true', help='run fastboot through sudo on the PC')
    parser.add_argument('--dry-run', action='store_true', help='verify images and print planned commands; no USB access')
    parser.add_argument('--kernel', help='bootfs path, e.g. /Image-6.18.3-keystone')
    parser.add_argument('--initrd', help='bootfs path, e.g. /initrd.img-6.18.3')
    parser.add_argument('--dtb', help='bootfs path, e.g. /spacemit/6.18.3-generic/k3-pico-itx.dtb')
    parser.add_argument('--root-partuuid', help='actual rootfs GPT partition UUID, without PARTUUID=')
    parser.add_argument('--boot-partition', default='2')
    parser.add_argument('--output', type=Path, help='write UART command text here (phase linux only)')
    args = parser.parse_args()
    try:
        if args.phase == 'linux':
            if not all((args.kernel, args.initrd, args.dtb, args.root_partuuid)):
                raise ValueError('phase linux requires --kernel/--initrd/--dtb/--root-partuuid')
            commands = linux_commands(args.kernel, args.initrd, args.dtb,
                                      args.root_partuuid, args.boot_partition)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(commands)
                print(f'UART U-Boot commands: {args.output}')
                print('Inspect this file, then paste its full contents into the UART U-Boot prompt.')
            else:
                print(commands, end='')
            return 0
        if args.output:
            raise ValueError('--output is for phase linux only')
        if args.release is None:
            raise ValueError('--release is required when running from the repository')
        if args.phase == 'fit' and not args.serial:
            raise ValueError('phase fit requires the serial reported by SPL fastboot devices')
        release, files = checked_release(args.release)
        if args.dry_run:
            prefix = (['sudo'] if args.sudo else []) + [args.fastboot]
            print('DRY RUN: checksums verified; no USB access and no logs created.')
            print(shlex.join(prefix + ['devices']))
            if args.phase == 'fsbl':
                print('# Requires exactly one ROM fastboot device before executing these commands.')
                print(shlex.join(prefix + ['stage', str(files[0])]))
                print(shlex.join(prefix + ['continue']))
            else:
                prefix += ['-s', args.serial]
                print(shlex.join(prefix + ['getvar', 'max-download-size']))
                print('# Transfer only if the reported SPL limit is at least the FIT size.')
                print(shlex.join(prefix + ['stage', str(files[1])]))
                print(shlex.join(prefix + ['continue']))
            return 0
        executable = shutil.which(args.fastboot)
        if not executable:
            raise ValueError('fastboot not found; install fastboot on the development PC')
        prefix = (['sudo'] if args.sudo else []) + [executable]
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        logs = release / 'logs'
        logs.mkdir(exist_ok=True)
        logfile = logs / f'{stamp}-{args.phase}-fastboot.log'
        print(f'PC fastboot log: {logfile}', flush=True)

        def run(arguments, timeout=15):
            command = prefix + arguments
            with logfile.open('a') as log:
                log.write('$ ' + shlex.join(command) + '\n')
            try:
                result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                output = exc.output or b''
                if isinstance(output, bytes):
                    output = output.decode(errors='replace')
                with logfile.open('a') as log:
                    log.write(output + '\nERROR: fastboot timed out\n')
                raise ValueError('fastboot timed out; inspect UART and USB enumeration') from exc
            with logfile.open('a') as log:
                log.write(result.stdout)
            print(result.stdout, end='', flush=True)
            if result.returncode:
                raise ValueError('fastboot failed; next stage was not executed')
            return result.stdout

        devices = []
        for line in run(['devices']).splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[1] == 'fastboot':
                devices.append(fields[0])
        if args.phase == 'fsbl':
            if len(devices) != 1:
                raise ValueError('phase fsbl requires exactly one ROM fastboot device')
            run(['stage', str(files[0])], timeout=120)
            run(['continue'])
            print('Check DDR completion on UART and SPL USB re-enumeration; then run phase fit.')
        else:
            if args.serial not in devices:
                raise ValueError('specified SPL serial is not currently enumerated')
            output = run(['-s', args.serial, 'getvar', 'max-download-size'])
            match = re.search(r'max-download-size:\s*(0x[0-9a-fA-F]+|[0-9]+)', output)
            if not match or files[1].stat().st_size > int(
                    match[1], 16 if match[1].lower().startswith('0x') else 10):
                raise ValueError('SPL download limit is missing or smaller than the FIT; not staged')
            run(['-s', args.serial, 'stage', str(files[1])], timeout=120)
            run(['-s', args.serial, 'continue'])
            print('Observe ESOS/OpenSBI/U-Boot on UART. No automatic extra continue is sent.')
        return 0
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
