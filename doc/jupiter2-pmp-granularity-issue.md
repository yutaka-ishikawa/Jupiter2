# Jupiter2 RAM起動：RPMI領域とPMP粒度の不一致（KSB-058）

登録日：2026-11-21。状態：KSB-058の粒度検査通過後、実機でKSB-059の容量拒否を確認。KSB-059／060／061／062の候補を実装・クロスビルド済み。修正後の実機起動と別Linux DTの整合、Enclaveの同時動作は未検証。

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
  --fsbl hardware/jupiter2/vendor/FSBL.bin \
  --uboot-itb hardware/jupiter2/vendor/u-boot.itb \
  --esos-itb hardware/jupiter2/vendor/esos.itb \
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

## 7. 修正後の実機結果：粒度を通過し、PMP容量で停止（KSB-059）

2026-11-21、ユーザー提供の再試験UARTログで次を確認した。

```text
[K3-RPMI] doorbell 0xcac90c00/0x100 protected by M-only page 0xcac90000/0x1000
Domain0 Region00 : 0x00000000cac90000-0x00000000cac90fff M: (I,R,W) S/U: ()
[K3-PMP] region base=0xcac90000 order=12 flags=0x80000003 pmp=0x0
...
[K3-PMP] REJECT root PMP capacity/order regular=13 broad=1 count=16
init_coldboot: PMP configure failed (error -2)
```

### 7.1 前回からの変化

256-byte領域のorder=8は4 KiBのorder=12へ変わり、表現不能という拒否は発生していない。
KSB-058の対象箇所は改善した。ただしPMP全体の設定、readback、SM admissionまで成功したわけではない。
停止位置は、PMPのハードウェアentryをプログラムする前のslot計画検査である。

### 7.2 なぜ容量不足になるか

| 用途 | 必要なentry数 |
| --- | --- |
| root domainの通常領域 | 13 |
| 全アドレスのS/U fallback | 1（最終slot 15） |
| 現行Keystoneの最低必要数 | 3 |
| 合計 | 17。実機は16個なので一つ不足 |

根拠はopensbi/include/sbi/k3_keystone_boot_slots.hのK3_BOOT_MIN_KEYSTONE=3と、
keystone/sm/src/pmp.cのk3_pmp_boot_partition_admit()の最低3個という検査である。
実機に残るのは2個。headerの数値だけを2へ変えてもSM側の契約と一致せず、解決にはならない。
現在の拒否は検査の故障ではなく、実機のroot領域数が現行の割当条件を満たさないためである。

### 7.3 次に進める調査

1. 今回の14個のdomain領域を固定した証拠として保存し、必要な保護と優先順位を確認する。
2. domainのメタデータを残したまま、実ハードウェアPMPへ変換したときに完全に冗長となるentryがあるか調べる。
3. 最初の候補はFirmware RXの0x100000000／order=18と、その包含領域の同base／order=20である。
   このログでは両方ともlegacy PMPへ変換した値がpmp=0で、Lはない。
   ただしdomain上のM権限は異なるため、単純にdomain登録そのものを消す案にはしない。
4. ハードウェア上の同値化を行う場合は、first-matchの優先順位、S/U権限、M-modeの扱い、L、
   Smepmpの有無、間にある他entry、readbackとSMへ渡すmaskの整合を確認する。
5. 特にRPMI共有領域とENF_PERMISSIONS付きのRCPU予約領域の包含関係を、
   「両方S/U禁止」という理由だけで整理しない。後者はM-modeも禁止するロック付きentryであり、保護の意味が異なる。
6. 同値性を説明できた範囲に限って割当を修正し、クロスビルド、可能なら対象条件を再現する実ゲスト、
   最終的には同じ実機RAM起動で確認する。検査を弱めて起動だけ通す変更は行わない。

この第7章は初回再試験時点の記録である。その後の容量問題への修正候補は第8章に示す。
getvarや追加continueで解決する停止ではないため、現在のログを保存し、容量割当の検討へ進む。


## 8. KSB-059／060／061／062の修正候補とEnclave数の制約

### 8.1 16個という上限と、実機ログの割当要求

