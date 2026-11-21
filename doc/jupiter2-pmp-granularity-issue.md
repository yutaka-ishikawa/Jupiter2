# Jupiter2 RAM起動：RPMI領域とPMP粒度の不一致（KSB-058）

登録日：2026-11-21。状態：実機で原因を確認。K3限定の修正候補を実装・クロスリンク済み。修正後の実機起動と別Linux DTの整合は未検証。

## 1. 確認できた到達点と停止箇所

開発PCからFSBLと開発版OpenSBI＋Keystone SMを含む統合FITをRAMへ転送した。
実機UARTでOpenSBI v1.6、[SM/TIMER]、実機のplatform情報が表示された。
従って、転送後のUSB消失だけを理由としたハングではなく、開発版の初期化処理へ到達している。
U-Bootへの移行、Linux起動、Enclave実行はこの試験では未達である。

```text
[SM/TIMER] host=sstc enclave=mtimer slice-us=10000
Platform Name               : spacemit k3 pico itx board
Firmware Base               : 0x100000000
Firmware Size               : 662 KB
Boot HART PMP Count         : 16
Boot HART PMP Granularity   : 12 bits
Domain0 Next Address        : 0x0000000102000000
Domain0 Next Mode           : S-mode
[K3-PMP] region base=0xcac90c00 order=8 flags=0x80000003 pmp=0x0
[K3-PMP] REJECT unrepresentable region base=0xcac90c00 order=8 gran=12
[K3-PMP] configure-return Hart=0 rc=-2
init_coldboot: PMP configure failed (error -2)
```

Next Modeは移行予定を示す。S-modeへ移行できたことを意味しない。
Firmware Sizeの測定値も今回の候補ビルドについてのもので、別ビルドの保証にはしない。

## 2. 問題の内容

| 項目 | 実測・ログから分かること |
| --- | --- |
| 登録領域 | 0xcac90c00–0xcac90cff、256 bytes（order=8） |
| 実機PMP | 16 entries、最小粒度4 KiB（gran=12） |
| 拒否処理 | opensbi/lib/sbi/sbi_hart.cのk3_keystone_root_pmp_configure |
| 権限 | MMIO、M-modeのR/W、S/Uは不許可。legacy PMPへ変換した権限は0 |
| 直接の原因 | 登録領域のorderが実機PMP粒度より小さいため、保護設定を表現できない |
| 適合する包含ページの候補 | 0xcac90000–0xcac90fff、4 KiB。採用は周辺の権限調査後に決める |

legacy PMPではロックされていない通常entryのM-modeアクセスとS/U権限を区別して扱う。
本件のpmp=0は単に領域を削除してよいという意味ではない。
後段の全アドレスS/U許可より先に置くことで、当該MMIOをS/Uから保護している。

K3統合の拒否検査を外す、domain entryを捨てる、全domain領域を無条件で丸める方法は採用しない。
小領域を4 KiBへ広げる場合は、同ページの他のS/U許可や他domainの領域を奪わないことが必要。

## 3. 調査と修正の手順

1. この記録と継続台帳へ不具合を登録する。実機証拠と推定を分ける。
2. 使用DTのreg／reg-namesから0xcac90c00の登録元を追い、RPMI queueかdoorbellか等を特定する。
3. ドライバーで使う実際の窓・オフセットと、PMPに登録する保護窓を分けて確認する。
4. 同じ4 KiBページ内のレジスター、DTノード、他domain・PMPの権限を調べる。
   Linux向けDTとU-Bootが引き渡すDTは同一とは限らないため、取り違えない。
5. 影響が確認できた範囲で修正する。K3固有の登録元で実機粒度に対応する案を優先して検討する。
   追加の禁止領域や既存のS/U許可領域との重複が不明なら、その条件では拒否を維持する。
6. 設定した粒度、変換前後の範囲、元のM/S/U権限を説明できる診断を残す。
7. クロスビルドと必要な静的確認を行い、対応する実ゲストが利用できる場合は実ゲストで検証する。
   模擬SBI／PMP／CSR試験を実機検証の代用にはしない。
8. 修正BINで同じ構成の統合FITを作り直し、NORへ書かずRAM起動で検証する。
9. 合格条件を満たしてから、Linux・Enclaveへ検証を広げる。実機で未実行の項目は未確認と記録する。

## 4. 次のRAM起動で確認すること

開発PCで修正OpenSBI＋SMをビルドし、[RAM起動手順](jupiter2-ram-boot-procedure.md)の
SM版生成例を使う。ESOSは--esos-configuration conf_dual、U-Bootはconf_11を維持する。
出力先は新しいディレクトリにし、以前のBIN・FITとSHA-256、ビルドコミット、設定を保存する。

FDL→FSBL→統合FITの順に転送する。UARTは電源投入前から保存する。
U-Boot到達後にfastbootへ入った場合に限り、PCのgetvar versionへの応答を確認して
最後のcontinueでfastboot待機を抜ける。PMP設定で停止中なら、この追加continueは解決策にならない。

