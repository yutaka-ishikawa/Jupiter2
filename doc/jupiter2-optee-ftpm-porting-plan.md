# Milk-V Jupiter2へのOP-TEE・fTPM TA移植計画

対象はSpacemiT K3（RV64）搭載のMilk-V Jupiter2 SBC。調査基準はJupiter2の
`main`（`19cd12988`）。本書は実装・試験の計画であり、ビルド、QEMU起動、
実機動作の結果は未取得。

## 目標と進め方

移植のベースは、**Jupiter2リポジトリの現行Keystone構成一式**とする。
改造OpenSBI＋Keystone SM、FSBL/U-Bootからの既存RAM起動・統合FIT生成手順、
`linux-k3/` とDTB、K3 QEMU、rootfs、Keystoneの検証環境にOP-TEEとfTPM TAを追加する。
最初の実機到達点は、同一ファームウェア・Linuxの起動中にKeystone Enclaveと
fTPM TAが動作し、LinuxからTPM 2.0コマンドを実行でき、試験用NVデータが
再起動・電源再投入後にも残ること。Measured Boot・IMAと製品向けの鍵管理は後続とする。

呼び出し経路は、`tpm2-tools → /dev/tpmrmN → tpm_ftpm_tee → Linux OP-TEE
（SBI MPXY）→ OpenSBIのOP-TEEドメイン → fTPM TA`。
TAの読み込みやストレージのRPCには、選択した構成に応じて `tee-supplicant` が関与する。

| 項目 | 現状と採用方針 |
| --- | --- |
| 起動 | [現行のKeystone RAM起動手順](jupiter2-ram-boot-procedure.md)と[統合FIT生成スクリプト](../scripts/build-jupiter2-ram-boot-image.py)を拡張する。 |
| OpenSBI | [改造OpenSBIのK3 Keystone構成](../opensbi/platform/generic/configs/k3_keystone_audit_defconfig)と[既存MPXY dispatcher](../opensbi/lib/utils/mpxy/fdt_mpxy_opteed.c)を使う。`CONFIG_K3_KEYSTONE_SM` で[無効化されているドメイン切替](../opensbi/lib/sbi/sbi_domain_context.c)は、SMと共通の隔離・遷移設計を実装してから有効にする。 |
| Linux | `linux-k3/` と現行K3/Bianbu defconfigを起点に[MPXY経路](../linux-k3/drivers/tee/optee/mpxy_sbi.c)と[fTPMドライバー](../linux-k3/drivers/char/tpm/tpm_ftpm_tee.c)を使う。同じImageでKeystone driverとTEE・TPMを利用する。 |
| OP-TEE・TA | SpacemiTの `k3-br-v1.0.y` を、現行MPXY ABIに合うOP-TEE本体とブート・DT差分の参照元とする。`optee_ftpm` とMicrosoft TPM 2.0参照実装を固定し、K3のTA ABIでビルドする。 |

## 実装順序と完了条件

### 1. 現行Keystone構成を再現し、基準を固定する

- Jupiter2のコミット、cross toolchain、ビルド設定、実機のFSBL/U-Boot、
  稼働中DTB、FIT、起動媒体・区画、UARTログ、成果物のSHA-256を記録する。
  現行のビルド・RAM起動手順で改造OpenSBI＋SMと `linux-k3` を起動し、
  Keystone既存検証の結果と既知の失敗を記録する。元の起動構成と復旧手順も確保する。
- [SDK調査資料](optee-milk-v-jupiter2.md)の固定manifestから、必要な
  OP-TEE本体、MPXY通信、FSBL/SPL・U-Bootのロード処理、domain/DTの差分を抽出する。
  採用したコンポーネントのコミットと適用差分を記録する。
- 完了条件は、既存構成の起動とKeystone回帰の基準を確定し、
  OP-TEE追加に必要なソース、ロード経路、MPXY ABIを特定できること。

### 2. 改造OpenSBI・起動手順・LinuxにOP-TEEを組み込む

- [同居設計](keystone-optee-coexistence-design.md)のC1/C2に沿って、
  Linux・Enclave・OP-TEEで共通のPMPポリシー、hart間の同期、呼出元認可、
  GPR/CSR・FP/Vector状態、RPC・割込み・タイマーと復帰先の管理を実装する。
  異種hartのPMP能力と切替失敗時の復旧を確認し、既存のドメイン切替禁止を
  安全な遷移に置き換える。
- 既存の統合FIT生成とRAM起動経路にOP-TEE payloadを追加する。
  FSBL/SPLとU-Bootがpayloadを渡せるかを確認し、必要な場合は対象の処理を追加する。
  ロード先・entry、SM・OP-TEE・Linuxの予約領域、TEE共有領域、domain/MPXY
  記述を照合する。OpenSBI用DTとLinux用DTB双方への伝達を検証する。
  実機はRAM起動で確認し、永続媒体への配置は対応区画と復旧手順の確定後に行う。
- 同居用のbuild/install/run構成を既存のビルドに追加する。K3 QEMUのpayloadロードと
  DT生成、LinuxのMPXY/mailbox、`CONFIG_TEE`、`CONFIG_OPTEE`、
  `CONFIG_TCG_TPM`、`CONFIG_TCG_FTPM_TEE`、Keystone driverを確認する。
  rootfsにlibteec、`tee-supplicant`、TA、試験ツールを配置する。
- 完了条件は、現行K3 QEMUと実機RAM起動で、同一のOpenSBI＋SM・Linuxの起動中に
  Keystone EnclaveとHello World TAを呼び出せること。UART、TEE登録、
  `xtest` の対象試験、Keystone回帰の結果を記録する。失敗、スキップ、モデルで
  検証できない項目は個別に記録する。