今回の実機は16個のPMP entryを検出した。物理CSRの数はハードウェアで決まり、
OpenSBIのconfigurationや配列上限を32へ変えても実機のentryは増えない。
ソフトウェアで変更できるのは、その16個の割当、保護領域の配置・表現、管理方法である。
QEMUのモデルを改造してentry数を増やすことと、実機の変更は区別する。

容量拒否は書込み前の計画段階なので、次は「書込み済み14個」ではなく割当要求の内訳である。

| 用途 | 対象・性質 | 要求数 |
| --- | --- | --- |
| Firmware | 0x100000000からのRXと包含する全体領域。S/U禁止、Lなし | 2 |
| ESOS／RT24 | RCPU0 runtimeの2分割、RCPU1 runtime、RCPU用DTB。M/S/Uを禁止するL付き保護 | 4 |
| RPMI | 0xcac90000のdoorbellページ、0x100800000の共有メモリー | 2 |
| 割込み | 0xf1800000のAPLIC、0xf1000000のM-mode IMSIC | 2 |
| UART | 0xd4017000のページ。S/UにもR/Wを許可 | 1 |
| K3レジスター保存領域 | 0xd4282000のページ | 1 |
| 追加MMIO | 0xf1810000–0xf181ffff。今回の登録用途は継続確認中 | 1 |
| fallback | 全アドレスのS/U R/W/X許可。最終entry | 1 |
| 合計 | | 14 |

OpenSBIコード自身の保護だけで14個を使うわけではない。販売元のESOS、通信、割込み等も含む。
用途未確定のMMIOを、未使用と推測して削除しない。

### 8.2 Firmware用PMPを共有できる条件

domainのRX／RWメタデータはそのまま残し、実ハードウェアのPMPへの割当だけを共有する。
次の全条件を満たす場合に限る。

- RXと包含領域がdomain配列で隣接し、同じscratch->fw_startから始まる。
- RX flagsはM-readable＋M-executableのみ、包含領域はM-readable＋M-writableのみ。
  MMIO、S/U許可、ENF_PERMISSIONSを含まない。
- RXの長さはscratch->fw_rw_offsetと一致し、包含領域はscratch->fw_size全体を含む。
- RXより包含領域のorderが大きく、表現不能や不正なorderは共有前にも拒否する。
- activeなSmepmp policyはない。MML／MMWP／RLBが有効なら拒否する。

legacy PMPでは両者のS/U権限はともにR/W/Xなし、Lもなしである。
小さいRXをハードウェアへ別途置かなくても、次に隣接する包含entryが同じS/U禁止を適用する。
間に他entryがあるケースは対象外なので、別の高優先ルールを露出させない。
外側の範囲も、他のroot entryの順序も変えない。

この説明はlegacy PMPのS/U保護と、ロックされていない信頼済みM-modeという契約についてである。
M-modeの内部アクセスが旧RX境界をまたぐ場合の部分一致faultまで同一とは主張しない。
PMPによるM-modeのRX／RW分離強制が必要な構成は対象外であり、Smepmp用の合成もしない。

### 8.3 同じ配置を計画・書込み・検証・admissionに使う

opensbi/lib/sbi/sbi_hart.cでdomainからcanonicalな配置を一度構築し、
その配置をプログラムと全CSR readbackで共有する。保持した全entryに加え、
空きslotがOFFであること、fallbackの位置・権限・物理アドレス範囲も検査する。
RXを包含するentry自体の実readbackで、小さいRX範囲を覆うS/U禁止も検証する。

後段のadmissionでも同じdomain由来の配置を再構築して全CSRを照合する。
その結果から得られた正規のroot-owned lock maskだけを、専用のpreflight経路へ渡す。
既存の汎用k3_a1_preflight_local()はLを許可しないままである。
未知のL、free slotのL、fallbackのL、不一致、3個未満の空きは引き続き拒否する。
SM自身の最低3個という契約は変更していない。

今回のdomain構成から期待される割当は次のとおり。これは修正後の実測値ではない。

| 用途 | PMP index | mask |
| --- | --- | --- |
| OpenSBIの通常保護 | 0–11 | 0x0fff |
| Keystone用の空き | 12–14 | 0x7000 |
| fallback（OpenSBI所有） | 15 | 0x8000 |
| OpenSBI所有の合計 | 0–11と15 | 0x8fff |

