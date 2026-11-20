# Milk-V Jupiter2：OpenSBI＋Keystone SMをRAMブートで確認する手順と実施計画

更新日：2026-11-20。状態：**統合FIT作成スクリプトを実装し、ホスト上で検査済み。販売元バイナリーとの実際の組合せとJupiter2実機での起動は未検証。**

## 1. 目的と到達点

NORのOpenSBI区画を書き換える前に、開発PCからUSB fastbootでファームウェアをRAMへ送り、開発したOpenSBI＋Keystone SMとLinuxの動作を確認する。

最初に販売元OpenSBIでRAM起動の経路を確認し、その後OpenSBI部分だけを開発版へ差し替える。Linuxは既に導入したカーネルを使用し、起動方法の問題とSMの問題を切り分ける。

本書では統合FITの作成ツールと、実機確認までの計画を示す。FSBL／U-Bootの互換性改修、販売元ファームウェアでの実ビルド、実機操作は実施していない。コマンドは実施予定を具体化するためのもので、各段階の開始条件を満たしてから実行する。特に第6章の互換性確認が完了するまでは、第8章の統合FIT転送へ進まない。

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

本書のram-boot-*.itbは、[build-jupiter2-ram-boot-image.py](../scripts/build-jupiter2-ram-boot-image.py)が生成する統合FITである。既存bundle/firmware/fw_dynamic.itbとは別物で、インストール用のbuild-jupiter2-install-image.pyでは生成しない。RAM用スクリプトもファームウェアのコンパイルや実機転送は行わない。

## 5. 開発PCでの準備と成果物の配置

**本書のbuild-jupiter2-ram-boot-image.pyは開発PCで実行する。Jupiter2実機では実行しない。** publicリポジトリ、入力ファイルを置くwork/jupiter2-ram-boot/original、生成先も開発PC上のディレクトリである。

| 操作 | 実行する場所 |
| --- | --- |
| ファームウェアのビルド、統合FIT生成、dumpimage・sha256sumによる生成物確認 | 開発PCのターミナル |
| fastboot devices／stage／continue／getvar | 開発PCのターミナル。USB経由でJupiter2実機と通信する。 |
| U-Bootのversion／printenv／setenv、Linuxの起動・動作確認 | Jupiter2実機。U-Boot操作は開発PCのUART端末から入力する。 |

生成スクリプト自体は実機との接続を必要としない。ただし、引数に指定する転送上限や実行時領域の値は事前に確認する。生成後、第8章で開発PCからイメージを転送し、実機で起動する。

Ubuntu／Debian系PCの例。PC用ツールを実機へコピーする必要はない。

```bash
sudo apt update
sudo apt install fastboot u-boot-tools device-tree-compiler git \
  build-essential python3 bc bison flex libssl-dev dpkg-dev picocom
mkdir -p work/jupiter2-ram-boot/{original,source,build,records,logs}
```

上記は転送・解析用と一般的なビルド依存である。クロスコンパイラー、DDRライブラリー、FSBL包装用ツール等は、採用するSDK・コミットの要件を第6章で確定して追加する。汎用コンパイラーだけで販売元FSBLを再現できるとは扱わない。

