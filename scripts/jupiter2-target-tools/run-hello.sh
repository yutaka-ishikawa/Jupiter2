#!/usr/bin/env bash
# Run only AFTER the reviewed SM firmware and matching trial kernel are booted.
set -Eeuo pipefail
bundle=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ $(uname -m) == riscv64 && $EUID == 0 ]] || { echo 'Run with sudo on Milk-V after SM firmware installation.' >&2; exit 2; }
bash "$bundle/tools/verify.sh"
release=$(cat "$bundle/kernelrelease.txt")
case "$release" in ''|*[!A-Za-z0-9._+-]*) exit 2;; esac
[[ $(uname -r) == "$release" ]] || { echo 'Running kernel does not match bundle.' >&2; exit 2; }
# Require identity of the installed driver as well as matching release text.
cmp "$bundle/modules/$release/extra/keystone-driver.ko" "/lib/modules/$release/extra/keystone-driver.ko"
modprobe keystone_driver
test -c /dev/keystone_enclave
"$bundle/apps/hello.ke"
"$bundle/apps/hello-native.ke"