### 3. fTPM TAをRV64向けにビルドしてLinuxへ公開する

- 固定したK3 OP-TEEから、実行環境と同じABIのTA dev kitを出力する。
  `TA_DEV_KIT_DIR` と `CFG_MS_TPM_20_REF` を指定してTAをビルドし、
  生成ELFのアーキテクチャ、署名前後の成果物、OP-TEE側のTA署名検証を確認する。
  初期候補の `optee_ftpm` には `-D_ARM_` があるため、適用箇所を調べ、
  RV64での整数幅、アラインメント、時刻、乱数、NVアクセスへの影響を評価する。
  Measured BootとPPIは初回試験では無効とする。
- UUID `bc50d971-d4c9-42c4-82cb-343fb7f37896` とコマンドID・共有バッファ
  の仕様を [Linux側ヘッダー](../linux-k3/drivers/char/tpm/tpm_ftpm_tee.h) と
  照合する。初期評価は署名済みREE-FS TAとrootfs起動後のドライバー読み込みを
  候補とし、`tee-supplicant` のTA検索先と起動順を確認する。
- LinuxドライバーにはTEE busと `microsoft,ftpm` のDT platform経路がある。
  TAの列挙条件とsupplicantの準備時点を調べ、片方の経路で登録する。
  初期RAMディスク等からTPMが必要になった場合は、early TAの組み込みと
  ストレージRPCが利用可能になる時点を別途検証する。
- 完了条件は、TAセッションが開き、対象fTPMの `/dev/tpmN` と
  `/dev/tpmrmN` をLinuxが登録すること。既存の別TPMがある環境ではsysfsで
  ドライバーを確認し、試験時は `-T device:/dev/tpmrmN` で対象を明示する。

### 4. 同居構成でfTPMとKeystoneの受入試験を行う

| 試験 | 合格条件 |
| --- | --- |
| TPMコマンド | `tpm2_getcap properties-fixed`、`tpm2_getrandom 16`、利用可能なバンクで `tpm2_pcrread` が成功する。 |
| PCR動作 | 評価専用のPCRへ既知ダイジェストをextendし、読み出した値が期待値と一致する。起動後のPCRは対象の起動種別に応じて評価する。 |
| NV永続化 | 評価専用NV indexを定義し、既知データを書き、通常再起動と電源再投入の後で一致を確認する。既存のTPMデータに触れず、試験用indexを後片付けする。 |
| RPC・ストレージ障害 | 評価用環境でsupplicant未起動・再起動、ストレージ利用不可を試し、エラーが観測でき、復旧後に既存NVデータが保たれることを確認する。 |
| 同一プロセス・並行動作 | 同一LinuxプロセスでKeystone SDKとTPMデバイスを開き、Enclave呼出しとTPMコマンドを交互に実行する。複数hartで並行に実行し、RPC・OCALL・割込み後に双方が正しく復帰する。 |
| 隔離と回帰 | Linux・Enclave・OP-TEE間の保護領域へのアクセス制御、共有領域の正常アクセス、遷移失敗時の回復を確認する。実機のPMP/DMA隔離を確認し、既存Keystone suiteとOP-TEE対象試験の結果を基準と照合する。 |
| 起動回帰 | 基準構成と同居構成でLinuxの起動・停止を確認し、起動媒体・CPU構成・メモリー容量を記録する。 |

証跡は、固定manifest、設定差分、使用DTBとFITの識別情報、UARTログ、
`dmesg`、TPMコマンドの出力、NV試験結果を構成ごとにまとめる。
QEMUと実機はそれぞれ結果を記録する。

## 後続の判断

- **永続領域と製品鍵**。評価ではREE FSを候補とする。TAの
  `CFG_FTPM_TA_TEE_STORAGE_ID` とコア設定から、実際に選ばれたバックエンドを
  確認する。製品構成ではRPMB等のリプレイ保護、デバイス固有HUKと乱数源、
  TA署名鍵、Secure Boot・更新時のロールバック対策を検証する。
  Jupiter2のUFS RPMBが採用SDKとLinuxの経路で利用できるかは未確認。
  HUKの開発用フォールバックを許す構成は評価専用とする。
  製品向けの鍵投入・eFuse設定は復旧とプロビジョニングの設計後に扱う。
- **Measured Boot・IMA**。ブート側のイベントログ、OP-TEEのイベントログ取得
  API、Linux側のTPM選択を揃え、イベントログの再生結果とPCRを照合する。
  [既存のKeystone PCR・Quote設計](keystone-tpm2-quote-design.md)との
  測定先の選択はこの段階で決める。

## 参照

- [SpacemiT SDKのOP-TEE構成調査](optee-milk-v-jupiter2.md)
- [OpenSBIへの取り込み計画](optee-opensbi-keystone-merge-plan.md)
- [Jupiter2の永続ストレージ調査](jupiter2-persistent-storage-investigation.md)
- [Jupiter2のセキュリティエンジンと乱数](jupiter2-security-engine-rng.md)
- [OP-TEE fTPM TAの初期候補（固定コミット）](https://github.com/OP-TEE/optee_ftpm/tree/f09f4cdad21028289d4e8fc573893b75f7228dc7)
- [上記TAが指定するMicrosoft TPM参照実装](https://github.com/microsoft/ms-tpm-20-ref/tree/98b60a44aba79b15fcce1c0d1e46cf5918400f6a)
