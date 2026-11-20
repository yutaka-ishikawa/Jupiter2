# Milk-V Jupiter2：OpenSBI＋Keystone SMをRAMブートで確認する手順と実施計画

作成日：2026-11-20。状態：**レビュー用の実施計画。統合FITの作成とJupiter2実機での起動は未検証。**

## 1. 目的と到達点

NORのOpenSBI区画を書き換える前に、開発PCからUSB fastbootでファームウェアをRAMへ送り、開発したOpenSBI＋Keystone SMとLinuxの動作を確認する。

最初に販売元OpenSBIでRAM起動の経路を確認し、その後OpenSBI部分だけを開発版へ差し替える。Linuxは既に導入したカーネルを使用し、起動方法の問題とSMの問題を切り分ける。

本書の作成段階では、ソース改修、ビルド、実機操作は実施していない。コマンドは実施予定を具体化するためのもので、各段階の開始条件を満たしてから実行する。特に第6章の互換性確認が完了するまでは、第8章の統合FIT転送へ進まない。

RAM起動では384 KiBのopensbi区画に統合FIT全体を収める必要はない。制約はFSBLの転送上限、RAM配置、ロード時の重なりである。NORへ正式導入する場合の容量確認は、従来の[スタック導入手順](milkv-jupiter2-stack-install.md)に従う。

## 2. 公開資料から分かったこと

