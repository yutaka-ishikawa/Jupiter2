# Jupiter2の実機資料

開発PCのリポジトリ直下のこのディレクトリに、Jupiter2実機の採取結果と
実機起動用の配布ファイルを集約する。

| 保存先 | 内容 |
| --- | --- |
| `jupiter2-hardware-inventory.json` | 公開用インベントリ。過去の実測値と原本のハッシュ |
| [実機調査記録](jupiter2-hardware-compatibility.md) | 元資料から確認済みの構成、UART・DTBの抜粋、照合結果 |
| `captures/<採取ID>/` | 実機から採取したDTB、UART、CPU・RAM・ストレージ情報と復旧用バックアップ |
| `vendor/` | 対応する販売元のFSBL・U-Boot・OpenSBI・ESOSなどの入力ファイル |

採取IDは `20261124-01` のように付け、起動条件ごとにフォルダーを分ける。
`running.dtb`、`uart.log`、`cpuinfo.txt`、`lscpu.txt`、`uname.txt`、
`dmesg.txt`、`iomem.txt` などを採取できた範囲で保存する。採取元、日時、
ボード・起動構成、採取コマンド、SHA-256も同じフォルダーに記録する。

手元の旧 `work/jupiter2-ram-boot/original/` にある販売元ファイルは
`vendor/` に、実機採取済みDTBやログは対応する `captures/<採取ID>/` に移す。
`captures/` はGitの追跡対象外。QEMUの生成DTBと比較用DTSは
`.build-k3/dtb-compare/` に置く。

[DTBの採取とQEMUとの差分確認](../../doc/jupiter2-qemu-hardware-test-gaps.md#8-実機dtbを基準にqemuの再現範囲を調べる)


## 使用する実機との照合

**QEMUとの比較や実機向けビルドに使う前に、手元の実機とこのディレクトリの
資料が同じボード・起動構成を示すことを確認する。** 実機から現在のDTBを再採取し、
保存した原本のSHA-256と照合する。実機のモデル・`compatible`、hart ID、
搭載RAM、予約領域、OpenSBIとLinuxの版、起動媒体、選択したDTB名も照合する。
ハッシュが異なる場合は採取段階や起動条件の差を調べ、違いを記録する。
ボードや構成が異なる場合は新しい採取IDを作り、その資料をQEMU比較の入力に使う。

過去に採取した Linux の `running.dtb` と実機ログのハッシュはインベントリに記録している。
販売元の起動ファイル4点は `vendor/` に保存する。

## 販売元FITからDTBを抽出

リポジトリのルートで、`lzop` をインストールした環境から実行する。

```bash
python3 scripts/extract-jupiter2-vendor-dtbs.py
```

スクリプトは `vendor/u-boot.itb` の `conf_11` と `vendor/esos.itb` の
`conf_dual` を読み、FIT内のハッシュを検証してから、同じ `vendor/` に
`u-boot-k3-pico-itx.dtb` と `esos-rcpu{0,1}-dtb-pico-itx.dtb` を生成する。
入力ファイルを入れ替えたら再実行する。

QEMUとの照合では、U-Boot FITのDTBを起動時構成の資料として使い、
Linuxに渡された実機の `captures/<採取ID>/running.dtb` があればそちらも
QEMUの生成DTBと比較する。ESOSの2個のDTBはRCPU用。
QEMUの同居用DTBは、QEMUモデルで実装されているデバイスとOpenSBIドメイン定義を
確認した入力から生成する。

## 別の実機で再現する順序

1. `vendor/` の `FSBL.bin`、`esos.itb`、`fw_dynamic.itb`、`u-boot.itb`
   が、使用するJupiter2のボード構成と販売元リリースに対応することを確認する。
   `dumpimage -l` でITBの構成を見て、入手元・リリース・SHA-256を記録する。
2. 一致しない場合は、旧ファイルを退避して、対応する一式で `vendor/` を入れ替える。
   ボードや起動構成が変わった場合は、Linuxに渡されたDTBも再採取し、
   `captures/<新しい採取ID>/running.dtb` に保存する。以前の採取記録は保持する。
3. 入力を変更した場合、または生成物がまだない場合は、上の抽出スクリプトを実行し、用途に応じて再生成する。
   - **実機RAM起動**では [RAM起動ガイド](../../doc/jupiter2-ram-boot-guide.md) の
     参照ビルダー `scripts/build-jupiter2-reference-ram-boot.py` を実行する。
     ガイドに従って `fw_dynamic.itb` から `fw_dynamic.bin` を抽出し、
     対応する `esos.itb` と一緒に指定する。参照ビルダーは固定ソースから
     FSBLとU-Bootを再ビルドし、選択した構成に対応するDTBを含む統合FITを作る。
     販売元のFSBL・U-Bootを入力として使う手順は
     [RAM起動手順](../../doc/jupiter2-ram-boot-procedure.md) を参照する。
   - **実機LinuxのDTBを加工する場合**は、Linuxへ渡すボード用DTBを入力に
     `scripts/prepare-jupiter2-keystone-linux-dtb.py --input <元DTB> --output <新DTB>`
     を使う。統合FIT内のファームウェア向けDTBとは起動段階が異なる。
   - **QEMUのOP-TEE同居**では、最新の実機資料をQEMU設定と照合した上で、
     適合を確認したDTBにOpenSBIドメインを設定し、
     `scripts/prepare-k3-qemu-optee-dtb.py --optee-first <入力DTB> <新boot.dtb>`
     で同居設定を生成する。このスクリプトの入力にはOpenSBIドメインの定義が必要。
     [実機DTBとの照合手順](../../doc/jupiter2-qemu-hardware-test-gaps.md#8-実機dtbを基準にqemuの再現範囲を調べる)

生成先には新しい出力名を指定し、使用した入力のSHA-256と出力を対応付ける。
