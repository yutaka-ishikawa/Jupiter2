# Jupiter2実機でKeystoneアプリを試験する

更新日：2026-11-21。

現在確認できているのは、販売元OpenSBIを使ったRAM起動とLinux起動である。
KeystoneアプリにはSM入りOpenSBIが必要。同じkernel/initrdと整合するLinux DTBを使い、
SM起動→Linux起動→driver→hello二種の順で確認する。NOR更新はこの試験に含めない。

## 1. 提供Linux DTBの確認結果

ユーザー提供k3-pico-itx.dtbは148441 bytes。
SHA-256: de39ef1acaf7fc13b365a55b1c007f8888c36a06b9840598762ce03a9aa5f129。

| Linux DTノード | 状態 | SMとの関係 |
| --- | --- | --- |
| /soc/mailbox0@cac90000 | okay | M-onlyページ内 |
| /soc/mailbox1@cac90400 | okay | M-onlyページ内 |
| /soc/mailbox2@cac90800 | okay | M-onlyページ内 |
| /soc/mailbox3@cac90c00 | okay | M-onlyページ内 |
| /soc/rcpu_rproc0@0 | disabled | mailbox 3の参照者だが無効 |
| /soc/mailbox4@cac91000 | okay | 対象ページ外、変更しない |
| /soc/rcpu_rproc1@1 | okay | mailbox 4を使用、変更しない |
| /soc/mpxy_mbox@0 | okay | SBI経由のRPMI、変更しない |

SMのKSB-058対応は0xcac90000–0xcac90fffをM-mode専用にする。
元DTBではLinuxの直接mailbox driverがこのページを使える設定のため、そのままSM版へ流用しない。
DT上では対象4 controllerに有効なmboxes利用者がいない。mailbox driverはprobeでIRQを登録し、
IRQ処理でMMIOを読むので、remoteproc 0がdisabledであるだけではcontrollerの所有が整合しない。
詳細はKSB-070に記録した。

## 2. 別名の試験用Linux DTBを作る（開発PC）

publicリポジトリのルートで実行する。TARGETは今回の実機名の例で、名前解決できない場合は
実際のIPアドレスへ変更する。既にPCへ取り出した同じDTBがあればscpの代わりにそのファイルを使う。

```bash
git pull --ff-only
PUBLIC_ROOT="$PWD"
WORK="$PWD/work/jupiter2-keystone-app-test"
TARGET=ishikawa@cradsec-jupitor2
mkdir -p "$WORK/original" "$WORK/linux"

scp "$TARGET:/boot/spacemit/6.18.3-generic/k3-pico-itx.dtb" \
  "$WORK/original/k3-pico-itx.dtb"

python3 scripts/prepare-jupiter2-keystone-linux-dtb.py \
  --input "$WORK/original/k3-pico-itx.dtb" \
  --output "$WORK/linux/k3-pico-itx-keystone.dtb"
cat "$WORK/linux/k3-pico-itx-keystone.dtb.json"
```

必要なPCツールはPython 3とdevice-tree-compilerのfdtput。
スクリプトは対象4 controllerを確認し、有効なmboxes利用者がいれば拒否する。
変更は4ノードのstatus=disabledだけで、元DTBを上書きせず、他のノード・プロパティの保持を検査する。
同じ結果の出力が既にある場合は再利用し、異なる内容なら上書きを拒否する。
reportに入力・出力hashと変更対象を保存する。DTB全体や起動時の乱数情報はreportへ出力しない。

今回の実入力から得た限定修正候補は148457 bytes、SHA-256:
54a6e7855c04dc17c67d13526a6e917f5f971a95d7b1d82894509d6aada4db5d。
これはmailboxページの所有を整合させる候補で、全PMP領域・Linux・Enclaveの実機合格ではない。
有効なremoteproc 1、mailbox 4以降、SBI MPXY、reserved-memoryは保持している。
DTBバイナリー全体は公開リポジトリへ追加せず、各自の作業ディレクトリで管理する。

## 3. 新しい名前で実機へ配置し、販売元構成で先に確認する

開発PCから新ファイルを転送する。

```bash
scp "$WORK/linux/k3-pico-itx-keystone.dtb" "$TARGET:/tmp/k3-pico-itx-keystone.dtb"
ssh -t "$TARGET" 'sudo install -m 0644 /tmp/k3-pico-itx-keystone.dtb /boot/spacemit/6.18.3-generic/k3-pico-itx-keystone.dtb'
```

元のk3-pico-itx.dtbとenv_k3.txtは変更しない。
まず成功済みの販売元OpenSBIのRAM起動経路で、新DTBだけを選んでLinuxが起動するか確認する。
DT変更の影響とSM変更の影響を分けるためである。
起動方法は[RAM起動ガイド](jupiter2-ram-boot-guide.md)に従う。
今回の実機用のUARTテキストは次で作れる。

