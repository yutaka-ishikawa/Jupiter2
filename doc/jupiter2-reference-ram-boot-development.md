# Jupiter2: ESOSを含む参照実装によるRAM起動の開発

## 1. 目的と現在の判定

販売元OpenSBIでUFSを列挙できるRAM起動を先に確立し、その後OpenSBIだけをKeystone版へ交換する。参照先は[ganboing/K3-Docsのhacking手順](https://github.com/ganboing/K3-Docs/blob/master/hacking/README.md)。これは第三者のK3開発記録であり、Milk-VがJupiter2で保証した手順ではない。

現在、開発版OpenSBI、販売元OpenSBIを使用した統合FIT、および販売元FSBL＋元のu-boot.itbのいずれでもUFS descriptor取得失敗が報告されている。`Error in status:00000004`は参照ドライバーのUIC_ERRORに相当する。続く`err = -110`はタイムアウトである。Keystone固有の障害、PMP設定、UFS媒体故障のどれかに原因を断定できない。通常起動との比較はまだ必要である。追跡は[KSB-063](keystone-bug-report.md#ksb-063-ram起動後のu-bootでufs通信が失敗)で行う。

## 2. 参照ドキュメントの解析

参照手順はESOSを結合するだけではなく、修正版U-BootからFSBLとS-mode U-Bootを作り、OpenSBIとESOSを含むFITをそのFSBLで起動する。

| 対象 | 参照実装で確認した内容 | 今回の扱い |
| --- | --- | --- |
| ソース | ganboing/u-boot-k3、k3-ganboing | `4c294a06c14e46e9c9cc934373c3e63919703017`に固定 |
| OpenSBI | ITSのimages/opensbi、各構成のloadablesにopensbi,uboot | 同じ配置規約で生成し、組込みBINの一致を検査 |
| ESOS | combine-esos.shでimageとloadablesを追加 | 明示したconf_dualの全loadablesを順序・名前を保って追加 |
| FSBL | LZO展開、rcpu0-fw/rcpu1-fwのremoteprocロード・開始 | 同じソースから作ったFSBLを必ず対で配布 |
| RCPU共有データ | rcpu-data-nullをロード後、EEPROM product_nameを書き込む | フックと元image名を維持 |
| USB起動 | BOOT_DEVICE_BOARDでは追加env読込みを省略、自動fastboot呼出しを停止 | 元の販売元版の追加continue待ちと混同しない |
| DDR情報保存 | DDR_TRAINING_SAVE_RESTOREを無効化 | 最終.configでも無効を確認 |
| 起動環境 | UFSからEFIを起動する既定bootcmd | 試験ではbootcmdを空にし、UARTプロンプトで停止 |

参照コミット：[OpenSBI同梱7032dfe](https://github.com/ganboing/u-boot-k3/commit/7032dfed946333159f6bd570187b3ee8efbe68d2)、[BOARDのenv読込み抑止52086a9](https://github.com/ganboing/u-boot-k3/commit/52086a93c90e2719e0ecd00d3d6e4754463eccf4)、[DDR保存無効化2cc4bc3](https://github.com/ganboing/u-boot-k3/commit/2cc4bc3f4989dacac1d75cdf10c787d01c67227e)、[EFI用環境329f4fb](https://github.com/ganboing/u-boot-k3/commit/329f4fbeb38761e7c1f0730ceb1c69ce5ea8081a)。EFI環境変更が今回のUIC_ERRORを直すという証拠はない。

既存packagerでもESOSは同梱している。同梱の有無と、FSBLがELFをremoteprocへロードして実際に開始したかは別の確認事項である。参照combine-esos.shはdescription一致で構成を探すため、`ESOS Dual Core Configuration`というdescriptionのconf_dualはk3-pico-itxに一致しない。コピーされたimagesが起動対象にならないまま終了する可能性があるため、そのまま使用しない。

参照記事の実機例はCOM260系で、現在のユーザーのFSBL/U-Boot（2026-04-30）とも版が異なる。Pico用DT、SPLのDDR設定、JTAG設定、ESOSとOpenSBIのRPMI ABIは実機投入前にレビューする。固定ソースのPico用DTを使用するが、これだけでJupiter2との互換性を保証しない。特に`arch/riscv/dts/k3_spl.dts`の`spacemit,enable-debug-jtag`とDDRテーブルを確認する。別ボードの容量表示を合わせるためにDDR値を書き換えない。

## 3. 実装する開発手順

1. 固定コミットを新規作業ディレクトリへ取得する。既存のoriginal/とreleaseは変更しない。
2. 販売元OpenSBI BINを固定ソースのITSが参照する場所へコピーする。まず販売元版で検証する。
3. k3_defconfigへ試験用設定（bootcmd空、bootdelay=-1、DDR情報保存とFSBL更新の無効化、永続envの読込み停止）を適用する。ボード側のUSB起動分岐もbootcmd/bootdelayを上書きするため、同じ停止設定へ変更する。ソース差分と入力ハッシュを保存する。
4. 同一作業ツリー内でFSBLとU-Bootをビルドする。ベンダーconfig.mkがsrctreeを直接参照するため、この処理でO=による分離ビルドを使わない。
5. 最終.config、FSBLサイズとAIHDヘッダー、conf_11、組込みOpenSBIの内容を検査する。ESOSを明示構成で追加してFITを生成する。
6. ホスト検査合格後、[実機テスト手順](jupiter2-reference-ram-boot-tests.md)でUFS列挙を確認する。成功前にLinux起動やKeystoneへ進まない。
7. 販売元版が成功したら同じソース・ESOS・設定でOpenSBIだけをKeystone版に変えて再ビルドし、入力manifestを比較する。

スクリプトはPCでのビルドと梱包を行う。fastboot実行、NOR書込み、実機設定変更は行わない。公開ソース内の開発用鍵を使用する非secure-boot評価向けであり、鍵を信頼する製品用イメージではない。

## 4. 開発PCの準備と実行

Linux開発PCのpublicリポジトリのルートで実行する。Ubuntu/Debianのホスト依存例：

```bash
sudo apt-get update
sudo apt-get install git build-essential python3 python3-dev python3-setuptools \
  bison flex swig libssl-dev libgnutls28-dev libncurses-dev \
  device-tree-compiler u-boot-tools lzop openssl bc
```

別途、SpacemiTがK3向けに提供するRISC-V GCCツールチェーンを導入し、そのbinをPATHへ追加する。`CROSS_COMPILE`はインストールした実際のprefixを指定する。以下はriscv64-unknown-linux-gnu-という名前のツールチェーンの例である。ホスト依存パッケージの導入だけではクロスコンパイラーは入らない。

```bash
export CROSS_COMPILE=riscv64-unknown-linux-gnu-
"${CROSS_COMPILE}gcc" --version
"${CROSS_COMPILE}ld" --version

# 今回のSPLで報告されたUSB転送上限。NOR区画容量ではない。
SPL_DOWNLOAD_BYTES=0x20000000
# 下記は1MiB以内と確認できた場合の指定。BINサイズから推測しない。
# 確認方法は既存RAM起動手順の第7.2節。
VENDOR_SBI_RESERVE_BYTES=0x00100000

python3 scripts/build-jupiter2-reference-ram-boot.py \
  --opensbi-bin work/jupiter2-ram-boot/original/fw_dynamic.bin \
  --esos-itb work/jupiter2-ram-boot/original/esos.itb \
  --esos-configuration conf_dual \
  --variant vendor \
  --opensbi-reserve-bytes "$VENDOR_SBI_RESERVE_BYTES" \
  --max-download-bytes "$SPL_DOWNLOAD_BYTES" \
  --cross-compile "$CROSS_COMPILE" \
  --output work/jupiter2-ram-boot/reference-vendor
```

この実行で固定ソースを取得・ビルドし、成功すると`reference-vendor/release/images/FSBL.bin`と`ram-boot-vendor.itb`を作る。`source/`にソースとビルド出力、`records/`にビルドログ・設定・差分・入力ハッシュ、`release/records/`にFITの構成・ペイロードの検査記録を置く。失敗時はログと作業ツリーを残す。出力先は毎回新しいディレクトリを指定する。

先にソースと変更だけをレビューするには、同じ引数へ`--prepare-only`を加え、別のoutputを指定する。この場合はイメージを作らない。取得済みの固定コミットのローカルgitリポジトリは`--source-repository /path/to/u-boot-k3`でも指定できる。チェックアウトするコミットは変わらない。

Keystone版は`--variant keystone`、対応する`fw_dynamic.bin`、確認済みのSM版実行時領域、新しいoutputへ変更する。販売元版の合格後に実施する。

## 5. 検証の範囲

ホストでの生成・ハッシュ照合はFSBLのDDR初期化、ESOS実行、RPMIのABI、UFS通信の成功を保証しない。実機の判定・ログ採取と失敗時の復帰は別紙に記載する。NOR書込みがないことも、DDR保存設定を無効化しただけでは保証せず、実機ログで確認する。
