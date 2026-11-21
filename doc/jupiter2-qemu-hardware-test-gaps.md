# Jupiter2実機試験から判明したQEMUの不足と追加検証

更新：2026年11月21日。今回の実機試験で分かった条件を、QEMUモデルの変更と試験条件の追加に分けて整理する。
QEMUの現在のモデルは `virt` を基にした部分モデルであり、実機の起動チェーン全体を再現していない。
この制約は[実機互換性調査](jupiter2-hardware-compatibility.md)でも記録していたが、
Keystoneの検証に必要な実機条件を回帰試験へ取り込む作業が不足していた（KSB-072）。

## 1. 今回の問題をQEMUで検出できなかった理由

従来の `scripts/run-k3.sh` は全Hartへ同じCPU設定を指定していた。

```text
rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16
```

ここで `pmp-granularity=16` は16 **バイト**であり、実機の4 KiBとは異なる。
OpenSBIログの `log2gran=12` は4096バイトを意味する。

実機はX100が16 PMP、A100が32 PMPだが、QEMUの試験では全Hartが16 PMPだった。
そのため「個数が16以外なら拒否」という移植コードの不備は試験対象にならなかった。
QEMUが32 PMPを扱えないという意味ではない。指定した試験構成に32個のHartがなかった。
また、QEMUの簡略なdomain/予約メモリー構成は実機のroot PMP規則数やロック配置とも一致しない。
QEMUのPASSは、その入力構成に対する結果であり、実機構成への適合証明ではなかった。

## 2. 不足一覧と優先順位

| 優先度 | 実機で判明した条件 | 必要な対応 | 今回の対応状況 |
| --- | --- | --- | --- |
| P0 | X100=16、A100=32 PMP（KSB-071） | Hart別のPMP数を再現し、混在したまま全Hart起動・Enclave同期を実行 | `mixed-pmp` オプションを追加 |
| P0 | PMP粒度4 KiB。256バイトのRPMI doorbell領域が表現できない（KSB-058） | 混在プロファイルを4096バイト粒度にし、小領域の拒否・ページ単位の保護を検証 | 混在プロファイルの粒度を修正。実機domain fixtureは未実装 |
| P0 | rootが13エントリー、Keystone空き3個。RCPU保護にLビットあり（KSB-059/060） | 実機相当のdomain規則・順序・ロックを入力する試験を追加 | 現行QEMUのdomainを実機同等にはしていない。未実装 |
| P0 | OS/UTMのslot共用では実機fallbackと競合（KSB-061/062） | 少数slot、広域fallback、共有regionの解放・再割当てを本物のSMで回帰試験 | KSB-073でUTM復帰も修正し、混在Linux guestでhello二種成功。slot不足・共有解放・実機予約条件の負の試験は未実施 |
| P1 | 実機のPMPADDR実装幅38ビット | WARL上位ビットと範囲境界の実測に合わせたCSRモデル・試験を追加 | 今回の混在実測は54ビット。実機の38ビットへ変更していない |
| P1 | PMP16〜31の初期状態が未採取 | 追加範囲のOFF/ロック/有効規則、特にPMP16のTORロックによるPMPADDR15への影響を検証 | SM/OpenSBIに全数検査を実装。負の条件を作るQEMU診断機構は未実装 |
| P1 | Linux直接mailboxとM-onlyページの所有権競合（KSB-070） | M-onlyページを含む実機相当DT入力、直接アクセスの拒否、SBI経由利用を検証 | 別名Linux DTBの生成・検査を実装済み。QEMUに同じmailbox機器モデルはない |
| P1 | ESOSとAP側RPMI queue/slot/server設定の不一致で起動停止（KSB-069） | 生きたサーバーとの通信、queue不一致や応答timeoutを試験。DT静的検査だけでは不足 | パッケージ作成時の実DT整合検査は実装済み。QEMUの実機ESOS/RCPUモデルは未実装 |
| P1 | 異なるCPUのISA/CSR、PMP同期IPI、Sstc/M-timer、HSM状態遷移 | X100/A100差のうち仕様と実測のあるものを追加し、idle/STOP/START/resumeを検証 | 今回はPMP数と粒度のみ。A100のISA差や全CSRを再現してはいない |
| P2 | FDL/SPL/統合FIT/ESOS entry・handshakeの不整合（KSB-065〜068） | 起動チェーンの入力検査と実機UART試験。全SoC模倣は別開発 | 参照FSBL・FIT作成処理を修正済み。QEMUでFSBL/ESOSを実行していない |
| P2 | UFS初期化失敗と、整合修正後の正常起動（KSB-063） | 実機UFS/RCPU/clock/power連携での確認 | QEMUのvirtio diskはUFSの代替試験にならない。実機試験を継続 |
| P2 | NOR OpenSBI区画384 KiB | 最終ITBの容量検査を配布工程で必須化 | 既存の容量検査・パッケージ作成処理で扱う。通常QEMU起動では検出できない |

