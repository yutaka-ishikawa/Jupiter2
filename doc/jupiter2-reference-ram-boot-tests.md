# Jupiter2参照RAM起動: 検査と実機テスト手順

**最新の操作手順は[RAM起動ガイド](jupiter2-ram-boot-guide.md)に集約した。**
本書は各調査段階の結果と詳細な確認手順を残す。Linux起動成功後の最終到達点は第16節。
ホスト試験はscripts/tests/jupiter2-ram-boot/へ移動し、先頭コメントとREADMEに目的を記載した。

## 1. 試験対象と判定の分離

[解析・ビルド手順](jupiter2-reference-ram-boot-development.md)で作る、新しいFSBLとESOS入り統合FITを対で試験する。今回の目的は販売元OpenSBIによるUFS列挙の確立である。古いvendor-releaseのFSBLと新しい統合FITを混ぜない。ホスト検査合格と実機起動合格は別に記録する。

実機投入前に固定ソースのPico用DT、SPLのDDR/JTAG設定、ESOSとOpenSBIの版をレビューする。参照記事のCOM260での成功はJupiter2での動作確認ではない。通常起動できる既存NORとバックアップを保持する。

## 2. 開発PCの検査

publicリポジトリのルートで実行する。

```bash
python3 -m py_compile scripts/build-jupiter2-reference-ram-boot.py \
  scripts/build-jupiter2-ram-boot-image.py
python3 scripts/tests/jupiter2-ram-boot/test_fit_packaging.py
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

## 8. 参照FSBLでの停止と診断版の再試験（KSB-065）

ユーザー実機のSPL 2022.10-g4c294a06-dirty（2026-11-21 11:56:38 +0900）は、
DDR training 5623ms、memory verify pass、2191805 bytesの転送、k3-pico-itxの選択後に
次のログで止まった。OpenSBIの表示はない。

```text
k3-rproc rcpu@1: try start rproc-1 failed
unknown boot device: 13
load failed: uboot=-1 esos=-1
```

13は固定ソースのBOOT_DEVICE_BOARDである。後二行は追加FITローダーにRAM起動のcaseがないため
表示されるが、その戻り値は旧コードで無視される。これだけを停止原因とは判断しない。
core 1の同期応答待ち失敗も旧ドライバーは成功として返すため、ESOSが正常でない状態で
OpenSBIへの引渡しまで進み得る。ESOS版・DDR/DT設定・ELF配置・共有データと
キャッシュ可視性等のどれが応答失敗の原因かはまだ確定していない。

診断版はpatches/jupiter2-reference-ram-boot-diagnostics.patchを固定ソースへ適用する。
RCPU同期timeoutをエラーとして返し、SPLで停止する。展開失敗も黙って省略しない。
RAM統合FITでは追加FIT読込みを省略し、loaded U-Boot metadataとentryを必須検査する。
各coreの設定済み起動アドレスと応答状態、成功時にはOpenSBIのentry/next/DTB/hartを表示する。
source.patchへ全変更を、build-manifest.jsonへ適用パッチのSHA-256を記録する。

これは起動失敗を隠さず原因を絞る版であり、core 1の起動失敗そのものを解消したとは扱わない。
DDR、RCPUのリセット順、応答確認、PMP保護を省略して先へ進める変更ではない。

開発PCのpublicルートで、これまで確認して設定した変数を使い、新しい出力先へ再ビルドする。

```bash
git pull --ff-only
: "${VENDOR_SBI_RESERVE_BYTES:?確認済み販売元OpenSBI実行時領域を設定する}"
: "${SPL_DOWNLOAD_BYTES:?確認済みSPL転送上限を設定する}"
: "${CROSS_COMPILE:?K3クロスコンパイラーのprefixを設定する}"
OUT="$PWD/work/jupiter2-ram-boot/reference-vendor-diag-$(date +%Y%m%d-%H%M%S)"

python3 scripts/build-jupiter2-reference-ram-boot.py \
  --opensbi-bin hardware/jupiter2/vendor/fw_dynamic.bin \
  --esos-itb hardware/jupiter2/vendor/esos.itb \
  --esos-configuration conf_dual \
  --variant vendor \
  --opensbi-reserve-bytes "$VENDOR_SBI_RESERVE_BYTES" \
  --max-download-bytes "$SPL_DOWNLOAD_BYTES" \
  --cross-compile "$CROSS_COMPILE" \
  --output "$OUT"