```bash
python3 scripts/run-jupiter2-ram-boot.py --phase linux \
  --kernel /Image-6.18.3-keystone \
  --initrd /initrd.img-6.18.3 \
  --dtb /spacemit/6.18.3-generic/k3-pico-itx-keystone.dtb \
  --root-partuuid 73708e51-d3a9-4b6f-ab55-894cd1d8b4a0 \
  --output "$WORK/boot-linux-keystone-dtb.cmd"
cat "$WORK/boot-linux-keystone-dtb.cmd"
```

生成した全文をUARTのU-Bootへ貼り付ける。PCのBashで実行しない。
PARTUUIDとファイル名は今回の実機用で、他の実機では実測値へ合わせる。

## 4. SM入りOpenSBIと統合FITを作る（開発PC）

前段が成功したら、同じpublicルートで実行する。CROSS_COMPILEは使用中のK3ツールチェーンに合わせる。

```bash
export CROSS_COMPILE=riscv64-unknown-linux-gnu-
make firmware

SM_BIN="$PUBLIC_ROOT/.build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin"
SM_OUT="$WORK/ram-boot-sm-$(date +%Y%m%d-%H%M%S)"

python3 scripts/build-jupiter2-reference-ram-boot.py \
  --opensbi-bin "$SM_BIN" \
  --esos-itb work/jupiter2-ram-boot/original/esos.itb \
  --esos-configuration conf_dual \
  --variant keystone \
  --opensbi-reserve-bytes 0x00100000 \
  --max-download-bytes 0x20000000 \
  --cross-compile "$CROSS_COMPILE" \
  --output "$SM_OUT"
REL="$SM_OUT/release"
```

.build-k3は標準ビルド先。makeでK3_BUILD_DIRを変えた場合はSM_BINも対応する実ファイルへ変更する。
1 MiBは以前の実機SMログのFirmware Size 662 KBを収める試験用予約値。
別ビルドではBINだけでなくBSS/heap/stack等を含む実行時サイズを確認する。
512 MiBは今回のSPLの転送上限で、操作ツールも実機から再取得する。
Makefileの通常のSM buildはcrypto provider=unavailableであり、今回の基本hello試験を
attestationや製品用の鍵・署名の検証として扱わない。

## 5. SM版をRAM起動し、先にLinuxの起動を確認する

完全電源断・FDLから、今作った対を転送する。

```bash
python3 scripts/run-jupiter2-ram-boot.py --release "$REL" --phase fsbl --sudo
```

UARTでDDR完了とSPLのUSB再認識を確認してから：

```bash
python3 scripts/run-jupiter2-ram-boot.py --release "$REL" \
  --phase fit --serial HW4MPK3321280144 --sudo
```

variant=keystoneではimages/ram-boot-keystone.itbを選ぶ。
UARTでSM/PMP初期化、OpenSBIからU-Bootへの移行が成功したことを確認する。
PMP設定・readback・SM初期化のエラーがあればLinuxへ進まない。
### U-Boot起動後に直接入力するコマンド（今回の実機）

以下は**UART端末のU-Bootプロンプト（=>）**へ入力する。PCのBashでは実行しない。
第3節で別名配置したk3-pico-itx-keystone.dtbを使用する。
bootfsはscsi 0:2、rootfsのPARTUUIDは今回の実機の実測値。
**各loadが成功したことを確認し、失敗した場合は後続のコマンドを実行しない。**

```text
scsi scan
scsi info

setenv kernel_addr_r 0x140000000
setenv ramdisk_addr 0x130000000
setenv fdt_addr_r 0x138000000

setenv knl_name Image-6.18.3-keystone
setenv ramdisk_name initrd.img-6.18.3
setenv dtb_dir spacemit/6.18.3-generic
setenv fdtfile k3-pico-itx-keystone.dtb

load scsi 0:2 ${kernel_addr_r} /${knl_name}

load scsi 0:2 ${ramdisk_addr} /${ramdisk_name}
setenv initrd_size ${filesize}

load scsi 0:2 ${fdt_addr_r} /${dtb_dir}/${fdtfile}

printenv kernel_addr_r ramdisk_addr initrd_size fdt_addr_r
printenv knl_name ramdisk_name dtb_dir fdtfile

setenv bootargs console=ttyS0,115200 earlycon=sbi root=PARTUUID=73708e51-d3a9-4b6f-ab55-894cd1d8b4a0 rootwait rw loglevel=8

booti ${kernel_addr_r} ${ramdisk_addr}:${initrd_size} ${fdt_addr_r}
```

initrd_sizeはinitrdのload直後、DTBのload前に保存する。filesizeは後続loadで更新される。
fdtfileも明示しているので、未定義の変数や以前のUART環境に依存しない。
今回は必要な値をsetenvで直接指定するため、env_k3.txtのload/importは不要。
カーネル読込み後に0x140000000へenv_k3.txtをloadすると、カーネル先頭を上書きしてしまう。
saveenvやenv_k3.txtの編集は行わない。

