#!/usr/bin/env bash
# Build the Keystone OpenSBI and assemble the matching FSBL and RAM-boot FIT.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ $# != 1 || $1 == --help || $1 == -h ]]; then
    echo 'Usage: bash scripts/build-jupiter2-ram-boot.sh OUTPUT_DIR'
    echo 'Overrides: CROSS_COMPILE, JOBS, K3_BUILD_DIR, ESOS_ITB, ESOS_CONFIGURATION, FASTBOOT_LOG'
    if [[ ${1:-} == --help || ${1:-} == -h ]]; then
        exit 0
    fi
    exit 2
fi
OUT="$(realpath -m -- "$1")"
K3_BUILD_DIR="$(realpath -m -- "${K3_BUILD_DIR:-$ROOT/.build-k3}")"
ESOS_ITB="$(realpath -e -- "${ESOS_ITB:-$ROOT/hardware/jupiter2/vendor/esos.itb}")"
CROSS_COMPILE="${CROSS_COMPILE:-riscv64-unknown-linux-gnu-}"
JOBS="${JOBS:-$(nproc)}"
ESOS_CONFIGURATION="${ESOS_CONFIGURATION:-conf_dual}"
if [[ -e "$OUT" || -L "$OUT" ]]; then
    printf 'Output already exists: %s\n' "$OUT" >&2
    exit 1
fi

limits=()
if [[ -n ${FASTBOOT_LOG:-} ]]; then
    limits=(--fastboot-log "$(realpath -e -- "$FASTBOOT_LOG")")
fi

make -C "$ROOT" firmware CROSS_COMPILE="$CROSS_COMPILE" JOBS="$JOBS" K3_BUILD_DIR="$K3_BUILD_DIR"
FW="$K3_BUILD_DIR/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic"
exec python3 "$ROOT/scripts/build-jupiter2-reference-ram-boot.py" \
    --opensbi-bin "$FW.bin" --opensbi-elf "$FW.elf" \
    --esos-itb "$ESOS_ITB" --esos-configuration "$ESOS_CONFIGURATION" \
    --variant keystone --cross-compile "$CROSS_COMPILE" --jobs "$JOBS" \
    "${limits[@]}" --output "$OUT"
