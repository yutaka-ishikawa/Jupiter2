# Milk-V Jupiter2 / SpacemiT K3：Keystone開発・導入ガイド

Milk-V Jupiter2でKeystoneを動かすためのQEMU、OpenSBI＋Security Monitor（SM）、
Linux、SDK、Eyrie、sampleをまとめたソースツリーです。
実機の情報を取得し、開発PCでビルド・試験した後、実機へ段階的に導入します。

## 目次

1. [目的と全体の作業順序](#overview)
2. [フェーズ1：実機情報の取得とバックアップ](#phase-info)
3. [フェーズ2：開発PCでのビルド](#phase-build)
4. [フェーズ3：実機への配置と起動確認](#phase-deploy)
5. [個別修正後の再ビルド・再配置](#rebuild)
6. [既知の制約・不具合・検証状況](#status)
7. [詳細ドキュメント一覧](#documents)

<a id="overview"></a>
## 1. 目的と全体の作業順序

| フェーズ | 作業場所 | 完了時にそろうもの |
| --- | --- | --- |
| 1. 実機情報の取得 | 実機Linux・UART、保存先は開発PC | CPU/OS/DTB/起動設定/区画情報、元の起動環境のバックアップ |
| 2. ビルドと試験 | 開発PC、QEMUのLinux guest | 対応するfirmware/kernel/driver/apps、試験記録、転送用イメージ |
| 3. deployと確認 | 開発PC、UARTのU-Boot、実機Linux | 新Linuxの起動確認、新SMのRAM起動、sampleの動作確認 |

実機への導入順は、**既存ファームウェアで新Linuxを一時起動 → 正常ならLinux起動設定を保存 → 新OpenSBI＋SMをRAM起動 → sample試験 → 必要ならNOR更新**です。
各段階の成功を確認してから次へ進みます。

同じ「install」でも、対象が異なります。

| 操作 | 対象・役割 |
| --- | --- |
| 開発PCの`make install` | ビルド済み成果物を`install/keystone/`へ配置し、QEMU用rootfsを作成・更新 |
| 実機の`sudo bash tools/install-linux.sh` | bundleから実機のLinux Image・modules・driver・hello二種を追加配置 |
| UARTでの一時起動 | RAM上の設定で起動確認。起動設定ファイルやNORの更新とは別工程 |
| 実機でのNOR書き込み | 確認済みの最終ITBをOpenSBI区画へ書き込む工程 |

ソースは`qemu/`、`opensbi/`、`keystone/`、`linux-k3/`、アプリは`samples/`にあります。
`patches/`には取込み・移植用パッチを保持しています。

<a id="phase-info"></a>
## 2. フェーズ1：実機情報の取得とバックアップ

### 2.1 UART接続と開発PC側の準備

配線、電圧、PCのシリアル端末、通信設定、U-Bootへの入力方法は
[UART接続手順](doc/milkv-jupiter2-uart.md)を参照してください。
PCの操作ターミナルとUART端末を分け、電源投入からのUARTログを保存します。

### 2.2 導入前の実機情報を採取

比較・導入の対象となるLinuxを実機で起動し、変更を加える前に実行します。
同じ端末で2.3まで進め、同じ `INFO_DIR` を使います。
Linux側の情報は下のコマンドで一括採取します。NOR区画容量の取得には、
2.3節の既存スクリプトを使います。

```bash
set -e
CAPTURE_ID="$(date +%Y%m%d-%H%M%S)"
INFO_DIR="$HOME/jupiter2-linux-capture-$CAPTURE_ID"
mkdir -m 700 "$INFO_DIR"

date -Iseconds > "$INFO_DIR/captured-at.txt"
uname -a > "$INFO_DIR/uname.txt"
LC_ALL=C lscpu > "$INFO_DIR/lscpu.txt"
cat /proc/cpuinfo > "$INFO_DIR/cpuinfo.txt"
cat /sys/devices/system/cpu/online > "$INFO_DIR/cpu-online.txt"
cat /proc/meminfo > "$INFO_DIR/meminfo.txt"
sudo cat /proc/iomem > "$INFO_DIR/iomem.txt"
sudo dmesg > "$INFO_DIR/dmesg.txt"
if sudo test -s /sys/firmware/fdt; then
    sudo cat /sys/firmware/fdt > "$INFO_DIR/running.dtb"
    test -s "$INFO_DIR/running.dtb"
elif sudo test -d /sys/firmware/devicetree/base && command -v dtc >/dev/null; then
    sudo dtc -I fs -O dtb /sys/firmware/devicetree/base > "$INFO_DIR/running-reconstructed.dtb"
    printf '%s\n' 'Original FDT unavailable; reconstructed from sysfs' >> "$INFO_DIR/capture-notes.txt"
else
    printf '%s\n' 'Original FDT unavailable; no sysfs DTB collected' >> "$INFO_DIR/capture-notes.txt"
fi

lsblk -f > "$INFO_DIR/lsblk.txt"
findmnt > "$INFO_DIR/findmnt.txt"
findmnt --target / > "$INFO_DIR/root-mount.txt"
findmnt --target /boot > "$INFO_DIR/boot-mount.txt"
cat /proc/cmdline > "$INFO_DIR/cmdline.txt"
if test -r /proc/mtd; then
    cat /proc/mtd > "$INFO_DIR/proc-mtd.txt"
else
    printf '%s\n' '/proc/mtd is unavailable' >> "$INFO_DIR/capture-notes.txt"
fi
if sudo test -f /boot/env_k3.txt; then
    sudo cat /boot/env_k3.txt > "$INFO_DIR/env_k3.txt"
else
    printf '%s\n' '/boot/env_k3.txt is absent' >> "$INFO_DIR/capture-notes.txt"
fi
```

採取ファイルは以下の用途で使います。

| ファイル | 採取する情報 |
| --- | --- |
| `captured-at.txt`、`uname.txt` | 採取日時、実行中のLinuxの版 |
| `lscpu.txt`、`cpuinfo.txt`、`cpu-online.txt` | CPU構成、各CPUの情報、オンラインCPUの範囲 |
| `meminfo.txt`、`iomem.txt`、`dmesg.txt` | Linuxから見えるRAM容量、物理メモリ配置、カーネルログ |
| `running.dtb` | 実機Linuxに渡されたFDTの原本。原本がない場合は再構成版を `running-reconstructed.dtb` として保存 |
| `lsblk.txt`、`findmnt.txt`、`root-mount.txt`、`boot-mount.txt` | ストレージ、全マウント、`/` と `/boot` を含むファイルシステム |
| `cmdline.txt`、`proc-mtd.txt`、`env_k3.txt` | Linux起動引数、MTD区画、使用中の起動設定（存在する場合） |
GRUBやextlinuxを使用している場合は、[導入手順の第5章](doc/milkv-jupiter2-stack-install.md#5-実機の現状記録とバックアップ)
に従って使用中の設定もこのディレクトリに保存します。起動媒体、
ボード型番、ファームウェアの版、選択したDTB名も `capture-notes.txt` に追記します。

Jupiter2はX100とA100の混成です。CPUの種類やLinuxのonline数だけでPMPの能力を推定せず、
ファームウェアのHart別ログも確認します。既知の構成は[実機調査](hardware/jupiter2/jupiter2-hardware-compatibility.md)、
PMPの16/32個混在は[対応計画と結果](doc/jupiter2-heterogeneous-pmp-plan.md)を参照してください。

<a id="capture-nor"></a>
### 2.3 NOR区画容量の確認とファームウェアのバックアップ

[OpenSBI区画のバックアップ](doc/milkv-jupiter2-opensbi-replacement.md#capture-opensbi-partition)と
[Linux起動設定のバックアップ](doc/milkv-jupiter2-stack-install.md#5-実機の現状記録とバックアップ)に従い、
同じ `INFO_DIR` の下に区画情報・元OpenSBI・起動設定を保存します。
バックアップのハッシュを記録し、対応する復旧方法と販売元FSBL/U-Bootの入手元も確認します。

NORへ導入する場合は、既存の [容量確認スクリプト](scripts/check-jupiter2-install-capacity.py)
を実機にコピーし、同じ端末で実行します。このスクリプトはsysfsから
`opensbi` 区画のデバイス名、NOR容量、消去単位を取得し、bundle作成で使う
`capacity_bytes` をJSONに出力します。

```bash
python3 scripts/check-jupiter2-install-capacity.py --json > "$INFO_DIR/jupiter2-nor-capacity.json"
```

今回の実測では`mtd5`の`opensbi`が`0x60000`＝393216 bytes（384 KiB）です。
番号や容量は実機の`/proc/mtd`で再確認してください。
詳しい読取り調査は[SPI NOR調査](doc/jupiter2-spi-nor-inspection.md)を参照してください。

<a id="capture-save"></a>
### 2.4 取得情報・バックアップを開発PCへ保存

**作成後は、記録・バックアップのディレクトリ全体を実機外の開発PCの `hardware/jupiter2/captures/<採取ID>/` にコピーしてください。**
実機の `INFO_DIR` の中身をそこに配置し、開発PCで記録した電源投入からのUARTログを
`uart.log` として同じ場所に保存します。SPLのUSB転送上限も採取する場合は、
対象機をSPL Fastboot段階にして、開発PCで次を実行します。複数台が接続されている
場合は `fastboot -s SERIAL` で対象機を指定します。

```bash
CAPTURE_ID=20261124-165032  # 実機で採取したIDに置き換える
CAPTURE_DIR="$PWD/hardware/jupiter2/captures/$CAPTURE_ID"
(
    set -o pipefail
    cd "$CAPTURE_DIR" || exit
    fastboot getvar max-download-size 2>&1 | tee spl-fastboot.log
)
```

販売元から入手した同一リリースの `FSBL.bin`、`esos.itb`、`fw_dynamic.itb`、
`u-boot.itb` は `hardware/jupiter2/vendor/` に置きます。入手元・リリース・
SHA-256を記録し、現在の実機に対応することを照合してください。差し替えた場合は、
既存の `scripts/extract-jupiter2-vendor-dtbs.py` でU-Boot用DTBと
ESOSのRCPU用DTBを同じ `vendor/` に抽出します。
[保存先とDTB抽出手順](hardware/jupiter2/README.md)

開発PCのリポジトリルートで `CAPTURE_ID` を設定し、コピーとログ採取が済んだ後に
全ファイルのハッシュを記録します。

```bash
CAPTURE_ID=20261124-165032  # 実機で採取したIDに置き換える
(
    set -euo pipefail
    cd "hardware/jupiter2/captures/$CAPTURE_ID"
    find . -type f ! -path ./SHA256SUMS -print0 |
        sort -z | xargs -0 -r sha256sum > SHA256SUMS
    sha256sum -c SHA256SUMS
)
```

QEMUが生成したDTBやDTSは `.build-k3/dtb-compare/` に置きます。
実機の採取ディレクトリは実機が起動しなくなった場合にも取り出せる場所に保存します。

### 採取ファイルとビルドの対応

| 用途 | スクリプトが実際に使う入力 |
| --- | --- |
| Keystone版RAM起動イメージ | `scripts/build-jupiter2-ram-boot.sh` は `vendor/esos.itb` と `vendor-fit.json` のESOS構成を使い、OpenSBI・FSBL・U-Bootをビルドします。採取した上限は `FASTBOOT_LOG="$CAPTURE_DIR/spl-fastboot.log"` で渡す場合に使います。 |
| NOR導入用bundle | 実機で採取した `jupiter2-nor-capacity.json` の `capacity_bytes` を読み取り、`scripts/build-jupiter2-install-image.py` に `--capacity-bytes` で渡します。 |
| 販売元DTB抽出 | `scripts/extract-jupiter2-vendor-dtbs.py` は `vendor-fit.json`、`vendor/u-boot.itb`、`vendor/esos.itb` を読み、`vendor/` にDTBを出力します。 |
| LinuxビルドとQEMU起動 | Linuxビルドは `hardware/jupiter2/linux.config`、`run-k3.sh` は `hardware/jupiter2/qemu.conf` を読みます。 |

`running.dtb` とLinux・UARTの採取記録は構成の照合や復旧に使います。
通常のビルドは `captures/` を自動検索しません。実機LinuxのDTBを加工する場合は
`scripts/prepare-jupiter2-keystone-linux-dtb.py` の `--input` に対象DTBを明示します。
[実機用イメージのビルド手順](doc/jupiter2-build-install-test.md)

ここまでで元の起動構成と復旧に必要な情報をそろえてから、deployへ進みます。

<a id="phase-build"></a>
## 3. フェーズ2：開発PCでのビルド

### 3.1 cloneと依存ツールのインストール

以下はUbuntu 24.04等のAPT系開発PCで実行します。

```bash
git clone https://github.com/yutaka-ishikawa/public.git
cd public
sudo bash scripts/install-build-deps.sh

# FIT作成・ESOS展開・実機へのRAM転送に使う追加ツール
sudo apt-get install -y u-boot-tools lzop fastboot
```

コンパイルは通常ユーザーで実行します。既定のcross prefixは`riscv64-linux-gnu-`です。
初回のQEMU・ゲストツール・rootfs等の準備には、外部ソースの取得が発生する場合があります。

### 3.2 make buildが生成するものと出力先

```bash
make build JOBS=20
```

QEMU、OpenSBI＋SM、Linuxとmodules、SDK/Eyrie、Keystone driver、sample群、
乱数・暗号の各profile、verificationプログラムと検証用modulesをビルドします。
**このコマンドではQEMU試験、実機への配置、RAM用統合FITの作成、NOR書き込みは行いません。**

| 成果物・用途 | 既定の場所 |
| --- | --- |
| QEMU/Linux/通常firmwareの作業領域 | `.build-k3/` |
| SDK/Eyrie/driverの作業領域 | `.build-keystone/` |
| 配置前の成果物 | `.build-keystone/stage/` |
| sampleのELF・runner・配布package | `samples/*/build/` |
| verificationの成果物 | `verifications/`内の各buildディレクトリ |
| 開発PCの`make install`による配置先 | `install/keystone/` |

`JOBS=20`は各ビルド工程内の並列数です。工程の順序はMakefileが管理します。
変数・個別ターゲット・出力の詳細は[make手順](doc/make-build-install.md)を参照してください。

### 3.3 OpenSBI＋Keystone SMのビルド

SMだけを変更した場合は、全体ビルドの代わりに次を実行します。

```bash
make firmware JOBS=20
```

通常の起動用BINは次です。SM単体の`sm-combined.o`では起動しません。

```text
.build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin
```

通常版のcrypto providerは`unavailable`です。QEMU開発鍵を使う`qemu-dev`は別profileで、
helloの動作からattestation/sealingの利用可否を判断しないでください。
SMの最適化・生成サイズは[サイズ調査](doc/jupiter2-firmware-size-reduction.md)を参照してください。

### 3.4 Linuxカーネル・モジュール・ドライバーのビルド

個別にビルドする場合の入口です。

```bash
make linux JOBS=20
make keystone JOBS=20
```

`make keystone`は依存するSM・Linux・SDK/Eyrieも処理し、対応driverとguest-overlayを作ります。
Imageは`.build-k3/linux/arch/riscv/boot/Image`、driverは`.build-keystone/driver/keystone-driver.ko`です。
実機へは同じkernel buildに対応するmodulesとdriverを配置します。

### 3.5 SDK・Eyrie・sampleのビルド

```bash
make samples JOBS=20
```

依存するSDKと二つのEyrie profileも準備します。

```text
samples/helloworld/build/hello.ke
samples/hello-native/build/hello-native.ke
samples/attestation/build/attestor.ke
samples/tests/build/tests.ke
```

`test-loop`等のEnclave用ELFはrunner経由で起動します。Linuxから直接実行するプログラムではありません。
構成と実行方法は[samples](samples/README.md)、既存examplesとの関係は[統合説明](doc/keystone-examples-integration.md)を参照してください。

### 3.6 QEMUでの動作確認

ビルド完了後、起動中のQEMUを停止し、開発PCの実行用ディレクトリへ配置します。

```bash
make install
bash scripts/run-k3.sh --image keystone --pmp-profile mixed
```

`make install`は再コンパイルせず、`install/keystone/`とQEMU用rootfsを作成・更新します。
実機には書き込みません。初回はBianbu baseアーカイブを取得する場合があります。

起動確認に加え、sampleのCREATE/RUN、OCALL、RESUME、正常終了、DESTROYまで試験します。
全Hartの起動だけでは、ホストへの共有メモリー復帰等の不具合は検出できません。
[QEMU運用手順](doc/jupiter2-qemu-operations.md)、[sample実行](samples/README.md)、
[verification](verifications/README.md)へ進んでください。
現在の`samples/run-qemu.py`による通常試験と、混在PMP用の専用試験の範囲は区別します。

### 3.7 RAM起動用イメージの作成

販売元OpenSBIによる基準確認と、開発したSM版の試験を分けます。
`make firmware`の後に、FSBL/U-BootとESOSを含む統合FITを作ります。

| 入力・工程 | 手順 |
| --- | --- |
| 販売元OpenSBI、ESOS等の入手・抽出と確認 | [RAM起動の準備手順](doc/jupiter2-ram-boot-procedure.md) |
| 固定ソースからFSBL/U-Bootと販売元版統合FITを生成 | [実機用ビルド手順書](doc/jupiter2-build-install-test.md#ram-boot-images) |
| ビルドしたSMのBINを使ってKeystone版を生成 | [SM起動・アプリ試験第4章](doc/jupiter2-keystone-app-test.md) |

使用するスクリプトは`scripts/build-jupiter2-reference-ram-boot.py`です。
成功すると指定出力先の`release/images/`にFSBLと統合FITが生成されます。
**新しく作ったFSBLと統合FITを対で使います。** `make build`やNOR用bundle作成だけでは、この対は生成されません。

### 3.8 NOR容量確認と実機配布用bundleの作成

通常のfirmware、Linux、driver、appsがそろった後に、開発PCで実行します。
以下の393216は今回の実測値です。フェーズ1で確認した実機容量と一致させます。

```bash
python3 scripts/build-jupiter2-install-image.py \
  --capacity-bytes 393216 \
  --output work/jupiter2-release
```

成功すると、最終の`fw_dynamic.itb`を作り、容量検査後に次を出力します。
出力先は未作成のディレクトリを指定します。

```text
work/jupiter2-release/
├── bundle/
│   ├── firmware/
│   ├── linux/
│   ├── modules/
│   ├── apps/
│   ├── tools/
│   └── docs/
├── bundle.tar.gz
└── bundle.tar.gz.sha256
```

これはRAM起動用`release/`とは別の配布物です。
[導入手順第4章](doc/milkv-jupiter2-stack-install.md)に、依存ツール、同梱内容、容量の再確認を記載しています。

<a id="phase-deploy"></a>
## 4. フェーズ3：実機への配置と起動確認

### 4.1 成果物を実機へ転送する

フェーズ1のバックアップを開発PCにも保存済みであることを確認します。
Linux配布用bundleはディレクトリ全体を実機へ転送します。
RAM転送用の`release/`はfastbootを実行するPCで使用します。
各配布物のmanifest・SHA-256と、使用するソース版を記録します。

### 4.2 Linux・モジュール・sampleを配置する

実機上の、展開したLinux配布用`bundle/`内で実行します。

```bash
sudo bash tools/install-linux.sh
```

Image、対応modules、Keystone driver、hello二種を追加配置します。
**この操作だけでは新Linuxを起動しません。initrd生成、起動設定変更、firmware書き込みも別工程です。**
配置先と事前確認は[導入手順第6章](doc/milkv-jupiter2-stack-install.md)を参照してください。
途中で失敗した場合、全体の自動rollbackは行わないため、部分配置を確認してから再実行します。

### 4.3 initrdを生成し、使用するDTBを準備する

インストールしたkernelの実際のreleaseを調べ、そのrelease用のinitrdを生成します。
今回のreleaseは`6.18.3`で、Imageファイル名の`-keystone`とは区別します。
[initrd生成手順](doc/milkv-jupiter2-stack-install.md)と
[Keystone用Linux DTBの準備](doc/jupiter2-keystone-app-test.md)を参照してください。
既存のImage/initrd/DTBを残して、別名の候補を配置します。

### 4.4 既存ファームウェアで新しいLinuxを一時起動する

**第1段階では`/boot/env_k3.txt`を編集せず、UARTのU-Bootで候補のkernel/initrd/DTBを指定します。**
`knl_name`、`ramdisk_name`、`dtb_dir`、`fdtfile`を含む値を実際の配置先に合わせ、saveenvを使わず起動します。
[導入手順第7章](doc/milkv-jupiter2-stack-install.md)のU-Boot手順で、Linux・UFS・ネットワーク等を確認します。
起動できなければ、元の起動設定で復帰し、次の段階へ進みません。

### 4.5 正常起動後にLinuxの起動設定を保存する

同じkernel/initrd/DTBの組合せで正常起動できた後に、今回のBianbu構成では`/boot/env_k3.txt`へ反映します。
元ファイルをバックアップしたまま保持し、通常起動でも同じ新kernelが動くことを確認します。
実際の起動経路と保存する変数は[導入手順](doc/milkv-jupiter2-stack-install.md)に従います。

### 4.6 新しいOpenSBI＋SMをRAM起動して確認する

第1段階が成功した後、開発PCからFDL/fastbootで新しいFSBL・統合FITをRAMへ転送します。
UARTでOpenSBI/SM初期化を確認し、UFS上の確認済みLinuxを起動します。

操作は[RAM起動ガイド](doc/jupiter2-ram-boot-guide.md)、SM版の選択と判定は
[SM起動・アプリ試験](doc/jupiter2-keystone-app-test.md)を参照してください。
この段階ではNORを書き換えません。

### 4.7 Keystone sampleを実行する

実機Linuxでkernel release、全16 CPUのonline、対応driverと`/dev/keystone_enclave`を確認し、
[アプリ試験第6章](doc/jupiter2-keystone-app-test.md)の直接コマンドでhello二種を一つずつ実行します。
今回の配置先は次です。

```text
/opt/keystone/6.18.3/hello.ke
/opt/keystone/6.18.3/hello-native.ke
```

アプリの期待出力・終了コード0・DESTROYと、SM/Linuxに例外がないことを確認します。
失敗した場合はUARTとdmesgを保存し、[不具合台帳](doc/keystone-bug-report.md)と照合します。
UTM読み取りの終了139については[KSB-073の修正・試験結果](doc/jupiter2-utm-host-access-issue.md)を参照してください。

### 4.8 RAM起動で確認後、必要に応じてNORへ書き込む

RAM起動とsample試験の成功後、永続的なfirmware更新が必要な場合に実施します。
実機の容量・バックアップ・最終ITBのhashを再確認し、
[導入手順第8章](doc/milkv-jupiter2-stack-install.md)の書き込み・読み戻し・再起動確認へ進みます。
RAM起動用の統合FITを、そのままNORのOpenSBI区画へ書く手順ではありません。

### 4.9 各段階のrollbackとFDLリカバリー

第1段階は元のkernel/initrd/DTB・起動設定へ戻します。
NOR更新後に失敗した場合は、実機外にも保存した元OpenSBIのバックアップを使って復旧します。
[導入手順第10章](doc/milkv-jupiter2-stack-install.md)と
[RAM起動・FDL準備](doc/jupiter2-ram-boot-procedure.md)に、起動できない場合の復旧経路を記載しています。

<a id="rebuild"></a>
## 5. 個別コンポーネントを修正した場合の再ビルド・再配置

| 変更したもの | 開発PCでの主なbuild | その後の作業 |
| --- | --- | --- |
| SM/OpenSBI | `make firmware JOBS=20` | RAM統合FITを再作成し、同じLinuxで再試験。QEMU用は`make install-opensbi` |
| kernel/driver | `make keystone JOBS=20` | 対応Image/modules/driverを再配布し、initrd生成と一時起動を再確認 |
| SDK/Eyrie | `make samples JOBS=20` | 二つのruntime profileとpackageを更新し、OCALL・正常終了まで再試験 |
| sampleアプリのみ | `make -C samples` | 作成したpackageを更新。SDK/runtime準備済みの場合 |
| QEMUモデル | `make qemu JOBS=20` | `make install-qemu`後、既存構成と変更対象構成で再試験 |

buildとinstallには同じ`K3_BUILD_DIR`、`KEYSTONE_BUILD_DIR`、`PREFIX`を指定します。
`make install`は古い成果物の鮮度を自動判定しないため、ソース変更後はbuild→installの順に実行します。
ビルド先の変更、cleanup、既存rootfsの更新は[make手順](doc/make-build-install.md)と
[QEMU運用手順](doc/jupiter2-qemu-operations.md)を参照してください。

<a id="status"></a>
## 6. 既知の制約・不具合・検証状況

- 実機では販売元版を含む参照RAM起動経路でU-Boot・UFS・Linux起動を確認しています。
- KSB-073修正後は、実QEMUのLinux guestで提供hello二種を一律/混在PMP構成とCPU3/8で実行し、計8回の正常終了を確認しました。
  修正前の同じ位置のload access fault・終了139もQEMUで再現しています。
- これは全sample・全verification suite、修正版の実機hello、DMA隔離、attestation/sealingの一括合格ではありません。
- QEMUの実機との差は[PMP・domain・周辺機器の不足一覧](doc/jupiter2-qemu-hardware-test-gaps.md)、
  バグごとの修正・試験範囲は[不具合台帳](doc/keystone-bug-report.md)を参照してください。
- LinuxのSstcとSMのM_TIMERは[共存方式](doc/keystone-sstc-coexistence.md)を使います。
  過去のSstcを抑止する方針と、現在の実装を混同しないでください。

<a id="documents"></a>
## 7. 詳細ドキュメント一覧

| 用途 | ドキュメント |
| --- | --- |
| ビルド全般・出力・install・変数 | [makeによるビルドと配置](doc/make-build-install.md) |
| UART接続・PC端末設定 | [UART接続手順](doc/milkv-jupiter2-uart.md) |
| 実機情報・CPU/メモリーの記録 | [実機調査](hardware/jupiter2/jupiter2-hardware-compatibility.md)、[インベントリ](hardware/jupiter2/jupiter2-hardware-inventory.json) |
| バックアップ・Linux配置・NOR更新・復旧 | [実機導入手順](doc/milkv-jupiter2-stack-install.md)、[OpenSBI置換調査](doc/milkv-jupiter2-opensbi-replacement.md) |
| RAM起動の操作・イメージ作成 | [RAM起動ガイド](doc/jupiter2-ram-boot-guide.md)、[準備・判断手順](doc/jupiter2-ram-boot-procedure.md) |
| RAM起動したU-Bootから販売元Linuxを起動 | [販売元Linuxの一時起動手順](doc/jupiter2-vendor-linux-ram-boot.md) |
| 参照FSBL/ESOS/RPMIの整合 | [開発記録](doc/jupiter2-reference-ram-boot-development.md)、[試験手順](doc/jupiter2-reference-ram-boot-tests.md) |
| SM用DTB・実機hello試験 | [SM起動・アプリ試験](doc/jupiter2-keystone-app-test.md) |
| QEMU/Bianbuの操作・共有・ゲストツール | [QEMU運用手順](doc/jupiter2-qemu-operations.md)、[guestコマンド](doc/keystone-guest-commands.md) |
| samplesと既存examplesの関係 | [samples](samples/README.md)、[統合説明](doc/keystone-examples-integration.md)、[変更レビュー](doc/keystone-samples-change-review.md) |
| 実guestの検証・検証範囲 | [verification](verifications/README.md)、[検証方法](doc/keystone-verification-methods.md)、[sampleの過去結果](samples/results.md) |
| 混在PMP・粒度・UTM復帰 | [16/32 PMP](doc/jupiter2-heterogeneous-pmp-plan.md)、[PMP実機調査](doc/jupiter2-pmp-granularity-issue.md)、[KSB-073](doc/jupiter2-utm-host-access-issue.md) |
| 容量削減・大容量EPM・タイマー・reset | [firmwareサイズ](doc/jupiter2-firmware-size-reduction.md)、[大容量EPM](doc/keystone-large-epm.md)、[Sstc共存](doc/keystone-sstc-coexistence.md)、[system reset](doc/keystone-system-reset.md) |
| Eyrie/raw loader等の過去の修正 | [累積修正記録](doc/keystone-cumulative-changes.md)、[Eyrie入口問題](doc/keystone-eyrie-entry-build-id.md) |
| 乱数SBI 3001 | [移植計画](doc/keystone-sbi-3001-plan.md)、[3方式設計](doc/keystone-sbi-3001-three-backends.md)、[実装記録](doc/keystone-sbi-3001-implementation.md)、[試験](verifications/random/README.md) |
| attestation/sealing SBI 3002/3003 | [共通計画](doc/keystone-sbi-3002-3003-joint-plan.md)、[3003計画](doc/keystone-sbi-3003-plan.md)、[実装記録](doc/keystone-sbi-3002-3003-implementation.md)、[試験](verifications/crypto/README.md) |
| 未移植機能・OP-TEE同居 | [移植計画](doc/keystone-porting-plan.md)、[Keystone・OP-TEE同居設計](doc/keystone-optee-coexistence-design.md) |
| バグの追跡 | [不具合台帳](doc/keystone-bug-report.md) |