```

ビルドが成功してから、段階4と同じ完全電源断・FDLで、今回の対を転送する。

```bash
cd "$OUT/release"
sudo fastboot devices
sudo fastboot stage images/FSBL.bin
sudo fastboot continue
# UARTでDDR完了、devicesでSPL再認識を確認してから次へ進む。
sudo fastboot devices
sudo fastboot -s HW4MPK3321280144 getvar max-download-size
# 報告された上限がFITサイズ以上であることを確認する。
stat -c '%s bytes' images/ram-boot-vendor.itb
sudo fastboot -s HW4MPK3321280144 stage images/ram-boot-vendor.itb
sudo fastboot -s HW4MPK3321280144 continue
```

再試験の判定：

- core 1の`handshake timeout`と`stop before OpenSBI`なら、意図した失敗時停止である。
  `start core=... entry=...`からの全UARTログを保存し、UFS試験へ進まない。
- 両coreが`handshake acknowledged`でも、ESOS全機能の正常性を保証しない。
  その後のOpenSBI起動、RPMI、U-Bootのログを確認する。
- `[RAMBOOT] OpenSBI entry=... next=... dtb=... hart=...`が最後なら、引渡し直前まで到達した。
  この表示だけでOpenSBI内部へ入ったとは判定しない。
- 古い`unknown boot device: 13`が出る、または新しい診断表示が一切ない場合は、
  転送したFSBL/FITとmanifestのハッシュを確認する。

診断版のパッチ適用とホスト梱包試験は開発環境で確認する。対応K3 GCCでの完全ビルド、
修正後の実機動作、実QEMU統合は未検証であり、今回の再試験で確認する。

## 9. core 0応答・core 1 timeout後のELF照合

診断版の実機結果は、core 0がhandshake acknowledged、core 1がsync=0のままtimeoutし、
ESOS rcpu1-fw failed: -110で停止した。展開後サイズはcore 0が260096、core 1が284080 bytes。
これは失敗時停止の確認であり、ESOS/RPMI/UFSの起動成功ではない。
同じpayloadアドレスは解放済みmalloc領域の再利用で、直ちに異常ではない。

entry=0xxは診断コードの%llxとSPL tiny printfの非互換（KSB-066）。%lxへ修正したが、
値がゼロだと判断して設定を書き換えない。まずホストで実ELFを確認し、この段階では再転送しない。

固定ソースarch/riscv/dts/k3_spl.dtsはcore 0のfw_boot_entry=0x100200000、
core 1は0x100800000。一方、以前のESOS一覧のrcpu1-fwはFIT load/entry=0x100804000。
FIT entryはELF内部のentryと別なので、これだけで根本原因を確定しない。

開発PCのpublicルートで実行する。今回の既知のESOS一覧ではImage 26がrcpu1-fwでLZO圧縮。
dumpimage一覧が異なる場合はその番号と圧縮方式に合わせる。

```bash
CHECK="work/jupiter2-ram-boot/records/esos-entry-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$CHECK"
dumpimage -l hardware/jupiter2/vendor/esos.itb > "$CHECK/esos-list.txt"
cat "$CHECK/esos-list.txt"
# Image 26がrcpu1-fw、Compressionがlzoであることを確認して次を実行する。
dumpimage -T flat_dt -p 26 -o "$CHECK/rcpu1-fw.lzo" \
  hardware/jupiter2/vendor/esos.itb
