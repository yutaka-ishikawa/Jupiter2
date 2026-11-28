# Jupiter2実機でKeystoneとOP-TEEを同居させる16枠PMP実装計画

Jupiter2 Pico-ITXのUSB RAM起動で、eFuseを有効にしたOP-TEEとKeystoneを同じLinux起動中に使う。
ESOSとRPMIの保護と動作を維持し、X100・A100とも各hartのPMP枠0–15で動作させる。
A100の枠16–31は無効とする。実機のOP-TEEはRTC・TE200・PRNG・IOPMPも有効とする。
[16枠の割り当てと根拠](keystone-optee-coexistence-design.md#103-実機のop-tee既定機能を維持する割り当て)

基準は `captures/20261108-075700/` の実機Linux DTB、販売元のPico-ITX用DTB、
同梱FIT `keystone-optee-geu-20261126-184408` と、領域の設定が一致する実機UART記録とする。
現行の初期化経路は21枠相当を要求して停止した。新しい表は実機資料と静的に照合済みで、
全域規則の共用はQEMUで確認済み。実機では各装置に合わせた枠の切替と検証を行う。
[KSB-092の調査記録](keystone-bug-report.md#ksb-092-実機の同居ram起動でopensbiのドメイン初期化が停止する)

初期の対応範囲は、EPMとUTMをそれぞれ1つのNAPOT枠で表せるEnclave 1個とする。
EPMを確保済みの最大使用数はLinux・U-Bootで16枠、OP-TEEとEnclaveで各15枠。
追加Enclave、TOR、ページング用の追加領域が枠に収まらない場合は、既存のCREATE契約に従って
PMP容量不足を報告する。各CPUからのMPXY呼び出しと、別hartでのEnclaveとfTPMの同時実行を検査する。

## PMP枠数調整を始める前の基準点

`Record baseline before Keystone and OP-TEE PMP slot adjustment` を、同梱構成のPMP枠数調整を
始める前の基準コミットとする。実装はこのコミットの次から進め、調整前の状態に戻る際はこのコミットを参照する。

## 状態別PMPアドレスの定義先

2026-11-27（JST）にB案を選択した。Linux・OP-TEE・Enclaveで共用するPMP枠の物理アドレスを
OpenSBIのK3用コードで定義する。起動時には登録済みのドメイン領域を固定の定義と照合し、
切替後は実際のPMP CSRからアドレス・サイズ・権限を読み戻す。

B案で対象機のI/Oと保護を両立できる配置を確認できなかった場合は、再現条件、制約と試験結果を
KSB-092に記録し、実機情報から生成するDTBに状態別の配置を定義するA案へ変更する。
A案でも起動時の領域照合、16枠の上限、切替後のCSR読み戻しと失敗時の復元を受入条件とする。
切り戻し時は枠15の共用を検証済みの `e01f41a4d` と、この節の判断記録を参照する。

## 1. 実装順序

枠切替の実装はOpenSBIとKeystone SMが担当する。Linux側は生成DTBとカーネル設定の確認を基本とし、
選択したMMIO仲介やDMA保護に必要な場合にドライバーを修正する。以下のパスはJupiter2リポジトリの
ルートからの相対パスで、OP-TEE・U-Bootの外部ソース内のパスはその旨を記す。
実機用の `optee_os` は `.build-k3/optee-hardware/optee_os/`、参照RAMビルダーの `u-boot-k3` は
`$OUT/source/` に置かれる。外部ソースの変更はJupiter2側の `patches/` から適用する。
「新規案」は追加する場合のファイル名の候補である。

| 工程 | 実施内容 | 次へ進む条件 |
| --- | --- | --- |
| 1 | 実機資料からアドレス・権限・優先順位を照合し、同居時の枠契約を確定する | 各状態の固定領域とEPM・UTMが16枠に収まり、必要なI/Oと重複条件を説明できる |
| 2 | OpenSBIとKeystone SMに、状態別の適用と全hartのEPM保護を実装する | 実際のQEMUゲストで枠の読み戻し、EPM同期、容量エラー、既存単独構成の回帰を確認できる |
| 3 | OP-TEE用の私有DTBと、実機FIT・Linux DTBの生成を接続する | FITの構成と予約領域が一致し、QEMUの同居ゲストでOP-TEE初期化・TA実行・Linuxへの復帰を確認できる |
| 4 | 実機のクロック・リセットと公開eFuse値へのアクセスを接続する | OP-TEEとホストが必要とする操作と権限が確定し、QEMUで実装済みの装置を用いて回帰を確認できる |
| 5 | IOPMP・DMA保護を確定し、既定機能入りCoreでUSB RAM起動を試験する | ESOSからLinuxまで起動し、両クラスタのPMPとDMAの実効権限が合格条件を満たす |
| 6 | 同一Linux起動でKeystone、OP-TEE、fTPM、IMAの検査を実施する | 両TEEの同時実行、再起動、基準イメージへの復帰を試験し、成果物とUARTを記録できる |

### 工程1　実機の枠契約と検査条件を確定する

- `hardware/jupiter2/` の採取結果とFIT内のOpenSBI用DTBを比較する。DTBの `ranges` による
  物理アドレス変換、起動経路で有効な装置、4 KiBのPMP粒度、NAPOT境界を確認する。
  `0xf0000000–0xf1ffffff` の保護範囲にあるホストのI²C3、APBC2、公開eFuseの扱いを確認する。
- ESOSの4つのロック枠を全状態で固定する。RPMI共有キューの枠1をRCPU1のロック枠6より先に置き、
  M-modeからのアクセスを維持する。doorbellとM-mode用割り込み・タイマーは全状態で
  S/U-modeからの直接アクセスを拒否する。基準機以外では、採取結果を比較してから同じ表を適用する。
- CoreとSHMは既定の物理範囲を使う。SHMはLinuxとOP-TEEでRW、実行不可とする。
  EPMの枠13は全hartで追跡し、枠14はホスト中のDCIU保護とEnclave中のUTM許可で使う。
  末尾の枠15はホストで全域許可、OP-TEE・Enclaveで全域拒否とする。
  EPM・UTMがCore、SHM、ESOS・RPMIなどの予約範囲と重ならないことをCREATEの事前検査に含める。
- 適用条件、構成の識別、枠ごとの所有者を確定し、生成DTBの検査とOpenSBIの起動時検査で照合する。
  領域や優先順位の矛盾、粒度違反、容量不足が見つかった場合はS-modeへの引き渡し前に報告する。

[実機情報と採取結果の比較](../hardware/jupiter2/jupiter2-hardware-compatibility.md) · [現行のPMP枠検査](../opensbi/include/sbi/k3_keystone_boot_slots.h)

#### 変更予定ファイル

| 対象 | ファイル | 変更内容 |
| --- | --- | --- |
| 同居設計 | `doc/keystone-optee-coexistence-design.md` | 状態ごとの枠番号、優先順位、適用条件を確定する |
| 実機適合性の調査記録 | `hardware/jupiter2/jupiter2-hardware-compatibility.md` | 基準機の採取IDと、別の実機で比較が必要な項目を追記する |

`hardware/jupiter2/captures/20261108-075700/running.dtb`、`hardware/jupiter2/vendor/u-boot-k3-pico-itx.dtb`、
`hardware/jupiter2/vendor-fit.json` は照合に使う入力である。

### 工程2　OpenSBIとKeystone SMの枠切替を実装する

- `sbi_hart.c` の現行検査はLinux・OP-TEE間でPMPエントリのベース、サイズ、MMIO属性の一致を要求する。
  同居時は実行状態ごとの表を検査し、枠15と共用枠の更新を一つのM-mode経路で管理する。
  Keystone単独とOP-TEE単独は各構成の既存経路で起動する。
- Keystoneの起動時枠検査とアロケーターを同居構成に対応させる。同居時は既存のOS全域制御専用枠を
  枠15へ統合する。枠13のEPMは既存の全hart同期を使う。UTMの予約はCREATEで確定し、枠14への
  設定は当該Enclaveを実行するhartで行う。CREATEはEPMとUTMの両方を確保できるか先に検査し、
  枠不足では既存のPMPエラー経路を使う。範囲重複と全hart同期の失敗も区別して記録する。
- MPXYとSMの既存の遷移点を使い、元の設定を照合してから枠15を拒否にする。対象hartの可変枠を
  更新し、PMP CSRの読み戻しと必要な同期を終えてから実行状態を切り替える。ホストへの復帰では、
  ホスト側の規則が確定してから枠15を許可へ戻す。切替失敗時は検査済みの旧状態を復元し、
  復元結果を確認できないhartはS-modeへ復帰させない。
- 一つのhartのMPXY・Enclave切替と全hartのEPM更新を整合させる。CREATE・DESTROY・HSMの
  既存の同期と世代確認を使い、別hartがOP-TEEを実行中でもEPM保護を反映する。停止中のhartは
  起動・復帰時に現在の保護を検査する。タイマー、IPI、Sstcとコンテキスト復帰は既存の動作を回帰検査する。

[OpenSBIの現行PMP計画とCSR更新](../opensbi/lib/sbi/sbi_hart.c) · [ドメイン切替](../opensbi/lib/sbi/sbi_domain_context.c) · [KeystoneのPMP管理](../keystone/sm/src/pmp.c) · [KeystoneのEnclave管理](../keystone/sm/src/enclave.c)

#### 変更予定ファイル

| 対象 | ファイル | 変更内容 |
| --- | --- | --- |
| OpenSBIの枠定義・検査 | `opensbi/include/sbi/k3_keystone_boot_slots.h`、`opensbi/include/sbi/k3_pmp_partition_evidence.h` | 同居時の枠数、所有者と起動時検査を定義する |
| OpenSBIのPMP実装 | `opensbi/lib/sbi/sbi_hart.c`、`opensbi/include/sbi/sbi_hart.h` | 状態別のPMP設定、CSRの読み戻しと復元を実装し、SMから使う窓口を接続する |
| OpenSBIのドメイン切替・MPXY | `opensbi/lib/sbi/sbi_domain_context.c`、`opensbi/lib/utils/mpxy/fdt_mpxy_opteed.c` | Linux・OP-TEE間の既存遷移を同居用のPMP処理へ接続する |
| Keystone SMのPMP管理 | `keystone/sm/src/pmp.c`、`keystone/sm/src/pmp.h`、`keystone/sm/src/sm.c` | 同居時のEPM・UTMの枠予約と枠15の共用を実装する |
| Keystone SMのEnclave管理 | `keystone/sm/src/enclave.c` | CREATEの範囲・容量検査、EPMの全hart同期、RUN・RESUME・復帰時のUTM設定を接続する |
| OpenSBIのHSM（条件付き） | `opensbi/lib/sbi/sbi_hsm.c` | 既存の起動・復帰経路への接続が必要な場合に、S-mode移行前のPMP確認を追加する |
| QEMU起動スクリプト・試験用DT設定 | `verifications/crypto/run-qemu.py`、`verifications/optee-coexistence/boot.dts`、`verifications/optee-coexistence/boot-pmp16-geu.dtso` | 混在PMPの同居試験で、PMP枠数、アドレス切替と枠不足を確認する |
| QEMUのゲスト試験コード（条件付き） | `verifications/optee-coexistence/coexist-init.c`、`verifications/optee-coexistence/host.cpp` | 既存試験で不足するEPM同期・容量エラーの確認を追加する |

OpenSBIのビルドは `opensbi/platform/generic/configs/k3_keystone_audit_defconfig` の
既存のKeystone SM・OPTEED設定を使う。同居構成に追加のビルド選択が必要と判明した場合は、同ファイルを見直す。

### 工程3　OP-TEE用の私有DTBとビルド経路を接続する

- 採用版OP-TEE Coreの16 MiB内に書き込み可能なDTBバッファーを予約する。Coreの初期化、
  TAの割り当て、Measured Bootログ `0x171ff0000–0x171ffffff` と領域が重ならないことを
  リンカーとビルド時の検査で確認する。OP-TEEがノードと予約を追加した後のサイズも確認する。
- OpenSBIは引き渡されたDTBの範囲・形式・長さを検査し、私有バッファーへコピーしてOP-TEEに渡す。
  OP-TEEのDTB更新はコピーに適用する。U-Bootへは元のDTBを渡し、測定済みの引き渡しDTBとログを保持する。
- 実機FITにはOpenSBI用DTBとCoreを格納し、出力するLinux用DTBで `/firmware/optee`、MPXYと
  `reserved-memory` を同じ設定から検査する。K3の既存MPXY、boot hart選択と16 hartの起動順を使う。
  QEMU用のビルド・試験手順と、実機用の既定機能入りクロスビルドをそれぞれ既存の手順に接続する。

[KSB-093の起動時DTB不整合](keystone-bug-report.md#ksb-093-実機同居用のop-tee起動dtbが読み取り専用) · [OpenSBI用DTB生成](../scripts/prepare-jupiter2-optee-opensbi-dtb.py) · [Linux用DTB生成](../scripts/prepare-jupiter2-optee-linux-dtb.py) · [FITと実機Coreのビルド手順](jupiter2-build-install-test.md#ram-boot-images)

#### 変更予定ファイル

| 対象 | ファイル | 変更内容 |
| --- | --- | --- |
| OpenSBIのDTB引き渡し | `opensbi/lib/utils/mpxy/fdt_mpxy_opteed.c` | OP-TEE起動前に私有DTBを用意して引き渡す |
| OpenSBIのDT設定読み取り（条件付き） | `opensbi/lib/utils/fdt/fdt_domain.c` | 私有コピー領域の情報をDTから受け取る場合に、その読み取りと検査を追加する |
| OP-TEE Coreのリンカー設定・起動コード | 外部 `optee_os` の `core/arch/riscv/kernel/kern.ld.S`、`core/arch/riscv/kernel/boot.c` | Coreのメモリ配置に私有DTBを予約し、起動時に既存のDT処理から使えるようにする。Jupiter2側に `patches/optee/k3-private-boot-dtb.patch` を新規追加する案 |
| OpenSBI用DTBとFITの生成スクリプト | `scripts/prepare-jupiter2-optee-opensbi-dtb.py`、`scripts/build-jupiter2-reference-ram-boot.py`、`scripts/build-jupiter2-ram-boot-image.py` | 実機の領域定義をK3コードの状態別配置と照合し、予約領域、Coreの配置とFIT選択構成を生成する |
| Linux用DTBの生成スクリプト | `scripts/prepare-jupiter2-optee-linux-dtb.py` | `/firmware/optee`、MPXY、`reserved-memory` の整合をビルド時に確認する |
| Coreのビルドスクリプト・実機手順 | `scripts/build-k3-optee-coexist.sh`、`doc/jupiter2-build-install-test.md` | QEMU用と実機用の各ビルドでOP-TEEのパッチを適用する手順を整える |
| FIT生成のホスト側試験 | `scripts/tests/jupiter2-ram-boot/test_fit_packaging.py` | 私有DTB、予約範囲とFIT内の入力の整合を検査する |

`records/opensbi-uboot.dtb` と `release/images/k3-pico-itx-keystone-optee.dtb` はビルドの生成物である。

### 工程4　実機のMMIOとeFuseを接続する

- K3版OP-TEEと実機Linux・U-Bootの呼び出し元を調べ、PMU AP、PMU MAIN、APBC2、DCIUの
  必要なレジスター操作を一覧にする。LinuxのI²C3、OP-TEEのRTC、GEU・TE200・PRNGの
  共通クロック、HSDMAのリセット・クロック、CPU起動・復帰に必要な操作を識別する。
- M-modeの仲介では、実行状態、レジスター、操作幅、許可するビットを照合し、共有レジスターの更新を
  直列化する。CPUの起動アドレス・復帰制御と、IOPMP保護を変える操作はM-modeの管理下に置く。
  Linuxには温度補正とSoC識別に必要な公開eFuse項目を返す。Coreは既存のeFuse・HUK経路で動作させる。
- 仲介の接続方法は二案を比較する。既存のPMU APのアクセス仲介を使う案では、Linux・U-Boot・
  OP-TEEの呼び出しを維持できるか、許可対象を絞れるかを確認する。用途別のSBI呼び出しを使う案では、
  各ドライバーの変更量と既存ビルドへの影響を確認する。両案が成立する場合は、変更箇所と保護範囲を
  示して方針の判断を仰いでから、この工程の実装を進める。

[既存のK3 MMIO仲介](../opensbi/platform/generic/spacemit/spacemit_k3.c) · [LinuxのK3クロック](../linux-k3/drivers/clk/spacemit/ccu-k3.c) · [採用版OP-TEEのK3クロック操作](https://github.com/spacemit-com/optee_os/blob/2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59/core/arch/riscv/plat-k3/k3_ccu.c)

#### 接続方式を決めるための照合結果

- Linuxと参照U-BootのAES/WTMクロックは、OP-TEEがeFuse・TE200に使う
  PLLゲートとAESクロック・リセット制御を操作する。同じ制御を複数の環境が
  更新するため、共有する設定をM-modeで管理する。
- 基準機のLinux DTBはI²C3とHDMAを有効にしている。LinuxのDCIUクロック・リセット
  とOP-TEEのHSDMA起動順序を照合した。共有するDMAのクロック・リセットは、
  IOPMPの有効状態を保ったまま正規の転送ができるように扱う。
- LinuxのeFuseドライバーはprobeでバンクをまとめて読み込む。基準機のDTBにある
  SoC識別のセルと、使用するLinux DTBの温度補正セルを照合して、公開項目の範囲を確定する。
  鍵の取得はOP-TEEが担当する。

| 方式 | 接続範囲と確認点 |
| --- | --- |
| 既存のMMIO仲介を拡張 | OpenSBIが既存のアクセス処理で許可済みのレジスターとマスクを扱う。基準機のLinuxはSv39で、既存仲介はBareとSv39に対応する。既存ドライバーの読み取り・更新・待ち合わせを保てることを確認する。 |
| 用途別のSBI呼び出し | OpenSBIが用途を限定した要求を受付ける。該当ドライバーを呼び出しに接続し、U-BootではOpenSBIの後に動く本体への適用範囲を確認する。 |

通常の同居QEMUは `riscv-virtio` のDTBで起動する。単独・同居、PMP、fTPM・IMAの回帰を
ここで確認し、Pico-ITXのクロック・リセットとeFuse・IOPMPの動作は実機の結果を記録する。
[基準機のLinux DTB](../hardware/jupiter2/captures/20261108-075700/running.dtb) · [LinuxのeFuseドライバー](../linux-k3/drivers/nvmem/spacemit-efuse.c)

#### 採用した方式

2026-11-27（JST）に既存のMMIO仲介を拡張する方式を選択した。Pico-ITX固定PMP構成で、
OpenSBIがLinux・U-BootとOP-TEEの32ビットアクセスを許可表と照合する。共有クロックと
リセットは書き込みをレジスターごとの所有ビットに制限する。ホストのeFuse読み取りには、
SoC識別と温度補正に使う公開ビットを返す。Secure Coreは既存のeFuse経路で初期化する。
[K3のMMIO仲介](../opensbi/platform/generic/spacemit/spacemit_k3.c) ·
[Pico-ITXの許可表](../opensbi/platform/generic/spacemit/k3_pico_itx_mmio.c)

#### 変更予定ファイル

| 対象 | ファイル | 変更内容 |
| --- | --- | --- |
| OpenSBIのK3プラットフォームコード | `opensbi/platform/generic/spacemit/spacemit_k3.c`、`opensbi/platform/generic/spacemit/k3_pico_itx_mmio.c`、`opensbi/platform/generic/spacemit/k3_pico_itx_mmio.h`、`opensbi/platform/generic/spacemit/objects.mk` | 既存のアクセスフォルト処理からクロック・リセットと公開eFuse値の許可表を参照する |
| OpenSBIのPMP配置とドメイン | `opensbi/lib/sbi/sbi_hart.c`、`opensbi/include/sbi/sbi_hart.h` | 検査済みのPico-ITX構成とOP-TEEドメインを仲介処理へ伝える |
| Linuxのクロック・リセットドライバー（条件付き） | `linux-k3/drivers/clk/spacemit/ccu-k3.c`、`linux-k3/drivers/reset/reset-spacemit.c` | 用途別SBI呼び出しを選んだ場合に、対象のクロック・リセット操作を接続する |
| LinuxのeFuseドライバー（条件付き） | `linux-k3/drivers/nvmem/spacemit-efuse.c` | 公開eFuseの取得にドライバー側の変更が必要な場合に、公開項目を受け取る経路に接続する |
| LinuxのDT設定（条件付き） | `scripts/prepare-jupiter2-optee-linux-dtb.py`。元の定義は `linux-k3/arch/riscv/boot/dts/spacemit/k3.dtsi` | クロックやeFuseの供給元を変更する方式の場合に、生成する同居用Linux DTBに反映する |
| OP-TEE CoreのK3クロックコード（条件付き） | 外部 `optee_os` の `core/arch/riscv/plat-k3/k3_ccu.c` | 用途別SBI呼び出しを選んだ場合に接続する。Jupiter2側のパッチは `patches/optee/k3-mmio-sbi.patch` が新規案 |
| U-Boot本体のK3クロックコード（条件付き） | 外部 `u-boot-k3` の `drivers/clk/spacemit/ccu-k3.c` | U-Boot本体の操作にも用途別SBIが必要な場合の候補。`patches/jupiter2-u-boot-mmio-sbi.patch` を追加し、`scripts/build-jupiter2-reference-ram-boot.py` から適用する案 |

U-Bootの候補パスは、参照RAMビルダーが固定しているコミットで確認した。
[参照版U-BootのK3クロックコード](https://github.com/ganboing/u-boot-k3/blob/4c294a06c14e46e9c9cc934373c3e63919703017/drivers/clk/spacemit/ccu-k3.c)

### 工程5　DMA保護を照合し実機でRAM起動する

- 採用版IOPMPの `INT2` にはOP-TEE CoreをRWとする規則がある。実機のDMA要求元と有効な規則を
  照合し、Core、測定ログ、EPMについて実効権限を確認する。ESOS・RPMI、Linuxのストレージ等、および
  TE200・PRNGに必要な正規の転送を確認する。結果はCPUのPMP読み戻しとは別に記録する。
- 現行のIOPMP設定でEPMの保護を確認できない場合は、予約したEPMプールを保護する方法と、
  EPMの確保・解放に同期して保護する方法の実現性を調べる。両方が成立する場合は、対応可能な
  DMA要求元、EPM割り当てと解放、既存のI/Oへの影響を比較して方針の判断を仰ぐ。
- 実機用の既定機能を使うCoreと新しいOpenSBIを含むFITを生成する。同じビルドの `FSBL.bin` と
  FITをUSBでRAMへ転送し、ESOS両コアの応答、RPMI、OpenSBIの枠の読み戻し、OP-TEE初期化、
  U-Boot、Linuxへの到達をUARTで確認する。X100とA100の結果を個別に記録する。
  実機Coreは `CFG_K3_EFUSE=y`、`CFG_K3_HUK_ALLOW_UNFUSED=n` でビルドし、本来の鍵経路で初期化できるかを確認する。
  検査中はUSB RAM起動を使い、基準のFSBLとFITへの切り戻しを確認する。

[採用版IOPMPのポリシー](https://github.com/spacemit-com/optee_os/blob/2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59/core/arch/riscv/plat-k3/k3_iopmp_policy.c#L453) · [実機のUSB RAM起動手順](jupiter2-ram-boot-guide.md)

#### 変更予定ファイル

| 対象 | ファイル | 変更内容 |
| --- | --- | --- |
| OP-TEE CoreのIOPMP（条件付き） | 外部 `optee_os` の `core/arch/riscv/plat-k3/k3_iopmp_policy.c`、`core/arch/riscv/plat-k3/k3_iopmp.c` | 実機で確認したDMA要求元に合わせ、必要なポリシーと初期化を修正する。Jupiter2側の `patches/optee/k3-iopmp-coexistence.patch` が新規案 |
| Linux用DTB・Keystone（固定EPMプール案を選んだ場合） | `scripts/prepare-jupiter2-optee-linux-dtb.py`、`keystone/linux-keystone-driver/keystone-page.c`、`keystone/sm/src/enclave.c` | EPMプールをDTBで予約し、必要に応じてLinuxドライバーでそのプールを選ぶ。SMはEPMが保護済みの範囲に収まることを検査する |
| OpenSBI・Keystone SM（EPMごとに保護を更新する案を選んだ場合） | `opensbi/platform/generic/spacemit/spacemit_k3.c`、`keystone/sm/src/enclave.c` | EPMの確保・解放とIOPMPのM-mode管理を接続する |
| 実機OP-TEE Coreのビルド設定・RAM起動手順 | `doc/jupiter2-build-install-test.md`、`doc/jupiter2-ram-boot-guide.md` | eFuse・HUKと既定機能のビルド指定、USB RAM起動と切り戻し手順を記録する |

`FSBL.bin` と `ram-boot-keystone.itb` は参照RAMビルダーの生成物で、ESOSの `hardware/jupiter2/vendor/esos.itb` は入力である。

### 工程6　実機Linuxで同時実行と再起動後を確認する

- 起動したImage、モジュール、Linux用DTBを照合する。KeystoneサンプルとOP-TEEのTAを動かし、
  fTPMに対応する `/dev/tpmrmN` を特定する。別hartでEnclaveとfTPMのコマンドを実行し、
  実行時間が重なったことと両方の正常終了をログに残す。
- 試験用NVデータの再起動・電源再投入後の保持、IMA測定とPCR 10の照合、Measured Boot有効時の
  TCGイベントログとPCR 0・1の照合を行う。検査が通ったFSBLとFITの組を、ビルド手順とともに記録する。

#### 変更予定ファイル

| 対象 | ファイル | 変更内容 |
| --- | --- | --- |
| 実機のLinuxカーネル設定（条件付き） | `hardware/jupiter2/linux.config` | TEE・MPXY・fTPM・IMA等に追加の設定が必要ならここへ記載する。`scripts/build-linux-k3.sh` が `linux-k3/arch/riscv/configs/k3_bianbu_defconfig` に重ねる設定ファイル |
| QEMU試験用のLinuxカーネル設定（条件付き） | `scripts/tests/jupiter2-ftpm-ima.config` | fTPM・IMAのQEMU試験に設定追加が必要な場合に更新する |
| 実機上の同時実行テスト（新規案） | `scripts/tests/jupiter2-coexistence-hardware.sh` | 既存コマンドを使い、別hartでのEnclaveとfTPMの実行時間・終了結果をまとめて採取する場合に追加する |
| 実機の導入・試験手順 | `doc/milkv-jupiter2-stack-install.md`、`doc/jupiter2-keystone-app-test.md`、`doc/jupiter2-ftpm-ta-test.md` | 両TEE・fTPMの操作、実行例と合格条件を記載する |
| 不具合記録・実機の試験結果 | `doc/keystone-bug-report.md`、`doc/evidence/jupiter2-coexistence-16-pmp/uart.txt`（新規案） | KSB-092・093の修正コミット、確認範囲と実機UARTを記録する |

Linuxの `linux-k3/drivers/tee/optee/mpxy_sbi.c` と `linux-k3/drivers/char/tpm/tpm_ftpm_tee.c` は、
既存のMPXYおよびfTPM経路を使って動作を確認する対象である。

## 2. 検証項目と合格条件

| 環境 | 試験 | 合格条件と使う手順 |
| --- | --- | --- |
| 開発PC | ビルド・DTB・FIT | 同居、Keystone単独、OP-TEE単独をビルドし、Core・SHM・DTB・ログの予約と選択したFIT構成を照合する。[実機ビルド手順](jupiter2-build-install-test.md) |
| K3 QEMU | 単独構成と同居構成 | 既存の `run-qemu.py --all --sstc on --optee-coexistence` にCore ELF、DTB、initramfsを渡し、16 CPU、Enclave 16回、OCALLを含むTA呼び出し33回、電源断を確認する。OP-TEE単独も既存のTA試験で確認する。[QEMUのビルドと試験手順](qemu-build-install-test.md) |
| K3 QEMU | 混在PMPと状態遷移 | 同居試験を既存の `mixed` プロファイルへ接続し、16/32枠混在・4 KiB粒度で全hartのPMPを読み戻す。追加枠の無効、容量不足の結果、CREATE・DESTROY後のEPM同期、別hartのMPXY、HSMの起動・復帰を確認する。[QEMUの混在PMPプロファイル](jupiter2-qemu-hardware-test-gaps.md#3-今回追加したqemuプロファイル) |
| K3 QEMU | fTPM・IMAとNVの回帰 | `make ftpm-ima` と `scripts/tests/jupiter2-ftpm-ima-qemu.sh` を使い、早期登録のPCR 10更新、遅延登録の対照結果、測定一覧を確認する。既存のNVランナーでコールドブート後に試験値を照合する。[fTPMとIMA試験手順](jupiter2-ftpm-ta-test.md) |
| 実機USB RAM起動 | 起動、ESOS・RPMI、eFuse、DMA | 両クラスタのPMP読み戻し、16 CPUのオンライン、ESOS・RPMI、割り込み・タイマー、必要なI²Cとクロック、eFuseを使うCoreの初期化、IOPMPの実効権限を確認する。[実機の適合性調査](../hardware/jupiter2/jupiter2-hardware-compatibility.md) |
| 実機Linux | 同時実行、起動後の機能検査 | Keystoneの `hello`・`hello-native`、OP-TEEのTA、fTPMの `/dev/tpmrmN` 経由の操作を確認し、fTPMとEnclaveを別hartで重ねて実行する。NVの再起動後の保持とIMAのPCR 10・`ascii_runtime_measurements` を照合する。Measured Boot有効時はFSBLのイベントログとPCR 0・1も照合する。[実機Linux試験手順](milkv-jupiter2-stack-install.md) · [Measured Boot検査手順](jupiter2-fsbl-measured-boot-verification.md) |

通常の同居QEMUランナーは一律16枠・16バイト粒度で起動する。混在PMPでの結果には、
起動オプションと実際のCSR読み戻しを添える。QEMUのGEUモデルで確認した内容と、実機のeFuse、
ESOS・RPMI、IOPMP、RTC、TE200の検査結果は、それぞれの実行環境を明記する。

### 全域枠の共用を確認したQEMU試験

同居構成で通常枠が13個必要な場合、OpenSBIとKeystone SMが枠15の全域規則を共用する。
枠13はEPM、枠14はUTMに使用する。OP-TEEからLinuxへのセカンダリhartの起動では、
既存HSMの遷移を使い、共有構成の停止はOP-TEEの拒否規則を適用した状態で行う。
検証は[同居ゲストの16枠PMP試験](../verifications/optee-coexistence/README.md#k3-qemuでの16枠pmp試験)を参照。

4 KiB粒度の一律16枠・混在16/32枠で、Enclave実行時に枠0–15を読み戻した。
通常枠を14個にした入力は、合計17枠が必要になるためLinux起動前に拒否された。

従来の同居試験では、LinuxとOP-TEEで同じアドレス範囲を使うPMP配置を検査した。
[CSR読み戻しとUARTの試験記録](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

### K3コードで定義したGEU枠の切替試験

B案の最初の実装では、GEUを含むLinuxの拒否窓と、OP-TEEがRWで使うGEUページをK3コードに定義した。

混在16/32枠は、QEMUのhart 0–7に16枠、hart 8–15に32枠を実装し、実機のX100とA100で
PMPの実装数が異なる条件を再現する構成である。使用する枠を全hartで0–15に揃え、
32枠側の枠16–31が無効であることをCSRで確認した。

一律16枠と混在16/32枠のQEMUで、起動時に全16 hartの枠7を読み戻した。Linux起動後には同じhartで、
`0xf0700000`・16 KiBの拒否から `0xf0702000`・4 KiBのRWへの切替と、Linux復帰時の復元を確認した。
両構成とも最大16枠で、Enclave 16回とTA呼び出し33回が成功した。

試験にはQEMUの空のeFuseモデルと開発用HUKを使った。
[再試験手順](../verifications/optee-coexistence/README.md#geuのアドレス切替) ·
[CSR読み戻しとUARTの試験記録](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

### 枠14の共用と私有DTBの確認

Pico-ITXの状態別配置をOpenSBIのK3コードに定義した。起動時に、実機DTBから登録された領域、
OpenSBIの実行領域、ESOSのロック範囲とRPMIの先行規則を照合する。枠14はLinuxでDCIUを拒否し、
OP-TEEで無効、EnclaveでUTMをRWにする。Keystoneの全hart PMP更新はEPMの枠13に適用する。
[Pico-ITXの固定枠定義](../opensbi/lib/sbi/k3_pico_itx_pmp.h)

4 KiB粒度の混在16/32枠と一律16枠のQEMUで、GEUと枠14の切替を実行した。OP-TEEとEnclaveの
両方からLinuxへ戻る際にDCIUの拒否を読み戻し、最大16枠を確認した。Core内に確保した私有DTBを
OpenSBIが複製して渡す構成でも、各16 CPU、Enclave 16回とTA呼び出し33回、正常電源断を確認した。
容量が不正な私有DTBの指定では、S-modeへの引き渡し前にMPXY初期化が停止した。
[枠14のQEMU試験手順](../verifications/optee-coexistence/README.md#枠14のdciuとutmの切替) ·
[QEMUのCSRとUART記録](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

実機向けは既定I/O機能入りのOP-TEE Coreをクロスビルドし、FSBL、統合FITおよびLinux用DTBを生成した。
組み込んだCore・DTB、私有DTBの位置、RPMI共有キュー、SHA-256を照合した。
[実機向けFITの生成方法](jupiter2-build-install-test.md#16枠同梱構成のfit生成検査)

### MMIO仲介を追加した状態でのQEMU回帰

Pico-ITXのMMIO仲介を追加したOpenSBIをビルドした。QEMUでKeystone単独、OP-TEE単独、
同居の一律16枠・16/32枠混在が合格した。両同居構成でPMP CSRの最大使用数は16枠だった。
fTPM・IMAは早期登録と遅延登録が合格し、NV試験は別のQEMUプロセスへの保存状態の引き継ぎを確認した。
この回帰で再現した起動台帳とHSM起動要求の競合は、KSB-096・KSB-097に原因と修正を記録した。
[不具合台帳](keystone-bug-report.md#ksb-096-op-tee先行起動で副hartのpmp記録が失敗する) ·
[QEMUの試験記録](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

工程5では修正版の統合FITでUSB RAM起動し、Pico-ITXのMMIO仲介、ESOS・RPMI、eFuseおよび
IOPMPの実効権限を確認する。今回のQEMUゲストはQEMU用DTBで起動した。

<a id="pico-itx-ram-boot-2026-11-28"></a>
### 実機USB RAM起動の記録（2026-11-28）

Pico-ITX実機でKeystone・OP-TEE同梱FITをUSB RAM起動した際の、利用者提供のUARTログを確認した。
前半のLinuxとsystemdの出力は、後半のBootROM USBダウンロードより前の別の起動に属する。
以下は106 KiBのヒープで行った初回のUSB RAM起動。試験で使ったFSBL・FIT・Coreのハッシュと正確な
ソースコミットはこの記録からは特定できていない。

| 段階 | UARTで確認した内容 |
| --- | --- |
| BootROMとSPL | 411,776バイトのFSBLを転送し、参照SPLが起動。SPLが2,624,029バイトの統合FITを受信 |
| ESOSとOpenSBI | 両RCPUのハンドシェイクが完了し、OpenSBI v1.6が起動。起動hart 0は `optee-domain` を選択 |
| PMP | 全16 hartで、`boot-host` 状態は15枠（`0xdfff`）、`optee` 状態は14枠（`0x9fff`）を読み戻した。実装数はhart 0–7が16枠、8–15が32枠。粒度は4 KiB |
| OP-TEE Core | OpenSBIが66,352バイトの起動DTBをCore内へ複製。Coreの初期化を経てエントリーテーブルを登録 |
| U-Boot本体とLinux | 最後の有効行は `Registered OP-TEE entry table: 0x171000384`。以後のU-Boot本体のバナー、プロンプト、Linux起動の出力は未確認 |

KSB-092のドメイン初期化の停止地点をこの試行では通過し、KSB-093で追加した起動DTBの複製も
UARTで確認した。実機でのPMPの読み戻し結果は表の2状態に限る。Linux復帰後とEnclave実行時のPMP、
周辺機器・DMA保護、TAとfTPMの動作は今後の確認項目。

最後の出力は `sbi_ecall_tee_domain_exit()` の呼び出し直前に出る。次の引き渡し先は
`untrusted-domain` のS-mode、アドレス `0x102000000` のU-Boot本体。ログだけでは
ドメイン終了処理とU-Boot初期出力の間のどこで止まったかを特定できない。
カーネルモジュールが読み込まれるより前の段階。
[OpenSBIのエントリーテーブル登録とドメイン終了](../opensbi/lib/utils/mpxy/fdt_mpxy_opteed.c#L215)

OP-TEEはeFuseバンク1・2を未書き込みと判定し、HUKの導出を拒否した。
`tee_fs_init_key_manager()` に続いて初期化エラーが出た後も、周辺機器の初期化ログと
エントリーテーブルの登録まで進んだ。HUKのエラーと最後の停止との因果関係は未確定。
診断版で再試験すると、初回ドメイン終了処理が `SBI_ENOMEM (-1004)` を返した。実機と同じ
106 KiBでQEMUでも再現し、空きデータがある状態で割り当て管理枠が枯渇していることを確認した。
Pico-ITX同梱FITのヒープを192 KiBに設定し、OpenSBIの実行範囲を既存の1 MiB内に収めた。
QEMUの混在16/32枠・一律16枠の同居試験が通過した。
[106 KiBの実機UARTとFITチェックサム](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-ksb-098-retest-uart.txt)

[初回の実機UART抜粋](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-ram-boot-uart.txt) ·
[不具合台帳 KSB-098](keystone-bug-report.md#ksb-098)

#### 192 KiBの修正版でU-Bootへ到達

OpenSBIのヒープ192 KiBと実行時752 KiBをUARTで確認した。全16 hartで `boot-host` は15枠、
`optee` は14枠だった。32枠を実装するhart 8–15で追加16枠は無効。起動時の `host` 状態は
判読できた8 hartで15枠だった。hart 0は `PMP rc=0` で `untrusted-domain` に切り替わり、
U-Boot本体の `=>` に到達した。
[修正版の実機UARTとPMPの集計](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-ksb-098-192k-uart.txt)

U-Bootから同梱用DTBでUFS上のLinux 6.18.3 #4を一時起動した。副hart 1〜15のPMP検査に失敗し、
CPU 0だけで初期化が続いた後、組み込みwatchdogのレジスタ読み出しでpanicした。
[Linux起動の実機UART](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-linux-startup-uart.txt) ·
[副hart再開 KSB-099](keystone-bug-report.md#ksb-099) ·
[watchdog KSB-100](keystone-bug-report.md#ksb-100)

`223c5f2` で副hart再開時のPMP再設定とwatchdogの仲介を修正した。
[同梱FITの実機再試験](keystone-bug-report.md#ksb-099-retest)

<a id="pico-itx-linux-pass"></a>
#### 修正版でLinuxの16 CPU起動とKeystoneサンプルを確認

Pico-ITXのUSB RAM起動で、ヒープ192 KiBのOpenSBIとOP-TEEを同梱したFITを使用した。
FSBLは411,776バイト、FITは2,624,105バイト。利用者は11月27日に使ったLinux Imageとモジュールを
継続使用した。Linux 6.18.3 #4、`Image-6.18.3-keystone`、`initrd.img-6.18.3`、
`k3-pico-itx-keystone-optee.dtb` をUARTから確認した。この試行に使った実バイナリの
SHA-256と正確なソースコミットは未収集。
[実機UARTとKeystoneサンプル結果](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-linux-boot-pass-uart.txt)

| 項目 | 実機で確認した結果 |
| --- | --- |
| 起動経路 | ESOS両RCPUが応答し、OpenSBIからOP-TEE Core初期化、U-Boot本体へ進んだ。UFSのLinuxでルートファイルシステムをマウントし、Bianbu 4.0.4へログインして `ls` を実行できた |
| 副hartとPMP | LinuxのSMP起動中にhart 1〜15でPMPを再設定し、すべてで `root-config PASS`。hart 8〜15では上位16枠が無効。Linuxは16 CPUを起動 |
| watchdog | 前回の読み出し例外を越えて、watchdogドライバが起動理由を表示。watchdogによるリセットは未試験 |
| Keystone | `sudo bash tools/run-hello.sh` で `hello` と `hello-native` がともに `enclave exit=0 DESTROY` |
| OP-TEE | DTBの `/firmware/optee` に16個のOP-TEE用チャネルがあり、LinuxのMPXYは全体で21チャネルを登録。Linuxの起動処理が内蔵の `device.pta` のセッションを開閉し、OP-TEE 4.5のドライバ初期化が完了 |

U-Bootは予約メモリ4件の警告と `fail to get alias node efuse_power` を出した後にLinuxへ進んだ。
LinuxはOP-TEE Coreと共有メモリを各16 MiB予約し、RCPU1用の予約領域と既存のM-mode予約領域の重複を
報告した。Linuxの `spacemit-rproc` がRCPU1を登録する際にリソース表の検査で `-22` が出た。
OP-TEEはeFuseバンク1・2が未書き込みとしてHUKの導出を拒否していた。この構成の外部TAの
ロードにはHUKを使うセキュアストレージが必要。
[実機UARTの該当行](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-linux-boot-pass-uart.txt)

次は同じ起動でTEEデバイスを確認し、ユーザー空間からCore内蔵の `device.pta` の応答を試す。
EnclaveとTAの同時実行、fTPM・IMA、DMA保護、実行時のPMP検査は第2節で追跡する。
[実機のOP-TEE試験手順](milkv-jupiter2-stack-install.md#pico-itx-optee-ta-smoke)

## 3. 完了時の記録

ソースのコミットと設定、ハードウェア採取ID、FSBL・FIT・OpenSBI・Core・Linux Image・DTBの
SHA-256、対象hart、UART、試験結果を残す。各項目にビルド、静的照合、QEMU実行、実機実行の
到達点を記録する。KSB-092とKSB-093に修正コミットと確認範囲を追記し、実機ビルド・導入手順に
合格した入力、検証コマンド、切り戻し手順を反映する。
