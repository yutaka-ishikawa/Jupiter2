"""Check a Jupiter2 guest's IMA measurement and observed TPM PCR extension."""
import argparse
import hashlib
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('early', 'late'))
    parser.add_argument('uart', type=Path)
    parser.add_argument('probe', type=Path)
    args = parser.parse_args()
    text = args.uart.read_text(errors='replace')
    markers = ['smp: Brought up 1 node, 16 CPUs', 'IMA_GUEST_RESULT=0', 'reboot: Power down']
    markers.append('No TPM chip found' if args.mode == 'late' else 'QEMU fTPM preparation status=0')
    for marker in markers:
        if marker not in text:
            parser.exit(1, f'Missing UART marker: {marker}\n')

    before = re.findall(r'IMA_PCR_BEFORE ([0-9a-f]{64})', text)
    after = re.findall(r'IMA_PCR_AFTER ([0-9a-f]{64})', text)
    digest_length = 40 if args.mode == 'late' else 64
    events = re.findall(
        rf'IMA_MEASUREMENT 10 ([0-9a-f]{{{digest_length}}}) ima-ng sha256:([0-9a-f]{{64}}) /ima-probe\b',
        text,
    )
    if not (len(before) == len(after) == len(events) == 1):
        parser.exit(1, 'Expected one PCR reading before and after one IMA measurement\n')

    template, measured = events[0]
    if measured != hashlib.sha256(args.probe.read_bytes()).hexdigest():
        parser.exit(1, 'IMA file digest differs from the test file digest\n')
    if args.mode == 'late':
        if before != after:
            parser.exit(1, 'Late fTPM registration unexpectedly extended PCR 10\n')
        print('PASS: late fTPM registration leaves PCR 10 unchanged')
    else:
        expected = hashlib.sha256(bytes.fromhex(before[0] + template)).hexdigest()
        if before == after or after[0] != expected:
            parser.exit(1, 'fTPM PCR 10 does not match the IMA SHA-256 extension\n')
        print('PASS: IMA SHA-256 extension matches fTPM PCR 10')


if __name__ == '__main__':
    main()
