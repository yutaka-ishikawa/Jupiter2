# Jupiter2 FSBL Measured Boot 検査手順書

## 準備と取得する証跡

1. [設計書](jupiter2-fsbl-measured-boot-design.md)のPCR割り当て、イベント型、測定範囲を固定する。FSBL、統合FIT、DTB、TA、Linux、OpenSBI/SM、設定、TPMハッシュバンク、予約領域を記録する。
2. 対象ファームウェアの選択構成と測定範囲を一覧にし、ホストで各SHA-256を計算する。FIT全体のハッシュとペイロード単位のハッシュを個別に保存する。
3. 起動ごとにUART、バイナリTCGログ、ログの実使用長、解析結果、PCR値を保存する。QEMUの注入ログと実機FSBL生成ログは別の試験記録に保存する。

## 検査項目

| ID | 環境 | 手順と合格条件 |
| --- | --- | --- |
| MB-01 | ホスト・SPL | 同じ入力のログを2回生成する。独立したデコーダーでヘッダー、SHA-256バンク、PCR、順序、対象名、ダイジェストを確認し、設計表と事前計算値に一致させる。SPLサイズとロード領域が既存制限に収まることも確認する。 |
| MB-02 | 16 hart QEMU | 既知の正常ログを予約領域に用意して起動する。OP-TEEが4 GiBより上のアドレスから指定長のバイト列を受け取り、fTPMが全件処理する。起動用FSBLを経由しないQEMU試験ではFSBL生成を未検証と記録する。 |
| MB-03 | QEMU・実機RAM起動 | コールドブートし、fTPMを登録する。ログを再生して、全対象PCRを `/dev/tpmrmN` の実測値と比較する。OP-TEEの出力する受領長とFSBLの実使用長が一致する。 |
| MB-04 | ホスト・実機RAM起動 | 起動可能な既知の別ビルドを1対象だけ差し替え、FITを正規に再生成して起動する。対応イベントのダイジェストが変わり、先頭から再生したPCRに一致する。測定対象が複数変わった場合は差分を記録して再試験する。 |
| MB-05 | QEMU | 空のログ、長さ不一致、固定ベースの不一致、予約範囲外、未対応バンク、上限超過を個別に試す。測定完了を返さず、判定理由を取得できる。既存の通常起動構成の回帰も確認する。 |
| MB-06 | QEMU・実機RAM起動 | 同じ起動でTPMデバイスを閉じて再オープンする。対象PCRが再extendされないことを確認する。通常再起動と電源再投入を個別に行い、設計したStartup方針に従った再生結果と照合する。 |
| MB-07 | 実機RAM起動 | FSBLからLinuxまでUARTを採取し、FSBLが出した対象数、ログ長、OpenSBIの予約・保護、OP-TEEの受領、fTPM登録を照合する。保護領域が通常世界やDMAの書込み対象外であることを、対応するPMP/IOPMP設定から確認する。 |
| MB-08 | QEMU・実機RAM起動 | Keystone Enclaveの作成・実行・破棄、fTPMの通常コマンド、既存の起動停止を確認する。IMA有効構成では実行時測定でPCR 10が更新され、ブート測定のPCRと区別できることを確認する。 |
| MB-09 | 実機RAM起動 | 開発版から基準FSBL/FITの対へ戻し、UARTで基準構成のLinux起動を確認する。 |

## 最初のFIT接続をUARTで検査する

参照ビルダーに `--spl-measurement-log` を付けたFSBLをRAM起動し、
`J2MB FIT log bytes=` とそれに続く `J2MB <16進データ>` 行を取得する。
UARTファイルにはこの試行1回分のログを入れ、次のように抽出する。

```sh
awk '$1 == "J2MB" && NF == 2 { print $2 }' uart.log | xxd -r -p > spl-fit-eventlog.bin
wc -c spl-fit-eventlog.bin
python3 scripts/jupiter2-measured-boot-replay.py spl-fit-eventlog.bin
```

