#!/usr/bin/env python3
"""実QEMUのPMPプロファイルをQMPで確認する開発PC用試験。

目的: CPU realize後の全16 CPUのPMP個数・粒度を調べ、混在設定の配線を検査する。
CPU/SBI/CSRをモックしない。guestは停止したままであり、OpenSBI/SMの動作や
Enclave隔離を証明する試験ではない。guest内run-allと実機試験は別途必要。
"""
import argparse
import json
import selectors
import subprocess


def check(qemu, mixed):
    machine = "jupiter2,mixed-pmp=" + ("on" if mixed else "off")
    command = [qemu, "-accel", "tcg", "-M", machine, "-smp", "16", "-m", "256M",
               "-cpu", "rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16",
               "-bios", "none", "-S", "-display", "none", "-serial", "none",
               "-monitor", "none", "-qmp", "stdio"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, bufsize=0)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)

    def receive():
        if not selector.select(timeout=20):
            raise RuntimeError("QMP response timeout")
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("QEMU exited before QMP response")
        return json.loads(line)

    def execute(name, arguments=None):
        request = {"execute": name}
        if arguments is not None:
            request["arguments"] = arguments
        process.stdin.write((json.dumps(request) + "\n").encode())
        process.stdin.flush()
        while True:
            response = receive()
            if "event" in response:
                continue
            if "error" in response:
                raise RuntimeError(str(response["error"]))
            return response["return"]

    try:
        if "QMP" not in receive():
            raise RuntimeError("missing QMP greeting")
        execute("qmp_capabilities")
        cpus = execute("query-cpus-fast")
        if {cpu["cpu-index"] for cpu in cpus} != set(range(16)):
            raise RuntimeError("expected CPU indices 0-15")
        for cpu in cpus:
            index = cpu["cpu-index"]
            properties = {}
            for prop in ("num-pmp-regions", "pmp-granularity"):
                properties[prop] = execute("qom-get", {"path": cpu["qom-path"],
                                                      "property": prop})
            expected = {"num-pmp-regions": 32 if mixed and index >= 8 else 16,
                        "pmp-granularity": 4096 if mixed else 16}
            if properties != expected:
                raise RuntimeError(f"CPU{index}: {properties}, expected {expected}")
        print(f"PASS QEMU realized configuration: {machine}, 16 CPUs")
        execute("quit")
        process.wait(timeout=10)
        if process.returncode:
            raise RuntimeError(f"QEMU exit code {process.returncode}")
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
        _, stderr = process.communicate(timeout=10)
        if process.returncode:
            print(stderr.decode(errors="replace").strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, help="rebuilt qemu-system-riscv64")
    args = parser.parse_args()
    for mixed in (False, True):
        check(args.qemu, mixed)


if __name__ == "__main__":
    main()
