#!/usr/bin/env python3
"""Host ELF-to-DT checks with actual LLVM and dtc; no firmware execution."""
import copy
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reference = load('reference', 'build-jupiter2-reference-ram-boot.py')
fit = load('fit', 'build-jupiter2-ram-boot-image.py')


@unittest.skipUnless(all(shutil.which(t) for t in ('clang', 'ld.lld', 'dtc')),
                     'requires LLVM with RISC-V target and dtc')
class ElfEntryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        source = self.base / 'entry.S'
        source.write_text('.text\n.globl _start\n_start:\n    j _start\n')
        subprocess.run(['clang', '--target=riscv64-unknown-elf', '-march=rv64imac',
                        '-c', source, '-o', self.base / 'entry.o'], check=True,
                       capture_output=True)
        subprocess.run(['ld.lld', '-Ttext=0x100804000', '-e', '_start',
                        self.base / 'entry.o', '-o', self.base / 'entry.elf'],
                       check=True, capture_output=True)
        self.data = (self.base / 'entry.elf').read_bytes()
        self.info = reference.elf_load_map(self.data)

    def compiled_tree(self):
        dts = '''/dts-v1/;
/ { soc {
 rcpu@0 { reg = <0 0 0 0>; mem_heap_start = <1 0x400000>;
  fw_boot_entry = <1 0x200000>; };
 rcpu@1 { reg = <0 0 0 0>; mem_heap_start = <1 0xa00000>;
  fw_boot_entry = <1 0x800000>; };
}; };'''
        infos = [copy.deepcopy(self.info), copy.deepcopy(self.info)]
        changed = reference.set_rcpu_entries(dts, infos)
        self.assertEqual(infos[1]['source_dt_entry'], 0x100800000)
        self.assertIn('mem_heap_start = <1 0xa00000>', changed)
        path = self.base / 'tree.dts'
        path.write_text(changed)
        output = self.base / 'tree.dtb'
        subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', output, path],
                       check=True, capture_output=True)
        return output, infos

    def test_real_elf_entry_reaches_compiled_dt(self):
        self.assertEqual(self.info['entry'], 0x100804000)
        output, infos = self.compiled_tree()
        reference.verify_rcpu_dtb(fit, output, infos)

    def test_old_entry_outside_code_is_rejected(self):
        data = bytearray(self.data)
        struct.pack_into('<Q', data, 24, 0x100800000)
        with self.assertRaisesRegex(ValueError, 'executable LOAD'):
            reference.elf_load_map(data)

    def test_stale_dt_entry_is_rejected(self):
        output, infos = self.compiled_tree()
        infos[1]['entry'] = 0x100800000
        with self.assertRaisesRegex(ValueError, 'compiled SPL DT'):
            reference.verify_rcpu_dtb(fit, output, infos)


@unittest.skipUnless(shutil.which('dtc'), 'requires real dtc')
class RpmiContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)

    def compile(self, text, name):
        source = self.base / (name + '.dts')
        output = self.base / (name + '.dtb')
        source.write_text(text)
        subprocess.run(['dtc', '-q', '-I', 'dts', '-O', 'dtb', '-o', output, source],
                       check=True, capture_output=True)
        return output.read_bytes()

    def server(self, status, base, name):
        data = self.compile('''/dts-v1/; / {
 mailbox { compatible = "spacemit,k3-mailbox3"; phandle = <1>;
  reg = <0xcac90c00 0x400>; #mbox-cells = <1>; };
 rpmi { compatible = "spacemit,k3-os0-rpmi"; status = "%s";
  shmem-base = <1 0x%x>; shmem-size = <0x4000>; slot-size = <256>;
  a2p-queue-size = <0x1000>; p2a-queue-size = <0x1000>; mboxes = <1 0>;
 }; };''' % (status, base), name)
        return fit.parse_fdt(data)[0]

    def test_disabled_server_is_not_selected(self):
        trees = [self.server('okay', 0x800000, 'core0'),
                 self.server('disabled', 0xe00000, 'core1')]
        contract = reference.rpmi_contract(fit, trees)
        self.assertEqual(contract['active_core'], 0)
        self.assertEqual(contract['shmem-base'], 0x100800000)

    def test_two_enabled_servers_are_rejected(self):
        trees = [self.server('okay', 0x800000, 'core0'),
                 self.server('okay', 0xe00000, 'core1')]
        with self.assertRaisesRegex(ValueError, 'exactly one enabled'):
            reference.rpmi_contract(fit, trees)

    def test_board_override_fixes_actual_mismatch_pattern(self):
        contract = reference.rpmi_contract(fit, [self.server('okay', 0x800000, 'core0')])
        source = '''/dts-v1/; / {
 rpmi_shmem_mbox: mailbox {
  compatible = "riscv,rpmi-shmem-mbox";
  reg = <1 0xe00000 0 0x1000>, <1 0xe01000 0 0x1000>,
        <1 0xe02000 0 0x1000>, <1 0xe03000 0 0x1000>, <0 0xcac90c00 0 0x100>;
  reg-names = "a2p-req", "p2a-ack", "p2a-req", "a2p-ack", "db-reg";
  riscv,slot-size = <256>;
 }; };'''
        before = self.compile(source, 'before')
        with self.assertRaisesRegex(ValueError, 'RPMI transport differs'):
            reference.verify_rpmi_dtb(fit, before, contract)
        after = self.compile(source + reference.rpmi_board_override(contract), 'after')
        reference.verify_rpmi_dtb(fit, after, contract)


if __name__ == '__main__':
    unittest.main()
