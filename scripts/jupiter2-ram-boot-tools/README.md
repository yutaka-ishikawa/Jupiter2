# Jupiter2 RAM起動用release

このディレクトリは開発PCで使用する。実機へOSイメージをインストールするものではない。
画像はimages/、PC側の操作スクリプトはtools/ram-boot.py、検査記録はrecords/にある。
Python 3、fastbootとUART端末はPCの標準パッケージを使用し、x86バイナリーは同梱しない。

## 1. FSBLを転送する（開発PC）

UARTログを保存し、完全電源断からFDLを押して起動する。
DRD Type-CをPCへ接続する。ROM fastboot機器は一台だけにする。
このreleaseディレクトリで実行する。

```bash
python3 tools/ram-boot.py --phase fsbl --dry-run
python3 tools/ram-boot.py --phase fsbl --sudo
```

画像のSHA-256を確認後、fastboot stage FSBL.binとcontinueを実行する。
UARTでDDR完了を確認し、USBがSPLとして再認識されるまで待つ。

## 2. 統合FITを転送する（開発PC）

今回の実機serialはHW4MPK3321280144。他の実機ではfastboot devicesの値を使用する。

```bash
python3 tools/ram-boot.py --phase fit --serial HW4MPK3321280144 --dry-run
python3 tools/ram-boot.py --phase fit --serial HW4MPK3321280144 --sudo
```

機器の存在とSPLの実測max-download-sizeを検査し、収まる場合だけFITをstageしてcontinueする。
PCログはlogs/へ保存する。UARTで両RCPUの応答、OpenSBI、U-Bootの=>を確認する。
追加continueは自動送信しない。失敗時は後続コマンドを実行しない。
スクリプトはflash/erase/saveenvを実行しないが、ファームウェア内部の自動書込みまで
このUSB操作だけで保証するものではない。ビルダーはDDR保存等を無効化している。

## 3. Linux起動コマンドを作る（開発PC）

まずUARTでscsi scan、scsi info、part list scsi 0、ls scsi 0:2 /を確認する。
以下のファイル名・PARTUUIDは今回の実機の例。実際の一覧と一致する値を指定する。

```bash
python3 tools/ram-boot.py --phase linux \
  --kernel /Image-6.18.3-keystone \
  --initrd /initrd.img-6.18.3 \
  --dtb /spacemit/6.18.3-generic/k3-pico-itx.dtb \
  --root-partuuid 73708e51-d3a9-4b6f-ab55-894cd1d8b4a0 \
  --boot-partition 2 --output tools/boot-linux.cmd
cat tools/boot-linux.cmd
```

このPC操作はコマンドファイルを作るだけで、Linuxを起動しない。
内容を確認し、tools/boot-linux.cmdの全文をUARTのU-Bootへ貼り付ける。
PCのBashで実行するファイルではない。fdtfileは明示設定し、initrd_sizeはDTBのload前に保存する。
各loadが成功した場合だけbootiへ進む。env_k3.txtと永続envは変更しない。
Linuxのrootfsは通常のrwで起動し、OSによるストレージ書込みはあり得る。

販売元OpenSBIでLinux起動まで確認できた経路だが、生成された各候補の動作は個別に確認する。
Keystone SM/Enclaveの検証は別段階。失敗時は全UARTログとlogs/を保存し、
電源断後FDLを押さず通常起動へ戻る。永続領域を変更していた場合の復旧とは区別する。

[USB RAM起動の詳しい手順](https://github.com/yutaka-ishikawa/Jupiter2/blob/main/doc/jupiter2-ram-boot-guide.md)
