#!/usr/bin/env bash
set -euo pipefail

TESTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$TESTS/../.." && pwd -P)"
WORK="$ROOT/.build-k3/ftpm-test"
OPTEE_OUT="$ROOT/.build-k3/optee-coexist/out"
LINUX_OUT="$(realpath -m "${LINUX_OUT:-$ROOT/.build-k3/ftpm-ima-linux}")"
CROSS_COMPILE="${CROSS_COMPILE:-riscv64-linux-gnu-}"
JOBS="${JOBS:-20}"
LINUX_TREE="$(git -C "$ROOT" rev-parse HEAD:linux-k3)"
IMA_TREE="$ROOT/.build-k3/ftpm-ima-source/$LINUX_TREE"
PATCH="$TESTS/jupiter2-ftpm-ima-kernel.patch"

checkout_source() {
    local directory="$1" repository="$2" revision="$3"
    if [[ ! -e "$directory" ]]; then
        git clone "$repository" "$directory"
        git -C "$directory" checkout --detach "$revision"
    fi
    if [[ "$(git -C "$directory" rev-parse --verify HEAD)" != "$revision" ]]; then
        printf 'Expected source commit %s at %s\n' "$revision" "$directory" >&2
        return 1
    fi
}

mkdir -p "$WORK" "$LINUX_OUT" "$(dirname "$IMA_TREE")"
checkout_source "$WORK/ftpm-src" https://github.com/OP-TEE/optee_ftpm.git \
    6f99e783eb9bb57c314a881433d4ec970de87959
checkout_source "$WORK/ms-tpm" https://github.com/microsoft/ms-tpm-20-ref.git \
    98b60a44aba79b15fcce1c0d1e46cf5918400f6a
checkout_source "$WORK/client-src" https://github.com/OP-TEE/optee_client.git \
    9f4414f62dfc5692fd39f760515ce2d344d07b6d

make -C "$WORK/ftpm-src" -j"$JOBS" O="$WORK/ta" \
    TA_DEV_KIT_DIR="$OPTEE_OUT/export-ta_rv64" CROSS_COMPILE="$CROSS_COMPILE" \
    CFG_MS_TPM_20_REF="$WORK/ms-tpm" CPPFLAGS=-DRADIX_BITS=64
make -C "$WORK/client-src/libteec" -j"$JOBS" OO="$WORK/client" \
    CROSS_COMPILE="$CROSS_COMPILE" CC="${CROSS_COMPILE}gcc" AR="${CROSS_COMPILE}ar"
make -C "$WORK/client-src/tee-supplicant" -j"$JOBS" OO="$WORK/client" \
    CROSS_COMPILE="$CROSS_COMPILE" CC="${CROSS_COMPILE}gcc" LDFLAGS=-static \
    CFG_TEE_SUPP_PLUGINS=n RPMB_EMU=0

if [[ ! -d "$IMA_TREE/linux-k3" ]]; then
    git -C "$ROOT" worktree add --detach --no-checkout "$IMA_TREE" HEAD
    git -C "$IMA_TREE" sparse-checkout set linux-k3
    git -C "$IMA_TREE" checkout --detach HEAD
fi
if ! git -C "$IMA_TREE" apply --reverse --check "$PATCH" 2>/dev/null; then
    git -C "$IMA_TREE" apply "$PATCH"
fi

cp "$TESTS/jupiter2-ftpm-ima.config" "$LINUX_OUT/.config"
make -C "$IMA_TREE/linux-k3" O="$LINUX_OUT" ARCH=riscv \
    CROSS_COMPILE="$CROSS_COMPILE" olddefconfig
make -C "$IMA_TREE/linux-k3" O="$LINUX_OUT" ARCH=riscv \
    CROSS_COMPILE="$CROSS_COMPILE" -j"$JOBS" Image modules
"${CROSS_COMPILE}gcc" -static -O2 -Wall -Wextra -Werror \
    -o "$LINUX_OUT/ftpm-ima-init" "$TESTS/jupiter2-ftpm-ima.c"
