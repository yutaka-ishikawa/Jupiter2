# Jupiter2向けfTPM TAのビルドとQEMU試験

K3 QEMUのLinuxから `libteec → OP-TEEドライバー → SBI MPXY →
OpenSBI → OP-TEE Core → fTPM TA` と呼び、TPM 2.0コマンドの応答を検証する。
[移植計画](jupiter2-optee-ftpm-porting-plan.md)の同居構成を使用する。

## 前提

- RV64 Linuxクロスコンパイラー。試験ではBuildroot GCC 13.3.0を使用。
- SpacemiT OP-TEE Core `2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59` から
  ビルドした `tee.elf` と対応する `export-ta_rv64`。試験では
  [eFuseクロックマッピングパッチ](../patches/optee/k3-map-efuse-clock-registers.patch)を
  適用した `CFG_TEE_CORE_NB_CORE=16 CFG_NUM_THREADS=16 CFG_K3_EFUSE=y
  CFG_REE_FS=y CFG_REE_FS_TA=y CFG_RPMB_FS=n` のビルドを使用した。
- K3 QEMU、Keystone SM入りのOpenSBI `fw_dynamic.bin`（KSB-083修正
  `16721a577` を含む）、OP-TEE・SBI MPXY・devtmpfs・initramfsが有効な
  `linux-k3` の `Image` と、同じLinuxビルドの `usr/gen_init_cpio`。
  DTBはOP-TEE先行起動の16 hart・2 GiB同居用で、OP-TEEとLinuxのドメイン、
  eFuseおよびPMUのMMIO、予約領域とMPXYチャネルを含む。設定は
  [移植計画のDTB生成とeFuse試験](jupiter2-optee-ftpm-porting-plan.md)を参照。
- TAの署名にはCoreが信頼する鍵を使用する。今回の鍵と、未書込みeFuseを
  模擬するQEMUの開発用HUKは試験専用。

## fTPM TAのクロスビルド

Jupiter2リポジトリのルートで実行する。冒頭の2パスは手元のビルドに合わせる。

```sh
set -eu
CROSS=/path/to/toolchain/bin/riscv64-buildroot-linux-gnu-
OPTEE_OUT=/path/to/optee-build
OUT="$PWD/.build-k3/ftpm-test"
UUID=bc50d971-d4c9-42c4-82cb-343fb7f37896
mkdir -p "$OUT"

git clone https://github.com/OP-TEE/optee_ftpm.git "$OUT/ftpm-src"
git -C "$OUT/ftpm-src" checkout --detach 6f99e783eb9bb57c314a881433d4ec970de87959
git clone https://github.com/microsoft/ms-tpm-20-ref.git "$OUT/ms-tpm"
git -C "$OUT/ms-tpm" checkout --detach 98b60a44aba79b15fcce1c0d1e46cf5918400f6a

make -C "$OUT/ftpm-src" -j8 O="$OUT/ta" \
    TA_DEV_KIT_DIR="$OPTEE_OUT/export-ta_rv64" CROSS_COMPILE="$CROSS" \
    CFG_MS_TPM_20_REF="$OUT/ms-tpm" CPPFLAGS=-DRADIX_BITS=64

test -s "$OUT/ta/$UUID.ta"
"${CROSS}readelf" -h "$OUT/ta/$UUID.elf"
```

`CPPFLAGS` でMicrosoft参照実装の多倍長整数のワード幅をRV64向けに明示する。
Measured BootとPPIは既定どおり無効。TAは既定の `TEE_STORAGE_PRIVATE` を使い、
今回のCoreではREEファイルシステムへ保存する。初期候補 `f09f4cdad210` は
現行Coreにない `TA_FLAG_INSTANCE_KEEP_CRASHED` を要求するため、今回の試験には
フラグ導入直前の `6f99e783eb9b` を固定した。クラッシュ後にTAの再起動を
抑止する挙動はこの組み合わせの試験対象外。

## テストコードとtee-supplicantのビルド

