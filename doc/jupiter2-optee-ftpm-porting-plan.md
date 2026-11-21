# Milk-V Jupiter2へのOP-TEE・fTPM TA移植計画

対象はSpacemiT K3（RV64）搭載のMilk-V Jupiter2 SBC。調査基準はJupiter2の
`main`（`3b9f02773`）。本書は実装・試験の計画であり、ビルド、QEMU起動、
実機動作の結果は未取得。

## 目標と進め方

最初の到達点は、OP-TEE単独の実機評価構成で、LinuxからfTPM TAへTPM 2.0
コマンドを送信でき、試験用NVデータが再起動・電源再投入後にも残ること。
Keystoneとの同居、Measured Boot・IMA、製品向け鍵管理とストレージ保護は
この到達点の確認後に個別に進める。

呼び出し経路は、`tpm2-tools → /dev/tpmrmN → tpm_ftpm_tee → Linux OP-TEE
（SBI MPXY）→ OpenSBIのOP-TEEドメイン → fTPM TA`。
TAの読み込みやストレージのRPCには、選択した構成に応じて `tee-supplicant` が関与する。

| 項目 | 現状と採用方針 |
| --- | --- |
| 起動 | SpacemiTの `k3-br-v1.0.y` secure SDKを参照構成とする。FSBL/SPL、OpenSBI、U-Boot、DTB、`optee.itb` の組み合わせを固定する。 |
| OpenSBI | リポジトリに [MPXY dispatcher](../opensbi/lib/utils/mpxy/fdt_mpxy_opteed.c) と [K3構成](../opensbi/platform/generic/configs/k3_defconfig) がある。既定のKeystoneビルドでは [ドメイン切替が無効](../opensbi/lib/sbi/sbi_domain_context.c) のため、OP-TEE単独用に別構成・別出力先を用意する。 |
| Linux | [MPXY経路](../linux-k3/drivers/tee/optee/mpxy_sbi.c) と [fTPMドライバー](../linux-k3/drivers/char/tpm/tpm_ftpm_tee.c) がある。K3/Bianbu defconfigのTEE設定を起点にし、最終 `.config` で `CONFIG_TEE`、`CONFIG_OPTEE`、`CONFIG_TCG_TPM`、`CONFIG_TCG_FTPM_TEE` を確認する。 |
| TA | OP-TEEの `optee_ftpm` とMicrosoft TPM 2.0参照実装を候補とする。TAのRV64対応、SDKのTA署名・配布手順、ドライバーとのABIを確認する。 |

## 実装順序と完了条件

### 1. SDKの参照構成を固定する

- [既存のSDK手順](optee-milk-v-jupiter2.md)に沿って `repo manifest -r` で
  SDK一式を固定する。併せてJupiter2、TA、TPM参照実装のコミット、
  cross toolchain、ビルド設定、成果物のSHA-256を記録する。
- secure構成をビルドし、FITの構成・ロード先、FSBL/SPLの読み込み経路、
  OpenSBIとLinuxが受け取るDTBを確認する。実機の稼働中DTB・UARTログ・
  媒体と区画情報を取り、復旧用イメージと現行構成のバックアップを確保する。
- 完了条件は、secure SDKの成果物が再生成でき、対象ボード向けの起動経路と
  元の構成への復旧方法を特定できること。

### 2. Jupiter2用のOP-TEE単独構成を起動する

- まずSDKに揃えた構成で確認し、その後Jupiter2ツリーのOpenSBI、
  Linuxを一つずつ差し替える。切り替えごとにMPXYチャネル・メッセージABI、
  OP-TEEドメインの起動hart・エントリ、予約メモリー・共有メモリー、
  PMPの範囲・粒度・エントリ数、必要なI/O隔離を照合する。
- K3 QEMUで同じ呼び出し経路を構成できる場合は先に起動とRPCを試す。
  モデルが提供しないブート、PMP、セキュリティエンジン、ストレージ機能は
  実機で確認する。実機では利用可能な一時起動経路を先に検討する。
  [既存のRAM起動手順](jupiter2-ram-boot-guide.md)で
  `optee.itb` も渡せるかは、実機のSPLと起動媒体で確認する。
  永続媒体への配置は、secure構成の区画定義と復旧方法を確定してから行う。
- 完了条件は、UARTでOP-TEE初期化、LinuxでMPXY経由のTEE登録を確認し、
  `tee-supplicant` を含む構成でHello World TAと `xtest` の対象試験を実行できること。
  失敗とスキップは個別に記録する。

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

### 4. 実機でコマンドと永続化を確認する

| 試験 | 合格条件 |
| --- | --- |
| TPMコマンド | `tpm2_getcap properties-fixed`、`tpm2_getrandom 16`、利用可能なバンクで `tpm2_pcrread` が成功する。 |
| PCR動作 | 評価専用のPCRへ既知ダイジェストをextendし、読み出した値が期待値と一致する。起動後のPCRは対象の起動種別に応じて評価する。 |
| NV永続化 | 評価専用NV indexを定義し、既知データを書き、通常再起動と電源再投入の後で一致を確認する。既存のTPMデータに触れず、試験用indexを後片付けする。 |
| RPC・ストレージ障害 | 評価用環境でsupplicant未起動・再起動、ストレージ利用不可を試し、エラーが観測でき、復旧後に既存NVデータが保たれることを確認する。 |
| 起動回帰 | 通常構成と評価構成でLinuxの起動・停止を確認し、既知の起動媒体・CPU構成・メモリー容量を記録する。 |

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
- **Keystoneとの同居**。[同居設計](keystone-optee-coexistence-design.md)に沿って
  PMPの所有とhartごとの同期、コンテキスト復帰、共有メモリー・RPC・割込みを
  実装する。同一LinuxプロセスからEnclaveとfTPMを交互・並行に呼び、
  既存Keystoneの回帰と、各保護領域の隔離を確認する。
- **Measured Boot・IMA**。ブート側のイベントログ、OP-TEEのイベントログ取得
  API、Linux側のTPM選択を揃え、イベントログの再生結果とPCRを照合する。
  [既存のKeystone PCR・Quote設計](keystone-tpm2-quote-design.md)との
  測定先の選択はこの段階で決める。

## 参照

- [Jupiter2のOP-TEE起動手順](optee-milk-v-jupiter2.md)
- [OpenSBIへの取り込み計画](optee-opensbi-keystone-merge-plan.md)
- [Jupiter2の永続ストレージ調査](jupiter2-persistent-storage-investigation.md)
- [Jupiter2のセキュリティエンジンと乱数](jupiter2-security-engine-rng.md)
- [OP-TEE fTPM TAの初期候補（固定コミット）](https://github.com/OP-TEE/optee_ftpm/tree/f09f4cdad21028289d4e8fc573893b75f7228dc7)
- [上記TAが指定するMicrosoft TPM参照実装](https://github.com/microsoft/ms-tpm-20-ref/tree/98b60a44aba79b15fcce1c0d1e46cf5918400f6a)
