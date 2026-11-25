# Jupiter2 QEMUの3構成をビルドして試験する

| 構成 | OpenSBI | OP-TEE Core | QEMUでの確認 |
| --- | --- | --- | --- |
| KeystoneとOP-TEE | Keystone SM入り | 検証用TAを組み込み | EnclaveとTAの同居、fTPMとLinux IMA |
| Keystoneのみ | Keystone SM入り | 搭載なし | Keystoneのゲスト検証とSBI乱数試験 |
| OP-TEEのみ | K3標準設定、Keystone SMなし | 検証用TAを組み込み | 16 CPUからのTA並行呼び出し |

コマンドはBashで実行します。各構成は共通準備を済ませてから選びます。
この手順の対象はQEMUです。

## 共通準備

Ubuntu 24.04相当のAPT環境を使います。まずGitを入れ、Jupiter2を取得します。

```bash
sudo apt-get update
sudo apt-get install git
git clone https://github.com/yutaka-ishikawa/Jupiter2.git
cd Jupiter2
sudo bash scripts/install-build-deps.sh
```

依存導入スクリプトはGNU Make、Meson、Ninja、CMake、RV64クロスコンパイラ、
Clang/LLVM、Python 3、`dtc`・`fdtget`・`fdtput` などを導入します。
以降の相対パスはリポジトリルート基準です。QEMU、OpenSBI、Linux、Keystoneの
ソースはチェックアウト内の `qemu/`、`opensbi/`、`linux-k3/`、
`keystone/` にあります。試験ソースは `verifications/` と `scripts/tests/` にあります。

OP-TEEを使う2構成ではPythonのELFライブラリも導入します。

```bash
sudo apt-get install python3-pyelftools
python3 -c 'from elftools.elf.elffile import ELFFile'
```

## 1. KeystoneとOP-TEEを同梱する

### ソースと成果物

共通準備の各ソースを使います。初回の `make optee-coexist` は、未取得なら
次のリポジトリを固定コミットで取得します。既存のチェックアウトはコミットを確認して再利用します。

