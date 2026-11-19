#!/usr/bin/env python3
"""Offline packaging tests with real FIT tools; no SBI/PMP or board execution."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / 'scripts/check-jupiter2-install-capacity.py'
BUILD = ROOT / 'scripts/build-jupiter2-install-image.py'
spec = importlib.util.spec_from_file_location('capacity', CHECK)
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


class InstallToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def invoke(self, script, *args, expected=0):
        proc = subprocess.run([sys.executable, str(script), *map(str, args)],
                              text=True, capture_output=True)
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        return proc

    def partition(self, name, label='opensbi', kind='nor', size='393216'):
        p = self.work / name
        p.mkdir()
        for key, value in {'name': label, 'type': kind, 'size': size,
                           'erasesize': '4096'}.items():
            (p / key).write_text(value)

    def test_live_discovery_and_explicit_selection(self):
        self.partition('mtd0', 'd420c000.spi', size='8388608')
        self.partition('mtd5')
        r = capacity.mtd_capacity(root=self.work)
        self.assertEqual((r['mtd'], r['capacity_bytes']), ('mtd5', 393216))
        with self.assertRaises(ValueError):
            capacity.mtd_capacity('mtd0', self.work)
        self.assertEqual(capacity.mtd_capacity('/dev/mtd5', self.work), r)

    def test_ambiguous_missing_and_nand(self):
        with self.assertRaises(ValueError):
            capacity.mtd_capacity(root=self.work)
        self.partition('mtd5')
        self.partition('mtd7')
        with self.assertRaises(ValueError):
            capacity.mtd_capacity(root=self.work)
        (self.work / 'mtd5/type').write_text('nand')
        with self.assertRaises(ValueError):
            capacity.mtd_capacity('mtd5', self.work)

    def test_offline_capacity_and_rejected_input(self):
        r = self.invoke(CHECK, '--capacity-bytes', '0x60000', '--json')
        self.assertEqual(json.loads(r.stdout)['capacity_bytes'], 393216)
        self.invoke(CHECK, '--capacity-bytes', '0', expected=2)
        self.invoke(CHECK, '--capacity-bytes', '393216', '--mtd', 'mtd5', expected=2)
        raw = self.work / 'raw.bin'
        raw.write_bytes(b'raw firmware')
        self.invoke(CHECK, '--capacity-bytes', '393216', '--image', raw, expected=2)
        self.invoke(CHECK, '--capacity-bytes', '393216', '--image', self.work, expected=2)

    @unittest.skipUnless(all(shutil.which(t) for t in ('mkimage', 'dumpimage', 'dtc')),
                         'real u-boot-tools and dtc required')
    def test_actual_fit_roundtrip_capacity_and_failure_cleanup(self):
        # Synthetic payload tests container handling only, not executable firmware.
        raw = self.work / 'input.bin'
        raw.write_bytes(bytes(range(256)) * 8)
        out = self.work / 'out'
        self.invoke(BUILD, '--firmware-only', '--firmware-bin', raw,
                    '--capacity-bytes', '393216', '--output', out)
        fit = out / 'bundle/firmware/fw_dynamic.itb'
        length = fit.stat().st_size
        self.invoke(CHECK, '--image', fit, '--capacity-bytes', str(length))
        r = self.invoke(CHECK, '--image', fit, '--capacity-bytes', str(length - 1),
                        '--json', expected=1)
        self.assertEqual(json.loads(r.stdout)['remaining_bytes'], -1)
        subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=out / 'bundle',
                       check=True, capture_output=True)
        with tarfile.open(out / 'bundle.tar.gz') as archive:
            self.assertIn('bundle/firmware/fw_dynamic.itb', archive.getnames())
        self.invoke(BUILD, '--firmware-only', '--firmware-bin', raw,
                    '--capacity-bytes', '393216', '--output', out, expected=2)
        bad = self.work / 'too-small'
        self.invoke(BUILD, '--firmware-only', '--firmware-bin', raw,
                    '--capacity-bytes', '1', '--output', bad, expected=2)
        self.assertFalse(bad.exists())
        self.assertFalse(list(self.work.glob('.jupiter2-image-*')))

    @unittest.skipUnless(all(shutil.which(t) for t in ('mkimage', 'dumpimage', 'dtc')),
                         'real u-boot-tools and dtc required')
    def test_full_bundle_matching_and_mismatch(self):
        k3, ks = self.work / 'k3', self.work / 'ks'
        fixtures = {
            k3 / 'firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin': b'payload',
            k3 / 'firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.elf': b'elf',
            k3 / 'linux/include/config/kernel.release': b'6.18-test\n',
            k3 / 'linux/Module.symvers': b'symbols',
            k3 / 'linux/.config': b'config',
            k3 / 'linux/arch/riscv/boot/Image': b'kernel',
            ks / 'stage/boot/k3/Image': b'kernel',
            ks / 'stage/lib/modules/6.18-test/kernel/example.ko': b'module',
            ks / 'driver/keystone-driver.ko': b'driver',
            ks / 'examples/hello/hello.ke': b'hello',
            ks / 'examples/hello-native/hello-native.ke': b'native',
        }
        for p, data in fixtures.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        import hashlib
        (ks / 'guest-overlay.kernel.sha256').write_text(hashlib.sha256(b'kernel').hexdigest())
        args = ['--capacity-bytes', '393216', '--k3-build-dir', k3, '--keystone-build-dir', ks]
        out = self.work / 'full'
        self.invoke(BUILD, *args, '--output', out)
        self.assertTrue((out / 'bundle/modules/6.18-test/extra/keystone-driver.ko').is_file())
        (ks / 'stage/boot/k3/Image').write_bytes(b'wrong kernel')
        bad = self.work / 'mismatch'
        self.invoke(BUILD, *args, '--output', bad, expected=2)
        self.assertFalse(bad.exists())


if __name__ == '__main__':
    unittest.main()
