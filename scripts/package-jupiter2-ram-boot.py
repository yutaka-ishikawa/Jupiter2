#!/usr/bin/env python3
"""Package a Jupiter2 reference release for BootROM and SPL USB RAM boot."""
import argparse
import hashlib
from pathlib import Path
import runpy
import shutil
import sys
import tarfile
import tempfile

SCRIPTS = Path(__file__).resolve().parent
ARCHIVE_NAME = 'ram-boot-bundle.tar.gz'
LINUX_DTB = Path('images/k3-pico-itx-keystone-optee.dtb')


def write_checksum(path, record, base):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    record.write_text(f'{digest}  {path.relative_to(base).as_posix()}\n')


def package(release, output):
    if output.exists() or output.is_symlink():
        raise ValueError('output already exists; choose a new --output')

    # Use the same image checks as the USB operation tool.
    checked_release = runpy.run_path(str(SCRIPTS / 'run-jupiter2-ram-boot.py'))['checked_release']
    release, images = checked_release(release)
    inputs = images + [release / 'records/manifest.json']
    inputs += [release / 'records' / (image.name + '.sha256') for image in images]
    linux_dtb = release / LINUX_DTB
    has_linux_dtb = linux_dtb.exists() or linux_dtb.is_symlink()
    if has_linux_dtb:
        inputs.append(linux_dtb)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.jupiter2-ram-bundle-', dir=output.parent) as name:
        stage = Path(name)
        bundled = stage / 'release'
        for source in inputs:
            if not source.is_file() or source.stat().st_size == 0:
                raise ValueError(f'missing or empty release file: {source}')
            target = bundled / source.relative_to(release)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        checked_release(bundled)

        # Include current host tools even when the input predates bundled tools.
        builder = runpy.run_path(str(SCRIPTS / 'build-jupiter2-reference-ram-boot.py'))
        builder['package_runtime_tools'](bundled)
        if has_linux_dtb:
            write_checksum(bundled / LINUX_DTB,
                           bundled / 'records' / (LINUX_DTB.name + '.sha256'),
                           bundled)

        archive = stage / ARCHIVE_NAME
        with tarfile.open(archive, 'w:gz') as bundle:
            bundle.add(bundled, arcname='release')
        write_checksum(archive, stage / (ARCHIVE_NAME + '.sha256'), stage)

        # Reserve a new destination without overwriting a concurrent output.
        output.mkdir()
        try:
            for entry in stage.iterdir():
                entry.rename(output / entry.name)
        except BaseException:
            shutil.rmtree(output)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True,
                        help='release directory from the reference RAM boot build')
    parser.add_argument('--output', type=Path, required=True,
                        help='new directory for the portable release, tar.gz and checksum')
    args = parser.parse_args()
    output = args.output.absolute()
    try:
        package(args.release, output)
    except (OSError, ValueError, tarfile.TarError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    print(f'Archive: {output / ARCHIVE_NAME}')
    print(f'SHA-256: {output / (ARCHIVE_NAME + ".sha256")}')
    print(f'Release: {output / "release"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
