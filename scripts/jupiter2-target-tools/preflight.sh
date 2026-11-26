#!/usr/bin/env bash
# Read-only prerequisite checks; run on the target, not the cross-build PC.
set -Eeuo pipefail
bundle=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ $(uname -m) == riscv64 ]] || { echo 'Run this on the Milk-V riscv64 board.' >&2; exit 2; }
missing=0
for command in python3 sha256sum cp install uname df modinfo modprobe depmod; do
    if ! command -v "$command" >/dev/null; then
        echo "MISSING: $command" >&2
        missing=1
    fi
done
((missing == 0)) || exit 2
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer required"'
bash "$bundle/tools/verify.sh"
python3 "$bundle/tools/check-capacity.py" --image "$bundle/firmware/fw_dynamic.itb"
printf '\nOS release and filesystem space:\n'
uname -r
df -h /boot /lib/modules /opt
command -v update-initramfs >/dev/null || echo 'NOTE: prepare initramfs with your OS tools.'
command -v flashcp >/dev/null || echo 'NOTE: NOR programming separately requires native mtd-utils (flashcp).'
echo 'Preflight checks completed; boot source, load addresses, PMP and compatibility still require review.'
