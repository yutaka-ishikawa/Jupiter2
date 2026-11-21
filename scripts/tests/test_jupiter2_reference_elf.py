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


if __name__ == '__main__':
    unittest.main()
