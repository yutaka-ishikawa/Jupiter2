#!/usr/bin/env python3
"""Host packaging tests using real dtc/mkimage/dumpimage, not simulated SBI."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'build-jupiter2-ram-boot-image.py'
spec = importlib.util.spec_from_file_location('ram_builder', SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@unittest.skipUnless(all(shutil.which(x) for x in ('dtc', 'mkimage', 'dumpimage')),
                     'requires real dtc/mkimage/dumpimage')
class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.run_tool(['dtc', '-I', 'dts', '-O', 'dtb', '-o', 'board.dtb'],
                      input='/dts-v1/; / { compatible = "test,board"; };')
        for name, data in [('uboot.bin', b'UBOOT' * 128), ('esos.bin', b'ESOS' * 64),
                           ('opensbi.bin', b'SBI' * 64), ('FSBL.bin', b'FSBL fixture')]:
            (self.base / name).write_bytes(data)
        self.uboot_dts = '''/dts-v1/;
/ {
 #address-cells = <2>;
 description = "vendor fixture";
 images {
  uboot { data = /incbin/("uboot.bin"); type = "standalone";
   arch = "riscv"; compression = "none"; load = <1 0x02000000>;
   hash-1 { algo = "crc32"; }; };
  fdt_11 { data = /incbin/("board.dtb"); type = "flat_dt";
   compression = "none"; hash-1 { algo = "sha256"; }; };
 };
 configurations { default = "conf_11";
  conf_11 { description = "k3-pico-itx"; fdt = "fdt_11"; loadables = "uboot"; };
 };
};'''
        self.esos_dts = '''/dts-v1/;
/ {
 #address-cells = <2>;
 description = "esos fixture";
 images {
  rt { data = /incbin/("esos.bin"); type = "firmware";
   arch = "riscv"; compression = "none"; load = <1 0x00800000>;
   hash-1 { algo = "sha256"; }; };
 };
 configurations { default = "board";
  board { description = "k3-pico-itx"; loadables = "rt"; };
 };
};'''
        self.make_fit('uboot', self.uboot_dts)
        self.make_fit('esos', self.esos_dts)

    def run_tool(self, cmd, **kwargs):
        return subprocess.run(cmd, cwd=self.base, check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)

    def make_fit(self, name, dts, external=False):
        (self.base / (name + '.its')).write_text(dts)
        self.run_tool(['mkimage', *(['-E'] if external else []),
                       '-f', name + '.its', name + '.itb'])

    def build(self, **options):
        args = dict(uboot_itb=self.base / 'uboot.itb', esos_itb=self.base / 'esos.itb',
                    opensbi_bin=self.base / 'opensbi.bin', fsbl=self.base / 'FSBL.bin',
                    configuration='conf_11', variant='vendor',
                    opensbi_reserve_bytes='0x100000', max_download_bytes='0x400000',
                    output=self.base / 'release')
        args.update(options)
        cmd = [sys.executable, str(SCRIPT)]
        for key, value in args.items():
            cmd += ['--' + key.replace('_', '-'), str(value)]
        return subprocess.run(cmd, cwd=self.base, capture_output=True, text=True)

    def test_roundtrip_and_payload_extraction(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        fit = self.base / 'release/images/ram-boot-vendor.itb'
        root, _, _ = builder.read_fit(fit)
        config = root.children['configurations'].children['conf_11']
        self.assertEqual(builder.string(config, 'firmware'), 'opensbi')
        self.assertEqual(builder.strings(config.props['loadables']), ['uboot', 'esos-0'])
        self.assertEqual(builder.number(root.children['images'].children['uboot'].props['entry']),
                         0x102000000)
        for index, source in [(0, 'opensbi.bin'), (1, 'uboot.bin'), (2, 'board.dtb'), (3, 'esos.bin')]:
            extracted = self.base / f'extract-{index}.bin'
            self.run_tool(['dumpimage', '-T', 'flat_dt', '-p', str(index), '-o', str(extracted), str(fit)])
            self.assertEqual(extracted.read_bytes(), (self.base / source).read_bytes())
        manifest = json.loads((self.base / 'release/records/manifest.json').read_text())
        self.assertFalse(manifest['hardware_verified'])
        self.assertEqual((self.base / 'release/images/FSBL.bin').read_bytes(), b'FSBL fixture')
        rebuilt = subprocess.run(['mkimage', '-f', 'ram-boot.its', 'rebuilt.itb'],
                                 cwd=self.base / 'release/records', capture_output=True)
        self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
        checksums = list((self.base / 'release/records').glob('*.sha256'))
        for checksum in checksums:
            check = subprocess.run(['sha256sum', '-c', str(checksum)],
                                   cwd=self.base / 'release', capture_output=True)
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_external_data_inputs(self):
        self.make_fit('uboot', self.uboot_dts, external=True)
        self.make_fit('esos', self.esos_dts, external=True)
        result = self.build(variant='keystone')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.base / 'release/images/ram-boot-keystone.itb').is_file())

    def test_hash_corruption_rejected_without_output(self):
        path = self.base / 'uboot.itb'
        path.write_bytes(path.read_bytes().replace(b'UBOOTUBOOT', b'BROKENBOOT', 1))
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('hash mismatch', result.stderr)
        self.assertFalse((self.base / 'release').exists())

    def test_wrong_board_rejected(self):
        result = self.build(board='k3_deb1')
        self.assertIn('does not match', result.stderr)
        self.assertNotEqual(result.returncode, 0)

    def test_missing_esos_board_rejected(self):
        self.make_fit('esos', self.esos_dts.replace('k3-pico-itx', 'k3_com260_ifx'))
        result = self.build()
        self.assertIn('exactly one matching ESOS', result.stderr)
        self.assertNotEqual(result.returncode, 0)

    def test_overlap_rejected(self):
        result = self.build(opensbi_reserve_bytes='0x900000')
        self.assertIn('overlapping', result.stderr)
        self.assertNotEqual(result.returncode, 0)

    def test_size_limit_rejected_atomically(self):
        result = self.build(max_download_bytes='128')
        self.assertIn('exceeds SPL download limit', result.stderr)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / 'release').exists())
        self.assertFalse(list(self.base.glob('.jupiter2-ram-*')))

    def test_existing_output_preserved(self):
        output = self.base / 'release'
        output.mkdir()
        (output / 'keep').write_text('keep')
        result = self.build()
        self.assertIn('already exists', result.stderr)
        self.assertEqual((output / 'keep').read_text(), 'keep')

    def test_signed_fit_rejected(self):
        self.make_fit('uboot', self.uboot_dts.replace('configurations {',
                                                    'signature-test {}; configurations {'))
        result = self.build()
        self.assertIn('signed/encrypted', result.stderr)
        self.assertNotEqual(result.returncode, 0)

    def test_compressed_input_rejected(self):
        self.make_fit('uboot', self.uboot_dts.replace('compression = "none"', 'compression = "gzip"', 1))
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('only uncompressed', result.stderr)

    def test_elf_is_not_accepted_as_bin(self):
        (self.base / 'opensbi.bin').write_bytes(b'\x7fELF' + bytes(64))
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('raw BIN', result.stderr)

    def test_runtime_reservation_covers_bin(self):
        result = self.build(opensbi_reserve_bytes='16')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('smaller than its BIN', result.stderr)

    def test_existing_dangling_symlink_preserved(self):
        output = self.base / 'release'
        output.symlink_to(self.base / 'missing')
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('already exists', result.stderr)
        self.assertTrue(output.is_symlink())

    def test_truncated_input_rejected(self):
        (self.base / 'uboot.itb').write_bytes(b'\xd0\x0d\xfe\xed')
        result = self.build()
        self.assertIn('truncated', result.stderr)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