```text
work/jupiter2-ram-boot/
├── original/     販売元FSBL.bin、u-boot.itb、OpenSBI、ESOS、入手元の記録
├── source/       固定コミットのソース
├── build/        販売元版と開発版を分けたビルド出力
├── vendor-release/    スクリプトが作る販売元版（images/とrecords/）
├── keystone-release/  スクリプトが作るSM版（images/とrecords/）
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

### 7.1 スクリプトに渡す入力

リポジトリのルートから実行する。必要なものは、ビルド済みの次の4ファイルである。original内の名前は、対応を確認した配布物から手動配置する。

| オプション | 入力 |
| --- | --- |
| --fsbl | 選定済みFSBL.bin。コピーするだけで、互換性・包装・DDR設定は変更しない。 |
| --uboot-itb | U-Boot＋DTBを含む販売元形式FIT。今回のconf_11のようにloadablesがU-Boot一つの構成。S-mode起動に必要な改修がある場合は、そのビルド済みFIT。 |
| --esos-itb | 同じボードに対応するESOS FIT。選択構成はdescriptionが--boardと完全一致するものを一つだけ採用する。 |
| --opensbi-bin | 生のfw_dynamic.bin。販売元のfw_dynamic.itbから抽出したBIN、次に開発版＋SMのBINを渡す。ELFやITB自体は渡さない。 |

--configuration conf_11と--board k3-pico-itxを明示する。U-Boot構成のdescriptionが一致しなければ停止する。出力には選択した構成だけを残し、defaultも同じ構成にする。元FITは変更しない。

ESOSの全loadablesをハッシュ検査後に取り込み、名前の衝突を避けて参照を付け直す。OpenSBIをfirmware、U-BootとESOSをloadablesに指定する。U-Bootにosがない場合はu-bootを設定し、entryがなければ元のloadを設定する。これによってバイナリー自体がS-mode用に変換されるわけではない。

対応範囲は署名・暗号化のないFIT、非圧縮の選択image、CRC32／SHA-1／SHA-256／SHA-384／SHA-512の入力ハッシュである。inline dataとexternal dataの両方を取り込める。未知の形式、ハッシュ不一致、ESOSボード不一致等では、完成出力を残さず停止する。

### 販売元がfw_dynamic.itbだけを配布している場合

**販売元のfw_dynamic.binを別途入手する必要はない。配布されているfw_dynamic.itbからOpenSBIのBINを抽出して使用する。** 以下はすべて開発PCでのファイル操作であり、実機への転送・書込みは行わない。

まず、対応する販売元のfw_dynamic.itbをwork/jupiter2-ram-boot/original/fw_dynamic.itbとして配置し、リポジトリのルートで内容を確認する。

```bash
dumpimage -l work/jupiter2-ram-boot/original/fw_dynamic.itb
```

Image 0がOpenSBIのfirmwareで、Compressionがuncompressedであることを確認した場合、次で格納データを取り出す。**-p 0はImage 0を意味する。** 実際のOpenSBIが別のImage番号なら、その番号を指定する。fw_dynamic.itbの名前だけで中身や番号を決めない。

```bash
# 開発PCのターミナルで、publicリポジトリのルートから実行する
dumpimage -T flat_dt -p 0 \
  -o work/jupiter2-ram-boot/original/fw_dynamic.bin \
  work/jupiter2-ram-boot/original/fw_dynamic.itb
```

-T flat_dtはFITのコンテナー形式を指定し、-oには抽出する生BINの保存先を指定する。単に拡張子を変更する操作ではない。Imageのload／entryも一覧で確認し、本スクリプトのOpenSBIロード先（既定0x100000000）と合うことを確認する。異なる場合は段階Aで配置を見直し、必要に応じて--opensbi-loadへ確認したアドレスを指定する。圧縮されている場合は、この抽出例をそのまま使わず、展開方法を確認する。

抽出後は元ITBも残し、入手元の記録とともに両方のSHA-256を保存する。

```bash
mkdir -p work/jupiter2-ram-boot/records
sha256sum \
  work/jupiter2-ram-boot/original/fw_dynamic.itb \
  work/jupiter2-ram-boot/original/fw_dynamic.bin \
  > work/jupiter2-ram-boot/records/vendor-opensbi-files.sha256