mailbox/RPMI/ESOS/UFSの問題をすべて「QEMUのバグ」とはしない。
モデルに存在しない機能の試験が抜けていた、という検証範囲の不足である。
実機のDMA、PMA、キャッシュ、セキュア起動、乱数・attestation品質も、このPMP修正で再現できたとは扱わない。
Linuxログのremoteproc資源処理エラーなど、因果が未確定の表示は別途調べ、PMP起動失敗と一括しない。

## 3. 今回追加したQEMUプロファイル

既存の一律16個の構成を既定として残し、比較用の混在プロファイルを追加した。

| プロファイル | Hart0〜7 | Hart8〜15 | PMP粒度 |
| --- | --- | --- | --- |
| `uniform16`（既定） | 16個 | 16個 | 既存設定の16バイト |
| `mixed` | 16個 | 32個 | 全Hartで4096バイト |

CPUをrealizeする前にHart別の `num-pmp-regions` と `pmp-granularity` を設定し、
QEMU本体のPMP CSR実装を使用する。SBI結果やSM関数をモックには置き換えない。
CPUモデルは両側ともrva23s64のままであり、X100/A100という名前や実装IDを付けて実機再現と見せる変更はしない。

```bash
# 開発PC、publicリポジトリのルート。変更したQEMUもビルドする。
make qemu
make firmware

# 同じカーネル・rootfs・修正版firmwareで比較する。
# install/keystoneへ配置する方法は既存のビルド・配置手順を参照する。
FW=.build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin
bash scripts/run-k3.sh --image keystone --bios "$FW" --pmp-profile uniform16
bash scripts/run-k3.sh --image keystone --bios "$FW" --pmp-profile mixed
```

QEMU直接起動時の指定は `-M jupiter2,mixed-pmp=on`。
未修正のQEMUにはこのpropertyがないため、更新前のバイナリーを使わない。
SMのビルド側 `KEYSTONE_PMP_PROFILE=mixed` は16/32個を許可する既定値。
`KEYSTONE_PMP_PROFILE=qemu16` はSMの証拠検査を16個だけに限定する診断ビルドで、
混在試験・実機試験には使用しない。QEMU起動オプションとSMビルド設定を混同しない。

## 4. 追加すべき回帰試験

1. 同じ修正版firmwareを一律16個と混在構成で起動し、全16 CPUとhello二種を確認する。
2. 混在構成のHart3とHart8からそれぞれCREATE/RUN/DESTROYを行い、全対象HartのPMP反映・readback・ACKを確認する。
3. 実機相当のdomain fixtureを追加し、予約13個、空き3個、ロック付き規則、広域fallbackで実行する。
4. 追加PMP範囲の不正初期状態を実際のCSRへ設定する専用診断経路を用意し、S-modeやCREATEへ進まないことを確認する。
5. 小領域、slot不足、共有slot解放、UTM/EPM配置不成立、同期timeout、idle、hotplugの拒否・復帰経路を実guestで検証する。
6. 実機専用のFDL/ESOS/RPMI/UFSの試験結果を別に記録し、QEMU試験の結果と混ぜない。

新しい試験スクリプトは試験ディレクトリに置き、目的・対象プロファイル・実行場所をコメントに記載する。
上記のうち機構未実装の項目は、手順を記載しただけで実施済みにはしない。
実施状況は[混在PMP修正計画・結果](jupiter2-heterogeneous-pmp-plan.md)へ記録する。


## 5. QEMU設定の検査スクリプト

```bash
python3 scripts/tests/jupiter2-ram-boot/check_qemu_pmp_profile.py \
  --qemu install/keystone/bin/qemu-system-riscv64
```

実QEMUを停止状態で起動し、QMPから全CPUの実設定を読み取る。
両プロファイルのPMP個数と粒度を確認するもので、OpenSBI/SMの実行試験を置き換えない。
スクリプト冒頭にも目的と検証限界を記載している。


## 6. 今回の実測結果

QEMU本体のビルドと両プロファイルのQMP設定検査に成功した。
さらに `run_pmp_hsm_smoke.py` で実OpenSBI/SMを起動し、全16 Hartのroot readbackとSBI HSM経由のS-mode到達が両構成で成功した。
生成物・UARTログは指定したoutput配下へ保存する。

一方、今回のQEMUのroot使用数は7個、空き9個、PMPADDR幅54ビットだった。
実機のroot13個・空き3個・38ビットを再現する試験は追加が必要である。
専用S-mode guestの成功をLinux/SDKのrun-allやEnclave隔離のPASSとはしない。


## 7. 実Linux/SDK/Eyrie/sampleまでの回帰試験を追加

KSB-073では実機と同じ提供sampleを実Linux guestで実行した。
修正前はQEMUでもrunner+0x529cのload access fault・終了139を再現できた。
修正後は両PMP構成×Linux CPU3/8×hello/nativeの計8回すべて正常終了した。
[入力hash・修正箇所・UARTと比較結果](jupiter2-utm-host-access-issue.md#6-実qemuでのsample回帰試験結果)を参照する。
これは全sample suiteや実機domain fixture等の未実装項目が解消したことを意味しない。
