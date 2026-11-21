# Milk-V Jupiter2：RAMへ転送してLinuxを起動する手順

更新日：2026-11-21。

**販売元OpenSBIを使い、修正したFSBL/U-BootとESOSをRAM起動し、UFS上のLinuxを起動できた実機手順。**
今回ユーザーからLinux起動成功の報告を受けた。Keystone SM/Enclaveの実行確認とは分ける。
新しい操作補助スクリプトはホストで検査済みで、補助スクリプト自体によるUSB転送は実機未確認。
従来の手動操作と同じstage/continueを段階別に実行する。

## 1. 使用するスクリプトと作業場所

| ファイル | 実行場所と目的 |
| --- | --- |
| scripts/build-jupiter2-reference-ram-boot.py | 開発PC。固定ソースからFSBL/U-Bootをビルドし、販売元OpenSBIとESOSを組み込む |
| scripts/run-jupiter2-ram-boot.py | 開発PC。RAM転送、またはUART用Linux起動コマンドの生成 |
| release/tools/ram-boot.py | 上記操作スクリプトの同梱コピー。releaseだけをPCへ持ち運んで使用できる |
| scripts/tests/jupiter2-ram-boot/ | 開発PC専用のホスト回帰試験。各先頭コメントに目的・検証範囲を記載 |

PCの操作ターミナルとUART端末は分ける。PC用Python/BashをU-Bootへ入力しない。
Linux用に生成するboot-linux.cmdは逆にUARTのU-Bootへ貼り付けるテキストで、PCのBashでは実行しない。

ファームウェアはRAMへ転送する。Linux kernel/initrd/DTBは既存UFSから読む。
OSストレージ全体をRAM化する手順ではなく、Linuxのrootfsは通常のrwで起動する。
fastboot flash/erase、saveenv、env_k3.txtの編集は行わない。

## 2. 開発PCの準備とイメージ作成

Linux開発PCのpublicリポジトリのルートで実行する。

```bash
git pull --ff-only
PUBLIC_ROOT="$PWD"
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
  --opensbi-bin work/jupiter2-ram-boot/original/fw_dynamic.bin \
  --esos-itb work/jupiter2-ram-boot/original/esos.itb \
  --esos-configuration conf_dual \
  --variant vendor \
  --opensbi-reserve-bytes "$VENDOR_SBI_RESERVE_BYTES" \
  --max-download-bytes "$SPL_DOWNLOAD_BYTES" \
  --cross-compile "$CROSS_COMPILE" \
  --output "$OUT"

REL="$OUT/release"
```

**このビルドコマンドの成功でFSBL.binとram-boot-vendor.itbを作る。**
OpenSBI BINとESOS ITBは入手済みの販売元入力を指定する。BINはfw_dynamic.itbから正しく抽出したものを使う。
ビルダーはOpenSBI/ESOS自体を再コンパイルしない。新しいFSBLと統合FITは必ず対で使用する。

```text
work/jupiter2-ram-boot/reference-vendor-日時/
├── source/                      固定ソースとビルド出力
├── records/                     設定、差分、ELF/RPMI契約、ビルドログ
└── release/
    ├── README-RAM-BOOT.md
    ├── images/
    │   ├── FSBL.bin
    │   └── ram-boot-vendor.itb
    ├── tools/
    │   ├── ram-boot.py
    │   └── boot-linux.cmd        第7節で生成するUART用テキスト
    ├── records/                 FIT一覧、manifest、SHA-256
    └── logs/                    実際のUSB操作時に作るPCログ
```

ビルダーが適用する要点は、実ELFからRCPUの起動先を設定することと、
有効なESOS RPMIサーバーからOpenSBI用DTのqueue設定を揃えること。
今回のcore 1 entryは0x100804000、RPMIはcore 0の0x100800000だった。
入力ごとに検査して反映し、これらを全入力へ固定値として流用しない。
起動失敗を無視して先へ進む変更ではない。

失敗時は$OUT/records/build.logを確認する。出力先が存在する場合は停止するので、
前回の記録を残し、新しいOUTを指定する。--prepare-onlyはソース準備だけで、イメージは作らない。

## 3. UART・USB接続と生成物の確認