```

以後の--opensbi-binには、この抽出で作成したfw_dynamic.binを指定する。--opensbi-reserve-bytesはBINのサイズだけでは確定できない。販売元の対応ソース、ELF／mapが入手できる場合はその配置情報等を確認する。ITBからBINを抽出できたことだけで実行時領域の確認済みとは扱わない。

### 7.2 転送上限とOpenSBI実行時領域を確認する

スクリプトへ次の二つの値を必ず渡す。NOR容量393216を転送上限として流用しない。

- --max-download-bytes：**SPL段階**のfastboot受信バッファーの容量。使用するFSBLの設定と照合する。第8.2節で選定済みFSBLをRAM起動した後、PCから下記のgetvarで確認できる場合がある。BootROM段階の値と区別する。取得できない場合は採用FSBLのソース・設定から確認する。
- --opensbi-reserve-bytes：OpenSBIのloadから必要な実行時領域末尾までのサイズ。BINのファイル長ではなく、ELFの配置、BSS、heap、scratch等を含めて段階Aで確定する。SM版では改めて求める。

#### FDL起動からSPLの受信容量を問い合わせるまで

**実機をFDLボタンを押しながら起動し、FSBLをRAMへ転送・起動した後、開発PCから容量を問い合わせる。u-boot.itbを転送する前に行う。** この確認では統合FITはまだ不要で、第6章で選定したFSBL.binを使う。

1. 開発PCでUART端末を開き、実機のログを保存する。
2. 実機の電源が切れている場合は、FDLボタンを押したまま電源を投入し、その後FDLを離す。既に給電している場合は、FDLを押したままRSTを短く押してからFDLを離す。
3. データ通信対応USBケーブルで、実機のDRD Type-Cポートと開発PCを接続する。実機への電源は別途供給する。
4. **開発PCのターミナルで、publicリポジトリのルートから**次を実行する。

```bash
sudo fastboot devices
sudo fastboot stage work/jupiter2-ram-boot/original/FSBL.bin
sudo fastboot continue
```

最初のfastboot devicesでは、機器が認識されていることを確認する。この時点はBootROM側のfastbootであり、まだ今回調べたいSPLの容量を問い合わせない。FSBL.binのstageはRAMへの転送で、flashコマンドは使用しない。

5. UARTでU-Boot SPLの起動とDDR初期化完了を確認する。USBが再認識されるまで待ち、開発PCで次を実行する。

```bash
sudo fastboot devices
```

例えば次のように表示された場合、左側のEXAMPLE123がserialである。これは説明用の架空の番号なので、実際の表示へ置き換える。

```text
EXAMPLE123    fastboot
```

6. 開発PCで、そのserialを-sに指定して問い合わせる。readで変数へ保存する必要はなく、直接指定してよい。

```bash
sudo fastboot -s EXAMPLE123 getvar max-download-size
```

例えば次の出力なら、SPLが報告した受信容量は0x01000000（16 MiB）である。この数値は出力例であり、実機の確認値ではない。

```text
max-download-size: 0x01000000
```

この場合、イメージ生成スクリプトには--max-download-bytes 0x01000000を指定する。実際に異なる値が出た場合は、その値を使い、採用FSBLの設定とも照合する。

**FDL直後はBootROM、FSBL起動後はSPL、u-boot.itb起動後はU-Bootのfastbootになる。今回必要なのはFSBL起動後・u-boot.itb転送前の値である。** getvarは容量の問合せであり、ファームウェアを取り出す操作ではない。未対応エラーが出た場合は、他段階の値で代用せず、FSBLのソース・設定から受信容量を確認する。

確認だけで終了する場合は、ログを保存して電源を切り、FDLを押さずに通常起動する。永続領域を変更していない条件では元の起動経路へ戻る。FSBL自体の自動保存等の確認は第6章の条件を引き続き適用する。

これらの確認値を入力する実行例を以下に示す。0xから始まる16進数、または10進数を入力できる。未確認の値を仮置きして実機へ進めない。

### 7.3 販売元OpenSBIを含むイメージを生成する

```bash
# 開発PCのターミナルで、publicリポジトリのルートから実行する
read -r -p '確認済みSPL転送上限(bytes): ' SPL_DOWNLOAD_BYTES
read -r -p '確認済み販売元OpenSBI実行時領域(bytes): ' VENDOR_SBI_RESERVE_BYTES

python3 scripts/build-jupiter2-ram-boot-image.py \
  --fsbl work/jupiter2-ram-boot/original/FSBL.bin \
  --uboot-itb work/jupiter2-ram-boot/original/u-boot.itb \
  --esos-itb work/jupiter2-ram-boot/original/esos.itb \
  --opensbi-bin work/jupiter2-ram-boot/original/fw_dynamic.bin \
  --configuration conf_11 \
  --board k3-pico-itx \
  --variant vendor \
  --opensbi-reserve-bytes "$VENDOR_SBI_RESERVE_BYTES" \
  --max-download-bytes "$SPL_DOWNLOAD_BYTES" \
  --output work/jupiter2-ram-boot/vendor-release
```

**このコマンドの成功によって、次の統合イメージとFSBLのコピーが生成される。実機への転送・flash・再起動は行われない。** --outputは未作成のディレクトリを指定する。既存出力を上書きしないため、再生成時は別名を使う。

```text
work/jupiter2-ram-boot/vendor-release/
├── images/
│   ├── FSBL.bin
│   └── ram-boot-vendor.itb
└── records/
    ├── manifest.json
    ├── fit-list.txt
    ├── mkimage.txt
    ├── ram-boot.its
    ├── payload-*.bin
    ├── FSBL.bin.sha256
    └── ram-boot-vendor.itb.sha256
