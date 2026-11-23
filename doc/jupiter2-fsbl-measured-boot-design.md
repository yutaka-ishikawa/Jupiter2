# Jupiter2 FSBL Measured Boot 設計書

## 対象と信頼の起点

SpacemiT K3のFSBL（U-Boot SPL）が起動イメージを測定し、TCG 2.0イベントログを作る。OpenSBIはログを保護してOP-TEEへ渡し、fTPM TAは初回起動時にログのダイジェストをPCRへ反映する。初期実装は既存のRAM起動経路を対象とし、FSBLから引き渡すファームウェアと設定の測定までを合格範囲とする。Linux Image・initrd・最終Linux DTB・bootargsの測定は、U-Bootで最終値が確定する段階を別途設計する。Linux IMAのPCR 10は既存の実行時測定の用途を維持する。

FSBLはこの方式の最初の測定主体。製品で測定を信頼する前提は、BootROMまたは先行する信頼済み段階がFSBLを認証すること。USB RAM起動での試験では連携の機能を検証する。ベンダーの認証範囲、鍵管理、ロールバック対策の実機確認は別途必要。

## 測定対象とPCR

| 順序 | PCR | 対象と測定時点 |
| --- | --- | --- |
| 1 | 0 | OpenSBI＋Keystone SM。選択したFITのペイロードを配置した後、実行前に測定 |
| 2 | 0 | U-Boot本体。同じFIT構成で実際に引き渡すバイト列を測定 |
| 3 | 0 | OP-TEE Core。統合FITから実際に配置するペイロードを測定 |
| 4 | 0 | ESOSの各ロード対象。対象コアの起動前に測定し、複数ならFITの順序を固定 |
| 5 | 1 | 選択したFIT構成と、OpenSBI／OP-TEE／U-Bootに渡す起動時DTB。アドレス等の最終修正を適用した後に測定 |

順序とPCR番号はJupiter2の初期プロファイル案。SPLの実際のロード順に依存せず、各対象が実行を開始する前にその対象の測定を終える。処理順が固定表と異なる場合は、ダイジェストを一時保持して確定順で記録する。圧縮やELFが関わる対象については、何をハッシュしたかを識別できるよう、ファイル形式、ロード範囲、アドレスおよびサイズをビルド記録に残す。実行対象を変更する再配置、DTB修正、キャッシュ書き戻しがある場合は、測定した表現と引き渡す内容の対応をテストで示す。ログ引き渡し自身のDTプロパティは循環を避けるため、測定範囲から外すか規定値に正規化し、検証器にも同じ規則を適用する。

## ログ形式と引き渡し

1. **FSBL**。初期評価ではSHA-256バンクを使う。TCG EFIの最初の `Spec ID Event03` を添え、後続の `TCG_PCR_EVENT2` にPCR番号、イベント型、ダイジェスト、対象識別情報を記録する。イベント型とサポートするアルゴリズムは固定版fTPMのパーサーと照合する。SHA-256バンクが実際に有効であることを検査してから運用する。FSBLはTPMコマンドを発行せず、完全なログを引き渡し前に確定する。
2. **OpenSBI**。ログ用の予約領域はFIT配置、PMP、IOPMP、既存予約メモリを照合して確定する。Base、容量、実使用長、所有者を起動構成に記録し、FSBL→OpenSBI→OP-TEEで同じ実アドレスと長さを使用する。OpenSBIは範囲と引き渡し元を確認し、後段の通常世界およびDMAから書き換えられないように保護する。保護を証明できない構成は評価用とする。
3. **OP-TEE**。採用版 `2fbd6ae54d89` のRISC-V側には `tpm_map_log_area()` の呼び出しが見当たらない。Coreで `CFG_CORE_TPM_EVENT_LOG=y` を有効にし、RISC-V起動時に保護済みログをマップして、`PTA_SYSTEM_GET_TPM_EVENT_LOG` からTAに渡す。既存の `arm,tpm_event_log` DT互換名を流用する場合も、物理アドレスの上位・下位セルを両方読んで検査する。現行実装は下位32ビットのみを使用するため、4 GiBより上で切り捨てが起きる。外部DTに含まれるアドレスは、ファームウェアが保護した範囲との照合を経て採用する。
4. **fTPM**。採用版 `6f99e783eb9b` の `CFG_TA_MEASURED_BOOT=y` を使う。Core側の実使用長と `CFG_TA_EVENT_LOG_SIZE` の上限を合わせ、TAスタック容量も確認する。現行TAはログ取得・処理に失敗してもTA初期化の成功を返せるため、測定必須構成では明示的な失敗判定を追加する。ヘッダー、長さ、アルゴリズム、PCR、イベント列を先に検証し、全イベントのextend成功後にだけ測定完了を示す。途中の失敗は当該起動の測定を無効と扱う。
5. **検証ツール**。保護した原本に対応するイベントログを検証用に取得できるようにする。初期試験ではテスト用の出力で取得し、Linux標準TPMログへの公開は別の引き渡しとして設計する。Linux向けログを公開しても、TA用原本の可変共有バッファとして使わない。

fTPMが同じログを二重にextendしないよう、初期実装はコールドブートのPCR初期状態を基準とする。TPM Startupの結果を確認し、TA再オープンで再生しない。通常再起動、TAの異常終了、状態復元ありのStartupを測定必須構成で扱うには、同じ起動の完了状態と復元PCRの扱いを検証する。PCRの一致はログ再生と対象バイナリの照合によって判断する。

## 参照

- [開発手順書](jupiter2-fsbl-measured-boot-development.md)
- [検査手順書](jupiter2-fsbl-measured-boot-verification.md)
- [SpacemiT K3起動資料](https://github.com/spacemit-com/docs-buildroot/blob/main/en/k3_buildroot/device/boot.md)
- [TF-AとfTPMのMeasured Boot実装例](https://trustedfirmware-a.readthedocs.io/en/v2.14.0/design_documents/measured_boot_poc.html)
- [SpacemiT版OP-TEEのログ受領コード](https://github.com/spacemit-com/optee_os/blob/2fbd6ae54d89/core/kernel/tpm.c)
- [固定版fTPMのログ処理](https://github.com/OP-TEE/optee_ftpm/blob/6f99e783eb9b/platform/fTPM_event_log.c)