[UART接続手順](milkv-jupiter2-uart.md)に従い、PC側は115200 baud、8N1、フロー制御なし。
UARTの全ログを保存する。USB fastbootはJupiter2のDRD Type-CをデータケーブルでPCへ接続する。

PCで生成物を確認する。

```bash
cd "$REL"
sha256sum -c records/FSBL.bin.sha256
sha256sum -c records/ram-boot-vendor.itb.sha256
sha256sum -c records/host-tools.sha256
```

イメージと実機の対応はmanifest、固定ソース差分、今回の検査記録で確認する。
一般の別ボード用FSBLや別版ESOSとの組合せへそのまま適用しない。

## 4. FSBLをRAMへ転送する（PC）

以下は**開発PCのターミナル**で直接入力する。UART端末では実行しない。
作業ディレクトリは第2節で作ったreleaseである。
Jupiter2を完全電源断し、FDLボタンを押して起動してから離す。
DRD Type-CをデータケーブルでPCへ接続し、ROMのダウンロード待機にする。

```bash
cd "$REL"
sha256sum -c records/FSBL.bin.sha256
sudo fastboot devices
```

checksumがOKで、ROMのfastboot機器が一台だけ表示されることを確認する。
機器が出ない場合は、FDL操作、DRDポート、データケーブル、PCのUSB認識を確認する。

FSBLを転送する。

```bash
sudo fastboot stage images/FSBL.bin
```

stageが成功したら、FSBLを実行する。

```bash
sudo fastboot continue
```

UARTでDDR training完了とmemory verify passを確認する。
ROMのUSB機器がいったん消え、SPLとして再認識されるまで待ってから第5節へ進む。
stageまたはDDR初期化に失敗した場合は、後続の転送を行わずログを保存する。

## 5. 統合FITをRAMへ転送する（PC）

引き続き**開発PCのターミナル**で実行する。
今回のSPL serialはHW4MPK3321280144。他の実機ではdevicesの実測値を指定する。

```bash
cd "$REL"
sudo fastboot devices
sudo fastboot -s HW4MPK3321280144 getvar max-download-size
stat -c '%s bytes' images/ram-boot-vendor.itb
sha256sum -c records/ram-boot-vendor.itb.sha256
```

今回の転送上限の報告値は0x20000000（536870912 bytes、512 MiB）。
**実際に報告された上限がstatのFITサイズ以上で、checksumがOKであることを確認してから転送する。**
上限を取得できない、serialが表示されない、FITが収まらない場合は次へ進まない。

```bash
sudo fastboot -s HW4MPK3321280144 stage images/ram-boot-vendor.itb
```

stageが成功したら、統合FITを実行する。

```bash
sudo fastboot -s HW4MPK3321280144 continue
```

USBが消えた後はUARTを見る。新しい対ではU-Bootへの追加continueを前提としない。
UARTで次を確認する。

1. 両coreのhandshake acknowledged。
2. OpenSBIへの引渡しを経てU-Bootの=>へ到達。
3. U-Bootの入出力がserialであること。

ここで指定するのは販売元OpenSBI用ram-boot-vendor.itb。
SM版のファイル名と試験順序は[Keystoneアプリ試験手順](jupiter2-keystone-app-test.md)を参照する。

この操作はflash/eraseを送らない。ファームウェア内部の自動保存までUSBコマンドだけで
保証するものではなく、ビルダーはDDR情報保存・FSBL更新等を無効化している。
UARTに書込み表示があれば、その操作も記録する。
手動操作のPCログはターミナルのログ保存機能等で残す。UARTログも別途保存する。
自動でPCログを残す操作補助スクリプトは第8節で紹介する。

## 6. UFSと起動ファイルを確認する（UART）

以下は**UART端末のU-Bootプロンプト（=>）**へ直接入力する。
開発PCのBashでは実行しない。

```text
scsi scan
scsi info
```

デバイス名と容量を取得でき、descriptor失敗やUTP timeoutが出ないことを確認する。
失敗した場合はscanを繰り返さずログを保存する。
成功したら、パーティションと起動ファイルを確認する。

```text
part list scsi 0
ls scsi 0:2 /
ls scsi 0:2 /spacemit/6.18.3-generic/
```

