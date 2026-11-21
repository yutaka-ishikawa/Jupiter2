#!/usr/bin/env python3
"""実system QEMUのLinux上でKeystone sampleのOCALLと正常終了を検査する。

目的: 起動だけの試験では検出できない、UTMのホスト読み取り・RESUME・DESTROYまで
実driver/SDK/Eyrie/sampleを通す。SBI/PMP/CSRのモックを使わない。
initrdには同ディレクトリのlinux-sample-init.shを/initとして入れ、対応kernelの
実driver、hello/hello-nativeの実package内容とRISC-V実行ライブラリーを配置する。
--reference-firmwareを指定すると、修正前のSIGSEGVを期待する負の回帰試験も行う。
この負の試験はEPM隔離違反の検査を意味しない。
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--initrd", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--reference-firmware", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cases = [("fixed", args.firmware)]
    if args.reference_firmware:
        cases.append(("reference", args.reference_firmware))
    result = {"inputs": {str(p.resolve()): digest(p) for p in
                         [args.qemu, args.kernel, args.initrd, args.firmware]},
              "cases": []}
    if args.reference_firmware:
        result["inputs"][str(args.reference_firmware.resolve())] = digest(args.reference_firmware)
    manifest = args.output / "results.json"
    failed = False
    for name, firmware in cases:
        for mixed in (False, True):
            profile = "mixed" if mixed else "uniform16"
            logpath = args.output / f"{name}-{profile}.log"
            command = [str(args.qemu.resolve()), "-accel", "tcg", "-M",
                       "jupiter2,mixed-pmp=" + ("on" if mixed else "off"),
                       "-smp", "16", "-m", "512M", "-cpu",
                       "rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16,sstc=on",
                       "-bios", str(firmware.resolve()), "-kernel", str(args.kernel.resolve()),
                       "-initrd", str(args.initrd.resolve()), "-append",
                       "console=ttyS0,115200 earlycon=sbi rdinit=/init loglevel=7 panic=-1",
                       "-display", "none", "-serial", "stdio", "-monitor", "none", "-no-reboot"]
            record = {"firmware": name, "profile": profile, "command": command,
                      "log": logpath.name, "pass": False}
            with logpath.open("w") as log:
                try:
                    run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                         timeout=args.timeout)
                    record["returncode"] = run.returncode
                except subprocess.TimeoutExpired:
                    record["timeout"] = True
            log = logpath.read_text(errors="replace")
            online = "KSB073-SAMPLES: ONLINE 0-15" in log
            normal_exit = record.get("returncode") == 0
            if name == "fixed":
                markers = [f"KSB073-SAMPLES: EXIT {app} cpu={cpu} 0"
                           for cpu in (3, 8) for app in ("hello", "hello-native")]
                record["pass"] = (normal_exit and online and all(m in log for m in markers)
                                  and "KSB073-SAMPLES: PASS ALL" in log
                                  and "PASS SAMPLE hello:" in log
                                  and "PASS SAMPLE hello-native:" in log
                                  and not any(m in log for m in ["KSB073-SAMPLES: FAIL",
                                                                "unhandled signal", "Kernel panic"]))
            else:
                record["pass"] = (normal_exit and online
                                  and "KSB073-SAMPLES: EXIT hello cpu=3 139" in log
                                  and "KSB073-SAMPLES: FAIL hello" in log
                                  and "cause: 0000000000000005" in log)
            result["cases"].append(record)
            manifest.write_text(json.dumps(result, indent=2) + "\n")
            status = "PASS" if record["pass"] else "FAIL"
            print(f"{status} {name}/{profile}: inspect {logpath}", flush=True)
            failed |= not record["pass"]
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