root domain情報は14領域のまま、実PMPは13個となる。4個のRCPU保護のLも維持する。

### 8.4 3個は固定上限ではなく最小条件。Enclaveの能力は別途数える

UTMはUntrusted Memory、Linux側とEnclaveが引数・結果・ocall等を受け渡す非信頼の共有領域。
EPMはEnclave Private Memory、Enclaveのコードや秘密データを置く保護領域である。
EnclaveはUTMの内容を検証して使い、EPMの秘密をそのままUTMへ出さない。


今回の実装は「Keystoneを3個に制限」しない。OpenSBIが使わない残りをすべてKeystoneへ渡す。
ただし今回の実機構成では整理後に3個しか残らないため、次の制約がある。

K3版ではSM本体がOpenSBI image内にあり、その保護はOpenSBIが担当する。
修正前のKeystone側ではOS-wide regionとUTMが末尾slotを切替利用していた。
しかしK3の後段root fallbackの下では、その共有はOS-wide denyを失わせる（KSB-062）。
今回の候補ではOS-wide regionを末尾の1個、UTMをそれより前の独立したentryへ分ける。
従って残り3個で収まるのは、OS用1＋NAPOT UTM用1＋NAPOT EPM用1という最小予算である。
先に共有を前提に示した「動的領域に二つ」「2 Enclave分」という計算は、安全なK3構成の能力としては撤回する。

| 単一Enclaveの構成 | OS切替用 | UTM（NAPOTの例） | EPM | backing | 合計 |
| --- | --- | --- | --- | --- | --- |
| NAPOT EPM、backingなし | 1 | 1 | 1 | 0 | 3 |
| TOR EPM、backingなし | 1 | 1 | 2 | 0 | 4。3個では不足 |
| NAPOT EPM＋NAPOT backing | 1 | 1 | 1 | 1 | 4。3個では不足 |
| TOR EPM＋NAPOT backing | 1 | 1 | 2 | 1 | 5。3個では不足 |
| TOR EPM＋TOR backing | 1 | 1 | 2 | 2 | 6。3個では不足 |

NAPOTは2のべき乗サイズとそのサイズでの整列が必要で、TORは一般の非ゼロbase領域で2個必要。
UTMもTORならその分さらに1個必要になる。
複数Enclaveは各EnclaveのEPM／UTM等の予約が必要なので、3個で2 Enclaveは収まらない。
この予算は動作保証ではなく、実際の起動・アプリ・SMP等の条件も別に満たす必要がある。
SMP／HSM／IPI同期、Enclave切替、アプリの他の条件は別途検証する。

現在のallocatorはEnclaveを保持している間、EPM等のslotも予約する。
停止中だから自動的にslotが他Enclaveへ解放される設計ではない。
複数Enclave・multimemの目標能力がこの予算を超える場合は、追加の安全な整理、
領域配置、または割当方式の設計変更が必要である。最低数の検査を外すだけでは能力は増えない。

### 8.5 共有slotの解放処理（KSB-061）とOS／UTMの分離（KSB-062）

上記の資源計算を確認中に、UTM等の一つのregionを解放すると、同じ末尾slotを使う
OS-wide region等が残っていてもreg_bitmapから予約が消える問題を確認した。
このままではCREATE／DESTROY反復後のANY割当がOS用slotを再利用し得る。
解放の参照確認は、一般の共有regionの予約を維持するため修正する。
K3については次のKSB-062対応でOSとUTMのslot自体を分離する。

解放時には同じpmp_lockを保持して残存regionを調べ、slotを参照するregionが
なくなった場合だけ予約bitを落とすよう修正する。TORの二つのslotについても同様に扱う。
この解放処理の修正自体はCSRを書き換えず、既存の所有mask・entry数も増減しない。

KSB-062では、context_switch_to_enclave()がOS-wide denyを設定した後、同じslotへUTM許可を書くと、
その後ろのOpenSBI fallbackが通常OSメモリーまで許可してしまう。
K3のCREATEではUTMをPMP_PRI_ANYで独立に予約し、OS-wide denyを保持したままUTMを許可する。
通常OSメモリーはOS-wide denyに一致し、後段fallbackへ抜けない。
独立したUTM entryを確保できない場合は、既存の失敗経路でEPM等を解放してCREATEを拒否する。
非K3の従来のfallbackを持たない構成のUTM割当方針は変更しない。
rootが明示的に許可するMMIOの扱いは別の既存方針であり、今回のOSメモリーfallback問題と区別する。

