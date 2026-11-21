# Jupiter2のX100/A100混在PMP構成への対応計画

本書は確認済み計画とその実装状況を記録する。2026年11月21日に修正候補を実装した。修正版ファームウェアの実機実行は未実施。
関連する問題は[KSB-071](keystone-bug-report.md#ksb-071-x100a100のpmp数混在を16個固定の移植処理が拒否)として管理する。

## 1. 実機ログで確認できたこと

2026年11月21日に提供されたUART記録 `log.txt` は複数回の起動を含む。
以下は末尾側の、Linux起動とhello失敗が連続している起動からの抜粋である。
過去のPMP容量不足による停止とは区別する。

| Hart | CPU種別 | 検出PMP数 | 今回の状態 |
| --- | --- | ---: | --- |
| 0〜7 | X100 | 16 | root PMP設定と各HartのSM初期化が成功 |
| 8〜15 | A100 | 32 | PMP設定が `-2` を返し、Linux CPU起動に失敗 |

CPU種別は[実機互換性調査](jupiter2-hardware-compatibility.md)と提供DTの定義による。
PMP数は今回のOpenSBIのHart別検出結果による。

```text
[K3-PMP] root-config PASS hart=7 root=13 Keystone-free=3
[SM/K3] SM initialized (see SM/CRYPTO capabilities; no hardware attestation or DMA proof; see SM/RNG quality)
[K3-PMP] configure-start Hart=8 count=32 log2gran=12 addrbits=38
[K3-PMP] configure-return Hart=8 rc=-2
[    2.638707] CPU8: failed to come online
...
[    9.808982] CPU15: failed to come online
[    9.809968] smp: Brought up 1 node, 8 CPUs
```

`opensbi/lib/sbi/sbi_hart.c` の `k3_root_pmp_layout_build()` は
`count != K3_BOOT_PMP_COUNT` の場合に `SBI_ENOTSUPP` を返す。
`K3_BOOT_PMP_COUNT` は16であり、今回のA100の失敗を直接説明する。
標準のOpenSBIの検出処理ではなく、この移植で追加したKeystone向け処理の不備である。
販売元環境には16 CPU起動の記録があるが、今回と同一バイナリー構成の比較試験とは区別する。

helloはSBI function 2001まで届くが、`sm_is_ready()` が全16 HartのSTARTEDを要求するため拒否される。
`SM not initialized` は複数の受付条件に共通の表示であり、SM初期化自体が未実行という意味には限定されない。
CPU3にtasksetしても全Hartの受付条件は変わらない。

## 2. 最初に実装する方針

**ハードウェアのPMP個数と、Keystoneが利用する共通エントリー数を分離する。**
初期対応では、X100/A100ともエントリー0〜15を共通配置として使用する。
A100の16〜31はKeystoneへ割り当てず、無効状態を検査・維持する。
これはハードウェアのPMP数を16へ変更する操作ではない。

| 範囲 | 共通配置での役割 |
| --- | --- |
| 0〜11 | 現在のroot domainの保護規則 |
| 12〜14 | Keystone用の共通3エントリー |
| 15 | root domainの広域S/U許可規則 |
| 16〜31（A100のみ） | 未使用。全数を読み取り、A=OFFかつL=0を確認 |

この配置は現在のdomainから12個の通常規則を構成できる場合のもの。
規則数が変われば従来どおり容量・順序検査で拒否し、固定表へ無理に押し込めない。
追加エントリーにはTORによる直前PMPADDRへのロックなどもあるため、
「優先順位が低いので無視できる」とは扱わない。

追加範囲に有効規則またはロックがあれば、初期対応では起動を拒否し、Hart、index、理由を記録する。
初期状態の根拠なしに解除・上書きしない。販売元が必要とする追加規則が見つかれば、
所有者と必要性を調べたうえでこの計画を見直す。

全Hartへ同じKeystoneエントリー番号を同期できるため、最初からHart別の動的割当てを導入せずに済む。
A100の追加分を使って同時Enclave数を増やす機能は、この修正の対象外とする。
共通3エントリーによる制約も変わらず、任意のメモリー配置や複数Enclaveの同時実行を保証しない。

## 3. 修正箇所

| 対象 | 予定する修正 |
| --- | --- |
| `opensbi/include/sbi/k3_keystone_boot_slots.h` | 16個の共通割当てと、Hartごとの実装個数16/32を区別。未知の個数は明示的に拒否 |
| `opensbi/lib/sbi/sbi_hart.c` | root構築の16個一致条件を置換。全実装エントリーの事前検査と設定後readbackを実施し、追加範囲を切り捨てない |
| `opensbi/include/sbi/sbi_hart.h` | PMP snapshotを最大32個に対応させ、実装個数と共通割当て数を別フィールドとして表現 |
| `opensbi/include/sbi/k3_a1_csr_preflight.h` | 全32個の状態検査と共通16個の配置検査を分離。未使用追加範囲の不正状態も拒否 |
| `opensbi/include/sbi/k3_pmp_partition_evidence.h` | 16/32混在の証拠を表現。共通配置一致と追加範囲の検証を両方要求 |
| `keystone/sm/src/pmp.c`, `pmp.h` | 共通16個のallocatorと実装個数を混同しない。SMが書ける範囲は引き続き12〜14などの検証済みマスクだけ |
| `keystone/sm/src/ipi.c`, OpenSBI HSM連携 | START、STOP、resumeとPMP同期の全経路で、追加範囲の契約が失われないことを監査・必要箇所を修正 |
| `keystone/sm/src/sm.c`, `sm-sbi-opensbi.c` | 未初期化、partition未準備、同期異常、Hart不足、非STARTEDを識別する診断を追加。受付条件は緩めない |
| ビルド・検証関連 | QEMU向け16個固定設定と実機混在設定を区別し、コンパイル条件の混同を防ぐ |

PMPエントリー集合は32ビット以上の型で表現するか、共通部分の16ビットマスクと追加部分の証拠を明確に分離する。
`1U << 32` の未定義動作、型変換での上位ビット消失、配列上限、CSR番号とRV64のpmpcfg配置を点検する。
一方、`k3_e2_hart_quarantine.h` などの16ビットHart集合は16 CPUを表すため、PMP個数の変更だけを理由に拡張しない。

## 4. 保護上の成立条件

1. 各Hartの実装個数、粒度、アドレス幅、Smepmp状態を検査する。
2. 全Hartで共通0〜15の意味・許可・所有権が一致することを、各Hartのreadbackで確認する。
3. A100の16〜31は、初回設定前と設定後に全数検査する。再起動・resume時にも再検査する。
4. 全Hartの検証とHSM準備が完了するまでCREATEを受け付けない。
5. Enclaveへの出入り、IPI更新、STOP/START、失敗時の隔離で保護の一貫性を維持する。
6. 不一致・readback失敗・同期timeoutは処理を停止し、成功扱いにしない。

A100がSTARTEDになっても、X100との差異がすべて解消したことにはならない。
ISA拡張やCSRの差が後続処理で問題になれば別途記録する。
また、Linuxのidle/suspendでHartが非STARTEDになる場合の受付と同期も実測する。
全CPUが一度起動したという理由だけで、この状態遷移の検証を省略しない。

## 5. 実装と検証の順序

### 段階1：診断と契約の実装

KSB-071に沿って上記の型、snapshot、root配置、追加範囲の検査を修正する。
失敗診断にはHart ID、実装個数、共通個数、拒否理由を含める。
実装後、差分とビルド結果を記録してRAM試験用イメージを生成する。

### 段階2：ビルドとQEMU回帰

```bash
make firmware
make -C verifications guest
make -C verifications kernel-modules
```

対応するK3 QEMU guest内で実行する。

```bash
bash verifications/run-all.sh
```

既存の16 PMP構成で保護、同期、拒否経路が退行していないことを確認する。
同一構成のQEMUだけではX100/A100混在を検証したことにはならない。
混在環境を再現できない場合は実機試験を必須とし、コンパイル成功をguest PASSと記載しない。
SBI/PMP/CSRのモックや本体関数を抜き出した試験は追加しない。
追加する試験スクリプトは `scripts/tests/jupiter2-ram-boot/` に置き、目的・実行場所・検証限界をコメントに書く。

### 段階3：実機でRAM起動し、16 CPUを確認

[RAM起動ガイド](jupiter2-ram-boot-guide.md)と
[SM起動・アプリ試験手順](jupiter2-keystone-app-test.md)に従い、修正版の統合FITをRAMへ転送する。
修正版試験のためにNORを書き換えない。元のイメージとログを保持する。

UARTで全HartのPMP検証成功とSM初期化を確認した後、Linux上で確認する。

```bash
uname -r
lscpu
cat /sys/devices/system/cpu/possible
cat /sys/devices/system/cpu/present
cat /sys/devices/system/cpu/online
cat /sys/devices/system/cpu/offline
```

期待値はonlineが `0-15`、offlineが空。
A100が起動しない、追加PMPの検査が失敗する、同期異常が出る場合はhelloへ進まない。

### 段階4：helloとCPU種別ごとの確認

```bash
sudo modprobe keystone_driver
ls -l /dev/keystone_enclave
sudo /opt/keystone/$(uname -r)/hello.ke
echo "hello終了コード=$?"
sudo /opt/keystone/$(uname -r)/hello-native.ke
echo "hello-native終了コード=$?"
```

最初の失敗で止め、続くアプリを実行せずUARTとdmesgを保存する。
両方が成功した後、X100とA100にそれぞれ固定して順番に確認する。

```bash
sudo taskset -c 3 /opt/keystone/$(uname -r)/hello.ke
echo "X100終了コード=$?"
sudo taskset -c 8 /opt/keystone/$(uname -r)/hello.ke
echo "A100終了コード=$?"
```

tasksetは修正方法ではなく、修正後のCPU種別ごとの試験に使う。
成功条件は終了コード0、期待するアプリ結果、PMP/readback/同期異常なし。
その後に反復CREATE/RUN/DESTROY、CPU移動、idle、検証環境でのhotplugと失敗経路を確認する。
通常helloの成功だけで隔離・attestation・DMA保護の証明とはしない。

### 段階5：結果記録と復帰

ソースcommit、FSBL/FIT/kernel/DTBのSHA-256、Hart別の実装個数と検証結果、UART全文、dmesg、
各アプリ終了コードを保存する。公開ログには鍵・seedなどを含めない。
不具合時は試験を止め、電源再投入でRAM上の候補を破棄し、既知の正常な起動構成へ戻す。
保存済みLinux起動ファイルや起動設定を変更した場合は別途そのバックアップから戻す。

## 6. 今回の確認範囲

本書作成時点では、UART記録とソースの照合により直接の拒否箇所を確認した。
32個側の追加16エントリーの実際の初期内容は未採取であり、無効であるとはまだ断定しない。
修正実装とSM/OpenSBIのクロスビルド・リンクを実施。QEMUの専用S-mode guestでは全16 Hart起動を確認。Linux/SDKの統合試験と修正後の実機helloは未実施。
追加したQEMU混在プロファイルと残る不足は[QEMUと実機試験の差分](jupiter2-qemu-hardware-test-gaps.md)を参照。


## 7. 修正候補の実装結果

- 実装個数16/32と共通割当て数16を分離。未知の個数、追加範囲の有効規則・ロックは拒否する。
- snapshotは最大32個を保持。証拠のactive/locked集合は32ビット化し、所有マスクは共通16個に限定する。
- root設定前・設定後、local preflight、SMのPMP初期化・設定・解除の前後、IPI ACK前に追加範囲を検査する。
- warm start/resumeは既存のroot readbackとadmission経路を通るため、同じ追加範囲検査を受ける。
  HSM開始の禁止条件や同期異常時の停止は緩めていない。
- SM受付失敗の理由を個別に表示する。全16 Hart STARTED条件は維持する。
- SMビルドの既定値からQEMU16専用defineを外し、明示的なqemu16診断ビルドだけで有効にする。
- QEMUへ任意選択の混在PMPプロファイルを追加。PMP数16/32と粒度4096バイトを再現するが、CPUの全仕様や実機domainを再現したものではない。

実機で期待するUART表示例（数値は現在のroot規則の場合）：

```text
[K3-PMP] root-config PASS hart=0 implemented=16 common=16 extra-off=0 root=13 Keystone-free=3
[K3-PMP] root-config PASS hart=8 implemented=32 common=16 extra-off=16 root=13 Keystone-free=3
```

追加範囲の状態が契約と違えば `extra rejected hart=... index=...` で停止する。
その場合に個数制限やロック検査を外して続行してはいけない。
SMがなお拒否する場合は `admission denied:` の具体的な理由を採取する。

### ビルド確認と未実施の試験

- 既定mixedと診断qemu16のSMは、それぞれ全30 translation unitsをRISC-V向けにコンパイル・relocatable link成功。
- mixedのSMをOpenSBIへリンクし、fw_dynamic.elf/bin生成とEnclave mtvecの4バイト整列検査に成功。
- `make -C verifications guest` は必要なSDKのlibkeystone-eapp.aがないため停止。
- `make -C verifications kernel-modules` は対応kernelのModule.symversがないため停止。
- guest内run-all、修正後の実機16 CPU起動、hello二種、idle/hotplug/負の経路は未検証。

実機では従来と同じ参照RAMブート作成スクリプトへ、今回ビルドしたOpenSBIのraw binを渡す。
販売元版vendor-releaseと区別した新しい出力ディレクトリを使う。
[SM起動・アプリ試験](jupiter2-keystone-app-test.md)のビルドとRAM起動手順に従い、
Linux側のonlineが0-15になってからhelloへ進む。


### QEMU追加試験の実測結果

変更したQEMU本体をビルドし、以下の両構成で確認した。

| 試験 | uniform16 | mixed |
| --- | --- | --- |
| QMPでrealize後の全16 CPUの個数・粒度を照合 | PASS：全16個、16バイト | PASS：前半16個/後半32個、全4 KiB |
| 実OpenSBI＋SMのHart別root PMP readback | 16 Hartで成功 | 16 Hartで成功、追加16個OFFを検証 |
| 実SBI HSMを使ったS-mode到達 | 全16 Hartで成功 | 全16 Hartで成功 |

後者は専用の小さなS-mode guestを実行した起動試験であり、Linux guest内のrun-allではない。
QEMUではrootが7個、Keystone空き9個、PMPADDR幅54ビットだった。
実機のroot13個・空き3個・PMPADDR幅38ビットは、この試験だけでは検証していない。

```bash
# 開発PC、publicルート。新しい出力先を指定する。
python3 scripts/tests/jupiter2-ram-boot/check_qemu_pmp_profile.py \
  --qemu install/keystone/bin/qemu-system-riscv64
python3 scripts/tests/jupiter2-ram-boot/run_pmp_hsm_smoke.py \
  --qemu install/keystone/bin/qemu-system-riscv64 \
  --firmware .build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin \
  --output work/ksb071-pmp-hsm-smoke
```

SM/OpenSBIの試験用raw bin：SHA-256
`14d45be6777a63cc650571b3fb7d410c628fde297a28eed35266d6e62e983441`。
同じソースでもビルド条件やツールが違えばhashは変わるため、利用者の成果物も別途記録する。
既存の実ツールを使うホスト梱包試験43件も成功。
EnclaveのCREATE/RUN、IPI同期更新、Linux idle/hotplug、追加範囲を不正状態にする負の試験は未実施。