| 確認対象 | 合格条件 |
| --- | --- |
| 対象領域 | 修正した範囲と権限が意図どおりで、粒度拒否が解消 |
| その他のdomain領域 | 既存のS/U許可・禁止が維持され、別の表現不能領域やslot不足がない |
| PMP設定 | readbackと検証が成功し、configure failedが出ない |
| 次段 | 実際にU-BootのバナーとUARTプロンプトへ到達 |
| Linux | 同じ新カーネルで起動、CPU、ストレージ、ネットワークを確認 |
| Keystone | SM初期化と同梱hello等を実行。U-Boot到達だけで合格にしない |

## 5. 試験の制約と失敗時の対応

現時点の証拠はユーザー提供UARTログ。修正後の実機起動は未検証である。
販売元U-Boot単体のRAM起動とUART操作は確認済みだが、SM版の動作保証ではない。

販売元U-BootではDDR training情報のNOR自動保存が観測されている。
flashコマンドを実行しない試験でも、起動ソフトウェアの自動書込みを別途扱う。
本調査ではNORへのファームウェア更新やsaveenvを実施しない。

失敗時はUARTを保存し、電源を切ってFDLを押さず通常起動へ戻す。
開発版のRAM内容を破棄しても、既に発生した永続書込みが復元されるわけではない。

## 6. 調査・修正結果

以下へ登録元、周辺ページの調査結果、採用した変更、ビルド／実機検証の結果を追記する。

### 6.1 登録元と隣接レジスター

登録元はopensbi/lib/utils/mailbox/fdt_mailbox_rpmi_shmem.cの
rpmi_shmem_transport_init()で、reg-namesがdb-regの窓を
sbi_domain_root_add_memrange(reg_addr, reg_size, reg_size, M-only MMIO flags)へ渡す。
公開されている販売元U-BootのK3 DTは、RPMI nodeの最後のregを
0xcac90c00／0x100、reg-nameをdb-regとする。ユーザーの実測domain情報と一致する。
この公開ソースを、ユーザー手元の全バイナリーと同一だと検証したわけではない。

