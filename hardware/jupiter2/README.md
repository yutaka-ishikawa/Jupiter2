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
両フォルダーの内容はGitの追跡対象外。QEMUの生成DTBと比較用DTSは
`.build-k3/dtb-compare/` に置く。

[DTBの採取とQEMUとの差分確認](../../doc/jupiter2-qemu-hardware-test-gaps.md#8-実機dtbを基準にqemuの再現範囲を調べる)


## 使用する実機との照合

**QEMUとの比較や実機向けビルドに使う前に、手元の実機とこのディレクトリの
資料が同じボード・起動構成を示すことを確認する。** 実機から現在のDTBを再採取し、
保存した原本のSHA-256と照合する。実機のモデル・`compatible`、hart ID、
搭載RAM、予約領域、OpenSBIとLinuxの版、起動媒体、選択したDTB名も照合する。
ハッシュが異なる場合は採取段階や起動条件の差を調べ、違いを記録する。
ボードや構成が異なる場合は新しい採取IDを作り、その資料をQEMU比較の入力に使う。

過去に照合した `jupiter2-info.tar.gz` の構成とSHA-256はインベントリに記録済み。
現作業環境ではアーカイブ原本、`running.dtb`、実機の各採取ファイル、
ベンダー版 `esos.itb` は確認できなかった。
