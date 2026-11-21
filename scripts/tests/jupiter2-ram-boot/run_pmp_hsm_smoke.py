#!/usr/bin/env python3
"""開発PC上で実QEMU/OpenSBI/SMの全Hart起動を確認する試験。

目的: PMP16/32混在と4 KiB粒度で各Hartがroot readbackを通過し、
実SBI HSM経由で全16 HartがS-modeへ到達することを確認する。
モックや本体関数の抜き出しは使わない。Linux/hello/PMP隔離試験とは別。
生成ELFと各構成のUARTログは --output ディレクトリに保持する。
"""
import argparse
import pathlib
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--firmware", required=True, help="SM-linked fw_dynamic.bin with boot trace")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--clang", default="clang")
    parser.add_argument("--linker", default="ld.lld")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = pathlib.Path(__file__).with_name("pmp-hsm-smoke.S")
    obj = args.output / "pmp-hsm-smoke.o"
    elf = args.output / "pmp-hsm-smoke.elf"
    subprocess.run([args.clang, "--target=riscv64-unknown-elf", "-march=rv64ima_zicsr",
                    "-mabi=lp64", "-c", str(source), "-o", str(obj)], check=True)
    linker_script = args.output / "pmp-hsm-smoke.ld"
    # The lowest LOAD must be the entry; QEMU uses LOAD low address as next_addr.
    linker_script.write_text("""OUTPUT_ARCH(riscv)
ENTRY(_start)
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
 . = 0x104000000;
 .text : { *(.text.init) *(.text*) } :text
 .rodata : { *(.rodata*) } :text
 . = ALIGN(4096);
 .bss (NOLOAD) : { *(.bss*) } :data
}
""")
    subprocess.run([args.linker, "-m", "elf64lriscv", "-T", str(linker_script),
                    str(obj), "-o", str(elf)], check=True)
    for mixed in (False, True):
        profile = "mixed" if mixed else "uniform16"
        command = [args.qemu, "-accel", "tcg", "-M",
                   "jupiter2,mixed-pmp=" + ("on" if mixed else "off"),
                   "-smp", "16", "-m", "256M", "-cpu",
                   "rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16",
                   "-bios", str(pathlib.Path(args.firmware).resolve()), "-kernel", str(elf),
                   "-display", "none", "-serial", "stdio", "-monitor", "none"]
        logpath = args.output / (profile + "-uart.log")
        with logpath.open("w") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=45)
        log = logpath.read_text(errors="replace")
        if result.returncode or "PMP-HSM-SMOKE: all 16 Harts reached S-mode" not in log:
            raise SystemExit(f"FAIL {profile}: inspect {logpath}")
        matches = re.findall(r"root-config PASS hart=(\d+) implemented=(\d+) common=16 "
                             r"extra-off=(\d+) root=\d+ Keystone-free=\d+", log)
        actual = {int(hart): (int(count), int(extra)) for hart, count, extra in matches}
        expected = {hart: (32, 16) if mixed and hart >= 8 else (16, 0) for hart in range(16)}
        if actual != expected:
            raise SystemExit(f"FAIL {profile}: missing or incorrect Hart readbacks: {actual}")
        if "extra rejected" in log or "PMP configure failed" in log:
            raise SystemExit(f"FAIL {profile}: rejected PMP state, inspect {logpath}")
        print(f"PASS {profile}: real OpenSBI/SM readback and HSM S-mode arrival on 16 Harts")


if __name__ == "__main__":
    main()
