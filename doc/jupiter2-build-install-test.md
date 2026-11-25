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

OP-TEE入りの2構成では、既存のビルダーでCoreをFITに格納できます。
実機向けのドメイン設定を含む起動経路と実機での動作は未検証です。
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

K3用クロスツールチェーンをPATHに置き、接頭辞は導入したものに合わせます。
NOR用の包装スクリプトにはPython 3.11以上が必要です。
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
sudo apt-get install python3-pyelftools
python3 -c 'from elftools.elf.elffile import ELFFile'

OPTEE_WORK="$PWD/.build-k3/optee-hardware"
OPTEE_SRC="$OPTEE_WORK/optee_os"
OPTEE_REV=2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59
mkdir -p "$OPTEE_WORK"
if [ ! -e "$OPTEE_SRC" ]; then
    git clone https://github.com/spacemit-com/optee_os.git "$OPTEE_SRC"
    git -C "$OPTEE_SRC" checkout --detach "$OPTEE_REV"
fi
test "$(git -C "$OPTEE_SRC" rev-parse HEAD)" = "$OPTEE_REV" &&
make -C "$OPTEE_SRC" -j20 O="$OPTEE_WORK/out" ARCH=riscv PLATFORM=k3 \
  CROSS_COMPILE="$CROSS_COMPILE" CROSS_COMPILE_core="$CROSS_COMPILE" \
  CROSS_COMPILE_ta_rv64="$CROSS_COMPILE" CFG_K3_HUK_ALLOW_UNFUSED=n

TEE_BIN="$OPTEE_WORK/out/core/tee.bin"
test -s "$TEE_BIN"
"${CROSS_COMPILE}readelf" -h -l "$OPTEE_WORK/out/core/tee.elf"
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
OP-TEE Coreは1.2節で作った `TEE_BIN` を使います。

```bash
make opensbi keystone JOBS=20
SBI="$PWD/.build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic"
OUT="$PWD/work/jupiter2-ram-boot/keystone-optee-$(date +%Y%m%d-%H%M%S)"
VARIANT=keystone
```

### 1.5 OP-TEE入りFITを作る（1.3・1.4共通）

選んだ構成で設定した `SBI`、`OUT`、`VARIANT` と、1.2節の `TEE_BIN` を引き継ぎます。

```bash
ESOS_CONFIGURATION=$(python3 -c 'import json, sys; print(json.load(sys.stdin)["esos_configuration"])' \
  < hardware/jupiter2/vendor-fit.json)
python3 scripts/build-jupiter2-reference-ram-boot.py \
  --opensbi-bin "$SBI.bin" --opensbi-elf "$SBI.elf" \
  --esos-itb hardware/jupiter2/vendor/esos.itb --esos-configuration "$ESOS_CONFIGURATION" \
  --optee-bin "$TEE_BIN" --variant "$VARIANT" --cross-compile "$CROSS_COMPILE" \
  --jobs 20 --output "$OUT"

FIT="ram-boot-$VARIANT.itb"
dumpimage -l "$OUT/release/images/$FIT"
fdtget -t s "$OUT/release/images/$FIT" /configurations/conf_11 loadables
(cd "$OUT/release" && sha256sum -c records/FSBL.bin.sha256 "records/$FIT.sha256")
```

一覧に `optee` があり、Coreのロード・エントリアドレスが `0x171000000` で
`tee.elf` の配置と一致することを確認します。同梱構成とKeystoneのみのFITは
同じファイル名になるため、出力ディレクトリで区別してください。

**実機起動前に必要な作業**。参照ビルダーの `--optee-bin` はCoreを格納します。
OpenSBIへ渡すDTBのOP-TEEドメインとMPXY設定を追加する機能はありません。
`$OUT/records/opensbi-uboot.dtb` で、Coreへの初回引き渡し、対象hart、
Core・共有メモリの予約、実機の周辺機器へのアクセスとPMP割り当てを照合してください。
その設定を含む実機用U-Boot FITの準備と、その構成での起動検証が必要です。
Linux用DTBのOP-TEEノードも別途確認します。
[実機移植計画](jupiter2-optee-ftpm-porting-plan.md) · [同居設計](keystone-optee-coexistence-design.md)

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

## 2. NOR導入用のbundle

[READMEのNOR区画採取手順](../README.md#capture-nor)で
保存したJSONを指定し、開発PCのリポジトリルートで実行します。

```bash
CAPTURE_ID=20261124-165032  # 実機で採取したIDに置き換える
CAPTURE_DIR="$PWD/hardware/jupiter2/captures/$CAPTURE_ID"
make opensbi keystone JOBS=20
CAPACITY=$(python3 -c 'import json, sys; print(json.load(sys.stdin)["capacity_bytes"])' \
  < "$CAPTURE_DIR/jupiter2-nor-capacity.json")
OUT="$PWD/work/jupiter2-release-$(date +%Y%m%d-%H%M%S)"
python3 scripts/build-jupiter2-install-image.py --capacity-bytes "$CAPACITY" --output "$OUT"
(cd "$OUT" && sha256sum -c bundle.tar.gz.sha256)
```

出力は `bundle/firmware/fw_dynamic.itb`、Linux・モジュール・Keystoneアプリを含む
`bundle.tar.gz` とそのSHA-256です。包装時に最終ITB全体が対象NOR区画に収まるか、
Linux Imageとドライバが対応するかを検査します。
実機への書き込み、既存イメージのバックアップ・復旧、導入後の起動確認は
[実機導入・復旧手順](milkv-jupiter2-stack-install.md) に従います。