lzop -d -c "$CHECK/rcpu1-fw.lzo" > "$CHECK/rcpu1-fw.elf"
readelf -h -lW "$CHECK/rcpu1-fw.elf" | tee "$CHECK/rcpu1-readelf.txt"
```

Entry point addressと、各LOADのVirtAddr/PhysAddr/FileSiz/MemSiz/Flagsを保存する。
ELF entryが0x100804000なら、固定SPL DTの0x100800000と不一致である。
その場合はPT_LOADの実配置と起動条件を照合してから、DTの修正候補を作る。
一致している場合は、ESOS版との起動・共有メモリーの契約や可視性など別の原因を調べる。
いずれもtimeoutを無視してOpenSBIへ進めない。

## 10. 実ELFで確定した起動先不一致と修正後の試験（KSB-067）

ユーザー提供rcpu1-fw.elf（284080 bytes）をreadelfとビルダーで検査した。
SHA-256はedbd613a0008a97ac94f589afd7d60c770dd809ae2e4260c54fe247fa42ab4ca。

| 項目 | 確認値 |
| --- | --- |
| ELF形式 | ELF64 little-endian RISC-V EXEC |
| ELF entry | 0x100804000 |
| 実行可能LOAD | PhysAddr=VirtAddr=0x100804000、FileSiz=MemSiz=0x44000、RWE |
| resource_tableのLOAD | PhysAddr=VirtAddr=0x100e00000、FileSiz=MemSiz=0x100、RW |
| 参照SPL DTのcore 1起動先 | 0x100800000（コードの16 KiB手前） |

0x100800000から0x100803fffをロードするセグメントはこのELFにない。
ドライバーはELFをp_paddrへロードするが、開始アドレスはSPL DTから取得するため、
今回の組合せで起動先が一致していなかった。修正後のcore 1応答成功やUFS起動はまだ未確認。

ビルダーは選択したESOS FITのrcpu0-fw/rcpu1-fwを展開し、RISC-V ELF64のentryが
ファイル内の実行可能PT_LOADに含まれ、仮想・物理アドレスが同一であることを検査する。
そのentryをそれぞれのSPL DTへ反映し、ビルド後のSPL DTBにも同値があることと、
そのDTBがFSBLに含まれることを確認する。値を固定の0x100804000へ一律置換しない。
ESOS本体の変更、RCPU応答待ちの省略、NOR書込みは行わない。

開発PCで更新を取得し、第8節のビルドコマンドを新しいoutputで実行する。
例えばOUTを次のようにして、同じ引数でビルドする。

```bash
git pull --ff-only
OUT="$PWD/work/jupiter2-ram-boot/reference-vendor-entry-$(date +%Y%m%d-%H%M%S)"
```

ビルド成功後は次を確認する。

```bash
cat "$OUT/records/rcpu-elf.json"
fdtget -t x "$OUT/records/spl.dtb" /soc/rcpu@1 fw_boot_entry
```

今回のcore 1のentry_hexが0x100804000、元のsource_dt_entry_hexが0x100800000、
ELFハッシュが上記と一致し、fdtgetは`1 804000`と表示することを確認する。
core 0は実際の同梱ELFのentryを使用する。
完全電源断・FDLから、新しく作ったFSBLと統合FITの対を第8節の順序で転送する。

UARTではcore 1のentry=0x100804000とhandshake acknowledgedを確認する。
両core成功後、OpenSBIの起動表示とU-Bootプロンプトが出てからUFS試験へ進む。
同じentryでもtimeoutする場合は、全ログを保存して停止し、他の初期化条件を調べる。

ホスト検証：ユーザー実ELFの解析、実際の固定DTSの変更、実dtcによるDT照合と不一致拒否を確認。
追加の3件はLLVMでRISC-V ELFを生成してからELF→DTBを検査する。実機実行やCPU模擬はしない。
既存FITテスト23件と分けて実行する。

```bash
# 追加試験にはRISC-V対応clang/ld.lldとdtcが必要。
python3 scripts/tests/jupiter2-ram-boot/test_elf_rpmi_contract.py
python3 scripts/tests/jupiter2-ram-boot/test_fit_packaging.py
```

この修正候補のK3 GCC完全ビルド・実機再試験・QEMU guest統合は未実施。

## 11. 両RCPU応答後、OpenSBI表示前で停止（KSB-068）

その後のユーザー実機では、core 0 entry=0x100200000、core 1 entry=0x100804000で
両方handshake acknowledgedとなった。KSB-066の表示とKSB-067の起動先修正を実機確認した。
最後の表示は次のとおりで、OpenSBIのバナーはない。

```text
[RAMBOOT] combined FIT: skip persistent extra FIT loads
[RAMBOOT] OpenSBI entry=0x100000000 next=0x102000000 dtb=102153cf0 hart=0
```

これはOpenSBI関数呼出し直前の表示である。OpenSBIに入ったか、初期化で待っているか、
consoleだけ無出力かはこのログだけでは分からない。
またRCPUの起動応答はRPMI全機能の確認ではない。U-Boot/UFS試験へは進めない。

次は今回実際に転送したrelease/images/ram-boot-vendor.itbを開発側で解析する。
このFITから同梱OpenSBI、U-Boot用DTB、ESOSと配置・ハッシュを確認できる。
OpenSBIの起動コードとリンク先、DTのconsole/RPMI/CPU設定、引渡しABIとの整合性を調べる。
SPLによるfixup後の実行時DTと一致するとは扱わず、必要なら追加の採取を行う。
現段階では原因を推測してPMPを解除したり、cache設定を変更して再試験を反復したりしない。

## 12. 実FITで確認したRPMI共有領域の不一致（KSB-069）

ユーザー提供ram-boot-vendor.itbは2191805 bytes。
SHA-256: cf820239195bc9f3dc825b7247e891ae0b59663c5d45e644bea294f999e58d95。
同梱OpenSBIは270552 bytes、SHA-256:
33072ac8216a74981ed36785a7d515f3c3cadcab3cef8d775972c28e2b9e6a9c。
FITハッシュを検査して展開し、RISC-Vの起動命令とDTBを確認した。

| 対象 | RPMI status | 共有領域 |
| --- | --- | --- |
| OpenSBI/U-Boot用DT | okay | 0x100e00000から4 queue |
| ESOS core 0のPico用DT | okay | 0x100800000、全体0x4000 |
| ESOS core 1のPico用DT | disabled | 0x100e00000、全体0x4000 |

有効なサーバーはcore 0であり、AP側がそのサーバーとは異なる領域を参照していた。
0x100e00000はcore 1のresource_table LOADとも重なる。
各queueは0x1000、slotは0x100、core 0のmailbox3は0xcac90c00、channel 0である。
doorbellのbaseはAP側と一致している。
この組合せの設定不良は確認済みだが、OpenSBI無出力の唯一の原因、修正後の起動成功とはまだ扱わない。
OpenSBIへ渡る実行時DTにはSPLのfixupがある点も区別する。

修正ビルダーは選択済みESOSのrcpu0-dtb-pico-itxとrcpu1-dtb-pico-itxを展開し、
親ノードも含めて有効なRPMIサーバーを探す。一つに決まらない場合は停止する。
共有領域、queue/slotサイズ、mailbox phandle/provider/channelを検査し、
k3-pico-itx.dtsへrpmi_shmem_mboxのボード別overrideを追加する。
共通k3.dtsiや他ボードの設定、ESOSのstatusやバイナリー自体は変更しない。
最終U-Boot FITのconf_11が選択するDTBを抽出して同じqueue/slot/doorbellを検査する。

ホストでは、受け取った実DTの不一致を検出し、有効サーバーの選択と、
実際の固定Pico DTSにoverrideを追加したcpp/dtc生成物の一致を確認した。
DTのプリプロセスは固定ソースの.configから定義を生成したホスト検査であり、
K3 GCCの完全ビルドではない。追加したRPMIの3件を含め、ELF/DTホスト試験6件とFIT試験23件を実行する。

```bash
python3 scripts/tests/jupiter2-ram-boot/test_elf_rpmi_contract.py
python3 scripts/tests/jupiter2-ram-boot/test_fit_packaging.py
```

開発PCのpublicルートで更新し、第8節の同じビルドコマンドを新しいoutputで実行する。
この修正でも引数の追加は不要。例えばOUTを次にする。

```bash
git pull --ff-only
OUT="$PWD/work/jupiter2-ram-boot/reference-vendor-rpmi-$(date +%Y%m%d-%H%M%S)"
```

成功後は次を確認する。

```bash
cat "$OUT/records/rpmi-contract.json"
fdtget -t x "$OUT/records/opensbi-uboot.dtb" \
  /soc/rpmi-shmem-mbox@cac90c00 reg
