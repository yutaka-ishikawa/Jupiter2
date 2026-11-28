#!/usr/bin/env python3
"""目的: PC操作スクリプトの破損検知・dry-run・UARTコマンド生成を検証する。

実FITツールで形式試験用releaseを作るが、USBへは接続せず、fastbootを実行しない。
生成するU-Bootテキストはbash -nで構文だけ確認し、bootiや試験用ELFは実行しない。
実機のDDR/ESOS/OpenSBI/Linuxの合格判定を行うスクリプトではない。
"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1]
SCRIPT = SCRIPTS / 'run-jupiter2-ram-boot.py'
BUNDLER = SCRIPTS / 'package-jupiter2-ram-boot.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = load('fit_fixtures', HERE / 'test_fit_packaging.py')
reference = load('reference_builder', SCRIPTS / 'build-jupiter2-reference-ram-boot.py')


@unittest.skipUnless(all(shutil.which(t) for t in ('dtc', 'mkimage', 'dumpimage')),
                     'requires real FIT tools')
class HostOperationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PackagingTests('test_reference_layout_roundtrip')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.reference_fit()
        result = self.fixture.build(uboot_layout='reference')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.base = self.fixture.base
        self.release = self.base / 'release'

    def run_cli(self, *args, script=SCRIPT):
        return subprocess.run([sys.executable, str(script), *map(str, args)],
                              cwd=self.base, text=True, capture_output=True)

    def test_rom_dry_run_never_executes_fastboot(self):
        result = self.run_cli('--phase', 'fsbl', '--release', self.release,
                              '--fastboot', '/not-installed-fastboot', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('stage', result.stdout)
        self.assertIn('FSBL.bin', result.stdout)
        self.assertFalse((self.release / 'logs').exists())

    def test_fit_dry_run_includes_limit_check(self):
        result = self.run_cli('--phase', 'fit', '--release', self.release,
                              '--serial', 'TEST-SERIAL', '--dry-run',
                              '--fastboot', '/not-installed-fastboot')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(result.stdout.index('getvar'), result.stdout.index('stage'))
        self.assertIn('ram-boot-vendor.itb', result.stdout)

    def test_corrupted_image_is_rejected_before_transfer(self):
        (self.release / 'images/FSBL.bin').write_bytes(b'corrupted')
        result = self.run_cli('--phase', 'fsbl', '--release', self.release, '--dry-run')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checksum mismatch', result.stderr)
        self.assertNotIn('stage', result.stdout)

    def test_nonreference_release_is_rejected(self):
        path = self.release / 'records/manifest.json'
        manifest = json.loads(path.read_text())
        manifest['uboot_layout'] = 'vendor'
        path.write_text(json.dumps(manifest))
        result = self.run_cli('--phase', 'fsbl', '--release', self.release, '--dry-run')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('reference builder', result.stderr)

    def test_missing_spl_serial_is_rejected(self):
        result = self.run_cli('--phase', 'fit', '--release', self.release, '--dry-run')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires the serial', result.stderr)

    def linux_args(self):
        return ['--phase', 'linux', '--kernel', '/Image-6.18.3-keystone',
                '--initrd', '/initrd.img-6.18.3',
                '--dtb', '/spacemit/6.18.3-generic/k3-pico-itx.dtb',
                '--root-partuuid', '73708e51-d3a9-4b6f-ab55-894cd1d8b4a0']

    def test_uart_text_has_defined_dtb_and_saved_initrd_size(self):
        output = self.base / 'boot-linux.cmd'
        result = self.run_cli(*self.linux_args(), '--output', output)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = output.read_text()
        self.assertIn('setenv fdtfile k3-pico-itx.dtb', text)
        self.assertLess(text.index('setenv initrd_size ${filesize}'),
                        text.index('if load scsi 0:2 ${fdt_addr_r}'))
        self.assertIn('if load scsi', text)
        self.assertIn('root=PARTUUID=73708e51-d3a9-4b6f-ab55-894cd1d8b4a0', text)
        subprocess.run(['bash', '-n', output], check=True, capture_output=True)

    def test_uart_path_cannot_inject_commands(self):
        args = self.linux_args()
        args[args.index('--kernel') + 1] = '/Image;reset'
        result = self.run_cli(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Linux paths', result.stderr)
        self.assertNotIn('booti', result.stdout)

    def test_bundled_tool_works_outside_release_directory(self):
        hashes = reference.package_runtime_tools(self.release)
        self.assertIn('tools/ram-boot.py', hashes)
        subprocess.run(['sha256sum', '-c', 'records/host-tools.sha256'],
                       cwd=self.release, check=True, capture_output=True)
        result = self.run_cli('--phase', 'fsbl', '--dry-run',
                              '--fastboot', '/not-installed-fastboot',
                              script=self.release / 'tools/ram-boot.py')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ram_boot_bundle_is_relocatable(self):
        dtb = 'k3-pico-itx-keystone-optee.dtb'
        shutil.copyfile(self.base / 'board.dtb', self.release / 'images' / dtb)
        self.assertFalse((self.release / 'tools').exists())
        output = self.base / 'ram-boot-bundle'
        args = ('--release', self.release, '--output', output)
        result = self.run_cli(*args, script=BUNDLER)
        self.assertEqual(result.returncode, 0, result.stderr)

        archive = output / 'ram-boot-bundle.tar.gz'
        subprocess.run(['sha256sum', '-c', archive.name + '.sha256'],
                       cwd=output, check=True, capture_output=True)
        extracted = self.base / 'unpacked'
        extracted.mkdir()
        subprocess.run(['tar', '-xzf', archive, '-C', extracted], check=True, capture_output=True)
        release = extracted / 'release'
        subprocess.run(['sha256sum', '-c', 'records/FSBL.bin.sha256',
                        'records/ram-boot-vendor.itb.sha256', 'records/host-tools.sha256',
                        f'records/{dtb}.sha256'],
                       cwd=release, check=True, capture_output=True)

        for phase in ('fsbl', 'fit'):
            result = self.run_cli('--phase', phase, '--serial', 'TEST-SERIAL',
                                  '--fastboot', '/not-installed-fastboot', '--dry-run',
                                  script=release / 'tools/ram-boot.py')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('stage', result.stdout)

        result = self.run_cli(*args, script=BUNDLER)
        self.assertEqual(result.returncode, 1)
        self.assertIn('output already exists', result.stderr)
        subprocess.run(['sha256sum', '-c', archive.name + '.sha256'],
                       cwd=output, check=True, capture_output=True)

    def test_corrupted_fit_cannot_be_bundled(self):
        (self.release / 'images/ram-boot-vendor.itb').write_bytes(b'corrupted')
        output = self.base / 'ram-boot-bundle'
        result = self.run_cli('--release', self.release, '--output', output, script=BUNDLER)
        self.assertEqual(result.returncode, 1)
        self.assertIn('checksum mismatch', result.stderr)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
