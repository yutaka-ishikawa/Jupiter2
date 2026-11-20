# Milk-V Jupiter2実機へのKeystoneソフトウェアスタック導入手順

更新日：2026-11-20（JST）。対象：`yutaka-ishikawa/public`のK3スタックと本書のイメージ作成スクリプト。
実機調査・build経路は`6403232967178cb896fc761eb0038fdf9a85bd54`を基準とし、使用commitは取得時に記録する。

対象はSpacemiT K3搭載Milk-V Jupiter2 SBCで、既存のboot firmware・Linux環境を残しながら、
開発したOpenSBI＋Keystone SM、Linux、Keystone driver、SDK/Eyrieアプリを段階導入する。
Jupiter（K1/M1）、Jupiter2 NX、Dev Kitにはそのまま適用しない。

**現在のソースは実機導入を無条件に完了できる状態ではない。**
ビルド・配布物作成・バックアップまでは準備できるが、firmwareの容量・起動互換性・
PMP条件を確定するまで書き込まない。以下の「停止条件」は作業上の必須条件である。
本手順による実機書き込み・起動は未検証。

## 1. 導入範囲と順序

| 要素 | 配置・実行場所 | 導入方法 |
| --- | --- | --- |
| OpenSBI＋Keystone SM | M-mode、実機のfirmware領域 | SMをリンクしたBINを対応FITへ包装し、使用中のopensbi区画だけ更新 |
| Linux Image・modules | 実機のboot領域・rootfs | 旧kernelを残し、新しいreleaseと試験用boot entryを追加 |
| Keystone driver | 対応kernelのmodulesディレクトリ | 同じ完全kernel出力で作成した`.ko`を配置 |
| Eyrie・loader・アプリ | 実機Linuxの通常ファイル | `.ke`に含めて配置。Eyrie単体をNORへ書かない |
| SDK | 開発ホスト | アプリ作成に使用。SDK全体を実機へ入れる必要はない |
| QEMU・9p共有 | 開発ホスト専用 | 実機へ導入しない |
| OP-TEE | 今回の導入対象外 | [同居設計](keystone-optee-coexistence-design.md)は未実装。TAも呼べる構成として扱わない |

インストールは次の2段階で行い、第1段階の成功後だけ第2段階へ進む。

| 段階 | 起動する組合せ | 実施内容 | 失敗時に戻すもの |
| --- | --- | --- | --- |
| 第1段階 | 新Linux＋既存OpenSBI | 第6章で配置し、第7章で新kernelへ切り替えて起動を確認 | 元のLinux起動設定。既存OpenSBIは変更しない |
| 第2段階 | 第1段階と同じ新Linux＋新OpenSBI／SM | 第8章でOpenSBIだけ更新し、同じkernelの起動を確認。その後第9章のEnclave試験 | まずOpenSBIを更新前へ戻す。必要ならLinux起動設定も元へ戻す |

