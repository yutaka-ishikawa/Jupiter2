#!/usr/bin/env python3
"""Package prebuilt Jupiter2 artifacts and an opensbi FIT; never build or flash."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / 'scripts/check-jupiter2-install-capacity.py'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def copy_file(source, target):
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError(f'missing/empty input: {source}')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def run(*args, **kwargs):
    return subprocess.check_output(list(map(str, args)), text=True, **kwargs)


def package(args, temporary):
    bundle = temporary / 'bundle'
    firmware = bundle / 'firmware'
    firmware.mkdir(parents=True)
    fwdir = args.k3_build_dir / 'firmware/build-opensbi-k3-keystone/platform/generic/firmware'
    binary = args.firmware_bin or fwdir / 'fw_dynamic.bin'
    copy_file(binary, firmware / 'fw_dynamic.bin')
    if args.firmware_bin is None:
        copy_file(fwdir / 'fw_dynamic.elf', firmware / 'fw_dynamic.elf')
    # The fixed vendor template has load/entry 0x100000000 and no compression.
    copy_file(ROOT / 'opensbi/platform/generic/spacemit/fw_dynamic.its',
              firmware / 'fw_dynamic.its')
    log = run('mkimage', '-f', 'fw_dynamic.its', 'fw_dynamic.itb', cwd=firmware)
    log += run('dumpimage', '-l', firmware / 'fw_dynamic.itb')
    extracted = temporary / 'extracted.bin'
    run('dumpimage', '-T', 'flat_dt', '-p', '0', '-o', extracted,
        firmware / 'fw_dynamic.itb')
    if sha256(extracted) != sha256(firmware / 'fw_dynamic.bin'):
        raise ValueError('FIT extracted payload differs from input firmware')
    report = json.loads(run(sys.executable, CHECKER, '--image', firmware / 'fw_dynamic.itb',
                            '--capacity-bytes', args.capacity_bytes, '--json'))
    report['image'] = 'firmware/fw_dynamic.itb'
    (bundle / 'capacity.json').write_text(json.dumps(report, indent=2) + '\n')
    (bundle / 'fit-inspection.txt').write_text(log)
    copy_file(CHECKER, bundle / 'check-capacity.py')
    if not args.firmware_only:
        kout = args.k3_build_dir / 'linux'
        kbuild = args.keystone_build_dir
        stage = kbuild / 'stage'
        release = (kout / 'include/config/kernel.release').read_text().strip()
        if not re.fullmatch(r'[A-Za-z0-9._+-]+', release):
            raise ValueError('invalid kernel release')
        image = kout / 'arch/riscv/boot/Image'
        if not (kout / 'Module.symvers').is_file() or not (kout / 'Module.symvers').stat().st_size:
            raise ValueError('complete kernel build with Module.symvers required')
        expected = (kbuild / 'guest-overlay.kernel.sha256').read_text().strip()
        if sha256(image) != expected or sha256(stage / 'boot/k3/Image') != expected:
            raise ValueError('kernel Image and driver overlay build do not match; rebuild make keystone')
        copy_file(image, bundle / 'linux/Image')
        copy_file(kout / '.config', bundle / 'linux/config')
        modules = stage / 'lib/modules' / release
        target = bundle / 'modules' / release
        # Exclude development symlinks, retain runtime symlinks without following them.
        shutil.copytree(modules, target, symlinks=True,
                        ignore=lambda path, names: {'build', 'source'} if Path(path) == modules else set())
        copy_file(kbuild / 'driver/keystone-driver.ko', target / 'extra/keystone-driver.ko')
        for name in ('hello', 'hello-native'):
            copy_file(kbuild / 'examples' / name / f'{name}.ke', bundle / 'apps' / f'{name}.ke')
        (bundle / 'kernelrelease.txt').write_text(release + '\n')
    (bundle / 'source-commit.txt').write_text(run('git', '-C', ROOT, 'rev-parse', 'HEAD'))
    (bundle / 'source-local.patch').write_text(run('git', '-C', ROOT, 'diff', '--binary', 'HEAD'))
    # Do not silently omit newly added production sources from provenance.
    untracked = run('git', '-C', ROOT, 'ls-files', '--others', '--exclude-standard')
    (bundle / 'source-untracked.txt').write_text(untracked)
    lines = [f'{sha256(p)}  {p.relative_to(bundle).as_posix()}\n'
             for p in sorted(bundle.rglob('*')) if p.is_file() and not p.is_symlink()]
    (bundle / 'SHA256SUMS').write_text(''.join(lines))
    archive = temporary / 'bundle.tar.gz'
    with tarfile.open(archive, 'w:gz', dereference=False) as tar:
        tar.add(bundle, arcname='bundle')
    (temporary / 'bundle.tar.gz.sha256').write_text(f'{sha256(archive)}  bundle.tar.gz\n')
    extracted.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new output directory; never overwrite')
    parser.add_argument('--capacity-bytes', required=True,
                        help='opensbi capacity measured on target, decimal or 0x hexadecimal')
    parser.add_argument('--k3-build-dir', type=Path, default=ROOT / '.build-k3')
    parser.add_argument('--keystone-build-dir', type=Path, default=ROOT / '.build-keystone')
    parser.add_argument('--firmware-only', action='store_true', help='package FIT only, without Linux/apps')
    parser.add_argument('--firmware-bin', type=Path, help='explicit prebuilt BIN, requires --firmware-only')
    args = parser.parse_args()
    if args.firmware_bin and not args.firmware_only:
        parser.error('--firmware-bin requires --firmware-only')
    args.output = args.output.absolute()
    args.k3_build_dir = args.k3_build_dir.resolve()
    args.keystone_build_dir = args.keystone_build_dir.resolve()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError('output already exists; choose a new --output')
        for command in ('mkimage', 'dumpimage', 'dtc', 'git'):
            if not shutil.which(command):
                raise ValueError(f'missing {command}; install u-boot-tools, device-tree-compiler, git')
        # Validate capacity before creating any output.
        run(sys.executable, CHECKER, '--capacity-bytes', args.capacity_bytes, '--json')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.jupiter2-image-', dir=args.output.parent) as name:
            temporary = Path(name)
            package(args, temporary)
            # Reserve destination exclusively so a concurrent invocation cannot overwrite it.
            args.output.mkdir()
            try:
                for entry in temporary.iterdir():
                    shutil.move(str(entry), args.output / entry.name)
            except BaseException:
                shutil.rmtree(args.output)
                raise
        print(f'Created: {args.output / "bundle.tar.gz"}')
        print(f'FIT: {args.output / "bundle/firmware/fw_dynamic.itb"}')
        print('Capacity verified against explicit input only. No flashing or hardware validation performed.')
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError) and exc.output:
            print(exc.output, file=sys.stderr)
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
