#!/usr/bin/env bash
# 目的: RAM起動関連のホスト回帰試験をまとめて実行する（開発PC用）。
# USBや実機の操作は行わない。CPU/SBI/PMPを模擬しない。
# 必要な実ツールがなければ停止し、全skipを合格として扱わない。
set -euo pipefail
TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
for tool in python3 dtc fdtput mkimage dumpimage lzop clang ld.lld; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "ERROR: required host test tool not found: $tool" >&2
        exit 1
    fi
done
python3 "$TEST_DIR/test_fit_packaging.py"
python3 "$TEST_DIR/test_elf_rpmi_contract.py"
python3 "$TEST_DIR/test_host_operations.py"
python3 "$TEST_DIR/test_linux_dtb_preparation.py"
