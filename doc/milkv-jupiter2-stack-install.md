# Milk-V Jupiter2実機へのKeystoneソフトウェアスタック導入手順

更新日：2026-11-20（JST）。対象ソース：`yutaka-ishikawa/public`、
`110c1138adb336d3a4c046c9f3250a7e3e4812ee`。

対象はSpacemiT K3搭載Milk-V Jupiter2 SBCで、既存のEDK2・Linux環境を残しながら、
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

推奨順序は、現行環境の記録・復旧準備→候補作成→互換性判定→旧OpenSBI上で新Linuxの
起動確認→OpenSBI＋SM置換→Enclave基本試験。新Linuxと新OpenSBIを一度に更新して
障害を切り分けにくくしない。旧OpenSBI上ではdriverをロードしてEnclaveを実行しない。

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

## 3. 実機の現状記録とバックアップ

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

## 4. 開発ホストで候補をビルドする

以下はUbuntu系開発PCのBashで、repository rootから実行する。
実機へSSHして実行するコマンドではない。依存導入は開発PCのパッケージを変更する。

```bash
git clone https://github.com/yutaka-ishikawa/public.git
cd public
git checkout 110c1138adb336d3a4c046c9f3250a7e3e4812ee
sudo bash scripts/install-build-deps.sh
```

実機対応の追加修正がある場合は上記commitの代わりにレビュー済みcommitを指定する。
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

## 5. 転送用パッケージを作成する

開発PCで続ける。新規ディレクトリを使用し、既存候補へ重ねて作成しない。

```bash
set -euo pipefail
KOUT="$PWD/.build-k3/linux"
STAGE="$PWD/.build-keystone/stage"
KREL=$(make -s -C linux-k3 O="$KOUT" ARCH=riscv \
    CROSS_COMPILE=riscv64-linux-gnu- kernelrelease)
case "$KREL" in ''|*[!A-Za-z0-9._+-]*) exit 1;; esac
BUNDLE="$PWD/work/jupiter2-install/bundle-$KREL"
test ! -e "$BUNDLE"
mkdir -p "$BUNDLE/linux" "$BUNDLE/modules" "$BUNDLE/apps" "$BUNDLE/firmware"
test -s "$KOUT/Module.symvers"
cmp "$STAGE/boot/k3/Image" "$KOUT/arch/riscv/boot/Image"
install -m 0644 "$KOUT/arch/riscv/boot/Image" "$BUNDLE/linux/Image"
install -m 0644 "$KOUT/.config" "$BUNDLE/linux/config"
# この全modules treeは同じImageのbuild時に生成されたもの。
cp -a "$STAGE/lib/modules/$KREL" "$BUNDLE/modules/"
rm -f "$BUNDLE/modules/$KREL/build" "$BUNDLE/modules/$KREL/source"
install -D -m 0644 .build-keystone/driver/keystone-driver.ko \
    "$BUNDLE/modules/$KREL/extra/keystone-driver.ko"
install -m 0755 .build-keystone/examples/hello/hello.ke "$BUNDLE/apps/"
install -m 0755 .build-keystone/examples/hello-native/hello-native.ke "$BUNDLE/apps/"
printf '%s\n' "$KREL" > "$BUNDLE/kernelrelease.txt"
git rev-parse HEAD > "$BUNDLE/source-commit.txt"
git diff --binary HEAD > "$BUNDLE/source-local.patch"
```

driverの`modinfo -F vermagic`と`KREL`、Imageとmodulesの対応を確認する。
release文字列の一致だけでは同じbuildと証明できないため、上記Image照合とbuild記録も保持する。
DTBは実機のboot方式・revisionに対応すると確認したものだけ別途追加する。
QEMU生成DTや全DTB一式を実機の既存DTへ一括上書きしない。

FITを作る。以下のテンプレートはload/entryが`0x100000000`、compressionがnoneであり、
実機のFSBL契約と一致していることが前提。

```bash
set -euo pipefail
FW="$PWD/.build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware"
install -m 0644 "$FW/fw_dynamic.bin" "$BUNDLE/firmware/"
install -m 0644 "$FW/fw_dynamic.elf" "$BUNDLE/firmware/"
cp opensbi/platform/generic/spacemit/fw_dynamic.its "$BUNDLE/firmware/"
(cd "$BUNDLE/firmware" && mkimage -f fw_dynamic.its fw_dynamic.itb)
dumpimage -l "$BUNDLE/firmware/fw_dynamic.itb"
stat -c '%n %s bytes' "$BUNDLE/firmware/"fw_dynamic.{bin,itb}
```

ここで**最終ITB**を実機の使用中区画容量と比較する。384 KiBのNOR構成なら：

```bash
test "$(stat -c %s "$BUNDLE/firmware/fw_dynamic.itb")" -le 393216
```

