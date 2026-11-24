#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
WORK="$ROOT/.build-k3/optee-coexist"
CROSS="${CROSS_COMPILE:-riscv64-linux-gnu-}"
JOBS="${JOBS:-20}"
CLIENT_DEFAULT="$WORK/client/usr"
OPTEE_CLIENT_OUT="${OPTEE_CLIENT_OUT:-$CLIENT_DEFAULT}"
OPTEE="$WORK/optee_os"
OUT="$WORK/out"
VERIFY="$ROOT/verifications/optee-coexistence"
UUID=c25c295d-8af1-44f7-9f0e-657c39bc22ad
OPTEE_COMMIT=2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59
OPTEE_PATCH="$ROOT/patches/optee/k3-map-efuse-clock-registers.patch"

python3 -c 'from elftools.elf.elffile import ELFFile'
mkdir -p "$WORK"

if [[ ! -e "$OPTEE" ]]; then
  git clone https://github.com/spacemit-com/optee_os.git "$OPTEE"
  git -C "$OPTEE" checkout --detach "$OPTEE_COMMIT"
fi

if [[ ! -e "$OPTEE/.git" ]] ||
   [[ "$(git -C "$OPTEE" rev-parse --verify HEAD)" != "$OPTEE_COMMIT" ]]; then
  printf 'OP-TEE作業ツリーのコミットを確認してください (%s): %s\n' \
    "$OPTEE_COMMIT" "$OPTEE" >&2
  exit 1
fi

if git -C "$OPTEE" apply --reverse --check "$OPTEE_PATCH" 2>/dev/null; then
  printf 'eFuseパッチは適用済みです。\n'
else
  git -C "$OPTEE" apply "$OPTEE_PATCH"
fi

OPTEE_ARGS=(
  O="$OUT" PLATFORM=k3 ARCH=riscv
  CROSS_COMPILE="$CROSS"
  CROSS_COMPILE_core="$CROSS"
  CROSS_COMPILE_ta_rv64="$CROSS"
  CFG_TEE_CORE_NB_CORE=16 CFG_NUM_THREADS=16
  CFG_K3_EFUSE=y CFG_K3_HUK_ALLOW_UNFUSED=y
  CFG_K3_IOPMP=n CFG_K3_PRNG=n
  CFG_MMP_RTC=n CFG_TE200_CRYPTO_DRIVER=n
  CFG_REE_FS=y CFG_REE_FS_TA=y CFG_RPMB_FS=n
)

make -C "$OPTEE" -j"$JOBS" "${OPTEE_ARGS[@]}"
make -C "$VERIFY" -j"$JOBS" ta CROSS_COMPILE="$CROSS" \
  TA_DEV_KIT_DIR="$OUT/export-ta_rv64"
make -C "$OPTEE" -j"$JOBS" "${OPTEE_ARGS[@]}" CFG_EARLY_TA=y \
  EARLY_TA_PATHS="$VERIFY/build/ta/$UUID.stripped.elf"

test -s "$OUT/core/tee.elf"
if [[ ! -s "$OPTEE_CLIENT_OUT/lib/libteec.a" ||
      ! -s "$OPTEE_CLIENT_OUT/include/tee_client_api.h" ]]; then
  if [[ "$(realpath -m "$OPTEE_CLIENT_OUT")" != "$(realpath -m "$CLIENT_DEFAULT")" ]]; then
    printf 'Missing RV64 libteec.a or tee_client_api.h in %s\n' "$OPTEE_CLIENT_OUT" >&2
    exit 1
  fi
  client_source="$WORK/optee_client"
  client_commit=9f4414f62dfc5692fd39f760515ce2d344d07b6d
  if [[ ! -e "$client_source" ]]; then
    git clone https://github.com/OP-TEE/optee_client.git "$client_source"
    git -C "$client_source" checkout --detach "$client_commit"
  fi
  if [[ "$(git -C "$client_source" rev-parse --verify HEAD)" != "$client_commit" ]]; then
    printf 'OP-TEE client checkout must be at %s: %s\n' "$client_commit" "$client_source" >&2
    exit 1
  fi
  make -C "$client_source" -j"$JOBS" CROSS_COMPILE="$CROSS" \
    O="$WORK/client-build" build-libteec
  mkdir -p "$OPTEE_CLIENT_OUT/include" "$OPTEE_CLIENT_OUT/lib"
  install -m 0644 "$client_source"/libteec/include/*.h "$OPTEE_CLIENT_OUT/include/"
  install -m 0644 "$WORK/client-build/libteec/libteec.a" "$OPTEE_CLIENT_OUT/lib/"
fi
printf 'OP-TEE client: %s\n' "$OPTEE_CLIENT_OUT"
printf '生成完了: %s\n' "$OUT/core/tee.elf"