```sh
git clone https://github.com/OP-TEE/optee_client.git "$OUT/client-src"
git -C "$OUT/client-src" checkout --detach 9f4414f62dfc5692fd39f760515ce2d344d07b6d

make -C "$OUT/client-src/libteec" -j8 OO="$OUT/client" \
    CROSS_COMPILE="$CROSS" CC="${CROSS}gcc" AR="${CROSS}ar"
make -C "$OUT/client-src/tee-supplicant" -j8 OO="$OUT/client" \
    CROSS_COMPILE="$CROSS" CC="${CROSS}gcc" LDFLAGS=-static \
    CFG_TEE_SUPP_PLUGINS=n RPMB_EMU=0
"${CROSS}gcc" -static -O2 -Wall -Wextra -Werror \
    -I"$OUT/client-src/libteec/include" scripts/tests/jupiter2-ftpm-smoke.c \
    "$OUT/client/libteec/libteec.a" -pthread -o "$OUT/ftpm-smoke"
```

[テストコード](../scripts/tests/jupiter2-ftpm-smoke.c)はfTPMのUUIDでセッションを開き、
コマンドID 0に `TPM2_GetRandom(16)` を渡す。TPM応答のタグ、リターンコード、
全体長、返却バイト数を検査する。既存ゲストから実行する場合は署名済みTAを
`/lib/optee_armtz/` に配置し、`tee-supplicant` を起動して `./ftpm-smoke` を
実行する。終了値0が合格。

## 最小initramfsでのQEMU試験

```sh
LINUX_OUT=/path/to/linux-k3-build
QEMU="$PWD/.build-k3/qemu/qemu-system-riscv64"
BOOT_DTB=/path/to/coexist-boot.dtb
SBI=/path/to/fw_dynamic.bin

cat > "$OUT/init.list" <<EOF_LIST
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
dir /lib 0755 0 0
dir /lib/optee_armtz 0755 0 0
dir /var 0755 0 0
dir /var/lib 0755 0 0
dir /var/lib/tee 0700 0 0
file /lib/optee_armtz/$UUID.ta $OUT/ta/$UUID.ta 0644 0 0
file /tee-supplicant $OUT/client/tee-supplicant/tee-supplicant 0755 0 0
file /init $OUT/ftpm-smoke 0755 0 0
EOF_LIST
"$LINUX_OUT/usr/gen_init_cpio" "$OUT/init.list" > "$OUT/init.cpio"

timeout 120 "$QEMU" -accel tcg,thread=multi \
    -M jupiter2,wtm-rng=on \
    -cpu rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16 \
    -smp 16 -m 2G -display none -monitor none -serial stdio \
    -dtb "$BOOT_DTB" -bios "$SBI" -kernel "$LINUX_OUT/arch/riscv/boot/Image" \
    -initrd "$OUT/init.cpio" \
    -append 'console=ttyS0,115200 earlycon=sbi keep_bootcon printk.devkmsg=on rdinit=/init cma=512M@4G-16G' \
    -device "loader,file=$OPTEE_OUT/core/tee.elf" > "$OUT/qemu.log" 2>&1

grep -F 'smp: Brought up 1 node, 16 CPUs' "$OUT/qemu.log"
grep -F 'fTPM PASS: TPM2_GetRandom returned 16 bytes' "$OUT/qemu.log"
grep -F 'reboot: Power down' "$OUT/qemu.log"
```

PID 1として動くテストコードはdevtmpfsをマウントし、試験出力を
`/dev/kmsg`経由でUARTに送る。tee-supplicantの起動後にTAを呼び、電源断する。
試験結果はUARTのPASS行で判定する。

## 実測結果

RV64 ELFと署名済みTA（331,376バイト）を生成した。K3 QEMUのUARTでLinuxの
16 CPU起動、OP-TEEによるREEからのfTPM TAロード、以下の応答と電源断を確認した。
QEMUの終了値は0だった。

```text
smp: Brought up 1 node, 16 CPUs
fTPM PASS: TPM2_GetRandom returned 16 bytes
reboot: Power down
```

Linuxの `tpm_ftpm_tee` と `/dev/tpmrmN` 経由の試験、再起動をまたぐNV保持、
Keystone EnclaveとfTPMの同時実行、実機での動作は未検証。