| 資料 | 内容と適用範囲 |
| --- | --- |
| [Milk-V公式Quick Start](https://milkv.io/docs/jupiter2/getting-started/quick-start) | K3 Pico-ITXの販売元資料を案内している。 |
| [K3 Pico-ITX User Guide](https://cdn-resource.spacemit.com/file/product/K3/k3_pico_ug_en.pdf) | V1.4、2026-11-06版。第3.1節にFDL、RST、DRD Type-C接続、書込み方法がある。新OpenSBIのRAM試験の具体的手順は確認できない。 |
| [SpacemiT Boot Development Guide](https://github.com/spacemit-com/docs-buildroot/blob/main/en/k3_buildroot/device/boot.md) | FSBL、U-Bootをstageして書込み用fastboot環境を起動する公式手順。OpenSBI更新はflashで説明されている。 |
| [Milk-Vコミュニティ投稿](https://community.milkv.io/t/jupiter-2-bootrom-and-booting-over-uart/3978/11) | ファームウェア開発者向けのRAM起動ガイドへの案内。公式保証された手順ではない。 |
| [K3 Firmware Hacking and JTAG](https://github.com/ganboing/K3-Docs/blob/master/hacking/README.md) | 改修版U-BootでOpenSBIをFITへ含め、ESOSも合成してstageする手順。掲載ログはk3_com260_ifxで、OpenSBI→S-mode U-Boot→GRUBまで進んでいる。Jupiter2での本スタックの合格記録ではない。 |
| [改修版U-Boot](https://github.com/ganboing/u-boot-k3)・[ESOS合成スクリプト](https://github.com/ganboing/u-boot-k3/blob/k3-ganboing/scripts/combine-esos.sh) | 比較・移植の候補。使用前にコミットを固定し、販売元版との差分を確認する。 |

公開ガイドのソースとバイナリーを無条件に採用せず、Jupiter2のボード判定、DDR初期化、起動経路に関わる差分を確認する。参照先のブランチは更新されるため、実施時には参照コミットも記録する。

## 3. 今回の実機で確認済みの情報

| 項目 | 確認済みの内容 |
| --- | --- |
| OS | Bianbu 4.0.4、U-Bootから直接Linuxを起動する構成 |
| 販売元FSBL／U-Boot | UART表示は2022.10、2026-04-30ビルド |
| fastboot serial | PCのfastboot devicesで各段階の実測値を確認する。BootROM段階ではserialが未設定の場合がある |
| U-Bootのボード表示 | spacemit k3 pico itx board |
| opensbi区画 | mtd5、0x60000＝393216 bytes＝384 KiB |
| 新Linux | /boot/Image-6.18.3-keystone。modulesのreleaseは6.18.3。起動とネットワーク接続は確認済み |

ユーザー提供のdumpimage出力による販売元u-boot.itbの内容は次のとおり。

| 要素 | 内容 |
| --- | --- |
| Image 0 | U-Boot、1326784 bytes、load＝0x102000000、entry表示なし |
| Image 11 | fdt_11＝k3-pico-itx.dtb、60706 bytes |
| conf_11 | description＝k3-pico-itx、FDT＝fdt_11、loadables＝uboot |
| デフォルト | conf_3＝k3_deb1 |
| OpenSBI | 収録されていない |
| ESOS | 収録されていない |

conf_11が実機のModel表示に対応する候補である。ただしFSBLがEEPROM等から構成を選ぶ可能性があるため、defaultのconf_3を理由に即座に変更しない。実際に選択された構成をUARTとソースで確認する。

## 4. 起動構成とRAM転送の意味

```text
BootROM：FDLでUSBダウンロード待機
  ↓ stage FSBL.bin → continue
FSBL（U-Boot SPL）：DDR初期化、FITの受信・展開、OpenSBIへの引渡し
  ↓ stage ram-boot-vendor.itb または ram-boot-keystone.itb → continue
RAM上の統合FIT
  ├── OpenSBI（販売元版、次に開発版＋SM）
  ├── S-modeで動くU-Boot
  ├── Jupiter2用DTB
  └── 対応するESOS等の追加ファームウェア
  ↓ OpenSBI → U-Boot → Linux
```

stageはRAMへの転送であり、単独では起動を意味しない。FSBLのcontinueは受信FITを使う次段起動につながる。一方、起動済みU-Bootのfastbootへ後からfw_dynamic.itbをstageし、continueしても、新OpenSBIへの引渡し処理にはならない。

OpenSBIにはDTBと、次に実行するU-Bootのアドレス・実行モード等の引渡し情報が必要である。単独ITBの転送、任意アドレスへのgo、fastboot bootへの置換を推測で行わない。

本書のram-boot-*.itbは今後作る統合FITの名称である。既存bundle/firmware/fw_dynamic.itbとは別物で、既存のインストールイメージ作成スクリプトがこれを生成するわけではない。

## 5. 開発PCでの準備と成果物の配置

Ubuntu／Debian系PCの例。PC用ツールを実機へコピーする必要はない。

```bash
sudo apt update
sudo apt install fastboot u-boot-tools device-tree-compiler git \
  build-essential python3 bc bison flex libssl-dev dpkg-dev picocom
mkdir -p work/jupiter2-ram-boot/{original,source,build,images,records,logs}
```

上記は転送・解析用と一般的なビルド依存である。クロスコンパイラー、DDRライブラリー、FSBL包装用ツール等は、採用するSDK・コミットの要件を第6章で確定して追加する。汎用コンパイラーだけで販売元FSBLを再現できるとは扱わない。

```text
work/jupiter2-ram-boot/
├── original/     販売元FSBL.bin、u-boot.itb、OpenSBI、ESOS、入手元の記録
├── source/       固定コミットのソース
├── build/        販売元版と開発版を分けたビルド出力
├── images/       確認済みFSBL.bin、ram-boot-vendor.itb、ram-boot-keystone.itb
├── records/      SHA-256、FIT一覧、DT情報、コンパイラー版、差分、判定結果
└── logs/         各段階のUARTログとPC側fastbootログ
```

originalには使用した配布パッケージ名、URL、版、取得日を残し、ファイルのSHA-256を記録する。販売元FSBLとU-Bootは既存Keystone bundleには含まれていない。OpenSBIとESOSは実機の販売元構成に対応した配布物から用意する。別ボードや最新版のファイルを無条件に混ぜない。

解析用には、販売元u-boot.itbから次のように抽出できる。これはPC上のファイル操作だけである。これらを抽出するだけで統合FITが完成するわけではない。

```bash
cd work/jupiter2-ram-boot
dumpimage -l original/u-boot.itb > records/vendor-uboot-fit.txt
dumpimage -T flat_dt -p 0 -o build/vendor-u-boot.bin original/u-boot.itb
dumpimage -T flat_dt -p 11 -o build/k3-pico-itx.dtb original/u-boot.itb
```

fw_dynamic.binは統合FITへ格納する実行バイナリーの候補、fw_dynamic.elfはシンボル・配置の解析用として保存する。ELFをfastbootで送る予定ではない。単独fw_dynamic.itbはNOR用成果物として区別して保存する。

## 6. 段階A：ソース差分と互換性を確認する

この段階は開発PCで行う。成果物は差分の一覧、採用コミット、ビルド条件、RAM配置表である。

1. 販売元SDKと改修版U-Bootの由来・基点を確認し、それぞれのコミットを固定する。
2. SPLのfastboot受信、FIT展開、OpenSBI起動処理を比較する。販売元4月版FSBLをそのまま使えるか、改修版FSBLが必要かを判断する。公開例のFSBLも改修版なので、販売元版の互換性は未確認である。
3. OpenSBIをFITのfirmware、U-Boot等をloadablesとして扱う方法と、fw_dynamic_info、DTB、次段アドレスの受渡しを確認する。
4. U-BootのS-mode設定、ボード選択、通常起動と書込み専用fastbootへの分岐を確認する。
5. ESOSのボード別構成、ロード先、起動・初期化処理、OpenSBIとのインターフェースを確認する。公開合成スクリプトはdescriptionが一致する構成へloadablesを追加するため、k3-pico-itxにESOSが追加されたことを必ず確認する。
6. 各imageのload／entry、サイズ、DTB、展開バッファー、OpenSBIの実行時領域、SM予約領域の重複を調べる。OpenSBI候補の先頭は0x100000000、販売元U-Bootのloadは0x102000000だが、採用ソースと実際のリンク結果を優先する。
7. DDR情報、環境変数、EEPROM等への自動保存を調べ、RAM試験用ビルドで停止する方法を確定する。変更箇所を差分として残す。

実機の以前のログには、販売元U-Bootによる次のNOR書込みがある。

```text
save DDR training info
write 38912 byte to spinor @offset 65536
```

**stageを使っても、起動したソフトウェアがNORへ自動保存する場合がある。NORを変更しない試験にするには、この自動保存経路を事前に止める。** 過去の書込みの有無はstageコマンドの説明だけでは判断できない。

採用条件：Jupiter2用構成、必要な追加ファームウェア、引渡し方法、RAM配置、転送上限、自動保存停止方法が説明できること。未確定なら実機転送へ進まず、結果をrecordsへ残す。

## 7. 段階B：販売元OpenSBIで統合FITを作成・検査する

まずSMを含めず、対応する販売元OpenSBI＋U-Boot＋DTB＋ESOSの組合せを作る。必要な修正は段階Aの差分に限定する。

公開ガイドのmake k3_defconfig allやOpenSBIのリンク指定は参考情報であり、そのまま本リポジトリの確定手順にはしない。特にfw_dynamic.binの場所は実際のビルド出力で確認する。クロス環境での正確なビルドコマンド、必要なFSBL包装処理、採用ツール版は、段階A完了後に本章へ追記する。

予定成果物は次のとおり。

| ファイル | 内容 |
| --- | --- |
| images/FSBL.bin | Jupiter2のDDR初期化と統合FIT起動に適合すると確認したFSBL |
| images/ram-boot-vendor.itb | 販売元OpenSBIを含むRAM起動用統合FIT |
| records/vendor-build.txt | 全入力コミット、バイナリーの出典とSHA-256、設定、ツール版、実行コマンド |
| records/vendor-memory-map.txt | 転送・展開時と実行時の領域、重複がない根拠 |

PC上でdumpimage -l、FITのDT解析、必要なimageの抽出・ハッシュ比較を行い、Jupiter2用構成がOpenSBI、U-Boot、DTB、ESOSを参照していることを確認する。スクリプトの終了コードだけで合格としない。S-mode引渡しはFIT一覧だけでなく、SPLソースと実機ログでも確認する。

## 8. 段階C：販売元OpenSBIをRAM起動する

### 8.1 開始前

段階A・Bが合格していること。UARTは[UART接続手順](milkv-jupiter2-uart.md)に従って開き、ログ保存を開始する。実機の現状とバックアップは[スタック導入手順の第5章](milkv-jupiter2-stack-install.md#5-実機の現状記録とバックアップ)に従う。

**バックアップ作成後は、そのディレクトリ全体を実機外の作業PCにもコピーする。**

Linux起動に進むとOSは通常のファイルシステムへ書き込む。RAM試験の目的はファームウェアを恒久更新せず確認することであり、OSを含めた全ストレージへの完全無書込み試験とは区別する。

### 8.2 FDLとFSBL

1. UARTログを保存した状態でFDLを押しながらRSTを短く押し、FDLを離す。
2. データ通信対応USBケーブルでDRD Type-CとPCを接続する。実機の電源は別途供給する。
3. PCで次を実行する。以下の相対パスはwork/jupiter2-ram-bootを作業ディレクトリとする。

```bash
sudo fastboot devices
sudo fastboot stage images/FSBL.bin
sudo fastboot continue
```

BootROM段階のserialは未設定の場合がある。複数のfastboot機器を接続しない。UARTでFSBLの起動、DDR初期化完了を確認し、PCで再度fastboot devicesを実行する。固定秒数待つだけで次へ進まない。

### 8.3 統合FIT

再認識された実機のserialをfastboot devicesで確認し、入力する。機器固有番号は本書へ掲載しない。

```bash
sudo fastboot devices
read -r -p 'fastboot devicesで確認したserial: ' FASTBOOT_SERIAL
sudo fastboot -s "$FASTBOOT_SERIAL" stage images/ram-boot-vendor.itb
sudo fastboot -s "$FASTBOOT_SERIAL" continue
```

公開例にはoem speed:super-speedもあるが、本手順では必須としない。今回のバイナリーではOEM環境変数操作が未対応だったため、別のOEM命令の有効性も推測しない。

UARTで選択構成、OpenSBIの版・起動表示、Next Address、Next Mode＝S-mode、U-Bootの起動を確認する。Linuxへ進む前にUARTからautobootを停止し、バージョンと起動設定を確認する。

```text
version
printenv bootcmd knl_name ramdisk_name dtb_dir
```

U-Bootが書込み用fastbootの待機に入った場合は合格とせず、ログを保存して段階Aへ戻る。未確認のOEM命令で通常起動へ切り替えない。

### 8.4 Linuxの起動と合格条件

販売元OpenSBIで既存の通常起動を確認した後、既に配置済みの新カーネルを一時指定して確認する。initrdの存在とDTBの適合性を事前確認する。今回の例は次のとおり。

```text
setenv knl_name Image-6.18.3-keystone
setenv ramdisk_name initrd.img-6.18.3
setenv dtb_dir spacemit/6.18.3-generic
printenv knl_name ramdisk_name dtb_dir
```

dtb_dirは既存DTBを継続利用する場合の例であり、6.18.3というmodules名からDTBのディレクトリを推測して作らない。FITに入れるU-Boot用DTBと、このLinux用DTBの指定は別である。initrd生成とbootcmdがenv_k3.txtを再読込する場合の対応は、[スタック導入手順の第6・7章](milkv-jupiter2-stack-install.md#6-新linuxとアプリを追加配置する)で確認する。bootcmdの再読込により一時設定が上書きされない起動経路を確定してからLinuxを起動する。

本試験ではenv_k3.txtを編集せず、saveenvも実行しない。

合格条件は、販売元OpenSBI経由のS-mode U-Boot、実機に合ったDTB、Linuxログイン、期待したuname -r、必要なCPUのオンライン状態、ストレージ・ネットワークの動作、自動NOR保存が発生しないこと。外部公開例の16 HART等を実機の期待値に転記せず、通常起動の記録と比較する。販売元OpenSBI段階ではEnclaveの動作合格を要求しない。

## 9. 段階D：開発したOpenSBI＋SMへ差し替える

段階Cが合格してから実施する。

1. 本リポジトリの[スタック導入手順の第3章](milkv-jupiter2-stack-install.md#3-開発ホストで候補をビルドする)に従いOpenSBI＋SMを作り、BIN、ELF、設定とビルド記録を保存する。
2. 実K3の初期化、必要なSBI、ESOSとの連携、SMのPMP・予約領域について販売元版との差分を確認する。QEMU向け設定のビルド成功を実機互換性の根拠にしない。
3. 段階Bと同じU-Boot、DTB、ESOS、FSBLを使い、OpenSBI部分だけを差し替えてimages/ram-boot-keystone.itbを作る。変更したOpenSBIの実行時領域を含めてRAM配置を再検査する。
4. 段階Cと同じFDL手順を最初から行い、最後に転送するFITだけをram-boot-keystone.itbへ変える。起動済みU-Bootへ単独OpenSBIを追加転送する方法は使わない。
5. UARTで開発版OpenSBIとSMの識別、初期化、S-modeへの移行を確認する。同じ新Linuxを起動し、kernelログ、CPU、ネットワーク等を販売元版と比較する。
6. 正確に対応するdriver、runtime、アプリを確認してから同梱hello二種を実行する。展開済みbundleを作業ディレクトリとしてsudo bash tools/run-hello.shを使用する。失敗した場合はログを残して中止する。
7. 必要な実機検証を行う。ホストでのコンパイル、FITの生成、OpenSBIのバナー表示だけでEnclaveの動作を合格にしない。

## 10. 失敗時の停止・復帰方法

| 失敗した段階 | 対応 |
| --- | --- |
| PCのビルド・FIT検査 | 実機へ転送せず、入力と差分を修正する。 |
| BootROMでUSBが出ない | 電源、FDL操作、DRDポート、データケーブル、PCのUSB認識を確認する。 |
| FSBLでDDR初期化に失敗 | ログを保存して電源を切り、対応が確認済みのFSBLへ戻す。別ボード用DDR設定を試行しない。 |
| 統合FIT展開・OpenSBIで停止 | 保存した正常FITと比較する。ロード先、選択構成、ESOS、引渡し情報を調べる。 |
| U-Bootで停止／fastboot待機のまま | U-Bootのモードと起動分岐を段階Aで見直す。NOR更新で解決しようとしない。 |
| Linuxが起動しない | 一時指定したkernel、initrd、Linux用DTBとログを確認する。SM版ならまず販売元OpenSBIの統合FITへ戻して比較する。 |
| SM／Enclaveで失敗 | 新たなEnclave実行を中止し、ログ保存後に販売元OpenSBIの統合FITまたは通常起動へ戻す。 |

UARTが応答しない場合は、ログを保存し、電源を切る。FDLを押さずに通常電源投入すれば、永続ファームウェアと起動設定を変更していない条件では元の起動経路へ戻る。USBダウンロード待機へ戻る場合はFDLボタンの状態等を確認する。

これはRAM上の試験内容を破棄する復帰であり、NORへ書き込まれたデータの復元ではない。自動保存等の書込みが観測された場合は、その箇所を特定する。元のOpenSBI区画のバックアップだけでDDR情報等も戻せるとは扱わない。恒久変更が必要になった場合の復旧は、別の[スタック導入手順の第10章](milkv-jupiter2-stack-install.md#10-復旧と正式採用)に従う。

本書の実行手順にはfastboot flash、erase、saveenv、sf write、flashcp、env_k3.txtの編集を含めない。

## 11. 各段階で残す記録と次の作業

| 段階 | レビューする記録 | 次へ進める条件 |
| --- | --- | --- |
| A：互換性調査 | 固定コミット、ソース差分、構成選択、FSBLの採否、RAM配置、自動保存停止方法 | 起動に必要な変更と条件が確定 |
| B：販売元版FIT | ビルド記録、入力と出力のSHA-256、FIT一覧、image抽出比較 | 正しいボード構成と全image参照、配置、転送上限を確認 |
| C：販売元版RAM起動 | PCログ、全UARTログ、Linux状態、通常起動との差分 | 新OpenSBIへ差し替える前にRAM起動経路が動作 |
| D：OpenSBI＋SM | 同じ記録とSM初期化・hello等の実行結果 | 実機の基本機能と必要なEnclave動作を確認 |

次に行う作業は段階Aのソース比較である。その結果を基に、実際に使うFSBL、ビルドコマンド、FIT生成方法を確定し、本書の第6・7章を更新する。現時点で実機試験は未実施で、RAMブートの成功やNORへの無書込みを検証済みとはしていない。
