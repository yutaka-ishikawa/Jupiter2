# Jupiter2実機用イメージのビルド・導入・試験

USBで一時起動する場合はRAM起動用のFSBLと統合FITを作ります。
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

対象機がSPL Fastboot段階にあるとき、開発PCで以下を実行します。
複数台を接続している場合は `fastboot -s SERIAL getvar max-download-size` で対象を選びます。

```bash
mkdir -p work/jupiter2-ram-boot
fastboot getvar max-download-size 2>&1 | tee work/jupiter2-ram-boot/spl-fastboot.log
OUT="$PWD/work/jupiter2-ram-boot/keystone-capture-$(date +%Y%m%d-%H%M%S)"
FASTBOOT_LOG="$PWD/work/jupiter2-ram-boot/spl-fastboot.log" \
  JOBS=20 bash scripts/build-jupiter2-ram-boot.sh "$OUT"
```

| 変数 | 既定値と用途 |
| --- | --- |
| `CROSS_COMPILE` | `riscv64-unknown-linux-gnu-`。K3ツールチェーンの接頭辞 |
| `JOBS` | `nproc`。ビルドの並列数 |
| `K3_BUILD_DIR` | `.build-k3`。OpenSBIのビルド出力先 |
| `ESOS_ITB` | `hardware/jupiter2/vendor/esos.itb`。対象実機に対応するESOS FIT |
| `ESOS_CONFIGURATION` | `conf_dual`。ESOS FITの構成名 |
| `FASTBOOT_LOG` | 未指定時は生成SPLの設定を使う。指定時は対象SPLの `getvar` 採取ログ |

実機では、生成したペアをUSBから転送し、UARTでOpenSBI・U-Boot・Linuxの順に
起動を確認します。続けて実機向けのLinuxとKeystoneドライバで `hello` と
`hello-native` を試験します。
[USB・UART起動手順](jupiter2-ram-boot-guide.md) · [Keystoneアプリの実機試験](jupiter2-keystone-app-test.md)

## 2. NOR導入用のbundle

実機LinuxでOpenSBI用NOR区画の容量を採取します。以下のスクリプトはsysfsを読み取ります。
得られたJSONを開発PCにコピーします。

```bash
python3 scripts/check-jupiter2-install-capacity.py --json > jupiter2-nor-capacity.json
```

開発PCで、採取したJSONをカレントディレクトリに置いて実行します。

```bash
make opensbi keystone JOBS=20
CAPACITY=$(python3 -c 'import json, sys; print(json.load(sys.stdin)["capacity_bytes"])' \
  < jupiter2-nor-capacity.json)
OUT="$PWD/work/jupiter2-release-$(date +%Y%m%d-%H%M%S)"
python3 scripts/build-jupiter2-install-image.py --capacity-bytes "$CAPACITY" --output "$OUT"
(cd "$OUT" && sha256sum -c bundle.tar.gz.sha256)
```

出力は `bundle/firmware/fw_dynamic.itb`、Linux・モジュール・Keystoneアプリを含む
`bundle.tar.gz` とそのSHA-256です。包装時に最終ITB全体が対象NOR区画に収まるか、
Linux Imageとドライバが対応するかを検査します。
実機への書き込み、既存イメージのバックアップ・復旧、導入後の起動確認は
[実機導入・復旧手順](milkv-jupiter2-stack-install.md) に従います。
