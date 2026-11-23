#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 2 ]]; then
    echo "Usage: $0 BASE_INITRAMFS_LIST OUTPUT_DIRECTORY" >&2
    echo 'Set QEMU, SBI, IMAGE, DTB, OPTEE_ELF, GEN_INIT_CPIO and CROSS_COMPILE.' >&2
    exit 2
fi
: "${QEMU:?}" "${SBI:?}" "${IMAGE:?}" "${DTB:?}" "${OPTEE_ELF:?}"
: "${GEN_INIT_CPIO:?}" "${CROSS_COMPILE:?}"

base=$(realpath "$1")
out=$(realpath -m "$2")
mkdir "$out"
src=$(dirname "$(realpath "$0")")
"${CROSS_COMPILE}gcc" -static -O2 -Wall -Wextra -Werror \
    "$src/jupiter2-ftpm-nv.c" -o "$out/init"
# Reuse the fTPM smoke test manifest and replace its guest init.
awk '$1 != "file" || $2 != "/init"' "$base" > "$out/base.list"
printf 'file /init %s 0755 0 0\n' "$out/init" >> "$out/base.list"

boot()
{
    local mode=$1
    local manifest=$2
    local log="$out/$mode.log"

    "$GEN_INIT_CPIO" "$manifest" > "$out/init.cpio"
    timeout 180 "$QEMU" -accel tcg,thread=multi \
        -M jupiter2,wtm-rng=on \
        -cpu rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16 \
        -smp 16 -m 2G -display none -monitor none -serial stdio \
        -dtb "$DTB" -bios "$SBI" -kernel "$IMAGE" -initrd "$out/init.cpio" \
        -append "console=ttyS0,115200 earlycon=sbi keep_bootcon printk.devkmsg=on rdinit=/init cma=512M@4G-16G -- $mode" \
        -device "loader,file=$OPTEE_ELF" > "$log" 2>&1
    grep -F 'smp: Brought up 1 node, 16 CPUs' "$log"
    grep -F "NV_RESULT $mode PASS" "$log"
    grep -F 'reboot: Power down' "$log"
}

boot seed "$out/base.list"

# Restore only the named REE FS files emitted by the test guest.
cp "$out/base.list" "$out/read.list"
python3 - "$out" <<'PY'
from pathlib import Path
import hashlib
import re
import sys

out = Path(sys.argv[1])
store = out / "ree-fs"
store.mkdir()
files = {}
name = None
reported = None
for line in (out / "seed.log").read_text(errors="replace").splitlines():
    if line.startswith("NV_FILE "):
        candidate = line.removeprefix("NV_FILE ")
        if name is not None or candidate in files or not re.fullmatch(
            r"dirf\.db|[0-9a-f]+", candidate
        ):
            raise SystemExit(f"Invalid REE FS file marker: {line}")
        name = candidate
        files[name] = bytearray()
    elif line.startswith("NV_HEX "):
        if name is None:
            raise SystemExit("Unexpected REE FS data")
        files[name].extend(bytes.fromhex(line.removeprefix("NV_HEX ")))
    elif line == "NV_END":
        if name is None:
            raise SystemExit("Unexpected REE FS end marker")
        name = None
    elif line.startswith("NV_EXPORT files="):
        reported = int(line.removeprefix("NV_EXPORT files="))
if name is not None or reported != len(files) or "dirf.db" not in files:
    raise SystemExit("Incomplete REE FS export")
with (out / "read.list").open("a") as manifest:
    for name, data in sorted(files.items()):
        path = store / name
        path.write_bytes(data)
        manifest.write(f"file /var/lib/tee/{name} {path} 0600 0 0\n")
        print(f"{hashlib.sha256(data).hexdigest()}  {name}")
PY

boot read "$out/read.list"
boot empty "$out/base.list"