```

manifest.jsonは入力ファイル名・SHA-256、格納payload、ボード、構成、検査対象のload領域、指定した制約、ツール版、未検証項目を記録する。入力の絶対パスや実機serialは収録しない。ram-boot.itsとpayload-*.binは生成内容を調べるための資料で、実機へ送るのはimages内の二ファイルだけである。

```bash
cd work/jupiter2-ram-boot/vendor-release
sha256sum -c records/FSBL.bin.sha256
sha256sum -c records/ram-boot-vendor.itb.sha256
cat records/fit-list.txt
```

スクリプトは各ロードイメージのファイル範囲、および指定されたOpenSBI実行時領域について重複を拒否する。最終FITを再読込し、全payloadのハッシュと元データとの一致、SPL転送上限を検査する。ただしDTBの自動配置、転送バッファー、U-Boot等のBSS・動的領域、SM予約領域、FSBL互換性、ESOS起動、NOR自動保存の有無までは証明しない。manifestのhardware_verifiedはfalseである。

ホスト側の検査は次で再実行できる。実際のmkimage、dumpimage、dtcを使用する。これはファイル生成・検査の試験であり、SBIやPMPの動作試験ではない。

```bash
python3 scripts/tests/test_jupiter2_ram_boot_image.py
```


### 7.4 数値とファイル名を直接指定する実行例

以下は対話入力やシェル変数を使わず、引数をすべて記載した例である。**販売元版・SM版ともに、開発PCのターミナルで、開発PC上のpublicリポジトリのルートから実行する。Jupiter2実機で実行するコマンドではない。**

**この例の転送上限16 MiBとOpenSBI実行時領域1 MiBは説明用の条件であり、今回の実機で確認済みの値ではない。採用するFSBLの受信容量が16 MiBであり、OpenSBIの全実行時領域が1 MiB以内であることを第6章・第7.2節で確認した場合に使用する。異なる場合は二つの数値を確認値へ変更する。** スクリプトへ数値を指定して成功しても、その数値自体の正しさや実機起動の成功を証明するものではない。

| 引数 | この例で指定する値 | 意味 |
| --- | --- | --- |
| --max-download-bytes | 0x01000000 | 16777216 bytes＝16 MiB。SPLの受信容量。 |
| --opensbi-reserve-bytes | 0x00100000 | 1048576 bytes＝1 MiB。OpenSBIのloadから確保する実行時領域。 |
| --configuration | conf_11 | 今回の販売元FITでk3-pico-itxに対応する構成。 |
| --board | k3-pico-itx | U-BootとESOSの構成descriptionに要求する値。 |

#### 販売元OpenSBI版

まずoriginalへ、対応を確認した販売元ファイルを配置する。OpenSBIは公開されているfw_dynamic.itbを置き、第7.1節の抽出手順でfw_dynamic.binを作成する。

```text
work/jupiter2-ram-boot/original/
├── FSBL.bin
├── u-boot.itb
├── esos.itb
├── fw_dynamic.itb    配布された元ITB
└── fw_dynamic.bin    元ITBから抽出して作成するBIN
```

fw_dynamic.binは販売元OpenSBIの生BINであり、上記の抽出で用意する。fw_dynamic.itbを改名して置かない。ファイルの入手元とSHA-256も別途記録する。

```bash
# 開発PCのターミナルで、publicリポジトリのルートから実行する
python3 scripts/build-jupiter2-ram-boot-image.py \
  --fsbl work/jupiter2-ram-boot/original/FSBL.bin \
  --uboot-itb work/jupiter2-ram-boot/original/u-boot.itb \
  --esos-itb work/jupiter2-ram-boot/original/esos.itb \
  --opensbi-bin work/jupiter2-ram-boot/original/fw_dynamic.bin \
  --configuration conf_11 \
  --board k3-pico-itx \
  --variant vendor \
  --opensbi-reserve-bytes 0x00100000 \
  --max-download-bytes 0x01000000 \
  --output work/jupiter2-ram-boot/vendor-release
```

**成功すると、work/jupiter2-ram-boot/vendor-release/images/ram-boot-vendor.itbが作成される。** 同じimages内にFSBL.binがコピーされ、records内に検査結果が出力される。出力先が既に存在する場合は停止するので、再生成する場合は--outputをvendor-release-02などの新しい名前へ変更する。

生成後の確認もリポジトリのルートから次のように行える。

```bash
dumpimage -l work/jupiter2-ram-boot/vendor-release/images/ram-boot-vendor.itb
(
  cd work/jupiter2-ram-boot/vendor-release
  sha256sum -c records/FSBL.bin.sha256
  sha256sum -c records/ram-boot-vendor.itb.sha256
)
```

#### 開発したOpenSBI＋SM版

同じ入力のうちOpenSBIだけを標準ビルド先の開発版へ変更する例である。**SM版についても全実行時領域が1 MiB以内であると別途確認した場合の数値例**であり、販売元版の値を無条件に流用しない。

```bash
# 開発PCのターミナルで、publicリポジトリのルートから実行する
python3 scripts/build-jupiter2-ram-boot-image.py \
  --fsbl work/jupiter2-ram-boot/original/FSBL.bin \
  --uboot-itb work/jupiter2-ram-boot/original/u-boot.itb \
  --esos-itb work/jupiter2-ram-boot/original/esos.itb \
  --opensbi-bin .build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin \
  --configuration conf_11 \
  --board k3-pico-itx \
  --variant keystone \
  --opensbi-reserve-bytes 0x00100000 \
  --max-download-bytes 0x01000000 \
  --output work/jupiter2-ram-boot/keystone-release
