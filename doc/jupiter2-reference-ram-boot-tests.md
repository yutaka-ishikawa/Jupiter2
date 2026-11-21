# Jupiter2参照RAM起動: 検査と実機テスト手順

## 1. 試験対象と判定の分離

[解析・ビルド手順](jupiter2-reference-ram-boot-development.md)で作る、新しいFSBLとESOS入り統合FITを対で試験する。今回の目的は販売元OpenSBIによるUFS列挙の確立である。古いvendor-releaseのFSBLと新しい統合FITを混ぜない。ホスト検査合格と実機起動合格は別に記録する。

実機投入前に固定ソースのPico用DT、SPLのDDR/JTAG設定、ESOSとOpenSBIの版をレビューする。参照記事のCOM260での成功はJupiter2での動作確認ではない。通常起動できる既存NORとバックアップを保持する。

## 2. 開発PCの検査

publicリポジトリのルートで実行する。

```bash
python3 -m py_compile scripts/build-jupiter2-reference-ram-boot.py \
  scripts/build-jupiter2-ram-boot-image.py
python3 scripts/tests/test_jupiter2_ram_boot_image.py
```

実際のdtc/mkimage/dumpimage/lzopでFITを作り、外部データ形式、全27 ESOS loadables、LZO展開後の重複、ハッシュ破損、参照レイアウト、組込みOpenSBI不一致を検査する。これはホスト梱包試験であり、CPUやPMPを模擬する試験ではない。

ビルド成功後の生成物を確認する。

```bash
cd work/jupiter2-ram-boot/reference-vendor/release
sha256sum -c records/FSBL.bin.sha256
sha256sum -c records/ram-boot-vendor.itb.sha256
dumpimage -l images/ram-boot-vendor.itb
cat ../records/build-manifest.json
cat ../records/uboot.config
cat records/manifest.json
```

conf_11のdescription=k3-pico-itx、loadablesの先頭=opensbi,uboot、続いて選択したconf_dualの全loadablesが同じ順序であることを確認する。rcpu0-fw、rcpu1-fw、rcpu-data-nullを改名しない。`hardware_verified:false`はホスト検査後もfalseのままである。

FSBL検査はROM向けラッパー全体が0x74000以内、AIHDヘッダーのmagic/version/非secure設定とCRC、SPL payloadのサイズ・CRC・末尾長を確認する。署名の信頼性やDDR互換性を認証するものではない。USB転送上限0x20000000とROMのFSBLサイズ制約を混同しない。

## 3. 通常起動の比較ログ

FDLを押さず完全電源断から起動する。UARTログを保存し、通常のU-Bootで停止できる場合は次を一度実行する。既存OSや起動設定の保存変更はしない。

```text
version
scsi scan
scsi info
```

通常起動でも同じUIC_ERRORなら、RAM統合FITだけの問題として調査を続けない。通常起動でUFSが見えるかを記録する。既に報告された販売元・開発版のRAM起動失敗を、改めて成功扱いにはしない。

## 4. 販売元OpenSBIを使う新しい対でRAM起動

UART端末の設定は[UART接続手順](milkv-jupiter2-uart.md)を参照し、全ログを保存する。PC側は115200 baud、8N1、フロー制御なし。以下のfastboot操作はUART端末とは別の開発PCターミナルで行う。

1. Jupiter2を完全電源断し、FDLを押しながら起動する。DRD Type-CをデータケーブルでPCへ接続する。
2. PCでROMのfastbootを確認し、新しく作ったFSBLを転送する。

```bash
cd work/jupiter2-ram-boot/reference-vendor/release
mkdir -p logs
sudo fastboot devices
sudo fastboot stage images/FSBL.bin 2>&1 | tee logs/01-stage-fsbl.txt
sudo fastboot continue 2>&1 | tee logs/02-continue-rom.txt
```

3. UARTで新しいSPLの版、DDR初期化成功を確認する。USB機器の再認識を待ち、SPLの転送上限を確認する。

```bash
sudo fastboot devices
sudo fastboot -s HW4MPK3321280144 getvar max-download-size
sudo fastboot -s HW4MPK3321280144 stage images/ram-boot-vendor.itb \
  2>&1 | tee logs/03-stage-fit.txt
sudo fastboot -s HW4MPK3321280144 continue \
  2>&1 | tee logs/04-continue-spl.txt
```

