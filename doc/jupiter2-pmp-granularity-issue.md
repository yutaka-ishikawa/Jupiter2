# Jupiter2 RAM起動：RPMI領域とPMP粒度の不一致（KSB-058）

登録日：2026-11-21。状態：実機で起動停止を確認、登録元と修正方法を調査中。

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
