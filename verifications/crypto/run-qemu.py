#!/usr/bin/env python3
"""Run actual system guests twice with the same identity, then without keys."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]


def run(args, name, provider):
    record = {'case': name, 'provider': provider, 'sstc': args.sstc, 'pass': False}
    log = args.logs / (name + '.log')
    record['log'] = str(log)
    log.write_text('')
    prefix = args.prefix.resolve()
    bios = prefix / ('firmware/k3/crypto-qemu-dev/fw_dynamic.bin' if provider == 'qemu-dev'
                     else 'firmware/k3/fw_dynamic.bin')
    paths = [bios, prefix / 'bin/qemu-system-riscv64', prefix / 'boot/k3/Image',
             ROOT / 'verifications/crypto/build/crypto.ke']
    try:
        firmware_data = bios.read_bytes()
        record['firmware_sha256'] = hashlib.sha256(firmware_data).hexdigest()
        if b'host=%s enclave=mtimer slice-us=10000' not in firmware_data:
            raise RuntimeError('Selected firmware lacks Sstc/SM timer coexistence: '
                               + str(bios) + ' sha256=' + record['firmware_sha256']
                               + '; run make build and make install')
        record['sha256'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        with tempfile.TemporaryDirectory(prefix='crypto-qemu-') as tmp:
            overlay = Path(tmp) / 'rootfs.qcow2'
            subprocess.run([str(prefix / 'bin/qemu-img'), 'create', '-f', 'qcow2', '-F', 'raw',
                            '-b', str(args.rootfs.resolve()), str(overlay)], check=True)
            command = ['bash', str(ROOT / 'scripts/run-k3.sh'), '--prefix', str(prefix),
                       '--crypto', provider, '--sstc', args.sstc, '--rootfs', str(overlay), '--rootfs-format', 'qcow2']
            record['command'] = command
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT)
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            captured = b''
            sent = False
            deadline = time.monotonic() + args.timeout
            try:
                with log.open('wb') as stream:
                    while time.monotonic() < deadline:
                        for key, _ in selector.select(1):
                            data = os.read(key.fd, 65536)
                            if not data:
                                raise RuntimeError('QEMU exited before completion')
                            stream.write(data)
                            stream.flush()
                            captured += data
                        if not sent and re.search(rb'(?:root@[^\r\n]*|bash-[0-9.]+)#', captured):
                            if args.all:
                                test = f'KEYSTONE_CRYPTO_EXPECT={provider} bash /mnt/host/verifications/run-all.sh'
                            else:
                                test = f'bash /mnt/host/verifications/crypto/run-guest.sh {provider}'
                            # run-guest's metadata default is relative to the shared repository.
                            setup = ('mkdir -p /proc /sys /mnt/host; mount -t proc proc /proc 2>/dev/null; '
                                     'mount -t sysfs sysfs /sys 2>/dev/null; '
                                     'mount -t 9p -o trans=virtio,version=9p2000.L hostshare /mnt/host && '
                                     + test + '; rc=$?; printf "\\nCRYPTO_CASE_EXIT=%d\\n" "$rc"\n')
                            process.stdin.write(setup.encode())
                            process.stdin.flush()
                            sent = True
                        match = re.search(rb'CRYPTO_CASE_EXIT=(\d+)\r*\n', captured)
                        if match:
                            banner = f'[SM/CRYPTO] provider={provider} '.encode()
                            minimum = 3 if provider == 'qemu-dev' else 1
                            record['guest_exit'] = int(match[1])
                            timer_banner = (b'host=sstc enclave=mtimer' if args.sstc == 'on'
                                            else b'host=sbi-mtimer enclave=mtimer')
                            host_marker = (b'PASS GUEST HOST SSTC:' if args.sstc == 'on'
                                           else b'INFO HOST TIMER: sstc=0')
                            suite_markers = [b'PASS GUEST SBI 3004: STOP/RESUME,',
                                             b'PASS GUEST SUITE SBI ', b'PASS GUEST SBI 4000: registered/',
                                             timer_banner, host_marker]
                            suite_complete = (not args.all or
                                              all(marker in captured for marker in suite_markers))
                            record['pass'] = (int(match[1]) == 0 and banner in captured and
                                              captured.count(b'PASS GUEST CRYPTO:') >= minimum and
                                              suite_complete)
                            if not record['pass']:
                                record['error'] = 'Guest failure, provider/timer mismatch or incomplete crypto/STOP suite'
                            return record
                    raise TimeoutError('Timed out waiting for ' + ('test result' if sent else 'root prompt'))
            finally:
                selector.close()
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
        record['error'] = str(exc)
    return record


def check_optee_pmp16(output, profile):
    if b'[K3-PMP] shared readback failed' in output:
        raise RuntimeError('PMP CSR readback failed')
    rows = re.findall(
        rb'\[K3-PMP\] shared CSR hart=(\d+) state=(boot-host|host|optee|enclave) '
        rb'implemented=(\d+) gran=(\d+) active=(\d+) mask=0x([0-9a-f]+)', output)
    expected_masks = {'boot-host': {0x9fff}, 'host': {0x9fff, 0xbfff},
                      'optee': {0x9fff, 0xbfff}, 'enclave': {0xffff}}
    harts = {state: set() for state in expected_masks}
    max_active = {}
    for hart, state, implemented, gran, active, mask in rows:
        hart, implemented, gran, active = map(int, (hart, implemented, gran, active))
        state = state.decode()
        mask = int(mask, 16)
        expected_count = 32 if profile == 'mixed' and hart >= 8 else 16
        if (hart >= 16 or implemented != expected_count or gran != 12
                or mask not in expected_masks[state] or active != mask.bit_count()):
            raise RuntimeError(f'Unexpected PMP CSR on hart {hart} in {state}: {mask:#x}')
        harts[state].add(hart)
        max_active[state] = max(max_active.get(state, 0), active)
    missing_boot = sorted(set(range(16)) - harts['boot-host'])
    if missing_boot:
        raise RuntimeError(f'Missing boot PMP readback on harts {missing_boot}')
    # During runtime, OP-TEE and OpenSBI can interleave UART bytes.
    missing_states = [state for state in expected_masks if not harts[state]]
    if missing_states:
        raise RuntimeError(f'Missing PMP readback for {missing_states}')
    return max_active


def check_optee_pmp16_geu(output):
    host = (0xf0700000, 14, 0x18)
    tee = (0xf0702000, 12, 0x1b)
    expected = {b'boot-host': host, b'host': host, b'enclave': host, b'optee': tee}
    boot_harts = set()
    entered = set()
    returned = set()
    indices = set()
    linux_smp = output.index(b'smp: Brought up 1 node, 16 CPUs')
    rows = re.finditer(
        rb'\[K3-PMP\] retarget CSR hart=(\d+) state=(boot-host|host|optee|enclave) '
        rb'slot=(\d+) base=0x([0-9a-f]+) order=(\d+) prot=0x([0-9a-f]+)',
        output)
    for row in rows:
        hart, state, slot, base, order, prot = row.groups()
        hart, slot = int(hart), int(slot)
        actual = (int(base, 16), int(order), int(prot, 16))
        if hart >= 16 or slot >= 13 or actual != expected[state]:
            raise RuntimeError(f'Unexpected GEU PMP readback: {row[0].decode()}')
        indices.add(slot)
        if state == b'boot-host':
            boot_harts.add(hart)
        elif row.start() > linux_smp:
            if state == b'optee':
                entered.add(hart)
            elif state == b'host' and hart in entered:
                returned.add(hart)
    if boot_harts != set(range(16)) or len(indices) != 1 or not returned:
        raise RuntimeError('Missing GEU boot readback or runtime OP-TEE/host round trip')
    return {'slot': indices.pop(), 'runtime_round_trip_harts': sorted(returned)}


def run_optee(args):
    tee, dtb, initrd = (path.resolve() for path in args.optee_coexistence)
    qemu = args.prefix / 'bin/qemu-system-riscv64'
    bios = args.prefix / 'firmware/k3/fw_dynamic.bin'
    kernel = args.prefix / 'boot/k3/Image'
    log = args.logs / 'optee-coexistence.log'
    record = {'case': 'optee-coexistence', 'sstc': args.sstc,
              'pass': False, 'log': str(log)}
    machine = 'jupiter2,wtm-rng=on'
    if args.optee_pmp16 == 'mixed':
        machine += ',mixed-pmp=on'
    if args.optee_pmp16:
        record['pmp_profile'] = args.optee_pmp16
    granularity = 4096 if args.optee_pmp16 else 16
    command = [
        str(qemu), '-accel', 'tcg,thread=multi', '-M', machine,
        '-cpu', 'rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,'
                f'pmp-granularity={granularity},sstc={args.sstc}',
        '-smp', '16', '-m', '2G', '-display', 'none', '-monitor', 'none',
        '-serial', 'stdio', '-bios', str(bios), '-kernel', str(kernel),
        '-dtb', str(dtb), '-initrd', str(initrd),
        '-device', f'loader,file={str(tee).replace(",", ",,")}',
        '-append', 'console=ttyS0,115200 earlycon=sbi keep_bootcon '
                   'printk.devkmsg=on rdinit=/init cma=512M@4G-16G',
    ]
    record['command'] = command
    markers = (
        b'smp: Brought up 1 node, 16 CPUs',
        b'PASS: 16 enclave runs, 33 TA calls including OCALL',
        b'reboot: Power down',
    )
    try:
        with log.open('wb') as stream:
            for path in (qemu, bios, kernel, tee, dtb, initrd):
                if not path.is_file() or not path.stat().st_size:
                    raise FileNotFoundError(f'Missing OP-TEE test input: {path}')
            process = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stream,
                                     stderr=subprocess.STDOUT, timeout=args.timeout)
        output = log.read_bytes()
        record['qemu_exit'] = process.returncode
        missing = [marker.decode() for marker in markers if marker not in output]
        if process.returncode or missing:
            record['error'] = f'QEMU exit {process.returncode}; missing markers: {missing}'
        else:
            if args.optee_pmp16:
                record['pmp_peak_by_state'] = check_optee_pmp16(output, args.optee_pmp16)
            if args.optee_pmp16_geu:
                record['geu_pmp'] = check_optee_pmp16_geu(output)
            record['pass'] = True
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        record['error'] = str(exc)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=ROOT / 'install/keystone')
    parser.add_argument('--rootfs', type=Path)
    parser.add_argument('--logs', type=Path, default=ROOT / 'verifications/crypto/results')
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--sstc', choices=['on', 'off'], default='on')
    parser.add_argument('--all', action='store_true', help='Run the existing guest suite each boot and the seven-case RNG matrix')
    parser.add_argument('--optee-coexistence', type=Path, nargs=3,
                        metavar=('TEE_ELF', 'BOOT_DTB', 'INITRAMFS'),
                        help='also run the 16-hart OP-TEE/Keystone guest integration')
    parser.add_argument('--optee-pmp16', nargs='?', const='mixed', choices=['mixed', 'uniform16'],
                        help='verify 16-slot PMP usage with boot-pmp16.dtb (default profile: mixed)')
    parser.add_argument('--optee-pmp16-geu', action='store_true',
                        help='verify GEU address changes with boot-pmp16-geu.dtb')
    args = parser.parse_args()
    if args.optee_pmp16 and not args.optee_coexistence:
        parser.error('--optee-pmp16 requires --optee-coexistence')
    if args.optee_pmp16_geu and not args.optee_pmp16:
        parser.error('--optee-pmp16-geu requires --optee-pmp16')
    # Guest metadata paths use the repository's standard installation.
    if args.prefix.resolve() != (ROOT / 'install/keystone').resolve():
        parser.error('This runner currently requires the standard install/keystone prefix; custom boot can be tested manually')
    args.rootfs = args.rootfs or args.prefix / 'rootfs/keystone-rootfs.img'
    args.logs.mkdir(parents=True, exist_ok=True)
    records = []
    for name, provider in [('qemu-dev-boot1', 'qemu-dev'), ('qemu-dev-boot2', 'qemu-dev'),
                           ('unavailable', 'unavailable')]:
        result = run(args, name, provider)
        records.append(result)
        scope = ('SBI 2001/2002/2003/2004(undefined)/2005/3001/3002/3003/3004/3006/4000'
                 if args.all else 'SBI 3002/3003')
        print(('PASS' if result['pass'] else 'FAIL'), scope, name,
              result.get('error', ''), flush=True)
        # Show actual guest assertions, rather than treating a boot summary as
        # a separate assertion for every SBI in the lifecycle.
        serial = Path(result['log'])
        if serial.is_file():
            for line in serial.read_text(errors='replace').splitlines():
                if line.startswith(('PASS ', 'FAIL ', 'SKIP ', 'INFO HOST TIMER:',
                                    '[SM/TIMER]', '[SM/CRYPTO] provider=', 'Boot HART ISA Extensions')):
                    print('  ' + line, flush=True)
        if not result['pass']:
            print('Log:', result['log'], flush=True)
            path = Path(result['log'])
            if path.exists():
                print('\n'.join(path.read_text(errors='replace').splitlines()[-25:]), flush=True)
        (args.logs / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n')
    if args.all:
        rng_logs = args.logs / 'rng'
        result = subprocess.run(['python3', str(ROOT / 'verifications/random/run-qemu-matrix.py'),
                                 '--prefix', str(args.prefix), '--rootfs', str(args.rootfs),
                                 '--logs', str(rng_logs), '--timeout', str(args.timeout), '--sstc', args.sstc])
        records.append({'case': 'rng-matrix-regression', 'pass': result.returncode == 0,
                        'log': str(rng_logs / 'manifest.json')})
        (args.logs / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n')
    if args.optee_coexistence:
        result = run_optee(args)
        records.append(result)
        print('PASS' if result['pass'] else 'FAIL', result['case'],
              result.get('error', ''), result['log'], flush=True)
        (args.logs / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n')
    return 0 if all(record['pass'] for record in records) else 1


if __name__ == '__main__':
    raise SystemExit(main())
