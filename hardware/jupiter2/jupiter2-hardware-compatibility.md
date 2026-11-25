# Milk-V Jupiter 2実機情報とKeystoneファームウェアの適合性

最終更新日 2026-11-26（日本時間）
初回調査 2026-11-08。初回比較ソースは `4011d1c9d`。

## 移植時に使用した実機情報

- 実機では販売元OpenSBIを使うUSB RAM起動でUFS上のLinux起動を確認済み。別名の
  `Image-6.18.3-keystone` でもLinux起動とネットワーク接続を確認。
  [RAM起動ガイド](../../doc/jupiter2-ram-boot-guide.md) · [実機起動記録](../../doc/jupiter2-ram-boot-procedure.md)
- 実機の混在PMPはX100が16、A100が32エントリ。本移植では双方の16枠を使い、
  A100の追加16枠（エントリ16〜31）は無効のまま維持する。混在PMPのQEMU試験では
  全hartの起動とKeystoneサンプルが通った。同居QEMU試験でもKeystoneとOP-TEEの動作を確認済み。
  以下のドキュメントは移植時の記録。
  [混在PMP対応記録](../../doc/jupiter2-heterogeneous-pmp-plan.md)
- 通常ビルドの最終NOR用FITが271,903バイトだった。対象機と今回生成した
  FITで容量を再確認する。
  [容量削減の測定結果](../../doc/jupiter2-firmware-size-reduction.md) · [実機用ビルド手順](../../doc/jupiter2-build-install-test.md)

添付版には、同梱構成で実機の全hartが起動し、KeystoneとOP-TEEのサンプルが通ったとの記載がある。
実機ログと試験時のビルド情報は未照合のため、下の比較表では実機起動の判定を未確認とする。

## 実機RAM起動バイナリの参照入力

過去の `reference-keystone-pmp32` について、提供された
`reference-keystone-pmp32-records.tar.gz` 内の `build-manifest.json` と
`commands.jsonl` を照合した。このビルドで `captures/` から直接読んだファイルはなかった。

| 入力・設定 | ビルド記録 |
| --- | --- |
| OpenSBI | ビルド済みKeystone版 `fw_dynamic.bin`。SHA-256 `828efc179aa30e0eb18cb5822ad1ffeefa5057ef4aef9eb56ee41e2fa5525a62` |
| ESOS | 当時の `work/jupiter2-ram-boot/original/esos.itb`、構成 `conf_dual`。SHA-256 `f6afe0f6bcc1f5448198a349819ce9c46d528d646abd358f6c11f66b9e871cd4` は現在の `vendor/esos.itb` と一致 |
| FSBL・U-Boot | 固定ソース `4c294a06c14e46e9c9cc934373c3e63919703017` から生成、U-Boot FIT構成 `conf_11` |
| サイズ設定 | OpenSBI予約 1,048,576バイト、SPL転送上限 536,870,912バイトを数値で指定 |

現行ラッパーの既定動作では予約領域を生成したELFとDTBから算出し、SPL転送上限を
生成SPLの設定から読む。採取ログを入力にするのは `FASTBOOT_LOG` を明示した場合。
`20261124-165032/spl-fastboot.log` は過去の観測値の転記であり、過去のビルド記録に
そのパスは現れない。NOR用bundleには対象機から採取した容量を別途渡す。
[現行のビルド手順](../../doc/jupiter2-build-install-test.md)

## 別の実機への導入前に比較する項目

