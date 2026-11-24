#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
WORK="$ROOT/.build-k3/optee-coexist"
VERIFY="$ROOT/verifications/optee-coexistence"
PREFIX="${PREFIX:-$ROOT/install/keystone}"
KERNEL_OUT="${KERNEL_OUT:-$ROOT/.build-k3/linux}"
KEYSTONE_BUILD_DIR="${KEYSTONE_BUILD_DIR:-$ROOT/.build-keystone}"
CROSS_COMPILE="${CROSS_COMPILE:-riscv64-linux-gnu-}"
OPTEE_CLIENT_OUT="${OPTEE_CLIENT_OUT:-$WORK/client/usr}"
OPTEE_CLIENT_OUT="$(realpath -m "$OPTEE_CLIENT_OUT")"
runtime="$PREFIX/runtime/hello-native"
driver="$KEYSTONE_BUILD_DIR/driver/keystone-driver.ko"
sample="$ROOT/samples/hello-native/build/hello-native"
for input in "$driver" "$sample" "$runtime/eyrie-rt" "$runtime/loader.bin" \
  "$OPTEE_CLIENT_OUT/lib/libteec.a" "$OPTEE_CLIENT_OUT/include/tee_client_api.h"; do
  if [[ ! -s "$input" ]]; then
    printf 'Missing coexistence build input: %s\n' "$input" >&2
    exit 1
  fi
done

cmp "$KERNEL_OUT/arch/riscv/boot/Image" "$PREFIX/boot/k3/Image"
mkdir -p "$WORK"
tmp="$(mktemp -d "$WORK/test.XXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT
make -C "$VERIFY" "$tmp/optee-coexistence" OUT="$tmp" \
  CROSS_COMPILE="$CROSS_COMPILE" SDK_DIR="$PREFIX/sdk" \
  OPTEE_CLIENT_OUT="$OPTEE_CLIENT_OUT" LDFLAGS=-static
"${CROSS_COMPILE}gcc" -static -O2 -Wall -Wextra -Werror \
  -o "$tmp/init" "$VERIFY/coexist-init.c"
dtc -q -I dts -O dtb -o "$tmp/boot.dtb" "$VERIFY/boot.dts"

cat > "$tmp/initramfs.list" <<LIST
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
file /init $tmp/init 0755 0 0
file /optee-coexistence $tmp/optee-coexistence 0755 0 0
file /keystone-driver.ko $driver 0644 0 0
file /hello-native $sample 0755 0 0
file /eyrie-rt $runtime/eyrie-rt 0755 0 0
file /loader.bin $runtime/loader.bin 0644 0 0
LIST
"$KERNEL_OUT/usr/gen_init_cpio" "$tmp/initramfs.list" > "$tmp/coexist.cpio"
mv "$tmp/boot.dtb" "$tmp/coexist.cpio" "$WORK/"
printf '%s\n' "$WORK/boot.dtb" "$WORK/coexist.cpio"
