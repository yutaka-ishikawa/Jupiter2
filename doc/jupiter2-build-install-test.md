# Jupiter2実機用イメージのビルド・導入・試験

USBで一時起動する場合はRAM起動用のFSBLと統合FITを作ります。

生成されるファイルは次の2つです。

- `$OUT/release/images/FSBL.bin`
- `$OUT/release/images/ram-boot-keystone.itb`

`$OUT` はビルド時に指定する出力ディレクトリです。以下の実行例では
リポジトリ直下の `work/jupiter2-ram-boot/keystone-<日時>/` です。

実機のOpenSBI用NOR区画へ導入する場合は、容量を採取して配布用bundleを作ります。
以下はKeystone SMを含む現在のソースから実機向け候補を作る手順です。

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

### 生成イメージを実機で確認する

実機では、生成したペアをUSBから転送し、UARTでOpenSBI・U-Boot・Linuxの順に
起動を確認します。続けて実機向けのLinuxとKeystoneドライバで `hello` と
`hello-native` を試験します。
[USB・UART起動手順](jupiter2-ram-boot-guide.md) · [Keystoneアプリの実機試験](jupiter2-keystone-app-test.md)

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