失敗した候補は書き込めない。サイズ削減、ロード経路の変更、区画変更は別の移植作業とし、
切り詰め・隣接区画へのはみ出し・未対応圧縮で回避しない。

転送前に通常ファイルのmanifestとアーカイブを作成する。

```bash
(cd "$BUNDLE" && find . -type f ! -name SHA256SUMS -print0 \
    | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -C "$(dirname "$BUNDLE")" -czf "$BUNDLE.tar.gz" "$(basename "$BUNDLE")"
sha256sum "$BUNDLE.tar.gz"
```

`scp`またはUSBストレージで実機の一般ユーザーの作業ディレクトリへ転送する。
実機でアーカイブのSHA-256をホストの値と比較してから展開し、展開先で
`sha256sum -c SHA256SUMS`を実行する。ネットワーク先・device名を推測して書き込まない。

## 6. 新Linuxとアプリを追加配置する

以降は実機上。旧kernelのboot entry、Image、initramfs、modulesを保持する。
`BUNDLE`は前節で検証した展開先の絶対パスを指定する。

```bash
set -euo pipefail
BUNDLE=/absolute/path/to/bundle-KERNELRELEASE
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

使用中のboot経路を第3節の記録から選ぶ。EDK2のBoot ManagerでOSを切り替えても
M-modeのOpenSBIは置き換わらない。kernel entryとfirmware更新は別工程である。

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

どちらも既定entryは旧環境のまま、UART/画面から手動でtrialを選ぶ。
`init=/bin/bash`、`root=/dev/vda`、QEMUのvirtio/9p設定は持ち込まない。
最初は通常メモリー量のhelloだけを試し、256 MiB EPM用CMAは後段で
[大容量EPM手順](keystone-large-epm.md)に従い実機の予約領域と照合して追加する。

旧OpenSBIのままtrial Linuxを一度起動し、`uname -r`、全CPU、storage、network、UARTを確認する。
成功してから旧kernelへ戻す。SM未導入の段階で`insmod`やEnclave実行は行わない。

## 8. OpenSBIとSMを置換する

第2節の条件と容量検査をすべて満たした候補だけを対象にする。
書込み操作は[EDK2維持の置換手順](milkv-jupiter2-opensbi-replacement.md)の
第7章（NOR fastboot）または第8章（実機Linux）から、**確定した媒体に対応する一方式**を選ぶ。
そこにある`candidate/fw_dynamic.itb`を、今回検証済みのITBとする。

- 更新対象は使用中の`opensbi`だけ。EDK2の`uboot`、FSBL、ESOS、ECを一括更新しない。
- NORは消去・検証を扱う`flashcp`等を用い、raw `dd`書込みをしない。
- fastboot用のRAM常駐U-Bootと実機のEDK2は別物。U-BootをEDK2区画へ書かない。
- Linux経由では読み戻し一致を確認してから再起動。fastboot経由は起動後にも照合する。

最初は新firmware＋旧kernelでLinuxまで起動することを確認し、その後trial kernelを選ぶ。
UARTで候補firmwareの固有build情報、SM初期化、全hart、timer/IPIを照合する。
SBI versionが同じというだけでは新firmware起動の証拠にしない。
PMP/admissionエラーで止まった場合、検査を無効にせず元firmwareへ戻す。

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
BUNDLE=/absolute/path/to/bundle-KERNELRELEASE
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
| 新Linux単独 | 旧OpenSBI上でstorage/network/全CPUが動作し、旧kernelへ戻せる |
| 新firmware単独 | 新候補を識別でき、EDK2→旧kernelまで到達。全hart・timer/IPIを確認 |
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

| 症状 | 対応 |
| --- | --- |
| trial Linuxだけ起動しない | 旧boot entryを手動選択。root UUID、initramfs、DT、storage driverを確認 |
| driverのinvalid module format | Image/modules/driverを同一buildへ揃える。強制loadしない |
| 新firmwareでUART/EDK2へ到達しない | FDLから保存済みFSBL/U-BootをRAM起動し、元opensbiを復元。詳細は置換手順第10章 |
| SM初期化・PMP同期失敗 | 元firmwareへ戻す。全hart診断とDT/配置を見直す |
| helloがhangする | UARTを保存して復旧。RCU stallだけで原因をtimerと決めない |
| libc等の依存不足 | 実機対応sysrootでアプリを再build。基本OSライブラリーを上書きしない |

旧kernelへ戻しても新OpenSBIは残る。M-mode側に原因がある場合はfirmwareも元に戻す。
firmwareの復旧は[置換手順第10章](milkv-jupiter2-opensbi-replacement.md#10-起動しない場合の復旧)を使い、
パーティション全体の読戻しとUARTを確認する。

正式採用は基本動作・回帰・隔離試験の結果をレビューしてから行う。
既定boot entryの変更とdriverの自動loadをその時点で設定する。
旧firmware、旧kernel、復旧用一式は残し、新旧のhash、config、DT、toolchain、
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
