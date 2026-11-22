#!/usr/bin/env python3
"""Add K3 OP-TEE memory reservations and MPXY wiring to a QEMU DTB."""
import argparse
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

DEFAULT_DOMAIN = "optee-domain"
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


def validate_domain_memory(domains, domain, untrusted):
    region_nodes = {}
    for node in domains.children.values():
        if b"opensbi,domain,memregion" in node.props.get("compatible", b"").split(b"\0"):
            handle, = struct.unpack(">I", node.props["phandle"])
            base, = struct.unpack(">Q", node.props["base"])
            order, = struct.unpack(">I", node.props["order"])
            if not 3 <= order <= 64 or base % (1 << order):
                raise ValueError("invalid OpenSBI memregion base or order")
            region_nodes[handle] = (base, 1 << order, "mmio" in node.props)

    core_base = REGIONS[0][1]
    if domain.props.get("next-addr") != struct.pack(">Q", core_base):
        raise ValueError(f"OP-TEE entry must be {core_base:#x}")
    if domain.props.get("next-mode", b"\0\0\0\1") != struct.pack(">I", 1):
        raise ValueError("OP-TEE domain must enter S-mode")

    for instance, expected in ((domain, (0x38, 0x18)), (untrusted, (0, 0x18))):
        entries = []
        for handle, access in struct.iter_unpack(">II", instance.props.get("regions", b"")):
            base, size, mmio = region_nodes[handle]
            entries.append((base, size, mmio, access))
        for (name, start, length), access in zip(REGIONS, expected):
            exact = [(mmio, flags) for base, size, mmio, flags in entries
                     if (base, size) == (start, length)]
            if (len(exact) != 1 or exact[0][0] or exact[0][1] & 0x78 != access
                    or (access == 0 and exact[0][1] & 7)):
                raise ValueError(f"missing or invalid domain permissions for {name}")
            if any(size < length and start < base + size and base < start + length
                   for base, size, _, _ in entries):
                raise ValueError(f"nested domain region overrides {name}")


def add_mpxy(root, edit, domain_name):
    chosen = root.children["chosen"]
    domains = chosen.children["opensbi-domains"]
    if b"opensbi,domain,config" not in domains.props.get("compatible", b"").split(b"\0"):
        raise ValueError("/chosen/opensbi-domains requires opensbi,domain,config")
    if domain_name not in domains.children:
        raise ValueError(f"missing OpenSBI domain: /chosen/opensbi-domains/{domain_name}")
    domain = domains.children[domain_name]
    if (domain_name == "untrusted-domain" or
            b"opensbi,domain,instance" not in
            domain.props.get("compatible", b"").split(b"\0")):
        raise ValueError("expected a trusted OpenSBI domain instance")
    untrusted = domains.children["untrusted-domain"]
    if (b"opensbi,domain,instance" not in
            untrusted.props.get("compatible", b"").split(b"\0")):
        raise ValueError("expected an untrusted-domain instance")
    validate_domain_memory(domains, domain, untrusted)
    cpus = root.children["cpus"]
    cpu_nodes = sorted((struct.unpack(">I", node.props["reg"])[0], name, node)
                       for name, node in cpus.children.items()
                       if node.props.get("device_type") == b"cpu\0")
    if ([hart for hart, _, _ in cpu_nodes] != list(range(16)) or
            any(node.props.get("status", b"okay\0") not in (b"okay\0", b"ok\0")
                for _, _, node in cpu_nodes)):
        raise ValueError("MPXY layout requires enabled harts 0 through 15")
    untrusted_handle, = struct.unpack(">I", untrusted.props["phandle"])
    if not untrusted_handle:
        raise ValueError("invalid untrusted-domain phandle")
    assignment = struct.pack(">I", untrusted_handle)
    if any(node.props.get("opensbi-domain", assignment) != assignment
           for _, _, node in cpu_nodes):
        raise ValueError("conflicting OpenSBI hart assignment")
    if "boot-hart" in domain.props:
        raise ValueError("OP-TEE domain must not boot a hart independently")
    cpu_handles = [struct.unpack(">I", node.props["phandle"])[0]
                   for _, _, node in cpu_nodes]
    if not all(cpu_handles):
        raise ValueError("invalid CPU phandle")

    handles = set()
    channel_ids = tuple(range(0x1000, 0x1010))

    def scan(node):
        interfaces = node.props.get("compatible", b"").split(b"\0")
        if set(interfaces).intersection(
                (b"riscv,sbi-mpxy-opteed", b"riscv,sbi-mpxy-mbox",
                 b"linaro,optee-tz")):
            raise ValueError("input already contains an OP-TEE or MPXY node")
        node_handles = {struct.unpack(">I", node.props[prop])[0]
                        for prop in ("phandle", "linux,phandle")
                        if prop in node.props}
        if handles & node_handles or len(node_handles) > 1:
            raise ValueError("conflicting DT phandles")
        handles.update(node_handles)
        ids = node.props.get("riscv,sbi-mpxy-channel-id", b"")
        if any(channel in channel_ids for (channel,) in struct.iter_unpack(">I", ids)):
            raise ValueError("input already uses a K3 OP-TEE MPXY channel ID")
        for child in node.children.values():
            scan(child)

    scan(root)
    trusted_handle = struct.unpack(">I", domain.props["phandle"])[0]
    mailbox_handle = max(handles) + 1
    if not trusted_handle or mailbox_handle >= 0xffffffff:
        raise ValueError("invalid domain phandle or exhausted phandle space")

    def new_node(path, compatible):
        edit(["-c"], path)
        edit(["-t", "s"], path, "compatible", compatible)

    for _, name, _ in cpu_nodes:
        edit(["-t", "x"], f"/cpus/{name}", "opensbi-domain",
             f"{untrusted_handle:x}")
    for name in (domain_name, "untrusted-domain"):
        edit(["-t", "x"], f"/chosen/opensbi-domains/{name}", "possible-harts",
             *(f"{handle:x}" for handle in cpu_handles))

    opteed = "/chosen/sbi-mpxy-opteed"
    new_node(opteed, "riscv,sbi-mpxy-opteed")
    edit(["-t", "x"], opteed, "opensbi-domain-instance", f"{trusted_handle:x}")
    edit(["-t", "x"], opteed, "riscv,sbi-mpxy-channel-id",
         *(f"{channel:x}" for channel in channel_ids))

    if "firmware" not in root.children:
        edit(["-c"], "/firmware")
    mailbox = "/firmware/sbi-mpxy-mailbox"
    new_node(mailbox, "riscv,sbi-mpxy-mbox")
    edit(["-t", "x"], mailbox, "phandle", f"{mailbox_handle:x}")
    edit(["-t", "x"], mailbox, "#mbox-cells", "2")
    optee = "/firmware/optee"
    new_node(optee, "linaro,optee-tz")
    edit(["-t", "s"], optee, "method", "smc")
    edit(["-t", "x"], optee, "mboxes",
         *(cell for channel in channel_ids
           for cell in (f"{mailbox_handle:x}", f"{channel:x}", "2")))


def prepare(source, output, domain_name=DEFAULT_DOMAIN):
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
        add_mpxy(root, edit, domain_name)
        os.link(staged, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mpxy-domain", metavar="NAME", default=DEFAULT_DOMAIN,
                        help=f"trusted OpenSBI domain name (default: {DEFAULT_DOMAIN})")
    args = parser.parse_args()
    try:
        prepare(args.input, args.output, args.mpxy_domain)
    except (OSError, ValueError, KeyError, struct.error,
            subprocess.CalledProcessError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")


if __name__ == "__main__":
    main()
