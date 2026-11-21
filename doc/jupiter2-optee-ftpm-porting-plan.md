# Milk-V Jupiter2へのOP-TEE・fTPM TA移植計画

対象はSpacemiT K3（RV64）搭載のMilk-V Jupiter2 SBC。調査基準はJupiter2の
`main`（`cf42df851`）。実装・試験の計画と進捗を記載する。

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

## 第1・第2段階の進捗

- OpenSBIのMPXY共有メモリーサイズ修正（KSB-045、`d32afa86c`）を取り込み、
  K3 Keystone構成の `fw_dynamic.bin` をビルドした。K3 QEMUで16 hartの
  ファームウェア起動を試し、OpenSBI v1.6のバナーとSMタイマー初期化ログを確認した。
  この試行にはLinuxとOP-TEE payloadを含めていない。
- K3用OP-TEE本体を `2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59` からRV64向けに
  ビルドした。[同居検証プログラムと検証用TA](../verifications/optee-coexistence/README.md)
  を追加し、RV64向けのホスト実行ファイルと署名済みTAを生成した。
  ホストのリンクにはoptee_client `9f4414f62dfc5692fd39f760515ce2d344d07b6d` を使用。
- `scripts/run-k3.sh` に `--dtb FILE --optee-elf FILE` を追加した。
  QEMUのgeneric loaderはELFの物理アドレスにロードし、CPUの開始PCはファームウェアに委ねる。
  16 hart・2 GiBのK3 QEMUで、予約領域を追加したDTBと `tee.elf` を渡し、
  QMPで物理アドレス `0x171000000` のELFロード部分を読み出して元ファイルと照合した。
  この試行ではCPUを停止したままロード内容を検査した。
- OPTEED dispatcherに呼出元domainとABI長の検査を追加し、切替結果をMPXYに
  返すようにした（KSB-074、`4b0f75220`）。現行のKeystone構成では切替が
  未対応のため、dispatcherで共有メモリーやcontextを更新する前に要求を拒否する。
  通常K3構成とK3 Keystone構成をビルドし、後者のファームウェア起動ログを
  16 hartのK3 QEMUで確認した。
- 残作業は、DTBのOP-TEEドメインとMPXYチャネル・Linux側ノードの定義、共通PMP
  ポリシーとhart間同期を伴うドメイン切替、ゲストでの通信と逐次・並行試験。
  現行のK3 Keystone構成ではドメイン切替を抑止している。

## 実装順序と完了条件

### 1. 改造OpenSBIでOP-TEE通信を有効にし、K3 QEMUで確認する

- 現行の改造OpenSBI＋Keystone SM、`linux-k3`、K3 QEMUのコミットと設定を固定し、
  基準構成を起動してKeystone既存検証の結果を記録する。SpacemiT SDKから、
  現行MPXY ABIに対応するOP-TEE本体と必要なブート・DT差分を特定する。
- [同居設計](keystone-optee-coexistence-design.md)に沿って、既存MPXY dispatcherを
  Linux・Enclave・OP-TEEの共通PMPポリシーとドメイン切替に接続する。
  hart間同期、CPU状態の保存・復帰、呼出元の認可、RPC・割込み・タイマー、
  切替失敗時の復旧を扱う。保護を維持できる切替経路の実装後にドメイン切替を有効にする。
- K3 QEMUのpayloadロード・DT生成、LinuxのMPXY/mailboxとTEE設定、
  rootfsのlibteecと `tee-supplicant` を揃える。固定したOP-TEEをQEMU用にビルドし、
  同一ゲストでOP-TEE初期化、LinuxのTEE登録、既存Hello World TAの呼出し、
  Keystone Enclaveの動作を確認する。
- **成果物・完了条件**。改造OpenSBIの変更、再現用のビルド・起動手順とUARTログを残す。
  QEMU上で実Linux → SBI MPXY → 改造OpenSBI → OP-TEEの往復が成功し、
  Keystoneの基準試験を再実行できること。

### 2. 通信・同居のテストプログラムを作り、K3 QEMUで確認する

- `verifications/` にLinux側テストプログラムと検証用TAを追加する。
  同じプロセスでTAセッションとKeystone Enclaveを開き、TAへの入力と応答を照合し、
  Enclave呼出しと交互に反復する。必要なRPC・OCALL後の復帰も確認する。
- 現行K3 QEMUは16 hart構成を要求する。まず単一hartに試験プロセスを固定して逐次試験を行い、複数hartの並行試験へ進む。共有領域の正常アクセス、
  保護領域の隔離、通信・遷移の失敗時の復帰、既存Keystoneの回帰を確認する。
  試験は実K3 QEMUゲスト、Linuxドライバー、OpenSBI/SM、EnclaveとTAを通して実行する。
- **成果物・完了条件**。テストソース、ビルド・ゲスト内実行手順、期待値、
  実行結果を揃える。失敗・スキップと、QEMUで検証できる範囲を記録する。

### 3. 改造OpenSBIの実機テスト手順書を作成する

- [既存のKeystone RAM起動手順](jupiter2-ram-boot-procedure.md)を基に、
  対象機材・起動媒体の確認、現行環境のバックアップ、成果物のハッシュ照合、
  統合FITの生成・RAM転送、UARTでの起動確認、元の構成への復帰を記載する。
  既存のFSBL/SPLとU-BootがOP-TEE試験用payloadを渡せるかを確認し、
  必要な場合は対応するローダー、ロード先、OpenSBI用DTとLinux用DTBを指定する。
- 第2段階のテストプログラム・検証用TAを使い、改造OpenSBIの通信、ドメイン切替、
  Keystone回帰を実機で確認できるようにする。コマンドの実行場所、期待ログ、
  合否・中止条件、採取するUARTログと `dmesg` を明記する。
- **担当と成果物**。Codexが実機テスト手順書と試験に必要な成果物一覧を作成する。
  実機での操作・試験はユーザーが実施する。実機の合否は提供されたログに基づいて記録する。

### 4. OP-TEEとfTPM TAをクロスコンパイルし、実機への配置手順を示す

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

- 開発ホストでRV64向けOP-TEE本体とfTPM TAをクロスコンパイルする。
  統合FITに組み込むOP-TEE payload、署名済みTA、対応のLinux Image・DTB・必要な
  モジュール、libteec・`tee-supplicant` の版、配置先とハッシュを一覧化する。
  実機手順には、ホストでのビルド、FITへの組み込み、実機への転送・RAM起動、
  rootfsへのTA配置、サービス・ドライバーの起動順、元の構成への復帰を含める。
  永続媒体へ配置する場合は対応区画と復旧手順を確定する。
- **担当と成果物**。Codexがクロスコンパイル済み成果物と実機deploy手順を揃える。
  実機への配置と下表の確認はユーザーが実施する。第3段階の結果を確認してから、
  fTPMを含む構成の実機試験へ進む。

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