今回の実機はYMTC YMUS8B5TH1A1C1、119.1 GBで、0:1=ESP、0:2=bootfs、0:3=rootfs。
kernel=/Image-6.18.3-keystone、initrd=/initrd.img-6.18.3、
DTB=/spacemit/6.18.3-generic/k3-pico-itx.dtbを確認した。
Partition Type: EFIはGPT形式の表示で、GRUBの起動指定ではない。
別実機ではpart listとファイル一覧に合わせる。
第7節の今回の例では修正DTBを使うため、準備後は同じディレクトリにk3-pico-itx-keystone.dtbがあることも確認する。
このU-Bootのlsにはディレクトリを指定する。ファイル単体の読込みは第7節のload成功で確認する。
これらのファイルを確認したら、第7節のLinux一時起動へ進む。

## 7. Linuxを一時起動する（UARTでコマンドを直接入力）

以下は**UART端末のU-Bootプロンプト（=>）**へ直接入力する、今回の実機の例。
PCでコマンド生成スクリプトを実行する必要はない。
ここではSM向けに準備・別名配置したk3-pico-itx-keystone.dtbを使用する。
準備方法は[Keystoneアプリ試験手順の第2〜3節](jupiter2-keystone-app-test.md#2-別名の試験用linux-dtbを作る開発pc)を参照する。
この修正DTBで販売元OpenSBIのLinux起動を確認し、SM版でも同じDTBを使用する。

bootfsはscsi 0:2、rootfsのPARTUUIDは73708e51-d3a9-4b6f-ab55-894cd1d8b4a0。
他の実機ではpart listとファイル一覧から得た値へ変更する。
**各loadの成功を確認してから次へ進み、失敗した場合はbootiを実行しない。**

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

initrdのload直後にfilesizeをinitrd_sizeへ保存する。filesizeはDTBのloadでも更新されるためである。
fdtfileを明示設定するので、未定義のままディレクトリだけをloadする誤りを避けられる。
今回の値はsetenvで直接指定するため、env_k3.txtのload/importは不要。
**カーネル読込み後に0x140000000へenv_k3.txtをloadすると、カーネル先頭を上書きする。**
env_k3.txtの編集やsaveenvは行わない。

使用するロード先はkernel=0x140000000、initrd=0x130000000、DTB=0x138000000。
固定参照ソースのU-Bootは先頭32 MiBを除外したRAM baseとImageのtext_offsetからカーネル移動先を決める。
今回の通常2 MiB offsetなら0x102200000で、ESOSの先頭実行領域を上書きする配置ではない。

ログイン画面まで進んだらLinuxで実行する。

```bash
uname -r
cat /proc/cmdline
```

Linux起動成功はユーザー報告済み。実際のuname出力は未収集。
Image名が-keystoneでも、kernel releaseはビルド設定で決まる（今回の導入例は6.18.3）。
販売元OpenSBIでの起動と、SM/Enclaveの成功は分ける。
SM版でLinuxが起動した後のdriverとhello試験は[Keystoneアプリ試験手順](jupiter2-keystone-app-test.md#6-ドライバーとhello二種を試験する実機linux)を参照する。

## 8. 操作補助スクリプトの紹介（任意）

第4〜6節は上記のコマンドを直接入力して実施できる。
同じFSBL/FIT転送を補助するtools/ram-boot.pyも同梱している。
補助スクリプトは画像checksum、ROM機器の台数、SPL serial、転送上限を検査し、PCログをlogs/へ保存する。
UARTでの到達確認と第6節のUFS確認は利用者が行う。

新しく作ったrelease内で使う場合：

```bash
python3 tools/ram-boot.py --phase fsbl --dry-run
python3 tools/ram-boot.py --phase fsbl --sudo
```

UARTでDDR完了とSPLのUSB再認識を確認してから：

```bash
python3 tools/ram-boot.py --phase fit --serial HW4MPK3321280144 --dry-run
python3 tools/ram-boot.py --phase fit --serial HW4MPK3321280144 --sudo
```

--dry-runは画像を検査して予定コマンドを表示するだけで、USB操作は実行しない。

### UART用Linux起動コマンドの生成（任意）

第7節のコマンドは直接入力できる。必要なら開発PCのrelease内で次を実行し、
同等のload失敗時の停止分岐付きテキストを生成できる。このPC操作だけではLinuxは起動しない。

```bash
python3 tools/ram-boot.py --phase linux \
  --kernel /Image-6.18.3-keystone \
  --initrd /initrd.img-6.18.3 \
  --dtb /spacemit/6.18.3-generic/k3-pico-itx-keystone.dtb \
  --root-partuuid 73708e51-d3a9-4b6f-ab55-894cd1d8b4a0 \
  --boot-partition 2 --output tools/boot-linux.cmd
cat tools/boot-linux.cmd
```

生成した全文を確認し、UARTのU-Bootへ貼り付ける。PCのBashで実行しない。

### 既存releaseをそのまま使う場合

以前作ったreleaseにはtools/がない。再ビルドしなくても、更新したpublicの操作スクリプトを使える。
RELを既存のreleaseの絶対パスへ設定し、開発PCで実行する。

```bash
python3 "$PUBLIC_ROOT/scripts/run-jupiter2-ram-boot.py" \
  --release "$REL" --phase fsbl --sudo
python3 "$PUBLIC_ROOT/scripts/run-jupiter2-ram-boot.py" \
  --release "$REL" --phase fit --serial HW4MPK3321280144 --sudo
```

二つを一括貼付けせず、間に第4節のDDR完了とSPL再認識を確認する。
Linux用テキストも同じスクリプトの--phase linuxで生成できる。
既存releaseはreference builder由来で、records/manifest.jsonと画像checksumが必要。

## 9. 失敗時と記録

PC側の失敗時は後続stage/continueを実行しない。logs/とrecords/を保存する。
UART側の失敗では、最後の表示だけでなく起動先頭からのログを保存する。
通常は電源断してFDLを押さず起動すれば元の起動経路へ戻るが、
これはRAM試験の破棄であり、変更した永続データを復元する操作ではない。

| 停止位置 | 記録・対応 |
| --- | --- |
| USB未認識 | FDL/DRD/ケーブル、devicesの結果を確認 |
| DDR失敗 | 別ボード設定で進めず、入力FSBLとログを確認 |
| RCPU timeout | ELF entryとrecords/rcpu-elf.json、SPL DTの整合を確認 |
| OpenSBI無出力 | records/rpmi-contract.jsonと実FITを保存 |
| UFSエラー | scanを反復せずログ保存 |
| ファイル読込み失敗 | bootfs番号、ファイル名、DTB指定を確認。生成テキストはbootiへ進まない |
| kernel panic/root mount失敗 | bootiからの全ログ、root PARTUUID、kernel/modules/initrdの対応を確認 |

## 10. ホスト試験と調査記録

ホスト回帰試験は専用ディレクトリに集約した。テストが作る形式試験用イメージは実機へ転送しない。

```bash
cd "$PUBLIC_ROOT"
# 完全なホスト試験には、通常依存に加えRISC-V対応LLVMが必要。
sudo apt-get install clang lld
bash scripts/tests/jupiter2-ram-boot/run-host-tests.sh
```

実ツールでのFIT/ELF/DT生成・整合検査と、操作スクリプトのdry-run・構文を確認する。
USB操作やCPU/SBI/PMPの模擬はしない。新しい操作補助ツールによる実機転送は未検証。

詳しい調査履歴は[開発・解析文書](jupiter2-reference-ram-boot-development.md)、
[段階別の実機記録とテスト手順](jupiter2-reference-ram-boot-tests.md)、
[障害台帳](keystone-bug-report.md)を参照する。

## 11. 次にKeystoneアプリを試験する

販売元OpenSBIでLinuxが起動したことと、SM/Enclaveが動くことは別の段階。
提供Linux用DTBには、SMのM-only mailboxページ内の直接controllerが有効な不整合があった。
[Keystone実機アプリ試験手順](jupiter2-keystone-app-test.md)で別名DTBを準備し、
販売元版でDT変更を確認してから、SM入りOpenSBIへ差し替えて同じLinuxを起動する。
その後にdriver、hello.ke、hello-native.keを順番に検証する。
元DTBやenv_k3.txtを置換せず、PMP保護を緩和して進めない。