抽出長をUARTの長さ表示と照合する。OpenSBI、U-Bootの順に
PCR 0向けに両イベントがあり、ダイジェストがロード対象の実データと
一致することを確認する。OP-TEEを同梱した場合はCoreのロード済み
バイト列を照合し、ESOSはRCPUに渡した展開済みELF全体を照合する。
PCR 1にはNUL終端を含む構成名と、ログ長のセルを0にしたpacked DTBの
ダイジェストが入る。DTBはLinux起動後の値ではなく、SPLがOpenSBIへ
制御を渡す時点の値を取得する。PCRへの反映は後段の検査で行う。

## 固定領域の検査

ホストのFIT生成試験では、固定ログ範囲に跨るOpenSBI範囲を拒否し、
範囲の先頭で終わる隣接区間を許容することを確認済み。
実際のSPL起動時は引き渡し直後のDTBの `/tpm-event-log` を取得し、
`tpm_event_log_sm_addr=<0x1 0x71ff0000>` とUARTの実使用長に一致する
`tpm_event_log_size` を照合する。


- FSBLのロードマップ、OpenSBIの領域表、OP-TEEの割り当て上限を比較し、
  ログ専用範囲 `[0x171ff0000, 0x172000000)` がそれぞれで同じであることを確認する。
- 使用長0、64 KiBちょうど、64 KiB超、異なるベースを個別に検査する。
  容量境界の正常ケースは、使用長がちょうど64 KiBの正当なTCGログで試す。
- Linux・Enclave状態のPMPに追加枠がなく、既存の16 MiB private領域の拒否が
  全hartに適用されていることを設定と読み戻しで確認する。OP-TEE側では
  専用マッピングが読み取り専用で、TA用メモリと重ならないことを確認する。
- 実機で、IOPMPの保護範囲がログ末尾まで含むことを確認する。

## PCR照合の操作

1. 初回起動では空の試験環境を用意し、fTPM登録後、sysfsで対象デバイスを同定する。以下では `/dev/tpmrm0` を例とする。

   ```sh
   tpm2_getcap -T device:/dev/tpmrm0 pcrs
   tpm2_pcrread -T device:/dev/tpmrm0 sha256:0,1
   tpm2_eventlog ./fsbl-eventlog.bin
   python3 scripts/jupiter2-measured-boot-replay.py ./fsbl-eventlog.bin
   ```

2. `fsbl-eventlog.bin` は起動時に保護したログに対応する試験用のバイナリ。Linux標準の `binary_bios_measurements` を使う場合は、同じログが公開されていることを長さとSHA-256で確認する。
3. コールドブート時のPCR初期値を確認する。対象PCRがSHA-256の32バイトゼロで開始する構成では、その値からログ順に `SHA256(旧PCR || イベントのSHA-256ダイジェスト)` を計算する。開始値が異なる場合は、その由来を特定して記録する。Spec IDなどの非extendイベントは計算から除外する。
4. PCR 0と1の計算値と実測値を比較する。パーサーがログを表示できること、測定ダイジェストが対象バイナリと一致すること、fTPMの実測PCRが一致することをそれぞれ記録する。

PCR再生ツールはホスト上の合成ログでPCR 0・1の計算と不正入力の拒否を確認した。
統合検査は計画段階。既存のfTPM・IMAのQEMU実績は [試験記録](jupiter2-ftpm-ta-test.md) を参照。

## OpenSBI受領検査の実測

16 hartのJupiter2 QEMUへ、ログのメタデータを追記したDTBを直接渡した。
固定アドレス、長さ116バイトの設定では、DTB照合と既存private領域の
PMP計画検査を通過した。Linuxの16 CPU起動、fTPMによる16バイトの
乱数取得、正常な電源断を確認した。アドレスの上位セルを0にしたケースと、
長さを65,537バイトにしたケースは、いずれもOpenSBIがメタデータを拒否し、
Linuxまで進まなかった。

