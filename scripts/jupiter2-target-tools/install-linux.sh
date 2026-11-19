#!/usr/bin/env bash
# Selectively install a new Linux release and apps. Never touch firmware/boot entries.
set -Eeuo pipefail
bundle=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ $(uname -m) == riscv64 && $EUID == 0 ]] || { echo 'Run with sudo on the Milk-V riscv64 board.' >&2; exit 2; }
bash "$bundle/tools/preflight.sh"
release=$(cat "$bundle/kernelrelease.txt")
case "$release" in ''|*[!A-Za-z0-9._+-]*) exit 2;; esac
for path in "/boot/Image-$release-keystone" "/boot/config-$release-keystone" "/opt/keystone/$release"; do
    [[ ! -e $path && ! -L $path ]] || { echo "Already exists: $path" >&2; exit 2; }
done
test -s "$bundle/linux/Image"
test -s "$bundle/linux/config"
test -s "$bundle/modules/$release/extra/keystone-driver.ko"
test -s "$bundle/apps/hello.ke"
test -s "$bundle/apps/hello-native.ke"
# No rollback across /boot, /lib and /opt: review any partial placement after failure.
install -m 0644 "$bundle/linux/Image" "/boot/Image-$release-keystone"
install -m 0644 "$bundle/linux/config" "/boot/config-$release-keystone"
cp -a "$bundle/modules/$release" /lib/modules/
depmod -a "$release"
install -d "/opt/keystone/$release"
install -m 0755 "$bundle/apps/hello.ke" "$bundle/apps/hello-native.ke" "/opt/keystone/$release/"
printf 'OS files installed for %s. Generate initramfs and add a manual trial boot entry using docs/milkv-jupiter2-stack-install.md.\n' "$release"