### 8.6 検証範囲と次の実機試験

SMの実ソース一式を再コンパイルし、SMあり・なしのOpenSBIをクロスリンクして確認する。
ここでは対応する実QEMU実行環境・kernel/rootfsがなく、integrationは未実行である。
模擬SBI／PMP／CSR試験は追加しない。ビルド成功を実機PMP成功と扱わない。

実機RAM起動では次のような診断を確認する。

```text
[K3-PMP] share firmware deny base=0x100000000 order=18 via order=20
[K3-PMP] verified shared firmware deny slot=7 base=0x100000000
K3 PMP: OpenSBI entries=12 fallback=15 Keystone free=3 mask=0x7000
[K3-PMP] root-config PASS hart=0 root=13 Keystone-free=3
```

後段でも同じ配置のreadbackを行うため、共有診断等が複数回出る場合がある。
実際のU-Bootバナー／UARTプロンプトへ進むことを確認してから、別Linux DTとの整合確認へ進む。
第6.2節のmailbox0〜3のM-mode所有条件は今回の修正でも変わらない。

Enclave試験はU-Boot到達後の別段階であり、少なくとも以下を実ゲスト／実機で確認する。

- 必要数と形状に応じたCREATE／RUN／STOP／RESUME／DESTROY。
- entry数を使い切ったCREATEの安全な失敗とrollback。
- 必要なentryを用意した構成で二つのNAPOT Enclaveを保持し、一方をDESTROYして再CREATEする場合の予約保持。
- 残り3個では2 EnclaveのCREATEが安全に失敗すること。ホスト復帰後の予約が破損しないこと。
- EnclaveからEPM／UTM／許可した領域の外の通常OSメモリーへアクセスし、拒否されること。
- TORとbackingを含む構成の不足判定。無理に許可せず、3個で不可能な構成を区別する。
- 複数Hartでの同期と切替、他Enclaveの保護、既存root-owned entryとLの不変性。

これらの実行結果はまだない。3個で一般的なKeystone機能や複数Enclaveが動くとは記載しない。

### 8.7 開発PCでの再生成と転送

依存とoriginal内の販売元ファイルは既存手順どおり用意する。
開発PCで最新ソースを取得し、publicリポジトリのルートから実行する。

```bash
set -euo pipefail
mkdir -p work/jupiter2-pmp-capacity-retest
KEYSTONE_SM_TRACE=0 make opensbi JOBS=4 \
  2>&1 | tee work/jupiter2-pmp-capacity-retest/build.log

python3 scripts/build-jupiter2-ram-boot-image.py \
  --fsbl hardware/jupiter2/vendor/FSBL.bin \
  --uboot-itb hardware/jupiter2/vendor/u-boot.itb \
  --esos-itb hardware/jupiter2/vendor/esos.itb \
  --opensbi-bin .build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin \
  --configuration conf_11 \
  --esos-configuration conf_dual \
  --board k3-pico-itx \
  --variant keystone \
  --opensbi-reserve-bytes 0x00100000 \
  --max-download-bytes 0x20000000 \
  --output work/jupiter2-ram-boot/keystone-pmp-capacity-retest
```

1 MiBは既存の候補値を使用する例で、再ビルドの領域と配置を確認する。転送上限512 MiBは実測値。
出力先が既存なら別名を指定する。NOR更新は行わず、UARTログを保存してFDLへ入り、PCで実行する。

```bash
sudo fastboot devices
sudo fastboot stage work/jupiter2-ram-boot/keystone-pmp-capacity-retest/images/FSBL.bin
sudo fastboot continue
```

DDR初期化とUSB再認識を確認してから、統合FITを転送する。

```bash
sudo fastboot -s HW4MPK3321280144 stage \
  work/jupiter2-ram-boot/keystone-pmp-capacity-retest/images/ram-boot-keystone.itb
sudo fastboot -s HW4MPK3321280144 continue
```