この試験はメタデータとPMP計画の検査を対象とする。FSBLが生成したログの受領、
OP-TEEによるログの取得、PCRへの反映、実機IOPMPの確認は別途実施する。
[OpenSBI受領検査のUART抜粋](evidence/jupiter2-fsbl-measured-boot/opensbi-dt-uart.txt)

## OP-TEE受領とfTPM再生の実測

16 hartのJupiter2 QEMUで、116バイトの合成TCGログを
`0x171ff0000` に置き、同じアドレスと長さを記したDTBで起動した。
OpenSBIの受領検査、OP-TEEの `ROM_SEC` マッピングとログの認識を確認した。
空の試験用NVストレージから起動したfTPMのSHA-256 PCR 0を
`/dev/tpmrm0` から読み、ホストのPCR再生ツールによる計算値と一致した。
Linuxは16 CPUで起動し、ゲストは正常に電源断した。

対象はQEMUの注入ログと空のNVストレージからの起動。
FSBLによるログ生成、NV状態復元を伴う再起動、実機IOPMPの検査は残る。
[QEMU UART抜粋とPCR照合](evidence/jupiter2-fsbl-measured-boot/ftpm-replay-uart.txt)

## Startup CLEARとNV保持のQEMU試験

16 hartのQEMUを別プロセスで2回起動し、異なる合成TCGログを渡した。
初回は試験用NV indexに4バイトを書き、`Shutdown(STATE)` の成功後に
保存ファイルを回収した。2回目はそのREE FSを復元し、同じindexを
再定義せず4バイトを読み出した。両起動で `Startup(CLEAR)` の成功を
1回ずつ観測し、デバイスを開き直して2回取得したSHA-256 PCR 0が、
各起動のログだけをホストで再生した値に一致した。両起動とも正常に電源断した。

この試験には保存ファイルを引き継いだコールドブートを使用した。
Linuxの通常再起動でのFSBL再実行、同一ブート内でのTA異常終了、
FSBLからの実機受け渡しは未検証。
[UARTログとPCR照合](evidence/jupiter2-fsbl-measured-boot/ftpm-startup-clear-uart.txt)

## SPL完全ビルドと2本のPCRの確認

固定版U-Bootに参照RAM起動の診断パッチと測定パッチ一式を適用し、
`k3_defconfig` でSPL測定を有効にした。RISC-V GCC 13.3.0でSPLを
コンパイル・リンクし、433,344バイトの `FSBL.bin` を生成した。
ヘッダーと埋め込みSPL DTBの一致、測定・引き渡しのシンボルのリンクを確認した。
このビルドはSPL単体で、実機のESOS FITを使った参照RAM起動一式の生成は
行っていない。[ビルド記録](evidence/jupiter2-fsbl-measured-boot/spl-build.txt)

別途、16 hartのQEMUにPCR 0・1の合成イベントを一つずつ含むログを注入した。
OP-TEEが受領し、fTPMの `Startup(CLEAR)` 後に `/dev/tpmrm0` から
読み出したSHA-256 PCR 0・1が独立再生値と一致した。正常電源断を確認した。
QEMUではSPLを実行していない。FSBLが生成したログとの統合検査には
対応する実機用ESOS FITと、実機のRAM起動が必要。
[UARTログと照合結果](evidence/jupiter2-fsbl-measured-boot/dual-pcr-uart.txt)

## 不正なイベントアルゴリズムの拒否

SPL経由の試験に先立ち、16 hart QEMUで、SHA-256のみを宣言した
合成ログのイベントにSHA-1のアルゴリズム番号を設定して渡した。
Linuxは起動したが、fTPMはログ再生を拒否し、TPMドライバーがTAの
セッションを開けなかった。テスト用ゲストはPCRを得られず電源断した。
これはテストの期待する拒否結果。RAM起動関連のホスト試験は46件合格。
[UARTログ抜粋](evidence/jupiter2-fsbl-measured-boot/malformed-event-uart.txt)
