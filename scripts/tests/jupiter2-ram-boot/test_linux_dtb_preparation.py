#!/usr/bin/env python3
"""目的: 試験用Linux DTBの限定変更と、有効mailbox利用者がいる場合の拒否を検証する。

実dtc/fdtputでDTBを生成・変更するホスト試験。元DTBの保持、他ノードと未知の
プロパティの保持を確認する。CPU/SBI/PMPは模擬せず、実機起動は行わない。
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[2]
SCRIPT = SCRIPTS / 'prepare-jupiter2-keystone-linux-dtb.py'
spec = importlib.util.spec_from_file_location('prepare_linux_dtb', SCRIPT)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
fit = prepare.load_fit_parser()


@unittest.skipUnless(all(shutil.which(t) for t in ('dtc', 'fdtput')),
                     'requires real dtc/fdtput')
class LinuxDtbTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.input = self.base / 'original.dtb'
        self.output = self.base / 'keystone.dtb'

    def make_input(self, active=False, unknown=False):
        mailboxes = ''.join(
            f'mailbox{i}@{0xcac90000 + i * 0x400:x} {{ '
            'compatible = "spacemit,k3-mailbox"; '
            f'reg = <0 0x{0xcac90000 + i * 0x400:x} 0 0x400>; '
            '#mbox-cells = <1>; status = "okay"; '
            + ('phandle = <16>; ' if i == 3 else '') + '};'
            for i in range(4))
        text = '''/dts-v1/; / { #address-cells = <2>; #size-cells = <2>;
 chosen { test-property = "preserve this"; };
 soc { #address-cells = <2>; #size-cells = <2>; ranges;
 ''' + mailboxes + '''
 mailbox4@cac91000 { compatible = "spacemit,k3-mailbox";
  reg = <0 0xcac91000 0 0x400>; #mbox-cells = <1>; status = "okay"; phandle = <17>; };
 remote0 { status = "%s"; mboxes = <%d 1 16 2>; };
 remote1 { status = "okay"; mboxes = <17 0 17 1>; };
 mpxy { compatible = "riscv,sbi-mpxy-mbox"; #mbox-cells = <2>;
  phandle = <18>; status = "okay"; };
 regulator { status = "okay"; mboxes = <18 7 0>; };
 }; };''' % ('okay' if active else 'disabled', 99 if unknown else 16)
        source = self.base / 'input.dts'
        source.write_text(text)
        subprocess.run(['dtc', '-q', '-I', 'dts', '-O', 'dtb', '-o', self.input, source],
                       check=True, capture_output=True)

    def run_cli(self, output=None):
        return subprocess.run([sys.executable, str(SCRIPT), '--input', str(self.input),
                               '--output', str(output or self.output)],
                              text=True, capture_output=True)

    def test_only_four_status_properties_change(self):
        self.make_input()
        before = self.input.read_bytes()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.input.read_bytes(), before)
        root, _ = fit.parse_fdt(self.output.read_bytes())
        nodes = prepare.nodes_with_status(fit, root)
        for i in range(4):
            self.assertFalse(nodes[f'/soc/mailbox{i}@{0xcac90000 + i * 0x400:x}'][1])
        self.assertTrue(nodes['/soc/mailbox4@cac91000'][1])
        self.assertTrue(nodes['/soc/remote1'][1])
        self.assertTrue(nodes['/soc/mpxy'][1])
        self.assertEqual(nodes['/chosen'][0].props['test-property'], b'preserve this\0')
        report = json.loads(self.output.with_suffix('.dtb.json').read_text())
        self.assertEqual(report['input_sha256'], hashlib.sha256(before).hexdigest())

    def test_active_consumer_refuses_change(self):
        self.make_input(active=True)
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('enabled mailbox consumer', result.stderr)
        self.assertFalse(self.output.exists())

    def test_unknown_provider_refuses_change(self):
        self.make_input(unknown=True)
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unknown mailbox provider', result.stderr)

    def test_input_cannot_be_overwritten(self):
        self.make_input()
        before = self.input.read_bytes()
        result = self.run_cli(output=self.input)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.input.read_bytes(), before)

    def test_existing_different_output_is_preserved(self):
        self.make_input()
        self.output.write_bytes(b'existing file')
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b'existing file')

    def test_repeat_with_same_output_is_idempotent(self):
        self.make_input()
        first = self.run_cli()
        second = self.run_cli()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)


if __name__ == '__main__':
    unittest.main()