[READMEの採取手順](../../README.md#22-導入前の実機情報を採取)で新しい採取IDを作り、
`hardware/jupiter2/captures/<採取ID>/` に保存する。次の表を採取先の
`capture-notes.txt` に写し、「対象機の値・根拠」と「判定」を記入する。
未取得の項目は未確認と記録する。ボードや起動条件が変わる場合は採取IDを分ける。

### 採取差分をスクリプトで確認する

リポジトリのルートから、対象機の採取ディレクトリ名を渡す。

```bash
CAPTURE_ID=20261126-090000  # 対象実機の採取IDに置き換える
python3 scripts/compare-jupiter2-capture.py "$CAPTURE_ID"
```

比較基準はLinux・DTBが `20261108-075700`、ストレージ・NORが
`20261120-101205`、SPL上限が `20261124-165032/spl-fastboot.log`。
販売元4ファイルも比べる場合は、対象機に対応する一式を採取先の `vendor/` に置く。
スクリプトは固定した参照ハッシュを使用するため、リポジトリの `vendor/` を
差し替えた後でも比較基準は変わらない。

結果は `MATCH`、`DIFFERENT`、`UNAVAILABLE`。終了コードは全項目一致が0、
差分または未取得が1、入力エラーが2。DTBはSHA-256に加え、モデル、compatible、
timebase、CPU・メモリ・予約領域を比較する。再構成DTBは項目比較に使う。
起動設定やストレージ記録はファイルのSHA-256を比較し、差が出たファイルは個別に確認する。
PMP CSR、実際に使用中の起動元、OP-TEEの動作はUARTや実機試験で別途確認する。


| 比較項目 | 参照機の記録 | 対象機の値・根拠 | 判定 |
| --- | --- | --- | --- |
| ボード・ファームウェア | K3 Pico ITX。販売元4ファイルは `vendor/` に保存 | モデル、販売元リリース、4ファイルのSHA-256 | |
| Linux版と構成 | 初回採取は `6.18.3-generic` | `uname.txt`、起動するImage・initrd・DTBの名前とハッシュ | |
| CPU・PMP・timebase | X100×8、A100×8、PMP 16/32、24 MHz | `lscpu.txt`、`cpu-online.txt`、CPU種類別のM-mode UART記録 | |
| RAMと予約メモリ | 下記の初回実機観測値 | `running.dtb`、`iomem.txt`、`meminfo.txt` | |
| DTBの段階 | Linux原本は `spacemit,k3-pico-itx`、保存済みU-Boot FITの抽出DTBは `spacemit,k3` | 各段階のDTB、root compatible、SHA-256 | |
| 起動媒体・Linux起動設定 | UFSからの起動記録あり | UART、`lsblk.txt`、`findmnt.txt`、PARTUUID、使用中の `env_k3.txt` 等 | |
| OpenSBIのNOR区画 | `opensbi` はオフセット `0x1b0000`、393,216バイト、消去単位4,096バイト | `proc-mtd.txt`、`jupiter2-nor-capacity.json`、使用中の起動元 | |
| SPL Fastboot転送上限 | 過去の問い合わせで `0x20000000`（512 MiB） | 対象SPLの `spl-fastboot.log` | |
| OP-TEE同梱 | 実機起動未確認 | 実機用ドメイン・MPXY・メモリ予約、UART起動ログ、TA応答 | |

DTBのハッシュ差は、同じ起動段階の原本同士で確認し、差があれば
`compatible`、hart、メモリ、予約領域を比較する。NORの容量差は対象機の
`capacity_bytes` をbundle作成へ渡す。SPLの転送上限はNOR容量と別に記録する。
[実機用ビルド手順](../../doc/jupiter2-build-install-test.md) · [NORへの導入と復旧](../../doc/milkv-jupiter2-opensbi-replacement.md)

## 入力資料と記録の保存方針

| 保存場所 | 採取・生成した内容 |
| --- | --- |
| `captures/20261108-075700/` | Linuxに渡されたDTB原本、CPU・メモリ配置と起動ログ |
| `captures/20261120-101205/` | ストレージ・起動設定とOpenSBI区画のバックアップ |
| `captures/20261124-165032/spl-fastboot.log` | 過去のSPL Fastboot実測値の転記。採取日は未確認 |
| `vendor/` | `FSBL.bin`、`esos.itb`、`fw_dynamic.itb`、`u-boot.itb` および抽出DTB |

販売元ファイルを変更したら `python3 scripts/extract-jupiter2-vendor-dtbs.py` で
抽出DTBを更新する。実機採取と生成物の保存方法は[実機資料のREADME](README.md)を参照する。

2026-11-08の調査で使用したアーカイブには、次の6ファイルが含まれていた。

| ファイル | 確認できる内容 |
| --- | --- |
| `running.dtb` | Linuxへ渡されたフラットなDTB。151,680バイト。 |
| `cpuinfo.txt` | 各hartのCPU種類、ISA、MMU、実装ID。 |
| `lscpu.txt` | 16 CPUのオンライン状態、CPU種類、周波数等。 |
| `uname.txt` | 実機Linuxの版。 |
| `dmesg.txt` | Linux起動、SBI機能検出、タイマー、割り込み、予約メモリ、NORパーティション。 |
| `iomem.txt` | Linuxが認識しているアドレス範囲。 |

登録した[採取アーカイブ](jupiter2-linux-capture-20261108-075700.tar.gz)のSHA-256：

```text
bda3228d2f471698ea9d4fa42e2ece8dbb6253813dc8a9baed85614e1cf6cbfa
```

DTBのSHA-256：

```text
19151092f33a1a0b340c21ba3aa88d6494e6726ebb9f30f802db758f38f006a8
```

将来のチャットでも参照できるよう、主要な実機値と各入力ファイルのハッシュを[機械可読のインベントリ](jupiter2-hardware-inventory.json)にも保存した。元のログ・DTBにはボードの個体情報やブート媒体の識別子等が含まれるため、それらの全文はこの文書へ転載していない。以下の抜粋とインベントリには動作条件の照合に必要な値を残した。

## 確認できた実機構成

### ボード、Linux、OpenSBI

| 項目 | 観測値 |
| --- | --- |
| Linuxが表示するモデル | `SpacemiT K3 Pico ITX` |
| DT root compatible | `spacemit,k3-pico-itx`（単独） |
| Linux | `6.18.3-generic`、ビルド`#1.0.5.4` |
| Linuxのビルド用コンパイラ | Bianbu GCC 15.2.0 |
| Linuxのビルド用リンカー | Bianbu GNU Binutils 2.46 |
| SBI仕様 | 2.0 |
| SBI implementation | ID `0x1`、Version `0x10006`（OpenSBI 1.6に対応） |
| 検出されたSBI機能 | TIME、IPI、RFENCE、SRST、DBCN、HSM |

現在のソースのOpenSBI版も1.6である。ただし、SBIの版番号から正確なベンダーコミットや設定までは特定できない。また、上記GCC・リンカーの版はLinuxについての表示で、OpenSBIのビルドツールの版ではない。

### CPU：16 hartだが同一種類ではない

| hart ID | CPU | `marchid` | `mimpid` | MMU |
| --- | --- | --- | --- | --- |
| 0–7 | Spacemit X100 | `0x8000000058000002` | `0x33d8a600` | Sv39 |
| 8–15 | Spacemit A100 | `0x8000000041000002` | `0x10000000d5686200` | Sv39 |

全hartの`mvendorid`は`0x710`。`lscpu`のオンラインCPUは0–15で、Linuxログにも`Brought up 1 node, 16 CPUs`がある。

提供された`cpuinfo.txt`では16 hartの`isa`文字列は同一であり、Sstc、Smaia、Ssaia、Svpbmt等を含む。ただし、同じISA表示からPMPの個数・粒度・初期配置・PMAやキャッシュの動作まで同一と判断することはできない。

現在のQEMU起動は全hartに同じ`rva23s64` CPUモデルを指定しており、X100/A100の混成そのものを再現していない。

### メモリと予約領域

Linuxへ公開されるメモリ範囲は次のとおり。

```text
base          0x102000000
size          0x7fe000000
end inclusive 0x8ffffffff
```

`iomem.txt`も`102000000-8ffffffff : System RAM`を示す。DTにはそれより下にRCPU、RPMI、M-mode等の予約領域がある。

| DTノード・用途 | 先頭 | サイズ |
| --- | --- | --- |
| `mmode_resv0` | `0xd4282000` | `0x1000` |
| `mmode_resv1` | `0x100000000` | `0x100000`（1 MiB） |
| `mmode_resv5` | `0x100800000` | `0x400000`（4 MiB） |
| RPMI共有領域`rpmi0` | `0x100e00000` | `0x4000`（16 KiB） |

`mmode_resv1`という名前とアドレスはファームウェア配置の手掛かりだが、これだけで実際のOpenSBIロード先やその領域全体の所有者を断定しない。RCPU・表示・CMA等の予約領域もあるため、Linuxへ見えるDRAMの先頭だけを基準に実機ファームウェアを配置してはいけない。

工場出荷環境のログには`rcpu1_runtime`と`mmode_resv5`の予約範囲の重複警告もある。今回のKeystone修正による警告ではなく、提供された既存環境の記録である。この警告だけから新しい障害を断定していない。

### タイマーと割り込み

| 項目 | 実機DT・ログ | QEMUモデルとの照合 |
| --- | --- | --- |
| timebase | 24,000,000 Hz | 一致 |
| CLINT | `0xe081c000`、サイズ`0x4000`、`riscv,clint0` | 基本アドレス・サイズ一致 |
| S-mode IMSIC | `0xe0400000`、サイズ`0x400000` | 一致 |
| IMSIC ID | 1 hartあたり511 IDs、63 guest IDs | 一致 |
| IMSIC索引 | hart-index-bits=4、guest-index-bits=6 | 一致 |
| S-mode APLIC | `0xe0804000`、サイズ`0x4000`、512 sources | 一致 |
| UART | `0xd4017000`、サイズ`0x100`、IRQ 42 | 一致 |
| UARTアクセス | reg-shift=2、reg-io-width=4 | 一致 |

ログには以下がある。

```text
riscv-imsic: interrupt-controller@e0400000: providing IPIs using interrupt 1
sched_clock: 64 bits at 24MHz
riscv-timer: Timer interrupt in S-mode is available via sstc extension
```

これは既存LinuxのS-mode側の動作証拠である。SMが使うM-mode IPIの配線、M-modeタイマー割り込み、全hartのPMP更新応答を確認した証拠ではない。Linux用DTBにはM-mode IMSIC/APLICのノードが見当たらないが、OpenSBIのfixup後のDTでは削除される場合があり、実機に存在しないという結論にはならない。

## ビルド・導入条件と過去の比較記録

### 1. OpenSBI用NOR区画と過去のサイズ比較

DTには次のパーティションがあり、Linux起動引数の`384K@1728K(opensbi)`とも一致する。

```dts
opensbi@1b0000 {
    reg = <0x1b0000 0x60000>;
};
uboot@210000 {
    reg = <0x210000 0x5f0000>;
};
```

| 対象 | サイズ |
| --- | --- |
| 既存OpenSBI領域 | `0x60000` = 393,216バイト |
| 照合したローカル`fw_dynamic.bin` | 532,320バイト |
| 超過分 | 139,104バイト |

初回に照合したファイルはSMトレースを有効にしてビルドしたもので、SHA-256は以下。

```text
668bfa1a0c57351456117001f7f8b413825eaff7d8c2ce44ee2e0d6810caceed
```

このraw binを既存NORレイアウトの領域へ単純に書く方法は成立しない。領域外まで書くと、隣接するU-Boot領域に入る。FITヘッダー等を追加する場合は、その実際のコンテナサイズも評価する必要がある。

その後、通常の `make opensbi` でBIN 270,248バイト、最終FIT 271,903バイトを確認した。
導入時は今回生成した最終FITと対象機の実測区画容量を照合する。
[サイズ削減調査](../../doc/jupiter2-firmware-size-reduction.md)

### 2. OpenSBIへ最初に渡されるDTBとroot compatible

現在の`opensbi/platform/generic/spacemit/spacemit_k3.c`の対応文字列は次の二つ。

```text
spacemit,k3
riscv-spacemit
```

一方、提供された`running.dtb`のrootには次しかない。

```dts
model = "SpacemiT K3 Pico ITX";
compatible = "spacemit,k3-pico-itx";
```

`fw_platform_lookup_special()`はrootのcompatibleを照合してplatform overrideを選ぶ。**このDTBをそのまま現在のOpenSBIへ渡した場合、K3 overrideは選ばれない。** その場合はCCI、クラスタ起動等の実機overrideも呼ばれない。以前のSstc抑止hookもこの影響を受けたが、現在のtimer共存処理はgeneric共通経路とSMの切替へ接続している。

保存済みの販売元U-Boot FITから抽出した `vendor/u-boot-k3-pico-itx.dtb` の
root compatibleは `spacemit,k3`。対象機のOpenSBIへの引き渡しを確認するには、
使用したFITとUARTを照合する。Linuxから採取した `running.dtb` はLinux側の確認に使う。

### 3. PMP前提と混成CPU

実機ログでX100が16、A100が32エントリと確認された。初期版ではA100のPMP設定が
`-2` を返し、CPU起動に失敗した。現在の通常SMビルドは `KEYSTONE_PMP_PROFILE=mixed`
を既定とする。対象機では全hartのPMP読戻しとLinuxのオンラインCPU数を確認する。
[実機ログと修正候補の試験](../../doc/jupiter2-heterogeneous-pmp-plan.md)

### 4. Sstcと固定オンラインポリシー

工場出荷側のLinuxはSstcを利用している。現在はLinuxのSstcを維持し、
enclave/Eyrie実行中だけstimecmpを退避してSTCEを無効化、SM用MTIMERを設定する
[共存方式](../../doc/keystone-sstc-coexistence.md) に変更した。ISA情報からsstcを削除しない。
実機でもSM用のMTIMERドライバ・DT・周波数・割込み配線の確認が必要で、共存動作は未確認。

Keystone構成ではhart STOP/SUSPENDを拒否するため、工場出荷側と同じCPU hotplug・
省電力動作を保証するものではない。

### 5. shutdown／rebootは実機のデバイスで確認する

実機にはRPMI共有領域、SBI MPXY mailbox、RPMI regulator・RTC・power keyを使う記録があり、SBI SRSTも検出されている。これは既存ファームウェアでRPMI系サービスやSBIリセット機能が提供されている根拠になる。

ただし、Linux DTBには`riscv,rpmi-system-reset`、`syscon-poweroff`、`syscon-reboot`のノードは見当たらない。OpenSBI入力DTBが別なら、そこに定義されている可能性がある。既存環境で実際に電源断・再起動が成功するかも、この採取ログだけでは確認できない。

今回のshutdown修正は、QEMUのsysconアドレスをハードコードせず、登録されたリセットデバイスを呼ぶ。そのため実機でもRPMI等を選べる構造だが、実機のリセット先ファームウェアが全hartを止めない終了経路を受け付けるかは実動作で確認する必要がある。

### 6. 実機のロード形式と配置

リポジトリの`opensbi/platform/generic/spacemit/fw_dynamic.its`はOpenSBIのload/entryに`0x100000000`を指定する。一方、QEMUモデルのDRAM先頭は`0x102000000`であり、両者を混同しない。

照合したファームウェアELFは位置独立の`DYN`、リンク上の`_fw_start=0`、`_fw_end=0x88000`だった。この範囲は静的なファームウェア範囲の手掛かりであり、scratch、スタック、ヒープ、DTや後続のロード物も含めた実機配置の正当性を証明するものではない。実機FSBL等のロード先・確保サイズ・`fw_dynamic`引き渡し条件・FIT形式を照合する必要がある。

## 次に必要な情報と検証順序

1. 対象機の採取結果を比較表へ記入し、使用中の起動媒体、販売元リリース、復旧用データを確定する。
2. 生成したFSBL・統合FITをUSBからRAMに転送し、DDR、ESOS、OpenSBI、U-Boot、Linuxの到達点をUARTで記録する。
3. Keystone採用時は全hartと両CPU種類でサンプルを確認する。OP-TEE同梱時は実機DTBとCore起動、Linuxドライバ、TAの応答を確認する。
4. NORへ導入する場合は、対象機の区画容量と今回の最終FITを照合し、復旧用バックアップと読戻し結果を保存する。

## 関連ソースと既存の調査記録

- [実機インベントリ](jupiter2-hardware-inventory.json)
- [QEMU Jupiter2モデル](../../qemu/hw/riscv/jupiter2.c)
- [QEMU定数](../../qemu/include/hw/riscv/jupiter2.h)
- [OpenSBI platformの選択](../../opensbi/platform/generic/platform.c)
- [OpenSBI K3 override](../../opensbi/platform/generic/spacemit/spacemit_k3.c)
- [実機向けFITテンプレート](../../opensbi/platform/generic/spacemit/fw_dynamic.its)
- [Keystoneのビルド定数](../../keystone/sm/tools/k3_rv64_compile_audit.py)
- [Keystoneプラットフォーム定数](../../keystone/sm/src/platform/spacemit_k3/platform.h)
- [PMP情報の検査](../../opensbi/include/sbi/k3_pmp_partition_evidence.h)
- [Eyrie入口の修正](../../doc/keystone-eyrie-entry-build-id.md)
- [システム終了の修正](../../doc/keystone-system-reset.md)

## Zkr乱数拡張の追加調査

公式資料・K3 CPU定義・実機情報からZkrの利用可能性は確認できていない。
[調査結果と実機での確定方法](../../doc/jupiter2-zkr-investigation.md)を参照。
