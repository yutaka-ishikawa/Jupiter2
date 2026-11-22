#!/usr/bin/env python3
"""Reserve the default K3 OP-TEE Core and static shared memory in a QEMU DTB."""
import argparse
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import tempfile

REGIONS = (("optee", 0x171000000, 0x1000000),
           ("optee-shm", 0x172000000, 0x1000000))


def read_tree(data):
    path = Path(__file__).with_name("prepare-jupiter2-keystone-linux-dtb.py")
    spec = importlib.util.spec_from_file_location("jupiter2_linux_dtb", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    fit = helper.load_fit_parser()
    root, _ = fit.parse_fdt(data)
    return root, helper.fdt_metadata(data)[1]


def ranges(node):
    reg = node.props["reg"]
    if not reg or len(reg) % 16:
        raise ValueError("invalid 64-bit reg property")
    return list(struct.iter_unpack(">QQ", reg))


def prepare(source, output):
    data = source.read_bytes()
    root, occupied = read_tree(data)
    cells = struct.pack(">I", 2)
    reserved = root.children.get("reserved-memory")
    if (root.props.get("#address-cells") != cells or
            root.props.get("#size-cells") != cells):
        raise ValueError("expected two address and size cells at the root")
    if reserved is not None:
        if (reserved.props.get("#address-cells") != cells or
                reserved.props.get("#size-cells") != cells or
                reserved.props.get("ranges") != b""):
            raise ValueError("expected identity-mapped 64-bit reserved-memory")
        for node in reserved.children.values():
            if "reg" in node.props:
                occupied.extend(ranges(node))
    ram = [region for node in root.children.values()
           if node.props.get("device_type") == b"memory\0"
           for region in ranges(node)]
    for _, start, size in REGIONS:
        if not any(base <= start and start + size <= base + length
                   for base, length in ram):
            raise ValueError(f"OP-TEE range at {start:#x} is outside RAM")
        if any(length and start < base + length and base < start + size
               for base, length in occupied):
            raise ValueError(f"OP-TEE range at {start:#x} overlaps a reservation")

    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        staged = Path(temp) / "boot.dtb"
        staged.write_bytes(data)

        def edit(options, *args):
            subprocess.run(["fdtput", *options, str(staged), *args], check=True)

        if reserved is None:
            edit(["-c"], "/reserved-memory")
            for prop in ("#address-cells", "#size-cells"):
                edit(["-t", "x"], "/reserved-memory", prop, "2")
            edit([], "/reserved-memory", "ranges")
        for name, start, size in REGIONS:
            path = f"/reserved-memory/{name}@{start:x}"
            edit(["-c"], path)
            edit(["-t", "x"], path, "reg", f"{start >> 32:x}",
                 f"{start & 0xffffffff:x}", "0", f"{size:x}")
            edit([], path, "no-map")
        os.link(staged, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        prepare(args.input, args.output)
    except (OSError, ValueError, KeyError, struct.error,
            subprocess.CalledProcessError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")


if __name__ == "__main__":
    main()