新しく作ったSPLが報告する上限がFITサイズ以上であることを確認してからstageする。上限が以前の0x20000000と異なる場合は、manifestの指定も再評価する。serialが変わった場合はdevicesの実測値を使う。`waiting for ...`が続く場合はCtrl+Cし、UARTで現在どの段階かを見る。

4. UARTでESOS remoteprocのロード・開始失敗がないこと、販売元OpenSBIの起動表示、U-Bootの版と`=>`を確認する。ログがESOS開始を示さない場合、警告がないだけで開始済みとは判定せず、FSBLフックと追加ログで確認する。

参照固定ソースは`run_fastboot_command()`の自動呼出しを停止している。この新しい対では、販売元4月版のようにU-Bootへもう一度continueを送ることを前提としない。USB fastboot機器が消えてUARTプロンプトが出ればそのまま進む。UARTがfastboot待機を明示し、devicesにも列挙される場合だけ追加continueの要否を調べる。

5. UARTで次を実行する。bootcmdは空、bootdelayは-1であることを確認する。

```text
version
printenv bootcmd bootdelay
scsi scan
scsi info
```

UFSの容量・ベンダー・デバイスが表示され、UIC_ERROR、descriptor失敗、UTP timeoutが出なければ「UFS列挙」の段階を合格とする。最初のscanが失敗した場合は反復せず、全ログを保存して停止する。EFI起動やLinux起動の合格には含めない。

## 5. Keystone版との比較

販売元版の段階4が成功した後、Keystone版を別outputへ生成する。ソース固定コミット、試験用設定、ESOS入力のハッシュが同じで、差分がOpenSBIの内容・必要な実行時予約領域であることをmanifestで確認する。FSBLは同じ設定でも、ビルド時刻が入るためバイト一致するとは限らない。差分理由を記録する。

完全電源断・FDLから同じ順序で新しいFSBLと`ram-boot-keystone.itb`を転送する。PMP初期化・CSR確認・SM初期化が成功し、U-BootのUFS列挙結果が販売元版と同じことを確認する。Linux用DTのRPMIページ使用条件を別途満たすまでLinuxへ進まない。Linux/Enclave試験は既存の[PMP調査文書](jupiter2-pmp-granularity-issue.md)と[RAM起動手順](jupiter2-ram-boot-procedure.md)の判定を引き継ぐ。

## 6. 失敗時の復帰と記録

DDR初期化、ESOS開始、OpenSBI、UFSのどこで停止したかを記録する。flash/erase/saveenv/sf writeは実行しない。通常は電源を切り、FDLを押さず起動すれば元のNOR起動へ戻る。UARTに`save DDR training info`や`write ... to spinor`が出た場合は無書込み試験とは扱わず、その箇所とバックアップを確認する。元OpenSBI区画の復元だけで他区画の変更も戻るとは扱わない。

各試験に入力SHA-256、ソースコミット、設定、全UARTログ、PC fastbootログ、電源断の有無、到達段階、エラー最初の行を残す。UFS失敗が再現したらKSB-063へ結果を追記し、次にFSBLのremoteproc開始、product_name、ESOS版、クロック・PHY初期化を通常起動と比較する。

## 7. 今回のホスト検証記録

2026-11-21に以下を確認した。

| 検査 | 結果と範囲 |
| --- | --- |
| Python構文 | 両スクリプトで合格 |
| 実FITツールによる回帰試験 | 23件合格。参照レイアウトを含む形式試験用データを使用 |
| 固定ソースの取得・準備 | ローカルgitから固定SHAを取得し、差分とmanifestを生成。既存outputへの再実行は拒否 |
| 最終Kconfig契約 | 固定ソースの実Kconfigで設定生成し検査合格。設定生成のコンパイラー検査はホストGCCであり、RISC-Vコードのビルド結果ではない |
| FSBL形式 | 固定ソースの実build_binary_file.pyに形式試験用SPLデータを渡して生成し、ヘッダー・CRC・長さを検査。payload破損を拒否 |
| K3向けGCCでの全ビルド | 未実施。この環境に対応するクロスGCCがない |
| 実ESOS・DDR・RPMI・UFS | 未検証。ユーザー実機で段階3以降を実施する |
| QEMU guest統合 | 未実施。ホスト検査をguest PASSとは扱わない |

形式試験用SPL/ESOSは起動用ファームウェアではなく、実機へ転送しない。
