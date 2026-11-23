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

## LinuxのTPMリソースマネージャー経由の試験

Jupiter2の既定Linuxビルド（`scripts/build-linux-k3.sh` の
`k3_bianbu_defconfig`）は `CONFIG_TCG_TPM=y` と
`CONFIG_TCG_FTPM_TEE=m` を使う。試験では同じカーネルビルドの
`Image` と `drivers/char/tpm/tpm_ftpm_tee.ko` を使用する。

この手順のTAはREEのファイルからロードする。使用したOP-TEE Coreは
REE配置のTAをTEEバスに列挙しないため、QEMU試験用DTBに
`microsoft,ftpm` のplatformデバイスを明示する。試験用ノードは
TPMコマンドの転送を検証するためのもので、Measured Bootのイベントログは
構成していない。最小ゲストでは `tee-supplicant` の起動後に
`/init` がモジュールをロードする。

上記と同じ変数を使い、元のDTBとinitramfsを残したまま、試験用のコピーを作る。

```sh
cp "$BOOT_DTB" "$OUT/ftpm-boot.dtb"
fdtput -c "$OUT/ftpm-boot.dtb" /tpm
fdtput -t s "$OUT/ftpm-boot.dtb" /tpm compatible microsoft,ftpm

cp "$OUT/init.list" "$OUT/tpm-init.list"
printf 'file /tpm_ftpm_tee.ko %s 0644 0 0\n' \
    "$LINUX_OUT/drivers/char/tpm/tpm_ftpm_tee.ko" >> "$OUT/tpm-init.list"
"$LINUX_OUT/usr/gen_init_cpio" "$OUT/tpm-init.list" > "$OUT/tpm-init.cpio"
```

上記QEMUコマンドの `-dtb` と `-initrd` をそれぞれ
`"$OUT/ftpm-boot.dtb"` と `"$OUT/tpm-init.cpio"` に変更し、`-append` の
末尾に ` -- /dev/tpmrm0` を追加する。実測時は `timeout 180` を使用した。
出力先を `"$OUT/qemu-tpm.log"` とし、
次の行で合格を判定する。

```sh
grep -F 'fTPM PASS: TPM2_GetRandom returned 16 bytes via /dev/tpmrm0' \
    "$OUT/qemu-tpm.log"
```

稼働中のLinuxで、TAの配置、DTB、`tee-supplicant` の起動を済ませ、
`modprobe tpm_ftpm_tee` で登録した後は、該当するデバイスを指定して
`./ftpm-smoke /dev/tpmrm0` を実行できる。複数のTPMがある場合はfTPMに
割り当てられた番号を指定する。

## 実測結果

RV64 ELFと署名済みTA（331,376バイト）を生成した。K3 QEMUのUARTでLinuxの
16 CPU起動、OP-TEEによるREEからのfTPM TAロード、以下の応答と電源断を確認した。
QEMUの終了値は0だった。

```text
smp: Brought up 1 node, 16 CPUs
fTPM PASS: TPM2_GetRandom returned 16 bytes
reboot: Power down
```