```

今回の入力ではactive_core=0、shmem_base_hex=0x100800000。
regは次の20 cellsに対応する。

```text
1 800000 0 1000   1 801000 0 1000
1 802000 0 1000   1 803000 0 1000
0 cac90c00 0 100
```

第8節と同じ完全電源断・FDL手順で、今回作ったFSBLと統合FITを対で転送する。
両coreのhandshake acknowledgedの後、OpenSBIバナーとU-Bootプロンプトを確認する。
両方が出てからUFS列挙へ進む。無出力なら全UARTログと今回のmanifestを保存して停止する。
修正候補の実機成功・QEMU guest統合は未検証である。

## 13. RPMI整合修正後のU-Boot到達とUFS列挙

2026-11-21のユーザー実機で、U-Boot 2022.10-g4c294a06-dirty
（Nov 21 2026 13:06:35 +0900）が起動し、UARTの=>へ到達した。
Modelはspacemit k3 pico itx board、envはnowhere、入出力はserial。
修正後のRAM起動経路でOpenSBIからU-Bootへの引渡しが進んだと判定する。
OpenSBIのバナーを含む全ログはこの報告にはなく、SBI/RPMI全機能の成功とは扱わない。

次はUARTのU-Bootプロンプトで以下を一度実行する。

```text
scsi scan
scsi info
```

UFSのデバイス名と容量が表示され、UIC_ERROR/descriptor失敗/UTP timeoutがなければ
UFS列挙の段階を合格とする。エラーなら反復せずログを保存してKSB-063へ追記する。
成功してもまだLinuxやKeystone Enclaveの合格には含めない。
次にパーティションと起動ファイルを読取り確認し、既存Bianbuの起動方式に合わせて進める。
参照記事のEFI/GRUBをそのままBianbuの起動に適用しない。

今回のdp cannot get HPD signal/display devices not foundはディスプレイ側の診断で、
UARTプロンプトへの到達を妨げていない。これをUFSエラーと扱わない。
Loading Environment from nowhereは試験設定の結果であり、起動時に永続envを読まない動作である。

## 14. 修正後のUFS列挙成功とパーティション確認

2026-11-21のユーザー実機でscsi scanとscsi infoの両方が成功した。

```text
Device 0: (0:0) Vendor: YMTC Prod.: YMUS8B5TH1A1C1 Rev: 0303
Type: Hard Disk
Capacity: 122056.0 MB = 119.1 GB (31246336 x 4096)
```

gear 3、lane 2、FAST MODE、rate 2の表示があり、今回のログにdescriptor失敗やUTP timeoutはない。
販売元OpenSBIを使う新しい参照RAM起動構成のUFS列挙段階を合格とする。
この結果だけでファイル読出し、Linux起動、Keystone版の動作も合格とはしない。

次はUARTのU-Bootで次を実行し、パーティション一覧を保存する。

```text
part list scsi 0
```

この一覧からbootファイルを置くパーティションとファイルシステムを確認して、
そのパーティションのenv_k3.txt、kernel、initrd、DTBを読取り確認する。
パーティション番号やLinuxのroot=を推測してbootコマンドを実行しない。
既存Bianbuの起動設定に合わせ、UARTで一時指定して販売元OpenSBIとのLinux起動を確認してから、
OpenSBIだけを開発版へ差し替える比較へ進む。

## 15. 実機bootfsからLinuxを一時起動する

ユーザー実機のGPT一覧でscsi 0:2がbootfs、scsi 0:3がrootfs。
rootfsのPARTUUIDは73708e51-d3a9-4b6f-ab55-894cd1d8b4a0である。
これは今回の実機固有の値。他の実機へそのまま流用しない。
Partition Type: EFIはGPT形式の表示で、GRUB起動の証拠ではない。
bootfsのenv_k3.txtをRAMへ取り込み、次のファイルと値を確認済み。

| 項目 | 今回の値 |
| --- | --- |
| カーネル | /Image-6.18.3-keystone、44638208 bytes |
| initrd | /initrd.img-6.18.3、41886729 bytes |
| Linux用DTB | /spacemit/6.18.3-generic/k3-pico-itx.dtb、148441 bytes |
| kernel_addr_r | 0x140000000 |
| ramdisk_addr | 0x130000000 |
| fdt_addr_r | 0x138000000 |

fdtfileは未定義だったため、実際に存在するk3-pico-itx.dtbを指定する。
commonargsはsplash等だけでroot=がないため、今回の試験ではUARTとrootfsを明示する。
以下はUARTのU-Bootで実行する。各loadのbytes read成功を確認し、失敗した場合は次へ進まない。

```text
setenv fdtfile k3-pico-itx.dtb
load scsi 0:2 ${kernel_addr_r} /${knl_name}
load scsi 0:2 ${ramdisk_addr} /${ramdisk_name}
setenv initrd_size ${filesize}
load scsi 0:2 ${fdt_addr_r} /${dtb_dir}/${fdtfile}
printenv kernel_addr_r ramdisk_addr initrd_size fdt_addr_r
```

filesizeはload成功のたびに更新される。initrdのサイズはDTBのload前に保存する。

```text
setenv bootargs console=ttyS0,115200 earlycon=sbi root=PARTUUID=73708e51-d3a9-4b6f-ab55-894cd1d8b4a0 rootwait rw loglevel=8
booti ${kernel_addr_r} ${ramdisk_addr}:${initrd_size} ${fdt_addr_r}
```

env_k3.txtと永続envは変更しない。ここではsaveenvを実行しない。
固定参照ソースの非SPL dram_init()は先頭32 MiBを除外してgd->ram_baseを設定する。
arch/riscv/lib/image.cのbooti_setup()はそのbaseにLinux Imageのtext_offsetを足した位置へ移動する。
通常の2 MiB offsetなら0x102200000で、先頭のESOS実行領域へ移動する構成ではない。
起動ログのMoving Image表示も保存する。initrdとDTBの追加移動が表示される場合もログを残す。

確認点はLinuxの起動ログ、rootfsのmount、login promptへの到達。起動後はuname -rを確認する。
今回のカーネルの実releaseは6.18.3であり、Image名の-keystoneだけからunameの値を判断しない。
販売元OpenSBIによるLinux起動の確認で、Keystone SM/Enclaveの実行成功とは分ける。
停止・panic・root mount失敗時は最初のエラーを含むUART全ログを保存する。
この段階のLinux起動はまだ実機結果待ちである。

## 16. Linux起動成功とスクリプト整理

ユーザーから2026-11-21にLinux起動成功が報告された。今回の手動起動は、
販売元OpenSBIと整合修正した参照FSBL/U-Boot/ESOSをRAM起動し、
UFS bootfs上のImage-6.18.3-keystone、initrd.img-6.18.3、
spacemit/6.18.3-generic/k3-pico-itx.dtbからrootfsを起動したもの。
uname -rの実出力とKeystone SM/Enclave実行結果はまだ取得していない。

途中のDTB load失敗は、fdtfile未定義のままディレクトリを指定したためだった。
再現用の運用ツールはfdtfileを明示設定し、initrd_sizeをDTB load前に保存し、
各load成功時だけbootiへ進むUARTテキストを生成する。
PC側の転送もFSBL段階とSPL/FIT段階を分け、checksumとSPLの転送上限を確認する。
これらは操作を行うスクリプトで、ホスト回帰試験とは区別する。

ホスト試験は次へ集約した。

```text
scripts/tests/jupiter2-ram-boot/
├── README.md
├── run-host-tests.sh
├── test_fit_packaging.py
├── test_elf_rpmi_contract.py
└── test_host_operations.py
```

各先頭コメントに何を検証するか、どこで実行するか、実機を操作しないことを明記した。
テスト用イメージは実機へ転送しない。新しい操作ツールのUSB実行は実機未確認。
実機成功はユーザーの手動操作の報告、ホスト回帰の合格は開発環境の実行結果として分ける。

```bash
bash scripts/tests/jupiter2-ram-boot/run-host-tests.sh
```

必要ツールを確認してから実FIT試験23件、ELF/RPMI DT試験6件、操作ツールのホスト試験8件を実行する。
操作ツール試験はUSBに触らないdry-runと、実FITツール・bash -n等を使う。
CPU/SBI/PMPの模擬やQEMU guest実行は行わない。