UARTでPMP診断と次段への進行を確認する。U-Bootがfastbootへ入った場合だけ、
PCのgetvar versionへの応答を確認し、追加continueでUARTプロンプトへ進む。
PMP途中の拒否なら追加continueでは解決しない。最初の試験はU-Boot到達までとする。

### 8.8 今回のビルド記録（2026-11-21）

SMの30 translation unitsを実クロスコンパイルし、OpenSBIとリンクした。
RISC-V ELF、SMシンボル、enclave mtvecの4-byte整列を確認した。
SMなしのk3_defconfigもクロスリンク成功。実機のPMP／OS保護／複数Enclaveの試験は未実行。

| 構成 | BINサイズ | BIN SHA-256 |
| --- | --- | --- |
| K3 Keystone audit（SMあり・multimemコードを含む） | 270248 bytes | 2ae3fa9c2fc4c28446955f864ea4b76c4980e70cb005c8a15ac82504127436ed |
| k3_defconfig（SMなし） | 269600 bytes | 941f32c66ebf89e2fb6a3934ebee8633735a0155022ce960d12eb61c76bd3093 |

ビルドでmultimemコードを含めたことは、実機のPMP予算でmultimemを使用できるという意味ではない。

## 9. RAM起動後のUFS通信失敗（KSB-063）

2026-11-21のユーザー実機ログで、U-Bootのscsi scanが次の経過となった。

```text
ufs_start: Failed setting power mode, err = -1
[RX, TX]: gear=[3, 3], lane[2, 2], pwr[FAST MODE, FAST MODE], rate = 2
Error in status:00000004
__ufshcd_query_descriptor: opcode 0x01 for idn 2 failed ... err = -1
Timedout waiting for UTP response
... err = -110
```

[販売元UFSドライバー](https://github.com/spacemit-com/uboot-2022.10/blob/k3-br-v1.0.y/drivers/ufs/ufs.c)と
[ヘッダー](https://github.com/spacemit-com/uboot-2022.10/blob/k3-br-v1.0.y/drivers/ufs/ufs.h)では、
表示したstatusの0x4はUIC_ERRORである。リンク通信の失敗で、UFS descriptor取得も完了していない。
これだけでPMPに原因を帰属したり、UFS故障と判断したりしない。

まずscsi scanを繰り返さず、UARTへ応答が戻るか確認する。Ctrl+Cで戻れる場合は停止してログ保存する。
プロンプトが戻ったら、UARTから他媒体を確認する。

```text
nvme scan
nvme info
mmc list
```

必要なLinuxがNVMe等にある場合は、その媒体のパーティションと起動ファイルを確認する。
UFS上のファイルが必要な場合は、使用中のRAM起動chainを次の条件で比較する。

1. 同じFSBL／U-Boot／ボードDTB／ESOSから、販売元OpenSBIを含む比較用統合FITを生成する。
2. 両方とも完全電源断から始め、同じ接続・同じ手順でRAM起動する。単なるwarm resetとの差も記録する。
3. 販売元版と開発版でそれぞれscsi scanを一度行い、全UARTログと入力・出力のSHA-256を保存する。
4. 両方失敗ならRAM起動経路・初期化条件・互換性を、販売元版だけ成功なら開発版の差分を調べる。

販売元U-Boot単体をM-modeで起動した試験と、OpenSBI経由の試験は、実行モードやESOS起動等が異なる。
純正U-Boot単体の成功だけで開発版OpenSBIが原因と断定しない。
PMP保護を解除する、NORを書き換える、UFSをeraseする方法はこの切り分けでは行わない。
その後、ユーザーから販売元OpenSBI入り統合FIT、および元の販売元FSBL＋u-boot.itbでも
同様のdescriptor失敗が報告された。各試行の入力SHAと全起動ログは引き続き確認が必要だが、
現在の証拠からKeystone固有の原因と扱わない。UFSからのLinux読み出しは未確認である。
次は[修正版FSBLとESOSを含む参照実装の開発手順](jupiter2-reference-ram-boot-development.md)と
[実機テスト手順](jupiter2-reference-ram-boot-tests.md)で、販売元OpenSBIを使うRAM起動を先に確立する。