`tpm_ftpm_tee.ko` を組み合わせた16 hartのQEMU試験では、
`/dev/tpmrm0` が登録され、`TPM2_GetRandom(16)` が成功した。UARTで
`fTPM PASS: TPM2_GetRandom returned 16 bytes via /dev/tpmrm0` と電源断を確認した。
初回はTAロード後に180秒でタイムアウトした。KSB-084のLinux向けIPIの
修正後は16 hart QEMUでモジュール登録から電源断まで反復試験に成功した。
調査と修正の詳細は
[障害記録](keystone-bug-report.md#ksb-084-qemuのftpmモジュール登録中に間欠的にタイムアウト)
で追跡する。

16 hartの同居QEMUでは、CPU 2でEnclaveを実行しながら、
CPU 3の `/dev/tpmrm0` から `TPM2_GetRandom(16)` を呼び出した。
初回の試験では3起動のうち1回がEnclave作成中のPMP同期で失敗した。
KSB-086の修正後は5起動すべてで16バイトの応答を取り、コマンドの送受信中に
Enclaveのタイマー割り込みを観測した。Enclaveの正常終了・破棄と電源断も確認した。
[障害記録](keystone-bug-report.md#ksb-086-ftpm同居qemuでenclaveのcreateが間欠的に失敗する)

NV保持のコールドブート試験は後述。実機での動作は未検証。

## TPMコマンドと障害復旧

KSB-086修正済みファームウェアを使い、16 hartのJupiter2 QEMUで、
`/dev/tpmrm0` にTPM 2.0コマンドを送った。既存データへの影響を避けるため、
initramfs内の評価用REE FSと試験用NV index `0x01500020` を使った。

| 試験 | 観測結果 |
| --- | --- |
| GetCapability | 固定プロパティ `TPM_PT_FAMILY_INDICATOR` の応答と成功コードを確認。 |
| PCR_Read / PCR_Extend | SHA-256バンクのPCR 16を読み、既知ダイジェストでextendした。再読出しが独立に計算したSHA-256値と一致。 |
| supplicant未起動でのprobe | TAセッションを開けず、TPMデバイスが登録されなかった。supplicantを起動してplatformドライバーをbindすると登録され、コマンドが成功。 |
| REE FSの書込み禁止 | NV_WriteでTAがpanic。書込み許可を戻しただけでは旧セッションは `TEE_ERROR_TARGET_DEAD`。platformドライバーをunbind/bindすると、障害前のNV値の読出しと新しい値の書込み・読出しが成功。 |
| 稼働後にsupplicantを停止・再起動 | 停止中のNV_WriteはRPC失敗にもかかわらずTPM成功を返した。REE FS内のファイル内容は変化せず、再起動後のNV_Readは未保存の値を返した。再起動後の別のNV_WriteもTPM成功を返したが、ファイル内容は変化しなかった。NV永続化の自動復旧は不合格。 |

[UARTログ抜粋](evidence/jupiter2-ftpm-recovery/uart.txt)。
ゲストは正常に電源断した。障害試験後の電源再投入をまたぐNV保持は未検証。

## NV永続化のコールドブート試験

[試験コード](../scripts/tests/jupiter2-ftpm-nv.c)は、試験専用NV index
`0x01500020` を定義し、`/dev/tpmrm0` 経由で4バイトを書き込む。
[QEMUランナー](../scripts/tests/jupiter2-ftpm-nv-qemu.sh)は、空のREE FSで
書き込みを実行したゲストから保存ファイルを回収する。初回ゲストの電源断後、
同じファイルだけをinitramfsに入れた別のQEMUプロセスで、
NV indexを定義し直さず読み出して4バイトの一致を検証する。
最後に空のREE FSでもう一度起動し、同じindexが存在しないことを確認する。

上記のTPMデバイス試験で使う、空の `/var/lib/tee` を持つ
`tpm-init.list` とDTBを用意する。クロスコンパイラー、OpenSBI、
Linux、OP-TEEおよびQEMUは上記と同じものを指定する。

```sh
QEMU="$QEMU" SBI="$SBI" IMAGE="$LINUX_OUT/arch/riscv/boot/Image" \
DTB="$OUT/ftpm-boot.dtb" OPTEE_ELF="$OPTEE_OUT/core/tee.elf" \
GEN_INIT_CPIO="$LINUX_OUT/usr/gen_init_cpio" CROSS_COMPILE="$CROSS" \
bash scripts/tests/jupiter2-ftpm-nv-qemu.sh "$OUT/tpm-init.list" "$OUT/nv-qemu"
```

出力先は新規ディレクトリを指定する。初回のUARTログには試験用REE FSの
シリアライズ結果も含む。検証対象は保存済みファイルからのfTPMの状態復元。
実機の永続媒体への書込みや、電源断時の媒体のフラッシュ動作は別途検証する。

16 hartのQEMU実測では、初回に36ファイルを回収し、別プロセスで
`NV_Read` が成功して書込み値 `TEST` の4バイトが一致した。
空のREE FSを使った対照試験では、同じindexへの `NV_Read` が
`TPM_RC_HANDLE`（第2ハンドル、`0x28b`）を返した。
3回とも正常に電源断した。[UARTログ抜粋](evidence/jupiter2-ftpm-nv/uart.txt)。

## fTPMとLinux IMAのQEMU試験

16 hartのJupiter2 QEMUで、`CONFIG_IMA=y`、`CONFIG_SECURITYFS=y`、
`CONFIG_IMA_MEASURE_PCR_IDX=10`、SHA-256、`ima-ng` を使った。
fTPMは既存と同じREE配置TAと `CONFIG_TCG_FTPM_TEE=m` で動かした。
比較用カーネルには、initramfs上のヘルパーをIMA初期化直前に呼ぶ
試験用のブートオプションを一時的に追加した。そのヘルパーは
`tee-supplicant` を起動し、fTPMモジュールをロードした。

- **IMAより先にfTPMを登録**。IMAのファイル測定ルールを読み込み、
  試験ファイルを読んだ。SHA-256のIMAログにPCR 10のイベントが1件記録された。
  ログ内のファイルダイジェストを試験ファイルから独立に計算した値と照合し、
  `SHA256(更新前のPCR 10 || IMAのテンプレートダイジェスト)` が
  `/dev/tpmrm0` から読んだ更新後のPCR 10と一致した。
- **通常の順序でfTPMを登録**。試験用ブートオプションを無効にし、
  fTPMを通常どおりユーザー空間の `/init` で登録した。
  IMAは初期化時にTPMを検出せず、測定ログは記録したがPCR 10は変化しなかった。

両起動とも正常に電源断した。この結果はfTPMをIMA初期化前に登録した
場合のLinux実行時測定を確認したもの。標準起動への組み込みと実機試験は未実施。
[UARTログ抜粋](evidence/jupiter2-ftpm-ima/uart.txt)。
