"""Copy QEMU UART to a log and display test milestones and elapsed time."""
import os
from pathlib import Path
import re
import select
import sys
import time

MILESTONE = re.compile(
    rb'OpenSBI v|Linux version |smp: Brought up|optee: initialized driver|'
    rb'QEMU fTPM preparation status=|No TPM chip found|Run /init as init process|'
    rb'IMA_(?:PCR_BEFORE|PCR_AFTER|MEASUREMENT|GUEST_RESULT)[ =]|'
    rb'reboot: Power down|Kernel panic|^qemu-system[^:]*:',
)


def main():
    mode, log_path = sys.argv[1:]
    start = time.monotonic()
    next_report = start + 10
    fd = sys.stdin.fileno()
    pending = b''
    with Path(log_path).open('wb') as log:
        while True:
            ready, _, _ = select.select([fd], [], [], max(0, next_report - time.monotonic()))
            if ready:
                chunk = os.read(fd, 65536)
                if not chunk:
                    if pending and MILESTONE.search(pending):
                        print(f'[{mode}] {pending.decode(errors="replace").strip()}', flush=True)
                    return
                log.write(chunk)
                log.flush()
                *lines, pending = (pending + chunk).split(b'\n')
                for line in lines:
                    if MILESTONE.search(line):
                        print(f'[{mode}] {line.decode(errors="replace").strip()}', flush=True)
            now = time.monotonic()
            if now >= next_report:
                print(f'[{mode}] QEMU running for {int(now - start)}s; UART: {log_path}', flush=True)
                next_report = now + 10


if __name__ == '__main__':
    main()