Linuxが起動したら、第6節でunameとdriverの対応を確認してからhello二種を実行する。

## 6. ドライバーとhello二種を試験する（実機Linux）

実機のLinux端末で、以下のブロックを順番に実行する。
今回の導入例のkernel releaseは6.18.3。Imageのファイル名末尾-keystoneをreleaseへ付けない。
起動したSMのsource/build記録と、使用するdriver/SDK/appsが対応していることも確認する。
単にrelease名が同じだけで異なるビルドが同一だとは扱わない。

まず、カーネル・オンラインCPU・配置済みファイルを確認する。

```bash
uname -r
cat /sys/devices/system/cpu/online
ls -l /lib/modules/6.18.3/extra/keystone-driver.ko
ls -l /opt/keystone/6.18.3/hello.ke
ls -l /opt/keystone/6.18.3/hello-native.ke
```

今回の期待値はkernel releaseが6.18.3、online CPUが0-15である。
異なる場合、ファイルがない場合は先へ進まない。
次にドライバーをロードする。

```bash
sudo modprobe keystone_driver
lsmod | grep keystone
ls -l /dev/keystone_enclave
```

modprobeが成功し、/dev/keystone_enclaveがcharacter deviceとして存在することを確認して、
最初のhelloを実行する。

```bash
sudo /opt/keystone/6.18.3/hello.ke
echo "hello終了コード=$?"
sudo dmesg | tail -n 100
```

**終了コードが0で、アプリが正常終了し、SMとLinuxにエラーがないことを確認してから**、
もう一方を実行する。失敗した場合はそこで停止する。

```bash
sudo /opt/keystone/6.18.3/hello-native.ke
echo "hello-native終了コード=$?"
sudo dmesg | tail -n 100
```

echoは対象アプリの直後に実行する。他のコマンドを挟むと、そのコマンドの終了コードになる。
どちらかが失敗した場合は後続の試験を止め、UARTログとdmesgを保存する。
admission denied:が出た場合は、その具体的な理由も記録する。

```bash
sudo dmesg > ~/keystone-dmesg.txt
```

両アプリの終了コード0、期待するアプリ結果、SM側CREATE/RUN/DESTROYとLinux側に
エラーがないことを基本試験の合格条件とする。
隔離違反・複数同時実行・署名/attestationの合格とは分ける。
現行のPMP予算はOS用1＋NAPOT UTM用1＋NAPOT EPM用1という最小構成で、
TORやbacking、二つ同時保持は追加entryを要する。まず二種を一つずつ実行し、
容量不足をPMP保護解除や割当失敗の無視で回避しない。

配布bundleに含まれるtools/run-hello.shは、hash・kernel release・driver一致を確認して
二種を順番に実行する補助ツールである。本章の手動実行では、配置済みの二種を直接起動する。

## 7. 失敗時の記録・戻し方

SM/PMP停止は全UARTログ、Linuxのtrap/panicは最初のエラーを含む全ログを保存する。
driver/CREATE/RUN失敗はkeystone-hello.log、dmesg、uname -r、bundle/source記録を保存する。
このDT修正はmailboxページだけの限定検査である。他のPMP領域・remoteproc/IRQ使用で
問題が出た場合は、その原因を調べる。有効なサービスを無断停止して合格扱いにしない。

RAM試験を破棄するには電源断し、FDLを押さず通常起動するか、保存した販売元releaseをRAM起動する。
元DTBとenv_k3.txtは保持しているため、別名DTBの試験設定を保存しなければ通常起動の選択は変わらない。
OSがrootfsへ書いた内容や既に行った永続更新の復元とは区別する。

## 8. 検証範囲

提供実DTBで4 controller有効・有効利用者なしを確認し、実fdtputで別名候補を生成した。
意味上の変更が4つのstatusだけで、他ノード・プロパティが保持されることを検査した。
ホスト回帰はscripts/tests/jupiter2-ram-boot/test_linux_dtb_preparation.pyで実dtc/fdtputを使う。
CPU/SBI/PMPは模擬せず、USBや実機を操作しない。
この候補による販売元/SM版Linux起動とhello実行は未検証で、上記の実機試験で確認する。


## 混在PMP修正後の再試験

CPU8〜15が起動せずhello CREATEが100100になる場合は
[KSB-071の修正と判定](jupiter2-heterogeneous-pmp-plan.md#7-修正候補の実装結果)を確認する。
今回の修正はSM/OpenSBIのみを更新したRAM起動で試せる。Linuxのonlineが0-15であることを確認してからhelloへ進む。
`admission denied:` や `extra rejected` が出た場合はそのUARTログを保存し、検査を無効化して続行しない。
QEMU試験の範囲は[実機との差分](jupiter2-qemu-hardware-test-gaps.md)を参照。
