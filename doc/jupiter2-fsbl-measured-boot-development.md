# Jupiter2 FSBL Measured Boot 開発手順書

[設計書](jupiter2-fsbl-measured-boot-design.md)の初期プロファイルを段階的に実装する。以下は開発計画。既存コマンドと新規実装が必要な箇所を段階ごとに示す。

## 1. 既存RAM起動とビルドの固定

- FSBL/U-Bootは参照ビルダーが固定する `ganboing/u-boot-k3@4c294a06c14e`、OP-TEEは `spacemit-com/optee_os@2fbd6ae54d89`、fTPMは `OP-TEE/optee_ftpm@6f99e783eb9b` を出発点とする。Jupiter2のコミット、linux-k3設定、Keystone/OpenSBI、ESOS、TA参照実装、ツールチェーンとSHA-256も記録する。
- 既存の参照ビルダーを [RAM起動ガイド](jupiter2-ram-boot-guide.md) に従って実行し、FSBL・統合FIT・構成記録と基準UARTを確保する。参照ビルダーには固定ソースの展開とボード設定の変更がある。実装時は固定コミット上の差分を管理し、再現できるパッチ適用段階をビルダーに追加する。
- 基準の組み合わせでRAM起動と復旧経路を確認する。改修版を最初に試す際もRAM起動を使い、現行の永続媒体上の起動ファイルを保持する。

## 2. FSBLでログを作る

- K3のFIT構成選択、ロード完了、起動・引き渡しを行う箇所を追い、表の対象を列挙する。各対象の正確な測定範囲と順序、ESOS起動時点を確定する。
- SPLのサイズ制約を確認し、利用できるSHA-256実装とTCG形式のシリアライズを組み込む。予約領域はFRU・DDR・FITダウンロード範囲、OpenSBI、OP-TEE、TEE共有領域と照合する。PMPを消費する場合はKeystoneの使用可能枠への影響を確認する。
- 実行前に測定し、ログ確定後に上限、実使用長、イベント数を記録する。最初の出力を、独立したログデコーダーとホスト側のダイジェスト計算で照合する。
- OP-TEEを追加した統合FITとFSBLの対を作れるよう、既存の参照ビルダーとFIT生成スクリプトを拡張する。現行の参照ビルダーの引数だけでこの測定付きペイロードを生成できることは前提にしない。

## 3. OpenSBIとOP-TEEの受領経路を作る

- OpenSBIの起動時にFSBL引き渡し情報を検証する。ログを保護するRAM領域の境界と権限を確定し、必要に応じてOP-TEE用の領域にコピーした上で、保護済みアドレスと正確な長さをOP-TEEに渡す。
- K3のRISC-V OP-TEE起動時にログのマッピングを接続し、物理アドレスの64ビット復元を修正する。ログサイズの上限、アドレス加算とページ丸め、予約範囲を検査する。QEMUで4 GiBより上の予約領域を使い、受領したバイト列と長さを照合する。
- 先にQEMUで保護領域に既知のテストログを用意し、FSBLと独立にPTA受領・TA再生を確認する。この段階の合格範囲は受領と再生。FSBLでの生成と実際の受け渡しは統合RAM起動で確認する。

## 4. OP-TEE・fTPM・Linuxをビルドして結合する

- [fTPMの既存ビルド手順](jupiter2-ftpm-ta-test.md)を使用する。Coreに `CFG_CORE_TPM_EVENT_LOG=y`、TAのmake引数に `CFG_TA_MEASURED_BOOT=y CFG_TA_EVENT_LOG_SIZE=<確定した最大バイト数>` を追加する。RV64 dev kitと署名付きTAを同じビルド構成で生成する。
- 固定版fTPMにログ取得、検証、extendの結果が上位へ伝わる経路を実装する。起動時のPCR初期状態と完了条件を確かめ、同一起動でのTA再接続を試す。
- Linuxの既定モジュール `tpm_ftpm_tee`、`tee-supplicant`、試験用REE FS、Linux用DTBを準備する。起動用と試験用のファイル一覧を残す。Linux IMAの同時利用には、IMA初期化前のfTPM登録が別途必要。
- QEMUの受領試験を通過した成果物で統合FITを作り、実機で [RAM起動手順](jupiter2-ram-boot-guide.md) に従ってFSBLとFITを検査用に転送する。実機での操作とUART採取はユーザーが実施する。合否は [検査手順書](jupiter2-fsbl-measured-boot-verification.md) で判定する。