| ソース | 保存先 | 固定コミット |
| --- | --- | --- |
| [SpacemiT optee_os](https://github.com/spacemit-com/optee_os) | `.build-k3/optee-coexist/optee_os/` | `2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59` |
| [optee_client](https://github.com/OP-TEE/optee_client) | `.build-k3/optee-coexist/optee_client/` | `9f4414f62dfc5692fd39f760515ce2d344d07b6d` |

Coreビルドは [eFuseクロックのマッピング修正](../patches/optee/k3-map-efuse-clock-registers.patch) を適用し、
`verifications/optee-coexistence/` の検証用TAを組み込みます。
`make ftpm-ima` は [optee_ftpm](https://github.com/OP-TEE/optee_ftpm) を
`.build-k3/ftpm-test/ftpm-src/`、[ms-tpm-20-ref](https://github.com/microsoft/ms-tpm-20-ref) を
`.build-k3/ftpm-test/ms-tpm/`、optee_clientを同ディレクトリの `client-src/` に取得します。
固定リビジョンは [fTPM・IMAビルドスクリプト](../scripts/tests/build-jupiter2-ftpm-ima.sh) に記載されています。
IMA試験用Linuxは `.build-k3/ftpm-ima-source/` に作るGit worktreeでビルドします。

### ビルド、配置、試験

```bash
make build JOBS=20
make install
make optee-coexist JOBS=20
make optee-coexist-test

WORK=.build-k3/optee-coexist
python3 verifications/crypto/run-qemu.py --all --sstc on \
  --optee-coexistence "$WORK/out/core/tee.elf" "$WORK/boot.dtb" "$WORK/coexist.cpio"
```

`make install` はQEMU、Linux、Keystone SM入りOpenSBIなどを `install/keystone/` へ配置します。
OP-TEE Coreと同居試験用DTB・initramfsは `$WORK` に生成し、ランナーに直接渡します。
同居ケースでは16オンラインCPU、Enclave実行16回、OCALLを含むTA呼び出し33回、正常電源断を確認します。

fTPMとIMAも調べる場合は次を実行します。

```bash
make ftpm-ima JOBS=20
bash scripts/tests/jupiter2-ftpm-ima-qemu.sh
```

早期登録ではIMAによるPCR 10の更新値を照合し、遅延登録では測定後もPCR 10が変わらないことを検査します。
既定のログは `.build-k3/ftpm-ima/{early,late}.log` です。

## 2. Keystoneのみを使う

共通準備のソースとツールでビルドできます。Bianbuのrootfsは初回の
インストール時に用意されます。手元のアーカイブを使う場合は
`ROOTFS_ARCHIVE` と、必要に応じて `ROOTFS_SHA256` を指定します。

```bash
make build JOBS=20
make install
python3 verifications/crypto/run-qemu.py --all --sstc on
```

このコマンドではKeystoneのゲスト検証と乱数構成の試験を実行し、
`verifications/crypto/results/` に各ケースのログと `manifest.json` を保存します。
手動でゲストへ入る場合は `make run` を使います。
インストール先のrootfsを既に使っている場合は、QEMUを終了し、
ホストでマウントしていればアンマウントとloop切断を済ませてから再インストールします。

## 3. OP-TEEのみを使う

ソースは共通準備の `qemu/`、`opensbi/`、`linux-k3/` と、構成1と同じ
OP-TEE Core・clientを使います。ルートの `make opensbi` はKeystone SMをリンクするため、
この構成のOpenSBIは `make -C opensbi` と `k3_defconfig` で直接ビルドします。
ルートMakefileにOP-TEE単独用の一括installターゲットはありません。
QEMUとLinuxを個別にインストールし、単独用OpenSBIを別PREFIXへ配置します。

```bash
OPTEE_PREFIX="$PWD/install/optee"
K3_OUT="$PWD/.build-k3"
WORK="$K3_OUT/optee-coexist"
OPEN_SBI_OUT="$K3_OUT/opensbi-optee"
JOBS=20
CROSS_COMPILE=riscv64-linux-gnu-

make qemu linux JOBS="$JOBS" CROSS_COMPILE="$CROSS_COMPILE"
make install-qemu install-linux PREFIX="$OPTEE_PREFIX"
make optee-coexist JOBS="$JOBS" CROSS_COMPILE="$CROSS_COMPILE"
make -C opensbi -j"$JOBS" O="$OPEN_SBI_OUT" PLATFORM=generic \
  PLATFORM_DEFCONFIG=k3_defconfig CROSS_COMPILE="$CROSS_COMPILE"
install -D -m 0644 "$OPEN_SBI_OUT/platform/generic/firmware/fw_dynamic.bin" \
  "$OPTEE_PREFIX/firmware/k3/fw_dynamic.bin"
```

16 hartの検証用initramfsを作ります。Linuxには `CONFIG_TEE=y`、
`CONFIG_OPTEE=y`、`CONFIG_RISCV_SBI_MPXY_MBOX=y` が必要です。

```bash
TEST_OUT="$K3_OUT/optee-only-test"
OPTEE_CLIENT_OUT="$WORK/client/usr"
mkdir -p "$TEST_OUT"

"${CROSS_COMPILE}gcc" -static -O2 -pthread \
  -I"$OPTEE_CLIENT_OUT/include" verifications/optee-coexistence/optee-16-hart-init.c \
  "$OPTEE_CLIENT_OUT/lib/libteec.a" -o "$TEST_OUT/init"

cat > "$TEST_OUT/init.list" <<LIST
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
file /init $TEST_OUT/init 0755 0 0
LIST
"$K3_OUT/linux/usr/gen_init_cpio" "$TEST_OUT/init.list" > "$TEST_OUT/init.cpio"

dtc -q -I dts -O dtb -o "$TEST_OUT/boot.dtb" verifications/optee-coexistence/boot.dts
```

ここではリポジトリ内のDTSを起点にします。このDTSには全16 hart、
16 MPXYチャネル、256 KiBのOpenSBIヒープ、eFuse用MMIOとOP-TEEドメインが
記載されています。単独試験ではKeystoneドライバやEnclaveをinitramfsへ入れません。

```bash
timeout 90 "$OPTEE_PREFIX/bin/qemu-system-riscv64" \
  -accel tcg,thread=multi -M jupiter2,wtm-rng=on \
  -cpu rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16,sstc=on \
  -smp 16 -m 2G -display none -monitor none -serial stdio \
  -bios "$OPTEE_PREFIX/firmware/k3/fw_dynamic.bin" \
  -kernel "$OPTEE_PREFIX/boot/k3/Image" \
  -dtb "$TEST_OUT/boot.dtb" -initrd "$TEST_OUT/init.cpio" \
  -device "loader,file=$WORK/out/core/tee.elf" \
  -append 'console=ttyS0,115200 earlycon=sbi keep_bootcon printk.devkmsg=on rdinit=/init cma=512M@4G-16G' \
  </dev/null >"$TEST_OUT/uart.log" 2>&1
grep -aF 'PASS: parallel OP-TEE TA calls on all 16 CPUs' "$TEST_OUT/uart.log"
```

既存の単独QEMU試験では16 CPUの並行TA呼び出しに成功し、その後の電源断が
タイムアウトした記録があります。TAの合格マーカーとQEMUの終了状態を両方確認します。
上記のDTSを使ったコマンド一式は、この手順書の作成時点ではQEMUで未検証です。
[単独試験の記録](jupiter2-optee-ftpm-porting-plan.md)と[検証プログラムの仕様](../verifications/optee-coexistence/README.md#k3-qemuでのop-tee単独16-hart試験)

## カスタマイズできる変数

ルートMakefileには `make ターゲット 変数=値`、直接実行するシェルスクリプトには
`変数=値 bash スクリプト` で渡します。

| 変数 | 既定値 | 適用範囲 |
| --- | --- | --- |
| `JOBS` | ルートMakefileは `nproc` | 各ビルド工程の並列数 |
| `CROSS_COMPILE` | `riscv64-linux-gnu-` | RV64クロスツールチェーンの接頭辞 |
| `PREFIX` | `install/keystone` | ルートMakefileのインストール先、同居試験準備、およびIMAランナーの既定入力先 |
| `K3_BUILD_DIR` | `.build-k3` | ルートMakefileのQEMU・Linux・OpenSBI出力。同居CoreとfTPMのスクリプト内の作業ディレクトリは固定 |
| `KEYSTONE_BUILD_DIR` | `.build-keystone` | Keystone SDK、ドライバ、インストール前のステージ |
| `ROOTFS_ARCHIVE`、`ROOTFS_SHA256` | 空 | 新規rootfsのアーカイブと検証用ハッシュ |
| `KEYSTONE_SM_OPT_LEVEL`、`KEYSTONE_SM_TRACE`、`KEYSTONE_PMP_PROFILE` | `2`、`0`、`mixed` | Keystone SMの最適化、トレース、PMPプロファイル |
| `OPTEE_CLIENT_OUT` | `.build-k3/optee-coexist/client/usr` | RV64用ヘッダーと `lib/libteec.a` の親ディレクトリ。別ディレクトリにはビルド済みの両方を用意 |
| `KERNEL_OUT` | `.build-k3/linux` | 同居試験準備スクリプトを直接実行するときのLinux出力先。Make経由では `K3_BUILD_DIR/linux` |
| `LINUX_OUT` | `.build-k3/ftpm-ima-linux` | fTPM・IMA用Linuxの出力先。変更時はビルドと試験の両方に渡す |
| `QEMU`、`SBI` | `$PREFIX/bin/qemu-system-riscv64`、`$PREFIX/firmware/k3/fw_dynamic.bin` | fTPM・IMAランナーのQEMUとファームウェア |
| `BOOT_DTB`、`TEE_ELF` | `.build-k3/optee-coexist/boot.dtb`、同ディレクトリの `out/core/tee.elf` | fTPM・IMAランナーのDTBとCore |
| `FTPM_TA`、`TEE_SUPPLICANT` | `.build-k3/ftpm-test/` 以下のビルド成果物 | fTPM・IMAランナーの署名済みTAと静的supplicant |
| `OUT`、`TIMEOUT`、`SSTC` | `.build-k3/ftpm-ima`、`180` 秒、`on` | fTPM・IMAランナーのログ先、各起動の制限時間、Sstc設定 |

`run-qemu.py` のインストール先、ログ先、制限時間、Sstcはそれぞれ
`--prefix`、`--logs`、`--timeout`、`--sstc` で指定します。
構成3の `OPTEE_PREFIX`、`OPEN_SBI_OUT`、`TEST_OUT` は実行例内の変数で、
配置先を変更するときはビルド・配置・試験の各コマンドで同じ値を使います。
追加のSDK・SM変数と出力先は[Makefileの設定変数](make-build-install.md#設定変数)を参照してください。
