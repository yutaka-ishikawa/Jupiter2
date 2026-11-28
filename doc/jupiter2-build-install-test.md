# Jupiter2実機用イメージのビルド・導入・試験

USBで一時起動する場合はRAM起動用のFSBLと統合FITを作ります。

Keystoneのみの構成で生成されるファイルは次の2つです。

- `$OUT/release/images/FSBL.bin`
- `$OUT/release/images/ram-boot-keystone.itb`

`$OUT` はビルド時に指定する出力ディレクトリです。以下の実行例では
リポジトリ直下の `work/jupiter2-ram-boot/keystone-<日時>/` です。

実機のOpenSBI用NOR区画へ導入する場合は、容量を採取して配布用bundleを作ります。
RAM起動用は次の3構成から選びます。

| 構成 | OpenSBI | FITのOP-TEE Core | FIT名 |
| --- | --- | --- | --- |
| Keystoneのみ | Keystone SM入り | なし | `ram-boot-keystone.itb` |
| OP-TEEのみ | K3標準設定、Keystone SMなし | `tee.bin` | `ram-boot-vendor.itb` |
| KeystoneとOP-TEEを同梱 | Keystone SM入り | `tee.bin` | `ram-boot-keystone.itb` |

OP-TEE入りの2構成では、ビルダーでCoreとOpenSBI用DTBをFITに格納します。
Pico-ITX向けの同梱構成では実機用FITとLinux用DTBの生成をホストで確認しました。
実機でのUSB RAM起動と周辺機器の動作確認が残っています。
NOR導入用bundleはこの手順ではKeystoneのみを対象とします。

## 開発PCの準備

Ubuntu系の開発PCで `Jupiter2` をチェックアウトし、リポジトリのルートで実行します。

```bash
sudo bash scripts/install-build-deps.sh
sudo apt-get install python3-dev python3-setuptools swig libgnutls28-dev \
  libncurses-dev u-boot-tools lzop openssl fastboot
export CROSS_COMPILE=riscv64-unknown-linux-gnu-
"${CROSS_COMPILE}gcc" --version
```

OP-TEE入りの構成をビルドする場合は、開発PCに `pyelftools` を導入し、Pythonから読み込めることを確認します。

```bash
sudo apt-get install python3-pyelftools
python3 -c 'from elftools.elf.elffile import ELFFile'
```

K3用クロスツールチェーンをPATHに置き、接頭辞は導入したものに合わせます。
NOR用・USB RAM起動用の包装スクリプトにはPython 3.11以上が必要です。
採取した実機情報と `hardware/jupiter2/` の記録を照合します。
[実機入力の管理](../hardware/jupiter2/README.md)

<a id="ram-boot-images"></a>
## 1. RAM起動用のFSBLと統合FIT

### 1.1 Keystoneのみ

```bash
OUT="$PWD/work/jupiter2-ram-boot/keystone-$(date +%Y%m%d-%H%M%S)"
JOBS=20 bash scripts/build-jupiter2-ram-boot.sh "$OUT"
ls -lh "$OUT/release/images/"
```

出力は同じビルドの `release/images/FSBL.bin` と
`release/images/ram-boot-keystone.itb` です。USB起動ではこの2つを対で使います。

### スクリプトが行う処理

1. `make firmware` でKeystone SM入りOpenSBIの `fw_dynamic.bin` と
   `fw_dynamic.elf` をビルドします。
2. [参照ビルダー](../scripts/build-jupiter2-reference-ram-boot.py)を起動し、
   実機入力の `esos.itb` を使って固定リビジョンのFSBLとU-Bootをビルドします。
3. OpenSBIのELFをBINに再変換して、組み込むBINと一致することを確認します。
   ELFの `_fw_start` と `_fw_end` から静的領域を求め、生成したU-Boot FITの
   DTBから有効hart数とヒープ設定を読みます。OpenSBIのスタック、ヒープ、
   起動時の一時スタックを考慮し、実行時の範囲を覆う2の累乗に切り上げます。
4. 生成されたSPL用ビルド設定の `CONFIG_FASTBOOT_BUF_SIZE` を読みます。
   既定の固定ソースでは512 MiBです。対応する実機SPLのFastboot採取ログを渡すと、
   そこに記録された上限を使います。生成SPLの設定より大きい値は拒否します。
5. 統合FITを作り、ロード範囲の重複とFIT全体の転送サイズを検査します。
   算出内訳、使用した値、入力のハッシュは `records/build-manifest.json`、
   ビルドログは `records/build.log` に残ります。

