#!/usr/bin/env bash
set -euo pipefail

TESTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$TESTS/../.." && pwd -P)"
CROSS_COMPILE="${CROSS_COMPILE:-riscv64-linux-gnu-}"
OUT="${OUT:-$ROOT/.build-k3/ftpm-ima}"
: "${LINUX_OUT:?Set LINUX_OUT to the IMA test kernel build directory}"
: "${QEMU:?Set QEMU to the Jupiter2 QEMU executable}"
: "${SBI:?Set SBI to fw_dynamic.bin}"
: "${BOOT_DTB:?Set BOOT_DTB to the OP-TEE-first QEMU DTB}"
: "${TEE_ELF:?Set TEE_ELF to the K3 OP-TEE Core ELF}"
: "${FTPM_TA:?Set FTPM_TA to the signed fTPM TA}"
: "${TEE_SUPPLICANT:?Set TEE_SUPPLICANT to the static RV64 tee-supplicant}"
UUID=bc50d971-d4c9-42c4-82cb-343fb7f37896
IMAGE="$LINUX_OUT/arch/riscv/boot/Image"
MODULE="$LINUX_OUT/drivers/char/tpm/tpm_ftpm_tee.ko"
for input in "$IMAGE" "$MODULE" "$TEE_ELF" "$SBI" "$BOOT_DTB" "$FTPM_TA" "$TEE_SUPPLICANT"; do
    test -s "$input" || { printf 'Missing test input: %s\n' "$input" >&2; exit 1; }
done

mkdir -p "$OUT"
OUT="$(realpath "$OUT")"
"${CROSS_COMPILE}gcc" -static -O2 -Wall -Wextra -Werror \
    -o "$OUT/init" "$TESTS/jupiter2-ftpm-ima.c"
printf 'Jupiter2 fTPM IMA test probe\n' > "$OUT/probe"
cat > "$OUT/init.list" <<LIST
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
dir /lib 0755 0 0
dir /lib/optee_armtz 0755 0 0
dir /var 0755 0 0
dir /var/lib 0755 0 0
dir /var/lib/tee 0700 0 0
file /lib/optee_armtz/$UUID.ta $FTPM_TA 0644 0 0
file /tee-supplicant $TEE_SUPPLICANT 0755 0 0
file /init $OUT/init 0755 0 0
file /tpm_ftpm_tee.ko $MODULE 0644 0 0
dir /sys 0755 0 0
dir /sys/kernel 0755 0 0
dir /sys/kernel/security 0755 0 0
slink /ima-ftpm-prepare /init 0755 0 0
file /ima-probe $OUT/probe 0644 0 0
LIST
"$LINUX_OUT/usr/gen_init_cpio" "$OUT/init.list" > "$OUT/init.cpio"

bootargs='console=ttyS0,115200 earlycon=sbi keep_bootcon printk.devkmsg=on rdinit=/init cma=512M@4G-16G ima_hash=sha256'
for mode in early late; do
    case "$mode" in
        early) args="$bootargs ima_test_ftpm=1" ;;
        late) args="$bootargs -- late" ;;
    esac
    log="$OUT/$mode.log"
    printf 'Running %s fTPM registration, UART: %s\n' "$mode" "$log"
    timeout "${TIMEOUT:-180}" "$QEMU" -accel tcg,thread=multi \
        -M jupiter2,wtm-rng=on \
        -cpu rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16 \
        -smp 16 -m 2G -display none -monitor none -serial stdio \
        -dtb "$BOOT_DTB" -bios "$SBI" -kernel "$IMAGE" \
        -initrd "$OUT/init.cpio" -append "$args" \
        -device "loader,file=${TEE_ELF//,/,,}" > "$log" 2>&1
    python3 "$TESTS/jupiter2-ftpm-ima-verify.py" "$mode" "$log" "$OUT/probe"
done