第1段階ではKeystone driverをロードせず、Enclaveを実行しない。
第2段階に入るために旧kernelへ戻す必要はない。
各段階のrollbackは[第10章](#10-復旧と正式採用)を参照する。

## 2. 書き込み前の停止条件

[実機適合性調査](jupiter2-hardware-compatibility.md)と
[EDK2維持のOpenSBI置換手順](milkv-jupiter2-opensbi-replacement.md)を先に確認する。

| 条件 | 必要な確認 |
| --- | --- |
| 使用中のboot媒体 | FSBLのUARTログ、MTD/GPT配置、販売元manifestを照合。LinuxのrootがUFSでもOpenSBIはNORの場合がある |
| firmware容量 | 記録済みNOR区画は384 KiB。過去のSM入りraw BINは532,320 bytesで超過。今回の最終ITBで再測定する |
| 実ロード形式 | 対応FSBLが読むFIT構造、load/entry、後段EDK2、RAM確保範囲を確認。BINを直接書かない |
| 初期DT | OpenSBI入力DTでK3 override、timer、IPI、RPMI、予約領域が正しく選ばれること。Linuxで採取したDTだけでは代替しない |
| 混成CPU | X100（hart 0–7）とA100（8–15）全hartのPMP数・粒度・アドレス幅・lock・優先順位をM-modeで確認 |
| 同期とtimer | 全hart PMP更新/IPI ACK、Sstc保存・復元、SM M_TIMER経路が実機で成立すること |
| 復旧 | 正しい販売元FSBL/U-Bootと元OpenSBIを退避し、FDL認識・復旧媒体アクセスを事前確認 |

現行ビルドの`KEYSTONE_K3_PMP_N_REG=16`、`K3_QEMU_PMP16`等は実機対応の証明ではない。
診断・移植変更が必要なら先に実装し、別commitで固定する。診断結果に合わせて監査を
修正するのであり、起動のためにPMP gateを無効化しない。
NORのuboot区画内に0xffの末尾領域があっても、opensbi区画を拡張してよい根拠にはならない。
UFS上の1 MiB区画に収まる場合も、FSBLが実際にそこを読むと確定するまで対象を変更しない。

## 3. 開発ホストで候補をビルドする

以下はUbuntu系開発PCのBashで、repository rootから実行する。
実機へSSHして実行するコマンドではない。依存導入は開発PCのパッケージを変更する。

```bash
git clone https://github.com/yutaka-ishikawa/public.git
cd public
git checkout main
git rev-parse HEAD
sudo bash scripts/install-build-deps.sh
```

表示したcommitを導入記録へ保存する。再現時は`git checkout 保存したcommit`で固定する。
実機対応の追加修正がある場合はレビュー済みcommitを指定する。
異なるソース・設定・toolchainの中間物は混用しない。

```bash
set -euo pipefail
mkdir -p work/jupiter2-install
# crypto開発鍵profileを作らず、通常のprovider-unavailableを使う。
KEYSTONE_SM_TRACE=0 make opensbi keystone JOBS=4 \
    2>&1 | tee work/jupiter2-install/build.log
```

`make keystone`はLinux、SDK/Eyrie、サンプル、driver、guest-overlayを準備する。
OpenSBIは別ターゲットなので両方を指定する。
このコマンドは実機flashを行わず、QEMU rootfsの作成も行わない。
`make build`全体はQEMUや開発暗号profileも作るため、実機候補作成には上記の個別指定を使う。

主な成果物は次の場所にある。

```text
.build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.{bin,elf}
.build-k3/linux/arch/riscv/boot/Image
.build-k3/linux/arch/riscv/boot/dts/
.build-k3/linux/{.config,Module.symvers}
.build-keystone/driver/keystone-driver.ko
.build-keystone/guest-overlay/usr/share/keystone/examples/{hello,hello-native}.ke
```

`make install`、`make install-opensbi`はホスト側への配置であり実機へのインストールではない。
`guest-overlay/`全体を実機の`/`へ展開してはいけない。QEMU向けのshutdown/reboot、
BusyBox wrapper等が通常OSのコマンドを置き換えるため、次節では必要なファイルだけ取り出す。

## 4. 容量確認とインストールイメージ作成

以下はクロスビルドを行った開発PCで実行する。Python 3.11以上、Git、
`mkimage`、`dumpimage`、`dtc`が必要。第3章のbuildとは別に、次の包装用ツールも導入する。

### 開発PCにイメージ作成用ツールをインストールする

Ubuntu 24.04またはDebian 12以降のAPT環境：

```bash
sudo apt-get update
sudo apt-get install -y python3 git u-boot-tools device-tree-compiler coreutils bash tar gzip
```

Fedora等のDNF環境：

```bash
sudo dnf install -y python3 git uboot-tools dtc coreutils bash tar gzip
```

使用中のOSに対応する一方を実行する。Pythonの版とコマンドの有無を確認する。

```bash
python3 -c 'import sys; print(sys.version); assert sys.version_info >= (3, 11), "Python 3.11以上が必要です"'
command -v git mkimage dumpimage dtc
```

`mkimage`と`dumpimage`はAPTの`u-boot-tools`／DNFの`uboot-tools`、
`dtc`はAPTの`device-tree-compiler`／DNFの`dtc`に含まれる。
Pythonの追加pipパッケージは不要。Pythonが3.11未満なら対応するPythonを用意し、
以降の`python3`をその実行コマンドに置き換える。
これらは開発PC上でFITを作るためのホスト用ツールであり、実機へコピーしない。

以下のイメージ作成スクリプトはビルド済み成果物を包装するもので、コンパイルや実機書込みは行わない。

### 実機でopensbi区画容量を確認する

repositoryの`scripts/check-jupiter2-install-capacity.py`を実機へコピーして実行する。
root権限は不要。`/sys/class/mtd/`からnameが`opensbi`、typeが`nor`の区画を一意に検出する。

```bash
python3 scripts/check-jupiter2-install-capacity.py
# 対象番号を明示する場合もname/typeを検査する
python3 scripts/check-jupiter2-install-capacity.py --mtd mtd5 --json
```

今回提供された実機の配置はNOR全体8 MiB、OpenSBI区画`mtd5`が393216 bytes（384 KiB）、
erase単位4096 bytes。比較対象はNOR全体ではなくOpenSBI区画の容量である。
番号・容量は再確認し、JSONの`capacity_bytes`を次の開発PCの指定値へ転記する。
区画名の重複、非NOR、読取り失敗時は停止する。使用中boot媒体の判定は別途必要。

### 開発PCでイメージを作る

第3章のbuild成功後、repository rootで実行する。`--capacity-bytes`は実測値を明示し、
既存出力へ上書きしないよう新しい`--output`を指定する。

```bash
python3 scripts/build-jupiter2-install-image.py \
    --capacity-bytes 393216 \
    --output work/jupiter2-release
```

**上記コマンドを実行し、終了code 0で完了すると、インストール用イメージが作成される。**
OpenSBI＋SMの最終FITは`work/jupiter2-release/bundle/firmware/fw_dynamic.itb`、
Linux・modules・アプリ・実機用tools・docsを含む配布イメージは
`work/jupiter2-release/bundle.tar.gz`に生成される。
展開済みの同内容も`work/jupiter2-release/bundle/`にまとまる。
新しいLinux Imageをコンパイルする処理は含まれないため、第3章のbuild成功が前提となる。
最終ITBが393216 bytesを超えるなどの検査失敗時は配布イメージを残さず終了する。

このコマンドは以下を行う。

1. OpenSBI BINを既存K3 ITSで最終ITBに包装する（load/entry `0x100000000`、非圧縮）。
2. `dumpimage`で本体を抽出し、元BINとSHA-256が一致することを確認する。
3. 最終ITB全体を指定容量と比較し、超過なら出力を残さず失敗する。
4. Imageとdriver overlayの記録済みkernel hashを照合し、全modules、driver、hello二種をまとめる。
5. 容量結果、FIT表示、source情報、SHA256SUMS、転送用tar.gzを生成する。

出力例：

```text
work/jupiter2-release/
    ├── bundle.tar.gz
    ├── bundle.tar.gz.sha256
    └── bundle/
        ├── firmware/fw_dynamic.{bin,elf,itb,its}
        ├── linux/{Image,config}
        ├── modules/KERNELRELEASE/
        ├── apps/{hello,hello-native}.ke
        ├── kernelrelease.txt
        ├── capacity.json
        ├── fit-inspection.txt
        ├── README.md
        ├── tools/{check-capacity.py,verify.sh,preflight.sh,install-linux.sh,run-hello.sh}
        ├── docs/                    本手順・置換復旧・実機調査等
        ├── check-capacity.py        互換用の従来パス
        ├── source-commit.txt
        ├── source-local.patch
        ├── source-untracked.txt
        └── SHA256SUMS
```

**実機へ持っていくものは、この`bundle/`全体、または`bundle.tar.gz`とそのchecksumだけ。**
生成物・実機用スクリプト・運用資料を一か所へ集約しており、実機にrepositoryのcheckoutは不要。
展開先の`README.md`に最初の操作とOS依存ツールを記載する。

```bash
# 実機。展開済みbundle内で実行。verify/preflightは書込みをしない。
bash tools/verify.sh
bash tools/preflight.sh
# 第5章のバックアップを済ませ、第6章の配置を行う場合だけ実行する。手動配置との二重実行はしない。
sudo bash tools/install-linux.sh
```

### install-linux.shが実機へ配置するファイル

`sudo bash tools/install-linux.sh`は、展開したbundleから次のファイルを実機へコピーする。
表の`<release>`は、bundle内の`kernelrelease.txt`に記録されたkernel releaseを表す。

| bundle内のファイル | 実機への配置先 | 用途 |
| --- | --- | --- |
| `linux/Image` | `/boot/Image-<release>-keystone` | 新しいLinux kernel本体 |
| `linux/config` | `/boot/config-<release>-keystone` | そのkernelのbuild設定。起動時に読む設定ファイルではない |
| `modules/<release>/`全体 | `/lib/modules/<release>/` | 新kernel用の全kernel modules。Keystone driverを含む |
| `modules/<release>/extra/keystone-driver.ko` | `/lib/modules/<release>/extra/keystone-driver.ko` | 上記modulesに含まれるKeystone driver |
| `apps/hello.ke`、`apps/hello-native.ke` | `/opt/keystone/<release>/` | Enclave動作確認用の二つのサンプル |

配置後、`depmod -a <release>`でmodule依存情報を生成する。
事前にbundleのchecksum、実機側の必要コマンドと区画容量を検査し、
同じreleaseの既存modulesや配置先がある場合は停止する。

**このコマンドでは新しいLinuxを起動しない。現在実行中のkernelも、次回起動するkernelの指定も変わらない。**
initramfsの生成は[第6章](#6-新linuxとアプリを追加配置する)、
起動するLinuxの変更は[第7章](#7-試験用boot-entryを追加する)で行う。
今回の`/boot/env_k3.txt`を使う構成は、第7章の「U-Bootから直接起動する場合」を参照する。
OpenSBI＋SMの書込みは[第8章](#8-opensbiとsmを置換する)の別工程となる。
DTBの配置、boot設定の編集、driverのロード、再起動も、このスクリプトでは行わない。

配置途中でI/Oエラー等が発生しても、それまでにコピーしたファイルは自動削除しない。
再実行前に上表の配置先を確認する。
必要なfirmware更新と新kernelの起動確認が済んだ後、
`sudo bash tools/run-hello.sh`でbundle内の二つのサンプルを実行できる。

### bundle.tar.gzに含まれる記録ファイル

次のファイルはtarを展開した`bundle/`内の説明・検証用ファイルであり、
`install-linux.sh`によって`/boot`や`/lib/modules`へ配置されるものではない。

| bundle内のファイル | 内容 |
| --- | --- |
| `kernelrelease.txt` | 同梱kernelとmodulesのrelease。配置先の名前と実行中kernelの照合に使う |
| `capacity.json` | 作成時に指定したOpenSBI区画容量、最終ITBのサイズ、容量判定、ITBのSHA-256 |
| `fit-inspection.txt` | FIT作成・内容表示の出力 |
| `source-commit.txt` | パッケージ作成時のソースcheckoutのcommit ID |
| `source-local.patch` | パッケージ作成時の追跡済みファイルとHEADとの差分 |
| `source-untracked.txt` | パッケージ作成時のGit未追跡ファイルのパス一覧。ファイル本体は含まず、tarの収録ファイル一覧でもない |
| `SHA256SUMS` | bundle内の通常ファイルを照合するSHA-256一覧 |
| `README.md`、`docs/` | 実機での操作方法と関連手順書 |

`source-*`は作成時checkoutの記録であり、ソースコード一式を保存するものではない。
再現可能な配布には必要なソースをcommitし、変更のないcheckoutでbuildする。
ビルド先を変えた場合は、イメージ作成時に`--k3-build-dir`と`--keystone-build-dir`を指定する。

### 実機OS側で用意するツールと同梱しないもの

Python、Bash、coreutils、kmod等は実機OSの標準パッケージを使う。
`tools/preflight.sh`が主要コマンドの有無を検査する。
NOR書込み用mtd-utils等の追加依存は、bundle内の`README.md`を参照する。
これらのOS標準パッケージはtarに含まれないため、必要なら実機OSへ別途導入する。

DTBは自動同梱・配置しない。実機に適合すると確認したDTBを別途用意し、第7章で参照先を指定する。
開発PC用のx86バイナリー、QEMU向けguest-overlayのshutdown等も同梱しない。

FITだけを作る場合：

```bash
python3 scripts/build-jupiter2-install-image.py \
    --firmware-only --capacity-bytes 393216 \
    --output work/jupiter2-install/firmware-01
# 明示的な別BINの場合は、上記に --firmware-bin /absolute/path/fw_dynamic.bin を追加
```

firmware-only出力にはLinux/modules/apps/kernelrelease.txtは含まれず、第6節のOS配置には使えない。
容量超過した現行firmwareをこのスクリプトが小さくするわけではない。サイズ削減・対応圧縮・
区画変更は別作業とし、ITBを切り詰めたり、uboot区画へはみ出して書いたりしない。
SMの最適化指定による削減実測は[OpenSBIとSMの容量削減調査](jupiter2-firmware-size-reduction.md)を参照。
通常の`make opensbi`にもSMの`-O2`を組み込んだ。Makefile経由の再buildで最終ITB
271,903 bytesを確認したが、使用環境で最終容量を再確認し、実機採用には同資料の回帰・適合性確認を行う。

### 転送後に実機容量ともう一度比較する

`bundle.tar.gz`とchecksumをscpまたはUSBで実機へ転送する。
ホストで表示したSHA-256と照合してから新規directoryへ展開する。

```bash
sha256sum -c bundle.tar.gz.sha256
tar -xzf bundle.tar.gz
cd bundle
sha256sum -c SHA256SUMS
python3 tools/check-capacity.py --image firmware/fw_dynamic.itb --mtd mtd5
```

`mtd5`はその時点の実機の番号に合わせる。省略すれば自動検出する。
開発PCで再確認する場合は、実機sysfsの代わりに`--capacity-bytes 393216`を指定できる。

容量確認の終了codeは0＝収まる（image省略時は容量取得成功）、1＝容量超過、2＝入力・読取りerror。
`--json`の`fits`と終了codeを両方確認する。イメージ作成は0＝作成成功、2＝作成失敗。
FIT magicの検査と容量確認は、署名・完全なFIT構造・実機起動互換性の検証ではない。
このスクリプトはMTDを読取り参照するだけで、区画が使用中boot元であるとは判定しない。

スクリプトのローカル試験：

```bash
python3 scripts/tests/test-jupiter2-install-tools.py -v
```

容量境界、MTD属性、実mkimage/dumpimageによる包装・抽出、超過時cleanup、
出力の上書き拒否、kernel hash不一致を検査する。テストpayloadは包装用の人工データであり、
OpenSBI/SM・QEMU guest・実機の動作試験ではない。FIT tool不足時は該当caseがskipされる。

## 5. 実機の現状記録とバックアップ

実機に電源、UART、ネットワークを接続する。UARTは基板資料で電圧・端子を確認し、
115200/8N1・フロー制御なしで電源投入直後から記録する。
Jupiter2 SBCにSDスロットはないため、SD起動を前提にしない。

以下は実機Linuxで実行する。root権限が必要な読取りだけ`sudo`を使う。
ログは個体情報を含むため、公開Gitへ追加せず作業用PCにも保存する。

```bash
set -e
RECORD="$PWD/jupiter2-before-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$RECORD"
uname -a > "$RECORD/uname.txt"
lscpu > "$RECORD/lscpu.txt"
cat /proc/cpuinfo > "$RECORD/cpuinfo.txt"
cat /proc/cmdline > "$RECORD/cmdline.txt"
cat /proc/mtd > "$RECORD/proc-mtd.txt"
lsblk -o NAME,PATH,TYPE,SIZE,FSTYPE,UUID,PARTUUID,PARTLABEL,MOUNTPOINTS \
    > "$RECORD/lsblk.txt"
findmnt > "$RECORD/findmnt.txt"
sudo dmesg > "$RECORD/dmesg.txt"
sudo cat /sys/firmware/fdt > "$RECORD/running.dtb"
```

`/sys/firmware/fdt`がない環境は、`dtc -I fs`等で実行中DTを別途採取する。
UEFIを使用していれば`efibootmgr -v`、GRUBなら`/etc/default/grub`、`/etc/grub.d/`、
`/boot/grub/grub.cfg`、extlinuxなら実際に使う`extlinux.conf`も退避する。
`/boot`、ESP、rootfs上の利用者データもバックアップする。

OpenSBI区画全体と必要なNOR/GPT情報の読取りは
[置換手順の第4章](milkv-jupiter2-opensbi-replacement.md#4-実機の起動媒体と配置を確定しバックアップする)
で行う。MTD番号を固定せずname/type/offset/sizeを照合する。
現在の販売元一式（FSBL、書込み用U-Boot、EDK2、ESOS、bootinfo、JSON等）は同一releaseで保存する。

### 2段階のrollbackに使う記録

第1段階のファイル配置や設定変更より前に、実機Linuxで保存する。
`ROLLBACK`は以降の各章でも同じ絶対パスを指定する。実機外の作業PCにもコピーしておく。

```bash
set -euo pipefail
ROLLBACK="$PWD/jupiter2-rollback-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$ROLLBACK"
uname -r > "$ROLLBACK/original-kernel-release.txt"
findmnt /boot > "$ROLLBACK/boot-mount.txt"
lsblk -o NAME,PATH,FSTYPE,UUID,PARTUUID,PARTLABEL,MOUNTPOINTS > "$ROLLBACK/storage.txt"
sudo cp -a /boot/env_k3.txt "$ROLLBACK/env_k3.txt"
sha256sum "$ROLLBACK/env_k3.txt" > "$ROLLBACK/env_k3.txt.sha256"
```

これは今回の`env_k3.txt`方式用。GRUB/extlinux方式では、実際に変更する設定を同様に保存する。
旧kernel・旧initramfs・旧DTB・旧modulesを残し、新releaseが旧releaseと重複しないことを確認する。
### OpenSBI区画の記録とバックアップ

Linux設定を保存する`jupiter2-rollback-日時/`とは別に、
`opensbi-partition-info-日時/`を作り、OpenSBI区画の情報・バックアップ・checksumをまとめて保存する。
以下は今回のNOR `mtd5`を実機Linuxから読み出す手順で、区画への書込みは行わない。
実際の起動元区画であることは、前節で参照した置換手順に従って確認する。

```bash
set -euo pipefail
OPENSBI_INFO="$PWD/opensbi-partition-info-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$OPENSBI_INFO"
MTD_NAME=mtd5
test "$(cat /sys/class/mtd/"$MTD_NAME"/name)" = opensbi
test "$(cat /sys/class/mtd/"$MTD_NAME"/type)" = nor

cat /proc/mtd > "$OPENSBI_INFO/proc-mtd.txt"
printf '%s\n' "$MTD_NAME" > "$OPENSBI_INFO/mtd-name.txt"
for field in name type size erasesize; do
    cat /sys/class/mtd/"$MTD_NAME"/"$field" > "$OPENSBI_INFO/$field.txt"
done
if test -r /sys/class/mtd/"$MTD_NAME"/offset; then
    cat /sys/class/mtd/"$MTD_NAME"/offset > "$OPENSBI_INFO/offset.txt"
fi

BACKUP="$OPENSBI_INFO/opensbi-partition-before.bin"
sudo dd if=/dev/"$MTD_NAME" of="$BACKUP" bs=64K status=progress
test "$(stat -c %s "$BACKUP")" -eq "$(cat "$OPENSBI_INFO/size.txt")"
(cd "$OPENSBI_INFO" && sha256sum opensbi-partition-before.bin) > "$BACKUP.sha256"
```

今回の実機では`opensbi-partition-before.bin`は393,216 bytesとなる。
作成後は、このdirectory全体を実機外の作業PCにもコピーする。

```text
opensbi-partition-info-YYYYMMDD-HHMMSS/
    ├── opensbi-partition-before.bin
    ├── opensbi-partition-before.bin.sha256
    ├── proc-mtd.txt
    ├── mtd-name.txt
    ├── name.txt
    ├── type.txt
    ├── size.txt
    ├── erasesize.txt
    └── offset.txt    sysfsで取得できる場合だけ
```

第10章のrollbackでは、取得済みのこのdirectoryを`OPENSBI_INFO`に指定して使う。
新しいdirectoryを作り直したり、更新後の区画内容で元バックアップを上書きしたりしない。
復旧用Linuxから実機のbootfsへアクセスできることも、起動先を変える前に確認する。
Linuxが起動しない場合、元設定を同じ実機の通常シェルから戻すことはできないためである。

## 6. 新Linuxとアプリを追加配置する

**第1段階の配置工程。OpenSBIは既存のまま変更しない。**

以降は実機上。旧kernelのboot entry、Image、initramfs、modulesを保持する。
`BUNDLE`は前節で検証した`bundle/`の絶対パスを指定する（firmware-onlyは不可）。
第4章の`tools/install-linux.sh`を使う場合は、以下の手動配置を重ねて実行しない。
同スクリプトで配置した場合も、次のinitramfs生成と第7節以降は必要である。

```bash
set -euo pipefail
BUNDLE=/absolute/path/to/bundle
KREL=$(cat "$BUNDLE/kernelrelease.txt")
case "$KREL" in ''|*[!A-Za-z0-9._+-]*) exit 1;; esac
cd "$BUNDLE"
sha256sum -c SHA256SUMS
# 同じreleaseの既存modulesを上書きしない。
test ! -e "/lib/modules/$KREL"
test ! -e "/boot/Image-$KREL-keystone"
test ! -e "/opt/keystone/$KREL"
sudo install -m 0644 linux/Image "/boot/Image-$KREL-keystone"
sudo install -m 0644 linux/config "/boot/config-$KREL-keystone"
sudo cp -a "modules/$KREL" /lib/modules/
sudo depmod -a "$KREL"
sudo install -d "/opt/keystone/$KREL"
sudo install -m 0755 apps/hello.ke apps/hello-native.ke "/opt/keystone/$KREL/"
```

既存kernelとreleaseが同じなら停止する。分離したbuild出力で固有の`CONFIG_LOCALVERSION`を
設定し、Image・全modules・driverを再buildしてパッケージを作り直す。
`build-linux-k3.sh`は毎回defconfigを再適用するため、`.config`だけを書き換えてから
`make keystone`を再実行すると設定が戻る。固有releaseの導入はbuild設定にも反映して固定する。

Bianbu等のDebian系で`initramfs-tools`を使用している場合は：

```bash
sudo update-initramfs -c -k "$KREL"
ls -l "/boot/initrd.img-$KREL"
```

別のinitramfs方式では、そのOSの生成コマンドを使う。
起動rootfsに必要なUFS/NVMe/USB、ファイルシステム等のdriverがImageまたはinitramfsに
含まれることを確認する。実機rootfsは既存OSを使い、QEMU用ext4イメージをUFS/NVMe全体へ書かない。
実機のglibc/libstdc++がrunnerに適合することも確認する。ロード時のGLIBC版不足は
対応sysrootでrunnerを再buildし、実機libcを手動上書きして解決しない。

## 7. 試験用boot entryを追加する

**第1段階の起動確認工程。第6章の新Linuxを、既存OpenSBIのまま起動する。**

使用中のboot経路を第5章の記録から選ぶ。EDK2のBoot ManagerでOSを切り替えても
M-modeのOpenSBIは置き換わらない。kernel entryとfirmware更新は別工程である。

### U-Bootから直接起動する場合

今回提示されたBianbu 4.0.4の`/boot/env_k3.txt`には、
`knl_name=vmlinuz-6.18.3-generic`、`ramdisk_name=initrd.img-6.18.3-generic`、
`dtb_dir=spacemit/6.18.3-generic`が設定されている。
U-Bootがこのファイルを読み込んでLinuxを直接起動する構成では、ここで起動ファイルを選ぶ。

1. 現在の`env_k3.txt`を別名でバックアップし、起動失敗時に元へ戻せる手段を確認する。
2. 第6章で新kernel用initramfsを作成する。
3. `knl_name`を、配置した`Image-<release>-keystone`へ変更する。
4. `ramdisk_name`を、生成した`initrd.img-<release>`へ変更する。
5. `dtb_dir`は、使用する実機用DTBが存在するディレクトリを指定する。
   既存DTBを継続利用する場合も、新kernelとの適合を確認する。

上記のファイル名はU-Bootが読むbootfsを基準とする。
Linuxでそのbootfsが`/boot`にマウントされていることを`findmnt /boot`で確認し、
指定したkernel、initramfs、実際に選択されるDTBがそこに存在することを確認する。
`<release>`は`kernelrelease.txt`の実際の値に置き換える。
`ramdisk_addr`、`loglevel`、`commonargs`はkernelの選択のためには変更しない。

**設定変更は次回起動から有効となる。** この方式はGRUBの別entry追加とは異なり、
`env_k3.txt`のkernel指定を変更すると既定の起動先も変わる。
旧kernelと元の設定を残し、UART等で復旧できる状態で試す。
OpenSBI＋SMの更新はこのファイルでは行わない。

[SpacemiT K3起動資料](https://github.com/spacemit-com/docs-buildroot/blob/main/en/k3_buildroot/device/boot.md)と
[K3 U-Boot環境定義](https://github.com/spacemit-com/uboot-2022.10/blob/k3-br-v1.0.y/board/spacemit/k3/k3.env)も参照。

### EDK2からGRUBを使っている場合

動作中entryを複製し、次だけ変更した「Keystone trial」を追加する。

- kernelを`Image-KERNELRELEASE-keystone`へ変更。
- initramfsを新releaseの`initrd.img-KERNELRELEASE`へ変更。
- root UUID、console、storage関連引数、必要なDT指定は実機の正常entryを引き継ぐ。

GRUBが参照するパスは、`/boot`が別partitionかrootfs内かで異なる。
既存entryと`grub-probe`等で確認し、Linux上のパスを無条件に転記しない。
`/etc/grub.d/40_custom`等のOS標準の追加方法を使い、`update-grub`後に生成されたentryを点検する。
直接`grub.cfg`を書き換えて永続設定としない。
署名強制がある環境では、新Imageとmoduleに認可された署名が必要。強制無効化を前提にしない。

### extlinux等を使っている場合

実際に使用されている設定へ別LABELを追加し、同様に新Image/initramfsと必要なDTを指定する。
EDK2が使わない`extlinux.conf`を編集しても反映されない。loaderが特定できない場合は
ファイル配置までで止め、使用中entryの形式を確定する。

GRUB/extlinuxで別entryを追加する場合は、既定entryを旧環境のまま残し、UART/画面から手動でtrialを選ぶ。
`init=/bin/bash`、`root=/dev/vda`、QEMUのvirtio/9p設定は持ち込まない。
最初は通常メモリー量のhelloだけを試し、256 MiB EPM用CMAは後段で
[大容量EPM手順](keystone-large-epm.md)に従い実機の予約領域と照合して追加する。

### 第1段階の合格条件

既存OpenSBIのまま新Linuxを起動し、`uname -r`がbundleの`kernelrelease.txt`と一致すること、
全16 CPU、storage、network、UART、通常のtimer動作を確認する。
Keystone driverを自動loadする設定は作らず、`insmod`・`modprobe keystone_driver`・
`tools/run-hello.sh`・Enclave実行はまだ行わない。

起動ログと結果を保存する。第1段階が合格したら新Linuxの指定を維持し、第8章へ進む。
失敗したら第2段階には進まず、[第1段階のrollback](#第1段階のrollback)で元の起動設定へ戻す。

## 8. OpenSBIとSMを置換する

**第2段階。第1段階で起動確認できた新Linuxとその起動設定を維持し、OpenSBI＋SMだけを更新する。**
第1段階の失敗をOpenSBI更新で直そうとせず、合格した場合だけ進む。
更新直前に元OpenSBIの区画全体バックアップ・SHA-256・実機外への退避と、
FDL／復旧用FSBL・U-Bootによる復元経路を確認する。

第2節の条件と容量検査をすべて満たした候補だけを対象にする。
書込み操作は[EDK2維持の置換手順](milkv-jupiter2-opensbi-replacement.md)の
第7章（NOR fastboot）または第8章（実機Linux）から、**確定した媒体に対応する一方式**を選ぶ。
そこにある`candidate/fw_dynamic.itb`を、今回検証済みのITBとする。

- 更新対象は使用中の`opensbi`だけ。EDK2の`uboot`、FSBL、ESOS、ECを一括更新しない。
- NORは消去・検証を扱う`flashcp`等を用い、raw `dd`書込みをしない。
- fastboot用のRAM常駐U-Bootと実機のEDK2は別物。U-BootをEDK2区画へ書かない。
- Linux経由では読み戻し一致を確認してから再起動。fastboot経由は起動後にも照合する。

再起動後は、第1段階と同じ新kernelを、新OpenSBI＋SM上で起動する。
UARTで候補firmwareの固有build情報、SM初期化、全hart、timer/IPIを照合する。
SBI versionが同じというだけでは新firmware起動の証拠にしない。
PMP/admissionエラーやkernel起動失敗があれば、検査を無効にせず
[第2段階のrollback](#第2段階のrollback)で元OpenSBIへ戻す。
同じkernelが既存OpenSBI上で動作する状態へ復旧し、新OpenSBI側の原因を調査する。

## 9. 実機での基本確認

新firmware＋trial kernelで、実機Linux上から実行する。
`KREL`は転送パッケージのreleaseとし、driverとアプリはその組だけを使う。

```bash
uname -r
cat /sys/devices/system/cpu/online
cat /proc/cmdline
sudo dmesg | tail -n 100
```

`uname -r`の一致、全16 CPU、UART/ネットワーク/storageの正常動作を確認してから：

```bash
set -e
BUNDLE=/absolute/path/to/bundle
KREL=$(cat "$BUNDLE/kernelrelease.txt")
test "$(uname -r)" = "$KREL"
modinfo "/lib/modules/$KREL/extra/keystone-driver.ko"
sudo modprobe keystone_driver
ls -l /dev/keystone_enclave
sudo /opt/keystone/"$KREL"/hello.ke
sudo /opt/keystone/"$KREL"/hello-native.ke
```

driverを自動loadする`modules-load.d`設定は、この段階では作らない。
device nodeがあるだけで成功とせず、CREATE/RUN/OCALL/RESUME/EXIT/DESTROYの完了、
runnerの終了status、実行後のLinux応答を記録する。失敗やhang後に無条件で再試行しない。

安定したらhelloを繰り返し、X100/A100それぞれで実行する。
Linux CPU番号とhart IDの対応を確認してから、例として`taskset -c 0`、`taskset -c 8`で
runnerを実行し、timer中断・復帰と同じ結果になることを確かめる。
CPU affinityは隔離の代替ではなく、混成CPUの経路確認に使う。
Keystone構成のSTOP/SUSPEND制限を踏まえ、初期確認でCPU hotplug・suspendは試さない。

| 段階 | 合格条件 |
| --- | --- |
| 第1段階：新Linux＋既存OpenSBI | 指定した新releaseで起動し、storage/network/全CPUが動作。復旧用の旧設定を保持 |
| 第2段階：同じ新Linux＋新OpenSBI／SM | 新firmwareを識別でき、第1段階と同じkernelが起動。SM初期化・全hart・timer/IPIを確認 |
| hello | 両サンプルが正常終了し、Linuxのclock・I/O・割込みが動作し続ける |
| 再実行・混成CPU | lifecycle反復と両CPU種類で同じ期待値。PMP資源の回収を確認 |
| 隔離・大容量 | 別工程でCPU/DMA保護、CMA、負荷・異常系を実機検証 |
| 終了 | 最後に実機OS本来のshutdown/rebootでRPMI等の実経路を確認 |

既存`verifications/run-all.sh`はQEMU guest専用という運用規約があるため、
実機へコピーしてそのまま実行する手順にはしない。まず対応QEMU guestで回帰を取り、
実機のPMP probe・故障注入は復旧可能な専用試験として別途準備する。
hello成功をattestation/sealing、乱数品質、DMA隔離の成功に読み替えない。
`qemu-dev`鍵やcounter疑似乱数を製品用providerとして導入しない。

## 10. 復旧と正式採用

### 第1段階のrollback

目標は**元のLinux＋既存OpenSBI**へ戻すこと。第1段階ではOpenSBIを書き換えていないので、
OpenSBI区画の復元は不要である。

| 失敗した時点 | 対処 |
| --- | --- |
| ファイル配置／initramfs生成中、起動設定を変更する前 | 旧起動設定を維持する。部分配置を確認し、新kernelを選ばない |
| 起動設定変更後、再起動前 | 下記の元設定復元を行い、元kernel指定に戻す |
| 新kernelが起動したがI/O等に問題がある | 動作中Linuxから元設定を復元し、旧kernelで再起動する |
| 新kernelが起動せず通常Linuxを使えない | 復旧用Linuxからbootfsをマウントして元設定を復元する。手順は下記 |

今回の`env_k3.txt`方式で、通常Linuxが使える場合は次を実行する。
`ROLLBACK`には第5章で保存したdirectoryを指定する。

```bash
set -euo pipefail
ROLLBACK=/absolute/path/to/jupiter2-rollback-TIMESTAMP
sha256sum -c "$ROLLBACK/env_k3.txt.sha256"
sudo cp -a "$ROLLBACK/env_k3.txt" /boot/env_k3.txt
sudo cmp "$ROLLBACK/env_k3.txt" /boot/env_k3.txt
sync
```

復元が成功してから再起動し、
`uname -r`が`original-kernel-release.txt`の値へ戻ったことを確認する。
GRUB/extlinux方式では旧entryを選び、追加したtrial entryを削除または無効化し、
変更した既定値も保存済み設定へ戻す。GRUBは元の設定から`update-grub`で再生成する。

**Linuxが起動しない場合：** 作業前に用意した、K3のUFS/NVMe等へアクセスできる復旧用Linuxを起動する。
第5章のPARTUUIDと照合して、実際のbootfsをマウントする。
以下は復旧用Linux上での例で、deviceとバックアップのパスは実物へ置き換える。

```bash
set -euo pipefail
BOOTFS_DEV=/dev/disk/by-partuuid/ACTUAL-BOOTFS-PARTUUID
ROLLBACK=/absolute/path/to/jupiter2-rollback-TIMESTAMP
sudo mkdir -p /mnt/jupiter2-bootfs
sudo mount "$BOOTFS_DEV" /mnt/jupiter2-bootfs
sudo cp -a "$ROLLBACK/env_k3.txt" /mnt/jupiter2-bootfs/env_k3.txt
sudo cmp "$ROLLBACK/env_k3.txt" /mnt/jupiter2-bootfs/env_k3.txt
sync
sudo umount /mnt/jupiter2-bootfs
```

bootfsをLinuxの`/boot`へマウントしていた構成では、マウント先直下が`env_k3.txt`の置き場所となる。
FDLでOpenSBIを書き戻すだけでは、bootfs上の誤ったkernel指定は直らない。
UARTのU-Bootから旧kernelを一時起動する方法を使う場合も、実機のboot変数・deviceに合わせ、
元ファイルを読み込む手順を事前確認しておく。

旧kernelで正常復旧するまでは、新規配置ファイルを削除しない。
復旧後、不要な新releaseのImage/config/initramfs/modules/appsだけを個別に退避または削除できる。
削除対象は第6章の配置先と実際の生成物を照合し、実行中kernelや旧releaseを対象にしない。
部分配置が残ると再実行が拒否されるため、再インストール前に整理する。

### 第2段階のrollback

目標はまず**第1段階で確認済みの新Linux＋元OpenSBI**へ戻すこと。
kernelと`env_k3.txt`は第1段階の合格状態を維持し、OpenSBI区画だけを元に戻す。
旧kernelを選ぶだけでは、新OpenSBIの問題は解消しない。

| 失敗した時点 | 対処 |
| --- | --- |
| 容量検査等で停止し、まだ書き込んでいない | OpenSBIはそのまま。新kernel＋既存OpenSBIでの状態を維持 |
| erase／書込み／読戻しに失敗したがLinuxが動作中 | 再起動せず、退避済みの元区画全体を復元し、読戻し一致を確認 |
| 再起動後にLinuxまで到達しない | FDLから販売元FSBLとU-BootをRAM起動し、元OpenSBIを復元 |
| 新Linuxは起動するがSMやhelloが失敗 | ログを保存し、必要なら元OpenSBIを復元。旧firmware上でEnclaveを再実行しない |

今回のNOR `mtd5`をLinuxから復元する例。
番号は毎回name/type/sizeで照合し、保存したバックアップがその区画のものであることを確認する。

```bash
set -euo pipefail
# TIMESTAMPは第5章で実際に作成したdirectory名の日時に置き換える
OPENSBI_INFO="$PWD/opensbi-partition-info-TIMESTAMP"
MTD_NAME=mtd5
BACKUP="$OPENSBI_INFO/opensbi-partition-before.bin"
test "$(cat /sys/class/mtd/"$MTD_NAME"/name)" = opensbi
test "$(cat /sys/class/mtd/"$MTD_NAME"/type)" = nor
test "$(stat -c %s "$BACKUP")" -eq "$(cat /sys/class/mtd/"$MTD_NAME"/size)"
# 保存時のSHA-256と一致することを確認してから復元する
(cd "$(dirname "$BACKUP")" && sha256sum -c "$(basename "$BACKUP").sha256")
sudo flashcp -v "$BACKUP" /dev/"$MTD_NAME"
READBACK=$(mktemp "$OPENSBI_INFO/opensbi-readback-XXXXXX.bin")
sudo dd if=/dev/"$MTD_NAME" of="$READBACK" bs=64K status=progress
sudo cmp "$BACKUP" "$READBACK"
sync
```

`OPENSBI_INFO`は保存先が異なる場合、その実際の絶対パスを指定する。
読戻しファイルも同じdirectory内に残り、復元結果の記録に使える。
復元と読戻しが成功するまで再起動しない。エラー時は復旧環境を使う。
再起動後、UARTで元OpenSBIの識別情報と新kernelの起動を確認する。

Linuxが起動しない場合のFDL手順、および使用中区画がGPTの場合の復旧は、
[OpenSBI置換手順の第10章](milkv-jupiter2-opensbi-replacement.md#10-起動しない場合の復旧)に従う。
保存済みの実機に対応するFSBL/U-BootをRAMへロードし、使用中の`opensbi`だけを戻す。
`uboot`区画がU-BootかEDK2かを勝手に変更せず、FSBL・ESOS・env・区画表も一括更新しない。

導入前の状態へ完全に戻す場合は、元OpenSBIで正常起動することを確認した後、
第1段階のrollbackも行って元のLinux指定へ戻す。

### 正式採用

第1段階、第2段階、Enclave試験の結果を別々に保存する。
基本動作・回帰・隔離試験の結果を確認してからdriverの自動load等を設定する。
旧firmware、旧kernel、元の起動設定、復旧用一式は残し、新旧のhash、config、DT、toolchain、
buildログ、UARTログ、case別結果を一つの導入記録にまとめる。

## 関連資料

- [実機情報とfirmware適合性](jupiter2-hardware-compatibility.md)
- [EDK2を維持したOpenSBI置換・復旧](milkv-jupiter2-opensbi-replacement.md)
- [buildとinstallの分離](make-build-install.md)
- [SPI NOR読取り調査](jupiter2-spi-nor-inspection.md)
- [SstcとSM timerの共存](keystone-sstc-coexistence.md)
- [Keystone移植計画](keystone-porting-plan.md)
- [既知不具合台帳](keystone-bug-report.md)
- [KeystoneとOP-TEEの同居設計](keystone-optee-coexistence-design.md)
