# Milk-V Jupiter2：RAMへ転送してLinuxを起動する手順

[実機用ビルド手順書](jupiter2-build-install-test.md#ram-boot-images)で
`FSBL.bin` と統合FITを生成した後、このガイドで実機の起動を確認します。
同じビルドから生成した2ファイルを対で使います。
過去に販売元OpenSBIの構成で、USBからの手動転送とUFS上のLinux起動を実機で確認しました。

ビルドに使った開発PCのシェルをそのまま使います。`OUT` は
[ビルド手順書のRAM起動イメージの実行例](jupiter2-build-install-test.md#ram-boot-images)
で設定した出力先です。ここではその値を引き継ぎます。
各変数の意味と設定方法は[RAM起動用の設定変数](jupiter2-build-install-test.md#ram-boot-variables)
を参照してください。別の端末で続ける場合は、同じビルドの出力先を使います。
販売元OpenSBIで試験する場合は `FIT=ram-boot-vendor.itb` を指定します。

```bash
JUPITER2_ROOT="$PWD"
# ビルド手順で設定したOUT環境変数を使います。
REL="$OUT/release"
FIT=ram-boot-keystone.itb
```

PC操作用の端末とUART端末を分けます。生成した `boot-linux.cmd` はUARTのU-Bootに入力します。
ファームウェアをRAMに読み込み、Linuxのkernel・initrd・DTBはUFSから読みます。
この手順では `fastboot flash`、`fastboot erase`、`saveenv` を使いません。

## 1. UART・USB接続と生成物の確認

[UART接続手順](milkv-jupiter2-uart.md)に従い、PC側は115200 baud、8N1、フロー制御なし。
UARTの全ログを保存する。USB fastbootはJupiter2のDRD Type-CをデータケーブルでPCへ接続する。

PCで生成物を確認する。

```bash
cd "$REL"
sha256sum -c records/FSBL.bin.sha256
sha256sum -c "records/$FIT.sha256"
sha256sum -c records/host-tools.sha256
```

イメージと実機の対応はmanifest、固定ソース差分、今回の検査記録で確認する。
一般の別ボード用FSBLや別版ESOSとの組合せへそのまま適用しない。

## 2. FSBLをRAMへ転送する（PC）

以下は**開発PCのターミナル**で直接入力する。UART端末では実行しない。
作業ディレクトリは冒頭で指定した `$REL` です。
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
ROMのUSB機器がいったん消え、SPLとして再認識されるまで待ってから第3節へ進む。
stageまたはDDR初期化に失敗した場合は、後続の転送を行わずログを保存する。

## 3. 統合FITをRAMへ転送する（PC）

引き続き**開発PCのターミナル**で実行する。
今回のSPL serialはHW4MPK3321280144。他の実機ではdevicesの実測値を指定する。

```bash
cd "$REL"
sudo fastboot devices
sudo fastboot -s HW4MPK3321280144 getvar max-download-size
stat -c '%s bytes' "images/$FIT"
sha256sum -c "records/$FIT.sha256"
```

今回の転送上限の報告値は0x20000000（536870912 bytes、512 MiB）。
**実際に報告された上限がstatのFITサイズ以上で、checksumがOKであることを確認してから転送する。**
上限を取得できない、serialが表示されない、FITが収まらない場合は次へ進まない。

```bash
sudo fastboot -s HW4MPK3321280144 stage "images/$FIT"
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

Keystone SM入りFITでの試験順序は[Keystoneアプリ試験手順](jupiter2-keystone-app-test.md)を参照する。

この操作はflash/eraseを送らない。ファームウェア内部の自動保存までUSBコマンドだけで
保証するものではなく、ビルダーはDDR情報保存・FSBL更新等を無効化している。
UARTに書込み表示があれば、その操作も記録する。
手動操作のPCログはターミナルのログ保存機能等で残す。UARTログも別途保存する。
自動でPCログを残す操作補助スクリプトは第6節で紹介する。

## 4. UFSと起動ファイルを確認する（UART）

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
第5節の今回の例では修正DTBを使うため、準備後は同じディレクトリにk3-pico-itx-keystone.dtbがあることも確認する。
このU-Bootのlsにはディレクトリを指定する。ファイル単体の読込みは第5節のload成功で確認する。
これらのファイルを確認したら、第5節のLinux一時起動へ進む。

## 5. Linuxを一時起動する（UARTでコマンドを直接入力）

以下は**UART端末のU-Bootプロンプト（=>）**へ直接入力する、今回の実機の例。
PCでコマンド生成スクリプトを実行する必要はない。
ここではSM向けに準備・別名配置したk3-pico-itx-keystone.dtbを使用する。
準備方法は[Keystoneアプリ試験手順の第2〜3節](jupiter2-keystone-app-test.md#2-別名の試験用linux-dtbを作る開発pc)を参照する。
この修正DTBで販売元OpenSBIのLinux起動を確認し、SM版でも同じDTBを使用する。

KeystoneとOP-TEEを同梱したFITでは、同じFITビルドから生成した `k3-pico-itx-keystone-optee.dtb` をUFSに配置する。
下の手動例では `fdtfile` をそのファイル名に変更し、DTBのload後に `fdt addr ${fdt_addr_r}` と
`fdt print /firmware/optee` を実行してノードを確認する。コマンド生成例を使う場合は `--dtb` に
同梱用DTBのパスを指定する。
[同梱用Linux DTBの生成](jupiter2-build-install-test.md#ram-boot-images)

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

## 6. 操作補助スクリプトの紹介（任意）

第2〜4節は上記のコマンドを直接入力して実施できる。
同じFSBL/FIT転送を補助するtools/ram-boot.pyも同梱している。
補助スクリプトは画像checksum、ROM機器の台数、SPL serial、転送上限を検査し、PCログをlogs/へ保存する。
UARTでの到達確認と第4節のUFS確認は利用者が行う。

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

第5節のコマンドは直接入力できる。必要なら開発PCのrelease内で次を実行し、
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

以前作ったreleaseにはtools/がない。再ビルドしなくても、更新したJupiter2の操作スクリプトを使える。
RELを既存のreleaseの絶対パスへ設定し、開発PCで実行する。

```bash
python3 "$JUPITER2_ROOT/scripts/run-jupiter2-ram-boot.py" \
  --release "$REL" --phase fsbl --sudo
python3 "$JUPITER2_ROOT/scripts/run-jupiter2-ram-boot.py" \
  --release "$REL" --phase fit --serial HW4MPK3321280144 --sudo
```

二つを一括貼付けせず、間に第2節のDDR完了とSPL再認識を確認する。
Linux用テキストも同じスクリプトの--phase linuxで生成できる。
既存releaseはreference builder由来で、records/manifest.jsonと画像checksumが必要。

## 7. 失敗時と記録

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

## 8. ホスト試験と調査記録

ホスト回帰試験は専用ディレクトリに集約した。テストが作る形式試験用イメージは実機へ転送しない。

```bash
cd "$JUPITER2_ROOT"
# 完全なホスト試験には、通常依存に加えRISC-V対応LLVMが必要。
sudo apt-get install clang lld
bash scripts/tests/jupiter2-ram-boot/run-host-tests.sh
```

実ツールでのFIT/ELF/DT生成・整合検査と、操作スクリプトのdry-run・構文を確認する。
USB操作やCPU/SBI/PMPの模擬はしない。新しい操作補助ツールによる実機転送は未検証。

詳しい調査履歴は[開発・解析文書](jupiter2-reference-ram-boot-development.md)、
[段階別の実機記録とテスト手順](jupiter2-reference-ram-boot-tests.md)、
[障害台帳](keystone-bug-report.md)を参照する。

## 9. 次にKeystoneアプリを試験する

販売元OpenSBIでLinuxが起動したことと、SM/Enclaveが動くことは別の段階。
提供Linux用DTBには、SMのM-only mailboxページ内の直接controllerが有効な不整合があった。
[Keystone実機アプリ試験手順](jupiter2-keystone-app-test.md)で別名DTBを準備し、
販売元版でDT変更を確認してから、SM入りOpenSBIへ差し替えて同じLinuxを起動する。
その後にdriver、hello.ke、hello-native.keを順番に検証する。
元DTBやenv_k3.txtを置換せず、PMP保護を緩和して進めない。