### 採取したFastboot上限を使う例

[READMEの実機情報採取手順](../README.md#capture-save)で
保存した `spl-fastboot.log` を使います。

```bash
CAPTURE_ID=20261124-165032  # 実機で採取したIDに置き換える
CAPTURE_DIR="$PWD/hardware/jupiter2/captures/$CAPTURE_ID"
OUT="$PWD/work/jupiter2-ram-boot/keystone-capture-$(date +%Y%m%d-%H%M%S)"
FASTBOOT_LOG="$CAPTURE_DIR/spl-fastboot.log" \
  JOBS=20 bash scripts/build-jupiter2-ram-boot.sh "$OUT"
```

<a id="ram-boot-variables"></a>
### RAM起動用の設定変数

`OUT` は上の実行例で設定するシェル変数です。ビルドスクリプトには
出力先の位置引数として渡します。`export` は不要です。ビルド後は同じシェルの
`OUT` をRAM起動ガイドで引き継ぎ、`REL="$OUT/release"` として使います。
以下の環境変数でビルド設定を上書きできます。

| 変数 | 既定値と用途 |
| --- | --- |
| `CROSS_COMPILE` | `riscv64-unknown-linux-gnu-`。K3ツールチェーンの接頭辞 |
| `JOBS` | `nproc`。ビルドの並列数 |
| `K3_BUILD_DIR` | `.build-k3`。OpenSBIのビルド出力先 |
| `ESOS_ITB` | `hardware/jupiter2/vendor/esos.itb`。対象実機に対応するESOS FIT |
| `ESOS_CONFIGURATION` | `hardware/jupiter2/vendor-fit.json` の `esos_configuration`（現在は `conf_dual`）。別のESOS構成を使う場合に上書き |
| `FASTBOOT_LOG` | 未指定時は生成SPLの設定を使う。指定時は対象SPLの `getvar` 採取ログ |

### 販売元OpenSBIで基準起動用のイメージを作る

販売元の `fw_dynamic.itb` から `hardware/jupiter2/vendor/fw_dynamic.bin` を抽出します。
[販売元OpenSBIの抽出手順](jupiter2-ram-boot-procedure.md)を参照してください。

```bash
sudo apt-get update
sudo apt-get install git build-essential python3 python3-dev python3-setuptools \
  bison flex swig libssl-dev libgnutls28-dev libncurses-dev \
  device-tree-compiler u-boot-tools lzop openssl bc fastboot
```

K3用RISC-V GCCを別途導入してPATHへ追加する。以下のprefixは今回の例で、導入した実名に合わせる。

```bash
export CROSS_COMPILE=riscv64-unknown-linux-gnu-
"${CROSS_COMPILE}gcc" --version

# 今回のSPLで実測したUSB転送上限。NORのopensbi区画容量ではない。
SPL_DOWNLOAD_BYTES=0x20000000
# 今回の販売元版で使用した実行時予約領域。別ビルドではBSS/heap/stack等も確認する。
VENDOR_SBI_RESERVE_BYTES=0x00100000
OUT="$PWD/work/jupiter2-ram-boot/reference-vendor-$(date +%Y%m%d-%H%M%S)"

python3 scripts/build-jupiter2-reference-ram-boot.py \
  --opensbi-bin hardware/jupiter2/vendor/fw_dynamic.bin \
  --esos-itb hardware/jupiter2/vendor/esos.itb \
  --esos-configuration conf_dual \
  --variant vendor \
  --opensbi-reserve-bytes "$VENDOR_SBI_RESERVE_BYTES" \
  --max-download-bytes "$SPL_DOWNLOAD_BYTES" \
  --cross-compile "$CROSS_COMPILE" \
  --output "$OUT"

```

生成先は `$OUT/release/images/` で、ファイルは `FSBL.bin` と
`ram-boot-vendor.itb` です。

### 1.2 OP-TEE入り構成の共通準備

固定コミットのSpacemiT版OP-TEEをK3向けにクロスビルドします。下の例は
実機向けK3のデバイス設定を使う評価用ビルドです。実機のeFuseに鍵が
プロビジョニングされている想定で開発用HUKのフォールバックを無効にします。
未書き込み機ではHUKが必要な機能を検証する前に対象機の鍵構成を確認してください。

```bash
OPTEE_WORK="$PWD/.build-k3/optee-hardware"
OPTEE_SRC="$OPTEE_WORK/optee_os"
OPTEE_REV=2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59
mkdir -p "$OPTEE_WORK"
if [ ! -e "$OPTEE_SRC" ]; then
    git clone https://github.com/spacemit-com/optee_os.git "$OPTEE_SRC"
    git -C "$OPTEE_SRC" checkout --detach "$OPTEE_REV"
fi
(
  set -e
  test "$(git -C "$OPTEE_SRC" rev-parse HEAD)" = "$OPTEE_REV"
  for patch in "$PWD/patches/optee/"{k3-map-efuse-clock-registers,k3-private-boot-dtb}.patch; do
    git -C "$OPTEE_SRC" apply --reverse --check "$patch" 2>/dev/null ||
      git -C "$OPTEE_SRC" apply "$patch"
  done
  make -C "$OPTEE_SRC" -j20 O="$OPTEE_WORK/out" ARCH=riscv PLATFORM=k3 \
    CROSS_COMPILE="$CROSS_COMPILE" CROSS_COMPILE_core="$CROSS_COMPILE" \
    CROSS_COMPILE_ta_rv64="$CROSS_COMPILE" \
    CFG_TEE_CORE_NB_CORE=16 CFG_NUM_THREADS=16 CFG_K3_PRIVATE_BOOT_DTB=y \
    CFG_K3_EFUSE=y CFG_K3_HUK_ALLOW_UNFUSED=n CFG_K3_IOPMP=y CFG_K3_PRNG=y \
    CFG_MMP_RTC=y CFG_TE200_CRYPTO_DRIVER=y CFG_REE_FS=y CFG_REE_FS_TA=y CFG_RPMB_FS=n
)

TEE_BIN="$OPTEE_WORK/out/core/tee.bin"
TEE_ELF="$OPTEE_WORK/out/core/tee.elf"
test -s "$TEE_BIN"
"${CROSS_COMPILE}readelf" -h -l "$TEE_ELF"
```

Linux側でOP-TEEを使うには、対応する `Image` とLinux DTBを用意します。
DTBのOP-TEEノードをRISC-V SBI MPXYのメールボックスに対応付け、
`CONFIG_TEE`、`CONFIG_OPTEE`、`CONFIG_RISCV_SBI_MPXY_MBOX` の設定を確認します。
外部TAを使う場合は、同じCoreのRV64 dev kitでビルドした署名済みTAを
ゲストのTA検索先（例 `/lib/optee_armtz/`）へ配置し、
対応するRV64 `tee-supplicant` をゲストで起動します。
[OP-TEE・fTPMの配置と検査項目](jupiter2-optee-ftpm-porting-plan.md)

### 1.3 OP-TEEのみ

Keystone SMを含まないOpenSBIを `opensbi/` の `k3_defconfig` で作ります。
1.2節と同じシェルで `TEE_BIN` を引き継ぎます。

```bash
SBI_OUT="$PWD/.build-k3/firmware/build-opensbi-k3-optee"
make -C opensbi -j20 O="$SBI_OUT" PLATFORM=generic \
  PLATFORM_DEFCONFIG=k3_defconfig CROSS_COMPILE="$CROSS_COMPILE"
make linux JOBS=20
SBI="$SBI_OUT/platform/generic/firmware/fw_dynamic"
OUT="$PWD/work/jupiter2-ram-boot/optee-only-$(date +%Y%m%d-%H%M%S)"
VARIANT=vendor
```

ビルダーの `vendor` は出力名の種別です。この例では上でビルドしたOpenSBIを指定します。
続けて1.5節でFITを作ります。

### 1.4 KeystoneとOP-TEEを同梱する

Keystone SM入りOpenSBIと、対応するLinux・ドライバをビルドします。
先に1.2節で同じビルドの `TEE_BIN` と `TEE_ELF` を作ります。
続く1.5節は `VARIANT=keystone` に対してPico-ITX用の16枠固定配置を指定します。

```bash
make opensbi keystone JOBS=20
SBI="$PWD/.build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic"
OUT="$PWD/work/jupiter2-ram-boot/keystone-optee-$(date +%Y%m%d-%H%M%S)"
VARIANT=keystone
```

<a id="optee-fit-build"></a>
### 1.5 OP-TEE入りFITを作る（1.3・1.4共通）

選んだ構成で設定した `SBI`、`OUT`、`VARIANT` と、1.2節の `TEE_BIN`・`TEE_ELF` を同じシェルで引き継ぎます。

OpenSBI側は参照U-BootのPico-ITX用DTBをベースに、ビルド中に
OP-TEEドメイン、Coreと共有メモリの予約、MPXY設定を生成します。
ベースDTBは `records/opensbi-uboot-base.dtb` に保存します。
Pico-ITXの16枠同梱構成では、OpenSBIのヒープを192 KiBに設定して初回の
ドメインコンテキスト確保に必要な管理枠を確保します。192 KiBの修正版はPico-ITX実機で
U-Boot本体のプロンプトに到達しました。続けて同じFITビルドのLinux用DTBでLinuxを一時起動します。
[停止原因と実機の確認結果](keystone-bug-report.md#ksb-098-board-pass) ·
[UFSとLinux起動ファイルの確認](jupiter2-ram-boot-guide.md#coexistence-linux-boot)

実機向けの設定済みDTBやオーバーレイを既に用意している場合は、
それぞれ `--opensbi-dtb` または `--opensbi-overlay` で指定できます。

```bash
ESOS_CONFIGURATION=$(python3 -c 'import json, sys; print(json.load(sys.stdin)["esos_configuration"])' \
  < hardware/jupiter2/vendor-fit.json)
OPTEE_FIT_ARGS=(--optee-bin "$TEE_BIN")
if [ "$VARIANT" = keystone ]; then
    OPTEE_FIT_ARGS+=(--optee-elf "$TEE_ELF" --pico-itx-pmp16)
fi
python3 scripts/build-jupiter2-reference-ram-boot.py \
  --opensbi-bin "$SBI.bin" --opensbi-elf "$SBI.elf" \
  --esos-itb hardware/jupiter2/vendor/esos.itb --esos-configuration "$ESOS_CONFIGURATION" \
  "${OPTEE_FIT_ARGS[@]}" --variant "$VARIANT" --cross-compile "$CROSS_COMPILE" \
  --jobs 20 --output "$OUT"

FIT="ram-boot-$VARIANT.itb"
dumpimage -l "$OUT/release/images/$FIT"
fdtget -t s "$OUT/release/images/$FIT" /configurations/conf_11 loadables
(cd "$OUT/release" && sha256sum -c records/FSBL.bin.sha256 "records/$FIT.sha256")
```

一覧に `optee` があり、Coreのロード・エントリアドレスが `0x171000000` で
`tee.elf` の配置と一致することを確認します。同梱構成とKeystoneのみのFITは
同じファイル名になるため、出力ディレクトリで区別してください。

指定したDTBはFITのFDTイメージに格納され、`$OUT/records/opensbi-uboot.dtb` にも保存されます。
ビルダーはOP-TEEエントリアドレスとMPXYのドメイン参照を検証します。
実機のhart構成、メモリ予約、PMP、Linux用DTBの `/firmware/optee` と
MPXYチャネルの対応は別途確認します。
Linux用DTBのMPXY接続は、同じOpenSBI用DTBから生成します。
採取済みのLinux用DTBを入力にします。対象実機で別のDTBを使っている場合は、
`LINUX_DTB` に実際の起動用DTB（例 `k3-pico-itx-keystone.dtb`）を指定します。

```bash
LINUX_DTB="${LINUX_DTB:-$PWD/hardware/jupiter2/captures/20261108-075700/running.dtb}"
LINUX_OPTEE_DTB="$OUT/release/images/k3-pico-itx-keystone-optee.dtb"
python3 scripts/prepare-jupiter2-optee-linux-dtb.py \
  "$OUT/records/opensbi-uboot.dtb" "$LINUX_DTB" "$LINUX_OPTEE_DTB"
fdtget -t s "$LINUX_OPTEE_DTB" /firmware/optee compatible
fdtget -t x "$LINUX_OPTEE_DTB" /firmware/optee mboxes
```

生成したLinux用DTBはUFSへ別名で配置し、U-Bootの `booti` に渡します。
別のメモリ構成を使う場合は、対象実機用に検証したDTBまたはオーバーレイを指定します。

[実機移植計画](jupiter2-optee-ftpm-porting-plan.md) · [同居設計](keystone-optee-coexistence-design.md)

#### 16枠同梱構成のFIT生成検査

1.4節で指定した `VARIANT=keystone` を使うと、上のコマンドが
`--optee-elf "$TEE_ELF" --pico-itx-pmp16` を渡します。ビルダーが同じCoreのELFとBINを
照合し、ELFの `.k3_boot_dtb` から私有DTBのアドレスと容量を取り出します。OpenSBIのELFと
生成DTBから、実行時に確保するスタックとヒープを含めて既存の1 MiB保護範囲に収まるか検査します。
上のLinux用DTB生成で、同じビルドの `records/opensbi-uboot.dtb` を使います。

標準の入力で生成したOpenSBI用DTBの `heap-size` は16進数の `30000` です。

```bash
fdtget -t x "$OUT/records/opensbi-uboot.dtb" /chosen/opensbi-config heap-size
```

FSBL・FIT・Linux用DTBの生成とハッシュ照合をホストで確認しました。実機のUSB RAM起動では、
クロック・リセット仲介と実機I/O・DMAの動作を確認します。
[16枠の実装計画](jupiter2-coexistence-16-pmp-plan.md#枠14の共用と私有dtbの確認) ·
[ホストビルドの記録](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

### 1.6 実機への配置と起動確認

Linuxを更新する場合は、使用中の起動設定と元のファイルを退避した上で、
ビルドした `.build-k3/linux/arch/riscv/boot/Image`、対象のLinux DTB、同一ビルドの
モジュールを実機の起動パーティションとrootfsへ配置します。
Keystone入りの構成では、同じカーネルでビルドしたKeystoneドライバと
`hello`・`hello-native` も配置します。 [Linux・モジュールの配置手順](milkv-jupiter2-stack-install.md)

[RAM起動ガイド](jupiter2-ram-boot-guide.md)に従い、同じビルドの `FSBL.bin` と
選択したFITをUSBでRAMに転送し、UARTでLinuxまでの到達を確認します。
OP-TEE入り構成は1.5節のDTBの条件を満たしたイメージを使います。
手動起動時は実機の起動パーティション、Linux Image、initrd、DTB、rootfsのPARTUUIDを
指定し、各ファイルのロードが成功してから `booti` を実行します。

- **Keystoneのみ**。ドライバを読み込み、`hello` と `hello-native` を実行します。
- **OP-TEEのみ**。UARTでCore、LinuxでOP-TEEドライバの初期化を確認し、対応TAのセッションを開いてコマンドを呼び出します。
- **同梱**。同一Linux起動中に、Keystone EnclaveとOP-TEE TAの両方の処理を確認します。

[Keystoneアプリの実機試験](jupiter2-keystone-app-test.md) · [OP-TEEの検査項目](jupiter2-optee-ftpm-porting-plan.md)

<a id="ram-boot-bundle"></a>
### 1.7 BootROMからRAM上で起動するFSBLと統合FITをbundleにする

第1章で作成した参照ビルダーの `$OUT/release` を使います。
Keystoneのみ、OP-TEEのみ、同梱構成のどれでも、同じビルドの
`FSBL.bin` と統合FITを対で包装します。既存のreleaseからも作成できます。
開発PCのリポジトリルートで、ビルド時に設定した `OUT` を引き継いで実行します。

```bash
BUNDLE_OUT="$OUT/ram-boot-bundle"
python3 scripts/package-jupiter2-ram-boot.py \
  --release "$OUT/release" --output "$BUNDLE_OUT" &&
  (cd "$BUNDLE_OUT" && sha256sum -c ram-boot-bundle.tar.gz.sha256)
```

`--output` には新しいディレクトリを指定します。スクリプトは
releaseのマニフェストからFITを選び、FSBLとFITのSHA-256を確認します。
アーカイブと同じ内容の `release/` も出力します。

```text
$BUNDLE_OUT/
├── ram-boot-bundle.tar.gz
├── ram-boot-bundle.tar.gz.sha256
└── release/
    ├── images/
    │   ├── FSBL.bin
    │   └── ram-boot-keystone.itb または ram-boot-vendor.itb
    ├── README-RAM-BOOT.md
    ├── records/
    └── tools/ram-boot.py
```

第1.5節で生成した `images/k3-pico-itx-keystone-optee.dtb` が入力releaseに
ある場合は、そのDTBとSHA-256も同梱します。BootROMへの転送には
`FSBL.bin` を、SPLへの転送には統合FITを使います。Linux用DTBはUFSの
bootfsへ配置し、Linux起動時に指定します。

別の開発PCからUSB転送する場合は、`ram-boot-bundle.tar.gz` と
`ram-boot-bundle.tar.gz.sha256` を空のディレクトリにコピーします。
そのディレクトリで、照合・展開・転送前の確認を行います。

```bash
(
    set -eu
    sha256sum -c ram-boot-bundle.tar.gz.sha256
    test ! -e release && test ! -L release || exit 1
    tar -xzf ram-boot-bundle.tar.gz
    cd release
    sha256sum -c records/host-tools.sha256
    python3 tools/ram-boot.py --phase fsbl --dry-run
)
```

実機への転送は、展開した `release/` の `README-RAM-BOOT.md` に従います。
生成直後の `$BUNDLE_OUT/release` も同じ手順で使えます。
[USB RAM起動ガイド](jupiter2-ram-boot-guide.md)

<a id="nor-bundle"></a>
## 2. NOR導入用のbundle

`--capacity-bytes` には、対象実機の `opensbi` NOR区画で測定した容量をバイト単位で指定します。
`20261124-165032/spl-fastboot.log` にある値は、RAM起動時のUSB転送上限です。

開発PCのリポジトリルートで、対象実機の容量を `CAPACITY` に設定します。
対象実機の区画が採取記録 `20261120-101205` と一致する場合は、その
`size.txt` を使えます。記録値は393216バイト（384 KiB）です。

```bash
CAPACITY=$(cat hardware/jupiter2/captures/20261120-101205/opensbi-partition-info-20261120-102404/size.txt)
```

対象実機で採取したJSONを使う場合は、そのJSONを
`hardware/jupiter2/captures/<採取ID>/jupiter2-nor-capacity.json` に保存し、
`CAPTURE_ID` に該当する採取IDを設定して実行します。
[READMEのNOR区画採取手順](../README.md#capture-nor)

```bash
CAPACITY=$(python3 -c 'import json, sys; print(json.load(sys.stdin)["capacity_bytes"])' \
  < "hardware/jupiter2/captures/${CAPTURE_ID:?対象実機の採取IDを設定してください}/jupiter2-nor-capacity.json")
```

容量を指定してbundleを作ります。すでに同じ構成のビルドが完了している場合は、
`make opensbi keystone JOBS=20` の行を省略できます。

```bash
OUT="$PWD/work/jupiter2-release-$(date +%Y%m%d-%H%M%S)"
(
    set -eu
    python3 scripts/check-jupiter2-install-capacity.py \
      --capacity-bytes "${CAPACITY:?先に実機のNOR区画容量を設定してください}"
    make opensbi keystone JOBS=20
    python3 scripts/build-jupiter2-install-image.py --capacity-bytes "$CAPACITY" --output "$OUT"
    cd "$OUT"
    sha256sum -c bundle.tar.gz.sha256
)
```

出力は `bundle/firmware/fw_dynamic.itb`、Linux・モジュール・Keystoneアプリを含む
`bundle.tar.gz` とそのSHA-256です。包装時に最終ITB全体が対象NOR区画に収まるか、
Linux Imageとドライバが対応するかを検査します。
実機へ転送するのは `$OUT/bundle.tar.gz` と `$OUT/bundle.tar.gz.sha256` です。
展開後の事前検査、Linuxの配置とinitrd生成、起動確認は実機導入手順に従います。
[bundleの転送と事前検査](milkv-jupiter2-stack-install.md#4-bundleの転送と事前検査)

<a id="nor-firmware-only"></a>
### OpenSBIのFITだけを包装する場合

レビュー済みのOpenSBIがビルド済みで、FITだけを配布する場合は、
対象実機から測定した同じ`CAPACITY`と、新しい出力先を指定します。

```bash
OUT="$PWD/work/jupiter2-firmware-$(date +%Y%m%d-%H%M%S)"
python3 scripts/build-jupiter2-install-image.py --firmware-only \
  --capacity-bytes "${CAPACITY:?先に実機のNOR区画容量を設定してください}" --output "$OUT" &&
  (cd "$OUT" && sha256sum -c bundle.tar.gz.sha256)
```

別途確認したBINを使う場合は、`--firmware-bin /absolute/path/fw_dynamic.bin`を追加します。
この配布物にはFIT、検証・操作用ツールと文書が含まれます。
[OpenSBIの更新・復旧手順](milkv-jupiter2-opensbi-replacement.md)

USB RAM起動で使うFSBLと統合FITを配布する場合は、第1.7節でbundleを作ります。
[BootROM用FSBLと統合FITの包装手順](#ram-boot-bundle)
