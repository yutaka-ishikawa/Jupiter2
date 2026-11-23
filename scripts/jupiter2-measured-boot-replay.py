#!/usr/bin/env python3
"""Replay the initial Jupiter2 SHA-256 measured-boot event log from zero PCRs."""

import argparse
import hashlib
import json
from pathlib import Path
import struct


def take(data, offset, layout):
    end = offset + struct.calcsize(layout)
    if end > len(data):
        raise ValueError(f"truncated record at byte {offset}")
    return struct.unpack_from(layout, data, offset), end


def replay(data):
    (pcr, event_type, digest, length), offset = take(data, 0, "<II20sI")
    if (pcr, event_type, digest) != (0, 3, bytes(20)):
        raise ValueError("expected the Spec ID EV_NO_ACTION header")
    end = offset + length
    if end > len(data):
        raise ValueError("truncated Spec ID payload")
    header = data[offset:end]
    (signature, _, _, major, _, uintn, count), pos = take(header, 0, "<16sIBBBBI")
    if signature != b"Spec ID Event03\0" or major != 2 or uintn != 2 or count != 1:
        raise ValueError("unsupported Spec ID profile")
    (algorithm, size, vendor_size), pos = take(header, pos, "<HHB")
    if (algorithm, size) != (0x000B, 32) or pos + vendor_size != len(header):
        raise ValueError("invalid SHA-256 algorithm table or vendor size")

    events = []
    pcrs = {0: bytes(32), 1: bytes(32)}
    offset = end
    while offset < len(data):
        (pcr, event_type, count), offset = take(data, offset, "<III")
        if pcr not in pcrs or event_type == 3 or count != 1:
            raise ValueError("event outside the initial Jupiter2 profile")
        (algorithm, digest, length), offset = take(data, offset, "<H32sI")
        end = offset + length
        if algorithm != 0x000B or end > len(data):
            raise ValueError("invalid SHA-256 event digest or data length")
        pcrs[pcr] = hashlib.sha256(pcrs[pcr] + digest).digest()
        events.append({
            "pcr": pcr,
            "type": event_type,
            "sha256": digest.hex(),
            "event_data_hex": data[offset:end].hex(),
        })
        offset = end

    if not events:
        raise ValueError("no measurement events")
    return {"events": events, "pcrs": {pcr: value.hex() for pcr, value in pcrs.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    try:
        result = replay(args.log.read_bytes())
    except (OSError, ValueError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
