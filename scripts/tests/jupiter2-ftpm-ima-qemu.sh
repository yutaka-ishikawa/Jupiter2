#!/usr/bin/env bash
set -euo pipefail

TESTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$TESTS/../.." && pwd -P)"
PREFIX="${PREFIX:-$ROOT/install/keystone}"
OUT="${OUT:-$ROOT/.build-k3/ftpm-ima}"
LINUX_OUT="${LINUX_OUT:-$ROOT/.build-k3/ftpm-ima-linux}"
QEMU="${QEMU:-$PREFIX/bin/qemu-system-riscv64}"
SBI="${SBI:-$PREFIX/firmware/k3/fw_dynamic.bin}"
BOOT_DTB="${BOOT_DTB:-$ROOT/.build-k3/optee-coexist/boot.dtb}"
TEE_ELF="${TEE_ELF:-$ROOT/.build-k3/optee-coexist/out/core/tee.elf}"
UUID=bc50d971-d4c9-42c4-82cb-343fb7f37896
FTPM_TA="${FTPM_TA:-$ROOT/.build-k3/ftpm-test/ta/$UUID.ta}"
TEE_SUPPLICANT="${TEE_SUPPLICANT:-$ROOT/.build-k3/ftpm-test/client/tee-supplicant/tee-supplicant}"
IMAGE="$LINUX_OUT/arch/riscv/boot/Image"
MODULE="$LINUX_OUT/drivers/char/tpm/tpm_ftpm_tee.ko"
INIT="$LINUX_OUT/ftpm-ima-init"
for input in "$IMAGE" "$MODULE" "$INIT" "$LINUX_OUT/usr/gen_init_cpio" "$QEMU" "$TEE_ELF" "$SBI" "$BOOT_DTB" "$FTPM_TA" "$TEE_SUPPLICANT"; do
    test -s "$input" || { printf 'Missing test input: %s\n' "$input" >&2; exit 1; }
done

mkdir -p "$OUT"
OUT="$(realpath "$OUT")"
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
file /init $INIT 0755 0 0
file /tpm_ftpm_tee.ko $MODULE 0644 0 0
dir /sys 0755 0 0
dir /sys/kernel 0755 0 0
dir /sys/kernel/security 0755 0 0
slink /ima-ftpm-prepare /init 0755 0 0
file /ima-probe $OUT/probe 0644 0 0
LIST
"$LINUX_OUT/usr/gen_init_cpio" "$OUT/init.list" > "$OUT/init.cpio"

bootargs='console=ttyS0,115200 earlycon=sbi keep_bootcon printk.devkmsg=on rdinit=/init cma=512M@4G-16G ima_hash=sha256'
timeout_seconds="${TIMEOUT:-180}"
sstc="${SSTC:-on}"
case "$sstc" in
    on|off) ;;
    *) printf 'Invalid SSTC value: %s (expected on or off)\n' "$sstc" >&2; exit 2 ;;
esac
for mode in early late; do
    case "$mode" in
        early) args="$bootargs ima_test_ftpm=1" ;;
        late) args="$bootargs -- late" ;;
    esac
    # Supply fresh entropy for the test guest's early userspace helper.
    # QEMU's custom DTB path does not add a missing rng-seed property.
    test_dtb="$OUT/$mode.dtb"
    cp -- "$BOOT_DTB" "$test_dtb"
    read -r -a seed_cells <<< "$(od -An -v -tx4 -N32 -w32 /dev/urandom)"
    fdtput -t x "$test_dtb" /chosen rng-seed "${seed_cells[@]}"
    log="$OUT/$mode.log"
    started=$SECONDS
    printf 'Running %s fTPM registration (timeout %ss), UART: %s\n' "$mode" "$timeout_seconds" "$log"
    if timeout "$timeout_seconds" "$QEMU" -accel tcg,thread=multi \
        -M jupiter2,wtm-rng=on \
        -cpu "rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16,sstc=$sstc" \
        -smp 16 -m 2G -display none -monitor none -serial stdio \
        -dtb "$test_dtb" -bios "$SBI" -kernel "$IMAGE" \
        -initrd "$OUT/init.cpio" -append "$args" \
        -device "loader,file=${TEE_ELF//,/,,}" 2>&1 |
        python3 "$TESTS/jupiter2-ftpm-ima-progress.py" "$mode" "$log"; then
        printf '[%s] QEMU finished in %ss\n' "$mode" "$((SECONDS - started))"
    else
        status=$?
        printf '[%s] QEMU/logging failed after %ss (exit %s); UART: %s\n' \
            "$mode" "$((SECONDS - started))" "$status" "$log" >&2
        exit "$status"
    fi
    python3 "$TESTS/jupiter2-ftpm-ima-verify.py" "$mode" "$log" "$OUT/probe"
done