```

成功するとwork/jupiter2-ram-boot/keystone-release/images/ram-boot-keystone.itbが作成される。この時点で行われるのはPC上のイメージ生成と検査だけであり、実機への転送・起動は第8章・第9章の別工程で行う。

## 8. 段階C：販売元OpenSBIをRAM起動する

### 8.1 開始前

段階A・Bが合格していること。UARTは[UART接続手順](milkv-jupiter2-uart.md)に従って開き、ログ保存を開始する。実機の現状とバックアップは[スタック導入手順の第5章](milkv-jupiter2-stack-install.md#5-実機の現状記録とバックアップ)に従う。

**バックアップ作成後は、そのディレクトリ全体を実機外の作業PCにもコピーする。**

Linux起動に進むとOSは通常のファイルシステムへ書き込む。RAM試験の目的はファームウェアを恒久更新せず確認することであり、OSを含めた全ストレージへの完全無書込み試験とは区別する。

### 8.2 FDLとFSBL

1. UARTログを保存した状態でFDLを押しながらRSTを短く押し、FDLを離す。
2. データ通信対応USBケーブルでDRD Type-CとPCを接続する。実機の電源は別途供給する。
3. PCで次を実行する。以下の相対パスは生成したwork/jupiter2-ram-boot/vendor-releaseを作業ディレクトリとする。

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
3. 段階Bと同じU-Boot、DTB、ESOS、FSBLを使い、下記のコマンドでOpenSBI部分だけを差し替えてkeystone-release/images/ram-boot-keystone.itbを作る。変更したOpenSBIの実行時領域を含めてRAM配置を再検査する。
4. 段階Cと同じFDL手順を最初から行い、最後に転送するFITだけをram-boot-keystone.itbへ変える。起動済みU-Bootへ単独OpenSBIを追加転送する方法は使わない。
5. UARTで開発版OpenSBIとSMの識別、初期化、S-modeへの移行を確認する。同じ新Linuxを起動し、kernelログ、CPU、ネットワーク等を販売元版と比較する。
6. 正確に対応するdriver、runtime、アプリを確認してから同梱hello二種を実行する。展開済みbundleを作業ディレクトリとしてsudo bash tools/run-hello.shを使用する。失敗した場合はログを残して中止する。
7. 必要な実機検証を行う。ホストでのコンパイル、FITの生成、OpenSBIのバナー表示だけでEnclaveの動作を合格にしない。

### 開発版＋SMの生成例

リポジトリのルートで実行する。SPL_DOWNLOAD_BYTESは第7.3節で確認した値を使用する。OpenSBI BINのパスは標準ビルド先の例で、変更している場合は実際の出力先を指定する。

```bash
read -r -p '確認済みSM版OpenSBI実行時領域(bytes): ' KEYSTONE_SBI_RESERVE_BYTES

python3 scripts/build-jupiter2-ram-boot-image.py \
  --fsbl work/jupiter2-ram-boot/original/FSBL.bin \
  --uboot-itb work/jupiter2-ram-boot/original/u-boot.itb \
  --esos-itb work/jupiter2-ram-boot/original/esos.itb \
  --opensbi-bin .build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin \
  --configuration conf_11 \
  --board k3-pico-itx \
  --variant keystone \
  --opensbi-reserve-bytes "$KEYSTONE_SBI_RESERVE_BYTES" \
  --max-download-bytes "$SPL_DOWNLOAD_BYTES" \
  --output work/jupiter2-ram-boot/keystone-release
```

出力構成は販売元版と同じで、FIT名がram-boot-keystone.itbとなる。第8章を最初から実施する際の作業ディレクトリはkeystone-releaseにする。FSBLをstageするところから再開し、統合FITはimages/ram-boot-keystone.itbを指定する。販売元版・SM版のmanifestで、OpenSBI以外の入力SHA-256が一致していることも確認する。

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

次に行う作業は段階Aのソース比較である。その結果を基に、実際に使うFSBLと各ファームウェアのビルド条件を確定し、第7章のスクリプトへ渡す入力を用意する。現時点で実機試験は未実施で、RAMブートの成功やNORへの無書込みを検証済みとはしていない。