参照：[U-BootのK3 DT](https://github.com/spacemit-com/uboot-2022.10/blob/k3-br-v1.0.y/arch/riscv/dts/k3.dtsi)。

本リポジトリのlinux-k3/arch/riscv/boot/dts/spacemit/k3.dtsiでは次の配置である。

| 物理範囲 | 用途 |
| --- | --- |
| 0xcac90000–0xcac903ff | mailbox0 |
| 0xcac90400–0xcac907ff | mailbox1 |
| 0xcac90800–0xcac90bff | mailbox2 |
| 0xcac90c00–0xcac90fff | mailbox3。RPMIの窓0xcac90c00–0xcac90cffを含む |
| 0xcac91000–0xcac913ff | mailbox4。別の4 KiBページ |

同じLinux DTではrcpu0がmailbox3を参照するがstatusはdisabled。
rcpu1はmailbox4を参照してokayで、今回の保護ページの外にある。
ただしmailbox0〜3のコントローラー自体はokayであり、Linux driverはprobe時にIRQを登録する。
consumerが無効でも、IRQ処理等のMMIOアクセスまで発生しないと保証できない。

**256-byteの禁止と同ページ内のS/U許可を、4 KiB粒度のPMPだけで同時に表現することはできない。**
ページ全体のM-mode所有を採る場合、残り3840 bytesについてもS/Uアクセスが禁止される。
「元の全S/Uアクセス権を変えずに4 KiBへ丸められる」という解釈は誤りである。
この所有契約に合わない構成では、RPMI／ESOSの配置変更やSBI経由アクセス等の別設計が必要になる。

### 6.2 実装した修正候補と守備範囲

K3かつCONFIG_K3_KEYSTONE_SMのときだけ、既知のdb-reg＝0xcac90c00／0x100を
保護範囲0xcac90000／0x1000で登録する。queueやdoorbellの実アクセス先、サイズ、
オフセット、メッセージ形式は変えない。他の小領域や他platformは変更しない。

- 現時点のroot domainに明示的なS/U許可との重複があれば拒否する。
  全アドレスのS/U fallbackだけは、M-only保護で上書きする対象として区別する。
- 引き渡されたファームウェアDTに同ページを使用する有効なspacemit,k3-mailboxまたは
  spacemit,k3-rmailboxがあれば拒否する。DTを黙って変更しない。
- domain登録に成功した場合に次の診断を出す。
- 汎用PMPの粒度検査、slot配置、readback、SM admissionは維持する。

```text
[K3-RPMI] doorbell 0xcac90c00/0x100 protected by M-only page 0xcac90000/0x1000
```

この候補は「mailbox0〜3をM-mode専用とする」構成に限定する。
起動時DTに競合が見つかる場合は拒否するため、全構成で起動を保証する修正ではない。

**Linux用DTを別途ロードする場合、そのDTにも同じ条件を適用する必要がある。**
ファームウェアは未来にLinuxが選ぶ別DTの内容まで検査できない。
Linux用のmailbox0〜3／同ページのremote mailboxと、そのconsumerが直接アクセスしない構成であることを
実際の起動DTで確認し、必要な無効化・別経路化を明示的に検討する。
既存のLinux DTを本修正が自動的に書き換えることはない。
ここが確認できるまでは、次の試験はU-Boot到達の確認までにとどめる。
Linux向けDTの一括上書きや、有効なremoteprocの無断停止は行わない。

### 6.3 ビルドと検証の記録

K3 Keystone audit構成で、実際のSMオブジェクトをリンクしたfw_dynamic.elf／BINを作成し、
RISC-V ELF、SMシンボル、enclave mtvecの4-byte整列を確認した。
実機起動も実QEMUゲストでの対象経路実行も、ここでは未実施である。
ホスト模擬PMP試験は追加していない。

SMなしのk3_defconfigでもfw_dynamic.elf／BINの生成に成功した。
この確認は条件付きコンパイルとリンクの確認であり、PMP配置やLinuxとの互換性の証明ではない。

### 6.4 開発PCで再ビルドし、U-Boot到達まで再試験する

既存のビルド依存を導入済みの開発PCで、publicリポジトリのルートから実行する。

```bash
set -euo pipefail
mkdir -p work/jupiter2-pmp-retest
# 通常のprovider-unavailable設定でOpenSBI＋SMを再ビルドする。
KEYSTONE_SM_TRACE=0 make opensbi JOBS=4 \
  2>&1 | tee work/jupiter2-pmp-retest/build.log

# 実測したSPLの受信上限。NOR区画容量ではない。
SPL_DOWNLOAD_BYTES=0x20000000
# 前回の同系ビルドではFirmware Size=662 KBだった。
# 再ビルド後も必要量と配置を確認する。1 MiBを無条件に実測済みと扱わない。
KEYSTONE_SBI_RESERVE_BYTES=0x00100000

python3 scripts/build-jupiter2-ram-boot-image.py \
  --fsbl work/jupiter2-ram-boot/original/FSBL.bin \
  --uboot-itb work/jupiter2-ram-boot/original/u-boot.itb \
  --esos-itb work/jupiter2-ram-boot/original/esos.itb \
  --opensbi-bin .build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin \
  --configuration conf_11 \
  --esos-configuration conf_dual \
  --board k3-pico-itx \
  --variant keystone \
  --opensbi-reserve-bytes "$KEYSTONE_SBI_RESERVE_BYTES" \
  --max-download-bytes "$SPL_DOWNLOAD_BYTES" \
  --output work/jupiter2-ram-boot/keystone-pmp-retest
```

出力先が既存なら別名を指定する。元のFITを取り違えないよう、fit-list.txtとmanifestを確認する。
上記はファームウェアDT・Linux DTの所有契約を満たすことを前提とした候補生成である。
DTの競合を消すために単に既存nodeを削除する手順ではない。

FDLへ入り、UARTログを保存した状態で開発PCから次を実行する。

```bash
sudo fastboot devices
sudo fastboot stage work/jupiter2-ram-boot/keystone-pmp-retest/images/FSBL.bin
sudo fastboot continue
```

DDR初期化完了とUSB再認識を確認してから、次を実行する。

```bash
sudo fastboot -s HW4MPK3321280144 stage \
  work/jupiter2-ram-boot/keystone-pmp-retest/images/ram-boot-keystone.itb
sudo fastboot -s HW4MPK3321280144 continue
```

期待する変化は、K3-RPMIのページ登録診断、対象regionのorder=12、PMP検証成功、
そしてU-Boot到達である。別の領域やslot数で拒否された場合も、拒否を無効にせずログを保存する。
U-Bootが起動後fastboot待機に入った場合だけ、応答を確認して待機を抜ける。

```bash
sudo fastboot -s HW4MPK3321280144 getvar version
sudo fastboot -s HW4MPK3321280144 continue
```

UARTでU-Bootのプロンプトに到達したら、まずそこで停止する。
Linuxへ進む前に実際のLinux用DTとの整合を確認する。

### 6.5 今回のクロスビルド結果（2026-11-21）

| 構成 | BINサイズ | BIN SHA-256 |
| --- | --- | --- |
| K3 Keystone audit（SMあり） | 270248 bytes | 925102f4af61902bcfa17e8e791d1b60f1c565b87b6cad944a38e46f1c3d9549 |
| k3_defconfig（SMなし） | 269600 bytes | 941f32c66ebf89e2fb6a3934ebee8633735a0155022ce960d12eb61c76bd3093 |

これらは開発環境内のビルド成果物の記録であり、ユーザーの実機へ転送済みの値ではない。
統合FITの再生成と修正後の実機ログは未取得。新しい実QEMUゲストのPASSも主張しない。
